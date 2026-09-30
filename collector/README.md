# Bengaluru traffic collector

No sensors, no manual work. GitHub runs `collect.py` around the clock on its own servers: every 15 minutes in the morning and evening rush hours, every 30 minutes at midday, and hourly at night. Each run asks TomTom for the current speed on 10 road segments (TomTom gets these from GPS traces of phones and cars) and asks Open-Meteo for the weather. The rows are saved to a private data repository (until you add the token in "Keep the data private" below, to the public `bengaluru-data` branch). After 4–6 weeks you have a continuous time series of about 1,600–2,400 readings per segment.

## Setup (about 15 minutes, once)

1. **Repository visibility and TomTom's terms.** GitHub Actions minutes are free and unlimited on public repositories, and the collection chain below needs that: each run stays active for about 5.5 hours, so on a private repository on a free account (2,000 minutes a month) the chain would run out of minutes in about two days. But TomTom's Maps API terms (sections 11.4, 11.6.1 and 11.6.4) prohibit storing results and building databases or public data sets from them, and this repository keeps the results on a public branch. Read `research/04-road-network-and-factors.md`, section 4, for the wording and the options (permission from TomTom for academic research, and keeping the collected files out of public view).
2. **Get a free TomTom API key.** Sign up at <https://developer.tomtom.com>. No credit card is needed. Copy the API key from your dashboard.
3. **Add the key to GitHub.** Repository **Settings → Secrets and variables → Actions → Secrets → New repository secret**. Name: `TOMTOM_API_KEY`, value: your key. Never paste the key into a file in the repository.
4. **Test one run.** **Actions** tab → **Collect Bengaluru traffic** → **Run workflow**. After about a minute, a `bengaluru-data` branch appears with `data/tomtom_flow/<month>.csv`.
5. **Check the roads matched correctly.** Open that CSV. Every row should have `status` = `ok`. The `frc` column should be `FRC0`–`FRC3` (major roads). If a row shows `FRC5` or higher, that point snapped to a side street: move its coordinates in `segments.csv` onto the main road. Also check that no two rows have the same `seg_start_*`/`seg_end_*` coordinates. TomTom road segments can be several kilometres long, so two points on one road can match the same segment and waste requests (the first run found this for Old Airport Road and Varthur Road).
6. **Switch collection on.** Same Settings page → **Variables → New repository variable**. Name: `COLLECT_ENABLED`, value: `true`. Then press **Run workflow** once to start the chain.
7. **Leave it running.** Once a week, open the Actions tab and check for red (failed) runs.

## Keep the data private (three steps, once)

TomTom's terms do not allow publishing the results, so the readings belong in a private repository while this repository stays public (public repositories get free unlimited Actions minutes). The workflow reads its instructions from `collector/loop.sh`: if the secret `DATA_REPO_TOKEN` exists, it pushes every reading to the private repository; if not, it falls back to the public `bengaluru-data` branch so that collection never stops.

1. **Create the private repository.** <https://github.com/new>, name `traffic-data-private`, **Private**, tick "Add a README file".
2. **Create a token that can write only to it.** <https://github.com/settings/personal-access-tokens/new>: name `traffic-data-writer`; Repository access: **Only select repositories** → `traffic-data-private`; Repository permissions → **Contents: Read and write**. Generate and copy the `github_pat_...` value. It expires after the period you choose (at most one year): put the date in your calendar.
3. **Save it in this repository.** Settings → Secrets and variables → Actions → **Secrets** → New repository secret. Name `DATA_REPO_TOKEN`, value: the token.

Then run the workflow **Move data to the private repository** once (Actions tab → Run workflow, leave "delete" unticked). It copies the readings already on the public branch into `data/legacy/` of the private repository and checks the row counts. When the collection chain has switched to the private repository (the next run starts at most 5.5 hours after you saved the secret; you can also cancel the running collection and start it again), run the workflow a second time with "delete" ticked to remove the public branch.

If a different repository name is used, set the Actions variable `DATA_REPO` to `owner/name`. Files in the private repository:

- `data/tomtom_flow/YYYY-MM.csv`, `data/weather/YYYY-MM.csv`: the readings (all readings from the switch onwards).
- `data/incidents/YYYY-MM.csv` and `data/incidents/state.json`: TomTom incidents as an event log (see `data/README.md` there).
- `data/legacy/...`: the readings collected before the switch, in the same layout. Load both folders and concatenate them.
- `network/stretches.json`: shape and OpenLR code of every stretch (written by "Build road network").

## How the chain works

GitHub's cron scheduler does not reliably start scheduled runs on new repositories (on this one it never fired). So `loop.sh` keeps its own clock: one workflow run wakes at :07, :22, :37 and :52 past every hour, collects if that slot is on the schedule below, stays alive for about 5.5 hours, and just before it ends starts the next run of the same workflow. The chain never needs a human, and the cron entry in the workflow is only a backup that restarts it if it ever breaks.

