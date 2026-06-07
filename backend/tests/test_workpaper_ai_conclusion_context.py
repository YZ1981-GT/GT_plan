"""AI 结论上下文服务测试

覆盖场景（Task 1.6）:
- 上下文缺失：注册表找不到工作包
- 函证为空：confirmation_summary 返回 missing
- 坏账/ECL 不完整：无 ECL 分析 sheets
- 调整影响存在：adjustment sheets 正常返回
- D1 vs D2 上下文差异
- 约束验证：不导入 generated schema

Requirements: 3.1, 3.2, 3.3
"""

from __future__ import annotations

import importlib
import inspect
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workpaper_ai_conclusion_context_service import (
    AIConclusionContext,
    WorkpaperAIConclusionContextService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

D1_PACKAGE = {
    "account_package_id": "D1_notes_receivable",
    "primary_wp_code": "D1",
    "sheets": [
        {"sheet_name": "审定表D1-1", "sheet_type": "audit_sheet", "source_wp_code": "D1"},
        {"sheet_name": "D1A 应收票据审计程序表", "sheet_type": "procedure", "source_wp_code": "D1"},
        {"sheet_name": "调整分录汇总表D1-15", "sheet_type": "adjustment", "source_wp_code": "D1"},
        {"sheet_name": "附注披露信息（上市公司）", "sheet_type": "disclosure", "source_wp_code": "D1", "schema_ref": "C-D1-disclosure.yaml"},
    ],
    "external_cards": ["confirmation_summary"],
    "downstream": ["report", "disclosure_note", "sign_off"],
}

D2_PACKAGE = {
    "account_package_id": "D2_accounts_receivable",
    "primary_wp_code": "D2",
    "sheets": [
        {"sheet_name": "审定表D2-1", "sheet_type": "audit_sheet", "source_wp_code": "D2"},
        {"sheet_name": "D2A 应收账款实质性程序表", "sheet_type": "control_panel", "source_wp_code": "D2"},
        {"sheet_name": "坏账准备明细表D2-3", "sheet_type": "analysis", "source_wp_code": "D2"},
        {"sheet_name": "调整分录汇总表D2-4", "sheet_type": "adjustment", "source_wp_code": "D2"},
        {"sheet_name": "应收账款分析表D2-5", "sheet_type": "analysis", "source_wp_code": "D2-5"},
        {"sheet_name": "坏账准备计提会计政策检查D2-8", "sheet_type": "procedure", "source_wp_code": "D2-6"},
        {"sheet_name": "应收坏账准备测算D2-9", "sheet_type": "analysis", "source_wp_code": "D2-6"},
        {"sheet_name": "预期信用损失的计量测试D2-10", "sheet_type": "analysis", "source_wp_code": "D2-6"},
        {"sheet_name": "应收账款附注披露信息", "sheet_type": "disclosure", "source_wp_code": "D2", "schema_ref": "C-D2-disclosure.yaml"},
    ],
    "external_cards": ["confirmation_summary", "adjustment_impact", "note_disclosure"],
    "downstream": ["report", "disclosure_note", "sign_off"],
}

D2_PACKAGE_NO_ECL = {
    "account_package_id": "D2_accounts_receivable",
    "primary_wp_code": "D2",
    "sheets": [
        {"sheet_name": "审定表D2-1", "sheet_type": "audit_sheet", "source_wp_code": "D2"},
        {"sheet_name": "调整分录汇总表D2-4", "sheet_type": "adjustment", "source_wp_code": "D2"},
        {"sheet_name": "应收账款附注披露信息", "sheet_type": "disclosure", "source_wp_code": "D2", "schema_ref": "C-D2-disclosure.yaml"},
    ],
    "external_cards": ["confirmation_summary"],
    "downstream": ["report"],
}


@pytest.fixture
def project_id():
    return uuid.uuid4()


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_registry():
    registry = MagicMock()
    registry.get_package.return_value = D1_PACKAGE
    return registry


def _build_service(mock_db, mock_registry):
    """构建服务实例"""
    return WorkpaperAIConclusionContextService(
        db=mock_db, registry_service=mock_registry
    )


# ---------------------------------------------------------------------------
# 测试：上下文缺失 - 工作包不存在
# ---------------------------------------------------------------------------


class TestMissingContext:
    """上下文缺失场景"""

    @pytest.mark.asyncio
    async def test_package_not_found_returns_missing(self, project_id, mock_db):
        """注册表找不到工作包时，missing 包含 registry 条目"""
        registry = MagicMock()
        registry.get_package.return_value = None
        svc = WorkpaperAIConclusionContextService(db=mock_db, registry_service=registry)

        ctx = await svc.build_context(project_id, "NONEXISTENT_pkg")

        assert ctx.wp_code == ""
        assert len(ctx.missing) == 1
        assert ctx.missing[0]["source"] == "registry"
        assert ctx.missing[0]["reason"] == "package_not_found"

    @pytest.mark.asyncio
    async def test_no_program_status_adds_missing(self, project_id, mock_db, mock_registry):
        """无程序状态记录时进入 missing"""
        svc = _build_service(mock_db, mock_registry)

        with patch.object(svc._program_status_service, "get_all_statuses", return_value=[]):
            with patch.object(svc, "_load_semantic_registry", return_value={"sheets": {}}):
                ctx = await svc.build_context(project_id, "D1_notes_receivable")

        missing_sources = [m["source"] for m in ctx.missing]
        assert "program_status_summary" in missing_sources

    @pytest.mark.asyncio
    async def test_no_field_sources_adds_missing(self, project_id, mock_db, mock_registry):
        """语义注册表无 field_sources 时进入 missing"""
        svc = _build_service(mock_db, mock_registry)

        # 返回注册表但没有 field_sources 条目
        registry_data = {"sheets": {"SomeSheet": {"wp_code": "D1", "sheet_type": "procedure"}}}

        with patch.object(svc._program_status_service, "get_all_statuses", return_value=[]):
            with patch.object(svc, "_load_semantic_registry", return_value=registry_data):
                ctx = await svc.build_context(project_id, "D1_notes_receivable")

        missing_sources = [m["source"] for m in ctx.missing]
        assert "field_sources" in missing_sources


# ---------------------------------------------------------------------------
# 测试：函证为空（D2 特有）
# ---------------------------------------------------------------------------


class TestConfirmationEmpty:
    """函证摘要为空场景"""

    @pytest.mark.asyncio
    async def test_confirmation_missing_adds_to_missing(self, project_id, mock_db):
        """函证服务返回 missing 时进入 missing 列表"""
        registry = MagicMock()
        registry.get_package.return_value = D2_PACKAGE
        svc = WorkpaperAIConclusionContextService(db=mock_db, registry_service=registry)

        with patch.object(svc._program_status_service, "get_all_statuses", return_value=[]):
            with patch.object(svc, "_load_semantic_registry", return_value={"sheets": {}}):
                with patch.object(
                    svc._summary_service,
                    "get_confirmation_summary",
                    return_value={"status": "missing", "coverage_rate": None},
                ):
                    ctx = await svc.build_context(project_id, "D2_accounts_receivable")

        missing_sources = [m["source"] for m in ctx.missing]
        assert "confirmation_summary" in missing_sources
        # 验证 confirmation_summary 字段为空 dict
        assert ctx.confirmation_summary == {}

    @pytest.mark.asyncio
    async def test_confirmation_loaded_not_in_missing(self, project_id, mock_db):
        """函证服务正常返回时不进入 missing"""
        registry = MagicMock()
        registry.get_package.return_value = D2_PACKAGE
        svc = WorkpaperAIConclusionContextService(db=mock_db, registry_service=registry)

        confirmation_data = {
            "status": "loaded",
            "total": 10,
            "sent": 8,
            "returned": 6,
            "matched": 5,
            "discrepancy": 1,
            "coverage_rate": 0.6,
            "diff_total": 5000.0,
        }

        with patch.object(svc._program_status_service, "get_all_statuses", return_value=[]):
            with patch.object(svc, "_load_semantic_registry", return_value={"sheets": {}}):
                with patch.object(
                    svc._summary_service,
                    "get_confirmation_summary",
                    return_value=confirmation_data,
                ):
                    ctx = await svc.build_context(project_id, "D2_accounts_receivable")

        # confirmation_summary 不该在 missing 中
        missing_sources = [m["source"] for m in ctx.missing]
        assert "confirmation_summary" not in missing_sources
        assert ctx.confirmation_summary["status"] == "loaded"
        assert ctx.confirmation_summary["coverage_rate"] == 0.6


# ---------------------------------------------------------------------------
# 测试：坏账/ECL 不完整
# ---------------------------------------------------------------------------


class TestBadDebtECLIncomplete:
    """坏账/ECL 不完整场景"""

    @pytest.mark.asyncio
    async def test_no_ecl_sheets_adds_missing(self, project_id, mock_db):
        """D2 工作包无 ECL 分析 sheets 时进入 missing"""
        registry = MagicMock()
        registry.get_package.return_value = D2_PACKAGE_NO_ECL
        svc = WorkpaperAIConclusionContextService(db=mock_db, registry_service=registry)

        with patch.object(svc._program_status_service, "get_all_statuses", return_value=[]):
            with patch.object(svc, "_load_semantic_registry", return_value={"sheets": {}}):
                with patch.object(
                    svc._summary_service,
                    "get_confirmation_summary",
                    return_value={"status": "missing", "coverage_rate": None},
                ):
                    ctx = await svc.build_context(project_id, "D2_accounts_receivable")

        missing_sources = [m["source"] for m in ctx.missing]
        assert "bad_debt_ecl" in missing_sources
        # 还应缺 analysis_summary
        assert "analysis_summary" in missing_sources

    @pytest.mark.asyncio
    async def test_ecl_sheets_present_not_missing(self, project_id, mock_db):
        """D2 工作包有 ECL sheets 时不进 missing"""
        registry = MagicMock()
        registry.get_package.return_value = D2_PACKAGE
        svc = WorkpaperAIConclusionContextService(db=mock_db, registry_service=registry)

        with patch.object(svc._program_status_service, "get_all_statuses", return_value=[]):
            with patch.object(svc, "_load_semantic_registry", return_value={"sheets": {}}):
                with patch.object(
                    svc._summary_service,
                    "get_confirmation_summary",
                    return_value={"status": "loaded", "total": 5, "coverage_rate": 0.8, "diff_total": 0},
                ):
                    ctx = await svc.build_context(project_id, "D2_accounts_receivable")

        missing_sources = [m["source"] for m in ctx.missing]
        assert "bad_debt_ecl" not in missing_sources
        assert ctx.bad_debt_ecl["has_ecl_data"] is True
        assert ctx.bad_debt_ecl["count"] >= 1


# ---------------------------------------------------------------------------
# 测试：调整影响存在
# ---------------------------------------------------------------------------


class TestAdjustmentImpact:
    """调整影响存在场景"""

    @pytest.mark.asyncio
    async def test_adjustment_present_structured_summary(self, project_id, mock_db, mock_registry):
        """注册表有调整分录 sheets 时返回结构化摘要"""
        svc = _build_service(mock_db, mock_registry)

        with patch.object(svc._program_status_service, "get_all_statuses", return_value=[]):
            with patch.object(svc, "_load_semantic_registry", return_value={"sheets": {}}):
                ctx = await svc.build_context(project_id, "D1_notes_receivable")

        assert ctx.adjustment_impact["has_adjustments"] is True
        assert len(ctx.adjustment_impact["adjustment_sheets"]) == 1
        assert ctx.adjustment_impact["downstream_affected"] == ["report", "disclosure_note", "sign_off"]
        # adjustment_impact 不在 missing 中
        missing_sources = [m["source"] for m in ctx.missing]
        assert "adjustment_impact" not in missing_sources

    @pytest.mark.asyncio
    async def test_no_adjustment_sheets_adds_missing(self, project_id, mock_db):
        """无调整分录 sheets 时进入 missing"""
        pkg_no_adj = {
            "account_package_id": "D1_notes_receivable",
            "primary_wp_code": "D1",
            "sheets": [
                {"sheet_name": "审定表D1-1", "sheet_type": "audit_sheet", "source_wp_code": "D1"},
            ],
            "downstream": [],
        }
        registry = MagicMock()
        registry.get_package.return_value = pkg_no_adj
        svc = WorkpaperAIConclusionContextService(db=mock_db, registry_service=registry)

        with patch.object(svc._program_status_service, "get_all_statuses", return_value=[]):
            with patch.object(svc, "_load_semantic_registry", return_value={"sheets": {}}):
                ctx = await svc.build_context(project_id, "D1_notes_receivable")

        missing_sources = [m["source"] for m in ctx.missing]
        assert "adjustment_impact" in missing_sources


# ---------------------------------------------------------------------------
# 测试：D1 vs D2 上下文差异
# ---------------------------------------------------------------------------


class TestD1VsD2Context:
    """D1 与 D2 上下文差异"""

    @pytest.mark.asyncio
    async def test_d1_no_confirmation_or_ecl(self, project_id, mock_db, mock_registry):
        """D1 上下文不包含函证摘要和坏账/ECL"""
        svc = _build_service(mock_db, mock_registry)

        with patch.object(svc._program_status_service, "get_all_statuses", return_value=[]):
            with patch.object(svc, "_load_semantic_registry", return_value={"sheets": {}}):
                ctx = await svc.build_context(project_id, "D1_notes_receivable")

        # D1 的 confirmation/bad_debt/analysis/disclosure 应为空
        assert ctx.confirmation_summary == {}
        assert ctx.bad_debt_ecl == {}
        assert ctx.analysis_summary == {}
        assert ctx.disclosure_impact == {}
        assert ctx.conclusion_sheet == "D1-C"

    @pytest.mark.asyncio
    async def test_d2_includes_all_context(self, project_id, mock_db):
        """D2 上下文包含完整的函证、ECL、分析、披露"""
        registry = MagicMock()
        registry.get_package.return_value = D2_PACKAGE
        svc = WorkpaperAIConclusionContextService(db=mock_db, registry_service=registry)

        confirmation_data = {
            "status": "loaded",
            "total": 10,
            "coverage_rate": 0.8,
            "diff_total": 1000.0,
        }

        with patch.object(svc._program_status_service, "get_all_statuses", return_value=[]):
            with patch.object(svc, "_load_semantic_registry", return_value={"sheets": {}}):
                with patch.object(
                    svc._summary_service,
                    "get_confirmation_summary",
                    return_value=confirmation_data,
                ):
                    ctx = await svc.build_context(project_id, "D2_accounts_receivable")

        assert ctx.conclusion_sheet == "D2-C"
        assert ctx.confirmation_summary["status"] == "loaded"
        assert ctx.bad_debt_ecl["has_ecl_data"] is True
        assert ctx.analysis_summary["has_analysis"] is True
        assert ctx.disclosure_impact["has_disclosure"] is True


# ---------------------------------------------------------------------------
# 测试：约束验证 - 不导入 generated schema
# ---------------------------------------------------------------------------


class TestNoGeneratedSchemaImport:
    """验证服务不导入 generated schema (1.4 约束)"""

    def test_no_wp_render_schema_service_import(self):
        """服务不导入 wp_render_schema_service"""
        import app.services.workpaper_ai_conclusion_context_service as mod

        source = inspect.getsource(mod)
        # 检查实际 import 语句，不检查注释/docstring
        import_lines = [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        joined_imports = "\n".join(import_lines)
        assert "wp_render_schema_service" not in joined_imports
        assert "generated/" not in joined_imports

        # 检查代码中不引用 generated_inventory_refs
        code_lines = [
            line
            for line in source.splitlines()
            if not line.strip().startswith("#") and not line.strip().startswith('"""') and not line.strip().startswith("'")
        ]
        code_body = "\n".join(code_lines)
        assert "generated_inventory_refs" not in code_body

    def test_no_yaml_parsing(self):
        """服务不直接解析 YAML"""
        import app.services.workpaper_ai_conclusion_context_service as mod

        source = inspect.getsource(mod)
        assert "import yaml" not in source
        assert "yaml.load" not in source
        assert "yaml.safe_load" not in source


# ---------------------------------------------------------------------------
# 测试：to_dict 序列化
# ---------------------------------------------------------------------------


class TestSerialization:
    """AIConclusionContext 序列化"""

    @pytest.mark.asyncio
    async def test_to_dict_structure(self, project_id, mock_db, mock_registry):
        """to_dict 输出包含所有必要字段"""
        svc = _build_service(mock_db, mock_registry)

        with patch.object(svc._program_status_service, "get_all_statuses", return_value=[]):
            with patch.object(svc, "_load_semantic_registry", return_value={"sheets": {}}):
                ctx = await svc.build_context(project_id, "D1_notes_receivable")

        d = ctx.to_dict()
        expected_keys = {
            "project_id", "account_package_id", "wp_code", "conclusion_sheet",
            "audit_sheet_summary", "program_status_summary", "field_sources",
            "confirmation_summary", "bad_debt_ecl", "analysis_summary",
            "adjustment_impact", "disclosure_impact", "missing",
        }
        assert set(d.keys()) == expected_keys
        assert d["wp_code"] == "D1"
        assert d["conclusion_sheet"] == "D1-C"
        assert isinstance(d["missing"], list)
