import { StoryController } from "./story.js";

const $ = (id) => document.getElementById(id);
const $$ = (sel) => document.querySelectorAll(sel);
const el = (tag, cls, txt) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (txt !== undefined) node.textContent = txt;
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
  { id: "patna", name: "Patna", lat: 25.5941, lng: 85.1376 },
  { id: "ahmedabad", name: "Ahmedabad", lat: 23.0225, lng: 72.5714 }
];

function findClosestCity(lat, lng) {
  let closest = CITIES[0], minD = Infinity;
  for (const c of CITIES) {
    const d = Math.hypot(lat - c.lat, lng - c.lng);
    if (d < minD) { minD = d; closest = c; }
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
    this.cleanestWindow = "12:00 – 15:00";
    this.currentHourlyPm25 = [];
    this.todaySavings = 340;
    this.fourDayData = null;
    this.init();
  }

  _loadProfile() {
    try {
      const s = localStorage.getItem("hawakhata_family");
      if (s) return JSON.parse(s);
    } catch {}
    return {
      id: "fam_local", name: "Family",
      location: { lat: 28.4595, lng: 77.0266, city_name: "Delhi NCR / Gurugram" },
      rooms: [{ name: "Living Room", volume_m3: 60.0, purifier_cadr_m3_per_h: 300.0, purifier_on_hours: [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23], windows_open_hours: [] }],
      sources: [],
      members: [
        { id: "m1", name: "Aarav (Child)", age_band: "child", sensitivities: ["asthma"] },
        { id: "m2", name: "Dadi (Elder)", age_band: "senior", sensitivities: ["cardiovascular"] },
        { id: "m3", name: "Priya (Adult)", age_band: "31_41", sensitivities: [] }
      ]
    };
  }

  _saveProfile() {
    try { localStorage.setItem("hawakhata_family", JSON.stringify(this.familyProfile)); } catch {}
  }

  async init() {
    this._bindNav();
    this._bindModals();
    this._bindChat();
    this._bindSwaps();
    this._bindHours();
    this._bindIndoor();
    this._bindPlan();
    this._bindMembers();
    this._bindTodayActions();
    this._bindTooltips();
    await this.refreshData();
    await this.setLanguage(this.currentLang);
    const sId = new URLSearchParams(window.location.search).get("story");
    if (sId) this.story.start(sId);
  }

  _bindTooltips() {
    $$(".has-tooltip").forEach((tip) => {
      tip.addEventListener("click", (e) => {
        e.stopPropagation();
        tip.classList.toggle("active");
      });
    });
    document.addEventListener("click", () => {
      $$(".has-tooltip.active").forEach((t) => t.classList.remove("active"));
    });
  }

  async refreshData() {
    const lbl = $("refresh-time-label");
    const modeBadge = $("data-mode-badge");
    if (lbl) lbl.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    try {
      const r = await fetch("/api/v1/meta");
      if (r.ok) {
        const d = (await r.json()).data || {};
        if (modeBadge) {
          modeBadge.textContent = d.data_mode === "live" ? "Live AQ" : "Demo";
          modeBadge.className = `pill-status ${d.data_mode === "live" ? "saved" : ""}`;
        }
      }
    } catch {}
    await this.recalculatePassbook();
    await this.fetchFourDayForecast();
  }

  async fetchFourDayForecast(activity = "walk", durationMin = 60) {
    try {
      const loc = this.familyProfile.location || { lat: 28.4595, lng: 77.0266, city_name: "Delhi NCR" };
      const mid = $("plan-member-select")?.value;
      const mem = this.familyProfile.members.find((m) => m.id === mid) || this.familyProfile.members[0];
      const ageBand = mem?.age_band || "31_41";
      const q = new URLSearchParams({
        lat: String(loc.lat),
        lng: String(loc.lng),
        city: loc.city_name || "Delhi NCR",
        activity: activity,
        duration_min: String(durationMin),
        age_band: ageBand
      });
      const resp = await fetch(`/api/v1/forecast/4day?${q.toString()}`);
      if (!resp.ok) return;
      const d = (await resp.json()).data || {};
      this.fourDayData = d;

      const twText = $("tomorrow-watch-text"), twBadge = $("tomorrow-watch-badge");
      if (twText && d.tomorrow_watch_headline) twText.textContent = d.tomorrow_watch_headline;
      if (twBadge && d.tomorrow_watch_direction) {
        twBadge.textContent = d.tomorrow_watch_direction === "worsens" ? "▲ Worsens" : (d.tomorrow_watch_direction === "improves" ? "▼ Improves" : "● Stable");
        twBadge.className = `pill-status ${d.tomorrow_watch_direction === "worsens" ? "debit" : (d.tomorrow_watch_direction === "improves" ? "saved" : "")}`;
      }

      const grid = $("four-day-cards-grid");
      if (grid && Array.isArray(d.days)) {
        grid.replaceChildren();
        d.days.forEach((day) => {
          const card = el("div", "outlook-card");
          const isHi = this.currentLang === "hi";
          const dayNameKey = day.day_label.toLowerCase().replace(" ", "_");
          const dayName = (isHi && this.i18nStrings[dayNameKey]) ? this.i18nStrings[dayNameKey] : day.day_label;
          const regKey = day.dispersion_regime === "Afternoon Mixing Lift" ? "disp_mixing" : (day.dispersion_regime === "Inversion Trap" ? "disp_inversion" : "disp_stagnant");
          const regName = (isHi && this.i18nStrings[regKey]) ? this.i18nStrings[regKey] : day.dispersion_regime;
          const catClass = day.naqi_category.toLowerCase().replace(/ /g, "-");
          const catKey = `cat_${catClass.replace(/-/g, "_")}`;
          const catName = (isHi && this.i18nStrings[catKey]) ? this.i18nStrings[catKey] : day.naqi_category;

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

      const flushTime = $("safe-flush-time"), flushPm = $("safe-flush-pm");
      if (flushTime && d.safe_house_flush) flushTime.textContent = `${d.safe_house_flush.day_label} ${d.safe_house_flush.start_hour}–${d.safe_house_flush.end_hour}`;
      if (flushPm && d.safe_house_flush) flushPm.textContent = `(${d.safe_house_flush.outdoor_pm25} µg/m³ · ${d.safe_house_flush.dispersion_regime})`;
      this.renderMultiDaySlots(d.top_slots || []);

      // Fetch 24h air points for active city to drive live 24h chart
      try {
        const airResp = await fetch("/api/v1/air/forecast", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lat: loc.lat, lng: loc.lng, hours: 24 })
        });
        if (airResp.ok) {
          const airData = (await airResp.json()).data || {};
          if (airData.points && airData.points.length >= 24) {
            this.currentHourlyPm25 = airData.points.map((p) => p.pm25_ug_m3);
            this.renderPlanHourlyChart(this.currentHourlyPm25);
            this._renderHoursStrip(airData.points);
          }
        }
      } catch {}
    } catch {}
  }

  _renderHoursStrip(points = []) {
    const s = $("hours-strip");
    if (!s) return;
    s.replaceChildren();
    points.slice(0, 24).forEach((pt, h) => {
      const pm = pt.pm25_ug_m3 || 0;
      let cat = "severe";
      if (pm <= 30) cat = "good";
      else if (pm <= 60) cat = "satisfactory";
      else if (pm <= 90) cat = "moderate";
      else if (pm <= 120) cat = "poor";
      else if (pm <= 250) cat = "very-poor";
      const cell = el("div", `hour-cell ${cat}${h >= 12 && h <= 15 ? " highlight" : ""}`, `${h}`);
      cell.setAttribute("title", `${h}:00 · ${Math.round(pm)} µg/m³`);
      s.appendChild(cell);
    });
  }

  renderMultiDaySlots(slots = []) {
    const list = $("multiday-slots-list");
    if (!list) return;
    list.replaceChildren();
    if (!slots.length) return list.append(el("div", "stat-lbl text-xs", "No 4-day slots calculated yet."));
    slots.forEach((s) => {
      const row = el("div", "stat-box flex justify-between items-center text-left"), left = el("div"), btns = el("div", "flex gap-05 items-center");
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
      btnIcs.addEventListener("click", () => {
        const loc = this.familyProfile.location?.city_name || "Delhi NCR";
        const pad = (n) => String(n).padStart(2, "0");
        const toUtc = (dt) => `${dt.getUTCFullYear()}${pad(dt.getUTCMonth() + 1)}${pad(dt.getUTCDate())}T${pad(dt.getUTCHours())}${pad(dt.getUTCMinutes())}00Z`;
        const start = new Date(Date.now() + (s.day_index || 1) * 86400000);
        start.setHours(s.start_hour || 13, 0, 0, 0);
        const end = new Date(start.getTime() + Math.max(1, (s.end_hour - s.start_hour) || 1) * 3600000);
        const ics = `BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//HawaKhata//Air Passbook//EN\r\nBEGIN:VEVENT\r\nUID:hk-${Date.now()}@hawakhata.org\r\nDTSTAMP:${toUtc(new Date())}\r\nDTSTART:${toUtc(start)}\r\nDTEND:${toUtc(end)}\r\nSUMMARY:HawaKhata Clean Window: ${s.day_label} ${s.time_label}\r\nDESCRIPTION:Scheduled clean air window in ${loc}. Dilutes PM2.5 to ${s.outdoor_pm25} ug/m3; saves ${s.savings_ug} ug.\r\nLOCATION:${loc}\r\nSTATUS:CONFIRMED\r\nEND:VEVENT\r\nEND:VCALENDAR`;
        const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `hawakhata-${s.day_label.toLowerCase()}-routine.ics`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        btnIcs.textContent = "✓ Saved";
        setTimeout(() => { btnIcs.textContent = "📅 .ics"; }, 2000);
      });
      btns.append(btnPlan, btnIcs);
      row.append(left, btns);
      list.append(row);
    });
  }

  _bindNav() {
    $$(".nav-item[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const t = btn.getAttribute("data-tab");
        if (t) this.switchTab(t);
      });
    });
    const langBtn = $("lang-toggle-btn");
    if (langBtn) langBtn.addEventListener("click", () => this.setLanguage(this.currentLang === "en" ? "hi" : "en"));
    const refBtn = $("refresh-btn");
    if (refBtn) refBtn.addEventListener("click", () => this.refreshData());
  }

  switchTab(tabId) {
    this.currentTab = tabId;
    $$(".tab-pane").forEach((p) => { p.hidden = p.id !== `tab-${tabId}`; });
    $$(".nav-item[data-tab]").forEach((b) => { b.classList.toggle("active", b.getAttribute("data-tab") === tabId); });
    const h = $(`${tabId}-heading`);
    if (h) h.focus();
  }

  async setLanguage(lang) {
    this.currentLang = lang;
    try {
      const r = await fetch(`/static/i18n/${lang}.json`);
      if (r.ok) {
        this.i18nStrings = await r.json();
        $$("[data-i18n]").forEach((node) => {
          const k = node.getAttribute("data-i18n");
          if (k && this.i18nStrings[k]) node.textContent = this.i18nStrings[k];
        });
      }
    } catch {}
    const l = $("lang-label");
    if (l) l.textContent = lang === "en" ? "हिन्दी" : "English";
    document.documentElement.lang = lang;
    this.renderMembers();
    this.renderActionStrip();
    if (this.currentHourlyPm25 && this.currentHourlyPm25.length) {
      this.renderPlanHourlyChart(this.currentHourlyPm25);
    }
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
      const b = $(bId), m = $(mId), c = $(cId);
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
  }

  _bindMembers() {
    const m = $("modal-member"), f = $("member-form"), close = () => { if (m) m.hidden = true; };
    const bAdd = $("btn-add-member");
    if (bAdd && m) {
      bAdd.addEventListener("click", () => {
        $("member-edit-id").value = "";
        $("member-name-input").value = "";
        $$('#member-form input[type="checkbox"]').forEach((c) => { c.checked = false; });
        m.hidden = false;
      });
    }
    if ($("modal-member-close")) $("modal-member-close").addEventListener("click", close);
    if ($("btn-cancel-member")) $("btn-cancel-member").addEventListener("click", close);
    if (f) {
      f.addEventListener("submit", async (e) => {
        e.preventDefault();
        const editId = $("member-edit-id")?.value;
        const name = $("member-name-input")?.value.trim() || "Member";
        const age = $("member-age-select")?.value || "31_41";
        const sens = Array.from($$('#member-form input:checked')).map((c) => c.value);
        if (editId) {
          const idx = this.familyProfile.members.findIndex((x) => x.id === editId);
          if (idx !== -1) this.familyProfile.members[idx] = { id: editId, name, age_band: age, sensitivities: sens };
        } else {
          this.familyProfile.members.push({ id: `m_${Date.now()}`, name, age_band: age, sensitivities: sens });
        }
        this._saveProfile();
        close();
        await this.recalculatePassbook();
      });
    }
  }

  async recalculatePassbook() {
    try {
      const resp = await fetch("/api/v1/passbook", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile: this.familyProfile }),
      });
      if (resp.ok) {
        const d = (await resp.json()).data || {};
        this._updateHero(d);
        this.renderMembers(d.entries || []);
        this._updatePlanMemberOptions();
        this.renderActionStrip();
      }
    } catch {
      this.renderMembers();
    }
  }

  _updateHero(d) {
    this.currentOutdoorPm25 = Math.round(d.current_pm25 || (d.peak_pm25 ? d.peak_pm25 * 0.85 : 317));
    this.currentAQI = d.current_aqi || 317;
    this.cleanestWindow = d.cleanest_window || "12:00 – 15:00";

    const debit = $("hero-debit"), budget = $("hero-budget"), bal = $("hero-balance"), cigs = $("hero-cigs");
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

    const inOut = $("indoor-outdoor-val");
    if (inOut) inOut.textContent = `${this.currentOutdoorPm25} µg/m³`;

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
    const topAqiChip = $("top-aqi-chip");
    const topAqiVal = $("top-aqi-val");
    const topAqiCat = $("top-aqi-cat");
    if (d.current_aqi != null && topAqiVal) {
      topAqiVal.textContent = String(d.current_aqi);
    }
    if (d.current_category_label && topAqiCat) {
      topAqiCat.textContent = d.current_category_label;
    }
    if (topAqiChip && d.current_category) {
      const catClass = d.current_category.replace(/_/g, "-");
      topAqiChip.className = `chip-aqi ${catClass}`;
      topAqiChip.setAttribute("aria-label", `Air Quality: ${d.current_category_label || d.current_category}`);
      const iconUse = topAqiChip.querySelector("use");
      if (iconUse) {
        iconUse.setAttribute("href", `#icon-naqi-${catClass}`);
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
    const isHi = this.currentLang === "hi";
    if (pmLbl) {
      pmLbl.textContent = `${isHi ? "लाइव" : "Live"}: ${pm} µg/m³ · AQI ${this.currentAQI || 317}`;
    }

    // 1. Mask
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

    // 2. Windows / Flush
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

    // 3. Purifier
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

    // 4. Outdoor / Pets
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
      const bVal = Math.round(e.budget_ug || 180), dVal = Math.round(e.debit_ug || 420);
      const pct = bVal > 0 ? (dVal / bVal) * 100 : 100;
      const row = el("div", "balance-row"), info = el("div", "member-info"), details = el("div");
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
      const fillColor = pct < 75 ? "#0F6E66" : (pct <= 100 ? "#C9A400" : "#C62828");
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

  renderPlanHourlyChart(hourlyPm25 = []) {
    const wrap = $("plan-hourly-svg-wrap");
    if (!wrap) return;
    wrap.replaceChildren();

    const pts = hourlyPm25 && hourlyPm25.length >= 24
      ? hourlyPm25.slice(0, 24)
      : [320, 310, 300, 290, 330, 380, 420, 390, 310, 220, 160, 110, 95, 90, 105, 140, 210, 290, 350, 380, 390, 370, 350, 330];

    const maxPm = Math.max(100, ...pts);
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 500 120");
    svg.setAttribute("class", "custom-viz");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "24-Hour PM2.5 Hourly Chart");

    // Cleanest daytime window highlight (hours 12 to 15)
    const hlRect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    hlRect.setAttribute("x", `${12 * 20 + 2}`);
    hlRect.setAttribute("y", "6");
    hlRect.setAttribute("width", "60");
    hlRect.setAttribute("height", "96");
    hlRect.setAttribute("rx", "4");
    hlRect.setAttribute("fill", "#0F6E66");
    hlRect.setAttribute("fill-opacity", "0.12");
    hlRect.setAttribute("stroke", "#0F6E66");
    hlRect.setAttribute("stroke-width", "1");
    hlRect.setAttribute("stroke-dasharray", "3 2");
    svg.appendChild(hlRect);

    const hlText = document.createElementNS("http://www.w3.org/2000/svg", "text");
    hlText.setAttribute("x", "272");
    hlText.setAttribute("y", "16");
    hlText.setAttribute("fill", "#0F6E66");
    hlText.setAttribute("font-size", "8");
    hlText.setAttribute("font-weight", "700");
    hlText.setAttribute("text-anchor", "middle");
    hlText.textContent = this.currentLang === "hi" ? "स्वच्छ समय" : "CLEANEST";
    svg.appendChild(hlText);

    // Axis line
    const axis = document.createElementNS("http://www.w3.org/2000/svg", "line");
    axis.setAttribute("x1", "10");
    axis.setAttribute("y1", "95");
    axis.setAttribute("x2", "490");
    axis.setAttribute("y2", "95");
    axis.setAttribute("stroke", "var(--line, #cbd5e1)");
    axis.setAttribute("stroke-width", "1");
    svg.appendChild(axis);

    // Dynamic info label
    const infoText = document.createElementNS("http://www.w3.org/2000/svg", "text");
    infoText.setAttribute("x", "250");
    infoText.setAttribute("y", "116");
    infoText.setAttribute("fill", "var(--ink, #1e293b)");
    infoText.setAttribute("font-size", "9");
    infoText.setAttribute("font-weight", "600");
    infoText.setAttribute("text-anchor", "middle");
    infoText.textContent = this.currentLang === "hi"
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

  _bindPlan() {
    const btn = $("btn-run-plan");
    const tabToday = $("btn-plan-today");
    const tabMulti = $("btn-plan-multiday");
    const multiContainer = $("multiday-slots-container");
    const shiftsContainer = $("plan-shifts-container");

    if (tabToday && tabMulti) {
      tabToday.addEventListener("click", () => {
        tabToday.className = "btn btn-sm btn-primary flex-1";
        tabToday.setAttribute("aria-selected", "true");
        tabMulti.className = "btn btn-sm btn-secondary flex-1";
        tabMulti.setAttribute("aria-selected", "false");
        if (multiContainer) multiContainer.hidden = true;
        if (shiftsContainer) shiftsContainer.hidden = false;
        if ($("plan-savings-pill")) {
          $("plan-savings-pill").textContent = `▲ Saves ${Math.round(this.todaySavings || 340)} µg`;
        }
      });
      tabMulti.addEventListener("click", () => {
        tabMulti.className = "btn btn-sm btn-primary flex-1";
        tabMulti.setAttribute("aria-selected", "true");
        tabToday.className = "btn btn-sm btn-secondary flex-1";
        tabToday.setAttribute("aria-selected", "false");
        if (multiContainer) multiContainer.hidden = false;
        if (shiftsContainer) shiftsContainer.hidden = true;
        if ($("plan-savings-pill")) {
          const sVal = this.fourDayData?.top_slots?.[0]?.savings_ug || 420;
          $("plan-savings-pill").textContent = `▲ Saves ${Math.round(sVal)} µg (4-Day Best)`;
        }
      });
    }

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
        transit_metro: { title: "Metro Commute", micro_env: "transit_metro", activity: "sedentary" },
        walk: { title: "Walk", micro_env: "outdoor", activity: "light" },
        run: { title: "Run", micro_env: "outdoor", activity: "moderate" }
      }[actType] || { title: "Activity", micro_env: "outdoor", activity: "moderate" };

      await this.fetchFourDayForecast(actType, dur);

      try {
        const resp = await fetch("/api/v1/plan", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            profile: this.familyProfile, member_id: mid,
            flexible_activities: [{
              id: `act_${actType}`, member_id: mid, title: actConfig.title,
              duration_hours: Math.max(1, Math.round(dur / 60)), earliest_start_hour: 11, latest_start_hour: 17,
              micro_env: actConfig.micro_env, activity: actConfig.activity,
              usual_start_hour: actType === "market_shopping" ? 10 : (actType === "park_terrace" ? 17 : 7)
            }]
          })
        });
        if (resp.ok) {
          const res = await resp.json();
          const shift = (res.data?.shifts || [])[0];
          const totalSavings = res.data?.total_savings_ug || 0;
          this.todaySavings = totalSavings;
          if (shift) {
            const h = $("plan-shift-hours"), d = $("plan-shift-delta");
            const pmStr = shift.outdoor_pm25_at_optimized ? ` (${Math.round(shift.outdoor_pm25_at_optimized)} µg/m³)` : "";
            if (h) h.textContent = `${shift.usual_start_hour}:00 → ${shift.optimized_start_hour}:00${pmStr}`;
            const sVal = Math.round(shift.savings_ug || totalSavings);
            const pVal = Math.round(shift.percent_savings || 0);
            if (d) d.textContent = `▲ Saves ${sVal} µg PM2.5 (${pVal}%)`;
          }
          if ($("plan-savings-pill")) $("plan-savings-pill").textContent = `▲ Saves ${Math.round(totalSavings)} µg`;
        }
      } catch {}
    });

    const applyBtn = $("btn-apply-plan");
    if (applyBtn) {
      applyBtn.addEventListener("click", () => {
        const isHi = this.currentLang === "hi";
        applyBtn.textContent = isHi ? "✓ योजना में जोड़ा गया" : "✓ Added to plan";
        applyBtn.className = "btn btn-sm btn-secondary";
        setTimeout(() => {
          applyBtn.textContent = isHi ? "योजना में जोड़ें" : "Add to plan";
          applyBtn.className = "btn btn-sm btn-primary";
        }, 2000);
      });
    }

    const icsBtn = $("btn-export-ics");
    if (icsBtn) {
      icsBtn.addEventListener("click", () => {
        const act = $("plan-activity-type")?.value || "walk", loc = this.familyProfile.location?.city_name || "Delhi NCR";
        const pad = (n) => String(n).padStart(2, "0"), toUtc = (d) => `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}00Z`;
        const start = new Date(Date.now() + 86400000); start.setHours(13, 0, 0, 0);
        const end = new Date(start.getTime() + 3600000);
        const ics = `BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//HawaKhata//Air Passbook//EN\r\nBEGIN:VEVENT\r\nUID:hk-${Date.now()}@hawakhata.org\r\nDTSTAMP:${toUtc(new Date())}\r\nDTSTART:${toUtc(start)}\r\nDTEND:${toUtc(end)}\r\nSUMMARY:HawaKhata Clean Window: ${act}\r\nDESCRIPTION:Scheduled in clean air window in ${loc}. Expected PM2.5 avoidance up to 45%.\r\nLOCATION:${loc}\r\nSTATUS:CONFIRMED\r\nEND:VEVENT\r\nEND:VCALENDAR`;
        const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" }), url = URL.createObjectURL(blob), a = document.createElement("a");
        a.href = url; a.download = "hawakhata-routine.ics"; document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
        const orig = icsBtn.textContent; icsBtn.textContent = this.currentLang === "hi" ? "✓ सहेज लिया गया" : "✓ Saved .ics"; setTimeout(() => { icsBtn.textContent = orig; }, 2000);
      });
    }
  }

  _bindIndoor() {
    const vRng = $("indoor-vol-range"), cRng = $("indoor-cadr-range"), wSel = $("indoor-window-select"), pBtn = $("btn-toggle-purifier");
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
        const resp = await fetch("/api/v1/indoor/simulate", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            location: this.familyProfile.location,
            room: {
              name: "Living Room",
              volume_m3: vol,
              purifier_cadr_m3_per_h: cadr,
              purifier_on_hours: on ? Array.from({length: 24}, (_, i) => i) : [],
              windows_open_hours: isWindowOpen ? [12, 13, 14] : []
            },
            sources: this.familyProfile.sources || []
          })
        });
        if (resp.ok) {
          const res = await resp.json();
          const d = res.data || {};
          const sim = d.simulation || {};
          const meanPm = Math.round(sim.mean_pm25_ug_m3 || 42);
          const reqCadr = Math.round(d.purifier_recommendation?.required_cadr_m3_per_h || (vol * 5));
          const cleanPct = Math.max(0, Math.min(99, Math.round((1 - meanPm / Math.max(1, outPm)) * 100)));

          if ($("indoor-pm25-val")) $("indoor-pm25-val").textContent = `${meanPm} µg/m³`;
          if ($("indoor-preview-pm25")) $("indoor-preview-pm25").textContent = `${meanPm} µg/m³`;
          if ($("indoor-outdoor-val")) $("indoor-outdoor-val").textContent = `${outPm} µg/m³`;
          if ($("indoor-cadr-val")) $("indoor-cadr-val").textContent = `${reqCadr} m³/h`;
          if ($("indoor-clean-pct")) $("indoor-clean-pct").textContent = `▲ ${cleanPct}% Cleaner Air`;
          if (statusPill) statusPill.textContent = this.currentLang === "hi" ? "सिम्युलेटेड (इंजन)" : "Simulated (engine)";
        }
      } catch {
        if (statusPill) statusPill.textContent = "Simulated (offline)";
      }
    };

    const updatePreview = () => {
      const vol = parseFloat(vRng?.value || "60"), cadr = on ? parseFloat(cRng?.value || "300") : 0;
      const ach = wSel?.value === "sealed" ? 0.4 : (wSel?.value === "open" ? 2.5 : 0.8);
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
              "Accept-Language": this.currentLang || "en"
            },
            body: JSON.stringify({ profile: this.familyProfile })
          });
          if (resp.ok) {
            const digest = (await resp.json()).data?.digest_text || "";
            if (navigator.clipboard && navigator.clipboard.writeText) {
              await navigator.clipboard.writeText(digest);
            } else {
              const ta = document.createElement("textarea");
              ta.value = digest;
              document.body.appendChild(ta);
              ta.select();
              document.execCommand("copy");
              document.body.removeChild(ta);
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
    const petModal = $("modal-pet");
    const petClose = $("modal-pet-close");
    if (petBtn && petModal) {
      petBtn.addEventListener("click", () => {
        petModal.hidden = false;
        this._loadPetGuidance("dog");
      });
    }
    if (petClose && petModal) {
      petClose.addEventListener("click", () => { petModal.hidden = true; });
    }

    $$(".pet-tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        $$(".pet-tab-btn").forEach((b) => { b.className = "btn btn-sm btn-secondary flex-1 pet-tab-btn"; });
        btn.className = "btn btn-sm btn-primary flex-1 pet-tab-btn";
        const sp = btn.getAttribute("data-species") || "dog";
        this._loadPetGuidance(sp);
      });
    });
  }

  async _loadPetGuidance(species) {
    try {
      const resp = await fetch("/api/v1/pets/guidance", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ species, location: this.familyProfile.location })
      });
      if (resp.ok) {
        const d = (await resp.json()).data || {};
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
      }
    } catch {}
  }

  _bindChat() {
    const drawer = $("ask-drawer"), input = $("ask-input"), log = $("ask-chat-msgs");
    const on = (id, fn) => { const b = $(id); if (b) b.addEventListener("click", fn); };
    on("fab-ask-btn", () => { if (drawer) drawer.hidden = false; if (input) input.focus(); });
    on("ask-close-btn", () => { if (drawer) drawer.hidden = true; });

    const form = $("ask-form");
    if (!form || !input || !log) return;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const msg = input.value.trim();
      if (!msg) return;
      const add = (cls, txt) => {
        const d = el("div", `msg ${cls}`, txt);
        log.appendChild(d); log.scrollTop = log.scrollHeight; return d;
      };
      add("user", msg);
      input.value = "";
      const aMsg = add("assistant", "...");
      try {
        const resp = await fetch("/api/v1/chat", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: msg, session_id: this.sessionId, language: this.currentLang, profile: this.familyProfile }),
        });
        const json = await resp.json();
        if (json.data) {
          this.sessionId = json.data.session_id;
          this._renderMarkdown(aMsg, json.data.reply);
          const modeLbl = json.data.degraded ? "Deterministic Fallback" : "Live Gemini Propose";
          const pillCls = json.data.degraded ? "warn" : "saved";
          const tag = (json.data.grounded ? "✓ Grounded · " : "") + modeLbl;
          log.appendChild(el("span", `pill-status ${pillCls} text-xs mt-05 block`, tag));
        } else {
          aMsg.textContent = "Unable to process request.";
        }
      } catch {
        aMsg.textContent = "Offline. Showing local verified air recommendations.";
      }
      log.scrollTop = log.scrollHeight;
    });
  }

  _renderMarkdown(container, text) {
    container.textContent = '';
    if (!text) return;
    const lines = text.split('\n');
    let currentUl = null;
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) { currentUl = null; continue; }
      if (trimmed.startsWith('* ') || trimmed.startsWith('- ')) {
        if (!currentUl) { currentUl = document.createElement('ul'); container.appendChild(currentUl); }
        const li = document.createElement('li');
        li.textContent = '';
        this._appendBoldText(li, trimmed.slice(2));
        currentUl.appendChild(li);
      } else {
        currentUl = null;
        const p = document.createElement('p');
        p.textContent = '';
        this._appendBoldText(p, trimmed);
        container.appendChild(p);
      }
    }
  }

  _appendBoldText(container, text) {
    const parts = text.split(/\*\*(.*?)\*\*/g);
    parts.forEach((part, i) => {
      if (i % 2 === 1) {
        const strong = document.createElement('strong');
        strong.textContent = part;
        container.appendChild(strong);
      } else if (part) {
        container.appendChild(document.createTextNode(part));
      }
    });
  }

  _bindSwaps() {
    const rng = $("mohalla-range"), chks = $$(".swap-chk");
    const cLbl = $("mohalla-count-label"), cVal = $("community-emissions-val"), hVal = $("household-dose-saved"), sPill = $("swaps-avoided-pill");

    const update = () => {
      let co2 = 0, pm = 0;
      chks.forEach((c) => {
        const row = c.closest(".balance-row");
        const pill = row ? row.querySelector(".pill-status") : null;
        if (c.checked) {
          co2 += parseFloat(c.getAttribute("data-co2") || "0");
          pm += parseFloat(c.getAttribute("data-pm25") || "0");
          if (pill) {
            pill.textContent = this.currentLang === "hi" ? "सक्रिय" : "Active";
            pill.className = "pill-status saved";
          }
        } else {
          if (pill) {
            pill.textContent = this.currentLang === "hi" ? "सक्षम करें" : "Enable";
            pill.className = "pill-status";
          }
        }
      });
      const count = parseInt(rng?.value || "50", 10);
      const isHi = this.currentLang === "hi";
      if (cLbl) cLbl.textContent = `${count} ${isHi ? "घर" : "homes"}`;
      if (cVal) cVal.textContent = `${(count * co2).toFixed(1)} kg`;
      if (hVal) hVal.textContent = `${Math.round(pm)} µg`;
      if (sPill) sPill.textContent = `▲ ${co2.toFixed(1)} kg ${isHi ? "बचाया गया" : "avoided"}`;
    };

    if (rng) rng.addEventListener("input", update);
    chks.forEach((c) => c.addEventListener("change", update));
    update();
  }

  _bindHours() {
    const s = $("hours-strip");
    if (!s) return;
    const m = { s: "severe", v: "very-poor", p: "poor", o: "moderate" };
    const cats = "ssvvvpppoooooooppvvsssss".split("").map((c) => m[c]);
    s.replaceChildren();
    for (let h = 0; h < 24; h++) {
      s.appendChild(el("div", `hour-cell ${cats[h]}${h >= 12 && h <= 15 ? " highlight" : ""}`, `${h}`));
    }
  }
}

document.addEventListener("DOMContentLoaded", () => { window.hawaKhata = new HawaKhataApp(); });
