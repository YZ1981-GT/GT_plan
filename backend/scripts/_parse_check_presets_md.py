"""从附注模版/校验公式预设.md 解析所有校验公式，生成 note_check_preset_formulas.json

解析 markdown 表格格式：
| 编号 | 公式类型 | 校验公式 |
|------|----------|----------|
| F1-1 | 余额 | `报表.货币资金期末 = ①货币资金分类表.合计行.期末余额` |
"""
import re
import json


def parse_formulas_from_md(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    formulas = []
    current_account = ""
    current_account_num = ""
    current_table = ""
    
    for line in content.split("\n"):
        line = line.strip()
        
        # 匹配科目标题：### 1. 货币资金 或 ### 5. 应收账款
        m = re.match(r'^###\s+(\d+)[.、．]\s*(.+)', line)
        if m:
            current_account_num = m.group(1)
            current_account = m.group(2).strip()
            current_table = ""
            continue
        
        # 匹配表格标题：**① 货币资金分类表** 或 **②③④ 按坏账准备计提方法分类**
        m = re.match(r'^\*\*([①②③④⑤⑥⑦⑧⑨⑩]+)\s*(.+?)\*\*', line)
        if m:
            current_table = m.group(1) + " " + m.group(2).strip()
            continue
        
        # 匹配公式行：| F1-1 | 余额 | `...` |
        m = re.match(r'^\|\s*(F[\d]+-[\d]+\w*)\s*\|\s*(\S+)\s*\|\s*(.+?)\s*\|', line)
        if m:
            formula_id = m.group(1)
            formula_type = m.group(2)
            formula_expr = m.group(3).strip()
            # 清理 markdown 格式
            formula_expr = formula_expr.replace('`', '').strip()
            
            formulas.append({
                "id": formula_id,
                "account_num": current_account_num,
                "account_name": current_account,
                "table_name": current_table,
                "type": formula_type,
                "formula": formula_expr,
            })
    
    return formulas


def categorize(formula_type: str) -> str:
    """将公式类型映射到三分类"""
    if formula_type in ("余额", "交叉", "跨科目", "二级明细"):
        return "logic_check"
    elif formula_type in ("宽表", "纵向", "其中项"):
        return "auto_calc"
    elif formula_type in ("完整性", "LLM审核"):
        return "reasonability"
    return "logic_check"


def main():
    result = {}
    
    for ttype, md_path in [
        ("soe", "附注模版/国企版校验公式预设.md"),
        ("listed", "附注模版/上市版校验公式预设.md"),
    ]:
        formulas = parse_formulas_from_md(md_path)
        print(f"{ttype}: 解析到 {len(formulas)} 条公式")
        
        # 按科目统计
        accounts = {}
        for f in formulas:
            key = f["account_name"]
            if key not in accounts:
                accounts[key] = 0
            accounts[key] += 1
        
        for acc, count in sorted(accounts.items(), key=lambda x: -x[1])[:15]:
            print(f"  {acc}: {count}条")
        
        # 转换为输出格式
        output = []
        for f in formulas:
            output.append({
                "id": f["id"],
                "note_section": f"五、{f['account_num']}",
                "section_title": f["account_name"],
                "table_name": f["table_name"],
                "check_type": f["type"],
                "category": categorize(f["type"]),
                "description": f"{f['account_name']}：{f['formula'][:50]}",
                "formula": f["formula"],
                "source": f"check_presets_md.{f['id']}",
            })
        
        result[ttype] = output
    
    # 保存
    out_path = "backend/data/note_check_preset_formulas.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n已保存到 {out_path}")
    print(f"SOE: {len(result['soe'])} 条, Listed: {len(result['listed'])} 条")


if __name__ == "__main__":
    main()
