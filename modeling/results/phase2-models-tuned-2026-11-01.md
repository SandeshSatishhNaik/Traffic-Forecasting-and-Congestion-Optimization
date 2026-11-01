# Phase 2: graph model with tuned settings (1 November 2026)

Same data, split, rows and models as `phase2-models-2026-11-01.md`, but the neural networks use the settings chosen by `tune.py` (see `tuning-2026-11-01.md`): hidden 64, embedding 4, dropout 0.2, learning rate 0.003, weight decay 0, batch 32, 3 input lags. The networks with and without the graph share these settings, so the ablation stays fair. Aggregate numbers only.

**Headline (all test days, MAE in km/h).**

| Horizon | Repeat last value | Boosting (all roads) | Net, no graph | **Net + road graph** |
|---|---|---|---|---|
| 15 min | 3.16 | 3.19 | 3.29 | **2.99** |
| 30 min | 3.91 | 3.58 | 3.63 | **3.33** |
| 60 min | 4.42 | 3.77 | 3.75 | **3.46** |

- The road graph lowers the net's error by 8 to 9% at every horizon (3.29 to 2.99, 3.63 to 3.33, 3.75 to 3.46).
- 60 minutes: 22% lower than repeating the last speed; on weekdays 5.33 to 3.94 km/h (26% lower).
- The learned adjacency again did not beat the fixed road graph (differences within the seed spread).
- Limits as before: one test week, one corridor, 33 days; the original Graph WaveNet / STID and METR-LA checks are not done.

Split by day: train before 2026-10-18, validation 2026-10-18 to 2026-10-24, test 2026-10-25 to 2026-10-31. Data: 33 days, 21 stretches. Neural models: mean +- std over 5 seeds.

### All test days

| Horizon | Model | MAE (km/h) | RMSE (km/h) | MAPE (%) | rows |
|---|---|---|---|---|---|
| 15 min | Persistence (last value) | 3.16 | 5.32 | 14.3 | 1904 |
| 15 min | Historical average | 4.14 | 5.98 | 24.4 | 1904 |
| 15 min | Gradient boosting (own history) | 3.32 | 4.66 | 15.2 | 1904 |
| 15 min | Gradient boosting (all roads) | 3.19 | 4.65 | 15.0 | 1904 |
| 15 min | Neural net, no graph | 3.29 +- 0.18 | 4.77 +- 0.15 | 15.4 +- 0.91 | 1904 |
| 15 min | Neural net + road graph | 2.99 +- 0.02 | 4.55 +- 0.01 | 13.8 +- 0.32 | 1904 |
| 15 min | Neural net + road graph + learned graph **(best MAE)** | 2.99 +- 0.02 | 4.56 +- 0.02 | 13.9 +- 0.26 | 1904 |
| 30 min | Persistence (last value) | 3.91 | 6.49 | 18.5 | 2499 |
| 30 min | Historical average | 4.11 | 6.01 | 24.0 | 2499 |
| 30 min | Gradient boosting (own history) | 3.71 | 5.30 | 18.4 | 2499 |
| 30 min | Gradient boosting (all roads) | 3.58 | 5.21 | 17.6 | 2499 |
| 30 min | Neural net, no graph | 3.63 +- 0.17 | 5.38 +- 0.12 | 18.0 +- 0.94 | 2499 |
| 30 min | Neural net + road graph **(best MAE)** | 3.33 +- 0.03 | 5.19 +- 0.04 | 16.2 +- 0.27 | 2499 |
| 30 min | Neural net + road graph + learned graph | 3.35 +- 0.03 | 5.20 +- 0.05 | 16.2 +- 0.35 | 2499 |
| 60 min | Persistence (last value) | 4.42 | 7.49 | 22.2 | 2338 |
| 60 min | Historical average | 3.90 | 5.87 | 22.8 | 2338 |
| 60 min | Gradient boosting (own history) | 3.82 | 5.54 | 20.0 | 2338 |
| 60 min | Gradient boosting (all roads) | 3.77 | 5.52 | 18.9 | 2338 |
| 60 min | Neural net, no graph | 3.75 +- 0.18 | 5.66 +- 0.15 | 19.4 +- 0.94 | 2338 |
| 60 min | Neural net + road graph **(best MAE)** | 3.46 +- 0.03 | 5.42 +- 0.02 | 17.6 +- 0.20 | 2338 |
| 60 min | Neural net + road graph + learned graph | 3.49 +- 0.10 | 5.46 +- 0.08 | 17.8 +- 0.70 | 2338 |

### Weekdays only

