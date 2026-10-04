"""公式管理「公式推送」面板操作：采用公式值 / 锁定 / 查询视图。

spec: chain-closure-phase2-formula-push-engine · 任务 10 / 12（由 engine.py 拆出，行数门禁 ≤800）
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from app.models.formula_push_models import FormulaPushRun, FormulaPushState
from app.services.formula_push.engine import MANUAL, PushActionError, load_push_rules, run_and_commit
from app.services.formula_push.policy import PolicyError, apply_user_action, values_equal
from app.services.formula_push.results import RunResult
from app.services.formula_push.rules import PushRule


def _dedupe(addr_ids: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(a).strip() for a in addr_ids if str(a or "").strip()))


async def _checked_targets(
    db, project_id: UUID, year: int, addr_ids: Iterable[str], *, for_update: bool = False,
) -> tuple[list[str], dict[str, FormulaPushState], dict[str, PushRule]]:
    """面板操作的目标校验：须有推送记录、规则仍在清单、且是可编辑目标。"""
    wanted = _dedupe(addr_ids)
    if not wanted:
        raise PushActionError("请至少选择一个目标")
    stmt = sa.select(FormulaPushState).where(
        FormulaPushState.project_id == project_id,
        FormulaPushState.year == year,
        FormulaPushState.addr_id.in_(wanted),
    )
    if for_update:
        stmt = stmt.with_for_update()
    rows = {r.addr_id: r for r in (await db.execute(stmt)).scalars().all()}
    missing = [a for a in wanted if a not in rows]
    if missing:
        more = "等" if len(missing) > 5 else ""
        raise PushActionError(f"以下目标尚无推送记录：{'、'.join(missing[:5])}{more}")
    rules = {r.rule_id: r for r in load_push_rules()}
    for addr in wanted:
        rule = rules.get(rows[addr].rule_id)
        if rule is None:
            raise PushActionError(f"目标 {addr} 的推送规则 {rows[addr].rule_id} 已不在清单中")
        if rows[addr].domain == "note":
            raise PushActionError(
                f"附注单元格以附注模块中的人工 / 锁定标记为准，请在附注模块中处理：{addr}"
            )
        if rule.policy != "editable":
            raise PushActionError(f"系统值 / 派生值由引擎按公式维护，不能采用或锁定：{addr}")
    return wanted, rows, rules


async def adopt(db, *, project_id: UUID, year: int, addr_ids: Iterable[str], user_id: UUID | None) -> RunResult:
    """采用公式值：以本次**重新算出**的公式值写入并转 auto（不用 last_formula_value —— 它可能已过时）。"""
    wanted, _, _ = await _checked_targets(db, project_id, year, addr_ids)
    return await run_and_commit(
        db, project_id=project_id, year=year, trigger=MANUAL, triggered_by=user_id, force_addr_ids=wanted,
    )


async def set_locked(
    db, *, project_id: UUID, year: int, addr_ids: Iterable[str], locked: bool, user_id: UUID | None,
) -> list[FormulaPushState]:
    """锁定 / 解锁（只改推送状态；解锁后转「待确认」，下次推送重新判定）。只 flush，调用方提交。"""
    wanted, rows, rules = await _checked_targets(db, project_id, year, addr_ids, for_update=True)
    now = datetime.now(timezone.utc)
    action = "lock" if locked else "unlock"
    for addr in wanted:
        row = rows[addr]
        try:
            row.state = apply_user_action(action, policy=rules[row.rule_id].policy, state=row.state)
        except PolicyError as exc:
            raise PushActionError(f"{addr}：{exc}") from exc
        row.updated_by = user_id
        row.updated_at = now
    await db.flush()
    return [rows[a] for a in wanted]


async def latest_run(db, *, project_id: UUID, year: int) -> FormulaPushRun | None:
    return (await db.execute(
        sa.select(FormulaPushRun)
        .where(FormulaPushRun.project_id == project_id, FormulaPushRun.year == year)
        .order_by(FormulaPushRun.started_at.desc(), FormulaPushRun.id.desc())
        .limit(1)
    )).scalar_one_or_none()


async def state_counts(db, *, project_id: UUID, year: int) -> dict[str, int]:
    rows = (await db.execute(
        sa.select(FormulaPushState.state, sa.func.count())
        .where(FormulaPushState.project_id == project_id, FormulaPushState.year == year)
        .group_by(FormulaPushState.state)
    )).all()
    return {str(state): int(n) for state, n in rows}


async def list_states(
    db, *, project_id: UUID, year: int, state: str | None = None,
) -> list[FormulaPushState]:
    stmt = sa.select(FormulaPushState).where(
        FormulaPushState.project_id == project_id, FormulaPushState.year == year,
    )
    if state:
        stmt = stmt.where(FormulaPushState.state == state)
    return list((await db.execute(stmt.order_by(FormulaPushState.addr_id))).scalars().all())


def state_view(row: FormulaPushState) -> dict[str, Any]:
    """面板「待处理差异」一行（当前值 / 公式值 / 状态 / 是否有差异）。"""
    return {
        "addr_id": row.addr_id,
        "rule_id": row.rule_id,
        "domain": row.domain,
        "wp_id": str(row.wp_id) if row.wp_id else None,
        "note_section": row.note_section,
        "state": row.state,
        "current_value": row.current_value,
        "formula_value": row.last_formula_value,
        "last_pushed_value": row.last_pushed_value,
        "differs": not values_equal(row.current_value, row.last_formula_value),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def run_view(row: FormulaPushRun | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "run_id": str(row.id),
        "trigger": row.trigger_source,
        "triggered_by": str(row.triggered_by) if row.triggered_by else None,
        "status": row.status,
        "written_count": row.written_count,
        "unchanged_count": row.unchanged_count,
        "kept_count": row.kept_count,
        "skipped_count": row.skipped_count,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "detail": row.detail or {},
    }
