"""Task 25 真库采集的阶段 13：当前代际的 room 不可复用（spec d2-online-edit-platform-closure R5/R6）。

拆分自 `test_task25_materialize_coordinator_pg.py` 的 `_collect()`（宿主在行数门禁 whitelist 上：
基线 2682 +5% = 2816）。采集体原样迁出：宿主把它在 `_collect()` 里的闭包经 ctx 传入，这里按**原名**
取回 ⇒ 下面的采集体与迁出前逐字相同（只少一级缩进）。判据住 `test_task25_room_generation_reuse_pg.py`。

13a 终态 room + 内容未改 ⇒ materialize 自己换代（同 content version、revision 不变）
13b 终态 room + 内容已改 ⇒ commit 直接落在新代际（不先落死代再换）
13c 非终态拒绝（refresh-required）⇒ 不换代、409 透出

必须排在阶段 12 之后：本阶段逐个把当前代际的 room 作废。
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa

if TYPE_CHECKING:
    from app.services.workpaper_sync.adapters.base import Projection


async def collect_retired_generation_cases(ctx: Any) -> None:
    """写 `ctx.snap["retired"]` 的三个场景；单场景失败经 `ctx.phase_failed` 落 harness_errors。"""
    from app.services.workpaper_sync import materialize_coordinator as MC
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.rooms import RoomService

    # 宿主 `_collect()` 的闭包，按原名取回（见模块 docstring）。
    Session, wp, ENTRY, snap = ctx.Session, ctx.wp, ctx.entry, ctx.snap  # noqa: N806
    _pointers, _flush, _coordinator, _request = ctx.pointers, ctx.flush, ctx.coordinator, ctx.request
    _projection, _phase_failed = ctx.projection, ctx.phase_failed
    _JsonCarrierAdapter, _HarnessError = ctx.json_adapter, ctx.harness_error  # noqa: N806

    async def _room_at_pointer() -> tuple[uuid.UUID, int]:
        ptr = await _pointers()
        async with Session() as s:
            rid = (
                await s.execute(
                    sa.text(
                        "SELECT id FROM working_paper_oo_room WHERE wp_id = :w "
                        "AND entry_id = :e AND generation = :g"
                    ),
                    {"w": wp, "e": ENTRY, "g": ptr["current_generation"]},
                )
            ).scalar_one_or_none()
        if rid is None:
            raise _HarnessError(
                f"gen {ptr['current_generation']} 没有 room —— 阶段 13 前提不成立"
            )
        return rid, int(ptr["current_generation"])

    async def _entry_counts() -> dict[str, int]:
        async with Session() as s:
            row = (
                await s.execute(
                    sa.text(
                        "SELECT "
                        "(SELECT COALESCE(max(generation), 0) FROM "
                        " working_paper_content_representation WHERE wp_id = :w "
                        " AND entry_id = :e), "
                        "(SELECT COALESCE(max(generation), 0) FROM "
                        " working_paper_oo_room WHERE wp_id = :w AND entry_id = :e), "
                        "(SELECT count(*) FROM working_paper_content_representation "
                        " WHERE wp_id = :w AND entry_id = :e)"
                    ),
                    {"w": wp, "e": ENTRY},
                )
            ).one()
        return {"max_rep": int(row[0]), "max_room": int(row[1]), "reps": int(row[2])}

    async def _retire_case(
        key: str, projection: Projection, *, retire: str
    ) -> dict[str, Any]:
        room_id, room_gen = await _room_at_pointer()
        async with Session() as s:
            svc = RoomService(WorkpaperSyncRepository(s))
            if retire == "supersede":
                await svc.supersede_room(room_id=room_id, reason="task25-retired")
            else:
                await svc.mark_refresh_required(room_id=room_id, reason="task25-refresh")
            await s.commit()
        before = await _pointers()
        counts_before = await _entry_counts()
        flushed = await _flush(key, projection, before["revision"])
        outcome, failure = None, None
        async with Session() as s:
            coordinator = _coordinator(s)
            try:
                outcome = await coordinator.materialize(
                    await coordinator.authorize(
                        _request(
                            token=flushed["token"], key=key,
                            revision=before["revision"], projection=projection,
                            adapter=_JsonCarrierAdapter(),
                        )
                    )
                )
            except Exception as exc:  # noqa: BLE001 - 记录实际类型供断言
                failure = exc
            issued = coordinator.descriptors_issued
        after = await _pointers()
        counts_after = await _entry_counts()
        descriptor = None if outcome is None else outcome.descriptor
        return {
            "retired_room_generation": room_gen,
            "max_generation_before": max(
                counts_before["max_rep"], counts_before["max_room"]
            ),
            "refusal": None if failure is None else type(failure).__name__,
            "refusal_detail": None if failure is None else str(failure)[:300],
            "status": (
                None if failure is None else MC.classify_materialize_rejection(failure)
            ),
            "descriptors_issued": issued,
            "business_identity_reused": (
                None if outcome is None else outcome.business_identity_reused
            ),
            "descriptor_generation": (
                None if descriptor is None else int(descriptor.generation)
            ),
            "pointer_generation_after": after["current_generation"],
            "pointer_moved": (
                after["current_representation_id"]
                != before["current_representation_id"]
            ),
            "revision_delta": after["revision"] - before["revision"],
            "rooms_delta": after["rooms"] - before["rooms"],
            "representations_delta": counts_after["reps"] - counts_before["reps"],
        }

    try:
        same_content = _projection("2025年度", "4321.00")  # 阶段 12 已提交的内容
        new_content = _projection("2025年度", "2468.00")
        snap["retired"]["same_content"] = await _retire_case(
            "idem-retired-same", same_content, retire="supersede"
        )
        snap["retired"]["new_content"] = await _retire_case(
            "idem-retired-new", new_content, retire="supersede"
        )
        snap["retired"]["refresh_required"] = await _retire_case(
            "idem-retired-refresh", new_content, retire="refresh"
        )
    except Exception as exc:  # noqa: BLE001
        _phase_failed("retired", exc)
