# -*- coding: utf-8 -*-
"""B60 P0/P1 template patch: xlsx index rename + main/attachment docx revisions."""
from __future__ import annotations

import json
import re
import shutil
from copy import deepcopy
from pathlib import Path

import openpyxl
from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

ROOT = Path(r"D:/GT_plan")
TPL_DIR = ROOT / "backend" / "wp_templates" / "B"


def find_src_dir() -> Path:
    base = ROOT / "基础数据"
    for p in base.rglob("*"):
        if p.is_dir() and p.name.startswith("B60 ") and "策略" in p.name:
            return p
    raise FileNotFoundError("B60 source dir not found")


def replace_in_cell(cell, old: str, new: str) -> int:
    n = 0
    if cell.value is None:
        return 0
    if isinstance(cell.value, str) and old in cell.value:
        cell.value = cell.value.replace(old, new)
        n += 1
    return n


def patch_xlsx(path: Path) -> dict:
    wb = openpyxl.load_workbook(path)
    stats = {"sheets_renamed": [], "cells": 0}
    rename_map = {
        "B61-1工时预算与控制表": "B60-1工时预算与控制表",
        "B61-1工时预算与控制板（按阶段）": "B60-1工时预算与控制板（按阶段）",
    }
    for old, new in rename_map.items():
        if old in wb.sheetnames:
            wb[old].title = new
            stats["sheets_renamed"].append(f"{old}->{new}")
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                stats["cells"] += replace_in_cell(cell, "B61-1", "B60-1")
        # 按阶段表：增加差异说明提示行（若不存在）
        if "按阶段" in ws.title:
            # 在表头行后确保有填写提示：找任务列旁
            if ws["H5"].value in (None, ""):
                ws["H5"] = "差异说明/是否更新B60第十五章"
    # 底稿目录 GT_Custom 用途说明
    if "GT_Custom" in wb.sheetnames:
        g = wb["GT_Custom"]
        if g["A1"].value in (None, "C1"):
            g["A1"] = "说明"
            g["B1"] = "本 Sheet 为平台占位/自定义扩展区；无定制内容时可忽略，勿当作正式工时表。"
    wb.save(path)
    return stats


def iter_all_paragraphs(doc: Document):
    for p in doc.paragraphs:
        yield p
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    yield p


def set_runs_text(paragraph, text: str, *, blue_hint: bool = False):
    """Replace paragraph text preserving first run style roughly."""
    if not paragraph.runs:
        paragraph.add_run(text)
        if blue_hint:
            paragraph.runs[0].font.color.rgb = RGBColor(0x00, 0x00, 0xFF)
        return
    paragraph.runs[0].text = text
    if blue_hint:
        paragraph.runs[0].font.color.rgb = RGBColor(0x00, 0x00, 0xFF)
    for r in paragraph.runs[1:]:
        r.text = ""


def replace_text_everywhere(doc: Document, replacements: list[tuple[str, str]]) -> int:
    count = 0
    for p in iter_all_paragraphs(doc):
        full = p.text
        if not full:
            continue
        new = full
        for old, nw in replacements:
            if old in new:
                new = new.replace(old, nw)
        if new != full:
            set_runs_text(p, new)
            count += 1
    return count


def insert_paragraph_after(paragraph, text: str, *, blue: bool = False):
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    # wrap as paragraph
    from docx.text.paragraph import Paragraph

    p = Paragraph(new_p, paragraph._parent)
    run = p.add_run(text)
    if blue:
        run.font.color.rgb = RGBColor(0x00, 0x00, 0xFF)
    run.font.size = Pt(10.5)
    return p


def add_table_after(paragraph, rows: list[list[str]]):
    """Insert a simple table after paragraph by creating tbl XML sibling."""
    # Use document-level add then move — simpler: add at end then physically move
    doc = paragraph.part.document
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            table.cell(i, j).text = val
    tbl = table._tbl
    paragraph._p.addnext(tbl)
    return table


def find_paragraph_contains(doc: Document, needle: str):
    for p in doc.paragraphs:
        if needle in p.text:
            return p
    return None


