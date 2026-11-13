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
Write-Host ""
Write-Host "Archive-path auto-fix gate (runs on every push, before the clean-tree gate):"
Write-Host "  spec archived to _archive/ but INDEX.md links / active table / stats not updated ->"
Write-Host "  pre-push auto-fixes what is safe (links, stale rows, stats) then rejects so you commit it:"
Write-Host "    python backend/scripts/check/fix_spec_index_archive_paths.py --check   # report only"
Write-Host "    python backend/scripts/check/fix_spec_index_archive_paths.py --apply   # auto-fix"
