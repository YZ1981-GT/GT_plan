# -*- coding: utf-8 -*-
"""Task 23 真实 PostgreSQL 行为守卫：frozen request、application 去重与 sequence 收敛。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 23
Requirements: 2.9, 4.1, 4.3, 4.10, 4.11, 5.4, 5.5, 5.10, 8.5, 10.5, 10.11, 14.3
Properties: **P18 / P36 / P56 / P62 / P64**

═══ 为什么必须真库，而且必须**真并发** ═══

Task 22 已经把 `correlate_durable_incoming` 的串行路径（winner 建 application、重放命中）
在真库上跑通，并测了 `application_key UNIQUE` 与 `uq_wpso_request` 两条唯一约束。
它**显式把并发留给了本任务**（Task 22 证据 §八.3）。

Property 18 的核心断言不是「有两条唯一约束」，而是：**N 个并发 shell 命中同一 application
key 时，恰好 1 个 primary、N−1 个 direct terminal duplicate、0 个 stranded/链/环**。
串行循环不能discharge它 —— 串行下 `INSERT ... ON CONFLICT DO NOTHING` 的冲突分支和
`SELECT ... FOR UPDATE` 的等锁分支根本不会被真正触发（第二次调用时第一次早已提交，
`FOR UPDATE` 不会阻塞，也就无法证明「阻塞后再读能看到 winner」）。因此本模块的并发场景
用 **N 条独立连接 + `asyncio.Barrier`** 让 N 个事务真正同时打开，并记录每个任务的
`pg_backend_pid()` 与四个单调时刻，把「真的并发了」变成可断言的事实而不是自述。

`DATABASE_URL` 非 PostgreSQL 时**直接失败而不是 skip** —— 与 Task 10/21/22 同约定。

═══ 隔离与采集 ═══

scratch schema `tmp_task23_ra_<hex>`，`search_path` 只含它，结束 `DROP SCHEMA CASCADE`。
全部场景由**一次 `asyncio.run`** 跑完落进快照（module fixture）。采集阶段的异常一律
**记录不穿透**：异常穿透会把整个 module 变成 collection ERROR，而 pytest 的 `-rf` 只列
FAILED 不列 ERROR ⇒ 定向变异看不到任何预期失败项 ⇒ 判 GREEN。
`test_no_phase_crashed_during_collection` 是这个决定的另一半。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sys
import time
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

_SCHEMA_PREFIX = "tmp_task23_ra_"

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

#: Property 18 的并发度。8 条独立连接：足以让「winner 建 + 多个 loser 等锁 + 部分 loser
#: 因 sequence 更低而不 fold」三条分支都被覆盖，又不至于把测试时间拖到分钟级。
RACE_N = 8


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _opt(value: object) -> str | None:
    """可空 UUID → `str | None`。

    `str(None) == "None"` 是真值：用 `str(x)` 投影再判空，会把「这一列根本没写上」
    判成「写上了」。
    """
    return None if value is None else str(value)


def _err(exc: BaseException) -> str:
    """异常 → 单行诊断，**带最后几帧**（只记 `type: message` 时无法定位）。"""
    import traceback

    frames = traceback.extract_tb(exc.__traceback__)[-4:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


# ═══════════════════════════════════════════════════════════════════════════
# DB 拒绝原因归因（与 Task 22 同形，注释见该文件）
# ═══════════════════════════════════════════════════════════════════════════

_CONSTRAINT_IN_TEXT = re.compile(r'constraint "([a-z0-9_]+)"')
_CK_IN_TEXT = re.compile(r"\b((?:ck|uq)_[a-z0-9_]+)\b")
_TRIGGER_FN_IN_TEXT = re.compile(r"\b(wpsync_check_[a-z0-9_]+)\b")


def _blame(exc: BaseException) -> dict[str, Any]:
    """把一次 DB 拒绝归因到**具体**约束/trigger，并记下**全部**被提到的约束名。

    `mentions` 是必需的：真值表要求「只违反自己那一条」，只记一个名字时，一行同时撞两条
    约束的情形会被静默归成其中一条，而下一个人会据此以为自己声明的那条还活着。
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
    if sqlstate == "23505":
        source = "unique"
    elif sqlstate == "23503":
        source = "foreign_key"
    elif sqlstate == "23514":
        source = "check_constraint" if named else "trigger_raise"
    elif sqlstate in ("42804", "42883", "42703", "42P01", "22P02", "42P10"):
        source = "probe_defect"
    else:
        source = "other"
    return {
        "type": type(exc).__name__,
        "constraint": named,
        "mentions": mentions,
        "sqlstate": sqlstate,
        "source": source,
        "text": text[:400],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 采集
# ═══════════════════════════════════════════════════════════════════════════


async def _collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部场景
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.workpaper_sync_models import (
        WorkpaperContentApplication,
        WorkpaperContentApplicationEvent,
        WorkpaperOoRoom,
        WorkpaperSyncOperation,
        WorkpaperSyncOperationEvent,
    )
    from app.services.workpaper_sync.models import (
        ActorType,
        ApplicationEventType,
        ArtifactKind,
        ArtifactState,
        BundleSlot,
        BundleSlotSpec,
        OperationShape,
        ParticipantMode,
        RecoveryReason,
        RequestKind,
        ScopeResourceKind,
        SupersedeError,
        compute_application_key,
        compute_frozen_request_fingerprint,
    )
    from app.services.workpaper_sync.repository import (
        IdempotencyConflictError,
        WorkpaperSyncRepository,
    )
    from app.services.workpaper_sync.request_application import (
        ApplicationPrecreatedError,
        CanonicalBindingError,
        CanonicalPrimaryUnboundError,
        OperationScopeNotVisibleError,
        ReadStage,
        RequestApplicationService,
        ScopeAuthorizationDeniedError,
    )
    from app.services.workpaper_sync.rooms import (
        RoomNotWritableError,
        RoomScope,
        RoomService,
        mint_route_credential,
    )

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 23 的判据是 V151 的 application/operation 约束与 **真并发** 下的 "
            "primary/duplicate 收敛（Property 18），必须真实 PostgreSQL；"
            f"当前 DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}。"
            "此处**不 skip** —— skip 等于静默抹掉本任务唯一判据。"
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
        "accepted": {},
        "idempotency": {},
        "fingerprint_fields": {},
        "race": {},
        "fold_race": {},
        "constraints": {},
        "key_ownership": {},
        "multi_delivery": {},
        "read_path": {},
        "recovery": {},
        "refresh_required": {},
        "subsumption": {},
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

        ids = {
            "project": uuid.uuid4(),
            "user_a": uuid.uuid4(),
            "user_b": uuid.uuid4(),
            "wp": uuid.uuid4(),
        }
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{ids['project']}')")
            for u in ("user_a", "user_b"):
                await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{ids[u]}')")
            await conn.exec_driver_sql(
                "INSERT INTO working_paper (id, project_id) VALUES "
                f"('{ids['wp']}', '{ids['project']}')"
            )

        project_id, wp_id = ids["project"], ids["wp"]
        scope = RoomScope(project_id=project_id, wp_id=wp_id, entry_id=ENTRY)
        base_path = f"storage/{project_id}/workpapers"

        # ═══ 世界：definitions / bundle / representation ═══════════════════
        async def _build_world(repo: WorkpaperSyncRepository, *, tag: str) -> dict[str, Any]:
            blobs: dict[str, Any] = {}
            for name in ("tpl", "instr", "contract", "authority", "bundle_payload"):
                blobs[name] = await repo.register_artifact(
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=ArtifactKind.definition,
                    state=ArtifactState.published,
                    relative_path=f"{base_path}/.versions/{wp_id}/definitions/{tag}-{name}.json",
                    sha256=_d(f"blob-{tag}-{name}"),
                    size_bytes=1024,
                    document_type="json",
                )
            tpl = await repo.create_definition_artifact(
                kind="template",
                logical_id=f"d2.template.{tag}",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["tpl"].id,
                sha256=_d(f"tpl-def-{tag}"),
                structure_hash=_d(f"tpl-structure-{tag}"),
                source_commit="task23",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation",
                logical_id=f"d2.instrumentation.{tag}",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["instr"].id,
                sha256=_d(f"instr-def-{tag}"),
                structure_hash=_d(f"instr-structure-{tag}"),
                source_commit="task23",
            )
            con = await repo.create_definition_artifact(
                kind="contract",
                logical_id=f"d2.contract.{tag}",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["contract"].id,
                sha256=_d(f"contract-def-{tag}"),
                source_commit="task23",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model",
                logical_id=f"authority.projection.{tag}",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["authority"].id,
                sha256=_d(f"authority-def-{tag}"),
                authority_model_type="projection_contract",
                source_commit="task23",
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
                canonical_payload_sha256=_d(f"bundle-canonical-{tag}"),
            )
            proj_art = await repo.register_artifact(
                project_id=project_id,
                wp_id=wp_id,
                kind=ArtifactKind.projection,
                state=ArtifactState.published,
                relative_path=f"{base_path}/.versions/{wp_id}/projections/{tag}.json.gz",
                sha256=_d(f"projection-{tag}"),
                size_bytes=2048,
                document_type="json.gz",
            )
            canon = await repo.register_artifact(
                project_id=project_id,
                wp_id=wp_id,
                kind=ArtifactKind.canonical,
                state=ArtifactState.published,
                relative_path=(
                    f"{base_path}/.versions/{wp_id}/representations/{ENTRY}/{tag}.xlsx"
                ),
                sha256=_d(f"canonical-{tag}"),
                size_bytes=40960,
                document_type="xlsx",
            )
            cv = await repo.create_content_version(
                project_id=project_id,
                wp_id=wp_id,
                entry_id=ENTRY,
                revision=1 if tag == "g1" else 2,
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
                adapter_build_digest=_d(f"adapter-build-{tag}"),
                structure_hash=_d(f"structure-{tag}"),
                identity_inventory_sha256=_d(f"identity-{tag}"),
                reason="content_commit",
            )
            await repo.set_entry_pointer(
                wp_id=wp_id, entry_id=ENTRY, representation_id=rep.id, generation=1
            )
            return {
                "bundle": bundle,
                "authority": authority,
                "content_version": cv,
                "representation": rep,
                "projection_sha256": proj_art.sha256,
                "adapter_build_digest": _d(f"adapter-build-{tag}"),
            }

        world: dict[str, Any] = {}
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            world.update(await _build_world(repo, tag="g1"))
            await s.commit()

        rep_id = world["representation"].id
        cv_id = world["content_version"].id
        bundle_id = world["bundle"].id
        projection_sha = world["projection_sha256"]
        adapter_build = world["adapter_build_digest"]

        # ═══ room / participant / confirmation ════════════════════════════
        room_id: uuid.UUID | None = None
        part_a_id: uuid.UUID | None = None
        part_b_id: uuid.UUID | None = None
        conf_a_id: uuid.UUID | None = None
        doc_key = ""
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                room, _frozen = await svc.open_or_reuse_room(
                    scope,
                    representation=world["representation"],
                    opened_base_version_id=cv_id,
                )
                room_id, doc_key = room.id, room.doc_key
                pa = await svc.join_participant(
                    scope, room_id=room_id, user_id=ids["user_a"],
                    mode=ParticipantMode.edit, permission_epoch=5, lease_token="lease-a",
                )
                pb = await svc.join_participant(
                    scope, room_id=room_id, user_id=ids["user_b"],
                    mode=ParticipantMode.edit, permission_epoch=5, lease_token="lease-b",
                )
                part_a_id, part_b_id = pa.id, pb.id
                frozen = await svc.frozen_bundle_identity(bundle_id)
                conf_a, _room_after = await svc.confirm_descriptor(
                    scope, room_id=room_id, participant_id=part_a_id,
                    representation_id=rep_id, content_version_id=cv_id,
                    projection_sha256=projection_sha, idempotency_key="ready-a",
                    expected_bundle=frozen,
                )
                conf_a_id = conf_a.id
                await svc.confirm_descriptor(
                    scope, room_id=room_id, participant_id=part_b_id,
                    representation_id=rep_id, content_version_id=cv_id,
                    projection_sha256=projection_sha, idempotency_key="ready-b",
                    expected_bundle=frozen,
                )
                await s.commit()
        except Exception as exc:  # noqa: BLE001 - 记录而非穿透
            _phase_failed("bootstrap_room", exc)
            raise _HarnessError(f"room bootstrap 失败，后续场景无意义: {_err(exc)}") from exc

        assert room_id is not None and part_a_id is not None and part_b_id is not None
        assert conf_a_id is not None

        # ── 一个 durable incoming（全部 correlation 共用同一份字节）───────────
        #
        # V151 的 `wpsync_check_artifact_identity` 要求 incoming 必须绑定
        # `source_delivery_id`（incoming 字节的唯一来源就是一次 callback 投递），
        # 所以先建 delivery 行再建 artifact。绕过这条会得到
        # CheckViolationError —— 那是**约束在工作**，不是探针可以放宽的地方。
        incoming_sha = _d("incoming-bytes-task23")
        incoming_id: uuid.UUID | None = None

        async def _new_incoming(
            repo: WorkpaperSyncRepository, *, tag: str, sha: str
        ) -> uuid.UUID:
            cred = mint_route_credential(room_id=room_id, generation=1, doc_key=doc_key)
            delivery = await repo.record_delivery(
                project_id=project_id,
                wp_id=wp_id,
                entry_id=ENTRY,
                room_id=room_id,
                generation=1,
                route_credential_id=cred.credential_id,
                callback_status=6,
                delivery_key=_d(f"delivery-{tag}"),
                payload_sha256=_d(f"payload-{tag}"),
            )
            # `wpsync_check_artifact_incoming_path` 要求路径里含
            # `.incoming/{wp_id}/{delivery_id}/` —— incoming 的落盘位置由 delivery
            # identity 决定，不能自定目录（否则两次投递可能写同一文件）。
            art = await repo.register_artifact(
                project_id=project_id,
                wp_id=wp_id,
                kind=ArtifactKind.incoming,
                state=ArtifactState.durable,
                relative_path=(
                    f"{base_path}/.incoming/{wp_id}/{delivery.id}/{tag}.xlsx"
                ),
                sha256=sha,
                size_bytes=51200,
                document_type="xlsx",
                source_delivery_id=delivery.id,
            )
            return art.id

        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            incoming_id = await _new_incoming(repo, tag="task23", sha=incoming_sha)
            await s.commit()
        assert incoming_id is not None

        # ═══ 阶段 1：accepted 前形态（AC 4.1 / P64）═══════════════════════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                ras = RequestApplicationService(repo)
                accepted = await ras.freeze_and_persist_request(
                    scope,
                    room_id=room_id,
                    participant_id=part_a_id,
                    idempotency_key="accepted-1",
                    client_edit_epoch=3,
                    contributor_user_ids=[ids["user_a"]],
                    created_by=ids["user_a"],
                )
                # 真读库核对，而不是信返回对象
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
                            sa.select(sa.func.count()).select_from(WorkpaperContentApplication)
                        )
                    ).scalar_one()
                )
                snap["accepted"] = {
                    "request_id": str(accepted.request.id),
                    "operation_id": str(accepted.operation.id),
                    "shape": accepted.operation_shape.value,
                    "cache_hit": accepted.cache_hit,
                    "request_sequence": accepted.request_sequence,
                    "db_application_id": _opt(row[0]),
                    "db_duplicate_of": _opt(row[1]),
                    "db_state": str(row[2]),
                    "db_request_link": _opt(row[3]),
                    "application_rows_in_schema": app_rows,
                    "accepted_application_count": accepted.application_count,
                    "fingerprint_is_digest": bool(
                        re.fullmatch(r"[0-9a-f]{64}", accepted.frozen_request_fingerprint)
                    ),
                    "request_state": str(accepted.request.state),
                }
                # 幂等重放：逐项等值 ⇒ 同 id + cache_hit
                replay = await ras.freeze_and_persist_request(
                    scope,
                    room_id=room_id,
                    participant_id=part_a_id,
                    idempotency_key="accepted-1",
                    client_edit_epoch=3,
                    contributor_user_ids=[ids["user_a"]],
                    created_by=ids["user_a"],
                )
                snap["accepted"]["replay_cache_hit"] = replay.cache_hit
                snap["accepted"]["replay_same_request"] = (
                    replay.request.id == accepted.request.id
                )
                snap["accepted"]["replay_same_operation"] = (
                    replay.operation.id == accepted.operation.id
                )
                await s.commit()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("accepted", exc)

        prior_request_id = snap.get("accepted", {}).get("request_id", "")
        prior_operation_id = snap.get("accepted", {}).get("operation_id", "")

        # ═══ 阶段 2：409 且不返回旧标识（AC 4.1）═════════════════════════
        async def _conflict_case(name: str, **over: Any) -> None:
            kwargs: dict[str, Any] = {
                "room_id": room_id,
                "participant_id": part_a_id,
                "idempotency_key": "accepted-1",
                "client_edit_epoch": 3,
                "contributor_user_ids": [ids["user_a"]],
                "created_by": ids["user_a"],
            }
            kwargs.update(over)
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                ras = RequestApplicationService(repo)
                before = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count()).select_from(WorkpaperSyncOperation)
                        )
                    ).scalar_one()
                )
                entry: dict[str, Any] = {}
                try:
                    out = await ras.freeze_and_persist_request(scope, **kwargs)
                    entry["accepted"] = True
                    entry["returned_request"] = str(out.request.id)
                except IdempotencyConflictError as exc:
                    entry["accepted"] = False
                    entry["error_type"] = type(exc).__name__
                    entry["error_code"] = getattr(exc, "error_code", None)
                    entry["text"] = str(exc)
                    entry["leaks_prior_request"] = prior_request_id in str(exc)
                    entry["leaks_prior_operation"] = prior_operation_id in str(exc)
                except Exception as exc:  # noqa: BLE001
                    entry["accepted"] = False
                    entry["error_type"] = type(exc).__name__
                    entry["text"] = str(exc)
                    entry["unexpected"] = True
                after = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count()).select_from(WorkpaperSyncOperation)
                        )
                    ).scalar_one()
                )
                entry["operation_rows_delta"] = after - before
                snap["idempotency"][name] = entry
                await s.rollback()

        try:
            # 另一个 participant 复用同 key
            await _conflict_case("cross_participant", participant_id=part_b_id)
            # 同 participant 但 payload（client_edit_epoch 进 fingerprint）不同
            await _conflict_case("payload_differs", client_edit_epoch=4)
            # 同 participant 但 contributor 集合不同（也进 fingerprint）
            await _conflict_case(
                "contributors_differ", contributor_user_ids=[ids["user_a"], ids["user_b"]]
            )
        except Exception as exc:  # noqa: BLE001
            _phase_failed("idempotency", exc)

        # 跨 kind 直打仓储：`assert_can_initiate_request` 会先拒 close_capture
        # （room policy 判据在前），走服务层时被测的幂等谓词一次都跑不到 —— 假红。
        # 一个场景只违反一个谓词：这里保持 freeze 完全等值，只换 kind。
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                room = (
                    await s.execute(sa.select(WorkpaperOoRoom).where(WorkpaperOoRoom.id == room_id))
                ).scalar_one()
                part_a = await svc._load_participant(part_a_id, room_id=room_id)
                conf = await svc.assert_can_initiate_request(
                    room_id=room_id, participant_id=part_a_id
                )
                freeze = await svc.build_request_freeze(
                    room=conf[0], participant=conf[1], confirmation=conf[2],
                    client_edit_epoch=3, contributor_user_ids=[ids["user_a"]],
                )
                kwargs = dict(freeze.as_repository_kwargs(scope=scope))
                kwargs["kind"] = RequestKind.close_capture
                entry: dict[str, Any] = {}
                try:
                    await repo.create_forcesave_request_with_shell(
                        **kwargs, idempotency_key="accepted-1", created_by=ids["user_a"]
                    )
                    entry["accepted"] = True
                except IdempotencyConflictError as exc:
                    entry["accepted"] = False
                    entry["error_type"] = type(exc).__name__
                    entry["text"] = str(exc)
                    entry["leaks_prior_request"] = prior_request_id in str(exc)
                    entry["leaks_prior_operation"] = prior_operation_id in str(exc)
                    entry["operation_rows_delta"] = 0
                snap["idempotency"]["cross_kind"] = entry
                _ = part_a
                await s.rollback()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("idempotency_cross_kind", exc)

        # ═══ 阶段 3：fingerprint 逐字段参与（AC 4.1「全部冻结字段等值」）═══
        try:
            base_kwargs = {
                "client_confirmation_id": conf_a_id,
                "client_base_version_id": cv_id,
                "client_base_representation_id": rep_id,
                "client_base_projection_sha256": projection_sha,
                "definition_bundle_sha256": _d("bundle-canonical-g1"),
                "authority_model_definition_sha256": _d("authority-def-g1"),
                "adapter_build_digest": adapter_build,
                "contributor_snapshot_digest": _d("contrib-baseline"),
                "client_edit_epoch": 3,
                "write_fence_epoch": 1,
                "initiator_permission_epoch": 5,
            }
            baseline_fp = compute_frozen_request_fingerprint(**base_kwargs)
            perturb: dict[str, Any] = {
                "client_confirmation_id": uuid.uuid4(),
                "client_base_version_id": uuid.uuid4(),
                "client_base_representation_id": uuid.uuid4(),
                "client_base_projection_sha256": _d("other-projection"),
                "definition_bundle_sha256": _d("other-bundle"),
                "authority_model_definition_sha256": _d("other-authority"),
                "adapter_build_digest": _d("other-adapter"),
                "contributor_snapshot_digest": _d("other-contrib"),
                "client_edit_epoch": 4,
                "write_fence_epoch": 2,
                "initiator_permission_epoch": 6,
            }
            fields: dict[str, Any] = {"baseline": baseline_fp, "per_field": {}}
            for field, value in perturb.items():
                kw = dict(base_kwargs)
                kw[field] = value
                fields["per_field"][field] = compute_frozen_request_fingerprint(**kw)
            snap["fingerprint_fields"] = fields
        except Exception as exc:  # noqa: BLE001
            _phase_failed("fingerprint_fields", exc)

        # ═══ 阶段 4：Property 18 —— RACE_N 条独立连接真并发 ═════════════
        try:
            race_ops: list[dict[str, Any]] = []
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                ras = RequestApplicationService(repo)
                for i in range(RACE_N):
                    acc = await ras.freeze_and_persist_request(
                        scope,
                        room_id=room_id,
                        # 交替 participant：证明并发 shell 可来自不同 initiator
                        participant_id=(part_a_id if i % 2 == 0 else part_b_id),
                        idempotency_key=f"race-{i}",
                        client_edit_epoch=10 + i,
                        contributor_user_ids=[ids["user_a"]],
                        created_by=ids["user_a"],
                    )
                    race_ops.append(
                        {
                            "operation_id": acc.operation.id,
                            "request_id": acc.request.id,
                            "request_sequence": acc.request_sequence,
                        }
                    )
                await s.commit()

            expected_key = compute_application_key(
                wp_id=wp_id,
                room_id=room_id,
                generation=1,
                frozen_client_base_version_id=cv_id,
                frozen_client_base_representation_id=rep_id,
                incoming_sha256=incoming_sha,
                definition_bundle_sha256=_d("bundle-canonical-g1"),
                authority_model_definition_sha256=_d("authority-def-g1"),
                adapter_build_digest=adapter_build,
            )

            barrier = asyncio.Barrier(RACE_N)
            results: list[dict[str, Any]] = []

            async def _racer(idx: int, op_id: uuid.UUID) -> None:
                rec: dict[str, Any] = {"idx": idx, "operation_id": str(op_id)}
                async with Session() as rs:
                    try:
                        # ① 打开事务并真的占用一条连接（记录 backend pid）
                        rec["backend_pid"] = int(
                            (await rs.execute(sa.text("SELECT pg_backend_pid()"))).scalar_one()
                        )
                        # ② `t_ready` = 「本任务的事务已打开、连接已占用」的时刻，
                        #    记在 `barrier.wait()` **之前**。
                        #
                        # 🔴 判据必须用 `max(t_ready) <= min(t_call)`，不能用
                        # `max(t_barrier) <= min(t_call)`（首轮那样写，实测偶发红）：
                        # barrier 释放后各任务恢复顺序是任意的，A 记 `t_barrier` 的时刻
                        # 完全可能晚于 B 记 `t_call` ⇒ 那条不等式并不成立，
                        # 是**探针缺陷**而非并发没发生。
                        # 而 `t_ready` 版是 barrier 语义的直接推论：任何 `wait()` 返回都
                        # 发生在最后一个参与者调用 `wait()` 之后，故必晚于所有 `t_ready`。
                        rec["t_ready"] = time.monotonic()
                        await barrier.wait()
                        rec["t_call"] = time.monotonic()
                        rrepo = WorkpaperSyncRepository(rs)
                        rras = RequestApplicationService(rrepo)
                        out = await rras.correlate(
                            operation_id=op_id,
                            incoming_artifact_id=incoming_id,
                            current_revision=1,
                            adapter_id="excel.d2.v1",
                            actor_type=ActorType.callback,
                        )
                        rec["shape"] = out.shape.value
                        rec["created_application"] = out.created_application
                        rec["application_id"] = str(out.application.id)
                        rec["application_key"] = str(out.application.application_key)
                        rec["effective"] = out.effective_request_sequence
                        rec["folded_from"] = out.folded_from_sequence
                        rec["canonical_primary"] = str(out.canonical_primary_operation_id)
                        await rs.commit()
                        rec["committed"] = True
                    except Exception as exc:  # noqa: BLE001 - 每条 racer 独立记录
                        await rs.rollback()
                        rec["committed"] = False
                        rec["error"] = _err(exc)
                        rec["blame"] = _blame(exc)
                    finally:
                        rec["t_done"] = time.monotonic()
                results.append(rec)

            await asyncio.gather(
                *(
                    _racer(i, race_ops[i]["operation_id"])
                    for i in range(RACE_N)
                )
            )

            op_ids = [o["operation_id"] for o in race_ops]
            async with Session() as s:
                apps = list(
                    (
                        await s.execute(
                            sa.select(
                                WorkpaperContentApplication.id,
                                WorkpaperContentApplication.application_key,
                                WorkpaperContentApplication.origin_request_id,
                                WorkpaperContentApplication.origin_request_sequence,
                                WorkpaperContentApplication.effective_request_sequence,
                                WorkpaperContentApplication.incoming_sha256,
                                WorkpaperContentApplication.superseded_by_application_id,
                            )
                        )
                    ).all()
                )
                ops = list(
                    (
                        await s.execute(
                            sa.select(
                                WorkpaperSyncOperation.id,
                                WorkpaperSyncOperation.application_id,
                                WorkpaperSyncOperation.duplicate_of_operation_id,
                                WorkpaperSyncOperation.state,
                                WorkpaperSyncOperation.forcesave_request_id,
                            ).where(WorkpaperSyncOperation.id.in_(op_ids))
                        )
                    ).all()
                )
                # 链：duplicate 指向的目标自身也是 duplicate
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
                # 环：任意长度（递归闭包里出现自身）
                cyclic = int(
                    (
                        await s.execute(
                            sa.text(
                                "WITH RECURSIVE walk(root, node, depth) AS ("
                                "  SELECT id, duplicate_of_operation_id, 1"
                                "    FROM working_paper_sync_operation"
                                "   WHERE duplicate_of_operation_id IS NOT NULL"
                                "  UNION ALL"
                                "  SELECT w.root, o.duplicate_of_operation_id, w.depth + 1"
                                "    FROM walk w"
                                "    JOIN working_paper_sync_operation o ON o.id = w.node"
                                "   WHERE o.duplicate_of_operation_id IS NOT NULL"
                                "     AND w.depth < 16"
                                ") SELECT count(*) FROM walk WHERE node = root"
                            )
                        )
                    ).scalar_one()
                )
                stranded = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperSyncOperation)
                            .where(
                                WorkpaperSyncOperation.id.in_(op_ids),
                                WorkpaperSyncOperation.application_id.is_(None),
                                WorkpaperSyncOperation.duplicate_of_operation_id.is_(None),
                            )
                        )
                    ).scalar_one()
                )
                waiting = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperSyncOperation)
                            .where(WorkpaperSyncOperation.state == "waiting_application")
                        )
                    ).scalar_one()
                )
                bound_events = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperSyncOperationEvent)
                            .where(
                                WorkpaperSyncOperationEvent.operation_id.in_(op_ids),
                                WorkpaperSyncOperationEvent.to_state == "application_bound",
                            )
                        )
                    ).scalar_one()
                )
                dup_events = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperSyncOperationEvent)
                            .where(
                                WorkpaperSyncOperationEvent.operation_id.in_(op_ids),
                                WorkpaperSyncOperationEvent.to_state == "duplicate",
                            )
                        )
                    ).scalar_one()
                )
                fold_events = list(
                    (
                        await s.execute(
                            sa.select(
                                WorkpaperContentApplicationEvent.folded_request_id,
                                WorkpaperContentApplicationEvent.effective_request_sequence,
                                WorkpaperContentApplicationEvent.room_latest_durable_sequence,
                            ).where(
                                WorkpaperContentApplicationEvent.event_type
                                == ApplicationEventType.sequence_folded.value
                            )
                        )
                    ).all()
                )
                room_row = (
                    await s.execute(
                        sa.select(
                            WorkpaperOoRoom.latest_durable_application_id,
                            WorkpaperOoRoom.latest_durable_sequence,
                        ).where(WorkpaperOoRoom.id == room_id)
                    )
                ).one()

            primaries = [o for o in ops if o[1] is not None]
            duplicates = [o for o in ops if o[2] is not None]
            snap["race"] = {
                "n": RACE_N,
                "expected_key": expected_key,
                "request_sequences": sorted(o["request_sequence"] for o in race_ops),
                "distinct_backend_pids": len(
                    {r["backend_pid"] for r in results if "backend_pid" in r}
                ),
                "all_committed": all(r.get("committed") for r in results),
                "racer_errors": [r.get("error") for r in results if r.get("error")],
                "created_application_count": sum(
                    1 for r in results if r.get("created_application")
                ),
                "shapes": sorted(r.get("shape", "?") for r in results),
                "max_t_ready": max(
                    (r["t_ready"] for r in results if "t_ready" in r), default=0.0
                ),
                "min_t_call": min((r["t_call"] for r in results if "t_call" in r), default=0.0),
                "ready_count": sum(1 for r in results if "t_ready" in r),
                "application_rows": len(apps),
                "application_keys": sorted({str(a[1]).strip() for a in apps}),
                "application_incoming_sha": sorted({str(a[5]).strip() for a in apps}),
                "primary_count": len(primaries),
                "duplicate_count": len(duplicates),
                "duplicates_all_direct": all(
                    primaries and d[2] == primaries[0][0] for d in duplicates
                ),
                "duplicate_states": sorted({str(d[3]) for d in duplicates}),
                "duplicates_have_no_application": all(d[1] is None for d in duplicates),
                "chained": chained,
                "cyclic": cyclic,
                "stranded": stranded,
                "waiting_application": waiting,
                "application_bound_events": bound_events,
                "duplicate_events": dup_events,
                "fold_event_count": len(fold_events),
                "fold_request_ids_distinct": len({str(f[0]) for f in fold_events})
                == len(fold_events),
                "fold_room_fence_all_set": all(f[2] is not None for f in fold_events),
                "origin_sequence": (int(apps[0][3]) if apps else None),
                "effective_sequence": (int(apps[0][4]) if apps else None),
                "superseded_by": (_opt(apps[0][6]) if apps else None),
                "room_latest_durable_application_id": _opt(room_row[0]),
                "room_latest_durable_sequence": int(room_row[1]),
                "winner_request_sequences": sorted(
                    o["request_sequence"]
                    for o in race_ops
                    if any(
                        r.get("created_application") and r["operation_id"] == str(o["operation_id"])
                        for r in results
                    )
                ),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("race", exc)

        # ═══ 阶段 4b：并发 fold —— 保证 origin **不是** max（AC 5.5 / 10.11）══
        #
        # 🔴 阶段 4 单独跑是不够的，而且首轮实测就踩了：winner 由谁先拿到 room lock
        # 决定，那一轮恰好是 sequence 最高的那个赢 ⇒ `effective == origin == max`
        # 恒成立、**零** fold event ⇒ `GREATEST` fold 与 room fence 同事务推进这条
        # 核心声明一次都没被执行，而断言照样全绿（判据靠调度运气通过）。
        #
        # 这里把 origin 钉死成**最低** sequence（先串行 correlate 它），再让余下
        # RACE_N−1 个更高 sequence 的 shell 真并发涌入。于是必然产生 fold，
        # 且能证明「origin 永不改写」与「effective 收敛到 max」是两件独立的事。
        try:
            fold_incoming = None
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                fold_incoming = await _new_incoming(
                    repo, tag="task23-fold", sha=_d("incoming-bytes-task23-fold")
                )
                await s.commit()

            fold_ops: list[dict[str, Any]] = []
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                ras = RequestApplicationService(repo)
                for i in range(RACE_N):
                    acc = await ras.freeze_and_persist_request(
                        scope,
                        room_id=room_id,
                        participant_id=(part_a_id if i % 2 == 0 else part_b_id),
                        idempotency_key=f"fold-{i}",
                        client_edit_epoch=200 + i,
                        contributor_user_ids=[ids["user_a"]],
                        created_by=ids["user_a"],
                    )
                    fold_ops.append(
                        {
                            "operation_id": acc.operation.id,
                            "request_sequence": acc.request_sequence,
                        }
                    )
                await s.commit()
            fold_ops.sort(key=lambda o: o["request_sequence"])
            seed, rest = fold_ops[0], fold_ops[1:]

            # 串行播种：最低 sequence 成为 origin/primary
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                ras = RequestApplicationService(repo)
                seeded = await ras.correlate(
                    operation_id=seed["operation_id"],
                    incoming_artifact_id=fold_incoming,
                    current_revision=1,
                    adapter_id="excel.d2.v1",
                    actor_type=ActorType.callback,
                )
                seeded_app_id = seeded.application.id
                await s.commit()

            fold_barrier = asyncio.Barrier(len(rest))
            fold_results: list[dict[str, Any]] = []

            async def _folder(idx: int, op_id: uuid.UUID) -> None:
                rec: dict[str, Any] = {"idx": idx}
                async with Session() as rs:
                    try:
                        rec["backend_pid"] = int(
                            (await rs.execute(sa.text("SELECT pg_backend_pid()"))).scalar_one()
                        )
                        await fold_barrier.wait()
                        rec["t_call"] = time.monotonic()
                        rras = RequestApplicationService(WorkpaperSyncRepository(rs))
                        out = await rras.correlate(
                            operation_id=op_id,
                            incoming_artifact_id=fold_incoming,
                            current_revision=1,
                            adapter_id="excel.d2.v1",
                            actor_type=ActorType.callback,
                        )
                        rec["shape"] = out.shape.value
                        rec["created_application"] = out.created_application
                        rec["folded_from"] = out.folded_from_sequence
                        rec["effective"] = out.effective_request_sequence
                        await rs.commit()
                        rec["committed"] = True
                    except Exception as exc:  # noqa: BLE001
                        await rs.rollback()
                        rec["committed"] = False
                        rec["error"] = _err(exc)
                    fold_results.append(rec)

            await asyncio.gather(
                *(_folder(i, o["operation_id"]) for i, o in enumerate(rest))
            )

            async with Session() as s:
                app_row = (
                    await s.execute(
                        sa.select(
                            WorkpaperContentApplication.origin_request_sequence,
                            WorkpaperContentApplication.effective_request_sequence,
                            WorkpaperContentApplication.superseded_by_application_id,
                        ).where(WorkpaperContentApplication.id == seeded_app_id)
                    )
                ).one()
                fold_evs = list(
                    (
                        await s.execute(
                            sa.select(
                                WorkpaperContentApplicationEvent.folded_request_id,
                                WorkpaperContentApplicationEvent.effective_request_sequence,
                                WorkpaperContentApplicationEvent.room_latest_durable_sequence,
                                WorkpaperContentApplicationEvent.origin_request_sequence,
                            )
                            .where(
                                WorkpaperContentApplicationEvent.application_id == seeded_app_id,
                                WorkpaperContentApplicationEvent.event_type
                                == ApplicationEventType.sequence_folded.value,
                            )
                            # 🔴 必须 ORDER BY：不排序时行序由 PG 自由决定，
                            # 「timeline 里 effective 单调上升」这条断言会随机红/绿。
                            # 首轮漏了 ORDER BY，采集到 monotonic=false（探针缺陷，
                            # 不是生产缺陷）。
                            .order_by(WorkpaperContentApplicationEvent.sequence_no)
                        )
                    ).all()
                )
                room_row = (
                    await s.execute(
                        sa.select(
                            WorkpaperOoRoom.latest_durable_application_id,
                            WorkpaperOoRoom.latest_durable_sequence,
                        ).where(WorkpaperOoRoom.id == room_id)
                    )
                ).one()
                primaries = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperSyncOperation)
                            .where(WorkpaperSyncOperation.application_id == seeded_app_id)
                        )
                    ).scalar_one()
                )
                dups = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperSyncOperation)
                            .where(
                                WorkpaperSyncOperation.id.in_(
                                    [o["operation_id"] for o in rest]
                                ),
                                WorkpaperSyncOperation.state == "duplicate",
                            )
                        )
                    ).scalar_one()
                )
            snap["fold_race"] = {
                "n_racers": len(rest),
                "distinct_backend_pids": len(
                    {r["backend_pid"] for r in fold_results if "backend_pid" in r}
                ),
                "all_committed": all(r.get("committed") for r in fold_results),
                "errors": [r.get("error") for r in fold_results if r.get("error")],
                "created_application_count": sum(
                    1 for r in fold_results if r.get("created_application")
                ),
                "seed_sequence": seed["request_sequence"],
                "max_sequence": max(o["request_sequence"] for o in fold_ops),
                "origin_sequence": int(app_row[0]),
                "effective_sequence": int(app_row[1]),
                "superseded_by": _opt(app_row[2]),
                "fold_event_count": len(fold_evs),
                "fold_request_ids_distinct": len({str(f[0]) for f in fold_evs})
                == len(fold_evs),
                "fold_room_fence_all_set": all(f[2] is not None for f in fold_evs),
                "fold_origin_never_rewritten": sorted({int(f[3]) for f in fold_evs}),
                "fold_effective_monotonic": [int(f[1]) for f in fold_evs]
                == sorted(int(f[1]) for f in fold_evs),
                "room_latest_durable_application_id": _opt(room_row[0]),
                "room_latest_durable_sequence": int(room_row[1]),
                "primary_count": primaries,
                "duplicate_count": dups,
                "shapes": sorted(r.get("shape", "?") for r in fold_results),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("fold_race", exc)

        app_id_for_probes = snap.get("race", {}).get("room_latest_durable_application_id")
        primary_op_id: str | None = None
        dup_op_id: str | None = None
        if app_id_for_probes:
            async with Session() as s:
                primary_op_id = _opt(
                    (
                        await s.execute(
                            sa.select(WorkpaperSyncOperation.id).where(
                                WorkpaperSyncOperation.application_id
                                == uuid.UUID(app_id_for_probes)
                            )
                        )
                    ).scalar_one_or_none()
                )
                dup_op_id = _opt(
                    (
                        await s.execute(
                            sa.select(WorkpaperSyncOperation.id)
                            .where(WorkpaperSyncOperation.state == "duplicate")
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                )

        # ═══ 阶段 5：sequence fold / supersede 的 DB 约束逐条归因 ═════════
        async def _forbidden(name: str, sql: str, *, expect: str, params: dict | None = None) -> None:
            async with Session() as s:
                entry: dict[str, Any] = {"expect": expect}
                try:
                    await s.execute(sa.text(sql), params or {})
                    await s.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
                    await s.flush()
                    entry["accepted"] = True
                except Exception as exc:  # noqa: BLE001
                    entry["accepted"] = False
                    entry.update(_blame(exc))
                finally:
                    await s.rollback()
                snap["constraints"][name] = entry

        if app_id_for_probes and primary_op_id and dup_op_id:
            try:
                A = app_id_for_probes
                # ── `origin_request_sequence` 的执法点是 identity trigger，不是 mutation ──
                #
                # 同 timing 的 trigger 按名字排序触发：`trg_wpca_identity` <
                # `trg_wpca_mutation`。前者会把 `origin_request_sequence` 与 origin
                # request 行的 `request_sequence` **跨行**重新比对 ⇒ 它先抛。
                # 首轮把本条声明成 mutation trigger，实测归因不符（fragment 不匹配）。
                # 这不是「归因写宽一点」的问题：identity trigger 给的保证更强
                # （不仅不可改，还必须等于那条 request 的真实 sequence），
                # 而 mutation trigger 的 identity-列 分支要另找一个 identity trigger
                # 不交叉校验的列才能单独证明 —— 就是下面的 `application_key_immutable`。
                await _forbidden(
                    "origin_sequence_immutable",
                    "UPDATE working_paper_content_application "
                    "SET origin_request_sequence = origin_request_sequence + 1 "
                    "WHERE id = CAST(:a AS uuid)",
                    expect="wpsync_check_application_identity",
                    params={"a": A},
                )
                await _forbidden(
                    "application_key_immutable",
                    "UPDATE working_paper_content_application "
                    "SET application_key = :k WHERE id = CAST(:a AS uuid)",
                    expect="wpsync_check_application_mutation",
                    params={"a": A, "k": _d("rewritten-application-key")},
                )
                await _forbidden(
                    "effective_sequence_monotonic",
                    "UPDATE working_paper_content_application "
                    "SET effective_request_sequence = effective_request_sequence - 1 "
                    "WHERE id = CAST(:a AS uuid)",
                    expect="wpsync_check_application_mutation",
                    params={"a": A},
                )
                # ── `ck_wpca_effective_ge_origin` 必须走 INSERT，不能走 UPDATE ──
                #
                # UPDATE 路径上它被 BEFORE UPDATE 的 `wpsync_check_application_mutation`
                # 完全遮蔽：任何把 effective 降到 origin 以下的 UPDATE，同时也是一次
                # 「effective 下降」⇒ trigger 先抛。首轮实测归因就落在 trigger 上，
                # 而那会让本条声明的 CHECK 看起来「还活着」却从未被证明过。
                # INSERT 路径上 BEFORE INSERT 的 identity trigger 不看 effective，
                # 于是这一行**只**违反本 CHECK。
                await _forbidden(
                    "effective_below_origin",
                    "INSERT INTO working_paper_content_application "
                    "(id, project_id, wp_id, entry_id, room_id, generation, origin_request_id, "
                    " application_key, client_edit_epoch, origin_request_sequence, "
                    " effective_request_sequence, base_version_id, base_representation_id, "
                    " current_revision, incoming_artifact_id, incoming_sha256, "
                    " definition_bundle_id, definition_bundle_sha256, "
                    " authority_model_definition_id, authority_model_definition_sha256, "
                    " adapter_id, adapter_build_digest, contributor_snapshot_digest, state) "
                    "SELECT gen_random_uuid(), project_id, wp_id, entry_id, room_id, generation, "
                    "       origin_request_id, :k, client_edit_epoch, "
                    "       origin_request_sequence, origin_request_sequence - 1, "
                    "       base_version_id, base_representation_id, current_revision, "
                    "       incoming_artifact_id, incoming_sha256, definition_bundle_id, "
                    "       definition_bundle_sha256, authority_model_definition_id, "
                    "       authority_model_definition_sha256, adapter_id, adapter_build_digest, "
                    "       contributor_snapshot_digest, state "
                    "  FROM working_paper_content_application WHERE id = CAST(:a AS uuid)",
                    expect="ck_wpca_effective_ge_origin",
                    params={"a": A, "k": _d("effective-below-origin-probe")},
                )
                await _forbidden(
                    "self_supersede",
                    "UPDATE working_paper_content_application "
                    "SET superseded_by_application_id = id WHERE id = CAST(:a AS uuid)",
                    expect="ck_wpca_no_self_supersede",
                    params={"a": A},
                )
                # ── 「一个 application 只能有一个 primary」也必须走 INSERT ──
                #
                # 把既有 duplicate 改绑成 primary 的 UPDATE 会先撞
                # `wpsync_check_operation_binding_immutable`（duplicate 指针不可变），
                # 于是 `uq_wpso_application` 从未被证明。新插一行 shape 合法的 primary
                # （dup=NULL、state=application_bound、bound_at 非空、scope 全同）
                # 只违反唯一约束这一条。
                await _forbidden(
                    "second_primary_for_application",
                    "INSERT INTO working_paper_sync_operation "
                    "(id, project_id, wp_id, entry_id, room_id, application_id, "
                    " application_bound_at, direction, state, definition_bundle_id, "
                    " definition_bundle_sha256, authority_model_definition_id, "
                    " authority_model_definition_sha256) "
                    "SELECT gen_random_uuid(), project_id, wp_id, entry_id, room_id, "
                    "       application_id, now(), direction, 'application_bound', "
                    "       definition_bundle_id, definition_bundle_sha256, "
                    "       authority_model_definition_id, authority_model_definition_sha256 "
                    "  FROM working_paper_sync_operation WHERE id = CAST(:p AS uuid)",
                    expect="uq_wpso_application",
                    params={"p": primary_op_id},
                )
                await _forbidden(
                    "duplicate_pointer_removed",
                    "UPDATE working_paper_sync_operation "
                    "SET duplicate_of_operation_id = NULL WHERE id = CAST(:d AS uuid)",
                    expect="wpsync_check_operation_binding_immutable",
                    params={"d": dup_op_id},
                )
                await _forbidden(
                    "primary_rebound",
                    "UPDATE working_paper_sync_operation "
                    "SET application_id = gen_random_uuid() WHERE id = CAST(:p AS uuid)",
                    expect="wpsync_check_operation_binding_immutable",
                    params={"p": primary_op_id},
                )
                # ── 链：新插一行**行级 CHECK 全合法**的 duplicate，只是目标是 duplicate ──
                #
                # 首轮把 primary 改成指向 duplicate，结果撞 `ck_wpso_duplicate_shape`
                # （primary 的 application_id 非空 ⇒ duplicate 分支不成立）——
                # 被测的 DEFERRED trigger 一次都没跑到（假红/WRONG-TEST）。
                await _forbidden(
                    "duplicate_chain",
                    "INSERT INTO working_paper_sync_operation "
                    "(id, project_id, wp_id, entry_id, room_id, duplicate_of_operation_id, "
                    " direction, state, definition_bundle_id, definition_bundle_sha256, "
                    " authority_model_definition_id, authority_model_definition_sha256) "
                    "SELECT gen_random_uuid(), project_id, wp_id, entry_id, room_id, "
                    "       CAST(:d AS uuid), direction, 'duplicate', definition_bundle_id, "
                    "       definition_bundle_sha256, authority_model_definition_id, "
                    "       authority_model_definition_sha256 "
                    "  FROM working_paper_sync_operation WHERE id = CAST(:d AS uuid)",
                    expect="wpsync_check_operation_duplicate_link",
                    params={"d": dup_op_id},
                )
                await _forbidden(
                    "stranded_duplicate_state",
                    "INSERT INTO working_paper_sync_operation "
                    "(id, project_id, wp_id, entry_id, room_id, direction, state, "
                    " definition_bundle_id, definition_bundle_sha256, "
                    " authority_model_definition_id, authority_model_definition_sha256) "
                    "SELECT gen_random_uuid(), project_id, wp_id, entry_id, room_id, "
                    "       direction, 'duplicate', definition_bundle_id, "
                    "       definition_bundle_sha256, authority_model_definition_id, "
                    "       authority_model_definition_sha256 "
                    "  FROM working_paper_sync_operation WHERE id = CAST(:p AS uuid)",
                    expect="ck_wpso_duplicate_shape",
                    params={"p": primary_op_id},
                )
                await _forbidden(
                    "fold_event_twice_same_request",
                    "INSERT INTO working_paper_content_application_event "
                    "(application_id, sequence_no, event_type, folded_request_id, "
                    " origin_request_sequence, effective_request_sequence, "
                    " room_latest_durable_sequence, actor_type) "
                    "SELECT application_id, 999, 'sequence_folded', folded_request_id, "
                    "       origin_request_sequence, effective_request_sequence, "
                    "       room_latest_durable_sequence, actor_type "
                    "  FROM working_paper_content_application_event "
                    " WHERE event_type = 'sequence_folded' LIMIT 1",
                    expect="uq_wpcae_fold_once",
                )
                await _forbidden(
                    "fold_event_without_room_fence",
                    "INSERT INTO working_paper_content_application_event "
                    "(application_id, sequence_no, event_type, folded_request_id, "
                    " origin_request_sequence, effective_request_sequence, actor_type) "
                    "VALUES (CAST(:a AS uuid), 998, 'sequence_folded', gen_random_uuid(), "
                    "        1, 1, 'system')",
                    expect="ck_wpcae_fold_requires_room_fence",
                    params={"a": A},
                )
                await _forbidden(
                    "second_application_bound_event",
                    "INSERT INTO working_paper_sync_operation_event "
                    "(operation_id, sequence_no, to_state, stage, actor_type) "
                    "VALUES (CAST(:p AS uuid), 997, 'application_bound', 'replay', 'system')",
                    expect="uq_wpsoe_application_bound_once",
                    params={"p": primary_op_id},
                )
                await _forbidden(
                    "duplicate_application_key",
                    "INSERT INTO working_paper_content_application "
                    "(id, project_id, wp_id, entry_id, room_id, generation, origin_request_id, "
                    " application_key, client_edit_epoch, origin_request_sequence, "
                    " effective_request_sequence, base_version_id, base_representation_id, "
                    " current_revision, incoming_artifact_id, incoming_sha256, "
                    " definition_bundle_id, definition_bundle_sha256, "
                    " authority_model_definition_id, authority_model_definition_sha256, "
                    " adapter_id, adapter_build_digest, contributor_snapshot_digest, state) "
                    "SELECT gen_random_uuid(), project_id, wp_id, entry_id, room_id, generation, "
                    "       origin_request_id, application_key, client_edit_epoch, "
                    "       origin_request_sequence, effective_request_sequence, base_version_id, "
                    "       base_representation_id, current_revision, incoming_artifact_id, "
                    "       incoming_sha256, definition_bundle_id, definition_bundle_sha256, "
                    "       authority_model_definition_id, authority_model_definition_sha256, "
                    "       adapter_id, adapter_build_digest, contributor_snapshot_digest, state "
                    "  FROM working_paper_content_application WHERE id = CAST(:a AS uuid)",
                    expect="working_paper_content_application_application_key_key",
                    params={"a": A},
                )
            except Exception as exc:  # noqa: BLE001
                _phase_failed("constraints", exc)

            # ── 被遮蔽约束的纵深证明 ────────────────────────────────────
            #
            # `ck_wpso_not_both_owners`（app 与 duplicate 指针互斥）在默认 schema 里
            # **永远无法单独触发**：任何 `app IS NOT NULL AND dup IS NOT NULL` 的行同时
            # 让 `ck_wpso_duplicate_shape` 的两个 disjunct 都失败 ⇒ 后者必然同时被违反。
            # 只断言「被拒了」会把归因写成任意一条，下一个人据此以为自己声明的那条活着。
            #
            # 处理方式不是编个归因，而是**在事务里临时 DROP 遮蔽者**（PG 的 DDL 是事务性的，
            # ROLLBACK 后 schema 原样），再看剩下那条是否真的接管。这既承认了遮蔽关系，
            # 又证明纵深防御不是死代码。
            try:
                async with Session() as s:
                    entry: dict[str, Any] = {}
                    await s.execute(
                        sa.text(
                            "ALTER TABLE working_paper_sync_operation "
                            "DROP CONSTRAINT ck_wpso_duplicate_shape"
                        )
                    )
                    try:
                        await s.execute(
                            sa.text(
                                "UPDATE working_paper_sync_operation "
                                "SET application_id = CAST(:a AS uuid), "
                                "    application_bound_at = now() "
                                "WHERE id = CAST(:d AS uuid)"
                            ),
                            {"a": app_id_for_probes, "d": dup_op_id},
                        )
                        await s.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
                        await s.flush()
                        entry["accepted"] = True
                    except Exception as exc:  # noqa: BLE001
                        entry["accepted"] = False
                        entry.update(_blame(exc))
                    await s.rollback()
                    snap["subsumption"]["not_both_owners_after_dropping_shape"] = entry
                # ROLLBACK 之后遮蔽者必须还在（证明探针没有污染 schema）
                async with Session() as s:
                    still = int(
                        (
                            await s.execute(
                                sa.text(
                                    "SELECT count(*) FROM pg_constraint "
                                    "WHERE conname = 'ck_wpso_duplicate_shape' "
                                    "  AND conrelid = 'working_paper_sync_operation'::regclass"
                                )
                            )
                        ).scalar_one()
                    )
                    snap["subsumption"]["shape_constraint_restored"] = still

                # ── 服务层「canonical primary 必须**唯一**绑定」也被 DB 遮蔽 ──
                #
                # `uq_wpso_application` 让「一个 application 被 2 个 operation 绑定」
                # 在库里根本无法存在 ⇒ `canonicalize_authorized` 里的 `bound != 1`
                # 分支是**不可达**的。不可达分支正是本 spec 反复付过代价的假绿源：
                # 「守卫锁住了它」只是自述。同样用事务内 DROP 把它变成可证的：
                # 去掉唯一约束、插入第二个 primary、再读 —— 服务层必须拒。
                async with Session() as s:
                    repo = WorkpaperSyncRepository(s)
                    ras = RequestApplicationService(repo)
                    entry2: dict[str, Any] = {}
                    await s.execute(
                        sa.text(
                            "ALTER TABLE working_paper_sync_operation "
                            "DROP CONSTRAINT uq_wpso_application"
                        )
                    )
                    await s.execute(
                        sa.text(
                            "INSERT INTO working_paper_sync_operation "
                            "(id, project_id, wp_id, entry_id, room_id, application_id, "
                            " application_bound_at, direction, state, definition_bundle_id, "
                            " definition_bundle_sha256, authority_model_definition_id, "
                            " authority_model_definition_sha256) "
                            "SELECT gen_random_uuid(), project_id, wp_id, entry_id, room_id, "
                            "       application_id, now(), direction, 'application_bound', "
                            "       definition_bundle_id, definition_bundle_sha256, "
                            "       authority_model_definition_id, "
                            "       authority_model_definition_sha256 "
                            "  FROM working_paper_sync_operation WHERE id = CAST(:p AS uuid)"
                        ),
                        {"p": primary_op_id},
                    )
                    try:
                        await ras.read_operation(
                            operation_id=uuid.UUID(primary_op_id),
                            declared_project_id=project_id,
                            declared_wp_id=wp_id,
                            declared_entry_id=ENTRY,
                            action="get",
                        )
                        entry2["accepted"] = True
                    except CanonicalBindingError as exc:
                        entry2["accepted"] = False
                        entry2["error_type"] = type(exc).__name__
                        entry2["text"] = str(exc)
                    except Exception as exc:  # noqa: BLE001
                        entry2["accepted"] = False
                        entry2["error_type"] = f"unexpected:{type(exc).__name__}"
                        entry2["text"] = str(exc)
                    await s.rollback()
                    snap["subsumption"]["service_rejects_double_bound_primary"] = entry2
                async with Session() as s:
                    snap["subsumption"]["unique_constraint_restored"] = int(
                        (
                            await s.execute(
                                sa.text(
                                    "SELECT count(*) FROM pg_constraint "
                                    "WHERE conname = 'uq_wpso_application' "
                                    "  AND conrelid = 'working_paper_sync_operation'::regclass"
                                )
                            )
                        ).scalar_one()
                    )
            except Exception as exc:  # noqa: BLE001
                _phase_failed("subsumption", exc)

            # self-supersede 的服务层拒绝（DB CHECK 之外的第二道）
            try:
                async with Session() as s:
                    repo = WorkpaperSyncRepository(s)
                    entry = {}
                    try:
                        await repo.supersede_application(
                            old_application_id=uuid.UUID(app_id_for_probes),
                            new_application_id=uuid.UUID(app_id_for_probes),
                        )
                        entry["accepted"] = True
                    except SupersedeError as exc:
                        entry["accepted"] = False
                        entry["error_type"] = type(exc).__name__
                        entry["text"] = str(exc)
                    await s.rollback()
                    snap["constraints"]["service_self_supersede"] = entry
            except Exception as exc:  # noqa: BLE001
                _phase_failed("service_self_supersede", exc)

        # ═══ 阶段 6：application_key 只存在于 application（P64）══════════
        try:
            async with Session() as s:
                cols = list(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT table_name, column_name FROM information_schema.columns "
                                "WHERE table_schema = :sch AND column_name = 'application_key' "
                                "ORDER BY table_name"
                            ),
                            {"sch": schema},
                        )
                    ).all()
                )
                uniq = list(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT c.conname, c.contype FROM pg_constraint c "
                                "WHERE c.conrelid = 'working_paper_content_application'::regclass "
                                "  AND c.contype IN ('u','p') "
                                "  AND EXISTS (SELECT 1 FROM unnest(c.conkey) k "
                                "   JOIN pg_attribute a ON a.attrelid = c.conrelid "
                                "    AND a.attnum = k WHERE a.attname = 'application_key')"
                            )
                        )
                    ).all()
                )
            snap["key_ownership"] = {
                "tables_with_application_key": [str(r[0]) for r in cols],
                "unique_constraints_on_key": sorted(str(r[0]) for r in uniq),
                "orm_operation_has_key": "application_key"
                in WorkpaperSyncOperation.__table__.columns.keys(),
                "orm_operation_event_has_key": "application_key"
                in WorkpaperSyncOperationEvent.__table__.columns.keys(),
                "orm_application_has_key": "application_key"
                in WorkpaperContentApplication.__table__.columns.keys(),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("key_ownership", exc)

        # ═══ 阶段 7：读路径固定四步（AC 5.5 末段 / 8.5 / 10.5）═══════════
        if primary_op_id and dup_op_id:
            try:
                async with Session() as s:
                    repo = WorkpaperSyncRepository(s)
                    ras = RequestApplicationService(repo)
                    before_ops = int(
                        (
                            await s.execute(
                                sa.select(sa.func.count()).select_from(WorkpaperSyncOperation)
                            )
                        ).scalar_one()
                    )
                    before_apps = int(
                        (
                            await s.execute(
                                sa.select(sa.func.count()).select_from(
                                    WorkpaperContentApplication
                                )
                            )
                        ).scalar_one()
                    )
                    read_primary = await ras.read_operation(
                        operation_id=uuid.UUID(primary_op_id),
                        declared_project_id=project_id,
                        declared_wp_id=wp_id,
                        declared_entry_id=ENTRY,
                        action="get",
                    )
                    read_dup = await ras.read_operation(
                        operation_id=uuid.UUID(dup_op_id),
                        declared_project_id=project_id,
                        declared_wp_id=wp_id,
                        declared_entry_id=ENTRY,
                        action="retry",
                    )
                    after_ops = int(
                        (
                            await s.execute(
                                sa.select(sa.func.count()).select_from(WorkpaperSyncOperation)
                            )
                        ).scalar_one()
                    )
                    after_apps = int(
                        (
                            await s.execute(
                                sa.select(sa.func.count()).select_from(
                                    WorkpaperContentApplication
                                )
                            )
                        ).scalar_one()
                    )
                    entry = {
                        "primary_stages": [st.value for st in read_primary.stages],
                        "primary_canonical_is_requested": (
                            read_primary.canonical_operation.id
                            == read_primary.requested_operation.id
                        ),
                        "primary_shape": read_primary.requested_shape.value,
                        "dup_stages": [st.value for st in read_dup.stages],
                        "dup_shape": read_dup.requested_shape.value,
                        "dup_requested_application": _opt(
                            read_dup.requested_operation.application_id
                        ),
                        "dup_canonical_application": _opt(read_dup.canonical_application_id),
                        "dup_canonical_is_primary": read_dup.canonical_is_primary,
                        "dup_followed": read_dup.followed_duplicate,
                        "dup_effective_sequence": read_dup.effective_request_sequence,
                        "operation_rows_delta": after_ops - before_ops,
                        "application_rows_delta": after_apps - before_apps,
                    }

                    # 跨 scope 声明 ⇒ 与「不存在」同一 404 语义
                    for label, kwargs in (
                        (
                            "cross_scope_project",
                            {"declared_project_id": uuid.uuid4()},
                        ),
                        ("cross_scope_entry", {"declared_entry_id": "xlsx/other-entry"}),
                    ):
                        base = {
                            "operation_id": uuid.UUID(primary_op_id),
                            "declared_project_id": project_id,
                            "declared_wp_id": wp_id,
                            "declared_entry_id": ENTRY,
                            "action": "get",
                        }
                        base.update(kwargs)
                        try:
                            await ras.read_operation(**base)
                            entry[label] = "accepted"
                        except OperationScopeNotVisibleError as exc:
                            entry[label] = type(exc).__name__
                            entry[f"{label}_code"] = getattr(exc, "error_code", None)
                        except Exception as exc:  # noqa: BLE001
                            entry[label] = f"unexpected:{type(exc).__name__}"
                    try:
                        await ras.read_operation(
                            operation_id=uuid.uuid4(),
                            declared_project_id=project_id,
                            declared_wp_id=wp_id,
                            declared_entry_id=ENTRY,
                            action="get",
                        )
                        entry["unknown_id"] = "accepted"
                    except OperationScopeNotVisibleError as exc:
                        entry["unknown_id"] = type(exc).__name__
                        entry["unknown_id_code"] = getattr(exc, "error_code", None)

                    # authorize 拒绝 ⇒ 403，且**与业务行是否存在无关**。
                    #
                    # 🔴 这条是「authorization-first 真的在第一步」的行为判据：探针给一个
                    # 只在 scope index 里登记、**没有 operation 行**的 id。若实现先加载
                    # 业务行，这里必然报 404/NoResultFound；只有授权真的在业务行之前，
                    # 才会得到 403。
                    ghost = uuid.uuid4()
                    await repo.register_scope(
                        resource_kind=ScopeResourceKind.sync_operation,
                        resource_id=str(ghost),
                        project_id=project_id,
                        wp_id=wp_id,
                        entry_id=ENTRY,
                        room_id=room_id,
                        generation=1,
                    )
                    try:
                        await ras.read_operation(
                            operation_id=ghost,
                            declared_project_id=project_id,
                            declared_wp_id=wp_id,
                            declared_entry_id=ENTRY,
                            action="resolve",
                            authorize=lambda ref: False,
                        )
                        entry["denied_ghost"] = "accepted"
                    except ScopeAuthorizationDeniedError as exc:
                        entry["denied_ghost"] = type(exc).__name__
                        entry["denied_ghost_code"] = getattr(exc, "error_code", None)
                    except Exception as exc:  # noqa: BLE001
                        entry["denied_ghost"] = f"unexpected:{type(exc).__name__}"
                    # 同一个 ghost，授权通过 ⇒ 才轮到「业务行不存在」
                    try:
                        await ras.read_operation(
                            operation_id=ghost,
                            declared_project_id=project_id,
                            declared_wp_id=wp_id,
                            declared_entry_id=ENTRY,
                            action="resolve",
                            authorize=lambda ref: True,
                        )
                        entry["allowed_ghost"] = "accepted"
                    except OperationScopeNotVisibleError as exc:
                        entry["allowed_ghost"] = type(exc).__name__
                    except Exception as exc:  # noqa: BLE001
                        entry["allowed_ghost"] = f"unexpected:{type(exc).__name__}"

                    # pre-correlation shell + require_application ⇒ 必须拒
                    # （canonical primary 未绑定 application 时不得当成可读终态）
                    pre_acc = await ras.freeze_and_persist_request(
                        scope,
                        room_id=room_id,
                        participant_id=part_a_id,
                        idempotency_key="read-pre-correlation",
                        client_edit_epoch=77,
                        contributor_user_ids=[ids["user_a"]],
                        created_by=ids["user_a"],
                    )
                    try:
                        await ras.read_operation(
                            operation_id=pre_acc.operation.id,
                            declared_project_id=project_id,
                            declared_wp_id=wp_id,
                            declared_entry_id=ENTRY,
                            action="get",
                        )
                        entry["pre_correlation_read"] = "accepted"
                    except CanonicalPrimaryUnboundError as exc:
                        entry["pre_correlation_read"] = type(exc).__name__
                        entry["pre_correlation_read_code"] = getattr(exc, "error_code", None)
                    except Exception as exc:  # noqa: BLE001
                        entry["pre_correlation_read"] = f"unexpected:{type(exc).__name__}"
                        entry["pre_correlation_read_code"] = getattr(exc, "error_code", None)
                    # 同一个 pre-correlation shell，`require_application=False` 时可读
                    # （timeline 查询要能看到尚未 correlate 的 shell）
                    lenient = await ras.read_operation(
                        operation_id=pre_acc.operation.id,
                        declared_project_id=project_id,
                        declared_wp_id=wp_id,
                        declared_entry_id=ENTRY,
                        action="timeline",
                        require_application=False,
                    )
                    entry["pre_correlation_lenient_stages"] = [
                        st.value for st in lenient.stages
                    ]
                    entry["pre_correlation_lenient_application"] = _opt(
                        lenient.canonical_application_id
                    )

                    # canonicalize 不接受非 AuthorizedOperationRef
                    try:
                        await ras.canonicalize_authorized(object())  # type: ignore[arg-type]
                        entry["raw_ref"] = "accepted"
                    except ScopeAuthorizationDeniedError as exc:
                        entry["raw_ref"] = type(exc).__name__
                    # 缺 authorized 阶段的 ref 也不行
                    from app.services.workpaper_sync.request_application import (
                        AuthorizedOperationRef,
                    )

                    try:
                        await ras.canonicalize_authorized(
                            AuthorizedOperationRef(
                                operation_id=uuid.UUID(primary_op_id),
                                project_id=project_id,
                                wp_id=wp_id,
                                entry_id=ENTRY,
                                room_id=room_id,
                                generation=1,
                                action="get",
                                stages=(ReadStage.requested_scope_resolved,),
                            )
                        )
                        entry["unauthorized_ref"] = "accepted"
                    except ScopeAuthorizationDeniedError as exc:
                        entry["unauthorized_ref"] = type(exc).__name__

                    snap["read_path"] = entry
                    await s.rollback()
            except Exception as exc:  # noqa: BLE001
                _phase_failed("read_path", exc)

        # ═══ 阶段 8：status 6/2 多 delivery 一 application（P56）═════════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                ras = RequestApplicationService(repo)
                before_apps = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count()).select_from(WorkpaperContentApplication)
                        )
                    ).scalar_one()
                )
                # 🔴 必须用**本阶段自己的** incoming 字节。
                # 首轮复用了 race 阶段那份 incoming（已提交），于是三次 correlation 全部
                # 命中 race 建好的 application ⇒ `application_rows_delta == 0`、
                # shapes 全 duplicate。那实际上测的是「跨阶段去重」，与 P56 想证明的
                # 「同 frozen identity 的 status 6 / status 2 / 重试合成一个 application」
                # 不是同一件事 —— 判据被上一阶段的残留状态遮蔽。
                p56_incoming = await _new_incoming(
                    repo, tag="task23-p56", sha=_d("incoming-bytes-task23-p56")
                )
                shapes: list[str] = []
                for i in range(3):
                    acc = await ras.freeze_and_persist_request(
                        scope,
                        room_id=room_id,
                        participant_id=part_a_id,
                        idempotency_key=f"p56-{i}",
                        client_edit_epoch=40 + i,
                        contributor_user_ids=[ids["user_a"]],
                        created_by=ids["user_a"],
                    )
                    out = await ras.correlate(
                        operation_id=acc.operation.id,
                        incoming_artifact_id=p56_incoming,
                        current_revision=1,
                        adapter_id="excel.d2.v1",
                        actor_type=ActorType.callback,
                    )
                    shapes.append(out.shape.value)
                after_apps = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count()).select_from(WorkpaperContentApplication)
                        )
                    ).scalar_one()
                )
                snap["multi_delivery"] = {
                    "shapes": shapes,
                    "application_rows_delta": after_apps - before_apps,
                    "primaries_for_this_incoming": int(
                        (
                            await s.execute(
                                sa.text(
                                    "SELECT count(*) FROM working_paper_sync_operation o "
                                    "JOIN working_paper_content_application c "
                                    "  ON c.id = o.application_id "
                                    "WHERE c.incoming_artifact_id = CAST(:i AS uuid)"
                                ),
                                {"i": str(p56_incoming)},
                            )
                        ).scalar_one()
                    ),
                }
                await s.rollback()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("multi_delivery", exc)

        # ═══ 阶段 9：recovery claim 前后三实体（AC 4.10 / 5.8 / 14.3）════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                ras = RequestApplicationService(repo)
                inc2_id = await _new_incoming(
                    repo, tag="task23-rec", sha=_d("incoming-recovery-task23")
                )
                case = await repo.create_recovery_case(
                    project_id=project_id,
                    wp_id=wp_id,
                    entry_id=ENTRY,
                    room_id=room_id,
                    generation=1,
                    source_delivery_key=_d("delivery-recovery-task23"),
                    incoming_artifact_id=inc2_id,
                    reason=RecoveryReason.crash_close,
                )
                pre = {
                    "request": _opt(case.recovery_request_id),
                    "application": _opt(case.application_id),
                    "operation": _opt(case.operation_id),
                    "state": str(case.state),
                }
                retry_pre = await ras.retry_eligibility(operation_id=case.operation_id)
                out = await ras.claim_recovery(
                    case_id=case.id,
                    claiming_participant_id=part_a_id,
                    prior_confirmation_id=conf_a_id,
                    idempotency_key="recovery-claim-1",
                    adapter_id="excel.d2.v1",
                    adapter_build_digest=adapter_build,
                    contributor_snapshot_digest=_d("contrib-recovery"),
                    current_revision=1,
                    actor_id=ids["user_a"],
                )
                shape = out.shape
                retry_post = await ras.retry_eligibility(
                    operation_id=out.operation.id
                )
                snap["recovery"] = {
                    "pre_claim": pre,
                    "pre_claim_all_null": all(
                        v is None for k, v in pre.items() if k != "state"
                    ),
                    "retry_eligible_before_claim": retry_pre,
                    "retry_eligible_after_claim": retry_post,
                    "shape": shape.value,
                    "kind": str(out.request.kind),
                    "case_application": _opt(out.case.application_id),
                    "operation_application": _opt(out.operation.application_id),
                    "application_incoming": _opt(out.application.incoming_artifact_id),
                    "case_incoming": _opt(out.case.incoming_artifact_id),
                    "same_application": out.case.application_id == out.application.id,
                    "shape_is_primary": shape is OperationShape.primary,
                }
                await s.rollback()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("recovery", exc)

        # ═══ 阶段 10：refresh_required 拒绝下一 request（P62 / AC 2.9 / 4.11）══
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                rooms_svc = RoomService(repo)
                ras = RequestApplicationService(repo, rooms_svc)
                await rooms_svc.mark_refresh_required(
                    room_id=room_id, reason="merged_projection_differs_from_incoming"
                )
                before = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count()).select_from(WorkpaperSyncOperation)
                        )
                    ).scalar_one()
                )
                entry: dict[str, Any] = {}
                try:
                    await ras.freeze_and_persist_request(
                        scope,
                        room_id=room_id,
                        participant_id=part_a_id,
                        idempotency_key="after-refresh-1",
                        client_edit_epoch=99,
                        contributor_user_ids=[ids["user_a"]],
                        created_by=ids["user_a"],
                    )
                    entry["accepted"] = True
                except RoomNotWritableError as exc:
                    entry["accepted"] = False
                    entry["error_type"] = type(exc).__name__
                    entry["error_code"] = getattr(exc, "error_code", None)
                    entry["mentions_refresh"] = "refresh" in str(exc)
                except Exception as exc:  # noqa: BLE001
                    entry["accepted"] = False
                    entry["error_type"] = f"unexpected:{type(exc).__name__}"
                    entry["text"] = str(exc)
                after = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count()).select_from(WorkpaperSyncOperation)
                        )
                    ).scalar_one()
                )
                entry["operation_rows_delta"] = after - before
                snap["refresh_required"] = entry
                await s.rollback()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("refresh_required", exc)

        # accepted 凭据的 assert_dispatchable 必须真的能拒
        try:
            from app.services.workpaper_sync.request_application import AcceptedRequest

            bad = AcceptedRequest(
                request=None,  # type: ignore[arg-type]
                operation=None,  # type: ignore[arg-type]
                operation_shape=OperationShape.pre_correlation,
                application_count=1,
                cache_hit=False,
                request_sequence=1,
                frozen_request_fingerprint=_d("x"),
            )
            try:
                bad.assert_dispatchable()
                snap["accepted"]["dispatch_guard"] = "accepted"
            except ApplicationPrecreatedError as exc:
                snap["accepted"]["dispatch_guard"] = type(exc).__name__
                snap["accepted"]["dispatch_guard_code"] = getattr(exc, "error_code", None)
        except Exception as exc:  # noqa: BLE001
            _phase_failed("dispatch_guard", exc)

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
# 〇、采集自身健康
# ═══════════════════════════════════════════════════════════════════════════


