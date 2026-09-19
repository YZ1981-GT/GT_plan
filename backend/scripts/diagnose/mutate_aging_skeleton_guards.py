"""变异检验：账龄空骨架 Property 5/8 守卫 —— Phase 2 / Task 14.

spec: .kiro/specs/four-table-extraction-entry-completion/  (Task 14, Requirements 6.1, 6.2, 7.2, 7.4)

对两个真源锚点做**单行 CRLF-safe** 变异，跑对应守卫，四态判定：
  * RED         —— 守卫按预期打红（正是我们期望的那条测试挂了）。守卫有效。
  * GREEN       —— 变异后守卫仍全绿 = 守卫缺陷（没兜住这类回退）。
  * ANCHOR-MISS —— 锚点在磁盘上命中 0 次或 >1 次（脚本缺陷，不是代码问题）。
  * WRONG-TEST  —— 打红了，但挂的不是预期那条测试（污染 / 锚点错行）。

锚点：
  A（Property 5，红基线④）：`k1_aux_detail._empty_aging` 的
      `return {k: 0.0 for k in seg_keys}` → 改回把首段塞哨兵金额
      （`return {(list(seg_keys)+[""])[0]: 4242.0}`）。取数骨架某段带金额 ⇒
      `test_property5_k1_no_single_segment_equals_balance`（sum!=0）必红。
  B（Property 8，硬编码段键）：`k1_aux_detail.build_k1_detail_rows_from_aux` 的
      `seg_keys = _segment_keys(segments)` → 改成硬编码常量 `seg_keys = ["within1"]`，
      使段键不再随枚举变 ⇒ 三年/五年/自定义键集全塌成 `["within1"]`，
      `test_property8_k1_skeleton_keys_track_enum`（键集应互不相同）必红。

用法（从仓库根运行）：
    python backend/scripts/diagnose/mutate_aging_skeleton_guards.py

设计铁律遵循：单行锚点、断言磁盘命中==1、mutate→run→在 finally 里 restore、
磁盘真相一律 open(encoding="utf-8")、判成败看 pytest 退出码 + 目标测试是否在失败集里。
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
K1_SRC = REPO / "backend" / "app" / "services" / "four_table" / "k1_aux_detail.py"
GUARD_FILE = "backend/tests/four_table/test_aging_skeleton_properties.py"


@dataclass
class Anchor:
    name: str
    src: Path
    find: str          # 单行原文（不含换行）
    replace: str       # 单行变异文
    expect_test: str   # 期望打红的测试名（pytest -k / nodeid 片段）
    result: str = ""   # 四态
    detail: str = field(default="")


ANCHORS: list[Anchor] = [
    Anchor(
        name="A: _empty_aging 塞首段哨兵金额（回退红基线④，Property 5）",
        src=K1_SRC,
        find="    return {k: 0.0 for k in seg_keys}",
        replace='    return {(list(seg_keys) + [""])[0]: 4242.0}  # MUTANT-A',
        expect_test="test_property5_k1_no_single_segment_equals_balance",
    ),
    Anchor(
        name="B: seg_keys 硬编码 ['within1']（改枚举不变，Property 8）",
        src=K1_SRC,
        find="    seg_keys = _segment_keys(segments)",
        replace='    seg_keys = ["within1"]  # MUTANT-B',
        expect_test="test_property8_k1_skeleton_keys_track_enum",
    ),
]


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _write(p: Path, text: str) -> None:
    # newline="" 保留原文换行风格（CRLF/LF 不被改写）
    p.write_text(text, encoding="utf-8", newline="")


def _run_guard(expect_test: str) -> tuple[bool, bool, str]:
    """跑守卫，只选期望测试。返回 (passed_overall, expect_test_selected, tail)。"""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    proc = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            GUARD_FILE, "-k", expect_test,
            "-q", "--no-header", "--tb=line",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    tail = "\n".join(out.strip().splitlines()[-6:])
    # -k 选中的测试若为 0（锚点/命名漂移导致选空），pytest 退出码 5
    selected = proc.returncode != 5 and "no tests ran" not in out.lower()
    passed = proc.returncode == 0
    return passed, selected, tail


def _judge(anchor: Anchor) -> None:
    src = anchor.src
    original = _read(src)

    # 磁盘命中断言（CRLF-safe：按行等值比对，避免 \n 跨行锚点在 CRLF 下 MISS）
    lines = original.splitlines()
    hits = sum(1 for ln in lines if ln == anchor.find)
    if hits != 1:
        anchor.result = "ANCHOR-MISS"
        anchor.detail = f"锚点磁盘命中 {hits} 次（应==1）：{anchor.find!r}"
        return

    mutated = original.replace(anchor.find + "\n", anchor.replace + "\n", 1)
    if mutated == original:
        # 处理文件以该行结尾无换行的边角
        mutated = original.replace(anchor.find, anchor.replace, 1)
    if mutated == original:
        anchor.result = "ANCHOR-MISS"
        anchor.detail = "替换未生效（换行风格异常）"
        return

    try:
        _write(src, mutated)
        passed, selected, tail = _run_guard(anchor.expect_test)
    finally:
        _write(src, original)  # 无论如何都还原

    # 还原自检
    if _read(src) != original:
        anchor.result = "ANCHOR-MISS"
        anchor.detail = "还原失败（磁盘与原文不一致）"
        return

    if not selected:
        anchor.result = "WRONG-TEST"
        anchor.detail = f"期望测试 {anchor.expect_test} 未被选中（命名漂移？）\n{tail}"
    elif passed:
        anchor.result = "GREEN"
        anchor.detail = f"变异后守卫仍全绿 = 守卫缺陷\n{tail}"
    elif anchor.expect_test in tail or "FAILED" in tail or "failed" in tail:
        anchor.result = "RED"
        anchor.detail = tail
    else:
        anchor.result = "WRONG-TEST"
        anchor.detail = f"打红但未见期望测试名\n{tail}"


def main() -> int:
    print(f"[mutate] repo={REPO}")
    print(f"[mutate] guard={GUARD_FILE}\n")
    for a in ANCHORS:
        print(f"→ 变异 {a.name}")
        _judge(a)
        print(f"  结果: {a.result}")
        if a.detail:
            for ln in a.detail.splitlines():
                print(f"    {ln}")
        print()

    print("=" * 64)
    print("四态判定汇总")
    print("=" * 64)
    w = max(len(a.name) for a in ANCHORS)
    for a in ANCHORS:
        print(f"  {a.name.ljust(w)}  {a.result}")

    all_red = all(a.result == "RED" for a in ANCHORS)
    print()
    print("✅ 全锚点 RED —— 守卫有效" if all_red else "❌ 存在非 RED 锚点 —— 见上方明细")
    return 0 if all_red else 1


if __name__ == "__main__":
    raise SystemExit(main())
