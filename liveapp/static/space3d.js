// Space-time view of the ORR network (Three.js, works offline: three.js is bundled in static/vendor/three).
// Floor = roads coloured by the speed recorded now; walls above each road = the GCN forecast,
// with height = minutes ahead (+15, +30, +60). Data come from the same API as the 2D page.
import * as THREE from "three";
import { OrbitControls } from "/static/vendor/three/OrbitControls.js";

const $ = (s) => document.querySelector(s);
const api = async (p) => { const r = await fetch(p); if (!r.ok) throw new Error(`${p}: ${r.status}`); return r.json(); };

// ---------------------------------------------------------------- colours (same scale as the 2D page)
const STOPS = [[0.35, [179, 19, 43]], [0.6, [239, 68, 68]], [0.75, [245, 158, 11]], [0.9, [163, 230, 53]], [1.0, [34, 197, 94]]];
function rgb(r) {
  if (r == null || isNaN(r)) return [100, 116, 139];
  r = Math.max(0.35, Math.min(1, r));
  for (let k = 1; k < STOPS.length; k++) if (r <= STOPS[k][0]) {
    const [r0, c0] = STOPS[k - 1], [r1, c1] = STOPS[k], f = (r - r0) / (r1 - r0);
    return c0.map((v, j) => Math.round(v + (c1[j] - v) * f));
  }
  return STOPS[STOPS.length - 1][1];
}
const css = (r, a = 1) => { const c = rgb(r); return `rgba(${c[0]},${c[1]},${c[2]},${a})`; };
const pct = (r) => (r == null ? "–" : Math.round(r * 100) + "%");
const level = (r) => (r == null ? "none" : r < 0.6 ? "severe" : r < 0.75 ? "slow" : "free");
const TC = new THREE.Color();   // colours are sRGB on the page; three.js works in linear space, so convert
function toColor(r, out = TC) { const c = rgb(r); return out.setRGB(c[0] / 255, c[1] / 255, c[2] / 255, THREE.SRGBColorSpace); }
function setColor(arr, i, r) { toColor(r); arr[i * 3] = TC.r; arr[i * 3 + 1] = TC.g; arr[i * 3 + 2] = TC.b; }
function toast(m) { const t = $("#toast"); t.textContent = m; t.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), 2800); }

// ---------------------------------------------------------------- scene
const canvas = $("#gl");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x050914);
scene.fog = new THREE.FogExp2(0x050914, 0.028);
const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 400);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true; controls.dampingFactor = 0.08; controls.autoRotate = true; controls.autoRotateSpeed = 0.35;
controls.maxPolarAngle = Math.PI * 0.49; controls.minDistance = 3; controls.maxDistance = 60;

const H = 0.06;                  // height per forecast minute (km units): +60 min = 3.6
const LAYERS = [0, 15, 30, 60];  // floor, then the three forecast horizons
const OFF = 0.16;                // carriageway offset to the left of travel (km, exaggerated like the 2D map)
const FLOW = 25;                 // dots: 1 s on screen = 25 s of driving (same as the 2D page)

const floor = new THREE.Mesh(new THREE.CircleGeometry(60, 64), new THREE.MeshBasicMaterial({ color: 0x070d1c }));
floor.rotation.x = -Math.PI / 2; floor.position.y = -0.02; scene.add(floor);
const grid = new THREE.GridHelper(80, 80, 0x1b3a6b, 0x0e1d38); grid.position.y = -0.01; scene.add(grid);
const scan = new THREE.Mesh(new THREE.RingGeometry(0.98, 1, 96),
  new THREE.MeshBasicMaterial({ color: 0x22d3ee, transparent: true, opacity: 0.3, side: THREE.DoubleSide, depthWrite: false }));
scan.rotation.x = -Math.PI / 2; scene.add(scan);

// ---------------------------------------------------------------- state
const S = { mode: "live", net: null, snap: null, t: "latest", roads: {}, ids: [], center: null, bbox: null,
  hover: null, selected: null, playing: false, timeline: [], day: null, umode: "off", unseen: null };

function project(lat, lon) {   // local km: x = east, z = south
  const [lat0, lon0] = S.center;
  return new THREE.Vector3((lon - lon0) * 111.32 * Math.cos(lat0 * Math.PI / 180), 0, -(lat - lat0) * 110.57);
}
function simplify(pts, n) { if (pts.length <= n) return pts; const out = []; for (let i = 0; i < n; i++) out.push(pts[Math.round(i * (pts.length - 1) / (n - 1))]); return out; }

