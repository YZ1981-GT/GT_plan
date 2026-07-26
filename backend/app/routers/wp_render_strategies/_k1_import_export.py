"""K1 其他应收款 — 导入导出（动态行表: K1-1/K1-2/K1-4/K1-5/K1-6/K1-7/K1-8/K1-11）."""

from __future__ import annotations

import io
import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy.ext.asyncio import AsyncSession

from ._cycle_import_export_common import (
    build_workbook_template,
    col_val,
    load_json_payload,
    parse_upload_xlsx,
    safe_float,
    safe_str,
    upsert_json_payload,
    workbook_to_response,
    import_rows_generic,
    create_cycle_import_export_router,
)

# ────────────────────────────────────────────────────────────
# K1-2 明细表（17列）
# ────────────────────────────────────────────────────────────
_K1_2_HEADERS = [
    "往来对象", "性质", "关联关系", "期初余额", "期末余额",
    "1年内", "1-2年", "2-3年", "3-4年", "4-5年", "5年以上",
    "阶段", "坏账准备", "净值", "凭证号", "结论", "备注",
]
_K1_2_KEYS = [
    "counterparty", "nature", "relatedParty", "openingBalance", "closingBalance",
    "agingLt1", "aging1to2", "aging2to3", "aging3to4", "aging4to5", "agingGt5",
    "stage", "badDebtProvision", "netValue", "voucherNo", "conclusion", "remark",
]

# ────────────────────────────────────────────────────────────
# K1-4 调整分录汇总（10列，对齐 Excel）
# ────────────────────────────────────────────────────────────
_K1_4_HEADERS = [
    "调整事项说明", "类别", "报表项目", "科目代码", "科目名称", "附注项目",
    "借方调整金额", "贷方调整金额", "索引", "备注",
]
_K1_4_KEYS = [
    "description", "category", "reportItem", "accountCode", "accountName", "noteItem",
    "debitAmount", "creditAmount", "indexRef", "remark",
]

# ────────────────────────────────────────────────────────────
# K1-5 大额分析（7列）
# ────────────────────────────────────────────────────────────
_K1_5_HEADERS = [
    "往来对象", "期末余额", "性质", "形成原因", "预计收回时间", "收回可能性", "后续核查",
]
_K1_5_KEYS = [
    "counterparty", "closingBalance", "nature", "formationReason", "expectedRecoveryTime", "recoveryPossibility", "followUpCheck",
]

# ────────────────────────────────────────────────────────────
# K1-7 三阶段划分（7列）
# ────────────────────────────────────────────────────────────
_K1_7_HEADERS = [
    "往来对象", "期末余额", "信用风险是否显著增加", "是否已发生信用减值", "划分阶段", "上期阶段", "变动说明",
]
_K1_7_KEYS = [
    "counterparty", "closingBalance", "significantIncrease", "isImpaired", "currentStage", "priorStage", "changeNote",
]

# ────────────────────────────────────────────────────────────
# K1-8 坏账测算 — 两个区段（账龄Tab + ECL Tab）合并为宽表导出
# 账龄Tab: 账龄区间/期末余额/迁徙率/预期损失率
# ECL Tab: 往来对象/EAD/PD/LGD/企业计提/测算结论
# ────────────────────────────────────────────────────────────
_K1_8_HEADERS = [
    "账龄区间", "期末余额", "迁徙率", "预期损失率",
    "往来对象", "EAD", "PD", "LGD", "企业计提", "测算结论",
]
_K1_8_KEYS = [
    "agingBucket", "closingBalance", "migrationRate", "expectedLossRate",
    "counterparty", "ead", "pd", "lgd", "bookedProvision", "calcConclusion",
]

# ────────────────────────────────────────────────────────────
# K1-11 关联方及交易检查（16列 = Excel 13列 + 公允/披露/资金占用）
# ────────────────────────────────────────────────────────────
_K1_11_ITEM_ID = "K1-11-related-party"

_K1_11_HEADERS = [
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
    "期后收款金额",
    "是否公允",
    "是否披露",
    "资金占用",
    "索引号",
    "备注",
]


async def _k1_11_load_bundle(db, wp_id: str) -> tuple[dict[str, Any], list[dict]]:
    """读取 K1-11 完整 JSON（tables.rows + 审计说明/结论）。"""
    payload = await load_json_payload(db, wp_id, _K1_11_ITEM_ID, field="remark")
    if payload is None:
        payload = await load_json_payload(db, wp_id, _K1_11_ITEM_ID, field="conclusion")
    if not isinstance(payload, dict):
        return {}, []
    tables = payload.get("tables") or {}
    rows = tables.get("rows")
    if not isinstance(rows, list):
        rows = []
    return payload, [r for r in rows if isinstance(r, dict)]


def _k1_11_export_row(data: dict) -> list[Any]:
    begin = safe_float(data.get("beginBalance"))
    debit = safe_float(data.get("debit"))
    credit = safe_float(data.get("credit"))
    end_raw = data.get("endBalance")
    end_balance = safe_float(end_raw) if end_raw not in (None, "") else begin + debit - credit
    provision = safe_float(data.get("provision"))
    book_raw = data.get("bookValue")
    book = safe_float(book_raw) if book_raw not in (None, "") else end_balance - provision
    return [
        safe_str(data.get("name") or data.get("partyName")),
        safe_str(data.get("relation") or data.get("relationship")),
        begin,
        debit,
        credit,
        end_balance,
        provision,
        book,
        safe_str(data.get("aging") or data.get("agingDescription")),
        safe_str(data.get("nature") or data.get("natureDescription")),
        safe_float(data.get("postCollection") or data.get("postPeriodCollection")),
        safe_str(data.get("isFair") or "待评估"),
        safe_str(data.get("isDisclosed") or "待评估"),
        safe_str(data.get("capitalOccupation") or "待评估"),
        safe_str(data.get("indexNo") or data.get("indexRef")),
        safe_str(data.get("remark")),
    ]


