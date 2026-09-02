"""Task 21 真实 PostgreSQL 行为守卫：room 资格门、双基线、fence 提升与撤销旋转。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 21
Requirements: 2.5, 2.6, 2.7, 2.8, 2.9, 4.7, 4.11, 10.2, 10.3, 10.4, 10.9, 10.10
Properties: P6 / P15 / P43 / P44 / P62 / P63

═══ 为什么必须真库 ═══

Task 21 的判据全是「room row lock 内原子决定」的结果：

* fence 提升与 outstanding request 取消必须在同一事务里发生（AC 4.7）；
* 双基线推进是两个独立字段的原子更新，且 `refresh_required` 必须**立刻**让下一次
  forcesave 被拒（AC 2.9 / 4.11）；
* `assert_can_initiate_request` 的八条判据里有五条读的是 DB 行状态（room state /
  participant lease / confirmation / fence / bundle FK），mock 掉就等于没测。

`DATABASE_URL` 非 PostgreSQL 时**直接失败而不是 skip** —— 与 Task 10 同约定：
本任务判据就是数据库行为，skip 等于静默抹掉唯一判据。

═══ 隔离 ═══

scratch schema `tmp_task21_room_<hex>`，`search_path` 只含它；`projects/users/
working_paper` 在 scratch 内建桩表；结束 `DROP SCHEMA CASCADE`。

═══ 采集写法 ═══

全部场景由**一次 `asyncio.run`** 跑完落进快照（module fixture）。不给每个测试各自开
async —— 共享连接池会被污染，第二个测试起 `NoneType has no attribute send`
（memory 已记录该坑）。
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

_SCHEMA_PREFIX = "tmp_task21_room_"

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


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _opt(value: object) -> str | None:
    """把可空 UUID 投影成 `str | None`。

    存在的理由很具体：`str(None) == "None"` 是真值，用它做 `all(...)` 判空会把
    「字段根本没写上」判成「写上了」。Task 21 首轮变异实测有一条（仓储侧短路 client
    基线首个赋值）就是靠这个投影 bug 蒙过守卫的。
    """
    return None if value is None else str(value)


async def _collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部 room 场景
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.workpaper_sync_models import (
        WorkpaperContentRepresentation,
        WorkpaperForcesaveRequest,
        WorkpaperOoClientConfirmation,
        WorkpaperOoParticipant,
        WorkpaperOoRoom,
        WorkpaperSyncOperationContributor,
    )
    from app.services.workpaper_sync.models import (
        ArtifactKind,
        ArtifactState,
        BundleSlot,
        BundleSlotSpec,
        ParticipantMode,
        ParticipantState,
        RequestKind,
        RequestState,
        RoomState,
        SyncDomainError,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.rooms import (
        BundleIdentityDriftError,
        ClientBaselineMissingError,
        DescriptorNotConfirmedError,
        ParticipantNotWritableError,
        RoomNotWritableError,
        RoomScope,
        RoomService,
        WriteFenceStaleError,
        assert_route_credential,
        derive_doc_key,
        mint_route_credential,
    )

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 21 的判据是 room row lock 内的原子决定（fence 提升 + outstanding "
            "request 取消 + 双基线推进），必须真实 PostgreSQL；当前 DATABASE_URL 为 "
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
        "open_room": {},
        "lease": {},
        "eligibility": {},
        "freeze": {},
        "baselines": {},
        "revoke": {},
        "supersede": {},
        "flush_only": {},
    }
    #: 每个采集阶段的异常都记进这里，**不允许**穿透 `_collect()`。
    #
    # 🔴 为什么必须这样：异常穿透会把整个 module 变成 collection ERROR，而 pytest 的
    # `-rf` 只列 FAILED 不列 ERROR ⇒ 变异检验看不到任何「预期失败项」⇒ 判 GREEN。
    # Task 21 首轮变异实测有四条（room-state 分支、barrier 分支、open-or-reuse 复用、
    # 仓储侧 client 基线赋值）正是这样隐身的：它们把某个 happy-path 阶段打崩，于是
    # 34 个断言全部变成 ERROR，报告里却显示「守卫没拦住」。
    snap["harness_errors"] = {}

    def _phase_failed(name: str, exc: BaseException) -> None:
        snap["harness_errors"][name] = _err(exc)

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

        ids = {
            "project": uuid.uuid4(),
            "user_a": uuid.uuid4(),
            "user_b": uuid.uuid4(),
            "user_v": uuid.uuid4(),
            "user_late": uuid.uuid4(),
            "user_other": uuid.uuid4(),
            "wp": uuid.uuid4(),
        }
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                f"INSERT INTO projects (id) VALUES ('{ids['project']}')"
            )
            for u in ("user_a", "user_b", "user_v", "user_late", "user_other"):
                await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{ids[u]}')")
            await conn.exec_driver_sql(
                "INSERT INTO working_paper (id, project_id) VALUES "
                f"('{ids['wp']}', '{ids['project']}')"
            )

        project_id, wp_id = ids["project"], ids["wp"]
        scope = RoomScope(project_id=project_id, wp_id=wp_id, entry_id=ENTRY)
        base_path = f"storage/{project_id}/workpapers"

        async def _build_world(repo: WorkpaperSyncRepository) -> dict[str, Any]:
            blobs: dict[str, Any] = {}
            for name in ("tpl", "instr", "contract", "authority", "bundle_payload"):
                blobs[name] = await repo.register_artifact(
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=ArtifactKind.definition,
                    state=ArtifactState.published,
                    relative_path=f"{base_path}/.versions/{wp_id}/definitions/{name}.json",
                    sha256=_d(f"blob-{name}"),
                    size_bytes=1024,
                    document_type="json",
                )
            tpl = await repo.create_definition_artifact(
                kind="template",
                logical_id="d2.template",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["tpl"].id,
                sha256=_d("tpl-def"),
                structure_hash=_d("tpl-structure"),
                source_commit="task21",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation",
                logical_id="d2.instrumentation",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["instr"].id,
                sha256=_d("instr-def"),
                structure_hash=_d("instr-structure"),
                source_commit="task21",
            )
            contract = await repo.create_definition_artifact(
                kind="contract",
                logical_id="d2.contract",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["contract"].id,
                sha256=_d("contract-def"),
                source_commit="task21",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model",
                logical_id="authority.projection",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["authority"].id,
                sha256=_d("authority-def"),
                authority_model_type="projection_contract",
                source_commit="task21",
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
            proj_art = await repo.register_artifact(
                project_id=project_id,
                wp_id=wp_id,
                kind=ArtifactKind.projection,
                state=ArtifactState.published,
                relative_path=f"{base_path}/.versions/{wp_id}/projections/v1.json.gz",
                sha256=_d("projection-v1"),
                size_bytes=2048,
                document_type="json.gz",
            )
            canon = await repo.register_artifact(
                project_id=project_id,
                wp_id=wp_id,
                kind=ArtifactKind.canonical,
                state=ArtifactState.published,
                relative_path=f"{base_path}/.versions/{wp_id}/representations/{ENTRY}/g1.xlsx",
                sha256=_d("canonical-g1"),
                size_bytes=40960,
                document_type="xlsx",
            )
            cv = await repo.create_content_version(
                project_id=project_id,
                wp_id=wp_id,
                entry_id=ENTRY,
                revision=1,
                source="html",
                projection_artifact_id=proj_art.id,
                projection_sha256=proj_art.sha256,
            )
            rep = await repo.create_representation(
                project_id=project_id,
                wp_id=wp_id,
                entry_id=ENTRY,
                content_version_id=cv.id,
                generation=1,
                document_type="xlsx",
                artifact_id=canon.id,
                artifact_sha256=canon.sha256,
                definition_bundle_id=bundle.id,
                authority_model_definition_id=authority.id,
                adapter_id="excel.d2.v1",
                adapter_build_digest=_d("adapter-build"),
                structure_hash=_d("structure-g1"),
                identity_inventory_sha256=_d("identity-g1"),
                reason="content_commit",
            )
            await repo.set_entry_pointer(
                wp_id=wp_id, entry_id=ENTRY, representation_id=rep.id, generation=1
            )
            return {
                "bundle": bundle,
                "authority": authority,
                "template": tpl,
                "instrumentation": instr,
                "contract": contract,
                "content_version": cv,
                "representation": rep,
                "projection_sha256": proj_art.sha256,
            }

        async def _durable_incoming(
            repo: WorkpaperSyncRepository,
            *,
            room: Any,
            entry_id: str,
            label: str,
        ) -> Any:
            """建一条 durable incoming artifact（V151 强制它必须绑 `source_delivery_id`）。

            顺带把 room service 与 delivery 的接缝跑一遍真实路径：delivery 的
            `route_credential_id` 由 :func:`mint_route_credential` 派生 —— 那正是
            AC 2.6 末句要求的「callback 使用 room/generation route credential」。
            """
            credential = mint_route_credential(
                room_id=room.id,
                generation=int(room.generation),
                doc_key=room.doc_key,
            )
            delivery = await repo.record_delivery(
                project_id=project_id,
                wp_id=wp_id,
                entry_id=entry_id,
                room_id=room.id,
                generation=int(room.generation),
                route_credential_id=credential.credential_id,
                callback_status=6,
                delivery_key=_d(f"delivery-{label}"),
            )
            # 路径由 DB CHECK sealing：必须含 `.incoming/{room_id}/{delivery_id}/`
            # （Task 11 的 quarantine/retention 靠路径反查归属，故不能自拟目录）。
            return await repo.register_artifact(
                project_id=project_id,
                wp_id=wp_id,
                kind=ArtifactKind.incoming,
                state=ArtifactState.durable,
                relative_path=(
                    f"{base_path}/.incoming/{wp_id}/{delivery.id}/{label}.xlsx"
                ),
                sha256=_d(f"incoming-{label}"),
                size_bytes=4096,
                document_type="xlsx",
                source_delivery_id=delivery.id,
            )

        world: dict[str, Any] = {}
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            world.update(await _build_world(repo))
            await s.commit()

        rep_id = world["representation"].id
        cv_id = world["content_version"].id
        bundle_id = world["bundle"].id
        projection_sha = world["projection_sha256"]

        # ═══ ① open_room：doc_key 由稳定身份派生 ═════════════════════════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                room, frozen = await svc.open_or_reuse_room(
                    scope,
                    representation=world["representation"],
                    opened_base_version_id=cv_id,
                )
                snap["open_room"] = {
                    "doc_key": room.doc_key,
                    "expected_doc_key": derive_doc_key(
                        wp_id=wp_id, entry_id=ENTRY, generation=1
                    ),
                    "generation": int(room.generation),
                    "state": room.state,
                    "write_fence_epoch": int(room.write_fence_epoch),
                    "latest_request_sequence": int(room.latest_request_sequence),
                    "latest_durable_sequence": int(room.latest_durable_sequence),
                    "bundle_slots_digest": frozen.slots_digest,
                    "bundle_sha256": frozen.definition_bundle_sha256,
                    "authority_model": frozen.authority_model.value,
                }
                # entry 不一致必须被拒（room 不得跨 entry 复用 representation）
                try:
                    await svc.open_or_reuse_room(
                        RoomScope(project_id=project_id, wp_id=wp_id, entry_id="other/entry"),
                        representation=world["representation"],
                        opened_base_version_id=cv_id,
                    )
                    snap["open_room"]["cross_entry_error"] = None
                except SyncDomainError as exc:
                    snap["open_room"]["cross_entry_error"] = _err(exc)
                await s.rollback()

        except Exception as exc:  # noqa: BLE001 - 记录而非穿透
            _phase_failed("open_room", exc)
        # 真正落库的 room（后续场景共用）
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                room, frozen = await svc.open_or_reuse_room(
                    scope,
                    representation=world["representation"],
                    opened_base_version_id=cv_id,
                )
                room_id = room.id
                part_a = await svc.join_participant(
                    scope,
                    room_id=room_id,
                    user_id=ids["user_a"],
                    mode=ParticipantMode.edit,
                    permission_epoch=5,
                    lease_token="lease-token-a",
                )
                part_b = await svc.join_participant(
                    scope,
                    room_id=room_id,
                    user_id=ids["user_b"],
                    mode=ParticipantMode.edit,
                    permission_epoch=5,
                    lease_token="lease-token-b",
                )
                part_v = await svc.join_participant(
                    scope,
                    room_id=room_id,
                    user_id=ids["user_v"],
                    mode=ParticipantMode.view,
                    permission_epoch=5,
                    lease_token="lease-token-v",
                )
                snap["lease"] = {
                    "token_hash_a": part_a.lease_token_hash,
                    "token_plain_sha": hashlib.sha256(b"lease-token-a").hexdigest(),
                    "token_hash_b": part_b.lease_token_hash,
                    "distinct_hashes": part_a.lease_token_hash != part_b.lease_token_hash,
                    "joined_fence": int(part_a.joined_write_fence_epoch),
                    "room_fence": int(room.write_fence_epoch),
                    "mode_v": part_v.mode,
                    "state_a": part_a.state,
                    "shared_room": part_a.room_id == part_b.room_id == part_v.room_id,
                }
                part_a_id, part_b_id, part_v_id = part_a.id, part_b.id, part_v.id

                # 另一个 entry 的 room + participant：供「跨 room 复用 participant id」场景用。
                other_entry = "xlsx/gt-other-entry"
                other_scope = RoomScope(
                    project_id=project_id, wp_id=wp_id, entry_id=other_entry
                )
                other_art = await repo.register_artifact(
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=ArtifactKind.canonical,
                    state=ArtifactState.published,
                    relative_path=(
                        f"{base_path}/.versions/{wp_id}/representations/{other_entry}/g1.xlsx"
                    ),
                    sha256=_d("canonical-other"),
                    size_bytes=1024,
                    document_type="xlsx",
                )
                other_rep = await repo.create_representation(
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=other_entry,
                    content_version_id=cv_id,
                    generation=1,
                    document_type="xlsx",
                    artifact_id=other_art.id,
                    artifact_sha256=other_art.sha256,
                    definition_bundle_id=bundle_id,
                    authority_model_definition_id=world["authority"].id,
                    adapter_id="excel.other.v1",
                    adapter_build_digest=_d("adapter-build"),
                    structure_hash=_d("structure-other"),
                    identity_inventory_sha256=_d("identity-other"),
                    reason="content_commit",
                )
                # 发布该 entry 的 current pointer：AC 2.5 要求 room 只接受 **published**
                # representation，光有 representation 行不算已发布（Task 25/26 的 publish
                # 正是「建行 + 移 pointer」两步）。
                await repo.set_entry_pointer(
                    wp_id=wp_id,
                    entry_id=other_entry,
                    representation_id=other_rep.id,
                    generation=1,
                )
                other_room, _ = await svc.open_or_reuse_room(
                    other_scope, representation=other_rep, opened_base_version_id=cv_id
                )
                other_part = await svc.join_participant(
                    other_scope,
                    room_id=other_room.id,
                    user_id=ids["user_other"],
                    mode=ParticipantMode.edit,
                    permission_epoch=5,
                    lease_token="lease-token-other",
                )
                other_room_participant_id = other_part.id
                other_room_id = other_room.id
                await s.commit()

        except Exception as exc:  # noqa: BLE001 - 记录而非穿透
            _phase_failed("world_rooms", exc)
        # ═══ ② 未 confirm descriptor 前不得 forcesave ═══════════════════
        async with Session() as s:
            svc = RoomService(WorkpaperSyncRepository(s))
            try:
                await svc.assert_can_initiate_request(
                    room_id=room_id, participant_id=part_a_id
                )
                snap["eligibility"]["before_confirm"] = None
            except Exception as exc:  # noqa: BLE001 - 记录**实际**异常类型
                # 🔴 刻意 catch 宽：只 catch 期望类型时，一旦生产代码改成抛别的类型，
                # 异常会穿透采集函数 ⇒ 整个 module 变成 collection ERROR ⇒ pytest 的
                # `-rf` 只列 FAILED 不列 ERROR ⇒ 变异检验把它判成 GREEN。
                # 这不是理论风险：Task 21 首轮变异实测 M14/M15/M26 三条正是这样隐身的。
                snap["eligibility"]["before_confirm"] = _err(exc)
            await s.rollback()

        # ═══ ③ confirm descriptor：建立 client-confirmed 基线 ════════════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                frozen = await svc.frozen_bundle_identity(bundle_id)
                conf_a, room_after = await svc.confirm_descriptor(
                    scope,
                    room_id=room_id,
                    participant_id=part_a_id,
                    representation_id=rep_id,
                    content_version_id=cv_id,
                    projection_sha256=projection_sha,
                    idempotency_key="ready-a-1",
                    expected_bundle=frozen,
                )
                # 刻意**只**确认 A：这样 room 已 active 而 B 仍未确认，才能证明
                # 「confirmation 门」独立于「room 状态门」生效（否则 opening 分支会遮蔽它）。
                snap["eligibility"]["after_confirm_room_state"] = room_after.state
                # 🔴 不得用 `str(x)` 直接投影：`str(None) == "None"` 是**真值**，
                # `all(baseline.values())` 会把「基线根本没写上」当成写上了。
                # 首轮变异 M29（仓储侧短路首个赋值）正是靠这个 bug 判成 GREEN 的。
                snap["eligibility"]["client_baseline"] = {
                    "version": _opt(room_after.client_confirmed_base_version_id),
                    "representation": _opt(room_after.client_confirmed_representation_id),
                    "projection": room_after.client_confirmed_projection_sha256 or None,
                    "bundle": _opt(room_after.client_confirmed_definition_bundle_id),
                }
                snap["eligibility"]["server_last_applied_after_confirm"] = (
                    None
                    if room_after.last_applied_version_id is None
                    else str(room_after.last_applied_version_id)
                )
                snap["eligibility"]["confirmation_slots_digest"] = conf_a.bundle_slots_digest
                conf_a_id = conf_a.id

                # 携带漂移 bundle identity 的 descriptor 必须被拒
                drifted = type(frozen)(
                    definition_bundle_id=frozen.definition_bundle_id,
                    definition_bundle_sha256=_d("drifted-bundle"),
                    authority_model=frozen.authority_model,
                    authority_model_definition_id=frozen.authority_model_definition_id,
                    authority_model_definition_sha256=frozen.authority_model_definition_sha256,
                    slots=frozen.slots,
                    slots_digest=frozen.slots_digest,
                )
                try:
                    await svc.confirm_descriptor(
                        scope,
                        room_id=room_id,
                        participant_id=part_b_id,
                        representation_id=rep_id,
                        content_version_id=cv_id,
                        projection_sha256=projection_sha,
                        idempotency_key="ready-b-drift",
                        expected_bundle=drifted,
                    )
                    snap["eligibility"]["drifted_descriptor_error"] = None
                except BundleIdentityDriftError as exc:
                    snap["eligibility"]["drifted_descriptor_error"] = _err(exc)
                await s.commit()

        except Exception as exc:  # noqa: BLE001 - 记录而非穿透
            _phase_failed("confirm", exc)
        # ═══ ④ 资格门通过 + 冻结身份 ════════════════════════════════════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                room, participant, confirmation = await svc.assert_can_initiate_request(
                    room_id=room_id,
                    participant_id=part_a_id,
                    expected_write_fence_epoch=1,
                )
                freeze1 = await svc.build_request_freeze(
                    room=room,
                    participant=participant,
                    confirmation=confirmation,
                    client_edit_epoch=1,
                    contributor_user_ids=[ids["user_a"], ids["user_b"]],
                )
                freeze1_again = await svc.build_request_freeze(
                    room=room,
                    participant=participant,
                    confirmation=confirmation,
                    client_edit_epoch=1,
                    contributor_user_ids=[ids["user_b"], ids["user_a"]],
                )
                freeze2 = await svc.build_request_freeze(
                    room=room,
                    participant=participant,
                    confirmation=confirmation,
                    client_edit_epoch=2,
                    contributor_user_ids=[ids["user_a"], ids["user_b"]],
                )
                freeze3 = await svc.build_request_freeze(
                    room=room,
                    participant=participant,
                    confirmation=confirmation,
                    client_edit_epoch=1,
                    contributor_user_ids=[ids["user_a"]],
                )
                snap["freeze"] = {
                    "fingerprint": freeze1.frozen_request_fingerprint,
                    "stable_across_contributor_order": (
                        freeze1.frozen_request_fingerprint
                        == freeze1_again.frozen_request_fingerprint
                    ),
                    "changes_with_edit_epoch": (
                        freeze1.frozen_request_fingerprint
                        != freeze2.frozen_request_fingerprint
                    ),
                    "changes_with_contributor_set": (
                        freeze1.frozen_request_fingerprint
                        != freeze3.frozen_request_fingerprint
                    ),
                    "client_base_version": str(freeze1.client_base_version_id),
                    "client_base_is_confirmed_base": (
                        freeze1.client_base_version_id
                        == room.client_confirmed_base_version_id
                    ),
                    "write_fence_epoch": freeze1.write_fence_epoch,
                    "kind": freeze1.kind.value,
                    "repo_kwargs_keys": sorted(
                        freeze1.as_repository_kwargs(scope=scope).keys()
                    ),
                }
                # 真建一个 request（后续撤销场景要取消它）
                outcome = await repo.create_forcesave_request_with_shell(
                    **freeze1.as_repository_kwargs(scope=scope),
                    idempotency_key="forcesave-a-1",
                    created_by=ids["user_a"],
                )
                snap["freeze"]["request_state"] = outcome.request.state
                snap["freeze"]["request_sequence"] = int(outcome.request.request_sequence)
                snap["freeze"]["operation_application_id"] = outcome.operation.application_id
                snap["freeze"]["operation_duplicate_of"] = (
                    outcome.operation.duplicate_of_operation_id
                )
                request_a_id = outcome.request.id
                operation_a_id = outcome.operation.id
                await s.commit()

        except Exception as exc:  # noqa: BLE001 - 记录而非穿透
            _phase_failed("freeze", exc)
        # ═══ ⑤ 逐条拒绝判据 ════════════════════════════════════════════
        async def _expect_reject(fn) -> str | None:
            """跑一个应当被拒的场景，返回实际异常字符串（未被拒返回 None）。

            catch `Exception` 而不是 `SyncDomainError`：见上面 before_confirm 处的注释 ——
            窄 catch 会让「抛了别的类型」变成不可见的 module ERROR，变异检验判 GREEN。
            这里把实际类型如实记进快照，断言侧再要求它是**专属**类型。
            """
            async with Session() as s:
                svc = RoomService(WorkpaperSyncRepository(s))
                try:
                    await fn(svc, s)
                    return None
                except Exception as exc:  # noqa: BLE001 - 记录实际类型供断言
                    return _err(exc)
                finally:
                    await s.rollback()

        async def _view_participant(svc, _s) -> None:
            await svc.assert_can_initiate_request(
                room_id=room_id, participant_id=part_v_id
            )

        async def _stale_descriptor_fence(svc, _s) -> None:
            await svc.assert_can_initiate_request(
                room_id=room_id,
                participant_id=part_a_id,
                expected_write_fence_epoch=99,
            )

        async def _close_capture_kind(svc, _s) -> None:
            await svc.assert_can_initiate_request(
                room_id=room_id,
                participant_id=part_a_id,
                kind=RequestKind.close_capture,
            )

        async def _foreign_participant(svc, _s) -> None:
            await svc.assert_can_initiate_request(
                room_id=room_id, participant_id=uuid.uuid4()
            )

        async def _unconfirmed_second_participant(svc, _s) -> None:
            # room 已 active（A 确认过），B 合法但未确认 ⇒ 必须由 confirmation 门拦下，
            # 证明它独立于「room 仍 opening」那条分支。
            await svc.assert_can_initiate_request(
                room_id=room_id, participant_id=part_b_id
            )

        async def _revoked_participant(svc, s) -> None:
            await s.execute(
                sa.update(WorkpaperOoParticipant)
                .where(WorkpaperOoParticipant.id == part_b_id)
                .values(state=ParticipantState.revoked.value, revoked_at=sa.func.now())
            )
            await s.flush()
            await svc.assert_can_initiate_request(
                room_id=room_id, participant_id=part_b_id
            )

        async def _expired_lease(svc, s) -> None:
            await s.execute(
                sa.update(WorkpaperOoParticipant)
                .where(WorkpaperOoParticipant.id == part_b_id)
                .values(expires_at=sa.text("now() - interval '1 hour'"))
            )
            await s.flush()
            await svc.assert_can_initiate_request(
                room_id=room_id, participant_id=part_b_id
            )

        async def _room_fence_bumped(svc, s) -> None:
            await s.execute(
                sa.update(WorkpaperOoRoom)
                .where(WorkpaperOoRoom.id == room_id)
                .values(write_fence_epoch=2)
            )
            await s.flush()
            await svc.assert_can_initiate_request(
                room_id=room_id, participant_id=part_a_id
            )

        async def _invalidated_confirmation(svc, s) -> None:
            await s.execute(
                sa.update(WorkpaperOoClientConfirmation)
                .where(WorkpaperOoClientConfirmation.id == conf_a_id)
                .values(invalidated_at=sa.func.now())
            )
            await s.flush()
            await svc.assert_can_initiate_request(
                room_id=room_id, participant_id=part_a_id
            )

        async def _new_editor_after_barrier(svc, s) -> None:
            await s.execute(
                sa.update(WorkpaperOoRoom)
                .where(WorkpaperOoRoom.id == room_id)
                .values(close_barrier_epoch=1)
            )
            await s.flush()
            # 用**全新** user：复用 user_v 会先撞 (room_id,user_id) 唯一约束，
            # 于是 barrier 判据被一个 IntegrityError 遮蔽（变异检验会判 GREEN）。
            await svc.join_participant(
                scope,
                room_id=room_id,
                user_id=ids["user_late"],
                mode=ParticipantMode.edit,
                permission_epoch=5,
                lease_token="late-joiner",
            )

        async def _participant_joined_at_older_fence(svc, s) -> None:
            # 把 room 与 confirmation 的 fence 一起提到 2，participant 的 joined fence
            # 留在 1 ⇒ **只有**第 ④ 条判据能拦下它。
            #
            # 为什么不是「把 participant 的 joined fence 调到 0」：`ck_wpoop_epochs`
            # 要求 `joined_write_fence_epoch >= 1`，那样会先撞 CHECK。
            # 为什么不能只提 room fence：第 ⑥ 条 confirmation-fence 会先打红，
            # 第 ④ 条被遮蔽 —— 首轮变异 M08 正是这样隐身的。
            await s.execute(
                sa.update(WorkpaperOoRoom)
                .where(WorkpaperOoRoom.id == room_id)
                .values(write_fence_epoch=2)
            )
            await s.execute(
                sa.update(WorkpaperOoClientConfirmation)
                .where(WorkpaperOoClientConfirmation.id == conf_a_id)
                .values(write_fence_epoch=2)
            )
            await s.flush()
            await svc.assert_can_initiate_request(
                room_id=room_id, participant_id=part_a_id
            )

        async def _cross_room_participant(svc, s) -> None:
            # 真实存在但属于**另一个 room** 的 participant ⇒ 只有 room 归属判据能拦。
            # （传随机 UUID 时「不存在」分支会先命中，归属判据被遮蔽 —— M12 的隐身路径。）
            await svc.assert_can_initiate_request(
                room_id=room_id, participant_id=other_room_participant_id
            )

        async def _settle_with_blank_digest(svc, _s) -> None:
            frozen_local = await svc.frozen_bundle_identity(bundle_id)
            await svc.settle_client_baseline(
                room_id=room_id,
                merged_projection_sha256="",
                incoming_projection_sha256="",
                applied_content_version_id=cv_id,
                applied_representation_id=rep_id,
                bundle=frozen_local,
            )

        snap["eligibility"]["unconfirmed_second_participant"] = await _expect_reject(
            _unconfirmed_second_participant
        )
        snap["eligibility"]["view_mode"] = await _expect_reject(_view_participant)
        snap["eligibility"]["stale_descriptor_fence"] = await _expect_reject(
            _stale_descriptor_fence
        )
        snap["eligibility"]["close_capture_from_client"] = await _expect_reject(
            _close_capture_kind
        )
        snap["eligibility"]["foreign_participant"] = await _expect_reject(
            _foreign_participant
        )
        snap["eligibility"]["revoked_participant"] = await _expect_reject(
            _revoked_participant
        )
        snap["eligibility"]["expired_lease"] = await _expect_reject(_expired_lease)
        snap["eligibility"]["room_fence_bumped"] = await _expect_reject(
            _room_fence_bumped
        )
        snap["eligibility"]["invalidated_confirmation"] = await _expect_reject(
            _invalidated_confirmation
        )
        snap["eligibility"]["new_editor_after_barrier"] = await _expect_reject(
            _new_editor_after_barrier
        )
        snap["eligibility"]["participant_joined_at_older_fence"] = await _expect_reject(
            _participant_joined_at_older_fence
        )
        snap["eligibility"]["cross_room_participant"] = await _expect_reject(
            _cross_room_participant
        )
        snap["eligibility"]["settle_with_blank_digest"] = await _expect_reject(
            _settle_with_blank_digest
        )

        # ═══ ⑥ 双基线：server 无条件、client 等值才推进 ══════════════════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                merged_art = await repo.register_artifact(
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=ArtifactKind.projection,
                    state=ArtifactState.published,
                    relative_path=f"{base_path}/.versions/{wp_id}/projections/v2.json.gz",
                    sha256=_d("merged-projection"),
                    size_bytes=2048,
                    document_type="json.gz",
                )
                applied_cv = await repo.create_content_version(
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=ENTRY,
                    revision=2,
                    source="onlyoffice",
                    projection_artifact_id=merged_art.id,
                    projection_sha256=merged_art.sha256,
                    parent_version_id=cv_id,
                )
                # `advance_server_last_applied` 现在必须带 application：AC 10.11 要求
                # server 指针与 room canonical fence 在同一 room lock 事务里原子决定。
                # 因此这里用**真实** application（由 repository 的 request-first
                # correlation 产出），而不是手插一行绕过 application_key 不变量。
                baseline_room_row = await repo.lock_room(room_id)
                baseline_incoming = await _durable_incoming(
                    repo, room=baseline_room_row, entry_id=ENTRY, label="baseline"
                )
                baseline_corr = await repo.correlate_durable_incoming(
                    operation_id=operation_a_id,
                    incoming_artifact_id=baseline_incoming.id,
                    current_revision=1,
                    adapter_id="excel.d2.v1",
                )
                before = await svc.baselines(room_id)
                fence_advance = await svc.advance_server_last_applied(
                    room_id=room_id,
                    content_version_id=applied_cv.id,
                    application_id=baseline_corr.application.id,
                )
                after_server = await svc.baselines(room_id)
                room_after_server = await repo.lock_room(room_id)
                snap["baselines"]["server_advance"] = {
                    "before_server": (
                        None if before.server_last_applied_version_id is None
                        else str(before.server_last_applied_version_id)
                    ),
                    "after_server": str(after_server.server_last_applied_version_id),
                    "client_unchanged": (
                        before.client_confirmed_base_version_id
                        == after_server.client_confirmed_base_version_id
                    ),
                    "room_state": room_after_server.state,
                    "canonical_application": str(
                        fence_advance.latest_durable_application_id
                    ),
                    "expected_application": str(baseline_corr.application.id),
                    "room_canonical_application": str(
                        room_after_server.latest_durable_application_id
                    ),
                    "room_durable_sequence": int(
                        room_after_server.latest_durable_sequence
                    ),
                }
                # 等值 ⇒ 推进 client baseline
                frozen = await svc.frozen_bundle_identity(bundle_id)
                equal = await svc.settle_client_baseline(
                    room_id=room_id,
                    merged_projection_sha256=_d("same"),
                    incoming_projection_sha256=_d("same"),
                    applied_content_version_id=applied_cv.id,
                    applied_representation_id=rep_id,
                    bundle=frozen,
                )
                after_equal = await svc.baselines(room_id)
                snap["baselines"]["equal_settle"] = {
                    "advanced": equal.client_baseline_advanced,
                    "refresh_required": equal.refresh_required,
                    "next_request_allowed": equal.next_request_allowed,
                    "client_version": str(after_equal.client_confirmed_base_version_id),
                    "client_projection": after_equal.client_confirmed_projection_sha256,
                }
                await s.commit()

            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                frozen = await svc.frozen_bundle_identity(bundle_id)
                unequal = await svc.settle_client_baseline(
                    room_id=room_id,
                    merged_projection_sha256=_d("merged-differs"),
                    incoming_projection_sha256=_d("incoming"),
                    applied_content_version_id=cv_id,
                    applied_representation_id=rep_id,
                    bundle=frozen,
                )
                room_row = (
                    await s.execute(sa.select(WorkpaperOoRoom).where(WorkpaperOoRoom.id == room_id))
                ).scalar_one()
                snap["baselines"]["unequal_settle"] = {
                    "advanced": unequal.client_baseline_advanced,
                    "refresh_required": unequal.refresh_required,
                    "next_request_allowed": unequal.next_request_allowed,
                    "reason": unequal.reason,
                    "room_state": room_row.state,
                    "refresh_reason": room_row.refresh_reason,
                    "client_version_kept": str(room_row.client_confirmed_base_version_id),
                }
                # refresh-required 后下一次 forcesave 必须被拒
                try:
                    await svc.assert_can_initiate_request(
                        room_id=room_id, participant_id=part_a_id
                    )
                    snap["baselines"]["next_request_after_refresh"] = None
                except RoomNotWritableError as exc:
                    snap["baselines"]["next_request_after_refresh"] = _err(exc)
                await s.commit()

        except Exception as exc:  # noqa: BLE001 - 记录而非穿透
            _phase_failed("baselines", exc)
        # ═══ ⑦ 撤销：writer ⇒ fence+1 + 取消 outstanding + refresh ════════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                fence_before = int(
                    (
                        await s.execute(
                            sa.select(WorkpaperOoRoom.write_fence_epoch).where(
                                WorkpaperOoRoom.id == room_id
                            )
                        )
                    ).scalar_one()
                )
                outcome_view = await svc.revoke_participant(
                    room_id=room_id, participant_id=part_v_id, oo_drop_confirmed=True
                )
                fence_after_view = int(
                    (
                        await s.execute(
                            sa.select(WorkpaperOoRoom.write_fence_epoch).where(
                                WorkpaperOoRoom.id == room_id
                            )
                        )
                    ).scalar_one()
                )
                outcome_writer = await svc.revoke_participant(
                    room_id=room_id, participant_id=part_a_id, oo_drop_confirmed=True
                )
                request_state = (
                    await s.execute(
                        sa.select(WorkpaperForcesaveRequest.state).where(
                            WorkpaperForcesaveRequest.id == request_a_id
                        )
                    )
                ).scalar_one()
                room_row = (
                    await s.execute(sa.select(WorkpaperOoRoom).where(WorkpaperOoRoom.id == room_id))
                ).scalar_one()
                participant_row = (
                    await s.execute(
                        sa.select(WorkpaperOoParticipant).where(
                            WorkpaperOoParticipant.id == part_a_id
                        )
                    )
                ).scalar_one()
                snap["revoke"] = {
                    "fence_before": fence_before,
                    "view_decision": outcome_view.decision,
                    "view_generation_rotated": outcome_view.generation_rotated,
                    "fence_after_view": fence_after_view,
                    "writer_decision": outcome_writer.decision,
                    "writer_generation_rotated": outcome_writer.generation_rotated,
                    "fence_after_writer": outcome_writer.write_fence_epoch,
                    "cancelled_request_ids": [
                        str(i) for i in outcome_writer.cancelled_request_ids
                    ],
                    "request_a_state": request_state,
                    "room_state": room_row.state,
                    "refresh_reason": room_row.refresh_reason,
                    "participant_state": participant_row.state,
                    "oo_drop_confirmed_at_set": participant_row.oo_drop_confirmed_at
                    is not None,
                }
                await s.commit()

        except Exception as exc:  # noqa: BLE001 - 记录而非穿透
            _phase_failed("revoke", exc)
        # ═══ ⑧ supersede + 新 generation 的 doc_key 轮转 ═════════════════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                superseded = await svc.supersede_room(
                    room_id=room_id, reason="writer_revoked"
                )
                snap["supersede"] = {
                    "state": superseded.state,
                    "superseded_at_set": superseded.superseded_at is not None,
                    "old_doc_key": superseded.doc_key,
                }
                # 🔴 这一步必须在**发布 g2 之前**做：撤销 writer 后的真实时序是
                # 「supersede 旧 room → 还没发布新代际」，此时 entry pointer 仍指向 g1。
                # 若等 g2 发布后再试，准入门（「g1 不再是 published」）会先命中，把
                # 「同代际在 uq_wpoor_generation 下永不可重开」这条诊断整条遮蔽掉。
                try:
                    await svc.open_or_reuse_room(
                        scope,
                        representation=world["representation"],
                        opened_base_version_id=cv_id,
                    )
                    snap["supersede"]["reopen_superseded_generation_error"] = None
                except Exception as exc:  # noqa: BLE001 - 记录实际类型供断言
                    snap["supersede"]["reopen_superseded_generation_error"] = _err(exc)
                # 新 generation 的 representation ⇒ 新 room ⇒ 新 doc_key
                canon2 = await repo.register_artifact(
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=ArtifactKind.canonical,
                    state=ArtifactState.published,
                    relative_path=(
                        f"{base_path}/.versions/{wp_id}/representations/{ENTRY}/g2.xlsx"
                    ),
                    sha256=_d("canonical-g2"),
                    size_bytes=40960,
                    document_type="xlsx",
                )
                rep2 = await repo.create_representation(
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=ENTRY,
                    content_version_id=cv_id,
                    generation=2,
                    document_type="xlsx",
                    artifact_id=canon2.id,
                    artifact_sha256=canon2.sha256,
                    definition_bundle_id=bundle_id,
                    authority_model_definition_id=world["authority"].id,
                    adapter_id="excel.d2.v1",
                    adapter_build_digest=_d("adapter-build"),
                    structure_hash=_d("structure-g2"),
                    identity_inventory_sha256=_d("identity-g2"),
                    reason="definition_upgrade",
                    parent_representation_id=rep_id,
                )
                # 「发布新 generation」= 建 representation 行 **且** 把 entry pointer 移过去。
                # 只建行不移 pointer 时，新代际仍不是 published，room 准入门会拒 ——
                # 那正是 AC 2.5 想要的语义（Task 25/26 的 publish 也是这两步）。
                await repo.set_entry_pointer(
                    wp_id=wp_id, entry_id=ENTRY, representation_id=rep2.id, generation=2
                )
                room2, _ = await svc.open_or_reuse_room(
                    scope, representation=rep2, opened_base_version_id=cv_id
                )
                snap["supersede"]["new_doc_key"] = room2.doc_key
                snap["supersede"]["new_generation"] = int(room2.generation)
                snap["supersede"]["doc_key_rotated"] = room2.doc_key != superseded.doc_key
                snap["supersede"]["new_room_fence"] = int(room2.write_fence_epoch)
                room2_id = room2.id
                await s.commit()

        except Exception as exc:  # noqa: BLE001 - 记录而非穿透
            _phase_failed("supersede", exc)
        # ═══ ⑨ 同代际必须复用而不是新建（AC 2.8 + uq_wpoor_generation）═══
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            svc = RoomService(repo)
            try:
                reused, _ = await svc.open_or_reuse_room(
                    scope, representation=rep2, opened_base_version_id=cv_id
                )
                snap["supersede"]["reuse_error"] = None
                snap["supersede"]["reuse_same_generation_room_id"] = str(reused.id)
                snap["supersede"]["reused_is_room2"] = str(reused.id) == str(room2_id)
            except Exception as exc:  # noqa: BLE001 - 复用退化成新建会撞唯一约束
                snap["supersede"]["reuse_error"] = _err(exc)
                snap["supersede"]["reuse_same_generation_room_id"] = None
                snap["supersede"]["reused_is_room2"] = False
                await s.rollback()
            # 已被 g2 取代的 g1：此时准入门先命中（「不再是 published 代际」）。
            # 两条诊断都要留证，否则改动分支顺序时没人发现遮蔽关系变了。
            try:
                await svc.open_or_reuse_room(
                    scope,
                    representation=world["representation"],
                    opened_base_version_id=cv_id,
                )
                snap["supersede"]["reopen_after_new_generation_error"] = None
            except Exception as exc:  # noqa: BLE001 - 记录实际类型供断言
                snap["supersede"]["reopen_after_new_generation_error"] = _err(exc)
            await s.rollback()

        # ═══ ⑩ flush-only：rollback 后零行（用独立 entry 避免撞唯一约束）════
        probe_entry = "xlsx/gt-probe-flush-only"
        probe_scope = RoomScope(
            project_id=project_id, wp_id=wp_id, entry_id=probe_entry
        )
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            svc = RoomService(repo)
            probe_art = await repo.register_artifact(
                project_id=project_id,
                wp_id=wp_id,
                kind=ArtifactKind.canonical,
                state=ArtifactState.published,
                relative_path=(
                    f"{base_path}/.versions/{wp_id}/representations/{probe_entry}/g1.xlsx"
                ),
                sha256=_d("canonical-probe"),
                size_bytes=1024,
                document_type="xlsx",
            )
            probe_rep = await repo.create_representation(
                project_id=project_id,
                wp_id=wp_id,
                entry_id=probe_entry,
                content_version_id=cv_id,
                generation=1,
                document_type="xlsx",
                artifact_id=probe_art.id,
                artifact_sha256=probe_art.sha256,
                definition_bundle_id=bundle_id,
                authority_model_definition_id=world["authority"].id,
                adapter_id="excel.probe.v1",
                adapter_build_digest=_d("adapter-build"),
                structure_hash=_d("structure-probe"),
                identity_inventory_sha256=_d("identity-probe"),
                reason="content_commit",
            )
            await repo.set_entry_pointer(
                wp_id=wp_id,
                entry_id=probe_entry,
                representation_id=probe_rep.id,
                generation=1,
            )
            probe_room, _ = await svc.open_or_reuse_room(
                probe_scope, representation=probe_rep, opened_base_version_id=cv_id
            )
            probe_id = probe_room.id
            await s.rollback()
        async with Session() as s:
            remaining = (
                await s.execute(
                    sa.select(sa.func.count())
                    .select_from(WorkpaperOoRoom)
                    .where(WorkpaperOoRoom.id == probe_id)
                )
            ).scalar_one()
            snap["flush_only"] = {"rows_after_rollback": int(remaining)}

        # ═══ ⑪ representation 准入：published / candidate / alias 漂移 ═════
        #
        # 三条判据各有独立异常类型。用**独立 entry** 而不是复用主 entry：主 entry 的
        # room 已存在，`open_or_reuse_room` 会走复用分支直接返回，准入门根本不会被执行
        # —— 那样这三条会全部假绿。
        admit_entry = "xlsx/gt-admission"
        admit_scope = RoomScope(
            project_id=project_id, wp_id=wp_id, entry_id=admit_entry
        )
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                admit_art = await repo.register_artifact(
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=ArtifactKind.canonical,
                    state=ArtifactState.published,
                    relative_path=(
                        f"{base_path}/.versions/{wp_id}/representations/{admit_entry}/g1.xlsx"
                    ),
                    sha256=_d("canonical-admit"),
                    size_bytes=2048,
                    document_type="xlsx",
                )
                admit_rep = await repo.create_representation(
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=admit_entry,
                    content_version_id=cv_id,
                    generation=1,
                    document_type="xlsx",
                    artifact_id=admit_art.id,
                    authority_model_definition_id=world["authority"].id,
                    artifact_sha256=admit_art.sha256,
                    definition_bundle_id=bundle_id,
                    adapter_id="excel.admit.v1",
                    adapter_build_digest=_d("adapter-build"),
                    structure_hash=_d("structure-admit"),
                    identity_inventory_sha256=_d("identity-admit"),
                    reason="content_commit",
                )
                admission: dict[str, Any] = {}
                admit_rep_id = admit_rep.id
                # 🔴 必须 commit：后面每条拒绝场景各用一个 session + rollback，
                # 若 representation 只 flush 不 commit，第一次 rollback 就把它撤掉，
                # 后续 `set_entry_pointer` 会撞外键 —— 那是采集缺陷，不是生产缺陷，
                # 但表现出来是「三条判据全红」，很容易被误读成实现错了。
                await s.commit()

            # ① 尚无 entry pointer ⇒ 未发布
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                admit_rep = (
                    await s.execute(
                        sa.select(WorkpaperContentRepresentation).where(
                            WorkpaperContentRepresentation.id == admit_rep_id
                        )
                    )
                ).scalar_one()
                try:
                    await svc.open_or_reuse_room(
                        admit_scope,
                        representation=admit_rep,
                        opened_base_version_id=cv_id,
                    )
                    admission["no_pointer"] = None
                except SyncDomainError as exc:
                    admission["no_pointer"] = _err(exc)
                    admission["no_pointer_code"] = getattr(exc, "error_code", None)
                await s.rollback()

            # ② 有 pointer ⇒ 通过（正向自检：门不是恒拒）
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                admit_rep = (
                    await s.execute(
                        sa.select(WorkpaperContentRepresentation).where(
                            WorkpaperContentRepresentation.id == admit_rep_id
                        )
                    )
                ).scalar_one()
                await repo.set_entry_pointer(
                    wp_id=wp_id,
                    entry_id=admit_entry,
                    representation_id=admit_rep_id,
                    generation=1,
                )
                admitted, admitted_bundle = await svc.open_or_reuse_room(
                    admit_scope, representation=admit_rep, opened_base_version_id=cv_id
                )
                admission["published_ok"] = str(admitted.id)
                admission["published_bundle_sha"] = admitted_bundle.definition_bundle_sha256
                await s.rollback()

            # ③ 未 finalize 的 upgrade candidate 挂在该 representation 上 ⇒ 拒
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                await repo.set_entry_pointer(
                    wp_id=wp_id,
                    entry_id=admit_entry,
                    representation_id=admit_rep_id,
                    generation=1,
                )
                staged_art = await repo.register_artifact(
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=ArtifactKind.upgrade_candidate,
                    state=ArtifactState.staged,
                    relative_path=(
                        f"{base_path}/.versions/{wp_id}/candidates/{admit_entry}/c1.xlsx"
                    ),
                    sha256=_d("candidate-admit"),
                    size_bytes=2048,
                    document_type="xlsx",
                )
                await repo.create_upgrade_candidate(
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=admit_entry,
                    content_version_id=cv_id,
                    source_representation_id=admit_rep_id,
                    staged_artifact_id=staged_art.id,
                    staged_artifact_sha256=staged_art.sha256,
                    template_definition_id=world["template"].id,
                    instrumentation_definition_id=world["instrumentation"].id,
                    target_contract_definition_id=world["contract"].id,
                    target_definition_bundle_id=bundle_id,
                )
                fresh_rep = (
                    await s.execute(
                        sa.select(WorkpaperContentRepresentation).where(
                            WorkpaperContentRepresentation.id == admit_rep_id
                        )
                    )
                ).scalar_one()
                try:
                    await svc.open_or_reuse_room(
                        admit_scope,
                        representation=fresh_rep,
                        opened_base_version_id=cv_id,
                    )
                    admission["staged_candidate"] = None
                except SyncDomainError as exc:
                    admission["staged_candidate"] = _err(exc)
                    admission["staged_candidate_code"] = getattr(exc, "error_code", None)
                await s.rollback()

            # ④-a alias 漂移的**主要**执法点其实在数据库：V151 的 `trg_wpcr_immutable`
            #     让 representation 行整行 immutable，`trg_wpcr_identity` 又在 INSERT 时
            #     把 bundle/authority digest 双向锁死。先把这条事实钉住 —— 否则下面那条
            #     服务层判据会被误读成「唯一防线」，将来有人删了 DB trigger 也没人发现。
            async with Session() as s:
                try:
                    await s.execute(
                        sa.update(WorkpaperContentRepresentation)
                        .where(WorkpaperContentRepresentation.id == admit_rep_id)
                        .values(definition_bundle_sha256=_d("aliased-bundle"))
                    )
                    await s.flush()
                    admission["db_refuses_row_drift"] = None
                except Exception as exc:  # noqa: BLE001 - 记录实际 DB 异常
                    admission["db_refuses_row_drift"] = _err(exc)
                await s.rollback()

            # ④-b 服务层判据的**可达路径**：`open_or_reuse_room` 收到的是调用方给的
            #     representation **对象**（coordinator 可能持有一份 detached/陈旧副本），
            #     而不是一个 id。把对象 expunge 后改掉冻结 digest 再传进来，就精确复现
            #     「调用方拿着一份 bundle 身份已漂移的 representation 来开 room」。
            #     不 expunge 会触发 autoflush ⇒ 撞上面那条 immutable trigger，
            #     测出来的就变成 DB 异常而不是服务层判据（判据被遮蔽）。
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                await repo.set_entry_pointer(
                    wp_id=wp_id,
                    entry_id=admit_entry,
                    representation_id=admit_rep_id,
                    generation=1,
                )
                drifted = (
                    await s.execute(
                        sa.select(WorkpaperContentRepresentation).where(
                            WorkpaperContentRepresentation.id == admit_rep_id
                        )
                    )
                ).scalar_one()
                s.expunge(drifted)
                drifted.definition_bundle_sha256 = _d("aliased-bundle")
                try:
                    await svc.open_or_reuse_room(
                        admit_scope,
                        representation=drifted,
                        opened_base_version_id=cv_id,
                    )
                    admission["alias_drift"] = None
                except SyncDomainError as exc:
                    admission["alias_drift"] = _err(exc)
                    admission["alias_drift_code"] = getattr(exc, "error_code", None)
                await s.rollback()

            # ④-c authority model 被换成另一份 definition ⇒ 同样是 alias 漂移
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                await repo.set_entry_pointer(
                    wp_id=wp_id,
                    entry_id=admit_entry,
                    representation_id=admit_rep_id,
                    generation=1,
                )
                drifted2 = (
                    await s.execute(
                        sa.select(WorkpaperContentRepresentation).where(
                            WorkpaperContentRepresentation.id == admit_rep_id
                        )
                    )
                ).scalar_one()
                s.expunge(drifted2)
                drifted2.authority_model_definition_id = world["template"].id
                try:
                    await svc.open_or_reuse_room(
                        admit_scope,
                        representation=drifted2,
                        opened_base_version_id=cv_id,
                    )
                    admission["authority_drift"] = None
                except SyncDomainError as exc:
                    admission["authority_drift"] = _err(exc)
                    admission["authority_drift_code"] = getattr(exc, "error_code", None)
                await s.rollback()
            snap["admission"] = admission

        except Exception as exc:  # noqa: BLE001 - 记录而非穿透
            _phase_failed("admission", exc)

        # ═══ ⑫ route credential + contributor 三分（AC 2.6 末句）══════════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                credential = await svc.route_credential(room2_id)
                room2_row = await repo.lock_room(room2_id)
                expected = mint_route_credential(
                    room_id=room2_id,
                    generation=int(room2_row.generation),
                    doc_key=room2_row.doc_key,
                )
                snap["route"] = {
                    "credential_id": str(credential.credential_id),
                    "matches_room_row": credential.credential_id == expected.credential_id,
                    "generation": credential.generation,
                    "doc_key": credential.doc_key,
                    "not_a_participant": str(credential.credential_id)
                    not in {str(part_a_id), str(part_b_id), str(part_v_id)},
                }
                # 换 generation 的凭证必须被拒（陈旧 descriptor 不得复用旧凭证）
                try:
                    assert_route_credential(
                        credential.credential_id,
                        room_id=room2_id,
                        generation=int(room2_row.generation) + 1,
                        doc_key=room2_row.doc_key,
                    )
                    snap["route"]["stale_generation_error"] = None
                except SyncDomainError as exc:
                    snap["route"]["stale_generation_error"] = _err(exc)
                    snap["route"]["stale_generation_code"] = getattr(exc, "error_code", None)
                await s.rollback()

        except Exception as exc:  # noqa: BLE001 - 记录而非穿透
            _phase_failed("route", exc)

        # ═══ ⑬ canonical fence：无条件推进 server + 同 app 只 fold ════════
        #
        # 这一段必须用**真实 application 行**：application 是 `correlate_durable_incoming`
        # 在 room lock 内 create-or-hit 出来的，手插一行会绕开 application_key 与
        # origin/effective sequence 的不变量，测出来的 fold 语义就不是生产语义。
        fence_entry = "xlsx/gt-fence"
        fence_scope = RoomScope(project_id=project_id, wp_id=wp_id, entry_id=fence_entry)
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                fence_art = await repo.register_artifact(
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=ArtifactKind.canonical,
                    state=ArtifactState.published,
                    relative_path=(
                        f"{base_path}/.versions/{wp_id}/representations/{fence_entry}/g1.xlsx"
                    ),
                    sha256=_d("canonical-fence"),
                    size_bytes=2048,
                    document_type="xlsx",
                )
                fence_rep = await repo.create_representation(
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=fence_entry,
                    content_version_id=cv_id,
                    generation=1,
                    document_type="xlsx",
                    artifact_id=fence_art.id,
                    artifact_sha256=fence_art.sha256,
                    definition_bundle_id=bundle_id,
                    authority_model_definition_id=world["authority"].id,
                    adapter_id="excel.fence.v1",
                    adapter_build_digest=_d("adapter-build"),
                    structure_hash=_d("structure-fence"),
                    identity_inventory_sha256=_d("identity-fence"),
                    reason="content_commit",
                )
                await repo.set_entry_pointer(
                    wp_id=wp_id,
                    entry_id=fence_entry,
                    representation_id=fence_rep.id,
                    generation=1,
                )
                fence_room, fence_bundle = await svc.open_or_reuse_room(
                    fence_scope, representation=fence_rep, opened_base_version_id=cv_id
                )
                fence_part = await svc.join_participant(
                    fence_scope,
                    room_id=fence_room.id,
                    user_id=ids["user_a"],
                    mode=ParticipantMode.edit,
                    permission_epoch=5,
                    lease_token="lease-token-fence",
                )
                fence_conf, _ = await svc.confirm_descriptor(
                    fence_scope,
                    room_id=fence_room.id,
                    participant_id=fence_part.id,
                    representation_id=fence_rep.id,
                    content_version_id=cv_id,
                    projection_sha256=projection_sha,
                    idempotency_key="fence-confirm-1",
                    expected_bundle=fence_bundle,
                )
                incoming = await _durable_incoming(
                    repo, room=fence_room, entry_id=fence_entry, label="fence"
                )
                room_row, part_row, conf_row = await svc.assert_can_initiate_request(
                    room_id=fence_room.id, participant_id=fence_part.id
                )
                freeze_a = await svc.build_request_freeze(
                    room=room_row,
                    participant=part_row,
                    confirmation=conf_row,
                    client_edit_epoch=1,
                    contributor_user_ids=[ids["user_a"]],
                )
                outcome_a = await repo.create_forcesave_request_with_shell(
                    **freeze_a.as_repository_kwargs(scope=fence_scope),
                    idempotency_key="fence-req-1",
                )
                correlated = await repo.correlate_durable_incoming(
                    operation_id=outcome_a.operation.id,
                    incoming_artifact_id=incoming.id,
                    current_revision=1,
                    adapter_id="excel.fence.v1",
                )
                application_id = correlated.application.id
                applied_art = await repo.register_artifact(
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=ArtifactKind.projection,
                    state=ArtifactState.published,
                    relative_path=f"{base_path}/.versions/{wp_id}/projections/fence.json.gz",
                    sha256=_d("fence-applied"),
                    size_bytes=1024,
                    document_type="json.gz",
                )
                applied_version = await repo.create_content_version(
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=fence_entry,
                    # `uq_wpcv_wp_revision` 是 **per wp**（不是 per entry）：revision 2
                    # 已被 baselines 阶段占用，这里必须往后排。
                    revision=3,
                    source="onlyoffice",
                    projection_artifact_id=applied_art.id,
                    projection_sha256=applied_art.sha256,
                    parent_version_id=cv_id,
                )
                advance = await svc.advance_server_last_applied(
                    room_id=fence_room.id,
                    content_version_id=applied_version.id,
                    application_id=application_id,
                )
                origin = int(correlated.application.origin_request_sequence)
                fold_high = await svc.fold_same_application_request(
                    room_id=fence_room.id,
                    application_id=application_id,
                    request_sequence=origin + 4,
                )
                fold_low = await svc.fold_same_application_request(
                    room_id=fence_room.id,
                    application_id=application_id,
                    request_sequence=origin + 1,
                )
                fence_room_row = await repo.lock_room(fence_room.id)
                snap["fence"] = {
                    "origin_sequence": origin,
                    "server_last_applied": str(advance.server_last_applied_version_id),
                    "advance_points_at_app": (
                        str(advance.latest_durable_application_id) == str(application_id)
                    ),
                    "advance_effective": advance.effective_request_sequence,
                    "fold_high_effective": fold_high.effective_request_sequence,
                    "fold_high_origin": fold_high.origin_request_sequence,
                    "fold_high_folded_from": fold_high.folded_from_sequence,
                    "fold_high_canonical_unchanged": fold_high.canonical_application_unchanged,
                    "fold_low_effective": fold_low.effective_request_sequence,
                    "fold_low_folded_from": fold_low.folded_from_sequence,
                    "room_latest_durable_app": str(
                        fence_room_row.latest_durable_application_id
                    ),
                    "room_latest_durable_sequence": int(
                        fence_room_row.latest_durable_sequence
                    ),
                    "application_id": str(application_id),
                }
                # 🔴 必须 commit：下面「跨 room / 跨 generation」两个场景要用**真实存在**
                # 的 application。rollback 掉之后它们会双双落到「application 不存在」这条
                # 分支上 —— 两个场景于是都通过，却都没有验证归属/代际判据（首轮实测就是
                # 这样：`cross_room` 的诊断文本是「application 不存在」）。
                await s.commit()

            # 同 canonical application 自我 supersede 必须被拒（独立 session：
            # 上一段已 commit，异常也不会污染它）。
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                try:
                    await repo.supersede_application(
                        old_application_id=application_id,
                        new_application_id=application_id,
                    )
                    snap["fence"]["self_supersede_error"] = None
                except SyncDomainError as exc:
                    snap["fence"]["self_supersede_error"] = _err(exc)
                    snap["fence"]["self_supersede_code"] = getattr(exc, "error_code", None)
                await s.rollback()

            # 另一代际的 room（room2 是 generation 2）也必须被拒 —— 与下面那条同属
            # 「归属」判据（application 的 room_id 与 generation 由 V151 双双 immutable，
            # 所以「同 room 不同 generation」在库里根本不可能存在，见 `_load_application`
            # 的 docstring 与下面的 DB 不变量断言）。
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                try:
                    await svc.advance_server_last_applied(
                        room_id=room2_id,
                        content_version_id=cv_id,
                        application_id=application_id,
                    )
                    snap["fence"]["cross_generation_error"] = None
                except SyncDomainError as exc:
                    snap["fence"]["cross_generation_error"] = _err(exc)
                    snap["fence"]["cross_generation_code"] = getattr(
                        exc, "error_code", None
                    )
                await s.rollback()
            # DB 不变量：room.generation / application.room_id / application.generation
            # 三者 immutable —— 这是「服务层不需要第二道 generation 检查」的**唯一**依据。
            async with Session() as s:
                probes: dict[str, str | None] = {}
                for label, stmt in (
                    (
                        "room_generation",
                        sa.update(WorkpaperOoRoom)
                        .where(WorkpaperOoRoom.id == room2_id)
                        .values(generation=99),
                    ),
                    (
                        "application_room_id",
                        sa.text(
                            "UPDATE working_paper_content_application SET room_id = :rid "
                            "WHERE id = :aid"
                        ).bindparams(rid=str(room2_id), aid=str(application_id)),
                    ),
                    (
                        "application_generation",
                        sa.text(
                            "UPDATE working_paper_content_application SET generation = 99 "
                            "WHERE id = :aid"
                        ).bindparams(aid=str(application_id)),
                    ),
                ):
                    try:
                        await s.execute(stmt)
                        await s.flush()
                        probes[label] = None
                    except Exception as exc:  # noqa: BLE001 - 记录实际 DB 异常
                        probes[label] = _err(exc)
                    await s.rollback()
                snap["fence"]["db_immutability"] = probes
            # 跨 room 但**同 generation**：`other_room` 也是 generation 1 ⇒ 只有
            # 「application 不属于本 room」这一条能生效。没有这个场景，把 room 归属判据
            # 删掉会被 generation 判据遮蔽，变异检验必判 GREEN。
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                try:
                    await svc.advance_server_last_applied(
                        room_id=other_room_id,
                        content_version_id=cv_id,
                        application_id=application_id,
                    )
                    snap["fence"]["cross_room_error"] = None
                except SyncDomainError as exc:
                    snap["fence"]["cross_room_error"] = _err(exc)
                    snap["fence"]["cross_room_code"] = getattr(exc, "error_code", None)
                await s.rollback()
            async with Session() as s:
                svc = RoomService(WorkpaperSyncRepository(s))
                try:
                    # 用**已提交**的 room2（fence 阶段整段 rollback，fence_room 不在库里），
                    # 配一个不存在的 application id ⇒ 只有「application 不存在」这条能命中。
                    await svc.fold_same_application_request(
                        room_id=room2_id,
                        application_id=uuid.uuid4(),
                        request_sequence=9,
                    )
                    snap["fence"]["missing_application_error"] = None
                except SyncDomainError as exc:
                    snap["fence"]["missing_application_error"] = _err(exc)
                await s.rollback()

        except Exception as exc:  # noqa: BLE001 - 记录而非穿透
            _phase_failed("fence", exc)

        # ═══ ⑭ freeze 的 base 来自 room 已确认快照，而不是 confirmation 行 ═
        #
        # 这一条是 Property 62 的下半段：`settle_client_baseline` 推进快照之后，下一次
        # forcesave 必须以**新快照**为 base。继续读 immutable 的 confirmation 行会把
        # 「第一次已合并进去的改动」当成本次新改动再合一遍。
        settle_entry = "xlsx/gt-settle-base"
        settle_scope = RoomScope(
            project_id=project_id, wp_id=wp_id, entry_id=settle_entry
        )
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                s_art = await repo.register_artifact(
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=ArtifactKind.canonical,
                    state=ArtifactState.published,
                    relative_path=(
                        f"{base_path}/.versions/{wp_id}/representations/{settle_entry}/g1.xlsx"
                    ),
                    sha256=_d("canonical-settle"),
                    size_bytes=2048,
                    document_type="xlsx",
                )
                s_rep = await repo.create_representation(
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=settle_entry,
                    content_version_id=cv_id,
                    generation=1,
                    document_type="xlsx",
                    artifact_id=s_art.id,
                    artifact_sha256=s_art.sha256,
                    definition_bundle_id=bundle_id,
                    authority_model_definition_id=world["authority"].id,
                    adapter_id="excel.settle.v1",
                    adapter_build_digest=_d("adapter-build"),
                    structure_hash=_d("structure-settle"),
                    identity_inventory_sha256=_d("identity-settle"),
                    reason="content_commit",
                )
                await repo.set_entry_pointer(
                    wp_id=wp_id,
                    entry_id=settle_entry,
                    representation_id=s_rep.id,
                    generation=1,
                )
                s_room, s_bundle = await svc.open_or_reuse_room(
                    settle_scope, representation=s_rep, opened_base_version_id=cv_id
                )
                s_part = await svc.join_participant(
                    settle_scope,
                    room_id=s_room.id,
                    user_id=ids["user_a"],
                    mode=ParticipantMode.edit,
                    permission_epoch=5,
                    lease_token="lease-token-settle",
                )
                s_conf, _ = await svc.confirm_descriptor(
                    settle_scope,
                    room_id=s_room.id,
                    participant_id=s_part.id,
                    representation_id=s_rep.id,
                    content_version_id=cv_id,
                    projection_sha256=projection_sha,
                    idempotency_key="settle-confirm-1",
                    expected_bundle=s_bundle,
                )
                room_row, part_row, conf_row = await svc.assert_can_initiate_request(
                    room_id=s_room.id, participant_id=s_part.id
                )
                first = await svc.build_request_freeze(
                    room=room_row,
                    participant=part_row,
                    confirmation=conf_row,
                    client_edit_epoch=1,
                )
                s_applied_art = await repo.register_artifact(
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=ArtifactKind.projection,
                    state=ArtifactState.published,
                    relative_path=(
                        f"{base_path}/.versions/{wp_id}/projections/settle-v2.json.gz"
                    ),
                    sha256=_d("settle-applied"),
                    size_bytes=1024,
                    document_type="json.gz",
                )
                s_applied_cv = await repo.create_content_version(
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=settle_entry,
                    revision=4,  # per-wp 唯一：2 归 baselines、3 归 fence
                    source="onlyoffice",
                    projection_artifact_id=s_applied_art.id,
                    projection_sha256=s_applied_art.sha256,
                    parent_version_id=cv_id,
                )
                settled = await svc.settle_client_baseline(
                    room_id=s_room.id,
                    merged_projection_sha256=_d("settle-equal"),
                    incoming_projection_sha256=_d("settle-equal"),
                    applied_content_version_id=s_applied_cv.id,
                    applied_representation_id=s_rep.id,
                    bundle=s_bundle,
                )
                room_row2, part_row2, conf_row2 = await svc.assert_can_initiate_request(
                    room_id=s_room.id, participant_id=s_part.id
                )
                second = await svc.build_request_freeze(
                    room=room_row2,
                    participant=part_row2,
                    confirmation=conf_row2,
                    client_edit_epoch=2,
                )
                snap["freeze_base"] = {
                    "settled": settled.client_baseline_advanced,
                    "confirmation_version": str(conf_row2.content_version_id),
                    "applied_version": str(s_applied_cv.id),
                    "first_base": str(first.client_base_version_id),
                    "second_base": str(second.client_base_version_id),
                    "second_projection": second.client_base_projection_sha256,
                    "applied_projection": _d("settle-equal"),
                    "same_confirmation_row": (
                        str(conf_row.id) == str(conf_row2.id)
                    ),
                    "fingerprints_differ": (
                        first.frozen_request_fingerprint
                        != second.frozen_request_fingerprint
                    ),
                }
                # contributor 三分：用真实 operation 行落 contributor
                s_outcome = await repo.create_forcesave_request_with_shell(
                    **second.as_repository_kwargs(scope=settle_scope),
                    idempotency_key="settle-req-2",
                )
                s_view = await svc.join_participant(
                    settle_scope,
                    room_id=s_room.id,
                    user_id=ids["user_v"],
                    mode=ParticipantMode.view,
                    permission_epoch=5,
                    lease_token="lease-token-settle-view",
                )
                s_writer_b = await svc.join_participant(
                    settle_scope,
                    room_id=s_room.id,
                    user_id=ids["user_b"],
                    mode=ParticipantMode.edit,
                    permission_epoch=5,
                    lease_token="lease-token-settle-b",
                )
                s_credential = await svc.route_credential(s_room.id)
                contributors = await svc.record_contributor_snapshot(
                    operation_id=s_outcome.operation.id,
                    room_id=s_room.id,
                    initiator_participant_id=s_part.id,
                    route_credential=s_credential,
                    oo_contributor_user_ids=[ids["user_b"], ids["user_v"]],
                )
                rows = (
                    (
                        await s.execute(
                            sa.select(WorkpaperSyncOperationContributor).where(
                                WorkpaperSyncOperationContributor.operation_id
                                == s_outcome.operation.id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                snap["contributors"] = {
                    "contract_source": contributors.contract_source,
                    "initiator": str(contributors.initiator_participant_id),
                    "route_credential": str(contributors.route_credential_id),
                    "route_is_not_initiator": (
                        str(contributors.route_credential_id)
                        != str(contributors.initiator_participant_id)
                    ),
                    "rows": sorted(
                        (str(row.participant_id), row.source, row.confidence)
                        for row in rows
                    ),
                    "digest": contributors.contributor_snapshot_digest,
                    "view_excluded": str(s_view.id)
                    not in {str(row.participant_id) for row in rows},
                    "writer_b_included": str(s_writer_b.id)
                    in {str(row.participant_id) for row in rows},
                    "request_initiator_column": str(
                        s_outcome.request.initiated_by_participant_id
                    ),
                }
                # 只读 participant 不得作为 initiator
                try:
                    await svc.record_contributor_snapshot(
                        operation_id=s_outcome.operation.id,
                        room_id=s_room.id,
                        initiator_participant_id=s_view.id,
                        route_credential=s_credential,
                    )
                    snap["contributors"]["view_initiator_error"] = None
                except SyncDomainError as exc:
                    snap["contributors"]["view_initiator_error"] = _err(exc)
                    snap["contributors"]["view_initiator_code"] = getattr(
                        exc, "error_code", None
                    )
                await s.rollback()

        except Exception as exc:  # noqa: BLE001 - 记录而非穿透
            _phase_failed("freeze_base", exc)

        snap["room_states"] = {s.value for s in RoomState}
        snap["request_states"] = {s.value for s in RequestState}
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
    """一次采集，全部场景共用（避免每测试各自 async 污染共享连接池）。"""
    return asyncio.run(_collect())


# ═══════════════════════════════════════════════════════════════════════════
# 断言
# ═══════════════════════════════════════════════════════════════════════════


def test_ran_on_real_postgresql_in_scratch_schema(snap: dict[str, Any]) -> None:
    assert "PostgreSQL" in (snap["server_version"] or ""), snap["server_version"]
    assert snap["schema"].startswith(_SCHEMA_PREFIX)
    assert snap["apply_errors"] == []


def test_no_happy_path_phase_crashed_during_collection(snap: dict[str, Any]) -> None:
    """采集完整性：任何 happy-path 阶段崩掉都必须在这里显性打红。

    这条不是「多余的自检」。它是「异常不得穿透采集函数」这个决定的另一半：阶段异常被
    记录而不是抛出之后，若没有本断言，一个把某阶段打崩的回归就会变成「那一段的断言全
    是 stale 数据、但测试全绿」。
    """
    assert snap["harness_errors"] == {}, (
        f"采集阶段异常（会让后续断言读到 stale/缺失数据）: {snap['harness_errors']}"
    )


def test_property_6_room_doc_key_comes_from_stable_identity(snap: dict[str, Any]) -> None:
    """AC 2.7：落库的 doc_key 必须等于稳定身份 + generation 的派生值。"""
    o = snap["open_room"]
    assert o["doc_key"] == o["expected_doc_key"], (
        f"room 落库 doc_key={o['doc_key']} ≠ 派生值 {o['expected_doc_key']}"
    )
    assert o["generation"] == 1
    assert o["state"] == "opening", "room 必须先 opening，descriptor 确认后才 active"
    assert o["write_fence_epoch"] == 1
    assert o["latest_request_sequence"] == 0 and o["latest_durable_sequence"] == 0


def test_room_cannot_reuse_representation_of_another_entry(snap: dict[str, Any]) -> None:
    assert snap["open_room"]["cross_entry_error"] is not None, (
        "room 与 representation 的 entry 不一致时必须拒绝 —— 否则 doc_key 指向的入口"
        "与实际打开的文件不是一回事"
    )


def test_ac_2_6_participant_lease_is_per_user_in_shared_room(snap: dict[str, Any]) -> None:
    """AC 2.6：room 共享，但 lease 逐人；lease token 只存 hash。"""
    lease = snap["lease"]
    assert lease["shared_room"] is True, "同 wp+entry+generation 的三人必须在同一 room"
    assert lease["distinct_hashes"] is True, "逐人 lease 不得共用同一 token"
    assert lease["token_hash_a"] == lease["token_plain_sha"], (
        "lease token 必须以 sha256 落库（明文只在 join 时出现一次）"
    )
    assert lease["joined_fence"] == lease["room_fence"]
    assert lease["mode_v"] == "view"
    assert lease["state_a"] == "active"


def test_ac_3_7_forcesave_blocked_before_descriptor_confirmation(
    snap: dict[str, Any]
) -> None:
    """确认前不得 forcesave，且诊断必须指向「去调 confirm-descriptor」这个可操作动作。

    room 仍 `opening` 与「无人确认过 descriptor」是同一个事实（room 只在首个有效
    confirmation 到达时才 active），所以这里期望 `DescriptorNotConfirmedError` 而不是
    笼统的 `room_not_writable` —— 后者让前端无从下手。
    """
    err = snap["eligibility"]["before_confirm"]
    assert err is not None, "descriptor 未确认时 forcesave 必须被拒（AC 3.7）"
    assert "DescriptorNotConfirmedError" in err, err
    assert "opening" in err, err


def test_confirm_descriptor_activates_room_and_sets_client_baseline(
    snap: dict[str, Any]
) -> None:
    e = snap["eligibility"]
    assert e["after_confirm_room_state"] == "active"
    baseline = e["client_baseline"]
    assert all(baseline.values()), f"client-confirmed 五元组必须整体写入: {baseline}"
    assert e["server_last_applied_after_confirm"] is None, (
        "Property 62：confirm descriptor 只建立 client 基线，不得顺手推进 server "
        "last-applied —— 那会把「编辑器已打开」当成「服务端已应用」"
    )


def test_descriptor_confirmation_freezes_typed_slot_inventory(
    snap: dict[str, Any]
) -> None:
    assert snap["eligibility"]["confirmation_slots_digest"] == (
        snap["open_room"]["bundle_slots_digest"]
    ), "confirmation 与 room 必须冻结同一份 typed-slot inventory digest"


def test_stale_descriptor_bundle_identity_is_rejected(snap: dict[str, Any]) -> None:
    err = snap["eligibility"]["drifted_descriptor_error"]
    assert err is not None and "BundleIdentityDrift" in err, err


def test_ac_4_1_request_freeze_uses_confirmed_base_and_stable_fingerprint(
    snap: dict[str, Any]
) -> None:
    f = snap["freeze"]
    assert f["client_base_is_confirmed_base"] is True, (
        "AC 4.11：连续 forcesave 只能用 request 冻结的 client-confirmed base"
    )
    assert f["stable_across_contributor_order"] is True, (
        "contributor 到达序不得影响 fingerprint，否则合法重放被误判 409"
    )
    assert f["changes_with_edit_epoch"] is True
    assert f["changes_with_contributor_set"] is True
    assert f["write_fence_epoch"] == 1
    assert f["kind"] == "forcesave"


def test_freeze_covers_every_repository_parameter(snap: dict[str, Any]) -> None:
    """`RequestFreeze` 必须覆盖 repository 需要的全部冻结入参（少一项即 fingerprint 失真）。"""
    assert set(snap["freeze"]["repo_kwargs_keys"]) == {
        "project_id",
        "wp_id",
        "entry_id",
        "room_id",
        "kind",
        "initiated_by_participant_id",
        "initiator_permission_epoch",
        "client_edit_epoch",
        "client_base_version_id",
        "client_base_representation_id",
        "client_base_projection_sha256",
        "definition_bundle_id",
        "authority_model_definition_id",
        "adapter_build_digest",
        "contributor_snapshot_digest",
        "frozen_request_fingerprint",
    }


def test_accepted_request_creates_pre_correlation_shell_only(
    snap: dict[str, Any]
) -> None:
    """AC 4.1：冻结事务只建 `application_id=NULL` shell，绝不预建 application。"""
    f = snap["freeze"]
    assert f["request_state"] == "frozen"
    assert f["request_sequence"] == 1
    assert f["operation_application_id"] is None
    assert f["operation_duplicate_of"] is None


@pytest.mark.parametrize(
    "case,expected_type",
    [
        ("unconfirmed_second_participant", "DescriptorNotConfirmedError"),
        ("view_mode", "ParticipantNotWritableError"),
        ("stale_descriptor_fence", "WriteFenceStaleError"),
        ("close_capture_from_client", "RoomPolicyError"),
        ("foreign_participant", "ParticipantNotWritableError"),
        ("revoked_participant", "ParticipantNotWritableError"),
        ("expired_lease", "ParticipantNotWritableError"),
        ("room_fence_bumped", "WriteFenceStaleError"),
        ("invalidated_confirmation", "DescriptorNotConfirmedError"),
        ("new_editor_after_barrier", "RoomNotWritableError"),
        # 下面三条刻意与上面的「近亲」分开：它们各自只让**一条**判据可能生效，
        # 用来证明相邻判据没有互相遮蔽（首轮变异实测三处遮蔽）。
        ("participant_joined_at_older_fence", "WriteFenceStaleError"),
        ("cross_room_participant", "ParticipantNotWritableError"),
        ("settle_with_blank_digest", "RoomPolicyError"),
    ],
)
def test_property_15_every_rejection_branch_has_its_own_error_type(
    snap: dict[str, Any], case: str, expected_type: str
) -> None:
    """Property 15：九条拒绝路径逐条独立可变异，且各自有专属 error 类型。

    共用一个笼统异常时，删掉任意一条门都会被别的分支遮蔽 ⇒ 变异检验判 GREEN。
    """
    err = snap["eligibility"][case]
    assert err is not None, f"{case}: 必须在 Command Service 之前被拒"
    assert err.startswith(expected_type), f"{case}: 期望 {expected_type}，实得 {err}"


def test_foreign_participant_does_not_leak_object_existence(snap: dict[str, Any]) -> None:
    """跨 room 使用 participant id 与「不存在」必须走同一 oracle（AC 10.6）。"""
    assert "participant 不存在" in snap["eligibility"]["foreign_participant"]


def test_property_62_server_last_applied_advances_unconditionally(
    snap: dict[str, Any]
) -> None:
    a = snap["baselines"]["server_advance"]
    assert a["before_server"] is None
    assert a["after_server"], "application 成功后必须无条件推进 server last-applied"
    assert a["client_unchanged"] is True, (
        "Property 62：推进 server last-applied 不得同时改动 client-confirmed —— "
        "合并成一个指针会让服务器自己合并出来的值被当成「用户没改过」而丢弃"
    )
    assert a["room_state"] == "active"


def test_property_62_client_baseline_advances_only_on_equivalence(
    snap: dict[str, Any]
) -> None:
    e = snap["baselines"]["equal_settle"]
    assert e["advanced"] is True and e["refresh_required"] is False
    assert e["next_request_allowed"] is True
    assert e["client_projection"], "等值时必须把 merged projection 写成新 client 基线"


def test_ac_2_9_unequal_merge_forces_refresh_required_and_blocks_next_request(
    snap: dict[str, Any]
) -> None:
    u = snap["baselines"]["unequal_settle"]
    assert u["advanced"] is False and u["refresh_required"] is True
    assert u["next_request_allowed"] is False
    assert u["room_state"] == "refresh_required"
    assert u["refresh_reason"] == "merged_projection_differs_from_incoming"
    assert u["client_version_kept"], "不等值时 client 基线必须保持旧值"
    nxt = snap["baselines"]["next_request_after_refresh"]
    assert nxt is not None and nxt.startswith("RoomNotWritableError"), (
        "refresh-required 必须立刻拒绝下一次 forcesave（AC 2.9 / 4.11）"
    )


def test_property_63_writer_revocation_bumps_fence_and_cancels_requests(
    snap: dict[str, Any]
) -> None:
    r = snap["revoke"]
    assert r["writer_decision"] == "write_fence_plus_generation_rotation", (
        "撤销裁决必须来自 Task 4 契约：OO 的 c=drop 只证明会话被逐出，不证明已合入内容"
        "被移除 ⇒ 必须提升 fence 并旋转 generation"
    )
    assert r["writer_generation_rotated"] is True
    assert r["fence_after_writer"] == r["fence_before"] + 1
    assert r["cancelled_request_ids"], "outstanding request 必须被取消（AC 4.7）"
    assert r["request_a_state"] == "superseded"
    assert r["room_state"] == "refresh_required"
    assert r["participant_state"] == "revoked"
    assert r["oo_drop_confirmed_at_set"] is True


def test_view_participant_revocation_does_not_rotate_generation(
    snap: dict[str, Any]
) -> None:
    """只读会话撤销不污染内容 ⇒ 不该把所有人踢出去重开。"""
    r = snap["revoke"]
    assert r["view_generation_rotated"] is False
    assert r["view_decision"] == "view_participant_no_fence_change"
    assert r["fence_after_view"] == r["fence_before"]


def test_ac_2_8_supersede_rotates_doc_key_for_new_generation(snap: dict[str, Any]) -> None:
    s = snap["supersede"]
    assert s["state"] == "superseded" and s["superseded_at_set"] is True
    assert s["new_generation"] == 2
    assert s["doc_key_rotated"] is True, (
        "新 generation 必须得到新 doc_key，否则 OO 会把新旧代际当成同一个文档"
    )
    assert s["new_room_fence"] == 1, "新 room 从 fence=1 起算"


def test_ac_2_8_same_generation_reuses_room_instead_of_creating_second(
    snap: dict[str, Any]
) -> None:
    """确定性 doc_key 的必然结论：一个 generation 一个 room，第二次调用必须复用。

    这条与 V151 的两条唯一约束（`uq_wpoor_doc_key` / `uq_wpoor_generation`）互相印证。
    旧实现靠 mtime 每次生成新 key，看不出「一代际一 room」这个事实 —— 那正是 Property 6
    要消灭的行为。
    """
    s = snap["supersede"]
    assert s["reuse_error"] is None, (
        "同 generation 第二次 open 抛异常 —— 复用退化成「总是新建」会直接撞 "
        f"uq_wpoor_generation：{s['reuse_error']}"
    )
    assert s["reused_is_room2"] is True, (
        f"同 generation 第二次 open 必须返回既有 room，实得 {s['reuse_same_generation_room_id']}"
    )


def test_superseded_generation_cannot_be_reopened(snap: dict[str, Any]) -> None:
    """同代际在唯一约束下永不可重开 ⇒ 必须显式报错要求先旋转 generation。

    场景取的是撤销 writer 后的真实时序：`supersede_room` 之后、**新代际还没发布**，
    entry pointer 仍指向该代际。这是这条诊断唯一可达的窗口 —— 等新代际发布后，准入门
    的「不再是 published 代际」会先命中并把它整条遮蔽（见下一条）。
    """
    err = snap["supersede"]["reopen_superseded_generation_error"]
    assert err is not None and err.startswith("RoomNotWritableError"), err
    assert "uq_wpoor_generation" in err, (
        "诊断必须点明是唯一约束禁止同代际重建，否则调用方会反复重试"
    )


def test_historical_generation_is_rejected_by_the_publication_gate(
    snap: dict[str, Any]
) -> None:
    """新代际发布之后，旧代际由**准入门**拒绝（根因是「不再 published」）。

    与上一条配对存在：两条断言把分支的**遮蔽顺序**钉住了。只留一条时，改动准入门与
    room-state 门的先后会静默改变用户看到的诊断，而没有任何测试会红。
    """
    err = snap["supersede"]["reopen_after_new_generation_error"]
    assert err is not None, "旧代际必须被拒"
    assert err.startswith("RepresentationNotPublishedError"), err


def test_property_5_room_service_only_flushes(snap: dict[str, Any]) -> None:
    """服务层不持有事务边界 —— rollback 后库里零行。"""
    assert snap["flush_only"]["rows_after_rollback"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# representation 准入（AC 2.5 / 2.10）
# ═══════════════════════════════════════════════════════════════════════════


def test_admission_gate_lets_the_published_representation_through(
    snap: dict[str, Any]
) -> None:
    """正向自检：准入门不是恒拒。

    没有这一条，下面三条「必须被拒」在门被写成 `raise` 常量时也全绿 —— 那是最典型的
    「守卫把错值当基线」。
    """
    a = snap["admission"]
    assert a["published_ok"], "published/current representation 必须能开 room"
    assert a["published_bundle_sha"], "冻结身份必须带 bundle digest"


def test_database_itself_refuses_representation_row_drift(snap: dict[str, Any]) -> None:
    """alias 漂移的**主要**执法点在数据库，先把这条事实钉住。

    V151 的 `trg_wpcr_immutable` 让 representation 整行 immutable，`trg_wpcr_identity`
    又在 INSERT 时把 `definition_bundle_sha256` / authority 与 bundle 双向锁死。所以
    「改一行 representation 的 bundle digest」在库里根本做不到。

    不钉住它的后果：下面那条服务层判据会被当成唯一防线，将来有人删掉 DB trigger 时
    没有任何测试会红。
    """
    err = snap["admission"]["db_refuses_row_drift"]
    assert err is not None, (
        "数据库允许 UPDATE representation 行 —— V151 的 immutable/identity trigger 失效了"
    )
    assert "immutable" in err or "check_violation" in err or "CheckViolation" in err, err


@pytest.mark.parametrize(
    "case,expected_code",
    [
        ("no_pointer", "representation_not_published"),
        ("staged_candidate", "representation_not_published"),
        ("alias_drift", "bundle_alias_drift"),
        ("authority_drift", "bundle_alias_drift"),
    ],
)
def test_only_published_non_candidate_drift_free_representation_enters_room(
    snap: dict[str, Any], case: str, expected_code: str
) -> None:
    """AC 2.5 / 2.10：三条准入判据各自独立可变异，且 error_code 不共用。

    * `no_pointer` —— 有 representation 行 ≠ 已发布；AC 2.5 要求 published representation。
    * `staged_candidate` —— 未 finalize 的 upgrade candidate 的 staged 产物
      「resolver/room/current pointer 均不得读取」。
    * `alias_drift` / `authority_drift` —— 调用方传进来的 representation **对象**上，
      冻结的 bundle digest / authority definition 与 bundle 行当前值不等，说明 bundle
      在发布之后被 registry alias 换了内容；此时进 room 会让 descriptor 冻结一份
      「id 相同、内容已换」的假身份（AC 2.10）。库里的行改不动（见上一条），但
      coordinator 手里那份 detached 副本可以陈旧 —— 这才是服务层这道门的可达路径。

    共用一个 error_code 时，先命中的分支会遮蔽后面的，删掉被遮蔽那条的变异必判
    GREEN —— 本 spec 已为这条教训付过一次代价，故此处按 code 逐条断言。
    """
    err = snap["admission"][case]
    assert err is not None, f"{case}: 必须拒绝"
    assert snap["admission"][f"{case}_code"] == expected_code, (
        f"{case}: 期望 error_code={expected_code}，实得 "
        f"{snap['admission'][f'{case}_code']!r}（{err}）"
    )


# ═══════════════════════════════════════════════════════════════════════════
# route credential（AC 2.6 末句 / Property 63）
# ═══════════════════════════════════════════════════════════════════════════


def test_route_credential_is_minted_from_the_room_row_not_the_caller(
    snap: dict[str, Any]
) -> None:
    """凭证三元组必须来自 room 行。

    从调用方入参取的后果：调用方给的 doc_key/generation 可能来自一份陈旧 descriptor，
    那样签出的凭证会让旧代际的 callback 一直合法，AC 2.8 的 supersede 就失效了。
    """
    r = snap["route"]
    assert r["matches_room_row"] is True, "凭证与 room 行三元组重算值不一致"
    assert r["generation"] == 2, "必须用 room 当前 generation"
    assert r["doc_key"].startswith("wpsync-")
    assert r["not_a_participant"] is True, (
        "route credential 不得等于任何 participant id —— Task 4 §3 实证 route participant、"
        "forcesave initiator 与 contributors 三者不同一"
    )


def test_route_credential_of_another_generation_is_rejected(snap: dict[str, Any]) -> None:
    err = snap["route"]["stale_generation_error"]
    assert err is not None, "换 generation 的凭证必须被拒"
    assert snap["route"]["stale_generation_code"] == "route_credential_invalid", err


# ═══════════════════════════════════════════════════════════════════════════
# canonical fence 与 same-application fold（AC 2.9 / 10.11 / Property 36）
# ═══════════════════════════════════════════════════════════════════════════


def test_server_advance_also_points_room_canonical_fence_at_that_application(
    snap: dict[str, Any]
) -> None:
    """AC 10.11：server 指针与 canonical fence 必须在同一事务里一起定。

    拆成两步的后果：会出现「server 已推进、canonical fence 还指着上一个 application」
    的中间态，而 Task 27 的 resolve 先比 canonical application identity、再比 effective
    sequence，读到那个中间态会把一次合法 resolve 判成 stale。
    """
    a = snap["baselines"]["server_advance"]
    assert a["canonical_application"] == a["expected_application"], (
        f"返回的 canonical application {a['canonical_application']} ≠ 实际 application "
        f"{a['expected_application']}"
    )
    assert a["room_canonical_application"] == a["expected_application"], (
        "room 行上的 latest_durable_application_id 没有跟着推进"
    )
    assert a["room_durable_sequence"] >= 1


def test_same_application_higher_request_only_folds_effective_sequence(
    snap: dict[str, Any]
) -> None:
    """AC 10.11 / Property 36：同 application key 的较高 request 只 fold。

    三件事同时成立才算对：
    1. `effective_request_sequence` 单调提升到 GREATEST；
    2. `origin_request_sequence` **一个字节都不动**（它是 application 的不可变身份成分）；
    3. room canonical fence 仍指向**同一个** application。
    """
    f = snap["fence"]
    origin = f["origin_sequence"]
    assert f["fold_high_origin"] == origin, (
        "fold 改动了 origin_request_sequence —— 它是不可变身份成分"
    )
    assert f["fold_high_effective"] == origin + 4, (
        f"effective 未提升到 GREATEST：{f['fold_high_effective']} ≠ {origin + 4}"
    )
    assert f["fold_high_folded_from"] == origin, "未记录 fold 起点"
    assert f["fold_high_canonical_unchanged"] is True, (
        "fold 之前 room canonical fence 就该已经指向同一 application"
    )
    assert f["room_latest_durable_app"] == f["application_id"], (
        "fold 之后 room canonical fence 必须仍指向同一 application"
    )
    assert f["room_latest_durable_sequence"] == origin + 4


def test_lower_request_sequence_never_regresses_effective_sequence(
    snap: dict[str, Any]
) -> None:
    """较低 sequence 的迟到 request 不得把 effective 拉回去（单调性）。"""
    f = snap["fence"]
    assert f["fold_low_effective"] == f["origin_sequence"] + 4, (
        f"较低 sequence 把 effective 拉回到 {f['fold_low_effective']}"
    )
    assert f["fold_low_folded_from"] is None, "没有实际提升时不应记 fold 起点"


def test_same_canonical_application_cannot_self_supersede(snap: dict[str, Any]) -> None:
    """Property 36：绝不能按 raw sequence 自我 supersede。

    真实后果：application 把自己标 `superseded` 之后，用户刚提交的 resolve 会被**自己
    的 fold** 判成 stale，前端表现为「反复 409、永远保存不上」，而两侧数据都没错。
    """
    err = snap["fence"]["self_supersede_error"]
    assert err is not None, "self-supersede 必须被拒"
    assert "self-supersede" in err or "SupersedeError" in err, err


@pytest.mark.parametrize(
    "case",
    ["cross_generation_error", "cross_room_error", "missing_application_error"],
)
def test_fence_refuses_application_outside_this_room(
    snap: dict[str, Any], case: str
) -> None:
    """别的 room 的 / 不存在的 application 不得推进本 room 的 fence。

    跨 room 等价于「用别的文档的 durable 事实给本房间放行」；不存在时静默通过则会让
    fence 指向一个悬空 FK。

    `cross_room_error` 用的是**同 generation** 的另一个 room，所以只有「归属」这一条
    判据能生效 —— 没有这个场景，把归属判据删掉会被别的分支遮蔽。
    """
    err = snap["fence"][case]
    assert err is not None, f"{case}: 必须拒绝"
    assert "CanonicalFenceError" in err or "canonical_fence" in err, err
    if case == "cross_room_error":
        assert snap["fence"]["cross_room_code"] == "canonical_fence_violation", err
        assert "属于 room" in err, f"必须是归属判据命中，实得 {err}"
    if case == "cross_generation_error":
        assert snap["fence"]["cross_generation_code"] == "canonical_fence_violation", err


def test_application_room_and_generation_are_db_immutable(snap: dict[str, Any]) -> None:
    """room.generation 与 application 的 room_id/generation 三者必须 DB 级 immutable。

    这条是「服务层不需要第二道 `app.generation == room.generation` 检查」的**唯一**依据：
    application 的 generation 由 `correlate_durable_incoming` 在 room row lock 内从
    `req.generation`（= 该 room 当时的 generation）复制而来，三者又都不可改 ⇒
    `app.room_id == room.id` 成立时 generation 必然相等。

    首轮变异 M64（删掉那道 generation 检查）判 GREEN，正是因为它 provably 不可达。
    与其留一段永不执行的分支（下一个人会以为守卫有缺陷而去放宽判据），不如把依据钉在
    这里：哪天 DB 解锁了任一条，本断言打红，那道检查就必须补回来。
    """
    probes = snap["fence"]["db_immutability"]
    for label in ("room_generation", "application_room_id", "application_generation"):
        assert probes.get(label) is not None, (
            f"{label} 可以被 UPDATE ⇒ 「app.generation 必等于 room.generation」不再成立，"
            "`_load_application` 必须补回 generation 检查"
        )


# ═══════════════════════════════════════════════════════════════════════════
# freeze 的 base 取自已确认快照（Property 62 下半段 / AC 4.11）
# ═══════════════════════════════════════════════════════════════════════════


def test_freeze_base_follows_the_settled_snapshot_not_the_confirmation_row(
    snap: dict[str, Any]
) -> None:
    """`settle_client_baseline` 推进快照后，下一次 forcesave 必须以**新快照**为 base。

    confirmation 行是 immutable 的，永远停在打开时那一版。继续读它的后果很具体：第二次
    forcesave 的三方 merge 会以「打开时那一版」为 base，于是第一次已经合进去的改动会被
    当成本次新改动**再合一遍**；若第一次做过冲突裁决，裁决结果会被这次重放覆盖掉。

    判据刻意同时断言「confirmation 行没变」——否则「base 变了」也可能是因为悄悄新建了
    一条 confirmation，那就不是本条要证明的事。
    """
    b = snap["freeze_base"]
    assert b["settled"] is True, "等值 settle 必须推进 client 快照"
    assert b["same_confirmation_row"] is True, (
        "两次 freeze 用的是同一条 confirmation 行（本条要证明的正是「同一 confirmation "
        "下 base 仍跟着快照走」）"
    )
    assert b["first_base"] == b["confirmation_version"], (
        "settle 之前，base 应当就是 confirmation 的版本"
    )
    assert b["second_base"] == b["applied_version"], (
        f"settle 之后 base 仍是旧 confirmation 版本 {b['second_base']} —— "
        f"应当跟到已应用版本 {b['applied_version']}（AC 4.11）"
    )
    assert b["second_projection"] == b["applied_projection"], (
        "projection digest 也必须跟到新快照，否则三方 merge 的 base 侧失真"
    )
    assert b["fingerprints_differ"] is True, (
        "base 不同的两次 request 必须有不同 fingerprint，否则会被当成重放返回旧 request"
    )


# ═══════════════════════════════════════════════════════════════════════════
# contributor 三分（AC 2.6 末句 / Property 44 / Property 63）
# ═══════════════════════════════════════════════════════════════════════════


def test_initiator_route_and_contributor_land_in_three_separate_places(
    snap: dict[str, Any]
) -> None:
    """AC 2.6 末句：initiator / route participant / contributor set 三者不得混同。

    落点必须是三处不同的载体：
    * initiator → `working_paper_forcesave_request.initiated_by_participant_id`
    * route     → room/generation route credential（uuid5，不是任何 participant）
    * contributor → `working_paper_sync_operation_contributor` 逐行
    """
    c = snap["contributors"]
    assert c["contract_source"] == "history.changes[].user", (
        "contributor 来源必须是契约里那一个 —— `users` 在 status 6 只含最后编辑者一人"
    )
    assert c["initiator"] == c["request_initiator_column"], (
        "contributor 快照记的 initiator 必须与 frozen request 那一列是同一人"
    )
    assert c["route_is_not_initiator"] is True
    assert c["route_credential"] != c["initiator"]
    assert c["digest"], "contributor 快照必须产出可比对 digest"


def test_contributor_rows_carry_source_and_confidence_per_task4_evidence(
    snap: dict[str, Any]
) -> None:
    """initiator 是 `exact`，OO 派生的 contributor 恒 `aggregate`。

    Task 4 §4 实测：`c=drop` 之后 `history.changes` **仍然列出**被撤销用户。所以它是
    审计快照而非授权依据（契约 `contributor_snapshot_caveat`）。标 `exact` 就等于把
    审计快照当授权凭据 —— 那正是 `participant_bound_callback_authorization.allowed=false`
    要禁止的东西。
    """
    c = snap["contributors"]
    by_participant = {row[0]: (row[1], row[2]) for row in c["rows"]}
    assert by_participant[c["initiator"]] == ("request_initiator", "exact")
    others = {
        value for key, value in by_participant.items() if key != c["initiator"]
    }
    assert others, "OO 侧 contributor 一条都没落库 ⇒ 审计快照丢了并发贡献者"
    assert others == {("oo_users", "aggregate")}, (
        f"OO 派生 contributor 的 (source, confidence) 必须恒为 (oo_users, aggregate)，"
        f"实得 {sorted(others)}"
    )


def test_view_participant_is_never_recorded_as_contributor(snap: dict[str, Any]) -> None:
    """Property 44：只读会话零内容贡献 —— 即便它出现在 OO 的 history 里。"""
    c = snap["contributors"]
    assert c["view_excluded"] is True, (
        "只读 participant 被记成 contributor —— 它不可能产生内容版本"
    )
    assert c["writer_b_included"] is True, (
        "反向自检：另一个 **写** participant 必须被记进来，否则上一条可能只是因为"
        "「谁都没记」而通过（vacuous truth）"
    )


def test_view_participant_cannot_be_the_initiator(snap: dict[str, Any]) -> None:
    err = snap["contributors"]["view_initiator_error"]
    assert err is not None, "只读 participant 不得作为 forcesave initiator"
    assert snap["contributors"]["view_initiator_code"] == "contributor_snapshot_invalid", err
