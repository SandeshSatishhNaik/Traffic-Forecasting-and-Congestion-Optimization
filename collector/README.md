# Bengaluru traffic collector

No sensors, no manual work. GitHub runs `collect.py` every 30 minutes on its own servers. Each run asks TomTom for the current speed on 11 road segments (TomTom gets these from GPS traces of phones and cars) and asks Open-Meteo for the weather. The rows are saved to the `bengaluru-data` branch. After 4–6 weeks you have a time series of about 1,400 readings per segment.

## Setup (about 15 minutes, once)

1. **Decide on repository visibility.** This repository is currently **public**, so the collected data would be public too. TomTom's terms probably do not allow republishing their traffic data; read them. The safe choice is **Settings → General → Danger Zone → Change visibility → Private**. On a free GitHub account, private repositories get 2,000 Actions minutes a month, and this collector uses about 1,500.
2. **Get a free TomTom API key.** Sign up at <https://developer.tomtom.com>. No credit card is needed. Copy the API key from your dashboard.
3. **Add the key to GitHub.** Repository **Settings → Secrets and variables → Actions → Secrets → New repository secret**. Name: `TOMTOM_API_KEY`, value: your key. Never paste the key into a file in the repository.
4. **Test one run.** **Actions** tab → **Collect Bengaluru traffic** → **Run workflow**. After about a minute, a `bengaluru-data` branch appears with `data/tomtom_flow/<month>.csv`.
5. **Check the roads matched correctly.** Open that CSV. Every row should have `status` = `ok`. The `frc` column should be `FRC0`–`FRC3` (major roads). If a row shows `FRC5` or higher, that point snapped to a side street: move its coordinates in `segments.csv` onto the main road.
6. **Switch on the schedule.** Same Settings page → **Variables → New repository variable**. Name: `COLLECT_ENABLED`, value: `true`.
7. **Leave it running.** Once a week, open the Actions tab and check for red (failed) runs.

## Budget

11 segments × 48 runs a day × 31 days = 16,368 requests a month. The TomTom free tier is 20,000 Flow Segment requests a month. Before adding segments, check the total with:

```
TOMTOM_API_KEY=your_key python collector/collect.py --check
```

This makes one request per segment, prints Google Maps links for the point you chose and the road TomTom matched, and shows the monthly total. It writes no files.

## The segments

`segments.csv` covers the Outer Ring Road from Silk Board to Mahadevapura, plus the roads people use instead of it: Hosur Road, Sarjapur Road, HAL Old Airport Road and Varthur Road. Coordinates are points on each road taken from OpenStreetMap. To use a different corridor, replace the rows: right-click a road in Google Maps to copy its coordinates.

The Outer Ring Road is a divided road, so each point measures one direction of travel. The `seg_start_*` and `seg_end_*` columns show which direction TomTom matched.

## Run it somewhere else

Any always-on computer with Python 3.8+ works:

```
*/30 * * * *  cd /path/to/repo && TOMTOM_API_KEY=... python3 collector/collect.py --out data
```

Test without a key or network: `python collector/collect.py --dry-run --out /tmp/test`.
