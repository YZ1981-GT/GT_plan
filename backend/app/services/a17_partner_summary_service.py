"""A17 合伙人/EQCR 一页摘要 + 报告日时间轴。"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.a17_independence_drift import check_independence_drift
from app.services.a17_kam_push_service import check_kam_stale

logger = logging.getLogger(__name__)


async def _wp_map(db: AsyncSession, project_id: UUID) -> dict[str, str]:
    result = await db.execute(
        sa.text(
            """
            -- wp_index 无 wp_id 列；wp_id 须经 working_paper.wp_index_id 反查
            SELECT wi.wp_code, wp.id AS wp_id FROM wp_index wi
            LEFT JOIN working_paper wp ON wp.wp_index_id = wi.id
            WHERE wi.project_id = :pid AND wi.wp_code LIKE 'A17%'
            """
        ),
        {"pid": str(project_id)},
    )
    return {row.wp_code: str(row.wp_id) for row in result.fetchall() if row.wp_id}


async def _response_value(db: AsyncSession, wp_id: str, item_id: str) -> str:
    result = await db.execute(
        sa.text(
            """
            SELECT conclusion, remark FROM checklist_responses
            WHERE wp_id = :wid AND item_id = :iid LIMIT 1
            """
        ),
        {"wid": wp_id, "iid": item_id},
    )
    row = result.fetchone()
    if not row:
        return ""
    return (row.remark or row.conclusion or "").strip()


def _parse_json_date(raw: str) -> str:
    if not raw:
        return ""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return str(data.get("date") or "").strip()
    except Exception:  # noqa: BLE001
        pass
    # plain date-ish
    m = re.search(r"\d{4}-\d{2}-\d{2}", raw)
    return m.group(0) if m else raw[:32]


async def _audit_report_date(db: AsyncSession, project_id: UUID) -> str | None:
    result = await db.execute(
        sa.text(
            """
            SELECT report_date FROM audit_report
            WHERE project_id = :pid AND COALESCE(is_deleted, false) = false
            ORDER BY year DESC NULLS LAST
            LIMIT 1
            """
        ),
        {"pid": str(project_id)},
    )
    val = result.scalar_one_or_none()
    if val is None:
        return None
    if isinstance(val, (date, datetime)):
        return val.date().isoformat() if isinstance(val, datetime) else val.isoformat()
    return str(val)[:10]


async def get_report_date_timeline(db: AsyncSession, project_id: UUID) -> dict:
    """汇总总结会 / 独立性签署 / 审计报告日。"""
    wps = await _wp_map(db, project_id)
    milestones: list[dict] = []

    # Closing meeting
    a176 = wps.get("A17-6")
    meeting = ""
    if a176:
        meeting = await _response_value(db, a176, "a176-meta-meeting_time")
    milestones.append(
        {
            "id": "closing_meeting",
            "label": "总结会",
            "date": (meeting or "")[:16] or None,
            "source": "A17-6",
            "item_id": "a176-meta-meeting_time",
            "ok": bool(meeting),
        }
    )

    # Independence partner sign
    a177 = wps.get("A17-7") or wps.get("A17-7A")
    partner_date = ""
    if a177:
        raw = await _response_value(db, a177, "a177-partner-sign")
        if not raw:
            raw = await _response_value(db, a177, "a177a-partner-sign")
        partner_date = _parse_json_date(raw)
        # fallback sign status
        if not partner_date:
            status = await _response_value(db, a177, "A17-7-sign-status")
            if status == "signed":
                partner_date = "(已签署，日期未填)"
    milestones.append(
        {
            "id": "independence_sign",
            "label": "独立性签署",
            "date": partner_date or None,
            "source": "A17-7",
            "item_id": "a177-partner-sign",
            "ok": bool(partner_date),
        }
    )

    report_date = await _audit_report_date(db, project_id)
    milestones.append(
        {
            "id": "audit_report",
            "label": "审计报告日",
            "date": report_date,
            "source": "audit_report",
            "item_id": None,
            "ok": bool(report_date),
        }
    )

    warnings: list[str] = []
    # Order checks (only when both look like YYYY-MM-DD)
    def _as_date(s: str | None) -> date | None:
        if not s or len(s) < 10:
            return None
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None

    d_meet = _as_date(meeting)
    d_ind = _as_date(partner_date if partner_date and partner_date[0].isdigit() else None)
    d_rep = _as_date(report_date)
    if d_meet and d_rep and d_meet > d_rep:
        warnings.append("总结会日期晚于审计报告日")
    if d_ind and d_rep and d_ind > d_rep:
        warnings.append("独立性签署日晚于审计报告日（通常应 ≤ 报告日）")

    return {
        "milestones": milestones,
        "warnings": warnings,
        "ok": len(warnings) == 0,
    }


async def get_partner_summary(db: AsyncSession, project_id: UUID) -> dict:
    """合伙人/EQCR 一页摘要。"""
    wps = await _wp_map(db, project_id)
    timeline = await get_report_date_timeline(db, project_id)
    drift = await check_independence_drift(db, project_id)

    kam_wp = wps.get("A17-2-1")
    kam_stale = {"stale": False, "message": "无 A17-2-1"}
    kam_count = 0
    if kam_wp:
        kam_stale = await check_kam_stale(db, project_id, UUID(kam_wp))
        r = await db.execute(
            sa.text(
                """
                SELECT COUNT(*) FROM checklist_responses
                WHERE wp_id = :wid AND item_id LIKE 'A17-2-1-KAM%'
                """
            ),
            {"wid": kam_wp},
        )
        kam_count = int(r.scalar_one() or 0)

    # Opinion preview from A17-1 ch14
    opinion = ""
    a171 = wps.get("A17-1")
    if a171:
        for iid in ("a171-ch14-content", "a171-ch14-yn", "A17-1-ch14"):
            opinion = await _response_value(db, a171, iid)
            if opinion:
                break

    # Consultation / disagreement quick flags
    a173 = wps.get("A17-3")
    has_consult = False
    if a173:
        r = await db.execute(
            sa.text(
                """
                SELECT 1 FROM checklist_responses
                WHERE wp_id = :wid AND item_id LIKE 'a173-%'
                  AND ((conclusion IS NOT NULL AND conclusion <> '')
                       OR (remark IS NOT NULL AND TRIM(remark) <> ''))
                LIMIT 1
                """
            ),
            {"wid": a173},
        )
        has_consult = r.fetchone() is not None

    a174 = wps.get("A17-4")
    has_disagreement = False
    disagreement_closed = True
    if a174:
        r = await db.execute(
            sa.text(
                """
                SELECT item_id, conclusion, remark FROM checklist_responses
                WHERE wp_id = :wid AND item_id LIKE 'a174-%'
                """
            ),
            {"wid": a174},
        )
        rows = r.fetchall()
        has_disagreement = any(
            (row.conclusion or row.remark or "").strip() for row in rows
        )
        if has_disagreement:
            disagreement_closed = any(
                row.item_id in ("a174-sec6-conclusion", "a174-sec6")
                and (row.remark or row.conclusion or "").strip()
                for row in rows
            )

    blockers: list[str] = []
    if kam_stale.get("stale"):
        blockers.append("KAM 与审计报告不一致")
    if drift.get("has_drift"):
        blockers.append(drift.get("message") or "独立性期间漂移")
    if has_disagreement and not disagreement_closed:
        blockers.append("A17-4 专业分歧未闭环")
    blockers.extend(timeline.get("warnings") or [])

    return {
        "project_id": str(project_id),
        "opinion_preview": (opinion or "")[:500],
        "kam_count": kam_count,
        "kam_stale": bool(kam_stale.get("stale")),
        "has_consultation": has_consult,
        "has_disagreement": has_disagreement,
        "disagreement_closed": disagreement_closed,
        "independence_drift": bool(drift.get("has_drift")),
        "independence_message": drift.get("message") or "",
        "timeline": timeline,
        "blockers": blockers,
        "ready_hint": "无阻断项" if not blockers else f"{len(blockers)} 项需关注",
    }
