"use strict";
// Bengaluru ORR Traffic Intelligence: front end. Talks only to the local FastAPI backend (/api/...).

const $ = (q) => document.querySelector(q);
const $$ = (q) => Array.from(document.querySelectorAll(q));
const H = [15, 30, 60];
const S = {
  mode: "live", horizon: 0, cmp: false, net: null, road: {}, ids: [], snap: null, status: null, results: null,
  days: [], day: null, timeline: [], playing: false, speed: 2, selected: null, route: null, pick: null, alertH: 0,
  serverOffset: 0, theme: "dark", seriesKey: null, fps: 0,
};
const LOG = [];

// ------------------------------------------------------------------ API
async function api(path, opt = {}) {
  const t0 = performance.now();
  let r;
  try { r = await fetch(path, opt); } catch (e) { logApi(opt.method || "GET", path, "ERR", performance.now() - t0, null); throw e; }
  logApi(opt.method || "GET", path, r.status, performance.now() - t0, r.headers.get("X-Process-Ms"));
  if (!r.ok) { let m = r.status; try { m = (await r.json()).detail || m; } catch (e) { /* not json */ } throw new Error(m); }
  return r.json();
}
function logApi(method, path, status, ms, server) {
  LOG.unshift({ method, path, status, ms: Math.round(ms), server });
  LOG.length = Math.min(LOG.length, 12);
  if ($("#p-system").classList.contains("on")) renderLog();
}
function renderLog() {
  $("#apilog").innerHTML = LOG.map((x) => `<div><span title="${x.path}">${x.method} ${x.path.length > 44 ? x.path.slice(0, 44) + "…" : x.path}</span>` +
    `<span class="${String(x.status)[0] === "2" ? "s2" : "s4"}">${x.status}</span><span>${x.server ? x.server + " ms" : x.ms + " ms"}</span></div>`).join("");
}

// ------------------------------------------------------------------ helpers
const STOPS = [[0.35, [179, 19, 43]], [0.6, [239, 68, 68]], [0.75, [245, 158, 11]], [0.9, [163, 230, 53]], [1.0, [34, 197, 94]]];
function rgb(r) {
  if (r == null || isNaN(r)) return [100, 116, 139];
  r = Math.max(0.35, Math.min(1, r));
  for (let k = 1; k < STOPS.length; k++) {
    if (r <= STOPS[k][0]) {
      const [r0, c0] = STOPS[k - 1], [r1, c1] = STOPS[k], f = (r - r0) / (r1 - r0);
      return c0.map((v, j) => Math.round(v + (c1[j] - v) * f));
    }
  }
  return STOPS[STOPS.length - 1][1];
}
const col = (r, a = 1) => { const c = rgb(r); return `rgba(${c[0]},${c[1]},${c[2]},${a})`; };
const pct = (r) => (r == null ? "–" : Math.round(r * 100) + "%");
const kmh = (v) => (v == null ? "–" : v.toFixed(0));
const lvl = (r) => (r == null ? "none" : r < 0.6 ? "severe" : r < 0.75 ? "slow" : "free");
const LVL = { severe: "congested", slow: "slow", free: "free flowing", none: "no reading" };
const hhmm = (iso) => iso.slice(11, 16);
const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function dayLabel(iso) { const [y, m, d] = iso.slice(0, 10).split("-").map(Number); return `${WD[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]} ${d} ${MON[m - 1]}`; }
function addMin(iso, m) { const d = new Date(iso + ":00Z"); d.setUTCMinutes(d.getUTCMinutes() + m); return d.toISOString().slice(0, 16); }
function minutesBetween(a, b) { return Math.round((new Date(b.replace(" ", "T") + "Z") - new Date(a.replace(" ", "T") + "Z")) / 60000); }
function ago(m) { if (m == null) return ""; if (m < 1) return "just now"; if (m < 60) return `${m} min ago`; const h = Math.floor(m / 60); return `${h} h ${m % 60} min ago`; }
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), 3200); }
function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

// ------------------------------------------------------------------ map
const map = L.map("map", { zoomControl: false, attributionControl: true, zoomSnap: 0.25 }).setView([12.95, 77.67], 13);
L.control.zoom({ position: "bottomright" }).addTo(map);
let tiles = null, tileOK = 0, tileErr = 0, tilesOffline = false;
function setTiles() {
  if (tiles) map.removeLayer(tiles);
  if (tilesOffline) return;
  const style = S.theme === "dark" ? "dark_all" : "light_all";
  tiles = L.tileLayer(`https://{s}.basemaps.cartocdn.com/${style}/{z}/{x}/{y}{r}.png`,
    { subdomains: "abcd", maxZoom: 19, attribution: "© OpenStreetMap contributors © CARTO" });
  tiles.on("tileload", () => { tileOK++; geoNote(); });
  tiles.on("tileerror", () => {
    tileErr++;
    if (tileErr >= 4 && tileOK === 0) { tilesOffline = true; map.removeLayer(tiles); $("#map").classList.add("offline-grid"); geoNote(); }
  });
  tiles.addTo(map);
}
function geoNote() {
  if (!S.net) return;
  const g = S.net.geometry;
  const shape = g.exact === g.total ? "exact road shapes (TomTom)" : g.exact ? `${g.exact} of ${g.total} exact road shapes` : "approximate road shapes (start, middle and end of each stretch)";
  $("#geoNote").textContent = (tilesOffline ? "Map tiles offline · " : "") + shape;
}

// ------------------------------------------------------------------ canvas: roads, connections, moving traffic
const cv = $("#fx"), ctx = cv.getContext("2d");
let CW = 0, CH = 0;
function resize() {
  const r = $(".mapwrap").getBoundingClientRect(), d = window.devicePixelRatio || 1;
  CW = r.width; CH = r.height; cv.width = CW * d; cv.height = CH * d; cv.style.width = CW + "px"; cv.style.height = CH + "px";
  ctx.setTransform(d, 0, 0, d, 0, 0);
  drawStrip();
}
window.addEventListener("resize", () => { resize(); map.invalidateSize(); });

