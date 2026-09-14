# -*- coding: utf-8 -*-
"""B60 P2 fixup: actually expand B60A; compress B60B regulation dumps."""
from __future__ import annotations

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


def resolve(folder: Path, prefix: str) -> Path:
    for f in folder.iterdir():
        if f.name.startswith(prefix) and f.suffix.lower() == ".docx":
            return f
    raise FileNotFoundError(prefix)


def blue_run(p, text):
    r = p.add_run(text)
    r.font.color.rgb = RGBColor(0x00, 0x00, 0xFF)
    r.font.size = Pt(10.5)


def wipe(p, text, blue=False):
    el = p._p
    pPr = el.find(qn("w:pPr"))
    for child in list(el):
        if child is not pPr:
            el.remove(child)
    r = OxmlElement("w:r")
    if blue:
        rPr = OxmlElement("w:rPr")
        color = OxmlElement("w:color")
        color.set(qn("w:val"), "0000FF")
        rPr.append(color)
        r.append(rPr)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    el.append(r)


def insert_block_before(target: Paragraph, title: str, rows: list[list[str]], tip: str | None):
    """Insert title + table + optional tip immediately before target paragraph."""
    # tip (closest to target)
    if tip:
        tip_el = OxmlElement("w:p")
        target._p.addprevious(tip_el)
        tp = Paragraph(tip_el, target._parent)
        blue_run(tp, tip)
        target = tp

    doc = target.part.document
    tbl = doc.add_table(rows=len(rows), cols=len(rows[0]))
    tbl.style = "Table Grid"
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            tbl.cell(i, j).text = val
    target._p.addprevious(tbl._tbl)

    title_el = OxmlElement("w:p")
    tbl._tbl.addprevious(title_el)
    tp = Paragraph(title_el, target._parent)
    tp.add_run(title)


def patch_a(path: Path) -> dict:
    doc = Document(str(path))
    if any(p.text.strip().startswith("三（补充）、与财务报表审计范围的差异") for p in doc.paragraphs):
        return {"skip": True}

    target = None
    for p in doc.paragraphs:
        if "内部控制自我评价情况" in p.text:
            target = p
            break
    if target is None:
        return {"error": "no anchor"}

    blocks = [
        (
            "三（补充）、与财务报表审计范围的差异",
            [
                ["事项", "是否存在差异", "差异说明", "对程序/证据的影响"],
                ["重要账户与披露范围", "", "", ""],
                ["业务层面控制测试范围", "", "", ""],
                ["IT 一般控制/应用控制范围", "", "", ""],
                ["基准日与报告涵盖期间", "", "", ""],
                ["其他", "", "", ""],
            ],
            "【无差异时在「是否存在差异」列填「否」。】",
        ),
        (
            "三（补充）、重要账户/披露与业务层面控制范围",
            [
                ["重要账户或披露", "相关认定", "拟测试的关键控制（简述）", "底稿索引", "备注"],
                ["", "", "", "", ""],
                ["", "", "", "", ""],
                ["", "", "", "", ""],
            ],
            "【可与 B50 SCOT+/仅重大及 C 循环程序表勾稽。】",
        ),
        (
            "三（补充）、缺陷评价标准对齐",
            [
                ["检查项", "是/否/说明", "索引"],
                ["已获取管理层内部控制自我评价报告", "", ""],
                ["评价报告要素完整（按评价指引）", "", ""],
                ["董事会缺陷评价标准符合《企业内部控制评价指引》", "", ""],
                ["企审双方对重大缺陷结论是否一致", "", ""],
                ["不一致时对内控审计意见类型/报告内容的影响", "", ""],
            ],
            None,
        ),
        (
            "三（补充）、IT 对 ICFR 意见的影响",
            [
                ["项目", "结论/安排", "索引"],
                ["是否适用 IT 审计（见 B60-2-1）", "", "B60-2-1"],
                ["ITGC/ITAC 对财务报告内控有效性的初步影响", "", "B60-2-3 / B22A"],
                ["已知 IT 缺陷（如有）及对 ICFR 意见影响", "", ""],
            ],
            "【整合审计时本表必填；可与 B60 第三章（六）勾稽。】",
        ),
    ]
    # insert in reverse so final order matches blocks
    for title, rows, tip in reversed(blocks):
        insert_block_before(target, title, rows, tip)

    # baseline table after 审计目标 heading
    if not any("基准日及意见对象" in p.text for p in doc.paragraphs):
        goal = None
        for p in doc.paragraphs:
            if p.text.strip() == "审计目标":
                goal = p
                break
        if goal:
            # insert after goal: find next para as target for "before next"? simpler add after goal
            nxt = goal._p.getnext()
            # create title after goal
            title_el = OxmlElement("w:p")
            goal._p.addnext(title_el)
            tp = Paragraph(title_el, goal._parent)
            blue_run(tp, "基准日及意见对象（摘录）")
            rows = [
                ["项目", "内容"],
                ["内控审计基准日", "202X年XX月XX日"],
                ["意见对象", "财务报告内部控制有效性"],
                ["非财务报告重大缺陷", "注意到的在报告中增加描述段（如适用）"],
                ["是否与财报审计整合执行", "是 / 否"],
            ]
            tbl = doc.add_table(rows=len(rows), cols=2)
            tbl.style = "Table Grid"
            for i, row in enumerate(rows):
                for j, val in enumerate(row):
                    tbl.cell(i, j).text = val
            tp._p.addnext(tbl._tbl)

    doc.save(str(path))
    return {"added": [b[0] for b in blocks], "baseline": True}


