# Install git hooks - repo-git-workflow-unification spec / Task 2.2

Write-Host "=== Install git hooks ==="

$hooksDir = ".git/hooks"
$sourceDir = ".git-hooks"

if (-not (Test-Path $hooksDir)) {
    Write-Error "Not in a git repo root (no $hooksDir found)"
    exit 1
}

# push_version.py: version-tag gate called by pre-push (also the tag + push tool)
$hooks = @("pre-push", "pre-commit", "push_version.py")
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
Write-Host ""
Write-Host "Every push of new commits needs an annotated version tag (vX.Y.Z) with a change list:"
Write-Host '  python .git-hooks/push_version.py push -c "change 1" -c "change 2"'
Write-Host "  (detached worktree: add --branch <remote-branch>; history: python .git-hooks/push_version.py list)"
