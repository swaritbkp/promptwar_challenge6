// Native ES Module: shared CSP-safe DOM helpers (textContent only, never HTML strings)

export const $ = (id) => document.getElementById(id);
export const $$ = (sel) => Array.from(document.querySelectorAll(sel));

export const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
};

export const svgEl = (tag, attrs = {}) => {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, String(v)));
  return node;
};

export const setText = (id, text) => {
  const node = $(id);
  if (node) node.textContent = text;
};

/** Translate a key with fallback; t(strings, key, fallback). */
export const t = (strings, key, fallback) => (strings && strings[key]) || fallback;

export const catClass = (code) => String(code || "very_poor").replace(/_/g, "-");
