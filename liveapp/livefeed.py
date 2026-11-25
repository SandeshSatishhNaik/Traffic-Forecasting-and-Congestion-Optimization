"""Live data for the app: keep the local data cache up to date, in a background thread.

Two sources:
  github  (default) the project's own collector writes TomTom readings to the bengaluru-data branch every
          15 minutes (rush hours) to 2 hours (night). This downloads the newest monthly files. No key, and
          no extra TomTom requests.
  tomtom  asks TomTom directly for all 21 stretches (needs TOMTOM_API_KEY, 21 requests per refresh, so it is
          rate-limited), plus Open-Meteo for weather. Also records the exact road shapes (geometry.json).

The cache has the same layout as the data branch (tomtom_flow/, weather/), so the models read it unchanged
and the app still starts without internet from the last download.
"""
import datetime
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "collector"))

import collect  # noqa: E402  (the project's tested TomTom / Open-Meteo request code)

REPO = os.environ.get("TRAFFIC_DATA_REPO", "SandeshSatishhNaik/Traffic-Forecasting-and-Congestion-Optimization")
BRANCH = os.environ.get("TRAFFIC_DATA_BRANCH", "bengaluru-data")
RAW = "https://raw.githubusercontent.com/{repo}/{branch}/data/{kind}/{month}.csv"
CACHE = os.path.join(HERE, "data", "cache")
GEOMETRY_JSON = os.path.join(HERE, "data", "geometry.json")
FIRST_MONTH = "2026-09"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
FLOW_FIELDS = ["timestamp_utc", "timestamp_ist", "segment_id", "status", "frc", "current_speed_kmph", "free_flow_speed_kmph",
               "current_travel_time_s", "free_flow_travel_time_s", "confidence", "road_closure",
               "seg_start_lat", "seg_start_lon", "seg_end_lat", "seg_end_lon"]
WEATHER_FIELDS = ["timestamp_utc", "timestamp_ist", "status", "temperature_c", "precipitation_mm", "rain_mm", "weather_code", "cloud_cover_pct"]


def months(until=None):
    until = until or datetime.datetime.now(IST)
    y, m = map(int, FIRST_MONTH.split("-"))
    out = []
    while (y, m) <= (until.year, until.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _etags(cache):
    p = os.path.join(cache, "etags.json")
    return (json.load(open(p)) if os.path.exists(p) else {}), p


def sync_github(cache=CACHE, all_months=False, timeout=60):
    """Download the monthly files that changed. Returns (files updated, bytes downloaded)."""
    tags, tag_path = _etags(cache)
    ms = months()
    if not all_months:
        ms = [m for m in ms if m in ms[-2:] or not os.path.exists(os.path.join(cache, "tomtom_flow", f"{m}.csv"))]
    updated, nbytes = [], 0
    for kind in ("tomtom_flow", "weather"):
        for m in ms:
            url = RAW.format(repo=REPO, branch=BRANCH, kind=kind, month=m)
            path = os.path.join(cache, kind, f"{m}.csv")
            hdr = {"User-Agent": "traffic-liveapp/1.0"}
            if url in tags and os.path.exists(path):
                hdr["If-None-Match"] = tags[url]
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=timeout) as r:
                    body = r.read()
                    etag = r.headers.get("ETag")
            except urllib.error.HTTPError as e:
                if e.code in (304, 404):
                    continue
                raise
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".part"
            with open(tmp, "wb") as f:
                f.write(body)
            os.replace(tmp, path)
            if etag:
                tags[url] = etag
            updated.append(f"{kind}/{m}.csv")
            nbytes += len(body)
    json.dump(tags, open(tag_path, "w"))
    return updated, nbytes


