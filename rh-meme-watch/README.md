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
| `STOCK_SYMBOLS` | AAPL,…,HOOD | CSV, see `.env.example` |
| `LOG_LEVEL` | `INFO` | |
| `TZ` | `Europe/Zurich` | digest timezone |

State lives in SQLite (`/data/state.db`, WAL) in the `rh_meme_watch_data`
volume: `pools` (per-address lifecycle) and `alerts` (audit log).

## Development

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/pytest
```

62 tests run offline against `tests/fixture_robinhood_pools.json`
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
