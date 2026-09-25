# Prediction-Market Research Agent — "Pay for yourself or you die"

**Mode: PAPER TRADING ONLY. No real-money trades are placed, ever, from this log.**

## Mandate

Research prediction markets, identify situations where the agent's estimated
probability differs meaningfully from the current market price, log every
opportunity with evidence, and track what eventually happened.

## Operating constraints (read before trusting anything in this folder)

1. **No live order-book access.** This environment's network policy blocks
   direct access to Polymarket, Kalshi, and Metaculus APIs (verified 2026-09-25:
   `gamma-api.polymarket.com`, `api.elections.kalshi.com`, `www.metaculus.com`
   all denied by the egress proxy). All market prices in this log are **dated
   press citations obtained via web search**, not live quotes. Every price
   carries a source and an as-of date; assume it is stale by hours-to-weeks.
   To upgrade this operation to live quotes, the environment's Network access
   setting needs those API hosts allowed (cloud environment menu → Edit).
2. **The agent's memory is stale.** Model knowledge cutoff is January 2026;
   research date is September 2026. All resolution-relevant facts are sourced
   from live web search, never from memory. Where memory and search conflict,
   search wins.
3. **No fabrication.** If a price, volume, or fact could not be sourced, it is
   marked UNVERIFIED or omitted. Facts and assumptions are labeled.
4. **Honest passes.** A researched market with no meaningful edge is logged as
   PASS. Manufacturing trades to look productive is how paper accounts lie.

## Paper account (assumption, not a fact)

- Starting bankroll: **$10,000 (paper)**, defined 2026-09-25.
- Sizing rule: quarter-Kelly on the agent's own probability estimate, capped at
  10% of bankroll per market, and positions are only "filled" at the last
  *sourced* price. If the real market has moved past that price when checked,
  the fill is voided, not backdated.

## Structure

- `ledger.json` — machine-readable log of every researched market: market ID,
  sourced price + date, agent estimate, verdict (LONG_NO / LONG_YES / PASS),
  paper position, resolution tracking.
- `reports/YYYY-MM-DD-*.md` — dated research reports: the reasoning, evidence
  for and against, confidence levels.

## Confidence scale

- **High** — resolution hinges on an already-verified public fact.
- **Medium** — strong inference from multiple independent sources.
- **Low** — model-based estimate or judgment call; disagreement with the market
  may reflect the agent's own miscalibration.

## Follow-up protocol

Each open entry has a `next_check` date. On each check: refresh the price if a
dated source exists, record resolution when it happens, and score the call
(Brier score vs. the market's implied probability at entry).