def patch_main_b60(path: Path) -> dict:
    doc = Document(str(path))
    stats = {"replacements": 0, "matrix": False, "scot_cols": False, "hints": 0}

    reps = [
        ("十三、对审计计划的更新和修改", "十五、对审计计划的更新和修改"),
        ("重要性水平的确定过程详见B15。", "重要性水平结论详见B19-1；计算过程详见B15。"),
        ("重要性水平的确定过程详见B15", "重要性水平结论详见B19-1；计算过程详见B15"),
        ("详见B15。", "详见B19-1（结论）/ B15（计算）。"),
        ("详见“B60-1审计项目工时预算与控制表”。", "详见「B60-1审计项目工时预算与控制表」（索引号统一为B60-1，不再使用B61-1）。"),
        ("详见\"B60-1审计项目工时预算与控制表\"。", "详见「B60-1审计项目工时预算与控制表」（索引号统一为B60-1，不再使用B61-1）。"),
    ]
    stats["replacements"] = replace_text_everywhere(doc, reps)

    # 编制边界提示：插在「四、对整合审计」段落后
    anchor = find_paragraph_contains(doc, "对整合审计、IPO审计业务和国企审计业务")
    if anchor is None:
        anchor = find_paragraph_contains(doc, "如果项目组根据监管机构要求需要分别报送")
    if anchor and not any("附件适用性勾选矩阵" in p.text for p in doc.paragraphs):
        # find end of section 四 — look for next major title or company name
        # insert matrix after the paragraph about 分别报送
        insert_at = find_paragraph_contains(doc, "如果项目组根据监管机构要求需要分别报送")
        if insert_at is None:
            insert_at = anchor
        p1 = insert_paragraph_after(
            insert_at,
            "五、附件适用性勾选矩阵（编制正文前先勾选；质控必查）",
            blue=True,
        )
        matrix_rows = [
            ["判断项", "是/否", "须编制附件", "备注"],
            ["整合审计 / 仅内控审计", "", "B60A", ""],
            ["IPO / 申报财务报表审计", "", "B60B", ""],
            ["国有企业年度财务报表审计", "", "B60C", ""],
            ["需向证监局等报送审计计划", "", "B60D", "非集团策略底稿"],
            ["适用 IT 审计（主稿三（六）任一勾选）", "", "B60-2-1；IT团队执行再要2-2、2-3", ""],
            ["利用评估（或其他）专家", "", "B60-3", ""],
            ["集团且利用组成部分注册会计师", "", "主稿第八章 + B30-2", "勿用B60D代替"],
        ]
        add_table_after(p1, matrix_rows)
        p2 = doc.paragraphs[-1]  # may not be correct; add hints via new paras after matrix
        # Find the matrix we just added: last table
        last_tbl = doc.tables[-1]
        # insert hints after table by adding next to tbl element
        hint1 = OxmlElement("w:p")
        last_tbl._tbl.addnext(hint1)
        from docx.text.paragraph import Paragraph

        hp = Paragraph(hint1, last_tbl._parent)
        r = hp.add_run(
            "【填写规则】本底稿为总体审计策略+计划层摘要。风险与应对细节索引B50/B30及各循环程序表，禁止粘贴B50全文；"
            "若无增量信息，填「无超出B50的补充」。SCOT+/仅重大表须填写：循环代码、拟用程序底稿索引、是否拟依赖控制、风险ID/B50行号。"
        )
        r.font.color.rgb = RGBColor(0x00, 0x00, 0xFF)
        stats["matrix"] = True
        stats["hints"] += 1

    def _append_cells(row, texts: list[str]):
        for text in texts:
            tc = deepcopy(row.cells[-1]._tc)
            # wipe paragraph content, keep tcPr
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

    # SCOT+ / 仅重大表增列
    for table in doc.tables:
        if not table.rows:
            continue
        headers = [c.text.strip().replace("\n", "") for c in table.rows[0].cells]
        joined = "|".join(headers)
        if "相关交易类别" in joined and "拟采取的方案" in joined and "循环代码" not in joined:
            extras = ["循环代码", "拟用程序底稿索引", "是否拟依赖控制", "风险ID/B50行号"]
            for i, row in enumerate(table.rows):
                _append_cells(row, extras if i == 0 else [""] * len(extras))
            stats["scot_cols"] = True
        if (
            "仅金额重大" in joined
            and "拟采取的方案" in joined
            and "循环代码" not in joined
            and "相关交易类别" not in joined
        ):
            extras = ["循环代码", "拟用程序底稿索引", "整合审计是否做业务层控制测试"]
            for i, row in enumerate(table.rows):
                _append_cells(row, extras if i == 0 else [""] * len(extras))
            stats["scot_cols"] = True

    # 第六章提示
    for p in doc.paragraphs:
        if "风险因素的确定依据详见B50" in p.text and "禁止粘贴" not in p.text:
            set_runs_text(
                p,
                p.text
                + "【本章仅摘录结论与索引，禁止粘贴B50全文；详细程序与样本量见B30及科目计划。】",
            )
            # blue on whole para is ok
            for r in p.runs:
                r.font.color.rgb = RGBColor(0x00, 0x00, 0xFF)
            stats["hints"] += 1
            break

    # 附件清单补充 B60A-D
    for p in doc.paragraphs:
        if p.text.strip() == "附件" or p.text.strip().startswith("附件"):
            # look ahead — handled by replacement on attachment list paras
            pass
    # Ensure attachment section mentions A-D
    att_anchor = find_paragraph_contains(doc, "B60-3 评估专家工作计划")
    if att_anchor and not any("B60A 对内控" in p.text for p in doc.paragraphs):
        insert_paragraph_after(att_anchor, "B60A 对内控审计的特殊考虑（条件适用）", blue=True)
        # chain
        a = find_paragraph_contains(doc, "B60A 对内控审计的特殊考虑")
        if a:
            insert_paragraph_after(a, "B60B 对IPO申报财务报表审计的特殊考虑（条件适用）", blue=True)
            b = find_paragraph_contains(doc, "B60B 对IPO")
            if b:
                insert_paragraph_after(b, "B60C 对国有企业年度财务报表审计的特殊考虑（条件适用）", blue=True)
                c = find_paragraph_contains(doc, "B60C 对国有企业")
                if c:
                    insert_paragraph_after(
                        c,
                        "B60D 向监管机构报送总体审计策略和具体审计计划的函副本（条件适用；非集团策略）",
                        blue=True,
                    )
        stats["hints"] += 1

    # 第十五章触发勾选提示
    ch15 = find_paragraph_contains(doc, "十五、对审计计划的更新和修改")
    if ch15:
        nxt = insert_paragraph_after(
            ch15,
            "【触发条件勾选】集团安排重大调整 / 重要性重定 / IT或专家安排重大调整 / KAM变化 / "
            "新舞弊迹象或程序重大变化 / 进度重大调整 / 关注函举报或融资退市风险 / 无上述情形（须书面说明本期无重大修改）。"
            "修改轮次表应评估：对已执行程序充分性的影响（无需追加 / 需追加—索引 / 需重做—索引）。",
            blue=True,
        )
        stats["hints"] += 1

    doc.save(str(path))
    return stats


