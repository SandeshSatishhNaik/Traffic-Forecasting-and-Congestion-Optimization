import { useCallback, useEffect, useRef, useState } from "react";
import MapView from "./MapView.jsx";
import { Chart, HorizonTiles, Led, Pipeline, Proof, ReplayBar, RoadPanel, SignBoard } from "./parts.jsx";
import { Corridor, Kpis, Matrix, ModelDiagram, Neighbours, Scorecard } from "./more.jsx";
import { api, dayLabel, hhmm } from "./lib.js";

const DEMO_DAY = "2026-11-24";   // a recent weekday with a strong evening rush, checked against the alerts

export default function App() {
  const [net, setNet] = useState(null), [status, setStatus] = useState(null), [results, setResults] = useState(null), [days, setDays] = useState([]);
  const [mode, setMode] = useState("live"), [t, setT] = useState("latest");
  const [snap, setSnap] = useState(null), [series, setSeries] = useState(null);
  const [h, setH] = useState(0), [selected, setSelected] = useState(null), [tab, setTab] = useState("signs");
  const [pulse, setPulse] = useState({ n: 0, from: 0 });
  const [toast, setToast] = useState(null), [error, setError] = useState(null), [clock, setClock] = useState("");
  const [day, setDay] = useState(null), [timeline, setTimeline] = useState([]), [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false), [speed, setSpeed] = useState(2), [unseenMode, setUnseenMode] = useState("off");
  const [checking, setChecking] = useState(false);
  const modeRef = useRef(mode); modeRef.current = mode;

  const say = useCallback((msg) => { setToast({ msg, k: Date.now() }); }, []);
  useEffect(() => { if (!toast) return; const x = setTimeout(() => setToast(null), 3800); return () => clearTimeout(x); }, [toast]);

  // ---- one moment: snapshot (all 15 networks run on the server) + corridor series; fires the pipeline pulse.
  // Only the newest request may update the screen: during a fast replay an older answer can arrive late.
  const seq = useRef(0), lastWhen = useRef("latest");
  const loadMoment = useCallback(async (when, from) => {
    const my = ++seq.current; lastWhen.current = when;
    try {
      const [s, c] = await Promise.all([api(`/api/snapshot?t=${encodeURIComponent(when)}`), api(`/api/series?t=${encodeURIComponent(when)}&hours=6`)]);
      if (my !== seq.current) return;
      setSnap(s); setSeries(c); setError(null);
      setPulse((p) => ({ n: p.n + 1, from }));
    } catch (e) { if (my === seq.current) setError(`The backend did not answer (${e.message}). Showing the last screen that loaded; retrying.`); }
  }, []);
  const refreshStatus = useCallback(() => api("/api/status").then((s) => { setStatus(s); setLinkOk(true); }).catch(() => setLinkOk(false)), []);
  const [linkOk, setLinkOk] = useState(true), [sse, setSse] = useState("connecting"), [help, setHelp] = useState(false);

  // retry quietly while the backend is unreachable (e.g. restarted during the demo)
  useEffect(() => {
    if (!error) return;
    const x = setInterval(() => { refreshStatus(); loadMoment(lastWhen.current, 0); }, 8000);
    return () => clearInterval(x);
  }, [error, loadMoment, refreshStatus]);

  // ---- start-up (each request retries until the backend answers)
  useEffect(() => {
    const load = (path, set, tries = 0) => api(path).then(set).catch((e) => {
      if (path === "/api/network" && tries === 1) setError(`Could not load the road network (${e.message}); retrying.`);
      setTimeout(() => load(path, set, tries + 1), Math.min(15000, 2000 * 2 ** tries));
    });
    load("/api/network", (n) => { setNet(n); setError(null); });
    load("/api/results", setResults);
    load("/api/days", setDays);
    refreshStatus();
    const c = setInterval(() => setClock(new Date().toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata" })), 1000);
    const st = setInterval(refreshStatus, 60000);
    return () => { clearInterval(c); clearInterval(st); };
  }, [refreshStatus]);

  useEffect(() => { loadMoment(t, modeRef.current === "live" ? 0 : 2); }, [t, loadMoment]);

  // ---- live push: the server tells us when new TomTom readings land
  useEffect(() => {
    const es = new EventSource("/api/stream");   // the browser reconnects by itself; we only show the state
    let dropped = false;
    es.onopen = () => {
      setSse("ok");
      if (dropped) { dropped = false; refreshStatus(); loadMoment(lastWhen.current, 0); say("Backend is back. Screen updated."); }
    };
    es.onerror = () => { dropped = true; setSse(es.readyState === EventSource.CLOSED ? "closed" : "retrying"); refreshStatus(); };
    es.addEventListener("update", (e) => {
      refreshStatus();
      if (modeRef.current !== "live") return;
      const latest = JSON.parse(e.data).latest;
      say(`New TomTom readings arrived (${hhmm(latest)}). Forecasts recomputed.`);
      loadMoment("latest", 0);
    });
    return () => es.close();
  }, [loadMoment, refreshStatus, say]);

  // ---- replay
  useEffect(() => {
    if (mode !== "replay" || !days.length) return;
    if (!day) { setDay((days.find((d) => d.date === DEMO_DAY) || days[days.length - 2] || days[0]).date); return; }
    api(`/api/timeline?date=${day}`).then((tl) => {
      const x = tl.filter((s) => s.ratio != null);
      setTimeline(x);
      const start = Math.max(0, x.findIndex((s) => s.time >= "17:00"));
      setIdx(start);
    }).catch((e) => setError(e.message));
  }, [mode, day, days]);
  // the slot index drives the replay time
  useEffect(() => { if (mode === "replay" && timeline[idx]) setT(`${day}T${timeline[idx].time}`); }, [mode, idx, timeline, day]);
  const seek = useCallback((i) => setIdx(i), []);
  useEffect(() => {
    if (!playing) return;
    if (idx >= timeline.length - 1) { setPlaying(false); return; }
    const x = setTimeout(() => setIdx(idx + 1), 1400 / speed);
    return () => clearTimeout(x);
  }, [playing, speed, timeline, idx]);

  const switchMode = (m) => {
    if (m === mode) return;
    setPlaying(false); setMode(m);
    if (m === "live") { setT("latest"); say("Live: the newest readings, forecasts for the next hour."); }
    else say("Replay: a recorded day, the same models run at every step.");
  };
  const select = useCallback((id) => { setSelected(id); setUnseenMode("off"); if (id) setTab("road"); }, []);
  const checkNow = async () => {
    setChecking(true);
    try { await api("/api/live/refresh", { method: "POST" }); say("Asked the collector feed for new readings. The board updates when they land."); }
    catch (e) { say(e.message.includes("off") ? "Offline mode: using the local data only." : `Could not refresh: ${e.message}`); }
    setTimeout(() => setChecking(false), 1500);
  };

  // ---- presenter keys: the demo can be driven without hunting for buttons on a projector
  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
      const k = e.key.toLowerCase();
      if (k === "?" || k === "h") setHelp((x) => !x);
      else if (k === "escape") { setHelp(false); if (selected) { setSelected(null); setTab("signs"); } }
      else if (k === "l") switchMode("live");
      else if (k === "r") switchMode("replay");
      else if (["1", "2", "3", "4"].includes(k)) setH([0, 15, 30, 60][+k - 1]);
      else if (mode === "replay" && k === " ") { e.preventDefault(); setPlaying((p) => !p); }
      else if (mode === "replay" && k === "arrowright") { setPlaying(false); setIdx((i) => Math.min(timeline.length - 1, i + 1)); }
      else if (mode === "replay" && k === "arrowleft") { setPlaying(false); setIdx((i) => Math.max(0, i - 1)); }
      else return;
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  });

  const live = mode === "live";
  const momentLabel = snap ? `${dayLabel(snap.time)} · ${snap.time.slice(11, 16)}` : "–";
  // how fresh is what we show? (stale data must look stale)
  const ageMin = status ? Math.round((Date.parse(status.now_ist.replace(" ", "T")) - Date.parse(status.latest_reading.replace(" ", "T"))) / 60000) : null;
  const feedOff = status?.feed?.source === "off";
  const state = !linkOk || error ? "down" : sse !== "ok" && sse !== "connecting" ? "retry" : feedOff ? "offline" : ageMin > 45 ? "stale" : "ok";
  const STATE = { ok: "Live", stale: "Stale", offline: "Offline copy", down: "Backend not answering", retry: "Reconnecting" };
  const ago = ageMin == null ? "" : ageMin < 1 ? "just now" : ageMin < 90 ? `${ageMin} min ago` : `${Math.round(ageMin / 60)} h ago`;
  return (
    <div className={`app ${live ? "is-live" : "is-replay"}`}>
      <header className="top">
        <div className="brand">
          <svg className="mark" viewBox="0 0 40 40" aria-hidden="true">
            {[[8, 20], [16, 20], [24, 20], [32, 20], [20, 10], [20, 30], [12, 12], [28, 28]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="2.6" />)}
          </svg>
          <div>
            <h1>ORR Traffic Intelligence</h1>
            <p>Bengaluru ORR · 21 stretches · graph neural network forecasts</p>
          </div>
        </div>
        <div className="modes" role="tablist" aria-label="Mode">
          <button role="tab" aria-selected={live} className={live ? "on" : ""} onClick={() => switchMode("live")}><span className="dot" />Live</button>
          <button role="tab" aria-selected={!live} className={!live ? "on" : ""} onClick={() => switchMode("replay")}>Replay a day</button>
        </div>
        <div className="freshness">
          {live ? <>
            <span className={`state st-${state}`} title={state === "stale" ? "No new reading for a while. The collector reads every 15 min in rush hours and up to every 2 h at night." : state === "offline" ? "Started with --source off: the local copy of the data, no new readings." : undefined}><i />{STATE[state]}</span>
            <span>Newest reading <b>{status ? status.latest_reading.slice(11, 16) : "–"}</b> <small>{ago}</small></span>
            <button className="link" onClick={checkNow} disabled={checking || feedOff}>{checking ? "Checking…" : "Check now"}</button></>
            : <>{state === "down" && <span className="state st-down"><i />{STATE.down}</span>}Replaying <b>{snap ? dayLabel(snap.time) : "–"}</b></>}
        </div>
        <Led value={clock || "--:--:--"} size="sm" label="Time in Bengaluru" />
        <nav className="links" aria-label="Other views">
          <a href="/static/3d.html">3D view</a><a href="/classic">Classic</a><a href="/docs">API</a>
          <button className="keys" onClick={() => setHelp(true)} aria-label="Keyboard shortcuts">?</button>
        </nav>
      </header>

      <Pipeline mode={mode} status={status} snap={snap} pulse={pulse} />

      <main className="main">
        <section className="mapzone">
          {net ? <MapView net={net} snap={snap} h={h} selected={selected} onSelect={select} unseenRoad={unseenMode !== "off" ? selected : null} />
            : <div className="map skeleton" />}
          <HorizonTiles snap={snap} h={h} setH={setH} />
          <div className="moment" aria-live="polite">
            <span className={`moment-tag ${live ? "live" : ""}`}>{live ? "Live" : "Replay"}</span>
            <Led value={momentLabel} size="sm" />
            <small>{h === 0 ? "map shows recorded speeds" : `map shows the forecast for +${h} min`}</small>
          </div>
          <div className="legend">
            <div className="ramp" />
            <div className="ramp-l"><span>congested</span><span>60%</span><span>75%</span><span>free flow</span></div>
            <p>Colour = speed as a share of the road's normal speed. Moving dashes are traffic: they crawl where the road is jammed. Click a road.</p>
          </div>
        </section>

        <aside className="side">
          <div className="tabs" role="tablist" aria-label="Panels">
            {[["signs", "Next hour"], ["all", "All roads"], ["road", "Road"], ["proof", "Proof"]].map(([k, n]) => (
              <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} disabled={k === "road" && !selected} onClick={() => setTab(k)}>{n}</button>
            ))}
          </div>
          <div className="panel" key={tab}>
            {error && <p className="error" role="alert">{error}</p>}
            {tab === "signs" && <>
              <Kpis net={net} snap={snap} />
              <h2 className="ph">Where congestion is coming</h2>
              <SignBoard net={net} snap={snap} onSelect={select} selected={selected} />
              <h2 className="ph">The ORR at a glance</h2>
              <Corridor net={net} snap={snap} h={h} selected={selected} onSelect={select} />
              <Scorecard snap={snap} />
              <h2 className="ph">Whole ORR: speed and forecast</h2>
              <Chart series={series} />
            </>}
            {tab === "all" && <Matrix net={net} snap={snap} h={h} selected={selected} onSelect={select} />}
            {tab === "road" && selected && <RoadPanel net={net} snap={snap} status={status} road={selected} t={t} onClose={() => { setSelected(null); setTab("signs"); }} unseenMode={unseenMode} setUnseenMode={setUnseenMode} />}
            {tab === "road" && selected && <Neighbours net={net} snap={snap} road={selected} h={h} onSelect={select} />}
            {tab === "proof" && <><h2 className="ph">How a forecast is made</h2><ModelDiagram /><Proof status={status} results={results} /></>}
          </div>
        </aside>
      </main>

      {!live && <ReplayBar days={days} day={day} setDay={(d) => { setPlaying(false); setDay(d); }} timeline={timeline} idx={idx} seek={(i) => { setPlaying(false); seek(i); }} playing={playing} setPlaying={setPlaying} speed={speed} setSpeed={setSpeed} />}
      {toast && <div className="toast" key={toast.k} role="status">{toast.msg}</div>}
      {help && (
        <div className="help" role="dialog" aria-label="Keyboard shortcuts" onClick={() => setHelp(false)}>
          <div onClick={(e) => e.stopPropagation()}>
            <h2>Presenter keys</h2>
            <dl>
              {[["L / R", "Live / Replay a day"], ["1 2 3 4", "Map: now, +15, +30, +60 min"], ["Space", "Play or pause the replay"], ["← →", "Replay: one step back / forward"],
                ["Esc", "Back to the whole corridor"], ["?", "Show or hide this list"]].map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
            </dl>
            <button className="ghost" onClick={() => setHelp(false)}>Close</button>
          </div>
        </div>
      )}
    </div>
  );
}
