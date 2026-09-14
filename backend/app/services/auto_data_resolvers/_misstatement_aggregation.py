"""A13 错报评价自动聚合 Resolver.

聚合 UnadjustedMisstatement 表数据，计算汇总指标，
查询 B15 重要性水平进行状态分类，持久化到 A13 底稿 parsed_data。

Usage:
    result = await resolve_auto_data_source(db, project_id, year, "a13_misstatement_summary")
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    Materiality,
    MisstatementType,
    UnadjustedMisstatement,
)
from app.models.workpaper_models import WorkingPaper, WpIndex

from . import auto_resolver

_logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：重要性状态分类
# ═══════════════════════════════════════════════════════════════════════════════


def classify_materiality_status(
    cumulative: Decimal,
    pm: Decimal | None,
    te: Decimal | None,
    sat: Decimal | None,
) -> str:
    """根据累计未更正错报与重要性水平阈值进行三色分类。

    Returns:
        "green"        — cumulative < SAT
        "yellow"       — SAT ≤ cumulative < PM
        "red"          — cumulative ≥ PM
        "undetermined" — PM 为 None 或 0
    """
    if pm is None or pm == 0:
        return "undetermined"
    # SAT 缺失时按 0 处理（所有金额都超过 SAT）
    effective_sat = sat if sat is not None and sat > 0 else Decimal("0")
    if cumulative < effective_sat:
        return "green"
    elif cumulative < pm:
        return "yellow"
    else:
        return "red"


# ═══════════════════════════════════════════════════════════════════════════════
# 聚合计算核心
# ═══════════════════════════════════════════════════════════════════════════════


def compute_aggregation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """从错报记录列表计算聚合指标（纯函数，便于测试）。

    每条 row 需含: misstatement_type, misstatement_amount, prior_year_status,
                   is_fraud (bool, 来自 A13-4 标记)

    排除 reversed 条目的统计：total_count, total_amount, by_type
    """
    total_count = 0
    total_amount = Decimal("0")
    by_type: dict[str, dict[str, Any]] = {
        "factual": {"count": 0, "amount": Decimal("0")},
        "judgmental": {"count": 0, "amount": Decimal("0")},
        "projected": {"count": 0, "amount": Decimal("0")},
    }
    fraud_count = 0
    net_effect = Decimal("0")
    continuing_count = 0
    continuing_amount = Decimal("0")
    reversed_count = 0
    reversed_amount = Decimal("0")
    new_count = 0
    new_amount = Decimal("0")

    for row in rows:
        amount = Decimal(str(row["misstatement_amount"]))
        status = row.get("prior_year_status", "new")
        mtype = row["misstatement_type"]
        is_fraud = row.get("is_fraud", False)

        # net_effect 包含所有记录（含 reversed，按会计方向取净额）
        net_effect += amount

        if status == "reversed":
            reversed_count += 1
            reversed_amount += amount
            continue

        # 非 reversed 记录计入 total
        total_count += 1
        total_amount += amount

        # by_type 分组
        type_key = mtype if isinstance(mtype, str) else mtype.value
        if type_key in by_type:
            by_type[type_key]["count"] += 1
            by_type[type_key]["amount"] += amount

        # fraud 统计
        if is_fraud:
            fraud_count += 1

        # prior_year 分组
        if status == "continuing":
            continuing_count += 1
            continuing_amount += amount
        elif status == "new":
            new_count += 1
            new_amount += amount

    cumulative_total = continuing_amount + new_amount

    return {
        "total_count": total_count,
        "total_amount": total_amount,
        "by_type": {
            "factual": {
                "count": by_type["factual"]["count"],
                "amount": by_type["factual"]["amount"],
            },
            "judgmental": {
                "count": by_type["judgmental"]["count"],
                "amount": by_type["judgmental"]["amount"],
            },
            "projected": {
                "count": by_type["projected"]["count"],
                "amount": by_type["projected"]["amount"],
            },
        },
        "fraud_count": fraud_count,
        "net_effect": net_effect,
        "prior_year": {
            "continuing_count": continuing_count,
            "continuing_amount": continuing_amount,
            "reversed_count": reversed_count,
            "reversed_amount": reversed_amount,
        },
        "current_year": {
            "new_count": new_count,
            "new_amount": new_amount,
        },
        "cumulative_total": cumulative_total,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DB 查询辅助
# ═══════════════════════════════════════════════════════════════════════════════


async def _fetch_misstatements(
    db: AsyncSession, project_id: UUID, year: int
) -> list[dict[str, Any]]:
    """查询项目年度的所有未删除错报记录。"""
    tbl = UnadjustedMisstatement.__table__
    q = sa.select(
        tbl.c.misstatement_type,
        tbl.c.misstatement_amount,
        tbl.c.prior_year_status,
        tbl.c.is_carried_forward,
    ).where(
        tbl.c.project_id == project_id,
        tbl.c.year == year,
        tbl.c.is_deleted == sa.false(),
    )
    result = await db.execute(q)
    rows = []
    for r in result.fetchall():
        rows.append({
            "misstatement_type": r.misstatement_type,
            "misstatement_amount": r.misstatement_amount,
            "prior_year_status": r.prior_year_status or "new",
            "is_fraud": False,  # TODO: 后续从 A13-4 sheet 标记读取
        })
    return rows


async def _fetch_materiality(
    db: AsyncSession, project_id: UUID, year: int
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """查询 B15 重要性水平，返回 (PM, TE, SAT)。"""
    q = sa.select(Materiality).where(
        Materiality.project_id == project_id,
        Materiality.year == year,
        Materiality.is_deleted == sa.false(),
    )
    result = await db.execute(q)
    mat = result.scalar_one_or_none()
    if mat is None:
        return None, None, None
    return (
        mat.overall_materiality,
        mat.performance_materiality,
        mat.trivial_threshold,
    )


async def _persist_summary(
    db: AsyncSession, project_id: UUID, year: int, summary: dict[str, Any]
) -> bool:
    """将聚合结果写入 A13 底稿的 parsed_data.html_data['summary']。

    Returns:
        True 写入成功，False 写入失败
    """
    # 查找 A13 主底稿 (wp_code = 'A13' 或 'A13-1')
    wp_idx = WpIndex.__table__
    wp_tbl = WorkingPaper.__table__

    q = (
        sa.select(wp_tbl.c.id, wp_tbl.c.parsed_data)
        .select_from(wp_tbl.join(wp_idx, wp_tbl.c.wp_index_id == wp_idx.c.id))
        .where(
            wp_idx.c.project_id == project_id,
            wp_idx.c.wp_code.in_(["A13", "A13-1"]),
            wp_idx.c.is_deleted == sa.false(),
            wp_tbl.c.is_deleted == sa.false(),
        )
        .limit(1)
    )
    result = await db.execute(q)
    row = result.first()
    if row is None:
        _logger.warning(
            "A13 workpaper not found for project=%s year=%s, skip persist",
            project_id, year,
        )
        return False

    wp_id = row.id
    parsed_data = row.parsed_data or {}
    html_data = parsed_data.get("html_data", {})
    html_data["summary"] = summary
    parsed_data["html_data"] = html_data

    update_q = (
        sa.update(wp_tbl)
        .where(wp_tbl.c.id == wp_id)
        .values(parsed_data=parsed_data, updated_at=sa.func.now())
    )
    await db.execute(update_q)
    await db.flush()
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 格式化输出
# ═══════════════════════════════════════════════════════════════════════════════


def _serialize_summary(
    agg: dict[str, Any],
    pm: Decimal | None,
    te: Decimal | None,
    sat: Decimal | None,
    fraud_count: int,
) -> dict[str, Any]:
    """将聚合结果格式化为 a13-summary-v1 JSON schema。"""
    cumulative = agg["cumulative_total"]
    status = classify_materiality_status(cumulative, pm, te, sat)
    fraud_flag = fraud_count > 0
    ratio = float(cumulative / pm) if pm and pm > 0 else 0.0

    def _d(v: Decimal) -> float:
        return float(v)

    return {
        "_format": "a13-summary-v1",
        "_aggregated_at": datetime.now(timezone.utc).isoformat(),
        "total_count": agg["total_count"],
        "total_amount": _d(agg["total_amount"]),
        "by_type": {
            "factual": {
                "count": agg["by_type"]["factual"]["count"],
                "amount": _d(agg["by_type"]["factual"]["amount"]),
            },
            "judgmental": {
                "count": agg["by_type"]["judgmental"]["count"],
                "amount": _d(agg["by_type"]["judgmental"]["amount"]),
            },
            "projected": {
                "count": agg["by_type"]["projected"]["count"],
                "amount": _d(agg["by_type"]["projected"]["amount"]),
            },
        },
        "fraud_count": fraud_count,
        "net_effect": _d(agg["net_effect"]),
        "prior_year": {
            "continuing_count": agg["prior_year"]["continuing_count"],
            "continuing_amount": _d(agg["prior_year"]["continuing_amount"]),
            "reversed_count": agg["prior_year"]["reversed_count"],
            "reversed_amount": _d(agg["prior_year"]["reversed_amount"]),
        },
        "current_year": {
            "new_count": agg["current_year"]["new_count"],
            "new_amount": _d(agg["current_year"]["new_amount"]),
        },
        "cumulative_total": _d(cumulative),
        "materiality": {
            "pm": _d(pm) if pm is not None else None,
            "te": _d(te) if te is not None else None,
            "sat": _d(sat) if sat is not None else None,
            "ratio": round(ratio, 4),
            "status": status,
            "fraud_flag": fraud_flag,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 注册 Resolver
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("a13_misstatement_summary")
async def _resolve_a13_summary(
    db: AsyncSession, project_id: UUID, year: int, **kw: Any
) -> dict[str, Any]:
    """A13 错报评价聚合 resolver：查询、计算、分类、持久化。"""
    # 1) 查询错报记录
    rows = await _fetch_misstatements(db, project_id, year)

    # 2) 聚合计算
    agg = compute_aggregation(rows)

    # 3) 查询 B15 重要性水平
    pm, te, sat = await _fetch_materiality(db, project_id, year)

    # 4) 格式化输出
    summary = _serialize_summary(agg, pm, te, sat, agg["fraud_count"])

    # 5) 持久化（retry 1 次）
    persisted = False
    for attempt in range(2):
        try:
            persisted = await _persist_summary(db, project_id, year, summary)
            if persisted:
                break
        except Exception as e:
            if attempt == 0:
                _logger.warning(
                    "A13 summary persist attempt 1 failed, retrying: %s", e
                )
            else:
                _logger.error(
                    "A13 summary persist failed after retry [project=%s year=%s]: %s",
                    project_id, year, e, exc_info=True,
                )

    # 6) 返回 summary（供调用者使用，无论是否持久化成功）
    summary["_persisted"] = persisted
    summary["summary"] = (
        f"未更正错报合计 {agg['total_count']} 笔, "
        f"累计 {float(agg['cumulative_total']):,.2f} 元, "
        f"状态: {summary['materiality']['status']}"
    )
    return summary
