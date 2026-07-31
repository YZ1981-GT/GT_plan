#!/usr/bin/env python
"""补齐 F1 预付款项的公式管理预设（幂等）。

改造前 `prefill_formula_mapping.json` 全库 210 条映射中 **F1 仅 1 条**
（`审定表F1-1`，5 个通用 cell：期初/未审/AJE/RJE/上年审定，全部只引用 `1123`）。
对比 F2 有 18 条、N1 的审定表块含 `WP()` 跨底稿取数 —— F1 缺：

1. 备抵科目 `1231-04 坏账准备-预付账款`（期初/期末）—— 两个披露表的「减：减值准备」行、
   上市②表「减值准备」列、国企逐段坏账准备列全靠手工，公式管理里查不到来源；
2. 借贷发生额（`本期借方` / `本期贷方`）—— F1-4 实质性分析要用；
3. 跨底稿取数 `WP('F1','明细表F1-2',…)` / `WP('F1','长期挂款检查表F1-5',…)`；
4. F1-2 明细表块（往来单位 `AUX('1123','客户',…)`）；
5. F1-4 实质性分析块（存货 `1401~1499` / 应付账款 `2202` / 存货采购）。

**两条硬约束**

- `preset_library.convert_prefill_presets()` 的 ``page_key = f"workpaper:{wp_code}"``
  **忽略 sheet** → 同一 wp_code 内 ``cell_ref`` 必须**全局唯一**，同名互相遮蔽。
- **F1-2 明细表块禁引 `WP()`** —— F1 的取数级联是 F1-2 → F1-1，明细再反引审定表即成环
  （与 N1-2 / K1-2 同款约束）。

科目口径依据（DB 只读实证 2026-07-31）：

- `BS-008 预付款项` 四个准则一律 ``TB('1123','期末余额')``（**不减备抵**）；
- 标准科目表有 ``1231-04 坏账准备-预付账款``（`direction='credit'`），
  故备抵必须写细分码 —— 写 ``TB('1231',…)`` 会把应收票据/应收账款/其他应收款的坏账
  一并算进 F1（实证项目 `0ec33ac9` 整个 `1231` 期末 28,464,225.16，其中 26,401,719.77 属应收账款）；
- 存货报表行是 ``BS-010 = SUM_TB('1401~1499','期末余额')``，**`1401` 是「材料采购」不是存货**
  （实证两个真实项目的 `1401` 均为空）；应付账款报表行是 ``BS-045 = TB('2202','期末余额')``。

Usage::

    python backend/scripts/fix/fix_f1_prefill_presets.py --dry-run
    python backend/scripts/fix/fix_f1_prefill_presets.py
    python backend/scripts/fix/fix_f1_prefill_presets.py --check

spec: .kiro/specs/f1-four-table-extraction-and-disclosure-alignment/ R5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
MAPPING_PATH = _BACKEND / "data" / "prefill_formula_mapping.json"

SHEET_ADJ = "审定表F1-1"
SHEET_DETAIL = "明细表F1-2"
SHEET_ANALYSIS = "实质性分析F1-4"

#: F1-1 审定表新增条目（cell_ref 在 workpaper:F1 内全局唯一）
ADJ_CELLS: list[dict[str, Any]] = [
    {
        "cell_ref": "坏账准备期初余额",
        "formula": "=TB('1231-04','期初余额')",
        "formula_type": "TB",
        "description": "坏账准备-预付账款期初余额（细分码；写 1231 宽口径会含应收账款坏账）",
    },
    {
        "cell_ref": "坏账准备期末未审数",
        "formula": "=TB('1231-04','期末余额')",
        "formula_type": "TB",
        "description": "坏账准备-预付账款期末余额（供两个披露表「减：减值准备」行取数）",
    },
    {
        "cell_ref": "本期借方发生额",
        "formula": "=TB('1123','本期借方')",
        "formula_type": "TB",
        "description": "预付款项本期借方发生额（新增预付；供 F1-4 借方发生额分析）",
    },
    {
        "cell_ref": "本期贷方发生额",
        "formula": "=TB('1123','本期贷方')",
        "formula_type": "TB",
        "description": "预付款项本期贷方发生额（转销/收回；供 F1-4 贷方发生额分析）",
    },
    {
        "cell_ref": "明细表期末审定合计",
        "formula": "=WP('F1','明细表F1-2','期末审定余额合计')",
        "formula_type": "WP",
        "description": "审定表按性质/账龄未审数来源 = F1-2 明细表期末审定余额合计",
    },
    {
        "cell_ref": "长期挂款审定合计",
        "formula": "=WP('F1','长期挂款检查表F1-5','审定余额合计')",
        "formula_type": "WP",
        "description": "账龄 1 年以上大额预付款项审定余额合计（← F1-5，供账龄行与披露②表勾稽）",
    },
]

#: F1-2 明细表块（**禁 WP()**，防 F1-1 ↔ F1-2 成环）
DETAIL_BLOCK: dict[str, Any] = {
    "wp_code": "F1",
    "wp_name": "预付账款明细表",
    "sheet": SHEET_DETAIL,
    "account_codes": ["1123"],
    "cells": [
        {
            "cell_ref": "明细期初余额",
            "formula": "=TB('1123','期初余额')",
            "formula_type": "TB",
            "description": "明细表期初未审余额合计核对数（与总账勾稽）",
        },
        {
            "cell_ref": "明细期末余额",
            "formula": "=TB('1123','期末余额')",
            "formula_type": "TB",
            "description": "明细表期末未审余额合计核对数（与总账勾稽）",
        },
        {
            "cell_ref": "明细往来单位期末余额",
            "formula": "=AUX('1123','客户','XX单位','期末余额')",
            "formula_type": "AUX",
            "description": (
                "按往来单位（辅助维度 `客户`）取某供应商期末余额 —— "
                "F1-2 逐行取数走「从辅助余额表导入」批量归集，本条供单户复核/覆盖"
            ),
        },
    ],
}

#: F1-4 实质性分析块（跨循环锚点同样按报表映射口径）
ANALYSIS_BLOCK: dict[str, Any] = {
    "wp_code": "F1",
    "wp_name": "预付账款实质性分析",
    "sheet": SHEET_ANALYSIS,
    "account_codes": ["1123", "1401~1499", "2202"],
    "cells": [
        {
            "cell_ref": "存货期末余额",
            "formula": "=TB_SUM('1401~1499','期末余额')",
            "formula_type": "TB_SUM",
            "description": (
                "存货期末账面价值（报表行 BS-010 口径）—— "
                "🔴 不能写 TB('1401')，1401 是「材料采购」不是存货合计"
            ),
        },
        {
            "cell_ref": "存货本期采购金额",
            "formula": "=TB_SUM('1401~1499','本期借方')",
            "formula_type": "TB_SUM",
            "description": "存货本期借方发生额（近似本期采购金额，供预付/采购占比分析）",
        },
        {
            "cell_ref": "应付账款期末余额",
            "formula": "=TB('2202','期末余额')",
            "formula_type": "TB",
            "description": "应付账款期末余额（报表行 BS-045）—— 与预付款项对同一供应商双向挂账核查",
        },
    ],
}


def _blocks(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return doc["mappings"]


def _find_block(doc: dict[str, Any], sheet: str) -> dict[str, Any] | None:
    for b in _blocks(doc):
        if b.get("wp_code") == "F1" and b.get("sheet") == sheet:
            return b
    return None


def _cell_refs(block: dict[str, Any]) -> set[str]:
    return {str(c.get("cell_ref") or "") for c in block.get("cells") or []}


def _all_f1_cell_refs(doc: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for b in _blocks(doc):
        if b.get("wp_code") != "F1":
            continue
        out.extend(str(c.get("cell_ref") or "") for c in b.get("cells") or [])
    return out


def apply(doc: dict[str, Any]) -> list[str]:
    changes: list[str] = []

    adj = _find_block(doc, SHEET_ADJ)
    if adj is None:
        changes.append(f"[FATAL] 缺 F1 {SHEET_ADJ} 块")
        return changes

    existing = _cell_refs(adj)
    added = [c for c in ADJ_CELLS if c["cell_ref"] not in existing]
    if added:
        adj.setdefault("cells", []).extend(json.loads(json.dumps(added, ensure_ascii=False)))
        changes.append(f"{SHEET_ADJ} 追加 {len(added)} 条：{'、'.join(c['cell_ref'] for c in added)}")

    want_codes = {"1123", "1231-04"}
    codes = adj.setdefault("account_codes", [])
    missing_codes = [c for c in sorted(want_codes) if c not in codes]
    if missing_codes:
        codes.extend(missing_codes)
        changes.append(f"{SHEET_ADJ}.account_codes 追加 {missing_codes}")

    for block in (DETAIL_BLOCK, ANALYSIS_BLOCK):
        sheet = block["sheet"]
        hit = _find_block(doc, sheet)
        if hit is None:
            # 插到 F1 既有块之后，保持同 wp_code 聚集
            idx = max(
                (i for i, b in enumerate(_blocks(doc)) if b.get("wp_code") == "F1"),
                default=len(_blocks(doc)) - 1,
            )
            _blocks(doc).insert(idx + 1, json.loads(json.dumps(block, ensure_ascii=False)))
            changes.append(f"新增块 {sheet}（{len(block['cells'])} 条）")
            continue
        existing = _cell_refs(hit)
        add = [c for c in block["cells"] if c["cell_ref"] not in existing]
        if add:
            hit.setdefault("cells", []).extend(json.loads(json.dumps(add, ensure_ascii=False)))
            changes.append(f"{sheet} 追加 {len(add)} 条")

    return changes


def validate(doc: dict[str, Any]) -> list[str]:
    errs: list[str] = []

    adj = _find_block(doc, SHEET_ADJ)
    if adj is None:
        return [f"缺 F1 {SHEET_ADJ} 块"]

    formulas = "\n".join(str(c.get("formula") or "") for c in adj.get("cells") or [])
    for want in (
        "TB('1231-04','期初余额')",
        "TB('1231-04','期末余额')",
        "TB('1123','本期借方')",
        "TB('1123','本期贷方')",
        "WP('F1','明细表F1-2'",
        "WP('F1','长期挂款检查表F1-5'",
    ):
        if want not in formulas:
            errs.append(f"{SHEET_ADJ} 缺公式 {want}")
    if "TB('1231'," in formulas:
        errs.append(f"{SHEET_ADJ} 出现宽口径坏账 TB('1231',…)（会含应收账款坏账）")

    detail = _find_block(doc, SHEET_DETAIL)
    if detail is None:
        errs.append(f"缺 F1 {SHEET_DETAIL} 块")
    elif "WP(" in json.dumps(detail, ensure_ascii=False):
        errs.append(f"{SHEET_DETAIL} 出现 WP()（F1-1 ↔ F1-2 会成环）")

    analysis = _find_block(doc, SHEET_ANALYSIS)
    if analysis is None:
        errs.append(f"缺 F1 {SHEET_ANALYSIS} 块")
    else:
        joined = "\n".join(str(c.get("formula") or "") for c in analysis.get("cells") or [])
        if "TB_SUM('1401~1499','期末余额')" not in joined:
            errs.append(f"{SHEET_ANALYSIS} 缺存货 BS-010 口径公式")
        if "TB('1401'," in joined:
            errs.append(f"{SHEET_ANALYSIS} 用 TB('1401') 取存货（1401 是材料采购，恒为空）")

    refs = _all_f1_cell_refs(doc)
    dupes = sorted({r for r in refs if refs.count(r) > 1})
    if dupes:
        errs.append(f"F1 内 cell_ref 重复（公式管理会互相遮蔽）：{dupes}")

    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description="补齐 F1 公式管理预设（幂等）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    raw = MAPPING_PATH.read_text(encoding="utf-8")
    doc = json.loads(raw)

    if args.check:
        errs = validate(doc)
        print("\n".join(errs or ["[OK] F1 公式预设校验通过"]))
        return 1 if errs else 0

    changes = apply(doc)
    print("\n".join(changes or ["无需修改（已对齐）"]))
    if any(c.startswith("[FATAL]") for c in changes):
        return 1

    errs = validate(doc)
    if errs:
        print("[FATAL] 校验失败，未写入：")
        print("\n".join(f"  {e}" for e in errs))
        return 1

    if args.dry_run:
        print("[dry-run] 未写文件")
        return 0

    if changes:
        trailing = "\n" if raw.endswith("\n") else ""
        MAPPING_PATH.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + trailing, encoding="utf-8"
        )
        print(f"已写入 {MAPPING_PATH}")
    print("[OK] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