function buildRoad(r) {
  const raw = simplify(r.geometry, 70).map(([la, lo]) => project(la, lo));
  // shift the carriageway to the left of its direction of travel (India drives on the left)
  const pts = raw.map((p, i) => {
    const a = raw[Math.max(0, i - 1)], b = raw[Math.min(raw.length - 1, i + 1)];
    const dx = b.x - a.x, dz = b.z - a.z, L = Math.hypot(dx, dz) || 1;
    return new THREE.Vector3(p.x + (dz / L) * OFF, 0.05, p.z - (dx / L) * OFF);
  });
  const curve = new THREE.CatmullRomCurve3(pts);
  const len = curve.getLength(), n = Math.max(24, Math.min(140, Math.round(len * 18)));
  const along = curve.getSpacedPoints(n);
  const R = { id: r.id, info: r, curve, len, along, cur: [null, null, null, null], tgt: [null, null, null, null] };

  const mat = new THREE.MeshBasicMaterial({ color: 0x64748b });
  R.tube = new THREE.Mesh(new THREE.TubeGeometry(curve, n, 0.055, 6, false), mat); scene.add(R.tube);
  R.glow = new THREE.Mesh(new THREE.TubeGeometry(curve, n, 0.16, 8, false),
    new THREE.MeshBasicMaterial({ color: 0x64748b, transparent: true, opacity: 0.22, depthWrite: false }));
  scene.add(R.glow);

  // the wall: rows at the floor, +15, +30, +60 min; vertex colours carry the forecast
  const cols = along.length, pos = new Float32Array(cols * 4 * 3), col = new Float32Array(cols * 4 * 3), idx = [];
  for (let j = 0; j < 4; j++) for (let i = 0; i < cols; i++) {
    const k = j * cols + i; pos[k * 3] = along[i].x; pos[k * 3 + 1] = 0.05 + LAYERS[j] * H; pos[k * 3 + 2] = along[i].z;
  }
  for (let j = 0; j < 3; j++) for (let i = 0; i < cols - 1; i++) {
    const a = j * cols + i, b = a + 1, c = a + cols, d = c + 1; idx.push(a, c, b, b, c, d);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.setAttribute("color", new THREE.BufferAttribute(col, 3)); g.setIndex(idx);
  R.wall = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.34, side: THREE.DoubleSide,
    depthWrite: false }));
  scene.add(R.wall);
  // bright edge lines at each forecast horizon
  R.edges = [1, 2, 3].map((j) => {
    const lg = new THREE.BufferGeometry().setFromPoints(along.map((p) => new THREE.Vector3(p.x, 0.05 + LAYERS[j] * H, p.z)));
    const line = new THREE.Line(lg, new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: j === 3 ? 0.95 : 0.55 }));
    scene.add(line); return line;
  });
  // invisible fat tube for hover / click
  R.pick = new THREE.Mesh(new THREE.TubeGeometry(curve, Math.min(60, n), 0.35, 5, false), new THREE.MeshBasicMaterial({ visible: false }));
  R.pick.userData.id = r.id; R.wall.userData.id = r.id; scene.add(R.pick);
  // ring at the middle: congested now (red) or early warning (amber)
  const mid = curve.getPointAt(0.5);
  R.ring = new THREE.Mesh(new THREE.RingGeometry(0.28, 0.36, 40),
    new THREE.MeshBasicMaterial({ color: 0xef4444, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending }));
  R.ring.rotation.x = -Math.PI / 2; R.ring.position.set(mid.x, 0.07, mid.z); scene.add(R.ring);
  R.mid = mid;
  // moving traffic
  R.parts = []; return R;
}

let dots = null;
function buildDots() {
  const all = [];
  for (const id of S.ids) { const R = S.roads[id]; const k = Math.max(2, Math.round(R.len / 0.45)); for (let i = 0; i < k; i++) all.push({ id, s: Math.random() }); }
  const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(all.length * 3), 3));
  dots = new THREE.Points(g, new THREE.PointsMaterial({ color: 0xffffff, size: 0.09, transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false }));
  dots.userData.list = all; scene.add(dots);
}

