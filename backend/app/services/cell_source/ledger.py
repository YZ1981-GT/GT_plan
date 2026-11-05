"""账务查询（科目余额表 / 序时账）的单元格来源（spec citar-cell-source-hover R6，design §8）。

数据来自导入：当前生效数据集 → 导入作业 → 用户确认的字段映射（``import_jobs.custom_mapping.confirmed_mappings``）。
- 列级（``col:{字段}``）：该字段取自哪个文件、哪个 sheet 的哪个表头；推导出来的列写推导方式（与 ``ledger_import.converter`` 的分支对应）
- 行级（``row:{id}``，只给有特殊情况的行）：同一字段映射了多列时被舍弃的值（``_discarded_mappings``）、由辅助明细汇总的科目行、
  方向按科目类别推断、人工修改（导入原值、修改人、时间、原因）
导入时没有保存源文件行号，不提供。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbBalance, TbLedger
from app.models.dataset_models import DatasetStatus, ImportJob, LedgerDataset
from app.models.ledger_edit_models import LedgerManualEdit
from app.services.cell_source.schema import item, link, money, source
from app.services.ledger_import.sheet_mapping import mapping_locate_key, strip_store_prefix
from app.services.user_display_names import resolve_user_display_names

BALANCE_TYPES = ("balance", "aux_balance")
LEDGER_TYPES = ("ledger", "aux_ledger")
#: 页面列 → 来源字段（同一列可由多种映射字段得来）
BALANCE_COLUMNS: dict[str, tuple[str, ...]] = {
    "account_code": ("account_code",),
    "account_name": ("account_name",),
    "opening": ("opening_balance", "opening_debit", "opening_credit", "year_opening_debit", "year_opening_credit",
                "opening_direction", "direction"),
    "debit": ("year_debit", "debit_amount"),
    "credit": ("year_credit", "credit_amount"),
    "closing": ("closing_balance", "closing_debit", "closing_credit", "closing_direction", "direction"),
}
JOURNAL_COLUMNS: dict[str, tuple[str, ...]] = {
    "voucher_date": ("voucher_date",), "voucher_no": ("voucher_no",), "summary": ("summary",),
    "account_code": ("account_code",), "account_name": ("account_name",),
    "debit": ("debit_amount", "amount", "direction", "entry_direction"),
    "credit": ("credit_amount", "amount", "direction", "entry_direction"),
}
FIELD_LABELS = {
    "account_code": "科目编码", "account_name": "科目名称", "opening_balance": "期初余额", "opening_debit": "期初借方",
    "opening_credit": "期初贷方", "year_opening_debit": "年初借方", "year_opening_credit": "年初贷方",
    "opening_direction": "期初方向", "direction": "余额方向", "year_debit": "本年累计借方", "debit_amount": "借方发生额",
    "year_credit": "本年累计贷方", "credit_amount": "贷方发生额", "closing_balance": "期末余额", "closing_debit": "期末借方",
    "closing_credit": "期末贷方", "closing_direction": "期末方向", "voucher_date": "凭证日期", "voucher_no": "凭证号",
    "summary": "摘要", "amount": "金额（单列）", "entry_direction": "借贷方向", "accounting_period": "会计期间",
    "aux_dimensions": "辅助核算",
    # 下面这些不进账务查询的列，导入记录详情要列全（与导入页列映射下拉同名）
    "company_code": "组织编码", "voucher_type": "凭证类型", "preparer": "制单人", "currency_code": "币种",
    "level": "科目级次", "aux_type": "辅助类型", "aux_code": "辅助编码", "aux_name": "辅助名称",
    "entry_seq": "分录序号", "counterpart_account": "对方科目", "category": "科目类别",
}


def field_label(field: str, table_type: str | None = None) -> str:
    """标准字段中文名；``direction`` 在余额表是余额方向、在序时账是借贷方向。"""
    if field == "direction" and table_type in LEDGER_TYPES:
        return "借贷方向"
    return FIELD_LABELS.get(field, field)
_INFERRED_SOURCES = {"account_category_inferred", "account_category_inferred_low_confidence", "contra_account"}


def _derivation(col: str, fields: set[str]) -> list[str]:
    """推导方式（与 converter 的分支一致：年初优先、分列优先于余额 + 方向列、本年累计优先于本期）。"""
    notes: list[str] = []
    if col == "opening":
        if fields & {"year_opening_debit", "year_opening_credit"}:
            notes.append("期初 = 年初借方 − 年初贷方（年初列优先于期初列）")
        elif fields & {"opening_debit", "opening_credit"}:
            notes.append("期初 = 期初借方 − 期初贷方")
        elif "opening_balance" in fields:
            notes.append("期初取期初余额" + ("，借贷按方向列" if fields & {"opening_direction", "direction"} else "，方向按科目类别推断"))
    elif col == "closing":
        if fields & {"closing_debit", "closing_credit"}:
            notes.append("期末 = 期末借方 − 期末贷方")
        elif "closing_balance" in fields:
            notes.append("期末取期末余额" + ("，借贷按方向列" if fields & {"closing_direction", "direction"} else "，方向按科目类别推断"))
    elif col in ("debit", "credit"):
        if f"year_{col}" in fields:
            notes.append("取本年累计发生额（有本年累计列时不取本期发生额）")
        if "amount" in fields and f"{col}_amount" not in fields:
            notes.append("单金额列按借贷标识拆成借方 / 贷方")
    return notes


def _mapping_index(confirmed: list[dict], types: tuple[str, ...]) -> dict[str, list[dict]]:
    """标准字段 → [{file, sheet, header, column, by_user, locate}]。"""
    out: dict[str, list[dict]] = {}
    for m in confirmed:
        if m.get("table_type") not in types:
            continue
        for e in m.get("mapping_entries") or []:
            field = e.get("standard_field")
            if not field:
                continue
            out.setdefault(field, []).append({
                "file": strip_store_prefix(m.get("file_name") or ""), "sheet": m.get("sheet_name") or "",
                "header": e.get("original_header") or e.get("canonical_header") or "",
                "column": e.get("column_index"), "by_user": bool(m.get("confirmed_by_user")),
                "locate": mapping_locate_key(m.get("file_name"), m.get("sheet_name"), e.get("column_index")),
            })
    return out


async def _dataset(db: AsyncSession, project_id: UUID, year: int) -> dict:
    """当前生效数据集、产生它的导入作业（卡片链接跳导入记录）与其确认映射、激活人 / 时间。"""
    row = (await db.execute(
        sa.select(LedgerDataset.id, LedgerDataset.job_id, LedgerDataset.activated_at, LedgerDataset.activated_by,
                  LedgerDataset.created_by, ImportJob.custom_mapping)
        .outerjoin(ImportJob, ImportJob.id == LedgerDataset.job_id)
        .where(LedgerDataset.project_id == project_id, LedgerDataset.year == year,
               LedgerDataset.status == DatasetStatus.active)
        .order_by(LedgerDataset.activated_at.desc().nullslast()).limit(1)
    )).first()
    if row is None:
        return {"id": None, "job_id": None, "confirmed": [], "who": None, "at": None}
    who = row.activated_by or row.created_by
    names = await resolve_user_display_names(db, [who]) if who else {}
    confirmed = ((row.custom_mapping or {}).get("confirmed_mappings") or []) if isinstance(row.custom_mapping, dict) else []
    return {"id": row.id, "job_id": row.job_id, "confirmed": confirmed, "who": names.get(str(who)) if who else None,
            "at": row.activated_at.isoformat() if row.activated_at else None}


def _column_sources(ds: dict, columns: dict[str, tuple[str, ...]], types: tuple[str, ...], what: str) -> dict[str, dict]:
    index = _mapping_index(ds["confirmed"], types)
    when = " ".join(x for x in ((ds["at"] or "")[:10], f"由 {ds['who']} 导入" if ds["who"] else "") if x)
    head = f"导入的{what}" + (f"（{when}）" if when else "")
    job = str(ds["job_id"]) if ds.get("job_id") else None
    out: dict[str, dict] = {}
    for col, fields in columns.items():
        hits = [(f, h) for f in fields for h in index.get(f, [])]
        # 每项可点：跳到「数据导入」页这次导入的记录，定位到这一列的映射（R9）
        items = [item(f"{h['file']} · {h['sheet']} ·「{h['header']}」", detail=f"映射为「{field_label(f, types[0])}」"
                      + ("（用户确认）" if h["by_user"] else "（自动识别）"),
                      link_to=link("ledger_import", code=job, ref=h["locate"]) if job else None)
                 for f, h in hits]
        notes = _derivation(col, {f for f, _ in hits})
        if not ds["confirmed"]:
            notes.append("本数据集没有保存字段映射记录（旧导入或迁移来的数据），无法列出来源表头")
        elif not hits:
            notes.append("这一列没有映射到导入文件的表头，留空或由其他列推导")
        if col == "account_name" and len({h["header"] for f, h in hits if f == "account_name"}) > 1:
            notes.append("科目名称映射了多列，导入只取每行第一个非空的值；行上会写明被舍弃的值")
        out[f"col:{col}"] = source("import", head, None, items, notes=notes)
    return out


def _row_notes(raw: dict | None, direction_sources: tuple, inferred_known: bool = False) -> tuple[list[dict], list[str], str | None]:
    """行级：被舍弃的多列映射值、辅助明细汇总、方向推断（列上已写「按科目类别推断」时不逐行重复）。"""
    items, notes, issue = [], [], None
    raw = raw if isinstance(raw, dict) else {}
    discarded = raw.get("_discarded_mappings") or {}
    for field, vals in discarded.items():
        for v in vals or []:
            items.append(item(f"未采用「{v.get('header')}」：{v.get('value')}", None, sign=0,
                              detail=f"与「{FIELD_LABELS.get(field, field)}」映射到同一字段"))
    if discarded:
        issue = "同一字段映射了多列，导入只取了第一列，请核对字段映射"
    if raw.get("_aggregated_from_aux"):
        notes.append(f"本行由 {raw.get('_aux_row_count') or '多'} 条辅助核算明细汇总（导入文件里没有该科目的汇总行）")
    if not inferred_known and any(s in _INFERRED_SOURCES for s in direction_sources if s):
        notes.append("余额方向按科目类别推断（导入文件里没有方向列或借贷分列）")
    return items, notes, issue


async def _edits(db: AsyncSession, project_id: UUID, year: int, table: str, row_ids: list) -> dict[str, dict]:
    if not row_ids:
        return {}
    rows = (await db.execute(
        sa.select(LedgerManualEdit).where(
            LedgerManualEdit.project_id == project_id, LedgerManualEdit.year == year,
            LedgerManualEdit.table_name == table, LedgerManualEdit.action == "edit",
            LedgerManualEdit.row_id.in_(row_ids),
        ).order_by(LedgerManualEdit.edited_at)
    )).scalars().all()
    first: dict[str, Any] = {}
    last: dict[str, Any] = {}
    for e in rows:
        first.setdefault(str(e.row_id), e)
        last[str(e.row_id)] = e
    names = await resolve_user_display_names(db, [e.edited_by for e in last.values()])
    return {rid: {"before": first[rid].before or {}, "by": names.get(str(e.edited_by)) if e.edited_by else None,
                  "at": e.edited_at.isoformat() if e.edited_at else None, "reason": e.reason}
            for rid, e in last.items()}


def _row_source(raw, direction_sources, edit: dict | None, fields: dict[str, str], inferred_known: bool = False) -> dict | None:
    items, notes, issue = _row_notes(raw, direction_sources, inferred_known)
    manual = None
    if edit:
        before = edit["before"]
        orig = "，".join(f"{label} {money(before.get(k)) if k not in ('summary', 'voucher_no', 'account_name') else before.get(k)}"
                        for k, label in fields.items() if k in before)
        manual = {"value": None, "auto": None, "by_name": edit["by"], "at": edit["at"],
                  "note": f"导入原值：{orig}" + (f"；原因：{edit['reason']}" if edit["reason"] else "")}
    if not (items or notes or issue or manual):
        return None
    return source("manual" if manual else "import", "本行" + ("人工修改过" if manual else "导入时的情况"), None, items,
                  notes=notes, issue=issue, manual=manual)


_BAL_FIELDS = {"opening_balance": "期初", "debit_amount": "借方", "credit_amount": "贷方", "closing_balance": "期末"}
_LED_FIELDS = {"voucher_date": "日期", "voucher_no": "凭证号", "summary": "摘要", "account_name": "科目名称",
               "debit_amount": "借方", "credit_amount": "贷方"}


async def balance_sources(db: AsyncSession, project_id: UUID, year: int) -> dict:
    """科目余额表：``col:{列}`` + ``row:{id}``（只给有特殊情况的行）。"""
    from app.services.dataset_query import get_active_filter

    ds = await _dataset(db, project_id, year)
    cells = _column_sources(ds, BALANCE_COLUMNS, BALANCE_TYPES, "科目余额表")
    bal = TbBalance.__table__
    rows = (await db.execute(
        sa.select(bal.c.id, bal.c.raw_extra, bal.c.opening_direction_source, bal.c.closing_direction_source)
        .where(await get_active_filter(db, bal, project_id, year))
    )).fetchall()
    edits = await _edits(db, project_id, year, "balance", [r.id for r in rows])
    # 列上已写「方向按科目类别推断」（整表没有方向列 / 借贷分列）⇒ 行上不再逐行重复
    inferred_known = any("科目类别推断" in n for k in ("col:opening", "col:closing") for n in cells[k]["notes"])
    for r in rows:
        s = _row_source(r.raw_extra, (r.opening_direction_source, r.closing_direction_source), edits.get(str(r.id)),
                        _BAL_FIELDS, inferred_known)
        if s:
            cells[f"row:{r.id}"] = s
    return {"year": year, "cells": cells, "notices": []}


async def journal_sources(db: AsyncSession, project_id: UUID, year: int) -> dict:
    """序时账列级来源（行数大，行级按 ``journal_row_source`` 单取）。"""
    ds = await _dataset(db, project_id, year)
    return {"year": year, "cells": _column_sources(ds, JOURNAL_COLUMNS, LEDGER_TYPES, "序时账"), "notices": []}


async def journal_row_source(db: AsyncSession, project_id: UUID, year: int, row_id: UUID) -> dict | None:
    from app.services.dataset_query import get_active_filter

    led = TbLedger.__table__
    row = (await db.execute(
        sa.select(led.c.raw_extra, led.c.entry_direction_source).where(
            await get_active_filter(db, led, project_id, year), led.c.id == row_id,
        )
    )).first()
    if row is None:
        return None
    edits = await _edits(db, project_id, year, "ledger", [row_id])
    return _row_source(row.raw_extra, (row.entry_direction_source,), edits.get(str(row_id)), _LED_FIELDS)
