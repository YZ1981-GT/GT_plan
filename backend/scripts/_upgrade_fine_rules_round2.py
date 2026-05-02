"""Round 2: Upgrade remaining 23 enhanced files that have header_rows but no layout."""
import json
from pathlib import Path

rules_dir = Path(__file__).resolve().parent.parent / "data" / "wp_fine_rules"

# Standard templates
STD_10 = {
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

STD_11_RECLASS = {
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

INCOME_9 = {
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

MOVEMENT_10 = {
    "label_col": 1,
    "columns": {
        "opening_balance": {"col": 2, "label": "期初余额"},
        "increase_purchase": {"col": 3, "label": "本期增加-购置"},
        "increase_other": {"col": 4, "label": "本期增加-其他"},
        "decrease_disposal": {"col": 5, "label": "本期减少-处置"},
        "decrease_other": {"col": 6, "label": "本期减少-其他"},
        "closing_balance": {"col": 7, "label": "期末余额"},
        "audit_adjustment": {"col": 8, "label": "审计调整"},
        "closing_audited": {"col": 9, "label": "期末审定数"},
        "index_ref": {"col": 10, "label": "索引"},
    },
}

# Map remaining codes to templates
LAYOUT_MAP = {
    # Balance sheet items (standard)
    "F4": STD_11_RECLASS,  # 应付账款 (has reclass)
    "K1": STD_11_RECLASS,  # 其他应收款 (has reclass)
    "L1": STD_10,          # 短期借款
    "N2": STD_10,          # 应交税费
    "J1": STD_10,          # 应付职工薪酬
    "I4": MOVEMENT_10,     # 长期待摊费用 (movement)
    "I5": STD_10,          # 其他非流动资产
    "M3": STD_10,          # 库存股
    "M4": STD_10,          # 资本公积
    "M5": STD_10,          # 盈余公积
    "M6": STD_10,          # 未分配利润
    "M7": STD_10,          # 专项储备
    "M8": STD_10,          # 一般风险准备
    "M9": STD_10,          # 其他综合收益
    "M10": STD_10,         # 其他权益工具
    # Income/expense items
    "I6": INCOME_9,        # 研发费用
    "K10": INCOME_9,       # 其他收益
    "K11": INCOME_9,       # 资产减值损失
    "K12": INCOME_9,       # 营业外收入
    "K13": INCOME_9,       # 营业外支出
    "L8": INCOME_9,        # 财务费用
    "N4": INCOME_9,        # 税金及附加
    "N5": INCOME_9,        # 所得税费用
}

upgraded = 0
for fp in sorted(rules_dir.glob("*.json")):
    data = json.loads(fp.read_text(encoding="utf-8"))
    code = data.get("wp_code", "")
    if code not in LAYOUT_MAP:
        continue
    
    sheet_rules = data.get("sheet_rules", [])
    
    # Find summary rule
    summary = None
    for sr in sheet_rules:
        if sr.get("type") == "summary":
            summary = sr
            break
    if not summary:
        for sr in sheet_rules:
            c = sr.get("code", "")
            if c.endswith("-1"):
                summary = sr
                break
    
    if not summary:
        print(f"SKIP {code}: no summary rule found")
        continue
    
    if summary.get("layout") and summary["layout"].get("columns"):
        print(f"SKIP {code}: already has layout")
        continue
    
    # If has old-style 'columns' at top level, wrap it
    existing = summary.get("columns", {})
    if existing:
        summary["layout"] = {"label_col": 1, "columns": existing}
    else:
        summary["layout"] = LAYOUT_MAP[code]
    
    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    upgraded += 1
    name = data.get("name", "")
    ncols = len(summary["layout"]["columns"])
    print(f"Upgraded {code:8s} {name:24s} -> {ncols} columns")

print(f"\nDone: {upgraded} upgraded")
