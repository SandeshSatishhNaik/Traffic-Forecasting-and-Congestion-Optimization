"""Compare baselines and graph models on one fixed chronological split.

Rows scored: every (road, time) where the road has a reading now and a reading h minutes later
(identical for all models). Seeds: the neural models are trained 5 times; the table gives the mean
and the standard deviation over seeds.

Usage: python modeling/evaluate.py --data-dir <folder with tomtom_flow/> [--out modeling/results/phase2.md]
"""
import argparse
import os

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import baselines
import prepare
import stgnn

HORIZONS = (15, 30, 60)
SEEDS = (0, 1, 2, 3, 4)


def metrics(y, p):
    e = p - y
    ok = y > 1.0
    return dict(MAE=np.abs(e).mean(), RMSE=np.sqrt((e ** 2).mean()), MAPE=100 * (np.abs(e[ok]) / y[ok]).mean())


def run(data_dir, test_days=7, val_days=7):
    df, ids = prepare.load_flow(data_dir)
    grid = prepare.speed_grid(df, ids)
    weather = baselines.load_weather(data_dir)
    last_full = grid.index.max().normalize() - pd.Timedelta("1D")
    test_start = last_full - pd.Timedelta(days=test_days - 1)
    val_start = test_start - pd.Timedelta(days=val_days)
    test_end = last_full + pd.Timedelta("1D")
    ref = prepare.free_flow_reference(grid, val_start)
    A = prepare.adjacency(ids, kind=("flow", "crossing"))
    A_flow = A  # links.csv holds both kinds; norm_adj symmetrises
    info = dict(ids=ids, val_start=val_start, test_start=test_start, test_end=test_end, n_days=grid.index.normalize().nunique())
    results, rows_out = {}, {}
    for h in HORIZONS:
        # ---- baselines on the same split (pair rows)
        d = baselines.build_rows(grid, h, weather)
        tr, te = d[d.t < test_start], d[(d.t >= test_start) & (d.t < test_end)]
        trv = d[d.t < val_start]
        preds = {"Persistence (last value)": te["x"].values, "Historical average": baselines.historical_average(tr, te)}
        feats_all = ["x", "x_m15", "x_m30", "road", "mod", "weekend", "rain"] + [f"v_{s}" for s in ids]
        feats_own = ["x", "x_m15", "x_m30", "road", "mod", "weekend", "rain"]
        for name, feats in (("Gradient boosting (own history)", feats_own), ("Gradient boosting (all roads)", feats_all)):
            gb = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.06, max_leaf_nodes=15, min_samples_leaf=20,
                                               l2_regularization=1.0, categorical_features=[feats.index("road")], random_state=0)
            gb.fit(tr[feats], tr["y"])
            preds[name] = gb.predict(te[feats])
        out = te[["t", "road", "y", "dtype"]].copy().reset_index(drop=True)
        for k, v in preds.items():
            out[k] = np.asarray(v)
        # ---- graph models
        TR = stgnn.make_tensors(grid[grid.index < val_start], ref, weather, h)
        VA = stgnn.make_tensors(grid[(grid.index >= val_start - pd.Timedelta("1h")) & (grid.index < test_start)], ref, weather, h)
        TE = stgnn.make_tensors(grid[(grid.index >= test_start - pd.Timedelta("1h")) & (grid.index < test_end + pd.Timedelta(minutes=h))], ref, weather, h)
        keep = (TE[4] >= test_start) & (TE[4] < test_end)
        TE = tuple(a[keep] for a in TE)
        key = {(t, j): i for i, (t, _) in enumerate(zip(TE[4], range(len(TE[4])))) for j in range(0)}
        pos = {t: i for i, t in enumerate(TE[4])}
        sel_i = np.array([pos.get(t, -1) for t in out["t"]])
        ok = sel_i >= 0
        for variant in stgnn.VARIANTS:
            allp = []
            for seed in SEEDS:
                p, best, ep = stgnn.train_predict(TR, VA, TE, A, variant, seed)
                allp.append(p)
            allp = np.stack(allp)                                    # (seeds, S, N)
            refv = ref.values
            col = np.full(len(out), np.nan)
            per_seed = []
            for s in range(len(SEEDS)):
                c = np.full(len(out), np.nan)
                c[ok] = allp[s][sel_i[ok], out["road"].values[ok]] * refv[out["road"].values[ok]]
                per_seed.append(c)
            out[f"GCN: {variant}"] = np.nanmean(np.stack(per_seed), 0)   # ensemble (for the demo / routing)
            out[f"_seeds_{variant}"] = list(np.stack(per_seed).T)
        out = out[ok].reset_index(drop=True)
        rows_out[h] = out
        names = [c for c in out.columns if not c.startswith("_") and c not in ("t", "road", "y", "dtype")]
        for scope in ("all", "weekday", "weekend/holiday"):
            m = np.ones(len(out), bool) if scope == "all" else (out["dtype"] == scope).values
            if m.sum() == 0:
                continue
            for name in names:
                if name.startswith("GCN: "):
                    v = name.split(": ")[1]
                    S = np.stack(out[f"_seeds_{v}"].values)[m]               # (rows, seeds)
                    per = [metrics(out["y"].values[m], S[:, s]) for s in range(S.shape[1])]
                    results[(h, name, scope)] = {k: (np.mean([q[k] for q in per]), np.std([q[k] for q in per])) for k in per[0]}
                    results[(h, name, scope)]["n"] = int(m.sum())
                else:
                    r = metrics(out["y"].values[m], out[name].values[m])
                    results[(h, name, scope)] = {k: (r[k], 0.0) for k in r}
                    results[(h, name, scope)]["n"] = int(m.sum())
    return info, results, rows_out


