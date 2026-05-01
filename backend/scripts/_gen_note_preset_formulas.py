"""从附注模板的 check_presets 生成预设公式JSON，供公式管理中心一键导入"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PRESET_FORMULAS = {
    "balance": {
        "category": "logic_check",
        "description": "报表余额 = 附注合计",
        "formula_tpl": "REPORT('{bs_code}','期末') = NOTE('{title}','合计','期末')",
    },
    "sub_item": {
        "category": "logic_check",
        "description": "子项合计 = 合计行",
        "formula_tpl": "SUM(子项) = NOTE('{title}','合计','期末')",
    },
    "movement": {
        "category": "logic_check",
        "description": "期初 + 本期增加 - 本期减少 = 期末",
        "formula_tpl": "NOTE('{title}','期初','期初') + NOTE('{title}','本期增加','本期') - NOTE('{title}','本期减少','本期') = NOTE('{title}','期末','期末')",
    },
    "aging": {
        "category": "logic_check",
        "description": "各账龄段合计 = 总额",
        "formula_tpl": "SUM(账龄各段) = NOTE('{title}','合计','期末')",
    },
    "vertical_reconcile": {
        "category": "logic_check",
        "description": "纵向勾稽：上下级科目一致",
        "formula_tpl": "NOTE('{title}','小计','期末') = SUM(明细行)",
    },
    "book_value": {
        "category": "logic_check",
        "description": "原值 - 折旧/摊销 - 减值 = 账面价值",
        "formula_tpl": "NOTE('{title}','原值','期末') - NOTE('{title}','累计折旧','期末') - NOTE('{title}','减值准备','期末') = NOTE('{title}','账面价值','期末')",
    },
    "cross_check": {
        "category": "logic_check",
        "description": "跨表交叉核对",
        "formula_tpl": "NOTE('{title}','合计','期末') = WP('{wp_code}','审定数')",
    },
    "ecl_three_stage": {
        "category": "logic_check",
        "description": "预期信用损失三阶段校验",
        "formula_tpl": "NOTE('{title}','第一阶段','期末') + NOTE('{title}','第二阶段','期末') + NOTE('{title}','第三阶段','期末') = NOTE('{title}','合计','期末')",
    },
}

# 科目 → 报表行次编码映射（常用）
ACCOUNT_BS_MAP = {
    "货币资金": "BS-002", "应收票据": "BS-007", "应收账款": "BS-008",
    "预付款项": "BS-010", "其他应收款": "BS-012", "存货": "BS-013",
    "长期股权投资": "BS-020", "投资性房地产": "BS-021", "固定资产": "BS-022",
    "在建工程": "BS-023", "无形资产": "BS-025", "商誉": "BS-026",
    "短期借款": "BS-040", "应付票据": "BS-041", "应付账款": "BS-042",
    "应付职工薪酬": "BS-045", "应交税费": "BS-046", "长期借款": "BS-055",
}

# 科目 → 底稿编码映射
ACCOUNT_WP_MAP = {
    "货币资金": "E1-1", "应收账款": "D2-1", "存货": "G1-1",
    "固定资产": "H1-1", "无形资产": "I1-1", "长期股权投资": "J1-1",
    "短期借款": "K1-1", "应付账款": "F1-1", "应付职工薪酬": "L1-1",
}


def generate():
    soe_path = os.path.join(BASE, "data", "note_template_soe.json")
    listed_path = os.path.join(BASE, "data", "note_template_listed.json")

    with open(soe_path, "r", encoding="utf-8") as f:
        soe = json.load(f)
    with open(listed_path, "r", encoding="utf-8") as f:
        listed = json.load(f)

    result = {"soe": [], "listed": []}

    for ttype, sections in [("soe", soe["sections"]), ("listed", listed["sections"])]:
        for s in sections:
            presets = s.get("check_presets", [])
            if not presets:
                continue
            title = s["section_title"]
            section_num = s["section_number"]
            bs_code = ACCOUNT_BS_MAP.get(title, "BS-???")
            wp_code = ACCOUNT_WP_MAP.get(title, "??-1")

            for p in presets:
                info = PRESET_FORMULAS.get(p, {})
                formula = info.get("formula_tpl", p).format(
                    title=title, bs_code=bs_code, wp_code=wp_code
                )
                result[ttype].append({
                    "note_section": section_num,
                    "section_title": title,
                    "check_type": p,
                    "category": info.get("category", "logic_check"),
                    "description": title + "：" + info.get("description", p),
                    "formula": formula,
                    "source": "check_presets." + p,
                })

    out_path = os.path.join(BASE, "data", "note_check_preset_formulas.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"SOE: {len(result['soe'])} formulas")
    print(f"Listed: {len(result['listed'])} formulas")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    generate()
