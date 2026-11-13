# Local setup: run the whole project on your own computer

This guide takes a fresh computer from nothing to everything running: collecting traffic data, training and
comparing the models, the METR-LA check, pretraining, and the dashboard. Follow it top to bottom.
Every command here was taken from the code in this repository.

**Two rules before you start**
1. TomTom's terms forbid publishing or storing their readings in a public place. Keep `local-data/`,
   `*.pkl` files and any dashboard `.html` on your machine only. `.gitignore` already blocks them; do not
   force-add them. Commit code and aggregate result tables only.
2. Use one collector at a time. The GitHub collector and the local collector share TomTom's free limit
   (20,000 flow requests a month; our schedule uses 18,476).

---

## 1. What you need

| Item | Needed for | Notes |
|---|---|---|
| Python 3.11 | everything | 3.8+ is enough for the collector only |
| Git | getting the code and the old data | |
| TomTom API key | collecting data | free tier, no card; your existing key works |
| 16 GB RAM | pretraining and METR-LA | the code ran in 15 GB |
| 4+ CPU cores | models | the results here were made on 4 cores, no GPU |
| NVIDIA GPU (optional) | full Graph WaveNet on METR-LA | about 23 min per epoch on CPU, so use a GPU |
| 5 GB free disk | METR-LA, data, environment | |
| A computer that stays on and online | collecting | see section 4 |

## 2. Get the code and a Python environment

```
git clone https://github.com/SandeshSatishhNaik/Traffic-Forecasting-and-Congestion-Optimization.git
cd Traffic-Forecasting-and-Congestion-Optimization
git checkout claude/brave-galileo-igwv6s        # this is the repository's default branch

python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# Mac / Linux:         source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install pandas numpy scikit-learn h5py
python -m pip install torch                       # CPU version, fine for everything except Graph WaveNet on METR-LA
```
For a GPU computer, install the CUDA build of torch from https://pytorch.org/get-started/locally/
instead of the last line, then check: `python -c "import torch; print(torch.cuda.is_available())"` should print `True`.

On Windows use `python`; on some Mac/Linux machines the command is `python3`.

## 3. Bring over the data collected so far

The readings live on the `bengaluru-data` branch (GitHub collector). Do this in order so no readings are lost:

1. **Stop the GitHub collector.** In the repository on GitHub: Settings, Secrets and variables, Actions,
   Variables, set `COLLECT_ENABLED` to `false`. Then Actions tab, open the running "Collect Bengaluru traffic"
   run and press **Cancel workflow**. (Readings between now and the first local reading are lost, so do
   section 4 straight after.)
2. **Copy the old data** into a folder called `local-data`:
   ```
   git fetch origin bengaluru-data
   git worktree add ../data-snapshot origin/bengaluru-data
   # Windows PowerShell:  Copy-Item -Recurse ..\data-snapshot\data\* local-data\
   # Mac / Linux:         mkdir -p local-data && cp -r ../data-snapshot/data/* local-data/
   ```
3. **Check it:** `local-data` must contain `tomtom_flow/`, `weather/` and `incidents/`, each with files named
   like `2026-10.csv`, `2026-11.csv`. Every reading is a row; check the size grows month to month:
   `wc -l local-data/tomtom_flow/*.csv` (Mac/Linux) or open a file in Excel.

## 4. Start the local collector

```
# Windows PowerShell:  $env:TOMTOM_API_KEY="your_key"
# Mac / Linux:         export TOMTOM_API_KEY=your_key

python collector/run_local.py --out local-data --dry-run --once    # test with fake readings, no key, no network
python collector/run_local.py --out local-data --once              # one real round; check new rows appear
python collector/run_local.py --out local-data                     # run for real; stop with Ctrl+C
```
- It uses the same schedule as the GitHub collector (IST times; Outer Ring Road every 15 min in the two rush
  windows, fewer readings otherwise), about 596 requests a day.
- **Keep the computer awake and online.** Turn off sleep (Windows: Settings, System, Power; Mac: Energy
  settings; Linux: `systemctl mask sleep.target`). A reading missed while the computer is off cannot be
  recovered. Restarting is safe: it continues at the next slot.
