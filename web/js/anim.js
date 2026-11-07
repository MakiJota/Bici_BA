// "Animación" tab: one day of EcoBici trips moving along their reconstructed routes
// (deck.gl TripsLayer). Departure / arrival times are observed; the path is the
// inferred route (step 06) traversed at constant speed. Not GPS.
import { D, loadStreets } from "./data.js";
import { fmt, getLang, pct, t } from "./i18n.js";

const CONFIG = {
  background: [6, 6, 6],
  roadBase: [44, 44, 44, 255],
  ramp: [[44, 44, 44], [105, 105, 105], [185, 185, 185], [255, 255, 255]],   // few -> many
  tripInfra: [255, 255, 255],      // trail on a bike lane
  tripStreet: [125, 125, 125],     // trail on a regular street
  tripOpacity: 0.6,
  trailSeconds: 300,
  pointSeconds: 240,
  tripWidthPx: 2,
  roadWidthPx: 1.2,
  rampMaxQuantile: 0.995,
  binS: 900,
};
const DECK_URL = "https://unpkg.com/deck.gl@8.9.35/dist.min.js";
const $ = (id) => document.getElementById(id);
const rgb = (c) => `rgb(${c[0]},${c[1]},${c[2]})`;
const NB = 96;                                         // 15-minute bins in a day

let inited = false, deckgl = null, days = null, active = false;
let net = null;                                        // flat street network
let day = null;                                        // decoded day file
let built = null;                                      // TripsLayer arrays for the current strategy
let focusStation = -1;                                 // -1 = all stations
let strategy = "I", time = 7 * 3600, playing = false, speed = 600, lastFrame = null, shownBin = -1, shownMode = null;
const show = { trips: true, ends: true, net: true, comunas: true };
let netMode = "bin", netColors = null, lastStats = 0;

function loadScript(src) {
  return new Promise((res, rej) => {
    if (window.deck) return res();
    const s = document.createElement("script");
    s.src = src; s.onload = res; s.onerror = () => rej(new Error("deck.gl"));
    document.head.appendChild(s);
  });
}
async function bytes(url) {
  const buf = new Uint8Array(await (await fetch(url)).arrayBuffer());
  if (buf[0] === 0x1f && buf[1] === 0x8b) {
    const ds = new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"));
    return new Uint8Array(await new Response(ds).arrayBuffer());
  }
  return buf;
}
const fmtTime = (s) => `${String(Math.floor(s / 3600) % 24).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`;

// ---------------- Street network (from segments.geojson) ----------------
function buildNetwork() {
  const feats = D.segs.features, K = feats.length;
  let nv = 0;
  const lines = feats.map((f) => (f.geometry.type === "LineString" ? f.geometry.coordinates : f.geometry.coordinates.flat()));
  lines.forEach((c) => { nv += c.length; });
  const path = new Float32Array(nv * 2), start = new Uint32Array(K + 1), vSeg = new Uint32Array(nv);
  const len = new Float32Array(K), infra = new Uint8Array(K);
  let v = 0;
  lines.forEach((c, k) => {
    start[k] = v;
    let L = 0;
    for (let j = 0; j < c.length; j++) {
      path[2 * v] = c[j][0]; path[2 * v + 1] = c[j][1]; vSeg[v] = k; v++;
      if (j) L += dist(c[j - 1][0], c[j - 1][1], c[j][0], c[j][1]);
    }
    len[k] = L; infra[k] = feats[k].properties.infra;
  });
  start[K] = v;
  net = { K, path, start, vSeg, len, infra, nv };
}
const KX = 111320 * Math.cos((34.6 * Math.PI) / 180), KY = 110570;
const dist = (x1, y1, x2, y2) => Math.hypot((x2 - x1) * KX, (y2 - y1) * KY);

// ---------------- Day file ----------------
async function loadDay(meta) {
  const b = await bytes(`data/anim/${meta.file}`), buf = b.buffer;
  let off = 0;
  const u32 = (n) => { const a = new Uint32Array(buf, off, n); off += 4 * n; return a; };
  const u16 = (n) => { const a = new Uint16Array(buf, off, n); off += 2 * n; return a; };
  const [nT, nP, nI, nS] = u32(4);
  const startI = u32(nP + 1), startS = u32(nP + 1);
  const pO = u16(nP), pD = u16(nP), refsI = u16(nI), refsS = u16(nS);
  const tPair = u16(nT), tStart = u16(nT), tEnd = u16(nT);
  day = { meta, nT, nP, pO, pD, refs: { I: [startI, refsI], S: [startS, refsS] }, tPair, tStart, tEnd };
  buildTrips();
}

