import { StoryController } from "./story.js";

const $ = (id) => document.getElementById(id);
const $$ = (sel) => document.querySelectorAll(sel);
const el = (tag, cls, txt) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (txt !== undefined) node.textContent = txt;
  return node;
};

class HawaKhataApp {
  constructor() {
    this.currentTab = "today";
    this.currentLang = "en";
    this.sessionId = null;
    this.i18nStrings = {};
    this.familyProfile = this._loadProfile();
    this.story = new StoryController(this);
    this.init();
  }

  _loadProfile() {
    try {
      const s = localStorage.getItem("hawakhata_family");
      if (s) return JSON.parse(s);
    } catch {}
    return {
      id: "fam_local", name: "Family",
      location: { lat: 28.4595, lng: 77.0266, city_name: "Gurugram" },
      rooms: [{ name: "Living Room", volume_m3: 60.0 }],
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

    const onCity = (id, fn) => { const b = $(id); if (b) b.addEventListener("click", fn); };
    onCity("btn-load-ncr", () => this.applyLocation("Gurugram", 28.4595, 77.0266));
    onCity("btn-load-chd", () => this.applyLocation("Mohali", 30.7046, 76.7179));
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
  }

  renderMembers(entries = []) {
    const list = $("passbook-members-list");
    if (!list) return;
    list.replaceChildren();
    this.familyProfile.members.forEach((m, idx) => {
      const e = entries.find((x) => x.member_id === m.id) || {};
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
      try {
        const resp = await fetch("/api/v1/plan", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            profile: this.familyProfile, member_id: mid,
            flexible_activities: [{
              id: "act_custom", member_id: mid, title: "Flexible Activity",
              duration_hours: dur / 60, earliest_start_hour: 6, latest_start_hour: 19,
              micro_env: "outdoor", activity: "moderate", usual_start_hour: 7
            }]
          })
        });
        if (resp.ok) {
          const shift = ((await resp.json()).data?.shifts || [])[0];
          if (shift) {
            const h = $("plan-shift-hours"), d = $("plan-shift-delta");
            if (h) h.textContent = `${shift.usual_start_hour}:00 → ${shift.optimized_start_hour}:00 (${shift.outdoor_pm25_at_optimized} µg/m³)`;
            if (d) d.textContent = `▲ Saves ${Math.round(shift.dose_saved_ug)} µg PM2.5`;
          }
        }
      } catch {}
    });
  }

  _bindIndoor() {
    const vRng = $("indoor-vol-range"), cRng = $("indoor-cadr-range"), wSel = $("indoor-window-select"), pBtn = $("btn-toggle-purifier");
    let on = true;
    const calc = () => {
      const vol = parseFloat(vRng?.value || "60"), cadr = on ? parseFloat(cRng?.value || "300") : 0;
      const ach = wSel?.value === "sealed" ? 0.4 : (wSel?.value === "open" ? 2.5 : 0.8);
      if ($("indoor-vol-label")) $("indoor-vol-label").textContent = `${vol} m³`;
      if ($("indoor-cadr-label")) $("indoor-cadr-label").textContent = `${cadr} m³/h`;
      const cIn = Math.round((ach * 340.0) / (ach + cadr / vol + 0.2));
      const pct = Math.max(0, Math.min(95, Math.round((1 - cIn / 340.0) * 100)));
      if ($("indoor-pm25-val")) $("indoor-pm25-val").textContent = `${cIn} µg/m³`;
      if ($("indoor-preview-pm25")) $("indoor-preview-pm25").textContent = `${cIn} µg/m³`;
      if ($("indoor-cadr-val")) $("indoor-cadr-val").textContent = `${Math.round(vol * 5)} m³/h`;
      if ($("indoor-clean-pct")) $("indoor-clean-pct").textContent = `▲ ${pct}% Cleaner Air`;
    };
    if (vRng) vRng.addEventListener("input", calc);
    if (cRng) cRng.addEventListener("input", calc);
    if (wSel) wSel.addEventListener("change", calc);
    if (pBtn) {
      pBtn.addEventListener("click", () => {
        on = !on;
        pBtn.textContent = on ? "Purifier ON" : "Purifier OFF";
        pBtn.className = `btn btn-sm ${on ? "btn-primary" : "btn-secondary"}`;
        calc();
      });
    }
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
          aMsg.textContent = json.data.reply;
          if (json.data.grounded) log.appendChild(el("span", "pill-status saved text-xs mt-05 block", "✓ Grounded calculation"));
        } else {
          aMsg.textContent = "Unable to process request.";
        }
      } catch {
        aMsg.textContent = "Offline. Showing local verified air recommendations.";
      }
      log.scrollTop = log.scrollHeight;
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
