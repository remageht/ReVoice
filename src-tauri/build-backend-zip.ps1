# ReVoice pre-bundle script. Resolves repo root from its own location,
# so it works regardless of the invoker's working directory.
# 1) builds the React frontend, 2) zips backend/revoice -> src-tauri/backend.zip
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$tauriDir = $PSScriptRoot

Write-Output "[revoice] frontend build..."
& npm.cmd run build --prefix (Join-Path $root "app")
if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }

Write-Output "[revoice] zipping backend..."
$src = Join-Path $root "backend\revoice"
$dst = Join-Path $tauriDir "backend.zip"
if (!(Test-Path $src)) { throw "backend source missing: $src" }
Remove-Item -Force $dst -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $src "*") -DestinationPath $dst -Force
Write-Output "[revoice] backend.zip ready"
