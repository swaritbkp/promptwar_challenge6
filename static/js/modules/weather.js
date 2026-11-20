// Native ES Module: live weather tiles, 4-day cards, GRAP pill, source pill,
// Morning/Afternoon/Evening strip, Right-Now action strip and the spoken morning brief.
// Every number shown here arrives from the backend engine; this module only formats it.

import { $, el, setText, t, catClass } from "./dom.js";

const REGIME_KEYS = {
  "Afternoon Mixing Lift": "disp_mixing",
  "Inversion Trap": "disp_inversion",
  "Stagnant Air": "disp_stagnant",
  "Wind Clearing": "disp_wind",
  "Rain Washout": "disp_rain",
};

const regimeName = (regime, ctx) => (ctx.isHi ? t(ctx.s, REGIME_KEYS[regime], regime) : regime);

export function renderLiveWeather(w, ctx) {
  if (!w) return;
  const fmt = (v, d = 1) => (typeof v === "number" ? v.toFixed(d) : "—");
  setText("weather-temp-val", `${fmt(w.temperature_c)} °C`);
  setText("weather-humidity-val", `${fmt(w.humidity_pct, 0)} %`);
  setText("weather-wind-val", `${fmt(w.wind_speed_kmh)} km/h`);
  setText("weather-blh-val", `${fmt(w.boundary_layer_height_m, 0)} m`);

  const pill = $("live-weather-regime-pill");
  if (pill && w.dispersion_regime) {
    pill.textContent = `${ctx.isHi ? "प्रसार" : "Dispersion"}: ${regimeName(w.dispersion_regime, ctx)}`;
    pill.className = `pill-status ${w.dispersion_regime === "Inversion Trap" ? "debit" : "saved"}`;
  }
  const wind = fmt(w.wind_speed_kmh);
  const blh = fmt(w.boundary_layer_height_m, 0);
  setText(
    "weather-smog-driver-explanation",
    ctx.isHi
      ? `हवा ${wind} km/h और मिक्सिंग परत ${blh} m: ${regimeName(w.dispersion_regime, ctx)} — कम हवा व नीची परत धुआँ ज़मीन के पास रोकती है।`
      : `${wind} km/h wind + ${blh} m boundary layer: ${w.physical_explanation}`
  );
}

export function renderFourDayCards(days, ctx) {
  const grid = $("four-day-cards-grid");
  if (!grid || !Array.isArray(days)) return;
  grid.replaceChildren();
  days.forEach((day) => {
    const cls = catClass(day.naqi_category.toLowerCase().replace(/ /g, "_"));
    const catName = ctx.isHi ? t(ctx.s, `cat_${cls.replace(/-/g, "_")}`, day.naqi_category) : day.naqi_category;
    const dayName = ctx.isHi ? t(ctx.s, day.day_label.toLowerCase().replace(" ", "_"), day.day_label) : day.day_label;
    const card = el("div", "outlook-card");
    card.append(
      el("div", "font-bold text-xs", dayName),
      el("span", `pill-status ${cls}`, `AQI ${day.peak_aqi} · ${catName}`),
      el("div", "text-xs font-semibold text-saved", `▲ ${day.cleanest_window_start}–${day.cleanest_window_end} · ${Math.round(day.cleanest_pm25)} µg/m³`),
      el("div", "text-xs stat-lbl", `${regimeName(day.dispersion_regime, ctx)} · ${day.wind_kmh} km/h`),
      el("div", "text-xs text-muted", `BLH ${Math.round(day.blh_m)} m · P90 ${Math.round(day.uncertainty_p90)}`)
    );
    grid.append(card);
  });
}

/** Data-source pill: "Source: Open-Meteo Live AQ · PM2.5 184 / PM10 262 µg/m³ · Updated 18:30 IST". */
export function renderSourcePill(d, ctx) {
  const pill = $("data-source-pill");
  if (!pill || d.current_pm25 == null) return;
  const pm10 = d.current_pm10 != null ? ` / PM10 ${Math.round(d.current_pm10)}` : "";
  const updated = d.fetched_at_ist ? ` · ${ctx.isHi ? "अपडेट" : "Updated"} ${d.fetched_at_ist}` : "";
  pill.textContent = `${ctx.isHi ? "स्रोत" : "Source"}: ${d.data_source} · PM2.5 ${Math.round(d.current_pm25)}${pm10} µg/m³${updated}`;
  pill.className = `pill-status text-xs ${d.data_mode === "fixture" ? "warn" : "saved"}`;
}

