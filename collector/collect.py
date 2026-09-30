#!/usr/bin/env python3
"""Collect Bengaluru traffic speeds (TomTom Traffic Flow) and weather (Open-Meteo).

Each run queries every segment in segments.csv once and appends one row per
segment to a monthly CSV. collector/loop.sh runs it 56 times a day, around the
clock (every 15 min in rush hours, every 30 min midday, hourly at night), to
build a time series.

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
INCIDENT_URL = "https://api.tomtom.com/traffic/services/5/incidentDetails"
FREE_MONTHLY_REQUESTS = 20000  # TomTom Flow Segment Data free tier (pricing page, Sept 2026)
FREE_MONTHLY_INCIDENT_REQUESTS = 2500  # TomTom Traffic Incidents free tier
QUOTA_CODES = {403, 429}

FLOW_FIELDS = [
    "timestamp_utc", "timestamp_ist", "segment_id", "status", "frc",
    "current_speed_kmph", "free_flow_speed_kmph",
    "current_travel_time_s", "free_flow_travel_time_s",
    "confidence", "road_closure",
    "seg_start_lat", "seg_start_lon", "seg_end_lat", "seg_end_lon",
]
INCIDENT_FIELDS = [
    "timestamp_utc", "timestamp_ist", "status", "incident_id", "category", "magnitude_of_delay",
    "start_time", "end_time", "from_place", "to_place", "road_numbers", "length_m", "delay_s",
    "probability", "number_of_reports", "lat", "lon",
]
INCIDENT_CATEGORIES = {0: "unknown", 1: "accident", 2: "fog", 3: "dangerous_conditions", 4: "rain", 5: "ice",
                       6: "jam", 7: "lane_closed", 8: "road_closed", 9: "road_works", 10: "wind",
                       11: "flooding", 14: "broken_down_vehicle"}
INCIDENT_QUERY = ("{incidents{type,geometry{type,coordinates},properties{id,iconCategory,magnitudeOfDelay,"
                  "startTime,endTime,from,to,length,delay,roadNumbers,probabilityOfOccurrence,"
                  "numberOfReports}}}")
WEATHER_FIELDS = [
    "timestamp_utc", "timestamp_ist", "status", "temperature_c",
    "precipitation_mm", "rain_mm", "weather_code", "cloud_cover_pct",
]

DATA_README = """# Bengaluru traffic data

