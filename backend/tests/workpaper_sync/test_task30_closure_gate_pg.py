# -*- coding: utf-8 -*-
"""Task 30 关门判据（集成半）：durable protocol / application / close exactly-one / recovery。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 30
Requirements: 4.1, 4.3, 4.9, 4.10, 4.11, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9,
              5.10, 10.5, 10.11
Properties: **P16 / P17 / P18 / P19 / P43 / P44 / P62 / P63 / P64**

═══ 这是「独立门」，不是第 N 份 Task 2x 守卫 ═══

Task 21~29 各自证明「我这一层对」。关门要证的是**跨层组合**对，所以本文件：

* 在**一个** scratch schema 里、用**生产服务对象**把 room → request/shell →
  durable incoming → application → close → recovery 串起来真跑；
* 判据一律**回读数据库行**，不采信服务返回对象（返回对象是被测代码自己算的）；
* 对两处并发判据给**正向的「争用真的发生了」凭证** —— Task 30 正文明确写了
  「partial unique 只算 at-most-one 证据」，所以必须另证那个 "one" 真的产生了，
  以及仲裁/收敛路径真的被执行过（Task 23 首轮就出现过「场景全绿而 fold 路径一次没跑」）。

═══ 为什么必须真库 ═══

`application_key UNIQUE`、`uq_wpso_request`、close-capture 的 partial unique、
`trg_wpses_pointer`（entry pointer 只放行 published artifact）、
`wpsync_check_artifact_identity` —— 这些判据的执行者是 PostgreSQL。替身仓储复现不了。
`DATABASE_URL` 非 PostgreSQL 时**直接失败而不是 skip**（与 Task 10/21/22/23/24 同约定）。

═══ 隔离与采集 ═══

scratch schema `tmp_task30_gate_<hex>`，`search_path` 只含它，结束 `DROP SCHEMA CASCADE`。
全部场景由**一次 `asyncio.run`** 跑完落进快照（module fixture）—— 每个测试各自开 async
会污染共享连接池（Task 21~27 实测：第二个起 `NoneType has no attribute send`）。
采集阶段异常一律**记录不穿透**：穿透会把整个 module 变成 collection ERROR，而 `-rfE` 之外
的定向变异会看不到预期失败项 ⇒ 误判 GREEN。`test_no_phase_crashed_during_collection`
是这个决定的另一半。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import time
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

_SCHEMA_PREFIX = "tmp_task30_gate_"

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

#: 收敛判据的并发度。6 条独立连接足以同时覆盖「winner 建 application」「loser 等锁后命中」
#: 与「loser sequence 更低不 fold」三条分支。
RACE_N = 6


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _opt(value: object) -> str | None:
    """可空 UUID → `str | None`。`str(None) == "None"` 会把「没写上」判成「写上了」。"""
    return None if value is None else str(value)


def _err(exc: BaseException) -> str:
    import traceback

    frames = traceback.extract_tb(exc.__traceback__)[-5:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成「无数据」）。"""


_CONSTRAINT_IN_TEXT = re.compile(r'constraint "([a-z0-9_]+)"')
_CK_IN_TEXT = re.compile(r"\b((?:ck|uq|trg|idx)_[a-z0-9_]+)\b")
_TRIGGER_FN_IN_TEXT = re.compile(r"\b(wpsync_check_[a-z0-9_]+)\b")


def _blame(exc: BaseException) -> dict[str, Any]:
    """把一次 DB 拒绝归因到具体约束/trigger，并记下**全部**被提到的名字。

    只记一个名字时，一行同时撞两条约束会被静默归成其中一条 —— 于是下一个人据此以为
    自己声明的那条还活着。
    """
    orig: BaseException = exc
    seen: set[int] = set()
    while True:
        nxt = getattr(orig, "orig", None) or orig.__cause__
        if nxt is None or id(nxt) in seen:
            break
        seen.add(id(nxt))
        orig = nxt
    text = str(orig)
    named = getattr(orig, "constraint_name", None)
    if not named:
        m = _CONSTRAINT_IN_TEXT.search(text)
        named = m.group(1) if m else None
    mentions = sorted(set(_CK_IN_TEXT.findall(text)) | set(_TRIGGER_FN_IN_TEXT.findall(text)))
    if not named and mentions:
        named = mentions[0]
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return {
        "type": type(exc).__name__,
        "constraint": named,
        "mentions": mentions,
        "sqlstate": sqlstate,
        "text": text[:400],
    }


class _ProgrammableTransport:
    """Command Service 的可编程 stand-in（真实 OO 9.4 属 Task 44/70，本门不冒充）。

    `calls` 累积每次出站请求，使「哪一步真的发了命令」成为可断言事实 —— 只数 DB 行
    区分不出「建了 request 却没出站」。
    """

    def __init__(self) -> None:
        self.calls: list[Any] = []
        self.error_code = 0

    async def post(self, request: Any) -> Any:
        from app.services.workpaper_sync.command_service import CommandResponse

        self.calls.append(request)
        return CommandResponse(
            status_code=200, text=json.dumps({"error": int(self.error_code)})
        )


