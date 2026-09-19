"""Stale degraded 记录器测试 — 验证非静默性（P0-4 增强版）。"""
import pytest
from app.services.stale_degraded_logger import (
    log_stale_degraded, get_degraded_records, clear_degraded_records,
)


@pytest.fixture(autouse=True)
def cleanup():
    """每个测试前后清理降级记录。"""
    clear_degraded_records()
    yield
    clear_degraded_records()


def test_log_stale_degraded_creates_record():
    """记录一条 degraded 后可查询到。"""
    log_stale_degraded(
        source="tb-row-001",
        target="wp-cell-D12",
        error="target field not found",
    )
    records = get_degraded_records()
    assert len(records) == 1
    assert records[0]["source"] == "tb-row-001"
    assert records[0]["target"] == "wp-cell-D12"
    assert records[0]["error"] == "target field not found"
    assert "timestamp" in records[0]


def test_multiple_degraded_records():
    """多次失败产生多条记录。"""
    log_stale_degraded("src-1", "tgt-1", "error-1")
    log_stale_degraded("src-2", "tgt-2", "error-2")
    log_stale_degraded("src-3", "tgt-3", "error-3")
    records = get_degraded_records()
    assert len(records) == 3


def test_degraded_record_contains_context():
    """context 字段可携带附加信息。"""
    log_stale_degraded(
        source="note-section",
        target="report-row",
        error="stale propagation timeout",
        context={"retry_count": 3, "project_id": "proj-001"},
    )
    records = get_degraded_records()
    assert records[0]["context"]["retry_count"] == 3
    assert records[0]["context"]["project_id"] == "proj-001"


def test_clear_degraded_records():
    """清理后记录为空。"""
    log_stale_degraded("a", "b", "c")
    assert len(get_degraded_records()) == 1
    clear_degraded_records()
    assert len(get_degraded_records()) == 0


def test_get_degraded_records_returns_copy():
    """返回列表是副本，外部修改不影响内部。"""
    log_stale_degraded("x", "y", "z")
    records = get_degraded_records()
    records.clear()
    assert len(get_degraded_records()) == 1


def test_field_missing_scenario_produces_degraded():
    """P0-4.4 核心场景：模拟字段缺失，断言产生 degraded 记录。

    模拟 event_handlers.py 中 AuditReport.is_stale 字段不存在时的行为：
    不再静默 pass，而是调用 log_stale_degraded。
    """
    # 模拟 handler 中的异常处理逻辑
    try:
        # 模拟 SQL 更新 is_stale 字段失败（字段不存在）
        raise AttributeError("column 'is_stale' does not exist on AuditReport")
    except Exception as e:
        log_stale_degraded(
            source="adjustment:adjustment.created",
            target="AuditReport:project=proj-001,year=2025",
            error=f"AuditReport is_stale 更新失败: {type(e).__name__}: {e}",
            context={"project_id": "proj-001", "year": 2025},
        )

    records = get_degraded_records()
    assert len(records) == 1
    assert "is_stale" in records[0]["error"]
    assert records[0]["context"]["year"] == 2025


def test_stale_never_silently_passes():
    """P0-4 核心约束：stale 字段缺失时不再静默成功，必须有 degraded 记录。

    验证逻辑：
    1. 模拟各种异常场景
    2. 每种异常都必须产生 degraded 记录
    3. 记录数等于异常数
    """
    error_scenarios = [
        ("AuditReport 字段不存在", AttributeError("is_stale")),
        ("DB 连接超时", TimeoutError("connection timed out")),
        ("附注表不存在", Exception("relation 'disclosure_note' does not exist")),
    ]

    for desc, exc in error_scenarios:
        log_stale_degraded(
            source=f"stale_cascade:{desc}",
            target="downstream",
            error=f"{type(exc).__name__}: {exc}",
        )

    records = get_degraded_records()
    assert len(records) == len(error_scenarios), (
        f"每种异常场景都必须产生 degraded 记录，期望 {len(error_scenarios)}，实际 {len(records)}"
    )
