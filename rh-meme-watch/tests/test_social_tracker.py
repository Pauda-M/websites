"""Social link verification and the red/green flag.

The invariant these tests exist to defend: **unknown is never scored as bad.**
A link the checker could not reach, and an audience no source can measure, must
not produce a red flag - otherwise one blocked network path or one missing API
token turns every token on the chain red and the flag stops meaning anything.
"""

from __future__ import annotations

import httpx
import respx

from rh_meme_watch.config import Config
from rh_meme_watch.rules import social_verdict
from rh_meme_watch.socials import (
    DEAD,
    LIVE,
    UNKNOWN,
    LinkCheck,
    SocialChecker,
    platform_of,
)

from conftest import mk_cfg

TG = "https://t.me/realchan"
XL = "https://x.com/realproj"

TG_LIVE = (
    '<html><body><div class="tgme_page">'
    '<div class="tgme_page_extra">12 345 subscribers</div>'
    "</div></body></html>"
)
TG_DEAD = "<html><body><div>If you have Telegram, you can contact…</div></body></html>"


def _checker(**kw) -> SocialChecker:
    kw.setdefault("http", httpx.Client(follow_redirects=True))
    return SocialChecker(**kw)


# --- platform detection -----------------------------------------------------

def test_platform_detection():
    assert platform_of("https://x.com/a") == "x"
    assert platform_of("https://twitter.com/a") == "x"
    assert platform_of("https://t.me/a") == "telegram"
    assert platform_of("https://discord.gg/a") == "discord"
    assert platform_of("https://warpcast.com/a") == "farcaster"
    assert platform_of("not a url") == "link"


# --- link liveness ----------------------------------------------------------

@respx.mock
def test_telegram_live_channel_yields_subscriber_count():
    respx.get(TG).mock(return_value=httpx.Response(200, html=TG_LIVE))
    result = _checker().check(TG)
    assert result.state == LIVE
    assert result.engagement == 12345, "space-separated thousands parsed"


@respx.mock
def test_telegram_page_without_a_channel_preview_is_dead():
    respx.get(TG).mock(return_value=httpx.Response(200, html=TG_DEAD))
    assert _checker().check(TG).state == DEAD


@respx.mock
def test_404_is_a_confirmed_dead_link():
    respx.get(TG).mock(return_value=httpx.Response(404))
    result = _checker().check(TG)
    assert result.state == DEAD
    assert "404" in result.note


@respx.mock
def test_rate_limit_is_unknown_not_dead():
    """429 from a hostile host says nothing about whether the link is real."""
    respx.get(TG).mock(return_value=httpx.Response(429))
    assert _checker().check(TG).state == UNKNOWN


@respx.mock
def test_network_failure_is_unknown_not_dead():
    respx.get(TG).mock(side_effect=httpx.ConnectError("egress blocked"))
    result = _checker().check(TG)
    assert result.state == UNKNOWN
    assert result.note == "unreachable"


@respx.mock
def test_x_without_a_token_is_unknown_not_live():
    """Unauthenticated x.com serves the same shell for live and deleted posts."""
    respx.get(XL).mock(return_value=httpx.Response(200, html="<html></html>"))
    result = _checker().check(XL)
    assert result.state == UNKNOWN
    assert "token" in result.note


# --- budget and caching -----------------------------------------------------

@respx.mock
def test_budget_caps_requests_and_does_not_cache_the_skip():
    route = respx.get(url__regex=r"https://t\.me/.*").mock(
        return_value=httpx.Response(200, html=TG_LIVE)
    )
    checker = _checker(checks_per_cycle=2)
    urls = [f"https://t.me/c{i}" for i in range(5)]
    first = [checker.check(u) for u in urls]
    assert route.call_count == 2
    assert sum(r.state == UNKNOWN for r in first) == 3

    # next cycle: the skipped links are retried, not written off
    checker.start_cycle()
    checker.check(urls[4])
    assert route.call_count == 3


@respx.mock
def test_settled_verdicts_cache_but_unknowns_recheck_sooner():
    respx.get(TG).mock(return_value=httpx.Response(200, html=TG_LIVE))
    checker = _checker()
    checker.check(TG)
    _, result, ttl = checker._cache[TG]
    assert result.state == LIVE and ttl == checker.cache_ttl_sec

    respx.get(XL).mock(return_value=httpx.Response(500))
    checker.check(XL)
    _, result, ttl = checker._cache[XL]
    assert result.state == UNKNOWN and ttl == checker.unknown_ttl_sec
    assert ttl < checker.cache_ttl_sec


# --- the flag ---------------------------------------------------------------

def test_no_socials_is_red(tmp_path):
    v = social_verdict([], {}, mk_cfg(tmp_path))
    assert v.is_red and v.reason == "no socials"


def test_every_link_confirmed_dead_is_red(tmp_path):
    checks = {TG: LinkCheck(TG, "telegram", DEAD)}
    v = social_verdict([TG], checks, mk_cfg(tmp_path))
    assert v.is_red and "dead" in v.reason


def test_live_link_above_the_floor_is_green(tmp_path):
    cfg = mk_cfg(tmp_path, social_green_engagement=1000)
    checks = {TG: LinkCheck(TG, "telegram", LIVE, 4200)}
    v = social_verdict([TG], checks, cfg)
    assert v.is_green and v.engagement == 4200


def test_live_link_below_the_floor_is_amber_not_green(tmp_path):
    cfg = mk_cfg(tmp_path, social_green_engagement=1000)
    checks = {TG: LinkCheck(TG, "telegram", LIVE, 200)}
    assert social_verdict([TG], checks, cfg).flag == "amber"


def test_unmeasurable_audience_is_amber_never_red(tmp_path):
    """No free source exists for X views; that must not read as zero views."""
    checks = {XL: LinkCheck(XL, "x", LIVE, None)}
    v = social_verdict([XL], checks, mk_cfg(tmp_path))
    assert v.flag == "amber"
    assert not v.is_red
    assert v.engagement is None


def test_unreachable_links_are_amber_never_red(tmp_path):
    """One blocked egress path must not red-flag the whole chain."""
    checks = {XL: LinkCheck(XL, "x", UNKNOWN, None, "unreachable")}
    assert social_verdict([XL], checks, mk_cfg(tmp_path)).flag == "amber"


def test_unchecked_links_are_amber(tmp_path):
    assert social_verdict([XL], {}, mk_cfg(tmp_path)).flag == "amber"


def test_one_dead_link_beside_a_live_one_is_not_red(tmp_path):
    cfg = mk_cfg(tmp_path, social_green_engagement=1000)
    checks = {
        TG: LinkCheck(TG, "telegram", LIVE, 9000),
        XL: LinkCheck(XL, "x", DEAD),
    }
    v = social_verdict([TG, XL], checks, cfg)
    assert v.is_green and v.dead == 1 and v.live == 1


def test_best_engagement_wins_across_platforms(tmp_path):
    cfg = mk_cfg(tmp_path, social_green_engagement=1000)
    checks = {
        TG: LinkCheck(TG, "telegram", LIVE, 1500),
        XL: LinkCheck(XL, "x", LIVE, 80),
    }
    assert social_verdict([TG, XL], checks, cfg).engagement == 1500
