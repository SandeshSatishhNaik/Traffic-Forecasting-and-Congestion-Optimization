#!/usr/bin/env python3
"""Build a connected road network: TomTom road stretches + OpenStreetMap features.

1. Walk the road. Ask TomTom for the stretch under a seed point, take the far
   end of that stretch, step a few metres past it along the road, and ask again.
   Repeated, this chains gap-free stretches along a road in both directions.
2. Link the stretches: A -> B when a vehicle can leave the end of A into the
   start of B ("flow" links), and a "junction" record where two roads cross.
3. Add free OpenStreetMap features to every stretch: road class, lanes, speed
   limit, signals, intersections, bus stops, metro, schools, hospitals, offices.

Output goes to stdout between BEGIN/END markers (segments.csv, links.csv,
features.csv). If DATA_REPO_TOKEN is set, the full geometry (which is TomTom
data) is also stored in the private data repository instead of being printed.

Run by .github/workflows/build-network.yml. Needs TOMTOM_API_KEY.
Self-test without network: python3 collector/build_network.py --selftest
"""
import argparse
import base64
import csv
import io
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TOMTOM_FLOW = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/{zoom}/json"
OVERPASS_URLS = ("https://overpass.kumi.systems/api/interpreter",
                 "https://overpass-api.de/api/interpreter",
                 "https://overpass.private.coffee/api/interpreter",
                 "https://overpass.openstreetmap.fr/api/interpreter")
R_EARTH = 6371008.8
STEP_OUT_M = (30, 60, 120, 250)   # how far past a stretch end to look for the next stretch
SIDE_M = (0, 12, -12)             # sideways nudges, for roads that curve at the junction
MAX_GAP_M = 90                    # next stretch must start this close to the previous end
MAX_TURN_DEG = 60                 # ... and continue in roughly the same direction
STOP_M = 350                      # a walk ends this close to its target

# Where to start walking. fwd/back: a target point to stop at (the walk ends once the target lies on
# the last stretch), or None to walk a fixed number of stretches. tier: how often the stretches are read
# (core = the Outer Ring Road, context = the roads around it; see loop.sh).
ROUTES = [
    dict(name="orr_ccw", tier="core", seed=(12.9231101, 77.6702694),
         fwd=(13.0003, 77.6803), back=(12.9176, 77.6233), fwd_steps=8, back_steps=8),
    dict(name="orr_cw", tier="core", seed=(12.9529429, 77.7001793),
         fwd=(12.9176, 77.6233), back=(13.0004, 77.6788), fwd_steps=8, back_steps=8),
    dict(name="hosur", tier="context", seed=(12.9131197, 77.6251008),
         fwd=None, back=None, fwd_steps=1, back_steps=0),
    dict(name="old_airport", tier="context", seed=(12.9589276, 77.6633594),
         fwd=None, back=None, fwd_steps=0, back_steps=0),
    dict(name="varthur", tier="context", seed=(12.9561094, 77.7295768),
         fwd=None, back=None, fwd_steps=0, back_steps=0),
]
# The request points of the first ten segments, so their ids and history carry over.
LEGACY = {
    "orr_hsr": (12.9164439, 77.6399669), "orr_iblur": (12.9231101, 77.6702694),
    "orr_bellandur": (12.9292128, 77.6831094), "orr_marathahalli": (12.9529429, 77.7001793),
    "orr_doddanekundi": (12.9750108, 77.6974233), "orr_mahadevapura": (12.9863477, 77.6906140),
    "hosur_bommanahalli": (12.9131197, 77.6251008), "sarjapur_agara": (12.9244884, 77.6451418),
    "old_airport_konena": (12.9589276, 77.6633594), "varthur_kundalahalli": (12.9561094, 77.7295768),
}
# Legacy ids that described the wrong road: not reused, listed in legacy_ids.csv instead.
RENAMED = {"sarjapur_agara": "was labelled Sarjapur Road, but TomTom matched the Outer Ring Road eastbound"}
SILK_BOARD = (12.9176, 77.6233)


