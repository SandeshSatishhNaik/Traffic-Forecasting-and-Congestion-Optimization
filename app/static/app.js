"use strict";
// Offline traffic intelligence app (talks only to the local server; no internet needed).
const $ = (s) => document.querySelector(s);
const H = [15, 30, 60];
const LEVEL_COLOR = { free: "var(--free)", slow: "var(--slow)", severe: "var(--severe)", none: "var(--none)" };
const LEVEL_TEXT = { free: "Free flowing", slow: "Slow", severe: "Congested", none: "No reading" };
const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
let META, RES, STATE, GEO, DAYS = [], idx = 0, hz = "now", showActual = false, aFilter = "all", playing = null, reqId = 0;
let routeSel = { src: null, dst: null }, ROUTE = null;

const get = (u) => fetch(u).then((r) => r.json());
const f1 = (v) => (v == null ? "–" : v.toFixed(1));
const pct = (v) => (v == null ? "–" : Math.round(v * 100) + "%");
const roadById = (id) => META.roads.find((r) => r.id === id);
const levelOf = (q) => (q == null ? "none" : q < 0.6 ? "severe" : q < 0.75 ? "slow" : "free");

function parseT(s) {
  const [d, t] = s.split("T"); const [y, m, dd] = d.split("-").map(Number);
  return { date: d, wd: WD[new Date(Date.UTC(y, m - 1, dd)).getUTCDay()], day: dd, mon: MON[m - 1], time: t };
}
function timeLabel(i) {
  const p = parseT(META.times[i]);
  return `${p.wd} ${p.day} ${p.mon}, ${p.time}` + (META.daytype[i] === "weekday" ? "" : " (weekend/holiday)") +
    (META.meta.mode === "latest" && i === META.times.length - 1 ? " · latest reading" : "");
}

