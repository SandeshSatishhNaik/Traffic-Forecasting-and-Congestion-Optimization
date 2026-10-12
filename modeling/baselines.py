"""Baseline forecasts of road speed: persistence, historical average, gradient boosting.

For a horizon h (15, 30, 60 minutes) the task is: given the speeds up to slot t, predict the speed of
a road at slot t + h. Only pairs of slots where both readings exist are evaluated (the collector reads
the Outer Ring Road every 15 min only in the rush-hour windows), and all models are scored on the
same rows. Split is chronological by day; the historical average and the normalisation reference use
the training days only.

Usage: python modeling/baselines.py --data-dir <folder with tomtom_flow/> [--out modeling/results/baselines.md] [--fixed-split]
"""
import argparse
import os

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import prepare

HORIZONS = (15, 30, 60)


def metrics(y, p):
    e = p - y
    ok = y > 1.0   # MAPE ignores readings near zero speed
    return dict(MAE=np.abs(e).mean(), RMSE=np.sqrt((e ** 2).mean()), MAPE=100 * (np.abs(e[ok]) / y[ok]).mean(), n=len(y))


def build_rows(grid, h, weather):
    """One row per (road, slot t) with a reading at t and at t+h."""
    k = h // prepare.SLOT_MIN
    ids = list(grid.columns)
    fut = grid.shift(-k)
    rows = []
    for j, s in enumerate(ids):
        m = grid[s].notna() & fut[s].notna()
        t = grid.index[m]
        d = pd.DataFrame({"t": t, "road": j, "x": grid[s][m].values, "y": fut[s][m].values,
                          "x_m15": grid[s].shift(1)[m].values, "x_m30": grid[s].shift(2)[m].values})
        for c, name in enumerate(ids):
            d[f"v_{name}"] = grid[name][m].values
        rows.append(d)
    d = pd.concat(rows, ignore_index=True)
    d["mod"] = d["t"].dt.hour * 60 + d["t"].dt.minute
    d["dtype"] = prepare.day_type(pd.DatetimeIndex(d["t"]))
    d["weekend"] = (d["dtype"] != "weekday").astype(int)
    d["rain"] = weather.reindex(d["t"], method="nearest", tolerance=pd.Timedelta("30min")).fillna(0).values
    return d


def load_weather(data_dir):
    import glob
    files = sorted(glob.glob(os.path.join(data_dir, "weather", "*.csv")))
    if not files:
        return pd.Series(dtype=float)
    w = pd.concat([pd.read_csv(f) for f in files])
    w = w[w["status"] == "ok"]
    return pd.Series(w["precipitation_mm"].astype(float).values, index=pd.to_datetime(w["timestamp_ist"])).sort_index()


def historical_average(train, test):
    key = ["road", "dtype", "mod"]
    full = train.groupby(key)["y"].mean()
    nodt = train.groupby(["road", "mod"])["y"].mean()
    road = train.groupby("road")["y"].mean()
    p = test.set_index(key).index.map(full)
    p = pd.Series(p, index=test.index)
    p = p.fillna(pd.Series(test.set_index(["road", "mod"]).index.map(nodt), index=test.index))
    return p.fillna(test["road"].map(road)).values


def run(data_dir, test_days=3, val_days=2):
    df, ids = prepare.load_flow(data_dir)
    grid = prepare.speed_grid(df, ids)
    weather = load_weather(data_dir)
    days = sorted(set(grid.index.normalize()))
    full_days = [d for d in days if d > pd.Timestamp(prepare.FIRST_READING).normalize()]
    test_start = full_days[-test_days]
    val_start = full_days[-(test_days + val_days)]
    train_end = val_start
    ref = prepare.free_flow_reference(grid, train_end)
    out = {"ids": ids, "train_end": train_end, "val_start": val_start, "test_start": test_start, "ref": ref, "res": {}}
    feats_base = ["x", "x_m15", "x_m30", "road", "mod", "weekend", "rain"] + [f"v_{s}" for s in ids]
    for h in HORIZONS:
        d = build_rows(grid, h, weather)
        tr, va, te = d[d.t < val_start], d[(d.t >= val_start) & (d.t < test_start)], d[d.t >= test_start]
        preds = {"Persistence (last value)": te["x"].values, "Historical average": historical_average(tr, te)}
        gb = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.06, max_leaf_nodes=15, min_samples_leaf=20,
                                           l2_regularization=1.0, categorical_features=[feats_base.index("road")], random_state=0)
        gb.fit(tr[feats_base], tr["y"])
        preds["Gradient boosting"] = gb.predict(te[feats_base])
        for name, p in preds.items():
            out["res"][(h, name, "all")] = metrics(te["y"].values, p)
            for dt in ("weekday", "weekend/holiday"):
                m = (te["dtype"] == dt).values
                if m.sum() > 0:
                    out["res"][(h, name, dt)] = metrics(te["y"].values[m], np.asarray(p)[m])
        out["res"][(h, "_sizes", "all")] = dict(train=len(tr), val=len(va), test=len(te))
        # validation score of the boosting model, to spot over-fitting
        out["res"][(h, "Gradient boosting (validation)", "all")] = metrics(va["y"].values, gb.predict(va[feats_base])) if len(va) else {}
    return out


