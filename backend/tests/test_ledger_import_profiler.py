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


# ---------------------------------------------------------------------------
# C4：WAL 探针接线（pipeline 在写阶段自己的 session 边界内读 LSN）
# ---------------------------------------------------------------------------


def test_build_profiler_report_attaches_write_stage_wal_bytes_only():
    """WAL 增量只贴到写阶段那一条；其他阶段保持 None（没有各自探针）。"""
    from app.services.ledger_import.profiler_report import _build_profiler_report

    perf = {
        "start": 100.0,
        "create_staged_done": 101.0,
        "parse_write_streaming_done": 103.5,
        "rebuild_aux_summary_done": 104.4,
    }
    report = _build_profiler_report(
        perf, 100.0, staging_rows=1_000, rebuild_rows=10,
        write_stage_wal_bytes=8_388_608,
    )
    assert report is not None
    stages = report["stages"]
    assert stages["parse_write_streaming_done"]["wal_bytes"] == 8_388_608
    for phase in ("start", "create_staged_done", "rebuild_aux_summary_done"):
        assert stages[phase]["wal_bytes"] is None, (
            f"{phase} 没有自己的 session 探针，wal_bytes 必须是 None 而不是 0"
        )


def test_build_profiler_report_keeps_none_when_wal_probe_unavailable():
    """探针读不到（非 PG / 无权限）时必须保持 None —— 读不到 ≠ 0 字节。"""
    from app.services.ledger_import.profiler_report import _build_profiler_report

    perf = {"start": 100.0, "parse_write_streaming_done": 102.0}
    report = _build_profiler_report(
        perf, 100.0, staging_rows=500, write_stage_wal_bytes=None,
    )
    assert report is not None
    assert report["stages"]["parse_write_streaming_done"]["wal_bytes"] is None


def test_record_wal_bytes_updates_existing_stage_and_ignores_unknown():
    """record_wal_bytes：已知 stage 补记，未知 stage 是 no-op（不凭空建记录）。"""
    from app.services.ledger_import.profiler import StagedProfiler

    profiler = StagedProfiler()
    profiler.record_stage_manual("write", duration_s=1.0, rows=100)
    assert profiler.stages["write"].wal_bytes is None

    profiler.record_wal_bytes("write", 4_096)
    assert profiler.stages["write"].wal_bytes == 4_096
    # 其余字段不被破坏
    assert profiler.stages["write"].rows == 100
    assert profiler.stages["write"].rows_per_sec == pytest.approx(100.0)

    profiler.record_wal_bytes("absent_stage", 99)
    assert "absent_stage" not in profiler.stages


@pytest.mark.asyncio
async def test_read_wal_lsn_and_diff_degrade_to_none_without_pg():
    """公开探针在非 PG / 无 session 时返回 None，不抛异常、不写 0。"""
    from app.services.ledger_import.profiler import read_wal_lsn, wal_bytes_between

    assert await read_wal_lsn(None) is None
    assert await wal_bytes_between(None, "0/1", "0/2") is None
    # 缺任一端同样 None
    assert await wal_bytes_between(None, None, "0/2") is None


def test_pipeline_source_reads_lsn_inside_write_stage_session_boundary():
    """接线判据：pipeline 必须在写阶段前后各取一次 LSN，且探针自己管 session 边界。

    这条用源码文本断言而不是跑真 pipeline —— 真 pipeline 需要完整项目数据与
    真实 PG；而「探针是否接在正确位置」正是过去漏掉的形态（骨架写好了但零调用）。

    实现形态：探针细节抽到 `profiler.WalStageProbe`（pipeline 在行数白名单上，
    不能塞逻辑），pipeline 只负责 `start()` / `stop()` 与传参。因此判据改为：
    ① import 了 WalStageProbe ② start/stop 都真的调用 ③ 值传进报告。
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "app" / "services" / "ledger_import" / "pipeline.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    # 1. 必须 import 探针
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("profiler")
        for alias in node.names
    }
    assert "WalStageProbe" in imported, (
        f"pipeline 没有 import WalStageProbe（实际 import: {imported}）"
    )

    # 2. start 与 stop 都必须真的调用
    def _attr_calls(root: ast.AST, attr: str) -> list[int]:
        return [
            node.lineno
            for node in ast.walk(root)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == attr
        ]

    starts = _attr_calls(tree, "start")
    stops = _attr_calls(tree, "stop")
    assert starts, "pipeline 没有调用探针 start()"
    assert stops, "pipeline 没有调用探针 stop()"

    # 3. start 必须在 stop 之前（顺序反了等于没测）
    assert min(starts) < min(stops), (
        f"探针 stop 在 start 之前（start@{starts} / stop@{stops}）"
    )


def test_wal_stage_probe_owns_session_boundary():
    """探针自己开 session 读 LSN —— 这是「阶段内读」的唯一实现方式。

    若把 LSN 读取挪到 pipeline 末尾（事务已提交），读到的位置与本次写入无关；
    这条钉住「探针内部用 session_factory 新开 session」。
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "app" / "services" / "ledger_import" / "profiler.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    probe = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "WalStageProbe"
    )
    methods = {node.name: node for node in probe.body if isinstance(node, ast.AsyncFunctionDef)}
    assert "start" in methods and "stop" in methods, "探针缺 start/stop"

    for name in ("start", "stop"):
        body = ast.dump(methods[name])
        assert "_session_factory" in body, (
            f"WalStageProbe.{name} 没有用 session_factory 开新 session ⇒ "
            "LSN 会读在错误的连接上"
        )
        assert "_get_wal_lsn" in body or "_wal_diff" in body, (
            f"WalStageProbe.{name} 没有真正读 LSN"
        )

    # wal_bytes 必须在未 stop 时返回 None（不能把「还没测」写成 0）
    prop = next(
        node for node in probe.body
        if isinstance(node, ast.FunctionDef) and node.name == "wal_bytes"
    )
    assert "None" in ast.dump(prop), "wal_bytes 未 stop 时没有返回 None 的分支"


def test_pipeline_passes_wal_into_profiler_report_call():
    """接线判据：pipeline 调 _build_profiler_report 时必须传 write_stage_wal_bytes。

    漏传会让 profiler_report 里 WAL 恒 None（静默退化成「探针没接」）。
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "app" / "services" / "ledger_import" / "pipeline.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    report_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_build_profiler_report"
    ]
    assert report_calls, "pipeline 没有调用 _build_profiler_report"
    keywords = {kw.arg for kw in report_calls[0].keywords}
    assert "write_stage_wal_bytes" in keywords, (
        "_build_profiler_report 调用漏了 write_stage_wal_bytes ⇒ WAL 恒 None"
    )


def test_import_job_runner_persists_profiler_report():
    """消费方判据：runner 必须把 profiler_report 落进 result_summary。

    历史上「骨架写好了但零消费方」正是 C4 的登记勘误；这条钉住落库点。
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "app" / "services" / "import_job_runner.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    # 找 result_payload = {...} 字典字面量，断言有 "profiler" 键且取值来自
    # result.profiler_report
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "result_payload" for t in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        keys = [
            k.value for k in node.value.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        ]
        if "profiler" not in keys:
            continue
        index = keys.index("profiler")
        value = node.value.values[index]
        found = (
            isinstance(value, ast.Attribute)
            and value.attr == "profiler_report"
        )
    assert found, (
        "result_payload 里没有 profiler: result.profiler_report ⇒ 报告从未落库"
    )
