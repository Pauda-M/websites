"""GeckoTerminal API client with 429/403 backoff.

Public rate limit is 30 req/min; a full cycle uses 5 fixed requests
(new_pools pages 1-3, top pools pages 1-2) plus at most
``Config.fdv_lookups_per_cycle`` search requests -> budget <= 8 req/min.

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


class GeckoUnavailable(RuntimeError):
    """The API could not be fetched this cycle (after backoff)."""


class GeckoClient:
    def __init__(
        self,
        http: httpx.Client | None = None,
        base_url: str = BASE_URL,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._own_http = http is None
        self.http = http or httpx.Client(timeout=httpx.Timeout(20.0))
        self.base_url = base_url.rstrip("/")
        self.sleep = sleep

    def close(self) -> None:
        if self._own_http:
            self.http.close()

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        headers = {"accept": API_VERSION_HEADER, "user-agent": USER_AGENT}
        last_error = "unknown"
        for attempt in range(len(BACKOFF_SECONDS) + 1):
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
            if attempt < len(BACKOFF_SECONDS):
                delay = BACKOFF_SECONDS[attempt]
                log.warning(
                    "GET %s -> %s; backing off %.0fs (attempt %d/%d)",
                    path,
                    last_error,
                    delay,
                    attempt + 1,
                    len(BACKOFF_SECONDS),
                )
                self.sleep(delay)
        raise GeckoUnavailable(f"GET {path} still failing after backoff: {last_error}")

    def new_pools(self, network: str = "robinhood", pages: int = 3) -> list[dict]:
        items: list[dict] = []
        for page in range(1, pages + 1):
            payload = self._get(f"/networks/{network}/new_pools", {"page": page})
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