- **Stop:** set `COLLECT_ENABLED` to `false`. The next run is skipped, so the chain ends when the current run finishes. Cancel the running run on the Actions tab to stop immediately.
- **Restart:** set it back to `true` and press **Run workflow**.

## Schedule and budget

Two tiers of stretches (the `tier` column of `segments.csv`), read at different times (IST). The times are on the 15-minute slot grid the chain wakes at.

| Tier | Stretches | Read at | Readings a day |
|---|---|---|---|
| core (the Outer Ring Road, both directions) | 17 | every 15 min 08:07-10:07 and 17:37-20:07; every 30 min 07:07-07:37, 10:37, 16:37-17:07, 20:37; 12:07 and 14:07; every 2 hours at night (22:07, 00:07, 02:07, 04:07, 06:07) | 32 |
| context (Hosur Road, the two long Old Airport / Varthur Road stretches) | 4 | 07:07, 08:07, 09:07, 10:07, 12:07, 14:07, 17:07, 18:07, 19:07, 20:07, 22:07, 02:07, 06:07 | 13 |

17 × 32 + 4 × 13 = 596 TomTom requests a day, 18,476 in a 31-day month. The free tier is 20,000 Flow Segment requests a month, leaving about 1,500 for test runs (the network builder uses about 200). The list of times is `CORE_TIMES` and `CONTEXT_TIMES` in `collector/loop.sh`; change them there and re-check the total with:

```
TOMTOM_API_KEY=your_key python collector/collect.py --check
```

(`--check` makes one request per segment, prints Google Maps links for the point you chose and the road TomTom matched, and writes no files.) For modelling, resample to a regular 15-minute grid and interpolate the sparse hours. Every 15 minutes around the clock for 21 stretches would need 65,000 requests a month.

## The segments

`segments.csv` has one row per TomTom stretch: `segment_id`, `name`, `road`, the request point (`lat`, `lon`, a point on the stretch that TomTom maps back to the same stretch), `route`, `tier`, `seq` (position along the route), `length_km`, `frc`. It is written by the network builder (next section), which also lists which stretch leads into which (`collector/network/links.csv`) and the OpenStreetMap features of each stretch (`collector/network/features.csv`).

The first ten segments used points chosen by hand. Nine of them are stretches of the new network under the same id. `sarjapur_agara` was labelled Sarjapur Road, but TomTom matched the Outer Ring Road eastbound near Agara, so it is now `orr_ccw_03` (`collector/network/legacy_ids.csv`).

To use a different corridor, add a route to `ROUTES` in `build_network.py` (a seed point on the road and a target to stop at) and run the workflow **Build road network**.

## Building the road network

The stretches TomTom returns are pieces of road of very different lengths, and the readings alone do not say which stretch leads into which. `build_network.py` (workflow **Build road network**, run by hand) fixes that:

1. **Walks the road.** It asks TomTom for the stretch under a seed point, takes the far end of that stretch, steps a few metres past it along the road and asks again. Repeated in both directions, this chains stretches with no gaps along the Outer Ring Road and its feeder roads.
2. **Links the stretches.** `flow` links (a vehicle can drive from the end of A into the start of B) and `crossing` records (two roads cross here).
3. **Adds OpenStreetMap features** to every stretch: road class, lanes, speed limit, one-way, bridge and tunnel share, traffic signals (count, per km, distance to the next one from each end), intersections, and counts of bus stops, metro stations, schools, hospitals, malls and offices within 300 m.

The road layout (`segments.csv`, `links.csv`) and the OpenStreetMap features (`features.csv`, © OpenStreetMap contributors, ODbL) are printed in the run's log. The shape and OpenLR code of each stretch are TomTom results; they are saved only in the private repository (`network/stretches.json`) when `DATA_REPO_TOKEN` is set. Options: **walk_only** skips the slower OpenStreetMap step, **verbose** prints every probe. It uses about 200 TomTom requests.

Test without network: `python3 collector/build_network.py --selftest`.

## Incidents

When the data goes to the private repository, the collector also polls TomTom's traffic incidents in the area of the segments every half hour (IST :07 and :37; about 1,200 requests a month against the free 2,500). `incidents/YYYY-MM.csv` is an event log: a `poll` row per poll (`n_active` = incidents active then), a `new` or `changed` row with the details, and an `ended` row when an incident is no longer reported. A daytime poll returns about 230 active incidents, mostly long-running road works and closures, so a full snapshot every time would be mostly repeats.

## Run it somewhere else

Any always-on computer with Python 3.8+ and git works: from a clone of the repository run

```
TOMTOM_API_KEY=... LOOP_MINUTES=100000 NO_CHAIN=true bash collector/loop.sh
```

It keeps collecting on the same schedule until stopped.

Test without a key or network: `python collector/collect.py --dry-run --out /tmp/test`.
