"""A21~A25 复核检查项 — 加载 definitions + review-context + auto_na."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project

_logger = logging.getLogger(__name__)

_DEFS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "a21_a25_review_definitions.json"


@lru_cache(maxsize=1)
def _load_definitions() -> dict[str, Any]:
    if not _DEFS_PATH.exists():
        return {"templates": {}, "auto_na_conditions": {}}
    return json.loads(_DEFS_PATH.read_text(encoding="utf-8"))


def _template_key(wp_code: str, enterprise_variant: str | None = None) -> str:
    if enterprise_variant:
        return f"{wp_code}:{enterprise_variant}"
    return wp_code


def resolve_template_key(wp_code: str, is_large_soe: bool, audit_type: str) -> str:
    """A24-1 / A25-1 需按 is_large_soe 选变体 key。"""
    if wp_code in ("A24-1", "A25-1"):
        variant = "large_soe" if is_large_soe else "non_soe"
        key = _template_key(wp_code, variant)
        templates = _load_definitions().get("templates", {})
        if key in templates:
            return key
    return wp_code


def get_template_definition(wp_code: str, is_large_soe: bool = False) -> dict | None:
    templates = _load_definitions().get("templates", {})
    key = resolve_template_key(wp_code, is_large_soe, "financial")
    if key in templates:
        return templates[key]
    return templates.get(wp_code)


def list_all_templates() -> list[dict]:
    return list(_load_definitions().get("templates", {}).values())


async def get_review_context(db: AsyncSession, project_id: UUID) -> dict[str, Any]:
    """推导 auto_na 条件（review-context API 数据源）。"""
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
        return {
            "business_category": "C",
            "audit_type": "financial",
            "is_large_soe": False,
            "has_component_auditor": False,
            "has_it_audit": False,
        }

    bc, audit_type, is_soe = row
    pid = str(project_id)

    has_component = (
        await db.execute(
            sa.text(
                "SELECT EXISTS("
                "SELECT 1 FROM wp_index "
                "WHERE project_id = :pid AND is_deleted = false "
                "AND (wp_code LIKE 'A10-2%' OR wp_code LIKE 'B60%')"
                ")"
            ),
            {"pid": pid},
        )
    ).scalar() or False

    has_it = (
        await db.execute(
            sa.text(
                "SELECT EXISTS("
                "SELECT 1 FROM wp_index "
                "WHERE project_id = :pid AND is_deleted = false "
                "AND wp_code IN ('A27', 'A27-1', 'B60-2-1')"
                ")"
            ),
            {"pid": pid},
        )
    ).scalar() or False

    return {
        "business_category": bc or "C",
        "audit_type": audit_type or "financial",
        "is_large_soe": bool(is_soe),
        "has_component_auditor": bool(has_component),
        "has_it_audit": bool(has_it),
    }


def apply_auto_na(template: dict, context: dict[str, Any]) -> dict:
    """为模板 items 附加 auto_na / disabled 标记。"""
    conditions = _load_definitions().get("auto_na_conditions", {})
    items_out = []
    for item in template.get("items", []):
        cond = item.get("auto_na_condition")
        auto_na = False
        reason = None
        if cond == "no_component_auditor":
            auto_na = not context.get("has_component_auditor", False)
        elif cond == "no_it_audit":
            auto_na = not context.get("has_it_audit", False)
        elif cond == "not_large_soe":
            auto_na = not context.get("is_large_soe", False)
        elif cond == "no_internal_control_audit":
            at = context.get("audit_type", "financial")
            auto_na = at not in ("internal_control", "combined")
        if auto_na and cond in conditions:
            reason = conditions[cond].get("label")
        items_out.append({**item, "auto_na": auto_na, "auto_na_reason": reason})
    return {**template, "items": items_out}


async def get_review_definition_for_wp(
    db: AsyncSession, project_id: UUID, wp_code: str
) -> dict | None:
    # 父码（A21/A22… 无 -N 后缀）解析为当前项目适用的子码（A21-1/A21-2）
    import re as _re
    if _re.match(r"^A2[1-5]$", (wp_code or "").strip().upper()):
        from app.services.a21_a25_version_selector import (
            get_applicable_review_templates,
            resolve_review_wp_code,
        )
        templates = await get_applicable_review_templates(db, project_id)
        resolved = resolve_review_wp_code(templates, wp_code)
        wp_code = resolved.get("wp_code") or wp_code

    ctx = await get_review_context(db, project_id)
    tpl = get_template_definition(wp_code, ctx.get("is_large_soe", False))
    if not tpl:
        return None
    return apply_auto_na(tpl, ctx)


def invalidate_cache() -> None:
    _load_definitions.cache_clear()


def _is_review_item_id(item_id: str) -> bool:
    import re

    return bool(re.match(r"^A2[1-5]-\d-(chk-\d+|record|sign)$", item_id))


def validate_review_conclusion(item_id: str, conclusion: str | None) -> bool:
    if conclusion is None:
        return True
    if item_id.endswith("-sign"):
        return conclusion in ("pass", "reject")
    if item_id.endswith("-record"):
        return conclusion == "done"
    if "-chk-" in item_id:
        return conclusion in ("Y", "N", "NA")
    return True


async def get_responses_map(
    db: AsyncSession, wp_id: UUID
) -> dict[str, dict[str, Any]]:
    r = await db.execute(
        sa.text(
            "SELECT item_id, conclusion, remark FROM checklist_responses WHERE wp_id = :wp_id"
        ),
        {"wp_id": str(wp_id)},
    )
    return {
        row.item_id: {"conclusion": row.conclusion, "remark": row.remark}
        for row in r.fetchall()
    }


async def get_prefill_suggestions(
    db: AsyncSession, project_id: UUID, wp_code: str
) -> dict[str, Any]:
    """plus：底稿完成率等预填建议（非 LLM）。"""
    from app.models.workpaper_models import WorkingPaper

    total_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).where(
        WorkingPaper.project_id == project_id,
        WorkingPaper.is_deleted == sa.false(),
    )
    # wp_file_status 合法值：draft/edit_complete/under_review/revision_required/
    # review_passed/archived（无 completed/reviewed）。"完成"口径取编制完成及以后状态。
    done_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).where(
        WorkingPaper.project_id == project_id,
        WorkingPaper.is_deleted == sa.false(),
        WorkingPaper.status.in_(["edit_complete", "review_passed", "archived"]),
    )
    total = (await db.execute(total_stmt)).scalar() or 0
    done = (await db.execute(done_stmt)).scalar() or 0
    pct = round(done / total * 100) if total else 0

    hints: list[dict[str, Any]] = []
    if pct >= 90:
        hints.append(
            {
                "item_pattern": "-chk-01",
                "suggested": "Y",
                "reason": f"底稿编制完成率 {done}/{total}（{pct}%）",
            }
        )
    if pct >= 80:
        hints.append(
            {
                "item_pattern": "-chk-05",
                "suggested": "Y",
                "reason": "多数底稿已标记完成，可核对索引完整性",
            }
        )

    adj_count = (
        await db.execute(
            sa.text(
                "SELECT COUNT(*) FROM adjustments "
                "WHERE project_id = :pid AND is_deleted = false"
            ),
            {"pid": str(project_id)},
        )
    ).scalar() or 0
    if adj_count == 0 and wp_code.endswith("-1"):
        hints.append(
            {
                "item_pattern": "-chk-04",
                "suggested": "Y",
                "reason": "未发现审计调整分录",
            }
        )

    return {
        "wp_code": wp_code,
        "workpaper_completion_pct": pct,
        "workpaper_done": done,
        "workpaper_total": total,
        "hints": hints,
    }


async def save_review_sign(
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
    wp_code: str,
    action: str,
    comment: str,
    user_id: UUID,
) -> dict[str, Any]:
    """写 {wp_code}-sign 到 checklist_responses。"""
    from datetime import datetime, timezone
    import uuid as uuid_mod

    if action not in ("pass", "reject"):
        raise ValueError("action 必须为 pass 或 reject")

    tpl = await get_review_definition_for_wp(db, project_id, wp_code)
    if not tpl:
        raise ValueError(f"未知复核模板: {wp_code}")

    applicable_items = [
        i for i in tpl.get("items", []) if not i.get("auto_na")
    ]
    r = await get_responses_map(db, wp_id)
    incomplete = [
        i["item_id"]
        for i in applicable_items
        if r.get(i["item_id"], {}).get("conclusion") not in ("Y", "NA")
    ]
    if action == "pass" and incomplete:
        raise ValueError(f"尚有 {len(incomplete)} 项未完成")

    now = datetime.now(timezone.utc).isoformat()
    remark = json.dumps(
        {"signer_id": str(user_id), "signed_at": now, "comment": comment},
        ensure_ascii=False,
    )
    item_id = f"{wp_code}-sign"
    await db.execute(
        sa.text(
            """
            INSERT INTO checklist_responses
                (id, project_id, wp_id, item_id, conclusion, remark, updated_by, created_at, updated_at)
            VALUES (:id, :pid, :wp_id, :item_id, :conclusion, :remark, :uid, :now, :now)
            ON CONFLICT (wp_id, item_id) DO UPDATE SET
                conclusion = EXCLUDED.conclusion,
                remark = EXCLUDED.remark,
                updated_by = EXCLUDED.updated_by,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "id": str(uuid_mod.uuid4()),
            "pid": str(project_id),
            "wp_id": str(wp_id),
            "item_id": item_id,
            "conclusion": action,
            "remark": remark,
            "uid": str(user_id),
            "now": now,
        },
    )
    return {"item_id": item_id, "conclusion": action, "remark": remark}


