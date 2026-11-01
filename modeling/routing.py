"""Trip time and route recommendation from the speed forecasts.

Cost of a stretch = length / speed at the moment the vehicle enters it (time-dependent). The planner is
Dijkstra on the stretch graph (flow links; turns at crossings; one assumed link, see ASSUMED_LINKS).

Evaluation (evaluate_trips): for every weekday departure in the test week where the readings exist,
compare the trip time an app would show (current speeds held constant), the historical average, and the
forecast-based estimate (graph neural net, predictions for +15/+30/+60 min) with the trip time the
vehicle actually experienced (stepping through the real speeds, interpolated between readings).
"""
import argparse
import heapq

import numpy as np
import pandas as pd

import baselines
import prepare
import stgnn

SEG = pd.read_csv(prepare.SEGMENTS_CSV).set_index("segment_id")
LEN = SEG["length_km"].to_dict()

# trips along one carriageway of the Outer Ring Road
TRIPS = {
    "ORR eastbound, Silk Board to Doddanekundi (7.9 km)": ["orr_ccw_02", "orr_ccw_03", "orr_ccw_04", "orr_iblur", "orr_bellandur", "orr_ccw_07"],
    "ORR westbound, Marathahalli to Silk Board (12.3 km)": ["orr_marathahalli", "orr_cw_03", "orr_cw_04", "orr_cw_05", "orr_cw_06", "orr_cw_07", "orr_hsr", "orr_cw_09"],
}
# Position of the Marathahalli crossing along two stretches, from the stretch end points (straight-line approximation).
FRAC = {"orr_doddanekundi": 0.26, "varthur_kundalahalli": 0.65}
# Link that the readings do not cover: Hosur Road's northern end to Varthur Road's western end (about 2.2 km).
ASSUMED_LINKS = [("hosur_02", "varthur_kundalahalli", 2.2, 25.0)]   # from, to, km, assumed km/h
TURN_PENALTY_MIN = 0.5


def interp_speed(grid, road, t):
    """Speed at time t, linear between the two surrounding slots; NaN if either is missing."""
    s = grid[road]
    t = pd.Timestamp(t).as_unit(s.index.unit)
    i = s.index.searchsorted(t, side="right") - 1
    if i < 0 or i + 1 >= len(s):
        return np.nan
    t0, t1 = s.index[i], s.index[i + 1]
    a, b = s.iloc[i], s.iloc[i + 1]
    if np.isnan(a) or np.isnan(b):
        return np.nan
    return a + (b - a) * ((t - t0) / (t1 - t0))


def walk_route(roads, depart, speed_at, fracs=None):
    """Minutes to drive the stretches in order; speed_at(road, minutes_after_departure) -> km/h."""
    t = 0.0
    for r in roads:
        v = speed_at(r, t)
        if not (v == v) or v < 1.0:
            return np.nan
        km = LEN[r] * (fracs or {}).get(r, 1.0)
        t += km / v * 60.0
    return t


def build_graph(ids):
    """Directed edges between stretches: flow links, turns at crossings (both ways), assumed links."""
    links = pd.read_csv(prepare.LINKS_CSV)
    E = {r: [] for r in ids}
    for _, r in links.iterrows():
        if r["kind"] == "flow":
            E[r["from_id"]].append((r["to_id"], 0.0, False))
        else:
            E[r["from_id"]].append((r["to_id"], TURN_PENALTY_MIN, False))
            E[r["to_id"]].append((r["from_id"], TURN_PENALTY_MIN, False))
    for a, b, km, v in ASSUMED_LINKS:
        E[a].append((b, km / v * 60.0, True))
    return E


def dijkstra(E, start, goal, speed_at, fracs):
    """Time-dependent Dijkstra over stretches. Start/goal are stretches; the goal stretch is driven for its fraction."""
    best = {start: 0.0}
    prev = {}
    pq = [(0.0, start)]
    while pq:
        t, r = heapq.heappop(pq)
        if t > best.get(r, 1e18):
            continue
        if r == goal:
            break
        v = speed_at(r, t)
        if not (v == v) or v < 1.0:
            continue
        done = t + LEN[r] * fracs.get(r, 1.0) / v * 60.0
        if r == goal:
            continue
        for nxt, extra, _ in E[r]:
            arrive = t + LEN[r] / v * 60.0 + extra
            if arrive < best.get(nxt, 1e18):
                best[nxt] = arrive
                prev[nxt] = r
                heapq.heappush(pq, (arrive, nxt))
    if goal not in best:
        return None, np.nan
    path, r = [goal], goal
    while r != start:
        r = prev[r]
        path.append(r)
    path.reverse()
    v = speed_at(goal, best[goal])
    return path, best[goal] + LEN[goal] * fracs.get(goal, 1.0) / v * 60.0


def train_forecasts(grid, ref, weather, val_start, test_start, test_end, seeds=(0, 1, 2, 3, 4)):
    """Graph neural net ensemble for +15/+30/+60 trained before the test week; predictions for every test slot."""
    ids = list(grid.columns)
    A = prepare.adjacency(ids, kind=("flow", "crossing"))
    Xall, tall = stgnn.make_inputs(grid[grid.index >= test_start - pd.Timedelta("1h")], ref, weather)
    keep = (tall >= test_start) & (tall < test_end)
    Xall, tall = Xall[keep], tall[keep]
    F = {}
    for h in (15, 30, 60):
        TR = stgnn.make_tensors(grid[grid.index < val_start], ref, weather, h)
        VA = stgnn.make_tensors(grid[(grid.index >= val_start - pd.Timedelta("1h")) & (grid.index < test_start)], ref, weather, h)
        P = np.mean([stgnn.train_predict(TR, VA, (Xall,), A, "graph", s)[0] for s in seeds], 0) * ref.values
        F[h] = pd.DataFrame(P, index=tall, columns=ids)
    return F


