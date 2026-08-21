/**
 * Wodi — Web Renderer Logic
 *
 * Handles:
 *  - SSE EventSource streaming from /api/execute
 *  - Markdown rendering (headings, bold, italic, code blocks, lists, links)
 *  - Panel expand/collapse/hide via document.title IPC
 *  - Status dot state machine (idle → active → error → idle)
 *  - nexFocusInput() global for PySide6 WebEngine hotkey bridge
 *  - Conversation history clear on panel reset
 *
 * Ported from Nex prototype app.js — upgraded with:
 *  - Full markdown table support
 *  - Horizontal rule rendering
 *  - Per-message agent badges
 *  - Keyboard shortcut Escape → hide
 *  - Voice button placeholder
 */

'use strict';

// ── Wodi SSE/IPC bridge (browser shim) ────────────────────────────────────────
if (!window.wodi) {
  const updateListeners = [];
  const focusListeners  = [];

  window.wodi = {
    executePrompt: async (text) => {
      try {
        const es = new EventSource(`/api/execute?prompt=${encodeURIComponent(text)}`);
        es.onmessage = (e) => {
          try {
            const d = JSON.parse(e.data);
            updateListeners.forEach(cb => cb(d));
            if (d.type === 'complete' || (d.type === 'error' && d.agent === 'System')) {
              es.close();
            }
          } catch (_) {}
        };
        es.onerror = () => {
          updateListeners.forEach(cb => cb({
            type: 'error',
            agent: 'System',
            message: 'Connection to Wodi lost. Is the server running?',
          }));
          es.close();
        };
        return { success: true };
      } catch (err) {
        return { success: false, error: err.message };
      }
    },

    hideWindow: () => {
      document.title = 'action:hide';
    },

    clearHistory: async () => {
      try { await fetch('/api/clear_history'); } catch (_) {}
    },

    onAgentUpdate:   (cb) => updateListeners.push(cb),
    onWindowFocused: (cb) => focusListeners.push(cb),
  };
}

// Global hook for PySide6 WebEngine → JS bridge (Ctrl+/ hotkey)
window.nexFocusInput = () => {
  if (input) {
    input.focus();
    input.select();
  }
};

// ── DOM references ─────────────────────────────────────────────────────────────
const app           = document.getElementById('app');
const input         = document.getElementById('prompt-input');
const btnSend       = document.getElementById('btn-send');
const btnClose      = document.getElementById('btn-close');
const btnVoice      = document.getElementById('btn-voice');
const statusDot     = document.getElementById('status-dot');
const responsePanel = document.getElementById('response-panel');
const messages      = document.getElementById('messages');

let busy       = false;
let isExpanded = false;

// ── Status dot ─────────────────────────────────────────────────────────────────
function setDot(state) {
  statusDot.className =
    state === 'active' ? 'dot-active' :
    state === 'error'  ? 'dot-error'  :
                         'dot-idle';
}

// ── Panel expand / collapse / hide ────────────────────────────────────────────
function expandPanel() {
  if (!isExpanded) {
    isExpanded = true;
    responsePanel.classList.remove('hidden');
    app.classList.add('expanded');
    document.title = 'action:expand';
  }
}

function resetPanel() {
  messages.innerHTML = '';
  responsePanel.classList.add('hidden');
  app.classList.remove('expanded');
  isExpanded = false;
  document.title = 'action:collapse';
}

