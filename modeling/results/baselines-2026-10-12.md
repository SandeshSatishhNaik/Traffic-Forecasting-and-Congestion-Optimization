# Baseline speed forecasts, first run (12 October 2026)

Data: 21 Outer Ring Road corridor stretches, readings from 30 Sep 10:40 IST to 12 Oct 10:37 IST (7,152 readings, 12 days). Aggregate error numbers only; the readings themselves are not in this repository.

**Read this first:** 12 days are too few for a conclusion. The first test days (5 to 9 Oct) are predicted from only 5 to 9 days of history, and the historical average needs several weeks per weekday. Treat these numbers as a working baseline to beat later, not as a ranking of the models. Re-run when 4 to 6 weeks of data exist.

Walk-forward evaluation: each day from 2026-10-05 to 2026-10-12 is predicted by models fitted on all earlier days only.

### All test days

| Horizon | Model | MAE (km/h) | RMSE (km/h) | MAPE (%) | test rows |
|---|---|---|---|---|---|
| 15 min | Persistence (last value) | 3.15 | 5.16 | 14.4 | 2040 |
| 15 min | Historical average | 4.59 | 7.12 | 25.4 | 2040 |
| 15 min | Gradient boosting | 3.38 | 4.89 | 16.3 | 2040 |
| 30 min | Persistence (last value) | 3.76 | 6.25 | 18.0 | 2669 |
| 30 min | Historical average | 4.49 | 7.07 | 24.3 | 2669 |
| 30 min | Gradient boosting | 3.80 | 5.63 | 19.2 | 2669 |
| 60 min | Persistence (last value) | 4.31 | 7.28 | 21.6 | 2507 |
| 60 min | Historical average | 4.17 | 6.76 | 22.2 | 2507 |
| 60 min | Gradient boosting | 4.02 | 6.13 | 20.6 | 2507 |

### Weekdays only

| Horizon | Model | MAE (km/h) | RMSE (km/h) | MAPE (%) | test rows |
|---|---|---|---|---|---|
| 15 min | Persistence (last value) | 3.62 | 5.53 | 17.3 | 1496 |
| 15 min | Historical average | 5.51 | 8.02 | 32.2 | 1496 |
| 15 min | Gradient boosting | 3.83 | 5.32 | 19.8 | 1496 |
| 30 min | Persistence (last value) | 4.48 | 6.91 | 22.3 | 1955 |
| 30 min | Historical average | 5.44 | 7.99 | 30.9 | 1955 |
| 30 min | Gradient boosting | 4.44 | 6.27 | 23.8 | 1955 |
| 60 min | Persistence (last value) | 5.20 | 8.11 | 26.9 | 1839 |
| 60 min | Historical average | 5.03 | 7.61 | 28.0 | 1839 |
| 60 min | Gradient boosting | 4.72 | 6.84 | 25.5 | 1839 |

### Weekends and holidays only

| Horizon | Model | MAE (km/h) | RMSE (km/h) | MAPE (%) | test rows |
|---|---|---|---|---|---|
| 15 min | Persistence (last value) | 1.86 | 3.94 | 6.4 | 544 |
| 15 min | Historical average | 2.03 | 3.63 | 6.7 | 544 |
| 15 min | Gradient boosting | 2.12 | 3.47 | 6.9 | 544 |
| 30 min | Persistence (last value) | 1.81 | 3.88 | 6.3 | 714 |
| 30 min | Historical average | 1.90 | 3.52 | 6.3 | 714 |
| 30 min | Gradient boosting | 2.07 | 3.32 | 6.8 | 714 |
| 60 min | Persistence (last value) | 1.87 | 4.25 | 6.9 | 668 |
| 60 min | Historical average | 1.80 | 3.50 | 6.4 | 668 |
| 60 min | Gradient boosting | 2.09 | 3.53 | 7.1 | 668 |

Test rows per horizon: 15 min 2040; 30 min 2669; 60 min 2507

## What the numbers say

- Weekends and holidays are easy: speeds stay near free-flow, so repeating the last value is as good as anything (MAE about 1.9 km/h at every horizon).
- Weekdays are where forecasting matters: the error is about twice as large (15 min: 3.6 to 3.8 km/h; 60 min: 4.7 to 5.2 km/h).
- Gradient boosting is best at 60 minutes on weekdays (MAE 4.72 against 5.20 for repeating the last value and 5.03 for the historical average) and has the lowest RMSE at every horizon, but it is not better than persistence at 15 minutes. With about 2,000 training rows this is expected.
- The historical average is worst at short horizons on weekdays because its early folds have only 2 weekdays of history.
- Not yet done: LSTM, Graph WaveNet and STID (they need a regular series; our readings are dense only in the rush-hour windows), and the same code on METR-LA as a check against published numbers.
