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


def test_social_chips_render_one_link_per_platform():
    chips = dashboard_ui._social_links(
        {"socials": ["https://x.com/proj", "https://t.me/projchat"]}
    )
    assert 'href="https://x.com/proj"' in chips
    assert 'href="https://t.me/projchat"' in chips
    assert "TG" in chips
    assert chips.count("<a class=\"social\"") == 2
    assert 'rel="noopener noreferrer nofollow"' in chips


def test_card_for_a_pool_checked_and_found_bare_says_so_loudly():
    """Only after an actual lookup. Before one, see the SOCIAL ? case below."""
    chips = dashboard_ui._social_links({"socials": [], "socials_checked": True})
    assert "NO SOCIAL" in chips
    assert "<a " not in chips


def test_hostile_schemes_are_never_rendered_as_links():
    """Social URLs come from a third party; a javascript: href is an injection."""
    chips = dashboard_ui._social_links(
        {
            "socials": [
                "javascript:alert(1)",
                "data:text/html,<script>alert(1)</script>",
                "https://t.me/good",
            ]
        }
    )
    assert "javascript:" not in chips
    assert "data:text/html" not in chips
    assert 'href="https://t.me/good"' in chips
    assert chips.count("<a class=\"social\"") == 1


def test_social_url_is_escaped_in_the_href():
    chips = dashboard_ui._social_links({"socials": ['https://x.com/a"><script>x()']})
    assert "<script>" not in chips
    assert "&quot;" in chips or "&gt;" in chips


def test_links_appear_on_the_rendered_card(tmp_path):
    from rh_meme_watch.store import Store

    cfg = mk_cfg(tmp_path)
    store = Store(cfg.db_path)
    addr = "0x" + "5e" * 20
    store.upsert_seen(
        addr, "SOCIALCOIN", "WETH", "uniswap-v2", NOW, NOW, 120_000.0, 90_000.0,
        socials=["https://t.me/socialchat"],
    )
    store.mark_alerted(addr, NOW, 120_000.0)
    page = dashboard_ui.render_html(cfg.db_path, cfg, NOW + timedelta(minutes=5), True)
    assert "SOCIALCOIN" in page
    assert "https://t.me/socialchat" in page


def test_coin_without_socials_is_skipped_from_the_filtered_view(tmp_path):
    """No social, no fact-check, no place on the radar."""
    from rh_meme_watch.dashboard import collect, qualifies
    from rh_meme_watch.store import Store

    cfg = mk_cfg(tmp_path, require_socials=True)
    store = Store(cfg.db_path)
    for addr, symbol, links in (
        ("0x" + "a1" * 20, "HASSOCIAL", ["https://t.me/c"]),
        ("0x" + "b2" * 20, "NOSOCIAL", None),
    ):
        store.upsert_seen(
            addr, symbol, "WETH", "uniswap-v2", NOW, NOW, 500_000.0, 90_000.0,
            socials=links,
        )
        store.mark_alerted(addr, NOW, 500_000.0)

    data = collect(cfg.db_path, cfg, NOW + timedelta(minutes=5))
    by_symbol = {p["symbol"]: p for p in data["pools"]}
    assert not qualifies(by_symbol["NOSOCIAL"], cfg), "no social -> skipped"
    assert by_symbol["HASSOCIAL"]["socials"] == ["https://t.me/c"]


def test_mcap_block_shows_detection_baseline_now_and_multiple():
    block = dashboard_ui._mcap_block(
        {"first_mcap": 500_000.0, "last_mcap": 1_750_000.0, "mcap_mult": 3.5}
    )
    assert "MCAP AT ALERT" in block
    assert "3.50x" in block
    assert "positive" in block


def test_mcap_block_marks_a_pool_that_shrank():
    block = dashboard_ui._mcap_block(
        {"first_mcap": 2_000_000.0, "last_mcap": 400_000.0, "mcap_mult": 0.2}
    )
    assert "0.20x" in block
    assert "negative" in block


def test_mcap_block_survives_a_pool_with_no_readings():
    block = dashboard_ui._mcap_block({})
    assert "MCAP AT ALERT" in block
    assert "—" in block, "em dash, not a crash or a fake zero"


def test_mcap_since_detection_appears_on_the_rendered_page(tmp_path):
    from rh_meme_watch.store import Store

    cfg = mk_cfg(tmp_path)
    store = Store(cfg.db_path)
    addr = "0x" + "9c" * 20
    store.upsert_seen(
        addr, "RUNNER", "WETH", "uniswap-v2", NOW, NOW, 200_000.0, 50_000.0,
        socials=["https://t.me/runner"], mcap=3_000_000.0,
    )
    store.mark_alerted(addr, NOW, 200_000.0, first_mcap=600_000.0)
    page = dashboard_ui.render_html(cfg.db_path, cfg, NOW + timedelta(minutes=5), True)
    assert "RUNNER" in page
    assert "MCAP AT ALERT" in page
    assert "5.00x" in page, "3.0M now vs 600k at alert"


def test_table_header_and_body_column_counts_agree(tmp_path):
    """A stray <th> without its <td> silently shears the whole table."""
    from rh_meme_watch.store import Store

    cfg = mk_cfg(tmp_path)
    store = Store(cfg.db_path)
    addr = "0x" + "7d" * 20
    store.upsert_seen(
        addr, "COLS", "WETH", "uniswap-v2", NOW, NOW, 200_000.0, 10_000.0,
        socials=["https://t.me/c"], mcap=1_000_000.0,
    )
    store.mark_alerted(addr, NOW, 200_000.0, first_mcap=500_000.0)
    page = dashboard_ui.render_html(cfg.db_path, cfg, NOW + timedelta(minutes=5), True)

    header = page.split("<thead>")[1].split("</thead>")[0]
    body_row = page.split("<tbody>")[1].split("</tr>")[0]
    assert header.count("<th>") == body_row.count("<td"), "header/body column mismatch"


def test_a_pool_nobody_checked_does_not_claim_to_have_no_social():
    """Both states stored NULL, so the board read NO SOCIAL on pools it had
    never examined - a finding the system did not have."""
    unchecked = dashboard_ui._social_links({"socials": [], "socials_checked": False})
    assert "SOCIAL ?" in unchecked
    assert "NO SOCIAL" not in unchecked

    checked = dashboard_ui._social_links({"socials": [], "socials_checked": True})
    assert "NO SOCIAL" in checked
    assert "SOCIAL ?" not in checked


def test_a_pool_with_socials_shows_links_regardless_of_the_flag():
    chips = dashboard_ui._social_links(
        {"socials": ["https://t.me/c"], "socials_checked": True}
    )
    assert 'href="https://t.me/c"' in chips
    assert "NO SOCIAL" not in chips and "SOCIAL ?" not in chips
