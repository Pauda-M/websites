"""SQLite store: WAL mode, schema, cooldown queries, persistence across reopen."""

from __future__ import annotations

from datetime import timedelta

from rh_meme_watch.store import Store

from conftest import NOW


def test_wal_mode_and_schema(tmp_path):
    store = Store(tmp_path / "state.db")
    mode = store.db.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"

    pool_cols = {r["name"] for r in store.db.execute("PRAGMA table_info(pools)")}
    assert pool_cols == {
        "address", "symbol", "quote", "dex", "created_at", "first_seen",
        "first_alert_ts", "first_liq", "last_liq", "last_vol_h1",
        "escalated_ts", "status",
    }
    alert_cols = {r["name"] for r in store.db.execute("PRAGMA table_info(alerts)")}
    assert alert_cols == {"id", "address", "kind", "ts", "payload_json"}


def test_alert_state_survives_reopen(tmp_path):
    path = tmp_path / "state.db"
    store = Store(path)
    store.upsert_seen("0xabc", "CLIPPY", "MSFT", "uniswap-v4", NOW, NOW, 190000.0, 5000.0)
    store.mark_alerted("0xabc", NOW, 190000.0)
    store.record_alert("0xabc", "new_stock", NOW, {"name": "CLIPPY / MSFT"})
    store.close()

    reopened = Store(path)
    assert reopened.was_alerted("0xabc")
    row = reopened.get_pool("0xabc")
    assert row["first_liq"] == 190000.0
    assert row["status"] == "alerted"
    assert reopened.last_symbol_alert_ts("clippy") is not None


def test_upsert_updates_last_values_but_keeps_first_alert(tmp_path):
    store = Store(tmp_path / "state.db")
    store.upsert_seen("0xabc", "PEPE", "WETH", "uniswap-v4", NOW, NOW, 100000.0, 1000.0)
    store.mark_alerted("0xabc", NOW, 100000.0)

    later = NOW + timedelta(minutes=5)
    store.upsert_seen("0xabc", "PEPE", "WETH", "uniswap-v4", NOW, later, 250000.0, 9000.0)
    row = store.get_pool("0xabc")
    assert row["last_liq"] == 250000.0
    assert row["first_liq"] == 100000.0
    assert row["first_alert_ts"] is not None


def test_symbol_cooldown_query_scopes_by_symbol(tmp_path):
    store = Store(tmp_path / "state.db")
    store.upsert_seen("0x1", "CLIPPY", "MSFT", "uniswap-v4", NOW, NOW, 190000.0, None)
    store.mark_alerted("0x1", NOW, 190000.0)
    store.upsert_seen("0x2", "PEPE", "WETH", "uniswap-v4", NOW, NOW, 200000.0, None)

    assert store.last_symbol_alert_ts("CLIPPY") == NOW
    assert store.last_symbol_alert_ts("PEPE") is None
    assert store.last_symbol_alert_ts("NOPE") is None


def test_last_alert_ts_by_kind(tmp_path):
    store = Store(tmp_path / "state.db")
    assert store.last_alert_ts("digest") is None
    store.record_alert("", "digest", NOW, {})
    assert store.last_alert_ts("digest") == NOW
