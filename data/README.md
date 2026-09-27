# Bengaluru traffic data

Collected automatically by `collector/collect.py` (see the repository's default branch).

- `tomtom_flow/YYYY-MM.csv`: one row per road segment per run (every 30 min).
  Speeds in km/h, travel times in seconds. `status` is `ok` or the error for that
  request, so gaps are visible. `frc` is TomTom's road class (FRC0 = motorway ...).
  `seg_*` columns are the ends of the road segment TomTom matched to the point.
- `weather/YYYY-MM.csv`: current weather at the centre of the corridor for each run.

Timestamps are when the request was made, in UTC and IST.
