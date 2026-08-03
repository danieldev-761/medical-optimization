"use strict";

/* ============================================================
   Medical Opt · dashboard
   ============================================================ */

const MONO = "ui-monospace, 'Cascadia Code', 'JetBrains Mono', Consolas, monospace";
const C = {
  original: "#fbbf24",
  limpio: "#5eead4",
  ingles: "#818cf8",
  grid: "rgba(148,163,184,0.08)",
  text: "#e8ecf4",
  muted: "#8b93a7",
  panel: "rgba(13,20,32,0.96)",
  border: "rgba(94,234,212,0.35)",
  doughnut: ["#5eead4", "#fbbf24", "#818cf8", "#34d399", "#f87171", "#facc15", "#a78bfa"],
};

const fmtUSD = (v) => {
  const n = Number(v) || 0;
  const s = n >= 1 ? n.toFixed(2) : n.toFixed(6);
  return "$" + s.replace(/\.?0+$/, "");
};
const fmtInt = (v) => (Number(v) || 0).toLocaleString("es-CO");
const fmtPct = (v) => (Number(v) || 0).toFixed(2) + "%";
const fmtAbbr = (v) => {
  const n = Number(v) || 0;
  if (Math.abs(n) >= 1e9) return (n / 1e9).toFixed(1) + "B";
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return (Math.round(n * 10) / 10).toString();
};

const charts = {};
const chartSig = {};
let busy = false;

/* ---------- tiny helpers ---------- */
const $ = (id) => document.getElementById(id);
const setText = (id, val) => { const el = $(id); if (el) el.textContent = val; };
const setWidth = (id, val) => { const el = $(id); if (el) el.style.width = val + "%"; };
const clampPct = (v, max) => Math.max(0, Math.min(Number(v) || 0, max));
const rgba = (hex, a) => {
  const m = hex.replace("#", "");
  const r = parseInt(m.slice(0, 2), 16), g = parseInt(m.slice(2, 4), 16), b = parseInt(m.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
};

function setSeg(id, text, cls) {
  const el = $(id);
  if (!el) return;
  el.textContent = text;
  el.className = "seg" + (cls ? " " + cls : "");
}

/* ---------- toasts ---------- */
function toast(message, type = "ok", ms = 4200) {
  const root = $("toast-root");
  if (!root) return;
  const icons = {
    ok: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
    err: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>',
    warn: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>',
  };
  const el = document.createElement("div");
  el.className = "toast " + type;
  el.innerHTML = '<span class="toast-ico" style="color:var(--' + (type === "ok" ? "ok" : type === "err" ? "danger" : "warn") + ')">' + (icons[type] || icons.ok) + "</span><span>" + message + "</span>";
  root.appendChild(el);
  setTimeout(() => {
    el.classList.add("leaving");
    el.addEventListener("animationend", () => el.remove(), { once: true });
  }, ms);
}

/* ============================================================
   Charts
   ============================================================ */

Chart.register({
  id: "valueLabels",
  afterDatasetsDraw(chart, _args, opts) {
    if (!opts || !opts.display) return;
    const meta = chart.getDatasetMeta(0);
    if (!meta.data || meta.data.length > opts.maxBars) return;
    const { ctx } = chart;
    const horizontal = chart.options.indexAxis === "y";
    ctx.save();
    ctx.font = opts.font || "600 11px " + MONO;
    ctx.fillStyle = opts.color || "#8b93a7";
    ctx.textAlign = horizontal ? "left" : "center";
    ctx.textBaseline = horizontal ? "middle" : "alphabetic";
    meta.data.forEach((bar, i) => {
      const v = chart.data.datasets[0].data[i];
      if (typeof v !== "number" || !Number.isFinite(v)) return;
      const label = opts.fmt ? opts.fmt(v) : fmtAbbr(v);
      ctx.fillText(label, horizontal ? bar.x + 6 : bar.x, horizontal ? bar.y : bar.y - 6);
    });
    ctx.restore();
  },
});

Chart.register({
  id: "centerText",
  afterDraw(chart, _args, opts) {
    if (!opts || !opts.display || chart.config.type !== "doughnut") return;
    const data = chart.data.datasets[0].data;
    if (!data || !data.length) return;
    const total = data.reduce((s, v) => s + (Number(v) || 0), 0);
    const { left, right, top, bottom } = chart.chartArea;
    const cx = (left + right) / 2;
    const cy = (top + bottom) / 2;
    const { ctx } = chart;
    ctx.save();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = opts.subColor || "#8b93a7";
    ctx.font = "10px " + MONO;
    ctx.fillText(opts.subLabel || "total", cx, cy - 12);
    ctx.fillStyle = opts.color || "#e8ecf4";
    ctx.font = "600 18px " + MONO;
    ctx.fillText(fmtAbbr(total), cx, cy + 8);
    ctx.restore();
  },
});

function labelValue(ctx) {
  const p = ctx.parsed;
  if (p === undefined || p === null) return 0;
  return typeof p === "object" ? (p.y ?? p.v ?? p.r ?? 0) : p;
}

function tooltipCfg(fmt) {
  const format = fmt || fmtAbbr;
  return {
    backgroundColor: C.panel,
    borderColor: C.border,
    borderWidth: 1,
    titleColor: C.text,
    bodyColor: C.muted,
    titleFont: { family: MONO, size: 12, weight: "600" },
    bodyFont: { family: MONO, size: 12 },
    padding: 10,
    cornerRadius: 8,
    displayColors: true,
    boxPadding: 4,
    callbacks: { label: (ctx) => " " + format(labelValue(ctx)) },
  };
}

function baseOptions(opts = {}) {
  const s = opts.scales || {};
  const defY = { ticks: { color: C.muted, font: { family: MONO, size: 11 }, callback: (v) => fmtAbbr(v) }, grid: { color: C.grid } };
  const defX = { ticks: { color: C.muted, font: { family: MONO, size: 11 } }, grid: { color: C.grid } };
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 700, easing: "easeOutQuart" },
    plugins: Object.assign(
      { legend: { display: false }, tooltip: tooltipCfg() },
      opts.plugins || {}
    ),
    scales: {
      x: Object.assign(defX, s.x || {}),
      y: Object.assign(defY, s.y || {}),
    },
  };
}

