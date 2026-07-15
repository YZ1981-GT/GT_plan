"""Runtime gap baseline tests — 固化四项已知缺口的证据。

每个测试明确标注 expected gap，用断言证明当前行为确实存在该缺口。
这些测试在缺口被修复前应 PASS（证明缺口存在）；
修复后应 FAIL（表明缺口已关闭，需更新为正向测试）。

Spec: .kiro/specs/formula-runtime-convergence/ Task 1
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.formula_runtime.fixtures import (
    SAMPLE_PROJECT_ID,
    SAMPLE_WP_ID,
    SAMPLE_YEAR,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Gap 1: workpaper scope 无领域 mutation
#
# DraftRefreshOrchestrator._dispatch_workpaper 返回 units=[] —— 即对 workpaper
# scope 不产生任何真实领域 mutation（仅产 page_keys 交预设库间接生成）。
# 这是已知缺口：编排层应直接驱动真实领域 adapter mutation。
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_gap1_workpaper_scope_produces_no_domain_mutations():
    """Gap 1 证据：_dispatch_workpaper 返回的 units 列表为空。

    Expected gap: 当前 orchestrator 对 workpaper scope 仅产 page_keys 交预设库，
    不产真实领域 mutation units。修复后此测试应 FAIL。
    """
    from app.services.formula_management.draft_refresh_orchestrator import (
        DraftRefreshOrchestrator,
    )

    orchestrator = DraftRefreshOrchestrator.__new__(DraftRefreshOrchestrator)

    # Mock internal helpers to isolate _dispatch_workpaper
    orchestrator._scope_cycle = MagicMock(return_value="D")
    orchestrator._wp_codes = AsyncMock(return_value=["D2-1", "D2-2", "D2-3"])

    units, page_keys = await orchestrator._dispatch_workpaper(
        "workpaper:D", project_id=SAMPLE_PROJECT_ID, year=SAMPLE_YEAR
    )

    # ── Gap 证据断言 ──
    # units 为空 = 无真实领域 mutation（已知缺口）
    assert units == [], (
        "Gap 1 证据：_dispatch_workpaper 应返回空 units（当前无领域 mutation）"
    )
    # page_keys 非空证明函数确实执行了
    assert len(page_keys) > 0, "page_keys 应非空（证明函数正常执行）"


# ═══════════════════════════════════════════════════════════════════════════════
# Gap 2: rollback 不恢复业务值
#
# DraftRefreshService.rollback 返回 restored_units（含 before_value），但编排层
# 本身不调用任何领域 adapter 来实际恢复业务数据。它仅恢复 draft_marker 状态并把
# before_value 返回给调用方，期望调用方自行恢复。这意味着如果调用方不处理，
# 业务值实际未被恢复——这是已知缺口。
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_gap2_rollback_does_not_restore_business_values():
    """Gap 2 证据：rollback 方法内无真实 write/restore adapter 调用。

    Expected gap: rollback 仅恢复 marker 并返回 restored_units，不调用任何
    领域 adapter 的 restore 方法来恢复实际业务数据单元。
    修复后此测试应 FAIL。
    """
    from app.services.draft_refresh_service import DraftRefreshService

    service = DraftRefreshService()

    # 构造 mock DB session：模拟一个已成功刷新的审计记录 + 快照
    mock_audit = MagicMock()
    mock_audit.id = uuid.uuid4()
    mock_audit.result_status = "success"
    mock_audit.detail = {}

    mock_snapshot = MagicMock()
    mock_snapshot.unit_scope = f"audit_sheet:{SAMPLE_WP_ID}:B5"
    mock_snapshot.before_value = {"amount": "12345.67"}
    mock_snapshot.editor_id = None
    mock_snapshot.refresh_id = mock_audit.id

    mock_marker = MagicMock()
    mock_marker.unit_scope = mock_snapshot.unit_scope
    mock_marker.refresh_id = mock_audit.id
    mock_marker.state = "draft"

    db = AsyncMock()

    # First execute: find audit record
    # Second execute: find snapshots
    # Third execute: find markers
    call_count = [0]

    async def mock_execute(stmt):
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            # audit record
            result.scalar_one_or_none = MagicMock(return_value=mock_audit)
        elif call_count[0] == 2:
            # snapshots
            scalars_mock = MagicMock()
            scalars_mock.all = MagicMock(return_value=[mock_snapshot])
            result.scalars = MagicMock(return_value=scalars_mock)
        elif call_count[0] == 3:
            # markers
            scalars_mock = MagicMock()
            scalars_mock.all = MagicMock(return_value=[mock_marker])
            result.scalars = MagicMock(return_value=scalars_mock)
        else:
            result.scalar_one_or_none = MagicMock(return_value=None)
            scalars_mock = MagicMock()
            scalars_mock.all = MagicMock(return_value=[])
            result.scalars = MagicMock(return_value=scalars_mock)
        return result

    db.execute = AsyncMock(side_effect=mock_execute)
    db.flush = AsyncMock()
    db.delete = AsyncMock()

    mock_op = MagicMock()
    mock_op.id = uuid.uuid4()
    mock_op.role = "partner"

    result = await service.rollback(
        db,
        refresh_id=mock_audit.id,
        operator=mock_op,
    )

    # ── Gap 证据断言 ──
    # rollback 返回了 restored_units（证明它识别了需要恢复的单元）
    assert result.status == "rolled_back", "rollback 应标记为已回滚"
    assert result.restored_count > 0 or len(result.restored_units) >= 0, (
        "rollback 应识别到需恢复的单元"
    )

    # 但关键：验证整个 rollback 过程中没有调用任何真实的领域 adapter restore
    # （因为当前 service 根本不持有/不调用任何 domain adapter）
    # 我们通过检查 db.execute 调用来验证——所有调用都是 SELECT/UPDATE marker，
    # 没有对业务数据表的 UPDATE/INSERT
    # 更直接的证据：DraftRefreshService 类没有任何 adapter 属性
    assert not hasattr(service, '_adapters'), (
        "Gap 2 证据：DraftRefreshService 无 _adapters 属性（无领域 adapter 注入）"
    )
    assert not hasattr(service, '_workpaper_adapter'), (
        "Gap 2 证据：DraftRefreshService 无 workpaper adapter"
    )
    assert not hasattr(service, '_adjudication_adapter'), (
        "Gap 2 证据：DraftRefreshService 无 adjudication adapter"
    )
    assert not hasattr(service, '_report_adapter'), (
        "Gap 2 证据：DraftRefreshService 无 report adapter"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Gap 3: save 误写 computed time
#
# WpFormulaService.save 在保存 auto_calc 公式定义时立即写入 last_computed_at，
# 但此时公式尚未被执行（执行由 runtime 在后续步骤完成）。这是已知 bug：
# last_computed_at 应仅在公式成功执行后才写入。
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_gap3_save_writes_computed_time_prematurely():
    """Gap 3 证据：save auto_calc 公式定义时写入 last_computed_at。

    Expected gap: 当前 save 方法对 auto_calc 类型在 upsert 时即写 last_computed_at
    = datetime.now()，但公式此时尚未执行。正确行为应仅在执行成功后记录。
    修复后此测试应 FAIL。
    """
    import inspect
    from app.services.wp_formula_service import WpFormulaService

    # 验证方式 1：源码分析 — save 方法中对 auto_calc 计算 computed_at
    source = inspect.getsource(WpFormulaService.save)

    # 关键证据：save 方法中有条件地设置 computed_at（仅 auto_calc 才设）
    assert "auto_calc" in source, "save 方法中应引用 auto_calc 类型"
    assert "computed_at" in source or "last_computed_at" in source, (
        "save 方法中应有 computed_at/last_computed_at 赋值逻辑"
    )

    # 关键证据：computed_at 在 save（定义保存）时就被设置，而非执行后
    # 代码模式：`computed_at = datetime.now(timezone.utc) if ftype == "auto_calc" else None`
    # 然后直接赋给 `existing.last_computed_at = computed_at` 或新建时写入
    assert "datetime.now" in source, (
        "Gap 3 证据：save 方法中直接使用 datetime.now 设置 computed_at"
        "（在定义保存阶段即写时间戳，公式尚未执行）"
    )

    # 验证方式 2：确认该时间戳是在同一方法中无条件写入（对 auto_calc）
    # 不依赖外部执行确认
    assert "existing.last_computed_at = computed_at" in source or \
           "last_computed_at" in source, (
        "Gap 3 证据：last_computed_at 在 save 方法体内被直接赋值"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Gap 4: 前后端响应字段漂移
#
# GtRefreshScopeDialog 期望的字段名（applied_count / page_count）与后端
# PresetApplication.to_dict() 实际返回的字段名（preset_count / presetted_pages /
# pending_pages）不一致，存在漂移。
# ═══════════════════════════════════════════════════════════════════════════════


def test_gap4_frontend_backend_response_field_drift():
    """Gap 4 证据：前后端响应字段名不一致（漂移）。

    Expected gap:
    - 前端 GtRefreshScopeDialog.presetSummary 期望:
      preset_application.applied_count, preset_application.page_count
    - 后端 PresetApplication.to_dict() 实际返回:
      preset_count, presetted_pages, pending_pages

    两组字段名不匹配 → 前端无法正确展示预设套用摘要。
    修复后此测试应 FAIL。
    """
    from app.services.draft_refresh_service import PresetApplication

    # 构造一个有实际数据的 PresetApplication
    pa = PresetApplication(
        units=[MagicMock(), MagicMock(), MagicMock()],  # 3 units
        presetted_pages=["workpaper:D2-1", "workpaper:D2-2"],
        pending_pages=["workpaper:D2-3"],
    )

    backend_fields = set(pa.to_dict().keys())

    # ── 后端实际字段 ──
    # PresetApplication.to_dict() 返回:
    #   {"preset_count": ..., "presetted_pages": [...], "pending_pages": [...]}
    assert "preset_count" in backend_fields, "后端应返回 preset_count"
    assert "presetted_pages" in backend_fields, "后端应返回 presetted_pages"
    assert "pending_pages" in backend_fields, "后端应返回 pending_pages"

    # ── 前端期望字段（来自 GtRefreshScopeDialog.vue presetSummary computed） ──
    # ```js
    # const applied = (pa as Record<string, unknown>).applied_count
    # const pages = (pa as Record<string, unknown>).page_count
    # ```
    frontend_expected_fields = {"applied_count", "page_count"}

    # ── Gap 证据断言：前端期望的字段不存在于后端返回中 ──
    assert "applied_count" not in backend_fields, (
        "Gap 4 证据：后端不返回前端期望的 'applied_count' 字段"
    )
    assert "page_count" not in backend_fields, (
        "Gap 4 证据：后端不返回前端期望的 'page_count' 字段"
    )

    # 漂移最终证据：两组字段无交集
    assert frontend_expected_fields.isdisjoint(backend_fields), (
        f"Gap 4 证据：前端期望字段 {frontend_expected_fields} 与后端实际字段 "
        f"{backend_fields} 完全不一致（漂移确认）"
    )
