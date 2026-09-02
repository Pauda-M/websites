"""Rule engine: classification, R1 NEW, R2 STOCK-PAIRED, R3 ESCALATE, R4 DUMP.

fdv_usd on a pool is the BASE token's FDV. The meme side is whichever token is
not a tokenized stock and not in the non-meme set (WETH/USDG/USDC/USDT/GLD).
When the meme is the quote token, its FDV must be resolved from another pool
where it is the base (see FdvResolver).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from .config import NON_MEME_EXTRA, Config
from .models import Pool, parse_pools

log = logging.getLogger("rh_meme_watch.rules")

# Quote symbols acceptable for resolving a meme token's own FDV.
_FDV_QUOTE_OK = frozenset({"USDG", "WETH", "USDC", "USDT"})


@dataclass(frozen=True)
class Classification:
    is_stock_paired: bool
    stock_symbol: str | None
    meme_symbol: str | None  # None -> no meme side (e.g. AMZN / USDG)
    meme_is_base: bool


def classify(pool: Pool, cfg: Config) -> Classification:
    base = pool.base_symbol.upper()
    quote = pool.quote_symbol.upper()
    stocks = cfg.stock_symbols

    base_is_stock = base in stocks
    quote_is_stock = quote in stocks
    base_excluded = base_is_stock or base in NON_MEME_EXTRA
    quote_excluded = quote_is_stock or quote in NON_MEME_EXTRA or quote == ""

    stock_symbol = None
    if base_is_stock:
        stock_symbol = pool.base_symbol
    elif quote_is_stock:
        stock_symbol = pool.quote_symbol

    if not base_excluded:
        meme_symbol, meme_is_base = pool.base_symbol, True
    elif not quote_excluded:
        meme_symbol, meme_is_base = pool.quote_symbol, False
    else:
        meme_symbol, meme_is_base = None, False

    return Classification(
        is_stock_paired=base_is_stock or quote_is_stock,
        stock_symbol=stock_symbol,
        meme_symbol=meme_symbol,
        meme_is_base=meme_is_base,
    )


def liquidity_floor(cls: Classification, cfg: Config) -> float:
    return cfg.liq_floor_stock if cls.is_stock_paired else cfg.liq_floor


def passes_new_rule(
    pool: Pool, cls: Classification, cfg: Config, now: datetime
) -> bool:
    """R1/R2 gate, without dedupe/cooldown (the caller checks the store)."""
    if cls.meme_symbol is None:
        return False
    age = pool.age_minutes(now)
    if age is None or age < 0 or age > cfg.new_window_min:
        return False
    if pool.reserve_usd is None:  # unknown liquidity (missing or <= 0) never passes
        return False
    return pool.reserve_usd >= liquidity_floor(cls, cfg)


@dataclass(frozen=True)
class EscalationVerdict:
    fire: bool
    reason: str | None  # "liq_x2" or "vol_h1"
    liq_mult: float | None


def escalation_verdict(
    pool: Pool,
    first_liq: float | None,
    escalated_ts: datetime | None,
    cfg: Config,
    now: datetime,
) -> EscalationVerdict:
    """R3: reserve >= 2x first-alert reserve OR vol.h1 >= ESC_VOL_H1,
    at most once per esc_cooldown_h per address."""
    if escalated_ts is not None and now - escalated_ts < timedelta(hours=cfg.esc_cooldown_h):
        return EscalationVerdict(False, None, None)
    liq_mult = None
    if first_liq and first_liq > 0 and pool.reserve_usd is not None:
        liq_mult = pool.reserve_usd / first_liq
    if liq_mult is not None and liq_mult >= 2.0:
        return EscalationVerdict(True, "liq_x2", liq_mult)
    if pool.vol_h1 is not None and pool.vol_h1 >= cfg.esc_vol_h1:
        return EscalationVerdict(True, "vol_h1", liq_mult)
    return EscalationVerdict(False, None, liq_mult)


def dump_warnings(pool: Pool, first_liq: float | None) -> list[str]:
    """R4: informational lines only, embedded in escalations and digests."""
    warnings: list[str] = []
    if pool.sellers_h1 > 0:
        ratio = pool.buyers_h1 / pool.sellers_h1
        if ratio < 0.7:
            warnings.append(f"buyers/sellers h1 {ratio:.2f}")
    if (
        first_liq
        and first_liq > 0
        and pool.reserve_usd is not None
        and pool.reserve_usd < 0.5 * first_liq
    ):
        drop = (1.0 - pool.reserve_usd / first_liq) * 100.0
        warnings.append(f"liq -{drop:.0f}% vs first alert")
    return warnings


def digest_pools(pools: list[Pool], now: datetime, limit: int = 10) -> list[Pool]:
    """Top pools by h24 volume among pools created in the last 24 h."""
    fresh = [
        p
        for p in pools
        if p.created_at is not None and now - p.created_at <= timedelta(hours=24)
    ]
    fresh.sort(key=lambda p: p.vol_h24 or 0.0, reverse=True)
    return fresh[:limit]


class FdvResolver:
    """Resolves a meme token's own FDV when the meme is the quote side.

    Looks for a <meme>/USDG-or-WETH pool via /search/pools (one extra request,
    cached for cfg.fdv_cache_ttl_sec, at most cfg.fdv_lookups_per_cycle
    lookups per cycle). Returns None when unresolvable -> rendered as "n/a".
    """

    def __init__(
        self,
        search_fn: Callable[[str], list[dict]],
        cfg: Config,
        now_fn: Callable[[], datetime],
    ) -> None:
        self._search = search_fn
        self._cfg = cfg
        self._now = now_fn
        self._cache: dict[str, tuple[datetime, float | None]] = {}
        self._lookups_this_cycle = 0

    def new_cycle(self) -> None:
        self._lookups_this_cycle = 0

    def fdv_for(self, pool: Pool, cls: Classification) -> float | None:
        if cls.meme_symbol is None:
            return None
        if cls.meme_is_base:
            return pool.fdv_usd
        symbol = cls.meme_symbol.upper()
        now = self._now()
        cached = self._cache.get(symbol)
        if cached is not None:
            ts, value = cached
            if (now - ts).total_seconds() < self._cfg.fdv_cache_ttl_sec:
                return value
        if self._lookups_this_cycle >= self._cfg.fdv_lookups_per_cycle:
            return None
        self._lookups_this_cycle += 1
        value: float | None = None
        try:
            candidates = parse_pools({"data": self._search(symbol)})
        except Exception as exc:  # a failed lookup must never break alerting
            log.warning("FDV search for %s failed: %r", symbol, exc)
            candidates = []
        for cand in candidates:
            if (
                cand.base_symbol.upper() == symbol
                and cand.quote_symbol.upper() in _FDV_QUOTE_OK
                and cand.fdv_usd is not None
            ):
                value = cand.fdv_usd
                break
        self._cache[symbol] = (now, value)
        return value
