$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$BackendPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$DefaultDatabaseUrl = "postgresql+asyncpg://odte_user:odte_password@127.0.0.1:55432/odte_gex"

function Get-EnvValue {
    param(
        [string]$FilePath,
        [string]$Name,
        [string]$DefaultValue = ""
    )

    if (-not (Test-Path $FilePath)) {
        return $DefaultValue
    }

    foreach ($line in Get-Content $FilePath) {
        if ($line -match "^\s*$Name=(.*)$") {
            return $Matches[1].Trim()
        }
    }

    return $DefaultValue
}

function Wait-ForPort {
    param(
        [string]$HostName,
        [int]$Port
    )

    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $async = $client.BeginConnect($HostName, $Port, $null, $null)
            if ($async.AsyncWaitHandle.WaitOne(1000)) {
                $client.EndConnect($async)
                $client.Close()
                return
            }
            $client.Close()
        } catch {
        }
        Start-Sleep -Seconds 1
    }

    throw "Database did not become reachable at ${HostName}:${Port}."
}

function Write-ColorLine {
    param(
        [string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::White
    )

    Write-Host $Message -ForegroundColor $Color
}

function Show-WindowsGuidance {
    param(
        [string]$Reason
    )

    Write-ColorLine ""
    Write-ColorLine "Native Windows note:" Yellow
    Write-ColorLine "This project's standard local database flow is Linux/WSL/Git Bash with scripts/start_app.sh." Cyan
    Write-ColorLine $Reason Red
    Write-ColorLine ""
    Write-ColorLine "Recommended paths:" Green
    Write-ColorLine "1. Use WSL or Git Bash and run: ./scripts/start_app.sh" Green
    Write-ColorLine "2. Or install PostgreSQL 17 on Windows, start the server manually, and point backend/.env DATABASE_URL to that running database." Green
    Write-ColorLine ""
    Write-ColorLine "Windows PostgreSQL checklist:" Yellow
    Write-ColorLine "- Install PostgreSQL 17" Yellow
    Write-ColorLine "- Make sure the PostgreSQL service is running" Yellow
    Write-ColorLine "- Create a database/user that matches backend/.env, or update DATABASE_URL" Yellow
    Write-ColorLine "- Re-run this launcher after the database is reachable" Yellow
}

if (-not (Test-Path $BackendPython)) {
    throw "Backend virtual environment is missing: $BackendPython"
}

if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    throw "pnpm is not installed or not on PATH."
}

$envFile = Join-Path $BackendDir ".env"
$databaseUrl = Get-EnvValue -FilePath $envFile -Name "DATABASE_URL" -DefaultValue $DefaultDatabaseUrl
$normalizedUrl = $databaseUrl -replace '^postgresql\+asyncpg://', 'postgresql://'
$databaseUri = [System.Uri]$normalizedUrl
$dbHost = $databaseUri.Host
$dbPort = if ($databaseUri.Port -gt 0) { $databaseUri.Port } else { 5432 }

$isLocalDatabase = $dbHost -eq "localhost" -or $dbHost -eq "127.0.0.1"
$psqlInstalled = [bool](Get-Command psql -ErrorAction SilentlyContinue)

if ($isLocalDatabase -and -not $psqlInstalled) {
    Show-WindowsGuidance "PostgreSQL does not appear to be installed on this Windows machine."
    exit 1
}

try {
    Write-Host "Waiting for database at ${dbHost}:${dbPort} ..."
    Wait-ForPort -HostName $dbHost -Port $dbPort
} catch {
    if ($isLocalDatabase) {
        Show-WindowsGuidance "A local PostgreSQL server is not reachable at ${dbHost}:${dbPort}."
        exit 1
    }

    throw
}

if ($isLocalDatabase) {
    Write-ColorLine "Local PostgreSQL is reachable. Continuing with backend and frontend startup." Green
} else {
    Write-Host "External database configured at ${dbHost}:${dbPort}."
}

Write-Host "Running backend migrations..."
Push-Location $BackendDir
& $BackendPython -m alembic upgrade head
Pop-Location

$backendCommand = @"
Set-Location '$BackendDir'
& '.\.venv\Scripts\python.exe' -m alembic upgrade head
& '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --reload
"@

$frontendCommand = @"
Set-Location '$FrontendDir'
pnpm dev
"@

Start-Process powershell.exe -ArgumentList @("-NoExit", "-Command", $backendCommand) | Out-Null
Start-Process powershell.exe -ArgumentList @("-NoExit", "-Command", $frontendCommand) | Out-Null

Write-Host "All services launched."
Write-Host "  Backend: http://localhost:8000"
Write-Host "  Frontend: http://localhost:3000"
