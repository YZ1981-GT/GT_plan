"""F1 预付账款 — 导入导出（列结构对齐 HTML 底稿）."""

from __future__ import annotations

import io
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

from ._cycle_import_export_common import (
    ROW_LIMIT,
    build_workbook_template,
    col_val,
    import_rows_generic,
    load_json_rows,
    parse_upload_xlsx,
    safe_float,
    safe_str,
    upsert_json_rows,
    workbook_to_response,
)
from ._cycle_import_export_common import (
    match_import_aging,
    resolve_aging_segments,
    subject_aging_periods,
    aging_export_values,
    build_aging_headers,
)
from ._d3_import_export import (
    _D3_2_BASE_HEADERS,
    _export_d3_2_row,
    _export_d3_5_row,
    _export_d3_6_row,
    _export_d3_7_row,
    _get_headers as _d3_get_headers,
    _parse_d3_2_row,
    _parse_d3_5_row,
    _parse_d3_6_row,
    _parse_d3_7_row,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["f1-import-export"])

# F1-2 基础列（与 D3-2 同结构；账龄另按 F1 三期动态追加）
_F1_2_BASE_HEADERS: list[str] = list(_D3_2_BASE_HEADERS)


def _f1_2_dynamic_headers(segments: list[Any]) -> list[str]:
    """F1-2：基础列 + 3N 账龄列（期初/期末未审/期末审定）。"""
    return _F1_2_BASE_HEADERS + build_aging_headers(segments, subject_aging_periods("F1"))


def _export_f1_2_row_dynamic(data: dict, segments: list[Any]) -> list:
    base = [
        safe_str(data.get("customerName")),
        safe_str(data.get("companyCode")),
        safe_str(data.get("nature")),
        safe_str(data.get("relationType")),
        safe_float(data.get("priorUnadjusted")),
        safe_float(data.get("priorAdjustment")),
        safe_float(data.get("priorReclass")),
        safe_float(data.get("debit")),
        safe_float(data.get("credit")),
        safe_float(data.get("entityReclass")),
        safe_float(data.get("endAje")),
        safe_float(data.get("endRje")),
        safe_str(data.get("isConfirmed")),
        safe_float(data.get("postPeriodSettlement")),
        safe_str(data.get("remark")),
    ]
    return base + aging_export_values(data, segments, subject_aging_periods("F1"))


def _parse_f1_2_row(row: tuple, actual_headers: list[str], segments: list[Any] | None = None) -> dict:
    """解析 F1-2：支持「债权人名称」别名，账龄按 F1 三期匹配。"""
    parsed = _parse_d3_2_row(row, actual_headers, None)
    # 债权人名称 / 期后回款 / 是否函证 别名
    creditor = safe_str(col_val(row, actual_headers, "债权人名称"))
    if creditor and not parsed.get("customerName"):
        parsed["customerName"] = creditor
    post_pay = col_val(row, actual_headers, "期后回款")
    if post_pay is not None and post_pay != "":
        parsed["postPeriodSettlement"] = safe_float(post_pay)
    confirmed = safe_str(col_val(row, actual_headers, "是否函证"))
    if confirmed:
        parsed["isConfirmed"] = confirmed

    if segments:
        aging_nested, _unmatched = match_import_aging(
            lambda h: col_val(row, actual_headers, h),
            actual_headers,
            segments,
            subject_aging_periods("F1"),
        )
        parsed.update(aging_nested)
    return parsed


_F1_5_HEADERS = [
    "债务人名称",
    "期末余额",
    "账龄",
    "经济业务说明",
    "未偿还或未结转的原因",
    "计划供货还是退款",
    "是否诉讼",
    "是否转入其他应收款",
    "计提坏账准备金额",
    "审定余额",
    "期后供货或退款金额",
    "支持性证据",
    "备注",
]


def _export_f1_5_row(data: dict) -> list:
    end_balance = safe_float(data.get("endBalance"))
    bad_debt = safe_float(data.get("badDebtProvision"))
    audited = data.get("auditedBalance")
    if audited is None or audited == "":
        audited = end_balance - bad_debt
    return [
        safe_str(data.get("customerName")),
        end_balance,
        safe_str(data.get("aging")),
        safe_str(data.get("businessDescription")),
        safe_str(data.get("reason") or data.get("unsettledReason")),
        safe_str(data.get("plan")),
        safe_str(data.get("isLitigation")),
        safe_str(data.get("transferToOtherReceivable")),
        bad_debt,
        safe_float(audited),
        safe_float(
            data.get("postSettlementAmount")
            if data.get("postSettlementAmount") is not None
            else data.get("settlementAmount", data.get("settledAmount"))
        ),
        safe_str(data.get("supportingEvidence")),
        safe_str(data.get("remark")),
    ]


