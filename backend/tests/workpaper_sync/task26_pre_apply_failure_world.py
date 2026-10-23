"""Task 26 真库采集的 S22 场景体：回调后 apply 在协调器接手前失败 ⇒ 可见、可重试；已应用过的再来一次 ⇒ 拒绝重放。

spec: writeback-followup-issue-closure · R3.3 / R3.4

宿主 `test_task26_oo_to_html_pg.py` 已贴行数门禁，按域内先例（`task26_closed_room_world.py`）：
采集体住本模块、由宿主 `_collect` 用闭包门面 `ctx` 调用；判据住 `test_callback_apply_failure_pg.py`。

故事：回调已 durable、归组成 application（`queued`）与 operation（`application_bound`），随后注册 /
绑定找不到 adapter（R3.4）。修前只打日志 ⇒ 两者原地不动，前端等到窗口超时也看不到原因。现在：

1. ``record_pre_apply_failure`` 把两者推到 `error`，错误码 / 阶段同时写进事件流与 operation 行；
2. 同一协调器入口重试（attempt=2）从 `error` 走到 `applied`（error 是可重试态，不是死胡同）；
3. 已 `applied` 之后再记录失败 ⇒ 不动（终态没有到 `error` 的边）；
4. 再用同一个 incoming 申请应用 ⇒ 协调器拒绝重放（路由据此回 0，不再 500：R3.3）。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import sqlalchemy as sa

from app.services.workpaper_sync.callback_apply_failure import record_pre_apply_failure

__all__ = ["collect_pre_apply_failure"]


async def _op_row(ctx: Any, op_id: Any) -> dict[str, Any]:
    async with ctx.Session() as s:
        row = (
            await s.execute(
                sa.text(
                    "SELECT state, error_code, error_stage, error_detail "
                    "FROM working_paper_sync_operation WHERE id = :o"
                ),
                {"o": op_id},
            )
        ).one()
        op_ev = (
            await s.execute(
                sa.text(
                    "SELECT to_state, error_code, stage FROM working_paper_sync_operation_event "
                    "WHERE operation_id = :o ORDER BY sequence_no DESC LIMIT 1"
                ),
                {"o": op_id},
            )
        ).one()
    return {
        "state": str(row.state),
        "error_code": row.error_code,
        "error_stage": row.error_stage,
        "error_detail": row.error_detail,
        "last_event": {"to_state": str(op_ev.to_state), "error_code": op_ev.error_code, "stage": op_ev.stage},
    }


async def _app_last_event(ctx: Any, app_id: Any) -> dict[str, Any]:
    async with ctx.Session() as s:
        ev = (
            await s.execute(
                sa.text(
                    "SELECT to_state, error_code FROM working_paper_content_application_event "
                    "WHERE application_id = :a ORDER BY sequence_no DESC LIMIT 1"
                ),
                {"a": app_id},
            )
        ).one()
    return {"to_state": str(ev.to_state), "error_code": ev.error_code}


async def _record(ctx: Any, world: dict[str, Any]) -> Any:
    async with ctx.Session() as s:
        try:
            return await record_pre_apply_failure(
                s,
                application_id=world["app"],
                operation_id=world["req"]["operation"],
                error_code="adapter_unavailable",
                stage="registry",
                detail="RegistryError: entry 没有已注册的 adapter",
            )
        except Exception as exc:  # noqa: BLE001 - 形态进快照
            await s.rollback()
            return {"raised": ctx.err(exc)}


async def _apply(ctx: Any, world: dict[str, Any], *, attempt: int) -> dict[str, Any]:
    async with ctx.Session() as s:
        coord = ctx.coordinator(s, probe=ctx.recording_probe())
        try:
            outcome = await coord.apply_durable_incoming(
                operation_id=world["req"]["operation"],
                declared_project_id=ctx.project,
                declared_wp_id=world["entry"]["wp"],
                declared_entry_id=ctx.entry,
                adapter=ctx.json_adapter(),
                contract=ctx.contract,
                actor_id=ctx.user_a,
                attempt=attempt,
            )
            return outcome.as_dict()
        except Exception as exc:  # noqa: BLE001 - 形态进快照
            await s.rollback()
            return {"raised": ctx.err(exc)}


async def collect_pre_apply_failure(ctx: Any) -> dict[str, Any]:
    """S22 采集；`ctx` 是宿主 `_collect` 的闭包门面（见模块 docstring）。"""
    period, total = ctx.period, ctx.total
    world = await ctx.stage_world(
        "pre_apply_failure",
        base_values={period: "2024", total: Decimal("100")},
        current_values=None,
        incoming_values={period: "2024", total: Decimal("888")},
    )
    wp, room, app = world["entry"]["wp"], world["env"]["room"], world["app"]
    before = await ctx.db_state(wp, room, app)
    recorded = await _record(ctx, world)
    op_after_record = await _op_row(ctx, world["req"]["operation"])
    app_event_after_record = await _app_last_event(ctx, app)
    mid = await ctx.db_state(wp, room, app)
    retried = await _apply(ctx, world, attempt=2)
    after = await ctx.db_state(wp, room, app)
    recorded_again = await _record(ctx, world)
    replay = await _apply(ctx, world, attempt=1)
    final = await ctx.db_state(wp, room, app)
    return {
        "before": before,
        "recorded": recorded,
        "op_after_record": op_after_record,
        "app_event_after_record": app_event_after_record,
        "mid": mid,
        "retried": retried,
        "after": after,
        "recorded_again": recorded_again,
        "replay": replay,
        "final": final,
    }
