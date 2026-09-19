"""D1 附注披露导入导出端点

POST /api/workpapers/{wp_id}/d1/disclosure/export-template?variant=listed
POST /api/workpapers/{wp_id}/d1/disclosure/export-data?variant=listed
POST /api/workpapers/{wp_id}/d1/disclosure/import-data?variant=listed

使用 openpyxl 生成/解析 xlsx。
格式校验：列名不匹配时返回 400 + 错误列名列表。
中文文件名使用 RFC5987 编码。

Spec: .kiro/specs/d1-disclosure-note/
Tasks: 10.1
Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
"""
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, Alignment, PatternFill
except ImportError:
    Workbook = None  # type: ignore
    load_workbook = None  # type: ignore

router = APIRouter(prefix="/api/workpapers", tags=["D1附注披露导入导出"])

# ─── Constants ────────────────────────────────────────────────────────────────

VALID_VARIANTS = frozenset({'listed', 'soe'})
MAX_IMPORT_ROWS = 200

# 🔴 列名必须与**界面**和**附注模板**三方一致（`d1NoteSectionMap.ts` 是列头单一真源）：
#    「种类」而非「票据种类」、「期末终止确认金额」带「期末」前缀、
#    「预期信用损失率(%)」用**半角**括号（附注模板与同步载荷都是半角）。
#    守卫：`backend/tests/test_d1_disclosure_export_columns.py` 直接读 `.ts` 源码比对。
SECTION_COLUMNS: dict[str, list[str]] = {
    'topSummary': ['票据种类', '期末账面余额', '期末坏账准备', '期末账面价值', '上年年末账面余额', '上年年末坏账准备', '上年年末账面价值'],
    'pledged': ['种类', '期末已质押金额'],
    'endorsed': ['种类', '期末终止确认金额', '期末未终止确认金额'],
    'transfer': ['种类', '期末转应收账款金额'],
    'badDebtClassEnd': ['类别', '账面余额', '坏账准备', '预期信用损失率(%)', '计提依据', '账面价值'],
    'badDebtClassPrior': ['类别', '账面余额', '坏账准备', '预期信用损失率(%)', '计提依据', '账面价值'],
    'badDebtMovementMain': ['项目', '坏账准备金额'],
    'badDebtMovementDetail': ['单位名称', '转回原因', '收回方式', '原确定坏账准备的依据', '转回或收回金额'],
    'writeOffMain': ['项目', '核销金额'],
    'writeOffDetail': ['单位名称', '应收票据性质', '核销金额', '核销原因', '履行的核销程序', '款项是否由关联交易产生'],
    'categorySummary': ['票据种类', '期末账面余额', '期末坏账准备', '期末账面价值', '期初账面余额', '期初坏账准备', '期初账面价值'],
    # 上市组合计提项目明细（源模板 R76~R89，一张表双期并列）；国企只用期末两列
    'portfolioBank': ['名称', '期末应收票据', '期末坏账准备', '上年年末应收票据', '上年年末坏账准备'],
    'portfolioCommercial': ['名称', '期末应收票据', '期末坏账准备', '上年年末应收票据', '上年年末坏账准备'],
    # 国企变动表「其中：」下的组合明细（预设 F4-20）
    'movementDetail': ['类别', '期初数', '计提', '收回或转回', '核销', '其他变动'],
    'notes': ['事项', '说明'],
}

# 变体差异列（国企措辞与列结构与上市不同，见源模板 / 附注模板 八、4）
SECTION_COLUMNS_OVERRIDE: dict[str, dict[str, list[str]]] = {
    'soe': {
        'badDebtClassEnd': ['类别', '账面余额', '坏账准备', '预期信用损失率(%)', '计提理由', '账面价值'],
        'badDebtClassPrior': ['类别', '账面余额', '坏账准备', '预期信用损失率(%)', '计提理由', '账面价值'],
        # 国企变动主表是横排 7 列（源模板 A46:G47）
        'badDebtMovementMain': ['类别', '期初数', '计提', '收回或转回', '核销', '其他变动', '期末数'],
        # 国企转回表 4 列，且「转回或收回前累计已计提坏账准备金额」是**金额列**（源模板 C59==SUM）
        'badDebtMovementDetail': ['债务人名称', '转回或收回金额', '转回或收回前累计已计提坏账准备金额', '转回或收回原因、方式'],
        'writeOffDetail': ['单位名称', '应收票据的性质', '核销金额', '核销原因', '履行的核销程序', '是否由关联交易产生'],
        # 国企组合计提表只有期末（源模板 A34:D42）
        'portfolioBank': ['名称', '期末应收票据', '期末坏账准备'],
        'portfolioCommercial': ['名称', '期末应收票据', '期末坏账准备'],
    },
}


def _cols(section: str, variant: str) -> list[str]:
    """取某变体下某区块的列名（变体覆盖优先）。"""
    return SECTION_COLUMNS_OVERRIDE.get(variant, {}).get(section) or SECTION_COLUMNS.get(section, [])


# Sections per variant
VARIANT_SECTIONS: dict[str, list[str]] = {
    'listed': [
        'topSummary', 'pledged', 'endorsed', 'transfer',
        'badDebtClassEnd', 'badDebtClassPrior',
        'portfolioBank', 'portfolioCommercial',
        'badDebtMovementMain', 'badDebtMovementDetail',
        'writeOffMain', 'writeOffDetail', 'notes',
    ],
    'soe': [
        'categorySummary', 'badDebtClassEnd', 'badDebtClassPrior',
        'portfolioBank', 'portfolioCommercial',
        'badDebtMovementMain', 'movementDetail', 'badDebtMovementDetail',
        'pledged', 'endorsed', 'transfer',
        'writeOffMain', 'writeOffDetail', 'notes',
    ],
}

