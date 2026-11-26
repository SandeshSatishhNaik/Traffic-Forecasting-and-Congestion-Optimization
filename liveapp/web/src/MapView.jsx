import { useEffect, useRef } from "react";
import L from "leaflet";
import { col, level, pct, kmh, LEVEL_WORD } from "./lib.js";

// Shift a carriageway to the left of its direction of travel (India drives on the left), in degrees.
function leftShift(pts, off = 0.00055) {
  return pts.map(([la, lo], i) => {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
    const dy = b[0] - a[0], dx = (b[1] - a[1]) * Math.cos((la * Math.PI) / 180);
    const n = Math.hypot(dx, dy) || 1;
    return [la + (dx / n) * off, lo - (dy / n) * off / Math.cos((la * Math.PI) / 180)];
  });
}

const valueAt = (d, h) => (!d ? null : h === 0 ? d.now_ratio : d[`r${h}`]);
const speedAt = (d, h) => (!d ? null : h === 0 ? d.now : d[`f${h}`]);

export default function MapView({ net, snap, h, selected, onSelect, unseenRoad }) {
  const el = useRef(null), mapRef = useRef(null), layers = useRef({});

  // build the map and the road layers once
  useEffect(() => {
    if (!net || mapRef.current) return;
    const map = L.map(el.current, { zoomControl: false, attributionControl: true, zoomSnap: 0.25, preferCanvas: false });
    mapRef.current = map;
    L.control.zoom({ position: "bottomleft" }).addTo(map);
    let ok = 0, bad = 0;
    const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, className: "basemap", attribution: "© OpenStreetMap contributors",
    });
    tiles.on("tileload", () => ok++);
    tiles.on("tileerror", () => { bad++; if (bad >= 4 && ok === 0) { map.removeLayer(tiles); el.current.classList.add("offline"); } });
    tiles.addTo(map);
    const bounds = L.latLngBounds([]);
    for (const r of net.roads) {
      const pts = leftShift(r.geometry);
      pts.forEach((p) => bounds.extend(p));
      const casing = L.polyline(pts, { weight: 11, color: "#050506", opacity: 0.85, lineCap: "round", lineJoin: "round", interactive: false }).addTo(map);
      const line = L.polyline(pts, { weight: 6, color: "#5c626e", lineCap: "round", lineJoin: "round", className: "road" }).addTo(map);
      const flow = L.polyline(pts, { weight: 2.2, color: "#fff", opacity: 0.85, dashArray: "2 14", lineCap: "round", interactive: false, className: "flow" }).addTo(map);
      line.on("click", () => onSelect(r.id));
      line.bindTooltip("", { sticky: true, className: "road-tip", direction: "top", offset: [0, -8] });
      layers.current[r.id] = { r, casing, line, flow };
    }
    // keep the network clear of the horizon tiles (top) and the legend (bottom right)
    const fit = () => map.fitBounds(bounds, { paddingTopLeft: [24, 120], paddingBottomRight: [40, 40] });
    fit();
    let lastH = el.current.clientHeight;
    const ro = new ResizeObserver(() => { map.invalidateSize(); const hh = el.current.clientHeight; if (Math.abs(hh - lastH) > 30) { lastH = hh; fit(); } });
    ro.observe(el.current);
    return () => { ro.disconnect(); map.remove(); mapRef.current = null; layers.current = {}; };
  }, [net]); // eslint-disable-line react-hooks/exhaustive-deps

  // recolour on every new moment / horizon / selection
  useEffect(() => {
    if (!snap) return;
    for (const [id, L_] of Object.entries(layers.current)) {
      const d = snap.roads[id], v = valueAt(d, h), s = speedAt(d, h), sel = id === selected;
      L_.line.setStyle({ color: col(v), weight: sel ? 9 : 6 });
      L_.casing.setStyle({ color: sel ? "#ffb000" : "#050506", weight: sel ? 15 : 11, opacity: sel ? 1 : 0.85 });
      const path = L_.line.getElement(), flow = L_.flow.getElement();
      if (path) {
        path.classList.toggle("jam", level(v) === "jam");
        path.classList.toggle("virtual", id === unseenRoad);
      }
      if (flow) flow.style.animationDuration = `${Math.max(0.45, Math.min(9, 36 / Math.max(4, s || 4)))}s`;   // dashes move about 0.9 px/s per km/h
      L_.line.setTooltipContent(
        `<b>${L_.r.label}</b><span>${L_.r.road}</span>` +
        `<em style="color:${col(v)}">${pct(v)} of normal · ${kmh(s)} km/h</em>` +
        `<small>${h === 0 ? "recorded now" : `forecast +${h} min`} · ${LEVEL_WORD[level(v)]}</small>`);
    }
  }, [snap, h, selected, unseenRoad]);

  // fly to a selected road
  useEffect(() => {
    const L_ = layers.current[selected];
    if (L_ && mapRef.current) mapRef.current.flyToBounds(L_.line.getBounds(), { padding: [120, 120], maxZoom: 14, duration: 0.8 });
  }, [selected]);

  return <div ref={el} className="map" role="application" aria-label="Map of the 21 road stretches, coloured by speed" />;
}