const DISP = {};           // displayed ratio / speed per road (eased towards the target)
const PART = {};           // moving dots per road
let SCR = {};              // screen geometry per road, rebuilt every frame
function offsetLine(p, d) {
  const n = p.length, out = [];
  for (let i = 0; i < n; i++) {
    const a = p[Math.max(0, i - 1)], b = p[Math.min(n - 1, i + 1)];
    let dx = b.x - a.x, dy = b.y - a.y; const L = Math.hypot(dx, dy) || 1; dx /= L; dy /= L;
    out.push({ x: p[i].x + dy * d, y: p[i].y - dx * d });   // left of the travel direction (India drives on the left)
  }
  return out;
}
function measure(p) { const c = [0]; for (let i = 1; i < p.length; i++) c.push(c[i - 1] + Math.hypot(p[i].x - p[i - 1].x, p[i].y - p[i - 1].y)); return c; }
function at(g, s) {
  const c = g.cum; if (s <= 0) return g.pts[0];
  for (let i = 1; i < c.length; i++) if (s <= c[i]) { const f = (s - c[i - 1]) / ((c[i] - c[i - 1]) || 1), a = g.pts[i - 1], b = g.pts[i]; return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f }; }
  return g.pts[g.pts.length - 1];
}
function target(r) {
  const d = S.snap && S.snap.roads[r];
  if (!d) return { ratio: null, kmh: null };
  if (S.horizon === 0) return { ratio: d.now_ratio, kmh: d.now };
  const h = S.horizon;
  if (S.cmp && S.mode === "lapse") return { ratio: d[`a${h}`] == null ? null : d[`a${h}`] / d.ref, kmh: d[`a${h}`] };
  return { ratio: d[`r${h}`], kmh: d[`f${h}`] };
}
function roadWidth() { return Math.max(3, Math.min(10, 3 + (map.getZoom() - 12) * 1.7)); }
function pathOf(g, ctx2) { ctx2.beginPath(); g.pts.forEach((p, i) => (i ? ctx2.lineTo(p.x, p.y) : ctx2.moveTo(p.x, p.y))); }

