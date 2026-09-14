"""workpaper_summaries_service — 底稿摘要 API

GET /api/projects/{pid}/workpaper-summaries/{key}

提供跨底稿摘要数据供 A17/A18 等完成阶段底稿消费。
"""

from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

# ── 摘要注册表：key → {source_wp, description} ──

SUMMARY_REGISTRY: dict[str, dict] = {
    "misstatement": {
        "source_wp": ["A13-1", "A13-4"],
        "description": "错报计数、未更正列表",
    },
    "control_deficiency": {
        "source_wp": ["A14-1"],
        "description": "缺陷数、重大/重要分级",
    },
    "going_concern": {
        "source_wp": ["A15-1"],
        "description": "调查结论、疑虑项摘要",
    },
    "governance_communication": {
        "source_wp": ["A10-2"],
        "description": "沟通事项条数（stub）",
    },
    "related_party": {
        "source_wp": ["A7-1"],
        "description": "交易/往来计数",
    },
}


async def _get_wp_id(db: AsyncSession, project_id: UUID, wp_code: str) -> UUID | None:
    result = await db.execute(
        text(
            """
            SELECT wp.id FROM working_paper wp
            JOIN wp_index wi ON wi.id = wp.wp_index_id
            WHERE wp.project_id = :pid AND wi.wp_code = :code AND wp.is_deleted = false
            LIMIT 1
            """
        ),
        {"pid": str(project_id), "code": wp_code},
    )
    val = result.scalar_one_or_none()
    return UUID(str(val)) if val else None


async def _related_party_summary(db: AsyncSession, project_id: UUID) -> dict:
    wp_id = await _get_wp_id(db, project_id, "A7-1")
    if wp_id is None:
        return {
            "ready": False,
            "key": "related_party",
            "source_wp": ["A7-1"],
            "reason": "项目内无 A7-1 底稿",
        }

    count_r = await db.execute(
        text(
            """
            SELECT COUNT(*) FROM checklist_responses
            WHERE wp_id = :wp_id AND conclusion IS NOT NULL AND conclusion <> ''
            """
        ),
        {"wp_id": str(wp_id)},
    )
    filled = int(count_r.scalar() or 0)

    total_r = await db.execute(
        text("SELECT COUNT(*) FROM checklist_responses WHERE wp_id = :wp_id"),
        {"wp_id": str(wp_id)},
    )
    total = int(total_r.scalar() or 0)

    lines = [
        f"A7-1 关联交易及往来：已填写 {filled} 条",
    ]
    if total > filled:
        lines.append(f"（共 {total} 条记录，{total - filled} 条待结论）")

    return {
        "ready": True,
        "key": "related_party",
        "source_wp": ["A7-1"],
        "summary_text": "\n".join(lines),
        "filled_count": filled,
        "total_count": total,
    }


async def _going_concern_summary(db: AsyncSession, project_id: UUID) -> dict:
    wp_id = await _get_wp_id(db, project_id, "A15-1")
    if wp_id is None:
        return {
            "ready": False,
            "key": "going_concern",
            "source_wp": ["A15-1"],
            "reason": "项目内无 A15-1 底稿",
        }

    concl_r = await db.execute(
        text(
            """
            SELECT conclusion, remark FROM checklist_responses
            WHERE wp_id = :wp_id AND item_id = 'A15-1-conclusion'
            LIMIT 1
            """
        ),
        {"wp_id": str(wp_id)},
    )
    row = concl_r.first()

    filled_r = await db.execute(
        text(
            """
            SELECT COUNT(*) FROM checklist_responses
            WHERE wp_id = :wp_id AND conclusion IS NOT NULL AND conclusion <> ''
            """
        ),
        {"wp_id": str(wp_id)},
    )
    filled = int(filled_r.scalar() or 0)

    if row is None and filled == 0:
        return {
            "ready": False,
            "key": "going_concern",
            "source_wp": ["A15-1"],
            "reason": "A15-1 尚无填写数据",
        }

    lines = [f"A15-1 持续经营调查：已填写 {filled} 项"]
    if row and row.conclusion:
        lines.append(f"调查结论：{row.conclusion}")
    if row and row.remark:
        lines.append(str(row.remark).strip())

    return {
        "ready": True,
        "key": "going_concern",
        "source_wp": ["A15-1"],
        "summary_text": "\n".join(lines),
        "conclusion": row.conclusion if row else None,
        "filled_count": filled,
    }


