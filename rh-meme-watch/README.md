# rh-meme-watch

Robinhood Chain new-pool Telegram alerter. Every 60 s it polls the public
GeckoTerminal API for newly created DEX pools on the `robinhood` network,
alerts once per pool when liquidity crosses a floor, escalates when a pool
keeps growing, and prominently flags pools paired against tokenized stocks
(the LONG / Bankr / PAIR "stock-paired meme" meta).

Standalone service: no NATS, no pbquantdb, no pbTradeNetV2 coupling.
Host install path: `/opt/pbSolutions/rh-meme-watch/`.

## Rules

| Rule | Behavior |
| --- | --- |
| R1 NEW | pool age ≤ `NEW_WINDOW_MIN` (180 min) AND `reserve_in_usd` ≥ `LIQ_FLOOR` ($150k) AND address never alerted → one alert |
| R2 STOCK-PAIRED | base or quote symbol ∈ `STOCK_SYMBOLS` → `📈 NEW STOCK-PAIRED` prefix, floor drops to `LIQ_FLOOR_STOCK` ($75k) |
| R3 ESCALATE | previously alerted pool with reserve ≥ 2× first-alert reserve OR `volume.h1` ≥ `ESC_VOL_H1` ($500k) → `🔺 ESCALATE`, max once per 6 h per address |
| R4 DUMP | info only: buyers/sellers h1 < 0.7 or reserve down > 50 % vs first alert → `⚠️` line inside escalations and digests |
| Digest | daily 07:00 Europe/Zurich: top 10 pools by h24 volume created in the last 24 h |
| Liquidity lock | escalations and digest entries additionally require the liquidity-lock proxy to pass (see below) and liquidity ≥ `MIN_LIQ` ($20k) |

Dedupe is per pool address; additionally one meme symbol alerts at most once
per 24 h (hot symbols spawn decoy pools — CLIPPY had ≥ 5), unless the decoy
independently passes R1 after the cooldown.

### Handled API quirks (verified against live data, 2026-09-02)

1. `fdv_usd` belongs to the **base** token. When the meme is the quote side
   ("AMZN / WADDLES"), its FDV is resolved from a `<meme>/USDG|WETH` pool via
   `/search/pools` (1 extra request, cached 10 min, ≤ 3 lookups/cycle),
   otherwise shown as `n/a`.
2. `reserve_in_usd` can be **negative** on bankr-robinhood pools → treated as
   unknown, never passes any floor.
3. Decoy pools for hot symbols → address dedupe + 24 h symbol cooldown.
4. `price_change_percentage.h24` is garbage on pools younger than 24 h
   (35 866 %-style values) → alerts show Δ1h for young pools.

Rate budget: 5 fixed requests per cycle (new_pools ×3, top pools ×2) + ≤ 3
FDV lookups = ≤ 8 req/min against a 30 req/min public limit. 429 and the
intermittent new_pools 403 back off 20→40→80 s and skip the cycle without
crashing the loop; the `/data/heartbeat` file is only touched after a fully
successful cycle (the Docker HEALTHCHECK watches its mtime, 5 min threshold).

## Install on the host

```bash
mkdir -p /opt/pbSolutions/rh-meme-watch && cd /opt/pbSolutions/rh-meme-watch
# private repo -> raw.githubusercontent.com needs a token; simplest is a shallow clone:
git clone --depth 1 https://github.com/Pauda-M/rh-meme-watch.git src
cp src/docker-compose.yml src/.env.example .
cp .env.example .env
$EDITOR .env                      # set TELEGRAM_BOT_TOKEN
docker compose pull
docker compose up -d
```

On startup the bot sends `rh-meme-watch up · floor $150k / stock $75k · poll 60s`.
If Telegram auth fails at startup the container exits non-zero (and
`restart: unless-stopped` retries).

## Configuration (env)

