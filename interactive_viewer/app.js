const state = {
  data: null,
  selected: null,
  hovered: null,
  chip: {
    canvas: document.getElementById("chipCanvas"),
    ctx: null,
    baseCanvas: document.createElement("canvas"),
    baseDirty: true,
    scale: 1,
    offsetX: 0,
    offsetY: 0,
    radius: 5,
    showPhotoBackground: false,
    wellOpacity: 0.88,
    photoImage: new Image(),
  },
  single: {
    canvas: document.getElementById("singleCanvas"),
    ctx: null,
  },
  all: {
    canvas: document.getElementById("allCanvas"),
    ctx: null,
    baseCanvas: document.createElement("canvas"),
    baseDirty: true,
  },
};

state.chip.ctx = state.chip.canvas.getContext("2d");
state.single.ctx = state.single.canvas.getContext("2d");
state.all.ctx = state.all.canvas.getContext("2d");

const statsEl = document.getElementById("stats");
const tipEl = document.getElementById("wellTip");
const selectedLabelEl = document.getElementById("selectedLabel");
const chartMetricsEl = document.getElementById("chartMetrics");
const experimentBadgeEl = document.getElementById("experimentBadge");
const overviewFooterEl = document.getElementById("overviewFooter");
const photoToggleEl = document.getElementById("photoToggle");
const wellOpacityEl = document.getElementById("wellOpacity");
const wellOpacityValueEl = document.getElementById("wellOpacityValue");
const wellJumpFormEl = document.getElementById("wellJumpForm");
const wellJumpInputEl = document.getElementById("wellJumpInput");
const saveCurveButtonEl = document.getElementById("saveCurveButton");
const navItems = Array.from(document.querySelectorAll(".nav-item"));
const pages = Array.from(document.querySelectorAll(".page"));
const pageTitleEl = document.getElementById("pageTitle");
const pageSubtitleEl = document.getElementById("pageSubtitle");
const sidebarExperimentEl = document.getElementById("sidebarExperiment");
const localImageInputEl = document.getElementById("localImageInput");
const imageCatalogEl = document.getElementById("imageCatalog");
const imageCatalogCountEl = document.getElementById("imageCatalogCount");
const resultImagePreviewEl = document.getElementById("resultImagePreview");
const browserEmptyEl = document.getElementById("browserEmpty");
const qcBeforeImageEl = document.getElementById("qcBeforeImage");
const qcAfterImageEl = document.getElementById("qcAfterImage");
const stage1ImageEl = document.getElementById("stage1Image");
const stage2ImageEl = document.getElementById("stage2Image");
const illuminationMapGridEl = document.getElementById("illuminationMapGrid");
const endpointMapImageEl = document.getElementById("endpointMapImage");
const endpointScatterImageEl = document.getElementById("endpointScatterImage");
const endpointSummaryEl = document.getElementById("endpointSummary");

state.chip.photoImage.src = "./assets/endpoint-photo.jpg";

const COLORS = {
  positive: "#ef1e24",
  negative: "#23629a",
  positiveLine: "#e31a1c",
  negativeLine: "#b8b8b8",
  selected: "#ffd166",
  overviewHighlight: "#ffd400",
  ink: "#092c3d",
  grid: "rgba(22, 64, 86, 0.12)",
  abnormalLine: "#7f8c8d",
  ctLine: "#1f6f8b",
};

const CURVE_Y_MIN = 80;
const CURVE_Y_MAX = 160;
const CT_BASELINE_CYCLES = 8;
const CT_THRESHOLD_SD_MULTIPLIER = 10;
const CT_MIN_THRESHOLD_DELTA = 2;
const CT_MIN_VALID_AMPLITUDE = 5;
const CHART_TITLE_FONT_SIZE = 15;
const CHART_AXIS_FONT_SIZE = 15;
const CHART_TICK_FONT_SIZE = 14;

const PAGE_META = {
  interactive: {
    title: "Interactive Viewing Deck",
    subtitle: "Endpoint chip interaction, single-well fluorescence curve, and curve-cluster highlighting.",
  },
  browser: {
    title: "RT-dPCR Result Browser",
    subtitle: "Browse local experiment images and exported workflow figures.",
  },
  quality: {
    title: "Image Correction QC",
    subtitle: "Review illumination-field correction, representative frames, and stage screening outputs.",
  },
  endpoint: {
    title: "Endpoint Quantification",
    subtitle: "Endpoint fluorescence classification with digital PCR Poisson occupancy correction.",
  },
};

function getCurveYRange() {
  const metaRange = state.data?.meta?.curveY;
  if (!metaRange) {
    return { min: CURVE_Y_MIN, max: CURVE_Y_MAX };
  }
  // Keep the fixed raw-like view when the data naturally lives near 80-160.
  if (metaRange.min >= 60 && metaRange.max <= 180) {
    return { min: CURVE_Y_MIN, max: CURVE_Y_MAX };
  }
  return metaRange;
}

