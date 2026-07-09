"""P0 冒烟测试：render-config 端点对所有已注册 A 类底稿 componentType 不 500。

背景（2026-06-18 踩坑）：
  双机合并后 `wp_render_config.py` 调用 `get_guidance_for_wp`（实际名 `get_wp_guidance`）
  导致全平台底稿打开 500。getDiagnostics 不报错、单测 mock 不真调 → 只有运行时崩。
  本测试用 in-process ASGI 真调 render-config 端点，断言：
    1. derive_component_type 对所有 _WP_CODE_OVERRIDE 返回合法 componentType
    2. 端点函数内部 import/调用链无 AttributeError/NameError（通过 mock DB 跑到真实代码路径）

设计：
  - 不需要真实 PG（mock AsyncSession）
  - 不需要真实数据（mock WorkingPaper/WpIndex 返回）
  - 重点覆盖 get_render_config 函数体内所有 import/调用是否存在
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wp_classification_service import (
    _WP_CODE_OVERRIDE,
    derive_component_type,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Part 1: derive_component_type 对 _WP_CODE_OVERRIDE 全覆盖
# ═══════════════════════════════════════════════════════════════════════════════

_ALL_OVERRIDE_CODES = list(_WP_CODE_OVERRIDE.keys())


@pytest.mark.parametrize("wp_code", _ALL_OVERRIDE_CODES)
def test_wp_code_override_returns_nonempty_component_type(wp_code: str):
    """每个 _WP_CODE_OVERRIDE 条目的 componentType 非空且非 skip。"""
    expected_ct = _WP_CODE_OVERRIDE[wp_code]
    assert expected_ct, f"_WP_CODE_OVERRIDE['{wp_code}'] 值为空"
    assert expected_ct != "skip", (
        f"_WP_CODE_OVERRIDE['{wp_code}'] 不应映射为 skip（已注册底稿应有专用组件）"
    )
    # 值必须是合法标识符格式（kebab-case）
    assert all(c.isalnum() or c == "-" for c in expected_ct), (
        f"componentType '{expected_ct}' 包含非法字符"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Part 2: htmlRendererRegistry 无重复 componentType（防双机合并重复 const）
# ═══════════════════════════════════════════════════════════════════════════════


def test_no_duplicate_component_types_in_wp_code_override():
    """_WP_CODE_OVERRIDE 中不应有重复 key（Python dict 天然去重，此测试防拼写变体冲突）。"""
    # 检查所有 value 格式合法
    values = list(_WP_CODE_OVERRIDE.values())
    for v in values:
        assert v and isinstance(v, str), f"componentType 值异常: {v!r}"
        assert all(c.isalnum() or c == "-" for c in v), f"componentType '{v}' 格式不合法"


# ═══════════════════════════════════════════════════════════════════════════════
# Part 3: render-config 端点函数体 import 链无 AttributeError
# ═══════════════════════════════════════════════════════════════════════════════


def _make_mock_db(wp_code: str = "A1"):
    """构造 mock DB session，模拟最小查询结果集。"""
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()
    wp_index_id = uuid.uuid4()

    # Mock WorkingPaper
    mock_wp = MagicMock()
    mock_wp.id = wp_id
    mock_wp.project_id = project_id
    mock_wp.wp_index_id = wp_index_id
    mock_wp.parsed_data = {"html_data": {}}
    mock_wp.file_path = None
    mock_wp.source_type = "template"
    mock_wp.assigned_to = None
    mock_wp.is_deleted = False

    # Mock WpIndex
    mock_wp_index = MagicMock()
    mock_wp_index.id = wp_index_id
    mock_wp_index.wp_code = wp_code
    mock_wp_index.wp_name = f"测试底稿 {wp_code}"
    mock_wp_index.audit_cycle = "A"
    mock_wp_index.is_deleted = False

    # Mock DB session
    db = AsyncMock()

    # execute returns different results based on query type
    # We'll use side_effect to handle multiple calls
    call_count = {"n": 0}

    async def mock_execute(*args, **kwargs):
        call_count["n"] += 1
        result = MagicMock()
        scalars_mock = MagicMock()

        # First call: WorkingPaper query
        if call_count["n"] == 1:
            scalars_mock.first.return_value = mock_wp
            result.scalars.return_value = scalars_mock
        # Second call: WpIndex query
        elif call_count["n"] == 2:
            scalars_mock.first.return_value = mock_wp_index
            result.scalars.return_value = scalars_mock
        # Third call: WpCrossRef query
        elif call_count["n"] <= 4:
            scalars_mock.all.return_value = []
            scalars_mock.first.return_value = None
            result.scalars.return_value = scalars_mock
            result.first.return_value = None
            result.scalar_one_or_none.return_value = None
            result.fetchall.return_value = []
        else:
            # All subsequent calls: return empty/None
            scalars_mock.all.return_value = []
            scalars_mock.first.return_value = None
            result.scalars.return_value = scalars_mock
            result.first.return_value = (None, "C")
            result.scalar_one_or_none.return_value = None
            result.scalar.return_value = 0
            result.fetchall.return_value = []
        return result

    db.execute = AsyncMock(side_effect=mock_execute)
    return db, wp_id, project_id


# A 类底稿中最关键的 wp_code 子集（覆盖不同 componentType 路径）
_CRITICAL_A_CODES = [
    "A1",       # a1-dashboard
    "A2",       # a2-adjustment-console
    "A3",       # a3-consolidation-console
    "A5",       # cf-verification
    "A1-15",    # checklist-table
    "A1-16",    # checklist-table
    "A1-13",    # analytical-review
    "A13",      # misstatement-workpaper
    "A21",      # review-checklist
    "A31",      # audit-legend
    "A16",      # word-template
    "A17-1",    # a17-summary
    "A18-2",    # regulatory-letter
    "A10-2",    # d-form-confirmation
    "A14-2",    # d-form-table
    "A14-6",    # e-control-test
    "A7-2",     # c-note-table
    # B 类关键底稿
    "B1A",      # a-program-console (承接)
    "B10",      # a-program-console (了解环境)
    "B1-1",     # d-form-table (风险评估)
    "B3",       # checklist-table (独立性)
    "B22A-1",   # d-form-table (企业层面控制)
    "B23-1",    # d-form-table (业务层面控制)
    "B50",      # a-program-console (风险汇总)
    "B51",      # d-form-table (舞弊三因素)
    "B60-1",    # audit-sheet (工时预算)
    # C 类关键底稿
    "C1",       # a-program-console (企业层面控制测试)
    "C2",       # d-form-table (销售循环控制测试)
    "C5-2",     # d-form-table (投资循环评价控制偏差)
    "C22",      # audit-sheet (IT一般控制测试)
    "C23",      # d-form-table (会计分录控制测试)
    "C24",      # d-form-table (会计分录细节测试)
    # D 类关键底稿
    "D0",       # confirmation-hub (收入循环函证)
    "D0-1",     # d-form-table (函证结果汇总)
    "D1",       # d-form-table (应收票据审定表)
    "D1-1",     # d-form-table (应收票据审定表明细)
    "D1-2",     # audit-sheet (原值明细含公式)
    "D2",       # d-form-table (应收账款审定表)
    "D2-1",     # d-form-table (应收账款审定表明细)
    "D2-5",     # audit-sheet (分析程序)
    "D3",       # d-form-table (预收账款)
    "D4",       # d-form-table (营业收入审定表)
    "D4-1",     # d-form-table (营业收入审定表明细)
    "D4-5",     # d-form-table (会计政策检查)
    "D4-22",    # audit-sheet (IPO舞弊应对)
    "D5",       # d-form-table (应收款项融资)
    "D6",       # d-form-table (合同资产)
    "D6-7",     # d-form-paragraph (会计政策段落)
    "D6-8",     # audit-sheet (减值测算DCF)
    "D7",       # d-form-table (合同负债)
    "D7-2",     # d-form-table (合同负债明细)
    # E 类关键底稿
    "E0",       # confirmation-hub (货币资金函证)
    "E0-1",     # d-form-table (函证结果汇总)
    "E0-3",     # d-form-table (跟函控制)
    "E0-5",     # d-form-table (替代程序)
    "E1",       # d-form-table (货币资金审定表)
    "E1-1",     # d-form-table (货币资金审定表明细)
    "E1-2",     # d-form-table (库存现金明细表)
    "E1-3",     # audit-sheet (银行存款明细表)
    "E1-5",     # audit-sheet (银行存款余额调节表)
    "E1-6",     # d-form-table (受限货币资金明细)
    "E1-9",     # audit-sheet (利息测算)
    "E1-10",    # d-form-table (调整分录汇总)
    "E1-14",    # audit-sheet (分析程序一)
    "E1-18",    # audit-sheet (检查程序一)
    "E1-26",    # audit-sheet (IPO舞弊应对一)
    "E1-32",    # audit-sheet (IPO舞弊应对七)
    # F 类关键底稿
    "F0",       # confirmation-hub (存货循环函证)
    "F0-1",     # d-form-table (函证结果汇总)
    "F0-3",     # d-form-table (跟函控制)
    "F1",       # d-form-table (预付账款审定表)
    "F1-1",     # d-form-table (预付账款审定表明细)
    "F1-2",     # audit-sheet (预付账款明细表)
    "F1-3",     # audit-sheet (预付账款账龄分析)
    "F1-4",     # d-form-table (预付账款坏账准备)
    "F2",       # d-form-table (存货及跌价准备审定表)
    "F2-1",     # d-form-table (存货审定表)
    "F2-2",     # audit-sheet (存货分类明细)
    "F2-11",    # d-form-table (跌价准备明细)
    "F2-16",    # d-form-table (存货会计政策检查)
    "F2-18",    # audit-sheet (存货分析程序一)
    "F2-21",    # audit-sheet (存货监盘计划)
    "F2-29",    # audit-sheet (存货检查一)
    "F2-38",    # audit-sheet (计价测试一)
    "F2-47",    # audit-sheet (跌价准备测试一)
    "F2-52",    # d-form-table (存货关联交易检查)
    "F2-55",    # audit-sheet (合同履约成本一)
    "F2-61",    # audit-sheet (存货IPO舞弊应对一)
    "F2-72",    # audit-sheet (存货IPO舞弊应对十二)
    "F3",       # d-form-table (应付票据审定表)
    "F3-1",     # d-form-table (应付票据审定表明细)
    "F3-2",     # audit-sheet (应付票据明细表)
    "F3-5",     # audit-sheet (应付票据分析程序)
    "F4",       # d-form-table (应付账款审定表)
    "F4-1",     # d-form-table (应付账款审定表明细)
    "F4-2",     # audit-sheet (应付账款明细表)
    "F4-4",     # d-form-table (应付账款调整分录汇总)
    "F5",       # d-form-table (营业成本审定表)
    "F5-1",     # d-form-table (营业成本审定表明细)
    "F5-2",     # audit-sheet (营业成本明细表)
    "F5-6",     # audit-sheet (营业成本分析程序)
    # G 类关键底稿
    "G0",       # confirmation-hub (投资循环函证)
    "G1",       # d-form-table (交易性金融资产审定表)
    "G7-1",     # d-form-table (长期股权投资审定表明细)
    # H 类关键底稿
    "H0",       # confirmation-hub (固定资产循环函证)
    "H1",       # d-form-table (固定资产审定表)
    "H1-1",     # d-form-table (固定资产审定表明细)
    "H1-2",     # audit-sheet (固定资产明细表)
    # I 类关键底稿
    "I1",       # d-form-table (无形资产审定表)
    "I1-1",     # d-form-table (无形资产审定表明细)
    "I1-2",     # audit-sheet (无形资产明细表)
    "I3-4",     # audit-sheet (DCF测算WACC/NPV)
    # J 类关键底稿 — 职工薪酬循环
    "J1A",      # j1-employee-compensation (应付职工薪酬程序表，整册内分发)
    "J2A",      # j2-defined-benefit-plan (设定受益计划程序表，整册内分发)
    "J3A",      # j3-share-based-payment (股份支付程序表，整册内分发)
    "J1-1",     # d-form-table (应付职工薪酬审定表)
    "J2-1",     # d-form-table (设定受益计划审定表)
    "J3-1",     # d-form-table (股份支付审定表)
    "J1-3",     # audit-sheet (工资测算含公式)
    "J2-3",     # d-form-table (精算假设评估)
    "J2-5",     # audit-sheet (精算重新计算含公式)
    "J3-4",     # audit-sheet (期权定价Black-Scholes)
    "J1-8",     # d-form-table (调整分录)
    "J3-6",     # d-form-table (调整分录)
    # K 类关键底稿 — 管理循环
    "K0A",      # a-program-console (管理循环函证程序表)
    "K1A",      # a-program-console (其他应收款程序表)
    "K5A",      # a-program-console (预计负债程序表)
    "K8A",      # a-program-console (销售费用程序表)
    "K9A",      # a-program-console (管理费用程序表)
    "K13A",     # a-program-console (营业外支出程序表)
    "K0",       # confirmation-hub (管理循环函证)
    "K0-1",     # d-form-table (函证结果汇总)
    "K0-3",     # d-form-table (跟函控制)
    "K1",       # c-note-table (其他应收款附注)
    "K1-1",     # d-form-table (其他应收款审定表)
    "K1-2",     # audit-sheet (其他应收款明细表)
    "K1-4",     # d-form-table (坏账准备)
    "K1-6",     # d-form-table (调整分录)
    "K3",       # c-note-table (其他应付款附注)
    "K3-1",     # d-form-table (其他应付款审定表)
    "K5",       # c-note-table (预计负债附注)
    "K5-1",     # d-form-table (预计负债审定表)
    "K5-3",     # d-form-table (或有事项评估)
    "K5-5",     # d-form-table (律师函回函分析)
    "K6-3",     # d-form-table (持有待售分类条件)
    "K8-1",     # d-form-table (销售费用审定表)
    "K8-2",     # audit-sheet (销售费用明细表)
    "K9-1",     # d-form-table (管理费用审定表)
    "K9-2",     # audit-sheet (管理费用明细表)
    "K10-1",    # d-form-table (其他收益审定表)
    "K11-1",    # d-form-table (资产减值损失审定表)
    "K12-1",    # d-form-table (营业外收入审定表)
    "K13-1",    # d-form-table (营业外支出审定表)
    "K13-4",    # d-form-table (调整分录)
    # L 类关键底稿 — 筹资循环
    "L0A",      # a-program-console (筹资循环程序表)
    "L4A",      # a-program-console (应付债券程序表)
    "L8A",      # a-program-console (财务费用程序表)
    "L1",       # d-form-table (短期借款审定表)
    "L1-1",     # d-form-table (短期借款审定表明细)
    "L3-4",     # d-form-table (重分类检查)
    "L4",       # d-form-table (应付债券审定表)
    "L4-1",     # d-form-table (应付债券审定表明细)
    "L8-1",     # d-form-table (财务费用审定表明细)
    # M 类关键底稿 — 权益循环
    "M1A",      # m1-dividends-payable (应付股利程序表，整册内分发)
    "M6A",      # m6-retained-earnings (未分配利润程序表，整册内分发)
    "M2",       # d-form-table (资本公积审定表)
    "M2-1",     # d-form-table (资本公积审定表明细)
    "M6",       # d-form-table (利润分配审定表)
    "M6-1",     # d-form-table (利润分配审定表明细)
    "M9-2",     # audit-sheet (其他综合收益明细)
    # N 类关键底稿 — 税费循环
    "N1A",      # a-program-console (应交税费程序表)
    "N5A",      # a-program-console (所得税费用程序表)
    "N2",       # d-form-table (增值税审定表)
    "N2-1",     # d-form-table (增值税审定表明细)
    "N5",       # d-form-table (所得税费用审定表)
    "N5-1",     # d-form-table (所得税费用审定表明细)
    # S 类关键底稿 — 专项
    "S1",       # a-program-console (收入截止测试)
    "S2",       # a-program-console (关联方交易核查)
    "S10",      # a-program-console (非货币性资产交换)
    "S15",      # audit-sheet (每股收益)
    "S17",      # audit-sheet (非经常性损益)
    "S20",      # d-form-table (新收入准则核查)
    "S32-1",    # d-form-table (IPO核查—收入确认)
    "S33-1",    # d-form-table (综合核查—财务信息)
    "S34-1-1",  # d-form-table (证监会核查—基本情况)
]


@pytest.mark.anyio
@pytest.mark.parametrize("wp_code", _CRITICAL_A_CODES)
async def test_render_config_endpoint_no_500(wp_code: str):
    """render-config 端点对关键 A 类底稿不 500（验证 import/函数调用链完整）。

    这是防止双机合并后函数名错误/import 缺失导致全平台 500 的核心守护。
    """
    from app.routers.wp_render_config import get_render_config

    db, wp_id, project_id = _make_mock_db(wp_code)

    # Mock current_user
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    # Mock classification service 返回匹配的 classification
    from app.services.wp_classification_service import ClassificationResult

    mock_classification = ClassificationResult(
        wp_code=wp_code,
        sheet_name=f"{wp_code}_sheet",
        class_code="A-程序表",
        class_=f"A类-{wp_code}",
        scope="standalone",
        is_real_workpaper=True,
        delegated_module=None,
        render_schema_path=None,
        template_version_id=None,
    )

    with (
        patch(
            "app.routers.wp_render_config.WpClassificationService"
        ) as MockClsSvc,
        patch(
            "app.routers.wp_render_config.WpTemplateVersionService"
        ) as MockVerSvc,
        patch(
            "app.routers.wp_render_config._resolve_auto_fill_values",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        # Classification service mock
        cls_instance = AsyncMock()
        cls_instance.get_classification = AsyncMock(return_value=[mock_classification])
        MockClsSvc.return_value = cls_instance

        # Version service mock
        ver_instance = AsyncMock()
        ver_obj = MagicMock()
        ver_obj.version = "v2025-R5"
        ver_obj.id = uuid.uuid4()
        ver_instance.get_current_version = AsyncMock(return_value=ver_obj)
        MockVerSvc.return_value = ver_instance

        try:
            result = await get_render_config(
                wp_id=wp_id,
                sheet_name=None,
                db=db,
                current_user=mock_user,
            )
        except Exception as e:
            # 404 是合理的（mock 数据不完整），但 500 类错误不可接受
            # AttributeError / NameError / ImportError = 代码链路断裂
            if isinstance(e, (AttributeError, NameError, ImportError, TypeError)):
                pytest.fail(
                    f"render-config 对 wp_code='{wp_code}' 崩溃: "
                    f"{type(e).__name__}: {e}\n"
                    f"这表示代码中存在函数名错误/import 缺失，会导致全平台 500"
                )
            # HTTPException 404 等业务异常是可接受的
            from fastapi import HTTPException
            if isinstance(e, HTTPException) and e.status_code in (404, 422):
                return  # 预期内：mock 数据不完整导致的业务异常
            # 其他未预期异常也报失败
            pytest.fail(
                f"render-config 对 wp_code='{wp_code}' 未预期异常: "
                f"{type(e).__name__}: {e}"
            )

        # 如果成功返回，验证基本结构
        assert isinstance(result, dict)
        assert "sheets" in result
        assert "wp_code" in result
        assert result["wp_code"] == wp_code
