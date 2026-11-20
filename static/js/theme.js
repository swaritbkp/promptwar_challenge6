// HawaKhata theme switcher (classic script, loaded in <head> so the stored theme applies
// before first paint). Light is the default for every first-time visitor; a manual choice
// persists in localStorage ("hawakhata_theme"). <html data-theme> is the single source of
// truth for app.css — there is no prefers-color-scheme override.
(function () {
  "use strict";
  var KEY = "hawakhata_theme";
  var root = document.documentElement;
  var LABELS = {
    en: { dark: "Switch to dark theme", light: "Switch to light theme" },
    hi: { dark: "डार्क थीम पर जाएँ", light: "लाइट थीम पर जाएँ" },
  };

  function read() {
    try {
      return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
    } catch (e) {
      return "light";
    }
  }

  function sync() {
    var btn = document.getElementById("btn-theme-toggle");
    if (!btn) return;
    var dark = root.getAttribute("data-theme") === "dark";
    var lang = root.lang === "hi" ? "hi" : "en";
    btn.setAttribute("aria-pressed", String(dark));
    btn.setAttribute("aria-label", LABELS[lang][dark ? "light" : "dark"]);
    btn.setAttribute("title", LABELS[lang][dark ? "light" : "dark"]);
    var icon = document.getElementById("theme-icon");
    if (icon) icon.textContent = dark ? "☀️" : "🌙";
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", dark ? "#0B111E" : "#F3F6FA");
  }

  function apply(theme) {
    root.setAttribute("data-theme", theme);
    sync();
  }

  apply(read());

  document.addEventListener("DOMContentLoaded", function () {
    sync();
    var btn = document.getElementById("btn-theme-toggle");
    if (btn) {
      btn.addEventListener("click", function () {
        var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
        try {
          localStorage.setItem(KEY, next);
        } catch (e) {}
        apply(next);
      });
    }
    // Keep the bilingual aria-label in step with the EN / हिन्दी toggle.
    new MutationObserver(sync).observe(root, { attributes: true, attributeFilter: ["lang"] });
  });
})();