let lastT = performance.now(), frames = 0, fpsT = performance.now();
function frame(now) {
  const dt = Math.min(0.1, (now - lastT) / 1000); lastT = now;
  frames++; if (now - fpsT > 1000) { S.fps = frames; frames = 0; fpsT = now; }
  ctx.clearRect(0, 0, CW, CH);
  if (S.net) {
    const w = roadWidth(), off = w * 0.75 + 1.5, dark = S.theme === "dark";
    SCR = {};
    for (const r of S.ids) {
      const raw = S.road[r].latlngs.map((ll) => map.latLngToContainerPoint(ll));
      const pts = offsetLine(raw, off), cum = measure(pts);
      const km = S.road[r].km || 1;
      SCR[r] = { pts, cum, len: cum[cum.length - 1], pxPerKm: cum[cum.length - 1] / km };
      const t = target(r), d = DISP[r] || (DISP[r] = { ratio: t.ratio, kmh: t.kmh });
      const k = Math.min(1, dt * 3.5);
      if (t.ratio == null) { d.ratio = null; d.kmh = null; } else { d.ratio = d.ratio == null ? t.ratio : d.ratio + (t.ratio - d.ratio) * k; d.kmh = d.kmh == null ? t.kmh : d.kmh + (t.kmh - d.kmh) * k; }
    }
    // route underlay
    const routeIds = S.route ? S.route.forecast : [];
    for (const r of routeIds) { if (!SCR[r]) continue; pathOf(SCR[r], ctx); ctx.lineWidth = w + 12; ctx.strokeStyle = "rgba(91,140,255,.35)"; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.stroke(); }
    // roads
    const pulse = 0.5 + 0.5 * Math.sin(now / 260);
    for (const r of S.ids) {
      const g = SCR[r], d = DISP[r];
      pathOf(g, ctx); ctx.lineCap = "round"; ctx.lineJoin = "round";
      ctx.lineWidth = w + 3; ctx.strokeStyle = dark ? "rgba(0,0,0,.55)" : "rgba(255,255,255,.9)"; ctx.stroke();
      if (lvl(d.ratio) === "severe") { ctx.save(); ctx.shadowColor = "rgba(239,68,68,.9)"; ctx.shadowBlur = 8 + 10 * pulse; ctx.lineWidth = w; ctx.strokeStyle = col(d.ratio); ctx.stroke(); ctx.restore(); }
      pathOf(g, ctx); ctx.lineWidth = w; ctx.strokeStyle = col(d.ratio, d.ratio == null ? 0.6 : 1); ctx.stroke();
    }
    // selected road and its connections
    if (S.selected && SCR[S.selected]) {
      const sel = S.road[S.selected];
      const dash = (ids, color) => { for (const r of ids) { if (!SCR[r]) continue; pathOf(SCR[r], ctx); ctx.setLineDash([10, 8]); ctx.lineDashOffset = -now / 40; ctx.lineWidth = w + 5; ctx.strokeStyle = color; ctx.stroke(); ctx.setLineDash([]); } };
      dash(sel.downstream.map((x) => x.id), "rgba(34,211,238,.85)");
      dash(sel.upstream, "rgba(167,139,250,.85)");
      pathOf(SCR[S.selected], ctx); ctx.lineWidth = w + 7; ctx.strokeStyle = dark ? "rgba(255,255,255,.95)" : "rgba(20,32,51,.85)"; ctx.stroke();
      pathOf(SCR[S.selected], ctx); ctx.lineWidth = w; ctx.strokeStyle = col(DISP[S.selected].ratio); ctx.stroke();
    }
    // connection points (where one stretch flows into the next)
    for (const l of S.net.links) {
      if (l.kind !== "flow") continue;
      const p = map.latLngToContainerPoint([l.lat, l.lon]);
      const hot = S.selected && (l.src === S.selected || l.dst === S.selected);
      ctx.beginPath(); ctx.arc(p.x, p.y, hot ? 5 : 2.6, 0, 7);
      ctx.fillStyle = hot ? "#22d3ee" : dark ? "rgba(230,235,245,.75)" : "rgba(20,32,51,.6)"; ctx.fill();
    }
    // moving traffic
    ctx.save();
    if (dark) ctx.globalCompositeOperation = "lighter";
    for (const r of S.ids) {
      const g = SCR[r], d = DISP[r]; if (d.ratio == null || g.len < 8) { PART[r] = []; continue; }
      const spacing = 14 + 30 * Math.max(0.3, Math.min(1.1, d.ratio));
      const want = Math.max(1, Math.min(160, Math.round(g.len / spacing)));
      const P = PART[r] || (PART[r] = []);
      while (P.length < want) P.push({ s: Math.random() * g.len, j: (Math.random() - 0.5) * 2 });
      if (P.length > want) P.length = want;
      const v = (d.kmh || 0) * g.pxPerKm / 3600 * 75;   // 1 s on screen = 75 s of driving
      const c = rgb(d.ratio);
      for (const p of P) {
        p.s += v * dt; if (p.s > g.len) p.s -= g.len;
        const a = at(g, p.s), b = at(g, Math.max(0, p.s - 7));
        ctx.beginPath(); ctx.moveTo(b.x, b.y); ctx.lineTo(a.x, a.y);
        ctx.strokeStyle = `rgba(${c[0]},${c[1]},${c[2]},.55)`; ctx.lineWidth = 2; ctx.stroke();
        ctx.beginPath(); ctx.arc(a.x, a.y, 1.9, 0, 7); ctx.fillStyle = dark ? "rgba(255,255,255,.95)" : "rgba(15,23,42,.85)"; ctx.fill();
      }
    }
    ctx.restore();
    // place names
    ctx.font = "600 12px Segoe UI, system-ui, sans-serif"; ctx.textAlign = "center";
    const done = new Set(), boxes = [];
    for (const r of S.ids) {
      const name = S.road[r].label; if (name.includes(" to ") || done.has(name) || S.road[r].route === "orr_cw") continue; done.add(name);
      const g = SCR[r], p = at(g, g.len / 2), tw = ctx.measureText(name).width;
      const box = { x0: p.x - tw / 2 - 4, x1: p.x + tw / 2 + 4, y0: p.y - 26, y1: p.y - 6 };
      if (boxes.some((b) => box.x0 < b.x1 && box.x1 > b.x0 && box.y0 < b.y1 && box.y1 > b.y0)) continue;
      boxes.push(box);
      ctx.lineWidth = 3.5; ctx.strokeStyle = dark ? "rgba(11,16,32,.9)" : "rgba(255,255,255,.95)"; ctx.strokeText(name, p.x, p.y - 12);
      ctx.fillStyle = dark ? "#e6ebf5" : "#142033"; ctx.fillText(name, p.x, p.y - 12);
    }
    // the car on the planned route
    if (S.route && S.route.forecast.length) {
      const segs = S.route.forecast.map((r) => SCR[r]).filter(Boolean), total = segs.reduce((a, g) => a + g.len, 0);
      S.route.s = ((S.route.s || 0) + dt * Math.max(60, total / 6)) % (total || 1);
      let s = S.route.s, p = null;
      for (const g of segs) { if (s <= g.len) { p = at(g, s); break; } s -= g.len; }
      if (p) { ctx.save(); ctx.shadowColor = "#5b8cff"; ctx.shadowBlur = 16; ctx.beginPath(); ctx.arc(p.x, p.y, 7, 0, 7); ctx.fillStyle = "#5b8cff"; ctx.fill(); ctx.restore();
        ctx.beginPath(); ctx.arc(p.x, p.y, 3, 0, 7); ctx.fillStyle = "#fff"; ctx.fill(); }
    }
  }
  requestAnimationFrame(frame);
}

// hover and click on roads
function nearest(pt) {
  let best = null, bd = 12;
  for (const r of S.ids) {
    const g = SCR[r]; if (!g) continue;
    for (let i = 1; i < g.pts.length; i++) {
      const a = g.pts[i - 1], b = g.pts[i], dx = b.x - a.x, dy = b.y - a.y, L2 = dx * dx + dy * dy || 1;
      const t = Math.max(0, Math.min(1, ((pt.x - a.x) * dx + (pt.y - a.y) * dy) / L2));
      const d = Math.hypot(pt.x - a.x - t * dx, pt.y - a.y - t * dy);
      if (d < bd) { bd = d; best = r; }
    }
  }
  return best;
}
map.on("mousemove", (e) => {
  const r = nearest(e.containerPoint), tip = $("#tip");
  $("#map").style.cursor = r ? "pointer" : "";
  if (!r || !S.snap) { tip.style.display = "none"; return; }
  const d = S.snap.roads[r], m = S.road[r], h = S.horizon;
  const line = h ? `<div>Forecast +${h} min: <b>${kmh(d[`f${h}`])} km/h</b> (${pct(d[`r${h}`])})</div>` +
    (d[`a${h}`] != null ? `<div class="muted">What happened: ${kmh(d[`a${h}`])} km/h</div>` : "") : "";
  tip.innerHTML = `<b>${esc(m.label)}</b> <span class="muted">· ${esc(m.road)}</span><div>Now: <b>${kmh(d.now)} km/h</b> (${pct(d.now_ratio)} of normal ${kmh(d.ref)})${d.age ? ` <span class="muted">· reading ${d.age} min old</span>` : ""}</div>${line}<div class="muted small">${m.km} km · click for details</div>`;
  tip.style.display = "block";
  tip.style.left = Math.min(e.containerPoint.x + 16, CW - 260) + "px"; tip.style.top = Math.max(8, e.containerPoint.y - 10) + "px";
});
map.on("mouseout", () => { $("#tip").style.display = "none"; });
map.on("click", (e) => {
  const r = nearest(e.containerPoint); if (!r) return;
  if (S.pick) { $(S.pick === "src" ? "#rsrc" : "#rdst").value = r; if (S.pick === "src") { S.pick = "dst"; $("#pickHint").textContent = "Now click the destination road."; } else { S.pick = null; $("#pickBtn").classList.remove("armed"); $("#pickHint").textContent = ""; plan(); } return; }
  selectRoad(r, true);
});