// axis pole with the time layers, plus faint layer outlines around the network
const labelsEl = $("#labels"), LBL = [];
function addLabel(text, v3, cls = "lbl") { const el = document.createElement("div"); el.className = cls; el.textContent = text; labelsEl.appendChild(el); LBL.push({ el, v: v3 }); }
function buildFrame() {
  const b = S.bbox, pad = 0.8;
  for (const [j, h] of LAYERS.entries()) {
    const y = 0.05 + h * H;
    const pts = [[b.min.x - pad, b.min.z - pad], [b.max.x + pad, b.min.z - pad], [b.max.x + pad, b.max.z + pad], [b.min.x - pad, b.max.z + pad]]
      .map(([x, z]) => new THREE.Vector3(x, y, z));
    const loop = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: 0x22d3ee, transparent: true, opacity: j === 0 ? 0.25 : 0.12 }));
    scene.add(loop);
    addLabel(j === 0 ? "now (recorded)" : `+${h} min forecast`, new THREE.Vector3(b.max.x + pad, y, b.min.z - pad), "lbl axis");
  }
  const pole = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(b.max.x + pad, 0, b.min.z - pad), new THREE.Vector3(b.max.x + pad, 0.05 + 60 * H, b.min.z - pad)]),
    new THREE.LineBasicMaterial({ color: 0x22d3ee }));
  scene.add(pole);
  const seen = new Set();
  for (const id of S.ids) {
    const r = S.roads[id].info, name = r.label;
    if (name.includes(" to ") || seen.has(name) || r.tier !== "core" && !/Airport/.test(name)) continue;
    seen.add(name); addLabel(name, S.roads[id].mid.clone().setY(0.35));
  }
}

// ---------------------------------------------------------------- data
async function loadNetwork() {
  S.net = await api("/api/network");
  const all = S.net.roads.flatMap((r) => r.geometry);
  S.center = [all.reduce((a, p) => a + p[0], 0) / all.length, all.reduce((a, p) => a + p[1], 0) / all.length];
  S.bbox = new THREE.Box3();
  for (const r of S.net.roads) { S.ids.push(r.id); S.roads[r.id] = buildRoad(r); for (const p of S.roads[r.id].along) S.bbox.expandByPoint(p); }
  buildDots(); buildFrame();
  $("#uRoad").innerHTML = '<option value="">Pick a road…</option>' + S.net.roads.map((r) => `<option value="${r.id}">${r.label} · ${r.road}</option>`).join("");
  $("#uRoad").onchange = (e) => select(e.target.value, true);
  vlab = document.createElement("div"); vlab.className = "lbl"; vlab.style.color = "#22d3ee"; labelsEl.appendChild(vlab);
  LBL.push({ el: vlab, v: new THREE.Vector3(), dyn: true });
  const c = S.bbox.getCenter(new THREE.Vector3()); controls.target.set(c.x, 1.2, c.z); view3d();
  $("#engine").innerHTML = `Geometry: ${S.net.geometry.exact} of ${S.net.geometry.total} stretches with exact TomTom road shapes. ` +
    `Forecasts come from 15 trained graph networks (3 horizons × 5 runs), computed on request by the local FastAPI backend.`;
}

async function loadMoment() {
  const t0 = performance.now();
  const [snap, ser] = await Promise.all([api(`/api/snapshot?t=${encodeURIComponent(S.t)}`),
    api(`/api/series?t=${encodeURIComponent(S.t)}${S.selected ? "&road=" + S.selected : ""}&hours=6`)]);
  S.snap = snap; S.series = ser; S.unseen = null; S.uerr = null;
  if (S.selected && S.umode !== "off") {
    const r = await fetch(`/api/unseen?road=${S.selected}&t=${encodeURIComponent(S.t)}`);
    if (r.ok) S.unseen = await r.json(); else S.uerr = (await r.json()).detail || r.status;
  }
  for (const id of S.ids) {
    const d = snap.roads[id], R = S.roads[id]; if (!d) continue;
    R.tgt = [d.now_ratio, d.r15, d.r30, d.r60]; R.d = d;
    if (S.unseen && id === S.selected) {
      const u = S.unseen.rows, k = S.umode === "none" ? "virtual" : "new";
      R.tgt = [S.umode === "none" ? S.unseen.nowcast : d.now_ratio, u[0][k], u[1][k], u[2][k]];
    }
    if (R.cur[0] == null) R.cur = R.tgt.slice();
    R.painted = false;
  }
  renderPanel(performance.now() - t0);
}

