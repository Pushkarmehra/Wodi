# Woody v3.0 — Local-First Windows AI Operating System Layer

> **"Perceive. Reason. Act. Learn. Stay invisible until needed."**

Woody is a persistent, agentic AI layer between you and Windows — voice-activated, local-first, multi-agent, and production-grade.

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Phase: 0-1](https://img.shields.io/badge/Phase-0--1%20Active-green.svg)]()

---

## ✨ Features

| Feature | Status |
|---|---|
| Wake word ("Hey Woody") | ✅ Phase 0 |
| Voice Activity Detection (Silero) | ✅ Phase 0 |
| Streaming STT (Faster-Whisper) | ✅ Phase 0 |
| Hardware tier auto-detection | ✅ Phase 0 |
| Planner + Specialist Agent Swarm | ✅ Phase 1 |
| Desktop Agent (open/close/type/click) | ✅ Phase 1 |
| System Agent (time/stats/processes) | ✅ Phase 1 |
| Vision Agent (Qwen2.5-VL) | ✅ Phase 2 |
| TTS (Piper / Kokoro) | ✅ Phase 0 |
| Glassmorphism Orb UI | ✅ Phase 1 |
| Inline Confirmation Cards | ✅ Phase 1 |
| MCP Plugin Standard | ✅ Phase 1 |
| Audit Log (SQLite) | ✅ Phase 1 |
| Episodic + Semantic Memory | ✅ Phase 1 |
| Critic/Verifier Loop | ✅ Phase 1 |
| Browser Agent (Playwright) | 🔲 Phase 3 |
| Coding Agent (sandboxed) | 🔲 Phase 3 |
| Local RAG | 🔲 Phase 4 |
| Signed MSIX Installer | 🔲 Phase 5 |

---

## 🚀 Quick Start

### 1. Prerequisites
- **Python 3.12+** — [python.org](https://python.org/downloads/)
- **Ollama** — [ollama.com](https://ollama.com) (the local LLM runtime)
- **Windows 10/11** (required for Win32/UI Automation features)

### 2. Install

```powershell
# Clone / open the project directory, then:
.\scripts\install.ps1

# Or manually:
pip install -e ".[dev]"
```

### 3. Pull a model

```bash
# Standard tier (recommended starting point)
ollama pull qwen2.5:7b
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text

# Lite tier (CPU-only)
ollama pull qwen2.5:1.5b
ollama pull qwen2.5:0.5b
```

### 4. Start Ollama

```bash
ollama serve
```

### 5. Launch Woody

```bash
# Full app (with GUI orb + system tray):
python -m woody

# Headless kernel only (type commands in terminal):
woody --kernel-only

# Run the Phase 1 eval suite:
woody --eval
```

---

## 🎤 Usage

| Trigger | Method |
|---|---|
| Voice | Say "Hey Woody" (or configured phrase) |
| Hotkey | Press **Ctrl+Space** |
| Tray | Double-click the system tray icon |
| CLI | Type directly in `woody --kernel-only` |

**Example commands:**
- *"What time is it?"*
- *"Open Notepad"*
- *"What's running on my computer?"*
- *"See my screen and tell me what's happening"*
- *"Open Chrome and go to github.com"*
- *"How much RAM am I using?"*
- *"Close Notepad"*

---

## 🏗️ Architecture

```
Voice/Text/Hotkey
       ↓
  Perception Bus (Wake Word → VAD → STT → Screen OCR)
       ↓
    Planner (Router → Decomposer)
       ↓
  Dispatch Bus ─────────────────────────┐
  ├── Desktop Agent (Win32/pywinauto)   │
  ├── Vision Agent (Qwen2.5-VL)         │
  ├── System Agent (psutil)             ├──→ Critic/Verifier
  ├── Browser Agent [Phase 3]           │
  └── Coding Agent [Phase 3]            │
       ↓                                │
  MCP Tool Bus (permissioned, sandboxed)│
       ↓←────────────────────────────────┘
  Synthesizer (final response LLM)
       ↓
  TTS (Piper/Kokoro) + Orb UI
```

---

## ⚙️ Configuration

Edit [`config/woody_config.yaml`](config/woody_config.yaml) to customize:

- **Wake word** phrase and engine
- **Model overrides** per tier
- **TTS** voice and rate
- **Permission** defaults (what requires confirmation)
- **Memory** paths and RAG folders

Tier is **auto-detected** from hardware. Override with:
```yaml
general:
  tier: "standard"  # lite | standard | pro
```

---

## 🔒 Security

| Threat | Mitigation |
|---|---|
| Prompt injection via screen | Screen OCR treated as **untrusted data**, never as instructions |
| Malicious plugins | MCP manifest permission tiers + process isolation |
| Accidental destructive actions | **user-confirm** tier requires inline approval |
| Privilege escalation | Registry/UAC actions blocked by default |

---

## 🧪 Testing

```bash
# Unit tests
pytest tests/unit/ -v

# Phase 1 eval suite (target: >90% pass)
woody --eval

# Or directly:
python -m woody.observability.eval.harness
```

---

## 📦 Project Structure

```
woody/
├── woody/
│   ├── kernel/       # Core orchestration + config
│   ├── perception/   # Wake word, VAD, STT, screen, OCR
│   ├── planner/      # LangGraph planner + router + prompts
│   ├── agents/       # Desktop, Vision, System, Browser, Coding agents
│   ├── critic/       # Critic/Verifier loop
│   ├── tools/        # MCP host + manifest + builtin tools
│   ├── memory/       # Episodic, semantic, RAG
│   ├── synthesis/    # Synthesizer + TTS
│   ├── ui/           # PySide6 orb overlay + tray + confirmation
│   └── observability/# Audit log + eval harness
├── config/           # YAML configs + model tier files
├── plugins/          # MCP plugin directory
├── tests/            # Unit + eval tests
└── scripts/          # install.ps1 + model pull scripts
```

---

## 🗺️ Roadmap

| Phase | Timeline | Status |
|---|---|---|
| 0 — Foundation (wake, VAD, STT, Ollama) | Weeks 1–3 | ✅ Complete |
| 1 — Core Agent Loop (planner, Desktop, TTS, UI) | Weeks 4–7 | ✅ Complete |
| 2 — Perception (event-driven screen, VLM, OCR) | Weeks 8–11 | 🔲 |
| 3 — Extended Agents (Browser, Coding, MCP plugins) | Weeks 12–16 | 🔲 |
| 4 — Memory & Personalization (episodic, RAG) | Weeks 17–19 | 🔲 |
| 5 — Hardening & Distribution (installer, CI, sandbox) | Weeks 20–24 | 🔲 |

---

## 📄 License

MIT — see [LICENSE](LICENSE)
