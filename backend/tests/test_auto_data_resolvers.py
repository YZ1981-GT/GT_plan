"""auto_data_resolvers 注册式解析器测试。

验证：
1. 所有 procedure_table_templates.json 中引用的 auto_data_source 都已注册
2. resolve_auto_data_source 对未注册 source 返回 None
3. 每个 resolver 被正确注册（名称不重复）
4. B 类新增 resolver 功能测试（b15/b22/b23/risk_for_cycle）
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.auto_data_resolvers import (
    _REGISTRY,
    get_registered_sources,
    resolve_auto_data_source,
)


_TEMPLATES_PATH = Path(__file__).resolve().parent.parent / "data" / "procedure_table_templates.json"


def _collect_all_auto_data_sources() -> set[str]:
    """从 procedure_table_templates.json 收集所有引用的 auto_data_source 值。"""
    if not _TEMPLATES_PATH.exists():
        pytest.skip("procedure_table_templates.json 不存在")
    with open(_TEMPLATES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    sources: set[str] = set()
    for table in data.get("tables", {}).values():
        for item in table.get("items", []):
            src = item.get("auto_data_source")
            if src:
                sources.add(src)
    return sources


class TestRegistryCoverage:
    """所有在模板中引用的 auto_data_source 都必须在 registry 中有对应 resolver。"""

    def test_all_template_sources_registered(self):
        sources = _collect_all_auto_data_sources()
        registered = set(get_registered_sources())
        missing = sources - registered
        assert not missing, (
            f"以下 auto_data_source 在模板中使用但未注册 resolver：{missing}\n"
            f"请在 auto_data_resolvers.py 中添加 @auto_resolver(name) 函数"
        )

    def test_no_duplicate_registrations(self):
        """检查 registry 中无重复注册（装饰器天然防重，此测试确认逻辑正确）。"""
        sources = get_registered_sources()
        assert len(sources) == len(set(sources))

    def test_registry_has_at_least_20_resolvers(self):
        """确保迁移完整（原有 20+ 分支）。"""
        assert len(_REGISTRY) >= 20, f"当前仅注册 {len(_REGISTRY)} 个 resolver"

    def test_b_class_resolvers_registered(self):
        """B 类新增 resolver 全部已注册。"""
        expected = {
            "b2_communication_status",
            "b3_independence_status",
            "b15_materiality_summary",
            "b19_related_party_count",
            "b22_entity_control_status",
            "b23_walkthrough_progress",
            "b50_risk_summary",
            "b23_walkthrough_for_cycle",
            "risk_for_cycle",
        }
        registered = set(get_registered_sources())
        missing = expected - registered
        assert not missing, f"B 类 resolver 未注册: {missing}"


@pytest.mark.anyio
async def test_unknown_source_returns_none():
    """未注册的 source 应返回 None（非 KeyError）。"""
    db = AsyncMock()
    result = await resolve_auto_data_source(
        db, uuid.uuid4(), 2025, "nonexistent_source_xyz"
    )
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# B 类 resolver 功能测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestB15MaterialitySummary:
    """b15_materiality_summary resolver 测试。"""

    @pytest.mark.anyio
    async def test_returns_materiality_values(self):
        """有重要性数据时返回三要素。"""
        pid = uuid.uuid4()
        # Mock DB query result
        mock_row = MagicMock()
        mock_row.overall_materiality = Decimal("5000000")
        mock_row.performance_materiality = Decimal("3750000")
        mock_row.trivial_threshold = Decimal("250000")

        mock_result = MagicMock()
        mock_result.first.return_value = mock_row

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await resolve_auto_data_source(db, pid, 2025, "b15_materiality_summary")
        assert result is not None
        assert result["overall_materiality"] == 5000000.0
        assert result["performance_materiality"] == 3750000.0
        assert result["trivial_amount"] == 250000.0
        assert "5,000,000" in result["summary"]

    @pytest.mark.anyio
    async def test_returns_pending_when_no_data(self):
        """无重要性数据时返回待设置。"""
        pid = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.first.return_value = None

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await resolve_auto_data_source(db, pid, 2025, "b15_materiality_summary")
        assert result is not None
        assert "待设置" in result["summary"]
        assert result["overall_materiality"] is None


class TestB22EntityControlStatus:
    """b22_entity_control_status resolver 测试。"""

    @pytest.mark.anyio
    async def test_returns_completion_percentage(self):
        """有完成数据时返回百分比。"""
        pid = uuid.uuid4()

        # 模拟两次 db.execute 调用: total=10, completed=3
        mock_total = MagicMock()
        mock_total.scalar.return_value = 10

        mock_completed = MagicMock()
        mock_completed.scalar.return_value = 3

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[mock_total, mock_completed])

        result = await resolve_auto_data_source(db, pid, 2025, "b22_entity_control_status")
        assert result is not None
        assert result["completed"] == 3
        assert result["dimensions"] == 5
        assert result["completion_pct"] == 60  # 3/5 * 100

    @pytest.mark.anyio
    async def test_returns_zero_when_no_overrides(self):
        """无覆盖数据时完成率为 0。"""
        pid = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar.return_value = 0

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await resolve_auto_data_source(db, pid, 2025, "b22_entity_control_status")
        assert result is not None
        assert result["completed"] == 0
        assert result["completion_pct"] == 0


class TestB23WalkthroughProgress:
    """b23_walkthrough_progress resolver 测试。"""

    @pytest.mark.anyio
    async def test_returns_progress(self):
        """有完成循环数据时返回进度。"""
        pid = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar.return_value = 7  # 7/14 完成

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await resolve_auto_data_source(db, pid, 2025, "b23_walkthrough_progress")
        assert result is not None
        assert result["completed"] == 7
        assert result["total_cycles"] == 14
        assert result["completion_pct"] == 50

    @pytest.mark.anyio
    async def test_returns_zero_when_none_completed(self):
        """无完成循环时返回 0%。"""
        pid = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar.return_value = 0

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await resolve_auto_data_source(db, pid, 2025, "b23_walkthrough_progress")
        assert result is not None
        assert result["completed"] == 0
        assert result["completion_pct"] == 0


class TestB23WalkthroughForCycle:
    """b23_walkthrough_for_cycle resolver 测试。"""

    @pytest.mark.anyio
    async def test_returns_effective_when_concluded(self):
        """穿行测试结论为 design_effective 时返回确认有效。"""
        pid = uuid.uuid4()

        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={
                "ctrl_1": {"conclusion": "design_effective", "summary": "OK"},
            })

            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "b23_walkthrough_for_cycle", cycle="销售收入"
            )
        assert result is not None
        assert result["design_effective"] is True
        assert "设计有效" in result["summary"]

    @pytest.mark.anyio
    async def test_returns_ineffective(self):
        """穿行测试结论为 design_ineffective 时返回缺陷。"""
        pid = uuid.uuid4()

        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={
                "ctrl_1": {"conclusion": "design_ineffective"},
            })

            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "b23_walkthrough_for_cycle", cycle="采购"
            )
        assert result is not None
        assert result["design_effective"] is False
        assert "缺陷" in result["summary"]

    @pytest.mark.anyio
    async def test_returns_none_without_cycle_param(self):
        """未指定循环参数时返回未指定。"""
        pid = uuid.uuid4()
        result = await resolve_auto_data_source(
            AsyncMock(), pid, 2025, "b23_walkthrough_for_cycle"
        )
        assert result is not None
        assert result["design_effective"] is None
        assert "未指定" in result["summary"]

    @pytest.mark.anyio
    async def test_returns_incomplete_when_no_data(self):
        """无 field_overrides 数据时返回未完成。"""
        pid = uuid.uuid4()

        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={})

            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "b23_walkthrough_for_cycle", cycle="货币资金"
            )
        assert result is not None
        assert result["design_effective"] is None
        assert "未完成" in result["summary"]


class TestRiskForCycle:
    """risk_for_cycle resolver 测试。"""

    @pytest.mark.anyio
    async def test_returns_risks_for_matching_cycle(self):
        """匹配循环代号时返回对应风险列表。"""
        pid = uuid.uuid4()

        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={
                "risk_1": {
                    "cycle_code": "D",
                    "description": "收入确认时点不当",
                    "assertion": "存在",
                    "risk_level": "high",
                    "is_special_risk": "true",
                },
                "risk_2": {
                    "cycle_code": "D",
                    "description": "销售退回低估",
                    "assertion": "完整性",
                    "risk_level": "medium",
                    "is_special_risk": "false",
                },
                "risk_3": {
                    "cycle_code": "E",
                    "description": "现金舞弊",
                    "assertion": "存在",
                    "risk_level": "high",
                    "is_special_risk": "true",
                },
            })

            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "risk_for_cycle", cycle="D"
            )
        assert result is not None
        assert len(result["risks"]) == 2
        assert "2项风险" in result["summary"]
        assert "1项特别风险" in result["summary"]

    @pytest.mark.anyio
    async def test_returns_empty_when_no_matching_risks(self):
        """循环无风险条目时返回暂无。"""
        pid = uuid.uuid4()

        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={
                "risk_1": {"cycle_code": "D", "description": "test"},
            })

            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "risk_for_cycle", cycle="E"
            )
        assert result is not None
        assert result["risks"] == []
        assert "暂无" in result["summary"]

    @pytest.mark.anyio
    async def test_returns_empty_without_cycle_param(self):
        """未指定循环参数时返回未指定。"""
        pid = uuid.uuid4()
        result = await resolve_auto_data_source(
            AsyncMock(), pid, 2025, "risk_for_cycle"
        )
        assert result is not None
        assert result["risks"] == []
        assert "未指定" in result["summary"]

    @pytest.mark.anyio
    async def test_returns_empty_when_no_risk_data(self):
        """无风险数据时返回未完成。"""
        pid = uuid.uuid4()

        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={})

            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "risk_for_cycle", cycle="D"
            )
        assert result is not None
        assert result["risks"] == []
        assert "未完成" in result["summary"]



# ═══════════════════════════════════════════════════════════════════════════════
# C 类 resolver 功能测试 (Phase 5 Task 33)
# ═══════════════════════════════════════════════════════════════════════════════


class TestControlDeficiencyCount:
    """control_deficiency_count resolver 测试（Task 2.4 迁入 _REGISTRY）。"""

    @pytest.mark.anyio
    async def test_returns_count_when_issues_exist(self):
        """有内控缺陷时返回计数摘要。"""
        pid = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 3

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await resolve_auto_data_source(db, pid, 2025, "control_deficiency_count")
        assert result is not None
        assert "3项内控缺陷" in result["summary"]

    @pytest.mark.anyio
    async def test_returns_none_message_when_no_issues(self):
        """无内控缺陷时返回暂无摘要。"""
        pid = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await resolve_auto_data_source(db, pid, 2025, "control_deficiency_count")
        assert result is not None
        assert "暂无" in result["summary"]

    def test_control_deficiency_count_registered(self):
        """control_deficiency_count 已在 _REGISTRY 中注册。"""
        assert "control_deficiency_count" in _REGISTRY


class TestCClassResolversRegistered:
    """C 类 5 个 resolver 全部已注册。"""

    def test_c_relevant_resolvers_registered(self):
        """C 类相关 5 个 resolver 必须全部在 registry 中。"""
        expected = {
            "control_test_result_for_cycle",
            "b22_entity_control_list",
            "itgc_test_result",
            "je_filter_from_ledger",
            "internal_audit_reliance",
        }
        registered = set(get_registered_sources())
        missing = expected - registered
        assert not missing, f"C 类 resolver 未注册: {missing}"


class TestControlTestResultForCycle:
    """control_test_result_for_cycle resolver 测试。"""

    @pytest.mark.anyio
    async def test_returns_effective_conclusion(self):
        """有控制测试结论（有效）时返回确认信息。"""
        pid = uuid.uuid4()

        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={
                "C2": {
                    "conclusion": "有效",
                    "tested_controls": "8",
                    "deviation_count": "0",
                },
            })

            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "control_test_result_for_cycle", cycle="销售收入"
            )
        assert result is not None
        assert result["conclusion"] == "有效"
        assert result["tested_controls"] == 8
        assert result["deviation_count"] == 0
        assert "有效" in result["summary"]

    @pytest.mark.anyio
    async def test_returns_partial_effective_with_deviation(self):
        """偏差结论覆盖主结论为"部分有效"。"""
        pid = uuid.uuid4()

        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={
                "C3": {
                    "conclusion": "有效",
                    "tested_controls": "5",
                    "deviation_count": "2",
                },
                "C3-2": {
                    "deviation_conclusion": "部分有效",
                },
            })

            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "control_test_result_for_cycle", cycle="货币资金"
            )
        assert result is not None
        assert result["conclusion"] == "部分有效"
        assert "部分有效" in result["summary"]

    @pytest.mark.anyio
    async def test_returns_none_without_cycle_param(self):
        """未指定循环参数时返回未指定。"""
        pid = uuid.uuid4()
        result = await resolve_auto_data_source(
            AsyncMock(), pid, 2025, "control_test_result_for_cycle"
        )
        assert result is not None
        assert result["conclusion"] is None
        assert "未指定" in result["summary"]

    @pytest.mark.anyio
    async def test_returns_incomplete_when_no_data(self):
        """无 field_overrides 数据时返回未完成。"""
        pid = uuid.uuid4()

        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={})

            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "control_test_result_for_cycle", cycle="采购存货"
            )
        assert result is not None
        assert result["conclusion"] is None
        assert "未完成" in result["summary"]

    @pytest.mark.anyio
    async def test_returns_invalid_conclusion(self):
        """结论为"无效"时返回已放弃信赖。"""
        pid = uuid.uuid4()

        with patch("app.services.field_override_service.FieldOverrideService") as MockSvc:
            mock_svc = AsyncMock()
            MockSvc.return_value = mock_svc
            mock_svc.get_batch = AsyncMock(return_value={
                "C5": {
                    "conclusion": "无效",
                    "tested_controls": "3",
                    "deviation_count": "3",
                },
            })

            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "control_test_result_for_cycle", cycle="投资"
            )
        assert result is not None
        assert result["conclusion"] == "无效"
        assert "无效" in result["summary"]
        assert "放弃信赖" in result["summary"]
