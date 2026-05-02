"""Upgrade enhanced fine rules to hand-crafted level by adding layout definitions.

Reads each file, finds the summary sheet_rule, and adds proper layout.columns
based on the existing columns/key_rows data.
"""
import json
from pathlib import Path

rules_dir = Path(__file__).resolve().parent.parent / "data" / "wp_fine_rules"

# Standard audit table column templates
STANDARD_10COL = {
    "label_col": 1,
    "columns": {
        "opening_unadjusted": {"col": 2, "label": "期初未审数"},
        "opening_adjustment": {"col": 3, "label": "期初账项调整"},
        "opening_audited": {"col": 4, "label": "期初审定数"},
        "closing_unadjusted": {"col": 5, "label": "期末未审数"},
        "closing_adjustment": {"col": 6, "label": "期末账项调整"},
        "closing_audited": {"col": 7, "label": "期末审定数"},
        "change_amount": {"col": 8, "label": "变动额"},
        "change_rate": {"col": 9, "label": "变动率"},
        "reason": {"col": 10, "label": "原因分析"},
    },
}

# 11-col with reclass (D2/D1/K1 style)
STANDARD_11COL_RECLASS = {
    "label_col": 1,
    "columns": {
        "opening_unadjusted": {"col": 2, "label": "期初未审数"},
        "opening_adjustment": {"col": 3, "label": "期初账项调整"},
        "opening_reclass": {"col": 4, "label": "期初重分类调整"},
        "opening_audited": {"col": 5, "label": "期初审定数"},
        "closing_unadjusted": {"col": 6, "label": "期末未审数"},
        "closing_adjustment": {"col": 7, "label": "期末账项调整"},
        "closing_reclass": {"col": 8, "label": "期末重分类调整"},
        "closing_audited": {"col": 9, "label": "期末审定数"},
        "change_amount": {"col": 10, "label": "变动额"},
        "change_rate": {"col": 11, "label": "变动率"},
    },
}

# Movement table (H1/H2/I1 style: 原值/折旧/减值/净值)
MOVEMENT_13COL = {
    "label_col": 1,
    "columns": {
        "opening_balance": {"col": 2, "label": "期初余额"},
        "increase_purchase": {"col": 3, "label": "本期增加-购置"},
        "increase_transfer": {"col": 4, "label": "本期增加-在建转入"},
        "increase_other": {"col": 5, "label": "本期增加-其他"},
        "decrease_disposal": {"col": 6, "label": "本期减少-处置"},
        "decrease_other": {"col": 7, "label": "本期减少-其他"},
        "closing_balance": {"col": 8, "label": "期末余额"},
        "audit_adjustment": {"col": 9, "label": "审计调整"},
        "closing_audited": {"col": 10, "label": "期末审定数"},
        "index_ref": {"col": 11, "label": "索引"},
    },
}

# Income/expense table (D4/F5/K8/K9 style)
INCOME_EXPENSE_9COL = {
    "label_col": 1,
    "columns": {
        "current_unadjusted": {"col": 2, "label": "本期未审数"},
        "current_adjustment": {"col": 3, "label": "本期账项调整"},
        "current_reclass": {"col": 4, "label": "本期重分类调整"},
        "current_audited": {"col": 5, "label": "本期审定数"},
        "prior_unadjusted": {"col": 6, "label": "上期未审数"},
        "prior_audited": {"col": 7, "label": "上期审定数"},
        "change_amount": {"col": 8, "label": "变动额"},
        "change_rate": {"col": 9, "label": "变动率"},
    },
}

# Equity table (M1/M2 style)
EQUITY_10COL = {
    "label_col": 1,
    "columns": {
        "opening_unadjusted": {"col": 2, "label": "期初未审数"},
        "opening_adjustment": {"col": 3, "label": "期初账项调整"},
        "opening_audited": {"col": 4, "label": "期初审定数"},
        "closing_unadjusted": {"col": 5, "label": "期末未审数"},
        "closing_adjustment": {"col": 6, "label": "期末账项调整"},
        "closing_audited": {"col": 7, "label": "期末审定数"},
        "change_amount": {"col": 8, "label": "变动额"},
        "change_rate": {"col": 9, "label": "变动率"},
        "reason": {"col": 10, "label": "原因分析"},
    },
}