def run_walk_forward(data_dir, min_train_days=5):
    """Expanding-window evaluation: each day from day `min_train_days` on is predicted by models fitted on
    all earlier days only. Uses every day as a test day once, which matters with only a few weeks of data."""
    df, ids = prepare.load_flow(data_dir)
    grid = prepare.speed_grid(df, ids)
    weather = load_weather(data_dir)
    days = sorted(set(grid.index.normalize()))
    feats = ["x", "x_m15", "x_m30", "road", "mod", "weekend", "rain"] + [f"v_{s}" for s in ids]
    out = {"ids": ids, "mode": "walk-forward", "res": {}, "folds": days[min_train_days:]}
    for h in HORIZONS:
        d = build_rows(grid, h, weather)
        d["day"] = d["t"].dt.normalize()
        parts = []
        for day in out["folds"]:
            tr, te = d[d.day < day], d[d.day == day]
            if len(te) == 0 or len(tr) < 100:
                continue
            te = te.copy()
            te["Persistence (last value)"] = te["x"].values
            te["Historical average"] = historical_average(tr, te)
            gb = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.06, max_leaf_nodes=15, min_samples_leaf=20,
                                               l2_regularization=1.0, categorical_features=[feats.index("road")], random_state=0)
            gb.fit(tr[feats], tr["y"])
            te["Gradient boosting"] = gb.predict(te[feats])
            parts.append(te)
        te = pd.concat(parts)
        for name in ("Persistence (last value)", "Historical average", "Gradient boosting"):
            out["res"][(h, name, "all")] = metrics(te["y"].values, te[name].values)
            for dt in ("weekday", "weekend/holiday"):
                m = (te["dtype"] == dt).values
                if m.sum():
                    out["res"][(h, name, dt)] = metrics(te["y"].values[m], te[name].values[m])
        out["res"][(h, "_sizes", "all")] = dict(train=0, val=0, test=len(te))
    return out


def to_markdown(out):
    L = []
    if out.get("mode") == "walk-forward":
        L.append(f"Walk-forward evaluation: each day from {out['folds'][0].date()} to {out['folds'][-1].date()} is predicted by models fitted on all earlier days only.")
    else:
        L.append(f"Train: slots before {out['val_start'].date()}; validation: {out['val_start'].date()} to {(out['test_start'] - pd.Timedelta('1D')).date()}; test: from {out['test_start'].date()} (chronological split by day).")
    L.append("")
    for scope, title in (("all", "All test days"), ("weekday", "Weekdays only"), ("weekend/holiday", "Weekends and holidays only")):
        L.append(f"### {title}")
        L.append("")
        L.append("| Horizon | Model | MAE (km/h) | RMSE (km/h) | MAPE (%) | test rows |")
        L.append("|---|---|---|---|---|---|")
        for h in HORIZONS:
            for name in ("Persistence (last value)", "Historical average", "Gradient boosting"):
                r = out["res"].get((h, name, scope))
                if r:
                    L.append(f"| {h} min | {name} | {r['MAE']:.2f} | {r['RMSE']:.2f} | {r['MAPE']:.1f} | {r['n']} |")
        L.append("")
    L.append("Test rows per horizon: " + "; ".join(f"{h} min {out['res'][(h, '_sizes', 'all')]['test']}" for h in HORIZONS))
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--test-days", type=int, default=3)
    ap.add_argument("--val-days", type=int, default=2)
    ap.add_argument("--fixed-split", action="store_true", help="one train/validation/test split instead of walk-forward")
    a = ap.parse_args()
    o = run(a.data_dir, a.test_days, a.val_days) if a.fixed_split else run_walk_forward(a.data_dir)
    md = to_markdown(o)
    print(md)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        open(a.out, "w").write(md + "\n")
