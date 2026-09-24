"""pump.fun watcher configuration.

The four threshold values are the ones from the checklist this watcher
implements, in their native units - unlike the Robinhood watcher, nothing here
needed translating, because these are literal pump.fun fields.

Market cap is the exception: the stream reports it in SOL, so the USD floor is
converted at the live SOL price rather than compared directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, "").strip() or default))
    except ValueError:
        return default


def _b(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    # --- the checklist, in native units ---
    min_mcap_usd: float = 6_000.0
    min_vol_usd: float = 3_000.0        # needs the funded key; 0 until then
    min_fees_sol: float = 0.1           # needs the funded key; 0 until then
    require_socials: bool = True

    # --- deployer concentration (measured, not eyeballed) ---
    # Calibration is provisional: the captured sample showed 0%, 0%, 0%, 6.19%
    # and 20%. Five launches is not a distribution, so these are starting points
    # to be re-fitted once real volume has accumulated.
    dev_share_elevated: float = 0.05
    dev_share_bundled: float = 0.15

    # --- copycat / vamp detection ---
    copycat_window_sec: int = 900
    copycat_memory: int = 4_000

    # --- stream ---
    ws_url: str = "wss://pumpportal.fun/api/data"
    api_key: str = ""                   # funds trade events (>= 0.02 SOL)
    reconnect_min_sec: float = 1.0
    reconnect_max_sec: float = 60.0
    metadata_lookups_per_min: int = 60
    metadata_timeout_sec: float = 8.0

    @property
    def has_trade_feed(self) -> bool:
        """Volume and fees-paid gates are unavailable without a funded key."""
        return bool(self.api_key)

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            min_mcap_usd=_f("PF_MIN_MCAP_USD", 6_000.0),
            min_vol_usd=_f("PF_MIN_VOL_USD", 3_000.0),
            min_fees_sol=_f("PF_MIN_FEES_SOL", 0.1),
            require_socials=_b("PF_REQUIRE_SOCIALS", True),
            dev_share_elevated=_f("PF_DEV_SHARE_ELEVATED", 0.05),
            dev_share_bundled=_f("PF_DEV_SHARE_BUNDLED", 0.15),
            copycat_window_sec=_i("PF_COPYCAT_WINDOW_SEC", 900),
            copycat_memory=_i("PF_COPYCAT_MEMORY", 4_000),
            ws_url=os.environ.get("PF_WS_URL", "").strip()
            or "wss://pumpportal.fun/api/data",
            api_key=os.environ.get("PF_API_KEY", "").strip(),
            metadata_lookups_per_min=_i("PF_METADATA_LOOKUPS_PER_MIN", 60),
        )