# ------------------------------------------------------------------ geometry
def hav_m(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(h))


def bearing(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def dest(p, brg, dist_m):
    d, b = dist_m / R_EARTH, math.radians(brg)
    la1, lo1 = math.radians(p[0]), math.radians(p[1])
    la2 = math.asin(math.sin(la1) * math.cos(d) + math.cos(la1) * math.sin(d) * math.cos(b))
    lo2 = lo1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(la1),
                           math.cos(d) - math.sin(la1) * math.sin(la2))
    return (math.degrees(la2), math.degrees(lo2))


def angdiff(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def poly_m(pts):
    return sum(hav_m(a, b) for a, b in zip(pts, pts[1:]))


def tail_bearing(pts, span=60):
    end = pts[-1]
    for p in reversed(pts[:-1]):
        if hav_m(p, end) >= span:
            return bearing(p, end)
    return bearing(pts[0], end)


def head_bearing(pts, span=60):
    start = pts[0]
    for p in pts[1:]:
        if hav_m(start, p) >= span:
            return bearing(start, p)
    return bearing(start, pts[-1])


def _xy(p, lat0):
    return p[1] * 111320.0 * math.cos(math.radians(lat0)), p[0] * 110540.0


def dist_to_poly_m(p, pts):
    """Return (distance in m, index of nearest segment) from p to the polyline."""
    px, py = _xy(p, p[0])
    best, bi = 1e18, 0
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        ax, ay = _xy(a, p[0])
        bx, by = _xy(b, p[0])
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        t = 0 if l2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / l2))
        d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
        if d < best:
            best, bi = d, i
    return best, bi


def sample(pts, every_m):
    """Points along the polyline roughly every_m apart (with cumulative distance)."""
    out, acc, nxt = [(pts[0], 0.0)], 0.0, every_m
    for a, b in zip(pts, pts[1:]):
        seg = hav_m(a, b)
        while seg and acc + seg >= nxt:
            f = (nxt - acc) / seg
            out.append(((a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])), nxt))
            nxt += every_m
        acc += seg
    if out[-1][1] < acc - 1:
        out.append((pts[-1], acc))
    return out


def thin(pts, min_m):
    out = [pts[0]]
    for p in pts[1:-1]:
        if hav_m(out[-1], p) >= min_m:
            out.append(p)
    out.append(pts[-1])
    return out


def bbox_of(pts, pad_m=0):
    la = [p[0] for p in pts]
    lo = [p[1] for p in pts]
    dl = pad_m / 110540.0
    dn = pad_m / (111320.0 * math.cos(math.radians(la[0])))
    return (min(la) - dl, min(lo) - dn, max(la) + dl, max(lo) + dn)


