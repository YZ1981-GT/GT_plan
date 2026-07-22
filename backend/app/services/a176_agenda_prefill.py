"""A17-6 总结会议程自动预填建议."""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.workpaper_summaries_service import get_workpaper_summary

logger = logging.getLogger(__name__)

_AGENDA_KEYS = tuple(str(i) for i in range(1, 11))


def _empty_agenda() -> dict[str, str]:
    return {k: "" for k in _AGENDA_KEYS}


async def _get_project_year(db: AsyncSession, project_id: UUID) -> int | None:
    try:
        from app.models.core import Project

        result = await db.execute(
            select(Project.audit_year, Project.audit_period_end).where(Project.id == project_id)
        )
        row = result.first()
        if not row:
            return None
        if row.audit_year:
            return int(row.audit_year)
        if row.audit_period_end:
            return row.audit_period_end.year
    except Exception as exc:  # noqa: BLE001
        logger.debug("agenda prefill: project year lookup failed: %s", exc)
    return None


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


async def _prefill_a13_misstatement(db: AsyncSession, project_id: UUID) -> str:
    try:
        mis = await get_workpaper_summary(db, project_id, "misstatement")
        if mis and mis.get("ready"):
            return mis.get("summary_text") or ""
    except Exception as exc:  # noqa: BLE001
        logger.debug("agenda prefill: A13 misstatement failed: %s", exc)
    return ""


async def _prefill_a177_sign_status(db: AsyncSession, project_id: UUID) -> str:
    try:
        from app.models.review_workflow_models import IndependenceSigningTask

        lines: list[str] = []
        for template_code in ("A17-7", "A17-7A"):
            base = (
                IndependenceSigningTask.project_id == project_id,
                IndependenceSigningTask.template_code == template_code,
            )
            total = int(
                (await db.execute(select(func.count()).select_from(IndependenceSigningTask).where(*base))).scalar()
                or 0
            )
            signed = int(
                (
                    await db.execute(
                        select(func.count()).select_from(IndependenceSigningTask).where(
                            *base, IndependenceSigningTask.status == "signed"
                        )
                    )
                ).scalar()
                or 0
            )
            if total:
                lines.append(f"{template_code} 独立性声明：已签署 {signed}/{total} 人")
            else:
                wid = await _get_wp_id(db, project_id, template_code)
                if wid:
                    r = await db.execute(
                        text(
                            """
                            SELECT conclusion FROM checklist_responses
                            WHERE wp_id = :wid AND item_id LIKE '%sign-status%'
                            LIMIT 1
                            """
                        ),
                        {"wid": str(wid)},
                    )
                    row = r.fetchone()
                    if row and row.conclusion:
                        lines.append(f"{template_code} 签署状态：{row.conclusion}")
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        logger.debug("agenda prefill: A17-7 sign status failed: %s", exc)
    return ""


async def _prefill_kam_titles(db: AsyncSession, project_id: UUID) -> str:
    try:
        wp_id = await _get_wp_id(db, project_id, "A17-2-1")
        if not wp_id:
            return ""
        result = await db.execute(
            text(
                """
                SELECT conclusion FROM checklist_responses
                WHERE wp_id = :wp_id AND item_id LIKE 'A17-2-1-KAM%'
                ORDER BY item_id
                """
            ),
            {"wp_id": str(wp_id)},
        )
        titles = [row.conclusion.strip() for row in result.fetchall() if row.conclusion and row.conclusion.strip()]
        if not titles:
            return ""
        return "关键审计事项：" + "；".join(titles)
    except Exception as exc:  # noqa: BLE001
        logger.debug("agenda prefill: KAM titles failed: %s", exc)
    return ""


async def _prefill_b50_risks(db: AsyncSession, project_id: UUID) -> tuple[str, str]:
    """Return (agenda 2 text, agenda 3 text) from B50 risk assessment."""
    try:
        year = await _get_project_year(db, project_id)
        if year is None:
            return "", ""
        from app.services.field_override_service import FieldOverrideService

        svc = FieldOverrideService(db)
        data = await svc.get_batch(project_id, year, scope="risk_assessment")
        if not data:
            return "", ""

        high_lines: list[str] = []
        special_lines: list[str] = []
        for _key, fields in data.items():
            desc = (fields.get("description") or "").strip()
            if not desc:
                continue
            level = (fields.get("risk_level") or "").strip()
            is_special = fields.get("is_special_risk") == "true"
            if is_special:
                special_lines.append(desc)
            elif level in ("高", "high", "High", "HIGH"):
                high_lines.append(desc)

        agenda2 = ""
        if high_lines:
            agenda2 = "计划阶段重大错报风险：" + "；".join(high_lines[:5])
        agenda3 = ""
        if special_lines:
            agenda3 = "特别风险：" + "；".join(special_lines[:5])
        return agenda2, agenda3
    except Exception as exc:  # noqa: BLE001
        logger.debug("agenda prefill: B50 risks failed: %s", exc)
    return "", ""


async def _prefill_a175_placeholder(db: AsyncSession, project_id: UUID) -> str:
    try:
        result = await db.execute(
            text(
                """
                SELECT wp.id FROM working_paper wp
                JOIN wp_index wi ON wi.id = wp.wp_index_id
                WHERE wp.project_id = :pid
                  AND wi.wp_code LIKE 'A17-5%'
                  AND wp.is_deleted = false
                LIMIT 1
                """
            ),
            {"pid": str(project_id)},
        )
        wp_id_val = result.scalar_one_or_none()
        if not wp_id_val:
            return ""
        wp_id = UUID(str(wp_id_val))
        total_r = await db.execute(
            text("SELECT COUNT(*) FROM checklist_responses WHERE wp_id = :wp_id"),
            {"wp_id": str(wp_id)},
        )
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
        total = int(total_r.scalar() or 0)
        if total == 0:
            return "A17-5 完成核对表已关联（尚无 checklist 记录）"
        return f"A17-5 完成核对表：已填写 {filled}/{total} 项"
    except Exception as exc:  # noqa: BLE001
        logger.debug("agenda prefill: A17-5 placeholder failed: %s", exc)
    return ""


async def build_agenda_prefill(db: AsyncSession, project_id: UUID) -> dict[str, str]:
    """Build suggested agenda text for A17-6 items 1..10."""
    agenda = _empty_agenda()
    a175_placeholder = await _prefill_a175_placeholder(db, project_id)
    agenda2, agenda3 = await _prefill_b50_risks(db, project_id)
    agenda["2"] = agenda2
    agenda["3"] = agenda3
    agenda["5"] = await _prefill_a13_misstatement(db, project_id)
    agenda["7"] = await _prefill_a177_sign_status(db, project_id)
    agenda["9"] = await _prefill_kam_titles(db, project_id)

    if a175_placeholder:
        for key in ("1", "4", "6", "8", "10"):
            if not agenda[key]:
                agenda[key] = a175_placeholder
    return agenda