// ---------------------------------------------------------------- panel
function renderPanel(ms) {
  const s = S.snap.summary;
  for (const [k, v] of [["k0", s.now], ["k15", s.r15], ["k30", s.r30], ["k60", s.r60]]) { const el = $("#" + k); el.textContent = pct(v); el.style.color = css(v); }
  $("#when").textContent = `${S.mode === "live" ? "LIVE · " : ""}${S.snap.time.replace("T", " ")}`;
  $("#chartTitle").textContent = S.selected ? `Forecast · ${S.roads[S.selected].info.label} (${S.roads[S.selected].info.road})` : "Live forecast · whole corridor";
  if (S.mode === "replay") $("#chartTitle").textContent = $("#chartTitle").textContent.replace("Live forecast", "Forecast");
  drawChart(S.series, S.unseen ? S.unseen.rows.map((x) => [x.t, S.umode === "none" ? x.virtual : x.new]) : null);
  renderUnseen();
  $("#chartNote").textContent = `Models ran in ${S.snap.model_ms ?? "–"} ms on the server · ${Math.round(ms)} ms request to screen` +
    (S.selected ? " · click empty space to go back to the corridor" : " · click a road for its own forecast");
  // hotspots: worst forecast in the next hour
  const rows = S.ids.map((id) => ({ id, R: S.roads[id], d: S.roads[id].d })).filter((x) => x.d)
    .map((x) => ({ ...x, worst: Math.min(...[x.d.r15, x.d.r30, x.d.r60].filter((v) => v != null)) }))
    .sort((a, b) => a.worst - b.worst).slice(0, 6);
  $("#hot").innerHTML = rows.map(({ id, R, d }) => {
    const early = d.now_ratio != null && d.now_ratio >= 0.6 && [d.r15, d.r30, d.r60].some((v) => v != null && v < 0.6);
    const tag = d.now_ratio != null && d.now_ratio < 0.6 ? '<span class="tag now">JAMMED</span>' : early ? '<span class="tag early">EARLY WARNING</span>' : "";
    const chip = (v) => `<i style="background:${css(v)}">${pct(v)}</i>`;
    return `<div class="hot" data-id="${id}"><div class="nm">${R.info.label}${tag}</div><div class="dr">${R.info.road} · normal ${Math.round(d.ref)} km/h</div>` +
      `<div class="chips">${chip(d.now_ratio)}${chip(d.r15)}${chip(d.r30)}${chip(d.r60)}</div></div>`;
  }).join("");
  document.querySelectorAll(".hot").forEach((el) => (el.onclick = () => select(el.dataset.id, true)));
}