// ------------------------------------------------------------------ panels
function renderCards() {
  const sn = S.snap; if (!sn) return;
  const sm = sn.summary, items = [["Now", sm.now, 0], ["+15 min", sm.r15, 15], ["+30 min", sm.r30, 30], ["+60 min", sm.r60, 60]];
  $("#cards").innerHTML = items.map(([l, v, h]) => `<div class="kpi ${S.horizon === h ? "sel" : ""}" data-h="${h}"><div class="v" style="color:${col(v)}">${pct(v)}</div><div class="l">${l}</div><div class="b">${h ? "forecast" : "recorded"}</div></div>`).join("");
  $$("#cards .kpi").forEach((k) => (k.onclick = () => setHorizon(+k.dataset.h)));
}
function renderAlerts() {
  const sn = S.snap; if (!sn) return;
  const list = sn.alerts.filter((a) => !S.alertH || a.h === S.alertH);
  $("#alertCount").textContent = list.length;
  $("#alerts").innerHTML = list.length ? list.map((a) => {
    const res = a.confirmed === true ? `<span class="ok">✓ happened</span>` : a.confirmed === false ? `<span class="no">did not happen</span>` : a.actual == null && S.snap.latest ? `<span class="no">in the future</span>` : "";
    return `<div class="al" data-r="${a.road}"><div class="hb ${a.level}">+${a.h}<br>min</div><div><div class="t">${esc(a.label)} ${a.early ? '<span class="tag">EARLY WARNING</span>' : ""}</div>` +
      `<div class="d">${esc(a.dir)} · ${LVL[a.level]} · ${kmh(a.forecast)} km/h forecast (now ${kmh(a.now)})</div></div><div>${res}</div></div>`;
  }).join("") : `<div class="muted small">No road is forecast to be slow or congested at these horizons.</div>`;
  $$("#alerts .al").forEach((x) => (x.onclick = () => selectRoad(x.dataset.r, true)));
}
function renderModelLine() {
  const sn = S.snap; if (!sn) return;
  $("#modelLine").innerHTML = `Forecasts computed now by <b>${sn.model_runs} trained Graph Convolutional Networks</b> (3 horizons × 5 training runs) in <b>${sn.model_ms} ms</b>, from the readings up to ${hhmm(sn.time)} only.`;
}
function renderWatermark() {
  const sn = S.snap; if (!sn) return;
  const head = S.mode === "live" ? (sn.latest ? "LIVE" : "LIVE (older reading)") : "TIME-LAPSE";
  const when = `${dayLabel(sn.time)} ${hhmm(sn.time)}`;
  const h = S.horizon;
  $("#watermark").innerHTML = h
    ? `${head} · ${S.cmp && S.mode === "lapse" ? "WHAT HAPPENED" : "FORECAST"} +${h} MIN<span class="sub">for ${hhmm(addMin(sn.time, h))}, made from data up to ${when}</span>`
    : `${head} · ${when}<span class="sub">${sn.daytype === "weekday" ? "weekday" : "weekend / holiday"}</span>`;
}

// corridor / road chart (SVG)
function chartSVG(sr, el, height = 190) {
  const W = el.clientWidth || 380, Hh = height, padL = 34, padR = 10, padT = 10, padB = 22;
  const pts = sr.past.map((p) => ({ t: p[0], v: p[1] }));
  if (!pts.length && !sr.forecast.length) { el.innerHTML = `<div class="muted small">No readings in this period.</div>`; return; }
  const t0 = new Date((pts.length ? pts[0].t : sr.time) + ":00Z").getTime(), t1 = new Date(sr.forecast[sr.forecast.length - 1].t + ":00Z").getTime();
  const X = (iso) => padL + (new Date(iso + ":00Z").getTime() - t0) / ((t1 - t0) || 1) * (W - padL - padR);
  const vals = pts.map((p) => p.v).concat(sr.forecast.flatMap((f) => [f.lo, f.hi]));
  const lo = Math.max(0.2, Math.min(0.5, Math.min(...vals) - 0.05)), hi = Math.max(1.05, Math.max(...vals) + 0.03);
  const Y = (v) => padT + (hi - v) / (hi - lo) * (Hh - padT - padB);
  let g = "";
  for (const v of [0.6, 0.75, 1.0]) if (v >= lo && v <= hi) g += `<line class="ax" x1="${padL}" x2="${W - padR}" y1="${Y(v)}" y2="${Y(v)}" stroke-dasharray="${v === 1 ? "" : "3 3"}"/><text x="${padL - 4}" y="${Y(v) + 3}" text-anchor="end">${Math.round(v * 100)}%</text>`;
  const nowX = X(sr.time);
  for (let k = 0; k < 6; k++) { const iso = addMin(sr.time, -60 * k); if (X(iso) >= padL) g += `<text x="${X(iso)}" y="${Hh - 6}" text-anchor="middle">${hhmm(iso)}</text>`; }
  const band = [{ t: sr.time, lo: null, hi: null }].concat(sr.forecast);
  const lastV = pts.length ? pts[pts.length - 1].v : sr.forecast[0].mean;
  const up = band.map((f) => `${X(f.t)},${Y(f.hi == null ? lastV : f.hi)}`), dn = band.slice().reverse().map((f) => `${X(f.t)},${Y(f.lo == null ? lastV : f.lo)}`);
  g += `<polygon points="${up.concat(dn).join(" ")}" fill="rgba(91,140,255,.18)"/>`;
  if (pts.length) g += `<polyline points="${pts.map((p) => `${X(p.t)},${Y(p.v)}`).join(" ")}" fill="none" stroke="${col(lastV)}" stroke-width="2.4"/>`;
  g += `<polyline points="${[`${nowX},${Y(lastV)}`].concat(sr.forecast.map((f) => `${X(f.t)},${Y(f.mean)}`)).join(" ")}" fill="none" stroke="#5b8cff" stroke-width="2.4" stroke-dasharray="6 4"/>`;
  for (const f of sr.forecast) {
    g += `<circle cx="${X(f.t)}" cy="${Y(f.mean)}" r="3.5" fill="#5b8cff"/>`;
    if (f.actual != null) g += `<circle cx="${X(f.t)}" cy="${Y(f.actual)}" r="4" fill="none" stroke="${col(f.actual)}" stroke-width="2"/>`;
  }
  g += `<line x1="${nowX}" x2="${nowX}" y1="${padT}" y2="${Hh - padB}" stroke="currentColor" opacity=".5"/><text x="${nowX}" y="${padT + 8}" text-anchor="middle" style="fill:currentColor">now</text>`;
  el.innerHTML = `<svg viewBox="0 0 ${W} ${Hh}" preserveAspectRatio="none">${g}</svg>`;
}
async function loadSeries() {
  if (!S.snap) return;
  const key = S.snap.time;
  if (S.seriesKey === key) return;
  S.seriesKey = key;
  const sr = await api(`/api/series?t=${encodeURIComponent(key)}&hours=6`);
  if (S.seriesKey !== key) return;
  chartSVG(sr, $("#chart"));
  $("#chartNote").textContent = "· line: recorded · dashed: model · band: range of 5 runs · rings: what happened";
}

