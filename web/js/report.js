// Section B — analytical report. Every figure is computed from the published
// aggregates under the current filters, except where a note says otherwise.
import { D, S, calendarSeries, demoBreakdown, levelOf, loadStreets, odMatrix, segmentCounts, unitComuna } from "./data.js";
import { fmt, pct, t } from "./i18n.js";
import { css, greys, message, plot } from "./charts.js";

const MIN = () => D.meta.min_cell;
let onStationClick = null;
export function initReport(cb) {
  onStationClick = cb;
  const groups = ["all", "comuna", "barrio", "gender", "age_group", "daytype", "hour", "bike_model"];
  const vars = ["duration_min", "distance_km", "speed_kmh"];
  const gSel = document.getElementById("ddsGroup"), vSel = document.getElementById("ddsVar");
  gSel.innerHTML = groups.map((g) => `<option value="${g}">${t("grp_" + g)}</option>`).join("");
  vSel.innerHTML = vars.map((v) => `<option value="${v}">${t("var_" + v)}</option>`).join("");
  gSel.value = "comuna";
  gSel.onchange = vSel.onchange = () => renderDDS();
  const months = t("months");
  for (const id of ["cmpA1", "cmpA2", "cmpB1", "cmpB2"]) {
    const el = document.getElementById(id);
    el.innerHTML = months.map((m, i) => `<option value="${i + 1}">${m}</option>`).join("");
  }
  // default comparison: southern-hemisphere winter vs spring
  document.getElementById("cmpA1").value = 6; document.getElementById("cmpA2").value = 8;
  document.getElementById("cmpB1").value = 9; document.getElementById("cmpB2").value = 11;
  for (const id of ["cmpA1", "cmpA2", "cmpB1", "cmpB2"]) document.getElementById(id).onchange = () => renderCompare();
}
export function relabelReport() {
  const gSel = document.getElementById("ddsGroup"), vSel = document.getElementById("ddsVar");
  [...gSel.options].forEach((o) => { o.textContent = t("grp_" + o.value); });
  [...vSel.options].forEach((o) => { o.textContent = t("var_" + o.value); });
  ["cmpA1", "cmpA2", "cmpB1", "cmpB2"].forEach((id) => [...document.getElementById(id).options].forEach((o, i) => { o.textContent = t("months")[i]; }));
}

let A = null;
export async function renderReport(agg) {
  A = agg;
  renderKPIs(); renderTerritorial(); renderTemporal(); renderCompare(); renderUsers(); renderDDS(); await renderStations();
}

// ---------------- A ----------------
function renderKPIs() {
  const m = D.meta.summary, months = t("months");
  document.getElementById("periodLine").textContent = t("period_line", months[S.m1 - 1], months[S.m2 - 1], fmt(A.n), A.days);
  const k = [];
  const add = (v, label, note = "") => k.push(`<div class="kpi"><b>${v}</b><span>${label}</span>${note ? `<small>${note}</small>` : ""}</div>`);
  add(fmt(A.n), t("k_trips"));
  add(fmt(A.days ? A.n / A.days : 0, 0), t("k_daily"));
  if (!A.demo) {
    add(fmt(A.act), t("k_active")); add(fmt(A.orig), t("k_orig")); add(fmt(A.dest), t("k_dest"));
  }
  add(fmt(A.n ? A.dur / A.n / 60 : NaN, 1) + " " + t("min"), t("k_dur_mean"));
  add(fmt(m.duration_median_min, 1) + " " + t("min"), t("k_dur_med"), t("k_note_static"));
  const dist = A.demo ? A.dist / A.nr : A.distI / A.nr;
  add(fmt(A.nr ? dist / 1000 : NaN, 2) + " " + t("km"), t("k_dist"));
  if (!A.demo) add(fmt(A.durR ? (A.distI / 1000) / (A.durR / 3600) : NaN, 1) + " " + t("kmh"), t("k_speed"), t("k_note_ratio"));
  let same;
  if (A.demo) { same = 0; for (let c = 1; c < 16; c++) same += A.M[c * 16 + c]; same /= A.n || 1; } else same = A.sameC / (A.n || 1);
  add(pct(same), t("k_same")); add(pct(1 - same), t("k_diff"));
  if (!A.demo) add(pct(A.round / (A.n || 1)), t("k_round"));
  document.getElementById("kpis").innerHTML = k.join("");
}