function drawChart(sr, extra) {
  const el = $("#chart"), W = el.clientWidth || 350, Hh = 170, pl = 30, pr = 8, pt = 10, pb = 20;
  const past = sr.past.filter((p) => p[1] != null), fc = sr.forecast;
  if (!past.length) { el.innerHTML = ""; return; }
  const t = (s) => new Date(s + ":00Z").getTime();
  const x0 = t(past[0][0]), x1 = t(fc.length ? fc[fc.length - 1].t : past[past.length - 1][0]);
  const vals = past.map((p) => p[1]).concat(fc.flatMap((f) => [f.lo, f.hi, f.actual].filter((v) => v != null)));
  const lo = Math.min(0.4, ...vals) - 0.03, hi = Math.max(1.0, ...vals) + 0.02;
  const X = (s) => pl + (t(s) - x0) / Math.max(1, x1 - x0) * (W - pl - pr), Y = (v) => pt + (hi - v) / (hi - lo) * (Hh - pt - pb);
  let g = "";
  for (const v of [0.6, 0.75, 1.0]) g += `<line x1="${pl}" x2="${W - pr}" y1="${Y(v)}" y2="${Y(v)}" stroke="currentColor" opacity=".18" stroke-dasharray="3 3"/><text x="${pl - 4}" y="${Y(v) + 3}" text-anchor="end" fill="currentColor">${Math.round(v * 100)}%</text>`;
  let lastX = -99;   // time labels, skipped when closer than 40 px to the previous one
  for (const [ts] of past) { const x = X(ts); if (x - lastX < 40) continue; lastX = x; g += `<text x="${x}" y="${Hh - 5}" text-anchor="middle" fill="currentColor">${ts.slice(11, 16)}</text>`; }
  const nowT = past[past.length - 1];
  if (fc.length) {
    const band = [[nowT[0], nowT[1]]].concat(fc.map((f) => [f.t, f.hi])).map(([s, v]) => `${X(s)},${Y(v)}`)
      .concat([[nowT[0], nowT[1]]].concat(fc.map((f) => [f.t, f.lo])).reverse().map(([s, v]) => `${X(s)},${Y(v)}`));
    g += `<polygon points="${band.join(" ")}" fill="rgba(91,140,255,.28)"/>`;
    g += `<polyline points="${[nowT].concat(fc.map((f) => [f.t, f.mean])).map(([s, v]) => `${X(s)},${Y(v)}`).join(" ")}" fill="none" stroke="#5b8cff" stroke-width="2.4" stroke-dasharray="6 4"/>`;
    for (const f of fc) g += `<circle cx="${X(f.t)}" cy="${Y(f.mean)}" r="3.2" fill="#5b8cff"/>`;
  }
  g += `<polyline points="${past.map(([s, v]) => `${X(s)},${Y(v)}`).join(" ")}" fill="none" stroke="#f97316" stroke-width="2.4"/>`;
  if (extra && fc.length) g += `<polyline points="${[[nowT[0], S.umode === "none" && S.unseen.nowcast != null ? S.unseen.nowcast : nowT[1]]].concat(extra).map(([s, v]) => `${X(s)},${Y(v)}`).join(" ")}" fill="none" stroke="#22d3ee" stroke-width="2.6"/>` +
    extra.map(([s, v]) => `<rect x="${X(s) - 3.5}" y="${Y(v) - 3.5}" width="7" height="7" fill="#22d3ee" transform="rotate(45 ${X(s)} ${Y(v)})"/>`).join("");
  let any = false;
  for (const f of fc) if (f.actual != null) { any = true; g += `<circle cx="${X(f.t)}" cy="${Y(f.actual)}" r="5" fill="none" stroke="${css(f.actual)}" stroke-width="2"/>`; }
  $("#actLeg").style.display = any ? "" : "none";
  g += `<line x1="${X(nowT[0])}" x2="${X(nowT[0])}" y1="${pt}" y2="${Hh - pb}" stroke="#22d3ee" opacity=".7"/><text x="${X(nowT[0])}" y="${pt + 2}" text-anchor="middle" fill="#22d3ee">now</text>`;
  el.setAttribute("viewBox", `0 0 ${W} ${Hh}`); el.innerHTML = g;
}

