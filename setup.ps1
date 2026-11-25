param(
  [switch]$Cuda,
  [string]$Model = "small.en"
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# Prefer a venv python if it already exists, otherwise the system python.
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path $venvPy) { $py = $venvPy } else { $py = "python" }

$argsList = @((Join-Path $root "bootstrap.py"), "--model", $Model)
if ($Cuda) { $argsList += "--cuda" }

& $py @argsList
