param(
    [Parameter(Position = 0)]
    [string]$Mode = "run"
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

function Show-Usage {
    @"
usage: ./script/codex_action.ps1 [mode]

Modes:
  run, serve           Start the local FastAPI app with uvicorn
  test                 Run the pytest suite
  publish-prod         Run tests, then deploy the linked Vercel project to production
  vercel-status        Print the linked Vercel project metadata
  help, --help, -h     Show this help
"@
}

function Get-PythonCommand {
    $venvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return $pythonCmd.Source
    }

    throw "Python was not found. Create .venv or install Python on PATH."
}

function Get-VercelCommand {
    $vercelCmd = Get-Command vercel -ErrorAction SilentlyContinue
    if ($vercelCmd) {
        return @($vercelCmd.Source)
    }

    $npxCmd = Get-Command npx -ErrorAction SilentlyContinue
    if ($npxCmd) {
        return @($npxCmd.Source, "vercel")
    }

    throw "Vercel CLI was not found. Install it globally or make npx available."
}

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$CommandParts
    )

    $command = $CommandParts[0]
    $arguments = @()
    if ($CommandParts.Length -gt 1) {
        $arguments = $CommandParts[1..($CommandParts.Length - 1)]
    }

    & $command @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $($CommandParts -join ' ')"
    }
}

switch ($Mode) {
    "run" {
        $python = @(Get-PythonCommand)
        Invoke-ExternalCommand -CommandParts ($python + @("-m", "uvicorn", "app.main:app", "--reload"))
    }
    "serve" {
        $python = @(Get-PythonCommand)
        Invoke-ExternalCommand -CommandParts ($python + @("-m", "uvicorn", "app.main:app", "--reload"))
    }
    "test" {
        $python = @(Get-PythonCommand)
        Invoke-ExternalCommand -CommandParts ($python + @("-m", "pytest"))
    }
    "publish-prod" {
        if (-not (Test-Path (Join-Path $RootDir ".vercel\project.json"))) {
            throw "This repo is not linked to a Vercel project. Run 'vercel link' first."
        }

        $python = @(Get-PythonCommand)
        Invoke-ExternalCommand -CommandParts ($python + @("-m", "pytest"))

        $vercel = @(Get-VercelCommand)
        Invoke-ExternalCommand -CommandParts ($vercel + @("deploy", "--prod"))
    }
    "vercel-status" {
        $projectFile = Join-Path $RootDir ".vercel\project.json"
        if (-not (Test-Path $projectFile)) {
            throw "Missing .vercel\project.json. Run 'vercel link' first."
        }

        Get-Content $projectFile
    }
    "help" {
        Show-Usage
    }
    "--help" {
        Show-Usage
    }
    "-h" {
        Show-Usage
    }
    default {
        Show-Usage
        throw "Unknown mode: $Mode"
    }
}
