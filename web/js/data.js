// Data loading, decoding and the filter engine shared by map and report.
// Formats are produced by pipeline/08_export_web.py (see its docstring).

export const D = {};          // decoded datasets
export const S = defaultState();

export function defaultState() {
  return {
    m1: 1, m2: 12, daytype: "all", bands: new Set([0, 1, 2, 3, 4, 5]), level: "comuna",
    area: "", origin: "", dest: "", gender: "", age: "",
    topN: 20, labels: false, strategy: "i",
  };
}
export function resetState() { Object.assign(S, defaultState()); }

async function bytes(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  const buf = new Uint8Array(await res.arrayBuffer());
  if (buf[0] === 0x1f && buf[1] === 0x8b) {           // gzip magic: decompress in the browser
    const ds = new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"));
    return new Uint8Array(await new Response(ds).arrayBuffer());
  }
  return buf;                                          // already decoded by the server
}
const json = (url) => fetch(url).then((r) => r.json());

export async function loadCore() {
  const [meta, stations, pairsB, odB, cal, barrios, comunas, stime] = await Promise.all([
    json("data/meta.json"), json("data/stations.json"), bytes("data/pairs.bin.gz"), bytes("data/od.bin.gz"),
    json("data/calendar.json"), json("data/barrios.geojson"), json("data/comunas.geojson"), json("data/station_time.json"),
  ]);
  Object.assign(D, { meta, stations, cal, barrios, comunas, stime });
  const P = meta.counts.pairs, R = meta.counts.od_rows;
  const pb = pairsB.buffer;
  D.pO = new Uint16Array(pb, 0, P); D.pD = new Uint16Array(pb, 2 * P, P);
  D.dI = new Uint16Array(pb, 4 * P, P); D.dS = new Uint16Array(pb, 6 * P, P);
  const ob = odB.buffer;
  D.odP = new Uint32Array(ob, 0, R); D.odDur = new Uint32Array(ob, 4 * R, R);
  D.odN = new Uint16Array(ob, 8 * R, R); D.odKey = new Uint8Array(ob, 10 * R, R);
  D.P = P; D.R = R; D.N = stations.length;

  // territorial lookups
  D.barrioNames = [...new Set(barrios.features.map((f) => f.properties.barrio))].sort((a, b) => a.localeCompare(b, "es"));
  D.barrioIdx = Object.fromEntries(D.barrioNames.map((b, i) => [b, i]));
  D.stBarrio = Uint16Array.from(stations, (s) => D.barrioIdx[s.barrio]);
  D.stComuna = Uint8Array.from(stations, (s) => s.comuna);
  D.barrioComuna = {};
  barrios.features.forEach((f) => { D.barrioComuna[f.properties.barrio] = f.properties.comuna; });

  // calendar of 2025: month and weekend for each day of year
  D.doyMonth = new Uint8Array(367); D.doyWeekend = new Uint8Array(367); D.doyDow = new Uint8Array(367);
  for (let doy = 1; doy <= 365; doy++) {
    const d = new Date(Date.UTC(meta.year, 0, doy));
    D.doyMonth[doy] = d.getUTCMonth() + 1;
    const wd = d.getUTCDay();
    D.doyWeekend[doy] = wd === 0 || wd === 6 ? 1 : 0;
    D.doyDow[doy] = (wd + 6) % 7;                       // 0 = Monday
  }
}

let demoPromise = null, streetPromise = null;
export function loadDemo() {
  demoPromise ??= Promise.all([json("data/demo_gender.json"), json("data/demo_age.json")]).then(([g, a]) => { D.demoG = g; D.demoA = a; });
  return demoPromise;
}
export function loadStreets() {
  streetPromise ??= Promise.all([json("data/segments.geojson"), bytes("data/seg_flows.bin.gz"), bytes("data/edge_seg.bin.gz"),
    json("data/ciclovias.geojson")]).then(([segs, sf, es, cv]) => {
    D.segs = segs; D.segFlows = new Uint32Array(sf.buffer); D.edgeSeg = new Uint16Array(es.buffer); D.ciclovias = cv;
    D.K = segs.features.length;
  });
  return streetPromise;
}
const routeCache = new Map();
export async function loadRoutes(i) {
  if (routeCache.has(i)) return routeCache.get(i);
  const b = await bytes(`data/routes/${i}.bin.gz`).catch(() => null);
  if (!b) return null;
  const buf = b.buffer, out = {};
  let off = 0;
  for (const tag of ["i", "s"]) {
    const [n, m] = new Uint32Array(buf.slice(off, off + 8)); off += 8;
    const edge = new Uint16Array(buf.slice(off, off + 2 * n)); off += 2 * n;
    const parent = new Uint16Array(buf.slice(off, off + 2 * n)); off += 2 * n;
    const dest = new Uint16Array(buf.slice(off, off + 2 * m)); off += 2 * m;
    const last = new Uint16Array(buf.slice(off, off + 2 * m)); off += 2 * m;
    const byDest = new Map();
    dest.forEach((d, j) => byDest.set(d, last[j]));
    out[tag] = { edge, parent, byDest };
  }
  routeCache.set(i, out);
  return out;
}
// Walk the route tree back from destination station d -> list of segment indices k
export function routeSegments(tree, d) {
  const out = [];
  let k = tree.byDest.get(d);
  if (k === undefined) return out;
  while (k !== 65535) { out.push(D.edgeSeg[tree.edge[k]]); k = tree.parent[k]; }
  return out.reverse();
}

