"""A17-7 vs B3 独立性期间字段漂移检测."""

from __future__ import annotations

import logging
import re
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_PERIOD_KEYS = (
    "business_start",
    "business_end",
    "report_start",
    "report_end",
)

_PERIOD_SUFFIXES = {
    "period-business-start": "business_start",
    "period-business-end": "business_end",
    "period-report-start": "report_start",
    "period-report-end": "report_end",
}

_B3_PERIOD_LIKE = (
    "%period%",
    "%start%",
    "%end%",
    "%业务期间%",
    "%财务报告%",
)


def _normalize_period_value(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"\s+", "", text)
    text = text.replace("/", "-").replace(".", "-")
    return text


def _map_item_id_to_period_key(item_id: str) -> str | None:
    lowered = item_id.lower()
    for suffix, key in _PERIOD_SUFFIXES.items():
        if suffix in lowered:
            return key
    return None


def _period_dict_to_signature(periods: dict[str, str | None]) -> str | None:
    parts: list[str] = []
    for key in _PERIOD_KEYS:
        val = _normalize_period_value(periods.get(key))
        if val:
            parts.append(f"{key}:{val}")
    if not parts:
        return None
    return "|".join(parts)


async def _get_wp_id(db: AsyncSession, project_id: UUID, wp_code: str) -> str | None:
    result = await db.execute(
        sa.text(
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
    return str(val) if val else None


async def _load_a177_periods(db: AsyncSession, project_id: UUID) -> dict[str, str | None]:
    periods: dict[str, str | None] = {k: None for k in _PERIOD_KEYS}
    for code in ("A17-7", "A17-7A"):
        wp_id = await _get_wp_id(db, project_id, code)
        if not wp_id:
            continue
        result = await db.execute(
            sa.text(
                """
                SELECT item_id, conclusion, remark
                FROM checklist_responses
                WHERE wp_id = :wp_id
                  AND (
                    item_id LIKE '%period-business-start%'
                    OR item_id LIKE '%period-business-end%'
                    OR item_id LIKE '%period-report-start%'
                    OR item_id LIKE '%period-report-end%'
                  )
                """
            ),
            {"wp_id": wp_id},
        )
        for row in result.fetchall():
            key = _map_item_id_to_period_key(row.item_id)
            if not key or periods.get(key):
                continue
            value = (row.remark or row.conclusion or "").strip()
            if value:
                periods[key] = value
    return periods


async def _load_b3_periods(db: AsyncSession, project_id: UUID) -> dict[str, str | None]:
    periods: dict[str, str | None] = {k: None for k in _PERIOD_KEYS}
    wp_id = await _get_wp_id(db, project_id, "B3")
    if not wp_id:
        return periods

    like_clauses = " OR ".join(f"item_id LIKE :p{i}" for i in range(len(_B3_PERIOD_LIKE)))
    params: dict[str, str] = {"wp_id": wp_id}
    for i, pattern in enumerate(_B3_PERIOD_LIKE):
        params[f"p{i}"] = pattern

    result = await db.execute(
        sa.text(
            f"""
            SELECT item_id, conclusion, remark
            FROM checklist_responses
            WHERE wp_id = :wp_id
              AND ({like_clauses}
                   OR conclusion LIKE '%期间%'
                   OR remark LIKE '%期间%'
                   OR conclusion LIKE '%财务报告%'
                   OR remark LIKE '%财务报告%')
            """
        ),
        params,
    )

    for row in result.fetchall():
        key = _map_item_id_to_period_key(row.item_id)
        value = (row.remark or row.conclusion or "").strip()
        if not value:
            continue
        if key and not periods.get(key):
            periods[key] = value
            continue
        # Pragmatic fallback: stuff unstructured period text into business range
        if not periods["business_start"] and not periods["business_end"]:
            if "业务" in row.item_id or "业务" in value:
                periods["business_start"] = value
            elif "报告" in row.item_id or "报告" in value:
                periods["report_start"] = value

    return periods


async def check_independence_drift(db: AsyncSession, project_id: UUID) -> dict:
    """Compare A17-7/A17-7A period fields with B3 period-like responses."""
    a177 = await _load_a177_periods(db, project_id)
    b3 = await _load_b3_periods(db, project_id)

    a177_sig = _period_dict_to_signature(a177)
    b3_sig = _period_dict_to_signature(b3)

    if not a177_sig and not b3_sig:
        return {
            "has_drift": False,
            "message": "A17-7 与 B3 均无可用期间数据，跳过漂移检测",
            "a177": a177,
            "b3": b3,
        }
    if not a177_sig:
        return {
            "has_drift": False,
            "message": "A17-7 期间字段未填写，数据不足",
            "a177": a177,
            "b3": b3,
        }
    if not b3_sig:
        return {
            "has_drift": False,
            "message": "B3 期间相关字段未填写，数据不足",
            "a177": a177,
            "b3": b3,
        }

    if a177_sig != b3_sig:
        return {
            "has_drift": True,
            "message": "A17-7 与 B3 期间字段不一致，请核对业务期间与财务报告期间",
            "a177": a177,
            "b3": b3,
        }

    return {
        "has_drift": False,
        "message": "A17-7 与 B3 期间字段一致",
        "a177": a177,
        "b3": b3,
    }


async def import_b3_periods_to_a177(
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
    user_id: UUID,
    overwrite: bool = False,
) -> dict:
    """将 B3 期间字段写入指定 A17-7/A17-7A 底稿。

    Returns:
        {imported: int, skipped: int, b3: dict, a177_before: dict, message: str}
    """
    from datetime import datetime, timezone

    b3 = await _load_b3_periods(db, project_id)
    a177_before = await _load_a177_periods(db, project_id)

    if not any(b3.values()):
        return {
            "imported": 0,
            "skipped": 0,
            "b3": b3,
            "a177_before": a177_before,
            "message": "B3 无可用期间数据，无法导入",
        }

    # Detect prefix from existing responses or default a177-
    result = await db.execute(
        sa.text(
            """
            SELECT item_id FROM checklist_responses
            WHERE wp_id = :wid AND item_id LIKE '%period-business%'
            LIMIT 1
            """
        ),
        {"wid": str(wp_id)},
    )
    sample = result.scalar_one_or_none()
    if sample and str(sample).startswith("a177a-"):
        prefix = "a177a-"
    else:
        prefix = "a177-"

    field_map = {
        "business_start": f"{prefix}period-business-start",
        "business_end": f"{prefix}period-business-end",
        "report_start": f"{prefix}period-report-start",
        "report_end": f"{prefix}period-report-end",
    }

    now = datetime.now(timezone.utc)
    imported = 0
    skipped = 0
    for key, item_id in field_map.items():
        value = (b3.get(key) or "").strip()
        if not value:
            skipped += 1
            continue
        existing = (a177_before.get(key) or "").strip()
        if existing and not overwrite:
            skipped += 1
            continue
        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses
                    (project_id, wp_id, item_id, conclusion, remark, updated_by, created_at, updated_at)
                VALUES (:pid, :wp_id, :item_id, NULL, :remark, :uid, :now, :now)
                ON CONFLICT (wp_id, item_id) DO UPDATE SET
                    remark = EXCLUDED.remark,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "pid": str(project_id),
                "wp_id": str(wp_id),
                "item_id": item_id,
                "remark": value,
                "uid": str(user_id),
                "now": now,
            },
        )
        imported += 1

    await db.flush()
    return {
        "imported": imported,
        "skipped": skipped,
        "b3": b3,
        "a177_before": a177_before,
        "message": f"已从 B3 导入 {imported} 个期间字段" + (f"（跳过 {skipped}）" if skipped else ""),
    }
