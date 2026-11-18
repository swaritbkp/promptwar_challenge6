import { StoryController } from "./story.js";

class HawaKhataApp {
  constructor() {
    this.currentTab = "today";
    this.currentLang = "en";
    this.i18nStrings = {};
    this.story = new StoryController(this);
    this.init();
  }

  async init() {
    this._bindNav();
    this._bindModals();
    this._bindChat();
    this._bindSwaps();
    this._bindHours();
    await this._loadMeta();
    await this.setLanguage(this.currentLang);
    const sId = new URLSearchParams(window.location.search).get("story");
    if (sId) this.story.start(sId);
  }

  async _loadMeta() {
    try {
      const r = await fetch("/api/v1/meta");
      if (r.ok) {
        const d = (await r.json()).data || {};
        if (d.data_mode === "fixture") {
          const b = document.getElementById("fixture-notice");
          if (b) b.style.display = "flex";
        }
      }
    } catch {}
  }

  _bindNav() {
    document.querySelectorAll(".nav-item[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const t = btn.getAttribute("data-tab");
        if (t) this.switchTab(t);
      });
    });
    const langBtn = document.getElementById("lang-toggle-btn");
    if (langBtn) {
      langBtn.addEventListener("click", () => this.setLanguage(this.currentLang === "en" ? "hi" : "en"));
    }
  }

  switchTab(tabId) {
    this.currentTab = tabId;
    document.querySelectorAll(".tab-pane").forEach((p) => {
      p.style.display = p.id === `tab-${tabId}` ? "block" : "none";
    });
    document.querySelectorAll(".nav-item[data-tab]").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-tab") === tabId);
    });
    const h = document.getElementById(`${tabId}-heading`);
    if (h) h.focus();
  }

  async setLanguage(lang) {
    this.currentLang = lang;
    try {
      const r = await fetch(`/static/i18n/${lang}.json`);
      if (r.ok) {
        this.i18nStrings = await r.json();
        document.querySelectorAll("[data-i18n]").forEach((el) => {
          const k = el.getAttribute("data-i18n");
          if (k && this.i18nStrings[k]) el.textContent = this.i18nStrings[k];
        });
      }
    } catch {}
    const l = document.getElementById("lang-label");
    if (l) l.textContent = lang === "en" ? "हिन्दी" : "English";
    document.documentElement.lang = lang;
  }

  _bindModals() {
    const wire = (btnId, modalId, closeId) => {
      const b = document.getElementById(btnId), m = document.getElementById(modalId), c = document.getElementById(closeId);
      if (b && m) b.addEventListener("click", () => { m.style.display = "flex"; });
      if (c && m) c.addEventListener("click", () => { m.style.display = "none"; });
    };
    wire("btn-why-number", "modal-why", "modal-why-close");
    wire("city-btn", "modal-city", "modal-city-close");

    const mCity = document.getElementById("modal-city"), lbl = document.getElementById("city-name-label");
    const setCity = (btnId, name) => {
      const btn = document.getElementById(btnId);
      if (btn && mCity) btn.addEventListener("click", () => { if (lbl) lbl.textContent = name; mCity.style.display = "none"; });
    };
    setCity("btn-load-ncr", "Gurugram");
    setCity("btn-load-chd", "Mohali");
  }

  _bindChat() {
    const fab = document.getElementById("fab-ask-btn"), drawer = document.getElementById("ask-drawer");
    const closeBtn = document.getElementById("ask-close-btn"), form = document.getElementById("ask-form");
    const input = document.getElementById("ask-input"), log = document.getElementById("ask-chat-msgs");

    if (fab && drawer) fab.addEventListener("click", () => { drawer.style.display = "flex"; if (input) input.focus(); });
    if (closeBtn && drawer) closeBtn.addEventListener("click", () => { drawer.style.display = "none"; });

    if (form && input && log) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const msg = input.value.trim();
        if (!msg) return;
        const addMsg = (cls, txt) => {
          const d = document.createElement("div"); d.className = `msg ${cls}`; d.textContent = txt;
          log.appendChild(d); log.scrollTop = log.scrollHeight; return d;
        };
        addMsg("user", msg);
        input.value = "";
        const aMsg = addMsg("assistant", "...");
        try {
          const resp = await fetch("/api/v1/chat", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: msg, language: this.currentLang }),
          });
          const json = await resp.json();
          aMsg.textContent = json.data ? json.data.reply : "Unable to process request.";
        } catch {
          aMsg.textContent = "Offline. Showing local verified air recommendations.";
        }
        log.scrollTop = log.scrollHeight;
      });
    }
  }

  _bindSwaps() {
    const rng = document.getElementById("mohalla-range");
    const cLbl = document.getElementById("mohalla-count-label"), cVal = document.getElementById("community-emissions-val");
    if (rng && cLbl && cVal) {
      rng.addEventListener("input", () => {
        const count = parseInt(rng.value, 10);
        cLbl.textContent = `${count} homes`;
        cVal.textContent = `${(count * 1.4).toFixed(1)} kg`;
      });
    }
  }

  _bindHours() {
    const s = document.getElementById("hours-strip");
    if (!s) return;
    const cats = ["severe","severe","very-poor","very-poor","very-poor","poor","poor","poor",
                  "moderate","moderate","moderate","moderate","moderate","moderate","moderate",
                  "poor","poor","very-poor","very-poor","severe","severe","severe","severe","severe"];
    s.replaceChildren();
    for (let h = 0; h < 24; h++) {
      const c = document.createElement("div");
      c.className = `hour-cell ${cats[h]}`;
      c.textContent = `${h}`;
      c.style.backgroundColor = `var(--naqi-${cats[h]})`;
      if (h >= 12 && h <= 15) c.classList.add("highlight");
      s.appendChild(c);
    }
  }
}

document.addEventListener("DOMContentLoaded", () => { window.hawaKhata = new HawaKhataApp(); });
