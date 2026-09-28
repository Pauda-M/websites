# Mid-window check — 2026-09-28 (day 3 of paper watch)

Live source: on-server poller (prices.json, 2026-09-28T15:59:46Z). Feed healthy
since Sep 25; three markets polled every 5 min without gaps.

## Book status: flat (both Sep-25 fills voided on first live contact)

| Market | Sep 25 live | Sep 28 live | Agent est. | Note |
|---|---|---|---|---|
| Shutdown Oct 1 (Kalshi) | 0 / 1c | 0 / 1c | 0.5% | Resolves Oct 1; Brier scoring then |
| Another Fed hike 2026 (Polymarket) | 90 / 91 | 90 / 91 | **0.76 → 0.85** | Re-underwritten, see below |
| BTC $100K 2026 (Kalshi) | 38 / 39 | 35 / 36 | 42% | Market now 6-7 pts below agent |

## Fed re-underwrite — no re-entry

[Likely] FedWatch put October at ~73% by Sep 23 (post-Barr, hot inflation
tail); dot-plot median implies one more 2026 hike. P(>=1 more hike) =
1 − 0.27 × ~0.53 ≈ 0.85. The market's 90.5% was 9 pts ahead of my Friday
number and I moved toward it, not vice versa. A model that lags the market
by that much in 72 hours has no claim to a 5-pt residual disagreement —
buying NO at 10c here would be paying for my own miscalibration. PASS.
PCE (Sep 30) and the October meeting are the next information events.

## Real-money frictions (what paper still hides)

- Kalshi fee 0.07 × P × (1−P): at the shutdown market's 1c price, ~0.07c per
  contract — 7% of the entire remaining edge. Near-certainty scalps are
  fee-dominated; that trade was marginal even before it voided.
- Polymarket Fed NO: 1c spread on a ~10c contract = 10% of notional lost to
  crossing; unmodeled gas/relayer costs on top.
- BTC strikes: 1c spread on 35c is the cheapest friction of the three
  (~3%), which is one reason the BTC market is the only one still worth
  watching for an entry.

## Verdict for the 2-4 day window so far

Zero paper P&L, by design: every apparent edge so far was either stale data
(both voided fills) or my own lag (Fed). Nothing here would have made real
money; a naive paper account using press quotes would be showing a fake
+$40-100. Resolution scoring starts Oct 1 (shutdown call: agent 0.5% vs
market's ~1c).
