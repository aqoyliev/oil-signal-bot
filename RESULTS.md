# Measured results — v2 (specification build)

Everything here was produced by `bot/backtester.py` on Dukascopy CFD data for
WTI and Brent. No parameter was tuned to improve a number on this page; where a
setting changed, the reason and the measurement are given.

Modelling, all pessimistic where the data cannot settle it: spread paid once per
round trip ($0.05, the measured median), the stop checked before the target
inside a bar, one position per symbol, entry at the far edge of the zone,
results in R (profit divided by money risked).

**Development window: 1 Jan 2024 – 1 Jan 2026.** Held back and untouched:
everything before 2024.

## The specification as written

WTI + Brent, 1h trend / 30m setup / 15m entry, 165 trades.

| | Trades | Win | Profit factor | Net R | Max DD | Max consec. losses |
|---|---|---|---|---|---|---|
| WTI | 80 | 37.5% | 0.77 | −12.0 | 24.8 | 9 |
| Brent | 85 | 32.9% | 0.68 | −17.7 | 24.5 | 9 |
| **Both** | **165** | **35.2%** | **0.73** | **−29.7** | 46.8 | 14 |

It loses money. Not because of the reward ratio — every ratio item 29 asks for
loses:

| RR | 1:2 | 1:3 | 1:4 | 1:5 | 1:6 |
|---|---|---|---|---|---|
| Profit factor | 0.72 | 0.78 | 0.82 | 0.79 | 0.72 |
| Average win | +1.34R | +1.68R | +1.87R | +1.96R | +1.85R |

The 1:6 configuration's average win is +1.85R: the far targets are mostly not
reached, which is the trap item 29 warns about.

### The score ranks setups backwards

| Grade | Trades | Win | Profit factor |
|---|---|---|---|
| VALID (75–79) | 72 | 44.4% | 0.90 |
| STRONG (80–84) | 56 | 30.4% | 0.70 |
| VERY_STRONG (85–89) | 33 | 21.2% | 0.46 |

### Why — each component measured on its own

Correlation between the component's 0–1 value and the trade's realised R.

| Component | Points | High: n / win / exp | Low: n / win / exp | Corr |
|---|---|---|---|---|
| mfi | 10 | 131 / 40% / −0.02R | 34 / 15% / −0.79R | **+0.24** |
| macd | 10 | 143 / 37% / −0.13R | 22 / 23% / −0.51R | **+0.10** |
| correlation | 5 | 157 / 35% | 8 / 38% | +0.07 |
| price action | 5 | 66 / 32% | 99 / 37% | +0.00 |
| rsi | 10 | 92 / 32% / −0.26R | 73 / 40% / −0.08R | −0.07 |
| dxy | 5 | 44 / 23% / −0.43R | 121 / 40% / −0.09R | −0.11 |
| support/resistance | 10 | 30 / 20% / −0.50R | 135 / 39% / −0.11R | −0.13 |
| breakout/retest | 10 | 82 / 29% / −0.33R | 83 / 41% / −0.03R | **−0.16** |
| structure | 15 | 165 / 35% | — | constant |
| ema | 15 | 165 / 35% | — | constant |
| news | 5 | — | 165 / 35% | constant |

So the 100 points divide into: **35 that never vary** (vetoes or constants, so
they cannot rank anything), **35 that are inverted**, 10 that are noise, and
**20 that carry signal**. The inverted points outweigh the useful ones.

Item 5's breakout+retest, the specification's "high-quality setup", is the
clearest case: with the breakout present 29% win and −0.33R a trade, without it
41% and −0.03R. Item 4's support/resistance proximity behaves the same way.
MFI is the strongest input in the table, which is worth noting because it runs
on broker tick volume rather than exchange volume.

### Re-weighting does not fix it

Each hypothesis is a single change drawn from the table above.

| | Profit factor | Net R |
|---|---|---|
| spec as written | 0.73 | −29.7 |
| drop the inverted weights | 0.83 | −16.2 |
| MFI floor only | 0.79 | −22.4 |
| no S/R proximity veto | 0.74 | −28.0 |
| no ADX filter | 0.72 | −32.7 |
| require no breakout | 0.71 | −23.5 |
| wider stops (1.5 ATR) | 0.63 | −46.5 |

