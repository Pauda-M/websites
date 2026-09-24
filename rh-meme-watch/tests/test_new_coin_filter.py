"""New-coin quality filter (R1 gates) and momentum confirmation.

Mirrors the tradeable half of a "viral coin" checklist: skip what is already too
big, priced on air, unattended, or already dumping; then confirm the thing is
still picking up speed. Holder counts and social-view data have no source on
this chain, so unique buyers stands in for "holders rising".
"""

from __future__ import annotations

from datetime import timedelta

from rh_meme_watch.models import Pool
from rh_meme_watch.rules import momentum, quality_verdict

from conftest import NOW, FakeGecko, api_item, mk_app, mk_cfg

GOOD = dict(
    name="MEME / WETH",
    reserve="200000",
    fdv="2000000",          # liq/fdv = 0.10, well above the 0.02 floor
    pct_h1="25.0",
    tx_h1={"buys": 120, "sells": 60, "buyers": 80, "sellers": 40},
)


def _pool(**over) -> Pool:
    return Pool.from_api(api_item(**{**GOOD, **over}))


def _meme_fdv(pool: Pool) -> float | None:
    """Meme is the base token in these fixtures, so the pool FDV is the meme FDV."""
    return pool.fdv_usd


def test_healthy_new_coin_passes(tmp_path):
    v = quality_verdict(_pool(), mk_cfg(tmp_path), _meme_fdv(_pool()))
    assert v.passes is True
    assert v.reason == "ok"


def test_too_big_to_multiply_is_rejected(tmp_path):
    v = quality_verdict(_pool(fdv="50000000"), mk_cfg(tmp_path), _meme_fdv(_pool(fdv="50000000")))
    assert v.passes is False
    assert "fdv" in v.reason


def test_thin_liquidity_against_huge_fdv_is_rejected(tmp_path):
    """The classic rug shape: $50k of liquidity supporting a $20M valuation."""
    v = quality_verdict(_pool(reserve="50000", fdv="4500000"), mk_cfg(tmp_path), _meme_fdv(_pool(reserve="50000", fdv="4500000")))
    assert v.passes is False
    assert "liq/fdv" in v.reason


def test_too_few_unique_buyers_is_rejected(tmp_path):
    v = quality_verdict(
        _pool(tx_h1={"buys": 200, "sells": 10, "buyers": 4, "sellers": 3}),
        mk_cfg(tmp_path),
    )
    assert v.passes is False
    assert "buyers" in v.reason


def test_more_sellers_than_buyers_is_rejected(tmp_path):
    v = quality_verdict(
        _pool(tx_h1={"buys": 40, "sells": 90, "buyers": 30, "sellers": 60}),
        mk_cfg(tmp_path),
    )
    assert v.passes is False
    assert "buy/sell" in v.reason


def test_dead_pool_is_rejected(tmp_path):
    v = quality_verdict(
        _pool(tx_h1={"buys": 20, "sells": 5, "buyers": 26, "sellers": 4}),
        mk_cfg(tmp_path),
    )
    assert v.passes is False
    assert "txns" in v.reason


def test_already_crashed_is_rejected(tmp_path):
    """'Zoom out the chart - already crashed? Skip it.'"""
    v = quality_verdict(_pool(pct_h1="-62.0"), mk_cfg(tmp_path), _meme_fdv(_pool(pct_h1="-62.0")))
    assert v.passes is False
    assert "dumping" in v.reason


def test_every_gate_is_disablable(tmp_path):
    cfg = mk_cfg(
        tmp_path,
        max_fdv=0,
        min_liq_fdv_ratio=0,
        min_buyers_h1=0,
        min_buy_sell_ratio=0,
        min_txns_h1=0,
        min_pct_h1=-1e9,
        min_vol_h1=0,
        min_vol_fdv_ratio=0,
        max_trades_per_buyer=0,
        retrace_h1_pct=0,
        retrace_m15_pct=0,
    )
    awful = _pool(
        fdv="900000000",
        reserve="21000",
        pct_h1="-95.0",
        tx_h1={"buys": 1, "sells": 9, "buyers": 1, "sellers": 9},
    )
    assert quality_verdict(awful, cfg, _meme_fdv(awful)).passes is True


def test_new_alert_is_filtered_and_logged(tmp_path):
    """A pool that clears age+liquidity but fails quality must not alert."""
    junk = api_item(
        name="AIRBALL / WETH",
        address="0x" + "7a" * 20,
        reserve="200000",
        fdv="80000000",  # far over MAX_FDV
        created_at=NOW - timedelta(minutes=41),
    )
    app, telegram, clock = mk_app(tmp_path, FakeGecko(new_items=[junk]))
    app.run_cycle()
    assert telegram.sent == []
    assert app.store.was_alerted("0x" + "7a" * 20) is False