def _k1_11_parse_row(row: tuple, headers: list[str]) -> dict:
    begin = safe_float(col_val(row, headers, "期初余额"))
    debit = safe_float(col_val(row, headers, "借方发生额"))
    if debit == 0:
        debit = safe_float(col_val(row, headers, "借方发生"))
    credit = safe_float(col_val(row, headers, "贷方发生额"))
    if credit == 0:
        credit = safe_float(col_val(row, headers, "贷方发生"))
    end_raw = col_val(row, headers, "期末余额")
    end_balance = safe_float(end_raw) if end_raw not in (None, "") else begin + debit - credit
    provision = safe_float(col_val(row, headers, "减：坏账准备"))
    if provision == 0:
        provision = safe_float(col_val(row, headers, "坏账准备"))
    book_raw = col_val(row, headers, "账面价值")
    book = safe_float(book_raw) if book_raw not in (None, "") else end_balance - provision
    nature = (
        safe_str(col_val(row, headers, "发生原因（款项性质）"))
        or safe_str(col_val(row, headers, "发生原因"))
        or safe_str(col_val(row, headers, "款项性质"))
    )
    return {
        "id": str(uuid4()),
        "name": safe_str(col_val(row, headers, "关联方名称")),
        "relation": safe_str(col_val(row, headers, "关联关系")),
        "beginBalance": begin,
        "debit": debit,
        "credit": credit,
        "endBalance": end_balance,
        "provision": provision,
        "aging": safe_str(col_val(row, headers, "发生时间及账龄")),
        "nature": nature,
        "postCollection": safe_float(col_val(row, headers, "期后收款金额"))
        or safe_float(col_val(row, headers, "期后收款")),
        "isFair": safe_str(col_val(row, headers, "是否公允")) or "待评估",
        "isDisclosed": safe_str(col_val(row, headers, "是否披露")) or "待评估",
        "capitalOccupation": safe_str(col_val(row, headers, "资金占用")) or "待评估",
        "indexNo": safe_str(col_val(row, headers, "索引号"))
        or safe_str(col_val(row, headers, "索引")),
        "remark": safe_str(col_val(row, headers, "备注")),
        # 兼容前端 bookValue 展示
        "bookValue": book,
    }


async def _k1_11_export_loader(db, wp_id: str) -> dict[str, Any]:
    full, rows = await _k1_11_load_bundle(db, wp_id)
    return {"full": full, "rows": rows}


def _k1_11_build_workbook(payload: dict | None, template_only: bool = False):
    meta = _K1_SPECS["K1-11"]
    wb = build_workbook_template(
        "K1-11",
        _K1_11_HEADERS,
        title=meta.get("title"),
        guidance=meta.get("guidance"),
    )
    if not template_only and payload:
        ws = wb["K1-11"]
        for d in payload.get("rows") or []:
            ws.append(_k1_11_export_row(d))
    return wb


def _k1_11_parse_import(content: bytes) -> tuple[list[dict], list[str], int]:
    headers_required = ["关联方名称", "关联关系", "期初余额", "期末余额"]
    try:
        actual, raw_rows = parse_upload_xlsx(content, headers_required, header_row=2)
    except ValueError as e:
        return [], [str(e)], 0
    rows, _truncated = import_rows_generic(
        raw_rows, actual, [], parse_fn=lambda r, h: _k1_11_parse_row(r, h),
    )
    return rows, [], len(rows)


async def _k1_11_import_handler(db, wp_id: str, rows: list[dict]) -> None:
    full, _ = await _k1_11_load_bundle(db, wp_id)
    if not isinstance(full, dict):
        full = {}
    full.setdefault("tables", {})
    full["tables"]["rows"] = rows
    full.setdefault("auditNote", full.get("auditNote") or "")
    full.setdefault("conclusion", full.get("conclusion") or "")
    full.setdefault("conclusionOption", full.get("conclusionOption") or "")
    await upsert_json_payload(db, wp_id, _K1_11_ITEM_ID, full, field="remark")


# ────────────────────────────────────────────────────────────
# K1-6 信用减值损失会计政策检查（多 sheet：组合/同业/K2损失率/文本）
# ────────────────────────────────────────────────────────────
_K1_6_COMBO_HEADERS = ["组合序号", "划分依据（款项性质）", "损失率确定方法", "备注"]
_K1_6_PEER_HEADERS = ["公司", "会计政策摘要", "与被审计单位可比"]
_K1_6_K2_HEADERS = ["账龄段", "历史损失率", "调整后损失率", "备注"]
_K1_6_TEXT_HEADERS = ["字段", "内容"]

_K1_6_TEXT_FIELD_MAP: dict[str, str] = {
    "减值政策说明": "K1-6-policy-desc",
    "审计程序": "K1-6-procedures",
    "历史坏账损失": "K1-6-historical",
    "前瞻性信息": "K1-6-forward",
    "与前期对比": "K1-6-prior-year",
    "同业综合对比": "K1-6-peer",
    "审计说明": "K1-6-audit-note",
    "审计结论": "K1-6-conclusion",
    "结论选项": "K1-6-conclusion-option",
}

_K1_6_K2_ITEM_ID = "K1-k2-aging-loss-rates"


async def _load_remark_text(db: AsyncSession, wp_id: str, item_id: str) -> str:
    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :iid LIMIT 1"
        ),
        {"wp_id": wp_id, "iid": item_id},
    )
    row = result.fetchone()
    if not row or not getattr(row, "remark", None):
        return ""
    return str(row.remark)


async def _upsert_remark_text(
    db: AsyncSession, wp_id: str, item_id: str, text: str, *, also_conclusion: bool = False
) -> None:
    proj = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wp_id AND is_deleted = false"),
        {"wp_id": wp_id},
    )
    project_id = proj.scalar_one_or_none()
    if not project_id:
        raise ValueError(f"working_paper not found: {wp_id}")
    if also_conclusion:
        await db.execute(
            sa.text("""
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, conclusion, updated_at, created_at)
                VALUES (:id, :project_id, :wp_id, :item_id, :remark, :conclusion, NOW(), NOW())
                ON CONFLICT (wp_id, item_id)
                DO UPDATE SET remark = :remark, conclusion = :conclusion, updated_at = NOW()
            """),
            {
                "id": str(uuid4()),
                "project_id": str(project_id),
                "wp_id": wp_id,
                "item_id": item_id,
                "remark": text,
                "conclusion": text,
            },
        )
    else:
        await db.execute(
            sa.text("""
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, updated_at, created_at)
                VALUES (:id, :project_id, :wp_id, :item_id, :remark, NOW(), NOW())
                ON CONFLICT (wp_id, item_id)
                DO UPDATE SET remark = :remark, updated_at = NOW()
            """),
            {
                "id": str(uuid4()),
                "project_id": str(project_id),
                "wp_id": wp_id,
                "item_id": item_id,
                "remark": text,
            },
        )
    await db.commit()


async def _k1_6_load_bundle(db: AsyncSession, wp_id: str) -> dict[str, Any]:
    combos_raw = await load_json_payload(db, wp_id, "K1-6-combos", field="remark")
    combos = combos_raw if isinstance(combos_raw, list) else []
    peer_raw = await load_json_payload(db, wp_id, "K1-6-peer-rows", field="remark")
    peer_rows = peer_raw if isinstance(peer_raw, list) else []
    k2_raw = await load_json_payload(db, wp_id, _K1_6_K2_ITEM_ID, field="remark")
    k2_rates = k2_raw if isinstance(k2_raw, list) else []
    texts: dict[str, str] = {}
    for label, item_id in _K1_6_TEXT_FIELD_MAP.items():
        texts[label] = await _load_remark_text(db, wp_id, item_id)
    return {"combos": combos, "peerRows": peer_rows, "k2Rates": k2_rates, "texts": texts}


