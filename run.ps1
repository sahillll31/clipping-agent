$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
$webDir = Join-Path $root "web"
$distIndex = Join-Path $webDir "dist\index.html"

if (-not (Test-Path $venvPy)) {
  Write-Host "First run - installing ClipForge toolchain..." -ForegroundColor Cyan
  & python (Join-Path $root "bootstrap.py")
}

if (-not (Test-Path (Join-Path $root "bin\ffmpeg.exe"))) {
  Write-Host "ffmpeg missing - running setup..." -ForegroundColor Yellow
  & $venvPy (Join-Path $root "bootstrap.py")
}

if (-not (Test-Path $distIndex)) {
  if (Get-Command npm -ErrorAction SilentlyContinue) {
    Write-Host "Building the web UI..." -ForegroundColor Cyan
    Push-Location $webDir
    try {
      if (-not (Test-Path (Join-Path $webDir "node_modules"))) {
        npm install --no-audit --no-fund
      }
      npm run build
    } finally {
      Pop-Location
    }
  } else {
    Write-Host "npm not found - serving the legacy UI. Install Node.js for the React app." -ForegroundColor Yellow
  }
}

Set-Location $root
& $venvPy (Join-Path $root "server.py")