const usdAxis = { y: { ticks: { color: C.muted, font: { family: MONO, size: 11 }, callback: (v) => fmtUSD(v) } } };

function legendCfg(position = "bottom") {
  return {
    display: true,
    position,
    labels: {
      color: C.muted,
      font: { family: MONO, size: 11 },
      usePointStyle: true,
      pointStyle: "circle",
      boxWidth: 8,
      boxHeight: 8,
      padding: 16,
    },
  };
}

function barGradient(ctx, color) {
  const area = ctx.chart.chartArea;
  if (!area) return color;
  const g = ctx.chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
  g.addColorStop(0, rgba(color, 0.95));
  g.addColorStop(1, rgba(color, 0.35));
  return g;
}

function lineGradient(ctx, color) {
  const area = ctx.chart.chartArea;
  if (!area) return color;
  const g = ctx.chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
  g.addColorStop(0, rgba(color, 0.28));
  g.addColorStop(1, rgba(color, 0));
  return g;
}

function upsertChart(id, config) {
  const el = $(id);
  if (!el) return;
  const sig = [
    config.type,
    (config.data.labels || []).join(","),
    (config.data.datasets || []).map((d) => (d.data || []).join(",")).join(";"),
  ].join("|");
  if (charts[id] && chartSig[id] === sig) return;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(el.getContext("2d"), config);
  chartSig[id] = sig;
}

function barChart(id, labels, vals, opts = {}) {
  const colors = opts.colors || [C.original, C.limpio, C.ingles];
  const options = baseOptions(Object.assign({
    plugins: { legend: { display: false }, valueLabels: { display: false } },
  }, opts));
  upsertChart(id, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "",
        data: vals,
        backgroundColor: (c) => barGradient(c, colors[c.dataIndex] || colors[0]),
        hoverBackgroundColor: (c) => rgba(colors[c.dataIndex] || colors[0], 0.85),
        borderRadius: 8,
        maxBarThickness: 64,
      }],
    },
    options,
  });
}

