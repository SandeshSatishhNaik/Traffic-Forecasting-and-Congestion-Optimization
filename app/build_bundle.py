#!/usr/bin/env python3
"""Build the data bundle that the offline traffic app serves.

The bundle holds, for every 15-minute slot of a replay window: the recorded speed of every road stretch,
the graph-model forecast for +15, +30 and +60 minutes, and the speed that was actually recorded at those
times. It also holds the road layout, so the app needs nothing else at demo time (no internet, no model).

Two ways to build it:

  # from saved forecasts (fast; the pickle written by modeling/routing.py --save)
  python app/build_bundle.py --demo demo.pkl --out app/data/bundle.json

  # from the raw data (trains the tuned graph model first: needs torch, takes a while on a CPU)
  python app/build_bundle.py --data-dir local-data --hp-json modeling/results/tuning-2026-11-01.json --out app/data/bundle.json

The bundle contains speeds derived from TomTom readings, so keep it private: app/data/ is in .gitignore.
"""
import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "modeling"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import prepare  # noqa: E402
from demo_dashboard import CHAINS, LABEL  # noqa: E402
from routing import ASSUMED_LINKS, FRAC, TRIPS, TURN_PENALTY_MIN  # noqa: E402

ROUTE_NAME = {"orr_ccw": "ORR eastbound", "orr_cw": "ORR westbound", "hosur": "Hosur Road",
              "old_airport": "Old Airport Road", "varthur": "Varthur Road"}
H = (15, 30, 60)


def r1(x):
    if x is None:
        return None
    x = float(x)
    return None if np.isnan(x) else round(x, 1)


def from_data(data_dir, hp_json, latest=False):
    """Same steps as modeling/routing.py: tuned graph model, 5 seeds, trained before the replay window.

    Default: the replay window is the last 7 full days. With latest=True it ends at the newest reading
    instead (today included), so the last slot holds real forecasts of the next 15, 30 and 60 minutes."""
    import baselines
    import routing
    import stgnn
    df, ids = prepare.load_flow(data_dir)
    grid = prepare.speed_grid(df, ids)
    weather = baselines.load_weather(data_dir)
    if latest:
        test_start = grid.index.max().normalize() - pd.Timedelta(days=6)
        test_end = grid.index.max() + pd.Timedelta(minutes=1)
    else:
        last_full = grid.index.max().normalize() - pd.Timedelta("1D")
        test_start = last_full - pd.Timedelta(days=6)
        test_end = last_full + pd.Timedelta("1D")
    val_start = test_start - pd.Timedelta(days=7)
    ref = prepare.free_flow_reference(grid, val_start)
    if hp_json:
        stgnn.configure(**json.load(open(hp_json))["best_hp"])
    print(f"training the graph model (5 seeds x 3 horizons) on data before {val_start.date()} ...", flush=True)
    F = routing.train_forecasts(grid, ref, weather, val_start, test_start, test_end)
    hist = routing.hist_table(grid, test_start)
    T = routing.evaluate_trips(grid, ref, weather, F, hist, test_start, test_end)
    return dict(F=F, grid=grid, ref=ref, T=T)


def window_accuracy(now, fc, act, ids, times):
    """MAE (km/h) of the forecast and of 'same as now' against what was recorded, in this window."""
    out = {}
    for h in H:
        ef, ep = [], []
        for r in ids:
            for k in range(len(times)):
                a, f, n = act[h][r][k], fc[h][r][k], now[r][k]
                if a is None or f is None or n is None:
                    continue
                ef.append(abs(f - a))
                ep.append(abs(n - a))
        out[str(h)] = dict(forecast=round(float(np.mean(ef)), 2) if ef else None,
                           same_as_now=round(float(np.mean(ep)), 2) if ep else None, rows=len(ef))
    return out


def bundle(D, note, mode="replay"):
    F, grid, ref, T = D["F"], D["grid"], D["ref"], D["T"]
    times = list(F[15].index)
    ids = list(grid.columns)
    seg = pd.read_csv(prepare.SEGMENTS_CSV).set_index("segment_id")
    links = pd.read_csv(prepare.LINKS_CSV)
    g = grid.reindex(times)
    now = {r: [r1(v) for v in g[r].values] for r in ids}
    fc = {h: {r: [r1(v) for v in F[h][r].values] for r in ids} for h in H}
    act = {}
    for h in H:
        ga = grid.reindex([t + pd.Timedelta(minutes=h) for t in times])
        act[h] = {r: [r1(v) for v in ga[r].values] for r in ids}
    dtype = prepare.day_type(pd.DatetimeIndex(times))
    pos = {t: k for k, t in enumerate(times)}
    trips = [dict(trip=x["trip"], i=pos[x["depart"]], **{k: r1(x[k]) for k in ("actual", "current", "historical", "forecast")})
             for _, x in T.iterrows() if x["depart"] in pos]
    roads = []
    for r in ids:
        s = seg.loc[r]
        roads.append(dict(id=r, label=LABEL.get(r, r), road=ROUTE_NAME.get(s["route"], s["route"]), route=s["route"],
                          seq=int(s["seq"]), tier=s["tier"], km=float(s["length_km"]), lat=float(s["lat"]), lon=float(s["lon"]),
                          ref=r1(ref[r])))
    return dict(
        meta=dict(built=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), note=note, mode=mode,
                  window=[times[0].strftime("%Y-%m-%d"), times[-1].strftime("%Y-%m-%d")],
                  model="Graph Convolutional Network with the road graph (tuned), mean of 5 training runs",
                  thresholds=dict(slow=0.75, severe=0.60), turn_penalty_min=TURN_PENALTY_MIN),
        times=[t.strftime("%Y-%m-%dT%H:%M") for t in times],
        daytype=[str(x) for x in dtype],
        roads=roads,
        now=now,
        forecast={str(h): fc[h] for h in H},
        actual={str(h): act[h] for h in H},
        links=[dict(src=x["from_id"], dst=x["to_id"], kind=x["kind"], lat=float(x["lat"]), lon=float(x["lon"])) for _, x in links.iterrows()],
        assumed=[dict(src=a, dst=b, km=km, kmph=v) for a, b, km, v in ASSUMED_LINKS],
        frac=FRAC,
        chains=CHAINS,
        trip_presets=TRIPS,
        trips=trips,
        accuracy=window_accuracy(now, fc, act, ids, times),
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--demo", help="pickle written by modeling/routing.py --save")
    src.add_argument("--data-dir", help="folder with tomtom_flow/ (trains the model first)")
    ap.add_argument("--latest", action="store_true",
                    help="with --data-dir: end the window at the newest reading, so the app opens on a real forecast of the next hour")
    ap.add_argument("--hp-json", default=os.path.join(ROOT, "modeling", "results", "tuning-2026-11-01.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "data", "bundle.json"))
    a = ap.parse_args()
    if a.demo:
        D = pd.read_pickle(a.demo)
        note = f"saved forecasts {os.path.basename(a.demo)}"
    else:
        D = from_data(a.data_dir, a.hp_json, a.latest)
        note = f"trained from {a.data_dir}"
    B = bundle(D, note, "latest" if a.latest and a.data_dir else "replay")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(B, f, separators=(",", ":"))
    print(f"wrote {a.out}: {len(B['times'])} slots x {len(B['roads'])} road stretches, window {B['meta']['window'][0]} to {B['meta']['window'][1]}")
    for h, v in B["accuracy"].items():
        print(f"  +{h} min: forecast MAE {v['forecast']} km/h, 'same as now' {v['same_as_now']} km/h ({v['rows']} rows)")
