// Shared Plotly styling: monochrome, consistent typography, light and dark.
export const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

export function baseLayout(title, extra = {}) {
  const ink = css("--ink"), ink2 = css("--ink-2"), line = css("--line");
  return {
    title: title ? { text: title, x: 0, xanchor: "left", font: { size: 13, color: ink, family: "Inter, sans-serif" } } : undefined,
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Inter, sans-serif", size: 11, color: ink2 },
    margin: { l: 56, r: 16, t: title ? 40 : 10, b: 76 },
    xaxis: { gridcolor: line, linecolor: ink, zeroline: false, automargin: true },
    yaxis: { gridcolor: line, linecolor: ink, zeroline: false, automargin: true, rangemode: "tozero" },
    legend: { orientation: "h", x: 0, y: -0.32, yanchor: "top", font: { size: 11 } },
    hoverlabel: { bgcolor: css("--surface"), bordercolor: ink, font: { color: ink, family: "Inter, sans-serif" } },
    bargap: 0.18,
    ...extra,
  };
}
const CONFIG = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines"] };

export function plot(id, traces, title, extra = {}) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!el.classList.contains("js-plotly-plot")) el.innerHTML = "";   // clear a previous message()
  const lay = baseLayout(title, extra);
  if (extra.xaxis) lay.xaxis = { ...baseLayout().xaxis, ...extra.xaxis };
  if (extra.yaxis) lay.yaxis = { ...baseLayout().yaxis, ...extra.yaxis };
  Plotly.react(el, traces, lay, CONFIG);
}
export function plotMini(id, traces, extra) {
  const lay = baseLayout(null, { margin: { l: 36, r: 6, t: 4, b: 30 }, showlegend: traces.length > 1, height: 140, ...extra });
  lay.legend = { orientation: "h", y: 1.15, font: { size: 10 } };
  if (extra.xaxis) lay.xaxis = { ...baseLayout().xaxis, ...extra.xaxis };
  Plotly.react(document.getElementById(id), traces, lay, { displayModeBar: false, responsive: true });
}
export function message(id, text) {
  const el = document.getElementById(id);
  if (!el) return;
  Plotly.purge(el);
  el.innerHTML = `<p class="fnote" style="padding:20px 0">${text}</p>`;
}
export const greys = (n) => Array.from({ length: n }, (_, i) => {
  const v = Math.round(20 + (i / Math.max(1, n - 1)) * 170);
  return `rgb(${v},${v},${v})`;
});