async def _misstatement_summary(db: AsyncSession, project_id: UUID) -> dict:
    try:
        from app.models.audit_platform_models import UnadjustedMisstatement

        count_stmt = (
            select(func.count())
            .select_from(UnadjustedMisstatement)
            .where(
                UnadjustedMisstatement.project_id == project_id,
                UnadjustedMisstatement.is_deleted == False,  # noqa: E712
            )
        )
        result = await db.execute(count_stmt)
        count = int(result.scalar() or 0)
        return {
            "ready": True,
            "key": "misstatement",
            "source_wp": ["A13-1", "A13-4"],
            "summary_text": f"A13 未更正错报：{count} 项",
            "count": count,
        }
    except Exception:
        return {
            "ready": False,
            "key": "misstatement",
            "source_wp": ["A13-1", "A13-4"],
            "reason": "错报数据源查询失败",
        }


async def _control_deficiency_summary(db: AsyncSession, project_id: UUID) -> dict:
    try:
        from app.models.phase15_models import IssueTicket

        count_stmt = (
            select(func.count())
            .select_from(IssueTicket)
            .where(
                IssueTicket.project_id == project_id,
                IssueTicket.category == "internal_control",
            )
        )
        result = await db.execute(count_stmt)
        count = int(result.scalar() or 0)
        return {
            "ready": True,
            "key": "control_deficiency",
            "source_wp": ["A14-1"],
            "summary_text": f"A14 内控缺陷：{count} 项",
            "count": count,
        }
    except Exception:
        return {
            "ready": False,
            "key": "control_deficiency",
            "source_wp": ["A14-1"],
            "reason": "缺陷数据源查询失败",
        }


async def _governance_communication_summary(db: AsyncSession, project_id: UUID) -> dict:
    wp_id = await _get_wp_id(db, project_id, "A10-2")
    if wp_id is None:
        return {
            "ready": False,
            "key": "governance_communication",
            "source_wp": ["A10-2"],
            "reason": "项目内无 A10-2 底稿",
        }

    filled_r = await db.execute(
        text(
            """
            SELECT COUNT(*) FROM checklist_responses
            WHERE wp_id = :wp_id AND conclusion IS NOT NULL AND conclusion <> ''
            """
        ),
        {"wp_id": str(wp_id)},
    )
    filled = int(filled_r.scalar() or 0)
    total_r = await db.execute(
        text("SELECT COUNT(*) FROM checklist_responses WHERE wp_id = :wp_id"),
        {"wp_id": str(wp_id)},
    )
    total = int(total_r.scalar() or 0)

    if total == 0 and filled == 0:
        return {
            "ready": False,
            "key": "governance_communication",
            "source_wp": ["A10-2"],
            "reason": "A10-2 尚无填写数据",
        }

    summary = f"A10-2 治理层沟通记录：已填写 {filled} 条"
    if total > filled:
        summary += f"（共 {total} 条，{total - filled} 条待结论）"
    return {
        "ready": True,
        "key": "governance_communication",
        "source_wp": ["A10-2"],
        "summary_text": summary,
        "filled_count": filled,
        "total_count": total,
    }


_IMPLEMENTORS: dict[str, object] = {
    "related_party": _related_party_summary,
    "going_concern": _going_concern_summary,
    "misstatement": _misstatement_summary,
    "control_deficiency": _control_deficiency_summary,
    "governance_communication": _governance_communication_summary,
}


async def get_workpaper_summary(
    db: AsyncSession | None, project_id: UUID, key: str
) -> dict | None:
    """获取指定 key 的底稿摘要。

    db=None 时返回 stub（单测兼容）；有 db 时走实现器。
    """
    entry = SUMMARY_REGISTRY.get(key)
    if entry is None:
        return None

    if db is None:
        return {
            "ready": False,
            "key": key,
            "source_wp": entry["source_wp"],
            "reason": "数据源未就绪",
        }

    impl = _IMPLEMENTORS.get(key)
    if impl is None:
        return {
            "ready": False,
            "key": key,
            "source_wp": entry["source_wp"],
            "reason": "数据源未就绪",
        }

    return await impl(db, project_id)
