"""Parsing, against frames actually captured from the live stream."""

from __future__ import annotations

import pytest

from pf_meme_watch.models import CREATE, MIGRATE, STATUS, Launch, parse_frame

from conftest import frames


def _by_symbol(symbol: str) -> Launch:
    for raw in frames():
        parsed = parse_frame(raw)
        if parsed.symbol == symbol:
            return parsed
    raise AssertionError(f"{symbol} not in fixture")


def test_every_captured_frame_parses_without_raising():
    parsed = [parse_frame(raw) for raw in frames()]
    assert len(parsed) == 10
    assert {p.kind for p in parsed} == {CREATE, MIGRATE, STATUS}


def test_subscription_acknowledgements_are_not_launches():
    status = [parse_frame(r) for r in frames() if parse_frame(r).kind == STATUS]
    assert len(status) == 3
    assert any("API key" in s.message for s in status), "the paid-tier notice"


def test_migrate_frame_carries_no_metrics():
    mig = next(p for p in map(parse_frame, frames()) if p.kind == MIGRATE)
    assert mig.mint and mig.pool == "raydium-cpmm"
    assert mig.mcap_sol is None and mig.dev_share is None
    assert mig.name == "" and mig.uri == ""


def test_standard_launch_fields():
    pool = _by_symbol("mayhem")
    assert pool.pool == "pump"
    assert pool.mint.endswith("pump")
    assert pool.mcap_sol == pytest.approx(31.769, abs=0.01)
    assert pool.mayhem is True
    assert pool.uri.startswith("https://")


def test_unknown_frame_shape_becomes_status_rather_than_raising():
    """The socket must survive a message this code has never seen."""
    assert parse_frame({"txType": "somethingNew"}).kind == STATUS
    assert parse_frame({}).kind == STATUS
    assert parse_frame([]).kind == STATUS


def test_market_cap_is_sol_and_needs_a_price_to_become_usd():
    pool = _by_symbol("SOCK")
    assert pool.mcap_sol == pytest.approx(43.686, abs=0.01)
    assert pool.mcap_usd(None) is None, "no price, no number"
    assert pool.mcap_usd(0) is None
    assert pool.mcap_usd(200) == pytest.approx(8737.2, abs=1.0)
