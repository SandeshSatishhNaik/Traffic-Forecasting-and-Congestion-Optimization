import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, col, pct, kmh, level, message, H, hhmm, dayLabel, LEVEL_WORD } from "./lib.js";

// ---------------------------------------------------------------- LED value: rolls in when it changes
export function Led({ value, color, size = "md", label }) {
  return (
    <span className={`led led-${size}`} style={color ? { color } : undefined} aria-label={label || String(value)}>
      <span key={String(value)} className="led-roll">{value}</span>
    </span>
  );
}

// ---------------------------------------------------------------- the pipeline: reading -> cache -> networks -> forecast
export function Pipeline({ mode, status, snap, pulse }) {
  const m = snap?.model_ms, alerts = snap?.alerts || [];
  const early = alerts.filter((a) => a.early).length;
  const stages = [
    { k: "TomTom reading", v: mode === "live" ? hhmm(status?.latest_reading?.replace(" ", "T")) : hhmm(snap?.time),
      s: mode === "live" ? "newest reading · 21 road stretches" : `recorded ${snap ? dayLabel(snap.time) : ""}` },
    { k: "Data cache", v: status ? status.readings.toLocaleString("en-IN") : "–",
      s: `since ${status ? dayLabel(status.first).slice(4) : "–"} · ${status?.feed?.source === "off" ? "offline" : `every ${Math.round((status?.feed?.interval_s || 180) / 60)} min`}` },
    { k: "Graph neural network", v: m == null ? "–" : `${m} ms`, s: "3 horizons × 5 runs" },
    { k: "Forecast", v: snap ? `${alerts.length}` : "–", s: `alerts · ${early} early warning${early === 1 ? "" : "s"}` },
  ];
  return (
    <section className="pipeline" aria-label="Live pipeline">
      {stages.map((st, i) => (
        <div className="stage-wrap" key={st.k}>
          <div className={`stage ${pulse.n && i >= pulse.from ? "fire" : ""}`} key={`${pulse.n}-${i}`} style={{ animationDelay: `${Math.max(0, i - pulse.from) * 0.32}s` }}>
            <span className="stage-k">{st.k}</span>
            <Led value={st.v} size="sm" />
            <span className="stage-s">{st.s}</span>
          </div>
          {i < stages.length - 1 && (
            <div className="wire" aria-hidden="true">
              <i key={pulse.n} className={pulse.n && i >= pulse.from ? "spark" : ""} style={{ animationDelay: `${(i - pulse.from) * 0.32 + 0.12}s` }} />
            </div>
          )}
        </div>
      ))}
    </section>
  );
}

