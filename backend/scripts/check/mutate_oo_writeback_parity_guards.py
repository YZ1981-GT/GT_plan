# -*- coding: utf-8 -*-
"""oo-writeback-template-parity-closure 的磁盘变异（任务 2.3 / 3.3 / 5.3）。

三个任务各自的守卫已经存在且基线全绿，但此前**从未做过磁盘变异**：

* 2.3 受保护口径改回旧口径（cross_sheet 当可编辑）必须打红；
* 3.3 公式还原三种形态（去掉还原 / 还原到错行 / 选 OO 值也还原）必须打红；
* 5.3 签名几何归一（不做归一 / 偏一行）必须打红。

四态判定沿用 :mod:`backend.scripts.check.mutate_common`：只有 ``RED``（变红且正是预期
那条用例）算合格；``GREEN`` 说明守卫有缺陷，``ANCHOR-MISS`` / ``WRONG-TEST`` 说明靶点写错。

用法::

    python backend/scripts/check/mutate_oo_writeback_parity_guards.py --check-anchors
    python backend/scripts/check/mutate_oo_writeback_parity_guards.py

🔴 必须单条命令跑，不要与别的命令串起来 —— 工具返回不代表子进程结束，串着跑会与仍在
写盘的变异交错，可能把变异态留在磁盘上。脚本内部每轮 ``finally`` 逐字节复原。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
if str(_HERE.parents[3]) not in sys.path:  # pragma: no cover - 脚本自举
    sys.path.insert(0, str(_HERE.parents[3]))

from backend.scripts.check.mutate_common import (  # noqa: E402
    Mutation,
    run_group,
    run_named_guard,
)

# 🔴 读写一律走 LF：``core.autocrlf=true`` 时 ``Path.write_text`` 会按平台换行写回，
# 复原后与 HEAD 不是逐字节相同（整文件 churn，git diff 为空但 status 报 M）。
REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


def _write(path: str, text: str) -> None:
    (REPO_ROOT / path).write_text(text, encoding="utf-8", newline="\n")

CONTRACTS = "backend/app/services/workpaper_sync/contracts.py"
BASE = "backend/app/services/workpaper_sync/adapters/base.py"
MERGE = "backend/app/services/workpaper_sync/merge.py"
RESTORE = "backend/app/services/workpaper_sync/formula_restore.py"
EVIDENCE = "backend/app/services/workpaper_sync/formula_recompute_evidence.py"
CONFLICTS = "backend/app/services/workpaper_sync/conflicts.py"

GUARD_PROTECTED = "backend/tests/workpaper_sync/test_protected_mode_single_source.py"
GUARD_RESTORE = "backend/tests/workpaper_sync/test_tamper_keep_current_restores_formula.py"
GUARD_SIGNATURE = "backend/tests/workpaper_sync/test_formula_signature_geometry.py"
GUARD_CONFLICT = "backend/tests/workpaper_sync/test_task14_merge_conflicts.py"

# ── 任务 2.3：受保护口径改回旧口径 ────────────────────────────────────────────
#
# 修前三处口径不同。任何一处退回旧口径都必须被 `test_three_definitions_agree` /
# `test_real_cross_sheet_fields_locate_as_formula` / `test_cross_sheet_*` 抓住。

PROTECTED_MUTATIONS: tuple[tuple[Mutation, str], ...] = (
    (
        Mutation(
            mid="P1",
            path=CONTRACTS,
            old="PROTECTED_MODES: Final[frozenset[FieldMode]] = FORMULA_MODES | frozenset({FieldMode.auto_source})",
            new="PROTECTED_MODES: Final[frozenset[FieldMode]] = frozenset({FieldMode.formula, FieldMode.auto_source})",
            expect_test="test_three_definitions_agree",
            why="受保护集合退回不含 cross_sheet（修前 contracts 一侧的口径）",
        ),
        GUARD_PROTECTED,
    ),
    (
        Mutation(
            mid="P2",
            path=BASE,
            old="        return self.mode in PROTECTED_MODES",
            new="        return self.mode in (FieldMode.formula, FieldMode.auto_source)",
            expect_test="test_three_definitions_agree",
            why="FieldValue.is_protected 退回只认 formula / auto_source（修前 adapters 一侧）",
        ),
        GUARD_PROTECTED,
    ),
    (
        Mutation(
            mid="P3",
            path=MERGE,
            old="        if spec.mode in FORMULA_MODES:\n            return ProtectionPolicy.read_only_formula",
            new="        if spec.mode is FieldMode.formula:\n            return ProtectionPolicy.read_only_formula",
            expect_test="test_real_cross_sheet_fields_locate_as_formula",
            why="merge._protection 只认本表 formula，把 cross_sheet 当可编辑（修前 merge 一侧）",
        ),
        GUARD_PROTECTED,
    ),
    (
        Mutation(
            mid="P4",
            path=CONTRACTS,
            old="FORMULA_MODES: Final[frozenset[FieldMode]] = frozenset({FieldMode.formula, FieldMode.cross_sheet})",
            new="FORMULA_MODES: Final[frozenset[FieldMode]] = frozenset({FieldMode.formula})",
            expect_test="test_formula_modes_partition",
            why="公式模式集合退回只含 formula（cross_sheet 不再按公式字段处理）",
        ),
        GUARD_PROTECTED,
    ),
)

# ── 任务 3.3：公式还原 ────────────────────────────────────────────────────────
#
# 任务书列了三种形态：去掉还原 / 还原到错行 / 选 OO 值也还原。前两条直接对应；
# 第三条按**真实语义**落地：受保护公式格永远不允许选 OO 值
# （`conflicts.resolved_value_for` 对 `is_protected` 只允许 keep_current，
# 需求 4.2 说的是「行为与现在一致」）。若把这道禁令去掉，用户在受保护格上
# 「选 OO 值」就会被放行 ⇒ 公式被覆盖（AC 6.6 失守）。变异即注入该放行。

RESTORE_MUTATIONS: tuple[tuple[Mutation, str], ...] = (
    (
        Mutation(
            mid="R1",
            path=RESTORE,
            old="    signatures = _BASE_SIGNATURES.get()\n    if not signatures:\n        return None",
            new="    signatures = _BASE_SIGNATURES.get()\n    if True:\n        return None",
            expect_test="test_keep_server_writes_the_template_formula_back",
            why="去掉还原：wanted_formula 恒返回 None（受保护格被敲成数字后整次保存失败）",
        ),
        GUARD_RESTORE,
    ),
    (
        Mutation(
            mid="R2",
            path=RESTORE,
            old="    text = FRE.instantiate_signature(signature, row=row, frame=frame)",
            new="    text = FRE.instantiate_signature(signature, row=row + 1, frame=frame)",
            expect_test="test_keep_server_writes_the_template_formula_back",
            why="还原到错行：签名落到 row+1，写回的公式引用整行偏移",
        ),
        GUARD_RESTORE,
    ),
    (
        Mutation(
            mid="R3",
            path=CONFLICTS,
            old="    if record.locator.is_protected and choice.kind is not ResolutionKind.keep_current:",
            new="    if False:",
            expect_test="test_protected_conflict_cannot_be_resolved_by_taking_incoming",
            why="选 OO 值也放行：受保护格的「只允许 keep_current」禁令被去掉 ⇒ 公式被覆盖",
        ),
        GUARD_CONFLICT,
    ),
)

# ── 任务 5.3：签名几何归一 ────────────────────────────────────────────────────

SIGNATURE_MUTATIONS: tuple[tuple[Mutation, str], ...] = (
    (
        Mutation(
            mid="S1",
            path=EVIDENCE,
            old="    if row == own_row:\n        return SAME_ROW\n    if frame is None:\n        return None",
            new="    if row == own_row:\n        return SAME_ROW\n    if True:\n        return None",
            expect_test="test_signature_survives_insert_and_delete",
            why="不做归一：给了 frame 也把他行引用逐字保留（插行后签名必变）",
        ),
        GUARD_SIGNATURE,
    ),
    (
        Mutation(
            mid="S2",
            path=EVIDENCE,
            old='    if row > first:\n        return "{r%+d}" % (row - own_row)',
            new='    if row > first:\n        return "{r%+d}" % (row - own_row + 1)',
            expect_test="test_tokens",
            why="偏一行：表内他行偏移量 +1，签名与真实位置不符",
        ),
        GUARD_SIGNATURE,
    ),
    (
        Mutation(
            mid="S3",
            path=EVIDENCE,
            old='    if row > last:\n        return "{end+%d}" % (row - last)',
            new='    if row > last:\n        return "{end+%d}" % (row - last + 1)',
            expect_test="test_tokens",
            why="表下方合计行偏移量偏一行（{end+k} 与真实位置不符）",
        ),
        GUARD_SIGNATURE,
    ),
    (
        Mutation(
            mid="S4",
            path=EVIDENCE,
            old="        value = _token_row(token, row=row, frame=frame)",
            new="        value = _token_row(token, row=row, frame=None)",
            expect_test="test_instantiate_into_shifted_geometry",
            why="还原时丢掉几何：插过行的文件里合计行引用落不回新位置",
        ),
        GUARD_SIGNATURE,
    ),
)

GROUPS: tuple[tuple[str, tuple[tuple[Mutation, str], ...]], ...] = (
    ("任务 2.3 受保护口径", PROTECTED_MUTATIONS),
    ("任务 3.3 公式还原", RESTORE_MUTATIONS),
    ("任务 5.3 签名几何", SIGNATURE_MUTATIONS),
)


def _check_anchors(group, label: str) -> int:
    """只读校验：每个锚点须在目标文件中恰好命中一次（按 LF 归一后计数）。"""
    rc = 0
    print(f"── {label}锚点 ──")
    for m, _guard in group:
        hits = _read(m.path).count(m.old)
        print(f"{m.mid}  {'OK' if hits == 1 else f'ANCHOR-MISS({hits})'}  {m.why}")
        if hits != 1:
            rc = 1
    return rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-anchors",
        action="store_true",
        help="只读校验锚点命中数（不改文件、不跑测试）",
    )
    parser.add_argument(
        "--group",
        choices=[name for name, _ in GROUPS],
        help="只跑某一组（默认全部）",
    )
    args = parser.parse_args(argv)

    selected = [g for g in GROUPS if args.group is None or g[0] == args.group]
    if args.check_anchors:
        rc = 0
        for name, group in selected:
            rc |= _check_anchors(group, name)
        return rc

    all_verdicts: dict[str, str] = {}
    rc = 0
    for name, group in selected:
        print(f"── {name} ──")
        verdicts: dict[str, str] = {}
        for m, guard in group:
            base_failed, _ = run_named_guard(guard, "__none__")
            if base_failed:
                verdicts[m.mid] = "BASE-RED"
                print(f"{m.mid}  SKIP(基线红)  {m.why}")
                continue
            original = _read(m.path)
            if original.count(m.old) != 1:
                verdicts[m.mid] = "ANCHOR-MISS"
                print(f"{m.mid}  ANCHOR-MISS  {m.why}")
                continue
            try:
                _write(m.path, original.replace(m.old, m.new, 1))
                overall, expected = run_named_guard(guard, m.expect_test)
                verdict = "GREEN" if not overall else ("RED" if expected else "WRONG-TEST")
            finally:
                _write(m.path, original)  # 无论如何逐字节复原（LF）
                if _read(m.path) != original:  # pragma: no cover
                    print(f"{m.mid}  !! 复原失败，请手工核对 {m.path}")
            verdicts[m.mid] = verdict
            print(f"{m.mid}  {verdict:<12} {m.why}")
        counts = {v: sum(1 for x in verdicts.values() if x == v) for v in set(verdicts.values())}
        print(f"{name}判定汇总：" + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        # 组内必须全 RED；计数只看本组，不能跨组累计
        if counts.get("RED", 0) != len(group):
            rc = 1
        all_verdicts.update(verdicts)

    total = sum(1 for g in selected for _ in g[1])
    red = sum(1 for v in all_verdicts.values() if v == "RED")
    print(f"\n总计：RED={red}/{total}")
    return rc


if __name__ == "__main__":  # pragma: no cover - 脚本入口
    raise SystemExit(main())