// ---------------- B ----------------
function levelMatrix() {
  if (A.demo) { const L = levelOf("comuna"); return { lvl: "comuna", U: 16, M: A.M, L }; }
  const { U, M, L } = odMatrix(A, S.level);
  return { lvl: S.level, U, M, L };
}
function unitsRanked(U, M, n) {
  const act = [];
  for (let u = 0; u < U; u++) {
    let o = 0, i = 0;
    for (let j = 0; j < U; j++) { o += M[u * U + j]; i += M[j * U + u]; }
    if (o || i) act.push({ u, out: o, inn: i, int: M[u * U + u] });
  }
  act.sort((a, b) => b.out + b.inn - (a.out + a.inn));
  return n ? act.slice(0, n) : act;
}
function renderTerritorial() {
  if (!A.n) { ["cTopOD", "cSankey", "cODHeat", "cInOut", "cInternal"].forEach((id) => message(id, t("no_data"))); return; }
  const { lvl, U, M, L } = levelMatrix();
  const ink = css("--ink"), mid = css("--ink-3");
  const flows = [];
  for (let o = 0; o < U; o++) for (let d = 0; d < U; d++) if (o !== d && M[o * U + d]) flows.push({ o, d, v: M[o * U + d], r: M[d * U + o] });
  flows.sort((a, b) => b.v - a.v);
  const top = flows.slice(0, 20).reverse();
  const lab = top.map((f) => `${L.name(f.o)} → ${L.name(f.d)}`);
  plot("cTopOD", [
    { type: "bar", orientation: "h", y: lab, x: top.map((f) => f.v), name: "A → B", marker: { color: ink },
      hovertemplate: "%{y}: %{x:,} " + t("trips") + "<extra></extra>" },
    { type: "bar", orientation: "h", y: lab, x: top.map((f) => -f.r), name: "B → A", marker: { color: mid },
      customdata: top.map((f) => f.r), hovertemplate: "B → A: %{customdata:,}<extra></extra>" },
  ], t("c_topod"), { barmode: "overlay", margin: { l: 220, r: 10, t: 40, b: 40 }, yaxis: { automargin: true, tickfont: { size: 10 } } });

  // Sankey: origins left, destinations right
  const sk = flows.slice(0, S.topN === 10 ? 10 : S.topN === 50 ? 50 : 20);
  const nodes = [], idx = new Map();
  const node = (key, label) => { if (!idx.has(key)) { idx.set(key, nodes.length); nodes.push(label); } return idx.get(key); };
  const src = [], tgt = [], val = [];
  for (const f of sk) { src.push(node("o" + f.o, L.name(f.o))); tgt.push(node("d" + f.d, L.name(f.d) + " ")); val.push(f.v); }
  plot("cSankey", [{ type: "sankey", arrangement: "snap",
    node: { label: nodes, color: ink, pad: 8, thickness: 10, line: { width: 0 } },
    link: { source: src, target: tgt, value: val, color: "rgba(128,128,128,0.35)" } }], t("c_sankey"), { margin: { l: 10, r: 10, t: 40, b: 10 } });

  // OD heatmap
  let units = lvl === "comuna" ? [...Array(15).keys()].map((x) => x + 1) : unitsRanked(U, M, lvl === "station" ? 25 : 48).map((x) => x.u);
  if (lvl === "barrio") units.sort((a, b) => D.barrioNames[a].localeCompare(D.barrioNames[b], "es"));
  const z = units.map((o) => units.map((d) => M[o * U + d]));
  const names = units.map((u) => L.name(u));
  plot("cODHeat", [{ type: "heatmap", z, x: names, y: names, colorscale: [[0, css("--bg")], [1, ink]], showscale: true,
    hovertemplate: "%{y} → %{x}: %{z:,}<extra></extra>", colorbar: { thickness: 8, outlinewidth: 0 } }],
  t("c_odheat"), { xaxis: { tickangle: -60, tickfont: { size: 9 }, title: { text: t("f_dest") } },
    yaxis: { autorange: "reversed", tickfont: { size: 9 }, title: { text: t("f_origin") } }, margin: { l: 110, r: 10, t: 40, b: 110 } });

  const ranked = unitsRanked(U, M, lvl === "comuna" ? 0 : 25);
  const rn = ranked.map((x) => L.name(x.u));
  plot("cInOut", [
    { type: "bar", x: rn, y: ranked.map((x) => x.out), name: t("departures"), marker: { color: ink } },
    { type: "bar", x: rn, y: ranked.map((x) => x.inn), name: t("arrivals"), marker: { color: mid } },
    { type: "scatter", mode: "markers", x: rn, y: ranked.map((x) => x.inn - x.out), name: t("net"), yaxis: "y2",
      marker: { color: css("--bg"), line: { color: ink, width: 1.5 }, size: 8, symbol: "diamond" } },
  ], t("c_inout"), { barmode: "group", xaxis: { tickangle: -45, tickfont: { size: 9 } },
    yaxis2: { overlaying: "y", side: "right", zeroline: true, zerolinecolor: ink, showgrid: false, title: { text: t("net") } } });

  plot("cInternal", [
    { type: "bar", x: rn, y: ranked.map((x) => x.int), name: t("internal"), marker: { color: ink } },
    { type: "bar", x: rn, y: ranked.map((x) => x.out - x.int), name: t("external_out"), marker: { color: mid } },
    { type: "bar", x: rn, y: ranked.map((x) => x.inn - x.int), name: t("external_in"), marker: { color: css("--line-2") } },
  ], t("c_internal"), { barmode: "stack", xaxis: { tickangle: -45, tickfont: { size: 9 } } });
}

