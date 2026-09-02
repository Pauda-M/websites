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


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    telegram_chat_id: str = "5182460904"
    poll_sec: int = 60
    liq_floor: float = 150_000.0
    liq_floor_stock: float = 75_000.0
    new_window_min: int = 180
    esc_vol_h1: float = 500_000.0
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
            liq_floor=_f("LIQ_FLOOR", 150_000.0),
            liq_floor_stock=_f("LIQ_FLOOR_STOCK", 75_000.0),
            new_window_min=_i("NEW_WINDOW_MIN", 180),
            esc_vol_h1=_f("ESC_VOL_H1", 500_000.0),
            stock_symbols=symbols,
            log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO",
            tz=os.environ.get("TZ", "Europe/Zurich").strip() or "Europe/Zurich",
            data_dir=Path(os.environ.get("DATA_DIR", "/data").strip() or "/data"),
            esc_cooldown_h=_f("ESC_COOLDOWN_H", 6.0),
            symbol_cooldown_h=_f("SYMBOL_COOLDOWN_H", 24.0),
            digest_hour=_i("DIGEST_HOUR", 7),
        )