def patch_attachment(path: Path, kind: str) -> int:
    doc = Document(str(path))
    n = replace_text_everywhere(doc, [("B61-1", "B60-1")])
    hints = {
        "B60A": (
            "【勾稽】仅当 B60 适用性矩阵勾选整合审计/仅内控审计时编制。"
            "须覆盖：基准日与审计目标、与财报审计范围差异、重要账户与业务层控制范围、"
            "缺陷评价标准对齐、管理层自评利用、IT 对 ICFR 意见影响（可索引 B60-2 / B22A）。"
        ),
        "B60B": (
            "【勾稽】仅当矩阵勾选 IPO/申报时编制。正文以表格为主；法规依据填文号索引，"
            "延伸检查/流水核查须填对象、时点、负责人及 S32/S33/S34 底稿索引。"
        ),
        "B60C": (
            "【勾稽】仅当矩阵勾选国企年审时编制。重点领域建议按「问题—账户—总体应对—程序索引」填写；"
            "出现重大分歧/意见类型影响/范围受限/计划重大修改等须安排与监管沟通。"
        ),
        "B60D": (
            "【勾稽】本函为监管报送副本存档，不是集团审计策略。"
            "报送内容须与 B60 正文一致；存档注明致达日期、收件人、报送方式及对应 B60 版本日期。"
            "集团安排见 B60 第八章与 B30-2。"
        ),
        "B60-2-1": "【勾稽】结论须与 B60 第三章（六）IT 适用勾选一致；适用则同步 B22A-4-1。",
        "B60-2-2": "【勾稽】IT 团队执行时编制；工时与 B60-1、B60-2-3 一致。",
        "B60-2-3": "【勾稽】作为 B60 IT 安排补充；重大范围变更回写 B60 第十五章。",
        "B60-3": "【勾稽】B60 三（四）利用评估专家时编制；其他领域专家可参照本结构。",
    }
    tip = hints.get(kind)
    if tip and doc.paragraphs:
        # insert after first non-empty para if tip not present
        if not any(tip[:12] in p.text for p in doc.paragraphs):
            first = next((p for p in doc.paragraphs if p.text.strip()), doc.paragraphs[0])
            insert_paragraph_after(first, tip, blue=True)
            n += 1
    # B60C: rename header idea via hint only (table structure left; hint covers 四列表)
    if kind == "B60C":
        for table in doc.tables:
            headers = [c.text.strip() for c in table.rows[0].cells]
            if headers and "可能存在的常见问题" in headers[0] and len(headers) >= 3:
                # ensure 3rd col mentions 程序索引
                if "程序" not in table.rows[0].cells[2].text:
                    table.rows[0].cells[2].text = "拟采取的总体应对措施 / 拟执行程序索引"
                    n += 1
                break
    if kind == "B60B":
        for table in doc.tables:
            headers = [c.text.strip().replace("\n", "") for c in table.rows[0].cells]
            if any("延伸检查" in h for h in headers) and "底稿索引" not in "".join(headers):
                for i, row in enumerate(table.rows):
                    tc = deepcopy(row.cells[-1]._tc)
                    for child in list(tc):
                        if child.tag != qn("w:tcPr"):
                            tc.remove(child)
                    p = OxmlElement("w:p")
                    r = OxmlElement("w:r")
                    t = OxmlElement("w:t")
                    t.text = "底稿索引(S32/S33/S34)" if i == 0 else ""
                    r.append(t)
                    p.append(r)
                    tc.append(p)
                    row._tr.append(tc)
                n += 1
                break
    doc.save(str(path))
    return n


