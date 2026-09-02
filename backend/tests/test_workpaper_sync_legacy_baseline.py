"""Wave 0 red-baseline guards for false HTML/OnlyOffice bidirectionality."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

_REPO = Path(__file__).resolve().parents[2]
_GENERATOR = _REPO / "backend" / "scripts" / "gen" / "generate_workpaper_sync_legacy_baseline.py"
_CLOSURE = _REPO / "backend" / "scripts" / "check" / "check_workpaper_sync_closure.py"
_MANIFEST = _REPO / "backend" / "data" / "workpaper_sync_entry_manifest.json"
_BASELINE = _REPO / "backend" / "data" / "workpaper_sync_legacy_baseline.json"
_FRONTEND = (
    _REPO
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "sync"
    / "workpaperSyncLegacyBaseline.generated.ts"
)


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def facts() -> tuple[ModuleType, ModuleType, dict, dict]:
    generator = _load_module("workpaper_sync_legacy_generator", _GENERATOR)
    closure = _load_module("workpaper_sync_closure_guard", _CLOSURE)
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    baseline = generator.build_baseline(manifest)
    return generator, closure, manifest, baseline


def test_legacy_characterization_and_frontend_projection_are_current(
    facts: tuple[ModuleType, ModuleType, dict, dict],
) -> None:
    generator, _, _, expected = facts
    assert json.loads(_BASELINE.read_text(encoding="utf-8")) == expected
    assert _BASELINE.read_text(encoding="utf-8") == generator.render_json(expected)
    assert _FRONTEND.read_text(encoding="utf-8") == generator.render_frontend(expected)


def test_every_open_independent_entry_has_explicit_failure_reasons(
    facts: tuple[ModuleType, ModuleType, dict, dict],
) -> None:
    _, _, _, baseline = facts
    open_entries = [
        entry
        for entry in baseline["entries"]
        if entry["independent_entry"] and entry["capability"] != "unreachable"
    ]
    assert open_entries
    for entry in open_entries:
        assert entry["reason_codes"], entry["entry_id"]
        assert entry["flags"]["no_durable_forcesave_ack"], entry["entry_id"]
        assert entry["flags"]["missing_adapter"], entry["entry_id"]


def test_single_mode_switch_debt_has_source_line_evidence(
    facts: tuple[ModuleType, ModuleType, dict, dict],
) -> None:
    _, _, _, baseline = facts
    debts = [entry for entry in baseline["entries"] if entry["flags"]["single_mode_switch_visible"]]
    assert debts
    assert baseline["stats"]["single_mode_switch_visible_count"] == len(debts)
    for entry in debts:
        evidence = entry["ui_characterization"]["evidence"]
        assert evidence, entry["entry_id"]
        assert all(item["file"].endswith(".vue") and item["line"] > 0 for item in evidence)


def test_bidirectional_without_adapter_is_a_blocking_failure(
    facts: tuple[ModuleType, ModuleType, dict, dict],
) -> None:
    _, closure, manifest, baseline = facts
    changed = copy.deepcopy(manifest)
    target = next(entry for entry in changed["entries"] if entry["independent_entry"])
    target["capability"] = "bidirectional"
    target["adapter_id"] = None

    issues = closure.evaluate_closure(changed, baseline)
    assert target["entry_id"] in issues["bidirectional_without_adapter"]
    assert target["entry_id"] in issues["bidirectional_without_contract_evidence"]
    assert target["entry_id"] in issues["bidirectional_without_browser_evidence"]


def test_wave0_closure_baseline_is_intentionally_red_not_allowlisted(
    facts: tuple[ModuleType, ModuleType, dict, dict],
) -> None:
    _, closure, manifest, baseline = facts
    issues = closure.evaluate_closure(manifest, baseline)
    assert any(issues.values())
    assert issues["legacy_fake_bidirectional"]
    assert issues["missing_forcesave_command"]
    assert issues["missing_durable_callback_ack"]
    assert closure.main([]) == 1
    assert closure.main(["--expect-open-debt"]) == 0


def test_comment_only_tokens_do_not_create_false_ui_evidence(
    facts: tuple[ModuleType, ModuleType, dict, dict],
) -> None:
    generator, _, _, _ = facts
    source = "<!-- <el-segmented /> -->\n// dualMode\n/* callbackAck */\nconst live = 1\n"
    stripped = generator.strip_source_comments(source)
    assert "el-segmented" not in stripped
    assert "dualMode" not in stripped
    assert "callbackAck" not in stripped
    assert "const live = 1" in stripped
