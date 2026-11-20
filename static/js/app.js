// HawaKhata (हवा खाता) - Air Passbook orchestrator (ES module).
// Owns app state, tab switching, language, location/persona changes and data refresh;
// rendering lives in ./modules/*. Every number displayed comes from the backend engine.

import { api } from "./modules/api.js";
import { $, $$, setText, t, catClass } from "./modules/dom.js";
import { renderPlanHourlyChart, renderHoursStrip, renderMultiDaySlots } from "./modules/charts.js";
import { initChatDrawer } from "./modules/chat.js";
import { initSwaps } from "./modules/swaps.js";
import { exportSlotIcs } from "./modules/ics.js";
import {
  renderLiveWeather,
  renderFourDayCards,
  renderSourcePill,
  renderGrap,
  bindGrapToggle,
  renderDayParts,
  renderActionStrip,
  VoiceBrief,
  composeVoiceScript,
} from "./modules/weather.js";
import { updateHero, renderMembers, updatePlanMemberOptions, initPersonas, initLocationModal } from "./modules/passbook.js";
import { bindPlan, updateMaskResult } from "./modules/plan.js";
import { bindIndoor, bindPets } from "./modules/indoor.js";
import { StoryController } from "./story.js";

const TABS = ["today", "plan", "indoor", "swaps"];
const DEFAULT_PROFILE = {
  id: "fam_local",
  name: "Family",
  location: { lat: 28.4595, lng: 77.0266, city_name: "Delhi NCR / Gurugram" },
  rooms: [{ name: "Living Room", volume_m3: 60.0, purifier_cadr_m3_per_h: 300.0, purifier_on_hours: Array.from({ length: 24 }, (_, i) => i), windows_open_hours: [] }],
  sources: [],
  members: [
    { id: "m1", name: "Aarav (Child)", age_band: "child", sensitivities: ["asthma"] },
    { id: "m2", name: "Dadi (Senior)", age_band: "senior", sensitivities: ["cardiovascular"] },
    { id: "m3", name: "Priya (Adult)", age_band: "31_41", sensitivities: [] },
  ],
};

class HawaKhataApp {
  constructor() {
    this.currentTab = "today";
    this.currentLang = "en";
    this.sessionId = null;
    this.i18nStrings = {};
    this.familyProfile = this._loadProfile();
    this.cities = [];
    this.activePersona = null;
    this.currentOutdoorPm25 = null;
    this.currentAQI = null;
    this.currentCategory = null;
    this.currentCategoryLabel = "";
    this.dataMode = "fixture";
    this.cleanestWindow = "—";
    this.currentHourlyPm25 = [];
    this.todaySavings = 0;
    this.fourDayData = null;
    this.maskType = "none";
    this.planStartHour = null;
    this._seq = 0;
    this.story = new StoryController(this);
    this.init();
  }

  get ctx() {
    return { isHi: this.currentLang === "hi", s: this.i18nStrings };
  }

  get city() {
    return this.familyProfile.location?.city_name || "Delhi NCR";
  }

  _loadProfile() {
    try {
      const saved = JSON.parse(localStorage.getItem("hawakhata_family") || "null");
      if (saved?.location && Array.isArray(saved.members) && saved.members.length) return saved;
    } catch {}
    return structuredClone(DEFAULT_PROFILE);
  }

  saveProfile() {
    try {
      localStorage.setItem("hawakhata_family", JSON.stringify(this.familyProfile));
    } catch {}
  }

  async init() {
    this._bindNav();
    this._bindTooltips();
    this._bindModals();
    initLocationModal(this);
    bindPlan(this);
    bindIndoor(this);
    bindPets(this);
    bindGrapToggle();
    this.voice = new VoiceBrief(() => composeVoiceScript(this, this.currentLang === "hi"), () => this.currentLang);
    this.swapsManager = initSwaps({ getLanguage: () => this.currentLang });
    this.chatManager = initChatDrawer({
      getSessionId: () => this.sessionId,
      setSessionId: (id) => { this.sessionId = id; },
      getLanguage: () => this.currentLang,
      getProfile: () => this.familyProfile,
    });

    setText("city-name-label", this.city);
    await this.setLanguage(this.currentLang);
    initPersonas(this);
    await this.refreshData();

    const storyId = new URLSearchParams(window.location.search).get("story");
    if (storyId) this.story.start(storyId);
  }

