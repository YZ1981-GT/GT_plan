"""一次性脚本：扩充 D 类 wp_code 到完整覆盖 (~55 条)

执行：python backend/scripts/fix/_expand_d_class_wp_codes.py
"""
import json
from pathlib import Path

MAPPING_FILE = Path(__file__).parent.parent.parent / "data" / "wp_account_mapping.json"

# ─── 新增 D 类条目（design 2.1 表格） ───────────────────────────────────────
NEW_D_ENTRIES = [
    # D0 辅助
    {"wp_code": "D0-1", "cycle": "D", "wp_name": "函证结果汇总", "account_codes": ["1121", "1122"], "account_name": "函证汇总", "report_row": None, "note_section": None},
    {"wp_code": "D0-2", "cycle": "D", "wp_name": "核实被函证单位", "account_codes": ["1121", "1122"], "account_name": "函证核实", "report_row": None, "note_section": None},
    {"wp_code": "D0-3", "cycle": "D", "wp_name": "跟函控制", "account_codes": ["1121", "1122"], "account_name": "跟函控制", "report_row": None, "note_section": None},
    {"wp_code": "D0-4", "cycle": "D", "wp_name": "差异调节", "account_codes": ["1121", "1122"], "account_name": "差异调节", "report_row": None, "note_section": None},
    {"wp_code": "D0-5", "cycle": "D", "wp_name": "替代程序", "account_codes": ["1121", "1122"], "account_name": "替代程序", "report_row": None, "note_section": None},
    # D1 应收票据
    {"wp_code": "D1-1", "cycle": "D", "wp_name": "应收票据审定表", "account_codes": ["1121"], "account_name": "应收票据", "report_row": "BS-004", "note_section": "五、2"},
    {"wp_code": "D1-2", "cycle": "D", "wp_name": "应收票据原值明细（按类）", "account_codes": ["1121"], "account_name": "应收票据明细", "report_row": None, "note_section": None},
    {"wp_code": "D1-3", "cycle": "D", "wp_name": "应收票据原值明细（按客户）", "account_codes": ["1121"], "account_name": "应收票据明细", "report_row": None, "note_section": None},
    {"wp_code": "D1-4", "cycle": "D", "wp_name": "应收票据坏账准备", "account_codes": ["1121"], "account_name": "应收票据坏账", "report_row": None, "note_section": None},
    # D2 应收账款补充
    {"wp_code": "D2-1", "cycle": "D", "wp_name": "应收账款审定表", "account_codes": ["1122"], "account_name": "应收账款", "report_row": "BS-005", "note_section": "五、3"},
    {"wp_code": "D2-5", "cycle": "D", "wp_name": "应收账款分析程序", "account_codes": ["1122"], "account_name": "应收账款分析", "report_row": None, "note_section": None},
    {"wp_code": "D2-6", "cycle": "D", "wp_name": "应收账款检查", "account_codes": ["1122"], "account_name": "应收账款检查", "report_row": None, "note_section": None},
    # D3 预收账款
    {"wp_code": "D3-1", "cycle": "D", "wp_name": "预收账款审定表", "account_codes": ["2203"], "account_name": "预收款项", "report_row": "BS-034", "note_section": "五、18"},
    {"wp_code": "D3-2", "cycle": "D", "wp_name": "预收账款明细表", "account_codes": ["2203"], "account_name": "预收款项明细", "report_row": None, "note_section": None},
    # D4 营业收入
    {"wp_code": "D4-1", "cycle": "D", "wp_name": "营业收入审定表", "account_codes": ["6001", "6051"], "account_name": "营业收入", "report_row": "IS-001", "note_section": "五、29"},
    {"wp_code": "D4-2", "cycle": "D", "wp_name": "收入明细（按类别）", "account_codes": ["6001", "6051"], "account_name": "收入明细", "report_row": None, "note_section": None},
    {"wp_code": "D4-3", "cycle": "D", "wp_name": "收入明细（按客户）", "account_codes": ["6001", "6051"], "account_name": "收入明细", "report_row": None, "note_section": None},
    {"wp_code": "D4-4", "cycle": "D", "wp_name": "收入明细（按月份）", "account_codes": ["6001", "6051"], "account_name": "收入明细", "report_row": None, "note_section": None},
    {"wp_code": "D4-5", "cycle": "D", "wp_name": "营业收入会计政策", "account_codes": ["6001"], "account_name": "收入政策", "report_row": None, "note_section": None},
    {"wp_code": "D4-6", "cycle": "D", "wp_name": "营业收入分析程序", "account_codes": ["6001", "6051"], "account_name": "收入分析", "report_row": None, "note_section": None},
    {"wp_code": "D4-12", "cycle": "D", "wp_name": "营业收入合同检查", "account_codes": ["6001"], "account_name": "合同检查", "report_row": None, "note_section": None},
    {"wp_code": "D4-13", "cycle": "D", "wp_name": "主营业务收入检查", "account_codes": ["6001"], "account_name": "收入检查", "report_row": None, "note_section": None},
    {"wp_code": "D4-21", "cycle": "D", "wp_name": "营业收入关联方检查", "account_codes": ["6001"], "account_name": "关联方检查", "report_row": None, "note_section": None},
    {"wp_code": "D4-22", "cycle": "D", "wp_name": "营业收入IPO舞弊应对", "account_codes": ["6001"], "account_name": "IPO舞弊应对", "report_row": None, "note_section": None, "applicable_when": {"business_category": ["ipo", "listed", "neeq", "restructuring"]}},
    {"wp_code": "D4-33", "cycle": "D", "wp_name": "其他业务收入", "account_codes": ["6051"], "account_name": "其他业务收入", "report_row": None, "note_section": None},
    # D5 应收款项融资
    {"wp_code": "D5-2", "cycle": "D", "wp_name": "应收款项融资明细", "account_codes": ["1124"], "account_name": "应收款项融资明细", "report_row": None, "note_section": None},
    # D6 合同资产
    {"wp_code": "D6-2", "cycle": "D", "wp_name": "合同资产明细表（详细）", "account_codes": ["1141"], "account_name": "合同资产明细", "report_row": None, "note_section": None},
    {"wp_code": "D6-3", "cycle": "D", "wp_name": "合同资产减值准备明细", "account_codes": ["1141"], "account_name": "合同资产减值", "report_row": None, "note_section": None},
    {"wp_code": "D6-4", "cycle": "D", "wp_name": "合同资产调整分录汇总", "account_codes": ["1141"], "account_name": "合同资产调整", "report_row": None, "note_section": None},
    {"wp_code": "D6-5", "cycle": "D", "wp_name": "合同资产关联方检查", "account_codes": ["1141"], "account_name": "合同资产关联方", "report_row": None, "note_section": None},
    {"wp_code": "D6-6", "cycle": "D", "wp_name": "合同资产检查表", "account_codes": ["1141"], "account_name": "合同资产检查", "report_row": None, "note_section": None},
    {"wp_code": "D6-7", "cycle": "D", "wp_name": "合同资产减值准备政策检查", "account_codes": ["1141"], "account_name": "合同资产政策", "report_row": None, "note_section": None},
    {"wp_code": "D6-8", "cycle": "D", "wp_name": "合同资产减值测算", "account_codes": ["1141"], "account_name": "合同资产测算", "report_row": None, "note_section": None},
    {"wp_code": "D6-9", "cycle": "D", "wp_name": "合同资产减值转回核销检查", "account_codes": ["1141"], "account_name": "合同资产核销", "report_row": None, "note_section": None},
    # D7 合同负债
    {"wp_code": "D7-2", "cycle": "D", "wp_name": "合同负债明细（详细）", "account_codes": ["2205"], "account_name": "合同负债明细", "report_row": None, "note_section": None},
]

