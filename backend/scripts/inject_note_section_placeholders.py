#!/usr/bin/env python3
"""在附注模板 SECTION 块内部注入精细填充占位符。

为每个 ##SECTION:code## 块内部添加：
- {{seq:prefix}} — 章节编号占位（标题行首）
- {{section:code}} — 文字说明填入位置（首个非标题文字段前）
- {{table:code:N}} + ##STYLE_REF:table:code:N## — 每张表格的占位

规则：
- 标题行 = 块内第一个 Heading 样式段落
- 表格按在 body 子元素中出现的顺序编号 0,1,2...
- 文字区 = 标题行之后、第一张表格之前的 Normal 段落区域
- 已有占位的块跳过（幂等）
- 不修改 ##SECTION: / ##/SECTION: 标记本身

Usage:
    python backend/scripts/inject_note_section_placeholders.py            # dry-run
    python backend/scripts/inject_note_section_placeholders.py --write
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

_BACKEND = Path(__file__).resolve().parent.parent
NOTES_DIR = _BACKEND / "data" / "audit_report_templates" / "disclosure_notes"
BACKUP_DIR = NOTES_DIR / "_backup_placeholders"

VARIANTS = [
    "soe_standalone.docx",
    "soe_consolidated.docx",
    "listed_standalone.docx",
    "listed_consolidated.docx",
]


def _extract_prefix(code: str) -> str:
    """从 section_code 提取编号前缀：'八、1' → '八', '一、1' → '一'."""
    parts = code.split("、")
    return parts[0] if parts else code


def _insert_paragraph_before_element(ref_element, text: str, body):
    """在 body 级子元素前插入一个新段落。"""
    new_p = OxmlElement("w:p")
    run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = text
    run.append(t)
    new_p.append(run)
    body.insert(list(body).index(ref_element), new_p)
    return new_p


def _has_placeholder(block_elements: list, code: str) -> bool:
    """检查块内是否已有占位（幂等检测）。"""
    for el in block_elements:
        if el.tag == qn("w:p"):
            texts = "".join(t.text or "" for t in el.iter(qn("w:t")))
            if (f"{{{{section:{code}}}}}" in texts
                or f"{{{{table:{code}" in texts
                or f"{{{{seq:" in texts):
                return True
    return False


def _get_block_elements(body, start_el, end_el) -> list:
    """获取 start_el 和 end_el 之间的所有 body 子元素（不含首尾标记）。"""
    elements = []
    in_range = False
    for child in body:
        if child is start_el:
            in_range = True
            continue
        if child is end_el:
            break
        if in_range:
            elements.append(child)
    return elements


def _is_heading(el) -> bool:
    """判断段落元素是否是 Heading 样式。

    XML pStyle val 在致同模板中：'2'=Heading1, '3'=Heading2, '4'=Heading3, '5'=Heading4。
    也可能是 'Heading1'/'heading1' 等英文样式名。
    """
    pPr = el.find(qn("w:pPr"))
    if pPr is None:
        return False
    pStyle = pPr.find(qn("w:pStyle"))
    if pStyle is not None:
        val = (pStyle.get(qn("w:val")) or "")
        val_lower = val.lower()
        # 英文样式名
        if "heading" in val_lower:
            return True
        # 致同模板数字样式：'2'=H1, '3'=H2, '4'=H3, '5'=H4
        if val in ("1", "2", "3", "4", "5", "6"):
            return True
    # 回退：大纲级别
    outlineLvl = pPr.find(qn("w:outlineLvl"))
    if outlineLvl is not None:
        return True
    return False


def _para_text(el) -> str:
    """获取段落元素的纯文本。"""
    return "".join(t.text or "" for t in el.iter(qn("w:t")))


def process_document(filepath: Path, *, write: bool) -> dict:
    """处理单个附注文档，注入 SECTION 块内部占位。"""
    doc = Document(str(filepath))
    body = doc.element.body
    paras = doc.paragraphs
    stats = {"seq": 0, "section": 0, "table": 0, "style_ref": 0, "skipped": 0}

    # 1) 找所有 SECTION 块的开始/结束元素
    sections = []
    i = 0
    while i < len(paras):
        t = (paras[i].text or "").strip()
        if t.startswith("##SECTION:") and not t.startswith("##/"):
            code = t.replace("##SECTION:", "").replace("##", "").strip()
            end_marker = f"##/SECTION:{code}##"
            start_el = paras[i]._element
            end_el = None
            for j in range(i + 1, min(i + 300, len(paras))):
                if end_marker in (paras[j].text or ""):
                    end_el = paras[j]._element
                    break
            if end_el is not None:
                sections.append((code, start_el, end_el))
                i = j + 1
            else:
                i += 1
        else:
            i += 1

    # 2) 对每个 SECTION 块注入占位
    for code, start_el, end_el in sections:
        block_elements = _get_block_elements(body, start_el, end_el)
        if not block_elements:
            continue

        # 幂等检测
        if _has_placeholder(block_elements, code):
            stats["skipped"] += 1
            continue

        prefix = _extract_prefix(code)
        heading_found = False
        text_marked = False
        table_index = 0

        for el in block_elements:
            if el.tag == qn("w:p"):
                if not heading_found and _is_heading(el):
                    # 标题行：在文本开头插入 {{seq:prefix}}
                    # 不改原文，在标题段前插一个占位段
                    if write:
                        _insert_paragraph_before_element(el, f"{{{{seq:{prefix}}}}}", body)
                    stats["seq"] += 1
                    heading_found = True
                elif heading_found and not text_marked and _para_text(el).strip():
                    # 第一个非空非标题文字段前：插 {{section:code}}
                    if not _is_heading(el):
                        if write:
                            _insert_paragraph_before_element(el, f"{{{{section:{code}}}}}", body)
                        stats["section"] += 1
                        text_marked = True

            elif el.tag == qn("w:tbl"):
                # 表格：在表格前插入 ##STYLE_REF + {{table:code:N}}
                if write:
                    _insert_paragraph_before_element(
                        el, f"##STYLE_REF:table:{code}:{table_index}##", body
                    )
                    # 重新定位表格（前面插了段落，表格位置后移了）
                    # 插入 {{table:}} 在 STYLE_REF 之后、表格之前
                    # 由于 body 元素顺序变了，需要重新找表格位置
                    tbl_idx = list(body).index(el)
                    table_p = OxmlElement("w:p")
                    run = OxmlElement("w:r")
                    t_el = OxmlElement("w:t")
                    t_el.text = f"{{{{table:{code}:{table_index}}}}}"
                    run.append(t_el)
                    table_p.append(run)
                    body.insert(tbl_idx, table_p)
                stats["table"] += 1
                stats["style_ref"] += 1
                table_index += 1

    if write:
        doc.save(str(filepath))
    return stats


def main():
    parser = argparse.ArgumentParser(description="Inject note section internal placeholders")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    mode = "WRITE" if args.write else "DRY-RUN"
    print(f"\n{'='*60}\n附注模板 SECTION 块内部占位注入 — {mode}\n{'='*60}\n")

    if args.write:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        for name in VARIANTS:
            src = NOTES_DIR / name
            if src.exists():
                shutil.copy2(src, BACKUP_DIR / name)
        print("  已备份到 _backup_placeholders/\n")

    for name in VARIANTS:
        filepath = NOTES_DIR / name
        if not filepath.exists():
            print(f"  MISSING: {name}")
            continue
        stats = process_document(filepath, write=args.write)
        print(f"📄 {name}")
        print(f"   seq={stats['seq']}  section={stats['section']}  "
              f"table={stats['table']}  style_ref={stats['style_ref']}  "
              f"skipped={stats['skipped']}")

    if not args.write:
        print("\n💡 确认后加 --write 执行")


if __name__ == "__main__":
    main()
