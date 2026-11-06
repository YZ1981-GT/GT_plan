"""C4：Ledger 导入分阶段 profiler 骨架测试（SQLite / 无 db）。

只验证 **profiler 本体**的行为 —— rows/s、duration、error 捕获、to_dict
形状、累计 total_rows / total_duration_s。WAL 字节在 PG 上的真实采集属于
专用环境验收（见 spec tasks.md C4 `[ ]*`），这里不伪造 PG 结果，只断言非 PG
环境下 wal_bytes 是 None。
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.ledger_import.profiler import StagedProfiler


@pytest.mark.asyncio
async def test_profiler_records_stage_duration_and_rows_per_sec():
    profiler = StagedProfiler()
    async with profiler.stage("staging_write", db=None, rows=100):
        await asyncio.sleep(0.01)
    report = profiler.to_dict()
    stage = report["stages"]["staging_write"]
    assert stage["rows"] == 100
    assert stage["duration_s"] > 0
    assert stage["rows_per_sec"] is not None
    assert stage["rows_per_sec"] == pytest.approx(100 / stage["duration_s"])
    assert stage["wal_bytes"] is None  # 无 db / 非 PG 环境
    assert stage["error"] is None
    assert report["total_rows"] == 100
    assert report["total_duration_s"] == pytest.approx(stage["duration_s"])


@pytest.mark.asyncio
async def test_profiler_captures_error_and_still_measures_stage():
    profiler = StagedProfiler()
    with pytest.raises(RuntimeError, match="boom"):
        async with profiler.stage("copy_insert", db=None, rows=0):
            raise RuntimeError("boom")
    stage = profiler.to_dict()["stages"]["copy_insert"]
    assert stage["error"] == "RuntimeError: boom"
    assert stage["duration_s"] > 0
    assert stage["rows"] == 0
    assert stage["rows_per_sec"] is None  # rows=0 时不计算 rate


@pytest.mark.asyncio
async def test_profiler_record_rows_accumulates_and_recomputes_rate():
    profiler = StagedProfiler()
    async with profiler.stage("activation", db=None, rows=0):
        await asyncio.sleep(0.01)
    # 对真实 COPY 返回的行数做 stage 结束后的补记
    profiler.record_rows("activation", 50)
    stage = profiler.to_dict()["stages"]["activation"]
    assert stage["rows"] == 50
    assert stage["rows_per_sec"] is not None
    assert stage["rows_per_sec"] == pytest.approx(50 / stage["duration_s"])


@pytest.mark.asyncio
async def test_profiler_record_rows_ignores_unknown_stage():
    profiler = StagedProfiler()
    # stage 还没登记 → record_rows 是 no-op，不抛异常
    profiler.record_rows("not_yet_started", 99)
    assert profiler.to_dict()["stages"] == {}
    assert profiler.total_rows == 0


@pytest.mark.asyncio
async def test_profiler_total_duration_accumulates_across_stages():
    profiler = StagedProfiler()
    async with profiler.stage("stage_a", db=None, rows=10):
        await asyncio.sleep(0.005)
    async with profiler.stage("stage_b", db=None, rows=20):
        await asyncio.sleep(0.005)
    report = profiler.to_dict()
    assert report["total_rows"] == 30
    assert set(report["stages"].keys()) == {"stage_a", "stage_b"}
    assert report["total_duration_s"] == pytest.approx(
        report["stages"]["stage_a"]["duration_s"] + report["stages"]["stage_b"]["duration_s"]
    )


@pytest.mark.asyncio
async def test_profiler_stages_property_is_isolated_copy():
    """stages 只读视图不得允许外部改写内部状态。"""
    profiler = StagedProfiler()
    async with profiler.stage("stage_a", db=None, rows=10):
        await asyncio.sleep(0.001)
    snapshot = profiler.stages
    snapshot["stage_a"] = None  # 污染副本不应影响内部
    assert profiler.stages["stage_a"] is not None
    assert profiler.stages["stage_a"].rows == 10


@pytest.mark.asyncio
async def test_profiler_to_dict_fields_are_json_serializable():
    """to_dict 结果必须能被 json.dumps 处理（供 progress / metadata 使用）。"""
    import json

    profiler = StagedProfiler()
    async with profiler.stage("export", db=None, rows=42):
        await asyncio.sleep(0.001)
    dumped = json.dumps(profiler.to_dict())
    loaded = json.loads(dumped)
    assert loaded["stages"]["export"]["rows"] == 42
    assert loaded["total_rows"] == 42