// ---------------------------------------------------------------- interaction
const ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
let downAt = null;
function pickAt(e) {
  mouse.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1); ray.setFromCamera(mouse, camera);
  const hit = ray.intersectObjects(S.ids.flatMap((id) => [S.roads[id].pick, S.roads[id].wall]), false)[0];
  return hit ? hit.object.userData.id : null;
}
canvas.addEventListener("pointermove", (e) => {
  if (!S.net) return;
  const id = pickAt(e); S.hover = id; canvas.style.cursor = id ? "pointer" : "grab";
  const tip = $("#tip");
  if (!id || !S.roads[id].d) { tip.style.display = "none"; return; }
  const R = S.roads[id], d = R.d, row = (lab, v, kmh, act) => `<div class="row"><span>${lab}</span><span><b style="color:${css(v)}">${pct(v)}</b> · ${kmh == null ? "–" : Math.round(kmh)} km/h${act != null ? ` <span class="mut">(happened ${Math.round(act)})</span>` : ""}</span></div>`;
  tip.innerHTML = `<b>${R.info.label}</b><div class="mut small">${R.info.road} · ${R.info.km} km · normal ${Math.round(d.ref)} km/h</div><hr style="border:0;border-top:1px solid var(--line)">` +
    row("now", d.now_ratio, d.now) + row("+15 min", d.r15, d.f15, d.a15) + row("+30 min", d.r30, d.f30, d.a30) + row("+60 min", d.r60, d.f60, d.a60);
  tip.style.display = "block";
  tip.style.left = Math.min(innerWidth - 260, e.clientX + 16) + "px"; tip.style.top = Math.min(innerHeight - 170, e.clientY + 16) + "px";
});
canvas.addEventListener("pointerdown", (e) => { downAt = [e.clientX, e.clientY]; controls.autoRotate = false; });
canvas.addEventListener("pointerup", (e) => {
  if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 5) return;
  select(pickAt(e), false);
});
let fly = null;
function select(id, flyTo) {
  S.selected = id || null; $("#uRoad").value = S.selected || "";
  if (id && flyTo) { const m = S.roads[id].mid; fly = { from: controls.target.clone(), to: new THREE.Vector3(m.x, 1.2, m.z), t: 0 }; controls.autoRotate = false; spinBtn(); }
  loadMoment().catch(console.error);
}
function view3d() { const c = controls.target; camera.position.set(c.x + 7, 14, c.z + 21); }
$("#v3d").onclick = () => { fly = null; view3d(); };
$("#vTop").onclick = () => { fly = null; const c = controls.target; camera.position.set(c.x, 24, c.z + 0.01); controls.autoRotate = false; spinBtn(); };
function spinBtn() { $("#vSpin").textContent = `Auto-rotate: ${controls.autoRotate ? "on" : "off"}`; }
$("#vSpin").onclick = () => { controls.autoRotate = !controls.autoRotate; spinBtn(); };
document.querySelectorAll("#uMode button").forEach((b) => (b.onclick = () => {
  document.querySelectorAll("#uMode button").forEach((x) => x.classList.toggle("on", x === b));
  S.umode = b.dataset.u; $("#unseenBox").scrollIntoView({ block: "nearest", behavior: "smooth" });
  if (S.umode !== "off" && !S.selected) { select("orr_cw_05", true); return; }   // default demo road
  for (const id of S.ids) S.roads[id].cur = [null, null, null, null];
  loadMoment().catch(console.error);
}));
let vlab = null;
function renderUnseen() {
  const o = $("#uOut"), chip = (v) => v == null ? "–" : `<i style="background:${css(v)}">${pct(v)}</i>`;
  if (S.umode === "off") { o.innerHTML = S.selected ? `<span class="mut">Choose <b>New sensor</b> or <b>No sensor</b> to forecast ${S.roads[S.selected].info.label} with networks that never saw it.</span>` : '<span class="mut">Pick a road above or click one in the 3D view.</span>'; return; }
  if (S.uerr) { o.innerHTML = `<span class="mut">${S.uerr}</span>`; return; }
  const u = S.unseen; if (!u) { o.textContent = "loading…"; return; }
  const k = S.umode === "none" ? "virtual" : "new";
  const nbc = S.umode === "none";   // no sensor: also show the neighbours' GCN forecast (best on average in the test week)
  let rows = u.rows.map((x) => `<tr><td>+${x.h} min</td><td>${chip(x[k])}</td>${nbc ? `<td>${chip(x.nbr_forecast)}</td>` : ""}<td>${chip(x.normal)}</td><td>${chip(x.actual)}</td></tr>`).join("");
  const nowRow = nbc ? `<tr><td>now</td><td>${chip(u.nowcast)}</td><td>–</td><td>${chip(u.now_actual)}</td><td>${chip(u.now_actual)}</td></tr>` : "";
  const m = u.measured["60"], f = (v) => v == null ? "–" : v.toFixed(1);
  const meas = S.umode === "none"
    ? `Test week, +60 min, error in points of normal speed: virtual sensor <b>${f(m.none.unseen)}</b> · neighbours' forecast ${f(m.none.nbr_forecast)} · neighbours now ${f(m.none.neighbours)} · normal model (saw it) ${f(m.none.seen)}`
    : `Test week, +60 min, error in points of normal speed: new-sensor GCN <b>${f(m.new.unseen)}</b> · same as now ${f(m.new.same_as_now)} · normal model (saw it) ${f(m.new.seen)}`;
  o.innerHTML = `<div class="vtag">${S.umode === "none" ? "VIRTUAL SENSOR · no readings of this road used" : "NEW SENSOR · live readings, no training history"}</div>` +
    `<table class="utab"><tr><th></th><th>${nbc ? "Virtual" : "Unseen"}</th>${nbc ? "<th>Nbrs' fc</th>" : ""}<th>Normal</th><th>Happened</th></tr>${nowRow}${rows}</table>` +
    `<div class="mut">${S.umode === "none" ? "Estimated only from connected roads: " + u.neighbours.join(", ") + ". " : ""}Cyan line in the chart = this forecast.</div>` +
    `<div class="mut" style="margin-top:6px">${meas} (measured, one week).</div>`;
}
$("#vHelp").onclick = () => $("#help").classList.toggle("closed");
$("#helpX").onclick = () => $("#help").classList.add("closed");

