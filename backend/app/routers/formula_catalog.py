"""公式目录 + 函数清单路由（spec unified-formula-registry Phase 2/3）。

端点：
- ``GET /api/formula-catalog``          — 本项目有效公式目录（跨 6 域）
- ``GET /api/formula-catalog/stats``    — 按域 / 层级 / 函数的计数摘要
- ``GET /api/formula-functions``        — 已注册函数清单（供前端语法解析器消费）
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User

router = APIRouter(tags=["formula-catalog"])


# ── 公式目录（需项目成员） ────────────────────────────────────────────────────

@router.get("/api/projects/{project_id}/formula-catalog")
async def formula_catalog(
    project_id: uuid.UUID,
    domain: str | None = Query(None, description="逗号分隔域名筛选，如 report,wp"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """本项目有效公式的扁平目录，可按域筛选。"""
    from app.services.formula_catalog import build_catalog

    domains = [d.strip() for d in domain.split(",") if d.strip()] if domain else None
    entries = await build_catalog(db, project_id, domains=domains)
    return {
        "project_id": str(project_id),
        "total": len(entries),
        "entries": [
            {
                "addr_id": e.addr_id,
                "domain": e.domain,
                "slot_key": e.slot_key,
                "formula_text": e.formula_text,
                "layer": e.layer,
                "function_refs": e.function_refs,
                "target_label": e.target_label,
            }
            for e in entries
        ],
    }


@router.get("/api/projects/{project_id}/formula-catalog/stats")
async def formula_catalog_stats(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """按域 / 层级 / 函数的计数摘要。"""
    from app.services.formula_catalog import catalog_stats

    return await catalog_stats(db, project_id)


# ── 函数清单（登录即可） ──────────────────────────────────────────────────────

@router.get("/api/formula-functions")
async def formula_functions(
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """已注册函数清单（供前端语法高亮 / 自动补全消费）。"""
    from app.services.formula_engine import _REGISTRY

    functions = []
    for meta in _REGISTRY.list_all():
        arity = meta.get("arity")
        min_args = 0 if arity is None else (arity if isinstance(arity, int) else min(arity))
        max_args = 99 if arity is None else (arity if isinstance(arity, int) else max(arity))
        functions.append({
            "name": meta["name"],
            "arity": arity,
            "minArgs": min_args,
            "maxArgs": max_args,
            "description": meta.get("description") or "",
            "syntax": meta.get("syntax") or "",
            "category": meta.get("category") or "",
        })
    # WP/PREV 的 arity 在 _REGISTRY 里是单值（2），但实际支持 2~3 参
    _MULTI: dict[str, tuple[int, int]] = {"WP": (2, 3), "PREV": (2, 3), "PRIOR": (2, 3)}
    for fn in functions:
        if fn["name"] in _MULTI:
            fn["minArgs"], fn["maxArgs"] = _MULTI[fn["name"]]
    return {"total": len(functions), "functions": functions}
