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
from typing import TYPE_CHECKING, Callable, Mapping, Sequence

from .config import NON_MEME_EXTRA, Config
from .models import Pool, parse_pools

if TYPE_CHECKING:  # avoids a runtime import purely for an annotation
    from .socials import LinkCheck

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
    """Minimum reserve a NEW pool must hold, relaxed for stock-paired pools."""
    return cfg.liq_floor_stock if cls.is_stock_paired else cfg.liq_floor


def meme_mcap(pool: Pool, cls: Classification) -> float | None:
    """The MEME side's market cap, or None when it cannot be read safely.

    ``market_cap_usd`` and ``fdv_usd`` both describe the BASE token. When the
    meme is the quote side ("AMZN / WADDLES") they are the tokenized stock's
    valuation, so returning them would put Amazon's market cap on a meme card.
    In that case this returns None and the caller keeps the last known value
    rather than writing a wrong one.

    FDV is used rather than ``market_cap_usd`` - which is frequently null here -
    because the detection baseline is resolved through ``FdvResolver``. Baseline
    and current must be the same metric or the multiple between them is
    meaningless.
    """
    if cls.meme_symbol is None or not cls.meme_is_base:
        return None
    return pool.fdv_usd


def meme_socials(pool: Pool, cls: Classification) -> tuple[str, ...]:
    """Social profiles belonging to the actual meme side of the pool."""
    if cls.meme_symbol is None:
        return ()
    return pool.base_socials if cls.meme_is_base else pool.quote_socials


def passes_pre_social_gates(
    pool: Pool, cls: Classification, cfg: Config, now: datetime
) -> bool:
    """Everything a NEW pool must clear that costs nothing to evaluate.

    Age window, instant-rug window and liquidity floor are all read straight off
    the discovery response. Socials are checked separately and afterwards,
    because establishing them costs a request and the budget for those is far
    smaller than the candidate stream - so it must only be spent on pools that
    have already cleared every free check.
    """
    if cls.meme_symbol is None:
        return False
    age = pool.age_minutes(now)
    if age is None or age < 0 or age > cfg.new_window_min:
        return False
    if age < cfg.min_age_min:  # the instant-rug window
        return False
    if pool.reserve_usd is None:  # unknown liquidity (missing or <= 0) never passes
        return False
    return pool.reserve_usd >= liquidity_floor(cls, cfg)


def passes_new_rule(
    pool: Pool, cls: Classification, cfg: Config, now: datetime
) -> bool:
    """Full R1/R2 gate, for callers holding a pool whose socials are already known.

    Socials and liquidity are deliberately AND-ed rather than traded off - a
    well-funded anonymous launch and a loud empty one are each rejected. Missing
    social metadata fails closed.
    """
    if not passes_pre_social_gates(pool, cls, cfg, now):
        return False
    if not cfg.require_socials:  # operational escape hatch if the info API breaks
        return True
    return bool(meme_socials(pool, cls))


@dataclass(frozen=True)
class QualityVerdict:
    """Why a new pool was, or was not, worth an alert.

    These are single-pool checks, so they can run on a pool minutes old - unlike
    the momentum and liquidity-lock checks, which need recorded history.
    """

    passes: bool
    failed: tuple[str, ...] = ()

    @property
    def reason(self) -> str:
        return ", ".join(self.failed) if self.failed else "ok"


