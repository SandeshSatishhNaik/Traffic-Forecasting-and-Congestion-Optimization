"""Traffic engine for the live app: data, trained graph models, forecasts, alerts, connections and routes.

Everything the API returns is computed here, at request time:
  - the readings come from the local data cache (kept up to date by livefeed.py),
  - the forecasts come from the saved Graph Convolutional Networks (train.py), run on the inputs of the
    requested moment, using only readings up to that moment,
  - routes come from a time-dependent Dijkstra over the road graph, with the forecast speeds.
"""
import heapq
import json
import math
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "modeling"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import torch  # noqa: E402

import baselines  # noqa: E402
import prepare  # noqa: E402
import stgnn  # noqa: E402
from demo_dashboard import LABEL  # noqa: E402
from routing import ASSUMED_LINKS, FRAC, TRIPS, TURN_PENALTY_MIN  # noqa: E402

H = (15, 30, 60)
THR = dict(slow=0.75, severe=0.60)
ROUTE_NAME = {"orr_ccw": "ORR eastbound", "orr_cw": "ORR westbound", "hosur": "Hosur Road",
              "old_airport": "Old Airport Road", "varthur": "Varthur Road"}
DATA_DIR = os.path.join(HERE, "data", "cache")
MODEL_DIR = os.path.join(HERE, "models")
GEOMETRY_JSON = os.path.join(HERE, "data", "geometry.json")
torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))


def r1(x):
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) else round(x, 1)


def level(ratio):
    if ratio is None:
        return "none"
    return "severe" if ratio < THR["severe"] else "slow" if ratio < THR["slow"] else "free"


def load_nets(model_dir, ids):
    """The saved networks: {horizon: [net per seed]} and the training metadata."""
    meta = json.load(open(os.path.join(model_dir, "model_meta.json"), encoding="utf-8"))
    if meta["ids"] != ids:
        raise SystemExit("The saved models were trained for a different list of road stretches. Run liveapp/train.py again.")
    stgnn.configure(**meta["hp"])
    A = prepare.adjacency(ids, kind=("flow", "crossing"))
    nets = {}
    for h in H:
        nets[h] = []
        for s in meta["seeds"]:
            net = stgnn.Net(A, "graph", meta["c_in"], hid=meta["hp"]["hid"], emb=meta["hp"]["emb"], drop=meta["hp"]["drop"])
            net.load_state_dict(torch.load(os.path.join(model_dir, f"gcn_h{h}_s{s}.pt"), map_location="cpu"))
            net.eval()
            nets[h].append(net)
    return nets, meta


