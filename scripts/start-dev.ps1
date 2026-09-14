$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"

function Resolve-NpmCommand {
  $npm = Get-Command npm -ErrorAction SilentlyContinue
  if ($npm) {
    return $npm.Source
  }

  $defaultNpm = Join-Path $env:ProgramFiles "nodejs\npm.cmd"
  if (Test-Path $defaultNpm) {
    return $defaultNpm
  }

  throw "npm was not found. Install Node.js LTS, then run scripts\setup-dev.ps1."
}

function Add-NodeToPath {
  $defaultNodeDir = Join-Path $env:ProgramFiles "nodejs"
  if (Test-Path (Join-Path $defaultNodeDir "node.exe")) {
    $env:Path = "$defaultNodeDir;$env:Path"
  }
}

if (-not (Test-Path $VenvPython)) {
  throw "Backend virtual environment not found. Run scripts\setup-dev.ps1 first."
}

Add-NodeToPath
$npm = Resolve-NpmCommand

Write-Host "Starting backend: http://127.0.0.1:8000"
$backendJob = Start-Job -Name competitive-analysis-backend -ScriptBlock {
  Set-Location $using:BackendDir
  & $using:VenvPython main.py
}

Write-Host "Starting frontend: http://127.0.0.1:5173"
$frontendJob = Start-Job -Name competitive-analysis-frontend -ScriptBlock {
  Set-Location $using:FrontendDir
  $nodeDir = Split-Path -Parent $using:npm
  $env:Path = "$nodeDir;$env:Path"
  & $using:npm run dev -- --host 127.0.0.1
}

Write-Host ""
Write-Host "Both services are starting. Press Ctrl+C to stop."
Write-Host "Backend health: http://127.0.0.1:8000/health"
Write-Host "Frontend:       http://127.0.0.1:5173"
Write-Host ""

try {
  while ($true) {
    Receive-Job -Job $backendJob -ErrorAction SilentlyContinue
    Receive-Job -Job $frontendJob -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
  }
} finally {
  Stop-Job -Job $backendJob, $frontendJob -ErrorAction SilentlyContinue
  Remove-Job -Job $backendJob, $frontendJob -ErrorAction SilentlyContinue
}
