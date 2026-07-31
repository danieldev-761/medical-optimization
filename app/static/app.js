"use strict";

const CHART_COLORS = { original: "#fbbf24", limpio: "#5eead4", ingles: "#818cf8", grid: "rgba(148,163,184,0.08)" };
const fmtUSD = (v) => "$" + (Number(v) || 0).toFixed(6);
const fmtInt = (v) => (Number(v) || 0).toLocaleString("es-CO");
const fmtPct = (v) => (Number(v) || 0).toFixed(2) + "%";

const charts = {};
let state = null;

async function loadResults() {
  const res = await fetch("/api/results");
  if (!res.ok) throw new Error((await res.json()).detail || "sin resultados");
  return res.json();
}

function baseOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { labels: { color: "#e6e9ef", font: { family: "ui-monospace", size: 11 } } } },
    scales: {
      x: { ticks: { color: "#8b93a7" }, grid: { color: CHART_COLORS.grid } },
      y: { ticks: { color: "#8b93a7" }, grid: { color: CHART_COLORS.grid } },
    },
  };
}

function renderReal(d) {
  const pp = d.preprocesamiento || {};
  const t = d.totales || {};
  const a = d.ahorro || {};

  setText("k-filas", fmtInt(pp.filas_leidas));
  setText("k-validas", fmtInt(pp.filas_validas ?? d.n_procesadas));
  setText("k-descartadas", fmtInt((pp.filas_descartadas_vacio ?? 0) + (pp.filas_por_error ?? 0)));
  setText("k-dup", fmtInt(pp.duplicados_eliminados));

  setText("v-original-tokens", fmtInt(t.tokens_original));
  setText("v-original-costo", fmtUSD(t.costo_original));
  setText("v-original-avg", (d.promedio_tokens_por_mensaje?.original ?? 0).toFixed(2));
  setText("v-limpio-tokens", fmtInt(t.tokens_limpio));
  setText("v-limpio-costo", fmtUSD(t.costo_limpio));
  setText("v-limpio-avg", (d.promedio_tokens_por_mensaje?.limpio ?? 0).toFixed(2));
  setText("v-ingles-tokens", fmtInt(t.tokens_ingles));
  setText("v-ingles-costo", fmtUSD(t.costo_ingles));
  setText("v-ingles-avg", (d.promedio_tokens_por_mensaje?.ingles ?? 0).toFixed(2));

  setText("s-limpio", fmtUSD(a.limpio_absoluto));
  setText("s-limpio-pct", fmtPct(a.limpio_pct));
  setText("s-ingles", fmtUSD(a.ingles_absoluto));
  setText("s-ingles-pct", fmtPct(a.ingles_pct));
  setWidth("s-limpio-bar", clampPct(a.limpio_pct, 100));
  setWidth("s-ingles-bar", clampPct(a.ingles_pct, 100));

  const hasIngles = (t.tokens_ingles ?? 0) > 0;
  const variants = hasIngles
    ? ["original", "limpio", "ingles"]
    : ["original", "limpio"];

  barChart("ch-tokens", variants.map((v) => v.toUpperCase()), variants.map((v) => t["tokens_" + v]),
    (ctx) => ctx.p0.chart.data.datasets[0].backgroundColor);
  barChart("ch-cost", variants.map((v) => v.toUpperCase()), variants.map((v) => t["costo_" + v]), null, "$");

  const savingsLabels = [];
  const savingsVals = [];
  if (hasIngles) { savingsLabels.push("vs inglés"); savingsVals.push(a.ingles_pct || 0); }
  savingsLabels.push("vs limpio"); savingsVals.push(a.limpio_pct || 0);
  horizChart("ch-savings", savingsLabels, savingsVals);

  const acciones = d.distribucion_acciones || {};
  doughnut("ch-acciones", Object.keys(acciones), Object.values(acciones));

  renderTimings(d._meta?.tiempos_seg);
}

function renderProyeccion(d) {
  const proy = d.proyeccion || {};
  const meta = proy._meta || {};
  const hasIngles = !!proy.ingles;
  const variants = hasIngles ? ["original", "limpio", "ingles"] : ["original", "limpio"];
  const periods = ["diario", "mensual", "trimestral", "anual"];

  const cards = document.getElementById("proj-cards");
  cards.innerHTML = "";
  periods.forEach((p) => {
    const v = variants[hasIngles ? 1 : 0];
    const data = proy[v]?.[p] || { costo: 0 };
    const art = document.createElement("article");
    art.className = "card proj-card";
    art.innerHTML = `
      <span class="period">${p}</span>
      <span class="amount total">${fmtUSD(data.costo)}</span>
      <div class="proj-rows">
        ${variants.map((v2) => {
          const d2 = proy[v2]?.[p] || { costo: 0, tokens: 0 };
          return `<span>${v2[0].toUpperCase()} <b>${fmtUSD(d2.costo)}</b></span>`;
        }).join("")}
      </div>
      <div class="proj-rows">${fmtInt(data.tokens ?? 0)} tokens · ${fmtInt(data.mensajes ?? 0)} msgs</div>`;
    cards.appendChild(art);
  });

  const labels = periods.map((p) => p[0].toUpperCase() + p.slice(1));
  const ds = variants.map((v, i) => ({
    label: v,
    data: periods.map((p) => proy[v]?.[p]?.costo ?? 0),
    backgroundColor: [CHART_COLORS.original, CHART_COLORS.limpio, CHART_COLORS.ingles][i],
    borderRadius: 6,
  }));
  upsertChart("ch-proj", { type: "bar", data: { labels, datasets: ds }, options: baseOptions() });

  const dsT = variants.map((v, i) => ({
    label: v,
    data: periods.map((p) => proy[v]?.[p]?.tokens ?? 0),
    borderColor: [CHART_COLORS.original, CHART_COLORS.limpio, CHART_COLORS.ingles][i],
    backgroundColor: "transparent",
    tension: 0.35,
    pointRadius: 4,
  }));
  upsertChart("ch-proj-tokens", { type: "line", data: { labels, datasets: dsT }, options: baseOptions() });
}

