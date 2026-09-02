"""SQLite persistence (WAL mode).

Schema:
  pools(address PK, symbol, quote, dex, created_at, first_seen, first_alert_ts,
        first_liq, last_liq, last_vol_h1, escalated_ts, status)
  alerts(id PK, address, kind, ts, payload_json)

All timestamps are ISO-8601 UTC strings. ``symbol`` holds the meme-side symbol
(uppercased) so the per-symbol alert cooldown can be queried.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pools (
    address TEXT PRIMARY KEY,
    symbol TEXT,
    quote TEXT,
    dex TEXT,
    created_at TEXT,
    first_seen TEXT,
    first_alert_ts TEXT,
    first_liq REAL,
    last_liq REAL,
    last_vol_h1 REAL,
    escalated_ts TEXT,
    status TEXT NOT NULL DEFAULT 'seen'
);
CREATE INDEX IF NOT EXISTS idx_pools_symbol ON pools(symbol);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    address TEXT NOT NULL,
    kind TEXT NOT NULL,
    ts TEXT NOT NULL,
    payload_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_kind_ts ON alerts(kind, ts);
"""


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
    except ValueError:
        return None


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(_SCHEMA)

    def close(self) -> None:
        self.db.close()

    # -- pools ---------------------------------------------------------------

    def upsert_seen(
        self,
        address: str,
        symbol: str,
        quote: str,
        dex: str,
        created_at: datetime | None,
        now: datetime,
        reserve: float | None,
        vol_h1: float | None,
    ) -> None:
        self.db.execute(
            """
            INSERT INTO pools (address, symbol, quote, dex, created_at, first_seen,
                               last_liq, last_vol_h1, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'seen')
            ON CONFLICT(address) DO UPDATE SET
                symbol = excluded.symbol,
                quote = excluded.quote,
                dex = excluded.dex,
                last_liq = excluded.last_liq,
                last_vol_h1 = excluded.last_vol_h1
            """,
            (
                address,
                symbol.upper(),
                quote.upper(),
                dex,
                _iso(created_at) if created_at else None,
                _iso(now),
                reserve,
                vol_h1,
            ),
        )

    def get_pool(self, address: str) -> sqlite3.Row | None:
        cur = self.db.execute("SELECT * FROM pools WHERE address = ?", (address,))
        return cur.fetchone()

    def was_alerted(self, address: str) -> bool:
        row = self.get_pool(address)
        return bool(row and row["first_alert_ts"])

    def mark_alerted(self, address: str, ts: datetime, first_liq: float | None) -> None:
        self.db.execute(
            "UPDATE pools SET first_alert_ts = ?, first_liq = ?, status = 'alerted' "
            "WHERE address = ?",
            (_iso(ts), first_liq, address),
        )

    def mark_escalated(self, address: str, ts: datetime) -> None:
        self.db.execute(
            "UPDATE pools SET escalated_ts = ?, status = 'escalated' WHERE address = ?",
            (_iso(ts), address),
        )

    def first_alert_ts(self, address: str) -> datetime | None:
        row = self.get_pool(address)
        return _parse(row["first_alert_ts"]) if row else None

    def escalated_ts(self, address: str) -> datetime | None:
        row = self.get_pool(address)
        return _parse(row["escalated_ts"]) if row else None

    def last_symbol_alert_ts(self, symbol: str) -> datetime | None:
        cur = self.db.execute(
            "SELECT MAX(first_alert_ts) AS ts FROM pools "
            "WHERE symbol = ? AND first_alert_ts IS NOT NULL",
            (symbol.upper(),),
        )
        row = cur.fetchone()
        return _parse(row["ts"]) if row else None

    # -- alerts --------------------------------------------------------------

    def record_alert(self, address: str, kind: str, ts: datetime, payload: dict) -> None:
        self.db.execute(
            "INSERT INTO alerts (address, kind, ts, payload_json) VALUES (?, ?, ?, ?)",
            (address, kind, _iso(ts), json.dumps(payload, default=str)),
        )

    def last_alert_ts(self, kind: str) -> datetime | None:
        cur = self.db.execute(
            "SELECT MAX(ts) AS ts FROM alerts WHERE kind = ?", (kind,)
        )
        row = cur.fetchone()
        return _parse(row["ts"]) if row else None
