"""Alerted pools must keep being observed after they drop out of discovery.

Discovery returns only the new-pool and top-pool windows. A pool falls out of
both within minutes of being alerted, and before this refresh existed its
snapshot history stopped dead at that point. On live data that left most alerted
pools with a handful of samples spanning a few minutes - far short of what a
liquidity-retention verdict needs - so the retention check could never settle and
the dashboard filter that depended on it was permanently empty.
"""

from __future__ import annotations

from datetime import timedelta

from rh_meme_watch.rules import lock_verdict

from datetime import datetime, timezone

from conftest import NOW, FakeGecko, api_item, mk_app, mk_cfg

ADDR = "0x" + "5a" * 20


def _alerted_pool(**over) -> dict:
    return api_item(
        name="KEEPER / WETH",
        address=ADDR,
        reserve="400000",
        fdv="2000000",
        vol_h1="90000",
        created_at=NOW - timedelta(minutes=30),
        tx_h1={"buys": 150, "sells": 70, "buyers": 90, "sellers": 45},
        **over,
    )


def test_pool_that_leaves_discovery_keeps_accumulating_history(tmp_path):
    gecko = FakeGecko(new_items=[_alerted_pool()])
    cfg = mk_cfg(tmp_path, digest_hour=25, liq_floor=150_000.0)
    app, telegram, clock = mk_app(tmp_path, gecko, cfg=cfg)

    app.run_cycle()
    assert app.store.was_alerted(ADDR), "alerted on the cycle that discovered it"

    # It now drops out of both discovery windows, but is served by the refresh.
    gecko.new_items = []
    gecko.top_items = []
    gecko.watchlist_items = {ADDR: _alerted_pool()}

    for _ in range(12):
        clock.advance(minutes=5)
        app.run_cycle()

    snaps = app.store.snapshots(ADDR, datetime(2000, 1, 1, tzinfo=timezone.utc))
    assert len(snaps) >= 10, f"history kept growing, got {len(snaps)}"
    assert gecko.watchlist_calls, "the refresh actually asked for it"
    assert ADDR in gecko.watchlist_calls[-1]


def test_the_refresh_is_what_lets_a_retention_verdict_settle(tmp_path):
    """The whole point: enough samples over enough time to reach a verdict."""
    gecko = FakeGecko(new_items=[_alerted_pool()])
    cfg = mk_cfg(
        tmp_path, digest_hour=25, liq_floor=150_000.0,
        lock_min_samples=10, lock_min_age_min=30,
    )
    app, telegram, clock = mk_app(tmp_path, gecko, cfg=cfg)
    app.run_cycle()

    gecko.new_items = []
    gecko.top_items = []
    gecko.watchlist_items = {ADDR: _alerted_pool()}
    for _ in range(14):
        clock.advance(minutes=5)
        app.run_cycle()

    snaps = app.store.snapshots(ADDR, datetime(2000, 1, 1, tzinfo=timezone.utc))
    history = [(s["ts"], s["reserve"]) for s in snaps]
    from rh_meme_watch.store import _parse

    parsed = [(_parse(ts), r) for ts, r in history]
    verdict = lock_verdict([(t, r) for t, r in parsed if t], app.cfg, 400_000.0)
    assert verdict.known, "a verdict can now be reached at all"
    assert verdict.locked, "steady liquidity over the window reads as held"


def test_pools_already_in_discovery_are_not_refetched(tmp_path):
    """No point spending requests on something the cycle already has."""
    gecko = FakeGecko(new_items=[_alerted_pool()])
    cfg = mk_cfg(tmp_path, digest_hour=25, liq_floor=150_000.0)
    app, telegram, clock = mk_app(tmp_path, gecko, cfg=cfg)
    app.run_cycle()

    clock.advance(minutes=5)
    app.run_cycle()  # still in discovery

    for call in gecko.watchlist_calls:
        assert ADDR not in call, "refetched a pool already in hand"


def test_a_failed_refresh_does_not_break_the_cycle(tmp_path):
    """Re-reading the watchlist is maintenance; losing it must not lose the cycle."""
    gecko = FakeGecko(new_items=[_alerted_pool()])
    cfg = mk_cfg(tmp_path, digest_hour=25, liq_floor=150_000.0)
    app, telegram, clock = mk_app(tmp_path, gecko, cfg=cfg)
    app.run_cycle()

    gecko.new_items = []
    gecko.top_items = []
    gecko.watchlist_items = {}  # refresh returns nothing at all

    clock.advance(minutes=5)
    assert app.run_cycle_safe() is True
    assert app.cfg.heartbeat_path.exists(), "the cycle still completed"