function renderTimings(timings) {
  const el = document.getElementById("timings");
  if (!timings || !Object.keys(timings).length) {
    el.innerHTML = '<span class="muted">Disponible al procesar vía /api/analyze.</span>';
    return;
  }
  const total = Object.values(timings).reduce((s, v) => s + v, 0);
  el.innerHTML = Object.entries(timings)
    .map(([k, v]) => `<div class="timing"><span>${k}</span><b>${v.toFixed(3)}s</b></div>`)
    .join("") + `<div class="timing"><span>total</span><b>${total.toFixed(3)}s</b></div>`;
}

function applyToUI(d) {
  const engine = d._meta?.motor_traduccion || d._meta?.engine;
  const badge = document.getElementById("engine-badge");
  badge.textContent = "motor: " + (engine || "—");
  if (engine === "deep_translator") { badge.style.color = "var(--warn)"; }
  else if (engine === "ctranslate2") { badge.style.color = "var(--accent)"; }
  else { badge.style.color = "var(--muted)"; }

  const hasIngles = (d.totales?.tokens_ingles ?? 0) > 0;
  const inglCard = document.querySelector(".variant.ingles");
  inglCard.style.opacity = hasIngles ? "1" : "0.45";
  renderReal(d);
  renderProyeccion(d);
}

async function init() {
  try {
    state = await loadResults();
    applyToUI(state);
  } catch (e) {
    document.querySelector(".run-status").textContent = "ⓘ " + e.message;
  }
}

/* --- charts helpers --- */
function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
function setWidth(id, val) { const el = document.getElementById(id); if (el) el.style.width = val + "%"; }
function clampPct(v, max) { return Math.max(0, Math.min(Number(v) || 0, max)); }

function makeDataset(vals, color, opts = {}) {
  return Object.assign({ label: "", data: vals, backgroundColor: color, borderRadius: 6 }, opts);
}
function canvas(id, config) {
  const canvas = document.getElementById(id);
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(canvas.getContext("2d"), config);
}
function barChart(id, labels, vals, colorFn, prefix = "") {
  const colors = ["#fbbf24", "#5eead4", "#818cf8"];
  const ds = makeDataset(vals, vals.map((_, i) => colors[i]));
  canvas(id, { type: "bar", data: { labels, datasets: [ds] }, options: baseOptions() });
}
function horizChart(id, labels, vals) {
  const ds = makeDataset(vals, ["#818cf8", "#5eead4"]);
  canvas(id, {
    type: "bar", data: { labels, datasets: [ds] },
    options: Object.assign(baseOptions(), { indexAxis: "y" }),
  });
}
function doughnut(id, labels, vals) {
  canvas(id, {
    type: "doughnut", data: { labels, datasets: [{ data: vals, backgroundColor: ["#5eead4", "#fbbf24", "#818cf8", "#34d399", "#f87171", "#facc15", "#a78bfa"] }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "right", labels: { color: "#8b93a7", font: { family: "ui-monospace", size: 11 } } } } },
  });
}
function upsertChart(id, config) {
  const canvasEl = document.getElementById(id);
  if (!canvasEl) return;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(canvasEl.getContext("2d"), config);
}

/* --- tabs --- */
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("is-active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("is-active"));
    btn.classList.add("is-active");
    document.getElementById("view-" + btn.dataset.view).classList.add("is-active");
  });
});

/* --- upload --- */
const dz = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const runBtn = document.getElementById("btn-run");
const statusEl = document.getElementById("run-status");

dz.addEventListener("click", () => fileInput.click());
dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
dz.addEventListener("drop", (e) => {
  e.preventDefault(); dz.classList.remove("drag");
  if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => { if (fileInput.files.length) setFile(fileInput.files[0]); });

function setFile(file) {
  runBtn.disabled = false;
  statusEl.textContent = "archivo: " + file.name;
  statusEl.className = "run-status";
  runBtn.onclick = () => runPipeline(file);
}

async function runPipeline(file) {
  runBtn.disabled = true;
  statusEl.textContent = "procesando… (puede tardar)";
  statusEl.className = "run-status busy";
  const fd = new FormData();
  fd.append("file", file);
  const qs = new URLSearchParams({
    optimize_tokens: document.getElementById("opt-tokens").checked,
    engine: document.getElementById("opt-engine").value,
  });
  try {
    const res = await fetch("/api/analyze?" + qs, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    state = data;
    applyToUI(state);
    statusEl.textContent = "✓ listo · " + file.name;
    statusEl.className = "run-status ok";
  } catch (e) {
    statusEl.textContent = "✗ " + e.message;
    statusEl.className = "run-status err";
  } finally {
    runBtn.disabled = false;
  }
}

document.getElementById("btn-reload").addEventListener("click", async () => {
  try { state = await loadResults(); applyToUI(state); }
  catch (e) { statusEl.textContent = "ⓘ " + e.message; statusEl.className = "run-status"; }
});

init();
