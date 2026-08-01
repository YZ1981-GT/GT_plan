#!/usr/bin/env python
"""重写 F2 存货的公式管理预设（幂等）。

═══════════════════════════════════════════════════════════════════════════════
背景（spec: .kiro/specs/f2-inventory-account-mapping-and-linkage/ Wave 4）
═══════════════════════════════════════════════════════════════════════════════

Wave 1~2 已证明并修复了 F2 render/取数路径的核心 bug：
`account_chart` 库内并存**两个互不兼容的标准存货科目表变体**（见
`app.services.f2_extraction.category_rules` docstring 实证表），
``1405``/``1406``/``1407``/``1408``/``1411``/``1416``/``1461`` 的
名称↔编码对应在两版之间**完全相反**。

改造前 `审定表F2-1` / `明细汇总表F2-2` 两个块把「原材料=1401」「在产品=1402」
「库存商品=1403」「工程物资=1405」「委托加工物资=1408」「存货跌价准备=1461」
写成公式管理页的固定公式 —— 这些编码在真实科目表里根本不是这些名字
（``1403`` 实际是「原材料」，``1405``/``1406`` 两版相反……），公式管理页看到的
公式与它声称汇总的分类**完全对不上**，比没有公式更糟糕（用户会以为已取过数）。

本脚本按 Requirement 4 重写：

1. **删除** 所有「具体 14xx 编码 = 某个分类」的写死映射（F2-1/F2-2 各 12 条）。
2. **保留**区间口径 `TB_SUM('1401~1499',…)`（报表行 `BS-010`，项目无关）。
3. **跌价准备**保留但给出 `1416` 与 `1461` 两条并在 description 写明
   「按项目科目表二选一」（两版标准科目表分别用其中一个）。
4. **新增** 底稿间 `WP()` 联动：
   - F2-1 的 AJE/RJE 调整净额改用 `WP('F2','调整分录汇总F2-14', ...)` 的
     借贷合计相减 —— 这是**项目无关**的写法（F2-14 汇总的是全部调整行，
     不限定某个具体科目码），替代原来错误地只统计 `1401` 一个码的 `ADJ()`。
   - F2-2 各分类 `期初/期末余额` 改用 `WP('F2', '<F2-3~13 各明细表 sheet 名>',
     '期末余额合计')` —— 分类维度已经由 F2-3~13 各专属明细表天然承载
     （每个 sheet 就是一个分类，不需要再猜编码）。
   - 两个披露 sheet（`附注披露信息（上市公司）` / `附注披露信息（国企）`）
     此前在公式管理页**完全空白** —— 新增块引用 F2-1/F2-2 的合计。
   - F2-47 跌价准备测试表补一条引用 F2-1 跌价准备审定数的 `WP()`（Req 4.3
     「F2-47 ← F2-1」）。
5. 修正 `分析程序F2-3` 块的 sheet 名（源 xlsx 里没有这个 tab；真实用途是
   「存货总体分析表F2-18」的总量分析，属改造前的贴错标签）+ 区间口径补全
   到 `1401~1499`（原只有 `1401~1405`，漏了 F2-6~F2-13 对应的六个分类）。
6. 修正 F2-38~49 系列测试表描述里把 `1403`（真实名「原材料」）误标成
   「库存商品」的文字错误（**这些码本身两版都一致、不是变体冲突**，只是
   描述文字写错分类名，不属 Req 4.2 的「编码语义冲突」情形，但既然发现了
   一并修掉，避免继续误导审计人员）。

**两条硬约束（同 F1 脚本）**

- `preset_library.convert_prefill_presets()` 的 ``page_key = f"workpaper:{wp_code}"``
  **忽略 sheet** → `workpaper:F2` 内 ``cell_ref`` 必须**全局唯一**。
- **F2-2 明细汇总表禁引 F2-1**（F2 的取数级联是 F2-3~13 → F2-2 → F2-1，
  若 F2-2 反引 F2-1 会成环）；F2-3~13 各明细表本身也不引用 F2-1/F2-2。

Usage::

    python backend/scripts/fix/fix_f2_prefill_presets.py --dry-run
    python backend/scripts/fix/fix_f2_prefill_presets.py
    python backend/scripts/fix/fix_f2_prefill_presets.py --check

spec: .kiro/specs/f2-inventory-account-mapping-and-linkage/ Wave 4 (Task 4.1)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
MAPPING_PATH = _BACKEND / "data" / "prefill_formula_mapping.json"

SHEET_ADJ = "审定表F2-1"
SHEET_DETAIL = "明细汇总表F2-2"
SHEET_ANALYSIS_OLD = "分析程序F2-3"
SHEET_ANALYSIS_NEW = "存货总体分析表F2-18"
SHEET_F2_14 = "调整分录汇总F2-14"
SHEET_F2_47 = "跌价准备测试表F2-47"
SHEET_DISC_LISTED = "附注披露信息（上市公司）"
SHEET_DISC_SOE = "附注披露信息（国企）"

#: F2-3~13 各分类明细表 sheet 名（源 xlsx tab 名，逐字）——
#: 明细汇总表 F2-2 按 `WP()` 引用它们的「期初/期末余额合计」，分类维度由
#: sheet 本身天然承载，不需要再猜编码。
DETAIL_SHEETS: dict[str, str] = {
    "原材料": "一、原材料明细表F2-3",
    "材料采购在途": "二、材料采购、在途物资明细表F2-4",
    "周转材料": "三、周转材料、低值易耗品，包装物明细表F2-5",
    "自制半成品": "四、自制半成品明细表F2-6",
    "委托加工物资": "五、委托加工物资明细表F2-7",
    "库存商品": "六、库存商品明细表F2-8",
    "发出商品": "七、发出商品F2-9",
    "开发产品": "八、开发产品F2-10",
    "开发成本": "九、开发成本F2-11",
    "合同履约成本": "十、合同履约成本F2-12",
    "消耗性生物资产": "十一、消耗性生物资产F2-13",
}

#: 改造前描述文字把 1403（真实科目名「原材料」）误标成「库存商品」的测试块；
#: 这些码本身两版标准科目表一致（非变体冲突），只是文字错误。
_MISLABELED_1403_SHEETS = {
    "计价方法测试表-平均F2-38",
    "计价方法测试表-先进先出F2-39",
    "计价方法测试表-标准成本差异F2-40",
}


def _blocks(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return doc["mappings"]


def _find_block(doc: dict[str, Any], sheet: str) -> dict[str, Any] | None:
    for b in _blocks(doc):
        if b.get("wp_code") == "F2" and b.get("sheet") == sheet:
            return b
    return None


def _f2_blocks(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [b for b in _blocks(doc) if b.get("wp_code") == "F2"]


def _all_f2_cell_refs(doc: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for b in _f2_blocks(doc):
        out.extend(str(c.get("cell_ref") or "") for c in b.get("cells") or [])
    return out


#: F2-1 审定表：删除全部「编码=分类」写死映射，只留区间/联动/上年审定。
_ADJ_CELLS_TO_DROP = {
    "原材料_期初", "原材料_未审数",
    "在产品_期初", "在产品_未审数",
    "库存商品_期初", "库存商品_未审数",
    "工程物资_期初", "工程物资_未审数",
    "委托加工物资_期初", "委托加工物资_未审数",
    "存货跌价准备_期初", "存货跌价准备_未审数",
    # 原 ADJ('1401',...) 只统计单一科目码，与描述「汇总1401~1461」不符，删除后
    # 由下方新增的 F2-14 联动公式替代。
    "AJE调整", "RJE调整",
}

_ADJ_NEW_CELLS: list[dict[str, Any]] = [
    {
        "cell_ref": "期初余额（区间口径）",
        "formula": "=TB_SUM('1401~1499','期初余额')",
        "formula_type": "TB_SUM",
        "description": "存货（报表行 BS-010 口径）期初余额合计——项目无关的区间求和，不依赖具体分类编码",
    },
    {
        "cell_ref": "存货跌价准备_期初_变体A",
        "formula": "=TB('1416','期初余额')",
        "formula_type": "TB",
        "description": "存货跌价准备期初余额（变体 A 标准科目表编码；与下一条二选一，按本项目 account_chart 实际编码取用）",
    },
    {
        "cell_ref": "存货跌价准备_期末_变体A",
        "formula": "=TB('1416','期末余额')",
        "formula_type": "TB",
        "description": "存货跌价准备期末余额（变体 A；与下一条二选一）",
    },
    {
        "cell_ref": "存货跌价准备_期初_变体B",
        "formula": "=TB('1461','期初余额')",
        "formula_type": "TB",
        "description": "存货跌价准备期初余额（变体 B 标准科目表编码；与上一条二选一，按本项目 account_chart 实际编码取用）",
    },
    {
        "cell_ref": "存货跌价准备_期末_变体B",
        "formula": "=TB('1461','期末余额')",
        "formula_type": "TB",
        "description": "存货跌价准备期末余额（变体 B；与上一条二选一）",
    },
    {
        "cell_ref": "AJE调整净额",
        "formula": "=WP('F2','调整分录汇总F2-14','借方合计')-WP('F2','调整分录汇总F2-14','贷方合计')",
        "formula_type": "WP",
        "description": (
            "存货审计调整分录净额（← F2-14 全部 AJE 借贷合计相减）——"
            "项目无关：不限定某个具体 14xx 科目码，覆盖 F2-14 实际录入的全部调整行"
        ),
    },
    {
        "cell_ref": "明细汇总期末合计",
        "formula": "=WP('F2','明细汇总表F2-2','期末余额合计')",
        "formula_type": "WP",
        "description": "审定表未审数来源 = F2-2 明细汇总表期末余额合计（供交叉核对）",
    },
]


#: F2-2 明细汇总表：同样删除「编码=分类」写死映射，改用 F2-3~13 各明细表联动。
_DETAIL_CELLS_TO_DROP = {
    "原材料_期初", "原材料_期末",
    "在产品_期初", "在产品_期末",
    "库存商品_期初", "库存商品_期末",
    "工程物资_期初", "工程物资_期末",
    "委托加工物资_期初", "委托加工物资_期末",
    "存货跌价准备_期初", "存货跌价准备_期末",
    "库存商品_主仓库_期末", "库存商品_备料库_期末",
    "库存商品_A类_期末", "库存商品_B类_期末",
    "AJE调整_明细",
}


def _detail_new_cells() -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for label, sheet in DETAIL_SHEETS.items():
        cells.append({
            "cell_ref": f"{label}_期初余额",
            "formula": f"=WP('F2','{sheet}','期初余额合计')",
            "formula_type": "WP",
            "description": f"{label}期初余额合计（← {sheet}，分类由明细表本身承载，不猜编码）",
        })
        cells.append({
            "cell_ref": f"{label}_期末余额",
            "formula": f"=WP('F2','{sheet}','期末余额合计')",
            "formula_type": "WP",
            "description": f"{label}期末余额合计（← {sheet}）",
        })
    cells.append({
        "cell_ref": "存货跌价准备_期初_变体A_明细",
        "formula": "=TB('1416','期初余额')",
        "formula_type": "TB",
        "description": "存货跌价准备期初余额（变体 A；与变体 B 二选一，按本项目 account_chart 实际编码）",
    })
    cells.append({
        "cell_ref": "存货跌价准备_期末_变体A_明细",
        "formula": "=TB('1416','期末余额')",
        "formula_type": "TB",
        "description": "存货跌价准备期末余额（变体 A；二选一）",
    })
    cells.append({
        "cell_ref": "存货跌价准备_期初_变体B_明细",
        "formula": "=TB('1461','期初余额')",
        "formula_type": "TB",
        "description": "存货跌价准备期初余额（变体 B；二选一）",
    })
    cells.append({
        "cell_ref": "存货跌价准备_期末_变体B_明细",
        "formula": "=TB('1461','期末余额')",
        "formula_type": "TB",
        "description": "存货跌价准备期末余额（变体 B；二选一）",
    })
    return cells


#: F2-2 本期借方/贷方发生额原区间只到 1408（漏了 1409~1499 多个分类），补全区间。
_DETAIL_RANGE_FIX = {
    "本期借方发生": "=TB_SUM('1401~1499','本期借方')",
    "本期贷方发生": "=TB_SUM('1401~1499','本期贷方')",
}


#: 新增披露 sheet 块（改造前公式管理页在这两个 sheet 完全空白）。
def _disclosure_block(sheet: str, variant_label: str) -> dict[str, Any]:
    return {
        "wp_code": "F2",
        "wp_name": f"存货附注披露（{variant_label}）",
        "sheet": sheet,
        "account_codes": ["1401~1499"],
        "cells": [
            {
                "cell_ref": f"分类披露期末合计（{variant_label}）",
                "formula": "=WP('F2','明细汇总表F2-2','期末余额合计')",
                "formula_type": "WP",
                "description": f"（1）分类表期末余额合计来源 = F2-2 明细汇总表（{variant_label}）",
            },
            {
                "cell_ref": f"跌价准备变动期末（{variant_label}）",
                "formula": "=WP('F2','存货审定表F2-1','存货跌价准备_期末_变体A')",
                "formula_type": "WP",
                "description": (
                    f"（2）跌价准备变动表期末数来源 = F2-1 审定表跌价准备审定数（{variant_label}；"
                    "若本项目用变体 B 编码，请在公式管理页改引「存货跌价准备_期末_变体B」）"
                ),
            },
        ],
    }


def apply(doc: dict[str, Any]) -> list[str]:
    changes: list[str] = []

    # ── 1. 审定表 F2-1：删旧、补新 ──────────────────────────────────────
    adj = _find_block(doc, SHEET_ADJ)
    if adj is None:
        changes.append(f"[FATAL] 缺 F2 {SHEET_ADJ} 块")
        return changes
    before = len(adj.get("cells") or [])
    adj["cells"] = [c for c in (adj.get("cells") or []) if c["cell_ref"] not in _ADJ_CELLS_TO_DROP]
    dropped = before - len(adj["cells"])
    if dropped:
        changes.append(f"{SHEET_ADJ} 删除 {dropped} 条「编码=分类」写死映射")
    existing = {c["cell_ref"] for c in adj["cells"]}
    added = [c for c in _ADJ_NEW_CELLS if c["cell_ref"] not in existing]
    if added:
        adj["cells"].extend(json.loads(json.dumps(added, ensure_ascii=False)))
        changes.append(f"{SHEET_ADJ} 追加 {len(added)} 条：{'、'.join(c['cell_ref'] for c in added)}")
    # account_codes 收窄为区间口径 + 两版备抵码（不再列出具体分类码）
    want_codes = ["1401~1499", "1416", "1461"]
    if adj.get("account_codes") != want_codes:
        adj["account_codes"] = want_codes
        changes.append(f"{SHEET_ADJ}.account_codes 改为区间口径 {want_codes}")

    # ── 2. 明细汇总表 F2-2：删旧、补新（F2-3~13 联动） ──────────────────
    detail = _find_block(doc, SHEET_DETAIL)
    if detail is None:
        changes.append(f"[FATAL] 缺 F2 {SHEET_DETAIL} 块")
        return changes
    before = len(detail.get("cells") or [])
    detail["cells"] = [
        c for c in (detail.get("cells") or []) if c["cell_ref"] not in _DETAIL_CELLS_TO_DROP
    ]
    dropped = before - len(detail["cells"])
    if dropped:
        changes.append(f"{SHEET_DETAIL} 删除 {dropped} 条「编码=分类」写死映射")
    existing = {c["cell_ref"] for c in detail["cells"]}
    new_cells = _detail_new_cells()
    added = [c for c in new_cells if c["cell_ref"] not in existing]
    if added:
        detail["cells"].extend(json.loads(json.dumps(added, ensure_ascii=False)))
        changes.append(f"{SHEET_DETAIL} 追加 {len(added)} 条（F2-3~13 联动 + 跌价二选一）")
    range_changed = False
    for cell in detail["cells"]:
        want = _DETAIL_RANGE_FIX.get(cell["cell_ref"])
        if want and cell.get("formula") != want:
            cell["formula"] = want
            range_changed = True
    if range_changed:
        changes.append(f"{SHEET_DETAIL} 本期借方/贷方发生区间补全为 1401~1499")
    if detail.get("account_codes") != ["1401~1499", "1416", "1461"]:
        detail["account_codes"] = ["1401~1499", "1416", "1461"]
        changes.append(f"{SHEET_DETAIL}.account_codes 改为区间口径")

    # ── 3. 分析程序块：修正贴错的 sheet 名 + 补全区间 ───────────────────
    old_analysis = _find_block(doc, SHEET_ANALYSIS_OLD)
    new_analysis = _find_block(doc, SHEET_ANALYSIS_NEW)
    if old_analysis is not None and new_analysis is None:
        old_analysis["sheet"] = SHEET_ANALYSIS_NEW
        old_analysis["wp_name"] = "存货总体分析表"
        for cell in old_analysis.get("cells") or []:
            if cell.get("formula") == "=TB_SUM('1401~1405','期末余额')":
                cell["formula"] = "=TB_SUM('1401~1499','期末余额')"
                cell["description"] = "从试算表取存货期末余额合计（未审，报表行 BS-010 口径）"
            if cell.get("formula", "").startswith("=PREV('F2','分析程序F2-3'"):
                cell["formula"] = cell["formula"].replace("分析程序F2-3", SHEET_ANALYSIS_NEW)
            # `page_key` 忽略 sheet → `上年审定数` 与 F2-1 的同名 cell_ref 全局撞键
            # （改造前只有 F2-1 一个块用它，未暴露；本次新增 F2-1 更多条目后一并
            # 重命名分析块的 cell_ref 消歧，避免公式管理页互相遮蔽）。
            if cell.get("cell_ref") == "上年审定数":
                cell["cell_ref"] = "上年审定数（分析程序）"
        changes.append(
            f"分析块 sheet 名从贴错的 {SHEET_ANALYSIS_OLD!r} 改为源 xlsx 真实 tab {SHEET_ANALYSIS_NEW!r}"
            "，并补全区间到 1401~1499"
        )

    # ── 4. 新增两个披露 sheet 块 ─────────────────────────────────────────
    for sheet, variant_label in ((SHEET_DISC_LISTED, "上市"), (SHEET_DISC_SOE, "国企")):
        if _find_block(doc, sheet) is None:
            idx = max(
                (i for i, b in enumerate(_blocks(doc)) if b.get("wp_code") == "F2"),
                default=len(_blocks(doc)) - 1,
            )
            _blocks(doc).insert(idx + 1, _disclosure_block(sheet, variant_label))
            changes.append(f"新增块 {sheet}（改造前公式管理页空白）")

    # ── 5. F2-47 跌价准备测试表补 F2-1 联动 ─────────────────────────────
    f2_47 = _find_block(doc, SHEET_F2_47)
    if f2_47 is not None:
        existing = {c["cell_ref"] for c in f2_47.get("cells") or []}
        if "审定表跌价准备审定数" not in existing:
            f2_47.setdefault("cells", []).append({
                "cell_ref": "审定表跌价准备审定数",
                "formula": "=WP('F2','存货审定表F2-1','存货跌价准备_期末_变体A')",
                "formula_type": "WP",
                "description": "跌价准备测试与 F2-1 审定表勾稽（← F2-1，二选一变体见 F2-1 描述）",
            })
            changes.append(f"{SHEET_F2_47} 追加 F2-1 联动")

    # ── 6. 修正 1403 误标「库存商品」为「原材料」（1403 两版一致，非编码冲突） ──
    relabeled = 0
    for sheet in _MISLABELED_1403_SHEETS:
        block = _find_block(doc, sheet)
        if block is None:
            continue
        for cell in block.get("cells") or []:
            desc = str(cell.get("description") or "")
            if "库存商品" in desc and "1403" in json.dumps(block.get("account_codes") or []):
                cell["description"] = desc.replace("库存商品", "原材料")
                relabeled += 1
    if relabeled:
        changes.append(f"修正 {relabeled} 处 1403 误标「库存商品」为「原材料」（1403 实为原材料，两版一致）")

    return changes


def validate(doc: dict[str, Any]) -> list[str]:
    errs: list[str] = []

    adj = _find_block(doc, SHEET_ADJ)
    detail = _find_block(doc, SHEET_DETAIL)
    if adj is None:
        errs.append(f"缺 F2 {SHEET_ADJ} 块")
        adj = {"cells": []}
    if detail is None:
        errs.append(f"缺 F2 {SHEET_DETAIL} 块")
        detail = {"cells": []}

    # 6.2 — 不再出现具体 14xx 编码=分类的写死映射（跌价 1416/1461 二选一是显式豁免）
    _CATEGORY_CODE_RE = re.compile(r"TB\('(140[1-9]|141[01])'")
    for block in (adj, detail):
        for cell in block.get("cells") or []:
            formula = str(cell.get("formula") or "")
            m = _CATEGORY_CODE_RE.search(formula)
            if m:
                errs.append(
                    f"{block.get('sheet')}/{cell['cell_ref']} 仍写死具体分类编码 "
                    f"{m.group(1)}：{formula}"
                )

    # 6.1 — 保留区间口径
    adj_formulas = "\n".join(str(c.get("formula") or "") for c in adj.get("cells") or [])
    if "TB_SUM('1401~1499'," not in adj_formulas:
        errs.append(f"{SHEET_ADJ} 缺区间口径 TB_SUM('1401~1499',…)")

    # 4.2 — 跌价准备两条二选一 + description 说明
    for code in ("1416", "1461"):
        if f"TB('{code}'," not in adj_formulas:
            errs.append(f"{SHEET_ADJ} 缺跌价准备变体 {code} 的公式")
    for cell in adj.get("cells") or []:
        if cell["cell_ref"].startswith("存货跌价准备_") and "二选一" not in str(
            cell.get("description") or ""
        ):
            errs.append(f"{SHEET_ADJ}/{cell['cell_ref']} description 未写明二选一")

    # 4.3 — 底稿间 WP() 联动齐备
    if "WP('F2','调整分录汇总F2-14'" not in adj_formulas:
        errs.append(f"{SHEET_ADJ} 缺 F2-14 联动（AJE 调整净额）")

    detail_formulas = "\n".join(str(c.get("formula") or "") for c in detail.get("cells") or [])
    for sheet in DETAIL_SHEETS.values():
        if f"'{sheet}'" not in detail_formulas:
            errs.append(f"{SHEET_DETAIL} 缺 {sheet} 联动")

    for sheet in (SHEET_DISC_LISTED, SHEET_DISC_SOE):
        if _find_block(doc, sheet) is None:
            errs.append(f"缺披露块 {sheet}")

    # F2-2 禁反引 F2-1（防成环）
    if SHEET_ADJ in detail_formulas or "存货审定表F2-1" in detail_formulas:
        errs.append(f"{SHEET_DETAIL} 反引 {SHEET_ADJ}（会与 F2-1 成环）")

    # cell_ref 全局唯一
    refs = _all_f2_cell_refs(doc)
    dupes = sorted({r for r in refs if refs.count(r) > 1})
    if dupes:
        errs.append(f"F2 内 cell_ref 重复（公式管理会互相遮蔽）：{dupes}")

    # 分析块 sheet 名必须已更正
    if _find_block(doc, SHEET_ANALYSIS_OLD) is not None:
        errs.append(f"分析块仍用贴错的 sheet 名 {SHEET_ANALYSIS_OLD!r}")

    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description="重写 F2 公式管理预设（幂等）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    raw = MAPPING_PATH.read_text(encoding="utf-8")
    doc = json.loads(raw)

    if args.check:
        errs = validate(doc)
        print("\n".join(errs or ["[OK] F2 公式预设校验通过"]))
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
