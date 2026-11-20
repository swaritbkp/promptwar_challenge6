// Native ES Module: passbook hero, member balance bars, Quick Scenario personas,
// and the Location modal (any-India search via backend proxy, metro chips, GPS).

import { api } from "./api.js";
import { $, el, svgEl, setText } from "./dom.js";

export function updateHero(d, app) {
  const hi = app.currentLang === "hi";
  setText("hero-debit", `${Math.round(d.total_debit_ug || 0)} µg`);
  setText("hero-budget", `${Math.round(d.total_budget_ug || 0)} µg`);
  const bal = $("hero-balance");
  if (bal) {
    const net = Math.round(d.net_balance_ug || 0);
    bal.textContent = `${net > 0 ? "+" : ""}${net} µg`;
    bal.className = `stat-val ${net < 0 ? "debit" : "saved"}`;
  }
  setText("hero-cigs", `${(d.cigarette_equivalent || 0).toFixed(1)} ${hi ? "सिगरेट" : "cigs"}`);

  const headline = $("brief-headline");
  if (headline) {
    const over = (d.net_balance_ug ?? -1) < 0;
    const who = d.highest_debit_member ? ` – ${d.highest_debit_member}` : "";
    headline.textContent = over
      ? (hi ? `एयर बजट पार हो गया${who}` : `Air budget exceeded${who}`)
      : (hi ? "WHO बजट के भीतर ✓ – परिवार सुरक्षित" : "Within WHO budget ✓ – Household protected");
    headline.className = `hero-headline ${over ? "text-debit" : "text-saved"}`;
  }
  if (d.peak_pm25 != null) setText("peak-warning-tag", `▼ ${hi ? "शिखर" : "Peak"} PM2.5: ${Math.round(d.peak_pm25)} µg/m³`);
}

export function renderMembers(entries, app) {
  const list = $("passbook-members-list");
  if (!list) return;
  list.replaceChildren();
  const hi = app.currentLang === "hi";
  app.familyProfile.members.forEach((m, idx) => {
    const e = entries.find((x) => x.member_id === m.id) || null;
    const row = el("div", "balance-row");
    row.setAttribute("role", "listitem");
    const details = el("div");
    const info = el("div", "member-info");
    info.append(el("div", "member-avatar", m.name.charAt(0).toUpperCase()), details);
    const sens = m.sensitivities?.length ? ` · ${m.sensitivities.join(", ")}` : "";
    details.append(
      el("div", "font-semibold", m.name),
      el("div", "stat-lbl text-xs", e ? `${hi ? "बजट" : "Budget"}: ${Math.round(e.budget_ug)} µg/d${sens}` : `${hi ? "गणना हो रही है" : "Calculating"}…${sens}`)
    );

    const barWrap = el("div", "member-bar-wrap");
    if (e) {
      const pct = e.budget_ug > 0 ? (e.debit_ug / e.budget_ug) * 100 : 100;
      const bar = svgEl("svg", { width: "100%", height: "8", role: "img", "aria-label": `${Math.round(pct)}% ${hi ? "बजट का" : "of WHO daily budget"}` });
      bar.append(svgEl("rect", { width: `${Math.min(100, Math.max(2, pct))}%`, height: "8", rx: "4", class: pct < 75 ? "fill-accent" : pct <= 100 ? "fill-moderate" : "fill-very-poor" }));
      barWrap.append(bar);
    }

    const del = el("button", "btn btn-sm btn-icon", "✕");
    del.type = "button";
    del.setAttribute("aria-label", `${hi ? "हटाएँ" : "Remove"} ${m.name}`);
    del.addEventListener("click", async () => {
      if (app.familyProfile.members.length <= 1) return;
      app.familyProfile.members.splice(idx, 1);
      app.saveProfile();
      await app.recalculatePassbook();
    });
    const acts = el("div", "member-acts flex gap-05 items-center");
    if (e) {
      acts.append(el("span", `pill-status ${e.debit_ug > e.budget_ug ? "debit" : "saved"}`, `${Math.round(e.debit_ug)} µg`));
      if (e.cigarette_equivalent != null) acts.append(el("span", "pill-status", `🚬 ${e.cigarette_equivalent.toFixed(1)}`));
    }
    acts.append(del);
    row.append(info, barWrap, acts);
    list.append(row);
  });
}

export function updatePlanMemberOptions(app, selectedId = null) {
  const sel = $("plan-member-select");
  if (!sel) return;
  const keep = selectedId || sel.value;
  sel.replaceChildren(
    ...app.familyProfile.members.map((m) => {
      const opt = el("option", null, m.name);
      opt.value = m.id;
      return opt;
    })
  );
  if (keep && app.familyProfile.members.some((m) => m.id === keep)) sel.value = keep;
}

