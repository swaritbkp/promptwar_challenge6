// Native ES Module: Plan tab — clean-window shift, Today/4-day horizon tabs,
// mask filtration toggle (None / Surgical / N95) and .ics export.

import { api } from "./api.js";
import { $, $$, el, setText } from "./dom.js";
import { renderMaskMeter } from "./charts.js";

const ACTIVITIES = {
  pet_walk: { title: "Dog / Pet Walk", micro_env: "outdoor", activity: "pet_walk", usual: 7 },
  market_shopping: { title: "Market / Shopping", micro_env: "outdoor", activity: "market_shopping", usual: 10 },
  school_run: { title: "School Run", micro_env: "transit_auto", activity: "school_run", usual: 7 },
  park_terrace: { title: "Park / Terrace Time", micro_env: "park_terrace", activity: "park_terrace", usual: 17 },
  transit_auto: { title: "Auto / Bike Commute", micro_env: "transit_auto", activity: "light", usual: 9 },
  walk: { title: "Walk", micro_env: "outdoor", activity: "walk", usual: 7 },
  run: { title: "Run", micro_env: "outdoor", activity: "run", usual: 7 },
};

const selectedMember = (app) => {
  const mid = $("plan-member-select")?.value;
  return app.familyProfile.members.find((m) => m.id === mid) || app.familyProfile.members[0];
};

/** Recalculate the outdoor-trip dose for the selected mask via the deterministic engine. */
export async function updateMaskResult(app) {
  const box = $("mask-result");
  if (!box) return;
  const hi = app.currentLang === "hi";
  const mem = selectedMember(app);
  const actType = $("plan-activity-type")?.value || "walk";
  const cfg = ACTIVITIES[actType] || ACTIVITIES.walk;
  const dur = parseInt($("plan-duration")?.value || "60", 10);
  const start = app.planStartHour ?? cfg.usual;
  try {
    const d = await api.postMaskedActivity({
      location: app.familyProfile.location,
      ageBand: mem?.age_band || "31_41",
      activity: cfg.activity,
      durationMin: dur,
      startHour: start,
      mask: app.maskType,
    });
    const hh = `${String(start).padStart(2, "0")}:00`;
    const name = mem?.name || "";
    const verdict = d.within_budget
      ? (hi ? `✓ ${name} के WHO दैनिक बजट के भीतर` : `✓ Within ${name}'s WHO daily budget`)
      : (hi ? `✕ ${name} के WHO दैनिक बजट से अधिक` : `✕ Exceeds ${name}'s WHO daily budget`);
    box.replaceChildren(
      el("div", "font-semibold text-sm", hi
        ? `${hh} पर ${dur} मिनट: ${d.masked_dose_ug} µg साँस में (बिना मास्क ${d.unmasked_dose_ug} µg)`
        : `${dur} min at ${hh}: ${d.masked_dose_ug} µg inhaled (no mask: ${d.unmasked_dose_ug} µg)`),
      el("div", "text-xs text-saved font-semibold", hi
        ? `▲ मास्क से बचत ${d.mask_saved_ug} µg · बाहरी PM2.5 ${d.mean_outdoor_pm25} µg/m³`
        : `▲ Mask saves ${d.mask_saved_ug} µg · outdoor PM2.5 ${d.mean_outdoor_pm25} µg/m³`),
      el("div", `text-xs font-semibold ${d.within_budget ? "text-saved" : "text-debit"}`,
        `${verdict} (${d.budget_share_pct}% ${hi ? "का" : "of"} ${d.budget_ug} µg)`)
    );
    const maskBtn = document.querySelector(`.mask-btn[data-mask="${app.maskType}"]`);
    renderMaskMeter(d, app.maskType === "none" ? (hi ? "बिना मास्क" : "No mask") : (maskBtn?.textContent || app.maskType), hi);
  } catch {
    box.replaceChildren(el("div", "stat-lbl text-xs", hi ? "मास्क गणना उपलब्ध नहीं" : "Mask calculation unavailable"));
    renderMaskMeter(null);
  }
}