class Engine:
    def __init__(self, data_dir=DATA_DIR, model_dir=MODEL_DIR):
        self.data_dir, self.model_dir = data_dir, model_dir
        self.lock = threading.RLock()
        seg = pd.read_csv(prepare.SEGMENTS_CSV)
        self.ids = seg["segment_id"].tolist()
        self.seg = seg.set_index("segment_id")
        self.links = pd.read_csv(prepare.LINKS_CSV)
        self.nets, self.meta = load_nets(model_dir, self.ids)
        self.ref = pd.Series(self.meta["ref"])[self.ids].astype(float)
        self.version = 0
        self.loaded_at = None
        self.reload()
        self._build_graph()

    # ------------------------------------------------------------------ data
    def reload(self):
        """Read the data cache again and rebuild the inputs. Called at start and after every live update."""
        t0 = time.time()
        df, ids = prepare.load_flow(self.data_dir)
        weather = baselines.load_weather(self.data_dir)
        weather = weather[~weather.index.duplicated(keep="last")]
        grid = prepare.speed_grid(df, ids)
        X, tX = stgnn.make_inputs(grid, self.ref, weather)
        coords = (df.sort_values("t").dropna(subset=["seg_start_lat", "seg_end_lat"])
                  .groupby("segment_id")[["seg_start_lat", "seg_start_lon", "seg_end_lat", "seg_end_lon"]].last())
        with self.lock:
            old_latest = getattr(self, "latest_time", None)
            self.df_rows = len(df)
            self.grid = grid
            self.weather = weather
            self.X, self.tX = X, tX
            self.pos = {t: k for k, t in enumerate(tX)}
            self.times = list(tX)
            self.tindex = {t: i for i, t in enumerate(self.times)}
            self.coords = coords
            self.cache = {}
            self.G = grid.values  # (T, N) km/h with NaN
            self.gpos = {t: k for k, t in enumerate(grid.index)}
            has = ~np.isnan(self.G).all(1)
            self.latest_time = grid.index[np.where(has)[0][-1]]
            self.latest_reading = df["t"].max()
            self.loaded_at = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None)
            self.load_seconds = round(time.time() - t0, 2)
            changed = old_latest is None or self.latest_time != old_latest
            self.version += 1
        return changed

    def slot(self, t=None):
        """Index into self.times for a time string / Timestamp, or the latest slot."""
        if t in (None, "", "latest"):
            return self.tindex[self.latest_time]
        ts = pd.Timestamp(t)
        k = np.searchsorted(np.array(self.times, dtype="datetime64[ns]"), np.datetime64(ts), side="right") - 1
        return int(min(max(k, 0), len(self.times) - 1))

    def value(self, r, t):
        k = self.gpos.get(t)
        if k is None:
            return None
        v = self.G[k, self.ids.index(r)]
        return None if np.isnan(v) else float(v)

    def last_known(self, j, t, back=8):
        """Most recent reading of road j at or before slot time t (up to `back` slots old): (km/h, age in min)."""
        k = self.gpos.get(t)
        if k is None:
            return None, None
        for b in range(0, back + 1):
            if k - b < 0:
                break
            v = self.G[k - b, j]
            if not np.isnan(v):
                return float(v), b * prepare.SLOT_MIN
        return None, None

    # ------------------------------------------------------------------ the models
    def forecast(self, i):
        """Run the saved networks on the inputs of slot i. {h: (mean km/h, min, max)} per road, and the time it took."""
        with self.lock:
            if i in self.cache:
                return self.cache[i]
            t = self.times[i]
            x = torch.tensor(self.X[self.pos[t]][None])
        t0 = time.perf_counter()
        out = {}
        with torch.no_grad():
            for h in H:
                P = np.stack([net(x)[0].numpy() for net in self.nets[h]]) * self.ref.values  # (seeds, N)
                out[h] = (P.mean(0), P.min(0), P.max(0))
        ms = round((time.perf_counter() - t0) * 1000, 1)
        res = (out, ms)
        with self.lock:
            if len(self.cache) > 4000:
                self.cache.clear()
            self.cache[i] = res
        return res

    # ------------------------------------------------------------------ unseen roads (train_unseen.py)
    def unseen(self, i, road):
        """Forecasts for `road` from networks that never saw it in training (liveapp/models/unseen/).
        new sensor: its own latest readings are inputs (normal speed from one week of nights);
        no sensor:  its inputs are blank, the estimate comes only from connected roads (virtual sensor).
        All values are ratios of the road's normal speed, next to the normal model and what happened."""
        d = os.path.join(self.model_dir, "unseen")
        ev_path = os.path.join(d, f"eval_{road}.json")
        if not os.path.exists(ev_path):
            return dict(error="no unseen-road models for this road yet: run python liveapp/train_unseen.py")
        key = ("unseen", i, road)
        with self.lock:
            if key in self.cache:
                return self.cache[key]
        ev = json.load(open(ev_path, encoding="utf-8"))
        if not hasattr(self, "unseen_nets"):
            self.unseen_nets = {}
        if road not in self.unseen_nets:
            A = prepare.adjacency(self.ids, kind=("flow", "crossing"))
            hp, nets = self.meta["hp"], {}
            for h in H:
                nets[h] = []
                for f in sorted(os.listdir(d)):
                    if f.startswith(f"unseen_{road}_h{h}_s") and f.endswith(".pt"):
                        net = stgnn.Net(A, "graph", self.meta["c_in"], hid=hp["hid"], emb=hp["emb"], drop=hp["drop"])
                        net.load_state_dict(torch.load(os.path.join(d, f), map_location="cpu"))
                        nets[h].append(net.eval())
            self.unseen_nets[road] = nets
        nets, j, L = self.unseen_nets[road], self.ids.index(road), stgnn.LAGS
        ref_full, ref_week = float(self.ref[road]), float(ev["ref_week"])
        nb = [self.ids.index(r) for r in ev["neighbours"]]

        def inputs(k, mode):
            x = self.X[self.pos[self.times[k]]].copy()
            if mode == "none":
                x[j, :L], x[j, L:2 * L] = 1.0, 0.0
            else:
                x[j, :L] = np.where(x[j, L:2 * L] > 0, x[j, :L] * ref_full / ref_week, 1.0)
            return torch.tensor(x[None])

        def run(k, h, mode):
            with torch.no_grad():
                out = np.mean([net(inputs(k, mode))[0].numpy() for net in nets[h]], 0)
            v = out[j] * (ref_week / ref_full if mode == "new" else 1.0)
            return round(float(v), 3), (round(float(out[nb].mean()), 3) if nb else None)

        t = self.times[i]
        fc, _ = self.forecast(i)
        rows = []
        for h in H:
            ta = t + pd.Timedelta(minutes=h)
            a = self.value(road, ta) if ta <= self.latest_time else None
            none, nbr = run(i, h, "none")
            rows.append(dict(h=h, t=ta.strftime("%Y-%m-%dT%H:%M"), virtual=none, nbr_forecast=nbr, new=run(i, h, "new")[0],
                             normal=round(float(fc[h][0][j]) / ref_full, 3), actual=None if a is None else round(a / ref_full, 3)))
        now, age = self.last_known(j, t)
        nowcast = run(i - 1, 15, "none")[0] if i > 0 else None      # virtual sensor's estimate of "now" (made 15 min ago)
        res = dict(road=road, label=self.label(road), dir=self.road_name(road), time=t.strftime("%Y-%m-%dT%H:%M"),
                   neighbours=[self.label(r) for r in ev["neighbours"]], now_actual=None if now is None else round(now / ref_full, 3),
                   nowcast=nowcast, rows=rows, measured=ev["h"], test_week=self.meta.get("test_range"))
        with self.lock:
            self.cache[key] = res
        return res

    # ------------------------------------------------------------------ one moment
    def snapshot(self, i):
        t = self.times[i]
        fc, ms = self.forecast(i)
        roads, alerts = {}, []
        for j, r in enumerate(self.ids):
            ref = float(self.ref[r])
            now, age = self.last_known(j, t)
            d = dict(ref=r1(ref), now=r1(now), age=age, now_ratio=None if now is None else round(now / ref, 3))
            d["now_level"] = level(d["now_ratio"])
            for h in H:
                m, lo, hi = fc[h][0][j], fc[h][1][j], fc[h][2][j]
                ta = t + pd.Timedelta(minutes=h)
                a = self.value(r, ta) if ta <= self.latest_time else None
                d[f"f{h}"], d[f"lo{h}"], d[f"hi{h}"] = r1(m), r1(lo), r1(hi)
                d[f"r{h}"] = round(float(m) / ref, 3)
                d[f"l{h}"] = level(d[f"r{h}"])
                d[f"a{h}"] = r1(a)
                if d[f"l{h}"] in ("slow", "severe"):
                    known = ta <= self.latest_time
                    alerts.append(dict(road=r, label=self.label(r), dir=self.road_name(r), h=h, level=d[f"l{h}"],
                                       forecast=r1(m), now=d["now"], early=d["now_level"] not in ("slow", "severe"),
                                       actual=r1(a), confirmed=(None if a is None else level(a / ref) in ("slow", "severe")) if known else None))
            roads[r] = d
        core = [r for r in self.ids if self.seg.loc[r, "tier"] == "core"]

        def avg(key):
            v = [roads[r][key] for r in core if roads[r][key] is not None]
            return round(float(np.mean(v)), 3) if v else None
        summary = dict(now=avg("now_ratio"), **{f"r{h}": avg(f"r{h}") for h in H})
        alerts.sort(key=lambda a: (a["h"], a["level"] != "severe", a["label"]))
        return dict(i=i, time=t.strftime("%Y-%m-%dT%H:%M"), latest=t == self.latest_time,
                    daytype=str(prepare.day_type(pd.DatetimeIndex([t]))[0]), roads=roads, alerts=alerts,
                    summary=summary, model_ms=ms, model_runs=len(H) * len(self.meta["seeds"]))

    def series(self, i, road=None, hours=6):
        """Recorded speed ratio for the past `hours` and the forecast for the next hour (corridor or one road)."""
        t = self.times[i]
        js = [self.ids.index(road)] if road else [j for j, r in enumerate(self.ids) if self.seg.loc[r, "tier"] == "core"]
        refs = self.ref.values[js]
        past = []
        start = t - pd.Timedelta(hours=hours)
        for k, ts in enumerate(self.grid.index):
            if ts < start or ts > t:
                continue
            row = self.G[k, js] / refs
            if np.isnan(row).all():
                continue
            past.append([ts.strftime("%Y-%m-%dT%H:%M"), round(float(np.nanmean(row)), 3)])
        fc, _ = self.forecast(i)
        fut = []
        for h in H:
            m, lo, hi = (float(np.mean(fc[h][q][js] / refs)) for q in range(3))
            ta = t + pd.Timedelta(minutes=h)
            k = self.gpos.get(ta)
            act = None
            if k is not None and ta <= self.latest_time:
                row = self.G[k, js] / refs
                act = None if np.isnan(row).all() else round(float(np.nanmean(row)), 3)
            fut.append(dict(t=ta.strftime("%Y-%m-%dT%H:%M"), h=h, mean=round(m, 3), lo=round(lo, 3), hi=round(hi, 3), actual=act))
        return dict(road=road, time=t.strftime("%Y-%m-%dT%H:%M"), past=past, forecast=fut)

    def timeline(self, date):
        """Every slot of a day: corridor speed ratio from the recorded readings (for the time-lapse strip)."""
        d0 = pd.Timestamp(date)
        js = [j for j, r in enumerate(self.ids) if self.seg.loc[r, "tier"] == "core"]
        refs = self.ref.values[js]
        out = []
        for i, t in enumerate(self.times):
            if t.normalize() != d0:
                continue
            k = self.gpos[t]
            row = self.G[k, js] / refs
            out.append(dict(i=i, time=t.strftime("%H:%M"), ratio=None if np.isnan(row).all() else round(float(np.nanmean(row)), 3)))
        return out

    def days(self):
        out = []
        for d in pd.DatetimeIndex(sorted({t.normalize() for t in self.times})):
            out.append(dict(date=d.strftime("%Y-%m-%d"), label=d.strftime("%a %d %b"),
                            daytype=str(prepare.day_type(pd.DatetimeIndex([d]))[0])))
        return out

    # ------------------------------------------------------------------ road network
    def label(self, r):
        return LABEL.get(r, r)

    def road_name(self, r):
        return ROUTE_NAME.get(self.seg.loc[r, "route"], self.seg.loc[r, "route"])

    def geometry(self):
        """Polyline per stretch, in travel direction. Exact TomTom shapes if geometry.json exists, else start - request point - end."""
        exact = {}
        if os.path.exists(GEOMETRY_JSON):
            exact = json.load(open(GEOMETRY_JSON, encoding="utf-8"))
        out, src = {}, {}
        for r in self.ids:
            if r in exact and len(exact[r]) >= 2:
                out[r], src[r] = exact[r], "tomtom"
                continue
            s = self.seg.loc[r]
            pts = []
            if r in self.coords.index:
                c = self.coords.loc[r]
                pts = [[c["seg_start_lat"], c["seg_start_lon"]], [float(s["lat"]), float(s["lon"])], [c["seg_end_lat"], c["seg_end_lon"]]]
            else:
                pts = [[float(s["lat"]), float(s["lon"])]] * 2
            out[r], src[r] = [[round(a, 6), round(b, 6)] for a, b in pts], "approx"
        return out, src

    def network(self):
        geo, src = self.geometry()
        roads = []
        for r in self.ids:
            s = self.seg.loc[r]
            roads.append(dict(id=r, label=self.label(r), road=self.road_name(r), route=s["route"], tier=s["tier"],
                              seq=int(s["seq"]), km=float(s["length_km"]), frc=s["frc"], ref=r1(self.ref[r]),
                              geometry=geo[r], geometry_source=src[r],
                              downstream=[x for x in self.E[r] if not x[2]], upstream=[a for a in self.ids if any(n == r for n, _, _ in self.E[a])]))
        for x in roads:
            x["downstream"] = [dict(id=n, turn=bool(extra)) for n, extra, _ in x["downstream"]]
        links = [dict(src=x["from_id"], dst=x["to_id"], kind=x["kind"], lat=float(x["lat"]), lon=float(x["lon"]))
                 for _, x in self.links.iterrows()]
        exact = sum(1 for v in src.values() if v == "tomtom")
        return dict(roads=roads, links=links, assumed=[dict(src=a, dst=b, km=km, kmph=v) for a, b, km, v in ASSUMED_LINKS],
                    trip_presets=TRIPS, geometry=dict(exact=exact, total=len(self.ids)))

    # ------------------------------------------------------------------ routing (same rules as modeling/routing.py)
    def _build_graph(self):
        self.E = {r: [] for r in self.ids}
        for _, x in self.links.iterrows():
            if x["kind"] == "flow":
                self.E[x["from_id"]].append((x["to_id"], 0.0, False))
            else:
                self.E[x["from_id"]].append((x["to_id"], TURN_PENALTY_MIN, False))
                self.E[x["to_id"]].append((x["from_id"], TURN_PENALTY_MIN, False))
        for a, b, km, v in ASSUMED_LINKS:
            self.E[a].append((b, km / v * 60.0, True))

    def _speed_forecast(self, i):
        fc, _ = self.forecast(i)
        t = self.times[i]

        def f(r, m):
            j = self.ids.index(r)
            pts = []
            v0, _ = self.last_known(j, t)
            if v0 is not None:
                pts.append((0.0, v0))
            pts += [(float(h), float(fc[h][0][j])) for h in H]
            return interp(m, pts)
        return f

    def _speed_live(self, i, notes):
        t = self.times[i]

        def f(r, m):
            v, _ = self.last_known(self.ids.index(r), t)
            if v is None:
                notes.add(f"{self.label(r)} ({self.road_name(r)}): no recent reading, 80% of normal speed assumed")
                return float(self.ref[r]) * 0.8
            return v
        return f

    def _speed_actual(self, i):
        t0 = self.times[i]
        if t0 + pd.Timedelta(minutes=60) > self.latest_time:
            return None

        def f(r, m):
            j = self.ids.index(r)
            x = m / 15.0
            pts = []
            for k in range(-4, 9):
                ts = t0 + pd.Timedelta(minutes=15 * k)
                g = self.gpos.get(ts)
                if g is not None and not np.isnan(self.G[g, j]):
                    pts.append((k, float(self.G[g, j])))
            before = [p for p in pts if p[0] <= x]
            after = [p for p in pts if p[0] > x]
            if before and after:
                (k0, v0), (k1, v1) = before[-1], after[0]
                return v0 + (v1 - v0) * (x - k0) / (k1 - k0)
            if before and x - before[-1][0] <= 4:
                return before[-1][1]
            if after and after[0][0] - x <= 4:
                return after[0][1]
            return None
        return f

    def _dijkstra(self, src, dst, speed):
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
                arrive = t + self.seg.loc[r, "length_km"] / v * 60.0 + extra
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

    def _drive(self, path, speed):
        t = 0.0
        for k, r in enumerate(path):
            v = speed(r, t)
            if v is None or v < 1.0:
                return None
            last = k == len(path) - 1
            km = float(self.seg.loc[r, "length_km"]) * (FRAC.get(r, 1.0) if last else 1.0)
            t += km / v * 60.0
            if not last:
                t += next((extra for nxt, extra, _ in self.E[r] if nxt == path[k + 1]), 0.0)
        return round(t, 1)

    def route(self, src, dst, i):
        if src not in self.ids or dst not in self.ids:
            return dict(error="unknown road stretch")
        if src == dst:
            return dict(error="start and destination are the same stretch")
        notes = set()
        fc, live, act = self._speed_forecast(i), self._speed_live(i, notes), self._speed_actual(i)
        out = dict(src=src, dst=dst, i=i, time=self.times[i].strftime("%Y-%m-%dT%H:%M"))
        for name, spd in (("forecast", fc), ("live", live)):
            path = self._dijkstra(src, dst, spd)
            if path is None:
                return dict(error="no route between these stretches in the road graph", **out)
            km = sum(float(self.seg.loc[r, "length_km"]) for r in path[:-1]) + float(self.seg.loc[path[-1], "length_km"]) * FRAC.get(path[-1], 1.0)
            out[name] = dict(path=[dict(id=r, label=self.label(r), road=self.road_name(r)) for r in path], km=round(km, 1),
                             minutes=self._drive(path, spd), actual_minutes=self._drive(path, act) if act else None,
                             assumed_link=any((a, b) in {(x[0], x[1]) for x in ASSUMED_LINKS} for a, b in zip(path, path[1:])))
        out["same_path"] = [p["id"] for p in out["forecast"]["path"]] == [p["id"] for p in out["live"]["path"]]
        out["notes"] = sorted(notes)
        return out

    # ------------------------------------------------------------------ status
    def status(self):
        return dict(stretches=len(self.ids), readings=self.df_rows, first=self.times[0].strftime("%Y-%m-%d %H:%M"),
                    latest_slot=self.latest_time.strftime("%Y-%m-%d %H:%M"),
                    latest_reading=self.latest_reading.strftime("%Y-%m-%d %H:%M"),
                    loaded_at=self.loaded_at.strftime("%Y-%m-%d %H:%M:%S"), load_seconds=self.load_seconds, version=self.version,
                    model=dict(name="Graph Convolutional Network with the road graph (tuned)", seeds=len(self.meta["seeds"]),
                               networks=len(self.meta["seeds"]) * len(H), trained_on=self.meta["train_range"],
                               validated_on=self.meta["val_range"], tested_on=self.meta["test_range"],
                               test_metrics=self.meta.get("test_metrics"), trained_at=self.meta.get("trained_at"),
                               hp=self.meta["hp"]))


def interp(m, pts):
    if not pts:
        return None
    if m <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if m <= x1:
            return y0 + (y1 - y0) * (m - x0) / (x1 - x0)
    return pts[-1][1]
