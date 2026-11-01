# Modelling

Baseline speed forecasts for the Bengaluru corridor. The readings are TomTom results and are not stored in this repository: point the scripts at a folder with the collector's files.

```
# one way to get the folder (public data branch, until the private repository is in use)
git fetch origin bengaluru-data
git worktree add ../data-snapshot origin/bengaluru-data      # files are in ../data-snapshot/data/

pip install pandas numpy scikit-learn
python modeling/baselines.py --data-dir ../data-snapshot/data --out modeling/results/baselines.md
```

- `prepare.py`: loads the readings, snaps them to the 15-minute grid, a fixed reference speed per road (95th percentile of night speeds in the training period), day type (weekday or weekend/holiday), and the road adjacency matrix from `collector/network/links.csv` (not used by the baselines yet; for the graph models).
- `baselines.py`: persistence (last value), historical average (per road, day type and time of day) and gradient boosting (scikit-learn `HistGradientBoostingRegressor`; the road's own speed now and 15 and 30 minutes ago, the speed of all 21 stretches now, time of day, weekend flag, rain). One model per horizon (15, 30, 60 minutes). Walk-forward evaluation: each day is predicted by models fitted on earlier days only. `--fixed-split` gives one train/validation/test split instead.
- `results/`: aggregate metrics (MAE, RMSE, MAPE) per run.

Only pairs of slots where both readings exist are scored, and every model is scored on the same rows. Normalisation and the historical average use earlier days only, so nothing from the future leaks in. Holidays are listed in `prepare.py` (`HOLIDAYS`, currently 2 Oct 2026); add more as they come.

## Phase 2: graph models

- `stgnn.py`: small spatio-temporal graph network (two graph-convolution layers) with three variants that differ only in the graph: none, road graph, road graph plus learned graph.
- `evaluate.py`: trains them 5 times each and scores them with the baselines on identical rows: `python modeling/evaluate.py --data-dir <folder> --out modeling/results/phase2.md`. Needs `torch`.
- `results/phase2-models-2026-11-01.md`: the results (aggregate numbers only).
- `alerts.py`: early congestion warnings from the forecasts, scored against the current-speed baseline (needs the per-row predictions from `evaluate.py --save-rows`).
- `routing.py`: time-dependent Dijkstra over the stretch graph, trip-time estimates from the forecasts, and the planner check. `--save` writes the forecasts for the dashboard.
- `demo_dashboard.py`: builds one offline HTML page that replays moments from the test week (forecast next to what happened). The page embeds readings, so it is **not** committed.
- `results/phase2-alerts-trips-2026-11-01.md`: alert and trip-time results (aggregate numbers).

Order: `evaluate.py --save-rows rows.pkl`, `alerts.py --rows rows.pkl`, `routing.py --save demo.pkl`, `demo_dashboard.py --demo demo.pkl --out dashboard.html`. Python 3.11 with pandas, numpy, scikit-learn and torch.
- `tune.py`: random hyper-parameter search with 3 seeds per configuration, using only data before the test week; writes `tuning.json` (settings, scores, learning curves). `evaluate.py --hp-json` and `routing.py --hp-json` then use the chosen settings.
- `results/tuning-2026-11-01.md` and `.json`: the search. `results/phase2-models-tuned-2026-11-01.md` and `results/phase2-alerts-trips-tuned-2026-11-01.md`: the final results with tuned settings.

## Phase 2: well-known models, METR-LA and pretraining
- `refmodels.py`: our re-implementations of **Graph WaveNet** (gated dilated causal convolutions, diffusion convolution, learned adjacency) and **STID** (node, time-of-day and day-type embeddings with an MLP). Written from the papers, not the authors' code.
- `refbengaluru.py`, `evaluate_ref.py`: train and score both on the Bengaluru data, on the same rows and 5 seeds as every other model: `python modeling/evaluate_ref.py --data-dir <data> --rows rows.pkl --out result.md`. Result: `results/phase2-reference-models-2026-11-01.md`.
- `metrla.py`: the standard METR-LA benchmark (12 steps in, 12 out, 70/10/20 split, masked metrics). Download metr-la.h5 and the DCRNN graph files first. STID: `python modeling/metrla.py --data-dir <folder> --model stid --epochs 30`. Graph WaveNet needs a GPU (about 23 min per epoch on CPU): `--model gwn --epochs 100`. Result: `results/metrla-stid-2026-11-01.md`.
- `pretrain.py`: pretrain STID on METR-LA, then fine-tune on Bengaluru (all weights, or trunk frozen). Result with a from-scratch control and the limits: `results/phase2-pretraining-2026-11-01.md`. Fine-tuning all weights was about 2% better than training from scratch (one pretraining run, one test week).
- Alternative roads for real route choice: see `collector/ALT_ROADS.md` (first build did not pass verification; not collected).