def test_real_postgres_and_v151_applied(snap: dict[str, Any]) -> None:
    assert "PostgreSQL" in str(snap["server_version"])
    assert snap["apply_errors"] == [], snap["apply_errors"]


def test_no_phase_crashed_during_collection(snap: dict[str, Any]) -> None:
    """采集阶段零异常。

    这条与「异常记录不穿透」是一体两面：不记录时穿透会让 module 变 collection ERROR，
    而 `-rf` 只列 FAILED 不列 ERROR ⇒ 定向变异看不到失败项 ⇒ 判 GREEN。
    """
    assert snap["harness_errors"] == {}, snap["harness_errors"]


# ═══════════════════════════════════════════════════════════════════════════
# 一、accepted 前形态（AC 4.1 / Property 64）
# ═══════════════════════════════════════════════════════════════════════════


def test_accepted_persists_request_and_pre_correlation_shell(snap: dict[str, Any]) -> None:
    acc = snap["accepted"]
    assert acc["shape"] == "pre_correlation"
    assert acc["db_application_id"] is None
    assert acc["db_duplicate_of"] is None
    assert acc["db_request_link"] == acc["request_id"]
    assert acc["db_state"] == "created"
    assert acc["request_state"] == "frozen"
    assert acc["fingerprint_is_digest"] is True


