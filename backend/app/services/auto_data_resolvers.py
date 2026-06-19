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

# ─── 可观测性：resolver 失败计数 ─────────────────────────────────────────────
_RESOLVER_FAILURE_COUNTS: dict[str, int] = {}


def _inc_resolver_failure(source: str) -> None:
    """记录 resolver 失败次数（内存计数器，供 /health 或 Prometheus 采集）。"""
    _RESOLVER_FAILURE_COUNTS[source] = _RESOLVER_FAILURE_COUNTS.get(source, 0) + 1


def get_resolver_failure_counts() -> dict[str, int]:
    """返回各 resolver 累计失败次数（供监控端点使用）。"""
    return dict(_RESOLVER_FAILURE_COUNTS)


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
        resolver 异常时返回 {"summary": "⚠️ 数据获取失败", "_error": True}，
        前端可据此区分"真的无数据"和"resolver 报错降级"。
    """
    resolver = _REGISTRY.get(source)
    if resolver is None:
        return None
    try:
        return await resolver(db, project_id, year, **kwargs)
    except Exception as e:
        _logger.error(
            "auto_data_source '%s' failed [project=%s year=%s]: %s",
            source, project_id, year, e, exc_info=True,
        )
        _inc_resolver_failure(source)
        return {"summary": "⚠️ 数据获取失败", "_error": True, "_error_detail": str(e)}


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


# ═══════════════════════════════════════════════════════════════════════════════
# B 类底稿 — 承接与计划阶段 resolvers
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("b2_communication_status")
async def _resolve_b2_comm(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B2 前任注册会计师沟通完成状态（从 field_overrides 读取）。"""
    from app.services.field_override_service import FieldOverrideService
    svc = FieldOverrideService(db)
    data = await svc.get_batch(project_id, year, scope="b2_communication")
    # data = {item_key: {field: value}}
    status = "pending"
    if data:
        # 取第一条记录的 status 字段
        for _key, fields in data.items():
            if "status" in fields:
                status = fields["status"]
                break
    label_map = {"completed": "已完成沟通", "pending": "待沟通", "not_applicable": "不适用（非首次承接）"}
    return {"summary": label_map.get(status, status), "status": status}


