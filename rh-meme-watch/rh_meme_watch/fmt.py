"""Formatting helpers and Telegram MarkdownV2 escaping."""

from __future__ import annotations

# Every reserved character of Telegram MarkdownV2 (plus backslash itself).
_MDV2_RESERVED = "_*[]()~`>#+-=|{}.!"


def escape_md(text: str) -> str:
    out = text.replace("\\", "\\\\")
    for ch in _MDV2_RESERVED:
        out = out.replace(ch, "\\" + ch)
    return out


def fmt_usd(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "-" if value < 0 else ""
    v = abs(value)
    if v >= 1e9:
        s = f"{v / 1e9:.1f}".rstrip("0").rstrip(".")
        return f"{sign}${s}B"
    if v >= 1e6:
        s = f"{v / 1e6:.1f}".rstrip("0").rstrip(".")
        return f"{sign}${s}M"
    if v >= 10_000:
        return f"{sign}${v / 1e3:.0f}k"
    if v >= 1_000:
        s = f"{v / 1e3:.1f}".rstrip("0").rstrip(".")
        return f"{sign}${s}k"
    return f"{sign}${v:.0f}"


def fmt_int(value: int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,}".replace(",", " ")


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.0f}%"


def fmt_age(minutes: float | None) -> str:
    if minutes is None:
        return "n/a"
    m = max(0, int(minutes))
    if m < 60:
        return f"{m}m"
    if m < 1440:
        h, rem = divmod(m, 60)
        return f"{h}h{rem:02d}m"
    d, rem = divmod(m, 1440)
    return f"{d}d{rem // 60}h"


def fmt_ratio(mult: float) -> str:
    s = f"{mult:.1f}".rstrip("0").rstrip(".")
    return f"x{s}"