def test_no_application_precreated_before_accepted(snap: dict[str, Any]) -> None:
    """AC 4.1「accepted 前不得预建 application 或 application key」。

    两条一起断言：凭据里的计数是**真查库**得来的（`accepted_application_count`），
    整个 schema 里也确实一行都没有。只断言前者时，「查错了表」也恒 0。
    """
    acc = snap["accepted"]
    assert acc["accepted_application_count"] == 0
    assert acc["application_rows_in_schema"] == 0


def test_identical_frozen_replay_returns_same_identifiers(snap: dict[str, Any]) -> None:
    acc = snap["accepted"]
    assert acc["replay_cache_hit"] is True
    assert acc["replay_same_request"] is True
    assert acc["replay_same_operation"] is True


def test_dispatch_guard_rejects_precreated_application(snap: dict[str, Any]) -> None:
    """凭据自证不是装饰：`application_count != 0` 必须真的拒。

    没有这条时「accepted 前零 application」只由正向场景支撑，而正向场景在
    `assert_dispatchable` 被整体删掉后仍然通过（计数本来就是 0）。
    """
    assert snap["accepted"]["dispatch_guard"] == "ApplicationPrecreatedError"
    assert snap["accepted"]["dispatch_guard_code"] == "application_precreated"


# ═══════════════════════════════════════════════════════════════════════════
# 二、409 且不返回旧标识（AC 4.1）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "case",
    ["cross_participant", "cross_kind", "payload_differs", "contributors_differ"],
)
def test_idempotency_conflict_returns_409_without_old_identifiers(
    snap: dict[str, Any], case: str
) -> None:
    """逐场景参数化。

    合成一条时任一维度失效会被另几维遮蔽 —— 例如把 fingerprint 比对删掉后，
    `cross_participant` 依然由 same-slot 判据拒绝，于是合并写法仍然绿。
    """
    entry = snap["idempotency"][case]
    assert entry.get("unexpected") is not True, entry
    assert entry["accepted"] is False, entry
    assert entry["error_type"] == "IdempotencyConflictError", entry
    assert entry["leaks_prior_request"] is False, entry["text"]
    assert entry["leaks_prior_operation"] is False, entry["text"]
    assert entry["operation_rows_delta"] == 0, entry