/** Quick Scenarios: 1 click reconfigures city + household + plan defaults. */
export async function initPersonas(app) {
  const bar = $("persona-bar");
  if (!bar) return;
  let personas = [];
  try {
    personas = await api.fetchPersonas();
  } catch {
    bar.closest("section, .card")?.setAttribute("hidden", "");
    return;
  }
  const render = () => {
    const hi = app.currentLang === "hi";
    bar.replaceChildren(
      ...personas.map((p) => {
        const b = el("button", "chip-filter persona-btn");
        b.type = "button";
        b.setAttribute("aria-pressed", String(app.activePersona === p.id));
        b.append(el("span", "font-semibold", hi ? p.label_hi : p.label_en), el("span", "text-xs persona-sub", hi ? p.subtitle_hi : p.subtitle_en));
        b.addEventListener("click", () => app.applyPersona(p).then(render));
        return b;
      })
    );
  };
  app.renderPersonas = render;
  render();
}

/** Location modal: metro chips (from /api/v1/meta), live any-India search, GPS, coordinates. */
export function initLocationModal(app) {
  const modal = $("modal-city");
  const openBtn = $("city-btn");
  const closeBtn = $("modal-city-close");
  const setOpen = (open) => {
    if (!modal) return;
    modal.hidden = !open;
    openBtn?.setAttribute("aria-expanded", String(open));
    if (open) $("city-search-input")?.focus();
    else openBtn?.focus();
  };
  openBtn?.addEventListener("click", () => setOpen(true));
  closeBtn?.addEventListener("click", () => setOpen(false));
  modal?.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
  app.closeLocationModal = () => setOpen(false);

  const choose = (name, lat, lng) => {
    setOpen(false);
    app.activePersona = null;
    app.renderPersonas?.();
    return app.applyLocation(name, lat, lng);
  };

  app.renderCityChips = (cities) => {
    const wrap = $("city-chips");
    if (!wrap) return;
    wrap.replaceChildren(
      ...cities.map((c) => {
        const b = el("button", "chip-filter", c.name);
        b.type = "button";
        b.addEventListener("click", () => choose(c.name, c.lat, c.lng));
        return b;
      })
    );
  };

  const input = $("city-search-input");
  const results = $("city-search-results");
  const status = $("city-search-status");
  let timer = null;
  let seq = 0;
  input?.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) {
      results?.replaceChildren();
      if (status) status.textContent = "";
      return;
    }
    timer = setTimeout(async () => {
      const mySeq = ++seq;
      if (status) status.textContent = app.currentLang === "hi" ? "खोज रहे हैं…" : "Searching…";
      try {
        const places = await api.searchLocations(q);
        if (mySeq !== seq || !results) return;
        results.replaceChildren(
          ...places.map((p) => {
            const label = p.admin1 ? `${p.name}, ${p.admin1}` : p.name;
            const b = el("button", "chip-filter w-full", `📍 ${label}`);
            b.type = "button";
            b.setAttribute("role", "option");
            b.addEventListener("click", () => choose(label, p.lat, p.lng));
            return b;
          })
        );
        if (status) status.textContent = places.length ? `${places.length} ${app.currentLang === "hi" ? "परिणाम" : "results"}` : (app.currentLang === "hi" ? "कोई स्थान नहीं मिला" : "No Indian place found");
      } catch {
        if (status) status.textContent = app.currentLang === "hi" ? "खोज उपलब्ध नहीं" : "Search unavailable — use a metro chip";
      }
    }, 300);
  });

  const gpsBtn = $("btn-use-gps");
  gpsBtn?.addEventListener("click", () => {
    if (!navigator.geolocation) return;
    gpsBtn.textContent = app.currentLang === "hi" ? "📍 स्थान खोज रहे हैं…" : "📍 Locating…";
    const reset = () => { gpsBtn.textContent = app.currentLang === "hi" ? "📍 मेरा वर्तमान स्थान" : "📍 Use My Current Location"; };
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        reset();
        const { latitude: lat, longitude: lng } = pos.coords;
        const near = app.nearestCity(lat, lng);
        choose(near ? `${app.currentLang === "hi" ? "मेरा स्थान" : "My location"} (near ${near.name})` : "My location", lat, lng);
      },
      reset,
      { timeout: 8000, maximumAge: 60000 }
    );
  });

  $("btn-apply-custom-loc")?.addEventListener("click", () => {
    const lat = parseFloat($("custom-lat")?.value);
    const lng = parseFloat($("custom-lng")?.value);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) return;
    choose($("custom-city-name")?.value.trim() || "Custom Area", lat, lng);
  });
}