function doughnut(id, labels, vals, opts = {}) {
  upsertChart(id, {
    type: "doughnut",
    data: { labels, datasets: [{ data: vals, backgroundColor: C.doughnut, borderWidth: 0, hoverOffset: 6 }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 700, easing: "easeOutQuart" },
      cutout: "62%",
      plugins: Object.assign(
        { legend: legendCfg("right"), tooltip: tooltipCfg(fmtInt), centerText: { display: true, subLabel: "total", color: C.text, subColor: C.muted } },
        opts.plugins || {}
      ),
    },
  });
}

function makeLineDataset(label, data, color) {
  return {
    label,
    data,
    borderColor: color,
    backgroundColor: (c) => lineGradient(c, color),
    fill: true,
    tension: 0.4,
    borderWidth: 2,
    pointRadius: 3,
    pointHoverRadius: 5,
    pointBackgroundColor: color,
  };
}

/* ============================================================
   Stage stepper
   ============================================================ */

const STEPS = [
  "Ingesta",
  "Validación",
  "Preprocesamiento",
  "Tokenización ES",
  "Traducción EN",
  "Costeo",
  "Reporte",
];
const STAGE_TO_STEP = {
  ingesta: 0,
  validacion: 1,
  preprocesamiento: 2,
  tokens_original: 3,
  tokens_limpio: 3,
  traduccion: 4,
  tokens_ingles: 4,
  costeo: 5,
  reporte: 6,
};
const CHECK_SVG = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';
const DOT_SVG = '<svg viewBox="0 0 24 24" width="10" height="10" fill="currentColor"><circle cx="12" cy="12" r="6"/></svg>';

let stepperCurrent = -1;

function buildStepper() {
  const list = $("stage-list");
  if (!list) return;
  list.innerHTML = STEPS.map((label, i) =>
    `<li class="stage-step" data-step="${i}" role="listitem"><span class="stage-ico">${DOT_SVG}</span><span>${label}</span></li>`
  ).join("");
}

function renderSteps() {
  const list = $("stage-list");
  if (!list) return;
  list.querySelectorAll(".stage-step").forEach((li) => {
    const i = Number(li.dataset.step);
    const ico = li.querySelector(".stage-ico");
    if (i < stepperCurrent) {
      li.className = "stage-step done";
      if (ico) ico.innerHTML = CHECK_SVG;
    } else if (i === stepperCurrent) {
      li.className = "stage-step active";
      if (ico) ico.innerHTML = DOT_SVG;
    } else {
      li.className = "stage-step";
      if (ico) ico.innerHTML = DOT_SVG;
    }
  });
}

function advanceStepper(stageName) {
  const idx = STAGE_TO_STEP[stageName];
  if (idx === undefined) return;
  stepperCurrent = Math.max(stepperCurrent, idx);
  renderSteps();
}

function finishStepper() {
  stepperCurrent = STEPS.length;
  renderSteps();
}

/* ============================================================
   Rendering
   ============================================================ */

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

  barChart("ch-tokens", variants.map((v) => v.toUpperCase()), variants.map((v) => t["tokens_" + v]), {
    plugins: { valueLabels: { display: true, maxBars: 4, fmt: fmtAbbr } },
  });
  barChart("ch-cost", variants.map((v) => v.toUpperCase()), variants.map((v) => t["costo_" + v]), {
    plugins: { valueLabels: { display: true, maxBars: 4, fmt: fmtUSD }, tooltip: tooltipCfg(fmtUSD) },
    scales: usdAxis,
  });

  const savingsLabels = [];
  const savingsVals = [];
  if (hasIngles) { savingsLabels.push("vs inglés"); savingsVals.push(a.ingles_pct || 0); }
  savingsLabels.push("vs limpio"); savingsVals.push(a.limpio_pct || 0);
  horizChart("ch-savings", savingsLabels, savingsVals);

  const acciones = d.distribucion_acciones || {};
  doughnut("ch-acciones", Object.keys(acciones), Object.values(acciones));

  renderEspecialidades(d.distribucion_especialidades || {});

  renderTimings(d._meta?.tiempos_seg);
}

