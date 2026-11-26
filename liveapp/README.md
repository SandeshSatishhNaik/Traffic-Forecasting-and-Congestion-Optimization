# Live app: Bengaluru ORR Traffic Intelligence (localhost)

The complete working system on one laptop: a **FastAPI backend** that runs the **trained Graph Convolutional
Networks** on **live readings**, and a **browser front end** with a map of the 21 connected road stretches,
moving traffic, forecasts, alerts, road connections and a route planner.

| What you see | What is behind it |
|---|---|
| **Live** mode: the newest readings and the forecast of the next hour | the project's collector reads TomTom every 15 min (rush hours); the app pulls the newest data every 3 min and pushes it to the page (server-sent events) |
| **Time-lapse** mode: a recorded day played at 1 to 8 slots a second | the same models run on the readings up to each moment, so every forecast can be checked against what happened |
| Roads coloured by speed, moving dots (faster when the road is faster), pulsing glow on congested roads | canvas animation over a Leaflet map, both carriageways drawn on the left of their direction |
| Click a road: its forecast, chart, and **connections** (cyan: where its traffic goes; violet: where it comes from) | road graph from `collector/network/links.csv` (flow links and junction crossings) |
| Route tab: fastest route with an animated car | time-dependent Dijkstra on the forecast, compared with what a live map would pick |
| Models tab, System tab, `/docs` | the model's own test-week score, all 11 model versions, the live pipeline status, every API call with its time, interactive API docs |

Every forecast on the page is computed on request by 15 saved networks (3 horizons x 5 training runs), in a few milliseconds.

## Set up once (about 10 minutes)

Python 3.10 or newer. In the project folder:

```
python -m pip install fastapi uvicorn pandas numpy scikit-learn torch
python liveapp/sync.py              # downloads the collected data into liveapp/data/cache (about 6 MB)
python liveapp/sync.py --geometry   # optional, needs TOMTOM_API_KEY: exact road shapes (21 requests, once)
python liveapp/train.py             # trains and saves the 15 networks (about 2 minutes)
```
On Windows you can double-click `liveapp\setup_liveapp.bat` instead. Set the key first in that window if you
want the exact road shapes: `$env:TOMTOM_API_KEY="your_key"` (PowerShell) or `set TOMTOM_API_KEY=your_key` (cmd).

Without `--geometry` each stretch is drawn through its start, middle and end point (approximate shape; the
long feeder roads then look straight). With it, the map shows the real road shapes. **Do it before the demo.**

## Start

```
python liveapp/main.py                  # live data from the collector (needs internet)
python liveapp/main.py --source off     # no internet: everything from the local cache
python liveapp/main.py --source tomtom  # live data straight from TomTom (needs TOMTOM_API_KEY; 21 requests per refresh)
```
Windows: double-click `liveapp\run_liveapp.bat`. The browser opens `http://127.0.0.1:8000/`. API docs: `/docs`.

Without internet the app still works: the map tiles are replaced by a plain grid, the roads, models, animation
and API all run locally. The default `github` source costs no TomTom requests; `--source tomtom` does, so it is
limited to one refresh every 5 minutes and 420 requests a day.

To retrain on the newest data (for example the evening before the demo): `python liveapp/sync.py` then `python liveapp/train.py`.

## Demo script (about 6 minutes)

1. **Live** (opens there). "This is the Outer Ring Road right now. The latest reading was at HH:MM. Colours are
   speed against each road's normal speed; the dots are traffic, slower where the road is slower."
2. Click **+30 min**. "This is the forecast for 30 minutes from now, computed just now by 15 trained graph networks
   in a few milliseconds" (point to the line under the alerts).
3. **Time-lapse**, a recent weekday, press **▶**. "The same models replay yesterday's evening rush. Watch the
   congestion build at Marathahalli and Bellandur." Pause around 18:00.
4. Tick **Show what actually happened** at +30 min: compare. Point to an alert marked **✓ happened** and to an
   **EARLY WARNING** (road fine now, forecast to congest).