def quality_verdict(
    pool: Pool, cfg: Config, meme_fdv: float | None = None
) -> QualityVerdict:
    """New-coin quality gate: size sanity, real participation, not already dumping.

    ``meme_fdv`` must be the MEME side's FDV. ``pool.fdv_usd`` is the BASE
    token's, so on a stock-as-base pool ("AMZN / WADDLES") it is the tokenized
    stock's multi-billion valuation - gating on that would reject every
    stock-paired pool. When the meme FDV is unknown the two FDV-based gates are
    skipped rather than guessed at.
    """
    failed: list[str] = []

    if cfg.max_fdv > 0 and meme_fdv is not None and meme_fdv > cfg.max_fdv:
        failed.append(f"fdv {meme_fdv:,.0f} > {cfg.max_fdv:,.0f}")

    if cfg.min_liq_fdv_ratio > 0 and meme_fdv and pool.reserve_usd is not None:
        ratio = pool.reserve_usd / meme_fdv
        if ratio < cfg.min_liq_fdv_ratio:
            failed.append(f"liq/fdv {ratio:.3f} < {cfg.min_liq_fdv_ratio}")

    if cfg.min_buyers_h1 > 0 and pool.buyers_h1 < cfg.min_buyers_h1:
        failed.append(f"buyers {pool.buyers_h1} < {cfg.min_buyers_h1}")

    if cfg.min_buy_sell_ratio > 0:
        ratio = pool.buys_h1 / pool.sells_h1 if pool.sells_h1 else float(pool.buys_h1 > 0)
        if pool.sells_h1 and ratio < cfg.min_buy_sell_ratio:
            failed.append(f"buy/sell {ratio:.2f} < {cfg.min_buy_sell_ratio}")

    if cfg.min_txns_h1 > 0 and (pool.buys_h1 + pool.sells_h1) < cfg.min_txns_h1:
        failed.append(f"txns {pool.buys_h1 + pool.sells_h1} < {cfg.min_txns_h1}")

    if (
        cfg.min_pct_h1 is not None
        and pool.price_change_h1 is not None
        and pool.price_change_h1 < cfg.min_pct_h1
    ):
        failed.append(f"dumping {pool.price_change_h1:.0f}% < {cfg.min_pct_h1:.0f}%")

    if cfg.min_vol_h1 > 0 and (pool.vol_h1 or 0.0) < cfg.min_vol_h1:
        failed.append(f"vol/h1 {pool.vol_h1 or 0:,.0f} < {cfg.min_vol_h1:,.0f}")

    # Turnover against valuation. A token's price is whatever the deployer says;
    # trading it costs fees, so volume is the harder half of the pair to invent.
    if cfg.min_vol_fdv_ratio > 0 and meme_fdv and pool.vol_h24 is not None:
        ratio = pool.vol_h24 / meme_fdv
        if ratio < cfg.min_vol_fdv_ratio:
            failed.append(f"vol/fdv {ratio:.4f} < {cfg.min_vol_fdv_ratio}")

    # Wash-trade detector. Volume and txn counts are both purchasable with fees;
    # distinct wallets are not. A live decoy in the fixture showed 701 buys from
    # a single buyer, with volume identical across every window.
    if cfg.max_trades_per_buyer > 0 and pool.buyers_h1 > 0:
        per_buyer = (pool.buys_h1 + pool.sells_h1) / pool.buyers_h1
        if per_buyer > cfg.max_trades_per_buyer:
            failed.append(
                f"{per_buyer:.0f} trades/buyer > {cfg.max_trades_per_buyer:.0f}"
            )

    # Already ran and rolled over: up hard on the hour but falling over the last
    # quarter of it. Measured on m15 rather than h24, which is unreliable on a
    # pool minutes old.
    if (
        cfg.retrace_h1_pct > 0
        and cfg.retrace_m15_pct < 0
        and pool.price_change_h1 is not None
        and pool.price_change_m15 is not None
        and pool.price_change_h1 >= cfg.retrace_h1_pct
        and pool.price_change_m15 <= cfg.retrace_m15_pct
    ):
        failed.append(
            f"retracing (h1 {pool.price_change_h1:+.0f}%, "
            f"m15 {pool.price_change_m15:+.0f}%)"
        )

    return QualityVerdict(not failed, tuple(failed))


@dataclass(frozen=True)
class SocialVerdict:
    """Red / green / amber on a pool's social presence.

    RED means something was positively established: the pool has no socials at
    all, or every social it lists is a confirmed dead link. GREEN means a link
    was confirmed live AND carried measured engagement at or above the floor.
    AMBER is everything in between, including "links are live but nobody could
    measure the audience".

    The absence of a measurement is never scored as a bad measurement. There is
    no free source for X post views, so if unmeasured engagement counted as
    zero, every token on this chain would sit permanently at RED and the flag
    would carry no information.
    """

    flag: str  # "red" | "green" | "amber"
    live: int = 0
    dead: int = 0
    unknown: int = 0
    engagement: int | None = None  # best measured audience, None if unmeasured
    reason: str = ""

    @property
    def is_red(self) -> bool:
        return self.flag == "red"

    @property
    def is_green(self) -> bool:
        return self.flag == "green"


def social_verdict(
    socials: Sequence[str], checks: Mapping[str, "LinkCheck"], cfg: Config
) -> SocialVerdict:
    """Score a pool's socials from whatever link checks are available."""
    if not socials:
        return SocialVerdict("red", reason="no socials")

    live = dead = unknown = 0
    best: int | None = None
    for url in socials:
        check = checks.get(url)
        if check is None or check.state == "unknown":
            unknown += 1
            continue
        if check.state == "dead":
            dead += 1
            continue
        live += 1
        if check.engagement is not None:
            best = check.engagement if best is None else max(best, check.engagement)

    # Every listed social confirmed dead is as bad as having none - the link
    # exists only to look legitimate.
    if dead and not live and not unknown:
        return SocialVerdict(
            "red", live, dead, unknown, best, f"all {dead} social link(s) dead"
        )

    floor = cfg.social_green_engagement
    if live and best is not None and floor > 0 and best >= floor:
        return SocialVerdict(
            "green", live, dead, unknown, best, f"{best:,} engaged, link live"
        )

    if live and best is not None:
        return SocialVerdict(
            "amber", live, dead, unknown, best, f"only {best:,} engaged"
        )
    if live:
        return SocialVerdict(
            "amber", live, dead, unknown, best, "link live, audience unmeasured"
        )
    return SocialVerdict(
        "amber", live, dead, unknown, best, "links not yet verified"
    )