def bbox_overlap(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


# ------------------------------------------------------------------- HTTP
def http(url, params=None, data=None, headers=None, timeout=60, tries=3):
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    last = "failed"
    for i in range(tries):
        try:
            req = urllib.request.Request(full, data=body, headers={
                "User-Agent": "traffic-forecasting-research/0.1", **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(3 * (i + 1))
                continue
            raise RuntimeError(last) from None
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            last = type(e).__name__
            time.sleep(3 * (i + 1))
    raise RuntimeError(last)


# -------------------------------------------------------- TomTom stretches
def stretch_key(pts):
    return (round(pts[0][0], 4), round(pts[0][1], 4), round(pts[-1][0], 4), round(pts[-1][1], 4))


class Flow:
    """TomTom Flow Segment Data client. fake(lat, lon) -> response dict, for tests."""

    def __init__(self, api_key, zoom=10, fake=None, pause=0.2):
        self.api_key, self.zoom, self.fake, self.pause = api_key, zoom, fake, pause
        self.calls, self.cache = 0, {}

    def stretch(self, lat, lon):
        ck = (round(lat, 5), round(lon, 5))
        if ck in self.cache:
            return self.cache[ck]
        self.calls += 1
        try:
            if self.fake:
                d = self.fake(lat, lon)
            else:
                d = http(TOMTOM_FLOW.format(zoom=self.zoom),
                         {"key": self.api_key, "point": f"{lat},{lon}", "unit": "KMPH", "openLr": "true"})
                time.sleep(self.pause)
        except RuntimeError as e:
            if str(e) in ("HTTP 403", "HTTP 429"):
                raise
            self.cache[ck] = None      # e.g. HTTP 400: no road near this point
            return None
        d = d["flowSegmentData"]
        pts = [(c["latitude"], c["longitude"]) for c in d.get("coordinates", {}).get("coordinate", [])]
        if len(pts) < 2:
            self.cache[ck] = None
            return None
        s = {"pts": pts, "frc": d.get("frc"), "openlr": d.get("openlr"), "key": stretch_key(pts),
             "len_m": poly_m(pts)}
        self.cache[ck] = s
        return s


def step(flow, cur, direction, log):
    """The stretch that follows cur (direction=+1) or precedes it (direction=-1), or None."""
    if direction > 0:
        anchor, travel = cur["pts"][-1], tail_bearing(cur["pts"])
        probe = travel
    else:
        anchor, travel = cur["pts"][0], head_bearing(cur["pts"])
        probe = (travel + 180) % 360
    for d in STEP_OUT_M:
        for side in SIDE_M:
            p = dest(anchor, probe, d)
            if side:
                p = dest(p, probe + 90, side)
            s = flow.stretch(*p)
            if s is None or s["key"] == cur["key"]:
                continue
            if direction > 0:
                gap, turn = hav_m(cur["pts"][-1], s["pts"][0]), angdiff(head_bearing(s["pts"]), travel)
            else:
                gap, turn = hav_m(cur["pts"][0], s["pts"][-1]), angdiff(tail_bearing(s["pts"]), travel)
            ok = gap <= MAX_GAP_M and turn <= MAX_TURN_DEG
            log(f"    probe {d:>3} m side {side:>3}: {s['frc']} {s['len_m']:.0f} m gap {gap:.0f} m turn {turn:.0f} deg -> "
                f"{'accept' if ok else 'reject'}")
            if ok:
                return s
    return None


def walk(flow, seed, direction, target, max_steps, log):
    chain, cur, seen, reason = [], seed, {seed["key"]}, "max_steps"
    for _ in range(max_steps):
        nxt = step(flow, cur, direction, log)
        if nxt is None:
            reason = "lost"
            break
        if nxt["key"] in seen:
            reason = "loop"
            break
        chain.append(nxt)
        seen.add(nxt["key"])
        cur = nxt
        if target and dist_to_poly_m(target, nxt["pts"])[0] < STOP_M:
            reason = "target"
            break
    return chain, reason


def build_stretches(flow, routes, log):
    """Walk every route. Returns stretches in travel order, one list per route."""
    result = []
    for r in routes:
        seed = flow.stretch(*r["seed"])
        if seed is None:
            log(f"route {r['name']}: no stretch at the seed point")
            continue
        log(f"route {r['name']}: seed {seed['frc']} {seed['len_m']:.0f} m")
        fwd, why_f = walk(flow, seed, +1, r["fwd"], r["fwd_steps"], log)
        back, why_b = walk(flow, seed, -1, r["back"], r["back_steps"], log)
        log(f"route {r['name']}: {len(back)} before the seed ({why_b}), {len(fwd)} after ({why_f})")
        result.append((r, list(reversed(back)) + [seed] + fwd))
    return result


def name_stretches(routes_result, legacy_keys):
    """Give ids: keep the id of every stretch the first ten segments already collect (unless RENAMED),
    number the rest along their route. A stretch reached from two routes is kept once."""
    out, seen = [], set()
    for r, chain in routes_result:
        for seq, s in enumerate(chain, 1):
            if s["key"] in seen:
                continue
            seen.add(s["key"])
            old = legacy_keys.get(s["key"])
            sid = old if old and old not in RENAMED else f"{r['name']}_{seq:02d}"
            out.append(dict(s, id=sid, route=r["name"], tier=r["tier"], seq=seq, legacy=old or ""))
    return out


# ------------------------------------------------------------------ links
def make_links(stretches):
    links = []
    for a in stretches:
        for b in stretches:
            if a is b:
                continue
            gap = hav_m(a["pts"][-1], b["pts"][0])
            if gap <= 50 and angdiff(tail_bearing(a["pts"]), head_bearing(b["pts"])) <= 110:
                links.append(dict(from_id=a["id"], to_id=b["id"], kind="flow", gap_m=round(gap),
                                  lat=round(a["pts"][-1][0], 5), lon=round(a["pts"][-1][1], 5)))
    boxes = {s["id"]: bbox_of(s["pts"], 40) for s in stretches}
    for i, a in enumerate(stretches):
        for b in stretches[i + 1:]:
            if a["route"] == b["route"] and abs(a["seq"] - b["seq"]) <= 1:
                continue
            if not bbox_overlap(boxes[a["id"]], boxes[b["id"]]):
                continue
            best = None
            for p, along_m in sample(a["pts"], 20):
                d, j = dist_to_poly_m(p, b["pts"])
                if d <= 30 and (best is None or d < best[0]):
                    best = (d, p, along_m, j)
            if best is None:
                continue
            d, p, along_m, j = best
            ba = bearing(*[q for q in _around(a["pts"], along_m)])
            bb = bearing(b["pts"][j], b["pts"][j + 1])
            ang = angdiff(ba, bb)
            if 35 <= ang <= 145:
                links.append(dict(from_id=a["id"], to_id=b["id"], kind="crossing", gap_m=round(d),
                                  lat=round(p[0], 5), lon=round(p[1], 5)))
    return links


def _around(pts, along_m):
    """Two polyline points around a distance along it, to get the local direction."""
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        seg = hav_m(a, b)
        if acc + seg >= along_m and seg > 0:
            return a, b
        acc += seg
    return pts[-2], pts[-1]


def point_at(pts, m):
    """The point m metres along the polyline."""
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        seg = hav_m(a, b)
        if seg and acc + seg >= m:
            f = (m - acc) / seg
            return (a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]))
        acc += seg
    return pts[-1]


def request_point(flow, s):
    """A point on the stretch that TomTom maps back to the same stretch."""
    for f in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
        p = point_at(s["pts"], f * s["len_m"])
        s2 = flow.stretch(*p)
        if s2 and s2["key"] == s["key"]:
            return p
    return None


# --------------------------------------------------------------- OSM part
_PREFERRED = []


def overpass(query, log, deadline=None, rounds=3):
    """Run an Overpass query. Tries every instance (the last one that worked first), up to `rounds` times."""
    last = "no instance answered"
    for r in range(rounds):
        for url in sorted(OVERPASS_URLS, key=lambda u: u not in _PREFERRED):
            if deadline and time.time() > deadline:
                raise RuntimeError("OSM time budget used up")
            try:
                els = http(url, data={"data": query}, timeout=150, tries=1)["elements"]
                _PREFERRED[:] = [url]
                return els
            except RuntimeError as e:
                last = f"{url.split('/')[2]}: {e}"
                log(f"  overpass {last}")
        time.sleep(10 * (r + 1))
    raise RuntimeError(last)


def poly_arg(pts, min_m=120):
    """Polyline as an Overpass coordinate list, thinned so long stretches stay cheap to query."""
    return ",".join(f"{la:.5f},{lo:.5f}" for la, lo in thin(pts, min_m)[:250])


CAR_ROADS = ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
             "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link", "living_street")