# ═══════════════════════════════════════════════════════════════════════════
# 采集
# ═══════════════════════════════════════════════════════════════════════════


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - 一次采集覆盖全部阶段
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.workpaper_sync_models import (
        WorkpaperCallbackRecoveryCase,
        WorkpaperContentApplication,
        WorkpaperOoCloseIntent,
        WorkpaperOoCloseIntentEvent,
        WorkpaperOoParticipant,
        WorkpaperOoRoom,
        WorkpaperSyncOperation,
        WorkpaperSyncScopeIndex,
    )
    from app.services.workpaper_sync.artifacts import QuarantinedIncomingError
    from app.services.workpaper_sync.callback_delivery import (
        QuarantineOperationForbiddenError,
    )
    from app.services.workpaper_sync.close_intent import (
        CLOSE_INTENT_LIVE_STATES,
        CloseIntentService,
        OPEN_CAPTURE_STATES,
        close_leader_sort_key,
    )
    from app.services.workpaper_sync.command_service import (
        CommandServiceClient,
        load_command_service_policy,
    )
    from app.services.workpaper_sync.models import (
        ActorType,
        ArtifactKind,
        ArtifactState,
        BundleSlot,
        BundleSlotSpec,
        CloseIntentState,
        ParticipantMode,
        ParticipantState,
        RecoveryReason,
        RequestKind,
        RequestState,
        ScopeResourceKind,
        compute_application_key,
    )
    from app.services.workpaper_sync.repository import (
        IdempotencyConflictError,
        WorkpaperSyncRepository,
    )
    from app.services.workpaper_sync.request_application import RequestApplicationService
    from app.services.workpaper_sync.rooms import (
        RoomScope,
        RoomService,
        derive_doc_key,
        mint_route_credential,
    )

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 30 的关门判据是 V151 约束 + room row lock + 真并发下的 application/"
            "close-capture 收敛，必须真实 PostgreSQL；当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip** —— skip 等于"
            "静默抹掉本门唯一判据。"
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
        "harness_errors": {},
        "shell": {},
        "race": {},
        "fold": {},
        "idempotency": {},
        "quarantine": {},
        "close": {},
        "recovery": {},
        "scope": {},
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
            except Exception as exc:  # noqa: BLE001 - 采集需原文入快照
                snap["apply_errors"].append({"index": idx, "error": _err(exc)})
                break
        if snap["apply_errors"]:
            raise _HarnessError(f"V151 应用失败: {snap['apply_errors']}")

        user_keys = ("user_a", "user_b", "user_c")
        ids: dict[str, uuid.UUID] = {"project": uuid.uuid4(), "wp": uuid.uuid4()}
        for u in user_keys:
            ids[u] = uuid.uuid4()
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                f"INSERT INTO projects (id) VALUES ('{ids['project']}')"
            )
            for u in user_keys:
                await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{ids[u]}')")
            await conn.exec_driver_sql(
                "INSERT INTO working_paper (id, project_id) VALUES "
                f"('{ids['wp']}', '{ids['project']}')"
            )

        project_id, wp_id = ids["project"], ids["wp"]
        scope = RoomScope(project_id=project_id, wp_id=wp_id, entry_id=ENTRY)
        base_path = f"storage/{project_id}/workpapers"
        adapter_id = "excel.d2.v1"
        adapter_digest = _d("adapter-build-t30")
        contrib_digest = _d("contrib-snapshot-t30")

        # ═══ 世界：definitions / approved bundle / published representation ═══
        async def _build_world(repo: WorkpaperSyncRepository) -> dict[str, Any]:
            blobs: dict[str, Any] = {}
            for name in ("tpl", "instr", "contract", "authority", "bundle_payload"):
                blobs[name] = await repo.register_artifact(
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=ArtifactKind.definition,
                    state=ArtifactState.published,
                    relative_path=(
                        f"{base_path}/.versions/{wp_id}/definitions/t30-{name}.json"
                    ),
                    sha256=_d(f"blob-t30-{name}"),
                    size_bytes=1024,
                    document_type="json",
                )
            tpl = await repo.create_definition_artifact(
                kind="template",
                logical_id="d2.template.t30",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["tpl"].id,
                sha256=_d("tpl-def-t30"),
                structure_hash=_d("tpl-structure-t30"),
                source_commit="task30",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation",
                logical_id="d2.instrumentation.t30",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["instr"].id,
                sha256=_d("instr-def-t30"),
                structure_hash=_d("instr-structure-t30"),
                source_commit="task30",
            )
            con = await repo.create_definition_artifact(
                kind="contract",
                logical_id="d2.contract.t30",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["contract"].id,
                sha256=_d("contract-def-t30"),
                source_commit="task30",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model",
                logical_id="authority.projection.t30",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["authority"].id,
                sha256=_d("authority-def-t30"),
                authority_model_type="projection_contract",
                source_commit="task30",
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
                        BundleSlot.contract, "definition", f"definition:{con.id}", con.sha256
                    ),
                },
                canonical_payload_artifact_id=blobs["bundle_payload"].id,
                canonical_payload_sha256=_d("bundle-canonical-t30"),
            )
            proj_art = await repo.register_artifact(
                project_id=project_id,
                wp_id=wp_id,
                kind=ArtifactKind.projection,
                state=ArtifactState.published,
                relative_path=f"{base_path}/.versions/{wp_id}/projections/t30.json.gz",
                sha256=_d("projection-t30"),
                size_bytes=2048,
                document_type="json.gz",
            )
            canon = await repo.register_artifact(
                project_id=project_id,
                wp_id=wp_id,
                kind=ArtifactKind.canonical,
                state=ArtifactState.published,
                relative_path=(
                    f"{base_path}/.versions/{wp_id}/representations/{ENTRY}/t30.xlsx"
                ),
                sha256=_d("canonical-t30"),
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
                adapter_id=adapter_id,
                adapter_build_digest=adapter_digest,
                structure_hash=_d("structure-t30"),
                identity_inventory_sha256=_d("identity-t30"),
                reason="content_commit",
            )
            await repo.set_entry_pointer(
                wp_id=wp_id, entry_id=ENTRY, representation_id=rep.id, generation=1
            )
            return {
                "bundle_id": bundle.id,
                "authority_sha256": _d("authority-def-t30"),
                "bundle_sha256": _d("bundle-canonical-t30"),
                "content_version_id": cv.id,
                "representation_id": rep.id,
                "projection_sha256": proj_art.sha256,
            }

        world: dict[str, Any] = {}
        async with Session() as s:
            world.update(await _build_world(WorkpaperSyncRepository(s)))
            await s.commit()
        rep_id = world["representation_id"]
        cv_id = world["content_version_id"]
        bundle_id = world["bundle_id"]
        projection_sha = world["projection_sha256"]

        transport = _ProgrammableTransport()
        policy = load_command_service_policy()

        def _client() -> CommandServiceClient:
            return CommandServiceClient(
                onlyoffice_url="http://oo.internal:8080",
                jwt_secret="task30-gate-secret",
                transport=transport,
                policy=policy,
            )

        def _wire(s: Any) -> tuple[Any, Any, RequestApplicationService, CloseIntentService]:
            repo = WorkpaperSyncRepository(s)
            rooms = RoomService(repo)
            ras = RequestApplicationService(repo, rooms)
            return (
                repo,
                rooms,
                ras,
                CloseIntentService(repo, _client(), rooms=rooms, requests=ras),
            )

        async def _make_room(*, generation: int, users: tuple[str, ...]) -> dict[str, Any]:
            """每个阶段一间新 generation 的 room，只返回**纯值**（ORM 对象跨 session 不安全）。"""
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                room = await repo.create_room(
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=ENTRY,
                    doc_key=derive_doc_key(
                        wp_id=wp_id, entry_id=ENTRY, generation=generation
                    ),
                    generation=generation,
                    opened_base_version_id=cv_id,
                )
                frozen = await svc.frozen_bundle_identity(bundle_id)
                parts: dict[str, uuid.UUID] = {}
                confs: dict[str, uuid.UUID] = {}
                for u in users:
                    part = await svc.join_participant(
                        scope,
                        room_id=room.id,
                        user_id=ids[u],
                        mode=ParticipantMode.edit,
                        permission_epoch=5,
                        lease_token=f"lease-{generation}-{u}",
                    )
                    parts[u] = part.id
                    conf, _after = await svc.confirm_descriptor(
                        scope,
                        room_id=room.id,
                        participant_id=part.id,
                        representation_id=rep_id,
                        content_version_id=cv_id,
                        projection_sha256=projection_sha,
                        idempotency_key=f"ready-{generation}-{u}",
                        expected_bundle=frozen,
                    )
                    confs[u] = conf.id
                out = {
                    "room_id": room.id,
                    "generation": generation,
                    "doc_key": room.doc_key,
                    "participants": parts,
                    "confirmations": confs,
                }
                await s.commit()
            return out

        async def _new_incoming(
            *,
            room_id: uuid.UUID,
            generation: int,
            doc_key: str,
            tag: str,
            sha: str,
            state: ArtifactState = ArtifactState.durable,
        ) -> dict[str, Any]:
            """建一条 delivery + 一个 incoming artifact（V151 要求 incoming 必绑 delivery）。"""
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                cred = mint_route_credential(
                    room_id=room_id, generation=generation, doc_key=doc_key
                )
                delivery = await repo.record_delivery(
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=ENTRY,
                    room_id=room_id,
                    generation=generation,
                    route_credential_id=cred.credential_id,
                    callback_status=6,
                    delivery_key=_d(f"delivery-{tag}"),
                    payload_sha256=_d(f"payload-{tag}"),
                )
                # 🔴 delivery 的合法状态边是 received → downloading → durable。
                #    直接从 received 交给 correlate 会被 FSM 拒（那是**约束在工作**），
                #    所以这里先走真实的 downloading 一步，而不是放宽 FSM。
                await repo.mark_delivery_downloading(delivery_id=delivery.id)
                art = await repo.register_artifact(
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=ArtifactKind.incoming,
                    state=state,
                    relative_path=(
                        f"{base_path}/.incoming/{wp_id}/{delivery.id}/{tag}.xlsx"
                    ),
                    sha256=sha,
                    size_bytes=51200,
                    document_type="xlsx",
                    source_delivery_id=delivery.id,
                )
                out = {"delivery_id": delivery.id, "artifact_id": art.id, "sha256": sha}
                await s.commit()
            return out

        # ═══════════════════════════════════════════════════════════════════
        # 阶段 1：normal pre-correlation shell → durable application correlation
        # ═══════════════════════════════════════════════════════════════════
        try:
            ctx = await _make_room(generation=1, users=("user_a", "user_b"))
            inc = await _new_incoming(
                room_id=ctx["room_id"],
                generation=1,
                doc_key=ctx["doc_key"],
                tag="t30-shell",
                sha=_d("incoming-shell"),
            )
            async with Session() as s:
                _repo, _rooms, ras, _close = _wire(s)
                accepted = await ras.freeze_and_persist_request(
                    scope,
                    room_id=ctx["room_id"],
                    participant_id=ctx["participants"]["user_a"],
                    idempotency_key="t30-shell-1",
                    client_edit_epoch=3,
                    contributor_user_ids=[ids["user_a"]],
                    created_by=ids["user_a"],
                )
                # 🔴 回读库行，不采信返回对象：shell 的两个 link 必须都是 NULL。
                row = (
                    await s.execute(
                        sa.select(
                            WorkpaperSyncOperation.application_id,
                            WorkpaperSyncOperation.duplicate_of_operation_id,
                            WorkpaperSyncOperation.state,
                            WorkpaperSyncOperation.forcesave_request_id,
                        ).where(WorkpaperSyncOperation.id == accepted.operation.id)
                    )
                ).one()
                app_rows = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count()).select_from(
                                WorkpaperContentApplication
                            )
                        )
                    ).scalar_one()
                )
                snap["shell"]["accepted"] = {
                    "operation_id": str(accepted.operation.id),
                    "request_id": str(accepted.request.id),
                    "shape": accepted.operation_shape.value,
                    "db_application_id": _opt(row[0]),
                    "db_duplicate_of": _opt(row[1]),
                    "db_request_link": _opt(row[3]),
                    "application_rows": app_rows,
                    "fingerprint_is_digest": bool(
                        re.fullmatch(r"[0-9a-f]{64}", accepted.frozen_request_fingerprint)
                    ),
                }
                await s.commit()
                shell_op_id = accepted.operation.id

            async with Session() as s:
                _repo, _rooms, ras, _close = _wire(s)
                out = await ras.correlate(
                    operation_id=shell_op_id,
                    incoming_artifact_id=inc["artifact_id"],
                    current_revision=1,
                    adapter_id=adapter_id,
                    delivery_id=inc["delivery_id"],
                    actor_type=ActorType.callback,
                )
                row = (
                    await s.execute(
                        sa.select(
                            WorkpaperSyncOperation.application_id,
                            WorkpaperSyncOperation.duplicate_of_operation_id,
                            WorkpaperSyncOperation.state,
                        ).where(WorkpaperSyncOperation.id == shell_op_id)
                    )
                ).one()
                app = (
                    await s.execute(
                        sa.select(
                            WorkpaperContentApplication.id,
                            WorkpaperContentApplication.origin_request_sequence,
                            WorkpaperContentApplication.effective_request_sequence,
                            WorkpaperContentApplication.superseded_by_application_id,
                            WorkpaperContentApplication.application_key,
                        ).where(WorkpaperContentApplication.id == out.application.id)
                    )
                ).one()
                snap["shell"]["correlated"] = {
                    "shape": out.shape.value,
                    "created_application": out.created_application,
                    "db_application_id": _opt(row[0]),
                    "db_duplicate_of": _opt(row[1]),
                    "db_state": str(row[2]),
                    # 🔴 「是不是 primary」由**结构**判定（绑了 application 且不指向别人），
                    #    不由 state 字面量判定：state 是 `application_bound` 这类生命周期值，
                    #    拿它当形态判据会把「形态」与「进行到哪一步」混成一件事。
                    "db_is_primary": row[0] is not None and row[1] is None,
                    "origin_sequence": int(app[1]),
                    "effective_sequence": int(app[2]),
                    "self_superseded": app[3] is not None,
                    "key_is_digest": bool(re.fullmatch(r"[0-9a-f]{64}", str(app[4]))),
                    # 🔴 期望值由本文件**独立**重算（`sha256("|".join(...))`），**不**调
                    #    `compute_application_key`：调生产函数会让「从 key 里删掉一个分量」
                    #    这类变异同时改动两侧，等式恒成立 ⇒ 判据自证（本 spec 点名的
                    #    self-certifying tautology 形态）。
                    "expected_key": hashlib.sha256(
                        "|".join(
                            [
                                str(wp_id),
                                str(ctx["room_id"]),
                                "1",
                                str(cv_id),
                                str(rep_id),
                                inc["sha256"],
                                world["bundle_sha256"],
                                world["authority_sha256"],
                                adapter_digest,
                            ]
                        ).encode("utf-8")
                    ).hexdigest(),
                    "actual_key": str(app[4]),
                }
                await s.commit()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("shell", exc)

        # ═══════════════════════════════════════════════════════════════════
        # 阶段 2：N 个 different-request 同 key → 1 primary + N-1 direct duplicates
        # ═══════════════════════════════════════════════════════════════════
        try:
            ctx2 = await _make_room(generation=2, users=("user_a",))
            inc2 = await _new_incoming(
                room_id=ctx2["room_id"],
                generation=2,
                doc_key=ctx2["doc_key"],
                tag="t30-race",
                sha=_d("incoming-race"),
            )
            race_ops: list[uuid.UUID] = []
            async with Session() as s:
                _repo, _rooms, ras, _close = _wire(s)
                for i in range(RACE_N):
                    acc = await ras.freeze_and_persist_request(
                        scope,
                        room_id=ctx2["room_id"],
                        participant_id=ctx2["participants"]["user_a"],
                        idempotency_key=f"t30-race-{i}",
                        client_edit_epoch=3,
                        contributor_user_ids=[ids["user_a"]],
                        created_by=ids["user_a"],
                    )
                    race_ops.append(acc.operation.id)
                await s.commit()

            barrier = asyncio.Barrier(RACE_N)
            results: list[dict[str, Any]] = []

            async def _racer(idx: int, op_id: uuid.UUID) -> None:
                rec: dict[str, Any] = {"idx": idx, "operation_id": str(op_id)}
                async with Session() as rs:
                    try:
                        rec["backend_pid"] = int(
                            (await rs.execute(sa.text("SELECT pg_backend_pid()"))).scalar_one()
                        )
                        # `t_ready` 记在 `wait()` **之前**：barrier 语义保证任何 `wait()`
                        # 返回都晚于最后一个参与者进入等待，故 max(t_ready) <= min(t_call)
                        # 必成立。用 `t_barrier` 版本会偶发假红（释放后恢复顺序任意）。
                        rec["t_ready"] = time.monotonic()
                        await barrier.wait()
                        rec["t_call"] = time.monotonic()
                        _r, _rm, rras, _c = _wire(rs)
                        out = await rras.correlate(
                            operation_id=op_id,
                            incoming_artifact_id=inc2["artifact_id"],
                            current_revision=1,
                            adapter_id=adapter_id,
                            actor_type=ActorType.callback,
                        )
                        rec["shape"] = out.shape.value
                        rec["created_application"] = out.created_application
                        rec["application_id"] = str(out.application.id)
                        await rs.commit()
                        rec["committed"] = True
                    except Exception as exc:  # noqa: BLE001 - 每条 racer 独立记录
                        await rs.rollback()
                        rec["committed"] = False
                        rec["error"] = _err(exc)
                        rec["blame"] = _blame(exc)
                results.append(rec)

            await asyncio.gather(*(_racer(i, race_ops[i]) for i in range(RACE_N)))

            async with Session() as s:
                ops = list(
                    (
                        await s.execute(
                            sa.select(
                                WorkpaperSyncOperation.id,
                                WorkpaperSyncOperation.application_id,
                                WorkpaperSyncOperation.duplicate_of_operation_id,
                                WorkpaperSyncOperation.state,
                            ).where(WorkpaperSyncOperation.id.in_(race_ops))
                        )
                    ).all()
                )
                apps = list(
                    (
                        await s.execute(
                            sa.select(
                                WorkpaperContentApplication.id,
                                WorkpaperContentApplication.application_key,
                            ).where(
                                WorkpaperContentApplication.incoming_sha256
                                == inc2["sha256"]
                            )
                        )
                    ).all()
                )
                chained = int(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT count(*) FROM working_paper_sync_operation o "
                                "JOIN working_paper_sync_operation t "
                                "  ON t.id = o.duplicate_of_operation_id "
                                "WHERE t.duplicate_of_operation_id IS NOT NULL "
                                "   OR t.state = 'duplicate'"
                            )
                        )
                    ).scalar_one()
                )
                cyclic = int(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT count(*) FROM working_paper_sync_operation "
                                "WHERE duplicate_of_operation_id = id"
                            )
                        )
                    ).scalar_one()
                )
            # 形态按**结构**分类（绑了 application 且不指向别人 = primary；指向别人 =
            # duplicate；两者皆空 = stranded shell）。用 state 字面量分类会把生命周期值
            # （`application_bound` / `duplicate`）与形态混成一件事。
            primaries = [o for o in ops if o[1] is not None and o[2] is None]
            duplicates = [o for o in ops if o[2] is not None]
            stranded = [o for o in ops if o[1] is None and o[2] is None]
            snap["race"] = {
                "n": RACE_N,
                "results": results,
                "committed": sum(1 for r in results if r.get("committed")),
                "distinct_backend_pids": len({r.get("backend_pid") for r in results}),
                "max_t_ready": max((r["t_ready"] for r in results if "t_ready" in r), default=0),
                "min_t_call": min((r["t_call"] for r in results if "t_call" in r), default=0),
                "created_application_count": sum(
                    1 for r in results if r.get("created_application")
                ),
                "application_rows": len(apps),
                "distinct_application_keys": len({str(a[1]) for a in apps}),
                "primary_count": len(primaries),
                "duplicate_count": len(duplicates),
                "stranded_count": len(stranded),
                "chained_count": chained,
                "cyclic_count": cyclic,
                "duplicate_targets_are_the_primary": (
                    sorted({str(o[2]) for o in duplicates})
                    == sorted({str(o[0]) for o in primaries})
                    if primaries and duplicates
                    else None
                ),
                "duplicate_states": sorted({str(o[3]) for o in duplicates}),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("race", exc)

        # ═══════════════════════════════════════════════════════════════════
        # 阶段 3：same-application higher sequence → 原子 fold，不 self-supersede
        # ═══════════════════════════════════════════════════════════════════
        try:
            ctx3 = await _make_room(generation=3, users=("user_a",))
            inc3 = await _new_incoming(
                room_id=ctx3["room_id"],
                generation=3,
                doc_key=ctx3["doc_key"],
                tag="t30-fold",
                sha=_d("incoming-fold"),
            )
            fold_ops: list[tuple[uuid.UUID, int]] = []
            async with Session() as s:
                _repo, _rooms, ras, _close = _wire(s)
                for i in range(3):
                    acc = await ras.freeze_and_persist_request(
                        scope,
                        room_id=ctx3["room_id"],
                        participant_id=ctx3["participants"]["user_a"],
                        idempotency_key=f"t30-fold-{i}",
                        client_edit_epoch=3,
                        contributor_user_ids=[ids["user_a"]],
                        created_by=ids["user_a"],
                    )
                    fold_ops.append((acc.operation.id, int(acc.request_sequence)))
                await s.commit()
            fold_ops.sort(key=lambda pair: pair[1])

            observed: list[dict[str, Any]] = []
            for op_id, seq in fold_ops:
                async with Session() as s:
                    _r, _rm, ras, _c = _wire(s)
                    out = await ras.correlate(
                        operation_id=op_id,
                        incoming_artifact_id=inc3["artifact_id"],
                        current_revision=1,
                        adapter_id=adapter_id,
                        actor_type=ActorType.callback,
                    )
                    observed.append(
                        {
                            "request_sequence": seq,
                            "shape": out.shape.value,
                            "created_application": out.created_application,
                            "effective": int(out.effective_request_sequence),
                            "folded_from": (
                                int(out.folded_from_sequence)
                                if out.folded_from_sequence is not None
                                else None
                            ),
                        }
                    )
                    await s.commit()
            async with Session() as s:
                app = (
                    await s.execute(
                        sa.select(
                            WorkpaperContentApplication.origin_request_sequence,
                            WorkpaperContentApplication.effective_request_sequence,
                            WorkpaperContentApplication.superseded_by_application_id,
                        ).where(
                            WorkpaperContentApplication.incoming_sha256 == inc3["sha256"]
                        )
                    )
                ).all()
            snap["fold"] = {
                "seeded_sequences": [seq for _op, seq in fold_ops],
                "observed": observed,
                "application_rows": len(app),
                "origin_sequence": int(app[0][0]) if app else None,
                "effective_sequence": int(app[0][1]) if app else None,
                "self_superseded": (app[0][2] is not None) if app else None,
                # 「fold 路径真的跑过」的凭证：至少一次 correlate 报出 folded_from
                # （只断言最终 effective == max 时，「压根没 fold、就是第一次写进去的」
                # 也会满足，那正是 Task 23 首轮的假绿形态）。
                "fold_events": sum(1 for o in observed if o["folded_from"] is not None),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("fold", exc)

        # ═══════════════════════════════════════════════════════════════════
        # 阶段 4：复合幂等键 + fingerprint —— 跨 participant/payload/contributor 409
        # ═══════════════════════════════════════════════════════════════════
        try:
            ctx4 = await _make_room(generation=4, users=("user_a", "user_b"))
            base_kwargs: dict[str, Any] = {
                "room_id": ctx4["room_id"],
                "participant_id": ctx4["participants"]["user_a"],
                "idempotency_key": "t30-idem",
                "client_edit_epoch": 3,
                "contributor_user_ids": [ids["user_a"]],
                "created_by": ids["user_a"],
            }
            async with Session() as s:
                _r, _rm, ras, _c = _wire(s)
                first = await ras.freeze_and_persist_request(scope, **base_kwargs)
                prior_request_id = str(first.request.id)
                prior_operation_id = str(first.operation.id)
                await s.commit()

            async def _conflict(name: str, **over: Any) -> None:
                kwargs = dict(base_kwargs)
                kwargs.update(over)
                async with Session() as s:
                    _r, _rm, ras, _c = _wire(s)
                    before = int(
                        (
                            await s.execute(
                                sa.select(sa.func.count()).select_from(
                                    WorkpaperSyncOperation
                                )
                            )
                        ).scalar_one()
                    )
                    entry: dict[str, Any] = {}
                    try:
                        out = await ras.freeze_and_persist_request(scope, **kwargs)
                        entry["accepted"] = True
                        entry["cache_hit"] = out.cache_hit
                        entry["returned_request"] = str(out.request.id)
                    except IdempotencyConflictError as exc:
                        entry["accepted"] = False
                        entry["error_type"] = type(exc).__name__
                        entry["leaks_prior_request"] = prior_request_id in str(exc)
                        entry["leaks_prior_operation"] = prior_operation_id in str(exc)
                    except Exception as exc:  # noqa: BLE001
                        entry["accepted"] = False
                        entry["error_type"] = type(exc).__name__
                        entry["unexpected"] = True
                        entry["text"] = str(exc)[:300]
                    after = int(
                        (
                            await s.execute(
                                sa.select(sa.func.count()).select_from(
                                    WorkpaperSyncOperation
                                )
                            )
                        ).scalar_one()
                    )
                    entry["operation_rows_delta"] = after - before
                    snap["idempotency"][name] = entry
                    await s.rollback()

            await _conflict("cross_participant", participant_id=ctx4["participants"]["user_b"])
            await _conflict("payload_differs", client_edit_epoch=4)
            await _conflict(
                "contributors_differ",
                contributor_user_ids=[ids["user_a"], ids["user_b"]],
            )
            # 逐字等值重放 ⇒ 必须命中缓存、返回同一 id（反向自检：409 不是恒真）
            await _conflict("identical_replay")
        except Exception as exc:  # noqa: BLE001
            _phase_failed("idempotency", exc)

        # ═══════════════════════════════════════════════════════════════════
        # 阶段 5：quarantined incoming —— application / engine / pointer 三处均拒
        # ═══════════════════════════════════════════════════════════════════
        try:
            ctx5 = await _make_room(generation=5, users=("user_a",))
            qinc = await _new_incoming(
                room_id=ctx5["room_id"],
                generation=5,
                doc_key=ctx5["doc_key"],
                tag="t30-quarantine",
                sha=_d("incoming-quarantined"),
                state=ArtifactState.quarantined,
            )
            async with Session() as s:
                art_row = (
                    await s.execute(
                        sa.text(
                            "SELECT state, durable_at IS NULL AS no_durable_at "
                            "FROM working_paper_artifact WHERE id = :aid"
                        ),
                        {"aid": str(qinc["artifact_id"])},
                    )
                ).one()
            snap["quarantine"]["artifact"] = {
                "state": str(art_row[0]),
                "durable_at_is_null": bool(art_row[1]),
            }

            async with Session() as s:
                _r, _rm, ras, _c = _wire(s)
                acc = await ras.freeze_and_persist_request(
                    scope,
                    room_id=ctx5["room_id"],
                    participant_id=ctx5["participants"]["user_a"],
                    idempotency_key="t30-quarantine-1",
                    client_edit_epoch=3,
                    contributor_user_ids=[ids["user_a"]],
                    created_by=ids["user_a"],
                )
                q_op_id = acc.operation.id
                await s.commit()

            async with Session() as s:
                _r, _rm, ras, _c = _wire(s)
                before = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count()).select_from(
                                WorkpaperContentApplication
                            )
                        )
                    ).scalar_one()
                )
                entry: dict[str, Any] = {}
                try:
                    await ras.correlate(
                        operation_id=q_op_id,
                        incoming_artifact_id=qinc["artifact_id"],
                        current_revision=1,
                        adapter_id=adapter_id,
                        actor_type=ActorType.callback,
                    )
                    entry["accepted"] = True
                except Exception as exc:  # noqa: BLE001 - 归因入快照
                    entry["accepted"] = False
                    entry["error_type"] = type(exc).__name__
                    # 拒绝必须来自**隔离**这条判据，不是「反正不是 durable」那条兜底。
                    entry["is_quarantine_error"] = isinstance(
                        exc, (QuarantinedIncomingError, QuarantineOperationForbiddenError)
                    )
                    entry["blame"] = _blame(exc)
                await s.rollback()
                async with Session() as s2:
                    after = int(
                        (
                            await s2.execute(
                                sa.select(sa.func.count()).select_from(
                                    WorkpaperContentApplication
                                )
                            )
                        ).scalar_one()
                    )
                entry["application_rows_delta"] = after - before
                snap["quarantine"]["application"] = entry

            # DB 层第三道门：representation 只能由 published canonical/result artifact 背书。
            # 🔴 判据取「新建一个指向 quarantined incoming 的 representation」而不是
            #    「改现有 representation 的 artifact_id」：后者会先撞 immutability trigger，
            #    于是拒绝理由漂成「不可变」，而本条要验的是「artifact 形态不合格」。
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                entry = {}
                try:
                    await repo.create_representation(
                        project_id=project_id,
                        wp_id=wp_id,
                        entry_id=ENTRY,
                        content_version_id=cv_id,
                        generation=99,
                        document_type="xlsx",
                        artifact_id=qinc["artifact_id"],
                        artifact_sha256=qinc["sha256"],
                        definition_bundle_id=bundle_id,
                        authority_model_definition_id=(
                            await repo.assert_bundle_usable(bundle_id)
                        ).authority_model_definition_id,
                        adapter_id=adapter_id,
                        adapter_build_digest=adapter_digest,
                        structure_hash=_d("structure-t30"),
                        identity_inventory_sha256=_d("identity-t30"),
                        reason="content_commit",
                    )
                    await s.commit()
                    entry["accepted"] = True
                except Exception as exc:  # noqa: BLE001
                    await s.rollback()
                    entry["accepted"] = False
                    entry["error_type"] = type(exc).__name__
                    entry["blame"] = _blame(exc)
                snap["quarantine"]["representation_artifact"] = entry
        except Exception as exc:  # noqa: BLE001
            _phase_failed("quarantine", exc)

        # ═══════════════════════════════════════════════════════════════════
        # 阶段 6：close exactly-one（single / A-B / B-A / reconciler 重入）
        # ═══════════════════════════════════════════════════════════════════
        async def _close(ctx: dict[str, Any], user: str, *, tag: str) -> dict[str, Any]:
            async with Session() as s:
                _r, _rm, _ras, svc = _wire(s)
                opened = await svc.open_close_intent(
                    scope,
                    room_id=ctx["room_id"],
                    participant_id=ctx["participants"][user],
                    idempotency_key=f"close-{tag}-{user}",
                    client_edit_epoch=3,
                    adapter_build_digest=adapter_digest,
                    contributor_snapshot_digest=contrib_digest,
                    contributor_user_ids=[ids[user]],
                    created_by=ids[user],
                    actor_id=ids[user],
                )
                out = {
                    "intent_id": str(opened.intent_id),
                    "intent_sequence": int(opened.intent_sequence),
                    "remaining_active": int(opened.remaining_active_editors),
                    "has_predecessor": bool(opened.has_predecessor),
                    "capture_created": bool(opened.reconcile.capture_created),
                    "leader_intent_id": _opt(opened.reconcile.leader_intent_id),
                    "eligible_count": len(opened.reconcile.prediction.eligible_intent_ids),
                    "promoted_short_circuit": bool(
                        opened.reconcile.prediction.promoted_short_circuit
                    ),
                }
                await s.commit()
                return out

        async def _reconcile(ctx: dict[str, Any]) -> dict[str, Any]:
            async with Session() as s:
                _r, _rm, _ras, svc = _wire(s)
                out = await svc.reconcile(
                    scope,
                    room_id=ctx["room_id"],
                    adapter_build_digest=adapter_digest,
                    contributor_snapshot_digest=contrib_digest,
                )
                rec = {
                    "leader_intent_id": _opt(out.leader_intent_id),
                    "capture_created": bool(out.capture_created),
                    "no_successor": bool(out.no_successor),
                    "live_intents": int(out.live_intent_count),
                    "open_captures": int(out.open_capture_count),
                    "stale_reported": [
                        str(x) for x in out.repository.authorization_stale_intent_ids
                    ],
                    "eligibility_epoch": int(out.repository.eligibility_epoch),
                    "eligibility_digest": out.repository.eligibility_digest,
                    # 「仲裁真的跑过」的三项凭证（不是装饰）：eligible ≥2 且未短路时，
                    # comparator 才可能选错 —— 只断言 leader 相等在只剩一条候选或
                    # promoted 幂等短路时会**恒真**地通过。
                    "eligible_count": len(out.prediction.eligible_intent_ids),
                    "promoted_short_circuit": bool(out.prediction.promoted_short_circuit),
                }
                await s.commit()
                return rec

        async def _terminate_open_requests(ctx: dict[str, Any]) -> int:
            """把该 generation 的普通 forcesave predecessor 全部落 terminal。

            直接 UPDATE 而非重跑 callback 链：本阶段的判据是 close barrier 语义，
            callback → durable → correlation 是阶段 1/2 的判据，混在一起会让失败原因不可归因。
            """
            from app.models.workpaper_sync_models import WorkpaperForcesaveRequest

            async with Session() as s:
                result = await s.execute(
                    sa.update(WorkpaperForcesaveRequest)
                    .where(
                        WorkpaperForcesaveRequest.room_id == ctx["room_id"],
                        WorkpaperForcesaveRequest.generation == ctx["generation"],
                        WorkpaperForcesaveRequest.kind == RequestKind.forcesave.value,
                        WorkpaperForcesaveRequest.state.in_(
                            sorted(x.value for x in OPEN_CAPTURE_STATES)
                        ),
                    )
                    .values(state=RequestState.terminal.value)
                )
                await s.commit()
                return int(result.rowcount or 0)

        async def _close_facts(ctx: dict[str, Any]) -> dict[str, Any]:
            from app.models.workpaper_sync_models import WorkpaperForcesaveRequest

            async with Session() as s:
                intents = list(
                    (
                        await s.execute(
                            sa.select(
                                WorkpaperOoCloseIntent.id,
                                WorkpaperOoCloseIntent.intent_sequence,
                                WorkpaperOoCloseIntent.state,
                                WorkpaperOoCloseIntent.promoted_request_id,
                            ).where(
                                WorkpaperOoCloseIntent.room_id == ctx["room_id"],
                                WorkpaperOoCloseIntent.generation == ctx["generation"],
                            )
                        )
                    ).all()
                )
                captures = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperForcesaveRequest)
                            .where(
                                WorkpaperForcesaveRequest.room_id == ctx["room_id"],
                                WorkpaperForcesaveRequest.generation == ctx["generation"],
                                WorkpaperForcesaveRequest.kind
                                == RequestKind.close_capture.value,
                            )
                        )
                    ).scalar_one()
                )
                stale_events = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperOoCloseIntentEvent)
                            .where(
                                WorkpaperOoCloseIntentEvent.intent_id.in_(
                                    [i[0] for i in intents] or [uuid.uuid4()]
                                ),
                                WorkpaperOoCloseIntentEvent.to_state
                                == CloseIntentState.authorization_stale.value,
                            )
                        )
                    ).scalar_one()
                )
                room = (
                    await s.execute(
                        sa.select(WorkpaperOoRoom.state).where(
                            WorkpaperOoRoom.id == ctx["room_id"]
                        )
                    )
                ).scalar_one()
            live = [i for i in intents if str(i[2]) in {x.value for x in CLOSE_INTENT_LIVE_STATES}]
            return {
                "all_captures": captures,
                "intent_states": sorted({str(i[2]) for i in intents}),
                "live_intents": len(live),
                "promoted_intents": [str(i[0]) for i in intents if i[3] is not None],
                "authorization_stale_events": stale_events,
                "room_state": str(room),
                "max_sequence_intent": (
                    str(max(intents, key=lambda i: (int(i[1]), str(i[0])))[0])
                    if intents
                    else None
                ),
            }

        # 🔴 `single` 的 room 只能有**一个** participant：房里还有活跃编辑者时，
        #    「关闭者排除自己后仍有 active」本就不该 capture（这是正确行为）。
        #    首轮把 single 也建成两人房 ⇒ 恒 0 capture，看起来像 close 坏了。
        for name, generation, members, order in (
            ("single", 6, ("user_a",), ("user_a",)),
            ("order_ab", 7, ("user_a", "user_b"), ("user_a", "user_b")),
            ("order_ba", 8, ("user_a", "user_b"), ("user_b", "user_a")),
        ):
            try:
                ctx = await _make_room(generation=generation, users=members)
                rec: dict[str, Any] = {"closes": []}
                for user in order:
                    rec["closes"].append(await _close(ctx, user, tag=name))
                # barrier 语义：**有 predecessor 时**（关闭者自己刚被提交一条普通 forcesave）
                # 在它 terminal 之前不得有 capture。没有 predecessor 时 barrier 本就是空的，
                # capture 立即产生 —— 那不是违规，所以判据必须按 `has_predecessor` 分支。
                rec["captures_before_terminal"] = (await _close_facts(ctx))["all_captures"]
                rec["any_predecessor"] = any(c["has_predecessor"] for c in rec["closes"])
                rec["terminated"] = await _terminate_open_requests(ctx)
                rec["reconcile_1"] = await _reconcile(ctx)
                # 重入：同一 eligibility snapshot 再跑一次，不得再建 capture、不得换 leader
                rec["reconcile_2"] = await _reconcile(ctx)
                rec.update(await _close_facts(ctx))
                snap["close"][name] = rec
            except Exception as exc:  # noqa: BLE001
                _phase_failed(f"close_{name}", exc)

        # ═══ 阶段 7：leader **promotion 之前**失权 → authorization_stale → 合法 successor ═══
        #
        # 🔴 时序是判据本身。首轮先 reconcile 再撤权 ⇒ leader 早已 promoted，撤权只是
        #    「事后」，服务正确地什么都不做（0 条 stale 事件），看起来像判据坏了。
        #    正确形态：barrier 尚未清除（predecessor 未 terminal）时就撤权，
        #    于是 reconcile 第一次评估 eligibility 时那个候选已不合格。
        try:
            ctx = await _make_room(generation=9, users=("user_a", "user_b", "user_c"))
            rec = {"closes": []}
            for user in ("user_a", "user_b", "user_c"):
                rec["closes"].append(await _close(ctx, user, tag="stale"))
            # 预测 leader：最高 `(intent_sequence, id)`。**自己算**而不是问服务 ——
            # 问服务等于用被测代码给自己出题。
            async with Session() as s:
                intents = list(
                    (
                        await s.execute(
                            sa.select(
                                WorkpaperOoCloseIntent.id,
                                WorkpaperOoCloseIntent.intent_sequence,
                                WorkpaperOoCloseIntent.participant_id,
                            ).where(
                                WorkpaperOoCloseIntent.room_id == ctx["room_id"],
                                WorkpaperOoCloseIntent.generation == ctx["generation"],
                            )
                        )
                    ).all()
                )
            assert len(intents) == 3, intents
            predicted = max(intents, key=lambda r: (int(r[1]), str(r[0])))
            rec["predicted_leader_intent_id"] = str(predicted[0])
            rec["predicted_by"] = "max(intent_sequence, id)"

            # 撤权（直接 UPDATE：走 `revoke_participant` 会提升 write fence 从而作废全部
            # confirmation，那是 Task 21 的判据，混进来会让本场景的失败原因不可归因）。
            #
            # 🔴 **只置 `revoked_at`、不动 `state`**：reconciler 的 `eligible()` 有三条独立
            #    失格判据（非 closing / 已撤权 / lease 过期）。同时把 state 改成 `revoked`
            #    会让两条判据同时成立 ⇒ 删掉「已撤权」那条时另一条仍拒 ⇒ 判据 GREEN
            #    （M17 首轮实测正是这个形态）。一个场景只触发一条判据。
            async with Session() as s:
                await s.execute(
                    sa.update(WorkpaperOoParticipant)
                    .where(WorkpaperOoParticipant.id == predicted[2])
                    .values(revoked_at=datetime.now(timezone.utc))
                )
                await s.commit()

            rec["terminated"] = await _terminate_open_requests(ctx)
            rec["reconcile_after"] = await _reconcile(ctx)
            rec.update(await _close_facts(ctx))
            snap["close"]["leader_stale"] = rec
        except Exception as exc:  # noqa: BLE001
            _phase_failed("close_leader_stale", exc)

        # ═══ 阶段 8：无 successor → recovery_required + 零 capture ═══
        #
        # 失格方式取**lease 过期**（只动 `expires_at`），与阶段 7 的「已撤权」互不重叠：
        # 三条失格判据各由一个场景单独触发，任一条被删都有一个场景变红。
        try:
            ctx = await _make_room(generation=10, users=("user_a", "user_b"))
            rec = {"closes": []}
            for user in ("user_a", "user_b"):
                rec["closes"].append(await _close(ctx, user, tag="nosucc"))
            rec["terminated"] = await _terminate_open_requests(ctx)
            async with Session() as s:
                await s.execute(
                    sa.update(WorkpaperOoParticipant)
                    .where(WorkpaperOoParticipant.room_id == ctx["room_id"])
                    .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=5))
                )
                await s.commit()
            rec["reconcile"] = await _reconcile(ctx)
            rec.update(await _close_facts(ctx))
            snap["close"]["no_successor"] = rec
        except Exception as exc:  # noqa: BLE001
            _phase_failed("close_no_successor", exc)

        # ═══ 阶段 8b：participant 不在 `closing` → 不得成为 leader 候选 ═══
        #
        # 第三条失格判据的独立场景：只把 state 改回 `active`（未撤权、未过期）。
        # 正确行为 = 它不合格，successor 落到另一条 intent 上。
        try:
            ctx = await _make_room(generation=12, users=("user_a", "user_b"))
            rec = {"closes": []}
            for user in ("user_a", "user_b"):
                rec["closes"].append(await _close(ctx, user, tag="notclosing"))
            async with Session() as s:
                intents = list(
                    (
                        await s.execute(
                            sa.select(
                                WorkpaperOoCloseIntent.id,
                                WorkpaperOoCloseIntent.intent_sequence,
                                WorkpaperOoCloseIntent.participant_id,
                            ).where(
                                WorkpaperOoCloseIntent.room_id == ctx["room_id"],
                                WorkpaperOoCloseIntent.generation == ctx["generation"],
                            )
                        )
                    ).all()
                )
            assert len(intents) == 2, intents
            predicted = max(intents, key=lambda r: (int(r[1]), str(r[0])))
            rec["predicted_leader_intent_id"] = str(predicted[0])
            async with Session() as s:
                await s.execute(
                    sa.update(WorkpaperOoParticipant)
                    .where(WorkpaperOoParticipant.id == predicted[2])
                    .values(state=ParticipantState.active.value)
                )
                await s.commit()
            rec["terminated"] = await _terminate_open_requests(ctx)
            rec["reconcile_after"] = await _reconcile(ctx)
            rec.update(await _close_facts(ctx))
            snap["close"]["not_closing"] = rec
        except Exception as exc:  # noqa: BLE001
            _phase_failed("close_not_closing", exc)

        # ═══════════════════════════════════════════════════════════════════
        # 阶段 9：recovery 生命周期（三实体计数 + authorization-first claim）
        # ═══════════════════════════════════════════════════════════════════
        try:
            ctx = await _make_room(generation=11, users=("user_a",))
            inc = await _new_incoming(
                room_id=ctx["room_id"],
                generation=11,
                doc_key=ctx["doc_key"],
                tag="t30-recovery",
                sha=_d("incoming-recovery"),
            )
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                case = await repo.create_recovery_case(
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=ENTRY,
                    room_id=ctx["room_id"],
                    generation=11,
                    source_delivery_key=_d("delivery-t30-recovery"),
                    incoming_artifact_id=inc["artifact_id"],
                    reason=RecoveryReason.crash_close,
                    ttl=timedelta(hours=72),
                    candidate_confirmation_digest=_d("conf-cand"),
                    candidate_contributor_digest=contrib_digest,
                )
                case_id = case.id
                await s.commit()

            async def _case_counts(cid: uuid.UUID) -> dict[str, Any]:
                async with Session() as s:
                    row = (
                        await s.execute(
                            sa.select(
                                WorkpaperCallbackRecoveryCase.state,
                                WorkpaperCallbackRecoveryCase.recovery_request_id,
                                WorkpaperCallbackRecoveryCase.application_id,
                                WorkpaperCallbackRecoveryCase.operation_id,
                            ).where(WorkpaperCallbackRecoveryCase.id == cid)
                        )
                    ).one()
                return {
                    "state": str(row[0]),
                    "request_id": _opt(row[1]),
                    "application_id": _opt(row[2]),
                    "operation_id": _opt(row[3]),
                }

            snap["recovery"]["before_claim"] = await _case_counts(case_id)

            # 普通 retry 必须拒绝 nullable-operation case
            async with Session() as s:
                _r, _rm, ras, _c = _wire(s)
                snap["recovery"]["ordinary_retry_allowed"] = await ras.retry_eligibility(
                    operation_id=None
                )
                await s.rollback()

            # authorization-first claim：一个事务内建 request + shell + application + scope
            async with Session() as s:
                _r, _rm, ras, _c = _wire(s)
                claimed = await ras.claim_recovery(
                    case_id=case_id,
                    claiming_participant_id=ctx["participants"]["user_a"],
                    prior_confirmation_id=ctx["confirmations"]["user_a"],
                    idempotency_key="t30-recovery-claim",
                    adapter_id=adapter_id,
                    adapter_build_digest=adapter_digest,
                    contributor_snapshot_digest=contrib_digest,
                    current_revision=1,
                    actor_id=ids["user_a"],
                )
                claim_out = {
                    "shape": str(getattr(claimed, "operation_shape", "")),
                    "request_id": _opt(getattr(claimed, "request_id", None)),
                    "operation_id": _opt(getattr(claimed, "operation_id", None)),
                    "application_id": _opt(getattr(claimed, "application_id", None)),
                }
                await s.commit()
            snap["recovery"]["claim"] = claim_out
            snap["recovery"]["after_claim"] = await _case_counts(case_id)
            async with Session() as s:
                scope_rows = list(
                    (
                        await s.execute(
                            sa.select(
                                WorkpaperSyncScopeIndex.resource_kind,
                                WorkpaperSyncScopeIndex.resource_id,
                                WorkpaperSyncScopeIndex.retired_at,
                            ).where(
                                WorkpaperSyncScopeIndex.resource_id.in_(
                                    [
                                        v
                                        for v in (
                                            snap["recovery"]["after_claim"]["request_id"],
                                            snap["recovery"]["after_claim"]["operation_id"],
                                            snap["recovery"]["after_claim"]["application_id"],
                                        )
                                        if v
                                    ]
                                    or ["-"]
                                )
                            )
                        )
                    ).all()
                )
            snap["recovery"]["scope_rows"] = sorted(
                {str(r[0]) for r in scope_rows}
            )
            snap["recovery"]["scope_row_count"] = len(scope_rows)
            snap["recovery"]["scope_rows_live"] = sum(1 for r in scope_rows if r[2] is None)

            # download-only：三实体保持 0
            inc_dl = await _new_incoming(
                room_id=ctx["room_id"],
                generation=11,
                doc_key=ctx["doc_key"],
                tag="t30-recovery-dl",
                sha=_d("incoming-recovery-dl"),
            )
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                dl_case = await repo.create_recovery_case(
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=ENTRY,
                    room_id=ctx["room_id"],
                    generation=11,
                    source_delivery_key=_d("delivery-t30-recovery-dl"),
                    incoming_artifact_id=inc_dl["artifact_id"],
                    reason=RecoveryReason.crash_close,
                )
                dl_case_id = dl_case.id
                await s.commit()
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                await repo.terminate_recovery_download_only(
                    case_id=dl_case_id, actor_id=ids["user_a"]
                )
                await s.commit()
            snap["recovery"]["download_only"] = await _case_counts(dl_case_id)
        except Exception as exc:  # noqa: BLE001
            _phase_failed("recovery", exc)

        # ═══ 阶段 10：scope tombstone —— retire 只置 `retired_at`，行物理保留 ═══
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                probe_id = str(uuid.uuid4())
                await repo.register_scope(
                    resource_kind=ScopeResourceKind.forcesave_request,
                    resource_id=probe_id,
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=ENTRY,
                )
                await s.commit()
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                await repo.retire_scope(
                    resource_kind=ScopeResourceKind.forcesave_request,
                    resource_id=probe_id,
                )
                await s.commit()
            async with Session() as s:
                row = (
                    await s.execute(
                        sa.select(
                            WorkpaperSyncScopeIndex.resource_id,
                            WorkpaperSyncScopeIndex.retired_at,
                        ).where(WorkpaperSyncScopeIndex.resource_id == probe_id)
                    )
                ).all()
                snap["scope"]["tombstone"] = {
                    "rows_after_retire": len(row),
                    "retired_at_set": bool(row and row[0][1] is not None),
                }
                # id 不可复用 —— 服务层与库层各查一次。
                # 🔴 只查服务层不够：服务层拒是一个域异常，绕过服务直接写 SQL 时那道门
                #    根本不参与，所以必须另证库里也有一道（tombstone 防复用的最终依据）。
                entry = {}
                try:
                    repo = WorkpaperSyncRepository(s)
                    await repo.register_scope(
                        resource_kind=ScopeResourceKind.forcesave_request,
                        resource_id=probe_id,
                        project_id=project_id,
                        wp_id=wp_id,
                        entry_id=ENTRY,
                    )
                    await s.commit()
                    entry["accepted"] = True
                except Exception as exc:  # noqa: BLE001
                    await s.rollback()
                    entry["accepted"] = False
                    entry["error_type"] = type(exc).__name__
                    entry["blame"] = _blame(exc)
                snap["scope"]["id_reuse"] = entry
            # `register_scope` 的**域层**拒绝是否还在（不是靠库层唯一索引兜底）。
            # 只断言「被拒」时，把域层判定短路成 `if False` 后 INSERT 会撞唯一索引 ⇒
            # 仍然「被拒」⇒ 判据 GREEN。故这里要求拒绝类型必须是域异常。
            snap["scope"]["id_reuse"]["is_domain_refusal"] = (
                snap["scope"]["id_reuse"].get("error_type") == "ScopeIntegrityError"
            )
            async with Session() as s:
                entry = {}
                try:
                    await s.execute(
                        sa.text(
                            "INSERT INTO working_paper_sync_scope_index "
                            "(resource_kind, resource_id, project_id, wp_id, entry_id) "
                            "VALUES ('forcesave_request', :rid, :pid, :wid, :eid)"
                        ),
                        {
                            "rid": probe_id,
                            "pid": str(project_id),
                            "wid": str(wp_id),
                            "eid": ENTRY,
                        },
                    )
                    await s.commit()
                    entry["accepted"] = True
                except Exception as exc:  # noqa: BLE001
                    await s.rollback()
                    entry["accepted"] = False
                    entry["blame"] = _blame(exc)
                snap["scope"]["id_reuse_raw_sql"] = entry
            # 物理删除必须也被库层拒（tombstone 不可清）。
            async with Session() as s:
                entry = {}
                try:
                    await s.execute(
                        sa.text(
                            "DELETE FROM working_paper_sync_scope_index "
                            "WHERE resource_id = :rid"
                        ),
                        {"rid": probe_id},
                    )
                    await s.commit()
                    entry["accepted"] = True
                except Exception as exc:  # noqa: BLE001
                    await s.rollback()
                    entry["accepted"] = False
                    entry["blame"] = _blame(exc)
                snap["scope"]["physical_delete"] = entry
        except Exception as exc:  # noqa: BLE001
            _phase_failed("scope", exc)

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