// road panel
async function selectRoad(r, openTab) {
  S.selected = r;
  if (openTab) setTab("road");
  const g = S.road[r];
  if (openTab && g.latlngs.length) map.fitBounds(L.latLngBounds(g.latlngs).pad(0.8), { maxZoom: 15, animate: true });
  renderRoad();
}
async function renderRoad() {
  const r = S.selected; if (!r || !S.snap) return;
  const d = S.snap.roads[r], m = S.road[r];
  const fc = H.map((h) => {
    const w = Math.min(100, (d[`r${h}`] || 0) / 1.1 * 100), a = d[`a${h}`];
    return `<div class="fcrow"><span>+${h} min</span><div class="bar"><i style="width:${w}%;background:${col(d[`r${h}`])}"></i>${a != null ? `<u style="left:${Math.min(100, a / d.ref / 1.1 * 100)}%" title="what happened"></u>` : ""}</div>` +
      `<span><b>${kmh(d[`f${h}`])}</b> km/h <span class="muted small">${kmh(d[`lo${h}`])}–${kmh(d[`hi${h}`])}</span></span></div>`;
  }).join("");
  const chip = (id, cls, extra = "") => `<span class="chip ${cls}" data-r="${id}">${esc(S.road[id].label)} <span class="muted">${esc(S.road[id].road)}</span>${extra}</span>`;
  $("#road").innerHTML = `<div class="card"><div class="rhead"><div><h2>${esc(m.label)}</h2><div class="muted">${esc(m.road)} · ${m.km} km · ${m.frc} · ${m.tier === "core" ? "Outer Ring Road" : "feeder road"}</div></div>` +
    `<div style="text-align:right"><div class="big" style="color:${col(d.now_ratio)}">${kmh(d.now)}<span class="unit"> km/h</span></div><div class="muted small">now · ${pct(d.now_ratio)} of normal (${kmh(d.ref)} km/h)${d.age ? ` · reading ${d.age} min old` : ""}</div></div></div></div>` +
    `<div class="card"><div class="card-h">Model forecast <span class="muted small">bar: % of normal · numbers: mean and range of 5 runs · tick: what happened</span></div>${fc}</div>` +
    `<div class="card"><div class="card-h">This stretch: recorded and forecast</div><div id="roadChart" class="chart"></div></div>` +
    `<div class="card"><div class="card-h">Road connections</div><div class="muted small" style="margin-bottom:6px">Traffic from here continues to <span style="color:var(--accent2)">(cyan on the map)</span></div><div class="chips">${m.downstream.map((x) => chip(x.id, "down", x.turn ? " <span class='muted'>· turn</span>" : "")).join("") || "<span class='muted small'>end of the modelled network</span>"}</div>` +
    `<div class="muted small" style="margin:10px 0 6px">Traffic arrives from <span style="color:#a78bfa">(violet)</span></div><div class="chips">${m.upstream.map((id) => chip(id, "up")).join("") || "<span class='muted small'>start of the modelled network</span>"}</div>` +
    `<div class="kv" style="margin-top:10px"><span>Road shape</span><span>${m.geometry_source === "tomtom" ? "exact (TomTom)" : "approximate"}</span><span>Stretch id</span><span>${r}</span></div></div>`;
  $$("#road .chip").forEach((c) => (c.onclick = () => selectRoad(c.dataset.r, true)));
  const sr = await api(`/api/series?t=${encodeURIComponent(S.snap.time)}&road=${r}&hours=6`);
  if (S.selected === r && $("#roadChart")) chartSVG(sr, $("#roadChart"), 170);
}

