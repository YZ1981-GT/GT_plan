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

SECTION_COLUMNS: dict[str, list[str]] = {
    'topSummary': ['票据种类', '期末余额', '期末坏账准备', '期末账面价值', '上年年末余额', '上年年末坏账准备', '上年年末账面价值'],
    'pledged': ['票据种类', '期末已质押金额'],
    'endorsed': ['票据种类', '终止确认金额', '未终止确认金额'],
    'transfer': ['票据种类', '转应收账款金额'],
    'badDebtClassEnd': ['类别', '账面余额', '坏账准备', '预期信用损失率（%）', '计提依据', '账面价值'],
    'badDebtClassPrior': ['类别', '账面余额', '坏账准备', '预期信用损失率（%）', '计提依据', '账面价值'],
    'badDebtMovementMain': ['项目', '坏账准备金额'],
    'badDebtMovementDetail': ['单位名称', '转回原因', '收回方式', '原确定坏账准备金额的依据', '转回或收回金额'],
    'writeOffMain': ['项目', '核销金额'],
    'writeOffDetail': ['单位名称', '应收票据', '核销金额', '核销原因', '履行的核销程序', '款项是否由关联交易产生'],
    'categorySummary': ['票据种类', '期末余额', '期末坏账准备', '期末账面价值', '期初余额', '期初坏账准备', '期初账面价值'],
    'notes': ['事项', '说明'],
}

# Sections per variant
VARIANT_SECTIONS: dict[str, list[str]] = {
    'listed': ['topSummary', 'pledged', 'endorsed', 'transfer', 'badDebtClassEnd', 'badDebtClassPrior', 'badDebtMovementMain', 'badDebtMovementDetail', 'writeOffMain', 'writeOffDetail', 'notes'],
    'soe': ['categorySummary', 'badDebtClassEnd', 'badDebtClassPrior', 'badDebtMovementMain', 'badDebtMovementDetail', 'pledged', 'endorsed', 'transfer', 'writeOffMain', 'writeOffDetail', 'notes'],
}

SHEET_TITLES: dict[str, str] = {
    'topSummary': '（0）应收票据汇总',
    'categorySummary': '（国企）应收票据分类汇总',
    'pledged': '（1）期末已质押的应收票据',
    'endorsed': '（2）已背书或贴现且未到期',
    'transfer': '（3）转为应收账款的票据',
    'badDebtClassEnd': '（4.1）坏账计提分类（期末）',
    'badDebtClassPrior': '（4.2）坏账计提分类（上年年末）',
    'badDebtMovementMain': '（5）坏账准备变动（主表）',
    'badDebtMovementDetail': '（5）坏账准备转回收回（其中）',
    'writeOffMain': '（6）实际核销（主表）',
    'writeOffDetail': '（6）实际核销（其中）',
    'notes': '说明事项',
}
TITLE_TO_SECTION: dict[str, str] = {v: k for k, v in SHEET_TITLES.items()}

