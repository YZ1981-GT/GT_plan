"""D2 应收账款导入导出端点

POST /api/workpapers/{wp_id}/d2/export-template?sheet=D2-2
POST /api/workpapers/{wp_id}/d2/export-data?sheet=D2-2
POST /api/workpapers/{wp_id}/d2/import-data?sheet=D2-2

使用 openpyxl 生成/解析 xlsx。
格式校验：列名不匹配时返回 400 + 错误列名列表。
行数限制：超500行截断 + 返回警告摘要。
支持 D2-1/D2-2/D2-3/D2-4/D2-6/D2-7/D2-9/D2-10/D2-11/D2-12 十个sheet。

Requirements: 19.1-19.7
"""
import io
import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.routers.wp_render_strategies._cycle_import_export_common import (
    AGING_PERIOD_LABELS,
    load_json_rows,
    match_import_aging,
    resolve_aging_segments,
    safe_float,
    safe_str,
    subject_aging_periods,
    upsert_json_rows,
)
from app.routers.wp_render_strategies._aging_export_headers import _looks_like_aging

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, Alignment, PatternFill
except ImportError:
    Workbook = None  # type: ignore
    load_workbook = None  # type: ignore

router = APIRouter(prefix="/api/workpapers", tags=["D2导入导出"])

# ─── Constants ────────────────────────────────────────────────────────────────

VALID_SHEETS = frozenset({
    'D2-1', 'D2-2', 'D2-3', 'D2-4', 'D2-5', 'D2-6', 'D2-7', 'D2-8', 'D2-9', 'D2-10', 'D2-11', 'D2-12', 'D2-13'
})

MAX_IMPORT_ROWS = 500

_D2_1_ROWS: list[tuple[str, str]] = [
    ('individual', '应收账款-单项计提'),
    ('aging', '应收账款-账龄组合'),
    ('customer-type', '应收账款-客户类型组合'),
]

_D2_1_FIELDS: list[tuple[str, str, bool]] = [
    ('prior-unadjusted', '期初未审', False),
    ('prior-aje', '期初AJE', False),
    ('prior-rje', '期初RJE', False),
    ('current-unadjusted', '期末未审', False),
    ('current-aje', '期末AJE', False),
    ('current-rje', '期末RJE', False),
    ('reason', '原因分析', True),
]

SHEET_COLUMNS: dict[str, list[str]] = {
    'D2-1': [
        '行键', '项目',
        '期初未审', '期初AJE', '期初RJE',
        '期末未审', '期末AJE', '期末RJE',
        '原因分析',
    ],
    'D2-2': None,  # 动态生成，见 get_d2_2_columns(segments)
    'D2-3': [
        '项目', '分类', '期初审定', '本期计提', '本期转入',
        '本期收回', '本期转回', '本期核销', '期末未审',
        '期末AJE', '期末RJE', '期末审定', '备注',
    ],
    'D2-4': [
        '序号', '类型', '借方科目', '贷方科目', '借方金额',
        '贷方金额', '摘要', '日期', '编制人', '备注',
    ],
    'D2-5': [
        'item_id', '值',
    ],
    'D2-6': [
        '序号', '关联方名称', '关系', '期初余额',
        '借方发生', '贷方发生', '期末余额', '坏账准备',
        '账面价值', '交易内容', '定价政策', '备注',
    ],
    'D2-7': [
        '序号', '客户名称', '日期', '凭证编号', '业务内容',
        '对方科目', '借方金额', '贷方金额',
        '原始凭证齐全', '记账凭证相符', '账务处理正确',
        '记录期间正确', '其他',
        '是否异常', '异常说明', '结论', '备注',
    ],
    'D2-8': [
        '记录类型', '段落ID/账龄段', '标题', '政策条款', '实际情况',
        '审计师评价', '结论',
        '余额Y1', '余额Y2', '余额Y3',
        '损失Y1', '损失Y2', '损失Y3',
        '迁徙率Y1', '迁徙率Y2', '迁徙率Y3',
    ],
    'D2-9': [
        '序号', '债务人名称', '审定账面余额', '预期信用损失率',
        '应计提金额', '实际计提金额', '差异', '计提依据', '备注',
    ],
    'D2-10': [
        '序号', '账龄段', '年度1迁徙率', '年度2迁徙率', '年度3迁徙率', '备注',
    ],
    'D2-11': [
        '序号', '类别', '单位名称', '原因', '方式',
        '金额', '原累计已计提', '合理性分析', '备注',
    ],
    'D2-12': [
        '序号', '类别', '客户名称', '金额', '对手方',
        '合同编号', '起始日期', '到期日期', '风险转移',
        '控制保留', '终止确认', '备注',
    ],
    'D2-13': [
        '记录类型', '问题ID/行ID', '问题', '回答', '说明',
        '组合名称', '业务模式', 'SPPI结果', '计量基础', '备注',
    ],
}

# D2-2 明细表固定（非账龄）列 — 供导入校验使用（账龄列按 label 动态匹配）。Task 12.2
_D2_2_BASE_COLUMNS: list[str] = [
    '序号', '客户名称', '公司代码', '关联方类型',
    '期初未审', '期初AJE', '期初RJE', '期初审定',
    '借方发生', '贷方发生', '期末余额', '重分类', '期末未审',
    '期末AJE', '期末RJE', '期末审定',
    '信用风险组合方式', '组合名称', '是否函证', '期后回款', '备注',
]


def get_d2_2_columns(segments: list[Any]) -> list[str]:
    """D2-2 明细表动态列头（Task 12.1）。

    3 期账龄（期初/期末未审/期末审定），每期 N 段，账龄列头由项目账龄配置派生。
    列头顺序遵循 segments 顺序，格式 `{label}({period_label})`。
    """
    prior = [f"{s.label}({AGING_PERIOD_LABELS['prior']})" for s in segments]
    current = [f"{s.label}({AGING_PERIOD_LABELS['current']})" for s in segments]
    audited = [f"{s.label}({AGING_PERIOD_LABELS['audited']})" for s in segments]
    return [
        '序号', '客户名称', '公司代码', '关联方类型',
        '期初未审', '期初AJE', '期初RJE', '期初审定',
        *prior,
        '借方发生', '贷方发生', '期末余额', '重分类', '期末未审',
        *current,
        '期末AJE', '期末RJE', '期末审定',
        *audited,
        '信用风险组合方式', '组合名称', '是否函证', '期后回款', '备注',
    ]


