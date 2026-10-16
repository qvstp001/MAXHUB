param(
    [ValidateRange(1, 65535)][int]$Port = 18096,
    [string]$Password = $env:ADMIN_PASSWORD,
    [string]$Python = ''
)

$ErrorActionPreference = 'Stop'
if (-not $Password) { $Password = 'local-only-123' }
if ($Password.Length -lt 10) { throw '管理员密码至少需要 10 个字符' }

# Prefer an installed interpreter, then the bundled desktop runtime when available.
$localPythonCandidates = if ($Python) { @($Python) } else {
    @('python', 'python3', (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'))
}
$localPython = $null
foreach ($candidate in $localPythonCandidates) {
    try {
        & $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { $localPython = $candidate; break }
    } catch { continue }
}
if (-not $localPython) { throw '需要 Python 3.12 或更高版本；可通过 -Python 指定 python.exe 完整路径' }

$localSettings = @{
    ADMIN_PASSWORD = $Password
    HOST = '127.0.0.1'
    PORT = [string]$Port
    PUBLIC_URL = "http://127.0.0.1:$Port"
    DATA_DIR = (Join-Path $PSScriptRoot 'data')
    LIBRARY_ROOTS = '[]'
    PLAYBACK_PROXY_URL = ''
    COOKIE_SECURE = 'false'
}
$previousSettings = @{}
foreach ($key in $localSettings.Keys) {
    $previousSettings[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
    [Environment]::SetEnvironmentVariable($key, $localSettings[$key], 'Process')
}
Push-Location $PSScriptRoot
try {
    Write-Host "QMaxHub: http://127.0.0.1:$Port"
    Write-Host '在「设置与扫描 → 媒体来源」添加本机目录；按 Ctrl+C 停止。'
    if ($Password -eq 'local-only-123') { Write-Host '本机试用密码：local-only-123（可用 -Password 修改）' }
    & $localPython -m qmaxhub
} finally {
    Pop-Location
    foreach ($key in $previousSettings.Keys) {
        [Environment]::SetEnvironmentVariable($key, $previousSettings[$key], 'Process')
    }
}
