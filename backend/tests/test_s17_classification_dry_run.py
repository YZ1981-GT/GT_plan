"""Offline contract tests for the S17 .xls classification dry-run."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

pytest.importorskip("xlrd")

from scripts.analyze.generate_s17_classification_dry_run import (  # noqa: E402
    DEFAULT_REFERENCE,
    DEFAULT_TEMPLATE,
    build_dry_run,
)


_EXPECTED = {
    "表头（请先填写）": "I-占位",
    "审计程序S17": "A-S 议题程序",
    "审定表S17-1": "F-审定表",
    "审核表（合并）S17-2": "D-检查表",
    "审核表（个别报表）S17-3": "D-检查表",
    "提示（供参考，不打印）": "H-辅助说明",
    "与营业外收支等核对表S17-11": "D-检查表",
    "非经常性损益项目的所得税影响S17-21": "D-检查表",
}


def test_real_xls_produces_eight_schema_candidates_without_database() -> None:
    report = build_dry_run()
    candidates = {row["sheet_name"]: row["class_code"] for row in report["candidates"]}

    assert report["candidate_count"] == 8
    assert candidates == _EXPECTED
    assert report["mode"] == "dry-run"
    assert report["writes_shared_database"] is False
    assert report["shared_database_accessed"] is False
    assert report["template"]["path"] == "backend/wp_templates/S/S17 非经常性损益.xls"
    assert report["template"]["format"] == "xls"
    assert report["classification_schema"]["candidate_columns"] == [
        "wp_code",
        "sheet_name",
        "class_code",
    ]
    assert report["reference_classification"]["existing_s17_rows"] == 1
    assert report["reference_classification"]["exact_candidate_rows"] == 0
    assert report["reference_classification"]["parent_only_rows"] == [
        {
            "wp_code": "S17",
            "sheet_name": "S17",
            "class_code": "S-审定表",
            "functional_type": None,
            "template_version_id": "bbc0190d-1a02-4d1a-9294-134f7f5fd547",
        }
    ]
    assert "数据库未查询" in report["reference_classification"]["conflict"]
    assert report["reference_classification"]["path"] == DEFAULT_REFERENCE.relative_to(
        Path(__file__).resolve().parents[2]
    ).as_posix()
    assert all(row["source"]["reader"] == "xlrd" for row in report["candidates"])
    assert all(row["wp_code"] == "S17" for row in report["candidates"])


def test_legacy_xlsx_classifier_conflicts_are_explicitly_recorded() -> None:
    report = build_dry_run()
    mismatches = report["conflicts"]["legacy_xlsx_classifier_mismatches"]

    assert {item["sheet"] for item in mismatches} == {
        "审核表（合并）S17-2",
        "审核表（个别报表）S17-3",
        "提示（供参考，不打印）",
        "非经常性损益项目的所得税影响S17-21",
    }
    assert {
        item["sheet"]: item["legacy"]
        for item in mismatches
    } == {
        "审核表（合并）S17-2": "F-数据表",
        "审核表（个别报表）S17-3": "_pending",
        "提示（供参考，不打印）": "_pending",
        "非经常性损益项目的所得税影响S17-21": "F-数据表",
    }
    assert "不自动写库" in report["conflicts"]["summary"]


def test_report_is_json_serializable_and_tool_has_no_database_writer() -> None:
    report = build_dry_run()
    json.dumps(report, ensure_ascii=False, sort_keys=True)

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "analyze" / (
        "generate_s17_classification_dry_run.py"
    )
    tree = ast.parse(script_path.read_text(encoding="utf-8"))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if node.module
    )
    assert not any(
        module.startswith("sqlalchemy") or module.startswith("app.core.database")
        for module in imported_modules
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"execute", "commit", "flush", "begin"}
        for node in ast.walk(tree)
    )
    assert DEFAULT_TEMPLATE.suffix.lower() == ".xls"