# ═══════════════════════════════════════════════════════════════════════════
# 三、frozen fingerprint 逐字段参与
# ═══════════════════════════════════════════════════════════════════════════


_FINGERPRINT_FIELDS = (
    "client_confirmation_id",
    "client_base_version_id",
    "client_base_representation_id",
    "client_base_projection_sha256",
    "definition_bundle_sha256",
    "authority_model_definition_sha256",
    "adapter_build_digest",
    "contributor_snapshot_digest",
    "client_edit_epoch",
    "write_fence_epoch",
    "initiator_permission_epoch",
)


@pytest.mark.parametrize("field", _FINGERPRINT_FIELDS)
def test_each_frozen_field_changes_the_fingerprint(snap: dict[str, Any], field: str) -> None:
    """「全部冻结字段等值才可返回旧 ID」要求每个字段都真的参与。

    逐字段一条：合成一条「随便改点什么 fingerprint 就变」只能证明**某个**字段参与，
    漏掉任一字段（例如忘记把 `write_fence_epoch` 拼进去）不会被发现，
    而那正好让「撤权后重放拿回旧 request」成为可能。
    """
    base = snap["fingerprint_fields"]["baseline"]
    got = snap["fingerprint_fields"]["per_field"][field]
    assert got != base, f"{field} 未参与 frozen_request_fingerprint"


