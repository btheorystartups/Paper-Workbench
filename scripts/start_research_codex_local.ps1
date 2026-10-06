param(
    [ValidateRange(1, 65535)][int]$Port = 8769
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$worker = Join-Path $projectRoot 'src\workbench\providers\research_codex_worker.py'
$database = Join-Path $projectRoot 'data\workbench.sqlite3'
$profile = Join-Path $env:USERPROFILE '.paper-workbench-codex'
foreach ($required in @($python, $worker, $database, $profile)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required local research component is missing: $required"
    }
}

# This launcher uses the authorized local database and a dedicated ChatGPT profile.
# It never reads .env files and keeps the local preview on loopback.
$env:PYTHONPATH = Join-Path $projectRoot 'src'
$env:WB_LOAD_DOTENV = 'false'
$env:WB_DEPLOYMENT_MODE = 'local'
$env:WB_PROVIDER_MODE = 'fake'
$env:WB_AUTH_REQUIRED = 'false'
$env:WB_DATABASE_URL = 'sqlite:///' + ($database -replace '\\', '/')
$env:WB_DATA_DIR = Join-Path $projectRoot 'data'
$env:WB_RUN_MIGRATIONS_ON_STARTUP = 'false'
$env:WB_RESEARCH_EXECUTOR_ENABLED = 'true'
$env:WB_RESEARCH_EXECUTOR_COMMAND = ConvertTo-Json -Compress @($python, $worker)
$env:WB_RESEARCH_CODEX_HOME = $profile
$env:WB_RESEARCH_CODEX_ACCOUNT_EMAIL = ''
# Author/general workers; specialist roles use the Astra policy independently.
$env:WB_RESEARCH_CODEX_MODEL = 'gpt-5.5'
$env:WB_RESEARCH_CODEX_REASONING_EFFORT = 'low'

Set-Location -LiteralPath $projectRoot
& $python -m uvicorn workbench.main:app --host 127.0.0.1 --port $Port
