"""从附注模版/校验公式预设.md 解析所有校验公式，生成 note_check_preset_formulas.json

核心逻辑：
1. 解析国企版 md → 完整的 758 条公式
2. 解析上市版 md → 仅差异部分的 ~186 条公式
3. 上市版继承：
   - md 中明确标注"与国企版完全一致"的科目 → 直接复制国企版公式
   - md 中有 🔸 差异标记的科目 → 用上市版公式替换/补充国企版
   - 上市版特有科目（FS/FK/FO 等）→ 直接使用

解析 markdown 表格格式：
| 编号 | 公式类型 | 校验公式 |
|------|----------|----------|
| F1-1 | 余额 | `报表.货币资金期末 = ①货币资金分类表.合计行.期末余额` |
"""
import re
import json

# 合法的公式类型
VALID_TYPES = {
    "余额", "宽表", "纵向", "交叉", "跨科目", "其中项",
    "二级明细", "完整性", "LLM审核", "账龄衔接", "—",
}

# 上市版 md 中明确标注"与国企版完全一致"的科目编号前缀
# 从 md 第 100-110 行 + 第 750/756/762 行提取
LISTED_SAME_AS_SOE_PREFIXES = [
    # 资产负债表科目
    "F1", "F2", "F3",
    "F11", "F12", "F13",
    "F16", "F18", "F19",
    "F24", "F30",
    "F32", "F34", "F35",
    "F39", "F40",
    "F41", "F42", "F44",
    "F46", "F52",
    "F54", "F55", "F56",
    "F57", "F58",
    # 利润表科目 F59~F75
    *[f"F{i}" for i in range(59, 76)],
    # 现金流量表科目 F76~F82
    *[f"F{i}" for i in range(76, 83)],
    # 补充资料 F83~F84
    "F83", "F84",
]