# Map wp_code -> layout template
LAYOUT_MAP = {
    # Balance sheet - assets (standard 10-col)
    "D3": STANDARD_10COL,
    "D5": STANDARD_10COL,
    "D6": STANDARD_10COL,
    "D7": STANDARD_10COL,
    "G2": STANDARD_10COL,
    "G4": STANDARD_10COL,
    "G5": STANDARD_10COL,
    "G6": STANDARD_10COL,
    "G7": STANDARD_10COL,
    "G8": STANDARD_10COL,
    "G9": STANDARD_10COL,
    "K2": STANDARD_10COL,
    "N1": STANDARD_10COL,
    "N3": STANDARD_10COL,
    # Balance sheet - liabilities (with reclass)
    "F3": STANDARD_11COL_RECLASS,
    "K3": STANDARD_11COL_RECLASS,
    "K5": STANDARD_10COL,
    "K6": STANDARD_10COL,
    "K7": STANDARD_10COL,
    "L2": STANDARD_10COL,
    "L3": STANDARD_10COL,
    "L4": STANDARD_10COL,
    "L5": STANDARD_10COL,
    "L6": STANDARD_10COL,
    "L7": STANDARD_10COL,
    "J2": STANDARD_10COL,
    "M1": STANDARD_10COL,
    # Movement tables
    "H2": MOVEMENT_13COL,
    "H3": MOVEMENT_13COL,
    "H4": MOVEMENT_13COL,
    "H6": STANDARD_10COL,
    "H8": MOVEMENT_13COL,
    "H9": STANDARD_10COL,
    "I2": MOVEMENT_13COL,
    "I3": STANDARD_10COL,
    # Income/expense
    "F5": INCOME_EXPENSE_9COL,
    "G10": STANDARD_10COL,
    "G11": INCOME_EXPENSE_9COL,
    "G13": INCOME_EXPENSE_9COL,
    "G14": INCOME_EXPENSE_9COL,
    "H10": INCOME_EXPENSE_9COL,
    "K4": STANDARD_10COL,
    "K8": INCOME_EXPENSE_9COL,
    # Equity
    "M2": EQUITY_10COL,
}

upgraded = 0
skipped = 0

for fp in sorted(rules_dir.glob("*.json")):
    data = json.loads(fp.read_text(encoding="utf-8"))
    code = data.get("wp_code", "")
    
    if code not in LAYOUT_MAP:
        continue
    
    sheet_rules = data.get("sheet_rules", [])
    
    # Find the summary sheet rule
    summary_rule = None
    for sr in sheet_rules:
        if sr.get("type") == "summary":
            summary_rule = sr
            break
    
    if not summary_rule:
        # Try first rule with code ending in -1
        for sr in sheet_rules:
            sr_code = sr.get("code", "")
            if sr_code.endswith("-1") or sr_code.endswith("A"):
                summary_rule = sr
                break
    
    if not summary_rule:
        skipped += 1
        continue
    
    # Check if already has layout
    if summary_rule.get("layout") and summary_rule["layout"].get("columns"):
        # Already has layout, skip
        skipped += 1
        continue
    
    # Add layout
    layout = LAYOUT_MAP[code]
    
    # If the rule already has a 'columns' dict at top level, merge it
    existing_cols = summary_rule.get("columns", {})
    if existing_cols and not summary_rule.get("layout"):
        # Has old-style columns, convert to layout format
        summary_rule["layout"] = {
            "label_col": 1,
            "columns": existing_cols,
        }
    else:
        summary_rule["layout"] = layout
    
    # Write back
    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    upgraded += 1
    name = data.get("name", "")
    ncols = len(summary_rule["layout"]["columns"])
    print(f"Upgraded {code:8s} {name:24s} -> {ncols} columns in layout")

print(f"\nDone: {upgraded} upgraded, {skipped} skipped")
