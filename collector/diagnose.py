#!/usr/bin/env python3
"""One-off diagnostics for the Bengaluru road network. Not part of the collection chain.

Answers four questions with real API responses:
  1. Does TomTom's `zoom` parameter change how long the matched road segment is?
  2. How many OpenStreetMap traffic signals sit on our segments, and do segment
     ends line up with signalised junctions?
  3. What does one TomTom vector flow tile contain (how many roads per request)?
  4. Does TomTom report incidents in this area?

Prints aggregates only (lengths, counts). Never prints the API key.
Run by .github/workflows/diagnose-network.yml (needs the TOMTOM_API_KEY secret).
"""
import collections
import csv
import json
import math
import os
import statistics
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- helpers
def http(url, params=None, timeout=40, binary=False, tries=3, pause=0.3):
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    last = "failed"
    for i in range(tries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": "traffic-forecasting-research/0.1"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
            time.sleep(pause)
            return body if binary else json.loads(body)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 * (i + 1))
                continue
            raise RuntimeError(last) from None
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            last = type(e).__name__
            time.sleep(2 * (i + 1))
    raise RuntimeError(last)


def hav_km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def poly_km(pts):
    return sum(hav_km(a, b) for a, b in zip(pts, pts[1:]))


def xy(lat, lon, lat0):
    return lon * 111320.0 * math.cos(math.radians(lat0)), lat * 110540.0


def dist_to_polyline_m(p, poly):
    px, py = xy(p[0], p[1], p[0])
    best = 1e18
    for a, b in zip(poly, poly[1:]):
        ax, ay = xy(a[0], a[1], p[0])
        bx, by = xy(b[0], b[1], p[0])
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        t = 0 if l2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / l2))
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best


# ------------------------------------------- minimal Mapbox-vector-tile decoder
def read_varint(buf, i):
    shift = result = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7


