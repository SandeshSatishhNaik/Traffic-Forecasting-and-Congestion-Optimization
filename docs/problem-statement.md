# Problem Statement

## As given (verbatim)

> AI-Driven Spatio-Temporal Traffic Intelligence System for Traffic Forecasting and Congestion Optimization

Status: **title only**. No scope, dataset, metrics, deliverables or timeline have been provided yet.

## Decomposition of the title

| Phrase | What it commits the project to |
|---|---|
| Spatio-temporal | Model the road network as a graph (sensors/intersections = nodes, road links = edges) and traffic as a time series on every node. Points to graph-based deep learning (STGCN, DCRNN, Graph WaveNet, AGCRN, GMAN, transformer variants). |
| Traffic forecasting | Predict speed / flow / occupancy per node for short horizons (typically 15, 30, 60 min). Standard metrics: MAE, RMSE, MAPE. |
| Congestion optimization | **Undefined.** Could mean adaptive signal control, route guidance, ramp metering, or congestion hotspot alerts with recommendations. Each is a different sub-project. |
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