export function bindPlan(app) {
  // Horizon tabs: "Today Only" shows the 24h chart view; "Best Slot in Next 4 Days" swaps it for
  // the 4-day slot list (rendered directly under the toggles, so it sits above the fold).
  const tabToday = $("btn-plan-today");
  const tabMulti = $("btn-plan-multiday");
  const setHorizon = (multi) => {
    tabToday?.setAttribute("aria-selected", String(!multi));
    tabMulti?.setAttribute("aria-selected", String(multi));
    tabToday?.setAttribute("tabindex", multi ? "-1" : "0");
    tabMulti?.setAttribute("tabindex", multi ? "0" : "-1");
    const single = $("plan-today-view");
    const many = $("multiday-slots-container");
    if (single) single.hidden = multi;
    if (many) many.hidden = !multi;
  };
  tabToday?.addEventListener("click", () => setHorizon(false));
  tabMulti?.addEventListener("click", () => setHorizon(true));
  [tabToday, tabMulti].forEach((tab) => tab?.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const multi = tab === tabToday;
    setHorizon(multi);
    (multi ? tabMulti : tabToday)?.focus();
  }));
  setHorizon(false);

  // Mask selector (aria-pressed toggle group)
  $$(".mask-btn").forEach((b) => {
    b.addEventListener("click", () => {
      app.maskType = b.getAttribute("data-mask") || "none";
      $$(".mask-btn").forEach((x) => {
        const on = x === b;
        x.setAttribute("aria-pressed", String(on));
      });
      updateMaskResult(app);
    });
  });
  ["plan-member-select", "plan-activity-type", "plan-duration"].forEach((id) =>
    $(id)?.addEventListener("change", () => {
      app.planStartHour = null;
      updateMaskResult(app);
    })
  );

  $("btn-run-plan")?.addEventListener("click", async () => {
    const mem = selectedMember(app);
    const dur = parseInt($("plan-duration")?.value || "60", 10);
    const actType = $("plan-activity-type")?.value || "walk";
    const cfg = ACTIVITIES[actType] || ACTIVITIES.walk;
    const hi = app.currentLang === "hi";
    await app.fetchFourDayForecast(actType, dur);
    try {
      const res = await api.postPlan({
        profile: app.familyProfile,
        memberId: mem?.id,
        flexibleActivities: [{
          id: `act_${actType}`,
          member_id: mem?.id,
          title: cfg.title,
          duration_hours: Math.max(1, Math.round(dur / 60)),
          earliest_start_hour: 6,
          latest_start_hour: 19,
          micro_env: cfg.micro_env,
          activity: cfg.activity,
          usual_start_hour: cfg.usual,
        }],
      });
      const shift = (res.shifts || [])[0];
      app.todaySavings = res.total_savings_ug || 0;
      setText("plan-savings-pill", `▲ ${hi ? "बचत" : "Saves"} ${Math.round(app.todaySavings)} µg`);
      if (shift) {
        app.planStartHour = shift.optimized_start_hour;
        const pm = shift.outdoor_pm25_at_optimized ? ` (${Math.round(shift.outdoor_pm25_at_optimized)} µg/m³)` : "";
        setText("plan-shift-title", `${cfg.title} · ${mem?.name || ""}`);
        setText("plan-shift-hours", `${String(shift.usual_start_hour).padStart(2, "0")}:00 → ${String(shift.optimized_start_hour).padStart(2, "0")}:00${pm}`);
        setText("plan-shift-delta", `▲ ${hi ? "बचत" : "Saves"} ${Math.round(shift.savings_ug)} µg (${Math.round(shift.percent_savings || 0)}%)`);
      }
    } catch {
      setText("plan-shift-delta", hi ? "योजना उपलब्ध नहीं" : "Plan unavailable");
    }
    updateMaskResult(app);
  });

  const exportToday = (btn) => {
    const start = app.planStartHour ?? 13;
    app.exportSlotIcs({
      day_index: 0,
      day_label: "Today",
      time_label: `${String(start).padStart(2, "0")}:00`,
      start_hour: start,
      end_hour: start + 1,
      outdoor_pm25: app.currentOutdoorPm25,
      savings_ug: app.todaySavings || 0,
    }, btn);
  };
  $("btn-export-ics")?.addEventListener("click", (e) => exportToday(e.currentTarget));
  $("btn-export-ics-multiday")?.addEventListener("click", (e) => {
    const top = app.fourDayData?.top_slots?.[0];
    if (top) app.exportSlotIcs(top, e.currentTarget);
  });
}
