param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$WithLocalPostgres,
    [switch]$WithRedis,
    [switch]$SkipDocker,
    [switch]$SkipMigrations,
    [switch]$NoSync
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-CommandExists {
    param([string]$Name)
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Split-Path -Parent $ScriptDir
Set-Location $BackendDir

Write-Step "Checking required commands"
if (-not (Test-CommandExists "uv")) {
    throw "uv is not installed or not in PATH. Install uv first, then rerun this script."
}

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env from .env.example. Check LLM and DATABASE_URL values before production use." -ForegroundColor Yellow
    } else {
        throw ".env is missing and .env.example was not found."
    }
}

if (-not $NoSync) {
    Write-Step "Installing/updating Python dependencies with uv"
    uv sync
}

if (-not $SkipDocker) {
    Write-Step "Checking Docker"
    if (-not (Test-CommandExists "docker")) {
        throw "Docker CLI is not installed or not in PATH. Install Docker Desktop or rerun with -SkipDocker if Chroma is already available."
    }

    $dockerOk = $false
    try {
        docker version *> $null
        $dockerOk = $true
    } catch {
        $dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        if (Test-Path $dockerDesktop) {
            Write-Host "Docker Engine is not ready. Starting Docker Desktop..." -ForegroundColor Yellow
            Start-Process -FilePath $dockerDesktop | Out-Null
            for ($i = 0; $i -lt 60; $i++) {
                Start-Sleep -Seconds 2
                try {
                    docker version *> $null
                    $dockerOk = $true
                    break
                } catch {
                    Write-Host "." -NoNewline
                }
            }
            Write-Host ""
        }
    }

    if (-not $dockerOk) {
        throw "Docker Engine is not available. Start Docker Desktop manually or rerun with -SkipDocker."
    }

    $services = @("chroma")
    if ($WithLocalPostgres) {
        $services += "db"
    }
    if ($WithRedis) {
        $services += "redis"
    }

    Write-Step "Starting Docker services: $($services -join ', ')"
    docker compose up -d $services
}

if (-not $SkipMigrations) {
    Write-Step "Running PostgreSQL migrations"
    uv run python -m alembic upgrade head
}

Write-Step "Starting backend"
Write-Host "Backend URL: http://$HostAddress`:$Port" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Yellow
uv run python -m uvicorn src.main:app --host $HostAddress --port $Port