def fetch_tomtom(key, cache=CACHE, zoom=10):
    """One reading of every stretch straight from TomTom, appended to the cache; also saves the exact road shapes."""
    segs = collect.read_segments(os.path.join(ROOT, "collector", "segments.csv"))
    now = datetime.datetime.now(datetime.timezone.utc)
    stamp_utc, stamp_ist = now.strftime("%Y-%m-%dT%H:%M:%SZ"), now.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
    rows, shapes, ok = [], {}, 0
    for seg in segs:
        try:
            data = collect.get_json(collect.TOMTOM_URL.format(zoom=zoom), {"key": key, "point": f"{seg['lat']},{seg['lon']}", "unit": "KMPH"})
            row = collect.parse_flow(data)
            coords = data["flowSegmentData"].get("coordinates", {}).get("coordinate", [])
            if len(coords) >= 2:
                shapes[seg["segment_id"]] = [[round(c["latitude"], 6), round(c["longitude"], 6)] for c in coords]
            ok += 1
        except urllib.error.HTTPError as e:
            row = {"status": f"http_{e.code}"}
            if e.code in collect.QUOTA_CODES:
                rows.append(dict(row, timestamp_utc=stamp_utc, timestamp_ist=stamp_ist, segment_id=seg["segment_id"]))
                break
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
            row = {"status": f"error_{type(e).__name__}"}
        rows.append(dict(row, timestamp_utc=stamp_utc, timestamp_ist=stamp_ist, segment_id=seg["segment_id"]))
    month = now.astimezone(IST).strftime("%Y-%m")
    collect.append_rows(os.path.join(cache, "tomtom_flow", f"live-{month}.csv"), FLOW_FIELDS, rows)
    try:
        lat = sum(s["lat"] for s in segs) / len(segs)
        lon = sum(s["lon"] for s in segs) / len(segs)
        w = collect.collect_weather(lat, lon, False)
        collect.append_rows(os.path.join(cache, "weather", f"live-{month}.csv"), WEATHER_FIELDS,
                            [dict({k: w.get(k) for k in WEATHER_FIELDS}, timestamp_utc=stamp_utc, timestamp_ist=stamp_ist)])
    except Exception:  # weather is optional
        pass
    if shapes:
        save_shapes(shapes)
    return ok, len(rows)


def save_shapes(shapes):
    old = json.load(open(GEOMETRY_JSON)) if os.path.exists(GEOMETRY_JSON) else {}
    old.update(shapes)
    os.makedirs(os.path.dirname(GEOMETRY_JSON), exist_ok=True)
    json.dump(old, open(GEOMETRY_JSON, "w"))


class LiveFeed(threading.Thread):
    """Refreshes the cache every `interval` seconds and calls on_update() when new readings arrived."""

    def __init__(self, source, on_update, interval=None, key=None, max_tomtom_per_day=420):
        super().__init__(daemon=True)
        self.source = source
        self.on_update = on_update
        self.key = key
        self.interval = interval or (900 if source == "tomtom" else 180)
        self.max_tomtom = max_tomtom_per_day
        self.used_today, self.day, self.last_fetch = 0, None, None
        self.wake = threading.Event()
        self.state = dict(source=source, interval_s=self.interval, last_attempt=None, last_success=None,
                          last_change=None, last_error=None, next_at=None, detail=None)

    def refresh_now(self):
        self.wake.set()

    def step(self):
        st = self.state
        st["last_attempt"] = datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        try:
            if self.source == "github":
                files, nbytes = sync_github()
                st["detail"] = f"{len(files)} file(s) updated, {nbytes / 1e6:.1f} MB" if files else "no new readings yet"
                changed = bool(files)
            else:
                if self.last_fetch and time.time() - self.last_fetch < 300:
                    st["detail"] = "TomTom asked less than 5 minutes ago; waiting (protects the free quota)"
                    return
                today = datetime.datetime.now(IST).date()
                if self.day != today:
                    self.day, self.used_today = today, 0
                if self.used_today + 21 > self.max_tomtom:
                    st["detail"] = f"daily TomTom limit for the app reached ({self.used_today} requests)"
                    return
                ok, n = fetch_tomtom(self.key)
                self.last_fetch = time.time()
                self.used_today += n
                st["detail"] = f"{ok} of 21 stretches read, {self.used_today} TomTom requests today"
                changed = ok > 0
            st["last_success"] = st["last_attempt"]
            st["last_error"] = None
            if changed and self.on_update():
                st["last_change"] = st["last_attempt"]
        except Exception as e:  # keep running on network errors: the app falls back to the cache
            st["last_error"] = f"{type(e).__name__}: {e}"[:200]

    def run(self):
        while True:
            self.step()
            nxt = datetime.datetime.now(IST) + datetime.timedelta(seconds=self.interval)
            self.state["next_at"] = nxt.strftime("%Y-%m-%d %H:%M:%S")
            self.wake.wait(self.interval)
            self.wake.clear()

