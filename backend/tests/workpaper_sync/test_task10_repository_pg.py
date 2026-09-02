# -*- coding: utf-8 -*-
"""Task 10 真实 PostgreSQL 行为守卫：多连接并发下 repository + V151 约束的联合结果。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 10
Requirements: 2.1, 2.4, 2.5, 2.9, 4.3, 5.4, 5.5, 5.10, 8.5, 10.5, 10.9, 10.10, 10.11, 13.5, 14.10
Properties: P4 / P5 / P18 / P36 / P43 / P59 / P63 / P64 / P68

═══ 为什么必须多连接、必须真库 ═══

Task 10 的核心断言全是**并发结果**：「N 个不同 request 同 application key 最终 1 primary +
N-1 direct duplicates 且零 stranded shell」「同 wp 串行、跨 wp 并行」「claim 并发幂等」。
单连接顺序调用永远看不到这些 —— 用 mock/SQLite 更是把唯一判据抹掉。故本文件：

* 每个并发场景开**独立 AsyncSession/连接**，用 `asyncio.gather` 真并发；
* 串行化判据用 `pg_try_advisory_xact_lock` 的真假（不靠 sleep 猜时序）；
* 乐观锁判据 = 两个并发 `bump_content_revision(expected)` 恰一个成功。

═══ 隔离：scratch schema，物理上不可能触到业务表 ═══

schema 名 `tmp_task10_repo_<hex>`，`search_path` 只含它（不含 public），
`projects/users/working_paper` 在 scratch 内建桩表 ⇒ V151 的 `ALTER TABLE working_paper`
与回填打在桩表上。结束 `DROP SCHEMA CASCADE`。

═══ 采集写法 ═══

全部场景由**一次 `asyncio.run`** 跑完并落进快照（module fixture）；不给每个测试各自
开 async（共享连接池会被污染，第二个测试起 `NoneType has no attribute send`）。
`DATABASE_URL` 非 PostgreSQL 时**直接失败而不是 skip**：本任务判据就是数据库并发行为，
skip 等于静默抹掉唯一判据。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import uuid
from datetime import timedelta
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

_SCHEMA_PREFIX = "tmp_task10_repo_"

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

ENTRY = "g7.disclosure.listed"


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _marker_sha(slot: str) -> str:
    """typed null marker 的真实 digest —— 与 V151 seed 的 canonical payload 逐字节一致。"""
    payload = (
        '{"schema_version":"definition-bundle-marker:v1",'
        f'"slot":"{slot}","value":"none"}}'
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# 采集
# ═══════════════════════════════════════════════════════════════════════════


async def _collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部并发场景
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.workpaper_sync_models import (
        WorkpaperCallbackRecoveryCase,
        WorkpaperContentApplication,
        WorkpaperContentApplicationEvent,
        WorkpaperContentVersion,
        WorkpaperForcesaveRequest,
        WorkpaperOoCloseIntent,
        WorkpaperOoCloseIntentEvent,
        WorkpaperOoParticipant,
        WorkpaperOoRoom,
        WorkpaperSyncOperation,
        WorkpaperSyncOperationEvent,
        WorkpaperSyncScopeIndex,
    )
    from app.services.workpaper_sync.models import (
        ActorType,
        ArtifactKind,
        ArtifactState,
        BundleSlot,
        BundleSlotSpec,
        CandidateState,
        DeliveryState,
        IdempotencyConflictError,
        ParticipantState,
        QuarantinedIncomingError,
        RecoveryReason,
        RequestKind,
        RequestState,
        RevisionConflictError,
        RoomState,
        ScopeIntegrityError,
        SyncDomainError,
        ScopeResourceKind,
        SupersedeError,
        compute_delivery_key,
        compute_frozen_request_fingerprint,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 10 的判据是数据库并发行为（advisory lock / 乐观锁 / create-or-hit / "
            "deferred trigger），必须真实 PostgreSQL；当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}

    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "server_version": None,
        "apply_errors": [],
        "introspection": {},
        "flush_only": {},
        "idempotency": {},
        "n_shells": {},
        "sequential_fold": {},
        "supersede": {},
        "delivery_owner": {},
        "quarantined": {},
        "scope_tombstone": {},
        "numeric_revision": {},
        "close": {},
        "recovery": {},
        "locks": {},
        "candidate": {},
    }
    engine = None
    try:
        async with admin.connect() as conn:
            snap["server_version"] = (
                await conn.exec_driver_sql("SELECT version()")
            ).scalar_one()
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
        for idx, stmt in enumerate(forward, 1):
            try:
                async with engine.begin() as conn:
                    await conn.exec_driver_sql(stmt)
            except Exception as exc:  # noqa: BLE001 - 采集需原文入快照
                snap["apply_errors"].append({"index": idx, "error": _err(exc)})
                break
        if snap["apply_errors"]:
            raise _HarnessError(f"V151 应用失败: {snap['apply_errors']}")

        # ── introspection：operation 表不得有 application_key 列 ──────────
        async with engine.connect() as conn:
            snap["introspection"]["operation_columns"] = [
                str(r)
                for r in (
                    await conn.exec_driver_sql(
                        "SELECT column_name FROM information_schema.columns WHERE "
                        f"table_schema = '{schema}' AND "
                        "table_name = 'working_paper_sync_operation' ORDER BY column_name"
                    )
                )
                .scalars()
                .all()
            ]
            snap["introspection"]["application_key_holders"] = [
                str(r)
                for r in (
                    await conn.exec_driver_sql(
                        "SELECT table_name FROM information_schema.columns WHERE "
                        f"table_schema = '{schema}' AND column_name = 'application_key'"
                    )
                )
                .scalars()
                .all()
            ]

        # ═══ 世界（一次提交）═══════════════════════════════════════════
        ids: dict[str, Any] = {
            "project": uuid.uuid4(),
            "user_a": uuid.uuid4(),
            "user_b": uuid.uuid4(),
            "user_c": uuid.uuid4(),
            "wp_a": uuid.uuid4(),
            "wp_b": uuid.uuid4(),
        }
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                f"INSERT INTO projects (id) VALUES ('{ids['project']}')"
            )
            for u in ("user_a", "user_b", "user_c"):
                await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{ids[u]}')")
            for w in ("wp_a", "wp_b"):
                await conn.exec_driver_sql(
                    "INSERT INTO working_paper (id, project_id) VALUES "
                    f"('{ids[w]}', '{ids['project']}')"
                )

        p, wp = ids["project"], ids["wp_a"]
        base_path = f"storage/{p}/workpapers"

        async def _defs(repo: WorkpaperSyncRepository) -> dict[str, Any]:
            """definition artifacts + approved projection_contract bundle。"""
            blobs = {}
            for name in ("tpl", "instr", "contract", "authority", "bundle_payload"):
                blobs[name] = await repo.register_artifact(
                    project_id=p,
                    wp_id=wp,
                    kind=ArtifactKind.definition,
                    state=ArtifactState.published,
                    relative_path=f"{base_path}/.versions/{wp}/definitions/{name}.json",
                    sha256=_d(f"blob-{name}"),
                    size_bytes=1024,
                    document_type="json",
                )
            tpl = await repo.create_definition_artifact(
                kind="template",
                logical_id="g7.listed.template",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["tpl"].id,
                sha256=_d("tpl-def"),
                structure_hash=_d("tpl-structure"),
                source_commit="task10",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation",
                logical_id="g7.listed.instrumentation",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["instr"].id,
                sha256=_d("instr-def"),
                structure_hash=_d("instr-structure"),
                source_commit="task10",
            )
            contract = await repo.create_definition_artifact(
                kind="contract",
                logical_id="g7.listed.contract",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["contract"].id,
                sha256=_d("contract-def"),
                source_commit="task10",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model",
                logical_id="authority.projection",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["authority"].id,
                sha256=_d("authority-def"),
                authority_model_type="projection_contract",
                source_commit="task10",
            )
            bundle = await repo.create_definition_bundle(
                authority_model_definition_id=authority.id,
                slots={
                    BundleSlot.template: BundleSlotSpec(
                        BundleSlot.template, "definition", f"definition:{tpl.id}", tpl.sha256
                    ),
                    BundleSlot.instrumentation: BundleSlotSpec(
                        BundleSlot.instrumentation,
                        "definition",
                        f"definition:{instr.id}",
                        instr.sha256,
                    ),
                    BundleSlot.contract: BundleSlotSpec(
                        BundleSlot.contract,
                        "definition",
                        f"definition:{contract.id}",
                        contract.sha256,
                    ),
                },
                canonical_payload_artifact_id=blobs["bundle_payload"].id,
                canonical_payload_sha256=_d("bundle-canonical"),
            )
            return {"bundle": bundle, "authority": authority, "tpl": tpl, "instr": instr}

        async def _defs_candidate_bundle(repo: WorkpaperSyncRepository) -> dict[str, Any]:
            """一套**未 approved** 的 definition + bundle（负控制用）。"""
            blob = await repo.register_artifact(
                project_id=p,
                wp_id=wp,
                kind=ArtifactKind.definition,
                state=ArtifactState.published,
                relative_path=f"{base_path}/.versions/{wp}/definitions/cand-{uuid.uuid4()}.json",
                sha256=_d(f"cand-blob-{uuid.uuid4()}"),
                size_bytes=512,
                document_type="json",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model",
                logical_id="authority.candidate",
                semantic_version="9.9.9",
                blob_artifact_id=blob.id,
                sha256=_d("authority-candidate"),
                authority_model_type="custom_authoritative_ooxml",
                source_commit="task10",
                approved=True,
            )
            tpl = await repo.create_definition_artifact(
                kind="template",
                logical_id="cand.template",
                semantic_version="9.9.9",
                blob_artifact_id=blob.id,
                sha256=_d("cand-template"),
                structure_hash=_d("cand-template-structure"),
                source_commit="task10",
                approved=True,
            )
            bundle = await repo.create_definition_bundle(
                authority_model_definition_id=authority.id,
                slots={
                    BundleSlot.template: BundleSlotSpec(
                        BundleSlot.template, "definition", f"definition:{tpl.id}", tpl.sha256
                    ),
                    BundleSlot.instrumentation: BundleSlotSpec(
                        BundleSlot.instrumentation,
                        "instrumentation:none:v1",
                        "marker:instrumentation:none:v1",
                        _marker_sha("instrumentation"),
                    ),
                    BundleSlot.contract: BundleSlotSpec(
                        BundleSlot.contract,
                        "contract:none:v1",
                        "marker:contract:none:v1",
                        _marker_sha("contract"),
                    ),
                },
                canonical_payload_artifact_id=blob.id,
                canonical_payload_sha256=_d(f"cand-bundle-{uuid.uuid4()}"),
                approved=False,  # 关键：candidate 状态
            )
            return {"bundle": bundle, "authority": authority}

        world: dict[str, Any] = {}
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            world.update(await _defs(repo))
            bundle = world["bundle"]
            authority = world["authority"]

            proj_art = await repo.register_artifact(
                project_id=p,
                wp_id=wp,
                kind=ArtifactKind.projection,
                state=ArtifactState.published,
                relative_path=f"{base_path}/.versions/{wp}/projections/v0.json.gz",
                sha256=_d("projection-v0"),
                size_bytes=2048,
                document_type="json.gz",
            )
            canon_g1 = await repo.register_artifact(
                project_id=p,
                wp_id=wp,
                kind=ArtifactKind.canonical,
                state=ArtifactState.published,
                relative_path=f"{base_path}/.versions/{wp}/representations/{ENTRY}/g1.xlsx",
                sha256=_d("canonical-g1"),
                size_bytes=40960,
                document_type="xlsx",
            )
            cv0 = await repo.create_content_version(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                revision=0,
                source="html",
                projection_artifact_id=proj_art.id,
                projection_sha256=proj_art.sha256,
                actor_id=ids["user_a"],
            )
            rep1 = await repo.create_representation(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                content_version_id=cv0.id,
                generation=1,
                document_type="xlsx",
                artifact_id=canon_g1.id,
                artifact_sha256=canon_g1.sha256,
                definition_bundle_id=bundle.id,
                authority_model_definition_id=authority.id,
                adapter_id="g7.disclosure.listed",
                adapter_build_digest=_d("adapter-build"),
                structure_hash=_d("structure"),
                identity_inventory_sha256=_d("identity-inventory"),
                reason="content_commit",
            )
            await repo.set_entry_pointer(
                wp_id=wp, entry_id=ENTRY, representation_id=rep1.id, generation=1
            )
            await repo.set_current_content_version(wp, cv0.id)
            world.update(
                {"cv0": cv0, "rep1": rep1, "proj_art": proj_art, "canon_g1": canon_g1}
            )
            await s.commit()

        adapter_digest = _d("adapter-build")
        contrib_digest = _d("contributors")

        async def _make_room(
            s: Any,
            repo: WorkpaperSyncRepository,
            *,
            generation: int,
            users: tuple[str, ...],
        ) -> dict[str, Any]:
            """建一个新 generation 的 room + 逐人 lease + descriptor confirmation。"""
            room = await repo.create_room(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                doc_key=f"wpsync:{wp}:{ENTRY}:{generation}",
                generation=generation,
                opened_base_version_id=world["cv0"].id,
            )
            parts: dict[str, Any] = {}
            confs: dict[str, Any] = {}
            for u in users:
                part = await repo.create_participant(
                    project_id=p,
                    wp_id=wp,
                    entry_id=ENTRY,
                    room_id=room.id,
                    user_id=ids[u],
                    mode="edit",
                    permission_epoch=1,
                    lease_token_hash=_d(f"lease-{generation}-{u}"),
                )
                conf = await repo.create_client_confirmation(
                    project_id=p,
                    wp_id=wp,
                    entry_id=ENTRY,
                    room_id=room.id,
                    participant_id=part.id,
                    representation_id=world["rep1"].id,
                    content_version_id=world["cv0"].id,
                    projection_sha256=world["proj_art"].sha256,
                    bundle_slots_digest=_d("bundle-slots"),
                    idempotency_key=f"ready-{generation}-{u}",
                )
                parts[u] = part
                confs[u] = conf
            await repo.set_room_client_confirmed_baseline(
                room_id=room.id, confirmation=confs[users[0]]
            )
            return {"room": room, "participants": parts, "confirmations": confs}

        def _fingerprint(conf: Any, *, fence: int, perm: int = 1, edit_epoch: int = 0) -> str:
            return compute_frozen_request_fingerprint(
                client_confirmation_id=conf.id,
                client_base_version_id=conf.content_version_id,
                client_base_representation_id=conf.representation_id,
                client_base_projection_sha256=conf.projection_sha256,
                definition_bundle_sha256=conf.definition_bundle_sha256,
                authority_model_definition_sha256=conf.authority_model_definition_sha256,
                adapter_build_digest=adapter_digest,
                contributor_snapshot_digest=contrib_digest,
                client_edit_epoch=edit_epoch,
                write_fence_epoch=fence,
                initiator_permission_epoch=perm,
            )

        async def _freeze(
            repo: WorkpaperSyncRepository,
            *,
            room: Any,
            conf: Any,
            participant: Any,
            key: str,
            kind: RequestKind = RequestKind.forcesave,
            fingerprint: str | None = None,
        ) -> Any:
            return await repo.create_forcesave_request_with_shell(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                room_id=room.id,
                kind=kind,
                initiated_by_participant_id=participant.id,
                initiator_permission_epoch=1,
                client_edit_epoch=0,
                client_base_version_id=conf.content_version_id,
                client_base_representation_id=conf.representation_id,
                client_base_projection_sha256=conf.projection_sha256,
                definition_bundle_id=conf.definition_bundle_id,
                authority_model_definition_id=world["authority"].id,
                adapter_build_digest=adapter_digest,
                contributor_snapshot_digest=contrib_digest,
                idempotency_key=key,
                frozen_request_fingerprint=fingerprint
                or _fingerprint(conf, fence=int(room.write_fence_epoch)),
                created_by=ids["user_a"],
            )

        async def _durable_incoming(
            repo: WorkpaperSyncRepository,
            *,
            room: Any,
            status: int,
            discriminator: str,
            payload_label: str,
            request_id: uuid.UUID | None = None,
        ) -> tuple[Any, Any]:
            """建 delivery → downloading → durable incoming artifact（路径按 delivery sealing）。"""
            delivery = await repo.record_delivery(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                room_id=room.id,
                generation=int(room.generation),
                route_credential_id=uuid.uuid4(),
                callback_status=status,
                delivery_key=compute_delivery_key(
                    room_id=room.id,
                    generation=int(room.generation),
                    callback_status=status,
                    discriminator=discriminator,
                ),
                payload_sha256=_d(f"payload-{discriminator}"),
                forcesave_request_id=request_id,
            )
            art = await repo.register_artifact(
                project_id=p,
                wp_id=wp,
                kind=ArtifactKind.incoming,
                state=ArtifactState.durable,
                relative_path=f"{base_path}/.incoming/{wp}/{delivery.id}/artifact.xlsx",
                sha256=_d(payload_label),
                size_bytes=51200,
                document_type="xlsx",
                source_delivery_id=delivery.id,
            )
            # delivery 停在 pre-durable `downloading`：durable sealing 必须与归属
            # （application 或 recovery）同一条 UPDATE 落库，见 repository 的说明。
            await repo.mark_delivery_downloading(delivery_id=delivery.id)
            return delivery, art

        # ═══ 场景 1：repository 只 flush 不 commit ════════════════════
        async with Session() as s:
            snap["flush_only"]["scope_rows_before"] = int(
                (
                    await s.execute(
                        sa.select(sa.func.count()).select_from(WorkpaperSyncScopeIndex)
                    )
                ).scalar_one()
            )
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            await repo.lock_workpaper(wp)
            await repo.create_content_version(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                revision=900,
                source="html",
                projection_artifact_id=world["proj_art"].id,
                projection_sha256=world["proj_art"].sha256,
            )
            await s.rollback()
        async with Session() as s:
            snap["flush_only"]["rows_after_rollback"] = int(
                (
                    await s.execute(
                        sa.select(sa.func.count()).select_from(WorkpaperContentVersion).where(
                            WorkpaperContentVersion.revision == 900
                        )
                    )
                ).scalar_one()
            )
            snap["flush_only"]["scope_rows_after_rollback"] = int(
                (
                    await s.execute(
                        sa.select(sa.func.count()).select_from(WorkpaperSyncScopeIndex)
                    )
                ).scalar_one()
            )

        # ═══ 场景 2：forcesave 复合幂等键 + fingerprint 冲突 ═══════════
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            r2 = await _make_room(s, repo, generation=2, users=("user_a", "user_b"))
            room2, pa, pb = r2["room"], r2["participants"]["user_a"], r2["participants"]["user_b"]
            ca = r2["confirmations"]["user_a"]
            cb = r2["confirmations"]["user_b"]
            first = await _freeze(repo, room=room2, conf=ca, participant=pa, key="K1")
            replay = await _freeze(repo, room=room2, conf=ca, participant=pa, key="K1")
            snap["idempotency"]["cache_hit"] = replay.cache_hit
            snap["idempotency"]["same_request_id"] = replay.request.id == first.request.id
            snap["idempotency"]["same_operation_id"] = replay.operation.id == first.operation.id
            snap["idempotency"]["shell_pre_correlation"] = (
                first.operation.application_id is None
                and first.operation.duplicate_of_operation_id is None
            )
            for label, kwargs in (
                (
                    "diff_fingerprint",
                    dict(
                        conf=ca,
                        participant=pa,
                        key="K1",
                        fingerprint=_fingerprint(ca, fence=1, edit_epoch=7),
                    ),
                ),
                ("cross_participant", dict(conf=cb, participant=pb, key="K1")),
                (
                    "cross_kind",
                    dict(conf=ca, participant=pa, key="K1", kind=RequestKind.close_capture),
                ),
            ):
                try:
                    await _freeze(repo, room=room2, **kwargs)
                    snap["idempotency"][label] = None
                except IdempotencyConflictError as exc:
                    snap["idempotency"][label] = _err(exc)
                    snap["idempotency"][f"{label}_status"] = getattr(exc, "http_status", None)
                    snap["idempotency"][f"{label}_leaks_old_id"] = (
                        str(first.request.id) in str(exc) or str(first.operation.id) in str(exc)
                    )
            await s.commit()
            world["room2"] = room2

        # ═══ 场景 3：N 个不同 request 同 application key（真并发）══════
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            r3 = await _make_room(s, repo, generation=3, users=("user_a",))
            room3, p3, c3 = r3["room"], r3["participants"]["user_a"], r3["confirmations"]["user_a"]
            room3_id = room3.id
            shells = []
            for i in range(4):
                out = await _freeze(repo, room=room3, conf=c3, participant=p3, key=f"N{i}")
                shells.append(out)
            # 同一 incoming payload ⇒ 同 application key
            deliveries = []
            for i, out in enumerate(shells):
                dl, art = await _durable_incoming(
                    repo,
                    room=room3,
                    status=6 if i % 2 == 0 else 2,
                    discriminator=f"n-shell-{i}",
                    payload_label="shared-incoming",
                    request_id=out.request.id,
                )
                deliveries.append((dl, art))
            await s.commit()
            incoming_shared_id = deliveries[0][1].id
            request_sequences = [int(o.request.request_sequence) for o in shells]

        async def _correlate_one(op_id: uuid.UUID, delivery_id: uuid.UUID) -> str | None:
            async with Session() as s2:
                repo2 = WorkpaperSyncRepository(s2)
                try:
                    await repo2.correlate_durable_incoming(
                        operation_id=op_id,
                        incoming_artifact_id=incoming_shared_id,
                        current_revision=0,
                        adapter_id="g7.disclosure.listed",
                        delivery_id=delivery_id,
                        actor_type=ActorType.callback,
                    )
                    await s2.commit()
                    return None
                except Exception as exc:  # noqa: BLE001 - 并发失败需原文入快照
                    await s2.rollback()
                    return _err(exc)

        results = await asyncio.gather(
            *[
                _correlate_one(o.operation.id, deliveries[i][0].id)
                for i, o in enumerate(shells)
            ]
        )
        snap["n_shells"]["correlate_errors"] = [r for r in results if r]
        async with Session() as s:
            apps = (
                (
                    await s.execute(
                        sa.select(WorkpaperContentApplication).where(
                            WorkpaperContentApplication.room_id == room3_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            ops = (
                (
                    await s.execute(
                        sa.select(WorkpaperSyncOperation).where(
                            WorkpaperSyncOperation.room_id == room3_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            primaries = [o for o in ops if o.application_id is not None]
            dups = [o for o in ops if o.duplicate_of_operation_id is not None]
            stranded = [
                o
                for o in ops
                if o.application_id is None
                and o.duplicate_of_operation_id is None
            ]
            room3_row = (
                await s.execute(
                    sa.select(WorkpaperOoRoom).where(WorkpaperOoRoom.id == room3_id)
                )
            ).scalar_one()
            app = apps[0] if len(apps) == 1 else None
            fold_events = (
                (
                    await s.execute(
                        sa.select(WorkpaperContentApplicationEvent).where(
                            WorkpaperContentApplicationEvent.event_type == "sequence_folded"
                        )
                    )
                )
                .scalars()
                .all()
                if app
                else []
            )
            bound_events = (
                (
                    await s.execute(
                        sa.select(sa.func.count())
                        .select_from(WorkpaperSyncOperationEvent)
                        .where(
                            WorkpaperSyncOperationEvent.to_state == "application_bound",
                            WorkpaperSyncOperationEvent.operation_id.in_(
                                [o.id for o in primaries]
                            ),
                        )
                    )
                ).scalar_one()
                if primaries
                else 0
            )
            dup_events = (
                (
                    await s.execute(
                        sa.select(sa.func.count())
                        .select_from(WorkpaperSyncOperationEvent)
                        .where(
                            WorkpaperSyncOperationEvent.to_state == "duplicate",
                            WorkpaperSyncOperationEvent.operation_id.in_([o.id for o in dups]),
                        )
                    )
                ).scalar_one()
                if dups
                else 0
            )
            snap["n_shells"].update(
                {
                    "applications": len(apps),
                    "primaries": len(primaries),
                    "duplicates": len(dups),
                    "stranded": len(stranded),
                    "duplicate_targets": sorted({str(o.duplicate_of_operation_id) for o in dups}),
                    "primary_id": str(primaries[0].id) if len(primaries) == 1 else None,
                    "duplicate_states": sorted({o.state for o in dups}),
                    "origin_sequence": int(app.origin_request_sequence) if app else None,
                    "effective_sequence": int(app.effective_request_sequence) if app else None,
                    "max_request_sequence": max(request_sequences),
                    "self_superseded": bool(app.superseded_by_application_id) if app else None,
                    "room_durable_application_matches": (
                        str(room3_row.latest_durable_application_id) == str(app.id)
                        if app
                        else False
                    ),
                    "room_durable_sequence": int(room3_row.latest_durable_sequence),
                    "bound_events": int(bound_events),
                    "duplicate_events": int(dup_events),
                    "fold_events_have_request_and_fence": all(
                        e.folded_request_id is not None
                        and e.room_latest_durable_sequence is not None
                        for e in fold_events
                    ),
                    "deliveries_bound": int(
                        (
                            await s.execute(
                                sa.text(
                                    "SELECT count(*) FROM working_paper_callback_delivery "
                                    "WHERE room_id = :r AND application_id IS NOT NULL"
                                ),
                                {"r": str(room3_id)},
                            )
                        ).scalar_one()
                    ),
                }
            )

        # ═══ 场景 4：same-app 较高 sequence 顺序 fold（确定性）════════
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            r4 = await _make_room(s, repo, generation=4, users=("user_a",))
            room4, p4, c4 = r4["room"], r4["participants"]["user_a"], r4["confirmations"]["user_a"]
            room4_id = room4.id
            low = await _freeze(repo, room=room4, conf=c4, participant=p4, key="LOW")
            high = await _freeze(repo, room=room4, conf=c4, participant=p4, key="HIGH")
            dl_low, art_low = await _durable_incoming(
                repo,
                room=room4,
                status=6,
                discriminator="fold-low",
                payload_label="fold-incoming",
                request_id=low.request.id,
            )
            dl_high, _ = await _durable_incoming(
                repo,
                room=room4,
                status=2,
                discriminator="fold-high",
                payload_label="fold-incoming",
                request_id=high.request.id,
            )
            first_corr = await repo.correlate_durable_incoming(
                operation_id=low.operation.id,
                incoming_artifact_id=art_low.id,
                current_revision=0,
                adapter_id="g7.disclosure.listed",
                delivery_id=dl_low.id,
            )
            second_corr = await repo.correlate_durable_incoming(
                operation_id=high.operation.id,
                incoming_artifact_id=art_low.id,
                current_revision=0,
                adapter_id="g7.disclosure.listed",
                delivery_id=dl_high.id,
            )
            await s.commit()
            room4_row = await repo.lock_room(room4_id)
            folds = (
                (
                    await s.execute(
                        sa.select(WorkpaperContentApplicationEvent).where(
                            WorkpaperContentApplicationEvent.application_id
                            == first_corr.application.id,
                            WorkpaperContentApplicationEvent.event_type == "sequence_folded",
                        )
                    )
                )
                .scalars()
                .all()
            )
            snap["sequential_fold"] = {
                "same_application": first_corr.application.id == second_corr.application.id,
                "first_shape": first_corr.shape.value,
                "second_shape": second_corr.shape.value,
                "origin_sequence": int(first_corr.application.origin_request_sequence),
                "low_sequence": int(low.request.request_sequence),
                "high_sequence": int(high.request.request_sequence),
                "effective_sequence": int(second_corr.effective_request_sequence),
                "fold_event_count": len(folds),
                "fold_event_request_is_high": all(
                    e.folded_request_id == high.request.id for e in folds
                ),
                "fold_event_room_fence": [int(e.room_latest_durable_sequence) for e in folds],
                "self_superseded": bool(
                    first_corr.application.superseded_by_application_id
                ),
                "room_durable_sequence": int(room4_row.latest_durable_sequence),
                "duplicate_points_to_primary": str(second_corr.operation.duplicate_of_operation_id)
                == str(first_corr.operation.id),
                "duplicate_has_no_application": second_corr.operation.application_id is None,
                "canonical_primary": str(second_corr.canonical_primary_operation_id)
                == str(first_corr.operation.id),
            }
            # 负控制：对已收敛的 shell 再次 correlate 必须被拒（重复 callback 不得二次绑定）
            for label, op_id in (
                ("primary", first_corr.operation.id),
                ("duplicate", second_corr.operation.id),
            ):
                try:
                    await repo.correlate_durable_incoming(
                        operation_id=op_id,
                        incoming_artifact_id=art_low.id,
                        current_revision=0,
                        adapter_id="g7.disclosure.listed",
                    )
                    snap["sequential_fold"][f"recorrelate_{label}_type"] = None
                except SyncDomainError as exc:
                    snap["sequential_fold"][f"recorrelate_{label}_type"] = type(exc).__name__
            await s.rollback()

        # ═══ 场景 5：禁 self-supersede ════════════════════════════════
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            app_id = (
                await s.execute(
                    sa.select(WorkpaperContentApplication.id).where(
                        WorkpaperContentApplication.room_id == room4_id
                    )
                )
            ).scalar_one()
            try:
                await repo.supersede_application(
                    old_application_id=app_id, new_application_id=app_id
                )
                snap["supersede"]["repo_self"] = None
            except SupersedeError as exc:
                snap["supersede"]["repo_self"] = _err(exc)
            await s.rollback()
        async with Session() as s:
            try:
                await s.execute(
                    sa.text(
                        "UPDATE working_paper_content_application "
                        "SET superseded_by_application_id = id WHERE id = :a"
                    ),
                    {"a": str(app_id)},
                )
                await s.commit()
                snap["supersede"]["db_self"] = None
            except Exception as exc:  # noqa: BLE001
                await s.rollback()
                snap["supersede"]["db_self"] = _err(exc)

        # ═══ 场景 6：delivery 归属只按 durable_at ════════════════════
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            r6 = await _make_room(s, repo, generation=6, users=("user_a",))
            room6, p6, c6 = r6["room"], r6["participants"]["user_a"], r6["confirmations"]["user_a"]
            room6_id = room6.id
            out6 = await _freeze(repo, room=room6, conf=c6, participant=p6, key="D1")
            pre = await repo.record_delivery(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                room_id=room6.id,
                generation=6,
                route_credential_id=uuid.uuid4(),
                callback_status=6,
                delivery_key=compute_delivery_key(
                    room_id=room6.id, generation=6, callback_status=6, discriminator="pre-fail"
                ),
                forcesave_request_id=out6.request.id,
            )
            await repo.mark_delivery_downloading(delivery_id=pre.id)
            failed = await repo.mark_delivery_pre_durable_failure(
                delivery_id=pre.id, state=DeliveryState.error, response_error=1
            )
            snap["delivery_owner"]["pre_durable"] = {
                "durable_at": failed.durable_at,
                "application_id": failed.application_id,
                "recovery_id": failed.callback_recovery_case_id,
                "request_kept": failed.forcesave_request_id == out6.request.id,
            }
            dl6, art6 = await _durable_incoming(
                repo,
                room=room6,
                status=2,
                discriminator="post-durable",
                payload_label="post-durable-incoming",
                request_id=out6.request.id,
            )
            corr6 = await repo.correlate_durable_incoming(
                operation_id=out6.operation.id,
                incoming_artifact_id=art6.id,
                current_revision=0,
                adapter_id="g7.disclosure.listed",
                delivery_id=dl6.id,
            )
            after = await repo.mark_delivery_post_durable_error(delivery_id=dl6.id)
            snap["delivery_owner"]["post_durable"] = {
                "state": after.state,
                "keeps_application": str(after.application_id) == str(corr6.application.id),
                "durable_at_set": after.durable_at is not None,
            }
            await s.commit()
            world["room6"] = room6
        async with Session() as s:
            try:
                await s.execute(
                    sa.text(
                        "UPDATE working_paper_callback_delivery SET application_id = NULL, "
                        "callback_recovery_case_id = NULL WHERE id = :d"
                    ),
                    {"d": str(dl6.id)},
                )
                await s.commit()
                snap["delivery_owner"]["db_rejects_dropping_owner"] = None
            except Exception as exc:  # noqa: BLE001
                await s.rollback()
                snap["delivery_owner"]["db_rejects_dropping_owner"] = _err(exc)

        # ═══ 场景 7：quarantined incoming 不可建 application ══════════
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            qdl = await repo.record_delivery(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                room_id=room6_id,
                generation=6,
                route_credential_id=uuid.uuid4(),
                callback_status=6,
                delivery_key=compute_delivery_key(
                    room_id=room6_id,
                    generation=6,
                    callback_status=6,
                    discriminator="quarantined",
                ),
            )
            qart = await repo.register_artifact(
                project_id=p,
                wp_id=wp,
                kind=ArtifactKind.incoming,
                state=ArtifactState.quarantined,
                relative_path=f"{base_path}/.incoming/{wp}/{qdl.id}/artifact.xlsx",
                sha256=_d("quarantined-incoming"),
                size_bytes=1234,
                document_type="xlsx",
                source_delivery_id=qdl.id,
            )
            await s.commit()
            # 判据必须落在**异常类型**上：只断言「抛了某个异常」时，把 quarantine 专属
            # 分支短路后，「尚未 durable」的暂态分支会抛同类异常把它遮蔽（变异 GREEN）。
            try:
                await repo.assert_incoming_durable(qart.id)
                snap["quarantined"]["repo_error"] = None
                snap["quarantined"]["repo_error_type"] = None
            except SyncDomainError as exc:
                snap["quarantined"]["repo_error"] = _err(exc)
                snap["quarantined"]["repo_error_type"] = type(exc).__name__
            snap["quarantined"]["durable_at_is_null"] = qart.durable_at is None
            # 正控制：staged（尚未 durable）必须是**另一种**错误类型（暂态 ≠ 隔离终态）
            staged_dl = await repo.record_delivery(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                room_id=room6_id,
                generation=6,
                route_credential_id=uuid.uuid4(),
                callback_status=6,
                delivery_key=compute_delivery_key(
                    room_id=room6_id, generation=6, callback_status=6, discriminator="staged"
                ),
            )
            staged_art = await repo.register_artifact(
                project_id=p,
                wp_id=wp,
                kind=ArtifactKind.incoming,
                state=ArtifactState.staged,
                relative_path=f"{base_path}/.incoming/{wp}/{staged_dl.id}/artifact.xlsx",
                sha256=_d("staged-incoming"),
                size_bytes=999,
                document_type="xlsx",
                source_delivery_id=staged_dl.id,
            )
            await s.commit()
            try:
                await repo.assert_incoming_durable(staged_art.id)
                snap["quarantined"]["staged_error_type"] = None
            except SyncDomainError as exc:
                snap["quarantined"]["staged_error_type"] = type(exc).__name__
        async with Session() as s:
            try:
                await s.execute(
                    sa.text(
                        "UPDATE working_paper_artifact SET state = 'durable', "
                        "durable_at = now(), quarantined_at = NULL WHERE id = :a"
                    ),
                    {"a": str(qart.id)},
                )
                await s.commit()
                snap["quarantined"]["db_release_error"] = None
            except Exception as exc:  # noqa: BLE001
                await s.rollback()
                snap["quarantined"]["db_release_error"] = _err(exc)

        # ═══ 场景 8：scope tombstone 不可删 / 不可复用 ════════════════
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            probe_id = str(uuid.uuid4())
            await repo.register_scope(
                resource_kind=ScopeResourceKind.sync_conflict,
                resource_id=probe_id,
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
            )
            await repo.retire_scope(
                resource_kind=ScopeResourceKind.sync_conflict, resource_id=probe_id
            )
            await s.commit()
            snap["scope_tombstone"]["resolve_after_retire"] = (
                await repo.resolve_scope(
                    resource_kind=ScopeResourceKind.sync_conflict, resource_id=probe_id
                )
            ) is None
            try:
                await repo.register_scope(
                    resource_kind=ScopeResourceKind.sync_conflict,
                    resource_id=probe_id,
                    project_id=p,
                    wp_id=wp,
                    entry_id=ENTRY,
                )
                snap["scope_tombstone"]["reuse_error"] = None
            except ScopeIntegrityError as exc:
                snap["scope_tombstone"]["reuse_error"] = _err(exc)
            await s.rollback()
            try:
                await repo.delete_scope(
                    resource_kind=ScopeResourceKind.sync_conflict, resource_id=probe_id
                )
                snap["scope_tombstone"]["repo_delete_error"] = None
            except ScopeIntegrityError as exc:
                snap["scope_tombstone"]["repo_delete_error"] = _err(exc)
            try:
                await repo.clear_scope_tombstone(
                    resource_kind=ScopeResourceKind.sync_conflict, resource_id=probe_id
                )
                snap["scope_tombstone"]["repo_clear_error"] = None
            except ScopeIntegrityError as exc:
                snap["scope_tombstone"]["repo_clear_error"] = _err(exc)
        for label, sql in (
            (
                "db_delete_error",
                "DELETE FROM working_paper_sync_scope_index WHERE resource_id = :r",
            ),
            (
                "db_clear_error",
                "UPDATE working_paper_sync_scope_index SET retired_at = NULL WHERE resource_id = :r",
            ),
            (
                "db_cross_scope_error",
                "UPDATE working_paper_sync_scope_index SET entry_id = 'other' WHERE resource_id = :r",
            ),
        ):
            async with Session() as s:
                try:
                    await s.execute(sa.text(sql), {"r": probe_id})
                    await s.commit()
                    snap["scope_tombstone"][label] = None
                except Exception as exc:  # noqa: BLE001
                    await s.rollback()
                    snap["scope_tombstone"][label] = _err(exc)

        # ═══ 场景 9：两个 wp 相同 numeric revision，opaque UUID 无碰撞 ══
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            cv_a = await repo.create_content_version(
                project_id=p,
                wp_id=ids["wp_a"],
                entry_id=ENTRY,
                revision=1,
                source="html",
                projection_artifact_id=world["proj_art"].id,
                projection_sha256=world["proj_art"].sha256,
            )
            art_b = await repo.register_artifact(
                project_id=p,
                wp_id=ids["wp_b"],
                kind=ArtifactKind.projection,
                state=ArtifactState.published,
                relative_path=f"{base_path}/.versions/{ids['wp_b']}/projections/v1.json.gz",
                sha256=_d("projection-wp-b"),
                size_bytes=2048,
                document_type="json.gz",
            )
            cv_b = await repo.create_content_version(
                project_id=p,
                wp_id=ids["wp_b"],
                entry_id=ENTRY,
                revision=1,
                source="html",
                projection_artifact_id=art_b.id,
                projection_sha256=art_b.sha256,
            )
            await s.commit()
            scope_a = await repo.resolve_scope(
                resource_kind=ScopeResourceKind.content_version, resource_id=str(cv_a.id)
            )
            scope_b = await repo.resolve_scope(
                resource_kind=ScopeResourceKind.content_version, resource_id=str(cv_b.id)
            )
            snap["numeric_revision"] = {
                "both_revision_1": int(cv_a.revision) == 1 and int(cv_b.revision) == 1,
                "distinct_opaque_ids": cv_a.id != cv_b.id,
                "scope_a_wp": str(scope_a.wp_id) if scope_a else None,
                "scope_b_wp": str(scope_b.wp_id) if scope_b else None,
                "expected_a_wp": str(ids["wp_a"]),
                "expected_b_wp": str(ids["wp_b"]),
            }
            # 🔴 探针 kind 刻意**不用** content_version：那个 kind 还有一条「resource_id
            # 必须是 UUID」的校验，会把 opaque 校验遮蔽成不可达分支（变异实测 GREEN）。
            try:
                await repo.register_scope(
                    resource_kind=ScopeResourceKind.sync_conflict,
                    resource_id="1",
                    project_id=p,
                    wp_id=ids["wp_a"],
                    entry_id=ENTRY,
                )
                snap["numeric_revision"]["numeric_scope_error"] = None
                snap["numeric_revision"]["numeric_scope_error_type"] = None
            except SyncDomainError as exc:
                snap["numeric_revision"]["numeric_scope_error"] = _err(exc)
                snap["numeric_revision"]["numeric_scope_error_type"] = type(exc).__name__
            await s.rollback()
        # DB 侧同一判据（repository 与 CHECK 双向）：裸 INSERT 数字 resource_id 必被拒
        async with Session() as s:
            try:
                await s.execute(
                    sa.text(
                        "INSERT INTO working_paper_sync_scope_index "
                        "(resource_kind, resource_id, project_id, wp_id, entry_id) "
                        "VALUES ('sync_conflict', '1', :p, :w, :e)"
                    ),
                    {"p": str(p), "w": str(ids["wp_a"]), "e": ENTRY},
                )
                await s.commit()
                snap["numeric_revision"]["db_numeric_scope_error"] = None
            except Exception as exc:  # noqa: BLE001
                await s.rollback()
                snap["numeric_revision"]["db_numeric_scope_error"] = _err(exc)

        # ═══ 场景 10：close intent / leader / successor / no-successor ══
        async def _capture_count(s: Any, room_id: uuid.UUID) -> int:
            return int(
                (
                    await s.execute(
                        sa.select(sa.func.count())
                        .select_from(WorkpaperForcesaveRequest)
                        .where(
                            WorkpaperForcesaveRequest.room_id == room_id,
                            WorkpaperForcesaveRequest.kind == "close_capture",
                        )
                    )
                ).scalar_one()
            )

        async def _close_case(
            name: str,
            *,
            generation: int,
            users: tuple[str, ...],
            script,
        ) -> None:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                ctx = await _make_room(s, repo, generation=generation, users=users)
                await s.commit()
                result = await script(s, repo, ctx)
                await s.commit()
                room_row = await repo.lock_room(ctx["room"].id)
                intents = (
                    (
                        await s.execute(
                            sa.select(WorkpaperOoCloseIntent).where(
                                WorkpaperOoCloseIntent.room_id == ctx["room"].id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                events = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperOoCloseIntentEvent)
                            .where(
                                WorkpaperOoCloseIntentEvent.intent_id.in_(
                                    [i.id for i in intents]
                                )
                            )
                        )
                    ).scalar_one()
                )
                snap["close"][name] = {
                    "captures": await _capture_count(s, ctx["room"].id),
                    "room_state": room_row.state,
                    "room_superseded": room_row.superseded_at is not None,
                    "leader_intent": str(room_row.close_leader_intent_id)
                    if room_row.close_leader_intent_id
                    else None,
                    "eligibility_epoch": int(room_row.close_leader_eligibility_epoch),
                    "intent_states": sorted(i.state for i in intents),
                    "promoted_pairs": sum(
                        1 for i in intents if i.promoted_request_id is not None
                    ),
                    "event_count": events,
                    **(result or {}),
                }
                await s.commit()

        async def _reconcile(repo: WorkpaperSyncRepository, room_id: uuid.UUID) -> Any:
            return await repo.reconcile_close_intents(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                room_id=room_id,
                adapter_build_digest=adapter_digest,
                contributor_snapshot_digest=contrib_digest,
            )

        async def _single_close(s, repo, ctx):
            await repo.create_close_intent(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                room_id=ctx["room"].id,
                participant_id=ctx["participants"]["user_a"].id,
                client_confirmation_id=ctx["confirmations"]["user_a"].id,
                actor_id=ids["user_a"],
            )
            first = await _reconcile(repo, ctx["room"].id)
            second = await _reconcile(repo, ctx["room"].id)
            return {
                "first_capture_created": first.capture_created,
                "second_capture_created": second.capture_created,
                "reentrant_same_leader": first.leader_intent_id == second.leader_intent_id,
            }

        await _close_case("single", generation=10, users=("user_a",), script=_single_close)

        def _two_user_close(order: tuple[str, str]):
            async def _script(s, repo, ctx):
                for u in order:
                    await repo.create_close_intent(
                        project_id=p,
                        wp_id=wp,
                        entry_id=ENTRY,
                        room_id=ctx["room"].id,
                        participant_id=ctx["participants"][u].id,
                        client_confirmation_id=ctx["confirmations"][u].id,
                        actor_id=ids[u],
                    )
                    await _reconcile(repo, ctx["room"].id)
                again = await _reconcile(repo, ctx["room"].id)
                return {"reentrant_capture_created": again.capture_created}

            return _script

        await _close_case(
            "order_ab", generation=11, users=("user_a", "user_b"),
            script=_two_user_close(("user_a", "user_b")),
        )
        await _close_case(
            "order_ba", generation=12, users=("user_a", "user_b"),
            script=_two_user_close(("user_b", "user_a")),
        )

        def _ordinary_then_close(terminal_before: bool):
            async def _script(s, repo, ctx):
                room = ctx["room"]
                out = await _freeze(
                    repo,
                    room=room,
                    conf=ctx["confirmations"]["user_a"],
                    participant=ctx["participants"]["user_a"],
                    key="ORD",
                )
                if terminal_before:
                    out.request.state = RequestState.terminal.value
                    await s.flush()
                for u in ("user_a", "user_b"):
                    await repo.create_close_intent(
                        project_id=p,
                        wp_id=wp,
                        entry_id=ENTRY,
                        room_id=room.id,
                        participant_id=ctx["participants"][u].id,
                        client_confirmation_id=ctx["confirmations"][u].id,
                        actor_id=ids[u],
                    )
                mid = await _reconcile(repo, room.id)
                if not terminal_before:
                    out.request.state = RequestState.terminal.value
                    await s.flush()
                final = await _reconcile(repo, room.id)
                return {
                    "captures_before_predecessor_terminal": 0 if not terminal_before else 1,
                    "mid_capture_created": mid.capture_created,
                    "final_capture_created": final.capture_created,
                }

            return _script

        await _close_case(
            "ordinary_terminal_before",
            generation=13,
            users=("user_a", "user_b"),
            script=_ordinary_then_close(True),
        )
        await _close_case(
            "ordinary_terminal_after",
            generation=14,
            users=("user_a", "user_b"),
            script=_ordinary_then_close(False),
        )

        async def _leader_revoked_with_successor(s, repo, ctx):
            room = ctx["room"]
            for u in ("user_a", "user_b"):
                await repo.create_close_intent(
                    project_id=p,
                    wp_id=wp,
                    entry_id=ENTRY,
                    room_id=room.id,
                    participant_id=ctx["participants"][u].id,
                    client_confirmation_id=ctx["confirmations"][u].id,
                    actor_id=ids[u],
                )
            # 让 leader 选出来但不 promote：留一个 active participant
            extra = await repo.create_participant(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                room_id=room.id,
                user_id=ids["user_c"],
                mode="edit",
                permission_epoch=1,
                lease_token_hash=_d("lease-extra"),
            )
            first = await _reconcile(repo, room.id)
            repeat = await _reconcile(repo, room.id)
            all_intents = (
                (
                    await s.execute(
                        sa.select(WorkpaperOoCloseIntent).where(
                            WorkpaperOoCloseIntent.room_id == room.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            # 🔴 独立复算 comparator：leader 必须是**最高** `(intent_sequence, id)`。
            # 缺这条断言时，把 max 改成 min 的变异不会被抓到（两条 intent 谁当 leader
            # 都会走同一条 stale→successor 路径，实测判 GREEN）。
            expected_leader = max(
                all_intents, key=lambda i: (int(i.intent_sequence), str(i.id))
            )
            leader_is_highest = str(first.leader_intent_id) == str(expected_leader.id)
            leader_intent = (
                await s.execute(
                    sa.select(WorkpaperOoCloseIntent).where(
                        WorkpaperOoCloseIntent.id == first.leader_intent_id
                    )
                )
            ).scalar_one()
            # 撤销 leader 的 participant（promotion 前失去资格）
            revoked = (
                await s.execute(
                    sa.select(WorkpaperOoParticipant).where(
                        WorkpaperOoParticipant.id == leader_intent.participant_id
                    )
                )
            ).scalar_one()
            revoked.state = ParticipantState.revoked.value
            revoked.revoked_at = sa.func.now()
            extra.state = ParticipantState.left.value
            extra.left_at = sa.func.now()
            await s.flush()
            after = await _reconcile(repo, room.id)
            return {
                "leader_is_highest_sequence": leader_is_highest,
                "same_snapshot_same_leader": first.leader_intent_id == repeat.leader_intent_id,
                "same_snapshot_no_new_event": repeat.capture_created is False,
                "stale_recorded": [str(i) for i in after.authorization_stale_intent_ids],
                "successor_differs": after.leader_intent_id != first.leader_intent_id,
                "successor_capture_created": after.capture_created,
                "eligibility_bumped": after.eligibility_epoch > first.eligibility_epoch,
                "no_successor": after.no_successor,
            }

        await _close_case(
            "leader_revoked_successor",
            generation=15,
            users=("user_a", "user_b"),
            script=_leader_revoked_with_successor,
        )

        async def _no_successor(s, repo, ctx):
            room = ctx["room"]
            await repo.create_close_intent(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                room_id=room.id,
                participant_id=ctx["participants"]["user_a"].id,
                client_confirmation_id=ctx["confirmations"]["user_a"].id,
                actor_id=ids["user_a"],
            )
            part = (
                await s.execute(
                    sa.select(WorkpaperOoParticipant).where(
                        WorkpaperOoParticipant.id == ctx["participants"]["user_a"].id
                    )
                )
            ).scalar_one()
            part.state = ParticipantState.revoked.value
            part.revoked_at = sa.func.now()
            await s.flush()
            first = await _reconcile(repo, room.id)
            second = await _reconcile(repo, room.id)
            return {
                "no_successor": first.no_successor,
                "capture_created": first.capture_created,
                "reentrant_capture_created": second.capture_created,
                "reentrant_no_successor": second.no_successor,
            }

        await _close_case(
            "no_successor", generation=16, users=("user_a",), script=_no_successor
        )

        # ═══ 场景 11：recovery claim 并发幂等 / download-only / fence ══
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            r17 = await _make_room(s, repo, generation=17, users=("user_a",))
            room17 = r17["room"]
            room17_id = room17.id
            conf17 = r17["confirmations"]["user_a"]
            part17 = r17["participants"]["user_a"]
            conf17_id = conf17.id
            part17_id = part17.id
            dl17, art17 = await _durable_incoming(
                repo,
                room=room17,
                status=2,
                discriminator="crash-close",
                payload_label="recovery-incoming",
            )
            case = await repo.create_recovery_case(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                room_id=room17_id,
                generation=17,
                source_delivery_key=dl17.delivery_key,
                incoming_artifact_id=art17.id,
                reason=RecoveryReason.crash_close,
                ttl=timedelta(days=7),
            )
            case_id_17 = case.id
            await repo.bind_delivery_to_recovery(
                delivery_id=dl17.id, incoming_artifact_id=art17.id, recovery_case_id=case_id_17
            )
            await s.commit()
            snap["recovery"]["pre_claim_zero_entities"] = {
                "request": case.recovery_request_id,
                "application": case.application_id,
                "operation": case.operation_id,
                "state": case.state,
            }
            dl17_key = dl17.delivery_key
            art17_id = art17.id
        # 负控制：durable fact 是 immutable —— 已归 recovery 的 delivery 不得改归属。
        # 单独开 session：本场景以 rollback 结束，若与上面共用会把 case 实例 expire 掉。
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            other_case = await repo.create_recovery_case(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                room_id=room17_id,
                generation=17,
                source_delivery_key=_d("other-delivery-key"),
                incoming_artifact_id=art17_id,
                reason=RecoveryReason.ambiguous_close,
            )
            try:
                await repo.bind_delivery_to_recovery(
                    delivery_id=dl17.id,
                    incoming_artifact_id=art17_id,
                    recovery_case_id=other_case.id,
                )
                snap["recovery"]["rebind_durable_delivery_type"] = None
            except SyncDomainError as exc:
                snap["recovery"]["rebind_durable_delivery_type"] = type(exc).__name__
            await s.rollback()
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            _ = dl17_key
            snap["recovery"]["pre_claim_operation_rows"] = int(
                (
                    await s.execute(
                        sa.select(sa.func.count())
                        .select_from(WorkpaperSyncOperation)
                        .where(WorkpaperSyncOperation.room_id == room17_id)
                    )
                ).scalar_one()
            )

        async def _claim_once() -> str | None:
            async with Session() as s2:
                repo2 = WorkpaperSyncRepository(s2)
                try:
                    await repo2.claim_recovery_case(
                        case_id=case_id_17,
                        claiming_participant_id=part17_id,
                        prior_confirmation_id=conf17_id,
                        idempotency_key="CLAIM-1",
                        current_revision=0,
                        adapter_id="g7.disclosure.listed",
                        adapter_build_digest=adapter_digest,
                        contributor_snapshot_digest=contrib_digest,
                        actor_id=ids["user_a"],
                    )
                    await s2.commit()
                    return None
                except Exception as exc:  # noqa: BLE001
                    await s2.rollback()
                    return _err(exc)

        claim_errors = await asyncio.gather(_claim_once(), _claim_once())
        async with Session() as s:
            case_row = (
                await s.execute(
                    sa.select(WorkpaperCallbackRecoveryCase).where(
                        WorkpaperCallbackRecoveryCase.id == case_id_17
                    )
                )
            ).scalar_one()
            snap["recovery"]["concurrent_claims"] = {
                "errors": [e for e in claim_errors if e],
                "state": case_row.state,
                "requests": int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperForcesaveRequest)
                            .where(
                                WorkpaperForcesaveRequest.room_id == room17_id,
                                WorkpaperForcesaveRequest.kind == "recovery_claim",
                            )
                        )
                    ).scalar_one()
                ),
                "operations": int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperSyncOperation)
                            .where(WorkpaperSyncOperation.room_id == room17_id)
                        )
                    ).scalar_one()
                ),
                "applications": int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperContentApplication)
                            .where(WorkpaperContentApplication.room_id == room17_id)
                        )
                    ).scalar_one()
                ),
                "all_three_bound": all(
                    v is not None
                    for v in (
                        case_row.recovery_request_id,
                        case_row.application_id,
                        case_row.operation_id,
                    )
                ),
            }

        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            r18 = await _make_room(s, repo, generation=18, users=("user_a",))
            room18 = r18["room"]
            room18_id = room18.id
            dl18, art18 = await _durable_incoming(
                repo,
                room=room18,
                status=2,
                discriminator="download-only",
                payload_label="download-only-incoming",
            )
            case18 = await repo.create_recovery_case(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                room_id=room18_id,
                generation=18,
                source_delivery_key=dl18.delivery_key,
                incoming_artifact_id=art18.id,
                reason=RecoveryReason.missing_request,
            )
            await repo.bind_delivery_to_recovery(
                delivery_id=dl18.id, incoming_artifact_id=art18.id, recovery_case_id=case18.id
            )
            await repo.terminate_recovery_download_only(
                case_id=case18.id, actor_id=ids["user_a"]
            )
            await s.commit()
            snap["recovery"]["download_only"] = {
                "state": case18.state,
                "request": case18.recovery_request_id,
                "application": case18.application_id,
                "operation": case18.operation_id,
                "operations_in_room": int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperSyncOperation)
                            .where(WorkpaperSyncOperation.room_id == room18_id)
                        )
                    ).scalar_one()
                ),
            }

        # 负控制：已 claim（三实体齐备）的 case 不得转 download-only。
        # 判据落在**异常类型**上：只断言「抛了异常」时，状态边校验会抛
        # StateTransitionError 把「零三实体」这条判据遮蔽成不可达分支（变异实测 GREEN）。
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            try:
                await repo.terminate_recovery_download_only(
                    case_id=case_id_17, actor_id=ids["user_a"]
                )
                snap["recovery"]["download_only_on_claimed_type"] = None
            except SyncDomainError as exc:
                snap["recovery"]["download_only_on_claimed_type"] = type(exc).__name__
            await s.rollback()

        # 最终 authorization fence：write fence 提升后 claim 必须零三实体
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            r19 = await _make_room(s, repo, generation=19, users=("user_a",))
            room19 = r19["room"]
            room19_id = room19.id
            conf19 = r19["confirmations"]["user_a"]
            part19 = r19["participants"]["user_a"]
            conf19_id = conf19.id
            part19_id = part19.id
            dl19, art19 = await _durable_incoming(
                repo,
                room=room19,
                status=2,
                discriminator="fence-stale",
                payload_label="fence-incoming",
            )
            case19 = await repo.create_recovery_case(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                room_id=room19_id,
                generation=19,
                source_delivery_key=dl19.delivery_key,
                incoming_artifact_id=art19.id,
                reason=RecoveryReason.ambiguous_close,
            )
            case19_id = case19.id
            room_row = await repo.lock_room(room19_id)
            room_row.write_fence_epoch = int(room_row.write_fence_epoch) + 1
            await s.flush()
            await s.commit()
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            try:
                await repo.claim_recovery_case(
                    case_id=case19_id,
                    claiming_participant_id=part19_id,
                    prior_confirmation_id=conf19_id,
                    idempotency_key="CLAIM-FENCE",
                    current_revision=0,
                    adapter_id="g7.disclosure.listed",
                    adapter_build_digest=adapter_digest,
                    contributor_snapshot_digest=contrib_digest,
                    actor_id=ids["user_a"],
                )
                snap["recovery"]["fence_error"] = None
            except ScopeIntegrityError as exc:
                snap["recovery"]["fence_error"] = _err(exc)
            # 故意 commit：若失败前已建三实体，这里会把它们持久化 ⇒ 下面计数打红
            await s.commit()
        async with Session() as s:
            snap["recovery"]["fence_zero_entities"] = {
                "requests": int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperForcesaveRequest)
                            .where(WorkpaperForcesaveRequest.room_id == room19_id)
                        )
                    ).scalar_one()
                ),
                "operations": int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperSyncOperation)
                            .where(WorkpaperSyncOperation.room_id == room19_id)
                        )
                    ).scalar_one()
                ),
                "applications": int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperContentApplication)
                            .where(WorkpaperContentApplication.room_id == room19_id)
                        )
                    ).scalar_one()
                ),
            }

        # ═══ 场景 12：同 wp 串行 / 跨 wp 并行 / revision 乐观锁 ═══════
        s_hold = Session()
        repo_hold = WorkpaperSyncRepository(s_hold)
        await repo_hold.lock_workpaper(ids["wp_a"])
        async with Session() as s_probe:
            probe = WorkpaperSyncRepository(s_probe)
            snap["locks"]["same_wp_blocked"] = not await probe.try_lock_workpaper(
                ids["wp_a"]
            )
            snap["locks"]["cross_wp_parallel"] = await probe.try_lock_workpaper(
                ids["wp_b"]
            )
            await s_probe.rollback()
        await s_hold.rollback()
        await s_hold.close()
        async with Session() as s_probe:
            probe = WorkpaperSyncRepository(s_probe)
            snap["locks"]["released_after_rollback"] = await probe.try_lock_workpaper(
                ids["wp_a"]
            )
            await s_probe.rollback()

        s1 = Session()
        s2 = Session()
        r1 = WorkpaperSyncRepository(s1)
        r2 = WorkpaperSyncRepository(s2)
        before = int(
            (
                await s1.execute(
                    sa.text("SELECT content_revision FROM working_paper WHERE id = :w"),
                    {"w": str(ids["wp_b"])},
                )
            ).scalar_one()
        )
        await r1.lock_workpaper(ids["wp_b"])
        first_new = await r1.bump_content_revision(ids["wp_b"], before)

        async def _second_bump() -> str | None:
            try:
                await r2.lock_workpaper(ids["wp_b"])
                await r2.bump_content_revision(ids["wp_b"], before)
                await s2.commit()
                return None
            except RevisionConflictError as exc:
                await s2.rollback()
                return _err(exc)

        task = asyncio.create_task(_second_bump())
        await asyncio.sleep(0.3)
        await s1.commit()
        second_err = await task
        await s1.close()
        await s2.close()
        async with Session() as s:
            final = int(
                (
                    await s.execute(
                        sa.text("SELECT content_revision FROM working_paper WHERE id = :w"),
                        {"w": str(ids["wp_b"])},
                    )
                ).scalar_one()
            )
        snap["locks"]["revision_cas"] = {
            "before": before,
            "first_new": first_new,
            "second_error": second_err,
            "final": final,
        }

        # ═══ 场景 13：candidate 不可见 + representation-only 零 revision ══
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            rev_before = int(
                (
                    await s.execute(
                        sa.text("SELECT content_revision FROM working_paper WHERE id = :w"),
                        {"w": str(wp)},
                    )
                ).scalar_one()
            )
            cand_art = await repo.register_artifact(
                project_id=p,
                wp_id=wp,
                kind=ArtifactKind.upgrade_candidate,
                state=ArtifactState.staged,
                relative_path=f"{base_path}/.upgrade-candidates/{wp}/cand.xlsx",
                sha256=_d("candidate-artifact"),
                size_bytes=40960,
                document_type="xlsx",
            )
            cand = await repo.create_upgrade_candidate(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                content_version_id=world["cv0"].id,
                source_representation_id=world["rep1"].id,
                staged_artifact_id=cand_art.id,
                staged_artifact_sha256=cand_art.sha256,
                template_definition_id=world["tpl"].id,
                instrumentation_definition_id=world["instr"].id,
                state=CandidateState.staged,
            )
            await s.commit()
            try:
                await repo.finalize_candidate(
                    candidate_id=cand.id, finalized_representation_id=world["rep1"].id
                )
                snap["candidate"]["finalize_before_ready_error"] = None
            except Exception as exc:  # noqa: BLE001
                snap["candidate"]["finalize_before_ready_error"] = _err(exc)
            await s.rollback()

            # representation-only 升级：新 generation，content revision 不变
            g2_art = await repo.register_artifact(
                project_id=p,
                wp_id=wp,
                kind=ArtifactKind.canonical,
                state=ArtifactState.published,
                relative_path=f"{base_path}/.versions/{wp}/representations/{ENTRY}/g2.xlsx",
                sha256=_d("canonical-g2"),
                size_bytes=40970,
                document_type="xlsx",
            )
            rep2 = await repo.create_representation(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                content_version_id=world["cv0"].id,
                generation=2,
                document_type="xlsx",
                artifact_id=g2_art.id,
                artifact_sha256=g2_art.sha256,
                definition_bundle_id=world["bundle"].id,
                authority_model_definition_id=world["authority"].id,
                adapter_id="g7.disclosure.listed",
                adapter_build_digest=_d("adapter-build"),
                structure_hash=_d("structure-v2"),
                identity_inventory_sha256=_d("identity-inventory-v2"),
                reason="definition_upgrade",
                parent_representation_id=world["rep1"].id,
            )
            await repo.set_entry_pointer(
                wp_id=wp, entry_id=ENTRY, representation_id=rep2.id, generation=2
            )
            await s.commit()
            rev_after = int(
                (
                    await s.execute(
                        sa.text("SELECT content_revision FROM working_paper WHERE id = :w"),
                        {"w": str(wp)},
                    )
                ).scalar_one()
            )
            snap["candidate"]["revision_before"] = rev_before
            snap["candidate"]["revision_after_representation_upgrade"] = rev_after

        # 负控制：candidate（未 approved）bundle 不得 finalize representation
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            cand_defs = await _defs_candidate_bundle(repo)
            try:
                await repo.create_representation(
                    project_id=p,
                    wp_id=wp,
                    entry_id=ENTRY,
                    content_version_id=world["cv0"].id,
                    generation=9,
                    document_type="xlsx",
                    artifact_id=world["canon_g1"].id,
                    artifact_sha256=world["canon_g1"].sha256,
                    definition_bundle_id=cand_defs["bundle"].id,
                    authority_model_definition_id=cand_defs["authority"].id,
                    adapter_id="g7.disclosure.listed",
                    adapter_build_digest=_d("adapter-build"),
                    structure_hash=_d("structure-cand"),
                    identity_inventory_sha256=_d("identity-cand"),
                    reason="definition_upgrade",
                )
                snap["candidate"]["unapproved_bundle_error_type"] = None
            except SyncDomainError as exc:
                snap["candidate"]["unapproved_bundle_error_type"] = type(exc).__name__
            await s.rollback()

        # entry pointer 不得指向未 published 的 artifact（candidate/staged）
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            staged_art = await repo.register_artifact(
                project_id=p,
                wp_id=wp,
                kind=ArtifactKind.canonical,
                state=ArtifactState.staged,
                relative_path=f"{base_path}/.staging/{wp}/g3.xlsx",
                sha256=_d("canonical-g3-staged"),
                size_bytes=40980,
                document_type="xlsx",
            )
            rep3 = await repo.create_representation(
                project_id=p,
                wp_id=wp,
                entry_id=ENTRY,
                content_version_id=world["cv0"].id,
                generation=3,
                document_type="xlsx",
                artifact_id=staged_art.id,
                artifact_sha256=staged_art.sha256,
                definition_bundle_id=world["bundle"].id,
                authority_model_definition_id=world["authority"].id,
                adapter_id="g7.disclosure.listed",
                adapter_build_digest=_d("adapter-build"),
                structure_hash=_d("structure-v3"),
                identity_inventory_sha256=_d("identity-inventory-v3"),
                reason="definition_upgrade",
            )
            try:
                await repo.set_entry_pointer(
                    wp_id=wp, entry_id=ENTRY, representation_id=rep3.id, generation=3
                )
                await s.commit()
                snap["candidate"]["pointer_to_unpublished_error"] = None
            except Exception as exc:  # noqa: BLE001
                await s.rollback()
                snap["candidate"]["pointer_to_unpublished_error"] = _err(exc)
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await admin.dispose()
    return snap


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


# ═══════════════════════════════════════════════════════════════════════════
# A. harness 自证
# ═══════════════════════════════════════════════════════════════════════════


def test_ran_on_real_postgresql_in_scratch_schema(snap: dict[str, Any]) -> None:
    assert "PostgreSQL" in (snap["server_version"] or ""), snap["server_version"]
    assert snap["schema"].startswith(_SCHEMA_PREFIX)
    assert snap["apply_errors"] == [], snap["apply_errors"]


def test_operation_table_has_no_application_key_column(snap: dict[str, Any]) -> None:
    """Property 64（DB 侧）：application_key 只存在于 application 表。"""
    assert "application_key" not in snap["introspection"]["operation_columns"]
    assert snap["introspection"]["application_key_holders"] == [
        "working_paper_content_application"
    ]


# ═══════════════════════════════════════════════════════════════════════════
# B. Property 5：repository 只 flush 不 commit
# ═══════════════════════════════════════════════════════════════════════════


def test_property_5_repository_only_flushes(snap: dict[str, Any]) -> None:
    """Property 5：repository 不持有事务边界 —— rollback 后库里零行（含 scope row）。"""
    f = snap["flush_only"]
    assert f["rows_after_rollback"] == 0, (
        "repository 自己 commit 了：rollback 后仍能查到 revision=900 的 content version"
    )
    # 判据是「rollback 前后 scope 行数不变」而不是某个写死的数字：
    # 写死数字会随场景增删漂移，是「把错值当基线锁死」的入口。
    assert f["scope_rows_after_rollback"] == f["scope_rows_before"], (
        "scope row 必须与 child 同事务 —— rollback 后 scope 行数应与事务前完全一致，"
        f"实得 before={f['scope_rows_before']} after={f['scope_rows_after_rollback']}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# C. Property 64：forcesave 复合幂等键 + fingerprint
# ═══════════════════════════════════════════════════════════════════════════


def test_property_64_forcesave_composite_idempotency(snap: dict[str, Any]) -> None:
    i = snap["idempotency"]
    assert i["cache_hit"] is True and i["same_request_id"] and i["same_operation_id"], (
        "逐项等值重放必须返回同一 request/operation"
    )
    assert i["shell_pre_correlation"] is True, (
        "accepted 前 shell 必须 application_id=NULL 且 duplicate_of=NULL"
    )
    for label in ("diff_fingerprint", "cross_participant", "cross_kind"):
        assert i[label] is not None, f"{label} 必须 409 冲突，实得放行"
        assert i[f"{label}_status"] == 409, f"{label} 必须映射 HTTP 409"
        assert i[f"{label}_leaks_old_id"] is False, (
            f"{label} 的 409 泄露了旧 request/operation id"
        )


# ═══════════════════════════════════════════════════════════════════════════
# D. Property 18 / 68：N 个 shell → 1 primary + N-1 direct duplicates
# ═══════════════════════════════════════════════════════════════════════════


def test_property_18_n_shells_one_primary_rest_direct_duplicates(
    snap: dict[str, Any]
) -> None:
    n = snap["n_shells"]
    assert n["correlate_errors"] == [], n["correlate_errors"]
    assert n["applications"] == 1, f"同 application key 只能有一个 application，实得 {n['applications']}"
    assert n["primaries"] == 1, f"必须恰一个 primary，实得 {n['primaries']}"
    assert n["duplicates"] == 3, f"必须 N-1=3 个 duplicate，实得 {n['duplicates']}"
    assert n["stranded"] == 0, "零 stranded shell（durable 后不得留 application/duplicate 均空的 shell）"
    assert n["duplicate_targets"] == [n["primary_id"]], (
        f"全部 duplicate 必须直指同一 primary，实得 {n['duplicate_targets']}"
    )
    assert n["duplicate_states"] == ["duplicate"], "duplicate 必为 terminal state"
    assert n["effective_sequence"] == n["max_request_sequence"], (
        "effective_request_sequence 必须 fold 到最大 request sequence"
    )
    assert n["self_superseded"] is False, "同 canonical application 不得 self-supersede"
    assert n["room_durable_application_matches"] is True
    assert n["room_durable_sequence"] == n["effective_sequence"], (
        "room latest durable fence 必须与 canonical application 的 effective sequence 同事务一致"
    )
    assert n["bound_events"] == 1, "primary 必须恰有一条 application_bound event"
    assert n["duplicate_events"] == 3, "每个 duplicate 必须恰有一条 terminal duplicate event"
    assert n["fold_events_have_request_and_fence"] is True
    assert n["deliveries_bound"] == 4, "四条 durable delivery 必须都绑定同一 canonical application"


def test_property_18_sequential_fold_does_not_self_supersede(snap: dict[str, Any]) -> None:
    """same-app 较高 sequence 原子 fold：origin 不变、effective 提升、零 self-supersede。"""
    f = snap["sequential_fold"]
    assert f["same_application"] is True
    assert f["first_shape"] == "primary" and f["second_shape"] == "duplicate"
    assert f["origin_sequence"] == f["low_sequence"], "origin_request_sequence 永不改写"
    assert f["effective_sequence"] == f["high_sequence"], "较高 sequence 必须被 fold 进来"
    assert f["fold_event_count"] == 1, (
        f"恰一条 sequence_folded event（幂等），实得 {f['fold_event_count']}"
    )
    assert f["fold_event_request_is_high"] is True
    assert f["fold_event_room_fence"] == [f["high_sequence"]]
    assert f["self_superseded"] is False
    assert f["room_durable_sequence"] == f["high_sequence"]
    assert f["duplicate_points_to_primary"] is True
    assert f["duplicate_has_no_application"] is True
    assert f["canonical_primary"] is True
    # 负控制：已收敛的 shell 再次 correlate 必须被拒（重复 callback 不得二次绑定）
    assert f["recorrelate_primary_type"] == "DuplicateLinkError", (
        "对 primary 再次 correlate 必须抛 DuplicateLinkError，实得 "
        f"{f['recorrelate_primary_type']}"
    )
    assert f["recorrelate_duplicate_type"] == "DuplicateLinkError", (
        "对 duplicate 再次 correlate 必须抛 DuplicateLinkError，实得 "
        f"{f['recorrelate_duplicate_type']}"
    )


def test_self_supersede_rejected_by_repository_and_database(snap: dict[str, Any]) -> None:
    assert snap["supersede"]["repo_self"] is not None, "repository 必须拒绝 self-supersede"
    assert snap["supersede"]["db_self"] is not None, "数据库 CHECK 必须拒绝 self-supersede"


# ═══════════════════════════════════════════════════════════════════════════
# E. Requirement 5.4：delivery 归属只按 durable_at
# ═══════════════════════════════════════════════════════════════════════════


def test_delivery_ownership_pre_and_post_durable(snap: dict[str, Any]) -> None:
    pre = snap["delivery_owner"]["pre_durable"]
    assert pre["durable_at"] is None
    assert pre["application_id"] is None and pre["recovery_id"] is None, (
        "pre-durable 失败必须零 application/recovery owner"
    )
    assert pre["request_kept"] is True, (
        "pre-durable 允许保留已精确绑定的 request/operation shell（request 与 application 不做 XOR）"
    )
    post = snap["delivery_owner"]["post_durable"]
    assert post["state"] == "error" and post["durable_at_set"] is True
    assert post["keeps_application"] is True, "post-durable error 必须保留既有 application owner"
    assert snap["delivery_owner"]["db_rejects_dropping_owner"] is not None, (
        "数据库必须拒绝 post-durable 丢弃 owner"
    )


# ═══════════════════════════════════════════════════════════════════════════
# F. Requirement 5.6：quarantined incoming
# ═══════════════════════════════════════════════════════════════════════════


def test_quarantined_incoming_cannot_create_application_or_be_released(
    snap: dict[str, Any]
) -> None:
    q = snap["quarantined"]
    assert q["durable_at_is_null"] is True
    assert q["repo_error"] is not None, "repository 必须拒绝 quarantined incoming"
    # 类型判据：quarantine 是永久终态，与「尚未 durable」暂态必须是两个错误类型，
    # 否则短路 quarantine 分支后暂态分支会抛同类异常把判据遮蔽（变异 GREEN）
    assert q["repo_error_type"] == "QuarantinedIncomingError", (
        f"quarantined 必须抛 QuarantinedIncomingError，实得 {q['repo_error_type']}"
    )
    assert q["staged_error_type"] == "IncomingNotDurableError", (
        f"staged（暂态）必须抛 IncomingNotDurableError 而不是隔离终态错误，"
        f"实得 {q['staged_error_type']}"
    )
    assert q["db_release_error"] is not None, "数据库必须拒绝 quarantined → durable"


# ═══════════════════════════════════════════════════════════════════════════
# G. Requirement 10.6：scope tombstone
# ═══════════════════════════════════════════════════════════════════════════


def test_scope_tombstone_is_immortal_and_never_reused(snap: dict[str, Any]) -> None:
    t = snap["scope_tombstone"]
    assert t["resolve_after_retire"] is True, "retired 与不存在必须走同一 404 oracle"
    assert t["reuse_error"] is not None, "retired 的 (kind,id) 不得复用"
    assert t["repo_delete_error"] is not None, "repository 必须拒绝物理删除"
    assert t["repo_clear_error"] is not None, "repository 必须拒绝清空 tombstone"
    assert t["db_delete_error"] is not None, "数据库必须拒绝物理删除"
    assert t["db_clear_error"] is not None, "数据库必须拒绝清空 tombstone"
    assert t["db_cross_scope_error"] is not None, "数据库必须拒绝跨 scope 重绑"


def test_numeric_revision_never_collides_across_workpapers(snap: dict[str, Any]) -> None:
    """Requirement 8.7 / 10.6：两个 wp 的 revision 1 由不同 opaque UUID 定位，零碰撞。"""
    n = snap["numeric_revision"]
    assert n["both_revision_1"] is True and n["distinct_opaque_ids"] is True
    assert n["scope_a_wp"] == n["expected_a_wp"]
    assert n["scope_b_wp"] == n["expected_b_wp"]
    assert n["numeric_scope_error_type"] == "ScopeIntegrityError", (
        "numeric revision 必须由 repository 的 opaque 校验拒绝（不是被别的校验遮蔽），"
        f"实得 {n['numeric_scope_error_type']}"
    )
    assert n["db_numeric_scope_error"] is not None, (
        "数据库 CHECK 必须同样拒绝 numeric resource_id（repository 与 DB 双向）"
    )


# ═══════════════════════════════════════════════════════════════════════════
# H. Property 63 / 68：close-capture exactly-one 与 successor/no-successor
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "case",
    ["single", "order_ab", "order_ba", "ordinary_terminal_before", "ordinary_terminal_after"],
)
def test_property_63_close_capture_exactly_one(snap: dict[str, Any], case: str) -> None:
    """合法资格路径最终**恰一条** close-capture；>1 与 0 都失败（partial unique 只证 at-most-one）。"""
    c = snap["close"][case]
    assert c["captures"] == 1, f"{case}: close-capture 必须恰一条，实得 {c['captures']}"
    assert c["promoted_pairs"] == 1, f"{case}: 必须恰一个 intent 携带 promoted_request_id"
    assert "promoted" in c["intent_states"], f"{case}: 必须有 promoted intent"


def test_property_63_reconciler_is_idempotent(snap: dict[str, Any]) -> None:
    single = snap["close"]["single"]
    assert single["first_capture_created"] is True
    assert single["second_capture_created"] is False, "reconciler 重入不得建第二 capture"
    assert single["reentrant_same_leader"] is True, "同 eligibility snapshot 不得换 leader"
    for case in ("order_ab", "order_ba"):
        assert snap["close"][case]["reentrant_capture_created"] is False


def test_property_63_ordinary_forcesave_barrier(snap: dict[str, Any]) -> None:
    """A 的普通 forcesave terminal 前后 B close，两种交错都最终 exactly-one。"""
    after = snap["close"]["ordinary_terminal_after"]
    assert after["mid_capture_created"] is False, (
        "barrier predecessor 未终结时不得提升 leader"
    )
    assert after["final_capture_created"] is True
    before = snap["close"]["ordinary_terminal_before"]
    assert before["mid_capture_created"] is True


def test_property_63_leader_revoked_selects_successor(snap: dict[str, Any]) -> None:
    c = snap["close"]["leader_revoked_successor"]
    assert c["leader_is_highest_sequence"] is True, (
        "leader 必须是最高 intent_sequence/id —— comparator 是 Requirement 4.10 "
        "规定的确定性规则；缺这条断言时 max→min 的变异抓不到"
    )
    assert c["same_snapshot_same_leader"] is True, "同 eligibility snapshot 重放不得换 leader"
    assert c["same_snapshot_no_new_event"] is True
    assert len(c["stale_recorded"]) == 1, (
        f"leader promotion 前失去资格必须审计为 authorization_stale，实得 {c['stale_recorded']}"
    )
    assert c["successor_differs"] is True and c["successor_capture_created"] is True
    assert c["eligibility_bumped"] is True, "successor 选择必须推进 eligibility epoch"
    assert c["no_successor"] is False
    assert c["captures"] == 1, "有合法 successor 时仍必须 exactly-one capture"
    assert "authorization_stale" in c["intent_states"]


def test_property_63_no_successor_zero_capture_but_explicit_terminal(
    snap: dict[str, Any]
) -> None:
    c = snap["close"]["no_successor"]
    assert c["captures"] == 0, "无合法 successor 时必须零 capture"
    assert c["no_successor"] is True and c["capture_created"] is False
    assert c["room_state"] == "recovery_required", (
        f"无 successor 必须落显式 recovery_required 终态，实得 {c['room_state']}"
    )
    assert c["room_superseded"] is True, "无 successor 必须原子 supersede generation"
    assert c["intent_states"] == ["recovery_required"], (
        f"未终结 intents 必须落 recovery_required（不得永久 retryable_blocked），实得 {c['intent_states']}"
    )
    assert c["reentrant_capture_created"] is False
    assert c["reentrant_no_successor"] is True


# ═══════════════════════════════════════════════════════════════════════════
# I. Requirement 5.8 / Property 43：recovery claim
# ═══════════════════════════════════════════════════════════════════════════


def test_recovery_case_has_zero_entities_before_claim(snap: dict[str, Any]) -> None:
    pre = snap["recovery"]["pre_claim_zero_entities"]
    assert pre["state"] == "unclaimed"
    assert pre["request"] is None and pre["application"] is None and pre["operation"] is None
    assert snap["recovery"]["pre_claim_operation_rows"] == 0, (
        "claim 前不得存在 operation（不得借 operation timeline 伪造 operation）"
    )


def test_recovery_claim_is_concurrent_idempotent(snap: dict[str, Any]) -> None:
    c = snap["recovery"]["concurrent_claims"]
    assert c["errors"] == [], c["errors"]
    assert c["state"] == "application_created"
    assert c["requests"] == 1, f"并发 claim 最多创建一个 recovery_claim request，实得 {c['requests']}"
    assert c["operations"] == 1, f"并发 claim 最多创建一个 operation shell，实得 {c['operations']}"
    assert c["applications"] == 1, f"并发 claim 最多创建/命中一个 application，实得 {c['applications']}"
    assert c["all_three_bound"] is True


def test_download_only_creates_zero_three_entities(snap: dict[str, Any]) -> None:
    d = snap["recovery"]["download_only"]
    assert d["state"] == "download_only"
    assert d["request"] is None and d["application"] is None and d["operation"] is None
    assert d["operations_in_room"] == 0, "download-only 永不创建 operation"
    assert snap["recovery"]["download_only_on_claimed_type"] == "ScopeIntegrityError", (
        "已 claim 的 case 转 download-only 必须由『三实体恒空』校验拒绝"
        "（不是被状态边遮蔽），实得 "
        f"{snap['recovery']['download_only_on_claimed_type']}"
    )
    assert snap["recovery"]["rebind_durable_delivery_type"] == "DeliveryOwnershipError", (
        "已 durable 的 delivery 改归属必须被拒（durable_at immutable），实得 "
        f"{snap['recovery']['rebind_durable_delivery_type']}"
    )


def test_property_43_final_authorization_fence_blocks_claim(snap: dict[str, Any]) -> None:
    """Property 43：write fence 提升后 claim 必须失败，且**零三实体**落库。"""
    assert snap["recovery"]["fence_error"] is not None, "陈旧 write fence 必须阻止 claim"
    z = snap["recovery"]["fence_zero_entities"]
    assert z == {"requests": 0, "operations": 0, "applications": 0}, (
        f"授权 fence 失败后不得留下任何实体，实得 {z}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# J. Property 59：同 wp 串行、跨 wp 并行、乐观锁
# ═══════════════════════════════════════════════════════════════════════════


def test_property_59_same_wp_serial_cross_wp_parallel(snap: dict[str, Any]) -> None:
    lk = snap["locks"]
    assert lk["same_wp_blocked"] is True, (
        "同 wp 的第二个事务必须拿不到 advisory lock（串行化由数据库锁决定）"
    )
    assert lk["cross_wp_parallel"] is True, "不同 wp 必须并行（无全局互斥）"
    assert lk["released_after_rollback"] is True, "事务级 advisory lock 必须随事务结束自动释放"


def test_property_59_revision_optimistic_lock_has_single_winner(snap: dict[str, Any]) -> None:
    cas = snap["locks"]["revision_cas"]
    assert cas["first_new"] == cas["before"] + 1
    assert cas["second_error"] is not None, "并发同 expected revision 的第二个 CAS 必须失败"
    assert cas["final"] == cas["before"] + 1, (
        f"同 wp 无丢更新：最终 revision 必须只 +1，实得 {cas['final']}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# K. Property 4：candidate 不可见 + representation-only 零 revision
# ═══════════════════════════════════════════════════════════════════════════


def test_property_4_representation_upgrade_does_not_bump_revision(
    snap: dict[str, Any]
) -> None:
    c = snap["candidate"]
    assert c["revision_after_representation_upgrade"] == c["revision_before"], (
        "纯 representation generation 升级不得推进 business content revision"
    )


def test_candidate_cannot_finalize_or_become_current(snap: dict[str, Any]) -> None:
    c = snap["candidate"]
    assert c["finalize_before_ready_error"] is not None, (
        "candidate 在 approved contract/bundle 之前不得 finalize"
    )
    assert c["pointer_to_unpublished_error"] is not None, (
        "entry current pointer 不得指向未 published artifact（candidate/staged）"
    )
    assert c["finalize_before_ready_error"].startswith("BundleIntegrityError"), (
        "candidate finalize 必须由『缺 approved contract/bundle』这条语义校验拒绝"
        "（不是被状态边遮蔽），实得 "
        f"{c['finalize_before_ready_error']}"
    )
    assert c["unapproved_bundle_error_type"] == "BundleIntegrityError", (
        "未 approved 的 bundle 不得 finalize representation，实得 "
        f"{c['unapproved_bundle_error_type']}"
    )
