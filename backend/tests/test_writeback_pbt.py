"""Property tests P29 + P30 — 回写乐观锁 stale 拒绝 / 回写事务原子性
（advanced-query-module Task 15.6 / 15.7）

- Feature: advanced-query-module, Property 29: 回写乐观锁 stale 拒绝
  Validates: Requirements 14.7
- Feature: advanced-query-module, Property 30: 回写事务原子性
  Validates: Requirements 3.6, 9.4, 14.8

harness 复用：
- P29 mirror test_writeback_confirmation.py（_StubAddressing + monkeypatch
  _read_workpaper_value + WritebackConfirmationGate）。
- P30 mirror test_snapshot_writer.py（AsyncMock db + _resolve_found_fake +
  在 11 步中随机某步注入异常，断言全回滚：exception 抛出且从不 commit、
  失败于写前的步骤连 UPDATE 都不触达）。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.custom_query.addressing_service import (
    AddressingService,
    ResolvedTarget,
)
from app.services.custom_query.snapshot_writer import (
    AuditWriteFailed,
    SnapshotWriter,
    WritebackConflict,
    WritebackPermissionDenied,
    WritebackResolveUnavailable,
    WritebackTargetUnresolvable,
)
from app.services.custom_query.writeback_preview import (
    ERR_CODE_WRITEBACK_CONFLICT,
    WritebackConfirmationConflict,
    WritebackConfirmationGate,
    WritebackPreviewService,
    WritebackTarget,
    _values_equal,
)


# ═══════════════════════════════════════════════════════════════════════════
# Property 29: 回写乐观锁 stale 拒绝（Task 15.6, R14.7）
# ═══════════════════════════════════════════════════════════════════════════


class _StubAddressing(AddressingService):
    """raw → addr_id 直映射，避免触达 ACNR/DB。"""

    async def resolve_target(self, raw, *, project_id=None, db=None, timeout_s=5.0):
        return ResolvedTarget(raw=raw, found=True, addr_id=f"ADDR/{raw}")


_DB_SENTINEL = object()  # 非 None → 进入 workpaper 只读复核分支

# 值池：混合数值 / 字符串 / 空，覆盖 _values_equal 的数值等价与空值归一分支
_VALUE_POOL = st.sampled_from([10, "10", 0, "x", "abc", 3.5, None, "", "10.0"])

# 保证与 old 不同的新值哨兵（使预览 item.changed=True，进入确认流程）
_NEW_SENTINEL = "__NEW_VALUE_SENTINEL__"


async def _build_wp_preview(old_value, *, window_s=600.0):
    """构造含单个 workpaper 目标的非空预览（old→new 恒变化）。"""
    svc = WritebackPreviewService(addressing=_StubAddressing())
    target = WritebackTarget(
        new_value=_NEW_SENTINEL,
        old_value=old_value,
        module="workpaper",
        wp_id="wp1",
        sheet_name="S",
        cell_ref="E100",
        raw="wp1/S/E100",
    )
    return await svc.generate(
        None, [target], project_id="p1", confirmation_window_s=window_s
    )


@pytest.mark.asyncio
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(old_value=_VALUE_POOL, current_value=_VALUE_POOL, expired=st.booleans())
async def test_p29_optimistic_lock_stale_rejection(
    old_value, current_value, expired, monkeypatch
):
    """Feature: advanced-query-module, Property 29: 回写乐观锁 stale 拒绝

    Validates: Requirements 14.7

    预览之后确认之前：预览过期 或 目标 cell 当前旧值与预览时不一致 → 拒绝回写、
    数据不变、提示重新预览；仅当窗口内且旧值一致时通过。
    """
    # monkeypatch 确认门只读复核读取的「当前旧值」
    async def _fake_read(db, wp_id, sheet_name, cell_ref):
        return current_value

    monkeypatch.setattr(
        WritebackPreviewService,
        "_read_workpaper_value",
        staticmethod(_fake_read),
    )

    preview = await _build_wp_preview(old_value, window_s=600.0)
    assert preview.enter_confirmation is True  # old→new 恒变化，非空预览

    now = datetime.now(timezone.utc)
    if expired:
        # 推到窗口外（601s 前 > 600s 窗口）
        preview.created_at = now - timedelta(seconds=601)

    gate = WritebackConfirmationGate()

    values_match = _values_equal(current_value, old_value)

    if expired:
        # 过期优先于 stale 判定（门内先查窗口）
        with pytest.raises(WritebackConfirmationConflict) as exc:
            await gate.validate(_DB_SENTINEL, preview, now=now)
        assert exc.value.reason == "expired"
        assert exc.value.error_code == ERR_CODE_WRITEBACK_CONFLICT
    elif values_match:
        # 窗口内 + 旧值一致 → 通过，数据不变（门不写库）
        check = await gate.validate(_DB_SENTINEL, preview, now=now)
        assert check.ok is True
        assert check.verified_items == 1
    else:
        # 窗口内 + 旧值 stale → 拒绝，提示重新预览
        with pytest.raises(WritebackConfirmationConflict) as exc:
            await gate.validate(_DB_SENTINEL, preview, now=now)
        assert exc.value.reason == "stale"
        assert exc.value.error_code == ERR_CODE_WRITEBACK_CONFLICT
        assert len(exc.value.stale_items) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Property 30: 回写事务原子性（Task 15.7, R3.6 / R9.4 / R14.8）
# ═══════════════════════════════════════════════════════════════════════════

_RESOLVE_TARGET_PATH = (
    "app.services.custom_query.addressing_service.addressing_service.resolve_target"
)
_AUDIT_LOGGER_PATH = "app.services.audit_logger_enhanced.audit_logger"

# 归属校验用的两个合法 UUID（project_mismatch 场景）
_PID_A = "11111111-1111-1111-1111-111111111111"
_PID_B = "22222222-2222-2222-2222-222222222222"

# 可注入失败的步骤 → 期望异常类型（含跨 sheet 归属校验 / 数据步 / 审计写入失败）
_FATAL_STEPS = {
    "select_not_found": ValueError,               # step1 记录不存在
    "project_mismatch": WritebackPermissionDenied,  # step2 归属校验失败（R9.4）
    "optimistic_conflict": WritebackConflict,     # step3 乐观锁
    "resolve_unresolvable": WritebackTargetUnresolvable,  # step4 addr_id 无法解析（R3.4）
    "resolve_unavailable": WritebackResolveUnavailable,   # step4 resolve 不可用（R3.5）
    "update_fails": RuntimeError,                 # step6 数据写入失败
    "persist_fails": RuntimeError,                # step9 回写身份落库失败
    "audit_fails": AuditWriteFailed,              # step10 审计失败（R14.8 无审计不回写）
}

# 失败于写入前（step≤4）→ UPDATE 从不触达
_PRE_WRITE_STEPS = {
    "select_not_found",
    "project_mismatch",
    "optimistic_conflict",
    "resolve_unresolvable",
    "resolve_unavailable",
}


def _make_user():
    u = MagicMock()
    u.id = "user-001"
    u.username = "tester"
    u.role = "admin"
    return u


def _snapshot_with_cell(sheet_name, row, col, value):
    return {
        "univer_snapshot": {
            "sheets": {
                "0": {
                    "name": sheet_name,
                    "cellData": {str(row): {str(col): {"v": value}}},
                }
            }
        }
    }


@pytest.mark.asyncio
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(inject=st.sampled_from(["none", *_FATAL_STEPS.keys()]))
async def test_p30_writeback_transaction_atomicity(inject, monkeypatch):
    """Feature: advanced-query-module, Property 30: 回写事务原子性

    Validates: Requirements 3.6, 9.4, 14.8

    在 11 步中随机某步注入异常（含归属校验 / 数据步 / 审计写入失败）→ 事务不 commit
    （由 caller 回滚，无部分写入）；失败于写前的步骤连 UPDATE 都不触达（数据不变）。
    无注入 → 成功且同样不在 writer 内 commit。
    """
    now = datetime.now(timezone.utc)
    sheet_name = "S"
    parsed_data = _snapshot_with_cell(sheet_name, 0, 0, "old")

    # 归属：project_mismatch 场景 row/passed 不同；其余 passed=None（跳过 step2）
    if inject == "project_mismatch":
        passed_project_id = _PID_A
        row_project_id = _PID_B
    else:
        passed_project_id = None
        row_project_id = _PID_A

    # 乐观锁：optimistic_conflict 场景 opened_at < updated_at
    if inject == "optimistic_conflict":
        opened_at = now - timedelta(seconds=30)
        row_updated_at = now
    else:
        opened_at = now
        row_updated_at = now

    update_called = {"flag": False}

    async def mock_execute(stmt, params=None):
        # text() 语句带 .text；ORM select（step8）不带 → 返回空对象跳过 orchestrator
        if hasattr(stmt, "text"):
            s = str(stmt.text)
            if "SELECT" in s and "FOR UPDATE" in s:
                res = MagicMock()
                if inject == "select_not_found":
                    res.first.return_value = None
                else:
                    res.first.return_value = (
                        row_updated_at, parsed_data, "D2", "", row_project_id,
                    )
                return res
            if "UPDATE working_paper" in s:
                update_called["flag"] = True
                if inject == "update_fails":
                    raise RuntimeError("injected update failure")
                return MagicMock()
            return MagicMock()
        # ORM select（step8 orchestrator）→ 无对象，跳过 after_save（非致命路径）
        res = MagicMock()
        res.scalar_one_or_none.return_value = None
        return res

    mock_db = AsyncMock()
    mock_db.execute = mock_execute
    mock_db.add = MagicMock()
    if inject == "persist_fails":
        mock_db.flush = AsyncMock(side_effect=RuntimeError("injected persist failure"))
    else:
        mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    # resolve 桩（step4）
    if inject == "resolve_unresolvable":
        async def _fake_resolve(raw, *, project_id=None, db=None, timeout_s=5.0):
            return ResolvedTarget(raw=raw, found=False, error="unresolvable")
    elif inject == "resolve_unavailable":
        async def _fake_resolve(raw, *, project_id=None, db=None, timeout_s=5.0):
            return ResolvedTarget(raw=raw, found=False, error="resolve_unavailable")
    else:
        async def _fake_resolve(raw, *, project_id=None, db=None, timeout_s=5.0):
            return ResolvedTarget(
                raw=raw, found=True, addr_id="D2/D2-2/A1",
                jump_route="/wp/x", entry_type="cell",
            )

    monkeypatch.setattr(_RESOLVE_TARGET_PATH, _fake_resolve)

    # 审计桩（step10）
    async def _audit_ok(**kwargs):
        return kwargs

    async def _audit_boom(**kwargs):
        raise RuntimeError("audit queue down")

    monkeypatch.setattr(
        f"{_AUDIT_LOGGER_PATH}.log_action",
        _audit_boom if inject == "audit_fails" else _audit_ok,
    )

    writer = SnapshotWriter()

    async def _run():
        return await writer.write_cell(
            db=mock_db,
            user=_make_user(),
            wp_id="wp-001",
            sheet_name=sheet_name,
            cell_ref="A1",
            new_value="new",
            opened_at=opened_at,
            module="workpaper",
            project_id=passed_project_id,
        )

    if inject == "none":
        result = await _run()
        assert result["success"] is True
        # writer 从不 commit（原子性由 caller 事务/回滚保证）
        mock_db.commit.assert_not_called()
    else:
        with pytest.raises(_FATAL_STEPS[inject]):
            await _run()
        # 任一步失败 → 从不 commit，无部分写入落库
        mock_db.commit.assert_not_called()
        # 失败于写前的步骤 → UPDATE 从不触达（数据不变）
        if inject in _PRE_WRITE_STEPS:
            assert update_called["flag"] is False
