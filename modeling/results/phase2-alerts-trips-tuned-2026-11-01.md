# Phase 2: congestion alerts and trip times with the tuned model (1 November 2026)

Same method as `phase2-alerts-trips-2026-11-01.md`; the forecasts come from the tuned graph network. Aggregate numbers only.

## Congestion alerts

| Threshold | Horizon | Alert from | Precision | Recall | F1 | congested cases | rows |
|---|---|---|---|---|---|---|---|
| speed < 0.60 x reference | 15 min | current speed | 0.81 | 0.81 | 0.81 | 503 | 1904 |
| speed < 0.60 x reference | 15 min | graph forecast | 0.85 | 0.81 | 0.83 | 503 | 1904 |
| speed < 0.60 x reference | 30 min | current speed | 0.77 | 0.76 | 0.76 | 613 | 2499 |
| speed < 0.60 x reference | 30 min | graph forecast | 0.84 | 0.77 | 0.80 | 613 | 2499 |
| speed < 0.60 x reference | 60 min | current speed | 0.71 | 0.66 | 0.69 | 524 | 2338 |
| speed < 0.60 x reference | 60 min | graph forecast | 0.82 | 0.72 | 0.77 | 524 | 2338 |
| speed < 0.75 x reference | 15 min | current speed | 0.84 | 0.84 | 0.84 | 849 | 1904 |
| speed < 0.75 x reference | 15 min | graph forecast | 0.84 | 0.88 | 0.86 | 849 | 1904 |
| speed < 0.75 x reference | 30 min | current speed | 0.80 | 0.79 | 0.80 | 1046 | 2499 |
| speed < 0.75 x reference | 30 min | graph forecast | 0.82 | 0.85 | 0.83 | 1046 | 2499 |
| speed < 0.75 x reference | 60 min | current speed | 0.77 | 0.72 | 0.75 | 959 | 2338 |
| speed < 0.75 x reference | 60 min | graph forecast | 0.79 | 0.84 | 0.81 | 959 | 2338 |

At 60 minutes the forecast raises F1 from 0.69 to 0.77 (strict threshold, 60% of normal speed) and from 0.75 to 0.81 (75%); at 30 minutes from 0.76 to 0.80.

## Trip times (errors in minutes; 70 eastbound and 56 westbound weekday departures)

| Trip | departures | Method | MAE (min) | mean error (min, + = too slow) | mean actual (min) |
|---|---|---|---|---|---|
| ORR eastbound, Silk Board to Doddanekundi (7.9 km) | 70 | current speeds held constant (what a live map shows) | 1.9 | -0.2 | 25.3 |
| ORR eastbound, Silk Board to Doddanekundi (7.9 km) | 70 | historical average | 6.4 | -3.8 | 25.3 |
| ORR eastbound, Silk Board to Doddanekundi (7.9 km) | 70 | graph forecast | 1.5 | -0.7 | 25.3 |
| ORR westbound, Marathahalli to Silk Board (12.3 km) | 56 | current speeds held constant (what a live map shows) | 2.4 | +0.8 | 39.3 |
| ORR westbound, Marathahalli to Silk Board (12.3 km) | 56 | historical average | 6.5 | -5.2 | 39.3 |
| ORR westbound, Marathahalli to Silk Board (12.3 km) | 56 | graph forecast | 2.1 | -0.7 | 39.3 |

Forecast-based estimates have the lowest error on both trips (1.5 vs 1.9 and 2.1 vs 2.4 min). The planner again chose the Outer Ring Road in all 70 departures (the only detour is about twice as long).

## Share of roads in the right congestion class one hour ahead (90 weekday moments, Outer Ring Road)

Forecast 72%, repeating the current state 64% (median moment: forecast 71%).
