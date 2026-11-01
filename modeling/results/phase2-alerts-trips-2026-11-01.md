# Phase 2: congestion alerts and trip times from the forecasts (1 November 2026)

Same data, split and models as `phase2-models-2026-11-01.md`: trained before 25 Oct, scored on the test week 25 to 31 Oct. Aggregate numbers only.

## Congestion alerts

A stretch is "congested" when its speed is below a fraction of its fixed reference speed. An alert made at time t for t + h is compared with what happened. "Current speed" means repeating the present speed (what a live map shows); "graph forecast" is the neural net with the road graph.

| Threshold | Horizon | Alert from | Precision | Recall | F1 | congested cases | rows |
|---|---|---|---|---|---|---|---|
| speed < 0.60 x reference | 15 min | current speed | 0.81 | 0.81 | 0.81 | 503 | 1904 |
| speed < 0.60 x reference | 15 min | graph forecast | 0.85 | 0.79 | 0.82 | 503 | 1904 |
| speed < 0.60 x reference | 30 min | current speed | 0.77 | 0.76 | 0.76 | 613 | 2499 |
| speed < 0.60 x reference | 30 min | graph forecast | 0.86 | 0.76 | 0.81 | 613 | 2499 |
| speed < 0.60 x reference | 60 min | current speed | 0.71 | 0.66 | 0.69 | 524 | 2338 |
| speed < 0.60 x reference | 60 min | graph forecast | 0.80 | 0.69 | 0.75 | 524 | 2338 |
| speed < 0.75 x reference | 15 min | current speed | 0.84 | 0.84 | 0.84 | 849 | 1904 |
| speed < 0.75 x reference | 15 min | graph forecast | 0.85 | 0.88 | 0.86 | 849 | 1904 |
| speed < 0.75 x reference | 30 min | current speed | 0.80 | 0.79 | 0.80 | 1046 | 2499 |
| speed < 0.75 x reference | 30 min | graph forecast | 0.83 | 0.83 | 0.83 | 1046 | 2499 |
| speed < 0.75 x reference | 60 min | current speed | 0.77 | 0.72 | 0.75 | 959 | 2338 |
| speed < 0.75 x reference | 60 min | graph forecast | 0.80 | 0.83 | 0.81 | 959 | 2338 |

At 60 minutes the forecast raises F1 from 0.69 to 0.75 (strict threshold) and from 0.75 to 0.81 (looser threshold); at 15 minutes the two are about equal. Precision improves more than recall, so the forecast mainly gives fewer false alarms.

## Trip times

For each weekday departure in the test week where the readings exist (70 eastbound, 56 westbound), the trip time estimated at departure is compared with the time the vehicle actually needed (stepping through the real speeds, interpolated between 15-minute readings; this interpolation is an assumption). Errors are in minutes.

| Trip | departures | Method | MAE (min) | mean error (min, + = too slow) | mean actual (min) |
|---|---|---|---|---|---|
| ORR eastbound, Silk Board to Doddanekundi (7.9 km) | 70 | current speeds held constant (what a live map shows) | 1.9 | -0.2 | 25.3 |
| ORR eastbound, Silk Board to Doddanekundi (7.9 km) | 70 | historical average | 6.4 | -3.8 | 25.3 |
| ORR eastbound, Silk Board to Doddanekundi (7.9 km) | 70 | graph forecast | 1.5 | -0.7 | 25.3 |
| ORR westbound, Marathahalli to Silk Board (12.3 km) | 56 | current speeds held constant (what a live map shows) | 2.4 | +0.8 | 39.3 |
| ORR westbound, Marathahalli to Silk Board (12.3 km) | 56 | historical average | 6.5 | -5.2 | 39.3 |
| ORR westbound, Marathahalli to Silk Board (12.3 km) | 56 | graph forecast | 2.0 | -0.7 | 39.3 |

- The forecast-based estimate has the lowest error on both trips (1.5 vs 1.9 min and 2.0 vs 2.4 min), about 20% lower than holding the current speeds constant. The gain is small because both trips take 25 to 40 minutes and the current speed is already a good guide for such short trips.
- The historical average is far worse (6 min error): the road is not "average" on a given day.
- Departures within a day are correlated and cover only 5 weekdays, so treat the differences as indicative.

## Route recommendation

`routing.py` implements time-dependent Dijkstra over the stretch graph (cost = length / speed when the vehicle enters the stretch). In the graph there is only one detour for the Silk Board to Marathahalli trip, Hosur Road plus Varthur Road with one assumed 2.2 km link, and it is about twice as long, so the planner chose the Outer Ring Road in all 70 weekday departures. This shows the planner works but not yet a benefit: real alternatives (Sarjapur Road, Bannerghatta Road and others) must be added to the network first.