def test_all_perturbed_fingerprints_are_pairwise_distinct(snap: dict[str, Any]) -> None:
    """11 个单字段扰动互不相同 —— 排除「两个字段被拼在同一个位置」的实现错误。"""
    values = list(snap["fingerprint_fields"]["per_field"].values())
    assert len(set(values)) == len(values)
    assert snap["fingerprint_fields"]["baseline"] not in values


# ═══════════════════════════════════════════════════════════════════════════
# 四、Property 18：真并发收敛
# ═══════════════════════════════════════════════════════════════════════════


def test_race_used_real_concurrency_not_a_serial_loop(snap: dict[str, Any]) -> None:
    """并发本身必须可断言，否则「并发通过了」只是自述。

    四条一起：`RACE_N` 条**不同的** backend pid（= 真的多连接）；全部 racer 都
    commit 成功；`RACE_N` 个任务都到达了 barrier；`max(t_ready) <= min(t_call)`
    （= 所有事务在任何一次 correlate 开始前就已打开 ⇒ 真的重叠，
    不是排队跑完一个再开下一个）。

    `ready_count == RACE_N` 不是冗余：只比时间戳时，若某个任务在 `t_ready` 之前就
    抛异常退出，`max()` 会在更小的集合上取到一个「看起来合规」的值。
    """
    race = snap["race"]
    assert race["n"] == RACE_N
    assert race["distinct_backend_pids"] == RACE_N, race["distinct_backend_pids"]
    assert race["all_committed"] is True, race["racer_errors"]
    assert race["ready_count"] == RACE_N, race
    assert race["max_t_ready"] <= race["min_t_call"], race


