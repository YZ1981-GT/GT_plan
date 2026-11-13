"""试算表行的上游溯源（spec voucher-workflow-linkage-lineage-closure R8.1，design §10.1）。

统一溯源对 ``tb_row`` 原先只有附件子源（ADR-FHIC-16），试算表「数据溯源」点开什么都没有。这里按标准科目给四类上游：

1. 构成：本年度、全部主体合计的未审 / 调整 / 重分类 /（有时）底稿发布 / 审定；
2. 已批准、计入本科目的调整分录，逐组一条。口径与试算表调整列同源（``TrialBalanceService.recalc_adjustments``：
   分录行标准科目 = 本科目、已批准、按最终处理排除客户已入账 / 不予更正的组）；底稿汇聚来的分录不进调整列
   （随审定表发布计入，V124 防双计），照样列出、注明，并带来源底稿可定位；
3. 向本科目发布审定数的底稿：映射表里对应、本项目已生成的，带最近一次发布时间（有发布记录时）；
4. 本科目在各底稿的抽凭 / 挂凭张数（登记科目以本科目开头）。

``wp_code`` 为空串的节点不是底稿（前端照常显示文字，不出「定位」）。每类最多 50 条，超出写「另有 n 条未列出」。
本年度试算表没有这个科目（如合并项目，试算表在合并模块）返回空。查询失败照常抛出，由统一溯源记 partial（R8.3），
不用空结果冒充没有数据。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    Adjustment,
    AdjustmentEntry,
    ReviewStatus,
    TbPublishAck,
    TrialBalance,
)
from app.models.workpaper_models import SampledVoucher, WorkingPaper, WpIndex
from app.schemas.locate_target import LocateTarget
from app.services.project_audit_year import fetch_project_audit_year
from app.services.wp_mapping_service import workpapers_for_account_codes

MAX_ITEMS = 50
_BEIJING = timezone(timedelta(hours=8))


class TbLineageYearRequired(Exception):
    """请求没带年度、项目也没有审计年度：不能按年度取试算表行。"""

    error_code = "TB_LINEAGE_YEAR_REQUIRED"
    status_code = 422
    message = "项目未设置审计年度，不能取试算表行的数据溯源"


def _money(value: Decimal | None) -> str:
    return f"{(value or Decimal('0')):,.2f}"


def _beijing_time(ts: datetime | None) -> str:
    """库里的时间按 UTC 存（naive 视为 UTC），界面按北京时间显示到分钟。"""
    if ts is None:
        return ""
    aware = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    return aware.astimezone(_BEIJING).strftime("%Y-%m-%d %H:%M")


def _capped(items: list[LocateTarget], total: int) -> list[LocateTarget]:
    if total > len(items):
        items.append(LocateTarget(wp_code="", label=f"另有 {total - len(items)} 条未列出"))
    return items


async def _wp_codes(db: AsyncSession, project_id: UUID, wp_ids: Iterable[UUID]) -> dict[UUID, tuple[str, str]]:
    ids = list(dict.fromkeys(wp_ids))
    if not ids:
        return {}
    rows = (await db.execute(
        sa.select(WorkingPaper.id, WpIndex.wp_code, WpIndex.wp_name)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.id.in_(ids), WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false())
    )).all()
    return {wid: (str(code or ""), str(name or "")) for wid, code, name in rows}


async def _composition(db: AsyncSession, project_id: UUID, code: str, year: int) -> LocateTarget | None:
    tb = TrialBalance
    count, unadjusted, aje, rje, wp_adj, audited = (await db.execute(
        sa.select(
            sa.func.count(tb.id), sa.func.sum(tb.unadjusted_amount), sa.func.sum(tb.aje_adjustment),
            sa.func.sum(tb.rje_adjustment), sa.func.sum(tb.wp_adjustment), sa.func.sum(tb.audited_amount),
        ).where(tb.project_id == project_id, tb.year == year, tb.standard_account_code == code,
                tb.is_deleted == sa.false())
    )).one()
    if not count:
        return None
    parts = [f"未审 {_money(unadjusted)}", f"调整 {_money(aje)}", f"重分类 {_money(rje)}"]
    if wp_adj:
        parts.append(f"底稿发布 {_money(wp_adj)}")
    parts.append(f"审定 {_money(audited)}")
    return LocateTarget(wp_code="", label="构成：" + " · ".join(parts))


def _source_wp_id(origin: str | None, source_ref: str | None) -> UUID | None:
    """底稿汇聚来的分录：source_ref = '{wp_id}:{item_id}'。"""
    if origin != "workpaper" or not source_ref:
        return None
    try:
        return UUID(source_ref.split(":", 1)[0])
    except ValueError:
        return None


async def _approved_adjustments(db: AsyncSession, project_id: UUID, code: str, year: int) -> list[LocateTarget]:
    from app.services.adjustment_treatment_service import effective_groups_clause

    adj, ae = Adjustment.__table__, AdjustmentEntry.__table__
    scope = (
        adj.c.project_id == project_id, adj.c.year == year, adj.c.is_deleted == sa.false(),
        ae.c.is_deleted == sa.false(), adj.c.review_status == ReviewStatus.approved.value,
        ae.c.standard_account_code == code,
        await effective_groups_clause(db, adj, project_id=project_id, year=year),
    )
    joined = ae.join(adj, ae.c.adjustment_id == adj.c.id)
    total = (await db.execute(
        sa.select(sa.func.count(sa.distinct(adj.c.entry_group_id))).select_from(joined).where(*scope)
    )).scalar_one()
    rows = (await db.execute(
        sa.select(
            adj.c.entry_group_id, sa.func.max(adj.c.adjustment_no), sa.func.max(adj.c.description),
            sa.func.max(adj.c.origin), sa.func.max(adj.c.source_ref),
            sa.func.sum(ae.c.debit_amount), sa.func.sum(ae.c.credit_amount),
        ).select_from(joined).where(*scope)
        .group_by(adj.c.entry_group_id)
        .order_by(sa.func.max(adj.c.adjustment_no), adj.c.entry_group_id)
        .limit(MAX_ITEMS)
    )).all()
    sources = {r[0]: _source_wp_id(r[3], r[4]) for r in rows}
    codes = await _wp_codes(db, project_id, [w for w in sources.values() if w is not None])
    items = []
    for group_id, no, desc, origin, _ref, debit, credit in rows:
        net = (debit or Decimal("0")) - (credit or Decimal("0"))
        label = f"{no} {(desc or '').strip() or '无摘要'} {'借' if net >= 0 else '贷'} {_money(abs(net))}"
        wp_id = sources.get(group_id)
        wp_code = codes.get(wp_id, ("", ""))[0] if wp_id else ""
        if origin == "workpaper":
            # 不进调整列：随审定表发布计入审定数（V124）
            label += f"（来自底稿{' ' + wp_code if wp_code else ''}，随审定表发布计入）"
        items.append(LocateTarget(wp_code=wp_code, wp_id=str(wp_id) if wp_code else None, label=label))
    return _capped(items, int(total or 0))


async def _publishing_workpapers(db: AsyncSession, project_id: UUID, code: str, year: int) -> list[LocateTarget]:
    mapped = workpapers_for_account_codes([code], include_parent=True)
    if not mapped:
        return []
    rows = (await db.execute(
        sa.select(WorkingPaper.id, WpIndex.wp_code, WpIndex.wp_name)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false(), WpIndex.wp_code.in_(mapped))
        .order_by(WpIndex.wp_code, WorkingPaper.id)
    )).all()
    # 发布记录记的是审定表编码（D4-1），归到所在底稿（D4）：编码相同或以「底稿编码-」开头
    acks = (await db.execute(
        sa.select(TbPublishAck.wp_code, sa.func.max(TbPublishAck.created_at))
        .where(TbPublishAck.project_id == project_id, TbPublishAck.year == year, TbPublishAck.wp_code.in_(mapped))
        .group_by(TbPublishAck.wp_code)
    )).all()
    items = []
    for wp_id, wp_code, wp_name in rows[:MAX_ITEMS]:
        times = [t for c, t in acks if t is not None and (c == wp_code or c.startswith(f"{wp_code}-"))]
        when = _beijing_time(max(times)) if times else ""
        note = f"最近一次发布审定数 {when}" if when else "未发布过审定数"
        title = f"{wp_code} {wp_name}".strip() if wp_name else str(wp_code)
        items.append(LocateTarget(wp_code=str(wp_code), wp_id=str(wp_id), label=f"{title} · {note}"))
    return _capped(items, len(rows))


async def _sampling_counts(db: AsyncSession, project_id: UUID, code: str, year: int) -> list[LocateTarget]:
    sv = SampledVoucher
    ident = (
        sa.func.coalesce(sv.company_code, "") + "|" + sa.func.coalesce(sa.cast(sv.voucher_date, sa.String), "")
        + "|" + sa.func.coalesce(sv.voucher_type, "") + "|" + sv.voucher_no
    )
    engine = sa.func.count(sa.distinct(sa.case((sv.batch_id.isnot(None), ident))))
    manual = sa.func.count(sa.distinct(sa.case((sv.batch_id.is_(None), ident))))
    rows = (await db.execute(
        sa.select(sv.working_paper_id, engine, manual)
        .where(sv.project_id == project_id, sv.year == year, sv.is_deleted == sa.false(),
               sv.working_paper_id.isnot(None), sv.account_code.startswith(code, autoescape=True))
        .group_by(sv.working_paper_id)
    )).all()
    codes = await _wp_codes(db, project_id, [r[0] for r in rows])
    found = sorted(((codes[w], w, e, m) for w, e, m in rows if w in codes), key=lambda x: (x[0][0], str(x[1])))
    items = []
    for (wp_code, _name), wp_id, engine_n, manual_n in found[:MAX_ITEMS]:
        parts = [p for p in (f"抽凭 {engine_n} 张" if engine_n else "", f"挂凭 {manual_n} 张" if manual_n else "") if p]
        items.append(LocateTarget(wp_code=wp_code, wp_id=str(wp_id), label=f"{wp_code} " + " · ".join(parts)))
    return _capped(items, len(found))


async def tb_row_upstream(db: AsyncSession, project_id: UUID, account_code: str, year: int | None) -> list[LocateTarget]:
    """试算表行（标准科目）的上游节点；年度缺省取项目审计年度，取不到抛 :class:`TbLineageYearRequired`。"""
    code = (account_code or "").strip()
    if not code:
        return []
    if year is None:
        year = await fetch_project_audit_year(db, project_id)
    if year is None:
        raise TbLineageYearRequired()
    composition = await _composition(db, project_id, code, year)
    if composition is None:
        return []
    out = [composition]
    out += await _approved_adjustments(db, project_id, code, year)
    out += await _publishing_workpapers(db, project_id, code, year)
    out += await _sampling_counts(db, project_id, code, year)
    return out