function getExperimentId() {
  const metaId = state.data?.meta?.experimentId;
  if (metaId) return metaId;
  const resultDir = String(state.data?.meta?.sourceResultDir || "");
  const parts = resultDir.replace(/\\/g, "/").split("/").filter(Boolean);
  return parts.length >= 2 ? parts[parts.length - 2] : "Unknown";
}

function getYAxisLabel() {
  return "Normalized fluorescence intensity (a.u.)";
}

function setupCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(rect.width * dpr));
  const height = Math.max(1, Math.round(rect.height * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  return { width, height, dpr };
}

function boundsPadding(bounds) {
  const width = bounds.maxX - bounds.minX;
  const height = bounds.maxY - bounds.minY;
  return {
    x: Math.max(40, width * 0.045),
    y: Math.max(40, height * 0.045),
  };
}

function configureChipTransform() {
  const { canvas } = state.chip;
  const { width, height } = setupCanvas(canvas);
  const bounds = state.data.meta.bounds;
  const padding = boundsPadding(bounds);
  const dataW = bounds.maxX - bounds.minX + padding.x * 2;
  const dataH = bounds.maxY - bounds.minY + padding.y * 2;
  const scale = Math.min(width / dataW, height / dataH);
  const drawW = dataW * scale;
  const drawH = dataH * scale;
  state.chip.scale = scale;
  state.chip.offsetX = (width - drawW) / 2 - (bounds.minX - padding.x) * scale;
  state.chip.offsetY = (height - drawH) / 2 - (bounds.minY - padding.y) * scale;
  state.chip.radius = Math.max(2.1, Math.min(5.2, scale * 5.6));
}

function chipToCanvas(well) {
  return {
    x: well.x * state.chip.scale + state.chip.offsetX,
    y: well.y * state.chip.scale + state.chip.offsetY,
  };
}

function canvasToChip(x, y) {
  return {
    x: (x - state.chip.offsetX) / state.chip.scale,
    y: (y - state.chip.offsetY) / state.chip.scale,
  };
}

function drawChip() {
  if (!state.data) return;
  configureChipTransform();
  const { ctx, canvas, radius } = state.chip;
  drawChipBase();
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(state.chip.baseCanvas, 0, 0);

  const selectedKey = state.selected?.curveKey;
  const hoveredId = state.hovered?.id;
  if (!selectedKey && !hoveredId) return;

  for (const well of state.data.wells) {
    if (well.curveKey !== selectedKey && well.id !== hoveredId) continue;
    const point = chipToCanvas(well);
    ctx.beginPath();
    ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
    ctx.lineWidth = Math.max(2.5, radius * 0.32);
    ctx.strokeStyle = well.curveKey === selectedKey ? COLORS.selected : "rgba(255, 255, 255, 0.95)";
    ctx.stroke();
  }
}

function drawChipBase() {
  const { canvas, radius } = state.chip;
  const base = state.chip.baseCanvas;
  if (
    !state.chip.baseDirty &&
    base.width === canvas.width &&
    base.height === canvas.height
  ) {
    return;
  }
  base.width = canvas.width;
  base.height = canvas.height;
  const ctx = base.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#c8eff9";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  if (
    state.chip.showPhotoBackground &&
    state.chip.photoImage.complete &&
    state.chip.photoImage.naturalWidth > 0 &&
    state.chip.photoImage.naturalHeight > 0
  ) {
    ctx.save();
    ctx.globalAlpha = 0.76;
    ctx.drawImage(
      state.chip.photoImage,
      state.chip.offsetX,
      state.chip.offsetY,
      state.chip.photoImage.naturalWidth * state.chip.scale,
      state.chip.photoImage.naturalHeight * state.chip.scale,
    );
    ctx.restore();
  }

  const selectedKey = state.selected?.curveKey;
  const hoveredId = state.hovered?.id;
  const wellOpacity = state.chip.wellOpacity;

  for (const well of state.data.wells) {
    const point = chipToCanvas(well);
    ctx.beginPath();
    ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);

    if (well.deleted) {
      ctx.globalAlpha = Math.max(0.28, wellOpacity * 0.68);
      ctx.fillStyle = "#fff";
      ctx.fill();
      ctx.globalAlpha = Math.max(0.42, wellOpacity);
      ctx.setLineDash([radius * 0.45, radius * 0.34]);
      ctx.lineWidth = Math.max(1.6, radius * 0.18);
      ctx.strokeStyle = "#111";
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
      continue;
    }

    ctx.globalAlpha = wellOpacity;
    ctx.fillStyle = well.classification === "positive" ? COLORS.positive : COLORS.negative;
    ctx.fill();
    ctx.globalAlpha = 1;

  }
  state.chip.baseDirty = false;
}

