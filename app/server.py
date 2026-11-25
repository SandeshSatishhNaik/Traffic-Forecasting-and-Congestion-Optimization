#!/usr/bin/env python3
"""Offline traffic intelligence app: a local web server with a JSON API and a browser interface.

Runs with the Python standard library only (no internet, no packages, no model at run time):

  python app/server.py                       # uses app/data/bundle.json, opens the browser
  python app/server.py --bundle my.json --port 8080 --no-browser

API (all GET, JSON):
  /api/meta                      road stretches, layout, replay times, model information
  /api/state?i=<slot>            speed now, forecasts for +15/+30/+60 min, what actually happened, alerts
  /api/route?src=<id>&dst=<id>&i=<slot>
                                 fastest route by time-dependent Dijkstra on the forecast, compared with the
                                 route a live map would pick from current speeds, and with the recorded trip
  /api/results                   aggregate model results (from the project's result files)

The data is a replay of recorded days (see app/build_bundle.py); nothing here is live.
"""
import argparse
import heapq
import json
import math
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}
H = (15, 30, 60)


class Model:
    """Everything the API needs, computed from the bundle with plain Python."""

    def __init__(self, bundle_path, results_path):
        with open(bundle_path, encoding="utf-8") as f:
            self.B = json.load(f)
        with open(results_path, encoding="utf-8") as f:
            self.results = json.load(f)
        B = self.B
        self.ids = [r["id"] for r in B["roads"]]
        self.road = {r["id"]: r for r in B["roads"]}
        self.n = len(B["times"])
        self.thr = B["meta"]["thresholds"]
        self.turn = B["meta"]["turn_penalty_min"]
        self.frac = B["frac"]
        # directed edges: flow links, turns at crossings (both ways), assumed links (fixed time)
        self.E = {r: [] for r in self.ids}
        for x in B["links"]:
            if x["kind"] == "flow":
                self.E[x["src"]].append((x["dst"], 0.0, False))
            else:
                self.E[x["src"]].append((x["dst"], self.turn, False))
                self.E[x["dst"]].append((x["src"], self.turn, False))
        for x in B["assumed"]:
            self.E[x["src"]].append((x["dst"], x["km"] / x["kmph"] * 60.0, True))

    # ------------------------------------------------------------------ helpers
    def level(self, v, r):
        if v is None:
            return "none"
        q = v / self.road[r]["ref"]
        return "severe" if q < self.thr["severe"] else "slow" if q < self.thr["slow"] else "free"

    def last_known(self, r, i, back=8):
        for k in range(i, max(-1, i - back - 1), -1):
            v = self.B["now"][r][k]
            if v is not None:
                return v, i - k
        return None, None

    def meta(self):
        B = self.B
        return dict(meta=B["meta"], times=B["times"], daytype=B["daytype"], roads=B["roads"], links=B["links"],
                    chains=B["chains"], trip_presets=B["trip_presets"], accuracy=B["accuracy"], assumed=B["assumed"])

    # ------------------------------------------------------------------ state at one slot
    def state(self, i):
        B = self.B
        roads, alerts = {}, []
        for r in self.ids:
            d = dict(now=B["now"][r][i], now_level=self.level(B["now"][r][i], r), ref=self.road[r]["ref"])
            for h in H:
                f, a = B["forecast"][str(h)][r][i], B["actual"][str(h)][r][i]
                d[f"f{h}"], d[f"a{h}"] = f, a
                d[f"f{h}_level"], d[f"a{h}_level"] = self.level(f, r), self.level(a, r)
                if d[f"f{h}_level"] in ("slow", "severe"):
                    alerts.append(dict(road=r, label=self.road[r]["label"], dir=self.road[r]["road"], h=h, level=d[f"f{h}_level"],
                                       forecast=f, now=d["now"], new=d["now_level"] not in ("slow", "severe"),
                                       actual=a, confirmed=None if a is None else self.level(a, r) in ("slow", "severe")))
            roads[r] = d
        core = [r for r in self.ids if self.road[r]["tier"] == "core"]

        def avg_ratio(key):
            v = [roads[r][key] / roads[r]["ref"] for r in core if roads[r][key] is not None]
            return round(sum(v) / len(v), 3) if v else None
        summary = dict(now=avg_ratio("now"), **{f"f{h}": avg_ratio(f"f{h}") for h in H})
        alerts.sort(key=lambda a: (a["h"], a["level"] != "severe", a["label"]))
        trips = [t for t in B["trips"] if t["i"] == i]
        return dict(i=i, time=B["times"][i], daytype=B["daytype"][i], roads=roads, alerts=alerts, summary=summary, trips=trips)

    # ------------------------------------------------------------------ routing
    def speed_forecast(self, i):
        B = self.B

        def f(r, m):
            pts = []
            v0 = B["now"][r][i]
            if v0 is not None:
                pts.append((0.0, v0))
            for h in H:
                v = B["forecast"][str(h)][r][i]
                if v is not None:
                    pts.append((float(h), v))
            return interp(m, pts)
        return f

    def speed_live(self, i, notes):
        def f(r, m):
            v, age = self.last_known(r, i)
            if v is None:
                notes.add(f"{self.road[r]['label']} ({self.road[r]['road']}): no recent reading, 80% of normal speed assumed")
                return self.road[r]["ref"] * 0.8
            return v
        return f

    def speed_actual(self, i):
        """Recorded speed at minute m after departure, interpolated between readings up to 60 min apart."""
        now = self.B["now"]

        def f(r, m):
            x = i + m / 15.0
            k0 = int(math.floor(x))
            before = after = None
            for k in range(k0, max(-1, k0 - 5), -1):
                if 0 <= k < self.n and now[r][k] is not None:
                    before = (k, now[r][k])
                    break
            for k in range(k0 + 1, min(self.n, k0 + 6)):
                if now[r][k] is not None:
                    after = (k, now[r][k])
                    break
            if before and after:
                return before[1] + (after[1] - before[1]) * (x - before[0]) / (after[0] - before[0])
            if before and x - before[0] <= 4:
                return before[1]
            if after and after[0] - x <= 4:
                return after[1]
            return None
        return f

    def dijkstra(self, src, dst, speed):
        best, prev, pq = {src: 0.0}, {}, [(0.0, src)]
        while pq:
            t, r = heapq.heappop(pq)
            if t > best.get(r, 1e18):
                continue
            if r == dst:
                break
            v = speed(r, t)
            if v is None or v < 1.0:
                continue
            for nxt, extra, _ in self.E[r]:
                arrive = t + self.road[r]["km"] / v * 60.0 + extra
                if arrive < best.get(nxt, 1e18):
                    best[nxt], prev[nxt] = arrive, r
                    heapq.heappush(pq, (arrive, nxt))
        if dst not in best:
            return None
        path, r = [dst], dst
        while r != src:
            r = prev[r]
            path.append(r)
        return path[::-1]

    def drive(self, path, speed):
        """Minutes to drive a path with the given speed function (same rules as the planner)."""
        t = 0.0
        for k, r in enumerate(path):
            v = speed(r, t)
            if v is None or v < 1.0:
                return None
            last = k == len(path) - 1
            km = self.road[r]["km"] * (self.frac.get(r, 1.0) if last else 1.0)
            t += km / v * 60.0
            if not last:
                t += next((extra for nxt, extra, _ in self.E[r] if nxt == path[k + 1]), 0.0)
        return round(t, 1)

    def route(self, src, dst, i):
        if src not in self.road or dst not in self.road:
            return dict(error="unknown road stretch")
        if src == dst:
            return dict(error="start and destination are the same stretch")
        notes = set()
        fc, live, act = self.speed_forecast(i), self.speed_live(i, notes), self.speed_actual(i)
        out = dict(src=src, dst=dst, i=i, time=self.B["times"][i])
        for name, spd in (("forecast", fc), ("live", live)):
            path = self.dijkstra(src, dst, spd)
            if path is None:
                return dict(error="no route between these stretches in the road graph", **out)
            km = sum(self.road[r]["km"] for r in path[:-1]) + self.road[path[-1]]["km"] * self.frac.get(path[-1], 1.0)
            out[name] = dict(path=[dict(id=r, label=self.road[r]["label"], road=self.road[r]["road"]) for r in path],
                             km=round(km, 1), minutes=self.drive(path, spd), actual_minutes=self.drive(path, act),
                             assumed_link=any(x["src"] == a and x["dst"] == b for a, b in zip(path, path[1:]) for x in self.B["assumed"]))
        out["same_path"] = [p["id"] for p in out["forecast"]["path"]] == [p["id"] for p in out["live"]["path"]]
        out["notes"] = sorted(notes)
        return out