POI_KEYS = ["schools", "hospitals", "malls", "offices", "bus_stops", "metro"]
POI_QUERY = ('nwr["amenity"~"^(school|college|university|hospital)$"]({bb});'
             'nwr["shop"~"^(mall|supermarket)$"]({bb});nwr["office"]({bb});nwr["highway"="bus_stop"]({bb});'
             'nwr["railway"~"^(station|subway_entrance)$"]({bb});')


def poi_class(tags):
    """Which of POI_KEYS an OSM element counts for, or None."""
    a = tags.get("amenity")
    if a in ("school", "college", "university"):
        return "schools"
    if a == "hospital":
        return "hospitals"
    if tags.get("shop") in ("mall", "supermarket"):
        return "malls"
    if "office" in tags:
        return "offices"
    if tags.get("highway") == "bus_stop":
        return "bus_stops"
    if tags.get("railway") in ("station", "subway_entrance") and tags.get("station") not in ("light_rail", "train"):
        return "metro"
    return None


def _maxspeed(v):
    try:
        return float(str(v).split()[0])
    except (ValueError, IndexError):
        return None


def _in_box(p, box):
    return box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]


def osm_features(stretches, log, pause=1.0, budget_s=1500):
    """Signals and points of interest for the whole corridor in two requests, roads once per stretch."""
    deadline = time.time() + budget_s
    south, west, north, east = bbox_of([p for s in stretches for p in s["pts"]], 500)
    bb = f"{south:.5f},{west:.5f},{north:.5f},{east:.5f}"
    sigs, pois = None, None
    try:
        els = overpass(f'[out:json][timeout:120];(node["highway"="traffic_signals"]({bb});'
                       f'node["crossing"="traffic_signals"]({bb}););out;', log, deadline)
        sigs = [(e["lat"], e["lon"]) for e in els if e["type"] == "node"]
        log(f"  {len(sigs)} traffic-signal nodes in the corridor box")
        time.sleep(pause)
        els = overpass(f'[out:json][timeout:150];({POI_QUERY.format(bb=bb)});out center tags;', log, deadline)
        pois = []
        for e in els:
            c = poi_class(e.get("tags", {}))
            pt = (e["lat"], e["lon"]) if "lat" in e else ((e["center"]["lat"], e["center"]["lon"]) if "center" in e else None)
            if c and pt:
                pois.append((c, pt))
        log(f"  {len(pois)} points of interest in the corridor box")
    except (RuntimeError, KeyError, ValueError) as e:
        log(f"  corridor-wide OSM query failed ({e})")
    roads = "|".join(CAR_ROADS)
    rows = []
    for s in stretches:
        km = s["len_m"] / 1000
        f = {"segment_id": s["id"], "length_km": round(km, 3), "frc": s["frc"]}
        if sigs is not None:
            box = bbox_of(s["pts"], 60)
            near = [p for p in sigs if _in_box(p, box) and dist_to_poly_m(p, s["pts"])[0] <= 30]
            f["signals"] = len(near)
            f["signals_per_km"] = round(len(near) / km, 2) if km else ""
            f["dist_signal_start_m"] = round(min((hav_m(s["pts"][0], p) for p in sigs), default=-1))
            f["dist_signal_end_m"] = round(min((hav_m(s["pts"][-1], p) for p in sigs), default=-1))
        if pois is not None:
            box = bbox_of(s["pts"], 350)
            cnt = dict.fromkeys(POI_KEYS, 0)
            for c, p in pois:
                if _in_box(p, box) and dist_to_poly_m(p, s["pts"])[0] <= 300:
                    cnt[c] += 1
            f.update(cnt)
        try:
            els = overpass(f'[out:json][timeout:120];(way(around:45,{poly_arg(s["pts"])})["highway"~"^({roads})$"];>;);out body;',
                           log, deadline)
            time.sleep(pause)
            nodes = {e["id"]: (e["lat"], e["lon"]) for e in els if e["type"] == "node"}
            f.update(_road_tags(s, [e for e in els if e["type"] == "way"], nodes))
        except (RuntimeError, KeyError, ValueError) as e:
            log(f"  {s['id']}: road query failed ({e})")
        rows.append(f)
        log(f"  {s['id']}: OSM features done")
    return rows


