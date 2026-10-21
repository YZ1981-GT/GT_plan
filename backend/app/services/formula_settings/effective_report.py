"""报表域有效定义解析（R1.1 / R1.2，design §5）。

有效配置 = 准则行（全局）逐行用本项目行（``project:{id}``）的公式字段覆盖；本项目独有行追加。
结构字段（行名 / 缩进 / 合计行 / 父行）取准则行，避免项目副本保留旧行名。

返回的是**未挂到会话的**新 ``ReportConfig`` 实例（字段拷贝），调用方只读，不得 flush。
"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import FinancialReportType, ReportConfig

FORMULA_FIELDS = ("formula", "aje_formula", "rje_formula", "formula_category",
                  "formula_description", "formula_source")
_TYPE_ORDER = {t: i for i, t in enumerate(FinancialReportType)}
_COPY_FIELDS = (
    "id", "report_type", "row_number", "row_code", "row_name", "indent_level", "formula",
    "formula_category", "formula_description", "formula_source", "applicable_standard",
    "is_total_row", "parent_row_code", "is_deleted", "aje_formula", "rje_formula", "is_stale",
    "formula_version", "base_version", "base_definition", "pinned", "base_origin",
    "base_template_id", "created_at", "updated_at", "updated_by",
)


def project_standard(project_id: UUID) -> str:
    return f"project:{project_id}"


def _copy(row: ReportConfig) -> ReportConfig:
    return ReportConfig(**{f: getattr(row, f, None) for f in _COPY_FIELDS})


def _sort_key(row: ReportConfig) -> tuple[int, int, str]:
    return (_TYPE_ORDER.get(row.report_type, 99), row.row_number or 0, row.row_code or "")


async def load_effective_report_configs(
    db: AsyncSession,
    *,
    standard: str,
    project_id: UUID | None,
    report_type: FinancialReportType | None = None,
) -> list[ReportConfig]:
    """准则行 ⊕ 本项目行 → 有效配置（按报表类型、行号排序）。

    ``project_id`` 为空或 ``standard`` 本身就是项目口径时，只返回该口径的行（旧行为）。
    """
    def _q(std: str):
        q = sa.select(ReportConfig).where(
            ReportConfig.applicable_standard == std, ReportConfig.is_deleted == sa.false()
        )
        if report_type is not None:
            q = q.where(ReportConfig.report_type == report_type)
        return q

    base_rows = list((await db.execute(_q(standard))).scalars().all())
    if project_id is None or standard.startswith("project:"):
        return sorted(base_rows, key=_sort_key)
    project_rows = list((await db.execute(_q(project_standard(project_id)))).scalars().all())
    if not project_rows:
        return sorted(base_rows, key=_sort_key)
    merged: dict[tuple, ReportConfig] = {(r.report_type, r.row_code): r for r in base_rows}
    for p in project_rows:
        key = (p.report_type, p.row_code)
        g = merged.get(key)
        if g is None:
            merged[key] = p  # 本项目独有行
            continue
        eff = _copy(g)
        for f in FORMULA_FIELDS:
            setattr(eff, f, getattr(p, f, None))
        eff.id = p.id
        eff.applicable_standard = p.applicable_standard
        eff.base_origin = p.base_origin
        eff.pinned = p.pinned
        merged[key] = eff
    return sorted(merged.values(), key=_sort_key)


def group_by_type(rows: list[ReportConfig]) -> dict[FinancialReportType, list[ReportConfig]]:
    out: dict[FinancialReportType, list[ReportConfig]] = {}
    for r in rows:
        out.setdefault(r.report_type, []).append(r)
    return out
