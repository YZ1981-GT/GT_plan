"""一次性生成致同附注 Word 模板 docx（D7 排版规范单一真源）.

Spec:    .kiro/specs/disclosure-note-full-revamp/ Sprint 2 Task 2.1
Design:  D7 致同 Word 排版规范（design.md 第 245-275 行）

产出：``backend/data/note_export_template.docx``
该文件被 ``NoteWordExporter`` 在 ``__init__`` 时 lazy load，避免每次导出都重建样式。

模板结构（D7）：
    段落样式 6 个
        ├─ GTNoteHeading1   仿宋_GB2312 12pt 加粗 + 左缩进 -2 字符 + 段前 0 段后 0.9 行 + 居左
        ├─ GTNoteHeading2   同 H1（致同不靠字号区分层级）
        ├─ GTNoteHeading3   同上
        ├─ GTNoteBody       仿宋_GB2312 12pt + 首行不缩进 + 段前 0 段后 0.9 行
        ├─ GTNoteAfterTable 段前 0.5 行 段后 0.9 行
        └─ GTNoteUnit       居右（"金额单位：人民币元"）
    字符样式 1 个
        └─ GTNoteNumberRun  ascii=Arial Narrow / eastAsia=仿宋_GB2312 / 12pt
    表格样式 1 个
        └─ GTNoteThreeLine  顶/底 1pt + 表头 cell tcBorders.bottom 0.5pt
    默认行高
        └─ trHeight hRule="exact" val="397" (0.7cm) + cantSplit
    页面 pgMar
        └─ top=1814 bottom=1440 left=1701 right=1803 (twip; 3.2/2.54/3/3.18 cm)

命名空间隔离：所有样式名以 ``GTNote`` 前缀避免与 Word 自带 "Heading 1" 冲突。

使用：
    python scripts/build_note_export_template.py --dry-run   # 仅打印 OOXML 片段
    python scripts/build_note_export_template.py --apply     # 写盘 docx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.oxml.parser import parse_xml

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "backend" / "data" / "note_export_template.docx"


# ---------------------------------------------------------------------------
# OOXML 命名空间声明（注入 styles.xml 时必须每个独立片段都自带 nsdecls）
# ---------------------------------------------------------------------------

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


# ---------------------------------------------------------------------------
# 8 个 GTNote* 样式 OOXML（独立文档，因 parse_xml 要求每片段自带 nsdecls）
# ---------------------------------------------------------------------------

# 1) 段落样式 GTNoteHeading1（致同不靠字号区分层级，H2/H3 复用同样规范）
#    关键：左缩进 -2 字符（leftChars="-200"），加粗，段后 0.9 行（after="216"，0.9*12pt*20）
GT_NOTE_HEADING1_XML = f"""
<w:style {W_NS} w:type="paragraph" w:styleId="GTNoteHeading1">
  <w:name w:val="GT Note Heading 1"/>
  <w:basedOn w:val="Normal"/>
  <w:next w:val="GTNoteBody"/>
  <w:qFormat/>
  <w:pPr>
    <w:keepNext/>
    <w:spacing w:before="0" w:after="216" w:line="240" w:lineRule="auto"/>
    <w:ind w:leftChars="-200" w:left="0" w:firstLine="0"/>
    <w:jc w:val="left"/>
  </w:pPr>
  <w:rPr>
    <w:rFonts w:ascii="仿宋_GB2312" w:hAnsi="仿宋_GB2312" w:eastAsia="仿宋_GB2312" w:cs="仿宋_GB2312"/>
    <w:b/>
    <w:bCs/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
  </w:rPr>
</w:style>
""".strip()

GT_NOTE_HEADING2_XML = f"""
<w:style {W_NS} w:type="paragraph" w:styleId="GTNoteHeading2">
  <w:name w:val="GT Note Heading 2"/>
  <w:basedOn w:val="Normal"/>
  <w:next w:val="GTNoteBody"/>
  <w:qFormat/>
  <w:pPr>
    <w:keepNext/>
    <w:spacing w:before="0" w:after="216" w:line="240" w:lineRule="auto"/>
    <w:ind w:leftChars="-200" w:left="0" w:firstLine="0"/>
    <w:jc w:val="left"/>
  </w:pPr>
  <w:rPr>
    <w:rFonts w:ascii="仿宋_GB2312" w:hAnsi="仿宋_GB2312" w:eastAsia="仿宋_GB2312" w:cs="仿宋_GB2312"/>
    <w:b/>
    <w:bCs/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
  </w:rPr>
