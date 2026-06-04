# Install git hooks - repo-git-workflow-unification spec / Task 2.2

Write-Host "=== Install git hooks ==="

$hooksDir = ".git/hooks"
$sourceDir = ".git-hooks"

if (-not (Test-Path $hooksDir)) {
    Write-Error "Not in a git repo root (no $hooksDir found)"
    exit 1
}

$hooks = @("pre-push", "pre-commit")
foreach ($h in $hooks) {
    $src = "$sourceDir/$h"
    $dst = "$hooksDir/$h"
    if (Test-Path $src) {
        Copy-Item $src $dst -Force
        Write-Host "  [OK] $h -> $dst"
    } else {
        Write-Host "  [SKIP] $src not found"
    }
}

Write-Host ""
Write-Host "=== Done ==="
Write-Host "GIT_MODE switch:"
Write-Host "  single (default) - solo user mode, warn only"
Write-Host "  multi            - team mode, strict PR + 6-dim check"
Write-Host ""
Write-Host 'Set multi mode: $env:GIT_MODE = "multi"'
