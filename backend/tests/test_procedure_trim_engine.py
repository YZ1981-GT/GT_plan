"""ProcedureTrimEngine 服务单元测试

Sprint 1 Task 1.5:
- trim 方法：状态变更 + trimming_metadata 写入
- revert 方法：状态恢复 + metadata 清除
- get_summary：按循环/按理由分组 + 警告阈值
- get_history：筛选条件 + 排序
- 边界条件：空 row_ids / reason_text 恰好 5 字符 / 裁剪率恰好 50%

Requirements: 2.4, 3.3, 4.1, 7.1, 7.2
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.procedure_trim_engine import (
    ProcedureTrimEngine,
    TrimReasonCode,
    CycleTrimStat,
    ReasonTrimStat,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_wp(parsed_data: dict | None = None):
    """Create a mock WorkingPaper."""
    wp = MagicMock()
    wp.id = uuid.uuid4()
    wp.project_id = uuid.uuid4()
    wp.parsed_data = parsed_data or {}
    return wp


def _make_db(wp=None):
    """Create a mock async db session."""
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = wp
    db.execute = AsyncMock(return_value=result_mock)
    db.flush = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# trim: 状态变更 + trimming_metadata 写入
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trim_updates_status_to_not_applicable():
    """trim 应将 status 从 pending 更新为 not_applicable。"""
    wp = _make_wp({
        "procedure_status": {
            "d4a": {"R1": {"status": "pending"}, "R2": {"status": "filled"}}
        }
    })
    db = _make_db(wp)
    engine = ProcedureTrimEngine()

    with patch("app.services.procedure_trim_engine.audit_logger") as mock_logger:
        mock_logger.log_action = AsyncMock()
        result = await engine.trim(
            db=db, wp_id=wp.id, sheet_key="d4a",
            row_ids=["R1", "R2"],
            reason_code=TrimReasonCode.CONTROL_TEST_EFFECTIVE,
            reason_text=None,
            user_id=uuid.uuid4(), project_id=wp.project_id,
        )

    assert result.succeeded == ["R1", "R2"]
    assert wp.parsed_data["procedure_status"]["d4a"]["R1"]["status"] == "not_applicable"
    assert wp.parsed_data["procedure_status"]["d4a"]["R2"]["status"] == "not_applicable"


@pytest.mark.asyncio
async def test_trim_writes_trimming_metadata():
    """trim 应写入 trimming_metadata 包含 reason_code/trimmed_by/trimmed_at。"""
    wp = _make_wp({
        "procedure_status": {"e1a": {"R5": {"status": "pending"}}}
    })
    db = _make_db(wp)
    engine = ProcedureTrimEngine()
    user_id = uuid.uuid4()

    with patch("app.services.procedure_trim_engine.audit_logger") as mock_logger:
        mock_logger.log_action = AsyncMock()
        await engine.trim(
            db=db, wp_id=wp.id, sheet_key="e1a",
            row_ids=["R5"],
            reason_code=TrimReasonCode.OTHER,
            reason_text="客户无海外业务，外币程序不适用",
            user_id=user_id, project_id=wp.project_id,
        )

    meta = wp.parsed_data["trimming_metadata"]["e1a"]["R5"]
    assert meta["reason_code"] == "other"
    assert meta["reason_text"] == "客户无海外业务，外币程序不适用"
    assert meta["trimmed_by"] == str(user_id)
    assert meta["trimmed_at"] is not None
    assert meta["batch_id"] is None  # single row → no batch_id


@pytest.mark.asyncio
async def test_trim_batch_sets_batch_id():
    """批量 trim（>1 row）应设置 batch_id。"""
    wp = _make_wp({
        "procedure_status": {
            "e1a": {"R1": {"status": "pending"}, "R2": {"status": "pending"}}
        }
    })
    db = _make_db(wp)
    engine = ProcedureTrimEngine()

    with patch("app.services.procedure_trim_engine.audit_logger") as mock_logger:
        mock_logger.log_action = AsyncMock()
        await engine.trim(
            db=db, wp_id=wp.id, sheet_key="e1a",
            row_ids=["R1", "R2"],
            reason_code=TrimReasonCode.NO_RELATED_BUSINESS,
            reason_text=None,
            user_id=uuid.uuid4(), project_id=wp.project_id,
        )

    meta_r1 = wp.parsed_data["trimming_metadata"]["e1a"]["R1"]
    meta_r2 = wp.parsed_data["trimming_metadata"]["e1a"]["R2"]
    assert meta_r1["batch_id"] is not None
    assert meta_r1["batch_id"] == meta_r2["batch_id"]


# ---------------------------------------------------------------------------
# revert: 状态恢复 + metadata 清除
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revert_restores_status_to_pending():
    """revert 应将 status 从 not_applicable 恢复为 pending。"""
    wp = _make_wp({
        "procedure_status": {"e1a": {"R1": {"status": "not_applicable"}}},
        "trimming_metadata": {"e1a": {"R1": {"reason_code": "no_related_business"}}},
    })
    db = _make_db(wp)
    engine = ProcedureTrimEngine()

    with patch("app.services.procedure_trim_engine.audit_logger") as mock_logger:
        mock_logger.log_action = AsyncMock()
        result = await engine.revert(
            db=db, wp_id=wp.id, sheet_key="e1a",
            row_ids=["R1"],
            user_id=uuid.uuid4(), project_id=wp.project_id,
        )

    assert result.succeeded == ["R1"]
    assert wp.parsed_data["procedure_status"]["e1a"]["R1"]["status"] == "pending"


@pytest.mark.asyncio
async def test_revert_clears_trimming_metadata():
    """revert 应清除对应行的 trimming_metadata。"""
    wp = _make_wp({
        "procedure_status": {"e1a": {"R1": {"status": "not_applicable"}}},
        "trimming_metadata": {
            "e1a": {
                "R1": {"reason_code": "other", "reason_text": "test reason text"},
            }
        },
    })
    db = _make_db(wp)
    engine = ProcedureTrimEngine()

    with patch("app.services.procedure_trim_engine.audit_logger") as mock_logger:
        mock_logger.log_action = AsyncMock()
        await engine.revert(
            db=db, wp_id=wp.id, sheet_key="e1a",
            row_ids=["R1"],
            user_id=uuid.uuid4(), project_id=wp.project_id,
        )

    assert "R1" not in wp.parsed_data["trimming_metadata"]["e1a"]


# ---------------------------------------------------------------------------
# get_summary: 按循环/按理由分组 + 警告阈值
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_summary_groups_by_cycle():
    """get_summary 应按 sheet_key（循环）分组统计。"""
    wp = _make_wp({
        "procedure_status": {
            "e1a": {
                "R1": {"status": "not_applicable"},
                "R2": {"status": "pending"},
            },
            "d4a": {
                "R1": {"status": "not_applicable"},
                "R2": {"status": "not_applicable"},
                "R3": {"status": "pending"},
            },
        },
        "trimming_metadata": {
            "e1a": {"R1": {"reason_code": "no_related_business"}},
            "d4a": {
                "R1": {"reason_code": "low_risk_assessment"},
                "R2": {"reason_code": "low_risk_assessment"},
            },
        },
    })
    db = _make_db(wp)
    engine = ProcedureTrimEngine()

    summary = await engine.get_summary(db=db, wp_id=wp.id)

    assert summary.total_procedures == 5
    assert summary.trimmed_count == 3
    # Find cycle stats
    e1a_stat = next(c for c in summary.by_cycle if c.cycle == "e1a")
    d4a_stat = next(c for c in summary.by_cycle if c.cycle == "d4a")
    assert e1a_stat.total == 2
    assert e1a_stat.trimmed == 1
    assert e1a_stat.rate == 50.0
    assert e1a_stat.warning is False  # exactly 50% → no warning
    assert d4a_stat.total == 3
    assert d4a_stat.trimmed == 2
    assert d4a_stat.rate == pytest.approx(66.67, abs=0.01)
    assert d4a_stat.warning is True  # > 50%


@pytest.mark.asyncio
async def test_get_summary_groups_by_reason():
    """get_summary 应按 reason_code 分组统计。"""
    wp = _make_wp({
        "procedure_status": {
            "e1a": {
                "R1": {"status": "not_applicable"},
                "R2": {"status": "not_applicable"},
                "R3": {"status": "not_applicable"},
            },
        },
        "trimming_metadata": {
            "e1a": {
                "R1": {"reason_code": "no_related_business"},
                "R2": {"reason_code": "no_related_business"},
                "R3": {"reason_code": "other"},
            },
        },
    })
    db = _make_db(wp)
    engine = ProcedureTrimEngine()

    summary = await engine.get_summary(db=db, wp_id=wp.id)

    assert len(summary.by_reason) == 2
    # Sorted by count descending
    assert summary.by_reason[0].reason_code == "no_related_business"
    assert summary.by_reason[0].count == 2
    assert summary.by_reason[1].reason_code == "other"
    assert summary.by_reason[1].count == 1


@pytest.mark.asyncio
async def test_get_summary_warning_threshold():
    """裁剪率 > 50% 应出现在 warnings，≤ 50% 不应出现。"""
    wp = _make_wp({
        "procedure_status": {
            "high": {
                "R1": {"status": "not_applicable"},
                "R2": {"status": "not_applicable"},
                "R3": {"status": "pending"},
            },
            "low": {
                "R1": {"status": "not_applicable"},
                "R2": {"status": "pending"},
                "R3": {"status": "pending"},
                "R4": {"status": "pending"},
            },
        },
        "trimming_metadata": {
            "high": {
                "R1": {"reason_code": "no_related_business"},
                "R2": {"reason_code": "no_related_business"},
            },
            "low": {
                "R1": {"reason_code": "no_related_business"},
            },
        },
    })
    db = _make_db(wp)
    engine = ProcedureTrimEngine()

    summary = await engine.get_summary(db=db, wp_id=wp.id)

    # high: 2/3 = 66.7% > 50% → warning
    # low: 1/4 = 25% ≤ 50% → no warning
    assert len(summary.warnings) == 1
    assert "high" in summary.warnings[0]


# ---------------------------------------------------------------------------
# get_history: 筛选条件 + 排序
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_history_returns_entries():
    """get_history 应返回审计日志条目列表。"""
    from datetime import datetime, timezone

    wp = _make_wp()
    db = AsyncMock()

    # Mock the SQL query result
    mock_rows = [
        (
            uuid.uuid4(),
            "workpaper.procedure_trimmed",
            uuid.uuid4(),
            {"action_type": "trim", "row_ids": ["R1", "R2"], "reason_code": "no_related_business"},
            datetime(2026, 5, 20, 10, 0, 0, tzinfo=timezone.utc),
        ),
        (
            uuid.uuid4(),
            "workpaper.procedure_trim_reverted",
            uuid.uuid4(),
            {"action_type": "revert", "row_ids": ["R1"]},
            datetime(2026, 5, 20, 9, 0, 0, tzinfo=timezone.utc),
        ),
    ]
    result_mock = MagicMock()
    result_mock.fetchall.return_value = mock_rows
    db.execute = AsyncMock(return_value=result_mock)

    engine = ProcedureTrimEngine()
    entries = await engine.get_history(db=db, wp_id=wp.id, filters=None)

    assert len(entries) == 2
    assert entries[0].action == "trim"
    assert entries[0].row_ids == ["R1", "R2"]
    assert entries[1].action == "revert"
    assert entries[1].row_ids == ["R1"]


@pytest.mark.asyncio
async def test_get_history_handles_db_error():
    """get_history 数据库查询失败时返回空列表。"""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=Exception("DB error"))

    engine = ProcedureTrimEngine()
    entries = await engine.get_history(db=db, wp_id=uuid.uuid4(), filters=None)

    assert entries == []


# ---------------------------------------------------------------------------
# 边界条件
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trim_empty_row_ids():
    """空 row_ids 应返回空结果（不报错）。"""
    wp = _make_wp({
        "procedure_status": {"e1a": {"R1": {"status": "pending"}}}
    })
    db = _make_db(wp)
    engine = ProcedureTrimEngine()

    with patch("app.services.procedure_trim_engine.audit_logger") as mock_logger:
        mock_logger.log_action = AsyncMock()
        result = await engine.trim(
            db=db, wp_id=wp.id, sheet_key="e1a",
            row_ids=[],
            reason_code=TrimReasonCode.NO_RELATED_BUSINESS,
            reason_text=None,
            user_id=uuid.uuid4(), project_id=wp.project_id,
        )

    assert result.ok is True
    assert result.succeeded == []
    assert result.skipped == []
    assert result.failed == []


@pytest.mark.asyncio
async def test_trim_reason_text_exactly_5_chars():
    """reason_text 恰好 5 字符应被接受。"""
    wp = _make_wp({
        "procedure_status": {"e1a": {"R1": {"status": "pending"}}}
    })
    db = _make_db(wp)
    engine = ProcedureTrimEngine()

    with patch("app.services.procedure_trim_engine.audit_logger") as mock_logger:
        mock_logger.log_action = AsyncMock()
        result = await engine.trim(
            db=db, wp_id=wp.id, sheet_key="e1a",
            row_ids=["R1"],
            reason_code=TrimReasonCode.OTHER,
            reason_text="12345",  # exactly 5 chars
            user_id=uuid.uuid4(), project_id=wp.project_id,
        )

    assert result.ok is True
    assert result.succeeded == ["R1"]
    meta = wp.parsed_data["trimming_metadata"]["e1a"]["R1"]
    assert meta["reason_text"] == "12345"


@pytest.mark.asyncio
async def test_get_summary_exactly_50_percent_no_warning():
    """裁剪率恰好 50% 不应触发警告。"""
    wp = _make_wp({
        "procedure_status": {
            "e1a": {
                "R1": {"status": "not_applicable"},
                "R2": {"status": "pending"},
            },
        },
        "trimming_metadata": {
            "e1a": {"R1": {"reason_code": "no_related_business"}},
        },
    })
    db = _make_db(wp)
    engine = ProcedureTrimEngine()

    summary = await engine.get_summary(db=db, wp_id=wp.id)

    # 1/2 = 50% → exactly 50% → no warning
    assert summary.trim_rate == 50.0
    assert len(summary.warnings) == 0


@pytest.mark.asyncio
async def test_get_summary_empty_workpaper():
    """空底稿（无 procedure_status）应返回零值。"""
    wp = _make_wp({})
    db = _make_db(wp)
    engine = ProcedureTrimEngine()

    summary = await engine.get_summary(db=db, wp_id=wp.id)

    assert summary.total_procedures == 0
    assert summary.trimmed_count == 0
    assert summary.trim_rate == 0.0
    assert summary.by_cycle == []
    assert summary.by_reason == []
    assert summary.warnings == []


@pytest.mark.asyncio
async def test_trim_preserves_existing_row_data():
    """trim 应保留行的其他字段（description, category 等），仅更新 status。"""
    wp = _make_wp({
        "procedure_status": {
            "e1a": {
                "R1": {
                    "status": "pending",
                    "description": "检查银行对账单",
                    "category": "常规★",
                    "assertions": ["存在"],
                },
            }
        }
    })
    db = _make_db(wp)
    engine = ProcedureTrimEngine()

    with patch("app.services.procedure_trim_engine.audit_logger") as mock_logger:
        mock_logger.log_action = AsyncMock()
        await engine.trim(
            db=db, wp_id=wp.id, sheet_key="e1a",
            row_ids=["R1"],
            reason_code=TrimReasonCode.NO_RELATED_BUSINESS,
            reason_text=None,
            user_id=uuid.uuid4(), project_id=wp.project_id,
        )

    row = wp.parsed_data["procedure_status"]["e1a"]["R1"]
    assert row["status"] == "not_applicable"
    assert row["description"] == "检查银行对账单"
    assert row["category"] == "常规★"
    assert row["assertions"] == ["存在"]


@pytest.mark.asyncio
async def test_revert_preserves_existing_row_data():
    """revert 应保留行的其他字段，仅恢复 status 为 pending。"""
    wp = _make_wp({
        "procedure_status": {
            "e1a": {
                "R1": {
                    "status": "not_applicable",
                    "description": "检查银行对账单",
                    "category": "常规★",
                },
            }
        },
        "trimming_metadata": {
            "e1a": {"R1": {"reason_code": "no_related_business"}},
        },
    })
    db = _make_db(wp)
    engine = ProcedureTrimEngine()

    with patch("app.services.procedure_trim_engine.audit_logger") as mock_logger:
        mock_logger.log_action = AsyncMock()
        await engine.revert(
            db=db, wp_id=wp.id, sheet_key="e1a",
            row_ids=["R1"],
            user_id=uuid.uuid4(), project_id=wp.project_id,
        )

    row = wp.parsed_data["procedure_status"]["e1a"]["R1"]
    assert row["status"] == "pending"
    assert row["description"] == "检查银行对账单"
    assert row["category"] == "常规★"
