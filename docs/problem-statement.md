# Problem Statement

## As given (verbatim)

> AI-Driven Spatio-Temporal Traffic Intelligence System for Traffic Forecasting and Congestion Optimization

Status: **title only**. No scope, dataset, metrics, deliverables or timeline have been provided yet.

## Clarified core problem (from the team)

> Predict upcoming traffic patterns for a region. Treat the region as zones/locations, and forecast the traffic for the near future from previous (historical) data.

Formally: given the past `T` time steps of traffic measurements (speed or flow) at `N` locations in a region, predict the next `T'` steps at all `N` locations.

```
input  X[t-T+1 .. t]   shape (T,  N, C)   C = features per location (speed, flow, time-of-day, ...)
output Y[t+1 .. t+T']  shape (T', N)
```

Common default: 5-minute intervals, `T = 12` (past 1 hour) → `T' = 12` (next 1 hour), reported at 15 / 30 / 60 min.

**Scope decision:** keep "Congestion Optimization" in the title. It is delivered as **route recommendation**: every road segment's cost is its length divided by the speed predicted for the moment you reach it, and Dijkstra's algorithm picks the lowest-cost route. Congestion alerts (predicted speed vs. free-flow speed) come from the same forecasts.

Visual blueprint of the whole system and its data: https://claude.ai/artifact/JbCUopciFya99bA96hnMvn

## Decomposition of the title

| Phrase | What it commits the project to |
|---|---|
| Spatio-temporal | Model the road network as a graph (sensors/intersections = nodes, road links = edges) and traffic as a time series on every node. Points to graph-based deep learning (STGCN, DCRNN, Graph WaveNet, AGCRN, GMAN, transformer variants). |
| Traffic forecasting | Predict speed / flow / occupancy per node for short horizons (typically 15, 30, 60 min). Standard metrics: MAE, RMSE, MAPE. |
| Congestion optimization | **Decided: route recommendation** plus congestion alerts, both driven by the forecasts. (Signal control, ramp metering were considered and not chosen.) |
| Intelligence system | An end-to-end system, not only a trained model: data pipeline → model → API → dashboard/map. |
| AI-driven | Learned models (deep learning and/or reinforcement learning) rather than rule-based only. |

## Key design risk: forecasting data vs. optimization environment

- Standard forecasting benchmarks (METR-LA, PEMS-BAY, PEMS03/04/07/08) are **freeway loop-detector** data.
- Traffic **signal** optimization happens at **urban intersections**, which those datasets do not contain, and cannot be tested on real roads — it needs a simulator (SUMO or CityFlow).
- So "forecast on PeMS + optimize signals" is two disconnected projects unless deliberately bridged.

Coherent options:

1. **Forecast → route guidance (lowest cost).** Forecast speeds on a benchmark network, convert to predicted travel times, compute congestion-aware routes. Same graph for both halves; no simulator.
2. **Simulator-closed loop (highest cost).** Build an urban network in SUMO/CityFlow, generate traffic, train the forecaster on simulated data, use forecasts as state for an RL signal controller. Coherent but synthetic data.
3. **Hybrid.** Real-data forecasting on a benchmark + a separate SUMO signal-control study. Common in student projects; weakest integration story.

## Open questions (must be answered before design)

1. What does "congestion optimization" mean to the evaluator: signal control, routing, or recommendations?
2. Is there a fuller brief (abstract, guide's notes, rubric) beyond this title?
3. Is data provided, or must public data be used? Must it be a specific city/region?
4. Deliverables: report, working demo, dashboard, paper?
5. Timeline, team size, available compute (laptop / Colab / GPU)?
