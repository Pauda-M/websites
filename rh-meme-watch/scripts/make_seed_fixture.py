#!/usr/bin/env python3
"""Deterministic generator for the synthetic seed fixture.

Used as a fallback when scripts/refresh_fixture.py cannot reach the live
GeckoTerminal API; encodes the verified 2026-09-02 robinhood-network quirks
(negative bankr reserves, CLIPPY decoys, garbage h24 pct on young pools,
stock-as-base names). The seed is marked with a top-level "provenance" key
so CI keeps trying to replace it with live data.
"""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixture_robinhood_pools.json"


def hx(seed: str) -> str:
    return "0x" + hashlib.sha256(seed.encode()).hexdigest()[:40]


def tx(buys, sells, buyers, sellers):
    return {"buys": buys, "sells": sells, "buyers": buyers, "sellers": sellers}


def pool(i, name, dex, created, reserve, fdv, mcap, vol_h1, vol_h24, pct_h1, pct_h24,
         t1=None, t24=None, price="0.0001230045", no_h1_tx=False):
    base_seed = f"base-{i}-{name}"
    quote_seed = f"quote-{i}-{name}"
    transactions = {
        "m5": tx(3, 1, 3, 1),
        "m15": tx(9, 4, 8, 4),
        "m30": tx(21, 9, 18, 8),
        "h1": t1 or tx(120, 95, 60, 48),
        "h6": tx(500, 410, 220, 180),
        "h24": t24 or tx(1900, 1500, 700, 560),
    }
    if no_h1_tx:
        transactions.pop("h1")
    return {
        "id": f"robinhood_{hx(f'pool-{i}-{name}')}",
        "type": "pool",
        "attributes": {
            "base_token_price_usd": price,
            "base_token_price_native_currency": "0.000000031",
            "quote_token_price_usd": "1.0002",
            "quote_token_price_native_currency": "0.00025",
            "base_token_price_quote_token": "0.000123",
            "quote_token_price_base_token": "8130.1",
            "address": hx(f"pool-{i}-{name}"),
            "name": name,
            "pool_name": name,
            "pool_fee_percentage": None,
            "pool_created_at": created,
            "fdv_usd": fdv,
            "market_cap_usd": mcap,
            "price_change_percentage": {
                "m5": "0.4", "m15": "1.1", "m30": "2.5",
                "h1": pct_h1, "h6": "12.0", "h24": pct_h24,
            },
            "transactions": transactions,
            "volume_usd": {
                "m5": "1200.5", "m15": "4100.2", "m30": "9400.9",
                "h1": vol_h1, "h6": "160000.0", "h24": vol_h24,
            },
            "reserve_in_usd": reserve,
        },
        "relationships": {
            "base_token": {"data": {"id": f"robinhood_{hx(base_seed)}", "type": "token"}},
            "quote_token": {"data": {"id": f"robinhood_{hx(quote_seed)}", "type": "token"}},
            "dex": {"data": {"id": dex, "type": "dex"}},
        },
    }