Collected automatically by `collector/collect.py` (see the repository's default branch).

- `tomtom_flow/YYYY-MM.csv`: one row per road segment per run, around the clock:
  every 15 min 07:07-11:07 and 16:07-21:07 IST, every 30 min midday, hourly at
  night.
  Speeds in km/h, travel times in seconds. `status` is `ok` or the error for that
  request, so gaps are visible. `frc` is TomTom's road class (FRC0 = motorway ...).
  `seg_*` columns are the ends of the road segment TomTom matched to the point.
- `weather/YYYY-MM.csv`: current weather at the centre of the corridor for each run.
- `incidents/YYYY-MM.csv`: TomTom traffic incidents (accidents, jams, closures, road works) active
  in the corridor's area, one row per incident at every half-hour poll. A row with an empty
  `incident_id` and `status` ok means the poll worked and found none.

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


def bbox_of_segments(segments, pad=0.02):
    """TomTom bbox string west,south,east,north around all segment points (pad in degrees, about 2 km)."""
    return "{:.5f},{:.5f},{:.5f},{:.5f}".format(
        min(s["lon"] for s in segments) - pad, min(s["lat"] for s in segments) - pad,
        max(s["lon"] for s in segments) + pad, max(s["lat"] for s in segments) + pad)


def first_coordinate(geometry):
    """(lat, lon) of the first point of a GeoJSON Point or LineString."""
    c = (geometry or {}).get("coordinates")
    while isinstance(c, list) and c and isinstance(c[0], list):
        c = c[0]
    return (c[1], c[0]) if isinstance(c, list) and len(c) >= 2 else (None, None)


def collect_incidents(bbox, key, dry_run):
    """Return one row per incident currently active in the bbox, or one status row on failure.
    A successful poll with no incidents returns one row with an empty incident_id."""
    if dry_run:
        items = [{"geometry": {"type": "Point", "coordinates": [77.65, 12.93]}, "properties": {
            "id": "dry-1", "iconCategory": 6, "magnitudeOfDelay": 2, "length": 500, "delay": 120}}]
    else:
        try:
            items = get_json(INCIDENT_URL, {
                "key": key, "bbox": bbox, "fields": INCIDENT_QUERY, "language": "en-GB",
                "timeValidityFilter": "present"}, timeout=30).get("incidents", [])
        except urllib.error.HTTPError as e:
            return [{"status": f"http_{e.code}"}]
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            return [{"status": f"error_{type(e).__name__}"}]
    rows = []
    for it in items:
        p = it.get("properties", {})
        lat, lon = first_coordinate(it.get("geometry"))
        rows.append({
            "status": "ok", "incident_id": p.get("id"),
            "category": INCIDENT_CATEGORIES.get(p.get("iconCategory"), p.get("iconCategory")),
            "magnitude_of_delay": p.get("magnitudeOfDelay"), "start_time": p.get("startTime"),
            "end_time": p.get("endTime"), "from_place": p.get("from"), "to_place": p.get("to"),
            "road_numbers": "|".join(p.get("roadNumbers") or []), "length_m": p.get("length"),
            "delay_s": p.get("delay"), "probability": p.get("probabilityOfOccurrence"),
            "number_of_reports": p.get("numberOfReports"), "lat": lat, "lon": lon})
    return rows or [{"status": "ok", "incident_id": ""}]


def incidents_check(segments, key):
    """Print whether the incident request works, and which fields come back. No values."""
    bbox = bbox_of_segments(segments)
    try:
        data = get_json(INCIDENT_URL, {"key": key, "bbox": bbox, "fields": INCIDENT_QUERY, "language": "en-GB",
                                       "timeValidityFilter": "present"}, timeout=30)
    except urllib.error.HTTPError as e:
        sys.exit(f"incident request failed: HTTP {e.code} {e.read()[:300]!r}")
    items = data.get("incidents", [])
    keys = sorted({k for it in items for k in it.get("properties", {})})
    print(f"incident request ok: {len(items)} incidents in bbox {bbox}")
    print("property fields returned:", keys)
    rows = collect_incidents(bbox, key, False)
    print(f"parsed into {len(rows)} rows; statuses: {sorted({r['status'] for r in rows})}; "
          f"with coordinates: {sum(1 for r in rows if r.get('lat') is not None)}")


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
    ap.add_argument("--runs-per-day", type=int, default=56, help="only used for the quota estimate")
    ap.add_argument("--check", action="store_true", help="query each segment once, print a report, write nothing")
    ap.add_argument("--incidents", action="store_true", help="also poll TomTom traffic incidents in the segments' area")
    ap.add_argument("--incidents-check", action="store_true", help="test the incident request, print field names only")
    ap.add_argument("--dry-run", action="store_true", help="use fake responses, no network, no API key needed")
    args = ap.parse_args()

    key = os.environ.get("TOMTOM_API_KEY", "")
    if not key and not args.dry_run:
        sys.exit("Set the TOMTOM_API_KEY environment variable (free key from developer.tomtom.com).")

    segments = read_segments(args.segments)
    if args.incidents_check:
        incidents_check(segments, key)
        return
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

    if args.incidents:
        inc = collect_incidents(bbox_of_segments(segments), key, args.dry_run)
        append_rows(os.path.join(args.out, "incidents", f"{month}.csv"), INCIDENT_FIELDS,
                    [{**stamp, **r} for r in inc])
        print(f"incidents: {inc[0]['status'] if inc[0]['status'] != 'ok' else sum(1 for r in inc if r.get('incident_id'))}")

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
