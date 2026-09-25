"""Parsing of GeckoTerminal pool objects into a typed model.

API quirks handled here:
- reserve_in_usd can be negative (seen on bankr-robinhood pools) -> treated as
  unknown (None).
- pool names arrive as "BASE / QUOTE" and sometimes carry a trailing fee tag
  ("MEME / AAPL 0.3%") which is stripped.
- numeric attributes are strings or null; anything unparseable becomes None.
- the Gecko client may attach ``_socials_by_token`` from the pool-info endpoint;
  these values are kept separately for base and quote so the rule engine can
  require a social on the actual meme side rather than on the paired asset.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
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


def token_address(token_id: str) -> str:
    """The address out of a token resource id, however it is spelled.

    GeckoTerminal ids look like "robinhood_0xabc..." in pool relationships. The
    info endpoint's spelling is not guaranteed to match, so comparisons are made
    on the address alone, lowercased.
    """
    text = str(token_id or "").strip().lower()
    return text.rsplit("_", 1)[-1] if "_" in text else text


def _socials(item: dict, token_id: str) -> tuple[str, ...]:
    raw = item.get("_socials_by_token") or {}
    if not isinstance(raw, dict):
        return ()
    values = raw.get(token_id)
    if values is None:  # fall back to address matching, per token_address()
        wanted = token_address(token_id)
        for key, candidate in raw.items():
            if token_address(key) == wanted:
                values = candidate
                break
    if not isinstance(values, (list, tuple)):
        return ()
    return tuple(str(v) for v in values if str(v).strip())


@dataclass
class Pool:
    address: str
    name: str
    base_symbol: str
    quote_symbol: str
    dex: str
    base_token_id: str
    quote_token_id: str
    base_socials: tuple[str, ...]
    quote_socials: tuple[str, ...]
    created_at: datetime | None
    base_token_price_usd: float | None
    quote_token_price_usd: float | None
    fdv_usd: float | None
    market_cap_usd: float | None
    reserve_usd: float | None  # None == unknown (missing, unparseable, or <= 0)
    vol_h1: float | None
    vol_h24: float | None
    price_change_h1: float | None
    price_change_h24: float | None
    # Short window. The API also exposes m5/m30/h6; m15 is kept because it is the
    # shortest window that is not pure noise on a thin new pool, and it is what
    # the retrace check compares the h1 move against. h24 cannot serve there: it
    # is unreliable on a pool minutes old (see the quirk note above).
    vol_m15: float | None
    price_change_m15: float | None
    buys_h1: int
    sells_h1: int
    buyers_h1: int
    sellers_h1: int
    buys_h24: int
    sells_h24: int
    buyers_h24: int
    sellers_h24: int

    def with_socials(self, by_token: dict) -> "Pool":
        """Return a copy carrying socials fetched after construction.

        Matching is on the token ADDRESS, not on the whole resource id. The ids
        come from two different endpoints - the pool's relationships and the
        pool-info payload - and nothing guarantees they are spelled identically.
        An exact-string match that silently misses produces "no socials" for
        every pool, indistinguishable from a chain whose projects register none.
        """
        if not by_token:
            return self
        folded = {token_address(k): tuple(v or ()) for k, v in by_token.items()}
        return replace(
            self,
            base_socials=folded.get(token_address(self.base_token_id), ()),
            quote_socials=folded.get(token_address(self.quote_token_id), ()),
        )

    def sides_matched(self, by_token: dict) -> bool:
        """Did a social payload actually line up with either side of this pool?

        False while ``by_token`` is non-empty means the lookup found tokens but
        matched none of them - a key-format mismatch, not an absence of socials.
        Those two look identical downstream, so they must be told apart here.
        """
        if not by_token:
            return False
        wanted = {token_address(self.base_token_id), token_address(self.quote_token_id)}
        return any(token_address(k) in wanted for k in by_token)

    @classmethod
    def from_api(cls, item: dict) -> "Pool":
        attrs = item.get("attributes") or {}
        pool_id = str(item.get("id") or "")
        # Pool ids look like "robinhood_0xabc..."; keep the raw id if unprefixed.
        address = pool_id.split("_", 1)[1] if "_" in pool_id else pool_id
        name = str(attrs.get("name") or "")
        base_symbol, quote_symbol = split_pool_name(name)
        base_token_id = _rel_id(item, "base_token")
        quote_token_id = _rel_id(item, "quote_token")

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
            base_token_id=base_token_id,
            quote_token_id=quote_token_id,
            base_socials=_socials(item, base_token_id),
            quote_socials=_socials(item, quote_token_id),
            created_at=_dt(attrs.get("pool_created_at")),
            base_token_price_usd=_num(attrs.get("base_token_price_usd")),
            quote_token_price_usd=_num(attrs.get("quote_token_price_usd")),
            fdv_usd=_pos_or_none(attrs.get("fdv_usd")),
            market_cap_usd=_pos_or_none(attrs.get("market_cap_usd")),
            reserve_usd=_pos_or_none(attrs.get("reserve_in_usd")),
            vol_h1=_num(volume.get("h1")),
            vol_h24=_num(volume.get("h24")),
            vol_m15=_num(volume.get("m15")),
            price_change_h1=_num(pct.get("h1")),
            price_change_h24=_num(pct.get("h24")),
            price_change_m15=_num(pct.get("m15")),
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