// ------------------------------------------------------------------ map geometry from coordinates
function buildGeometry() {
  const flow = META.links.filter((l) => l.kind === "flow");
  const raw = {};
  for (const r of META.roads) {
    const s = flow.find((l) => l.dst === r.id), e = flow.find((l) => l.src === r.id);
    const p = [];
    if (s) p.push([s.lat, s.lon]);
    p.push([r.lat, r.lon]);
    if (e) p.push([e.lat, e.lon]);
    raw[r.id] = p;
  }
  const all = Object.values(raw).flat();
  const lat0 = all.reduce((a, p) => a + p[0], 0) / all.length, k = Math.cos((lat0 * Math.PI) / 180);
  const xs = all.map((p) => p[1] * k), ys = all.map((p) => -p[0]);
  const W = 800, Hh = 560, pad = 60;
  const minx = Math.min(...xs), maxx = Math.max(...xs), miny = Math.min(...ys), maxy = Math.max(...ys);
  const sc = Math.min((W - 2 * pad) / (maxx - minx), (Hh - 2 * pad) / (maxy - miny));
  const ox = (W - sc * (maxx - minx)) / 2, oy = (Hh - sc * (maxy - miny)) / 2;
  const proj = ([la, lo]) => [ox + (lo * k - minx) * sc, oy + (-la - miny) * sc];
  const geo = {};
  const dots = [];
  for (const r of META.roads) {
    let pts = raw[r.id].map(proj);
    if (pts.length === 1) {   // a stretch without links: a dot; keep dots apart
      let [x, y] = pts[0];
      while (dots.some(([a, b]) => Math.hypot(a - x, b - y) < 16)) y += 18;
      dots.push([x, y]);
      geo[r.id] = { dot: [x, y], mid: [x, y] };
    } else {
      geo[r.id] = { line: offsetLeft(pts, 4.5), mid: proj([r.lat, r.lon]) };
    }
  }
  return geo;
}
// shift a polyline to the left of the direction of travel (India drives on the left)
function offsetLeft(pts, d) {
  return pts.map((p, i) => {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
    const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1;
    return [p[0] + (dy / L) * d, p[1] - (dx / L) * d];
  });
}
const LABELS = [
  ["orr_ccw_01", "Silk Board", -10, 22, "middle"], ["orr_ccw_02", "HSR Layout", 0, 24, "middle"], ["orr_ccw_03", "Agara", -14, -12, "end"],
  ["orr_iblur", "Iblur", 0, 24, "middle"], ["orr_bellandur", "Bellandur", 14, 18, "start"], ["orr_marathahalli", "Marathahalli", 14, 4, "start"],
  ["orr_mahadevapura", "Mahadevapura", 14, 4, "start"], ["orr_doddanekundi", "Doddanekundi", -14, 4, "end"],
  ["hosur_02", "Hosur Rd", -12, 0, "end"], ["hosur_bommanahalli", "Bommanahalli", -12, 10, "end"],
  ["old_airport_konena", "Old Airport Rd (in)", -14, 4, "end"], ["varthur_kundalahalli", "Varthur Rd (out)", -14, 4, "end"],
];
const ptsAttr = (pts) => pts.map((p) => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");

function drawMap(svg, colorOf, overlay) {
  let s = `<rect x="0" y="0" width="800" height="560" fill="none"/>`;
  const faded = overlay ? 0.35 : 1;
  for (const r of META.roads) {
    const g = GEO[r.id];
    if (g.line) s += `<polyline points="${ptsAttr(g.line)}" fill="none" stroke="var(--casing)" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>`;
  }
  for (const r of META.roads) {
    const g = GEO[r.id], c = colorOf(r.id);
    if (g.line) s += `<polyline class="road" data-id="${r.id}" points="${ptsAttr(g.line)}" fill="none" stroke="${c}" stroke-opacity="${faded}" stroke-width="7.5" stroke-linecap="round" stroke-linejoin="round"/>`;
    else s += `<circle class="road" data-id="${r.id}" cx="${g.dot[0].toFixed(1)}" cy="${g.dot[1].toFixed(1)}" r="7.5" fill="${c}" fill-opacity="${faded}" stroke="var(--casing)" stroke-width="2.5"/>`;
  }
  if (overlay) {
    for (const [ids, color, w, dash] of overlay) {
      for (const id of ids) {
        const g = GEO[id];
        if (g.line) s += `<polyline class="road" data-id="${id}" points="${ptsAttr(g.line)}" fill="none" stroke="${color}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" ${dash ? 'stroke-dasharray="7 6"' : ""}/>`;
        else s += `<circle class="road" data-id="${id}" cx="${g.dot[0]}" cy="${g.dot[1]}" r="9" fill="none" stroke="${color}" stroke-width="3.5"/>`;
      }
    }
  }
  for (const [id, text, dx, dy, anchor] of LABELS) {
    const g = GEO[id]; if (!g) continue;
    const [x, y] = g.mid;
    s += `<text class="maplabel" x="${(x + dx).toFixed(1)}" y="${(y + dy).toFixed(1)}" text-anchor="${anchor}">${text}</text>`;
  }
  s += `<text x="785" y="548" text-anchor="end" class="maplabel" style="font-size:11px">N &#8593;  map drawn from road coordinates, no map tiles</text>`;
  svg.innerHTML = s;
}

// ------------------------------------------------------------------ tooltip
function attachTip(svg, textOf) {
  const tip = $("#tip");
  svg.addEventListener("mousemove", (e) => {
    const el = e.target.closest("[data-id]");
    if (!el) { tip.style.display = "none"; return; }
    tip.innerHTML = textOf(el.dataset.id);
    tip.style.display = "block";
    tip.style.left = Math.min(e.clientX + 14, window.innerWidth - 300) + "px";
    tip.style.top = e.clientY + 14 + "px";
  });
  svg.addEventListener("mouseleave", () => (tip.style.display = "none"));
}
function roadTip(id) {
  const r = roadById(id), d = STATE && STATE.roads[id];
  if (!d) return r.label;
  let t = `<b>${r.label}</b><br><span class="muted">${r.road}, ${r.km.toFixed(1)} km, normal ${f1(r.ref)} km/h</span><br>Now: ${f1(d.now)} km/h`;
  for (const h of H) t += `<br>+${h} min: forecast ${f1(d["f" + h])}` + (showActual ? `, actual ${f1(d["a" + h])}` : "");
  return t;
}

// ------------------------------------------------------------------ replay clock
function buildDays() {
  DAYS = [];
  META.times.forEach((t, i) => {
    const p = parseT(t);
    if (!DAYS.length || DAYS[DAYS.length - 1].date !== p.date) DAYS.push({ date: p.date, start: i, n: 0, p });
    DAYS[DAYS.length - 1].n++;
  });
  $("#days").innerHTML = DAYS.map((d, k) => `<button data-k="${k}">${d.p.day} ${d.p.mon}<span class="wk">${d.p.wd}${META.daytype[d.start] === "weekday" ? "" : " · holiday/wknd"}</span></button>`).join("");
  $("#days").onclick = (e) => {
    const b = e.target.closest("button"); if (!b) return;
    const d = DAYS[+b.dataset.k];
    setIdx(d.start + Math.min(+$("#slot").value, d.n - 1));
  };
}
function dayOf(i) { return DAYS.find((d) => i >= d.start && i < d.start + d.n); }

function setIdx(i) {
  idx = Math.max(0, Math.min(META.times.length - 1, i));
  const d = dayOf(idx);
  $("#slot").max = d.n - 1;
  $("#slot").value = idx - d.start;
  document.querySelectorAll("#days button").forEach((b) => b.classList.toggle("on", DAYS[+b.dataset.k] === d));
  $("#tlabel").textContent = timeLabel(idx);
  $("#rdep").textContent = timeLabel(idx);
  loadState();
}
async function loadState() {
  const my = ++reqId;
  const st = await get(`/api/state?i=${idx}`);
  if (my !== reqId) return;
  STATE = st;
  renderReplay();
  if (ROUTE && $("#tab-route").classList.contains("on") && routeSel.src && routeSel.dst) planRoute();
  else renderRouteMap();
}

// ------------------------------------------------------------------ replay view
function levelKey() {
  if (hz === "now") return "now_level";
  return (showActual ? "a" : "f") + hz + "_level";
}
function renderReplay() {
  const key = levelKey();
  drawMap($("#map"), (id) => LEVEL_COLOR[STATE.roads[id][key]]);
  const what = hz === "now" ? "Recorded speed at this moment" : showActual ? `What was actually recorded ${hz} minutes later` : `Forecast for ${hz} minutes ahead (made at this moment)`;
  $("#maptitle").textContent = `${what}. Colours compare each road with its normal speed.`;
  // KPIs
  const S = STATE.summary;
  $("#kpis").innerHTML = [["now", "Now"], ["f15", "+15 min"], ["f30", "+30 min"], ["f60", "+60 min"]].map(([k, l]) => {
    const v = S[k], lv = levelOf(v);
    return `<div class="kpi"><div class="v" style="color:${lv === "none" ? "var(--mut)" : LEVEL_COLOR[lv]}">${pct(v)}</div><div class="l">${l}</div></div>`;
  }).join("") + `<div class="muted small" style="grid-column:1/-1">Average Outer Ring Road speed as % of normal (forecasts from the graph model).</div>`;
  // alerts
  const list = STATE.alerts.filter((a) => aFilter === "all" || String(a.h) === aFilter);
  $("#alertcount").textContent = `(${list.length})`;
  $("#alerts").innerHTML = list.length ? list.map((a) => {
    const chk = a.confirmed == null ? `<span class="chk">no reading later</span>` : a.confirmed ? `<span class="chk y">&#10003; happened</span>` : `<span class="chk n">&#10007; did not happen</span>`;
    return `<div class="alert"><span class="pill ${a.level}">+${a.h} min</span>
      <div><b>${a.label}</b>${a.new ? '<span class="tag">EARLY WARNING</span>' : ""}<div class="muted small">${a.dir}: ${LEVEL_TEXT[a.level].toLowerCase()}, ${f1(a.forecast)} km/h forecast (now ${f1(a.now)})</div></div>
      ${chk}</div>`;
  }).join("") : `<div class="muted" style="padding:8px 2px">No congestion forecast at this moment.</div>`;
  // table in corridor order
  const order = META.chains.flatMap((c) => c[1]);
  let t = `<tr><th>Stretch</th><th class="l">Road</th><th>Normal</th><th>Now</th>${H.map((h) => `<th>+${h} min forecast / actual</th>`).join("")}</tr>`;
  for (const id of order) {
    const r = roadById(id), d = STATE.roads[id];
    const cell = (v, lv) => `<span class="dot" style="background:${LEVEL_COLOR[lv]}"></span>${f1(v)}`;
    t += `<tr><td>${r.label}</td><td class="l muted">${r.road}</td><td>${f1(r.ref)}</td><td>${cell(d.now, d.now_level)}</td>` +
      H.map((h) => `<td>${cell(d["f" + h], d["f" + h + "_level"])} <span class="muted">/ ${f1(d["a" + h])}</span></td>`).join("") + "</tr>";
  }
  $("#roadtable").innerHTML = t;
}

// ------------------------------------------------------------------ route planner
function fillRouteForm() {
  const order = META.chains.flatMap((c) => c[1]);
  const opts = order.map((id) => { const r = roadById(id); return `<option value="${id}">${r.label} · ${r.road}</option>`; }).join("");
  $("#src").innerHTML = opts; $("#dst").innerHTML = opts;
  const presets = Object.entries(META.trip_presets);
  const presetText = (ids) => { const a = roadById(ids[0]), z = roadById(ids[ids.length - 1]);
    const km = ids.reduce((t, id) => t + roadById(id).km, 0);
    return `${a.label} &rarr; ${z.label} &middot; ${a.road} (${km.toFixed(1)} km)`; };
  $("#presets").innerHTML = presets.map(([name, ids], k) => `<button class="btn" data-k="${k}" title="${name}">${presetText(ids)}</button>`).join("");
  $("#presets").onclick = (e) => {
    const b = e.target.closest("button"); if (!b) return;
    const ids = presets[+b.dataset.k][1];
    setRoute(ids[0], ids[ids.length - 1]); planRoute();
  };
  setRoute(presets[0][1][0], presets[0][1][presets[0][1].length - 1]);
  $("#src").onchange = () => setRoute($("#src").value, routeSel.dst);
  $("#dst").onchange = () => setRoute(routeSel.src, $("#dst").value);
  $("#plan").onclick = planRoute;
  let clickStep = 0;
  $("#rmap").addEventListener("click", (e) => {
    const el = e.target.closest("[data-id]"); if (!el) return;
    if (clickStep === 0) { setRoute(el.dataset.id, routeSel.dst); clickStep = 1; }
    else { setRoute(routeSel.src, el.dataset.id); clickStep = 0; planRoute(); }
  });
}
function setRoute(src, dst) {
  routeSel = { src, dst }; ROUTE = null;
  $("#src").value = src; $("#dst").value = dst;
  $("#rout").innerHTML = "";
  renderRouteMap();
}
function renderRouteMap() {
  if (!STATE || !META) return;
  const overlay = [];
  if (ROUTE && !ROUTE.error) {
    if (!ROUTE.same_path) overlay.push([ROUTE.live.path.map((p) => p.id), "var(--live)", 5, true]);
    overlay.push([ROUTE.forecast.path.map((p) => p.id), "var(--route)", 6.5, false]);
  } else overlay.push([[routeSel.src, routeSel.dst].filter(Boolean), "var(--route)", 6.5, false]);
  drawMap($("#rmap"), (id) => LEVEL_COLOR[STATE.roads[id].f15_level], overlay);
}
async function planRoute() {
  if (!routeSel.src || !routeSel.dst) return;
  const R = await get(`/api/route?src=${routeSel.src}&dst=${routeSel.dst}&i=${idx}`);
  ROUTE = R;
  renderRouteMap();
  if (R.error) { $("#rout").innerHTML = `<div class="card err">${R.error}</div>`; return; }
  const F = R.forecast, L = R.live;
  const pathText = (p) => p.path.map((x) => x.label).join(" &rarr; ");
  const act = (v) => (v == null ? `<span class="muted">not recorded</span>` : `<b>${f1(v)} min</b>`);
  let verdict;
  if (R.same_path) {
    const ok = F.actual_minutes != null && F.minutes != null && L.minutes != null;
    verdict = ok ? `Both pick the same roads here. The forecast's travel-time estimate was ${Math.abs(F.minutes - F.actual_minutes) <= Math.abs(L.minutes - L.actual_minutes) ? "closer to" : "further from"} what was recorded (forecast ${f1(F.minutes)}, live map ${f1(L.minutes)}, recorded ${f1(F.actual_minutes)} min).`
      : "Both pick the same roads here.";
  } else {
    verdict = F.actual_minutes != null && L.actual_minutes != null
      ? `Different routes. Recorded time: forecast route ${f1(F.actual_minutes)} min, live-map route ${f1(L.actual_minutes)} min.`
      : "Different routes; recorded trip times are not available for both.";
  }
  $("#rout").innerHTML = `
    <div class="card">
      <div class="rcard fc"><div class="muted small">Fastest route on the forecast (time-dependent Dijkstra)</div>
        <div class="big">${f1(F.minutes)} min</div><div class="small">${F.km} km &middot; recorded trip time on this route: ${act(F.actual_minutes)}</div>
        <div class="path">${pathText(F)}</div>${F.assumed_link ? '<div class="small err">Includes one assumed link (Hosur Rd to Varthur Rd) that the readings do not cover.</div>' : ""}</div>
      <div class="rcard"><div class="muted small">Route a live map would pick (current speeds held constant)</div>
        <div class="big" style="color:var(--mut)">${f1(L.minutes)} min</div><div class="small">${L.km} km &middot; recorded: ${act(L.actual_minutes)}</div>
        <div class="path">${pathText(L)}</div></div>
      <div class="small">${verdict}</div>
      ${R.notes.length ? `<div class="muted small" style="margin-top:6px">${R.notes.join("<br>")}</div>` : ""}
      <div class="muted small" style="margin-top:6px">API: <code>/api/route?src=${R.src}&amp;dst=${R.dst}&amp;i=${R.i}</code></div>
    </div>`;
}

// ------------------------------------------------------------------ models + how it works
function renderModels() {
  let t = `<table><tr><th>Model</th>${RES.horizons.map((h) => `<th class="l">+${h} min</th>`).join("")}</tr>`;
  let grp = "";
  for (const m of RES.models) {
    if (m.group !== grp) { grp = m.group; t += `<tr class="grp"><td colspan="4">${grp}</td></tr>`; }
    t += `<tr class="${m.used ? "used" : ""}"><td>${m.name}${m.used ? ' <span class="tag">USED BY THE APP</span>' : ""}</td>` +
      m.mae.map((v) => `<td class="l"><span class="bar" style="width:${Math.round((v / 4.5) * 120)}px"></span>${v.toFixed(2)}</td>`).join("") + "</tr>";
  }
  $("#mtable").innerHTML = t + "</table>";
  $("#msrc").textContent = "Source: " + RES.source;
  const A = META.accuracy;
  $("#acc").innerHTML = `<table><tr><th>Horizon</th><th>Forecast</th><th>Same as now</th><th>Rows</th></tr>` +
    H.map((h) => `<tr><td>+${h} min</td><td><b>${A[h].forecast}</b></td><td>${A[h].same_as_now}</td><td>${A[h].rows}</td></tr>`).join("") +
    `</table><div class="muted small" style="margin-top:6px">MAE in km/h, computed by the app on ${META.meta.window[0]} to ${META.meta.window[1]}. The app averages the 5 training runs, so it is slightly lower than the per-run average in the table above.</div>`;
  $("#alerttable").innerHTML = `<table><tr><th>Alert when</th><th>Horizon</th><th>Current speed</th><th>Forecast</th></tr>` +
    RES.alerts.map((a) => `<tr><td>&lt; ${a.threshold} &times; normal</td><td>+${a.h} min</td><td>${a.current.toFixed(2)}</td><td><b>${a.forecast.toFixed(2)}</b></td></tr>`).join("") + "</table>";
  $("#triptable").innerHTML = `<table><tr><th>Trip</th><th>Live map</th><th>History</th><th>Forecast</th></tr>` +
    RES.trips.map((x) => `<tr><td class="l" style="white-space:normal">${x.trip}<div class="muted small">${x.departures} departures, mean ${x.actual_mean} min</div></td><td>${x.current}</td><td>${x.historical}</td><td><b>${x.forecast}</b></td></tr>`).join("") + "</table>";
  $("#mnotes").innerHTML = RES.notes.map((n) => `<li>${n}</li>`).join("") +
    `<li>METR-LA benchmark (Los Angeles), our STID: ${RES.metrla.stid.join(" / ")} km/h at 15 / 30 / 60 min; the Graph WaveNet paper reports ${RES.metrla.graph_wavenet_paper.join(" / ")}.</li>`;
}
function renderHow() {
  const steps = [
    ["Collect", "TomTom speeds on 21 stretches and Open-Meteo weather, every 15 min in rush hours (GitHub Actions or run_local.py)."],
    ["Road graph", "Stretches linked by flow links and junction crossings."],
    ["Pre-process", "15-min grid, missing readings masked, speed divided by each road's normal speed."],
    ["Forecast", "Graph Convolutional Network with the road graph, tuned, 5 training runs averaged: +15, +30, +60 min."],
    ["Compare", "Persistence, Historical Average, Gradient Boosting, GCN variants, Graph WaveNet, STID, pretrained STID."],
    ["Decide", "Alerts below 75% / 60% of normal speed; trip times; time-dependent Dijkstra route."],
    ["Show", "This app: local server with a JSON API and this page."],
  ];
  $("#flow").innerHTML = steps.map(([b, d], k) => `<div class="step"><div class="n">${k + 1}</div><b>${b}</b><div>${d}</div></div>`).join("");
  $("#where").innerHTML = [
    "<b>This computer:</b> a Python server (standard library only), this page and a data bundle. No internet is used.",
    `<b>Built beforehand:</b> forecasts of the tuned graph model for every 15-minute slot of ${META.meta.window[0]} to ${META.meta.window[1]}, plus what was actually recorded (bundle built ${META.meta.built}).`,
    "<b>Online only:</b> the data collector (TomTom and Open-Meteo need the internet). With fresh data, rebuild the bundle with app/build_bundle.py.",
    "<b>API:</b> /api/meta, /api/state?i=slot, /api/route?src=&amp;dst=&amp;i=, /api/results.",
  ].map((x) => `<li>${x}</li>`).join("");
  $("#limits").innerHTML = [
    "This is a replay of recorded days, not live traffic.",
    "One corridor and one test week; results are indicative.",
    "The road graph has one real detour (Hosur Rd to Varthur Rd, with one assumed link), so the planner usually keeps to the Outer Ring Road.",
    "Raw readings are TomTom data and are not published; only aggregate results are shared.",
  ].map((x) => `<li>${x}</li>`).join("");
}

// ------------------------------------------------------------------ wiring
function bind() {
  document.querySelectorAll("#tabs button").forEach((b) => (b.onclick = () => {
    document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x === b));
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.id === "tab-" + b.dataset.tab));
    $("#clock").style.display = b.dataset.tab === "models" || b.dataset.tab === "how" ? "none" : "";
    if (b.dataset.tab === "route") renderRouteMap();
  }));
  $("#hseg").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; hz = b.dataset.h;
    document.querySelectorAll("#hseg button").forEach((x) => x.classList.toggle("on", x === b)); renderReplay(); };
  $("#aseg").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; aFilter = b.dataset.a;
    document.querySelectorAll("#aseg button").forEach((x) => x.classList.toggle("on", x === b)); renderReplay(); };
  $("#showActual").onchange = (e) => { showActual = e.target.checked; renderReplay(); };
  $("#slot").oninput = (e) => setIdx(dayOf(idx).start + +e.target.value);
  $("#play").onclick = () => {
    if (playing) { clearInterval(playing); playing = null; $("#play").innerHTML = "&#9654;"; return; }
    $("#play").innerHTML = "&#10074;&#10074;";
    playing = setInterval(() => setIdx(idx + 1 < META.times.length ? idx + 1 : 0), 900);
  };
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "SELECT" || e.target.tagName === "INPUT" && e.target.type !== "range") return;
    if (e.key === "ArrowRight") setIdx(idx + 1);
    if (e.key === "ArrowLeft") setIdx(idx - 1);
  });
  attachTip($("#map"), roadTip);
  attachTip($("#rmap"), roadTip);
}

(async function init() {
  [META, RES] = await Promise.all([get("/api/meta"), get("/api/results")]);
  GEO = buildGeometry();
  buildDays();
  fillRouteForm();
  renderModels();
  renderHow();
  bind();
  const latest = META.meta.mode === "latest";
  const last = META.times[META.times.length - 1].replace("T", " ");
  $("#badge").textContent = latest ? `Forecasts from recorded data up to ${last}` : `Offline replay · recorded ${META.meta.window[0]} to ${META.meta.window[1]}`;
  $("#foot").textContent = latest
    ? `Recorded TomTom data from ${META.meta.window[0]} up to ${last}. At the latest reading the forecasts look into the future, so there is no recorded value to compare yet. Forecasts: ${META.meta.model}. Bundle built ${META.meta.built}.`
    : `Replay of recorded TomTom data, ${META.meta.window[0]} to ${META.meta.window[1]}. Forecasts: ${META.meta.model}. Bundle built ${META.meta.built}. Not live traffic.`;
  const start = latest ? META.times.length - 1 : META.times.findIndex((t, i) => t.endsWith("T18:07") && META.daytype[i] === "weekday");
  setIdx(start >= 0 ? start : 0);
})();