def _d2_2_export_values(row: dict, segments: list[Any]) -> list[Any]:
    """D2-2 动态导出行值（读取嵌套 agingPrior/agingCurrent/agingAudited，按 segments 顺序）。Task 12.1。"""
    def _period_vals(field: str) -> list[Any]:
        bucket = row.get(field) or {}
        return [safe_float(bucket.get(s.key)) if isinstance(bucket, dict) else '' for s in segments]

    return [
        row.get('seq', ''), row.get('customerName', ''), row.get('companyCode', ''), row.get('relationType', ''),
        row.get('priorUnadjusted', ''), row.get('priorAje', ''), row.get('priorRje', ''), row.get('priorAudited', ''),
        *_period_vals('agingPrior'),
        row.get('debitOccurrence', ''), row.get('creditOccurrence', ''), row.get('endBalance', ''),
        row.get('reclassification', ''), row.get('currentUnadjusted', ''),
        *_period_vals('agingCurrent'),
        row.get('currentAje', ''), row.get('currentRje', ''), row.get('currentAudited', ''),
        *_period_vals('agingAudited'),
        row.get('creditRiskClassification', ''), row.get('groupName', ''),
        '是' if row.get('isConfirmation') else '', row.get('postPayment', ''), row.get('remark', ''),
    ]


SHEET_ITEM_ID_MAP: dict[str, str] = {
    'D2-2': 'D2-detail-rows',
    'D2-4': 'D2-entry-rows',
    'D2-6': 'D2-related-party-rows',
    'D2-7': 'D2-voucher-samples',
    'D2-9': 'D2-ecl-single-rows',
    'D2-10': 'D2-ecl-migration-matrix',
}

# 多 key 落库 sheet（导入分流 / 导出合并）
D2_3_CATEGORY_MAP: dict[str, str] = {
    '单项计提': 'individual',
    '账龄组合': 'aging',
    '客户类型组合': 'customer-type',
}
D2_3_ITEM_IDS: dict[str, str] = {
    'individual': 'D2-bd-individual-rows',
    'aging': 'D2-bd-aging-rows',
    'customer-type': 'D2-bd-customer-rows',
}
D2_3_FIXED_LABELS: dict[str, str] = {
    'individual': '按单项计提小计',
    'aging': '按账龄组合计提小计',
    'customer-type': '按客户类型组合计提小计',
}
D2_3_EXPORT_CATEGORY: dict[str, str] = {
    v: k for k, v in D2_3_CATEGORY_MAP.items()
}

D2_11_SECTION_MAP: dict[str, str] = {
    '转回': 'reversal',
    '核销': 'writeoff',
}
D2_11_ITEM_IDS: dict[str, str] = {
    'reversal': 'D2-writeoff-reversal-rows',
    'writeoff': 'D2-writeoff-writeoff-rows',
}

D2_12_TYPE_MAP: dict[str, str] = {
    '质押': 'pledge',
    '保理': 'factoring',
}
D2_12_ITEM_IDS: dict[str, str] = {
    'pledge': 'D2-pledge-rows',
    'factoring': 'D2-factoring-rows',
}

D2_8_ITEM_IDS: dict[str, str] = {
    'paragraphs': 'D2-policy-paragraphs',
    'historical': 'D2-policy-historical-matrix',
    'migration': 'D2-policy-migration-matrix',
}

D2_13_ITEM_IDS: dict[str, str] = {
    'judgments': 'D2-bizmodel-judgments',
    'groups': 'D2-bizmodel-groups',
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _validate_sheet(sheet: str) -> None:
    if sheet not in VALID_SHEETS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的sheet: {sheet}。支持: {', '.join(sorted(VALID_SHEETS))}"
        )


def _create_template_workbook(sheet: str, segments: list[Any] | None = None) -> "Workbook":
    wb = Workbook()
    ws = wb.active
    ws.title = sheet

    # D2-2 明细表：账龄列头按项目账龄配置动态生成（Task 12.1）
    if sheet == 'D2-2':
        columns = get_d2_2_columns(segments or [])
    else:
        columns = SHEET_COLUMNS[sheet]
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(
        start_color="D9E1F2", end_color="D9E1F2", fill_type="solid"
    )
    header_align = Alignment(
        horizontal="center", vertical="center", wrap_text=True
    )

    for col_idx, col_name in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        ws.column_dimensions[cell.column_letter].width = max(
            len(col_name) * 2 + 4, 12
        )

    ws.freeze_panes = "A2"

    if sheet == 'D2-1':
        for row_key, label in _D2_1_ROWS:
            ws.append([row_key, label] + [None] * (len(columns) - 2))

    return wb


def _validate_columns(ws: Any, sheet: str) -> list[str]:
    """校验列名，返回不匹配的列名列表。

    D2-2：校验固定基础列（_D2_2_BASE_COLUMNS），账龄列（形如 `1年以内(期初)`）按 label
    动态匹配，不作为非法列（Task 12.2）。
    """
    if sheet == 'D2-2':
        expected = set(_D2_2_BASE_COLUMNS)
    else:
        expected = set(SHEET_COLUMNS[sheet])
    actual: list[str] = []
    for cell in ws[1]:
        if cell.value is not None:
            actual.append(str(cell.value).strip())

    invalid = [
        col for col in actual
        if col not in expected and not (sheet == 'D2-2' and _looks_like_aging(col))
    ]
    if len(actual) < 3:
        invalid.append('列数不足(至少需要3列)')
    return invalid


def _parse_rows(ws: Any, sheet: str) -> tuple[list[dict], str | None]:
    """解析数据行为 dict 列表，超500行截断。

    D2-2 保留全部实际列（含动态账龄列），供 _parse_d2_2_rows 按 label 匹配。
    """
    columns = None if sheet == 'D2-2' else SHEET_COLUMNS[sheet]
    actual_cols: list[str] = []
    for cell in ws[1]:
        if cell.value is not None:
            actual_cols.append(str(cell.value).strip())
        else:
            actual_cols.append('')

    rows: list[dict] = []
    warning: str | None = None
    row_count = 0

    for row in ws.iter_rows(min_row=2, values_only=True):
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
                if col_name and (columns is None or col_name in columns):
                    row_dict[col_name] = val if val is not None else ''
        rows.append(row_dict)

    return rows, warning


