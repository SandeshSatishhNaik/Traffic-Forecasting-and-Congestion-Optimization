"""Re-implementations of two published traffic models, written from the papers.

Graph WaveNet (Wu et al., IJCAI 2019): stacked gated dilated causal convolutions, diffusion graph
convolution over forward and backward transition matrices plus a self-adaptive adjacency matrix learned from
node embeddings, skip connections, direct multi-step output.
STID (Shao et al., CIKM 2022): a plain MLP over each node's recent history plus node, time-of-day and
day-of-week embeddings.

These are our own PyTorch versions, not the authors' code: names, sizes and training settings follow the
papers, and metrla.py checks them against the published METR-LA numbers.
"""
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# ----------------------------------------------------------------------------- STID
class MLPRes(nn.Module):
    def __init__(self, d, drop=0.15):
        super().__init__()
        self.fc1, self.fc2, self.drop = nn.Linear(d, d), nn.Linear(d, d), nn.Dropout(drop)

    def forward(self, x):
        return x + self.fc2(self.drop(F.relu(self.fc1(x))))


class STID(nn.Module):
    """x: (B, L, N, C) values, tod: (B, L, N) in [0,1), dow: (B, L, N) ints 0..6 -> (B, H, N)."""

    def __init__(self, n_nodes, L, C=1, H=12, emb=32, tod_size=288, layers=3, drop=0.15, node_emb=True):
        super().__init__()
        self.n, self.H, self.tod_size = n_nodes, H, tod_size
        self.inp = nn.Linear(L * C, emb)
        self.node = nn.Parameter(torch.empty(n_nodes, emb)) if node_emb else None
        if node_emb:
            nn.init.xavier_uniform_(self.node)
        self.tod = nn.Parameter(torch.empty(tod_size, emb))
        self.dow = nn.Parameter(torch.empty(7, emb))
        nn.init.xavier_uniform_(self.tod)
        nn.init.xavier_uniform_(self.dow)
        d = emb * (3 + (1 if node_emb else 0))
        self.trunk = nn.Sequential(*[MLPRes(d, drop) for _ in range(layers)])
        self.out = nn.Linear(d, H)

    def forward(self, x, tod, dow):
        B, L, N, C = x.shape
        h = self.inp(x.permute(0, 2, 1, 3).reshape(B, N, L * C))
        t = self.tod[(tod[:, -1] * self.tod_size).long().clamp(0, self.tod_size - 1)]
        d = self.dow[dow[:, -1].long()]
        parts = [h, t, d] + ([self.node.expand(B, -1, -1)] if self.node is not None else [])
        z = self.trunk(torch.cat(parts, -1))
        return self.out(z).permute(0, 2, 1)


# ------------------------------------------------------------------------ Graph WaveNet
def transition(A):
    d = A.sum(1)
    d_inv = np.where(d > 0, 1.0 / np.maximum(d, 1e-12), 0.0)
    return (d_inv[:, None] * A).astype(np.float32)


class GCN(nn.Module):
    def __init__(self, c_in, c_out, drop, n_supports, order=2):
        super().__init__()
        self.order = order
        self.mlp = nn.Conv2d((order * n_supports + 1) * c_in, c_out, 1)
        self.drop = drop

    def forward(self, x, supports):
        out = [x]
        for A in supports:
            x1 = torch.einsum("vw,bcwl->bcvl", A, x)
            out.append(x1)
            for _ in range(2, self.order + 1):
                x1 = torch.einsum("vw,bcwl->bcvl", A, x1)
                out.append(x1)
        return F.dropout(self.mlp(torch.cat(out, 1)), self.drop, training=self.training)


class GraphWaveNet(nn.Module):
    """x: (B, C, N, L) -> (B, H, N). Defaults follow the paper's METR-LA setting (8 layers, dilations 1,2,1,2,...)."""

    def __init__(self, A, in_dim=2, H=12, res=32, dil=32, skip=256, end=512, blocks=4, layers=2, k=2, drop=0.3, adaptive=True, graph=True, emb=10):
        super().__init__()
        N = A.shape[0]
        self.graph, self.adaptive, self.drop = graph, adaptive and graph, drop
        self.supports = [torch.tensor(transition(A)), torch.tensor(transition(A.T))] if graph else []
        self.register_buffer("s0", self.supports[0] if graph else torch.zeros(1))
        self.register_buffer("s1", self.supports[1] if graph else torch.zeros(1))
        if self.adaptive:
            self.e1 = nn.Parameter(torch.randn(N, emb) * 0.3)
            self.e2 = nn.Parameter(torch.randn(emb, N) * 0.3)
        n_sup = (2 if graph else 0) + (1 if self.adaptive else 0)
        self.start = nn.Conv2d(in_dim, res, 1)
        self.filt, self.gate, self.skip_c, self.res_c, self.gcn, self.bn = (nn.ModuleList() for _ in range(6))
        self.rf = 1
        for b in range(blocks):
            d = 1
            for l in range(layers):
                self.filt.append(nn.Conv2d(res, dil, (1, k), dilation=(1, d)))
                self.gate.append(nn.Conv2d(res, dil, (1, k), dilation=(1, d)))
                self.skip_c.append(nn.Conv2d(dil, skip, 1))
                self.res_c.append(nn.Conv2d(dil, res, 1))
                self.bn.append(nn.BatchNorm2d(res))
                if graph:
                    self.gcn.append(GCN(dil, res, drop, n_sup))
                self.rf += (k - 1) * d
                d *= 2
        self.end1, self.end2 = nn.Conv2d(skip, end, 1), nn.Conv2d(end, H, 1)

    def forward(self, x):
        L = x.shape[3]
        if L < self.rf:
            x = F.pad(x, (self.rf - L, 0, 0, 0))
        x = self.start(x)
        skip = 0
        sup = []
        if self.graph:
            sup = [self.s0, self.s1]
            if self.adaptive:
                sup.append(F.softmax(F.relu(self.e1 @ self.e2), dim=1))
        for i in range(len(self.filt)):
            r = x
            h = torch.tanh(self.filt[i](r)) * torch.sigmoid(self.gate[i](r))
            s = self.skip_c[i](h)
            skip = s + (skip[..., -s.size(3):] if not isinstance(skip, int) else 0)
            h = self.gcn[i](h, sup) if self.graph else self.res_c[i](h)
            x = self.bn[i](h + r[..., -h.size(3):])
        x = self.end2(F.relu(self.end1(F.relu(skip))))
        return x.squeeze(-1)
