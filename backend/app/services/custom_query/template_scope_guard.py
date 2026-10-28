"""模板作用域治理：写入期 scope 归一 + 分享目标逐项目鉴权（服务层）。

从 ``routers/custom_query.py`` 抽出 —— scope 归一与授权属服务层职责，router 只该
调用。纯 helper（无端点），由 `custom_query` re-export 供契约测试直调与 monkeypatch。

与 ``TemplateScopeAdapter`` 的分工：adapter 是**无依赖的纯归一**（scope 别名、项目
ID 排序去重），本模块在其上叠加**写入期约束**（team 必须有 config 锚点）与**授权**
（逐项目 edit 鉴权）。

_Requirements: 8.1, 8.2, 8.3, 8.5
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from app.deps import PERMISSION_HIERARCHY, require_project_access
from app.models.base import PermissionLevel, ProjectStatus
from app.models.core import Project, ProjectUser
from app.models.custom_query_models import CustomQueryTemplate
from app.services.custom_query.template_scope_adapter import (
    NormalizedTemplateScope,
    TemplateScopeAdapter,
    TemplateScopeValidationError,
)
from app.services.custom_query.template_service import (
    ERR_CODE_TEMPLATE_NOT_VISIBLE,
    TEMPLATE_NOT_VISIBLE_MESSAGE,
    template_service,
)

logger = logging.getLogger(__name__)

def _normalize_template_scope(
    scope: Any, shared_project_ids: Any, config: Any
) -> "NormalizedTemplateScope":
    """归一写入侧的 scope 与分享目标（R8.1 / R8.2）。

    比 `TemplateScopeAdapter.normalize` 多一条**写入期**约束：``team`` 必须在
    ``config.project_id`` 有显式锚点。改造前 team 的锚点靠 ``shared_project_ids``
    推断，导致「分享给哪些项目」与「属于哪个团队」两个语义共用一列 —— 改了分享
    列就悄悄改了团队归属。
    """
    cfg = config if isinstance(config, dict) else {}
    config_project_id = cfg.get("project_id")
    try:
        normalized = TemplateScopeAdapter.normalize(
            scope, shared_project_ids, config_project_id=config_project_id
        )
    except TemplateScopeValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "TEMPLATE_SCOPE_INVALID", "message": str(exc)},
        )

    if normalized.scope == "team" and not config_project_id:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "TEMPLATE_SCOPE_INVALID",
                "message": "团队模板必须在 config.project_id 指定团队项目锚点",
            },
        )
    return normalized


#: 达到「edit」的成员级别（与 ``deps.assert_project_permission`` 比的是同一张级别表）
_SHAREABLE_LEVELS: tuple[PermissionLevel, ...] = tuple(
    PermissionLevel(name) for name, rank in PERMISSION_HIERARCHY.items() if rank >= PERMISSION_HIERARCHY["edit"]
)


async def template_share_target_ids(db: Any, user: Any) -> list[str]:
    """本人可作为「指定项目共享」目标的项目（advanced-query-linkage-closure AQ-39，R9.1 页面版与弹窗 💾 三档）。

    与保存 / 更新时对每个分享目标做的 ``require_project_access("edit")``（``deps.assert_project_permission``）同一口径：
    已归档项目对任何人都不可编辑（423）⇒ 不列；admin 跳过成员判定 ⇒ 其余项目全列；其他身份 = 本项目未删成员行的级别
    达到 edit（系统角色 partner / manager 不因角色放行，与门禁一致）。已删项目不列（界面项目下拉不含它们，分享给回收站里
    的项目也没有意义）。返回项目 id 文本，按文本排序；前端据此决定三档是否可选，后端保存时仍逐项目鉴权。
    """
    stmt = select(Project.id).where(Project.is_deleted == False, Project.status != ProjectStatus.archived)  # noqa: E712
    role = getattr(getattr(user, "role", None), "value", None)
    if role != "admin":
        stmt = stmt.join(ProjectUser, ProjectUser.project_id == Project.id).where(
            ProjectUser.user_id == user.id,
            ProjectUser.is_deleted == False,  # noqa: E712
            ProjectUser.permission_level.in_(_SHAREABLE_LEVELS),
        )
    return sorted({str(pid) for pid in (await db.execute(stmt)).scalars().all()})


def _template_not_visible() -> HTTPException:
    """读取 / 执行 / 修改不可见模板：403 ``TEMPLATE_NOT_VISIBLE``「无权访问该模板」（advanced-query-linkage-closure R9.2）。"""
    return HTTPException(
        status_code=403,
        detail={"error_code": ERR_CODE_TEMPLATE_NOT_VISIBLE, "message": TEMPLATE_NOT_VISIBLE_MESSAGE},
    )


async def _load_template(db: Any, template_id: Any) -> CustomQueryTemplate:
    """按路径参数取模板：标识非法 400 ``INVALID_TEMPLATE_ID``，不存在 404 ``TEMPLATE_NOT_FOUND``。"""
    try:
        tpl_uuid = uuid.UUID(str(template_id))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400, detail={"error_code": "INVALID_TEMPLATE_ID", "message": "模板标识非法"}
        ) from None
    tpl = await db.get(CustomQueryTemplate, tpl_uuid)
    # 已软删（在回收站里）的模板对详情 / 更新 / 删除 / 执行一律 404，恢复只走回收站（R9.5）
    if tpl is None or getattr(tpl, "is_deleted", False):
        raise HTTPException(
            status_code=404, detail={"error_code": "TEMPLATE_NOT_FOUND", "message": "模板不存在或已删除"}
        )
    return tpl


async def _assert_template_visible(
    tpl: CustomQueryTemplate, *, current_user: Any, db: Any
) -> None:
    """模板可见性校验，复用 TemplateService 的单一判定（R8.1）。"""
    if not await template_service.is_visible(tpl, user=current_user, db=db):
        raise _template_not_visible()


def _template_owner_id(tpl: CustomQueryTemplate) -> Any:
    return getattr(tpl, "creator_id", None) or tpl.created_by
