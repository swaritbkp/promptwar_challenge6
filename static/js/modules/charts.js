// Native ES Module: CSP-safe SVG visualizations built only with createElementNS,
// geometry attributes and CSS classes (no inline styles, no HTML strings).
// Every value drawn here comes from the backend engine; this module only scales it.

import { $, el, svgEl } from "./dom.js";

/** CPCB NAQI AQI scale (0–500): upper bound of each band, in display order. */
const AQI_BANDS = [[50, "good"], [100, "satisfactory"], [200, "moderate"], [300, "poor"], [400, "very-poor"], [500, "severe"]];
const BAND_NAMES = { good: "Good", satisfactory: "Satisfactory", moderate: "Moderate", poor: "Poor", "very-poor": "Very Poor", severe: "Severe" };
const BAND_NAMES_HI = { good: "अच्छा", satisfactory: "संतोषजनक", moderate: "मध्यम", poor: "खराब", "very-poor": "बहुत खराब", severe: "गंभीर" };
const clamp01 = (v) => Math.min(1, Math.max(0, v));
const round1 = (v) => Math.round(v * 10) / 10;

/** NAQI band class for a 24-h PM2.5 concentration (µg/m³). */
export function pmBand(pm) {
  if (pm <= 30) return "good";
  if (pm <= 60) return "satisfactory";
  if (pm <= 90) return "moderate";
  if (pm <= 120) return "poor";
  if (pm <= 250) return "very-poor";
  return "severe";
}

/** NAQI band class for an AQI value. */
export const aqiBand = (aqi) => (AQI_BANDS.find(([hi]) => aqi <= hi) || AQI_BANDS[5])[1];

const newSvg = (viewBox, label, cls = "custom-viz") => {
  const svg = svgEl("svg", { viewBox, class: cls, role: "img", "aria-label": label, preserveAspectRatio: "xMidYMid meet" });
  const title = svgEl("title");
  title.textContent = label;
  svg.append(title);
  return svg;
};
const text = (x, y, str, cls = "viz-text", anchor = "start") => {
  const node = svgEl("text", { x, y, class: cls, "text-anchor": anchor });
  node.textContent = str;
  return node;
};
const mount = (id, node) => $(id)?.replaceChildren(...(node ? [node] : []));

/**
 * Finds the cleanest daytime waking window (06:00 to 20:00).
 * Single shared helper eliminating duplicate window algorithms across views.
 *
 * @param {number[]} hourlyPm25 - Up to 24 hourly PM2.5 readings.
 * @param {number} windowHours - Window length in hours (default 3).
 * @returns {{ startHour: number, endHour: number, avgPm25: number, label: string }}
 */
export function findCleanestWakingWindow(hourlyPm25 = [], windowHours = 3) {
  if (!hourlyPm25 || hourlyPm25.length === 0) {
    return { startHour: 13, endHour: 16, avgPm25: 120, label: "13:00 – 16:00" };
  }
  const pts = hourlyPm25.slice(0, 24);
  let bestStart = 13;
  let bestAvg = Infinity;
  const maxStart = Math.min(pts.length - windowHours, 17);
  for (let h = 6; h <= maxStart; h++) {
    let sum = 0;
    for (let w = 0; w < windowHours; w++) sum += pts[h + w] || 0;
    const avg = sum / windowHours;
    if (avg < bestAvg) {
      bestAvg = avg;
      bestStart = h;
    }
  }
  const endHour = bestStart + windowHours;
  const hh = (h) => `${String(h).padStart(2, "0")}:00`;
  return { startHour: bestStart, endHour, avgPm25: round1(bestAvg), label: `${hh(bestStart)} – ${hh(endHour)}` };
}

