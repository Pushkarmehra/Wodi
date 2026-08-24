/**
 * Nex — Renderer Logic
 * Renders streamed SSE responses and extends output panel ONCE per prompt.
 */

// ── SSE / Browser shim ──
if (!window.nex) {
  const updateListeners = [];
  const focusListeners  = [];

  window.nex = {
    executePrompt: async (text) => {
      try {
        const es = new EventSource(`/api/execute?prompt=${encodeURIComponent(text)}`);
        es.onmessage = (e) => {
          try {
            const d = JSON.parse(e.data);
            updateListeners.forEach(cb => cb(d));
            if (d.type === "complete" || (d.type === "error" && d.agent === "System")) es.close();
          } catch {}
        };
        es.onerror = () => {
          updateListeners.forEach(cb => cb({ type: "error", agent: "System", message: "Connection lost." }));
          es.close();
        };
        return { success: true };
      } catch (err) {
        return { success: false, error: err.message };
      }
    },
    hideWindow: () => {
      document.title = "action:hide";
    },
    clearHistory: async () => {
      try { await fetch('/api/clear_history'); } catch {}
    },
    onAgentUpdate:   (cb) => updateListeners.push(cb),
    onWindowFocused: (cb) => focusListeners.push(cb),
  };
}

window.nexFocusInput = () => {
  if (input) {
    input.focus();
    input.select();
  }
};

// ── DOM References ──
const app           = document.getElementById("app");
const input         = document.getElementById("prompt-input");
const btnSend       = document.getElementById("btn-send");
const btnClose      = document.getElementById("btn-close");
const statusDot     = document.getElementById("status-dot");
const responsePanel = document.getElementById("response-panel");
const messages      = document.getElementById("messages");

let busy = false;
let isExpanded = false;

function setDot(state) {
  statusDot.className = state === "active" ? "dot-active"
                      : state === "error"  ? "dot-error"
                      : "dot-idle";
}

function expandPanel() {
  if (!isExpanded) {
    isExpanded = true;
    responsePanel.classList.remove("hidden");
    app.classList.add("expanded");
    document.title = "action:expand";
  }
}

function resetPanel() {
  messages.innerHTML = "";
  responsePanel.classList.add("hidden");
  app.classList.remove("expanded");
  isExpanded = false;
  document.title = "action:collapse";
}

function parseMarkdown(text) {
  if (!text) return "";

  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Code blocks: ``` ... ```
  html = html.replace(/```([\s\S]*?)```/g, (match, p1) => {
    return `<pre><code>${p1.trim()}</code></pre>`;
  });

  // Inline code: `code`
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Bold: **text**
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

  // Italic: *text*
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

  // Headings
  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

  // Bullet Lists
  html = html.replace(/^\s*[-*]\s+(.*$)/gim, '<li>$1</li>');
  html = html.replace(/(<li>[\s\S]*?<\/li>)/gi, '<ul>$1</ul>');
  html = html.replace(/<\/ul>\s*<ul>/g, '');

  // Links: [label](url)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // Paragraph breaks
  html = html.replace(/\n\n/g, '<div class="spacer"></div>');
  html = html.replace(/\n/g, '<br/>');

  return html;
}

function addMessage(text, type = "agent", label = "") {
  expandPanel();

  const wrap = document.createElement("div");
  wrap.classList.add("message", `message-${type}`);

  if (label) {
    const lbl = document.createElement("div");
    lbl.classList.add("message-label");
    lbl.textContent = label;
    wrap.appendChild(lbl);
  }

  const body = document.createElement("div");
  body.classList.add("message-body");

  if (type === "log" || text.startsWith("Calling:") || text.startsWith("Executed")) {
    wrap.classList.add("message-status-badge");
    body.innerHTML = `<span class="badge-icon">⚡</span> ${text}`;
  } else if (type === "user") {
    body.textContent = text;
  } else {
    body.innerHTML = parseMarkdown(text);
  }

  wrap.appendChild(body);
  messages.appendChild(wrap);
  responsePanel.scrollTop = responsePanel.scrollHeight;
}

// ── Execute ──
async function run() {
  const prompt = input.value.trim();
  if (!prompt || busy) return;

  busy = true;
  btnSend.disabled = true;
  input.value = "";
  input.style.height = "auto";
  setDot("active");

  // Reset previous turn messages & expand panel once
  resetPanel();
  addMessage(prompt, "user", "You");

  try {
    const res = await window.nex.executePrompt(prompt);
    if (res && !res.success) setDot("error");
  } catch {
    setDot("error");
  } finally {
    busy = false;
    btnSend.disabled = false;
    setDot("idle");
    input.focus();
  }
}

// ── SSE Updates ──
window.nex.onAgentUpdate(d => {
  switch (d.type) {
    case "status":
      setDot("active");
      break;
    case "response":
      addMessage(d.message, "agent", d.agent || "Nex");
      break;
    case "success":
      if (d.message) addMessage(d.message, "agent", d.agent || "Nex");
      break;
    case "error":
      addMessage(d.message, "error", d.agent || "Error");
      setDot("error");
      break;
    case "complete":
      setDot("idle");
      break;
  }
});

// ── Events ──
btnSend.addEventListener("click", run);

btnClose.addEventListener("click", () => {
  resetPanel();
  window.nex.hideWindow();
});

input.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    run();
  } else if ((e.ctrlKey || e.metaKey) && (e.key === "/" || e.code === "Slash")) {
    e.preventDefault();
    resetPanel();
    window.nex.hideWindow();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 52) + "px";
});

document.addEventListener("keydown", e => {
  if (e.key === "Escape" || ((e.ctrlKey || e.metaKey) && (e.key === "/" || e.code === "Slash"))) {
    e.preventDefault();
    resetPanel();
    window.nex.hideWindow();
  }
});

window.nex.onWindowFocused(() => input.focus());