// Assemble per-pair paths from segment refs, then per-trip vertices with timestamps.
function buildTrips() {
  const [rStart, refs] = day.refs[strategy];
  const { nP, nT } = day;
  // pass 1: count vertices per pair
  const pairV = new Uint32Array(nP + 1);
  for (let p = 0; p < nP; p++) {
    let n = 0;
    for (let r = rStart[p]; r < rStart[p + 1]; r++) { const k = refs[r] >> 1; n += net.start[k + 1] - net.start[k] - (n ? 1 : 0); }
    pairV[p + 1] = pairV[p] + n;
  }
  const pv = new Float32Array(pairV[nP] * 2), pc = new Float32Array(pairV[nP]), pi = new Uint8Array(pairV[nP]);
  const pairLen = new Float32Array(nP);
  const segCnt = new Uint32Array(nP + 1);
  for (let p = 0; p < nP; p++) segCnt[p + 1] = segCnt[p] + (rStart[p + 1] - rStart[p]);
  const segK = new Uint16Array(segCnt[nP]), segMid = new Float32Array(segCnt[nP]);
  for (let p = 0; p < nP; p++) {
    let w = pairV[p], cum = 0, s = segCnt[p];
    for (let r = rStart[p]; r < rStart[p + 1]; r++) {
      const k = refs[r] >> 1, rev = refs[r] & 1, a = net.start[k], b = net.start[k + 1], n = b - a;
      segK[s] = k; segMid[s] = cum + net.len[k] / 2; s++;
      for (let j = 0; j < n; j++) {
        const v = rev ? b - 1 - j : a + j;
        if (j === 0 && w > pairV[p]) continue;               // shared junction vertex
        const x = net.path[2 * v], y = net.path[2 * v + 1];
        if (w > pairV[p]) cum += dist(pv[2 * (w - 1)], pv[2 * (w - 1) + 1], x, y);
        pv[2 * w] = x; pv[2 * w + 1] = y; pc[w] = cum; pi[w] = net.infra[k]; w++;
      }
    }
    pairLen[p] = cum;
  }
  // pass 2: trips (optionally only those leaving or arriving at one station,
  // like the legacy R experiment with station 227 and its destinations)
  const keep = (i) => focusStation < 0 || day.pO[day.tPair[i]] === focusStation || day.pD[day.tPair[i]] === focusStation;
  const tripStartIdx = new Uint32Array(nT + 1);
  for (let i = 0; i < nT; i++) { const p = day.tPair[i]; tripStartIdx[i + 1] = tripStartIdx[i] + (keep(i) && pairLen[p] > 0 ? pairV[p + 1] - pairV[p] : 0); }
  const NV = tripStartIdx[nT];
  const path = new Float32Array(NV * 2), times = new Float32Array(NV), colors = new Uint8Array(NV * 4);
  const cnt = new Uint16Array(net.K * NB);
  const startsPerBin = new Float64Array(NB), activePerBin = new Float64Array(NB);
  const sPos = new Float32Array(nT * 2), ePos = new Float32Array(nT * 2), sT = new Float32Array(nT), eT = new Float32Array(nT);
  for (let i = 0; i < nT; i++) {
    const p = day.tPair[i], t0 = day.tStart[i] * 60, t1 = day.tEnd[i] * 60, o = D.stations[day.pO[p]], d = D.stations[day.pD[p]];
    if (!keep(i)) { sT[i] = eT[i] = -1e9; continue; }   // filtered out: never inside the visible window
    sPos[2 * i] = o.lon; sPos[2 * i + 1] = o.lat; ePos[2 * i] = d.lon; ePos[2 * i + 1] = d.lat; sT[i] = t0; eT[i] = t1;
    startsPerBin[Math.min(NB - 1, Math.floor(t0 / CONFIG.binS))]++;
    for (let b = Math.floor(t0 / CONFIG.binS); b <= Math.min(NB - 1, Math.floor(t1 / CONFIG.binS)); b++) activePerBin[b]++;
    const L = pairLen[p];
    if (!(L > 0)) continue;
    let w = tripStartIdx[i];
    for (let v = pairV[p]; v < pairV[p + 1]; v++, w++) {
      path[2 * w] = pv[2 * v]; path[2 * w + 1] = pv[2 * v + 1];
      times[w] = t0 + ((t1 - t0) * pc[v]) / L;
      const c = pi[v] ? CONFIG.tripInfra : CONFIG.tripStreet;
      colors[4 * w] = c[0]; colors[4 * w + 1] = c[1]; colors[4 * w + 2] = c[2]; colors[4 * w + 3] = 255;
    }
    for (let s = segCnt[p]; s < segCnt[p + 1]; s++) {
      const b = Math.min(NB - 1, Math.floor((t0 + ((t1 - t0) * segMid[s]) / L) / CONFIG.binS));
      const idx = segK[s] * NB + b;
      if (cnt[idx] < 65535) cnt[idx]++;
    }
  }
  // colour-scale ceilings
  const nz = [];
  for (let j = 0; j < cnt.length; j++) if (cnt[j]) nz.push(cnt[j]);
  nz.sort((a, b) => a - b);
  const maxBin = Math.max(1, nz[Math.floor(CONFIG.rampMaxQuantile * (nz.length - 1))] || 1);
  const tot = new Float64Array(net.K);
  for (let k = 0; k < net.K; k++) for (let b = 0; b < NB; b++) tot[k] += cnt[k * NB + b];
  const tz = Array.from(tot).filter((x) => x > 0).sort((a, b) => a - b);
  const maxCum = Math.max(1, tz[Math.floor(CONFIG.rampMaxQuantile * (tz.length - 1))] || 1);
  const cumStarts = []; startsPerBin.reduce((a, v, i) => (cumStarts[i] = a + v), 0);
  built = { path, times, colors, tripStartIdx, cnt, maxBin, maxCum, startsPerBin, activePerBin, cumStarts, sPos, ePos, sT, eT, nT };
  // data objects are created once per build: a new object every frame would make
  // deck.gl re-upload all vertex attributes to the GPU on each frame
  built.tripData = { length: nT, startIndices: tripStartIdx,
    attributes: { getPath: { value: path, size: 2 }, getTimestamps: { value: times, size: 1 }, getColor: { value: colors, size: 4, normalized: true } } };
  built.startData = { length: nT, attributes: { getPosition: { value: sPos, size: 2 }, getFilterValue: { value: sT, size: 1 } } };
  built.endData = { length: nT, attributes: { getPosition: { value: ePos, size: 2 }, getFilterValue: { value: eT, size: 1 } } };
  built.version = (built.version || 0) + 1;
  shownBin = -1;
}

