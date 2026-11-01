# STID on METR-LA (our re-implementation), 2026-11-01

Standard protocol: 12 in, 12 out, 70/10/20 split, masked metrics. 30 epochs on CPU (about 45 s per epoch), 207 sensors, best validation MAE 2.935.

| Horizon | MAE | RMSE | MAPE (%) |
|---|---|---|---|
| 15 min | 2.81 | 5.55 | 7.6 |
| 30 min | 3.18 | 6.56 | 9.3 |
| 60 min | 3.55 | 7.51 | 10.9 |

Graph WaveNet was not run in full: it needs about 23 minutes per epoch on CPU. On a GPU machine:

    python modeling/metrla.py --data-dir <folder with metr-la.h5 and graph_sensor_ids.txt, distances> --model gwn --epochs 100 --out gwn_metrla.json

The Graph WaveNet paper reports test MAE 2.69 / 3.07 / 3.53 at 15 / 30 / 60 min. I did not verify published STID numbers, so none are quoted here.
