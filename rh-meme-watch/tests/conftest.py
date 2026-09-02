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
    tx_h1: dict | None = None,
) -> dict:
    """Build a GeckoTerminal-shaped pool item for synthetic tests."""
    if address is None:
        address = "0x" + f"{abs(hash(name)) % (16**40):040x}"
    if isinstance(created_at, datetime):
        created_at = created_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "id": f"robinhood_{address}",
        "type": "pool",
        "attributes": {
            "base_token_price_usd": "0.000123",
            "address": address,
            "name": name,
            "pool_created_at": created_at,
            "fdv_usd": fdv,
            "market_cap_usd": market_cap,
            "price_change_percentage": {"h1": pct_h1, "h24": pct_h24},
            "transactions": {
                "h1": tx_h1 or {"buys": 100, "sells": 80, "buyers": 50, "sellers": 40},
                "h24": {"buys": 900, "sells": 700, "buyers": 300, "sellers": 250},
            },
            "volume_usd": {"h1": vol_h1, "h24": vol_h24},
            "reserve_in_usd": reserve,
        },
        "relationships": {
            "base_token": {"data": {"id": f"robinhood_0xbase{address[-8:]}", "type": "token"}},
            "quote_token": {"data": {"id": f"robinhood_0xquote{address[-8:]}", "type": "token"}},
            "dex": {"data": {"id": dex, "type": "dex"}},
        },
    }


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
    ) -> None:
        self.new_items = new_items or []
        self.top_items = top_items or []
        self.search_results = search_results or {}
        self.raise_on_new: Exception | None = None
        self.raise_on_top: Exception | None = None
        self.search_calls: list[str] = []

    def new_pools(self, network: str = "robinhood", pages: int = 3) -> list[dict]:
        if self.raise_on_new is not None:
            raise self.raise_on_new
        return list(self.new_items)

    def top_pools(self, network: str = "robinhood", pages: int = 2) -> list[dict]:
        if self.raise_on_top is not None:
            raise self.raise_on_top
        return list(self.top_items)

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
