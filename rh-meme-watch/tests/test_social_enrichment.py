"""On-demand social lookups must never stall or silently suppress the loop.

Discovery used to enrich blindly, newest-first. It returned ~60 pools a cycle
against a budget of 3, so the budget went to pools too young to alert while every
real candidate reached the social gate with no data and failed closed - the
dashboard sat at zero alerts with nothing in the log to explain it. Socials are
now fetched per pool, by the caller, only once every free check has passed.
"""

from __future__ import annotations

import httpx
import respx

from rh_meme_watch.gecko import BASE_URL, GeckoClient

from conftest import api_item

NEW_POOLS_URL = f"{BASE_URL}/networks/robinhood/new_pools"
INFO_URL_RE = r"/networks/robinhood/pools/0x[0-9a-f]+/info$"

TWITTER_INFO = {
    "data": [
        {"id": "robinhood_0xbaseaabbccdd", "attributes": {"twitter_handle": "@proj"}}
    ]
}


def _client():
    sleeps: list[float] = []
    return GeckoClient(http=httpx.Client(), sleep=sleeps.append), sleeps


@respx.mock
def test_discovery_no_longer_spends_the_budget_blindly():
    """new_pools must not fetch socials for pools it merely happened to return."""
    respx.get(NEW_POOLS_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [api_item(address=f"0x{i:02x}" + "0" * 38) for i in range(20)]}
        )
    )
    info = respx.get(url__regex=INFO_URL_RE).mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    client, _ = _client()

    items = client.new_pools(pages=1)

    assert len(items) == 20, "market data still returned"
    assert info.call_count == 0, "not one lookup spent on undecided pools"


@respx.mock
def test_lookup_does_not_sleep_through_the_cycle():
    """A 429 on metadata must cost one request, not 140s of backoff."""
    info = respx.get(url__regex=INFO_URL_RE).mock(return_value=httpx.Response(429))
    client, sleeps = _client()

    result = client.socials_for("0xaa" + "0" * 38)

    assert result == {}, "fails closed"
    assert info.call_count == 1, "single attempt, no retry storm"
    assert sleeps == [], "no sleeping for metadata"


@respx.mock
def test_pool_discovery_still_retries_with_full_backoff():
    """The bounded-retry mode must not weaken market-data resilience."""
    respx.get(NEW_POOLS_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"data": []})]
    )
    client, sleeps = _client()
    assert client.new_pools(pages=1) == []
    assert sleeps == [20.0]


@respx.mock
def test_socials_found_are_cached_for_the_long_ttl():
    address = "0xbb" + "0" * 38
    info = respx.get(url__regex=INFO_URL_RE).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": f"robinhood_0xbase{address[-8:]}",
                        "attributes": {"twitter_handle": "@proj"},
                    }
                ]
            },
        )
    )
    client, _ = _client()

    first = client.socials_for(address)
    second = client.socials_for(address)

    assert first == second
    assert list(first.values())[0] == ("https://x.com/proj",)
    assert info.call_count == 1, "second call served from cache"


@respx.mock
def test_missing_socials_are_rechecked_soon_not_cached_for_hours():
    """Projects add socials after deploy; a long negative cache would hide them."""
    address = "0xcc" + "0" * 38
    respx.get(NEW_POOLS_URL).mock(
        return_value=httpx.Response(200, json={"data": [api_item(address=address)]})
    )
    info = respx.get(url__regex=INFO_URL_RE).mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    client, _ = _client()
    client.social_miss_ttl_sec = 30

    client.socials_for(address)
    assert info.call_count == 1

    # within the short miss TTL -> still cached
    client.socials_for(address)
    assert info.call_count == 1

    # once the short TTL lapses the pool is re-checked, well inside the 180 min
    # alert window that a 6 h cache would have swallowed.
    addr_only = address
    ts, socials, ttl = client._pool_social_cache[addr_only]
    assert ttl == 30, "miss TTL, not the 6 h hit TTL"
    client._pool_social_cache[addr_only] = (ts - 31, socials, ttl)
    client.socials_for(address)
    assert info.call_count == 2


@respx.mock
def test_lookup_budget_is_bounded_per_cycle():
    """Even on-demand, a pathological cycle must not exhaust the rate limit."""
    respx.get(NEW_POOLS_URL).mock(return_value=httpx.Response(200, json={"data": []}))
    info = respx.get(url__regex=INFO_URL_RE).mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    client, _ = _client()
    client.social_lookups_per_cycle = 3

    client.new_pools(pages=1)  # resets the per-cycle counter
    for i in range(10):
        client.socials_for(f"0x{i:02x}" + "0" * 38)

    assert info.call_count == 3, "budget caps the request spend"
    assert len(client._pool_social_cache) == 3, "unbudgeted pools are not cached"