def _parse_f1_5_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析 F1-5：支持 Excel 13 列及旧版 8 列别名。"""
    name = safe_str(col_val(row, actual_headers, "债务人名称")) or safe_str(
        col_val(row, actual_headers, "对方单位名称")
    )
    end_balance = safe_float(col_val(row, actual_headers, "期末余额"))
    bad_debt = safe_float(col_val(row, actual_headers, "计提坏账准备金额"))
    audited_raw = col_val(row, actual_headers, "审定余额")
    audited = safe_float(audited_raw) if audited_raw not in (None, "") else end_balance - bad_debt

    reason = safe_str(col_val(row, actual_headers, "未偿还或未结转的原因")) or safe_str(
        col_val(row, actual_headers, "未结转或未偿还的原因")
    )
    plan = safe_str(col_val(row, actual_headers, "计划供货还是退款")) or safe_str(
        col_val(row, actual_headers, "处理计划")
    )
    post = col_val(row, actual_headers, "期后供货或退款金额")
    if post in (None, ""):
        post = col_val(row, actual_headers, "至审计日结转或偿还金额")

    return {
        "rowId": str(uuid4()),
        "customerName": name,
        "endBalance": end_balance,
        "aging": safe_str(col_val(row, actual_headers, "账龄")),
        "businessDescription": safe_str(col_val(row, actual_headers, "经济业务说明")),
        "reason": reason,
        "plan": plan,
        "isLitigation": safe_str(col_val(row, actual_headers, "是否诉讼")),
        "transferToOtherReceivable": safe_str(col_val(row, actual_headers, "是否转入其他应收款")),
        "badDebtProvision": bad_debt,
        "auditedBalance": audited,
        "postSettlementAmount": safe_float(post),
        "supportingEvidence": safe_str(col_val(row, actual_headers, "支持性证据")),
        "remark": safe_str(col_val(row, actual_headers, "备注")),
    }


_F1_6_HEADERS = [
    "关联方名称",
    "关联关系",
    "期初余额",
    "借方发生额",
    "贷方发生额",
    "期末余额",
    "减：坏账准备",
    "账面价值",
    "发生时间及账龄",
    "发生原因（款项性质）",
    "期后到货",
    "索引号",
    "备注",
]


def _export_f1_6_row(data: dict) -> list:
    prior = safe_float(data.get("priorBalance"))
    debit = safe_float(data.get("debit"))
    credit = safe_float(data.get("credit"))
    end_balance = data.get("endBalance")
    if end_balance is None or end_balance == "":
        end_balance = prior + debit - credit
    else:
        end_balance = safe_float(end_balance)
    bad_debt = safe_float(data.get("badDebt") or data.get("badDebtProvision"))
    book = data.get("bookValue")
    if book is None or book == "":
        book = end_balance - bad_debt
    return [
        safe_str(data.get("partyName") or data.get("customerName")),
        safe_str(data.get("relationship")),
        prior,
        debit,
        credit,
        end_balance,
        bad_debt,
        safe_float(book),
        safe_str(data.get("agingDescription")),
        safe_str(data.get("natureDescription") or data.get("nature")),
        safe_float(data.get("postPeriodDelivery") or data.get("postPeriodSettlement")),
        safe_str(data.get("indexRef")),
        safe_str(data.get("remark")),
    ]


def _parse_f1_6_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析 F1-6：支持 Excel 13 列及旧版 10 列别名。"""
    prior = safe_float(col_val(row, actual_headers, "期初余额"))
    debit = safe_float(col_val(row, actual_headers, "借方发生额"))
    if debit == 0:
        debit = safe_float(col_val(row, actual_headers, "借方发生"))
    credit = safe_float(col_val(row, actual_headers, "贷方发生额"))
    if credit == 0:
        credit = safe_float(col_val(row, actual_headers, "贷方发生"))
    end_raw = col_val(row, actual_headers, "期末余额")
    end_balance = safe_float(end_raw) if end_raw not in (None, "") else prior + debit - credit
    bad_debt = safe_float(col_val(row, actual_headers, "减：坏账准备"))
    book_raw = col_val(row, actual_headers, "账面价值")
    book = safe_float(book_raw) if book_raw not in (None, "") else end_balance - bad_debt
    nature = (
        safe_str(col_val(row, actual_headers, "发生原因（款项性质）"))
        or safe_str(col_val(row, actual_headers, "发生原因"))
        or safe_str(col_val(row, actual_headers, "款项性质"))
    )

    return {
        "rowId": str(uuid4()),
        "partyName": safe_str(col_val(row, actual_headers, "关联方名称")),
        "relationship": safe_str(col_val(row, actual_headers, "关联关系")),
        "priorBalance": prior,
        "debit": debit,
        "credit": credit,
        "endBalance": end_balance,
        "badDebt": bad_debt,
        "bookValue": book,
        "agingDescription": safe_str(col_val(row, actual_headers, "发生时间及账龄")),
        "natureDescription": nature,
        "postPeriodDelivery": safe_float(col_val(row, actual_headers, "期后到货")),
        "indexRef": safe_str(col_val(row, actual_headers, "索引号"))
        or safe_str(col_val(row, actual_headers, "索引")),
        "remark": safe_str(col_val(row, actual_headers, "备注")),
    }


