// Native ES Module: Chart visualizations and hourly air dispersion displays

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
};

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
    for (let w = 0; w < windowHours; w++) {
      sum += pts[h + w] || 0;
    }
    const avg = sum / windowHours;
    if (avg < bestAvg) {
      bestAvg = avg;
      bestStart = h;
    }
  }
  const endHour = bestStart + windowHours;
  const startStr = `${String(bestStart).padStart(2, "0")}:00`;
  const endStr = `${String(endHour).padStart(2, "0")}:00`;
  return {
    startHour: bestStart,
    endHour,
    avgPm25: Math.round(bestAvg * 10) / 10,
    label: `${startStr} – ${endStr}`,
  };
}

/**
 * Renders the accessible 24-hour PM2.5 SVG bar chart with cleanest window overlay.
 */
export function renderPlanHourlyChart(hourlyPm25 = [], isHi = false, i18nStrings = {}) {
  const wrap = $("plan-hourly-svg-wrap");
  if (!wrap) return;
  wrap.replaceChildren();

  if (!hourlyPm25 || hourlyPm25.length === 0) {
    const emptyMsg = el("div", "stat-lbl text-xs p-1", isHi ? "डेटा लोड हो रहा है..." : "Loading forecast data...");
    wrap.appendChild(emptyMsg);
    return;
  }

  const pts = hourlyPm25.slice(0, 24);
  const maxPm = Math.max(100, ...pts);

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 500 120");
  svg.setAttribute("class", "custom-viz");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "24-Hour PM2.5 Hourly Chart");

  const cleanWin = findCleanestWakingWindow(pts, 3);
  const winWidth = 60;
  const hlX = cleanWin.startHour * 20 + 2;

  const hlRect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  hlRect.setAttribute("x", `${hlX}`);
  hlRect.setAttribute("y", "6");
  hlRect.setAttribute("width", `${winWidth}`);
  hlRect.setAttribute("height", "96");
  hlRect.setAttribute("rx", "4");
  hlRect.setAttribute("fill", "#0F6E66");
  hlRect.setAttribute("fill-opacity", "0.12");
  hlRect.setAttribute("stroke", "#0F6E66");
  hlRect.setAttribute("stroke-width", "1");
  hlRect.setAttribute("stroke-dasharray", "3 2");
  svg.appendChild(hlRect);

  const hlText = document.createElementNS("http://www.w3.org/2000/svg", "text");
  hlText.setAttribute("x", `${hlX + winWidth / 2}`);
  hlText.setAttribute("y", "16");
  hlText.setAttribute("fill", "#0F6E66");
  hlText.setAttribute("font-size", "8");
  hlText.setAttribute("font-weight", "700");
  hlText.setAttribute("text-anchor", "middle");
  hlText.textContent = isHi ? "स्वच्छ समय" : "CLEANEST";
  svg.appendChild(hlText);

  const cleanPill = $("chart-clean-window-pill");
  if (cleanPill) {
    cleanPill.textContent = `▲ ${isHi ? "स्वच्छतम दिन का समय" : "Cleanest Daytime Window"}: ${cleanWin.label}`;
  }

  // Baseline axis
  const axis = document.createElementNS("http://www.w3.org/2000/svg", "line");
  axis.setAttribute("x1", "10");
  axis.setAttribute("y1", "95");
  axis.setAttribute("x2", "490");
  axis.setAttribute("y2", "95");
  axis.setAttribute("stroke", "var(--line, #cbd5e1)");
  axis.setAttribute("stroke-width", "1");
  svg.appendChild(axis);

  // Dynamic status text updated on hover/focus
  const infoText = document.createElementNS("http://www.w3.org/2000/svg", "text");
  infoText.setAttribute("x", "250");
  infoText.setAttribute("y", "116");
  infoText.setAttribute("fill", "var(--ink, #1e293b)");
  infoText.setAttribute("font-size", "9");
  infoText.setAttribute("font-weight", "600");
  infoText.setAttribute("text-anchor", "middle");
  infoText.textContent = isHi
    ? "घंटे पर होवर या टैप करें · PM2.5 और NAQI देखें"
    : "Hover/tap any hour bar to view PM2.5 and NAQI band";
  svg.appendChild(infoText);

  pts.forEach((pm, h) => {
    const barH = Math.max(4, Math.round((pm / maxPm) * 70));
    const barY = 95 - barH;
    const barX = h * 20 + 5;

    let color = "#6A1B4D";
    let catName = "Severe";
    if (pm <= 30) { color = "#2E7D32"; catName = "Good"; }
    else if (pm <= 60) { color = "#7CB342"; catName = "Satisfactory"; }
    else if (pm <= 90) { color = "#C9A400"; catName = "Moderate"; }
    else if (pm <= 120) { color = "#E07B00"; catName = "Poor"; }
    else if (pm <= 250) { color = "#C62828"; catName = "Very Poor"; }

    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", String(barX));
    rect.setAttribute("y", String(barY));
    rect.setAttribute("width", "14");
    rect.setAttribute("height", String(barH));
    rect.setAttribute("rx", "2");
    rect.setAttribute("fill", color);
    rect.setAttribute("class", "chart-bar-rect");
    rect.setAttribute("tabindex", "0");
    rect.setAttribute("role", "button");
    rect.setAttribute("aria-label", `${h}:00 · ${Math.round(pm)} µg/m³ · ${catName}`);

    const showHour = () => {
      infoText.textContent = `${String(h).padStart(2, "0")}:00 · PM2.5: ${Math.round(pm)} µg/m³ · NAQI: ${catName}`;
    };
    rect.addEventListener("mouseenter", showHour);
    rect.addEventListener("focus", showHour);
    rect.addEventListener("click", showHour);

    svg.appendChild(rect);

    if (h % 3 === 0) {
      const tick = document.createElementNS("http://www.w3.org/2000/svg", "text");
      tick.setAttribute("x", String(barX + 7));
      tick.setAttribute("y", "105");
      tick.setAttribute("fill", "var(--text-muted, #64748b)");
      tick.setAttribute("font-size", "7");
      tick.setAttribute("text-anchor", "middle");
      tick.textContent = `${String(h).padStart(2, "0")}h`;
      svg.appendChild(tick);
    }
  });

  wrap.appendChild(svg);
}