ORDER = ["Persistence (last value)", "Historical average", "Gradient boosting (own history)", "Gradient boosting (all roads)",
         "GCN: none", "GCN: graph", "GCN: adaptive"]
LABEL = {"GCN: none": "Neural net, no graph", "GCN: graph": "Neural net + road graph", "GCN: adaptive": "Neural net + road graph + learned graph"}


def to_markdown(info, results):
    L = [f"Split by day: train before {info['val_start'].date()}, validation {info['val_start'].date()} to {(info['test_start'] - pd.Timedelta('1D')).date()}, test {info['test_start'].date()} to {(info['test_end'] - pd.Timedelta('1D')).date()}. Data: {info['n_days']} days, 21 stretches. Neural models: mean +- std over 5 seeds.", ""]
    for scope, title in (("all", "All test days"), ("weekday", "Weekdays only"), ("weekend/holiday", "Weekends and holidays only")):
        L += [f"### {title}", "", "| Horizon | Model | MAE (km/h) | RMSE (km/h) | MAPE (%) | rows |", "|---|---|---|---|---|---|"]
        for h in HORIZONS:
            best = min((results[(h, n, scope)]["MAE"][0], n) for n in ORDER if (h, n, scope) in results)[1]
            for n in ORDER:
                r = results.get((h, n, scope))
                if not r:
                    continue
                f = lambda k, d=2: (f"{r[k][0]:.{d}f}" + (f" +- {r[k][1]:.2f}" if r[k][1] else ""))
                nm = LABEL.get(n, n) + (" **(best MAE)**" if n == best else "")
                L.append(f"| {h} min | {nm} | {f('MAE')} | {f('RMSE')} | {f('MAPE', 1)} | {r['n']} |")
        L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--save-rows", default=None, help="pickle of per-row predictions (not for the repository)")
    a = ap.parse_args()
    info, res, rows = run(a.data_dir)
    md = to_markdown(info, res)
    print(md)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        open(a.out, "w").write(md + "\n")
    if a.save_rows:
        pd.to_pickle(rows, a.save_rows)
