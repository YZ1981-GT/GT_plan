"""A13-5 沟通函草稿生成服务

根据当前未更正错报生成管理层沟通函草稿（Communication Draft），
仅包含 prior_year_status IN ('continuing', 'new') 的记录。

模板选择逻辑：
- Template A: cumulative < PM × 0.75 (远低于重要性水平)
- Template B: PM × 0.75 ≤ cumulative < PM (接近重要性水平)
- Template C: cumulative ≥ PM (超过重要性水平)

Validates: Requirements 5.1, 5.2, 5.3, 5.5, 5.6, 5.7
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    Materiality,
    UnadjustedMisstatement,
)
from app.models.workpaper_models import WorkingPaper, WpIndex

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：模板选择
# ═══════════════════════════════════════════════════════════════════════════════


def select_template(cumulative: Decimal, pm: Decimal | None) -> str:
    """根据累计未更正错报与 PM 选择结论模板。

    Returns:
        "A" — cumulative < PM × 0.75
        "B" — PM × 0.75 ≤ cumulative < PM
        "C" — cumulative ≥ PM
        "A" — PM is None/0 时默认 A（保守处理）
    """
    if pm is None or pm <= 0:
        return "A"
    threshold_75 = pm * Decimal("0.75")
    if cumulative < threshold_75:
        return "A"
    elif cumulative < pm:
        return "B"
    else:
        return "C"


def _get_conclusion_text(template_type: str, cumulative: Decimal, pm: Decimal | None) -> str:
    """根据模板类型生成结论文本。"""
    pm_str = f"{float(pm):,.2f}" if pm else "未确定"
    cum_str = f"{float(cumulative):,.2f}"

    if template_type == "A":
        return (
            f"未更正错报累计金额 {cum_str} 元，远低于整体重要性水平 {pm_str} 元。"
            "我们认为上述未更正错报单独或汇总对财务报表整体不构成重大影响。"
        )
    elif template_type == "B":
        return (
            f"未更正错报累计金额 {cum_str} 元，接近整体重要性水平 {pm_str} 元。"
            "虽然未超过重要性水平，但已接近阈值，我们提请管理层关注并考虑更正。"
            "若不予更正，我们将在进一步评估后确定其对审计意见的影响。"
        )
    else:  # C
        return (
            f"未更正错报累计金额 {cum_str} 元，已达到或超过整体重要性水平 {pm_str} 元。"
            "我们强烈建议管理层更正上述错报。"
            "若管理层不予更正，我们需要考虑对审计报告意见类型的影响。"
        )


def build_draft_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从错报记录构建草稿条目列表。

    仅包含 prior_year_status IN ('continuing', 'new') 的记录。
    每条包含: seq, description, affected_account, amount, misstatement_type, management_reason
    """
    items = []
    seq = 0
    for row in rows:
        status = row.get("prior_year_status", "new")
        if status not in ("continuing", "new"):
            continue
        seq += 1
        items.append({
            "seq": seq,
            "description": row.get("misstatement_description", ""),
            "affected_account": row.get("affected_account_name", "")
                or row.get("affected_account_code", ""),
            "amount": float(Decimal(str(row["misstatement_amount"]))),
            "misstatement_type": row.get("misstatement_type", "factual"),
            "management_reason": row.get("management_reason", ""),
        })
    return items