function renderEspecialidades(dist) {
  const entries = Object.entries(dist)
    .map(([k, v]) => [k, Number(v) || 0])
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);
  const box = $("ch-especialidades")?.parentElement;
  if (!box) return;
  box.querySelectorAll(".chart-empty").forEach((n) => n.remove());
  const canvas = $("ch-especialidades");
  if (!entries.length) {
    if (canvas) canvas.style.display = "none";
    const empty = document.createElement("div");
    empty.className = "chart-empty";
    empty.textContent = "Sin datos de especialidades.";
    box.appendChild(empty);
    delete charts["ch-especialidades"];
    delete chartSig["ch-especialidades"];
    return;
  }
  if (canvas) canvas.style.display = "";
  const labels = entries.map(([k]) => k);
  const vals = entries.map(([, v]) => v);
  const colors = ["#5eead4", "#34d399", "#818cf8", "#a78bfa", "#fbbf24", "#f87171", "#facc15", "#22d3ee"];
  upsertChart("ch-especialidades", {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "",
        data: vals,
        backgroundColor: (c) => barGradient(c, colors[c.dataIndex % colors.length]),
        hoverBackgroundColor: (c) => rgba(colors[c.dataIndex % colors.length], 0.85),
        borderRadius: 8,
        maxBarThickness: 28,
      }],
    },
    options: Object.assign(baseOptions(), {
      indexAxis: "y",
      plugins: Object.assign({}, baseOptions().plugins, {
        legend: { display: false },
        tooltip: tooltipCfg(fmtInt),
        valueLabels: { display: false },
      }),
      scales: {
        x: { ticks: { color: C.muted, font: { family: MONO, size: 11 }, callback: (v) => fmtAbbr(v) }, grid: { color: C.grid } },
        y: { ticks: { color: C.text, font: { family: MONO, size: 11 } }, grid: { display: false } },
      },
    }),
  });
}

function horizChart(id, labels, vals) {
  const colors = ["#818cf8", "#5eead4"];
  upsertChart(id, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "",
        data: vals,
        backgroundColor: (c) => barGradient(c, colors[c.dataIndex % colors.length]),
        hoverBackgroundColor: (c) => rgba(colors[c.dataIndex % colors.length], 0.85),
        borderRadius: 8,
        maxBarThickness: 34,
      }],
    },
    options: Object.assign(baseOptions(), {
      indexAxis: "y",
      plugins: Object.assign({}, baseOptions().plugins, {
        legend: { display: false },
        tooltip: tooltipCfg((v) => Number(v).toFixed(2) + "%"),
        valueLabels: { display: true, maxBars: 4, fmt: (v) => Number(v).toFixed(1) + "%" },
      }),
    }),
  });
}

function renderProyeccion(d) {
  const proy = d.proyeccion || {};
  const hasIngles = !!proy.ingles;
  const variants = hasIngles ? ["original", "limpio", "ingles"] : ["original", "limpio"];
  const periods = ["diario", "mensual", "trimestral", "anual"];

  const cards = $("proj-cards");
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
  const colors = [C.original, C.limpio, C.ingles];

  const dsBar = variants.map((v, i) => ({
    label: v,
    data: periods.map((p) => proy[v]?.[p]?.costo ?? 0),
    backgroundColor: (c) => barGradient(c, colors[i]),
    hoverBackgroundColor: (c) => rgba(colors[i], 0.85),
    borderRadius: 8,
    maxBarThickness: 48,
  }));
  upsertChart("ch-proj", {
    type: "bar",
    data: { labels, datasets: dsBar },
    options: Object.assign(baseOptions({ scales: usdAxis }), {
      plugins: Object.assign({}, baseOptions().plugins, {
        legend: legendCfg(),
        tooltip: tooltipCfg(fmtUSD),
        valueLabels: { display: false },
      }),
    }),
  });

  const dsLine = variants.map((v, i) => makeLineDataset(v, periods.map((p) => proy[v]?.[p]?.tokens ?? 0), colors[i]));
  upsertChart("ch-proj-tokens", {
    type: "line",
    data: { labels, datasets: dsLine },
    options: Object.assign(baseOptions(), {
      plugins: Object.assign({}, baseOptions().plugins, {
        legend: legendCfg(),
        tooltip: tooltipCfg(fmtInt),
      }),
    }),
  });
}

