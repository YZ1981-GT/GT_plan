"""从 B1-5 KAA检查程序表 源 xlsx 提取结构化预置，生成 b1_5_kaa_presets.json。

结构：
{
  "sections": [
    {"key":"standard","title":"一、确定是否达到KAA标准","items":[
        {"seq":"1","text":"...","kind":"judge","sub_items":[...]}, ...]},
    {"key":"approval","title":"二、完成KAA审批或报备流程","items":[...]}
  ]
}
kind: judge(是/否/N/A) | group(有子项的父项，父不判定) | note(说明行)
"""
from __future__ import annotations

import json
import os
import re

BASE = r"../基础数据/致同通用审计程序及底稿模板（2025年修订）/1.致同审计程序及底稿模板（2025年）/1.初步业务活动（B1-B5）/B1 业务承接和保持"
SRC = os.path.join(BASE, "B1-5 KAA检查程序表.xlsx")
OUT = "app/data/b1_5_kaa_presets.json"

# 父项（含子项，父本身不判定，用于分组）
GROUP_PARENTS = {"7", "12"}  # 一节内 item7/item12 是分组父
SEC_RE = re.compile(r"^[一二三四五六七八九十]、?$")
SUB_RE = re.compile(r"^（\d+）$")


def main() -> None:
    import openpyxl

    wb = openpyxl.load_workbook(SRC, data_only=True)
    ws = wb.worksheets[0]

    sections: list[dict] = []
    cur_section: dict | None = None
    cur_group: dict | None = None
    seen_program_header = False

    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True):
        cells = [("" if c is None else str(c).strip().replace("\n", "")) for c in row]
        seq = cells[0] if len(cells) > 0 else ""
        text = cells[1] if len(cells) > 1 else ""
        if not seq and not text:
            continue
        if seq == "序号":
            seen_program_header = True
            continue
        if not seen_program_header:
            continue  # 跳过标题/表头行

        if SEC_RE.match(seq):
            # 章节
            key = "standard" if "KAA标准" in text else ("approval" if "审批" in text or "报备" in text else f"sec{len(sections)}")
            sec_no = seq.rstrip("、")
            cur_section = {"key": key, "title": f"{sec_no}、{text}", "items": []}
            sections.append(cur_section)
            cur_group = None
            continue

        if cur_section is None:
            continue

        # 跳过无序号的说明/提示行（如末尾"提示：GTIL..."，可能落在 col0 或 col1）
        if not seq or seq.startswith("提示") or text.startswith("提示") or len(seq) > 4:
            continue

        if SUB_RE.match(seq):
            # 子项
            sub = {"seq": seq, "text": text, "kind": "judge"}
            if cur_group is not None:
                cur_group.setdefault("sub_items", []).append(sub)
            else:
                cur_section["items"].append(sub)
            continue

        # 主项
        is_group = seq in GROUP_PARENTS and cur_section["key"] == "standard"
        # approval 节的主项都可能有子项，用后续（N）判定；先按 group 容纳
        approval_group = cur_section["key"] == "approval"
        item = {"seq": seq, "text": text, "kind": "group" if (is_group or approval_group) else "judge"}
        if is_group or approval_group:
            item["sub_items"] = []
            cur_group = item
        else:
            cur_group = None
        cur_section["items"].append(item)

    result = {"source_sheet": ws.title.strip(), "sections": sections}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    n_items = sum(len(s["items"]) for s in sections)
    n_sub = sum(len(it.get("sub_items", [])) for s in sections for it in s["items"])
    print(f"[OK] {OUT}: {len(sections)} sections, {n_items} items, {n_sub} sub-items")


if __name__ == "__main__":
    main()