SHEET_TITLES: dict[str, str] = {
    'topSummary': '（0）应收票据汇总',
    'categorySummary': '（国企）应收票据分类汇总',
    'pledged': '（1）期末已质押的应收票据',
    'endorsed': '（2）已背书或贴现且未到期',
    'transfer': '（3）转为应收账款的票据',
    'badDebtClassEnd': '（4.1）坏账计提分类（期末）',
    'badDebtClassPrior': '（4.2）坏账计提分类（上年年末）',
    'portfolioBank': '（4.3）组合计提-银行承兑汇票',
    'portfolioCommercial': '（4.3）组合计提-商业承兑汇票',
    'badDebtMovementMain': '（5）坏账准备变动（主表）',
    'movementDetail': '（5）坏账准备变动（其中明细）',
    'badDebtMovementDetail': '（5）坏账准备转回收回（其中）',
    'writeOffMain': '（6）实际核销（主表）',
    'writeOffDetail': '（6）实际核销（其中）',
    'notes': '说明事项',
}
TITLE_TO_SECTION: dict[str, str] = {v: k for k, v in SHEET_TITLES.items()}

# 多层表头：只声明**第 1 行**（分组带 / 小节标题）与合并区域；
# 第 2 行（末级表头）一律由 `_cols(section, variant)` 派生 —— 防止列名改了表头没跟着改，
# 导致 `_validate_columns` 把自家导出的模板判成「列名不匹配」。
_MULTI_HEADER_ROW1: dict[str, dict[str, Any]] = {
    "topSummary": {"row1": ["票据种类", "期末余额", "", "", "上年年末余额", "", ""], "merges": ["A1:A2", "B1:D1", "E1:G1"]},
    "categorySummary": {"row1": ["票据种类", "期末数", "", "", "期初数", "", ""], "merges": ["A1:A2", "B1:D1", "E1:G1"]},
    "badDebtClassEnd": {"row1": ["类别", "期末余额", "", "", "", ""], "merges": ["A1:A2", "B1:F1"]},
    "badDebtClassPrior": {"row1": ["类别", "上年年末余额", "", "", "", ""], "merges": ["A1:A2", "B1:F1"]},
    "badDebtMovementMain": {"row1": ["（5）本期计提、收回或转回的坏账准备情况", ""], "merges": ["A1:B1"]},
    "writeOffMain": {"row1": ["（6）本期实际核销的应收票据情况", ""], "merges": ["A1:B1"]},
    "badDebtMovementDetail": {"row1": ["其中：本期转回或收回金额重要的坏账准备如下：", "", "", "", ""], "merges": ["A1:E1"]},
    "writeOffDetail": {"row1": ["其中，重要的应收票据核销情况如下（逐项披露）：", "", "", "", "", ""], "merges": ["A1:F1"]},
    "portfolioBank": {"row1": ["组合计提项目：银行承兑汇票", "", "", "", ""], "merges": ["A1:E1"]},
    "portfolioCommercial": {"row1": ["组合计提项目：商业承兑汇票", "", "", "", ""], "merges": ["A1:E1"]},
    "movementDetail": {"row1": ["其中：按组合计提预期信用损失的应收票据明细（F4-20）", "", "", "", "", ""], "merges": ["A1:F1"]},
}

# 国企侧第 1 行差异（列数不同 → 合并区域也不同）
_MULTI_HEADER_ROW1_OVERRIDE: dict[str, dict[str, dict[str, Any]]] = {
    "soe": {
        "badDebtMovementMain": {
            "row1": ["类别", "期初数", "本期变动情况", "", "", "", "期末数"],
            "merges": ["A1:A2", "B1:B2", "C1:F1", "G1:G2"],
        },
        "badDebtMovementDetail": {
            "row1": ["其中，本期转回或收回金额重要的应收票据坏账准备：", "", "", ""],
            "merges": ["A1:D1"],
        },
        "portfolioBank": {"row1": ["按组合计提坏账准备：银行承兑汇票", "", ""], "merges": ["A1:C1"]},
        "portfolioCommercial": {"row1": ["按组合计提坏账准备：商业承兑汇票", "", ""], "merges": ["A1:C1"]},
    },
}


