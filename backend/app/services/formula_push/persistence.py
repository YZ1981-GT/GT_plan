"""公式推送来源信封、运行失败记录与提交后通知（S5 拆分）。"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from app.models.formula_push_models import FormulaPushRun, FormulaPushState
from app.services.formula_push.results import RunResult, _jsonable

logger = logging.getLogger(__name__)
SSE_EVENT = "formula.pushed"


def rule_inputs(rule: Any, collected: Iterable[Any], value: Any) -> list[Any]:
    """优先保留求值器实际 emit；无 emit 的四表/派生规则保存其来源结果。"""
    items = list(collected)
    if items:
        return items
    from app.services.formula_provenance import normalize_input_atom

    kind = {"four_table_leaves": "FOUR_TABLE", "derivation": "DERIVED"}.get(
        rule.source.kind, "FORMULA",
    )
    key = rule.source.name or ",".join(rule.source.slots) or rule.source.expression or rule.rule_id
    return [normalize_input_atom(kind, str(key), value, f"push-rule:{rule.rule_id}")]


async def save_states(ctx: Any, run_id: UUID) -> None:
    """原子 upsert 目标状态、最近计算尝试和实际采用来源。"""
    from app.services.formula_provenance import advance_final_value, build_attempt

    for write in ctx.state_writes:
        row = ctx.states.get(write.addr_id)
        if row is None:
            row = FormulaPushState(
                id=uuid.uuid4(), project_id=ctx.project_id, year=ctx.year,
                addr_id=write.addr_id, rule_id=write.rule_id,
                domain=write.domain, state=write.state,
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
        if write.definition_identity is not None:
            status = "succeeded" if write.formula_value is not None else "skipped"
            attempt = build_attempt(
                domain="push", identity=write.definition_identity, run_id=run_id,
                computed_at=ctx.now, computed_by=ctx.triggered_by,
                calc_version="push:1", inputs=write.inputs,
                calculated_value=write.formula_value if status == "succeeded" else None,
                calculation_status=status,
                error_code=None if status == "succeeded" else "PUSH_TARGET_VALUE_MISSING",
            )
            row.provenance = advance_final_value(
                row.provenance, value_slot="current", value_state=write.state,
                attempt=attempt, calculation_applied=write.calculation_applied,
            ).model_dump(mode="json")
        if write.forced:
            row.updated_by = ctx.triggered_by
    await ctx.db.flush()


async def record_failure(
    db: Any, *, project_id: UUID, year: int, trigger: str,
    triggered_by: UUID | None, error: BaseException,
) -> None:
    """原事务回滚后另记失败 run；记录失败不掩盖原异常。"""
    now = datetime.now(timezone.utc)
    try:
        db.add(FormulaPushRun(
            id=uuid.uuid4(), project_id=project_id, year=year,
            trigger_source=trigger, triggered_by=triggered_by,
            status="failed", started_at=now, finished_at=now,
            detail={"error": f"{type(error).__name__}: {error}"[:2000]},
        ))
        await db.commit()
    except Exception:
        logger.exception("formula_push: 失败运行记录写入失败 project=%s year=%s", project_id, year)
        await db.rollback()


def _broadcast(result: RunResult) -> None:
    try:
        from app.services.event_bus import event_bus
        event_bus.broadcast_raw(SSE_EVENT, result.summary())
    except Exception:
        logger.warning("formula_push: SSE 广播失败 project=%s", result.project_id, exc_info=True)


async def notify_committed(result: RunResult) -> None:
    """提交成功后发 SSE 与附注章节事件；dry-run 不通知。"""
    if result.dry_run or result.run_id is None:
        return
    from app.services.formula_push.note_events import publish_note_sections

    _broadcast(result)
    await publish_note_sections(result.project_id, result.year, result.note_sections, result.run_id)


async def load_states(db: Any, project_id: UUID, year: int) -> dict[str, FormulaPushState]:
    rows = (await db.execute(
        sa.select(FormulaPushState).where(
            FormulaPushState.project_id == project_id,
            FormulaPushState.year == year,
        )
    )).scalars().all()
    return {row.addr_id: row for row in rows}


async def execute_and_commit(
    operation: Any, action_error_type: type[Exception], db: Any, **kwargs: Any,
) -> RunResult:
    """运行公式推送并统一提交、回滚、失败留痕和提交后通知。"""
    dry_run = bool(kwargs.get("dry_run"))
    try:
        result = await operation(db, **kwargs)
        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    except Exception as exc:
        await db.rollback()
        if not dry_run and not isinstance(exc, action_error_type):
            await record_failure(
                db,
                project_id=kwargs["project_id"], year=kwargs["year"],
                trigger=kwargs["trigger"], triggered_by=kwargs.get("triggered_by"),
                error=exc,
            )
        raise
    await notify_committed(result)
    return result
