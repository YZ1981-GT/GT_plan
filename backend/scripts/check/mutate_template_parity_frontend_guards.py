# -*- coding: utf-8 -*-
"""前端「按模板对齐」的磁盘变异（spec oo-writeback-template-parity-closure 任务 7.2）。

任务 7.2 要求：任务 7.1 里每条「按模板改前端」的项，改回旧口径都必须打红。
本脚本按前端守卫逐条注入旧口径，用 vitest 跑对应用例，四态判定同
:mod:`backend.scripts.check.mutate_common`（RED / GREEN / ANCHOR-MISS / WRONG-TEST）。

用法（🔴 单条命令跑，不要与其他命令串行）::

    python backend/scripts/check/mutate_template_parity_frontend_guards.py --check-anchors
    python backend/scripts/check/mutate_template_parity_frontend_guards.py

前端目录默认 ``audit-platform/frontend``；vitest 走 ``node node_modules/vitest/vitest.mjs``
（不经 ``cmd /c npx``：文件多时会撞 Windows 命令行长度上限）。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "audit-platform" / "frontend"

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):  # pragma: no cover
        pass

D1_ECL = "src/components/workpaper/composables/useD1EclCalc.ts"
D1_NOTES = "src/components/workpaper/composables/useD1NotesReceivable.ts"
D2_ENGINE = "src/components/workpaper/composables/useD2FormulaEngine.ts"
CHANGE_RATE = "src/components/workpaper/composables/templateChangeRate.ts"
D6_DETAIL = "src/components/workpaper/composables/useD6ImpairmentDetail.ts"

GUARD_D = "src/components/workpaper/__tests__/templateParityDBatch.spec.ts"
GUARD_FG = "src/components/workpaper/__tests__/templateParityFGBatch.spec.ts"


@dataclass(frozen=True)
class FrontMutation:
    mid: str
    path: str
    old: str
    new: str
    guard: str
    expect: str
    why: str


MUTATIONS: tuple[FrontMutation, ...] = (
    FrontMutation(
        mid="F1",
        path=D1_ECL,
        old="  return shouldProvision - actualProvision",
        new="  return actualProvision - shouldProvision",
        guard=GUARD_D,
        expect="少提为正、多提为负",
        why="D1-15 差异退回旧口径「实际 − 应计」（模板 ⑤=③−④）",
    ),
    FrontMutation(
        mid="F2",
        path=D1_NOTES,
        old="  return shouldProvision - actualProvision",
        new="  return actualProvision - shouldProvision",
        guard=GUARD_D,
        expect="少提为正、多提为负",
        why="D2-9 差异退回旧口径（同 D1-15，废弃的 useD1NotesReceivable 一并）",
    ),
    FrontMutation(
        mid="F3",
        path=D2_ENGINE,
        old="  return should - actual",
        new="  return actual - should",
        guard=GUARD_D,
        expect="少提为正、多提为负",
        why="D2 公式引擎差异退回旧口径",
    ),
    FrontMutation(
        mid="F4",
        path=D6_DETAIL,
        old="    row.priorUnadjusted, row.provision, row.otherIncrease,",
        new="    priorAudited, row.provision, row.otherIncrease,",
        guard=GUARD_D,
        expect="期初账项 / 重分类调整不带入期末未审",
        why="D6-3 期末未审退回从期初审定起算（模板 K = B + …）",
    ),
    FrontMutation(
        mid="F5",
        path=CHANGE_RATE,
        old="  if (prior === 0 && current === 0) return blank\n  if (prior === 0) return current > 0 ? 1 : 'N/A'",
        new="  if (prior === 0) return current === 0 ? blank : (current > 0 ? 1 : -1)",
        guard=GUARD_FG,
        expect="期初为 0 时按模板",
        why="变动率退回旧口径：期初 0 且本期减少记 −1（模板 #DIV/0! ⇒ 'N/A'）",
    ),
    FrontMutation(
        mid="F6",
        path=CHANGE_RATE,
        old="  if (prior === 0 && current === 0) return blank",
        new="  if (prior === 0 && current === 0) return 'N/A'",
        guard=GUARD_FG,
        expect="F1-1 / F4-1",
        why="变动率两者都 0 时退回 'N/A'（D 类模板为空串 / F1-1 为 0，由 blank 参数决定）",
    ),
)


def _read(path: Path) -> str:
    """按 LF 读取（把磁盘上的 CRLF 归一，比对锚点用）。"""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _write(path: Path, text: str) -> None:
    """🔴 一律写 LF。

    ``core.autocrlf=true`` 时 ``Path.write_text`` 默认按平台换行写回，复原后与 HEAD 不是
    逐字节相同（整文件 churn）。仓库已踩过这个坑，这里显式 ``newline="\\n"``。
    """
    path.write_text(text, encoding="utf-8", newline="\n")


def _run_vitest(guard: str) -> tuple[bool, str]:
    proc = subprocess.run(
        ["node", "node_modules/vitest/vitest.mjs", "run", guard],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "CI": "1"},
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode != 0, out


def check_anchors() -> int:
    rc = 0
    print("── 任务 7.2 前端变异锚点 ──")
    for m in MUTATIONS:
        text = _read(FRONTEND / m.path)
        hits = text.count(m.old)
        print(f"{m.mid}  {'OK' if hits == 1 else f'ANCHOR-MISS({hits})'}  {m.why}")
        if hits != 1:
            rc = 1
    return rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-anchors", action="store_true")
    args = parser.parse_args(argv)
    if args.check_anchors:
        return check_anchors()

    verdicts: dict[str, str] = {}
    for m in MUTATIONS:
        target = FRONTEND / m.path
        original = _read(target)
        if original.count(m.old) != 1:
            verdicts[m.mid] = "ANCHOR-MISS"
            print(f"{m.mid}  ANCHOR-MISS  {m.why}")
            continue
        base_failed, _ = _run_vitest(m.guard)
        if base_failed:
            verdicts[m.mid] = "BASE-RED"
            print(f"{m.mid}  SKIP(基线红)  {m.why}")
            continue
        try:
            _write(target, original.replace(m.old, m.new, 1))
            failed, out = _run_vitest(m.guard)
            hit_expected = m.expect in out
            verdict = "GREEN" if not failed else ("RED" if hit_expected else "WRONG-TEST")
        finally:
            _write(target, original)
            if _read(target) != original:  # pragma: no cover
                print(f"{m.mid}  !! 复原失败，请手工核对 {m.path}")
        verdicts[m.mid] = verdict
        print(f"{m.mid}  {verdict:<12} {m.why}")

    counts: dict[str, int] = {}
    for v in verdicts.values():
        counts[v] = counts.get(v, 0) + 1
    print("\n任务 7.2 判定汇总：" + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0 if counts.get("RED", 0) == len(MUTATIONS) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
