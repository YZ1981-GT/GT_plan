"""公式推送端点（公式管理「公式推送」面板）。

spec: chain-closure-phase2-formula-push-engine · design §九 · 任务 12 · 需求 1.1 / 1.4 / 2.3

| 方法 | 路径 | 权限 | 作用 |
|---|---|---|---|
| GET  | /rules?wp_code=E1        | readonly | 规则清单 |
| POST | /run                     | edit     | 立即推送（dry_run 试跑，事务回滚） |
| GET  | /latest?year=            | readonly | 最近一次运行 + 状态计数 |
| GET  | /states?year=&state=     | readonly | 目标级状态（当前值 / 公式值 / 差异） |
| POST | /states/adopt            | edit     | 采用公式值 |
| POST | /states/lock             | edit     | 锁定 / 解锁 |

权限依赖一律 ``require_project_access``（项目维度，不只校验登录）；无权 403 由 TestClient 真请求守卫。
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.models.formula_push_models import PUSH_STATES
from app.services.formula_push import engine, panel
from app.services.formula_push.bindings import supported_wp_codes, watched_prefixes
from app.services.formula_push.rules import rules_for

router = APIRouter(prefix="/api/projects/{project_id}/formula-push", tags=["formula-push"])


class RunBody(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    dry_run: bool = False


class AdoptBody(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    addr_ids: list[str] = Field(..., min_length=1, max_length=500)


class LockBody(AdoptBody):
    locked: bool


def _rule_view(rule) -> dict[str, Any]:
    target = rule.target
    return {
        "rule_id": rule.rule_id,
        "wp_code": rule.wp_code,
        "stage": rule.stage,
        "policy": rule.policy,
        "triggers": list(rule.triggers),
        "description": rule.description,
        "formula": rule.source.display_formula,
        "source_kind": rule.source.kind,
        "target": {
            "domain": target.domain,
            "sheet_code": target.sheet_code,
            "item_id": target.item_id,
            "fields": list(target.fields),
            "table": target.table,
            "sections": target.sections,
        },
    }


def _bad_request(exc: engine.PushActionError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/bindings")
async def list_bindings(
    project_id: UUID,
    current_user: User = Depends(require_project_access("readonly")),
):
    """返回公式推送 binding 接入清单；清单本身不依赖项目数据。"""
    codes = supported_wp_codes()
    prefixes = watched_prefixes()
    return {
        "supported_wp_codes": list(codes),
        "bindings": [
            {"wp_code": code, "account_prefixes": list(prefixes.get(code, ())) }
            for code in codes
        ],
    }


@router.get("/rules")
async def list_rules(
    project_id: UUID,
    wp_code: str | None = Query(None, max_length=16),
    current_user: User = Depends(require_project_access("readonly")),
):
    rules = rules_for(engine.load_push_rules(), wp_code=wp_code)
    return {
        "supported_wp_codes": list(supported_wp_codes()),
        "rules": [_rule_view(r) for r in rules],
    }


@router.post("/run")
async def run_push(
    project_id: UUID,
    body: RunBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    try:
        result = await engine.run_and_commit(
            db, project_id=project_id, year=body.year, trigger=engine.MANUAL,
            triggered_by=current_user.id, dry_run=body.dry_run,
        )
    except engine.PushActionError as exc:
        raise _bad_request(exc) from exc
    return {**result.summary(), "items": [i.as_dict() for i in result.items]}


@router.get("/latest")
async def latest(
    project_id: UUID,
    year: int = Query(..., ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    run = await panel.latest_run(db, project_id=project_id, year=year)
    return {
        "run": panel.run_view(run),
        "state_counts": await panel.state_counts(db, project_id=project_id, year=year),
    }


@router.get("/states")
async def states(
    project_id: UUID,
    year: int = Query(..., ge=2000, le=2100),
    state: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    if state is not None and state not in PUSH_STATES:
        raise HTTPException(status_code=400, detail=f"未知状态 {state}（可选：{'、'.join(PUSH_STATES)}）")
    rows = await panel.list_states(db, project_id=project_id, year=year, state=state)
    return {"states": [panel.state_view(r) for r in rows]}


@router.post("/states/adopt")
async def adopt(
    project_id: UUID,
    body: AdoptBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    try:
        result = await panel.adopt(
            db, project_id=project_id, year=body.year, addr_ids=body.addr_ids, user_id=current_user.id,
        )
    except engine.PushActionError as exc:
        raise _bad_request(exc) from exc
    wanted = set(body.addr_ids)
    return {**result.summary(), "items": [i.as_dict() for i in result.items if i.addr_id in wanted]}


@router.post("/states/lock")
async def lock(
    project_id: UUID,
    body: LockBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    try:
        rows = await panel.set_locked(
            db, project_id=project_id, year=body.year, addr_ids=body.addr_ids,
            locked=body.locked, user_id=current_user.id,
        )
        await db.commit()
    except engine.PushActionError as exc:
        await db.rollback()
        raise _bad_request(exc) from exc
    return {"states": [panel.state_view(r) for r in rows]}
