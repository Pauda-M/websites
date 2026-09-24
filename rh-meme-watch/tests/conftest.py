from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from rh_meme_watch.app import App
from rh_meme_watch.config import Config
from rh_meme_watch.store import Store

FIXTURE_PATH = Path(__file__).parent / "fixture_robinhood_pools.json"

# Reference "now" used by synthetic-pool tests (controlled clock).
NOW = datetime(2026, 9, 2, 7, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="session")
def fixture_payload() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def api_item(
    name: str = "MEME / WETH",
    address: str | None = None,
    dex: str = "uniswap-v4",
    created_at: str | datetime | None = None,
    reserve: str | float | None = "200000",
    fdv: str | float | None = "500000",
    market_cap: str | float | None = None,
    vol_h1: str | float | None = "10000",
    vol_h24: str | float | None = "50000",
    pct_h1: str | float | None = "10.0",
    pct_h24: str | float | None = "20.0",
    vol_m15: str | float | None = "2500",
    pct_m15: str | float | None = "2.0",
    tx_h1: dict | None = None,
    socials: bool = True,
) -> dict:
    """Build a GeckoTerminal-shaped pool item for synthetic tests.

    Synthetic candidates carry social metadata by default because production
    NEW-token qualification now requires at least one project social profile.
    Set ``socials=False`` to exercise the fail-closed social gate.
    """
    if address is None:
        address = "0x" + f"{abs(hash(name)) % (16**40):040x}"
    if isinstance(created_at, datetime):
        created_at = created_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    base_id = f"robinhood_0xbase{address[-8:]}"
    quote_id = f"robinhood_0xquote{address[-8:]}"
    item = {
        "id": f"robinhood_{address}",
        "type": "pool",
        "attributes": {
            "base_token_price_usd": "0.000123",
            "address": address,
            "name": name,
            "pool_created_at": created_at,
            "fdv_usd": fdv,
            "market_cap_usd": market_cap,
            "price_change_percentage": {
                "h1": pct_h1,
                "h24": pct_h24,
                "m15": pct_m15,
            },
            "transactions": {
                "h1": tx_h1 or {"buys": 100, "sells": 80, "buyers": 50, "sellers": 40},
                "h24": {"buys": 900, "sells": 700, "buyers": 300, "sellers": 250},
            },
            "volume_usd": {"h1": vol_h1, "h24": vol_h24, "m15": vol_m15},
            "reserve_in_usd": reserve,
        },
        "relationships": {
            "base_token": {"data": {"id": base_id, "type": "token"}},
            "quote_token": {"data": {"id": quote_id, "type": "token"}},
            "dex": {"data": {"id": dex, "type": "dex"}},
        },
    }
    if socials:
        item["_socials_by_token"] = {
            base_id: ["https://x.com/test_project"],
            quote_id: ["https://x.com/test_project"],
        }
    return item


def mk_cfg(tmp_path: Path, **overrides) -> Config:
    defaults = dict(
        telegram_bot_token="123456:TEST-TOKEN",
        telegram_chat_id="5182460904",
        data_dir=tmp_path / "data",
    )
    defaults.update(overrides)
    return Config(**defaults)


class FakeTelegram:
    """Records every sent message; can be told to fail."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.fail_with: Exception | None = None

    def verify(self) -> dict:
        return {"ok": True, "result": {"username": "fake_bot"}}

    def send(self, text: str) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append(text)


class FakeGecko:
    """Serves preset API items; can be told to raise per endpoint."""

    def __init__(
        self,
        new_items: list[dict] | None = None,
        top_items: list[dict] | None = None,
        search_results: dict[str, list[dict]] | None = None,
        watchlist_items: dict[str, dict] | None = None,
    ) -> None:
        self.new_items = new_items or []
        self.top_items = top_items or []
        self.search_results = search_results or {}
        # Address -> item, served by the watchlist refresh. Empty by default so
        # the refresh is a no-op unless a test opts in.
        self.watchlist_items = watchlist_items or {}
        self.raise_on_new: Exception | None = None
        self.raise_on_top: Exception | None = None
        self.search_calls: list[str] = []
        self.watchlist_calls: list[list[str]] = []
        self.social_calls: list[str] = []

    def new_pools(self, network: str = "robinhood", pages: int = 3) -> list[dict]:
        if self.raise_on_new is not None:
            raise self.raise_on_new
        return list(self.new_items)

    def top_pools(self, network: str = "robinhood", pages: int = 2) -> list[dict]:
        if self.raise_on_top is not None:
            raise self.raise_on_top
        return list(self.top_items)

    def pools_by_address(
        self, addresses: list[str], network: str = "robinhood"
    ) -> list[dict]:
        self.watchlist_calls.append(list(addresses))
        return [self.watchlist_items[a] for a in addresses if a in self.watchlist_items]

    def socials_for(
        self, pool_address: str, network: str = "robinhood"
    ) -> dict[str, tuple[str, ...]]:
        """On-demand social lookup, served from whichever item carries the pool.

        Mirrors production: discovery does not include socials, so they are
        fetched per pool. Items built with ``api_item(socials=True)`` supply
        them; ``socials=False`` yields nothing, which is the fail-closed case.
        """
        self.social_calls.append(pool_address)
        for source in (self.new_items, self.top_items, list(self.watchlist_items.values())):
            for item in source:
                pool_id = str(item.get("id") or "")
                addr = pool_id.split("_", 1)[1] if "_" in pool_id else pool_id
                if addr.lower() == (pool_address or "").lower():
                    return {
                        k: tuple(v)
                        for k, v in (item.get("_socials_by_token") or {}).items()
                    }
        return {}

    def search_pools(self, query: str, network: str = "robinhood") -> list[dict]:
        self.search_calls.append(query)
        return list(self.search_results.get(query.upper(), []))


class Clock:
    def __init__(self, start: datetime = NOW) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


def mk_app(
    tmp_path: Path,
    gecko: FakeGecko,
    clock: Clock | None = None,
    cfg: Config | None = None,
) -> tuple[App, FakeTelegram, Clock]:
    # digest_hour=25 -> the daily digest never fires unless a test opts in
    cfg = cfg or mk_cfg(tmp_path, digest_hour=25)
    clock = clock or Clock()
    telegram = FakeTelegram()
    store = Store(cfg.db_path)
    app = App(
        cfg,
        gecko=gecko,  # type: ignore[arg-type]
        telegram=telegram,  # type: ignore[arg-type]
        store=store,
        now_fn=clock,
        sleep_fn=lambda s: None,
    )
    return app, telegram, clock


# Gates with no source in the video and never ordered are OFF by default. The
# tests that exercise them must switch them on deliberately - that is the whole
# point of the default being off.
OPTIONAL_GATES = dict(
    max_fdv=5_000_000.0,
    min_liq_fdv_ratio=0.02,
    min_buyers_h1=25,
    min_buy_sell_ratio=1.0,
    min_txns_h1=50,
    min_age_min=10,
    min_pct_h1=-15.0,
    min_vol_fdv_ratio=0.01,
    max_trades_per_buyer=20.0,
    retrace_h1_pct=20.0,
    retrace_m15_pct=-3.0,
    min_fdv=0.0,
)


def mk_cfg_optional(tmp_path: Path, **over) -> Config:
    """Config with the optional (unsourced) gates enabled, for their own tests."""
    return mk_cfg(tmp_path, **{**OPTIONAL_GATES, **over})