  _bindTooltips() {
    const closeAll = () => $$(".has-tooltip.active").forEach((n) => n.classList.remove("active"));
    $$(".has-tooltip").forEach((tip) => {
      tip.addEventListener("click", (e) => {
        e.stopPropagation();
        tip.classList.toggle("active");
      });
      tip.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          e.stopPropagation();
          tip.classList.toggle("active");
        } else if (e.key === "Escape") {
          tip.classList.remove("active");
        }
      });
    });
    document.addEventListener("click", closeAll);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeAll(); });
  }

  _bindNav() {
    $$(".nav-item[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => this.switchTab(btn.getAttribute("data-tab")));
    });
    $("lang-toggle-btn")?.addEventListener("click", () => this.setLanguage(this.currentLang === "en" ? "hi" : "en"));
    $("refresh-btn")?.addEventListener("click", () => this.refreshData());
  }

  _bindModals() {
    const why = $("modal-why");
    $("btn-why-number")?.addEventListener("click", () => { if (why) why.hidden = false; });
    $("modal-why-close")?.addEventListener("click", () => { if (why) why.hidden = true; });
    why?.addEventListener("keydown", (e) => { if (e.key === "Escape") why.hidden = true; });

    $("btn-add-member")?.addEventListener("click", async () => {
      const name = $("new-member-name")?.value.trim() || `Member ${this.familyProfile.members.length + 1}`;
      this.familyProfile.members.push({ id: `m_${Date.now()}`, name, age_band: "31_41", sensitivities: [] });
      this.saveProfile();
      await this.recalculatePassbook();
    });

    const copyBtn = $("btn-copy-digest");
    copyBtn?.addEventListener("click", async () => {
      const hi = this.currentLang === "hi";
      try {
        const digest = await api.postDigest(this.familyProfile, this.currentLang);
        await navigator.clipboard?.writeText(digest);
        copyBtn.textContent = hi ? "✓ WhatsApp के लिए कॉपी हुआ!" : "✓ Copied for WhatsApp!";
      } catch {
        copyBtn.textContent = hi ? "कॉपी नहीं हो सका" : "Copy unavailable";
      }
      setTimeout(() => { copyBtn.textContent = hi ? "📋 पासबुक साझा करें" : "📋 Share Passbook"; }, 2500);
    });
  }

  /** Show exactly one tab pane; keep sidebar + bottom nav + story mode in sync. */
  switchTab(tabId) {
    if (!TABS.includes(tabId)) return;
    this.currentTab = tabId;
    $$(".tab-pane").forEach((pane) => { pane.hidden = pane.id !== `tab-${tabId}`; });
    $$(".nav-item[data-tab]").forEach((b) => {
      const on = b.getAttribute("data-tab") === tabId;
      b.classList.toggle("active", on);
      if (on) b.setAttribute("aria-current", "page");
      else b.removeAttribute("aria-current");
    });
    const heading = $(`${tabId}-heading`);
    if (heading) {
      heading.setAttribute("tabindex", "-1");
      heading.focus({ preventScroll: true });
    }
    window.scrollTo({ top: 0 });
  }

  async setLanguage(lang) {
    this.currentLang = lang;
    try {
      this.i18nStrings = await api.fetchI18n(lang);
      $$("[data-i18n]").forEach((node) => {
        const v = this.i18nStrings[node.getAttribute("data-i18n")];
        if (v) node.textContent = v;
      });
      $$("[data-i18n-placeholder]").forEach((node) => {
        const v = this.i18nStrings[node.getAttribute("data-i18n-placeholder")];
        if (v) node.setAttribute("placeholder", v);
      });
    } catch {}
    setText("lang-label", lang === "en" ? "हिन्दी" : "English");
    $("lang-toggle-btn")?.setAttribute("aria-label", lang === "en" ? "Switch language to Hindi" : "Switch language to English");
    document.documentElement.lang = lang;
    this.voice?.stop();
    this.renderPersonas?.();
    this.renderAll();
    this.swapsManager?.update();
  }

  /** Re-render every data-driven view from current state (used after language switch). */
  renderAll() {
    this.renderLiveAQ();
    this.updateDataModeBadge();
    if (this.passbookData) {
      updateHero(this.passbookData, this);
      renderMembers(this.passbookData.entries || [], this);
    }
    if (this.fourDayData) this.renderForecast();
  }

  nearestCity(lat, lng) {
    let best = null;
    let bestD = Infinity;
    this.cities.forEach((c) => {
      const d = Math.hypot(lat - c.lat, lng - c.lng);
      if (d < bestD) { bestD = d; best = c; }
    });
    return best;
  }

  async refreshData() {
    setText("refresh-time-label", new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    if (!this.cities.length) {
      try {
        const meta = await api.fetchMeta();
        this.cities = meta.cities || [];
        this.renderCityChips?.(this.cities);
      } catch {}
    }
    await Promise.all([this.fetchFourDayForecast(), this.recalculatePassbook()]);
    this.refreshIndoor?.();
    updateMaskResult(this);
  }

  updateDataModeBadge() {
    const badge = $("data-mode-badge");
    if (!badge) return;
    const live = this.dataMode !== "fixture";
    badge.textContent = live ? t(this.i18nStrings, "live_aq", "Live AQ") : t(this.i18nStrings, "demo_mode", "Offline");
    badge.className = `pill-status text-xs ${live ? "saved" : "warn"}`;
  }

  updateLiveAQ(d) {
    if (d?.current_pm25 == null) return;
    this.currentOutdoorPm25 = Math.round(d.current_pm25);
    this.currentAQI = Math.round(d.current_aqi);
    this.currentCategory = d.current_category;
    this.currentCategoryLabel = d.current_category_label;
    this.dataMode = d.data_mode || "fixture";
    this.renderLiveAQ();
    this.updateDataModeBadge();
    renderSourcePill(d, this.ctx);
    if (d.grap) renderGrap(d.grap, this.ctx);
  }

  renderLiveAQ() {
    if (this.currentAQI == null) return;
    const cls = catClass(this.currentCategory);
    setText("top-aqi-val", String(this.currentAQI));
    setText("top-aqi-cat", this.ctx.isHi ? t(this.i18nStrings, `cat_${this.currentCategory}`, this.currentCategoryLabel) : this.currentCategoryLabel);
    const chip = $("top-aqi-chip");
    if (chip) {
      chip.className = `chip-aqi ${cls}`;
      chip.setAttribute("aria-label", `Air Quality: AQI ${this.currentAQI}, ${this.currentCategoryLabel}`);
      chip.querySelector("use")?.setAttribute("href", `#icon-naqi-${cls}`);
    }
    setText("indoor-outdoor-val", `${this.currentOutdoorPm25} µg/m³`);
    renderActionStrip(this.currentOutdoorPm25, this.currentAQI, this.fourDayData?.safe_house_flush, this.ctx);
  }

  exportSlotIcs(slot, btn = null) {
    exportSlotIcs(slot, btn, this.city, this.currentLang === "hi");
  }

  /** Single forecast call: 4-day outlook, clock-aligned 24h series, weather, live AQ, GRAP. */
  async fetchFourDayForecast(activity = $("plan-activity-type")?.value || "walk", durationMin = parseInt($("plan-duration")?.value || "60", 10)) {
    const seq = ++this._seq;
    const loc = this.familyProfile.location;
    const mem = this.familyProfile.members.find((m) => m.id === $("plan-member-select")?.value) || this.familyProfile.members[0];
    try {
      const d = await api.fetchFourDayForecast({ lat: loc.lat, lng: loc.lng, city: this.city, activity, durationMin, ageBand: mem?.age_band || "31_41" });
      if (seq !== this._seq) return; // a newer city/persona request superseded this one
      this.fourDayData = d;
      this.renderForecast();
    } catch {
      if (seq === this._seq) setText("tomorrow-watch-text", this.ctx.isHi ? "पूर्वानुमान अभी उपलब्ध नहीं" : "Forecast temporarily unavailable — retry with ⟳");
    }
  }

  renderForecast() {
    const d = this.fourDayData;
    const ctx = this.ctx;
    renderLiveWeather(d.current_weather, ctx);
    this.updateLiveAQ(d);
    renderFourDayCards(d.days, ctx);
    renderDayParts(d.day_parts, ctx, "day-parts-today");
    renderDayParts(d.day_parts, ctx, "day-parts-plan");

    setText("tomorrow-watch-text", d.tomorrow_watch_headline || "");
    const tw = $("tomorrow-watch-badge");
    if (tw && d.tomorrow_watch_direction) {
      const dir = d.tomorrow_watch_direction;
      tw.textContent = dir === "worsens" ? (ctx.isHi ? "▲ बिगड़ेगा" : "▲ Worsens") : dir === "improves" ? (ctx.isHi ? "▼ सुधरेगा" : "▼ Improves") : (ctx.isHi ? "● स्थिर" : "● Stable");
      tw.className = `pill-status ${dir === "worsens" ? "debit" : dir === "improves" ? "saved" : ""}`;
    }

    const today = d.days?.[0];
    if (today) {
      this.cleanestWindow = `${today.cleanest_window_start} – ${today.cleanest_window_end}`;
      setText("clean-window-tag", `▲ ${ctx.isHi ? "स्वच्छतम" : "Cleanest"}: ${this.cleanestWindow}`);
      setText("brief-recommendation", `${ctx.isHi ? "सबसे स्वच्छ समय" : "Cleanest window"}: ${this.cleanestWindow} (${Math.round(today.cleanest_pm25)} µg/m³).`);
    }
    const flush = d.safe_house_flush;
    if (flush) {
      setText("safe-flush-time", `${flush.day_label} ${flush.start_hour}–${flush.end_hour}`);
      setText("safe-flush-pm", `(${flush.outdoor_pm25} µg/m³)`);
    }
    renderMultiDaySlots(d.top_slots || [], (slot, btn) => this.exportSlotIcs(slot, btn));
    this.currentHourlyPm25 = Array.isArray(d.hourly_pm25_24h) ? d.hourly_pm25_24h : [];
    renderPlanHourlyChart(this.currentHourlyPm25, ctx.isHi, this.i18nStrings);
    renderHoursStrip(this.currentHourlyPm25, ctx.isHi);
  }

  async recalculatePassbook() {
    const seq = this._seq;
    try {
      const d = await api.postPassbook(this.familyProfile);
      if (seq !== this._seq) return;
      this.passbookData = d;
      updateHero(d, this);
      renderMembers(d.entries || [], this);
      updatePlanMemberOptions(this);
      if (!this.fourDayData) this.updateLiveAQ(d);
    } catch {
      renderMembers([], this);
    }
  }

  /** Switch city: every view (passbook, 4-day, weather, strip, chart, Home Air) refreshes together. */
  applyLocation(name, lat, lng) {
    this.familyProfile.location = { lat, lng, city_name: name };
    this.saveProfile();
    setText("city-name-label", name);
    this.closeLocationModal?.();
    return this.refreshData();
  }

  /** Quick Scenario persona: city + household + plan defaults in one click. */
  async applyPersona(p) {
    this.activePersona = p.id;
    this.familyProfile = { ...this.familyProfile, location: { ...p.location }, members: p.members.map((m) => ({ ...m })) };
    this.saveProfile();
    setText("city-name-label", p.location.city_name);
    updatePlanMemberOptions(this, p.plan?.member_id);
    if (p.plan) {
      const act = $("plan-activity-type");
      const dur = $("plan-duration");
      if (act) act.value = p.plan.activity;
      if (dur) dur.value = String(p.plan.duration_min);
    }
    this.planStartHour = null;
    await this.refreshData();
  }
}

const app = new HawaKhataApp();
window.hawakhataApp = app;
export default app;
