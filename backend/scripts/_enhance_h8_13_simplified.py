# -*- coding: utf-8 -*-
"""Enhance H8-13 简化处理的租赁检查表 Excel template.

问题（源模板）：
1. 索引号误写 H8-12
2. 审计目标套用使用权资产认定，与简化处理（不确认 ROU）矛盾
3. 仅有费用重算列，缺 CAS21§32 短期/低价值资格判断
4. 租赁开始日与租赁期开始日冗余；P–R 列空置未用满 18 列承诺

改进：资格判断 + 直线法费用重算双轨，修正目标/索引/提示，补公式与下拉。
"""
from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(r"D:/GT_plan")
TARGETS = [ROOT / "backend" / "wp_templates" / "H" / "H8 使用权资产.xlsx"]
base = ROOT / "基础数据"
if base.exists():
    for p in base.rglob("H8 使用权资产.xlsx"):
        if p not in TARGETS:
            TARGETS.append(p)

SHEET = "简化处理的租赁检查表H8-13"
DATA_START, DATA_END = 10, 19  # 10 行明细
TOTAL_ROW = 20

THIN = Border(
    left=Side(style="thin", color="B0B0B0"),
    right=Side(style="thin", color="B0B0B0"),
    top=Side(style="thin", color="B0B0B0"),
    bottom=Side(style="thin", color="B0B0B0"),
)
HEADER_FILL = PatternFill("solid", fgColor="DDEBF7")
FORMULA_FILL = PatternFill("solid", fgColor="E2EFDA")  # 自动计算列
TOTAL_FILL = PatternFill("solid", fgColor="FFF2CC")
WARN_FILL = PatternFill("solid", fgColor="FCE4D6")
GUIDE_FONT = Font(color="0563C1", size=9)
BOLD = Font(bold=True, size=10)
HEADER_FONT = Font(bold=True, size=9)
OBJ_FONT = Font(size=10)
TITLE_FONT = Font(bold=True, size=14, color="1F4E79")

# 统一 18 列：资格判断 + 费用重算
HEADERS = [
    ("A", "序号", 6),
    ("B", "资产类别", 12),
    ("C", "资产名称", 14),
    ("D", "合同号", 14),
    ("E", "租赁期开始日", 12),
    ("F", "租赁到期日", 12),
    ("G", "租赁期(月)", 10),
    ("H", "全新资产价值", 12),
    ("I", "简化类型", 12),
    ("J", "月租金", 11),
    ("K", "本期应计月数", 11),
    ("L", "本期应计租金", 12),
    ("M", "账面本期租金", 12),
    ("N", "差异", 11),
    ("O", "勾稽一致", 10),
    ("P", "费用科目", 12),
    ("Q", "核查结论", 14),
    ("R", "索引号", 10),
]

OBJECTIVES = [
    (
        "A6",
        "1. 确认被审计单位对短期租赁及低价值资产租赁采用简化处理符合《企业会计准则第21号——租赁》"
        "第32条：租赁期不超过12个月（不含购买选择权），或全新状态下价值较低（实务阈值≤40,000元）且未转租；"
        "不符合条件的租赁已确认使用权资产与租赁负债。",
    ),
    (
        "A7",
        "2. 确认简化处理项下租赁付款额已按直线法（或其他系统合理方法）计入相关资产成本或当期损益，"
        "本期应计租金费用完整、准确，并与相关费用科目勾稽一致；重大差异已追查并考虑调整。",
    ),
]


def _clear_row(ws, row: int, max_col: int = 18) -> None:
    for c in range(1, max_col + 1):
        cell = ws.cell(row, c)
        cell.value = None
        cell.comment = None


def _unmerge_all(ws) -> None:
    for mr in list(ws.merged_cells.ranges):
        ws.unmerge_cells(str(mr))


