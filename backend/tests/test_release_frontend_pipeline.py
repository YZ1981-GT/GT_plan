"""platform-release-blocker-closure Task 18/19: release pipeline references are executable."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "audit-platform" / "frontend"


def test_release_scripts_exist_and_package_commands_are_closed() -> None:
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    scripts = package["scripts"]
    assert scripts["build:verify"] == "node scripts/build-verified-dist.mjs"
    assert scripts["preview:verified"] == "node scripts/preview-verified-dist.mjs"
    assert scripts["bundle:check"] == "node scripts/check-bundle-budget.mjs --check --dir dist"
    for relative in (
        "scripts/build-verified-dist.mjs",
        "scripts/preview-verified-dist.mjs",
        "scripts/check-bundle-budget.mjs",
        "scripts/smoke-built-dist.mjs",
        # 包体预算单一策略文件（2026-11-06 起取代匿名 bundle-budget.baseline.json）。
        "scripts/bundle-budget.json",
        "Dockerfile",
        "docker/default.conf.template",
    ):
        path = FRONTEND / relative
        assert path.is_file() and path.stat().st_size > 0, relative


def test_verified_build_has_content_addressed_output_and_all_gates() -> None:
    vite = (FRONTEND / "vite.config.ts").read_text(encoding="utf-8")
    builder = (FRONTEND / "scripts/build-verified-dist.mjs").read_text(encoding="utf-8")
    preview = (FRONTEND / "scripts/preview-verified-dist.mjs").read_text(encoding="utf-8")
    assert "GT_FRONTEND_OUT_DIR" in vite and "manifest: true" in vite
    for required in ("check-bundle-budget.mjs", "smoke-built", "manifestSha256"):
        assert required in builder
    assert "budgetBaselineSha256" in preview and "manifestSha256" in preview


def test_stable_launcher_and_docker_use_existing_scripts() -> None:
    launcher = (ROOT / "start-dev.bat").read_text(encoding="ascii")
    dockerfile = (FRONTEND / "Dockerfile").read_text(encoding="utf-8")
    assert "run build:verify" in launcher
    assert "run preview:verified" in launcher
    assert "run build:runtime" not in launcher
    assert "RUN npm run build" in dockerfile
    assert "RUN npm run bundle:check" in dockerfile


def test_ci_push_runs_for_spec_branches() -> None:
    for relative in (".github/workflows/ci.yml", ".github/workflows/governance-checks.yml"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        trigger = source.split("pull_request:", 1)[0]
        assert "'spec/**'" in trigger, relative
