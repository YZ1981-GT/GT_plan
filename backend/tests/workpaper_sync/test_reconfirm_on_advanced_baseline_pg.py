# -*- coding: utf-8 -*-
"""同一 lease 重开在线编辑：确认前移到 room 已认可的新基线（真实 PostgreSQL）。

spec: d2-skeleton-slot-reuse-and-writeback-speed · R4

═══ 锁的是什么缺陷 ═══

重药安徽 D2（2026-10-23）：OO 改一格 → forcesave → 应用成功（merged == incoming，room
快照推进到 rev 19 的同代新 representation）→ 用户重开在线编辑。lease 未过期 ⇒ 复用同一
participant ⇒ confirm-descriptor 回传 pointer 上的新基线 ⇒ 仓储报「同一编辑会话不得用
不同基线二次确认」，在线编辑在 lease 到期（4 小时）前打不开。

═══ 判据 ═══

① 回传的正是 room 快照 ⇒ 成功：旧确认 ``invalidated_at`` 落值、新确认成为唯一 active，
  资格门读到的是新确认；同一请求重放返回同一行。
② 其余形态保持 409（``ScopeIntegrityError``）：旧基线重放、room 未认可的基线、
  快照被别的 participant 拉回旧版本时的版本倒退。

真库的理由：``uq_wpocc_active`` 是 PG partial unique（``WHERE invalidated_at IS NULL``），
``trg_wpocc_identity`` 在 UPDATE 时也跑 —— 两者 SQLite 都没有。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_MIGRATION = (
    _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"
)
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_reconfirm_"
_STUB_DDL = """
CREATE TABLE projects (id UUID PRIMARY KEY, name VARCHAR(200) NOT NULL DEFAULT 'stub');
CREATE TABLE users (id UUID PRIMARY KEY, username VARCHAR(100) NOT NULL DEFAULT 'stub');
CREATE TABLE working_paper (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    file_version INTEGER NOT NULL DEFAULT 1,
    parsed_data JSONB,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""
ENTRY = "xlsx/gt-d2-accounts-receivable"


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


async def _collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部场景
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.workpaper_sync_models import WorkpaperOoClientConfirmation
    from app.services.workpaper_sync.models import (
        ArtifactKind,
        ArtifactState,
        BundleSlot,
        BundleSlotSpec,
        ParticipantMode,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.rooms import RoomScope, RoomService

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise RuntimeError("判据是 PG partial unique + 触发器，必须真实 PostgreSQL（不 skip）")
    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off))
    snap: dict[str, Any] = {"schema": schema, "server_version": None, "phase_errors": {}}
    engine = None
    try:
        async with admin.connect() as conn:
            snap["server_version"] = (await conn.exec_driver_sql("SELECT version()")).scalar_one()
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(
            settings.DATABASE_URL,
            poolclass=NullPool,
            connect_args={**ssl_off, "server_settings": {"search_path": schema}},
        )
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            for stmt in [s.strip() for s in _STUB_DDL.strip().split(";") if s.strip()]:
                await conn.exec_driver_sql(stmt)
        for stmt in forward:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(stmt)

        project_id, wp_id = uuid.uuid4(), uuid.uuid4()
        user_a, user_b = uuid.uuid4(), uuid.uuid4()
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{project_id}')")
            for u in (user_a, user_b):
                await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{u}')")
            await conn.exec_driver_sql(
                f"INSERT INTO working_paper (id, project_id) VALUES ('{wp_id}', '{project_id}')"
            )
        scope = RoomScope(project_id=project_id, wp_id=wp_id, entry_id=ENTRY)
        base = f"storage/{project_id}/workpapers/.versions/{wp_id}"
        w: dict[str, Any] = {}

        async def _version(repo: WorkpaperSyncRepository, n: int, parent: Any) -> tuple[Any, Any]:
            """第 n 版内容：content version（revision=n）+ 同代（gen 1）representation。"""
            proj = await repo.register_artifact(
                project_id=project_id, wp_id=wp_id, kind=ArtifactKind.projection,
                state=ArtifactState.published, relative_path=f"{base}/projections/v{n}.json.gz",
                sha256=_d(f"projection-v{n}"), size_bytes=1024, document_type="json.gz",
            )
            canon = await repo.register_artifact(
                project_id=project_id, wp_id=wp_id, kind=ArtifactKind.canonical,
                state=ArtifactState.published,
                relative_path=f"{base}/representations/{ENTRY}/g1-v{n}.xlsx",
                sha256=_d(f"canonical-v{n}"), size_bytes=4096, document_type="xlsx",
            )
            cv = await repo.create_content_version(
                project_id=project_id, wp_id=wp_id, entry_id=ENTRY, revision=n,
                source="html" if parent is None else "onlyoffice",
                parent_version_id=None if parent is None else parent[0].id,
                projection_artifact_id=proj.id, projection_sha256=proj.sha256,
            )
            rep = await repo.create_representation(
                project_id=project_id, wp_id=wp_id, entry_id=ENTRY, content_version_id=cv.id,
                generation=1, document_type="xlsx", artifact_id=canon.id,
                artifact_sha256=canon.sha256, definition_bundle_id=w["bundle"].id,
                authority_model_definition_id=w["authority"].id, adapter_id="excel.d2.v1",
                adapter_build_digest=_d("adapter-build"), structure_hash=_d("structure"),
                identity_inventory_sha256=_d("identity"),
                reason="content_commit" if parent is None else "rematerialize",
                parent_representation_id=None if parent is None else parent[1].id,
            )
            await repo.set_entry_pointer(
                wp_id=wp_id, entry_id=ENTRY, representation_id=rep.id, generation=1
            )
            return cv, rep

        async def _confirm(
            svc: RoomService, participant_id: Any, version: tuple[Any, Any], key: str,
            projection: str | None = None,
        ) -> Any:
            cv, rep = version
            conf, _room = await svc.confirm_descriptor(
                scope, room_id=w["room"].id, participant_id=participant_id,
                representation_id=rep.id, content_version_id=cv.id,
                projection_sha256=projection or cv.projection_sha256, idempotency_key=key,
                expected_bundle=w["frozen"],
            )
            return conf

        async def _refusal(name: str, body: Any) -> None:
            """跑一段应被拒的确认；记录实际异常，整段回滚（不污染后续阶段）。"""
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                try:
                    await body(repo, svc)
                    snap[name] = None
                except Exception as exc:  # noqa: BLE001 - 记录实际异常类型
                    snap[name] = _err(exc)
                await s.rollback()

        async def _rows_of(s: Any, participant_id: Any) -> list[tuple[str, bool]]:
            rows = (
                await s.execute(
                    sa.select(
                        WorkpaperOoClientConfirmation.representation_id,
                        WorkpaperOoClientConfirmation.invalidated_at,
                    )
                    .where(WorkpaperOoClientConfirmation.participant_id == participant_id)
                    .order_by(WorkpaperOoClientConfirmation.confirmed_at)
                )
            ).all()
            return [(str(r[0]), r[1] is None) for r in rows]

        # ═══ 世界：bundle + v1 + room + A/B 两个 lease，A 确认 v1 ═══
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            svc = RoomService(repo)
            blobs = {}
            for name in ("tpl", "instr", "contract", "authority", "bundle_payload"):
                blobs[name] = await repo.register_artifact(
                    project_id=project_id, wp_id=wp_id, kind=ArtifactKind.definition,
                    state=ArtifactState.published, relative_path=f"{base}/definitions/{name}.json",
                    sha256=_d(f"blob-{name}"), size_bytes=512, document_type="json",
                )
            defs = {}
            for kind, logical in (("template", "d2.template"), ("instrumentation", "d2.instr"), ("contract", "d2.contract")):
                short = {"template": "tpl", "instrumentation": "instr", "contract": "contract"}[kind]
                defs[kind] = await repo.create_definition_artifact(
                    kind=kind, logical_id=logical, semantic_version="1.0.0",
                    blob_artifact_id=blobs[short].id, sha256=_d(f"{short}-def"),
                    **({"structure_hash": _d(f"{short}-structure")} if kind != "contract" else {}),
                    source_commit="reconfirm",
                )
            w["authority"] = await repo.create_definition_artifact(
                kind="authority_model", logical_id="authority.projection", semantic_version="1.0.0",
                blob_artifact_id=blobs["authority"].id, sha256=_d("authority-def"),
                authority_model_type="projection_contract", source_commit="reconfirm",
            )
            w["bundle"] = await repo.create_definition_bundle(
                authority_model_definition_id=w["authority"].id,
                slots={
                    slot: BundleSlotSpec(slot, "definition", f"definition:{defs[k].id}", defs[k].sha256)
                    for slot, k in (
                        (BundleSlot.template, "template"),
                        (BundleSlot.instrumentation, "instrumentation"),
                        (BundleSlot.contract, "contract"),
                    )
                },
                canonical_payload_artifact_id=blobs["bundle_payload"].id,
                canonical_payload_sha256=_d("bundle-canonical"),
            )
            w["v1"] = await _version(repo, 1, None)
            w["room"], w["frozen"] = await svc.open_or_reuse_room(
                scope, representation=w["v1"][1], opened_base_version_id=w["v1"][0].id
            )
            w["a"] = await svc.join_participant(
                scope, room_id=w["room"].id, user_id=user_a, mode=ParticipantMode.edit,
                permission_epoch=1, lease_token="lease-a",
            )
            w["b"] = await svc.join_participant(
                scope, room_id=w["room"].id, user_id=user_b, mode=ParticipantMode.edit,
                permission_epoch=1, lease_token="lease-b",
            )
            w["conf_v1"] = await _confirm(svc, w["a"].id, w["v1"], "open-a-1")
            await s.commit()

        # ═══ OO→HTML 应用：同代 v2 + merged == incoming 推进 room 快照 ═══
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            svc = RoomService(repo)
            w["v2"] = await _version(repo, 2, w["v1"])
            settled = await svc.settle_client_baseline(
                room_id=w["room"].id,
                merged_projection_sha256=w["v2"][0].projection_sha256,
                incoming_projection_sha256=w["v2"][0].projection_sha256,
                applied_content_version_id=w["v2"][0].id,
                applied_representation_id=w["v2"][1].id,
                bundle=w["frozen"],
            )
            snap["settled"] = settled.client_baseline_advanced
            await s.commit()

        # ═══ ② rep/cv 等于快照但 projection 不等：快照不是整体认可 ⇒ 拒 ═══
        async def _tampered(repo: Any, svc: RoomService) -> None:
            await _confirm(svc, w["a"].id, w["v2"], "tampered-a-1", projection=_d("tampered"))

        await _refusal("projection_mismatch", _tampered)

        # ═══ ① 同一 lease 重开：回传 room 快照（v2）═══
        snap["reopen"] = {}
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                conf_v2 = await _confirm(svc, w["a"].id, w["v2"], "reopen-a-1")
                replay = await _confirm(svc, w["a"].id, w["v2"], "reopen-a-1")
                _room, _part, gate_conf = await svc.assert_can_initiate_request(
                    room_id=w["room"].id, participant_id=w["a"].id
                )
                snap["reopen"] = {
                    "new_is_distinct": conf_v2.id != w["conf_v1"].id,
                    "replay_same_row": replay.id == conf_v2.id,
                    "gate_uses_new": gate_conf.id == conf_v2.id,
                    "rows": await _rows_of(s, w["a"].id),
                }
                await s.commit()
        except Exception as exc:  # noqa: BLE001 - 记录实际异常
            snap["phase_errors"]["reopen"] = _err(exc)
        snap["expected_rows"] = [(str(w["v1"][1].id), False), (str(w["v2"][1].id), True)]

        # ═══ ② 旧基线重放（陈旧标签页）═══
        async def _stale(repo: Any, svc: RoomService) -> None:
            await _confirm(svc, w["a"].id, w["v1"], "stale-a-1")

        await _refusal("stale_replay", _stale)

        # ═══ ② room 未认可的基线：v3 已发布但从未 settle ═══
        async def _unvouched(repo: Any, svc: RoomService) -> None:
            v3 = await _version(repo, 3, w["v2"])
            await _confirm(svc, w["a"].id, v3, "unvouched-a-1")

        await _refusal("unvouched", _unvouched)

        # ═══ ② 版本倒退：B 首次确认 v1 把快照拉回 v1，A（已在 v2）不得跟着退 ═══
        async def _regress(repo: Any, svc: RoomService) -> None:
            await _confirm(svc, w["b"].id, w["v1"], "open-b-1")
            await _confirm(svc, w["a"].id, w["v1"], "regress-a-1")

        await _refusal("regress", _regress)
        return snap
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await admin.dispose()


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


def test_ran_on_real_postgresql(snap: dict[str, Any]) -> None:
    assert "PostgreSQL" in (snap["server_version"] or "")
    assert snap["settled"] is True, "前置：merged == incoming 必须推进 room 快照"


def test_reopen_with_room_vouched_baseline_rebases_the_lease(snap: dict[str, Any]) -> None:
    assert snap["phase_errors"] == {}, snap["phase_errors"]
    r = snap["reopen"]
    assert r["new_is_distinct"] and r["replay_same_row"] and r["gate_uses_new"], r
    assert r["rows"] == snap["expected_rows"], (
        "旧确认必须作废、新确认成为唯一 active（uq_wpocc_active）", r["rows"]
    )


@pytest.mark.parametrize(
    "phase", ["projection_mismatch", "stale_replay", "unvouched", "regress"]
)
def test_other_identity_changes_are_still_refused(snap: dict[str, Any], phase: str) -> None:
    assert snap[phase] is not None and snap[phase].startswith("ScopeIntegrityError"), (
        phase,
        snap[phase],
    )
