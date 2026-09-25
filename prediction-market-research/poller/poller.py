#!/usr/bin/env python3
"""Live price poller for the prediction-market research dashboard.

PAPER MODE ONLY: this process reads public market data and writes JSON files.
It places no orders, holds no keys, and has no write access to anything but
its output directory.

Reads /config/markets.json, polls Kalshi and Polymarket public APIs, writes
<out>/prices.json (atomic replace) for the dashboard and appends one line per
poll cycle to <data>/history.jsonl for later calibration scoring.

Stdlib only — no pip dependencies.
"""
import json
import os
import sys
import tempfile
import time
import urllib.request

CONFIG_PATH = os.environ.get("PM_CONFIG", "/config/markets.json")
OUT_PATH = os.environ.get("PM_OUT", "/www/prices.json")
HIST_PATH = os.environ.get("PM_HIST", "/data/history.jsonl")
INTERVAL_S = int(os.environ.get("PM_POLL_SECONDS", "300"))

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA_BASE = "https://gamma-api.polymarket.com"


def get_json(url: str):
    req = urllib.request.Request(
        url, headers={"User-Agent": "pm-research-paper-poller/1.0 (read-only)"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def poll_kalshi(ticker: str) -> dict:
    # This deployment's API returns decimal-dollar strings (yes_bid_dollars);
    # fall back to the integer-cent fields older deployments use.
    m = get_json(f"{KALSHI_BASE}/markets/{ticker}")["market"]

    def price(dollars_key, cents_key):
        v = m.get(dollars_key)
        if v not in (None, ""):
            return round(float(v), 4)
        v = m.get(cents_key)
        return None if v in (None, "") else round(v / 100.0, 4)

    return {
        "yes_bid": price("yes_bid_dollars", "yes_bid"),
        "yes_ask": price("yes_ask_dollars", "yes_ask"),
        "last": price("last_price_dollars", "last_price"),
        "volume": m.get("volume_fp") or m.get("volume"),
        "status": m.get("status"),
        "close_time": m.get("close_time"),
        "source": f"kalshi:{ticker}",
    }


def poll_polymarket(slug: str) -> dict:
    markets = get_json(f"{GAMMA_BASE}/markets?slug={slug}")
    if not markets:
        raise ValueError(f"no polymarket market for slug {slug}")
    m = markets[0]
    yes_last = None
    prices = m.get("outcomePrices")
    if prices:
        if isinstance(prices, str):
            prices = json.loads(prices)
        yes_last = round(float(prices[0]), 4)
    fnum = lambda v: None if v in (None, "") else round(float(v), 4)
    return {
        "yes_bid": fnum(m.get("bestBid")),
        "yes_ask": fnum(m.get("bestAsk")),
        "last": yes_last,
        "volume": fnum(m.get("volumeNum")),
        "status": "closed" if m.get("closed") else "open",
        "close_time": m.get("endDate"),
        "source": f"polymarket:{slug}",
    }


def poll_once(cfg: list) -> dict:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out = {"as_of": now, "mode": "PAPER_TRADING_ONLY", "markets": {}}
    for entry in cfg:
        ledger_id = entry["ledger_id"]
        try:
            if entry["venue"] == "kalshi":
                quote = poll_kalshi(entry["kalshi_ticker"])
            elif entry["venue"] == "polymarket":
                quote = poll_polymarket(entry["poly_slug"])
            else:
                raise ValueError(f"unknown venue {entry['venue']}")
            quote["fetched_at"] = now
            out["markets"][ledger_id] = quote
        except Exception as exc:  # keep polling the rest; record the failure
            out["markets"][ledger_id] = {"error": str(exc), "fetched_at": now}
    return out


def write_atomic(path: str, payload: dict) -> None:
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(payload, f, indent=1)
    os.chmod(tmp, 0o644)  # mkstemp defaults to 0600, unreadable by the nginx worker
    os.replace(tmp, path)


def main() -> None:
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    print(f"pm-poller: {len(cfg)} markets, every {INTERVAL_S}s -> {OUT_PATH}", flush=True)
    while True:
        snapshot = poll_once(cfg)
        write_atomic(OUT_PATH, snapshot)
        try:
            with open(HIST_PATH, "a") as f:
                f.write(json.dumps(snapshot) + "\n")
        except OSError as exc:
            print(f"pm-poller: history write failed: {exc}", file=sys.stderr, flush=True)
        errs = [k for k, v in snapshot["markets"].items() if "error" in v]
        print(f"pm-poller: {snapshot['as_of']} ok={len(snapshot['markets']) - len(errs)} err={len(errs)}"
              + (f" ({errs})" if errs else ""), flush=True)
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    main()
