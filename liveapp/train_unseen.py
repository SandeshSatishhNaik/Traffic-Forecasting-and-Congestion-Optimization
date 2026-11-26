#!/usr/bin/env python3
"""Unseen roads: train, save and test graph models that never saw one road, for every road.

Answers "what about roads you did not collect?". For each road R the GCN is trained with R hidden completely
(no reading of R in training or validation); R gets the mean road embedding of the others. Two cases are tested
on the test week (same split as train.py):

  new sensor  R has just started sending readings: its own last readings are inputs, its reference speed comes
              from one week of nights (the validation week). Compared with "same as now" and the normal model.
  no sensor   R is never measured: its own inputs are blank, the forecast comes only from the connected roads
              through the road graph (a "virtual sensor"). Compared with "R is like its neighbours right now".

Errors are in percentage points of R's normal speed (the scale the map colours use), so the no-sensor case
needs no km/h reference. The live app loads the saved networks (liveapp/models/unseen/) for its
"treat as unseen" switch.

  python liveapp/train_unseen.py --jobs 3          # all 21 roads, 2 seeds, 3 processes in parallel
  python liveapp/train_unseen.py --summary         # rebuild the result table from the saved per-road files
"""
import argparse
import datetime
import glob
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "modeling"))
OUT = os.path.join(HERE, "models", "unseen")
H = (15, 30, 60)


def setup(data_dir):
    import pandas as pd
    import baselines
    import prepare
    import stgnn
    df, ids = prepare.load_flow(data_dir)
    grid = prepare.speed_grid(df, ids)
    weather = baselines.load_weather(data_dir)
    last_full = grid.index.max().normalize() - pd.Timedelta("1D")
    test_start = last_full - pd.Timedelta(days=6)
    val_start = test_start - pd.Timedelta(days=7)
    hp = json.load(open(os.path.join(ROOT, "modeling", "results", "tuning-2026-11-01.json")))["best_hp"]
    stgnn.configure(**hp)
    return dict(df=df, ids=ids, grid=grid, weather=weather, test_start=test_start, test_end=last_full + pd.Timedelta("1D"),
                val_start=val_start, last_full=last_full, hp=hp, A=prepare.adjacency(ids, kind=("flow", "crossing")),
                ref_full=prepare.free_flow_reference(grid, val_start),
                ref_week=prepare.free_flow_reference(grid[grid.index >= val_start], test_start))


def blank(X, j, lags):
    """Inputs with road j never measured: values 1.0 and missing flags 0 for every lag."""
    X = X.copy()
    X[:, j, :lags] = 1.0
    X[:, j, lags:2 * lags] = 0.0
    return X