def _road_tags(s, ways, nodes):
    """Road class, lanes, speed limit and intersections from the OSM ways next to the stretch."""
    votes = {"highway": {}, "lanes": {}, "maxspeed": {}, "oneway": {}, "name": {}, "way": {}}
    bridge = tunnel = total = 0
    geoms = []
    for w in ways:
        g = [nodes[n] for n in w.get("nodes", []) if n in nodes]
        if len(g) >= 2:
            geoms.append((w, g))
    smp = sample(s["pts"], 50)
    for p, _ in smp:
        best = None
        for w, g in geoms:
            d = dist_to_poly_m(p, g)[0]
            if d <= 25 and (best is None or d < best[0]):
                best = (d, w)
        if best is None:
            continue
        t, total = best[1].get("tags", {}), total + 1
        for k, v in (("highway", t.get("highway")), ("lanes", t.get("lanes")), ("maxspeed", _maxspeed(t.get("maxspeed"))),
                     ("oneway", t.get("oneway")), ("name", t.get("name")), ("way", best[1]["id"])):
            if v is not None:
                votes[k][v] = votes[k].get(v, 0) + 1
        bridge += t.get("bridge") not in (None, "no")
        tunnel += t.get("tunnel") not in (None, "no")

    def top(k):
        return max(votes[k], key=votes[k].get) if votes[k] else ""
    nbrs = {}                       # a node with 3+ different neighbours is an intersection
    for w, _ in geoms:
        ns = w.get("nodes", [])
        for x, y in zip(ns, ns[1:]):
            nbrs.setdefault(x, set()).add(y)
            nbrs.setdefault(y, set()).add(x)
    hubs = []
    for n, nb in nbrs.items():
        if len(nb) >= 3 and n in nodes and dist_to_poly_m(nodes[n], s["pts"])[0] <= 20:
            if all(hav_m(nodes[n], h) > 25 for h in hubs):
                hubs.append(nodes[n])
    km = s["len_m"] / 1000
    lanes = [float(k) for k in votes["lanes"] for _ in range(votes["lanes"][k]) if str(k).replace(".", "").isdigit()]
    return {"osm_road": top("highway"), "osm_name": top("name"), "osm_way_id": top("way"),
            "lanes": round(sum(lanes) / len(lanes), 1) if lanes else "", "maxspeed_kmph": top("maxspeed"),
            "oneway": top("oneway"), "bridge_share": round(bridge / total, 2) if total else "",
            "tunnel_share": round(tunnel / total, 2) if total else "",
            "intersections": len(hubs), "intersections_per_km": round(len(hubs) / km, 2) if km else ""}


