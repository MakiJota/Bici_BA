// Section A — interactive mobility map (MapLibre GL JS).
import { D, S, aggregate, aggregateDemo, demoActive, levelOf, loadRoutes, loadStreets, odMatrix, routeSegments, segmentCounts, streetCounts, unitStations } from "./data.js";
import { fmt, pct, t } from "./i18n.js";
import { css, plotMini } from "./charts.js";
import { rangeHist } from "./rangehist.js";

let map, agg = null, segCounts = null, focus = null, ready = false, selectedStation = null;
let flowHist = null, streetHist = null, flowLevel = null, shownFlows = [];
const MAX_ARROWS = 1500;                               // drawing cap (strongest first)
const MAX_DEFAULT_ROUTES = 30;
const layerOn = { stations: true, od: true, routes: true, streets: false, barrios: false, comunas: true, infra: false };
const EMPTY = { type: "FeatureCollection", features: [] };

const dark = () => getComputedStyle(document.documentElement).getPropertyValue("--bg").trim() === "#0c0c0c";
const basemap = () => dark()
  ? "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json"
  : "https://basemaps.cartocdn.com/gl/positron-nolabels-gl-style/style.json";

// CARTO basemap reduced to land, water and parks: roads, rail and buildings are
// removed so that stations, flows and the routed street network stand out.
async function cleanBasemap() {
  const style = await (await fetch(basemap())).json();
  style.layers = style.layers.filter((l) => !["roads", "buildings"].includes(l["source-layer"]) &&
    !/^(road|bridge|tunnel|rail|aeroway|boundary_(county|state))/.test(l.id));
  return style;
}
// Heat ramp for street intensity (few -> many trips), legible on either theme.
const HEAT_DARK = ["#3a0e0e", "#6e1717", "#a3201d", "#d6331f", "#ff5a36", "#ffa07a", "#ffe0cc"];
const HEAT_LIGHT = ["#fde0da", "#f9b3a5", "#f07c69", "#e04535", "#bf1f1a", "#8c1010", "#520808"];
const heat = () => (dark() ? HEAT_DARK : HEAT_LIGHT);
const heatAt = (x) => { const r = heat(); return r[Math.min(r.length - 1, Math.max(0, Math.round(x * (r.length - 1))))]; };

