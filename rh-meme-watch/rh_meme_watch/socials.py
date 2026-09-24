"""Social link verification: does the link exist, and does it go anywhere real?

A registered social handle proves nothing - a deployer can point at a deleted
post, a dead channel, or a page that has nothing to do with the token. This
module does the check a human would: open the link and see whether anything is
actually there.

The rule that governs every decision here: **unknown is not dead**. A link this
module could not reach - because egress was blocked, the host rate-limited us,
or the budget ran out - is reported as ``UNKNOWN``, never as ``DEAD``. Treating
unreachable as dead would red-flag every token the moment a network path broke,
which is worse than having no check at all.

Engagement numbers follow the same rule. Telegram publishes subscriber counts on
its public preview pages, so those are measurable for free. X post views are not
available without a paid API token; absent one, X engagement is ``None``
(unmeasured), never ``0``. "No views" must never be inferred from "no source".
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

USER_AGENT = (
    "rh-meme-watch/0.1 (Robinhood Chain pool watcher; "
    "github.com/Pauda-M/rh-meme-watch)"
)

LIVE = "live"
DEAD = "dead"
UNKNOWN = "unknown"

# Telegram's public preview page carries the subscriber count in a meta tag or
# an explicit counter element. Both shapes are seen in the wild.
_TG_SUBS = (
    re.compile(r'<div class="tgme_page_extra">([\d\s,\.]+)\s*(?:subscribers|members)', re.I),
    re.compile(r'([\d\s,\.]+)\s*(?:subscribers|members)', re.I),
)
# A t.me URL that resolves but has no channel preview is a dead handle.
_TG_ALIVE = re.compile(r'tgme_page|tgme_channel|tgme_header', re.I)


def _int(raw: str) -> int | None:
    digits = re.sub(r"[^\d]", "", raw or "")
    if not digits:
        return None
    try:
        value = int(digits)
    except ValueError:
        return None
    return value if 0 <= value < 10**9 else None


@dataclass(frozen=True)
class LinkCheck:
    """One social link's verdict.

    ``state`` is LIVE/DEAD/UNKNOWN. ``engagement`` is a measured audience number
    (Telegram subscribers, X post views) or None when no source could supply one
    - which is NOT the same as zero.
    """

    url: str
    platform: str
    state: str = UNKNOWN
    engagement: int | None = None
    note: str = ""

    @property
    def is_live(self) -> bool:
        return self.state == LIVE

    @property
    def is_dead(self) -> bool:
        return self.state == DEAD


def platform_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if host in {"x.com", "twitter.com", "mobile.twitter.com"}:
        return "x"
    if host in {"t.me", "telegram.me"}:
        return "telegram"
    if "discord" in host:
        return "discord"
    if "farcaster" in host or "warpcast" in host:
        return "farcaster"
    if "zora" in host:
        return "zora"
    return host or "link"


class SocialChecker:
    """Bounded, cached link checker. Never raises into the poll loop."""

    def __init__(
        self,
        http: httpx.Client | None = None,
        *,
        checks_per_cycle: int = 8,
        cache_ttl_sec: int = 3600,
        unknown_ttl_sec: int = 300,
        timeout_sec: float = 8.0,
        x_bearer_token: str = "",
    ) -> None:
        self._own_http = http is None
        self.http = http or httpx.Client(
            timeout=httpx.Timeout(timeout_sec), follow_redirects=True
        )
        self.checks_per_cycle = max(0, checks_per_cycle)
        self.cache_ttl_sec = max(60, cache_ttl_sec)
        self.unknown_ttl_sec = max(30, unknown_ttl_sec)
        self.x_bearer_token = x_bearer_token
        self._spent = 0
        self._cache: dict[str, tuple[float, LinkCheck, int]] = {}

    def close(self) -> None:
        if self._own_http:
            self.http.close()

    def start_cycle(self) -> None:
        self._spent = 0

    def check(self, url: str, now: float | None = None) -> LinkCheck:
        now = time.time() if now is None else now
        platform = platform_of(url)
        cached = self._cache.get(url)
        if cached is not None and now - cached[0] < cached[2]:
            return cached[1]
        if self._spent >= self.checks_per_cycle:
            # Budget exhausted: explicitly unknown, and NOT cached, so the link
            # is retried next cycle rather than being written off.
            return LinkCheck(url, platform, UNKNOWN, None, "budget spent")
        self._spent += 1
        result = self._check_now(url, platform)
        # A settled verdict is stable enough for the long TTL; an unknown is not
        # a finding, so it is re-checked soon.
        ttl = self.cache_ttl_sec if result.state != UNKNOWN else self.unknown_ttl_sec
        self._cache[url] = (now, result, ttl)
        return result

    def _check_now(self, url: str, platform: str) -> LinkCheck:
        try:
            resp = self.http.get(url, headers={"user-agent": USER_AGENT})
        except httpx.HTTPError as exc:
            # Network failure says nothing about the link. Stay UNKNOWN.
            log.info("social check unreachable %s: %r", url, exc)
            return LinkCheck(url, platform, UNKNOWN, None, "unreachable")

        if resp.status_code in (404, 410):
            return LinkCheck(url, platform, DEAD, None, f"HTTP {resp.status_code}")
        if resp.status_code >= 400:
            # 403/429 from a hostile or rate-limiting host is not evidence of a
            # dead link.
            return LinkCheck(url, platform, UNKNOWN, None, f"HTTP {resp.status_code}")

        if platform == "telegram":
            return self._telegram(url, resp.text)
        if platform == "x":
            return self._x(url, resp)
        return LinkCheck(url, platform, LIVE, None, f"HTTP {resp.status_code}")

    def _telegram(self, url: str, body: str) -> LinkCheck:
        """t.me publishes subscriber counts on its public preview - free signal."""
        if not _TG_ALIVE.search(body):
            return LinkCheck(url, "telegram", DEAD, None, "no channel preview")
        for pattern in _TG_SUBS:
            match = pattern.search(body)
            if match:
                count = _int(match.group(1))
                if count is not None:
                    return LinkCheck(url, "telegram", LIVE, count, "subscribers")
        return LinkCheck(url, "telegram", LIVE, None, "no count published")

    def _x(self, url: str, resp: httpx.Response) -> LinkCheck:
        """Unauthenticated x.com serves the same JS shell for live and deleted
        posts, so a 200 proves nothing. Without a bearer token this stays
        UNKNOWN rather than being scored as live."""
        if not self.x_bearer_token:
            return LinkCheck(url, "x", UNKNOWN, None, "no X API token")
        return LinkCheck(url, "x", LIVE, None, "token path not implemented")