UNI = "uniswap-v4"
BANKR = "bankr-robinhood"
D = []
# --- the five named stock-paired pools the task pins ---
D.append(pool(1, "AI / NVDA", UNI, "2026-08-29T14:02:11Z", "2400000.55", "18500000.0", None, "310500.2", "8200000.9", "18.2", "42.7"))
D.append(pool(2, "MOO / MU", UNI, "2026-08-30T08:41:03Z", "612000.11", "2900000.0", "2100000.0", "88000.4", "1900000.2", "-4.2", "11.9"))
D.append(pool(3, "BONER / HIMS", UNI, "2026-08-28T21:17:45Z", "893000.02", "5100000.0", None, "141000.7", "2600000.5", "7.7", "-9.4"))
D.append(pool(4, "AAPLCAT / AAPL", UNI, "2026-08-31T11:55:29Z", "431000.9", "1600000.0", None, "64000.1", "990000.3", "22.4", "310.2"))
D.append(pool(5, "CLIPPY / MSFT", UNI, "2026-08-30T16:24:52Z", "1910000.33", "9400000.0", "8100000.0", "422000.8", "5600000.1", "31.5", "88.0"))
# --- CLIPPY decoys (hot symbols spawn decoy pools; >=5 CLIPPY pools total) ---
D.append(pool(6, "CLIPPY / MSFT", UNI, "2026-09-01T22:03:14Z", "5100.4", "9400000.0", None, "900.2", "14000.7", "3.1", "1200.5"))
D.append(pool(7, "CLIPPY / MSFT", BANKR, "2026-09-02T01:12:40Z", "812.9", "9400000.0", None, "120.0", "2200.4", "-8.8", "540.1"))
D.append(pool(8, "CLIPPY / WETH", UNI, "2026-09-01T19:44:09Z", "12400.6", "9400000.0", None, "3100.5", "45000.2", "1.9", "780.3"))
D.append(pool(9, "CLIPPY / USDG", UNI, "2026-09-01T13:37:56Z", "68000.2", "9400000.0", None, "15400.9", "230000.6", "-2.4", "95.7"))
# --- stock as BASE, meme as QUOTE ---
D.append(pool(10, "AMZN / WADDLES", UNI, "2026-08-31T06:20:33Z", "241000.5", "245000000000.0", None, "56000.3", "870000.8", "5.5", "14.2"))
# --- meme as base vs stock (the task's format example) ---
D.append(pool(11, "AAPLDOG / AAPL", UNI, "2026-09-02T06:19:00Z", "118000.44", "440000.0", None, "212000.5", "212000.5", "311.0", "35866.2",
              t1=tx(1204, 980, 301, 288)))
# --- bankr pools with NEGATIVE reserve_in_usd (verified API quirk) ---
D.append(pool(12, "BNKRDOG / WETH", BANKR, "2026-09-01T23:58:21Z", "-3421.77", "310000.0", None, "45000.1", "160000.9", "44.1", "5120.8"))
D.append(pool(13, "GROKCOIN / USDG", BANKR, "2026-09-02T03:11:02Z", "-0.01", "125000.0", None, "8100.6", "22000.3", "-12.5", "980.4"))
# --- young pool with garbage h24 price change ---
D.append(pool(14, "TSLADOG / TSLA", UNI, "2026-09-02T05:40:10Z", "205000.7", "760000.0", None, "98000.2", "101000.5", "42.3", "35866.0"))
# --- tokenized stock / stable & gold pools (no meme side) ---
D.append(pool(15, "AMZN / USDG", UNI, "2026-08-15T10:00:00Z", "5400000.0", "245000000000.0", None, "1200000.4", "22000000.7", "0.8", "1.9"))
D.append(pool(16, "gld / USDG", UNI, "2026-08-10T09:30:00Z", "980000.0", "18000000000.0", None, "310000.2", "2900000.1", "0.2", "0.9"))
D.append(pool(17, "TSLA / USDG", UNI, "2026-08-12T14:45:00Z", "3900000.0", "1080000000000.0", None, "890000.9", "16500000.2", "-1.1", "2.4"))
# --- fee-suffix name variant ---
D.append(pool(18, "MOONPIG / AAPL 0.3%", UNI, "2026-08-31T18:22:47Z", "156000.8", "890000.0", None, "34000.4", "410000.6", "9.9", "120.7"))
# --- HOOD-paired ---
D.append(pool(19, "HOODCAT / HOOD", UNI, "2026-08-30T12:12:12Z", "324000.1", "1400000.0", None, "71000.8", "1200000.4", "14.8", "33.1"))
# --- plain memes vs WETH / USDG ---
names = [
    ("PEPE / WETH", "2026-08-29T10:10:10Z", "740000.3", "3200000.0", "190000.5", "2100000.8"),
    ("WADDLES / USDG", "2026-08-30T20:20:20Z", "410000.6", "1900000.0", "84000.2", "1150000.9"),
    ("DOGWIFHOOD / WETH", "2026-09-01T09:09:09Z", "265000.9", "980000.0", "51000.7", "640000.3"),
    ("RHINU / USDG", "2026-08-28T17:35:00Z", "188000.2", "720000.0", "23000.9", "390000.1"),
    ("SNEK / WETH", "2026-09-01T15:26:38Z", "97000.5", "455000.0", "17800.3", "210000.4"),
    ("CHAD / USDG", "2026-08-31T23:47:19Z", "154000.7", "610000.0", "29000.6", "330000.2"),
    ("GIGA / WETH", "2026-09-02T02:02:02Z", "176000.4", "830000.0", "62000.1", "88000.8"),
    ("FROGGO / USDG", "2026-08-30T05:55:44Z", "132000.8", "540000.0", "12000.4", "260000.5"),
    ("HODLCAT / WETH", "2026-08-29T19:08:27Z", "88000.1", "310000.0", "9100.2", "150000.7"),
    ("YOLO / USDG", "2026-09-01T11:31:53Z", "203000.3", "915000.0", "41000.5", "480000.9"),
]
for j, (nm, created, res, fdv, v1, v24) in enumerate(names, start=20):
    D.append(pool(j, nm, UNI, created, res, fdv, None, v1, v24, "6.2", "19.5"))
