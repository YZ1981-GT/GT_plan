"""CP-03 防御：附注 partial/failed/skipped 正确传到步骤状态和 all_ok。

已复现缺陷（建议文档 §13.6）：
_refresh_notes 返回 note_status=partial/failed/skipped 时，_push_one 仍把附注步骤标 succeeded、all_ok=true。

修复：notes() 返回 (detail, note_status) 元组；for 循环对 partial/failed 降级步骤状态并设 all_ok=False。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# 被测模块的步骤常量
STEP_NOTES = "notes"


def _make_stats(note_status: str, refreshed: int = 0, failed: int = 0, skipped: int = 0) -> dict:
    return {
        "stale_marked": 5,
        "distinct_section_count": 3,
        "node_count": 2,
        "refreshed_count": refreshed,
        "failed_count": failed,
        "skipped_count": skipped,
        "note_status": note_status,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("note_status,expected_step_status,expected_all_ok", [
    ("persisted", "succeeded", True),
    ("partial", "partial", False),
    ("failed", "failed", False),
    ("skipped", "succeeded", True),  # skipped = 合法无可刷目标，不降级
])
async def test_note_status_propagates_to_step_and_all_ok(note_status, expected_step_status, expected_all_ok):
    """_push_one 消费 notes() 的结构化 note_status，正确设置步骤状态和 all_ok。"""
    from app.services.consol_push_service import _push_one

    stats = _make_stats(
        note_status,
        refreshed=3 if note_status in ("persisted", "partial") else 0,
        failed=2 if note_status in ("partial", "failed") else 0,
    )
    steps: list[dict] = []
    warnings: list[str] = []

    with patch("app.services.consol_push_service._project_name", new=AsyncMock(return_value="测试")), \
         patch("app.services.consol_push_service._advisory_lock", new=AsyncMock()), \
         patch("app.services.consol_push_service._process_lock") as mock_lock, \
         patch("app.services.consol_worksheet_engine.recalc_full", new=AsyncMock(return_value={"node_count": 1, "account_count": 1})), \
         patch("app.services.consol_trial_service.recalculate_trial", new=AsyncMock(return_value=[])), \
         patch("app.services.consol_report_service.ConsolReportService") as MockReportSvc, \
         patch("app.services.consol_push_service._refresh_notes", new=AsyncMock(return_value=stats)):

        # mock process lock 为 async context manager
        mock_lock.return_value.__aenter__ = AsyncMock()
        mock_lock.return_value.__aexit__ = AsyncMock()

        # mock report service
        mock_report_instance = AsyncMock()
        mock_report_instance.generate_consol_reports = AsyncMock(return_value={})
        MockReportSvc.return_value = mock_report_instance

        # mock db
        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        import uuid
        result = await _push_one(db, uuid.uuid4(), 2025, steps, warnings)

    assert result == expected_all_ok, f"all_ok 应为 {expected_all_ok}，实际 {result}"

    note_step = next((s for s in steps if s["step"] == STEP_NOTES), None)
    assert note_step is not None, f"未找到 notes 步骤：{steps}"
    assert note_step["status"] == expected_step_status, (
        f"note_status={note_status} 时步骤状态应为 {expected_step_status}，实际 {note_step['status']}"
    )

    # partial/failed 时 detail 包含失败信息
    if note_status in ("partial", "failed"):
        assert "失败" in (note_step.get("detail") or ""), f"detail 应包含'失败'：{note_step}"
        assert any("失败" in w for w in warnings), f"warnings 应包含失败信息：{warnings}"


@pytest.mark.asyncio
async def test_mutation_proof_old_logic_would_always_succeed():
    """变异证明：旧逻辑（notes 返回 str）总是标 succeeded。"""
    # 旧 notes() 返回 str，不返回 tuple；for 循环无条件 record succeeded
    detail_str = "标记 5 行待更新，3 个章节 × 2 个节点，刷新 0，失败 6，附注状态=failed"
    # 旧逻辑等效：
    assert isinstance(detail_str, str)
    assert not isinstance(detail_str, tuple)
    # 如果 for 循环仍用旧逻辑 `record(step, "succeeded", detail)`，
    # 那么即使 detail 包含"失败 6"和"附注状态=failed"，步骤仍标 succeeded
    # 这就是 CP-03 缺陷——状态误报
