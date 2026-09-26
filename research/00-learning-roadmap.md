# Learning & Research Roadmap

Goal: go from zero to a defensible spatio-temporal traffic forecasting system, learning each concept in the order the project needs it.

Each stage has a **checkpoint** — a small thing you build to prove you understood it. Don't move on until the checkpoint works.

---

## Decision 0 — What is a "zone"?

This choice decides the data, the models and the papers you read. Make it first.

| Option | What a "zone" is | Typical data | Model family | Verdict |
|---|---|---|---|---|
| **A. Sensor graph** | A road sensor / segment; zones connected by roads | METR-LA, PEMS-BAY, PEMS04/08, LargeST | Spatio-temporal GNNs (DCRNN, Graph WaveNet, ...) | **Recommended.** Largest literature, standard benchmarks, matches "spatio-temporal" in the title. |
| B. City grid | City split into square cells; predict inflow/outflow per cell | TaxiBJ, BikeNYC | CNN-based (ST-ResNet, ConvLSTM) | Older line of work (2017–2019); fewer recent papers. |
| C. Admin zones | Named districts / taxi zones; predict demand or OD flow | NYC TLC taxi zones | GNNs on a zone adjacency graph | Good if you need "regions" literally; messier data prep. |

---

## Stage 1 — Time-series fundamentals

**Learn**
- Trend, seasonality, periodicity. Traffic has strong **daily** and **weekly** cycles (rush hours, weekends).
- Sliding-window framing: turn a long series into (past window → future window) samples.
- **Chronological** train/val/test split (typically 70/10/20). Never shuffle before splitting — that leaks the future into training.
- Normalization (z-score) using **training-set statistics only**.
- Metrics: MAE, RMSE, MAPE. In METR-LA, `0` means *missing*, so metrics must be **masked** (ignore zeros), otherwise results are wrong.

**Checkpoint:** load METR-LA, plot one sensor for one week, and point out the rush-hour dips and the weekend difference.

---

## Stage 2 — Baselines (the numbers every model must beat)

**Learn**
- Historical Average (HA): predict the average for that sensor at that time-of-day/day-of-week.
- Last-value / naive persistence.
- ARIMA / VAR (classical statistics).
- Gradient boosting (XGBoost/LightGBM) with lag + time-of-day features.

**Why:** an examiner's first question is "better than what?". A deep model that barely beats HA is not a result.

**Checkpoint:** a table of MAE/RMSE/MAPE at 15/30/60 min for HA and XGBoost on METR-LA.

---

## Stage 3 — Deep sequence models (time only)

**Learn**
- RNN → LSTM / GRU; encoder–decoder (seq2seq) for multi-step output.
- Temporal convolution (TCN, dilated causal convolutions).
- PyTorch training loop, early stopping, learning-rate schedules.

**Limitation to notice:** these treat each sensor independently (or all sensors as one flat vector), ignoring road connectivity. That gap motivates Stage 4.

**Checkpoint:** an LSTM seq2seq that beats HA at the 15-min horizon.

---

## Stage 4 — Graphs (space)

**Learn**
- Graph basics: nodes, edges, adjacency matrix, degree, Laplacian.
- Building the road graph: pairwise road distances → Gaussian kernel → threshold small weights (the DCRNN recipe).
- Graph convolution: spectral (ChebNet), spatial (GCN), **diffusion convolution** (directed roads).
- Learned / adaptive adjacency (let the model discover hidden links).

**Checkpoint:** build the METR-LA adjacency matrix yourself and visualize the sensors + edges on a map.

---

## Stage 5 — Spatio-temporal GNNs (the core of the project)

Read in this order — each paper fixes a weakness of the one before.

| # | Model | Venue | Key idea |
|---|---|---|---|
| 1 | STGCN | IJCAI 2018 | Graph conv (space) + temporal conv (time), fully convolutional |
| 2 | DCRNN | ICLR 2018 | Diffusion conv inside a GRU seq2seq; handles directed roads |
| 3 | Graph WaveNet | IJCAI 2019 | Learns an adaptive adjacency matrix + dilated temporal conv |
| 4 | ASTGCN | AAAI 2019 | Spatial & temporal attention; uses daily/weekly periodic inputs |
| 5 | AGCRN | NeurIPS 2020 | Node-specific parameters + learned graph; no predefined graph needed |
| 6 | GMAN | AAAI 2020 | Attention-based encoder–decoder, strong at long horizons |
| 7 | STID | CIKM 2022 | Just MLPs + spatial/time-of-day ID embeddings — matches complex GNNs |
| 8 | STAEformer | CIKM 2023 | Transformer with adaptive embeddings; strong recent baseline |

**Lesson from 7–8:** simple models with good embeddings rival complex GNNs. Worth knowing before you claim a novel architecture.

**Checkpoint:** run Graph WaveNet (or STID) through a benchmark library and reproduce the published METR-LA MAE within a small margin.

---

## Stage 6 — Tooling (don't write everything from scratch)

| Tool | Use |
|---|---|
| [BasicTS](https://github.com/GestaltCogTeam/BasicTS) | Fair benchmark toolkit; many models + datasets ready to run |
| [LibCity](https://github.com/LibCity/Bigscity-LibCity) | Urban spatio-temporal library; paper list at `LibCity/Bigscity-LibCity-PaperList` |
| [LargeST](https://github.com/liuxu77/LargeST) | Large-scale California dataset (NeurIPS 2023) for scaling experiments |
| PyTorch Geometric Temporal | GNN building blocks if you write your own model |

---

## Stage 7 — From model to "system"

- Serve predictions via an API (e.g. FastAPI).
- Map dashboard: sensors coloured by predicted speed at +15/+30/+60 min.
- **Congestion layer** (cheap, makes the title honest): convert predicted speed into levels (e.g. free / slow / congested relative to each sensor's free-flow speed) and raise early warnings for sensors predicted to become congested.
- Optional "optimization" extension: turn predicted speeds into predicted travel times and suggest a less-congested route. Only claim "optimization" if this exists.

---

## Datasets (start here)

| Dataset | Content | Size |
|---|---|---|
| METR-LA | Speed, LA County highway loop detectors, 5-min | 207 sensors, 2012 |
| PEMS-BAY | Speed, Bay Area (Caltrans PeMS), 5-min | 325 sensors, ~6 months of 2017 |
| PEMS04 / PEMS08 | Flow, California districts, 5-min | 307 / 170 sensors |
| LargeST | Flow, all of California | ~8,600 sensors, multi-year |

All are freeway data. If the project must use a specific local city, expect to spend significant time finding/collecting data — do the learning on METR-LA first either way.

---

## Common mistakes that invalidate results

1. Random (non-chronological) train/test split → future leakage.
2. Normalizing with statistics computed on the full dataset.
3. Unmasked metrics on METR-LA (zeros = missing).
4. Reporting only one horizon, or only the average — report 15/30/60 min.
5. Comparing only against weak baselines (skip HA/LSTM → claims look inflated; skip STID/Graph WaveNet → claims look unchallenged).

---

## Open decisions

- [ ] Zone definition: A / B / C (recommended: A)
- [ ] Keep "Congestion Optimization" in the title (build the Stage 7 extension) or rename
- [ ] Target region: public benchmark only, or a specific city
- [ ] Timeline, team split, compute (laptop / Colab / GPU)