- Run it in a terminal you leave open, or under `tmux`/`screen` (Linux/Mac), or as a Windows Task Scheduler
  task that starts at logon.
- Do not move the `local-data` folder while it runs. Back it up weekly (copy the folder).
- Never run this while `COLLECT_ENABLED` is `true`.

## 5. Check the data before you train

Models read `local-data` directly, so run this health check from the repository folder:
```
python - <<'PY'
import sys; sys.path.insert(0, "modeling")
import prepare
df, ids = prepare.load_flow("local-data")
print(len(df), "valid readings,", df["segment_id"].nunique(), "of", len(ids), "stretches")
print("first reading:", df["t"].min(), "  last reading:", df["t"].max())
print(df.groupby(df["t"].dt.date).size().tail(7))
PY
```
(Windows PowerShell has no `<<` heredoc: save the lines between `PY` and `PY` as `health.py` and run `python health.py`.)
What good looks like: `21 of 21 stretches`, the last reading is today, and each full day shows **596** readings
(on the snapshot up to 1 Nov the check printed 19,093 readings and 596 per full day). A day with far fewer means
the collector was off or a slot failed.

## 6. Run the models on your data

Run these from the repository folder, in this order. Results are aggregate tables (safe to commit); the
`.pkl` and `.html` files contain readings (do not commit).

```
mkdir results-local

# 1. Baselines: repeat last speed, historical average, gradient boosting
python modeling/baselines.py --data-dir local-data --out results-local/baselines.md

# 2. Tune the graph net (random search, uses only data before the test week). The longest step.
python modeling/tune.py --data-dir local-data --out tuning.json --trials 30

# 3. Train and score all models on the same rows, 5 seeds each (writes the per-row predictions)
python modeling/evaluate.py --data-dir local-data --hp-json tuning.json --save-rows rows.pkl --out results-local/models.md

# 4. Alerts, trip times, routing
python modeling/alerts.py --data-dir local-data --rows rows.pkl --out results-local/alerts.md
python modeling/routing.py --data-dir local-data --hp-json tuning.json --save demo.pkl --out results-local/trips.md

# 5. Graph WaveNet and STID (our re-implementations), same rows, 5 seeds
python modeling/evaluate_ref.py --data-dir local-data --rows rows.pkl --out results-local/reference.md --save-rows rows_ref.pkl --seeds 5

# 6. The replay dashboard (open dashboard.html in a browser; works offline)
python modeling/demo_dashboard.py --demo demo.pkl --out dashboard.html --tuning tuning.json
```
Time on a 4-core CPU: `evaluate_ref.py` took about 10 minutes. The others were not timed precisely;
`tune.py` is the longest (plan for an hour or more [estimate]).

### Read this before you compare with the old numbers
- **The test week moves.** The code takes the last 7 complete days as the test week and the 7 days before as
  validation. With newer data the test week is no longer 25-31 Oct, so the numbers will differ from the Phase 2
  tables. Do not mix old and new numbers in one table; report them as a new run.
- **Update the holiday list.** `modeling/prepare.py` has `HOLIDAYS = {"2026-10-02", "2026-10-19", "2026-10-20", "2026-10-21"}`.
  Days in this set are treated as weekend-like. It does not yet include November. Add the real Karnataka
  public holidays from the official list (Kannada Rajyotsava and Deepavali fall in early November 2026; I have
  not verified the exact dates), then run the models.
- Re-run `tune.py` on the new data; settings tuned on 33 days may not suit 45+ days.

## 7. METR-LA check and pretraining

METR-LA is the standard public benchmark (207 Los Angeles freeway sensors). Download three files into a folder `metrla`:
```
mkdir metrla
curl -L -o metrla/metr-la.h5 https://raw.githubusercontent.com/transpaper/GCNN/master/data/METR-LA_traffic_speed/metr-la.h5
curl -L -o metrla/graph_sensor_ids.txt https://raw.githubusercontent.com/liyaguang/DCRNN/master/data/sensor_graph/graph_sensor_ids.txt
curl -L -o metrla/distances_la_2012.csv https://raw.githubusercontent.com/liyaguang/DCRNN/master/data/sensor_graph/distances_la_2012.csv
```
(`metr-la.h5` is about 57 MB. The same file is on Kaggle: annnnguyen/metr-la-dataset.)

