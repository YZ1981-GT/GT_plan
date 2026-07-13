"""J1 应付职工薪酬 — 导入导出3端点.

支持的sheet类型：
- detail: 明细表J1-2（3分区×14列对齐源模板，导出3 sheet + 编制说明）
- accrual / allocation / general / non_monetary / severance: 检查表类

模板结构（detail）：
  Sheet1: (1)短期薪酬
  Sheet2: (2)离职后福利
  Sheet3: (3)辞退福利
  Sheet4: 编制说明

14列表头：序号|项目名称|未审-期初数|未审-本期增加|未审-本期减少|未审-期末数|
         期初调整-账项调整|账项调整-本期增加|账项调整-本期减少|
         审定-期初数|审定-本期增加|审定-本期减少|审定-期末数|备注

Spec: .kiro/specs/j1-employee-compensation/
"""
from __future__ import annotations
import io
import json
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
import sqlalchemy as sa
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.core.database import get_db
from app.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["j1-import-export"])

SHEET_TYPES = {"detail", "accrual", "allocation", "general", "non_monetary", "severance", "monthly", "voucher", "industry"}

# ─── J1-2 明细表 14 列定义 ────────────────────────────────────────────────────

DETAIL_COLUMNS = [
    "序号", "项目名称",
    "未审-期初数", "未审-本期增加", "未审-本期减少", "未审-期末数",
    "期初调整-账项调整",
    "账项调整-本期增加", "账项调整-本期减少",
    "审定-期初数", "审定-本期增加", "审定-本期减少", "审定-期末数",
    "备注",
]

# 3分区默认行
SECTION_ROWS = {
    "(1)短期薪酬": [
        ("一", "工资、奖金、津贴和补贴"),
        ("", "其中：1.工资"),
        ("", "2.奖金"),
        ("", "3.津贴"),
        ("", "4.补贴"),
        ("", "5.其他"),
        ("二", "职工福利费"),
        ("三", "社会保险费"),
        ("", "1.基本医疗保险费"),
        ("", "2.补充医疗保险费"),
        ("", "3.工伤保险费"),
        ("", "4.生育保险费"),
        ("四", "住房公积金"),
        ("五", "工会经费"),
        ("六", "职工教育经费"),
        ("七", "短期带薪缺勤"),
        ("八", "短期利润分享计划"),
        ("九", "非货币性福利"),
        ("十", "其他短期薪酬"),
        ("", "其中：以现金结算的股份支付"),
    ],
    "(2)离职后福利": [
        ("一", "离职后福利"),
        ("", "其中：1.基本养老保险"),
        ("", "2.失业保险费"),
        ("", "3.企业年金缴费"),
        ("", "4.其他"),
        ("二", "其他长期职工福利"),
        ("", "其中：1."),
        ("", "2.其他"),
    ],
    "(3)辞退福利": [
        ("1", ""),
    ],
}

# 检查表类列定义（保留兼容）
CHECK_COLUMNS = {
    "accrual": ["项目", "计提基数-名称", "计提基数-金额", "计提基数-索引", "计提比例", "应提金额", "实际计提数", "差异", "差异原因", "结论"],
    "allocation": ["项目名称", "生产成本", "制造费用", "管理费用", "销售费用", "其他", "本期合计", "本期实际计提数", "本期差异", "差异原因", "结论"],
    "general": ["区块", "项目", "日期", "凭证编号", "业务内容", "对方科目", "明细科目", "金额", "附件", "结论"],
    "non_monetary": ["日期", "凭证种类", "凭证编号", "业务内容", "明细科目", "对方科目", "借方", "贷方", "附件", "非货币性福利形式", "实物来源", "结论"],
    "severance": ["日期", "凭证种类", "凭证编号", "业务内容", "明细科目", "对方明细科目", "借方", "贷方", "附件", "结论"],
}

# ─── J1-8 检查表（凭证级测试）列定义（对齐源模板：记账凭证+外部单据+核对） ──────────
# 贷方检查（计提/增加）— occurrenceRows；外部单据=职工薪酬计算表
VOUCHER_CREDIT_COLUMNS = [
    "序号", "薪酬项目", "日期", "凭证编号", "业务内容", "对方科目", "明细科目", "贷方金额",
    "人数", "审批人",
    "计算表-月份", "计算表-金额", "计算表-是否恰当审批",
    "核对1原始凭证齐全", "核对2记账相符", "核对3科目正确", "核对4计算准确", "核对5截止正确",
    "索引号", "是否异常", "备注",
]
# 借方检查（发放/减少）/ 期后支付 — postCollectionRows / postPeriodRows；外部单据=付款审批单+银行回单
VOUCHER_DEBIT_COLUMNS = [
    "序号", "薪酬项目", "日期", "凭证编号", "业务内容", "对方科目", "明细科目", "借方金额",
    "人数", "审批人",
    "审批单-日期编号", "审批单-是否恰当审批",
    "银行回单-日期", "银行回单-摘要说明", "银行回单-金额",
    "核对1付款审批单齐全", "核对2银行回单", "核对3代扣代缴", "核对4薪酬发放表相符", "核对5发放金额一致",
    "索引号", "是否异常", "备注",
]
VOUCHER_SHEET_NAMES = {
    "credit": "贷方检查(计提)",
    "debit": "借方检查(发放)",
    "post": "期后支付检查",
}

# 两行合并表头分组定义（对齐源模板：第一行合并分组，第二行子列名）
# 元素：(标签, spec)。spec=list 表示分组(第1行合并跨这些子列)；spec=None 表示单列(第1/2行纵向合并)
# 列顺序必须与 VOUCHER_*_COLUMNS 及 _excel_to_voucher_row 的位置索引严格一致
VOUCHER_CREDIT_GROUPS = [
    ("序号", None),
    ("记账凭证", ["薪酬项目", "日期", "凭证编号", "业务内容", "对方科目", "明细科目", "贷方金额"]),
    ("人数", None),
    ("审批人", None),
    ("职工薪酬计算表", ["月份", "金额", "是否经过恰当审批"]),
    ("核对内容", ["①原始凭证齐全", "②记账相符", "③科目正确", "④计算准确", "⑤截止正确"]),
    ("索引号", None),
    ("是否异常", None),
    ("备注", None),
]
VOUCHER_DEBIT_GROUPS = [
    ("序号", None),
    ("记账凭证", ["薪酬项目", "日期", "凭证编号", "业务内容", "对方科目", "明细科目", "借方金额"]),
    ("人数", None),
    ("审批人", None),
    ("付款审批单", ["日期/编号", "是否经过恰当审批"]),
    ("银行回单", ["日期", "摘要/说明", "金额"]),
    ("核对内容", ["①付款审批单齐全", "②银行回单", "③代扣代缴", "④发放表相符", "⑤金额一致"]),
    ("索引号", None),
    ("是否异常", None),
    ("备注", None),
]


def _style_one(cell):
    """单个表头单元格样式."""
    cell.font = HEADER_FONT
    cell.fill = HEADER_FILL
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = THIN_BORDER