// ---------------- C ----------------
function daysPerDow(m1 = S.m1, m2 = S.m2) {
  const c = new Array(7).fill(0), mc = new Array(13).fill(0);
  for (let doy = 1; doy <= 365; doy++) {
    const m = D.doyMonth[doy], we = D.doyWeekend[doy];
    if (m < m1 || m > m2) continue;
    if (S.daytype === "wd" && we) continue;
    if (S.daytype === "we" && !we) continue;
    c[D.doyDow[doy]]++; mc[m]++;
  }
  return { c, mc };
}
function renderTemporal() {
  const cal = calendarSeries();
  const ink = css("--ink"), mid = css("--ink-3");
  const notes = [];
  if (A.demo) notes.push(t("demo_time"));
  const sub = (S.origin && S.origin[0] !== "c") || (S.area && S.area[0] !== "c") || S.dest;
  if (sub) notes.push(cal.comunaFilter ? `Comuna ${cal.comunaFilter}` : "");
  const days = A.days || 1, { c: dowDays, mc } = daysPerDow();
  const hrs = [...Array(24).keys()];
  plot("cHour", [{ type: "bar", x: hrs, y: [...cal.byHour].map((v) => v / days), marker: { color: ink },
    hovertemplate: "%{x}h: %{y:,.0f}<extra></extra>" }], t("c_hour") + (notes.length ? " · " + notes.join(" · ") : ""),
  { xaxis: { dtick: 2, title: { text: t("hour") } }, yaxis: { title: { text: t("trips_per_day") } } });

  const dowTot = new Array(7).fill(0);
  for (let d = 0; d < 7; d++) for (let h = 0; h < 24; h++) dowTot[d] += cal.hd[d * 24 + h];
  plot("cDow", [{ type: "bar", x: t("weekday_short"), y: dowTot.map((v, d) => (dowDays[d] ? v / dowDays[d] : 0)),
    marker: { color: dowTot.map((_, d) => (d < 5 ? ink : mid)) } }], t("c_dow"));

  const monTot = new Array(13).fill(0);
  for (let doy = 1; doy <= 365; doy++) monTot[D.doyMonth[doy]] += cal.byDoy[doy];
  const ms = [];
  for (let m = S.m1; m <= S.m2; m++) ms.push(m);
  plot("cMonth", [{ type: "scatter", mode: "lines+markers", x: ms.map((m) => t("months")[m - 1]), y: ms.map((m) => (mc[m] ? monTot[m] / mc[m] : null)),
    line: { color: ink, width: 2 }, marker: { color: ink } }], t("c_month"), { yaxis: { title: { text: t("trips_per_day") } } });

  const z = [];
  for (let d = 0; d < 7; d++) z.push(hrs.map((h) => (dowDays[d] ? cal.hd[d * 24 + h] / dowDays[d] : null)));
  plot("cHeatHD", [{ type: "heatmap", z, x: hrs, y: t("weekday_short"), colorscale: [[0, css("--bg")], [1, ink]],
    colorbar: { thickness: 8, outlinewidth: 0 }, hovertemplate: "%{y} %{x}h: %{z:,.0f}<extra></extra>" }],
  t("c_heathd"), { yaxis: { autorange: "reversed" }, xaxis: { dtick: 2 } });

  const xs = [], ys = [];
  for (let doy = 1; doy <= 365; doy++) {
    const m = D.doyMonth[doy], we = D.doyWeekend[doy];
    if (m < S.m1 || m > S.m2 || (S.daytype === "wd" && we) || (S.daytype === "we" && !we)) continue;
    xs.push(new Date(Date.UTC(D.meta.year, 0, doy)).toISOString().slice(0, 10)); ys.push(cal.byDoy[doy]);
  }
  plot("cDaily", [{ type: "scatter", mode: "lines", x: xs, y: ys, line: { color: ink, width: 1.2 }, fill: "tozeroy", fillcolor: "rgba(128,128,128,0.15)" }],
    t("c_daily"), { xaxis: { rangeslider: { visible: true, thickness: 0.08, bgcolor: css("--soft") }, type: "date" } });
}
function renderCompare() {
  if (!D.cal) return;
  const v = (id) => +document.getElementById(id).value;
  const series = (a, b) => {
    const lo = Math.min(a, b), hi = Math.max(a, b);
    const cal = calendarSeries(S, lo, hi);
    let days = 0;
    for (let doy = 1; doy <= 365; doy++) {
      const m = D.doyMonth[doy], we = D.doyWeekend[doy];
      if (m >= lo && m <= hi && !(S.daytype === "wd" && we) && !(S.daytype === "we" && !we)) days++;
    }
    return { y: [...cal.byHour].map((x) => x / (days || 1)), lo, hi, tot: cal.byHour.reduce((s, x) => s + x, 0) / (days || 1) };
  };
  const a = series(v("cmpA1"), v("cmpA2")), b = series(v("cmpB1"), v("cmpB2"));
  const M = t("months"), hrs = [...Array(24).keys()];
  const name = (s, L) => `${L}: ${M[s.lo - 1]}–${M[s.hi - 1]} (${fmt(s.tot)} ${t("trips_per_day")})`;
  const change = a.tot ? (b.tot / a.tot - 1) : NaN;
  plot("cCompare", [
    { type: "scatter", mode: "lines", x: hrs, y: a.y, name: name(a, "A"), line: { color: css("--ink-3"), width: 2, dash: "dash" } },
    { type: "scatter", mode: "lines", x: hrs, y: b.y, name: name(b, "B"), line: { color: css("--ink"), width: 2.2 } },
  ], `${t("c_compare")} · B vs A: ${change >= 0 ? "+" : ""}${pct(change)}`, { xaxis: { dtick: 2, title: { text: t("hour") } } });
}