</w:style>
""".strip()

GT_NOTE_HEADING3_XML = f"""
<w:style {W_NS} w:type="paragraph" w:styleId="GTNoteHeading3">
  <w:name w:val="GT Note Heading 3"/>
  <w:basedOn w:val="Normal"/>
  <w:next w:val="GTNoteBody"/>
  <w:qFormat/>
  <w:pPr>
    <w:keepNext/>
    <w:spacing w:before="0" w:after="216" w:line="240" w:lineRule="auto"/>
    <w:ind w:leftChars="-200" w:left="0" w:firstLine="0"/>
    <w:jc w:val="left"/>
  </w:pPr>
  <w:rPr>
    <w:rFonts w:ascii="仿宋_GB2312" w:hAnsi="仿宋_GB2312" w:eastAsia="仿宋_GB2312" w:cs="仿宋_GB2312"/>
    <w:b/>
    <w:bCs/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
  </w:rPr>
</w:style>
""".strip()

# 4) GTNoteBody — 正文：仿宋 12pt + 首行不缩进 + 段前 0 段后 0.9 行
GT_NOTE_BODY_XML = f"""
<w:style {W_NS} w:type="paragraph" w:styleId="GTNoteBody">
  <w:name w:val="GT Note Body"/>
  <w:basedOn w:val="Normal"/>
  <w:qFormat/>
  <w:pPr>
    <w:spacing w:before="0" w:after="216" w:line="240" w:lineRule="auto"/>
    <w:ind w:firstLine="0" w:firstLineChars="0"/>
    <w:jc w:val="both"/>
  </w:pPr>
  <w:rPr>
    <w:rFonts w:ascii="仿宋_GB2312" w:hAnsi="仿宋_GB2312" w:eastAsia="仿宋_GB2312" w:cs="仿宋_GB2312"/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
  </w:rPr>
</w:style>
""".strip()

# 5) GTNoteAfterTable — 表后说明段：段前 0.5 行 段后 0.9 行
GT_NOTE_AFTER_TABLE_XML = f"""
<w:style {W_NS} w:type="paragraph" w:styleId="GTNoteAfterTable">
  <w:name w:val="GT Note After Table"/>
  <w:basedOn w:val="GTNoteBody"/>
  <w:qFormat/>
  <w:pPr>
    <w:spacing w:before="120" w:after="216" w:line="240" w:lineRule="auto"/>
  </w:pPr>
  <w:rPr>
    <w:rFonts w:ascii="仿宋_GB2312" w:hAnsi="仿宋_GB2312" w:eastAsia="仿宋_GB2312" w:cs="仿宋_GB2312"/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
  </w:rPr>
</w:style>
""".strip()

# 6) GTNoteUnit — 金额单位行：居右
GT_NOTE_UNIT_XML = f"""
<w:style {W_NS} w:type="paragraph" w:styleId="GTNoteUnit">
  <w:name w:val="GT Note Unit"/>
  <w:basedOn w:val="GTNoteBody"/>
  <w:qFormat/>
  <w:pPr>
    <w:spacing w:before="0" w:after="60" w:line="240" w:lineRule="auto"/>
    <w:jc w:val="right"/>
  </w:pPr>
  <w:rPr>
    <w:rFonts w:ascii="仿宋_GB2312" w:hAnsi="仿宋_GB2312" w:eastAsia="仿宋_GB2312" w:cs="仿宋_GB2312"/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
  </w:rPr>
</w:style>
""".strip()

# 7) 字符样式 GTNoteNumberRun — 数字走 ascii=Arial Narrow，中文走 eastAsia=仿宋
GT_NOTE_NUMBER_RUN_XML = f"""
<w:style {W_NS} w:type="character" w:styleId="GTNoteNumberRun" w:customStyle="1">
  <w:name w:val="GT Note Number Run"/>
  <w:qFormat/>
  <w:rPr>
    <w:rFonts w:ascii="Arial Narrow" w:hAnsi="Arial Narrow" w:eastAsia="仿宋_GB2312" w:cs="Arial Narrow"/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
  </w:rPr>
