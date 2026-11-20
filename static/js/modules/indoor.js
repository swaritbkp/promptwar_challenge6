// Native ES Module: Home Air simulator (engine-backed, with instant slider preview),
// plants-vs-HEPA reality check, and the species-specific Pet Air Advisor modal.

import { api } from "./api.js";
import { $, $$, el, setText } from "./dom.js";
import { renderIndoorCompare } from "./charts.js";

export function bindIndoor(app) {
  const vRng = $("indoor-vol-range");
  const cRng = $("indoor-cadr-range");
  const wSel = $("indoor-window-select");
  const pBtn = $("btn-toggle-purifier");
  const pRng = $("plant-count-range");
  let on = true;
  let timer = null;

  const showResult = (pm, outPm, preview) => {
    const pct = Math.max(0, Math.min(99, Math.round((1 - pm / Math.max(1, outPm)) * 100)));
    setText("indoor-pm25-val", `${pm} µg/m³`);
    setText("indoor-preview-pm25", `${pm} µg/m³`);
    setText("indoor-outdoor-val", `${outPm} µg/m³`);
    setText("indoor-clean-pct", `🛡 ${pct}% ${app.currentLang === "hi" ? "स्वच्छ हवा" : "Cleaner Air"}${preview ? " (Preview)" : ""}`);
    renderIndoorCompare(outPm, pm, app.currentLang === "hi");
  };

  const runEngineSim = async () => {
    const vol = parseFloat(vRng?.value || "60");
    const cadr = on ? parseFloat(cRng?.value || "300") : 0.0;
    const outPm = app.currentOutdoorPm25;
    const hi = app.currentLang === "hi";
    setText("indoor-sim-status", hi ? "सिम्युलेटिंग..." : "Simulating...");
    try {
      const d = await api.postIndoorSimulate({
        location: app.familyProfile.location,
        room: {
          name: "Living Room",
          volume_m3: vol,
          purifier_cadr_m3_per_h: cadr,
          purifier_on_hours: on ? Array.from({ length: 24 }, (_, i) => i) : [],
          windows_open_hours: wSel?.value === "open" ? [12, 13, 14] : [],
        },
        sources: app.familyProfile.sources || [],
      });
      showResult(Math.round(d.simulation?.mean_pm25_ug_m3 ?? 0), outPm, false);
      setText("indoor-cadr-val", `${Math.round(d.purifier_recommendation?.required_cadr_m3_per_h ?? vol * 5)} m³/h`);
      setText("indoor-sim-status", hi ? "सिम्युलेटेड (इंजन)" : "Simulated (engine)");
    } catch {
      setText("indoor-sim-status", hi ? "ऑफ़लाइन" : "Simulated (offline)");
    }
  };

  // Instant single-box mass-balance preview while dragging; the engine result replaces it.
  const updatePreview = () => {
    const vol = parseFloat(vRng?.value || "60");
    const cadr = on ? parseFloat(cRng?.value || "300") : 0;
    const ach = wSel?.value === "sealed" ? 0.4 : wSel?.value === "open" ? 2.5 : 0.8;
    const outPm = app.currentOutdoorPm25;
    setText("indoor-vol-label", `${vol} m³`);
    setText("indoor-cadr-label", `${cadr} m³/h`);
    setText("indoor-sim-status", app.currentLang === "hi" ? "पूर्वावलोकन…" : "Preview (sliding...)");
    showResult(Math.round((ach * outPm) / (ach + cadr / vol + 0.2)), outPm, true);
    clearTimeout(timer);
    timer = setTimeout(runEngineSim, 300);
  };

  const updatePlants = () => {
    const count = parseInt(pRng?.value || "5", 10);
    const cadr = (count * 0.1).toFixed(1);
    const hepa = on ? parseFloat(cRng?.value || "300") : 300;
    const ratio = Math.round(hepa / Math.max(0.1, count * 0.1));
    setText("plant-count-label", `${count} plants`);
    setText("plant-cadr-label", `CADR: ${cadr} m³/h`);
    setText("plant-reality-verdict", `${count} plants clear ~${cadr} m³/h. A ${hepa} m³/h HEPA purifier is ${ratio}× faster for winter smog. Wipe leaves weekly and avoid overwatering.`);
  };

  vRng?.addEventListener("input", updatePreview);
  cRng?.addEventListener("input", updatePreview);
  wSel?.addEventListener("change", updatePreview);
  pRng?.addEventListener("input", updatePlants);
  pBtn?.addEventListener("click", () => {
    on = !on;
    pBtn.textContent = on ? "Purifier ON" : "Purifier OFF";
    pBtn.className = `btn btn-sm ${on ? "btn-primary" : "btn-secondary"}`;
    pBtn.setAttribute("aria-pressed", String(on));
    updatePreview();
  });
  app.refreshIndoor = runEngineSim;
}

export function bindPets(app) {
  const modal = $("modal-pet");
  if (!modal) return;
  const select = (species) => {
    $$(".pet-tab-btn").forEach((b) => {
      const onTab = b.getAttribute("data-species") === species;
      b.setAttribute("aria-pressed", String(onTab));
    });
    loadPetGuidance(app, species);
  };
  const open = (species) => {
    modal.hidden = false;
    select(species);
    $("modal-pet-close")?.focus();
  };
  $("btn-pet-care")?.addEventListener("click", () => open("dog"));
  $("btn-pet-care-indoor")?.addEventListener("click", () => open("cat"));
  $("modal-pet-close")?.addEventListener("click", () => { modal.hidden = true; });
  modal.addEventListener("keydown", (e) => { if (e.key === "Escape") modal.hidden = true; });
  $$(".pet-tab-btn").forEach((b) => b.addEventListener("click", () => select(b.getAttribute("data-species") || "dog")));
}

async function loadPetGuidance(app, species) {
  try {
    const d = await api.postPetGuidance({ species, location: app.familyProfile.location });
    setText("pet-walk-summary", d.walk_advice || "");
    setText("pet-walk-dur-pill", `Max ${d.safe_walk_duration_min} min`);
    setText("pet-wipe-pill", d.post_walk_wipe_needed ? "Damp Wipe Needed" : "Wipe Optional");
    const ul = $("pet-indoor-steps");
    if (ul) {
      ul.replaceChildren(
        ...(d.warnings || []).map((w) => el("li", "text-debit font-semibold", `⚠️ ${w}`)),
        ...(d.practical_steps || []).map((s) => el("li", null, `✓ ${s}`))
      );
    }
  } catch {
    setText("pet-walk-summary", app.currentLang === "hi" ? "पालतू सलाह उपलब्ध नहीं" : "Pet guidance unavailable");
  }
}
