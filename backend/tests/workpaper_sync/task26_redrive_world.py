"""Task 26 真库采集的 S23 场景体：中断的 apply 被重驱候选查询选中，判据逐条可证伪。

spec: writeback-followup-issue-closure · R3.2

宿主同 `task26_closed_room_world.py`（闭包门面 `ctx`）；判据住 `test_oo_apply_redrive_pg.py`。

故事：回调归组后进程退出，application 停在 apply 中途的某一站。把它的事件与创建时间拨回一小时前，
模拟「很久没人推进」：

1. 候选查询选中它（且是同一个 primary operation）；
2. 刚走过一站（建行事件在一小时前、这一站的事件刚写）⇒ 不选：判据看**最近一次**事件 —— 正在跑的
   apply 每站都写事件；两条都停滞 ⇒ 先选建得更早的那条；
3. 落 `error` / `conflict` ⇒ 不选（一个等用户重试、一个等用户裁决）；
4. 同一协调器入口 attempt=2 从中途那一站（`validating`）续跑到 `applied`（重驱用的就是这个入口）。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import sqlalchemy as sa

from app.models.workpaper_sync_models import WorkpaperContentApplication
from app.services.workpaper_sync.models import ApplicationEventType, ApplicationState
from app.services.workpaper_sync.oo_apply_redrive import find_stuck_application
from app.services.workpaper_sync.repository import WorkpaperSyncRepository

__all__ = ["collect_redrive"]


async def _age(ctx: Any, app_id: Any, *, minutes: int) -> None:
    """把这条 application 的事件与创建时间拨回 `minutes` 分钟前。

    事件表是 append-only（`trg_wpcae_append_only` 拒绝 UPDATE）：只在本临时 schema 里、本事务内
    关掉这一个触发器做时间平移，改完立即恢复。
    """
    async with ctx.Session() as s:
        await s.execute(sa.text(
            "ALTER TABLE working_paper_content_application_event DISABLE TRIGGER trg_wpcae_append_only"
        ))
        await s.execute(
            sa.text(
                "UPDATE working_paper_content_application_event "
                "SET occurred_at = now() - make_interval(mins => :m) WHERE application_id = :a"
            ),
            {"a": app_id, "m": minutes},
        )
        await s.execute(sa.text(
            "ALTER TABLE working_paper_content_application_event ENABLE TRIGGER trg_wpcae_append_only"
        ))
        await s.execute(
            sa.text(
                "UPDATE working_paper_content_application "
                "SET created_at = now() - make_interval(mins => :m) WHERE id = :a"
            ),
            {"a": app_id, "m": minutes},
        )
        await s.commit()


async def _advance(ctx: Any, app_id: Any, to_state: ApplicationState) -> None:
    """真实走一站（先写事件、再改投影，与协调器同序）：apply 跑到一半，这一站的事件刚写。"""
    async with ctx.Session() as s:
        app = (
            await s.execute(
                sa.select(WorkpaperContentApplication)
                .where(WorkpaperContentApplication.id == app_id)
                .with_for_update()
            )
        ).scalar_one()
        await WorkpaperSyncRepository(s).append_application_event(
            application_id=app.id,
            event_type=ApplicationEventType.state_changed,
            origin_request_sequence=int(app.origin_request_sequence),
            effective_request_sequence=int(app.effective_request_sequence),
            from_state=ApplicationState(app.state),
            to_state=to_state,
        )
        app.state = to_state.value
        await s.commit()


async def _find(ctx: Any) -> Any:
    async with ctx.Session() as s:
        found = await find_stuck_application(s)
    return None if found is None else [str(found[0]), str(found[1])]


async def _set_state(ctx: Any, app_id: Any, state: str) -> None:
    """只为证「这两种状态不选」：直接改投影（不走事件 —— 本场景不再 apply 这条）。"""
    async with ctx.Session() as s:
        await s.execute(
            sa.text("UPDATE working_paper_content_application SET state = :st WHERE id = :a"),
            {"a": app_id, "st": state},
        )
        await s.commit()


async def collect_redrive(ctx: Any) -> dict[str, Any]:
    """S23 采集；`ctx` 是宿主 `_collect` 的闭包门面。"""
    period, total = ctx.period, ctx.total
    values = {"base_values": {period: "2024", total: Decimal("100")}, "current_values": None,
              "incoming_values": {period: "2024", total: Decimal("888")}}
    stuck = await ctx.stage_world("redrive_stuck", **values)
    other = await ctx.stage_world("redrive_other", **values)
    out: dict[str, Any] = {
        "ids": {"app": str(stuck["app"]), "op": str(stuck["req"]["operation"]),
                "other_app": str(other["app"]), "other_op": str(other["req"]["operation"])},
    }
    out["fresh"] = await _find(ctx)
    await _age(ctx, stuck["app"], minutes=60)
    out["aged"] = await _find(ctx)
    await _advance(ctx, stuck["app"], ApplicationState.validating)  # 一小时前建行、这一站刚写
    out["touched_again"] = await _find(ctx)

    await _age(ctx, stuck["app"], minutes=60)
    await _age(ctx, other["app"], minutes=90)
    out["oldest_first"] = await _find(ctx)  # 两条都停滞 ⇒ 先重驱建得更早的那条
    await _age(ctx, stuck["app"], minutes=0)
    excluded: dict[str, Any] = {}
    for state in ("error", "conflict"):
        await _set_state(ctx, other["app"], state)
        excluded[state] = await _find(ctx)
    out["excluded"] = excluded

    # apply 中途的每一站停滞都要被选中（另一条已落 conflict，不再是候选）；逐站只改投影
    await _age(ctx, stuck["app"], minutes=60)
    stations: dict[str, Any] = {}
    for station in ("queued", "validating", "extracting", "merging", "rematerializing", "applying"):
        await _set_state(ctx, stuck["app"], station)
        stations[station] = await _find(ctx)
    out["stations"] = stations
    await _set_state(ctx, stuck["app"], "validating")  # 回到真实走到的那一站再重驱
    out["before_redrive"] = await ctx.db_state(stuck["entry"]["wp"], stuck["env"]["room"], stuck["app"])
    async with ctx.Session() as s:
        coord = ctx.coordinator(s, probe=ctx.recording_probe())
        try:
            outcome = await coord.apply_durable_incoming(
                operation_id=stuck["req"]["operation"],
                declared_project_id=ctx.project,
                declared_wp_id=stuck["entry"]["wp"],
                declared_entry_id=ctx.entry,
                adapter=ctx.json_adapter(),
                contract=ctx.contract,
                attempt=2,
            )
            out["redriven"] = outcome.as_dict()
        except Exception as exc:  # noqa: BLE001 - 形态进快照
            out["redriven"] = {"raised": ctx.err(exc)}
    out["after"] = await ctx.db_state(stuck["entry"]["wp"], stuck["env"]["room"], stuck["app"])
    out["after_redrive_find"] = await _find(ctx)
    return out
