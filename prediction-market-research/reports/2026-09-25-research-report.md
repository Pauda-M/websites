# Research Report — 2026-09-25

Agent: "Pay for yourself or you die" · Mode: **PAPER TRADING ONLY**

Data channel this session: web search citations only. Direct Polymarket /
Kalshi / Metaculus API access is blocked by the environment's network policy
(verified today — all three hosts denied by the egress proxy). Every price
below is a dated press quote, flagged where the date could not be verified.

---

## Opportunity 1 — Government shutdown on Oct 1, 2026 (Kalshi)

**Verdict: LONG NO (paper). Confidence: HIGH on direction, LOW on fill.**

| | |
|---|---|
| Market | `KXGOVTSHUTDOWN-26OCT01` — resolves YES only if part of the government is shut down at 10:00 a.m. ET on Oct 1, 2026 |
| Last sourced price | **4¢ YES** (Yahoo News headline; date unverified, post-CR-signing). Mid-August: 15–16¢. End of July: ~35¢. |
| Agent estimate | **~0.5% YES** |
| Edge | ~3.5 points on NO — *if* the 4¢ quote still holds |

**The controlling fact [Certain, multiply sourced]:** H.R. 6500, the
"Continuing Appropriations and Extensions Act, 2027," was **signed into law on
September 2, 2026**, funding the government through **December 11, 2026**
(White House briefing statement; The Hill; Fox News; NAGGL; SpacePolicyOnline).
Margins were veto-proof anyway: Senate 90–6, House 370–48. There is no funding
lapse possible on Oct 1 under current law.

**Why the market might still show 4%:** longshot bias plus dead-money decay —
retail YES holders don't get cashed out until resolution, and nobody market-makes
the last few cents tightly. This is the classic near-certainty discount, not
information.

**Evidence supporting NO:** CR signed 4 weeks before the deadline; explicitly
covers the Oct 1 date; both chambers on recess-adjacent autopilot until the
Dec 11 fight.

**Evidence against / residual tail:** [Guessing] exotic executive-action
scenarios (rescission gambits, an agency operating lapse engineered despite
appropriations) could arguably furlough parts of an agency — but the Kalshi
contract requires a *shutdown* condition at a specific timestamp; none of the
reporting suggests any such move in flight. I price the tail at 0.5%.

**Paper position:** 1,000 NO @ 96¢ ($960 at risk to make $40, ~4.2% in 6 days).
**Fill voided if YES has already collapsed below 2¢** — below that, fees eat
the edge. This position is really a calibration exercise: the honest note is
that the 4¢ quote is probably stale and the live market is likely 1–2¢ already.

---

## Opportunity 2 — Another Fed rate hike in 2026 (Polymarket)

**Verdict: LONG NO (paper), small. Confidence: LOW-MEDIUM.**

| | |
|---|---|
| Market | Polymarket "another Fed hike in 2026" (post-September; remaining meetings: October and December) |
| Last sourced price | **84% YES** (Crypto Briefing, post-Sep-16 FOMC; exact date unverified) |
| Agent estimate | **~76% YES** |
| Edge | ~8 points on NO |

**Context [Certain]:** The FOMC hiked 25bps on Sep 16, 2026, unanimously
(12–0), to 3.75–4.00% (American Banker live blog; Kiplinger). August CPI:
+0.4% m/m, 3.4% y/y headline; core +0.3% m/m, hotter than expected (CNBC,
Sep 11). Oil near $100/bbl. Chair Warsh has been hawkish since Jackson Hole.

**My arithmetic [Likely]:** CME FedWatch put an **October hike at ~58%** as of
Sep 18 (CNBC). For NO to win, both October and December must pass without a
hike. Conditional on an October skip (which would most plausibly happen
because data softened), December is not a coin flip up — I put it at ~40–45%.
P(at least one more hike) ≈ 1 − 0.42 × 0.58 ≈ **76%**, range 72–80%.

**Evidence supporting my lower number:** the futures curve itself (58% Oct);
the dot plot shows only *four* participants projecting two additional 2026
hikes — the committee median implies one more hike total was already delivered
in September or barely one more; three months of data (two CPIs, two jobs
reports) is a lot of room for the hiking case to crack.

**Evidence against me (take this seriously):** Polymarket ran hawkish of Fed
futures all summer (53% vs 32% in early summer per KuCoin) and **Polymarket
was right** — the September hike happened. Goldman *and* BofA both added an
October hike to their forecasts; BofA expects December too. Warsh explicitly
rejected the "restrictive relative to neutral" framing at the presser, which
reads as a chair not looking for reasons to stop. If Polymarket's hawkish skew
is informed rather than crowd bias, my 76% is the miscalibrated number.

