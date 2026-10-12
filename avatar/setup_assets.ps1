# Descarga los assets del avatar (librerias JS, Cubism Core, perfil wLipSync y modelo Mao).
# Uso:  powershell -ExecutionPolicy Bypass -File avatar\setup_assets.ps1
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$root = $PSScriptRoot
$vendor = Join-Path $root "vendor"
New-Item -ItemType Directory -Force -Path $vendor, (Join-Path $root "public\lipsync"), (Join-Path $root "public\models") | Out-Null

$files = @{
  (Join-Path $vendor "pixi.min.js")                         = "https://cdn.jsdelivr.net/npm/pixi.js@7.4.2/dist/pixi.min.js"
  (Join-Path $vendor "pixi-live2d-display-cubism4.min.js")  = "https://cdn.jsdelivr.net/npm/pixi-live2d-display@0.4.0/dist/cubism4.min.js"
  (Join-Path $vendor "wlipsync-single.js")                  = "https://cdn.jsdelivr.net/npm/wlipsync@1.3.0/dist/wlipsync-single.js"
  (Join-Path $vendor "live2dcubismcore.min.js")             = "https://cdn.jsdelivr.net/npm/live2dcubismcore@1.0.2/live2dcubismcore.min.js"
  (Join-Path $root "public\lipsync\profile.json")           = "https://raw.githubusercontent.com/mrxz/wLipSync/main/example/profile.json"
}
Write-Host "Descargando librerias..."
foreach ($k in $files.Keys) { Invoke-WebRequest -Uri $files[$k] -OutFile $k; Write-Host "  $k" }

Write-Host "Descargando modelo Mao (CubismWebSamples)..."
$tmp = Join-Path $env:TEMP "cws_jarvis"
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
git clone --no-checkout --depth 1 --filter=blob:none https://github.com/Live2D/CubismWebSamples.git $tmp
git -C $tmp sparse-checkout init --cone
git -C $tmp sparse-checkout set Samples/Resources/Mao
git -C $tmp checkout
Copy-Item -Recurse -Force (Join-Path $tmp "Samples\Resources\Mao\*") (Join-Path $root "public\models\Mao")
Remove-Item -Recurse -Force $tmp

Write-Host "Assets del avatar listos."
