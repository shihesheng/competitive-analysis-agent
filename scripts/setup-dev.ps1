param(
  [switch]$SkipBackend,
  [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"

function Resolve-PythonCommand {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return @{ Command = $python.Source; Args = @() }
  }

  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    return @{ Command = $py.Source; Args = @("-3") }
  }

  throw "Python was not found. Install Python 3.11+ or add it to PATH."
}

function Resolve-NpmCommand {
  $npm = Get-Command npm -ErrorAction SilentlyContinue
  if ($npm) {
    return $npm.Source
  }

  $defaultNpm = Join-Path $env:ProgramFiles "nodejs\npm.cmd"
  if (Test-Path $defaultNpm) {
    return $defaultNpm
  }

  throw "npm was not found. Install Node.js LTS, then rerun this script."
}

function Add-NodeToPath {
  $defaultNodeDir = Join-Path $env:ProgramFiles "nodejs"
  if (Test-Path (Join-Path $defaultNodeDir "node.exe")) {
    $env:Path = "$defaultNodeDir;$env:Path"
  }
}

if (-not $SkipBackend) {
  $pythonCmd = Resolve-PythonCommand

  if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating backend virtual environment..."
    & $pythonCmd.Command @($pythonCmd.Args + @("-m", "venv", (Join-Path $BackendDir ".venv")))
  }

  Write-Host "Installing backend dependencies..."
  & $VenvPython -m pip install --upgrade pip
  & $VenvPython -m pip install -r (Join-Path $BackendDir "requirements.txt")
}

if (-not $SkipFrontend) {
  Add-NodeToPath
  $npm = Resolve-NpmCommand

  Write-Host "Installing frontend dependencies..."
  Push-Location $FrontendDir
  try {
    & $npm install --registry=https://registry.npmmirror.com --no-audit --no-fund
  } finally {
    Pop-Location
  }
}

Write-Host "Development dependencies are ready."
