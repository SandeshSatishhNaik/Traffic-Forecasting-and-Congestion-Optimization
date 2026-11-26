#!/usr/bin/env python3
"""Hidden-road test: can the trained graph model forecast a road it never saw in training?

Question behind it: could the system be extended to more roads without retraining from scratch?
For each chosen road R:
  - training and validation data: R is blanked out completely (no readings of R ever reach the model),
  - R's reference ("normal") speed comes only from the nights of the week before the test week, as a newly
    collected road would have after one week,
  - R's road embedding (its learned identity) is replaced by the mean embedding of the other roads,
  - at test time R's own last readings are used as inputs (a new road would be collected live).
R is then scored on the test week against "same as now" and against the normal model that did see R,
on identical rows. Same split, settings and graph as liveapp/train.py; 3 seeds by default.

  python modeling/hidden_road.py --data-dir liveapp/data/cache
Writes an aggregate table (no readings) to modeling/results/hidden-road-<date>.md.
"""
import argparse
import datetime
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import torch  # noqa: E402

import baselines  # noqa: E402
import prepare  # noqa: E402
import stgnn  # noqa: E402

H = (15, 30, 60)
DEFAULT_ROADS = ["orr_ccw_01", "orr_bellandur", "orr_marathahalli", "orr_cw_05", "hosur_bommanahalli", "varthur_kundalahalli"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=os.path.join(os.path.dirname(HERE), "liveapp", "data", "cache"))
    ap.add_argument("--roads", default=",".join(DEFAULT_ROADS))
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--hp-json", default=os.path.join(HERE, "results", "tuning-2026-11-01.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "results", f"hidden-road-{datetime.date.today():%Y-%m-%d}.md"))
    a = ap.parse_args()
    t0 = time.time()

    df, ids = prepare.load_flow(a.data_dir)
    grid = prepare.speed_grid(df, ids)
    weather = baselines.load_weather(a.data_dir)
    last_full = grid.index.max().normalize() - pd.Timedelta("1D")
    test_start = last_full - pd.Timedelta(days=6)
    test_end = last_full + pd.Timedelta("1D")
    val_start = test_start - pd.Timedelta(days=7)
    hp = json.load(open(a.hp_json))["best_hp"]
    stgnn.configure(**hp)
    A = prepare.adjacency(ids, kind=("flow", "crossing"))
    seeds = list(range(a.seeds))
    roads = a.roads.split(",")
    ref_full = prepare.free_flow_reference(grid, val_start)
    ref_week = prepare.free_flow_reference(grid[grid.index >= val_start], test_start)   # one week of nights
    print(f"test week {test_start:%Y-%m-%d} to {last_full:%Y-%m-%d}; roads hidden one at a time: {roads}; seeds {seeds}")

    def fit(g, ref, h, s):
        TR = stgnn.make_tensors(g[g.index < val_start], ref, weather, h)
        VA = stgnn.make_tensors(g[(g.index >= val_start - pd.Timedelta("1h")) & (g.index < test_start)], ref, weather, h)
        return stgnn.train_predict(TR, VA, None, A, "graph", s, return_net=True)[3]

    def predict(net, ref, j):
        X, t = stgnn.make_inputs(grid, ref, weather)
        keep = (t >= test_start) & (t < test_end)
        with torch.no_grad():
            return net(torch.tensor(X[keep])).numpy()[:, j] * ref.iloc[j], t[keep]

    # the normal model (sees every road), same seeds: trained once per horizon
    seen = {}
    for h in H:
        seen[h] = [fit(grid, ref_full, h, s) for s in seeds]
        print(f"  normal model +{h} min trained ({len(seeds)} seeds)", flush=True)

    rows = []
    for r in roads:
        j = ids.index(r)
        g = grid.copy()
        g.loc[g.index < test_start, r] = np.nan                     # the model never sees R before the test week
        ref = ref_full.copy()
        ref[r] = ref_week[r]
        for h in H:
            hid_p, seen_p = [], []
            for s in seeds:
                net = fit(g, ref, h, s)
                with torch.no_grad():                                 # R's identity: mean of the other roads
                    others = [k for k in range(len(ids)) if k != j]
                    net.emb[j] = net.emb[others].mean(0)
                p, tte = predict(net, ref, j)
                hid_p.append(p)
                seen_p.append(predict(seen[h][s], ref_full, j)[0])
            target = grid[r].reindex(tte + pd.Timedelta(minutes=h)).values
            now = grid[r].reindex(tte).values
            ok = ~np.isnan(target) & ~np.isnan(now)
            mae = lambda p: float(np.abs(p - target)[ok].mean())
            hid_runs = [mae(p) for p in hid_p]
            row = dict(road=r, h=h, rows=int(ok.sum()), hidden=float(np.mean(hid_runs)), hidden_sd=float(np.std(hid_runs)),
                       seen=mae(np.mean(seen_p, 0)), hidden_mean=mae(np.mean(hid_p, 0)), persistence=mae(now))
            rows.append(row)
            print(f"  {r:22s} +{h:2d} min: hidden {row['hidden_mean']:.2f}  seen {row['seen']:.2f}  same-as-now {row['persistence']:.2f} km/h "
                  f"(runs {row['hidden']:.2f} ± {row['hidden_sd']:.2f}; {row['rows']} rows)", flush=True)

    R = pd.DataFrame(rows)
    lines = [f"# Hidden-road test ({datetime.date.today():%Y-%m-%d})", "",
             "Can the graph model forecast a road it never saw in training? Each road below was hidden from training "
             "and validation, given the mean road embedding and a reference speed from one week of nights, then "
             "forecast on the test week from its own live readings. MAE in km/h, lower is better; same rows in each "
             "column. Hidden and seen models: mean forecast of the seeds.", "",
             f"Data: {len(df):,} readings, {len(ids)} stretches. Test week {test_start:%Y-%m-%d} to {last_full:%Y-%m-%d} "
             f"(one week, one corridor). Seeds: {len(seeds)}. Script: `modeling/hidden_road.py`.", "",
             "| Road | Horizon | Hidden (never seen) | Seen (normal model) | Same as now | Rows |", "|---|---|---|---|---|---|"]
    for x in rows:
        lines.append(f"| {x['road']} | +{x['h']} min | {x['hidden_mean']:.2f} (runs {x['hidden']:.2f} ± {x['hidden_sd']:.2f}) | "
                     f"{x['seen']:.2f} | {x['persistence']:.2f} | {x['rows']} |")
    lines += ["", "Average over the hidden roads:", "", "| Horizon | Hidden | Seen | Same as now |", "|---|---|---|---|"]
    for h in H:
        s = R[R.h == h]
        lines.append(f"| +{h} min | {s.hidden_mean.mean():.2f} | {s.seen.mean():.2f} | {s.persistence.mean():.2f} |")
    lines += ["", f"Run time {time.time() - t0:.0f} s."]
    open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines[-7:]))
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
