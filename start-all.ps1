# Arranca TODO de una vez: Ollama + servidor web + bot de Telegram + avatar (overlay).
# Uso:  .\start-all.ps1
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $py)) {
    Write-Host "[!] No se encontro: $py" -ForegroundColor Red
    Write-Host "    Crea el entorno virtual e instala las dependencias:" -ForegroundColor Yellow
    Write-Host "      python -m venv .venv"
    Write-Host "      .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt"
    exit 1
}

# 1) Ollama (LLM)
if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) {
    Write-Host "[>] Arrancando Ollama..." -ForegroundColor Cyan
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
} else {
    Write-Host "[i] Ollama ya esta en ejecucion." -ForegroundColor DarkGray
}

# 2) Servidor web (backend + avatar) en su propia ventana.
#    Nota: la ruta puede contener espacios -> hay que entrecomillarla.
$webScript = Join-Path $root "start-web.ps1"
Write-Host "[>] Abriendo servidor web..." -ForegroundColor Cyan
Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$webScript`""

# Esperar a que el backend responda antes de lanzar el avatar.
Write-Host "[>] Esperando al servidor web..." -ForegroundColor Cyan
$listo = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        Invoke-WebRequest "http://127.0.0.1:8000/status" -UseBasicParsing -TimeoutSec 2 | Out-Null
        $listo = $true; break
    } catch { Start-Sleep -Seconds 1 }
}
if ($listo) {
    Write-Host "[ok] Servidor web listo." -ForegroundColor Green
} else {
    Write-Host "[!] El servidor web no respondio en 40s. Revisa su ventana." -ForegroundColor Yellow
}

# 3) Bot de Telegram en su propia ventana.
$tgScript = Join-Path $root "start-telegram.ps1"
Write-Host "[>] Abriendo bot de Telegram..." -ForegroundColor Cyan
Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$tgScript`""

# 4) Avatar (overlay Electron).
if (Test-Path -LiteralPath (Join-Path $root "avatar\node_modules")) {
    Write-Host "[>] Abriendo avatar (overlay)..." -ForegroundColor Cyan
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "npm start" `
        -WorkingDirectory (Join-Path $root "avatar")
} else {
    Write-Host "[!] Faltan dependencias del avatar. Ejecuta:  cd avatar; npm install" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[ok] Todo lanzado. Cierra cada ventana (o Ctrl+C) para detener." -ForegroundColor Green