export async function initMap(onSelectUnit) {
  const style = await cleanBasemap().catch(() => basemap());
  flowHist = rangeHist(document.getElementById("flowHist"), { accent: () => css("--c-od"), onChange: () => { drawOD(); drawRoutes(); legend(); } });
  streetHist = rangeHist(document.getElementById("streetHist"), { colors: (i, n) => heatAt(i / Math.max(1, n - 1)), onChange: () => drawStreets() });
  map = new maplibregl.Map({
    container: "map", style, bounds: [[-58.535, -34.708], [-58.335, -34.528]],
    fitBoundsOptions: { padding: 24 }, minZoom: 9.5, maxZoom: 17,
    attributionControl: { compact: true, customAttribution: D.meta.attribution },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
  map.on("error", (e) => console.warn("map error:", e.error?.message || e));
  map.on("load", () => {
    console.info("map loaded");
    const ink = css("--ink"), mid = css("--ink-3"), stc = css("--c-station"), odc = css("--c-od"), bike = css("--c-bike");
    map.addSource("barrios", { type: "geojson", data: D.barrios });
    map.addSource("comunas", { type: "geojson", data: D.comunas });
    map.addSource("infra", { type: "geojson", data: EMPTY });
    map.addSource("streets", { type: "geojson", data: EMPTY, promoteId: "k" });
    map.addSource("od", { type: "geojson", data: EMPTY });
    map.addSource("heads", { type: "geojson", data: EMPTY });
    map.addSource("routes", { type: "geojson", data: EMPTY });
    map.addSource("stations", { type: "geojson", data: EMPTY });

    for (const lv of ["barrios", "comunas"]) {
      map.addLayer({ id: `${lv}-fill`, type: "fill", source: lv, paint: { "fill-color": ink, "fill-opacity": 0 } });
      map.addLayer({ id: `${lv}-line`, type: "line", source: lv,
        paint: { "line-color": lv === "comunas" ? ink : mid, "line-width": lv === "comunas" ? 1.1 : 0.6, "line-opacity": 0.7 } });
    }
    map.addLayer({ id: "infra", type: "line", source: "infra",
      layout: { "line-cap": "round" }, paint: { "line-color": bike, "line-width": ["interpolate", ["linear"], ["zoom"], 11, 1.3, 15, 3], "line-opacity": 0.9 } });
    map.addLayer({ id: "streets", type: "line", source: "streets", layout: { "line-cap": "round" },
      paint: { "line-color": ["interpolate", ["linear"], ["coalesce", ["feature-state", "x"], 0], ...heat().flatMap((c, i, a) => [i / (a.length - 1), c])],
        "line-opacity": ["case", ["boolean", ["feature-state", "on"], false], ["interpolate", ["linear"], ["coalesce", ["feature-state", "x"], 0], 0, 0.35, 0.6, 0.75, 1, 1], 0],
        "line-width": ["interpolate", ["linear"], ["coalesce", ["feature-state", "x"], 0], 0, 0.4, 0.5, 0.9, 0.8, 2.2, 1, 5] } });
    map.addLayer({ id: "routes-s", type: "line", source: "routes", filter: ["==", ["get", "s"], "s"],
      paint: { "line-color": mid, "line-width": ["get", "w"], "line-dasharray": [2, 1.5], "line-opacity": 0.9 } });
    map.addLayer({ id: "routes-i", type: "line", source: "routes", filter: ["==", ["get", "s"], "i"], layout: { "line-cap": "round" },
      paint: { "line-color": ink, "line-width": ["get", "w"], "line-opacity": 0.85 } });
    map.addLayer({ id: "od", type: "line", source: "od", layout: { "line-cap": "round" },
      paint: { "line-color": odc, "line-width": ["get", "w"], "line-opacity": ["get", "a"] } });
    map.addLayer({ id: "heads", type: "fill", source: "heads", paint: { "fill-color": odc, "fill-opacity": ["get", "a"] } });
    map.addLayer({ id: "od-labels", type: "symbol", source: "od", layout: {
      "symbol-placement": "line-center", "text-field": ["get", "label"], "text-size": 11, "text-font": ["Open Sans Regular", "Noto Sans Regular"],
      "visibility": "none" }, paint: { "text-color": ink, "text-halo-color": css("--bg"), "text-halo-width": 1.6 } });
    // stations sit below routes and flows so arrows stay readable
    map.addLayer({ id: "stations", type: "circle", source: "stations", paint: {
      "circle-radius": ["get", "r"], "circle-color": stc,
      "circle-stroke-color": ["case", ["get", "sel"], ink, stc], "circle-stroke-width": ["case", ["get", "sel"], 2.5, 0.9],
      "circle-opacity": ["*", ["get", "op"], 0.32], "circle-stroke-opacity": ["get", "op"] } }, "routes-s");

    map.moveLayer("infra", "routes-s");                 // bike lanes stay visible above street intensity
    // interactions
    map.on("click", "stations", (e) => selectStation(e.features[0].properties.i));
    map.on("click", "streets", (e) => showStreet(e.features[0]));
    for (const lv of ["barrios", "comunas"]) {
      map.on("click", `${lv}-fill`, (e) => {
        if (map.queryRenderedFeatures(e.point, { layers: ["stations", "streets"].filter((l) => map.getLayer(l)) }).length) return;
        const p = e.features[0].properties;
        const ref = lv === "comunas" ? `c:${p.comuna}` : `b:${p.barrio}`;
        if ((lv === "comunas") !== (S.level === "comuna") && S.level !== "station") return;
        focus = focus === ref ? null : ref;
        onSelectUnit?.(focus);
        drawOD(); showUnit(focus);
      });
    }
    for (const l of ["stations", "streets", "barrios-fill", "comunas-fill"]) {
      map.on("mouseenter", l, () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", l, () => { map.getCanvas().style.cursor = ""; });
    }
    const pop = new maplibregl.Popup({ closeButton: false, closeOnClick: false, maxWidth: "260px" });
    map.on("mousemove", "od", (e) => { pop.setLngLat(e.lngLat).setHTML(e.features[0].properties.tip).addTo(map); });
    map.on("mouseleave", "od", () => pop.remove());
    map.on("mousemove", "stations", (e) => { pop.setLngLat(e.lngLat).setHTML(e.features[0].properties.tip).addTo(map); });
    map.on("mouseleave", "stations", () => pop.remove());

    ready = true;
    applyLayerVisibility();
    updateMap();
  });

  document.querySelectorAll("#layers input[data-layer]").forEach((cb) => cb.addEventListener("change", async () => {
    layerOn[cb.dataset.layer] = cb.checked;
    if ((cb.dataset.layer === "streets" || cb.dataset.layer === "infra") && cb.checked) await ensureStreets();
    applyLayerVisibility(); updateMap();
  }));
  document.getElementById("detailClose").addEventListener("click", () => {
    document.getElementById("detail").hidden = true;
    selectedStation = null; focus = null; drawStations(); drawOD(); drawRoutes();
  });
}

async function ensureStreets() {
  await loadStreets();
  if (!map.getSource("streets")._loaded_once) {
    map.getSource("streets").setData(D.segs);
    map.getSource("infra").setData(D.ciclovias);
    map.getSource("streets")._loaded_once = true;
  }
}

function applyLayerVisibility() {
  if (!ready) return;
  const vis = (id, on) => map.getLayer(id) && map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
  vis("stations", layerOn.stations);
  vis("od", layerOn.od); vis("heads", layerOn.od); vis("od-labels", layerOn.od && S.labels);
  vis("routes-i", layerOn.routes); vis("routes-s", layerOn.routes);
  vis("streets", layerOn.streets); vis("infra", layerOn.infra);
  if (map.getLayer("infra")) {                           // beside, not over, the street intensity
    map.setPaintProperty("infra", "line-offset", layerOn.streets ? 3 : 0);
    map.setPaintProperty("infra", "line-width", layerOn.streets ? 1.1 : ["interpolate", ["linear"], ["zoom"], 11, 1.3, 15, 3]);
  }
  document.getElementById("flowBox").hidden = !layerOn.od;
  document.getElementById("streetBox").hidden = !layerOn.streets;
  vis("barrios-line", layerOn.barrios || S.level === "barrio"); vis("barrios-fill", S.level === "barrio");
  vis("comunas-line", layerOn.comunas); vis("comunas-fill", S.level === "comuna");
}

let aggVersion = 0;
export function setAggregate(a) { if (a !== agg) a.v ??= ++aggVersion; agg = a; }
// zoom to the stations of a filter unit ("s:", "b:", "c:")
export function fitUnit(ref) {
  if (!ready) return;
  const m = unitStations(ref);
  if (!m) { map.fitBounds([[-58.535, -34.708], [-58.335, -34.528]], { padding: 24, duration: 700 }); return; }
  const b = new maplibregl.LngLatBounds();
  D.stations.forEach((s) => m[s.i] && b.extend([s.lon, s.lat]));
  if (!b.isEmpty()) map.fitBounds(b, { padding: 120, maxZoom: 13, duration: 700 });
}
export async function updateMap() {
  if (!ready) return;
  agg ??= demoActive() ? aggregateDemo() : aggregate();
  applyLayerVisibility();
  drawStations(); drawOD(); drawRoutes();
  if (layerOn.streets) { await ensureStreets(); drawStreets(true); }
  legend();
  if (selectedStation != null) selectStation(selectedStation, true);
}

// ---------------- Stations ----------------
function drawStations() {
  const tot = agg.demo ? null : agg.dep.map((v, i) => v + agg.arr[i]);
  const max = tot ? Math.max(...tot) || 1 : 1;
  const stLevel = S.level === "station" && !agg.demo;
  const feats = D.stations.map((s) => {
    const v = tot ? tot[s.i] : 0;
    return { type: "Feature", geometry: { type: "Point", coordinates: [s.lon, s.lat] }, properties: {
      i: s.i, sel: s.i === selectedStation,
      op: s.i === selectedStation ? 1 : layerOn.streets ? 0.35 : stLevel ? 0.95 : 0.45,
      r: tot ? (stLevel ? 2 + 11 * Math.sqrt(v / max) : 1.5 + 5 * Math.sqrt(v / max)) : 2.5,
      tip: `<b>${s.name}</b><br>${s.barrio} · Comuna ${s.comuna}` + (tot ? `<br>${fmt(v)} ${t("trips")}` : "") } };
  });
  map.getSource("stations").setData({ type: "FeatureCollection", features: feats });
}

// ---------------- OD arrows ----------------
function anchor(lvl, u) {
  if (lvl === "station") return [D.stations[u].lon, D.stations[u].lat];
  if (lvl === "comuna") return D.meta.anchors.comuna[String(u)];
  return D.meta.anchors.barrio[D.barrioNames[u]];
}
function curve(a, b, n = 24) {
  const k = Math.cos((a[1] * Math.PI) / 180);
  const dx = (b[0] - a[0]) * k, dy = b[1] - a[1];
  const cx = (a[0] + b[0]) / 2 - (dy * 0.18) / k, cy = (a[1] + b[1]) / 2 + dx * 0.18;
  const pts = [];
  for (let j = 0; j <= n; j++) {
    const s = j / n, u = 1 - s;
    pts.push([u * u * a[0] + 2 * u * s * cx + s * s * b[0], u * u * a[1] + 2 * u * s * cy + s * s * b[1]]);
  }
  return pts;
}
function arrowHead(pts, w) {
  const k = Math.cos((pts[0][1] * Math.PI) / 180);
  const tip = pts[pts.length - 3], prev = pts[pts.length - 6];
  const dx = (tip[0] - prev[0]) * k, dy = tip[1] - prev[1], L = Math.hypot(dx, dy) || 1;
  // head size grows with flow width but never exceeds a fifth of the arrow's length
  const chordDeg = Math.hypot((pts[pts.length - 1][0] - pts[0][0]) * k, pts[pts.length - 1][1] - pts[0][1]);
  const ux = dx / L, uy = dy / L, size = Math.min(0.0009 + w * 0.00028, chordDeg * 0.2);
  const back = [tip[0] - (ux * size) / k, tip[1] - uy * size];
  const left = [back[0] - (uy * size * 0.55) / k, back[1] + ux * size * 0.55];
  const right = [back[0] + (uy * size * 0.55) / k, back[1] - ux * size * 0.55];
  return [[tip, left, right, tip]];
}
function topFlows() {
  // demographic mode: comuna matrix from the demographic cube
  const lvl = agg.demo ? "comuna" : S.level;
  let M, Du, U;
  if (agg.demo) { M = agg.M; Du = agg.Du; U = 16; } else ({ M, Du, U } = odMatrix(agg, lvl));
  const L = levelOf(lvl), list = [];
  const fo = focus && lvl !== "station" ? focus : null;
  const fu = fo ? (lvl === "comuna" ? +fo.slice(2) : D.barrioIdx[fo.slice(2)]) : null;
  const fs = lvl === "station" && selectedStation != null ? selectedStation : null;
  for (let o = 0; o < U; o++) for (let d = 0; d < U; d++) {
    const v = M[o * U + d];
    if (!v || o === d) continue;
    if (fu != null && o !== fu && d !== fu) continue;
    if (fs != null && o !== fs && d !== fs) continue;
    list.push({ o, d, v, rev: M[d * U + o], dur: Du[o * U + d] / v });
  }
  list.sort((a, b) => b.v - a.v);
  // distribution of every flow -> histogram; the selected range picks the arrows
  // the range resets to the strongest flows whenever filters or level change
  const levelKey = `${lvl}|${fu}|${fs}|${agg.v}`, vals = list.map((f) => f.v);
  if (levelKey !== flowLevel) { flowLevel = levelKey; flowHist.setTop(vals, lvl === "station" ? 150 : 60); }
  else flowHist.set(vals);
  const { lo, hi } = flowHist.range, total = agg.n;
  const inRange = list.filter((f) => f.v >= lo && f.v < hi);
  const trips = inRange.reduce((s, f) => s + f.v, 0);
  document.getElementById("flowInfo").textContent =
    `${fmt(Math.min(inRange.length, MAX_ARROWS))} ${t("flows_shown")}` + (inRange.length > MAX_ARROWS ? ` (${t("of")} ${fmt(inRange.length)})` : "") +
    ` · ${pct(trips / (total || 1), 1)} ${t("of_trips")}`;
  return { lvl, L, list: inRange.slice(0, MAX_ARROWS), total };
}
function drawOD() {
  if (!ready || !agg) return;
  const { lvl, L, list, total } = topFlows();
  const max = list[0]?.v || 1, lines = [], heads = [];
  shownFlows = list;
  const dense = list.length > 200;
  for (const f of list) {
    const a = anchor(lvl, f.o), b = anchor(lvl, f.d);
    if (!a || !b) continue;
    const x = Math.pow(f.v / max, 0.7);
    const w = (dense ? 0.6 : 1) + (dense ? 6 : 10) * x, pts = curve(a, b), alpha = (dense ? 0.25 : 0.4) + 0.55 * x;
    const tip = `<b>${L.name(f.o)} → ${L.name(f.d)}</b><br>${fmt(f.v)} ${t("trips")} (${pct(f.v / total, 2)})<br>` +
      `${L.name(f.d)} → ${L.name(f.o)}: ${fmt(f.rev)}<br>${t("net")}: ${fmt(f.v - f.rev)}<br>${t("k_dur_mean")}: ${fmt(f.dur / 60, 1)} ${t("min")}`;
    lines.push({ type: "Feature", geometry: { type: "LineString", coordinates: pts }, properties: { w, a: alpha, tip, label: fmt(f.v) } });
    heads.push({ type: "Feature", geometry: { type: "Polygon", coordinates: arrowHead(pts, w) }, properties: { a: Math.min(1, alpha + 0.2) } });
  }
  map.getSource("od").setData({ type: "FeatureCollection", features: lines });
  map.getSource("heads").setData({ type: "FeatureCollection", features: heads });
}

// ---------------- Streets ----------------
let streetVals = null, streetReq = 0, streetNote = "";
async function drawStreets(recount = false) {
  if (!D.segs || !layerOn.streets) return;
  if (recount || !streetVals) {
    const req = ++streetReq;
    document.getElementById("streetInfo").textContent = t("computing");
    // gender / age filters exist only at comuna level (privacy): streets then follow time filters only
    const vals = agg.demo ? segmentCounts() : await streetCounts(agg, S.strategy);
    if (req !== streetReq) return;
    streetNote = agg.demo ? " · " + t("streets_no_demo") : "";
    segCounts = streetVals = vals;
    streetHist.set(Array.from(streetVals).filter((v) => v > 0));
  }
  // colour = class of the 1-2-5 log scale (same classes as the legend); hidden outside the range
  const { lo, hi } = streetHist.range, nb = streetHist.bins();
  let n = 0;
  for (let k = 0; k < D.K; k++) {
    const v = streetVals[k], on = v > 0 && v >= lo && v < hi;
    if (on) n++;
    map.setFeatureState({ source: "streets", id: k }, { on, x: v > 0 ? streetHist.binOf(v) / Math.max(1, nb - 1) : 0 });
  }
  document.getElementById("streetInfo").textContent = `${fmt(n)} ${t("segments_shown")}${streetNote}`;
}

// ---------------- Routes ----------------
async function drawRoutes() {
  if (!ready) return;
  const src = map.getSource("routes");
  const origin = selectedStation;                       // fixed for this request
  if (!layerOn.routes || agg.demo) { src.setData(EMPTY); return; }
  if (origin == null) return drawTopRoutes(src);
  await loadStreets();
  const tree = await loadRoutes(origin);
  if (!tree || origin !== selectedStation) { if (selectedStation == null) src.setData(EMPTY); return; }
  // destinations: the selected destination station, else the top destinations from this station
  const dests = [];
  const dRef = S.dest && S.dest.startsWith("s:") ? +S.dest.slice(2) : null;
  if (dRef != null) dests.push({ d: dRef, v: 1 });
  else {
    for (let p = 0; p < D.P; p++) if (D.pO[p] === origin && D.pD[p] !== origin && agg.pairN[p]) dests.push({ d: D.pD[p], v: agg.pairN[p] });
    dests.sort((a, b) => b.v - a.v);
    dests.splice(Math.min(S.topN, 10));
  }
  const max = dests[0]?.v || 1, feats = [];
  for (const { d, v } of dests) for (const tag of ["s", "i"]) {
    const segs = routeSegments(tree[tag], d);
    const coords = segs.map((k) => D.segs.features[k]?.geometry.coordinates).filter(Boolean);
    if (coords.length) feats.push({ type: "Feature", geometry: { type: "MultiLineString", coordinates: coords },
      properties: { s: tag, w: tag === "i" ? 1.5 + 4 * Math.sqrt(v / max) : 1.4, d } });
  }
  src.setData({ type: "FeatureCollection", features: feats });
}

// Without a selected station: routes of the strongest station pairs among the
// flows currently selected (station level) or touching the focused unit.
let routeReq = 0;
async function drawTopRoutes(src) {
  const req = ++routeReq;
  await loadStreets();
  let pairs = [];
  if (S.level === "station") pairs = shownFlows.slice(0, MAX_DEFAULT_ROUTES).map((f) => ({ o: f.o, d: f.d, v: f.v }));
  else {
    const inUnit = (i) => !focus || (focus[0] === "c" ? `c:${D.stations[i].comuna}` : `b:${D.stations[i].barrio}`) === focus;
    for (let p = 0; p < D.P; p++) {
      const o = D.pO[p], d = D.pD[p], v = agg.pairN[p];
      if (v && o !== d && (inUnit(o) || inUnit(d))) pairs.push({ o, d, v });
    }
    pairs.sort((a, b) => b.v - a.v); pairs = pairs.slice(0, MAX_DEFAULT_ROUTES);
  }
  const trees = await Promise.all([...new Set(pairs.map((p) => p.o))].map(async (o) => [o, await loadRoutes(o)]));
  if (req !== routeReq || selectedStation != null) return;
  const tm = new Map(trees), max = pairs[0]?.v || 1, feats = [];
  for (const { o, d, v } of pairs) for (const tag of ["s", "i"]) {
    const tree = tm.get(o);
    if (!tree) continue;
    const coords = routeSegments(tree[tag], d).map((k) => D.segs.features[k]?.geometry.coordinates).filter(Boolean);
    if (coords.length) feats.push({ type: "Feature", geometry: { type: "MultiLineString", coordinates: coords },
      properties: { s: tag, w: tag === "i" ? 1.2 + 3.5 * Math.sqrt(v / max) : 1.2, d } });
  }
  src.setData({ type: "FeatureCollection", features: feats });
}

// ---------------- Detail panels ----------------
function openDetail(html) {
  const el = document.getElementById("detail");
  document.getElementById("detailBody").innerHTML = html;
  el.hidden = false;
}
async function selectStation(i, silent = false) {
  selectedStation = i;
  const s = D.stations[i];
  if (!silent) {
    drawStations(); drawOD(); drawRoutes();
    if (map.getZoom() < 13) map.flyTo({ center: [s.lon, s.lat], zoom: 13.3, duration: 900 });
  }
  if (agg.demo) {
    openDetail(`<h3>${s.name}</h3><p class="meta">#${s.id} · ${s.address} · ${s.barrio} · Comuna ${s.comuna}</p><p class="fnote">${t("demo_level")}</p>`);
    return;
  }
  const dep = agg.dep[i], arr = agg.arr[i];
  const topD = [], topO = [];
  for (let p = 0; p < D.P; p++) {
    const c = agg.pairN[p];
    if (!c) continue;
    if (D.pO[p] === i) topD.push([D.pD[p], c]);
    if (D.pD[p] === i) topO.push([D.pO[p], c]);
  }
  const li = (arr2) => arr2.sort((a, b) => b[1] - a[1]).slice(0, 5)
    .map(([j, c]) => `<li>${j === i ? "↺ " : ""}${D.stations[j].name} <span class="meta">· ${fmt(c)}</span></li>`).join("");
  openDetail(`<h3>${s.name}</h3><p class="meta">#${s.id} · ${s.address} · ${s.barrio} · Comuna ${s.comuna}</p>
    <div class="stat-grid">
      <div><b>${fmt(dep)}</b><span>${t("departures")}</span></div><div><b>${fmt(arr)}</b><span>${t("arrivals")}</span></div>
      <div><b>${fmt(dep + arr)}</b><span>${t("total")}</span></div><div><b>${fmt(arr - dep)}</b><span>${t("net")}</span></div>
    </div>
    <h4>${t("top_dest")}</h4><ol>${li(topD)}</ol><h4>${t("top_orig")}</h4><ol>${li(topO)}</ol>
    <h4>${t("temporal")}</h4><div class="mini" id="miniSt"></div>
    <p class="fnote">${layerOn.routes ? t("route_to") + " — " + t("st_infra") + " (—) / " + t("st_short") + " (- -)" : ""}</p>`);
  const st = D.stime[i];
  plotMini("miniSt", [
    { x: [...Array(24).keys()], y: st.dep_wd.map((v, h) => v + st.dep_we[h]), name: t("departures"), type: "bar", marker: { color: css("--ink") } },
    { x: [...Array(24).keys()], y: st.arr_wd.map((v, h) => v + st.arr_we[h]), name: t("arrivals"), type: "bar", marker: { color: css("--ink-3") } },
  ], { xaxis: { title: { text: t("hour") }, dtick: 3 }, barmode: "group" });
}

function showStreet(f) {
  const k = f.properties.k ?? f.id;
  const p = D.segs.features[k].properties;
  const v = segCounts?.[k] ?? 0;
  const base = k * 144, mon = new Array(12).fill(0), band = new Array(6).fill(0);
  for (let key = 0; key < 144; key++) {
    const c = D.segFlows[base + key];
    mon[Math.floor(key / 12)] += c; band[key % 6] += c;
  }
  const tot = agg.demo ? D.meta.routing.routable_trips : agg.n - agg.round;
  openDetail(`<h3>${p.name}</h3><p class="meta">${p.tipo} · ${p.infra ? t("infra_yes") : t("infra_no")}</p>
    <div class="stat-grid"><div><b>${fmt(v)}</b><span>${t("inferred_trips")}</span></div>
    <div><b>${pct(v / tot, 2)}</b><span>${t("share_routed")}</span></div></div>
    <h4>${t("by_band")}</h4><div class="mini" id="miniBand"></div><h4>${t("by_month")}</h4><div class="mini" id="miniMon"></div>
    <p class="fnote">${t("routes_disclaimer")}</p>`);
  const hb = D.meta.hour_bands.map(([a, b]) => `${a}–${b}h`);
  plotMini("miniBand", [{ x: hb, y: band, type: "bar", marker: { color: css("--ink") } }], {});
  plotMini("miniMon", [{ x: t("months"), y: mon, type: "bar", marker: { color: css("--ink") } }], {});
}

function showUnit(ref) {
  if (!ref) { document.getElementById("detail").hidden = true; return; }
  const lvl = ref[0] === "c" ? "comuna" : "barrio";
  const L = levelOf(lvl), u = lvl === "comuna" ? +ref.slice(2) : D.barrioIdx[ref.slice(2)];
  let M, U;
  if (agg.demo) { M = agg.M; U = 16; } else ({ M, U } = odMatrix(agg, lvl));
  let out = 0, inn = 0;
  for (let j = 0; j < U; j++) { out += M[u * U + j]; inn += M[j * U + u]; }
  const internal = M[u * U + u];
  const terr = D.meta.territories.find((x) => x.level === lvl && String(x.unit) === ref.slice(2));
  openDetail(`<h3>${L.name(u)}</h3><p class="meta">${lvl === "comuna" ? t("comuna") : t("barrio") + " · Comuna " + D.barrioComuna[ref.slice(2)]}
     ${terr ? ` · ${fmt(terr.area_km2, 1)} km² · ${fmt(terr.population_2010)} hab. (2010)` : ""}</p>
    <div class="stat-grid"><div><b>${fmt(out)}</b><span>${t("departures")}</span></div><div><b>${fmt(inn)}</b><span>${t("arrivals")}</span></div>
    <div><b>${fmt(internal)}</b><span>${t("internal")}</span></div><div><b>${fmt(inn - out)}</b><span>${t("net")}</span></div></div>
    <p class="fnote">${t("legend_od")}</p>`);
}

function legend() {
  const parts = [], sw = (v) => `<i class="sw" style="background:${css(v)}"></i>`;
  if (layerOn.stations && !agg.demo) parts.push(sw("--c-station") + t("legend_st"));
  if (layerOn.od) parts.push(sw("--c-od") + t("legend_od"));
  if (layerOn.routes && !agg.demo) parts.push(`<i class="sw ln"></i>` + (selectedStation != null ? t("legend_routes_st") : t("legend_routes_top")));
  if (layerOn.infra) parts.push(sw("--c-bike") + t("ly_infra"));
  if (agg.demo) parts.push(t("demo_level"));
  document.getElementById("legend").innerHTML = parts.join("<br>");
}

export function resetMapSelection() { selectedStation = null; focus = null; document.getElementById("detail").hidden = true; }
export function resizeMap() { map?.resize(); }
export function setLabels() { applyLayerVisibility(); }
export function focusStation(i) { if (ready) selectStation(i); }
export { unitStations };
