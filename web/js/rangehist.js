// Histogram with a selectable range, used as an interactive legend.
// Values are binned on a fixed 1-2-5 logarithmic scale so the selected range
// (stored as bin edges) stays meaningful when filters change the data.
//   const h = rangeHist(el, { onChange(lo, hi) {}, colors: (i, n) => "#hex" });
//   h.set(values)          -> redraw with new data (keeps the range)
//   h.range                -> { lo, hi } value thresholds (hi = Infinity when open)
// Interactions: drag either handle; click a bar to keep only that bar;
// double-click to select everything.
import { fmt } from "./i18n.js";

const EDGES = [1];
while (EDGES[EDGES.length - 1] < 1e7) {
  const e = EDGES[EDGES.length - 1], m = e / 10 ** Math.floor(Math.log10(e));
  EDGES.push(m === 1 ? e * 2 : m === 2 ? e * 2.5 : e * 2);
}
const short = (v) => (v >= 1e6 ? fmt(v / 1e6, 1) + "M" : v >= 1e4 ? fmt(v / 1e3, 0) + "k" : fmt(v));

export function rangeHist(el, { onChange, colors, accent = () => "#888" } = {}) {
  el.classList.add("rh");
  el.innerHTML = `<canvas></canvas><div class="rh-range"><input type="range" class="lo" min="0" step="1"><input type="range" class="hi" min="0" step="1"></div><div class="rh-axis"><span></span><span></span></div>`;
  const cv = el.querySelector("canvas"), loI = el.querySelector(".lo"), hiI = el.querySelector(".hi");
  const [axL, axR] = el.querySelectorAll(".rh-axis span");
  let counts = [], nb = 1, lo = 0, hi = Infinity;            // lo/hi are bin indices
  const api = { get range() { return { lo: EDGES[lo], hi: hi >= nb - 1 ? Infinity : EDGES[hi + 1] }; }, bins: () => nb, edges: EDGES };

  function draw() {
    const dpr = devicePixelRatio || 1, w = cv.clientWidth || 200, h = cv.clientHeight || 46;
    cv.width = w * dpr; cv.height = h * dpr;
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    const mx = Math.max(1, ...counts), bw = w / nb, hh = Math.min(hi, nb - 1);
    for (let i = 0; i < nb; i++) {
      const bh = counts[i] ? Math.max(2, Math.sqrt(counts[i] / mx) * (h - 2)) : 0;
      ctx.globalAlpha = i >= lo && i <= hh ? 1 : 0.22;
      ctx.fillStyle = colors ? colors(i, nb) : accent();
      ctx.fillRect(i * bw + 0.5, h - bh, Math.max(1, bw - 1.5), bh);
    }
    ctx.globalAlpha = 1;
    loI.max = hiI.max = String(nb - 1); loI.value = String(lo); hiI.value = String(hh);
    axL.textContent = short(EDGES[lo]);
    axR.textContent = hh >= nb - 1 ? "∞" : short(EDGES[hh + 1]);
  }
  const emit = () => { draw(); onChange?.(api.range.lo, api.range.hi); };

  loI.oninput = () => { lo = Math.min(+loI.value, Math.min(hi, nb - 1)); emit(); };
  hiI.oninput = () => { hi = Math.max(+hiI.value, lo); if (hi >= nb - 1) hi = Infinity; emit(); };
  const binAt = (e) => Math.min(nb - 1, Math.max(0, Math.floor((e.offsetX / cv.clientWidth) * nb)));
  cv.onclick = (e) => { const b = binAt(e); lo = b; hi = b >= nb - 1 ? Infinity : b; emit(); };
  cv.ondblclick = () => { lo = 0; hi = Infinity; emit(); };
  cv.onmousemove = (e) => { const b = binAt(e); cv.title = `${short(EDGES[b])}–${b >= nb - 1 ? "∞" : short(EDGES[b + 1])}: ${fmt(counts[b] || 0)}`; };

  api.set = (values) => {
    let vmax = 1;
    for (const v of values) if (v > vmax) vmax = v;
    nb = Math.max(2, EDGES.findIndex((e) => e > vmax));
    counts = new Array(nb).fill(0);
    for (const v of values) if (v >= 1) counts[Math.min(nb - 1, binOf(v))]++;
    lo = Math.min(lo, nb - 1);
    draw();
  };
  // choose the lowest edge leaving at most `n` values above it
  api.setTop = (values, n) => {
    const sorted = [...values].sort((a, b) => b - a), v = sorted[Math.min(n, sorted.length) - 1] || 1;
    lo = Math.max(0, binOf(v)); hi = Infinity;
    api.set(values);
  };
  api.setAll = () => { lo = 0; hi = Infinity; draw(); };
  api.binOf = binOf;
  return api;
}
export function binOf(v) {
  let i = 0;
  while (i < EDGES.length - 1 && EDGES[i + 1] <= v) i++;
  return i;
}