// ---------------- Units ----------------
// A unit reference is "s:<station index>", "b:<barrio name>" or "c:<comuna>".
export function unitStations(ref) {
  const m = new Uint8Array(D.N);
  if (!ref) return null;
  const [k, v] = [ref[0], ref.slice(2)];
  for (let i = 0; i < D.N; i++) {
    const s = D.stations[i];
    m[i] = k === "s" ? i === +v : k === "b" ? s.barrio === v : s.comuna === +v;
  }
  return m;
}
export function unitComuna(ref) {
  if (!ref) return null;
  const [k, v] = [ref[0], ref.slice(2)];
  return k === "c" ? +v : k === "b" ? D.barrioComuna[v] : D.stations[+v].comuna;
}
export function unitLabel(ref) {
  if (!ref) return "";
  const [k, v] = [ref[0], ref.slice(2)];
  return k === "s" ? D.stations[+v].name : k === "b" ? v : `Comuna ${v}`;
}
export const levelOf = (lvl) => ({
  station: { U: D.N, o: (p) => D.pO[p], d: (p) => D.pD[p], name: (u) => D.stations[u].name, ref: (u) => `s:${u}` },
  barrio: { U: D.barrioNames.length, o: (p) => D.stBarrio[D.pO[p]], d: (p) => D.stBarrio[D.pD[p]], name: (u) => D.barrioNames[u], ref: (u) => `b:${D.barrioNames[u]}` },
  comuna: { U: 16, o: (p) => D.stComuna[D.pO[p]], d: (p) => D.stComuna[D.pD[p]], name: (u) => `Comuna ${u}`, ref: (u) => `c:${u}` },
}[lvl]);

// ---------------- Masks ----------------
export function keyMask(state = S, m1 = state.m1, m2 = state.m2) {
  const km = new Uint8Array(144);
  for (let m = m1; m <= m2; m++) for (let we = 0; we < 2; we++) {
    if (state.daytype === "wd" && we) continue;
    if (state.daytype === "we" && !we) continue;
    for (const b of state.bands) km[(m - 1) * 12 + we * 6 + b] = 1;
  }
  return km;
}
export function hourInBands(h, bands = S.bands) {
  const hb = D.meta.hour_bands;
  for (const b of bands) if (h >= hb[b][0] && h < hb[b][1]) return true;
  return false;
}
export function selectedDays(state = S, m1 = state.m1, m2 = state.m2) {
  let n = 0;
  for (let doy = 1; doy <= 365; doy++) {
    const m = D.doyMonth[doy], we = D.doyWeekend[doy];
    if (m < m1 || m > m2) continue;
    if (state.daytype === "wd" && we) continue;
    if (state.daytype === "we" && !we) continue;
    n++;
  }
  return n;
}

// ---------------- Main aggregation (no demographic filter) ----------------
export function aggregate(state = S) {
  const km = keyMask(state);
  const oM = unitStations(state.origin), dM = unitStations(state.dest), aM = unitStations(state.area);
  const pm = new Uint8Array(D.P);
  for (let p = 0; p < D.P; p++) {
    const o = D.pO[p], d = D.pD[p];
    pm[p] = (!oM || oM[o]) && (!dM || dM[d]) && (!aM || aM[o] || aM[d]) ? 1 : 0;
  }
  const pairN = new Float64Array(D.P), pairDur = new Float64Array(D.P);
  for (let r = 0; r < D.R; r++) {
    const p = D.odP[r];
    if (pm[p] && km[D.odKey[r]]) { pairN[p] += D.odN[r]; pairDur[p] += D.odDur[r]; }
  }
  let n = 0, dur = 0, nr = 0, distI = 0, durR = 0, round = 0, sameC = 0;
  const dep = new Float64Array(D.N), arr = new Float64Array(D.N);
  for (let p = 0; p < D.P; p++) {
    const c = pairN[p];
    if (!c) continue;
    const o = D.pO[p], d = D.pD[p];
    n += c; dur += pairDur[p]; dep[o] += c; arr[d] += c;
    if (o === d) round += c;
    else if (D.dI[p] > 0) { nr += c; distI += c * D.dI[p]; durR += pairDur[p]; }
    if (D.stComuna[o] === D.stComuna[d]) sameC += c;
  }
  let orig = 0, dest = 0, act = 0;
  for (let i = 0; i < D.N; i++) { if (dep[i]) orig++; if (arr[i]) dest++; if (dep[i] || arr[i]) act++; }
  return { demo: false, km, pairN, pairDur, n, dur, nr, distI, durR, round, sameC, dep, arr, orig, dest, act, days: selectedDays(state) };
}

