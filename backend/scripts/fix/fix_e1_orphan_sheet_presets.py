"""E1 孤儿 sheet 公式预设补齐（幂等脚本）

用法：
    python -m scripts.fix.fix_e1_orphan_sheet_presets --dry-run   # 预览变更
    python -m scripts.fix.fix_e1_orphan_sheet_presets --check     # 检查是否有欠账（CI 用）
    python -m scripts.fix.fix_e1_orphan_sheet_presets --apply     # 执行写入

补齐范围：
    - E1-15 利息收入月度分析（现有组件零预设）
    - E1-20 银行存款及其他货币资金应计利息测算
    - E1-26~E1-32 新接线 6 张 sheet（现金交易/银行账户/存款利息匹配/银行流水/董监高流水）
      E1-27/E1-28 也补（通用表已有 columns config，可锚 TB）

科目约束：BS-002 = TB('1001') + TB('1002') + TB('1012')，新增预设只引这三个码。
明细 sheet 禁 WP() 引审定表（防成环）。

@spec e1-orphan-components-wiring — Task 11
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "prefill_formula_mapping.json"

# 源 xlsx 的真实 tab 名（openpyxl 直读实证 2026-08-03）
E1_NEW_BLOCKS = [
    {
        "wp_code": "E1",
        "wp_name": "利息收入月度分析",
        "sheet": "利息收入月度分析E1-15",
        "account_codes": ["1002"],
        "description": "E1-15 利息收入月度分析。按银行账户每月余额×利率测算利息，与账面利息收入核对。",
        "cells": [
            {
                "cell_ref": "银行存款余额",
                "formula": "TB('1002','期末余额')",
                "formula_type": "TB",
                "description": "银行存款期末余额（1002），用于利率测算基数",
            },
            {
                "cell_ref": "银行存款期初余额",
                "formula": "TB('1002','期初余额')",
                "formula_type": "TB",
                "description": "银行存款期初余额（1002），用于年度平均余额计算",
            },
        ],
    },
    {
        "wp_code": "E1",
        "wp_name": "应计利息测算",
        "sheet": "银行存款及其他货币资金应计利息测算E1-20",
        "account_codes": ["1002", "1012"],
        "description": "E1-20 应计利息测算。按余额×利率÷360 逐日测算应计利息。利率/天数由审计师手工录入。",
        "cells": [
            {
                "cell_ref": "银行存款余额",
                "formula": "TB('1002','期末余额')",
                "formula_type": "TB",
                "description": "银行存款期末余额，作为利息测算基数",
            },
            {
                "cell_ref": "其他货币资金余额",
                "formula": "TB('1012','期末余额')",
                "formula_type": "TB",
                "description": "其他货币资金期末余额（结构性存款等），作为利息测算基数",
            },
            {
                "cell_ref": "利率",
                "formula": "PLACEHOLDER",
                "formula_type": "PLACEHOLDER",
                "description": "年利率由审计师根据银行合同/回函手工录入，四表推不出",
            },
        ],
    },
    {
        "wp_code": "E1",
        "wp_name": "现金交易分析",
        "sheet": "现金交易分析E1-26",
        "account_codes": ["1001"],
        "description": "E1-26 现金交易分析（IPO/舞弊应对）。分析现金收支异常模式。",
        "cells": [
            {
                "cell_ref": "库存现金余额",
                "formula": "TB('1001','期末余额')",
                "formula_type": "TB",
                "description": "库存现金期末余额，用于与现金交易规模对比",
            },
        ],
    },
    {
        "wp_code": "E1",
        "wp_name": "现金截止测试",
        "sheet": "现金截止测试E1-27",
        "account_codes": ["1001"],
        "description": "E1-27 现金截止测试（IPO/舞弊应对）。核查期末现金收支跨期。",
        "cells": [
            {
                "cell_ref": "库存现金余额",
                "formula": "TB('1001','期末余额')",
                "formula_type": "TB",
                "description": "库存现金期末审定余额，作为截止金额参照基数",
            },
        ],
    },
    {
        "wp_code": "E1",
        "wp_name": "现金收支检查表",
        "sheet": "现金收支检查表E1-28",
        "account_codes": ["1001"],
        "description": "E1-28 现金收支检查表（IPO/舞弊应对）。检查大额现金收支合理性。",
        "cells": [
            {
                "cell_ref": "库存现金余额",
                "formula": "TB('1001','期末余额')",
                "formula_type": "TB",
                "description": "库存现金期末余额，用于大额收支占比计算",
            },
        ],
    },
    {
        "wp_code": "E1",
        "wp_name": "银行账户分析",
        "sheet": "银行账户分析E1-29",
        "account_codes": ["1002"],
        "description": "E1-29 银行账户分析（IPO/舞弊应对）。多维度分析银行账户开立地、多年指标。",
        "cells": [
            {
                "cell_ref": "银行存款余额",
                "formula": "TB('1002','期末余额')",
                "formula_type": "TB",
                "description": "银行存款期末余额，用于各账户占比分析",
            },
        ],
    },
    {
        "wp_code": "E1",
        "wp_name": "存款规模与利息收入匹配性分析",
        "sheet": "存款规模与利息收入匹配性分析E1-30",
        "account_codes": ["1002"],
        "description": "E1-30 存款规模与利息收入匹配性（IPO/舞弊应对）。按日余额×年利率/360 测算。",
        "cells": [
            {
                "cell_ref": "银行存款余额",
                "formula": "TB('1002','期末余额')",
                "formula_type": "TB",
                "description": "银行存款期末余额，用于与测算利息收入匹配性对比",
            },
        ],
    },
    {
        "wp_code": "E1",
        "wp_name": "银行流水双向核对表",
        "sheet": "银行流水双向核对表E1-31",
        "account_codes": ["1002"],
        "description": "E1-31 银行流水双向核对（IPO/舞弊应对）。账→流/流→账双向匹配。明细 sheet 禁 WP() 防环。",
        "cells": [
            {
                "cell_ref": "银行存款余额",
                "formula": "TB('1002','期末余额')",
                "formula_type": "TB",
                "description": "银行存款期末余额，用于流水覆盖率计算基数",
            },
        ],
    },
    {
        "wp_code": "E1",
        "wp_name": "董监高及关键岗位流水核查",
        "sheet": "董监高及关键岗位流水核查E1-32",
        "account_codes": ["1002"],
        "description": "E1-32 董监高关键岗位流水核查（IPO/舞弊应对）。明细 sheet 禁 WP() 防环。",
        "cells": [
            {
                "cell_ref": "银行存款余额",
                "formula": "TB('1002','期末余额')",
                "formula_type": "TB",
                "description": "银行存款期末余额参照（核查金额占比用）",
            },
        ],
    },
]

# BS-002 解析出的合法科目集合
VALID_ACCOUNT_CODES = {"1001", "1002", "1012"}


def validate_blocks() -> list[str]:
    """校验新增 blocks 的科目合规性。"""
    errors = []
    for block in E1_NEW_BLOCKS:
        for code in block.get("account_codes", []):
            if code not in VALID_ACCOUNT_CODES:
                errors.append(f"{block['sheet']}: account_code '{code}' not in BS-002 set {VALID_ACCOUNT_CODES}")
        for cell in block.get("cells", []):
            formula = cell.get("formula", "")
            # Check no WP() reference to E1-1 (prevent cycle)
            if "WP(" in formula and "E1-1" in formula:
                errors.append(f"{block['sheet']}: cell '{cell['cell_ref']}' has WP() referencing E1-1 (cycle risk)")
    return errors


def load_data() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def find_existing_sheets(data: dict) -> set[str]:
    """返回已有 E1 blocks 的 sheet 名集合。"""
    mappings = data.get("mappings", [])
    return {
        m["sheet"]
        for m in mappings
        if isinstance(m, dict) and m.get("wp_code") == "E1"
    }


def compute_plan(data: dict) -> list[dict]:
    """计算需要新增的 blocks。"""
    existing = find_existing_sheets(data)
    return [b for b in E1_NEW_BLOCKS if b["sheet"] not in existing]


def apply_plan(data: dict, plan: list[dict]) -> dict:
    """把 plan 里的 blocks 追加到 mappings。"""
    mappings = data.get("mappings", [])
    mappings.extend(plan)
    data["mappings"] = mappings
    return data


def round_trip_check(data: dict) -> bool:
    """验证 json.dumps 能逐字复现原文。"""
    original = DATA_PATH.read_text(encoding="utf-8")
    serialized = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    return serialized == original


def main():
    import argparse
    parser = argparse.ArgumentParser(description="E1 orphan sheet preset补齐")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="预览变更")
    group.add_argument("--check", action="store_true", help="检查欠账（CI）")
    group.add_argument("--apply", action="store_true", help="执行写入")
    args = parser.parse_args()

    # Validate block definitions
    errors = validate_blocks()
    if errors:
        print("[ERR] Block validation errors:")
        for e in errors:
            print(f"  {e}")
        sys.exit(2)

    data = load_data()
    plan = compute_plan(data)

    if args.check:
        if plan:
            print(f"[ERR] {len(plan)} blocks 未补齐:")
            for b in plan:
                print(f"  {b['sheet']}")
            sys.exit(1)
        else:
            print(f"[OK] E1 orphan sheet presets: 0 欠账（{len(E1_NEW_BLOCKS)} blocks 已全部就位）")
            sys.exit(0)

    if args.dry_run:
        if not plan:
            print("[OK] 无需变更（所有 blocks 已存在）")
            sys.exit(0)
        print(f"将新增 {len(plan)} blocks:")
        for b in plan:
            print(f"  + {b['sheet']} ({len(b['cells'])} cells)")
        sys.exit(0)

    if args.apply:
        if not plan:
            print("[OK] 无需变更")
            sys.exit(0)
        data = apply_plan(data, plan)
        output = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        DATA_PATH.write_text(output, encoding="utf-8")
        print(f"[OK] 已写入 {len(plan)} blocks")
        for b in plan:
            print(f"  + {b['sheet']}")


if __name__ == "__main__":
    main()