def _write_voucher_header(ws, groups) -> int:
    """写两行合并表头（第1行分组合并/单列纵向合并，第2行子列名），返回总列数."""
    col = 1
    for label, spec in groups:
        if isinstance(spec, list):
            n = len(spec)
            ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + n - 1)
            _style_one(ws.cell(row=1, column=col, value=label))
            # 合并区其余首行单元格也需描边
            for k in range(1, n):
                _style_one(ws.cell(row=1, column=col + k))
            for j, sub in enumerate(spec):
                _style_one(ws.cell(row=2, column=col + j, value=sub))
            col += n
        else:
            ws.merge_cells(start_row=1, start_column=col, end_row=2, end_column=col)
            _style_one(ws.cell(row=1, column=col, value=label))
            _style_one(ws.cell(row=2, column=col))
            col += 1
    return col - 1


def _bool_cell(v) -> bool:
    """Excel 单元格 → 布尔（是/√/true/1 视为 True）."""
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("是", "√", "true", "1", "y", "yes", "√")


def _voucher_row_to_excel(row: dict, direction: str) -> list:
    """凭证行 dict → Excel 行值（按方向选列结构）."""
    ev = row.get("evidence") or {}
    calc = ev.get("calc") or {}
    approval = ev.get("approval") or {}
    bank = ev.get("bank") or {}
    checks = row.get("checks") or [False] * 5
    checks = (list(checks) + [False] * 5)[:5]
    chk = ["是" if c else "" for c in checks]
    base = [
        row.get("debtorName", ""), row.get("date", ""), row.get("voucherNo", ""),
        row.get("businessContent", ""), row.get("offsetAccount", ""), row.get("offsetSubAccount", ""),
    ]
    tail = [row.get("indexNo", ""), "是" if row.get("abnormal") else "", row.get("remark", "")]
    if direction == "credit":
        return [
            *base,
            _to_num(row.get("creditAmount")), row.get("staffCount", ""), row.get("approver", ""),
            calc.get("month", ""), calc.get("amount", ""), calc.get("approved", ""),
            *chk, *tail,
        ]
    return [
        *base,
        _to_num(row.get("debitAmount")), row.get("staffCount", ""), row.get("approver", ""),
        approval.get("dateNo", ""), approval.get("approved", ""),
        bank.get("date", ""), bank.get("summary", ""), bank.get("amount", ""),
        *chk, *tail,
    ]


def _excel_to_voucher_row(vals: list, direction: str, seq: int) -> dict:
    """Excel 行值 → 凭证行 dict（跳过序号列）."""
    # vals 已跳过序号列（从第2列开始）
    g = lambda i: vals[i] if i < len(vals) and vals[i] is not None else ""  # noqa: E731
    checks_start = 12 if direction == "credit" else 14
    checks = [_bool_cell(g(checks_start + k)) for k in range(5)]
    idx_off = checks_start + 5
    row = {
        "id": f"j1vc-imp-{direction}-{seq}",
        "debtorName": str(g(0)), "date": str(g(1)), "voucherNo": str(g(2)),
        "businessContent": str(g(3)), "offsetAccount": str(g(4)), "offsetSubAccount": str(g(5)),
        "creditAmount": 0, "debitAmount": 0,
        "staffCount": g(7), "approver": str(g(8)),
        "supportingDoc": "", "checks": checks,
        "indexNo": str(g(idx_off)), "abnormal": _bool_cell(g(idx_off + 1)), "remark": str(g(idx_off + 2)),
    }
    if direction == "credit":
        row["creditAmount"] = _to_num(g(6))
        row["evidence"] = {
            "calc": {"month": str(g(9)), "amount": _to_num(g(10)), "approved": str(g(11))},
            "approval": {"dateNo": "", "approved": ""},
            "bank": {"date": "", "summary": "", "amount": 0},
        }
    else:
        row["debitAmount"] = _to_num(g(6))
        row["evidence"] = {
            "calc": {"month": "", "amount": 0, "approved": ""},
            "approval": {"dateNo": str(g(9)), "approved": str(g(10))},
            "bank": {"date": str(g(11)), "summary": str(g(12)), "amount": _to_num(g(13))},
        }
    return row


def _build_voucher_template_wb(vc_data: dict | None = None, post_rows: list | None = None) -> Workbook:
    """构建 J1-8 检查表工作簿（贷方检查/借方检查/期后支付 + 编制说明）."""
    wb = Workbook()
    wb.remove(wb.active)

    sections = [
        ("credit", VOUCHER_CREDIT_GROUPS, (vc_data or {}).get("occurrenceRows") or []),
        ("debit", VOUCHER_DEBIT_GROUPS, (vc_data or {}).get("postCollectionRows") or []),
        ("post", VOUCHER_DEBIT_GROUPS, post_rows or []),
    ]
    for direction, groups, rows in sections:
        ws = wb.create_sheet(title=VOUCHER_SHEET_NAMES[direction])
        col_count = _write_voucher_header(ws, groups)  # 两行表头
        for i, r in enumerate(rows, start=1):
            ws.append([i, *_voucher_row_to_excel(r, direction)])  # 数据自第3行起
        for col_idx in range(1, col_count + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 14

    # 编制说明
    ws_note = wb.create_sheet(title="编制说明")
    ws_note["A1"] = "J1-8 应付职工薪酬检查表 — 编制说明"
    ws_note["A1"].font = Font(name="微软雅黑", size=14, bold=True)
    notes = [
        "",
        "一、表格结构（3个数据sheet + 本说明）",
        "  Sheet「贷方检查(计提)」：本期计提/增加凭证，外部单据=职工薪酬计算表(月份/金额/是否恰当审批)",
        "  Sheet「借方检查(发放)」：本期发放/减少凭证，外部单据=付款审批单(日期编号/是否恰当审批)+银行回单(日期/摘要/金额)",
        "  Sheet「期后支付检查」：资产负债表日后支付凭证，用于验证完整性（是否漏提），列结构同借方检查",
        "",
        "二、核对内容（5项，填「是」表示已核对通过，留空表示未通过/不适用）",
        "  贷方：①原始凭证齐全 ②记账凭证与原始凭证相符 ③会计科目正确 ④金额计算准确 ⑤截止期间正确",
        "  借方/期后：①付款审批单齐全 ②银行回单/转账凭证 ③代扣代缴凭证 ④与薪酬发放表相符 ⑤发放金额与审批一致",
        "",
        "三、导入说明",
        "  1. 按 sheet 名匹配三区（贷方检查/借方检查/期后支付），序号列自动生成可留空",
        "  2. 「是否异常」「是否恰当审批」等列填「是」或留空",
        "  3. 金额列为数字；空行（薪酬项目为空）自动跳过",
        "  4. 导入不覆盖「样本选取标准」与「审计说明/结论」，仅替换三区凭证明细",
        "  5. 科目 2211 应付职工薪酬（贷方/负债类），期末=期初+贷方-借方",
    ]
    for i, line in enumerate(notes, start=2):
        ws_note.cell(row=i, column=1, value=line)
    ws_note.column_dimensions["A"].width = 90
    return wb

# ─── 样式 ─────────────────────────────────────────────────────────────────────

HEADER_FONT = Font(name="微软雅黑", size=11, bold=True)
HEADER_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
CALC_FILL = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)


