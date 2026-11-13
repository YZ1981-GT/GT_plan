"""性能测试选择器的共享库硬闸门（spec platform-heavy-jobs-and-capacity-closure 任务 0.3 / R1.5）。"""

from __future__ import annotations

from tests._perf_gate import perf_write_gate_error

_WRITE_PERF = ["tests/procedure_delegation/test_procedure_performance.py::test_x"]
_PG = "postgresql+asyncpg://u:p@host:5432/gt_perf_blast"
_SHARED = "postgresql+asyncpg://u:p@host:5432/audit_platform"


def test_no_write_perf_selected_needs_no_gate():
    # 只跑纯内存 perf（无 pg_only），或根本没选 perf：闸门不触发。
    assert perf_write_gate_error(_PG, {"GT_PERF_DISPOSABLE_DB": "YES"}, []) is None


def test_sqlite_env_skips_gate_because_pg_only_is_skipped():
    # 非 PG 环境下 pg_only 用例会被整批跳过，不会真写库 ⇒ 不需要闸门。
    assert perf_write_gate_error("sqlite+aiosqlite:///:memory:", {}, _WRITE_PERF) is None


def test_write_perf_on_pg_without_declaration_is_hard_error():
    error = perf_write_gate_error(_PG, {}, _WRITE_PERF)
    assert error is not None
    assert "GT_PERF_DISPOSABLE_DB=YES" in error
    assert "test_procedure_performance" in error


def test_write_perf_against_shared_database_is_refused_even_when_declared():
    error = perf_write_gate_error(_SHARED, {"GT_PERF_DISPOSABLE_DB": "YES"}, _WRITE_PERF)
    assert error is not None
    assert "audit_platform" in error


def test_write_perf_passes_on_declared_disposable_pg():
    assert perf_write_gate_error(_PG, {"GT_PERF_DISPOSABLE_DB": "1"}, _WRITE_PERF) is None