async def get_review_sign_status_batch(
    db: AsyncSession, project_id: UUID
) -> dict[str, str | None]:
    """批量读取适用子码的 -sign conclusion。"""
    from app.services.a21_a25_version_selector import get_applicable_review_templates

    templates = await get_applicable_review_templates(db, project_id)
    applicable_codes = [t["wp_code"] for t in templates if t.get("applicable")]

    if not applicable_codes:
        return {}

    placeholders = ", ".join(f":c{i}" for i in range(len(applicable_codes)))
    params: dict[str, Any] = {"pid": str(project_id)}
    for i, code in enumerate(applicable_codes):
        params[f"c{i}"] = code

    r = await db.execute(
        sa.text(
            f"""
            SELECT wi.wp_code, cr.conclusion
            FROM checklist_responses cr
            JOIN working_paper wp ON wp.id = cr.wp_id
            JOIN wp_index wi ON wi.id = wp.wp_index_id
            WHERE wp.project_id = :pid
              AND wp.is_deleted = false
              AND wi.wp_code IN ({placeholders})
              AND cr.item_id = wi.wp_code || '-sign'
            """
        ),
        params,
    )
    out: dict[str, str | None] = {c: None for c in applicable_codes}
    for row in r.fetchall():
        out[row.wp_code] = row.conclusion
    return out