// ---------------------------------------------------------------- horizon tiles: now / +15 / +30 / +60, same scale
export function HorizonTiles({ snap, h, setH }) {
  const s = snap?.summary || {};
  const tiles = [[0, "Now", s.now, "recorded"], [15, "+15 min", s.r15, "forecast"], [30, "+30 min", s.r30, "forecast"], [60, "+60 min", s.r60, "forecast"]];
  return (
    <div className="tiles" role="tablist" aria-label="Show the map now or forecast">
      {tiles.map(([v, name, r, kind]) => (
        <button key={v} role="tab" aria-selected={h === v} className={`tile ${h === v ? "on" : ""}`} onClick={() => setH(v)}>
          <span className="tile-k">{name}</span>
          <Led value={pct(r)} color={col(r)} size="md" />
          <span className="tile-s">{v === 0 || r == null || s.now == null ? `ORR speed · ${kind}` : (() => {
            const d = Math.round((r - s.now) * 100);
            return d === 0 ? "same as now" : <><b className={d < 0 ? "dn" : "up"}>{d < 0 ? "▼" : "▲"} {Math.abs(d)}</b> point{Math.abs(d) === 1 ? "" : "s"} vs now</>;
          })()}</span>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- the sign board: hotspots, re-ranking in place
export function SignBoard({ net, snap, onSelect, selected }) {
  const rows = !net || !snap ? [] : net.roads
    .map((r) => ({ r, d: snap.roads[r.id], m: message(snap.roads[r.id]) }))
    .filter((x) => x.m)
    .sort((a, b) => a.m.rank - b.m.rank || a.d.now_ratio - b.d.now_ratio)
    .slice(0, 7);
  const refs = useRef({}), prev = useRef({}), seen = useRef({});
  const [fresh, setFresh] = useState({});
  // FLIP: rows slide from their old place to the new one instead of jumping
  useLayoutEffect(() => {
    const now = {};
    for (const { r, m } of rows) {
      const el = refs.current[r.id]; if (!el) continue;
      const top = el.getBoundingClientRect().top; now[r.id] = top;
      if (prev.current[r.id] != null && Math.abs(prev.current[r.id] - top) > 1) {
        el.animate([{ transform: `translateY(${prev.current[r.id] - top}px)` }, { transform: "none" }], { duration: 520, easing: "cubic-bezier(.2,.9,.2,1)" });
      }
    }
    prev.current = now;
    const changed = {}, first = Object.keys(seen.current).length === 0;   // nothing is "new" on the first render
    for (const { r, m } of rows) if (seen.current[r.id] !== m.text) { if (!first) changed[r.id] = true; seen.current[r.id] = m.text; }
    if (Object.keys(changed).length) { setFresh(changed); const t = setTimeout(() => setFresh({}), 6000); return () => clearTimeout(t); }
  }, [snap]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!snap) return <div className="board skeleton" />;
  return (
    <ol className="board" aria-label="Hotspots in the next hour">
      {rows.length === 0 && <li className="sign calm"><span className="sign-msg">All clear</span><span className="sign-road">No road is slow now or in the next hour</span></li>}
      {rows.map(({ r, d, m }) => (
        <li key={r.id} ref={(e) => (refs.current[r.id] = e)} className={`sign tone-${m.tone} ${fresh[r.id] ? "fresh" : ""} ${selected === r.id ? "sel" : ""}`}>
          <button className="sign-btn" onClick={() => onSelect(r.id)} aria-label={`${r.label}: ${m.text}`}>
            <span className="sign-msg">{m.text}</span>
            <span className="sign-road">{r.label}<small>{r.road}</small></span>
            <span className="sign-cells" aria-hidden="true">
              {[d.now_ratio, d.r15, d.r30, d.r60].map((v, i) => <i key={i} style={{ background: col(v), color: v != null && v < 0.5 ? "#fff" : undefined }}>{pct(v)}</i>)}
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}

// ---------------------------------------------------------------- forecast chart (recorded, forecast band, what happened)
export function Chart({ series, extra, extraLabel }) {
  const ref = useRef(null);
  const [w, setW] = useState(420), [hv, setHv] = useState(null);
  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, e.contentRect.width)));
    ro.observe(ref.current); return () => ro.disconnect();
  }, []);
  if (!series) return <div ref={ref} className="chart skeleton" />;
  const Hh = 190, pl = 38, pr = 14, pt = 16, pb = 24;
  const past = series.past.filter((p) => p[1] != null), fc = series.forecast;
  if (!past.length) return <div ref={ref} className="chart empty">No readings in the last hours</div>;
  const T = (s) => new Date(`${s}:00Z`).getTime();
  const x0 = T(past[0][0]), x1 = T(fc.length ? fc[fc.length - 1].t : past[past.length - 1][0]);
  const typ = (series.typical || []).filter((p) => p[1] != null && T(p[0]) >= T(past[0][0]));
  const typAt = Object.fromEntries(typ);
  const vals = past.map((p) => p[1]).concat(fc.flatMap((f) => [f.lo, f.hi, f.actual]), extra ? extra.map((e) => e[1]) : [], typ.map((p) => p[1])).filter((v) => v != null);
  const lo = Math.min(0.4, ...vals) - 0.03, hi = Math.max(1.0, ...vals) + 0.03;
  const X = (s) => pl + ((T(s) - x0) / Math.max(1, x1 - x0)) * (w - pl - pr);
  const Y = (v) => pt + ((hi - v) / (hi - lo)) * (Hh - pt - pb);
  const now = past[past.length - 1];
  const band = [now].concat(fc.map((f) => [f.t, f.hi])).map(([s, v]) => `${X(s)},${Y(v)}`)
    .concat([now].concat(fc.map((f) => [f.t, f.lo])).reverse().map(([s, v]) => `${X(s)},${Y(v)}`)).join(" ");
  const labels = []; let lastX = -99;
  for (const [s] of past) { const x = X(s); if (x - lastX >= 46) { labels.push([s, x]); lastX = x; } }
  const key = `${series.time}-${series.road}`;
  const pts = past.map(([s, v]) => ({ s, v, k: "recorded" })).concat(fc.map((f) => ({ s: f.t, v: f.mean, k: `forecast +${f.h} min`, f })));
  const near = (ev) => { const b = ev.currentTarget.getBoundingClientRect(), x = ev.clientX - b.left; let best = 0; pts.forEach((p, i) => { if (Math.abs(X(p.s) - x) < Math.abs(X(pts[best].s) - x)) best = i; }); setHv(best); };
  const hp = hv != null ? pts[hv] : null;
  return (
    <div ref={ref} className="chart">
      <div className="chart-read" aria-live="off">
        {hp ? <><b>{hp.s.slice(11, 16)}</b><span style={{ color: col(hp.v) }}>{pct(hp.v)}</span><em>{hp.k}</em>
          {hp.f && <small>range {pct(hp.f.lo)}–{pct(hp.f.hi)}{hp.f.actual != null ? ` · happened ${pct(hp.f.actual)}` : ""}</small>}
          {typAt[hp.s] != null && <small>usual {pct(typAt[hp.s])}</small>}</>
          : <small>Move over the chart to read a value.</small>}
      </div>
      <svg viewBox={`0 0 ${w} ${Hh}`} width="100%" height={Hh} role="img" aria-label="Speed over the last hours and the forecast for the next hour" onPointerMove={near} onPointerLeave={() => setHv(null)}>
        {[0.6, 0.75, 1].map((v) => (
          <g key={v}><line x1={pl} x2={w - pr} y1={Y(v)} y2={Y(v)} className="grid" /><text x={pl - 6} y={Y(v) + 4} textAnchor="end" className="axis">{Math.round(v * 100)}%</text></g>
        ))}
        {labels.map(([s, x]) => <text key={s} x={x} y={Hh - 6} textAnchor="middle" className="axis">{s.slice(11, 16)}</text>)}
        <rect x={X(now[0])} y={pt} width={Math.max(0, w - pr - X(now[0]))} height={Hh - pt - pb} className="future" />
        {typ.length > 1 && <polyline points={typ.map(([s, v]) => `${X(s)},${Y(v)}`).join(" ")} className="typ draw-fade" />}
        {fc.length > 0 && <polygon key={`b${key}`} points={band} className="band draw-fade" />}
        <polyline key={`p${key}`} points={past.map(([s, v]) => `${X(s)},${Y(v)}`).join(" ")} className="rec draw" pathLength="1" />
        {fc.length > 0 && <polyline key={`f${key}`} points={[now].concat(fc.map((f) => [f.t, f.mean])).map(([s, v]) => `${X(s)},${Y(v)}`).join(" ")} className="fc draw late" pathLength="1" />}
        {extra && <polyline key={`x${key}`} points={[now].concat(extra).map(([s, v]) => `${X(s)},${Y(v)}`).join(" ")} className="virt draw late" pathLength="1" />}
        {fc.map((f) => <circle key={f.t} cx={X(f.t)} cy={Y(f.mean)} r="3.6" className="fc-dot" />)}
        {fc.filter((f) => f.actual != null).map((f) => <circle key={`a${f.t}`} cx={X(f.t)} cy={Y(f.actual)} r="6" className="act" style={{ stroke: col(f.actual) }} />)}
        <line x1={X(now[0])} x2={X(now[0])} y1={pt - 6} y2={Hh - pb} className="nowline" />
        <text x={X(now[0])} y={pt - 8} textAnchor="middle" className="nowtxt">now</text>
        {hp && <g pointerEvents="none"><line x1={X(hp.s)} x2={X(hp.s)} y1={pt} y2={Hh - pb} className="hairline" /><circle cx={X(hp.s)} cy={Y(hp.v)} r="5" className="hov" style={{ stroke: col(hp.v) }} /></g>}
      </svg>
      <div className="chart-key">
        <span><i className="k-rec" />recorded</span><span><i className="k-fc" />forecast</span><span><i className="k-band" />range of 5 runs</span>
        {typ.length > 1 && <span><i className="k-typ" />usual on a {series.daytype === "weekday" ? "weekday" : series.daytype}</span>}
        {fc.some((f) => f.actual != null) && <span><i className="k-act" />what happened</span>}
        {extra && <span><i className="k-virt" />{extraLabel}</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- one road: numbers, chart, unseen-road test
export function RoadPanel({ net, snap, status, road, t, onClose, unseenMode, setUnseenMode }) {
  const tm = status?.model?.test_metrics;
  const r = net?.roads.find((x) => x.id === road), d = snap?.roads[road];
  const [series, setSeries] = useState(null), [u, setU] = useState(null), [err, setErr] = useState(null);
  useEffect(() => setSeries(null), [road]);
  useEffect(() => {
    let current = true;
    api(`/api/series?t=${encodeURIComponent(t)}&road=${road}&hours=6`).then((x) => current && setSeries(x)).catch(() => {});
    return () => { current = false; };
  }, [road, t, snap]);
  useEffect(() => {
    setU(null); setErr(null);
    if (unseenMode === "off") return;
    let current = true;
    api(`/api/unseen?road=${road}&t=${encodeURIComponent(t)}`).then((x) => current && setU(x)).catch((e) => current && setErr(e.message));
    return () => { current = false; };
  }, [road, t, unseenMode, snap]);
  if (!r || !d) return null;
  const k = unseenMode === "none" ? "virtual" : "new";
  const extra = u ? u.rows.map((x) => [x.t, x[k]]) : null;
  const m = u?.measured?.["60"];
  return (
    <div className="road">
      <div className="road-head">
        <div>
          <h2>{r.label}</h2>
          <p>{r.road} · {r.km} km · normal speed {Math.round(d.ref)} km/h</p>
        </div>
        <button className="ghost" onClick={onClose} aria-label="Back to the whole corridor">Corridor</button>
      </div>
      <div className="road-cells">
        {[["Now", d.now_ratio, d.now, null], ...H.map((h) => [`+${h} min`, d[`r${h}`], d[`f${h}`], d[`a${h}`], `${kmh(d[`lo${h}`])}–${kmh(d[`hi${h}`])}`])].map(([n, v, s, a, rg]) => (
          <div key={n} className="rc">
            <span>{n}</span>
            <Led value={pct(v)} color={col(v)} size="sm" />
            <small>{kmh(s)} km/h{a != null ? ` · happened ${Math.round(a)}` : ""}</small>{rg && <small className="rg">range {rg}</small>}
          </div>
        ))}
      </div>
      <p className="honest">"Range" shows how far the 5 trained runs disagree; it is not a guarantee.{tm ? <> On the unseen test week the average error was <b>{H.map((h) => tm[String(h)].model.toFixed(1)).join(" / ")} km/h</b> at +15 / +30 / +60 min.</> : null}</p>
      <Chart series={series} extra={extra} extraLabel={unseenMode === "none" ? "virtual sensor" : "never-trained model"} />
      <div className="unseen">
        <h3>What if we had never seen this road?</h3>
        <div className="seg" role="radiogroup" aria-label="Unseen-road test">
          {[["off", "Normal model"], ["new", "New sensor"], ["none", "No sensor"]].map(([v, n]) => (
            <button key={v} role="radio" aria-checked={unseenMode === v} className={unseenMode === v ? "on" : ""} onClick={() => setUnseenMode(v)}>{n}</button>
          ))}
        </div>
        {unseenMode !== "off" && (
          <p className="unseen-note">
            {err ? err : !u ? "Running the networks that never saw this road…" : unseenMode === "none"
              ? <>Estimated only from the connected roads ({u.neighbours.join(", ")}). Test week, +60 min error: virtual sensor <b>{m.none.unseen?.toFixed(1)}</b>, neighbours' forecast <b>{m.none.nbr_forecast?.toFixed(1)}</b>, copy neighbours {m.none.neighbours?.toFixed(1)}, normal model {m.none.seen?.toFixed(1)} points of normal speed.</>
              : <>Uses this road's live readings but no training history. Test week, +60 min error: {m.new.unseen?.toFixed(1)} vs same-as-now {m.new.same_as_now?.toFixed(1)} vs normal model {m.new.seen?.toFixed(1)} points.</>}
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- proof: honest results with their limits
export function Proof({ status, results }) {
  const tm = status?.model?.test_metrics, mr = status?.model;
  return (
    <div className="proof">
      <h2>How good is the forecast?</h2>
      <p className="lede">Tested on a week the model never saw ({mr?.tested_on?.[0]} to {mr?.tested_on?.[1]}), against simply assuming "the speed stays as it is now". Average error in km/h, lower is better.</p>
      {tm && (
        <table className="metrics">
          <thead><tr><th>Ahead</th><th>Our model</th><th>Same as now</th><th>Better by</th></tr></thead>
          <tbody>
            {H.map((h) => { const x = tm[String(h)]; const g = Math.round((1 - x.model / x.same_as_now) * 100); return (
              <tr key={h}><td>+{h} min</td><td className="num strong">{x.model.toFixed(2)}</td><td className="num">{x.same_as_now.toFixed(2)}</td>
                <td><span className="gain"><i style={{ width: `${Math.min(100, g * 3)}%` }} />{g}%</span></td></tr>); })}
          </tbody>
        </table>
      )}
      <h3>Eleven model versions, same test rows (Phase 2, 25–31 Oct)</h3>
      {results && (
        <table className="metrics models">
          <thead><tr><th>Model</th>{results.horizons.map((h) => <th key={h}>+{h}</th>)}</tr></thead>
          <tbody>
            {results.models.map((x) => (
              <tr key={x.name} className={x.used ? "used" : ""}><td>{x.name}{x.used && <em>in this app</em>}</td>{x.mae.map((v, i) => <td key={i} className="num">{v.toFixed(2)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      )}
      <h3>Roads we never measured</h3>
      <p>Each of the 21 roads was hidden from training in turn. With no sensor at all, the road graph estimates it from its neighbours: 12.0 points of error at +60 min against 14.2 for copying the neighbours; real readings with training stay best at 8.2. <span className="src">modeling/results/unseen-roads-2026-11-26.md</span></p>
      <h3>Limits</h3>
      <ul className="limits">
        <li>One corridor (the ORR), one test week per result.</li>
        <li>STID, a model without the road graph, ties our graph model: the graph is not the only route to this accuracy.</li>
        <li>Readings are TomTom snapshots every 15 min in rush hours, up to 2 h at night; "live" is as fresh as the last one.</li>
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------- replay controls
export function ReplayBar({ days, day, setDay, timeline, idx, seek, playing, setPlaying, speed, setSpeed }) {
  const strip = useRef(null);
  const mins = (hm) => +hm.slice(0, 2) * 60 + +hm.slice(3, 5);
  const at = (hm) => `${(mins(hm) / 1440) * 100}%`;   // the strip is a 24-hour clock, left to right
  const nearest = (frac) => {
    const m = frac * 1440; let best = 0;
    timeline.forEach((x, i) => { if (Math.abs(mins(x.time) - m) < Math.abs(mins(timeline[best].time) - m)) best = i; });
    return best;
  };
  return (
    <div className="replay">
      <select value={day || ""} onChange={(e) => setDay(e.target.value)} aria-label="Day to replay">
        {days.map((d) => <option key={d.date} value={d.date}>{d.label}{d.daytype !== "weekday" ? " · holiday/weekend" : ""}</option>)}
      </select>
      <button className="play" onClick={() => setPlaying(!playing)} aria-label={playing ? "Pause" : "Play"}>
        {playing ? <svg viewBox="0 0 24 24" width="20" height="20"><rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor" /><rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor" /></svg>
          : <svg viewBox="0 0 24 24" width="20" height="20"><path d="M8 5v14l11-7z" fill="currentColor" /></svg>}
      </button>
      <div className="seg small" role="radiogroup" aria-label="Replay speed">
        {[1, 2, 4].map((s) => <button key={s} role="radio" aria-checked={speed === s} className={speed === s ? "on" : ""} onClick={() => setSpeed(s)}>{s}×</button>)}
      </div>
      <div className="strip" ref={strip} role="slider" aria-label="Time of day" aria-valuemin={0} aria-valuemax={timeline.length - 1} aria-valuenow={idx}
        aria-valuetext={timeline[idx]?.time} tabIndex={0}
        onKeyDown={(e) => { if (e.key === "ArrowRight") seek(Math.min(timeline.length - 1, idx + 1)); if (e.key === "ArrowLeft") seek(Math.max(0, idx - 1)); }}
        onPointerDown={(e) => {
          if (!timeline.length) return;
          const go = (ev) => { const b = strip.current.getBoundingClientRect(); seek(nearest(Math.max(0, Math.min(1, (ev.clientX - b.left) / b.width)))); };
          go(e); const up = () => { removeEventListener("pointermove", go); removeEventListener("pointerup", up); };
          addEventListener("pointermove", go); addEventListener("pointerup", up);
        }}>
        {timeline.map((x, i) => {
          const end = i + 1 < timeline.length ? mins(timeline[i + 1].time) : Math.min(1440, mins(x.time) + 60);
          return <i key={x.time} style={{ left: at(x.time), width: `${((end - mins(x.time)) / 1440) * 100}%`, background: col(x.ratio), opacity: i <= idx ? 1 : 0.35 }} title={`${x.time} · ${pct(x.ratio)}`} />;
        })}
        {timeline[idx] && <b className="cursor" style={{ left: at(timeline[idx].time) }}><span>{timeline[idx].time}</span></b>}
        <div className="strip-hours" aria-hidden="true">{["03:00", "06:00", "09:00", "12:00", "15:00", "18:00", "21:00"].map((hr) => <span key={hr} style={{ left: at(hr) }}>{hr}</span>)}</div>
      </div>
    </div>
  );
}

export { level, LEVEL_WORD };