None reaches 1.0.

Every variant also shows train 0.46–0.67 then test 1.13–1.25, *including the
untouched specification*. A split that flips the same way under every
configuration is a property of the period, not evidence that a configuration
works.

The real obstacle: median maximum favourable excursion is **0.71R**, and only
21% of trades ever reach 2R. A strategy whose minimum target is 1:2 cannot work
on entries that rarely travel 2R. Widening the stops to compensate was tested
and made it worse.

## Moving the timeframe ladder up

Same code, same rules, only the ladder changes. Per-timeframe volatility bounds
are the middle 90% of that timeframe's own ATR% distribution; the time stop is
96 setup bars in every case.

| Ladder | Trades | Win | PF | Net R | Max DD | Median excursion | Reached 2R | Train / test PF |
|---|---|---|---|---|---|---|---|---|
| spec 1h/30m/15m | 169 | 34.3% | 0.70 | −33.9 | 46.8 | 0.71R | 21% | 0.50 / 1.28 |
| **A — 4h/1h/30m** | 78 | 38.5% | **1.02** | +0.8 | **9.6** | **1.06R** | 28% | 0.98 / 1.10 |
| B — 1d/4h/1h | 27 | 29.6% | 0.71 | −5.8 | 11.3 | 0.77R | 26% | 1.02 / 0.21 |

Ladder A is the first configuration that does not lose, and the change is
qualitative rather than cosmetic:

* entries finally travel far enough for a 1:2 target — the central objection to
  the spec ladder
* drawdown 9.6R against 46.8R; six consecutive losses against fourteen
* the split stops swinging: 0.98 / 1.10 against 0.50 / 1.28
* **the grades point the right way for the first time**: VALID 0.79, STRONG
  0.76, VERY_STRONG 2.08 (n=12), against 0.86 / 0.67 / 0.46 on the spec ladder

What it is not: profitable. PF 1.02 and +0.8R over two years is break-even, and
anything beyond the modelled spread makes it negative. 78 trades is a thin
sample, the VERY_STRONG figure rests on 12 of them, and frequency is 0.11/day
against item 1's target of 2–3.

Ladder B is worse, and at 27 trades its 1.02-then-0.21 split is noise.

## Notes on the specification itself

* **Items 17 and 18 disagree.** Item 17 grades a single RR (2/3/4/5/6), item 18
  fixes the ladder at 2/3/5/6. Read literally the 1:4 band unlocks no new
  target, so 85–89 scores received the same two TPs as 80–84. The ladder was
  given precedence because item 18 names its four values explicitly.
* **Item 18's 25%-per-target strands the position** whenever item 17's realistic
  cap allows only one TP, which was half of all signals: 75% of the position was
  left with no target at all. Shares now spread over the targets that exist.
* **Item 27's volatility filter is a no-op at the stated bounds.** Measured ATR%
  on WTI: median 0.33% on 30m, 0.47% on 1h, 0.93% on 4h. A 0.15–1.50% window
  keeps 99.8% of 30m bars and 99.3% of 1h bars. It only bites on 15m (82%).
* **Items 20/21 cost 83% of the signals.** 421 raw valid signals became 73 after
  the duplicate filter and daily cap — 302 were suppressed as the same setup.
  Items 20 and 36 say not to manufacture signals to hit a daily target, so the
  resulting 0.40/day is compliant with the specification's philosophy even
  though it misses its numeric target.
* **Item 11's news score cannot be backtested.** The free calendar feed carries
  the current week only, and historical consensus figures are not freely
  available, so the score is neutral throughout. The blackout *is* measurable,
  because the recurring releases are reconstructible from their publication
  rules.
* **Item 26 has a floor the spec does not mention.** One minimum lot of a
  1000-barrel contract with a $0.70 stop risks $7 whatever the account holds, so
  0.5% risk needs about $1400 of balance at that stop. Of the 73 signals in the
  original window, none was tradable on a $1000 account at 0.5%.

## Reproducing

```bash
python -m bot.backtester     # not yet a CLI; see the commit history for scripts
```
