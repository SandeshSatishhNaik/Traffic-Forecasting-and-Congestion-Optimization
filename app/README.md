# Offline traffic app (final demo)

A complete, working version of the system that runs on one laptop **without internet**:
a local Python server with a JSON API, and a browser interface with four pages.

| Page | What it shows |
|---|---|
| Replay | Map of the 21 road stretches coloured by speed, now and forecast for +15, +30, +60 min; congestion alerts with a check of whether they really happened; a table of every stretch |
| Route planner | Fastest route by time-dependent Dijkstra on the forecast, compared with the route a live map would pick and with the recorded trip time |
| Models | Error of all 11 model versions, alert and trip-time results, notes and limits |
| How it works | The pipeline from readings to decisions, what runs where, honest limits |

**It runs on recorded data, not a live feed.** Forecasts were made by the tuned graph model (GCN with the
road graph, 5 training runs averaged) for every 15-minute slot of the window, using only data from before
each moment. Two kinds of bundle:

- **Replay** (default): the last 7 full days. Every forecast can be checked against what happened.
- **Latest** (`--latest`): the window ends at the newest reading, and the app opens there. At that moment
  the +15, +30 and +60 minute forecasts are real forecasts of the future, with nothing to compare yet.
  Build it shortly before the presentation and say "forecast from data up to HH:MM".

Say which one you show at the start.

## Start it (demo day)

1. Get the latest code: `git pull` in the project folder.
2. Put the data bundle at `app/data/bundle.json` (it is private, so it is not in the repository; see below).
3. Start:
   - Windows: double-click `app\run_demo.bat`
   - Mac / Linux: `./app/run_demo.sh`
   - or anywhere: `python app/server.py`
4. The browser opens `http://127.0.0.1:8000/`. Stop with Ctrl+C.

Running needs **only Python 3.8+**, with no packages and no internet. Test it once with Wi-Fi switched off.

Options: `--port 8080` if 8000 is busy, `--no-browser`, `--bundle path/to/bundle.json`.

## Build the data bundle (before demo day)

The bundle holds the replay week: recorded speeds, forecasts and road layout (about 0.5 MB).
It contains TomTom-derived speeds, so **never commit it** (`app/data/` is in `.gitignore`).

```
# from saved forecasts (fast; the pickle from modeling/routing.py --save)
python app/build_bundle.py --demo demo.pkl --out app/data/bundle.json

# from raw data (trains the tuned model first; needs the modeling packages and torch)
python app/build_bundle.py --data-dir local-data --out app/data/bundle.json

# from raw data, window ending at the newest reading (forecasts of the next hour)
python app/build_bundle.py --data-dir local-data --latest --out app/data/bundle.json
```
Training takes about 5 to 10 minutes on a 4-core laptop CPU.

## Demo day (works with no internet at the college)

1. The evening before, at home with internet: get the newest data (see docs/LOCAL_SETUP.md, section 3),
   build a **replay** bundle and a **latest** bundle, and keep both:
   `--out app/data/bundle.json` and `--out app/data/bundle_latest.json`.
2. On the morning, if there is internet, refresh the data and rebuild the latest bundle once more.
3. Start the app with the one you want: `python app/server.py` (replay) or
   `python app/server.py --bundle app/data/bundle_latest.json` (latest).
4. Rehearse once with Wi-Fi switched off.
The raw-data build uses the last full week as the replay week and trains on everything before it, exactly
like `modeling/routing.py`. It prints the forecast error on the replay week next to "same as now".

## Demo script (about 5 minutes)

1. **Replay, Mon 26 Oct 18:07** (the replay bundle opens there). "Evening rush. The ORR is at about 65% of normal
   speed; westbound Marathahalli to Bellandur is congested (red)."
2. Click **+60 min**. "This is the forecast made at 18:07 for 19:07." Tick **Show what actually happened**
   and compare. Untick.
3. **Congestion alerts**: point to **happened ✓** (the alert came true) and **EARLY WARNING** (the road is
   fine now but is forecast to congest).
4. Press **▶** to play the evening forward, then pause.
5. **Route planner**: click the first preset, then **Plan fastest route**. Read the three numbers: forecast
   time, live-map time, recorded time. "Here both pick the ORR, because our graph has only one real
   detour; the difference is the time estimate." Point to the API line under the result.
6. **Models**: "We compared 11 model versions on the same rows. The app uses GCN with the road graph
   (highlighted). STID, which has no graph, ties it, and pretraining STID on Los Angeles data helped by about 2%."
7. **How it works**: the seven steps, and the honest limits.

## API

All `GET`, JSON. `i` is the slot number (0 to 671 for a 7-day week).

| Endpoint | Returns |
|---|---|
| `/api/meta` | road stretches, links, replay times, model and window accuracy |
| `/api/state?i=168` | speed now, forecasts and recorded values for +15/+30/+60 min, alert list, corridor summary |
| `/api/route?src=orr_ccw_02&dst=orr_doddanekundi&i=168` | forecast route and live-map route with times and recorded trip times |
| `/api/results` | the aggregate results shown on the Models page (`app/results.json`) |

## Files

| File | Purpose |
|---|---|
| `server.py` | local server and API (standard library only) |
| `build_bundle.py` | builds `data/bundle.json` from saved forecasts or raw data |
| `results.json` | aggregate results from `modeling/results/` (safe to commit) |
| `static/` | the page: `index.html`, `style.css`, `app.js` (no external files) |
| `run_demo.bat`, `run_demo.sh` | one-click start |

## Limits (say them before you are asked)

- Replay of recorded data, not live. Live use needs the collector online and a rebuilt bundle.
- One corridor, one test week.
- The road graph has one real detour (Hosur Road to Varthur Road, with one assumed link), so route choice is limited.
- Raw readings are TomTom data and are not published.
