"""Tests for check_wp_semantic_schema.py.

验证:
- 脚本正常运行不报错
- 输出包含预期的 sections
- D1/D2 已标注 sheet_type 的 sheet 显示 has_sheet_type=true
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# 确保 backend 目录在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.check.check_wp_semantic_schema import (
    VALID_SHEET_TYPES,
    check_field_sources,
    check_no_generated_ref,
    check_sheet_type_validity,
    run_check,
    scan_production_schemas,
    scan_registry,
)


class TestCheckSheetTypeValidity:
    """6.2: sheet_type 枚举合法性检查."""

    def test_valid_sheet_type_no_error(self):
        for st in VALID_SHEET_TYPES:
            issues = check_sheet_type_validity(st, "test")
            assert issues == [], f"Expected no issues for {st}"

    def test_invalid_sheet_type_returns_error(self):
        issues = check_sheet_type_validity("bogus_type", "test_context")
        assert len(issues) == 1
        assert issues[0]["level"] == "error"
        assert issues[0]["check"] == "sheet_type_enum"
        assert "bogus_type" in issues[0]["message"]


class TestCheckFieldSources:
    """6.3: field_sources.source_ref 可解析检查."""

    def test_valid_source_ref_no_error(self):
        field_sources = {
            "f1": {
                "source_ref": {"module": "trial_balance", "account_code": "1121"},
            }
        }
        issues = check_field_sources(field_sources, "ctx")
        assert issues == []

    def test_missing_source_ref_error(self):
        field_sources = {"f1": {"label": "no ref"}}
        issues = check_field_sources(field_sources, "ctx")
        assert len(issues) == 1
        assert issues[0]["check"] == "source_ref_missing"

    def test_source_ref_not_dict_error(self):
        field_sources = {"f1": {"source_ref": "string_not_dict"}}
        issues = check_field_sources(field_sources, "ctx")
        assert len(issues) == 1
        assert issues[0]["check"] == "source_ref_not_dict"

    def test_source_ref_no_module_key_error(self):
        field_sources = {"f1": {"source_ref": {"account_code": "1121"}}}
        issues = check_field_sources(field_sources, "ctx")
        assert len(issues) == 1
        assert issues[0]["check"] == "source_ref_no_module"

    def test_non_dict_field_sources_error(self):
        issues = check_field_sources("not_a_dict", "ctx")  # type: ignore
        assert len(issues) == 1
        assert issues[0]["check"] == "field_sources_format"


class TestCheckNoGeneratedRef:
    """6.4: generated schema 不得被引用为生产真源."""

    def test_no_generated_ref_ok(self):
        issues = check_no_generated_ref("C-D1-disclosure.yaml", "ctx")
        assert issues == []

    def test_generated_ref_error(self):
        issues = check_no_generated_ref("generated/D1.yaml", "ctx")
        assert len(issues) == 1
        assert issues[0]["check"] == "generated_as_production"

    def test_empty_ref_ok(self):
        issues = check_no_generated_ref("", "ctx")
        assert issues == []


class TestRunCheck:
    """集成测试: 脚本正常运行."""

    def test_run_check_returns_report(self):
        """脚本执行返回完整报告结构."""
        report = run_check(strict=False)
        # 必须包含 expected sections
        assert "status" in report
        assert "error_count" in report
        assert "warning_count" in report
        assert "errors" in report
        assert "warnings" in report
        assert "migration_report" in report
        assert "schemas_scanned" in report
        assert "registry_entries_scanned" in report

    def test_run_check_migration_report_structure(self):
        """迁移报告包含 summary、d1_d2_breakdown."""
        report = run_check(strict=False)
        mr = report["migration_report"]
        assert "summary" in mr
        assert "has_explicit_sheet_type" in mr["summary"]
        assert "relies_on_heuristic" in mr["summary"]
        assert "d1_d2_breakdown" in mr
        assert "d1" in mr["d1_d2_breakdown"]
        assert "d2" in mr["d1_d2_breakdown"]

    def test_d1_d2_annotated_sheets_have_sheet_type(self):
        """D1/D2 已标注 sheet 在报告中显示 has_sheet_type=true."""
        report = run_check(strict=False)
        mr = report["migration_report"]
        d1 = mr["d1_d2_breakdown"]["d1"]
        d2 = mr["d1_d2_breakdown"]["d2"]
        # registry 已标注多个 D1/D2 sheet
        assert d1["with_sheet_type"] > 0, "D1 should have sheets with sheet_type"
        assert d2["with_sheet_type"] > 0, "D2 should have sheets with sheet_type"

    def test_run_check_no_errors_on_current_schemas(self):
        """当前 schema 配置不应产生 error (均合规)."""
        report = run_check(strict=False)
        # 当前生产 schema + registry 都配置正确，不应有 error
        assert report["error_count"] == 0, (
            f"Unexpected errors: {json.dumps(report['errors'], ensure_ascii=False)}"
        )

    def test_run_check_p0_always_pass(self):
        """P0 模式 status 不应该是 fail (只有 warn/pass)."""
        report = run_check(strict=False)
        # P0: errors=0 应为 warn 或 pass
        if report["error_count"] == 0:
            assert report["status"] in ("pass", "warn")

    def test_strict_mode_blocks_on_missing_type(self):
        """Strict 模式下缺失 sheet_type 时 status=fail."""
        report = run_check(strict=True)
        # 当前有 schema 缺少 sheet_type (如 B-template.yaml)
        if report["warning_count"] > 0:
            missing_type_warnings = [
                w for w in report["warnings"] if w["check"] == "missing_sheet_type"
            ]
            if missing_type_warnings:
                assert report["status"] == "fail"
                assert report.get("strict_blocked") is True


class TestScanProductionSchemas:
    """验证扫描生产 schema 逻辑."""

    def test_scans_yaml_files(self):
        """能扫描到生产 YAML 文件."""
        issues, summaries = scan_production_schemas()
        # 至少能扫到 C-D1-disclosure.yaml, D2A.yaml 等
        assert len(summaries) > 0
        filenames = [s["file"] for s in summaries]
        assert "D2A.yaml" in filenames

    def test_d2a_has_sheet_type(self):
        """D2A.yaml 有 sheet_type=procedure."""
        _, summaries = scan_production_schemas()
        d2a = next((s for s in summaries if s["file"] == "D2A.yaml"), None)
        assert d2a is not None
        assert d2a["has_sheet_type"] is True
        assert d2a["sheet_type"] == "procedure"


class TestScanRegistry:
    """验证注册表扫描."""

    def test_scans_registry_entries(self):
        """能扫描到注册表条目."""
        issues, summaries = scan_registry()
        assert len(summaries) > 0

    def test_registry_d1_audit_sheet_has_type(self):
        """注册表中 D1 审定表有 sheet_type."""
        _, summaries = scan_registry()
        audit_sheets = [
            s for s in summaries
            if s.get("sheet_type") == "audit_sheet" and "D1" in str(s.get("wp_code", ""))
        ]
        assert len(audit_sheets) > 0

    def test_registry_no_generated_refs(self):
        """注册表中 schema_ref 不应指向 generated/."""
        issues, _ = scan_registry()
        generated_errors = [
            i for i in issues if i["check"] == "generated_as_production"
        ]
        assert generated_errors == [], (
            f"Registry has generated refs: {generated_errors}"
        )
