"""公式模板可见性与管理权限（R13.2 / R13.9，design §16.3）。

* personal = 所有者；team = 所属项目的未删除成员；group = 所属项目沿 ``parent_project_id`` 上溯到集团根，
  该根及其全部下级项目的成员；firm = 全体登录用户；admin 全部可见。所有者总能看到自己的模板。
* 列表、详情、版本、订阅者四个读接口用同一个 :class:`Viewer`；不可见一律按「不存在」（404，不泄露存在性）。
* 修改 / 删除 / 发布新版本：所有者或 admin。创建：firm 仅 admin；team / group 需所属项目 edit（由路由校验）。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import ProjectUser
from app.models.formula_setting_models import SHARE_SCOPES, FormulaTemplate
from app.services.formula_settings.errors import Forbidden, FormulaSettingError, NotFound

SHARE_LABELS = {"personal": "个人", "team": "项目组", "group": "集团", "firm": "事务所"}
#: 「自定义公式预设」存储模板的域（见 custom_presets；不是可订阅的公式域）
STORE_DOMAIN = "preset"


def is_admin(user) -> bool:
    role = getattr(user, "role", None)
    return str(getattr(role, "value", role) or "") == "admin"


async def _group_root(db: AsyncSession, project_id: uuid.UUID | None, cache: dict) -> uuid.UUID | None:
    if project_id is None:
        return None
    if project_id not in cache:
        from app.services.note_content_template_service import resolve_canonical_group_root

        cache[project_id] = await resolve_canonical_group_root(db, project_id)
    return cache[project_id]


@dataclass
class Viewer:
    """一次请求内的可见性判定（成员项目与集团根只查一次）。"""

    user: object
    member_projects: set[uuid.UUID] = field(default_factory=set)
    member_roots: set[uuid.UUID] = field(default_factory=set)
    roots: dict = field(default_factory=dict)

    @property
    def admin(self) -> bool:
        return is_admin(self.user)

    @classmethod
    async def load(cls, db: AsyncSession, user) -> "Viewer":
        v = cls(user)
        if v.admin:
            return v
        rows = await db.execute(sa.select(ProjectUser.project_id).where(
            ProjectUser.user_id == user.id, ProjectUser.is_deleted == sa.false()))
        v.member_projects = {r[0] for r in rows.all()}
        for pid in v.member_projects:
            root = await _group_root(db, pid, v.roots)
            if root is not None:
                v.member_roots.add(root)
        return v

    async def can_view(self, db: AsyncSession, tpl: FormulaTemplate) -> bool:
        if tpl.is_deleted or (STORE_DOMAIN in (tpl.domains or []) and not self.admin):
            return False  # 「自定义公式预设」存储模板不对外（只经预设库端点读写）
        if self.admin or tpl.owner_user_id == self.user.id or tpl.share_scope == "firm":
            return True
        if tpl.share_scope == "team":
            return tpl.owner_project_id in self.member_projects
        if tpl.share_scope == "group":
            root = await _group_root(db, tpl.owner_project_id, self.roots)
            return root is not None and root in self.member_roots
        return False

    def can_manage(self, tpl: FormulaTemplate) -> bool:
        return self.admin or tpl.owner_user_id == self.user.id


async def get_visible(db: AsyncSession, viewer: Viewer, template_id: uuid.UUID) -> FormulaTemplate:
    tpl = await db.get(FormulaTemplate, template_id)
    if tpl is None or not await viewer.can_view(db, tpl):
        raise NotFound("公式模板不存在或无权查看")
    return tpl


async def get_managed(db: AsyncSession, viewer: Viewer, template_id: uuid.UUID) -> FormulaTemplate:
    tpl = await get_visible(db, viewer, template_id)
    if not viewer.can_manage(tpl):
        raise Forbidden("只有模板所有者或管理员可以修改该模板")
    return tpl


async def list_visible(db: AsyncSession, viewer: Viewer, *, domain: str | None = None,
                       scope: str | None = None) -> list[FormulaTemplate]:
    q = sa.select(FormulaTemplate).where(FormulaTemplate.is_deleted == sa.false())
    if scope:
        q = q.where(FormulaTemplate.applicable_scope.in_([scope, ""]))
    rows = (await db.execute(q.order_by(FormulaTemplate.updated_at.desc()))).scalars().all()
    out = [t for t in rows if STORE_DOMAIN not in (t.domains or []) and (domain is None or domain in (t.domains or []))]
    return [t for t in out if await viewer.can_view(db, t)]


def check_share_scope(share_scope: str, owner_project_id: uuid.UUID | None, *, admin: bool) -> None:
    """共享范围的结构性校验（项目 edit 权限由路由按 ``owner_project_id`` 校验）。"""
    if share_scope not in SHARE_SCOPES:
        raise FormulaSettingError(f"共享范围须为 {' / '.join(SHARE_LABELS[s] for s in SHARE_SCOPES)}")
    if share_scope == "firm" and not admin:
        raise Forbidden("事务所模板只有管理员可以创建或设置")
    if share_scope in ("team", "group") and owner_project_id is None:
        raise FormulaSettingError(f"{SHARE_LABELS[share_scope]}模板须指定所属项目")