// ---------------- D ----------------
function catLabel(attr, c) {
  if (attr === "gender") return t("g_" + c);
  return c === "unknown" ? t("unknown") : c === "suppressed" ? t("suppressed") : c;
}
function renderUsers() {
  const q = D.meta.quality;
  document.getElementById("userAvail").innerHTML = t("user_avail",
    pct(1 - q.gender_counts.nan / q.raw_rows), pct(q.age_available_share)) + "<br>" + t("demo_one");
  const ink = css("--ink"), mid = css("--ink-3");
  const blocks = [["gender", "cGender", "c_gender"], ["age_group", "cAge", "c_age"]];
  const res = {};
  for (const [attr, id, title] of blocks) {
    const b = demoBreakdown(attr === "gender" ? "gender" : "age");
    res[attr] = b;
    const tot = b.reduce((s, x) => s + x.n, 0) || 1;
    const shown = b.filter((x) => x.n > 0);
    plot(id, [{ type: "bar", x: shown.map((x) => catLabel(attr, x.cat)), y: shown.map((x) => (x.n < MIN() ? 0 : x.n)),
      text: shown.map((x) => (x.n < MIN() ? t("n_lt", MIN()) : pct(x.n / tot))), textposition: "outside", cliponaxis: false,
      marker: { color: shown.map((x) => (["suppressed", "unknown", "UNKNOWN"].includes(x.cat) ? mid : ink)) },
      hovertemplate: "%{x}: %{y:,}<extra></extra>" }], t(title), { yaxis: { title: { text: t("trips") } } });
  }
  // hourly profile by gender (annual, from the analytical tables)
  const demo = D.meta.demographics.filter((r) => r.attribute === "gender" && !r.suppressed && r.trips >= MIN());
  const dash = { MALE: "solid", FEMALE: "dash", OTHER: "dot", UNKNOWN: "dashdot" };
  plot("cGenderHour", demo.map((r) => {
    const s = r.hours.reduce((a, b) => a + b, 0);
    return { type: "scatter", mode: "lines", x: [...Array(24).keys()], y: r.hours.map((v) => (v / s) * 100),
      name: `${t("g_" + r.value)} (n=${fmt(r.trips)})`, line: { color: r.value === "OTHER" || r.value === "UNKNOWN" ? mid : ink, dash: dash[r.value], width: 1.8 } };
  }), t("c_genderhour") + ` · ${t("k_note_static")}`, { xaxis: { dtick: 2, title: { text: t("hour") } }, yaxis: { title: { text: "%" } },
    legend: { orientation: "h", y: -0.3, font: { size: 10 } }, margin: { l: 56, r: 16, t: 40, b: 80 } });

  // mean duration and distance by group, current filters
  const rows = [...res.gender.filter((x) => !["suppressed", "UNKNOWN"].includes(x.cat)).map((x) => ({ ...x, lab: t("g_" + x.cat) })),
    ...res.age_group.filter((x) => !["suppressed", "unknown"].includes(x.cat)).map((x) => ({ ...x, lab: x.cat }))].filter((x) => x.n >= MIN());
  plot("cDemoDDS", [
    { type: "bar", x: rows.map((r) => r.lab), y: rows.map((r) => r.dur / r.n / 60), name: t("var_duration_min"), marker: { color: ink }, offsetgroup: 1 },
    { type: "bar", x: rows.map((r) => r.lab), y: rows.map((r) => (r.nr ? r.dist / r.nr / 1000 : null)), name: t("var_distance_km"), marker: { color: mid }, yaxis: "y2", offsetgroup: 2 },
  ], t("c_demodds"), { barmode: "group", yaxis: { title: { text: t("min") } },
    yaxis2: { overlaying: "y", side: "right", showgrid: false, title: { text: t("km") }, rangemode: "tozero" } });

  // static table
  const tr = D.meta.demographics.filter((r) => !r.suppressed).map((r) => {
    const pairs = JSON.parse(r.top_comuna_pairs || "[]").slice(0, 3).map(([a, b]) => `${a}→${b}`).join(", ");
    const dds = D.meta.dds.find((x) => x.group === r.attribute && x.value === r.value) || {};
    return `<tr><td>${catLabel(r.attribute, r.value)}</td><td>${fmt(r.trips)}</td><td>${pct(r.share)}</td><td>${pct(r.weekend_share)}</td>
      <td>${pct(r.peak_am_share)}</td><td>${pct(r.peak_pm_share)}</td><td>${fmt(dds.duration_min_median, 1)}</td>
      <td>${fmt(dds.distance_km_median, 2)}</td><td>${fmt(dds.speed_kmh_median, 1)}</td><td>${pairs}</td></tr>`;
  }).join("");
  const es = document.documentElement.lang === "es";
  document.getElementById("tDemo").innerHTML = `<table><thead><tr><th>${t("col_group")}</th><th>${t("col_n")}</th><th>${t("share")}</th>
    <th>${t("weekend")}</th><th>07–10h</th><th>17–20h</th><th>${t("var_duration_min")} (${t("col_median")})</th>
    <th>${t("var_distance_km")} (${t("col_median")})</th><th>${t("var_speed_kmh")} (${t("col_median")})</th>
    <th>${es ? "Pares de comunas principales" : "Top commune pairs"}</th></tr></thead><tbody>${tr}</tbody></table>
    <p class="fnote">${t("k_note_static")}. n ≥ ${MIN()}.</p>`;
}

