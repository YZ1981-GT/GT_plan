"""复核签字 / 底稿完成率 / A16 / 关联方 / 内控缺陷 域 resolvers。"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_data_resolvers import auto_resolver


@auto_resolver("review_progress")
async def _resolve_review_progress(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """三级复核签字整体进度（已签/总级数）。

    数据来源: review_checklist_service.get_review_sign_status_batch
    返回结构: {"summary": str}
    """
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
    """A21 现场负责人复核签字状态。

    数据来源: review_checklist_service.get_review_sign_status_batch
    返回结构: {"summary": str}
    """
    return await _resolve_sign_status(db, project_id, "A21", "现场负责人")


@auto_resolver("a22_sign_status")
async def _resolve_a22(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """A22 经理复核签字状态。

    数据来源: review_checklist_service.get_review_sign_status_batch
    返回结构: {"summary": str}
    """
    return await _resolve_sign_status(db, project_id, "A22", "经理")


@auto_resolver("a23_sign_status")
async def _resolve_a23(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """A23 合伙人复核签字状态。

    数据来源: review_checklist_service.get_review_sign_status_batch
    返回结构: {"summary": str}
    """
    return await _resolve_sign_status(db, project_id, "A23", "合伙人")


@auto_resolver("workpaper_completion_rate")
async def _resolve_wp_completion(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """底稿编制完成率（已完成+已复核 / 总数）。

    数据来源: working_paper 表（status in completed/reviewed）
    返回结构: {"summary": str}（含完成数/总数/百分比）
    """
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
    """C 类控制测试底稿完成率。

    数据来源: working_paper JOIN wp_index（wp_code LIKE 'C%'）
    返回结构: {"summary": str}（含完成数/总数/百分比）
    """
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
    """D~N 实质性程序底稿完成率。

    数据来源: working_paper JOIN wp_index（wp_code 匹配 ^[D-N]）
    返回结构: {"summary": str}（含完成数/总数/百分比）
    """
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
    """分析性复核底稿（A1-13/A1-14）完成状态。

    数据来源: working_paper JOIN wp_index（wp_code IN A1-13, A1-14）
    返回结构: {"summary": str}（含各底稿完成情况）
    """
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
    """归档就绪状态（全部底稿复核完成则可归档）。

    数据来源: working_paper 表（status='reviewed' 占比）
    返回结构: {"summary": str}
    """
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
    """A16 审计报告主版本推荐（根据项目特征自动匹配模板）。

    数据来源: a16_version_service.recommend_main_version
    返回结构: {"summary": str, "detail": dict}（含推荐代号/标签/置信度）
    """
    from app.services.a16_version_service import recommend_main_version
    rec = await recommend_main_version(db, project_id)
    suffix = "（请项目组确认）" if rec.get("confidence") != "high" else ""
    return {"summary": f"推荐 {rec['code']} {rec['label']}{suffix}", "detail": rec}


@auto_resolver("related_party_transaction_count")
async def _resolve_related_party(db: AsyncSession, project_id: UUID, year: int, **kw) -> dict:
    """关联方及关联交易数量/金额汇总（A7 关联方底稿用）。

    数据来源: related_party_registry / related_party_transaction 表
    返回结构: {"summary": str, "applicable": str|None}
    """
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
    """关联方交易与附注披露一致性核查。

    数据来源: related_party_transaction / disclosure_note 表
    返回结构: {"summary": str}（含交易笔数和披露章节数量对比）
    """
    from app.models.related_party_models import RelatedPartyTransaction
    from app.models.report_models import DisclosureNote
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
    """A16 审计报告签署状态追踪。

    数据来源: field_override_service（word_template:A16 scope）
    返回结构: {"summary": str, "step_status": str|None}
    """
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
    """已识别内控缺陷数量统计（A14 内控底稿用）。

    数据来源: issue_ticket 表（category='internal_control'）
    返回结构: {"summary": str}
    """
    from app.models.phase15_models import IssueTicket
    count = (await db.execute(sa.select(sa.func.count()).select_from(IssueTicket).where(
        IssueTicket.project_id == project_id, IssueTicket.category == "internal_control", IssueTicket.status != "rejected",
    ))).scalar() or 0
    return {"summary": f"已识别{count}项内控缺陷" if count else "暂无已识别缺陷"}
