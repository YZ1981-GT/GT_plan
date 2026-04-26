"""底稿-科目映射 API

提供底稿与科目/试算表/附注的关联查询和预填充数据。
"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.services.wp_mapping_service import WpMappingService

router = APIRouter(
    prefix="/api/projects/{project_id}/wp-mapping",
    tags=["wp-mapping"],
)


@router.get("/all")
async def get_all_mappings(
    project_id: UUID,
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取全部底稿-科目映射"""
    svc = WpMappingService()
    return svc.get_all_mappings()


@router.get("/by-account/{account_code}")
async def find_by_account(
    project_id: UUID,
    account_code: str,
    current_user: User = Depends(require_project_access("readonly")),
):
    """根据科目编码查找关联底稿"""
    svc = WpMappingService()
    return svc.find_by_account_code(account_code)


@router.get("/by-wp/{wp_code}")
async def find_by_wp(
    project_id: UUID,
    wp_code: str,
    current_user: User = Depends(require_project_access("readonly")),
):
    """根据底稿编码查找映射"""
    svc = WpMappingService()
    return svc.find_by_wp_code(wp_code)


@router.get("/by-note/{note_section:path}")
async def find_by_note(
    project_id: UUID,
    note_section: str,
    current_user: User = Depends(require_project_access("readonly")),
):
    """根据附注章节查找关联底稿"""
    svc = WpMappingService()
    return svc.find_by_note_section(note_section)


