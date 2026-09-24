"""SOL/USD feed, and the rule that an unknown price disables its own gate.

The market-cap filter is a MINIMUM stated in USD against a stream that reports
SOL. Evaluating it without a price would reject everything - which is precisely
how the social gate silently zeroed the other watcher for hours with nothing in
the log to explain it. Here an unmeasurable input yields None, and the caller
skips the check rather than failing it.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from pf_meme_watch.price import GECKO_URL, SolPriceFeed, mcap_usd


def _payload(price):
    return {"data": {"attributes": {"price_usd": price}}}


def _feed(**kw) -> SolPriceFeed:
    kw.setdefault("http", httpx.Client())
    return SolPriceFeed(**kw)


# --- conversion -------------------------------------------------------------

def test_conversion_never_guesses():
    assert mcap_usd(30.0, 200.0) == pytest.approx(6000.0)
    assert mcap_usd(None, 200.0) is None
    assert mcap_usd(30.0, None) is None
    assert mcap_usd(30.0, 0) is None, "a zero price is not a price"
    assert mcap_usd(30.0, -5) is None


def test_the_threshold_really_does_move_with_price():
    """24 SOL at $250, 40 SOL at $150 - the same filter, a different meaning."""
    sock_mcap_sol = 43.69
    assert mcap_usd(sock_mcap_sol, 150) < 6600
    assert mcap_usd(sock_mcap_sol, 250) > 10_000


# --- fetching ---------------------------------------------------------------

@respx.mock
def test_a_good_response_is_parsed_and_cached():
    route = respx.get(GECKO_URL).mock(
        return_value=httpx.Response(200, json=_payload("212.34"))
    )
    feed = _feed()
    assert feed.usd(now=1000.0) == pytest.approx(212.34)
    assert feed.usd(now=1010.0) == pytest.approx(212.34)
    assert route.call_count == 1, "second call served from cache"


@respx.mock
def test_a_stale_cache_is_refreshed():
    respx.get(GECKO_URL).mock(
        side_effect=[
            httpx.Response(200, json=_payload("200")),
            httpx.Response(200, json=_payload("260")),
        ]
    )
    feed = _feed(stale_after_sec=300)
    assert feed.usd(now=1000.0) == pytest.approx(200)
    assert feed.usd(now=1400.0) == pytest.approx(260), "past the stale window"


@respx.mock
def test_a_failed_refresh_falls_back_to_the_last_good_price():
    """One bad request must not disable the gate."""
    respx.get(GECKO_URL).mock(
        side_effect=[httpx.Response(200, json=_payload("200")), httpx.Response(503)]
    )
    feed = _feed(stale_after_sec=60, max_age_sec=3600)
    assert feed.usd(now=1000.0) == pytest.approx(200)
    assert feed.usd(now=1100.0) == pytest.approx(200), "still defensible"
    assert feed.failures == 1


@respx.mock
def test_an_ancient_price_is_dropped_rather_than_trusted():
    """SOL barely moves in minutes; an hour-old price during a sharp move would
    quietly shift the threshold without anyone noticing."""
    respx.get(GECKO_URL).mock(
        side_effect=[httpx.Response(200, json=_payload("200")), httpx.Response(503)]
    )
    feed = _feed(stale_after_sec=60, max_age_sec=3600)
    feed.usd(now=1000.0)
    assert feed.usd(now=1000.0 + 3601) is None, "too old to use"


@respx.mock
def test_never_raises_into_the_caller():
    respx.get(GECKO_URL).mock(side_effect=httpx.ConnectError("no route"))
    assert _feed().usd(now=1.0) is None


@respx.mock
@pytest.mark.parametrize(
    "body",
    [
        {"data": {}},
        {"data": {"attributes": {}}},
        {"data": {"attributes": {"price_usd": None}}},
        {"data": {"attributes": {"price_usd": "not a number"}}},
        {},
    ],
)
def test_malformed_payloads_yield_no_price_rather_than_a_wrong_one(body):
    respx.get(GECKO_URL).mock(return_value=httpx.Response(200, json=body))
    assert _feed().usd(now=1.0) is None


@respx.mock
@pytest.mark.parametrize("price", ["0.0001", "999999999", "-40"])
def test_implausible_prices_are_refused(price):
    """A parse error dressed as a number would silently retune the filter."""
    respx.get(GECKO_URL).mock(return_value=httpx.Response(200, json=_payload(price)))
    assert _feed().usd(now=1.0) is None