def test_instant_rug_window_is_skipped_then_alerts(tmp_path):
    """Younger than MIN_AGE_MIN: no alert yet, but it is not lost - it alerts later."""
    addr = "0x" + "8b" * 20

    def item(created_min_ago: int):
        return api_item(
            name="FRESH / WETH",
            address=addr,
            reserve="200000",
            fdv="2000000",
            created_at=NOW - timedelta(minutes=created_min_ago),
            tx_h1={"buys": 120, "sells": 60, "buyers": 80, "sellers": 40},
        )

    gecko = FakeGecko(new_items=[item(3)])
    app, telegram, clock = mk_app(tmp_path, gecko)
    app.run_cycle()
    assert telegram.sent == [], "3 minutes old: inside the instant-rug window"

    clock.advance(minutes=12)
    gecko.new_items = [item(15)]
    app.run_cycle()
    assert len(telegram.sent) == 1


def test_momentum_needs_history():
    assert momentum([(100.0, 5)]).known is False
    assert momentum([(100.0, 5)]).label == "unproven"


def test_momentum_accelerating_and_fading():
    rising = [(100.0 * (i + 1), 10 + 3 * i) for i in range(9)]
    m = momentum(rising)
    assert m.known is True and m.vol_rising and m.buyers_rising
    assert m.label == "accelerating"
    assert m.vol_change_pct is not None and m.vol_change_pct > 0
    assert m.buyers_change is not None and m.buyers_change > 0

    falling = [(1000.0 - 100 * i, 50 - 4 * i) for i in range(9)]
    assert momentum(falling).label == "fading"

    mixed = [(100.0 * (i + 1), 40 - 2 * i) for i in range(9)]
    assert momentum(mixed).label == "mixed"


def test_dashboard_shows_momentum_badge(tmp_path):
    from rh_meme_watch.dashboard import collect, render_html

    addr = "0x" + "9c" * 20

    def item(i: int):
        return api_item(
            name="CLIMBER / WETH",
            address=addr,
            reserve="200000",
            fdv="2000000",
            vol_h1=str(50_000 * (i + 1)),
            created_at=NOW - timedelta(minutes=30),
            tx_h1={"buys": 120 + i, "sells": 60, "buyers": 80 + 5 * i, "sellers": 40},
        )

    gecko = FakeGecko()
    app, telegram, clock = mk_app(tmp_path, gecko)
    for i in range(8):
        gecko.new_items = [item(i)] if i == 0 else []
        gecko.top_items = [item(i)]
        app.run_cycle()
        clock.advance(minutes=5)

    pool = collect(app.cfg.db_path, app.cfg, clock.now)["pools"][0]
    assert pool["momentum"] == "accelerating"
    assert pool["vol_change_pct"] > 0

    page = render_html(app.cfg.db_path, app.cfg, clock.now, show_all=True)
    assert "accelerating" in page


def test_stock_as_base_pool_is_not_judged_on_the_stock_fdv(tmp_path):
    """Regression: pool.fdv_usd is the BASE token's.

    On "AMZN / WADDLES" that is Amazon's ~$245B valuation, not the meme's.
    Gating on it rejected every stock-as-base pool - the whole stock-paired meta.
    """
    cfg = mk_cfg(tmp_path)
    pool = _pool(name="AMZN / WADDLES", fdv="245000000000", reserve="241000")

    # the raw pool FDV would fail both FDV gates...
    assert quality_verdict(pool, cfg, pool.fdv_usd).passes is False
    # ...but judged on the meme side's own FDV it passes
    assert quality_verdict(pool, cfg, 1_900_000.0).passes is True
    # unknown meme FDV skips those gates rather than guessing
    assert quality_verdict(pool, cfg, None).passes is True


def test_stock_paired_alert_survives_the_filter_end_to_end(tmp_path):
    """The 📈 meta must still alert: meme FDV comes from the resolver, not the pool."""
    item = api_item(
        name="AMZN / WADDLES",
        address="0x" + "ab" * 20,
        reserve="241000",
        fdv="245000000000",  # AMZN's FDV, on the base side
        created_at=NOW - timedelta(minutes=30),
        tx_h1={"buys": 120, "sells": 60, "buyers": 80, "sellers": 40},
    )
    gecko = FakeGecko(
        new_items=[item],
        search_results={"WADDLES": [api_item(name="WADDLES / USDG", fdv="1900000")]},
    )
    app, telegram, clock = mk_app(tmp_path, gecko)
    app.run_cycle()
    assert len(telegram.sent) == 1
    assert "FDV(meme) $1.9M" in telegram.sent[0].replace("\\", "")
