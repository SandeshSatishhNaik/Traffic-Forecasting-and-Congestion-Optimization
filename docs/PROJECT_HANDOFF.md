# Project handoff: everything a new session needs to know

Written 26 November 2026 at the end of the cloud development session, for the team and for local Claude Code
sessions. `CLAUDE.md` (repository root) has the short rules; this file has the full picture. Numbers here are
measured unless marked otherwise; where they come from is given in brackets.

---

## 1. The project in one paragraph

"AI-Driven Spatio-Temporal Traffic Intelligence System for Traffic Forecasting and Congestion Optimization", a
Project Based Learning project (GM University, Davanagere; Semester III, UE24CS2306). It forecasts road speed
15, 30 and 60 minutes ahead on 21 connected road stretches of Bengaluru's Outer Ring Road (ORR), using real
TomTom readings collected by our own pipeline and a Graph Convolutional Network over the road graph, and turns
the forecasts into congestion alerts, trip-time estimates and route recommendations (time-dependent Dijkstra),
shown in a local web app. "Optimization" in the title means alerts plus route recommendation.

Repository: `github.com/SandeshSatishhNaik/Traffic-Forecasting-and-Congestion-Optimization`, branch
`claude/brave-galileo-igwv6s` (also the default branch). Team names and USNs are still placeholders in the
reports and decks.

---

## 2. Data

| Item | Detail |
|---|---|
| Source | TomTom Traffic Flow (Flow Segment Data): current speed, free-flow speed, travel time, confidence, segment shape; Open-Meteo weather (rain); TomTom incidents (logged, not used by any model yet) |
| Area | ORR from Silk Board towards KR Puram, both directions (17 "core" stretches) + 4 "context" feeder stretches (Hosur Road x2, Old Airport Road, Varthur Road) = 21 |
| Since | 27 Sep 2026 (first 10 stretches); the 21-stretch network from 30 Sep 2026 10:40 (`prepare.FIRST_READING`) |
| Schedule (IST) | core: 32 readings a day (every 15 min in the two rush windows, 30 min around them, 2 h at night); context: 13 a day. 596 requests a day = 18,476 in a 31-day month, inside the 20,000 free tier |
| Pipeline | GitHub Actions chain (`collect-bengaluru.yml` runs `collector/loop.sh`, restarts itself about every 5.5 h, backup cron every 3 h) writes monthly CSVs to the `bengaluru-data` branch. `collector/run_local.py` does the same on a laptop |
| Size | Phase 2 results: 33 days, 19,093 valid readings. By 25 Nov: 33,363 readings, 596 on every full day except 17 Nov (579) |
| Licence | TomTom terms forbid publishing or storing readings publicly. The repository is public, so raw data must not be committed. The data branch is still public: moving it to the private repository failed because the `DATA_REPO_TOKEN` secret lacks write access (HTTP 403). A permission email to TomTom is drafted (`research/05-tomtom-permission-email.md`), not sent |

Files: `tomtom_flow/YYYY-MM.csv` (columns: timestamp_utc, timestamp_ist, segment_id, status, frc,
current_speed_kmph, free_flow_speed_kmph, current/free_flow travel time, confidence, road_closure, segment start
and end coordinates), `weather/YYYY-MM.csv`, `incidents/YYYY-MM.csv`.

## 3. Road network

- `collector/build_network.py` walks each road with TomTom requests, links stretches into a graph and adds
  OpenStreetMap features. Output in `collector/network/`: `links.csv` (flow links: A leads into B; crossings:
  roads that meet at a junction), `features.csv` (lanes, speed limit, signals, intersections, schools,
  hospitals, offices, bus stops, metro per stretch; **not yet used by the models**), `legacy_ids.csv`.
- `segments.csv` is what the collector reads: id, request point, route, tier, length, road class.
- Extra parallel roads for real route choice (Sarjapur Road, Whitefield, Old Madras Road): first build failed
  verification (5 of 13 stretches matched the expected road name; matches were 14 to 23 km long). Not collected.
  `collector/ALT_ROADS.md` has the plan; `collector/quota_plan.py` shows at most 12 extra stretches fit, and only
  with a trimmed schedule.

## 4. Pre-processing (modeling/prepare.py)

15-minute grid (:07, :22, :37, :52 IST); missing readings masked, never filled for scoring; speed divided by a
fixed reference speed per road (95th percentile of night speeds in the training period); calendar features
(time of day, weekday versus weekend/holiday); rain; road adjacency from `links.csv`. Holidays (`HOLIDAYS`):
2 Oct, 19-21 Oct (Dasara, confirmed by weekend-level speeds), 1, 8, 10 and 27 Nov (official Karnataka list) and
9 Nov (Deepavali bridge day: rush-hour speed ratio 0.98, against 0.66-0.73 on ordinary weekdays).