// route panel
function fillRoute() {
  const opts = S.ids.map((r) => `<option value="${r}">${esc(S.road[r].label)} · ${esc(S.road[r].road)}</option>`).join("");
  $("#rsrc").innerHTML = opts; $("#rdst").innerHTML = opts;
  $("#rsrc").value = "orr_ccw_02"; $("#rdst").value = "orr_doddanekundi";
  $("#presets").innerHTML = Object.entries(S.net.trip_presets).map(([name, ids]) => `<button data-s="${ids[0]}" data-d="${ids[ids.length - 1]}">${esc(name)}</button>`).join("");
  $$("#presets button").forEach((b) => (b.onclick = () => { $("#rsrc").value = b.dataset.s; $("#rdst").value = b.dataset.d; plan(); }));
  $("#planBtn").onclick = plan;
  $("#pickBtn").onclick = () => { S.pick = S.pick ? null : "src"; $("#pickBtn").classList.toggle("armed", !!S.pick); $("#pickHint").textContent = S.pick ? "Click the start road on the map." : ""; };
}
async function plan() {
  if (!S.snap) return;
  const src = $("#rsrc").value, dst = $("#rdst").value;
  try {
    const R = await api(`/api/route?src=${src}&dst=${dst}&t=${encodeURIComponent(S.snap.time)}`);
    S.route = { forecast: R.forecast.path.map((p) => p.id), s: 0 };
    const box = (x, title, best) => `<div class="rres ${best ? "best" : ""}"><div class="muted small">${title}</div><div class="m">${x.minutes == null ? "–" : x.minutes + " min"}</div>` +
      `<div class="small">${x.km} km${x.actual_minutes != null ? ` · <b>what it really took: ${x.actual_minutes} min</b>` : ""}${x.assumed_link ? " · uses one assumed link" : ""}</div><div class="path">${x.path.map((p) => esc(p.label)).join(" → ")}</div></div>`;
    let verdict = R.same_path ? "Both choose the same roads; the difference is the travel-time estimate." : "The forecast chooses different roads from a live map.";
    if (R.forecast.actual_minutes != null && R.live.actual_minutes != null && R.forecast.minutes != null && R.live.minutes != null) {
      const ef = Math.abs(R.forecast.minutes - R.forecast.actual_minutes), el = Math.abs(R.live.minutes - R.live.actual_minutes);
      verdict += ef < el ? ` The forecast's estimate was closer to the real trip (${ef.toFixed(1)} vs ${el.toFixed(1)} min off).` : ` Here the live-map estimate was closer (${el.toFixed(1)} vs ${ef.toFixed(1)} min off).`;
    } else if (S.snap.latest) verdict += " This departure is now, so the real trip time is not known yet.";
    $("#routeOut").innerHTML = box(R.forecast, `Fastest on the forecast · time-dependent Dijkstra · depart ${hhmm(R.time)}`, true) +
      box(R.live, "What a live map would pick (current speeds held constant)", false) +
      `<div class="card small">${verdict}${R.notes.length ? `<div class="muted" style="margin-top:6px">${R.notes.map(esc).join("<br>")}</div>` : ""}<div class="muted" style="margin-top:6px">API: /api/route?src=${src}&amp;dst=${dst}</div></div>`;
    const b = L.latLngBounds(S.route.forecast.flatMap((r) => S.road[r].latlngs)); map.fitBounds(b.pad(0.25), { animate: true });
  } catch (e) { $("#routeOut").innerHTML = `<div class="card">${esc(e.message)}</div>`; S.route = null; }
}

// models panel
function renderModels() {
  const st = S.status, R = S.results; if (!st || !R) return;
  const m = st.model, tm = m.test_metrics || {};
  $("#liveModel").innerHTML = `<div class="card-h">Running now in the backend <span class="badge">LIVE MODEL</span></div>` +
    `<div class="kv"><span>Model</span><span>${esc(m.name)}</span><span>Networks</span><span>${m.networks} (3 horizons × ${m.seeds} training runs, averaged)</span>` +
    `<span>Trained on</span><span>${m.trained_on.join(" to ")}</span><span>Validated on</span><span>${m.validated_on.join(" to ")}</span><span>Tested on</span><span>${m.tested_on.join(" to ")} (never used in training)</span>` +
    `<span>Settings</span><span>hidden ${m.hp.hid}, embedding ${m.hp.emb}, dropout ${m.hp.drop}, learning rate ${m.hp.lr}, ${m.hp.lags} lags</span></div>` +
    `<table style="margin-top:8px"><tr><th>Test week, MAE km/h</th>${H.map((h) => `<th>+${h} min</th>`).join("")}</tr>` +
    `<tr class="used"><td>This model</td>${H.map((h) => `<td>${tm[h] ? tm[h].model.toFixed(2) : "–"}</td>`).join("")}</tr>` +
    `<tr><td>Same as now</td>${H.map((h) => `<td>${tm[h] ? tm[h].same_as_now.toFixed(2) : "–"}</td>`).join("")}</tr></table>`;
  const mx = Math.max(...R.models.flatMap((x) => x.mae));
  let rows = "", grp = null;
  for (const x of R.models) {
    if (x.group !== grp) { grp = x.group; rows += `<tr class="grp"><td colspan="4">${esc(grp)}</td></tr>`; }
    rows += `<tr class="${x.used ? "used" : ""}"><td>${esc(x.name)}${x.used ? '<span class="badge">IN THE APP</span>' : ""}</td>${x.mae.map((v) => `<td><span class="mbar" style="width:${v / mx * 46}px"></span>${v.toFixed(2)}</td>`).join("")}</tr>`;
  }
  $("#modelTable").innerHTML = `<table><tr><th>Model</th>${R.horizons.map((h) => `<th>+${h}</th>`).join("")}</tr>${rows}</table><div class="muted small" style="margin-top:6px">${esc(R.source)}</div>`;
  $("#modelNotes").innerHTML = (R.notes || []).map((n) => `<li>${esc(n)}</li>`).join("");
}