_SUPPORTED_SHEETS: set[str] = {"F1-2", "F1-5", "F1-6", "F1-7", "F1-7-post"}

_SHEET_ITEM_ID: dict[str, str] = {
    "F1-2": "F1-det-rows",
    "F1-5": "F1-lt-rows",
    "F1-6": "F1-rp-rows",
    "F1-7": "F1-vc-current-rows",
    "F1-7-post": "F1-vc-post-rows",
}

_D3_SHEET_MAP: dict[str, str] = {
    "F1-2": "D3-2",
    "F1-5": "D3-5",
    "F1-6": "D3-6",
}

# F1-7 本期增减 — 比 D3-7 多「借方金额」列（对齐 F1TabComprehensiveCheck）
_F1_7_HEADERS = [
    "客户名称", "日期", "凭证编号", "业务内容", "对方科目", "对方明细科目",
    "借方金额", "贷方金额", "支持性文件",
    "核对内容1", "核对内容2", "核对内容3", "核对内容4", "核对内容5",
    "索引号", "是否异常", "备注说明",
]

_SHEET_META: dict[str, dict[str, Any]] = {
    "F1-2": {
        "title": "F1-2 预付账款明细表",
        "guidance": [
            "F1-2 预付账款明细表 编制说明",
            "",
            "列结构与 Excel F1-2 一致：债权人|关联方|款项性质|期初/发生/期末|三期账龄|函证|期后回款等。",
            "期末余额=期初审定+借方-贷方；账龄与期末余额由系统自动校验；期后回款与 F1-7 期后检查联动。",
        ],
    },
    "F1-5": {
        "title": "F1-5 账龄1年及以上大额预付账款检查表",
        "guidance": [
            "F1-5 编制说明",
            "",
            "13列对齐 Excel：债务人|期末余额|账龄|业务说明|未结转原因|计划供货/退款|"
            "是否诉讼|是否转其他应收|坏账准备|审定余额|期后供货退款|支持性证据|备注。",
            "审定余额=期末余额−坏账准备；可从 F1-2 导入超1年户。",
        ],
    },
    "F1-6": {
        "title": "F1-6 预付账款关联方及交易检查表",
        "guidance": [
            "F1-6 编制说明",
            "",
            "13列对齐 Excel：关联方|关系|期初|借方|贷方|期末|坏账准备|账面价值|"
            "发生时间及账龄|款项性质|期后到货|索引号|备注。",
            "期末=期初+借方−贷方；账面价值=期末−坏账准备；可从 F1-2 导入关联方户。",
        ],
    },
    "F1-7": {
        "title": "F1-7 预付账款检查表 — (1) 本期增减变动",
        "guidance": [
            "F1-7 本期增减 编制说明",
            "",
            "17列宽表，含借方/贷方金额；核对内容1~5填 Y/是 表示已核对。",
            "可从抽凭引擎分配样本后导出/导入。",
        ],
    },
    "F1-7-post": {
        "title": "F1-7 预付账款检查表 — (2) 期后结转检查",
        "guidance": [
            "F1-7 期后结转 编制说明",
            "",
            "16列（无借方金额列），与 F1-2 期后结转(Z列)交叉验证。",
        ],
    },
}


