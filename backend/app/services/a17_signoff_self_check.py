"""A17 签发/归档自检 + 跨底稿联动告警（A13 超重要性、A10-1 未沟通）。"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.a17_independence_drift import check_independence_drift
from app.services.a17_kam_push_service import check_kam_stale
from app.services.a17_partner_summary_service import get_report_date_timeline
from app.services.gate_rules_phase14 import check_misstatement_exceeds_materiality

logger = logging.getLogger(__name__)


async def _wp_map(db: AsyncSession, project_id: UUID) -> dict[str, str]:
    result = await db.execute(
        sa.text(
            """
            -- wp_index 无 wp_id 列；wp_id 须经 working_paper.wp_index_id 反查
            SELECT wi.wp_code, wp.id AS wp_id FROM wp_index wi
            LEFT JOIN working_paper wp ON wp.wp_index_id = wi.id
            WHERE wi.project_id = :pid
              AND (wi.wp_code LIKE 'A17%' OR wi.wp_code IN ('A10-1', 'A13'))
            """
        ),
        {"pid": str(project_id)},
    )
    return {row.wp_code: str(row.wp_id) for row in result.fetchall() if row.wp_id}


async def _load_responses(db: AsyncSession, wp_id: str, prefix: str) -> list:
    result = await db.execute(
        sa.text(
            """
            SELECT item_id, conclusion, remark, wp_ref
            FROM checklist_responses
            WHERE wp_id = :wid AND item_id LIKE :pfx
            """
        ),
        {"wid": wp_id, "pfx": f"{prefix}%"},
    )
    return result.fetchall()


def _is_truthy(val: str | None) -> bool:
    return str(val or "").strip().lower() in {"1", "true", "yes", "y", "是", "不适用"}


def _is_bare_no(conclusion: str | None, remark: str | None) -> bool:
    c = str(conclusion or "").strip()
    is_no = c in {"否", "X/W"} or c.lower() in {"n", "no"}
    return is_no and not str(remark or "").strip()


async def _a101_communicated(db: AsyncSession, wp_id: str | None) -> bool:
    """A10-1：有签署日期视为已完成沟通函签发。"""
    if not wp_id:
        return False
    result = await db.execute(
        sa.text(
            """
            SELECT conclusion, remark FROM checklist_responses
            WHERE wp_id = :wid AND item_id = 'a101-sign-date' LIMIT 1
            """
        ),
        {"wid": wp_id},
    )
    row = result.fetchone()
    if not row:
        return False
    return bool((row.conclusion or row.remark or "").strip())


async def get_cross_alerts(db: AsyncSession, project_id: UUID) -> dict:
    """A13 超重要性 + A10-1 未沟通 联动告警。"""
    wps = await _wp_map(db, project_id)
    alerts: list[dict] = []

    mis = await check_misstatement_exceeds_materiality(str(project_id), db)
    over_materiality = bool(mis)
    if mis:
        alerts.append(
            {
                "id": "a13_over_materiality",
                "severity": "error",
                "title": "未更正错报超过整体重要性",
                "message": mis["message"],
                "action_tab": "A17-1",
                "action_hint": "请复核 A17-1 ch14 意见类型、A17-6 议程#5，并确认已与治理层沟通（A10-1）",
                "links": ["A13", "A17-1", "A17-6", "A10-1"],
            }
        )

    a101_wp = wps.get("A10-1")
    communicated = await _a101_communicated(db, a101_wp)
    if not communicated:
        severity = "error" if over_materiality else "warning"
        alerts.append(
            {
                "id": "a10_not_communicated",
                "severity": severity,
                "title": "A10-1 与治理层沟通函尚未签署",
                "message": (
                    "未填写沟通函签署日期；若存在 KAM/舞弊/超重要性错报，须完成治理层沟通。"
                    if over_materiality
                    else "沟通函签署日期为空。涉及 KAM 或舞弊事项时请先完成 A10-1。"
                ),
                "action_tab": None,
                "action_hint": "打开 A10-1 填写签署日期",
                "links": ["A10-1", "A17-2-1"],
            }
        )
        if over_materiality:
            alerts.append(
                {
                    "id": "a10_required_for_over_materiality",
                    "severity": "error",
                    "title": "超重要性错报须完成治理层沟通",
                    "message": "A13 未更正错报已超重要性，但 A10-1 尚未签署，阻断归档建议。",
                    "action_tab": None,
                    "action_hint": "先完成 A10-1 签署，再回到 A17 Bundle 复核",
                    "links": ["A10-1", "A13"],
                }
            )

    return {
        "project_id": str(project_id),
        "over_materiality": over_materiality,
        "a10_communicated": communicated,
        "alerts": alerts,
    }


async def get_signoff_self_check(db: AsyncSession, project_id: UUID) -> dict:
    """归档/签发前自检清单。"""
    wps = await _wp_map(db, project_id)
    items: list[dict] = []

    # ── A17-1 ──
    a171 = wps.get("A17-1")
    a171_ok = False
    if a171:
        rows = await _load_responses(db, a171, "a171-")
        filled = sum(
            1
            for r in rows
            if (r.conclusion or r.remark or "").strip()
        )
        a171_ok = filled >= 8  # 宽松：至少填了半数章节量级
        items.append(
            {
                "id": "a171_filled",
                "ok": a171_ok,
                "severity": "error" if not a171_ok else "info",
                "label": "A17-1 重大事项概要已实质填写",
                "detail": f"已填 {filled} 项" if a171 else "未创建 A17-1",
                "action_tab": "A17-1",
            }
        )
    else:
        items.append(
            {
                "id": "a171_filled",
                "ok": False,
                "severity": "error",
                "label": "A17-1 重大事项概要已实质填写",
                "detail": "项目中不存在 A17-1",
                "action_tab": "A17-1",
            }
        )

    # ── A17-5 裸「否」──
    a175_codes = [c for c in wps if c.startswith("A17-5-")]
    bare_nos: list[str] = []
    for code in a175_codes:
        result = await db.execute(
            sa.text(
                """
                SELECT item_id, conclusion, remark FROM checklist_responses
                WHERE wp_id = :wid
                """
            ),
            {"wid": wps[code]},
        )
        for r in result.fetchall():
            if _is_bare_no(r.conclusion, r.remark):
                bare_nos.append(f"{code}:{r.item_id}")
    a175_ok = len(bare_nos) == 0
    items.append(
        {
            "id": "a175_no_bare_no",
            "ok": a175_ok,
            "severity": "error" if not a175_ok else "info",
            "label": "A17-5 无「否」无备注裸项",
            "detail": (
                f"{len(bare_nos)} 项「否」缺备注：{', '.join(bare_nos[:5])}"
                if bare_nos
                else ("无 A17-5" if not a175_codes else "通过")
            ),
            "action_tab": "A17-5",
        }
    )

    # ── A17-7 签署 ──
    a177 = wps.get("A17-7") or wps.get("A17-7A")
    a177_ok = False
    if a177:
        result = await db.execute(
            sa.text(
                """
                SELECT conclusion FROM checklist_responses
                WHERE wp_id = :wid AND item_id = 'A17-7-sign-status' LIMIT 1
                """
            ),
            {"wid": a177},
        )
        row = result.fetchone()
        a177_ok = bool(row and row.conclusion == "signed")
    items.append(
        {
            "id": "a177_signed",
            "ok": a177_ok,
            "severity": "error" if not a177_ok else "info",
            "label": "A17-7 独立性已签署",
            "detail": "已签署" if a177_ok else "未签署或不存在 A17-7",
            "action_tab": "A17-7",
        }
    )

    # ── 报告日时间轴 ──
    timeline = await get_report_date_timeline(db, project_id)
    tl_ok = bool(timeline.get("ok"))
    items.append(
        {
            "id": "report_date_timeline",
            "ok": tl_ok,
            "severity": "error" if not tl_ok else "info",
            "label": "总结会/独立性签署日 ≤ 报告日",
            "detail": "；".join(timeline.get("warnings") or []) or "时间轴正常",
            "action_tab": "A17-7",
        }
    )

    # ── KAM stale ──
    kam_wp = wps.get("A17-2-1")
    kam_ok = True
    kam_detail = "无 A17-2-1"
    if kam_wp:
        stale = await check_kam_stale(db, project_id, UUID(kam_wp))
        kam_ok = not bool(stale.get("stale"))
        kam_detail = stale.get("message") or ("一致" if kam_ok else "KAM 过期")
    items.append(
        {
            "id": "kam_fresh",
            "ok": kam_ok,
            "severity": "error" if not kam_ok else "info",
            "label": "KAM 已推送且与报告一致",
            "detail": kam_detail,
            "action_tab": "A17-2-1",
        }
    )

    # ── 独立性漂移 ──
    drift = await check_independence_drift(db, project_id)
    drift_ok = not bool(drift.get("has_drift"))
    items.append(
        {
            "id": "independence_drift",
            "ok": drift_ok,
            "severity": "warning" if not drift_ok else "info",
            "label": "独立性期间与 B3 无未解释漂移",
            "detail": drift.get("message") or "无漂移",
            "action_tab": "A17-7",
        }
    )

    # ── 跨底稿 ──
    cross = await get_cross_alerts(db, project_id)
    for alert in cross["alerts"]:
        items.append(
            {
                "id": alert["id"],
                "ok": False,
                "severity": alert["severity"],
                "label": alert["title"],
                "detail": alert["message"],
                "action_tab": alert.get("action_tab"),
                "links": alert.get("links") or [],
            }
        )

    hard_fail = any(
        (not it["ok"]) and it.get("severity") == "error" for it in items
    )
    ready = not hard_fail and a171_ok and a177_ok and a175_ok and kam_ok and tl_ok

    return {
        "project_id": str(project_id),
        "ready": ready,
        "a17_completed": ready,
        "items": items,
        "cross_alerts": cross["alerts"],
        "over_materiality": cross["over_materiality"],
        "a10_communicated": cross["a10_communicated"],
    }
