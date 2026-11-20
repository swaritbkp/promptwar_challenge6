// Native ES Module: CSP-safe chat drawer and conversation manager

import { api } from "./api.js";

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
};

/**
 * CSP-safe markdown DOM renderer for agent text.
 * Strictly avoids innerHTML/outerHTML, building semantic DOM nodes with textContent.
 */
export function renderCspMarkdown(container, text) {
  container.textContent = "";
  if (!text) return;

  const lines = text.split("\n");
  let currentUl = null;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      currentUl = null;
      continue;
    }

    if (trimmed.startsWith("* ") || trimmed.startsWith("- ")) {
      if (!currentUl) {
        currentUl = document.createElement("ul");
        container.appendChild(currentUl);
      }
      const li = document.createElement("li");
      appendFormattedText(li, trimmed.slice(2));
      currentUl.appendChild(li);
    } else {
      currentUl = null;
      const p = document.createElement("p");
      appendFormattedText(p, trimmed);
      container.appendChild(p);
    }
  }
}

function appendFormattedText(container, text) {
  // Support **bold** formatting safely using split
  const parts = text.split(/\*\*(.*?)\*\*/g);
  parts.forEach((part, i) => {
    if (i % 2 === 1) {
      const strong = document.createElement("strong");
      strong.textContent = part;
      container.appendChild(strong);
    } else if (part) {
      container.appendChild(document.createTextNode(part));
    }
  });
}

/** Turn status pill: guardrail refusals never claim a live Gemini proposal. */
export function statusPill(data, hi) {
  let cls = "saved";
  let tag;
  if (data.blocked_by_guardrail) {
    cls = "warn";
    tag = hi ? "🛡 सुरक्षा गार्डरेल · नीति लागू" : "🛡 Safety Guardrail · Policy Enforced";
  } else {
    if (data.degraded) cls = "warn";
    const mode = data.degraded
      ? (hi ? "नियम-आधारित फ़ॉलबैक" : "Deterministic Fallback")
      : (hi ? "लाइव Gemini प्रस्ताव" : "Live Gemini Propose");
    tag = (data.grounded ? (hi ? "✓ सत्यापित · " : "✓ Grounded · ") : "") + mode;
  }
  const pill = el("span", `pill-status ${cls} text-xs mt-05 block`, tag);
  return pill;
}

/**
 * Initializes and binds the chat drawer, quick actions, and message flow.
 */
export function initChatDrawer({ getSessionId, setSessionId, getLanguage, getProfile }) {
  const drawer = $("ask-drawer");
  const input = $("ask-input");
  const log = $("ask-chat-msgs");
  const form = $("ask-form");

  const trigger = $("fab-ask-btn");
  const openDrawer = () => {
    if (drawer) drawer.hidden = false;
    trigger?.setAttribute("aria-expanded", "true");
    if (input) input.focus();
  };
  const closeDrawer = () => {
    if (drawer) drawer.hidden = true;
    trigger?.setAttribute("aria-expanded", "false");
    trigger?.focus();
  };

  if (trigger) trigger.addEventListener("click", () => (drawer && !drawer.hidden ? closeDrawer() : openDrawer()));

  const closeBtn = $("ask-close-btn");
  if (closeBtn) closeBtn.addEventListener("click", closeDrawer);

  // Close chat drawer on Escape key
  if (drawer) {
    drawer.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeDrawer();
    });
  }

  if (!form || !input || !log) return { open: openDrawer, close: closeDrawer };

  const addMsg = (cls, txt) => {
    const d = el("div", `msg ${cls}`, txt);
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
    return d;
  };

  // Sample prompts: full list on a fresh drawer, collapsed to a 1-line toggle after the first send.
  const samples = $("ask-samples");
  const samplesToggle = $("ask-samples-toggle");
  const setSamplesOpen = (open) => {
    if (samples) samples.hidden = !open;
    samplesToggle?.setAttribute("aria-expanded", String(open));
  };
  samplesToggle?.addEventListener("click", () => setSamplesOpen(samples?.hidden ?? false));
  const collapseSamples = () => {
    if (samplesToggle) samplesToggle.hidden = false;
    setSamplesOpen(false);
  };

  // One-click sample prompts (text is translated via data-i18n, so the sent query follows the UI language)
  document.querySelectorAll(".ask-sample-btn").forEach((b) => {
    b.addEventListener("click", () => {
      input.value = b.textContent || "";
      form.requestSubmit();
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = input.value.trim();
    if (!msg) return;

    addMsg("user", msg);
    input.value = "";
    collapseSamples();
    const aMsg = addMsg("assistant", "...");

    try {
      const data = await api.postChat({
        message: msg,
        sessionId: getSessionId(),
        language: getLanguage(),
        profile: getProfile(),
      });

      if (data && data.reply) {
        if (data.session_id) setSessionId(data.session_id);
        renderCspMarkdown(aMsg, data.reply);

        log.appendChild(statusPill(data, getLanguage() === "hi" || data.language === "hi"));

        // Render follow-up chips if present
        if (Array.isArray(data.chips) && data.chips.length > 0) {
          const chipBox = el("div", "flex gap-05 flex-wrap");
          data.chips.forEach((chipText) => {
            const chipBtn = el("button", "chip-filter", chipText);
            chipBtn.type = "button";
            chipBtn.addEventListener("click", () => {
              input.value = chipText;
              form.requestSubmit();
            });
            chipBox.appendChild(chipBtn);
          });
          log.appendChild(chipBox);
        }
      } else {
        aMsg.textContent = "Unable to process request.";
      }
    } catch {
      aMsg.textContent = "Offline. Showing local verified air recommendations.";
    }
    log.scrollTop = log.scrollHeight;
  });

  return { open: openDrawer, close: closeDrawer };
}
