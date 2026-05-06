"""角色化 LLM 辅助功能 — 四种角色的实用增强

1. 审计员：底稿编制进度提醒（超期未更新检测）
2. 项目经理：项目周报自动生成（LLM润色）
3. 质控人员：QC问题趋势分析
4. 合伙人：一页纸项目摘要
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpIndex, WorkingPaper, WpFileStatus

_logger = logging.getLogger(__name__)


# ═══ 1. 审计员：底稿编制进度提醒 ═══

async def get_stale_workpapers(
    db: AsyncSession,
    project_id: UUID,
    staff_id: UUID | None = None,
    stale_days: int = 3,
) -> list[dict]:
    """检测超期未更新的底稿

    规则：状态为 draft/edit_complete 且最后修改超过 stale_days 天
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)

    query = (
        sa.select(WpIndex, WorkingPaper)
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WpIndex.project_id == project_id,
            WpIndex.is_deleted == sa.false(),
            WorkingPaper.is_deleted == sa.false(),
            WorkingPaper.status.in_([WpFileStatus.draft, WpFileStatus.edit_complete]),
            WorkingPaper.updated_at < cutoff,
        )
    )
    if staff_id:
        query = query.where(WorkingPaper.assigned_to == staff_id)

    result = await db.execute(query.order_by(WorkingPaper.updated_at))
    rows = result.all()

    return [
        {
            "wp_code": idx.wp_code,
            "wp_name": idx.wp_name,
            "status": wp.status.value,
            "last_updated": wp.updated_at.isoformat() if wp.updated_at else None,
            "days_stale": (datetime.now(timezone.utc) - wp.updated_at).days if wp.updated_at else stale_days,
            "assigned_to": str(wp.assigned_to) if wp.assigned_to else None,
        }
        for idx, wp in rows
    ]


# ═══ 2. 项目经理：项目周报自动生成 ═══

async def generate_weekly_report(
    db: AsyncSession,
    project_id: UUID,
    week_start: date | None = None,
) -> dict[str, Any]:
    """生成项目周报数据 + LLM润色

    汇总本周：完成底稿数/新增调整/未解决问题/工时统计
    """
    from app.models.audit_platform_models import Adjustment, TrialBalance
    from app.models.core import Project

    if not week_start:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)

    ws = datetime.combine(week_start, datetime.min.time())
    we = datetime.combine(week_end, datetime.min.time())

    # 项目信息
    project = (await db.execute(sa.select(Project).where(Project.id == project_id))).scalar_one_or_none()
    project_name = project.client_name if project else "未知项目"

    # 本周完成的底稿
    completed_q = await db.execute(
        sa.select(sa.func.count()).select_from(WorkingPaper).join(WpIndex).where(
            WpIndex.project_id == project_id,
            WorkingPaper.status.in_([WpFileStatus.under_review, WpFileStatus.review_passed]),
            WorkingPaper.updated_at >= ws,
            WorkingPaper.updated_at < we,
        )
    )
    completed_count = completed_q.scalar() or 0

    # 本周新增调整分录
    adj_q = await db.execute(
        sa.select(sa.func.count()).select_from(Adjustment).where(
            Adjustment.project_id == project_id,
            Adjustment.is_deleted == sa.false(),
            Adjustment.created_at >= ws,
            Adjustment.created_at < we,
        )
    )
    new_adjustments = adj_q.scalar() or 0

    # 总体进度
    total_wp = (await db.execute(
        sa.select(sa.func.count()).select_from(WpIndex).where(
            WpIndex.project_id == project_id, WpIndex.is_deleted == sa.false()
        )
    )).scalar() or 0

    done_wp = (await db.execute(
        sa.select(sa.func.count()).select_from(WorkingPaper).join(WpIndex).where(
            WpIndex.project_id == project_id,
            WorkingPaper.status.in_([WpFileStatus.review_passed, WpFileStatus.archived]),
            WorkingPaper.is_deleted == sa.false(),
        )
    )).scalar() or 0

    # 超期底稿
    stale = await get_stale_workpapers(db, project_id, stale_days=5)

    raw_data = {
        "project_name": project_name,
        "week": f"{week_start.isoformat()} ~ {(week_end - timedelta(days=1)).isoformat()}",
        "completed_this_week": completed_count,
        "new_adjustments": new_adjustments,
        "total_workpapers": total_wp,
        "done_workpapers": done_wp,
        "completion_rate": round(done_wp / max(total_wp, 1) * 100, 1),
        "stale_workpapers": len(stale),
        "stale_details": stale[:5],
    }

    # LLM 润色
    polished = await _llm_polish_report(raw_data)

    return {
        "raw_data": raw_data,
        "polished_report": polished,
    }


# ═══ 3. 质控人员：QC问题趋势 ═══

async def get_qc_trend(
    db: AsyncSession,
    project_id: UUID,
    weeks: int = 4,
) -> dict[str, Any]:
    """QC问题趋势分析（按周统计各类问题数量变化）"""
    from app.models.workpaper_models import WpQcResult

    today = date.today()
    trend_data = []

    for w in range(weeks):
        week_end = today - timedelta(days=w * 7)
        week_start = week_end - timedelta(days=7)
        ws = datetime.combine(week_start, datetime.min.time())
        we = datetime.combine(week_end, datetime.min.time())

        # 该周的 QC 结果
        result = await db.execute(
            sa.select(sa.func.count()).select_from(WpQcResult).where(
                WpQcResult.project_id == project_id,
                WpQcResult.created_at >= ws,
                WpQcResult.created_at < we,
            )
        )
        count = result.scalar() or 0
        trend_data.append({
            "week": week_start.isoformat(),
            "issue_count": count,
        })

    trend_data.reverse()
    return {
        "project_id": str(project_id),
        "weeks": weeks,
        "trend": trend_data,
        "latest_count": trend_data[-1]["issue_count"] if trend_data else 0,
    }


