"""一次性脚本：从 B1-1/B1-2 源模板提取固定问卷事项，生成预置行 JSON。

输出：backend/app/data/b1_risk_assessment_presets.json
结构：{ "B1-1": {"sections":[{"title":..,"items":[{"item":..,"kind":"text|note|choice"}]}]}, "B1-2": {...} }

- 章节标题：A 列以「一、二、三、四、五、六、七」开头，或纯标题行（B/C 无表头语义）
- 事项行：A 列有内容且非章节标题
- 判断 kind：题干含「是否」→ choice(是/否/N/A)；其余 → text
"""
from __future__ import annotations

import json
import os
import re

BASE = r"基础数据/致同通用审计程序及底稿模板（2025年修订）/1.致同审计程序及底稿模板（2025年）/1.初步业务活动（B1-B5）/B1 业务承接和保持"
FILES = {
    "B1-1": "B1-1 风险评估表（适用于承接）.xlsx",
    "B1-2": "B1-2 风险评估表（适用于保持）.xlsx",
}
OUT = "backend/app/data/b1_risk_assessment_presets.json"

SECTION_RE = re.compile(r"^[一二三四五六七八九十]、")
HEADER_LABELS = {"事项", "被审计单位：", "所属办公室：", "拟承接合伙人:", "项目合伙人:", "项目负责经理："}


def classify_kind(text: str) -> str:
    if "是否" in text or text.endswith("？") or text.endswith("?"):
        return "choice"
    return "text"


def main() -> None:
    import openpyxl

    result: dict = {}
    for code, fn in FILES.items():
        path = os.path.join(BASE, fn)
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.worksheets[0]
        sheet_title = ws.title
        sections: list[dict] = []
        current = {"title": "基本信息", "items": []}
        seen_header = False
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True):
            a = row[0] if len(row) > 0 else None
            if a is None or not str(a).strip():
                continue
            text = str(a).strip().replace("\n", "").replace("\r", "")
            # 跳过大标题（第1行表名）与表头行
            if not seen_header:
                if text == "事项":
                    seen_header = True
                continue
            if text in HEADER_LABELS:
                continue
            if SECTION_RE.match(text):
                if current["items"]:
                    sections.append(current)
                current = {"title": text, "items": []}
                continue
            current["items"].append({"item": text, "kind": classify_kind(text)})
        if current["items"]:
            sections.append(current)
        result[code] = {"source_sheet": sheet_title, "sections": sections}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    # 摘要
    for code, data in result.items():
        n_sec = len(data["sections"])
        n_item = sum(len(s["items"]) for s in data["sections"])
        print(f"[OK] {code}: {n_sec} sections, {n_item} items -> {OUT}")


if __name__ == "__main__":
    main()
