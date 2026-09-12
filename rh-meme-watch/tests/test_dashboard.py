"""Dashboard: heat score, snapshot recording, HTML rendering, HTTP endpoints."""

from __future__ import annotations

from datetime import timedelta

import httpx

from rh_meme_watch.dashboard import collect, heat_score, render_html, start_dashboard
from rh_meme_watch.store import Store

from conftest import NOW, FakeGecko, api_item, mk_app, mk_cfg


def test_heat_score_bounds_and_monotonicity():
    assert heat_score(None, None, None, None, 500_000) == 0 + round(100 * 0.30 * 0.2)
    assert heat_score(0, 0, 0, 0.5, 500_000) == 0
    full = heat_score(500_000, 200, 100, 3.0, 500_000)
    assert full == 100
    assert heat_score(10_000_000, 999, 1, 99.0, 500_000) == 100  # capped
    low_vol = heat_score(50_000, 100, 100, 1.0, 500_000)
    high_vol = heat_score(400_000, 100, 100, 1.0, 500_000)
    assert high_vol > low_vol


def test_cycle_snapshots_only_alerted_pools(tmp_path):
    alerted = api_item(
        name="AAPLDOG / AAPL",
        address="0x" + "aa" * 20,
        reserve="118000",
        created_at=NOW - timedelta(minutes=41),
    )
    ignored = api_item(
        name="TINY / WETH",
        address="0x" + "bb" * 20,
        reserve="5000",  # below every floor -> never alerts
        created_at=NOW - timedelta(minutes=10),
    )
    gecko = FakeGecko(new_items=[alerted, ignored])
    app, telegram, clock = mk_app(tmp_path, gecko)
    app.run_cycle()
    clock.advance(minutes=1)
    app.run_cycle()

    since = NOW - timedelta(hours=1)
    assert len(app.store.snapshots("0x" + "aa" * 20, since)) == 2
    assert app.store.snapshots("0x" + "bb" * 20, since) == []


def test_prune_snapshots(tmp_path):
    store = Store(tmp_path / "s.db")
    store.record_snapshot("0x1", NOW - timedelta(days=20), 1.0, 1.0, 1, 1, 1, 1, 0.0)
    store.record_snapshot("0x1", NOW, 2.0, 2.0, 2, 2, 2, 2, 0.0)
    store.prune_snapshots(NOW - timedelta(days=14))
    rows = store.snapshots("0x1", NOW - timedelta(days=30))
    assert len(rows) == 1
    assert rows[0]["reserve"] == 2.0


def _seeded_cfg_store(tmp_path):
    cfg = mk_cfg(tmp_path)
    store = Store(cfg.db_path)
    addr = "0x" + "cc" * 20
    store.upsert_seen(addr, "AAPLDOG", "AAPL", "uniswap-v4", NOW, NOW, 118000.0, 212000.0)
    store.mark_alerted(addr, NOW, 118000.0)
    store.record_alert(addr, "new_stock", NOW, {})
    for i in range(3):
        store.record_snapshot(
            addr, NOW + timedelta(minutes=i), 118000.0 + 1000 * i, 212000.0,
            1204, 980, 301, 288, 311.0,
        )
    return cfg, store, addr


def test_collect_and_render(tmp_path):
    cfg, store, addr = _seeded_cfg_store(tmp_path)
    now = NOW + timedelta(minutes=5)
    data = collect(cfg.db_path, cfg, now)
    assert data["alerts_24h"] == 1
    assert len(data["pools"]) == 1
    pool = data["pools"][0]
    assert pool["address"] == addr
    assert 0 <= pool["heat"] <= 100
    assert len(pool["spark"]) == 3

    page = render_html(cfg.db_path, cfg, now, show_all=True)
    assert "AAPLDOG / AAPL" in page
    assert "tracking" in page
    assert "<polyline" in page


def test_render_escapes_hostile_symbols(tmp_path):
    cfg = mk_cfg(tmp_path)
    store = Store(cfg.db_path)
    addr = "0x" + "dd" * 20
    store.upsert_seen(addr, '<script>alert(1)</script>', "WETH", "uniswap-v4", NOW, NOW, 200000.0, 1.0)
    store.mark_alerted(addr, NOW, 200000.0)
    page = render_html(cfg.db_path, cfg, NOW, show_all=True)
    assert "<script" not in page.lower()
    assert "&lt;script&gt;" in page.lower()


def test_http_endpoints(tmp_path):
    cfg, store, addr = _seeded_cfg_store(tmp_path)
    server = start_dashboard(cfg, port=0)
    port = server.server_address[1]
    try:
        with httpx.Client(trust_env=False, timeout=5.0) as client:
            base = f"http://127.0.0.1:{port}"
            page = client.get(f"{base}/?all=1")
            assert page.status_code == 200
            assert "AAPLDOG" in page.text

            api = client.get(f"{base}/api/pools")
            assert api.status_code == 200
            assert api.json()["pools"][0]["address"] == addr

            health = client.get(f"{base}/healthz")
            assert health.status_code == 503  # no heartbeat written yet

            cfg.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            cfg.heartbeat_path.write_text("x")
            health = client.get(f"{base}/healthz")
            assert health.status_code == 200

            assert client.get(f"{base}/nope").status_code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_thermal_color_endpoints_and_direction():
    from rh_meme_watch.dashboard import thermal_color

    assert thermal_color(0) == "#3987e5"    # cold = blue
    assert thermal_color(100) == "#e34948"  # burning = red
    assert thermal_color(50) == "#8a8984"   # neutral midpoint
    assert thermal_color(-5) == thermal_color(0)
    assert thermal_color(999) == thermal_color(100)
    # red channel rises monotonically with heat
    reds = [int(thermal_color(h)[1:3], 16) for h in (0, 25, 50, 75, 100)]
    assert reds == sorted(reds)


def test_rug_risk_bomb_badge(tmp_path):
    from datetime import timedelta as _td

    cfg = mk_cfg(tmp_path)
    store = Store(cfg.db_path)
    addr = "0x" + "ee" * 20
    store.upsert_seen(addr, "RUGGY", "WETH", "uniswap-v4", NOW, NOW, 200000.0, 5000.0)
    store.mark_alerted(addr, NOW, 200000.0)
    # latest snapshot: buyers/sellers 0.5 and liquidity down 60% vs first alert
    store.record_snapshot(addr, NOW + _td(minutes=5), 80000.0, 5000.0, 10, 20, 10, 20, -40.0)
    page = render_html(cfg.db_path, cfg, NOW + _td(minutes=6), show_all=True)
    assert "RUGGY" in page
    assert page.count("\U0001f4a3") >= 2  # legend + the flagged row


def test_burning_pool_gets_fire_and_red_bar(tmp_path):
    from datetime import timedelta as _td

    cfg = mk_cfg(tmp_path)
    store = Store(cfg.db_path)
    addr = "0x" + "ff" * 20
    store.upsert_seen(addr, "MOON", "AAPL", "uniswap-v4", NOW, NOW, 100000.0, 500000.0)
    store.mark_alerted(addr, NOW, 100000.0)
    # huge volume, strong buy flow, 3x liquidity -> heat 100
    store.record_snapshot(addr, NOW + _td(minutes=5), 300000.0, 600000.0, 400, 100, 400, 100, 50.0)
    page = render_html(cfg.db_path, cfg, NOW + _td(minutes=6), show_all=True)
    assert "\U0001f525" in page
    assert "background:#e34948" in page
