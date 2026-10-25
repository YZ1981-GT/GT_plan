"""D4 价格分析回写联动守卫的**变异检验**（spec d4-price-analysis-writeback-linkage / Task 8）.

对前端生产代码做**单行**变异，跑对应 vitest 守卫，还原文件，四态判定：

  * RED         —— 守卫逮到变异（**期望态**）。
  * GREEN       —— 变异后守卫仍全绿 = **守卫缺陷**（断的是"字符存在"而非行为）。修守卫，不改代码。
  * ANCHOR-MISS —— 锚点在磁盘真相里命中 0 或 >1（脚本缺陷）。
  * WRONG-TEST  —— 打红了但 vitest 报告的失败文件不含预期守卫。

三个锚点（Requirement 7.2 硬要求）：
  M1  删接收端       —— 删 useD4PriceWriteback.ts 的 `eventBus.on('d4:price-abnormal', ...)`
                        → 回写又成死代码 → d4NoDeadEvent + d4PriceWritebackLinkage 必红
  M2  改错回写目标 key —— 把 useD4PriceWriteback.ts 的 `D4_2_ROWS_KEY = 'D4-2-rows'` 改成 'D4-X-rows'
                        → 写回落错 key，接线测试读不到标记 → d4PriceWritebackLinkage 必红
  M3  行派生依赖改空   —— 把 useD4Adjudication.ts 的 crossSheetMainRows 源改成空对象
                        → D4-2 产品行不再派生进 D4-1 → d4AdjudicationRowLinkage Property1 必红

铁律：磁盘真相经 open(encoding='utf-8') 读；锚点单行（CRLF 安全）且命中 == 1；
finally 里必还原（防污染工作树）。

用法：
  python backend/scripts/diagnose/mutate_d4_linkage_guards.py --check-anchors
  python backend/scripts/diagnose/mutate_d4_linkage_guards.py --apply
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # …/GT_plan
FE = ROOT / "audit-platform/frontend"
COMPOSABLES = FE / "src/components/workpaper/composables"
WRITEBACK = COMPOSABLES / "useD4PriceWriteback.ts"
ADJUDICATION = COMPOSABLES / "useD4Adjudication.ts"
ENVPATCH = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@dataclass(frozen=True)
class Case:
    id: str
    file: Path
    anchor: str
    replacement: str
    # 期望被打红的守卫 spec 文件名（vitest 输出的 FAIL 行里必须出现）
    wants: tuple[str, ...]
    requirement: str


CASES = [
    Case(
        id="M1-remove-receiver",
        file=WRITEBACK,
        anchor="  eventBus.on('d4:price-abnormal', handler as any)",
        replacement="  // <MUTATED: removed receiver> // eventBus.on('d4:price-abnormal', handler as any)",
        wants=("d4NoDeadEvent.spec.ts", "d4PriceWritebackLinkage.spec.ts"),
        requirement="6.2 (接收端真接线)",
    ),
    Case(
        id="M2-wrong-target-key",
        file=WRITEBACK,
        anchor="const D4_2_ROWS_KEY = 'D4-2-rows'",
        replacement="const D4_2_ROWS_KEY = 'D4-X-rows'  // <MUTATED: wrong target key>",
        wants=("d4PriceWritebackLinkage.spec.ts",),
        requirement="4.1/4.2 (回写落对 key)",
    ),
    Case(
        id="M3-empty-crosssheet-derive",
        file=ADJUDICATION,
        anchor="    Object.entries(mainRevenueByProduct.value).map(([product, agg]) =>",
        replacement="    Object.entries({} as Record<string, {current:number;prior:number}>).map(([product, agg]) =>  // <MUTATED: empty derive>",
        wants=("d4AdjudicationRowLinkage.spec.ts",),
        requirement="1.1 (Property 1 行派生)",
    ),
]


def _read(p: Path) -> str:
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def check_anchors() -> int:
    bad = 0
    for case in CASES:
        n = _read(case.file).count(case.anchor)
        status = "OK" if n == 1 else "ANCHOR-MISS"
        if n != 1:
            bad += 1
        print(f"  [{status}] {case.id} (n={n})  <- {case.file.name}")
    print(f"\nANCHOR-MISS: {bad}/{len(CASES)}")
    return 1 if bad else 0


def _run_guard(wants: tuple[str, ...]) -> tuple[int, str]:
    """跑相关 vitest 守卫（按 spec 文件名过滤）。"""
    args = ["npx", "vitest", "run", *[f"src/components/workpaper/composables/__tests__/{w}" for w in wants], "--reporter=dot"]
    proc = subprocess.run(
        args, cwd=str(FE), capture_output=True, env=ENVPATCH, shell=True,
    )
    return proc.returncode, (proc.stdout.decode("utf-8", errors="replace") + proc.stderr.decode("utf-8", errors="replace"))


def classify(case: Case) -> str:
    text = _read(case.file)
    n = text.count(case.anchor)
    if n != 1:
        return f"{case.id}: ANCHOR-MISS (n={n})"
    new_text = text.replace(case.anchor, case.replacement, 1)
    if new_text == text or new_text.count(case.anchor) != 0:
        return f"{case.id}: ANCHOR-MISS (replace no-op)"

    backup = case.file.with_suffix(case.file.suffix + ".mutbak")
    shutil.copy2(case.file, backup)
    try:
        with open(case.file, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_text)
        rc, out = _run_guard(case.wants)
        if rc == 0:
            return f"{case.id}: GREEN (guard defect — Req {case.requirement})"
        # 打红：确认失败输出里出现了预期守卫文件名
        hit = [w for w in case.wants if w in out]
        if hit:
            return f"{case.id}: RED (caught by {hit})"
        return f"{case.id}: WRONG-TEST (rc={rc}, none of {list(case.wants)} in output)"
    finally:
        shutil.copy2(backup, case.file)
        backup.unlink(missing_ok=True)


def apply_all() -> int:
    print("变异四态判定：")
    bad = 0
    for case in CASES:
        result = classify(case)
        print(f"  {result}")
        if ": RED" not in result:
            bad += 1
    print(f"\n非 RED（需处理）: {bad}/{len(CASES)}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.check_anchors:
        return check_anchors()
    if args.apply:
        return apply_all()
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
