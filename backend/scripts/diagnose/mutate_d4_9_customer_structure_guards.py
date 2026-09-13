# -*- coding: utf-8 -*-
"""D4-9 变异检验：证明 Task 3/4/9/10 的守卫真的锁死了各条结构约束。

spec: d4-9-customer-structure-bidirectional-writeback / Task 11
Requirements: 8.1, 8.2, 8.3

四态判定（只看失败测试名集合，不看退出码）：
- RED         打红了且**正是**预期那条测试（守卫有效）
- GREEN       改了行为却无任何判据变红（守卫缺陷，必修，不删变异）
- ANCHOR-MISS 锚点未命中或命中 >1 处（脚本缺陷）。含 \\n 跨行锚点在 CRLF 必 MISS，故全部单行片段
- WRONG-TEST  打红了但不是预期项（污染残留 / 锚点错行）

锚点（≥4，对齐 spec Requirement 8.3）：
  M01 删 formula_mask 保护   —— D/F 占比列不再受保护 ⇒ 契约/保护集守卫红
  M02 静态标量改成 row 域    —— totals 字段 row_from 从 24 改成 row_identity ⇒ parse 失败/结构守卫红
  M03 两 table 合并成一 table—— 上期 table_key 改成与本期同名 ⇒ 3-table 结构守卫红
  M04 去 rowId 身份          —— row_identity json_pointer 去掉 rowId ⇒ 投影 fail-closed 守卫红
  M05 总额来源改错           —— formula_lineage 的 D4-7 来源改错 ⇒ 血缘守卫红

用法（仓库根）：
    python backend/scripts/diagnose/mutate_d4_9_customer_structure_guards.py --list
    python backend/scripts/diagnose/mutate_d4_9_customer_structure_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_d4_9_customer_structure_guards.py --run all

🔴 禁后台执行（孤儿 python + 前台同时变异 ⇒ 还原失败）；绝不 --restore。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_SRC = _REPO / "backend" / "app" / "services" / "workpaper_sync" / "phase5_d4_customer_structure.py"

# 短 nodeid（basename::类::方法），带 backend/ 前缀会让 want 匹配失败。
_T3 = "test_d4_9_task3_contract.py"
_T4 = "test_d4_9_task4_projection.py"
_T9 = "test_d4_9_task9_formula_protection.py"


@dataclass
class Mutation:
    mid: str
    intent: str
    anchor: str  # 单行片段（原样出现在源文件里）
    new: str
    want: str  # 预期打红的测试（短 nodeid 子串）
    result: str = ""
    failed: list[str] = field(default_factory=list)


MUTATIONS: list[Mutation] = [
    Mutation(
        "M01",
        "删 formula_mask 保护：本期占比列区间清空 ⇒ D/F formula 字段脱离 mask",
        anchor='        f"D{CUR_FIRST_DATA_ROW}:D{CUR_LAST_DATA_ROW}",',
        new='        # (mutated: formula_mask 删除本期 D 列保护)',
        want="test_ratio_columns_are_formula_and_masked",
    ),
    Mutation(
        "M02",
        "静态标量改 row 域：totals 字段 row_from 从静态行号改成 row_identity",
        anchor='                "cell": {"column": column, "row_from": row},',
        new='                "cell": {"column": column, "row_from": "row_identity"},',
        want="test_totals_table_is_static_scalar",
    ),
    Mutation(
        "M03",
        "两 table 合并：上期 table_key 改成与本期同名 ⇒ 不再是 3 张独立 table",
        anchor='PRI_TABLE_KEY: Final[str] = "customer_prior_rows"',
        new='PRI_TABLE_KEY: Final[str] = "customer_current_rows"',
        want="test_exactly_three_tables",
    ),
    Mutation(
        "M04",
        "去 rowId 身份：动态行 row_identity json_pointer 去掉 rowId 段",
        anchor='        "row_identity": {"kind": "field", "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY}"},',
        new='        "row_identity": {"kind": "field", "json_pointer": "/rows/*/name"},',
        want="test_missing_row_id_fails_closed",
    ),
    Mutation(
        "M05",
        "总额来源改错：血缘里本期销售总额来源 D4-7!D26 改成错误 cell",
        anchor='            {"target": f"C{CUR_TOTAL_ROW}", "source": "D4-7!D26", "note": "本期销售总额从毛利率分析表D4-7取数；手工覆盖保留（Req 5.5）"},',
        new='            {"target": f"C{CUR_TOTAL_ROW}", "source": "D4-7!Z99", "note": "mutated"},',
        want="test_totals_source_is_d4_7",
    ),
]

_TEST_FILES = [
    f"backend/tests/workpaper_sync/{_T3}",
    f"backend/tests/workpaper_sync/{_T4}",
    f"backend/tests/workpaper_sync/{_T9}",
]


def _locate(lines: list[str], anchor: str) -> list[int]:
    return [i for i, ln in enumerate(lines) if anchor in ln]


def _check_anchors() -> int:
    text = _SRC.read_text(encoding="utf-8")
    lines = text.splitlines()
    bad = 0
    for m in MUTATIONS:
        hits = _locate(lines, m.anchor)
        status = "OK" if len(hits) == 1 else f"MISS({len(hits)})"
        if len(hits) != 1:
            bad += 1
        print(f"[{m.mid}] anchor {status}: {m.intent}")
    return 1 if bad else 0


def _run_tests() -> tuple[set[str], set[str]]:
    """跑三个守卫文件，返回 (失败测试名集合, 出错/collection-error 测试名集合)。

    🔴 UTF-8 显式解码：pytest 中文输出在 Windows GBK 控制台会 UnicodeDecodeError，
    text=True 会静默吞成 None ⇒ 解析到 0 个 FAILED，把有效守卫误判 GREEN。
    契约漂移让 fixture 抛异常 ⇒ pytest 报 **ERROR** 而非 FAILED，故两者都收集。
    """
    import os

    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *_TEST_FILES, "-rAE", "--tb=no", "-p", "no:cacheprovider"],
        cwd=str(_REPO),
        capture_output=True,
        env=env,
    )
    out = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
    failed: set[str] = set()
    errored: set[str] = set()
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("FAILED "):
            failed.add(line[len("FAILED "):].split(" ")[0].split("::")[-1])
        elif line.startswith("ERROR "):
            errored.add(line[len("ERROR "):].split(" ")[0].split("::")[-1])
    return failed, errored


def _apply(m: Mutation) -> tuple[bool, str]:
    text = _SRC.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    hits = [i for i, ln in enumerate(lines) if m.anchor in ln]
    if len(hits) != 1:
        return False, f"命中 {len(hits)} 行"
    idx = hits[0]
    orig = lines[idx]
    indent = orig[: len(orig) - len(orig.lstrip())]
    lines[idx] = indent + m.new.lstrip() + ("\n" if orig.endswith("\n") else "")
    _SRC.write_text("".join(lines), encoding="utf-8")
    return True, orig


def _run(selected: list[str]) -> int:
    original = _SRC.read_bytes()
    try:
        for m in MUTATIONS:
            if selected != ["all"] and m.mid not in selected:
                continue
            ok, note = _apply(m)
            if not ok:
                m.result = "ANCHOR-MISS"
                print(f"[{m.mid}] ANCHOR-MISS: {note}")
                _SRC.write_bytes(original)
                continue
            try:
                failed, errored = _run_tests()
            finally:
                _SRC.write_bytes(original)
            # 契约漂移让 module fixture 抛异常 ⇒ 该模块**全部**测试报 ERROR（含 want）。
            # FAILED（断言级）与 ERROR（fixture 级）都算守卫触发；want 命中任一即 RED。
            fired = failed | errored
            m.failed = sorted(fired)
            if not fired:
                m.result = "GREEN"
            elif any(m.want in f for f in fired):
                m.result = "RED"
            else:
                m.result = "WRONG-TEST"
            print(f"[{m.mid}] {m.result} fired={m.failed or '()'}  <= {m.intent}")
    finally:
        _SRC.write_bytes(original)

    # 还原后必须回到全绿。
    restored_fail, restored_err = _run_tests()
    restored_fail = restored_fail | restored_err
    red = sum(1 for m in MUTATIONS if m.result == "RED")
    bad = [m.mid for m in MUTATIONS if m.result in {"GREEN", "ANCHOR-MISS", "WRONG-TEST"}]
    print("=" * 70)
    print(f"汇总: RED={red}/{len([m for m in MUTATIONS if m.result])}  问题项={bad}  还原后失败={sorted(restored_fail) or '无'}")
    if bad or restored_fail:
        print("🔴 GREEN=守卫缺陷 / ANCHOR-MISS=脚本缺陷 / WRONG-TEST=锚点错行 / 还原后不绿=污染")
        return 1
    print("✅ 全部变异被守卫捕获，还原后回到全绿。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--run", nargs="?", const="all", default=None)
    args = ap.parse_args()
    if args.list:
        for m in MUTATIONS:
            print(f"{m.mid}: {m.intent}\n    want={m.want}")
        return 0
    if args.check_anchors:
        return _check_anchors()
    if args.run is not None:
        return _run([s.strip() for s in args.run.split(",")] if args.run != "all" else ["all"])
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