// ---------------- Layers ----------------
function rampColor(x) {
  const r = CONFIG.ramp, s = Math.min(Math.max(x, 0), 1) * (r.length - 1);
  const i = Math.min(Math.floor(s), r.length - 2), f = s - i;
  return [0, 1, 2].map((k) => Math.round(r[i][k] + (r[i + 1][k] - r[i][k]) * f));
}
function fillNetColors(bin) {
  const cols = new Uint8Array(net.nv * 4), mx = netMode === "bin" ? built.maxBin : built.maxCum;
  const lut = new Array(net.K);
  for (let k = 0; k < net.K; k++) {
    let n = 0;
    if (netMode === "bin") n = built.cnt[k * NB + bin];
    else for (let b = 0; b <= bin; b++) n += built.cnt[k * NB + b];
    lut[k] = n > 0 ? rampColor(Math.log1p(n) / Math.log1p(mx)) : null;
  }
  for (let v = 0; v < net.nv; v++) {
    const c = lut[net.vSeg[v]] || CONFIG.roadBase, o = 4 * v;
    cols[o] = c[0]; cols[o + 1] = c[1]; cols[o + 2] = c[2]; cols[o + 3] = 255;
  }
  netColors = cols;
}
function layers() {
  const { TripsLayer, PathLayer, ScatterplotLayer, GeoJsonLayer, DataFilterExtension } = window.deck;
  const bin = Math.min(NB - 1, Math.floor(time / CONFIG.binS));
  const netOn = show.net || !show.trips;
  if (netOn && (bin !== shownBin || netMode !== shownMode || !net.data || net.dataOn !== netOn)) {
    fillNetColors(bin); shownBin = bin; shownMode = netMode;
    net.data = { length: net.K, startIndices: net.start,
      attributes: { getPath: { value: net.path, size: 2 }, getColor: { value: netColors, size: 4, normalized: true } } };
    net.dataOn = true;
  } else if (!netOn && net.dataOn !== false) {
    net.data = { length: net.K, startIndices: net.start, attributes: { getPath: { value: net.path, size: 2 } } };
    net.dataOn = false;
  }
  const additive = { depthTest: false, blend: true, blendFunc: [770, 1, 1, 1], blendEquation: 32774 };
  const out = [new PathLayer({
    id: "net", data: net.data,
    _pathType: "open", getColor: CONFIG.roadBase, widthUnits: "pixels", getWidth: CONFIG.roadWidthPx,
  })];
  if (show.comunas) out.push(new GeoJsonLayer({ id: "comunas", data: D.comunas, stroked: true, filled: false,
    getLineColor: [150, 150, 150, 140], lineWidthUnits: "pixels", getLineWidth: 1 }));
  if (show.trips) out.push(new TripsLayer({
    id: "trips", data: built.tripData,
    _pathType: "open", opacity: focusStation >= 0 ? 0.95 : CONFIG.tripOpacity, widthUnits: "pixels",
    getWidth: focusStation >= 0 ? 4 : CONFIG.tripWidthPx, updateTriggers: { getWidth: focusStation },
    capRounded: true, jointRounded: true, fadeTrail: true, trailLength: CONFIG.trailSeconds, currentTime: time, parameters: additive,
  }));
  if (show.ends) {
    const pts = (id, data, filled) => new ScatterplotLayer({
      id, data,
      filled, stroked: !filled, getFillColor: [255, 255, 255], getLineColor: [255, 255, 255], lineWidthUnits: "pixels", getLineWidth: 1,
      radiusUnits: "pixels", getRadius: filled ? 2.2 : 3.5, opacity: 0.85,
      extensions: [new DataFilterExtension({ filterSize: 1 })], filterRange: [time - CONFIG.pointSeconds, time], parameters: additive,
    });
    out.push(pts("starts", built.startData, true), pts("ends", built.endData, false));
  }
  if (focusStation >= 0) {
    const s = D.stations[focusStation];
    out.push(new ScatterplotLayer({ id: "focus", data: [s], getPosition: (d) => [d.lon, d.lat], filled: true, stroked: true,
      getFillColor: [6, 6, 6], getLineColor: [255, 255, 255], lineWidthUnits: "pixels", getLineWidth: 2.5,
      radiusUnits: "pixels", getRadius: 9 }));
  }
  return out;
}

