"""429/403 backoff behavior (respx-mocked) and heartbeat-on-success only."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
import respx

from rh_meme_watch.gecko import BASE_URL, GeckoClient, GeckoUnavailable

from conftest import NOW, FakeGecko, api_item, mk_app

NEW_POOLS_URL = f"{BASE_URL}/networks/robinhood/new_pools"
TOP_POOLS_URL = f"{BASE_URL}/networks/robinhood/pools"


def _client_with_sleep_recorder():
    sleeps: list[float] = []
    client = GeckoClient(http=httpx.Client(), sleep=sleeps.append)
    return client, sleeps


@respx.mock
def test_429_backoff_then_success():
    route = respx.get(NEW_POOLS_URL).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(429),
            httpx.Response(200, json={"data": [api_item()]}),
        ]
    )
    client, sleeps = _client_with_sleep_recorder()
    items = client.new_pools(pages=1)
    assert len(items) == 1
    assert sleeps == [20.0, 40.0]
    assert route.call_count == 3


@respx.mock
def test_403_is_retryable_like_429():
    respx.get(NEW_POOLS_URL).mock(
        side_effect=[
            httpx.Response(403),
            httpx.Response(200, json={"data": []}),
        ]
    )
    client, sleeps = _client_with_sleep_recorder()
    assert client.new_pools(pages=1) == []
    assert sleeps == [20.0]


@respx.mock
def test_exhausted_backoff_raises_gecko_unavailable():
    respx.get(NEW_POOLS_URL).mock(return_value=httpx.Response(429))
    client, sleeps = _client_with_sleep_recorder()
    with pytest.raises(GeckoUnavailable):
        client.new_pools(pages=1)
    assert sleeps == [20.0, 40.0, 80.0]


@respx.mock
def test_full_cycle_against_mocked_api_writes_heartbeat(tmp_path):
    respx.get(NEW_POOLS_URL).mock(return_value=httpx.Response(200, json={"data": []}))
    respx.get(TOP_POOLS_URL).mock(return_value=httpx.Response(200, json={"data": []}))
    client = GeckoClient(http=httpx.Client(), sleep=lambda s: None)

    from conftest import Clock, FakeTelegram, mk_cfg
    from rh_meme_watch.app import App
    from rh_meme_watch.store import Store

    cfg = mk_cfg(tmp_path)
    app = App(
        cfg,
        gecko=client,
        telegram=FakeTelegram(),  # type: ignore[arg-type]
        store=Store(cfg.db_path),
        now_fn=Clock(),
        sleep_fn=lambda s: None,
    )
    assert app.run_cycle_safe() is True
    assert cfg.heartbeat_path.exists()


def test_heartbeat_not_written_when_api_fails(tmp_path):
    gecko = FakeGecko()
    gecko.raise_on_new = GeckoUnavailable("HTTP 429 after backoff")
    app, telegram, clock = mk_app(tmp_path, gecko)

    assert app.run_cycle_safe() is False, "loop must survive the failure"
    assert not app.cfg.heartbeat_path.exists(), "heartbeat only on success"

    # next cycle recovers -> heartbeat appears
    gecko.raise_on_new = None
    gecko.new_items = [
        api_item(created_at=NOW - timedelta(minutes=10), reserve="200000")
    ]
    assert app.run_cycle_safe() is True
    assert app.cfg.heartbeat_path.exists()


def test_loop_survives_unexpected_exceptions(tmp_path):
    gecko = FakeGecko()
    gecko.raise_on_top = ValueError("boom")
    app, telegram, clock = mk_app(tmp_path, gecko)
    assert app.run_cycle_safe() is False
    assert not app.cfg.heartbeat_path.exists()