# ═══════════════════════════════════════════════════════════════════════════
# §0 采集自身的健康（禁 fail-open）
# ═══════════════════════════════════════════════════════════════════════════


def test_real_postgres_and_v151_applied(snap: dict[str, Any]) -> None:
    assert "PostgreSQL" in str(snap["server_version"]), snap["server_version"]
    assert snap["apply_errors"] == [], snap["apply_errors"]


def test_no_phase_crashed_during_collection(snap: dict[str, Any]) -> None:
    """任一阶段崩了 ⇒ 该阶段的判据是在**旧快照/空字典**上评估的（假绿）。"""
    assert snap["harness_errors"] == {}, snap["harness_errors"]


# ═══════════════════════════════════════════════════════════════════════════
# §1 normal shell → durable application correlation（AC 4.1 / 5.4 / 5.5）
# ═══════════════════════════════════════════════════════════════════════════


def test_accepted_creates_a_shell_with_both_links_null_and_zero_applications(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 4.1, 5.4**"""
    acc = snap["shell"]["accepted"]
    assert acc["shape"] == "pre_correlation", acc
    assert acc["db_application_id"] is None, acc
    assert acc["db_duplicate_of"] is None, acc
    assert acc["db_request_link"] == acc["request_id"], acc
    assert acc["application_rows"] == 0, acc
    assert acc["fingerprint_is_digest"] is True, acc


def test_durable_correlation_binds_the_same_operation_as_primary(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 5.4, 5.5**

    同一条 requested operation 上原地变成 primary —— 不新建 operation、不建链。
    """
    cor = snap["shell"]["correlated"]
    assert cor["shape"] == "primary", cor
    assert cor["created_application"] is True, cor
    assert cor["db_application_id"] is not None, cor
    assert cor["db_duplicate_of"] is None, cor
    assert cor["db_is_primary"] is True, cor
    assert cor["db_state"] == "application_bound", cor
    assert cor["self_superseded"] is False, cor


def test_application_key_is_the_frozen_identity_digest(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 5.5, 8.5**

    库里的 key 必须与由**冻结身份**独立重算出的 key 逐字相同（两条推导链比对）。
    """
    cor = snap["shell"]["correlated"]
    assert cor["key_is_digest"] is True, cor
    assert cor["actual_key"] == cor["expected_key"], cor


def test_origin_and_effective_sequence_start_equal(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 5.5**"""
    cor = snap["shell"]["correlated"]
    assert cor["origin_sequence"] == cor["effective_sequence"], cor


# ═══════════════════════════════════════════════════════════════════════════
# §2 收敛：1 primary + N-1 direct terminal duplicates，零 stranded
# ═══════════════════════════════════════════════════════════════════════════


def test_the_convergence_race_really_contended(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 5.5**

    「恰一个 primary」在**串行**执行下也成立，所以必须先证明并发真的发生了：
    N 条不同的后端连接，且最后一个进入 barrier 的时刻早于第一次 `correlate` 调用。
    没有这一条时，把 barrier 删掉退化成串行循环，下面全部判据照样绿。
    """
    race = snap["race"]
    assert race["n"] == RACE_N, race
    assert race["distinct_backend_pids"] == RACE_N, race
    assert race["max_t_ready"] <= race["min_t_call"], race
    assert race["committed"] == RACE_N, [
        r for r in race["results"] if not r.get("committed")
    ]


def test_the_race_yields_exactly_one_application_and_one_creator(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 5.5**

    「恰一个」要**正面**证到：行数为 1（partial unique 只给 at-most-one），
    且恰有一个 racer 报告自己是创建者（否则 1 行可能来自零次创建 + 某处预建）。
    """
    race = snap["race"]
    assert race["application_rows"] == 1, race
    assert race["distinct_application_keys"] == 1, race
    assert race["created_application_count"] == 1, race


def test_the_race_yields_one_primary_and_n_minus_one_direct_terminal_duplicates(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 5.5, 8.5**"""
    race = snap["race"]
    assert race["primary_count"] == 1, race
    assert race["duplicate_count"] == RACE_N - 1, race
    assert race["duplicate_states"] == ["duplicate"], race
    assert race["duplicate_targets_are_the_primary"] is True, race


def test_the_race_leaves_no_stranded_chained_or_cyclic_shell(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 5.5**

    三种坏形态各自独立：stranded（两个 link 都空）、chained（duplicate 指向 duplicate）、
    cyclic（自指）。只查其中一种会漏掉另外两种。
    """
    race = snap["race"]
    assert race["stranded_count"] == 0, race
    assert race["chained_count"] == 0, race
    assert race["cyclic_count"] == 0, race


# ═══════════════════════════════════════════════════════════════════════════
# §3 same-application higher sequence fold
# ═══════════════════════════════════════════════════════════════════════════


def test_the_fold_path_actually_executed(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 5.5**

    先证 fold 真的跑过（至少一次 correlate 报出 `folded_from`）。只断言最终
    `effective == max` 时，「压根没 fold、就是第一次写进去的最大值」也满足 ——
    Task 23 首轮实测过这种「场景全绿而被测路径一次未跑」的形态。
    """
    fold = snap["fold"]
    assert len(fold["seeded_sequences"]) == 3, fold
    assert fold["seeded_sequences"] == sorted(fold["seeded_sequences"]), fold
    assert fold["fold_events"] >= 1, fold


def test_fold_keeps_origin_immutable_and_never_self_supersedes(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 5.5, 8.10**"""
    fold = snap["fold"]
    assert fold["application_rows"] == 1, fold
    assert fold["origin_sequence"] == min(fold["seeded_sequences"]), fold
    assert fold["effective_sequence"] == max(fold["seeded_sequences"]), fold
    assert fold["self_superseded"] is False, fold


# ═══════════════════════════════════════════════════════════════════════════
# §4 复合幂等键 + frozen_request_fingerprint
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "case",
    ["cross_participant", "payload_differs", "contributors_differ"],
    ids=["cross_participant", "payload_differs", "contributors_differ"],
)
def test_reusing_one_idempotency_key_conflicts_without_leaking_prior_ids(
    snap: dict[str, Any], case: str
) -> None:
    """**Validates: Requirements 4.1, 10.5**"""
    entry = snap["idempotency"][case]
    assert entry["accepted"] is False, entry
    assert entry.get("unexpected") is not True, entry
    assert entry["error_type"] == "IdempotencyConflictError", entry
    assert entry["leaks_prior_request"] is False, entry
    assert entry["leaks_prior_operation"] is False, entry
    assert entry["operation_rows_delta"] == 0, entry


def test_an_identical_replay_is_a_cache_hit_not_a_conflict(snap: dict[str, Any]) -> None:
    """反向自检：409 不是恒真 —— 逐字等值重放必须命中缓存并返回同一 request。"""
    entry = snap["idempotency"]["identical_replay"]
    assert entry["accepted"] is True, entry
    assert entry["cache_hit"] is True, entry


# ═══════════════════════════════════════════════════════════════════════════
# §5 quarantined incoming：三层拒绝
# ═══════════════════════════════════════════════════════════════════════════


def test_quarantined_incoming_never_becomes_durable(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 5.6**"""
    art = snap["quarantine"]["artifact"]
    assert art["state"] == "quarantined", art
    assert art["durable_at_is_null"] is True, art


def test_quarantined_incoming_is_refused_at_the_application_entry(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 5.6**

    Task 29 把这条场景登记成 evidence-schema 债（记不成 `passed`）。**行为**在这里验：
    correlate 必须拒，且一行 application 都不许多出来。
    """
    entry = snap["quarantine"]["application"]
    assert entry["accepted"] is False, entry
    assert entry["application_rows_delta"] == 0, entry
    # 🔴 必须断言到**隔离**这条拒绝，不能只断言「被拒」：`assert_incoming_durable` 里
    #    「state != durable」那条兜底会把 quarantined 也拒掉，两条分支共享结果 ⇒ 只断言
    #    「被拒」时，把隔离那道门短路成 `if False` 照样绿（M15 首轮实测 GREEN）。
    assert entry["is_quarantine_error"] is True, entry


def test_a_quarantined_artifact_cannot_back_a_representation(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 5.6, 2.10**

    第三层（库内）：published representation 不得指向 quarantined incoming。
    """
    entry = snap["quarantine"]["representation_artifact"]
    assert entry["accepted"] is False, entry
    # 拒绝必须来自「artifact 形态」那一道门，而不是随便一个错误（否则探针写错也算过）。
    assert entry["blame"]["mentions"] or "artifact" in entry["blame"]["text"], entry


# ═══════════════════════════════════════════════════════════════════════════
# §6 close exactly-one
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "case", ["single", "order_ab", "order_ba"], ids=["single", "order_ab", "order_ba"]
)
def test_close_yields_exactly_one_capture(snap: dict[str, Any], case: str) -> None:
    """**Validates: Requirements 4.11, 5.9**

    三个场景（单人、A→B、B→A）最终都恰一条 close capture。
    """
    rec = snap["close"][case]
    assert rec["all_captures"] == 1, rec
    # 「恰一次创建」：capture 只能在 open 或某次 reconcile 中被创建**一次**。
    creations = sum(1 for c in rec["closes"] if c["capture_created"]) + sum(
        1 for key in ("reconcile_1", "reconcile_2") if rec[key]["capture_created"]
    )
    assert creations == 1, rec


@pytest.mark.parametrize(
    "case", ["single", "order_ab", "order_ba"], ids=["single", "order_ab", "order_ba"]
)
def test_no_capture_exists_before_predecessors_are_terminal(
    snap: dict[str, Any], case: str
) -> None:
    """**Validates: Requirements 4.11**（close barrier：predecessor 未 terminal 不得提升）

    判据按 `has_predecessor` 分支：barrier 只在**有** predecessor 时推迟提升。
    对没有 predecessor 的场景断言「terminal 前零 capture」会把正确行为判成违规，
    也会掩盖真正的 barrier 缺陷（把它改成恒不推迟时，有 predecessor 那两个场景才会红）。
    """
    rec = snap["close"][case]
    if rec["any_predecessor"]:
        assert rec["captures_before_terminal"] == 0, rec
        assert rec["terminated"] >= 1, rec
    else:
        assert rec["captures_before_terminal"] == 1, rec
    # 至少要有一个场景真的走过「推迟」分支，否则 barrier 判据从未被执行。
    assert any(
        other["any_predecessor"] and other["captures_before_terminal"] == 0
        for other in snap["close"].values()
        if "any_predecessor" in other
    ), {k: v.get("any_predecessor") for k, v in snap["close"].items()}


@pytest.mark.parametrize(
    "case", ["single", "order_ab", "order_ba"], ids=["single", "order_ab", "order_ba"]
)
def test_reconciler_is_reentrant_and_keeps_the_same_leader(
    snap: dict[str, Any], case: str
) -> None:
    """**Validates: Requirements 5.9**

    重入不得再建 capture、不得换 leader，且同一 eligibility snapshot 的 digest 相同。
    """
    rec = snap["close"][case]
    assert rec["reconcile_2"]["capture_created"] is False, rec
    assert rec["reconcile_2"]["leader_intent_id"] == rec["reconcile_1"]["leader_intent_id"], rec
    assert (
        rec["reconcile_2"]["eligibility_digest"] == rec["reconcile_1"]["eligibility_digest"]
    ), rec
    assert rec["all_captures"] == 1, rec


def test_the_leader_comparator_really_ran_on_more_than_one_candidate(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 5.9**

    「重入不换 leader」在只剩一条候选或 promoted 幂等短路时**恒真**。所以必须有一个
    场景真的让 comparator 在 ≥2 个候选上跑过 —— 否则这条判据从未被执行。
    """
    def _first(rec: dict[str, Any]) -> dict[str, Any]:
        return rec.get("reconcile_after") or rec.get("reconcile") or rec.get("reconcile_1", {})

    counts = {name: _first(rec).get("eligible_count") for name, rec in snap["close"].items()}
    multi = [(name, rec) for name, rec in snap["close"].items() if (_first(rec).get("eligible_count") or 0) >= 2]
    assert multi, counts
    for name, rec in multi:
        assert _first(rec)["promoted_short_circuit"] is False, (name, _first(rec))


def test_leader_revoked_before_promotion_yields_a_legitimate_successor(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 5.9, 10.9**

    leader 失权 ⇒ 写 `authorization_stale` 审计、选出合法 successor，最终仍恰一条 capture。

    「本应是 leader 的那一条」由本文件按最高 `(intent_sequence, id)` **独立算出**，
    不问服务 —— 问服务等于用被测代码给自己出题。
    """
    rec = snap["close"]["leader_stale"]
    after = rec["reconcile_after"]
    predicted = rec["predicted_leader_intent_id"]
    assert after["leader_intent_id"] is not None, rec
    assert after["leader_intent_id"] != predicted, rec
    assert predicted in after["stale_reported"], rec
    assert rec["authorization_stale_events"] >= 1, rec
    assert "authorization_stale" in rec["intent_states"], rec
    assert rec["all_captures"] == 1, rec
    assert after["no_successor"] is False, rec
    assert after["leader_intent_id"] in rec["promoted_intents"], rec


def test_a_non_closing_participant_is_not_a_leader_candidate(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 4.10, 5.9**

    第三条失格判据（participant 不在 `closing`）的独立场景：只把 state 改回 `active`，
    未撤权、未过期。正确行为是它不合格、`authorization_stale` 有审计、leader 落到另一条 intent。

    🔴 capture 保持 **0** 是正确的、不是缺陷：房里又有一个 `active` 编辑者，close barrier
    本就不该放行。所以本条不断言 capture 数（那属于阶段 6 的判据），只断言「非 closing 的
    候选不得当 leader」。
    """
    rec = snap["close"]["not_closing"]
    after = rec["reconcile_after"]
    assert after["leader_intent_id"] is not None, rec
    assert after["leader_intent_id"] != rec["predicted_leader_intent_id"], rec
    assert rec["predicted_leader_intent_id"] in after["stale_reported"], rec
    assert rec["authorization_stale_events"] >= 1, rec
    assert rec["all_captures"] == 0, rec


def test_no_successor_lands_recovery_required_with_zero_capture(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 5.9**

    全部 participant 的 lease 过期 ⇒ `recovery_required` + 零 capture + 不留活 intent
    （不得永久阻塞）。失格方式刻意只用「过期」这一条，与撤权/非 closing 两个场景不重叠。
    """
    rec = snap["close"]["no_successor"]
    assert rec["reconcile"]["no_successor"] is True, rec
    assert rec["reconcile"]["capture_created"] is False, rec
    assert rec["all_captures"] == 0, rec
    assert "recovery_required" in rec["intent_states"], rec
    assert rec["live_intents"] == 0, rec


# ═══════════════════════════════════════════════════════════════════════════
# §7 recovery 生命周期
# ═══════════════════════════════════════════════════════════════════════════


def test_a_crash_case_has_all_three_entities_null_before_claim(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 5.8**"""
    before = snap["recovery"]["before_claim"]
    assert before["state"] == "unclaimed", before
    assert before["request_id"] is None, before
    assert before["application_id"] is None, before
    assert before["operation_id"] is None, before


def test_ordinary_retry_refuses_a_nullable_operation_case(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 5.8, 8.7**"""
    assert snap["recovery"]["ordinary_retry_allowed"] is False, snap["recovery"]


def test_authorization_first_claim_creates_all_three_and_their_scope_rows(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 5.8, 10.1, 10.2**

    claim 成功后三实体同时出现，且它们的 scope index 行**在同一事务内**就已存在
    （回读时全部存活、无 `retired_at`）。
    """
    after = snap["recovery"]["after_claim"]
    assert after["request_id"] is not None, after
    assert after["operation_id"] is not None, after
    assert after["application_id"] is not None, after
    assert after["state"] == "application_created", after
    assert snap["recovery"]["scope_row_count"] >= 3, snap["recovery"]
    assert snap["recovery"]["scope_rows_live"] == snap["recovery"]["scope_row_count"], (
        snap["recovery"]
    )


def test_download_only_keeps_all_three_entities_null(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 5.8**"""
    dl = snap["recovery"]["download_only"]
    assert dl["state"] == "download_only", dl
    assert dl["request_id"] is None, dl
    assert dl["application_id"] is None, dl
    assert dl["operation_id"] is None, dl


# ═══════════════════════════════════════════════════════════════════════════
# §8 scope tombstone
# ═══════════════════════════════════════════════════════════════════════════


def test_retiring_a_scope_row_keeps_the_tombstone_physically(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 10.11**"""
    tomb = snap["scope"]["tombstone"]
    assert tomb["rows_after_retire"] == 1, tomb
    assert tomb["retired_at_set"] is True, tomb


def test_a_retired_resource_id_cannot_be_reused(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 10.11**

    两层各查一次：服务层拒（域异常）+ 库层拒（绕过服务直接 INSERT 时的最终依据）。
    只查服务层时，任何绕过服务的写路径都能复活一个已退役的 id。
    """
    entry = snap["scope"]["id_reuse"]
    assert entry["accepted"] is False, entry
    assert entry["is_domain_refusal"] is True, entry
    raw = snap["scope"]["id_reuse_raw_sql"]
    assert raw["accepted"] is False, raw
    assert raw["blame"]["sqlstate"] == "23505", raw


def test_a_scope_tombstone_cannot_be_physically_deleted(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 10.11**（tombstone 不可物理删除/清空）"""
    entry = snap["scope"]["physical_delete"]
    assert entry["accepted"] is False, entry
    # 拒绝必须来自库内 trigger（`RAISE` ⇒ sqlstate 23514）并指名这张表 + `retired_at`，
    # 否则「探针 SQL 写错」也会被算成「删除被拒」。
    assert entry["blame"]["sqlstate"] == "23514", entry
    assert "working_paper_sync_scope_index" in entry["blame"]["text"], entry
    assert "retired_at" in entry["blame"]["text"], entry