// ---------------- Panel ----------------
function drawChart() {
  const c = $("aChart"), ctx = c.getContext("2d"), dpr = devicePixelRatio || 1, w = c.clientWidth, h = c.clientHeight;
  c.width = w * dpr; c.height = h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
  const s = built.startsPerBin, cum = built.cumStarts, maxS = Math.max(...s) || 1, maxC = cum[NB - 1] || 1, bw = w / NB;
  ctx.fillStyle = "#8a8a8a";
  s.forEach((v, i) => { const bh = (v / maxS) * (h - 14); ctx.fillRect(i * bw, h - bh, Math.max(bw - 0.6, 0.5), bh); });
  ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 1.4; ctx.beginPath();
  cum.forEach((v, i) => { const x = i * bw, y = h - (v / maxC) * (h - 14); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.stroke();
  const x = (Math.min(time, 86400) / 86400) * w;
  ctx.strokeStyle = "#ffffff"; ctx.setLineDash([2, 2]); ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke(); ctx.setLineDash([]);
  ctx.fillStyle = "#8a8a8a"; ctx.font = "10px Inter, sans-serif";
  [0, 6, 12, 18].forEach((hh) => ctx.fillText(String(hh).padStart(2, "0"), (hh / 24) * w + 2, 10));
}
function onBikeLaneNow() {
  // share of trips under way whose current position is on a ciclovía segment
  let on = 0, n = 0;
  const { tripStartIdx: S, times: T, colors: C } = built;
  for (let i = 0; i < built.nT; i++) {
    const a = S[i], b = S[i + 1];
    if (b - a < 2 || T[a] > time || T[b - 1] < time) continue;
    let lo = a, hi = b - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (T[m] <= time) lo = m; else hi = m; }
    n++; if (C[4 * hi] === CONFIG.tripInfra[0]) on++;
  }
  return n ? on / n : NaN;
}
function updatePanel(force = false) {
  const bin = Math.min(NB - 1, Math.floor(time / CONFIG.binS));
  $("aStarted").textContent = fmt(built.cumStarts[bin] || 0);
  $("aActive").textContent = fmt(built.activePerBin[bin] || 0);
  $("aBin").textContent = fmt(built.startsPerBin[bin] || 0);
  const now = performance.now();
  if (force || now - lastStats > 250) { $("aLane").textContent = pct(onBikeLaneNow(), 0); lastStats = now; }
  $("aClock").textContent = fmtTime(time);
  $("aSlider").value = time;
  drawChart();
}
function render(force = false) { if (!deckgl) return; deckgl.setProps({ layers: layers() }); updatePanel(force); }

let frames = 0, renderMs = 0;
function frame(ts) {
  if (!active) { lastFrame = null; return; }
  frames++;
  if (playing) {
    if (lastFrame !== null) time += ((ts - lastFrame) / 1000) * speed;
    if (time >= 86400) { time = 86400; setPlaying(false); }
    const t0 = performance.now();
    render();
    renderMs = performance.now() - t0;
  }
  lastFrame = ts;
  requestAnimationFrame(frame);
}
function setPlaying(p) { playing = p; $("aPlay").innerHTML = p ? "&#10074;&#10074;" : "&#9654;"; }

function dayLabel(d) {
  const dt = new Date(`${d.date}T12:00:00Z`);
  return dt.toLocaleDateString(getLang() === "es" ? "es-AR" : "en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }) +
    ` · ${fmt(d.trips)} ${t("trips")}`;
}
export function relabelAnim() {
  if (!inited) return;
  $("aDay").innerHTML = days.days.map((d, i) => `<option value="${i}">${dayLabel(d)}</option>`).join("");
  $("aDay").value = String(days.days.indexOf(day.meta));
  $("aStation").innerHTML = `<option value="-1">${t("a_all_stations")}</option>` + [...D.stations]
    .sort((a, b) => a.name.localeCompare(b.name, "es")).map((s) => `<option value="${s.i}">${s.name} (#${s.id})</option>`).join("");
  $("aStation").value = String(focusStation);
  $("aLgStart").title = t("a_start");
  updatePanel(true);
}

// ---------------- Init ----------------
export async function openAnim() {
  active = true;
  if (!inited) {
    $("animLoading").hidden = false;
    await Promise.all([loadScript(DECK_URL), loadStreets()]);
    days = await (await fetch("data/anim/days.json")).json();
    buildNetwork();
    await loadDay(days.days[1]);                        // busiest day of the year
    deckgl = new window.deck.DeckGL({
      container: "anim",
      initialViewState: { longitude: -58.445, latitude: -34.612, zoom: innerWidth < 700 ? 10.6 : 11.6, pitch: 0, bearing: 0 },
      map: false,                                       // no basemap: the street network is the map (as in FlowSense)
      controller: true, parameters: { clearColor: CONFIG.background.map((v) => v / 255).concat(1) }, layers: [],
    });
    wire();
    inited = true;
    relabelAnim();
    $("aLgInfra").style.background = rgb(CONFIG.tripInfra);
    $("aLgStreet").style.background = rgb(CONFIG.tripStreet);
    $("aLgRamp").style.background = `linear-gradient(90deg, ${CONFIG.ramp.map(rgb).join(",")})`;
    $("animLoading").hidden = true;
  }
  render(true);
  requestAnimationFrame(frame);
}
export function closeAnim() { active = false; if (inited) setPlaying(false); }
// read-only hook for automated checks
window.__anim = { get state() { return { active, playing, time, inited, strategy, focusStation, frames, renderMs: Math.round(renderMs), vertices: built ? built.times.length : 0 }; } };

function wire() {
  $("aPlay").onclick = () => { if (time >= 86400) time = 0; setPlaying(!playing); };
  $("aSlider").oninput = (e) => { time = +e.target.value; render(true); };
  $("aSpeed").onchange = (e) => { speed = +e.target.value; };
  $("aDay").onchange = async (e) => { setPlaying(false); await loadDay(days.days[+e.target.value]); render(true); };
  $("aStrategy").onclick = (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    $("aStrategy").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    strategy = b.dataset.v; buildTrips(); render(true);
  };
  for (const [id, key] of [["aTrips", "trips"], ["aEnds", "ends"], ["aNet", "net"], ["aComunas", "comunas"]]) {
    $(id).onchange = (e) => { show[key] = e.target.checked; shownBin = -1; render(true); };
  }
  $("aNetMode").onchange = (e) => { netMode = e.target.value; shownBin = -1; render(true); };
  $("aStation").onchange = (e) => {
    focusStation = +e.target.value; buildTrips(); render(true);
    if (focusStation >= 0) {
      const s = D.stations[focusStation];
      deckgl.setProps({ initialViewState: { longitude: s.lon, latitude: s.lat, zoom: 13.2, pitch: 0, bearing: 0, transitionDuration: 800 } });
    }
  };
  addEventListener("resize", () => inited && drawChart());
  addEventListener("keydown", (e) => {
    if (active && e.code === "Space" && !["SELECT", "INPUT"].includes(document.activeElement?.tagName)) { e.preventDefault(); $("aPlay").click(); }
  });
  const q = new URLSearchParams(location.search);   // ?t=HH:MM&play=1 for screenshots / sharing
  if (q.get("t")) { const [h, m] = q.get("t").split(":").map(Number); time = h * 3600 + (m || 0) * 60; }
  if (q.get("play") === "1") setPlaying(true);
}
