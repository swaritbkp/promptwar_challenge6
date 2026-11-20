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

/**
 * Initializes and binds the chat drawer, quick actions, and message flow.
 */
export function initChatDrawer({ getSessionId, setSessionId, getLanguage, getProfile }) {
  const drawer = $("ask-drawer");
  const input = $("ask-input");
  const log = $("ask-chat-msgs");
  const form = $("ask-form");

  const openDrawer = () => {
    if (drawer) drawer.hidden = false;
    if (input) input.focus();
  };
  const closeDrawer = () => {
    if (drawer) drawer.hidden = true;
  };

  const fab = $("fab-ask-btn");
  if (fab) fab.addEventListener("click", openDrawer);

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

        const modeLbl = data.degraded ? "Deterministic Fallback" : "Live Gemini Propose";
        const pillCls = data.degraded ? "warn" : "saved";
        const tag = (data.grounded ? "✓ Grounded · " : "") + modeLbl;
        log.appendChild(el("span", `pill-status ${pillCls} text-xs mt-05 block`, tag));

        // Render follow-up chips if present
        if (Array.isArray(data.chips) && data.chips.length > 0) {
          const chipBox = el("div", "flex gap-05 flex-wrap mt-05");
          data.chips.forEach((chipText) => {
            const chipBtn = el("button", "btn btn-sm btn-secondary text-xs", chipText);
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