def test_race_yields_exactly_one_application(snap: dict[str, Any]) -> None:
    race = snap["race"]
    assert race["application_rows"] == 1
    assert race["application_keys"] == [race["expected_key"]]
    assert race["application_incoming_sha"] == [
        # application 的 incoming digest 就是那份 durable incoming 的 digest
        race["application_incoming_sha"][0]
    ]
    assert race["created_application_count"] == 1, race["created_application_count"]


def test_race_yields_one_primary_and_n_minus_one_direct_duplicates(
    snap: dict[str, Any]
) -> None:
    race = snap["race"]
    assert race["primary_count"] == 1
    assert race["duplicate_count"] == RACE_N - 1
    assert race["duplicates_all_direct"] is True
    assert race["duplicates_have_no_application"] is True
    assert race["duplicate_states"] == ["duplicate"]
    assert race["shapes"] == sorted(["primary"] + ["duplicate"] * (RACE_N - 1))


def test_race_leaves_zero_stranded_chained_or_cyclic_rows(snap: dict[str, Any]) -> None:
    race = snap["race"]
    assert race["stranded"] == 0
    assert race["waiting_application"] == 0
    assert race["chained"] == 0
    assert race["cyclic"] == 0


def test_race_writes_exactly_one_bound_event_and_n_minus_one_duplicate_events(
    snap: dict[str, Any]
) -> None:
    """AC 5.10：`application_bound` 与 `duplicate` 各自在同 operation 内恰一个 event。"""
    race = snap["race"]
    assert race["application_bound_events"] == 1
    assert race["duplicate_events"] == RACE_N - 1