# ------------------------------------------------------------ output helpers
def to_csv(rows, fields):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def emit(name, text):
    print(f"----BEGIN {name}----")
    print(text.rstrip("\n"))
    print(f"----END {name}----")


def store_private(path, text, log):
    """Save a file in the private data repository (Contents API). Silent no-op without a token."""
    token, repo = os.environ.get("DATA_REPO_TOKEN"), os.environ.get("DATA_REPO", "SandeshSatishhNaik/traffic-data-private")
    if not token:
        log(f"  no DATA_REPO_TOKEN: {path} not stored (it can be rebuilt by running this again)")
        return
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    hdr = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    try:
        try:
            sha = http(url, headers=hdr)["sha"]
        except RuntimeError:
            sha = None
        body = {"message": f"Update {path}", "content": base64.b64encode(text.encode()).decode()}
        if sha:
            body["sha"] = sha
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="PUT",
                                     headers={**hdr, "User-Agent": "traffic-forecasting-research/0.1"})
        urllib.request.urlopen(req, timeout=60).read()
        log(f"  stored {path} in the private data repository")
    except (urllib.error.URLError, RuntimeError) as e:
        log(f"  could not store {path} privately: {e}")


def run(flow, routes, do_osm, log, legacy=None):
    legacy_keys = {}
    for sid, pt in (LEGACY if legacy is None else legacy).items():
        st = flow.stretch(*pt)
        if st:
            legacy_keys[st["key"]] = sid
    chains = build_stretches(flow, routes, log)
    stretches = name_stretches(chains, legacy_keys)
    log(f"{len(stretches)} stretches, {flow.calls} TomTom requests so far")
    links = make_links(stretches)
    for s in stretches:
        s["req"] = request_point(flow, s)
    log(f"{flow.calls} TomTom requests in total")
    emit_walk(stretches, links)
    feats = osm_features(stretches, log) if do_osm else []
    return stretches, links, feats