// system panel
function renderSystem() {
  const st = S.status; if (!st) return;
  const f = st.feed || {}, age = st.now_ist ? minutesBetween(st.latest_reading, st.now_ist) : null;
  const src = f.source === "github" ? "project collector via GitHub (no key, no extra TomTom requests)" : f.source === "tomtom" ? "TomTom directly (your API key)" : "off (local cache only)";
  const step = (n, cls, h, d) => `<div class="step"><div class="n ${cls}">${n}</div><div><div class="h">${h}</div><div class="d">${d}</div></div></div>`;
  $("#pipe").innerHTML =
    step(1, age != null && age < 150 ? "" : "warn", "Collector", `TomTom Traffic Flow for 21 stretches, every 15 min in rush hours (GitHub Actions). Latest reading <b>${st.latest_reading}</b> (${ago(age)}).`) +
    step(2, f.source === "off" ? "off" : f.last_error ? "warn" : "", "Live feed", `Source: ${src}. Last check ${f.last_attempt || "–"}${f.detail ? `: ${esc(f.detail)}` : ""}.${f.last_error ? ` <span style="color:var(--warn)">${esc(f.last_error)}</span>` : ""}${f.next_at ? ` Next check ${f.next_at.slice(11)}.` : ""} <button class="btn" id="refreshBtn" style="padding:2px 8px;margin-left:4px">Refresh now</button>`) +
    step(3, "", "Data", `${st.readings.toLocaleString()} readings from ${st.first} to ${st.latest_slot}, 15-minute grid, missing readings masked. Reloaded ${st.loaded_at} in ${st.load_seconds} s.`) +
    step(4, "", "Models", `${st.model.networks} Graph Convolutional Networks loaded (trained ${st.model.trained_at}). Every forecast on this page is computed on request.`) +
    step(5, "", "Backend", `FastAPI on this computer, up ${Math.round(st.uptime_s / 60)} min. Endpoints: /api/status, /api/network, /api/snapshot, /api/series, /api/route, /api/timeline, /api/stream (live push). <a href="/docs" target="_blank">API docs</a>`) +
    step(6, "", "Front end", `Leaflet map, canvas animation at ${S.fps} frames/s, ${S.ids.length} road stretches, ${S.net.links.filter((l) => l.kind === "flow").length} connections.`);
  const b = $("#refreshBtn"); if (b) b.onclick = async () => { try { await api("/api/live/refresh", { method: "POST" }); toast("Asked the live feed to check now"); } catch (e) { toast(e.message); } };
  renderLog();
}
function renderStatus() {
  const st = S.status; if (!st) return;
  const age = st.now_ist ? minutesBetween(st.latest_reading, st.now_ist) : null, f = st.feed || {};
  if (S.mode === "live") {
    $("#statusLine").innerHTML = `<b>Latest reading ${st.latest_reading.slice(11)}</b> (${ago(age)}) · source: ${f.source === "github" ? "project collector" : f.source === "tomtom" ? "TomTom direct" : "local cache"}` +
      (f.last_attempt ? ` · checked ${f.last_attempt.slice(11, 16)}` : "") + (f.last_error ? ` · <span style="color:var(--warn)">offline, using cache</span>` : "");
  } else {
    $("#statusLine").innerHTML = `<b>Time-lapse of recorded data</b> · the same models run at every step`;
  }
}

// ------------------------------------------------------------------ applying a moment
function applySnap(sn) {
  S.snap = sn;
  renderCards(); renderAlerts(); renderModelLine(); renderWatermark();
  if (S.selected && $("#p-road").classList.contains("on")) renderRoad();
  if (!S.playing) loadSeries();
  if (S.mode === "lapse") { $("#tlabel").textContent = `${dayLabel(sn.time)}, ${hhmm(sn.time)}`; moveHead(); }
}
function setHorizon(h) {
  S.horizon = h;
  $$("#hseg button").forEach((b) => b.classList.toggle("on", +b.dataset.h === h));
  renderCards(); renderWatermark();
}

// ------------------------------------------------------------------ live mode
async function loadLatest(announce) {
  const [st, sn] = await Promise.all([api("/api/status"), api("/api/snapshot?t=latest")]);
  S.status = st;
  if (st.now_ist) S.serverOffset = new Date(st.now_ist.replace(" ", "T") + "Z").getTime() - Date.now();
  if (S.mode !== "live") return;
  const changed = !S.snap || S.snap.time !== sn.time;
  applySnap(sn); renderStatus();
  if (announce && changed) toast(`New readings arrived · ${hhmm(sn.time)}`);
}
async function enterLive() {
  S.mode = "live"; stopPlay();
  $("#mLive").classList.add("on"); $("#mLapse").classList.remove("on");
  $("#lapseBar").classList.add("hidden"); $("#cmpWrap").classList.add("disabled"); S.cmp = false; $("#cmp").checked = false;
  S.seriesKey = null;
  await loadLatest(false);
  setTimeout(() => { resize(); map.invalidateSize(); }, 50);
}
function startStream() {
  try {
    const es = new EventSource("/api/stream");
    es.addEventListener("update", () => { if (S.mode === "live") loadLatest(true); });
  } catch (e) { /* the 30-second poll still updates */ }
  setInterval(async () => {
    try { S.status = await api("/api/status"); renderStatus(); if ($("#p-system").classList.contains("on")) renderSystem(); } catch (e) { /* offline */ }
  }, 30000);
}

