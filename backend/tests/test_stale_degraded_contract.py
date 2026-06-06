"""Stale degraded 记录器测试 — 验证非静默性。"""
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