def _k1_6_combo_export_rows(combos: list[dict]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for i, c in enumerate(combos):
        if not isinstance(c, dict):
            continue
        rows.append([
            i + 1,
            safe_str(c.get("basis")),
            safe_str(c.get("method")),
            safe_str(c.get("remark")),
        ])
    return rows


def _k1_6_peer_export_rows(peer_rows: list[dict]) -> list[list[Any]]:
    out: list[list[Any]] = []
    for r in peer_rows:
        if not isinstance(r, dict):
            continue
        out.append([
            safe_str(r.get("company")),
            safe_str(r.get("policyText") or r.get("text")),
            safe_str(r.get("comparable")),
        ])
    return out


def _k1_6_k2_export_rows(k2_rates: list[dict]) -> list[list[Any]]:
    out: list[list[Any]] = []
    for r in k2_rates:
        if not isinstance(r, dict):
            continue
        out.append([
            safe_str(r.get("agingBucket") or r.get("bucket")),
            safe_float(r.get("historicalRate")),
            safe_float(r.get("adjustedRate") or r.get("historicalRate")),
            safe_str(r.get("remark")),
        ])
    return out


def _k1_6_text_export_rows(texts: dict[str, str]) -> list[list[Any]]:
    return [[label, texts.get(label, "")] for label in _K1_6_TEXT_FIELD_MAP]


def _k1_6_append_sheet(wb: Workbook, sheet_name: str, headers: list[str], data_rows: list[list[Any]]) -> None:
    ws = wb.create_sheet(sheet_name[:31])
    ws.append(headers)
    ws.freeze_panes = "A2"
    for row in data_rows:
        ws.append(row)
    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 16


def _k1_6_build_workbook(payload: dict | None, template_only: bool = False):
    wb = Workbook()
    wb.remove(wb.active)
    combos = (payload or {}).get("combos") or []
    peer_rows = (payload or {}).get("peerRows") or []
    k2_rates = (payload or {}).get("k2Rates") or []
    texts = (payload or {}).get("texts") or {}

    if template_only and not combos:
        combos = [{"basis": "押金和保证金", "method": "账龄分析法", "remark": ""}]
    if template_only and not peer_rows:
        peer_rows = [{"company": "示例公司", "policyText": "组合1 押金保证金；组合2 代垫款", "comparable": "部分一致"}]
    if template_only and not k2_rates:
        k2_rates = [
            {"agingBucket": "1年以内", "historicalRate": 0.01, "adjustedRate": 0.01, "remark": ""},
            {"agingBucket": "1-2年", "historicalRate": 0.05, "adjustedRate": 0.05, "remark": ""},
        ]

    _k1_6_append_sheet(wb, "组合划分", _K1_6_COMBO_HEADERS, _k1_6_combo_export_rows(combos))
    _k1_6_append_sheet(wb, "同业对比", _K1_6_PEER_HEADERS, _k1_6_peer_export_rows(peer_rows))
    _k1_6_append_sheet(wb, "K2账龄损失率", _K1_6_K2_HEADERS, _k1_6_k2_export_rows(k2_rates))
    _k1_6_append_sheet(wb, "文本说明", _K1_6_TEXT_HEADERS, _k1_6_text_export_rows(texts))

    meta = _K1_SPECS["K1-6"]
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append([meta.get("title", "K1-6")])
    ws_guide["A1"].font = Font(bold=True, size=12)
    ws_guide.append([])
    for line in meta.get("guidance") or []:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _k1_6_parse_sheet(content: bytes, sheet_name: str, required_headers: list[str]) -> tuple[list[str], list[tuple]]:
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    if sheet_name not in wb.sheetnames:
        wb.close()
        return [], []
    ws = wb[sheet_name]
    header_row = 1
    actual = [
        str(c.value).strip() if c and c.value else ""
        for c in next(ws.iter_rows(min_row=header_row, max_row=header_row))
    ]
    rows: list[tuple] = []
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        if all(v is None for v in row):
            continue
        if row and str(row[0] or "").strip().startswith("示例"):
            continue
        rows.append(row)
    wb.close()
    return actual, rows


def _k1_6_parse_combos(rows: list[tuple], headers: list[str]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        basis = safe_str(col_val(row, headers, "划分依据（款项性质）") or col_val(row, headers, "划分依据"))
        if not basis:
            continue
        out.append({
            "id": str(uuid4()),
            "basis": basis,
            "method": safe_str(col_val(row, headers, "损失率确定方法")),
            "remark": safe_str(col_val(row, headers, "备注")),
        })
    return out


def _k1_6_parse_peers(rows: list[tuple], headers: list[str]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        company = safe_str(col_val(row, headers, "公司"))
        policy = safe_str(col_val(row, headers, "会计政策摘要"))
        if not company and not policy:
            continue
        out.append({
            "id": str(uuid4()),
            "company": company,
            "policyText": policy,
            "comparable": safe_str(col_val(row, headers, "与被审计单位可比")),
        })
    return out


def _k1_6_parse_k2(rows: list[tuple], headers: list[str]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        bucket = safe_str(col_val(row, headers, "账龄段"))
        if not bucket:
            continue
        hist = safe_float(col_val(row, headers, "历史损失率"))
        adj_raw = col_val(row, headers, "调整后损失率")
        out.append({
            "id": str(uuid4()),
            "agingBucket": bucket,
            "historicalRate": hist,
            "adjustedRate": safe_float(adj_raw) if adj_raw not in (None, "") else hist,
            "remark": safe_str(col_val(row, headers, "备注")),
        })
    return out


def _k1_6_parse_texts(rows: list[tuple], headers: list[str]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for row in rows:
        label = safe_str(col_val(row, headers, "字段"))
        if label in _K1_6_TEXT_FIELD_MAP:
            texts[label] = safe_str(col_val(row, headers, "内容"))
    return texts


def _k1_6_parse_import(content: bytes) -> tuple[dict[str, Any], list[str], int]:
    errors: list[str] = []
    combo_h, combo_rows = _k1_6_parse_sheet(content, "组合划分", _K1_6_COMBO_HEADERS)
    peer_h, peer_rows = _k1_6_parse_sheet(content, "同业对比", _K1_6_PEER_HEADERS)
    k2_h, k2_rows = _k1_6_parse_sheet(content, "K2账龄损失率", _K1_6_K2_HEADERS)
    text_h, text_rows = _k1_6_parse_sheet(content, "文本说明", _K1_6_TEXT_HEADERS)

    payload: dict[str, Any] = {}
    combos = _k1_6_parse_combos(combo_rows, combo_h) if combo_rows else []
    peers = _k1_6_parse_peers(peer_rows, peer_h) if peer_rows else []
    k2 = _k1_6_parse_k2(k2_rows, k2_h) if k2_rows else []
    texts = _k1_6_parse_texts(text_rows, text_h) if text_rows else {}

    if combos:
        payload["combos"] = combos
    if peers:
        payload["peerRows"] = peers
    if k2:
        payload["k2Rates"] = k2
    if texts:
        payload["texts"] = texts

    imported = len(combos) + len(peers) + len(k2) + len(texts)
    if imported == 0:
        errors.append("未解析到有效数据，请使用 K1-6 标准模板（含组合划分/同业对比/K2账龄损失率/文本说明）")
    return payload, errors, imported


async def _k1_6_import_handler(db: AsyncSession, wp_id: str, payload: dict[str, Any]) -> None:
    if "combos" in payload:
        await upsert_json_payload(db, wp_id, "K1-6-combos", payload["combos"], field="remark")
    if "peerRows" in payload:
        await upsert_json_payload(db, wp_id, "K1-6-peer-rows", payload["peerRows"], field="remark")
    if "k2Rates" in payload:
        await upsert_json_payload(db, wp_id, _K1_6_K2_ITEM_ID, payload["k2Rates"], field="remark")
    for label, text in (payload.get("texts") or {}).items():
        item_id = _K1_6_TEXT_FIELD_MAP.get(label)
        if item_id:
            await _upsert_remark_text(
                db, wp_id, item_id, text, also_conclusion=(item_id == "K1-6-conclusion")
            )


async def _k1_6_export_loader(db: AsyncSession, wp_id: str) -> dict[str, Any]:
    return await _k1_6_load_bundle(db, wp_id)


# ────────────────────────────────────────────────────────────
# K1-1 审定表（多 sheet：组合/账龄/性质宽表 + 报表核对 + 文本）
# ────────────────────────────────────────────────────────────
_K1_1_WIDE_HEADERS = [
    "项目",
    "期初未审", "期初AJE", "期初RJE", "期初审定",
    "期末未审", "期末AJE", "期末RJE", "期末审定",
    "变动额", "变动率", "原因分析",
]

_K1_1_PORTFOLIO_DEFS: list[tuple[str, str]] = [
    ("r0", "单项计提"),
    ("r1", "账龄组合"),
    ("r2", "客户类型组合"),
    ("r3", "其他组合"),
]

_K1_1_AGING_DEFS: list[tuple[str, str]] = [
    ("a0", "1年以内"),
    ("a1", "1-2年"),
    ("a2", "2-3年"),
    ("a3", "3-4年"),
    ("a4", "4-5年"),
    ("a5", "5年以上"),
]

_K1_1_NATURE_DEFS: list[tuple[str, str]] = [
    ("n0", "保证金"),
    ("n1", "押金"),
    ("n2", "备用金"),
    ("n3", "往来款"),
    ("n4", "其他"),
]

_K1_1_SECTIONS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("组合原值", "receivable", _K1_1_PORTFOLIO_DEFS),
    ("组合坏账", "baddebt", _K1_1_PORTFOLIO_DEFS),
    ("账龄原值", "aging-gross", _K1_1_AGING_DEFS),
    ("账龄坏账", "aging-prov", _K1_1_AGING_DEFS),
    ("性质原值", "nature-gross", _K1_1_NATURE_DEFS),
    ("性质坏账", "nature-prov", _K1_1_NATURE_DEFS),
]

_K1_1_FS_HEADERS = ["字段", "金额"]
_K1_1_FS_FIELDS: list[tuple[str, str]] = [
    ("应收利息", "interest"),
    ("应收股利", "dividend"),
    ("其他应收款合计", "other-total"),
]

_K1_1_TEXT_HEADERS = ["字段", "内容"]
_K1_1_TEXT_MAP: dict[str, str] = {
    "审计说明": "K1-1-audit-note",
    "审计结论": "K1-1-audit-conclusion",
}


def _k1_1_round2(n: float) -> float:
    return round(n * 100) / 100


def _k1_1_audited(unadj: float, aje: float, rje: float) -> float:
    return _k1_1_round2(unadj + aje + rje)


async def _k1_1_load_responses(db: AsyncSession, wp_id: str) -> dict[str, str]:
    result = await db.execute(
        sa.text(
            "SELECT item_id, remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id LIKE 'K1-1-%'"
        ),
        {"wp_id": wp_id},
    )
    out: dict[str, str] = {}
    for row in result.fetchall():
        iid = str(getattr(row, "item_id", "") or "")
        if iid:
            out[iid] = "" if getattr(row, "remark", None) is None else str(row.remark)
    return out


def _k1_1_num(responses: dict[str, str], item_id: str) -> float:
    raw = responses.get(item_id, "")
    try:
        return float(raw) if raw not in ("", None) else 0.0
    except (ValueError, TypeError):
        return 0.0


def _k1_1_str(responses: dict[str, str], item_id: str) -> str:
    return safe_str(responses.get(item_id, ""))


def _k1_1_row_values(responses: dict[str, str], prefix: str, row_key: str, label: str) -> list[Any]:
    base = f"K1-1-{prefix}-{row_key}"
    prior_unadj = _k1_1_num(responses, f"{base}-prior-unadj")
    prior_aje = _k1_1_num(responses, f"{base}-prior-aje")
    prior_rje = _k1_1_num(responses, f"{base}-prior-rje")
    prior_audited = _k1_1_num(responses, f"{base}-prior-audited") or _k1_1_audited(prior_unadj, prior_aje, prior_rje)
    unadj = _k1_1_num(responses, f"{base}-unadj")
    aje = _k1_1_num(responses, f"{base}-aje")
    rje = _k1_1_num(responses, f"{base}-rje")
    audited = _k1_1_audited(unadj, aje, rje)
    change_amount = _k1_1_round2(audited - prior_audited)
    change_rate = ""
    if abs(prior_audited) >= 0.005:
        change_rate = _k1_1_round2(change_amount / prior_audited)
    remark = _k1_1_str(responses, f"{base}-remark")
    stored_label = _k1_1_str(responses, f"K1-1-{prefix}-{row_key}-label") or label
    return [
        stored_label,
        prior_unadj, prior_aje, prior_rje, prior_audited,
        unadj, aje, rje, audited,
        change_amount, change_rate, remark,
    ]


async def _k1_1_export_loader(db: AsyncSession, wp_id: str) -> dict[str, Any]:
    responses = await _k1_1_load_responses(db, wp_id)
    sections: dict[str, list[list[Any]]] = {}
    for sheet_name, prefix, defs in _K1_1_SECTIONS:
        sections[sheet_name] = [
            _k1_1_row_values(responses, prefix, row_key, label)
            for row_key, label in defs
        ]
    fs = {
        "interest": _k1_1_num(responses, "K1-1-fs-interest"),
        "dividend": _k1_1_num(responses, "K1-1-fs-dividend"),
        "other-total": _k1_1_num(responses, "K1-1-fs-other-total"),
    }
    texts = {
        "审计说明": _k1_1_str(responses, "K1-1-audit-note"),
        "审计结论": _k1_1_str(responses, "K1-1-audit-conclusion"),
    }
    return {"sections": sections, "fs": fs, "texts": texts}


def _k1_1_build_workbook(payload: dict | None, template_only: bool = False):
    wb = Workbook()
    wb.remove(wb.active)
    sections = (payload or {}).get("sections") or {}
    fs = (payload or {}).get("fs") or {}
    texts = (payload or {}).get("texts") or {}

    for sheet_name, prefix, defs in _K1_1_SECTIONS:
        rows = sections.get(sheet_name)
        if rows is None and template_only:
            rows = [[label, 0, 0, 0, 0, 0, 0, 0, 0, 0, "", ""] for _, label in defs]
        _k1_6_append_sheet(wb, sheet_name, _K1_1_WIDE_HEADERS, rows or [])

    fs_rows = [[label, fs.get(key, 0) if not template_only else 0] for label, key in _K1_1_FS_FIELDS]
    _k1_6_append_sheet(wb, "报表核对", _K1_1_FS_HEADERS, fs_rows)

    text_rows = [[label, texts.get(label, "")] for label in _K1_1_TEXT_MAP]
    _k1_6_append_sheet(wb, "文本说明", _K1_1_TEXT_HEADERS, text_rows)

    meta_title = "K1-1 其他应收款审定表"
    meta_guidance = [
        "K1-1 审定表 编制说明",
        "",
        "多 sheet 结构：组合原值/组合坏账/账龄原值/账龄坏账/性质原值/性质坏账/报表核对/文本说明。",
        "宽表列：期初(未审/AJE/RJE/审定) + 期末(未审/AJE/RJE/审定) + 变动额/变动率/原因分析。",
        "审定=未审+AJE+RJE；变动超30%须在原因分析列说明。",
        "组合名称须与 K1-6/K1-8 一致；未审数可从 K1-2 同步。",
        "报表核对：其他应收款合计 vs K1-1 净值审定。",
    ]
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append([meta_title])
    ws_guide["A1"].font = Font(bold=True, size=12)
    ws_guide.append([])
    for line in meta_guidance:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _k1_1_label_to_row_key(label: str, defs: list[tuple[str, str]]) -> str | None:
    s = safe_str(label)
    if not s:
        return None
    for row_key, def_label in defs:
        if s == def_label:
            return row_key
    return None


def _k1_1_parse_wide_rows(
    rows: list[tuple],
    headers: list[str],
    defs: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        label = safe_str(col_val(row, headers, "项目"))
        row_key = _k1_1_label_to_row_key(label, defs)
        if not row_key and i < len(defs):
            row_key = defs[i][0]
            if not label:
                label = defs[i][1]
        if not row_key:
            continue
        default_label = next((d[1] for d in defs if d[0] == row_key), label)
        prior_unadj = safe_float(col_val(row, headers, "期初未审"))
        prior_aje = safe_float(col_val(row, headers, "期初AJE"))
        prior_rje = safe_float(col_val(row, headers, "期初RJE"))
        unadj = safe_float(col_val(row, headers, "期末未审"))
        aje = safe_float(col_val(row, headers, "期末AJE"))
        rje = safe_float(col_val(row, headers, "期末RJE"))
        remark = safe_str(col_val(row, headers, "原因分析"))
        out.append({
            "rowKey": row_key,
            "label": label or default_label,
            "priorUnadj": prior_unadj,
            "priorAje": prior_aje,
            "priorRje": prior_rje,
            "unadj": unadj,
            "aje": aje,
            "rje": rje,
            "remark": remark,
        })
    return out


def _k1_1_parse_import(content: bytes) -> tuple[dict[str, Any], list[str], int]:
    errors: list[str] = []
    payload: dict[str, Any] = {"sections": {}, "fs": {}, "texts": {}}
    imported = 0

    for sheet_name, prefix, defs in _K1_1_SECTIONS:
        headers, raw_rows = _k1_6_parse_sheet(content, sheet_name, _K1_1_WIDE_HEADERS)
        if not raw_rows:
            continue
        parsed = _k1_1_parse_wide_rows(raw_rows, headers, defs)
        if parsed:
            payload["sections"][prefix] = parsed
            imported += len(parsed)

    fs_headers, fs_rows = _k1_6_parse_sheet(content, "报表核对", _K1_1_FS_HEADERS)
    for row in fs_rows:
        label = safe_str(col_val(row, fs_headers, "字段"))
        for fs_label, key in _K1_1_FS_FIELDS:
            if label == fs_label:
                payload["fs"][key] = safe_float(col_val(row, fs_headers, "金额"))
                imported += 1

    text_headers, text_rows = _k1_6_parse_sheet(content, "文本说明", _K1_1_TEXT_HEADERS)
    texts: dict[str, str] = {}
    for row in text_rows:
        label = safe_str(col_val(row, text_headers, "字段"))
        if label in _K1_1_TEXT_MAP:
            texts[label] = safe_str(col_val(row, text_headers, "内容"))
    for label, item_id in _K1_1_TEXT_MAP.items():
        if label in texts:
            payload["texts"][label] = texts[label]
            imported += 1

    if imported == 0:
        errors.append("未解析到有效数据，请使用 K1-1 标准模板（含组合/账龄/性质宽表）")
    return payload, errors, imported


async def _k1_1_import_handler(db: AsyncSession, wp_id: str, payload: dict[str, Any]) -> None:
    sections = payload.get("sections") or {}
    for prefix, rows in sections.items():
        if prefix in ("receivable", "baddebt"):
            count_id = f"K1-1-{prefix}-count"
            await _upsert_remark_text(db, wp_id, count_id, str(len(rows)))
        for row in rows:
            row_key = safe_str(row.get("rowKey"))
            if not row_key:
                continue
            base = f"K1-1-{prefix}-{row_key}"
            label = safe_str(row.get("label"))
            if label:
                await _upsert_remark_text(db, wp_id, f"{base}-label", label)
            field_map = {
                "prior-unadj": row.get("priorUnadj"),
                "prior-aje": row.get("priorAje"),
                "prior-rje": row.get("priorRje"),
                "unadj": row.get("unadj"),
                "aje": row.get("aje"),
                "rje": row.get("rje"),
            }
            for suffix, val in field_map.items():
                await _upsert_remark_text(db, wp_id, f"{base}-{suffix}", str(_k1_1_round2(safe_float(val))))
            remark = safe_str(row.get("remark"))
            if remark:
                await _upsert_remark_text(db, wp_id, f"{base}-remark", remark)

    for key, val in (payload.get("fs") or {}).items():
        await _upsert_remark_text(db, wp_id, f"K1-1-fs-{key}", str(_k1_1_round2(safe_float(val))))

    for label, text in (payload.get("texts") or {}).items():
        item_id = _K1_1_TEXT_MAP.get(label)
        if item_id:
            await _upsert_remark_text(
                db, wp_id, item_id, text, also_conclusion=(item_id == "K1-1-audit-conclusion")
            )


# ────────────────────────────────────────────────────────────
# K1-3 坏账准备明细（多 sheet：明细 + 三阶段 + 文本）
# ────────────────────────────────────────────────────────────
_K1_3_ITEM_ID = 'K1-3-baddebt-rows'

_K1_3_MAIN_HEADERS = [
    '项目', '类别', '期初账面', '期初调整', '期初审定',
    '本期计提', '其他增加', '本期转回', '本期核销', '其他减少',
    '期末账面', '期末调整', '期末审定', '原因',
]

_K1_3_STAGE_HEADERS = ['项目', '第一阶段', '第二阶段', '第三阶段']

_K1_3_TEXT_MAP: dict[str, str] = {
    '审计说明': 'auditNote',
    '审计结论': 'conclusion',
    '结论选项': 'conclusionOption',
}


async def _k1_3_load_bundle(db: AsyncSession, wp_id: str) -> dict[str, Any]:
    raw = await load_json_payload(db, wp_id, _K1_3_ITEM_ID, field='remark')
    if not isinstance(raw, dict):
        return {'version': 2, 'mainRows': [], 'stageMovements': [], 'auditNote': '', 'conclusion': '', 'conclusionOption': ''}
    return raw


def _k1_3_main_export_rows(payload: dict) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for r in payload.get('mainRows') or []:
        if not isinstance(r, dict):
            continue
        rows.append([
            safe_str(r.get('label')),
            safe_str(r.get('category')),
            safe_float(r.get('priorBook')),
            safe_float(r.get('priorAdj')),
            safe_float(r.get('priorAudited')),
            safe_float(r.get('currentProvision')),
            safe_float(r.get('currentOtherIncrease')),
            safe_float(r.get('currentReversal')),
            safe_float(r.get('currentWriteOff')),
            safe_float(r.get('currentOtherDecrease')),
            safe_float(r.get('currentBook')),
            safe_float(r.get('currentAdj')),
            safe_float(r.get('currentAudited')),
            safe_str(r.get('reason')),
        ])
    return rows


def _k1_3_stage_export_rows(payload: dict) -> list[list[Any]]:
    out: list[list[Any]] = []
    for r in payload.get('stageMovements') or []:
        if not isinstance(r, dict):
            continue
        out.append([
            safe_str(r.get('label')),
            safe_float(r.get('stage1')),
            safe_float(r.get('stage2')),
            safe_float(r.get('stage3')),
        ])
    return out


def _k1_3_build_workbook(payload: dict | None, template_only: bool = False):
    wb = Workbook()
    wb.remove(wb.active)
    p = payload or {}
    if template_only and not p.get('mainRows'):
        p = {
            'mainRows': [
                {'label': '单项评估计提', 'category': 'individual', 'isSubRow': False, 'isFixed': True},
                {'label': '按组合计提', 'category': 'portfolio', 'isSubRow': False, 'isFixed': True},
            ],
            'stageMovements': [
                {'label': '期初余额', 'stage1': 0, 'stage2': 0, 'stage3': 0},
                {'label': '本年计提', 'stage1': 0, 'stage2': 0, 'stage3': 0},
            ],
        }
    _k1_6_append_sheet(wb, '坏账明细', _K1_3_MAIN_HEADERS, _k1_3_main_export_rows(p))
    _k1_6_append_sheet(wb, '三阶段转入转出', _K1_3_STAGE_HEADERS, _k1_3_stage_export_rows(p))
    texts = [[k, safe_str(p.get(v))] for k, v in _K1_3_TEXT_MAP.items()]
    _k1_6_append_sheet(wb, '文本说明', _K1_6_TEXT_HEADERS, texts)
    return wb


def _k1_3_parse_main(rows: list[tuple], headers: list[str]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        label = safe_str(col_val(row, headers, '项目'))
        if not label:
            continue
        out.append({
            'id': str(uuid4()),
            'label': label,
            'category': safe_str(col_val(row, headers, '类别')) or 'individual',
            'isSubRow': safe_str(col_val(row, headers, '类别')) == 'individual' and label not in ('单项评估计提', '按组合计提', '合计'),
            'isFixed': label in ('单项评估计提', '按组合计提', '合计'),
            'priorBook': safe_float(col_val(row, headers, '期初账面')),
            'priorAdj': safe_float(col_val(row, headers, '期初调整')),
            'priorAudited': safe_float(col_val(row, headers, '期初审定')),
            'currentProvision': safe_float(col_val(row, headers, '本期计提')),
            'currentOtherIncrease': safe_float(col_val(row, headers, '其他增加')),
            'currentReversal': safe_float(col_val(row, headers, '本期转回')),
            'currentWriteOff': safe_float(col_val(row, headers, '本期核销')),
            'currentOtherDecrease': safe_float(col_val(row, headers, '其他减少')),
            'currentBook': safe_float(col_val(row, headers, '期末账面')),
            'currentAdj': safe_float(col_val(row, headers, '期末调整')),
            'currentAudited': safe_float(col_val(row, headers, '期末审定')),
            'reason': safe_str(col_val(row, headers, '原因')),
        })
    return out


def _k1_3_parse_stage(rows: list[tuple], headers: list[str]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        label = safe_str(col_val(row, headers, '项目'))
        if not label:
            continue
        out.append({
            'key': label,
            'label': label,
            'stage1': safe_float(col_val(row, headers, '第一阶段')),
            'stage2': safe_float(col_val(row, headers, '第二阶段')),
            'stage3': safe_float(col_val(row, headers, '第三阶段')),
            'editable': label != '期末余额',
        })
    return out


def _k1_3_parse_import(content: bytes) -> tuple[dict[str, Any], list[str], int]:
    errors: list[str] = []
    payload: dict[str, Any] = {'version': 2}
    imported = 0
    mh, mrows = _k1_6_parse_sheet(content, '坏账明细', _K1_3_MAIN_HEADERS)
    if mrows:
        payload['mainRows'] = _k1_3_parse_main(mrows, mh)
        imported += len(payload['mainRows'])
    sh, srows = _k1_6_parse_sheet(content, '三阶段转入转出', _K1_3_STAGE_HEADERS)
    if srows:
        payload['stageMovements'] = _k1_3_parse_stage(srows, sh)
        imported += len(payload['stageMovements'])
    th, trows = _k1_6_parse_sheet(content, '文本说明', _K1_6_TEXT_HEADERS)
    for row in trows:
        label = safe_str(col_val(row, th, '字段'))
        if label in _K1_3_TEXT_MAP:
            payload[_K1_3_TEXT_MAP[label]] = safe_str(col_val(row, th, '内容'))
            imported += 1
    if imported == 0:
        errors.append('未解析到有效数据，请使用 K1-3 标准模板')
    return payload, errors, imported


async def _k1_3_import_handler(db: AsyncSession, wp_id: str, payload: dict[str, Any]) -> None:
    full, _ = await _k1_3_load_bundle(db, wp_id)
    if not isinstance(full, dict):
        full = {}
    full.update({k: payload[k] for k in ('mainRows', 'stageMovements', 'auditNote', 'conclusion', 'conclusionOption') if k in payload})
    full['version'] = 2
    await upsert_json_payload(db, wp_id, _K1_3_ITEM_ID, full, field='remark')


async def _k1_3_export_loader(db: AsyncSession, wp_id: str) -> dict[str, Any]:
    return await _k1_3_load_bundle(db, wp_id)


# ────────────────────────────────────────────────────────────
# K1-9 转回/核销检查（单 sheet 双区段）
# ────────────────────────────────────────────────────────────
_K1_9_ITEM_ID = 'K1-9-writeoff'

_K1_9_HEADERS = [
    '类别', '单位名称', '转回原因/核销原因', '收回方式', '原确定坏账准备的依据',
    '收回或转回金额/核销金额', '收回/转回前累计已计提', '其他应收款的性质',
    '履行的核销程序', '是否关联方往来', '合理性', '合理性分析', '索引号',
]


async def _k1_9_load_bundle(db: AsyncSession, wp_id: str) -> dict[str, Any]:
    raw = await load_json_payload(db, wp_id, _K1_9_ITEM_ID, field='remark')
    if not isinstance(raw, dict):
        return {'tables': {'reversal': [], 'writeoff': []}, 'auditProcedures': '', 'auditNote': '', 'conclusion': ''}
    return raw


def _k1_9_export_rows(payload: dict) -> list[list[Any]]:
    out: list[list[Any]] = []
    tables = payload.get('tables') or {}
    for r in tables.get('reversal') or []:
        if not isinstance(r, dict):
            continue
        out.append([
            '转回', safe_str(r.get('unit')), safe_str(r.get('reason')), safe_str(r.get('method')),
            safe_str(r.get('basis')), safe_float(r.get('amount')), safe_float(r.get('accumProvision')),
            '', '', '', safe_str(r.get('isReasonable')), safe_str(r.get('analysis')), safe_str(r.get('indexNo')),
        ])
    for r in tables.get('writeoff') or []:
        if not isinstance(r, dict):
            continue
        out.append([
            '核销', safe_str(r.get('unit')), safe_str(r.get('reason')), '', '',
            safe_float(r.get('amount')), '', safe_str(r.get('nature')), safe_str(r.get('procedure')),
            safe_str(r.get('relatedParty')), safe_str(r.get('isReasonable')), safe_str(r.get('analysis')),
            safe_str(r.get('indexNo')),
        ])
    return out


def _k1_9_build_workbook(payload: dict | None, template_only: bool = False):
    wb = Workbook()
    ws = wb.active
    ws.title = 'K1-9'
    ws.append(_K1_9_HEADERS)
    ws.freeze_panes = 'A2'
    if not template_only and payload:
        for row in _k1_9_export_rows(payload):
            ws.append(row)
    elif template_only:
        ws.append(['转回', '示例单位', '收回货款', '银行转账', '账龄较长', 10000, 12000, '', '', '', '合理', '', ''])
    return wb


def _k1_9_parse_row(row: tuple, headers: list[str]) -> tuple[str, dict]:
    section = safe_str(col_val(row, headers, '类别'))
    is_writeoff = section in ('核销', 'writeoff')
    base = {
        'id': str(uuid4()),
        'unit': safe_str(col_val(row, headers, '单位名称')),
        'reason': safe_str(col_val(row, headers, '转回原因/核销原因')),
        'amount': safe_float(col_val(row, headers, '收回或转回金额/核销金额')),
        'isReasonable': safe_str(col_val(row, headers, '合理性')) or '待核实',
        'analysis': safe_str(col_val(row, headers, '合理性分析')),
        'indexNo': safe_str(col_val(row, headers, '索引号')),
    }
    if is_writeoff:
        return 'writeoff', {
            **base,
            'nature': safe_str(col_val(row, headers, '其他应收款的性质')),
            'procedure': safe_str(col_val(row, headers, '履行的核销程序')),
            'relatedParty': safe_str(col_val(row, headers, '是否关联方往来')) or '否',
        }
    return 'reversal', {
        **base,
        'method': safe_str(col_val(row, headers, '收回方式')),
        'basis': safe_str(col_val(row, headers, '原确定坏账准备的依据')),
        'accumProvision': safe_float(col_val(row, headers, '收回/转回前累计已计提')),
    }


def _k1_9_parse_import(content: bytes) -> tuple[dict[str, Any], list[str], int]:
    try:
        actual, raw_rows = parse_upload_xlsx(content, ['类别', '单位名称'], header_row=1)
    except ValueError as e:
        return {}, [str(e)], 0
    reversal: list[dict] = []
    writeoff: list[dict] = []
    for row in raw_rows:
        if not safe_str(col_val(row, actual, '单位名称')):
            continue
        kind, parsed = _k1_9_parse_row(row, actual)
        if kind == 'writeoff':
            writeoff.append(parsed)
        else:
            reversal.append(parsed)
    imported = len(reversal) + len(writeoff)
    payload = {'tables': {'reversal': reversal, 'writeoff': writeoff}}
    errors: list[str] = []
    if imported == 0:
        errors.append('未解析到有效转回/核销行')
    return payload, errors, imported


async def _k1_9_import_handler(db: AsyncSession, wp_id: str, payload: dict[str, Any]) -> None:
    full, _ = await _k1_9_load_bundle(db, wp_id)
    if not isinstance(full, dict):
        full = {}
    if 'tables' in payload:
        full['tables'] = payload['tables']
    await upsert_json_payload(db, wp_id, _K1_9_ITEM_ID, full, field='remark')


async def _k1_9_export_loader(db: AsyncSession, wp_id: str) -> dict[str, Any]:
    return await _k1_9_load_bundle(db, wp_id)


# ────────────────────────────────────────────────────────────
# Sheet Specs 汇总
# ────────────────────────────────────────────────────────────
_K1_SPECS: dict[str, dict[str, Any]] = {
    "K1-1": {
        "item_id": "K1-1-receivable-count",
        "storage_field": "remark",
        "title": "K1-1 其他应收款审定表",
        "export_loader": _k1_1_export_loader,
        "build_workbook": _k1_1_build_workbook,
        "parse_import": _k1_1_parse_import,
        "import_handler": _k1_1_import_handler,
        "guidance": [
            "K1-1 审定表 编制说明",
            "",
            "多 sheet 结构：组合原值/组合坏账/账龄原值/账龄坏账/性质原值/性质坏账/报表核对/文本说明。",
            "宽表列：期初(未审/AJE/RJE/审定) + 期末(未审/AJE/RJE/审定) + 变动额/变动率/原因分析。",
            "审定=未审+AJE+RJE；变动超30%须在原因分析列说明。",
            "组合名称须与 K1-6/K1-8 一致；未审数可从 K1-2 同步。",
            "报表核对：其他应收款合计 vs K1-1 净值审定。",
        ],
    },
    "K1-3": {
        "item_id": _K1_3_ITEM_ID,
        "storage_field": "remark",
        "title": "K1-3 坏账准备明细表",
        "export_loader": _k1_3_export_loader,
        "build_workbook": _k1_3_build_workbook,
        "parse_import": _k1_3_parse_import,
        "import_handler": _k1_3_import_handler,
        "guidance": [
            "K1-3 坏账准备明细 编制说明",
            "",
            "多 sheet：坏账明细 / 三阶段转入转出 / 文本说明。",
            "期末账面=期初审定+计提+其他增加-转回-核销-其他减少；期末审定=期末账面+期末调整。",
            "须与 K1-8 测算、K1-9 转回核销勾稽。",
        ],
    },
    "K1-2": {
        "item_id": "K1-2-rows",
        "storage_field": "remark",
        "title": "K1-2 其他应收款明细表",
        "headers": _K1_2_HEADERS,
        "field_keys": _K1_2_KEYS,
        # 动态账龄列头（Task 12.1）：导出时基础列 + 项目账龄配置派生的 3N 账龄列（期初/期末未审/期末审定）
        "aging": {
            "subject": "K1",
            "base_headers": [
                "往来对象", "性质", "关联关系", "期初余额", "期末余额",
                "阶段", "坏账准备", "净值", "凭证号", "结论", "备注",
            ],
            "base_field_keys": [
                "counterparty", "nature", "relatedParty", "openingBalance", "closingBalance",
                "stage", "badDebtProvision", "netValue", "voucherNo", "conclusion", "remark",
            ],
        },
        "guidance": [
            "K1-2 明细表 编制说明",
            "",
            "17列对应：往来对象/性质/关联关系/期初余额/期末余额/1年内~5年以上(6档账龄)/阶段/坏账准备/净值/凭证号/结论/备注。",
            "期末余额应等于各账龄区间之和。净值=期末余额-坏账准备。",
            "账龄区间金额为数值型，单位：元。",
        ],
    },
    "K1-4": {
        "item_id": "K1-4-adj-entries",
        # 前端 useK1Adjustment（及 K1-7/K1-12 推送）读写 remark 列，工厂默认 conclusion 会写错列（Task 2.7）
        "storage_field": "remark",
        "title": "K1-4 其他应收款调整分录汇总表",
        "headers": _K1_4_HEADERS,
        "field_keys": _K1_4_KEYS,
        "guidance": [
            "K1-4 调整分录汇总 编制说明",
            "",
            "类别填：账项调整 / 报表调整 / 其他。",
            "账项调整影响审定数；报表调整仅影响列报。",
            "仅列示与其他应收款（1221）及坏账准备（1231）相关的审计调整。",
            "可与中央调整分录模块双向同步；整表借贷须平衡。",
        ],
    },
    "K1-5": {
        "item_id": "K1-5-rows",
        "storage_field": "remark",
        "title": "K1-5 大额其他应收款情况分析表",
        "headers": _K1_5_HEADERS,
        "field_keys": _K1_5_KEYS,
        "guidance": [
            "K1-5 大额分析 编制说明",
            "",
            "填列金额较大（超过重要性水平）的其他应收款，逐笔分析形成原因及收回可能性。",
            "收回可能性填：很可能/可能/极小可能。",
        ],
    },
    "K1-6": {
        "item_id": "K1-6-combos",
        "storage_field": "remark",
        "title": "K1-6 信用减值损失会计政策检查",
        "export_loader": _k1_6_export_loader,
        "build_workbook": _k1_6_build_workbook,
        "parse_import": _k1_6_parse_import,
        "import_handler": _k1_6_import_handler,
        "guidance": [
            "K1-6 会计政策检查 编制说明",
            "",
            "多 sheet 结构：组合划分 / 同业对比 / K2账龄损失率 / 文本说明。",
            "组合划分须与 K1-7 三阶段、K1-8 坏账测算一致；K2 调整后损失率可推送至 K1-8。",
            "与被审计单位可比填：是/否/部分一致。",
            "损失率为小数（0.05 = 5%）。",
        ],
    },
    "K1-7": {
        "item_id": "K1-7-rows",
        "storage_field": "remark",
        "title": "K1-7 三阶段划分检查表",
        "headers": _K1_7_HEADERS,
        "field_keys": _K1_7_KEYS,
        "guidance": [
            "K1-7 三阶段划分 编制说明",
            "",
            "阶段判定规则：已减值→Stage3；信用风险显著增加→Stage2；否则→Stage1。",
            "信用风险是否显著增加 / 是否已发生信用减值 填 是/否。",
            "划分阶段填 1/2/3 或 Stage1/Stage2/Stage3。",
        ],
    },
    "K1-8": {
        "item_id": "K1-8-rows",
        "storage_field": "remark",
        "title": "K1-8 坏账准备测算（账龄+ECL合并宽表）",
        "headers": _K1_8_HEADERS,
        "field_keys": _K1_8_KEYS,
        "guidance": [
            "K1-8 坏账测算 编制说明",
            "",
            "前4列为账龄迁徙区段：账龄区间/期末余额/迁徙率/预期损失率。",
            "后6列为ECL测算区段：往来对象/EAD/PD/LGD/企业计提/测算结论。",
            "ECL=EAD×PD×LGD；预期损失=期末余额×预期损失率。",
            "两区段行数可能不同，空行跳过。",
        ],
    },
    "K1-9": {
        "item_id": _K1_9_ITEM_ID,
        "storage_field": "remark",
        "title": "K1-9 坏账准备转回(收回)核销检查表",
        "export_loader": _k1_9_export_loader,
        "build_workbook": _k1_9_build_workbook,
        "parse_import": _k1_9_parse_import,
        "import_handler": _k1_9_import_handler,
        "guidance": [
            "K1-9 转回/核销检查 编制说明",
            "",
            "类别填「转回」或「核销」；转回行填收回方式/原计提依据；核销行填性质/核销程序/是否关联方。",
            "合理性填：合理/不合理/待核实。合计须与 K1-3 本期转回/核销列勾稽。",
        ],
    },
    "K1-11": {
        "item_id": _K1_11_ITEM_ID,
        "storage_field": "remark",
        "title": "K1-11 其他应收款关联方及交易检查表",
        "headers": _K1_11_HEADERS,
        "export_loader": _k1_11_export_loader,
        "build_workbook": _k1_11_build_workbook,
        "parse_import": _k1_11_parse_import,
        "import_handler": _k1_11_import_handler,
        "guidance": [
            "K1-11 关联方及交易检查表 编制说明",
            "",
            "16列：关联方|关系|期初|借方|贷方|期末|坏账|账面价值|账龄|款项性质|"
            "期后收款|是否公允|是否披露|资金占用|索引|备注。",
            "期末=期初+借方−贷方；账面价值=期末−坏账准备。",
            "可从 K1-2 导入关联方行；期后收款凭证检查详见 K1-12。",
        ],
    },
}

router = create_cycle_import_export_router(tag="k1-import-export", api_prefix="k1", specs=_K1_SPECS)
