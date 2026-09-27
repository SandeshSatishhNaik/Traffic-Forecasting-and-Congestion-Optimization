# Bengaluru traffic collector

No sensors, no manual work. GitHub runs `collect.py` every 15 minutes during the day (06:37–21:22 IST) on its own servers. Each run asks TomTom for the current speed on 10 road segments (TomTom gets these from GPS traces of phones and cars) and asks Open-Meteo for the weather. The rows are saved to the `bengaluru-data` branch. After 4–6 weeks you have a time series of about 1,700–2,500 readings per segment.

## Setup (about 15 minutes, once)

1. **Repository visibility.** GitHub Actions minutes are free and unlimited on public repositories, and the collection chain below needs that: each run stays active for about 5.5 hours. On a private repository on a free account (2,000 minutes a month) the chain would run out of minutes in about two days. The trade-off is that on a public repository the collected TomTom data is public too; check TomTom's terms before publishing results.
2. **Get a free TomTom API key.** Sign up at <https://developer.tomtom.com>. No credit card is needed. Copy the API key from your dashboard.
3. **Add the key to GitHub.** Repository **Settings → Secrets and variables → Actions → Secrets → New repository secret**. Name: `TOMTOM_API_KEY`, value: your key. Never paste the key into a file in the repository.
4. **Test one run.** **Actions** tab → **Collect Bengaluru traffic** → **Run workflow**. After about a minute, a `bengaluru-data` branch appears with `data/tomtom_flow/<month>.csv`.
5. **Check the roads matched correctly.** Open that CSV. Every row should have `status` = `ok`. The `frc` column should be `FRC0`–`FRC3` (major roads). If a row shows `FRC5` or higher, that point snapped to a side street: move its coordinates in `segments.csv` onto the main road. Also check that no two rows have the same `seg_start_*`/`seg_end_*` coordinates. TomTom road segments can be several kilometres long, so two points on one road can match the same segment and waste requests (the first run found this for Old Airport Road and Varthur Road).
6. **Switch collection on.** Same Settings page → **Variables → New repository variable**. Name: `COLLECT_ENABLED`, value: `true`. Then press **Run workflow** once to start the chain.
7. **Leave it running.** Once a week, open the Actions tab and check for red (failed) runs.

## How the chain works

GitHub's cron scheduler does not reliably start scheduled runs on new repositories (on this one it never fired). So `loop.sh` keeps its own clock: one workflow run collects at :07, :22, :37 and :52 past every hour (UTC; 06:37–21:22 IST), stays alive for about 5.5 hours, and just before it ends starts the next run of the same workflow. The chain never needs a human, and the cron entry in the workflow is only a backup that restarts it if it ever breaks.

- **Stop:** set `COLLECT_ENABLED` to `false`. The next run is skipped, so the chain ends when the current run finishes. Cancel the running run on the Actions tab to stop immediately.
- **Restart:** set it back to `true` and press **Run workflow**.

## Budget

10 segments × 60 runs a day (every 15 min, 06:37–21:22 IST) × 31 days = 18,600 requests a month. The TomTom free tier is 20,000 Flow Segment requests a month, leaving room for about 140 manual test runs. Collecting every 15 minutes around the clock would need 29,760, so nights are skipped. Before adding segments, check the total with:

```
TOMTOM_API_KEY=your_key python collector/collect.py --check
```

This makes one request per segment, prints Google Maps links for the point you chose and the road TomTom matched, and shows the monthly total. It writes no files.

## The segments

`segments.csv` covers the Outer Ring Road from Silk Board to Mahadevapura, plus the roads people use instead of it: Hosur Road, Sarjapur Road, HAL Old Airport Road and Varthur Road. Coordinates are points on each road taken from OpenStreetMap. To use a different corridor, replace the rows: right-click a road in Google Maps to copy its coordinates.

The Outer Ring Road is a divided road, so each point measures one direction of travel. The `seg_start_*` and `seg_end_*` columns show which direction TomTom matched.

## Run it somewhere else

Any always-on computer with Python 3.8+ works (this crontab line assumes the computer clock is in IST: 60 runs a day, 07:07–21:52):

```
7,22,37,52 7-21 * * *  cd /path/to/repo && TOMTOM_API_KEY=... python3 collector/collect.py --out data
```

Test without a key or network: `python collector/collect.py --dry-run --out /tmp/test`.
