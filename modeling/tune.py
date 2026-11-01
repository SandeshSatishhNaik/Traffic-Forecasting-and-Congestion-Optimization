"""Hyper-parameter search for the graph model, using only data before the test week.

Tuning split (never touches the test week 25 to 31 Oct):
  tune-train: before 11 Oct     tune-validation: 11 to 17 Oct (a normal working week plus a weekend)
Random search over the space below; every configuration is trained for all three horizons with 3 seeds and
scored by the mean validation error (in % of normal speed). The best configuration is then used by
`evaluate.py --hp-json` for the one and only test run.

Usage: python modeling/tune.py --data-dir <folder> --out modeling/results/tuning.json [--trials 30]
"""
import argparse
import json
import random
import time

import numpy as np
import pandas as pd

import baselines
import prepare
import stgnn

SPACE = dict(hid=[16, 32, 64, 128], emb=[4, 8, 16], drop=[0.0, 0.1, 0.2, 0.3], lr=[1e-3, 3e-3, 1e-2],
             wd=[0.0, 1e-4, 1e-3], batch=[32, 64, 128], lags=[2, 3, 4, 6])
HORIZONS = (15, 30, 60)


def score(grid, ref, weather, A, hp, seeds, tune_end, val_start):
    stgnn.configure(**hp)
    per_h = {}
    for h in HORIZONS:
        TR = stgnn.make_tensors(grid[grid.index < val_start], ref, weather, h)
        VA = stgnn.make_tensors(grid[(grid.index >= val_start - pd.Timedelta("2h")) & (grid.index < tune_end)], ref, weather, h)
        keep = (VA[4] >= val_start)
        VA = tuple(a[keep] for a in VA)
        vals = []
        for s in seeds:
            _, best, _ = stgnn.train_predict(TR, VA, VA, A, "graph", s, hp=hp)
            vals.append(best)
        per_h[h] = float(np.mean(vals)) * 100
    return float(np.mean(list(per_h.values()))), per_h


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials", type=int, default=30)
    a = ap.parse_args()
    df, ids = prepare.load_flow(a.data_dir)
    grid = prepare.speed_grid(df, ids)
    weather = baselines.load_weather(a.data_dir)
    test_start = grid.index.max().normalize() - pd.Timedelta("1D") - pd.Timedelta(days=6)
    tune_end = test_start - pd.Timedelta(days=7)          # 18 Oct: validation week ends here, so tuning never sees it
    val_start = tune_end - pd.Timedelta(days=7)           # 11 Oct
    ref = prepare.free_flow_reference(grid, val_start)
    A = prepare.adjacency(ids, kind=("flow", "crossing"))
    rng = random.Random(0)
    trials = [("default", dict(stgnn.DEFAULT_HP))]
    seen = {tuple(sorted(stgnn.DEFAULT_HP.items()))}
    while len(trials) < a.trials + 1:
        hp = {k: rng.choice(v) for k, v in SPACE.items()}
        key = tuple(sorted(hp.items()))
        if key in seen:
            continue
        seen.add(key)
        trials.append((f"trial {len(trials)}", hp))
    results = []
    for name, hp in trials:
        t0 = time.time()
        m, per_h = score(grid, ref, weather, A, hp, (0, 1, 2), tune_end, val_start)
        results.append(dict(name=name, hp=hp, val_mean=m, val_by_h={str(k): v for k, v in per_h.items()}, seconds=round(time.time() - t0, 1)))
        print(f"{name:9s} val {m:.2f}  (15/30/60: {per_h[15]:.2f}/{per_h[30]:.2f}/{per_h[60]:.2f})  {hp}", flush=True)
    best = min(results, key=lambda r: r["val_mean"])
    default = results[0]
    # learning curves for the default and the best configuration (60-minute horizon, seed 0)
    curves = {}
    for lab, hp in (("default", default["hp"]), ("tuned", best["hp"])):
        stgnn.configure(**hp)
        TR = stgnn.make_tensors(grid[grid.index < val_start], ref, weather, 60)
        VA = stgnn.make_tensors(grid[(grid.index >= val_start - pd.Timedelta("2h")) & (grid.index < tune_end)], ref, weather, 60)
        VA = tuple(x[VA[4] >= val_start] for x in VA)
        hist = []
        stgnn.train_predict(TR, VA, VA, A, "graph", 0, hp=hp, history=hist, patience=10 ** 6, epochs=60)
        curves[lab] = [[round(x * 100, 3), round(y * 100, 3)] for x, y in hist]
    json.dump(dict(best_hp=best["hp"], best=best, default=default, results=results, curves=curves, space=SPACE,
                   tune_val=[str(val_start.date()), str((tune_end - pd.Timedelta("1D")).date())]), open(a.out, "w"), indent=1)
    print("\nBEST", best["val_mean"], best["hp"], "| default", default["val_mean"])