// ---------------------------------------------------------------- live and replay
let es = null;
function startLive() {
  S.mode = "live"; S.t = "latest"; stopPlay(); $("#replayCtl").style.display = "none";
  loadMoment().catch(console.error); refreshStatus();
  if (!es) {
    es = new EventSource("/api/stream");
    es.addEventListener("update", () => { if (S.mode === "live") { loadMoment(); refreshStatus(); toast("New readings arrived: forecasts updated"); } });
  }
}
async function refreshStatus() {
  try {
    const s = await api("/api/status"), f = s.feed || {};
    $("#stat").innerHTML = S.mode === "live"
      ? `Latest reading <b>${s.latest_reading.slice(11, 16)}</b> · source: ${f.source === "off" ? "local cache" : f.source === "github" ? "project collector" : f.source}`
      : `Replay of recorded data · the same models run at every step`;
  } catch (e) { $("#stat").textContent = "backend not reachable"; }
}
async function startReplay() {
  S.mode = "replay"; $("#replayCtl").style.display = "contents"; refreshStatus();
  if (!$("#day").options.length) {
    const days = (await api("/api/days")).filter((d) => d.daytype === "weekday");
    $("#day").innerHTML = days.map((d) => `<option value="${d.date}">${d.label}</option>`).join("");
    const pick = days.find((d) => d.date === "2026-11-24") || days[days.length - 2] || days[days.length - 1];
    $("#day").value = pick.date;
  }
  await loadDay($("#day").value);
}
async function loadDay(date) {
  S.day = date; S.timeline = (await api(`/api/timeline?date=${date}`)).filter((x) => x.ratio != null);
  const sl = $("#slider"); sl.max = S.timeline.length - 1;
  const start = S.timeline.findIndex((x) => x.time >= "17:00"); sl.value = start < 0 ? 0 : start;
  seek(+sl.value);
}
function seek(i) { const x = S.timeline[i]; if (!x) return; S.t = `${S.day}T${x.time}`; loadMoment().catch(console.error); }
function stopPlay() { S.playing = false; clearTimeout(S.timer); $("#play").textContent = "▶"; }
function step() {
  if (!S.playing) return;
  const sl = $("#slider"); if (+sl.value >= +sl.max) { stopPlay(); return; }
  sl.value = +sl.value + 1; seek(+sl.value); S.timer = setTimeout(step, 900);
}
$("#play").onclick = () => { if (S.playing) stopPlay(); else { S.playing = true; $("#play").textContent = "❚❚"; step(); } };
$("#slider").oninput = (e) => { stopPlay(); seek(+e.target.value); };
$("#day").onchange = (e) => { stopPlay(); loadDay(e.target.value); };
document.querySelectorAll("#modes button").forEach((b) => (b.onclick = () => {
  document.querySelectorAll("#modes button").forEach((x) => x.classList.toggle("on", x === b));
  b.dataset.m === "live" ? startLive() : startReplay();
}));

