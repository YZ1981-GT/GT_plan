"""上年数据来源 —— 报表上期与 PREV 共用的单一来源（spec formula-fetch-and-wp-generation-defect-closure R2.1 / R2.4）。

* 上年项目 :func:`find_prior_project`：显式关联的 ``prior_year_project_id``（未删除）；否则同企业代码 +
  审计年度 = 本年 − 1 + 同报表口径（本项目填了口径时）的项目，**唯一才认**（多个不猜）。
* 上年数据来源 :func:`resolve_prior_source`：同项目有 ``year − 1`` 试算表 → 同项目；否则上年项目且它有
  ``year − 1`` 试算表。取不到时 ``reason`` 写明原因，调用方据此报缺数，不代入 0。

调用方：报表上期 ``report_prior_period``、PREV 两参 / 三参（``formula_ref_preload`` / ``formula_preloader`` /
``prev_wp_field``）。不各写一份查找逻辑。
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PriorProject:
    project_id: uuid.UUID | None
    reason: str = ""


@dataclass(frozen=True)
class PriorSource:
    """取上年数据的项目与年度；``project_id`` 为 ``None`` 时 ``reason`` 是取不到的原因。"""

    project_id: uuid.UUID | None
    year: int
    same_project: bool = False
    reason: str = ""


async def has_trial_balance(db: AsyncSession, project_id: uuid.UUID, year: int) -> bool:
    from app.models.audit_platform_models import TrialBalance

    hit = (await db.execute(sa.select(TrialBalance.id).where(
        TrialBalance.project_id == project_id, TrialBalance.year == year,
        TrialBalance.is_deleted == sa.false()).limit(1))).first()
    return hit is not None


async def find_prior_project(db: AsyncSession, project_id: uuid.UUID, year: int) -> PriorProject:
    """``year`` 是本年审计年度；上年项目的审计年度是 ``year − 1``。"""
    from app.models.core import Project

    proj = (await db.execute(sa.select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if proj is None:
        return PriorProject(None, "本项目不存在")
    explicit = proj.prior_year_project_id
    if explicit:
        alive = (await db.execute(sa.select(Project.id).where(
            Project.id == explicit, Project.is_deleted == sa.false()))).first()
        if alive is not None:
            return PriorProject(explicit)
    code = proj.company_code
    if not code:
        return PriorProject(None, "本项目没有企业代码，找不到上年项目（可在项目上指定上年项目）")
    conds = [Project.company_code == code, Project.audit_year == year - 1,
             Project.is_deleted == sa.false(), Project.id != project_id]
    if proj.report_scope:
        conds.append(Project.report_scope == proj.report_scope)
    ids = (await db.execute(sa.select(Project.id).where(*conds))).scalars().all()
    if len(ids) == 1:
        return PriorProject(ids[0])
    where = f"企业代码 {code}、审计年度 {year - 1}" + (f"、报表口径 {proj.report_scope}" if proj.report_scope else "")
    if not ids:
        return PriorProject(None, f"没有上年项目（{where}）")
    logger.info("上年项目不唯一（%d 个）project=%s", len(ids), project_id)
    return PriorProject(None, f"上年项目不唯一（{where} 的项目有 {len(ids)} 个），请在项目上指定上年项目")


async def resolve_prior_source(db: AsyncSession, project_id: uuid.UUID, year: int) -> PriorSource:
    """上年（``year − 1``）数据从哪个项目取。只读；调用方负责保存点。"""
    prior_year = year - 1
    if await has_trial_balance(db, project_id, prior_year):
        return PriorSource(project_id, prior_year, same_project=True)
    found = await find_prior_project(db, project_id, year)
    if found.project_id is None:
        return PriorSource(None, prior_year, reason=f"本项目没有 {prior_year} 年试算表，{found.reason}")
    if not await has_trial_balance(db, found.project_id, prior_year):
        return PriorSource(None, prior_year, reason=f"上年项目没有 {prior_year} 年试算表")
    return PriorSource(found.project_id, prior_year)