def emit_walk(stretches, links):
    """Print the walk result at once, so a slow or failing OSM step cannot lose it."""
    rows = [{"segment_id": s["id"], "route": s["route"], "tier": s["tier"], "seq": s["seq"],
             "legacy_id": s["legacy"], "length_km": round(s["len_m"] / 1000, 3),
             "frc": s["frc"], "req_lat": f"{s['req'][0]:.6f}" if s.get("req") else "",
             "req_lon": f"{s['req'][1]:.6f}" if s.get("req") else "",
             "start_lat": f"{s['pts'][0][0]:.5f}", "start_lon": f"{s['pts'][0][1]:.5f}",
             "end_lat": f"{s['pts'][-1][0]:.5f}", "end_lon": f"{s['pts'][-1][1]:.5f}"} for s in stretches]
    emit("walk.csv", to_csv(rows, list(rows[0]) if rows else []))
    emit("links.csv", to_csv(links, ["from_id", "to_id", "kind", "gap_m", "lat", "lon"]))


def report(stretches, links, feats):
    seg_rows = []
    for s in stretches:
        f = next((x for x in feats if x["segment_id"] == s["id"]), {})
        rq = s.get("req")
        road = f.get("osm_name") or s["route"]
        seg_rows.append({"segment_id": s["id"], "name": f"{road} ({s['route']} #{s['seq']})", "road": road,
                         "lat": f"{rq[0]:.6f}" if rq else "", "lon": f"{rq[1]:.6f}" if rq else "",
                         "osm_way_id": f.get("osm_way_id", ""), "route": s["route"], "tier": s["tier"],
                         "seq": s["seq"], "length_km": round(s["len_m"] / 1000, 3), "frc": s["frc"]})
    emit("segments.csv", to_csv(seg_rows, list(seg_rows[0]) if seg_rows else []))
    alias = [{"old_id": old, "new_id": next((s["id"] for s in stretches if s["legacy"] == old), ""), "note": why}
             for old, why in RENAMED.items()]
    emit("legacy_ids.csv", to_csv(alias, ["old_id", "new_id", "note"]))
    if feats:
        fields = ["segment_id", "length_km", "frc", "osm_road", "osm_name", "lanes", "maxspeed_kmph", "oneway",
                  "bridge_share", "tunnel_share", "signals", "signals_per_km", "dist_signal_start_m",
                  "dist_signal_end_m", "intersections", "intersections_per_km", "schools", "hospitals",
                  "malls", "offices", "bus_stops", "metro"]
        emit("features.csv", to_csv(feats, fields))


def store_geometry(stretches, log):
    doc = [{"segment_id": s["id"], "route": s["route"], "seq": s["seq"], "frc": s["frc"], "openlr": s["openlr"],
            "tier": s["tier"], "legacy_id": s["legacy"], "length_m": round(s["len_m"]), "polyline": [[round(a, 6), round(b, 6)] for a, b in s["pts"]]}
           for s in stretches]
    store_private("network/stretches.json", json.dumps(doc, separators=(",", ":")), log)


