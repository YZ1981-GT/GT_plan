"""A30 电子底稿归档检查表解析（spec attachment-archive-and-a-class-evidence 需求 8，ADR-AE-11）。

模板 ``wp_templates/A/A30 电子底稿归档检查表.xlsx``：第 4 行表头（索引号 / 电子工作底稿名称 / 有或无），第 5 行起
每行一个底稿编码；名称带 ``*`` 为必备项；A 列以「项目合伙人」「填表说明」开头即到页脚。

改造前 A30 不在两份 xlsx 列映射里，``parse_checklist_xlsx`` 抛错 ⇒ 页面是空模板。不往
``checklist_xlsx_parser.py`` 里加分支：那个文件超行数门且列映射驱动，这张表是「编码清单」形态，结构不同。

输出与 ``GtChecklistTable`` 现有结构同形：``item_id = A30-{编码}``（编码去掉空白，``A 1-11`` → ``A1-11``；同一编码
第二次出现起加 ``-2`` / ``-3``），按编码首字母分节，``conclusion_mode = completion``（是 / 否 / 不适用）。
"""

from __future__ import annotations

import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import openpyxl

INDEX_CHECKLIST_CODES = frozenset({"A30"})
FIRST_DATA_ROW = 5
FOOTER_PREFIXES = ("项目合伙人", "填表说明")
SECTION_TITLES: dict[str, str] = {
    "A": "A 完成阶段", "B": "B 控制了解", "C": "C 控制测试", "D": "D 销售收入", "E": "E 货币资金",
    "F": "F 采购存货", "G": "G 投资", "H": "H 固定资产", "I": "I 无形资产", "J": "J 职工薪酬",
    "K": "K 管理", "L": "L 筹资", "M": "M 股东权益", "N": "N 税费", "S": "S 专项",
}
_CODE_RE = re.compile(r"^[A-Z]\d")
_CACHE: dict[str, tuple[float, dict]] = {}


def is_index_checklist(wp_code: str | None) -> bool:
    return (wp_code or "") in INDEX_CHECKLIST_CODES


def normalize_code(raw: object) -> str:
    return re.sub(r"\s+", "", str(raw or ""))


def template_path(wp_code: str) -> Path | None:
    from app.services.wp_export.wp_file_resolver import BACKEND_ROOT

    folder = BACKEND_ROOT / "wp_templates" / wp_code[:1]
    if not folder.is_dir():
        return None
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() == ".xlsx" and normalize_code(f.stem).startswith(wp_code) \
                and not normalize_code(f.stem)[len(wp_code):][:1].isdigit():
            return f
    return None


def parse_index_checklist(file_path: Path | str, wp_code: str = "A30") -> dict:
    wb = openpyxl.load_workbook(str(file_path), data_only=True, read_only=True)
    try:
        ws = wb.worksheets[0]
        sections: dict[str, dict] = {}
        seen: Counter[str] = Counter()
        for row in ws.iter_rows(min_row=FIRST_DATA_ROW, max_col=4, values_only=True):
            first = str(row[0] or "").strip()
            if first.startswith(FOOTER_PREFIXES):
                break
            code = normalize_code(first)
            if not _CODE_RE.match(code):
                continue
            raw_name = str(row[1] or "").strip()
            required = "*" in raw_name
            name = raw_name.replace("*", "").strip() or code
            seen[code] += 1
            item_id = f"{wp_code}-{code}" + (f"-{seen[code]}" if seen[code] > 1 else "")
            letter = code[0]
            section = sections.setdefault(letter, {
                "id": f"{wp_code}-S-{letter}", "title": SECTION_TITLES.get(letter, f"{letter} 其他"), "items": [],
            })
            section["items"].append({
                "id": item_id, "type": "actionable", "standard_ref": code,
                "content": f"{name}（必备）" if required else name,
                "preset_wp_ref": code, "required": required, "children": [],
            })
    finally:
        wb.close()
    ordered = list(sections.values())
    total = sum(len(s["items"]) for s in ordered)
    return {
        "wp_code": wp_code,
        "title": "电子底稿归档检查表",
        "conclusion_mode": "completion",
        "sections": ordered,
        "toc": [{"id": s["id"], "title": s["title"], "applicable": None} for s in ordered],
        "stats": {"total_actionable": total, "total_guidance": 0, "total_sections": len(ordered),
                  "total_required": sum(1 for s in ordered for i in s["items"] if i["required"])},
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }


async def get_index_checklist_template(wp_code: str) -> dict:
    """mtime 缓存的解析结果；模板不存在 ⇒ FileNotFoundError。"""
    path = template_path(wp_code)
    if path is None:
        raise FileNotFoundError(f"未找到底稿清单核对表模板：wp_code={wp_code}")
    mtime = os.path.getmtime(path)
    cached = _CACHE.get(wp_code)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    parsed = parse_index_checklist(path, wp_code)
    _CACHE[wp_code] = (mtime, parsed)
    return parsed


def checklist_item_codes(template: dict) -> dict[str, str]:
    """``item_id → 底稿编码``（建议端点用）。"""
    return {item["id"]: item["standard_ref"] for s in template.get("sections", []) for item in s.get("items", [])}
