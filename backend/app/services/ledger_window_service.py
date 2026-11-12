"""Bounded Ledger windows with exact summaries and signed keyset cursors.

Canonical order is ``voucher_date NULLS LAST, voucher_no NULLS LAST, id``.
Running balances are computed over every canonical row, then display filters are
applied, so filtering never changes the balance attached to a business row.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Literal, Protocol
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import JSONB

from app.models.audit_platform_models import TbAuxBalance, TbAuxLedger, TbBalance, TbLedger
from app.schemas.ledger_window import (
    LedgerMonthSummary,
    LedgerWindowPage,
    LedgerWindowQuery,
    LedgerWindowResponse,
    LedgerWindowSubtotal,
    LedgerWindowSummary,
)
from app.services.dataset_service import DatasetService
from app.services.ledger_penetration_service import _attach_extra_fields
from app.services import ledger_window_cursor

Kind = Literal["ledger", "aux_ledger"]


class SummaryCache(Protocol):
    """首窗摘要的长效缓存（Redis 实现见 ledger_window_cache.RedisSummaryCache）。"""

    async def get(self, key: str) -> dict[str, Any] | None: ...

    async def set(self, key: str, value: dict[str, Any]) -> None: ...
_MONEY = Decimal("0.01")
_V2_SIGN = "v2_category_natural_positive"


def _money(value: Any) -> str:
    amount = Decimal(str(value or 0)).quantize(_MONEY, rounding=ROUND_HALF_EVEN)
    return format(amount, "f")


def _direction(value: Decimal) -> Literal["debit", "credit"]:
    return "credit" if value < 0 else "debit"


def _amount(value: Decimal) -> str:
    return _money(abs(value))


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _account_condition(table: sa.Table, account_code: str) -> sa.ColumnElement:
    if account_code == "*":
        # 全部科目：不加任何科目谓词（LIKE '%' 会迫使每行回表读 account_code，也挡住仅索引扫描）
        return sa.true()
    if account_code.endswith("*"):
        return table.c.account_code.like(_escape_like(account_code[:-1]) + "%", escape="\\")
    return table.c.account_code == account_code


def _scope_conditions(
    table: sa.Table,
    project_id: UUID,
    dataset_id: UUID,
    query: LedgerWindowQuery,
    *,
    auxiliary: bool,
) -> list[sa.ColumnElement]:
    conditions = [
        table.c.project_id == project_id,
        table.c.year == query.year,
        table.c.dataset_id == dataset_id,
        table.c.is_deleted == sa.false(),
        _account_condition(table, query.account_code),
    ]
    if auxiliary:
        # 不指定辅助类型 = 浏览该科目（或全部科目）下所有维度的明细行
        if query.aux_type:
            conditions.append(table.c.aux_type == query.aux_type)
        if query.aux_code is not None:
            conditions.append(table.c.aux_code == query.aux_code)
    return conditions


ALL_ACCOUNTS = "*"


def _is_browse_all(query: LedgerWindowQuery, *, auxiliary: bool) -> bool:
    """浏览模式：未限定科目，或辅助明细未限定维度类型。此模式下余额类数字不具备会计含义。"""
    return query.account_code == ALL_ACCOUNTS or (auxiliary and not query.aux_type)


def _range_conditions(table: sa.Table, query: LedgerWindowQuery) -> list[sa.ColumnElement]:
    conditions: list[sa.ColumnElement] = []
    if query.date_from is not None:
        conditions.append(table.c.voucher_date >= query.date_from)
    if query.date_to is not None:
        conditions.append(table.c.voucher_date <= query.date_to)
    return conditions


def _visible_condition(columns: Any, query: LedgerWindowQuery, *, auxiliary: bool) -> sa.ColumnElement:
    predicates: list[sa.ColumnElement] = []
    if query.keyword:
        pattern = f"%{_escape_like(query.keyword.lower())}%"
        candidates = [columns.summary, columns.voucher_no, sa.cast(columns.voucher_date, sa.String)]
        if auxiliary:
            candidates.extend([columns.aux_code, columns.aux_name])
        else:
            candidates.append(columns.counterpart_account)
        predicates.append(sa.or_(*[
            sa.func.lower(sa.func.coalesce(col, "")).like(pattern, escape="\\") for col in candidates
        ]))
    if query.amount_dir == "debit":
        predicates.append(sa.func.coalesce(columns.debit_amount, 0) > 0)
    elif query.amount_dir == "credit":
        predicates.append(sa.func.coalesce(columns.credit_amount, 0) > 0)
    return sa.and_(*predicates) if predicates else sa.true()


def _signed_opening(table: sa.Table) -> sa.ColumnElement:
    raw = sa.func.coalesce(table.c.opening_balance, 0)
    is_v2 = table.c.sign_convention_version == _V2_SIGN
    return sa.case(
        (sa.and_(is_v2, table.c.opening_direction == "credit"), -sa.func.abs(raw)),
        (sa.and_(is_v2, table.c.opening_direction == "debit"), sa.func.abs(raw)),
        else_=raw,
    )


def _order(columns: Any) -> tuple[sa.ColumnElement, ...]:
    return (
        columns.voucher_date.asc().nulls_last(),
        columns.voucher_no.asc().nulls_last(),
        columns.id.asc(),
    )


def _after_cursor(table: sa.Table, key: dict[str, Any], *, nullable: bool) -> sa.ColumnElement:
    last_id = UUID(str(key["id"]))
    last_no = key.get("no")
    last_date = date.fromisoformat(key["date"]) if key.get("date") else None
    if not nullable:
        if last_date is None or last_no is None:
            raise HTTPException(status_code=400, detail={
                "error_code": "LEDGER_CURSOR_INVALID",
                "message": "普通序时账游标缺少日期或凭证号，请刷新后重试",
            })
        # 普通序时账两列都 NOT NULL；行值比较让 PostgreSQL 用完整排序索引范围扫描，
        # 而非日期条件的 OR 分支退化成 Bitmap + 外部排序。
        return sa.tuple_(table.c.voucher_date, table.c.voucher_no, table.c.id) > sa.tuple_(
            last_date, last_no, last_id,
        )
    id_after = table.c.id > last_id
    if last_no is None:
        no_after = sa.and_(table.c.voucher_no.is_(None), id_after)
    else:
        no_after = sa.or_(table.c.voucher_no > last_no, table.c.voucher_no.is_(None),
                          sa.and_(table.c.voucher_no == last_no, id_after))
    if last_date is None:
        return sa.and_(table.c.voucher_date.is_(None), no_after)
    return sa.or_(
        table.c.voucher_date > last_date,
        table.c.voucher_date.is_(None),
        sa.and_(table.c.voucher_date == last_date, no_after),
    )


def _month_key(value: Any) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m") if hasattr(value, "strftime") else str(value)[:7]


def _query_identity(kind: Kind, project_id: UUID, query: LedgerWindowQuery) -> dict[str, Any]:
    return {"kind": kind, "project_id": str(project_id), "year": query.year,
            "account_code": query.account_code, "date_from": query.date_from, "date_to": query.date_to,
            "keyword": query.keyword or "", "amount_dir": query.amount_dir,
            "aux_type": query.aux_type or "", "aux_code": query.aux_code,
            "limit": query.limit}


class LedgerWindowService:
    def __init__(self, db: AsyncSession, summary_cache: "SummaryCache | None" = None):
        self.db = db
        self.summary_cache = summary_cache

    async def _active_dataset(self, project_id: UUID, year: int) -> UUID:
        try:
            dataset_id = await DatasetService.get_active_dataset_id(self.db, project_id, year)
        except Exception as exc:
            raise HTTPException(status_code=503, detail={
                "error_code": "LEDGER_DATASET_UNAVAILABLE",
                "message": "无法确认当前生效数据集，请稍后重试",
            }) from exc
        if dataset_id is None:
            raise HTTPException(status_code=409, detail={
                "error_code": "LEDGER_ACTIVE_DATASET_REQUIRED",
                "message": "当前项目年度没有生效数据集，不能打开窗口账簿",
            })
        return dataset_id

    async def _opening(
        self,
        project_id: UUID,
        dataset_id: UUID,
        query: LedgerWindowQuery,
        *,
        auxiliary: bool,
    ) -> Decimal:
        if _is_browse_all(query, auxiliary=auxiliary):
            # 全部科目 / 跨维度浏览：把各科目（含父子级）或各维度期初加总没有会计意义，且会重复计入
            return Decimal(0)
        table = TbAuxBalance.__table__ if auxiliary else TbBalance.__table__
        conditions = _scope_conditions(table, project_id, dataset_id, query, auxiliary=auxiliary)
        value = (await self.db.execute(
            sa.select(sa.func.coalesce(sa.func.sum(_signed_opening(table)), 0)).where(*conditions)
        )).scalar_one()
        return Decimal(str(value or 0))

    async def _range_opening(
        self,
        table: sa.Table,
        project_id: UUID,
        dataset_id: UUID,
        query: LedgerWindowQuery,
        annual_opening: Decimal,
        *,
        auxiliary: bool,
    ) -> Decimal:
        if query.date_from is None:
            return annual_opening
        movement = sa.func.coalesce(table.c.debit_amount, 0) - sa.func.coalesce(table.c.credit_amount, 0)
        prior = (await self.db.execute(
            sa.select(sa.func.coalesce(sa.func.sum(movement), 0)).where(
                *_scope_conditions(table, project_id, dataset_id, query, auxiliary=auxiliary),
                table.c.voucher_date < query.date_from,
            )
        )).scalar_one()
        return annual_opening + Decimal(str(prior or 0))

    async def _summary(
        self,
        table: sa.Table,
        project_id: UUID,
        dataset_id: UUID,
        query: LedgerWindowQuery,
        annual_opening: Decimal,
        range_opening: Decimal,
        *,
        auxiliary: bool,
    ) -> LedgerWindowSummary:
        scope = _scope_conditions(table, project_id, dataset_id, query, auxiliary=auxiliary)
        in_range = [*scope, *_range_conditions(table, query)]
        visible = _visible_condition(table.c, query, auxiliary=auxiliary)
        if _is_browse_all(query, auxiliary=auxiliary):
            # 浏览模式没有会计意义的累计余额：显示条件（关键字 / 借贷方向）直接下推到 WHERE，
            # 只统计命中行，不再对每个扫描行求值 FILTER（实测 149 万行关键字汇总 2.4s → 1.0s）
            in_range = [*in_range, visible]
            visible = sa.true()
        if _is_browse_all(query, auxiliary=auxiliary) and self.db.bind.dialect.name == "postgresql":
            # 浏览全部的汇总要扫百万级行：并行聚合会占用 /dev/shm，容器默认 64MB 时直接
            # DiskFullError（实测 430 万行辅助明细 500）。本事务内关闭并行，顺序扫描不占共享内存。
            await self.db.execute(sa.text("SET LOCAL max_parallel_workers_per_gather = 0"))
        movement = sa.func.coalesce(table.c.debit_amount, 0) - sa.func.coalesce(table.c.credit_amount, 0)
        year_part = sa.extract("year", table.c.voucher_date)
        month_part = sa.extract("month", table.c.voucher_date)
        stmt = (
            sa.select(
                year_part.label("year_part"), month_part.label("month_part"),
                sa.func.count().label("canonical_count"),
                sa.func.coalesce(sa.func.sum(movement), 0).label("canonical_movement"),
                sa.func.count().filter(visible).label("visible_count"),
                sa.func.coalesce(sa.func.sum(sa.func.coalesce(table.c.debit_amount, 0)).filter(visible), 0)
                .label("visible_debit"),
                sa.func.coalesce(sa.func.sum(sa.func.coalesce(table.c.credit_amount, 0)).filter(visible), 0)
                .label("visible_credit"),
            )
            .where(*in_range)
            .group_by(year_part, month_part)
            .order_by(year_part.asc().nulls_last(), month_part.asc().nulls_last())
        )
        rows = (await self.db.execute(stmt)).mappings().all()
        running = range_opening
        total, debit_total, credit_total, undated = 0, Decimal(0), Decimal(0), 0
        months: list[LedgerMonthSummary] = []
        for row in rows:
            running += Decimal(str(row["canonical_movement"] or 0))
            visible_count = int(row["visible_count"] or 0)
            if row["year_part"] is None:
                key, label = None, "未注明日期合计"
                undated = int(row["canonical_count"] or 0)
            else:
                key = f"{int(row['year_part']):04d}-{int(row['month_part']):02d}"
                label = f"{key} 本月合计"
            if visible_count <= 0:
                continue
            debit, credit = Decimal(str(row["visible_debit"] or 0)), Decimal(str(row["visible_credit"] or 0))
            total += visible_count
            debit_total += debit
            credit_total += credit
            months.append(LedgerMonthSummary(
                month=key, label=label, row_count=visible_count,
                debit_total=_money(debit), credit_total=_money(credit),
                closing_balance=_amount(running), closing_balance_signed=_money(running),
                closing_direction=_direction(running),
            ))
        warnings = [f"有 {undated} 条分录没有日期，按规范账序排在最后"] if undated else []
        return LedgerWindowSummary(
            total=total,
            annual_opening=_amount(annual_opening), annual_opening_signed=_money(annual_opening),
            annual_opening_direction=_direction(annual_opening),
            range_opening=_amount(range_opening), range_opening_signed=_money(range_opening),
            range_opening_direction=_direction(range_opening),
            debit_total=_money(debit_total), credit_total=_money(credit_total),
            undated_count=undated, months=months, warnings=warnings,
        )

    async def _extra_columns(
        self,
        table: sa.Table,
        project_id: UUID,
        dataset_id: UUID,
        query: LedgerWindowQuery,
        *,
        auxiliary: bool,
    ) -> list[str]:
        base_conditions = [
            *_scope_conditions(table, project_id, dataset_id, query, auxiliary=auxiliary),
            *_range_conditions(table, query),
        ]
        if not _is_browse_all(query, auxiliary=auxiliary):
            # 浏览模式只抽样前 2000 行推断额外列，不带关键字条件（稀有关键字会让抽样扫完整个范围）
            base_conditions.append(_visible_condition(table.c, query, auxiliary=auxiliary))
        source_stmt = sa.select(
            sa.case(
                (sa.func.jsonb_typeof(table.c.raw_extra) == "object", table.c.raw_extra),
                else_=sa.cast(sa.literal("{}"), JSONB),
            ).label("raw_extra")
        ).where(*base_conditions)
        if _is_browse_all(query, auxiliary=auxiliary):
            # 全量扫描上百万行的 raw_extra 键代价过高：浏览模式只抽样前 2000 行推断额外列
            source_stmt = source_stmt.limit(2000)
        source = source_stmt.subquery("extra_source")
        keys = (sa.func.jsonb_object_keys(source.c.raw_extra)
                .table_valued("key").render_derived().lateral("extra_keys"))
        stmt = (sa.select(keys.c.key).select_from(source.join(keys, sa.true()))
                .where(keys.c.key.not_like("\\_%", escape="\\"))
                .distinct().order_by(keys.c.key).limit(500))
        return [str(value) for value in (await self.db.execute(stmt)).scalars().all()]

    async def _page_rows(
        self,
        table: sa.Table,
        project_id: UUID,
        dataset_id: UUID,
        query: LedgerWindowQuery,
        anchor: Decimal,
        key: dict[str, Any] | None,
        *,
        auxiliary: bool,
    ) -> list[dict[str, Any]]:
        movement = (sa.func.coalesce(table.c.debit_amount, 0)
                    - sa.func.coalesce(table.c.credit_amount, 0)).label("_movement")
        columns = [
            table.c.id, table.c.voucher_date, table.c.voucher_no,
            table.c.account_code, table.c.account_name,
            table.c.debit_amount, table.c.credit_amount,
            table.c.summary, table.c.voucher_type, table.c.company_code,
            table.c.accounting_period, table.c.raw_extra,
        ]
        if auxiliary:
            columns.extend([table.c.aux_type, table.c.aux_code, table.c.aux_name])
        else:
            columns.append(table.c.counterpart_account)
        conditions = [*_scope_conditions(table, project_id, dataset_id, query, auxiliary=auxiliary),
                      *_range_conditions(table, query)]
        if key is not None:
            conditions.append(_after_cursor(table, key, nullable=auxiliary))
        base = sa.select(*columns, movement).where(*conditions).cte("ledger_window_base")
        if _is_browse_all(query, auxiliary=auxiliary):
            # 浏览模式没有会计意义的运行余额（前端不展示）：跳过全量窗口累计，
            # 让 ORDER BY ... LIMIT 直接走排序索引取前 N 行。
            running = sa.literal(Decimal(0), type_=sa.Numeric(38, 2)).label("running_balance_signed")
        else:
            running = (
                sa.literal(anchor, type_=sa.Numeric(38, 2))
                + sa.func.sum(base.c._movement).over(order_by=_order(base.c), rows=(None, 0))
            ).label("running_balance_signed")
        ranked = sa.select(*[base.c[col.key] for col in columns], running).cte("ledger_window_ranked")
        stmt = (sa.select(ranked)
                .where(_visible_condition(ranked.c, query, auxiliary=auxiliary))
                .order_by(*_order(ranked.c)).limit(query.limit + 1))
        return [dict(row._mapping) for row in (await self.db.execute(stmt)).all()]

    @staticmethod
    def _serialize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        clean = _attach_extra_fields(rows)
        for row in clean:
            row["id"] = str(row["id"])
            if row.get("voucher_date") is not None:
                row["voucher_date"] = row["voucher_date"].isoformat()
            for field in ("debit_amount", "credit_amount"):
                row[field] = None if row.get(field) is None else _money(row[field])
            signed = Decimal(str(row.pop("running_balance_signed") or 0))
            row["running_balance_signed"] = _money(signed)
            row["running_balance"] = _amount(signed)
            row["running_balance_direction"] = _direction(signed)
        return clean

    @staticmethod
    def _subtotals(
        entries: list[dict[str, Any]],
        lookahead: dict[str, Any] | None,
        summary: LedgerWindowSummary,
    ) -> list[LedgerWindowSubtotal]:
        by_month = {item.month: item for item in summary.months}
        subtotals: list[LedgerWindowSubtotal] = []
        for index, row in enumerate(entries):
            next_row = entries[index + 1] if index + 1 < len(entries) else lookahead
            current_month = _month_key(row.get("voucher_date"))
            next_month = _month_key(next_row.get("voucher_date")) if next_row else object()
            if current_month != next_month and current_month in by_month:
                subtotals.append(LedgerWindowSubtotal(
                    after_entry_id=str(row["id"]), month=by_month[current_month],
                ))
        return subtotals

    async def _first_page_state(
        self,
        kind: Kind,
        table: sa.Table,
        project_id: UUID,
        dataset_id: UUID,
        query: LedgerWindowQuery,
        *,
        auxiliary: bool,
    ) -> tuple[LedgerWindowSummary, Decimal, list[str]]:
        """首窗需要的精确摘要 / 范围期初 / 额外列。

        浏览模式（全部科目）的摘要要扫百万行，且与用户、每页条数无关，只取决于
        数据集 + 筛选条件：命中 ``summary_cache`` 时直接复用（键含数据集 ID，重新导入自然失效）。
        """
        browse = _is_browse_all(query, auxiliary=auxiliary)
        cache = self.summary_cache if browse else None
        cache_key = None
        if cache is not None:
            identity = {**_query_identity(kind, project_id, query), "limit": 0, "dataset": str(dataset_id)}
            cache_key = f"{kind}:{project_id}:{dataset_id}:{ledger_window_cursor.query_fingerprint(identity)[:32]}"
            hit = await cache.get(cache_key)
            if hit is not None:
                try:
                    return (LedgerWindowSummary.model_validate(hit["summary"]),
                            Decimal(str(hit["anchor"])), list(hit["extra_columns"]))
                except (KeyError, TypeError, ValueError):
                    pass  # 缓存内容损坏 ⇒ 重算

        annual_opening = await self._opening(project_id, dataset_id, query, auxiliary=auxiliary)
        range_opening = await self._range_opening(
            table, project_id, dataset_id, query, annual_opening, auxiliary=auxiliary,
        )
        summary = await self._summary(
            table, project_id, dataset_id, query, annual_opening, range_opening, auxiliary=auxiliary,
        )
        extra_columns = await self._extra_columns(table, project_id, dataset_id, query, auxiliary=auxiliary)
        if browse and auxiliary:
            summary.warnings = [*summary.warnings,
                                "当前为浏览模式：未限定科目/辅助类型，余额列不适用；"
                                "辅助明细同一凭证可能因多个维度重复出现，合计仅供浏览"]
        if cache is not None and cache_key is not None:
            await cache.set(cache_key, {
                "summary": summary.model_dump(mode="json"),
                "anchor": str(range_opening),
                "extra_columns": extra_columns,
            })
        return summary, range_opening, extra_columns

    async def fetch(
        self,
        kind: Kind,
        project_id: UUID,
        subject: str,
        query: LedgerWindowQuery,
    ) -> LedgerWindowResponse:
        auxiliary = kind == "aux_ledger"
        table = TbAuxLedger.__table__ if auxiliary else TbLedger.__table__
        dataset_id = await self._active_dataset(project_id, query.year)
        fingerprint = ledger_window_cursor.query_fingerprint(_query_identity(kind, project_id, query))
        cursor_payload: dict[str, Any] | None = None
        if query.cursor:
            cursor_payload = ledger_window_cursor.decode(
                query.cursor, subject=subject, fingerprint=fingerprint, dataset_id=str(dataset_id),
            )

        if cursor_payload is None:
            summary, range_opening, extra_columns = await self._first_page_state(
                kind, table, project_id, dataset_id, query, auxiliary=auxiliary,
            )
            anchor, key, page_index, start = range_opening, None, 0, 1
        else:
            try:
                summary = LedgerWindowSummary.model_validate(cursor_payload["m"])
                anchor = Decimal(str(cursor_payload["a"]))
                key = dict(cursor_payload["k"])
                page_index = int(cursor_payload["i"])
                start = int(cursor_payload["n"])
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail={
                    "error_code": "LEDGER_CURSOR_INVALID",
                    "message": "翻页游标缺少窗口状态，请刷新后重试",
                }) from exc
            extra_columns = []

        raw_rows = await self._page_rows(
            table, project_id, dataset_id, query, anchor, key, auxiliary=auxiliary,
        )
        has_more = len(raw_rows) > query.limit
        page_raw, lookahead = raw_rows[:query.limit], (raw_rows[query.limit] if has_more else None)
        entries = self._serialize_rows(page_raw)
        subtotals = self._subtotals(entries, lookahead, summary)
        end = start + len(entries) - 1
        next_cursor = None
        if has_more and entries:
            last = entries[-1]
            next_cursor = ledger_window_cursor.issue({
                "s": subject, "q": fingerprint, "d": str(dataset_id),
                "k": {"date": last.get("voucher_date"), "no": last.get("voucher_no"), "id": last["id"]},
                "a": last["running_balance_signed"], "m": summary.model_dump(mode="json"),
                "i": page_index + 1, "n": end + 1,
            })
        return LedgerWindowResponse(
            kind=kind, dataset_id=str(dataset_id), query_fingerprint=fingerprint,
            entries=entries, summary=summary,
            page=LedgerWindowPage(
                limit=query.limit, page_index=page_index, start=start if entries else 0,
                end=end if entries else 0, has_more=has_more, next_cursor=next_cursor,
            ),
            extra_columns=extra_columns, subtotals=subtotals,
        )
