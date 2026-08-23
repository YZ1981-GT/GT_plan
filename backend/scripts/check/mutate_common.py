"""变异检验公共 harness（高级查询系列变异脚本共用）。

各变异脚本按批次增长，harness 曾在每个脚本里各写一份。此处收敛为单点：
``Mutation`` 数据类、文件读写、跑单个守卫文件、按组跑变异与只读锚点校验。

判别四态（只看退出码会把后三态误判成 RED）：

===========  ============================================
RED          变红且正是预期那条测试        ← 唯一合格
GREEN        没变红                       ← 守卫有缺陷
ANCHOR-MISS  锚点未命中或命中 >1 处        ← 脚本有缺陷
WRONG-TEST   变红了但不是预期项            ← 锚点错行或污染残留
===========  ============================================

注意：锚点里含 ``\\n`` 的跨行文本在 CRLF 文件上必 MISS；本模块统一按 UTF-8 读写并
保持原换行（``newline=""`` 语义由 ``Path.read_text``/``write_text`` 的默认行为承担，
仓库内目标文件均为 LF）。
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Mutation:
    mid: str
    path: str
    old: str
    new: str
    expect_test: str
    why: str


def read_source(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


def write_source(path: str, text: str) -> None:
    (REPO / path).write_text(text, encoding="utf-8")


def run_named_guard(guard: str, expect_test: str) -> tuple[bool, bool]:
    """跑单个守卫文件；返回 (整体是否失败, 预期测试是否失败)。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", guard, "-q", "--tb=no", "-p", "no:cacheprovider"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    expected_failed = any(
        line.startswith("FAILED") and expect_test in line for line in out.splitlines()
    )
    return proc.returncode != 0, expected_failed


def run_group(mutations: tuple[tuple[Mutation, str], ...], label: str) -> int:
    """按 (变异, 守卫文件) 组跑变异；全部 RED 才返回 0。"""
    verdicts: dict[str, str] = {}
    for m, guard in mutations:
        base_failed, _ = run_named_guard(guard, "__none__")
        if base_failed:
            print(f"{m.mid}  SKIP(基线红)  {m.why}")
            verdicts[m.mid] = "BASE-RED"
            continue
        original = read_source(m.path)
        if original.count(m.old) != 1:
            verdicts[m.mid] = "ANCHOR-MISS"
            print(f"{m.mid}  ANCHOR-MISS  {m.why}")
            continue
        try:
            write_source(m.path, original.replace(m.old, m.new, 1))
            overall, expected = run_named_guard(guard, m.expect_test)
            verdict = "GREEN" if not overall else ("RED" if expected else "WRONG-TEST")
        finally:
            write_source(m.path, original)  # 无论如何恢复
        verdicts[m.mid] = verdict
        print(f"{m.mid}  {verdict:<12} {m.why}")
    counts = {v: sum(1 for x in verdicts.values() if x == v) for v in set(verdicts.values())}
    print(f"\n{label}判定汇总：" + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0 if counts.get("RED", 0) == len(mutations) else 1


def check_group_anchors(mutations: tuple[tuple[Mutation, str], ...], label: str) -> int:
    """只读校验：每个锚点须在目标文件中恰好命中一次。"""
    rc = 0
    print(f"── {label}锚点 ──")
    for m, _guard in mutations:
        hits = read_source(m.path).count(m.old)
        print(f"{m.mid}  {'OK' if hits == 1 else f'ANCHOR-MISS({hits})'}  {m.why}")
        if hits != 1:
            rc = 1
    return rc
