# Re-implemented Graph WaveNet and STID on the Bengaluru corridor (2026-11-01)

Same scored rows as the other models, 5 seeds, mean +- std over seeds. Test week 25-31 Oct. Code: modeling/refmodels.py, refbengaluru.py, evaluate_ref.py.

| Horizon | Model | MAE (km/h) | RMSE (km/h) | MAPE (%) | rows |
|---|---|---|---|---|---|
| 15 min | Persistence (last value) | 3.16 | 5.32 | 14.3 | 1904 |
| 15 min | Gradient boosting (all roads) | 3.19 | 4.65 | 15.0 | 1904 |
| 15 min | Our net, no graph | 3.29 +- 0.18 | 4.77 +- 0.15 | 15.4 +- 0.91 | 1904 |
| 15 min | Our net + road graph | 2.99 +- 0.02 | 4.55 +- 0.01 | 13.8 +- 0.32 | 1904 |
| 15 min | Graph WaveNet (re-implemented) | 2.99 +- 0.01 | 4.67 +- 0.03 | 13.8 +- 0.2 | 1904 |
| 15 min | STID (re-implemented) | 2.99 +- 0.01 | 4.61 +- 0.02 | 13.7 +- 0.1 | 1904 |
| 30 min | Persistence (last value) | 3.91 | 6.49 | 18.5 | 2499 |
| 30 min | Gradient boosting (all roads) | 3.58 | 5.21 | 17.6 | 2499 |
| 30 min | Our net, no graph | 3.63 +- 0.17 | 5.38 +- 0.12 | 18.0 +- 0.94 | 2499 |
| 30 min | Our net + road graph | 3.33 +- 0.03 | 5.19 +- 0.04 | 16.2 +- 0.27 | 2499 |
| 30 min | Graph WaveNet (re-implemented) | 3.49 +- 0.04 | 5.50 +- 0.03 | 16.7 +- 0.4 | 2499 |
| 30 min | STID (re-implemented) | 3.33 +- 0.02 | 5.25 +- 0.04 | 15.8 +- 0.1 | 2499 |
| 60 min | Persistence (last value) | 4.42 | 7.49 | 22.2 | 2338 |
| 60 min | Gradient boosting (all roads) | 3.77 | 5.52 | 18.9 | 2338 |
| 60 min | Our net, no graph | 3.75 +- 0.18 | 5.66 +- 0.15 | 19.4 +- 0.94 | 2338 |
| 60 min | Our net + road graph | 3.46 +- 0.03 | 5.42 +- 0.02 | 17.6 +- 0.20 | 2338 |
| 60 min | Graph WaveNet (re-implemented) | 3.85 +- 0.05 | 6.26 +- 0.08 | 19.4 +- 0.5 | 2338 |
| 60 min | STID (re-implemented) | 3.41 +- 0.05 | 5.44 +- 0.04 | 17.0 +- 0.3 | 2338 |

Reading: Graph WaveNet overfits this small dataset (worse than our graph net at 30 and 60 min). STID ties our graph net at 15 and 30 min; at 60 min 3.41 vs 3.46 is within about one standard deviation.