@dataclass(frozen=True)
class Momentum:
    """Rate-of-change confirmation from recorded history.

    Mirrors the "is it still picking up speed?" pre-entry check: volume rising
    rather than falling, and unique buyers still arriving. Holder counts are not
    available from the API, so unique buyers is the closest real proxy.
    """

    known: bool
    vol_rising: bool = False
    buyers_rising: bool = False
    vol_change_pct: float | None = None
    buyers_change: int | None = None

    @property
    def label(self) -> str:
        if not self.known:
            return "unproven"
        if self.vol_rising and self.buyers_rising:
            return "accelerating"
        if self.vol_rising or self.buyers_rising:
            return "mixed"
        return "fading"


def momentum(
    history: list[tuple[float | None, int | None]], min_samples: int = 6
) -> Momentum:
    """Compare the latest third of ``(vol_h1, buyers_h1)`` samples with the earlier ones."""
    points = [(v, b) for v, b in history if v is not None or b is not None]
    if len(points) < min_samples:
        return Momentum(False)
    split = max(1, len(points) // 3)
    early, late = points[:-split], points[-split:]

    def avg(rows, idx):
        vals = [row[idx] for row in rows if row[idx] is not None]
        return sum(vals) / len(vals) if vals else None

    v0, v1 = avg(early, 0), avg(late, 0)
    b0, b1 = avg(early, 1), avg(late, 1)
    vol_change = (100.0 * (v1 - v0) / v0) if v0 else None
    buyers_change = int(b1 - b0) if b0 is not None and b1 is not None else None
    return Momentum(
        True,
        vol_rising=bool(vol_change is not None and vol_change > 0),
        buyers_rising=bool(buyers_change is not None and buyers_change > 0),
        vol_change_pct=round(vol_change, 1) if vol_change is not None else None,
        buyers_change=buyers_change,
    )


@dataclass(frozen=True)
class LockVerdict:
    """Liquidity-lock proxy verdict.

    The GeckoTerminal API exposes no LP-lock field (true lock state lives
    on-chain: LP tokens burned to 0x0 or held by a locker contract), so this
    infers it from the reserve history this service records itself. Liquidity
    that holds near its running peak is behaving as locked; liquidity being
    pulled is not. ``known`` is False until there is enough history to judge,
    and an unknown verdict never counts as locked.
    """

    locked: bool
    known: bool
    drawdown: float | None  # worst observed drop from the running peak, 0..1
    observed_min: float | None  # minutes of history observed
    samples: int

    @property
    def label(self) -> str:
        if not self.known:
            return "unproven"
        return "locked" if self.locked else "pulling"


def lock_verdict(
    history: list[tuple[datetime, float | None]],
    cfg: Config,
    current_reserve: float | None = None,
) -> LockVerdict:
    """Judge the liquidity-lock proxy from ``(timestamp, reserve)`` samples.

    Drawdown is measured against the *running* peak, so an early liquidity pull
    is never hidden by a later refill.
    """
    points = [(ts, r) for ts, r in history if r is not None and r > 0]
    if len(points) < 2:
        return LockVerdict(False, False, None, None, len(points))
    points.sort(key=lambda p: p[0])
    observed_min = (points[-1][0] - points[0][0]).total_seconds() / 60.0

    peak = points[0][1]
    worst = 0.0
    for _ts, reserve in points:
        if reserve > peak:
            peak = reserve
        elif peak > 0:
            worst = max(worst, (peak - reserve) / peak)

    known = len(points) >= cfg.lock_min_samples and observed_min >= cfg.lock_min_age_min
    reserve_now = current_reserve if current_reserve is not None else points[-1][1]
    locked = (
        known
        and worst <= cfg.lock_max_drawdown
        and reserve_now is not None
        and reserve_now >= cfg.min_liq
    )
    return LockVerdict(locked, known, worst, observed_min, len(points))


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
    lock: LockVerdict | None = None,
) -> EscalationVerdict:
    """R3: reserve >= 2x first-alert reserve OR vol.h1 >= ESC_VOL_H1,
    at most once per esc_cooldown_h per address. Pools whose current
    liquidity is unknown or below cfg.min_liq never escalate (a volume
    spike on a drained pool is exit noise, not growth), and with
    cfg.require_liq_lock the liquidity-lock proxy must also pass — an
    unproven or pulling pool is held back rather than surfaced."""
    if pool.reserve_usd is None or pool.reserve_usd < cfg.min_liq:
        return EscalationVerdict(False, None, None)
    if cfg.require_liq_lock and lock is not None and not lock.locked:
        return EscalationVerdict(False, None, None)
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


def digest_pools(
    pools: list[Pool], now: datetime, limit: int = 10, min_liq: float = 0.0
) -> list[Pool]:
    """Top pools by h24 volume among pools created in the last 24 h.

    Pools with unknown liquidity or liquidity below min_liq are dropped, so
    dust/decoy pools with wash volume never reach the digest."""
    fresh = [
        p
        for p in pools
        if p.created_at is not None
        and now - p.created_at <= timedelta(hours=24)
        and p.reserve_usd is not None
        and p.reserve_usd >= min_liq
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
