import { Led } from "./parts.jsx";
import { col, pct, kmh, message, H } from "./lib.js";

const at = (d, h) => (!d ? null : h === 0 ? d.now_ratio : d[`r${h}`]);

// group the roads by carriageway, in driving order
function groups(net) {
  const g = new Map();
  for (const r of net?.roads || []) { if (!g.has(r.route)) g.set(r.route, { route: r.route, name: r.road, tier: r.tier, roads: [] }); g.get(r.route).roads.push(r); }
  for (const x of g.values()) x.roads.sort((a, b) => a.seq - b.seq);
  return [...g.values()].sort((a, b) => (a.tier === "core" ? 0 : 1) - (b.tier === "core" ? 0 : 1));
}

// ---------------------------------------------------------------- four numbers that answer "how is the corridor?"
export function Kpis({ net, snap }) {
  if (!net || !snap) return <div className="kpis skeleton" />;
  const ds = net.roads.map((r) => snap.roads[r.id]).filter(Boolean);
  const slowNow = ds.filter((d) => d.now_ratio != null && d.now_ratio < 0.75).length;
  const coming = ds.filter((d) => d.now_ratio >= 0.75 && message(d)).length;
  const early = snap.alerts.filter((a) => a.early).length;
  const cells = [
    ["ORR speed now", pct(snap.summary.now), col(snap.summary.now), `${net.roads.filter((r) => r.tier === "core").length} core stretches`],
    ["Slow now", `${slowNow}`, null, `of ${ds.length} stretches`],
    ["Slowing soon", `${coming}`, null, "flagged for the next hour"],
    ["Early warnings", `${early}`, null, "before it slows"],
  ];
  return (
    <div className="kpis" aria-label="Corridor summary">
      {cells.map(([k, v, c, s]) => (
        <div className="kpi" key={k}><span className="kpi-k">{k}</span><Led value={v} color={c || undefined} size="md" /><span className="kpi-s">{s}</span></div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- the ORR drawn as straight strips: width = length, colour = speed at the chosen time
export function Corridor({ net, snap, h, selected, onSelect }) {
  if (!net || !snap) return <div className="corr skeleton" />;
  return (
    <div className="corr">
      {groups(net).filter((g) => g.tier === "core").map((g) => (
        <div className="lane" key={g.route}>
          <span className="lane-k">{g.name}<small>{g.route.endsWith("cw") && !g.route.endsWith("ccw") ? "→ clockwise" : "→ anticlockwise"}</small></span>
          <div className="lane-bar" role="group" aria-label={`${g.name}, stretches in driving order`}>
            {g.roads.map((r) => {
              const v = at(snap.roads[r.id], h);
              return (
                <button key={r.id} className={`seg-cell ${selected === r.id ? "sel" : ""}`} style={{ flexGrow: r.km, background: col(v), color: v != null && v < 0.5 ? "#fff" : "#0b0c0e" }}
                  onClick={() => onSelect(r.id)} title={`${r.label} · ${r.km} km · ${pct(v)} of normal`} aria-label={`${r.label}, ${pct(v)} of normal speed`}>
                  {r.km >= 1.4 ? pct(v) : ""}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      <p className="corr-note">Each block is one stretch, as long as the road. {h === 0 ? "Recorded now." : `Forecast for +${h} min.`} Click a block.</p>
    </div>
  );
}

// ---------------------------------------------------------------- what the models said and what then happened
export function Scorecard({ snap }) {
  if (!snap) return null;
  const a = snap.alerts, checked = a.filter((x) => x.confirmed != null), ok = checked.filter((x) => x.confirmed).length;
  const early = a.filter((x) => x.early), earlyChecked = early.filter((x) => x.confirmed != null), earlyOk = earlyChecked.filter((x) => x.confirmed).length;
  return (
    <div className="score">
      <h2 className="ph">Alerts: said, then happened?</h2>
      {a.length === 0 ? <p className="score-note">No road is forecast to slow in the next hour.</p> : <>
        <div className="score-bar" aria-hidden="true">
          <i style={{ flexGrow: ok, background: "var(--free)" }} /><i style={{ flexGrow: checked.length - ok, background: "var(--jam)" }} /><i style={{ flexGrow: a.length - checked.length, background: "var(--rim-hi)" }} />
        </div>
        <ul className="score-key">
          <li><i style={{ background: "var(--free)" }} />came true <b>{ok}</b></li>
          <li><i style={{ background: "var(--jam)" }} />did not <b>{checked.length - ok}</b></li>
          <li><i style={{ background: "var(--rim-hi)" }} />not checked <b>{a.length - checked.length}</b></li>
        </ul>
        <p className="score-note">
          {checked.length ? <>{ok} of {checked.length} alerts that can already be checked came true{early.length ? <>; early warnings (road not yet slow): {earlyOk} of {earlyChecked.length}</> : null}.</>
            : "None of these can be checked yet: they point to the future. Replay a past day to see how many came true."}
        </p>
      </>}
    </div>
  );
}

// ---------------------------------------------------------------- every road in one table
export function Matrix({ net, snap, h, selected, onSelect }) {
  if (!net || !snap) return <div className="board skeleton" />;
  return (
    <div className="matrix">
      <p className="mx-note">All {net.roads.length} stretches at four moments. Colour is the share of normal speed; the last column is the change over the next hour.</p>
      {groups(net).map((g) => (
        <section key={g.route}>
          <h3 className="mx-h">{g.name}<small>{g.tier === "core" ? "core corridor" : "context road: feeds the corridor"}</small></h3>
          <table className="mx">
            <thead><tr><th>Stretch</th><th>Now</th><th>+15</th><th>+30</th><th>+60</th><th>Δ 1 h</th></tr></thead>
            <tbody>
              {g.roads.map((r) => {
                const d = snap.roads[r.id], vals = [d?.now_ratio, d?.r15, d?.r30, d?.r60];
                const delta = vals[0] != null && vals[3] != null ? Math.round((vals[3] - vals[0]) * 100) : null;
                return (
                  <tr key={r.id} className={selected === r.id ? "sel" : ""}>
                    <td><button onClick={() => onSelect(r.id)}>{r.label}<small>{r.km} km · {kmh(d?.now)} km/h now</small></button></td>
                    {vals.map((v, i) => <td key={i}><i className="mx-c" style={{ background: col(v), color: v != null && v < 0.5 ? "#fff" : undefined, outline: [0, 15, 30, 60][i] === h ? "2px solid var(--amber)" : "none" }}>{pct(v)}</i></td>)}
                    <td className={`mx-d ${delta == null ? "" : delta <= -10 ? "dn" : delta >= 10 ? "up" : ""}`}>{delta == null ? "–" : `${delta > 0 ? "▲" : delta < 0 ? "▼" : "•"} ${Math.abs(delta)}`}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- roads that feed into / out of this one
export function Neighbours({ net, snap, road, h, onSelect }) {
  const r = net?.roads.find((x) => x.id === road); if (!r) return null;
  const by = (id) => net.roads.find((x) => x.id === id);
  const chip = (id, kind, turn) => {
    const x = by(id); if (!x) return null; const v = at(snap?.roads[id], h);
    return <button key={`${kind}${id}`} className="chip" onClick={() => onSelect(id)}><i style={{ background: col(v) }} />{x.label}<small>{pct(v)}{turn ? " · turn" : ""}</small></button>;
  };
  const up = r.upstream || [], down = r.downstream || [];
  if (!up.length && !down.length) return null;
  return (
    <div className="nbrs">
      <h3>Connected roads</h3>
      <p>The network passes information along these links, so a jam here is a warning for the roads after it.</p>
      <div className="nbr-row"><span>Traffic comes from</span><div>{up.length ? up.map((id) => chip(id, "u")) : <em>no listed road</em>}</div></div>
      <div className="nbr-row"><span>Traffic goes to</span><div>{down.length ? down.map((x) => chip(x.id, "d", x.turn)) : <em>no listed road</em>}</div></div>
    </div>
  );
}

// ---------------------------------------------------------------- how a forecast is made: four steps
export function ModelDiagram() {
  const steps = [
    ["1", "Read", "The last 3 readings (45 min) of all 21 stretches, the time of day, weekday or holiday, and rain."],
    ["2", "Share along the road", "Two graph-convolution layers let each stretch look at the stretches it connects to, so a jam moves through the network."],
    ["3", "Predict", "15 networks run: +15, +30 and +60 min, 5 trained runs each."],
    ["4", "Show the range", "The mean of the 5 runs is the forecast; their spread is the shaded range."],
  ];
  return (
    <ol className="flow-steps" aria-label="How a forecast is made">
      {steps.map(([n, k, s], i) => (
        <li key={n}>
          <span className="fs-n">{n}</span>
          <div><b>{k}</b><p>{s}</p></div>
          {i < steps.length - 1 && <svg className="fs-arrow" viewBox="0 0 12 14" aria-hidden="true"><path d="M6 0v10M1 6l5 6 5-6" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg>}
        </li>
      ))}
    </ol>
  );
}

export { H };
