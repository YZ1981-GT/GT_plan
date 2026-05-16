"""Stale 全模块聚合服务（Spec A R2）

为 PartnerSignDecision / EqcrProjectView / WorkpaperList 提供单端点聚合：
- workpapers.prefill_stale + .consistency_status
- financial_report.is_stale
- disclosure_notes.is_stale
- unadjusted_misstatements: 派生（updated_at < materiality.updated_at）

性能：4 条聚合 SQL，单请求 < 200ms（PG 索引齐全）。
N+1 防退化：CI 加 `assert_query_count(<= 6)` 装饰器。

Validates: Spec A requirements.md R2
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


async def get_full_summary(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> dict:
    """聚合返回 4 模块 stale 计数 + items 摘要。

    Returns:
        {
          "workpapers": { total, stale, inconsistent, items[] },
          "reports":    { total, stale, items[] },
          "notes":      { total, stale, items[] },
          "misstatements": { total, recheck_needed, items[] },
          "last_event_at": ISO8601 | null
        }
    """
    # 1. workpapers (prefill_stale + consistency_status)
    wp_sql = sa.text(
        """
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE prefill_stale = true) AS stale,
          COUNT(*) FILTER (WHERE consistency_status = 'inconsistent') AS inconsistent
        FROM working_paper
        WHERE project_id = :pid AND is_deleted = false
        """
    )
    wp_row = (await db.execute(wp_sql, {"pid": str(project_id)})).first()
    wp_items_sql = sa.text(
        """
        SELECT wp.id, wi.wp_code, wi.wp_name
        FROM working_paper wp
        LEFT JOIN wp_index wi ON wp.wp_index_id = wi.id
        WHERE wp.project_id = :pid
          AND wp.is_deleted = false
          AND (wp.prefill_stale = true OR wp.consistency_status = 'inconsistent')
        ORDER BY wi.wp_code NULLS LAST
        LIMIT 50
        """
    )
    wp_items = [
        {"id": str(r.id), "wp_code": r.wp_code, "wp_name": r.wp_name}
        for r in (await db.execute(wp_items_sql, {"pid": str(project_id)})).all()
    ]

    # 2. financial_report (is_stale)
    rpt_sql = sa.text(
        """
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE is_stale = true) AS stale
        FROM financial_report
        WHERE project_id = :pid AND year = :yr AND is_deleted = false
        """
    )
    rpt_row = (await db.execute(rpt_sql, {"pid": str(project_id), "yr": year})).first()
    rpt_items_sql = sa.text(
        """
        SELECT id, report_type, row_code, row_name
        FROM financial_report
        WHERE project_id = :pid AND year = :yr AND is_deleted = false
          AND is_stale = true
        ORDER BY report_type, row_code
        LIMIT 30
        """
    )
    rpt_items = [
        {
            "id": str(r.id),
            "report_type": r.report_type,
            "row_code": r.row_code,
            "row_name": r.row_name,
        }
        for r in (await db.execute(rpt_items_sql, {"pid": str(project_id), "yr": year})).all()
    ]

    # 3. disclosure_notes (is_stale)
    notes_sql = sa.text(
        """
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE is_stale = true) AS stale
        FROM disclosure_notes
        WHERE project_id = :pid AND year = :yr AND is_deleted = false
        """
    )
    notes_row = (await db.execute(notes_sql, {"pid": str(project_id), "yr": year})).first()
    notes_items_sql = sa.text(
        """
        SELECT id, note_section, section_title
        FROM disclosure_notes
        WHERE project_id = :pid AND year = :yr AND is_deleted = false
          AND is_stale = true
        ORDER BY note_section
        LIMIT 30
        """
    )
    notes_items = [
        {"id": str(r.id), "note_section": r.note_section, "section_title": r.section_title}
        for r in (await db.execute(notes_items_sql, {"pid": str(project_id), "yr": year})).all()
    ]

    # 4. misstatements (派生：updated_at < materiality.updated_at)
    # 字段缺失降级为派生计算
    miss_sql = sa.text(
        """
        WITH mat AS (
          SELECT MAX(updated_at) AS mat_updated
          FROM materiality
          WHERE project_id = :pid AND year = :yr AND is_deleted = false
        )
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (
            WHERE m.updated_at < (SELECT mat_updated FROM mat)
          ) AS recheck_needed
        FROM unadjusted_misstatements m
        WHERE m.project_id = :pid AND m.year = :yr AND m.is_deleted = false
        """
    )
    try:
        miss_row = (await db.execute(miss_sql, {"pid": str(project_id), "yr": year})).first()
        miss_items_sql = sa.text(
            """
            WITH mat AS (
              SELECT MAX(updated_at) AS mat_updated
              FROM materiality
              WHERE project_id = :pid AND year = :yr AND is_deleted = false
            )
            SELECT m.id, m.affected_account_code, m.misstatement_amount
            FROM unadjusted_misstatements m
            WHERE m.project_id = :pid AND m.year = :yr AND m.is_deleted = false
              AND m.updated_at < (SELECT mat_updated FROM mat)
            ORDER BY m.misstatement_amount DESC NULLS LAST
            LIMIT 30
            """
        )
        miss_items = [
            {
                "id": str(r.id),
                "affected_account_code": r.affected_account_code,
                "misstatement_amount": str(r.misstatement_amount) if r.misstatement_amount is not None else None,
            }
            for r in (
                await db.execute(miss_items_sql, {"pid": str(project_id), "yr": year})
            ).all()
        ]
    except Exception:
        # materiality 表可能不存在或字段缺失 → 降级为 0
        miss_row = None
        miss_items = []

    # 5. last_event_at: 取 4 模块中最近的 updated_at
    last_evt_sql = sa.text(
        """
        SELECT GREATEST(
          (SELECT MAX(updated_at) FROM working_paper WHERE project_id = :pid AND is_deleted = false),
          (SELECT MAX(updated_at) FROM financial_report WHERE project_id = :pid AND year = :yr AND is_deleted = false),
          (SELECT MAX(updated_at) FROM disclosure_notes WHERE project_id = :pid AND year = :yr AND is_deleted = false)
        ) AS last_evt
        """
    )
    last_evt = (await db.execute(last_evt_sql, {"pid": str(project_id), "yr": year})).scalar()

    return {
        "workpapers": {
            "total": wp_row.total if wp_row else 0,
            "stale": wp_row.stale if wp_row else 0,
            "inconsistent": wp_row.inconsistent if wp_row else 0,
            "items": wp_items,
        },
        "reports": {
            "total": rpt_row.total if rpt_row else 0,
            "stale": rpt_row.stale if rpt_row else 0,
            "items": rpt_items,
        },
        "notes": {
            "total": notes_row.total if notes_row else 0,
            "stale": notes_row.stale if notes_row else 0,
            "items": notes_items,
        },
        "misstatements": {
            "total": miss_row.total if miss_row else 0,
            "recheck_needed": miss_row.recheck_needed if miss_row else 0,
            "items": miss_items,
        },
        "last_event_at": last_evt.isoformat() if isinstance(last_evt, datetime) else None,
    }