```
# STID: about 45 s per epoch on a 4-core CPU. Our run: 30 epochs, test MAE 2.81 / 3.18 / 3.55 km/h at 15 / 30 / 60 min.
python modeling/metrla.py --data-dir metrla --model stid --epochs 30 --out stid_metrla.json

# Graph WaveNet: use a GPU (about 23 min per epoch on CPU). Published results to compare with
# (Graph WaveNet paper): 2.69 / 3.07 / 3.53 km/h at 15 / 30 / 60 min.
python modeling/metrla.py --data-dir metrla --model gwn --epochs 100 --out gwn_metrla.json
```
The script uses the GPU when torch can see one; add `--cpu` to force CPU.

Pretrain STID on METR-LA, then fine-tune on Bengaluru (needs `rows.pkl` from step 3 above):
```
python modeling/pretrain.py --metrla-dir metrla --data-dir local-data --rows rows.pkl --epochs 15 --state stid_metrla.pt --out results-local/pretrain.md
```
It prints three variants: STID from scratch, pretrained with all weights fine-tuned, pretrained with the trunk
frozen. The earlier run gave about 2% lower error with all weights fine-tuned (one pretraining run, one test
week). The script does not include the learning-rate control; see `modeling/results/phase2-pretraining-2026-11-01.md`.

## 8. More roads for real route choice (not finished)

The first build did not pass verification (wrong seed points, 14-23 km stretches). What to do:
1. In Google Maps, find a **short, busy piece** (under about 5 km) of each road you want (for example Sarjapur
   Road, Whitefield Road), right-click the road, copy the coordinates.
2. Put them as seeds in `ROUTES_ALT` in `collector/build_network.py`, with the road name in `expect`.
3. Run `python collector/build_network.py --alt` (needs `TOMTOM_API_KEY`; about 60 requests; prints
   `VERIFY OK` or `VERIFY CHECK` for each stretch). Keep only `OK` stretches under about 5 km.
4. `python collector/quota_plan.py 12` checks the monthly requests: at most 12 extra stretches fit, and only with
   the trimmed schedule in `collector/ALT_ROADS.md`.
5. Switch on by following `collector/ALT_ROADS.md`; update `CORE_TIMES`/`CONTEXT_TIMES` in **both**
   `collector/loop.sh` and `collector/run_local.py` (they must match).
6. Route choice between these roads can only be evaluated after a few weeks of data.

## 9. If something goes wrong

| Problem | Fix |
|---|---|
| `Set the TOMTOM_API_KEY environment variable first` | set the variable in the same terminal that runs the collector |
| HTTP 403 or 429 from TomTom | the monthly limit is used up, or two collectors share the key; stop one |
| Collector stops after the laptop sleeps | turn off sleep; the missed readings are gone, restart it |
| `No module named torch` / `h5py` / `sklearn` | activate `.venv`, then `python -m pip install torch h5py scikit-learn` |
| `torch.cuda.is_available()` is `False` on a GPU computer | install the CUDA build of torch (section 2) |
| `FileNotFoundError ... tomtom_flow` | `--data-dir` must be the folder that contains `tomtom_flow/` (here `local-data`) |
| Out of memory in `pretrain.py` | close other programs; it needs about 8 GB or more |
| Tuning takes too long | `--trials 12` gives a shorter search |

## 10. Ready checklist

- [ ] Python 3.11, `.venv`, packages installed
- [ ] GitHub collector stopped (`COLLECT_ENABLED` false) and old data copied to `local-data`
- [ ] `run_local.py --once` wrote new rows; collector running with the computer set not to sleep
- [ ] `local-data` loads (section 5)
- [ ] `HOLIDAYS` updated for November
- [ ] Section 6 commands run; results in `results-local/`
- [ ] METR-LA downloaded; STID run; Graph WaveNet queued for a GPU
- [ ] `local-data/`, `*.pkl`, `dashboard*.html` not committed (`git status` shows none of them)
