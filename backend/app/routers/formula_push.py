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
    wp_codes: list[str] | None = Field(None, max_length=50)


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
    if body.wp_codes is not None:
        cleaned = [c.strip() for c in body.wp_codes if c and c.strip()]
        if not cleaned:
            raise HTTPException(status_code=400, detail="wp_codes 不能为空列表（省略该参数表示全量推送）")
        body.wp_codes = cleaned
    try:
        result = await engine.run_and_commit(
            db, project_id=project_id, year=body.year, trigger=engine.MANUAL,
            triggered_by=current_user.id, dry_run=body.dry_run,
            codes=body.wp_codes,
        )
    except engine.PushActionError as exc:
        raise _bad_request(exc) from exc
    return {**result.summary(), "items": [i.as_dict() for i in result.items]}


@router.get("/latest")
async def latest(
    project_id: UUID,
    year: int = Query(..., ge=2000, le=2100),
    wp_code: str | None = Query(None, max_length=16),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    run = await panel.latest_run(db, project_id=project_id, year=year, wp_code=wp_code)
    return {
        "run": panel.run_view(run, wp_code=wp_code),
        "state_counts": await panel.state_counts(db, project_id=project_id, year=year, wp_code=wp_code),
    }


@router.get("/states")
async def states(
    project_id: UUID,
    year: int = Query(..., ge=2000, le=2100),
    state: str | None = Query(None),
    wp_code: str | None = Query(None, max_length=16),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    if state is not None and state not in PUSH_STATES:
        raise HTTPException(status_code=400, detail=f"未知状态 {state}（可选：{'、'.join(PUSH_STATES)}）")
    rows = await panel.list_states(db, project_id=project_id, year=year, state=state, wp_code=wp_code)
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


# ── 运行历史与逐项明细（按 run 批次筛选 skip/failed）──────────────


@router.get("/runs")
async def list_runs(
    project_id: UUID,
    year: int = Query(..., ge=2000, le=2100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """返回公式推送运行历史列表（最近优先）。"""
    runs = await panel.list_runs(db, project_id=project_id, year=year, limit=limit, offset=offset)
    return {
        "runs": [panel.run_view(r) for r in runs],
        "total": await panel.count_runs(db, project_id=project_id, year=year),
    }


@router.get("/runs/{run_id}/items")
async def run_items(
    project_id: UUID,
    run_id: UUID,
    outcome: str | None = Query(None, description="过滤 outcome: written/unchanged/kept/skipped/conflict/failed"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """按 run_id 返回逐项推送明细，可按 outcome 筛选 skip/failed 等。"""
    run = await panel.get_run(db, project_id=project_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行记录不存在或不属于该项目")
    items = (run.detail or {}).get("items", [])
    if outcome:
        items = [i for i in items if isinstance(i, dict) and i.get("outcome") == outcome]
    return {
        "run_id": str(run.id),
        "status": run.status,
        "items": items,
        "total": len(items),
    }

# ── 全局覆盖率端点（无需项目权限） ────────────────────────────────────────
# spec: formula-management-ux-improvements · B 批 · Task B1

import json
from pathlib import Path

_COVERAGE_PATH = Path(__file__).resolve().parents[2] / "data" / "formula_push_coverage.json"

#: 各循环不需要推送的原因说明（A/B/C/S 循环不产出数值回写试算表）
_NOT_NEEDED_REASONS: dict[str, str] = {
    "A": "报表/调整类底稿不涉及数值回写试算表",
    "B": "控制了解/计划类底稿，审计程序不产出数值",
    "C": "控制测试底稿只记录测试结论，不涉及科目金额",
    "S": "专项底稿按项目自定义，不走统一推送通道",
}

#: 各循环的总底稿编码数（D~N 实质性循环有明确底稿，A/B/C/S 按类型标注）
_CYCLE_TOTAL_CODES: dict[str, int] = {
    "D": 7,   # D1~D7
    "E": 1,   # E1
    "F": 5,   # F1~F5
    "G": 14,  # G1~G14
    "H": 10,  # H1~H10
    "I": 6,   # I1~I6
    "J": 2,   # J1~J2
    "K": 13,  # K1~K13
    "L": 8,   # L1~L8
    "M": 10,  # M1~M10
    "N": 5,   # N1~N5
}

_CYCLE_LABELS: dict[str, str] = {
    "A": "A 报表/调整", "B": "B 控制了解", "C": "C 控制测试",
    "D": "D 销售收入", "E": "E 货币资金", "F": "F 采购存货",
    "G": "G 投资", "H": "H 固定资产", "I": "I 无形资产",
    "J": "J 职工薪酬", "K": "K 管理", "L": "L 筹资",
    "M": "M 股东权益", "N": "N 税费", "S": "S 专项",
}

global_router = APIRouter(prefix="/api/formula-push", tags=["formula-push"])


@global_router.get("/coverage")
async def push_coverage():
    """返回推送覆盖率概览（按循环分组，静态数据无需鉴权）。"""
    try:
        data = json.loads(_COVERAGE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"registered_codes": []}

    registered = set(data.get("registered_codes", []))
    total_registered = len(registered)

    # 按循环分组
    cycles = []
    total_all = 0
    for letter in "ABCDEFGHIJKLMNS":
        reason = _NOT_NEEDED_REASONS.get(letter)
        total = _CYCLE_TOTAL_CODES.get(letter, 0)
        connected = sum(1 for c in registered if c.startswith(letter))

        if reason:
            # 不需推送的循环
            cycles.append({
                "cycle": letter,
                "label": _CYCLE_LABELS.get(letter, letter),
                "connected": 0,
                "total": 0,
                "percentage": 100,
                "not_needed": True,
                "reason": reason,
            })
        elif total > 0:
            total_all += total
            cycles.append({
                "cycle": letter,
                "label": _CYCLE_LABELS.get(letter, letter),
                "connected": connected,
                "total": total,
                "percentage": round(connected / total * 100) if total else 0,
                "not_needed": False,
                "reason": None,
            })

    return {
        "total_registered": total_registered,
        "total_codes": total_all,
        "percentage": round(total_registered / total_all * 100) if total_all else 0,
        "cycles": cycles,
    }