def interp(m, pts):
    if not pts:
        return None
    if m <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if m <= x1:
            return y0 + (y1 - y0) * (m - x0) / (x1 - x0)
    return pts[-1][1]


def make_handler(model):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def json(self, obj, code=200):
            self.send(code, json.dumps(obj, separators=(",", ":")).encode(), "application/json")

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if u.path == "/api/meta":
                    return self.json(model.meta())
                if u.path == "/api/results":
                    return self.json(model.results)
                if u.path in ("/api/state", "/api/route"):
                    i = int(q.get("i", 0))
                    if not 0 <= i < model.n:
                        return self.json(dict(error=f"i must be between 0 and {model.n - 1}"), 400)
                    if u.path == "/api/state":
                        return self.json(model.state(i))
                    r = model.route(q.get("src", ""), q.get("dst", ""), i)
                    return self.json(r, 400 if "error" in r else 200)
                name = "index.html" if u.path in ("/", "/index.html") else u.path.lstrip("/")
                path = os.path.normpath(os.path.join(STATIC, name.replace("static/", "", 1)))
                if not path.startswith(STATIC) or not os.path.isfile(path):
                    return self.send(404, b"not found", "text/plain")
                with open(path, "rb") as f:
                    self.send(200, f.read(), TYPES.get(os.path.splitext(path)[1], "application/octet-stream"))
            except (ValueError, KeyError) as e:
                self.json(dict(error=str(e)), 400)
    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bundle", default=os.path.join(HERE, "data", "bundle.json"))
    ap.add_argument("--results", default=os.path.join(HERE, "results.json"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    if not os.path.isfile(a.bundle):
        raise SystemExit(f"No data bundle at {a.bundle}. Build one first: python app/build_bundle.py --help")
    model = Model(a.bundle, a.results)
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(model))
    url = f"http://{a.host}:{a.port}/"
    w = model.B["meta"]["window"]
    kind = "forecasts up to the latest reading" if model.B["meta"].get("mode") == "latest" else "replay"
    print(f"Traffic app: {len(model.ids)} road stretches, {kind}, {w[0]} to {w[1]} ({model.n} slots).")
    print(f"Open {url}  (Ctrl+C to stop). Works without internet.")
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
