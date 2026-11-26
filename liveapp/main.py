#!/usr/bin/env python3
"""Bengaluru ORR traffic intelligence: the local live app (FastAPI backend + browser front end).

  python liveapp/main.py                      # live data from the project's collector (GitHub), port 8000
  python liveapp/main.py --source tomtom      # live data straight from TomTom (needs TOMTOM_API_KEY)
  python liveapp/main.py --source off         # no internet: serve the local cache only

Open http://127.0.0.1:8000/ (the browser opens by itself). API documentation: http://127.0.0.1:8000/docs
First time: python liveapp/sync.py, then python liveapp/train.py (see liveapp/README.md).
"""
import argparse
import asyncio
import datetime
import json
import os
import sys
import threading
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException, Query, Request
    from fastapi.openapi.docs import get_swagger_ui_html
    from fastapi.responses import FileResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:
    sys.exit("Install the app packages first:  python -m pip install fastapi uvicorn")

import engine as eng  # noqa: E402
import livefeed  # noqa: E402

STATIC = os.path.join(HERE, "static")
RESULTS = os.path.join(os.path.dirname(HERE), "app", "results.json")
STARTED = time.time()

app = FastAPI(title="Bengaluru ORR Traffic Intelligence API",
              description="Forecasts from the trained Graph Convolutional Networks, live readings, congestion alerts, "
                          "road connections and time-dependent routing for 21 connected road stretches.",
              version="1.0", docs_url=None, redoc_url=None)
E = None          # the engine, set in main()
FEED = None       # the live feed thread, or None


@app.middleware("http")
async def timing(request: Request, call_next):
    t0 = time.perf_counter()
    resp = await call_next(request)
    resp.headers["X-Process-Ms"] = f"{(time.perf_counter() - t0) * 1000:.1f}"
    return resp


@app.get("/docs", include_in_schema=False)
def docs():
    """Interactive API documentation, served from local files (works without internet)."""
    return get_swagger_ui_html(openapi_url=app.openapi_url, title="ORR Traffic API",
                               swagger_js_url="/static/vendor/swagger/swagger-ui-bundle.js",
                               swagger_css_url="/static/vendor/swagger/swagger-ui.css",
                               swagger_favicon_url="/static/vendor/swagger/favicon-32x32.png")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/status", summary="Data, model and live-feed status")
def status():
    s = E.status()
    s["feed"] = FEED.state if FEED else dict(source="off")
    s["uptime_s"] = round(time.time() - STARTED)
    s["now_ist"] = datetime.datetime.now(livefeed.IST).strftime("%Y-%m-%d %H:%M:%S")
    return s


@app.get("/api/network", summary="Road stretches with their shape, normal speed and connections")
def network():
    return E.network()


@app.get("/api/days", summary="Days available in the data")
def days():
    return E.days()


@app.get("/api/timeline", summary="Corridor speed for every 15-minute slot of one day")
def timeline(date: str = Query(..., description="YYYY-MM-DD")):
    return E.timeline(date)


@app.get("/api/snapshot", summary="Speeds now, model forecasts (+15/+30/+60 min) and alerts at one moment")
def snapshot(t: str = Query("latest", description="'latest' or a time like 2026-11-24T18:07")):
    return E.snapshot(E.slot(t))


@app.get("/api/series", summary="Recorded speed (past hours) and forecast (next hour), corridor or one stretch")
def series(t: str = "latest", road: str = None, hours: float = 6):
    if road and road not in E.ids:
        raise HTTPException(400, "unknown road stretch")
    return E.series(E.slot(t), road, hours)


@app.get("/api/unseen", summary="One road treated as unseen: forecasts from networks that never saw it (new sensor / no sensor)")
def unseen(road: str, t: str = "latest"):
    if road not in E.ids:
        raise HTTPException(400, "unknown road stretch")
    r = E.unseen(E.slot(t), road)
    if "error" in r:
        raise HTTPException(409, r["error"])
    return r


@app.get("/api/route", summary="Fastest route on the forecast (time-dependent Dijkstra) against the live-map choice")
def route(src: str, dst: str, t: str = "latest"):
    r = E.route(src, dst, E.slot(t))
    if "error" in r:
        raise HTTPException(400, r["error"])
    return r


@app.get("/api/results", summary="Aggregate results of all 11 model versions (project result files)")
def results():
    return json.load(open(RESULTS, encoding="utf-8"))


@app.post("/api/live/refresh", summary="Ask the live feed to fetch new readings now")
def refresh():
    if not FEED:
        raise HTTPException(409, "live feed is off (started with --source off)")
    FEED.refresh_now()
    return dict(ok=True, source=FEED.source)


@app.get("/api/stream", summary="Server-sent events: 'update' whenever new readings arrive")
async def stream(request: Request):
    async def gen():
        seen, beat = E.version, time.time()
        yield f"event: hello\ndata: {json.dumps(dict(version=seen))}\n\n"
        while True:
            if await request.is_disconnected():
                break
            if E.version != seen:
                seen = E.version
                yield f"event: update\ndata: {json.dumps(dict(version=seen, latest=E.latest_time.strftime('%Y-%m-%dT%H:%M')))}\n\n"
            if time.time() - beat > 15:
                beat = time.time()
                yield ": keep-alive\n\n"
            await asyncio.sleep(1.0)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")


def main():
    global E, FEED
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=("github", "tomtom", "off"), default="github")
    ap.add_argument("--interval", type=int, default=None, help="seconds between live refreshes (default 180 github, 900 tomtom)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(os.path.join(eng.MODEL_DIR, "model_meta.json")):
        sys.exit("No trained models yet. Run:  python liveapp/sync.py   then   python liveapp/train.py")
    if not os.path.isdir(os.path.join(eng.DATA_DIR, "tomtom_flow")):
        sys.exit("No data yet. Run:  python liveapp/sync.py")
    key = os.environ.get("TOMTOM_API_KEY")
    if a.source == "tomtom" and not key:
        sys.exit("--source tomtom needs TOMTOM_API_KEY in the environment.")
    if a.source == "github":
        try:
            files, _ = livefeed.sync_github()
            print(f"live data: {len(files)} file(s) updated from the collector")
        except Exception as e:
            print(f"live data: could not reach GitHub ({type(e).__name__}); starting from the local cache")

    print("loading data and the trained models ...", flush=True)
    E = eng.Engine()
    st = E.status()
    print(f"  {st['readings']:,} readings, latest {st['latest_reading']}; {st['model']['networks']} networks loaded")
    if a.source != "off":
        FEED = livefeed.LiveFeed(a.source, E.reload, a.interval, key)
        FEED.start()
    url = f"http://{a.host}:{a.port}/"
    print(f"open {url}   (API docs: {url}docs)   stop with Ctrl+C", flush=True)
    if not a.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