/**
 * Renders the Today hours strip using the shared cleanest waking window calculation.
 */
export function renderHoursStrip(points = [], isHi = false) {
  const s = $("hours-strip");
  if (!s) return;
  s.replaceChildren();

  const pmList = points.map((p) => (typeof p === "number" ? p : p?.pm25_ug_m3 || 0));
  const cleanWin = findCleanestWakingWindow(pmList, 3);

  points.slice(0, 24).forEach((pt, h) => {
    const pm = typeof pt === "number" ? pt : (pt?.pm25_ug_m3 || 0);
    let cat = "severe";
    if (pm <= 30) cat = "good";
    else if (pm <= 60) cat = "satisfactory";
    else if (pm <= 90) cat = "moderate";
    else if (pm <= 120) cat = "poor";
    else if (pm <= 250) cat = "very-poor";

    const isClean = h >= cleanWin.startHour && h < cleanWin.endHour;
    const cell = el("div", `hour-cell ${cat}${isClean ? " highlight" : ""}`, `${h}`);
    cell.setAttribute("title", `${h}:00 · ${Math.round(pm)} µg/m³${isClean ? " (Cleanest Window)" : ""}`);
    s.appendChild(cell);
  });
}

/**
 * Renders the top multi-day routine slots for the next 4 days.
 */
export function renderMultiDaySlots(slots = [], exportIcsFn = null) {
  const list = $("multiday-slots-list");
  if (!list) return;
  list.replaceChildren();

  if (!slots.length) {
    return list.append(el("div", "stat-lbl text-xs", "No 4-day slots calculated yet."));
  }

  slots.forEach((s) => {
    const row = el("div", "stat-box flex justify-between items-center text-left");
    const left = el("div");
    const btns = el("div", "flex gap-05 items-center");

    left.append(
      el("div", "font-semibold text-sm", `#${s.rank} ${s.day_label}: ${s.time_label}`),
      el("div", "stat-lbl text-xs", `${s.dispersion_regime} · PM2.5: ${s.outdoor_pm25} µg/m³ · Dose: ${s.dose_ug} µg`),
      el("div", "text-xs text-saved font-semibold mt-05", `▲ Saves ${s.savings_ug} µg (${s.savings_pct}%) vs today smog peak`)
    );

    const btnPlan = el("button", "btn btn-sm btn-primary", "Plan");
    btnPlan.addEventListener("click", () => {
      btnPlan.textContent = "✓ Set";
      btnPlan.className = "btn btn-sm btn-secondary";
    });

    const btnIcs = el("button", "btn btn-sm btn-secondary", "📅 .ics");
    if (exportIcsFn) {
      btnIcs.addEventListener("click", () => exportIcsFn(s, btnIcs));
    }

    btns.append(btnPlan, btnIcs);
    row.append(left, btns);
    list.append(row);
  });
}
