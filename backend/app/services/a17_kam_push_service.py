"""a17_kam_push_service — KAM → 审计报告单向 push

从 A17-2-1 (checklist_responses) 读取 KAM 条目，格式化后写入
audit_report.report_body_json 的 KAM 段落（section_id="kam"）。

设计原则:
  - A17-2-1 是 KAM 的权威源（authoritative）
  - 单向 push: A17-2-1 → 审计报告 KAM 段落
  - 报告 KAM 段落被完全覆写（非增量合并）
  - P4+ 可选: 报告修订 → A17-2-1 stale 标记（本期不实现双向）
"""

import json
import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import AuditReport

logger = logging.getLogger(__name__)


async def push_kam_to_report(
    db: AsyncSession, project_id: UUID, wp_id: UUID
) -> dict:
    """Push KAM data from A17-2-1 to audit report KAM section.

    Steps:
    1. Load KAM entries from checklist_responses (A17-2-1-KAM-*)
    2. Format KAM data for audit report (matter + response per item)
    3. Write to audit_report.report_body_json KAM section
    4. Return push result summary

    Returns:
        {"success": bool, "pushed_count": int, "message": str}
    """
    # 1. Load KAM entries
    entries = await _load_kam_entries(db, wp_id)
    if not entries:
        return {
            "success": False,
            "pushed_count": 0,
            "message": "A17-2-1 中未找到 KAM 条目，请先在底稿中添加关键审计事项",
        }

    # 2. Format for report
    kam_items = _format_kam_for_report(entries)

    # 3. Find audit report
    report = await _get_audit_report(db, project_id)
    if report is None:
        return {
            "success": False,
            "pushed_count": 0,
            "message": "该项目尚未创建审计报告，请先在报告模块中初始化审计报告",
        }

    # 4. Write KAM section into report_body_json
    _write_kam_to_report_body(report, kam_items)
    await db.flush()

    pushed = len(kam_items)
    logger.info(
        "Pushed %d KAM items from A17-2-1 (wp_id=%s) to audit_report (project=%s)",
        pushed, wp_id, project_id,
    )
    return {
        "success": True,
        "pushed_count": pushed,
        "message": f"已成功推送 {pushed} 条关键审计事项至审计报告",
    }


# ─── Private helpers ──────────────────────────────────────────────────


async def _load_kam_entries(
    db: AsyncSession, wp_id: UUID
) -> list[tuple[str, str, str, str]]:
    """Load KAM entries from checklist_responses. Returns (item_id, conclusion, remark, wp_ref)."""
    result = await db.execute(
        text("""
            SELECT item_id, conclusion, remark, wp_ref
            FROM checklist_responses
            WHERE wp_id = :wp_id
              AND item_id LIKE 'A17-2-1-KAM%'
            ORDER BY item_id
        """),
        {"wp_id": str(wp_id)},
    )
    return [
        (row.item_id, row.conclusion or "", row.remark or "", row.wp_ref or "")
        for row in result.fetchall()
    ]


def _format_kam_for_report(
    entries: list[tuple[str, str, str, str]],
) -> list[dict]:
    """Format KAM entries into report_body_json items structure.

    Report KAM item schema: {"matter": str, "response": str}
    - matter: KAM 标题 + 情况描述 + 确定原因
    - response: 审计应对
    """
    items = []
    for item_id, title, remark_json, wp_ref in entries:
        remark = _parse_remark(remark_json)
        # Build matter: combine title, situation, and reason
        matter_parts = []
        if title:
            matter_parts.append(title)
        situation = remark.get("situation", "")
        if situation:
            matter_parts.append(situation)
        reason = remark.get("reason", "")
        if reason:
            matter_parts.append(f"确定为关键审计事项的原因：{reason}")
        matter = "\n".join(matter_parts) if matter_parts else title or item_id

        # Build response
        response = remark.get("response", "")

        items.append({"matter": matter, "response": response})
    return items


def _parse_remark(remark_json: str) -> dict:
    """Parse remark JSON string, return empty dict on failure."""
    if not remark_json:
        return {}
    try:
        return json.loads(remark_json)
    except (json.JSONDecodeError, TypeError):
        return {}


async def _get_audit_report(
    db: AsyncSession, project_id: UUID
) -> AuditReport | None:
    """Get the project's audit report (latest non-deleted)."""
    result = await db.execute(
        sa.select(AuditReport).where(
            AuditReport.project_id == project_id,
            AuditReport.is_deleted == sa.false(),
        ).order_by(AuditReport.year.desc()).limit(1)
    )
    return result.scalar_one_or_none()


def _write_kam_to_report_body(report: AuditReport, kam_items: list[dict]) -> None:
    """Overwrite the KAM section in report_body_json with new items.

    If report_body_json is None or has no sections, initialize it.
    If KAM section exists, overwrite items. Otherwise append a new KAM section.
    """
    body = report.report_body_json or {}
    sections = body.get("sections", [])

    # Find existing KAM section
    kam_section_idx = None
    for idx, section in enumerate(sections):
        if section.get("section_id") == "kam" or section.get("section_name") == "关键审计事项段":
            kam_section_idx = idx
            break

    new_kam_section = {
        "section_id": "kam",
        "section_name": "关键审计事项段",
        "section_order": 3,
        "items": kam_items,
        "content": "",
        "pushed_from": "A17-2-1",
    }

    if kam_section_idx is not None:
        sections[kam_section_idx] = new_kam_section
    else:
        sections.append(new_kam_section)

    body["sections"] = sections
    # Force SQLAlchemy to detect JSONB mutation
    report.report_body_json = body
