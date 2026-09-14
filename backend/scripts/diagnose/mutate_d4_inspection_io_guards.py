# -*- coding: utf-8 -*-
"""D4-13/14/15/16 导入导出守卫变异检验（四态）。

spec: d4-inspection-writeback-formula-io · Task 7
对 _d4_import_export.py 源文件做**临时**变异（改完立即恢复），每次重跑
tests/test_d4_inspection_io_guards.py，观察对应守卫是否打红。

3 锚点：
  M1 把 D4-15 item_id "D4-15-items" 改回 "D4-15-rows" → test_d4_15_item_id_* 必红
  M2 把 import 分发的 _parse_d4_16_row 改回 _parse_generic_row → test_import_dispatch_* 必红
  M3 把 _parse_d4_16_row 差异重算 (book - ports) 改成读文件差异列 → test_parse_d4_16_row_* 必红

四态：RED（打红且命中预期测试）/ GREEN（守卫缺陷，改坏仍绿）/
      ANCHOR-MISS（变异锚点未命中源码）/ WRONG-TEST（红了但不是预期项）。

用法（从 backend 目录）：
  python scripts/diagnose/mutate_d4_inspection_io_guards.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]  # backend/
_TARGET = _BACKEND / "app" / "routers" / "wp_render_strategies" / "_d4_import_export.py"
_TESTFILE = "tests/test_d4_inspection_io_guards.py"


def _run_test(node: str) -> tuple[bool, str]:
    """跑单个测试节点，返回 (passed, tail)。不经 shell，避免 -k 被拆。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", f"{_TESTFILE}::{node}", "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(_BACKEND), capture_output=True, text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    passed = proc.returncode == 0
    tail = out.strip().splitlines()[-3:] if out else []
    return passed, " | ".join(tail)


MUTATIONS = [
    {
        "id": "M1_item_id_back_to_rows",
        "node": "test_d4_15_item_id_is_items_not_rows",
        # export + import 两处都改回 D4-15-rows
        "old": 'item_id = "D4-15-items"',
        "new": 'item_id = "D4-15-rows"',
        "count": 2,
    },
    {
        "id": "M2_dispatch_back_to_generic",
        "node": "test_import_dispatch_uses_dedicated_parsers",
        "old": 'row_dict = _parse_d4_16_row(row, actual_headers)',
        "new": 'row_dict = _parse_generic_row(row, actual_headers)',
        "count": 1,
    },
    {
        "id": "M3_diff_read_from_file",
        "node": "test_parse_d4_16_row_english_keys_and_recalc",
        # 把重算改成读文件的“申报差异”列（造假入口）
        "old": '"taxDiff": book - tax,              # 重算',
        "new": '"taxDiff": _safe_float(_col_val("申报差异")),',
        "count": 1,
    },
]


def main() -> int:
    original = _TARGET.read_text(encoding="utf-8")

    # 基线：未变异时对应守卫必须全绿
    baseline = {}
    for mut in MUTATIONS:
        ok, tail = _run_test(mut["node"])
        baseline[mut["id"]] = ok
        if not ok:
            print(json.dumps({"baseline": "FAIL", "node": mut["node"], "tail": tail}, ensure_ascii=False))
            return 1

    verdicts = []
    green = 0
    for mut in MUTATIONS:
        hit = original.count(mut["old"])
        if hit != mut["count"]:
            verdicts.append({"id": mut["id"], "actual": "ANCHOR-MISS",
                             "detail": f"锚点命中 {hit} 次，期望 {mut['count']}"})
            continue
        mutated = original.replace(mut["old"], mut["new"], mut["count"])
        try:
            _TARGET.write_text(mutated, encoding="utf-8")
            passed, tail = _run_test(mut["node"])
        finally:
            _TARGET.write_text(original, encoding="utf-8")  # 立即恢复
        if passed:
            actual = "GREEN"  # 改坏仍绿 = 守卫缺陷
            green += 1
        else:
            actual = "RED"    # 预期该 node 打红
        verdicts.append({"id": mut["id"], "node": mut["node"], "actual": actual, "tail": tail})

    # 恢复自检：确认文件已还原
    restored_ok = _TARGET.read_text(encoding="utf-8") == original
    report = {
        "verdicts": verdicts,
        "green_count": green,
        "restored_ok": restored_ok,
        "pass": green == 0 and all(v["actual"] == "RED" for v in verdicts) and restored_ok,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
