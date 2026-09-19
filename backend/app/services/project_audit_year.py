"""全平台统一的项目审计年度解析。

优先级（SQL 与 ORM 对齐）：
1. projects.audit_year（物化列，主来源）
2. audit_period_end 年份
3. audit_period_start 年份
4. wizard_state.basic_info.audit_year
5. 项目名末尾 _YYYY 后缀（如「重药控股安徽有限公司_2025」）
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project

_MIN_YEAR = 2000

# 列表/单字段 SQL 查询（无 ORM 对象时内联使用）
PROJECT_AUDIT_YEAR_SQL = sa.text(
    "SELECT COALESCE("
    "  audit_year, "
    "  EXTRACT(YEAR FROM audit_period_end)::int, "
    "  EXTRACT(YEAR FROM audit_period_start)::int"
    ") FROM projects WHERE id = :pid"
)

PROJECT_AUDIT_YEAR_BIZ_SQL = sa.text(
    "SELECT COALESCE("
    "  audit_year, "
    "  EXTRACT(YEAR FROM audit_period_end)::int, "
    "  EXTRACT(YEAR FROM audit_period_start)::int"
    "), "
    "COALESCE(business_category, 'C') "
    "FROM projects WHERE id = :pid"
)


def _valid_year(value: Any) -> int | None:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if year > _MIN_YEAR else None


def _year_from_date(value: date | datetime | None) -> int | None:
    if value is None:
        return None
    try:
        return _valid_year(value.year)
    except AttributeError:
        return None


def _year_from_name(name: str | None) -> int | None:
    if not name:
        return None
    match = re.search(r"_(\d{4})$", name)
    return _valid_year(match.group(1)) if match else None


def extract_audit_year_from_wizard_state(wizard_state: dict | None) -> int | None:
    """从向导状态 basic_info 提取 audit_year。"""
    if not wizard_state:
        return None
    basic_info = (
        wizard_state.get("steps", {}).get("basic_info", {}).get("data")
        or wizard_state.get("basic_info", {}).get("data")
        or {}
    )
    raw_year = basic_info.get("audit_year") or basic_info.get("year")
    return _valid_year(raw_year)


def resolve_project_audit_year(project: Project) -> int | None:
    """从 ORM Project 解析审计年度（与 PROJECT_AUDIT_YEAR_SQL 对齐，并含命名约定兜底）。"""
    year = _valid_year(project.audit_year)
    if year:
        return year
    year = _year_from_date(project.audit_period_end)
    if year:
        return year
    year = _year_from_date(project.audit_period_start)
    if year:
        return year
    year = extract_audit_year_from_wizard_state(project.wizard_state)
    if year:
        return year
    return _year_from_name(project.name)


async def fetch_project_audit_year(
    db: AsyncSession,
    project_id: UUID | str,
) -> int | None:
    """异步查询项目审计年度（SQL COALESCE 路径）。"""
    row = (await db.execute(PROJECT_AUDIT_YEAR_SQL, {"pid": str(project_id)})).first()
    if not row or row[0] is None:
        return None
    return _valid_year(row[0])
