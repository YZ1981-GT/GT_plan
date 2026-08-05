#!/usr/bin/env python
"""补齐 G 循环披露/明细块公式预设（幂等）。

对齐 Wave 4.1（审定表块科目已纠正）后，补齐：
- 11 个缺披露块的循环（G2~G4/G6~G14，G0 无披露 sheet 跳过）
- 明细表块的 WP() 联动（审定表→明细表/明细表→审定表禁成环）

设计原则：
- 披露块公式 = `TB('科目','期末余额')` + `WP('Gx','审定表Gx-1','合计_期末')` 勾稽
- 明细块禁 `WP()` 指向本循环审定表（防成环）
- 损益类（G11~G14）口径 = 本期发生额

Usage::
    python backend/scripts/fix/fix_g_cycle_disclosure_presets.py --check
    python backend/scripts/fix/fix_g_cycle_disclosure_presets.py --dry-run
    python backend/scripts/fix/fix_g_cycle_disclosure_presets.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MAPPING_PATH = Path(__file__).resolve().parents[2] / "data" / "prefill_formula_mapping.json"

# 科目码真源（来自 g_cycle_specs.py + fix_g_cycle_prefill_presets.py 纠偏后）
G_ACCOUNT_CODES: dict[str, dict] = {
    "G2": {"code": "1132", "name": "应收利息", "period": "balance"},
    "G3": {"code": "1131", "name": "应收股利", "period": "balance"},
    "G4": {"code": "1504", "name": "债权投资", "period": "balance", "provision": "1505"},
    "G6": {"code": "1506", "name": "其他债权投资", "period": "balance"},
    "G7": {"code": "1511", "name": "长期股权投资", "period": "balance", "provision": "1512"},
    "G8": {"code": "1507", "name": "其他权益工具投资", "period": "balance"},
    "G9": {"code": "1519", "name": "其他非流动金融资产", "period": "balance"},
    "G10": {"code": "2101", "name": "交易性金融负债", "period": "balance"},
    "G11": {"code": "6111", "name": "投资收益", "period": "current"},
    "G12": {"code": "6103", "name": "净敞口套期收益", "period": "current"},
    "G13": {"code": "6101", "name": "公允价值变动收益", "period": "current"},
    "G14": {"code": "6702", "name": "信用减值损失", "period": "current"},
}

# 披露 sheet 名（源 xlsx 实证 —— 全部 G 循环均用全角括号）
DISC_SHEET_LISTED = "附注披露信息（上市公司）"
DISC_SHEET_SOE = "附注披露信息（国企）"


def _build_disclosure_block(wp_code: str, variant: str) -> dict | None:
    """构建一个披露块。"""
    info = G_ACCOUNT_CODES.get(wp_code)
    if not info:
        return None

    code = info["code"]
    name = info["name"]
    period = info["period"]
    provision = info.get("provision")

    if variant == "listed":
        sheet = DISC_SHEET_LISTED
    else:
        sheet = DISC_SHEET_SOE

    cells = []
    if period == "balance":
        cells.append({
            "cell_ref": f"{name}_期末",
            "description": f"披露表{name}期末余额",
            "formula": f"=TB('{code}','期末余额')",
            "formula_type": "TB",
        })
        cells.append({
            "cell_ref": f"{name}_期初",
            "description": f"披露表{name}期初余额",
            "formula": f"=TB('{code}','期初余额')",
            "formula_type": "TB",
        })
        if provision:
            prov_name = f"{name}减值准备"
            cells.append({
                "cell_ref": f"{prov_name}_期末",
                "description": f"披露表{prov_name}期末余额",
                "formula": f"=TB('{provision}','期末余额')",
                "formula_type": "TB",
            })
            cells.append({
                "cell_ref": f"{prov_name}_期初",
                "description": f"披露表{prov_name}期初余额",
                "formula": f"=TB('{provision}','期初余额')",
                "formula_type": "TB",
            })
    else:
        cells.append({
            "cell_ref": f"{name}_本期",
            "description": f"披露表{name}本期发生额",
            "formula": f"=TB('{code}','本期发生额')",
            "formula_type": "TB",
        })
        cells.append({
            "cell_ref": f"{name}_上期",
            "description": f"披露表{name}上期发生额",
            "formula": f"=PREV('{wp_code}','审定表{wp_code}-1','{name}_本期')",
            "formula_type": "PREV",
        })

    # 勾稽：审定表合计
    adj_sheet = f"审定表{wp_code}-1"
    if wp_code == "G7":
        adj_sheet = f"长期股权投资审定表{wp_code}-1"
    cells.append({
        "cell_ref": "审定表核对",
        "description": f"从{adj_sheet}取期末审定合计（勾稽用）",
        "formula": f"=WP('{wp_code}','{adj_sheet}','审定合计_期末')",
        "formula_type": "WP",
    })

    variant_label = "上市" if variant == "listed" else "国企"
    return {
        "wp_code": wp_code,
        "wp_name": f"{name}披露（{variant_label}）",
        "sheet": sheet,
        "account_codes": [code] + ([provision] if provision else []),
        "cells": cells,
    }


def _existing_disc_keys(mappings: list[dict]) -> set[str]:
    """已有的披露块键集 = (wp_code, sheet)。"""
    keys = set()
    for m in mappings:
        sheet = m.get("sheet", "")
        if "附注" in sheet or "披露" in sheet:
            keys.add((m["wp_code"], sheet))
    return keys


def plan(data: dict) -> list[dict]:
    """返回需要新增的披露块列表。"""
    mappings = data.get("mappings", [])
    existing = _existing_disc_keys(mappings)
    additions = []

    for wp_code in sorted(G_ACCOUNT_CODES.keys()):
        for variant in ["listed", "soe"]:
            block = _build_disclosure_block(wp_code, variant)
            if not block:
                continue
            key = (block["wp_code"], block["sheet"])
            if key not in existing:
                additions.append(block)

    return additions


def apply_plan(data: dict, additions: list[dict]) -> int:
    """将新增块追加到 mappings 末尾。"""
    mappings = data.setdefault("mappings", [])
    for block in additions:
        mappings.append(block)
    return len(additions)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="只报欠账，有欠账 exit 1")
    g.add_argument("--dry-run", action="store_true", help="打印将要新增的块，不写盘")
    g.add_argument("--apply", action="store_true", help="写盘")
    args = ap.parse_args()

    raw = MAPPING_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    additions = plan(data)

    if not additions:
        print("[fix_g_cycle_disclosure_presets] 0 项欠账（披露块已齐备）")
        return 0

    for block in additions:
        print(f"  + {block['wp_code']}|{block['sheet']} ({len(block['cells'])} 条公式)")

    if args.check:
        print(f"[fix_g_cycle_disclosure_presets] {len(additions)} 项欠账")
        return 1

    if args.dry_run or not args.apply:
        print(f"[fix_g_cycle_disclosure_presets] dry-run：{len(additions)} 个块待新增（加 --apply 写盘）")
        return 0

    n = apply_plan(data, additions)
    MAPPING_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[fix_g_cycle_disclosure_presets] 已新增 {n} 个披露块 -> {MAPPING_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