def parse_formulas_from_md(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    formulas = []
    current_account = ""
    current_account_num = ""
    current_table = ""

    for line in content.split("\n"):
        line = line.strip()

        # ── 匹配科目标题 ──
        # ### 1. 货币资金
        # ### 🔸 33. 交易性金融负债（上市版差异：宽表结构）
        m = re.match(r'^###\s+(?:🔸\s*)?(\d+)[.、．]\s*(.+)', line)
        if m:
            current_account_num = m.group(1)
            raw_name = m.group(2).strip()
            raw_name = re.sub(r'[（(].*?[）)]$', '', raw_name).strip()
            current_account = raw_name
            current_table = ""
            continue

        # ### 🔸 上市版特有：设定受益计划净资产
        m = re.match(r'^###\s+🔸\s*上市版特有[：:]\s*(.+)', line)
        if m:
            raw_name = m.group(1).strip()
            raw_name = re.sub(r'[（(].*?[）)]$', '', raw_name).strip()
            current_account = raw_name
            current_account_num = ""
            current_table = ""
            continue

        # ── 匹配表格标题 ──
        m = re.match(r'^\*\*([①②③④⑤⑥⑦⑧⑨⑩]+)\s*(.+?)\*\*', line)
        if m:
            current_table = m.group(1) + " " + m.group(2).strip()
            continue

        # ── 匹配公式行 ──
        m = re.match(
            r'^\|\s*([A-Z][A-Za-z]*\d*-[\d]+\w*)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|',
            line,
        )
        if m:
            formula_id = m.group(1)
            col2 = m.group(2).strip()
            col3 = m.group(3).strip()

            col2_clean = col2.replace("：", "").strip()
            if col2_clean in VALID_TYPES:
                formula_type = col2_clean
                formula_expr = col3.replace('`', '').strip()
            else:
                type_match = None
                for vt in VALID_TYPES:
                    if col2_clean.startswith(vt):
                        type_match = vt
                        break
                if type_match:
                    formula_type = type_match
                    rest = col2_clean[len(type_match):].lstrip("：:").strip()
                    formula_expr = (rest + " " + col3).replace('`', '').strip()
                else:
                    continue

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
    elif formula_type in ("完整性", "LLM审核", "账龄衔接"):
        return "reasonability"
    elif formula_type == "—":
        return "skip"
    return "logic_check"


def to_output(f: dict) -> dict:
    """转换为输出格式"""
    section_label = f"五、{f['account_num']}" if f["account_num"] else ""
    return {
        "id": f["id"],
        "note_section": section_label,
        "section_title": f["account_name"],
        "table_name": f["table_name"],
        "check_type": f["type"],
        "category": categorize(f["type"]),
        "description": f"{f['account_name']}：{f['formula'][:80]}",
        "formula": f["formula"],
        "source": f"check_presets_md.{f['id']}",
    }


def get_formula_prefix(formula_id: str) -> str:
    """提取公式编号的科目前缀，如 F1-1 → F1, F33-4 → F33, FS-1 → FS"""
    m = re.match(r'^([A-Z][A-Za-z]*\d*)-', formula_id)
    return m.group(1) if m else ""


def build_listed_formulas(soe_formulas: list[dict], listed_raw: list[dict]) -> list[dict]:
    """构建上市版完整公式集：继承国企版 + 叠加差异

    策略：
    1. 国企版所有公式默认继承到上市版
    2. 如果上市版 md 中有同编号公式 → 用上市版的替换
    3. 如果上市版标记为"—"（不适用）→ 排除该条
    4. 上市版特有科目（FS/FK/FO/M/X/D/E 等）→ 直接追加
    """
    result = []

    # 索引：上市版差异/特有公式按 id 索引
    listed_by_id = {f["id"]: f for f in listed_raw}
    # 记录上市版中标记为"不适用"的公式 id
    skip_ids = {f["id"] for f in listed_raw if f["type"] == "—"}

    # 1. 遍历国企版公式，逐条决定继承还是替换
    for f in soe_formulas:
        fid = f["id"]
        if fid in skip_ids:
            # 上市版标记为不适用 → 排除
            continue
        if fid in listed_by_id:
            # 上市版有同编号公式 → 用上市版的
            listed_f = listed_by_id.pop(fid)
            if listed_f["type"] != "—":
                result.append(listed_f)
        else:
            # 上市版未覆盖 → 继承国企版
            result.append(f)

    # 2. 追加上市版剩余的公式（特有科目 + 差异科目中新增的编号）
    for fid, f in listed_by_id.items():
        if f["type"] != "—":
            result.append(f)

    return result


def main():
    # 解析国企版
    soe_raw = parse_formulas_from_md("附注模版/国企版校验公式预设.md")
    soe_active = [f for f in soe_raw if categorize(f["type"]) != "skip"]
    print(f"国企版: 解析到 {len(soe_raw)} 条，有效 {len(soe_active)} 条")

    # 解析上市版（仅差异部分）
    listed_raw = parse_formulas_from_md("附注模版/上市版校验公式预设.md")
    listed_diff_active = [f for f in listed_raw if categorize(f["type"]) != "skip"]
    listed_skip = [f for f in listed_raw if categorize(f["type"]) == "skip"]
    print(f"上市版差异: 解析到 {len(listed_raw)} 条（有效 {len(listed_diff_active)} 条，不适用 {len(listed_skip)} 条）")

    # 构建上市版完整公式集
    listed_full = build_listed_formulas(soe_active, listed_raw)
    print(f"上市版完整: {len(listed_full)} 条（继承国企版 + 差异 + 特有）")

    # 统计
    print("\n--- 国企版按科目统计 (top 15) ---")
    _print_account_stats(soe_active)

    print("\n--- 上市版完整按科目统计 (top 15) ---")
    _print_account_stats(listed_full)

    # 转换为输出格式
    soe_output = [to_output(f) for f in soe_active]
    listed_output = [to_output(f) for f in listed_full]

    result = {"soe": soe_output, "listed": listed_output}

    # 保存
    out_path = "backend/data/note_check_preset_formulas.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n已保存到 {out_path}")
    print(f"SOE: {len(soe_output)} 条, Listed: {len(listed_output)} 条")


def _print_account_stats(formulas, top=15):
    accounts = {}
    for f in formulas:
        key = f["account_name"] or "(未识别)"
        accounts[key] = accounts.get(key, 0) + 1
    for acc, count in sorted(accounts.items(), key=lambda x: -x[1])[:top]:
        print(f"  {acc}: {count}条")


if __name__ == "__main__":
    main()
