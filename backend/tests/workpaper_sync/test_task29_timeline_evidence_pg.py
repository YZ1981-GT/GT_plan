# -*- coding: utf-8 -*-
"""Task 29 真实 PostgreSQL 守卫：append-only timeline 投影、recovery 零 operation、evidence 重算。
spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 29
Requirements: 5.10, 5.11, 12.10, 12.11, 12.12, 13.5, 13.6, 13.10, 14.16
Properties: **P68 / P69 / P70 / P71**

═══ 为什么必须真库 ═══

Task 29 的核心判据是「**库里的行**与 current state 的关系」，替身仓储证不了：

* **P68 的「current state 只是投影」** —— 要证的是：删掉一条真实 event 行、或直接
  `UPDATE` current state，读侧的一致性判定会打红。替身仓储没有「行」可删。
* **claim 前零 operation** —— 三张表的行计数判据。V151 的
  `working_paper_callback_recovery_case.operation_id` 是 nullable FK，
  「claim 前为 NULL」只能在真表上观测。
* **P69/P70 的 evidence 重算** —— recomputer 逐项重读 FK 与 artifact hash；悬挂 FK、
  跨 entry 复用、download-only 出现三实体，全都是「真实行之间的关系」。
* **P71 的 stale** —— `working_paper_sync_test_run` 的 13 个身份列与重算时的现场事实
  逐字段比对。

═══ 隔离与采集 ═══

scratch schema `tmp_task29_evidence_<hex>` + 独立文件根，结束 `DROP SCHEMA CASCADE` +
`rmtree`。全部场景由**一次 `asyncio.run`** 跑完落进快照（module fixture）—— 每个测试
各自开 async 会污染共享连接池（Task 21~28 实测：第二个起
`NoneType has no attribute send`）。采集阶段异常一律**记录不穿透**：穿透会把整个 module
变成 collection ERROR，而 `-rf` 只列 FAILED 不列 ERROR ⇒ 定向变异看不到预期失败项 ⇒
判 GREEN。`test_no_phase_crashed_during_collection` 是这个决定的另一半。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
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

import app.services.workpaper_sync.evidence as EV  # noqa: E402

_SCHEMA_PREFIX = "tmp_task29_evidence_"
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

#: 采集用的 entry。必须是**真实 manifest 里存在的** entry_id：recomputer 从 manifest
#: 取 source-backed profile，编一个不存在的 entry 会走「未登记入口」分支而不是本判据。
ENTRY = "xlsx/gt-d2-accounts-receivable"
OTHER_ENTRY = "xlsx/cash-flow-verification"
#: 第三个 entry：只用来证明「一个 entry 一次 run 都没有」也是 unverified（不是崩）。
ENTRY_WITHOUT_RUN = "xlsx/d4/analysis/d4-tab-indicator"


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _opt(value: object) -> str | None:
    """可空 UUID → `str | None`。`str(None) == "None"` 会把「没写上」判成「写上了」。"""
    return None if value is None else str(value)


def _err(exc: BaseException) -> str:
    import traceback

    frames = traceback.extract_tb(exc.__traceback__)[-8:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - 一次采集覆盖全部场景
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.workpaper_sync_models import (
        WorkpaperCallbackRecoveryCase,
        WorkpaperCallbackRecoveryCaseEvent,
        WorkpaperContentApplication,
        WorkpaperEntryEvidenceScenario,
        WorkpaperSyncOperation,
        WorkpaperSyncOperationEvent,
        WorkpaperSyncTestRun,
    )
    from app.services.workpaper_sync import definitions as D
    from app.services.workpaper_sync import evidence as EV
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.entry_profile import (
        capability_of,
        manifest_entries_by_id,
    )
    from app.services.workpaper_sync.models import (
        ActorType,
        ArtifactKind,
        ArtifactState,
        AuthorityModel,
        BundleSlot,
        OperationState,
        ParticipantMode,
        RecoveryCaseState,
        RecoveryReason,
        RequestKind,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.timeline import (
        ProjectionDefect,
        SyncTimelineService,
        TimelineQuery,
        TimelineStream,
    )

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 29 的判据是「库里的 append-only 行 ↔ current state」与 evidence 逐项"
            "重算，必须真实 PostgreSQL；当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task29_store_"))
    (base_root / "storage").mkdir()
    (base_root / "definition_store").mkdir()

    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "server_version": None,
        "apply_errors": [],
        "harness_errors": {},
        "scenarios": {},
    }

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
            except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言为空
                snap["apply_errors"].append(
                    {"index": idx, "error": _err(exc), "head": stmt[:120]}
                )
        if snap["apply_errors"]:
            raise _HarnessError(f"V151 应用失败: {snap['apply_errors'][:3]}")

        project = uuid.uuid4()
        user_a, user_b = uuid.uuid4(), uuid.uuid4()
        wp = uuid.uuid4()
        other_wp = uuid.uuid4()
        artifacts = CanonicalArtifactRepository(base_root)

        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{project}')")
            for u in (user_a, user_b):
                await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{u}')")
            for w in (wp, other_wp):
                await conn.exec_driver_sql(
                    "INSERT INTO working_paper (id, project_id) VALUES "
                    f"('{w}', '{project}')"
                )

        # ── approved definition bundle ────────────────────────────────
        blobs = {
            name: artifacts.publish_definition_blob(
                project_id=project,
                wp_id=wp,
                definition_kind=kind,
                payload=json.dumps({"k": name}, sort_keys=True).encode(),
            )
            for name, kind in {
                "tpl": "template",
                "instr": "instrumentation",
                "contract": "contract",
                "authority": "authority_model",
                "bundle_payload": "bundle",
            }.items()
        }
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            art = {
                name: await repo.register_artifact(
                    project_id=project,
                    wp_id=wp,
                    kind=ArtifactKind.definition,
                    state=ArtifactState.published,
                    relative_path=pub.relative_path,
                    sha256=pub.sha256,
                    size_bytes=pub.size_bytes,
                    document_type=pub.document_type,
                    retention_class="definition",
                )
                for name, pub in blobs.items()
            }
            tpl = await repo.create_definition_artifact(
                kind="template", logical_id="task29.tpl", semantic_version="1.0.0",
                blob_artifact_id=art["tpl"].id, sha256=_d("task29-template"),
                structure_hash=_d("task29-tpl-structure"), source_commit="task29",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation", logical_id="task29.instr",
                semantic_version="1.0.0", blob_artifact_id=art["instr"].id,
                sha256=_d("task29-instrumentation"),
                structure_hash=_d("task29-instr-structure"), source_commit="task29",
            )
            contract_def = await repo.create_definition_artifact(
                kind="contract", logical_id="task29.contract", semantic_version="1.0.0",
                blob_artifact_id=art["contract"].id, sha256=_d("task29-contract"),
                source_commit="task29",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task29.authority",
                semantic_version="1.0.0", blob_artifact_id=art["authority"].id,
                sha256=_d("task29-authority"),
                authority_model_type="projection_contract", source_commit="task29",
            )

            def _slots() -> dict:
                return {
                    BundleSlot.template: D.definition_slot_spec(
                        BundleSlot.template,
                        definition_id=tpl.id, definition_sha256=tpl.sha256,
                    ),
                    BundleSlot.instrumentation: D.definition_slot_spec(
                        BundleSlot.instrumentation,
                        definition_id=instr.id, definition_sha256=instr.sha256,
                    ),
                    BundleSlot.contract: D.definition_slot_spec(
                        BundleSlot.contract,
                        definition_id=contract_def.id,
                        definition_sha256=contract_def.sha256,
                    ),
                }

            bundle = await repo.create_definition_bundle(
                authority_model_definition_id=authority.id,
                slots=_slots(),
                canonical_payload_artifact_id=art["bundle_payload"].id,
                canonical_payload_sha256=D.bundle_canonical_digest(
                    authority_model="projection_contract",
                    authority_model_definition_sha256=authority.sha256,
                    slots=_slots(),
                ),
            )
            await s.commit()
        bundle_id, bundle_sha = bundle.id, bundle.canonical_payload_sha256
        authority_id, authority_sha = authority.id, authority.sha256

        # ── content version + representation + room + participant ─────
        async def _build_entry(
            target_wp: uuid.UUID, entry_id: str, tag: str
        ) -> dict[str, Any]:
            rep_bytes = b"PK\x03\x04" + json.dumps({"tag": tag}).encode()
            gen1 = artifacts.publish_representation(
                entry_id=entry_id,
                generation=1,
                staged=artifacts.stage_bytes(
                    project_id=project, wp_id=target_wp, payload=rep_bytes,
                    document_type="xlsx",
                ),
                validate_ooxml=False,
            )
            proj = artifacts.publish_projection(
                revision=1,
                staged=artifacts.stage_bytes(
                    project_id=project, wp_id=target_wp,
                    payload=json.dumps({"tag": tag}, sort_keys=True).encode(),
                    document_type="json.gz",
                ),
            )
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                art_rep = await repo.register_artifact(
                    project_id=project, wp_id=target_wp, kind=ArtifactKind.canonical,
                    state=ArtifactState.published, relative_path=gen1.relative_path,
                    sha256=gen1.sha256, size_bytes=gen1.size_bytes, document_type="xlsx",
                )
                art_proj = await repo.register_artifact(
                    project_id=project, wp_id=target_wp, kind=ArtifactKind.projection,
                    state=ArtifactState.published, relative_path=proj.relative_path,
                    sha256=proj.sha256, size_bytes=proj.size_bytes,
                    document_type="json.gz",
                )
                cv = await repo.create_content_version(
                    project_id=project, wp_id=target_wp, entry_id=entry_id, revision=1,
                    source="html", projection_artifact_id=art_proj.id,
                    projection_sha256=proj.sha256, actor_id=user_a,
                )
                rep = await repo.create_representation(
                    project_id=project, wp_id=target_wp, entry_id=entry_id,
                    content_version_id=cv.id, generation=1, document_type="xlsx",
                    artifact_id=art_rep.id, artifact_sha256=gen1.sha256,
                    definition_bundle_id=bundle_id,
                    authority_model_definition_id=authority_id,
                    adapter_id="task29.adapter",
                    adapter_build_digest=_d("task29-adapter"),
                    structure_hash=_d(f"task29-structure-{tag}"),
                    identity_inventory_sha256=_d(f"task29-identity-{tag}"),
                    reason="content_commit",
                )
                room = await repo.create_room(
                    project_id=project, wp_id=target_wp, entry_id=entry_id,
                    doc_key=_d(f"task29-dock-{tag}")[:40], generation=1,
                    opened_base_version_id=cv.id,
                )
                participant = await repo.create_participant(
                    project_id=project, wp_id=target_wp, entry_id=entry_id,
                    room_id=room.id, user_id=user_a, mode=ParticipantMode.edit,
                    permission_epoch=1, lease_token_hash=_d(f"lease-{tag}"),
                )
                confirmation = await repo.create_client_confirmation(
                    project_id=project, wp_id=target_wp, entry_id=entry_id,
                    room_id=room.id, participant_id=participant.id,
                    representation_id=rep.id, content_version_id=cv.id,
                    projection_sha256=proj.sha256,
                    bundle_slots_digest=bundle_sha,
                    idempotency_key=f"confirm-{tag}",
                )
                await s.commit()
            return {
                "wp": target_wp,
                "entry": entry_id,
                "version": cv.id,
                "representation": rep.id,
                "artifact": art_rep.id,
                "artifact_sha256": gen1.sha256,
                "room": room.id,
                "participant": participant.id,
                "confirmation": confirmation.id,
            }

        main = await _build_entry(wp, ENTRY, "main")
        other = await _build_entry(other_wp, OTHER_ENTRY, "other")

        # ── 一条正常的 forcesave → durable correlation → primary ──────
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            accepted = await repo.create_forcesave_request_with_shell(
                project_id=project, wp_id=wp, entry_id=ENTRY, room_id=main["room"],
                kind=RequestKind.forcesave,
                initiated_by_participant_id=main["participant"],
                initiator_permission_epoch=1, client_edit_epoch=1,
                client_base_version_id=main["version"],
                client_base_representation_id=main["representation"],
                client_base_projection_sha256=_d("task29-base-projection"),
                definition_bundle_id=bundle_id,
                authority_model_definition_id=authority_id,
                adapter_build_digest=_d("task29-adapter"),
                contributor_snapshot_digest=_d("task29-contributors"),
                idempotency_key="fs-1",
                frozen_request_fingerprint=_d("task29-fingerprint-1"),
                created_by=user_a,
            )
            await s.commit()
        request_id = accepted.request.id
        shell_id = accepted.operation.id
        shell_application_before = accepted.operation.application_id

        # durable incoming：**先有 delivery**（V151 的 `ck_wpa_incoming_requires_delivery`
        # 与 `trg_wpa_incoming_path` 都以 delivery identity 为准），路径按
        # `.incoming/{wp_id}/{delivery_id}/` sealing。刻意不走 `seal_incoming()`：
        # 那条路要真实 OOXML 过安全门，而本文件要证的是 timeline/evidence 的关系，
        # 不是 OOXML 安全（那是 Task 11 的判据面）。
        async def _durable_incoming(
            *, label: str, target_room: uuid.UUID, request_ref: uuid.UUID | None,
            operation_ref: uuid.UUID | None,
        ) -> tuple[uuid.UUID, uuid.UUID]:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                delivery = await repo.record_delivery(
                    project_id=project, wp_id=wp, entry_id=ENTRY, room_id=target_room,
                    generation=1, route_credential_id=uuid.uuid4(), callback_status=6,
                    delivery_key=_d(f"task29-delivery-{label}"),
                    payload_sha256=_d(f"task29-payload-{label}"),
                    forcesave_request_id=request_ref,
                    operation_id=operation_ref,
                )
                await s.commit()
            payload = json.dumps({"incoming": label}, sort_keys=True).encode()
            digest = hashlib.sha256(payload).hexdigest()
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                artifact = await repo.register_artifact(
                    project_id=project, wp_id=wp, kind=ArtifactKind.incoming,
                    state=ArtifactState.durable,
                    relative_path=(
                        f".incoming/{wp}/{delivery.id}/incoming-{digest[:12]}.xlsx"
                    ),
                    sha256=digest, size_bytes=len(payload), document_type="xlsx",
                    source_delivery_id=delivery.id,
                )
                await s.commit()
            return artifact.id, delivery.id

        incoming_id, main_delivery_id = await _durable_incoming(
            label="main", target_room=main["room"], request_ref=request_id,
            operation_ref=shell_id,
        )

        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            correlation = await repo.correlate_durable_incoming(
                operation_id=shell_id,
                incoming_artifact_id=incoming_id,
                current_revision=1,
                adapter_id="task29.adapter",
            )
            await s.commit()
        application_id = correlation.application.id

        # 走一段真实状态机，让 operation timeline 有多条 event。
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            # 状态边由 `models.ALLOWED_*_TRANSITIONS` 强制（`merging` 不能直达 `applying`，
            # 必须经 `rematerializing` —— canonical rematerialize 是 AC 4.x 的必经一步）。
            for frm, to, stage in (
                (OperationState.application_bound, OperationState.extracting, "extract"),
                (OperationState.extracting, OperationState.merging, "merge"),
                (OperationState.merging, OperationState.rematerializing, "rematerialize"),
                (OperationState.rematerializing, OperationState.applying, "apply"),
                (OperationState.applying, OperationState.applied, "post_durable"),
            ):
                await repo.append_operation_event(
                    operation_id=shell_id, from_state=frm, to_state=to, stage=stage,
                    actor_type=ActorType.system,
                )
            await s.execute(
                sa.update(WorkpaperSyncOperation)
                .where(WorkpaperSyncOperation.id == shell_id)
                .values(state=OperationState.applied.value)
            )
            await s.commit()

        service_snapshots: dict[str, Any] = {}
        async with Session() as s:
            timeline = SyncTimelineService(s)
            healthy = await timeline.operation_timeline(
                operation_id=shell_id,
                declared_project_id=project,
                declared_wp_id=wp,
                declared_entry_id=ENTRY,
            )
            service_snapshots["healthy"] = {
                "events": len(healthy.operation_events),
                "sequence_numbers": [e.sequence_no for e in healthy.operation_events],
                "defects": sorted(
                    d.value for check in healthy.checks for d in check.defects
                ),
                "application_id": _opt(healthy.application_id),
                "server_clock_source": healthy.as_dict()["server_clock_source"],
                "payload_keys": sorted(healthy.operation_events[0].payload) if
                healthy.operation_events else [],
                "raw_json": json.dumps(healthy.as_dict(), ensure_ascii=False),
            }

        # ── ① 直接改 current state：投影必须打红（P68）──────────────
        async with Session() as s:
            await s.execute(
                sa.update(WorkpaperSyncOperation)
                .where(WorkpaperSyncOperation.id == shell_id)
                .values(state=OperationState.error.value)
            )
            await s.commit()
        async with Session() as s:
            diverged = await SyncTimelineService(s).operation_timeline(
                operation_id=shell_id, declared_project_id=project,
                declared_wp_id=wp, declared_entry_id=ENTRY,
            )
            service_snapshots["state_diverged"] = sorted(
                d.value for check in diverged.checks for d in check.defects
            )
        async with Session() as s:
            await s.execute(
                sa.update(WorkpaperSyncOperation)
                .where(WorkpaperSyncOperation.id == shell_id)
                .values(state=OperationState.applied.value)
            )
            await s.commit()

        # ── ② append-only 在**存储层**是否真的强制 ────────────────
        #
        # 🔴 这里刻意不再走「删一条 event 看读侧是否报 sequence_gap」：实测 V151 有
        # 触发器**物理拒绝** DELETE/UPDATE（错误信息逐字写着「删除中间 event / 伪造
        # event / 改写既有 event 一律拒绝」）。也就是说「读侧能不能发现被删的 event」
        # 在真实数据上不可达 —— 那种判据的定向变异会永久 GREEN。
        #
        # 于是这里换成**更强**的判据：证明三类篡改都被数据库拒绝。读侧的
        # `sequence_gap` / `transition_chain_broken` 由离线文件用合成事件覆盖
        # （那边它们可达），两边合起来才是完整的 P68。
        async with Session() as s:
            victim = (
                await s.execute(
                    sa.select(WorkpaperSyncOperationEvent)
                    .where(WorkpaperSyncOperationEvent.operation_id == shell_id)
                    .order_by(WorkpaperSyncOperationEvent.sequence_no)
                    .offset(1)
                    .limit(1)
                )
            ).scalar_one()
            victim_id = int(victim.id)
            victim_sequence = int(victim.sequence_no)

        tamper: dict[str, Any] = {}
        async with Session() as s:
            try:
                await s.execute(
                    sa.delete(WorkpaperSyncOperationEvent).where(
                        WorkpaperSyncOperationEvent.id == victim_id
                    )
                )
                await s.commit()
                tamper["delete"] = None
            except Exception as exc:  # noqa: BLE001 - 记录类型即判据
                await s.rollback()
                tamper["delete"] = type(exc).__name__
        async with Session() as s:
            try:
                await s.execute(
                    sa.update(WorkpaperSyncOperationEvent)
                    .where(WorkpaperSyncOperationEvent.id == victim_id)
                    .values(to_state=OperationState.error.value)
                )
                await s.commit()
                tamper["update"] = None
            except Exception as exc:  # noqa: BLE001
                await s.rollback()
                tamper["update"] = type(exc).__name__
        async with Session() as s:
            try:
                s.add(
                    WorkpaperSyncOperationEvent(
                        operation_id=shell_id,
                        sequence_no=victim_sequence,
                        from_state=OperationState.extracting.value,
                        to_state=OperationState.error.value,
                        stage="forged",
                        actor_type=ActorType.system.value,
                        occurred_at=_now(),
                    )
                )
                await s.commit()
                tamper["duplicate_sequence"] = None
            except Exception as exc:  # noqa: BLE001
                await s.rollback()
                tamper["duplicate_sequence"] = type(exc).__name__
        service_snapshots["tamper"] = tamper

        # 篡改全部被拒 ⇒ 库里行数不变，读侧判据仍应干净。
        async with Session() as s:
            after_tamper = await SyncTimelineService(s).operation_timeline(
                operation_id=shell_id, declared_project_id=project,
                declared_wp_id=wp, declared_entry_id=ENTRY,
            )
            service_snapshots["after_tamper"] = {
                "events": len(after_tamper.operation_events),
                "defects": sorted(
                    d.value for check in after_tamper.checks for d in check.defects
                ),
            }

        # ── ③ 横向 scope：拿别的 wp 的 scope 读本 operation ──────────
        async with Session() as s:
            try:
                await SyncTimelineService(s).operation_timeline(
                    operation_id=shell_id, declared_project_id=project,
                    declared_wp_id=other_wp, declared_entry_id=OTHER_ENTRY,
                )
                service_snapshots["cross_scope_refused"] = False
            except Exception as exc:  # noqa: BLE001 - 记录类型即判据
                service_snapshots["cross_scope_refused"] = type(exc).__name__

        # ── ④ 归并查询：逐 locator ───────────────────────────────────
        async with Session() as s:
            timeline = SyncTimelineService(s)
            by_locator: dict[str, int] = {}
            for locator, value in (
                ("wp_id", wp),
                ("room_id", main["room"]),
                ("request_id", request_id),
                ("participant_id", main["participant"]),
                ("operation_id", shell_id),
                ("application_id", application_id),
            ):
                events = await timeline.merged_timeline(
                    TimelineQuery(**{locator: value}, limit=500)
                )
                by_locator[locator] = len(events)
            correlation_events = await timeline.merged_timeline(
                TimelineQuery(correlation_id=shell_id, limit=500)
            )
            by_locator["correlation_id"] = len(correlation_events)
            service_snapshots["by_locator"] = by_locator
            service_snapshots["streams_seen"] = sorted(
                {
                    e.stream.value
                    for e in await timeline.merged_timeline(
                        TimelineQuery(room_id=main["room"], limit=500)
                    )
                }
            )

        # ── ⑤ recovery case：claim 前后的三实体 ─────────────────────
        crash_incoming_id, crash_delivery_id = await _durable_incoming(
            label="crash", target_room=main["room"], request_ref=None,
            operation_ref=None,
        )
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            case = await repo.create_recovery_case(
                project_id=project, wp_id=wp, entry_id=ENTRY, room_id=main["room"],
                generation=1, source_delivery_key=_d("task29-delivery-crash"),
                incoming_artifact_id=crash_incoming_id,
                reason=RecoveryReason.crash_close,
                candidate_confirmation_digest=_d("task29-candidate"),
                candidate_contributor_digest=_d("task29-contributors"),
            )
            await s.commit()
        case_id = case.id

        async def _entity_counts() -> dict[str, int]:
            async with Session() as s:
                row = (
                    await s.execute(
                        sa.select(
                            WorkpaperCallbackRecoveryCase.recovery_request_id,
                            WorkpaperCallbackRecoveryCase.application_id,
                            WorkpaperCallbackRecoveryCase.operation_id,
                        ).where(WorkpaperCallbackRecoveryCase.id == case_id)
                    )
                ).first()
            return {
                "request": int(row[0] is not None),
                "application": int(row[1] is not None),
                "operation": int(row[2] is not None),
            }

        service_snapshots["pre_claim_entities"] = await _entity_counts()
        async with Session() as s:
            pre_claim = await SyncTimelineService(s).recovery_case_timeline(
                case_id=case_id, declared_project_id=project,
                declared_wp_id=wp, declared_entry_id=ENTRY,
            )
            service_snapshots["pre_claim_timeline"] = {
                "has_three_entities": pre_claim.has_three_entities,
                "claimed_operation_id": _opt(pre_claim.claimed_operation_id),
                "event_count": len(pre_claim.events),
                "keys": sorted(pre_claim.as_dict()),
                "defects": sorted(
                    d.value for check in pre_claim.checks for d in check.defects
                ),
            }

        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            claimed = await repo.claim_recovery_case(
                case_id=case_id,
                claiming_participant_id=main["participant"],
                prior_confirmation_id=main["confirmation"],
                idempotency_key="claim-1",
                current_revision=1,
                adapter_id="task29.adapter",
                adapter_build_digest=_d("task29-adapter"),
                contributor_snapshot_digest=_d("task29-contributors"),
                actor_id=user_a,
            )
            await s.commit()
        service_snapshots["post_claim_entities"] = await _entity_counts()
        service_snapshots["post_claim_shape"] = claimed.shape.value
        async with Session() as s:
            post_claim = await SyncTimelineService(s).recovery_case_timeline(
                case_id=case_id, declared_project_id=project,
                declared_wp_id=wp, declared_entry_id=ENTRY,
            )
            service_snapshots["post_claim_timeline"] = {
                "has_three_entities": post_claim.has_three_entities,
                "event_count": len(post_claim.events),
            }
        claim_application_id = claimed.application.id
        claim_operation_id = claimed.operation.id

        # ── ⑥ evidence：写一个「干净」run + scenario 行，再逐类破坏 ──
        entries_by_id = manifest_entries_by_id()
        manifest_entry = entries_by_id[ENTRY]
        capability = capability_of(manifest_entry)
        required = EV.derive_for_manifest_entry(
            manifest_entry, authority_model=AuthorityModel.projection_contract
        )
        environment = EV.EvidenceEnvironment(
            source_commit="task29commit",
            runner_version="task29-runner:v1",
            onlyoffice_build="9.4.0.42",
            browser_build="Chrome/140.0.0.0",
        )

        evidence_run_seed = uuid.uuid4()
        run_manifest_pub = artifacts.publish_evidence_manifest(
            project_id=project, wp_id=wp, entry_id=ENTRY, test_run_id=evidence_run_seed,
            payload=json.dumps({"run": "task29"}, sort_keys=True).encode(),
        )
        trace_pub = artifacts.publish_trace_bundle(
            project_id=project, wp_id=wp, entry_id=ENTRY, test_run_id=evidence_run_seed,
            scenario_id="task29-shared-trace",
            payload=json.dumps({"trace": "task29"}, sort_keys=True).encode(),
        )
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            run_manifest_artifact = await repo.register_artifact(
                project_id=project, wp_id=wp, kind=ArtifactKind.evidence,
                state=ArtifactState.published,
                relative_path=run_manifest_pub.relative_path,
                sha256=run_manifest_pub.sha256, size_bytes=run_manifest_pub.size_bytes,
                document_type=run_manifest_pub.document_type,
                retention_class="evidence_manifest",
            )
            trace_artifact = await repo.register_artifact(
                project_id=project, wp_id=wp, kind=ArtifactKind.trace_bundle,
                state=ArtifactState.published, relative_path=trace_pub.relative_path,
                sha256=trace_pub.sha256, size_bytes=trace_pub.size_bytes,
                document_type="json.gz", retention_class="trace_bundle",
            )
            await s.commit()

        async def _write_run(
            *,
            entry_id: str,
            required_set: Any,
            overrides: dict[str, Any] | None = None,
            scenario_overrides: dict[str, dict[str, Any]] | None = None,
            skip: set[str] | None = None,
            extra_rows: list[dict[str, Any]] | None = None,
            pool: dict[str, dict[str, Any]] | None = None,
        ) -> uuid.UUID:
            payload = {
                "entry_id": entry_id,
                "source_commit": environment.source_commit,
                "runner_version": environment.runner_version,
                "manifest_source_digest": EV.manifest_source_digest(),
                "editability": required_set.editability.value,
                "room_model": required_set.room_model.value,
                "scenario_profile_digest": required_set.scenario_profile_digest,
                "onlyoffice_build": environment.onlyoffice_build,
                "browser_build": environment.browser_build,
                "environment_digest": environment.digest,
                "required_scenario_set_digest": required_set.digest,
                "authority_model_definition_sha256": authority_sha,
                "definition_bundle_sha256": bundle_sha,
                "run_manifest_artifact_id": run_manifest_artifact.id,
                "run_manifest_sha256": run_manifest_pub.sha256,
                "started_at": _now(),
                "finished_at": _now(),
                "aggregate_result": "passed",
            }
            payload.update(overrides or {})
            # 默认用主 entry 的实体池；跨 entry 复用场景刻意**也**传它，于是
            # 「同一批实体出现在两个 entry 的证据里」是真实构造出来的，不是断言出来的。
            pool = pool if pool is not None else entity_pool
            run = WorkpaperSyncTestRun(id=uuid.uuid4(), **payload)
            rows: list[WorkpaperEntryEvidenceScenario] = []
            ordinal = 0
            for scenario in required_set.scenarios:
                if skip and scenario.scenario_id in skip:
                    continue
                ordinal += 1
                body: dict[str, Any] = {
                    "operation_ids": [],
                    "application_ids": [],
                    "recovery_case_ids": [],
                    "content_version_ids": [],
                    "representation_ids": [],
                }
                # entity 形态按 V151 的三条 kind 约束分支填（与
                # `RequiredScenario.kind` 的推导同一顺序），实体逐场景独占。
                owned = pool.get(scenario.scenario_id) or {}
                if scenario.kind in (
                    EV.ScenarioKind.download_only,
                    EV.ScenarioKind.recovery_reject,
                ):
                    body["recovery_case_ids"] = [str(owned["case"])]
                elif scenario.kind is EV.ScenarioKind.recovery_claim:
                    body["recovery_case_ids"] = [str(owned["case"])]
                    body["operation_ids"] = [str(owned["operation"])]
                    body["application_ids"] = [str(owned["application"])]
                elif scenario.expects_application:
                    body["operation_ids"] = [str(owned["operation"])]
                    body["application_ids"] = [str(owned["application"])]
                    body["content_version_ids"] = [str(main["version"])]
                    body["representation_ids"] = [str(main["representation"])]
                body.update((scenario_overrides or {}).get(scenario.scenario_id, {}))
                rows.append(
                    WorkpaperEntryEvidenceScenario(
                        id=uuid.uuid4(),
                        run_id=run.id,
                        scenario_id=scenario.scenario_id,
                        ordinal=ordinal,
                        scenario_kind=scenario.kind.value,
                        # 一条场景在当前 schema 下无法记成 passed（AC 5.6 的零 application
                        # 与 `ck_wpees_standard_requires_entities` 冲突），已登记在
                        # `SCHEMA_UNREPRESENTABLE_SCENARIOS`。harness 如实落
                        # `unverifiable`，recomputer 会把它记成可归因的独立缺陷。
                        result=(
                            "unverifiable"
                            if scenario.scenario_id in EV.SCHEMA_UNREPRESENTABLE_SCENARIOS
                            else "passed"
                        ),
                        authority_model_definition_sha256=authority_sha,
                        definition_bundle_sha256=bundle_sha,
                        trace_bundle_artifact_id=trace_artifact.id,
                        trace_bundle_sha256=trace_pub.sha256,
                        server_timeline_digest=_d(f"timeline-{scenario.scenario_id}"),
                        database_snapshot_digest=_d(f"db-{scenario.scenario_id}"),
                        browser_build=environment.browser_build,
                        **body,
                    )
                )
            for extra in extra_rows or []:
                ordinal += 1
                rows.append(
                    WorkpaperEntryEvidenceScenario(
                        id=uuid.uuid4(),
                        run_id=run.id,
                        ordinal=ordinal,
                        # `standard` + `passed` 必须带 operation+application
                        # （`ck_wpees_standard_requires_entities`）—— 这条「多出来的
                        # 未登记场景」在库层面完全合法，只有 recomputer 的 required set
                        # 比对能发现它。
                        scenario_kind=EV.ScenarioKind.standard.value,
                        result="passed",
                        authority_model_definition_sha256=authority_sha,
                        definition_bundle_sha256=bundle_sha,
                        trace_bundle_artifact_id=trace_artifact.id,
                        trace_bundle_sha256=trace_pub.sha256,
                        server_timeline_digest=_d("extra"),
                        database_snapshot_digest=_d("extra"),
                        browser_build=environment.browser_build,
                        operation_ids=[str(shell_id)],
                        application_ids=[str(application_id)],
                        recovery_case_ids=[],
                        content_version_ids=[],
                        representation_ids=[],
                        **extra,
                    )
                )
            async with Session() as s:
                s.add(run)
                # 必须先 flush run 行：scenario 行有 `run_id` 外键，SQLAlchemy 的插入
                # 顺序不保证父行先落（实测确实先插了 scenario ⇒ ForeignKeyViolation）。
                await s.flush()
                for row in rows:
                    s.add(row)
                await s.commit()
            return run.id

        async def _write_run_or_refusal(**kwargs: Any) -> tuple[uuid.UUID | None, str | None]:
            """写 run；若被**数据库**拒绝则返回拒绝异常类型名。

            存在的理由：V151 对 evidence 行有三条 kind/entity CHECK，某些「刻意做脏」的
            负面场景根本插不进去。那说明该属性的**首要**执行点在存储层，读侧
            recomputer 的同名检查只是第二道防线 —— 判据应当如实落在「库拒绝了」上，
            而不是假装读侧发现了它（那种判据的定向变异会永久 GREEN）。
            """
            try:
                return await _write_run(**kwargs), None
            except Exception as exc:  # noqa: BLE001 - 记录类型即判据
                return None, type(exc).__name__

        async def _verdict(run_id: uuid.UUID, *, entry_id: str = ENTRY) -> dict[str, Any]:
            async with Session() as s:
                recomputer = EV.EvidenceRecomputer(s)
                verdict = await recomputer.recompute(
                    entry_id=entry_id,
                    authority_model=AuthorityModel.projection_contract,
                    environment=environment,
                    run_id=run_id,
                )
            return verdict.as_dict()

        # 🔴 每条 scenario 必须有**自己的** operation/application/recovery case。
        #
        # 第一版让 24 条 scenario 共用同一对 (operation, application) —— recomputer 立刻
        # 报 `reused_within_run`，而那正是 P70 要禁的形态。也就是说：一个诚实的 harness
        # 本来就必须逐场景造实体，「共用一对」连自己的正面控制都过不去。
        # 造法：每条各自一份 delivery + incoming（payload 不同 ⇒ sha 不同 ⇒ frozen
        # application key 不同）+ 一次 forcesave request/shell + 一次 correlate。
        async def _fresh_application(label: str) -> tuple[uuid.UUID, uuid.UUID]:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                accepted_one = await repo.create_forcesave_request_with_shell(
                    project_id=project, wp_id=wp, entry_id=ENTRY, room_id=main["room"],
                    kind=RequestKind.forcesave,
                    initiated_by_participant_id=main["participant"],
                    initiator_permission_epoch=1, client_edit_epoch=1,
                    client_base_version_id=main["version"],
                    client_base_representation_id=main["representation"],
                    client_base_projection_sha256=_d("task29-base-projection"),
                    definition_bundle_id=bundle_id,
                    authority_model_definition_id=authority_id,
                    adapter_build_digest=_d("task29-adapter"),
                    contributor_snapshot_digest=_d("task29-contributors"),
                    idempotency_key=f"fs-{label}",
                    frozen_request_fingerprint=_d(f"task29-fingerprint-{label}"),
                    created_by=user_a,
                )
                await s.commit()
            artifact_id, _ = await _durable_incoming(
                label=label, target_room=main["room"],
                request_ref=accepted_one.request.id,
                operation_ref=accepted_one.operation.id,
            )
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                outcome = await repo.correlate_durable_incoming(
                    operation_id=accepted_one.operation.id,
                    incoming_artifact_id=artifact_id,
                    current_revision=1,
                    adapter_id="task29.adapter",
                )
                await s.commit()
            return accepted_one.operation.id, outcome.application.id

        async def _fresh_case(label: str, *, claim: bool) -> dict[str, Any]:
            case_incoming, _ = await _durable_incoming(
                label=f"case-{label}", target_room=main["room"], request_ref=None,
                operation_ref=None,
            )
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                fresh = await repo.create_recovery_case(
                    project_id=project, wp_id=wp, entry_id=ENTRY, room_id=main["room"],
                    generation=1,
                    source_delivery_key=_d(f"task29-delivery-case-{label}"),
                    incoming_artifact_id=case_incoming,
                    reason=RecoveryReason.crash_close,
                    candidate_confirmation_digest=_d("task29-candidate"),
                    candidate_contributor_digest=_d("task29-contributors"),
                )
                await s.commit()
            out: dict[str, Any] = {"case": fresh.id, "operation": None, "application": None}
            if claim:
                async with Session() as s:
                    repo = WorkpaperSyncRepository(s)
                    claim_outcome = await repo.claim_recovery_case(
                        case_id=fresh.id,
                        claiming_participant_id=main["participant"],
                        prior_confirmation_id=main["confirmation"],
                        idempotency_key=f"claim-{label}",
                        current_revision=1,
                        adapter_id="task29.adapter",
                        adapter_build_digest=_d("task29-adapter"),
                        contributor_snapshot_digest=_d("task29-contributors"),
                        actor_id=user_a,
                    )
                    await s.commit()
                out["operation"] = claim_outcome.operation.id
                out["application"] = claim_outcome.application.id
            return out

        entity_pool: dict[str, dict[str, Any]] = {}
        for scenario in required.scenarios:
            sid = scenario.scenario_id
            if scenario.kind is EV.ScenarioKind.recovery_claim:
                entity_pool[sid] = await _fresh_case(sid, claim=True)
            elif scenario.kind in (
                EV.ScenarioKind.download_only,
                EV.ScenarioKind.recovery_reject,
            ):
                entity_pool[sid] = await _fresh_case(sid, claim=False)
            elif scenario.expects_application:
                op_one, app_one = await _fresh_application(sid)
                entity_pool[sid] = {
                    "case": None, "operation": op_one, "application": app_one,
                }
            else:
                entity_pool[sid] = {"case": None, "operation": None, "application": None}

        evidence: dict[str, Any] = {}
        evidence["required_scenario_count"] = len(required.scenarios)
        evidence["capability"] = capability.value
        evidence["close_required"] = required.close_required
        evidence["distinct_applications"] = len(
            {
                str(item["application"])
                for item in entity_pool.values()
                if item["application"] is not None
            }
        )

        clean_run = await _write_run(entry_id=ENTRY, required_set=required)
        evidence["clean"] = await _verdict(clean_run)

        missing_run = await _write_run(
            entry_id=ENTRY, required_set=required, skip={"rollback"}
        )
        evidence["missing_scenario"] = await _verdict(missing_run)

        # download-only 出现三实体：**存储层**就拒（`ck_wpees_download_only_zero_entities`）。
        _, download_refusal = await _write_run_or_refusal(
            entry_id=ENTRY,
            required_set=required,
            scenario_overrides={
                "download_only_zero_three_entities": {
                    "operation_ids": [str(shell_id)],
                    "application_ids": [str(application_id)],
                }
            },
        )
        evidence["download_only_with_entities_refused_by_db"] = download_refusal

        dangling_run = await _write_run(
            entry_id=ENTRY,
            required_set=required,
            scenario_overrides={
                "html_to_oo": {
                    "operation_ids": [str(uuid.uuid4())],
                    "application_ids": [str(application_id)],
                }
            },
        )
        evidence["dangling_fk"] = await _verdict(dangling_run)

        cross_entry_run = await _write_run(
            entry_id=ENTRY,
            required_set=required,
            scenario_overrides={
                "oo_to_html": {
                    "operation_ids": [str(shell_id)],
                    "application_ids": [str(application_id)],
                    "representation_ids": [str(other["representation"])],
                }
            },
        )
        evidence["cross_entry_representation"] = await _verdict(cross_entry_run)

        stale_run = await _write_run(
            entry_id=ENTRY,
            required_set=required,
            overrides={"source_commit": "an-older-commit"},
        )
        evidence["stale_source_commit"] = await _verdict(stale_run)

        # 环境 digest 单独一条：它与 source_commit 是**两条独立**判据。
        # 只改 source_commit 时 run 里存着的 environment_digest 仍是当时算出来的那个，
        # 所以只有 `source_commit_changed` 会响；把两者合成一条断言会把「只响一条」
        # 误判成通过。
        stale_env_run = await _write_run(
            entry_id=ENTRY,
            required_set=required,
            overrides={"environment_digest": _d("a-different-environment")},
        )
        evidence["stale_environment_digest"] = await _verdict(stale_env_run)

        stale_build_run = await _write_run(
            entry_id=ENTRY,
            required_set=required,
            overrides={"onlyoffice_build": "9.3.0.1", "browser_build": "Chrome/1.0"},
        )
        evidence["stale_builds"] = await _verdict(stale_build_run)

        stale_profile_run = await _write_run(
            entry_id=ENTRY,
            required_set=required,
            overrides={"room_model": "exclusive", "editability": "readonly"},
        )
        evidence["stale_profile_downgrade"] = await _verdict(stale_profile_run)

        stale_digest_run = await _write_run(
            entry_id=ENTRY,
            required_set=required,
            overrides={"required_scenario_set_digest": _d("some-other-set")},
        )
        evidence["stale_required_set"] = await _verdict(stale_digest_run)

        # scenario 与所属 run 的 authority/bundle identity 必须一致 —— 同样是**库**先拒
        # （V151 触发器：「禁止跨 run 复制 evidence」）。
        _, bundle_refusal = await _write_run_or_refusal(
            entry_id=ENTRY,
            required_set=required,
            overrides={"definition_bundle_sha256": _d("another-bundle")},
        )
        evidence["bundle_mismatch_refused_by_db"] = bundle_refusal

        extra_run = await _write_run(
            entry_id=ENTRY,
            required_set=required,
            extra_rows=[{"scenario_id": "invented_scenario"}],
        )
        evidence["extra_scenario"] = await _verdict(extra_run)

        # 同一 operation/application 被两条互不等价的 scenario 引用（P70 同 run 内复用）。
        # 拿 `refresh_required_reopen` 自己的实体去顶掉 `rollback` 的那份。
        shared = entity_pool["refresh_required_reopen"]
        reuse_run = await _write_run(
            entry_id=ENTRY,
            required_set=required,
            scenario_overrides={
                "rollback": {
                    "operation_ids": [str(shared["operation"])],
                    "application_ids": [str(shared["application"])],
                },
            },
        )
        evidence["reuse_within_run"] = await _verdict(reuse_run)

        # 跨 entry 复用：另一个 entry 的 run 引用同一批实体（P70）
        other_required = EV.derive_for_manifest_entry(
            entries_by_id[OTHER_ENTRY], authority_model=AuthorityModel.projection_contract
        )
        other_run = await _write_run(entry_id=OTHER_ENTRY, required_set=other_required)
        evidence["cross_entry_reuse_other"] = await _verdict(
            other_run, entry_id=OTHER_ENTRY
        )
        evidence["cross_entry_reuse_main"] = await _verdict(clean_run)

        # 没有任何 run 的 entry
        async with Session() as s:
            recomputer = EV.EvidenceRecomputer(s)
            no_run = await recomputer.recompute(
                entry_id=ENTRY_WITHOUT_RUN,
                authority_model=AuthorityModel.projection_contract,
                environment=environment,
            )
        evidence["no_run"] = no_run.as_dict()

        # profile 交叉矛盾的 entry（Task 1/67 的欠账）必须报 drift 而不是崩
        async with Session() as s:
            recomputer = EV.EvidenceRecomputer(s)
            drifted = await recomputer.recompute(
                entry_id="docx/gt-a10-bundle",
                authority_model=AuthorityModel.opaque_single_onlyoffice,
                environment=environment,
            )
        evidence["profile_drift"] = drifted.as_dict()

        snap["scenarios"] = {"timeline": service_snapshots, "evidence": evidence}
        snap["world"] = {
            "shell_application_before": _opt(shell_application_before),
            "shell_id": str(shell_id),
            "application_id": str(application_id),
            "case_id": str(case_id),
        }
    except _HarnessError as exc:
        _phase_failed("bootstrap", exc)
    except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言为空
        _phase_failed("collect", exc)
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except Exception as exc:  # noqa: BLE001
            snap["harness_errors"]["teardown"] = _err(exc)
        await admin.dispose()
        shutil.rmtree(base_root, ignore_errors=True)
    return snap


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


class TestHarness:
    def test_a_real_postgres_backed_the_run(self, snap: dict[str, Any]) -> None:
        assert snap["apply_errors"] == [], snap["apply_errors"][:3]
        assert "PostgreSQL" in str(snap["server_version"])

    def test_no_phase_crashed_during_collection(self, snap: dict[str, Any]) -> None:
        """采集阶段零异常。

        这条是「异常记录不穿透」的另一半：不写它，采集失败就表现为「所有场景断言都
        因为 KeyError 而红」，看起来像一堆无关失败；写了它，失败位置一眼可见。
        """
        assert snap["harness_errors"] == {}, snap["harness_errors"]


class TestAppendOnlyProjection:
    """P68：current state 只是 append-only timeline 的投影。"""

    def test_a_healthy_operation_timeline_has_no_defect(self, snap: dict[str, Any]) -> None:
        healthy = snap["scenarios"]["timeline"]["healthy"]
        assert healthy["defects"] == [], healthy["defects"]
        assert healthy["events"] >= 5, healthy["events"]
        assert healthy["sequence_numbers"] == list(
            range(1, healthy["events"] + 1)
        ), healthy["sequence_numbers"]

    def test_the_shell_had_a_null_application_before_correlation(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 5.5：normal accepted shell 在 correlation 前 `application_id` 必须为 NULL。"""
        assert snap["world"]["shell_application_before"] is None

    def test_the_timeline_reports_the_bound_application_after_correlation(
        self, snap: dict[str, Any]
    ) -> None:
        healthy = snap["scenarios"]["timeline"]["healthy"]
        assert healthy["application_id"] == snap["world"]["application_id"]

    def test_editing_current_state_directly_is_caught(self, snap: dict[str, Any]) -> None:
        assert snap["scenarios"]["timeline"]["state_diverged"] == ["state_diverged"]

    @pytest.mark.parametrize(
        "kind", ["delete", "update", "duplicate_sequence"], ids=["delete", "update", "dup-seq"]
    )
    def test_the_storage_layer_refuses_every_tamper_form(
        self, snap: dict[str, Any], kind: str
    ) -> None:
        """AC 13.5：event 表在**存储层**就是 append-only。

        三种篡改各自参数化：删中间一条、改写既有一条、插一条重号伪造事件。共用一条
        断言时「三种里只挡住一种」照样绿。
        """
        refused = snap["scenarios"]["timeline"]["tamper"][kind]
        assert refused is not None, (
            f"{kind} 篡改**成功**了 —— append-only 只剩应用层约定"
        )
        assert refused.endswith("Error"), refused

    def test_the_timeline_survives_the_tamper_attempts_unchanged(
        self, snap: dict[str, Any]
    ) -> None:
        healthy = snap["scenarios"]["timeline"]["healthy"]
        after = snap["scenarios"]["timeline"]["after_tamper"]
        assert after["events"] == healthy["events"], (healthy["events"], after["events"])
        assert after["defects"] == [], after["defects"]

    def test_the_timeline_declares_the_server_clock_as_its_time_source(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 13.10：关键时间来自服务端；浏览器 trace 只能是客户端证据。"""
        assert snap["scenarios"]["timeline"]["healthy"]["server_clock_source"] == "database"

    def test_the_projected_event_carries_the_redaction_policy_version(
        self, snap: dict[str, Any]
    ) -> None:
        keys = snap["scenarios"]["timeline"]["healthy"]["payload_keys"]
        assert "redaction_policy_version" in keys, keys

    def test_the_projected_event_drops_the_surrogate_id(self, snap: dict[str, Any]) -> None:
        """`id` 是 bigint 代理键，不进投影（业务身份是 stream+parent+sequence_no）。"""
        keys = snap["scenarios"]["timeline"]["healthy"]["payload_keys"]
        assert "id" not in keys, keys

    def test_no_credential_or_business_value_appears_in_the_serialized_timeline(
        self, snap: dict[str, Any]
    ) -> None:
        """真库出来的 timeline JSON 里不得出现 token/URL query/业务值。"""
        blob = snap["scenarios"]["timeline"]["healthy"]["raw_json"]
        for forbidden in ("Bearer ", "eyJ", "?token=", "Authorization"):
            assert forbidden not in blob, f"timeline JSON 里出现 {forbidden!r}"

    def test_a_cross_scope_read_is_refused(self, snap: dict[str, Any]) -> None:
        refused = snap["scenarios"]["timeline"]["cross_scope_refused"]
        assert refused == "TimelineUsageError", refused


class TestTimelineLocators:
    """AC 13.6：按 wp/room/request/participant/operation/application/correlation 查询。"""

    def test_every_locator_returns_events(self, snap: dict[str, Any]) -> None:
        by_locator = snap["scenarios"]["timeline"]["by_locator"]
        empty = sorted(name for name, count in by_locator.items() if count == 0)
        assert not empty, f"这些定位维度查不到任何 event: {empty}"

    def test_the_room_query_spans_more_than_one_stream(self, snap: dict[str, Any]) -> None:
        """归并查询必须真的跨流，否则「四条流统一投影」是空话。"""
        streams = snap["scenarios"]["timeline"]["streams_seen"]
        assert len(streams) >= 2, streams
        assert "operation" in streams


class TestRecoveryCaseHasNoOperationBeforeClaim:
    """AC 5.8 / 13.5 / P68：claim 前三实体为 0，且不得借 operation timeline 伪造。"""

    def test_all_three_entities_are_absent_before_claim(self, snap: dict[str, Any]) -> None:
        counts = snap["scenarios"]["timeline"]["pre_claim_entities"]
        assert counts == {"request": 0, "application": 0, "operation": 0}, counts

    def test_the_pre_claim_timeline_says_so(self, snap: dict[str, Any]) -> None:
        pre = snap["scenarios"]["timeline"]["pre_claim_timeline"]
        assert pre["has_three_entities"] is False
        assert pre["claimed_operation_id"] is None
        assert pre["event_count"] >= 1, "recovery case 必须有自己的 append-only timeline"
        assert pre["defects"] == [], pre["defects"]

    def test_the_pre_claim_payload_has_no_operation_events_key(
        self, snap: dict[str, Any]
    ) -> None:
        keys = snap["scenarios"]["timeline"]["pre_claim_timeline"]["keys"]
        assert "operation_events" not in keys, keys
        assert "events" in keys and "claimed_operation_id" in keys

    def test_claiming_creates_all_three_entities_at_once(self, snap: dict[str, Any]) -> None:
        counts = snap["scenarios"]["timeline"]["post_claim_entities"]
        assert counts == {"request": 1, "application": 1, "operation": 1}, counts
        assert snap["scenarios"]["timeline"]["post_claim_timeline"]["has_three_entities"] is True

    def test_the_claim_shell_became_a_primary(self, snap: dict[str, Any]) -> None:
        assert snap["scenarios"]["timeline"]["post_claim_shape"] == "primary"

    def test_the_recovery_timeline_grows_append_only(self, snap: dict[str, Any]) -> None:
        before = snap["scenarios"]["timeline"]["pre_claim_timeline"]["event_count"]
        after = snap["scenarios"]["timeline"]["post_claim_timeline"]["event_count"]
        assert after > before, (before, after)


class TestEvidenceRecomputation:
    """P69：服务端从真实行重算 required set / 外键 / hash，不信写入的 aggregate result。"""

    def test_a_clean_run_has_exactly_one_known_and_attributed_defect(
        self, snap: dict[str, Any]
    ) -> None:
        """正面控制。

        🔴 断言的是**精确集合**而不是「非空」：一个逐场景造齐实体、环境完全对齐的 run
        只应剩下唯一一条**已登记且可归因**的缺陷 —— `scenario_kind_unrepresentable`
        （AC 5.6 的「quarantined 永不创建 application」与 V151 的
        `ck_wpees_standard_requires_entities` 当前不可同时满足，见
        `evidence.SCHEMA_UNREPRESENTABLE_SCENARIOS`）。

        这条**不是**放宽：entry 因此保持未验收。精确集合让任何其他检查误报（多一个码）
        或漏报（少这个码）都打红，正面控制的区分度反而比「== []」更高。
        """
        clean = snap["scenarios"]["evidence"]["clean"]
        assert clean["defects"] == ["scenario_kind_unrepresentable"], clean["defects"]
        assert clean["stale_reasons"] == [], clean["stale_reasons"]
        assert clean["result"] == "unverified", clean
        assert any("quarantined" in note for note in clean["notes"]), clean["notes"]

    def test_that_defect_is_the_declared_schema_gap_and_only_that(self) -> None:
        """反向锁死上一条：登记表恰有一条，且理由指名 V151 的约束。"""
        assert len(EV.SCHEMA_UNREPRESENTABLE_SCENARIOS) == 1, (
            f"schema 欠账登记表变成 {len(EV.SCHEMA_UNREPRESENTABLE_SCENARIOS)} 条 —— "
            "它是可归因的**单点**欠账，不是可以随手加项的豁免名单"
        )
        (sid, reason), = EV.SCHEMA_UNREPRESENTABLE_SCENARIOS.items()
        assert sid == "quarantined_rejects_application_and_engine"
        assert "ck_wpees_standard_requires_entities" in reason
        assert "owner" in reason
        # 该场景必须仍在 required set 里 —— 登记欠账不等于把它移出必需集合。
        assert sid in {s.scenario_id for s in EV.PROJECTION_BASE_SCENARIOS}

    def test_every_scenario_owns_its_own_application(self, snap: dict[str, Any]) -> None:
        """harness 自证：逐场景造实体，而不是共用一对（否则正面控制无意义）。"""
        evidence = snap["scenarios"]["evidence"]
        assert evidence["distinct_applications"] >= 20, evidence["distinct_applications"]

    def test_the_required_set_came_from_the_source_backed_profile(
        self, snap: dict[str, Any]
    ) -> None:
        evidence = snap["scenarios"]["evidence"]
        assert evidence["close_required"] is True, (
            f"{ENTRY} 的 room_model 是 shared 且 editable，必须要求 close 场景"
        )
        assert evidence["required_scenario_count"] >= 24, evidence
        assert len(evidence["clean"]["required_scenario_ids"]) == (
            evidence["required_scenario_count"]
        )

    def test_a_missing_scenario_is_unverified(self, snap: dict[str, Any]) -> None:
        verdict = snap["scenarios"]["evidence"]["missing_scenario"]
        assert "missing_scenario" in verdict["defects"], verdict
        assert verdict["result"] == "unverified"

    def test_download_only_with_entities_is_refused_by_the_storage_layer(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 12.11：download-only 的 operation/application 恒空 —— **库**先拒。

        实测 V151 的 `ck_wpees_download_only_zero_entities` 让这类脏行根本插不进去，
        所以判据落在「库拒绝了」而不是「recomputer 发现了」：后者在真实数据上不可达，
        对应的定向变异会永久 GREEN。recomputer 的同名检查是第二道防线，由
        `test_the_v151_constraint_that_enforces_it_still_exists` 与离线文件共同背书。
        """
        refusal = snap["scenarios"]["evidence"]["download_only_with_entities_refused_by_db"]
        assert refusal is not None, (
            "download-only 带三实体的脏行**插进去了** —— V151 的 CHECK 不在了"
        )
        assert refusal.endswith("Error"), refusal

    def test_the_v151_constraint_that_enforces_it_still_exists(self) -> None:
        """上一条的反向锁：约束名与语义都必须仍在迁移里。"""
        sql = _MIGRATION.read_text(encoding="utf-8")
        assert "ck_wpees_download_only_zero_entities" in sql
        assert "ck_wpees_standard_requires_entities" in sql
        assert "ck_wpees_recovery_claim_requires_case" in sql

    def test_a_dangling_operation_fk_is_unverified(self, snap: dict[str, Any]) -> None:
        verdict = snap["scenarios"]["evidence"]["dangling_fk"]
        assert "dangling_operation_fk" in verdict["defects"], verdict

    def test_an_entity_from_another_entry_is_unverified(self, snap: dict[str, Any]) -> None:
        verdict = snap["scenarios"]["evidence"]["cross_entry_representation"]
        assert "entity_scope_mismatch" in verdict["defects"], verdict

    def test_an_extra_unregistered_scenario_is_unverified(self, snap: dict[str, Any]) -> None:
        """required set 只能由推导产生，不接受追加自由项。"""
        verdict = snap["scenarios"]["evidence"]["extra_scenario"]
        assert "extra_scenario" in verdict["defects"], verdict

    def test_a_scenario_whose_bundle_differs_from_its_run_is_refused_by_the_db(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 12.10/12.11：scenario 的 bundle/authority identity 必须与所属 run 一致。

        与 download-only 同理：V151 的触发器（「禁止跨 run 复制 evidence」）在插入时就拒，
        所以判据落在库的拒绝上。recomputer 的 `bundle_digest_mismatch` 是第二道防线。
        """
        refusal = snap["scenarios"]["evidence"]["bundle_mismatch_refused_by_db"]
        assert refusal is not None, (
            "scenario 的 bundle digest 与 run 不一致的行**插进去了** —— 跨 run 复制 evidence "
            "的门不在了"
        )
        assert refusal.endswith("Error"), refusal

    def test_an_entry_without_any_run_is_unverified(self, snap: dict[str, Any]) -> None:
        verdict = snap["scenarios"]["evidence"]["no_run"]
        assert verdict["run_id"] is None
        assert verdict["result"] == "unverified"
        assert verdict["notes"], "没有 run 时必须说明原因"

    def test_a_contradictory_profile_reports_drift_instead_of_crashing(
        self, snap: dict[str, Any]
    ) -> None:
        """5 个 `single_html + exclusive` 的 docx entry 是 Task 1/67 的欠账。

        判据是「它被指名为 unverified」而**不是**「它被跳过」：跳过会让 AC 12.13 的
        五类计数把这些 entry 从分母里抹掉。
        """
        verdict = snap["scenarios"]["evidence"]["profile_drift"]
        assert verdict["defects"] == ["profile_cross_rule_drift"], verdict
        assert verdict["result"] == "unverified"
        assert verdict["required_scenario_ids"] == []


class TestEvidenceReuseIsRefused:
    """P70：同一实体不得跨 scenario / 跨 entry 复用。"""

    def test_reusing_one_operation_for_two_scenarios_is_refused(
        self, snap: dict[str, Any]
    ) -> None:
        verdict = snap["scenarios"]["evidence"]["reuse_within_run"]
        assert "reused_within_run" in verdict["defects"], verdict

    def test_the_same_entities_in_two_entries_runs_reddens_both(
        self, snap: dict[str, Any]
    ) -> None:
        """跨 entry 复用必须让**两侧**都不通过（只红一侧等于可以挑一个 entry 收口）。"""
        other = snap["scenarios"]["evidence"]["cross_entry_reuse_other"]
        main = snap["scenarios"]["evidence"]["cross_entry_reuse_main"]
        assert "reused_across_entry" in other["defects"], other
        assert "reused_across_entry" in main["defects"], main


class TestEvidenceStaleness:
    """P71：环境 / profile / required set / bundle 任一变化即 stale。"""

    def test_a_different_source_commit_makes_the_run_stale(
        self, snap: dict[str, Any]
    ) -> None:
        verdict = snap["scenarios"]["evidence"]["stale_source_commit"]
        assert verdict["stale_reasons"] == ["source_commit_changed"], verdict
        # `result` 是 `unverified`（不是 `stale`）：本 run 同时带着那条已登记的 schema
        # 欠账缺陷，而**缺陷优先于 stale** —— 一个既 stale 又有缺陷的 run 只报 stale 会
        # 让缺陷消失在「等环境刷新就好」里。stale 判据本体在 `stale_reasons` 上。
        assert verdict["result"] != "verified", verdict

    def test_the_environment_digest_is_its_own_independent_stale_reason(
        self, snap: dict[str, Any]
    ) -> None:
        """环境 digest 与 source commit 是两条独立判据，各自单独可响。"""
        verdict = snap["scenarios"]["evidence"]["stale_environment_digest"]
        assert verdict["stale_reasons"] == ["environment_digest_changed"], verdict

    def test_changing_the_oo_or_browser_build_makes_the_run_stale(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 14.16：OnlyOffice / 浏览器 build 变化即失效。"""
        verdict = snap["scenarios"]["evidence"]["stale_builds"]
        for reason in ("onlyoffice_build_changed", "browser_build_changed"):
            assert reason in verdict["stale_reasons"], verdict

    def test_downgrading_the_profile_cannot_keep_old_evidence_fresh(
        self, snap: dict[str, Any]
    ) -> None:
        """P71 点名的保鲜手法：把 profile 从 shared/editable 改成 exclusive/readonly。"""
        verdict = snap["scenarios"]["evidence"]["stale_profile_downgrade"]
        for reason in ("room_model_changed", "editability_changed"):
            assert reason in verdict["stale_reasons"], verdict
        assert verdict["result"] != "verified", verdict

    def test_a_different_required_set_digest_makes_the_run_stale(
        self, snap: dict[str, Any]
    ) -> None:
        verdict = snap["scenarios"]["evidence"]["stale_required_set"]
        assert "required_scenario_set_changed" in verdict["stale_reasons"], verdict

    def test_stale_alone_is_not_reported_as_verified(self, snap: dict[str, Any]) -> None:
        for key in (
            "stale_source_commit",
            "stale_profile_downgrade",
            "stale_required_set",
        ):
            verdict = snap["scenarios"]["evidence"][key]
            assert verdict["result"] != "verified", (key, verdict)