// ---------------- E ----------------
function renderDDS() {
  const g = document.getElementById("ddsGroup").value, v = document.getElementById("ddsVar").value;
  let rows = D.meta.dds.filter((r) => r.group === g && !r.suppressed && r.n_trips >= MIN());
  if (g === "hour") rows.sort((a, b) => +a.value - +b.value);
  else if (g === "comuna") rows.sort((a, b) => +a.value - +b.value);
  else if (g === "barrio") rows.sort((a, b) => b[`${v}_median`] - a[`${v}_median`]);
  const lab = rows.map((r) => (g === "gender" ? t("g_" + r.value) : g === "daytype" ? t(r.value) : g === "comuna" ? `Comuna ${r.value}` : g === "hour" ? `${r.value}h` : r.value));
  const tick = g === "comuna" ? rows.map((r) => `C${r.value}`) : lab;      // short ticks, full names in hover/table
  const ink = css("--ink");
  plot("cDDS", [{ type: "scatter", mode: "markers", x: tick, y: rows.map((r) => r[`${v}_median`]),
    error_y: { type: "data", symmetric: false, array: rows.map((r) => r[`${v}_p75`] - r[`${v}_median`]),
      arrayminus: rows.map((r) => r[`${v}_median`] - r[`${v}_p25`]), color: css("--ink-3"), thickness: 1.4, width: 3 },
    marker: { color: ink, size: 7, symbol: "line-ew-open", line: { width: 2, color: ink } },
    customdata: rows.map((r) => [r[`${v}_p25`], r[`${v}_p75`], r[`${v}_mean`], r.n_trips]),
    hovertemplate: "%{x}<br>p25 %{customdata[0]:.2f} · " + t("col_median") + " %{y:.2f} · p75 %{customdata[1]:.2f}<br>" + t("col_mean") + " %{customdata[2]:.2f} · n=%{customdata[3]:,}<extra></extra>" }],
  `${t("var_" + v)}: p25 · ${t("col_median")} · p75`, { xaxis: { tickangle: g === "barrio" ? -60 : 0, tickfont: { size: 9 },
    title: { text: `${t("grp_" + g)} · ${t("k_note_static")}` } } });

  document.getElementById("tDDS").innerHTML = `<table><thead><tr><th>${t("col_group")}</th><th>${t("col_n")}</th>
    ${["duration_min", "distance_km", "speed_kmh"].map((x) => `<th>${t("var_" + x)}<br>${t("col_p25")} · ${t("col_median")} · ${t("col_p75")}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r, i) => `<tr><td>${lab[i]}</td><td>${fmt(r.n_trips)}</td>${["duration_min", "distance_km", "speed_kmh"].map((x) =>
      `<td>${fmt(r[x + "_p25"], 1)} · <b>${fmt(r[x + "_median"], 1)}</b> · ${fmt(r[x + "_p75"], 1)}</td>`).join("")}</tr>`).join("")}</tbody></table>
    <p class="fnote">${t("rE_lead")} ${fmt(D.meta.summary.speed_implausible_trips)} > ${D.meta.summary.max_speed_kmh} km/h excl.</p>`;

  // filter-responsive histogram of estimated distance
  if (A.demo) { message("cDistHist", t("demo_level")); return; }
  const bins = new Float64Array(25);
  for (let p = 0; p < D.P; p++) {
    const c = A.pairN[p];
    if (!c || D.pO[p] === D.pD[p] || !D.dI[p]) continue;
    bins[Math.min(24, Math.floor(D.dI[p] / 500))] += c;
  }
  plot("cDistHist", [{ type: "bar", x: [...bins.keys()].map((i) => i * 0.5 + 0.25), y: [...bins], marker: { color: ink }, width: 0.45,
    hovertemplate: "%{x:.2f} km: %{y:,}<extra></extra>" }], t("c_disthist"),
  { xaxis: { title: { text: t("km") + " (≥12 km agrupado)" } }, yaxis: { title: { text: t("trips") } } });
}

// ---------------- F ----------------
async function renderStations() {
  const ink = css("--ink"), mid = css("--ink-3");
  if (A.demo) { ["cStTop", "cStNet", "cStDepArr"].forEach((id) => message(id, t("demo_level"))); }
  else {
    const st = D.stations.map((s) => ({ i: s.i, name: s.name, dep: A.dep[s.i], arr: A.arr[s.i] })).filter((s) => s.dep + s.arr > 0);
    const top = [...st].sort((a, b) => b.dep + b.arr - (a.dep + a.arr)).slice(0, 15).reverse();
    plot("cStTop", [{ type: "bar", orientation: "h", y: top.map((s) => s.name), x: top.map((s) => s.dep + s.arr), marker: { color: ink },
      customdata: top.map((s) => s.i), hovertemplate: "%{y}: %{x:,}<extra></extra>" }], t("c_sttop"), { margin: { l: 180, r: 10, t: 40, b: 40 } });
    const net = [...st].sort((a, b) => (a.arr - a.dep) - (b.arr - b.dep));
    const nn = [...net.slice(0, 8), ...net.slice(-8)];
    plot("cStNet", [{ type: "bar", orientation: "h", y: nn.map((s) => s.name), x: nn.map((s) => s.arr - s.dep),
      marker: { color: nn.map((s) => (s.arr - s.dep > 0 ? ink : mid)) }, customdata: nn.map((s) => s.i),
      hovertemplate: "%{y}: %{x:+,}<extra></extra>" }], t("c_stnet"), { margin: { l: 180, r: 10, t: 40, b: 40 }, xaxis: { title: { text: t("net") } } });
    const td = [...st].sort((a, b) => b.dep - a.dep).slice(0, 10), ta = [...st].sort((a, b) => b.arr - a.arr).slice(0, 10);
    const both = [...new Map([...td, ...ta].map((s) => [s.i, s])).values()].sort((a, b) => a.dep + a.arr - (b.dep + b.arr));
    plot("cStDepArr", [
      { type: "bar", orientation: "h", y: both.map((s) => s.name), x: both.map((s) => s.dep), name: t("departures"), marker: { color: ink }, customdata: both.map((s) => s.i) },
      { type: "bar", orientation: "h", y: both.map((s) => s.name), x: both.map((s) => s.arr), name: t("arrivals"), marker: { color: mid }, customdata: both.map((s) => s.i) },
    ], t("c_stdeparr"), { barmode: "group", margin: { l: 180, r: 10, t: 40, b: 40 } });
    for (const id of ["cStTop", "cStNet", "cStDepArr"]) {
      const el = document.getElementById(id);
      el.removeAllListeners?.("plotly_click");
      el.on?.("plotly_click", (e) => onStationClick?.(e.points[0].customdata));
    }
  }
  await loadStreets();
  const sc = segmentCounts();
  const byName = new Map();
  D.segs.features.forEach((f, k) => {
    const nm = f.properties.name || "—";
    const e = byName.get(nm) || { max: 0, infra: 0, len: 0 };
    e.max = Math.max(e.max, sc[k]);
    byName.set(nm, e);
  });
  const top = [...byName.entries()].sort((a, b) => b[1].max - a[1].max).slice(0, 15).reverse();
  plot("cStreets", [{ type: "bar", orientation: "h", y: top.map((x) => x[0]), x: top.map((x) => x[1].max), marker: { color: ink },
    hovertemplate: "%{y}: %{x:,}<extra></extra>" }],
  t("c_streets"), { margin: { l: 170, r: 10, t: 40, b: 50 },
    xaxis: { title: { text: document.documentElement.lang === "es" ? "Viajes inferidos en el tramo más cargado" : "Inferred trips on the busiest segment" } } });
}
export { unitComuna };
