"""I 循环零回归验证（Task 22 / Requirements 11.5）。只读，不改任何文件。

## 判据设计：为什么不是「跑改动前 vs 改动后」

Task 22 原文要求「施加改动前跑一次收集失败集合 → 施加改动 → 再跑一次求差集」，
并**禁用 `git stash` / HEAD-swap**（memory 已记：那两种做法会把并发会话的未提交
改动一起卷走，且 HEAD-swap 后 `.pyc` / vite 缓存不同步会造出假绿）。

诚实地说：**本 spec 的改动已经施加完了，"改动前"那一次跑不回来了**。
用 stash/swap 造出来的「改动前」也不是真的改动前（工作树里还有 3 个并发会话的改动）。

替代判据（可复跑、且比一次性对照更有长期价值）：

1. **改动域判据（硬性，红则失败）** —— 本 spec 改动波及的 I 循环守卫，
   失败数必须为 **0**。这是「本 spec 是否引入回归」的直接判据。
2. **改动域外判据（软性，只报告）** —— 其余失败必须 ⊆ 登记的
   :data:`KNOWN_FOREIGN_FAILURES`（并发会话正在写的 K/L 域）。
   出现登记外的新失败会**列出来**供人工判断，但不判失败 ——
   因为无法区分「本 spec 引入」与「并发会话刚写坏」，谎称能区分才是假绿。
3. **改动文件存在性** —— 逐个 `Path.exists()`，防「改了个不存在的路径」
   或「文件被并发会话删掉」。
4. **Vite transform** —— 调平台既有的 `vite_transform_smoke.mjs`（全树，
   改动文件是其子集），抓 Volar/vitest 查不出的模板级崩溃。

用法::

    python backend/scripts/diagnose/verify_i_cycle_zero_regression.py
    python backend/scripts/diagnose/verify_i_cycle_zero_regression.py --skip-vite
    python backend/scripts/diagnose/verify_i_cycle_zero_regression.py --files-only

spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/ Task 22
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_FE = _ROOT / "audit-platform" / "frontend"

# ─────────────────────────────────────────────────────────────────────────────
# 本 spec 的改动文件（显式登记 —— 工作树长期不干净，`git status` 区分不出归属）
# ─────────────────────────────────────────────────────────────────────────────

#: 后端改动/新增
BACKEND_CHANGED: tuple[str, ...] = (
    # 守卫
    "backend/tests/test_note_i_cycle_structure.py",       # sys.modules 修复 + P18/P19 + Task19 + P15 补强
    "backend/tests/four_table/test_i5_absent_account.py",  # Property 3 补强 8 条
    "backend/tests/test_i_cycle_ci_wiring.py",             # 新建（Task 21）
    # 生产代码
    "backend/app/services/four_table/i_cycle_source_defects.py",  # 新建（Task 19）
    "backend/app/data/wp_code_overrides.json",                    # 加 1 条 sheet skip
    # 工具
    "backend/scripts/diagnose/mutate_i_cycle_guards.py",           # 新建（Task 20）
    "backend/scripts/diagnose/verify_i_cycle_zero_regression.py",  # 本文件（Task 22）
    # CI
    ".github/workflows/governance-checks.yml",
)

#: 前端改动/新增（相对仓库根）
_FE_PREFIX = "audit-platform/frontend/src/components/workpaper"
FRONTEND_CHANGED: tuple[str, ...] = (
    # 新建
    f"{_FE_PREFIX}/composables/iCycleAdjudicationSeed.ts",
    f"{_FE_PREFIX}/composables/useICycleAdjudicationSeeding.ts",
    f"{_FE_PREFIX}/composables/__tests__/iCycleAdjudicationSeed.spec.ts",
    # 改动
    f"{_FE_PREFIX}/composables/useICycleFourTableSource.ts",
    f"{_FE_PREFIX}/composables/__tests__/iCycleAccountScope.spec.ts",
    f"{_FE_PREFIX}/composables/__tests__/iDisclosureColumns.spec.ts",
    # 六个审定表（接 seeding + 科目码收敛 + fmtAmount 收敛）
    f"{_FE_PREFIX}/i1/core/I1TabAdjudication.vue",
    f"{_FE_PREFIX}/i2/core/I2TabAdjudication.vue",
    f"{_FE_PREFIX}/i3/core/I3TabAdjudication.vue",
    f"{_FE_PREFIX}/i4/core/I4TabAdjudication.vue",
    f"{_FE_PREFIX}/i5/core/I5TabAdjudication.vue",
    f"{_FE_PREFIX}/i6/core/I6TabAdjudication.vue",
    # fmtAmount 收敛（明细表 / 截止测试 / 抽样表）
    f"{_FE_PREFIX}/i1/core/I1TabDetail.vue",
    f"{_FE_PREFIX}/i2/core/I2TabDetail.vue",
    f"{_FE_PREFIX}/i2/cutoff/I2TabCutoffBackward.vue",
    f"{_FE_PREFIX}/i2/cutoff/I2TabCutoffForward.vue",
    f"{_FE_PREFIX}/i2/cutoff/I2CutoffSampleTable.vue",
    f"{_FE_PREFIX}/i3/core/I3TabDetail.vue",
    f"{_FE_PREFIX}/i4/core/I4TabDetail.vue",
    f"{_FE_PREFIX}/i5/core/I5TabDetail.vue",
    f"{_FE_PREFIX}/i6/core/I6TabDetail.vue",
    f"{_FE_PREFIX}/i6/cutoff/I6TabCutoffBackward.vue",
    f"{_FE_PREFIX}/i6/cutoff/I6TabCutoffForward.vue",
    # 披露 Tab 的 inject 补齐
    f"{_FE_PREFIX}/i3/core/I3TabDisclosureListed.vue",
    f"{_FE_PREFIX}/i3/core/I3TabDisclosureSoe.vue",
    f"{_FE_PREFIX}/i5/core/I5TabDisclosureListed.vue",
    f"{_FE_PREFIX}/i5/core/I5TabDisclosureSoe.vue",
    f"{_FE_PREFIX}/i6/core/I6TabDisclosureListed.vue",
    f"{_FE_PREFIX}/i6/core/I6TabDisclosureSoe.vue",
)

# ─────────────────────────────────────────────────────────────────────────────
# 测试范围
# ─────────────────────────────────────────────────────────────────────────────

#: 后端：`four_table/` 全量 + `-k` 表达式收 I 循环相关（参数用列表传，不经 shell）
BACKEND_PYTEST_ARGS: tuple[str, ...] = (
    "backend/tests/four_table/",
    "backend/tests/test_note_i_cycle_structure.py",
    "backend/tests/test_i_cycle_formula_presets.py",
    "backend/tests/test_i_cycle_ci_wiring.py",
)

#: 前端：vitest 位置参数是**子串过滤器**，`iCycle` 等前缀会命中一批 spec
FRONTEND_VITEST_FILTERS: tuple[str, ...] = (
    "iCycle", "iDisclosureColumns", "i1", "i2", "i3", "i4", "i5", "i6",
)

#: 判定「属于本 spec 改动域」的失败文件名特征（小写子串）
OWN_DOMAIN_MARKERS: tuple[str, ...] = (
    "icycle", "idisclosurecolumns", "i1", "i2", "i3", "i4", "i5", "i6",
    "note_i_cycle", "i_cycle",
)

#: 🔴 **登记的改动域外已知失败**（并发会话正在写的域，非本 spec 引入）。
#:
#: 2026-08-12 多次实测稳定在这批：K13/K10 公式引擎重构中（`parseNum is not defined`）、
#: L2/L4 披露接线重构中。数值会随对方进度浮动，故只登记**文件名**不登记条数。
KNOWN_FOREIGN_FAILURES: dict[str, str] = {
    "useK13FormulaEngine.test.ts": "K 循环公式引擎重构中（parseNum 未定义）",
    "useK10FormulaEngine.spec.ts": "同上",
    "useK10FormulaEngine.pbt.spec.ts": "同上",
    "useK12Adjustment.spec.ts": "K12 调整分录重构中",
    "l2l4DisclosureWiring.spec.ts": "L2/L4 披露接线重构中",
    "l4-bonds-payable.integration.test.ts": "同上",
    "noteSectionMapNamingCoverage.spec.ts": "平台级命名覆盖面（随各 spec 新增章节浮动）",
    "hgDisclosureColumns.spec.ts": "H/G 列结构（h-cycle spec 在跑）",
    "useF3Integration.spec.ts": "F 循环集成（f-cycle spec 在跑）",
    "useF5Integration.spec.ts": "同上",
    "g7NoteSubtableContract.spec.ts": "g7-column-alignment spec 在跑",
    "test_k_cycle_formula_presets.py": "K 循环公式预设（k-cycle spec 在跑）",
}


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _is_own_domain(name: str) -> bool:
    low = name.lower()
    return any(m in low for m in OWN_DOMAIN_MARKERS)


# ─────────────────────────────────────────────────────────────────────────────
# ① 改动文件存在性
# ─────────────────────────────────────────────────────────────────────────────


def check_files() -> int:
    print("=" * 78)
    print("① 改动文件存在性（逐个 Path.exists）")
    print("=" * 78)
    missing: list[str] = []
    for rel in (*BACKEND_CHANGED, *FRONTEND_CHANGED):
        if not (_ROOT / rel).exists():
            missing.append(rel)
    total = len(BACKEND_CHANGED) + len(FRONTEND_CHANGED)
    print(f"  登记 {total} 个（后端 {len(BACKEND_CHANGED)} / 前端 {len(FRONTEND_CHANGED)}）")
    if missing:
        for m in missing:
            print(f"  🔴 缺失 {m}")
    else:
        print("  OK 全部存在")
    return len(missing)


# ─────────────────────────────────────────────────────────────────────────────
# ② 后端
# ─────────────────────────────────────────────────────────────────────────────


def run_backend() -> tuple[list[str], str]:
    print()
    print("=" * 78)
    print("② 后端（four_table 全量 + I 循环守卫）")
    print("=" * 78)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *BACKEND_PYTEST_ARGS, "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=_env(),
    )
    failed = re.findall(r"^FAILED\s+(\S+)::(\S+)", proc.stdout, re.MULTILINE)
    summary = next(
        (ln.strip() for ln in reversed(proc.stdout.splitlines())
         if re.search(r"passed|failed|error", ln)),
        "(无汇总行)",
    )
    print(f"  {summary}")
    names = [f"{Path(f).name}::{t}" for f, t in failed]
    return names, summary


# ─────────────────────────────────────────────────────────────────────────────
# ③ 前端
# ─────────────────────────────────────────────────────────────────────────────


def run_frontend() -> tuple[list[str], str]:
    print()
    print("=" * 78)
    print("③ 前端（vitest 子串过滤：iCycle / i1~i6 / iDisclosureColumns）")
    print("=" * 78)
    out = _FE / ".vitest-i-cycle-zero-regression.json"
    subprocess.run(
        ["npx.cmd", "vitest", "run", *FRONTEND_VITEST_FILTERS,
         "--reporter=json", f"--outputFile={out.name}"],
        cwd=str(_FE), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=_env(),
    )
    if not out.exists():
        print("  🔴 未生成 JSON（vitest 未产出报告）")
        return ["<vitest 无报告>"], "(无)"
    data = json.loads(out.read_text(encoding="utf-8"))
    failed: list[str] = []
    for res in data.get("testResults", []):
        fname = Path(res.get("name") or "?").name
        for a in res.get("assertionResults", []):
            if a.get("status") == "failed":
                failed.append(f"{fname}::{a.get('fullName') or a.get('title')}")
    summary = (
        f"{data.get('numTotalTests')} tests / {data.get('numFailedTests')} failed"
        f" / {data.get('numFailedTestSuites')} files failed"
    )
    print(f"  {summary}")
    for _ in range(10):
        try:
            out.unlink(missing_ok=True)
            break
        except PermissionError:
            time.sleep(0.3)
    return failed, summary


# ─────────────────────────────────────────────────────────────────────────────
# ④ Vite transform
# ─────────────────────────────────────────────────────────────────────────────


def run_vite() -> int:
    print()
    print("=" * 78)
    print("④ Vite transform 冒烟（平台既有全树脚本；改动文件是其子集）")
    print("=" * 78)
    script = _ROOT / "backend" / "scripts" / "check" / "vite_transform_smoke.mjs"
    if not script.exists():
        print(f"  🔴 {script.relative_to(_ROOT)} 不存在")
        return 1
    proc = subprocess.run(
        ["node", str(script)],
        cwd=str(_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=_env(),
    )
    tail = [ln for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()][-6:]
    for ln in tail:
        print(f"  {ln[:140]}")
    # 只关心改动文件是否出现在崩溃清单里
    crashed = [
        rel for rel in FRONTEND_CHANGED
        if Path(rel).name in proc.stdout and "FAIL" in proc.stdout
    ]
    if crashed:
        print(f"  🔴 本 spec 改动文件出现在 transform 崩溃清单：{crashed}")
        return len(crashed)
    print(f"  OK 本 spec 的 {len(FRONTEND_CHANGED)} 个前端改动文件均未出现 transform 崩溃")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# 汇总
# ─────────────────────────────────────────────────────────────────────────────


def classify(failed: list[str], label: str) -> int:
    own = [f for f in failed if _is_own_domain(f.split("::")[0])]
    foreign = [f for f in failed if f not in own]
    unregistered = [f for f in foreign if f.split("::")[0] not in KNOWN_FOREIGN_FAILURES]

    print()
    print(f"  ── {label} 失败分类 ──")
    print(f"     改动域（I 循环）失败 = {len(own)}")
    for f in own[:20]:
        print(f"       🔴 {f}")
    by_file: dict[str, int] = {}
    for f in foreign:
        by_file[f.split("::")[0]] = by_file.get(f.split("::")[0], 0) + 1
    print(f"     改动域外失败 = {len(foreign)}（{len(by_file)} 个文件）")
    for name, n in sorted(by_file.items(), key=lambda kv: -kv[1]):
        tag = KNOWN_FOREIGN_FAILURES.get(name, "🔴 未登记")
        print(f"       {n:>4}  {name:<44} {tag}")
    if unregistered:
        print(f"     ⚠ 登记外的新失败 {len(unregistered)} 条 —— 需人工判断归属"
              f"（无法自动区分「本 spec 引入」与「并发会话刚写坏」）")
    return len(own)


def main() -> int:
    ap = argparse.ArgumentParser(description="I 循环零回归验证（只读）")
    ap.add_argument("--skip-vite", action="store_true", help="跳过 Vite transform（较慢）")
    ap.add_argument("--files-only", action="store_true", help="只查改动文件存在性")
    args = ap.parse_args()

    bad = check_files()
    if args.files_only:
        print(f"\n结论：改动文件缺失 {bad} 个")
        return 1 if bad else 0

    be_failed, be_sum = run_backend()
    fe_failed, fe_sum = run_frontend()

    own_be = classify(be_failed, "后端")
    own_fe = classify(fe_failed, "前端")

    vite_bad = 0 if args.skip_vite else run_vite()

    print()
    print("=" * 78)
    print("零回归结论")
    print("=" * 78)
    print(f"  后端：{be_sum}")
    print(f"  前端：{fe_sum}")
    print(f"  改动文件缺失            = {bad}")
    print(f"  改动域（I 循环）后端失败 = {own_be}")
    print(f"  改动域（I 循环）前端失败 = {own_fe}")
    print(f"  改动文件 transform 崩溃 = {vite_bad}"
          + ("（已跳过）" if args.skip_vite else ""))
    total = bad + own_be + own_fe + vite_bad
    print(f"\n  {'✅ 零回归成立' if total == 0 else f'🔴 存在 {total} 项问题'}")
    print("  注：改动域外失败不计入判据 —— 那是并发会话正在写的域，"
          "谎称能自动区分归属才是假绿")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
