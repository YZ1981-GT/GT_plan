# OfficeCLI bootstrap (Windows). Reads officecli.lock.json, downloads the pinned
# release asset, verifies SHA-256, installs to tools/officecli/bin/.
# The binary is gitignored on purpose (~32 MB). Run this after cloning.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\officecli\install.ps1
#   ... -Force      reinstall even if the binary already matches the lock
[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$lockPath = Join-Path $root 'officecli.lock.json'
if (-not (Test-Path $lockPath)) { throw "lock file not found: $lockPath" }
$lock = Get-Content $lockPath -Raw -Encoding UTF8 | ConvertFrom-Json

# --- platform key -----------------------------------------------------------
$arch = $env:PROCESSOR_ARCHITECTURE
if ($env:PROCESSOR_ARCHITEW6432) { $arch = $env:PROCESSOR_ARCHITEW6432 }
switch ($arch) {
    'AMD64' { $key = 'win-x64' }
    'ARM64' { $key = 'win-arm64' }
    default { throw "unsupported architecture: $arch" }
}

$entry = $lock.assets.$key
if (-not $entry) { throw "no asset for platform '$key' in lock file" }

$binDir = Join-Path $root 'bin'
$target = Join-Path $binDir 'officecli.exe'
$expected = $entry.sha256.ToLower()

# --- already installed? -----------------------------------------------------
if ((Test-Path $target) -and -not $Force) {
    $have = (Get-FileHash $target -Algorithm SHA256).Hash.ToLower()
    if ($have -eq $expected) {
        $ver = (& $target --version) 2>$null
        Write-Host "OfficeCLI already installed and verified ($($lock.version), reported: $ver)"
        exit 0
    }
    Write-Host "existing binary hash mismatch, reinstalling..."
}

# --- download ---------------------------------------------------------------
$url = $lock.release_url_template.Replace('{version}', $lock.version).Replace('{asset}', $entry.asset)
New-Item -ItemType Directory -Path $binDir -Force | Out-Null
$tmp = Join-Path $binDir ("." + $entry.asset + ".part")
Write-Host "downloading $($entry.asset) ($($lock.version)) ..."

$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
if ($curl) {
    & $curl.Source -sSL --fail -o $tmp $url
    if ($LASTEXITCODE -ne 0) { throw "curl failed with exit code $LASTEXITCODE" }
}
else {
    $old = $ProgressPreference
    $ProgressPreference = 'SilentlyContinue'
    try { Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing }
    finally { $ProgressPreference = $old }
}

# --- verify -----------------------------------------------------------------
$actual = (Get-FileHash $tmp -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $expected) {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    throw "SHA-256 mismatch for $($entry.asset)`n  expected: $expected`n  actual:   $actual"
}

Move-Item -Path $tmp -Destination $target -Force
$ver = (& $target --version) 2>$null
Write-Host "OK  OfficeCLI $($lock.version) installed -> $target (reported: $ver)"
Write-Host "    SHA-256 verified: $expected"
