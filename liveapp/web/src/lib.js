// Shared helpers: API access, the congestion colour ramp (same scale as the other pages), formatting.

export async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let detail = r.status;
    try { detail = (await r.json()).detail || detail; } catch { /* not JSON */ }
    throw new Error(String(detail));
  }
  return r.json();
}

// speed as a share of the road's normal speed -> colour. Congested < 60 %, slow < 75 %.
const STOPS = [[0.35, [190, 24, 48]], [0.6, [242, 72, 52]], [0.75, [255, 168, 0]], [0.9, [150, 214, 120]], [1.0, [31, 191, 184]]];
export function rgb(r) {
  if (r == null || Number.isNaN(r)) return [92, 98, 110];
  r = Math.max(0.35, Math.min(1, r));
  for (let k = 1; k < STOPS.length; k++) {
    if (r <= STOPS[k][0]) {
      const [r0, c0] = STOPS[k - 1], [r1, c1] = STOPS[k], f = (r - r0) / (r1 - r0);
      return c0.map((v, j) => Math.round(v + (c1[j] - v) * f));
    }
  }
  return STOPS[STOPS.length - 1][1];
}
export const col = (r, a = 1) => { const c = rgb(r); return `rgba(${c[0]},${c[1]},${c[2]},${a})`; };
export const level = (r) => (r == null ? "none" : r < 0.6 ? "jam" : r < 0.75 ? "slow" : "free");
export const LEVEL_WORD = { jam: "Congested", slow: "Slow", free: "Free flowing", none: "No reading" };
export const pct = (r) => (r == null ? "–" : `${Math.round(r * 100)}%`);
export const kmh = (v) => (v == null ? "–" : `${Math.round(v)}`);
export const H = [15, 30, 60];
export const hhmm = (iso) => (iso ? iso.slice(11, 16) : "–");
const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function dayLabel(iso) {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${WD[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]} ${d} ${MON[m - 1]}`;
}

// The sign message for one road: what a roadside message sign would say about it.
export function message(d) {
  if (!d || d.now_ratio == null) return null;
  if (d.now_ratio < 0.6) return { tone: "jam", text: "Congested now", rank: 0 + d.now_ratio };
  for (const h of H) if (d[`r${h}`] != null && d[`r${h}`] < 0.6) return { tone: "early", text: `Jam in ${h} min`, rank: 1 + h / 100 };
  for (const h of H) if (d[`r${h}`] != null && d[`r${h}`] < 0.75) return { tone: "slow", text: `Slowing in ${h} min`, rank: 2 + h / 100 };
  if (d.now_ratio < 0.75) return { tone: "slow", text: "Slow, easing", rank: 3 };
  return null;
}
