"use strict";

const CHART_COLORS = { original: "#fbbf24", limpio: "#5eead4", ingles: "#818cf8", grid: "rgba(148,163,184,0.08)" };
const fmtUSD = (v) => "$" + (Number(v) || 0).toFixed(6);
const fmtInt = (v) => (Number(v) || 0).toLocaleString("es-CO");
const fmtPct = (v) => (Number(v) || 0).toFixed(2) + "%";

const charts = {};
let busy = false;

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
  const variants = hasIngles ? ["original", "limpio", "ingles"] : ["original", "limpio"];

  barChart("ch-tokens", variants.map((v) => v.toUpperCase()), variants.map((v) => t["tokens_" + v]));
  barChart("ch-cost", variants.map((v) => v.toUpperCase()), variants.map((v) => t["costo_" + v]));

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
  const hasIngles = !!proy.ingles;
  const variants = hasIngles ? ["original", "limpio", "ingles"] : ["original", "limpio"];
  const periods = ["diario", "mensual", "trimestral", "anual"];

  const cards = document.getElementById("proj-cards");
  cards.innerHTML = "";
  periods.forEach((p) => {
    const data = proy[variants[0]]?.[p] || { costo: 0 };
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
    el.innerHTML = '<span class="muted">Sin datos de timing.</span>';
    return;
  }
  const total = Object.values(timings).reduce((s, v) => s + v, 0);
  el.innerHTML = Object.entries(timings)
    .map(([k, v]) => `<div class="timing"><span>${k}</span><b>${v.toFixed(3)}s</b></div>`)
    .join("") + `<div class="timing"><span>total</span><b>${total.toFixed(3)}s</b></div>`;
}

function applyToUI(d) {
  const engine = d._meta?.motor_traduccion;
  const badge = document.getElementById("engine-badge");
  badge.hidden = false;
  badge.textContent = "motor: " + (engine || "—");
  if (engine === "deep_translator") { badge.style.color = "var(--warn)"; }
  else if (engine === "ctranslate2") { badge.style.color = "var(--accent)"; }
  else { badge.style.color = "var(--muted)"; }

  document.getElementById("btn-download").hidden = false;

  const hasIngles = (d.totales?.tokens_ingles ?? 0) > 0;
  document.querySelector(".variant.ingles").style.opacity = hasIngles ? "1" : "0.45";
  renderReal(d);
  renderProyeccion(d);
  document.getElementById("analysis").hidden = false;
  document.getElementById("analysis").scrollIntoView({ behavior: "smooth" });
}

/* --- charts helpers --- */
function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
function setWidth(id, val) { const el = document.getElementById(id); if (el) el.style.width = val + "%"; }
function clampPct(v, max) { return Math.max(0, Math.min(Number(v) || 0, max)); }

function canvas(id, config) {
  const el = document.getElementById(id);
  if (!el) return;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(el.getContext("2d"), config);
}
function barChart(id, labels, vals) {
  const colors = ["#fbbf24", "#5eead4", "#818cf8"];
  canvas(id, { type: "bar", data: { labels, datasets: [makeDataset(vals, vals.map((_, i) => colors[i]))] }, options: baseOptions() });
}
function makeDataset(vals, color) {
  return { label: "", data: vals, backgroundColor: color, borderRadius: 6 };
}
function horizChart(id, labels, vals) {
  canvas(id, {
    type: "bar", data: { labels, datasets: [makeDataset(vals, ["#818cf8", "#5eead4"])] },
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
  const el = document.getElementById(id);
  if (!el) return;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(el.getContext("2d"), config);
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

/* --- upload + progreso en vivo --- */
const dz = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const runBtn = document.getElementById("btn-run");
const statusEl = document.getElementById("run-status");
const progressWrap = document.getElementById("progress-wrap");
const progressFill = document.getElementById("progress-fill");
const progressLabel = document.getElementById("progress-label");
const progressPct = document.getElementById("progress-pct");

dz.addEventListener("click", () => fileInput.click());
dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
dz.addEventListener("drop", (e) => {
  e.preventDefault(); dz.classList.remove("drag");
  if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => { if (fileInput.files.length) setFile(fileInput.files[0]); });

function setFile(file) {
  if (busy) return;
  runBtn.disabled = false;
  statusEl.textContent = "archivo: " + file.name;
  statusEl.className = "run-status";
  runBtn.onclick = () => runPipeline(file);
}

function setProgress(label, pct) {
  progressWrap.hidden = false;
  progressLabel.textContent = label;
  progressPct.textContent = Math.round(pct) + "%";
  progressFill.style.width = Math.min(100, Math.max(0, pct)) + "%";
}

async function runPipeline(file) {
  if (busy) return;
  busy = true;
  runBtn.disabled = true;
  document.getElementById("analysis").hidden = true;
  statusEl.textContent = "procesando…";
  statusEl.className = "run-status busy";
  setProgress("iniciando…", 0);

  const fd = new FormData();
  fd.append("file", file);
  const qs = new URLSearchParams({
    optimize_tokens: document.getElementById("opt-tokens").checked,
    engine: document.getElementById("opt-engine").value,
  });

  try {
    const res = await fetch("/api/analyze/stream?" + qs, { method: "POST", body: fd });
    if (!res.ok || !res.body) throw new Error("No se pudo iniciar el procesamiento");
    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        for (const line of raw.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const evt = JSON.parse(line.slice(6));
          if (evt.type === "stage") setProgress(evt.etapa.replace(/_/g, " "), evt.progreso);
          else if (evt.type === "done") {
            applyToUI(evt.data);
            statusEl.textContent = "✓ análisis listo · " + file.name;
            statusEl.className = "run-status ok";
            progressWrap.hidden = true;
          } else if (evt.type === "error") throw new Error(evt.detail);
        }
      }
    }
  } catch (e) {
    statusEl.textContent = "✗ " + e.message;
    statusEl.className = "run-status err";
    progressWrap.hidden = true;
  } finally {
    busy = false;
    runBtn.disabled = false;
  }
}
