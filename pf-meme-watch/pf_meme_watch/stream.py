"""pump.fun websocket collector.

Subscribes only to the free streams. ``subscribeTokenTrade`` and
``subscribeAccountTrade`` are metered - 0.01 SOL per 10,000 messages, drawn from
a funded wallet - and this watcher signs no transactions and holds no position,
so there is nothing on the other side of that cost. They are refused here rather
than merely left unused: a metered subscription that can be switched on by
passing the wrong string is a bill waiting to be run up by a typo.

The provider asks for one connection carrying all subscriptions, not one per
subscription, so this keeps a single socket and re-subscribes after a reconnect.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Awaitable, Callable

from .models import Launch, parse_frame

log = logging.getLogger("pf_meme_watch.stream")

FREE_METHODS = frozenset({"subscribeNewToken", "subscribeMigration"})
METERED_METHODS = frozenset({"subscribeTokenTrade", "subscribeAccountTrade"})

DEFAULT_SUBSCRIPTIONS = ("subscribeNewToken", "subscribeMigration")


class MeteredSubscriptionRefused(RuntimeError):
    """Raised rather than silently incurring a per-message charge."""


def _validate(methods: tuple[str, ...]) -> tuple[str, ...]:
    for method in methods:
        if method in METERED_METHODS:
            raise MeteredSubscriptionRefused(
                f"{method} is metered (0.01 SOL / 10k messages) and this watcher "
                "does not trade; refusing to subscribe"
            )
        if method not in FREE_METHODS:
            raise ValueError(f"unknown subscription method: {method!r}")
    return methods


class PumpStream:
    """Reconnecting consumer of the free pump.fun data streams."""

    def __init__(
        self,
        url: str = "wss://pumpportal.fun/api/data",
        subscriptions: tuple[str, ...] = DEFAULT_SUBSCRIPTIONS,
        *,
        connect=None,
        reconnect_min_sec: float = 1.0,
        reconnect_max_sec: float = 60.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.url = url
        self.subscriptions = _validate(tuple(subscriptions))
        self.reconnect_min_sec = max(0.1, reconnect_min_sec)
        self.reconnect_max_sec = max(self.reconnect_min_sec, reconnect_max_sec)
        self.sleep = sleep
        self._connect = connect
        self.frames_seen = 0
        self.reconnects = 0
        self.backoff = self.reconnect_min_sec
        self.backoffs_used: list[float] = []

    def _connector(self):
        if self._connect is not None:
            return self._connect
        import websockets  # imported lazily so tests need no network stack

        return websockets.connect

    async def run(
        self, on_launch: Callable[[Launch], Awaitable[None] | None], stop=None
    ) -> None:
        """Consume forever, reconnecting with jittered backoff.

        A dropped socket is normal operation, not an error: the loop reconnects
        and re-subscribes. Jitter matters because every consumer of a public
        stream reconnects at the same instant after a provider restart.
        """
        self.backoff = self.reconnect_min_sec
        while stop is None or not stop():
            delivered = 0
            try:
                async with self._connector()(self.url) as ws:
                    log.info("connected to %s", self.url)
                    for method in self.subscriptions:
                        await ws.send(json.dumps({"method": method}))
                    async for raw in ws:
                        if stop is not None and stop():
                            return
                        self.frames_seen += 1
                        delivered += 1
                        # The backoff resets on a connection that PROVED itself,
                        # not on one that merely opened. A provider that accepts
                        # sockets and drops them instantly - the ordinary shape of
                        # an outage - would otherwise be hammered at the minimum
                        # delay indefinitely.
                        if delivered == 1:
                            self.backoff = self.reconnect_min_sec
                        launch = parse_frame(_decode(raw))
                        result = on_launch(launch)
                        if asyncio.iscoroutine(result):
                            await result
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - any failure means reconnect
                self.reconnects += 1
                log.warning(
                    "stream dropped after %d frames (%s); reconnecting in ~%.1fs",
                    delivered,
                    exc,
                    self.backoff,
                )
            if stop is not None and stop():
                return
            self.backoffs_used.append(self.backoff)
            await self.sleep(self.backoff * (0.5 + random.random()))
            self.backoff = min(self.backoff * 2, self.reconnect_max_sec)


def _decode(raw) -> dict:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {"message": "unparseable frame"}
    return parsed if isinstance(parsed, dict) else {"message": "non-object frame"}
