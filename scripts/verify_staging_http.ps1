param(
    [Parameter(Mandatory = $true)]
    [string]$DeploymentId
)

$ErrorActionPreference = 'Stop'
$report = [ordered]@{ deployment_id = $DeploymentId; checks = @() }
$paths = @('/health', '/auth/config', '/ui/', '/ui/app.js', '/workspaces', '/auth/me')
foreach ($path in $paths) {
    $response = (& vercel curl $path --deployment $DeploymentId '--' --silent --show-error --max-time 30 --write-out '\nWB_STATUS:%{http_code}' | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Request command failed for $path" }
    $matched = [regex]::Match($response, '\nWB_STATUS:(\d{3})\s*$')
    if (-not $matched.Success) { throw "Missing response status for $path" }
    $status = [int]$matched.Groups[1].Value
    $body = $response.Substring(0, $matched.Index)
    $credentialPattern = 'vercel_blob_rw_|postgres(?:ql)?(?:\+psycopg)?://[^\s"'']+:[^\s"'']+@|-----BEGIN .*PRIVATE KEY-----'
    if ($body -match $credentialPattern) { throw "Credential pattern found in response for $path; body suppressed" }
    $expected = if ($path -in @('/workspaces', '/auth/me')) { 401 } else { 200 }
    if ($status -ne $expected) { throw "Unexpected HTTP $status for $path; body suppressed" }
    if ($path -eq '/health') {
        $health = $body | ConvertFrom-Json
        if ($health.status -ne 'ok' -or $health.provider_mode -ne 'fake' -or
            $health.auth_required -ne $true -or $health.oidc_mode -ne 'disabled' -or
            $health.deployment_mode -ne 'vercel') { throw 'Deployed health settings do not match staging policy' }
    }
    if ($path -eq '/auth/config') {
        $auth = $body | ConvertFrom-Json
        if ($auth.registration_enabled -ne $false -or $auth.oidc_browser_enabled -ne $false -or
            $auth.cookie_sessions_enabled -ne $true -or $auth.auth_required -ne $true -or
            $auth.upload_max_bytes -ne 4000000) { throw 'Deployed auth configuration does not match staging policy' }
    }
    if ($path -eq '/ui/' -and $body -notmatch 'Paper-Workbench') { throw 'Expected UI markup is absent' }
    if ($path -eq '/ui/app.js' -and $body -notmatch 'loadAuthConfig') { throw 'Expected hosted UI code is absent' }
    $report.checks += [ordered]@{ path = $path; status = $status; credential_patterns = 'absent' }
}
$report.status = 'passed'
$report | ConvertTo-Json -Depth 4