/** Clickable GRAP Stage pill; toggles an advisory list (EN / HI) below it. */
export function renderGrap(grap, ctx) {
  const btn = $("grap-pill");
  const box = $("grap-details");
  if (!btn || !box || !grap) return;
  btn.textContent = `🚦 ${ctx.isHi ? grap.label_hi : grap.label_en} · AQI ${grap.aqi}`;
  btn.className = `btn btn-sm grap-pill grap-${grap.code.toLowerCase()}`;
  const list = el("ul", "flex-col gap-05 pl-1");
  (ctx.isHi ? grap.advisories_hi : grap.advisories_en).forEach((a) => list.append(el("li", null, a)));
  box.replaceChildren(list, el("p", "stat-lbl text-xs mt-05", ctx.isHi ? grap.scope_note_hi : grap.scope_note_en));
}

export function bindGrapToggle() {
  const btn = $("grap-pill");
  const box = $("grap-details");
  if (!btn || !box) return;
  btn.addEventListener("click", () => {
    box.hidden = !box.hidden;
    btn.setAttribute("aria-expanded", String(!box.hidden));
  });
}

/** Morning (06–11h) / Afternoon (12–16h) / Evening (17–21h) strip. */
export function renderDayParts(parts, ctx, containerId) {
  const wrap = $(containerId);
  if (!wrap || !Array.isArray(parts)) return;
  wrap.replaceChildren();
  parts.forEach((p) => {
    const cls = catClass(p.category_code);
    const cat = ctx.isHi ? t(ctx.s, `cat_${p.category_code}`, p.category_label) : p.category_label;
    const card = el("div", "daypart-card");
    card.append(
      el("div", "font-bold text-xs", `${ctx.isHi ? p.label_hi : p.label_en} · ${String(p.start_hour).padStart(2, "0")}–${p.end_hour}h`),
      el("span", `pill-status ${cls}`, `PM2.5 ${Math.round(p.mean_pm25)} · AQI ${p.aqi} · ${cat}`),
      el("div", "text-xs stat-lbl", ctx.isHi ? p.guidance_hi : p.guidance_en)
    );
    wrap.append(card);
  });
}

/** Right-Now action strip driven by the same live PM2.5/AQI as the header chip. */
export function renderActionStrip(pm, aqi, flush, ctx) {
  const wrap = $("action-strip-pills");
  if (!wrap || pm == null) return;
  setText("action-strip-pm", `${ctx.isHi ? "लाइव" : "Live"}: ${pm} µg/m³ · AQI ${aqi}`);
  const level = pm > 120 ? "debit" : pm > 60 ? "warn" : "saved";
  const pick = (hi3, en3) => (ctx.isHi ? hi3 : en3)[level === "debit" ? 0 : level === "warn" ? 1 : 2];
  const hour = new Date().getHours();
  const flushStart = flush ? parseInt(flush.start_hour, 10) : -1;
  const flushNow = flush && flush.day_index === 0 && hour === flushStart;
  const flushLbl = flush ? `${flush.day_label} ${flush.start_hour}` : "—";
  const pills = [
    [level, pick(["😷 मास्क: बाहर N95 अनिवार्य", "😷 मास्क: N95 अनुशंसित", "😊 मास्क: वैकल्पिक"], ["😷 Mask: N95 Required Outdoors", "😷 Mask: N95 Recommended", "😊 Mask: Optional"])],
    [flushNow ? "saved" : "", flushNow
      ? (ctx.isHi ? "🪟 खिड़कियाँ: अभी 1 घंटा खोलें" : "🪟 Windows: Open 1h Now (Safe Flush)")
      : (ctx.isHi ? `🪟 खिड़कियाँ बंद · फ्लश ${flushLbl}` : `🪟 Windows Sealed · Flush ${flushLbl}`)],
    [level, pick(["🌀 प्यूरीफायर: हाई / निरंतर", "🌀 प्यूरीफायर: ऑटो / मीडियम", "🌀 प्यूरीफायर: लो / इको"], ["🌀 Purifier: High / Continuous", "🌀 Purifier: Auto / Medium", "🌀 Purifier: Low / Eco"])],
    [level, pick(["🐾 पेट्स/सैर: 10 मिनट से कम", "🐾 पेट्स/सैर: स्वच्छ समय में", "🌳 बाहर: खेल व सैर सुरक्षित"], ["🐾 Outdoor/Pets: 10-min Walks Only", "🐾 Outdoor/Pets: Use Clean Window", "🌳 Outdoor: Safe for Play & Walks"])],
  ];
  wrap.replaceChildren(...pills.map(([cls, txt]) => el("span", `pill-status ${cls}`, txt)));
}