// ------------------------------------------------------------------ time-lapse mode
async function enterLapse() {
  S.mode = "lapse";
  $("#mLapse").classList.add("on"); $("#mLive").classList.remove("on");
  $("#lapseBar").classList.remove("hidden"); $("#cmpWrap").classList.remove("disabled");
  setTimeout(() => { resize(); map.invalidateSize(); }, 50);
  if (!S.days.length) {
    S.days = await api("/api/days");
    $("#daySel").innerHTML = S.days.slice().reverse().map((d) => `<option value="${d.date}">${d.label}${d.daytype === "weekday" ? "" : " · weekend/holiday"}</option>`).join("");
  }
  const latestDay = S.status.latest_slot.slice(0, 10);
  const pickDay = S.days.slice().reverse().find((d) => d.date < latestDay && d.daytype === "weekday") || S.days[S.days.length - 1];
  $("#daySel").value = S.day || pickDay.date;
  renderStatus();
  await loadDay($("#daySel").value, "17:00");
}
async function loadDay(date, from) {
  S.day = date;
  S.timeline = await api(`/api/timeline?date=${date}`);
  drawStrip();
  const k = Math.max(0, S.timeline.findIndex((x) => x.time >= from));
  await seek(k);
}
let seeking = false;
async function seek(k) {
  if (!S.timeline.length) return;
  k = Math.max(0, Math.min(S.timeline.length - 1, k));
  S.k = k;
  const iso = `${S.day}T${S.timeline[k].time}`;
  seeking = true;
  try { const sn = await api(`/api/snapshot?t=${encodeURIComponent(iso)}`); if (S.mode === "lapse" && S.k === k) applySnap(sn); } finally { seeking = false; }
}
function drawStrip() {
  const c = $("#stripC"); if (!c || !S.timeline.length) return;
  const r = c.getBoundingClientRect(), d = window.devicePixelRatio || 1; c.width = r.width * d; c.height = r.height * d;
  const g = c.getContext("2d"); g.setTransform(d, 0, 0, d, 0, 0);
  const n = S.timeline.length, w = r.width / n;
  S.timeline.forEach((x, i) => { g.fillStyle = x.ratio == null ? "rgba(100,116,139,.25)" : col(x.ratio, 0.95); g.fillRect(i * w, 0, Math.ceil(w) + 0.5, r.height); });
  g.font = "600 10px Segoe UI, system-ui, sans-serif"; g.fillStyle = "rgba(255,255,255,.95)"; g.strokeStyle = "rgba(0,0,0,.6)"; g.lineWidth = 3;
  S.timeline.forEach((x, i) => { if (x.time.endsWith(":07") && +x.time.slice(0, 2) % 3 === 0) { g.strokeText(x.time.slice(0, 2) + ":00", i * w + 3, r.height - 6); g.fillText(x.time.slice(0, 2) + ":00", i * w + 3, r.height - 6); } });
  moveHead();
}
function moveHead() { if (S.k == null || !S.timeline.length) return; $("#head").style.left = ((S.k + 0.5) / S.timeline.length * 100) + "%"; }
function stopPlay() { S.playing = false; $("#playBtn").textContent = "▶"; loadSeries(); }
async function playLoop() {
  while (S.playing && S.mode === "lapse") {
    const t0 = performance.now();
    if (S.k >= S.timeline.length - 1) { stopPlay(); break; }
    await seek(S.k + 1);
    const wait = 1000 / S.speed - (performance.now() - t0);
    if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  }
}

// ------------------------------------------------------------------ tabs, controls, theme
function setTab(t) {
  $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  $$(".panel").forEach((p) => p.classList.toggle("on", p.id === "p-" + t));
  if (t === "models") renderModels();
  if (t === "system") renderSystem();
  if (t === "road") { if (!S.selected) $("#road").innerHTML = `<div class="empty">Click a road on the map.</div>`; else renderRoad(); }
}
function bind() {
  $$("#tabs button").forEach((b) => (b.onclick = () => setTab(b.dataset.tab)));
  $$("#hseg button").forEach((b) => (b.onclick = () => setHorizon(+b.dataset.h)));
  $$("#aseg button").forEach((b) => (b.onclick = () => { S.alertH = +b.dataset.h; $$("#aseg button").forEach((x) => x.classList.toggle("on", x === b)); renderAlerts(); }));
  $("#cmp").onchange = (e) => { S.cmp = e.target.checked; if (S.cmp && !S.horizon) setHorizon(30); renderWatermark(); };
  $("#mLive").onclick = () => enterLive();
  $("#mLapse").onclick = () => enterLapse();
  $("#daySel").onchange = (e) => { stopPlay(); loadDay(e.target.value, "07:00"); };
  $("#playBtn").onclick = () => { if (S.playing) { stopPlay(); return; } S.playing = true; $("#playBtn").textContent = "❚❚"; playLoop(); };
  $$("#speedSeg button").forEach((b) => (b.onclick = () => { S.speed = +b.dataset.s; $$("#speedSeg button").forEach((x) => x.classList.toggle("on", x === b)); }));
  $("#strip").onclick = (e) => { const r = $("#strip").getBoundingClientRect(); stopPlay(); seek(Math.floor((e.clientX - r.left) / r.width * S.timeline.length)); };
  $("#themeBtn").onclick = () => setTheme(S.theme === "dark" ? "light" : "dark");
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "SELECT" || e.target.tagName === "INPUT") return;
    if (e.key >= "1" && e.key <= "4") setHorizon([0, 15, 30, 60][+e.key - 1]);
    if (S.mode !== "lapse") return;
    if (e.key === " ") { e.preventDefault(); $("#playBtn").click(); }
    if (e.key === "ArrowRight") { stopPlay(); seek(S.k + 1); }
    if (e.key === "ArrowLeft") { stopPlay(); seek(S.k - 1); }
  });
}
function setTheme(t) {
  S.theme = t; document.documentElement.dataset.theme = t;
  try { localStorage.setItem("orr-theme", t); } catch (e) { /* private window */ }
  setTiles(); drawStrip();
}
setInterval(() => { const d = new Date(Date.now() + S.serverOffset); $("#clock").textContent = d.toISOString().slice(11, 19); }, 1000);

// ------------------------------------------------------------------ start
(async function init() {
  try { const t = localStorage.getItem("orr-theme"); if (t) S.theme = t; } catch (e) { /* ignore */ }
  document.documentElement.dataset.theme = S.theme;
  setTiles(); resize(); bind();
  const [net, results] = await Promise.all([api("/api/network"), api("/api/results")]);
  S.net = net; S.results = results; S.ids = net.roads.map((r) => r.id);
  for (const r of net.roads) S.road[r.id] = Object.assign(r, { latlngs: r.geometry.map(([a, b]) => L.latLng(a, b)) });
  map.fitBounds(L.latLngBounds(net.roads.flatMap((r) => S.road[r.id].latlngs)).pad(0.08));
  geoNote(); fillRoute();
  await enterLive();
  startStream();
  requestAnimationFrame(frame);
})();
