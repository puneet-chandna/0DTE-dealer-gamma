# Controlled launcher check for PowerShell on Linux; native commands and TCP are stubbed.
# Run with pwsh -File this-script -Source scripts/start_app.ps1 -Case sqlite-default.
param([string]$Source = (Join-Path $PSScriptRoot "../../scripts/start_app.ps1"), [string]$Case = "sqlite-default")
$ErrorActionPreference = "Stop"
$root = Join-Path ([System.IO.Path]::GetTempPath()) ("odte-launcher-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force "$root/scripts", "$root/backend/.venv/Scripts", "$root/frontend", "$root/bin" | Out-Null
Copy-Item $Source "$root/scripts/start_app.ps1"
Set-Content "$root/scripts/read_env.py" "# Shared-reader invocation stub"
$python = @'
#!/bin/sh
printf '%s\n' "$*" >> "$ODTE_PROBE_PYTHON_LOG"
case "$1" in
  */read_env.py) printf '%s\n' "${TEST_DATABASE_URL:-$4}"; exit "${TEST_HELPER_EXIT:-0}" ;;
  -m) exit "${TEST_MIGRATION_EXIT:-0}" ;;
  *) exit 99 ;;
esac
'@
Set-Content "$root/backend/.venv/Scripts/python.exe" $python
Set-Content "$root/bin/pnpm" "#!/bin/sh`nexit 0"
Set-Content "$root/bin/psql" "#!/bin/sh`nexit 0"
& /bin/chmod +x "$root/backend/.venv/Scripts/python.exe" "$root/bin/pnpm" "$root/bin/psql"
$env:PATH = "$root/bin`:$env:PATH"
$env:ODTE_PROBE_PYTHON_LOG = "$root/python.log"
$env:TEST_DATABASE_URL = ""
$env:TEST_HELPER_EXIT = "0"
$env:TEST_MIGRATION_EXIT = "0"
$script:Launches = @()
$script:Ports = @()
$script:PsqlLookups = 0
$expectedFailure = $false
switch ($Case) {
    "sqlite-default" {}
    "sqlite-reader" {
        Set-Content "$root/backend/.env" 'export DATABASE_URL = "sqlite+aiosqlite:///./quoted file.db" # local'
        $env:TEST_DATABASE_URL = "sqlite+aiosqlite:///./quoted file.db"
    }
    "postgres-local" { $env:TEST_DATABASE_URL = "postgresql+asyncpg://localhost:55432/test" }
    "postgres-external" { $env:TEST_DATABASE_URL = "postgres://remote.example.test:5432/test" }
    "invalid-reader" { $env:TEST_HELPER_EXIT = "2"; $expectedFailure = $true }
    "failed-migration" { $env:TEST_MIGRATION_EXIT = "17"; $expectedFailure = $true }
    default { throw "Unknown probe case: $Case" }
}
function Start-Process {
    param([string]$FilePath, [string[]]$ArgumentList)
    $script:Launches += ($ArgumentList -join "`n")
}
function Get-Command {
    param([string]$Name, [string]$ErrorAction)
    if ($Name -eq "psql") { $script:PsqlLookups++ }
    Microsoft.PowerShell.Core\Get-Command $Name -ErrorAction SilentlyContinue
}
function New-Object {
    param([string]$TypeName)
    if ($TypeName -ne "System.Net.Sockets.TcpClient") { throw "Unexpected object: $TypeName" }
    $handle = [pscustomobject]@{}
    Add-Member -InputObject $handle -MemberType ScriptMethod -Name WaitOne -Value { param($timeout) return $true }
    $client = [pscustomobject]@{ Handle = $handle }
    Add-Member -InputObject $client -MemberType ScriptMethod -Name BeginConnect -Value {
        param($HostName, $Port, $callback, $state)
        $script:Ports += "${HostName}:$Port"
        return [pscustomobject]@{ AsyncWaitHandle = $this.Handle }
    }
    Add-Member -InputObject $client -MemberType ScriptMethod -Name EndConnect -Value { param($async) }
    Add-Member -InputObject $client -MemberType ScriptMethod -Name Close -Value {}
    return $client
}
$caught = $null
try { . "$root/scripts/start_app.ps1" } catch { $caught = $_ }
if ($expectedFailure) {
    if (-not $caught) { throw "Expected launcher failure for $Case" }
    if ($script:Launches.Count) { throw "Launched services after a failure" }
    if ($Case -eq "failed-migration" -and "$caught" -notmatch "migrations failed.*17") {
        throw "Expected migration exit 17, got $caught"
    }
} else {
    if ($caught) { throw $caught }
    if ($script:Launches.Count -ne 2) { throw "Expected two app terminals" }
    if (($script:Launches -join "`n") -match "alembic") { throw "Migrations run twice" }
    if ($Case -like "sqlite-*") {
        if ($script:PsqlLookups -or $script:Ports.Count) { throw "SQLite attempted PostgreSQL discovery or TCP wait" }
    } else {
        $expectedPort = if ($Case -eq "postgres-local") { "localhost:55432" } else { "remote.example.test:5432" }
        if ($script:Ports.Count -ne 1 -or $script:Ports[0] -ne $expectedPort) {
            throw "Wrong PostgreSQL endpoint: $($script:Ports)"
        }
    }
}
$calls = @(Get-Content $env:ODTE_PROBE_PYTHON_LOG)
if ($calls[0] -notmatch "read_env.py .* DATABASE_URL sqlite\+aiosqlite://") {
    throw "Launcher did not use the shared reader and SQLite default: $($calls[0])"
}
$migrationCalls = @($calls | Where-Object { $_ -match "^-m alembic upgrade head$" })
$expectedMigrations = if ($Case -eq "invalid-reader") { 0 } else { 1 }
if ($migrationCalls.Count -ne $expectedMigrations) { throw "Unexpected migration count" }
"PASS $Case (PowerShell runtime, mocked native commands and TCP)"