| Horizon | Model | MAE (km/h) | RMSE (km/h) | MAPE (%) | rows |
|---|---|---|---|---|---|
| 15 min | Persistence (last value) | 3.69 | 5.75 | 17.5 | 1360 |
| 15 min | Historical average | 4.85 | 6.65 | 30.8 | 1360 |
| 15 min | Gradient boosting (own history) | 3.55 | 4.95 | 17.9 | 1360 |
| 15 min | Gradient boosting (all roads) | 3.62 | 5.06 | 18.2 | 1360 |
| 15 min | Neural net, no graph | 3.68 +- 0.19 | 5.18 +- 0.20 | 18.4 +- 1.22 | 1360 |
| 15 min | Neural net + road graph **(best MAE)** | 3.38 +- 0.03 | 4.91 +- 0.02 | 16.5 +- 0.45 | 1360 |
| 15 min | Neural net + road graph + learned graph | 3.39 +- 0.02 | 4.91 +- 0.03 | 16.7 +- 0.29 | 1360 |
| 30 min | Persistence (last value) | 4.63 | 7.15 | 23.0 | 1785 |
| 30 min | Historical average | 4.80 | 6.68 | 30.3 | 1785 |
| 30 min | Gradient boosting (own history) | 4.07 | 5.73 | 22.1 | 1785 |
| 30 min | Gradient boosting (all roads) | 4.04 | 5.69 | 21.4 | 1785 |
| 30 min | Neural net, no graph | 4.14 +- 0.20 | 5.91 +- 0.16 | 21.9 +- 1.22 | 1785 |
| 30 min | Neural net + road graph **(best MAE)** | 3.82 +- 0.04 | 5.67 +- 0.04 | 19.7 +- 0.36 | 1785 |
| 30 min | Neural net + road graph + learned graph | 3.84 +- 0.05 | 5.68 +- 0.06 | 19.7 +- 0.48 | 1785 |
| 60 min | Persistence (last value) | 5.33 | 8.43 | 28.1 | 1670 |
| 60 min | Historical average | 4.56 | 6.51 | 28.7 | 1670 |
| 60 min | Gradient boosting (own history) | 4.20 | 6.04 | 24.3 | 1670 |
| 60 min | Gradient boosting (all roads) | 4.21 | 6.05 | 23.0 | 1670 |
| 60 min | Neural net, no graph | 4.28 +- 0.18 | 6.25 +- 0.19 | 23.8 +- 1.15 | 1670 |
| 60 min | Neural net + road graph **(best MAE)** | 3.94 +- 0.03 | 5.94 +- 0.02 | 21.5 +- 0.25 | 1670 |
| 60 min | Neural net + road graph + learned graph | 4.00 +- 0.12 | 5.99 +- 0.11 | 21.8 +- 0.96 | 1670 |

### Weekends and holidays only

| Horizon | Model | MAE (km/h) | RMSE (km/h) | MAPE (%) | rows |
|---|---|---|---|---|---|
| 15 min | Persistence (last value) **(best MAE)** | 1.86 | 4.07 | 6.4 | 544 |
| 15 min | Historical average | 2.36 | 3.80 | 8.2 | 544 |
| 15 min | Gradient boosting (own history) | 2.72 | 3.86 | 8.5 | 544 |
| 15 min | Gradient boosting (all roads) | 2.12 | 3.41 | 7.0 | 544 |
| 15 min | Neural net, no graph | 2.33 +- 0.23 | 3.56 +- 0.04 | 7.8 +- 0.50 | 544 |
| 15 min | Neural net + road graph | 2.02 +- 0.07 | 3.49 +- 0.04 | 7.0 +- 0.20 | 544 |
| 15 min | Neural net + road graph + learned graph | 1.98 +- 0.06 | 3.53 +- 0.05 | 6.9 +- 0.18 | 544 |
| 30 min | Persistence (last value) | 2.11 | 4.43 | 7.3 | 714 |
| 30 min | Historical average | 2.37 | 3.86 | 8.3 | 714 |
| 30 min | Gradient boosting (own history) | 2.82 | 4.02 | 9.1 | 714 |
| 30 min | Gradient boosting (all roads) | 2.43 | 3.76 | 8.0 | 714 |
| 30 min | Neural net, no graph | 2.35 +- 0.13 | 3.73 +- 0.03 | 8.1 +- 0.36 | 714 |
| 30 min | Neural net + road graph **(best MAE)** | 2.10 +- 0.04 | 3.70 +- 0.07 | 7.4 +- 0.10 | 714 |
| 30 min | Neural net + road graph + learned graph | 2.11 +- 0.03 | 3.74 +- 0.02 | 7.5 +- 0.09 | 714 |
| 60 min | Persistence (last value) **(best MAE)** | 2.14 | 4.31 | 7.6 | 668 |
| 60 min | Historical average | 2.26 | 3.80 | 8.0 | 668 |
| 60 min | Gradient boosting (own history) | 2.85 | 4.03 | 9.4 | 668 |
| 60 min | Gradient boosting (all roads) | 2.68 | 3.89 | 8.8 | 668 |
| 60 min | Neural net, no graph | 2.44 +- 0.19 | 3.80 +- 0.02 | 8.3 +- 0.44 | 668 |
| 60 min | Neural net + road graph | 2.26 +- 0.04 | 3.83 +- 0.02 | 8.0 +- 0.08 | 668 |
| 60 min | Neural net + road graph + learned graph | 2.21 +- 0.06 | 3.84 +- 0.06 | 7.9 +- 0.15 | 668 |

