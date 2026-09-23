"""The premium skin is what actually serves the page, so it needs its own cover.

``dashboard_ui.start_dashboard`` swaps ``dashboard.render_html`` at import-time of
the server, so a fault here is visible on the live page even though the legacy
renderer's tests stay green.
"""

from __future__ import annotations

from datetime import timedelta

import httpx

from rh_meme_watch import dashboard as legacy
from rh_meme_watch import dashboard_ui
from rh_meme_watch.store import Store

from conftest import NOW, mk_cfg


def _seed(tmp_path, symbol="AAPLDOG", **cfg_kw):
    cfg = mk_cfg(tmp_path, **cfg_kw)
    store = Store(cfg.db_path)
    addr = "0x" + "ab" * 20
    store.upsert_seen(addr, symbol, "AAPL", "uniswap-v2", NOW, NOW, 120_000.0, 90_000.0)
    store.mark_alerted(addr, NOW, 120_000.0)
    for i in range(1, 4):
        store.record_snapshot(
            addr,
            NOW + timedelta(minutes=i),
            120_000.0 + i * 20_000,
            90_000.0 + i * 30_000,
            80,
            30,
            70,
            25,
            12.0,
        )
    return cfg, store, addr


def test_renders_the_radar_page(tmp_path):
    cfg, _, _ = _seed(tmp_path)
    page = dashboard_ui.render_html(cfg.db_path, cfg, NOW + timedelta(minutes=5), True)
    assert "<!doctype html>" in page
    assert "AAPLDOG" in page
    assert "Top opportunities" in page
    assert dashboard_ui.FOMO_URL in page
    assert "<polyline" in page, "sparkline drawn"


def test_escapes_hostile_symbols(tmp_path):
    cfg = mk_cfg(tmp_path)
    store = Store(cfg.db_path)
    addr = "0x" + "cd" * 20
    store.upsert_seen(
        addr, "<script>alert(1)</script>", "WETH", "uniswap-v4", NOW, NOW, 200_000.0, 1.0
    )
    store.mark_alerted(addr, NOW, 200_000.0)
    page = dashboard_ui.render_html(cfg.db_path, cfg, NOW, True)
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page.lower(), "escaped, not raw"
    assert "&l<" not in page, "entity must not be sliced in half"


def test_risk_badges_cover_every_signal():
    badges = dashboard_ui._risk_badges(
        {
            "status": "escalated",
            "liq_lock": "pulling",
            "custody": "single custodian",
            "momentum": "fading",
            "dump_flag": True,
        }
    )
    for label in ("ESCALATED", "LIQ PULL", "1 CUSTODIAN", "FADING", "RUG RISK"):
        assert label in badges

    good = dashboard_ui._risk_badges(
        {
            "status": "alerted",
            "liq_lock": "locked",
            "custody": "burned",
            "momentum": "accelerating",
            "vol_change_pct": 140.0,
            "dump_flag": False,
        }
    )
    for label in ("TRACKING", "LIQ HELD", "LP BURNED", "ACCELERATING +140%"):
        assert label in good
    assert "RUG RISK" not in good


def test_filtered_view_hides_pools_that_fail_the_gates(tmp_path):
    """Default view shows only locked liquidity at or above MIN_LIQ."""
    cfg, _, _ = _seed(tmp_path, min_liq=20_000.0)
    now = NOW + timedelta(minutes=5)
    filtered = dashboard_ui.render_html(cfg.db_path, cfg, now, show_all=False)
    everything = dashboard_ui.render_html(cfg.db_path, cfg, now, show_all=True)
    assert "AAPLDOG" in everything
    # too young to prove a lock -> unproven -> excluded from the filtered radar
    assert "No qualifying pools" in filtered


def test_start_dashboard_installs_the_skin_and_serves(tmp_path):
    cfg, _, _ = _seed(tmp_path)
    original = legacy.render_html
    server = dashboard_ui.start_dashboard(cfg, port=0)
    try:
        assert legacy.render_html is dashboard_ui.render_html
        port = server.server_address[1]
        with httpx.Client(trust_env=False, timeout=5.0) as client:
            base = f"http://127.0.0.1:{port}"
            page = client.get(f"{base}/?all=1")
            assert page.status_code == 200
            assert "Top opportunities" in page.text
            assert client.get(f"{base}/healthz").status_code in (200, 503)
            assert client.get(f"{base}/api/pools").json()["pools"]
    finally:
        server.shutdown()
        server.server_close()
        legacy.render_html = original
