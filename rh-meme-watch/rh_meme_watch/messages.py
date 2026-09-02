"""Alert message builders. Output is fully-escaped Telegram MarkdownV2."""

from __future__ import annotations

from datetime import datetime

from .config import Config
from .fmt import escape_md, fmt_age, fmt_int, fmt_pct, fmt_ratio, fmt_usd
from .models import Pool
from .rules import Classification

_DAY_MIN = 24 * 60


def _delta_line(pool: Pool, now: datetime) -> str:
    """h24 price change is garbage on pools younger than 24 h -> show h1."""
    age = pool.age_minutes(now)
    if age is None or age < _DAY_MIN:
        return f"Δ1h {fmt_pct(pool.price_change_h1)}"
    return f"Δ1h {fmt_pct(pool.price_change_h1)} · Δ24h {fmt_pct(pool.price_change_h24)}"


def _stats_lines(pool: Pool, fdv_meme: float | None, now: datetime) -> list[str]:
    line1 = (
        f"{pool.dex or 'dex?'} age {fmt_age(pool.age_minutes(now))}"
        f" · liq {fmt_usd(pool.reserve_usd)}"
        f" · FDV(meme) {fmt_usd(fdv_meme)}"
        f" · vol1h {fmt_usd(pool.vol_h1)}"
        f" · {_delta_line(pool, now)}"
    )
    line2 = (
        f"buys/sells 1h {fmt_int(pool.buys_h1)}/{fmt_int(pool.sells_h1)}"
        f" · buyers/sellers {fmt_int(pool.buyers_h1)}/{fmt_int(pool.sellers_h1)}"
    )
    return [line1, line2]


def build_startup(cfg: Config) -> str:
    text = (
        f"rh-meme-watch up · floor {fmt_usd(cfg.liq_floor)}"
        f" / stock {fmt_usd(cfg.liq_floor_stock)}"
        f" · poll {cfg.poll_sec}s"
    )
    return escape_md(text)


def build_new_alert(
    pool: Pool,
    cls: Classification,
    fdv_meme: float | None,
    now: datetime,
) -> str:
    header = (
        f"📈 NEW STOCK-PAIRED {pool.name}"
        if cls.is_stock_paired
        else f"🆕 NEW {pool.name}"
    )
    lines = [header, *_stats_lines(pool, fdv_meme, now), f"gecko: {pool.gecko_url}"]
    return escape_md("\n".join(lines))


def build_escalation(
    pool: Pool,
    cls: Classification,
    fdv_meme: float | None,
    now: datetime,
    reason: str,
    liq_mult: float | None,
    warnings: list[str],
) -> str:
    header = f"🔺 ESCALATE {pool.name}"
    if cls.is_stock_paired:
        header = f"🔺 ESCALATE 📈 {pool.name}"
    why = (
        f"liq {fmt_ratio(liq_mult)} vs first alert"
        if reason == "liq_x2" and liq_mult is not None
        else f"vol1h {fmt_usd(pool.vol_h1)}"
    )
    lines = [header, why, *_stats_lines(pool, fdv_meme, now)]
    lines.extend(f"⚠️ {w}" for w in warnings)
    lines.append(f"gecko: {pool.gecko_url}")
    return escape_md("\n".join(lines))


def build_digest(
    entries: list[tuple[Pool, Classification, list[str]]],
    now: datetime,
) -> str:
    lines = ["📊 daily digest · top pools by 24h volume (created last 24h)"]
    if not entries:
        lines.append("no new pools in the last 24h")
    for i, (pool, cls, warnings) in enumerate(entries, start=1):
        tag = "📈 " if cls.is_stock_paired else ""
        line = (
            f"{i}. {tag}{pool.name}"
            f" · liq {fmt_usd(pool.reserve_usd)}"
            f" · vol24h {fmt_usd(pool.vol_h24)}"
            f" · {_delta_line(pool, now)}"
        )
        if warnings:
            line += " · ⚠️ " + "; ".join(warnings)
        lines.append(line)
    return escape_md("\n".join(lines))