/** 🔊 Spoken morning brief via the browser-native Web Speech API (no network calls). */
export class VoiceBrief {
  constructor(getScript, getLang) {
    this.getScript = getScript;
    this.getLang = getLang;
    this.btn = $("btn-voice-brief");
    this.synth = "speechSynthesis" in window ? window.speechSynthesis : null;
    if (!this.btn) return;
    if (!this.synth || typeof window.SpeechSynthesisUtterance !== "function") {
      this.btn.hidden = true;
      return;
    }
    this.btn.addEventListener("click", () => (this.synth.speaking ? this.stop() : this.speak()));
    this.render(false);
  }

  render(speaking) {
    if (!this.btn) return;
    const hi = this.getLang() === "hi";
    this.btn.textContent = speaking ? (hi ? "⏹ रोकें" : "⏹ Stop") : (hi ? "🔊 सुनें" : "🔊 Listen");
    this.btn.setAttribute("aria-pressed", String(speaking));
  }

  speak() {
    const lang = this.getLang() === "hi" ? "hi-IN" : "en-IN";
    const u = new window.SpeechSynthesisUtterance(this.getScript());
    u.lang = lang;
    u.rate = 1.0;
    const voice = this.synth.getVoices().find((v) => v.lang === lang || v.lang.startsWith(lang.slice(0, 2)));
    if (voice) u.voice = voice;
    u.onend = () => this.render(false);
    u.onerror = () => this.render(false);
    this.synth.cancel();
    this.synth.speak(u);
    this.render(true);
  }

  stop() {
    if (this.synth) this.synth.cancel();
    this.render(false);
  }
}

/** Compose the 15–20 s spoken summary from already-computed engine values. */
export function composeVoiceScript(st, isHi) {
  const d = st.fourDayData || {};
  const grap = d.grap ? (isHi ? d.grap.label_hi : d.grap.label_en) : "";
  const flush = d.safe_house_flush ? `${d.safe_house_flush.start_hour}` : "—";
  const pm = Math.round(st.currentOutdoorPm25 || 0);
  const action = pm > 120
    ? (isHi ? "बाहर N95 मास्क पहनें और प्यूरीफायर तेज़ चलाएँ" : "wear an N95 outdoors and run the purifier on high")
    : pm > 60
    ? (isHi ? "संवेदनशील सदस्य बाहर कम समय रहें" : "keep sensitive members' outdoor time short")
    : (isHi ? "आज बाहर की गतिविधियाँ सुरक्षित हैं" : "outdoor activities are fine today");
  return isHi
    ? `हवा खाता ब्रीफ़। ${st.city} में अभी AQI ${st.currentAQI} है, PM2.5 ${pm}। ${grap}। सैर का सबसे सुरक्षित समय ${st.cleanestWindow}। घर हवादार करने का सुरक्षित समय ${flush}। आज की मुख्य सलाह: ${action}।`
    : `HawaKhata air brief. ${st.city} AQI is ${st.currentAQI} right now, PM2.5 ${pm}. ${grap}. Safest walk window: ${st.cleanestWindow}. Safe house-flush hour: ${flush}. Top action: ${action}.`;
}