function renderTimings(timings) {
  const el = $("timings");
  const badge = $("total-time-badge");
  if (!timings || !Object.keys(timings).length) {
    el.innerHTML = '<span class="muted">Sin datos de timing.</span>';
    if (badge) badge.textContent = "";
    return;
  }
  const total = Object.values(timings).reduce((s, v) => s + v, 0);
  const totalFmt = total >= 60 ? (total / 60).toFixed(2) + " min (" + total.toFixed(1) + " s)" : total.toFixed(2) + " s";
  if (badge) badge.textContent = "⏱ Tiempo total de carga: " + totalFmt;
  el.innerHTML = Object.entries(timings)
    .map(([k, v]) => `<div class="timing"><span>${k}</span><b>${v.toFixed(3)}s</b></div>`)
    .join("") + `<div class="timing"><span>total</span><b>${total.toFixed(3)}s</b></div>`;
}

function setDownloadState(enabled, href, statusText) {
  const btn = $("btn-download");
  const status = $("download-status");
  if (btn) {
    if (enabled && href) {
      btn.href = href;
      btn.classList.remove("disabled");
      btn.removeAttribute("aria-disabled");
    } else {
      btn.removeAttribute("href");
      btn.classList.add("disabled");
      btn.setAttribute("aria-disabled", "true");
    }
  }
  if (status) {
    status.textContent = statusText || "";
    status.classList.toggle("busy", !!statusText && /generando/i.test(statusText));
  }
}

function renderMetrics(d, { scroll = true } = {}) {
  const meta = d._meta || {};
  const engine = meta.motor_traduccion;

  const prompt = $("prompt-cmd");
  prompt.textContent = "analyze --done";
  prompt.className = "prompt-cmd ok";

  setSeg("sl-engine", "engine: " + (engine || "—"),
    engine === "ctranslate2" ? "seg-ok" : engine === "deep_translator" ? "seg-warn" : "");
  setSeg("sl-rows", "rows: " + fmtInt(d.n_procesadas));

  const hasIngles = (d.totales?.tokens_ingles ?? 0) > 0;
  const savePct = hasIngles ? d.ahorro?.ingles_pct : d.ahorro?.limpio_pct;
  setSeg("sl-save", "saving: " + fmtPct(savePct), "seg-ok");

  const timings = meta.tiempos_seg;
  if (timings) {
    const total = Object.values(timings).reduce((s, v) => s + v, 0);
    const timeStr = total >= 60 ? (total / 60).toFixed(1) + "m" : total.toFixed(1) + "s";
    setSeg("sl-time", "⏱ duró " + timeStr);
  }

  document.querySelector(".variant.ingles").style.opacity = hasIngles ? "1" : "0.45";
  renderReal(d);
  renderProyeccion(d);
  $("analysis").hidden = false;
  if (scroll) $("analysis").scrollIntoView({ behavior: "smooth" });
}

function applyToUI(d, { scroll = true } = {}) {
  renderMetrics(d, { scroll });
  const meta = d._meta || {};
  const excelReady = !!meta.excel_disponible;
  const href = meta.run_id ? "/api/download?run_id=" + meta.run_id : "/api/download";
  setDownloadState(
    excelReady,
    href,
    excelReady ? "Excel listo para descargar." : "El Excel no está disponible aún; la descarga se habilita cuando esté listo."
  );
  if (excelReady) toast("Excel listo para descargar.", "ok");
}

async function loadLatestResults() {
  try {
    const res = await fetch("/api/results");
    if (!res.ok) throw new Error("no results");
    const d = await res.json();
    applyToUI(d, { scroll: false });
  } catch {
    setDownloadState(false, null, "Aún no hay métricas. Ejecuta un análisis para habilitar la descarga.");
  }
}
window.addEventListener("DOMContentLoaded", () => {
  buildStepper();
  loadLatestResults();
});

/* ============================================================
   Tabs
   ============================================================ */
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => {
      b.classList.remove("is-active");
      b.setAttribute("aria-selected", "false");
    });
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("is-active"));
    btn.classList.add("is-active");
    btn.setAttribute("aria-selected", "true");
    $("view-" + btn.dataset.view).classList.add("is-active");
  });
});

/* ============================================================
   Upload + file chip
   ============================================================ */