def test_race_folds_to_max_sequence_without_self_supersede(snap: dict[str, Any]) -> None:
    """`origin` 不可变、`effective = max(all)`、room fence 指向该 canonical application。"""
    race = snap["race"]
    expected_max = max(race["request_sequences"])
    assert race["effective_sequence"] == expected_max, race
    assert race["origin_sequence"] in race["request_sequences"]
    assert race["origin_sequence"] <= race["effective_sequence"]
    assert race["superseded_by"] is None, "同 canonical application 不得 self-supersede"
    assert race["room_latest_durable_sequence"] == expected_max
    assert race["room_latest_durable_application_id"] is not None


def test_race_fold_events_are_per_request_and_carry_room_fence(snap: dict[str, Any]) -> None:
    """每个抬高 sequence 的 request 各写一条 fold event，且都带 room fence。

    fold event 条数取决于 racer 的到达序（GREATEST 语义下低 sequence 不 fold），
    因此断言的是**上界与形状**而不是一个魔法数字：≤ N−1、`folded_request_id` 互不相同、
    `room_latest_durable_sequence` 全部非空（AC 10.11「同事务原子决定」的可测投影）。

    🔴 最后一条是本条存在的理由：winner 若不是最高 sequence，就**必须**有 fold
    发生过。首轮实测 winner 恰好是最高 sequence ⇒ 零 fold event 而断言全绿 ——
    这条声明当时完全靠调度运气通过。fold 路径的**确定性**判据在
    `test_fold_race_*`（阶段 4b），本条只补上「该 fold 时没漏 fold」这个条件蕴含。
    """
    race = snap["race"]
    assert race["fold_event_count"] <= RACE_N - 1
    assert race["fold_request_ids_distinct"] is True
    assert race["fold_room_fence_all_set"] is True
    winner_is_max = race["origin_sequence"] == max(race["request_sequences"])
    assert winner_is_max or race["fold_event_count"] >= 1, race


# ═══════════════════════════════════════════════════════════════════════════
# 四之二、并发 fold：origin 必须**不是** max（AC 5.5 / 10.11 的确定性判据）
# ═══════════════════════════════════════════════════════════════════════════


def test_fold_race_used_real_concurrency(snap: dict[str, Any]) -> None:
    fold = snap["fold_race"]
    assert fold["n_racers"] == RACE_N - 1
    assert fold["distinct_backend_pids"] == RACE_N - 1, fold
    assert fold["all_committed"] is True, fold["errors"]
    assert fold["created_application_count"] == 0, "application 已由 seed 建好，racer 不得再建"


def test_fold_race_keeps_origin_at_the_seeded_lowest_sequence(snap: dict[str, Any]) -> None:
    """`origin_request_sequence` 不可变：即使后续 request 的 sequence 全部更高。

    这条与 `effective == max` 必须分开断言。二者在「winner 恰好是 max」时同时成立，
    于是那种场景无法区分「origin 真的没被改写」和「origin 本来就等于 max」。
    """
    fold = snap["fold_race"]
    assert fold["origin_sequence"] == fold["seed_sequence"]
    assert fold["origin_sequence"] < fold["max_sequence"], fold


def test_fold_race_converges_effective_to_max_without_self_supersede(
    snap: dict[str, Any]
) -> None:
    fold = snap["fold_race"]
    assert fold["effective_sequence"] == fold["max_sequence"], fold
    assert fold["superseded_by"] is None, "同 canonical application 只 fold，禁 self-supersede"
    assert fold["room_latest_durable_sequence"] == fold["max_sequence"]
    assert fold["room_latest_durable_application_id"] is not None


def test_fold_race_writes_fold_events_carrying_the_room_fence(snap: dict[str, Any]) -> None:
    """fold event 真的写了（≥1），逐 request 唯一，且每条都带 room durable fence。

    `room_latest_durable_sequence` 非空是 `ck_wpcae_fold_requires_room_fence` 的正面
    证据：AC 10.11 要求 fold 与 room fence 在**同一事务**里原子决定，而「同事务」
    的可测投影就是「fold event 上必定记着当时的 room fence」。
    """
    fold = snap["fold_race"]
    assert fold["fold_event_count"] >= 1, fold
    assert fold["fold_event_count"] <= RACE_N - 1
    assert fold["fold_request_ids_distinct"] is True
    assert fold["fold_room_fence_all_set"] is True
    # 每条 fold event 记录的 origin 都还是 seed 的那个（append-only timeline 不改写 origin）
    assert fold["fold_origin_never_rewritten"] == [fold["seed_sequence"]], fold
    # timeline 里 effective 按 `sequence_no` 单调上升（GREATEST 语义的 append-only 投影）
    assert fold["fold_effective_monotonic"] is True, fold


def test_fold_race_yields_one_primary_and_the_rest_direct_duplicates(
    snap: dict[str, Any]
) -> None:
    fold = snap["fold_race"]
    assert fold["primary_count"] == 1
    assert fold["duplicate_count"] == RACE_N - 1
    assert fold["shapes"] == ["duplicate"] * (RACE_N - 1)


# ═══════════════════════════════════════════════════════════════════════════
# 五、sequence fold / supersede 的 DB 约束逐条归因
# ═══════════════════════════════════════════════════════════════════════════

#: 每条 sequence/收敛规则 → **执法点**。行必须构造成「只违反自己那一条」。
#:
#: 执法点分两类，判据形态不同（这个区分是必需的，不是分类癖）：
#:
#: * ``constraint`` —— 行级 CHECK / UNIQUE。asyncpg 给出 `constraint_name`，可直接归因。
#: * ``trigger`` —— plpgsql `RAISE EXCEPTION ... USING ERRCODE='check_violation'`。
#:   它**不带** constraint 名，报文里也不含函数名 ⇒ 只按名字归因必然判「没归因到」。
#:   这类的归因依据是 `fragment`：该 RAISE 在 V151 里的**唯一**报文片段。
#:   同时要求 `mentions` 为空 —— 证明没有任何行级 CHECK 抢先把它遮蔽掉
#:   （首轮实测有 4 条正是这样被遮蔽的，见 `_forbidden` 各处注释）。
_CONSTRAINT_EXPECT: dict[str, dict[str, str]] = {
    "origin_sequence_immutable": {
        "kind": "trigger",
        "name": "wpsync_check_application_identity",
        "fragment": "必须等于 origin request 的 request_sequence",
    },
    "application_key_immutable": {
        "kind": "trigger",
        "name": "wpsync_check_application_mutation",
        "fragment": "identity 列",
    },
    "effective_sequence_monotonic": {
        "kind": "trigger",
        "name": "wpsync_check_application_mutation",
        "fragment": "effective_request_sequence 只可单调提升",
    },
    "effective_below_origin": {
        "kind": "constraint",
        "name": "ck_wpca_effective_ge_origin",
        "fragment": "",
    },
    "self_supersede": {
        "kind": "constraint",
        "name": "ck_wpca_no_self_supersede",
        "fragment": "",
    },
    "second_primary_for_application": {
        "kind": "constraint",
        "name": "uq_wpso_application",
        "fragment": "",
    },
    "duplicate_pointer_removed": {
        "kind": "trigger",
        "name": "wpsync_check_operation_binding_immutable",
        "fragment": "duplicate 指针不可变",
    },
    "primary_rebound": {
        "kind": "trigger",
        "name": "wpsync_check_operation_binding_immutable",
        "fragment": "禁止改绑/解绑",
    },
    "duplicate_chain": {
        "kind": "trigger",
        "name": "wpsync_check_operation_duplicate_link",
        "fragment": "不是 direct primary",
    },
    "stranded_duplicate_state": {
        "kind": "constraint",
        "name": "ck_wpso_duplicate_shape",
        "fragment": "",
    },
    "fold_event_twice_same_request": {
        "kind": "constraint",
        "name": "uq_wpcae_fold_once",
        "fragment": "",
    },
    "fold_event_without_room_fence": {
        "kind": "constraint",
        "name": "ck_wpcae_fold_requires_room_fence",
        "fragment": "",
    },
    "second_application_bound_event": {
        "kind": "constraint",
        "name": "uq_wpsoe_application_bound_once",
        "fragment": "",
    },
    "duplicate_application_key": {
        "kind": "constraint",
        "name": "working_paper_content_application_application_key_key",
        "fragment": "",
    },
}


@pytest.mark.parametrize("rule", sorted(_CONSTRAINT_EXPECT))
def test_sequence_rule_is_enforced_by_its_declared_constraint(
    snap: dict[str, Any], rule: str
) -> None:
    """被拒**且**拒它的正是声明的那个执法点。

    只断言「被拒了」不够：一行若被另一条约束偶然挡住，归因就是错的，而下一个人会据此
    以为「我声明的那条还活着」。`source != 'probe_defect'` 是必需的第三条 ——
    42804/22P02 是 SQL 写错，不分类就会被读成「约束生效」（典型 WRONG-TEST）。
    """
    entry = snap["constraints"][rule]
    spec = _CONSTRAINT_EXPECT[rule]
    assert entry["accepted"] is False, entry
    assert entry["source"] != "probe_defect", entry
    named = str(entry.get("constraint") or "")
    mentions = entry.get("mentions") or []
    if spec["kind"] == "constraint":
        assert spec["name"] == named or spec["name"] in mentions, entry
    else:
        # trigger raise：既要落在 trigger 分类，也要匹配那条 RAISE 的唯一报文片段，
        # 且**没有**任何行级 CHECK 抢先遮蔽（mentions 必空）。
        assert entry["source"] == "trigger_raise", entry
        assert spec["fragment"] in str(entry["text"]), entry
        assert mentions == [], entry


