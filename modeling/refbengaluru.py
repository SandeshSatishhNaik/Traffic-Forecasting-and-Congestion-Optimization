"""Graph WaveNet and STID (refmodels.py) on the Bengaluru corridor, scored on the same rows as evaluate.py.

Adaptation to our data, stated plainly:
  - history: 6 slots of 15 minutes (1.5 h) instead of 12 steps; roads are read every 15 min only in the
    rush-hour windows, so missing slots are filled with the road's normal speed and flagged by a mask channel
    (an addition to the original input of speed and time of day);
  - Graph WaveNet uses 2 blocks of 2 layers (receptive field 7) instead of 4 blocks (13), 21 nodes, dropout 0.2;
  - one model predicts +15, +30 and +60 minutes together (loss counts only targets that exist);
  - STID: node, time-of-day (96 slots) and day-type (weekday vs weekend/holiday) embeddings.
Speeds are divided by each road's fixed reference speed, as for the other models.
"""
import numpy as np
import pandas as pd
import torch

import prepare
import refmodels

LB = 6
KS = (1, 2, 4)            # +15, +30, +60 minutes in 15-minute slots
HP = dict(lr=2e-3, wd=1e-4, batch=64, epochs=150, patience=20)


def make_seq(grid, ref, weather):
    S = (grid / ref).clip(0, 1.5).values.astype(np.float32)
    M = ~np.isnan(S)
    Sf = np.where(M, S, 1.0).astype(np.float32)
    T, N = S.shape
    idx = np.arange(LB - 1, T)
    V = np.stack([Sf[idx - l] for l in range(LB - 1, -1, -1)], 1)            # (S, LB, N) oldest first
    MM = np.stack([M[idx - l] for l in range(LB - 1, -1, -1)], 1).astype(np.float32)
    t = grid.index[idx]
    modall = ((grid.index.hour * 60 + grid.index.minute) / 1440).values.astype(np.float32)
    tod = np.stack([modall[idx - l] for l in range(LB - 1, -1, -1)], 1)
    dt = (prepare.day_type(pd.DatetimeIndex(t)) != "weekday").astype(np.int64)
    Y = np.zeros((len(idx), N, len(KS)), np.float32)
    YM = np.zeros((len(idx), N, len(KS)), bool)
    for j, k in enumerate(KS):
        ok = idx + k < T
        Y[ok, :, j] = Sf[idx[ok] + k]
        YM[ok, :, j] = M[idx[ok] + k]
    return dict(V=V, M=MM, tod=tod, dt=dt, Y=Y, YM=YM, t=t, last_present=M[idx])


def _forward(kind, net, b):
    V, M, tod, dt = b
    B, L, N = V.shape
    if kind == "stid":
        x = torch.stack([V, M], -1)
        return net(x, tod[..., None].expand(-1, -1, N), dt[:, None, None].expand(-1, L, N)).permute(0, 2, 1)      # (B, N, H)
    x = torch.stack([V.permute(0, 2, 1), M.permute(0, 2, 1), tod[:, None, :].expand(-1, N, -1)], 1)              # (B, 3, N, L)
    return net(x).permute(0, 2, 1)


def _tens(d, sel):
    return (torch.tensor(d["V"][sel]), torch.tensor(d["M"][sel]), torch.tensor(d["tod"][sel]), torch.tensor(d["dt"][sel]))


def fit_predict(kind, A, tr, va, te, seed, hp=None, pre_state=None, freeze_trunk=False, return_net=False, verbose=False):
    hp = {**HP, **(hp or {})}
    torch.manual_seed(seed)
    np.random.seed(seed)
    N = tr["V"].shape[2]
    if kind == "stid":
        net = refmodels.STID(N, LB, C=2, H=len(KS), tod_size=96, emb=32, layers=3, drop=0.15)
    else:
        net = refmodels.GraphWaveNet(A, in_dim=3, H=len(KS), blocks=2, layers=2, drop=0.2, res=32, dil=32, skip=128, end=256)
    if pre_state is not None:
        own = net.state_dict()
        net.load_state_dict({k: v for k, v in pre_state.items() if k in own and own[k].shape == v.shape}, strict=False)
    Btr, Bva, Bte = _tens(tr, slice(None)), _tens(va, slice(None)), _tens(te, slice(None))
    Ytr, Mtr = torch.tensor(tr["Y"]), torch.tensor(tr["YM"].astype(np.float32))
    Yva, Mva = torch.tensor(va["Y"]), torch.tensor((va["YM"] & va["last_present"][..., None]).astype(np.float32))
    params = [p for n, p in net.named_parameters() if not (freeze_trunk and n.startswith(("trunk", "inp")))]
    opt = torch.optim.Adam(params, lr=hp["lr"], weight_decay=hp["wd"])
    n = len(Ytr)
    best, bad, state = 1e9, 0, None
    for ep in range(hp["epochs"]):
        net.train()
        perm = torch.randperm(n)
        for i in range(0, n, hp["batch"]):
            b = perm[i:i + hp["batch"]]
            opt.zero_grad()
            p = _forward(kind, net, tuple(x[b] for x in Btr))
            loss = ((p - Ytr[b]).abs() * Mtr[b]).sum() / Mtr[b].sum().clamp(min=1)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 5)
            opt.step()
        net.eval()
        with torch.no_grad():
            v = (((_forward(kind, net, Bva) - Yva).abs() * Mva).sum() / Mva.sum().clamp(min=1)).item()
        if verbose and ep % 10 == 0:
            print(ep, round(loss.item() * 100, 2), round(v * 100, 2), flush=True)
        if v < best - 1e-5:
            best, bad, state = v, 0, {k: x.clone() for k, x in net.state_dict().items()}
        else:
            bad += 1
            if bad >= hp["patience"]:
                break
    net.load_state_dict(state)
    net.eval()
    with torch.no_grad():
        P = _forward(kind, net, Bte).numpy()
    return (P, best, net) if return_net else (P, best)
