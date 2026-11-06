// Entry point: loads data, wires shared filters, tabs and language, keeps map and report in sync.
import { D, S, aggregate, aggregateDemo, demoActive, loadCore, loadDemo, resetState } from "./data.js";
import { applyStatic, fmt, getLang, setLang, t } from "./i18n.js";
import { focusStation, initMap, resetMapSelection, resizeMap, setAggregate, setLabels, updateMap } from "./map.js";
import { initReport, relabelReport, renderReport } from "./report.js";
import { renderMethod } from "./method.js";

let view = "map", reportDirty = true, current = null;
const $ = (id) => document.getElementById(id);

async function main() {
  setLang(getLang());
  try {
    await loadCore();
  } catch (e) {
    $("loading").innerHTML = `<p>Error: ${e.message}</p>`;
    throw e;
  }
  buildFilters();
  initReport((i) => { switchView("map"); focusStation(i); });
  initMap((ref) => { /* map unit click: no filter change, only highlight */ });
  wireTabs();
  renderMethod();
  $("loading").classList.add("done");
  await update();
  const h = location.hash.slice(1);                 // deep links: #report, #method
  if (h === "report" || h === "method") switchView(h);
  loadDemo();   // prefetch for a fast first demographic filter
}

// ---------------- Filters UI ----------------
function options(sel, items, keepValue = true) {
  const v = sel.value;
  sel.innerHTML = items;
  if (keepValue) sel.value = v;
}
function unitOptions() {
  const com = [...Array(15).keys()].map((i) => `<option value="c:${i + 1}">Comuna ${i + 1}</option>`).join("");
  const bar = D.barrioNames.map((b) => `<option value="b:${b}">${b}</option>`).join("");
  const sta = [...D.stations].sort((a, b) => a.name.localeCompare(b.name, "es"))
    .map((s) => `<option value="s:${s.i}">${s.name} (#${s.id})</option>`).join("");
  return `<option value="">${t("any")}</option><optgroup label="${t("lvl_comuna")}">${com}</optgroup>` +
    `<optgroup label="${t("lvl_barrio")}">${bar}</optgroup><optgroup label="${t("lvl_station")}">${sta}</optgroup>`;
}
function buildFilters() {
  const months = t("months");
  const mo = months.map((m, i) => `<option value="${i + 1}">${m}</option>`).join("");
  options($("fMonthFrom"), mo); options($("fMonthTo"), mo);
  $("fMonthFrom").value = S.m1; $("fMonthTo").value = S.m2;
  $("fHours").innerHTML = D.meta.hour_bands.map(([a, b], i) =>
    `<button class="chip ${S.bands.has(i) ? "on" : ""}" data-b="${i}">${String(a).padStart(2, "0")}–${String(b).padStart(2, "0")}h</button>`).join("");
  for (const id of ["fArea", "fOrigin", "fDest"]) options($(id), unitOptions());
  options($("fGender"), `<option value="">${t("any")}</option>` +
    D.meta.genders.filter((g) => g !== "suppressed").map((g) => `<option value="${g}">${t("g_" + g)}</option>`).join(""));
  options($("fAge"), `<option value="">${t("any")}</option>` +
    D.meta.ages.filter((a) => a !== "suppressed").map((a) => `<option value="${a}">${a === "unknown" ? t("unknown") : a}</option>`).join(""));
  syncControls();

  $("fMonthFrom").onchange = () => { S.m1 = +$("fMonthFrom").value; if (S.m1 > S.m2) { S.m2 = S.m1; $("fMonthTo").value = S.m2; } update(); };
  $("fMonthTo").onchange = () => { S.m2 = +$("fMonthTo").value; if (S.m2 < S.m1) { S.m1 = S.m2; $("fMonthFrom").value = S.m1; } update(); };
  $("fHours").onclick = (e) => {
    const b = e.target.closest(".chip");
    if (!b) return;
    const i = +b.dataset.b;
    if (S.bands.has(i) && S.bands.size === 1) return;     // keep at least one band
    S.bands.has(i) ? S.bands.delete(i) : S.bands.add(i);
    b.classList.toggle("on");
    update();
  };
  segControl("fDaytype", (v) => { S.daytype = v; update(); });
  segControl("fLevel", (v) => { S.level = v; resetMapSelection(); update(); });
  segControl("fTopN", (v) => { S.topN = +v; update(false); });
  segControl("fStrategy", (v) => { S.strategy = v; update(false); });
  $("fLabels").onchange = () => { S.labels = $("fLabels").checked; setLabels(); };
  $("fArea").onchange = () => { S.area = $("fArea").value; update(); };
  $("fOrigin").onchange = () => { S.origin = $("fOrigin").value; update(); };
  $("fDest").onchange = () => { S.dest = $("fDest").value; update(); };
  $("fGender").onchange = async () => { S.gender = $("fGender").value; if (S.gender) { S.age = ""; $("fAge").value = ""; } await update(); };
  $("fAge").onchange = async () => { S.age = $("fAge").value; if (S.age) { S.gender = ""; $("fGender").value = ""; } await update(); };
  $("fReset").onclick = () => { resetState(); resetMapSelection(); buildFilters(); update(); };
  $("filtersToggle").onclick = () => $("filters").classList.toggle("open");
}
function segControl(id, fn) {
  $(id).onclick = (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    $(id).querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    fn(b.dataset.v);
  };
}
function syncControls() {
  const set = (id, v) => $(id).querySelectorAll("button").forEach((x) => x.classList.toggle("on", x.dataset.v === String(v)));
  set("fDaytype", S.daytype); set("fLevel", S.level); set("fTopN", S.topN); set("fStrategy", S.strategy);
  $("fArea").value = S.area; $("fOrigin").value = S.origin; $("fDest").value = S.dest;
  $("fGender").value = S.gender; $("fAge").value = S.age; $("fLabels").checked = S.labels;
}

// ---------------- Update cycle ----------------
async function update(recompute = true) {
  if (recompute || !current) {
    if (demoActive()) await loadDemo();
    current = demoActive() ? aggregateDemo() : aggregate();
  }
  setAggregate(current);
  $("fSample").textContent = t("sample", fmt(current.n));
  $("fNote").textContent = demoActive() ? t("demo_level") : "";
  await updateMap();
  reportDirty = true;
  if (view === "report") { await renderReport(current); reportDirty = false; }
}

// ---------------- Tabs & language ----------------
function switchView(v) {
  view = v;
  history.replaceState(null, "", v === "map" ? location.pathname : `#${v}`);
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  document.querySelectorAll(".view").forEach((s) => s.classList.toggle("active", s.id === `view-${v}`));
  $("filters").style.display = v === "method" ? "none" : "";
  document.querySelector("main").style.left = v === "method" && innerWidth > 900 ? "0" : "";
  if (v === "map") resizeMap();
  if (v === "report" && reportDirty && current) { renderReport(current); reportDirty = false; }
}
function wireTabs() {
  document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));
  document.querySelectorAll(".lang-btn").forEach((b) => b.addEventListener("click", async () => {
    setLang(b.dataset.lang);
    buildFilters(); relabelReport(); renderMethod();
    reportDirty = true;
    await update(false);
  }));
}

main();
export { applyStatic };
