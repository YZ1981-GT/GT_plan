"""受影响项目：按域的作用范围口径批量取项目（design §6 步骤 4）。

作用范围口径与单项目解析一致：
* standard —— ``ReportConfigService.resolve_applicable_standard``（模板类型缺省 soe、范围缺省 standalone，
  不在合法集合时为 enterprise）；
* template_type —— soe / listed（缺省 soe）；
* any —— ``*``。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Iterable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import ProjectStatus
from app.models.core import Project
from app.services.formula_settings.definitions import ANY_SCOPE, get_spec

VALID_STANDARDS = frozenset({"soe_consolidated", "soe_standalone", "listed_consolidated",
                             "listed_standalone", "enterprise"})


@dataclass(frozen=True)
class ProjectInfo:
    id: uuid.UUID
    name: str
    status: str
    scope: str | None

    @property
    def frozen(self) -> bool:
        return self.status == ProjectStatus.archived.value


def scope_of(domain: str, template_type: str | None, report_scope: str | None) -> str | None:
    """项目在 ``domain`` 下的全局作用范围。

    返回 ``None`` 表示该域对此项目不适用（例如 ``consol_note`` 对单体项目）。
    """
    kind = get_spec(domain).scope_kind
    if kind == "any":
        return ANY_SCOPE
    tt = template_type or "soe"
    if kind == "consolidated_template_type":
        if report_scope != "consolidated":
            return None
        return tt if tt in ("soe", "listed") else "soe"
    if kind == "template_type":
        return tt if tt in ("soe", "listed") else "soe"
    standard = f"{tt}_{report_scope or 'standalone'}"
    return standard if standard in VALID_STANDARDS else "enterprise"


def _status(value) -> str:
    return value.value if hasattr(value, "value") else str(value or "")


async def list_projects(db: AsyncSession, domain: str, *, scope: str | None = None,
                        ids: Iterable[uuid.UUID] | None = None) -> list[ProjectInfo]:
    """未删除项目；给 ``scope`` 时只留作用范围相同的（``*`` = 全部），给 ``ids`` 时只取这些。

    ``scope_of`` 返回 ``None`` 的项目（域不适用）始终被跳过。
    """
    q = sa.select(Project.id, Project.name, Project.status, Project.template_type,
                  Project.report_scope).where(Project.is_deleted == sa.false())
    if ids is not None:
        id_list = list(ids)
        if not id_list:
            return []
        q = q.where(Project.id.in_(id_list))
    out: list[ProjectInfo] = []
    for pid, name, status, tt, rs in (await db.execute(q.order_by(Project.name))).all():
        s = scope_of(domain, tt, rs)
        if s is None:
            continue
        info = ProjectInfo(pid, name or "", _status(status), s)
        if scope is None or scope == ANY_SCOPE or info.scope == scope:
            out.append(info)
    return out


async def get_project(db: AsyncSession, domain: str, project_id: uuid.UUID) -> ProjectInfo | None:
    found = await list_projects(db, domain, ids=[project_id])
    return found[0] if found else None
