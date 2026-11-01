# -*- coding: utf-8 -*-
"""Task26 companion world：store 第 N 项失败时整笔回滚，并用同一 operation 重试。"""
from __future__ import annotations

import sys
import types
from typing import Any

import sqlalchemy as sa
from sqlalchemy import event

from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY
from app.services.workpaper_sync.store_item_specs import DedicatedStoreItem, StoreMergePlan

_PROVIDER = "task26_atomic_store_provider"
_PROVIDER_KEY = f"app.services.workpaper_sync.{_PROVIDER}"


def _install_provider(ctx: Any) -> tuple[Any, Any]:
    previous = STORE_MERGE_REGISTRY.get(ctx.adapter_id)
    previous_module = sys.modules.get(_PROVIDER_KEY)
    provider = types.ModuleType(_PROVIDER_KEY)
    provider.STORE_ATOMIC_A, provider.STORE_ATOMIC_B = ctx.store_items
    provider.all_store_item_ids = lambda: ()
    provider.merge_all_atomic_stores = lambda **_: {}

    def merge(marker: str):
        def apply(*, projection, base_state):
            payload = dict(base_state) if isinstance(base_state, dict) else {}
            payload.update({"marker": marker, "field_count": len(projection.values)})
            return payload, 1, tuple(sorted(projection.values))

        return apply

    provider.merge_atomic_a = merge("a")
    provider.merge_atomic_b = merge("b")
    sys.modules[_PROVIDER_KEY] = provider
    STORE_MERGE_REGISTRY[ctx.adapter_id] = StoreMergePlan(
        adapter_id=ctx.adapter_id,
        provider_module=_PROVIDER,
        dual_store_fn="_mirror_dual_stores",
        merge_all_fn="merge_all_atomic_stores",
        dedicated_items=(
            DedicatedStoreItem("STORE_ATOMIC_A", "merge_atomic_a", "dict", _PROVIDER),
            DedicatedStoreItem("STORE_ATOMIC_B", "merge_atomic_b", "dict", _PROVIDER),
        ),
    )
    return previous, previous_module


def _restore_provider(ctx: Any, previous: Any, previous_module: Any) -> None:
    if previous is None:
        STORE_MERGE_REGISTRY.pop(ctx.adapter_id, None)
    else:
        STORE_MERGE_REGISTRY[ctx.adapter_id] = previous
    if previous_module is None:
        sys.modules.pop(_PROVIDER_KEY, None)
    else:
        sys.modules[_PROVIDER_KEY] = previous_module


async def _atomic_state(ctx: Any, wp_id: Any, room_id: Any, app_id: Any) -> dict[str, Any]:
    state = await ctx.db_state(wp_id, room_id, app_id)
    async with ctx.Session() as session:
        stores = (
            await session.execute(
                sa.text(
                    "SELECT item_id, remark, xmin::text AS xid FROM checklist_responses "
                    "WHERE wp_id = :w ORDER BY item_id"
                ),
                {"w": wp_id},
            )
        ).mappings().all()
        xids: dict[str, str] = {}
        if state["app_result_revision"] is not None:
            queries = {
                "revision": ("SELECT xmin::text FROM working_paper WHERE id = :w", {"w": wp_id}),
                "content_version": (
                    "SELECT xmin::text FROM working_paper_content_version WHERE id = :id",
                    {"id": state["current_content_version_id"]},
                ),
                "representation": (
                    "SELECT xmin::text FROM working_paper_content_representation WHERE id = :id",
                    {"id": state["app_result_representation"]},
                ),
                "entry_pointer": (
                    "SELECT xmin::text FROM working_paper_sync_entry_state "
                    "WHERE wp_id = :w AND entry_id = :entry",
                    {"w": wp_id, "entry": ctx.entry},
                ),
                "application": (
                    "SELECT xmin::text FROM working_paper_content_application WHERE id = :id",
                    {"id": app_id},
                ),
                "operation": (
                    "SELECT xmin::text FROM working_paper_sync_operation "
                    "WHERE application_id = :id AND duplicate_of_operation_id IS NULL",
                    {"id": app_id},
                ),
                "outbox": (
                    "SELECT xmin::text FROM import_event_outbox WHERE payload->>'wp_id' = :w",
                    {"w": str(wp_id)},
                ),
            }
            for label, (sql, params) in queries.items():
                xid = (await session.execute(sa.text(sql), params)).scalar_one_or_none()
                if xid is not None:
                    xids[label] = str(xid)
            for row in stores:
                xids[f"store:{row['item_id']}"] = str(row["xid"])
    state["store_rows"] = [dict(row) for row in stores]
    state["committed_xids"] = xids
    return state


