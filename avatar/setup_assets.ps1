# Descarga los assets del avatar (librerias JS, Cubism Core, perfil wLipSync y modelos).
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
  # Cubism Core 4.2.2 (soporta moc3 v3/v4: Cubism 3 y 4).
  (Join-Path $vendor "live2dcubismcore.min.js")             = "https://cdn.jsdelivr.net/npm/live2dcubismcore@1.0.2/live2dcubismcore.min.js"
  (Join-Path $root "public\lipsync\profile.json")           = "https://raw.githubusercontent.com/mrxz/wLipSync/main/example/profile.json"
}
Write-Host "Descargando librerias..."
foreach ($k in $files.Keys) { Invoke-WebRequest -Uri $files[$k] -OutFile $k; Write-Host "  $k" }

# Descarga un modelo de ejemplo oficial (Live2D/CubismWebSamples, Cubism 3/4).
function Get-CubismSampleModel {
  param([string]$Name)
  $repo = "Live2D/CubismWebSamples"
  $branch = "develop"
  $sub = "Samples/Resources/$Name"
  $base = "https://raw.githubusercontent.com/$repo/$branch/$sub/"
  $dst = Join-Path $root "public\models\$Name"
  Write-Host "Descargando modelo $Name (CubismWebSamples)..."
  $tree = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/git/trees/$branch`?recursive=1" -Headers @{ "User-Agent"="jarvis" } -TimeoutSec 90
  $filesToGet = $tree.tree | Where-Object { $_.type -eq "blob" -and $_.path -like "$sub/*" } | Select-Object -ExpandProperty path
  foreach ($f in $filesToGet) {
    $rel = $f.Substring($sub.Length + 1)
    $target = Join-Path $dst $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
    Invoke-WebRequest -Uri ($base + $rel) -OutFile $target
    Write-Host "  $rel"
  }
}

# Haru (Cubism 3): modelo recortado de los test assets de pixi-live2d-display.
Write-Host "Descargando modelo Haru (Cubism 3)..."
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

# Wanko (Cubism 3): perrito chibi. LipSync = PARAM_MOUTH_OPEN_Y.
Get-CubismSampleModel -Name "Wanko"

Write-Host "Assets del avatar listos (Haru, Wanko)."
