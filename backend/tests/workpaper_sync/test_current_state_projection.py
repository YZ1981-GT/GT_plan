"""当前双向回写事实投影与 active spec 闭合守卫。"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure"
GENERATOR = ROOT / "backend/scripts/gen/generate_workpaper_sync_current_state.py"
OUTPUT = ROOT / "backend/data/workpaper_sync_current_state.json"
PARADIGM = ROOT / "backend/data/workpaper_sync_migration_paradigm.json"


def load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("workpaper_sync_current_state_gen", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_projection_is_current_and_idempotent() -> None:
    generator = load_generator()
    first = generator.build_report()
    second = generator.build_report()
    assert first == second
    assert OUTPUT.read_text(encoding="utf-8") == generator.render(first)


def test_counts_are_derived_from_entry_rows() -> None:
    report = load(OUTPUT)
    rows = report["entries"]
    independent = [row for row in rows if row["independent_entry"]]
    assert report["counts"]["entries"] == len(rows)
    assert report["counts"]["independent"] == len(independent)
    assert report["counts"]["pending"] == sum(
        row["capability"] is None for row in independent
    )
    assert report["counts"]["declared_adapters"] == sum(
        bool(row["adapter_id"]) for row in independent
    )


def test_static_projection_never_claims_runtime_success() -> None:
    report = load(OUTPUT)
    assert report["runtime_scope"] == {
        "database_queried": False,
        "onlyoffice_queried": False,
        "meaning": "runtime_readiness/acceptance_state are unknown, not failed or passed",
    }
    assert all(row["runtime_readiness"] == "unknown" for row in report["entries"])
    assert all(row["acceptance_state"] == "unknown" for row in report["entries"])


def test_pending_rows_have_target_blockers_and_no_adapter() -> None:
    rows = [
        row for row in load(OUTPUT)["entries"]
        if row["independent_entry"] and row["capability"] is None
    ]
    assert rows, "pending 分母为空会让 AC 1.3 的反例门空跑"
    for row in rows:
        assert row["capability_target"] in {
            "bidirectional", "single_html", "single_onlyoffice", "unreachable"
        }
        assert row["capability_target_blocked_by"]
        assert row["adapter_id"] is None


def test_d2_inspection_is_generated_pending_not_hand_edited_success() -> None:
    by_id = {row["entry_id"]: row for row in load(OUTPUT)["entries"]}
    row = by_id["xlsx/gt-d2-inspection"]
    assert row["adjudication_state"] == "pending"
    assert row["capability"] is None
    assert "dedicated_host_binding" in row["capability_target_blocked_by"]
    assert row["contract_id"] == "d2.inspection"
    assert row["runtime_readiness"] == "unknown"


def test_active_spec_covers_every_authoritative_acceptance_criterion() -> None:
    paradigm = load(PARADIGM)
    expected = {
        str(row["ac"])
        for row in paradigm["adjudication_criteria"]["acceptance_criteria"]
    }
    requirements = (SPEC / "requirements.md").read_text(encoding="utf-8")
    tasks = (SPEC / "tasks.md").read_text(encoding="utf-8")
    design = (SPEC / "design.md").read_text(encoding="utf-8")
    actual_requirements = {
        match.group(1)
        for match in re.finditer(r"^(\d+\.\d+)\. ", requirements, re.MULTILINE)
    }
    task_refs = {
        token
        for line in tasks.splitlines()
        if "_AC:" in line
        for token in re.findall(r"\d+\.\d+", line)
    }
    design_refs = {
        ac for ac in expected if f"| {ac} |" in design
    }
    assert actual_requirements == expected
    assert task_refs == expected
    assert design_refs == expected


def test_source_review_is_bound_to_overlay() -> None:
    report = load(OUTPUT)
    review_ref = report["source_review_ref"]
    assert isinstance(review_ref, str) and review_ref
    review = load(ROOT / review_ref)
    assert review["decision"] == "approved"
    assert review["approved_source_digest_after"] == report["source_digest"]
