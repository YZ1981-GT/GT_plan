# -*- coding: utf-8 -*-
"""Task 24 真实 PostgreSQL 行为守卫：clean close 的 exactly-one close-capture。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 24
Requirements: 4.1, 4.4, 4.7, 4.10, 5.5, 10.10
Properties: **P12 / P13 / P15 / P43 / P64**

═══ 为什么 partial unique 不够，必须有行为测试 ═══

V151 的 `uq_wpfr_open_close_capture` 是 generation 内 open-state partial unique：它证明
**不会有两条**，永远证明不了**最终会有一条**。AC 4.10 明写这一点。所以本模块把
Task 24 正文点名的每个场景都在真库上跑一遍，逐个数 capture 条数。

═══ 判别性：leader 必须**不是**那个「怎么排都会赢」的人 ═══

🔴 这是本任务最容易假绿的地方，而且本 spec 已经踩过一次：Task 23 的第一版竞态
「每条断言都过，而 fold 分支一次都没执行」—— 因为赢家恰好是按到达顺序也会赢的那个。

close leader 有同样的形状。`intent_sequence` 由 `max+1` 生成，于是默认情况下
「最高 sequence」＝「最后插入」＝「`created_at` 最晚」＝（多半也是）「id 最大」，
四种错误 comparator 会给出同一个答案，怎么改都测不出来。

本模块因此做两件事：

1. 每个核心场景跑四种扰动 —— `none` / `created_reversed` / `sequence_reversed` /
   `both`。中间两种让「最高 sequence」与「`created_at` 最晚」**必然分离**，
   于是 comparator 一旦改用 `created_at` 就会选错人；
2. 另有一个专门的判别性场景 :data:`_DISCRIMINATING`：四个 participant，把最高
   `intent_sequence` 赋给一个**既不是第一个插入、也不是最后一个插入、且不是全局最大
   id** 的 intent，同时把它的 `created_at` 设成**最早**。于是「按 created_at」
   「按插入序取首」「按插入序取尾」「按 id」四种错法**全部**会选错人，而且是
   确定性地选错（不是靠随机 id 碰运气）。

═══ 每个阶段一个独立事务 ═══

场景不是「一个 session 里跑到底」，而是逐阶段各开一个 session 并 commit ——
既贴近真实（每个 API 调用一个事务），也躲开一个实测踩过的坑：用 `sa.update()`
直接改行**不会**刷新 SQLAlchemy 的 identity map，随后同一 session 里的
`select(...)` 会拿回缓存里的旧值；而用 `expire_all()` 强制过期又会让后续同步
属性访问触发懒加载，在 async 引擎下直接 `MissingGreenlet`。分事务两个问题都不存在，
而且阶段之间只传**纯值**（uuid/int/str），ORM 实例不跨事务。

═══ Command Service 是可编程 stand-in ═══

本模块用 :class:`_ProgrammableTransport`（确定性、可断言调用序）代替真实 OO 9.4。
真实 OO 9.4 的端到端验收是 **Task 44/70**，本任务不声称覆盖它。stand-in 覆盖的是
「出站请求形态」与「HTTP 200 只代表 accepted」这条语义。

═══ 隔离与采集 ═══

scratch schema `tmp_task24_ci_<hex>`，`search_path` 只含它，结束 `DROP SCHEMA CASCADE`。
全部场景由**一次 `asyncio.run`** 跑完落进快照。采集阶段异常一律**记录不穿透**：
穿透会把整个 module 变成 collection ERROR，而 `-rf` 只列 FAILED 不列 ERROR
⇒ 定向变异看不到预期失败项 ⇒ 判 GREEN。
`test_no_phase_crashed_during_collection` 是这个决定的另一半。

`DATABASE_URL` 非 PostgreSQL 时**直接失败而不是 skip** —— 与 Task 10/21/22/23 同约定：
skip 等于静默抹掉本任务唯一判据。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
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

_SCHEMA_PREFIX = "tmp_task24_ci_"

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

#: 扰动模式。中间两种是**判别性**的（最高 sequence ≠ 最晚 created_at）。
_SHUFFLES = ("none", "created_reversed", "sequence_reversed", "both")

#: 判别性扰动（守卫与变异脚本共同引用）。
_DISCRIMINATING_SHUFFLES = ("created_reversed", "sequence_reversed")

#: 判别性场景名。
_DISCRIMINATING = "deterministic_leader_discriminating"

_AUTH_CASES = [
    "revoked_participant",
    "expired_lease",
    "view_only",
    "refresh_required",
    "write_fence_bumped",
]

#: intent 终态字面量（测试侧集中一处，避免散写字符串）。
_TERMINAL_INTENT_STATES = frozenset(
    {"authorization_stale", "recovery_required", "superseded", "error"}
)


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _err(exc: BaseException) -> str:
    """异常 → 单行诊断，带最后几帧（只记 `type: message` 时无法定位）。"""
    import traceback

    frames = traceback.extract_tb(exc.__traceback__)[-4:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


class _ProgrammableTransport:
    """Command Service 的可编程 stand-in（真实 OO 9.4 见 Task 44/70）。

    `calls` 累积每一次出站请求，让「哪些 close 真的发了命令、发了几条」成为可断言
    事实 —— 只数 DB 行数无法区分「建了 request 但没出站」。
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


