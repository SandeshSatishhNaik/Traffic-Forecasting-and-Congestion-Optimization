"""METR-LA check for the re-implemented models, with the standard protocol.

Data: METR-LA (207 loop detectors, Los Angeles, 5-minute speeds, 34,272 steps), as released with DCRNN.
Protocol (DCRNN / Graph WaveNet): 12 past steps -> 12 future steps, 70/10/20 chronological split,
z-score with training statistics, loss and metrics ignore missing (zero) targets, errors at 15, 30 and 60
minutes (steps 3, 6, 12). Adjacency: thresholded Gaussian kernel of road distance (DCRNN).

Differences from the original code, stated plainly: our own PyTorch re-implementations (refmodels.py);
missing inputs are set to 0 after normalisation; the number of epochs and learning-rate schedule are
set by --epochs and are usually shorter than in the papers.

Usage:
  python modeling/metrla.py --data-dir <folder with metr-la.h5, graph_sensor_ids.txt, distances_la_2012.csv> --model stid --epochs 30
  python modeling/metrla.py --data-dir ... --model gwn --epochs 50          # needs a GPU in practice
Published results to compare with (Graph WaveNet paper, Table 2, MAE / RMSE / MAPE):
  15 min 2.69 / 5.15 / 6.90%   30 min 3.07 / 6.22 / 8.37%   60 min 3.53 / 7.37 / 10.01%
"""
import argparse
import json
import os
import time

import h5py
import numpy as np
import pandas as pd
import torch

import refmodels

L = 12