| Variable | Default | Notes |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | — | **required**; never committed, never baked into the image |
| `TELEGRAM_CHAT_ID` | `5182460904` | |
| `POLL_SEC` | `60` | |
| `LIQ_FLOOR` | `150000` | USD |
| `LIQ_FLOOR_STOCK` | `75000` | USD, R2 floor |
| `NEW_WINDOW_MIN` | `180` | max pool age for R1 |
| `ESC_VOL_H1` | `500000` | USD, R3 volume trigger |
| `MIN_LIQ` | `20000` | USD, pools below this never appear in digests, escalations or the default dashboard view |
| `REQUIRE_LIQ_LOCK` | `1` | gate escalations + digest entries on the liquidity-lock proxy (`0` disables) |
| `LOCK_MAX_DRAWDOWN` | `0.25` | worst allowed drop from the running peak before liquidity counts as "pulling" |
| `LOCK_MIN_AGE_MIN` | `30` | minutes of recorded history needed before a lock verdict is given |
| `LOCK_MIN_SAMPLES` | `10` | snapshots needed before a lock verdict is given |
| `RPC_URL` | — | Robinhood Chain JSON-RPC endpoint; empty disables all on-chain reads |
| `ONCHAIN_LOOKUPS_PER_CYCLE` | `4` | pools verified on-chain per cycle (oldest-checked first) |
| `ONCHAIN_CACHE_TTL_SEC` | `1800` | how long an on-chain result is reused |
| `CUSTODY_DROP_PCT` | `10` | custodian LP-balance drop (%) that raises 🚨 LP MOVED |
| `LP_CUSTODIANS` | measured default | `addr=label` pairs of known LP custodians |
| `DASHBOARD_PORT` | `8080` | in-container port of the web dashboard, `0` disables |
| `STOCK_SYMBOLS` | AAPL,…,HOOD | CSV, see `.env.example` |
| `LOG_LEVEL` | `INFO` | |
| `TZ` | `Europe/Zurich` | digest timezone |

State lives in SQLite (`/data/state.db`, WAL) in the `rh_meme_watch_data`
volume: `pools` (per-address lifecycle), `alerts` (audit log), `snapshots`
(per-cycle history for alerted pools, kept 14 days) and `onchain` (cached
LP-custody and reserve reads).

## On-chain verification (chain 4663)

With `RPC_URL` set, a few pools per cycle are read directly from the chain
(cached `ONCHAIN_CACHE_TTL_SEC`, oldest-checked first, alerted pools only):

* **LP custody** — for v2-style pools, the LP token's `totalSupply()` plus the
  balances at the burn addresses and at known custodians; unknown holders are
  discovered from the LP token's `Transfer` logs. Stored per pool and shown on
  the dashboard as 🔥 `LP burned`, 🏦 `1 custodian <pct>%`, or 🏦 `dispersed`.
* **🚨 LP MOVED alert** — when a custodian's LP balance falls by more than
  `CUSTODY_DROP_PCT`, which is the actual rug event rather than its price
  aftermath.
* **Reserve verification** — the quote-token balance the pool contract really
  holds (`balanceOf(pool)`), so liquidity can be checked against the chain
  instead of trusted from the API.

### What was measured on 2026-09-12, and why there is no "LP locked" filter

| Finding | Consequence |
| --- | --- |
| **No pool burns LP.** All 12 largest `uniswap-v2-robinhood` pools hold 0.00% of LP at `0x0` and `0xdEaD`. | A "LP burned ≥ X%" filter would match zero pools, permanently. |
| **One contract held 100% of the LP** of every v2 pool sampled (`0x2ac03e14…82f8`). | LP custody does not discriminate between these tokens; they share one custodian. |
| **That custodian is owner-controlled, not time-locked** — its bytecode exposes `owner()` / `transferOwnership()` and no `unlockTime()`; its owner is an EOA. | Liquidity is revocable by a single keyholder, so "locked" would be a false label. |
| **`uniswap-v4` / `bankr` pools use 32-byte pool ids**, and v3 pools hold liquidity as NFT positions. | No fungible LP exists to check; these report `n/a` rather than a guess. |

So this service reports *who custodies the LP and whether that balance moves*,
and never claims liquidity is locked. Note that the RPC rejects requests sent
with Python's default urllib User-Agent, so a real one is always sent.

## Liquidity lock (proxy, not on-chain proof)

True lock state is an **on-chain** property — LP tokens burned to `0x0` or held
by a locker contract — and the GeckoTerminal pool API exposes no such field, so
this service does not claim to read it. Instead it infers the *observable
consequence* of a lock from the reserve history it records itself every cycle:

