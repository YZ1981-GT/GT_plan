"""R3 关键 verdict 的磁盘变异证明。

变异只在子进程回归期间存在，finally 按字节恢复，避免把变异态留在工作树。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_NOTES = _BACKEND / "app" / "services" / "consol_push_notes.py"
_PUSH = _BACKEND / "app" / "services" / "consol_push_service.py"


def _assert_mutation_is_red(
    path: Path,
    old: bytes,
    new: bytes,
    label: str,
    test_path: str,
) -> None:
    original = path.read_bytes()
    needle = old
    replacement = new
    if needle not in original and b"\r\n" in original:
        needle = old.replace(b"\n", b"\r\n")
        replacement = new.replace(b"\n", b"\r\n")
    assert needle in original, f"{label} 变异靶点不存在，不能把本轮算作 RED"
    mutated = original.replace(needle, replacement, 1)
    assert mutated != original
    path.write_bytes(mutated)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_path, "-p", "no:playwright", "-q"],
            cwd=_BACKEND,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        assert result.returncode != 0, f"{label} 变异存活：\n{(result.stdout + result.stderr)[-4000:]}"
    finally:
        path.write_bytes(original)
        assert path.read_bytes() == original, f"{label} 变异恢复后字节不一致"


def test_context_failed_mutation_is_red():
    _assert_mutation_is_red(
        _NOTES,
        b'if reason == "context_failed":\n            return "failed", detail',
        b'if reason == "context_failed":\n            return "skipped", detail',
        "context_failed 改回 skipped",
        "tests/test_consol_push_cp03_note_status.py",
    )


def test_skipped_step_mutation_is_red():
    _assert_mutation_is_red(
        _PUSH,
        b'record(step, "skipped", detail)',
        b'record(step, "succeeded", detail)',
        "skipped 改回 succeeded",
        "tests/test_consol_push_cp03_note_status.py",
    )



def test_elimination_enqueue_failure_without_record_is_red():
    _handler = _BACKEND / "app" / "services" / "consol_elimination_recalc_handler.py"
    old = (
        b'from app.services.consol_push_failure_record import record_consol_push_failure\n'
        b'\n'
        b'        await record_consol_push_failure(\n'
        b'            project_id,\n'
        b'            int(year),\n'
        b'            trigger=trigger,\n'
        b'            reason=f"\xe5\x90\x88\xe5\xb9\xb6\xe9\x87\x8d\xe7\xae\x97\xe4\xba\x8b\xe4\xbb\xb6\xe6\x8a\x95\xe9\x80\x92\xe5\xa4\xb1\xe8\xb4\xa5\xef\xbc\x9a{err}",\n'
        b'            source_id=str(source_id) if "source_id" in locals() else None,\n'
        b'        )\n'
    )
    _assert_mutation_is_red(
        _handler,
        old,
        b"pass\n",
        "处理器失败路径删除 failed 运行记录",
        "tests/test_consol_elimination_recalc_failure.py",
    )



def test_review_route_swallowing_event_failure_is_red():
    _router = _BACKEND / "app" / "routers" / "consolidation.py"
    _assert_mutation_is_red(
        _router,
        b'recalc_trigger = "event_failed"',
        b'recalc_trigger = "event_published"',
        "路由吞掉事件异常仍返回 event_published",
        "tests/test_consol_elimination_review_response.py",
    )



def test_kept_manual_mutation_is_red():
    _run = _BACKEND / "app" / "services" / "consol_note_subtree_reaggregate.py"
    _assert_mutation_is_red(
        _run,
        b"outcome.status = _KEPT_MANUAL",
        b"outcome.status = _PERSISTED",
        "kept_manual 改回 persisted",
        "tests/services/test_consol_note_reaggregate_semantics.py",
    )



def test_executor_all_failed_mutation_is_red():
    _executor = _BACKEND / "app" / "services" / "consol_note_reaggregate_executor.py"
    _assert_mutation_is_red(
        _executor,
        b'if result.get("status") == "failed":',
        b'if False and result.get("status") == "failed":',
        "执行器全部失败仍返回成功",
        "tests/test_consol_note_reaggregate_durable_job.py",
    )



def test_kept_manual_stale_clear_mutation_is_red():
    _run = _BACKEND / "app" / "services" / "consol_note_subtree_reaggregate.py"
    _assert_mutation_is_red(
        _run,
        b"clear_stale(record)",
        b"pass",
        "kept_manual/汇总成功不清 stale 原因",
        "tests/services/test_consol_note_reaggregate_semantics.py",
    )