def run_roads(roads, seeds, data_dir, threads):
    import numpy as np
    import pandas as pd
    import torch
    import stgnn
    torch.set_num_threads(threads)
    D = setup(data_dir)
    ids, grid, A, L = D["ids"], D["grid"], D["A"], stgnn.LAGS
    Asym = ((A + A.T) > 0)
    seen_dir = os.path.join(HERE, "models")
    seen_meta = json.load(open(os.path.join(seen_dir, "model_meta.json"), encoding="utf-8"))
    hp = seen_meta["hp"]
    os.makedirs(OUT, exist_ok=True)
    ratio = (grid / D["ref_full"]).values                      # actual ratio of every road (for scoring)
    Xall, tall = stgnn.make_inputs(grid, D["ref_full"], D["weather"])
    keep = (tall >= D["test_start"]) & (tall < D["test_end"])
    Xte, tte = Xall[keep], tall[keep]
    gpos = {t: k for k, t in enumerate(grid.index)}

    def load_seen(h, s):
        net = stgnn.Net(A, "graph", seen_meta["c_in"], hid=hp["hid"], emb=hp["emb"], drop=hp["drop"])
        net.load_state_dict(torch.load(os.path.join(seen_dir, f"gcn_h{h}_s{s}.pt"), map_location="cpu"))
        return net.eval()

    for r in roads:
        t0 = time.time()
        j = ids.index(r)
        others = [k for k in range(len(ids)) if k != j]
        nb = [k for k in np.where(Asym[j])[0] if k != j]
        g = grid.copy()
        g.loc[g.index < D["test_start"], r] = np.nan
        ref = D["ref_full"].copy()
        ref[r] = D["ref_week"][r]
        # inputs for the "new sensor" case: R's ratios on its own one-week reference
        Xnew = Xte.copy()
        Xnew[:, j, :L] = np.where(Xte[:, j, L:2 * L] > 0, Xte[:, j, :L] * D["ref_full"][r] / ref[r], 1.0)
        Xnone = blank(Xte, j, L)
        res = dict(road=r, neighbours=[ids[k] for k in nb], ref_week=float(ref[r]), ref_full=float(D["ref_full"][r]), h={})
        for h in H:
            TR = stgnn.make_tensors(g[g.index < D["val_start"]], ref, D["weather"], h)
            # virtual-sensor training: a second copy of every sample with one random *known* road blanked out
            # (inputs missing) while its true future speed stays the target, so the network learns to fill in
            # a road from its neighbours. R itself is never a target (it is hidden).
            rng = np.random.default_rng(1000 + h)
            kk = rng.choice(others, size=len(TR[0]))
            Xb = TR[0].copy(); Xb[np.arange(len(Xb)), kk, :L] = 1.0; Xb[np.arange(len(Xb)), kk, L:2 * L] = 0.0
            TR = (np.concatenate([TR[0], Xb]), np.concatenate([TR[1], TR[1]]), np.concatenate([TR[2], TR[2]]))
            VA = stgnn.make_tensors(g[(g.index >= D["val_start"] - pd.Timedelta("1h")) & (g.index < D["test_start"])], ref, D["weather"], h)
            p_new, p_none, p_nfc = [], [], []
            for s in seeds:
                net = stgnn.train_predict(TR, VA, None, A, "graph", s, return_net=True)[3]
                with torch.no_grad():
                    net.emb[j] = net.emb[others].mean(0)
                    p_new.append(net(torch.tensor(Xnew)).numpy()[:, j] * ref[r] / D["ref_full"][r])   # back to the scoring scale
                    out_none = net(torch.tensor(Xnone)).numpy()
                    p_none.append(out_none[:, j])
                    if nb:   # neighbours' own GCN forecasts (same hidden model, R blank), averaged
                        p_nfc.append(out_none[:, nb].mean(1))
                torch.save(net.state_dict(), os.path.join(OUT, f"unseen_{r}_h{h}_s{s}.pt"))
            with torch.no_grad():
                p_seen = np.mean([load_seen(h, s)(torch.tensor(Xte)).numpy()[:, j] for s in seen_meta["seeds"]], 0)
            ks = np.array([gpos.get(t) for t in tte]); kh = np.array([gpos.get(t + pd.Timedelta(minutes=h), -1) for t in tte])
            target = np.where(kh >= 0, ratio[kh, j], np.nan)
            now = ratio[ks, j]
            nbr = np.nanmean(ratio[ks][:, nb], 1) if nb else np.full(len(ks), np.nan)
            ok_new = ~np.isnan(target) & ~np.isnan(now)
            ok_none = ~np.isnan(target) & ~np.isnan(nbr)
            e = lambda p, ok: round(float(np.abs(np.asarray(p) - target)[ok].mean() * 100), 2) if ok.any() else None
            res["h"][h] = dict(
                new=dict(unseen=e(np.mean(p_new, 0), ok_new), seen=e(p_seen, ok_new), same_as_now=e(now, ok_new), rows=int(ok_new.sum())),
                none=dict(unseen=e(np.mean(p_none, 0), ok_none), nbr_forecast=e(np.mean(p_nfc, 0), ok_none) if p_nfc else None,
                          neighbours=e(nbr, ok_none), seen=e(p_seen, ok_none), rows=int(ok_none.sum())))
        res["seconds"] = round(time.time() - t0)
        json.dump(res, open(os.path.join(OUT, f"eval_{r}.json"), "w"), indent=1)
        print(f"{r}: done in {res['seconds']} s  " + "  ".join(
            f"+{h}: gcn {res['h'][h]['none']['unseen']} nbr-fc {res['h'][h]['none']['nbr_forecast']} nbrs {res['h'][h]['none']['neighbours']}" for h in H), flush=True)


