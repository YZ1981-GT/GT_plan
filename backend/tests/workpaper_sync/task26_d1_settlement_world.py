"""Task 26 真库采集的 S20 场景体：application 终态 ⇒ request 终结（D1）。

═══ 为什么是伴生模块 ═══

`test_task26_oo_to_html_pg.py` 在行数门禁 whitelist 上（基线 3493 +5%），S20 采集体与 D1
判据放进去会顶过门禁。按域内先例（`aos8_endpoint_world.py`）：采集体住世界模块、由宿主
`_collect` 用**闭包门面** `ctx` 调用（本模块不自己建连接、不建 world）；判据住
`test_task26_d1_request_settlement_pg.py`。

═══ 场景在证什么 ═══

修前全仓没有任何生产代码写 `correlated → terminal`：保存成功后 request 停在 `correlated`，
initiator 主动离开被 in-flight 门恒拒（真库：重药安徽 3 次 applied 全如此，离开 409
`participant_leave_refused_in_flight`）。既有守卫用裸 `UPDATE … SET state='terminal'` 模拟
这一步，于是从未暴露。本场景真走「离开被拒 → apply → 离开放行」，并覆盖只有这里才有的
两种形态：同 application key 折叠进来的 duplicate request（较高 sequence 的第二次保存），
以及仓储侧的另一个终态写入点 `supersede_application`。
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import sqlalchemy as sa

from app.models.workpaper_sync_models import (
    WorkpaperContentApplication,
    WorkpaperForcesaveRequest,
)
from app.services.workpaper_sync.repository import WorkpaperSyncRepository
from app.services.workpaper_sync.request_application import RequestApplicationService
from app.services.workpaper_sync.request_settlement import (
    settle_requests_of_terminal_application,
)
from app.services.workpaper_sync.rooms import RoomService

__all__ = ["collect_settlement"]


async def _room_request_rows(ctx: Any, room_id: uuid.UUID) -> dict[str, dict[str, Any]]:
    async with ctx.Session() as s:
        rows = (
            await s.execute(
                sa.select(WorkpaperForcesaveRequest).where(
                    WorkpaperForcesaveRequest.room_id == room_id
                )
            )
        ).scalars().all()
    return {
        str(r.id): {
            "state": str(r.state),
            "sequence": int(r.request_sequence),
            "finished": r.finished_at is not None,
        }
        for r in rows
    }


async def _try_leave(ctx: Any, env: dict[str, Any]) -> dict[str, Any]:
    async with ctx.Session() as s:
        svc = RoomService(WorkpaperSyncRepository(s))
        try:
            out = await svc.leave_participant(
                room_id=env["room"], participant_id=env["participant"],
                actor_user_id=ctx.user_a, client_reports_dirty=False,
            )
            await s.commit()
            return {"left": True, "already_left": out.already_left}
        except Exception as exc:  # noqa: BLE001 - 拒绝形态进快照
            await s.rollback()
            return {
                "left": False,
                "type": type(exc).__name__,
                "error_code": getattr(exc, "error_code", None),
            }


async def collect_settlement(ctx: Any) -> dict[str, Any]:
    """S20 采集；`ctx` 是宿主 `_collect` 的闭包门面（见模块 docstring）。"""
    period, total = ctx.period, ctx.total
    s20 = await ctx.stage_world(
        "settlement",
        base_values={period: "2024", total: Decimal("100")},
        current_values=None,
        incoming_values={period: "2024", total: Decimal("777")},
    )
    env20 = s20["env"]

    # ① 同一份 incoming 的第二次保存（sequence 2）⇒ 同 key ⇒ direct duplicate。
    req20b = await ctx.accept_request(env20, key="fs-settlement-b")
    async with ctx.Session() as s:
        folded = await RequestApplicationService(WorkpaperSyncRepository(s)).correlate(
            operation_id=req20b["operation"],
            incoming_artifact_id=s20["inc"]["incoming"],
            current_revision=0,
            adapter_id=ctx.entry,
        )
        await s.commit()
    fold = {
        "shape": folded.shape.value,
        "same_application": folded.application.id == s20["app"],
    }
    before = await ctx.db_state(s20["entry"]["wp"], env20["room"], s20["app"])
    requests_before = await _room_request_rows(ctx, env20["room"])
    # ② 内容尚未应用 ⇒ in-flight 门必须仍然拒（修复不得放宽它）。
    leave_before = await _try_leave(ctx, env20)
    async with ctx.Session() as s:
        coord = ctx.coordinator(s, probe=ctx.recording_probe())
        outcome = await coord.apply_durable_incoming(
            operation_id=s20["req"]["operation"],
            declared_project_id=ctx.project,
            declared_wp_id=s20["entry"]["wp"],
            declared_entry_id=ctx.entry,
            adapter=ctx.json_adapter(),
            contract=ctx.contract,
            actor_id=ctx.user_a,
        )
    after = await ctx.db_state(s20["entry"]["wp"], env20["room"], s20["app"])
    requests_after = await _room_request_rows(ctx, env20["room"])
    # 幂等：已结算的 application 再结算一次 ⇒ 零改写、不抛（terminal 的出边为空集，
    # 已终结的 request 不得再走 assert_transition）。
    async with ctx.Session() as s:
        app20 = (
            await s.execute(
                sa.select(WorkpaperContentApplication).where(
                    WorkpaperContentApplication.id == s20["app"]
                )
            )
        ).scalar_one()
        try:
            again = await settle_requests_of_terminal_application(
                WorkpaperSyncRepository(s), app20
            )
            resettle: dict[str, Any] = {"settled": [str(i) for i in again]}
        except Exception as exc:  # noqa: BLE001 - 形态进快照
            resettle = {"error": ctx.err(exc)}
        await s.rollback()
    # ③ 内容已应用 ⇒ 同一 participant 现在必须能离开。
    leave_after = await _try_leave(ctx, env20)

    # ④ 仓储侧终态写入点：较新的 durable snapshot（不同字节 ⇒ 不同 key）supersede 旧
    # application ⇒ 旧 request `superseded`，新 request 仍 `correlated`。
    s20s = await ctx.stage_world(
        "settlement_supersede",
        base_values={period: "2024", total: Decimal("100")},
        current_values=None,
        incoming_values={period: "2024", total: Decimal("555")},
    )
    req_new = await ctx.accept_request(s20s["env"], key="fs-settlement-new")
    inc_new = await ctx.seal_incoming(
        s20s["env"], s20s["entry"], req_new,
        payload=ctx.ooxml(
            projection_values=ctx.carrier_values(
                ctx.projection({period: "2024", total: Decimal("556")})
            )
        ),
    )
    app_new = await ctx.correlate(s20s["env"], s20s["entry"], req_new, inc_new)
    async with ctx.Session() as s:
        await WorkpaperSyncRepository(s).supersede_application(
            old_application_id=s20s["app"], new_application_id=app_new
        )
        await s.commit()
    return {
        "outcome": outcome.as_dict(),
        "fold": fold,
        "origin_request": str(s20["req"]["request"]),
        "folded_request": str(req20b["request"]),
        "before": before,
        "after": after,
        "requests_before": requests_before,
        "requests_after": requests_after,
        "resettle": resettle,
        "leave_before": leave_before,
        "leave_after": leave_after,
        "supersede": {
            "old_request": str(s20s["req"]["request"]),
            "new_request": str(req_new["request"]),
            "requests": await _room_request_rows(ctx, s20s["env"]["room"]),
        },
    }
