"""GeckoTerminal API client with 429/403 backoff and bounded social enrichment.

Public rate limit is 30 req/min. Fixed pool discovery uses 5 requests
(new_pools pages 1-3, top pools pages 1-2). New-pool social enrichment is
strictly bounded and cached so it cannot consume the whole request budget.

429 and 403 (new_pools intermittently 403s) are retryable: backoff
20 -> 40 -> 80 s, log, then give up on the cycle without crashing the loop.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

import httpx

log = logging.getLogger("rh_meme_watch.gecko")

BASE_URL = "https://api.geckoterminal.com/api/v2"
API_VERSION_HEADER = "application/json;version=20230302"
USER_AGENT = "rh-meme-watch/0.1 (Robinhood Chain pool watcher; github.com/Pauda-M/rh-meme-watch)"

BACKOFF_SECONDS = (20.0, 40.0, 80.0)
RETRYABLE_STATUS = frozenset({403, 429, 500, 502, 503, 504})
MULTI_BATCH = 30  # /pools/multi/ accepts at most 30 addresses per request
SOCIAL_CACHE_MAX = 2048
SOCIAL_FIELDS = (
    "twitter_handle",
    "telegram_handle",
    "discord_url",
    "farcaster_url",
    "zora_url",
)


class GeckoUnavailable(RuntimeError):
    """The API could not be fetched this cycle (after backoff)."""


class GeckoClient:
    def __init__(
        self,
        http: httpx.Client | None = None,
        base_url: str = BASE_URL,
        sleep: Callable[[float], None] = time.sleep,
        social_lookups_per_cycle: int = 6,
        social_cache_ttl_sec: int = 21600,
        social_miss_ttl_sec: int = 300,
    ) -> None:
        self._own_http = http is None
        self.http = http or httpx.Client(timeout=httpx.Timeout(20.0))
        self.base_url = base_url.rstrip("/")
        self.sleep = sleep
        self.social_lookups_per_cycle = max(0, social_lookups_per_cycle)
        self.social_cache_ttl_sec = max(60, social_cache_ttl_sec)
        self.social_miss_ttl_sec = max(30, social_miss_ttl_sec)
        self._social_lookups_this_cycle = 0
        self._pool_social_cache: dict[
            str, tuple[float, dict[str, tuple[str, ...]], int]
        ] = {}

    def close(self) -> None:
        if self._own_http:
            self.http.close()

    def _get(
        self, path: str, params: dict | None = None, retries: int | None = None
    ) -> dict:
        """GET with backoff. ``retries=0`` means a single attempt, no sleeping.

        Market data is worth waiting 20+40+80 s for; optional enrichment is not,
        because that sleep blocks the whole poll loop.
        """
        backoff = BACKOFF_SECONDS if retries is None else BACKOFF_SECONDS[:retries]
        url = f"{self.base_url}{path}"
        headers = {"accept": API_VERSION_HEADER, "user-agent": USER_AGENT}
        last_error = "unknown"
        for attempt in range(len(backoff) + 1):
            try:
                resp = self.http.get(url, params=params, headers=headers)
            except httpx.HTTPError as exc:
                last_error = f"transport error: {exc!r}"
                resp = None
            if resp is not None:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        last_error = f"invalid JSON: {exc!r}"
                elif resp.status_code in RETRYABLE_STATUS:
                    last_error = f"HTTP {resp.status_code}"
                else:
                    raise GeckoUnavailable(
                        f"GET {path} failed with non-retryable HTTP {resp.status_code}"
                    )
            if attempt < len(backoff):
                delay = backoff[attempt]
                log.warning(
                    "GET %s -> %s; backing off %.0fs (attempt %d/%d)",
                    path,
                    last_error,
                    delay,
                    attempt + 1,
                    len(backoff),
                )
                self.sleep(delay)
        raise GeckoUnavailable(f"GET {path} still failing after backoff: {last_error}")

    @staticmethod
    def _pool_address(item: dict) -> str:
        pool_id = str(item.get("id") or "")
        return pool_id.split("_", 1)[1] if "_" in pool_id else pool_id

    @staticmethod
    def _socials_from_info(payload: dict) -> dict[str, tuple[str, ...]]:
        """Return token-resource id -> normalized social labels/URLs."""
        data = payload.get("data") or []
        if isinstance(data, dict):
            data = [data]
        result: dict[str, tuple[str, ...]] = {}
        for token in data:
            if not isinstance(token, dict):
                continue
            token_id = str(token.get("id") or "")
            attrs = token.get("attributes") or {}
            socials: list[str] = []
            twitter = str(attrs.get("twitter_handle") or "").strip().lstrip("@")
            telegram = str(attrs.get("telegram_handle") or "").strip().lstrip("@")
            discord = str(attrs.get("discord_url") or "").strip()
            farcaster = str(attrs.get("farcaster_url") or "").strip()
            zora = str(attrs.get("zora_url") or "").strip()
            if twitter:
                socials.append(f"https://x.com/{twitter}")
            if telegram:
                socials.append(f"https://t.me/{telegram}")
            if discord:
                socials.append(discord)
            if farcaster:
                socials.append(farcaster)
            if zora:
                socials.append(zora)
            if token_id:
                result[token_id] = tuple(dict.fromkeys(socials))
        return result

    def _pool_socials(self, network: str, pool_address: str) -> dict[str, tuple[str, ...]]:
        now = time.time()
        cached = self._pool_social_cache.get(pool_address)
        if cached is not None and now - cached[0] < cached[2]:
            return cached[1]
        if self._social_lookups_this_cycle >= self.social_lookups_per_cycle:
            return {}
        self._social_lookups_this_cycle += 1
        try:
            # One attempt only: metadata is optional, and _get's 20/40/80 s
            # backoff would stall the market-data loop for minutes per pool.
            payload = self._get(
                f"/networks/{network}/pools/{pool_address}/info", retries=0
            )
            socials = self._socials_from_info(payload)
        except GeckoUnavailable as exc:
            # Social metadata is a qualification dependency, not a reason to
            # abort the whole market-data cycle. Missing metadata fails closed.
            log.info("social metadata unavailable for %s: %s", pool_address, exc)
            socials = {}
        # A known-good answer is stable, so it is cached for the full TTL. An
        # empty or failed answer is not: projects routinely deploy first and add
        # their socials minutes later, and a 6 h negative cache would suppress
        # those for the entire alert window. Re-check them soon instead.
        has_socials = any(socials.values())
        ttl = self.social_cache_ttl_sec if has_socials else self.social_miss_ttl_sec
        self._pool_social_cache[pool_address] = (now, socials, ttl)
        self._prune_social_cache(now)
        return socials

    def _prune_social_cache(self, now: float) -> None:
        """Drop expired entries so a long-running process cannot grow unbounded."""
        if len(self._pool_social_cache) <= SOCIAL_CACHE_MAX:
            return
        self._pool_social_cache = {
            addr: entry
            for addr, entry in self._pool_social_cache.items()
            if now - entry[0] < entry[2]
        }

    def socials_for(
        self, pool_address: str, network: str = "robinhood"
    ) -> dict[str, tuple[str, ...]]:
        """Token-id -> socials for one pool, cached and budgeted.

        Called only for pools that have already cleared the free gates, so the
        scarce budget is spent where the answer decides the outcome.
        """
        if not pool_address:
            return {}
        return self._pool_socials(network, pool_address)

    def _enrich_new_pool_socials(self, items: list[dict], network: str) -> list[dict]:
        for item in items:
            if not isinstance(item, dict):
                continue
            address = self._pool_address(item)
            if not address:
                continue
            item["_socials_by_token"] = self._pool_socials(network, address)
        return items

    def new_pools(self, network: str = "robinhood", pages: int = 3) -> list[dict]:
        # A new polling cycle starts here. Discovery no longer enriches socials
        # blindly: it returned ~60 pools per cycle against a budget of 3, so the
        # budget was spent on the newest pools - which are below the minimum age
        # and cannot alert anyway - while every real candidate reached the social
        # gate with no data and failed closed. Socials are now fetched on demand,
        # by the caller, only for pools that have cleared every free check.
        self._social_lookups_this_cycle = 0
        items: list[dict] = []
        for page in range(1, pages + 1):
            payload = self._get(f"/networks/{network}/new_pools", {"page": page})
            items.extend(payload.get("data") or [])
        return items

    def pools_by_address(
        self, addresses: list[str], network: str = "robinhood"
    ) -> list[dict]:
        """Fetch specific pools by address, whether or not they are still ranked.

        Discovery only returns pools inside the new-pool and top-pool windows, so
        a pool drops out of view within minutes of being alerted and stops being
        observed. Anything that needs a history - the liquidity-retention check
        most of all - then never accumulates enough samples to reach a verdict.

        The /multi/ endpoint takes up to 30 addresses per request, so re-reading a
        200-pool watchlist costs 7 requests rather than 200, which is what makes
        this affordable inside the rate limit at all.
        """
        items: list[dict] = []
        for start in range(0, len(addresses), MULTI_BATCH):
            batch = [a for a in addresses[start : start + MULTI_BATCH] if a]
            if not batch:
                continue
            try:
                # One attempt, no sleeping. A rate-limited refresh must cost a
                # cycle of history, never the cycle: seven batches each backing
                # off 20s exceeds the whole poll interval and the loop starves.
                payload = self._get(
                    f"/networks/{network}/pools/multi/{','.join(batch)}", retries=0
                )
            except GeckoUnavailable as exc:
                # Re-reading the watchlist is maintenance, not discovery. Losing a
                # batch costs one cycle of history, never the cycle itself.
                log.info("watchlist refresh batch failed: %s", exc)
                continue
            items.extend(payload.get("data") or [])
        return items

    def top_pools(self, network: str = "robinhood", pages: int = 2) -> list[dict]:
        items: list[dict] = []
        for page in range(1, pages + 1):
            payload = self._get(
                f"/networks/{network}/pools",
                {"sort": "h24_volume_usd_desc", "page": page},
            )
            items.extend(payload.get("data") or [])
        return items

    def search_pools(self, query: str, network: str = "robinhood") -> list[dict]:
        payload = self._get("/search/pools", {"query": query, "network": network})
        return payload.get("data") or []
