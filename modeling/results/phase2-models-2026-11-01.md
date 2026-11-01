# Phase 2: does the road graph help? (1 November 2026)

Data: 21 Outer Ring Road corridor stretches, 30 Sep to 1 Nov 2026 (33 days, 19,093 readings). Only aggregate error numbers are kept in this repository, not the readings.

**Models.** Persistence repeats the last speed. Historical average uses road, day type and time of day. Gradient boosting is scikit-learn's `HistGradientBoostingRegressor`, with only the road's own history or with the speeds of all 21 roads. The neural nets (`stgnn.py`) are two graph-convolution layers plus a linear output, trained 5 times with different seeds; they differ **only in the graph**: none (identity), the road graph from `collector/network/links.csv`, or that graph plus a learned adjacency.

**Reading the tables.** Every model is scored on the same (road, time) pairs. Holidays (2 Oct, Dasara 19 to 21 Oct) are treated as weekends. The test week 25 to 31 Oct has no holiday.

**Headline (all test days, MAE in km/h).**

| Horizon | Repeat last value | Boosting (all roads) | Neural net, no graph | **Neural net + road graph** |
|---|---|---|---|---|
| 15 min | 3.16 | 3.19 | 3.29 | **2.98** |
| 30 min | 3.91 | 3.58 | 3.73 | **3.38** |
| 60 min | 4.42 | 3.77 | 3.87 | **3.51** |

- Adding the road graph lowers the neural net's error by about 9% at every horizon (3.29 to 2.98, 3.73 to 3.38, 3.87 to 3.51). Nothing else changed, so the gain comes from the graph.
- On weekdays, where forecasting matters, the 60-minute error falls from 5.33 (repeat last value) and 4.21 (boosting) to 4.04 km/h.
- The learned adjacency (Graph WaveNet style) did not beat the fixed road graph here. A plausible reason is that 21 stretches and 4 weeks of data are too few to learn extra links; this is a guess, not tested.
- Weekends and holidays are easy: the best simple models are within about 0.3 km/h of the graph model there, so most of the benefit is on weekdays.

**Limits.** One test week, five seeds, one corridor, 33 days of history. The differences between the graph net and boosting at 15 and 30 minutes are about 0.2 km/h and can change with another test week. The Dasara holidays are identified partly from the data itself (weekend-like speeds) and are only used as a calendar flag. Not done: LSTM, the original Graph WaveNet and STID code, and the same code on METR-LA.

Split by day: train before 2026-10-18, validation 2026-10-18 to 2026-10-24, test 2026-10-25 to 2026-10-31. Data: 33 days, 21 stretches. Neural models: mean +- std over 5 seeds.

### All test days

| Horizon | Model | MAE (km/h) | RMSE (km/h) | MAPE (%) | rows |
|---|---|---|---|---|---|
| 15 min | Persistence (last value) | 3.16 | 5.32 | 14.3 | 1904 |
| 15 min | Historical average | 4.14 | 5.98 | 24.4 | 1904 |
| 15 min | Gradient boosting (own history) | 3.32 | 4.66 | 15.2 | 1904 |
| 15 min | Gradient boosting (all roads) | 3.19 | 4.65 | 15.0 | 1904 |
| 15 min | Neural net, no graph | 3.29 +- 0.11 | 4.77 +- 0.07 | 15.2 +- 0.62 | 1904 |
| 15 min | Neural net + road graph **(best MAE)** | 2.98 +- 0.03 | 4.56 +- 0.02 | 13.8 +- 0.28 | 1904 |
| 15 min | Neural net + road graph + learned graph | 3.02 +- 0.02 | 4.59 +- 0.03 | 14.0 +- 0.11 | 1904 |
| 30 min | Persistence (last value) | 3.91 | 6.49 | 18.5 | 2499 |
| 30 min | Historical average | 4.11 | 6.01 | 24.0 | 2499 |
| 30 min | Gradient boosting (own history) | 3.71 | 5.30 | 18.4 | 2499 |
| 30 min | Gradient boosting (all roads) | 3.58 | 5.21 | 17.6 | 2499 |
| 30 min | Neural net, no graph | 3.73 +- 0.16 | 5.45 +- 0.11 | 18.2 +- 0.86 | 2499 |
| 30 min | Neural net + road graph **(best MAE)** | 3.38 +- 0.05 | 5.22 +- 0.04 | 16.8 +- 0.23 | 2499 |
| 30 min | Neural net + road graph + learned graph | 3.43 +- 0.07 | 5.30 +- 0.06 | 17.1 +- 0.47 | 2499 |
| 60 min | Persistence (last value) | 4.42 | 7.49 | 22.2 | 2338 |
| 60 min | Historical average | 3.90 | 5.87 | 22.8 | 2338 |
| 60 min | Gradient boosting (own history) | 3.82 | 5.54 | 20.0 | 2338 |
| 60 min | Gradient boosting (all roads) | 3.77 | 5.52 | 18.9 | 2338 |
| 60 min | Neural net, no graph | 3.87 +- 0.07 | 5.78 +- 0.06 | 20.1 +- 0.64 | 2338 |
| 60 min | Neural net + road graph **(best MAE)** | 3.51 +- 0.10 | 5.47 +- 0.11 | 18.2 +- 0.81 | 2338 |
| 60 min | Neural net + road graph + learned graph | 3.64 +- 0.15 | 5.61 +- 0.13 | 19.3 +- 0.77 | 2338 |

### Weekdays only

