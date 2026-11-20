// HawaKhata (हवा खाता) - Air Passbook Orchestrator (ES Module)
// Clean orchestrator wiring modules, single forecast fetch, live weather, and reactive UI state

import { api } from "./modules/api.js";
import {
  findCleanestWakingWindow,
  renderPlanHourlyChart,
  renderHoursStrip,
  renderMultiDaySlots,
} from "./modules/charts.js";
import { initChatDrawer } from "./modules/chat.js";
import { initSwaps } from "./modules/swaps.js";
import { exportSlotIcs } from "./modules/ics.js";
import { StoryController } from "./story.js";

const $ = (id) => document.getElementById(id);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
};

const CITIES = [
  { id: "delhi_ncr", name: "Delhi NCR / Gurugram", lat: 28.4595, lng: 77.0266 },
  { id: "chandigarh", name: "Chandigarh / Mohali", lat: 30.7333, lng: 76.7794 },
  { id: "mumbai", name: "Mumbai", lat: 19.0760, lng: 72.8777 },
  { id: "bengaluru", name: "Bengaluru", lat: 12.9716, lng: 77.5946 },
  { id: "kolkata", name: "Kolkata", lat: 22.5726, lng: 88.3639 },
  { id: "chennai", name: "Chennai", lat: 13.0827, lng: 80.2707 },
  { id: "hyderabad", name: "Hyderabad", lat: 17.3850, lng: 78.4867 },
  { id: "pune", name: "Pune", lat: 18.5204, lng: 73.8567 },
  { id: "jaipur", name: "Jaipur", lat: 26.9124, lng: 75.7873 },
  { id: "lucknow", name: "Lucknow", lat: 26.8467, lng: 80.9462 },
];

function findClosestCity(lat, lng) {
  let closest = CITIES[0];
  let minD = Infinity;
  for (const c of CITIES) {
    const d = Math.hypot(lat - c.lat, lng - c.lng);
    if (d < minD) {
      minD = d;
      closest = c;
    }
  }
  return closest;
}

class HawaKhataApp {
  constructor() {
    this.currentTab = "today";
    this.currentLang = "en";
    this.sessionId = null;
    this.i18nStrings = {};
    this.familyProfile = this._loadProfile();
    this.story = new StoryController(this);
    this.airSeries = null;
    this.currentOutdoorPm25 = 317;
    this.currentAQI = 317;
    this.currentCategory = "very_poor";
    this.currentCategoryLabel = "Very Poor";
    this.dataMode = "fixture";
    this.cleanestWindow = "12:00 – 15:00";
    this.currentHourlyPm25 = [];
    this.todaySavings = 340;
    this.fourDayData = null;
    this.swapsManager = null;
    this.chatManager = null;
    this.init();
  }