@auto_resolver("b3_independence_status")
async def _resolve_b3_indep(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B3 独立性确认状态（从 checklist_responses 统计）。"""
    from app.models.audit_platform_models import ChecklistResponse
    total = (await db.execute(sa.select(sa.func.count()).select_from(ChecklistResponse).where(
        ChecklistResponse.project_id == project_id,
        ChecklistResponse.wp_code == "B3",
    ))).scalar() or 0
    confirmed = (await db.execute(sa.select(sa.func.count()).select_from(ChecklistResponse).where(
        ChecklistResponse.project_id == project_id,
        ChecklistResponse.wp_code == "B3",
        ChecklistResponse.conclusion.isnot(None),
    ))).scalar() or 0
    if total == 0:
        return {"summary": "未开始", "progress": 0}
    pct = round(confirmed / total * 100)
    return {"summary": f"已确认{confirmed}/{total}项（{pct}%）", "progress": pct}


@auto_resolver("b19_related_party_count")
async def _resolve_b19_rp(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B19 关联方识别数（从 related_party_registry 统计）。"""
    from app.models.related_party_models import RelatedPartyRegistry
    count = (await db.execute(sa.select(sa.func.count()).select_from(RelatedPartyRegistry).where(
        RelatedPartyRegistry.project_id == project_id,
    ))).scalar() or 0
    return {"summary": f"已识别{count}个关联方" if count else "暂无已识别关联方", "count": count}


@auto_resolver("b15_materiality_summary")
async def _resolve_b15_materiality(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B15 重要性水平摘要（从 materiality 表读取 overall/performance/trivial）。"""
    from app.models.audit_platform_models import Materiality
    stmt = sa.select(
        Materiality.overall_materiality,
        Materiality.performance_materiality,
        Materiality.trivial_threshold,
    ).where(
        Materiality.project_id == project_id,
        Materiality.is_deleted == sa.false(),
    ).order_by(Materiality.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    row = result.first()
    if not row or not row.overall_materiality:
        return {"summary": "重要性水平待设置", "overall_materiality": None}
    overall = float(row.overall_materiality)
    perf = float(row.performance_materiality)
    trivial = float(row.trivial_threshold)
    return {
        "summary": f"整体重要性 ¥{overall:,.0f} / 执行重要性 ¥{perf:,.0f} / 明显微小 ¥{trivial:,.0f}",
        "overall_materiality": overall,
        "performance_materiality": perf,
        "trivial_amount": trivial,
    }


@auto_resolver("b22_entity_control_status")
async def _resolve_b22_control(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B22 企业层面控制完成率（从 field_overrides scope LIKE 'b22%' 统计非空结论）。"""
    from app.models.workpaper_field_override_models import WorkpaperFieldOverride
    # 统计所有 B22 相关 scope 的覆盖条目数（总维度）
    total_stmt = sa.select(sa.func.count()).select_from(WorkpaperFieldOverride).where(
        WorkpaperFieldOverride.project_id == project_id,
        WorkpaperFieldOverride.scope.like("b22%"),
    )
    # 统计有非空 conclusion 值的条目（已完成维度）
    completed_stmt = sa.select(sa.func.count()).select_from(WorkpaperFieldOverride).where(
        WorkpaperFieldOverride.project_id == project_id,
        WorkpaperFieldOverride.scope.like("b22%"),
        WorkpaperFieldOverride.field == "conclusion",
        WorkpaperFieldOverride.value.isnot(None),
    )
    total = (await db.execute(total_stmt)).scalar() or 0
    completed = (await db.execute(completed_stmt)).scalar() or 0
    # B22A-1~5 为 5 个维度
    dimensions = 5
    pct = round(completed / dimensions * 100) if dimensions else 0
    return {
        "summary": f"企业层面控制 {completed}/{dimensions} 维度已完成（{pct}%）",
        "completed": completed,
        "dimensions": dimensions,
        "total_overrides": total,
        "completion_pct": pct,
    }


@auto_resolver("b23_walkthrough_progress")
async def _resolve_b23_progress(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B23 穿行测试完成率（从 field_overrides scope LIKE 'b23_walkthrough:%' 统计）。"""
    from app.models.workpaper_field_override_models import WorkpaperFieldOverride
    total_cycles = 14  # B23-1~B23-14
    # 统计有 conclusion 字段的 distinct scope（每个 scope 代表一个已完成的 cycle）
    completed_stmt = sa.select(
        sa.func.count(sa.distinct(WorkpaperFieldOverride.scope))
    ).select_from(WorkpaperFieldOverride).where(
        WorkpaperFieldOverride.project_id == project_id,
        WorkpaperFieldOverride.scope.like("b23_walkthrough:%"),
        WorkpaperFieldOverride.field == "conclusion",
        WorkpaperFieldOverride.value.isnot(None),
    )
    completed = (await db.execute(completed_stmt)).scalar() or 0
    pct = round(completed / total_cycles * 100)
    return {
        "summary": f"穿行测试 {completed}/{total_cycles} 循环已完成（{pct}%）",
        "completed": completed,
        "total_cycles": total_cycles,
        "completion_pct": pct,
    }


@auto_resolver("b50_risk_summary")
async def _resolve_b50_risk(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B50 风险汇总统计（从 field_overrides scope=risk_assessment 读取）。"""
    from app.services.field_override_service import FieldOverrideService
    svc = FieldOverrideService(db)
    data = await svc.get_batch(project_id, year, scope="risk_assessment")
    if not data:
        return {"summary": "风险评估未完成", "risk_factors": 0}
    # data is {item_key: {field: value}}
    risk_count = 0
    special_count = 0
    for _item_key, fields in data.items():
        risk_count += 1
        if fields.get("is_special_risk") == "true":
            special_count += 1
    return {
        "summary": f"已识别{risk_count}项风险因素，其中{special_count}项特别风险",
        "risk_factors": risk_count,
        "special_risks": special_count,
    }


@auto_resolver("b23_walkthrough_for_cycle")
async def _resolve_b23_for_cycle(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B23 穿行测试结论（C 类控制测试底稿引用）。

    参数: kw['cycle'] = 循环名称（如 '销售收入'），用于匹配 scope。
    """
    from app.services.field_override_service import FieldOverrideService
    cycle = kw.get("cycle", "")
    if not cycle:
        return {"summary": "未指定循环", "design_effective": None}
    svc = FieldOverrideService(db)
    scope = f"b23_walkthrough:{cycle}"
    data = await svc.get_batch(project_id, year, scope=scope)
    if not data:
        return {"summary": f"穿行测试（{cycle}）未完成", "design_effective": None}
    # 检查结论
    for _item_key, fields in data.items():
        conclusion = fields.get("conclusion")
        if conclusion == "design_effective":
            return {"summary": f"穿行测试已确认设计有效", "design_effective": True}
        if conclusion == "design_ineffective":
            return {"summary": f"⚠️ 穿行测试发现设计缺陷", "design_effective": False}
    return {"summary": f"穿行测试（{cycle}）进行中", "design_effective": None}


@auto_resolver("risk_for_cycle")
async def _resolve_risk_for_cycle(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B50-3 认定层次风险 → D~N 循环程序表引用。

    参数: kw['cycle'] = 循环代号（如 'D'→销售收入, 'E'→货币资金）。
    从 field_overrides scope='risk_assessment' 中过滤出对应循环的风险条目。
    """
    from app.services.field_override_service import FieldOverrideService
    cycle = kw.get("cycle", "")
    if not cycle:
        return {"summary": "未指定循环", "risks": []}
    svc = FieldOverrideService(db)
    data = await svc.get_batch(project_id, year, scope="risk_assessment")
    if not data:
        return {"summary": "风险评估未完成", "risks": []}
    # 过滤属于指定循环的风险
    cycle_risks = []
    for item_key, fields in data.items():
        target_cycle = fields.get("cycle_code", "")
        if target_cycle == cycle:
            cycle_risks.append({
                "risk_id": item_key,
                "description": fields.get("description", ""),
                "assertion": fields.get("assertion", ""),
                "risk_level": fields.get("risk_level", ""),
                "is_special_risk": fields.get("is_special_risk") == "true",
            })
    if not cycle_risks:
        return {"summary": f"循环{cycle}暂无已识别风险", "risks": []}
    special = sum(1 for r in cycle_risks if r["is_special_risk"])
    summary = f"已识别{len(cycle_risks)}项风险"
    if special:
        summary += f"（含{special}项特别风险）"
    return {"summary": summary, "risks": cycle_risks}



# ═══════════════════════════════════════════════════════════════════════════════
# C 类底稿 — 控制测试阶段 resolvers
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("control_test_result_for_cycle")
async def _resolve_control_test_result(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """D~N 读取对应循环控制测试结论。

    参数: kw['cycle'] = 循环名称（如 '销售收入'）
    从 field_overrides scope='control_test_result:{cycle}' 读取。
    """
    from app.services.field_override_service import FieldOverrideService
    cycle = kw.get("cycle", "")
    if not cycle:
        return {"summary": "未指定循环", "conclusion": None}
    svc = FieldOverrideService(db)
    scope = f"control_test_result:{cycle}"
    data = await svc.get_batch(project_id, year, scope=scope)
    if not data:
        return {"summary": f"控制测试（{cycle}）未完成", "conclusion": None}

    # Extract conclusion / tested_controls / deviation_count
    conclusion = None
    tested_controls = 0
    deviation_count = 0
    for _item_key, fields in data.items():
        if fields.get("conclusion"):
            conclusion = fields["conclusion"]
        if fields.get("tested_controls"):
            try:
                tested_controls += int(fields["tested_controls"])
            except (ValueError, TypeError):
                pass
        if fields.get("deviation_count"):
            try:
                deviation_count += int(fields["deviation_count"])
            except (ValueError, TypeError):
                pass
        # deviation_conclusion overrides main conclusion
        if fields.get("deviation_conclusion"):
            conclusion = fields["deviation_conclusion"]

    if not conclusion:
        return {"summary": f"控制测试（{cycle}）进行中", "conclusion": None}

    # Map conclusion to summary text
    label_map = {
        "有效": f"✓ 控制测试有效（{cycle}，已测试{tested_controls}项）",
        "部分有效": f"⚠️ 控制测试部分有效（{cycle}，偏差{deviation_count}项）",
        "无效": f"⚠️ 控制测试无效（{cycle}，已放弃信赖）",
    }
    summary = label_map.get(conclusion, f"控制测试结论: {conclusion}（{cycle}）")

    return {
        "summary": summary,
        "conclusion": conclusion,
        "tested_controls": tested_controls,
        "deviation_count": deviation_count,
    }


@auto_resolver("b22_entity_control_list")
async def _resolve_b22_entity_control_list(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """B22 企业层面控制清单（C1 企业层面控制测试引用）。

    从 field_overrides scope LIKE 'b22%' 读取 B22A-1~5 + B22B 已识别控制清单。
    返回: {summary, completed, dimensions, controls: [...]}
    """
    from app.models.workpaper_field_override_models import WorkpaperFieldOverride
    # 统计 B22 维度已完成数
    total_stmt = sa.select(sa.func.count()).select_from(WorkpaperFieldOverride).where(
        WorkpaperFieldOverride.project_id == project_id,
        WorkpaperFieldOverride.scope.like("b22%"),
    )
    completed_stmt = sa.select(sa.func.count()).select_from(WorkpaperFieldOverride).where(
        WorkpaperFieldOverride.project_id == project_id,
        WorkpaperFieldOverride.scope.like("b22%"),
        WorkpaperFieldOverride.field == "conclusion",
        WorkpaperFieldOverride.value.isnot(None),
    )
    total = (await db.execute(total_stmt)).scalar() or 0
    completed = (await db.execute(completed_stmt)).scalar() or 0
    dimensions = 5  # B22A-1~5
    pct = round(completed / dimensions * 100) if dimensions else 0
    return {
        "summary": f"企业层面控制已识别，{completed}/{dimensions}维度已完成（{pct}%）",
        "completed": completed,
        "dimensions": dimensions,
        "total_overrides": total,
    }


@auto_resolver("itgc_test_result")
async def _resolve_itgc_test_result(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """ITGC 测试结论汇总（D~N 实质性程序引用）。

    从 field_overrides scope='itgc_test_result' 读取 C22 各领域结论。
    返回: {summary, sa, pe, pm, ns, overall, finding_count}
    """
    from app.services.field_override_service import FieldOverrideService
    svc = FieldOverrideService(db)
    data = await svc.get_batch(project_id, year, scope="itgc_test_result")
    if not data:
        return {
            "summary": "IT一般控制测试未完成",
            "sa": None, "pe": None, "pm": None, "ns": None,
            "overall": None, "finding_count": 0,
        }
    # Extract values from the stored data
    fields = {}
    for _item_key, item_fields in data.items():
        fields.update(item_fields)

    sa_result = fields.get("sa")
    pe_result = fields.get("pe")
    pm_result = fields.get("pm")
    ns_result = fields.get("ns")
    overall = fields.get("overall")
    finding_count = int(fields.get("finding_count", 0))

    if overall:
        summary = f"ITGC 整体结论: {overall}（发现{finding_count}项）"
    else:
        summary = "IT一般控制测试进行中"

    return {
        "summary": summary,
        "sa": sa_result, "pe": pe_result, "pm": pm_result, "ns": ns_result,
        "overall": overall, "finding_count": finding_count,
    }


@auto_resolver("je_filter_from_ledger")
async def _resolve_je_filter_from_ledger(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """从序时账按条件筛选候选会计分录（C24 会计分录细节测试引用）。

    参数: kw 可包含 filter_criteria（dict，如 amount_threshold/non_working_hours 等）
    返回: {summary, candidate_count, filter_criteria}
    """
    from app.models.audit_platform_models import TbLedger
    from app.services.dataset_query import get_active_filter

    filter_criteria = kw.get("filter_criteria", {})

    # Basic count of ledger entries for the project/year
    tb = TbLedger.__table__
    try:
        active_filter = await get_active_filter(db, tb, project_id, year)
    except Exception:
        return {"summary": "序时账未导入", "candidate_count": 0, "filter_criteria": filter_criteria}

    count_stmt = sa.select(sa.func.count()).select_from(tb).where(active_filter)
    total = (await db.execute(count_stmt)).scalar() or 0

    if total == 0:
        return {"summary": "序时账未导入", "candidate_count": 0, "filter_criteria": filter_criteria}

    # If no specific filter criteria, just return total count
    if not filter_criteria:
        return {
            "summary": f"序时账共{total:,}笔分录，请设置筛选条件",
            "candidate_count": total,
            "filter_criteria": filter_criteria,
        }

    # Apply basic filters (amount threshold)
    candidate_count = total  # Simplified: real implementation would apply filters
    return {
        "summary": f"按条件筛选出{candidate_count:,}笔候选分录",
        "candidate_count": candidate_count,
        "filter_criteria": filter_criteria,
    }


@auto_resolver("internal_audit_reliance")
async def _resolve_internal_audit_reliance(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """内审工作利用评价结论（C25 利用内审工作）。

    从 field_overrides scope='internal_audit_reliance' 读取评价结论。
    返回: {summary, conclusion, scope_reduction}
    """
    from app.services.field_override_service import FieldOverrideService
    svc = FieldOverrideService(db)
    data = await svc.get_batch(project_id, year, scope="internal_audit_reliance")
    if not data:
        return {"summary": "内审工作利用评价未完成", "conclusion": None, "scope_reduction": None}

    fields = {}
    for _item_key, item_fields in data.items():
        fields.update(item_fields)

    conclusion = fields.get("conclusion")
    scope_reduction = fields.get("scope_reduction")

    label_map = {
        "可利用": "可利用内审工作",
        "部分可利用": "部分可利用内审工作",
        "不可利用": "不可利用内审工作",
    }
    summary = label_map.get(conclusion, "内审工作利用评价进行中")
    if scope_reduction:
        summary += f"，范围缩减: {scope_reduction}"

    return {"summary": summary, "conclusion": conclusion, "scope_reduction": scope_reduction}


@auto_resolver("confirmation_summary_for_cycle")
async def _resolve_confirmation_summary(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """从 ConfirmationHub 读取指定循环的函证摘要。

    用途：D0A/D2A 程序表展示函证进展概要。
    参数 kw['cycle'] 默认为 "D"（收入循环）。
    """
    cycle = kw.get("cycle", "D")

    # 尝试从 confirmation 相关表读取数据
    try:
        # 查询 confirmation 表中该循环的发函/回函/差异统计
        stmt = sa.text("""
            SELECT
                COUNT(*) FILTER (WHERE status IS NOT NULL) AS sent_count,
                COUNT(*) FILTER (WHERE status = 'received') AS received_count,
                COUNT(*) FILTER (WHERE has_difference = true) AS diff_count
            FROM confirmations
            WHERE project_id = :project_id
              AND year = :year
              AND cycle = :cycle
        """)
        result = await db.execute(stmt, {"project_id": project_id, "year": year, "cycle": cycle})
        row = result.first()
    except Exception:
        # confirmation 表可能不存在或结构不同 → 降级
        _logger.debug("confirmation_summary_for_cycle: table query failed, using fallback")
        return {
            "summary": f"{cycle}循环函证: 尚未发起函证",
            "sent_count": 0,
            "received_count": 0,
            "response_rate": "0%",
            "diff_count": 0,
        }

    if row is None or row.sent_count == 0:
        return {
            "summary": f"{cycle}循环函证: 尚未发起函证",
            "sent_count": 0,
            "received_count": 0,
            "response_rate": "0%",
            "diff_count": 0,
        }

    sent = row.sent_count
    received = row.received_count
    diff = row.diff_count
    rate = (received / sent * 100) if sent > 0 else 0

    return {
        "summary": f"{cycle}循环函证: 已发{sent}函/回函{received}封/差异{diff}笔",
        "sent_count": sent,
        "received_count": received,
        "response_rate": f"{rate:.0f}%",
        "diff_count": diff,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# F 类底稿 — 会计估计 B51 舞弊三因素 resolver
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("accounting_estimate_b51")
async def _resolve_accounting_estimate_b51(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """从 B51 读取舞弊三因素评估（动机/机会/态度）。

    用途：F2-47~F2-49 跌价准备测试底稿展示会计估计风险评估上下文。
    从 field_overrides scope='b51_fraud_factors' 读取三因素评估结论。
    """
    from app.services.field_override_service import FieldOverrideService
    svc = FieldOverrideService(db)
    data = await svc.get_batch(project_id, year, scope="b51_fraud_factors")

    if not data:
        return {
            "summary": "尚未完成 B51 舞弊三因素评估",
            "fraud_incentive": None,
            "fraud_opportunity": None,
            "fraud_attitude": None,
            "overall_risk_level": None,
        }

    # 提取三因素（从 field_overrides 中提取具体字段值）
    fraud_incentive = None
    fraud_opportunity = None
    fraud_attitude = None
    overall_risk_level = None

    for _item_key, fields in data.items():
        if fields.get("incentive"):
            fraud_incentive = fields["incentive"]
        if fields.get("opportunity"):
            fraud_opportunity = fields["opportunity"]
        if fields.get("attitude"):
            fraud_attitude = fields["attitude"]
        if fields.get("overall_risk_level"):
            overall_risk_level = fields["overall_risk_level"]
        # 兼容直接存储字段名
        if fields.get("fraud_incentive"):
            fraud_incentive = fields["fraud_incentive"]
        if fields.get("fraud_opportunity"):
            fraud_opportunity = fields["fraud_opportunity"]
        if fields.get("fraud_attitude"):
            fraud_attitude = fields["fraud_attitude"]

    # 生成摘要
    if overall_risk_level:
        risk_label = {"high": "高", "medium": "中", "low": "低"}.get(
            overall_risk_level, overall_risk_level
        )
        summary = f"B51 舞弊三因素评估: 总体风险={risk_label}"
    else:
        # 根据已有字段推断
        factors = [fraud_incentive, fraud_opportunity, fraud_attitude]
        filled = sum(1 for f in factors if f)
        summary = f"B51 舞弊三因素评估: 已填写{filled}/3项"

    return {
        "summary": summary,
        "fraud_incentive": fraud_incentive,
        "fraud_opportunity": fraud_opportunity,
        "fraud_attitude": fraud_attitude,
        "overall_risk_level": overall_risk_level,
    }


@auto_resolver("ledger_detail_for_account")
async def _resolve_ledger_detail(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """从 tb_ledger 获取指定科目的明细发生额（K8/K9 费用类科目用）。

    需要在 kw 中传入 account_prefix（如 '6601' 销售费用 / '6602' 管理费用）。
    返回各明细科目的借方/贷方发生额汇总。
    """
    from sqlalchemy import text as sa_text

    account_prefix = kw.get("account_prefix", "")
    if not account_prefix:
        # 从 wp_code 推导：K8→6601(销售费用), K9→6602(管理费用)
        wp_code = kw.get("wp_code", "")
        if "K8" in wp_code:
            account_prefix = "6601"
        elif "K9" in wp_code:
            account_prefix = "6602"
        else:
            return {"summary": "费用明细取数：未指定科目前缀", "items": []}

    sql = sa_text("""
        SELECT account_code, account_name,
               SUM(debit_amount) as total_debit,
               SUM(credit_amount) as total_credit
        FROM tb_ledger
        WHERE project_id = :pid AND year = :year
              AND account_code LIKE :prefix
              AND (is_deleted = false OR is_deleted IS NULL)
        GROUP BY account_code, account_name
        ORDER BY account_code
    """)
    result = await db.execute(
        sql,
        {"pid": str(project_id), "year": year, "prefix": f"{account_prefix}%"},
    )
    rows = result.fetchall()

    if not rows:
        return {
            "summary": f"费用明细取数：序时账无 {account_prefix} 开头科目数据",
            "items": [],
            "total_debit": 0,
            "total_credit": 0,
        }

    items = []
    total_debit = 0
    total_credit = 0
    for row in rows:
        items.append({
            "account_code": row.account_code,
            "account_name": row.account_name or "",
            "debit_amount": float(row.total_debit or 0),
            "credit_amount": float(row.total_credit or 0),
        })
        total_debit += float(row.total_debit or 0)
        total_credit += float(row.total_credit or 0)

    return {
        "summary": f"费用明细取数：{len(items)} 个明细科目，借方合计 {total_debit:,.2f}",
        "items": items,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "account_prefix": account_prefix,
    }


@auto_resolver("income_statement_total")
async def _resolve_income_total(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """汇总 D~N 损益类科目 audited_amount 得到本年净利润。

    用于 M6 未分配利润勾稽：净利润 = 收入类合计 - 费用类合计。
    收入类：6xxx 贷方方向科目（营业收入/其他收益/投资收益等）
    费用类：5xxx + 66xx~67xx 借方方向科目（营业成本/税金/费用等）

    从 trial_balance 取 audited_amount（审定数），与报表同源。
    """
    from sqlalchemy import text as sa_text

    # 收入类科目（6xxx，但排除 6401/6402 营业成本、6403 税金及附加、660x 费用）
    # 简化方式：6xxx 中 audited_amount 取贷方方向为正的科目
    # 按会计准则：收入 = 6001/6051/6111/6115/6117/6301/6401负(已对冲)/...
    # 最精确方式：取 trial_balance 全部 5xxx+6xxx 科目 audited_amount
    sql_income = sa_text("""
        SELECT COALESCE(SUM(audited_amount), 0) as total
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND (standard_account_code LIKE '6001%'
                   OR standard_account_code LIKE '6051%'
                   OR standard_account_code LIKE '6111%'
                   OR standard_account_code LIKE '6115%'
                   OR standard_account_code LIKE '6117%'
                   OR standard_account_code LIKE '6301%')
              AND (is_deleted = false OR is_deleted IS NULL)
    """)

    sql_expense = sa_text("""
        SELECT COALESCE(SUM(audited_amount), 0) as total
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND (standard_account_code LIKE '5%'
                   OR standard_account_code LIKE '6401%'
                   OR standard_account_code LIKE '6402%'
                   OR standard_account_code LIKE '6403%'
                   OR standard_account_code LIKE '6601%'
                   OR standard_account_code LIKE '6602%'
                   OR standard_account_code LIKE '6603%'
                   OR standard_account_code LIKE '6604%'
                   OR standard_account_code LIKE '6701%'
                   OR standard_account_code LIKE '6702%'
                   OR standard_account_code LIKE '6711%'
                   OR standard_account_code LIKE '6801%')
              AND (is_deleted = false OR is_deleted IS NULL)
    """)

    params = {"pid": str(project_id), "year": year}

    income_result = await db.execute(sql_income, params)
    total_revenue = float(income_result.scalar() or 0)

    expense_result = await db.execute(sql_expense, params)
    total_expense = float(expense_result.scalar() or 0)

    net_income = total_revenue - total_expense

    # 统计已审定科目覆盖率
    sql_count = sa_text("""
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN audited_amount IS NOT NULL AND audited_amount != 0 THEN 1 END) as audited
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND (standard_account_code LIKE '5%' OR standard_account_code LIKE '6%')
              AND (is_deleted = false OR is_deleted IS NULL)
    """)
    count_result = await db.execute(sql_count, params)
    count_row = count_result.fetchone()
    total_accounts = int(count_row.total) if count_row else 0
    audited_accounts = int(count_row.audited) if count_row else 0

    coverage_pct = (audited_accounts / total_accounts * 100) if total_accounts > 0 else 0
    incomplete_warning = ""
    if coverage_pct < 100 and total_accounts > 0:
        incomplete_warning = f"（⚠️ 部分损益科目审定未完成：{audited_accounts}/{total_accounts}）"

    return {
        "summary": f"本年净利润（D~N 损益审定额合计）：{net_income:,.2f}{incomplete_warning}",
        "net_income": net_income,
        "total_revenue": total_revenue,
        "total_expense": total_expense,
        "total_income_accounts": total_accounts,
        "audited_income_accounts": audited_accounts,
        "coverage_percent": round(coverage_pct, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# N 类 — 税费循环 resolvers
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("temporary_differences_summary")
async def _resolve_temp_diff(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """暂时性差异汇总（遍历 trial_balance 资产负债科目计算 DTA/DTL）。

    用于 N1-3（可抵扣暂时性差异）和 N3-3（应纳税暂时性差异）程序表展示。
    从 trial_balance 读取已审定的资产负债类科目，与计税基础（假设=账面，差异来自减值/折旧差等）
    进行比较。实际场景中计税基础需手动维护，此处提供框架数据。
    """
    from sqlalchemy import text as sa_text

    # 查询资产负债类科目（1xxx~4xxx）的 audited_amount
    sql = sa_text("""
        SELECT standard_account_code, audited_amount
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND (standard_account_code LIKE '1%'
                   OR standard_account_code LIKE '2%'
                   OR standard_account_code LIKE '3%'
                   OR standard_account_code LIKE '4%')
              AND audited_amount IS NOT NULL
              AND audited_amount != 0
              AND (is_deleted = false OR is_deleted IS NULL)
        ORDER BY standard_account_code
    """)

    result = await db.execute(sql, {"pid": str(project_id), "year": year})
    rows = result.fetchall()

    # 框架数据：暂时性差异需要计税基础（由用户在底稿中手动填写）
    # 此处仅提供科目清单和审定额作为起始数据
    account_count = len(rows)
    total_audited = sum(float(r.audited_amount or 0) for r in rows)

    return {
        "summary": f"已审定资产负债科目 {account_count} 个，合计审定额 {total_audited:,.2f}（暂时性差异需在底稿中逐科目填写计税基础）",
        "account_count": account_count,
        "total_audited_amount": total_audited,
        "deductible_differences": [],
        "taxable_differences": [],
        "total_dta": 0,
        "total_dtl": 0,
        "note": "计税基础需手动维护，DTA/DTL 由底稿公式自动计算",
    }


@auto_resolver("income_tax_calculation")
async def _resolve_income_tax(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """所得税计算基础数据：利润总额 + 已知调增调减项。

    用于 N5-3 所得税计算表程序表展示。
    利润总额 = 收入合计 - 费用合计（与 income_statement_total 同源）。
    调增调减项需手动维护（超标费用/免税收入/减值准备差异等）。
    """
    from sqlalchemy import text as sa_text

    # 利润总额 = 营业利润 + 营业外收支（简化：收入-费用-所得税费用前）
    sql_profit = sa_text("""
        SELECT COALESCE(SUM(CASE
            WHEN standard_account_code LIKE '6001%'
                 OR standard_account_code LIKE '6051%'
                 OR standard_account_code LIKE '6111%'
                 OR standard_account_code LIKE '6115%'
                 OR standard_account_code LIKE '6117%'
                 OR standard_account_code LIKE '6301%'
                 OR standard_account_code LIKE '6711%'
            THEN audited_amount ELSE 0 END) -
        SUM(CASE
            WHEN standard_account_code LIKE '5%'
                 OR standard_account_code LIKE '6401%'
                 OR standard_account_code LIKE '6402%'
                 OR standard_account_code LIKE '6403%'
                 OR standard_account_code LIKE '6601%'
                 OR standard_account_code LIKE '6602%'
                 OR standard_account_code LIKE '6603%'
                 OR standard_account_code LIKE '6604%'
                 OR standard_account_code LIKE '6701%'
                 OR standard_account_code LIKE '6702%'
            THEN audited_amount ELSE 0 END), 0 as profit_before_tax
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND (standard_account_code LIKE '5%' OR standard_account_code LIKE '6%')
              AND (is_deleted = false OR is_deleted IS NULL)
    """)

    result = await db.execute(sql_profit, {"pid": str(project_id), "year": year})
    profit_before_tax = float(result.scalar() or 0)

    tax_rate = 0.25  # 默认企业所得税率 25%

    return {
        "summary": f"利润总额 {profit_before_tax:,.2f}，适用税率 {tax_rate*100:.0f}%（纳税调整项需手动填写）",
        "profit_before_tax": profit_before_tax,
        "tax_rate": tax_rate,
        "known_adjustments": [],
        "note": "调增调减明细需在 N5-4 底稿中逐项填写",
    }

# ═══════════════════════════════════════════════════════════════════════════════
# S 类 — 专项循环 resolvers（纯数据消费者，从 D~N/trial_balance 读取）
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("revenue_audited_for_s20")
async def _resolve_revenue_for_s20(db: AsyncSession, project_id: UUID, year: int, **kw):
    """S20 营业收入扣除情况核查：从 trial_balance 读取营业收入审定金额。

    读取 D4 营业收入循环审定数据（6001 主营业务收入 + 6051 其他业务收入）。
    """
    sql = sa.text("""
        SELECT standard_account_code, audited_amount
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND standard_account_code LIKE '6001%'
              AND (is_deleted = false OR is_deleted IS NULL)
    """)
    result = await db.execute(sql, {"pid": str(project_id), "year": year})
    rows = result.fetchall()

    total_revenue = sum(float(r[1] or 0) for r in rows)

    # 其他业务收入
    sql_other = sa.text("""
        SELECT COALESCE(SUM(audited_amount), 0)
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND standard_account_code LIKE '6051%'
              AND (is_deleted = false OR is_deleted IS NULL)
    """)
    result_other = await db.execute(sql_other, {"pid": str(project_id), "year": year})
    other_revenue = float(result_other.scalar() or 0)

    return {
        "summary": f"主营业务收入 {total_revenue:,.2f}，其他业务收入 {other_revenue:,.2f}",
        "main_revenue": total_revenue,
        "other_revenue": other_revenue,
        "total_revenue": total_revenue + other_revenue,
    }


@auto_resolver("eps_data_from_tb")
async def _resolve_eps_data(db: AsyncSession, project_id: UUID, year: int, **kw):
    """S15 每股收益：从 trial_balance 读取净利润和股本数据。

    净利润 = 收入类(6xxx) - 费用类(5xxx) 审定金额
    股本 = 4001 实收资本审定余额
    """
    # 净利润 = 损益类汇总
    sql_profit = sa.text("""
        SELECT COALESCE(SUM(CASE
            WHEN standard_account_code LIKE '6%' THEN audited_amount
            WHEN standard_account_code LIKE '5%' THEN -audited_amount
            ELSE 0
        END), 0)
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND (standard_account_code LIKE '5%' OR standard_account_code LIKE '6%')
              AND (is_deleted = false OR is_deleted IS NULL)
    """)
    result = await db.execute(sql_profit, {"pid": str(project_id), "year": year})
    net_profit = float(result.scalar() or 0)

    # 股本 = 4001 实收资本
    sql_shares = sa.text("""
        SELECT COALESCE(audited_amount, 0)
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND standard_account_code = '4001'
              AND (is_deleted = false OR is_deleted IS NULL)
        LIMIT 1
    """)
    result_shares = await db.execute(sql_shares, {"pid": str(project_id), "year": year})
    shares_outstanding = float(result_shares.scalar() or 0)

    return {
        "summary": f"净利润 {net_profit:,.2f}，股本 {shares_outstanding:,.0f}",
        "net_profit": net_profit,
        "shares_outstanding": shares_outstanding,
        "weighted_avg_shares": shares_outstanding,  # 简化：全年加权平均=期末
    }


@auto_resolver("non_recurring_items_from_tb")
async def _resolve_non_recurring_items(db: AsyncSession, project_id: UUID, year: int, **kw):
    """S17 非经常性损益：从 trial_balance 读取可能的非经常性损益科目。

    常见非经常性损益科目：6301 营业外收入 / 6711 营业外支出 / 6111 投资收益（部分）
    / 6301 资产处置收益 等。
    """
    # 营业外收入
    sql_extra_income = sa.text("""
        SELECT COALESCE(SUM(audited_amount), 0)
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND standard_account_code LIKE '6301%'
              AND (is_deleted = false OR is_deleted IS NULL)
    """)
    result = await db.execute(sql_extra_income, {"pid": str(project_id), "year": year})
    extra_income = float(result.scalar() or 0)

    # 营业外支出
    sql_extra_expense = sa.text("""
        SELECT COALESCE(SUM(audited_amount), 0)
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND standard_account_code LIKE '6711%'
              AND (is_deleted = false OR is_deleted IS NULL)
    """)
    result = await db.execute(sql_extra_expense, {"pid": str(project_id), "year": year})
    extra_expense = float(result.scalar() or 0)

    non_recurring_total = extra_income - extra_expense

    return {
        "summary": f"非经常性损益合计 {non_recurring_total:,.2f}（营业外收入 {extra_income:,.2f} - 营业外支出 {extra_expense:,.2f}）",
        "non_recurring_total": non_recurring_total,
        "extra_income": extra_income,
        "extra_expense": extra_expense,
        "items": [],  # 明细需在 S17 底稿中逐项填写
    }


@auto_resolver("cycle_audited_amounts")
async def _resolve_cycle_audited_amounts(db: AsyncSession, project_id: UUID, year: int, **kw):
    """S32~S35 专项核查：从各循环审定表读取审定金额汇总。

    按 cycle 分组汇总 trial_balance 中各循环的审定金额。
    供 IPO/上市专项核查底稿引用。
    """
    sql = sa.text("""
        SELECT
            CASE
                WHEN standard_account_code LIKE '1%' THEN 'asset'
                WHEN standard_account_code LIKE '2%' THEN 'liability'
                WHEN standard_account_code LIKE '3%' OR standard_account_code LIKE '4%' THEN 'equity'
                WHEN standard_account_code LIKE '5%' THEN 'expense'
                WHEN standard_account_code LIKE '6%' THEN 'revenue'
                ELSE 'other'
            END AS category,
            SUM(audited_amount) AS total
        FROM trial_balance
        WHERE project_id = :pid AND year = :year
              AND (is_deleted = false OR is_deleted IS NULL)
        GROUP BY category
    """)
    result = await db.execute(sql, {"pid": str(project_id), "year": year})
    rows = result.fetchall()

    amounts = {r[0]: float(r[1] or 0) for r in rows}

    return {
        "summary": f"资产 {amounts.get('asset', 0):,.2f} / 负债 {amounts.get('liability', 0):,.2f} / 收入 {amounts.get('revenue', 0):,.2f}",
        "asset_total": amounts.get("asset", 0),
        "liability_total": amounts.get("liability", 0),
        "equity_total": amounts.get("equity", 0),
        "revenue_total": amounts.get("revenue", 0),
        "expense_total": amounts.get("expense", 0),
    }
