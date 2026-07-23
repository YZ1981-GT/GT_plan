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

    # 新数据源：checklist_responses（B50-T3-*，经 b50_risk_reader.load_b50_risks）
    _B50_RISKS = [
        {"risk_id": "收入确认-existence", "account": "收入确认", "assertion": "existence",
         "assertion_cn": "存在", "risk_level": "H", "is_special_risk": True, "cycle": "D",
         "description": "【高风险】收入确认 - 存在认定（特别风险）"},
        {"risk_id": "收入确认-completeness", "account": "收入确认", "assertion": "completeness",
         "assertion_cn": "完整性", "risk_level": "M", "is_special_risk": False, "cycle": "D",
         "description": "【中风险】收入确认 - 完整性认定"},
        {"risk_id": "货币资金-existence", "account": "货币资金", "assertion": "existence",
         "assertion_cn": "存在", "risk_level": "H", "is_special_risk": True, "cycle": "E",
         "description": "【高风险】货币资金 - 存在认定（特别风险）"},
    ]

    @pytest.mark.anyio
    async def test_returns_risks_for_matching_cycle(self):
        """匹配循环代号时返回对应风险列表。"""
        pid = uuid.uuid4()
        with patch("app.services.b50_risk_reader.load_b50_risks",
                   AsyncMock(return_value=list(self._B50_RISKS))):
            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "risk_for_cycle", cycle="D"
            )
        assert result is not None
        assert len(result["risks"]) == 2
        assert "2项认定层次风险" in result["summary"]
        assert "1项特别风险" in result["summary"]

    @pytest.mark.anyio
    async def test_matches_by_table_code_first_letter(self):
        """cycle 传完整 table_code（如 D2A）时按首字母匹配。"""
        pid = uuid.uuid4()
        with patch("app.services.b50_risk_reader.load_b50_risks",
                   AsyncMock(return_value=list(self._B50_RISKS))):
            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "risk_for_cycle", cycle="D2A"
            )
        assert result is not None
        assert len(result["risks"]) == 2

    @pytest.mark.anyio
    async def test_returns_empty_when_no_matching_risks(self):
        """循环无风险条目时返回暂无。"""
        pid = uuid.uuid4()
        with patch("app.services.b50_risk_reader.load_b50_risks",
                   AsyncMock(return_value=[
                       {"risk_id": "收入确认-existence", "account": "收入确认",
                        "assertion": "existence", "assertion_cn": "存在", "risk_level": "H",
                        "is_special_risk": True, "cycle": "D", "description": "x"},
                   ])):
            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "risk_for_cycle", cycle="L"
            )
        assert result is not None
        assert result["risks"] == []
        assert "暂无" in result["summary"]

    @pytest.mark.anyio
    async def test_returns_all_without_cycle_param(self):
        """未指定循环参数时返回全部风险（避免模板未传 cycle 导致恒空）。"""
        pid = uuid.uuid4()
        with patch("app.services.b50_risk_reader.load_b50_risks",
                   AsyncMock(return_value=list(self._B50_RISKS))):
            result = await resolve_auto_data_source(
                AsyncMock(), pid, 2025, "risk_for_cycle"
            )
        assert result is not None
        assert len(result["risks"]) == 3
        assert "全部已识别3项" in result["summary"]

    @pytest.mark.anyio
    async def test_returns_empty_when_no_risk_data(self):
        """无风险数据时返回未完成。"""
        pid = uuid.uuid4()
        with patch("app.services.b50_risk_reader.load_b50_risks",
                   AsyncMock(return_value=[])):
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