def _yes_no(val: Any) -> bool:
    s = safe_str(val).lower()
    return s in ('是', 'yes', 'true', '1', 'y')


def _parse_d2_2_rows(rows: list[dict], segments: list[Any] | None = None) -> list[dict]:
    """解析 D2-2 明细行 → nested keyed 结构（agingPrior/agingCurrent/agingAudited）。Task 12.2。

    账龄列按 label 匹配当前项目账龄配置（segments），格式 `{label}({period_label})`，
    不再写入 legacy flat 字段（priorAging1Year 等）。segments 为空时账龄容器为空对象。
    """
    segs = segments or []
    periods = subject_aging_periods('D2')  # [prior, current, audited]
    out: list[dict] = []
    for i, r in enumerate(rows, start=1):
        prior_u = safe_float(r.get('期初未审'))
        prior_a = safe_float(r.get('期初AJE'))
        prior_r = safe_float(r.get('期初RJE'))
        cur_u = safe_float(r.get('期末未审'))
        cur_a = safe_float(r.get('账项调整(AJE)')) or safe_float(r.get('期末AJE'))
        cur_r = safe_float(r.get('重分类调整(RJE)')) or safe_float(r.get('期末RJE'))
        aging_nested, _unmatched = match_import_aging(
            lambda h: r.get(h), list(r.keys()), segs, periods,
        )
        out.append({
            'rowId': str(uuid4()),
            'seq': int(safe_float(r.get('序号'))) or i,
            'customerName': safe_str(r.get('客户名称')),
            'companyCode': safe_str(r.get('公司代码')),
            'relationType': safe_str(r.get('关联方类型')) or '非关联方',
            'priorUnadjusted': prior_u,
            'priorAje': prior_a,
            'priorRje': prior_r,
            'priorAudited': safe_float(r.get('期初审定')) or (prior_u + prior_a + prior_r),
            'debitOccurrence': safe_float(r.get('借方发生')),
            'creditOccurrence': safe_float(r.get('贷方发生')),
            'endBalance': safe_float(r.get('期末余额')),
            'reclassification': safe_float(r.get('重分类')),
            'currentUnadjusted': cur_u,
            'currentAje': cur_a,
            'currentRje': cur_r,
            'currentAudited': safe_float(r.get('期末审定')) or (cur_u + cur_a + cur_r),
            'creditRiskClassification': safe_str(r.get('信用风险组合方式')),
            'groupName': safe_str(r.get('组合名称')),
            'isConfirmation': _yes_no(r.get('是否函证')),
            'postPayment': safe_float(r.get('期后回款')),
            'remark': safe_str(r.get('备注')),
            **aging_nested,
        })
    return out


def _d2_2_skipped_aging_columns(rows: list[dict], segments: list[Any] | None) -> list[str]:
    """检测 D2-2 导入行中不匹配当前账龄配置的账龄列（Task 12.2，Requirement 8.3）。"""
    all_headers: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k and k not in seen:
                seen.add(k)
                all_headers.append(k)
    _, unmatched = match_import_aging(
        lambda _h: None, all_headers, segments or [], subject_aging_periods('D2'),
    )
    return unmatched


def _create_fixed_d2_3_row(category: str) -> dict:
    return {
        'rowId': f'fixed-{category}',
        'category': category,
        'label': D2_3_FIXED_LABELS[category],
        'isSubRow': False,
        'isFixed': True,
        'priorUnadjusted': 0,
        'priorAje': 0,
        'priorRje': 0,
        'priorAudited': 0,
        'currentProvision': 0,
        'currentTransferIn': 0,
        'currentRecovery': 0,
        'currentReversal': 0,
        'currentWriteOff': 0,
        'currentUnadjusted': 0,
        'currentAje': 0,
        'currentRje': 0,
        'currentAudited': 0,
    }


def _parse_d2_3_row(r: dict, category: str) -> dict:
    label = safe_str(r.get('项目'))
    fixed_label = D2_3_FIXED_LABELS.get(category, '')
    is_fixed = label == fixed_label or '小计' in label
    prior_audited = safe_float(r.get('期初审定'))
    current_unadjusted = safe_float(r.get('期末未审'))
    current_aje = safe_float(r.get('期末AJE'))
    current_rje = safe_float(r.get('期末RJE'))
    current_audited = safe_float(r.get('期末审定'))
    if not current_audited and (current_unadjusted or current_aje or current_rje):
        current_audited = current_unadjusted + current_aje + current_rje
    return {
        'rowId': f'fixed-{category}' if is_fixed else str(uuid4()),
        'category': category,
        'label': label or fixed_label,
        'isSubRow': not is_fixed,
        'isFixed': is_fixed,
        'priorUnadjusted': 0,
        'priorAje': 0,
        'priorRje': 0,
        'priorAudited': prior_audited,
        'currentProvision': safe_float(r.get('本期计提')),
        'currentTransferIn': safe_float(r.get('本期转入')),
        'currentRecovery': safe_float(r.get('本期收回')),
        'currentReversal': safe_float(r.get('本期转回')),
        'currentWriteOff': safe_float(r.get('本期核销')),
        'currentUnadjusted': current_unadjusted,
        'currentAje': current_aje,
        'currentRje': current_rje,
        'currentAudited': current_audited,
    }