@router.get("/prefill/{wp_code}")
async def get_prefill_data(
    project_id: UUID,
    wp_code: str,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取底稿预填充数据（从试算表取数）"""
    svc = WpMappingService(db)
    result = await svc.get_prefill_data(project_id, year, wp_code)
    if result is None:
        return {"message": f"未找到底稿 {wp_code} 的映射配置"}
    return result


@router.get("/recommend")
async def recommend_workpapers(
    project_id: UUID,
    year: int = Query(...),
    report_scope: str = Query("standalone"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """根据试算表有余额的科目，智能推荐需要编制的底稿清单"""
    svc = WpMappingService(db)
    return await svc.recommend_workpapers(project_id, year, report_scope)


# ─── TSJ 提示词 ───

@router.get("/tsj/{account_name}")
async def get_tsj_prompts(
    project_id: UUID,
    account_name: str,
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取科目对应的 TSJ 审计复核提示词"""
    from app.services.tsj_prompt_service import TsjPromptService
    svc = TsjPromptService()
    result = svc.get_for_account(account_name)
    if not result:
        return {"tips": [], "checklist": [], "risk_areas": [], "message": f"未找到 {account_name} 的 TSJ 提示词"}
    # 不返回 full_content（太大），只返回结构化数据
    return {
        "account_name": result["account_name"],
        "tsj_file": result["tsj_file"],
        "tips": result["tips"],
        "checklist": result["checklist"],
        "risk_areas": result["risk_areas"],
    }


# ─── 项目经理：待复核收件箱 ───

@router.get("/review-inbox")
async def get_review_inbox(
    project_id: UUID,
    year: int = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """获取当前用户待复核的底稿列表"""
    from app.models.workpaper_models import WorkingPaper, WpIndex, WpReviewStatus

    q = (
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
            WorkingPaper.review_status.in_([
                WpReviewStatus.pending_level1,
                WpReviewStatus.pending_level2,
                WpReviewStatus.level1_in_progress,
                WpReviewStatus.level2_in_progress,
            ]),
        )
        .order_by(WorkingPaper.updated_at.desc())
    )
    result = await db.execute(q)
    rows = result.all()

    items = []
    for wp, idx in rows:
        items.append({
            "wp_id": str(wp.id),
            "wp_code": idx.wp_code,
            "wp_name": idx.wp_name,
            "audit_cycle": idx.audit_cycle,
            "file_status": wp.status.value if wp.status else "unknown",
            "review_status": wp.review_status.value if wp.review_status else "not_submitted",
            "assigned_to": wp.assigned_to,
            "reviewer": wp.reviewer,
            "file_version": wp.file_version,
            "updated_at": wp.updated_at.isoformat() if wp.updated_at else None,
        })
    return {"total": len(items), "items": items}


# ─── 项目经理：项目进度总览 ───

@router.get("/progress-overview")
async def get_progress_overview(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取项目底稿进度总览（按循环分组统计）"""
    import sqlalchemy as _sa
    from app.models.workpaper_models import WorkingPaper, WpIndex

    q = (
        _sa.select(
            WpIndex.audit_cycle,
            WorkingPaper.status,
            _sa.func.count().label("cnt"),
        )
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == _sa.false(),
        )
        .group_by(WpIndex.audit_cycle, WorkingPaper.status)
    )
    result = await db.execute(q)

    cycles: dict[str, dict] = {}
    total_all = 0
    done_all = 0
    for row in result.fetchall():
        cycle = row.audit_cycle or "其他"
        status = row.status.value if row.status else "unknown"
        cnt = row.cnt
        if cycle not in cycles:
            cycles[cycle] = {"cycle": cycle, "total": 0, "statuses": {}}
        cycles[cycle]["total"] += cnt
        cycles[cycle]["statuses"][status] = cycles[cycle]["statuses"].get(status, 0) + cnt
        total_all += cnt
        if status in ("review_passed", "archived", "review_level1_passed", "review_level2_passed"):
            done_all += cnt

    return {
        "total": total_all,
        "done": done_all,
        "progress_pct": round(done_all / total_all * 100) if total_all > 0 else 0,
        "cycles": sorted(cycles.values(), key=lambda x: x["cycle"]),
    }


# ─── 项目经理：底稿分配 ───

@router.post("/assign/{wp_code}")
async def assign_workpaper(
    project_id: UUID,
    wp_code: str,
    staff_name: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """将底稿分配给指定人员"""
    from app.models.workpaper_models import WorkingPaper, WpIndex

    # 查找底稿
    q = (
        sa.select(WorkingPaper)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WpIndex.wp_code == wp_code,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    result = await db.execute(q)
    wp = result.scalar_one_or_none()
    if not wp:
        from fastapi import HTTPException
        raise HTTPException(404, f"底稿 {wp_code} 不存在")

    wp.assigned_to = staff_name
    await db.flush()
    return {"message": f"已将 {wp_code} 分配给 {staff_name}", "wp_id": str(wp.id)}


# ─── 项目经理：进度简报AI生成 ───

@router.get("/progress-report")
async def generate_progress_report(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """AI 生成项目进度简报"""
    import sqlalchemy as _sa
    from app.models.workpaper_models import WorkingPaper, WpIndex

    # 1. 统计数据
    q = (
        _sa.select(
            WpIndex.audit_cycle,
            WorkingPaper.status,
            _sa.func.count().label("cnt"),
        )
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == _sa.false(),
        )
        .group_by(WpIndex.audit_cycle, WorkingPaper.status)
    )
    result = await db.execute(q)
    stats: dict[str, dict[str, int]] = {}
    total = 0
    done = 0
    for row in result.fetchall():
        cycle = row.audit_cycle or "其他"
        status = row.status.value if row.status else "unknown"
        stats.setdefault(cycle, {})[status] = row.cnt
        total += row.cnt
        if status in ("review_passed", "archived"):
            done += row.cnt

    pct = round(done / total * 100) if total > 0 else 0

    # 2. 生成简报文本
    lines = [
        f"# 项目进度简报",
        f"",
        f"**项目ID**: {project_id}",
        f"**审计年度**: {year}",
        f"**总体进度**: {done}/{total} ({pct}%)",
        f"",
        f"## 各循环进度",
        f"",
    ]
    for cycle in sorted(stats.keys()):
        s = stats[cycle]
        c_total = sum(s.values())
        c_done = sum(s.get(st, 0) for st in ("review_passed", "archived"))
        c_pct = round(c_done / c_total * 100) if c_total > 0 else 0
        lines.append(f"- **{cycle}循环**: {c_done}/{c_total} ({c_pct}%)")
        for status, cnt in sorted(s.items()):
            lines.append(f"  - {status}: {cnt}")

    lines.extend([
        f"",
        f"## 待关注事项",
        f"",
    ])

    # 待复核数量
    review_count = sum(
        s.get("under_review", 0) + s.get("revision_required", 0)
        for s in stats.values()
    )
    if review_count > 0:
        lines.append(f"- 待复核/退回修改底稿: {review_count} 个")

    # 未开始数量
    not_started = sum(s.get("not_started", 0) for s in stats.values())
    if not_started > 0:
        lines.append(f"- 尚未开始编制: {not_started} 个")

    if pct >= 80:
        lines.append(f"- 项目进度良好，已完成 {pct}%")
    elif pct >= 50:
        lines.append(f"- 项目进度正常，需关注未完成循环")
    else:
        lines.append(f"- 项目进度偏慢（{pct}%），建议加快编制节奏")

    report_text = "\n".join(lines)

    # 3. 尝试用 LLM 润色
    try:
        from app.services.llm_client import chat_completion
        ai_text = await chat_completion([
            {"role": "system", "content": "你是审计项目经理，请根据以下数据生成一份简洁的项目进度简报，包含总体进度、各循环状态、待关注事项和下一步建议。用中文，不超过300字。"},
            {"role": "user", "content": report_text},
        ])
        if ai_text and len(ai_text) > 20:
            report_text = ai_text
    except Exception:
        pass  # LLM 不可用时用规则生成的文本

    return {
        "total": total,
        "done": done,
        "progress_pct": pct,
        "report_text": report_text,
    }