// Unit-level OD matrix from pair counts (any level). Returns {U, M (U*U), dur (U*U)}
export function odMatrix(agg, lvl) {
  const L = levelOf(lvl), U = L.U, M = new Float64Array(U * U), Du = new Float64Array(U * U);
  for (let p = 0; p < D.P; p++) {
    const c = agg.pairN[p];
    if (!c) continue;
    const i = L.o(p) * U + L.d(p);
    M[i] += c; Du[i] += agg.pairDur[p];
  }
  return { U, M, Du, L };
}

// ---------------- Demographic aggregation (comuna level) ----------------
export function demoActive(state = S) { return !!(state.gender || state.age); }
export function aggregateDemo(state = S) {
  const cube = state.gender ? D.demoG : D.demoA;
  const cats = state.gender ? D.meta.genders : D.meta.ages;
  const cat = cats.indexOf(state.gender || state.age);
  const km = keyMask(state);
  const oc = unitComuna(state.origin), dc = unitComuna(state.dest), ac = unitComuna(state.area);
  const M = new Float64Array(16 * 16), Du = new Float64Array(16 * 16);
  let n = 0, dur = 0, nr = 0, dist = 0;
  const L = cube.n.length;
  for (let r = 0; r < L; r++) {
    if (cube.cat[r] !== cat || !km[cube.key[r]]) continue;
    const o = cube.oc[r], d = cube.dc[r];
    if ((oc && o !== oc) || (dc && d !== dc) || (ac && o !== ac && d !== ac)) continue;
    n += cube.n[r]; dur += cube.dur[r]; nr += cube.nr[r]; dist += cube.dist[r];
    M[o * 16 + d] += cube.n[r]; Du[o * 16 + d] += cube.dur[r];
  }
  return { demo: true, n, dur, nr, dist, M, Du, days: selectedDays(state) };
}
// Breakdown of the current (non-demographic) filters by every category of an attribute
export function demoBreakdown(attr, state = S) {
  const cube = attr === "gender" ? D.demoG : D.demoA;
  const cats = attr === "gender" ? D.meta.genders : D.meta.ages;
  const km = keyMask(state);
  const oc = unitComuna(state.origin), dc = unitComuna(state.dest), ac = unitComuna(state.area);
  const out = cats.map((c) => ({ cat: c, n: 0, dur: 0, nr: 0, dist: 0 }));
  for (let r = 0; r < cube.n.length; r++) {
    if (!km[cube.key[r]]) continue;
    const o = cube.oc[r], d = cube.dc[r];
    if ((oc && o !== oc) || (dc && d !== dc) || (ac && o !== ac && d !== ac)) continue;
    const x = out[cube.cat[r]];
    x.n += cube.n[r]; x.dur += cube.dur[r]; x.nr += cube.nr[r]; x.dist += cube.dist[r];
  }
  return out;
}

// ---------------- Calendar (day x hour x origin comuna) ----------------
export function calendarSeries(state = S, m1 = state.m1, m2 = state.m2) {
  const c = D.cal, oc = unitComuna(state.origin) || unitComuna(state.area);
  const byHour = new Float64Array(24), byDoy = new Float64Array(366), hd = new Float64Array(7 * 24);
  for (let r = 0; r < c.n.length; r++) {
    const doy = c.doy[r], m = D.doyMonth[doy], we = D.doyWeekend[doy], h = c.hour[r];
    if (m < m1 || m > m2) continue;
    if (state.daytype === "wd" && we) continue;
    if (state.daytype === "we" && !we) continue;
    if (!hourInBands(h, state.bands)) continue;
    if (oc && c.oc[r] !== oc) continue;
    const v = c.n[r];
    byHour[h] += v; byDoy[doy] += v;
    hd[D.doyDow[doy] * 24 + h] += v;
  }
  return { byHour, byDoy, hd, comunaFilter: oc };
}

// ---------------- Streets ----------------
export function segmentCounts(state = S) {
  const km = keyMask(state), keys = [];
  km.forEach((v, k) => v && keys.push(k));
  const out = new Float64Array(D.K);
  for (let k = 0; k < D.K; k++) {
    let s = 0;
    const base = k * 144;
    for (const key of keys) s += D.segFlows[base + key];
    out[k] = s;
  }
  return out;
}
