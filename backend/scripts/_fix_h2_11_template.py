# -*- coding: utf-8 -*-
"""Fix H2-11 interest capitalization sheet in H2 Excel template."""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

import shutil
from pathlib import Path

src = Path(r"d:\GT_plan\backend\wp_templates\H") / "H2 在建工程.xlsx"
out = Path(r"d:\GT_plan\backend\wp_templates\H") / "H2 在建工程.xlsx"
tmp = Path(r"d:\GT_plan\backend\wp_templates\H") / "_H2_fixed_tmp.xlsx"

wb = openpyxl.load_workbook(src)
ws = wb[[s for s in wb.sheetnames if "H2-11" in s][0]]

thin = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
input_fill = PatternFill("solid", fgColor="FFF2CC")
formula_fill = PatternFill("solid", fgColor="E2EFDA")
warn_font = Font(color="C00000", bold=True)
label_font = Font(bold=True)


def style_input(cell):
    cell.fill = input_fill
    cell.border = thin
    cell.alignment = Alignment(horizontal="right", vertical="center")


def style_formula(cell):
    cell.fill = formula_fill
    cell.border = thin
    cell.alignment = Alignment(horizontal="right", vertical="center")


# 1) 专门借款资本化输入区（O/P）
ws["O5"] = "【专门借款资本化】"
ws["O5"].font = label_font
ws["O6"] = "专门借款利息费用"
style_input(ws["P6"])
ws["P6"].number_format = "#,##0.00"
ws["P6"].comment = Comment(
    "手工填入：专门借款当期实际发生的利息费用（资本化期间内）", "H2-11"
)

ws["O7"] = "减：闲置资金收益"
style_input(ws["P7"])
ws["P7"].number_format = "#,##0.00"
ws["P7"].comment = Comment(
    "尚未动用的专门借款存入银行利息收入或暂时性投资收益", "H2-11"
)

ws["O8"] = "专门借款资本化金额"
ws["P8"] = "=IF(OR(P6=\"\",P6=0),0,P6-N(P7))"
style_formula(ws["P8"])
ws["P8"].number_format = "#,##0.00"
ws["P8"].comment = Comment(
    "CAS17：专门借款资本化=利息费用-闲置资金收益", "H2-11"
)

# 资本化率输入
ws["K7"] = "一般借款资本化率（月）："
if ws["L7"].value is None:
    ws["L7"] = 0
style_input(ws["L7"])
ws["L7"].number_format = "0.0000%"
ws["L7"].comment = Comment(
    "填一般借款月资本化率（可由加权年利率÷12，或取自H2-10月利率测算）", "H2-11"
)

# 2) SP列澄清
ws["J8"] = "专门借款占用额"
ws["J9"] = "SP(已占用)"
ws["J9"].comment = Comment(
    "用于符合资本化条件资产的专门借款占用额。"
    "一般借款资本化基数须扣除本列已占用专门借款。",
    "H2-11",
)
ws["K9"] = "⑨＝T-1⑨+（⑥-③-⑦+⑧-SP）/2"
ws["L9"] = "⑩=⑨×一般借款月资本化率"

# 3) 年初/月度加权：扣减SP + 下限0
ws["K10"] = "=MAX(0,G10+N(I10)-N(D10)-N(J10))"
ws["L10"] = "=K10*$L$7"

for r in range(11, 23):
    prev = r - 1
    ws[f"K{r}"] = (
        f"=MAX(0,K{prev}+(G{r}-N(H{r})-N(D{r})+N(I{r})-N(J{r}))/2)"
    )
    ws[f"L{r}"] = f"=K{r}*$L$7"

# K23：取年末加权，避免对各月⑨无意义加总
ws["K23"] = "=K22"
ws["K23"].comment = Comment(
    "取12月末累计加权平均支出（不再对各月⑨简单加总）", "H2-11"
)
ws["L23"] = "=SUM(L11:L22)"

# 4) 结论区联动 + 防DIV/0
ws["K24"] = "专门借款资本化金额"
ws["L24"] = "=P8"
style_formula(ws["L24"])
ws["L24"].number_format = "#,##0.00"
ws["L24"].comment = Comment("取自右侧专门借款测算P8（利息-闲置收益）", "H2-11")

ws["I25"] = "应予资本化合计"
ws["J25"] = "=L23+L24"
style_formula(ws["J25"])
ws["J25"].number_format = "#,##0.00"

ws["K25"] = "差异(测算-账面)"
ws["K25"].font = warn_font
ws["L25"] = "=L23+L24-N(D23)"
style_formula(ws["L25"])
ws["L25"].number_format = "#,##0.00"
ws["L25"].comment = Comment(
    "差异=（一般借款资本化+专门借款资本化）-账面借款费用(D本年合计)。"
    "正数=账面少计；负数=账面多计。",
    "H2-11",
)

ws["M25"] = '=IF(ABS(L23+L24)<1E-9,"—",L25/(L23+L24))'
style_formula(ws["M25"])
ws["M25"].number_format = "0.00%"
ws["M25"].comment = Comment(
    "差异率=差异/应予资本化合计；分母为0时显示—（避免#DIV/0!）", "H2-11"
)

# 5) 测算说明纠错
ws["B27"] = "①先测算专门借款资本化＝利息费用－闲置资金收益（见右上P8）；"
ws["B28"] = "②再按工程支出/预付款扣除已占用专门借款(SP)后，计算每月加权平均超额支出；"
ws["B29"] = (
    "③超额加权支出×一般借款月资本化率＝一般借款补充资本化；"
    "合计①+③与账面借款费用(D列)比对。"
)

ws["H27"] = "审计调整（账面多计资本化时，差异L25为负）："
ws["H28"] = "Dr.财务费用－利息支出"
ws["I29"] = "Cr.在建工程－期间费用－贷款利息"
ws["H30"] = "（账面少计时方向相反：Dr在建工程 Cr财务费用）"

# 6) 提示强化
ws["A32"] = "提示（编制要点）："
ws["A33"] = "1、关注："
ws["A34"] = "（1）利息资本化的开始和停止时间是否正确（资本化期间内才可资本化）；"
ws["A35"] = (
    "（2）专门借款与一般借款划分是否有合同依据；"
    "资本化率是否取自一般借款加权平均利率；"
)
ws["A36"] = "（3）闲置资金收益是否已从专门借款资本化中扣减；相关会计处理是否正确。"
ws["A45"] = (
    "一般借款：利息费用资本化金额＝累计资产支出超过专门借款部分的资产支出加权平均数"
    "×所占用一般借款的资本化率。（本表主表测算的即为该部分）"
)
ws["A48"] = (
    "加权平均支出应包括工程支出（前期开发费、工程费用、建安工程等）及预付工程款；"
    "须扣除借款费用(③)避免重复资本化，并扣除专门借款已占用额(SP)。"
)

ws.column_dimensions["O"].width = 22
ws.column_dimensions["P"].width = 16

wb.save(tmp)
try:
    shutil.copyfile(tmp, out)
    tmp.unlink(missing_ok=True)
    print("Saved:", out)
except PermissionError:
    print("LOCKED — saved to:", tmp)
    print("请关闭 Excel/WPS 中的 H2 在建工程.xlsx 后重新运行本脚本，或手动用临时文件覆盖。")
    out = tmp
for addr in [
    "K7", "L7", "O6", "P8", "J8", "J9", "K10", "K11", "K23",
    "L23", "K24", "L24", "L25", "M25", "J25", "B27", "H30",
]:
    print(f"{addr} = {ws[addr].value!r}")
