# Simulation and Replay: What Each Can Prove

Idea from the team: take pre-recorded / already available data, recreate it on the road network in a simulation, and run the predictions there so there is an output to show.

There are two different things this can mean. They prove different claims.

---

## A. Replay (recommended for the demo)

Feed **real recorded data** into the system in time order, as if it were arriving live. Every 5 minutes (or sped up to every second on screen) the model sees the latest readings, makes its +15 / +30 / +60 min forecast, and the dashboard shows the forecast next to what actually happened.

- Data: the METR-LA test period (the last 20%, never seen in training), and later the collected Bengaluru data.
- What it proves: **forecast accuracy on real traffic**, shown live instead of only as a table of numbers.
- Cost: low. It is a loop over a data file plus the dashboard.
- Rule: only replay a period the model was not trained on. Otherwise the demo is showing memorised answers.

## B. Traffic simulation (SUMO)

Build the road network in a traffic simulator, generate vehicles, and let them drive.

- Tools: SUMO (open source). `osmWebWizard.py` imports a Bengaluru area from OpenStreetMap; `routeSampler.py` fits vehicle routes to observed counts; induction-loop detectors act as virtual sensors at chosen points; TraCI lets Python reroute vehicles while the simulation runs. The sublane model and motorcycle vehicle class help with two-wheeler-heavy traffic.
- What it proves: **whether route recommendations reduce travel time.** You cannot test rerouting on real roads, and a simulator lets you compare:
  1. no guidance
  2. guidance from current speeds
  3. guidance from predicted speeds

  with the same vehicle demand, measuring average trip time and total delay.
- What it does **not** prove: forecast accuracy for Bengaluru. The simulated vehicles follow demand the team typed in. A model trained on that output learns the team's assumptions, so its accuracy says nothing about real roads. Evaluators who know the field will ask about this.
- Cost: high. Cleaning up the OSM junctions and signals for an Indian corridor and calibrating demand to real counts or speeds is weeks of work for even a small area.
- Calibration still needs real data: counts or speeds from the TomTom collection, or from videos.

---

## Recommended split

| Claim in the report | Evidence | Data |
|---|---|---|
| The forecasting model is accurate | Error at 15 / 30 / 60 min vs. baselines | METR-LA (real), then Bengaluru collected data (real) |
| It works live | Replay demo on the dashboard | Held-out real data |
| Forecast-based routing saves time | Simulation experiment: 3 routing strategies, same demand | SUMO corridor calibrated to real Bengaluru speeds |
| What-if scenarios (closure, rain, event) | Simulation runs | SUMO |

Order of work: replay first (cheap, needed anyway for the dashboard), simulation second, and only for the routing and what-if claims.
