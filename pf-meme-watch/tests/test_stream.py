"""Collector behaviour: free streams only, and a drop is not a failure."""

from __future__ import annotations

import asyncio
import json

import pytest

from pf_meme_watch.models import CREATE, MIGRATE, STATUS
from pf_meme_watch.stream import (
    DEFAULT_SUBSCRIPTIONS,
    MeteredSubscriptionRefused,
    PumpStream,
)

from conftest import frames


class FakeSocket:
    """One connection: records what was sent, replays a script, then drops."""

    def __init__(self, script: list[str], fail_after: bool = True):
        self.script = script
        self.sent: list[str] = []
        self.fail_after = fail_after

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send(self, payload: str):
        self.sent.append(payload)

    async def __aiter__(self):  # pragma: no cover - replaced below
        raise NotImplementedError

    def __aiter__(self):
        async def gen():
            for line in self.script:
                yield line
            if self.fail_after:
                raise ConnectionResetError("socket closed by peer")

        return gen()


def _connector(sockets: list[FakeSocket]):
    calls = {"n": 0}

    def connect(url):
        i = min(calls["n"], len(sockets) - 1)
        calls["n"] += 1
        return sockets[i]

    connect.calls = calls
    return connect


# --- the cost guard ---------------------------------------------------------

def test_metered_subscriptions_are_refused_not_merely_unused():
    """A per-message charge must not be reachable by passing a string."""
    for method in ("subscribeTokenTrade", "subscribeAccountTrade"):
        with pytest.raises(MeteredSubscriptionRefused) as err:
            PumpStream(subscriptions=(method,))
        assert "metered" in str(err.value)


def test_unknown_methods_are_rejected():
    with pytest.raises(ValueError):
        PumpStream(subscriptions=("subscribeSomethingElse",))


def test_the_default_is_the_free_pair():
    stream = PumpStream()
    assert stream.subscriptions == DEFAULT_SUBSCRIPTIONS
    assert set(stream.subscriptions) == {"subscribeNewToken", "subscribeMigration"}


# --- consuming --------------------------------------------------------------

def test_real_frames_arrive_parsed():
    script = [json.dumps(f) for f in frames()]
    sock = FakeSocket(script)
    stream = PumpStream(connect=_connector([sock]), sleep=_noop_sleep)

    got = []
    asyncio.run(stream.run(got.append, stop=lambda: len(got) >= len(script)))

    kinds = [launch.kind for launch in got]
    assert CREATE in kinds and MIGRATE in kinds and STATUS in kinds
    creates = [g for g in got if g.is_create and g.dev_share is not None]
    assert any(abs(c.dev_share - 0.20) < 0.001 for c in creates), "SOCK still 20%"


def test_it_subscribes_on_connect():
    sock = FakeSocket([], fail_after=False)
    stream = PumpStream(connect=_connector([sock]), sleep=_noop_sleep)
    asyncio.run(stream.run(lambda _l: None, stop=_once()))
    methods = [json.loads(s)["method"] for s in sock.sent]
    assert methods == list(DEFAULT_SUBSCRIPTIONS)


def test_a_dropped_socket_reconnects_and_resubscribes():
    """A drop is normal operation on a public stream, not an error."""
    first = FakeSocket([json.dumps({"message": "hi"})])  # drops after one frame
    second = FakeSocket([json.dumps(frames()[3])], fail_after=False)
    connect = _connector([first, second])
    stream = PumpStream(connect=connect, sleep=_noop_sleep)

    got = []
    asyncio.run(stream.run(got.append, stop=lambda: len(got) >= 2))

    assert connect.calls["n"] >= 2, "it reconnected"
    assert stream.reconnects >= 1
    assert [json.loads(s)["method"] for s in second.sent] == list(DEFAULT_SUBSCRIPTIONS)


def test_a_socket_that_opens_then_drops_still_backs_off():
    """The bug this caught: resetting on connect rather than on a delivered
    frame meant a provider accepting and instantly dropping sockets got hammered
    at the minimum delay forever."""
    bad = [FakeSocket([]) for _ in range(6)]  # open, deliver nothing, drop
    stream = PumpStream(connect=_connector(bad), sleep=_noop_sleep,
                        reconnect_min_sec=1.0, reconnect_max_sec=60.0)
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 10

    asyncio.run(stream.run(lambda _l: None, stop=stop))
    used = stream.backoffs_used
    assert len(used) >= 3
    assert used == sorted(used), "monotonically increasing"
    assert used[-1] > used[0], "it actually grew"
    assert max(used) <= 60.0, "and stays capped"


def test_backoff_resets_only_once_a_frame_actually_arrives():
    good = FakeSocket([json.dumps({"message": "hi"})])  # delivers, then drops
    after = FakeSocket([], fail_after=False)
    stream = PumpStream(connect=_connector([good, after]), sleep=_noop_sleep,
                        reconnect_min_sec=1.0)
    stream.backoff = 32.0  # as if it had been failing for a while

    got = []
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 6

    asyncio.run(stream.run(got.append, stop=stop))
    assert got, "a frame was delivered"
    assert stream.backoffs_used[0] == 1.0, "a proven connection reset it"


def test_a_garbage_frame_does_not_kill_the_socket():
    sock = FakeSocket(["not json at all", json.dumps(frames()[3])], fail_after=False)
    stream = PumpStream(connect=_connector([sock]), sleep=_noop_sleep)

    got = []
    asyncio.run(stream.run(got.append, stop=lambda: len(got) >= 2))

    assert got[0].kind == STATUS, "unparseable becomes a status, not an exception"
    assert got[1].is_create, "and the socket kept going"


async def _noop_sleep(_d: float) -> None:
    return None


def _once():
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 1

    return stop