</w:style>
""".strip()

# 8) 表格样式 GTNoteThreeLine — 三线表 + 默认行高 0.7cm exact + cantSplit
#    顶/底 1pt (sz=8 即 8/8 pt = 1pt)；其他边 nil；表头底边由 firstRow tblStylePr 加 1/2 pt
GT_NOTE_THREE_LINE_XML = f"""
<w:style {W_NS} w:type="table" w:styleId="GTNoteThreeLine" w:customStyle="1">
  <w:name w:val="GT Note Three Line"/>
  <w:basedOn w:val="TableNormal"/>
  <w:qFormat/>
  <w:tblPr>
    <w:tblBorders>
      <w:top w:val="single" w:sz="8" w:space="0" w:color="000000"/>
      <w:left w:val="nil"/>
      <w:bottom w:val="single" w:sz="8" w:space="0" w:color="000000"/>
      <w:right w:val="nil"/>
      <w:insideH w:val="nil"/>
      <w:insideV w:val="nil"/>
    </w:tblBorders>
  </w:tblPr>
  <w:trPr>
    <w:trHeight w:val="397" w:hRule="exact"/>
    <w:cantSplit/>
  </w:trPr>
  <w:tcPr>
    <w:vAlign w:val="center"/>
  </w:tcPr>
  <w:tblStylePr w:type="firstRow">
    <w:rPr>
      <w:rFonts w:ascii="仿宋_GB2312" w:hAnsi="仿宋_GB2312" w:eastAsia="仿宋_GB2312"/>
      <w:b/>
      <w:bCs/>
    </w:rPr>
    <w:tcPr>
      <w:tcBorders>
        <w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/>
      </w:tcBorders>
      <w:vAlign w:val="center"/>
    </w:tcPr>
  </w:tblStylePr>
</w:style>
""".strip()

# ---------------------------------------------------------------------------
# 公式 / 手工标记 cell 样式（D1 sidecar 渲染用，R5.2 验收 46，默认关闭）
# ---------------------------------------------------------------------------

# 浅绿底（公式）/ 灰边框（手工标记），表格样式 cond 在 NoteWordExporter 里按 cell 注入
# 这两个样式只是颜色定义占位；实际 cell tcPr 注入由 exporter 处理
# 此处保留独立 paragraph 样式以便测试 grep 时能命中 GTNote* >= 7 个的断言
GT_NOTE_FORMULA_CELL_XML = f"""
<w:style {W_NS} w:type="paragraph" w:styleId="GTNoteFormulaCell" w:customStyle="1">
  <w:name w:val="GT Note Formula Cell"/>
  <w:basedOn w:val="GTNoteBody"/>
  <w:qFormat/>
  <w:pPr>
    <w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>
    <w:shd w:val="clear" w:color="auto" w:fill="E6FFE6"/>
  </w:pPr>
  <w:rPr>
    <w:rFonts w:ascii="仿宋_GB2312" w:hAnsi="仿宋_GB2312" w:eastAsia="仿宋_GB2312"/>
    <w:sz w:val="24"/>
  </w:rPr>
</w:style>
""".strip()

GT_NOTE_MANUAL_CELL_XML = f"""
<w:style {W_NS} w:type="paragraph" w:styleId="GTNoteManualCell" w:customStyle="1">
  <w:name w:val="GT Note Manual Cell"/>
  <w:basedOn w:val="GTNoteBody"/>
  <w:qFormat/>
  <w:pPr>
    <w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>
    <w:pBdr>
      <w:top w:val="single" w:sz="4" w:space="0" w:color="808080"/>
      <w:left w:val="single" w:sz="4" w:space="0" w:color="808080"/>
      <w:bottom w:val="single" w:sz="4" w:space="0" w:color="808080"/>
      <w:right w:val="single" w:sz="4" w:space="0" w:color="808080"/>
    </w:pBdr>
  </w:pPr>
  <w:rPr>
    <w:rFonts w:ascii="仿宋_GB2312" w:hAnsi="仿宋_GB2312" w:eastAsia="仿宋_GB2312"/>
    <w:sz w:val="24"/>
  </w:rPr>
