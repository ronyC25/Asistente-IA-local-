# Lanzador del asistente: usa SIEMPRE el Python del entorno virtual (.venv).
# Uso:  .\start.ps1 -Mode web|telegram|voice|cli   (por defecto: web)
param(
    [ValidateSet("web", "telegram", "voice", "cli")]
    [string]$Mode = "web"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $py)) {
    Write-Host "[!] No se encontro: $py" -ForegroundColor Red
    Write-Host "    Crea el entorno virtual e instala las dependencias:" -ForegroundColor Yellow
    Write-Host "      python -m venv .venv"
    Write-Host "      .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt"
    Write-Host "      .\.venv\Scripts\python.exe -m pip install -r requirements-voice.txt   # opcional (voz)"
    exit 1
}

Set-Location -LiteralPath $root

if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) {
    Write-Host "[i] Ollama no parece estar en ejecucion. Arrancalo ('ollama serve') si el asistente no responde." -ForegroundColor Yellow
}

$pyArgs = switch ($Mode) {
    "web"      { @("-m", "src.main", "--web") }
    "telegram" { @("-m", "src.main", "--telegram") }
    "voice"    { @("-m", "src.main", "--voice") }
    "cli"      { @("-m", "src.main") }
}

Write-Host "[>] Modo '$Mode' con $py" -ForegroundColor Cyan
& $py @pyArgs
