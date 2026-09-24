"""Environment-driven configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_STOCK_SYMBOLS = (
    "AAPL,AMC,AMD,AMZN,BABA,BE,CRCL,CRWV,GOOGL,GOOG,INTC,META,MSFT,MU,NVDA,"
    "ORCL,PLTR,QQQ,SGOV,SLV,SNDK,SPCX,SPY,TSLA,USAR,HIMS,LLY,TTWO,GME,RBLX,QUBT,HOOD"
)

# Symbols that are never the meme side of a pool but are not tokenized stocks either.
NON_MEME_EXTRA = frozenset({"WETH", "USDG", "USDC", "USDT", "GLD"})

# LP custodians observed on chain, as "address=label" pairs. Measured 2026-09-12:
# this contract held 100% of the LP supply of every uniswap-v2-robinhood pool
# sampled, is owner-controlled (owner(), transferOwnership(), no unlockTime())
# and its owner is an EOA - so it is custody, not a time lock.
DEFAULT_LP_CUSTODIANS = (
    "0x2ac03e14cfe755426daaee0a4994184ce81482f8=v2 launchpad custodian"
)


class ConfigError(RuntimeError):
    pass


def _f(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _i(name: str, default: int) -> int:
    return int(_f(name, float(default)))


def _custodians(csv: str) -> tuple[tuple[str, str], ...]:
    """Parse "addr=label,addr=label" into pairs; a bare address gets an empty label."""
    out: list[tuple[str, str]] = []
    for chunk in csv.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        addr, _, label = chunk.partition("=")
        addr = addr.strip().lower()
        if addr.startswith("0x") and len(addr) == 42:
            out.append((addr, label.strip()))
    return tuple(out)


def _b(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be a boolean (1/0/true/false), got {raw!r}")


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    telegram_chat_id: str = "5182460904"
    poll_sec: int = 60
    liq_floor: float = 20_000.0  # [USER] "at least 20 000 liquidity"
    liq_floor_stock: float = 20_000.0  # [USER]
    new_window_min: int = 180
    esc_vol_h1: float = 500_000.0
    min_liq: float = 20_000.0  # pools below this never appear in digests/escalations
    # Liquidity-lock proxy. True lock state is an on-chain property (LP burned or
    # held by a locker) that the GeckoTerminal API does not expose, so it is
    # inferred from observed reserve history: liquidity that holds near its
    # running peak behaves like locked liquidity, liquidity being pulled does not.
    require_liq_lock: bool = True  # gate escalations + digest entries on it
    lock_max_drawdown: float = 0.25  # worst allowed drop from the running peak
    lock_min_age_min: int = 30  # minutes of history needed before judging
    lock_min_samples: int = 10  # snapshots needed before judging
    stock_symbols: frozenset[str] = field(
        default_factory=lambda: frozenset(s for s in DEFAULT_STOCK_SYMBOLS.split(",") if s)
    )
    log_level: str = "INFO"
    tz: str = "Europe/Zurich"
    data_dir: Path = Path("/data")
    esc_cooldown_h: float = 6.0
    symbol_cooldown_h: float = 24.0
    digest_hour: int = 7
    fdv_cache_ttl_sec: int = 600
    fdv_lookups_per_cycle: int = 3
    # ------------------------------------------------------------------
    # EVERY threshold below carries its source. Nothing here is invented.
    #   [VIDEO] = on the filter panel in the source video
    #   [USER]  = explicitly ordered
    # A gate with no source does not belong in this file. An earlier revision
    # carried ten invented thresholds; one of them (a buy/sell ratio that
    # appears nowhere in the video and was never asked for) rejected 100% of
    # candidates and produced zero alerts for hours.
    # ------------------------------------------------------------------
    # [VIDEO] Market cap minimum, 6000. His panel sets a floor, not a ceiling.
    min_fdv: float = 6_000.0
    # [VIDEO] Volume minimum, 3000.
    min_vol_h1: float = 3_000.0
    # [VIDEO] Liquidity, Buys and Sells were left BLANK on his panel. The
    # liquidity floor below is [USER], not his.
    #
    # Disabled by default (0): no source. Retained as switches rather than
    # deleted so they can be turned on deliberately, never by drifting back in.
    max_fdv: float = 0.0
    min_liq_fdv_ratio: float = 0.0
    min_buyers_h1: int = 0
    min_buy_sell_ratio: float = 0.0
    min_txns_h1: int = 0
    min_age_min: int = 0
    min_pct_h1: float = -1e9
    min_vol_fdv_ratio: float = 0.0
    max_trades_per_buyer: float = 0.0
    retrace_h1_pct: float = 0.0
    retrace_m15_pct: float = 0.0
    # Social gate. A NEW pool's meme side must expose at least one project
    # social. AND-ed with the liquidity floor, never traded off against it.
    require_socials: bool = True
    # Social engagement flags. "Green" needs MEASURED engagement at or above the
    # threshold; "red" fires on having no socials at all, which is always
    # knowable. Engagement that could not be measured is never treated as zero -
    # that would red-flag every token on this chain, since no free source for X
    # post views exists. See socials.py.
    social_green_engagement: int = 1000
    social_engagement_ttl_sec: int = 3600
    x_bearer_token: str = ""  # optional; without it X engagement is unmeasured
    social_lookups_per_cycle: int = 6  # bounded so the 30 req/min limit is safe
    social_cache_ttl_sec: int = 21_600  # a found social set is stable
    social_miss_ttl_sec: int = 300  # projects add socials after deploy; recheck
    # Lookups spent per cycle establishing socials for already-alerted pools, so
    # the dashboard stops claiming "no social" about pools nobody examined. Runs
    # after the alert path, which has first claim on the budget.
    social_backfill_per_cycle: int = 2
    # On-chain verification (Robinhood Chain RPC). Empty url disables it.
    rpc_url: str = ""
    onchain_lookups_per_cycle: int = 4
    onchain_cache_ttl_sec: int = 1800
    custody_drop_pct: float = 10.0  # LP custodian balance drop that raises an alert
    lp_custodians: tuple[tuple[str, str], ...] = ()
    dashboard_port: int = 8080  # 0 disables the dashboard HTTP server
    # Alerted pools re-read so their history keeps accumulating after they drop
    # out of discovery. watchlist_size is the set covered; watchlist_batch is how
    # much of it is refreshed per cycle, rotating. Refreshing all 200 at once cost
    # 7 requests, every one of them rate-limited, and starved the loop - so the
    # set is walked a batch at a time instead: 1 extra request per cycle, a full
    # pass every watchlist_size/watchlist_batch cycles.
    watchlist_size: int = 200
    watchlist_batch: int = 30  # the /multi/ endpoint's per-request maximum
    snapshot_keep_days: int = 14

    @property
    def db_path(self) -> Path:
        return self.data_dir / "state.db"

    @property
    def heartbeat_path(self) -> Path:
        return self.data_dir / "heartbeat"

    @staticmethod
    def from_env() -> "Config":
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ConfigError("TELEGRAM_BOT_TOKEN is required")
        symbols_csv = os.environ.get("STOCK_SYMBOLS", "").strip() or DEFAULT_STOCK_SYMBOLS
        symbols = frozenset(
            s.strip().upper() for s in symbols_csv.replace(" ", ",").split(",") if s.strip()
        )
        return Config(
            telegram_bot_token=token,
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", "5182460904").strip()
            or "5182460904",
            poll_sec=_i("POLL_SEC", 60),
            liq_floor=_f("LIQ_FLOOR", 20_000.0),
            liq_floor_stock=_f("LIQ_FLOOR_STOCK", 20_000.0),
            new_window_min=_i("NEW_WINDOW_MIN", 180),
            esc_vol_h1=_f("ESC_VOL_H1", 500_000.0),
            min_liq=_f("MIN_LIQ", 20_000.0),
            require_liq_lock=_b("REQUIRE_LIQ_LOCK", True),
            lock_max_drawdown=_f("LOCK_MAX_DRAWDOWN", 0.25),
            lock_min_age_min=_i("LOCK_MIN_AGE_MIN", 30),
            lock_min_samples=_i("LOCK_MIN_SAMPLES", 10),
            stock_symbols=symbols,
            log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO",
            tz=os.environ.get("TZ", "Europe/Zurich").strip() or "Europe/Zurich",
            data_dir=Path(os.environ.get("DATA_DIR", "/data").strip() or "/data"),
            esc_cooldown_h=_f("ESC_COOLDOWN_H", 6.0),
            symbol_cooldown_h=_f("SYMBOL_COOLDOWN_H", 24.0),
            digest_hour=_i("DIGEST_HOUR", 7),
            max_fdv=_f("MAX_FDV", 0.0),
            min_liq_fdv_ratio=_f("MIN_LIQ_FDV_RATIO", 0.0),
            min_buyers_h1=_i("MIN_BUYERS_H1", 0),
            min_buy_sell_ratio=_f("MIN_BUY_SELL_RATIO", 0.0),
            min_txns_h1=_i("MIN_TXNS_H1", 0),
            min_age_min=_i("MIN_AGE_MIN", 0),
            min_pct_h1=_f("MIN_PCT_H1", -1e9),
            min_fdv=_f("MIN_FDV", 6_000.0),
            min_vol_h1=_f("MIN_VOL_H1", 3_000.0),
            min_vol_fdv_ratio=_f("MIN_VOL_FDV_RATIO", 0.0),
            max_trades_per_buyer=_f("MAX_TRADES_PER_BUYER", 0.0),
            retrace_h1_pct=_f("RETRACE_H1_PCT", 0.0),
            retrace_m15_pct=_f("RETRACE_M15_PCT", 0.0),
            require_socials=_b("REQUIRE_SOCIALS", True),
            social_green_engagement=_i("SOCIAL_GREEN_ENGAGEMENT", 1000),
            social_engagement_ttl_sec=_i("SOCIAL_ENGAGEMENT_TTL_SEC", 3600),
            x_bearer_token=os.environ.get("X_BEARER_TOKEN", "").strip(),
            social_lookups_per_cycle=_i("SOCIAL_LOOKUPS_PER_CYCLE", 6),
            social_cache_ttl_sec=_i("SOCIAL_CACHE_TTL_SEC", 21_600),
            social_miss_ttl_sec=_i("SOCIAL_MISS_TTL_SEC", 300),
            social_backfill_per_cycle=_i("SOCIAL_BACKFILL_PER_CYCLE", 2),
            rpc_url=os.environ.get("RPC_URL", "").strip(),
            onchain_lookups_per_cycle=_i("ONCHAIN_LOOKUPS_PER_CYCLE", 4),
            onchain_cache_ttl_sec=_i("ONCHAIN_CACHE_TTL_SEC", 1800),
            custody_drop_pct=_f("CUSTODY_DROP_PCT", 10.0),
            lp_custodians=_custodians(
                os.environ.get("LP_CUSTODIANS", "").strip() or DEFAULT_LP_CUSTODIANS
            ),
            watchlist_size=_i("WATCHLIST_SIZE", 200),
            watchlist_batch=_i("WATCHLIST_BATCH", 30),
            dashboard_port=_i("DASHBOARD_PORT", 8080),
        )