# 多层表头配置：section -> (第1行, 第2行, 合并区域, 数据起始行)
MULTI_HEADER_CONFIG: dict[str, dict[str, Any]] = {
    "topSummary": {
        "row1": ["票据种类", "期末余额", "", "", "上年年末余额", "", ""],
        "row2": ["票据种类", "账面余额", "坏账准备", "账面价值", "账面余额", "坏账准备", "账面价值"],
        "merges": ["A1:A2", "B1:D1", "E1:G1"],
        "data_start_row": 3,
    },
    "categorySummary": {
        "row1": ["票据种类", "期末数", "", "", "期初数", "", ""],
        "row2": ["票据种类", "账面余额", "坏账准备", "期末账面价值", "账面余额", "坏账准备", "期初账面价值"],
        "merges": ["A1:A2", "B1:D1", "E1:G1"],
        "data_start_row": 3,
    },
    "badDebtClassEnd": {
        "row1": ["类别", "期末余额", "", "", "", ""],
        "row2": ["类别", "账面余额", "坏账准备", "预期信用损失率（%）", "计提依据", "账面价值"],
        "merges": ["A1:A2", "B1:F1"],
        "data_start_row": 3,
    },
    "badDebtClassPrior": {
        "row1": ["类别", "上年年末余额", "", "", "", ""],
        "row2": ["类别", "账面余额", "坏账准备", "预期信用损失率（%）", "计提依据", "账面价值"],
        "merges": ["A1:A2", "B1:F1"],
        "data_start_row": 3,
    },
    "badDebtMovementMain": {
        "row1": ["（5）本期计提、收回或转回的坏账准备情况", ""],
        "row2": ["项目", "坏账准备金额"],
        "merges": ["A1:B1"],
        "data_start_row": 3,
    },
    "writeOffMain": {
        "row1": ["（6）本期实际核销的应收票据情况", ""],
        "row2": ["项目", "核销金额"],
        "merges": ["A1:B1"],
        "data_start_row": 3,
    },
    "badDebtMovementDetail": {
        "row1": ["其中：本期转回或收回金额重要的坏账准备如下：", "", "", "", ""],
        "row2": ['单位名称', '转回原因', '收回方式', '原确定坏账准备金额的依据', '转回或收回金额'],
        "merges": ["A1:E1"],
        "data_start_row": 3,
    },
    "writeOffDetail": {
        "row1": ["其中，重要的应收票据核销情况如下（逐项披露）：", "", "", "", "", ""],
        "row2": ['单位名称', '应收票据', '核销金额', '核销原因', '履行的核销程序', '款项是否由关联交易产生'],
        "merges": ["A1:F1"],
        "data_start_row": 3,
    },
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
        columns = SECTION_COLUMNS[section]
        ws = wb.create_sheet(title=SHEET_TITLES.get(section, section))
        mh = MULTI_HEADER_CONFIG.get(section)
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
            fixed_rows = ['上年年末数', '本期计提', '本期收回或转回', '本期核销', '【本期转销】', '【其他】', '期末数']
            start_row = MULTI_HEADER_CONFIG['badDebtMovementMain']['data_start_row']
            for i, label in enumerate(fixed_rows, start=start_row):
                ws.cell(row=i, column=1, value=label)
                if '【' in label:
                    ws.cell(row=i, column=1).font = Font(color="C00000")
                ws.cell(row=i, column=1).fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
        elif section == 'writeOffMain':
            start_row = MULTI_HEADER_CONFIG['writeOffMain']['data_start_row']
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
            {'票据种类': r.get('category', ''), '期末已质押金额': _num(r.get('pledgedAmount'))}
            for r in get_rows('pledged-rows')
        ],
        'endorsed': [
            {'票据种类': r.get('category', ''), '终止确认金额': _num(r.get('derecognizedAmount')), '未终止确认金额': _num(r.get('notDerecognizedAmount'))}
            for r in get_rows('endorsed-rows')
        ],
        'transfer': [
            {'票据种类': r.get('category', ''), '转应收账款金额': _num(r.get('transferAmount'))}
            for r in get_rows('transfer-rows')
        ],
        'badDebtMovementDetail': [
            {
                '单位名称': r.get('companyName', ''),
                '转回原因': r.get('reversalReason', ''),
                '收回方式': r.get('originalMethod', ''),
                '原确定坏账准备金额的依据': r.get('reversalBasis', ''),
                '转回或收回金额': _num(r.get('amount')),
            }
            for r in get_rows('reversal-rows')
        ],
        'writeOffDetail': [
            {
                '单位名称': r.get('companyName', ''),
                '应收票据': r.get('noteType', ''),
                '核销金额': _num(r.get('amount')),
                '核销原因': r.get('reason', ''),
                '履行的核销程序': r.get('procedure', ''),
                '款项是否由关联交易产生': r.get('relatedPartyFlag', ''),
            }
            for r in get_rows('writeoff-rows')
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
            {'类别': '按单项计提坏账准备', '账面余额': _num(single.get('balance')), '坏账准备': _num(single.get('provision')), '预期信用损失率（%）': '', '计提依据': '', '账面价值': _num(single.get('bookValue'))},
            {'类别': '其中：', '账面余额': '', '坏账准备': '', '预期信用损失率（%）': '', '计提依据': '', '账面价值': ''},
        ]
        for r in individuals:
            bal = _num(r.get('balance'))
            prov = _num(r.get('provision'))
            rows.append({'类别': r.get('name', ''), '账面余额': bal, '坏账准备': prov, '预期信用损失率（%）': '', '计提依据': r.get('basis', ''), '账面价值': bal - prov})
        rows.extend([
            {'类别': '按组合计提坏账准备', '账面余额': combo_bal, '坏账准备': combo_prov, '预期信用损失率（%）': '', '计提依据': '', '账面价值': combo_bal - combo_prov},
            {'类别': '其中：', '账面余额': '', '坏账准备': '', '预期信用损失率（%）': '', '计提依据': '', '账面价值': ''},
            {'类别': '银行承兑汇票', '账面余额': _num(bank.get('balance')), '坏账准备': _num(bank.get('provision')), '预期信用损失率（%）': '', '计提依据': '', '账面价值': _num(bank.get('bookValue'))},
            {'类别': '商业承兑汇票', '账面余额': _num(commercial.get('balance')), '坏账准备': _num(commercial.get('provision')), '预期信用损失率（%）': '', '计提依据': '', '账面价值': _num(commercial.get('bookValue'))},
            {'类别': '合计', '账面余额': total_bal, '坏账准备': total_prov, '预期信用损失率（%）': '', '计提依据': '', '账面价值': total_book},
        ])
        return rows

    sheet_rows['badDebtClassEnd'] = build_bad_debt_class('end')
    sheet_rows['badDebtClassPrior'] = build_bad_debt_class('prior')

    for sheet_name, rows in sheet_rows.items():
        sheet_title = SHEET_TITLES.get(sheet_name, sheet_name)
        if sheet_title not in wb.sheetnames:
            continue
        ws = wb[sheet_title]
        cols = SECTION_COLUMNS[sheet_name]
        mh = MULTI_HEADER_CONFIG.get(sheet_name)
        start_row = int(mh["data_start_row"]) if mh else 2
        for r_idx, row_vals in enumerate(_sheet_values(rows, cols), start=start_row):
            for c_idx, cell_val in enumerate(row_vals, start=1):
                ws.cell(row=r_idx, column=c_idx, value=cell_val)


