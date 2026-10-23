"""Task 26 真库采集的 S21 场景体：文档服务器已最终保存 ⇒ room closed 之后 apply 仍能落库。

spec: writeback-followup-issue-closure · R1.5 / D2

═══ 为什么是伴生模块 ═══

`test_task26_oo_to_html_pg.py` 在行数门禁 whitelist 上（基线 3493 +5%），采集体与判据放进去
会顶过门禁。按域内先例（`task26_d1_settlement_world.py`）：采集体住世界模块、由宿主 `_collect`
用闭包门面 `ctx` 调用；判据住 `test_room_close_after_docserver_saved_pg.py`。

═══ 场景在证什么 ═══

status 2 回 0 之后 room 落 `closed`（D1）。关闭之后仍可能有 apply 跑在这一代上：同一次回调里
apply 失败后用户点重试、或后台重驱。修前 `content_mutation._advance_room`（merged ≠ incoming
时 `→ refresh_required`）、`RoomService.settle_client_baseline`（同上）与协调器随后的
`supersede_room` 对 `closed` 都是非法边 ⇒ apply 在提交前最后一步失败。两条分支各取一个世界：

* ``equal``：merged == incoming ⇒ 基线推进那一支；
* ``differs``：current 与 base 分叉 ⇒ merged ≠ incoming ⇒ refresh 那一支。

另记三种不该动的起点（重复关闭 / superseded / recovery_required）的关闭结果。
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import sqlalchemy as sa

from app.services.workpaper_sync.repository import WorkpaperSyncRepository
from app.services.workpaper_sync.rooms import RoomService

__all__ = ["collect_closed_room"]


async def _room_row(ctx: Any, room_id: uuid.UUID) -> dict[str, Any]:
    async with ctx.Session() as s:
        row = (
            await s.execute(
                sa.text(
                    "SELECT state, closed_at, superseded_at, refresh_required_at "
                    "FROM working_paper_oo_room WHERE id = :r"
                ),
                {"r": room_id},
            )
        ).one()
    return {
        "state": str(row.state),
        "closed_at_set": row.closed_at is not None,
        "superseded_at_set": row.superseded_at is not None,
        "refresh_required_at_set": row.refresh_required_at is not None,
    }


async def _close(ctx: Any, room_id: uuid.UUID) -> dict[str, Any]:
    async with ctx.Session() as s:
        try:
            room = await RoomService(WorkpaperSyncRepository(s)).close_after_docserver_saved(
                room_id=room_id
            )
            await s.commit()
            return {"state": str(room.state)}
        except Exception as exc:  # noqa: BLE001 - 形态进快照
            await s.rollback()
            return {"error": ctx.err(exc)}


async def _apply(ctx: Any, world: dict[str, Any]) -> Any:
    async with ctx.Session() as s:
        coord = ctx.coordinator(s, probe=ctx.recording_probe())
        return await coord.apply_durable_incoming(
            operation_id=world["req"]["operation"],
            declared_project_id=ctx.project,
            declared_wp_id=world["entry"]["wp"],
            declared_entry_id=ctx.entry,
            adapter=ctx.json_adapter(),
            contract=ctx.contract,
            actor_id=ctx.user_a,
        )


async def collect_closed_room(ctx: Any) -> dict[str, Any]:
    """S21 采集；`ctx` 是宿主 `_collect` 的闭包门面（见模块 docstring）。"""
    period, total = ctx.period, ctx.total
    out: dict[str, Any] = {}
    branches = {
        "equal": None,
        "differs": {period: "2025 已审", total: Decimal("100")},
    }
    for tag, current_values in branches.items():
        world = await ctx.stage_world(
            f"closed_room_{tag}",
            base_values={period: "2024", total: Decimal("100")},
            current_values=current_values,
            incoming_values={period: "2024", total: Decimal("888")},
        )
        room_id = world["env"]["room"]
        first_close = await _close(ctx, room_id)
        second_close = await _close(ctx, room_id)  # 重发的回调 ⇒ 幂等
        before = await ctx.db_state(world["entry"]["wp"], room_id, world["app"])
        try:
            outcome = (await _apply(ctx, world)).as_dict()
        except Exception as exc:  # noqa: BLE001 - 修前形态：最后一步抛
            outcome = {"raised": ctx.err(exc)}
        after = await ctx.db_state(world["entry"]["wp"], room_id, world["app"])
        out[tag] = {
            "first_close": first_close,
            "second_close": second_close,
            "room_after_close": await _room_row(ctx, room_id),
            "outcome": outcome,
            "before": before,
            "after": after,
        }

    # 不该被关闭抢掉的两种起点：已 superseded（终态）与 recovery_required（只能去 superseded）。
    world = await ctx.stage_world(
        "closed_room_untouched",
        base_values={period: "2024", total: Decimal("100")},
        current_values=None,
        incoming_values={period: "2024", total: Decimal("888")},
    )
    room_id = world["env"]["room"]
    async with ctx.Session() as s:
        await RoomService(WorkpaperSyncRepository(s)).supersede_room(
            room_id=room_id, reason="closed-room-world"
        )
        await s.commit()
    out["superseded"] = {"close": await _close(ctx, room_id), "room": await _room_row(ctx, room_id)}
    world = await ctx.stage_world(
        "closed_room_recovery",
        base_values={period: "2024", total: Decimal("100")},
        current_values=None,
        incoming_values={period: "2024", total: Decimal("888")},
    )
    room_id = world["env"]["room"]
    async with ctx.Session() as s:
        await s.execute(
            sa.text(
                "UPDATE working_paper_oo_room SET state = 'recovery_required', "
                "superseded_at = now() WHERE id = :r"
            ),
            {"r": room_id},
        )
        await s.commit()
    out["recovery_required"] = {
        "close": await _close(ctx, room_id),
        "room": await _room_row(ctx, room_id),
    }
    return out
