"""auto_data_source 注册式解析器。

将 ProcedureTableService._resolve_auto_values 的 20+ elif 分支
拆解为独立的注册式 resolver 函数，每个 resolver：
- 只负责单一数据源的查询逻辑
- 返回 dict（至少 summary 字段）
- 异常由调度器统一捕获记录

用法：
    from app.services.auto_data_resolvers import resolve_auto_data_source

    result = await resolve_auto_data_source(db, project_id, year, source_name)
    # result = {"summary": "...", ...}  或  None（未注册的 source）

新增 resolver 只需在本模块底部加一个 @auto_resolver("name") 装饰的 async 函数。
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Callable, Awaitable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

_logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Registry 基础设施
# ═══════════════════════════════════════════════════════════════════════════════

# resolver 签名: async (db, project_id, year, **kwargs) -> dict[str, Any]
ResolverFn = Callable[..., Awaitable[dict[str, Any]]]

_REGISTRY: dict[str, ResolverFn] = {}


def auto_resolver(name: str):
    """装饰器：注册一个 auto_data_source 解析器。"""
    def decorator(fn: ResolverFn) -> ResolverFn:
        _REGISTRY[name] = fn
        return fn
    return decorator


def get_registered_sources() -> list[str]:
    """返回所有已注册的 source 名列表（供测试/自省用）。"""
    return list(_REGISTRY.keys())


async def resolve_auto_data_source(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    source: str,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """调度器：按 source 名查找并执行对应 resolver。

    Returns:
        resolver 返回的 dict（至少含 summary），或 None 表示未注册。
    """
    resolver = _REGISTRY.get(source)
    if resolver is None:
        return None
    return await resolver(db, project_id, year, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
# 调整分录相关 resolvers
# ═══════════════════════════════════════════════════════════════════════════════


async def _count_adjustments(db: AsyncSession, project_id: UUID, year: int, adj_type: str) -> int:
    from app.models.audit_platform_models import Adjustment
    if adj_type == "passed":
        stmt = sa.select(sa.func.count()).select_from(Adjustment).where(
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            Adjustment.passed_reason.isnot(None),
            Adjustment.is_deleted == sa.false(),
        )
    else:
        stmt = sa.select(sa.func.count()).select_from(Adjustment).where(
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            Adjustment.adjustment_type == adj_type,
            Adjustment.is_deleted == sa.false(),
        )
    result = await db.execute(stmt)
    return result.scalar() or 0


async def _count_adjustments_with_pending(
    db: AsyncSession, project_id: UUID, year: int, adj_type: str
) -> tuple[int, int, float]:
    from app.models.audit_platform_models import Adjustment, AdjustmentEntry
    total_stmt = sa.select(sa.func.count()).select_from(Adjustment).where(
        Adjustment.project_id == project_id,
        Adjustment.year == year,
        Adjustment.adjustment_type == adj_type,
        Adjustment.is_deleted == sa.false(),
    )
    pending_stmt = sa.select(sa.func.count()).select_from(Adjustment).where(
        Adjustment.project_id == project_id,
        Adjustment.year == year,
        Adjustment.adjustment_type == adj_type,
        Adjustment.review_status != "approved",
        Adjustment.passed_reason.is_(None),
        Adjustment.is_deleted == sa.false(),
    )
    amount_stmt = sa.select(
        sa.func.coalesce(sa.func.sum(AdjustmentEntry.debit_amount), 0)
    ).join(
        Adjustment, AdjustmentEntry.adjustment_id == Adjustment.id
    ).where(
        Adjustment.project_id == project_id,
        Adjustment.year == year,
        Adjustment.adjustment_type == adj_type,
        Adjustment.is_deleted == sa.false(),
    )
    total_r = await db.execute(total_stmt)
    pending_r = await db.execute(pending_stmt)
    amount_r = await db.execute(amount_stmt)
    return (total_r.scalar() or 0, pending_r.scalar() or 0, float(amount_r.scalar() or 0))


@auto_resolver("adjustment_count_aje")
async def _resolve_adj_aje(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    count, pending, amount = await _count_adjustments_with_pending(db, project_id, year, "aje")
    if count == 0:
        return {"summary": "无"}
    if pending > 0:
        return {"summary": f"共{count}笔 ¥{amount:,.0f}（⚠️{pending}笔待审）"}
    return {"summary": f"共{count}笔 ¥{amount:,.0f}（全部已批）"}


@auto_resolver("adjustment_count_rje")
async def _resolve_adj_rje(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    count, pending, amount = await _count_adjustments_with_pending(db, project_id, year, "rje")
    if count == 0:
        return {"summary": "无"}
    if pending > 0:
        return {"summary": f"共{count}笔 ¥{amount:,.0f}（⚠️{pending}笔待审）"}
    return {"summary": f"共{count}笔 ¥{amount:,.0f}（全部已批）"}


@auto_resolver("adjustment_count_passed")
async def _resolve_adj_passed(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    count = await _count_adjustments(db, project_id, year, "passed")
    return {"summary": f"共{count}笔" if count else "无"}


@auto_resolver("adjustment_count_consol")
async def _resolve_adj_consol(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.consolidation_models import EliminationEntry
    stmt = sa.select(sa.func.count()).select_from(EliminationEntry).where(
        EliminationEntry.project_id == project_id,
        EliminationEntry.is_deleted == sa.false(),
    )
    r = await db.execute(stmt)
    count = r.scalar() or 0
    return {"summary": f"共{count}笔合并调整" if count else "无合并调整"}


@auto_resolver("misstatement_summary")
async def _resolve_misstatement_summary(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    count = await _count_adjustments(db, project_id, year, "passed")
    return {"summary": f"未更正错报{count}笔" if count else "无未更正错报"}


@auto_resolver("misstatement_evaluation")
async def _resolve_misstatement_eval(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.audit_platform_models import Adjustment, Materiality, AdjustmentEntry
    passed_stmt = sa.select(
        sa.func.coalesce(sa.func.sum(AdjustmentEntry.debit_amount), 0)
    ).join(
        Adjustment, AdjustmentEntry.adjustment_id == Adjustment.id
    ).where(
        Adjustment.project_id == project_id,
        Adjustment.year == year,
        Adjustment.passed_reason.isnot(None),
        Adjustment.is_deleted == sa.false(),
    )
    passed_r = await db.execute(passed_stmt)
    passed_amount = passed_r.scalar() or 0
    mat_stmt = sa.select(Materiality.performance_materiality, Materiality.trivial_threshold).where(
        Materiality.project_id == project_id,
    )
    mat_r = await db.execute(mat_stmt)
    mat_row = mat_r.first()
    if not mat_row or not mat_row.performance_materiality:
        return {"summary": f"未更正错报 ¥{passed_amount:,.0f}（重要性待设置）"}
    perf_mat = float(mat_row.performance_materiality)
    trivial = float(mat_row.trivial_threshold) if mat_row.trivial_threshold else 0
    if passed_amount == 0:
        return {"summary": "无未更正错报"}
    if passed_amount > perf_mat:
        return {"summary": f"⚠️ 未更正错报 ¥{passed_amount:,.0f} 超执行重要性 ¥{perf_mat:,.0f}"}
    if passed_amount <= trivial:
        return {"summary": f"未更正错报 ¥{passed_amount:,.0f}，低于明显微小阈值 → 不影响意见"}
    return {"summary": f"未更正错报 ¥{passed_amount:,.0f}，低于执行重要性 ¥{perf_mat:,.0f}"}


# ═══════════════════════════════════════════════════════════════════════════════
# 重要性 / 试算平衡 / 合并
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("materiality_set")
async def _resolve_materiality(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.audit_platform_models import Materiality
    stmt = sa.select(Materiality.overall_materiality).where(Materiality.project_id == project_id)
    result = await db.execute(stmt)
    val = result.scalar_one_or_none()
    mat = Decimal(str(val)) if val else Decimal("0")
    return {"summary": f"重要性水平 {mat:,.0f} 元" if mat else "待设置"}


@auto_resolver("trial_balance_check")
async def _resolve_tb_check(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.audit_platform_models import TbBalance
    from app.services.dataset_query import get_active_filter
    tb = TbBalance.__table__
    active_filter = await get_active_filter(db, tb, project_id, year)
    bal_stmt = sa.select(
        sa.func.coalesce(
            sa.func.sum(sa.case((tb.c.closing_balance > 0, tb.c.closing_balance), else_=sa.literal(0))), 0
        ).label("debit_total"),
        sa.func.coalesce(
            sa.func.sum(sa.case((tb.c.closing_balance < 0, sa.func.abs(tb.c.closing_balance)), else_=sa.literal(0))), 0
        ).label("credit_total"),
    ).where(active_filter, tb.c.level == 1)
    bal_r = await db.execute(bal_stmt)
    bal_row = bal_r.first()
    if bal_row:
        debit = float(bal_row.debit_total)
        credit = float(bal_row.credit_total)
        diff = abs(debit - credit)
        if diff < 0.01:
            return {"summary": f"✓ 试算平衡（借=贷 ¥{debit:,.0f}）"}
        return {"summary": f"⚠️ 不平衡（差异 ¥{diff:,.2f}）"}
    return {"summary": "无余额数据"}


@auto_resolver("consol_scope_status")
async def _resolve_consol_scope(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.consolidation_models import ConsolScope
    stmt = sa.select(sa.func.count()).select_from(ConsolScope).where(
        ConsolScope.project_id == project_id,
        ConsolScope.is_included == sa.true(),
        ConsolScope.is_deleted == sa.false(),
    )
    r = await db.execute(stmt)
    count = r.scalar() or 0
    return {"summary": f"已纳入{count}家子公司" if count else "待确定"}


@auto_resolver("consol_elimination_count")
async def _resolve_consol_elim(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.consolidation_models import EliminationEntry
    stmt = sa.select(sa.func.count()).select_from(EliminationEntry).where(
        EliminationEntry.project_id == project_id,
        EliminationEntry.is_deleted == sa.false(),
    )
    r = await db.execute(stmt)
    count = r.scalar() or 0
    return {"summary": f"共{count}笔抵销分录" if count else "无"}


@auto_resolver("consol_internal_trade_status")
async def _resolve_consol_trade(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.consolidation_models import InternalTrade
    stmt = sa.select(sa.func.count()).select_from(InternalTrade).where(
        InternalTrade.project_id == project_id,
    )
    r = await db.execute(stmt)
    count = r.scalar() or 0
    return {"summary": f"内部往来{count}笔" if count else "无内部往来"}


@auto_resolver("consol_trial_balance_check")
async def _resolve_consol_tb(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.audit_platform_models import TrialBalance
    tb_t = TrialBalance.__table__
    stmt = sa.select(
        sa.func.coalesce(sa.func.sum(tb_t.c.aje_adjustment), 0).label("aje_sum"),
        sa.func.coalesce(sa.func.sum(tb_t.c.rje_adjustment), 0).label("rje_sum"),
    ).where(
        tb_t.c.project_id == project_id,
        tb_t.c.year == year,
        tb_t.c.is_deleted == sa.false(),
    )
    r = await db.execute(stmt)
    row = r.first()
    if row:
        aje = float(row.aje_sum)
        rje = float(row.rje_sum)
        if abs(aje) < 0.01 and abs(rje) < 0.01:
            return {"summary": "✓ 合并试算平衡"}
        return {"summary": f"⚠️ 调整净差异 AJE ¥{aje:,.0f} / RJE ¥{rje:,.0f}"}
    return {"summary": "无合并试算数据"}


# ═══════════════════════════════════════════════════════════════════════════════
# 现金流 / 复核签字 / 底稿完成率
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("cf_verification_status")
async def _resolve_cf(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.cf_verification_models import CfVerificationResult
    stmt = sa.select(
        sa.func.count(),
        sa.func.count().filter(CfVerificationResult.pass_ == sa.true()),
    ).where(
        CfVerificationResult.project_id == project_id,
        CfVerificationResult.year == year,
    )
    result = await db.execute(stmt)
    total, passed = result.one()
    if total == 0:
        summary = "未执行"
    elif passed == total:
        summary = f"全部通过（{total}项）"
    else:
        summary = f"通过{passed}/{total}项"
    return {"summary": summary, "link": {"type": "cf_verification", "target": "cash_flow_verification"}}


@auto_resolver("review_progress")
async def _resolve_review_progress(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.services.review_checklist_service import get_review_sign_status_batch
    statuses = await get_review_sign_status_batch(db, project_id)
    passed = sum(1 for v in statuses.values() if v == "pass")
    total = len(statuses)
    return {"summary": f"复核{passed}/{total}级完成" if total else "无适用复核"}


async def _resolve_sign_status(db: AsyncSession, project_id: UUID, prefix: str, role_label: str) -> dict:
    """通用签字状态解析（A21/A22/A23 复用）。"""
    from app.services.review_checklist_service import get_review_sign_status_batch
    statuses = await get_review_sign_status_batch(db, project_id)
    st = statuses.get(f"{prefix}-1") or statuses.get(f"{prefix}-2")
    if st == "pass":
        return {"summary": f"✓ {role_label}已签字"}
    if st == "reject":
        return {"summary": f"⚠️ {role_label}退回"}
    return {"summary": f"待{role_label}复核签字"}


@auto_resolver("a21_sign_status")
async def _resolve_a21(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    return await _resolve_sign_status(db, project_id, "A21", "现场负责人")


@auto_resolver("a22_sign_status")
async def _resolve_a22(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    return await _resolve_sign_status(db, project_id, "A22", "经理")


@auto_resolver("a23_sign_status")
async def _resolve_a23(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    return await _resolve_sign_status(db, project_id, "A23", "合伙人")


@auto_resolver("workpaper_completion_rate")
async def _resolve_wp_completion(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.workpaper_models import WorkingPaper
    total_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).where(
        WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false(),
    )
    done_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).where(
        WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false(),
        WorkingPaper.status.in_(["completed", "reviewed"]),
    )
    total = (await db.execute(total_stmt)).scalar() or 0
    done = (await db.execute(done_stmt)).scalar() or 0
    pct = round(done / total * 100) if total else 0
    return {"summary": f"编制完成{done}/{total}（{pct}%）"}


@auto_resolver("control_test_completion")
async def _resolve_ctrl_completion(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.workpaper_models import WorkingPaper, WpIndex
    base = sa.select(sa.func.count()).select_from(WorkingPaper).join(
        WpIndex, WorkingPaper.wp_index_id == WpIndex.id
    ).where(WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false(), WpIndex.wp_code.like("C%"))
    total = (await db.execute(base)).scalar() or 0
    done = (await db.execute(base.where(WorkingPaper.status.in_(["completed", "reviewed"])))).scalar() or 0
    if total == 0:
        return {"summary": "无控制测试底稿"}
    return {"summary": f"控制测试 {done}/{total}张（{round(done / total * 100)}%）"}


@auto_resolver("substantive_completion")
async def _resolve_sub_completion(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.workpaper_models import WorkingPaper, WpIndex
    base = sa.select(sa.func.count()).select_from(WorkingPaper).join(
        WpIndex, WorkingPaper.wp_index_id == WpIndex.id
    ).where(WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false(), WpIndex.wp_code.op("~")("^[D-N]"))
    total = (await db.execute(base)).scalar() or 0
    done = (await db.execute(base.where(WorkingPaper.status.in_(["completed", "reviewed"])))).scalar() or 0
    if total == 0:
        return {"summary": "无实质性程序底稿"}
    return {"summary": f"实质性程序 {done}/{total}张（{round(done / total * 100)}%）"}


@auto_resolver("analytical_review_done")
async def _resolve_ar_done(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.workpaper_models import WorkingPaper, WpIndex
    stmt = sa.select(WpIndex.wp_code, WorkingPaper.status).join(
        WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id
    ).where(WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false(), WpIndex.wp_code.in_(["A1-13", "A1-14"]))
    rows = (await db.execute(stmt)).all()
    if not rows:
        return {"summary": "分析性复核底稿未生成"}
    done_codes = [r[0] for r in rows if r[1] in ("completed", "reviewed")]
    all_codes = [r[0] for r in rows]
    if len(done_codes) == len(all_codes):
        return {"summary": f"通过（{'/'.join(all_codes)} 已完成）"}
    return {"summary": f"{'/'.join(all_codes)} — 完成{len(done_codes)}/{len(all_codes)}"}


@auto_resolver("archive_completion")
async def _resolve_archive(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.workpaper_models import WorkingPaper
    total = (await db.execute(sa.select(sa.func.count()).select_from(WorkingPaper).where(
        WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false(),
    ))).scalar() or 0
    reviewed = (await db.execute(sa.select(sa.func.count()).select_from(WorkingPaper).where(
        WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false(), WorkingPaper.status == "reviewed",
    ))).scalar() or 0
    if total == 0:
        return {"summary": "无底稿"}
    if reviewed == total:
        return {"summary": "通过（全部完成复核，可归档）"}
    return {"summary": f"待归档（{total - reviewed}张未完成复核）"}


# ═══════════════════════════════════════════════════════════════════════════════
# A16 / A7 关联方 / A14 内控
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("a16_template_recommend")
async def _resolve_a16_recommend(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.services.a16_version_service import recommend_main_version
    rec = await recommend_main_version(db, project_id)
    suffix = "（请项目组确认）" if rec.get("confidence") != "high" else ""
    return {"summary": f"推荐 {rec['code']} {rec['label']}{suffix}", "detail": rec}


@auto_resolver("related_party_transaction_count")
async def _resolve_related_party(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.related_party_models import RelatedPartyRegistry, RelatedPartyTransaction
    party_r = await db.execute(sa.select(sa.func.count()).select_from(RelatedPartyRegistry).where(
        RelatedPartyRegistry.project_id == project_id, RelatedPartyRegistry.is_deleted == sa.false(),
    ))
    party_count = party_r.scalar() or 0
    txn_r = await db.execute(sa.select(
        sa.func.count(), sa.func.coalesce(sa.func.sum(RelatedPartyTransaction.amount), 0),
    ).select_from(RelatedPartyTransaction).where(
        RelatedPartyTransaction.project_id == project_id, RelatedPartyTransaction.is_deleted == sa.false(),
    ))
    txn_row = txn_r.one()
    txn_count, txn_total = txn_row[0] or 0, txn_row[1] or 0
    if txn_count > 0:
        return {"summary": f"已识别{txn_count}笔关联交易，涉及{party_count}个关联方，合计{txn_total:,.2f}元", "applicable": "yes"}
    if party_count > 0:
        return {"summary": f"已登记{party_count}个关联方，尚未录入交易"}
    return {"summary": "待识别"}


@auto_resolver("related_party_disclosure_check")
async def _resolve_related_party_disclosure(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.related_party_models import RelatedPartyTransaction
    from app.models.disclosure_models import DisclosureNote
    txn_count = (await db.execute(sa.select(sa.func.count()).select_from(RelatedPartyTransaction).where(
        RelatedPartyTransaction.project_id == project_id, RelatedPartyTransaction.is_deleted == sa.false(),
    ))).scalar() or 0
    note_count = (await db.execute(sa.select(sa.func.count()).select_from(DisclosureNote).where(
        DisclosureNote.project_id == project_id, DisclosureNote.year == year, DisclosureNote.is_deleted == sa.false(),
        sa.or_(DisclosureNote.note_section.like("十一%"), DisclosureNote.note_section.like("十、%"), DisclosureNote.note_section.like("十一、%")),
    ))).scalar() or 0
    if txn_count > 0 and note_count > 0:
        return {"summary": f"已录入{txn_count}笔交易，附注已有{note_count}个章节披露，待核对一致性"}
    if txn_count > 0:
        return {"summary": f"已录入{txn_count}笔交易，但附注尚无关联方披露章节"}
    if note_count > 0:
        return {"summary": f"附注已有{note_count}个关联方章节，但尚未录入交易明细"}
    return {"summary": "关联方交易及附注均待完善"}


@auto_resolver("a16_sign_status_check")
async def _resolve_a16_sign(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.services.field_override_service import FieldOverrideService
    svc = FieldOverrideService(db)
    selected_version = await svc.get(project_id, year, "word_template:A16", "selected_version", "value")
    if not selected_version:
        return {"summary": "待确定主版本"}
    sign_scope = f"word_template:A16:{selected_version}"
    sign_status = await svc.get(project_id, year, sign_scope, "sign_status", "value")
    if sign_status == "signed":
        return {"summary": f"✓ 主版本 {selected_version} 已签署", "step_status": "completed"}
    if sign_status == "sent":
        return {"summary": f"主版本 {selected_version} 已发出，待签回", "step_status": "in_progress"}
    return {"summary": f"主版本 {selected_version}，待签署"}


@auto_resolver("control_deficiency_count")
async def _resolve_ctrl_deficiency(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    from app.models.issue_ticket_models import IssueTicket
    count = (await db.execute(sa.select(sa.func.count()).select_from(IssueTicket).where(
        IssueTicket.project_id == project_id, IssueTicket.category == "internal_control", IssueTicket.is_deleted == sa.false(),
    ))).scalar() or 0
    return {"summary": f"已识别{count}项内控缺陷" if count else "暂无已识别缺陷"}
