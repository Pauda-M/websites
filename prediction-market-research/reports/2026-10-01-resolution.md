# Resolution check — 2026-10-01

## First resolved call: shutdown market — agent correct

Kalshi `KXGOVTSHUTDOWN-26OCT01` finalized at 13:37 UTC. Outcome: **NO** —
the government is funded through Dec 11 under the CR signed Sep 2; no lapse
at the 10:00 ET resolution timestamp.

| Forecast | P(yes) | Brier |
|---|---|---|
| Agent (Sep 25) | 0.5% | **0.000025** |
| Stale press quote used at entry | 4% | 0.0016 |
| Live book at first poll (Sep 25) | ~1% | ~0.0001 |

No P&L — the paper fill was voided on day one (stale quote). The score is
calibration-only, and one resolved call proves nothing on its own; it goes
into the running tally.

## Fed market: whipsaw through both agent estimates

Soft August core PCE (Sep 30: 0.2% m/m vs 0.3% expected, 3.0% y/y — CNBC)
cut October hike odds. Polymarket "another hike 2026": 90.5 (Sep 28) →
**81.5** today.

The uncomfortable entry in the log: the NO re-entry declined on Sep 28 at
~9.5c marks ~18.5c today. The Sep-28 reasoning ("the market led, the model
lagged") was itself a capitulation at the local extreme. Conclusion that
survives both whipsaws: this agent's Fed estimates have ~±8 points of noise,
so no gap under ~10 points is a trade. Estimate reset to 0.78 vs market
81.5. Still flat, still correct to be.

## Book

Flat. BTC $100K steady at 36/37 vs agent 42% (next look Oct 5). Feed
healthy — 6 days of 5-minute polls without a gap.
