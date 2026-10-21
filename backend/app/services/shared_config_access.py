"""共享配置模板鉴权（spec formula-global-settings-sync R14.1 / R14.2，design §16.5）。

各配置类型的业务逻辑不动，只补「谁能看、谁能改、谁能引用到哪个项目」：

* 创建：system（事务所）仅 admin；group（集团）需 ``owner_project_id`` 的 edit；personal 登录即可。
* 修改 / 删除：admin；personal 的所有者；group 由所属项目 edit 的成员管理。
* 详情：system / 公开 → 全体；personal → 所有者；group → 与所属项目同一集团根的项目成员；
  ``allowed_project_ids`` 白名单里的项目成员。不可见按不存在（404）。
* 引用到项目 / 查引用历史：目标项目 edit / readonly。
* ``formula_config`` 类型下线（改用公式模板，R14.2；真库 0 条，无迁移）。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import assert_project_permission
from app.models.core import ProjectUser

RETIRED_TYPES = {"formula_config": "公式配置模板已下线，请改用「公式模板」（公式管理中心 → 保存为模板 / 订阅模板）"}
OWNER_TYPES = ("system", "group", "personal")


def is_admin(user) -> bool:
    role = getattr(user, "role", None)
    return str(getattr(role, "value", role) or "") == "admin"


def check_not_retired(config_type: str | None) -> None:
    if config_type in RETIRED_TYPES:
        raise HTTPException(status_code=410, detail=RETIRED_TYPES[config_type])


async def check_create(db: AsyncSession, user, *, owner_type: str, owner_project_id: uuid.UUID | None,
                       config_type: str) -> None:
    check_not_retired(config_type)
    if owner_type not in OWNER_TYPES:
        raise HTTPException(status_code=400, detail="所有者类型须为 system / group / personal")
    if owner_type == "system" and not is_admin(user):
        raise HTTPException(status_code=403, detail="事务所模板只有管理员可以创建")
    if owner_type == "group":
        if owner_project_id is None:
            raise HTTPException(status_code=400, detail="集团模板须指定所属项目")
        await assert_project_permission(db, user, owner_project_id, "edit")


async def _member_projects(db: AsyncSession, user) -> set[uuid.UUID]:
    rows = await db.execute(sa.select(ProjectUser.project_id).where(
        ProjectUser.user_id == user.id, ProjectUser.is_deleted == sa.false()))
    return {r[0] for r in rows.all()}


async def can_view(db: AsyncSession, user, tpl) -> bool:
    if tpl is None or tpl.is_deleted:
        return False
    if is_admin(user) or tpl.owner_type == "system" or tpl.is_public:
        return True
    if tpl.owner_type == "personal":
        return tpl.owner_user_id == user.id
    members = await _member_projects(db, user)
    if tpl.owner_type == "group" and tpl.owner_project_id is not None:
        from app.services.note_content_template_service import resolve_canonical_group_root

        root = await resolve_canonical_group_root(db, tpl.owner_project_id)
        for pid in members:
            if root is not None and await resolve_canonical_group_root(db, pid) == root:
                return True
    allowed = {str(x) for x in (tpl.allowed_project_ids or [])}
    return any(str(pid) in allowed for pid in members)


async def list_visible(db: AsyncSession, user, config_type: str, templates) -> list:
    """按 :func:`can_view` 过滤列表 —— 与详情 / 版本同一口径（R14.1：列表与详情可见性必须一致）。

    下线类型直接空列表（不泄露存在性）。``templates`` 为该 ``config_type`` 的全部未删除模板。
    """
    if config_type in RETIRED_TYPES:
        return []
    out = []
    for tpl in templates:
        if await can_view(db, user, tpl):
            out.append(tpl)
    return out


async def check_manage(db: AsyncSession, user, tpl) -> None:
    if is_admin(user):
        return
    if tpl.owner_type == "personal" and tpl.owner_user_id == user.id:
        return
    if tpl.owner_type == "group" and tpl.owner_project_id is not None:
        await assert_project_permission(db, user, tpl.owner_project_id, "edit")
        return
    raise HTTPException(status_code=403, detail="只有模板所有者或管理员可以修改、删除该模板")