async def collect_store_atomic(
    scope: dict[str, Any], *, adapter_id: str, store_items: tuple[str, str]
) -> dict[str, Any]:
    """从宿主采集作用域取既有夹具；显式键访问让接口漂移立即失败。"""
    ctx = types.SimpleNamespace(
        Session=scope["Session"], engine=scope["engine"], project=scope["project"],
        user_a=scope["user_a"], contract=scope["contract"], entry=scope["ENTRY"],
        adapter_id=adapter_id, store_items=store_items, period=scope["PERIOD"],
        total=scope["TOTAL"], decimal=scope["Decimal"],
        recording_probe=scope["_RecordingProbe"], json_adapter=scope["_JsonCarrierAdapter"],
        stage_world=scope["_stage_world"], coordinator=scope["_coordinator"],
        db_state=scope["_db_state"],
    )
    previous, previous_module = _install_provider(ctx)
    AtomicAdapter = type("AtomicAdapter", (ctx.json_adapter,), {"adapter_id": ctx.adapter_id})
    try:
        async with ctx.engine.begin() as conn:
            await conn.exec_driver_sql(
                "CREATE TABLE checklist_responses ("
                "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
                "project_id UUID NOT NULL REFERENCES projects(id), "
                "wp_id UUID NOT NULL REFERENCES working_paper(id), "
                "item_id VARCHAR(200) NOT NULL, conclusion TEXT, remark TEXT, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE (wp_id, item_id))"
            )
        staged = await ctx.stage_world(
            "store-atomic",
            base_values={ctx.period: "2024", ctx.total: ctx.decimal("100")},
            current_values=None,
            incoming_values={ctx.period: "2025", ctx.total: ctx.decimal("777")},
            adapter_id=ctx.adapter_id,
        )
        wp_id = staged["entry"]["wp"]
        room_id = staged["env"]["room"]
        application_id = staged["app"]
        operation_id = staged["req"]["operation"]
        before = await _atomic_state(ctx, wp_id, room_id, application_id)
        inserts = {"count": 0}

        def fail_second_store_insert(_conn, _cursor, statement, _params, _context, _many):
            if "INSERT INTO checklist_responses" not in statement:
                return
            inserts["count"] += 1
            if inserts["count"] == 2:
                raise RuntimeError("注入缺陷：第二个 store item 写入失败")

        event.listen(ctx.engine.sync_engine, "before_cursor_execute", fail_second_store_insert)
        try:
            async with ctx.Session() as session:
                failed = await ctx.coordinator(
                    session, probe=ctx.recording_probe()
                ).apply_durable_incoming(
                    operation_id=operation_id,
                    declared_project_id=ctx.project,
                    declared_wp_id=wp_id,
                    declared_entry_id=ctx.entry,
                    adapter=AtomicAdapter(),
                    contract=ctx.contract,
                    actor_id=ctx.user_a,
                )
        finally:
            event.remove(ctx.engine.sync_engine, "before_cursor_execute", fail_second_store_insert)
        mid = await _atomic_state(ctx, wp_id, room_id, application_id)
        async with ctx.Session() as session:
            retried = await ctx.coordinator(
                session, probe=ctx.recording_probe()
            ).apply_durable_incoming(
                operation_id=operation_id,
                declared_project_id=ctx.project,
                declared_wp_id=wp_id,
                declared_entry_id=ctx.entry,
                adapter=AtomicAdapter(),
                contract=ctx.contract,
                actor_id=ctx.user_a,
                attempt=2,
            )
        after = await _atomic_state(ctx, wp_id, room_id, application_id)
        return {
            "failed_outcome": failed.as_dict(),
            "retried_outcome": retried.as_dict(),
            "before": before,
            "mid": mid,
            "after": after,
            "store_insert_attempts_before_failure": inserts["count"],
            "same_operation": failed.canonical_operation_id == retried.canonical_operation_id,
            "same_application": failed.application_id == retried.application_id,
            "same_substrate": failed.substrate.artifact_id == retried.substrate.artifact_id,
        }
    finally:
        _restore_provider(ctx, previous, previous_module)