# ═══════════════════════════════════════════════════════════════════════════════
# 全量 resolver 成功契约守卫（A 增强版）
#
# 背景：resolver 返回结构被前端按 `summary` 渲染；调度器 resolve_auto_data_source
# 仅在 resolver 抛异常时兜底为 {"_error": True}。若某 resolver 漏 summary 键、
# 返回非 dict、或因导入/查询写错直接裸抛，调度器会把它降级成 _error，前端永远
# 显示"数据获取失败"——属静默契约破裂。本守卫遍历全部已注册 resolver，用"任意
# 查询都返回空结果"的 AsyncMock db 驱动它们走"无数据降级"分支，断言：
#   1. resolver 不裸抛异常（导入路径/查询结构正确）
#   2. 返回值为 dict 且必含 `summary` 键（即便降级分支也要给 summary）
#
# 注：本守卫不验证 summary 的具体业务文案（那需真实 DB 数据，见 test_auto_data_
# resolvers.py 中针对 b15/b22/b23/control_test 等的功能测试）。它只锁死"成功路径
# 契约形状"，防止新增 resolver 漏 summary 或写坏导入。
# 曾用本守卫的探针抓出 2 个真 bug：b3_independence_status（导入不存在的 ORM 类
# ChecklistResponse + 查不存在的 wp_code 列）、related_party_disclosure_check
# （导入不存在的 app.models.disclosure_models）。
# ═══════════════════════════════════════════════════════════════════════════════


def _make_empty_result_db() -> AsyncMock:
    """构造一个对任意查询都返回"空结果"的 AsyncMock db。

    覆盖 resolver 取数的全部惯用形态：scalar / scalar_one_or_none / first /
    one / fetchall / fetchone / all，统一给空值，迫使 resolver 走无数据降级分支。
    """
    db = AsyncMock()
    result = MagicMock()
    result.scalar.return_value = 0
    result.scalar_one_or_none.return_value = None
    result.first.return_value = None
    result.one.return_value = (0, 0)
    result.fetchall.return_value = []
    result.fetchone.return_value = None
    result.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    return db


# resolver 可选 kwargs 的合理默认值（cycle/wp_code 等域参数）。
# 给齐这些值，确保需要参数的 resolver 也能走进正常分支而非"未指定"早退
# （早退分支同样返回含 summary 的 dict，所以给不给都满足契约，这里给齐更贴近真实调用）。
_RESOLVER_KW_DEFAULTS = {
    "cycle": "D",
    "wp_code": "K8",
    "account_prefix": "6601",
    "filter_criteria": {},
}


@pytest.mark.anyio
@pytest.mark.parametrize("source_name", sorted(_REGISTRY.keys()))
async def test_resolver_success_contract(source_name):
    """每个已注册 resolver：用空结果 db 驱动，必须不裸抛且返回含 summary 的 dict。"""
    db = _make_empty_result_db()
    fn = _REGISTRY[source_name]

    try:
        result = await fn(db, uuid.uuid4(), 2025, **_RESOLVER_KW_DEFAULTS)
    except Exception as e:  # noqa: BLE001 — 守卫本身就是要抓裸抛
        pytest.fail(
            f"resolver '{source_name}' 直接裸抛 {type(e).__name__}: {e}\n"
            f"（调度器会把它兜成 _error，前端永远显示'数据获取失败'。"
            f"常见根因：导入路径写错 / 查询了不存在的列。）"
        )

    # resolver 允许返回 None（仅调度器对"未注册 source"用），但已注册 resolver
    # 的成功/降级路径都必须返回 dict 且含 summary。
    assert isinstance(result, dict), (
        f"resolver '{source_name}' 返回了 {type(result).__name__} 而非 dict"
    )
    assert "summary" in result, (
        f"resolver '{source_name}' 返回的 dict 缺少 'summary' 键：keys={list(result.keys())}\n"
        f"（前端按 summary 渲染，缺失会导致空白/报错。）"
    )
    assert isinstance(result["summary"], str) and result["summary"], (
        f"resolver '{source_name}' 的 summary 必须是非空字符串，实际：{result['summary']!r}"
    )


@pytest.mark.anyio
async def test_resolver_contract_covers_all_registered():
    """元测试：确认契约守卫确实覆盖了全部已注册 resolver（防参数化漏项）。"""
    # 参数化用的是 _REGISTRY 快照；此测试确认 registry 非空且数量合理。
    assert len(_REGISTRY) >= 40, f"resolver 数量异常偏少：{len(_REGISTRY)}"