def summary(data_dir):
    import numpy as np
    D = setup(data_dir)
    rows = [json.load(open(p)) for p in sorted(glob.glob(os.path.join(OUT, "eval_*.json")))]
    meta = dict(ids=D["ids"], seeds=SEEDS_USED, test_range=[f"{D['test_start']:%Y-%m-%d}", f"{D['last_full']:%Y-%m-%d}"],
                roads={x["road"]: dict(ref_week=x["ref_week"], neighbours=x["neighbours"], h=x["h"]) for x in rows},
                trained_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    json.dump(meta, open(os.path.join(OUT, "unseen_meta.json"), "w"), indent=1)
    avg = lambda case, key, h: np.nanmean([x["h"][str(h)][case][key] for x in rows if x["h"][str(h)][case][key] is not None])
    cnt = lambda case, h: sum(1 for x in rows if x["h"][str(h)][case]["unseen"] is not None)
    L = [f"# Unseen roads ({datetime.date.today():%Y-%m-%d})", "",
         "What can the graph model say about a road it never saw? For each of the road stretches below, the GCN was trained "
         "with that road hidden completely (no readings in training or validation) and given the mean road embedding. "
         f"Test week {meta['test_range'][0]} to {meta['test_range'][1]} (one week, one corridor), {len(SEEDS_USED)} seeds per "
         "road and horizon, mean forecast of the seeds. Error = mean absolute error in **percentage points of the road's "
         "normal speed** (lower is better), identical rows within each case. Script: `liveapp/train_unseen.py`.", "",
         "- **New sensor**: the road has just started sending readings (its own last readings are inputs; normal speed from one week of nights).",
         "- **No sensor**: the road is never measured; the forecast comes only from the connected roads through the graph (virtual sensor). "
         "*GCN virtual sensor*: the hidden model's own forecast for the blank road (trained with one random known road blanked "
         "per extra sample). *Neighbours' GCN forecast*: average of the same model's forecasts for the road's graph neighbours. "
         "Baseline *neighbours now*: their current speed ratio.", "",
         "## Average over the roads", "", "| Horizon | No sensor: GCN virtual sensor | No sensor: neighbours' GCN forecast | No sensor: neighbours now | New sensor: GCN | New sensor: same as now | Normal model (saw the road) |",
         "|---|---|---|---|---|---|---|"]
    for h in H:
        L.append(f"| +{h} min ({cnt('none', h)} roads) | {avg('none', 'unseen', h):.1f} | {avg('none', 'nbr_forecast', h):.1f} | {avg('none', 'neighbours', h):.1f} | "
                 f"{avg('new', 'unseen', h):.1f} | {avg('new', 'same_as_now', h):.1f} | {avg('new', 'seen', h):.1f} |")
    L += ["", "## Per road (+60 min)", "", "| Road | No sensor: GCN | Neighbours' forecast | Neighbours now | New sensor: GCN | Same as now | Normal model | Rows (new / none) |",
          "|---|---|---|---|---|---|---|---|"]
    for x in rows:
        a, b = x["h"]["60"]["new"], x["h"]["60"]["none"]
        f = lambda v: "–" if v is None else f"{v:.1f}"
        L.append(f"| {x['road']} | {f(b['unseen'])} | {f(b.get('nbr_forecast'))} | {f(b['neighbours'])} | {f(a['unseen'])} | {f(a['same_as_now'])} | {f(a['seen'])} | {a['rows']} / {b['rows']} |")
    out = os.path.join(ROOT, "modeling", "results", f"unseen-roads-{datetime.date.today():%Y-%m-%d}.md")
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L[:17]))
    print(f"wrote {out}")


SEEDS_USED = [0, 1]

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=os.path.join(HERE, "data", "cache"))
    ap.add_argument("--roads", default="")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--threads", type=int, default=5)
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.summary:
        summary(a.data_dir)
    elif a.roads:
        run_roads(a.roads.split(","), SEEDS_USED, a.data_dir, a.threads)
    else:
        import pandas as pd
        ids = pd.read_csv(os.path.join(ROOT, "collector", "segments.csv"))["segment_id"].tolist()
        parts = [ids[k::a.jobs] for k in range(a.jobs)]
        t0 = time.time()
        procs = [subprocess.Popen([sys.executable, __file__, "--roads", ",".join(p), "--threads", str(a.threads), "--data-dir", a.data_dir])
                 for p in parts]
        codes = [p.wait() for p in procs]
        print(f"all roads trained in {time.time() - t0:.0f} s, exit codes {codes}")
        if all(c == 0 for c in codes):
            summary(a.data_dir)