Phase 2 split: train before 18 Oct, validate 18-24 Oct, test 25-31 Oct 2026. All models scored on identical rows.

## 5. Models and results (Phase 2, test week 25-31 Oct, MAE km/h, lower is better)

| Model | 15 min | 30 min | 60 min | Role |
|---|---|---|---|---|
| Persistence (last value) | 3.16 | 3.91 | 4.42 | floor |
| Historical Average | 4.14 | 4.11 | 3.90 | floor |
| Gradient Boosting, own history (scikit-learn HistGradientBoostingRegressor) | 3.32 | 3.71 | 3.82 | classical rival |
| Gradient Boosting, all roads | 3.19 | 3.58 | 3.77 | strongest classical rival |
| GCN, no graph | 3.29 | 3.63 | 3.75 | ablation |
| **GCN + road graph (tuned)** | **2.99** | **3.33** | **3.46** | **the model used for alerts, trips, routes and the apps** |
| GCN + road graph + learned graph | 2.99 | 3.35 | 3.49 | ablation |
| Graph WaveNet (our re-implementation) | 2.99 | 3.49 | 3.85 | literature; overfits a month of data |
| STID (our re-implementation; no graph) | 2.99 | 3.33 | 3.41 | literature; ties the GCN |
| STID pretrained on METR-LA, fine-tuned | 2.92 | 3.27 | 3.33 | transfer; about 2% better than STID from scratch (control with the same settings: 3.01 / 3.37 / 3.43) |
| STID pretrained, trunk frozen | 2.96 | 3.35 | 3.41 | transfer; no gain |

Neural models: mean of 5 seeds (spread 0.01-0.05). Sources: `modeling/results/phase2-models-tuned-2026-11-01.md`,
`phase2-reference-models-2026-11-01.md`, `phase2-pretraining-2026-11-01.md`.

What the numbers support, honestly:
- Adding the road graph lowers **our GCN's** error by 8-9%; at 60 min the GCN is 22% better than persistence.
- STID, which has no graph, reaches similar accuracy, so on 33 days model design matters as much as the graph.
  Do not claim "the graph is what makes forecasts better" in general.
- Pretrained STID scored best, but on one pretraining run and one test week.
- The GCN is the output model because the "does the graph help?" experiment and the decision pipeline are built
  on it, not because it scored best.

Our GCN (`modeling/stgnn.py`): two graph-convolution layers over the road graph, then a linear layer; one model
per horizon; inputs per road: last 3 readings (speed / reference) + missing flags + time of day + weekend flag +
rain. Tuned by random search (`tune.py`, 30 trials x 3 seeds, pre-test data only): hidden 64, embedding 4,
dropout 0.2, learning rate 0.003, weight decay 0, batch 32, 3 lags (validation error 8.63% against 8.78% default).

METR-LA check (`modeling/metrla.py`): our STID 2.81 / 3.18 / 3.55 km/h at 15 / 30 / 60 min after 30 CPU epochs;
the Graph WaveNet paper reports 2.69 / 3.07 / 3.53. Full Graph WaveNet needs a GPU (about 23 min per epoch on CPU).

Decisions from forecasts (`alerts.py`, `routing.py`; `results/phase2-alerts-trips-tuned-2026-11-01.md`):
- Alerts (speed below 0.6 or 0.75 of reference): F1 at 60 min 0.77 from the forecast against 0.69 from the current
  speed (threshold 0.6); 0.81 against 0.75 (threshold 0.75).
- Trip time: mean error 1.5 vs 1.9 min (ORR eastbound, 7.9 km) and 2.1 vs 2.4 min (westbound, 12.3 km) against a
  live-map style estimate; historical average 6.4 / 6.5 min.
- Route planner: time-dependent Dijkstra (cost = length / speed when the vehicle enters the stretch). It chose the
  ORR in all 70 weekday departures tested, because the only alternative in the graph is about twice as long and
  uses one assumed link. Real route choice needs the extra parallel roads.

## 6. Changes from the Phase 1 plan (state these, do not hide them)

