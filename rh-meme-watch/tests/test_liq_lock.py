"""Liquidity-lock proxy: verdict maths, escalation/digest gating, MIN_LIQ 20k."""

from __future__ import annotations

from datetime import timedelta

from rh_meme_watch.config import Config
from rh_meme_watch.models import Pool
from rh_meme_watch.rules import escalation_verdict, lock_verdict

from conftest import NOW, FakeGecko, api_item, mk_app, mk_cfg


def _history(values: list[float], step_min: int = 5, start=NOW):
    return [(start + timedelta(minutes=i * step_min), v) for i, v in enumerate(values)]


def test_min_liq_default_is_20k(tmp_path):
    assert mk_cfg(tmp_path).min_liq == 20_000.0
    assert Config(telegram_bot_token="x").min_liq == 20_000.0


def test_too_little_history_is_unproven_never_locked(tmp_path):
    cfg = mk_cfg(tmp_path)
    v = lock_verdict(_history([100_000.0, 101_000.0]), cfg)
    assert v.known is False
    assert v.locked is False
    assert v.label == "unproven"


def test_stable_liquidity_over_window_is_locked(tmp_path):
    cfg = mk_cfg(tmp_path)
    # 12 samples x 5 min = 55 min of history, gentle drift only
    v = lock_verdict(_history([100_000.0 + 500 * i for i in range(12)]), cfg)
    assert v.known is True
    assert v.locked is True
    assert v.label == "locked"
    assert v.drawdown == 0.0


def test_liquidity_pull_fails_the_lock(tmp_path):
    cfg = mk_cfg(tmp_path)
    values = [100_000.0] * 8 + [60_000.0] + [61_000.0] * 3  # -40% pull
    v = lock_verdict(_history(values), cfg)
    assert v.known is True
    assert v.locked is False
    assert v.label == "pulling"
    assert v.drawdown is not None and 0.39 < v.drawdown < 0.41


def test_drawdown_uses_running_peak_so_refill_cannot_hide_a_pull(tmp_path):
    cfg = mk_cfg(tmp_path)
    values = [100_000.0] * 4 + [50_000.0] * 2 + [120_000.0] * 6  # pulled, then refilled
    v = lock_verdict(_history(values), cfg)
    assert v.locked is False, "an early 50% pull must not be erased by a later refill"
    assert v.drawdown is not None and v.drawdown >= 0.49


def test_stable_but_below_min_liq_is_not_locked(tmp_path):
    cfg = mk_cfg(tmp_path)  # min_liq 20k
    v = lock_verdict(_history([15_000.0] * 12), cfg)
    assert v.known is True
    assert v.locked is False


def test_lock_thresholds_are_configurable(tmp_path):
    strict = mk_cfg(tmp_path, lock_max_drawdown=0.05)
    loose = mk_cfg(tmp_path, lock_max_drawdown=0.50)
    values = [100_000.0] * 8 + [80_000.0] * 4  # -20%
    assert lock_verdict(_history(values), strict).locked is False
    assert lock_verdict(_history(values), loose).locked is True


def test_escalation_gated_by_lock_verdict(tmp_path):
    cfg = mk_cfg(tmp_path)
    pool = Pool.from_api(
        api_item(name="AAPLDOG / AAPL", reserve="118000", vol_h1="600000")
    )
    pulling = lock_verdict(_history([200_000.0] * 8 + [100_000.0] * 4), cfg)
    locked = lock_verdict(_history([118_000.0] * 12), cfg)

    assert escalation_verdict(pool, 100_000.0, None, cfg, NOW, lock=pulling).fire is False
    assert escalation_verdict(pool, 100_000.0, None, cfg, NOW, lock=locked).fire is True
    # opt out of the gate entirely
    off = mk_cfg(tmp_path, require_liq_lock=False)
    assert escalation_verdict(pool, 100_000.0, None, off, NOW, lock=pulling).fire is True


def _run_cycles(app, clock, item_factory, count: int, step_min: int = 5) -> None:
    for i in range(count):
        app.gecko.new_items = [item_factory(i)] if i == 0 else []
        app.gecko.top_items = [item_factory(i)]
        app.run_cycle()
        clock.advance(minutes=step_min)