def evaluate_trips(grid, ref, weather, F, hist, test_start, test_end):
    rows = []
    ids = list(grid.columns)
    for name, roads in TRIPS.items():
        for d in grid.index[(grid.index >= test_start) & (grid.index < test_end)]:
            if d.day_of_week >= 5 or prepare.day_type(pd.DatetimeIndex([d]))[0] != "weekday":
                continue
            cur = {r: grid.at[d, r] for r in roads}
            if any(np.isnan(v) for v in cur.values()) or d not in F[15].index:
                continue
            actual = walk_route(roads, d, lambda r, m: interp_speed(grid, r, d + pd.Timedelta(seconds=int(round(m * 60))).as_unit('ns')))
            if np.isnan(actual) or actual > 120:
                continue
            inst = walk_route(roads, d, lambda r, m: cur[r])
            def hist_speed(r, m):
                t = d + pd.Timedelta(seconds=int(round(m * 60))).as_unit('ns')
                return hist.get((r, "weekday", int(t.hour * 60 + t.minute) // 15 * 15), np.nan)
            ha = walk_route(roads, d, hist_speed)
            def fc_speed(r, m):
                pts = [(0, cur[r])] + [(h, F[h].at[d, r]) for h in (15, 30, 60)]
                return float(np.interp(min(m, 60), [p[0] for p in pts], [p[1] for p in pts]))
            fc = walk_route(roads, d, fc_speed)
            rows.append(dict(trip=name, depart=d, actual=actual, current=inst, historical=ha, forecast=fc))
    return pd.DataFrame(rows)


def hist_table(grid, train_end):
    g = grid[grid.index < train_end]
    day = np.where(prepare.day_type(g.index) == "weekday", "weekday", "weekend")
    t = pd.DataFrame({"mod": (g.index.hour * 60 + g.index.minute) // 15 * 15, "day": day}, index=g.index)
    out = {}
    for r in g.columns:
        m = pd.concat([t, g[r].rename("v")], axis=1).dropna().groupby(["day", "mod"])["v"].mean()
        for (dday, mod), v in m.items():
            if dday == "weekday":
                out[(r, "weekday", mod)] = v
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--save", default=None, help="pickle with forecasts for the demo (not for the repository)")
    a = ap.parse_args()
    df, ids = prepare.load_flow(a.data_dir)
    grid = prepare.speed_grid(df, ids)
    weather = baselines.load_weather(a.data_dir)
    last_full = grid.index.max().normalize() - pd.Timedelta("1D")
    test_start = last_full - pd.Timedelta(days=6)
    val_start = test_start - pd.Timedelta(days=7)
    test_end = last_full + pd.Timedelta("1D")
    ref = prepare.free_flow_reference(grid, val_start)
    F = train_forecasts(grid, ref, weather, val_start, test_start, test_end)
    hist = hist_table(grid, test_start)
    T = evaluate_trips(grid, ref, weather, F, hist, test_start, test_end)
    L = ["| Trip | departures | Method | MAE (min) | mean error (min, + = too slow) | mean actual (min) |", "|---|---|---|---|---|---|"]
    for name, g in T.groupby("trip"):
        for m, lab in (("current", "current speeds held constant (what a live map shows)"), ("historical", "historical average"), ("forecast", "graph forecast")):
            ok = g[m].notna()
            e = g.loc[ok, m] - g.loc[ok, "actual"]
            L.append(f"| {name} | {int(ok.sum())} | {lab} | {e.abs().mean():.1f} | {e.mean():+.1f} | {g.loc[ok, 'actual'].mean():.1f} |")
    print("\n".join(L))
    # planner check: ORR versus the only detour in the graph, for every weekday evening/morning departure
    E = build_graph(ids)
    wins, tot, gaps = 0, 0, []
    for d in T[T.trip.str.startswith("ORR eastbound")]["depart"]:
        def spd(r, m, d=d):
            if r in ("hosur_02", "varthur_kundalahalli", "orr_doddanekundi"):
                v = grid.at[d, r] if not np.isnan(grid.at[d, r]) else ref[r] * 0.8
                return float(v)
            return float(np.interp(min(m, 60), [0, 15, 30, 60], [grid.at[d, r], F[15].at[d, r], F[30].at[d, r], F[60].at[d, r]]))
        path, mins = dijkstra(E, "orr_ccw_02", "orr_doddanekundi", spd, FRAC)
        if path is None:
            continue
        tot += 1
        wins += path[1] == "orr_ccw_03"
    print(f"\nPlanner: ORR chosen in {wins} of {tot} weekday departures")
    if a.out:
        open(a.out, "w").write("\n".join(L) + f"\n\nPlanner: ORR chosen in {wins} of {tot} weekday departures (the only detour in the graph is about 2x longer)\n")
    if a.save:
        pd.to_pickle(dict(F=F, grid=grid, ref=ref, T=T), a.save)
