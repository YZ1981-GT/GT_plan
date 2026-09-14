"""A21~A25 复核模板版本选择器 — 类比 a17_5_version_selector."""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services.business_category_service import get_category_prefix
from app.services.review_checklist_service import list_all_templates

_logger = logging.getLogger(__name__)


def _determine_applicability(
    business_category: str | None,
    audit_type: str | None,
    is_large_soe: bool,
) -> list[dict]:
    """纯逻辑：返回各子码 applicable / mandatory / reason。"""
    prefix = get_category_prefix(business_category or "")
    at = (audit_type or "financial").lower()
    results: list[dict] = []

    filtered: list[dict] = []
    for tpl in list_all_templates():
        variant = tpl.get("enterprise_variant")
        if variant == "large_soe" and not is_large_soe:
            continue
        if variant == "non_soe" and is_large_soe:
            continue
        filtered.append(tpl)

    for tpl in filtered:
        code = tpl.get("wp_code") or ""
        role = tpl.get("role") or ""
        tpl_audit = (tpl.get("audit_type") or "financial").lower()
        cats = tpl.get("applicable_categories") or ["A", "B", "C"]
        applicable = prefix in cats
        mandatory = False
        reason = ""

        if tpl_audit == "financial":
            if at not in ("financial", "combined"):
                applicable = False
                reason = "仅财报/整合审计适用"
        elif tpl_audit == "internal_control":
            if at not in ("internal_control", "combined"):
                applicable = False
                reason = "仅内控/整合审计适用"

        if role in ("quality_reviewer", "eqcr") and prefix not in ("A", "B"):
            applicable = False
            reason = reason or "A/B 类项目适用"

        if applicable and role == "field_lead":
            mandatory = True

        results.append(
            {
                "wp_code": code,
                "title": tpl.get("filename") or code,
                "role": role,
                "role_label": tpl.get("role_label") or role,
                "audit_type": tpl_audit,
                "audit_type_label": tpl.get("audit_type_label") or tpl_audit,
                "applicable": applicable,
                "mandatory": mandatory,
                "reason": reason,
            }
        )

    return results


async def get_applicable_review_templates(
    db: AsyncSession,
    project_id: UUID,
) -> list[dict]:
    row = (
        await db.execute(
            sa.select(
                Project.business_category,
                Project.audit_type,
                Project.is_large_soe,
            ).where(Project.id == project_id, Project.is_deleted == sa.false())
        )
    ).first()
    if not row:
        _logger.warning("get_applicable_review_templates: project %s not found", project_id)
        return _determine_applicability(None, "financial", False)

    bc, audit_type, is_soe = row
    return _determine_applicability(bc, audit_type, bool(is_soe))


def pick_applicable_wp_code(
    role_prefix: str,
    audit_type: str,
    is_large_soe: bool,
    templates: list[dict],
) -> str | None:
    """按角色前缀（A21）与 audit_type 选 -1/-2 子码。"""
    suffix = "-1" if audit_type in ("financial", "combined") else "-2"
    if audit_type == "combined":
        suffix = "-1"
    candidate = f"{role_prefix}{suffix}"
    by_code = {t["wp_code"]: t for t in templates}
    if candidate in by_code and by_code[candidate].get("applicable"):
        return candidate
    alt = f"{role_prefix}-1" if suffix == "-2" else f"{role_prefix}-2"
    if alt in by_code and by_code[alt].get("applicable"):
        return alt
    return None


def resolve_review_wp_code(templates: list[dict], ref: str) -> dict:
    """将程序表 ref_index（A21 或 A21-1）解析为适用子码 + 元数据。"""
    import re

    ref = (ref or "").strip().upper()
    by_code = {t["wp_code"]: t for t in templates}

    if re.match(r"^A2[1-5]-\d$", ref) and ref in by_code:
        t = by_code[ref]
        return {
            "wp_code": ref,
            "applicable": bool(t.get("applicable")),
            "mandatory": bool(t.get("mandatory")),
            "reason": t.get("reason") or "",
        }

    parent_match = re.match(r"^(A2[1-5])", ref)
    if not parent_match:
        return {"wp_code": ref, "applicable": False, "mandatory": False, "reason": "非复核索引"}

    parent = parent_match.group(1)
    candidates = sorted(
        (t for t in templates if t["wp_code"].startswith(f"{parent}-")),
        key=lambda x: x["wp_code"],
    )
    for c in candidates:
        if c.get("applicable"):
            return {
                "wp_code": c["wp_code"],
                "applicable": True,
                "mandatory": bool(c.get("mandatory")),
                "reason": c.get("reason") or "",
            }
    if candidates:
        c = candidates[0]
        return {
            "wp_code": c["wp_code"],
            "applicable": False,
            "mandatory": False,
            "reason": c.get("reason") or f"{parent} 对当前项目不适用",
        }
    return {
        "wp_code": f"{parent}-1",
        "applicable": False,
        "mandatory": False,
        "reason": f"未找到 {parent} 模板",
    }
