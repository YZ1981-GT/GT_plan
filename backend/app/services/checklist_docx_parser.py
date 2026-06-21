"""核对表 docx 解析器 — 将 A1-15/A1-16 模板解析为结构化 JSON.

设计目标：
- A1-15: 3 Word 表格 → 跳过表1(封面)，解析表2(目录→toc)，解析表3(核对表主体)
- A1-16: 1 Word 表格 → 跳过封面/说明行，14物理列→3逻辑列(相邻去重)
- 条目分类：actionable(主条目) / guidance(子项) / header(小节标题)
- 全局 mtime 缓存 → 模板文件不变则不重复解析
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docx import Document
from docx.table import Table, _Cell

logger = logging.getLogger(__name__)

# ─── 常量 ─────────────────────────────────────────────────────────────────────

# 准则索引号前缀正则（判定 actionable 的必要条件之一）
_STANDARD_REF_RE = re.compile(
    r"^(CAS|IG|ISA|Art|法规|编报规则|上市规则|SAS|IFRS|IAS|SSA|CSRC)",
    re.IGNORECASE,
)

# A1-16 准则索引正则（更宽泛，包含 Art/RPID/公告/编报规则/重要提醒 等）
_A16_REF_RE = re.compile(
    r"^(Art|RPID|公告|《|财会|解释性公告|重要提醒|\d+[\.\d]*\s*Art)",
    re.IGNORECASE,
)

# guidance 子项开头字母 a~j（含中英文句点/括号等分隔符）
_GUIDANCE_PREFIX_RE = re.compile(r"^[a-j][.、)）:\s]", re.IGNORECASE)

# 扩展 guidance：(1)/(2) 等编号子项
_GUIDANCE_NUMBERED_RE = re.compile(r"^\(\d+\)\s*")

# 章节表头检测（A1-15 中 "准则索引号" 出现在表头行）
_SECTION_HEADER_RE = re.compile(r"准则索引号|Standard\s*Ref", re.IGNORECASE)

# A1-16 章节表头检测
_A16_SECTION_RE = re.compile(r"^法规[：:]")

# 模板文件目录
_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "wp_templates" / "A"

# ─── 全局 mtime 缓存 ──────────────────────────────────────────────────────────
_CHECKLIST_TEMPLATE_CACHE: dict[str, tuple[float, dict]] = {}  # wp_code → (mtime, parsed)


# ─── 公开 API ─────────────────────────────────────────────────────────────────


def get_template_path(wp_code: str) -> Path | None:
    """根据 wp_code 前缀查找模板文件路径."""
    for f in _TEMPLATE_DIR.iterdir():
        if f.suffix.lower() == ".docx" and f.name.startswith(wp_code):
            return f
    return None


async def get_checklist_template(wp_code: str) -> dict:
    """获取解析后的核对表模板（带 mtime 缓存）."""
    file_path = get_template_path(wp_code)
    if file_path is None:
        raise FileNotFoundError(f"未找到核对表模板文件: wp_code={wp_code}")

    mtime = os.path.getmtime(file_path)
    if wp_code in _CHECKLIST_TEMPLATE_CACHE:
        cached_mtime, cached_data = _CHECKLIST_TEMPLATE_CACHE[wp_code]
        if cached_mtime == mtime:
            return cached_data

    parsed = parse_checklist_docx(file_path, wp_code)
    _CHECKLIST_TEMPLATE_CACHE[wp_code] = (mtime, parsed)
    return parsed


def parse_checklist_docx(file_path: Path | str, wp_code: str) -> dict:
    """解析核对表 docx 模板，返回统一结构化 JSON."""
    file_path = Path(file_path)
    doc = Document(str(file_path))

    if wp_code == "A1-15":
        return _parse_a1_15(doc, wp_code)
    elif wp_code == "A1-16":
        return _parse_a1_16(doc, wp_code)
    elif wp_code == "A1-12":
        return _parse_a1_12(doc, wp_code)
    else:
        raise ValueError(f"不支持的核对表 wp_code: {wp_code}")


# ─── A1-12 解析 ──────────────────────────────────────────────────────────────


def _parse_a1_12(doc: "Document", wp_code: str) -> dict:
    """A1-12 重大事项决定程序履行情况核查表: 单表格 17 行 × 3 列.

    结构：
      Row 0: 表头 [条目描述, 是否适用, 如适用索引号]
      Row 1-14: 第一分组条目（"一、需提交专业技术委员会…"）
      Row 15: 第二分组标题（"二、…"）
      Row 16: 第二分组空填写行

    分组规则: 以"一、"/"二、"/"三、"等开头的行为 section 标题，其余为条目。
    """
    tables = doc.tables
    if not tables:
        raise ValueError("A1-12 预期至少 1 个表格，实际 0 个")

    tbl = tables[0]
    sections: list[dict] = []
    current_section: dict | None = None
    section_idx = 0
    item_idx = 0

    _SECTION_RE = re.compile(r"^[一二三四五六七八九十]+、")

    for ri in range(len(tbl.rows)):
        cell0 = tbl.cell(ri, 0).text.strip().replace("\xa0", " ")
        # 跳过纯空行
        if not cell0:
            continue
        # Row 0 的后续列是"是否适用"/"索引号"表头标记——
        # 但 cell0 本身可能含 section 标题（如"一、…"），仍需判断
        if ri == 0:
            # 检测 Row 0 的 cell0 是否本身就是 section 标题
            if _SECTION_RE.match(cell0):
                section_idx += 1
                current_section = {
                    "id": f"S{section_idx:02d}",
                    "title": cell0,
                    "items": [],
                }
                sections.append(current_section)
            continue

        # 检测是否为分组标题
        if _SECTION_RE.match(cell0):
            section_idx += 1
            current_section = {
                "id": f"S{section_idx:02d}",
                "title": cell0,
                "items": [],
            }
            sections.append(current_section)
        else:
            # 核查条目行
            if current_section is None:
                # 首行条目出现在第一个标题之前（Row 0 是标题，Row 1 已有 section）
                # 但 A1-12 实际上 Row 0 是表头，Row 1-14 属于第一个 section
                # 第一个 section 标题在 Row 0 col0 末尾已含"一、"…实际是嵌在表头里的
                # 兜底：创建默认 section
                section_idx += 1
                current_section = {
                    "id": f"S{section_idx:02d}",
                    "title": "核查事项",
                    "items": [],
                }
                sections.append(current_section)

            item_idx += 1
            current_section["items"].append({
                "id": f"Q{item_idx:03d}",
                "type": "actionable",
                "standard_ref": "",
                "content": cell0,
                "text": cell0,
                "children": [],
            })

    # 如果第一行实际包含 section 标题（如"一、…"在 Row 0 第一列）
    # 上面逻辑已处理。但 A1-12 的 Row 0 是三列表头，真正 section 标题
    # 嵌在条目描述列里（Row 1 的 cell0 以数字开头而非"一、"）。
    # 分析实际数据：Row 0 的 cell0 是"一、 需提交…的情形"→匹配 _SECTION_RE。
    # Row 1-14 以"1、"开头→不匹配 _SECTION_RE→归入条目。✓

    # 统计
    total_actionable = sum(
        1 for sec in sections for item in sec["items"] if item["type"] == "actionable"
    )

    title = _extract_title_from_filename(wp_code)

    return {
        "wp_code": wp_code,
        "title": title or "重大事项决定程序的履行情况核查表",
        "sections": sections,
        "toc": [{"id": s["id"], "title": s["title"], "applicable": None} for s in sections],
        "stats": {
            "total_actionable": total_actionable,
            "total_guidance": 0,
            "total_sections": len(sections),
        },
        "has_standard_ref": False,
        "allow_custom_items": True,
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── A1-15 解析 ──────────────────────────────────────────────────────────────


def _parse_a1_15(doc: Document, wp_code: str) -> dict:
    """A1-15: 3 个表格 → 跳过表1(封面25行), 解析表2(目录), 解析表3(核对表主体)."""
    tables = doc.tables
    if len(tables) < 3:
        raise ValueError(f"A1-15 预期至少 3 个表格，实际 {len(tables)} 个")

    # 表2 → TOC
    toc = _parse_a1_15_toc(tables[1])

    # 表3 → sections
    sections = _parse_a1_15_body(tables[2])

    # 统计
    total_actionable = 0
    total_guidance = 0
    for sec in sections:
        for item in sec["items"]:
            if item["type"] == "actionable":
                total_actionable += 1
                total_guidance += len(item.get("children", []))

    # 标题从文件名提取
    title = _extract_title_from_filename(wp_code)

    return {
        "wp_code": wp_code,
        "title": title or "企业会计准则有关财务报表列报及披露核对表",
        "sections": sections,
        "toc": toc,
        "stats": {
            "total_actionable": total_actionable,
            "total_guidance": total_guidance,
            "total_sections": len(sections),
        },
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }


def _parse_a1_15_toc(table: Table) -> list[dict]:
    """解析 A1-15 表2（目录表）→ toc 列表.

    表2 结构：3 列，col0 为空或序号前缀，col1=章节标题，col2=适用Y/N
    """
    toc: list[dict] = []
    section_idx = 0

    for row in table.rows:
        cells = row.cells
        if len(cells) < 2:
            continue

        # col1 是标题列（实证确认 col0 通常为空）
        text = _cell_text(cells[1]).strip()
        if not text:
            # fallback to col0
            text = _cell_text(cells[0]).strip()
        if not text:
            continue

        # 跳过表头行
        if "目录" in text or "核对表" in text:
            continue

        # 识别章节标题行：以数字/中文数字开头
        if re.match(r"^\d+[\.\d]*\s", text) or re.match(r"^[一二三四五六七八九十]", text):
            section_idx += 1
            # 适用标记在最后一列
            applicable_text = _cell_text(cells[-1]).strip() if len(cells) > 2 else ""
            applicable = None
            if applicable_text.upper() == "Y":
                applicable = True
            elif applicable_text.upper() == "N":
                applicable = False
            toc.append({
                "id": f"S{section_idx:02d}",
                "title": text,
                "applicable": applicable,
            })

    return toc


def _parse_a1_15_body(table: Table) -> list[dict]:
    """解析 A1-15 表3（核对表主体 934行×3列）→ sections 列表."""
    sections: list[dict] = []
    current_section: dict | None = None
    section_idx = 0
    item_idx = 0
    last_actionable: dict | None = None

    for row in table.rows:
        cells = row.cells
        if len(cells) < 2:
            continue

        # 检测是否为合并单元格行
        is_merged = _is_row_merged(row, expected_cols=3)

        col0_text = _cell_text(cells[0]).strip()
        col1_text = _cell_text(cells[1]).strip() if len(cells) > 1 else ""

        # 1) 检测章节表头行（"准则索引号" 重复出现 → 新章节开始）
        if _SECTION_HEADER_RE.search(col0_text) or _SECTION_HEADER_RE.search(col1_text):
            # 章节标题通常在 col1 中
            section_title = col1_text if col1_text else col0_text
            # 清理标题中多余的"适用"等文字
            section_title = re.sub(
                r"\s*(适用|不适用|Y|N|/|（|）|\(|\)).*$", "", section_title
            ).strip()
            if not section_title or section_title == col0_text:
                section_title = (
                    col1_text.split("\n")[0].strip()
                    if col1_text
                    else f"章节{section_idx + 1}"
                )

            section_idx += 1
            item_idx = 0
            last_actionable = None
            current_section = {
                "id": f"S{section_idx:02d}",
                "title": section_title,
                "items": [],
            }
            sections.append(current_section)
            continue

        # 如果还没遇到第一个章节，跳过
        if current_section is None:
            continue

        # 2) 合并行处理：guidance 或 header
        if is_merged:
            merged_text = _get_merged_row_text(cells).strip()
            if not merged_text:
                continue

            if _GUIDANCE_PREFIX_RE.match(merged_text):
                # guidance 子项 → 挂到最近 actionable parent
                if last_actionable is not None:
                    child_label = merged_text[0].lower()
                    child_id = f"{last_actionable['id']}-{child_label}"
                    child_ref = _extract_standard_ref_from_guidance(merged_text)
                    last_actionable["children"].append({
                        "id": child_id,
                        "content": merged_text,
                        "standard_ref": child_ref,
                    })
                continue
            else:
                # header（小节标题）
                item_idx += 1
                current_section["items"].append({
                    "id": f"{current_section['id']}-{item_idx:03d}",
                    "type": "header",
                    "standard_ref": "",
                    "content": merged_text,
                    "children": [],
                })
                continue

        # 3) 非合并行 + col0 有准则索引 → actionable
        if col0_text and _STANDARD_REF_RE.match(col0_text):
            item_idx += 1
            item_id = f"{current_section['id']}-{item_idx:03d}"
            actionable_item = {
                "id": item_id,
                "type": "actionable",
                "standard_ref": col0_text,
                "content": col1_text,
                "children": [],
            }
            current_section["items"].append(actionable_item)
            last_actionable = actionable_item
            continue

        # 4) 非合并行，col1 以 a~j 开头 → guidance
        if col1_text and _GUIDANCE_PREFIX_RE.match(col1_text):
            if last_actionable is not None:
                child_label = col1_text[0].lower()
                child_id = f"{last_actionable['id']}-{child_label}"
                child_ref = _extract_standard_ref_from_guidance(col1_text)
                last_actionable["children"].append({
                    "id": child_id,
                    "content": col1_text,
                    "standard_ref": child_ref,
                })
            continue

        # 5) 非合并行，col0 非空但不匹配标准索引正则 → 仍视为 actionable
        #    （有些准则索引格式不在正则中）
        if col0_text and col1_text:
            item_idx += 1
            item_id = f"{current_section['id']}-{item_idx:03d}"
            actionable_item = {
                "id": item_id,
                "type": "actionable",
                "standard_ref": col0_text,
                "content": col1_text,
                "children": [],
            }
            current_section["items"].append(actionable_item)
            last_actionable = actionable_item
            continue

        # 6) 无索引的独立内容行 → header
        if col1_text and not col0_text:
            item_idx += 1
            current_section["items"].append({
                "id": f"{current_section['id']}-{item_idx:03d}",
                "type": "header",
                "standard_ref": "",
                "content": col1_text,
                "children": [],
            })

    return sections


# ─── A1-16 解析 ──────────────────────────────────────────────────────────────


def _parse_a1_16(doc: Document, wp_code: str) -> dict:
    """A1-16: 1 个表格(653行×14物理列) → 跳过封面/说明，去重得3逻辑列."""
    tables = doc.tables
    if len(tables) < 1:
        raise ValueError("A1-16 预期至少 1 个表格")

    table = tables[0]
    sections = _parse_a1_16_body(table)

    total_actionable = 0
    total_guidance = 0
    for sec in sections:
        for item in sec["items"]:
            if item["type"] == "actionable":
                total_actionable += 1
                total_guidance += len(item.get("children", []))

    return {
        "wp_code": wp_code,
        "title": "上市公司财务报表额外披露要求核对表（A股）",
        "sections": sections,
        "toc": [{"id": s["id"], "title": s["title"], "applicable": None} for s in sections],
        "stats": {
            "total_actionable": total_actionable,
            "total_guidance": total_guidance,
            "total_sections": len(sections),
        },
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }


def _parse_a1_16_body(table: Table) -> list[dict]:
    """解析 A1-16 表格主体 → sections.

    数据起始标志：第一个 col0 匹配 "法规：" 的行。
    章节分隔：col0 匹配 "法规：" 开头的行。
    """
    sections: list[dict] = []
    current_section: dict | None = None
    section_idx = 0
    item_idx = 0
    last_actionable: dict | None = None

    rows = list(table.rows)
    # 找到数据起始行（第一个 "法规：" 开头的行）
    data_start = 0
    for i, row in enumerate(rows):
        logical = _dedup_adjacent_cells(row.cells)
        if logical and _A16_SECTION_RE.match(logical[0].strip()):
            data_start = i
            break

    for row in rows[data_start:]:
        cells = row.cells
        logical = _dedup_adjacent_cells(cells)

        if not logical:
            continue

        # 全合并行（1 个 logical col）
        if len(logical) == 1:
            text = logical[0].strip()
            if not text:
                continue
            # 单列合并行 → header（如果在章节内）
            if current_section is not None:
                # 检查是否为 guidance
                if _GUIDANCE_PREFIX_RE.match(text) or _GUIDANCE_NUMBERED_RE.match(text):
                    if last_actionable is not None:
                        child_label = text[0].lower() if text[0].isalpha() else f"n{len(last_actionable['children']) + 1}"
                        child_id = f"{last_actionable['id']}-{child_label}"
                        last_actionable["children"].append({
                            "id": child_id,
                            "content": text,
                            "standard_ref": "",
                        })
                    continue
                item_idx += 1
                current_section["items"].append({
                    "id": f"{current_section['id']}-{item_idx:03d}",
                    "type": "header",
                    "standard_ref": "",
                    "content": text,
                    "children": [],
                })
            continue

        col0 = logical[0].strip()
        col1 = logical[1].strip() if len(logical) > 1 else ""

        # 全行为空 → 跳过
        if not col0 and not col1:
            continue

        # 章节表头检测：col0 匹配 "法规：" → 新章节
        if _A16_SECTION_RE.match(col0):
            section_title = col1 if col1 else col0
            # 清理 "适用或不适用" 后缀
            section_title = re.sub(r"\s*(适用|不适用).*$", "", section_title).strip()
            section_idx += 1
            item_idx = 0
            last_actionable = None
            current_section = {
                "id": f"S{section_idx:02d}",
                "title": section_title,
                "items": [],
            }
            sections.append(current_section)
            continue

        # 如果还没遇到章节 → 跳过
        if current_section is None:
            continue

        # guidance 子项：col0 为空 + col1 以 a~j 或 (1) 开头
        if not col0 and col1 and (
            _GUIDANCE_PREFIX_RE.match(col1) or _GUIDANCE_NUMBERED_RE.match(col1)
        ):
            if last_actionable is not None:
                if col1[0].isalpha():
                    child_label = col1[0].lower()
                else:
                    child_label = f"n{len(last_actionable['children']) + 1}"
                child_id = f"{last_actionable['id']}-{child_label}"
                last_actionable["children"].append({
                    "id": child_id,
                    "content": col1,
                    "standard_ref": "",
                })
            continue

        # actionable：col0 有准则索引（Art./RPID/公告 等）
        if col0 and (_A16_REF_RE.match(col0) or _STANDARD_REF_RE.match(col0)):
            item_idx += 1
            item_id = f"{current_section['id']}-{item_idx:03d}"
            actionable_item = {
                "id": item_id,
                "type": "actionable",
                "standard_ref": col0,
                "content": col1,
                "children": [],
            }
            current_section["items"].append(actionable_item)
            last_actionable = actionable_item
            continue

        # 无索引行但有内容 → header（小节标题或独立文本）
        if col1:
            # 看看是否是编号子项（如 "16 长期股权投资"）→ 视为 header
            item_idx += 1
            current_section["items"].append({
                "id": f"{current_section['id']}-{item_idx:03d}",
                "type": "header",
                "standard_ref": col0,
                "content": col1,
                "children": [],
            })

    return sections


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────


def _cell_text(cell: _Cell) -> str:
    """获取单元格纯文本内容."""
    return (cell.text or "").strip()


def _is_row_merged(row, expected_cols: int = 3) -> bool:
    """检测行是否包含合并单元格（A1-15 3列格式）.

    python-docx 中合并单元格的特征：多个相邻 cell 对象引用同一个 tc 元素。
    """
    cells = row.cells
    if len(cells) <= 1:
        return True

    # 检查唯一 tc 数量
    unique_tcs = set()
    for cell in cells:
        unique_tcs.add(cell._tc)

    # 如果唯一 tc 数量少于 expected_cols，说明有合并
    return len(unique_tcs) < expected_cols


def _get_merged_row_text(cells) -> str:
    """获取合并行的完整文本（去重相邻相同 tc 内容）."""
    texts = []
    prev_tc = None
    for cell in cells:
        tc = cell._tc
        if tc is prev_tc:
            continue
        t = _cell_text(cell)
        if t:
            texts.append(t)
        prev_tc = tc
    return " ".join(texts).strip()


def _dedup_adjacent_cells(cells) -> list[str]:
    """将物理列通过相邻 tc 去重得到逻辑列内容列表.

    python-docx 对合并单元格返回重复的 cell 引用，相邻 cell 若引用同一 tc，
    视为同一逻辑列。
    """
    logical: list[str] = []
    prev_tc = None
    for cell in cells:
        tc = cell._tc
        if tc is prev_tc:
            continue  # 同一 tc → 跳过
        logical.append(_cell_text(cell))
        prev_tc = tc
    return logical


def _extract_standard_ref_from_guidance(text: str) -> str:
    """从 guidance 子项文本中提取可能的准则引用."""
    m = re.search(r"(CAS|IG|ISA|Art|法规)\s*[\d.]+(?:\([^)]*\))?", text)
    if m:
        return m.group(0)
    return ""


def _extract_title_from_filename(wp_code: str) -> str:
    """从模板文件名提取标题."""
    for f in _TEMPLATE_DIR.iterdir():
        if f.suffix.lower() == ".docx" and f.name.startswith(wp_code):
            name_without_ext = f.stem
            # 去掉 wp_code 前缀和日期后缀
            title = re.sub(r"^A1-1[56]\s*", "", name_without_ext)
            title = re.sub(r"\d{8}$", "", title).strip()
            return title
    return ""


def invalidate_cache(wp_code: str | None = None) -> None:
    """手动清除缓存（用于测试或强制刷新）."""
    if wp_code:
        _CHECKLIST_TEMPLATE_CACHE.pop(wp_code, None)
    else:
        _CHECKLIST_TEMPLATE_CACHE.clear()
