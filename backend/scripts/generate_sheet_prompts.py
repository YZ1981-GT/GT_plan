"""generate_sheet_prompts.py — 从科目级提示词自动生成底稿级提示词骨架

用法:
    python scripts/generate_sheet_prompts.py --wp-code D3 --sheets 1,2,3,5,7,8
    python scripts/generate_sheet_prompts.py --wp-code K1 --sheets 1,2,3,4,5,7,8,9,10,11,12
    python scripts/generate_sheet_prompts.py --wp-code D3 --sheets 1,2,3 --from-source data/tsj_review_prompts/D/D3.md

生成的文件需人工审阅和微调，本脚本仅提供骨架。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 底稿类型映射
SHEET_TYPE_MAP = {
    "1": "审定表",
    "2": "明细表",
    "3": "坏账准备/减值准备",
    "4": "调整分录",
    "5": "分析表",
    "6": "关联方检查",
    "7": "凭证检查",
    "8": "政策检查",
    "note-listed": "附注披露（上市公司）",
    "note-soe": "附注披露（国有企业）",
}

TEMPLATE = '''# {wp_code}-{suffix} {sheet_type}复核提示词

## 适用底稿
{sheet_type}（{wp_code}-{suffix}）

## tips

- 待填写：根据科目特性补充审计要点
- 待填写：参考源文件对应章节

## checklist

### 高风险

- [ ] 待填写

### 中风险

- [ ] 待填写

### 低风险

- [ ] 待填写

## risk_areas

### 高风险

- 待填写

### 中风险

- 待填写

### 低风险

- 待填写
'''

TEMPLATE_FROM_SOURCE = '''---
version: "1.0.0"
updated: "2026-07-20"
author: "auto-generated"
applicable_standards: []
---

# {wp_code}-{suffix} {sheet_type}复核提示词

## 适用底稿
{sheet_type}（{wp_code}-{suffix}）

## tips

- 以下内容从源科目级提示词自动抽取，请人工审阅和微调

## checklist

### 高风险

{checklist_high}

### 中风险

{checklist_medium}

### 低风险

- [ ] 待填写

## risk_areas

### 高风险

{risk_high}

### 中风险

{risk_medium}

### 低风险

{risk_low}
'''


def extract_from_source(source_path: Path) -> dict[str, list[str]]:
    """从源科目级提示词文件中抽取 tips/checklist/risk_areas"""
    content = source_path.read_text(encoding="utf-8-sig")

    tips = []
    checklist_items = []
    risk_high = []
    risk_medium = []
    risk_low = []

    lines = content.split("\n")
    current_section = ""
    current_risk = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            current_section = stripped
            current_risk = ""
        elif "高风险" in stripped and stripped.startswith("#"):
            current_risk = "high"
        elif "中风险" in stripped and stripped.startswith("#"):
            current_risk = "medium"
        elif "低风险" in stripped and stripped.startswith("#"):
            current_risk = "low"
        elif stripped.startswith("- [ ]") or stripped.startswith("- [x]"):
            item = stripped[5:].strip()
            if item:
                checklist_items.append(item)
        elif stripped.startswith("- **") and current_risk:
            item = stripped.lstrip("- ").strip()
            if current_risk == "high":
                risk_high.append(item)
            elif current_risk == "medium":
                risk_medium.append(item)
            else:
                risk_low.append(item)

    return {
        "checklist": checklist_items[:20],  # Limit to first 20
        "risk_high": risk_high[:5],
        "risk_medium": risk_medium[:5],
        "risk_low": risk_low[:3],
    }


def main():
    parser = argparse.ArgumentParser(description="生成底稿级提示词骨架文件")
    parser.add_argument("--wp-code", required=True, help="科目前缀，如 D3, K1, F2")
    parser.add_argument("--sheets", required=True, help="逗号分隔的底稿后缀，如 1,2,3,5,7,8,note-listed,note-soe")
    parser.add_argument("--output-dir", default=None, help="输出目录（默认: backend/data/tsj_review_prompts/{cycle_letter}/）")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    parser.add_argument("--from-source", default=None, help="源科目级提示词文件路径，自动抽取内容填充骨架")
    args = parser.parse_args()

    wp_code = args.wp_code.upper()
    cycle_letter = wp_code[0]
    suffixes = [s.strip() for s in args.sheets.split(",")]

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(__file__).resolve().parents[1] / "data" / "tsj_review_prompts" / cycle_letter

    output_dir.mkdir(parents=True, exist_ok=True)

    # 从源文件抽取内容（如果提供）
    source_data = None
    if args.from_source:
        source_path = Path(args.from_source)
        if source_path.is_file():
            source_data = extract_from_source(source_path)
            print(f"[INFO] 从源文件抽取: {len(source_data['checklist'])} 检查项, {len(source_data['risk_high'])} 高风险项")
        else:
            print(f"[WARN] 源文件不存在: {source_path}, 使用骨架模板")

    created = 0
    skipped = 0

    for suffix in suffixes:
        filename = f"{wp_code}-{suffix}.md"
        filepath = output_dir / filename

        if filepath.exists() and not args.force:
            print(f"  [跳过] {filename}（已存在，使用 --force 覆盖）")
            skipped += 1
            continue

        sheet_type = SHEET_TYPE_MAP.get(suffix, f"底稿{suffix}")

        if source_data:
            checklist_high = "\n".join(f"- [ ] {item}" for item in source_data["checklist"][:10]) or "- [ ] 待填写"
            checklist_medium = "\n".join(f"- [ ] {item}" for item in source_data["checklist"][10:20]) or "- [ ] 待填写"
            risk_h = "\n".join(f"- {item}" for item in source_data["risk_high"]) or "- 待填写"
            risk_m = "\n".join(f"- {item}" for item in source_data["risk_medium"]) or "- 待填写"
            risk_l = "\n".join(f"- {item}" for item in source_data["risk_low"]) or "- 待填写"
            content = TEMPLATE_FROM_SOURCE.format(
                wp_code=wp_code, suffix=suffix, sheet_type=sheet_type,
                checklist_high=checklist_high, checklist_medium=checklist_medium,
                risk_high=risk_h, risk_medium=risk_m, risk_low=risk_l,
            )
        else:
            content = TEMPLATE.format(
                wp_code=wp_code,
                suffix=suffix,
                sheet_type=sheet_type,
            )

        filepath.write_text(content, encoding="utf-8")
        print(f"  [创建] {filename}")
        created += 1

    print(f"\n完成: 创建 {created} 个, 跳过 {skipped} 个")
    print(f"输出目录: {output_dir}")
    print("\n⚠️  生成的文件仅为骨架，请根据源科目级提示词内容人工补充审计要点。")


if __name__ == "__main__":
    main()