def _style_header(ws, row_num: int, col_count: int):
    """给表头行添加样式."""
    for col in range(1, col_count + 1):
        cell = ws.cell(row=row_num, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER


def _build_detail_template_wb(data_sections: dict | None = None) -> Workbook:
    """构建 J1-2 明细表工作簿（3分区sheet + 编制说明）."""
    wb = Workbook()
    # 删除默认sheet
    wb.remove(wb.active)

    section_keys = ["(1)短期薪酬", "(2)离职后福利", "(3)辞退福利"]
    storage_keys = ["shortTerm", "postEmployment", "severance"]

    for idx, (sec_name, stor_key) in enumerate(zip(section_keys, storage_keys)):
        ws = wb.create_sheet(title=sec_name)
        # 写表头
        ws.append(DETAIL_COLUMNS)
        _style_header(ws, 1, len(DETAIL_COLUMNS))

        # 写默认行骨架或实际数据
        rows_data = None
        if data_sections and stor_key in data_sections:
            rows_data = data_sections[stor_key]

        if rows_data:
            for item in rows_data:
                ws.append([
                    item.get("seq", ""),
                    item.get("label", ""),
                    item.get("unadjBegin", ""),
                    item.get("unadjIncrease", ""),
                    item.get("unadjDecrease", ""),
                    "",  # 期末=公式
                    item.get("openingAdj", ""),
                    item.get("ajeIncrease", ""),
                    item.get("ajeDecrease", ""),
                    "",  # 审定期初=公式
                    "",  # 审定增加=公式
                    "",  # 审定减少=公式
                    "",  # 审定期末=公式
                    item.get("remark", ""),
                ])
        else:
            # 空模板：填入默认行名
            for seq, label in SECTION_ROWS[sec_name]:
                ws.append([seq, label] + [""] * 12)

        # 列宽设置
        ws.column_dimensions["A"].width = 6
        ws.column_dimensions["B"].width = 24
        for col_letter in "CDEFGHIJKLMN":
            ws.column_dimensions[col_letter].width = 13

        # 灰底标记公式列(F/J/K/L/M = 6/10/11/12/13)
        for row_num in range(2, ws.max_row + 1):
            for col in [6, 10, 11, 12, 13]:
                cell = ws.cell(row=row_num, column=col)
                cell.fill = CALC_FILL

    # 编制说明 sheet
    ws_note = wb.create_sheet(title="编制说明")
    ws_note["A1"] = "J1-2 应付职工薪酬明细表 — 编制说明"
    ws_note["A1"].font = Font(name="微软雅黑", size=14, bold=True)
    notes = [
        "",
        "一、表格结构",
        "本明细表分3个分区（对应3个sheet）：",
        "  (1) 短期薪酬 — 工资/社保/公积金/福利等",
        "  (2) 离职后福利中设定提存计划、其他长期福利中符合设定提存条件的负债",
        "  (3) 一年内支付的辞退福利",
        "",
        "二、列说明（14列）",
        "  A-序号：分类编号（一/二/三...或1/2/3）",
        "  B-项目名称：薪酬项目名称",
        "  C~F-未审数：期初数 / 本期增加 / 本期减少 / 期末数(公式)",
        "  G-期初调整：账项调整额",
        "  H~I-账项调整：本期增加 / 本期减少",
        "  J~M-审定数：期初数(公式) / 本期增加(公式) / 本期减少(公式) / 期末数(公式)",
        "  N-备注",
        "",
        "三、公式规则（灰底列为自动计算，导入时可留空）",
        "  未审期末(F) = 期初(C) + 增加(D) - 减少(E)",
        "  审定期初(J) = 未审期初(C) + 期初调整(G)",
        "  审定增加(K) = 未审增加(D) + 账项增加(H)",
        "  审定减少(L) = 未审减少(E) + 账项减少(I)",
        "  审定期末(M) = 审定期初(J) + 审定增加(K) - 审定减少(L)",
        "",
        "四、导入规则",
        "  1. 导入时仅读取非公式列(A/B/C/D/E/G/H/I/N)的数据",
        "  2. 灰底公式列(F/J/K/L/M)可留空，系统自动计算",
        "  3. 每个sheet独立对应一个分区，按sheet名匹配",
        "  4. 辞退福利分区可自由增减行数",
        "",
        "五、科目方向",
        "  2211 应付职工薪酬为负债类贷方科目",
        "  期末 = 期初 + 贷方发生(增加) - 借方发生(减少)",
    ]
    for i, line in enumerate(notes, start=2):
        ws_note.cell(row=i, column=1, value=line)
    ws_note.column_dimensions["A"].width = 80

    return wb


# ─── J1-4 月度分析表模板 ──────────────────────────────────────────────────────

MONTHLY_COLUMNS = ["部门"] + [f"{m}月" for m in range(1, 13)] + ["合计"]

MONTHLY_DEFAULT_DEPTS = ["A部门", "B部门", "C部门"]

MONTHLY_BLOCKS = [
    ("本期计提工资", True),
    ("本期员工数量", True),
    ("本期人均工资", False),      # 公式=计提/数量
    ("上期计提工资", True),
    ("上期员工数量", True),
    ("上期人均工资", False),      # 公式
    ("人均工资变动率", False),    # 公式
]

MONTHLY_BOTTOM_ROWS = ["本期实际发放额", "本期留存", "上年同期留存"]


def _build_monthly_template_wb(data: dict | None = None) -> Workbook:
    """构建 J1-4 月度分析表工作簿（4 sheets: 本期分析/同期对比/占比与留存/编制说明）."""
    wb = Workbook()
    wb.remove(wb.active)

    # Sheet1: 本期分析（本期计提+本期员工数量，用户填入）
    ws1 = wb.create_sheet(title="本期分析")
    _write_monthly_block(ws1, "本期计提工资", data, "currentAccrual", start_row=1)
    next_row = 2 + len(MONTHLY_DEFAULT_DEPTS) + 2  # header + dept rows + total + gap
    _write_monthly_block(ws1, "本期员工数量", data, "currentHeadcount", start_row=next_row, is_integer=True)
    _set_monthly_col_widths(ws1)

    # Sheet2: 同期对比（上期计提+上期员工数量）
    ws2 = wb.create_sheet(title="同期对比")
    _write_monthly_block(ws2, "上期计提工资", data, "priorAccrual", start_row=1)
    next_row2 = 2 + len(MONTHLY_DEFAULT_DEPTS) + 2
    _write_monthly_block(ws2, "上期员工数量", data, "priorHeadcount", start_row=next_row2, is_integer=True)
    _set_monthly_col_widths(ws2)

    # Sheet3: 占比与留存（实际发放/本期留存/上年同期留存）
    ws3 = wb.create_sheet(title="占比与留存")
    ws3.append(MONTHLY_COLUMNS)
    _style_header(ws3, 1, len(MONTHLY_COLUMNS))
    bottom_data = data or {}
    for label in MONTHLY_BOTTOM_ROWS:
        field_map = {"本期实际发放额": "actualPaid", "本期留存": "currentRetained", "上年同期留存": "priorRetained"}
        field = field_map.get(label, "")
        row_data = bottom_data.get(field, [0] * 12) if data else [0] * 12
        if not isinstance(row_data, list) or len(row_data) < 12:
            row_data = [0] * 12
        ws3.append([label] + row_data[:12] + [sum(row_data[:12])])
    _set_monthly_col_widths(ws3)

    # Sheet4: 编制说明
    ws_note = wb.create_sheet(title="编制说明")
    ws_note["A1"] = "J1-4 应付职工薪酬实质性分析表 — 编制说明"
    ws_note["A1"].font = Font(name="微软雅黑", size=14, bold=True)
    notes = [
        "",
        "一、表格结构",
        "本分析表分3个sheet（本期分析/同期对比/占比与留存），对应前端3个Tab：",
        "  Sheet1「本期分析」：本期计提工资（按部门×12月）+ 本期员工数量",
        "  Sheet2「同期对比」：上期计提工资 + 上期员工数量",
        "  Sheet3「占比与留存」：本期实际发放额 / 本期留存 / 上年同期留存",
        "",
        "二、列结构（14列）",
        "  A-部门：部门/人员类型名称（如A部门、B部门，可自由命名）",
        "  B~M-1月~12月：各月金额或人数",
        "  N-合计：12个月之和（公式列，导入时可留空）",
        "",
        "三、行结构",
        "  每个区块：N个部门行（动态，可增删）+ 1个合计行（公式，导入时可留空）",
        "  导入时按部门名称匹配，新部门自动创建，空行跳过",
        "",
        "四、公式规则（系统自动计算，导入时可留空）",
        "  合计(N列) = SUM(1月~12月)",
        "  本期人均工资 = 本期计提工资 ÷ 本期员工数量（按部门×月）",
        "  上期人均工资 = 上期计提工资 ÷ 上期员工数量",
        "  人均工资变动率 = (本期人均 - 上期人均) ÷ |上期人均| × 100%",
        "  本期各月占比 = 当月计提合计 ÷ 全年合计 × 100%",
        "",
        "五、导入规则",
        "  1. 仅读取用户输入区块（本期计提/本期员工/上期计提/上期员工/底部3行）",
        "  2. 公式区块（人均/变动率/占比）不导入，系统自动计算",
        "  3. 按sheet名匹配分区：本期分析→currentAccrual+currentHeadcount",
        "  4. 「合计」行不导入（系统自动求和）",
        "  5. 部门名称为空的行跳过",
        "",
        "六、审计关注点",
        "  1. 关注各月之间波动有无异常，如果异常降低，考虑是否存在其他方",
        "     （如关联方）代付工资的情况",
        "  2. 关注实际薪酬发放日与资产负债表日的间隔时间，考虑本期留存",
        "     金额是否合理",
        "  3. 人均工资变动率>30% 系统自动红色预警，须结合业务实质判断",
        "",
        "七、科目方向",
        "  2211 应付职工薪酬为负债类贷方科目",
        "  计提=贷方增加（各月计提金额为正数）",
        "  发放=借方减少",
    ]
    for i, line in enumerate(notes, start=2):
        ws_note.cell(row=i, column=1, value=line)
    ws_note.column_dimensions["A"].width = 80

    return wb


def _write_monthly_block(ws, title: str, data: dict | None, field: str, start_row: int, is_integer: bool = False):
    """向ws写入一个指标区块（标题行+表头+部门行+合计行）."""
    # 标题行
    ws.cell(row=start_row, column=1, value=title)
    ws.cell(row=start_row, column=1).font = Font(bold=True, size=11)
    # 表头行
    header_row = start_row + 1
    for col_idx, col_name in enumerate(MONTHLY_COLUMNS, 1):
        ws.cell(row=header_row, column=col_idx, value=col_name)
    _style_header(ws, header_row, len(MONTHLY_COLUMNS))

    # 数据行
    depts = MONTHLY_DEFAULT_DEPTS
    block_data = {}
    if data and field in data and isinstance(data[field], dict):
        block_data = data[field]
        # 如果数据中有额外部门，加入
        for dept in block_data:
            if dept not in depts:
                depts = list(depts) + [dept]

    current_row = header_row + 1
    for dept in depts:
        months = block_data.get(dept, [0] * 12)
        if not isinstance(months, list) or len(months) < 12:
            months = [0] * 12
        total = sum(months[:12])
        row_values = [dept] + months[:12] + [total]
        for col_idx, val in enumerate(row_values, 1):
            ws.cell(row=current_row, column=col_idx, value=val)
        current_row += 1

    # 合计行（灰底）
    ws.cell(row=current_row, column=1, value="合计")
    ws.cell(row=current_row, column=1).font = Font(bold=True)
    for col in range(1, len(MONTHLY_COLUMNS) + 1):
        ws.cell(row=current_row, column=col).fill = CALC_FILL


def _set_monthly_col_widths(ws):
    """设置月度表列宽."""
    ws.column_dimensions["A"].width = 14
    for letter in "BCDEFGHIJKLMN":
        ws.column_dimensions[letter].width = 11


# ─── 路由 ─────────────────────────────────────────────────────────────────────

@router.get("/api/workpapers/{wp_id}/j1/export-template")
async def export_template(
    wp_id: str,
    sheet_type: str = Query(...),
    _user=Depends(get_current_user),
):
    """导出模板（空表头 + 默认行骨架 + 编制说明）."""
    if sheet_type not in SHEET_TYPES:
        raise HTTPException(400, f"不支持的sheet类型: {sheet_type}")

    if sheet_type == "detail":
        wb = _build_detail_template_wb()
    elif sheet_type == "monthly":
        wb = _build_monthly_template_wb()
    elif sheet_type == "voucher":
        wb = _build_voucher_template_wb()
    elif sheet_type == "industry":
        wb = _build_industry_wb()
    elif sheet_type == "accrual":
        wb = _build_accrual_wb()
    elif sheet_type == "allocation":
        wb = _build_allocation_wb()
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = f"J1-{sheet_type}"
        columns = CHECK_COLUMNS[sheet_type]
        ws.append(columns)
        _style_header(ws, 1, len(columns))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"J1_{sheet_type}_模板.xlsx"
    encoded = quote(filename, safe="")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.get("/api/workpapers/{wp_id}/j1/export-data")
async def export_data(
    wp_id: str,
    sheet_type: str = Query(...),
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    """导出数据（含现有数据）."""
    if sheet_type not in SHEET_TYPES:
        raise HTTPException(400, f"不支持的sheet类型: {sheet_type}")

    if sheet_type == "detail":
        # 读3分区数据
        data_sections = {}
        for stor_key in ["shortTerm", "postEmployment", "severance"]:
            item_id = f"J1-2-detail-{stor_key}"
            result = await db.execute(
                sa.text(
                    "SELECT remark FROM checklist_responses "
                    "WHERE wp_id = :wp_id AND item_id = :iid LIMIT 1"
                ),
                {"wp_id": wp_id, "iid": item_id},
            )
            row = result.fetchone()
            if row and row.remark:
                try:
                    data_sections[stor_key] = json.loads(row.remark)
                except (json.JSONDecodeError, TypeError):
                    pass

        wb = _build_detail_template_wb(data_sections if data_sections else None)
    elif sheet_type == "monthly":
        # 读月度分析数据
        result = await db.execute(
            sa.text(
                "SELECT remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id = :iid LIMIT 1"
            ),
            {"wp_id": wp_id, "iid": "J1-4-monthly-analysis"},
        )
        row = result.fetchone()
        monthly_data = None
        if row and row.remark:
            try:
                monthly_data = json.loads(row.remark)
            except (json.JSONDecodeError, TypeError):
                pass
        wb = _build_monthly_template_wb(monthly_data)
    elif sheet_type == "voucher":
        # 读 J1-8 凭证检查数据（J1-8-voucher-check + J1-8-post-period）
        vc_data, post_rows = None, None
        r1 = await db.execute(
            sa.text("SELECT remark FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :iid LIMIT 1"),
            {"wp_id": wp_id, "iid": "J1-8-voucher-check"},
        )
        row1 = r1.fetchone()
        if row1 and row1.remark:
            try:
                vc_data = json.loads(row1.remark)
            except (json.JSONDecodeError, TypeError):
                pass
        r2 = await db.execute(
            sa.text("SELECT remark FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :iid LIMIT 1"),
            {"wp_id": wp_id, "iid": "J1-8-post-period"},
        )
        row2 = r2.fetchone()
        if row2 and row2.remark:
            try:
                post_rows = json.loads(row2.remark)
            except (json.JSONDecodeError, TypeError):
                pass
        wb = _build_voucher_template_wb(vc_data, post_rows)
    elif sheet_type == "industry":
        items = await _fetch_items(db, wp_id, [
            "J1-5-company-dept", "J1-5-revenue", "J1-5-social-left", "J1-5-social-right",
            "J1-5-peer-production", "J1-5-peer-smr", "J1-5-note", "J1-5-conclusion",
        ])
        wb = _build_industry_wb(items)
    elif sheet_type == "accrual":
        items = await _fetch_items(db, wp_id, [
            "J1-6-short-term", "J1-6-post-employment", "J1-6-questions", "J1-6-conclusion",
        ])
        wb = _build_accrual_wb(items)
    elif sheet_type == "allocation":
        items = await _fetch_items(db, wp_id, [
            "J1-7-alloc-rows", "J1-7-policy", "J1-7-note", "J1-7-conclusion",
        ])
        wb = _build_allocation_wb(items)
    else:
        # 检查表类 - 走原有逻辑
        item_id = f"J1-{sheet_type}-data"
        result = await db.execute(
            sa.text(
                "SELECT remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id = :iid LIMIT 1"
            ),
            {"wp_id": wp_id, "iid": item_id},
        )
        row = result.fetchone()
        data_rows = []
        if row and row.remark:
            try:
                data_rows = json.loads(row.remark)
            except (json.JSONDecodeError, TypeError):
                pass

        wb = Workbook()
        ws = wb.active
        ws.title = f"J1-{sheet_type}"
        columns = CHECK_COLUMNS[sheet_type]
        ws.append(columns)
        _style_header(ws, 1, len(columns))
        for item in data_rows:
            ws.append([item.get(c, "") for c in columns])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"J1_{sheet_type}_数据.xlsx"
    encoded = quote(filename, safe="")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.post("/api/workpapers/{wp_id}/j1/import-data")
async def import_data(
    wp_id: str,
    file: UploadFile = File(...),
    sheet_type: str = Query("detail"),
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    """导入数据."""
    if sheet_type not in SHEET_TYPES:
        raise HTTPException(400, f"不支持的sheet类型: {sheet_type}")

    content = await file.read()
    wb = load_workbook(io.BytesIO(content), data_only=True)

    if sheet_type == "detail":
        # 导入3分区
        section_map = {
            "(1)短期薪酬": "shortTerm",
            "(2)离职后福利": "postEmployment",
            "(3)辞退福利": "severance",
        }
        total_imported = 0
        for sheet_name, stor_key in section_map.items():
            if sheet_name not in wb.sheetnames:
                continue
            ws = wb[sheet_name]
            # 读表头
            headers = [str(cell.value or "").strip() for cell in ws[1]]
            rows = []
            for row in ws.iter_rows(min_row=2, values_only=True):
                row_dict = {}
                for i, val in enumerate(row):
                    if i < len(headers):
                        row_dict[headers[i]] = val
                # 跳过完全空行
                if not any(v is not None and v != "" for v in row_dict.values()):
                    continue
                # 转换为composable字段名
                parsed = {
                    "seq": str(row_dict.get("序号", "") or ""),
                    "label": str(row_dict.get("项目名称", "") or ""),
                    "unadjBegin": _to_num(row_dict.get("未审-期初数")),
                    "unadjIncrease": _to_num(row_dict.get("未审-本期增加")),
                    "unadjDecrease": _to_num(row_dict.get("未审-本期减少")),
                    "openingAdj": _to_num(row_dict.get("期初调整-账项调整")),
                    "ajeIncrease": _to_num(row_dict.get("账项调整-本期增加")),
                    "ajeDecrease": _to_num(row_dict.get("账项调整-本期减少")),
                    "remark": str(row_dict.get("备注", "") or ""),
                }
                rows.append(parsed)
                total_imported += 1

            if rows:
                item_id = f"J1-2-detail-{stor_key}"
                serialized = json.dumps(rows, ensure_ascii=False)
                await db.execute(
                    sa.text(
                        "INSERT INTO checklist_responses (wp_id, item_id, remark) "
                        "VALUES (:wp_id, :iid, :remark) "
                        "ON CONFLICT (wp_id, item_id) DO UPDATE SET remark = :remark"
                    ),
                    {"wp_id": wp_id, "iid": item_id, "remark": serialized},
                )

        await db.commit()
        return {"imported_count": total_imported, "sheet_type": sheet_type}
    elif sheet_type == "monthly":
        # 导入月度分析
        monthly_sheet_map = {
            "本期分析": [("本期计提工资", "currentAccrual"), ("本期员工数量", "currentHeadcount")],
            "同期对比": [("上期计提工资", "priorAccrual"), ("上期员工数量", "priorHeadcount")],
            "占比与留存": [],  # bottom rows
        }
        result_data: dict = {}
        total_imported = 0

        for sheet_name, blocks in monthly_sheet_map.items():
            if sheet_name not in wb.sheetnames:
                continue
            ws = wb[sheet_name]

            if sheet_name == "占比与留存":
                # 读底部3行
                headers = [str(cell.value or "").strip() for cell in ws[1]]
                field_map = {"本期实际发放额": "actualPaid", "本期留存": "currentRetained", "上年同期留存": "priorRetained"}
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if not row or not row[0]:
                        continue
                    label = str(row[0]).strip()
                    if label in field_map:
                        months = [_to_num(row[i] if i < len(row) else 0) for i in range(1, 13)]
                        result_data[field_map[label]] = months
                        total_imported += 1
            else:
                # 读各区块
                current_block_field = None
                reading_data = False
                for row in ws.iter_rows(min_row=1, values_only=True):
                    if not row:
                        continue
                    first_cell = str(row[0] or "").strip()
                    # 检查是否是区块标题
                    matched_block = None
                    for block_title, field_name in blocks:
                        if first_cell == block_title:
                            matched_block = field_name
                            break
                    if matched_block:
                        current_block_field = matched_block
                        if current_block_field not in result_data:
                            result_data[current_block_field] = {}
                        reading_data = False
                        continue
                    # 检查是否是表头行
                    if first_cell == "部门":
                        reading_data = True
                        continue
                    # 读数据行
                    if reading_data and current_block_field and first_cell:
                        if first_cell == "合计":
                            reading_data = False
                            continue
                        months = [_to_num(row[i] if i < len(row) else 0) for i in range(1, 13)]
                        result_data[current_block_field][first_cell] = months
                        total_imported += 1

        if result_data:
            # 合并到已有数据
            existing_raw = None
            existing_result = await db.execute(
                sa.text("SELECT remark FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :iid LIMIT 1"),
                {"wp_id": wp_id, "iid": "J1-4-monthly-analysis"},
            )
            existing_row = existing_result.fetchone()
            if existing_row and existing_row.remark:
                try:
                    existing_raw = json.loads(existing_row.remark)
                except (json.JSONDecodeError, TypeError):
                    existing_raw = {}
            if not existing_raw:
                existing_raw = {}
            existing_raw.update(result_data)

            serialized = json.dumps(existing_raw, ensure_ascii=False)
            await db.execute(
                sa.text(
                    "INSERT INTO checklist_responses (wp_id, item_id, remark) "
                    "VALUES (:wp_id, :iid, :remark) "
                    "ON CONFLICT (wp_id, item_id) DO UPDATE SET remark = :remark"
                ),
                {"wp_id": wp_id, "iid": "J1-4-monthly-analysis", "remark": serialized},
            )
            # 更新部门列表
            all_depts = set()
            for field in ["currentAccrual", "currentHeadcount", "priorAccrual", "priorHeadcount"]:
                if field in existing_raw and isinstance(existing_raw[field], dict):
                    all_depts.update(existing_raw[field].keys())
            if all_depts:
                dept_serialized = json.dumps(sorted(all_depts), ensure_ascii=False)
                await db.execute(
                    sa.text(
                        "INSERT INTO checklist_responses (wp_id, item_id, remark) "
                        "VALUES (:wp_id, :iid, :remark) "
                        "ON CONFLICT (wp_id, item_id) DO UPDATE SET remark = :remark"
                    ),
                    {"wp_id": wp_id, "iid": "J1-4-departments", "remark": dept_serialized},
                )

        await db.commit()
        return {"imported_count": total_imported, "sheet_type": sheet_type}
    elif sheet_type == "voucher":
        # 导入 J1-8 凭证检查三区（贷方检查/借方检查/期后支付）
        name_to_dir = {v: k for k, v in VOUCHER_SHEET_NAMES.items()}
        parsed = {"credit": [], "debit": [], "post": []}
        for sheet_name in wb.sheetnames:
            direction = name_to_dir.get(sheet_name)
            if not direction:
                continue
            ws = wb[sheet_name]
            seq = 0
            for row in ws.iter_rows(min_row=3, values_only=True):  # 跳过两行合并表头
                if not row:
                    continue
                vals = list(row[1:])  # 跳过序号列
                # 整行全空才跳过（任一业务列有值即保留）
                if not vals or not any(v is not None and str(v).strip() != "" for v in vals):
                    continue
                seq += 1
                parsed[direction].append(_excel_to_voucher_row(vals, direction, seq))

        # 读 project_id（checklist_responses.project_id NOT NULL）
        pid_res = await db.execute(
            sa.text("SELECT project_id FROM working_paper WHERE id = :wp_id LIMIT 1"),
            {"wp_id": wp_id},
        )
        pid_row = pid_res.fetchone()
        project_id = str(pid_row.project_id) if pid_row and pid_row.project_id else None

        # 读现有 J1-8-voucher-check，保留 criteria/auditNote/conclusion，仅替换三区明细
        existing = {}
        r_exist = await db.execute(
            sa.text("SELECT remark FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :iid LIMIT 1"),
            {"wp_id": wp_id, "iid": "J1-8-voucher-check"},
        )
        row_e = r_exist.fetchone()
        if row_e and row_e.remark:
            try:
                existing = json.loads(row_e.remark) or {}
            except (json.JSONDecodeError, TypeError):
                existing = {}
        existing["occurrenceRows"] = parsed["credit"]
        existing["postCollectionRows"] = parsed["debit"]
        _upsert_sql = sa.text(
            "INSERT INTO checklist_responses (wp_id, project_id, item_id, remark) "
            "VALUES (:wp_id, :pid, :iid, :remark) "
            "ON CONFLICT (wp_id, item_id) DO UPDATE SET remark = :remark"
        )
        await db.execute(_upsert_sql, {
            "wp_id": wp_id, "pid": project_id, "iid": "J1-8-voucher-check",
            "remark": json.dumps(existing, ensure_ascii=False),
        })
        # 期后支付独立存储
        await db.execute(_upsert_sql, {
            "wp_id": wp_id, "pid": project_id, "iid": "J1-8-post-period",
            "remark": json.dumps(parsed["post"], ensure_ascii=False),
        })
        await db.commit()
        total = len(parsed["credit"]) + len(parsed["debit"]) + len(parsed["post"])
        return {"imported_count": total, "sheet_type": sheet_type}
    elif sheet_type == "industry":
        items, total = [], 0
        if "公司薪酬总览" in wb.sheetnames:
            rows = _sheet_to_rows(wb["公司薪酬总览"], J15_DEPT_COLS)
            items.append(("J1-5-company-dept", json.dumps(rows, ensure_ascii=False))); total += len(rows)
        if "社保人数核对" in wb.sheetnames:
            left, right = [], []
            for row in wb["社保人数核对"].iter_rows(min_row=2, values_only=True):
                if not row or row[1] is None or str(row[1]).strip() == "":
                    continue
                rec = {"label": str(row[1]), "count": _to_num(row[2] if len(row) > 2 else 0)}
                (right if str(row[0] or "").strip() == "社保人数" else left).append(rec)
            items.append(("J1-5-social-left", json.dumps(left, ensure_ascii=False)))
            items.append(("J1-5-social-right", json.dumps(right, ensure_ascii=False)))
            total += len(left) + len(right)
        if "同行业-生产人员" in wb.sheetnames:
            rows = _sheet_to_rows(wb["同行业-生产人员"], J15_PROD_COLS)
            items.append(("J1-5-peer-production", json.dumps(rows, ensure_ascii=False)))
            names = [r.get("company", "") for r in rows if r.get("company")]
            items.append(("J1-5-peers", json.dumps(names, ensure_ascii=False))); total += len(rows)
        if "同行业-销管研" in wb.sheetnames:
            rows = _sheet_to_rows(wb["同行业-销管研"], J15_SMR_COLS)
            items.append(("J1-5-peer-smr", json.dumps(rows, ensure_ascii=False))); total += len(rows)
        if "营业收入及说明" in wb.sheetnames:
            kv = _kv_read(wb["营业收入及说明"])
            items.append(("J1-5-revenue", str(_to_num(kv.get("营业收入")))))
            items.append(("J1-5-note", str(kv.get("审计说明") or "")))
            items.append(("J1-5-conclusion", str(kv.get("审计结论") or "")))
        await _upsert_items(db, wp_id, items)
        return {"imported_count": total, "sheet_type": sheet_type}
    elif sheet_type == "accrual":
        items, total = [], 0
        if "短期薪酬" in wb.sheetnames:
            rows = _sheet_to_rows(wb["短期薪酬"], J16_ACCRUAL_COLS)
            items.append(("J1-6-short-term", json.dumps(rows, ensure_ascii=False))); total += len(rows)
        if "离职后福利" in wb.sheetnames:
            rows = _sheet_to_rows(wb["离职后福利"], J16_ACCRUAL_COLS)
            items.append(("J1-6-post-employment", json.dumps(rows, ensure_ascii=False))); total += len(rows)
        if "审计说明与结论" in wb.sheetnames:
            kv = _kv_read(wb["审计说明与结论"])
            q_labels = ["公司对社会保险费的缴费方法", "国家关于计缴比例、计缴基数的规定",
                        "相关部门为公司确定的计缴基数的依据", "公司未给员工计缴社会保险的情况", "其他需要说明的事项"]
            answers = [str(kv.get(lbl) or "") for lbl in q_labels]
            items.append(("J1-6-questions", json.dumps(answers, ensure_ascii=False)))
            items.append(("J1-6-conclusion", str(kv.get("审计结论") or "")))
        await _upsert_items(db, wp_id, items)
        return {"imported_count": total, "sheet_type": sheet_type}
    elif sheet_type == "allocation":
        items, total = [], 0
        if "分配情况" in wb.sheetnames:
            rows = _sheet_to_rows(wb["分配情况"], J17_ALLOC_COLS)
            items.append(("J1-7-alloc-rows", json.dumps(rows, ensure_ascii=False))); total += len(rows)
        if "政策与说明" in wb.sheetnames:
            kv = _kv_read(wb["政策与说明"])
            p_labels = ["工资总额的组成部分", "公司是否执行工效挂钩", "福利政策", "职工薪酬核算、计提分配及支付政策及流程"]
            answers = [str(kv.get(lbl) or "") for lbl in p_labels]
            items.append(("J1-7-policy", json.dumps(answers, ensure_ascii=False)))
            items.append(("J1-7-note", str(kv.get("审计说明") or "")))
            items.append(("J1-7-conclusion", str(kv.get("审计结论") or "")))
        await _upsert_items(db, wp_id, items)
        return {"imported_count": total, "sheet_type": sheet_type}
    else:
        # 检查表类 — 原有逻辑
        ws = wb.active
        headers = [str(cell.value or "").strip() for cell in ws[1]]
        imported_rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            row_dict = {}
            for i, val in enumerate(row):
                if i < len(headers):
                    row_dict[headers[i]] = val
            if any(v is not None and v != "" for v in row_dict.values()):
                imported_rows.append(row_dict)

        item_id = f"J1-{sheet_type}-data"
        await db.execute(
            sa.text(
                "INSERT INTO checklist_responses (wp_id, item_id, remark) "
                "VALUES (:wp_id, :iid, :remark) "
                "ON CONFLICT (wp_id, item_id) DO UPDATE SET remark = :remark"
            ),
            {"wp_id": wp_id, "iid": item_id, "remark": json.dumps(imported_rows, ensure_ascii=False)},
        )
        await db.commit()
        return {"imported_count": len(imported_rows), "sheet_type": sheet_type}


def _to_num(val) -> float:
    """安全数值转换."""
    if val is None or val == "":
        return 0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0


# ══════════════════════════════════════════════════════════════════════════════
# J1-5 / J1-6 / J1-7 多区块导入导出（数据驱动行 helper）
# 列定义元素：(json_field, 列头, is_num)
# 特殊 field：rate_pct=rate×100 显示；isSection=bool→是/空
# ══════════════════════════════════════════════════════════════════════════════

# J1-5 与同行业对比分析表
J15_DEPT_COLS = [
    ("dept", "部门/岗位", False), ("curHeadcount", "本期人数", True), ("curTotal", "本期总额", True),
    ("priorHeadcount", "上期人数", True), ("priorTotal", "上期总额", True),
    ("industryAvg", "行业人均", True), ("analysis", "异常分析说明", False),
]
J15_PROD_COLS = [
    ("company", "公司", False), ("headcount", "人数", True), ("laborCost", "人工成本", True),
    ("mainLaborCost", "主营成本中人工成本", True), ("revenue", "营业收入", True),
    ("totalCost", "成本总额", True), ("mainCost", "主营业务成本", True),
]
J15_SMR_COLS = [
    ("company", "公司", False),
    ("salesCount", "销售人数", True), ("salesCost", "销售成本", True),
    ("mgmtCount", "管理人数", True), ("mgmtCost", "管理成本", True),
    ("rdCount", "研发人数", True), ("rdCost", "研发成本", True),
]
# J1-6 计提情况检查表
J16_ACCRUAL_COLS = [
    ("label", "项目", False), ("indent", "层级", True),
    ("baseName", "计提基数-名称", False), ("baseAmount", "计提基数-金额", True), ("baseIndex", "计提基数-索引", False),
    ("rate_pct", "计提比例(%)", True), ("actual", "实际计提数", True),
    ("diffReason", "差异原因", False), ("conclusion", "结论", False),
]
# J1-7 分配情况检查表
J17_ALLOC_COLS = [
    ("label", "项目名称", False), ("indent", "层级", True), ("isSection", "是否分区标题", False),
    ("productionCost", "生产成本", True), ("manufacturing", "制造费用", True), ("adminExpense", "管理费用", True),
    ("sellingExpense", "销售费用", True), ("otherExpense", "其他", True),
    ("actualAccrual", "本期实际计提数", True), ("diffReason", "差异原因", False), ("conclusion", "结论", False),
]


def _rows_to_sheet(ws, cols, rows):
    """通用：行对象列表 → sheet（首行表头 + 数据行）."""
    ws.append([c[1] for c in cols])
    _style_header(ws, 1, len(cols))
    for r in (rows or []):
        line = []
        for field, _label, is_num in cols:
            if field == "rate_pct":
                line.append(_to_num(r.get("rate")) * 100)
            elif field == "isSection":
                line.append("是" if r.get("isSection") else "")
            elif is_num:
                line.append(_to_num(r.get(field)))
            else:
                line.append(r.get(field, ""))
        ws.append(line)
    for i in range(1, len(cols) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 15


def _sheet_to_rows(ws, cols):
    """通用：sheet → 行对象列表（按列位置解析，跳过表头行）."""
    out = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not any(v is not None and str(v).strip() != "" for v in row):
            continue
        d = {"id": f"imp-{len(out)}"}
        for i, (field, _label, is_num) in enumerate(cols):
            val = row[i] if i < len(row) else None
            if field == "rate_pct":
                d["rate"] = _to_num(val) / 100
            elif field == "isSection":
                d["isSection"] = str(val).strip() == "是" if val is not None else False
            elif is_num:
                d[field] = _to_num(val)
            else:
                d[field] = str(val) if val is not None else ""
        out.append(d)
    return out


def _kv_sheet(ws, pairs):
    """写 key-value 说明 sheet（键|值 两列）."""
    ws.append(["项目", "内容"])
    _style_header(ws, 1, 2)
    for k, v in pairs:
        ws.append([k, v])
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 70


def _kv_read(ws):
    """读 key-value sheet → dict."""
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[0] is None:
            continue
        out[str(row[0]).strip()] = row[1] if len(row) > 1 and row[1] is not None else ""
    return out


def _note_sheet(ws, title, lines):
    """编制说明 sheet."""
    ws["A1"] = title
    ws["A1"].font = Font(name="微软雅黑", size=14, bold=True)
    for i, line in enumerate(lines, start=2):
        ws.cell(row=i, column=1, value=line)
    ws.column_dimensions["A"].width = 90


async def _fetch_items(db, wp_id: str, item_ids: list) -> dict:
    """批量读取 checklist_responses.remark → {item_id: raw_str}."""
    out = {}
    for iid in item_ids:
        r = await db.execute(
            sa.text("SELECT remark FROM checklist_responses WHERE wp_id=:w AND item_id=:i LIMIT 1"),
            {"w": wp_id, "i": iid},
        )
        row = r.fetchone()
        out[iid] = row.remark if row and row.remark else None
    return out


async def _upsert_items(db, wp_id: str, items: list):
    """批量 upsert（自动补 project_id NOT NULL）."""
    pid_res = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id=:w LIMIT 1"), {"w": wp_id},
    )
    pid_row = pid_res.fetchone()
    project_id = str(pid_row.project_id) if pid_row and pid_row.project_id else None
    sql = sa.text(
        "INSERT INTO checklist_responses (wp_id, project_id, item_id, remark) "
        "VALUES (:w, :p, :i, :r) ON CONFLICT (wp_id, item_id) DO UPDATE SET remark=:r"
    )
    for iid, remark in items:
        await db.execute(sql, {"w": wp_id, "p": project_id, "i": iid, "r": remark})
    await db.commit()


def _parse_json_array(raw):
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


# ─── J1-5 与同行业对比分析表 ──────────────────────────────────────────────────

def _build_industry_wb(data: dict | None = None) -> Workbook:
    data = data or {}
    wb = Workbook()
    wb.remove(wb.active)

    _rows_to_sheet(wb.create_sheet("公司薪酬总览"), J15_DEPT_COLS, _parse_json_array(data.get("J1-5-company-dept")))

    ws_soc = wb.create_sheet("社保人数核对")
    ws_soc.append(["类别", "项目", "人数"])
    _style_header(ws_soc, 1, 3)
    for r in _parse_json_array(data.get("J1-5-social-left")):
        ws_soc.append(["工资人数", r.get("label", ""), _to_num(r.get("count"))])
    for r in _parse_json_array(data.get("J1-5-social-right")):
        ws_soc.append(["社保人数", r.get("label", ""), _to_num(r.get("count"))])
    ws_soc.column_dimensions["A"].width = 14
    ws_soc.column_dimensions["B"].width = 40
    ws_soc.column_dimensions["C"].width = 12

    _rows_to_sheet(wb.create_sheet("同行业-生产人员"), J15_PROD_COLS, _parse_json_array(data.get("J1-5-peer-production")))
    _rows_to_sheet(wb.create_sheet("同行业-销管研"), J15_SMR_COLS, _parse_json_array(data.get("J1-5-peer-smr")))

    revenue = data.get("J1-5-revenue") or "0"
    _kv_sheet(wb.create_sheet("营业收入及说明"), [
        ("营业收入", str(revenue).strip('"') if revenue else "0"),
        ("审计说明", (data.get("J1-5-note") or "")),
        ("审计结论", (data.get("J1-5-conclusion") or "")),
    ])
    _note_sheet(wb.create_sheet("编制说明"), "J1-5 与同行业对比分析表 — 编制说明", [
        "", "一、sheet结构",
        "  公司薪酬总览：按部门/岗位填本期/上期人数与总额、行业人均；人均/变动率/占收入比为系统自动计算不导入",
        "  社保人数核对：类别列填「工资人数」或「社保人数」区分左右两区",
        "  同行业-生产人员 / 同行业-销管研：各可比公司数据；人均/占比等为自动计算不导入",
        "  营业收入及说明：营业收入(数值)、审计说明、审计结论 三项 key-value",
        "", "二、导入说明",
        "  1. 按 sheet 名匹配各区块，序号/公式列不导入",
        "  2. 整行全空自动跳过；可比公司名取自各行「公司」列",
        "  3. 计提比例等百分比列按数值填写（如 8 表示 8%）",
    ])
    return wb


# ─── J1-6 计提情况检查表 ──────────────────────────────────────────────────────

def _build_accrual_wb(data: dict | None = None) -> Workbook:
    data = data or {}
    wb = Workbook()
    wb.remove(wb.active)
    _rows_to_sheet(wb.create_sheet("短期薪酬"), J16_ACCRUAL_COLS, _parse_json_array(data.get("J1-6-short-term")))
    _rows_to_sheet(wb.create_sheet("离职后福利"), J16_ACCRUAL_COLS, _parse_json_array(data.get("J1-6-post-employment")))

    questions = _parse_json_array(data.get("J1-6-questions"))
    q_labels = ["公司对社会保险费的缴费方法", "国家关于计缴比例、计缴基数的规定",
                "相关部门为公司确定的计缴基数的依据", "公司未给员工计缴社会保险的情况", "其他需要说明的事项"]
    pairs = [(lbl, questions[i] if i < len(questions) else "") for i, lbl in enumerate(q_labels)]
    pairs.append(("审计结论", data.get("J1-6-conclusion") or ""))
    _kv_sheet(wb.create_sheet("审计说明与结论"), pairs)
    _note_sheet(wb.create_sheet("编制说明"), "J1-6 计提情况检查表 — 编制说明", [
        "", "一、sheet结构",
        "  短期薪酬 / 离职后福利：计提基数(名称/金额/索引)、计提比例(%)、实际计提数；应提金额=基数×比例、差异为系统自动计算不导入",
        "  审计说明与结论：5项审计说明问答 + 审计结论 key-value",
        "", "二、导入说明",
        "  1. 「层级」列 0=一级项目 1=子项目（缩进）",
        "  2. 计提比例(%)按数值填写（如 8 表示 8%）",
        "  3. 整行全空自动跳过",
    ])
    return wb


# ─── J1-7 分配情况检查表 ──────────────────────────────────────────────────────

def _build_allocation_wb(data: dict | None = None) -> Workbook:
    data = data or {}
    wb = Workbook()
    wb.remove(wb.active)
    _rows_to_sheet(wb.create_sheet("分配情况"), J17_ALLOC_COLS, _parse_json_array(data.get("J1-7-alloc-rows")))

    policy = _parse_json_array(data.get("J1-7-policy"))
    p_labels = ["工资总额的组成部分", "公司是否执行工效挂钩", "福利政策", "职工薪酬核算、计提分配及支付政策及流程"]
    pairs = [(lbl, policy[i] if i < len(policy) else "") for i, lbl in enumerate(p_labels)]
    pairs.append(("审计说明", data.get("J1-7-note") or ""))
    pairs.append(("审计结论", data.get("J1-7-conclusion") or ""))
    _kv_sheet(wb.create_sheet("政策与说明"), pairs)
    _note_sheet(wb.create_sheet("编制说明"), "J1-7 分配情况检查表 — 编制说明", [
        "", "一、sheet结构",
        "  分配情况：各薪酬项目在 生产成本/制造费用/管理费用/销售费用/其他 的分配额 + 本期实际计提数；本期合计、差异为系统自动计算不导入",
        "  政策与说明：4项计提分配政策问答 + 审计说明 + 审计结论 key-value",
        "", "二、导入说明",
        "  1. 「是否分区标题」列填「是」表示分组标题行（如「(1)短期薪酬」），其余留空",
        "  2. 「层级」列 0/1 控制缩进",
        "  3. 分配合计应与实际计提数勾稽一致，差异≠0需填差异原因",
    ])
    return wb
