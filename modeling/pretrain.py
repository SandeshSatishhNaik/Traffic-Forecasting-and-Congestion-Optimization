"""Pretrain STID on METR-LA (Los Angeles freeways), then fine-tune on the Bengaluru corridor.

Idea: the shared parts of the network (input layer, time-of-day and day-type embeddings, residual MLP trunk,
output layer) may carry general knowledge about how speeds evolve; the node embeddings are specific to each
road network and are learned from scratch. Both datasets are expressed the same way: speed divided by the
road's fixed reference speed (95th percentile of night-time speed), 15-minute steps, 6 past steps, targets
+15, +30 and +60 minutes. METR-LA's 5-minute series is split into three 15-minute series (offsets 0, 1, 2).

Three Bengaluru models are compared on the same rows (5 seeds each): trained from scratch, pretrained then
all weights fine-tuned, pretrained with the trunk frozen. Honest expectation: little or no gain, because
Bengaluru's roads, congestion and calendar differ from Los Angeles freeways in 2012.

Usage: python modeling/pretrain.py --metrla-dir <folder> --data-dir <Bengaluru folder> --rows rows.pkl --out modeling/results/pretrain.md
"""
import argparse
import os

import numpy as np
import pandas as pd
import torch

import evaluate_ref as E
import metrla
import refbengaluru as rb
import refmodels

LB, KS = rb.LB, rb.KS


def metrla_windows(metrla_dir, offsets=(0, 1, 2)):
    X, tod5, dow, W = metrla.load(metrla_dir)
    T, N = X.shape
    n_tr = int(T * 0.7)
    night = np.array([(h >= 22 or h < 6) for h in (tod5 * 24).astype(int)])
    tr = X[:n_tr]
    ref = np.array([np.quantile(tr[night[:n_tr] & (tr[:, j] > 0), j], 0.95) for j in range(N)], dtype=np.float32)
    daytype = (dow >= 5).astype(np.int64)
    parts = {"train": [], "val": []}
    for off in offsets:
        S = X[off::3] / ref
        M = X[off::3] > 0
        Sf = np.where(M, np.clip(S, 0, 1.5), 1.0).astype(np.float32)
        T3 = len(Sf)
        todo, dto = tod5[off::3], daytype[off::3]
        idx = np.arange(LB - 1, T3 - max(KS))
        V = np.stack([Sf[idx - l] for l in range(LB - 1, -1, -1)], 1)
        MM = np.stack([M[idx - l] for l in range(LB - 1, -1, -1)], 1).astype(np.float32)
        tod = np.stack([todo[idx - l] for l in range(LB - 1, -1, -1)], 1).astype(np.float32)
        Y = np.stack([Sf[idx + k] for k in KS], -1)
        YM = np.stack([M[idx + k] for k in KS], -1)
        d = dict(V=V, M=MM, tod=tod, dt=dto[idx], Y=Y, YM=YM, last_present=M[idx])
        cut_tr, cut_va = int(0.7 * len(idx)), int(0.8 * len(idx))
        parts["train"].append({k: v[:cut_tr] for k, v in d.items()})
        parts["val"].append({k: v[cut_tr:cut_va] for k, v in d.items()})
    cat = lambda L: {k: np.concatenate([p[k] for p in L]) for k in L[0]}
    return cat(parts["train"]), cat(parts["val"]), W


def pretrain(metrla_dir, epochs, seed=0):
    tr, va, W = metrla_windows(metrla_dir)
    print("METR-LA windows: train", len(tr["V"]), "val", len(va["V"]), flush=True)
    hp = dict(rb.HP, epochs=epochs, patience=6, lr=2e-3, wd=1e-5, batch=128)
    P, best, net = rb.fit_predict("stid", None, tr, va, va, seed, hp, return_net=True, verbose=True)
    print("pretraining done, best validation error (% of normal speed):", round(best * 100, 2), flush=True)
    return net.state_dict(), best


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrla-dir", required=True)
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--rows", required=True)
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--out", default=None)
    ap.add_argument("--state", default=None, help="save / reuse the pretrained weights (.pt)")
    a = ap.parse_args()
    if a.state and os.path.exists(a.state):
        state = torch.load(a.state)
    else:
        state, _ = pretrain(a.metrla_dir, a.epochs)
        if a.state:
            torch.save(state, a.state)
    rows = pd.read_pickle(a.rows)
    scratch, ids = E.run(a.data_dir, rows, kinds=("stid",), tag="stid")
    ft_hp = dict(lr=1e-3, epochs=100, patience=15)
    pre, _ = E.run(a.data_dir, scratch, kinds=("stid",), hp=ft_hp, pre_state=state, tag="stid_pre")
    fro, _ = E.run(a.data_dir, pre, kinds=("stid",), hp=ft_hp, pre_state=state, freeze_trunk=True, tag="stid_frozen")
    md = E.table(fro, ("stid", "stid_pre", "stid_frozen"), extra=("Persistence (last value)", "GCN: graph"))
    print(md)
    if a.out:
        open(a.out, "w").write(md + "\n")