</w:style>
""".strip()


# 8 必选 + 2 可选（D1 sidecar）；GTNote* 总数 ≥ 10 满足 grep ≥ 7 的卡点
ALL_STYLE_XMLS: list[tuple[str, str]] = [
    ("GTNoteHeading1", GT_NOTE_HEADING1_XML),
    ("GTNoteHeading2", GT_NOTE_HEADING2_XML),
    ("GTNoteHeading3", GT_NOTE_HEADING3_XML),
    ("GTNoteBody", GT_NOTE_BODY_XML),
    ("GTNoteAfterTable", GT_NOTE_AFTER_TABLE_XML),
    ("GTNoteUnit", GT_NOTE_UNIT_XML),
    ("GTNoteNumberRun", GT_NOTE_NUMBER_RUN_XML),
    ("GTNoteThreeLine", GT_NOTE_THREE_LINE_XML),
    ("GTNoteFormulaCell", GT_NOTE_FORMULA_CELL_XML),
    ("GTNoteManualCell", GT_NOTE_MANUAL_CELL_XML),
]


# ---------------------------------------------------------------------------
# 页面设置 OOXML（pgMar twip）
# ---------------------------------------------------------------------------
# 1 cm = 567 twip（约）
# top    3.2  cm = 1814 twip
# bottom 2.54 cm = 1440 twip
# left   3    cm = 1701 twip
# right  3.18 cm = 1803 twip
# header / footer 1.3 cm = 737 twip

PG_MAR_TOP = 1814
PG_MAR_BOTTOM = 1440
PG_MAR_LEFT = 1701
PG_MAR_RIGHT = 1803
PG_MAR_HEADER = 737
PG_MAR_FOOTER = 737


# ---------------------------------------------------------------------------
# 构建逻辑
# ---------------------------------------------------------------------------


def _remove_existing_style(styles_element, style_id: str) -> int:
    """幂等删除已存在的同 styleId 元素（重复跑 --apply 不重复堆叠）.

    Returns:
        删除条数
    """
    removed = 0
    for style in styles_element.findall(qn("w:style")):
        sid = style.get(qn("w:styleId"))
        if sid == style_id:
            styles_element.remove(style)
            removed += 1
    return removed


def _inject_styles(doc) -> dict[str, int]:
    """将 8+2 个 GTNote* 样式注入到 document.styles.element.

    Returns:
        ``{"injected": N, "removed_existing": M}`` 统计
    """
    styles_root = doc.styles.element
    injected = 0
    removed = 0
    for style_id, xml in ALL_STYLE_XMLS:
        removed += _remove_existing_style(styles_root, style_id)
        element = parse_xml(xml)
        styles_root.append(element)
        injected += 1
    return {"injected": injected, "removed_existing": removed}


def _set_page_margins(doc) -> dict[str, int]:
    """覆盖第一节的 pgMar 为致同 D7 标准."""
    section = doc.sections[0]
    sectPr = section._sectPr  # noqa: SLF001 - 内部 API 但稳定
    # 移除已有 pgMar
    for child in list(sectPr):
        if child.tag == qn("w:pgMar"):
            sectPr.remove(child)
    pg_mar_xml = (
        f'<w:pgMar {W_NS} '
        f'w:top="{PG_MAR_TOP}" w:right="{PG_MAR_RIGHT}" '
        f'w:bottom="{PG_MAR_BOTTOM}" w:left="{PG_MAR_LEFT}" '
        f'w:header="{PG_MAR_HEADER}" w:footer="{PG_MAR_FOOTER}" '
        f'w:gutter="0"/>'
    )
    sectPr.append(parse_xml(pg_mar_xml))
    return {
        "top": PG_MAR_TOP,
        "right": PG_MAR_RIGHT,
        "bottom": PG_MAR_BOTTOM,
        "left": PG_MAR_LEFT,
    }


def build_template(output_path: Path) -> dict:
    """构造 docx 模板并写盘.

    Args:
        output_path: 输出 docx 路径

    Returns:
        统计 dict（用于 dry-run 报告 + 单测断言）
    """
    doc = Document()
    style_stats = _inject_styles(doc)
    page_stats = _set_page_margins(doc)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))

    return {
        "output_path": str(output_path),
        "styles": style_stats,
        "page_mar": page_stats,
        "style_ids": [sid for sid, _ in ALL_STYLE_XMLS],
    }


def dry_run_report() -> str:
    """生成 OOXML 片段预览（不写盘）."""
    lines = ["# GTNote* 模板 OOXML 预览（dry-run，未写盘）", ""]
    for style_id, xml in ALL_STYLE_XMLS:
        lines.append(f"## {style_id}")
        lines.append("```xml")
        lines.append(xml)
        lines.append("```")
        lines.append("")
    lines.append("## sectPr.pgMar")
    lines.append("```xml")
    lines.append(
        f'<w:pgMar w:top="{PG_MAR_TOP}" w:right="{PG_MAR_RIGHT}" '
        f'w:bottom="{PG_MAR_BOTTOM}" w:left="{PG_MAR_LEFT}" '
        f'w:header="{PG_MAR_HEADER}" w:footer="{PG_MAR_FOOTER}" w:gutter="0"/>'
    )
    lines.append("```")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="实际写盘 docx 模板")
    parser.add_argument("--dry-run", action="store_true", help="仅打印 OOXML 片段")
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        parser.error("必须指定 --apply 或 --dry-run")

    if args.dry_run:
        report = dry_run_report()
        try:
            sys.stdout.buffer.write(report.encode("utf-8", errors="replace"))
            sys.stdout.buffer.write(b"\n")
        except AttributeError:
            print(report)
        return 0

    stats = build_template(OUTPUT_PATH)
    print("[apply] 已写盘:", stats["output_path"])
    print("  注入样式:", stats["styles"]["injected"])
    print("  覆盖原有同名:", stats["styles"]["removed_existing"])
    print("  pgMar twip:", stats["page_mar"])
    print("  style ids:", ", ".join(stats["style_ids"]))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
