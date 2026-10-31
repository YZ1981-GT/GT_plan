"""Stale 全模块聚合服务（Spec A R2）

为 PartnerSignDecision / EqcrProjectView / WorkpaperList 提供单端点聚合：
- workpapers.prefill_stale + .consistency_status
- financial_report 过期（report_freshness.stale_clause，含计算版本不是当前版本的存量行）+ 计算失败 / 口径留空计数
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


def _sql(statement: str) -> sa.TextClause:
    """裸 SQL 的 ``:pid`` 按 UUID 类型绑定：PG 上与按字符串绑定等价；SQLite 上 UUID 列存 32 位 hex，
    按带连字符的字符串比较恒不命中 —— 历史实现在 SQLite 上永远汇总出 0，复用它的测试因此恒绿 / 恒空。"""
    return sa.text(statement).bindparams(sa.bindparam("pid", type_=sa.Uuid()))


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
    pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
    # 1. workpapers (prefill_stale + consistency_status)
    wp_sql = _sql(
        """
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE prefill_stale = true) AS stale,
          COUNT(*) FILTER (WHERE consistency_status = 'inconsistent') AS inconsistent
        FROM working_paper
        WHERE project_id = :pid AND is_deleted = false
        """
    )
    wp_row = (await db.execute(wp_sql, {"pid": pid})).first()
    wp_items_sql = _sql(
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
        for r in (await db.execute(wp_items_sql, {"pid": pid})).all()
    ]

    # 2. financial_report（过期 = report_freshness.stale_clause：已标过期或计算版本不是当前版本；
    #    明细同时带计算失败原因 calc_error 与口径留空原因 blank_reason）
    from app.services.report_freshness import count_summary, list_rows, stale_clause

    rpt_counts = await count_summary(db, pid, year)
    rpt_items = [
        {k: r[k] for k in ("id", "report_type", "row_code", "row_name", "calc_error", "blank_reason")}
        for r in await list_rows(db, pid, year, stale_clause(), limit=30)
    ]

    # 3. disclosure_notes (is_stale)
    notes_sql = _sql(
        """
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE is_stale = true) AS stale
        FROM disclosure_notes
        WHERE project_id = :pid AND year = :yr AND is_deleted = false
        """
    )
    notes_row = (await db.execute(notes_sql, {"pid": pid, "yr": year})).first()
    notes_items_sql = _sql(
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
        for r in (await db.execute(notes_items_sql, {"pid": pid, "yr": year})).all()
    ]

    # 4. misstatements (派生：updated_at < materiality.updated_at)
    # 字段缺失降级为派生计算
    miss_sql = _sql(
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
    miss_unavailable = False
    try:
        # SAVEPOINT：本段失败只回滚本段 —— PG 上未包 SAVEPOINT 的失败会中止整个事务，后续查询全部连带失败
        async with db.begin_nested():
            miss_row = (await db.execute(miss_sql, {"pid": pid, "yr": year})).first()
            miss_items_sql = _sql(
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
                    await db.execute(miss_items_sql, {"pid": pid, "yr": year})
                ).all()
            ]
    except Exception:
        # 查询失败如实标「不可用」（不是「没有待评估错报」）：签发清单据此判检查失败；仪表盘仍显示 0
        miss_row = None
        miss_items = []
        miss_unavailable = True

    # 5. last_event_at: 取 3 模块中最近的 updated_at（三条 MAX 在 Python 侧取最大：GREATEST 是 PG 专有，
    #    SQLite 上整条报错 —— 签发清单复用本函数，单测在 SQLite 上会因此恒判「执行失败」）
    last_candidates = []
    for sql in (
        "SELECT MAX(updated_at) FROM working_paper WHERE project_id = :pid AND is_deleted = false",
        "SELECT MAX(updated_at) FROM financial_report WHERE project_id = :pid AND year = :yr AND is_deleted = false",
        "SELECT MAX(updated_at) FROM disclosure_notes WHERE project_id = :pid AND year = :yr AND is_deleted = false",
    ):
        value = (await db.execute(_sql(sql), {"pid": pid, "yr": year})).scalar()
        if isinstance(value, datetime):
            last_candidates.append(value if value.tzinfo else value.replace(tzinfo=timezone.utc))
    last_evt = max(last_candidates) if last_candidates else None

    return {
        "workpapers": {
            "total": wp_row.total if wp_row else 0,
            "stale": wp_row.stale if wp_row else 0,
            "inconsistent": wp_row.inconsistent if wp_row else 0,
            "items": wp_items,
        },
        "reports": {
            "total": rpt_counts.total,
            "stale": rpt_counts.stale,
            "calc_error": rpt_counts.calc_error,
            "blank": rpt_counts.blank,
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
            "unavailable": miss_unavailable,
        },
        "last_event_at": last_evt.isoformat() if isinstance(last_evt, datetime) else None,
    }
