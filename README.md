<div align="center">

# 🌟 Woody v3.0 — Local-First Windows AI Operating System Layer

<p align="center">
  <img src="assets/banner.jpg" alt="Woody v3.0 AI OS Layer" width="100%" />
</p>

> **"Perceive. Reason. Act. Learn. Stay invisible until needed."**

Woody is a persistent, multi-agent AI operating layer built natively for Windows — featuring local-first intelligence, multimodal screen perception, real-time voice interaction, fluid glassmorphism command centers, and an authentic interactive animated AI desktop companion powered by the **VPet Simulation Engine**.

---

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Platform: Windows 11/10](https://img.shields.io/badge/Platform-Windows_11%20%7C%2010-0078D4?style=for-the-badge&logo=windows&logoColor=white)](https://microsoft.com/windows)
[![LangGraph Multi-Agent](https://img.shields.io/badge/Orchestration-LangGraph-FF6F00?style=for-the-badge&logo=langchain&logoColor=white)](https://langchain.com)
[![VPet Simulation Engine](https://img.shields.io/badge/VPet_Engine-6%2C180%2B_Frames-9333EA?style=for-the-badge)](vpet/)
[![Ollama Local LLMs](https://img.shields.io/badge/Local_LLM-Ollama-black?style=for-the-badge&logo=ollama&logoColor=white)](https://ollama.com)
[![Inworld AI Voice](https://img.shields.io/badge/Neural_TTS-Inworld_AI-7C3AED?style=for-the-badge)](https://inworld.ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-10B981?style=for-the-badge)](LICENSE)

</div>

---

## ⚡ What's New in Woody v3.0

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>🐾 Authentic VPet Desktop Companion (`--pet`)</h3>
      <ul>
        <li><b>6,180+ Animation Frames & 25+ Actions:</b> Powered by official VPet core sprites (Idle, Meow, Tennis, Music, Sleep, Work, Pinch, Squat, Say, Level-Up).</li>
        <li><b>Full RPG Stats & Life Simulation:</b> Dynamic Level & EXP, Money ($), Fullness (Hunger), Thirst, Stamina, Mood, and Likability tracking.</li>
        <li><b>120+ Authentic Items & Shop:</b> Complete LinePutScript (<code>.lps</code>) foods, drinks, medicine, and gifts with official English translations.</li>
        <li><b>Work & Study Jobs:</b> Earn money through AI Coding, Live Streaming, Calligraphy, and Analytics with floating Purple WorkTimers.</li>
        <li><b>Zero-Latency Neural Voice:</b> Sentence-pipelined Inworld TTS-2 streaming (&lt;50ms queue) with native audio cues (purrs, chimes, coins).</li>
      </ul>
    </td>
    <td width="50%" valign="top">
      <h3>🔮 Liquid Glass Command Center (`--web-ui`)</h3>
      <ul>
        <li><b>Apple Intelligence-Inspired UI:</b> Refractive glassmorphism with dynamic ambient lighting, specular depth, and fluid spring animations.</li>
        <li><b>Live Audio Visualizer:</b> Real-time dynamic voice gradient glowing orb & responsive spectrum waveforms.</li>
        <li><b>Streaming Swarm Transcripts:</b> Instant markdown chat stream, step-by-step reasoning nodes, and activity audit log.</li>
        <li><b>Interactive Confirmation Cards:</b> Inline approvals for high-privilege system actions before execution.</li>
      </ul>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <h3>👁️ Multimodal Screen Vision Agent</h3>
      <ul>
        <li><b>Live Screen Analysis:</b> Seamlessly inspects active windows, multi-monitor setups, and UI controls via Groq Llama-3.2 Vision / Qwen2.5-VL.</li>
        <li><b>Low-Overhead Event Hooks:</b> Event-driven Win32 hooks trigger screen perception without draining CPU/battery.</li>
        <li><b>Visual UI Grounding:</b> Recognizes buttons, input fields, forms, and error dialogs for high-precision desktop automation.</li>
      </ul>
    </td>
    <td width="50%" valign="top">
      <h3>🚀 Pipelined Speech & Multi-Agent Swarm</h3>
      <ul>
        <li><b>Sub-Second Voice Loop:</b> OpenWakeWord ("Hey Woody") + Silero VAD + Faster-Whisper streaming STT.</li>
        <li><b>LangGraph Swarm Routing:</b> Autonomous intent decomposition between Desktop, Vision, System, Browser, and Chat agents.</li>
        <li><b>Critic/Verifier Self-Correction:</b> Automated verification loops ensure desktop commands succeed accurately.</li>
        <li><b>Model Context Protocol (MCP):</b> Connect external tools and enterprise data sources via MCP manifests.</li>
      </ul>
    </td>
  </tr>
</table>

---

## 🐾 Meet Woody — Your AI Desktop Pet Companion

Woody is not just a background daemon; it comes with an authentic, fully animated **AI Desktop Pet** that lives directly on your Windows screen. Ask questions, have it inspect your screen, automate desktop tasks, feed it snacks, or let it work jobs to earn money!

<p align="center">
  <img src="assets/desktop_pet.jpg" alt="Woody AI Desktop Pet Showcase" width="95%" />
</p>

### 🎬 Animated Pet Sprite States

<div align="center">

| Walking Right | Idle & Observing | Going to Sleep | Sleeping | Waking Up |
|:---:|:---:|:---:|:---:|:---:|
| <img src="gifs/walk_positive.gif" width="110" height="110" /> | <img src="gifs/idle.gif" width="110" height="110" /> | <img src="gifs/idle_to_sleep.gif" width="110" height="110" /> | <img src="gifs/sleep.gif" width="110" height="110" /> | <img src="gifs/sleep_to_idle.gif" width="110" height="110" /> |
| `walk_positive` | `idle` | `idle_to_sleep` | `sleep` | `sleep_to_idle` |

</div>

### ✨ VPet Simulation Highlights:
- **6,180+ Official Animation Frames:** Direct integration of the official LorisYounger/VPet core sprite graph across 25+ unique interactive animations.
- **5-Tab Floating Toolbar (Purple Theme `prupe.lps`):**
  - 🍲 **Feed:** Feed foods, drinks, snacks, and medicine to restore fullness and health.
  - 📊 **Status:** View Level, EXP, Health, Stamina, Mood, Hunger, Thirst, and Likability.
  - 🎭 **Interact:** Play tennis, blow bubbles, touch head/body, pinch cheeks, or make it dance.
  - 🏪 **Shop:** Purchase from 120+ translated catalog items using earned coins ($).
  - 💼 **Work:** Start real-time Work & Study jobs (AI Coding, Streaming, Math, Analytics) with floating purple countdown timers.
  - 💬 **Chat / Voice:** Direct chat input box and voice listening toggle.
- **Full Woody AI Brain & Tools:** Single-click the pet to trigger Woody's voice greeting and chat box — ask Woody to open applications, search the web, analyze your screen, or execute complex desktop tasks.
- **Zero-Latency Sentence TTS Pipeline:** Instant voice output (<50ms queue) with Inworld Neural Voice (`community-blcuaurhzmvi`) and native audio feedback (purrs, chimes, coin clinks).
- **Persistent State:** Saves character progress, level, inventory, and stats to `~/.woody/vpet_save.json`.

```bash
# Launch Woody in Desktop Pet mode
woody --pet
```

---

## 🔮 Liquid Glass Command Center & Web Overlay

Woody features a state-of-the-art UI system crafted with **Apple-inspired fluid glassmorphism**, specular catch-lights, and responsive ambient backdrops.

<p align="center">
  <img src="assets/command_center.jpg" alt="Woody Command Center Interface" width="95%" />
</p>

- **Dynamic Voice Visualizer Orb:** Glows and modulates in real-time as you speak or when Woody responds.
- **Live Markdown Stream:** Watch agent reasoning steps, code blocks, and formatted summaries appear incrementally.
- **Multi-Agent Switcher:** Monitor real-time statuses for **Desktop Agent**, **Vision Agent**, **System Agent**, and **Memory**.
- **Human-in-the-Loop Safety:** Destructive actions (e.g. deleting files, closing unsaved apps) generate inline confirmation cards requiring explicit authorization.

```bash
# Launch Woody with the full Glassmorphism WebEngine Overlay
woody --web-ui

# Launch with native PySide6 floating bar
woody
```

---

## 🏗️ Multi-Agent Swarm Architecture

```
                  ┌─────────────────────────────────────────┐
                  │   User Input (Voice / Hotkey / Web UI)  │
                  └────────────────────┬────────────────────┘
                                       │
                  ┌────────────────────▼────────────────────┐
                  │             Perception Bus              │
                  │   Wake Word → Silero VAD → Whisper STT  │
                  │   Event-Driven Win32 Screen & OCR Hook  │
                  └────────────────────┬────────────────────┘
                                       │
                  ┌────────────────────▼────────────────────┐
                  │    LangGraph Router & Task Planner      │
                  │ (Fast Intent Classification & Decompose)│
                  └────────────────────┬────────────────────┘
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         ▼                             ▼                             ▼
  ┌───────────────┐             ┌───────────────┐             ┌───────────────┐
  │ Desktop Agent │             │ Vision Agent  │             │ System Agent  │
  │ Win32/pywinauto             │ Llama 3.2-VL  │             │ psutil / WMI  │
  │ Click, Type,  │             │ Visual Reason │             │ Telemetry &   │
  │ Window Ops    │             │ UI Grounding  │             │ Process Mgt   │
  └───────┬───────┘             └───────┬───────┘             └───────┬───────┘
          │                             │                             │
          ├─────────────────────────────┼─────────────────────────────┤
          ▼                             ▼                             ▼
  ┌───────────────┐             ┌───────────────┐             ┌───────────────┐
  │ Browser Agent │             │  Coding Agent │             │   MCP Tools   │
  │ Playwright UI │             │ Python Code / │             │ Model Context │
  │ Web Navigation│             │ REPL Sandbox  │             │ Protocol Host │
  └───────┬───────┘             └───────┬───────┘             └───────┬───────┘
          │                             │                             │
          └─────────────────────────────┼─────────────────────────────┘
                                       │
                  ┌────────────────────▼────────────────────┐
                  │         Critic / Verifier Loop          │
                  │ (Outcome Check & Self-Correction Engine)│
                  └────────────────────┬────────────────────┘
                                       │
                  ┌────────────────────▼────────────────────┐
                  │       Synthesizer & Audio Pipeline      │
                  │ (Inworld AI TTS-2 / Piper / Kokoro / Edge)│
                  └────────────────────┬────────────────────┘
                                       │
               ┌────────────────────────┴────────────────────────┐
               ▼                                                 ▼
      ┌───────────────────┐                             ┌───────────────────┐
      │  Desktop AI Pet   │                             │  Command Center   │
      │  (VPet + Audio)   │                             │ (Glassmorphic UI) │
      └───────────────────┘                             └───────────────────┘
```

---

## 🕹️ Launch Modes & CLI Reference

| Command | Description | Best For |
|---|---|---|
| `woody` | Full application with native PySide6 floating glass bar & tray | Daily desktop workflow |
| `woody --pet` | Interactive animated VPet desktop companion (6,180+ frames) | Cozy desk buddy & casual voice control |
| `woody --web-ui` | Apple-inspired fluid glassmorphic Command Center | Rich visual multi-agent experience |
| `woody --serve` | Headless FastAPI backend daemon (REST API + SSE) | Headless servers, background services |
| `woody --kernel-only` | Pure REPL terminal interface (no GUI) | Debugging, CLI scripting |
| `woody --eval` | Automated Phase evaluation & benchmark suite | Verification & quality testing |
| `woody --port 8765` | Custom backend port override | Multi-instance or non-standard port setups |
| `woody --config PATH` | Custom YAML configuration file path | Custom model / agent configurations |

---

## 🚀 Quick Start

### 1. Prerequisites
- **Windows 10 / 11** (Required for Win32 API & UI Automation)
- **Python 3.12+** — [Download from python.org](https://python.org/downloads/)
- **Ollama** (for local offline LLMs) — [ollama.com](https://ollama.com)
- *(Optional)* **Groq API Key** / **Inworld AI Key** / **Gemini Key** (for cloud acceleration & neural pet voice)

### 2. Installation

```powershell
# Clone the repository
git clone https://github.com/Pushkarmehra/Wodi.git
cd Wodi

# Run automated Windows setup script (installs venv & all dependencies)
.\scripts\install.ps1

# Or install manually with optional extras:
pip install -e ".[dev,audio,desktop,vision,ui,llm,cloud]"
```

### 3. Configure API Keys (Optional for Cloud Boost)

Copy `.env.example` to `.env` and fill in your keys:

```ini
# Neural Voice & Cloud LLM Keys
INWORLD_API_KEY="your_inworld_key"
GROQ_API_KEY="your_groq_key"
GEMINI_API_KEY="your_gemini_key"
OPENAI_API_KEY="your_openai_key"
```

### 4. Pull Local Ollama Models (for Offline Mode)

```bash
# Recommended models
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

### 5. Launch Woody!

```bash
# Start your VPet Desktop Companion
python -m woody --pet

# Or open the modern Command Center
python -m woody --web-ui
```

---

## 🎤 Natural Language Usage Examples

| Domain | Voice / Text Prompt | Agent Executing |
|---|---|---|
| **Desktop Automation** | *"Open Notepad, type my grocery list, and save it to Desktop"* | Desktop Agent (Win32) |
| **Multimodal Vision** | *"Look at my screen and summarize this open document"* | Vision Agent (Llama 3.2-VL / Qwen-VL) |
| **System Diagnostics** | *"What processes are taking up the most RAM right now?"* | System Agent (psutil / WMI) |
| **Browser Workflow** | *"Open Chrome, search for latest AI papers, and open GitHub"* | Browser / Desktop Agent |
| **Pet & Life Sim** | *"Woody, start working on Python AI Coding"* / Feed food 🍲 / Pet head 💖 | VPet Engine & Graph State Machine |
| **Contextual Memory** | *"Where did I leave off on my machine learning project?"* | Episodic Memory & RAG |
| **Code Generation** | *"Write a Python script to convert all PNGs to WebP in this folder"* | Coding Agent (Sandbox REPL) |

---

## ⚙️ Configuration & Hardware Tiers

Woody automatically detects your system hardware on boot and configures the optimal tier. You can customize settings in [`config/woody_config.yaml`](config/woody_config.yaml):

```yaml
general:
  name: "Woody"
  tier: "auto"                 # auto | lite | standard | pro

perception:
  wake_word:
    enabled: true
    engine: "openwakeword"     # openwakeword | porcupine | disabled
    phrase: "hey woody"
  vad:
    enabled: true
    threshold: 0.55
  stt:
    model: "base"              # tiny | base | small | medium | large-v3

models:
  provider: "groq"             # groq | ollama | openai | gemini
  router: "openai/gpt-oss-20b"
  planner: "openai/gpt-oss-120b"
  vision: "llama-3.2-11b-vision-preview"

agents:
  desktop:
    enabled: true
  vision:
    enabled: true
  browser:
    enabled: true
```

| Tier | Minimum Specs | Models Used | STT Engine |
|---|---|---|---|
| **Lite** | Intel Core i5 / 8GB RAM (CPU only) | `qwen2.5:1.5b` / Groq Cloud | Whisper `tiny` / `base` |
| **Standard** | RTX 3060 / 16GB RAM / NPU | `qwen2.5:7b` + `nomic-embed` | Whisper `small` + Silero |
| **Pro** | RTX 4080+ / 32GB+ RAM | `qwen2.5:14b` + Qwen2.5-VL | Whisper `medium` / `large-v3` |

---

## 📂 Project Directory Structure

```
Wodi/
├── assets/                  # Banners, interface mockups, showcase imagery
├── config/                  # Default configurations (woody_config.yaml)
├── gifs/                    # Sprite fallback animation loops
├── scripts/                 # Automated setup & utility scripts (install.ps1)
├── tests/                   # Comprehensive pytest test suite
├── vpet/                    # Authentic VPet-Simulator Core assets & LPS files
│   └── VPet-main/           # 6,180+ frames, animations, item LPS, English dicts
└── woody/                   # Core Python package
    ├── agents/              # LangGraph multi-agent swarm (Desktop, Vision, System, Browser, Chat)
    ├── critic/              # Verification & self-correction engine
    ├── ipc/                 # Inter-process communication & event bus
    ├── kernel/              # Core lifecycle, configuration & hardware tier detection
    ├── memory/              # Vector RAG & episodic conversation memory
    ├── observability/       # Logging, tracing & evaluation harness
    ├── perception/          # Audio capture, wake word, VAD & screen capture hooks
    ├── planner/             # Task decomposition & LangGraph router
    ├── synthesis/           # Neural TTS audio pipeline (Inworld AI, Piper, Kokoro, Edge)
    ├── tools/               # Win32 automation, MCP host, browser & system tools
    └── ui/                  # Native PySide6, Liquid Glass WebEngine, & VPet Engine
        ├── desktop_pet.py   # Complete VPet Desktop Companion with Purple Theme
        ├── vpet_engine.py   # VPet life sim, RPG stats, jobs & LPS item parser
        ├── vpet_graph.py    # Frame-by-frame 25-action animation player
        └── web_overlay.py   # Liquid glass command center overlay
```

---

## 🔒 Security, Safety & Privacy

- **Local-First Privacy:** Sensitive data, screenshots, and audio can execute entirely on your local hardware.
- **Permission Tiers:** High-impact actions (file deletion, registry edits, system shutdown) require inline interactive user confirmation.
- **Prompt Injection Defense:** Screen OCR and clipboard inputs are treated as **untrusted data**, never direct instruction prompts.
- **Audit Logging:** Every planner step, tool execution, and agent response is logged to a local SQLite database for full transparency.

---

## 🗺️ Roadmap & Phase Milestones

| Phase | Description | Status |
|---|---|---|
| **Phase 0** | Wake word ("Hey Woody"), Silero VAD, Streaming STT, Audio Pipeline | ✅ Completed |
| **Phase 1** | LangGraph Planner, Desktop Agent, Win32 Automation, Critic Loop | ✅ Completed |
| **Phase 2** | Multimodal Vision Agent, Event-Driven Screen Hooks, OCR Grounding | ✅ Completed |
| **Phase 3** | Animated AI Desktop Pet Companion (`--pet`), Inworld Neural TTS-2 | ✅ Completed |
| **Phase 4** | Apple-Inspired Fluid Glassmorphism Command Center (`--web-ui`) | ✅ Completed |
| **Phase 5** | VPet Core Simulation Engine (6,180+ frames, 25 actions, 120+ items, jobs) | ✅ Completed |
| **Phase 6** | Browser Agent (Playwright), MCP Host Tools, Coding Sandbox | ✅ Completed |
| **Phase 7** | One-Click Signed Windows MSIX Installer & Auto-Updater | 🔲 Planned |

---

## 📄 License & Attribution

- Released under the **[MIT License](LICENSE)**.
- Built with ❤️ for Windows automation enthusiasts and AI agent builders.
- Special thanks to the open-source communities behind **[LorisYounger/VPet](https://github.com/LorisYounger/VPet)**, **LangGraph**, **Ollama**, **PySide6**, **Silero VAD**, **Faster-Whisper**, and **Inworld AI**.
