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
async def test_record_stage_manual_logs_phase_without_context_manager():
    """旁路登记：pipeline 有自己的 _perf 字典，record_stage_manual 允许事后转移。"""
    profiler = StagedProfiler()
    profiler.record_stage_manual("parse_write_streaming", duration_s=1.5, rows=12_000)
    profiler.record_stage_manual("rebuild_aux_summary", duration_s=0.4, rows=0, wal_bytes=2_048)
    report = profiler.to_dict()
    assert set(report["stages"].keys()) == {"parse_write_streaming", "rebuild_aux_summary"}
    assert report["stages"]["parse_write_streaming"]["rows"] == 12_000
    assert report["stages"]["parse_write_streaming"]["rows_per_sec"] == pytest.approx(8_000.0)
    assert report["stages"]["rebuild_aux_summary"]["rows_per_sec"] is None
    assert report["stages"]["rebuild_aux_summary"]["wal_bytes"] == 2_048
    assert report["total_rows"] == 12_000
    assert report["total_duration_s"] == pytest.approx(1.9)


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


# ---------------------------------------------------------------------------
# pipeline._build_profiler_report：把 _perf 字典翻译成 profiler report
# ---------------------------------------------------------------------------


def test_build_profiler_report_translates_perf_dict_into_stage_records():
    """`execute_pipeline` 结尾调用的翻译函数：接入 `_perf` 字典但不重测时间。"""
    from app.services.ledger_import.profiler_report import _build_profiler_report

    perf = {
        "start": 100.0,
        "detect_identify_done": 100.5,
        "create_staged_done": 101.0,
        "parse_write_streaming_done": 103.5,
        "activation_gate_done": 103.7,
        "activate_dataset_done": 104.0,
        "rebuild_aux_summary_done": 104.4,
    }
    report = _build_profiler_report(perf, 100.0, staging_rows=12_000, rebuild_rows=50)
    assert report is not None
    stages = report["stages"]
    assert set(stages.keys()) == set(perf.keys())
    # 关键：parse_write_streaming 的 rows / rate 对得上
    assert stages["parse_write_streaming_done"]["rows"] == 12_000
    assert stages["parse_write_streaming_done"]["rows_per_sec"] == pytest.approx(12_000 / 2.5)
    # rebuild 是 balance+aux_balance 的汇总行数
    assert stages["rebuild_aux_summary_done"]["rows"] == 50
    # 非业务 phase 不带 rows
    for phase in ("start", "detect_identify_done", "create_staged_done",
                  "activation_gate_done", "activate_dataset_done"):
        assert stages[phase]["rows"] == 0
        assert stages[phase]["rows_per_sec"] is None
    assert report["total_rows"] == 12_050
    assert report["total_duration_s"] == pytest.approx(4.4)


def test_build_profiler_report_empty_perf_returns_none():
    """_perf 空的时候（pipeline 还没 _mark 到任何 phase）返回 None。"""
    from app.services.ledger_import.profiler_report import _build_profiler_report

    assert _build_profiler_report({}, 123.0) is None