* liquidity that stays within `LOCK_MAX_DRAWDOWN` (25%) of its **running peak**
  over at least `LOCK_MIN_AGE_MIN` (30 min) and `LOCK_MIN_SAMPLES` (10)
  snapshots, while sitting at or above `MIN_LIQ` ($20k) → 🔒 **locked**
* liquidity that dropped further than that → 🔓 **pulling** (drawdown shown)
* not enough history yet → ⧖ **unproven**, which never counts as locked

The drawdown is measured against the running peak, so an early pull can never
be hidden by a later refill. With `REQUIRE_LIQ_LOCK=1` (default) only 🔒 pools
reach escalations and the daily digest, and the dashboard's default view shows
only them (`/?all=1` shows everything).

**R1/R2 NEW alerts are deliberately NOT gated on this.** A pool minutes old has
no history to judge, so gating new alerts would delay every one of them by at
least half an hour and destroy the point of a 60-second watcher. New alerts stay
fast; the lock filter governs what gets *promoted*.

## Dashboard

The container serves a read-only web dashboard of every detected (alerted)
pool, ranked by a transparent 0-100 **heat** score (45% h1 volume vs the
escalation threshold, 25% buyer/seller flow, 30% liquidity multiple since the
first alert), with a 24h liquidity sparkline per pool, 🔒/🔓/⧖ liquidity-lock
badges, 💣 rug-risk flags and summary tiles. The default view is filtered to
pools passing the liquidity-lock + `MIN_LIQ` filters; `/?all=1` lists every
tracked pool. Routes: `/` (HTML, auto-refresh 60s), `/api/pools` (JSON),
`/healthz`.

`docker-compose.yml` maps it to **`127.0.0.1:8791`** on the host only - open
`http://localhost:8791` on the host, or front it with nginx/tailscale to reach
it remotely (the page is unauthenticated by design, so do not map it to a
public interface directly).

## Development

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/pytest
```

100 tests run offline against `tests/fixture_robinhood_pools.json`
(40 robinhood pools). **Fixture provenance:** the sandbox this project was
authored in had no network egress to `api.geckoterminal.com`, so the fixture
is materialized by CI on the first run: `scripts/refresh_fixture.py` pulls 40
live pools from the API (the GitHub runner has open internet), the full test
suite is re-run against them, and the result is committed. If the live API is
unreachable, the deterministic synthetic seed (`scripts/make_seed_fixture.py`,
marked with a top-level `"provenance"` key and shaped from the verified API
quirks above) is committed instead, and the next push retries the live
upgrade. Locally, generate one with either script if the file is missing.
To refresh from any machine with internet:

```bash
python3 scripts/refresh_fixture.py && git add tests/fixture_robinhood_pools.json && git commit -m "refresh fixture"
```

## CI / packaging

- `.github/workflows/build.yml` (standalone repo): push to `main` → pytest →
  build → push `ghcr.io/pauda-m/rh-meme-watch:latest` using `GITHUB_TOKEN`
  (no PAT).
- `Dockerfile`: python:3.12-slim, non-root user, heartbeat HEALTHCHECK.
- `docker-compose.yml`: `restart: unless-stopped`, `env_file: .env`,
  named volume on `/data`, `mem_limit: 128m`, no ports.

## Transplanting into the standalone Pauda-M/rh-meme-watch repo

This project was delivered on a branch of `Pauda-M/websites` because the
build session's GitHub credentials cannot create repositories. To move it
into its own private repo (one-time, from any machine with git access):

```bash
# 1. create the empty private repo Pauda-M/rh-meme-watch on GitHub (no README)
git clone --branch claude/rh-meme-watch-alerter-rgq04l https://github.com/Pauda-M/websites.git /tmp/websites-rhmw
cd /tmp/websites-rhmw/rh-meme-watch
git init -b main
git add -A
git commit -m "rh-meme-watch v0.1.0"
git remote add origin git@github.com:Pauda-M/rh-meme-watch.git
git push -u origin main        # triggers build.yml: tests + GHCR image
```

## Out of scope

Trading, wallets, on-chain reads, holder distribution.