def load(data_dir):
    f = h5py.File(os.path.join(data_dir, "metr-la.h5"), "r")["df"]
    X = f["block0_values"][:].astype(np.float32)
    ts = f["axis1"][:].astype(np.int64)
    sensors = [s.decode() for s in f["axis0"][:]]
    order = open(os.path.join(data_dir, "graph_sensor_ids.txt")).read().strip().split(",")
    assert sensors == order, "sensor order differs from graph_sensor_ids.txt"
    sec = ts // 10 ** 9
    tod = ((sec % 86400) / 300).astype(np.int64) / 288.0
    dow = ((sec // 86400 + 3) % 7).astype(np.int64)      # 1 Jan 1970 was a Thursday
    d = pd.read_csv(os.path.join(data_dir, "distances_la_2012.csv"), dtype={"from": str, "to": str})
    idx = {s: i for i, s in enumerate(sensors)}
    D = np.full((len(sensors),) * 2, np.inf)
    for a, b, c in d.itertuples(index=False):
        if a in idx and b in idx:
            D[idx[a], idx[b]] = c
    finite = D[np.isfinite(D)]
    sigma = finite.std()
    W = np.exp(-np.square(D / sigma))
    W[W < 0.1] = 0
    np.fill_diagonal(W, 0)
    return X, tod.astype(np.float32), dow, W.astype(np.float32)


def metrics(pred, y):
    m = y != 0
    e = (pred - y)[m]
    return dict(MAE=float(np.abs(e).mean()), RMSE=float(np.sqrt((e ** 2).mean())), MAPE=float(100 * (np.abs(e) / y[m]).mean()))


def run(a):
    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    dev = "cuda" if torch.cuda.is_available() and not a.cpu else "cpu"
    torch.set_num_threads(os.cpu_count() or 4)
    X, tod, dow, W = load(a.data_dir)
    if a.nodes:
        X, W = X[:, :a.nodes], W[:a.nodes, :a.nodes]
    T, N = X.shape
    n_s = T - 2 * L + 1
    n_tr, n_va = int(n_s * 0.7), int(n_s * 0.1)
    tr_idx, va_idx, te_idx = np.arange(n_tr), np.arange(n_tr, n_tr + n_va), np.arange(n_tr + n_va, n_s)
    tr_end = n_tr + L
    nz = X[:tr_end][X[:tr_end] != 0]
    mean, std = float(nz.mean()), float(nz.std())
    Xn = np.where(X != 0, (X - mean) / std, 0).astype(np.float32)
    Xn_t, X_t = torch.tensor(Xn), torch.tensor(X)
    tod_t, dow_t = torch.tensor(tod), torch.tensor(dow)
    ar = torch.arange(L)

    def batch(idx):
        i = torch.tensor(idx)[:, None]
        xin = Xn_t[i + ar]                                  # (B, L, N)
        yy = X_t[i + L + ar]                                # (B, L, N) original scale
        todb = tod_t[i + ar][..., None].expand(-1, -1, N)
        dowb = dow_t[i + ar][..., None].expand(-1, -1, N)
        return xin, todb, dowb, yy

    if a.model == "stid":
        net = refmodels.STID(N, L).to(dev)
        fwd = lambda xin, todb, dowb: net(xin[..., None], todb, dowb)
    else:
        net = refmodels.GraphWaveNet(W).to(dev)
        fwd = lambda xin, todb, dowb: net(torch.stack([xin.permute(0, 2, 1), todb.permute(0, 2, 1)], 1))
    print(f"{a.model}: {sum(p.numel() for p in net.parameters())} parameters, device {dev}, nodes {N}, "
          f"train/val/test samples {len(tr_idx)}/{len(va_idx)}/{len(te_idx)}", flush=True)
    opt = torch.optim.Adam(net.parameters(), lr=a.lr, weight_decay=a.wd)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, a.epochs)

    def predict(idx):
        net.eval()
        P, Y = [], []
        with torch.no_grad():
            for i in range(0, len(idx), 128):
                xin, todb, dowb, yy = batch(idx[i:i + 128])
                p = fwd(xin.to(dev), todb.to(dev), dowb.to(dev)).cpu() * std + mean
                P.append(p.permute(0, 2, 1).numpy() if p.shape[1] == L and p.shape[2] == N else p.numpy())
                Y.append(yy.permute(0, 2, 1).numpy())
        return np.concatenate(P).transpose(0, 2, 1), np.concatenate(Y).transpose(0, 2, 1)   # (S, L, N)

    best, best_state, hist = 1e9, None, []
    for ep in range(a.epochs):
        net.train()
        t0 = time.time()
        perm = np.random.permutation(tr_idx)
        tot = 0.0
        steps = len(perm) // a.batch if not a.max_steps else min(a.max_steps, len(perm) // a.batch)
        for s in range(steps):
            xin, todb, dowb, yy = batch(perm[s * a.batch:(s + 1) * a.batch])
            p = fwd(xin.to(dev), todb.to(dev), dowb.to(dev)) * std + mean       # (B, L, N)
            yy = yy.to(dev)
            m = (yy != 0).float()
            loss = ((p - yy).abs() * m).sum() / m.sum().clamp(min=1)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 5)
            opt.step()
            tot += loss.item()
        sched.step()
        P, Y = predict(va_idx)
        v = metrics(P, Y)["MAE"]
        hist.append(dict(epoch=ep + 1, train_mae=tot / steps, val_mae=v, seconds=round(time.time() - t0, 1)))
        print(hist[-1], flush=True)
        if v < best:
            best, best_state = v, {k: x.clone() for k, x in net.state_dict().items()}
    net.load_state_dict(best_state)
    P, Y = predict(te_idx)
    res = {f"{h * 5} min": metrics(P[:, h - 1], Y[:, h - 1]) for h in (3, 6, 12)}
    out = dict(model=a.model, epochs=a.epochs, nodes=N, device=dev, best_val_mae=best, test=res, history=hist,
               published={"15 min": [2.69, 5.15, 6.90], "30 min": [3.07, 6.22, 8.37], "60 min": [3.53, 7.37, 10.01]} if a.model == "gwn" else None)
    print(json.dumps(res), flush=True)
    if a.out:
        json.dump(out, open(a.out, "w"), indent=1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--model", choices=["stid", "gwn"], default="stid")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--wd", type=float, default=1e-5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--nodes", type=int, default=0, help="use only the first N sensors (quick tests)")
    ap.add_argument("--max-steps", type=int, default=0, help="limit training steps per epoch (quick tests)")
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--out", default=None)
    run(ap.parse_args())
