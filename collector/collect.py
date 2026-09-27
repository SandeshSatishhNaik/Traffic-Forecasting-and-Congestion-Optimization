#!/usr/bin/env python3
"""Collect Bengaluru traffic speeds (TomTom Traffic Flow) and weather (Open-Meteo).

Each run queries every segment in segments.csv once and appends one row per
segment to a monthly CSV. Run it every 15 minutes during the day (the GitHub
Actions workflow in .github/workflows/collect-bengaluru.yml does this) to build
a time series.

Standard library only, so it runs anywhere Python 3.8+ is installed.

Usage:
  TOMTOM_API_KEY=... python collector/collect.py --out data          # collect
  TOMTOM_API_KEY=... python collector/collect.py --check             # verify segments, write nothing
  python collector/collect.py --dry-run --out /tmp/test              # fake responses, no network
"""
import argparse
import csv
import json
import os
import random
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
TOMTOM_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/{zoom}/json"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
FREE_MONTHLY_REQUESTS = 20000  # TomTom Flow Segment Data free tier (pricing page, Sept 2026)
QUOTA_CODES = {403, 429}

FLOW_FIELDS = [
    "timestamp_utc", "timestamp_ist", "segment_id", "status", "frc",
    "current_speed_kmph", "free_flow_speed_kmph",
    "current_travel_time_s", "free_flow_travel_time_s",
    "confidence", "road_closure",
    "seg_start_lat", "seg_start_lon", "seg_end_lat", "seg_end_lon",
]
WEATHER_FIELDS = [
    "timestamp_utc", "timestamp_ist", "status", "temperature_c",
    "precipitation_mm", "rain_mm", "weather_code", "cloud_cover_pct",
]

DATA_README = """# Bengaluru traffic data

Collected automatically by `collector/collect.py` (see the repository's default branch).

- `tomtom_flow/YYYY-MM.csv`: one row per road segment per run (every 15 min,
  06:37-21:22 IST; no readings at night).
  Speeds in km/h, travel times in seconds. `status` is `ok` or the error for that
  request, so gaps are visible. `frc` is TomTom's road class (FRC0 = motorway ...).
  `seg_*` columns are the ends of the road segment TomTom matched to the point.
- `weather/YYYY-MM.csv`: current weather at the centre of the corridor for each run.

Timestamps are when the request was made, in UTC and IST.
"""


def get_json(url, params, timeout=20):
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": "traffic-forecasting-research/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def read_segments(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("segment_id", "").strip()]
    for r in rows:
        r["lat"], r["lon"] = float(r["lat"]), float(r["lon"])
    return rows