/** Accessible 24-hour PM2.5 bar chart: rounded bars, gridlines, CLEANEST band + pill. */
export function renderPlanHourlyChart(hourlyPm25 = [], isHi = false) {
  const wrap = $("plan-hourly-svg-wrap");
  if (!wrap) return;
  if (!hourlyPm25 || hourlyPm25.length === 0) {
    wrap.replaceChildren(el("div", "stat-lbl text-xs p-1", isHi ? "डेटा लोड हो रहा है..." : "Loading forecast data..."));
    return;
  }
  const pts = hourlyPm25.slice(0, 24);
  const maxPm = Math.max(100, ...pts);
  const base = 92;
  const svg = newSvg("0 0 500 116", isHi ? "24 घंटे का PM2.5 चार्ट" : "24-Hour PM2.5 Hourly Chart");
  [0.25, 0.5, 0.75, 1].forEach((f) => svg.append(svgEl("line", { x1: 4, x2: 496, y1: base - f * 74, y2: base - f * 74, class: "viz-grid" })));
  svg.append(svgEl("line", { x1: 4, x2: 496, y1: base, y2: base, class: "viz-axis" }));

  const win = findCleanestWakingWindow(pts, 3);
  const hlX = win.startHour * 20 + 2;
  const pillLabel = isHi ? "स्वच्छतम" : "CLEANEST";
  svg.append(
    svgEl("rect", { x: hlX, y: 4, width: 60, height: base - 2, rx: 6, class: "viz-clean-band" }),
    svgEl("rect", { x: hlX + 6, y: 6, width: 48, height: 12, rx: 6, class: "viz-clean-pill" }),
    text(hlX + 30, 15, pillLabel, "viz-clean-text", "middle")
  );
  const cleanPill = $("chart-clean-window-pill");
  if (cleanPill) cleanPill.textContent = `▲ ${isHi ? "स्वच्छतम दिन का समय" : "Cleanest Daytime Window"}: ${win.label}`;

  const info = text(250, 113, isHi ? "घंटे पर होवर या टैप करें · PM2.5 और NAQI देखें" : "Hover/tap any hour bar to view PM2.5 and NAQI band", "viz-chart-info", "middle");
  svg.append(info);
  pts.forEach((pm, h) => {
    const barH = Math.max(4, Math.round((pm / maxPm) * 70));
    const band = pmBand(pm);
    const rect = svgEl("rect", { x: h * 20 + 5, y: base - barH, width: 14, height: barH, rx: 3, class: `chart-bar-rect fill-${band}`, tabindex: 0, role: "button", "aria-label": `${h}:00 · ${Math.round(pm)} µg/m³ · ${BAND_NAMES[band]}` });
    const show = () => { info.textContent = `${String(h).padStart(2, "0")}:00 · PM2.5: ${Math.round(pm)} µg/m³ · NAQI: ${BAND_NAMES[band]}`; };
    rect.addEventListener("mouseenter", show);
    rect.addEventListener("focus", show);
    rect.addEventListener("click", show);
    svg.append(rect);
    if (h % 3 === 0) svg.append(text(h * 20 + 12, 102, `${String(h).padStart(2, "0")}h`, "viz-chart-text", "middle"));
  });
  wrap.replaceChildren(svg);
}

/** Today hours strip using the shared cleanest waking window calculation. */
export function renderHoursStrip(points = []) {
  const s = $("hours-strip");
  if (!s) return;
  const pmList = points.map((p) => (typeof p === "number" ? p : p?.pm25_ug_m3 || 0));
  const win = findCleanestWakingWindow(pmList, 3);
  s.replaceChildren(...pmList.slice(0, 24).map((pm, h) => {
    const isClean = h >= win.startHour && h < win.endHour;
    const cell = el("div", `hour-cell ${pmBand(pm)}${isClean ? " highlight" : ""}`, `${h}`);
    cell.setAttribute("title", `${h}:00 · ${Math.round(pm)} µg/m³${isClean ? " (Cleanest Window)" : ""}`);
    return cell;
  }));
}

/** Top multi-day routine slots for the next 4 days. */
export function renderMultiDaySlots(slots = [], exportIcsFn = null) {
  const list = $("multiday-slots-list");
  if (!list) return;
  if (!slots.length) return list.replaceChildren(el("div", "stat-lbl text-xs", "No 4-day slots calculated yet."));
  list.replaceChildren(...slots.map((s) => {
    const row = el("div", "stat-box flex justify-between items-center flex-wrap gap-05 text-left");
    const left = el("div");
    left.append(
      el("div", "font-semibold text-sm", `#${s.rank} ${s.day_label}: ${s.time_label}`),
      el("div", "stat-lbl text-xs", `${s.dispersion_regime} · PM2.5: ${s.outdoor_pm25} µg/m³ · Dose: ${s.dose_ug} µg`),
      el("div", "text-xs text-saved font-semibold mt-05", `▲ Saves ${s.savings_ug} µg (${s.savings_pct}%) vs today smog peak`)
    );
    const btnPlan = el("button", "btn btn-sm btn-primary", "Plan");
    btnPlan.type = "button";
    btnPlan.addEventListener("click", () => {
      btnPlan.textContent = "✓ Set";
      btnPlan.className = "btn btn-sm btn-tonal";
    });
    const btnIcs = el("button", "btn btn-sm btn-tonal", "📅 .ics");
    btnIcs.type = "button";
    if (exportIcsFn) btnIcs.addEventListener("click", () => exportIcsFn(s, btnIcs));
    const btns = el("div", "flex gap-05 items-center");
    btns.append(btnPlan, btnIcs);
    row.append(left, btns);
    return row;
  }));
}