def _parse_d2_3_by_category(rows: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {cat: [] for cat in D2_3_ITEM_IDS}
    for r in rows:
        cat_label = safe_str(r.get('分类'))
        category = D2_3_CATEGORY_MAP.get(cat_label)
        if not category:
            continue
        buckets[category].append(_parse_d2_3_row(r, category))
    result: dict[str, list[dict]] = {}
    for category, item_id in D2_3_ITEM_IDS.items():
        cat_rows = buckets[category]
        if not any(row.get('isFixed') for row in cat_rows):
            cat_rows.insert(0, _create_fixed_d2_3_row(category))
        result[item_id] = cat_rows
    return result


def _parse_d2_6_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        prior = safe_float(r.get('期初余额'))
        debit = safe_float(r.get('借方发生'))
        credit = safe_float(r.get('贷方发生'))
        end_bal = safe_float(r.get('期末余额')) or (prior + debit - credit)
        bad_debt = safe_float(r.get('坏账准备'))
        book_val = safe_float(r.get('账面价值')) or (end_bal - bad_debt)
        out.append({
            'rowId': str(uuid4()),
            'debtorName': safe_str(r.get('关联方名称')),
            'relationType': safe_str(r.get('关系')),
            'transactionType': safe_str(r.get('交易内容')),
            'priorBalance': prior,
            'debitAmount': debit,
            'creditAmount': credit,
            'endBalance': end_bal,
            'badDebtProvision': bad_debt,
            'bookValue': book_val,
            'isArmsLength': safe_str(r.get('定价政策')),
            'remark': safe_str(r.get('备注')),
        })
    return out


def _parse_d2_11_by_section(rows: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {'reversal': [], 'writeoff': []}
    for i, r in enumerate(rows, start=1):
        section_label = safe_str(r.get('类别'))
        section = D2_11_SECTION_MAP.get(section_label)
        if not section:
            continue
        buckets[section].append({
            'rowId': str(uuid4()),
            'section': section,
            'debtorName': safe_str(r.get('单位名称')),
            'amount': safe_float(r.get('金额')),
            'originalDate': '',
            'reason': safe_str(r.get('原因')),
            'approvalDoc': safe_str(r.get('方式')),
            'isReasonable': safe_str(r.get('合理性分析')),
            'auditorComment': safe_str(r.get('备注')),
            'indexRef': safe_str(r.get('序号')) or str(i),
        })
    return {
        D2_11_ITEM_IDS['reversal']: buckets['reversal'],
        D2_11_ITEM_IDS['writeoff']: buckets['writeoff'],
    }


def _parse_d2_12_by_type(rows: list[dict]) -> dict[str, list[dict]]:
    pledge_rows: list[dict] = []
    factoring_rows: list[dict] = []
    for i, r in enumerate(rows, start=1):
        type_label = safe_str(r.get('类别'))
        row_type = D2_12_TYPE_MAP.get(type_label)
        if row_type == 'pledge':
            pledge_rows.append({
                'rowId': str(uuid4()),
                'debtorName': safe_str(r.get('客户名称')),
                'pledgeAmount': safe_float(r.get('金额')),
                'pledgeDate': safe_str(r.get('起始日期')),
                'pledgee': safe_str(r.get('对手方')),
                'pledgePurpose': safe_str(r.get('合同编号')),
                'expiryDate': safe_str(r.get('到期日期')),
                'status': '有效',
                'remark': safe_str(r.get('备注')),
                'indexRef': safe_str(r.get('序号')) or str(i),
            })
        elif row_type == 'factoring':
            risk = _yes_no(r.get('风险转移'))
            control = _yes_no(r.get('控制保留'))
            derecognition = safe_str(r.get('终止确认'))
            if not derecognition:
                if risk:
                    derecognition = '终止确认'
                elif not risk and not control:
                    derecognition = '终止确认'
                else:
                    derecognition = '继续确认'
            factoring_rows.append({
                'rowId': str(uuid4()),
                'debtorName': safe_str(r.get('客户名称')),
                'factoringAmount': safe_float(r.get('金额')),
                'factoringDate': safe_str(r.get('起始日期')),
                'factor': safe_str(r.get('对手方')),
                'riskTransferred': risk,
                'controlRetained': control,
                'derecognition': derecognition,
                'remark': safe_str(r.get('备注')),
            })
    return {
        D2_12_ITEM_IDS['pledge']: pledge_rows,
        D2_12_ITEM_IDS['factoring']: factoring_rows,
    }


def _normalize_entry_type(val: Any) -> str:
    s = safe_str(val).upper()
    return 'RJE' if s in ('RJE', '重分类', '重分类调整') else 'AJE'


def _yn_to_flag(val: Any) -> str:
    if _yes_no(val):
        return 'Y'
    s = safe_str(val).upper()
    if s in ('N', '否', 'NO', 'FALSE', '0'):
        return 'N'
    return safe_str(val)


def _flag_to_yn(val: Any) -> str:
    s = safe_str(val).upper()
    if s in ('Y', '是', 'YES', 'TRUE', '1'):
        return '是'
    if s in ('N', '否', 'NO', 'FALSE', '0'):
        return '否'
    return safe_str(val)


def _parse_d2_4_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for i, r in enumerate(rows, start=1):
        debit_acct = safe_str(r.get('借方科目'))
        credit_acct = safe_str(r.get('贷方科目'))
        acct_name = debit_acct or credit_acct
        note_item = credit_acct if debit_acct and credit_acct and debit_acct != credit_acct else ''
        remark_parts: list[str] = []
        if safe_str(r.get('日期')):
            remark_parts.append(f"日期:{safe_str(r.get('日期'))}")
        if safe_str(r.get('编制人')):
            remark_parts.append(f"编制人:{safe_str(r.get('编制人'))}")
        base_remark = safe_str(r.get('备注'))
        if base_remark:
            remark_parts.append(base_remark)
        out.append({
            'rowId': str(uuid4()),
            'description': safe_str(r.get('摘要')),
            'entryType': _normalize_entry_type(r.get('类型')),
            'reportItem': '',
            'accountName': acct_name,
            'noteItem': note_item,
            'debitAmount': safe_float(r.get('借方金额')),
            'creditAmount': safe_float(r.get('贷方金额')),
            'indexRef': safe_str(r.get('序号')) or str(i),
            'remark': ' | '.join(remark_parts),
        })
    return out


def _parse_d2_7_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for i, r in enumerate(rows, start=1):
        debit = safe_float(r.get('借方金额'))
        credit = safe_float(r.get('贷方金额'))
        amount = debit or credit
        period_raw = safe_str(r.get('记录期间正确'))
        is_cutoff = bool(period_raw) and not _yes_no(period_raw)
        abnormal_raw = safe_str(r.get('是否异常'))
        remark = safe_str(r.get('异常说明')) or safe_str(r.get('备注'))
        out.append({
            'rowId': str(uuid4()),
            'seq': int(safe_float(r.get('序号'))) or i,
            'voucherNo': safe_str(r.get('凭证编号')),
            'voucherDate': safe_str(r.get('日期')),
            'amount': amount,
            'counterparty': safe_str(r.get('客户名称')),
            'abstract': safe_str(r.get('业务内容')),
            'accountName': safe_str(r.get('对方科目')),
            'attachmentCount': 0,
            'hasOriginal': _yn_to_flag(r.get('原始凭证齐全')),
            'amountConsistent': _yn_to_flag(r.get('记账凭证相符')),
            'dateConsistent': _yn_to_flag(r.get('账务处理正确')),
            'revenueDate': safe_str(r.get('日期')),
            'isCutoff': is_cutoff,
            'customerConfirm': '',
            'agingVerify': safe_str(r.get('其他')),
            'abnormalFlag': _yn_to_flag(abnormal_raw) if abnormal_raw else '',
            'conclusion': safe_str(r.get('结论')),
            'indexRef': safe_str(r.get('序号')) or str(i),
            'remark': remark,
        })
    return out


def _parse_d2_9_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for i, r in enumerate(rows, start=1):
        balance = safe_float(r.get('审定账面余额'))
        rate = safe_float(r.get('预期信用损失率'))
        should = safe_float(r.get('应计提金额')) or balance * rate
        actual = safe_float(r.get('实际计提金额'))
        out.append({
            'rowId': str(uuid4()),
            'debtorName': safe_str(r.get('债务人名称')),
            'auditedBalance': balance,
            'expectedLossRate': rate,
            'shouldProvision': should,
            'actualBalance': actual,
            'difference': safe_float(r.get('差异')) or (actual - should),
            'basis': safe_str(r.get('计提依据')),
            'indexRef': safe_str(r.get('序号')) or str(i),
        })
    return out


def _parse_d2_10_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        y1 = safe_float(r.get('年度1迁徙率'))
        y2 = safe_float(r.get('年度2迁徙率'))
        y3 = safe_float(r.get('年度3迁徙率'))
        avg = (y1 + y2 + y3) / 3 if (y1 or y2 or y3) else 0
        out.append({
            'rowId': str(uuid4()),
            'agingBand': safe_str(r.get('账龄段')),
            'year1Rate': y1,
            'year2Rate': y2,
            'year3Rate': y3,
            'avgRate': avg,
            'expectedLossRate': y1 * y2 * y3,
        })
    return out


def _parse_d2_8_rows(rows: list[dict]) -> dict[str, list[dict]]:
    paragraphs: list[dict] = []
    historical: list[dict] = []
    migration: list[dict] = []
    for r in rows:
        row_type = safe_str(r.get('记录类型')).lower()
        key = safe_str(r.get('段落ID/账龄段'))
        if row_type == 'paragraph':
            paragraphs.append({
                'paragraphId': key,
                'title': safe_str(r.get('标题')),
                'policyDescription': safe_str(r.get('政策条款')),
                'actualSituation': safe_str(r.get('实际情况')),
                'auditorEvaluation': safe_str(r.get('审计师评价')),
                'conclusion': safe_str(r.get('结论')),
            })
        elif row_type == 'historical':
            historical.append({
                'rowId': str(uuid4()),
                'agingBand': key,
                'balanceY1': safe_float(r.get('余额Y1')),
                'balanceY2': safe_float(r.get('余额Y2')),
                'balanceY3': safe_float(r.get('余额Y3')),
                'lossY1': safe_float(r.get('损失Y1')),
                'lossY2': safe_float(r.get('损失Y2')),
                'lossY3': safe_float(r.get('损失Y3')),
            })
        elif row_type == 'migration':
            migration.append({
                'rowId': str(uuid4()),
                'agingBand': key,
                'year1Rate': safe_float(r.get('迁徙率Y1')),
                'year2Rate': safe_float(r.get('迁徙率Y2')),
                'year3Rate': safe_float(r.get('迁徙率Y3')),
            })
    return {
        D2_8_ITEM_IDS['paragraphs']: paragraphs,
        D2_8_ITEM_IDS['historical']: historical,
        D2_8_ITEM_IDS['migration']: migration,
    }


def _parse_d2_13_rows(rows: list[dict]) -> dict[str, list[dict]]:
    judgments: list[dict] = []
    groups: list[dict] = []
    for r in rows:
        row_type = safe_str(r.get('记录类型')).lower()
        key = safe_str(r.get('问题ID/行ID'))
        if row_type == 'judgment':
            judgments.append({
                'questionId': key,
                'question': safe_str(r.get('问题')),
                'answer': safe_str(r.get('回答')),
                'explanation': safe_str(r.get('说明')),
            })
        elif row_type == 'group':
            groups.append({
                'rowId': key or str(uuid4()),
                'groupName': safe_str(r.get('组合名称')),
                'bizModel': safe_str(r.get('业务模式')),
                'sppiResult': safe_str(r.get('SPPI结果')),
                'measurementBasis': safe_str(r.get('计量基础')),
                'remark': safe_str(r.get('备注')),
            })
    return {
        D2_13_ITEM_IDS['judgments']: judgments,
        D2_13_ITEM_IDS['groups']: groups,
    }


def _rows_to_storage_map(
    sheet: str, rows: list[dict], segments: list[Any] | None = None
) -> dict[str, list[dict]]:
    """解析导入行并映射为 item_id → rows（单 key sheet 亦返回单元素 dict）。"""
    if sheet == 'D2-2':
        return {SHEET_ITEM_ID_MAP['D2-2']: _parse_d2_2_rows(rows, segments)}
    if sheet == 'D2-3':
        return _parse_d2_3_by_category(rows)
    if sheet == 'D2-4':
        return {SHEET_ITEM_ID_MAP['D2-4']: _parse_d2_4_rows(rows)}
    if sheet == 'D2-6':
        return {SHEET_ITEM_ID_MAP['D2-6']: _parse_d2_6_rows(rows)}
    if sheet == 'D2-7':
        return {SHEET_ITEM_ID_MAP['D2-7']: _parse_d2_7_rows(rows)}
    if sheet == 'D2-9':
        return {SHEET_ITEM_ID_MAP['D2-9']: _parse_d2_9_rows(rows)}
    if sheet == 'D2-10':
        return {SHEET_ITEM_ID_MAP['D2-10']: _parse_d2_10_rows(rows)}
    if sheet == 'D2-8':
        return _parse_d2_8_rows(rows)
    if sheet == 'D2-13':
        return _parse_d2_13_rows(rows)
    if sheet == 'D2-11':
        return _parse_d2_11_by_section(rows)
    if sheet == 'D2-12':
        return _parse_d2_12_by_type(rows)
    return {'D2-import-fallback': [{**r, 'rowId': str(uuid4())} for r in rows]}


def _load_stored_rows(sheet: str, stored_by_key: dict[str, list[dict]]) -> list[dict]:
    """合并多 key 存储为导出行列表（附带分类/类别字段）。"""
    if sheet == 'D2-3':
        flat: list[dict] = []
        for category, item_id in D2_3_ITEM_IDS.items():
            for row in stored_by_key.get(item_id, []):
                flat.append({**row, '_exportCategory': D2_3_EXPORT_CATEGORY.get(category, '')})
        return flat
    if sheet == 'D2-11':
        flat = []
        for section, item_id in D2_11_ITEM_IDS.items():
            label = '转回' if section == 'reversal' else '核销'
            for row in stored_by_key.get(item_id, []):
                flat.append({**row, '_exportSection': label})
        return flat
    if sheet == 'D2-12':
        flat = []
        for row_type, item_id in D2_12_ITEM_IDS.items():
            label = '质押' if row_type == 'pledge' else '保理'
            for row in stored_by_key.get(item_id, []):
                flat.append({**row, '_exportType': label})
        return flat
    if sheet == 'D2-8':
        flat = []
        for row in stored_by_key.get(D2_8_ITEM_IDS['paragraphs'], []):
            flat.append({**row, '_exportType': 'paragraph'})
        for row in stored_by_key.get(D2_8_ITEM_IDS['historical'], []):
            flat.append({**row, '_exportType': 'historical'})
        for row in stored_by_key.get(D2_8_ITEM_IDS['migration'], []):
            flat.append({**row, '_exportType': 'migration'})
        return flat
    if sheet == 'D2-13':
        flat = []
        for row in stored_by_key.get(D2_13_ITEM_IDS['judgments'], []):
            flat.append({**row, '_exportType': 'judgment'})
        for row in stored_by_key.get(D2_13_ITEM_IDS['groups'], []):
            flat.append({**row, '_exportType': 'group'})
        return flat
    item_id = SHEET_ITEM_ID_MAP.get(sheet)
    if item_id:
        return stored_by_key.get(item_id, [])
    return []


def _sheet_storage_keys(sheet: str) -> list[str]:
    if sheet == 'D2-3':
        return list(D2_3_ITEM_IDS.values())
    if sheet == 'D2-11':
        return list(D2_11_ITEM_IDS.values())
    if sheet == 'D2-12':
        return list(D2_12_ITEM_IDS.values())
    if sheet == 'D2-8':
        return list(D2_8_ITEM_IDS.values())
    if sheet == 'D2-13':
        return list(D2_13_ITEM_IDS.values())
    item_id = SHEET_ITEM_ID_MAP.get(sheet)
    return [item_id] if item_id else []


def _export_row_values(sheet: str, row: dict) -> list[Any]:
    if sheet == 'D2-2':
        return [
            row.get('seq', ''), row.get('customerName', ''), row.get('companyCode', ''),
            row.get('relationType', ''), row.get('priorUnadjusted', ''), row.get('priorAje', ''),
            row.get('priorRje', ''), row.get('priorAudited', ''),
            row.get('priorAging1Year', ''), row.get('priorAging1to2', ''), row.get('priorAging2to3', ''),
            row.get('priorAging3to4', ''), row.get('priorAging4to5', ''), row.get('priorAgingOver5', ''),
            row.get('debitOccurrence', ''), row.get('creditOccurrence', ''), row.get('endBalance', ''),
            row.get('reclassification', ''), row.get('currentUnadjusted', ''),
            row.get('currentAging1Year', ''), row.get('currentAging1to2', ''), row.get('currentAging2to3', ''),
            row.get('currentAging3to4', ''), row.get('currentAging4to5', ''), row.get('currentAgingOver5', ''),
            row.get('currentAje', ''), row.get('currentRje', ''), row.get('currentAudited', ''),
            row.get('auditedAging1Year', ''), row.get('auditedAging1to2', ''), row.get('auditedAging2to3', ''),
            row.get('auditedAging3to4', ''), row.get('auditedAging4to5', ''), row.get('auditedAgingOver5', ''),
            row.get('creditRiskClassification', ''), row.get('groupName', ''),
            '是' if row.get('isConfirmation') else '', row.get('postPayment', ''), row.get('remark', ''),
        ]
    if sheet == 'D2-9':
        return [
            row.get('indexRef', ''), row.get('debtorName', ''), row.get('auditedBalance', ''),
            row.get('expectedLossRate', ''), row.get('shouldProvision', ''), row.get('actualBalance', ''),
            row.get('difference', ''), row.get('basis', ''), row.get('remark', ''),
        ]
    if sheet == 'D2-10':
        return [
            row.get('indexRef', ''), row.get('agingBand', ''), row.get('year1Rate', ''),
            row.get('year2Rate', ''), row.get('year3Rate', ''), row.get('remark', ''),
        ]
    if sheet == 'D2-4':
        debit_acct = row.get('accountName', '')
        credit_acct = row.get('noteItem', '') or debit_acct
        return [
            row.get('indexRef', ''), row.get('entryType', ''),
            debit_acct if row.get('debitAmount') else '',
            credit_acct if row.get('creditAmount') else credit_acct,
            row.get('debitAmount', ''), row.get('creditAmount', ''),
            row.get('description', ''), '', '', row.get('remark', ''),
        ]
    if sheet == 'D2-7':
        amount = row.get('amount', 0)
        return [
            row.get('seq', ''), row.get('counterparty', ''), row.get('voucherDate', ''),
            row.get('voucherNo', ''), row.get('abstract', ''), row.get('accountName', ''),
            amount, 0,
            _flag_to_yn(row.get('hasOriginal', '')),
            _flag_to_yn(row.get('amountConsistent', '')),
            _flag_to_yn(row.get('dateConsistent', '')),
            '否' if row.get('isCutoff') else '是',
            row.get('agingVerify', ''),
            _flag_to_yn(row.get('abnormalFlag', '')),
            row.get('remark', ''), row.get('conclusion', ''), row.get('remark', ''),
        ]
    if sheet == 'D2-3':
        return [
            row.get('label', ''),
            row.get('_exportCategory') or D2_3_EXPORT_CATEGORY.get(row.get('category', ''), ''),
            row.get('priorAudited', ''), row.get('currentProvision', ''),
            row.get('currentTransferIn', ''), row.get('currentRecovery', ''),
            row.get('currentReversal', ''), row.get('currentWriteOff', ''),
            row.get('currentUnadjusted', ''), row.get('currentAje', ''),
            row.get('currentRje', ''), row.get('currentAudited', ''),
        ]
    if sheet == 'D2-6':
        return [
            '', row.get('debtorName', ''), row.get('relationType', ''),
            row.get('priorBalance', ''), row.get('debitAmount', ''),
            row.get('creditAmount', ''), row.get('endBalance', ''),
            row.get('badDebtProvision', ''), row.get('bookValue', ''),
            row.get('transactionType', ''), row.get('isArmsLength', ''),
            row.get('remark', ''),
        ]
    if sheet == 'D2-11':
        return [
            row.get('indexRef', ''), row.get('_exportSection', ''),
            row.get('debtorName', ''), row.get('reason', ''),
            row.get('approvalDoc', ''), row.get('amount', ''),
            '', row.get('isReasonable', ''), row.get('auditorComment', ''),
        ]
    if sheet == 'D2-12':
        if row.get('_exportType') == '保理' or row.get('factoringAmount') is not None:
            return [
                row.get('indexRef', ''), '保理', row.get('debtorName', ''),
                row.get('factoringAmount', ''), row.get('factor', ''),
                '', row.get('factoringDate', ''), row.get('expiryDate', ''),
                '是' if row.get('riskTransferred') else '否',
                '是' if row.get('controlRetained') else '否',
                row.get('derecognition', ''), row.get('remark', ''),
            ]
        return [
            row.get('indexRef', ''), '质押', row.get('debtorName', ''),
            row.get('pledgeAmount', ''), row.get('pledgee', ''),
            row.get('pledgePurpose', ''), row.get('pledgeDate', ''),
            row.get('expiryDate', ''), '', '', '', row.get('remark', ''),
        ]
    if sheet == 'D2-8':
        t = row.get('_exportType', '')
        if t == 'paragraph':
            return [
                'paragraph', row.get('paragraphId', ''), row.get('title', ''), row.get('policyDescription', ''),
                row.get('actualSituation', ''), row.get('auditorEvaluation', ''), row.get('conclusion', ''),
                '', '', '', '', '', '', '', '', '',
            ]
        if t == 'historical':
            return [
                'historical', row.get('agingBand', ''), '', '', '', '', '',
                row.get('balanceY1', ''), row.get('balanceY2', ''), row.get('balanceY3', ''),
                row.get('lossY1', ''), row.get('lossY2', ''), row.get('lossY3', ''),
                '', '', '',
            ]
        return [
            'migration', row.get('agingBand', ''), '', '', '', '', '',
            '', '', '', '', '', '',
            row.get('year1Rate', ''), row.get('year2Rate', ''), row.get('year3Rate', ''),
        ]
    if sheet == 'D2-13':
        t = row.get('_exportType', '')
        if t == 'judgment':
            return [
                'judgment', row.get('questionId', ''), row.get('question', ''), row.get('answer', ''),
                row.get('explanation', ''), '', '', '', '', '',
            ]
        return [
            'group', row.get('rowId', ''), '', '', '',
            row.get('groupName', ''), row.get('bizModel', ''), row.get('sppiResult', ''),
            row.get('measurementBasis', ''), row.get('remark', ''),
        ]
    return list(row.values())


# ─── D2-1 审定表 per-cell 导入导出 ───────────────────────────────────────────

async def _fetch_d2_adj_map(db: AsyncSession, wp_id: str) -> dict[str, str]:
    import sqlalchemy as sa
    result = await db.execute(
        sa.text(
            "SELECT item_id, remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id LIKE 'D2-adj-%'"
        ),
        {"wp_id": wp_id},
    )
    return {row.item_id: (row.remark or "") for row in result.fetchall()}


async def _upsert_d2_adj_cell(
    db: AsyncSession, wp_id: str, item_id: str, remark: str,
) -> None:
    import sqlalchemy as sa
    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses (id, wp_id, item_id, remark, updated_at)
            VALUES (:id, :wp_id, :item_id, :remark, NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET remark = :remark, updated_at = NOW()
        """),
        {"id": str(uuid4()), "wp_id": wp_id, "item_id": item_id, "remark": remark},
    )


def _parse_d2_1_row(row: tuple, columns: list[str]) -> dict | None:
    def col(name: str) -> Any:
        try:
            idx = columns.index(name)
            return row[idx] if idx < len(row) else None
        except ValueError:
            return None

    row_key = safe_str(col('行键'))
    label = safe_str(col('项目'))
    if not row_key and not label:
        return None
    if row_key == 'total':
        return None
    if not row_key:
        for rk, lbl in _D2_1_ROWS:
            if lbl == label:
                row_key = rk
                break
    if row_key not in {rk for rk, _ in _D2_1_ROWS}:
        return None

    parsed: dict[str, Any] = {'rowKey': row_key, 'label': label}
    for field_key, header, is_text in _D2_1_FIELDS:
        val = col(header)
        parsed[field_key] = safe_str(val) if is_text else safe_float(val)
    return parsed


async def _export_d2_1_data(
    wp_id: str, db: AsyncSession,
) -> StreamingResponse:
    responses = await _fetch_d2_adj_map(db, wp_id)
    wb = _create_template_workbook('D2-1')
    ws = wb.active
    for row_key, label in _D2_1_ROWS:
        values = [row_key, label]
        for field_key, _header, is_text in _D2_1_FIELDS:
            item_id = f"D2-adj-{row_key}-{field_key}"
            raw = responses.get(item_id, '')
            if is_text:
                values.append(raw)
            else:
                values.append(safe_float(raw) if raw else 0.0)
        ws.append(values)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="D2-1-data.xlsx"'},
    )


async def _import_d2_1_data(
    wp_id: str, ws: Any, db: AsyncSession,
) -> dict[str, Any]:
    columns = SHEET_COLUMNS['D2-1']
    rows_data: list[dict] = []
    field_count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None or v == '' for v in row):
            continue
        parsed = _parse_d2_1_row(row, columns)
        if not parsed:
            continue
        rows_data.append(parsed)

    for row in rows_data:
        row_key = row.get('rowKey', '')
        if not row_key:
            continue
        for field_key, _header, is_text in _D2_1_FIELDS:
            val = row.get(field_key)
            if val is None or (not is_text and val == ''):
                continue
            item_id = f"D2-adj-{row_key}-{field_key}"
            remark = str(val) if is_text else str(safe_float(val))
            await _upsert_d2_adj_cell(db, wp_id, item_id, remark)
            field_count += 1

    await db.commit()
    return {
        'code': 200,
        'message': '导入成功',
        'data': {
            'rowCount': len(rows_data),
            'fieldCount': field_count,
        },
    }


async def _export_d2_5_data(
    wp_id: str, db: AsyncSession,
) -> StreamingResponse:
    import sqlalchemy as sa

    result = await db.execute(
        sa.text(
            "SELECT item_id, remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id LIKE 'D2-analysis-%' "
            "ORDER BY item_id"
        ),
        {"wp_id": wp_id},
    )
    rows = result.fetchall()
    wb = _create_template_workbook('D2-5')
    ws = wb.active
    for r in rows:
        ws.append([r.item_id, r.remark or ''])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="D2-5-data.xlsx"'},
    )


async def _import_d2_5_data(
    wp_id: str, ws: Any, db: AsyncSession,
) -> dict[str, Any]:
    import sqlalchemy as sa

    columns = SHEET_COLUMNS['D2-5']
    rows_data: list[tuple[str, str]] = []
    row_count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None or v == '' for v in row):
            continue
        row_count += 1
        if row_count > MAX_IMPORT_ROWS:
            break
        row_dict = {columns[idx]: row[idx] if idx < len(row) else '' for idx in range(len(columns))}
        item_id = safe_str(row_dict.get('item_id'))
        if not item_id.startswith('D2-analysis-'):
            continue
        rows_data.append((item_id, safe_str(row_dict.get('值'))))

    for item_id, remark in rows_data:
        await db.execute(
            sa.text("""
                INSERT INTO checklist_responses (id, wp_id, item_id, conclusion, remark, updated_at)
                VALUES (:id, :wp_id, :item_id, NULL, :remark, NOW())
                ON CONFLICT (wp_id, item_id)
                DO UPDATE SET remark = :remark, updated_at = NOW()
            """),
            {"id": str(uuid4()), "wp_id": wp_id, "item_id": item_id, "remark": remark},
        )
    await db.commit()

    return {
        'code': 200,
        'message': '导入成功',
        'data': {
            'rowCount': len(rows_data),
            'fieldCount': len(SHEET_COLUMNS['D2-5']),
        },
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/{wp_id}/d2/export-template")
async def export_template(
    wp_id: str,
    sheet: str = Query(..., description="Sheet名称"),
    db: AsyncSession = Depends(get_db),
):
    """导出空白xlsx模板（含表头+格式）"""
    _validate_sheet(sheet)

    # D2-2 明细表：账龄列头按项目账龄配置动态生成（Task 12.1）
    segments = await resolve_aging_segments(db, wp_id, 'D2') if sheet == 'D2-2' else None
    wb = _create_template_workbook(sheet, segments)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"{sheet}-template.xlsx"
    return StreamingResponse(
        buffer,
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@router.post("/{wp_id}/d2/export-data")
async def export_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet名称"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出含当前数据的xlsx"""
    _validate_sheet(sheet)

    if sheet == 'D2-1':
        return await _export_d2_1_data(wp_id, db)
    if sheet == 'D2-5':
        return await _export_d2_5_data(wp_id, db)

    storage_keys = _sheet_storage_keys(sheet)
    stored_by_key: dict[str, list[dict]] = {}
    for key in storage_keys:
        stored_by_key[key] = await load_json_rows(db, wp_id, key, field='remark')
    stored = _load_stored_rows(sheet, stored_by_key)

    # D2-2 明细表：账龄列头/值按项目账龄配置动态生成（Task 12.1）
    segments = await resolve_aging_segments(db, wp_id, 'D2') if sheet == 'D2-2' else None
    wb = _create_template_workbook(sheet, segments)
    ws = wb.active
    for row in stored:
        if sheet == 'D2-2':
            ws.append(_d2_2_export_values(row, segments or []))
        else:
            ws.append(_export_row_values(sheet, row))

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"{sheet}-data.xlsx"
    return StreamingResponse(
        buffer,
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@router.post("/{wp_id}/d2/import-data")
async def import_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet名称"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """解析xlsx回写checklist_responses"""
    _validate_sheet(sheet)

    if not file.filename or not file.filename.endswith('.xlsx'):
        raise HTTPException(
            status_code=400, detail="仅支持 .xlsx 格式文件"
        )

    content = await file.read()
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"无法解析xlsx文件: {str(e)}"
        )

    ws = wb.active

    if sheet == 'D2-1':
        invalid_columns = _validate_columns(ws, sheet)
        if invalid_columns:
            return {
                "code": 400,
                "message": "列名不匹配",
                "data": {"invalidColumns": invalid_columns},
            }
        return await _import_d2_1_data(wp_id, ws, db)
    if sheet == 'D2-5':
        invalid_columns = _validate_columns(ws, sheet)
        if invalid_columns:
            return {
                "code": 400,
                "message": "列名不匹配",
                "data": {"invalidColumns": invalid_columns},
            }
        return await _import_d2_5_data(wp_id, ws, db)

    invalid_columns = _validate_columns(ws, sheet)
    if invalid_columns:
        return {
            "code": 400,
            "message": "列名不匹配",
            "data": {"invalid_columns": invalid_columns},
        }

    rows, warning = _parse_rows(ws, sheet)
    if not rows:
        return {
            "data": {
                "rowCount": 0,
                "fieldCount": 0,
                "warning": "文件中无有效数据行",
            }
        }

    # D2-2：解析账龄列前解析项目账龄配置 segments（Task 12.2）
    segments = await resolve_aging_segments(db, wp_id, 'D2') if sheet == 'D2-2' else None
    skipped_columns = _d2_2_skipped_aging_columns(rows, segments) if sheet == 'D2-2' else []

    storage_map = _rows_to_storage_map(sheet, rows, segments)
    for item_id, stored_rows in storage_map.items():
        await upsert_json_rows(db, wp_id, item_id, stored_rows, field='remark')

    total_rows = sum(len(v) for v in storage_map.values())
    field_count = (
        len(get_d2_2_columns(segments or [])) if sheet == 'D2-2' else len(SHEET_COLUMNS[sheet])
    )
    result: dict[str, Any] = {
        "rowCount": total_rows,
        "fieldCount": field_count,
    }
    if warning:
        result["warning"] = warning
    if skipped_columns:
        result["skipped_columns"] = skipped_columns
        result["warnings"] = [
            f"以下账龄列未匹配当前账龄配置，已跳过: {', '.join(skipped_columns)}"
        ]

    return {"data": result}
