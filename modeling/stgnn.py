"""Small spatio-temporal graph network for the corridor, with ablations.

All 21 road stretches are predicted together. Each stretch gets, for the last three 15-minute slots,
its speed relative to its fixed reference speed (plus a "reading present" mask), the time of day,
a weekend flag and rain. Two graph-convolution layers mix each stretch with its neighbours in the
road graph, then a linear layer predicts the speed `h` minutes ahead.

Variants (same code, same data, only the graph differs):
  none      identity graph: every road is forecast from its own history (plus a road embedding)
  graph     road graph from collector/network/links.csv (flow links and crossings, both directions)
  adaptive  road graph plus a learned adjacency (Graph WaveNet style)

Missing readings (roads are read less often outside the rush-hour windows) are filled with 1.0 (the
reference speed) and flagged by the mask, and the loss only counts targets that exist.
"""
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

import prepare

LAGS = 3
DEFAULT_HP = dict(hid=32, emb=8, drop=0.1, lr=3e-3, wd=1e-4, batch=64, lags=3)
VARIANTS = ("none", "graph", "adaptive")


def configure(**hp):
    """Set the hyper-parameters used by every later call (including the number of input lags)."""
    global LAGS
    DEFAULT_HP.update(hp)
    LAGS = int(DEFAULT_HP["lags"])


def norm_adj(A):
    A = A + A.T
    A = (A > 0).astype(np.float32) + np.eye(len(A), dtype=np.float32)
    return A / A.sum(1, keepdims=True)


def make_tensors(grid, ref, weather, h):
    """X (S,N,C), Y (S,N), masks and slot times for every slot that has an input and a target."""
    k = h // prepare.SLOT_MIN
    S = (grid / ref).clip(0, 1.5).values.astype(np.float32)
    M = ~np.isnan(S)
    Sf = np.where(M, S, 1.0).astype(np.float32)
    T, N = S.shape
    idx = np.arange(LAGS - 1, T - k)
    vals = np.stack([Sf[idx - l] for l in range(LAGS)], -1)           # (S,N,LAGS)
    msk = np.stack([M[idx - l] for l in range(LAGS)], -1).astype(np.float32)
    t = grid.index[idx]
    mod = (t.hour * 60 + t.minute).values
    tf = np.stack([np.sin(2 * np.pi * mod / 1440), np.cos(2 * np.pi * mod / 1440),
                   (prepare.day_type(t) != "weekday").astype(float),
                   weather.reindex(t, method="nearest", tolerance=pd.Timedelta("30min")).fillna(0).values.clip(0, 5) / 5], 1)
    tf = np.repeat(tf[:, None, :], N, 1).astype(np.float32)
    X = np.concatenate([vals, msk, tf], -1)
    Y = Sf[idx + k]
    YM = M[idx + k]
    keep = (M[idx].sum(1) >= 1) & (YM.sum(1) >= 1)
    return X[keep], Y[keep], YM[keep], M[idx][keep], t[keep]


class Net(nn.Module):
    def __init__(self, A, variant, c_in, hid=32, emb=8, drop=0.1):
        super().__init__()
        N = A.shape[0]
        self.variant = variant
        self.register_buffer("A", torch.tensor(norm_adj(A) if variant != "none" else np.eye(N, dtype=np.float32)))
        if variant == "adaptive":
            self.e1 = nn.Parameter(torch.randn(N, 8) * 0.3)
            self.e2 = nn.Parameter(torch.randn(N, 8) * 0.3)
        self.emb = nn.Parameter(torch.randn(N, emb) * 0.1)
        self.l1s, self.l1n = nn.Linear(c_in + emb, hid), nn.Linear(c_in + emb, hid, bias=False)
        self.l2s, self.l2n = nn.Linear(hid, hid), nn.Linear(hid, hid, bias=False)
        self.out = nn.Linear(hid + c_in, 1)
        self.drop = nn.Dropout(drop)

    def adj(self):
        if self.variant == "adaptive":
            return 0.5 * self.A + 0.5 * torch.softmax(torch.relu(self.e1 @ self.e2.T), dim=1)
        return self.A

    def forward(self, x):
        B, N, _ = x.shape
        A = self.adj()
        x = torch.cat([x, self.emb.expand(B, -1, -1)], -1)
        h = torch.relu(self.l1s(x) + self.l1n(A @ x))
        h = self.drop(h)
        h = torch.relu(self.l2s(h) + self.l2n(A @ h))
        return self.out(torch.cat([h, x[..., :-self.emb.shape[1]]], -1)).squeeze(-1)


def masked_l1(p, y, m):
    return ((p - y).abs() * m).sum() / m.sum().clamp(min=1)


def train_predict(tr, va, te, A, variant, seed, epochs=200, patience=25, hp=None, history=None):
    hp = {**DEFAULT_HP, **(hp or {})}
    torch.manual_seed(seed)
    np.random.seed(seed)
    f = lambda a: torch.tensor(a)
    Xtr, Ytr, Mtr = f(tr[0]), f(tr[1]), f(tr[2].astype(np.float32))
    Xva, Yva, Mva = f(va[0]), f(va[1]), f(va[2].astype(np.float32) * va[3][:, :].astype(np.float32))
    net = Net(A, variant, Xtr.shape[-1], hid=hp["hid"], emb=hp["emb"], drop=hp["drop"])
    opt = torch.optim.Adam(net.parameters(), lr=hp["lr"], weight_decay=hp["wd"])
    best, best_state, bad = 1e9, None, 0
    n = len(Xtr)
    for ep in range(epochs):
        net.train()
        perm = torch.randperm(n)
        tot = 0.0
        for i in range(0, n, hp["batch"]):
            b = perm[i:i + hp["batch"]]
            opt.zero_grad()
            loss = masked_l1(net(Xtr[b]), Ytr[b], Mtr[b])
            loss.backward()
            opt.step()
            tot += loss.item() * len(b)
        net.eval()
        with torch.no_grad():
            v = masked_l1(net(Xva), Yva, Mva).item()
        if history is not None:
            history.append((tot / n, v))
        if v < best - 1e-5:
            best, bad = v, 0
            best_state = {k: x.clone() for k, x in net.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    net.load_state_dict(best_state)
    net.eval()
    with torch.no_grad():
        return net(f(te[0])).numpy(), best, ep


def make_inputs(grid, ref, weather):
    """Inputs for every slot (no target needed): X (S,N,C) and the slot times, for forecasting from `t`."""
    S = (grid / ref).clip(0, 1.5).values.astype(np.float32)
    M = ~np.isnan(S)
    Sf = np.where(M, S, 1.0).astype(np.float32)
    T, N = S.shape
    idx = np.arange(LAGS - 1, T)
    vals = np.stack([Sf[idx - l] for l in range(LAGS)], -1)
    msk = np.stack([M[idx - l] for l in range(LAGS)], -1).astype(np.float32)
    t = grid.index[idx]
    mod = (t.hour * 60 + t.minute).values
    tf = np.stack([np.sin(2 * np.pi * mod / 1440), np.cos(2 * np.pi * mod / 1440),
                   (prepare.day_type(t) != "weekday").astype(float),
                   weather.reindex(t, method="nearest", tolerance=pd.Timedelta("30min")).fillna(0).values.clip(0, 5) / 5], 1)
    tf = np.repeat(tf[:, None, :], N, 1).astype(np.float32)
    return np.concatenate([vals, msk, tf], -1), t
