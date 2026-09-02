"""Parsing of GeckoTerminal pool objects into a typed model.

API quirks handled here:
- reserve_in_usd can be negative (seen on bankr-robinhood pools) -> treated as
  unknown (None), so it can never pass a liquidity floor.
- pool names arrive as "BASE / QUOTE" and sometimes carry a trailing fee tag
  ("MEME / AAPL 0.3%") which is stripped.
- numeric attributes are strings or null; anything unparseable becomes None.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

_FEE_RE = re.compile(r"^\d+(\.\d+)?%$")


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pos_or_none(value: Any) -> float | None:
    n = _num(value)
    if n is None or n <= 0:
        return None
    return n


def _dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def split_pool_name(name: str) -> tuple[str, str]:
    """"AAPLDOG / AAPL 0.3%" -> ("AAPLDOG", "AAPL"). Single-sided names get quote ""."""
    parts = [p.strip() for p in name.split(" / ")]
    if len(parts) == 1:
        return parts[0], ""
    base, quote = parts[0], parts[1]
    tokens = quote.split()
    if len(tokens) > 1 and _FEE_RE.match(tokens[-1]):
        quote = " ".join(tokens[:-1])
    return base, quote


def _rel_id(item: dict, key: str) -> str:
    try:
        return str(item["relationships"][key]["data"]["id"])
    except (KeyError, TypeError):
        return ""


@dataclass
class Pool:
    address: str
    name: str
    base_symbol: str
    quote_symbol: str
    dex: str
    base_token_id: str
    quote_token_id: str
    created_at: datetime | None
    base_token_price_usd: float | None
    fdv_usd: float | None
    market_cap_usd: float | None
    reserve_usd: float | None  # None == unknown (missing, unparseable, or <= 0)
    vol_h1: float | None
    vol_h24: float | None
    price_change_h1: float | None
    price_change_h24: float | None
    buys_h1: int
    sells_h1: int
    buyers_h1: int
    sellers_h1: int
    buys_h24: int
    sells_h24: int
    buyers_h24: int
    sellers_h24: int

    @classmethod
    def from_api(cls, item: dict) -> "Pool":
        attrs = item.get("attributes") or {}
        pool_id = str(item.get("id") or "")
        # Pool ids look like "robinhood_0xabc..."; keep the raw id if unprefixed.
        address = pool_id.split("_", 1)[1] if "_" in pool_id else pool_id
        name = str(attrs.get("name") or "")
        base_symbol, quote_symbol = split_pool_name(name)

        volume = attrs.get("volume_usd") or {}
        pct = attrs.get("price_change_percentage") or {}
        tx = attrs.get("transactions") or {}
        tx_h1 = tx.get("h1") or {}
        tx_h24 = tx.get("h24") or {}

        def _count(bucket: dict, key: str) -> int:
            n = _num(bucket.get(key))
            return int(n) if n is not None and n >= 0 else 0

        return cls(
            address=address.lower(),
            name=name,
            base_symbol=base_symbol,
            quote_symbol=quote_symbol,
            dex=_rel_id(item, "dex"),
            base_token_id=_rel_id(item, "base_token"),
            quote_token_id=_rel_id(item, "quote_token"),
            created_at=_dt(attrs.get("pool_created_at")),
            base_token_price_usd=_num(attrs.get("base_token_price_usd")),
            fdv_usd=_pos_or_none(attrs.get("fdv_usd")),
            market_cap_usd=_pos_or_none(attrs.get("market_cap_usd")),
            reserve_usd=_pos_or_none(attrs.get("reserve_in_usd")),
            vol_h1=_num(volume.get("h1")),
            vol_h24=_num(volume.get("h24")),
            price_change_h1=_num(pct.get("h1")),
            price_change_h24=_num(pct.get("h24")),
            buys_h1=_count(tx_h1, "buys"),
            sells_h1=_count(tx_h1, "sells"),
            buyers_h1=_count(tx_h1, "buyers"),
            sellers_h1=_count(tx_h1, "sellers"),
            buys_h24=_count(tx_h24, "buys"),
            sells_h24=_count(tx_h24, "sells"),
            buyers_h24=_count(tx_h24, "buyers"),
            sellers_h24=_count(tx_h24, "sellers"),
        )

    def age_minutes(self, now: datetime) -> float | None:
        if self.created_at is None:
            return None
        return (now - self.created_at).total_seconds() / 60.0

    @property
    def gecko_url(self) -> str:
        return f"https://www.geckoterminal.com/robinhood/pools/{self.address}"


def parse_pools(payload: dict) -> list[Pool]:
    data = payload.get("data") or []
    pools: list[Pool] = []
    for item in data:
        if isinstance(item, dict):
            pools.append(Pool.from_api(item))
    return pools
