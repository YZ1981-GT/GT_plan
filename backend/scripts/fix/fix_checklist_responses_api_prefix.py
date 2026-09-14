"""修复 `checklist-responses` 调用缺 `/api` 前缀导致的 404（审计说明/结论静默丢失）。

spec: i-cycle-extraction-formula-and-disclosure-closure Task 24（浏览器实测发现）

## 缺陷

浏览器实测（重药控股安徽_2025 / I1 上市披露 tab，装 XHR 拦截器）抓到::

    PUT /workpapers/{uuid}/checklist-responses  -> 404   × 210
    POST /api/projects/{uuid}/disclosure-notes/sync-from-workpaper -> 409 × 14

后者是 `_guard_standard_matches_project` 守卫（预期行为，项目 entity_type=soe 却推 listed）。
**前者是真缺陷**：URL 少了 `/api` 前缀。

判据链（三重实证）：

1. `audit-platform/frontend/src/utils/http.ts` 的 `baseURL: '/'`
   ⇒ `http.put('/workpapers/…')` 实际请求 `/workpapers/…`，后端无此路由。
2. 同一批文件里的附注同步却写的是 `/api/projects/${…}/disclosure-notes/sync-from-workpaper`
   （带 `/api`）⇒ 是遗漏而非设计。
3. 全库其余 40+ 个 `checklist-responses` 调用点一律 `api.get/put('/api/workpapers/…')`。

## 后果（比白屏隐蔽）

`checklist_responses` 表存的是**审计说明与结论**。调用点全部包在
``try { … } catch { /* silent */ }`` 里 ⇒ 审计师填完说明/结论，点保存无任何报错，
**数据从未落库**。实测印证：两个测试项目的 I 循环底稿 `checklist_responses` 合计仅 **1 行**。

## 修复范围（8 处 / 8 个文件）

I 循环（本 spec 范围，6 个文件 7 处）：
  · GtI1IntangibleAssets.vue          · GtI2DevelopmentExpenditure.vue
  · GtI3Goodwill.vue                  · GtI4LongTermPrepaid.vue
  · composables/useI5FormData.ts      · GtI6ResearchDevelopmentExpense.vue（2 处）

H3 循环（跨域同源缺陷，一并修）：
  · composables/h3MortgageReconcile.ts   · composables/h3TransferReconcile.ts
  （这两处用 `api from '@/services/apiProxy'`，与正确调用点同一客户端，同样需 `/api`）

## 不受影响

`__tests__/useB22BControlMatrix.spec.ts` 里的
``url.includes('/workpapers/b22a-wp/checklist-responses')`` 是**字面量**断言，
本脚本正则只匹配模板插值 `${…}`，故天然不命中；且 `/api/workpapers/…` 仍满足该
`includes` 判断，测试不会因本次修复而红。

用法::

    python backend/scripts/fix/fix_checklist_responses_api_prefix.py --check
    python backend/scripts/fix/fix_checklist_responses_api_prefix.py
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "audit-platform" / "frontend" / "src"
assert _SRC.is_dir(), f"frontend src missing: {_SRC}"

#: 只匹配模板插值形态的裸路径（排除测试里的字面量断言）
_BAD = re.compile(r"`/workpapers/(\$\{[^}]+\})/checklist-responses`")
_GOOD_TMPL = "`/api/workpapers/{}/checklist-responses`"

#: 反向自检：修复后不得再有裸路径，且 `/api/` 版本必须出现
_GOOD_RE = re.compile(r"`/api/workpapers/\$\{[^}]+\}/checklist-responses`")


def _iter_files():
    for p in sorted(_SRC.rglob("*")):
        if p.suffix not in (".ts", ".vue"):
            continue
        if "__tests__" in p.parts or p.name.endswith(".spec.ts"):
            continue
        yield p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只报告，不写文件")
    args = ap.parse_args()

    total_hits = 0
    touched: list[tuple[str, int]] = []
    problems: list[str] = []

    for p in _iter_files():
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits = _BAD.findall(text)
        if not hits:
            continue
        rel = str(p.relative_to(_ROOT)).replace("\\", "/")
        total_hits += len(hits)
        touched.append((rel, len(hits)))

        if args.check:
            print(f"  待修 {len(hits)} 处  {rel}")
            continue

        new_text = _BAD.sub(lambda m: _GOOD_TMPL.format(m.group(1)), text)
        p.write_text(new_text, encoding="utf-8")

        # 反向自检：裸路径必须消失、/api 版本必须出现
        verify = p.read_text(encoding="utf-8")
        if _BAD.search(verify):
            problems.append(f"{rel}: 写入后裸路径仍存在")
        if not _GOOD_RE.search(verify):
            problems.append(f"{rel}: 写入后未见 /api 版本")
        print(f"  FIXED {len(hits)} 处  {rel}")

    print("\n===== 汇总 =====")
    verb = "待修" if args.check else "已修"
    print(f"{verb} {total_hits} 处，涉及 {len(touched)} 个文件")
    for rel, n in touched:
        cycle = "I 循环" if re.search(r"/(GtI[1-6]|useI[1-6])", rel) else "其他循环"
        print(f"  [{cycle}] {n} 处  {rel}")
    if problems:
        print(f"\n异常 {len(problems)} 条：")
        for x in problems:
            print(f"  - {x}")
        return 1
    if total_hits == 0:
        print("无待修（幂等）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