# ═══ 4. 合伙人：一页纸项目摘要 ═══

async def generate_project_summary(
    db: AsyncSession,
    project_id: UUID,
) -> dict[str, Any]:
    """一页纸项目摘要（5分钟了解项目状态）

    包含：关键指标 + 风险点 + 待决事项 + 进度概览
    """
    from app.models.audit_platform_models import Adjustment, UnadjustedMisstatement, Materiality
    from app.models.core import Project

    project = (await db.execute(sa.select(Project).where(Project.id == project_id))).scalar_one_or_none()

    # 底稿进度
    total_wp = (await db.execute(
        sa.select(sa.func.count()).select_from(WpIndex).where(
            WpIndex.project_id == project_id, WpIndex.is_deleted == sa.false()
        )
    )).scalar() or 0

    done_wp = (await db.execute(
        sa.select(sa.func.count()).select_from(WorkingPaper).join(WpIndex).where(
            WpIndex.project_id == project_id,
            WorkingPaper.status.in_([WpFileStatus.review_passed, WpFileStatus.archived]),
            WorkingPaper.is_deleted == sa.false(),
        )
    )).scalar() or 0

    # 调整分录
    adj_count = (await db.execute(
        sa.select(sa.func.count()).select_from(Adjustment).where(
            Adjustment.project_id == project_id, Adjustment.is_deleted == sa.false()
        )
    )).scalar() or 0

    # 未更正错报
    misstatement_count = (await db.execute(
        sa.select(sa.func.count()).select_from(UnadjustedMisstatement).where(
            UnadjustedMisstatement.project_id == project_id, UnadjustedMisstatement.is_deleted == sa.false()
        )
    )).scalar() or 0

    # 超期底稿
    stale = await get_stale_workpapers(db, project_id, stale_days=5)

    summary_data = {
        "project_name": project.client_name if project else "",
        "audit_year": getattr(project, 'audit_year', None),
        "metrics": {
            "workpaper_progress": f"{done_wp}/{total_wp} ({round(done_wp/max(total_wp,1)*100)}%)",
            "adjustments": adj_count,
            "misstatements": misstatement_count,
            "stale_workpapers": len(stale),
        },
        "risks": [],
        "pending_decisions": [],
    }

    # 风险识别
    if len(stale) > 5:
        summary_data["risks"].append(f"超期底稿较多（{len(stale)}个），项目进度可能延误")
    if misstatement_count > 3:
        summary_data["risks"].append(f"未更正错报{misstatement_count}项，需评估是否影响审计意见")
    completion_rate = done_wp / max(total_wp, 1)
    if completion_rate < 0.5:
        summary_data["risks"].append(f"底稿完成率仅{round(completion_rate*100)}%，需加快进度")

    # 待决事项
    if stale:
        summary_data["pending_decisions"].append(f"催促{len(stale)}个超期底稿的编制人")
    if misstatement_count > 0:
        summary_data["pending_decisions"].append("与管理层沟通未更正错报处理方案")

    # LLM 生成摘要文字
    polished = await _llm_generate_summary(summary_data)
    summary_data["narrative"] = polished

    return summary_data


# ═══ LLM 辅助函数 ═══

async def _llm_polish_report(raw_data: dict) -> str:
    """LLM 润色周报"""
    try:
        from app.services.llm_client import chat_completion
        prompt = f"""请根据以下审计项目周报数据，生成一段简洁专业的周报摘要（3-5句话）：

项目：{raw_data['project_name']}
本周完成底稿：{raw_data['completed_this_week']} 个
新增调整分录：{raw_data['new_adjustments']} 笔
总体进度：{raw_data['done_workpapers']}/{raw_data['total_workpapers']}（{raw_data['completion_rate']}%）
超期底稿：{raw_data['stale_workpapers']} 个

要求：专业简洁，突出进展和风险，给出下周建议。"""

        result = await chat_completion(prompt, temperature=0.3, max_tokens=300)
        return result or "（LLM 生成失败，请查看原始数据）"
    except Exception as e:
        _logger.warning("LLM polish failed: %s", e)
        return f"本周完成{raw_data['completed_this_week']}个底稿，总进度{raw_data['completion_rate']}%，{raw_data['stale_workpapers']}个底稿超期待跟进。"


async def _llm_generate_summary(summary_data: dict) -> str:
    """LLM 生成项目摘要"""
    try:
        from app.services.llm_client import chat_completion
        metrics = summary_data["metrics"]
        risks = summary_data.get("risks", [])
        prompt = f"""请根据以下审计项目数据，生成一段合伙人可在5分钟内阅读的项目状态摘要（5-8句话）：

项目：{summary_data['project_name']}
底稿进度：{metrics['workpaper_progress']}
调整分录：{metrics['adjustments']} 笔
未更正错报：{metrics['misstatements']} 项
超期底稿：{metrics['stale_workpapers']} 个
风险点：{'; '.join(risks) if risks else '暂无重大风险'}

要求：开头一句话总结项目状态（正常/需关注/有风险），然后分点说明关键信息和建议。"""

        result = await chat_completion(prompt, temperature=0.3, max_tokens=400)
        return result or "（LLM 生成失败）"
    except Exception as e:
        _logger.warning("LLM summary failed: %s", e)
        return f"项目进度{metrics['workpaper_progress']}，{'有风险需关注' if risks else '进展正常'}。"