def generate_communication_draft(
    rows: list[dict[str, Any]],
    pm: Decimal | None,
) -> dict[str, Any]:
    """纯函数：从错报记录生成沟通函草稿 JSON。

    Returns:
        communication-draft-v1 格式 dict，或 None 如果无可用记录
    """
    items = build_draft_items(rows)

    if not items:
        return {"_empty": True, "message": "当前无未更正错报，无需生成沟通函"}

    cumulative = Decimal(str(sum(item["amount"] for item in items)))
    template_type = select_template(cumulative, pm)
    conclusion_text = _get_conclusion_text(template_type, cumulative, pm)

    return {
        "_format": "communication-draft-v1",
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "template_type": template_type,
        "items": items,
        "summary": {
            "total_count": len(items),
            "cumulative_amount": float(cumulative),
            "pm": float(pm) if pm else None,
            "ratio": round(float(cumulative / pm), 4) if pm and pm > 0 else 0.0,
            "conclusion": conclusion_text,
        },
        "conclusion_text": conclusion_text,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DB 层
# ═══════════════════════════════════════════════════════════════════════════════


async def _fetch_active_misstatements(
    db: AsyncSession, project_id: UUID, year: int
) -> list[dict[str, Any]]:
    """查询项目年度所有未删除的错报记录（完整字段）。"""
    tbl = UnadjustedMisstatement.__table__
    q = sa.select(
        tbl.c.misstatement_description,
        tbl.c.affected_account_code,
        tbl.c.affected_account_name,
        tbl.c.misstatement_amount,
        tbl.c.misstatement_type,
        tbl.c.management_reason,
        tbl.c.prior_year_status,
    ).where(
        tbl.c.project_id == project_id,
        tbl.c.year == year,
        tbl.c.is_deleted == sa.false(),
    ).order_by(tbl.c.created_at)

    result = await db.execute(q)
    return [dict(r._mapping) for r in result.fetchall()]


async def _fetch_pm(db: AsyncSession, project_id: UUID, year: int) -> Decimal | None:
    """查询 B15 重要性水平 PM。"""
    q = sa.select(Materiality.overall_materiality).where(
        Materiality.project_id == project_id,
        Materiality.year == year,
        Materiality.is_deleted == sa.false(),
    )
    result = await db.execute(q)
    val = result.scalar_one_or_none()
    return val


async def _persist_draft_to_a13_5(
    db: AsyncSession, project_id: UUID, year: int, draft: dict[str, Any]
) -> bool:
    """将草稿持久化到 A13-5 sheet 的 parsed_data.html_data['communication_draft']。

    Req 5.7: 下次打开直接展示，无需重新生成。
    """
    wp_idx = WpIndex.__table__
    wp_tbl = WorkingPaper.__table__

    q = (
        sa.select(wp_tbl.c.id, wp_tbl.c.parsed_data)
        .select_from(wp_tbl.join(wp_idx, wp_tbl.c.wp_index_id == wp_idx.c.id))
        .where(
            wp_idx.c.project_id == project_id,
            wp_idx.c.wp_code.in_(["A13", "A13-1", "A13-5"]),
            wp_idx.c.is_deleted == sa.false(),
            wp_tbl.c.is_deleted == sa.false(),
        )
        .limit(1)
    )
    result = await db.execute(q)
    row = result.first()
    if row is None:
        logger.warning(
            "A13 workpaper not found for draft persist: project=%s year=%s",
            project_id, year,
        )
        return False

    wp_id = row.id
    parsed_data = row.parsed_data or {}
    html_data = parsed_data.get("html_data", {})
    html_data["communication_draft"] = draft
    parsed_data["html_data"] = html_data

    update_q = (
        sa.update(wp_tbl)
        .where(wp_tbl.c.id == wp_id)
        .values(parsed_data=parsed_data, updated_at=sa.func.now())
    )
    await db.execute(update_q)
    await db.flush()
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 公共 API
# ═══════════════════════════════════════════════════════════════════════════════


async def create_communication_draft(
    db: AsyncSession, project_id: UUID, year: int
) -> dict[str, Any]:
    """生成并持久化沟通函草稿。

    Returns:
        communication-draft-v1 格式 dict
    """
    rows = await _fetch_active_misstatements(db, project_id, year)
    pm = await _fetch_pm(db, project_id, year)
    draft = generate_communication_draft(rows, pm)

    # 持久化到 A13-5（即使是 empty 也持久化，下次直接返回）
    if not draft.get("_empty"):
        await _persist_draft_to_a13_5(db, project_id, year, draft)

    return draft
