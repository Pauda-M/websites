#!/usr/bin/env python3
"""Refresh tests/fixture_robinhood_pools.json from the live GeckoTerminal API.

Pulls 2 pages (40 pools) of /networks/robinhood/pools?sort=h24_volume_usd_desc
and writes them verbatim into the fixture file, replacing the committed seed.
Stdlib only, so it runs on any machine (or CI runner) with open internet:

    python3 scripts/refresh_fixture.py

The build sandbox that authored this repo had no egress to api.geckoterminal.com,
so the committed seed fixture is synthetic (marked with a top-level "provenance"
key). Running this script replaces it with real API output and drops the marker;
the branch CI refresh job does exactly that and commits the result.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://api.geckoterminal.com/api/v2"
HEADERS = {
    "accept": "application/json;version=20230302",
    "user-agent": "rh-meme-watch-fixture/0.1 (github.com/Pauda-M/rh-meme-watch)",
}
PAGES = 2
MIN_POOLS = 30
FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixture_robinhood_pools.json"


def fetch(url: str, attempts: int = 4) -> dict:
    delay = 10.0
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429, 500, 502, 503, 504) and attempt < attempts:
                print(f"HTTP {exc.code} on {url}, retrying in {delay:.0f}s", file=sys.stderr)
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < attempts:
                print(f"{exc!r} on {url}, retrying in {delay:.0f}s", file=sys.stderr)
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError("unreachable")


def main() -> int:
    items: list[dict] = []
    for page in range(1, PAGES + 1):
        url = f"{BASE}/networks/robinhood/pools?sort=h24_volume_usd_desc&page={page}"
        payload = fetch(url)
        page_items = payload.get("data") or []
        print(f"page {page}: {len(page_items)} pools", file=sys.stderr)
        items.extend(page_items)
        time.sleep(2.5)  # stay far under the 30 req/min public limit

    if len(items) < MIN_POOLS:
        print(f"only {len(items)} pools fetched (< {MIN_POOLS}); refusing to write", file=sys.stderr)
        return 1
    for item in items:
        attrs = item.get("attributes") or {}
        if not item.get("id") or not attrs.get("name"):
            print("malformed pool item in API response; refusing to write", file=sys.stderr)
            return 1

    FIXTURE.write_text(json.dumps({"data": items}, indent=1) + "\n")
    print(f"wrote {len(items)} live pools to {FIXTURE}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
