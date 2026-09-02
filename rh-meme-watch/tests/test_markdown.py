"""MarkdownV2 escaping: reserved chars in symbols must never leak unescaped."""

from __future__ import annotations

from datetime import timedelta

from rh_meme_watch.fmt import escape_md, fmt_age, fmt_int, fmt_usd
from rh_meme_watch.messages import build_new_alert, build_startup
from rh_meme_watch.models import Pool
from rh_meme_watch.rules import classify

from conftest import NOW, api_item, mk_cfg

RESERVED = set("_*[]()~`>#+-=|{}.!")


def assert_fully_escaped(text: str) -> None:
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2  # backslash escapes exactly the next char
            continue
        assert ch not in RESERVED, f"unescaped {ch!r} at index {i} in {text!r}"
        i += 1


def test_escape_md_covers_every_reserved_char():
    nasty = "a_b*c[d]e(f)g~h`i>j#k+l-m=n|o{p}q.r!s\\t"
    escaped = escape_md(nasty)
    assert_fully_escaped(escaped)
    # dollar sign is NOT a MarkdownV2 reserved char and must pass through bare
    assert escape_md("$150k") == "$150k"


def test_alert_with_hostile_symbol_is_fully_escaped(tmp_path):
    cfg = mk_cfg(tmp_path)
    pool = Pool.from_api(
        api_item(
            name="D.O-G(E)+*_$ / AAPL",
            reserve="118000",
            created_at=NOW - timedelta(minutes=41),
        )
    )
    cls = classify(pool, cfg)
    text = build_new_alert(pool, cls, 440_000.0, NOW)
    assert_fully_escaped(text)
    assert "STOCK\\-PAIRED" in text  # the static prefix is escaped too


def test_alert_urls_are_escaped(tmp_path):
    cfg = mk_cfg(tmp_path)
    pool = Pool.from_api(
        api_item(name="PEPE / WETH", reserve="200000", created_at=NOW - timedelta(minutes=10))
    )
    text = build_new_alert(pool, classify(pool, cfg), None, NOW)
    assert_fully_escaped(text)
    assert "geckoterminal\\.com" in text


def test_startup_message_content(tmp_path):
    cfg = mk_cfg(tmp_path)
    text = build_startup(cfg)
    assert_fully_escaped(text)
    plain = text.replace("\\", "")
    assert plain == "rh-meme-watch up · floor $150k / stock $75k · poll 60s"


def test_formatting_helpers():
    assert fmt_usd(118_000.44) == "$118k"
    assert fmt_usd(440_000) == "$440k"
    assert fmt_usd(1_230_000) == "$1.2M"
    assert fmt_usd(2_000_000_000) == "$2B"
    assert fmt_usd(950) == "$950"
    assert fmt_usd(1_500) == "$1.5k"
    assert fmt_usd(None) == "n/a"
    assert fmt_int(1204) == "1 204"
    assert fmt_age(41) == "41m"
    assert fmt_age(3 * 60 + 12) == "3h12m"
    assert fmt_age(None) == "n/a"