async def _collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部场景
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.workpaper_sync_models import (
        WorkpaperForcesaveRequest,
        WorkpaperOoCloseIntent,
        WorkpaperOoCloseIntentEvent,
        WorkpaperOoParticipant,
        WorkpaperOoRoom,
    )
    from app.services.workpaper_sync.close_intent import (
        CLOSE_INTENT_LIVE_STATES,
        CloseIntentService,
        OPEN_CAPTURE_STATES,
    )
    from app.services.workpaper_sync.command_service import (
        CommandServiceClient,
        load_command_service_policy,
    )
    from app.services.workpaper_sync.models import (
        ArtifactKind,
        ArtifactState,
        BundleSlot,
        BundleSlotSpec,
        CloseIntentState,
        ParticipantMode,
        ParticipantState,
        RequestKind,
        RequestState,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.request_application import RequestApplicationService
    from app.services.workpaper_sync.rooms import (
        ParticipantNotWritableError,
        RoomNotWritableError,
        RoomScope,
        RoomService,
        WriteFenceStaleError,
        derive_doc_key,
    )

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 24 的判据是 close-capture 的 generation 内唯一性、room row lock 下的"
            " leader 仲裁与 intent 状态终结，全部依赖真实 PostgreSQL 约束与锁；"
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
        "close": {},
        "dispatch": {},
        "authorization": {},
        "concurrency": {},
        "policy": {},
        "sequence_uniqueness": {},
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

        user_keys = ("user_a", "user_b", "user_c", "user_d")
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
        adapter_digest = _d("adapter-build-task24")
        contrib_digest = _d("contributors-task24")

        # ═══ 世界：definitions / bundle / representation（一次）═════════════
        async def _build_world(repo: WorkpaperSyncRepository) -> dict[str, Any]:
            blobs: dict[str, Any] = {}
            for name in ("tpl", "instr", "contract", "authority", "bundle_payload"):
                blobs[name] = await repo.register_artifact(
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=ArtifactKind.definition,
                    state=ArtifactState.published,
                    relative_path=(
                        f"{base_path}/.versions/{wp_id}/definitions/t24-{name}.json"
                    ),
                    sha256=_d(f"blob-t24-{name}"),
                    size_bytes=1024,
                    document_type="json",
                )
            tpl = await repo.create_definition_artifact(
                kind="template",
                logical_id="d2.template.t24",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["tpl"].id,
                sha256=_d("tpl-def-t24"),
                structure_hash=_d("tpl-structure-t24"),
                source_commit="task24",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation",
                logical_id="d2.instrumentation.t24",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["instr"].id,
                sha256=_d("instr-def-t24"),
                structure_hash=_d("instr-structure-t24"),
                source_commit="task24",
            )
            con = await repo.create_definition_artifact(
                kind="contract",
                logical_id="d2.contract.t24",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["contract"].id,
                sha256=_d("contract-def-t24"),
                source_commit="task24",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model",
                logical_id="authority.projection.t24",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["authority"].id,
                sha256=_d("authority-def-t24"),
                authority_model_type="projection_contract",
                source_commit="task24",
            )
            bundle = await repo.create_definition_bundle(
                authority_model_definition_id=authority.id,
                slots={
                    BundleSlot.template: BundleSlotSpec(
                        BundleSlot.template,
                        "definition",
                        f"definition:{tpl.id}",
                        tpl.sha256,
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
                        f"definition:{con.id}",
                        con.sha256,
                    ),
                },
                canonical_payload_artifact_id=blobs["bundle_payload"].id,
                canonical_payload_sha256=_d("bundle-canonical-t24"),
            )
            proj_art = await repo.register_artifact(
                project_id=project_id,
                wp_id=wp_id,
                kind=ArtifactKind.projection,
                state=ArtifactState.published,
                relative_path=f"{base_path}/.versions/{wp_id}/projections/t24.json.gz",
                sha256=_d("projection-t24"),
                size_bytes=2048,
                document_type="json.gz",
            )
            canon = await repo.register_artifact(
                project_id=project_id,
                wp_id=wp_id,
                kind=ArtifactKind.canonical,
                state=ArtifactState.published,
                relative_path=(
                    f"{base_path}/.versions/{wp_id}/representations/{ENTRY}/t24.xlsx"
                ),
                sha256=_d("canonical-t24"),
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
                adapter_build_digest=adapter_digest,
                structure_hash=_d("structure-t24"),
                identity_inventory_sha256=_d("identity-t24"),
                reason="content_commit",
            )
            await repo.set_entry_pointer(
                wp_id=wp_id, entry_id=ENTRY, representation_id=rep.id, generation=1
            )
            return {
                "bundle_id": bundle.id,
                "content_version_id": cv.id,
                "representation_id": rep.id,
                "projection_sha256": proj_art.sha256,
            }

        world: dict[str, Any] = {}
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            world.update(await _build_world(repo))
            await s.commit()
        rep_id = world["representation_id"]
        cv_id = world["content_version_id"]
        bundle_id = world["bundle_id"]
        projection_sha = world["projection_sha256"]

        transport = _ProgrammableTransport()
        policy = load_command_service_policy()
        snap["policy"] = {
            "claim_shape": policy.jwt_claim_shape,
            "http_timeout": int(policy.timers.command_service_http_timeout_seconds),
            "known_codes": list(policy.known_codes),
        }

        def _client() -> CommandServiceClient:
            return CommandServiceClient(
                onlyoffice_url="http://oo.internal:8080",
                jwt_secret="task24-pg-secret",
                transport=transport,
                policy=policy,
            )

        def _wire(s: Any) -> tuple[Any, Any, CloseIntentService]:
            repo = WorkpaperSyncRepository(s)
            rooms = RoomService(repo)
            return (
                repo,
                rooms,
                CloseIntentService(
                    repo,
                    _client(),
                    rooms=rooms,
                    requests=RequestApplicationService(repo, rooms),
                ),
            )

        # ═══ 每个场景一个新 generation 的 room；只返回**纯值** ══════════════
        async def _make_room(*, generation: int, users: tuple[str, ...]) -> dict[str, Any]:
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
                room_id = room.id
                doc_key = room.doc_key
                frozen = await svc.frozen_bundle_identity(bundle_id)
                parts: dict[str, uuid.UUID] = {}
                for u in users:
                    part = await svc.join_participant(
                        scope,
                        room_id=room_id,
                        user_id=ids[u],
                        mode=ParticipantMode.edit,
                        permission_epoch=5,
                        lease_token=f"lease-{generation}-{u}",
                    )
                    parts[u] = part.id
                    await svc.confirm_descriptor(
                        scope,
                        room_id=room_id,
                        participant_id=part.id,
                        representation_id=rep_id,
                        content_version_id=cv_id,
                        projection_sha256=projection_sha,
                        idempotency_key=f"ready-{generation}-{u}",
                        expected_bundle=frozen,
                    )
                await s.commit()
            return {
                "room_id": room_id,
                "generation": generation,
                "doc_key": doc_key,
                "participants": parts,
                "users": users,
            }

        async def _read_intents(ctx: dict[str, Any]) -> list[dict[str, Any]]:
            """按 `created_at` 升序读 intent 的**纯值**投影。"""
            async with Session() as s:
                rows = (
                    (
                        await s.execute(
                            sa.select(WorkpaperOoCloseIntent)
                            .where(
                                WorkpaperOoCloseIntent.room_id == ctx["room_id"],
                                WorkpaperOoCloseIntent.generation == ctx["generation"],
                            )
                            .order_by(
                                WorkpaperOoCloseIntent.created_at.asc(),
                                WorkpaperOoCloseIntent.intent_sequence.asc(),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                return [
                    {
                        "id": r.id,
                        "participant_id": r.participant_id,
                        "sequence": int(r.intent_sequence),
                        "state": r.state,
                        "created_at": r.created_at,
                        "predecessor": r.ordinary_forcesave_request_id,
                        "promoted_request_id": r.promoted_request_id,
                    }
                    for r in rows
                ]

        async def _do_close(ctx: dict[str, Any], user: str, *, tag: str) -> dict[str, Any]:
            async with Session() as s:
                _repo, _rooms, svc = _wire(s)
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
                    "intent_id": opened.intent_id,
                    "intent_sequence": opened.intent_sequence,
                    "remaining_active": opened.remaining_active_editors,
                    "has_predecessor": opened.has_predecessor,
                    "capture_created": opened.reconcile.capture_created,
                    "leader_intent_id": opened.reconcile.leader_intent_id,
                    "predecessor_request_id": (
                        opened.predecessor.accepted.request.id
                        if opened.predecessor is not None
                        else None
                    ),
                    "predecessor_outcome": (
                        opened.predecessor.dispatch.outcome.value
                        if opened.predecessor is not None
                        else None
                    ),
                    "predecessor_accepted_only": (
                        (
                            opened.predecessor.dispatch.accepted
                            and opened.predecessor.dispatch.awaits_callback
                        )
                        if opened.predecessor is not None
                        else None
                    ),
                    "shell_application_id": (
                        opened.predecessor.accepted.operation.application_id
                        if opened.predecessor is not None
                        else None
                    ),
                    "application_count": (
                        opened.predecessor.accepted.application_count
                        if opened.predecessor is not None
                        else None
                    ),
                }
                await s.commit()
                return out

        async def _do_reconcile(ctx: dict[str, Any]) -> dict[str, Any]:
            async with Session() as s:
                _repo, _rooms, svc = _wire(s)
                out = await svc.reconcile(
                    scope,
                    room_id=ctx["room_id"],
                    adapter_build_digest=adapter_digest,
                    contributor_snapshot_digest=contrib_digest,
                )
                rec = {
                    "leader_intent_id": out.leader_intent_id,
                    "capture_created": out.capture_created,
                    "no_successor": out.no_successor,
                    "live_intents": out.live_intent_count,
                    "open_captures": out.open_capture_count,
                    "stale_reported": [
                        str(x) for x in out.repository.authorization_stale_intent_ids
                    ],
                    "eligibility_epoch": int(out.repository.eligibility_epoch),
                    "dispatched_capture": out.capture_dispatch is not None,
                    # 🔴 下面三项是「comparator 这一次真的跑了」的凭证，不是装饰：
                    # 「同 eligibility snapshot 重试不换 leader」若只断言两次 leader 相等，
                    # 在 promoted 幂等短路（comparator 根本没执行）或 eligible 只剩一条
                    # （max 无从选错）时会**恒真**地通过 —— 那正是 Task 23 实测到的假绿形态：
                    # 场景通过了每一条断言，而被测代码路径一次都没执行。
                    "eligibility_digest": out.repository.eligibility_digest,
                    "eligible_count": len(out.prediction.eligible_intent_ids),
                    "promoted_short_circuit": out.prediction.promoted_short_circuit,
                }
                await s.commit()
                return rec

        async def _terminate_predecessors(ctx: dict[str, Any]) -> int:
            """把该 generation 的普通 forcesave predecessor 全部落 terminal。

            直接 UPDATE 而不是走 callback 链路：本任务的判据是 barrier 语义
            （「全部 predecessor 达 durable terminal 后才提升 leader」），而
            callback → durable → correlation 是 Task 22/26 的判据。在这里重跑那条链
            只会把失败原因混在一起。
            """
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

        async def _apply_shuffle(ctx: dict[str, Any], mode: str) -> dict[str, Any]:
            """独立扰动 `created_at` 与 `intent_sequence`。

            两者分开扰动是 Task 24 正文的原话（「分别打乱 `created_at` 与插入顺序」）。
            `created_reversed` 让最先插入的 intent 拿到**最晚**时间戳，于是
            「最高 sequence」与「最晚 created_at」必然是不同的两条 —— comparator
            改用 created_at 时会确定性地选错人。

            timestamptz 一律在 **Python 侧**构造 aware `datetime` 再作绑定参数下发：
            asyncpg 按目标列类型编码，SQL 层 `CAST(:x AS timestamptz)` 无效。
            """
            rows = await _read_intents(ctx)
            if not rows or mode == "none":
                return {"mode": mode, "touched": 0}
            anchor = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
            n = len(rows)
            touched = 0
            async with Session() as s:
                if mode in ("created_reversed", "both"):
                    for idx, row in enumerate(rows):
                        await s.execute(
                            sa.update(WorkpaperOoCloseIntent)
                            .where(WorkpaperOoCloseIntent.id == row["id"])
                            .values(
                                created_at=anchor + timedelta(seconds=(n - idx) * 60)
                            )
                        )
                        touched += 1
                await s.commit()
            if mode in ("sequence_reversed", "both"):
                seqs = sorted(r["sequence"] for r in rows)
                await _assign_sequences(
                    ctx, {rows[idx]["id"]: seqs[n - 1 - idx] for idx in range(n)}
                )
                touched += n
            return {"mode": mode, "touched": touched}

        async def _assign_sequences(
            ctx: dict[str, Any], mapping: dict[uuid.UUID, int]
        ) -> None:
            """把 intent 的 `intent_sequence` 重排成任意置换。

            🔴 必须**先泊车再落位**：V151 有
            `uq_wpoci_sequence UNIQUE (room_id, generation, intent_sequence)`，
            逐行 UPDATE 成一个置换时中途必然撞上尚未挪走的旧值
            （实测 `duplicate key ... (room, generation, 2) already exists`）。
            所以先把涉及的行全部挪到一段不冲突的高位（仍满足
            `ck_wpoci_sequence_positive`），再逐行写入目标值。
            """
            async with Session() as s:
                for offset, intent_id in enumerate(mapping, start=1):
                    await s.execute(
                        sa.update(WorkpaperOoCloseIntent)
                        .where(WorkpaperOoCloseIntent.id == intent_id)
                        .values(intent_sequence=900_000 + offset)
                    )
                await s.flush()
                for intent_id, seq in mapping.items():
                    await s.execute(
                        sa.update(WorkpaperOoCloseIntent)
                        .where(WorkpaperOoCloseIntent.id == intent_id)
                        .values(intent_sequence=int(seq))
                    )
                await s.commit()

        async def _capture_counts(ctx: dict[str, Any]) -> tuple[int, int]:
            """(open close-capture 数, 含终态的 close-capture 总数)。

            两个数都要：partial unique 只约束 open 状态，「造过第二条又终结掉」
            在只看 open 时是隐形的。
            """
            async with Session() as s:
                base = sa.select(sa.func.count()).select_from(
                    WorkpaperForcesaveRequest
                ).where(
                    WorkpaperForcesaveRequest.room_id == ctx["room_id"],
                    WorkpaperForcesaveRequest.generation == ctx["generation"],
                    WorkpaperForcesaveRequest.kind == RequestKind.close_capture.value,
                )
                open_n = int(
                    (
                        await s.execute(
                            base.where(
                                WorkpaperForcesaveRequest.state.in_(
                                    sorted(x.value for x in OPEN_CAPTURE_STATES)
                                )
                            )
                        )
                    ).scalar_one()
                )
                all_n = int((await s.execute(base)).scalar_one())
                return open_n, all_n

        async def _measure(ctx: dict[str, Any]) -> dict[str, Any]:
            rows = await _read_intents(ctx)
            open_n, all_n = await _capture_counts(ctx)
            async with Session() as s:
                room = (
                    await s.execute(
                        sa.select(WorkpaperOoRoom).where(
                            WorkpaperOoRoom.id == ctx["room_id"]
                        )
                    )
                ).scalar_one()
                leader_id = room.close_leader_intent_id
                room_state = room.state
                room_superseded = room.superseded_at is not None
                elig = int(room.close_leader_eligibility_epoch)
                barrier = int(room.close_barrier_epoch)
                events = 0
                stale_events = 0
                if rows:
                    ids_list = [r["id"] for r in rows]
                    events = int(
                        (
                            await s.execute(
                                sa.select(sa.func.count())
                                .select_from(WorkpaperOoCloseIntentEvent)
                                .where(
                                    WorkpaperOoCloseIntentEvent.intent_id.in_(ids_list)
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
                                    WorkpaperOoCloseIntentEvent.intent_id.in_(ids_list),
                                    WorkpaperOoCloseIntentEvent.to_state
                                    == CloseIntentState.authorization_stale.value,
                                )
                            )
                        ).scalar_one()
                    )
            expected_leader = (
                max(rows, key=lambda r: (r["sequence"], str(r["id"])))["id"]
                if rows
                else None
            )
            latest_created = (
                max(rows, key=lambda r: (r["created_at"], str(r["id"])))["id"]
                if rows
                else None
            )
            live = [
                r
                for r in rows
                if CloseIntentState(r["state"]) in CLOSE_INTENT_LIVE_STATES
            ]
            promoted = [
                r for r in rows if CloseIntentState(r["state"]) is CloseIntentState.promoted
            ]
            leader_row = next((r for r in rows if r["id"] == leader_id), None)
            return {
                "open_captures": open_n,
                "all_captures": all_n,
                "room_state": room_state,
                "room_superseded": room_superseded,
                "leader_intent": str(leader_id) if leader_id else None,
                "expected_leader": str(expected_leader) if expected_leader else None,
                "leader_is_highest_sequence_id": leader_id == expected_leader,
                "leader_is_latest_created_at": (
                    leader_id is not None and leader_id == latest_created
                ),
                "highest_seq_equals_latest_created": expected_leader == latest_created,
                "leader_sequence": leader_row["sequence"] if leader_row else None,
                "intent_count": len(rows),
                "intent_states": sorted(r["state"] for r in rows),
                "live_intents": len(live),
                "promoted_intents": len(promoted),
                "promoted_with_request": sum(
                    1 for r in promoted if r["promoted_request_id"] is not None
                ),
                "predecessor_links": sum(
                    1 for r in rows if r["predecessor"] is not None
                ),
                "eligibility_epoch": elig,
                "close_barrier_epoch": barrier,
                "event_count": events,
                "authorization_stale_events": stale_events,
            }

        async def _case(
            name: str, *, generation: int, users: tuple[str, ...], script: Any
        ) -> None:
            before = len(transport.calls)
            try:
                ctx = await _make_room(generation=generation, users=users)
                extra = await script(ctx)
                measured = await _measure(ctx)
                measured["dispatches"] = len(transport.calls) - before
                measured.update(extra or {})
                snap["close"][name] = measured
            except Exception as exc:  # noqa: BLE001 - 记录不穿透
                _phase_failed(f"close::{name}", exc)
                snap["close"][name] = {"error": _err(exc)}

        generation = 100

        # ═══ 核心场景 × 四种扰动 ═══════════════════════════════════════════
        def _single(shuffle: str):
            async def _script(ctx):
                opened = await _do_close(ctx, "user_a", tag=f"single-{shuffle}")
                await _apply_shuffle(ctx, shuffle)
                out = await _do_reconcile(ctx)
                return {
                    "shuffle": shuffle,
                    "first_capture_created": opened["capture_created"],
                    "reentrant_capture_created": out["capture_created"],
                    "predecessor_created": opened["has_predecessor"],
                    "remaining_active_at_close": opened["remaining_active"],
                    "reentrant_same_leader": (
                        opened["leader_intent_id"] == out["leader_intent_id"]
                    ),
                }

            return _script

        def _two_user(order: tuple[str, str], shuffle: str, *, terminal_before: bool):
            async def _script(ctx):
                first = await _do_close(ctx, order[0], tag=f"two-{shuffle}")
                if terminal_before:
                    await _terminate_predecessors(ctx)
                second = await _do_close(ctx, order[1], tag=f"two-{shuffle}")
                mid_open, _mid_all = await _capture_counts(ctx)
                # 🔴 扰动落在 promotion **之前**还是**之后**，判据完全不同：
                #  * 之前 ⇒ leader 必须跟着 sequence 变（comparator 判据）；
                #  * 之后 ⇒ leader 必须**纹丝不动**（AC 10.10：promotion 后不得改选）。
                # `terminal_before=True` 时第二人关闭当场就 promote，故一律是「之后」。
                shuffle_pre_promotion = mid_open == 0
                leader_before_shuffle = second["leader_intent_id"]
                await _apply_shuffle(ctx, shuffle)
                if not terminal_before:
                    await _terminate_predecessors(ctx)
                final = await _do_reconcile(ctx)
                again = await _do_reconcile(ctx)
                return {
                    "shuffle": shuffle,
                    "order": list(order),
                    "terminal_before_second_close": terminal_before,
                    "shuffle_pre_promotion": shuffle_pre_promotion,
                    "leader_before_shuffle": str(leader_before_shuffle),
                    "leader_after_shuffle": str(final["leader_intent_id"]),
                    "leader_unchanged_by_shuffle": (
                        leader_before_shuffle == final["leader_intent_id"]
                    ),
                    "first_predecessor": first["has_predecessor"],
                    "second_predecessor": second["has_predecessor"],
                    "captures_at_mid": mid_open,
                    "final_capture_created": (
                        final["capture_created"] or second["capture_created"]
                    ),
                    "reentrant_capture_created": again["capture_created"],
                    "reentrant_same_leader": (
                        final["leader_intent_id"] == again["leader_intent_id"]
                    ),
                }

            return _script

        for shuffle in _SHUFFLES:
            await _case(
                f"single__{shuffle}",
                generation=generation,
                users=("user_a",),
                script=_single(shuffle),
            )
            generation += 1
        for order in (("user_a", "user_b"), ("user_b", "user_a")):
            tag = "ab" if order[0] == "user_a" else "ba"
            for shuffle in _SHUFFLES:
                await _case(
                    f"order_{tag}__{shuffle}",
                    generation=generation,
                    users=("user_a", "user_b"),
                    script=_two_user(order, shuffle, terminal_before=False),
                )
                generation += 1
        for shuffle in _SHUFFLES:
            await _case(
                f"terminal_before__{shuffle}",
                generation=generation,
                users=("user_a", "user_b"),
                script=_two_user(("user_a", "user_b"), shuffle, terminal_before=True),
            )
            generation += 1

        # ═══ 判别性场景 ════════════════════════════════════════════════════
        async def _discriminating(ctx):
            openings = []
            for u in ("user_a", "user_b", "user_c", "user_d"):
                openings.append(await _do_close(ctx, u, tag="disc"))
            rows = await _read_intents(ctx)
            if len(rows) != 4:
                raise _HarnessError(f"判别性场景需要 4 条 intent，实得 {len(rows)}")
            global_max_id = max(rows, key=lambda r: str(r["id"]))["id"]
            middles = [rows[1], rows[2]]  # 既非首插入也非末插入
            candidates = [r for r in middles if r["id"] != global_max_id]
            if not candidates:  # pragma: no cover - 只有一行能是全局最大 id
                raise _HarnessError("两个中间 intent 不可能同时是全局最大 id")
            target = candidates[0]
            anchor = datetime(2026, 4, 1, 9, 0, 0, tzinfo=timezone.utc)
            others = [r for r in rows if r["id"] != target["id"]]
            # target 拿最高 sequence + **最早** created_at；其余按顺序拿更晚的时间
            await _assign_sequences(
                ctx,
                {target["id"]: 99, **{r["id"]: i for i, r in enumerate(others, start=1)}},
            )
            async with Session() as s:
                await s.execute(
                    sa.update(WorkpaperOoCloseIntent)
                    .where(WorkpaperOoCloseIntent.id == target["id"])
                    .values(created_at=anchor)
                )
                for idx, row in enumerate(others, start=1):
                    await s.execute(
                        sa.update(WorkpaperOoCloseIntent)
                        .where(WorkpaperOoCloseIntent.id == row["id"])
                        .values(created_at=anchor + timedelta(minutes=10 * idx))
                    )
                await s.commit()
            await _terminate_predecessors(ctx)
            first = await _do_reconcile(ctx)
            second = await _do_reconcile(ctx)
            return {
                "target_intent": str(target["id"]),
                "target_is_first_inserted": target["id"] == rows[0]["id"],
                "target_is_last_inserted": target["id"] == rows[-1]["id"],
                "target_is_global_max_id": target["id"] == global_max_id,
                "leader_equals_target": (
                    str(first["leader_intent_id"]) == str(target["id"])
                ),
                "reentrant_same_leader": (
                    first["leader_intent_id"] == second["leader_intent_id"]
                ),
                "capture_created": first["capture_created"],
                "reentrant_capture_created": second["capture_created"],
                "predecessors": sum(1 for o in openings if o["has_predecessor"]),
            }

        await _case(
            _DISCRIMINATING,
            generation=generation,
            users=("user_a", "user_b", "user_c", "user_d"),
            script=_discriminating,
        )
        generation += 1

        # ═══ id tiebreak 在真库里为何不可达 ════════════════════════════════
        #
        # 首轮本想造两条同 `intent_sequence` 的 intent 来在真库上证明 comparator 的
        # `str(i.id)` 那一项，实测被 V151 的
        # `uq_wpoci_sequence UNIQUE (room_id, generation, intent_sequence)` 拒绝。
        # 结论不是「绕过约束」而是**把结论记下来**：id tiebreak 在真实 schema 下
        # 不可达，它是防御性确定性，只能由离线合成输入证明
        # （`test_task24_close_intent.py::test_equal_sequence_falls_back_to_highest_id`）。
        # 这里改为**正面断言该约束确实在挡**——否则上面那句话哪天就悄悄过期了。
        try:
            ctx = await _make_room(generation=generation, users=("user_a", "user_b"))
            generation += 1
            await _do_close(ctx, "user_a", tag="uniq")
            await _do_close(ctx, "user_b", tag="uniq")
            rows = await _read_intents(ctx)
            rejected: dict[str, Any] = {"attempted": len(rows)}
            async with Session() as s:
                try:
                    await s.execute(
                        sa.update(WorkpaperOoCloseIntent)
                        .where(WorkpaperOoCloseIntent.id == rows[0]["id"])
                        .values(intent_sequence=rows[1]["sequence"])
                    )
                    await s.commit()
                    rejected["rejected"] = False
                    rejected["constraint"] = None
                except Exception as exc:  # noqa: BLE001 - 归因入快照
                    await s.rollback()
                    text = str(getattr(exc, "orig", exc))
                    rejected["rejected"] = True
                    rejected["constraint"] = (
                        "uq_wpoci_sequence" if "uq_wpoci_sequence" in text else text[:200]
                    )
            snap["sequence_uniqueness"] = rejected
        except Exception as exc:  # noqa: BLE001
            _phase_failed("sequence_uniqueness", exc)

        # ═══ leader 在 promotion 前被撤销 / 过期 ⇒ 合法 successor ══════════
        def _leader_disqualified(mode: str):
            async def _script(ctx):
                # A、B 关闭；C 保持 active ⇒ leader 选出但不 promote
                await _do_close(ctx, "user_a", tag=f"disq-{mode}")
                await _do_close(ctx, "user_b", tag=f"disq-{mode}")
                first = await _do_reconcile(ctx)
                repeat = await _do_reconcile(ctx)
                rows = await _read_intents(ctx)
                leader_row = next(
                    r for r in rows if r["id"] == first["leader_intent_id"]
                )
                # 直接 UPDATE participant 而不是 RoomService.revoke_participant：
                # 后者会提升 write fence，于此后 confirmation 全部作废 —— 那是
                # Property 15 的判据（Task 21 已覆盖），会把本场景失败原因混在一起。
                now = datetime.now(timezone.utc)
                values: dict[str, Any] = (
                    {"state": ParticipantState.revoked.value, "revoked_at": now}
                    if mode == "revoked"
                    else {"expires_at": now - timedelta(seconds=5)}
                )
                async with Session() as s:
                    await s.execute(
                        sa.update(WorkpaperOoParticipant)
                        .where(
                            WorkpaperOoParticipant.id == leader_row["participant_id"]
                        )
                        .values(**values)
                    )
                    await s.execute(
                        sa.update(WorkpaperOoParticipant)
                        .where(
                            WorkpaperOoParticipant.id == ctx["participants"]["user_c"]
                        )
                        .values(state=ParticipantState.left.value, left_at=now)
                    )
                    await s.commit()
                await _terminate_predecessors(ctx)
                after = await _do_reconcile(ctx)
                again = await _do_reconcile(ctx)
                return {
                    "mode": mode,
                    "same_snapshot_same_leader": (
                        first["leader_intent_id"] == repeat["leader_intent_id"]
                    ),
                    # 同 snapshot 重试的**前置事实**：两次都真的跑了 comparator
                    # （没被 promoted 短路）、每次都有 ≥2 条 eligible 可选、
                    # epoch/digest 一字未动、且此刻零 capture。
                    "first_eligible_count": first["eligible_count"],
                    "repeat_eligible_count": repeat["eligible_count"],
                    "first_promoted_short_circuit": first["promoted_short_circuit"],
                    "repeat_promoted_short_circuit": repeat["promoted_short_circuit"],
                    "same_snapshot_same_epoch": (
                        first["eligibility_epoch"] == repeat["eligibility_epoch"]
                    ),
                    "same_snapshot_same_digest": (
                        first["eligibility_digest"] == repeat["eligibility_digest"]
                    ),
                    "same_snapshot_open_captures": repeat["open_captures"],
                    "leader_before": str(first["leader_intent_id"]),
                    "leader_after": str(after["leader_intent_id"]),
                    "successor_differs": (
                        after["leader_intent_id"] != first["leader_intent_id"]
                    ),
                    "stale_reported": after["stale_reported"],
                    "eligibility_bumped": (
                        after["eligibility_epoch"] > first["eligibility_epoch"]
                    ),
                    "successor_capture_created": after["capture_created"],
                    "no_successor": after["no_successor"],
                    "reentrant_capture_created": again["capture_created"],
                }

            return _script

        for mode in ("revoked", "expired"):
            await _case(
                f"leader_disqualified__{mode}",
                generation=generation,
                users=("user_a", "user_b", "user_c"),
                script=_leader_disqualified(mode),
            )
            generation += 1

        # ═══ 无 successor ⇒ supersede + recovery_required + 零 capture ═════
        async def _no_successor(ctx):
            await _do_close(ctx, "user_a", tag="nosucc")
            first = await _do_reconcile(ctx)
            now = datetime.now(timezone.utc)
            async with Session() as s:
                await s.execute(
                    sa.update(WorkpaperOoParticipant)
                    .where(WorkpaperOoParticipant.id == ctx["participants"]["user_a"])
                    .values(state=ParticipantState.revoked.value, revoked_at=now)
                )
                await s.execute(
                    sa.update(WorkpaperOoParticipant)
                    .where(WorkpaperOoParticipant.id == ctx["participants"]["user_b"])
                    .values(state=ParticipantState.left.value, left_at=now)
                )
                await s.commit()
            await _terminate_predecessors(ctx)
            after = await _do_reconcile(ctx)
            again = await _do_reconcile(ctx)
            return {
                "leader_before": str(first["leader_intent_id"]),
                "no_successor": after["no_successor"],
                "capture_created": after["capture_created"],
                "live_after": after["live_intents"],
                "stale_reported": after["stale_reported"],
                "reentrant_no_successor": again["no_successor"],
                "reentrant_capture_created": again["capture_created"],
                "reentrant_live": again["live_intents"],
            }

        await _case(
            "no_successor",
            generation=generation,
            users=("user_a", "user_b"),
            script=_no_successor,
        )
        generation += 1

        # ═══ 授权：Command Service 之前拒绝，且零 intent / 零出站 ═════════
        try:
            cases: dict[str, Any] = {}
            probes: tuple[tuple[str, dict[str, Any] | None, type[Exception]], ...] = (
                (
                    "revoked_participant",
                    {
                        "state": ParticipantState.revoked.value,
                        "revoked_at": datetime.now(timezone.utc),
                    },
                    ParticipantNotWritableError,
                ),
                (
                    "expired_lease",
                    {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=5)},
                    ParticipantNotWritableError,
                ),
                ("view_only", {"mode": ParticipantMode.view.value}, ParticipantNotWritableError),
                ("refresh_required", None, RoomNotWritableError),
                ("write_fence_bumped", None, WriteFenceStaleError),
            )
            for label, mutate, expected in probes:
                ctx = await _make_room(
                    generation=generation, users=("user_a", "user_b")
                )
                generation += 1
                async with Session() as s:
                    if mutate is not None:
                        await s.execute(
                            sa.update(WorkpaperOoParticipant)
                            .where(
                                WorkpaperOoParticipant.id
                                == ctx["participants"]["user_a"]
                            )
                            .values(**mutate)
                        )
                    elif label == "refresh_required":
                        _repo, rooms, _svc = _wire(s)
                        await rooms.mark_refresh_required(
                            room_id=ctx["room_id"], reason="task24-probe"
                        )
                    else:
                        await s.execute(
                            sa.update(WorkpaperOoRoom)
                            .where(WorkpaperOoRoom.id == ctx["room_id"])
                            .values(
                                write_fence_epoch=WorkpaperOoRoom.write_fence_epoch + 1
                            )
                        )
                    await s.commit()
                calls_before = len(transport.calls)
                try:
                    await _do_close(ctx, "user_a", tag=f"auth-{label}")
                    cases[label] = {"refused": False}
                except Exception as exc:  # noqa: BLE001 - 分类入快照
                    cases[label] = {
                        "refused": True,
                        "type": type(exc).__name__,
                        "expected_family": isinstance(exc, expected),
                        "dispatched": len(transport.calls) - calls_before,
                        "intents": len(await _read_intents(ctx)),
                    }
            snap["authorization"] = cases
        except Exception as exc:  # noqa: BLE001
            _phase_failed("authorization", exc)

        # ═══ 出站形态 ═════════════════════════════════════════════════════
        try:
            ctx = await _make_room(generation=generation, users=("user_a", "user_b"))
            generation += 1
            before = len(transport.calls)
            opened = await _do_close(ctx, "user_a", tag="dispatch")
            sent = transport.calls[before:]
            rows = await _read_intents(ctx)
            intent = next(r for r in rows if r["id"] == opened["intent_id"])
            async with Session() as s:
                request = (
                    await s.execute(
                        sa.select(WorkpaperForcesaveRequest).where(
                            WorkpaperForcesaveRequest.id
                            == opened["predecessor_request_id"]
                        )
                    )
                ).scalar_one()
                request_kind = request.kind
                request_id = request.id
                # intent 的**当前** state 只是 timeline 的投影（AC 5.10）：
                # `ordinary_forcesaving` 之后 reconciler 会把 leader 推到
                # `leader_ready → waiting_barrier`，所以「建过 predecessor」这件事
                # 只能在 append-only 事件里查，不能靠当前 state。
                event_states = [
                    r[0]
                    for r in (
                        await s.execute(
                            sa.select(WorkpaperOoCloseIntentEvent.to_state)
                            .where(
                                WorkpaperOoCloseIntentEvent.intent_id
                                == opened["intent_id"]
                            )
                            .order_by(WorkpaperOoCloseIntentEvent.sequence_no.asc())
                        )
                    ).all()
                ]
            snap["dispatch"] = {
                "predecessor_dispatched": len(sent),
                "doc_key_sent": sent[0].body["key"] if sent else None,
                "room_doc_key": ctx["doc_key"],
                "request_id_in_userdata": (
                    str(request_id) in sent[0].body["userdata"] if sent else False
                ),
                "command": sent[0].body["c"] if sent else None,
                "outcome": opened["predecessor_outcome"],
                "accepted_only": opened["predecessor_accepted_only"],
                "intent_state_after_predecessor": intent["state"],
                "intent_event_states": event_states,
                "intent_predecessor_link": str(intent["predecessor"])
                if intent["predecessor"]
                else None,
                "predecessor_request_id": str(request_id),
                "predecessor_kind": request_kind,
                "shell_application_id": opened["shell_application_id"],
                "application_count_at_accepted": opened["application_count"],
                "timeout_seconds": sent[0].timeout_seconds if sent else None,
                "auth_header_present": (
                    bool(sent[0].headers.get(policy.jwt_header)) if sent else False
                ),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("dispatch", exc)

        # ═══ 真并发：两个 participant 同时 close，仍恰一条 capture ════════
        try:
            race_ctx = await _make_room(
                generation=generation, users=("user_a", "user_b")
            )
            generation += 1
            barrier = asyncio.Barrier(2)
            results: list[dict[str, Any]] = []

            async def _racer(user: str) -> None:
                rec: dict[str, Any] = {"user": user}
                async with Session() as rs:
                    try:
                        rec["backend_pid"] = int(
                            (
                                await rs.execute(sa.text("SELECT pg_backend_pid()"))
                            ).scalar_one()
                        )
                        # 🔴 `t_ready` 记在 `barrier.wait()` **之前**：判据用
                        # `max(t_ready) <= min(t_call)`。用 `t_barrier`（wait 返回后）
                        # 会偶发红 —— barrier 释放后各任务恢复顺序任意，A 记 t_barrier
                        # 完全可能晚于 B 记 t_call。Task 23 实测踩过，会成为 CI 重试。
                        rec["t_ready"] = time.monotonic()
                        await barrier.wait()
                        rec["t_call"] = time.monotonic()
                        _repo, _rooms, rsvc = _wire(rs)
                        opened = await rsvc.open_close_intent(
                            scope,
                            room_id=race_ctx["room_id"],
                            participant_id=race_ctx["participants"][user],
                            idempotency_key=f"race-{user}",
                            client_edit_epoch=3,
                            adapter_build_digest=adapter_digest,
                            contributor_snapshot_digest=contrib_digest,
                            contributor_user_ids=[ids[user]],
                            created_by=ids[user],
                            actor_id=ids[user],
                        )
                        rec["intent_sequence"] = opened.intent_sequence
                        rec["predecessor"] = opened.has_predecessor
                        rec["capture_created"] = opened.reconcile.capture_created
                        await rs.commit()
                        rec["committed"] = True
                    except Exception as exc:  # noqa: BLE001
                        rec["committed"] = False
                        rec["error"] = _err(exc)
                        await rs.rollback()
                results.append(rec)

            await asyncio.gather(*(_racer(u) for u in ("user_a", "user_b")))
            await _terminate_predecessors(race_ctx)
            final = await _do_reconcile(race_ctx)
            measured = await _measure(race_ctx)
            snap["concurrency"] = {
                "racers": results,
                "distinct_backend_pids": len(
                    {r["backend_pid"] for r in results if "backend_pid" in r}
                ),
                "ready_count": sum(1 for r in results if "t_ready" in r),
                "max_t_ready": max(
                    (r["t_ready"] for r in results if "t_ready" in r), default=0.0
                ),
                "min_t_call": min(
                    (r["t_call"] for r in results if "t_call" in r), default=0.0
                ),
                "all_committed": all(r.get("committed") for r in results),
                "distinct_sequences": len(
                    {r["intent_sequence"] for r in results if "intent_sequence" in r}
                ),
                "final_capture_created": final["capture_created"],
                **measured,
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("concurrency", exc)

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
# 采集自身的完整性
# ═══════════════════════════════════════════════════════════════════════════


def test_real_postgres_and_v151_applied(snap: dict[str, Any]) -> None:
    assert "PostgreSQL" in str(snap["server_version"]), snap["server_version"]
    assert snap["apply_errors"] == [], snap["apply_errors"]


def test_no_phase_crashed_during_collection(snap: dict[str, Any]) -> None:
    """采集阶段零异常。

    与「异常记录不穿透」配对：不穿透保证 `-rf` 能列出预期失败项，本条保证
    「静默少跑了一个场景」不会被当成通过。
    """
    assert snap["harness_errors"] == {}, snap["harness_errors"]


def test_every_scenario_produced_a_measurement(snap: dict[str, Any]) -> None:
    expected = (
        {f"single__{s}" for s in _SHUFFLES}
        | {f"order_ab__{s}" for s in _SHUFFLES}
        | {f"order_ba__{s}" for s in _SHUFFLES}
        | {f"terminal_before__{s}" for s in _SHUFFLES}
        | {_DISCRIMINATING, "no_successor"}
        | {f"leader_disqualified__{m}" for m in ("revoked", "expired")}
    )
    assert set(snap["close"]) == expected, set(snap["close"]) ^ expected
    for name, rec in snap["close"].items():
        assert "error" not in rec, (name, rec.get("error"))


# ═══════════════════════════════════════════════════════════════════════════
# exactly-one：每个场景逐个数 capture
# ═══════════════════════════════════════════════════════════════════════════

_CAPTURE_SCENARIOS = (
    [f"single__{s}" for s in _SHUFFLES]
    + [f"order_ab__{s}" for s in _SHUFFLES]
    + [f"order_ba__{s}" for s in _SHUFFLES]
    + [f"terminal_before__{s}" for s in _SHUFFLES]
    + [_DISCRIMINATING]
)

#: 扰动落在 promotion **之前**的场景 —— 只有这些能用「leader 必须是最高
#: `(intent_sequence, id)`」当判据。`terminal_before__*` 的 promotion 发生在第二人
#: 关闭当场，扰动必然在其后，那批改用「promotion 后不得改选」判据。
_PRE_PROMOTION_SCENARIOS = (
    [f"single__{s}" for s in _SHUFFLES]
    + [f"order_ab__{s}" for s in _SHUFFLES]
    + [f"order_ba__{s}" for s in _SHUFFLES]
    + [_DISCRIMINATING]
)


@pytest.mark.parametrize("name", _CAPTURE_SCENARIOS, ids=_CAPTURE_SCENARIOS)
def test_capture_scenario_yields_exactly_one_close_capture(
    snap: dict[str, Any], name: str
) -> None:
    """合法资格场景最终**恰一条** close-capture。任何 >1 均失败（AC 4.10）。

    `all_captures` 与 `open_captures` 都断言 == 1：partial unique 只管 open 状态，
    「造过第二条又终结掉」在只看 open 时是隐形的。
    """
    rec = snap["close"][name]
    assert rec["open_captures"] == 1, rec
    assert rec["all_captures"] == 1, rec
    assert rec["promoted_intents"] == 1, rec
    assert rec["promoted_with_request"] == 1, rec


@pytest.mark.parametrize("name", _PRE_PROMOTION_SCENARIOS, ids=_PRE_PROMOTION_SCENARIOS)
def test_leader_is_the_highest_sequence_id_in_every_scenario(
    snap: dict[str, Any], name: str
) -> None:
    """leader 必须是最高 `(intent_sequence, id)` —— 由测试**独立复算**。

    独立复算是必需的：只断言「有一个 leader」时，把 comparator 改成 min 或
    `created_at` 都仍然会选出**某个** leader，全部断言照样通过（Task 10 的注释里
    记着同一条教训）。
    """
    rec = snap["close"][name]
    assert rec["leader_is_highest_sequence_id"] is True, rec
    assert rec["leader_intent"] == rec["expected_leader"], rec


_DISCRIMINATING_CASES = [
    f"{k}__{s}" for k in ("order_ab", "order_ba") for s in _DISCRIMINATING_SHUFFLES
]


@pytest.mark.parametrize("name", _DISCRIMINATING_CASES, ids=_DISCRIMINATING_CASES)
def test_created_at_does_not_decide_the_leader(snap: dict[str, Any], name: str) -> None:
    """判别性断言：这些扰动下「最高 sequence」与「最晚 `created_at`」是**不同**两条。

    先断言判别性本身（`highest_seq_equals_latest_created is False`），再断言 leader
    选的是前者。少了第一句，这条测试在扰动失效时会静默退化成恒真 —— 那正是
    「守卫把错值当基线」的近亲。
    """
    rec = snap["close"][name]
    assert rec["intent_count"] >= 2, rec
    assert rec["highest_seq_equals_latest_created"] is False, (
        "扰动没有产生判别性输入：最高 sequence 恰好也是最晚 created_at，"
        "此时 comparator 改用 created_at 也测不出来",
        rec,
    )
    assert rec["leader_is_latest_created_at"] is False, rec
    assert rec["leader_is_highest_sequence_id"] is True, rec


def test_deterministic_leader_is_neither_first_inserted_nor_latest_created_at(
    snap: dict[str, Any],
) -> None:
    """🔴 最强判别性场景：四种错误 comparator **全部**会选错人。

    断言链条：target 既不是第一个插入、也不是最后一个插入、也不是全局最大 id，
    而且 `created_at` **最早**；leader 仍然是 target。于是「按插入序取首」
    「按插入序取尾」「按 id」「按 created_at」四种错法各自确定性地选错 ——
    不依赖随机 id 碰运气。
    """
    rec = snap["close"][_DISCRIMINATING]
    assert rec["intent_count"] == 4, rec
    assert rec["target_is_first_inserted"] is False, rec
    assert rec["target_is_last_inserted"] is False, rec
    assert rec["target_is_global_max_id"] is False, rec
    assert rec["leader_is_latest_created_at"] is False, rec
    assert rec["highest_seq_equals_latest_created"] is False, rec
    assert rec["leader_equals_target"] is True, rec
    assert rec["leader_sequence"] == 99, rec
    assert rec["open_captures"] == 1 and rec["all_captures"] == 1, rec
    assert rec["reentrant_same_leader"] is True, rec
    assert rec["reentrant_capture_created"] is False, rec


def test_database_forbids_equal_intent_sequences_so_id_tiebreak_is_defensive_only(
    snap: dict[str, Any],
) -> None:
    """真库拒绝同 `(room, generation, intent_sequence)` ⇒ id tiebreak 不可达。

    这条记录的是一个**实测结论**而不是一个能力：首轮试图在真库上构造两条同
    `intent_sequence` 的 intent 来证明 comparator 的 `str(i.id)` 那一项，被 V151 的
    `uq_wpoci_sequence` 直接拒绝。所以：

    * comparator 里的 id tiebreak 是**防御性确定性**，真实 schema 下走不到；
    * 它只能由离线合成输入证明（`test_task24_close_intent.py::
      test_equal_sequence_falls_back_to_highest_id`）；
    * 而「不可达」这个前提本身必须被断言 —— 否则哪天约束被去掉，上面两句话就
      悄悄过期，而没有任何守卫会红。
    """
    rec = snap["sequence_uniqueness"]
    assert rec["attempted"] == 2, rec
    assert rec["rejected"] is True, rec
    assert rec["constraint"] == "uq_wpoci_sequence", rec


# ═══════════════════════════════════════════════════════════════════════════
# 关闭顺序 / barrier / 重入
# ═══════════════════════════════════════════════════════════════════════════

_TWO_USER_CASES = [f"order_ab__{s}" for s in _SHUFFLES] + [
    f"order_ba__{s}" for s in _SHUFFLES
]


@pytest.mark.parametrize("name", _TWO_USER_CASES, ids=_TWO_USER_CASES)
def test_first_closer_gets_a_predecessor_and_last_closer_does_not(
    snap: dict[str, Any], name: str
) -> None:
    """先关闭者建普通 forcesave predecessor；最后关闭者不建（它的 capture 就是保存）。

    同时断言 `predecessor_links == 1` —— `ordinary_forcesave_request_id` 必须真的
    被写上。该列此前**没有任何生产代码写过**，只断言「建了一条 forcesave」无法
    证明 intent 与它的 predecessor 建立了可审计对应关系。
    """
    rec = snap["close"][name]
    assert rec["first_predecessor"] is True, rec
    assert rec["second_predecessor"] is False, rec
    assert rec["predecessor_links"] == 1, rec


_ORDER_AB_CASES = [f"order_ab__{s}" for s in _SHUFFLES]
_TERMINAL_BEFORE_CASES = [f"terminal_before__{s}" for s in _SHUFFLES]


@pytest.mark.parametrize("name", _ORDER_AB_CASES, ids=_ORDER_AB_CASES)
def test_no_capture_before_predecessors_are_terminal(
    snap: dict[str, Any], name: str
) -> None:
    """B 在 A 的 predecessor 仍未终结时关闭 ⇒ 此刻**零** capture。"""
    rec = snap["close"][name]
    assert rec["terminal_before_second_close"] is False, rec
    assert rec["captures_at_mid"] == 0, rec
    assert rec["shuffle_pre_promotion"] is True, rec
    assert rec["final_capture_created"] is True, rec


@pytest.mark.parametrize("name", _TERMINAL_BEFORE_CASES, ids=_TERMINAL_BEFORE_CASES)
def test_capture_is_created_when_predecessor_terminal_precedes_second_close(
    snap: dict[str, Any], name: str
) -> None:
    """A 的 predecessor 先终结、B 再关闭 ⇒ B 关闭当场即可提升 leader。"""
    rec = snap["close"][name]
    assert rec["terminal_before_second_close"] is True, rec
    assert rec["captures_at_mid"] == 1, rec
    assert rec["shuffle_pre_promotion"] is False, rec
    assert rec["open_captures"] == 1 and rec["all_captures"] == 1, rec


@pytest.mark.parametrize("name", _TERMINAL_BEFORE_CASES, ids=_TERMINAL_BEFORE_CASES)
def test_perturbation_after_promotion_never_changes_the_leader(
    snap: dict[str, Any], name: str
) -> None:
    """promotion **之后**扰动 `created_at` / `intent_sequence` ⇒ leader 纹丝不动。

    AC 10.10：leader 已 promotion 后授权失效只能走 recovery，**不得**接任再造第二
    capture。把「已 promoted 即幂等短路」写成可断言事实：即使把另一条 intent 的
    sequence 抬到最高，promoted 那条仍是 leader，且不产生第二条 capture。

    这与 :func:`test_leader_is_the_highest_sequence_id_in_every_scenario` 不矛盾 ——
    后者只覆盖 promotion **之前**的扰动。两条一起才把 comparator 与幂等短路的
    分界线钉住。
    """
    rec = snap["close"][name]
    assert rec["shuffle_pre_promotion"] is False, rec
    assert rec["leader_unchanged_by_shuffle"] is True, rec
    assert rec["reentrant_capture_created"] is False, rec
    assert rec["promoted_intents"] == 1, rec
    assert rec["open_captures"] == 1 and rec["all_captures"] == 1, rec


_REENTRANT_CASES = (
    _TWO_USER_CASES + _TERMINAL_BEFORE_CASES + [f"single__{s}" for s in _SHUFFLES]
)


@pytest.mark.parametrize("name", _REENTRANT_CASES, ids=_REENTRANT_CASES)
def test_reconciler_is_reentrant_without_a_second_capture(
    snap: dict[str, Any], name: str
) -> None:
    """重入 reconcile 不得再造 capture，也不得换 leader。"""
    rec = snap["close"][name]
    assert rec["reentrant_capture_created"] is False, rec
    assert rec["reentrant_same_leader"] is True, rec
    assert rec["open_captures"] == 1, rec


def test_single_close_needs_no_predecessor(snap: dict[str, Any]) -> None:
    for shuffle in _SHUFFLES:
        rec = snap["close"][f"single__{shuffle}"]
        assert rec["remaining_active_at_close"] == 0, rec
        assert rec["predecessor_created"] is False, rec
        assert rec["first_capture_created"] is True, rec
        assert rec["predecessor_links"] == 0, rec


# ═══════════════════════════════════════════════════════════════════════════
# leader 失格 ⇒ authorization_stale + successor
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("mode", ["revoked", "expired"], ids=["revoked", "expired"])
def test_leader_disqualified_before_promotion_yields_a_legitimate_successor(
    snap: dict[str, Any], mode: str
) -> None:
    """promotion 前 leader 失格 ⇒ 写 `authorization_stale`、推进 epoch、选 successor，
    最终仍**恰一条** capture。

    撤销与过期各一条用例：两者是 :func:`~.close_intent.intent_is_eligible` 的两个
    独立子判据，合成一条时删掉任一个都会被另一个遮蔽。
    """
    rec = snap["close"][f"leader_disqualified__{mode}"]
    assert rec["successor_differs"] is True, rec
    assert rec["leader_before"] in rec["stale_reported"], rec
    assert len(rec["stale_reported"]) == 1, rec
    assert rec["eligibility_bumped"] is True, rec
    assert rec["no_successor"] is False, rec
    assert rec["successor_capture_created"] is True, rec
    assert rec["reentrant_capture_created"] is False, rec
    assert rec["open_captures"] == 1 and rec["all_captures"] == 1, rec
    assert rec["authorization_stale_events"] == 1, rec
    assert "authorization_stale" in rec["intent_states"], rec


@pytest.mark.parametrize("mode", ["revoked", "expired"], ids=["revoked", "expired"])
def test_repeat_reconcile_in_one_eligibility_snapshot_keeps_the_leader(
    snap: dict[str, Any], mode: str
) -> None:
    """🔴 Task 24 正文点名：同一 eligibility snapshot 内重试**不得换 leader**。

    这条与 :func:`test_reconciler_is_reentrant_without_a_second_capture` 不重复。
    后者的第二次 reconcile 发生在 promotion **之后** —— 那时 `already_promoted`
    幂等短路直接返回，comparator 一次都没执行，所以它证明的是「短路有效」而不是
    「comparator 稳定」。本条刻意停在 promotion **之前**（第三个 participant 仍
    `active` ⇒ barrier 不放行），于是两次 reconcile 都真的走到 comparator。

    断言顺序是判据设计的一部分：**先证明路径真的跑了，再断言结论**。

    * `promoted_short_circuit is False` ×2 —— 没走幂等短路；
    * `eligible_count >= 2` ×2 —— `max()` 面对的是真选择。只剩一条时「leader 不变」
      恒真，断言会静默退化成同义反复；
    * `open_captures == 0` —— 确认仍在 promotion 之前；
    * epoch / digest 逐字相同 —— 这才叫「同一个 snapshot」，否则命题的前提不成立。

    Task 23 实测过一个反例：某并发场景通过了每一条断言，而被测代码路径从未执行，
    因为胜者恰好是「无论如何都会赢」的那一条。上面四条前置事实就是为了让这种
    「碰巧通过」在本条上不可能发生。
    """
    rec = snap["close"][f"leader_disqualified__{mode}"]
    assert rec["first_promoted_short_circuit"] is False, rec
    assert rec["repeat_promoted_short_circuit"] is False, rec
    assert rec["first_eligible_count"] >= 2, rec
    assert rec["repeat_eligible_count"] >= 2, rec
    assert rec["same_snapshot_open_captures"] == 0, rec
    assert rec["same_snapshot_same_epoch"] is True, rec
    assert rec["same_snapshot_same_digest"] is True, rec
    assert rec["same_snapshot_same_leader"] is True, rec


# ═══════════════════════════════════════════════════════════════════════════
# 无 successor ⇒ supersede + recovery_required + 零 capture + 不永久阻塞
# ═══════════════════════════════════════════════════════════════════════════


def test_no_successor_supersedes_generation_with_zero_captures(
    snap: dict[str, Any],
) -> None:
    rec = snap["close"]["no_successor"]
    assert rec["no_successor"] is True, rec
    assert rec["capture_created"] is False, rec
    assert rec["open_captures"] == 0 and rec["all_captures"] == 0, rec
    assert rec["room_superseded"] is True, rec
    assert rec["room_state"] == "recovery_required", rec


def test_no_successor_leaves_no_live_intent_so_it_is_never_permanently_blocked(
    snap: dict[str, Any],
) -> None:
    """零 capture 路径必须**显式终结**每条 intent（AC 4.10「不得永久 blocked」）。

    partial unique 对「一条 capture 都没有」毫无意见，所以「零 capture 且卡死」
    只能靠这条抓 —— 它与上面的 `open_captures == 0` 合起来才是完整的
    「不永久阻塞、也不第二条」。
    """
    rec = snap["close"]["no_successor"]
    assert rec["live_after"] == 0, rec
    assert rec["live_intents"] == 0, rec
    assert rec["reentrant_live"] == 0, rec
    assert rec["reentrant_no_successor"] is True, rec
    assert rec["reentrant_capture_created"] is False, rec
    assert set(rec["intent_states"]) <= _TERMINAL_INTENT_STATES, rec


def test_no_successor_records_the_stale_audit_before_superseding(
    snap: dict[str, Any],
) -> None:
    """失格的 leader 必须留下 `authorization_stale` 审计，而不是被直接 supersede。"""
    rec = snap["close"]["no_successor"]
    assert rec["leader_before"] in rec["stale_reported"], rec
    assert rec["authorization_stale_events"] >= 1, rec


# ═══════════════════════════════════════════════════════════════════════════
# 授权：Command Service 之前拒绝，且零 intent / 零出站
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("case", _AUTH_CASES, ids=_AUTH_CASES)
def test_unauthorized_close_is_refused_before_any_command_service_call(
    snap: dict[str, Any], case: str
) -> None:
    """撤销/过期/只读/refresh-required/fence 变化 ⇒ 出站前拒，且**不留 intent**。

    `dispatched == 0` 与 `intents == 0` 缺一不可：只断言抛异常无法区分「拒在出站前」
    与「建了 intent、发了命令、之后才失败」，而 AC 4.7 管的正是前者。
    """
    rec = snap["authorization"][case]
    assert rec["refused"] is True, rec
    assert rec["expected_family"] is True, rec
    assert rec["dispatched"] == 0, rec
    assert rec["intents"] == 0, rec


# ═══════════════════════════════════════════════════════════════════════════
# 出站形态
# ═══════════════════════════════════════════════════════════════════════════


def test_predecessor_dispatch_carries_room_doc_key_and_frozen_request_id(
    snap: dict[str, Any],
) -> None:
    rec = snap["dispatch"]
    assert rec["predecessor_dispatched"] == 1, rec
    assert rec["command"] == "forcesave", rec
    assert rec["doc_key_sent"] == rec["room_doc_key"], rec
    assert rec["request_id_in_userdata"] is True, rec
    assert rec["predecessor_kind"] == "forcesave", rec
    assert rec["timeout_seconds"] == float(snap["policy"]["http_timeout"]), rec
    assert rec["auth_header_present"] is True, rec


def test_accepted_shell_has_no_application_before_dispatch(snap: dict[str, Any]) -> None:
    """Property 12 / P64：accepted 时 shell 的 `application_id` 为空、application 数为 0。"""
    rec = snap["dispatch"]
    assert rec["shell_application_id"] is None, rec
    assert rec["application_count_at_accepted"] == 0, rec
    assert rec["outcome"] == "accepted", rec
    assert rec["accepted_only"] is True, rec


def test_intent_records_its_predecessor_link_and_timeline(snap: dict[str, Any]) -> None:
    """intent 必须写下 predecessor 链接，并在 append-only timeline 留下
    `ordinary_forcesaving`。

    判据落在 **timeline** 而不是当前 state：`ordinary_forcesaving` 之后 reconciler
    会把该 intent 推到 `leader_ready → waiting_barrier`（它是唯一 closer，而另一位
    editor 仍 active），所以当前 state 是 `waiting_barrier`。首轮按当前 state 断言
    `ordinary_forcesaving` 实测失败 —— 那是**断言写错**，不是行为错；current state
    只是 timeline 的投影（AC 5.10）。
    """
    rec = snap["dispatch"]
    assert rec["intent_predecessor_link"] == rec["predecessor_request_id"], rec
    assert rec["intent_event_states"][0] == "created", rec
    assert "ordinary_forcesaving" in rec["intent_event_states"], rec
    assert rec["intent_state_after_predecessor"] == "waiting_barrier", rec
    assert rec["intent_event_states"][-1] == "waiting_barrier", rec


# ═══════════════════════════════════════════════════════════════════════════
# 真并发
# ═══════════════════════════════════════════════════════════════════════════


def test_concurrent_closes_really_overlapped(snap: dict[str, Any]) -> None:
    """并发是**实测**而不是自述：不同 backend pid + 全部到达 barrier + 时刻重叠。

    `ready_count == 2` 不冗余：只比时间戳时，若某任务在 `t_ready` 之前就抛异常退出，
    `max()` 会在更小的集合上取到一个「看起来合规」的值。
    """
    race = snap["concurrency"]
    assert race["distinct_backend_pids"] == 2, race
    assert race["ready_count"] == 2, race
    assert race["max_t_ready"] <= race["min_t_call"], race


def test_concurrent_closes_still_yield_exactly_one_capture(snap: dict[str, Any]) -> None:
    """两个 participant 同时 close ⇒ 仍恰一条 capture、两条 intent 各自不同 sequence。"""
    race = snap["concurrency"]
    assert race["all_committed"] is True, [r.get("error") for r in race["racers"]]
    assert race["intent_count"] == 2, race
    assert race["distinct_sequences"] == 2, (
        "两条 intent 拿到同一个 intent_sequence —— room row lock 没有把 max+1 串行化",
        race,
    )
    assert race["open_captures"] == 1, race
    assert race["all_captures"] == 1, race
    assert race["leader_is_highest_sequence_id"] is True, race


# ═══════════════════════════════════════════════════════════════════════════
# 变异接口登记（mutation interface registry）
# ═══════════════════════════════════════════════════════════════════════════
#
# `backend/scripts/diagnose/mutate_task24_close_intent_guards.py` 的 `want=` 直接引用
# 下列 nodeid。**被变异引用的 parametrized nodeid 就是接口**：改动 `_SHUFFLES` 的取值、
# 增删场景都会让 `want` 指空并被判 WRONG-TEST。
#
# 这份清单同时让变异脚本的 `--list` 能定位到目标 —— `_mutation_kit` 只能在守卫文件的
# **文本**里查 needle，而这些 id 是由 `_SHUFFLES` 拼出来的，不以完整形式出现在源码里。
#
# _MUTATION_INTERFACE:
#   test_created_at_does_not_decide_the_leader[order_ab__created_reversed]
#   test_reconciler_is_reentrant_without_a_second_capture[order_ab__none]
#   test_capture_scenario_yields_exactly_one_close_capture[order_ab__none]
#   test_capture_scenario_yields_exactly_one_close_capture[single__none]
#   test_first_closer_gets_a_predecessor_and_last_closer_does_not[order_ab__none]
#   test_no_capture_before_predecessors_are_terminal[order_ab__none]
#   test_leader_disqualified_before_promotion_yields_a_legitimate_successor[revoked]
#   test_leader_disqualified_before_promotion_yields_a_legitimate_successor[expired]
#   test_repeat_reconcile_in_one_eligibility_snapshot_keeps_the_leader[revoked]


def test_mutation_interface_nodeids_are_declared() -> None:
    """登记块存在且覆盖变异脚本引用的每一个 parametrized nodeid。

    本文件的收集需要真库 fixture，所以这里只做**静态**核对：登记的每个 id 必须能由
    本文件的场景命名规则拼出来（`{scenario}__{shuffle}` / `[{mode}]`）。真正的
    「nodeid 存在性」由离线守卫那份登记块用 `--collect-only` 核对（那边不需要 DB）。
    """
    src = Path(__file__).read_text(encoding="utf-8")
    declared = [
        line.strip().lstrip("#").strip()
        for line in src.split("# _MUTATION_INTERFACE:", 1)[1].splitlines()
        if line.strip().startswith("#") and "[" in line
    ]
    assert len(declared) == 9, declared
    known_params = (
        {f"{k}__{s}" for k in ("single", "order_ab", "order_ba", "terminal_before") for s in _SHUFFLES}
        | {"revoked", "expired"}
        | {_DISCRIMINATING}
    )
    for nodeid in declared:
        param = nodeid.split("[", 1)[1].rstrip("]")
        assert param in known_params, (nodeid, param)
