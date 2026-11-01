"""Add Graph WaveNet and STID (our re-implementations) to the Bengaluru comparison, on the same rows.

Needs the per-row predictions saved by `evaluate.py --save-rows` (same split, same rows), and the same
tuned hyper-parameters file if you used one there. Five seeds per model; mean +- std over seeds.

Usage: python modeling/evaluate_ref.py --data-dir <folder> --rows rows.pkl --out modeling/results/phase2-ref-models.md
"""
import argparse
import json

import numpy as np
import pandas as pd

import baselines
import prepare
import refbengaluru as rb

HOR = {15: 0, 30: 1, 60: 2}
SEEDS = (0, 1, 2, 3, 4)


def metrics(y, p):
    e = p - y
    ok = y > 1.0
    return dict(MAE=np.abs(e).mean(), RMSE=np.sqrt((e ** 2).mean()), MAPE=100 * (np.abs(e[ok]) / y[ok]).mean())


def run(data_dir, rows, test_days=7, val_days=7, kinds=("gwn", "stid"), seeds=SEEDS, hp=None, pre_state=None, freeze_trunk=False, tag=None):
    df, ids = prepare.load_flow(data_dir)
    grid = prepare.speed_grid(df, ids)
    weather = baselines.load_weather(data_dir)
    last_full = grid.index.max().normalize() - pd.Timedelta("1D")
    test_start = last_full - pd.Timedelta(days=test_days - 1)
    val_start = test_start - pd.Timedelta(days=val_days)
    test_end = last_full + pd.Timedelta("1D")
    ref = prepare.free_flow_reference(grid, val_start)
    A = prepare.adjacency(ids, kind=("flow", "crossing"))
    d = rb.make_seq(grid, ref, weather)
    t = d["t"]
    sel = lambda m: {k: (v[m] if isinstance(v, np.ndarray) else v[m]) for k, v in d.items()}
    tr_m = np.asarray(t < val_start) & (d["YM"].any((1, 2)))
    va_m = np.asarray((t >= val_start) & (t < test_start)) & (d["YM"].any((1, 2)))
    te_m = np.asarray((t >= test_start) & (t < test_end))
    tr, va, te = sel(tr_m), sel(va_m), sel(te_m)
    pos = {x: i for i, x in enumerate(te["t"])}
    preds = {}
    for kind in kinds:
        per = []
        for s in seeds:
            P, best = rb.fit_predict(kind, A, tr, va, te, s, hp, pre_state=pre_state, freeze_trunk=freeze_trunk)
            per.append(P)
            print(tag or kind, "seed", s, "val", round(best * 100, 2), flush=True)
        preds[tag or kind] = np.stack(per)           # (seeds, S, N, 3)
    out = {}
    for h, j in HOR.items():
        r = rows[h]
        i = np.array([pos.get(x, -1) for x in r["t"]])
        ok = i >= 0
        for kind in ([tag] if tag else kinds):
            cols = []
            for s in range(len(seeds)):
                c = np.full(len(r), np.nan)
                c[ok] = preds[kind][s][i[ok], r["road"].values[ok], j] * ref.values[r["road"].values[ok]]
                cols.append(c)
            r[f"_seeds_{kind}"] = list(np.stack(cols).T)
        out[h] = r[ok].reset_index(drop=True)
    return out, ids


def table(rows, kinds, extra=("Persistence (last value)", "Gradient boosting (all roads)", "GCN: none", "GCN: graph")):
    LAB = {"gwn": "Graph WaveNet (re-implemented)", "stid": "STID (re-implemented)", "stid_pre": "STID, pretrained on METR-LA, all weights fine-tuned", "stid_frozen": "STID, pretrained on METR-LA, trunk frozen", "stid_ctrl": "STID from scratch, fine-tuning settings (control)", "GCN: none": "Our net, no graph", "GCN: graph": "Our net + road graph"}
    L = ["| Horizon | Model | MAE (km/h) | RMSE (km/h) | MAPE (%) | rows |", "|---|---|---|---|---|---|"]
    for h in HOR:
        r = rows[h]
        y = r["y"].values
        for name in extra:
            if name.startswith("GCN"):
                v = name.split(": ")[1]
                S = np.stack(r[f"_seeds_{v}"].values)
                per = [metrics(y, S[:, s]) for s in range(S.shape[1])]
                m = {k: (np.mean([q[k] for q in per]), np.std([q[k] for q in per])) for k in per[0]}
            else:
                q = metrics(y, r[name].values)
                m = {k: (q[k], 0.0) for k in q}
            f = lambda k, dgt=2: f"{m[k][0]:.{dgt}f}" + (f" +- {m[k][1]:.2f}" if m[k][1] else "")
            L.append(f"| {h} min | {LAB.get(name, name)} | {f('MAE')} | {f('RMSE')} | {f('MAPE', 1)} | {len(y)} |")
        for kind in kinds:
            S = np.stack(r[f"_seeds_{kind}"].values)
            per = [metrics(y, S[:, s]) for s in range(S.shape[1])]
            m = {k: (np.mean([q[k] for q in per]), np.std([q[k] for q in per])) for k in per[0]}
            L.append(f"| {h} min | {LAB[kind]} | {m['MAE'][0]:.2f} +- {m['MAE'][1]:.2f} | {m['RMSE'][0]:.2f} +- {m['RMSE'][1]:.2f} | {m['MAPE'][0]:.1f} +- {m['MAPE'][1]:.1f} | {len(y)} |")
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--save-rows", default=None)
    ap.add_argument("--seeds", type=int, default=5)
    a = ap.parse_args()
    rows = pd.read_pickle(a.rows)
    out, ids = run(a.data_dir, rows, seeds=tuple(range(a.seeds)))
    md = table(out, ("gwn", "stid"))
    print(md)
    if a.out:
        open(a.out, "w").write(md + "\n")
    if a.save_rows:
        pd.to_pickle(out, a.save_rows)
