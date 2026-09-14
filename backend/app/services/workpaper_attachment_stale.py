"""底稿关联附件 — stale 失效信息（Req6）。

spec: attachment-workpaper-linkage-convergence Task 6.1

分级：
  - definite：该底稿作为 source 的 evidence_refs 已 inactive，或关联附件侧 ref 已 inactive
  - conservative：仅 working_paper.prefill_stale（无明确 ref 失效行）
fail-open：查询失败返回 None（不附加 stale_info）。
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_SOURCE_TYPES_WP = ("working_paper", "wp", "workpaper")
_SAFE_ID = re.compile(r"^[0-9a-fA-F-]{36}$")


def _sql_in_strings(values: list[str]) -> str:
    """仅允许 UUID 形态字符串，拼成 ``('a','b')``；空则 ``(NULL)``（永不命中）。"""
    cleaned = [v for v in values if isinstance(v, str) and _SAFE_ID.match(v)]
    if not cleaned:
        return "(NULL)"
    return "(" + ",".join(f"'{v}'" for v in cleaned) + ")"


async def build_stale_info(
    db: AsyncSession,
    *,
    wp_id: UUID,
    attachment_ids: list[str],
    wp_meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """构造 additive ``stale_info``；无失效时返回 has_stale=false；失败返回 None。

    ``wp_meta`` 可选（``AttachmentService._resolve_wp_meta``），避免重复查 WorkingPaper。
    """
    try:
        from app.models.core import Project
        from app.models.workpaper_models import WorkingPaper

        if wp_meta is not None and wp_meta.get("project_id") is not None:
            project_id = wp_meta["project_id"]
            prefill_stale = bool(wp_meta.get("prefill_stale"))
            audit_year = wp_meta.get("audit_year")
        else:
            row = (
                await db.execute(
                    sa.select(
                        WorkingPaper.project_id,
                        WorkingPaper.prefill_stale,
                        Project.audit_year,
                    )
                    .join(Project, Project.id == WorkingPaper.project_id)
                    .where(WorkingPaper.id == wp_id)
                )
            ).first()
            if row is None:
                return {
                    "has_stale": False,
                    "level": None,
                    "items": [],
                    "project_id": None,
                }
            project_id, prefill_stale, audit_year = row[0], bool(row[1]), row[2]

        items: list[dict[str, Any]] = []

        try:
            items.extend(
                await _inactive_refs_from_wp(
                    db,
                    project_id=project_id,
                    audit_year=audit_year,
                    wp_id=wp_id,
                )
            )
            if attachment_ids:
                items.extend(
                    await _inactive_refs_to_attachments(
                        db,
                        project_id=project_id,
                        audit_year=audit_year,
                        attachment_ids=attachment_ids,
                    )
                )
        except Exception:
            logger.warning(
                "event=awp_stale_refs_query_fail_open wp_id=%s",
                wp_id,
                exc_info=True,
            )

        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for it in items:
            key = f"{it.get('kind')}:{it.get('id')}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(it)

        has_definite = len(deduped) > 0
        if has_definite:
            return {
                "has_stale": True,
                "level": "definite",
                "items": deduped[:50],
                "project_id": str(project_id),
            }
        if prefill_stale:
            return {
                "has_stale": True,
                "level": "conservative",
                "items": [
                    {
                        "kind": "prefill",
                        "id": str(wp_id),
                        "reason": "prefill_stale",
                        "label": "底稿预填/依赖已标脏（保守提示）",
                    }
                ],
                "project_id": str(project_id),
            }
        return {
            "has_stale": False,
            "level": None,
            "items": [],
            "project_id": str(project_id),
        }
    except Exception:
        logger.warning("event=awp_stale_fail_open wp_id=%s", wp_id, exc_info=True)
        return None


async def _inactive_refs_from_wp(
    db: AsyncSession,
    *,
    project_id: UUID,
    audit_year: int | None,
    wp_id: UUID,
) -> list[dict[str, Any]]:
    """query_refs_from_source 语义：source=底稿 且 status=inactive。"""
    # source_type 为固定白名单，非用户输入
    stype_sql = "(" + ",".join(f"'{t}'" for t in _SOURCE_TYPES_WP) + ")"
    year_clause = "AND audit_year = :yr" if audit_year is not None else ""
    params: dict[str, Any] = {"pid": str(project_id), "sid": str(wp_id)}
    if audit_year is not None:
        params["yr"] = int(audit_year)

    rows = (
        await db.execute(
            sa.text(
                f"""
                SELECT id, evidence_type, evidence_id, label, status
                FROM evidence_refs
                WHERE project_id = :pid
                  {year_clause}
                  AND source_type IN {stype_sql}
                  AND source_id = :sid
                  AND status = 'inactive'
                ORDER BY created_at DESC
                LIMIT 30
                """
            ),
            params,
        )
    ).mappings().all()

    return [
        {
            "kind": "evidence_ref",
            "id": str(r["id"]),
            "evidence_id": str(r["evidence_id"]),
            "evidence_type": r["evidence_type"],
            "reason": "ref_inactive",
            "label": r["label"] or "证据引用已失效",
        }
        for r in rows
    ]


async def _inactive_refs_to_attachments(
    db: AsyncSession,
    *,
    project_id: UUID,
    audit_year: int | None,
    attachment_ids: list[str],
) -> list[dict[str, Any]]:
    eids_sql = _sql_in_strings(attachment_ids[:100])
    if eids_sql == "(NULL)":
        return []
    year_clause = "AND audit_year = :yr" if audit_year is not None else ""
    params: dict[str, Any] = {"pid": str(project_id)}
    if audit_year is not None:
        params["yr"] = int(audit_year)

    rows = (
        await db.execute(
            sa.text(
                f"""
                SELECT id, evidence_type, evidence_id, label, status
                FROM evidence_refs
                WHERE project_id = :pid
                  {year_clause}
                  AND evidence_id IN {eids_sql}
                  AND status = 'inactive'
                ORDER BY created_at DESC
                LIMIT 30
                """
            ),
            params,
        )
    ).mappings().all()

    return [
        {
            "kind": "evidence_ref",
            "id": str(r["id"]),
            "evidence_id": str(r["evidence_id"]),
            "evidence_type": r["evidence_type"],
            "reason": "attachment_ref_inactive",
            "label": r["label"] or "关联附件证据引用已失效",
        }
        for r in rows
    ]
