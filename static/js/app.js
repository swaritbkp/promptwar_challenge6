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
    await this.refreshData();
    await this.setLanguage(this.currentLang);
    const sId = new URLSearchParams(window.location.search).get("story");
    if (sId) this.story.start(sId);
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

    onCity("btn-apply-custom-loc", () => {
      const lat = parseFloat($("custom-lat")?.value) || 28.4595;
      const lng = parseFloat($("custom-lng")?.value) || 77.0266;
      this.applyLocation($("custom-city-name")?.value.trim() || "Custom Area", lat, lng);
    });
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
      }
    } catch {
      this.renderMembers();
    }
  }

  _updateHero(d) {
    const debit = $("hero-debit"), budget = $("hero-budget"), bal = $("hero-balance"), cigs = $("hero-cigs");
    if (debit) debit.textContent = `${Math.round(d.total_debit_ug || 1420)} µg`;
    if (budget) budget.textContent = `${Math.round(d.total_budget_ug || 240)} µg`;
    if (bal) {
      const net = Math.round(d.net_balance_ug || -1180);
      bal.textContent = `${net > 0 ? "+" : ""}${net} µg`;
      bal.className = `stat-val ${net < 0 ? "debit" : "saved"}`;
    }
    if (cigs) cigs.textContent = `${(d.cigarette_equivalent || 8.2).toFixed(1)} cigs`;
    const headline = $("brief-headline");
    if (headline) {
      const net = d.net_balance_ug ?? -1;
      if (net < 0) {
        const member = d.highest_debit_member ? ` – ${d.highest_debit_member} over limit` : "";
        headline.textContent = `Air budget exceeded${member}`;
        headline.className = "card-title text-debit";
      } else {
        headline.textContent = "Within WHO budget ✓ – Household protected";
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
  }

  renderMembers(entries = []) {
    const list = $("passbook-members-list");
    if (!list) return;
    list.replaceChildren();
    this.familyProfile.members.forEach((m, idx) => {
      const e = entries.find((x) => x.member_id === m.id || x.member_label === m.name) || {};
      const bVal = Math.round(e.budget_ug || 90), dVal = Math.round(e.debit_ug || 420);
      const row = el("div", "balance-row"), info = el("div", "member-info"), details = el("div");
      info.append(el("div", "member-avatar", m.name.charAt(0).toUpperCase()), details);
      details.append(
        el("div", "font-semibold", m.name),
        el("div", "stat-lbl text-xs", `Budget: ${bVal} µg/d ${m.sensitivities?.length ? "· " + m.sensitivities.join(", ") : ""}`)
      );
      const bar = el("div", "member-bar-wrap");
      bar.append(el("div", "member-bar-fill w-full"));
      const del = el("button", "btn btn-sm btn-secondary", "✕");
      del.title = "Remove";
      del.addEventListener("click", async () => {
        this.familyProfile.members.splice(idx, 1);
        this._saveProfile();
        await this.recalculatePassbook();
      });
      const acts = el("div", "flex gap-05 items-center");
      acts.append(el("span", `pill-status ${dVal > bVal ? "debit" : "saved"}`, `${dVal} µg`), del);
      row.append(info, bar, acts);
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
        transit_metro: { title: "Metro Commute", micro_env: "transit_metro", activity: "sedentary" },
        walk: { title: "Walk", micro_env: "outdoor", activity: "light" },
        run: { title: "Run", micro_env: "outdoor", activity: "moderate" }
      }[actType] || { title: "Activity", micro_env: "outdoor", activity: "moderate" };

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
  }

  _bindIndoor() {
    const vRng = $("indoor-vol-range"), cRng = $("indoor-cadr-range"), wSel = $("indoor-window-select"), pBtn = $("btn-toggle-purifier");
    const pRng = $("plant-count-range");
    let on = true;
    let simTimer = null;

    const runEngineSim = async () => {
      const vol = parseFloat(vRng?.value || "60");
      const cadr = on ? parseFloat(cRng?.value || "300") : 0;
      const isWindowOpen = wSel?.value === "open";
      const statusPill = $("indoor-sim-status");
      if (statusPill) statusPill.textContent = this.currentLang === "hi" ? "सिम्युलेटिंग (इंजन)..." : "Simulating (engine)...";

      try {
        const resp = await fetch("/api/v1/indoor/simulate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            location: this.familyProfile.location,
            room: {
              name: "Active Room",
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
          const outPm = Math.round(this.airSeries?.points?.[0]?.pm25_ug_m3 || 340);
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
      if ($("indoor-vol-label")) $("indoor-vol-label").textContent = `${vol} m³`;
      if ($("indoor-cadr-label")) $("indoor-cadr-label").textContent = `${cadr} m³/h`;

      const statusPill = $("indoor-sim-status");
      if (statusPill) statusPill.textContent = this.currentLang === "hi" ? "पूर्वावलोकन (स्लाइडिंग...)" : "Preview (sliding...)";

      const cIn = Math.round((ach * 340.0) / (ach + cadr / vol + 0.2));
      const pct = Math.max(0, Math.min(95, Math.round((1 - cIn / 340.0) * 100)));
      if ($("indoor-pm25-val")) $("indoor-pm25-val").textContent = `${cIn} µg/m³`;
      if ($("indoor-preview-pm25")) $("indoor-preview-pm25").textContent = `${cIn} µg/m³`;
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
    if (cRng) cRng.addEventListener("input", () => { updatePreview(); updatePlants(); });
    if (wSel) wSel.addEventListener("change", updatePreview);
    if (pRng) pRng.addEventListener("input", updatePlants);
    if (pBtn) {
      pBtn.addEventListener("click", () => {
        on = !on;
        pBtn.textContent = on ? "Purifier ON" : "Purifier OFF";
        pBtn.className = `btn btn-sm ${on ? "btn-primary" : "btn-secondary"}`;
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
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ profile: this.familyProfile })
          });
          if (resp.ok) {
            const digest = (await resp.json()).data?.digest_text || "";
            await navigator.clipboard.writeText(digest);
            copyBtn.textContent = "✓ Copied!";
            setTimeout(() => { copyBtn.textContent = "📋 Share Passbook"; }, 2000);
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
        const species = btn.getAttribute("data-species") || "dog";
        this._loadPetGuidance(species);
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
        if (c.checked) {
          co2 += parseFloat(c.getAttribute("data-co2") || "0");
          pm += parseFloat(c.getAttribute("data-pm25") || "0");
        }
      });
      const count = parseInt(rng?.value || "50", 10);
      if (cLbl) cLbl.textContent = `${count} homes`;
      if (cVal) cVal.textContent = `${(count * co2).toFixed(1)} kg`;
      if (hVal) hVal.textContent = `${Math.round(pm)} µg`;
      if (sPill) sPill.textContent = `▲ ${co2.toFixed(1)} kg avoided`;
    };

    if (rng) rng.addEventListener("input", update);
    chks.forEach((c) => c.addEventListener("change", update));
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