// ── Markdown renderer ─────────────────────────────────────────────────────────
function parseMarkdown(text) {
  if (!text) return '';

  // Escape HTML first
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Fenced code blocks (``` lang\n ... ```)
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code class="lang-${lang || 'text'}">${code.trim()}</code></pre>`
  );

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Headings (must come before bold)
  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gim,  '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gim,   '<h1>$1</h1>');

  // Horizontal rule
  html = html.replace(/^---$/gim, '<hr/>');

  // Bold + italic
  html = html.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.*?)\*\*/g,     '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/g,         '<em>$1</em>');

  // Unordered lists
  html = html.replace(/^\s*[-*]\s+(.*$)/gim, '<li>$1</li>');
  html = html.replace(/(<li>[\s\S]*?<\/li>)/gi, '<ul>$1</ul>');
  html = html.replace(/<\/ul>\s*<ul>/g, '');

  // Ordered lists
  html = html.replace(/^\s*\d+\.\s+(.*$)/gim, '<li>$1</li>');

  // Links [label](url)
  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  );

  // Paragraph breaks
  html = html.replace(/\n\n/g, '<div class="spacer"></div>');
  html = html.replace(/\n/g, '<br/>');

  return html;
}

// ── Message bubble factory ────────────────────────────────────────────────────
function addMessage(text, type = 'agent', label = '') {
  expandPanel();

  const wrap = document.createElement('div');
  wrap.classList.add('message', `message-${type}`);

  // Agent label / sender pill
  if (label) {
    const lbl = document.createElement('div');
    lbl.classList.add('message-label');
    lbl.textContent = label;
    wrap.appendChild(lbl);
  }

  const body = document.createElement('div');
  body.classList.add('message-body');

  const isToolLog = type === 'log' || text.startsWith('Calling:') || text.startsWith('Executed');

  if (isToolLog) {
    wrap.classList.add('message-status-badge');
    body.innerHTML = `<span class="badge-icon">⚡</span> ${text}`;
  } else if (type === 'user') {
    body.textContent = text;
  } else {
    body.innerHTML = parseMarkdown(text);
  }

  wrap.appendChild(body);
  messages.appendChild(wrap);
  responsePanel.scrollTop = responsePanel.scrollHeight;
}

// ── Execute prompt ─────────────────────────────────────────────────────────────
async function run() {
  const prompt = input.value.trim();
  if (!prompt || busy) return;

  busy = true;
  btnSend.disabled = true;
  input.value = '';
  input.style.height = 'auto';
  setDot('active');

  // Reset previous turn
  resetPanel();
  addMessage(prompt, 'user', 'You');

  try {
    const res = await window.wodi.executePrompt(prompt);
    if (res && !res.success) setDot('error');
  } catch (_) {
    setDot('error');
  } finally {
    busy = false;
    btnSend.disabled = false;
    input.focus();
  }
}

// ── SSE update handler ────────────────────────────────────────────────────────
window.wodi.onAgentUpdate(d => {
  switch (d.type) {
    case 'status':
      setDot('active');
      break;

    case 'response':
      addMessage(d.message, 'agent', d.agent || 'Wodi');
      setDot('idle');
      break;

    case 'log':
      addMessage(d.message || d.status, 'log');
      break;

    case 'success':
      if (d.message) addMessage(d.message, 'agent', d.agent || 'Wodi');
      setDot('idle');
      break;

    case 'error':
      addMessage(d.message, 'error', d.agent || 'Error');
      setDot('error');
      break;

    case 'complete':
      setDot('idle');
      break;
  }
});

// ── Events ────────────────────────────────────────────────────────────────────
btnSend.addEventListener('click', run);

btnClose.addEventListener('click', () => {
  resetPanel();
  window.wodi.clearHistory();
  window.wodi.hideWindow();
});

// Voice button — placeholder for future STT integration
btnVoice.addEventListener('click', () => {
  addMessage('Voice input coming soon! Use Ctrl+Space to activate wake word.', 'agent', 'Wodi');
});

// Enter = send, Shift+Enter = newline
input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    run();
  } else if (e.key === 'Escape' || ((e.ctrlKey || e.metaKey) && (e.key === '/' || e.code === 'Slash'))) {
    e.preventDefault();
    resetPanel();
    window.wodi.hideWindow();
  }
});

// Auto-resize textarea (max 3 lines)
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 52) + 'px';
});

// Global Esc key
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    e.preventDefault();
    resetPanel();
    window.wodi.hideWindow();
  }
});

// Focus on window focus (called by PySide6 WebEngine)
window.wodi.onWindowFocused(() => input.focus());

// Auto-focus on load
window.addEventListener('load', () => input.focus());
