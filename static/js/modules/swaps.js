// Native ES Module: Sustainable urban swaps, habit tracker, and RWA / community multiplier

const $ = (id) => document.getElementById(id);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

/**
 * Initializes and wires the swaps calculator, community multiplier, and WhatsApp action copy.
 *
 * @param {Object} options
 * @param {() => string} options.getLanguage - Returns active language ('en' | 'hi').
 * @returns {{ update: () => void }}
 */
export function initSwaps({ getLanguage }) {
  const rng = $("society-flats-range") || $("mohalla-range");
  const chks = $$(".swap-chk");
  const cLbl = $("society-flats-count-label") || $("mohalla-count-label");
  const sSmokeVal = $("society-smoke-prevented-val") || $("community-emissions-val");
  const hVal = $("household-dose-saved");
  const sPill = $("swaps-avoided-pill");
  const copyBtn = $("btn-copy-rwa-note");
  const copyFb = $("rwa-copy-feedback");

  const update = () => {
    let doseSaved = 0;
    let rwaSmokePerFlat = 0;
    let totalCo2 = 0;
    const isHi = getLanguage() === "hi";

    chks.forEach((c) => {
      const row = c.closest(".balance-row");
      const pill = row ? row.querySelector(".pill-status") : null;
      const isChecked = c.checked;
      if (isChecked) {
        doseSaved += parseFloat(c.getAttribute("data-dose") || c.getAttribute("data-pm25") || "0");
        totalCo2 += parseFloat(c.getAttribute("data-co2") || "0");
        rwaSmokePerFlat += parseFloat(c.getAttribute("data-smoke") || "0");
        if (pill) {
          pill.textContent = isHi ? "सक्रिय" : "Active";
          pill.className = "pill-status saved";
        }
      } else if (pill) {
        pill.textContent = isHi ? "सक्षम करें" : "Enable";
        pill.className = "pill-status";
      }
    });

    const flats = parseInt(rng?.value || "120", 10);
    if (cLbl) cLbl.textContent = `${flats} ${isHi ? "फ्लैट / घर" : "flats / homes"}`;
    const collectiveSmoke = (flats * rwaSmokePerFlat) || (flats * totalCo2);
    if (sSmokeVal) sSmokeVal.textContent = `${collectiveSmoke.toFixed(1)} kg`;
    if (hVal) hVal.textContent = `${Math.round(doseSaved)} µg`;
    if (sPill) sPill.textContent = `▲ ${Math.round(doseSaved)} µg ${isHi ? "बचाया गया" : "avoided"}`;
  };

  if (rng) rng.addEventListener("input", update);
  chks.forEach((c) => c.addEventListener("change", update));

  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      const flats = parseInt(rng?.value || "120", 10);
      let rwaSmoke = 0;
      $$(".rwa-chk").forEach((c) => {
        if (c.checked) rwaSmoke += parseFloat(c.getAttribute("data-smoke") || "0");
      });
      const totalSmoke = (flats * (rwaSmoke || 1.26)).toFixed(1);
      const isHi = getLanguage() === "hi";
      const note = isHi
        ? `*हवा खाता - RWA वायु सुरक्षा निवेदन*\nप्रिय पड़ोसियों,\nसर्दियों में हमारी सोसाइटी दो कदम उठा सकती है:\n1. सुरक्षा गार्डों को इलेक्ट्रिक हीटर दें ताकि अलाव न जले।\n2. सूखे पत्तों की खाद बनाएं।\n${flats} फ्लैटों से लगभग ${totalSmoke} kg धुआं रुकेगा।\n— हवा खाता`
        : `*HawaKhata RWA Winter Smog Action*\nDear Neighbors,\nOur society can take two high-impact winter steps:\n1. Provide electric heaters to guards to avoid open fires.\n2. Compost dry leaves with zero burning.\nFor ${flats} homes, this avoids ~${totalSmoke} kg toxic smoke.\n— HawaKhata`;

      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(note);
        }
        if (copyFb) {
          copyFb.hidden = false;
          copyFb.textContent = isHi ? "✓ क्लिपबोर्ड पर कॉपी हो गया!" : "✓ Copied note to clipboard!";
          setTimeout(() => {
            if (copyFb) copyFb.hidden = true;
          }, 3000);
        }
      } catch {}
    });
  }

  update();
  return { update };
}