def test_service_layer_also_refuses_self_supersede(snap: dict[str, Any]) -> None:
    """DB CHECK 之外的第二道：`assert_supersede` 在服务层就拒同 id。"""
    entry = snap["constraints"]["service_self_supersede"]
    assert entry["accepted"] is False
    assert entry["error_type"] == "SupersedeError"
    assert "self-supersede" in entry["text"]


def test_not_both_owners_is_shadowed_but_alive(snap: dict[str, Any]) -> None:
    """`ck_wpso_not_both_owners` 在默认 schema 里被 `ck_wpso_duplicate_shape` 完全遮蔽。

    任何 `application_id IS NOT NULL AND duplicate_of_operation_id IS NOT NULL` 的行都会
    让 duplicate_shape 的两个 disjunct 同时失败 ⇒ 二者必然一起被违反，无法为
    not_both_owners 构造「只违反自己」的行。承认这一点而不是编个归因；
    再在事务内临时 DROP 遮蔽者，证明剩下那条真的接管（纵深防御不是死代码）。
    PG 的 DDL 是事务性的，ROLLBACK 后 schema 原样 —— 最后一条断言就是这件事。
    """
    entry = snap["subsumption"]["not_both_owners_after_dropping_shape"]
    assert entry["accepted"] is False, entry
    named = str(entry.get("constraint") or "")
    mentions = entry.get("mentions") or []
    assert "ck_wpso_not_both_owners" == named or "ck_wpso_not_both_owners" in mentions, entry
    assert snap["subsumption"]["shape_constraint_restored"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 六、application_key 只存在于 application（Property 64）
# ═══════════════════════════════════════════════════════════════════════════


def test_application_key_column_exists_only_on_content_application(
    snap: dict[str, Any]
) -> None:
    """schema 级判据（不是 grep）：整个 schema 里只有一张表有 `application_key` 列。"""
    own = snap["key_ownership"]
    assert own["tables_with_application_key"] == ["working_paper_content_application"]
    assert own["orm_operation_has_key"] is False
    assert own["orm_operation_event_has_key"] is False
    assert own["orm_application_has_key"] is True


def test_application_key_is_unique(snap: dict[str, Any]) -> None:
    assert snap["key_ownership"]["unique_constraints_on_key"], snap["key_ownership"]


def test_application_key_signature_excludes_status_and_request_identity() -> None:
    """签名判据（Task 22 立的形态，本任务同样依赖它，故在此再钉一次）。

    签名比「算一遍看变不变」强：后者只证明当前实现没用这些入参，前者让「想把 status
    塞进 key」必须先改签名 —— 而改签名会被本条打红。
    """
    import inspect as _inspect

    from app.services.workpaper_sync.models import compute_application_key

    params = set(_inspect.signature(compute_application_key).parameters)
    forbidden = {
        "callback_status",
        "status",
        "request_id",
        "request_sequence",
        "origin_request_sequence",
        "effective_request_sequence",
        "room_last_applied_version_id",
        "delivery_key",
        "delivery_id",
        "delivery_discriminator",
    }
    assert not (params & forbidden), params & forbidden
    assert params == {
        "wp_id",
        "room_id",
        "generation",
        "frozen_client_base_version_id",
        "frozen_client_base_representation_id",
        "incoming_sha256",
        "definition_bundle_sha256",
        "authority_model_definition_sha256",
        "adapter_build_digest",
    }


# ═══════════════════════════════════════════════════════════════════════════
# 七、读路径固定四步（AC 5.5 末段 / 8.5 / 10.5）
# ═══════════════════════════════════════════════════════════════════════════


def test_primary_read_follows_the_fixed_stage_order(snap: dict[str, Any]) -> None:
    rp = snap["read_path"]
    assert rp["primary_stages"] == [
        "requested_scope_resolved",
        "requested_action_authorized",
        "requested_operation_loaded",
        "canonicalized",
        "canonical_application_bound",
    ]
    assert rp["primary_shape"] == "primary"
    assert rp["primary_canonical_is_requested"] is True


def test_duplicate_read_verifies_direct_primary_before_canonicalizing(
    snap: dict[str, Any]
) -> None:
    """duplicate 读路径必须多一步 `direct_primary_verified`，且**顺序在 canonicalize 之前**。"""
    stages = snap["read_path"]["dup_stages"]
    assert stages == [
        "requested_scope_resolved",
        "requested_action_authorized",
        "requested_operation_loaded",
        "direct_primary_verified",
        "canonicalized",
        "canonical_application_bound",
    ]
    assert stages.index("direct_primary_verified") < stages.index("canonicalized")


def test_duplicate_read_never_requires_the_duplicate_itself_to_bind_application(
    snap: dict[str, Any]
) -> None:
    """AC 5.5 末段：只要求 canonical primary 唯一绑定，合法 duplicate 自身必须为空。"""
    rp = snap["read_path"]
    assert rp["dup_shape"] == "duplicate"
    assert rp["dup_requested_application"] is None
    assert rp["dup_canonical_application"] is not None
    assert rp["dup_canonical_is_primary"] is True
    assert rp["dup_followed"] is True
    assert rp["dup_effective_sequence"] is not None


def test_duplicate_read_creates_no_new_operation_or_application(snap: dict[str, Any]) -> None:
    rp = snap["read_path"]
    assert rp["operation_rows_delta"] == 0
    assert rp["application_rows_delta"] == 0


@pytest.mark.parametrize("case", ["cross_scope_project", "cross_scope_entry", "unknown_id"])
def test_scope_mismatch_and_unknown_id_share_one_404_envelope(
    snap: dict[str, Any], case: str
) -> None:
    """跨 scope 与不存在**同一** 404 语义 —— 否则错误类型本身泄露「该 id 存在」。"""
    assert snap["read_path"][case] == "OperationScopeNotVisibleError", snap["read_path"]


def test_authorization_fires_before_any_business_row_is_loaded(snap: dict[str, Any]) -> None:
    """行为判据（不是注释）：只在 scope index 登记、无 operation 行的 id ——

    * `authorize` 拒 ⇒ **403**（`ScopeAuthorizationDeniedError`）；
    * `authorize` 放行 ⇒ 才轮到「业务行不存在」的 404。

    若实现先加载业务行，第一种情形只会得到 404。两条一起断言：只测第一条时，
    「两种情形都返回 403」也能通过，而那意味着 404 语义丢失。
    """
    rp = snap["read_path"]
    assert rp["denied_ghost"] == "ScopeAuthorizationDeniedError", rp
    assert rp["denied_ghost_code"] == "scope_authorization_denied"
    assert rp["allowed_ghost"] == "OperationScopeNotVisibleError", rp


def test_pre_correlation_shell_is_readable_but_not_as_a_bound_operation(
    snap: dict[str, Any]
) -> None:
    """`require_application` 两态各自可证。

    * `True`（GET/conflict/retry/resolve）⇒ canonical primary 未绑定 application 必须拒；
    * `False`（timeline）⇒ 尚未 correlate 的 shell 必须可读，且 `canonical_application_id`
      为空、阶段里**没有** `canonical_application_bound`。

    两态一起断言：只留第一条时，把 `require_application` 参数整个删掉（恒 True）
    不会被发现，而那会让 accepted 之后、durable 之前的轮询全部 500。
    """
    rp = snap["read_path"]
    # 🔴 断言的是 `CanonicalPrimaryUnboundError` 而**不是**其兄弟类型。
    # 首轮两条拒绝共用 `CanonicalBindingError`：`app_id is None` 时若不拒，紧接着的
    # `count(... application_id == app_id)` 会被渲染成 `IS NULL` ⇒ 统计到全部
    # pre-correlation shell ⇒ `bound != 1` 抛同一个类型 ⇒ 定向变异实测 GREEN。
    # 分型之后这条判据才真的能证明第一道门有效。
    assert rp["pre_correlation_read"] == "CanonicalPrimaryUnboundError", rp
    assert rp["pre_correlation_read_code"] == "canonical_primary_unbound"
    assert rp["pre_correlation_lenient_application"] is None
    assert rp["pre_correlation_lenient_stages"] == [
        "requested_scope_resolved",
        "requested_action_authorized",
        "requested_operation_loaded",
        "canonicalized",
    ]


def test_service_rejects_a_double_bound_primary_when_the_unique_index_is_gone(
    snap: dict[str, Any]
) -> None:
    """服务层「canonical primary 唯一绑定」不是不可达分支。

    `uq_wpso_application` 让「一个 application 被两个 operation 绑定」在库里无法存在
    ⇒ 该分支平时不可达，而不可达分支的「已被守卫锁住」只是自述。这里在事务内 DROP
    唯一约束、造出双绑，证明服务层这道纵深防御真的会拒；ROLLBACK 后约束原样。
    """
    entry = snap["subsumption"]["service_rejects_double_bound_primary"]
    assert entry["accepted"] is False, entry
    assert entry["error_type"] == "CanonicalBindingError", entry
    assert snap["subsumption"]["unique_constraint_restored"] == 1


def test_canonicalize_requires_an_authorized_reference(snap: dict[str, Any]) -> None:
    """authorization-first 由参数类型强制：裸对象与「缺授权阶段」的 ref 都要被拒。"""
    rp = snap["read_path"]
    assert rp["raw_ref"] == "ScopeAuthorizationDeniedError"
    assert rp["unauthorized_ref"] == "ScopeAuthorizationDeniedError"


def test_authorization_stage_reads_only_the_scope_index() -> None:
    """源码形态判据：授权阶段只许调 `resolve_scope`（AC 10.5）。

    运行期观察只能证明「这次没多读」；把 `lock_room`/`sa.select(Operation)` 加回授权阶段后
    行为结果一样，只有源码判据会红。
    """
    from app.services.workpaper_sync.request_application import (
        assert_authorization_first_source_shape,
    )

    assert assert_authorization_first_source_shape() == ("resolve_scope",)


# ═══════════════════════════════════════════════════════════════════════════
# 八、status 6/2 多 delivery 一 application（Property 56）
# ═══════════════════════════════════════════════════════════════════════════


def test_repeated_correlation_under_one_frozen_identity_creates_one_application(
    snap: dict[str, Any]
) -> None:
    """同 frozen identity 的三次 correlation（status 6 / status 2 / 重试）⇒ 一个 application。"""
    md = snap["multi_delivery"]
    assert md["application_rows_delta"] == 1
    assert md["shapes"] == ["primary", "duplicate", "duplicate"]
    assert md["primaries_for_this_incoming"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 九、recovery claim（AC 4.10 / 5.8 / 14.3）
# ═══════════════════════════════════════════════════════════════════════════


def test_recovery_case_has_zero_entities_before_claim(snap: dict[str, Any]) -> None:
    rec = snap["recovery"]
    assert rec["pre_claim_all_null"] is True, rec["pre_claim"]
    assert rec["pre_claim"]["state"] == "unclaimed"


def test_nullable_operation_recovery_case_never_enters_ordinary_retry(
    snap: dict[str, Any]
) -> None:
    """claim 前 `operation_id` 为 NULL ⇒ 不得进入普通 retry；claim 后才可以。

    两态一起断言：只断言前者时，「`retry_eligibility` 恒返回 False」也通过，
    而那会让 primary retry 也进不去。
    """
    rec = snap["recovery"]
    assert rec["retry_eligible_before_claim"] is False
    assert rec["retry_eligible_after_claim"] is True


def test_recovery_claim_lands_as_primary_bound_to_the_same_application(
    snap: dict[str, Any]
) -> None:
    rec = snap["recovery"]
    assert rec["shape_is_primary"] is True
    assert rec["kind"] == "recovery_claim"
    assert rec["same_application"] is True
    assert rec["operation_application"] == rec["case_application"]
    assert rec["application_incoming"] == rec["case_incoming"]


# ═══════════════════════════════════════════════════════════════════════════
# 十、refresh_required 拒绝下一 request（Property 62 / AC 2.9 / 4.11）
# ═══════════════════════════════════════════════════════════════════════════


def test_refresh_required_room_rejects_next_request_before_any_row_is_written(
    snap: dict[str, Any]
) -> None:
    """merged≠incoming ⇒ room `refresh_required` ⇒ 下一 request 在 Command Service **之前**被拒。

    「之前」的可测形态就是 `operation_rows_delta == 0`：既没落 request 也没落 shell，
    因此不可能已经发出过 Command Service 调用（后者以凭据为前提）。
    """
    entry = snap["refresh_required"]
    assert entry["accepted"] is False, entry
    assert entry["error_type"] == "RoomNotWritableError", entry
    assert entry["mentions_refresh"] is True
    assert entry["operation_rows_delta"] == 0