# ---------------------------------------------------------------- self-test
def _selftest():
    """Synthetic road: two parallel carriageways 25 m apart cut into stretches, plus a crossing road."""
    base = (12.95, 77.65)
    line = [dest(base, 45, i * 100) for i in range(0, 61)]           # 6 km north-east
    off = lambda pts, m: [dest(p, 135, m) for p in pts]               # shift 25 m to the right
    out_pts, back_pts = off(line, 12.5), list(reversed(off(line, -12.5)))
    cuts = [0, 8, 20, 21, 40, 60]                                     # stretch boundaries (vertex numbers)
    net = []
    for a, b in zip(cuts, cuts[1:]):
        net.append(("out", out_pts[a:b + 1]))
        net.append(("back", back_pts[len(line) - 1 - b:len(line) - 1 - a + 1]))
    cross = [dest(line[30], 315, 1500), dest(line[30], 135, 1500)]     # crosses at vertex 30
    net.append(("cross", [cross[0], dest(cross[0], 135, 1500), cross[1]]))

    def fake(lat, lon):
        best = min(net, key=lambda t: dist_to_poly_m((lat, lon), t[1])[0])
        if dist_to_poly_m((lat, lon), best[1])[0] > 100:
            raise RuntimeError("HTTP 400")
        return {"flowSegmentData": {"frc": "FRC1", "openlr": "x", "coordinates": {"coordinate": [
            {"latitude": p[0], "longitude": p[1]} for p in best[1]]}}}

    routes = [dict(name="road_out", tier="core", seed=out_pts[30], fwd=out_pts[60], back=out_pts[0],
                   fwd_steps=8, back_steps=8),
              dict(name="road_back", tier="core", seed=back_pts[10], fwd=back_pts[60], back=back_pts[0],
                   fwd_steps=8, back_steps=8),
              dict(name="cross", tier="context", seed=cross[0], fwd=None, back=None, fwd_steps=0, back_steps=0)]
    flow = Flow("", fake=fake, pause=0)
    stretches, links, _ = run(flow, routes, False, lambda m: None, legacy={})
    by_route = {}
    for s in stretches:
        by_route.setdefault(s["route"], []).append(s)
    assert len(by_route["road_out"]) == 5, [s["id"] for s in stretches]
    assert len(by_route["road_back"]) == 5
    for r in ("road_out", "road_back"):
        ids = [s["id"] for s in by_route[r]]
        assert len(set(ids)) == 5
    flows = [l for l in links if l["kind"] == "flow"]
    assert len(flows) == 8, flows                                      # 4 links per carriageway
    assert not any(l["from_id"].startswith("road_out") and l["to_id"].startswith("road_back") for l in flows)
    crossings = [l for l in links if l["kind"] == "crossing"]
    assert len(crossings) >= 2, crossings                              # cross road meets both carriageways
    assert all(s.get("req") for s in stretches)
    print("selftest ok:", len(stretches), "stretches,", len(flows), "flow links,", len(crossings), "crossings")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--no-osm", action="store_true", help="skip the OpenStreetMap features")
    ap.add_argument("--verbose", action="store_true", help="print every probe of the walk")
    ap.add_argument("--zoom", type=int, default=10)
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    key = os.environ.get("TOMTOM_API_KEY", "")
    if not key:
        sys.exit("Set TOMTOM_API_KEY.")
    log = (lambda m: print(m, flush=True)) if args.verbose else (
        lambda m: print(m, flush=True) if not m.startswith("    probe") else None)
    flow = Flow(key, zoom=args.zoom)
    stretches, links, feats = run(flow, ROUTES, not args.no_osm, log)
    report(stretches, links, feats)
    store_geometry(stretches, log)
    print(f"Done. {flow.calls} TomTom requests.")


if __name__ == "__main__":
    main()