5. Click **Marathahalli**: the forecast with the range of the 5 runs, the chart, and the **road connections**
   lighting up on the map.
6. **Route**: click the first preset. "Time-dependent Dijkstra on the forecast; the car follows the route." Read
   the verdict honestly (sometimes the live-map estimate is closer).
7. **Models**: "This model, tested on a week it never saw, beats 'same as now' at every horizon." Then the 11 versions.
8. **System**: the pipeline with live status, the API calls with their times, and `/docs` (the backend).

Say once, clearly: the data are real TomTom readings collected by our own pipeline; live means the newest
reading, which is at most 15 minutes old in rush hours and up to 2 hours old at night.

## Main screen (React)

`http://127.0.0.1:8000/` is a React app styled after the ORR's roadside message signs. The built files are in
`static/app/` (committed, so running the app needs only Python). The earlier page stays at `/classic`.

- **Pipeline strip** (top): TomTom reading -> data cache -> graph neural network (15 networks, run time in ms) ->
  forecast (alerts). A light runs along it whenever new readings arrive (live) or the moment changes (replay).
- **Horizon tiles** on the map: Now / +15 / +30 / +60 min; the map recolours to the chosen horizon.
- **Next hour**: sign-style messages ("Congested now", "Jam in 30 min") that re-rank in place, plus the corridor chart.
- **Road**: click a road for its numbers, chart and the unseen-road test. **Proof**: test-week errors and limits.
- **Replay a day**: day picker, play at 1x/2x/4x, a strip of the whole day coloured by speed.

To change it: `cd liveapp/web`, `npm install` once, `npm run dev` (hot reload, uses the running backend on port
8000), then `npm run build` to update `static/app/`.

## 3D space-time view and unseen roads

`/static/3d.html` (button **3D view** on the main page): the floor is the road map coloured by the speed now; walls
rise above each road to the +15, +30 and +60 minute forecasts (height = minutes ahead). Live and replay; hover or
click a road for details. three.js is bundled in `static/vendor/three/`, so it works offline.

**Unseen-road test** (panel in the 3D view, API `/api/unseen?road=...&t=...`): what if we had never seen a road?

```
python liveapp/train_unseen.py --jobs 3     # once: 21 roads x 3 horizons x 2 seeds, each road hidden from training (about 40 min on 16 cores)
```
For every road this trains networks that never saw it (no reading of it in training or validation; it gets the mean
road embedding) and saves them in `liveapp/models/unseen/` (derived from readings: not in git). Training also blanks
one random known road per extra sample, so the network learns to fill a road in from its neighbours. Two cases:
- **No sensor** (virtual sensor): the road's inputs are blank; the estimate of now and of +15/+30/+60 min comes only
  from the connected roads through the road graph.
- **New sensor**: the road just started sending readings; its own live readings are inputs, but it has no training history.

The panel shows the forecast next to the normal model and what happened, plus the error measured on the test
week. Results: `modeling/results/unseen-roads-<date>.md`.

## Honest limits

- Readings come every 15 minutes in rush hours and every 30 minutes to 2 hours otherwise, so "live" is as fresh as the last reading.
- The route planner has one real detour in the graph (and one assumed link), so the forecast and the live map usually pick the same roads; the difference is the time estimate.
- The models are trained once (`train.py`) and then used; they are not retrained while the app runs.

## Files

| File | Purpose |
|---|---|
| `main.py` | FastAPI backend: API, live push (`/api/stream`), offline API docs (`/docs`) |
| `engine.py` | data, saved networks, forecasts, alerts, connections, routing |
| `livefeed.py` | background live updates (GitHub collector data or TomTom direct) |
| `sync.py`, `train.py` | download the data; train and save the networks |
| `static/` | the page (`index.html`, `style.css`, `app.js`) and bundled Leaflet and Swagger UI (works offline) |
| `data/`, `models/` | the data cache, road shapes and trained networks: derived from TomTom readings, kept out of git |

`app/` (one folder up) is the earlier offline replay version, kept as a backup that needs only Python.
