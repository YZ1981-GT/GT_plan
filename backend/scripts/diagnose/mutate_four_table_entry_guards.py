"""四表库取数入口三铁律守卫的**变异检验**（Task 6 / four-table-extraction-entry-completion）.

对生产代码做**单行**变异，跑对应守卫，还原文件，四态判定：

  * RED         —— 守卫逮到变异且命中的正是预期那条测试（**期望态**）。
  * GREEN       —— 变异后守卫仍全绿 = **守卫缺陷**（断的是"函数存在"而非行为）。修守卫，不改代码。
  * ANCHOR-MISS —— 锚点在磁盘真相里命中 0 或 >1（脚本缺陷；注意 CRLF / 跨行 `\n` 锚点在 Windows 必 MISS）。
  * WRONG-TEST  —— 打红了但不是预期项（污染残留 / 锚点错行）。

三个锚点（Requirement 6.2 硬要求：至少含以下三条）：
  M1  去 active dataset 过滤   —— 删 `aux_aggregation.py` 里 `sa.and_(active_filter, ...)` 的 `active_filter,`
  M2  去单一 aux_type 锁定     —— 删 `aux_aggregation.py` 跳2 `.where(sa.and_(base_where, TbAuxBalance.aux_type == aux_type))` 的等值锁
  M3  merge → overwrite       —— 把 `_d3_import_export.py` 的 `new_rows = [过滤]` 改成 `new_rows = rows_data`（覆盖手工行）

铁律（workspace conventions）：
  * 磁盘真相经 `open(p, encoding='utf-8')` 读（不吃 read_file 陈旧缓存）；
  * 锚点必须**单行**（CRLF 安全）且断言命中次数 == 1；
  * 只变异 → 跑守卫 → 还原 → 判定；异常/中断也要在 finally 里还原（防污染工作树）。

用法：
  python backend/scripts/diagnose/mutate_four_table_entry_guards.py --check-anchors   # 只校验锚点唯一命中
  python backend/scripts/diagnose/mutate_four_table_entry_guards.py --apply           # 跑基线 + 逐锚点变异四态判定
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # …/GT_plan
AUX = ROOT / "backend/app/services/four_table/aux_aggregation.py"
D3 = ROOT / "backend/app/routers/wp_render_strategies/_d3_import_export.py"
GUARD = "tests/four_table/test_four_table_entry_guards.py"
PYTEST_CWD = ROOT / "backend"
ENVPATCH = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@dataclass(frozen=True)
class Case:
    id: str
    file: Path
    # 单行锚点（原文逐字，含缩进；不含换行 —— CRLF 安全）
    anchor: str
    replacement: str
    # 期望被打红的守卫（-k 过滤 + 输出里必须出现的 test 名）
    wants: tuple[str, ...]
    requirement: str


CASES = [
    Case(
        id="M1-remove-active-filter",
        file=AUX,
        anchor="            active_filter,",
        # 删掉 active_filter 这一元素（保留 _prefix_predicate），SQL 丢失 dataset_id 谓词 → 跨数据集双算
        replacement="            # active_filter,  <MUTATED: removed active dataset filter>",
        wants=("test_iron_law_1_active_filter_does_not_double_amount",),
        requirement="2.3/3.5 (Property 1)",
    ),
    Case(
        id="M2-remove-aux-type-lock",
        file=AUX,
        anchor="                .where(sa.and_(base_where, TbAuxBalance.aux_type == aux_type))",
        # 去掉单一 aux_type 等值锁 → 跳2 跨全部 aux_type 合计（成本中心混入）
        replacement="                .where(base_where)  # <MUTATED: removed single aux_type lock>",
        wants=("test_iron_law_2_single_aux_type_lock",),
        requirement="3.5 (Property 2)",
    ),
    Case(
        id="M3-merge-to-overwrite",
        file=D3,
        anchor='    new_rows = [r for r in rows_data if r["customerName"] not in existing_names]',
        # merge → overwrite：不再按业务键过滤，全部当新行 → 冲掉/重复已有手工行
        replacement="    new_rows = rows_data  # <MUTATED: merge -> overwrite>",
        wants=(
            "test_merge_keeps_existing_rows_byte_for_byte",
            "test_merge_does_not_overwrite_on_duplicate_key",
        ),
        requirement="3.4 (Property 3)",
    ),
]


def _read(p: Path) -> str:
    """磁盘真相（不吃缓存）。"""
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def _count(text: str, anchor: str) -> int:
    """单行锚点的出现次数（普通子串计数，非正则；CRLF 安全）。"""
    return text.count(anchor)


def check_anchors() -> int:
    bad = 0
    for case in CASES:
        n = _count(_read(case.file), case.anchor)
        status = "OK" if n == 1 else "ANCHOR-MISS"
        if n != 1:
            bad += 1
        print(f"  [{status}] {case.id} (n={n})  <- {case.file.name}")
    print(f"\nANCHOR-MISS: {bad}/{len(CASES)}")
    return 1 if bad else 0


def _run_guard(wants: tuple[str, ...]) -> tuple[int, str]:
    """只跑相关守卫（-k 过滤，subprocess 不经 shell，避免 -k 被拆词）。"""
    k_expr = " or ".join(wants)
    args = [
        sys.executable, "-m", "pytest", GUARD,
        "-k", k_expr, "-q", "-p", "no:randomly", "--tb=line",
    ]
    proc = subprocess.run(
        args, cwd=str(PYTEST_CWD), capture_output=True, env=ENVPATCH
    )
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace")


def classify(case: Case) -> str:
    """对单个锚点做变异 → 跑守卫 → 还原 → 四态判定。"""
    text = _read(case.file)
    n = _count(text, case.anchor)
    if n != 1:
        return f"{case.id}: ANCHOR-MISS (n={n})"

    new_text = text.replace(case.anchor, case.replacement, 1)
    if new_text == text or _count(new_text, case.anchor) != 0:
        return f"{case.id}: ANCHOR-MISS (replace no-op)"

    backup = case.file.with_suffix(case.file.suffix + ".mutbak")
    shutil.copy2(case.file, backup)
    try:
        with open(case.file, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_text)
        rc, out = _run_guard(case.wants)
        if rc == 0:
            # 变异后守卫仍全绿 = 守卫缺陷
            return f"{case.id}: GREEN (guard defect — Req {case.requirement})"
        # 打红了：确认打红的正是预期那几条测试（防污染/错行 = WRONG-TEST）
        hit = [w for w in case.wants if (w in out and "PASSED" not in _same_line(out, w))]
        # 简化：只要每条 wanted 测试名出现在 FAILED 行即视为命中
        failed_hits = [w for w in case.wants if _is_failed(out, w)]
        if len(failed_hits) == len(case.wants):
            return f"{case.id}: RED (caught by {list(case.wants)})"
        return f"{case.id}: WRONG-TEST (rc={rc}, failed_hits={failed_hits}, wanted={list(case.wants)})"
    finally:
        shutil.copy2(backup, case.file)
        backup.unlink(missing_ok=True)


def _same_line(out: str, name: str) -> str:
    for line in out.splitlines():
        if name in line:
            return line
    return ""


def _is_failed(out: str, name: str) -> bool:
    """该测试名是否出现在 FAILED 语境（pytest -q --tb=line 会输出 `FAILED …::name …`）。"""
    for line in out.splitlines():
        if name in line and "FAILED" in line:
            return True
    return False


def apply_all() -> int:
    # 先跑基线：守卫必须全绿，否则无从判断变异是否"新引入的红"
    rc, out = _run_guard(tuple(w for c in CASES for w in c.wants))
    if rc != 0:
        print("FAIL: 基线守卫未全绿，无法做变异检验\n")
        print(out[-2000:])
        return 1
    print("OK: 基线守卫全绿\n")

    print("变异四态判定：")
    bad = 0
    for case in CASES:
        result = classify(case)
        print(f"  {result}")
        if not result.split(": ", 1)[1].startswith("RED"):
            bad += 1
    print(f"\n非 RED（需处理）: {bad}/{len(CASES)}")
    print("判读：GREEN=守卫缺陷（修守卫）；ANCHOR-MISS=修锚点；WRONG-TEST=锚点错行/污染。")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check-anchors", action="store_true", help="只校验锚点唯一命中")
    ap.add_argument("--apply", action="store_true", help="跑基线 + 逐锚点变异四态判定")
    args = ap.parse_args()
    if args.check_anchors:
        return check_anchors()
    if args.apply:
        return apply_all()
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
