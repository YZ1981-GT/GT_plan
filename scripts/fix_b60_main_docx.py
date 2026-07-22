# -*- coding: utf-8 -*-
"""Fix B60 main docx: TOC, matrix, materiality, ch15 hint placement."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.text.paragraph import Paragraph

ROOT = Path(r"D:/GT_plan")
TPL = ROOT / "backend" / "wp_templates" / "B"


def find_src() -> Path:
    for p in (ROOT / "基础数据").rglob("*"):
        if p.is_dir() and p.name.startswith("B60 ") and "策略" in p.name:
            return p
    raise FileNotFoundError


def clear_para(p):
    p._p.clear_content() if False else None
    for r in list(p.runs):
        r.text = ""
    if not p.runs:
        p.add_run("")
    p.runs[0].text = ""


def set_para_text(p, text: str, *, blue: bool = False):
    if not p.runs:
        p.add_run(text)
    else:
        p.runs[0].text = text
        for r in p.runs[1:]:
            r.text = ""
    if blue and p.runs:
        p.runs[0].font.color.rgb = RGBColor(0x00, 0x00, 0xFF)


def insert_after(paragraph, text: str, *, blue: bool = False):
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    p = Paragraph(new_p, paragraph._parent)
    run = p.add_run(text)
    run.font.size = Pt(10.5)
    if blue:
        run.font.color.rgb = RGBColor(0x00, 0x00, 0xFF)
    return p


def add_table_after(paragraph, rows: list[list[str]]):
    doc = paragraph.part.document
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            table.cell(i, j).text = val
    paragraph._p.addnext(table._tbl)
    return table


def delete_paragraph(paragraph):
    p = paragraph._element
    p.getparent().remove(p)


def fix_doc(path: Path) -> dict:
    doc = Document(str(path))
    stats = {}

    # 1) Fix TOC line: keep only 十五 + page
    for p in doc.paragraphs:
        t = p.text
        if "对审计计划的更新和修改" in t and "\t" in t:
            # TOC entry
            set_para_text(p, "十五、对审计计划的更新和修改\t29")
            stats["toc_fixed"] = True
        if t.startswith("【触发条件勾选】") and any(
            x.text.startswith("附件\t") or x.text.strip() == "附件" for x in doc.paragraphs
        ):
            # misplaced near TOC — delete; will re-add at body ch15
            # only delete if previous sibling looks like TOC 十五
            stats["will_remove_toc_hint"] = True

    # Remove misplaced trigger hints that sit between TOC 十五 and 附件
    to_delete = []
    paras = list(doc.paragraphs)
    for i, p in enumerate(paras):
        if p.text.startswith("【触发条件勾选】"):
            # if next few contain 附件 as TOC
            nearby = "".join(x.text for x in paras[max(0, i - 1) : i + 2])
            if "附件" in nearby and "十五、对审计计划" in nearby:
                to_delete.append(p)
    for p in to_delete:
        delete_paragraph(p)
        stats["removed_toc_hint"] = True

    # 2) Fix materiality line
    for p in doc.paragraphs:
        if "B19-1" in p.text and "B15" in p.text and "重要性" in p.text:
            set_para_text(p, "重要性水平结论详见B19-1；计算过程详见B15。")
            stats["materiality_fixed"] = True

    # 3) Insert applicability matrix after body title「总体审计策略」(first occurrence after TOC)
    if not any("附件适用性勾选矩阵" in p.text for p in doc.paragraphs):
        anchor = None
        for p in doc.paragraphs:
            if p.text.strip() == "总体审计策略":
                anchor = p
                break
        if anchor is None:
            for p in doc.paragraphs:
                if p.text.strip().startswith("一、审计工作范围"):
                    anchor = p
                    break
        if anchor:
            title = insert_after(
                anchor,
                "〇、附件适用性勾选矩阵（编制正文前先勾选；质控必查）",
                blue=True,
            )
            rows = [
                ["判断项", "是/否", "须编制附件", "备注"],
                ["整合审计 / 仅内控审计", "", "B60A", ""],
                ["IPO / 申报财务报表审计", "", "B60B", ""],
                ["国有企业年度财务报表审计", "", "B60C", ""],
                ["需向证监局等报送审计计划", "", "B60D", "非集团策略底稿"],
                ["适用 IT 审计（主稿三（六）任一勾选）", "", "B60-2-1；IT团队执行再要2-2、2-3", ""],
                ["利用评估（或其他）专家", "", "B60-3", ""],
                ["集团且利用组成部分注册会计师", "", "主稿第八章 + B30-2", "勿用B60D代替"],
            ]
            add_table_after(title, rows)
            # hint after last table
            last_tbl = doc.tables[-1]
            hint = OxmlElement("w:p")
            last_tbl._tbl.addnext(hint)
            hp = Paragraph(hint, last_tbl._parent)
            r = hp.add_run(
                "【填写规则】本底稿为总体审计策略+计划层摘要。风险与应对细节索引B50/B30及各循环程序表，禁止粘贴B50全文；"
                "若无增量信息，填「无超出B50的补充」。第七章 SCOT+/仅重大表须填：循环代码、拟用程序底稿索引、是否拟依赖控制、风险ID/B50行号。"
            )
            r.font.color.rgb = RGBColor(0x00, 0x00, 0xFF)
            r.font.size = Pt(10.5)
            stats["matrix_inserted"] = True

    # 4) Ensure body chapter 十五 has trigger hint once
    body_ch15 = None
    for p in doc.paragraphs:
        if p.text.strip() == "十五、对审计计划的更新和修改":
            body_ch15 = p
    if body_ch15:
        # check if next para already trigger
        nxt = body_ch15._p.getnext()
        has_hint = False
        if nxt is not None and nxt.tag == qn("w:p"):
            np = Paragraph(nxt, body_ch15._parent)
            if "触发条件勾选" in np.text:
                has_hint = True
        if not has_hint:
            insert_after(
                body_ch15,
                "【触发条件勾选】集团安排重大调整 / 重要性重定 / IT或专家安排重大调整 / KAM变化 / "
                "新舞弊迹象或程序重大变化 / 进度重大调整 / 关注函举报或融资退市风险 / 无上述情形（须书面说明本期无重大修改）。"
                "修改轮次表应评估：对已执行程序充分性的影响（无需追加 / 需追加—索引 / 需重做—索引）。",
                blue=True,
            )
            stats["ch15_hint"] = True

    doc.save(str(path))
    return stats


def main():
    src = find_src()
    report = {}
    for folder, tag in ((TPL, "tpl"), (src, "src")):
        main_docx = [
            f
            for f in folder.iterdir()
            if f.suffix.lower() == ".docx" and f.name.startswith("B60 ") and not f.name.startswith("B60-")
        ][0]
        report[tag] = {"path": str(main_docx), **fix_doc(main_docx)}
    print(report)


if __name__ == "__main__":
    main()