def _validate_columns(ws: Any, section: str) -> list[str]:
    """Validate column names, return list of invalid column names."""
    expected_list = SECTION_COLUMNS.get(section, [])
    expected = set(expected_list)
    if not expected:
        return ['未知的section类型']

    mh = MULTI_HEADER_CONFIG.get(section)
    header_row = 2 if mh else 1
    actual: list[str] = []
    for cell in ws[header_row]:
        if cell.value is not None and str(cell.value).strip() != '':
            actual.append(str(cell.value).strip())

    invalid = [col for col in actual if col not in expected]
    missing = [col for col in expected_list if col not in actual]
    invalid.extend([f"缺少列:{m}" for m in missing])
    if len(actual) < 2:
        invalid.append('列数不足(至少需要2列)')
    return invalid


def _parse_rows(ws: Any, section: str) -> tuple[list[dict], str | None]:
    """Parse data rows into dict list, truncate at MAX_IMPORT_ROWS."""
    columns = SECTION_COLUMNS.get(section, [])
    mh = MULTI_HEADER_CONFIG.get(section)
    header_row = 2 if mh else 1
    data_start = int(mh["data_start_row"]) if mh else 2
    actual_cols: list[str] = []
    for cell in ws[header_row]:
        if cell.value is not None:
            actual_cols.append(str(cell.value).strip())
        else:
            actual_cols.append('')

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
        invalid = _validate_columns(ws, section_key)
        if invalid:
            all_invalid.extend([f"{sheet_name}: {col}" for col in invalid])
            continue

        rows, warning = _parse_rows(ws, section_key)
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
                    "basis": str(row.get('计提依据') or ''),
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

    movement_map = {
        '上年年末数': 'priorBalance',
        '本期计提': 'provision',
        '本期收回或转回': 'reversal',
        '本期核销': 'writeOff',
        '【本期转销】': 'transfer',
        '【其他】': 'other',
        '期末数': 'endBalance',
    }
    mv_obj = {"rowId": "mv-total", "rowType": "fixed", "label": "合计", "isFixed": True, "priorBalance": 0, "provision": 0, "reversal": 0, "writeOff": 0, "transfer": 0, "other": 0, "endBalance": 0}
    for row in parsed_by_sheet.get('badDebtMovementMain', []):
        label = str(row.get('项目') or '').strip()
        key = movement_map.get(label)
        if key:
            mv_obj[key] = _num(row.get('坏账准备金额'))
    if not mv_obj["endBalance"]:
        mv_obj["endBalance"] = mv_obj["priorBalance"] + mv_obj["provision"] - mv_obj["reversal"] - mv_obj["writeOff"] - mv_obj["transfer"] + mv_obj["other"]

    class_end_rows, individual_end_rows = build_class_rows(parsed_by_sheet.get('badDebtClassEnd', []), 'end')
    class_prior_rows, individual_prior_rows = build_class_rows(parsed_by_sheet.get('badDebtClassPrior', []), 'prior')

    reversal_rows = [
        {
            "rowId": f"rv-{uuid.uuid4().hex[:10]}",
            "rowType": "dynamic",
            "isFixed": False,
            "companyName": str(r.get('单位名称') or ''),
            "reversalReason": str(r.get('转回原因') or ''),
            "originalMethod": str(r.get('收回方式') or ''),
            "reversalBasis": str(r.get('原确定坏账准备金额的依据') or ''),
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
            "noteType": str(r.get('应收票据') or ''),
            "amount": _num(r.get('核销金额')),
            "reason": str(r.get('核销原因') or ''),
            "procedure": str(r.get('履行的核销程序') or ''),
            "relatedPartyFlag": str(r.get('款项是否由关联交易产生') or ''),
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
        {"rowId": f"pl-{uuid.uuid4().hex[:10]}", "rowType": "dynamic", "category": str(r.get('票据种类') or ''), "isFixed": False, "pledgedAmount": _num(r.get('期末已质押金额'))}
        for r in parsed_by_sheet.get('pledged', [])
    ]))
    payload_items.append(_upsert_item_payload(variant, 'endorsed-rows', [
        {"rowId": f"en-{uuid.uuid4().hex[:10]}", "rowType": "dynamic", "category": str(r.get('票据种类') or ''), "isFixed": False, "derecognizedAmount": _num(r.get('终止确认金额')), "notDerecognizedAmount": _num(r.get('未终止确认金额'))}
        for r in parsed_by_sheet.get('endorsed', [])
    ]))
    payload_items.append(_upsert_item_payload(variant, 'transfer-rows', [
        {"rowId": f"tr-{uuid.uuid4().hex[:10]}", "rowType": "dynamic", "category": str(r.get('票据种类') or ''), "isFixed": False, "transferAmount": _num(r.get('转应收账款金额'))}
        for r in parsed_by_sheet.get('transfer', [])
    ]))
    payload_items.append(_upsert_item_payload(variant, 'class-end-rows', class_end_rows))
    payload_items.append(_upsert_item_payload(variant, 'individual-end-rows', individual_end_rows))
    payload_items.append(_upsert_item_payload(variant, 'class-prior-rows', class_prior_rows))
    payload_items.append(_upsert_item_payload(variant, 'individual-prior-rows', individual_prior_rows))
    payload_items.append(_upsert_item_payload(variant, 'movement-rows', [mv_obj]))
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