def _multi_header(section: str, variant: str) -> dict[str, Any] | None:
    """多层表头配置（row1 声明 + row2 派生 + 合并区域 + 数据起始行）。"""
    base = _MULTI_HEADER_ROW1_OVERRIDE.get(variant, {}).get(section) or _MULTI_HEADER_ROW1.get(section)
    if not base:
        return None
    cols = _cols(section, variant)
    row1 = list(base["row1"])
    # row1 长度对齐列数（列数被变体覆盖改变时自动补空）
    if len(row1) < len(cols):
        row1 += [""] * (len(cols) - len(row1))
    return {
        "row1": row1[: len(cols)],
        "row2": cols,
        "merges": base["merges"],
        "data_start_row": 3,
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _validate_variant(variant: str) -> None:
    if variant not in VALID_VARIANTS:
        raise HTTPException(status_code=400, detail=f"不支持的variant: {variant}。支持: listed, soe")


def _create_template_workbook(variant: str) -> "Workbook":
    """Create a multi-sheet workbook with one sheet per section."""
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore

    sections = VARIANT_SECTIONS[variant]
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    band_fill = PatternFill(start_color="EAF3FF", end_color="EAF3FF", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for section in sections:
        columns = _cols(section, variant)
        ws = wb.create_sheet(title=SHEET_TITLES.get(section, section))
        mh = _multi_header(section, variant)
        if mh:
            for col_idx, col_name in enumerate(mh["row1"], 1):
                cell = ws.cell(row=1, column=col_idx, value=col_name)
                cell.font = header_font
                cell.fill = band_fill
                cell.alignment = header_align
                ws.column_dimensions[cell.column_letter].width = max(len(str(col_name)) * 2 + 6, 14)
            for col_idx, col_name in enumerate(mh["row2"], 1):
                cell = ws.cell(row=2, column=col_idx, value=col_name)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_align
            for merge_ref in mh["merges"]:
                ws.merge_cells(merge_ref)
            ws.freeze_panes = f"A{mh['data_start_row']}"
        else:
            for col_idx, col_name in enumerate(columns, 1):
                cell = ws.cell(row=1, column=col_idx, value=col_name)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_align
                ws.column_dimensions[cell.column_letter].width = max(len(col_name) * 2 + 4, 14)
            ws.freeze_panes = "A2"
        if section == 'notes':
            default_rows = [
                ('总说明', ''),
                ('（1）已质押说明', ''),
                ('（2）背书贴现说明', ''),
                ('（4）坏账分类说明', ''),
                ('（6）核销说明', ''),
            ]
            for idx, (k, v) in enumerate(default_rows, start=2):
                ws.cell(row=idx, column=1, value=k)
                ws.cell(row=idx, column=2, value=v)
        elif section == 'badDebtMovementMain':
            # 上市是竖排 7 个项目行；国企是横排 3 个类别行（源模板 A48~A52）
            fixed_rows = (
                ['单项计提预期信用损失的应收票据', '按组合计提预期信用损失的应收票据', '合计']
                if variant == 'soe'
                else ['上年年末数', '本期计提', '本期收回或转回', '本期核销', '【本期转销】', '【其他】', '期末数']
            )
            start_row = int((_multi_header('badDebtMovementMain', variant) or {}).get('data_start_row', 2))
            for i, label in enumerate(fixed_rows, start=start_row):
                ws.cell(row=i, column=1, value=label)
                if '【' in label:
                    ws.cell(row=i, column=1).font = Font(color="C00000")
                ws.cell(row=i, column=1).fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
        elif section == 'writeOffMain':
            start_row = int((_multi_header('writeOffMain', variant) or {}).get('data_start_row', 2))
            ws.cell(row=start_row, column=1, value='实际核销的应收票据')
            ws.cell(row=start_row, column=1).fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")

    # 参照 D4：追加填写说明与注意事项
    guide_ws = wb.create_sheet("填写说明")
    guide_ws.append(["D1附注披露导入模板填写说明（请先阅读）"])
    guide_ws.append(["1）请勿修改各业务sheet表头文字；多层表头只在末级表头下方填数据。"])
    guide_ws.append(["2）支持一次导入覆盖本页全部表格，建议先导出“数据”作为增量修改模板。"])
    guide_ws.append(["3）金额列填数值，不要加千分位和单位；空值可留空。"])
    guide_ws.append(["4）坏账分类表中“其中：”行为说明行，可保留；明细行可自行增删。"])
    guide_ws.append(["5）说明事项sheet用于填写页面中的各段“说明”文本。"])
    guide_ws.append(["6）如提示列名不匹配，请使用最新模板重新填写。"])
    guide_ws.append(["7）“（4.3）组合计提-银行/商业承兑汇票”按出票人类型或账龄逐行填写；"
                     "上市版含期末与上年年末两组金额，按名称成对对齐（同名视为同一行）。"])
    if variant == 'soe':
        guide_ws.append(["8）“（5）坏账准备变动（其中明细）”填写按组合计提下的明细；"
                         "填了明细后“按组合计提预期信用损失的应收票据”行按明细汇总（校验预设 F4-20）。"])
    guide_ws.append(["9）比例、预期信用损失率等派生列由系统按金额推导，模板中不提供，请勿另加列。"])
    guide_ws.column_dimensions["A"].width = 110

    return wb


def _fill_template_with_data(wb: "Workbook", variant: str, response_map: dict[str, str]) -> None:
    prefix = f"D1-disc-{variant}-"

    def get_rows(key: str) -> list[dict[str, Any]]:
        return _safe_parse_rows(response_map.get(prefix + key))

    def get_num(key: str) -> float:
        return _num(response_map.get(prefix + key))

    sheet_rows: dict[str, list[dict[str, Any]]] = {
        'topSummary': _safe_parse_rows(response_map.get(prefix + 'top-summary-rows')),
        'categorySummary': _safe_parse_rows(response_map.get(prefix + 'top-summary-rows')),
        'pledged': [
            {'种类': r.get('category', ''), '期末已质押金额': _num(r.get('pledgedAmount'))}
            for r in get_rows('pledged-rows')
        ],
        'endorsed': [
            {'种类': r.get('category', ''), '期末终止确认金额': _num(r.get('derecognizedAmount')), '期末未终止确认金额': _num(r.get('notDerecognizedAmount'))}
            for r in get_rows('endorsed-rows')
        ],
        'transfer': [
            {'种类': r.get('category', ''), '期末转应收账款金额': _num(r.get('transferAmount'))}
            for r in get_rows('transfer-rows')
        ],
        # 国企转回表列结构与上市不同：4 列且「累计已计提坏账准备金额」是金额列
        'badDebtMovementDetail': [
            (
                {
                    '债务人名称': r.get('companyName', ''),
                    '转回或收回金额': _num(r.get('amount')),
                    '转回或收回前累计已计提坏账准备金额': _num(r.get('cumulativeProvision')),
                    '转回或收回原因、方式': r.get('reversalReason', ''),
                }
                if variant == 'soe' else
                {
                    '单位名称': r.get('companyName', ''),
                    '转回原因': r.get('reversalReason', ''),
                    '收回方式': r.get('originalMethod', ''),
                    '原确定坏账准备的依据': r.get('reversalBasis', ''),
                    '转回或收回金额': _num(r.get('amount')),
                }
            )
            for r in get_rows('reversal-rows')
        ],
        'writeOffDetail': [
            {
                '单位名称': r.get('companyName', ''),
                ('应收票据的性质' if variant == 'soe' else '应收票据性质'): r.get('noteType', ''),
                '核销金额': _num(r.get('amount')),
                '核销原因': r.get('reason', ''),
                '履行的核销程序': r.get('procedure', ''),
                ('是否由关联交易产生' if variant == 'soe' else '款项是否由关联交易产生'): r.get('relatedPartyFlag', ''),
            }
            for r in get_rows('writeoff-rows')
        ],
        # 组合计提项目明细（上市双期并列 / 国企只期末）——本轮新增录入面的导入导出覆盖
        'portfolioBank': _portfolio_sheet_rows(
            get_rows('bank-portfolio-end-rows'), get_rows('bank-portfolio-prior-rows'), variant,
        ),
        'portfolioCommercial': _portfolio_sheet_rows(
            get_rows('commercial-portfolio-end-rows'), get_rows('commercial-portfolio-prior-rows'), variant,
        ),
        # 国企变动表「其中：」明细（F4-20）
        'movementDetail': [
            {
                '类别': r.get('label', ''),
                '期初数': _num(r.get('priorBalance')),
                '计提': _num(r.get('provision')),
                '收回或转回': _num(r.get('reversal')),
                '核销': _num(r.get('writeOff')),
                '其他变动': _num(r.get('other')),
            }
            for r in get_rows('movement-detail-rows')
        ],
        'writeOffMain': [{'项目': '实际核销的应收票据', '核销金额': get_num('writeoff-amount')}],
        'notes': [
            {'事项': '总说明', '说明': response_map.get(prefix + 'note-top') or ''},
            {'事项': '（1）已质押说明', '说明': response_map.get(prefix + 'note-pledged') or ''},
            {'事项': '（2）背书贴现说明', '说明': response_map.get(prefix + 'note-endorsed') or ''},
            {'事项': '（4）坏账分类说明', '说明': response_map.get(prefix + 'note-badDebtClass') or ''},
            {'事项': '（6）核销说明', '说明': response_map.get(prefix + 'note-writeOff') or ''},
        ],
    }

    movement_rows = get_rows('movement-rows')
    mv = movement_rows[0] if movement_rows else {}
    sheet_rows['badDebtMovementMain'] = [
        {'项目': '上年年末数', '坏账准备金额': _num(mv.get('priorBalance'))},
        {'项目': '本期计提', '坏账准备金额': _num(mv.get('provision'))},
        {'项目': '本期收回或转回', '坏账准备金额': _num(mv.get('reversal'))},
        {'项目': '本期核销', '坏账准备金额': _num(mv.get('writeOff'))},
        {'项目': '【本期转销】', '坏账准备金额': _num(mv.get('transfer'))},
        {'项目': '【其他】', '坏账准备金额': _num(mv.get('other'))},
        {'项目': '期末数', '坏账准备金额': _num(mv.get('endBalance'))},
    ]

    # 上市源模板用「计提依据」，国企用「计提理由」（逐表措辞，见附注模板 五、4[6] / 八、4[3]）
    basis_col = '计提理由' if variant == 'soe' else '计提依据'

    def build_bad_debt_class(period: str) -> list[dict[str, Any]]:
        class_rows = get_rows(f'class-{period}-rows')
        individuals = get_rows(f'individual-{"end" if period=="end" else "prior"}-rows')
        by_id = {str(r.get('rowId')): r for r in class_rows}
        single = by_id.get(f'class-{period}-individual', {})
        bank = by_id.get(f'class-{period}-portfolio-bank', {})
        commercial = by_id.get(f'class-{period}-portfolio-commercial', {})
        combo_bal = _num(bank.get('balance')) + _num(commercial.get('balance'))
        combo_prov = _num(bank.get('provision')) + _num(commercial.get('provision'))
        total_bal = _num(single.get('balance')) + combo_bal
        total_prov = _num(single.get('provision')) + combo_prov
        total_book = total_bal - total_prov
        rows: list[dict[str, Any]] = [
            {'类别': '按单项计提坏账准备', '账面余额': _num(single.get('balance')), '坏账准备': _num(single.get('provision')), '预期信用损失率(%)': '', basis_col: '', '账面价值': _num(single.get('bookValue'))},
            {'类别': '其中：', '账面余额': '', '坏账准备': '', '预期信用损失率(%)': '', basis_col: '', '账面价值': ''},
        ]
        for r in individuals:
            bal = _num(r.get('balance'))
            prov = _num(r.get('provision'))
            rows.append({'类别': r.get('name', ''), '账面余额': bal, '坏账准备': prov, '预期信用损失率(%)': '', basis_col: r.get('basis', ''), '账面价值': bal - prov})
        rows.extend([
            {'类别': '按组合计提坏账准备', '账面余额': combo_bal, '坏账准备': combo_prov, '预期信用损失率(%)': '', basis_col: '', '账面价值': combo_bal - combo_prov},
            {'类别': '其中：', '账面余额': '', '坏账准备': '', '预期信用损失率(%)': '', basis_col: '', '账面价值': ''},
            {'类别': '银行承兑汇票', '账面余额': _num(bank.get('balance')), '坏账准备': _num(bank.get('provision')), '预期信用损失率(%)': '', basis_col: '', '账面价值': _num(bank.get('bookValue'))},
            {'类别': '商业承兑汇票', '账面余额': _num(commercial.get('balance')), '坏账准备': _num(commercial.get('provision')), '预期信用损失率(%)': '', basis_col: '', '账面价值': _num(commercial.get('bookValue'))},
            {'类别': '合计', '账面余额': total_bal, '坏账准备': total_prov, '预期信用损失率(%)': '', basis_col: '', '账面价值': total_book},
        ])
        return rows

    sheet_rows['badDebtClassEnd'] = build_bad_debt_class('end')
    sheet_rows['badDebtClassPrior'] = build_bad_debt_class('prior')

    for sheet_name, rows in sheet_rows.items():
        sheet_title = SHEET_TITLES.get(sheet_name, sheet_name)
        if sheet_title not in wb.sheetnames:
            continue
        ws = wb[sheet_title]
        cols = _cols(sheet_name, variant)
        mh = _multi_header(sheet_name, variant)
        start_row = int(mh["data_start_row"]) if mh else 2
        for r_idx, row_vals in enumerate(_sheet_values(rows, cols), start=start_row):
            for c_idx, cell_val in enumerate(row_vals, start=1):
                ws.cell(row=r_idx, column=c_idx, value=cell_val)


def _header_cells(ws: Any, section: str, variant: str) -> list[str]:
    """读末级表头（按列序，空串占位）。

    🔴 纵向合并的列（`A1:A2` / `B1:B2` 这类 rowspan=2 的表头）在 openpyxl 里
    **只有左上角单元格有值**，第 2 行被清空 → 直接读第 2 行会漏掉标签列，
    导致「导入自家导出的模板」必然报「缺少列」（本轮往返自检发现的既有缺陷）。
    故第 2 行为空时回退取同列第 1 行的值。
    """
    mh = _multi_header(section, variant)
    if not mh:
        return [
            (str(c.value).strip() if c.value is not None else '')
            for c in ws[1]
        ]
    row1 = list(ws[1])
    row2 = list(ws[2])
    width = max(len(row1), len(row2))
    out: list[str] = []
    for i in range(width):
        v2 = row2[i].value if i < len(row2) else None
        if v2 is not None and str(v2).strip() != '':
            out.append(str(v2).strip())
            continue
        v1 = row1[i].value if i < len(row1) else None
        out.append(str(v1).strip() if v1 is not None else '')
    return out


def _validate_columns(ws: Any, section: str, variant: str) -> list[str]:
    """Validate column names, return list of invalid column names."""
    expected_list = _cols(section, variant)
    expected = set(expected_list)
    if not expected:
        return ['未知的section类型']

    actual = [c for c in _header_cells(ws, section, variant) if c]

    invalid = [col for col in actual if col not in expected]
    missing = [col for col in expected_list if col not in actual]
    invalid.extend([f"缺少列:{m}" for m in missing])
    if len(actual) < 2:
        invalid.append('列数不足(至少需要2列)')
    return invalid


def _parse_rows(ws: Any, section: str, variant: str) -> tuple[list[dict], str | None]:
    """Parse data rows into dict list, truncate at MAX_IMPORT_ROWS."""
    columns = _cols(section, variant)
    mh = _multi_header(section, variant)
    data_start = int(mh["data_start_row"]) if mh else 2
    # 与 _validate_columns 同一套表头读取（纵向合并列回退第 1 行）
    actual_cols = _header_cells(ws, section, variant)

    rows: list[dict] = []
    warning: str | None = None
    row_count = 0

    for row in ws.iter_rows(min_row=data_start, values_only=True):
        if all(v is None or v == '' for v in row):
            continue
        row_count += 1
        if row_count > MAX_IMPORT_ROWS:
            warning = f"数据超过{MAX_IMPORT_ROWS}行限制，已截断至{MAX_IMPORT_ROWS}行"
            break

        row_dict: dict[str, Any] = {}
        for col_idx, val in enumerate(row):
            if col_idx < len(actual_cols):
                col_name = actual_cols[col_idx]
                if col_name in columns:
                    row_dict[col_name] = val if val is not None else ''
        rows.append(row_dict)

    return rows, warning


def _rfc5987_filename(filename: str) -> str:
    """RFC5987 encode filename for Content-Disposition header (Chinese filename fix)."""
    return f"attachment; filename*=UTF-8''{quote(filename)}"


def _num(v: Any) -> float:
    try:
        if v is None or v == '':
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def _safe_parse_rows(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _sheet_values(rows: list[dict[str, Any]], cols: list[str]) -> list[list[Any]]:
    return [[r.get(c, '') for c in cols] for r in rows]


def _portfolio_sheet_rows(
    end_rows: list[dict[str, Any]],
    prior_rows: list[dict[str, Any]],
    variant: str,
) -> list[dict[str, Any]]:
    """组合计提明细 → sheet 行（按名称把期末 / 上年年末对齐，同前端 `mergePortfolio`）。

    国企侧源模板只有期末两列，故不输出上年年末列（列定义已在 override 里裁掉）。
    """
    def name_of(r: dict[str, Any]) -> str:
        return str(r.get('drawerTypeOrAging') or '')

    names: list[str] = []
    for r in [*end_rows, *prior_rows]:
        n = name_of(r)
        if n not in names:
            names.append(n)
    out: list[dict[str, Any]] = []
    for n in names:
        e = next((r for r in end_rows if name_of(r) == n), {})
        p = next((r for r in prior_rows if name_of(r) == n), {})
        row: dict[str, Any] = {
            '名称': n,
            '期末应收票据': _num(e.get('balance')),
            '期末坏账准备': _num(e.get('provision')),
        }
        if variant != 'soe':
            row['上年年末应收票据'] = _num(p.get('balance'))
            row['上年年末坏账准备'] = _num(p.get('provision'))
        out.append(row)
    return out


def _portfolio_import_rows(rows: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    """sheet 行 → 组合计提明细持久化行（`*-portfolio-{period}-rows`）。"""
    bal_key = '期末应收票据' if period == 'end' else '上年年末应收票据'
    prov_key = '期末坏账准备' if period == 'end' else '上年年末坏账准备'
    out: list[dict[str, Any]] = []
    for r in rows:
        name = str(r.get('名称') or '').strip()
        if not name:
            continue
        bal = _num(r.get(bal_key))
        prov = _num(r.get(prov_key))
        out.append({
            "rowId": f"pf-{uuid.uuid4().hex[:10]}",
            "rowType": "dynamic",
            "drawerTypeOrAging": name,
            "isFixed": False,
            "balance": bal,
            "provision": prov,
            "lossRate": (prov / bal) if bal else 0,
        })
    return out


def _upsert_item_payload(variant: str, item_key: str, remark: Any) -> tuple[str, str]:
    item_id = f"D1-disc-{variant}-{item_key}"
    if isinstance(remark, (int, float)):
        remark_str = str(remark)
    elif isinstance(remark, str):
        remark_str = remark
    else:
        remark_str = json.dumps(remark, ensure_ascii=False)
    return item_id, remark_str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/{wp_id}/d1/disclosure/export-template")
async def export_disclosure_template(
    wp_id: str,
    variant: str = Query(..., description="上市/国企: listed or soe"),
):
    """导出空白xlsx模板（含表头+格式，每section一个sheet）"""
    _validate_variant(variant)

    wb = _create_template_workbook(variant)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"D1-附注披露-{'上市公司' if variant == 'listed' else '国企'}-模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _rfc5987_filename(filename)},
    )


@router.post("/{wp_id}/d1/disclosure/export-data")
async def export_disclosure_data(
    wp_id: str,
    variant: str = Query(..., description="上市/国企: listed or soe"),
    db: AsyncSession = Depends(get_db),
):
    """导出含当前数据的xlsx（基础版：含表头的模板作为基础）"""
    _validate_variant(variant)

    wb = _create_template_workbook(variant)
    result = await db.execute(
        text("""
            SELECT item_id, remark
            FROM checklist_responses
            WHERE wp_id = :wp_id
              AND item_id LIKE :prefix
        """),
        {"wp_id": str(wp_id), "prefix": f"D1-disc-{variant}-%"},
    )
    response_map = {str(r.item_id): (r.remark or '') for r in result.fetchall()}
    _fill_template_with_data(wb, variant, response_map)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"D1-附注披露-{'上市公司' if variant == 'listed' else '国企'}-数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _rfc5987_filename(filename)},
    )


@router.post("/{wp_id}/d1/disclosure/import-data")
async def import_disclosure_data(
    wp_id: str,
    variant: str = Query(..., description="上市/国企: listed or soe"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """解析xlsx回写checklist_responses"""
    _validate_variant(variant)

    if not file.filename or not file.filename.endswith('.xlsx'):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式文件")

    content = await file.read()
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法解析xlsx文件: {str(e)}")

    sections = VARIANT_SECTIONS[variant]
    total_rows = 0
    all_warnings: list[str] = []
    all_invalid: list[str] = []
    parsed_by_sheet: dict[str, list[dict[str, Any]]] = {}

    for sheet_name in wb.sheetnames:
        section_key = TITLE_TO_SECTION.get(sheet_name, sheet_name)
        if section_key not in sections:
            continue
        ws = wb[sheet_name]

        # Column validation
        invalid = _validate_columns(ws, section_key, variant)
        if invalid:
            all_invalid.extend([f"{sheet_name}: {col}" for col in invalid])
            continue

        rows, warning = _parse_rows(ws, section_key, variant)
        total_rows += len(rows)
        parsed_by_sheet[section_key] = rows
        if warning:
            all_warnings.append(f"{sheet_name}: {warning}")

    if all_invalid:
        raise HTTPException(
            status_code=400,
            detail={"message": "列名不匹配", "invalid_columns": all_invalid},
        )

    now = datetime.now(timezone.utc)

    def build_class_rows(rows: list[dict[str, Any]], period: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        single_balance = single_provision = 0.0
        bank_balance = bank_provision = 0.0
        commercial_balance = commercial_provision = 0.0
        individuals: list[dict[str, Any]] = []
        for row in rows:
            label = str(row.get('类别') or '').strip()
            bal = _num(row.get('账面余额'))
            prov = _num(row.get('坏账准备'))
            if label.startswith('按单项'):
                single_balance, single_provision = bal, prov
            elif label == '银行承兑汇票':
                bank_balance, bank_provision = bal, prov
            elif label == '商业承兑汇票':
                commercial_balance, commercial_provision = bal, prov
            elif label in ('', '其中：', '合计', '按组合计提坏账准备'):
                continue
            else:
                individuals.append({
                    "rowId": f"ind-{uuid.uuid4().hex[:10]}",
                    "rowType": "dynamic",
                    "name": label,
                    "isFixed": False,
                    "balance": bal,
                    "provision": prov,
                    "lossRate": (prov / bal) if bal else 0,
                    "basis": str(row.get('计提依据') or row.get('计提理由') or ''),
                })
        class_rows = [
            {"rowId": f"class-{period}-individual", "rowType": "fixed", "label": "按单项计提", "isFixed": True, "balance": single_balance, "ratio": 0, "provision": single_provision, "lossRate": (single_provision / single_balance) if single_balance else 0, "bookValue": single_balance - single_provision},
            {"rowId": f"class-{period}-portfolio-bank", "rowType": "fixed", "label": "按组合计提-银行承兑汇票", "isFixed": True, "balance": bank_balance, "ratio": 0, "provision": bank_provision, "lossRate": (bank_provision / bank_balance) if bank_balance else 0, "bookValue": bank_balance - bank_provision},
            {"rowId": f"class-{period}-portfolio-commercial", "rowType": "fixed", "label": "按组合计提-商业承兑汇票", "isFixed": True, "balance": commercial_balance, "ratio": 0, "provision": commercial_provision, "lossRate": (commercial_provision / commercial_balance) if commercial_balance else 0, "bookValue": commercial_balance - commercial_provision},
        ]
        total_balance = single_balance + bank_balance + commercial_balance
        for r in class_rows:
            r["ratio"] = (r["balance"] / total_balance) if total_balance else 0
        return class_rows, individuals

    def _end_balance(o: dict[str, Any]) -> float:
        """期末 = 期初 + 计提 − 收回或转回 − 核销 − 转销 − 其他变动（源模板 G48 / B100）。"""
        return (
            _num(o.get('priorBalance')) + _num(o.get('provision'))
            - _num(o.get('reversal')) - _num(o.get('writeOff'))
            - _num(o.get('transfer')) - _num(o.get('other'))
        )

    movement_rows_payload: list[dict[str, Any]]
    if variant == 'soe':
        # 国企变动主表是横排：类别 × 期初 / 计提 / 收回或转回 / 核销 / 其他变动 / 期末
        soe_mv_labels = [
            ('mv-individual', '按单项计提', '单项计提预期信用损失的应收票据'),
            ('mv-portfolio', '按组合计提', '按组合计提预期信用损失的应收票据'),
            ('mv-total', '合计', '合计'),
        ]
        by_label = {str(r.get('类别') or '').strip(): r for r in parsed_by_sheet.get('badDebtMovementMain', [])}
        movement_rows_payload = []
        for row_id, stored_label, sheet_label in soe_mv_labels:
            src = by_label.get(sheet_label, {})
            obj = {
                "rowId": row_id, "rowType": "fixed", "label": stored_label, "isFixed": True,
                "priorBalance": _num(src.get('期初数')),
                "provision": _num(src.get('计提')),
                "reversal": _num(src.get('收回或转回')),
                "writeOff": _num(src.get('核销')),
                "transfer": 0.0,
                "other": _num(src.get('其他变动')),
                "endBalance": _num(src.get('期末数')),
            }
            if not obj["endBalance"]:
                obj["endBalance"] = _end_balance(obj)
            movement_rows_payload.append(obj)
    else:
        movement_map = {
            '上年年末数': 'priorBalance',
            '本期计提': 'provision',
            '本期收回或转回': 'reversal',
            '本期核销': 'writeOff',
            '【本期转销】': 'transfer',
            '【其他】': 'other',
            '期末数': 'endBalance',
        }
        mv_obj: dict[str, Any] = {"rowId": "mv-total", "rowType": "fixed", "label": "合计", "isFixed": True, "priorBalance": 0, "provision": 0, "reversal": 0, "writeOff": 0, "transfer": 0, "other": 0, "endBalance": 0}
        for row in parsed_by_sheet.get('badDebtMovementMain', []):
            label = str(row.get('项目') or '').strip()
            key = movement_map.get(label)
            if key:
                mv_obj[key] = _num(row.get('坏账准备金额'))
        if not mv_obj["endBalance"]:
            mv_obj["endBalance"] = _end_balance(mv_obj)
        movement_rows_payload = [mv_obj]

    # 国企「其中：」明细行（F4-20）
    movement_detail_payload = []
    for r in parsed_by_sheet.get('movementDetail', []):
        label = str(r.get('类别') or '').strip()
        if not label:
            continue
        obj = {
            "rowId": f"mvd-{uuid.uuid4().hex[:10]}", "rowType": "dynamic", "label": label, "isFixed": False,
            "priorBalance": _num(r.get('期初数')),
            "provision": _num(r.get('计提')),
            "reversal": _num(r.get('收回或转回')),
            "writeOff": _num(r.get('核销')),
            "transfer": 0.0,
            "other": _num(r.get('其他变动')),
            "endBalance": 0.0,
        }
        obj["endBalance"] = _end_balance(obj)
        movement_detail_payload.append(obj)

    class_end_rows, individual_end_rows = build_class_rows(parsed_by_sheet.get('badDebtClassEnd', []), 'end')
    class_prior_rows, individual_prior_rows = build_class_rows(parsed_by_sheet.get('badDebtClassPrior', []), 'prior')

    reversal_rows = [
        {
            "rowId": f"rv-{uuid.uuid4().hex[:10]}",
            "rowType": "dynamic",
            "isFixed": False,
            "companyName": str(r.get('债务人名称') if variant == 'soe' else r.get('单位名称') or ''),
            # 国企只有「转回或收回原因、方式」一列文本
            "reversalReason": str(
                (r.get('转回或收回原因、方式') if variant == 'soe' else r.get('转回原因')) or ''
            ),
            "originalMethod": str(r.get('收回方式') or ''),
            "reversalBasis": str(r.get('原确定坏账准备的依据') or ''),
            "cumulativeProvision": _num(r.get('转回或收回前累计已计提坏账准备金额')),
            "amount": _num(r.get('转回或收回金额')),
        }
        for r in parsed_by_sheet.get('badDebtMovementDetail', [])
    ]
    writeoff_rows = [
        {
            "rowId": f"wo-{uuid.uuid4().hex[:10]}",
            "rowType": "dynamic",
            "isFixed": False,
            "companyName": str(r.get('单位名称') or ''),
            "noteType": str(
                (r.get('应收票据的性质') if variant == 'soe' else r.get('应收票据性质')) or ''
            ),
            "amount": _num(r.get('核销金额')),
            "reason": str(r.get('核销原因') or ''),
            "procedure": str(r.get('履行的核销程序') or ''),
            "relatedPartyFlag": str(
                (r.get('是否由关联交易产生') if variant == 'soe' else r.get('款项是否由关联交易产生')) or ''
            ),
        }
        for r in parsed_by_sheet.get('writeOffDetail', [])
    ]
    writeoff_amount = 0.0
    for r in parsed_by_sheet.get('writeOffMain', []):
        if str(r.get('项目') or '').strip():
            writeoff_amount = _num(r.get('核销金额'))
            break

    payload_items: list[tuple[str, str]] = []
    payload_items.append(_upsert_item_payload(variant, 'pledged-rows', [
        {"rowId": f"pl-{uuid.uuid4().hex[:10]}", "rowType": "dynamic", "category": str(r.get('种类') or ''), "isFixed": False, "pledgedAmount": _num(r.get('期末已质押金额'))}
        for r in parsed_by_sheet.get('pledged', [])
    ]))
    payload_items.append(_upsert_item_payload(variant, 'endorsed-rows', [
        {"rowId": f"en-{uuid.uuid4().hex[:10]}", "rowType": "dynamic", "category": str(r.get('种类') or ''), "isFixed": False, "derecognizedAmount": _num(r.get('期末终止确认金额')), "notDerecognizedAmount": _num(r.get('期末未终止确认金额'))}
        for r in parsed_by_sheet.get('endorsed', [])
    ]))
    payload_items.append(_upsert_item_payload(variant, 'transfer-rows', [
        {"rowId": f"tr-{uuid.uuid4().hex[:10]}", "rowType": "dynamic", "category": str(r.get('种类') or ''), "isFixed": False, "transferAmount": _num(r.get('期末转应收账款金额'))}
        for r in parsed_by_sheet.get('transfer', [])
    ]))
    payload_items.append(_upsert_item_payload(variant, 'class-end-rows', class_end_rows))
    payload_items.append(_upsert_item_payload(variant, 'individual-end-rows', individual_end_rows))
    payload_items.append(_upsert_item_payload(variant, 'class-prior-rows', class_prior_rows))
    payload_items.append(_upsert_item_payload(variant, 'individual-prior-rows', individual_prior_rows))
    payload_items.append(_upsert_item_payload(variant, 'movement-rows', movement_rows_payload))
    payload_items.append(_upsert_item_payload(variant, 'movement-detail-rows', movement_detail_payload))
    # 组合计提明细（本轮新增录入面）
    payload_items.append(_upsert_item_payload(
        variant, 'bank-portfolio-end-rows',
        _portfolio_import_rows(parsed_by_sheet.get('portfolioBank', []), 'end'),
    ))
    payload_items.append(_upsert_item_payload(
        variant, 'commercial-portfolio-end-rows',
        _portfolio_import_rows(parsed_by_sheet.get('portfolioCommercial', []), 'end'),
    ))
    if variant != 'soe':
        payload_items.append(_upsert_item_payload(
            variant, 'bank-portfolio-prior-rows',
            _portfolio_import_rows(parsed_by_sheet.get('portfolioBank', []), 'prior'),
        ))
        payload_items.append(_upsert_item_payload(
            variant, 'commercial-portfolio-prior-rows',
            _portfolio_import_rows(parsed_by_sheet.get('portfolioCommercial', []), 'prior'),
        ))
    payload_items.append(_upsert_item_payload(variant, 'reversal-rows', reversal_rows))
    payload_items.append(_upsert_item_payload(variant, 'writeoff-rows', writeoff_rows))
    payload_items.append(_upsert_item_payload(variant, 'writeoff-amount', writeoff_amount))
    summary_rows = parsed_by_sheet.get('topSummary', []) or parsed_by_sheet.get('categorySummary', [])
    payload_items.append(_upsert_item_payload(variant, 'top-summary-rows', summary_rows))

    notes_map = {str(r.get('事项') or '').strip(): str(r.get('说明') or '') for r in parsed_by_sheet.get('notes', [])}
    payload_items.append(_upsert_item_payload(variant, 'note-top', notes_map.get('总说明', '')))
    payload_items.append(_upsert_item_payload(variant, 'note-pledged', notes_map.get('（1）已质押说明', '')))
    payload_items.append(_upsert_item_payload(variant, 'note-endorsed', notes_map.get('（2）背书贴现说明', '')))
    payload_items.append(_upsert_item_payload(variant, 'note-badDebtClass', notes_map.get('（4）坏账分类说明', '')))
    payload_items.append(_upsert_item_payload(variant, 'note-writeOff', notes_map.get('（6）核销说明', '')))

    project_row = await db.execute(
        text("SELECT project_id FROM working_paper WHERE id = :wp_id LIMIT 1"),
        {"wp_id": str(wp_id)},
    )
    project_id = project_row.scalar_one_or_none()
    if not project_id:
        raise HTTPException(status_code=400, detail="无法确定 project_id，请确认底稿存在")

    upsert_sql = text("""
        INSERT INTO checklist_responses (project_id, wp_id, item_id, conclusion, remark, wp_ref, updated_by, created_at, updated_at)
        VALUES (:project_id, :wp_id, :item_id, NULL, :remark, NULL, :updated_by, :now, :now)
        ON CONFLICT (wp_id, item_id) DO UPDATE SET
            remark = EXCLUDED.remark,
            updated_by = EXCLUDED.updated_by,
            updated_at = EXCLUDED.updated_at
    """)
    for item_id, remark in payload_items:
        await db.execute(
            upsert_sql,
            {
                "project_id": str(project_id),
                "wp_id": str(wp_id),
                "item_id": item_id,
                "remark": remark,
                "updated_by": str(current_user.id),
                "now": now,
            },
        )
    await db.commit()

    result: dict[str, Any] = {"rowCount": total_rows, "sectionCount": len(sections), "savedItems": len(payload_items)}
    if all_warnings:
        result["warnings"] = all_warnings

    return {"data": result}
