"""变异检验：高级查询「年度默认值」修复（前端 vitest 守卫）。

用法::

    python backend/scripts/check/mutate_custom_query_year_default.py
    python backend/scripts/check/mutate_custom_query_year_default.py --check-anchors

背景：`CustomQueryTab.vue` 的年度输入框固定初始化为 ``new Date().getFullYear()``（日历
当年），而审计做的是**上一年度**报表 ⇒ 2026 年打开页面默认查 2026，四表里只有 2025
的数据，任何查询恒返回 0 行且页面不提示原因。现改为跟随项目 ``audit_year``（后端
``resolve_project_audit_year`` 下发），并给 0 行加上含年度的可诊断提示。

harness 沿用 ``mutate_common`` 的读写与判定四态，但守卫跑的是 vitest（不是 pytest），
故自带 runner。
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from mutate_common import REPO, Mutation, check_group_anchors, read_source, write_source

FRONTEND = REPO / "audit-platform" / "frontend"
GUARD = "src/components/custom-query/__tests__/advancedQueryFrontend.spec.ts"
TAB = "audit-platform/frontend/src/components/template-library/CustomQueryTab.vue"

YEAR_MUTATIONS: tuple[tuple[Mutation, str], ...] = (
    (
        Mutation(
            "Y01",
            TAB,
            "  year: defaultAuditYear(),",
            "  year: new Date().getFullYear(),  // 变异：回到日历当年",
            "初始年度不是日历当年",
            "年度初始值退回日历当年（四表无当年数据 ⇒ 恒 0 行）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "Y02",
            TAB,
            "  return new Date().getFullYear() - 1\n}",
            "  return new Date().getFullYear()  // 变异\n}",
            "初始年度不是日历当年",
            "兜底年度退回日历当年",
        ),
        GUARD,
    ),
    (
        Mutation(
            "Y03",
            TAB,
            "  formCtx.value.year = proj?.audit_year ?? defaultAuditYear()",
            "  formCtx.value.year = defaultAuditYear()  // 变异：忽略项目审计年度",
            "选中项目后年度跟随该项目的 audit_year",
            "年度不再跟随所选项目的 audit_year",
        ),
        GUARD,
    ),
    (
        Mutation(
            "Y04",
            TAB,
            "      audit_year: p.audit_year ?? p.auditYear ?? null,\n",
            "",
            "选中项目后年度跟随该项目的 audit_year",
            "项目列表不再映射 audit_year（下发了却不读 = 死数据）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "Y05",
            TAB,
            "    if (formCtx.value.project_id) syncYearToProject(formCtx.value.project_id)",
            "    // 变异：列表加载后不再对齐已选项目年度",
            "列表加载完成时会把已选项目的年度对齐",
            "模板恢复场景下年度不对齐（先设 project_id 再拉列表）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "Y06",
            TAB,
            '        emptyHint.value = `年度 ${formCtx.value.year} 下没有匹配数据`',
            "        emptyHint.value = ''  // 变异：0 行不再提示原因",
            "0 行结果给出含年度的可诊断提示",
            "0 行静默返回（缺陷难以被发现的根因）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "Y07",
            TAB,
            "      } else {\n        emptyHint.value = ''\n        ElMessage.success(",
            "      } else {\n        ElMessage.success(",
            "有结果时清空空态提示",
            "有结果时不清空空态提示（上一次的 0 行提示粘住）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "Y08",
            TAB,
            '            @change="onProjectChange"\n',
            "",
            "从项目下拉发出 change 后年度跟随",
            "模板漏接 @change（函数对但永不触发 —— 典型未接线假绿）",
        ),
        GUARD,
    ),
)

LABEL = "年度默认值"


def _run_vitest(guard: str, expect_test: str) -> tuple[bool, bool]:
    proc = subprocess.run(
        ["npx", "vitest", "run", guard, "--reporter=dot"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    # vitest 的失败行形如 " FAIL  <file> > <describe> > <test>"
    expected_failed = any(
        "FAIL" in line and expect_test in line for line in out.splitlines()
    )
    overall_failed = proc.returncode != 0 or " failed" in out
    return overall_failed, expected_failed


def run_year_mutations() -> int:
    verdicts: dict[str, str] = {}
    base_failed, _ = _run_vitest(GUARD, "__none__")
    if base_failed:
        print("前端守卫基线未全绿，变异无意义")
        return 1
    for m, guard in YEAR_MUTATIONS:
        original = read_source(m.path)
        if original.count(m.old) != 1:
            verdicts[m.mid] = "ANCHOR-MISS"
            print(f"{m.mid}  ANCHOR-MISS  {m.why}")
            continue
        try:
            write_source(m.path, original.replace(m.old, m.new, 1))
            overall, expected = _run_vitest(guard, m.expect_test)
            verdict = "GREEN" if not overall else ("RED" if expected else "WRONG-TEST")
        finally:
            write_source(m.path, original)
        verdicts[m.mid] = verdict
        print(f"{m.mid}  {verdict:<12} {m.why}")
    counts = {v: sum(1 for x in verdicts.values() if x == v) for v in set(verdicts.values())}
    print(f"\n{LABEL}判定汇总：" + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0 if counts.get("RED", 0) == len(YEAR_MUTATIONS) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-anchors", action="store_true", help="只校验锚点，不改文件")
    args = parser.parse_args()
    if args.check_anchors:
        return check_group_anchors(YEAR_MUTATIONS, LABEL)
    return run_year_mutations()


if __name__ == "__main__":
    sys.exit(main())
