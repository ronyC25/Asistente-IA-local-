# Descarga los assets del avatar (librerias JS, Cubism Core, perfil wLipSync y modelo Haru).
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
  # Cubism Core 4.2.2 (soporta moc3 v4). Haru es Cubism 4.
  (Join-Path $vendor "live2dcubismcore.min.js")             = "https://cdn.jsdelivr.net/npm/live2dcubismcore@1.0.2/live2dcubismcore.min.js"
  (Join-Path $root "public\lipsync\profile.json")           = "https://raw.githubusercontent.com/mrxz/wLipSync/main/example/profile.json"
}
Write-Host "Descargando librerias..."
foreach ($k in $files.Keys) { Invoke-WebRequest -Uri $files[$k] -OutFile $k; Write-Host "  $k" }

Write-Host "Descargando modelo Haru (Cubism 4, asset de pixi-live2d-display)..."
$repo = "guansss/pixi-live2d-display"
$sub = "test/assets/haru"
$base = "https://raw.githubusercontent.com/$repo/master/$sub/"
$dst = Join-Path $root "public\models\Haru"
$tree = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/git/trees/master?recursive=1" -Headers @{ "User-Agent"="jarvis" } -TimeoutSec 90
$filesToGet = $tree.tree | Where-Object { $_.type -eq "blob" -and $_.path -like "$sub/*" } | Select-Object -ExpandProperty path
foreach ($f in $filesToGet) {
  $rel = $f.Substring($sub.Length + 1)
  $target = Join-Path $dst $rel
  New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
  Invoke-WebRequest -Uri ($base + $rel) -OutFile $target
  Write-Host "  $rel"
}

Write-Host "Assets del avatar listos (modelo Haru)."