def parse_msg(buf):
    i, n = 0, len(buf)
    while i < n:
        key, i = read_varint(buf, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            val, i = read_varint(buf, i)
        elif wire == 1:
            val = buf[i:i + 8]
            i += 8
        elif wire == 2:
            ln, i = read_varint(buf, i)
            val = buf[i:i + ln]
            i += ln
        elif wire == 5:
            val = buf[i:i + 4]
            i += 4
        else:
            raise ValueError("bad wire type")
        yield field, wire, val


def packed_varints(b):
    out, i = [], 0
    while i < len(b):
        v, i = read_varint(b, i)
        out.append(v)
    return out


def decode_value(b):
    for f, w, v in parse_msg(b):
        if f == 1:
            return v.decode("utf-8", "replace")
        if f == 2:
            return struct.unpack("<f", v)[0]
        if f == 3:
            return struct.unpack("<d", v)[0]
        if f == 4:
            return v if v < 2 ** 63 else v - 2 ** 64
        if f == 5:
            return v
        if f == 6:
            return (v >> 1) ^ -(v & 1)
        if f == 7:
            return bool(v)
    return None


def decode_tile(buf):
    layers = []
    for f, w, v in parse_msg(buf):
        if f != 3:
            continue
        layer = {"name": "", "features": [], "keys": [], "values": []}
        for lf, lw, lv in parse_msg(v):
            if lf == 1:
                layer["name"] = lv.decode("utf-8", "replace")
            elif lf == 2:
                feat = {"type": None, "tags": [], "geom": []}
                for ff, fw, fv in parse_msg(lv):
                    if ff == 2:
                        feat["tags"] = packed_varints(fv)
                    elif ff == 3:
                        feat["type"] = fv
                    elif ff == 4:
                        feat["geom"] = packed_varints(fv)
                layer["features"].append(feat)
            elif lf == 3:
                layer["keys"].append(lv.decode("utf-8", "replace"))
            elif lf == 4:
                layer["values"].append(decode_value(lv))
        layers.append(layer)
    return layers


def feature_props(layer, feat):
    t = feat["tags"]
    return {layer["keys"][t[i]]: layer["values"][t[i + 1]] for i in range(0, len(t) - 1, 2)}


def tile_xy(lat, lon, z):
    n = 2 ** z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


# ------------------------------------------------------------------ main
def main():
    key = os.environ.get("TOMTOM_API_KEY", "")
    if not key:
        sys.exit("TOMTOM_API_KEY is not set")
    segs = list(csv.DictReader(open(os.path.join(HERE, "segments.csv"), encoding="utf-8")))

    # 1. zoom vs segment length -------------------------------------------------
    print("=" * 78)
    print("1. TomTom Flow Segment Data: does `zoom` change the matched segment?")
    print("=" * 78)
    zooms = [8, 10, 12, 14, 16, 18, 20, 22]
    polys, table = {}, collections.defaultdict(dict)
    frcs = collections.defaultdict(dict)
    openlr_seen = 0
    for s in segs:
        sid = s["segment_id"]
        for z in zooms:
            try:
                d = http(f"https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/{z}/json",
                         {"key": key, "point": f"{s['lat']},{s['lon']}", "unit": "KMPH", "openLr": "true"})["flowSegmentData"]
            except RuntimeError as e:
                table[sid][z] = str(e)
                continue
            pts = [(c["latitude"], c["longitude"]) for c in d.get("coordinates", {}).get("coordinate", [])]
            polys[(sid, z)] = pts
            ln = poly_km(pts) if len(pts) > 1 else 0.0
            table[sid][z] = ln
            frcs[sid][z] = d.get("frc", "?")
            if d.get("openlr"):
                openlr_seen += 1
    print("Length of the matched road segment in km (polyline length) by zoom level:")
    print(f"{'segment':22}" + "".join(f"{'z' + str(z):>8}" for z in zooms) + "   frc@z10 -> frc@z22")
    for s in segs:
        sid = s["segment_id"]
        row = "".join((f"{table[sid][z]:8.2f}" if isinstance(table[sid].get(z), float) else f"{str(table[sid].get(z, '-')):>8}") for z in zooms)
        print(f"{sid:22}{row}   {frcs[sid].get(10, '?')} -> {frcs[sid].get(22, '?')}")
    print(f"OpenLR code returned in {openlr_seen} of {len(segs) * len(zooms)} responses")
    # do finer segments nest inside the z10 segment?
    print("\nSegment start/end at z10 vs z18 (rounded to 4 decimals):")
    for s in segs:
        sid = s["segment_id"]
        for z in (10, 18):
            p = polys.get((sid, z))
            if p and len(p) > 1:
                print(f"  {sid:22} z{z}: ({p[0][0]:.4f},{p[0][1]:.4f}) -> ({p[-1][0]:.4f},{p[-1][1]:.4f})  {len(p)} pts")

    # 2. OSM signals ------------------------------------------------------------
    print("\n" + "=" * 78)
    print("2. OpenStreetMap traffic signals near our segments")
    print("=" * 78)
    base = {sid: polys[(sid, 10)] for sid in [s["segment_id"] for s in segs] if polys.get((sid, 10))}
    allpts = [p for pts in base.values() for p in pts]
    south, north = min(p[0] for p in allpts) - 0.01, max(p[0] for p in allpts) + 0.01
    west, east = min(p[1] for p in allpts) - 0.01, max(p[1] for p in allpts) + 0.01
    print(f"bbox (S,W,N,E) = {south:.3f},{west:.3f},{north:.3f},{east:.3f}")
    query = (f'[out:json][timeout:90];(node["highway"="traffic_signals"]({south},{west},{north},{east});'
             f'node["crossing"="traffic_signals"]({south},{west},{north},{east}););out;')
    els = None
    for url in ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
                "https://overpass.private.coffee/api/interpreter"):
        try:
            els = http(url, {"data": query}, timeout=120, tries=2)["elements"]
            print("Overpass instance:", url.split("/")[2])
            break
        except RuntimeError as e:
            print("Overpass instance", url.split("/")[2], "failed:", e)
    if els is None:
        print("No Overpass instance answered; skipping signal analysis.")
    else:
        sig = [(e["lat"], e["lon"]) for e in els if e.get("tags", {}).get("highway") == "traffic_signals"]
        cross = [(e["lat"], e["lon"]) for e in els if e.get("tags", {}).get("highway") != "traffic_signals"
                 and e.get("tags", {}).get("crossing") == "traffic_signals"]
        print(f"In the bbox: {len(sig)} nodes tagged highway=traffic_signals, "
              f"{len(cross)} extra pedestrian-crossing signals")
        allsig = sig + cross
        print(f"\n{'segment':22}{'len km':>8}{'signals':>9}{'per km':>8}{'start->nearest':>16}{'end->nearest':>14}")
        for s in segs:
            sid = s["segment_id"]
            p = base.get(sid)
            if not p:
                continue
            ln = poly_km(p)
            near = [q for q in allsig if dist_to_polyline_m(q, p) <= 30]
            ds = min((hav_km(p[0], q) * 1000 for q in allsig), default=-1)
            de = min((hav_km(p[-1], q) * 1000 for q in allsig), default=-1)
            print(f"{sid:22}{ln:8.2f}{len(near):9d}{len(near) / max(ln, 1e-9):8.1f}{ds:14.0f} m{de:12.0f} m")
        print("(signals counted within 30 m of the segment's polyline; 'nearest' = metres from segment start/end to the closest signal)")

    # 3. vector flow tiles ------------------------------------------------------
    print("\n" + "=" * 78)
    print("3. TomTom vector flow tiles: what one request contains")
    print("=" * 78)
    for z in (13, 14):
        x0, y0 = tile_xy(north, west, z)
        x1, y1 = tile_xy(south, east, z)
        print(f"zoom {z}: {(x1 - x0 + 1)} x {(y1 - y0 + 1)} = {(x1 - x0 + 1) * (y1 - y0 + 1)} tiles cover the whole bbox")
    z = 13
    x0, y0 = tile_xy(north, west, z)
    x1, y1 = tile_xy(south, east, z)
    total_feats = 0
    cats = collections.Counter()
    levels = []
    key_names = set()
    layer_names = collections.Counter()
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            try:
                body = http(f"https://api.tomtom.com/traffic/map/4/tile/flow/absolute/{z}/{x}/{y}.pbf",
                            {"key": key}, binary=True, timeout=40)
                layers = decode_tile(body)
            except (RuntimeError, ValueError, IndexError, struct.error) as e:
                print(f"  tile {z}/{x}/{y}: error {e}")
                continue
            nf = 0
            for layer in layers:
                layer_names[layer["name"]] += len(layer["features"])
                key_names.update(layer["keys"])
                for f in layer["features"]:
                    nf += 1
                    pr = feature_props(layer, f)
                    cats[pr.get("road_category", pr.get("road_type", "?"))] += 1
                    if isinstance(pr.get("traffic_level"), (int, float)):
                        levels.append(float(pr["traffic_level"]))
            total_feats += nf
            print(f"  tile {z}/{x}/{y}: {len(body):6d} bytes, {nf:5d} road features")
    print(f"total road features in the z{z} tiles: {total_feats}")
    print("layers:", dict(layer_names))
    print("property names:", sorted(key_names))
    print("by road category:", dict(cats))
    if levels:
        print(f"traffic_level (absolute, km/h) over all features: min {min(levels):.0f}, "
              f"median {statistics.median(levels):.0f}, max {max(levels):.0f}; "
              f"distinct values {len(set(round(v, 1) for v in levels))}")
    try:
        body = http(f"https://api.tomtom.com/traffic/map/4/tile/flow/relative/{z}/{x0}/{y0}.pbf", {"key": key}, binary=True)
        lv = []
        for layer in decode_tile(body):
            for f in layer["features"]:
                v = feature_props(layer, f).get("traffic_level")
                if isinstance(v, (int, float)):
                    lv.append(float(v))
        if lv:
            print(f"style 'relative' on tile {z}/{x0}/{y0}: traffic_level min {min(lv):.2f} median {statistics.median(lv):.2f} max {max(lv):.2f}")
    except (RuntimeError, ValueError, IndexError, struct.error) as e:
        print("style 'relative' failed:", e)

    # 4. incidents ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("4. TomTom traffic incidents in the bbox right now")
    print("=" * 78)
    try:
        inc = http("https://api.tomtom.com/traffic/services/5/incidentDetails",
                   {"key": key, "bbox": f"{west},{south},{east},{north}",
                    "fields": "{incidents{type,properties{iconCategory,magnitudeOfDelay,startTime,endTime,length,delay,timeValidity}}}",
                    "language": "en-GB", "timeValidityFilter": "present"})
        items = inc.get("incidents", [])
        names = {0: "unknown", 1: "accident", 2: "fog", 3: "dangerous conditions", 4: "rain", 5: "ice", 6: "jam",
                 7: "lane closed", 8: "road closed", 9: "road works", 10: "wind", 11: "flooding", 14: "broken down vehicle"}
        print(f"{len(items)} incidents")
        print("by type:", dict(collections.Counter(names.get(i["properties"].get("iconCategory"), i["properties"].get("iconCategory")) for i in items)))
        print("by delay magnitude (0 unknown .. 4 undefined):", dict(collections.Counter(i["properties"].get("magnitudeOfDelay") for i in items)))
    except RuntimeError as e:
        print("incident request failed:", e)
    print("\nDone.")


if __name__ == "__main__":
    main()