def append_rows(path, fields, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    is_new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if is_new:
            writer.writeheader()
        writer.writerows(rows)


def parse_flow(data):
    d = data["flowSegmentData"]
    coords = d.get("coordinates", {}).get("coordinate", [])
    first, last = (coords[0], coords[-1]) if coords else ({}, {})
    return {
        "status": "ok",
        "frc": d.get("frc"),
        "current_speed_kmph": d.get("currentSpeed"),
        "free_flow_speed_kmph": d.get("freeFlowSpeed"),
        "current_travel_time_s": d.get("currentTravelTime"),
        "free_flow_travel_time_s": d.get("freeFlowTravelTime"),
        "confidence": d.get("confidence"),
        "road_closure": d.get("roadClosure"),
        "seg_start_lat": first.get("latitude"), "seg_start_lon": first.get("longitude"),
        "seg_end_lat": last.get("latitude"), "seg_end_lon": last.get("longitude"),
    }


def fake_flow(seg):
    free = random.choice([40, 50, 60])
    cur = round(free * random.uniform(0.3, 1.0))
    return {"flowSegmentData": {
        "frc": "FRC2", "currentSpeed": cur, "freeFlowSpeed": free,
        "currentTravelTime": round(900 / max(cur, 1)), "freeFlowTravelTime": round(900 / free),
        "confidence": 1.0, "roadClosure": False,
        "coordinates": {"coordinate": [
            {"latitude": seg["lat"] - 0.001, "longitude": seg["lon"] - 0.001},
            {"latitude": seg["lat"] + 0.001, "longitude": seg["lon"] + 0.001}]},
    }}


def collect_flow(segments, key, zoom, dry_run):
    """Return one result dict per segment. Stops calling TomTom after a quota error."""
    results, quota_hit = [], False
    for seg in segments:
        if quota_hit:
            results.append({"status": "skipped_quota"})
            continue
        try:
            data = fake_flow(seg) if dry_run else get_json(
                TOMTOM_URL.format(zoom=zoom),
                {"key": key, "point": f"{seg['lat']},{seg['lon']}", "unit": "KMPH"})
            results.append(parse_flow(data))
        except urllib.error.HTTPError as e:
            results.append({"status": f"http_{e.code}"})
            quota_hit = e.code in QUOTA_CODES
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
            results.append({"status": f"error_{type(e).__name__}"})
    return results


def collect_weather(lat, lon, dry_run):
    if dry_run:
        return {"status": "ok", "temperature_c": 24.0, "precipitation_mm": 0.0,
                "rain_mm": 0.0, "weather_code": 3, "cloud_cover_pct": 80}
    try:
        cur = get_json(WEATHER_URL, {
            "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "timezone": "Asia/Kolkata",
            "current": "temperature_2m,precipitation,rain,weather_code,cloud_cover",
        })["current"]
        return {"status": "ok", "temperature_c": cur.get("temperature_2m"),
                "precipitation_mm": cur.get("precipitation"), "rain_mm": cur.get("rain"),
                "weather_code": cur.get("weather_code"), "cloud_cover_pct": cur.get("cloud_cover")}
    except urllib.error.HTTPError as e:
        return {"status": f"http_{e.code}"}
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
        return {"status": f"error_{type(e).__name__}"}


def maps_link(lat, lon):
    return f"https://www.google.com/maps?q={lat},{lon}"


def print_check(segments, results, runs_per_day):
    print(f"{'segment':<22} {'status':<14} {'frc':<5} {'now/free km/h':<14} matched road segment")
    for seg, r in zip(segments, results):
        speeds = f"{r.get('current_speed_kmph')}/{r.get('free_flow_speed_kmph')}" if r["status"] == "ok" else "-"
        print(f"{seg['segment_id']:<22} {r['status']:<14} {str(r.get('frc') or '-'):<5} {speeds:<14} "
              f"{maps_link(r.get('seg_start_lat'), r.get('seg_start_lon')) if r['status'] == 'ok' else ''}")
        print(f"{'':<22} point you asked for: {maps_link(seg['lat'], seg['lon'])}")
    monthly = len(segments) * runs_per_day * 31
    print(f"\n{len(segments)} segments x {runs_per_day} runs/day x 31 days = {monthly:,} requests/month "
          f"(free tier: {FREE_MONTHLY_REQUESTS:,})")
    if monthly > FREE_MONTHLY_REQUESTS:
        print("WARNING: this exceeds the free tier. Remove segments or run less often.")
    print("Check that each matched segment is on the road you meant (open both links). "
          "FRC0-FRC2 are major roads; FRC5+ usually means the point snapped to a side street.")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--segments", default=os.path.join(here, "segments.csv"))
    ap.add_argument("--out", default="data", help="output folder (created if missing)")
    ap.add_argument("--zoom", type=int, default=10, help="TomTom zoom level used to match the road segment")
    ap.add_argument("--runs-per-day", type=int, default=60, help="only used for the quota estimate")
    ap.add_argument("--check", action="store_true", help="query each segment once, print a report, write nothing")
    ap.add_argument("--dry-run", action="store_true", help="use fake responses, no network, no API key needed")
    args = ap.parse_args()

    key = os.environ.get("TOMTOM_API_KEY", "")
    if not key and not args.dry_run:
        sys.exit("Set the TOMTOM_API_KEY environment variable (free key from developer.tomtom.com).")

    segments = read_segments(args.segments)
    now = datetime.now(timezone.utc)
    stamp = {"timestamp_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
             "timestamp_ist": now.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")}

    flow = collect_flow(segments, key, args.zoom, args.dry_run)
    if args.check:
        print_check(segments, flow, args.runs_per_day)
        return

    month = now.astimezone(IST).strftime("%Y-%m")
    append_rows(os.path.join(args.out, "tomtom_flow", f"{month}.csv"), FLOW_FIELDS,
                [{**stamp, "segment_id": s["segment_id"], **r} for s, r in zip(segments, flow)])

    lat = sum(s["lat"] for s in segments) / len(segments)
    lon = sum(s["lon"] for s in segments) / len(segments)
    append_rows(os.path.join(args.out, "weather", f"{month}.csv"), WEATHER_FIELDS,
                [{**stamp, **collect_weather(lat, lon, args.dry_run)}])

    readme = os.path.join(args.out, "README.md")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as f:
            f.write(DATA_README)

    ok = sum(r["status"] == "ok" for r in flow)
    print(f"{stamp['timestamp_ist']} IST: {ok}/{len(flow)} segments ok")
    if ok == 0:
        sys.exit("No segment returned data. Check the API key and quota.")


if __name__ == "__main__":
    main()
