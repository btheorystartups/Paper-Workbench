param(
    [ValidateRange(1, 65535)][int]$Port = 8000,
    [string]$DatabasePath = '',
    [string]$CodexProfile = '',
    [string]$AccountEmail = '',
    [string]$ChatModel = 'gpt-5.6-sol',
    [string]$ChatReasoningEffort = 'xhigh',
    # Author/general workers. Reviewers use WB_RESEARCH_CODEX_ROLE_POLICY or the Astra defaults.
    [string]$ResearchModel = 'gpt-5.6-sol',
    [string]$ResearchReasoningEffort = 'low'
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$worker = Join-Path $projectRoot 'src\workbench\providers\research_codex_worker.py'

if (-not $DatabasePath) {
    $DatabasePath = Join-Path $projectRoot 'data\workbench.sqlite3'
}
if (-not $CodexProfile) {
    $CodexProfile = Join-Path $env:USERPROFILE '.paper-workbench-codex'
}
if (-not $AccountEmail) {
    $AccountEmail = $env:WB_CODEX_LOCAL_ACCOUNT_EMAIL
}

foreach ($required in @($python, $worker, $DatabasePath, $CodexProfile)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required local Paper-Workbench component is missing: $required"
    }
}
if (-not $AccountEmail) {
    throw 'AccountEmail or WB_CODEX_LOCAL_ACCOUNT_EMAIL is required.'
}
if (-not $env:WB_CODEX_LOCAL_GATE_SECRET -or $env:WB_CODEX_LOCAL_GATE_SECRET.Length -lt 32) {
    throw 'WB_CODEX_LOCAL_GATE_SECRET must already be set to an independent secret of at least 32 characters.'
}

$database = (Resolve-Path -LiteralPath $DatabasePath).Path
$profile = (Resolve-Path -LiteralPath $CodexProfile).Path

# One loopback application serves writing/chat and bounded delegated research.
# Secrets must already be present in the process environment; this launcher never loads .env files.
$env:PYTHONPATH = Join-Path $projectRoot 'src'
$env:WB_LOAD_DOTENV = 'false'
$env:WB_DEPLOYMENT_MODE = 'local'
$env:WB_PROVIDER_MODE = 'fake'
$env:WB_AUTH_REQUIRED = 'false'
$env:WB_AUTH_ALLOW_REGISTRATION = 'false'
$env:WB_AUTH_COOKIE_SESSIONS_ENABLED = 'false'
$env:WB_OIDC_MODE = 'disabled'
$env:WB_DATABASE_URL = 'sqlite:///' + ($database -replace '\\', '/')
$env:WB_DATA_DIR = Split-Path -Parent $database
$env:WB_RUN_MIGRATIONS_ON_STARTUP = 'false'

$env:WB_LLM_PROVIDER = 'codex_local'
$env:WB_CODEX_LOCAL_ENABLED = 'true'
$env:WB_CODEX_LOCAL_HOME = $profile
$env:WB_CODEX_LOCAL_ACCOUNT_EMAIL = $AccountEmail
$env:WB_CODEX_LOCAL_MODEL = $ChatModel
$env:WB_CODEX_LOCAL_REASONING_EFFORT = $ChatReasoningEffort

$env:WB_RESEARCH_EXECUTOR_ENABLED = 'true'
$env:WB_RESEARCH_EXECUTOR_COMMAND = ConvertTo-Json -Compress @($python, $worker)
$env:WB_RESEARCH_CODEX_HOME = $profile
$env:WB_RESEARCH_CODEX_ACCOUNT_EMAIL = $AccountEmail
$env:WB_RESEARCH_CODEX_MODEL = $ResearchModel
$env:WB_RESEARCH_CODEX_REASONING_EFFORT = $ResearchReasoningEffort

Set-Location -LiteralPath $projectRoot
& $python -m workbench.codex_local_server --port $Port