/** 1 · NAQI spectrum gauge: six CPCB bands (0–500) with a live AQI marker pin. */
export function renderNaqiGauge(aqi, isHi = false) {
  if (aqi == null) return;
  const W = 560;
  const L = 10;
  const span = W - 2 * L;
  const band = aqiBand(aqi);
  const svg = newSvg(`0 0 ${W} 52`, isHi
    ? `NAQI स्पेक्ट्रम: AQI ${aqi}, ${BAND_NAMES_HI[band]}`
    : `NAQI spectrum gauge: AQI ${aqi}, ${BAND_NAMES[band]} band`);
  const clip = svgEl("clipPath", { id: "naqi-gauge-clip" });
  clip.append(svgEl("rect", { x: L, y: 18, width: span, height: 12, rx: 6 }));
  const defs = svgEl("defs");
  defs.append(clip);
  svg.append(defs);
  const g = svgEl("g", { "clip-path": "url(#naqi-gauge-clip)" });
  let lo = 0;
  AQI_BANDS.forEach(([hi, cls]) => {
    g.append(svgEl("rect", { x: L + (lo / 500) * span, y: 18, width: ((hi - lo) / 500) * span, height: 12, class: `fill-${cls}` }));
    svg.append(text(L + (hi / 500) * span, 48, String(hi), "viz-text", hi === 500 ? "end" : "middle"));
    lo = hi;
  });
  svg.append(g, text(L, 48, "0", "viz-text"));
  const x = L + clamp01(aqi / 500) * span;
  const tx = Math.min(W - 30, Math.max(30, x));
  svg.append(
    text(tx, 11, `AQI ${aqi}`, "viz-text-strong", "middle"),
    svgEl("circle", { cx: x, cy: 24, r: 9, class: "viz-pin-ring" }),
    svgEl("circle", { cx: x, cy: 24, r: 3.5, class: "viz-pin-core" })
  );
  mount("naqi-gauge-wrap", svg);
}

/** 2 · Atmospheric inversion lid: BLH ceiling height, trapped smog band and wind chevrons. */
export function renderInversionLid(w, isHi = false) {
  const blh = w?.boundary_layer_height_m;
  if (typeof blh !== "number") return;
  const wind = typeof w.wind_speed_kmh === "number" ? w.wind_speed_kmh : 0;
  const ground = 64;
  // sqrt scale spreads the critical 0–600 m range; the lowest lid still clears the rooftops.
  const lidY = 44 - Math.sqrt(Math.min(blh, 1500) / 1500) * 36;
  const level = blh <= 200 ? "" : blh <= 600 ? " mid" : " high";
  const svg = newSvg("0 0 260 72", isHi
    ? `इनवर्ज़न ढक्कन: मिक्सिंग परत ${Math.round(blh)} मीटर, हवा ${round1(wind)} km/h`
    : `Inversion lid: boundary layer ${Math.round(blh)} m, wind ${round1(wind)} km/h`);
  svg.append(
    svgEl("rect", { x: 0, y: 0, width: 260, height: 72, class: "viz-sky" }),
    svgEl("rect", { x: 0, y: lidY, width: 260, height: ground - lidY, class: `viz-smog${level}` })
  );
  // Minimalist skyline: [x, width, height]
  [[8, 14, 10], [24, 10, 14], [36, 18, 8], [56, 12, 17], [70, 20, 11], [92, 10, 7], [104, 16, 15], [122, 22, 9], [146, 12, 12], [160, 18, 16], [180, 14, 8], [196, 20, 13], [218, 12, 10], [232, 20, 14]]
    .forEach(([x, wd, h]) => svg.append(svgEl("rect", { x, y: ground - h, width: wd, height: h, rx: 1.5, class: "viz-skyline" })));
  svg.append(
    svgEl("rect", { x: 0, y: ground, width: 260, height: 8, class: "viz-skyline" }),
    svgEl("path", { d: `M0 ${lidY} H260`, class: `viz-lid${level}` })
  );
  const chevrons = wind < 6 ? 1 : wind < 12 ? 2 : 3;
  for (let i = 0; i < chevrons; i++) {
    const cx = 196 + i * 14;
    const cy = Math.max(10, lidY - 9);
    svg.append(svgEl("path", { d: `M${cx} ${cy - 5} L${cx + 6} ${cy} L${cx} ${cy + 5}`, class: "viz-chevron" }));
  }
  const tagY = lidY > 24 ? lidY - 18 : lidY + 4;
  const tagLabel = `${isHi ? "परत" : "BLH"} ${Math.round(blh)} m`;
  svg.append(
    svgEl("rect", { x: 6, y: tagY, width: 72, height: 14, rx: 7, class: "viz-tag" }),
    text(42, tagY + 10, tagLabel, "viz-text-strong", "middle")
  );
  mount("inversion-lid-wrap", svg);
}

