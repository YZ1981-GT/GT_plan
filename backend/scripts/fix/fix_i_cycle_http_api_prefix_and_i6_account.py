"""修复 I 循环两类叠加缺陷：`http.*` 缺 `/api` 前缀（14 处 404）+ I6 取错科目（6602 管理费用）。

spec: i-cycle-extraction-formula-and-disclosure-closure Task 24 补测轮

## 缺陷 A：`http.*` 缺 `/api` 前缀 ⇒ 全部 404 静默失效

`audit-platform/frontend/src/utils/http.ts` 的 `baseURL: '/'`
⇒ ``http.get(`/projects/${pid}/trial-balance`)`` 实际请求 `/projects/...`，后端无此路由。
后端真实路由一律 `/api/**`（`main.py` 挂载 prefix）。全库正确调用点写的都是
``api.get('/api/workpapers/…')``。

受影响的 I 循环能力（全部包在 `try{}catch{}` 或 `_silent: true` 里 ⇒ 无任何报错）：

* **TB 自动取数**   `/projects/{pid}/trial-balance` —— I1/I3/I4/I6 主入口 + useI5FormData
                    + I2TabWorkHourCheck + useI2Analysis
* **selfLoad 自加载** `/workpapers/{wpId}/render-config` —— I1/I2/I3/I4/I6 主入口 + useI5FormData
* **回写试算表**    `/workpapers/{wpId}/writeback-trial-balance` —— I2TabAdjudication

与本 spec 首轮修的 `checklist-responses`（9 处）同源同因。

## 缺陷 B：I6 取错科目族（6602 管理费用 → 6604 研发费用）

``GtI6ResearchDevelopmentExpense.vue`` 的 `_loadTbData()`::

    params: { account_prefix: '6602' }      # 6602 = 管理费用（全库借方 6.24 亿）
    if (code.startsWith('6602')) { … }

后端**早已纠正**并留了两处注释：

* `four_table/i_cycle_accounts.py:22`
  「I6 ``6602`` → 6602 是**管理费用**（全库借方 6.24 亿）；研发费用是 ``6604`` → 数字完全错」
* `wp_render_strategies/_i6_research_development_expense.py:5`
  「已按 `report_config` 的 `IS-006` = ``TB('6604','本期发生额')`` 纠正」
* `iCycleAccountScope.I_CYCLE_ACCOUNT_SPECS.I6` 的 `fallback: ['6604']`

前端主入口是**漏同步的第三处真源**。

🔴 **A 与 B 必须同时修**：只修 A 会让 I6 从「恒 0」变成「取 6.24 亿管理费用」——
比原状更危险（fail-open 掩盖接线错误的典型：第一个缺陷掩盖了第二个）。

## 不改的两处（避免误改业务语义，只登记）

* `I2TabWorkHourCheck.vue` 的 `account_prefix: '6602'` —— I2 是开发支出(1704)，
  工时检查取 6602 可能意在「计入管理费用的研发人员薪酬」，需业务确认后再改。
* `useI2Analysis.ts` 的 `account_prefix: '6001'` —— 营业收入，I2 研发投入占收入比分析用，正确。
* K9 域的 `unadjusted6602` / `audited6602` / `account_prefix:'6602'` —— **K9 就是管理费用，正确**。

用法::

    python backend/scripts/fix/fix_i_cycle_http_api_prefix_and_i6_account.py --check
    python backend/scripts/fix/fix_i_cycle_http_api_prefix_and_i6_account.py
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_WP = _ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
assert _WP.is_dir(), f"workpaper dir missing: {_WP}"

#: 缺陷 A 的作用域（I 循环主入口 + I 循环 composable + i1~i6 子目录）
_A_FILES = [
    "GtI1IntangibleAssets.vue",
    "GtI2DevelopmentExpenditure.vue",
    "GtI3Goodwill.vue",
    "GtI4LongTermPrepaid.vue",
    "GtI5OtherNoncurrentAssets.vue",
    "GtI6ResearchDevelopmentExpense.vue",
    "composables/useI5FormData.ts",
    "composables/useI2Analysis.ts",
    "i2/core/I2TabAdjudication.vue",
    "i2/inspection/I2TabWorkHourCheck.vue",
]

#: `http.get(`/xxx` → `http.get(`/api/xxx`（只补前缀，不动路径其余部分）
_A_PAT = re.compile(r"(http\.(?:get|post|put|patch|delete)\(`)/(?!api/)")
_A_REPL = r"\1/api/"

#: 缺陷 B：仅 GtI6 主入口，仅这两处字面量（字段名 unadjusted6602 属可读性，另行处理）
_B_FILE = "GtI6ResearchDevelopmentExpense.vue"
_B_PAIRS = [
    ("params: { account_prefix: '6602' },", "params: { account_prefix: '6604' },"),
    ("if (code.startsWith('6602')) {", "if (code.startsWith('6604')) {"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    a_total = 0
    a_touched: list[tuple[str, int]] = []
    problems: list[str] = []

    # ── 缺陷 A ────────────────────────────────────────────────────────────
    for rel in _A_FILES:
        p = _WP / rel
        if not p.is_file():
            problems.append(f"[A] 文件不存在: {rel}")
            continue
        text = p.read_text(encoding="utf-8")
        n = len(_A_PAT.findall(text))
        if not n:
            continue
        a_total += n
        a_touched.append((rel, n))
        if args.check:
            print(f"  [A] 待修 {n} 处  {rel}")
            continue
        new = _A_PAT.sub(_A_REPL, text)
        p.write_text(new, encoding="utf-8")
        if _A_PAT.search(p.read_text(encoding="utf-8")):
            problems.append(f"[A] 写入后仍有裸路径: {rel}")
        print(f"  [A] FIXED {n} 处  {rel}")

    # ── 缺陷 B ────────────────────────────────────────────────────────────
    b_total = 0
    pb = _WP / _B_FILE
    if not pb.is_file():
        problems.append(f"[B] 文件不存在: {_B_FILE}")
    else:
        text = pb.read_text(encoding="utf-8")
        for old, new in _B_PAIRS:
            cnt = text.count(old)
            if cnt == 0:
                if text.count(new) >= 1:
                    print(f"  [B] OK(已修)  {old[:44]}…")
                else:
                    problems.append(f"[B] 锚点消失且未见目标形态: {old[:60]}")
                continue
            if cnt != 1:
                problems.append(f"[B] 锚点命中 {cnt} 次（期望 1）: {old[:60]}")
                continue
            b_total += 1
            if args.check:
                print(f"  [B] 待修  {old[:44]}… → 6604")
                continue
            text = text.replace(old, new, 1)
        if not args.check and b_total:
            pb.write_text(text, encoding="utf-8")
            verify = pb.read_text(encoding="utf-8")
            for old, new in _B_PAIRS:
                if old in verify:
                    problems.append(f"[B] 写入后旧形态仍在: {old[:60]}")
                if new not in verify:
                    problems.append(f"[B] 写入后新形态缺失: {new[:60]}")
            print(f"  [B] FIXED {b_total} 处  {_B_FILE}（6602 管理费用 → 6604 研发费用）")

    print("\n===== 汇总 =====")
    verb = "待修" if args.check else "已修"
    print(f"A（缺 /api 前缀）{verb} {a_total} 处 / {len(a_touched)} 文件")
    for rel, n in a_touched:
        print(f"    {n} 处  {rel}")
    print(f"B（I6 科目 6602→6604）{verb} {b_total} 处")
    if problems:
        print(f"\n异常 {len(problems)} 条：")
        for x in problems:
            print(f"  - {x}")
        return 1
    if a_total == 0 and b_total == 0:
        print("无待修（幂等）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
