# Wodi Installation Script for Windows
# Run as: .\scripts\install.ps1
# Requires: Python 3.12+, internet connection

param(
    [string]$Tier = "auto",   # auto | lite | standard | pro
    [switch]$SkipOllama,
    [switch]$SkipModels
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║     Wodi v3.0 Installation Script    ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Check Python ─────────────────────────────────────────────────────────────
Write-Host "[1/6] Checking Python 3.12..." -ForegroundColor Yellow
try {
    $pyver = python --version 2>&1
    if ($pyver -notmatch "3\.1[2-9]|3\.[2-9]\d") {
        Write-Host "      Python 3.12+ required. Found: $pyver" -ForegroundColor Red
        Write-Host "      Download: https://python.org/downloads/" -ForegroundColor Gray
        exit 1
    }
    Write-Host "      OK: $pyver" -ForegroundColor Green
} catch {
    Write-Host "      Python not found! Install from https://python.org" -ForegroundColor Red
    exit 1
}

# ── Install pip dependencies ──────────────────────────────────────────────────
Write-Host "[2/6] Installing Python dependencies..." -ForegroundColor Yellow
Write-Host "      This may take several minutes on first install." -ForegroundColor Gray

# Install core deps
python -m pip install --upgrade pip --quiet
python -m pip install -e ".[dev]" --quiet

Write-Host "      Dependencies installed." -ForegroundColor Green

# ── Check/Install Ollama ──────────────────────────────────────────────────────
if (-not $SkipOllama) {
    Write-Host "[3/6] Checking Ollama..." -ForegroundColor Yellow
    $ollamaInstalled = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollamaInstalled) {
        Write-Host "      Ollama not found. Downloading installer..." -ForegroundColor Yellow
        $installerUrl = "https://ollama.com/download/OllamaSetup.exe"
        $installerPath = "$env:TEMP\OllamaSetup.exe"
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
        Write-Host "      Running Ollama installer..." -ForegroundColor Gray
        Start-Process -FilePath $installerPath -Wait
        Write-Host "      Ollama installed." -ForegroundColor Green
    } else {
        Write-Host "      OK: Ollama found" -ForegroundColor Green
    }
} else {
    Write-Host "[3/6] Skipping Ollama check (--SkipOllama)" -ForegroundColor Gray
}

# ── Detect hardware tier ──────────────────────────────────────────────────────
Write-Host "[4/6] Detecting hardware tier..." -ForegroundColor Yellow
$detectedTier = python -c "
from wodi.utils.hardware import detect_hardware
hw = detect_hardware()
print(hw.tier.value)
" 2>&1

if ($Tier -eq "auto") {
    $Tier = $detectedTier
}
Write-Host "      Tier: $Tier (RAM, GPU detected)" -ForegroundColor Green

# ── Pull Ollama models ────────────────────────────────────────────────────────
if (-not $SkipModels) {
    Write-Host "[5/6] Pulling Ollama models for '$Tier' tier..." -ForegroundColor Yellow

    $modelMap = @{
        "lite"     = @("qwen2.5:0.5b", "qwen2.5:1.5b")
        "standard" = @("qwen2.5:7b", "qwen2.5:1.5b", "nomic-embed-text")
        "pro"      = @("qwen2.5:32b", "llama3.1:8b", "qwen2.5:3b", "nomic-embed-text")
    }

    $models = $modelMap[$Tier]
    if (-not $models) { $models = $modelMap["standard"] }

    foreach ($model in $models) {
        Write-Host "      Pulling $model ..." -ForegroundColor Gray
        ollama pull $model
    }

    Write-Host "      Models ready." -ForegroundColor Green
} else {
    Write-Host "[5/6] Skipping model pull (--SkipModels)" -ForegroundColor Gray
}

# ── Create data directory ─────────────────────────────────────────────────────
Write-Host "[6/6] Creating Wodi data directory..." -ForegroundColor Yellow
$dataDir = "$env:USERPROFILE\.wodi"
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir | Out-Null
}
New-Item -ItemType Directory -Path "$dataDir\models\tts" -Force | Out-Null

Write-Host ""
Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║        Installation Complete!        ║" -ForegroundColor Green
Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "  1. Start Ollama:    ollama serve" -ForegroundColor Gray
Write-Host "  2. Start Wodi:      python -m wodi" -ForegroundColor Gray
Write-Host "  3. Headless mode:   wodi --kernel-only" -ForegroundColor Gray
Write-Host "  4. Run eval suite:  wodi --eval" -ForegroundColor Gray
Write-Host ""
Write-Host "  Optional: Download TTS model for voice output:" -ForegroundColor White
Write-Host "  https://huggingface.co/rhasspy/piper-voices" -ForegroundColor Gray
Write-Host "  Place .onnx + .onnx.json in: $dataDir\models\tts\" -ForegroundColor Gray
Write-Host ""