**Paper position:** 1,500 NO @ 16¢ ($240 at risk). Sized well below Kelly
because the disagreement is 8 points against a market that recently out-called
me-shaped reasoning. Fill voided if YES < 80¢ at verification.

---

## Opportunity 3 — Bitcoin tops $100K before end of 2026 (Kalshi)

**Verdict: PASS — no meaningful edge. Confidence in the pass: MEDIUM.**

| | |
|---|---|
| Market | Kalshi BTC range/threshold complex — "top $100,000 before year-end" |
| Sourced price | **46% YES** (Bitcoin.com News, **Sep 23, 2026**; ~$4.8M across seven strikes) |
| Spot | **BTC = $84,413** at 9 a.m. ET Sep 25 (Fortune), down ~$24.6K y/y |
| Agent estimate | **~42% YES** |

**Model [Guessing, labeled as such]:** GBM barrier-touch probability, 97 days
to year-end, log-distance to $100K = 0.169:

| Annualized vol | Drift 0 | Drift −20%/yr | Drift −40%/yr |
|---|---|---|---|
| 40% | 41% | 33% | 25% |
| 50% | 51% | 44% | 38% |
| 60% | 58% | 53% | 47% |

The market's 46% sits in the middle of the plausible grid. My bearish tilt
(hiking cycle, oil-driven macro, BTC in a downtrend all year, "not this month"
even per Kalshi's own $90K September strike at 39%) pushes me to ~42%, but
that is a **model disagreement, not an information edge**. I don't know
realized vol in this regime; at 55%+ vol the market is *cheap* and my tilt is
wrong-signed. A 4-point gap inside my own error bars is not a trade.

Logged as WATCHING. If BTC breaks below ~$75K with the market still >35%, or
above $95K with the market <60%, re-underwrite.

---

## Meta-notes (what would make this operation actually pay for itself)

1. **The binding constraint is data, not analysis.** With API hosts allowed in
   the environment's network policy, this agent could scan hundreds of markets
   for stale-quote/near-certainty discounts (Opportunity 1's shape) instead of
   hand-researching three. That's where the systematic edge lives.
2. All three of today's edges are small. That is the expected result of honest
   work in liquid markets, and it is worth stating: **nothing found today
   would "pay for itself" after fees at real size.** The shutdown trade is
   ~free money but capped at pennies; the Fed trade is a genuine disagreement
   with a market that was recently right.

## Sources

- [The Hill — Trump signs stopgap funding bill into law](https://thehill.com/homenews/administration/6067996-trump-stopgap-funding-law-government-shutdown/)
- [White House — H.R. 6500 signed into law](https://www.whitehouse.gov/briefings-statements/2026/09/congressional-bill-h-r-6500-signed-into-law/)
- [Fox News — Government shutdown averted](https://www.foxnews.com/politics/trump-signs-government-funding-bill-avoiding-shutdown-ahead-midterms)
- [Yahoo — Betting Odds of Government Shutdown 2026 Crashes to 4% on Kalshi](https://www.yahoo.com/news/politics/articles/betting-odds-government-shutdown-2026-105637438.html)
- [CryptoNews — Government Shutdown Odds: Kalshi, Polymarket Diverge](https://cryptonews.com/news/government-shutdown-odds-kalshi-polymarket/)
- [CNBC — CPI inflation report August 2026](https://www.cnbc.com/2026/09/11/cpi-inflation-report-august-2026.html)
- [CNBC — Three words from Kevin Warsh… (FedWatch Oct ~58%)](https://www.cnbc.com/2026/09/18/three-words-from-kevin-warsh-have-wall-street-wondering-how-far-the-fed-will-go-with-rate-hikes.html)
- [American Banker — FOMC September 2026 press conference live coverage](https://www.americanbanker.com/live-blog/federal-open-market-committee-press-conference-september-2026-live-coverage)
- [Crypto Briefing — Polymarket shows 84% odds of another Fed hike in 2026](https://cryptobriefing.com/polymarket-fed-rate-hike-2026-odds/)
- [KuCoin — Polymarket 53% vs futures 32% on September hike](https://www.kucoin.com/news/flash/polymarket-prices-53-odds-of-fed-rate-hike-in-september-2026-vs-32-in-futures)
- [Bitcoin.com News — Kalshi: BTC $97K peak, 46% for $100K](https://news.bitcoin.com/crypto-news/kalshi-bitcoin-price-97k-peak-2026-100k-odds/)
- [Fortune — Price of Bitcoin, Sep 25, 2026](https://fortune.com/article/price-of-bitcoin-09-25-2026/)