def enhance(ws) -> None:
    _unmerge_all(ws)

    # ── 标题区 ────────────────────────────────────────────────────────────
    ws.merge_cells("A1:R1")
    ws["A1"] = "致同会计师事务所"
    ws["A1"].font = Font(bold=True, size=16, color="1F4E79")
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells("A2:R2")
    ws["A2"] = "简化处理的租赁检查表"
    ws["A2"].font = TITLE_FONT
    ws["A2"].alignment = Alignment(horizontal="center", vertical="center")

    # 保留目录引用；修正索引号 H8-12 → H8-13
    ws["A3"] = "=底稿目录!A2"
    ws["E3"] = "=底稿目录!A4"
    ws["K3"] = "=底稿目录!A6"
    ws["N3"] = "索引号："
    ws["O3"] = "H8-13"
    ws["O3"].font = Font(bold=True, color="C00000", size=11)

    ws["A4"] = "=底稿目录!A3"
    ws["E4"] = "=底稿目录!A5"
    ws["K4"] = "=底稿目录!A7"
    ws["N4"] = "页  次："

    # ── 审计目标（与简化处理认定对齐）──────────────────────────────────────
    ws["A5"] = "一、审计目标："
    ws["A5"].font = BOLD
    for coord, text in OBJECTIVES:
        ws[coord] = text
        ws[coord].font = OBJ_FONT
        ws[coord].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[6].height = 42
    ws.row_dimensions[7].height = 36

    ws["A8"] = "二、审计过程："
    ws["A8"].font = BOLD

    # ── 表头 ──────────────────────────────────────────────────────────────
    for col_letter, title, width in HEADERS:
        cell = ws[f"{col_letter}9"]
        cell.value = title
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
        cell.border = THIN
        ws.column_dimensions[col_letter].width = width
    ws.row_dimensions[9].height = 32

    # 表头批注
    comments = {
        "D9": "租赁合同编号，便于与合同台账、费用明细勾稽。",
        "G9": "优先按起止日自动推算；也可手工填入。含续租选择权时按准则确定的租赁期填列。"
              "≤12 且无购买选择权 → 可归短期。",
        "H9": "标的资产全新状态下的价值（绝对金额，实务阈值 40,000 元），与承租人规模无关。",
        "I9": "自动判断：短期 / 低价值 / 短期+低价值 / 不符合。不符合者应确认使用权资产。",
        "K9": "本期财务报告期间应计提租金的月份数（含不足整月的按实际政策折算）。",
        "L9": "直线法：本期应计租金 = 月租金 × 本期应计月数。有免租期/递进租金时按系统合理方法调整后填月租金或月数。",
        "N9": "差异 = 本期应计租金 − 账面本期租金。重大差异须追查。",
        "O9": "是否与管理费用/制造费用/研发支出等相关科目勾稽一致。",
        "Q9": "符合简化条件 / 不符合应确认ROU / 待核实",
    }
    for coord, text in comments.items():
        ws[coord].comment = Comment(text, "H8-13", width=280, height=80)

    # 公式列着色提示
    for col in ("G", "I", "L", "N"):
        ws[f"{col}9"].fill = FORMULA_FILL

    # ── 明细行公式 ────────────────────────────────────────────────────────
    for r in range(DATA_START, DATA_END + 1):
        for c in range(1, 19):
            cell = ws.cell(r, c)
            cell.border = THIN
            if c == 1:
                cell.value = r - DATA_START + 1
                cell.alignment = Alignment(horizontal="center")
            elif c == 7:
                # 租赁期(月)：有起止日则推算，否则留空供手工填
                cell.value = (
                    f'=IF(OR(E{r}="",F{r}=""),"",'
                    f'MAX(1,(YEAR(F{r})-YEAR(E{r}))*12+MONTH(F{r})-MONTH(E{r})+1))'
                )
                cell.fill = FORMULA_FILL
                cell.number_format = "0"
            elif c == 9:
                # 简化类型
                cell.value = (
                    f'=IF(OR(G{r}="",H{r}=""),"",'
                    f'IF(AND(G{r}<=12,H{r}<=40000),"短期+低价值",'
                    f'IF(G{r}<=12,"短期租赁",'
                    f'IF(H{r}<=40000,"低价值","不符合"))))'
                )
                cell.fill = FORMULA_FILL
                cell.alignment = Alignment(horizontal="center")
            elif c == 12:
                cell.value = f'=IF(OR(J{r}="",K{r}=""),"",J{r}*K{r})'
                cell.fill = FORMULA_FILL
                cell.number_format = "#,##0.00"
            elif c == 14:
                cell.value = f'=IF(OR(L{r}="",M{r}=""),"",L{r}-M{r})'
                cell.fill = FORMULA_FILL
                cell.number_format = "#,##0.00"
            elif c in (8, 10, 11, 13):
                cell.number_format = "#,##0.00" if c != 11 else "0"

    # ── 合计行 ────────────────────────────────────────────────────────────
    for c in range(1, 19):
        cell = ws.cell(TOTAL_ROW, c)
        cell.border = THIN
        cell.fill = TOTAL_FILL
    ws.merge_cells(f"A{TOTAL_ROW}:D{TOTAL_ROW}")
    ws[f"A{TOTAL_ROW}"] = "合计"
    ws[f"A{TOTAL_ROW}"].font = BOLD
    for col, formula in (
        ("H", f"=SUM(H{DATA_START}:H{DATA_END})"),
        ("J", f"=SUM(J{DATA_START}:J{DATA_END})"),
        ("L", f"=SUM(L{DATA_START}:L{DATA_END})"),
        ("M", f"=SUM(M{DATA_START}:M{DATA_END})"),
        ("N", f"=SUM(N{DATA_START}:N{DATA_END})"),
    ):
        cell = ws[f"{col}{TOTAL_ROW}"]
        cell.value = formula
        cell.font = BOLD
        cell.number_format = "#,##0.00"

    # 不符笔数提示（合计行右侧）
    ws[f"Q{TOTAL_ROW}"] = (
        f'=COUNTIF(I{DATA_START}:I{DATA_END},"不符合")'
    )
    ws[f"R{TOTAL_ROW}"] = "笔不符合"
    ws[f"Q{TOTAL_ROW}"].fill = WARN_FILL
    ws[f"R{TOTAL_ROW}"].fill = WARN_FILL

    # ── 审计说明 / 结论（下移，给过程表留空）────────────────────────────
    # 清理旧内容区（原 21–31 及可能残留）
    for r in range(21, 45):
        _clear_row(ws, r)

    ws["A22"] = "三、审计说明："
    ws["A22"].font = BOLD
    ws["A23"] = (
        "（说明抽查范围、简化处理政策一贯性、免租期/递进租金处理、与费用科目勾稽结果，"
        "以及「不符合」笔数的后续处理——是否已转入 H8-2/H9 确认。）"
    )
    ws["A23"].font = Font(color="808080", size=9, italic=True)
    ws["A23"].alignment = Alignment(wrap_text=True)
    ws.row_dimensions[23].height = 28

    ws["A26"] = "四、审计结论："
    ws["A26"].font = BOLD
    ws["A27"] = (
        "经检查，本期简化处理的租赁□符合 / □基本符合 / □不符合 CAS21 第32条条件；"
        "租金费用计提□准确 / □存在差异已调整 / □待进一步核实。"
    )
    ws["A27"].font = Font(size=10)
    ws["A27"].alignment = Alignment(wrap_text=True)
    ws.row_dimensions[27].height = 28

    # ── 编制提示 ──────────────────────────────────────────────────────────
    ws["A29"] = "提示（编制要点）："
    ws["A29"].font = Font(bold=True, color="0563C1", size=10)
    tips = [
        "① 短期租赁：租赁期开始日确定的租赁期不超过12个月；含购买选择权的不属于短期租赁；转租中的转租人不得对原租赁选用短期简化。",
        "② 低价值资产租赁：按标的资产全新状态绝对金额判断（实务阈值人民币40,000元），与承租人规模、性质无关；预期转租的不适用。",
        "③ 简化处理会计：不确认使用权资产和租赁负债，将租赁付款额在租赁期内按直线法或其他系统合理方法计入相关资产成本或当期损益。",
        "④ 费用重算：本期应计租金＝月租金×本期应计月数；存在免租期或租金递增时，应先将合同总对价按系统合理方法分摊后再填列月租金/月数。",
        "⑤ 「简化类型＝不符合」的租赁应转入 H8-2/H9 按完整租赁模型确认；差异（N列）重大时须追查至凭证与科目余额并考虑调整。",
        "⑥ 本表索引号为 H8-13，勿与 H8-12（减少/终止检查表）混淆。",
    ]
    for i, tip in enumerate(tips):
        row = 30 + i
        ws.cell(row, 1).value = tip
        ws.cell(row, 1).font = GUIDE_FONT
        ws.cell(row, 1).alignment = Alignment(wrap_text=True)
        ws.row_dimensions[row].height = 22

    # ── 数据验证 ──────────────────────────────────────────────────────────
    # 清掉旧 DV，避免重复
    ws.data_validations.dataValidation = []

    dv_recon = DataValidation(type="list", formula1='"是,否,待核实"', allow_blank=True)
    dv_recon.error = "请选择：是 / 否 / 待核实"
    dv_recon.add(f"O{DATA_START}:O{DATA_END}")
    ws.add_data_validation(dv_recon)

    dv_concl = DataValidation(
        type="list",
        formula1='"符合简化条件,不符合应确认ROU,待核实"',
        allow_blank=True,
    )
    dv_concl.error = "请选择核查结论"
    dv_concl.add(f"Q{DATA_START}:Q{DATA_END}")
    ws.add_data_validation(dv_concl)

    dv_cat = DataValidation(
        type="list",
        formula1='"房屋建筑物,机器设备,运输工具,办公设备,其他"',
        allow_blank=True,
    )
    dv_cat.add(f"B{DATA_START}:B{DATA_END}")
    ws.add_data_validation(dv_cat)


def main() -> None:
    updated = []
    locked = []
    for path in TARGETS:
        if not path.exists():
            print(f"SKIP missing: {path}")
            continue
        try:
            wb = openpyxl.load_workbook(path)
        except PermissionError:
            locked.append(str(path))
            print(f"LOCKED (close WPS/Excel first): {path}")
            continue
        if SHEET not in wb.sheetnames:
            print(f"SKIP no sheet: {path}")
            continue
        enhance(wb[SHEET])
        try:
            wb.save(path)
        except PermissionError:
            locked.append(str(path))
            # 写入旁路文件，关闭占用后可手动覆盖
            sidecar = path.with_name(path.stem + "_H813enhanced.xlsx")
            wb.save(sidecar)
            print(f"LOCKED save → wrote sidecar: {sidecar}")
            continue
        updated.append(str(path))
        print(f"OK: {path}")
    print(f"done, {len(updated)} updated, {len(locked)} locked")


if __name__ == "__main__":
    main()
