"""项目级公式健康度聚合服务（spec: formula-management-deep-optimization · R2）。

六维度指标：
1. push_coverage — 推送覆盖率（D~N 各循环接入率）
2. push_success_rate — 最近一次推送的 written/skipped/conflict 分布
3. formula_config_rate — 报表行有公式 vs 无公式的比例
4. pending_conflicts — FormulaSyncItem status=pending 的计数
5. cross_check_pass_rate — 最近一次 cross_check 的 pass/fail
6. stale_ratio — 过期的报表/附注数量
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def compute_health(
    db: AsyncSession, project_id: uuid.UUID, year: int
) -> dict[str, Any]:
    """聚合六维度公式健康指标。纯只读，不写数据。"""
    return {
        "project_id": str(project_id),
        "year": year,
        "push_coverage": _push_coverage(),
        "push_success_rate": await _last_run_stats(db, project_id, year),
        "formula_config_rate": await _config_coverage(db, project_id, year),
        "pending_conflicts": await _pending_count(db, project_id),
        "cross_check_pass_rate": await _cross_check_stats(db, project_id, year),
        "stale_ratio": await _stale_stats(db, project_id, year),
    }


# ── 维度 1：推送覆盖率（复用 coverage.py 纯函数） ──────────────────────────


def _push_coverage() -> dict[str, Any]:
    """D~N 各循环的接入率。纯函数，不碰 DB。"""
    try:
        from app.services.formula_push.coverage import load_coverage
        return load_coverage()
    except Exception:
        logger.warning("推送覆盖率计算失败", exc_info=True)
        return {"total_registered": 0, "total_codes": 0, "percentage": 0, "cycles": []}


# ── 维度 2：最近一次推送统计 ────────────────────────────────────────────────


async def _last_run_stats(
    db: AsyncSession, project_id: uuid.UUID, year: int
) -> dict[str, Any]:
    """查 formula_push_run 最近一条。"""
    try:
        from app.models.formula_push_models import FormulaPushRun

        row = (await db.execute(
            sa.select(FormulaPushRun)
            .where(
                FormulaPushRun.project_id == project_id,
                FormulaPushRun.year == year,
            )
            .order_by(FormulaPushRun.started_at.desc())
            .limit(1)
        )).scalars().first()
        if row is None:
            return {"has_run": False}
        total = row.written_count + row.unchanged_count + row.kept_count + row.skipped_count
        return {
            "has_run": True,
            "status": row.status,
            "trigger": row.trigger_source,
            "written": row.written_count,
            "unchanged": row.unchanged_count,
            "kept": row.kept_count,
            "skipped": row.skipped_count,
            "total": total,
            "success_rate": round(
                (row.written_count + row.unchanged_count + row.kept_count) / total * 100, 1
            ) if total > 0 else 0,
            "started_at": row.started_at.isoformat() if row.started_at else None,
        }
    except Exception:
        logger.warning("推送统计查询失败", exc_info=True)
        return {"has_run": False, "error": "查询失败"}


# ── 维度 3：公式配置率（报表行有公式比例） ──────────────────────────────────


async def _config_coverage(
    db: AsyncSession, project_id: uuid.UUID, year: int
) -> dict[str, Any]:
    """统计 report_config 中有公式 vs 无公式的行。"""
    try:
        from app.models.report_models import ReportConfig

        total_q = sa.select(sa.func.count()).select_from(ReportConfig).where(
            ReportConfig.project_id == project_id,
            ReportConfig.year == year,
            ReportConfig.is_deleted == sa.false(),
        )
        total = (await db.execute(total_q)).scalar() or 0

        with_formula_q = sa.select(sa.func.count()).select_from(ReportConfig).where(
            ReportConfig.project_id == project_id,
            ReportConfig.year == year,
            ReportConfig.is_deleted == sa.false(),
            ReportConfig.formula.isnot(None),
            ReportConfig.formula != "",
        )
        with_formula = (await db.execute(with_formula_q)).scalar() or 0

        return {
            "total_rows": total,
            "with_formula": with_formula,
            "without_formula": total - with_formula,
            "coverage_rate": round(with_formula / total * 100, 1) if total > 0 else 0,
        }
    except Exception:
        logger.warning("公式配置率查询失败", exc_info=True)
        return {"total_rows": 0, "with_formula": 0, "coverage_rate": 0}


# ── 维度 4：冲突待确认数 ───────────────────────────────────────────────────


async def _pending_count(db: AsyncSession, project_id: uuid.UUID) -> dict[str, Any]:
    """查 FormulaSyncItem status=pending 的计数。"""
    try:
        from app.models.formula_setting_models import FormulaSyncItem

        count_q = sa.select(sa.func.count()).select_from(FormulaSyncItem).where(
            FormulaSyncItem.project_id == project_id,
            FormulaSyncItem.status == "pending",
        )
        count = (await db.execute(count_q)).scalar() or 0
        return {"pending": count}
    except Exception:
        logger.warning("待确认项查询失败", exc_info=True)
        return {"pending": 0}


# ── 维度 5：表间审核通过率 ──────────────────────────────────────────────────


async def _cross_check_stats(
    db: AsyncSession, project_id: uuid.UUID, year: int
) -> dict[str, Any]:
    """查 cross_check_results 最近一批结果。"""
    try:
        from app.models.wp_optimization_models import CrossCheckResult as CrossCheckResultRow

        rows = (await db.execute(
            sa.select(CrossCheckResultRow.status)
            .where(
                CrossCheckResultRow.project_id == project_id,
                CrossCheckResultRow.year == year,
            )
        )).scalars().all()
        if not rows:
            return {"has_results": False, "total": 0}
        passed = sum(1 for s in rows if s == "passed")
        failed = sum(1 for s in rows if s == "failed")
        total = len(rows)
        return {
            "has_results": True,
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
        }
    except Exception:
        logger.warning("表间审核统计查询失败", exc_info=True)
        return {"has_results": False, "total": 0}


# ── 维度 6：过期占比 ───────────────────────────────────────────────────────


async def _stale_stats(
    db: AsyncSession, project_id: uuid.UUID, year: int
) -> dict[str, Any]:
    """统计报表/附注中 is_stale=True 的数量。"""
    try:
        from app.models.report_models import FinancialReport

        report_total = (await db.execute(
            sa.select(sa.func.count()).select_from(FinancialReport).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.is_deleted == sa.false(),
            )
        )).scalar() or 0

        report_stale = (await db.execute(
            sa.select(sa.func.count()).select_from(FinancialReport).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.is_deleted == sa.false(),
                FinancialReport.is_stale == sa.true(),
            )
        )).scalar() or 0

        return {
            "report_total": report_total,
            "report_stale": report_stale,
            "report_stale_rate": round(
                report_stale / report_total * 100, 1
            ) if report_total > 0 else 0,
        }
    except Exception:
        logger.warning("过期统计查询失败", exc_info=True)
        return {"report_total": 0, "report_stale": 0, "report_stale_rate": 0}