  _loadProfile() {
    try {
      const s = localStorage.getItem("hawakhata_family");
      if (s) return JSON.parse(s);
    } catch {}
    return {
      id: "fam_local",
      name: "Family",
      location: { lat: 28.4595, lng: 77.0266, city_name: "Delhi NCR / Gurugram" },
      rooms: [
        {
          name: "Living Room",
          volume_m3: 60.0,
          purifier_cadr_m3_per_h: 300.0,
          purifier_on_hours: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23],
          windows_open_hours: [],
        },
      ],
      sources: [],
      members: [
        { id: "m1", name: "Aarav (Child)", age_band: "child", sensitivities: ["asthma"] },
        { id: "m2", name: "Dadi (Elder)", age_band: "senior", sensitivities: ["cardiovascular"] },
        { id: "m3", name: "Priya (Adult)", age_band: "31_41", sensitivities: [] },
      ],
    };
  }

  _saveProfile() {
    try {
      localStorage.setItem("hawakhata_family", JSON.stringify(this.familyProfile));
    } catch {}
  }

  async init() {
    this._bindNav();
    this._bindModals();
    this._bindPlan();
    this._bindIndoor();
    this._bindTodayActions();
    this._bindTooltips();

    this.swapsManager = initSwaps({ getLanguage: () => this.currentLang });
    this.chatManager = initChatDrawer({
      getSessionId: () => this.sessionId,
      setSessionId: (id) => { this.sessionId = id; },
      getLanguage: () => this.currentLang,
      getProfile: () => this.familyProfile,
    });

    await this.setLanguage(this.currentLang);
    await this.refreshData();

    const sId = new URLSearchParams(window.location.search).get("story");
    if (sId) this.story.start(sId);
  }

  _bindTooltips() {
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
          e.stopPropagation();
          tip.classList.remove("active");
        }
      });
    });
    document.addEventListener("click", () => {
      $$(".has-tooltip.active").forEach((t) => t.classList.remove("active"));
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        $$(".has-tooltip.active").forEach((t) => t.classList.remove("active"));
      }
    });
  }

  async refreshData() {
    const lbl = $("refresh-time-label");
    if (lbl) {
      lbl.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    try {
      const meta = await api.fetchMeta();
      this.dataMode = meta.data_mode || "fixture";
      this.updateDataModeBadge();
    } catch {}

    // Single unified forecast fetch + passbook calculation
    await Promise.all([this.fetchFourDayForecast(), this.recalculatePassbook()]);
  }

  updateDataModeBadge() {
    const modeBadge = $("data-mode-badge");
    if (!modeBadge) return;
    const isHi = this.currentLang === "hi";
    if (this.dataMode === "live") {
      modeBadge.textContent = isHi ? (this.i18nStrings["live_aq"] || "लाइव AQ") : "Live AQ";
      modeBadge.className = "pill-status saved";
    } else {
      modeBadge.textContent = isHi ? (this.i18nStrings["demo_mode"] || "डेमो") : "Demo";
      modeBadge.className = "pill-status";
    }
  }

  renderLiveWeather(w = this.fourDayData?.current_weather) {
    if (!w) return;
    const tempEl = $("weather-temp-val");
    const humEl = $("weather-humidity-val");
    const windEl = $("weather-wind-val");
    const blhEl = $("weather-blh-val");
    const regPill = $("live-weather-regime-pill");
    const expEl = $("weather-smog-driver-explanation");

    if (tempEl && w.temperature_c != null) tempEl.textContent = `${w.temperature_c.toFixed(1)} °C`;
    if (humEl && w.humidity_pct != null) humEl.textContent = `${Math.round(w.humidity_pct)} %`;
    if (windEl && w.wind_speed_kmh != null) windEl.textContent = `${w.wind_speed_kmh.toFixed(1)} km/h`;
    if (blhEl && w.boundary_layer_height_m != null) blhEl.textContent = `${Math.round(w.boundary_layer_height_m)} m`;

    const isHi = this.currentLang === "hi";
    if (regPill && w.dispersion_regime) {
      const regKey =
        w.dispersion_regime === "Afternoon Mixing Lift"
          ? "disp_mixing"
          : w.dispersion_regime === "Inversion Trap"
          ? "disp_inversion"
          : "disp_stagnant";
      const regName = isHi && this.i18nStrings[regKey] ? this.i18nStrings[regKey] : w.dispersion_regime;
      regPill.textContent = `${isHi ? "प्रसार" : "Dispersion"}: ${regName}`;
      regPill.className = `pill-status ${w.dispersion_regime === "Inversion Trap" ? "debit" : "saved"}`;
    }
    if (expEl && w.physical_explanation) {
      if (isHi) {
        expEl.textContent = `धीमी हवा (${w.wind_speed_kmh.toFixed(1)} km/h) और कम मिक्सिंग परत (${Math.round(
          w.boundary_layer_height_m
        )}m) जमीन के पास धुआं रोक रही है; दोपहर 13:00 के बाद धूप से प्रसार बेहतर होता है।`;
      } else {
        expEl.textContent = `${w.wind_speed_kmh.toFixed(1)} km/h wind + ${Math.round(
          w.boundary_layer_height_m
        )}m boundary layer ceiling: ${w.physical_explanation}`;
      }
    }
  }

  renderFourDayCards(days = this.fourDayData?.days) {
    const grid = $("four-day-cards-grid");
    if (!grid || !Array.isArray(days)) return;
    grid.replaceChildren();
    const isHi = this.currentLang === "hi";

    days.forEach((day) => {
      const card = el("div", "outlook-card");
      const dayNameKey = day.day_label.toLowerCase().replace(" ", "_");
      const dayName = isHi && this.i18nStrings[dayNameKey] ? this.i18nStrings[dayNameKey] : day.day_label;
      const regKey =
        day.dispersion_regime === "Afternoon Mixing Lift"
          ? "disp_mixing"
          : day.dispersion_regime === "Inversion Trap"
          ? "disp_inversion"
          : "disp_stagnant";
      const regName = isHi && this.i18nStrings[regKey] ? this.i18nStrings[regKey] : day.dispersion_regime;
      const catClass = day.naqi_category.toLowerCase().replace(/ /g, "-");
      const catKey = `cat_${catClass.replace(/-/g, "_")}`;
      const catName = isHi && this.i18nStrings[catKey] ? this.i18nStrings[catKey] : day.naqi_category;

      card.append(
        el("div", "font-bold text-xs", dayName),
        el("span", `pill-status ${catClass}`, `AQI ${day.peak_aqi} · ${catName}`),
        el("div", "text-xs font-semibold text-saved", `▲ ${day.cleanest_window_start}–${day.cleanest_window_end}`),
        el("div", "text-xs stat-lbl", `${regName} · ${day.wind_kmh}km/h`),
        el("div", "text-xs text-muted", `BLH: ${Math.round(day.blh_m)}m · P90: ${Math.round(day.uncertainty_p90)}`)
      );
      grid.append(card);
    });
  }

  updateLiveAQ(currentPm25, currentAqi, categoryCode, categoryLabel) {
    if (currentPm25 != null) this.currentOutdoorPm25 = Math.round(currentPm25);
    if (currentAqi != null) this.currentAQI = Math.round(currentAqi);
    if (categoryCode) this.currentCategory = categoryCode;
    if (categoryLabel) this.currentCategoryLabel = categoryLabel;

    const topAqiVal = $("top-aqi-val");
    if (topAqiVal) topAqiVal.textContent = String(this.currentAQI);

    const topAqiCat = $("top-aqi-cat");
    if (topAqiCat) {
      const isHi = this.currentLang === "hi";
      const catKey = `cat_${(this.currentCategory || "very_poor").replace(/-/g, "_")}`;
      topAqiCat.textContent = isHi && this.i18nStrings[catKey] ? this.i18nStrings[catKey] : (this.currentCategoryLabel || "Very Poor");
    }

    const topAqiChip = $("top-aqi-chip");
    if (topAqiChip && this.currentCategory) {
      const catClass = this.currentCategory.replace(/_/g, "-");
      topAqiChip.className = `chip-aqi ${catClass}`;
      topAqiChip.setAttribute("aria-label", `Air Quality: ${this.currentCategoryLabel || this.currentCategory}`);
      const iconUse = topAqiChip.querySelector("use");
      if (iconUse) {
        iconUse.setAttribute("href", `#icon-naqi-${catClass}`);
      }
    }

    const inOut = $("indoor-outdoor-val");
    if (inOut) inOut.textContent = `${this.currentOutdoorPm25} µg/m³`;

    // Unified binding: ensure action strip matches top header AQI
    this.renderActionStrip();
  }

  exportSlotIcs(s, btn = null) {
    const loc = this.familyProfile.location?.city_name || "Delhi NCR";
    exportSlotIcs(s, btn, loc, this.currentLang === "hi");
  }

  /**
   * Unified single forecast fetch: gets 4-day outlook, 24h hourly points, live weather,
   * and live AQ snapshot in ONE network call.
   */
  async fetchFourDayForecast(activity = "walk", durationMin = 60) {
    try {
      const loc = this.familyProfile.location || { lat: 28.4595, lng: 77.0266, city_name: "Delhi NCR" };
      const mid = $("plan-member-select")?.value;
      const mem = (this.familyProfile.members || []).find((m) => m.id === mid) || (this.familyProfile.members || [])[0];
      const ageBand = mem?.age_band || "31_41";

      const d = await api.fetchFourDayForecast({
        lat: loc.lat,
        lng: loc.lng,
        city: loc.city_name || "Delhi NCR",
        activity,
        durationMin,
        ageBand,
      });

      this.fourDayData = d;

      // 1. Update Live Weather tiles
      if (d.current_weather) {
        this.renderLiveWeather(d.current_weather);
      }

      // 2. Unify Live AQ snapshot
      if (d.current_aqi != null && d.current_pm25 != null) {
        this.updateLiveAQ(d.current_pm25, d.current_aqi, d.current_category, d.current_category_label);
      }

      // 3. Tomorrow Watch
      const twText = $("tomorrow-watch-text");
      const twBadge = $("tomorrow-watch-badge");
      if (twText && d.tomorrow_watch_headline) twText.textContent = d.tomorrow_watch_headline;
      if (twBadge && d.tomorrow_watch_direction) {
        twBadge.textContent =
          d.tomorrow_watch_direction === "worsens" ? "▲ Worsens" : d.tomorrow_watch_direction === "improves" ? "▼ Improves" : "● Stable";
        twBadge.className = `pill-status ${
          d.tomorrow_watch_direction === "worsens" ? "debit" : d.tomorrow_watch_direction === "improves" ? "saved" : ""
        }`;
      }

      // 4. Daily outlook cards
      if (Array.isArray(d.days)) {
        this.renderFourDayCards(d.days);
        if (d.days[0]) {
          this.cleanestWindow = `${d.days[0].cleanest_window_start} – ${d.days[0].cleanest_window_end}`;
          const cleanTag = $("clean-window-tag");
          const recText = $("brief-recommendation");
          const chartPill = $("chart-clean-window-pill");
          if (cleanTag) cleanTag.textContent = `▲ Cleanest: ${this.cleanestWindow}`;
          if (recText) recText.textContent = `Cleanest window: ${this.cleanestWindow}.`;
          if (chartPill) {
            chartPill.textContent = `▲ ${
              this.currentLang === "hi" ? "स्वच्छतम दिन का समय" : "Cleanest Daytime Window"
            }: ${this.cleanestWindow}`;
          }
        }
      }

      // 5. Safe house flush
      const flushTime = $("safe-flush-time");
      const flushPm = $("safe-flush-pm");
      if (flushTime && d.safe_house_flush) {
        flushTime.textContent = `${d.safe_house_flush.day_label} ${d.safe_house_flush.start_hour}–${d.safe_house_flush.end_hour}`;
      }
      if (flushPm && d.safe_house_flush) {
        flushPm.textContent = `(${d.safe_house_flush.outdoor_pm25} µg/m³ · ${d.safe_house_flush.dispersion_regime})`;
      }

      // 6. Top multi-day routine slots
      renderMultiDaySlots(d.top_slots || [], (slot, btn) => this.exportSlotIcs(slot, btn));

      // 7. Render 24h hourly chart and strip directly from unified forecast payload
      if (Array.isArray(d.hourly_pm25_24h) && d.hourly_pm25_24h.length >= 24) {
        this.currentHourlyPm25 = d.hourly_pm25_24h;
      } else if (Array.isArray(d.days) && d.days[0]) {
        const clean = findCleanestWakingWindow(this.currentHourlyPm25, 3);
        this.cleanestWindow = clean.label;
      }
      renderPlanHourlyChart(this.currentHourlyPm25, this.currentLang === "hi", this.i18nStrings);
      renderHoursStrip(this.currentHourlyPm25, this.currentLang === "hi");
    } catch {}
  }

  _bindNav() {
    $$(".nav-item[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.getAttribute("data-tab");
        if (tab) this.switchTab(tab);
      });
    });
    const langBtn = $("lang-toggle-btn");
    if (langBtn) {
      langBtn.addEventListener("click", () => this.setLanguage(this.currentLang === "en" ? "hi" : "en"));
    }
    const refBtn = $("btn-refresh");
    if (refBtn) refBtn.addEventListener("click", () => this.refreshData());
  }

  switchTab(tabId) {
    this.currentTab = tabId;
    $$(".tab-panel").forEach((p) => {
      p.hidden = p.id !== `tab-${tabId}`;
    });
    $$(".nav-item[data-tab]").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-tab") === tabId);
    });
    const h = $(`${tabId}-heading`);
    if (h) h.focus();
  }

  async setLanguage(lang) {
    this.currentLang = lang;
    try {
      this.i18nStrings = await api.fetchI18n(lang);
      $$("[data-i18n]").forEach((node) => {
        const k = node.getAttribute("data-i18n");
        if (k && this.i18nStrings[k]) node.textContent = this.i18nStrings[k];
      });
    } catch {}

    const l = $("lang-label");
    if (l) l.textContent = lang === "en" ? "हिन्दी" : "English";
    document.documentElement.lang = lang;

    this.renderMembers();
    this.renderActionStrip();
    this.updateDataModeBadge();
    this.updateLiveAQ(this.currentOutdoorPm25, this.currentAQI, this.currentCategory, this.currentCategoryLabel);
    this.renderLiveWeather();
    this.renderFourDayCards();
    renderPlanHourlyChart(this.currentHourlyPm25, this.currentLang === "hi", this.i18nStrings);
    renderHoursStrip(this.currentHourlyPm25, this.currentLang === "hi");
    if (this.swapsManager) this.swapsManager.update();
  }

  applyLocation(name, lat, lng) {
    const lbl = $("city-name-label");
    if (lbl) lbl.textContent = name;
    this.familyProfile.location = { lat, lng, city_name: name };
    this._saveProfile();
    const m = $("modal-city");
    if (m) m.hidden = true;
    return this.refreshData();
  }

  _bindModals() {
    const wire = (bId, mId, cId) => {
      const b = $(bId);
      const m = $(mId);
      const c = $(cId);
      if (b && m) b.addEventListener("click", () => { m.hidden = false; });
      if (c && m) c.addEventListener("click", () => { m.hidden = true; });
    };
    wire("btn-why-number", "modal-why", "modal-why-close");
    wire("city-btn", "modal-city", "modal-city-close");

    const gpsBtn = $("btn-use-gps");
    if (gpsBtn) {
      gpsBtn.addEventListener("click", () => {
        if (!navigator.geolocation) {
          this.applyLocation("Delhi NCR / Gurugram", 28.4595, 77.0266);
          return;
        }
        gpsBtn.textContent = "📍 Locating...";
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            const lat = pos.coords.latitude;
            const lng = pos.coords.longitude;
            const closest = findClosestCity(lat, lng);
            this.applyLocation(closest.name, lat, lng);
            gpsBtn.textContent = "📍 Use My Current Location";
          },
          () => {
            gpsBtn.textContent = "📍 Use My Current Location";
            this.applyLocation("Delhi NCR / Gurugram", 28.4595, 77.0266);
          },
          { timeout: 8000, maximumAge: 60000 }
        );
      });
    }

    const cityDropdown = $("city-select-dropdown");
    if (cityDropdown) {
      cityDropdown.addEventListener("change", (e) => {
        const val = e.target.value;
        if (val === "custom") {
          $("custom-lat")?.focus();
          return;
        }
        const found = CITIES.find((c) => c.id === val);
        if (found) {
          this.applyLocation(found.name, found.lat, found.lng);
        }
      });
    }

    const btnApplyCustom = $("btn-apply-custom-loc");
    if (btnApplyCustom) {
      btnApplyCustom.addEventListener("click", () => {
        const lat = parseFloat($("custom-lat")?.value) || 28.4595;
        const lng = parseFloat($("custom-lng")?.value) || 77.0266;
        this.applyLocation($("custom-city-name")?.value.trim() || "Custom Area", lat, lng);
      });
    }

    const btnAddMember = $("btn-add-member");
    if (btnAddMember) {
      btnAddMember.addEventListener("click", async () => {
        const name = $("new-member-name")?.value.trim() || "Member";
        const age = $("new-member-age")?.value || "31_41";
        const sens = $("new-member-sens")?.value ? [$("new-member-sens").value] : [];
        this.familyProfile.members.push({
          id: `m_${Date.now()}`,
          name,
          age_band: age,
          sensitivities: sens,
        });
        this._saveProfile();
        $("new-member-name").value = "";
        await this.recalculatePassbook();
      });
    }
  }

  async recalculatePassbook() {
    try {
      const d = await api.postPassbook(this.familyProfile);
      this._updateHero(d);
      this.renderMembers(d.entries || []);
      this._updatePlanMemberOptions();
      this.renderActionStrip();
    } catch {
      this.renderMembers();
    }
  }

  _updateHero(d) {
    this.cleanestWindow = d.cleanest_window || "12:00 – 15:00";
    const debit = $("hero-debit");
    const budget = $("hero-budget");
    const bal = $("hero-balance");
    const cigs = $("hero-cigs");
    if (debit) debit.textContent = `${Math.round(d.total_debit_ug || 0)} µg`;
    if (budget) budget.textContent = `${Math.round(d.total_budget_ug || 0)} µg`;
    if (bal) {
      const net = Math.round(d.net_balance_ug || 0);
      bal.textContent = `${net > 0 ? "+" : ""}${net} µg`;
      bal.className = `stat-val ${net < 0 ? "debit" : "saved"}`;
    }
    if (cigs) {
      const cVal = d.cigarette_equivalent != null ? d.cigarette_equivalent : 0;
      cigs.textContent = `${cVal.toFixed(1)} cigs`;
    }

    const headline = $("brief-headline");
    if (headline) {
      const net = d.net_balance_ug ?? -1;
      const isHi = this.currentLang === "hi";
      if (net < 0) {
        const member = d.highest_debit_member ? ` – ${d.highest_debit_member}` : "";
        headline.textContent = isHi ? `एयर बजट पार हो गया${member}` : `Air budget exceeded${member}`;
        headline.className = "card-title text-debit";
      } else {
        headline.textContent = isHi ? "WHO बजट के भीतर ✓ – परिवार सुरक्षित" : "Within WHO budget ✓ – Household protected";
        headline.className = "card-title text-saved";
      }
    }
    const peakTag = $("peak-warning-tag");
    if (peakTag && d.peak_pm25 != null) {
      peakTag.textContent = `▼ Peak PM2.5: ${Math.round(d.peak_pm25)} µg/m³`;
    }
    const cleanTag = $("clean-window-tag");
    if (cleanTag && d.cleanest_window) {
      cleanTag.textContent = `▲ Cleanest: ${d.cleanest_window}`;
    }
    const recText = $("brief-recommendation");
    if (recText && d.cleanest_window) {
      recText.textContent = `Cleanest window: ${d.cleanest_window}.`;
    }

    this.renderActionStrip();
  }

  renderActionStrip() {
    const pillsWrap = $("action-strip-pills");
    const pmLbl = $("action-strip-pm");
    if (!pillsWrap) return;
    pillsWrap.replaceChildren();

    const pm = this.currentOutdoorPm25 || 317;
    const aqi = this.currentAQI || 317;
    const isHi = this.currentLang === "hi";
    if (pmLbl) {
      pmLbl.textContent = `${isHi ? "लाइव" : "Live"}: ${pm} µg/m³ · AQI ${aqi}`;
    }

    // 1. Mask Pill
    const maskPill = el("span", "pill-status");
    if (pm > 120) {
      maskPill.className = "pill-status debit";
      maskPill.textContent = isHi ? "😷 मास्क: बाहर N95 अनिवार्य" : "😷 Mask: N95 Required Outdoors";
    } else if (pm > 60) {
      maskPill.className = "pill-status warn";
      maskPill.textContent = isHi ? "😷 मास्क: N95 अनुशंसित" : "😷 Mask: N95 Recommended";
    } else {
      maskPill.className = "pill-status saved";
      maskPill.textContent = isHi ? "😊 मास्क: वैकल्पिक" : "😊 Mask: Optional";
    }

    // 2. Windows / Flush Pill
    const winPill = el("span", "pill-status");
    const currentHour = new Date().getHours();
    const isFlushTime = currentHour >= 12 && currentHour <= 15;
    if (isFlushTime) {
      winPill.className = "pill-status saved";
      winPill.textContent = isHi ? "🪟 खिड़कियाँ: सुरक्षित फ्लश (1h खोलें)" : "🪟 Windows: Safe Flush Window (1h Open)";
    } else {
      winPill.className = "pill-status";
      winPill.textContent = isHi ? "🪟 खिड़कियाँ: बंद रखें (स्मॉग सील)" : "🪟 Windows: Keep Sealed";
    }

    // 3. Purifier Pill
    const purPill = el("span", "pill-status");
    if (pm > 120) {
      purPill.className = "pill-status debit";
      purPill.textContent = isHi ? "🌀 प्यूरीफायर: हाई / निरंतर" : "🌀 Purifier: High / Continuous";
    } else if (pm > 60) {
      purPill.className = "pill-status warn";
      purPill.textContent = isHi ? "🌀 प्यूरीफायर: ऑटो / मीडियम" : "🌀 Purifier: Auto / Medium";
    } else {
      purPill.className = "pill-status saved";
      purPill.textContent = isHi ? "🌀 प्यूरीफायर: लो / इको" : "🌀 Purifier: Low / Eco";
    }

    // 4. Outdoor / Pets Pill
    const petPill = el("span", "pill-status");
    if (pm > 120) {
      petPill.className = "pill-status debit";
      petPill.textContent = isHi ? "🐾 पेट्स/सैर: 10m से कम · भारी श्रम रोकें" : "🐾 Outdoor/Pets: 10m Walks Only · Rest";
    } else if (pm > 60) {
      petPill.className = "pill-status warn";
      petPill.textContent = isHi ? "🐾 पेट्स/सैर: दोपहर 12–15 बजे सुरक्षित" : "🐾 Outdoor/Pets: Moderate · Walk 12–15:00";
    } else {
      petPill.className = "pill-status saved";
      petPill.textContent = isHi ? "🌳 बाहर: खेलकूद व सैर के लिए सुरक्षित" : "🌳 Outdoor: Safe for Play & Walks";
    }

    pillsWrap.append(maskPill, winPill, purPill, petPill);
  }

  renderMembers(entries = []) {
    const list = $("passbook-members-list");
    if (!list) return;
    list.replaceChildren();

    this.familyProfile.members.forEach((m, idx) => {
      const e = entries.find((x) => x.member_id === m.id || x.member_label === m.name) || {};
      const bVal = Math.round(e.budget_ug || 180);
      const dVal = Math.round(e.debit_ug || 420);
      const pct = bVal > 0 ? (dVal / bVal) * 100 : 100;

      const row = el("div", "balance-row");
      const info = el("div", "member-info");
      const details = el("div");

      info.append(el("div", "member-avatar", m.name.charAt(0).toUpperCase()), details);
      details.append(
        el("div", "font-semibold", m.name),
        el("div", "stat-lbl text-xs", `Budget: ${bVal} µg/d ${m.sensitivities?.length ? "· " + m.sensitivities.join(", ") : ""}`)
      );

      const barWrap = el("div", "member-bar-wrap");
      const barSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      barSvg.setAttribute("width", "100%");
      barSvg.setAttribute("height", "10");

      const barBg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      barBg.setAttribute("width", "100%");
      barBg.setAttribute("height", "10");
      barBg.setAttribute("rx", "5");
      barBg.setAttribute("fill", "#e2e8f0");

      const barFill = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      barFill.setAttribute("width", `${Math.min(100, Math.max(2, pct))}%`);
      barFill.setAttribute("height", "10");
      barFill.setAttribute("rx", "5");
      const fillColor = pct < 75 ? "#0F6E66" : pct <= 100 ? "#C9A400" : "#C62828";
      barFill.setAttribute("fill", fillColor);

      barSvg.append(barBg, barFill);
      barWrap.appendChild(barSvg);

      const del = el("button", "btn btn-sm btn-secondary", "✕");
      del.title = "Remove";
      del.addEventListener("click", async () => {
        this.familyProfile.members.splice(idx, 1);
        this._saveProfile();
        await this.recalculatePassbook();
      });

      const acts = el("div", "flex gap-05 items-center");
      acts.append(el("span", `pill-status ${dVal > bVal ? "debit" : "saved"}`, `${dVal} µg`), del);
      row.append(info, barWrap, acts);
      list.appendChild(row);
    });
  }

  _updatePlanMemberOptions() {
    const sel = $("plan-member-select");
    if (!sel) return;
    sel.replaceChildren();
    this.familyProfile.members.forEach((m) => {
      const opt = el("option", null, m.name);
      opt.value = m.id;
      sel.appendChild(opt);
    });
  }

  _bindPlan() {
    const btn = $("btn-run-plan");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const mid = $("plan-member-select")?.value || this.familyProfile.members[0]?.id || "m1";
      const dur = parseInt($("plan-duration")?.value || "60", 10);
      const actType = $("plan-activity-type")?.value || "pet_walk";

      const actConfig = {
        pet_walk: { title: "Dog / Pet Walk", micro_env: "outdoor", activity: "pet_walk" },
        market_shopping: { title: "Market / Shopping", micro_env: "outdoor", activity: "market_shopping" },
        school_run: { title: "School Run", micro_env: "transit_auto", activity: "school_run" },
        park_terrace: { title: "Park / Terrace Time", micro_env: "park_terrace", activity: "park_terrace" },
        transit_auto: { title: "Auto / Bike Commute", micro_env: "transit_auto", activity: "light" },
        walk: { title: "Walk", micro_env: "outdoor", activity: "light" },
        run: { title: "Run", micro_env: "outdoor", activity: "moderate" },
      }[actType] || { title: "Activity", micro_env: "outdoor", activity: "moderate" };

      await this.fetchFourDayForecast(actType, dur);

      try {
        const res = await api.postPlan({
          profile: this.familyProfile,
          memberId: mid,
          flexibleActivities: [
            {
              id: `act_${actType}`,
              member_id: mid,
              title: actConfig.title,
              duration_hours: Math.max(1, Math.round(dur / 60)),
              earliest_start_hour: 11,
              latest_start_hour: 17,
              micro_env: actConfig.micro_env,
              activity: actConfig.activity,
              usual_start_hour: actType === "market_shopping" ? 10 : actType === "park_terrace" ? 17 : 7,
            },
          ],
        });

        const shift = (res.shifts || [])[0];
        this.todaySavings = res.total_savings_ug || 0;
        if (shift) {
          const h = $("plan-shift-hours");
          const d = $("plan-shift-delta");
          const pmStr = shift.outdoor_pm25_at_optimized ? ` (${Math.round(shift.outdoor_pm25_at_optimized)} µg/m³)` : "";
          if (h) h.textContent = `${shift.usual_start_hour}:00 → ${shift.optimized_start_hour}:00${pmStr}`;
          if (d) d.textContent = `▲ ${Math.round(shift.dose_saved_ug)} µg (${Math.round(shift.savings_percent || 0)}%)`;
        }
      } catch {}
    });

    const icsBtn = $("btn-export-ics");
    if (icsBtn) {
      icsBtn.addEventListener("click", () => {
        const slot = {
          day_index: 0,
          day_label: "Today",
          time_label: this.cleanestWindow,
          start_hour: 13,
          end_hour: 16,
          outdoor_pm25: this.currentOutdoorPm25 || 120,
          savings_ug: this.todaySavings || 210,
        };
        this.exportSlotIcs(slot, icsBtn);
      });
    }
  }

  _bindIndoor() {
    const vRng = $("indoor-vol-range");
    const cRng = $("indoor-cadr-range");
    const wSel = $("indoor-window-select");
    const pBtn = $("btn-toggle-purifier");
    const pRng = $("plant-count-range");
    let on = true;
    let simTimer = null;

    const runEngineSim = async () => {
      const vol = parseFloat(vRng?.value || "60");
      const cadr = on ? parseFloat(cRng?.value || "300") : 0.0;
      const isWindowOpen = wSel?.value === "open";
      const outPm = this.currentOutdoorPm25 || 317;
      const statusPill = $("indoor-sim-status");
      if (statusPill) statusPill.textContent = this.currentLang === "hi" ? "सिम्युलेटिंग..." : "Simulating...";

      try {
        const d = await api.postIndoorSimulate({
          location: this.familyProfile.location,
          room: {
            name: "Living Room",
            volume_m3: vol,
            purifier_cadr_m3_per_h: cadr,
            purifier_on_hours: on ? Array.from({ length: 24 }, (_, i) => i) : [],
            windows_open_hours: isWindowOpen ? [12, 13, 14] : [],
          },
          sources: this.familyProfile.sources || [],
        });

        const sim = d.simulation || {};
        const meanPm = Math.round(sim.mean_pm25_ug_m3 || 42);
        const reqCadr = Math.round(d.purifier_recommendation?.required_cadr_m3_per_h || vol * 5);
        const cleanPct = Math.max(0, Math.min(99, Math.round((1 - meanPm / Math.max(1, outPm)) * 100)));

        if ($("indoor-pm25-val")) $("indoor-pm25-val").textContent = `${meanPm} µg/m³`;
        if ($("indoor-preview-pm25")) $("indoor-preview-pm25").textContent = `${meanPm} µg/m³`;
        if ($("indoor-outdoor-val")) $("indoor-outdoor-val").textContent = `${outPm} µg/m³`;
        if ($("indoor-cadr-val")) $("indoor-cadr-val").textContent = `${reqCadr} m³/h`;
        if ($("indoor-clean-pct")) $("indoor-clean-pct").textContent = `▲ ${cleanPct}% Cleaner Air`;
        if (statusPill) statusPill.textContent = this.currentLang === "hi" ? "सिम्युलेटेड (इंजन)" : "Simulated (engine)";
      } catch {
        if (statusPill) statusPill.textContent = "Simulated (offline)";
      }
    };

    const updatePreview = () => {
      const vol = parseFloat(vRng?.value || "60");
      const cadr = on ? parseFloat(cRng?.value || "300") : 0;
      const ach = wSel?.value === "sealed" ? 0.4 : wSel?.value === "open" ? 2.5 : 0.8;
      const outPm = this.currentOutdoorPm25 || 317;
      if ($("indoor-vol-label")) $("indoor-vol-label").textContent = `${vol} m³`;
      if ($("indoor-cadr-label")) $("indoor-cadr-label").textContent = `${cadr} m³/h`;

      const statusPill = $("indoor-sim-status");
      if (statusPill) statusPill.textContent = this.currentLang === "hi" ? "पूर्वावलोकन (स्लाइडिंग...)" : "Preview (sliding...)";

      const cIn = Math.round((ach * outPm) / (ach + cadr / vol + 0.2));
      const pct = Math.max(0, Math.min(95, Math.round((1 - cIn / Math.max(1, outPm)) * 100)));
      if ($("indoor-pm25-val")) $("indoor-pm25-val").textContent = `${cIn} µg/m³`;
      if ($("indoor-preview-pm25")) $("indoor-preview-pm25").textContent = `${cIn} µg/m³`;
      if ($("indoor-outdoor-val")) $("indoor-outdoor-val").textContent = `${outPm} µg/m³`;
      if ($("indoor-clean-pct")) $("indoor-clean-pct").textContent = `▲ ${pct}% Cleaner Air (Preview)`;

      clearTimeout(simTimer);
      simTimer = setTimeout(runEngineSim, 300);
    };

    const updatePlants = () => {
      const count = parseInt(pRng?.value || "5", 10);
      const cadr = (count * 0.1).toFixed(1);
      const hepa = on ? parseFloat(cRng?.value || "300") : 300;
      const ratio = Math.round(hepa / Math.max(0.1, count * 0.1));
      if ($("plant-count-label")) $("plant-count-label").textContent = `${count} plants`;
      if ($("plant-cadr-label")) $("plant-cadr-label").textContent = `CADR: ${cadr} m³/h`;
      if ($("plant-reality-verdict")) {
        $("plant-reality-verdict").textContent = `${count} plants clear ~${cadr} m³/h. A ${hepa} m³/h HEPA purifier is ${ratio}× faster for winter smog. Wipe leaves weekly and avoid overwatering.`;
      }
    };

    if (vRng) vRng.addEventListener("input", updatePreview);
    if (cRng) cRng.addEventListener("input", updatePreview);
    if (wSel) wSel.addEventListener("change", updatePreview);
    if (pRng) pRng.addEventListener("input", updatePlants);

    if (pBtn) {
      pBtn.addEventListener("click", () => {
        on = !on;
        pBtn.textContent = on ? "Purifier ON" : "Purifier OFF";
        pBtn.className = `btn btn-sm ${on ? "btn-primary" : "btn-secondary"}`;
        pBtn.setAttribute("aria-pressed", String(on));
        updatePreview();
      });
    }
    runEngineSim();
  }

  _bindTodayActions() {
    const copyBtn = $("btn-copy-digest");
    if (copyBtn) {
      copyBtn.addEventListener("click", async () => {
        try {
          const resp = await fetch("/api/v1/passbook/digest", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Accept-Language": this.currentLang || "en",
            },
            body: JSON.stringify({ profile: this.familyProfile }),
          });
          if (resp.ok) {
            const digest = (await resp.json()).data?.digest_text || "";
            if (navigator.clipboard && navigator.clipboard.writeText) {
              await navigator.clipboard.writeText(digest);
            }
            copyBtn.textContent = this.currentLang === "hi" ? "✓ WhatsApp के लिए कॉपी हुआ!" : "✓ Copied for WhatsApp!";
            setTimeout(() => {
              copyBtn.textContent = this.currentLang === "hi" ? "📋 पासबुक साझा करें" : "📋 Share Passbook";
            }, 2500);
          }
        } catch {
          copyBtn.textContent = "✓ Passbook Ready";
        }
      });
    }

    const petBtn = $("btn-pet-care");
    const petBtnIndoor = $("btn-pet-care-indoor");
    const petModal = $("modal-pet");
    const petClose = $("modal-pet-close");
    if (petBtn && petModal) {
      petBtn.addEventListener("click", () => {
        petModal.hidden = false;
        this._loadPetGuidance("dog");
      });
    }
    if (petBtnIndoor && petModal) {
      petBtnIndoor.addEventListener("click", () => {
        petModal.hidden = false;
        $$(".pet-tab-btn").forEach((b) => {
          const sp = b.getAttribute("data-species");
          b.className = sp === "cat" ? "btn btn-sm btn-primary flex-1 pet-tab-btn" : "btn btn-sm btn-secondary flex-1 pet-tab-btn";
        });
        this._loadPetGuidance("cat");
      });
    }
    if (petClose && petModal) {
      petClose.addEventListener("click", () => {
        petModal.hidden = true;
      });
    }

    $$(".pet-tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        $$(".pet-tab-btn").forEach((b) => {
          b.className = "btn btn-sm btn-secondary flex-1 pet-tab-btn";
        });
        btn.className = "btn btn-sm btn-primary flex-1 pet-tab-btn";
        const sp = btn.getAttribute("data-species") || "dog";
        this._loadPetGuidance(sp);
      });
    });
  }

  async _loadPetGuidance(species) {
    try {
      const d = await api.postPetGuidance({
        species,
        location: this.familyProfile.location,
      });
      if ($("pet-walk-summary")) $("pet-walk-summary").textContent = d.walk_advice || "";
      if ($("pet-walk-dur-pill")) $("pet-walk-dur-pill").textContent = `Max ${d.safe_walk_duration_min} min`;
      if ($("pet-wipe-pill")) $("pet-wipe-pill").textContent = d.post_walk_wipe_needed ? "Damp Wipe Needed" : "Wipe Optional";
      const stepsUl = $("pet-indoor-steps");
      if (stepsUl) {
        stepsUl.replaceChildren();
        (d.warnings || []).forEach((w) => {
          const li = el("li", "text-debit font-semibold", `⚠️ ${w}`);
          stepsUl.appendChild(li);
        });
        (d.practical_steps || []).forEach((s) => {
          const li = el("li", null, `✓ ${s}`);
          stepsUl.appendChild(li);
        });
      }
    } catch {}
  }
}

// Instantiate and expose globally on window for story mode and browser console access
const app = new HawaKhataApp();
window.hawakhataApp = app;
export default app;