// ---------------------------------------------------------------- frame loop
function resize() {
  renderer.setSize(innerWidth, innerHeight, false); camera.aspect = innerWidth / innerHeight;
  // centre the scene in the space left of the side panel (about 400 px wide)
  const shift = innerWidth > 900 ? 200 : 0;
  camera.setViewOffset(innerWidth, innerHeight, shift, 0, innerWidth, innerHeight);
  camera.updateProjectionMatrix();
}
addEventListener("resize", resize); resize();
const clock = new THREE.Clock(), tmp = new THREE.Vector3();
function frame() {
  const dt = Math.min(0.1, clock.getDelta()), T = clock.elapsedTime, k = Math.min(1, dt * 3);
  if (fly) { fly.t = Math.min(1, fly.t + dt * 1.2); const e = 1 - Math.pow(1 - fly.t, 3); const prev = controls.target.clone();
    controls.target.lerpVectors(fly.from, fly.to, e); camera.position.add(tmp.subVectors(controls.target, prev)); if (fly.t >= 1) fly = null; }
  for (const id of S.ids) {
    const R = S.roads[id]; if (R.tgt[0] === undefined) continue;
    let changed = false;
    for (let j = 0; j < 4; j++) {
      const a = R.cur[j], b = R.tgt[j];
      if (b == null) { if (a != null) { R.cur[j] = null; changed = true; } continue; }
      const v = a == null ? b : a + (b - a) * k; if (a == null || Math.abs(v - a) > 1e-4) { R.cur[j] = v; changed = true; }
    }
    if (changed || !R.painted) {
      R.painted = true;
      toColor(R.cur[0], R.tube.material.color); R.glow.material.color.copy(R.tube.material.color);
      const col = R.wall.geometry.attributes.color, n = R.along.length;
      for (let j = 0; j < 4; j++) { const r = R.cur[j] ?? R.cur[0]; for (let i = 0; i < n; i++) setColor(col.array, j * n + i, r); }
      col.needsUpdate = true;
      R.edges.forEach((ln, j) => toColor(R.cur[j + 1] ?? R.cur[0], ln.material.color));
    }
    // emphasis: hovered / selected road bright, others dimmed when something is selected
    const focus = S.selected ? id === S.selected : true, hov = id === S.hover;
    R.wall.material.opacity = (focus ? 0.42 : 0.07) + (hov ? 0.2 : 0);
    R.edges.forEach((ln, j) => (ln.material.opacity = (focus ? (j === 2 ? 0.95 : 0.5) : 0.12)));
    R.glow.material.opacity = (hov || id === S.selected ? 0.55 : 0.22) * (focus ? 1 : 0.5);
    if (S.unseen && id === S.selected) { R.glow.material.color.set(0x22d3ee); R.glow.material.opacity = 0.35 + 0.3 * Math.sin(T * 4) ** 2; }
    else R.glow.material.color.copy(R.tube.material.color);
    // rings: congested now (red) or early warning (amber), pulsing
    const d = R.d, now = d && d.now_ratio, worst = d ? Math.min(...[d.r15, d.r30, d.r60].filter((v) => v != null)) : 1;
    const jam = now != null && now < 0.6, early = !jam && now != null && worst < 0.6;
    R.ring.material.color.set(jam ? 0xef4444 : 0xf59e0b);
    const p = (T * 0.8 + R.len) % 1; R.ring.scale.setScalar(1 + p * 1.8); R.ring.material.opacity = jam || early ? (1 - p) * 0.9 : 0;
  }
  if (dots) {
    const list = dots.userData.list, pos = dots.geometry.attributes.position.array;
    for (let i = 0; i < list.length; i++) {
      const q = list[i], R = S.roads[q.id], kmh = R.d && R.d.now != null ? R.d.now : 0;
      q.s = (q.s + (kmh * FLOW / 3600) * dt / R.len) % 1;
      const p = R.curve.getPointAt(q.s); pos[i * 3] = p.x; pos[i * 3 + 1] = 0.12; pos[i * 3 + 2] = p.z;
    }
    dots.geometry.attributes.position.needsUpdate = true;
  }
  const sp = (T * 0.12) % 1; scan.scale.setScalar(1 + sp * 22); scan.material.opacity = 0.35 * (1 - sp);
  if (S.bbox) { const c = S.bbox.getCenter(tmp); scan.position.set(c.x, 0.02, c.z); }
  controls.update(); renderer.render(scene, camera);
  if (vlab) {
    const on = S.unseen && S.selected;
    vlab.textContent = on ? (S.umode === "none" ? "◆ VIRTUAL SENSOR" : "◆ NEW SENSOR") : "";
    if (on) { const m = S.roads[S.selected].mid; LBL[LBL.length - 1].v.set(m.x, 0.05 + 60 * H + 0.5, m.z); }
  }
  for (const L of LBL) {
    const v = L.v.clone().project(camera), vis = v.z < 1 && Math.abs(v.x) < 1.1 && Math.abs(v.y) < 1.1;
    L.el.style.display = vis ? "" : "none";
    if (vis) { L.el.style.left = ((v.x + 1) / 2 * innerWidth) + "px"; L.el.style.top = ((1 - v.y) / 2 * innerHeight) + "px"; }
  }
  requestAnimationFrame(frame);
}
setInterval(() => { $("#clock").textContent = new Date().toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata" }); }, 1000);
setInterval(() => { if (S.mode === "live") refreshStatus(); }, 60000);

loadNetwork().then(() => { startLive(); frame(); }).catch((e) => { $("#stat").textContent = "could not load: " + e.message; console.error(e); });
