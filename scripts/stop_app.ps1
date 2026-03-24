$ErrorActionPreference = "Stop"

function Write-ColorLine {
    param(
        [string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::White
    )

    Write-Host $Message -ForegroundColor $Color
}

Write-ColorLine ""
Write-ColorLine "Native Windows note:" Yellow
Write-ColorLine "The repo-standard stop flow is to use WSL or Git Bash and run: ./scripts/stop_app.sh" Cyan
Write-ColorLine "That stops frontend first, backend second, and PostgreSQL last." Green
Write-ColorLine ""
Write-ColorLine "If you started the app from native PowerShell, stop the backend and frontend windows first, then stop PostgreSQL from your Windows PostgreSQL service or pg_ctl setup." Yellow
Write-ColorLine "No automatic native Windows stop orchestration is configured for the local PostgreSQL flow yet." Red