/** Two proportional horizontal bars with labels (shared by the Home Air and mask meters). */
function dualBar({ label, rows, scale, tick }) {
  const W = 640;
  const svg = newSvg(`0 0 ${W} ${tick ? 74 : 62}`, label);
  rows.forEach(([name, value, cls], i) => {
    const y = 6 + i * 28;
    svg.append(
      text(0, y + 6, name, "viz-text-strong"),
      svgEl("rect", { x: 0, y: y + 10, width: W, height: 12, rx: 6, class: "viz-track" }),
      svgEl("rect", { x: 0, y: y + 10, width: Math.max(6, clamp01(value / scale) * W), height: 12, rx: 6, class: cls })
    );
  });
  if (tick) {
    const x = clamp01(tick.value / scale) * (W - 2) + 1;
    svg.append(svgEl("line", { x1: x, x2: x, y1: 14, y2: 62, class: "viz-budget-tick" }), text(Math.min(x, W), 72, tick.label, "viz-text", x > W - 60 ? "end" : "middle"));
  }
  return svg;
}

/** 3a · Home Air: outdoor vs simulated indoor PM2.5 with % reduction cue. */
export function renderIndoorCompare(outPm, inPm, isHi = false) {
  if (outPm == null || inPm == null) return;
  const pct = Math.max(0, Math.round((1 - inPm / Math.max(1, outPm)) * 100));
  const label = isHi
    ? `बाहर PM2.5 ${outPm} बनाम घर के अंदर ${inPm} µg/m³, ${pct}% स्वच्छ`
    : `Outdoor PM2.5 ${outPm} vs simulated indoor ${inPm} µg/m³, ${pct}% cleaner`;
  mount("indoor-compare-wrap", dualBar({
    label,
    scale: Math.max(outPm, inPm, 1),
    rows: [
      [`${isHi ? "बाहर" : "Outdoor"} · ${outPm} µg/m³`, outPm, `fill-${pmBand(outPm)}`],
      [`${isHi ? "घर के अंदर" : "Indoor"} · ${inPm} µg/m³ · ▼ ${pct}%`, inPm, "fill-saved"],
    ],
  }));
  $("indoor-compare-wrap")?.setAttribute("aria-label", label);
}

/** 3b · Plan mask meter: unmasked vs masked trip dose against the WHO daily budget tick. */
export function renderMaskMeter(d, maskLabel, isHi = false) {
  if (!d) return mount("mask-meter-wrap", null);
  const scale = Math.max(d.unmasked_dose_ug, d.budget_ug, 1);
  mount("mask-meter-wrap", dualBar({
    label: isHi
      ? `खुराक: बिना मास्क ${d.unmasked_dose_ug} µg, ${maskLabel} के साथ ${d.masked_dose_ug} µg, WHO बजट ${d.budget_ug} µg`
      : `Dose: unmasked ${d.unmasked_dose_ug} µg, with ${maskLabel} ${d.masked_dose_ug} µg, WHO daily budget ${d.budget_ug} µg`,
    scale,
    rows: [
      [`${isHi ? "बिना मास्क" : "No mask"} · ${d.unmasked_dose_ug} µg`, d.unmasked_dose_ug, "fill-debit"],
      [`${maskLabel} · ${d.masked_dose_ug} µg`, d.masked_dose_ug, "fill-saved"],
    ],
    tick: { value: d.budget_ug, label: `WHO ${d.budget_ug} µg` },
  }));
}

/** 4 · 4-day comparative severity mini-bar, scaled against the 4-day max peak AQI. */
export function severityMiniBar(peak, maxPeak, band, isHi = false) {
  const svg = newSvg("0 0 100 8", isHi ? `शिखर AQI ${peak}, चार दिन के अधिकतम ${maxPeak} की तुलना में` : `Peak AQI ${peak} of 4-day max ${maxPeak}`, "custom-viz mini-bar");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.append(
    svgEl("rect", { x: 0, y: 0, width: 100, height: 8, rx: 4, class: "viz-track" }),
    svgEl("rect", { x: 0, y: 0, width: Math.max(6, clamp01(peak / Math.max(1, maxPeak)) * 100), height: 8, rx: 4, class: `fill-${band}` })
  );
  return svg;
}