def patch_b(path: Path) -> dict:
    doc = Document(str(path))
    stats = {"wiped": 0, "deleted": 0}

    # Identify zones:
    # After "1、延伸检查" heading: wipe tip P13, delete P14-P16 until "2、资金流水核查"
    # After "2、资金流水核查": wipe tip P18, delete long paras until "3、其他核查程序"

    paras = list(doc.paragraphs)
    # pass 1: find indices
    idx_ext_tip = idx_cash_tip = None
    idx_cash_head = idx_other_head = None
    for i, p in enumerate(paras):
        t = p.text.strip()
        if t.startswith("1、延伸检查") and len(t) < 20:
            # next tip
            pass
        if "执行延伸检查程序的要求" in t:
            idx_ext_tip = i
        if t.startswith("2、资金流水核查"):
            idx_cash_head = i
        if "执行资金流水核查程序的要求" in t:
            idx_cash_tip = i
        if t.startswith("3、其他核查程序"):
            idx_other_head = i

    short_ext = (
        "【依据索引—延伸检查】《会计监管风险提示第4号》（证监办发〔2012〕89号）；"
        "证监会公告〔2012〕14号；发行监管函〔2012〕551号。正文只填上表；细则见 S32。"
    )
    short_cash = (
        "【依据索引—资金流水】证监会公告〔2012〕14号；《会计监管风险提示第2号》；"
        "发行监管函〔2012〕551号；《首发业务若干问题解答》（2020年6月版）第54条。正文只填核查表；细则见 S33。"
    )

    if idx_ext_tip is not None:
        wipe(paras[idx_ext_tip], short_ext, blue=True)
        stats["wiped"] += 1
        # delete until cash head
        end = idx_cash_head if idx_cash_head is not None else idx_ext_tip + 1
        for j in range(idx_ext_tip + 1, end):
            # re-get because indices shift — collect elements first
            pass
        to_del = []
        for j in range(idx_ext_tip + 1, end):
            to_del.append(paras[j]._p)
        for el in to_del:
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
                stats["deleted"] += 1

    # refresh
    paras = list(doc.paragraphs)
    idx_cash_tip = idx_other_head = None
    for i, p in enumerate(paras):
        t = p.text.strip()
        if "执行资金流水核查程序的要求" in t or t.startswith("【依据索引—资金流水】"):
            if "依据索引" in t:
                idx_cash_tip = None  # already done
            else:
                idx_cash_tip = i
        if "资金流水核查程序的要求" in t and "依据索引" not in t:
            idx_cash_tip = i
        if t.startswith("3、其他核查程序"):
            idx_other_head = i

    if idx_cash_tip is not None:
        wipe(paras[idx_cash_tip], short_cash, blue=True)
        stats["wiped"] += 1
        end = idx_other_head if idx_other_head is not None else idx_cash_tip + 1
        to_del = []
        for j in range(idx_cash_tip + 1, end):
            to_del.append(paras[j]._p)
        for el in to_del:
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
                stats["deleted"] += 1

    doc.save(str(path))
    return stats


def main():
    import json

    src = find_src()
    report = {}
    for folder, tag in ((TPL, "tpl"), (src, "src")):
        report[tag] = {
            "A": patch_a(resolve(folder, "B60A")),
            "B": patch_b(resolve(folder, "B60B")),
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