| Horizon | Model | MAE (km/h) | RMSE (km/h) | MAPE (%) | rows |
|---|---|---|---|---|---|
| 15 min | Persistence (last value) | 3.69 | 5.75 | 17.5 | 1360 |
| 15 min | Historical average | 4.85 | 6.65 | 30.8 | 1360 |
| 15 min | Gradient boosting (own history) | 3.55 | 4.95 | 17.9 | 1360 |
| 15 min | Gradient boosting (all roads) | 3.62 | 5.06 | 18.2 | 1360 |
| 15 min | Neural net, no graph | 3.65 +- 0.10 | 5.17 +- 0.08 | 18.2 +- 0.78 | 1360 |
| 15 min | Neural net + road graph **(best MAE)** | 3.38 +- 0.03 | 4.92 +- 0.03 | 16.5 +- 0.38 | 1360 |
| 15 min | Neural net + road graph + learned graph | 3.44 +- 0.03 | 4.96 +- 0.04 | 16.8 +- 0.18 | 1360 |
| 30 min | Persistence (last value) | 4.63 | 7.15 | 23.0 | 1785 |
| 30 min | Historical average | 4.80 | 6.68 | 30.3 | 1785 |
| 30 min | Gradient boosting (own history) | 4.07 | 5.73 | 22.1 | 1785 |
| 30 min | Gradient boosting (all roads) | 4.04 | 5.69 | 21.4 | 1785 |
| 30 min | Neural net, no graph | 4.21 +- 0.14 | 6.00 +- 0.14 | 22.1 +- 1.04 | 1785 |
| 30 min | Neural net + road graph **(best MAE)** | 3.89 +- 0.05 | 5.73 +- 0.05 | 20.5 +- 0.29 | 1785 |
| 30 min | Neural net + road graph + learned graph | 3.96 +- 0.07 | 5.81 +- 0.08 | 21.0 +- 0.57 | 1785 |
| 60 min | Persistence (last value) | 5.33 | 8.43 | 28.1 | 1670 |
| 60 min | Historical average | 4.56 | 6.51 | 28.7 | 1670 |
| 60 min | Gradient boosting (own history) | 4.20 | 6.04 | 24.3 | 1670 |
| 60 min | Gradient boosting (all roads) | 4.21 | 6.05 | 23.0 | 1670 |
| 60 min | Neural net, no graph | 4.40 +- 0.08 | 6.40 +- 0.08 | 24.6 +- 0.97 | 1670 |
| 60 min | Neural net + road graph **(best MAE)** | 4.04 +- 0.13 | 6.02 +- 0.14 | 22.4 +- 1.10 | 1670 |
| 60 min | Neural net + road graph + learned graph | 4.21 +- 0.19 | 6.19 +- 0.18 | 23.8 +- 1.07 | 1670 |

### Weekends and holidays only

| Horizon | Model | MAE (km/h) | RMSE (km/h) | MAPE (%) | rows |
|---|---|---|---|---|---|
| 15 min | Persistence (last value) **(best MAE)** | 1.86 | 4.07 | 6.4 | 544 |
| 15 min | Historical average | 2.36 | 3.80 | 8.2 | 544 |
| 15 min | Gradient boosting (own history) | 2.72 | 3.86 | 8.5 | 544 |
| 15 min | Gradient boosting (all roads) | 2.12 | 3.41 | 7.0 | 544 |
| 15 min | Neural net, no graph | 2.39 +- 0.15 | 3.58 +- 0.04 | 7.9 +- 0.42 | 544 |
| 15 min | Neural net + road graph | 2.00 +- 0.07 | 3.49 +- 0.04 | 7.0 +- 0.24 | 544 |
| 15 min | Neural net + road graph + learned graph | 1.97 +- 0.05 | 3.50 +- 0.02 | 6.9 +- 0.10 | 544 |
| 30 min | Persistence (last value) | 2.11 | 4.43 | 7.3 | 714 |
| 30 min | Historical average | 2.37 | 3.86 | 8.3 | 714 |
| 30 min | Gradient boosting (own history) | 2.82 | 4.02 | 9.1 | 714 |
| 30 min | Gradient boosting (all roads) | 2.43 | 3.76 | 8.0 | 714 |
| 30 min | Neural net, no graph | 2.53 +- 0.22 | 3.75 +- 0.03 | 8.5 +- 0.54 | 714 |
| 30 min | Neural net + road graph **(best MAE)** | 2.11 +- 0.07 | 3.67 +- 0.02 | 7.4 +- 0.18 | 714 |
| 30 min | Neural net + road graph + learned graph | 2.11 +- 0.07 | 3.74 +- 0.07 | 7.5 +- 0.24 | 714 |
| 60 min | Persistence (last value) **(best MAE)** | 2.14 | 4.31 | 7.6 | 668 |
| 60 min | Historical average | 2.26 | 3.80 | 8.0 | 668 |
| 60 min | Gradient boosting (own history) | 2.85 | 4.03 | 9.4 | 668 |
| 60 min | Gradient boosting (all roads) | 2.68 | 3.89 | 8.8 | 668 |
| 60 min | Neural net, no graph | 2.57 +- 0.13 | 3.79 +- 0.03 | 8.6 +- 0.27 | 668 |
| 60 min | Neural net + road graph | 2.20 +- 0.03 | 3.77 +- 0.04 | 7.8 +- 0.13 | 668 |
| 60 min | Neural net + road graph + learned graph | 2.24 +- 0.07 | 3.78 +- 0.07 | 7.9 +- 0.14 | 668 |

