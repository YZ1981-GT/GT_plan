"""整理 D0A~D7A 程序表提取结果，写入 procedure_table_templates.json

读取 _d_procedure_tables_extracted.json，清洗后合并到主配置文件。
对 D7A 等过度提取的情况，只保留有 ref_index 的主步骤并重排 seq。
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"
EXTRACTED = DATA_DIR / "_d_procedure_tables_extracted.json"
TEMPLATES = DATA_DIR / "procedure_table_templates.json"


def curate_items(code: str, items: list[dict]) -> list[dict]:
    """整理步骤列表：对过度提取的情况保留主步骤。"""
    # For tables with reasonable count (<= 25), keep as-is but renumber
    if len(items) <= 25:
        result = []
        for i, item in enumerate(items, 1):
            result.append({
                "seq": i,
                "content": item["content"],
                "ref_index": item["ref_index"],
                "auto_data_source": item.get("auto_data_source"),
                "applicable_default": "yes",
            })
        return result

    # For over-extracted tables (D7A), keep only items with ref_index + key numbered steps
    with_ref = [i for i in items if i["ref_index"] is not None]
    if len(with_ref) >= 5:
        result = []
        for i, item in enumerate(with_ref, 1):
            result.append({
                "seq": i,
                "content": item["content"],
                "ref_index": item["ref_index"],
                "auto_data_source": None,
                "applicable_default": "yes",
            })
        return result

    # Fallback: take first 15
    return items[:15]


def add_auto_data_sources(code: str, items: list[dict]) -> list[dict]:
    """为程序表步骤添加 auto_data_source 绑定。

    规则：
    - 第1步通常是编制审定表 → 无 auto
    - 含"风险"关键词 → risk_for_cycle
    - 含"控制测试"关键词 → control_test_result_for_cycle
    - 含"函证"关键词 → confirmation_summary_for_cycle（仅 D0A/D2A）
    """
    for item in items:
        content = item["content"]
        # Skip if already set
        if item.get("auto_data_source"):
            continue
        # Assign based on content keywords
        if "风险评估" in content or "错报风险" in content:
            item["auto_data_source"] = "risk_for_cycle"
        elif "控制测试" in content:
            item["auto_data_source"] = "control_test_result_for_cycle"
        elif "函证" in content and code in ("D0A", "D2A"):
            item["auto_data_source"] = "confirmation_summary_for_cycle"
    return items


def main():
    with open(EXTRACTED, "r", encoding="utf-8") as f:
        extracted = json.load(f)

    with open(TEMPLATES, "r", encoding="utf-8") as f:
        templates = json.load(f)

    tables = templates["tables"]

    for code, data in extracted.items():
        if "error" in data:
            print(f"  ⚠️  跳过 {code}: {data['error']}")
            continue

        items = curate_items(code, data["items"])
        items = add_auto_data_sources(code, items)

        tables[code] = {
            "name": data["name"],
            "items": items,
        }
        print(f"  ✓ {code}: {data['name']} → {len(items)} 步骤")

    with open(TEMPLATES, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)

    print(f"\n已更新: {TEMPLATES}")
    print(f"程序表总数: {len(tables)}")


if __name__ == "__main__":
    main()
