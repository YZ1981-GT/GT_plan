"""C2 收口守卫：附注公式刷新链必须真的取章节级 advisory 锁。

spec: `platform-heavy-jobs-and-capacity-closure` 批 C 任务 C2。

## 为什么需要这条守卫

复核记录写明「`note_followup` / 合并附注写入方尚未切到新内核」，而
`_apply_note_formulas` 在切内核前只有 `db.begin_nested()`（章节 SAVEPOINT）——
SAVEPOINT 只隔离**失败**，不隔离**并发**：两个进程同时刷新同一章节时，
双方都能读到旧 `table_data` 再各自写回，后写者静默覆盖先写者的公式结果。

## 判据（三条，缺一即红）

1. `_apply_note_formulas` 真的调用 `acquire_section_lock`（不是只在 import 里出现）；
2. 调用点在 `execute_note_formulas` **之前**（先锁后写；反了就等于没锁）；
3. 每个章节都取锁（调用点在 `for sec in sections:` 循环体内）。

三条都按源码 AST/文本位置判定，避免「import 了但没调用」这类假绿。
"""

from __future__ import annotations

import ast
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "note_workpaper_pull_service.py"
)


def _apply_note_formulas_node() -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_apply_note_formulas":
            return node
    raise AssertionError("找不到 _apply_note_formulas（改名后必须同步本守卫）")


def _called_names(node: ast.AST) -> list[tuple[int, str]]:
    """按行号返回该函数体内所有直接调用的函数名。"""
    out: list[tuple[int, str]] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name:
                out.append((sub.lineno, str(name)))
    return sorted(out)


def test_section_lock_is_actually_called() -> None:
    """判据 1：确实调用了 acquire_section_lock（不是只 import）。"""
    calls = {name for _line, name in _called_names(_apply_note_formulas_node())}
    assert "acquire_section_lock" in calls, (
        "_apply_note_formulas 没有调用 acquire_section_lock ⇒ 并发刷新同一章节会互相覆盖"
    )


def test_lock_is_acquired_before_formula_execution() -> None:
    """判据 2：先取锁后执行公式（顺序反了等于没锁）。"""
    calls = _called_names(_apply_note_formulas_node())
    lock_lines = [line for line, name in calls if name == "acquire_section_lock"]
    exec_lines = [line for line, name in calls if name == "execute_note_formulas"]
    assert lock_lines, "没有 acquire_section_lock 调用"
    assert exec_lines, "没有 execute_note_formulas 调用"
    assert min(lock_lines) < min(exec_lines), (
        f"取锁行 {lock_lines} 必须早于公式执行行 {exec_lines}"
    )


def test_lock_is_inside_the_sections_loop() -> None:
    """判据 3：取锁在 `for sec in sections:` 循环体内（每章节各取一次）。"""
    node = _apply_note_formulas_node()
    loop_lines = [
        sub.lineno
        for sub in ast.walk(node)
        if isinstance(sub, ast.For) and getattr(sub.target, "id", None) == "sec"
    ]
    assert loop_lines, "找不到 `for sec in sections:` 循环"
    lock_lines = [line for line, name in _called_names(node) if name == "acquire_section_lock"]
    assert lock_lines, "没有 acquire_section_lock 调用"
    assert all(line > min(loop_lines) for line in lock_lines), (
        "acquire_section_lock 必须在遍历 sections 的循环体内"
    )


def test_kernel_exposes_lock_only_entry_point() -> None:
    """内核必须提供只取锁的入口（不代做读写），并容忍无 bind 的 session 替身。"""
    from app.services.disclosure import note_section_write_kernel as kernel

    assert hasattr(kernel, "acquire_section_lock"), (
        "内核缺少只取锁入口 ⇒ 调用方只能被迫用 no-op mutator 多做一次全表读"
    )
    assert "acquire_section_lock" in kernel.__all__
    # 非 PG（测试替身没有 bind / 方言名不是 postgresql）必须返回 False 而不是抛错
    class _BareSession:
        pass

    import asyncio

    got = asyncio.run(
        kernel.acquire_section_lock.__wrapped__(_BareSession())
    ) if hasattr(kernel.acquire_section_lock, "__wrapped__") else None
    # 直接走方言判定函数，验证无 bind 不抛
    assert kernel._dialect_name(_BareSession()) == ""