# ─── Task 2 修正：D5/D6/D7 名称错配 ───────────────────────────────────────
NAME_FIXES = {
    "D5": "应收款项融资审定表",   # was "合同资产审定表"
    "D6": "合同资产审定表",       # was "合同负债审定表"
    "D7": "合同负债审定表",       # was "应收款项融资审定表"
}

# 同时修正 account_codes 和 account_name
ACCOUNT_FIXES = {
    "D5": {"account_codes": ["1124"], "account_name": "应收款项融资"},
    "D6": {"account_codes": ["1141"], "account_name": "合同资产"},
    "D7": {"account_codes": ["2205"], "account_name": "合同负债"},
}


def main():
    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    existing_codes = {m["wp_code"] for m in data["mappings"]}
    print(f"当前 D 类条目: {sorted(c for c in existing_codes if c.startswith('D'))}")
    print(f"总条目数: {len(data['mappings'])}")

    # Task 2: Fix D5/D6/D7 names
    fixes_applied = 0
    for entry in data["mappings"]:
        if entry["wp_code"] in NAME_FIXES:
            old_name = entry["wp_name"]
            new_name = NAME_FIXES[entry["wp_code"]]
            if old_name != new_name:
                print(f"  修正 {entry['wp_code']}: '{old_name}' → '{new_name}'")
                entry["wp_name"] = new_name
                fixes_applied += 1
        if entry["wp_code"] in ACCOUNT_FIXES:
            fix = ACCOUNT_FIXES[entry["wp_code"]]
            entry["account_codes"] = fix["account_codes"]
            entry["account_name"] = fix["account_name"]

    # Task 1: Add missing entries
    added = 0
    for new_entry in NEW_D_ENTRIES:
        if new_entry["wp_code"] not in existing_codes:
            data["mappings"].append(new_entry)
            existing_codes.add(new_entry["wp_code"])
            added += 1
        else:
            print(f"  跳过已存在: {new_entry['wp_code']}")

    with open(MAPPING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    total_d = len([m for m in data["mappings"] if m.get("cycle") == "D"])
    print(f"\n完成: 修正名称 {fixes_applied} 条, 新增 {added} 条")
    print(f"D 类总计: {total_d} 条")
    print(f"总条目数: {len(data['mappings'])}")


if __name__ == "__main__":
    main()