def _headers(sheet_code: str) -> list[str]:
    if sheet_code == "F1-7":
        return _F1_7_HEADERS
    if sheet_code == "F1-7-post":
        return _d3_get_headers("D3-7")
    if sheet_code == "F1-5":
        return _F1_5_HEADERS
    if sheet_code == "F1-6":
        return _F1_6_HEADERS
    return _d3_get_headers(_D3_SHEET_MAP[sheet_code])


def _validate_sheet(sheet_code: str) -> None:
    if sheet_code not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet_code}。支持: {sorted(_SUPPORTED_SHEETS)}")


def _export_row(sheet_code: str, data: dict) -> list:
    if sheet_code == "F1-7":
        check_items = data.get("checkItems", [False] * 5)
        return [
            safe_str(data.get("customerName")),
            safe_str(data.get("date")),
            safe_str(data.get("voucherNo")),
            safe_str(data.get("businessContent")),
            safe_str(data.get("counterAccount")),
            safe_str(data.get("counterDetailAccount")),
            safe_float(data.get("debitAmount")),
            safe_float(data.get("creditAmount")),
            safe_str(data.get("supportingDoc")),
            *["Y" if c else "" for c in (check_items + [False] * 5)[:5]],
            safe_str(data.get("indexRef")),
            safe_str(data.get("isAbnormal")),
            safe_str(data.get("remark")),
        ]
    if sheet_code == "F1-5":
        return _export_f1_5_row(data)
    if sheet_code == "F1-6":
        return _export_f1_6_row(data)
    d3 = _D3_SHEET_MAP.get(sheet_code, "D3-7")
    if d3 == "D3-2":
        return _export_d3_2_row(data)
    if d3 == "D3-5":
        return _export_d3_5_row(data)
    if d3 == "D3-6":
        return _export_d3_6_row(data)
    return _export_d3_7_row(data)


def _parse_f1_7_row(row: tuple, headers: list[str]) -> dict:
    check_items = [
        safe_str(col_val(row, headers, f"核对内容{i}")).upper() in ("Y", "是", "TRUE", "1")
        for i in range(1, 6)
    ]
    return {
        "rowId": str(uuid4()),
        "customerName": safe_str(col_val(row, headers, "客户名称")),
        "date": safe_str(col_val(row, headers, "日期")),
        "voucherNo": safe_str(col_val(row, headers, "凭证编号")),
        "businessContent": safe_str(col_val(row, headers, "业务内容")),
        "counterAccount": safe_str(col_val(row, headers, "对方科目")),
        "counterDetailAccount": safe_str(col_val(row, headers, "对方明细科目")),
        "debitAmount": safe_float(col_val(row, headers, "借方金额")),
        "creditAmount": safe_float(col_val(row, headers, "贷方金额")),
        "supportingDoc": safe_str(col_val(row, headers, "支持性文件")),
        "checkItems": check_items,
        "indexRef": safe_str(col_val(row, headers, "索引号")),
        "isAbnormal": safe_str(col_val(row, headers, "是否异常")),
        "remark": safe_str(col_val(row, headers, "备注说明")),
    }


def _parse_row(sheet_code: str, row: tuple, headers: list[str]) -> dict:
    if sheet_code == "F1-7":
        return _parse_f1_7_row(row, headers)
    if sheet_code == "F1-7-post":
        return _parse_d3_7_row(row, headers)
    if sheet_code == "F1-5":
        return _parse_f1_5_row(row, headers)
    if sheet_code == "F1-6":
        return _parse_f1_6_row(row, headers)
    d3 = _D3_SHEET_MAP[sheet_code]
    if d3 == "D3-2":
        return _parse_d3_2_row(row, headers)
    if d3 == "D3-5":
        return _parse_d3_5_row(row, headers)
    return _parse_d3_6_row(row, headers)


def _template_meta(sheet: str) -> tuple[str | None, str | None, list[str]]:
    meta = _SHEET_META.get(sheet, {})
    return meta.get("title"), None, meta.get("guidance", [])


