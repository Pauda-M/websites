#!/usr/bin/env python3
"""Capture raw pump.fun websocket frames so the parser can be built from real data.

This is a throwaway reconnaissance tool, not part of the service. It connects to
a candidate endpoint, tries a few subscription shapes, dumps every frame it
receives to JSONL, and prints a field-frequency summary of what actually arrived.

Nothing about the message schema is assumed. The point is to find out.

Usage:
    python3 probe_wss.py                      # try the default candidates
    python3 probe_wss.py --url wss://host/p   # a specific endpoint
    python3 probe_wss.py --seconds 120 --out /tmp/pf.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

try:
    import websockets
except ImportError:
    sys.exit("need: pip install websockets")

# Candidates to try, in order. These are guesses - the probe exists to find out
# which (if any) is live and what it actually sends.
CANDIDATES = [
    "wss://pumpportal.fun/api/data",
    "wss://frontend-api.pump.fun/socket.io/?EIO=4&transport=websocket",
    "wss://pumpportal.fun/api/data?",
]

# Subscription shapes to attempt once connected. Unknown methods are usually
# ignored or answered with an error, both of which are useful information.
SUBSCRIBES = [
    {"method": "subscribeNewToken"},
    {"method": "subscribeMigration"},
    {"method": "subscribeTokenTrade", "keys": []},
]

USER_AGENT = "pf-meme-watch-probe/0.1"


def summarize(path: Path) -> None:
    """Field frequencies and a couple of sample frames - enough to write models."""
    frames = []
    for line in path.read_text().splitlines():
        try:
            frames.append(json.loads(line))
        except ValueError:
            continue
    if not frames:
        print("\nno frames captured")
        return

    print(f"\n=== {len(frames)} frames captured ===")
    keys = Counter()
    for f in frames:
        if isinstance(f, dict):
            keys.update(f.keys())
    print("\ntop-level fields (count):")
    for k, n in keys.most_common(40):
        print(f"  {n:6d}  {k}")

    # Show the shape of the most complete frame, with values truncated.
    best = max((f for f in frames if isinstance(f, dict)), key=len, default=None)
    if best:
        print("\nrichest frame:")
        for k, v in sorted(best.items()):
            text = json.dumps(v)
            print(f"  {k:28s} = {text[:70]}{'...' if len(text) > 70 else ''}")


async def probe(url: str, seconds: int, out: Path) -> int:
    print(f"\n--- connecting: {url}")
    count = 0
    try:
        async with websockets.connect(
            url,
            additional_headers={"User-Agent": USER_AGENT},
            open_timeout=15,
            ping_interval=20,
        ) as ws:
            print("    connected")
            for sub in SUBSCRIBES:
                await ws.send(json.dumps(sub))
                print(f"    sent: {json.dumps(sub)}")

            deadline = time.time() + seconds
            with out.open("a") as fh:
                while time.time() < deadline:
                    try:
                        raw = await asyncio.wait_for(
                            ws.recv(), timeout=max(1, deadline - time.time())
                        )
                    except asyncio.TimeoutError:
                        break
                    count += 1
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", "replace")
                    fh.write(raw.strip() + "\n")
                    if count <= 3:
                        print(f"    frame {count}: {raw[:220]}")
    except Exception as exc:  # noqa: BLE001 - reconnaissance, report everything
        print(f"    FAILED: {type(exc).__name__}: {exc}")
    print(f"    {count} frames from {url}")
    return count


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", action="append", help="endpoint (repeatable)")
    ap.add_argument("--seconds", type=int, default=45)
    ap.add_argument("--out", default="/tmp/pf_frames.jsonl")
    args = ap.parse_args()

    out = Path(args.out)
    out.write_text("")
    total = 0
    for url in args.url or CANDIDATES:
        total += await probe(url, args.seconds, out)
        if total:
            break  # first endpoint that talks wins

    print(f"\nwrote {out}")
    summarize(out)


if __name__ == "__main__":
    asyncio.run(main())
