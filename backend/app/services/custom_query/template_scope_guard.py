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
from typing import Any

from fastapi import HTTPException

from app.deps import require_project_access
from app.models.custom_query_models import CustomQueryTemplate
from app.services.custom_query.template_scope_adapter import (
    NormalizedTemplateScope,
    TemplateScopeAdapter,
    TemplateScopeValidationError,
)
from app.services.custom_query.template_service import template_service

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




async def _assert_template_visible(
    tpl: CustomQueryTemplate, *, current_user: Any, db: Any
) -> None:
    """模板可见性校验，复用 TemplateService 的单一判定（R8.1）。"""
    if not await template_service.is_visible(tpl, user=current_user, db=db):
        raise HTTPException(
            status_code=403, detail={"error_code": "TEMPLATE_NOT_VISIBLE"}
        )


def _template_owner_id(tpl: CustomQueryTemplate) -> Any:
    return getattr(tpl, "creator_id", None) or tpl.created_by
