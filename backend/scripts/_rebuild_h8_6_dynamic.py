# -*- coding: utf-8 -*-
"""Rebuild H8-6 annual/monthly sheets: lease term driven (not hardcoded 10 years).

按年：
- 用户填写/复核「租赁期(年)」E9 → L9=有效付款期数
- 表2/表3预留最多 MAX_YEARS 行，公式按 L9 自动启用/置空（改年限即动态生效）
- 年租金、初始直接费用集中录入，不再写死 10 行

按月：
- 年租金/支付月份/初始直接费用参数化
- C 列租金按「支付月份 + 租期内」公式生成，去掉写死的 50000 行
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.comments import Comment

ROOT = Path(r"D:/GT_plan")
TARGETS = [ROOT / "backend" / "wp_templates" / "H" / "H8 使用权资产.xlsx"]
base = ROOT / "基础数据"
if base.exists():
    for p in base.rglob("H8 使用权资产.xlsx"):
        if p not in TARGETS and "_H8" not in p.name:
            TARGETS.append(p)

MAX_YEARS = 30  # 与按月约 30 年容量对齐
SHEET_H85 = "租赁期的确定H8-5"
PV_START = 20
PV_END = PV_START + MAX_YEARS - 1  # 49
PV_TOTAL = PV_END + 1  # 50
SEC3_TITLE = PV_TOTAL + 2  # 52
SEC3_H1 = SEC3_TITLE + 1  # 53
SEC3_H2 = SEC3_TITLE + 2  # 54
SUB_START = SEC3_H2 + 1  # 55
SUB_END = SUB_START + MAX_YEARS - 1  # 84
SUB_TOTAL = SUB_END + 1  # 85
AUDIT_NOTE = SUB_TOTAL + 1  # 86
AUDIT_DESC = SUB_TOTAL + 2  # 87
AUDIT_CONC = SUB_TOTAL + 4  # 89
TIPS = SUB_TOTAL + 7  # 92

GUIDE_FONT = Font(color="0563C1", size=9)
TITLE_NOTE = Font(size=9, color="833C0C")
OBJ_FONT = Font(size=10)
HEADER_FONT = Font(bold=True, size=10)
OK_FILL = PatternFill("solid", fgColor="E2EFDA")
NOTE_FILL = PatternFill("solid", fgColor="FFF8E7")
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
LEFT_WRAP = Alignment(wrap_text=True, vertical="center", horizontal="left")


def _comment(ws, addr: str, text: str, w: int = 280, h: int = 70) -> None:
    try:
        ws[addr].comment = Comment(text, "H8-6", width=w, height=h)
    except Exception:
        pass


def _set(ws, addr, value, font=None, fill=None) -> None:
    ws[addr] = value
    if font:
        ws[addr].font = font
    if fill:
        ws[addr].fill = fill
    ws[addr].alignment = LEFT_WRAP


def _add_list_validation(ws, cell_ref: str, options: str, prompt: str) -> None:
    dv = DataValidation(
        type="list",
        formula1=f'"{options}"',
        allow_blank=False,
        showErrorMessage=True,
        showInputMessage=True,
        promptTitle="编制选择",
        prompt=prompt,
        errorTitle="输入无效",
        error=f"请选择：{options}",
    )
    ws.add_data_validation(dv)
    dv.add(cell_ref)


def enhance_h85_bridge(ws) -> None:
    """H8-5 增加结构化结论格，供 H8-6 引用起租日/约满日/期数。"""
    # 原模板 A21:B21 / C21:F21 为合并区，先拆开再写入
    for rng in ("A21:B21", "C21:F21", "A21:I21", "A22:I22"):
        try:
            ws.unmerge_cells(rng)
        except Exception:
            pass

    _set(
        ws,
        "A21",
        "确定的租赁期（结构化·供H8-6引用）",
        HEADER_FONT,
        NOTE_FILL,
    )
    try:
        ws.merge_cells("A21:I21")
    except Exception:
        pass

    ws["B22"] = "起租日"
    ws["B22"].font = Font(bold=True, size=9)
    if ws["C22"].value in (None, ""):
        ws["C22"] = date(2021, 1, 1)
    ws["C22"].number_format = "YYYY-MM-DD"
    ws["C22"].fill = INPUT_FILL
    _comment(ws, "C22", "租赁期开始日。H8-6按年B9、按月C15默认引用本格。")

    ws["D22"] = "约满日"
    ws["D22"].font = Font(bold=True, size=9)
    if ws["E22"].value in (None, ""):
        ws["E22"] = date(2030, 12, 31)
    ws["E22"].number_format = "YYYY-MM-DD"
    ws["E22"].fill = INPUT_FILL
    _comment(ws, "E22", "含续租可能后的届满日。H8-6按月C16默认引用本格。")

    ws["F22"] = "租赁期(月)"
    ws["F22"].font = Font(bold=True, size=9)
    ws["G22"] = "=(YEAR($E$22)-YEAR($C$22))*12+MONTH($E$22)-MONTH($C$22)+1"
    ws["G22"].fill = OK_FILL
    ws["H22"] = "租赁期(年)"
    ws["H22"].font = Font(bold=True, size=9)
    ws["I22"] = "=MAX(1,ROUND($G$22/12,0))"
    ws["I22"].fill = OK_FILL
    _comment(ws, "I22", "有效年数。H8-6按年L9默认引用。")

    _set(
        ws,
        "A21b" if False else "A21",
        ws["A21"].value,
    )
    # 在标题下用批注提示；避免占用 A23 段标题
    _comment(
        ws,
        "A21",
        "先判断租赁期，再填第22行C22/E22；H8-6将自动带入。若§2重新评估后租期变化，请同步改E22。",
    )


def _clear_range(ws, r1: int, r2: int, c1: int = 1, c2: int = 13) -> None:
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            cell = ws.cell(r, c)
            cell.value = None
            cell.comment = None


def _unmerge_overlapping(ws, min_row: int, max_row: int) -> None:
    to_remove = []
    for m in list(ws.merged_cells.ranges):
        if m.max_row >= min_row and m.min_row <= max_row:
            to_remove.append(str(m))
    for s in to_remove:
        try:
            ws.unmerge_cells(s)
        except Exception:
            pass


def _copy_style(src, dst) -> None:
    if src.has_style:
        dst.font = src.font.copy()
        dst.border = src.border.copy()
        dst.fill = src.fill.copy()
        dst.number_format = src.number_format
        dst.alignment = src.alignment.copy()


def rebuild_annual(ws) -> None:
    """Rebuild section 2/3 as term-driven dynamic blocks (max MAX_YEARS)."""
    _set(
        ws,
        "A7",
        "1. 租赁合同的基本信息（H8-5带入 + L9动态期数 + Q9付款时点）",
        HEADER_FONT,
    )

    # 从 H8-5 带入起租日
    ws["B9"] = f"='{SHEET_H85}'!C22"
    ws["B9"].number_format = "YYYY-MM-DD"
    _comment(ws, "B9", f"默认引用{SHEET_H85}!C22起租日；可覆盖。")

    # K/L/M 参数
    ws["K8"] = "年租金(不含税)"
    ws["K8"].font = HEADER_FONT
    if not isinstance(ws["K9"].value, (int, float)):
        ws["K9"] = 50000
    ws["K9"].fill = INPUT_FILL
    _comment(ws, "K9", "必填：每年租金（不含税）。")

    ws["L8"] = "有效付款期数(年)"
    ws["L8"].font = HEADER_FONT
    ws["L9"] = f"='{SHEET_H85}'!I22"
    ws["L9"].fill = INPUT_FILL
    _comment(
        ws,
        "L9",
        f"默认引用{SHEET_H85}!I22。也可覆盖为整数5/10/15；表2/表3按此动态启用（最多30年）。",
    )

    ws["M8"] = "初始直接费用"
    ws["M8"].font = HEADER_FONT
    if not isinstance(ws["M9"].value, (int, float)):
        ws["M9"] = 15000
    ws["M9"].fill = INPUT_FILL

    # 付款时点开关
    ws["Q8"] = "付款时点"
    ws["Q8"].font = HEADER_FONT
    ws["Q9"] = "期初"
    ws["Q9"].fill = INPUT_FILL
    _add_list_validation(ws, "Q9", "期初,期末", "期初付=首期进预付；期末付=各期均折现进负债")
    _comment(
        ws,
        "Q9",
        "期初：首期折现期0进预付，利息=(期初−付款)×利率。"
        "期末：折现期1..n，利息=期初×利率，再减付款。",
    )

    # Clear old section 2+
    _unmerge_overlapping(ws, 18, max(ws.max_row or 59, 120))
    _clear_range(ws, 18, max(ws.max_row or 59, 120), 1, 13)

    _set(ws, "A18", "2. 计算租赁负债余额（L9动态期数 + Q9付款时点，最多30年）", HEADER_FONT)
    headers = [
        (1, "租金支付日期"),
        (2, "剩余合同租金（不含税）"),
        (3, "租赁付款额原值"),
        (4, "租赁负债折现期(年)"),
        (5, "租赁负债折现系数"),
        (6, "租赁付款额现值"),
        (7, "租赁预付款"),
        (8, "初始直接费用"),
        (9, "使用权资产初始确认金额"),
    ]
    for c, t in headers:
        cell = ws.cell(19, c, t)
        cell.font = HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")

    _set(
        ws,
        "L19",
        "Q9=期初：第0期进预付；Q9=期末：折现期从1起、无租金预付。年租金K9，期数L9（H8-5）。",
        GUIDE_FONT,
        NOTE_FILL,
    )

    for i in range(MAX_YEARS):
        r = PV_START + i
        if i == 0:
            ws.cell(r, 1).value = f'=IF($L$9>{i},$B$9,"")'
        else:
            prev = r - 1
            ws.cell(r, 1).value = (
                f'=IF($L$9>{i},DATE(YEAR(A{prev})+1,MONTH(A{prev}),DAY(A{prev})),"")'
            )
        ws.cell(r, 1).number_format = "YYYY-MM-DD"
        ws.cell(r, 2).value = f'=IF($L$9>{i},$K$9,0)'
        ws.cell(r, 2).number_format = "#,##0.00"
        # 折现期：期初=0..n-1；期末=1..n
        ws.cell(r, 4).value = f'=IF($L$9>{i},IF($Q$9="期末",{i}+1,{i}),"")'
        # 期初且D=0 → 不进负债本金
        ws.cell(r, 3).value = (
            f'=IF(OR($L$9<={i},D{r}="",AND($Q$9<>"期末",D{r}=0)),0,B{r})'
        )
        ws.cell(r, 3).number_format = "#,##0.00"
        ws.cell(r, 5).value = f'=IF($L$9>{i},1/(1+$H$9)^D{r},"")'
        ws.cell(r, 5).number_format = "0.0000"
        ws.cell(r, 6).value = f'=IF($L$9>{i},C{r}*E{r},0)'
        ws.cell(r, 6).number_format = "#,##0.00"
        ws.cell(r, 7).value = (
            f'=IF(AND($L$9>{i},$Q$9<>"期末",D{r}=0),B{r},0)'
        )
        ws.cell(r, 7).number_format = "#,##0.00"
        ws.cell(r, 8).value = "=$M$9" if i == 0 else 0
        ws.cell(r, 8).number_format = "#,##0.00"

    tr = PV_TOTAL
    ws.cell(tr, 1).value = "合计"
    ws.cell(tr, 1).font = HEADER_FONT
    for col, letter in [(2, "B"), (3, "C"), (6, "F"), (7, "G"), (8, "H")]:
        ws.cell(tr, col).value = f"=SUM({letter}{PV_START}:{letter}{PV_END})"
        ws.cell(tr, col).number_format = "#,##0.00"
    ws.cell(tr, 9).value = f"=F{tr}+G{tr}+H{tr}"
    ws.cell(tr, 9).number_format = "#,##0.00"

    ws["B13"] = f"=I{tr}"
    ws["C14"] = f"=F{tr}"
    ws["C15"] = f"=H{tr}+G{tr}"
    ws["F13"] = f"=J{SUB_START}"
    ws["G14"] = f"=K{SUB_START}"
    ws["F15"] = "=G14-F13"

    _set(ws, f"A{SEC3_TITLE}", "3. 租赁负债及使用权资产后续计量（随L9/Q9动态）", HEADER_FONT)
    ws.cell(SEC3_H1, 1).value = "期间"
    ws.cell(SEC3_H1, 2).value = "租赁负债"
    ws.cell(SEC3_H1, 7).value = "使用权资产"
    ws.cell(SEC3_H1, 10).value = "对应递延所得税资产"
    ws.cell(SEC3_H1, 11).value = "对应递延所得税负债"
    for c in (1, 2, 7, 10, 11):
        ws.cell(SEC3_H1, c).font = HEADER_FONT
    ws.cell(SEC3_H2, 2).value = "期初余额"
    ws.cell(SEC3_H2, 3).value = "租赁付款额"
    ws.cell(SEC3_H2, 4).value = "支付月份"
    ws.cell(SEC3_H2, 5).value = "利息费用"
    ws.cell(SEC3_H2, 6).value = "期末余额"
    ws.cell(SEC3_H2, 7).value = "期初余额"
    ws.cell(SEC3_H2, 8).value = "折旧费用"
    ws.cell(SEC3_H2, 9).value = "期末余额"
    try:
        ws.merge_cells(start_row=SEC3_H1, start_column=1, end_row=SEC3_H2, end_column=1)
        ws.merge_cells(start_row=SEC3_H1, start_column=2, end_row=SEC3_H1, end_column=6)
        ws.merge_cells(start_row=SEC3_H1, start_column=7, end_row=SEC3_H1, end_column=9)
        ws.merge_cells(start_row=SEC3_H1, start_column=10, end_row=SEC3_H2, end_column=10)
        ws.merge_cells(start_row=SEC3_H1, start_column=11, end_row=SEC3_H2, end_column=11)
    except Exception:
        pass

    for j in range(MAX_YEARS):
        r = SUB_START + j
        pv_r = PV_START + j
        ws.cell(r, 1).value = f'=IF($L$9>{j},TEXT(YEAR($B$9)+{j},"0")&"年度","")'
        if j == 0:
            ws.cell(r, 2).value = f'=IF($L$9>{j},F{tr},0)'
        else:
            ws.cell(r, 2).value = f'=IF($L$9>{j},B{r-1}-C{r-1}+E{r-1},0)'
        ws.cell(r, 2).number_format = "#,##0.00"
        ws.cell(r, 3).value = f'=IF($L$9>{j},C{pv_r},0)'
        ws.cell(r, 3).number_format = "#,##0.00"
        ws.cell(r, 4).value = f'=IF($L$9>{j},MONTH($B$9),"")'
        # 利息：期末=期初×利率；期初=(期初−付款)×利率
        ws.cell(r, 5).value = (
            f'=IF($L$9>{j},IF($Q$9="期末",B{r}*$H$9,(B{r}-C{r})*$H$9),0)'
        )
        ws.cell(r, 5).number_format = "#,##0.00"
        ws.cell(r, 6).value = (
            f'=IF($L$9>{j},IF($Q$9="期末",B{r}+E{r}-C{r},B{r}-C{r}+E{r}),0)'
        )
        ws.cell(r, 6).number_format = "#,##0.00"
        if j == 0:
            ws.cell(r, 7).value = f'=IF($L$9>{j},I{tr},0)'
        else:
            ws.cell(r, 7).value = f'=IF($L$9>{j},I{r-1},0)'
        ws.cell(r, 7).number_format = "#,##0.00"
        ws.cell(r, 8).value = (
            f'=IF(AND($L$9>{j},{j}<MIN($L$9,$I$9)),$I${tr}/MIN($L$9,$I$9),0)'
        )
        ws.cell(r, 8).number_format = "#,##0.00"
        ws.cell(r, 9).value = f'=IF($L$9>{j},G{r}-H{r},0)'
        ws.cell(r, 9).number_format = "#,##0.00"
        ws.cell(r, 10).value = f'=IF($L$9>{j},F{r}*$J$9,0)'
        ws.cell(r, 11).value = f'=IF($L$9>{j},I{r}*$J$9,0)'
        ws.cell(r, 10).number_format = "#,##0.00"
        ws.cell(r, 11).number_format = "#,##0.00"

    sr = SUB_TOTAL
    ws.cell(sr, 1).value = "合计"
    ws.cell(sr, 1).font = HEADER_FONT
    ws.cell(sr, 3).value = f"=SUM(C{SUB_START}:C{SUB_END})"
    ws.cell(sr, 5).value = f"=SUM(E{SUB_START}:E{SUB_END})"
    ws.cell(sr, 8).value = f"=SUM(H{SUB_START}:H{SUB_END})"
    for c in (3, 5, 8):
        ws.cell(sr, c).number_format = "#,##0.00"

    _set(
        ws,
        f"A{AUDIT_NOTE}",
        "自检：①L9来自H8-5可覆盖；②Q9期初/期末切换后重算；③第L9年负债期末≈0；"
        f"④折旧合计≈I{tr}；⑤右侧N9:P9自动自检。",
        GUIDE_FONT,
        OK_FILL,
    )
    _set(
        ws,
        f"A{AUDIT_DESC}",
        "三、审计说明：H8-5起租/约满/期数；付款时点(Q9)；折现率；初始计量；"
        "后续利息/折旧；与H8-1、H9勾稽。",
        TITLE_NOTE,
        NOTE_FILL,
    )
    _set(
        ws,
        f"A{AUDIT_CONC}",
        "四、审计结论：□初始及后续计量准确、与账面/H9无重大差异  □除下列差异外未见异常  "
        "□存在重大未调整差异不可确认。差异说明：__________。索引：H8-1 / H8-4 / H8-5 / H9。",
        TITLE_NOTE,
        NOTE_FILL,
    )
    _set(ws, f"A{TIPS}", "提示（编制）：", GUIDE_FONT)
    _set(
        ws,
        f"A{TIPS+1}",
        "1、流程：H8-5填C22/E22 → 本表L9/B9自动带入 → 填K9/M9/G9/Q9 → 表2/表3自动生成。",
        GUIDE_FONT,
    )
    _set(
        ws,
        f"A{TIPS+2}",
        "2、Q9选「期末」时无租金预付、折现期从1起；选「期初」时首期进预付列。寿命I9与L9取短折旧。",
        GUIDE_FONT,
    )
    _set(
        ws,
        f"A{TIPS+3}",
        "3、按月表J20默认勾稽本表L9；复杂月付用按月表。变更H8-7；减值折旧H8-8。",
        GUIDE_FONT,
    )
    for addr in [f"A{AUDIT_DESC}", f"A{AUDIT_CONC}", f"A{AUDIT_NOTE}"]:
        try:
            r = int(addr[1:])
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)
        except Exception:
            pass

    if ws["H9"].value != "=G9":
        ws["H9"] = "=G9"
    _comment(ws, "I9", "摊销年限；折旧=入账/MIN(L9,I9)。")



def rebuild_monthly_payments(ws) -> None:
    """按月动态：H8-5带入 + 年数/付款时点驱动。"""
    # --- Row20 参数区 ---
    _set(ws, "A20", "年租金(不含税)*", Font(bold=True, size=9))
    if not isinstance(ws["C20"].value, (int, float)):
        ws["C20"] = 50000
    ws["C20"].fill = INPUT_FILL
    _comment(ws, "C20", "每年支付的合同租金（不含税）。")

    _set(ws, "D20", "每年支付月份*", Font(bold=True, size=9))
    if not isinstance(ws["E20"].value, (int, float)):
        ws["E20"] = 1
    ws["E20"].fill = INPUT_FILL

    _set(ws, "F20", "初始直接费用", Font(bold=True, size=9))
    if not isinstance(ws["G20"].value, (int, float)):
        ws["G20"] = 15000
    ws["G20"].fill = INPUT_FILL

    _set(ws, "I20", "租赁期(年)*", Font(bold=True, size=9))
    # J20 在 usability 中再勾稽按年L9；此处先占位
    if ws["J20"].value in (None, ""):
        ws["J20"] = 10
    ws["J20"].fill = INPUT_FILL

    _set(ws, "K20", "使用寿命(月)", Font(bold=True, size=9))
    ws["L20"] = "=$J$20*12"
    ws["L20"].fill = INPUT_FILL

    # 付款时点
    _set(ws, "N20", "付款时点", Font(bold=True, size=9))
    ws["O20"] = "期初"
    ws["O20"].fill = INPUT_FILL
    _add_list_validation(ws, "O20", "期初,期末", "期初：起租月租金进H预付；期末：首笔租金不早于起租后12个月")
    _comment(ws, "O20", "与按年表Q9一致。期初H22含年租金；期末H22仅初始直接费用。")

    # 起租/约满：默认 H8-5
    ws["C15"] = f"='{SHEET_H85}'!C22"
    ws["C15"].number_format = "YYYY-MM-DD"
    _comment(ws, "C15", f"默认引用{SHEET_H85}!C22。")
    ws["C16"] = f"='{SHEET_H85}'!E22"
    ws["C16"].number_format = "YYYY-MM-DD"
    ws["C16"].fill = OK_FILL
    _comment(ws, "C16", f"默认引用{SHEET_H85}!E22约满日；也可改回按J20推算。")

    ws["C18"] = "=(YEAR($C$16)-YEAR($C$15))*12+MONTH($C$16)-MONTH($C$15)+1"
    _comment(ws, "C18", "租赁月数随C15/C16自动变。")

    # H22：期初=租金+IDC；期末=仅IDC
    ws["H22"] = '=IF($O$20="期末",$G$20,$C$20+$G$20)'
    ws["H22"].number_format = "#,##0.00"
    _comment(ws, "H22", "期初含预付年租金；期末仅初始直接费用。")

    for r in range(22, 349):
        prev = r - 1
        # 期初：B>C15；期末：B>=EDATE(C15,12)
        ws.cell(r, 3).value = (
            f'=IF(AND(A{r}<=$C$18,MONTH(B{r})=$E$20,B{r}<=$C$16,'
            f'IF($O$20="期末",B{r}>=EDATE($C$15,12),B{r}>$C$15)),$C$20,0)'
        )
        ws.cell(r, 3).number_format = "#,##0.00"

        if r == 22:
            ws.cell(r, 6).value = '=IF($C$18<=0,0,$C$17/12*E349)'
            ws.cell(r, 7).value = '=IF($C$18<=0,0,F22+E349)'
            ws.cell(r, 9).value = 0
            ws.cell(r, 10).value = 0
            ws.cell(r, 11).value = '=$E$349+$H$349-I22'
        else:
            ws.cell(r, 6).value = (
                f'=IF(OR(B{r}>$C$16,A{r}>$C$18),0,$C$17/12*(G{prev}-C{r}))'
            )
            ws.cell(r, 7).value = (
                f'=IF(OR(B{r}>$C$16,A{r}>$C$18),0,G{prev}-C{r}+F{r})'
            )
            ws.cell(r, 9).value = (
                f'=IF(OR(B{r}>$C$16,($A{r}-1)>=MIN($C$18,$L$20),MIN($C$18,$L$20)<=1),0,'
                f'($E$349+$H$349)/MAX(MIN($C$18,$L$20)-1,1))'
            )
            ws.cell(r, 10).value = f'=IF(I{r}=0,0,J{prev}+I{r})'
            ws.cell(r, 11).value = f'=IF(OR(B{r}>$C$16,A{r}>$C$18),0,K{prev}-I{r})'

        for col in (6, 7, 9, 10, 11):
            ws.cell(r, col).number_format = "#,##0.00"
        ws.cell(r, 12).value = f'=IF(G{r}=0,0,G{r}*$C$19)'
        ws.cell(r, 13).value = f'=IF(K{r}=0,0,K{r}*$C$19)'
        ws.cell(r, 12).number_format = "#,##0.00"
        ws.cell(r, 13).number_format = "#,##0.00"

    ws["E22"] = "=(D22+C22)/(POWER((1+$C$17/12),A22-1))"

    _set(
        ws,
        "A6",
        "填表说明（按月·动态）：C15/C16默认来自H8-5；J20默认勾稽按年L9；O20选期初/期末；"
        "填C17/C20/E20/G20后明细自动生成。右侧自动自检。",
        GUIDE_FONT,
        NOTE_FILL,
    )
    _set(
        ws,
        "A350",
        "自检：①H8-5日期已带入；②O20与按年Q9一致；③末月负债≈0；④折旧合计≈入账；⑤J20≈按年L9。",
        GUIDE_FONT,
        OK_FILL,
    )
    _set(
        ws,
        "C10",
        "租期来自H8-5或J20。寿命短于租期时改L20。",
        GUIDE_FONT,
    )
    _set(
        ws,
        "C11",
        "月折旧按MIN(C18,L20)次月起折尽；O20=期末时首笔租金不早于起租后12个月。",
        GUIDE_FONT,
    )


def _add_int_validation(ws, cell_ref: str, mn: int, mx: int, prompt: str) -> None:
    dv = DataValidation(
        type="whole",
        operator="between",
        formula1=str(mn),
        formula2=str(mx),
        allow_blank=True,
        showErrorMessage=True,
        showInputMessage=True,
        promptTitle="编制输入",
        prompt=prompt,
        errorTitle="输入无效",
        error=f"请输入{mn}~{mx}的整数",
    )
    ws.add_data_validation(dv)
    dv.add(cell_ref)


def enhance_usability(ws_ann, ws_mon, ann_title: str, mon_title: str) -> None:
    """编制便利：冻结窗格、输入校验、自动自检、两表年数联动、必填提示。"""
    # ── 按年 ─────────────────────────────────────────────
    ws_ann.freeze_panes = "A20"  # 锁定表头与参数，滚动看表2
    # 必填入口条
    _set(
        ws_ann,
        "A10",
        "【编制入口·必填黄格】先填H8-5的C22起租日/E22约满日 → 本表B9/L9自动带入；"
        "再填K9年租金、M9初始直接费用、G9折现率、Q9付款时点(期初/期末)、I9摊销年限。",
        GUIDE_FONT,
        INPUT_FILL,
    )
    try:
        ws_ann.merge_cells("A10:M10")
    except Exception:
        pass

    # L9 也可直接输整数：校验 1~30（公式值同样兼容）
    _add_int_validation(ws_ann, "L9", 1, 30, "有效付款期数1~30年；也可保留=ROUND(E9)公式")
    _add_int_validation(ws_ann, "I9", 1, 50, "摊销/使用寿命年限（年）")

    # 自动自检（公式，随L9变）
    _set(
        ws_ann,
        "N8",
        "自动自检",
        Font(bold=True, size=9),
        OK_FILL,
    )
    ws_ann["N9"] = (
        '=IF(OR($L$9="",$L$9<1),"待填期数",'
        'IF(ABS(INDEX($F$55:$F$84,$L$9))<1,"✓负债期末≈0","×查负债摊销"))'
    )
    ws_ann["O9"] = (
        '=IF(OR($L$9="",$L$9<1),"待填期数",'
        'IF(ABS(INDEX($I$55:$I$84,MIN($L$9,$I$9)))<1,"✓折旧折尽","×查折旧/寿命"))'
    )
    ws_ann["P9"] = (
        '=IF(ABS($B$16-$C$16)<0.01,"✓计算区借贷平衡","×计算区不平衡")'
    )
    for col in ("N9", "O9", "P9"):
        ws_ann[col].fill = OK_FILL
        ws_ann[col].font = Font(size=9, bold=True)
    _comment(ws_ann, "N9", "随L9自动检查第L9年负债期末是否≈0")
    _comment(ws_ann, "O9", "检查折旧期满年使用权资产净值是否≈0")
    _comment(ws_ann, "P9", "检查计算区借方合计与贷方合计")

    # ── 按月 ─────────────────────────────────────────────
    ws_mon.freeze_panes = "A22"  # 锁定参数，滚动明细
    _set(
        ws_mon,
        "A5",
        "【编制入口·必填黄格】C15/C16默认H8-5；J20默认=按年L9；O20付款时点默认=按年Q9；"
        "再填C17折现率、C20年租金、E20支付月、G20初始直接费用、L20寿命月数。",
        GUIDE_FONT,
        INPUT_FILL,
    )
    try:
        ws_mon.merge_cells("A5:M5")
    except Exception:
        pass

    # 两表年数联动：按月J20默认=按年L9
    ref = f"='{ann_title}'!L9"
    if not (isinstance(ws_mon["J20"].value, str) and "L9" in str(ws_mon["J20"].value)):
        ws_mon["J20"] = ref
    ws_mon["J20"].fill = INPUT_FILL
    _comment(ws_mon, "J20", "默认链接按年表L9（其本身默认来自H8-5!I22）。可覆盖为整数。")

    # 付款时点联动按年Q9
    ws_mon["O20"] = f"='{ann_title}'!Q9"
    ws_mon["O20"].fill = INPUT_FILL
    _comment(ws_mon, "O20", "默认链接按年表Q9付款时点；可覆盖为期初/期末。")

    _add_int_validation(ws_mon, "E20", 1, 12, "每年支付月份：1~12")
    # J20 可能是公式，整型校验仍提示手工覆盖时的范围
    _add_int_validation(ws_mon, "J20", 1, 30, "租赁期年数1~30；默认已勾稽按年表L9")

    # 按月自动自检
    _set(ws_mon, "N14", "自动自检", Font(bold=True, size=9), OK_FILL)
    # 找租期末附近：用C18作为期序，余额在 G(21+C18)
    # row = 21 + C18  → 当 C18=120, row=141
    ws_mon["N15"] = (
        '=IF($C$18<=0,"待填租期",'
        'IF(ABS(INDEX($G$22:$G$348,$C$18))<1,"✓末月负债≈0","×查利息/付款"))'
    )
    ws_mon["O15"] = (
        '=IF($C$18<=0,"待填租期",'
        'IF(ABS($I$349-($E$349+$H$349))<1,"✓折旧合计≈入账","×查折旧折尽"))'
    )
    ws_mon["P15"] = (
        f'=IF(ABS($J$20-\'{ann_title}\'!L9)<0.1,"✓与按年L9一致","△与按年L9不一致")'
    )
    for col in ("N15", "O15", "P15"):
        ws_mon[col].fill = OK_FILL
        ws_mon[col].font = Font(size=9, bold=True)
    _comment(ws_mon, "N15", "检查第C18个月负债余额是否≈0")
    _comment(ws_mon, "O15", "检查折旧合计是否约等于入账价值")
    _comment(ws_mon, "P15", "检查本表J20是否与按年表L9一致")

    # 更新填表说明一句
    _set(
        ws_mon,
        "A6",
        "填表说明（按月·动态）：【核心】J20默认=按年L9；也可直接改年数。"
        "C16/C18随年数变；填C15/C17/C20/E20/G20/L20后，明细自动生成。"
        "右侧N15:P15为自动自检。月利率=年利率/12。",
        GUIDE_FONT,
        NOTE_FILL,
    )


def resolve_sheet(wb, *names: str):
    for n in names:
        if n in wb.sheetnames:
            return wb[n]
    for s in wb.sheetnames:
        if "H8-6" in s and "按年" in s and any("按年" in n for n in names):
            return wb[s]
        if "H8-6" in s and "按月" in s and any("按月" in n for n in names):
            return wb[s]
    return None


def rebuild(path: Path, save_as: Path | None = None) -> None:
    wb = openpyxl.load_workbook(path)
    # ensure renamed sheets
    for old, new in [
        ("使用权资产 租赁负责初始及后续计量（按年）H8-6", "使用权资产 租赁负债初始及后续计量（按年）H8-6"),
        ("使用权资产 租赁负责初始及后续计量（按月）H8-6", "使用权资产 租赁负债初始及后续计量（按月）H8-6"),
    ]:
        if old in wb.sheetnames and new not in wb.sheetnames:
            wb[old].title = new

    ws_a = resolve_sheet(
        wb,
        "使用权资产 租赁负债初始及后续计量（按年）H8-6",
        "使用权资产 租赁负责初始及后续计量（按年）H8-6",
    )
    ws_m = resolve_sheet(
        wb,
        "使用权资产 租赁负债初始及后续计量（按月）H8-6",
        "使用权资产 租赁负责初始及后续计量（按月）H8-6",
    )
    if ws_a is None or ws_m is None:
        raise SystemExit(f"H8-6 sheets missing: {wb.sheetnames}")

    ws_h85 = None
    for s in wb.sheetnames:
        if "H8-5" in s or s == SHEET_H85:
            ws_h85 = wb[s]
            break
    if ws_h85 is not None:
        enhance_h85_bridge(ws_h85)

    rebuild_annual(ws_a)
    rebuild_monthly_payments(ws_m)
    enhance_usability(ws_a, ws_m, ws_a.title, ws_m.title)

    out = save_as or path
    try:
        wb.save(out)
        print("saved", out)
    except PermissionError:
        alt = out.with_name(out.stem + "_H86dynamic.xlsx")
        wb.save(alt)
        print("locked, saved", alt)


def main() -> None:
    seen: set[str] = set()
    for p in TARGETS:
        if not p.exists() or p.name.startswith("~$"):
            continue
        if any(x in p.name for x in ("_H86", "_H88", "_H810", "_H813")):
            continue
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        print("rebuild", p)
        rebuild(p)


if __name__ == "__main__":
    main()
