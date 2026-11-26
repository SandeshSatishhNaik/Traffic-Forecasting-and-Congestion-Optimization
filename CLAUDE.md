# CLAUDE.md: Traffic Forecasting and Congestion Optimization

Student PBL project (GM University): "AI-Driven Spatio-Temporal Traffic Intelligence System for Traffic
Forecasting and Congestion Optimization" on the Bengaluru Outer Ring Road (ORR). The team presents and defends
it, so explain choices in simple language and say what is measured, estimated or untested.

## Hard rules

- **Data licence.** TomTom's terms forbid publishing or storing their readings publicly, and this repository is
  public. Never commit readings or anything that embeds them: `local-data/`, `liveapp/data/`, `liveapp/models/`,
  `app/data/`, `*.pkl`, `*.pt`, dashboard `.html` files. `.gitignore` covers them; run `git status` before every
  commit. Commit code and aggregate result tables only.
- **The collection chain runs from this branch.** `claude/brave-galileo-igwv6s` is the default branch, and the
  GitHub Actions collector (`.github/workflows/collect-bengaluru.yml`, `collector/loop.sh`,
  `collector/segments.csv`) checks it out on every restart. A change there changes live data collection.
  Do not change the schedule or segments without the team agreeing.
- **TomTom free tier:** 20,000 flow requests a month; the collector uses 596 a day (18,476 a month). Anything else
  that calls TomTom (liveapp `--source tomtom`, `sync.py --geometry`, `build_network.py`) uses the same quota.
- Never claim a model "beats" another unless the gap is larger than the seed spread. Report limits (one test
  week, one corridor) next to results.
- No pull requests unless asked.

## Layout

| Folder | What |
|---|---|
| `collector/` | TomTom + Open-Meteo collector (`collect.py`, `loop.sh`, `run_local.py`), road network builder, quota check |
| `modeling/` | data preparation (`prepare.py`), baselines, GCN (`stgnn.py`), evaluation, tuning, alerts, routing, Graph WaveNet/STID re-implementations, METR-LA, pretraining; `results/` holds aggregate results |
| `liveapp/` | **the final demo**: FastAPI backend + animated browser front end; runs the trained GCNs on live data (see `liveapp/README.md`) |
| `app/` | earlier offline replay app (backup; needs only Python) |
| `docs/` | Phase 1 report and deck, Report 2 sections (PDF), `LOCAL_SETUP.md` |
| `research/` | notes, including the draft TomTom permission email |

## Commands

```
python -m pip install fastapi uvicorn pandas numpy scikit-learn torch
python liveapp/sync.py              # data from the bengaluru-data branch into liveapp/data/cache
python liveapp/sync.py --geometry   # exact road shapes (needs TOMTOM_API_KEY, 21 requests)
python liveapp/train.py             # 15 networks (3 horizons x 5 seeds), about 2 min on 4 cores
python liveapp/main.py              # http://127.0.0.1:8000  (API docs /docs); --source off without internet
python collector/build_network.py --selftest
python modeling/evaluate.py --data-dir <folder with tomtom_flow/> --hp-json modeling/results/tuning-2026-11-01.json
```

## Modelling conventions

- 15-minute slot grid (:07, :22, :37, :52 IST); missing readings are masked, never filled for scoring.
- Speeds are divided by a fixed reference speed per road (95th percentile of night speed in training).
- Chronological split by day; all models scored on identical rows; neural models: 5 seeds, mean +- std.
- Holidays live in `prepare.HOLIDAYS` (October and November 2026, incl. the 9 Nov Deepavali bridge day, checked
  against the data). Add new ones from an official list and check them against rush-hour speeds.
- Published Phase 2 numbers (`modeling/results/*2026-11-01*`) use the 33-day data and test week 25-31 Oct 2026.
  New runs on more data are new results: give them new dated file names.

## State (26 Nov 2026)

- Collection running since 27 Sep 2026; 21 stretches; about 8 weeks of data.
- Output model: GCN with the road graph (tuned). STID (no graph) ties it; pretrained STID scored about 2% better
  (one run). Graph WaveNet overfits this data.
- Final presentation Friday 27 Nov (a Karnataka holiday, so live traffic will be light: lead with Time-lapse).
- Open: exact road shapes need the key on the team laptop; extra parallel roads (`collector/ALT_ROADS.md`) failed
  verification; `DATA_REPO_TOKEN` lacks write access to the private data repository; TomTom permission email not
  sent; team names and USNs still placeholders in reports and decks.
