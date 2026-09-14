# -*- coding: utf-8 -*-
"""B60 P2: expand A/B/C, harden D/3, align B60-1 hours sheet."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import openpyxl
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
    raise FileNotFoundError("src B60 dir")


def resolve(folder: Path, prefix: str, suffix: str) -> Path:
    for f in folder.iterdir():
        if f.name.startswith(prefix) and f.suffix.lower() == suffix:
            return f
    raise FileNotFoundError(f"{prefix}*{suffix}")


def blue_run(p: Paragraph, text: str):
    r = p.add_run(text)
    r.font.color.rgb = RGBColor(0x00, 0x00, 0xFF)
    r.font.size = Pt(10.5)
    return r


def insert_para_after(paragraph, text: str = "", *, blue: bool = False) -> Paragraph:
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    p = Paragraph(new_p, paragraph._parent)
    if text:
        if blue:
            blue_run(p, text)
        else:
            p.add_run(text)
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


def append_cells(row, texts: list[str]):
    for text in texts:
        tc = deepcopy(row.cells[-1]._tc)
        for child in list(tc):
            if child.tag != qn("w:tcPr"):
                tc.remove(child)
        p = OxmlElement("w:p")
        r = OxmlElement("w:r")
        t = OxmlElement("w:t")
        t.set(qn("xml:space"), "preserve")
        t.text = text
        r.append(t)
        p.append(r)
        tc.append(p)
        row._tr.append(tc)


def set_para(p: Paragraph, text: str, *, blue: bool = False):
    if not p.runs:
        p.add_run("")
    p.runs[0].text = text
    for r in p.runs[1:]:
        r.text = ""
    if blue and p.runs:
        p.runs[0].font.color.rgb = RGBColor(0x00, 0x00, 0xFF)


def wipe_para(p: Paragraph, text: str, *, blue: bool = False):
    el = p._p
    pPr = el.find(qn("w:pPr"))
    for child in list(el):
        if child is not pPr:
            el.remove(child)
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    if blue:
        rPr = OxmlElement("w:rPr")
        color = OxmlElement("w:color")
        color.set(qn("w:val"), "0000FF")
        rPr.append(color)
        r.append(rPr)
    r.append(t)
    el.append(r)


def find_para(doc: Document, needle: str):
    for p in doc.paragraphs:
        if needle in p.text:
            return p
    return None


def has_text(doc: Document, needle: str) -> bool:
    return any(needle in p.text for p in doc.paragraphs)


# ---------- B60A ----------
def patch_b60a(path: Path) -> dict:
    doc = Document(str(path))
    stats = {"added": []}
    if has_text(doc, "与财报审计范围差异"):
        stats["skip"] = "already expanded"
        return stats

    # After 适用的内控审计准则 tip, before 三、了解内部控制 — insert structured blocks
    # Simpler: append new sections before 四、自我评价 or at end before last tip
    anchor = find_para(doc, "对被审计单位的内部控制自我评价情况")
    if anchor is None:
        anchor = doc.paragraphs[-1]

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

    # Insert BEFORE 自我评价 section: walk backwards by inserting after a marker we create once
    # Insert in reverse so order is preserved when always inserting after same anchor's previous
    # Better: insert after "对企业利用信息技术的考虑" section tip
    insert_at = find_para(doc, "对企业利用信息技术的考虑")
    if insert_at is None:
        insert_at = find_para(doc, "了解内部控制")
    if insert_at is None:
        insert_at = doc.paragraphs[3]

    cursor = insert_at
    # move to end of IT subsection — find 自我评价 and insert before it by using element before
    target = find_para(doc, "对被审计单位的内部控制自我评价情况")
    if target is not None:
        # insert content before target by adding previous siblings in reverse
        prev = target
        for title, rows, tip in reversed(blocks):
            # build from tip -> table -> title so final order is title, table, tip
            if tip:
                tip_p = OxmlElement("w:p")
                prev._p.addprevious(tip_p)
                tp = Paragraph(tip_p, prev._parent)
                blue_run(tp, tip)
                prev = tp
            # table
            tbl_doc = doc.add_table(rows=len(rows), cols=len(rows[0]))
            tbl_doc.style = "Table Grid"
            for i, row in enumerate(rows):
                for j, val in enumerate(row):
                    tbl_doc.cell(i, j).text = val
            prev._p.addprevious(tbl_doc._tbl)
            # title
            title_p = OxmlElement("w:p")
            tbl_doc._tbl.addprevious(title_p)
            tp = Paragraph(title_p, prev._parent)
            tp.add_run(title)
            prev = tp
            stats["added"].append(title)
    else:
        cursor = doc.paragraphs[-1]
        for title, rows, tip in blocks:
            cursor = insert_para_after(cursor, title)
            add_table_after(cursor, rows)
            cursor = Paragraph(doc.tables[-1]._tbl.getnext() or cursor._p, cursor._parent) if False else cursor
            if tip:
                # find last table and add tip after
                last = doc.tables[-1]
                tip_el = OxmlElement("w:p")
                last._tbl.addnext(tip_el)
                tp = Paragraph(tip_el, last._parent)
                blue_run(tp, tip)
                cursor = tp
            stats["added"].append(title)

    # Strengthen 审计目标 with baseline table if missing
    if not has_text(doc, "基准日及意见对象"):
        goal = find_para(doc, "审计目标")
        if goal:
            t = insert_para_after(goal, "基准日及意见对象（摘录）", blue=True)
            add_table_after(
                t,
                [
                    ["项目", "内容"],
                    ["内控审计基准日", "202X年XX月XX日"],
                    ["意见对象", "财务报告内部控制有效性"],
                    ["非财务报告重大缺陷", "注意到的在报告中增加描述段（如适用）"],
                    ["是否与财报审计整合执行", "是 / 否"],
                ],
            )
            stats["added"].append("基准日表")

    doc.save(str(path))
    return stats


# ---------- B60B ----------
def patch_b60b(path: Path) -> dict:
    doc = Document(str(path))
    stats = {"compressed": 0, "cols": 0}

    # Compress long regulation dumps into short 依据索引
    compress_map_prefixes = [
        ("【提示】中国证监会关于在IPO申报财务报表审计中执行延伸检查程序的要求",
         "【依据索引—延伸检查】《会计监管风险提示第4号》证监办发〔2012〕89号；证监会公告〔2012〕14号；发行监管函〔2012〕551号。正文只填上表对象/类别/时间/底稿索引，细则见专项底稿 S32。"),
        ("【提示】中国证监会关于在IPO申报财务报表审计中执行资金流水核查程序的要求",
         "【依据索引—资金流水】证监会公告〔2012〕14号；《会计监管风险提示第2号》；发行监管函〔2012〕551号；《首发业务若干问题解答》（2020年6月版）第54条。正文只填核查范围表；扩大范围条件见 S33。"),
    ]

    # Replace first matching long tip para; delete subsequent long regulation paras until next numbered heading
    paras = list(doc.paragraphs)
    i = 0
    while i < len(paras):
        t = paras[i].text.strip()
        replaced = False
        for prefix, short in compress_map_prefixes:
            if t.startswith(prefix) or (prefix[4:20] in t and t.startswith("【提示】")):
                # more robust: if 延伸检查程序的要求 in text
                if "延伸检查程序的要求" in t or "资金流水核查程序的要求" in t:
                    short = compress_map_prefixes[0][1] if "延伸检查" in t else compress_map_prefixes[1][1]
                    wipe_para(paras[i], short, blue=True)
                    stats["compressed"] += 1
                    # delete following long paras until we hit a short heading like "2、资金" or "3、其他"
                    j = i + 1
                    while j < len(paras):
                        jt = paras[j].text.strip()
                        if (
                            jt.startswith("2、资金流水")
                            or jt.startswith("3、其他核查")
                            or jt.startswith("【提示】以上内容")
                            or jt.startswith("二、")
                            or jt.startswith("三、")
                        ):
                            break
                        # keep if it's the 资金流水 tip header
                        if "资金流水核查程序的要求" in jt or "延伸检查程序的要求" in jt:
                            break
                        if len(jt) > 80 or jt.startswith("1、") or jt.startswith("（") or jt.startswith("保荐"):
                            el = paras[j]._p
                            el.getparent().remove(el)
                            stats["compressed"] += 1
                            paras = list(doc.paragraphs)
                            continue
                        if jt.startswith("1、") and "证监会" in jt:
                            el = paras[j]._p
                            el.getparent().remove(el)
                            stats["compressed"] += 1
                            paras = list(doc.paragraphs)
                            continue
                        # numbered regulation items
                        if jt and (jt[0].isdigit() or jt.startswith("（") or "发行人或" in jt or "保荐机构" in jt):
                            el = paras[j]._p
                            el.getparent().remove(el)
                            stats["compressed"] += 1
                            paras = list(doc.paragraphs)
                            continue
                        break
                    replaced = True
                    break
        if replaced:
            paras = list(doc.paragraphs)
            i += 1
            continue
        i += 1

    # Add 底稿索引 to 资金流水 table if missing
    for table in doc.tables:
        headers = [c.text.strip().replace("\n", "") for c in table.rows[0].cells]
        joined = "".join(headers)
        if "拟核查的人员范围" in joined and "底稿索引" not in joined:
            for ri, row in enumerate(table.rows):
                append_cells(row, ["底稿索引(S33)" if ri == 0 else ""])
            stats["cols"] += 1
        if "核查内容" in joined and "现金交易" in "".join(
            table.rows[1].cells[0].text if len(table.rows) > 1 else ""
        ):
            if "底稿索引" not in joined:
                for ri, row in enumerate(table.rows):
                    append_cells(row, ["底稿索引(S32/S34)" if ri == 0 else ""])
                stats["cols"] += 1
        # 专项报告表加「是否适用」
        if headers[:2] == ["报告内容", "预计出具时间"] or (
            "报告内容" in headers and "预计出具时间" in headers and "是否适用" not in headers
        ):
            if "是否适用" not in headers:
                for ri, row in enumerate(table.rows):
                    append_cells(row, ["是否适用(是/否)" if ri == 0 else ""])
                stats["cols"] += 1

    # Add note if not present
    if not has_text(doc, "法规长文已外置"):
        tip_anchor = find_para(doc, "对IPO申报财务报表审计的特殊考虑")
        if tip_anchor:
            insert_para_after(
                tip_anchor,
                "【编排说明】法规长文已外置为「依据索引」；计划正文只保留可填表。细则执行见 S32/S33/S34。",
                blue=True,
            )

    doc.save(str(path))
    return stats


# ---------- B60C ----------
def patch_b60c(path: Path) -> dict:
    doc = Document(str(path))
    stats = {"cols": 0, "trigger": False}

    # Expand focus table to 4 columns if still 3
    for table in doc.tables:
        headers = [c.text.strip().replace("\n", "") for c in table.rows[0].cells]
        if headers and "可能存在的常见问题" in headers[0]:
            if len(headers) == 3 or (len(headers) >= 3 and "拟执行程序索引" not in "".join(headers)):
                # rewrite headers
                table.rows[0].cells[0].text = "风险/问题"
                table.rows[0].cells[1].text = "相关账户、交易或披露"
                if len(table.rows[0].cells) >= 3:
                    table.rows[0].cells[2].text = "拟采取的总体应对措施"
                if "拟执行程序索引" not in "".join(c.text for c in table.rows[0].cells):
                    for ri, row in enumerate(table.rows):
                        append_cells(row, ["拟执行程序索引" if ri == 0 else ""])
                    stats["cols"] += 1
            break

    # Communication trigger checklist
    if not has_text(doc, "国资沟通触发条件勾选"):
        anchor = find_para(doc, "与监管机构沟通的时间计划")
        if anchor is None:
            anchor = find_para(doc, "与监管机构沟通")
        if anchor:
            t = insert_para_after(anchor, "国资沟通触发条件勾选（出现任一「是」须安排沟通并填上表）", blue=True)
            add_table_after(
                t,
                [
                    ["触发情形", "是/否", "计划沟通时点", "参与人"],
                    ["与管理层存在重大分歧", "", "", ""],
                    ["主审所与参审所之间存在重大分歧", "", "", ""],
                    ["影响审计意见类型或报告要素的重大事项", "", "", ""],
                    ["审计范围受限或其他重大困难", "", "", ""],
                    ["对审计计划的重大修改", "", "", ""],
                    ["其他重大审计/会计/内控或违法事项", "", "", ""],
                ],
            )
            stats["trigger"] = True

    doc.save(str(path))
    return stats


# ---------- B60D ----------
def patch_b60d(path: Path) -> dict:
    doc = Document(str(path))
    stats = {}
    if has_text(doc, "报送存档信息"):
        stats["skip"] = True
        return stats

    # Find tip table or first tip para
    anchor = find_para(doc, "本函件应打印在印有本所名称的信纸上")
    if anchor is None:
        anchor = find_para(doc, "项目组应确保报送的审计计划内容")
    if anchor is None and doc.paragraphs:
        anchor = doc.paragraphs[0]

    t = insert_para_after(anchor, "报送存档信息（副本归档必填）", blue=True)
    add_table_after(
        t,
        [
            ["项目", "内容"],
            ["致达日期", ""],
            ["收件人（监管机构及人员）", ""],
            ["报送方式（当面/邮寄/系统）", ""],
            ["对应 B60 版本日期", ""],
            ["是否与 B60 正文一致", "是 / 否（否须说明）"],
            ["后续重大更新是否补充报送", "是 / 否 / 不适用"],
        ],
    )
    stats["archive_table"] = True
    doc.save(str(path))
    return stats


# ---------- B60-3 ----------
def patch_b60_3(path: Path) -> dict:
    doc = Document(str(path))
    stats = {}
    # Soften title / add domain type
    title = find_para(doc, "评估专家工作计划")
    if title and "通用结构" not in title.text:
        # keep title, add subtitle after
        insert_para_after(
            title,
            "【说明】本模板以资产评估专家为主；税务/法律/精算等专家可复用本结构，将「评估」替换为对应领域，并在下表注明专家类型。",
            blue=True,
        )
        stats["note"] = True

    if not has_text(doc, "专家类型（领域）"):
        # add after 项目名称 table if exists
        if doc.tables:
            # insert para+table after first table
            first = doc.tables[0]
            p = OxmlElement("w:p")
            first._tbl.addnext(p)
            pp = Paragraph(p, first._parent)
            blue_run(pp, "专家类型（领域）")
            rows = [
                ["专家类型", "是/否", "备注"],
                ["资产评估 / 估值 / 减值", "", "本模板默认"],
                ["税务", "", "可复用本结构"],
                ["法律", "", "可复用本结构"],
                ["精算 / 其他", "", "注明具体领域"],
            ]
            # add table after pp
            tbl = doc.add_table(rows=len(rows), cols=3)
            tbl.style = "Table Grid"
            for i, row in enumerate(rows):
                for j, val in enumerate(row):
                    tbl.cell(i, j).text = val
            pp._p.addnext(tbl._tbl)
            stats["type_table"] = True

    # Update index line if present
    for p in doc.paragraphs:
        if p.text.strip().startswith("索引号：B60-3"):
            wipe_para(p, "索引号：B60-3（利用专家工作计划—评估为主，其他领域可复用）")
            stats["index"] = True
            break

    doc.save(str(path))
    return stats


# ---------- B60-1 xlsx ----------
CYCLE_TASKS = [
    "一、实质性任务（按循环/SCOT+，可增删）",
    "收入（D循环）",
    "成本费用（E等）",
    "存货",
    "货币资金",
    "往来款项（应收/应付）",
    "固定资产/在建工程",
    "无形资产/商誉",
    "金融工具/投资",
    "职工薪酬",
    "税项（所得税/增值税等）",
    "债务/权益",
    "小计（实质性）",
    "",
    "二、控制测试与IT",
    "企业层面控制测试",
    "业务层面控制测试",
    "IT一般控制测试",
    "IT应用控制/信息处理控制",
    "穿行测试",
    "小计（控制/IT）",
    "",
    "三、其他任务",
    "初步业务活动",
    "风险评估程序",
    "日记账分录测试",
    "专家工作",
    "其他审计师/组成部分",
    "复核及监督",
    "报告与沟通",
    "行政及其他",
    "小计（其他）",
    "合计",
    "",
    "【勾稽】工时重大超支是否已更新 B60 第十五章：是 / 否 / N/A",
]


def patch_b60_1_xlsx(path: Path) -> dict:
    wb = openpyxl.load_workbook(path)
    stats = {"sheet": None}
    # find 按阶段 sheet
    stage = None
    for name in wb.sheetnames:
        if "按阶段" in name:
            stage = wb[name]
            stats["sheet"] = name
            break
    if stage is None:
        return {"error": "no stage sheet"}

    # Ensure header has 差异说明
    # Row 5 headers
    headers = ["任务", "预算工时", "实际工时", "工时变动", "成本预算", "实际成本", "成本变动", "差异说明/是否更新B60第十五章"]
    for col, h in enumerate(headers, 1):
        stage.cell(5, col).value = h

    # Rebuild task list from row 6
    # Clear old content rows 6-50
    for r in range(6, 55):
        for c in range(1, 9):
            stage.cell(r, c).value = None

    for i, task in enumerate(CYCLE_TASKS):
        stage.cell(6 + i, 1).value = task if task else None

    # 职级表：加差异说明列提示
    grade = None
    for name in wb.sheetnames:
        if "工时预算与控制表" in name and "按阶段" not in name and name != "底稿目录":
            grade = wb[name]
            break
    if grade is not None:
        # find last used col in header row 5
        if grade["I5"].value in (None, ""):
            grade["I5"] = "差异说明"
        if grade["A25"].value in (None, ""):
            grade["A25"] = "【勾稽】与 B60 三（三）、B60-2-2 IT 工时一致；重大差异回写第十五章"

    # GT_Custom note already set in P0
    wb.save(path)
    return stats


def main():
    src = find_src()
    report = {}
    for folder, tag in ((TPL, "tpl"), (src, "src")):
        report[tag] = {
            "A": patch_b60a(resolve(folder, "B60A", ".docx")),
            "B": patch_b60b(resolve(folder, "B60B", ".docx")),
            "C": patch_b60c(resolve(folder, "B60C", ".docx")),
            "D": patch_b60d(resolve(folder, "B60D", ".docx")),
            "3": patch_b60_3(resolve(folder, "B60-3", ".docx")),
            "xlsx": patch_b60_1_xlsx(resolve(folder, "B60-1", ".xlsx")),
        }
    out = ROOT / "docs" / "proposals" / "b60-p2-run-report.json"
    import json

    out.write_text(__import__("json").dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(__import__("json").dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