def patch_json_text_files():
    files = [
        ROOT / "backend/data/ledger_adapters/wp_render_schema/generated/B60.yaml",
        ROOT / "backend/data/ledger_adapters/wp_render_schema/generated/B60-1.yaml",
        ROOT / "backend/data/step_sheet_mapping.json",
        ROOT / "backend/data/cross_wp_references.json",
        ROOT / "backend/data/acnr/global_catalog.json",
        ROOT / "backend/data/acnr/sources/classification_cache.json",
    ]
    out = {}
    for f in files:
        if not f.exists():
            out[str(f)] = "missing"
            continue
        text = f.read_text(encoding="utf-8")
        new = text.replace("B61-1工时预算与控制表", "B60-1工时预算与控制表")
        new = new.replace("B61-1工时预算与控制板（按阶段）", "B60-1工时预算与控制板（按阶段）")
        new = new.replace("B61-1", "B60-1")
        if new != text:
            f.write_text(new, encoding="utf-8")
            out[f.name] = "updated"
        else:
            out[f.name] = "unchanged"
    return out


def resolve_file(folder: Path, prefix: str, suffix: str) -> Path:
    for f in folder.iterdir():
        if f.name.startswith(prefix) and f.suffix.lower() == suffix:
            return f
    raise FileNotFoundError(f"{prefix}*{suffix} in {folder}")


def main():
    src = find_src_dir()
    report = {"src": str(src), "tpl": str(TPL_DIR), "xlsx": {}, "docx": {}, "meta": {}}

    # xlsx both copies
    for folder, tag in ((TPL_DIR, "tpl"), (src, "src")):
        xlsx = resolve_file(folder, "B60-1", ".xlsx")
        report["xlsx"][tag] = {"path": str(xlsx), **patch_xlsx(xlsx)}

    # main docx both
    for folder, tag in ((TPL_DIR, "tpl"), (src, "src")):
        main_docx = resolve_file(folder, "B60 ", ".docx")
        # only files that are the main strategy (not starting B60- )
        candidates = [
            f
            for f in folder.iterdir()
            if f.suffix.lower() == ".docx" and f.name.startswith("B60 ") and not f.name.startswith("B60-")
        ]
        main_docx = candidates[0]
        report["docx"][f"main_{tag}"] = patch_main_b60(main_docx)

    # attachments both
    kinds = {
        "B60A": "B60A",
        "B60B": "B60B",
        "B60C": "B60C",
        "B60D": "B60D",
        "B60-2-1": "B60-2-1",
        "B60-2-2": "B60-2-2",
        "B60-2-3": "B60-2-3",
        "B60-3": "B60-3",
    }
    for folder, tag in ((TPL_DIR, "tpl"), (src, "src")):
        for kind, prefix in kinds.items():
            f = resolve_file(folder, prefix, ".docx")
            report["docx"][f"{kind}_{tag}"] = patch_attachment(f, kind)

    report["meta"] = patch_json_text_files()

    out = ROOT / "docs" / "proposals" / "b60-revision-run-report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
