"""公式推送状态与失败运行记录的持久化。

从 ``formula_push.engine`` 拆出，保持 engine 聚焦「读值 → 判定 → 写目标」编排。
函数只使用调用方传入的会话；``save_states`` 只 flush，失败运行记录沿用原行为自行 commit/rollback。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from app.models.formula_push_models import FormulaPushRun, FormulaPushState
from app.services.formula_push.results import _jsonable

logger = logging.getLogger(__name__)


async def load_states(
    db: Any, project_id: UUID, year: int,
) -> dict[str, FormulaPushState]:
    """读取项目年度下按地址键控的推送状态。"""
    rows = (
        await db.execute(
            sa.select(FormulaPushState).where(
                FormulaPushState.project_id == project_id,
                FormulaPushState.year == year,
            )
        )
    ).scalars().all()
    return {row.addr_id: row for row in rows}


async def save_states(ctx: Any, run_id: UUID) -> None:
    """upsert ``(project_id, year, addr_id)`` 唯一的推送状态，只 flush。"""
    for write in ctx.state_writes:
        row = ctx.states.get(write.addr_id)
        if row is None:
            row = FormulaPushState(
                id=uuid.uuid4(),
                project_id=ctx.project_id,
                year=ctx.year,
                addr_id=write.addr_id,
                rule_id=write.rule_id,
                domain=write.domain,
                state=write.state,
            )
            ctx.db.add(row)
            ctx.states[write.addr_id] = row
        row.rule_id = write.rule_id
        row.domain = write.domain
        row.wp_id = write.wp_id
        row.note_section = write.note_section
        row.last_formula_value = _jsonable(write.formula_value)
        row.current_value = _jsonable(write.current_after)
        if write.record_pushed:
            row.last_pushed_value = _jsonable(write.formula_value)
        row.state = write.state
        row.last_run_id = run_id
        row.updated_at = ctx.now
        if write.forced:
            row.updated_by = ctx.triggered_by
    await ctx.db.flush()


async def record_failure(
    db: Any,
    *,
    project_id: UUID,
    year: int,
    trigger: str,
    triggered_by: UUID | None,
    error: BaseException,
) -> None:
    """记录失败运行，且不让记录失败掩盖原始异常。"""
    now = datetime.now(timezone.utc)
    try:
        db.add(
            FormulaPushRun(
                id=uuid.uuid4(),
                project_id=project_id,
                year=year,
                trigger_source=trigger,
                triggered_by=triggered_by,
                status="failed",
                started_at=now,
                finished_at=now,
                detail={"error": f"{type(error).__name__}: {error}"[:2000]},
            )
        )
        await db.commit()
    except Exception:  # noqa: BLE001 — 记录失败本身不能掩盖原始异常
        logger.exception(
            "formula_push: 失败运行记录写入失败 project=%s year=%s",
            project_id,
            year,
        )
        await db.rollback()