function chartArea(canvas, compact = false) {
  const left = 72;
  const right = 18;
  const top = 32;
  const bottom = 46;
  return {
    x: left,
    y: top,
    w: canvas.width - left - right,
    h: canvas.height - top - bottom,
  };
}

function niceTicks(min, max, count = 5) {
  const span = Math.max(1, max - min);
  const raw = span / Math.max(1, count - 1);
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].find((m) => raw <= m * power) * power;
  const first = Math.ceil(min / step) * step;
  const ticks = [];
  for (let value = first; value <= max + step * 0.5; value += step) {
    ticks.push(value);
  }
  return ticks;
}

function drawAxes(ctx, canvas, area, yMin, yMax, title, yLabel, compact = false) {
  ctx.save();
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.strokeStyle = "#111";
  ctx.lineWidth = 2;
  ctx.strokeRect(area.x, area.y, area.w, area.h);

  const cycleMax = getMaxCycle();
  const yTicks = niceTicks(yMin, yMax, 5);
  ctx.font = `700 ${CHART_TICK_FONT_SIZE}px Arial, Helvetica, sans-serif`;
  ctx.fillStyle = "#111";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  ctx.strokeStyle = "rgba(0, 0, 0, 0.09)";
  for (const tick of yTicks) {
    const y = valueToY(tick, yMin, yMax, area);
    ctx.beginPath();
    ctx.moveTo(area.x, y);
    ctx.lineTo(area.x + area.w, y);
    ctx.stroke();
    ctx.fillText(String(Math.round(tick)), area.x - 7, y);
  }

  const xTicks = [0, 10, 20, 30, 40].filter((tick) => tick <= cycleMax);
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  for (const tick of xTicks) {
    const x = cycleToX(tick, cycleMax, area);
    ctx.strokeStyle = "rgba(0, 0, 0, 0.09)";
    ctx.beginPath();
    ctx.moveTo(x, area.y);
    ctx.lineTo(x, area.y + area.h);
    ctx.stroke();
    ctx.fillText(String(tick), x, area.y + area.h + 8);
  }

  if (title) {
    ctx.font = `700 ${CHART_TITLE_FONT_SIZE}px Arial, Helvetica, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillText(title, area.x + area.w / 2, 4);
  }

  ctx.font = `700 ${CHART_AXIS_FONT_SIZE}px Arial, Helvetica, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("PCR cycle number", area.x + area.w / 2, canvas.height - 14);
  ctx.save();
  ctx.translate(17, area.y + area.h / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText(yLabel, 0, 0);
  ctx.restore();
  ctx.restore();
}

function average(values) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function standardDeviation(values, mean) {
  if (values.length <= 1) return 0;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

function estimateCt(curve) {
  const baselineCycles = Math.max(1, Math.min(CT_BASELINE_CYCLES, curve.length));
  const baselineValues = curve.slice(0, baselineCycles);
  const baseline = average(baselineValues);
  const baselineStd = standardDeviation(baselineValues, baseline);
  const peak = Math.max(...curve);
  const endpoint = curve[curve.length - 1];
  const amplitude = peak - baseline;
  const thresholdDelta = Math.max(
    baselineStd * CT_THRESHOLD_SD_MULTIPLIER,
    CT_MIN_THRESHOLD_DELTA,
  );
  const threshold = baseline + thresholdDelta;

  if (amplitude < Math.max(CT_MIN_VALID_AMPLITUDE, thresholdDelta)) {
    return {
      baseline,
      baselineStd,
      peak,
      endpoint,
      amplitude,
      threshold,
      thresholdDelta,
      ct: null,
    };
  }

  let ct = null;
  for (let index = baselineCycles; index < curve.length; index += 1) {
    const previous = curve[index - 1];
    const current = curve[index];
    if (previous < threshold && current >= threshold) {
      const span = current - previous || 1;
      const fraction = (threshold - previous) / span;
      ct = index - 1 + fraction;
      break;
    }
  }
  return { baseline, baselineStd, peak, endpoint, amplitude, threshold, thresholdDelta, ct };
}

function getCtDisplay(well, metrics) {
  if (!well || well.deleted) return "NA";
  if (well.classification === "negative") return "N/A";
  if (well.hidden || well.curveOutlier || well.earlyOutlier) return "Review";
  return formatMetricValue(metrics.ct, 1);
}

function formatMetricValue(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "NA";
  }
  return Number(value).toFixed(digits);
}

function getSelectedCurveColor(well) {
  if (!well) return COLORS.ink;
  if (well.hidden || well.curveOutlier || well.earlyOutlier) {
    return COLORS.abnormalLine;
  }
  return well.classification === "positive" ? COLORS.positiveLine : COLORS.negative;
}

function renderChartMetrics(well, curve) {
  if (!well || well.deleted || !curve) {
    chartMetricsEl.innerHTML = "";
    return;
  }
  const metrics = estimateCt(curve);
  const statusClass = well.hidden || well.curveOutlier || well.earlyOutlier
    ? "status-abnormal"
    : well.classification === "positive"
      ? "status-positive"
      : "status-negative";
  const statusLabel = well.hidden || well.curveOutlier || well.earlyOutlier
    ? "Abnormal"
    : well.classification === "positive"
      ? "Positive"
      : "Negative";
  chartMetricsEl.innerHTML = [
    `<span class="metric-pill ${statusClass}">${statusLabel}</span>`,
    `<span class="metric-pill">Ct ${getCtDisplay(well, metrics)}</span>`,
    `<span class="metric-pill">Threshold ${formatMetricValue(metrics.threshold, 1)}</span>`,
    `<span class="metric-pill">Baseline ${formatMetricValue(metrics.baseline, 1)}</span>`,
    `<span class="metric-pill">Peak ${formatMetricValue(metrics.peak, 1)}</span>`,
    `<span class="metric-pill">Delta ${formatMetricValue(metrics.amplitude, 1)}</span>`,
    `<span class="metric-pill">End ${formatMetricValue(metrics.endpoint, 1)}</span>`,
  ].join("");
}

function getMaxCycle() {
  return Math.max(1, (state.data?.cycles?.length || 1) - 1);
}

function cycleToX(cycle, maxCycle, area) {
  if (maxCycle <= 1) return area.x;
  return area.x + (cycle / maxCycle) * area.w;
}

function valueToY(value, yMin, yMax, area) {
  return area.y + area.h - ((value - yMin) / Math.max(0.001, yMax - yMin)) * area.h;
}

function drawCurvePath(ctx, curve, area, yMin, yMax, color, alpha, width) {
  const cycleMax = getMaxCycle();
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.beginPath();
  for (let index = 0; index < curve.length; index += 1) {
    const x = cycleToX(index, cycleMax, area);
    const y = valueToY(curve[index], yMin, yMax, area);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
  ctx.restore();
}

function shouldDrawCtMarker(well, metrics) {
  return Boolean(
    well &&
    well.classification === "positive" &&
    !well.hidden &&
    !well.curveOutlier &&
    !well.earlyOutlier &&
    metrics?.ct !== null &&
    metrics?.threshold !== null,
  );
}

function drawCtMarker(ctx, canvas, area, yMin, yMax, metrics) {
  const cycleMax = getMaxCycle();
  const x = cycleToX(metrics.ct, cycleMax, area);
  const y = valueToY(metrics.threshold, yMin, yMax, area);
  if (x < area.x || x > area.x + area.w || y < area.y || y > area.y + area.h) return;

  ctx.save();
  ctx.setLineDash([8, 6]);
  ctx.lineWidth = 1.8;
  ctx.strokeStyle = COLORS.ctLine;
  ctx.globalAlpha = 0.92;

  ctx.beginPath();
  ctx.moveTo(area.x, y);
  ctx.lineTo(area.x + area.w, y);
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(x, area.y);
  ctx.lineTo(x, area.y + area.h);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = COLORS.ctLine;
  ctx.beginPath();
  ctx.arc(x, y, 4.8, 0, Math.PI * 2);
  ctx.fill();

  const label = `Ct ${formatMetricValue(metrics.ct, 1)}`;
  ctx.font = "700 12px Arial, Helvetica, sans-serif";
  const labelWidth = ctx.measureText(label).width + 14;
  const labelX = Math.min(Math.max(x + 8, area.x + 4), area.x + area.w - labelWidth - 4);
  const labelY = Math.max(area.y + 8, y - 28);
  ctx.fillStyle = "rgba(255, 255, 255, 0.94)";
  ctx.strokeStyle = "rgba(31, 111, 139, 0.42)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(labelX, labelY, labelWidth, 22, 5);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = COLORS.ctLine;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, labelX + labelWidth / 2, labelY + 11);
  ctx.restore();
}

function drawAllBase() {
  if (!state.data || !state.all.baseDirty) return;
  const visible = state.all.canvas;
  const base = state.all.baseCanvas;
  base.width = visible.width;
  base.height = visible.height;
  const ctx = base.getContext("2d");
  const area = chartArea(base, false);
  const { min, max } = getCurveYRange();

  drawAxes(ctx, base, area, min, max, "RT-dPCR Smoothed Signals", getYAxisLabel(), false);
  ctx.save();
  ctx.rect(area.x, area.y, area.w, area.h);
  ctx.clip();
  for (const [key, curve] of Object.entries(state.data.displayCurves)) {
    const isPositive = key.startsWith("positive:");
    drawCurvePath(
      ctx,
      curve,
      area,
      min,
      max,
      isPositive ? COLORS.positiveLine : COLORS.negativeLine,
      isPositive ? 0.52 : 0.18,
      isPositive ? 1.15 : 0.55,
    );
  }
  ctx.restore();
  state.all.baseDirty = false;
}

function drawAllChart() {
  if (!state.data) return;
  setupCanvas(state.all.canvas);
  if (
    state.all.baseCanvas.width !== state.all.canvas.width ||
    state.all.baseCanvas.height !== state.all.canvas.height
  ) {
    state.all.baseDirty = true;
  }
  drawAllBase();
  const ctx = state.all.ctx;
  ctx.clearRect(0, 0, state.all.canvas.width, state.all.canvas.height);
  ctx.drawImage(state.all.baseCanvas, 0, 0);

  if (!state.selected?.curveKey) return;
  const curve = state.data.displayCurves[state.selected.curveKey] || state.data.singleCurves[state.selected.curveKey];
  if (!curve) return;
  const area = chartArea(state.all.canvas, false);
  const { min, max } = getCurveYRange();
  ctx.save();
  ctx.rect(area.x, area.y, area.w, area.h);
  ctx.clip();
  drawCurvePath(ctx, curve, area, min, max, "#ffffff", 0.92, 6.6);
  drawCurvePath(ctx, curve, area, min, max, COLORS.overviewHighlight, 1, 3.2);
  ctx.restore();
}

function drawSingleChart() {
  if (!state.data) return;
  setupCanvas(state.single.canvas);
  const canvas = state.single.canvas;
  const ctx = state.single.ctx;
  const area = chartArea(canvas, true);

  if (!state.selected || state.selected.deleted) {
    drawSinglePlaceholder(ctx, canvas, area);
    selectedLabelEl.textContent = state.selected?.deleted ? "Removed well" : "Select a well";
    chartMetricsEl.innerHTML = "";
    updateSaveCurveButton();
    return;
  }

  const curve = state.data.singleCurves[state.selected.curveKey];
  if (!curve) {
    drawSinglePlaceholder(ctx, canvas, area);
    selectedLabelEl.textContent = "No curve data";
    chartMetricsEl.innerHTML = "";
    updateSaveCurveButton();
    return;
  }

  const { min: yMin, max: yMax } = getCurveYRange();
  drawAxes(ctx, canvas, area, yMin, yMax, "Single-well RT-dPCR Signal", getYAxisLabel(), true);
  const metrics = estimateCt(curve);
  ctx.save();
  ctx.rect(area.x, area.y, area.w, area.h);
  ctx.clip();
  drawCurvePath(
    ctx,
    curve,
    area,
    yMin,
    yMax,
    getSelectedCurveColor(state.selected),
    1,
    3.4,
  );
  if (shouldDrawCtMarker(state.selected, metrics)) {
    drawCtMarker(ctx, canvas, area, yMin, yMax, metrics);
  }
  ctx.restore();

  const hiddenText = state.selected.hidden ? " | hidden from overview" : "";
  selectedLabelEl.textContent =
    `#${state.selected.id} ${state.selected.classification === "positive" ? "Positive" : "Negative"}` + hiddenText;
  renderChartMetrics(state.selected, curve);
  updateSaveCurveButton();
}

function drawSinglePlaceholder(ctx, canvas, area) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const cx = area.x + area.w / 2;
  const cy = area.y + area.h / 2 - 10;
  const r = Math.min(area.w, area.h) * 0.18;
  ctx.save();
  ctx.strokeStyle = "#7c8a95";
  ctx.fillStyle = "rgba(245, 247, 248, 0.96)";
  ctx.lineWidth = 4;
  ctx.setLineDash([10, 8]);
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(cx - r * 0.62, cy + r * 0.62);
  ctx.lineTo(cx + r * 0.62, cy - r * 0.62);
  ctx.stroke();
  ctx.restore();

  ctx.fillStyle = "#586773";
  ctx.font = "700 18px Arial, Helvetica, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.fillText("Removed well", cx, cy + r + 16);
}

function findNearestWell(event) {
  const rect = state.chip.canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const x = (event.clientX - rect.left) * dpr;
  const y = (event.clientY - rect.top) * dpr;
  const chipPoint = canvasToChip(x, y);
  const hitRadius = Math.max(13 / state.chip.scale, 12);
  let best = null;
  let bestDistance = Infinity;
  for (const well of state.data.wells) {
    const dx = well.x - chipPoint.x;
    const dy = well.y - chipPoint.y;
    const distance = Math.hypot(dx, dy);
    if (distance < bestDistance) {
      best = well;
      bestDistance = distance;
    }
  }
  return bestDistance <= hitRadius ? best : null;
}

function showTip(well, event) {
  if (!well) {
    tipEl.classList.remove("visible");
    return;
  }
  const classText = well.deleted
    ? "Removed"
    : well.classification === "positive"
      ? "Positive"
      : "Negative";
  const detail = well.deleted
    ? `Retention ${well.retentionRatio ?? "-"}`
    : `Raw ${well.rawIntensity}<br>Normalized ${well.normalizedIntensity}${well.classification === "negative" ? "<br>Ct not reported for negative wells" : ""}${well.hidden ? "<br>Curve hidden in overview" : ""}`;
  tipEl.innerHTML = `<strong>#${well.id} ${classText}</strong><br>x ${well.x}, y ${well.y}<br>${detail}`;
  tipEl.style.left = `${event.clientX - state.chip.canvas.getBoundingClientRect().left + 14}px`;
  tipEl.style.top = `${event.clientY - state.chip.canvas.getBoundingClientRect().top + 14}px`;
  tipEl.classList.add("visible");
}

function selectWell(well) {
  if (!well) return;
  state.selected = well;
  if (wellJumpInputEl) {
    wellJumpInputEl.value = String(well.id);
  }
  drawChip();
  drawSingleChart();
  drawAllChart();
}

function updateSaveCurveButton() {
  if (!saveCurveButtonEl) return;
  const hasCurve = Boolean(
    state.selected &&
    !state.selected.deleted &&
    state.selected.curveKey &&
    state.data?.singleCurves?.[state.selected.curveKey],
  );
  saveCurveButtonEl.disabled = !hasCurve;
  saveCurveButtonEl.textContent = hasCurve ? "Save PNG" : "No curve";
}

function findWellById(idText) {
  const normalized = String(idText || "").trim();
  if (!normalized) return null;
  return state.data?.wells?.find((well) => String(well.id) === normalized) || null;
}

function jumpToWellById(event) {
  event.preventDefault();
  const idText = wellJumpInputEl.value.trim();
  const well = findWellById(idText);
  if (!well) {
    wellJumpInputEl.select();
    selectedLabelEl.textContent = idText ? `Well #${idText} not found` : "Enter a well ID";
    chartMetricsEl.innerHTML = "";
    return;
  }
  state.hovered = null;
  tipEl.classList.remove("visible");
  selectWell(well);
}

function sanitizeFilename(value) {
  return String(value).replace(/[\\/:*?"<>|]+/g, "-").replace(/\s+/g, "_");
}

function saveSelectedCurvePng() {
  if (!state.selected || state.selected.deleted) return;
  const curve = state.data.singleCurves[state.selected.curveKey];
  if (!curve) return;

  drawSingleChart();
  const source = state.single.canvas;
  const labelHeight = 46;
  const exportCanvas = document.createElement("canvas");
  exportCanvas.width = source.width;
  exportCanvas.height = source.height + labelHeight;
  const ctx = exportCanvas.getContext("2d");

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, exportCanvas.width, exportCanvas.height);
  ctx.drawImage(source, 0, 0);

  const dpr = window.devicePixelRatio || 1;
  const label = `Experiment ${getExperimentId()} | Well #${state.selected.id} | ${state.selected.classification}`;
  ctx.fillStyle = "rgba(9, 44, 61, 0.95)";
  ctx.fillRect(0, source.height, exportCanvas.width, labelHeight);
  ctx.fillStyle = "#ffffff";
  ctx.font = `700 ${Math.round(15 * dpr)}px Arial, Helvetica, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, exportCanvas.width / 2, source.height + labelHeight / 2);

  const link = document.createElement("a");
  const experiment = sanitizeFilename(getExperimentId());
  const wellId = sanitizeFilename(state.selected.id);
  link.download = `${experiment}_well_${wellId}_single_curve.png`;
  link.href = exportCanvas.toDataURL("image/png");
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function renderStats() {
  const meta = state.data.meta;
  statsEl.innerHTML = [
    `Total ${meta.totalWells}`,
    `Positive ${meta.positiveCount}`,
    `Negative ${meta.negativeCount}`,
    `Removed ${meta.deletedCount}`,
    `Hidden curves ${meta.hiddenCurveCount}`,
  ].map((text) => `<span>${text}</span>`).join("");
}

function toggleEndpointPhoto() {
  state.chip.showPhotoBackground = !state.chip.showPhotoBackground;
  photoToggleEl.textContent = state.chip.showPhotoBackground ? "Hide photo background" : "Show photo background";
  photoToggleEl.setAttribute("aria-expanded", String(state.chip.showPhotoBackground));
  state.chip.baseDirty = true;
  window.requestAnimationFrame(drawChip);
}

function updateWellOpacity() {
  const value = Number(wellOpacityEl.value);
  state.chip.wellOpacity = Math.max(0.15, Math.min(1, value / 100));
  wellOpacityValueEl.value = `${Math.round(state.chip.wellOpacity * 100)}%`;
  state.chip.baseDirty = true;
  window.requestAnimationFrame(drawChip);
}

function pickInitialWell() {
  return state.data.wells.find((well) => well.classification === "positive" && !well.hidden)
    || state.data.wells.find((well) => !well.deleted);
}

function redrawAll() {
  if (!state.data) return;
  state.all.baseDirty = true;
  state.chip.baseDirty = true;
  if (state.selected && wellJumpInputEl) {
    wellJumpInputEl.value = String(state.selected.id);
  }
  experimentBadgeEl.textContent = `Experiment ${getExperimentId()}`;
  overviewFooterEl.textContent = `${getExperimentId()} | ${getYAxisLabel()}`;
  drawChip();
  drawSingleChart();
  drawAllChart();
}

function setActivePage(pageName) {
  const meta = PAGE_META[pageName] || PAGE_META.interactive;
  navItems.forEach((item) => item.classList.toggle("active", item.dataset.page === pageName));
  pages.forEach((page) => page.classList.toggle("active", page.id === `page-${pageName}`));
  pageTitleEl.textContent = meta.title;
  pageSubtitleEl.textContent = meta.subtitle;
  if (pageName === "interactive") {
    window.requestAnimationFrame(redrawAll);
  }
}

function getImageAssets() {
  return state.data?.meta?.imageAssets || {
    resultImages: [],
    sampleImages: [],
    qc: {},
    endpoint: {},
  };
}

function setImageElement(imageEl, item, fallbackText = "Image not available") {
  if (!imageEl) return;
  if (item?.src) {
    imageEl.src = item.src;
    imageEl.alt = item.label || item.fileName || "RT-dPCR image";
    imageEl.dataset.loaded = "true";
  } else {
    imageEl.removeAttribute("src");
    imageEl.alt = fallbackText;
    imageEl.dataset.loaded = "false";
  }
}

function fitResultPreviewImage() {
  if (!resultImagePreviewEl?.src) return;
  const stage = resultImagePreviewEl.closest(".image-stage");
  if (!stage || !resultImagePreviewEl.naturalWidth || !resultImagePreviewEl.naturalHeight) return;
  const padding = 42;
  const availableWidth = Math.max(120, stage.clientWidth - padding);
  const availableHeight = Math.max(120, stage.clientHeight - padding);
  const scale = Math.min(
    availableWidth / resultImagePreviewEl.naturalWidth,
    availableHeight / resultImagePreviewEl.naturalHeight
  );
  const width = Math.floor(resultImagePreviewEl.naturalWidth * scale);
  const height = Math.floor(resultImagePreviewEl.naturalHeight * scale);
  resultImagePreviewEl.style.width = `${width}px`;
  resultImagePreviewEl.style.height = `${height}px`;
}

function makeImageButton(item, index, onSelect) {
  const button = document.createElement("button");
  button.type = "button";
  button.innerHTML = `${item.label || item.fileName || `Image ${index + 1}`}<small>${item.category || "local"} | ${item.fileName || ""}</small>`;
  button.addEventListener("click", () => onSelect(item, button));
  return button;
}

function selectBrowserImage(item, activeButton) {
  if (!item) return;
  setImageElement(resultImagePreviewEl, item);
  resultImagePreviewEl.style.width = "";
  resultImagePreviewEl.style.height = "";
  if (resultImagePreviewEl.complete) {
    window.requestAnimationFrame(fitResultPreviewImage);
  }
  browserEmptyEl.textContent = item.label || item.fileName || "Selected image";
  Array.from(imageCatalogEl.children).forEach((button) => button.classList.toggle("active", button === activeButton));
}

function renderImageBrowser(items) {
  imageCatalogEl.innerHTML = "";
  imageCatalogCountEl.textContent = `${items.length} image${items.length === 1 ? "" : "s"}`;
  if (!items.length) {
    resultImagePreviewEl.removeAttribute("src");
    browserEmptyEl.textContent = "Select local images or regenerate the viewer to import workflow figures.";
    imageCatalogEl.innerHTML = `<div class="placeholder-card">No image catalog is available yet.</div>`;
    return;
  }
  items.forEach((item, index) => {
    imageCatalogEl.appendChild(makeImageButton(item, index, selectBrowserImage));
  });
  selectBrowserImage(items[0], imageCatalogEl.firstElementChild);
}

function renderManifestImageBrowser() {
  const assets = getImageAssets();
  const items = [
    ...(assets.resultImages || []),
    ...(assets.sampleImages || []),
  ];
  renderImageBrowser(items);
}

function loadLocalImages(event) {
  const files = Array.from(event.target.files || []).filter((file) => file.type.startsWith("image/"));
  const items = files.map((file) => ({
    label: file.webkitRelativePath || file.name,
    category: "local",
    fileName: file.name,
    src: URL.createObjectURL(file),
  }));
  renderImageBrowser(items);
}

function renderImageTile(item, label) {
  if (!item?.src) {
    const placeholder = document.createElement("div");
    placeholder.className = "placeholder-card";
    placeholder.textContent = `${label} image was not found in this workflow output.`;
    return placeholder;
  }
  const tile = document.createElement("figure");
  tile.className = "map-tile";
  const image = document.createElement("img");
  image.src = item.src;
  image.alt = item.label || label;
  const caption = document.createElement("span");
  caption.textContent = label;
  tile.append(image, caption);
  return tile;
}

function renderQualityPage() {
  const assets = getImageAssets();
  const qc = assets.qc || {};
  setImageElement(qcBeforeImageEl, qc.beforeCorrection, "Before correction image not available");
  setImageElement(qcAfterImageEl, qc.afterCorrection, "After correction image not available");
  setImageElement(stage1ImageEl, qc.stage1, "Stage 1 image not available");
  setImageElement(stage2ImageEl, qc.stage2, "Stage 2 image not available");

  illuminationMapGridEl.innerHTML = "";
  const maps = qc.illuminationMaps || [];
  if (maps.length) {
    maps.slice(0, 4).forEach((item, index) => {
      illuminationMapGridEl.appendChild(renderImageTile(item, item.label || `Correction map ${index + 1}`));
    });
  } else {
    illuminationMapGridEl.appendChild(renderImageTile(null, "Illumination field / 3D map"));
  }
}

function renderEndpointPage() {
  const assets = getImageAssets();
  const endpoint = assets.endpoint || {};
  setImageElement(endpointMapImageEl, endpoint.map, "Endpoint map not available");
  setImageElement(endpointScatterImageEl, endpoint.scatter, "Endpoint scatter plot not available");

  const meta = state.data.meta;
  const positive = Number(meta.positiveCount || 0);
  const negative = Number(meta.negativeCount || 0);
  const accepted = positive + negative;
  const fraction = accepted > 0 ? positive / accepted : 0;
  const lambda = fraction > 0 && fraction < 1 ? -Math.log(1 - fraction) : null;
  const poissonText = lambda === null
    ? "Poisson occupancy cannot be finite when the accepted partitions are all positive or no accepted partition exists."
    : `Poisson-corrected mean occupancy: ${lambda.toFixed(4)} copies per accepted partition.`;
  endpointSummaryEl.innerHTML = [
    `<div>Accepted partitions: ${accepted}</div>`,
    `<div>Positive partitions: ${positive}</div>`,
    `<div>Positive fraction p: ${accepted ? fraction.toFixed(4) : "NA"}</div>`,
    `<div>${poissonText}</div>`,
  ].join("");
}

function initializeWorkbenchPages() {
  sidebarExperimentEl.textContent = getExperimentId();
  navItems.forEach((item) => {
    item.addEventListener("click", () => setActivePage(item.dataset.page));
  });
  localImageInputEl.addEventListener("change", loadLocalImages);
  renderManifestImageBrowser();
  renderQualityPage();
  renderEndpointPage();
}

async function init() {
  const response = await fetch(`./viewer_data.json?v=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("viewer_data.json not found. Run interactive_chip_viewer.py first.");
  }
  state.data = await response.json();
  renderStats();
  state.selected = pickInitialWell();
  updateWellOpacity();
  initializeWorkbenchPages();
  state.chip.photoImage.addEventListener("load", () => {
    state.chip.baseDirty = true;
    if (state.chip.showPhotoBackground) drawChip();
  });
  redrawAll();

  state.chip.canvas.addEventListener("mousemove", (event) => {
    const well = findNearestWell(event);
    if (well?.id !== state.hovered?.id) {
      state.hovered = well;
      drawChip();
    }
    showTip(well, event);
  });

  state.chip.canvas.addEventListener("mouseleave", () => {
    state.hovered = null;
    tipEl.classList.remove("visible");
    drawChip();
  });

  state.chip.canvas.addEventListener("click", (event) => {
    const well = findNearestWell(event);
    if (well) selectWell(well);
  });

  photoToggleEl.addEventListener("click", toggleEndpointPhoto);
  wellOpacityEl.addEventListener("input", updateWellOpacity);
  wellJumpFormEl.addEventListener("submit", jumpToWellById);
  saveCurveButtonEl.addEventListener("click", saveSelectedCurvePng);
  resultImagePreviewEl.addEventListener("load", fitResultPreviewImage);

  window.addEventListener("resize", () => {
    window.requestAnimationFrame(() => {
      redrawAll();
      fitResultPreviewImage();
    });
  });
}

init().catch((error) => {
  document.body.innerHTML = `<pre style="padding:24px;font:16px/1.5 Consolas,monospace;color:#9b1c1c">${error.message}</pre>`;
});
