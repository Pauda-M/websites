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
from typing import Sequence

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
    status TEXT NOT NULL DEFAULT 'seen',
    socials TEXT
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
CREATE TABLE IF NOT EXISTS onchain (
    address TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    kind TEXT,
    total_supply TEXT,
    holder TEXT,
    holder_units TEXT,
    holder_pct REAL,
    burned_pct REAL,
    reserve_usd REAL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS snapshots (
    address TEXT NOT NULL,
    ts TEXT NOT NULL,
    reserve REAL,
    vol_h1 REAL,
    buys INTEGER,
    sells INTEGER,
    buyers INTEGER,
    sellers INTEGER,
    pct_h1 REAL,
    PRIMARY KEY (address, ts)
);
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
        self._migrate()

    def _migrate(self) -> None:
        """Additive column migrations for databases created by older versions.

        CREATE TABLE IF NOT EXISTS leaves an existing table alone, so a column
        added to _SCHEMA never reaches a database that already exists - which in
        production is the only one that matters.
        """
        have = {row["name"] for row in self.db.execute("PRAGMA table_info(pools)")}
        for column, ddl in (("socials", "TEXT"),):
            if column not in have:
                self.db.execute(f"ALTER TABLE pools ADD COLUMN {column} {ddl}")

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
        socials: Sequence[str] | None = None,
    ) -> None:
        # An empty list means "not enriched this cycle", not "socials removed":
        # the per-cycle lookup budget routinely leaves a pool unenriched. Only a
        # non-empty list overwrites what is stored, so a known-good list is never
        # clobbered by a budget miss.
        socials_json = json.dumps(list(socials)) if socials else None
        self.db.execute(
            """
            INSERT INTO pools (address, symbol, quote, dex, created_at, first_seen,
                               last_liq, last_vol_h1, status, socials)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'seen', ?)
            ON CONFLICT(address) DO UPDATE SET
                symbol = excluded.symbol,
                quote = excluded.quote,
                dex = excluded.dex,
                last_liq = excluded.last_liq,
                last_vol_h1 = excluded.last_vol_h1,
                socials = COALESCE(excluded.socials, pools.socials)
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
                socials_json,
            ),
        )

    @staticmethod
    def socials_of(row) -> tuple[str, ...]:
        """Decode a stored socials list, tolerating nulls and legacy rows."""
        try:
            raw = row["socials"]
        except (IndexError, KeyError):
            return ()
        if not raw:
            return ()
        try:
            values = json.loads(raw)
        except (TypeError, ValueError):
            return ()
        if not isinstance(values, list):
            return ()
        return tuple(str(v) for v in values if str(v).strip())

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

    # -- snapshots (per-cycle history for alerted pools, feeds the dashboard) --

    def record_snapshot(
        self,
        address: str,
        ts: datetime,
        reserve: float | None,
        vol_h1: float | None,
        buys: int,
        sells: int,
        buyers: int,
        sellers: int,
        pct_h1: float | None,
    ) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO snapshots "
            "(address, ts, reserve, vol_h1, buys, sells, buyers, sellers, pct_h1) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (address, _iso(ts), reserve, vol_h1, buys, sells, buyers, sellers, pct_h1),
        )

    def snapshots(self, address: str, since: datetime) -> list[sqlite3.Row]:
        cur = self.db.execute(
            "SELECT * FROM snapshots WHERE address = ? AND ts >= ? ORDER BY ts",
            (address, _iso(since)),
        )
        return cur.fetchall()

    def prune_snapshots(self, cutoff: datetime) -> None:
        self.db.execute("DELETE FROM snapshots WHERE ts < ?", (_iso(cutoff),))

    # -- on-chain verification cache -----------------------------------------

    def get_onchain(self, address: str) -> sqlite3.Row | None:
        cur = self.db.execute("SELECT * FROM onchain WHERE address = ?", (address,))
        return cur.fetchone()

    def upsert_onchain(
        self,
        address: str,
        ts: datetime,
        kind: str,
        total_supply: int | None,
        holder: str | None,
        holder_units: int | None,
        holder_pct: float | None,
        burned_pct: float | None,
        reserve_usd: float | None,
        note: str,
    ) -> None:
        self.db.execute(
            "INSERT INTO onchain (address, ts, kind, total_supply, holder, holder_units, "
            "holder_pct, burned_pct, reserve_usd, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(address) DO UPDATE SET ts=excluded.ts, kind=excluded.kind, "
            "total_supply=excluded.total_supply, holder=excluded.holder, "
            "holder_units=excluded.holder_units, holder_pct=excluded.holder_pct, "
            "burned_pct=excluded.burned_pct, reserve_usd=excluded.reserve_usd, "
            "note=excluded.note",
            (
                address,
                _iso(ts),
                kind,
                str(total_supply) if total_supply is not None else None,
                holder,
                str(holder_units) if holder_units is not None else None,
                holder_pct,
                burned_pct,
                reserve_usd,
                note,
            ),
        )

    def onchain_due(self, cutoff: datetime, limit: int) -> list[sqlite3.Row]:
        """Alerted pools whose on-chain check is missing or older than cutoff.

        Driven from the store rather than the current API response: a pool that
        has dropped out of the API's windows is exactly when its LP is most
        likely to be pulled, and custody is a pure chain read that needs no API.
        """
        cur = self.db.execute(
            "SELECT p.address, p.symbol, p.quote, p.dex, p.last_liq, p.last_vol_h1, "
            "       o.ts AS checked_ts "
            "FROM pools p LEFT JOIN onchain o ON o.address = p.address "
            "WHERE p.first_alert_ts IS NOT NULL "
            "  AND (o.ts IS NULL OR o.ts < ?) "
            # never-checked pools first, newest alert first within each group:
            # the newest alerts are the live meta (and what the dashboard shows),
            # while the oldest alerted pools are long-dead dust.
            "ORDER BY (o.ts IS NOT NULL), p.first_alert_ts DESC LIMIT ?",
            (_iso(cutoff), limit),
        )
        return cur.fetchall()

    def onchain_checked_at(self, address: str) -> datetime | None:
        row = self.get_onchain(address)
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
