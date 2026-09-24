"""SOL/USD, because the stream prices market caps in SOL and the filter is in USD.

This is not a rounding detail. A $6,000 floor is 24 SOL at $250 and 40 SOL at
$150, and on the captured sample that is the difference between 5 of 5 launches
clearing it and 1 of 5. A hardcoded SOL figure silently becomes a different
filter every week - which is presumably why the checklist this implements keeps
its numbers in a members' area rather than in the video.

When no price can be established the market-cap gate is SKIPPED, not failed. A
minimum-threshold gate evaluated against an unknown price would reject
everything, which is exactly how the social gate silently zeroed the other
watcher. An unmeasurable input disables its own check and says so.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

log = logging.getLogger("pf_meme_watch.price")

USER_AGENT = "pf-meme-watch/0.1 (pump.fun launch watcher)"
WRAPPED_SOL = "So11111111111111111111111111111111111111112"
GECKO_URL = (
    "https://api.geckoterminal.com/api/v2/networks/solana/tokens/" + WRAPPED_SOL
)
GECKO_HEADERS = {
    "accept": "application/json;version=20230302",
    "user-agent": USER_AGENT,
}
# A price this far outside plausibility is a parse error, not a market move.
SANE_MIN_USD = 1.0
SANE_MAX_USD = 100_000.0


@dataclass
class SolPrice:
    """Cached SOL/USD. ``value`` is None when no price could be established."""

    value: float | None = None
    fetched_at: float = 0.0
    stale_after_sec: float = 300.0
    max_age_sec: float = 3600.0

    def is_fresh(self, now: float) -> bool:
        return self.value is not None and (now - self.fetched_at) < self.stale_after_sec

    def usable(self, now: float) -> float | None:
        """A slightly stale price still beats no price; an ancient one does not.

        SOL does not move enough in a few minutes to flip this filter, but an
        hour-old price during a sharp move would quietly shift the threshold.
        """
        if self.value is None or (now - self.fetched_at) > self.max_age_sec:
            return None
        return self.value


class SolPriceFeed:
    """Polls a free public source, caches, and never raises into the caller."""

    def __init__(
        self,
        http: httpx.Client | None = None,
        url: str = GECKO_URL,
        *,
        stale_after_sec: float = 300.0,
        max_age_sec: float = 3600.0,
        timeout_sec: float = 10.0,
    ) -> None:
        self._own_http = http is None
        self.http = http or httpx.Client(timeout=httpx.Timeout(timeout_sec))
        self.url = url
        self.cached = SolPrice(
            stale_after_sec=stale_after_sec, max_age_sec=max_age_sec
        )
        self.fetches = 0
        self.failures = 0

    def close(self) -> None:
        if self._own_http:
            self.http.close()

    def usd(self, now: float | None = None) -> float | None:
        """Current SOL/USD, refreshing when stale. None if none can be had."""
        now = time.time() if now is None else now
        if self.cached.is_fresh(now):
            return self.cached.value
        fetched = self._fetch()
        if fetched is not None:
            self.cached.value = fetched
            self.cached.fetched_at = now
            return fetched
        self.failures += 1
        # Fall back to the last good price while it is still defensible, rather
        # than dropping to None and disabling the gate on one failed request.
        return self.cached.usable(now)

    def _fetch(self) -> float | None:
        self.fetches += 1
        try:
            resp = self.http.get(self.url, headers=GECKO_HEADERS)
            if resp.status_code != 200:
                log.info("sol price: HTTP %s", resp.status_code)
                return None
            attrs = ((resp.json() or {}).get("data") or {}).get("attributes") or {}
            raw = attrs.get("price_usd")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            log.info("sol price unavailable: %r", exc)
            return None
        try:
            price = float(raw)
        except (TypeError, ValueError):
            return None
        if not (SANE_MIN_USD <= price <= SANE_MAX_USD):
            log.warning("sol price %r outside sane range; ignoring", price)
            return None
        return price


def mcap_usd(mcap_sol: float | None, sol_usd: float | None) -> float | None:
    """Convert, or return None when either side is unknown. Never guesses."""
    if mcap_sol is None or sol_usd is None or sol_usd <= 0:
        return None
    return mcap_sol * sol_usd
