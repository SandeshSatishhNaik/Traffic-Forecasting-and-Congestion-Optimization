#!/usr/bin/env python3
"""Train the graph models the live app runs, and save them.

Same model and settings as the project's results: Graph Convolutional Network with the road graph, tuned
settings, 5 training runs (seeds) for each horizon (+15, +30, +60 min), early stopping on a validation week.
Split by day, from the newest data backwards: the last 7 full days are the test week (never used for
training), the 7 days before are the validation week, everything earlier is training data.

  python liveapp/train.py                       # data from liveapp/data/cache (filled by liveapp/sync.py)
  python liveapp/train.py --data-dir local-data --seeds 3

Writes liveapp/models/gcn_h{15,30,60}_s{seed}.pt and model_meta.json. They are derived from TomTom
readings, so they stay out of git (liveapp/models/ is in .gitignore).
"""
import argparse
import datetime
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "modeling"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import torch  # noqa: E402

import baselines  # noqa: E402
import prepare  # noqa: E402
import stgnn  # noqa: E402

H = (15, 30, 60)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=os.path.join(HERE, "data", "cache"))
    ap.add_argument("--out", default=os.path.join(HERE, "models"))
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--hp-json", default=os.path.join(ROOT, "modeling", "results", "tuning-2026-11-01.json"))
    a = ap.parse_args()

    t0 = time.time()
    df, ids = prepare.load_flow(a.data_dir)
    grid = prepare.speed_grid(df, ids)
    weather = baselines.load_weather(a.data_dir)
    last_full = grid.index.max().normalize() - pd.Timedelta("1D")
    test_start = last_full - pd.Timedelta(days=6)
    test_end = last_full + pd.Timedelta("1D")
    val_start = test_start - pd.Timedelta(days=7)
    ref = prepare.free_flow_reference(grid, val_start)
    hp = json.load(open(a.hp_json))["best_hp"]
    stgnn.configure(**hp)
    A = prepare.adjacency(ids, kind=("flow", "crossing"))
    seeds = list(range(a.seeds))
    print(f"{len(df):,} readings, {len(ids)} stretches, {grid.index.min():%Y-%m-%d} to {grid.index.max():%Y-%m-%d %H:%M}")
    print(f"train before {val_start:%Y-%m-%d}, validate {val_start:%Y-%m-%d} to {test_start - pd.Timedelta('1D'):%Y-%m-%d}, "
          f"test {test_start:%Y-%m-%d} to {last_full:%Y-%m-%d}")
    os.makedirs(a.out, exist_ok=True)

    Xall, tall = stgnn.make_inputs(grid, ref, weather)
    keep = (tall >= test_start) & (tall < test_end)
    Xte, tte = Xall[keep], tall[keep]
    metrics = {}
    for h in H:
        TR = stgnn.make_tensors(grid[grid.index < val_start], ref, weather, h)
        VA = stgnn.make_tensors(grid[(grid.index >= val_start - pd.Timedelta("1h")) & (grid.index < test_start)], ref, weather, h)
        preds = []
        for s in seeds:
            _, best, ep, net = stgnn.train_predict(TR, VA, None, A, "graph", s, return_net=True)
            torch.save(net.state_dict(), os.path.join(a.out, f"gcn_h{h}_s{s}.pt"))
            with torch.no_grad():
                preds.append(net(torch.tensor(Xte)).numpy())
            print(f"  +{h} min seed {s}: validation error {best * 100:.2f}% of normal speed, {ep + 1} epochs", flush=True)
        P = np.mean(preds, 0) * ref.values                                     # (S, N) km/h, mean of seeds
        target = grid.reindex(tte + pd.Timedelta(minutes=h)).values
        now = grid.reindex(tte).values
        ok = ~np.isnan(target) & ~np.isnan(now)
        metrics[str(h)] = dict(model=round(float(np.abs(P - target)[ok].mean()), 2),
                               same_as_now=round(float(np.abs(now - target)[ok].mean()), 2), rows=int(ok.sum()))
        print(f"  +{h} min test week: model MAE {metrics[str(h)]['model']} km/h, 'same as now' {metrics[str(h)]['same_as_now']} km/h "
              f"({metrics[str(h)]['rows']} rows)", flush=True)

    meta = dict(ids=ids, ref={r: float(ref[r]) for r in ids}, hp=hp, c_in=int(Xall.shape[-1]), seeds=seeds,
                train_range=[f"{grid.index.min():%Y-%m-%d}", f"{val_start - pd.Timedelta('1D'):%Y-%m-%d}"],
                val_range=[f"{val_start:%Y-%m-%d}", f"{test_start - pd.Timedelta('1D'):%Y-%m-%d}"],
                test_range=[f"{test_start:%Y-%m-%d}", f"{last_full:%Y-%m-%d}"], test_metrics=metrics,
                trained_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), readings=len(df))
    json.dump(meta, open(os.path.join(a.out, "model_meta.json"), "w", encoding="utf-8"), indent=1)
    print(f"saved {len(seeds) * len(H)} networks to {a.out} in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