def test_escalation_waits_for_a_proven_lock_then_fires(tmp_path):
    addr = "0x" + "1a" * 20

    def item(i: int):
        return api_item(
            name="AAPLDOG / AAPL",
            address=addr,
            reserve="118000",
            vol_h1="600000",  # escalation condition true from the start
            created_at=NOW - timedelta(minutes=41),
        )

    gecko = FakeGecko()
    app, telegram, clock = mk_app(tmp_path, gecko)
    # first cycle alerts; early cycles have too little history to prove a lock
    _run_cycles(app, clock, item, 3)
    assert len(telegram.sent) == 1, "NEW alert only - lock still unproven"

    # keep liquidity flat until the lock window is satisfied
    _run_cycles(app, clock, item, 9)
    assert len(telegram.sent) == 2
    assert "ESCALATE" in telegram.sent[1]


def test_escalation_never_fires_while_liquidity_is_pulled(tmp_path):
    addr = "0x" + "2b" * 20
    reserves = ["300000"] * 4 + ["90000"] * 10  # hard pull after the alert

    def item(i: int):
        return api_item(
            name="RUGGY / WETH",
            address=addr,
            reserve=reserves[min(i, len(reserves) - 1)],
            vol_h1="900000",
            created_at=NOW - timedelta(minutes=20),
        )

    gecko = FakeGecko()
    app, telegram, clock = mk_app(tmp_path, gecko)
    _run_cycles(app, clock, item, 14)
    assert len(telegram.sent) == 1, "only the NEW alert; pulled liquidity never escalates"


def test_digest_requires_the_lock(tmp_path):
    from datetime import datetime, timezone

    from conftest import Clock

    start = datetime(2026, 9, 2, 4, 0, tzinfo=timezone.utc)  # 06:00 Zurich, pre-digest
    clock = Clock(start)
    stable = "0x" + "3c" * 20
    pulled = "0x" + "4d" * 20

    def items(i: int):
        drop = "40000" if i >= 4 else "300000"
        return [
            api_item(
                name="STABLE / WETH",
                address=stable,
                reserve="300000",
                vol_h24="900000",
                created_at=start - timedelta(hours=2),
            ),
            api_item(
                name="PULLED / WETH",
                address=pulled,
                reserve=drop,
                vol_h24="5000000",  # loudest volume, must still be excluded
                created_at=start - timedelta(hours=2),
            ),
        ]

    gecko = FakeGecko()
    app, telegram, _ = mk_app(tmp_path, gecko, clock=clock, cfg=mk_cfg(tmp_path))
    for i in range(14):
        batch = items(i)
        gecko.new_items = batch if i == 0 else []
        gecko.top_items = batch
        app.run_cycle()
        clock.advance(minutes=5)
    # now past 07:00 Zurich -> digest fires on the next cycle
    gecko.new_items = []
    gecko.top_items = items(14)
    app.run_cycle()

    digest = [m for m in telegram.sent if "digest" in m]
    assert len(digest) == 1
    assert "STABLE" in digest[0]
    assert "PULLED" not in digest[0]


def test_dashboard_filters_to_locked_pools_with_all_override(tmp_path):
    from rh_meme_watch.dashboard import collect, qualifies, render_html

    addr_ok = "0x" + "5e" * 20
    addr_bad = "0x" + "6f" * 20

    def items(i: int):
        return [
            api_item(
                name="HOLDER / WETH",
                address=addr_ok,
                reserve="250000",
                created_at=NOW - timedelta(minutes=30),
            ),
            api_item(
                name="LEAKER / WETH",
                address=addr_bad,
                reserve="250000" if i < 4 else "50000",
                created_at=NOW - timedelta(minutes=30),
            ),
        ]

    gecko = FakeGecko()
    app, telegram, clock = mk_app(tmp_path, gecko)
    for i in range(14):
        batch = items(i)
        gecko.new_items = batch if i == 0 else []
        gecko.top_items = batch
        app.run_cycle()
        clock.advance(minutes=5)

    now = clock.now
    data = collect(app.cfg.db_path, app.cfg, now)
    by_addr = {p["address"]: p for p in data["pools"]}
    assert by_addr[addr_ok]["liq_lock"] == "locked"
    assert by_addr[addr_bad]["liq_lock"] == "pulling"
    assert qualifies(by_addr[addr_ok], app.cfg) is True
    assert qualifies(by_addr[addr_bad], app.cfg) is False

    filtered = render_html(app.cfg.db_path, app.cfg, now)
    assert "HOLDER" in filtered
    assert "LEAKER" not in filtered
    assert "\U0001f512 locked" in filtered

    unfiltered = render_html(app.cfg.db_path, app.cfg, now, show_all=True)
    assert "HOLDER" in unfiltered and "LEAKER" in unfiltered
    assert "pulling" in unfiltered