# --- more stock-paired memes for variety ---
more = [
    ("NVDAPUP / NVDA", "2026-08-31T13:13:13Z", "268000.4", "1200000.0", "58000.2", "760000.6"),
    ("SPYCAT / SPY", "2026-09-01T07:07:07Z", "142000.9", "530000.0", "26000.8", "310000.2"),
    ("METAMOON / META", "2026-08-30T15:15:15Z", "221000.6", "870000.0", "39000.1", "540000.8"),
    ("PLTRDOG / PLTR", "2026-09-01T21:21:21Z", "96000.3", "365000.0", "14000.7", "175000.4"),
    ("GMEFROG / GME", "2026-08-29T04:44:04Z", "184000.5", "690000.0", "31000.9", "420000.1"),
]
for j, (nm, created, res, fdv, v1, v24) in enumerate(more, start=30):
    D.append(pool(j, nm, UNI, created, res, fdv, None, v1, v24, "8.4", "27.3"))
# --- edge cases: null created_at, null fdv, missing h1 transactions, null reserve ---
D.append(pool(35, "GHOST / WETH", UNI, None, "125000.0", None, None, "8000.0", "95000.0", None, None))
D.append(pool(36, "NOFDV / USDG", UNI, "2026-09-01T16:16:16Z", "168000.2", None, None, "21000.3", "240000.6", "4.4", "18.8"))
D.append(pool(37, "NOTX / WETH", UNI, "2026-08-31T02:22:42Z", "111000.9", "480000.0", None, "6000.1", "82000.3", "2.2", "9.6", no_h1_tx=True))
D.append(pool(38, "NORES / USDG", UNI, "2026-09-01T18:45:36Z", None, "260000.0", None, "5000.4", "61000.2", "1.5", "7.1"))
D.append(pool(39, "ZERORES / WETH", BANKR, "2026-09-02T04:24:48Z", "0", "140000.0", None, "2000.2", "18000.5", "-3.3", "44.9"))
D.append(pool(40, "LASTCAT / USDG", UNI, "2026-08-28T08:18:28Z", "301000.4", "1150000.0", None, "47000.6", "660000.3", "5.9", "16.4"))

assert len(D) == 40, len(D)
addresses = [p["id"] for p in D]
assert len(set(addresses)) == 40

doc = {
    "provenance": (
        "synthetic-seed 2026-09-02: shaped from GeckoTerminal API v2 pool objects and the "
        "verified robinhood-network quirks (negative bankr reserves, decoy CLIPPY pools, "
        "garbage h24 pct on young pools, stock-as-base names). Replace with live data via "
        "scripts/refresh_fixture.py (the branch CI refresh-fixture job does this automatically)."
    ),
    "data": D,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(doc, indent=1) + "\n")
print(f"wrote {len(D)} pools -> {OUT}")
