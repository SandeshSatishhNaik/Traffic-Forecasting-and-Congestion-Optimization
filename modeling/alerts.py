"""Congestion alerts from forecasts, scored against what actually happened.

A stretch is "congested" when its speed is below THRESH x its fixed reference speed (95th percentile of
night-time speed in the training period). An alert at time t for horizon h says "this stretch will be
congested at t + h". The alert from the forecast model is compared with the alert from simply repeating
the current speed (what a live map effectively tells you).

Input: per-row predictions from evaluate.py (--save-rows). Not for the repository: they hold readings.
"""
import argparse

import numpy as np
import pandas as pd

import baselines
import evaluate
import prepare


def prf(actual, alert):
    tp = int((actual & alert).sum()); fp = int((~actual & alert).sum()); fn = int((actual & ~alert).sum())
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f = 2 * p * r / (p + r) if p == p and r == r and p + r else float("nan")
    return dict(precision=p, recall=r, f1=f, tp=tp, fp=fp, fn=fn, positives=int(actual.sum()), rows=len(actual))


def run(rows, ref, thresh):
    out = {}
    for h, d in rows.items():
        rr = ref.values[d["road"].values]
        actual = (d["y"].values / rr) < thresh
        for name in ("Persistence (last value)", "GCN: graph"):
            out[(h, name)] = prf(actual, (d[name].values / rr) < thresh)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rows = pd.read_pickle(a.rows)
    df, ids = prepare.load_flow(a.data_dir)
    grid = prepare.speed_grid(df, ids)
    last_full = grid.index.max().normalize() - pd.Timedelta("1D")
    val_start = last_full - pd.Timedelta(days=6) - pd.Timedelta(days=7)
    ref = prepare.free_flow_reference(grid, val_start)
    L = ["| Threshold | Horizon | Alert from | Precision | Recall | F1 | congested cases | rows |", "|---|---|---|---|---|---|---|---|"]
    for th in (0.6, 0.75):
        res = run(rows, ref, th)
        for h in (15, 30, 60):
            for name, lab in (("Persistence (last value)", "current speed"), ("GCN: graph", "graph forecast")):
                r = res[(h, name)]
                L.append(f"| speed < {th:.2f} x reference | {h} min | {lab} | {r['precision']:.2f} | {r['recall']:.2f} | {r['f1']:.2f} | {r['positives']} | {r['rows']} |")
    md = "\n".join(L)
    print(md)
    if a.out:
        open(a.out, "w").write(md + "\n")
