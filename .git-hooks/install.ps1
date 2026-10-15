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
Write-Host "  single (default) - clean-tree hard gate; other sync checks warn only"
Write-Host "  multi            - clean-tree hard gate + strict PR and sync checks"
Write-Host ""
Write-Host 'Set multi mode: $env:GIT_MODE = "multi"'