@router.post("/api/workpapers/{wp_id}/f1/export-template")
async def f1_export_template(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)
    # F1-2 明细表：账龄列头按项目账龄配置动态生成（三期：期初/期末未审/期末审定）
    if sheet == "F1-2":
        segments = await resolve_aging_segments(db, wp_id, "F1")
        headers = _f1_2_dynamic_headers(segments)
    else:
        headers = _headers(sheet)
    title, subtitle, guidance = _template_meta(sheet)
    wb = build_workbook_template(sheet, headers, title=title, subtitle=subtitle, guidance=guidance)
    return workbook_to_response(wb, f"{sheet}_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/f1/export-data")
async def f1_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)
    item_id = _SHEET_ITEM_ID[sheet]
    rows_data = await load_json_rows(db, wp_id, item_id, field="remark")
    title, subtitle, guidance = _template_meta(sheet)
    # F1-2 明细表：账龄列头/值按项目账龄配置动态生成（三期）
    f1_2_segments: list[Any] = []
    if sheet == "F1-2":
        f1_2_segments = await resolve_aging_segments(db, wp_id, "F1")
        headers = _f1_2_dynamic_headers(f1_2_segments)
    else:
        headers = _headers(sheet)
    wb = build_workbook_template(sheet, headers, title=title, subtitle=subtitle, guidance=guidance)
    ws = wb[sheet]
    for d in rows_data:
        if sheet == "F1-2":
            ws.append(_export_f1_2_row_dynamic(d, f1_2_segments))
        else:
            ws.append(_export_row(sheet, d))
    return workbook_to_response(wb, f"{sheet}_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/f1/import-data")
async def f1_import_data(
    wp_id: str,
    sheet: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _validate_sheet(sheet)
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")
    header_row = 2 if _SHEET_META.get(sheet, {}).get("title") else 1

    # F1-2 明细表：账龄列按 label 动态匹配当前项目配置（三期），验证仅校验基础列
    f1_2_segments: list[Any] = []
    skipped_columns: list[str] = []
    if sheet == "F1-2":
        f1_2_segments = await resolve_aging_segments(db, wp_id, "F1")
        # 「对方单位名称」与 Excel「债权人名称」二选一即可
        headers = [h for h in _F1_2_BASE_HEADERS if h != "对方单位名称"]
    elif sheet == "F1-5":
        # 新 13 列与旧 8 列共用核心列；名称列二选一
        headers = ["期末余额", "账龄", "经济业务说明", "备注"]
    elif sheet == "F1-6":
        # 新 13 列与旧版共用核心列；关联方名称必填
        headers = ["关联方名称", "关联关系", "期初余额", "期末余额"]
    else:
        headers = _headers(sheet)

    try:
        actual, raw_rows = parse_upload_xlsx(content, headers, header_row=header_row)
    except ValueError as e:
        return {"ok": False, "errors": [str(e)], "imported_count": 0}
    except Exception:
        raise HTTPException(400, "无法解析xlsx文件")

    if sheet == "F1-2":
        if "对方单位名称" not in actual and "债权人名称" not in actual:
            return {"ok": False, "errors": ["缺少列: 对方单位名称 或 债权人名称"], "imported_count": 0}
        _, skipped_columns = match_import_aging(
            lambda _h: None, actual, f1_2_segments, subject_aging_periods("F1"),
        )
        rows_data, truncated = import_rows_generic(
            raw_rows, actual, [], parse_fn=lambda r, h: _parse_f1_2_row(r, h, f1_2_segments),
        )
    elif sheet == "F1-5":
        if "债务人名称" not in actual and "对方单位名称" not in actual:
            return {"ok": False, "errors": ["缺少列: 债务人名称 或 对方单位名称"], "imported_count": 0}
        rows_data, truncated = import_rows_generic(
            raw_rows, actual, [], parse_fn=lambda r, h: _parse_f1_5_row(r, h),
        )
    elif sheet == "F1-6":
        rows_data, truncated = import_rows_generic(
            raw_rows, actual, [], parse_fn=lambda r, h: _parse_f1_6_row(r, h),
        )
    else:
        rows_data, truncated = import_rows_generic(
            raw_rows, actual, [], parse_fn=lambda r, h: _parse_row(sheet, r, h),
        )
    await upsert_json_rows(db, wp_id, _SHEET_ITEM_ID[sheet], rows_data, field="remark")
    out: dict[str, Any] = {"ok": True, "imported_count": len(rows_data), "errors": []}
    if truncated:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    if skipped_columns:
        out["skipped_columns"] = skipped_columns
        out["warnings"] = [
            f"以下账龄列未匹配当前账龄配置，已跳过: {', '.join(skipped_columns)}"
        ]
    return out
