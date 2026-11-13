"""任务 5.5 的磁盘变异验证。

每个变异都在独立子进程中运行真实的后端或前端回归用例。变异前保存原始
字节，验证结束后无论成功失败都逐字节恢复，避免把变异态留在工作树。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "audit-platform" / "frontend"
GROUP_LINKS = ROOT / "backend" / "app" / "services" / "group_links.py"
PROJECT_WIZARD = ROOT / "backend" / "app" / "routers" / "project_wizard.py"
CONSOLIDATION_HUB = ROOT / "audit-platform" / "frontend" / "src" / "views" / "ConsolidationHub.vue"


Mutation = Callable[[bytes], bytes]


def _run_backend(node_id: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    env.pop("GT_REQUIRE_PG", None)
    return subprocess.run(
        [sys.executable, "-m", "pytest", node_id, "-q", "-p", "no:playwright", "--tb=short"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )


def _run_frontend() -> subprocess.CompletedProcess[str]:
    node = "node"
    return subprocess.run(
        [node, "node_modules/vitest/vitest.mjs", "run",
         "src/views/__tests__/ConsolidationHub.reparent.spec.ts", "--reporter=verbose"],
        cwd=FRONTEND,
        env={**os.environ, "FORCE_COLOR": "0"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )


def _normalized(raw: bytes) -> tuple[str, str]:
    text = raw.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), newline


def _with_newline(text: str, newline: str) -> bytes:
    return text.replace("\n", newline).encode("utf-8")


def _replace_once(raw: bytes, old: str, new: str, *, label: str) -> bytes:
    text, newline = _normalized(raw)
    count = text.count(old)
    assert count == 1, f"{label} 变异锚点应命中 1 次，实际 {count} 次"
    return _with_newline(text.replace(old, new), newline)


def _move_comparison_before_lock(raw: bytes) -> bytes:
    text, newline = _normalized(raw)
    lock = "    await lock_topology_years(db, [year])\n"
    comparison = "    if expected_parent_code is not _UNCHECKED:\n"
    next_check = "    if resolve_project_audit_year(project) != year:\n"
    function_start = text.index("async def reparent_project(")
    lock_start = text.index(lock, function_start)
    comparison_start = text.index(comparison, lock_start)
    comparison_end = text.index(next_check, comparison_start)
    comparison_block = text[comparison_start:comparison_end]
    locked_region_without_comparison = text[lock_start:comparison_start] + text[comparison_end:]
    # The current implementation compares only after lock_topology_years + refresh.
    # This mutation puts the same comparison before both operations so the
    # deterministic interleaving test can prove the race is no longer protected.
    mutated = text[:lock_start] + comparison_block + locked_region_without_comparison
    return _with_newline(mutated, newline)


def _assert_red(path: Path, mutate: Mutation, run: Callable[[], subprocess.CompletedProcess[str]], label: str) -> None:
    original = path.read_bytes()
    mutated = mutate(original)
    assert mutated != original, f"{label} 未改变目标文件，不能算有效变异"
    path.write_bytes(mutated)
    try:
        result = run()
        output = (result.stdout or "") + (result.stderr or "")
        evidence = output[-4000:]
        print(f"[task-5.5-mutation][RED] {label}\n{evidence}")
        assert result.returncode != 0, f"{label} 存活（测试仍通过）\n{evidence}"
    finally:
        path.write_bytes(original)
        assert path.read_bytes() == original, f"{label} 恢复后字节不一致"


def test_mutation_delete_service_cas_comparison_is_red() -> None:
    """变异：删除服务层比较，过期期望值测试必须失败。"""
    _assert_red(
        GROUP_LINKS,
        lambda raw: _replace_once(
            raw,
            "    if expected_parent_code is not _UNCHECKED:",
            "    if False and expected_parent_code is not _UNCHECKED:",
            label="删除服务层 CAS 比较",
        ),
        lambda: _run_backend(
            "tests/test_parent_code_update.py::test_stale_expected_parent_returns_409_and_keeps_both_scopes"
        ),
        "删除服务层 CAS 比较",
    )


def test_mutation_move_service_cas_comparison_before_lock_is_red() -> None:
    """变异：把比较移到锁与 refresh 之前，交错并发测试必须失败。"""
    _assert_red(
        GROUP_LINKS,
        _move_comparison_before_lock,
        lambda: _run_backend(
            "tests/test_parent_code_update.py::test_expected_parent_code_is_checked_after_topology_lock_refresh"
        ),
        "CAS 比较移到拓扑锁之前",
    )


def test_mutation_missing_expected_parent_is_red() -> None:
    """变异：缺少 expected_parent_company_code 改为放行，428 测试必须失败。"""
    _assert_red(
        PROJECT_WIZARD,
        lambda raw: _replace_once(
            raw,
            '    if "expected_parent_company_code" not in body.model_fields_set:',
            "    if False:",
            label="缺少 expected_parent_company_code 改为放行",
        ),
        lambda: _run_backend(
            "tests/test_parent_code_update.py::test_expected_parent_code_missing_returns_428_without_write"
        ),
        "缺少 expected_parent_company_code 改为放行",
    )


def test_mutation_frontend_omits_expected_parent_is_red() -> None:
    """变异：前端 PATCH 不发送期望上级，现有请求契约测试必须失败。"""
    _assert_red(
        CONSOLIDATION_HUB,
        lambda raw: _replace_once(
            raw,
            "      expected_parent_company_code: dragData.parentCompanyCode ?? null,",
            "",
            label="前端拖拽不带 expected_parent_company_code",
        ),
        _run_frontend,
        "前端拖拽不带 expected_parent_company_code",
    )
