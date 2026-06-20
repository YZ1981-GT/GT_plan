"""科目工作包多文件聚合解析器测试

验证 resolve_package_sheets 消费 account_package_registry：
- D2 应收账款聚合返回全部 sheet（≥14），每个 componentType 为 HTML 类（无 univer/空白）
- GT_Custom / 占位 sheet 跳过
- 无注册表条目返回 None（调用方回退原 classification，零回归）
- _SHEET_TYPE_TO_CLASS 全部值经 class_code_to_component 返回非 None 且 ∈ HTML 白名单

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1-2.7
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.services.account_package_registry_service import (
    AccountPackageRegistryService,
    VALID_SHEET_TYPES,
)
from app.services.wp_account_package_resolver import (
    HTML_RENDERABLE_COMPONENTS,
    _SHEET_TYPE_TO_CLASS,
    _sheet_type_to_component,
    resolve_package_sheets,
)
from app.services.wp_component_type_mapping import class_code_to_component


_DUMMY_PID = uuid4()


# ─── 映射层断言（纯函数，无需 DB/注册表） ───────────────────────────────────


class TestSheetTypeMapping:
    def test_all_mapped_class_codes_resolve_to_html(self):
        """_SHEET_TYPE_TO_CLASS 每个 class_code 经 class_code_to_component
        返回非 None 且落在 HTML 白名单（杜绝 univer 空白）。"""
        for sheet_type, class_code in _SHEET_TYPE_TO_CLASS.items():
            component = class_code_to_component(class_code)
            assert component is not None, f"{sheet_type}→{class_code} 映射到 None"
            assert component in HTML_RENDERABLE_COMPONENTS, (
                f"{sheet_type}→{class_code}→{component} 不在 HTML 白名单"
            )
            assert component != "univer", f"{sheet_type} 不得映射到 univer"

    def test_every_registry_sheet_type_is_mappable(self):
        """注册表所有合法 sheet_type 都能映射到 HTML 组件（无遗漏）。"""
        for sheet_type in VALID_SHEET_TYPES:
            component = _sheet_type_to_component(sheet_type)
            assert component is not None, f"sheet_type={sheet_type} 无法映射到 HTML"
            assert component in HTML_RENDERABLE_COMPONENTS

    def test_analysis_maps_to_audit_sheet_not_univer(self):
        """关键修正点：analysis → audit-sheet（非 univer）。"""
        assert _sheet_type_to_component("analysis") == "audit-sheet"

    def test_disclosure_maps_to_c_note_table(self):
        assert _sheet_type_to_component("disclosure") == "c-note-table"

    def test_conclusion_maps_to_d_form_paragraph(self):
        assert _sheet_type_to_component("conclusion") == "d-form-paragraph"


# ─── D2 真实注册表聚合 ───────────────────────────────────────────────────


class TestResolveD2Package:
    @pytest.mark.asyncio
    async def test_d2_returns_all_sheets(self):
        """D2 应收账款聚合返回注册表声明的全部 sheet（14）+ 合成底稿目录（≥15）。"""
        results = await resolve_package_sheets(None, "D2", _DUMMY_PID)
        assert results is not None
        assert len(results) >= 15

    @pytest.mark.asyncio
    async def test_d2_has_synthetic_directory(self):
        """聚合首位插入合成「底稿目录」(b-index)，供架构树 4 阶段导航。"""
        results = await resolve_package_sheets(None, "D2", _DUMMY_PID)
        assert results is not None
        assert results[0].sheet_name == "底稿目录"
        assert class_code_to_component(results[0].class_code) == "b-index"

    @pytest.mark.asyncio
    async def test_d2_every_component_is_html(self):
        """D2 每个 sheet 的 class_code 派生的 componentType 都是 HTML 类（无 univer）。"""
        results = await resolve_package_sheets(None, "D2", _DUMMY_PID)
        assert results is not None
        for r in results:
            assert r.class_code is not None
            component = class_code_to_component(r.class_code)
            assert component in HTML_RENDERABLE_COMPONENTS, (
                f"sheet '{r.sheet_name}' class_code={r.class_code}→{component} 非 HTML"
            )

    @pytest.mark.asyncio
    async def test_d2_includes_analysis_and_check_sheets(self):
        """聚合不遗漏分析表 D2-5 / 检查表 D2-6~D2-13。"""
        results = await resolve_package_sheets(None, "D2", _DUMMY_PID)
        assert results is not None
        names = [r.sheet_name for r in results]
        assert any("分析表D2-5" in n for n in names), "遗漏 D2-5 分析表"
        assert any("D2-6" in n for n in names), "遗漏 D2-6 检查表"
        assert any("D2-13" in n for n in names), "遗漏 D2-13"

    @pytest.mark.asyncio
    async def test_d1_returns_sheets(self):
        """D1 应收票据也能聚合。"""
        results = await resolve_package_sheets(None, "D1", _DUMMY_PID)
        assert results is not None
        assert len(results) >= 10


# ─── 边界：无条目 / 占位跳过 ──────────────────────────────────────────────


class TestResolveEdgeCases:
    @pytest.mark.asyncio
    async def test_unknown_wp_code_returns_none(self):
        """无注册表条目的科目返回 None（调用方回退原逻辑，零回归）。"""
        results = await resolve_package_sheets(None, "Z99", _DUMMY_PID)
        assert results is None

    @pytest.mark.asyncio
    async def test_gt_custom_sheets_skipped(self, tmp_path):
        """GT_Custom 占位 sheet 被跳过。"""
        reg = {
            "packages": [
                {
                    "account_package_id": "TEST_PKG",
                    "cycle": "D",
                    "account_code": "9999",
                    "account_name": "测试科目",
                    "report_row": None,
                    "note_section": None,
                    "mapping_status": "pending_inventory_reconciliation",
                    "primary_wp_code": "TST",
                    "sheets": [
                        {"sheet_name": "审定表TST-1", "sheet_type": "audit_sheet", "source_wp_code": "TST"},
                        {"sheet_name": "GT_Custom自定义", "sheet_type": "audit_sheet", "source_wp_code": "TST"},
                    ],
                }
            ]
        }
        path = tmp_path / "reg.json"
        path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        svc = AccountPackageRegistryService(registry_path=path)

        results = await resolve_package_sheets(None, "TST", _DUMMY_PID, registry=svc)
        assert results is not None
        names = [r.sheet_name for r in results]
        assert "审定表TST-1" in names
        assert not any("GT_Custom" in n for n in names)
        # 含合成底稿目录置顶
        assert names[0] == "底稿目录"

    @pytest.mark.asyncio
    async def test_mapping_status_ignored(self, tmp_path):
        """pending_inventory_reconciliation 不作消费门控，package 存在即消费 sheets。"""
        reg = {
            "packages": [
                {
                    "account_package_id": "TEST_PENDING",
                    "cycle": "D",
                    "account_code": "8888",
                    "account_name": "待盘点科目",
                    "report_row": None,
                    "note_section": None,
                    "mapping_status": "pending_inventory_reconciliation",
                    "primary_wp_code": "TPD",
                    "sheets": [
                        {"sheet_name": "审定表TPD-1", "sheet_type": "audit_sheet", "source_wp_code": "TPD"},
                    ],
                }
            ]
        }
        path = tmp_path / "reg.json"
        path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        svc = AccountPackageRegistryService(registry_path=path)

        results = await resolve_package_sheets(None, "TPD", _DUMMY_PID, registry=svc)
        assert results is not None
        # 1 真实 sheet + 合成底稿目录
        assert len(results) == 2
        assert any(r.sheet_name == "审定表TPD-1" for r in results)
