#!/usr/bin/env python
"""D4 营业收入公式预设纠偏（幂等，Task 6.1 + 6.2 范围）。

修订 ``backend/data/prefill_formula_mapping.json`` 里 D4 的 8 类缺陷
（全部为 DB + 源 xlsx 只读实证）：

**Task 6.1 范围：**

1. **余额口径 → 本期发生额**（Req 7.1）
   损益类科目无余额概念。改造前 4 条预设用 ``'期初余额'`` / ``'期末余额'``，
   而 ``report_config`` 实证：
   - ``IS-001 一、营业收入 = SUM_TB('6001~6099','本期发生额')``
   - ``IS-002 减：营业成本 = SUM_TB('6401~6499','本期发生额')``
   故一律改 ``'本期发生额'``。

2. **收入区间对齐 IS-001**（Req 7.2）
   改造前区间写 ``'6001~6051'``，不对齐报表行的 ``'6001~6099'``。
   ``6051 其他业务收入`` 在 IS-001 的 ``6001~6099`` 区间内，属同一行。

3. **6051 单列**（Req 7.2）
   其他业务收入 ``6051`` 虽属 IS-001 区间，但审定表 D4-1 分主营/其他两段，
   故在审定表块的 ``account_codes`` 里需要独立列出（取数粒度需要区分主营 vs 其他）。

4. **补 6401/6402 成本侧预设**（Req 7.4）
   改造前完全缺失营业成本侧（``IS-002``）。
   新增审定表成本条目 + 成本明细表块。

5. **每块补 sheet_name**（Req 7.3）
   改造前 6 个块全部 ``sheet_name=None``，导致 ``page_key=workpaper:D4``
   忽略 sheet 后 ``上年审定数`` 在两个块间撞键被吞。

**Task 6.2 范围：**

6. **新增两个披露 sheet 预设块**（Req 7.5）
   改造前 ``附注披露信息（上市公司）`` 和 ``附注披露信息（国企）`` 零预设，
   公式管理页完全空白。

7. **纠正贴错标签块**（Req 7.6）
   块 ``wp_name='营业收入明细表'``（``sheet='收入明细表D4-4'``）的
   ``TB_AUX('6001','客户','...')`` 维度双错：D4-2 是按月×产品，非按客户。
   删除该块。另删口径与维度双错的 ``TB_AUX`` 条目（损益类搭 ``'期末余额'``
   或 6001/6051/6401/6402 搭 ``'客户'`` 维度的 D4-2 场景）。

8. **审定表补 WP() 引用明细表**（Req 7.7）
   ``WP('D4','主营业务收入明细表D4-2','...')`` 与
   ``WP('D4','其他业务收入明细表D4-3','...')``。
   明细表块（D4-2、D4-3）禁止反向引用审定表（防成环）。

Usage::

    python backend/scripts/fix/fix_d4_prefill_presets.py --dry-run
    python backend/scripts/fix/fix_d4_prefill_presets.py
    python backend/scripts/fix/fix_d4_prefill_presets.py --check

spec: .kiro/specs/d4-four-table-extraction-and-disclosure-alignment/ Requirements 7.1~7.7
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
MAPPING_PATH = _BACKEND / "data" / "prefill_formula_mapping.json"

# ─── 正确的 sheet 名（源 xlsx tab 名精确值） ───────────────────────────
SHEET_ADJ = "营业收入审定表D4-1"
SHEET_ANALYSIS = "分析程序D4-3"
SHEET_DETAIL_OTHER = "收入明细表D4-4"
SHEET_DETAIL_MAIN = "主营业务收入明细表D4-2"
SHEET_ERP = "营业收入账面金额与ERP系统核对记录D4-13"
SHEET_CUTOFF = "营业收入截止测试（账到单据）D4-17"
SHEET_DETAIL_OTHER_D43 = "其他业务收入明细表D4-3"

# Task 6.2: 披露 sheet（源 xlsx tab 名精确值，全角括号）
SHEET_DISC_LISTED = "附注披露信息（上市公司）"
SHEET_DISC_SOE = "附注披露信息（国企）"

# Task 6.2: 贴错标签的旧块标识（将被删除）
_MISLABELED_SHEET = "收入明细表D4-4"
_MISLABELED_WP_NAME = "营业收入明细表"

# ─── 口径常量 ─────────────────────────────────────────────────────────
OCCURRENCE = "本期发生额"
OLD_BALANCE_TERMS = ("期初余额", "期末余额")

# 损益类科目码（用于 TB_AUX 口径校验）
_PL_CODES = ("6001", "6051", "6401", "6402")


def _blocks(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return doc["mappings"]


def _find_d4_block(doc: dict[str, Any], sheet: str) -> dict[str, Any] | None:
    for b in _blocks(doc):
        if b.get("wp_code") == "D4" and b.get("sheet") == sheet:
            return b
    return None


def _cell_refs_in_block(block: dict[str, Any]) -> set[str]:
    return {str(c.get("cell_ref") or "") for c in block.get("cells") or []}


def _all_d4_cell_refs(doc: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for b in _blocks(doc):
        if b.get("wp_code") != "D4":
            continue
        out.extend(str(c.get("cell_ref") or "") for c in b.get("cells") or [])
    return out


def _last_d4_idx(doc: dict[str, Any]) -> int:
    """Return index of last D4 block in mappings."""
    idx = -1
    for i, b in enumerate(_blocks(doc)):
        if b.get("wp_code") == "D4":
            idx = i
    return idx


# ─── Task 6.2: 披露 sheet 预设块定义 ─────────────────────────────────

_DISC_LISTED_BLOCK: dict[str, Any] = {
    "wp_code": "D4",
    "wp_name": "D4 附注披露信息（上市公司）",
    "sheet": SHEET_DISC_LISTED,
    "sheet_name": SHEET_DISC_LISTED,
    "account_codes": ["6001", "6051", "6401", "6402"],
    "cells": [
        {
            "cell_ref": "主营业务收入本期",
            "formula": f"=TB('6001','{OCCURRENCE}')",
            "formula_type": "TB",
            "description": "披露表主营业务收入本期发生额",
        },
        {
            "cell_ref": "其他业务收入本期",
            "formula": f"=TB('6051','{OCCURRENCE}')",
            "formula_type": "TB",
            "description": "披露表其他业务收入本期发生额",
        },
        {
            "cell_ref": "营业收入合计本期",
            "formula": f"=TB_SUM('6001~6099','{OCCURRENCE}')",
            "formula_type": "TB_SUM",
            "description": "披露表营业收入合计本期发生额（IS-001）",
        },
        {
            "cell_ref": "主营业务成本本期",
            "formula": f"=TB('6401','{OCCURRENCE}')",
            "formula_type": "TB",
            "description": "披露表主营业务成本本期发生额",
        },
        {
            "cell_ref": "其他业务成本本期",
            "formula": f"=TB('6402','{OCCURRENCE}')",
            "formula_type": "TB",
            "description": "披露表其他业务成本本期发生额",
        },
        {
            "cell_ref": "营业成本合计本期",
            "formula": f"=TB_SUM('6401~6499','{OCCURRENCE}')",
            "formula_type": "TB_SUM",
            "description": "披露表营业成本合计本期发生额（IS-002）",
        },
        {
            "cell_ref": "上年主营业务收入",
            "formula": f"=PREV('D4','{SHEET_DISC_LISTED}','主营业务收入本期')",
            "formula_type": "PREV",
            "description": "上年主营业务收入（取上年同页）",
        },
        {
            "cell_ref": "上年营业成本合计",
            "formula": f"=PREV('D4','{SHEET_DISC_LISTED}','营业成本合计本期')",
            "formula_type": "PREV",
            "description": "上年营业成本合计（取上年同页）",
        },
    ],
}

_DISC_SOE_BLOCK: dict[str, Any] = {
    "wp_code": "D4",
    "wp_name": "D4 附注披露信息（国企）",
    "sheet": SHEET_DISC_SOE,
    "sheet_name": SHEET_DISC_SOE,
    "account_codes": ["6001", "6051", "6401", "6402"],
    "cells": [
        {
            "cell_ref": "主营业务收入本期",
            "formula": f"=TB('6001','{OCCURRENCE}')",
            "formula_type": "TB",
            "description": "披露表主营业务收入本期发生额",
        },
        {
            "cell_ref": "其他业务收入本期",
            "formula": f"=TB('6051','{OCCURRENCE}')",
            "formula_type": "TB",
            "description": "披露表其他业务收入本期发生额",
        },
        {
            "cell_ref": "营业收入合计本期",
            "formula": f"=TB_SUM('6001~6099','{OCCURRENCE}')",
            "formula_type": "TB_SUM",
            "description": "披露表营业收入合计本期发生额（IS-001）",
        },
        {
            "cell_ref": "主营业务成本本期",
            "formula": f"=TB('6401','{OCCURRENCE}')",
            "formula_type": "TB",
            "description": "披露表主营业务成本本期发生额",
        },
        {
            "cell_ref": "其他业务成本本期",
            "formula": f"=TB('6402','{OCCURRENCE}')",
            "formula_type": "TB",
            "description": "披露表其他业务成本本期发生额",
        },
        {
            "cell_ref": "营业成本合计本期",
            "formula": f"=TB_SUM('6401~6499','{OCCURRENCE}')",
            "formula_type": "TB_SUM",
            "description": "披露表营业成本合计本期发生额（IS-002）",
        },
        {
            "cell_ref": "上年主营业务收入",
            "formula": f"=PREV('D4','{SHEET_DISC_SOE}','主营业务收入本期')",
            "formula_type": "PREV",
            "description": "上年主营业务收入（取上年同页）",
        },
        {
            "cell_ref": "上年营业成本合计",
            "formula": f"=PREV('D4','{SHEET_DISC_SOE}','营业成本合计本期')",
            "formula_type": "PREV",
            "description": "上年营业成本合计（取上年同页）",
        },
    ],
}

# ─── Task 6.2: 审定表 WP() 引用明细表 ────────────────────────────────
_WP_CELLS_FOR_ADJ: list[dict[str, Any]] = [
    {
        "cell_ref": "明细表D4-2合计",
        "formula": f"=WP('D4','{SHEET_DETAIL_MAIN}','全年收入合计')",
        "formula_type": "WP",
        "description": "审定表引用主营业务收入明细表D4-2全年合计",
    },
    {
        "cell_ref": "明细表D4-3合计",
        "formula": f"=WP('D4','{SHEET_DETAIL_OTHER_D43}','全年收入合计')",
        "formula_type": "WP",
        "description": "审定表引用其他业务收入明细表D4-3全年合计",
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# apply: 幂等修改逻辑
# ═══════════════════════════════════════════════════════════════════════════

def apply(doc: dict[str, Any]) -> list[str]:
    """Apply fixes and return list of change descriptions."""
    changes: list[str] = []

    # ── 1. 修余额口径 → 本期发生额 + 修区间 6001~6051 → 6001~6099 ─────
    for b in _blocks(doc):
        if b.get("wp_code") != "D4":
            continue
        for cell in b.get("cells") or []:
            formula = cell.get("formula") or ""
            orig = formula
            # Fix balance terms → 本期发生额 (only for TB/TB_SUM/TB_AUX type)
            if cell.get("formula_type") in ("TB", "TB_SUM", "TB_AUX"):
                for old_term in OLD_BALANCE_TERMS:
                    if old_term in formula:
                        formula = formula.replace(old_term, OCCURRENCE)
            # Fix interval 6001~6051 → 6001~6099
            if "6001~6051" in formula:
                formula = formula.replace("6001~6051", "6001~6099")
            if formula != orig:
                cell["formula"] = formula
                changes.append(
                    f"  {b['sheet']}.{cell['cell_ref']}: "
                    f"口径/区间修正 → {formula}"
                )

    # ── 2. 审定表 account_codes：确保有 6051 单列 ──────────────────────
    adj = _find_d4_block(doc, SHEET_ADJ)
    if adj is None:
        changes.append("[FATAL] 缺 D4 营业收入审定表D4-1 块")
        return changes

    codes = adj.setdefault("account_codes", [])
    if "6051" not in codes:
        codes.append("6051")
        changes.append(f"  {SHEET_ADJ}.account_codes 追加 '6051'")

    # Ensure 6001 is present (should be already)
    if "6001" not in codes:
        codes.insert(0, "6001")
        changes.append(f"  {SHEET_ADJ}.account_codes 追加 '6001'")

    # ── 3. 审定表补成本侧条目 6401/6402 ──────────────────────────────
    cost_codes_to_add = []
    if "6401" not in codes:
        cost_codes_to_add.append("6401")
    if "6402" not in codes:
        cost_codes_to_add.append("6402")
    if cost_codes_to_add:
        codes.extend(cost_codes_to_add)
        changes.append(f"  {SHEET_ADJ}.account_codes 追加成本侧 {cost_codes_to_add}")

    # 审定表补成本侧 cells
    cost_cells: list[dict[str, Any]] = [
        {
            "cell_ref": "营业成本本期发生额",
            "formula": f"=TB_SUM('6401~6499','{OCCURRENCE}')",
            "formula_type": "TB_SUM",
            "description": (
                "营业成本本期发生额（IS-002 口径 SUM_TB('6401~6499','本期发生额')）"
            ),
        },
        {
            "cell_ref": "主营业务成本本期发生额",
            "formula": f"=TB('6401','{OCCURRENCE}')",
            "formula_type": "TB",
            "description": "主营业务成本本期发生额（6401 前缀）",
        },
        {
            "cell_ref": "其他业务成本本期发生额",
            "formula": f"=TB('6402','{OCCURRENCE}')",
            "formula_type": "TB",
            "description": "其他业务成本本期发生额（6402 前缀）",
        },
    ]
    existing_refs = _cell_refs_in_block(adj)
    added_cost = [c for c in cost_cells if c["cell_ref"] not in existing_refs]
    if added_cost:
        adj.setdefault("cells", []).extend(
            json.loads(json.dumps(added_cost, ensure_ascii=False))
        )
        changes.append(
            f"  {SHEET_ADJ} 追加成本侧 {len(added_cost)} 条："
            f"{'、'.join(c['cell_ref'] for c in added_cost)}"
        )

    # ── 4. 每块补 sheet_name ──────────────────────────────────────────
    for b in _blocks(doc):
        if b.get("wp_code") != "D4":
            continue
        sheet = b.get("sheet") or ""
        if not b.get("sheet_name"):
            b["sheet_name"] = sheet
            changes.append(f"  块 '{sheet}' 补 sheet_name='{sheet}'")

    # ══════════════════════════════════════════════════════════════════════
    # Task 6.2 变更
    # ══════════════════════════════════════════════════════════════════════

    # ── 5. 删除贴错标签块（Req 7.6）──────────────────────────────────
    #  wp_name='营业收入明细表'，sheet='收入明细表D4-4'
    #  TB_AUX('6001','客户','...') 维度双错：D4-2 是按月×产品，非按客户。
    #  源 xlsx 无 '营业收入明细表' 这个 tab 名。
    blocks_to_remove: list[int] = []
    for i, b in enumerate(_blocks(doc)):
        if b.get("wp_code") != "D4":
            continue
        if (b.get("sheet") == _MISLABELED_SHEET
                and b.get("wp_name") == _MISLABELED_WP_NAME):
            blocks_to_remove.append(i)
    for i in reversed(blocks_to_remove):
        removed = _blocks(doc).pop(i)
        changes.append(
            f"  删除贴错标签块 '{removed.get('wp_name')}'"
            f"（sheet='{removed.get('sheet')}'，"
            f"TB_AUX('6001','客户') 口径与维度双错）"
        )

    # ── 6. 删口径与维度双错的 TB_AUX 条目（Req 7.6）─────────────────
    #  a) TB_AUX 搭配 '期末余额' 用于 6001/6051/6401/6402（损益类无余额）
    #  b) TB_AUX 用 '客户' 维度用于 D4-2（D4-2 是按月×产品）
    for b in _blocks(doc):
        if b.get("wp_code") != "D4":
            continue
        cells = b.get("cells") or []
        cells_to_remove: list[int] = []
        for ci, cell in enumerate(cells):
            if cell.get("formula_type") != "TB_AUX":
                continue
            formula = cell.get("formula") or ""
            # Check for 期末余额 with PL codes
            has_pl_code = any(code in formula for code in _PL_CODES)
            has_balance = "期末余额" in formula
            has_customer_dim = "'客户'" in formula or '"客户"' in formula
            if has_pl_code and has_balance:
                cells_to_remove.append(ci)
            elif has_pl_code and has_customer_dim:
                # '客户' dimension wrong for D4-2 (month×product)
                cells_to_remove.append(ci)
        for ci in reversed(cells_to_remove):
            removed_cell = cells.pop(ci)
            changes.append(
                f"  删 TB_AUX 条目 {b.get('sheet')}.{removed_cell.get('cell_ref')}"
                f"（口径/维度双错）: {removed_cell.get('formula')}"
            )

    # ── 7. 新增两个披露 sheet 预设块（Req 7.5）──────────────────────
    for block_def in (_DISC_LISTED_BLOCK, _DISC_SOE_BLOCK):
        existing = _find_d4_block(doc, block_def["sheet"])
        if existing is None:
            # Insert after last D4 block
            insert_idx = _last_d4_idx(doc) + 1
            _blocks(doc).insert(
                insert_idx,
                json.loads(json.dumps(block_def, ensure_ascii=False)),
            )
            changes.append(f"  新建披露块 '{block_def['sheet']}'")
        else:
            # Ensure cells exist
            existing_refs = _cell_refs_in_block(existing)
            for cell in block_def["cells"]:
                if cell["cell_ref"] not in existing_refs:
                    existing.setdefault("cells", []).append(
                        json.loads(json.dumps(cell, ensure_ascii=False))
                    )
                    changes.append(
                        f"  {block_def['sheet']} 追加 {cell['cell_ref']}"
                    )
            # Ensure sheet_name
            if not existing.get("sheet_name"):
                existing["sheet_name"] = block_def["sheet"]
                changes.append(
                    f"  块 '{block_def['sheet']}' 补 sheet_name"
                )

    # ── 8. 审定表补 WP() 引用明细表（Req 7.7）────────────────────────
    adj = _find_d4_block(doc, SHEET_ADJ)
    if adj is not None:
        existing_refs = _cell_refs_in_block(adj)
        for wp_cell in _WP_CELLS_FOR_ADJ:
            if wp_cell["cell_ref"] not in existing_refs:
                adj.setdefault("cells", []).append(
                    json.loads(json.dumps(wp_cell, ensure_ascii=False))
                )
                changes.append(
                    f"  {SHEET_ADJ} 追加 WP() 引用: {wp_cell['cell_ref']}"
                )

    return changes


# ═══════════════════════════════════════════════════════════════════════════
# validate: --check 校验逻辑
# ═══════════════════════════════════════════════════════════════════════════

def validate(doc: dict[str, Any]) -> list[str]:
    """Validate D4 presets, return list of error strings (empty = pass)."""
    errs: list[str] = []

    # ── 检查余额口径不应出现 ──────────────────────────────────────────
    for b in _blocks(doc):
        if b.get("wp_code") != "D4":
            continue
        for cell in b.get("cells") or []:
            formula = cell.get("formula") or ""
            ft = cell.get("formula_type") or ""
            if ft in ("TB", "TB_SUM", "TB_AUX"):
                for term in OLD_BALANCE_TERMS:
                    if term in formula:
                        errs.append(
                            f"损益类科目用余额口径：{b['sheet']}.{cell['cell_ref']} "
                            f"含 '{term}'（应为 '{OCCURRENCE}'）"
                        )

    # ── 检查区间对齐 IS-001 ──────────────────────────────────────────
    for b in _blocks(doc):
        if b.get("wp_code") != "D4":
            continue
        for cell in b.get("cells") or []:
            formula = cell.get("formula") or ""
            if "6001~6051" in formula:
                errs.append(
                    f"区间未对齐 IS-001：{b['sheet']}.{cell['cell_ref']} "
                    f"含 '6001~6051'（应为 '6001~6099'）"
                )

    # ── 检查 6051 单列 ───────────────────────────────────────────────
    adj = _find_d4_block(doc, SHEET_ADJ)
    if adj is None:
        errs.append(f"缺 D4 {SHEET_ADJ} 块")
        return errs

    codes = adj.get("account_codes") or []
    if "6051" not in codes:
        errs.append(f"{SHEET_ADJ}.account_codes 缺 '6051'（其他业务收入须单列）")

    # ── 检查成本侧 6401/6402 ────────────────────────────────────────
    if "6401" not in codes:
        errs.append(f"{SHEET_ADJ}.account_codes 缺 '6401'（主营业务成本）")
    if "6402" not in codes:
        errs.append(f"{SHEET_ADJ}.account_codes 缺 '6402'（其他业务成本）")

    # 检查成本公式存在
    adj_formulas = "\n".join(
        str(c.get("formula") or "") for c in adj.get("cells") or []
    )
    if "TB_SUM('6401~6499'" not in adj_formulas:
        errs.append(f"{SHEET_ADJ} 缺成本合计公式 TB_SUM('6401~6499',…)")

    # ── 检查每块有 sheet_name ────────────────────────────────────────
    for b in _blocks(doc):
        if b.get("wp_code") != "D4":
            continue
        if not b.get("sheet_name"):
            errs.append(f"块 '{b.get('sheet')}' 缺 sheet_name（会导致撞键）")

    # ── 检查 (sheet_name, cell_ref) 组合唯一 ─────────────────────────
    # 有 sheet_name 时按 (sheet_name, cell_ref) 判重；无 sheet_name 时才全局判重
    pairs: list[tuple[str, str]] = []
    for b in _blocks(doc):
        if b.get("wp_code") != "D4":
            continue
        sn = b.get("sheet_name") or ""
        for c in b.get("cells") or []:
            pairs.append((sn, str(c.get("cell_ref") or "")))
    dupes = sorted({p for p in pairs if pairs.count(p) > 1})
    if dupes:
        errs.append(
            f"D4 内 (sheet_name, cell_ref) 重复（同 sheet 内公式会互相遮蔽）：{dupes}"
        )

    # ══════════════════════════════════════════════════════════════════════
    # Task 6.2 校验
    # ══════════════════════════════════════════════════════════════════════

    # ── 检查贴错标签块已删除（Req 7.6）────────────────────────────────
    for b in _blocks(doc):
        if b.get("wp_code") != "D4":
            continue
        if (b.get("sheet") == _MISLABELED_SHEET
                and b.get("wp_name") == _MISLABELED_WP_NAME):
            errs.append(
                f"贴错标签块仍存在：wp_name='{_MISLABELED_WP_NAME}' "
                f"sheet='{_MISLABELED_SHEET}'（源 xlsx 无此 tab，且 TB_AUX 维度双错）"
            )

    # ── 检查无口径与维度双错的 TB_AUX（Req 7.6）──────────────────────
    for b in _blocks(doc):
        if b.get("wp_code") != "D4":
            continue
        for cell in b.get("cells") or []:
            if cell.get("formula_type") != "TB_AUX":
                continue
            formula = cell.get("formula") or ""
            has_pl_code = any(code in formula for code in _PL_CODES)
            has_balance = "期末余额" in formula
            has_customer_dim = "'客户'" in formula or '"客户"' in formula
            if has_pl_code and has_balance:
                errs.append(
                    f"TB_AUX 损益类+余额口径："
                    f"{b.get('sheet')}.{cell.get('cell_ref')} → {formula}"
                )
            if has_pl_code and has_customer_dim:
                errs.append(
                    f"TB_AUX 损益类+客户维度（D4-2 是按月×产品）："
                    f"{b.get('sheet')}.{cell.get('cell_ref')} → {formula}"
                )

    # ── 检查两个披露 sheet 有预设块（Req 7.5）────────────────────────
    for sheet in (SHEET_DISC_LISTED, SHEET_DISC_SOE):
        if _find_d4_block(doc, sheet) is None:
            errs.append(f"缺披露块 '{sheet}'（公式管理页空白）")

    # ── 检查审定表有 WP() 引用明细表（Req 7.7）───────────────────────
    adj = _find_d4_block(doc, SHEET_ADJ)
    if adj is not None:
        adj_formulas_str = "\n".join(
            str(c.get("formula") or "") for c in adj.get("cells") or []
        )
        if SHEET_DETAIL_MAIN not in adj_formulas_str:
            errs.append(
                f"{SHEET_ADJ} 缺 WP() 引用 '{SHEET_DETAIL_MAIN}'"
            )
        if SHEET_DETAIL_OTHER_D43 not in adj_formulas_str:
            errs.append(
                f"{SHEET_ADJ} 缺 WP() 引用 '{SHEET_DETAIL_OTHER_D43}'"
            )

    # ── 检查明细表块不反向引用审定表（防成环，Req 7.7）────────────────
    _detail_sheets = (SHEET_DETAIL_MAIN, SHEET_DETAIL_OTHER_D43)
    for b in _blocks(doc):
        if b.get("wp_code") != "D4":
            continue
        if b.get("sheet") not in _detail_sheets:
            continue
        for cell in b.get("cells") or []:
            formula = cell.get("formula") or ""
            if SHEET_ADJ in formula:
                errs.append(
                    f"明细表 '{b.get('sheet')}' 反向引用审定表（成环）："
                    f"{cell.get('cell_ref')} → {formula}"
                )

    return errs


# ═══════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════

def main() -> int:
    ap = argparse.ArgumentParser(description="D4 公式预设纠偏（幂等）")
    ap.add_argument("--dry-run", action="store_true", help="计算变更但不写入文件")
    ap.add_argument("--check", action="store_true", help="只做校验，有错 exit 1")
    args = ap.parse_args()

    raw = MAPPING_PATH.read_text(encoding="utf-8")
    doc = json.loads(raw)

    if args.check:
        errs = validate(doc)
        if errs:
            print(f"[FAIL] {len(errs)} 项欠账：")
            for e in errs:
                print(f"  {e}")
        else:
            print("[OK] D4 公式预设校验通过（0 项欠账）")
        return 1 if errs else 0

    changes = apply(doc)
    if changes:
        print(f"变更 {len(changes)} 项：")
        for c in changes:
            print(c)
    else:
        print("无需修改（已对齐）")

    if any(c.startswith("[FATAL]") for c in changes):
        return 1

    # Post-apply validation
    errs = validate(doc)
    if errs:
        print("[FATAL] apply 后校验失败，未写入：")
        for e in errs:
            print(f"  {e}")
        return 1

    if args.dry_run:
        print("[dry-run] 未写文件")
        return 0

    if changes:
        trailing = "\n" if raw.endswith("\n") else ""
        MAPPING_PATH.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + trailing,
            encoding="utf-8",
        )
        print(f"已写入 {MAPPING_PATH}")

    print("[OK] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