_REVIEW_PRESET_PREFIXES = ("A21", "A22", "A23", "A24", "A25")


async def get_review_sign_hints_by_preset(
    db: AsyncSession, project_id: UUID
) -> dict[str, dict[str, Any]]:
    """A17-5 等核对表 preset_index A22/A23… → 读对应子码 -sign 状态。"""
    from app.services.a21_a25_version_selector import get_applicable_review_templates

    statuses = await get_review_sign_status_batch(db, project_id)
    templates = await get_applicable_review_templates(db, project_id)
    by_code = {t["wp_code"]: t for t in templates}

    out: dict[str, dict[str, Any]] = {}
    for prefix in _REVIEW_PRESET_PREFIXES:
        candidates = sorted(c for c in statuses if c.startswith(f"{prefix}-"))
        chosen = None
        for c in candidates:
            if by_code.get(c, {}).get("applicable"):
                chosen = c
                break
        if not chosen and candidates:
            chosen = candidates[0]

        st = statuses.get(chosen) if chosen else None
        tpl_info = by_code.get(chosen or "", {})
        suggested = None
        reason = ""

        if not chosen or not tpl_info.get("applicable", True):
            suggested = "N/A"
            reason = tpl_info.get("reason") or f"{prefix} 对当前项目不适用"
        elif st == "pass":
            suggested = "Y"
            reason = f"{chosen} 复核已签字通过"
        elif st == "reject":
            suggested = "N"
            reason = f"{chosen} 复核已退回"
        else:
            reason = f"{chosen or prefix} 复核尚未签字"

        out[prefix] = {
            "wp_code": chosen,
            "sign_status": st,
            "suggested_conclusion": suggested,
            "reason": reason,
            "applicable": bool(tpl_info.get("applicable")) if chosen else False,
        }
    return out
