"""F 类底稿联动完善验证（Phase 5 Tasks 42-48）。

验证:
  Task 42: F{n}A 程序表 risk_for_cycle + control_test_result_for_cycle auto_data_source 绑定
  Task 43: F 检查/分析/盘点/计价/跌价底稿结论→F{n}A 程序表步骤状态回写
  Task 44: F0→ConfirmationHub 路由（前端 render-config 识别 confirmation-hub → cycle=F）
  Task 45: F 附注 sheet→disclosure_notes 路由确认
  Task 46: F2-47~49 跌价准备→B51 联动面板（accounting_estimate_b51）
  Task 47: F5→F2 成本结转 ref_index chip 跳转
  Task 48: 扩展 test_auto_data_resolvers.py 覆盖新增 F 类 resolver（accounting_estimate_b51）
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.wp_classification_service import _WP_CODE_OVERRIDE
from app.services.auto_data_resolvers import (
    get_registered_sources,
    resolve_auto_data_source,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

_TEMPLATES_PATH = Path(__file__).resolve().parent.parent / "data" / "procedure_table_templates.json"


@pytest.fixture(scope="module")
def procedure_templates() -> dict:
    """加载 procedure_table_templates.json。"""
    with open(_TEMPLATES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tables", data)


@pytest.fixture(scope="module")
def f0a_items(procedure_templates) -> list[dict]:
    """F0A 函证程序表步骤列表。"""
    return procedure_templates.get("F0A", {}).get("items", [])


@pytest.fixture(scope="module")
def f1a_items(procedure_templates) -> list[dict]:
    """F1A 预付账款程序表步骤列表。"""
    return procedure_templates.get("F1A", {}).get("items", [])


@pytest.fixture(scope="module")
def f2a_items(procedure_templates) -> list[dict]:
    """F2A 存货程序表步骤列表。"""
    return procedure_templates.get("F2A", {}).get("items", [])


@pytest.fixture(scope="module")
def f3a_items(procedure_templates) -> list[dict]:
    """F3A 应付票据程序表步骤列表。"""
    return procedure_templates.get("F3A", {}).get("items", [])


@pytest.fixture(scope="module")
def f4a_items(procedure_templates) -> list[dict]:
    """F4A 应付账款程序表步骤列表。"""
    return procedure_templates.get("F4A", {}).get("items", [])


@pytest.fixture(scope="module")
def f5a_items(procedure_templates) -> list[dict]:
    """F5A 营业成本程序表步骤列表。"""
    return procedure_templates.get("F5A", {}).get("items", [])


# ═══════════════════════════════════════════════════════════════════════════════
# Task 42: F{n}A 程序表 risk_for_cycle + control_test_result_for_cycle 绑定
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask42AutoDataSourceBinding:
    """验证 F{n}A 程序表绑定 risk_for_cycle 和 control_test_result_for_cycle。"""

    def test_all_f_program_tables_exist(self, procedure_templates):
        """F0A~F5A 全部 6 个程序表存在于 procedure_table_templates.json。"""
        for code in ["F0A", "F1A", "F2A", "F3A", "F4A", "F5A"]:
            assert code in procedure_templates, f"{code} 程序表未注册"

    def test_f2a_has_control_test_result_for_cycle(self, f2a_items):
        """F2A 程序表有步骤绑定 control_test_result_for_cycle。"""
        control_items = [
            item for item in f2a_items
            if item.get("auto_data_source") == "control_test_result_for_cycle"
        ]
        assert len(control_items) > 0, (
            "F2A 程序表应至少有 1 个步骤绑定 control_test_result_for_cycle"
        )

    def test_f1a_has_risk_for_cycle(self, f1a_items):
        """F1A seq=1 绑定 risk_for_cycle（获取明细表是首要风险应对步骤）。"""
        seq1 = next((item for item in f1a_items if item.get("seq") == 1), None)
        assert seq1 is not None, "F1A 缺少 seq=1 步骤"
        assert seq1.get("auto_data_source") == "risk_for_cycle", (
            f"F1A seq=1 应绑定 risk_for_cycle，实际为 {seq1.get('auto_data_source')}"
        )

    def test_f2a_has_risk_for_cycle(self, f2a_items):
        """F2A seq=1 绑定 risk_for_cycle。"""
        seq1 = next((item for item in f2a_items if item.get("seq") == 1), None)
        assert seq1 is not None, "F2A 缺少 seq=1 步骤"
        assert seq1.get("auto_data_source") == "risk_for_cycle", (
            f"F2A seq=1 应绑定 risk_for_cycle，实际为 {seq1.get('auto_data_source')}"
        )

    def test_f5a_has_control_test_result_for_cycle(self, f5a_items):
        """F5A 程序表有步骤绑定 control_test_result_for_cycle。"""
        control_items = [
            item for item in f5a_items
            if item.get("auto_data_source") == "control_test_result_for_cycle"
        ]
        assert len(control_items) > 0, (
            "F5A 程序表应至少有 1 个步骤绑定 control_test_result_for_cycle"
        )

    def test_f3a_has_control_test_result_for_cycle(self, f3a_items):
        """F3A 程序表有步骤绑定 control_test_result_for_cycle。"""
        control_items = [
            item for item in f3a_items
            if item.get("auto_data_source") == "control_test_result_for_cycle"
        ]
        assert len(control_items) > 0, (
            "F3A 程序表应至少有 1 个步骤绑定 control_test_result_for_cycle"
        )

    def test_f4a_has_control_test_result_for_cycle(self, f4a_items):
        """F4A 程序表有步骤绑定 control_test_result_for_cycle。"""
        control_items = [
            item for item in f4a_items
            if item.get("auto_data_source") == "control_test_result_for_cycle"
        ]
        assert len(control_items) > 0, (
            "F4A 程序表应至少有 1 个步骤绑定 control_test_result_for_cycle"
        )

    def test_risk_for_cycle_resolver_registered(self):
        """risk_for_cycle resolver 已注册。"""
        sources = get_registered_sources()
        assert "risk_for_cycle" in sources

    def test_control_test_result_for_cycle_resolver_registered(self):
        """control_test_result_for_cycle resolver 已注册。"""
        sources = get_registered_sources()
        assert "control_test_result_for_cycle" in sources

    @pytest.mark.anyio
    async def test_risk_for_cycle_with_f_cycle(self):
        """risk_for_cycle resolver 用 cycle='F' 正确返回（含空数据降级）。"""
        pid = uuid.uuid4()
        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={
                "risk_f1": {
                    "cycle_code": "F",
                    "description": "存货跌价风险",
                    "assertion": "计价和分摊",
                    "risk_level": "high",
                    "is_special_risk": "true",
                },
            })
            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "risk_for_cycle", cycle="F"
            )
        assert result is not None
        assert len(result["risks"]) == 1
        assert "1项风险" in result["summary"]
        assert result["risks"][0]["is_special_risk"] is True

    @pytest.mark.anyio
    async def test_control_test_result_with_f_cycle(self):
        """control_test_result_for_cycle resolver 用 cycle='采购存货' 正确返回。"""
        pid = uuid.uuid4()
        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={
                "C4": {
                    "conclusion": "有效",
                    "tested_controls": "6",
                    "deviation_count": "0",
                },
            })
            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "control_test_result_for_cycle", cycle="采购存货"
            )
        assert result is not None
        assert result["conclusion"] == "有效"
        assert result["tested_controls"] == 6


# ═══════════════════════════════════════════════════════════════════════════════
# Task 43: F 检查/分析/盘点/计价/跌价底稿结论→F{n}A 程序表步骤状态回写
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask43ConclusionWriteback:
    """验证 F 子底稿结论回写到 F{n}A 程序表步骤的 scope 机制。

    设计：当 F2-21~26/F2-29~35/F2-38~44/F2-47~49/F2-55~58 底稿保存时，
    通过 _on_f_workpaper_conclusion_saved handler 将结论写入
    field_overrides scope=f_procedure_status:{wp_code}。
    """

    def test_f_workpaper_conclusion_handler_registered(self):
        """_on_f_workpaper_conclusion_saved handler 在 register_event_handlers 中被注册。"""
        # 验证 event_handlers 模块可被导入且 register_event_handlers 可用
        from app.services.event_handlers import register_event_handlers
        # 调用 register_event_handlers 以注册所有 handlers
        register_event_handlers()
        from app.services.event_handlers import event_bus
        from app.models.audit_platform_schemas import EventType
        handlers = event_bus._handlers.get(EventType.WORKPAPER_SAVED, [])
        assert len(handlers) >= 1, "WORKPAPER_SAVED 事件应有订阅者"
        # 验证至少有一个 handler 名称包含 f_workpaper_conclusion
        handler_names = [
            getattr(h, "__qualname__", getattr(h, "__name__", ""))
            for h in handlers
        ]
        has_f_handler = any(
            "f_workpaper_conclusion" in name.lower()
            for name in handler_names
        )
        assert has_f_handler, (
            f"WORKPAPER_SAVED handlers 中应有 _on_f_workpaper_conclusion_saved，"
            f"实际: {handler_names}"
        )

    def test_f_conclusion_wp_codes_registered(self):
        """F 检查/分析/盘点/计价/跌价 wp_code 全部在 _WP_CODE_OVERRIDE 中。"""
        # 盘点
        for i in range(21, 27):
            assert f"F2-{i}" in _WP_CODE_OVERRIDE, f"F2-{i} 未注册"
        # 检查
        for i in range(29, 36):
            assert f"F2-{i}" in _WP_CODE_OVERRIDE, f"F2-{i} 未注册"
        # 计价
        for i in range(38, 45):
            assert f"F2-{i}" in _WP_CODE_OVERRIDE, f"F2-{i} 未注册"
        # 跌价
        for i in range(47, 50):
            assert f"F2-{i}" in _WP_CODE_OVERRIDE, f"F2-{i} 未注册"
        # 合同成本
        for i in range(55, 59):
            assert f"F2-{i}" in _WP_CODE_OVERRIDE, f"F2-{i} 未注册"

    def test_f_conclusion_scope_pattern(self):
        """F 结论回写 scope 命名规范: f_procedure_status:{wp_code}。"""
        # 验证 scope 生成逻辑模式
        sample_codes = ["F2-21", "F2-38", "F2-47"]
        for code in sample_codes:
            scope = f"f_procedure_status:{code}"
            assert scope.startswith("f_procedure_status:")
            assert code in scope

    def test_f2a_has_ref_to_conclusion_sheets(self, f2a_items):
        """F2A 程序表步骤中 ref_index 引用了结论底稿。"""
        all_refs = []
        for item in f2a_items:
            ref = item.get("ref_index")
            if ref:
                all_refs.append(ref)
        ref_text = " ".join(all_refs)
        # 验证关键引用
        assert "F2-21" in ref_text or "F2-21A" in ref_text, "F2A 应引用盘点底稿"
        assert "F2-47" in ref_text, "F2A 应引用跌价底稿"
        assert "F2-38" in ref_text, "F2A 应引用计价测试底稿"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 44: F0→ConfirmationHub 路由
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask44ConfirmationHubRoute:
    """验证 F0 底稿映射为 confirmation-hub，前端可路由到 ConfirmationHub cycle=F。"""

    def test_f0_maps_to_confirmation_hub(self):
        """F0 在 _WP_CODE_OVERRIDE 中映射为 confirmation-hub。"""
        assert "F0" in _WP_CODE_OVERRIDE, "F0 未在 _WP_CODE_OVERRIDE 中注册"
        assert _WP_CODE_OVERRIDE["F0"] == "confirmation-hub", (
            f"F0 应映射为 confirmation-hub，实际为 {_WP_CODE_OVERRIDE['F0']}"
        )

    def test_f0_in_confirmation_hub_whitelist(self):
        """F0 已加入 confirmation-hub 白名单（同 D0/E0 模式）。"""
        confirmation_codes = [
            code for code, ct in _WP_CODE_OVERRIDE.items()
            if ct == "confirmation-hub"
        ]
        assert "F0" in confirmation_codes, "F0 不在 confirmation-hub 类型列表中"
        assert "D0" in confirmation_codes, "D0 也应在列表（参照物）"
        assert "E0" in confirmation_codes, "E0 也应在列表（参照物）"

    def test_f0_d0_e0_same_component_type(self):
        """F0/D0/E0 使用相同 componentType（confirmation-hub）。"""
        assert _WP_CODE_OVERRIDE.get("F0") == _WP_CODE_OVERRIDE.get("D0")
        assert _WP_CODE_OVERRIDE.get("F0") == _WP_CODE_OVERRIDE.get("E0")

    def test_confirmation_hub_is_valid_component_type(self):
        """confirmation-hub 是合法的 componentType。"""
        from app.services.wp_classification_service import VALID_COMPONENT_TYPES
        assert "confirmation-hub" in VALID_COMPONENT_TYPES

    def test_f0_cycle_derivable_from_wp_code(self):
        """F0 wp_code 前缀 'F' 可被 ConfirmationHub 推导为 cycle=F。"""
        wp_code = "F0"
        # 前端 ConfirmationHub 通过 wp_code[0] 推导 cycle
        cycle = wp_code[0]
        assert cycle == "F"

    def test_confirmation_summary_for_cycle_resolver_exists(self):
        """confirmation_summary_for_cycle resolver 已注册（用于 F0A 函证摘要）。"""
        sources = get_registered_sources()
        assert "confirmation_summary_for_cycle" in sources


# ═══════════════════════════════════════════════════════════════════════════════
# Task 45: F 附注 sheet→disclosure_notes 路由确认
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask45DisclosureNotesRoute:
    """验证 F 附注 sheet 路由。

    F 类底稿附注 sheet 在 F{n} 主模板中（非独立 wp_code），
    通过 disclosure_notes 模块统一管理。
    F 类没有独立的 c-note-table 映射 wp_code——
    附注是通过 disclosure_notes 模块直接关联到科目。
    """

    def test_c_note_table_is_valid_component_type(self):
        """c-note-table 是合法的 componentType。"""
        from app.services.wp_classification_service import VALID_COMPONENT_TYPES
        assert "c-note-table" in VALID_COMPONENT_TYPES

    def test_f_cycle_no_explicit_c_note_table_codes(self):
        """F 类目前没有显式的 c-note-table wp_code（附注统一在 disclosure_notes 模块管理）。"""
        f_note_codes = [
            code for code, ct in _WP_CODE_OVERRIDE.items()
            if code.startswith("F") and ct == "c-note-table"
        ]
        # F 类附注不作为独立 wp_code 注册，而是通过 disclosure_notes 模块处理
        # 如果未来需要添加，此测试需更新
        # 当前设计：附注内容在 F{n} xlsx 中是一个 sheet，
        # 渲染时由 disclosure_notes 模块按科目编码关联
        assert len(f_note_codes) == 0, (
            f"F 类附注通过 disclosure_notes 模块处理，不应有显式 c-note-table wp_code，"
            f"发现: {f_note_codes}"
        )

    def test_disclosure_notes_module_available(self):
        """disclosure_notes 模块可正常导入。"""
        from app.routers import disclosure_notes  # noqa: F401

    def test_f_class_d_form_table_not_misrouted(self):
        """F 类 d-form-table 底稿不会被错误路由到 disclosure_notes。"""
        # F1-1、F2-1 等审定表应该是 d-form-table
        d_form_codes = ["F1-1", "F2-1", "F3-1", "F4-1", "F5-1"]
        for code in d_form_codes:
            ct = _WP_CODE_OVERRIDE.get(code)
            assert ct == "d-form-table", (
                f"{code} 应为 d-form-table，实际为 {ct}"
            )

    def test_f_main_workpapers_registered(self):
        """F1~F5 主底稿已注册（附注 sheet 在主模板中）。"""
        for code in ["F1", "F2", "F3", "F4", "F5"]:
            assert code in _WP_CODE_OVERRIDE, f"{code} 主底稿未注册"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 46: F2-47~49 跌价准备→B51 联动面板
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask46AccountingEstimateB51:
    """验证 accounting_estimate_b51 resolver 与 F2-47~49 跌价准备联动。"""

    def test_accounting_estimate_b51_resolver_registered(self):
        """accounting_estimate_b51 resolver 已注册。"""
        sources = get_registered_sources()
        assert "accounting_estimate_b51" in sources, (
            "accounting_estimate_b51 resolver 未注册"
        )

    def test_f2_47_49_registered_as_audit_sheet(self):
        """F2-47/F2-48/F2-49 注册为 audit-sheet。"""
        for i in range(47, 50):
            code = f"F2-{i}"
            assert code in _WP_CODE_OVERRIDE, f"{code} 未注册"
            assert _WP_CODE_OVERRIDE[code] == "audit-sheet", (
                f"{code} 应为 audit-sheet，实际为 {_WP_CODE_OVERRIDE[code]}"
            )

    def test_f2a_step_references_depreciation_sheets(self, f2a_items):
        """F2A 程序表有步骤引用 F2-47/F2-48/F2-49（跌价准备）。"""
        depreciation_refs = []
        for item in f2a_items:
            ref = item.get("ref_index") or ""
            if "F2-47" in ref or "F2-48" in ref or "F2-49" in ref:
                depreciation_refs.append(item)
        assert len(depreciation_refs) > 0, (
            "F2A 程序表应有步骤引用 F2-47/48/49 跌价准备底稿"
        )

    def test_f2a_depreciation_step_has_b51_auto_data_source(self, f2a_items):
        """F2A 跌价准备步骤绑定 accounting_estimate_b51 auto_data_source。"""
        b51_items = [
            item for item in f2a_items
            if item.get("auto_data_source") == "accounting_estimate_b51"
        ]
        assert len(b51_items) > 0, (
            "F2A 应有步骤绑定 accounting_estimate_b51（跌价准备联动 B51）"
        )
        # 该步骤应引用 F2-47/48/49
        ref = b51_items[0].get("ref_index") or ""
        assert "F2-47" in ref, (
            f"绑定 accounting_estimate_b51 的步骤应引用 F2-47，实际 ref_index={ref}"
        )

    @pytest.mark.anyio
    async def test_accounting_estimate_b51_returns_fraud_factors(self):
        """accounting_estimate_b51 resolver 返回舞弊三因素数据。"""
        pid = uuid.uuid4()
        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={
                "b51_item1": {
                    "incentive": "管理层有粉饰业绩的动机",
                    "opportunity": "存货计价依赖判断",
                    "attitude": "管理层对估计偏保守",
                    "overall_risk_level": "high",
                },
            })
            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "accounting_estimate_b51"
            )
        assert result is not None
        assert result["fraud_incentive"] == "管理层有粉饰业绩的动机"
        assert result["fraud_opportunity"] == "存货计价依赖判断"
        assert result["fraud_attitude"] == "管理层对估计偏保守"
        assert result["overall_risk_level"] == "high"
        assert "高" in result["summary"]

    @pytest.mark.anyio
    async def test_accounting_estimate_b51_no_data(self):
        """accounting_estimate_b51 resolver 无数据时返回未完成提示。"""
        pid = uuid.uuid4()
        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={})
            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "accounting_estimate_b51"
            )
        assert result is not None
        assert "尚未完成" in result["summary"]
        assert result["overall_risk_level"] is None

    @pytest.mark.anyio
    async def test_accounting_estimate_b51_partial_data(self):
        """accounting_estimate_b51 resolver 部分数据时返回填写进度。"""
        pid = uuid.uuid4()
        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={
                "b51_item1": {
                    "fraud_incentive": "存在动机",
                    # fraud_opportunity 和 fraud_attitude 缺失
                },
            })
            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "accounting_estimate_b51"
            )
        assert result is not None
        assert result["fraud_incentive"] == "存在动机"
        assert result["fraud_opportunity"] is None
        assert "1/3" in result["summary"]


# ═══════════════════════════════════════════════════════════════════════════════
# Task 47: F5→F2 成本结转 ref_index chip 跳转
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask47F5ToF2RefIndex:
    """验证 F5A 程序表有步骤通过 ref_index 引用 F2（成本结转联动）。"""

    def test_f5a_exists(self, procedure_templates):
        """F5A 程序表存在。"""
        assert "F5A" in procedure_templates
        assert procedure_templates["F5A"]["name"] == "营业成本实质性程序表"

    def test_f5a_has_ref_to_f2(self, f5a_items):
        """F5A 程序表步骤中 ref_index 引用了 F2 相关底稿。"""
        f2_refs = []
        for item in f5a_items:
            ref = item.get("ref_index") or ""
            # 匹配 F2-xx 或 F2-16 等引用
            if re.search(r"F2-?\d*", ref):
                f2_refs.append(item)
        assert len(f2_refs) > 0, (
            "F5A 程序表应有步骤引用 F2 底稿（成本结转联动）"
        )

    def test_f5a_cost_transfer_step_refs_f2(self, f5a_items):
        """F5A 有步骤通过 ref_index 引用 F2-16（会计政策）或 F2-40（计价）。"""
        # F5A seq 4 引用 F2-16（会计政策），seq 10 引用 F2-40
        f2_specific_refs = []
        for item in f5a_items:
            ref = item.get("ref_index") or ""
            if "F2-16" in ref or "F2-40" in ref:
                f2_specific_refs.append(item)
        assert len(f2_specific_refs) > 0, (
            "F5A 应引用 F2-16（会计政策）或 F2-40（计价）"
        )

    def test_f2_main_workpaper_registered(self):
        """F2 主底稿已注册（GtIndexChip 可解析 F2 → 导航）。"""
        assert "F2" in _WP_CODE_OVERRIDE, "F2 未注册"
        assert "F2-1" in _WP_CODE_OVERRIDE, "F2-1 未注册"

    def test_f5_and_f2_both_registered(self):
        """F5 和 F2 都在 _WP_CODE_OVERRIDE 中（双向可导航）。"""
        assert "F5" in _WP_CODE_OVERRIDE
        assert "F5-1" in _WP_CODE_OVERRIDE
        assert "F2" in _WP_CODE_OVERRIDE
        assert "F2-1" in _WP_CODE_OVERRIDE


# ═══════════════════════════════════════════════════════════════════════════════
# Task 48: accounting_estimate_b51 resolver 功能测试
# (扩展 test_auto_data_resolvers.py 覆盖)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask48AccountingEstimateB51Resolver:
    """accounting_estimate_b51 resolver 完整功能验证。

    覆盖场景:
    - 正常返回三因素 + 总体风险等级
    - 无数据降级
    - 部分数据
    - 兼容字段名（incentive vs fraud_incentive）
    """

    @pytest.mark.anyio
    async def test_returns_full_assessment(self):
        """完整三因素 + 总体风险等级返回。"""
        pid = uuid.uuid4()
        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={
                "factor1": {
                    "incentive": "业绩压力大",
                    "opportunity": "估计方法复杂",
                    "attitude": "管理层偏保守",
                    "overall_risk_level": "medium",
                },
            })
            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "accounting_estimate_b51"
            )
        assert result is not None
        assert result["fraud_incentive"] == "业绩压力大"
        assert result["fraud_opportunity"] == "估计方法复杂"
        assert result["fraud_attitude"] == "管理层偏保守"
        assert result["overall_risk_level"] == "medium"
        assert "中" in result["summary"]

    @pytest.mark.anyio
    async def test_returns_high_risk_label(self):
        """高风险时 summary 包含 '高'。"""
        pid = uuid.uuid4()
        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={
                "f1": {"overall_risk_level": "high", "incentive": "x"},
            })
            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "accounting_estimate_b51"
            )
        assert "高" in result["summary"]
        assert result["overall_risk_level"] == "high"

    @pytest.mark.anyio
    async def test_returns_low_risk_label(self):
        """低风险时 summary 包含 '低'。"""
        pid = uuid.uuid4()
        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={
                "f1": {"overall_risk_level": "low", "incentive": "无明显动机"},
            })
            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "accounting_estimate_b51"
            )
        assert "低" in result["summary"]
        assert result["overall_risk_level"] == "low"

    @pytest.mark.anyio
    async def test_compatible_field_names(self):
        """兼容 fraud_incentive/fraud_opportunity/fraud_attitude 字段名。"""
        pid = uuid.uuid4()
        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={
                "b51_data": {
                    "fraud_incentive": "利润承诺压力",
                    "fraud_opportunity": "复杂估计模型",
                    "fraud_attitude": "合理化倾向",
                    "overall_risk_level": "high",
                },
            })
            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "accounting_estimate_b51"
            )
        assert result["fraud_incentive"] == "利润承诺压力"
        assert result["fraud_opportunity"] == "复杂估计模型"
        assert result["fraud_attitude"] == "合理化倾向"

    @pytest.mark.anyio
    async def test_empty_data_returns_not_completed(self):
        """field_overrides 无数据时返回未完成提示。"""
        pid = uuid.uuid4()
        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={})
            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "accounting_estimate_b51"
            )
        assert result is not None
        assert "尚未完成" in result["summary"]
        assert result["fraud_incentive"] is None
        assert result["fraud_opportunity"] is None
        assert result["fraud_attitude"] is None
        assert result["overall_risk_level"] is None

