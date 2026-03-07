/**
 * Chart.js wrappers for quant-v2.
 * All chart functions accept plain arrays and return Chart instances.
 */

/**
 * Render an equity curve chart.
 * @param {string} canvasId - Canvas element ID
 * @param {number[]} equity - Cumulative equity curve values
 * @param {string[]} labels - Date labels
 */
function renderEquityChart(canvasId, equity, labels) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  return new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [{
        label: "Equity",
        data: equity,
        borderColor: "#4ade80",
        backgroundColor: "rgba(74,222,128,0.08)",
        borderWidth: 1.5,
        pointRadius: 0,
        fill: true,
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#6b7280", maxTicksLimit: 6 }, grid: { color: "#1f2937" } },
        y: { ticks: { color: "#6b7280" }, grid: { color: "#1f2937" } }
      }
    }
  });
}

/**
 * Render a Monte Carlo fan chart (10th/50th/90th percentile bands).
 * @param {string} canvasId
 * @param {number[]} p10 - 10th percentile equity
 * @param {number[]} p50 - Median equity
 * @param {number[]} p90 - 90th percentile equity
 */
function renderMCChart(canvasId, p10, p50, p90) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  const labels = p50.map((_, i) => i + 1);
  return new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        { label: "P90", data: p90, borderColor: "#22c55e", borderWidth: 1, pointRadius: 0, fill: "+1", backgroundColor: "rgba(34,197,94,0.1)" },
        { label: "Median", data: p50, borderColor: "#86efac", borderWidth: 2, pointRadius: 0, fill: false },
        { label: "P10", data: p10, borderColor: "#ef4444", borderWidth: 1, pointRadius: 0, fill: false },
      ]
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: "#9ca3af", boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: "#6b7280" }, grid: { color: "#1f2937" } },
        y: { ticks: { color: "#6b7280" }, grid: { color: "#1f2937" } }
      }
    }
  });
}

/**
 * Render an Optuna trial sparkline.
 * @param {string} canvasId
 * @param {number[]} sharpes - IS-val Sharpe per trial
 */
function renderOptunaSparkline(canvasId, sharpes) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  const best = sharpes.map((_, i) => Math.max(...sharpes.slice(0, i + 1)));
  return new Chart(ctx, {
    type: "line",
    data: {
      labels: sharpes.map((_, i) => i),
      datasets: [
        { data: sharpes, borderColor: "#60a5fa", borderWidth: 1, pointRadius: 0 },
        { data: best, borderColor: "#f59e0b", borderWidth: 1.5, pointRadius: 0, borderDash: [4, 2] },
      ]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: { ticks: { color: "#6b7280" }, grid: { color: "#1f2937" } }
      }
    }
  });
}