const dz = $("dropzone");
const fileInput = $("file-input");
const runBtn = $("btn-run");
const statusEl = $("run-status");
const progressWrap = $("progress-wrap");
const progressFill = $("progress-fill");
const progressLabel = $("progress-label");
const progressPct = $("progress-pct");
const progressBar = $("progress-wrap")?.querySelector(".progress-bar");
const fileChip = $("file-chip");
const fileChipName = $("file-chip-name");
const fileChipClear = $("file-chip-clear");

let selectedFile = null;

dz.addEventListener("click", () => fileInput.click());
dz.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    fileInput.click();
  }
});
dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
dz.addEventListener("drop", (e) => {
  e.preventDefault();
  dz.classList.remove("drag");
  if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => { if (fileInput.files.length) setFile(fileInput.files[0]); });
fileChipClear.addEventListener("click", (e) => {
  e.stopPropagation();
  clearFile();
});

function setFile(file) {
  if (busy) return;
  selectedFile = file;
  runBtn.disabled = false;
  statusEl.textContent = "archivo: " + file.name;
  statusEl.className = "run-status";
  fileChip.hidden = false;
  fileChipName.textContent = file.name;
  runBtn.onclick = () => runPipeline(file);
  toast("Archivo listo: " + file.name, "ok");
}

function clearFile() {
  selectedFile = null;
  fileInput.value = "";
  runBtn.disabled = true;
  runBtn.onclick = null;
  statusEl.textContent = "";
  statusEl.className = "run-status";
  fileChip.hidden = true;
}

function setProgress(label, pct) {
  progressWrap.hidden = false;
  progressLabel.textContent = label;
  progressPct.textContent = Math.round(pct) + "%";
  progressFill.style.width = Math.min(100, Math.max(0, pct)) + "%";
  if (progressBar) {
    progressBar.setAttribute("aria-valuenow", String(Math.round(pct)));
    progressBar.setAttribute("aria-valuetext", label + " · " + Math.round(pct) + "%");
  }
}

async function runPipeline(file) {
  if (busy) return;
  busy = true;
  stepperCurrent = -1;
  buildStepper();
  renderSteps();
  if ($("stage-steps")) $("stage-steps").hidden = false;
  runBtn.disabled = true;
  $("analysis").hidden = true;
  statusEl.textContent = "procesando…";
  statusEl.className = "run-status busy";
  setProgress("iniciando…", 0);

  const fd = new FormData();
  fd.append("file", file);
  const qs = new URLSearchParams({
    optimize_tokens: $("opt-tokens").checked,
    engine: $("opt-engine").value,
  });

  try {
    const res = await fetch("/api/analyze/stream?" + qs, { method: "POST", body: fd });
    if (!res.ok || !res.body) throw new Error("No se pudo iniciar el procesamiento");
    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    const prompt = $("prompt-cmd");
    setSeg("sl-engine", "engine: running", "seg-warn");

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
          if (evt.type === "stage") {
            setProgress(evt.etapa.replace(/_/g, " "), evt.progreso);
            advanceStepper(evt.etapa);
            prompt.textContent = "analyze --stage " + evt.etapa + " " + Math.round(evt.progreso) + "%";
            prompt.className = "prompt-cmd run";
          } else if (evt.type === "metrics") {
            renderMetrics(evt.data, true);
            setDownloadState(false, null, "Generando Excel… la descarga se habilita cuando esté listo.");
            statusEl.textContent = "✓ análisis listo · generando Excel…";
            statusEl.className = "run-status ok";
          } else if (evt.type === "done") {
            applyToUI(evt.data, { scroll: false });
            statusEl.textContent = "✓ análisis listo · " + file.name;
            statusEl.className = "run-status ok";
            progressWrap.hidden = true;
            if ($("stage-steps")) $("stage-steps").hidden = true;
            finishStepper();
          } else if (evt.type === "error") throw new Error(evt.detail);
        }
      }
    }
  } catch (e) {
    statusEl.textContent = "✗ " + e.message;
    statusEl.className = "run-status err";
    const prompt = $("prompt-cmd");
    prompt.textContent = "error: " + e.message;
    prompt.className = "prompt-cmd err";
    progressWrap.hidden = true;
    if ($("stage-steps")) $("stage-steps").hidden = true;
    toast(e.message, "err");
  } finally {
    busy = false;
    runBtn.disabled = !selectedFile;
  }
}