| Phase 1 plan | What happened |
|---|---|
| METR-LA and PEMS-BAY | METR-LA only (check and pretraining); PEMS-BAY not used |
| Historical Average, XGBoost, LSTM, Graph WaveNet, STID | scikit-learn Gradient Boosting instead of XGBoost; **LSTM not implemented**; GCN, Graph WaveNet, STID done |
| OpenStreetMap features in the road graph | collected, not yet used by the models |
| API (FastAPI) and map dashboard | done in `liveapp/` (FastAPI, Leaflet map) |
| Recommended route beats the current-speed route | not shown (only one real detour) |
| BasicTS / LibCity, NetworkX | own PyTorch code and own Dijkstra |

## 7. The applications

**`liveapp/` (final demo, localhost)**: FastAPI backend + browser front end.
- Engine (`engine.py`) loads the data cache and the 15 saved networks and runs them at request time (about 2-4 ms
  per moment). Alerts, road connections, corridor and road series, routing.
- Live feed (`livefeed.py`): default `github` source pulls the collector's newest monthly files every 3 min (no key,
  no extra TomTom requests); `tomtom` source calls TomTom directly (rate-limited: 5 min, 420 requests a day) and
  saves exact road shapes to `liveapp/data/geometry.json`. Server-sent events push "new readings" to the page.
- Endpoints: `/api/status`, `/api/network`, `/api/days`, `/api/timeline`, `/api/snapshot`, `/api/series`,
  `/api/route`, `/api/results`, `POST /api/live/refresh`, `/api/stream`; offline Swagger docs at `/docs`.
- Front end (`static/`): Leaflet (bundled), canvas roads with both carriageways on the left of travel, moving
  traffic dots, pulsing congestion, road connections (cyan downstream, violet upstream), Live and Time-lapse modes,
  +15/+30/+60 forecasts, "show what actually happened", alerts with outcome checks, route planner with an
  animated car, Models and System tabs, light/dark theme. Works without internet except the map tiles.
- `train.py` trains on everything before the last two full weeks, validates on the first, tests on the last.
  Run on 25 Nov: test week 18-24 Nov, model 2.92 / 3.30 / 3.34 km/h against "same as now" 3.15 / 3.82 / 4.35.
- Without `sync.py --geometry` (needs the TomTom key) roads are drawn through start, middle and end points.

**`app/` (backup)**: offline replay of a precomputed bundle, standard-library server, no packages needed.

## 8. Documents and deliverables

- `docs/PBL_Report_Phase_1.docx`, `docs/phase1-presentation.pptx` (Phase 1).
- Phase 2 deck: 12 slides on the college template (`PBL_Phase2_Presentation_Traffic.pptx`, delivered as a file,
  not in the repository because charts derive from readings). It says "GCN" for the output model and carries the
  graph caveat.
- `docs/PBL_Report_2_Context_Contents_Artifacts.pdf` (+ editable source in `docs/report2-source/`): Contents,
  Project Context (incl. the Phase 1 changes table), Artifacts.
- `docs/LOCAL_SETUP.md`, `liveapp/README.md` (setup and a 6-minute demo script), `app/README.md`.

## 9. Open items

1. Run `python liveapp/sync.py --geometry` with the TomTom key (exact road shapes) before the demo.
2. Final presentation Friday 27 Nov 2026 is Kanakadasa Jayanti (public holiday): live traffic will be light; lead
   with Time-lapse of a recent weekday rush.
3. Fill team names, USNs, guide and coordinator in reports and decks.
4. Data privacy: give `DATA_REPO_TOKEN` Contents read/write on `traffic-data-private` and migrate, or move
   collection to a private setup; send the TomTom permission email.
5. After the presentation: LSTM baseline (promised in Phase 1); parallel roads with seeds picked on a map
   (short busy pieces under 5 km); re-run the full comparison on the 8 weeks of data with new dated result files;
   test a GCN + STID ensemble; full Graph WaveNet on METR-LA on a GPU; use the OpenStreetMap features.

## 10. Working rules for any session

- Never commit readings or anything derived row-by-row from them (see `.gitignore`).
- Changes to `collector/loop.sh`, `collector/segments.csv` or the collect workflow change live collection: ask first.
- Every TomTom call shares the 20,000-a-month quota with the collector.
- Results: identical rows across models, 5 seeds, chronological split, report limits; new runs get new dated files.
- Explain in simple language; label claims as measured, estimated or untested.

## 11. Glossary

Stretch: one TomTom road segment (21). Reference speed: a road's fixed normal speed. Horizon: 15/30/60 min ahead.
Road graph: stretches as nodes, links as edges. GCN: graph convolutional network. Ablation: removing one part to
measure its value. Seed: one training run. MAE: average error in km/h. METR-LA: Los Angeles benchmark (207 sensors).
Persistence: "same as now". Time-lapse: recorded day replayed with the models running at every step.
