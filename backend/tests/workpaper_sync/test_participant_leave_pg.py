"""participant 主动离开：**真库**行为判据（P7 / P8 / P9）。

spec: oo-single-pass-materialize-and-room-leave · Requirement 4.1, 4.2, 4.3, 4.4
Properties: **P7**（只改该 participant，其余 participant 与 room 状态不变）/
**P8**（dirty 时被拒）/ **P9**（幂等：重复调用不产生第二条事件）

═══ 为什么必须真库 ═══

本任务的每一条判据都是「一次 DB 事务里到底改了哪些行的哪些列」：

* P7 要断 room 行**逐列**未变 —— mock 掉 session 就只能断「我没调那个方法」，而
  `room.state = …` 这种就地赋值根本不经过任何方法；
* P9 要断第二次 leave **零写入** —— 判据是真实发出的 UPDATE 语句条数，不是返回值；
* AC 4.4 的 in-flight 门读的是 request 行状态，而 request 行有 6 个 FK，桩不出来。

`DATABASE_URL` 非 PostgreSQL 时**直接失败而不是 skip** —— 与 Task 10 / 21 同约定：
本任务判据就是数据库行为，skip 等于静默抹掉唯一判据。

═══ 隔离与采集写法 ═══

scratch schema `tmp_leave_<hex>`，`search_path` 只含它，结束 `DROP SCHEMA CASCADE`。
全部场景由**一次 `asyncio.run`** 跑完落进快照（module fixture）—— 每个测试各自开 async
会污染共享连接池（第二个测试起 `NoneType has no attribute send`，memory 已记录该坑）。

阶段异常一律**记录而不穿透**：穿透会把整个 module 变成 collection ERROR，而 `-rf` 只列
FAILED 不列 ERROR ⇒ 变异检验看不到任何预期失败项 ⇒ 判 GREEN
（`test_no_phase_crashed_during_collection` 是这条决定的另一半）。

═══ 哪些 setup 刻意用裸 SQL ═══

`room.state` 从 `opening` 推到 `active` 的生产路径是 descriptor confirmation，而
`participant.state` 推到 `closing` 的生产路径是 close intent —— 后者**本身就会改 room**，
拿它当 fixture 就没法再断言「leave 没改 room」。所以这两处 setup 用裸 UPDATE 把世界摆到
待测形态，被测对象仍然是生产代码（`RoomService.leave_participant`）。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
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

_SCHEMA_PREFIX = "tmp_leave_"

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

ENTRY = "xlsx/gt-d4-operating-revenue"

#: room 行上**必须逐列不变**的列（P7）。含 `updated_at`：leave 连时间戳都不该碰。
ROOM_COLUMNS = (
    "state",
    "generation",
    "doc_key",
    "write_fence_epoch",
    "close_barrier_epoch",
    "close_leader_intent_id",
    "close_leader_eligibility_epoch",
    "refresh_required_at",
    "refresh_reason",
    "expires_at",
    "updated_at",
    "superseded_at",
    "latest_request_sequence",
    "latest_durable_sequence",
    "latest_durable_application_id",
    "client_confirmed_base_version_id",
    "last_applied_version_id",
)


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _plain(value: object) -> object:
    """把 UUID / datetime 投影成可比较的字符串，`None` 保持 `None`。

    🔴 不用 `str(value)`：`str(None) == "None"` 是真值，用它做「这一列写上了吗」的判断会
    把「根本没写」判成「写上了」（Task 21 首轮变异实测有一条正是靠这个投影 bug 蒙过守卫）。
    """
    if value is None:
        return None
    if isinstance(value, (int, bool)):
        return value
    return str(value)


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成「无数据」）。"""


class _StatementWitness:
    """数真实发到 PG 的 `UPDATE working_paper_oo_participant` 语句条数。

    P9 的判据是「第二次 leave **零写入**」。返回值层面的 `already_left=True` 只能证明
    「服务端这么说」—— 一个先写一遍再返回 True 的实现照样绿。所以观测面放在
    `before_cursor_execute` 上：它看到的是真的要发给数据库的 SQL。

    观测者自身由 `test_the_statement_witness_can_actually_see_an_update` 反证（第一次
    leave 必须**被它看到**恰 1 条），否则「零条」这个结论在一个坏掉的监听器下恒真。
    """

    def __init__(self) -> None:
        self.updates: list[str] = []
        self.enabled = False

    def hook(self, conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001, D401
        if not self.enabled:
            return
        normalized = " ".join(str(statement).split()).lower()
        if normalized.startswith("update working_paper_oo_participant"):
            self.updates.append(normalized)

    def count_during(self) -> int:
        return len(self.updates)

    def reset(self) -> None:
        self.updates.clear()


async def _collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部 leave 场景
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.workpaper_sync_models import (
        WorkpaperForcesaveRequest,
        WorkpaperOoParticipant,
        WorkpaperOoRoom,
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
        StateTransitionError,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.rooms import (
        ParticipantDirtyLeaveError,
        ParticipantLeaveInFlightError,
        ParticipantScopeNotVisibleError,
        RoomService,
        derive_doc_key,
    )

    url = str(settings.DATABASE_URL)
    if "postgresql" not in url:
        raise _HarnessError(f"本判据要求真 PostgreSQL，实得 {url!r}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = _SCHEMA_PREFIX + uuid.uuid4().hex[:10]
    ssl_off = {"ssl": False}
    admin = create_async_engine(url, poolclass=NullPool, connect_args=ssl_off)
    snap: dict[str, Any] = {
        "schema": schema,
        "server_version": None,
        "apply_errors": [],
        "harness_errors": {},
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
            url,
            poolclass=NullPool,
            connect_args={**ssl_off, "server_settings": {"search_path": schema}},
        )
        witness = _StatementWitness()
        event.listen(engine.sync_engine, "before_cursor_execute", witness.hook)
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

        project_id, wp_id = uuid.uuid4(), uuid.uuid4()
        user_a, user_b, user_intruder = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{project_id}')")
            for u in (user_a, user_b, user_intruder):
                await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{u}')")
            await conn.exec_driver_sql(
                "INSERT INTO working_paper (id, project_id) VALUES "
                f"('{wp_id}', '{project_id}')"
            )
        base_path = f"storage/{project_id}/workpapers"

        async def _definitions(repo: WorkpaperSyncRepository) -> dict[str, Any]:
            """approved bundle + content version + representation（room/request 的 FK 前提）。"""
            blobs = {}
            for name in ("tpl", "instr", "contract", "authority", "payload", "proj", "canon"):
                kind = ArtifactKind.definition
                if name == "proj":
                    kind = ArtifactKind.projection
                elif name == "canon":
                    kind = ArtifactKind.canonical
                blobs[name] = await repo.register_artifact(
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=kind,
                    state=ArtifactState.published,
                    relative_path=f"{base_path}/.versions/{wp_id}/{name}.bin",
                    sha256=_d(f"blob-{name}"),
                    size_bytes=1024,
                    document_type="json",
                )
            defs = {}
            for kind, logical, extra in (
                ("template", "d4.template", {}),
                ("instrumentation", "d4.instrumentation", {}),
                ("contract", "d4.contract", {}),
                ("authority_model", "authority.projection",
                 {"authority_model_type": "projection_contract"}),
            ):
                defs[kind] = await repo.create_definition_artifact(
                    kind=kind,
                    logical_id=logical,
                    semantic_version="1.0.0",
                    blob_artifact_id=blobs[
                        {"template": "tpl", "instrumentation": "instr",
                         "contract": "contract", "authority_model": "authority"}[kind]
                    ].id,
                    sha256=_d(f"def-{kind}"),
                    source_commit="leave-judgement",
                    **extra,
                )

            bundle = await repo.create_definition_bundle(
                authority_model_definition_id=defs["authority_model"].id,
                slots={
                    BundleSlot.template: BundleSlotSpec(
                        BundleSlot.template, "definition",
                        f"definition:{defs['template'].id}", defs["template"].sha256,
                    ),
                    BundleSlot.instrumentation: BundleSlotSpec(
                        BundleSlot.instrumentation, "definition",
                        f"definition:{defs['instrumentation'].id}",
                        defs["instrumentation"].sha256,
                    ),
                    BundleSlot.contract: BundleSlotSpec(
                        BundleSlot.contract, "definition",
                        f"definition:{defs['contract'].id}", defs["contract"].sha256,
                    ),
                },
                canonical_payload_artifact_id=blobs["payload"].id,
                canonical_payload_sha256=_d("bundle-canonical"),
            )
            cv = await repo.create_content_version(
                project_id=project_id,
                wp_id=wp_id,
                entry_id=ENTRY,
                revision=1,
                source="html",
                projection_artifact_id=blobs["proj"].id,
                projection_sha256=blobs["proj"].sha256,
            )
            rep = await repo.create_representation(
                project_id=project_id,
                wp_id=wp_id,
                entry_id=ENTRY,
                content_version_id=cv.id,
                generation=1,
                document_type="xlsx",
                artifact_id=blobs["canon"].id,
                artifact_sha256=blobs["canon"].sha256,
                definition_bundle_id=bundle.id,
                authority_model_definition_id=defs["authority_model"].id,
                adapter_id="excel.d4.v1",
                adapter_build_digest=_d("adapter-build"),
                structure_hash=_d("structure-g1"),
                identity_inventory_sha256=_d("identity-g1"),
                reason="content_commit",
            )
            return {
                "bundle": bundle,
                "authority": defs["authority_model"],
                "content_version": cv,
                "representation": rep,
            }

        async def _room_with(
            repo: WorkpaperSyncRepository,
            world: dict[str, Any],
            *,
            generation: int,
            users: tuple[uuid.UUID, ...],
        ) -> dict[str, Any]:
            """建一间 room + 若干 active edit participant，并把 room 摆成 `active`。

            room 从 `opening` 到 `active` 的生产路径是 descriptor confirmation；这里用裸
            UPDATE 摆位，因为被测的正是「leave 不改 room」，用会改 room 的路径当 fixture
            就没法再断言那件事（见模块 docstring 末段）。
            """
            room = await repo.create_room(
                project_id=project_id,
                wp_id=wp_id,
                entry_id=ENTRY,
                doc_key=derive_doc_key(
                    wp_id=wp_id, entry_id=ENTRY, generation=generation
                ),
                generation=generation,
                opened_base_version_id=world["content_version"].id,
            )
            participants = []
            for user in users:
                participants.append(
                    await repo.create_participant(
                        project_id=project_id,
                        wp_id=wp_id,
                        entry_id=ENTRY,
                        room_id=room.id,
                        user_id=user,
                        mode=ParticipantMode.edit.value,
                        permission_epoch=1,
                        lease_token_hash=_d(f"lease-{room.id}-{user}"),
                    )
                )
            await repo.session.execute(
                sa.update(WorkpaperOoRoom)
                .where(WorkpaperOoRoom.id == room.id)
                .values(state="active")
            )
            await repo.session.flush()
            # 🔴 主键与 epoch 一律投影成**纯标量**返回，场景里不得再拿这些 ORM 实例做定位：
            # 有几个场景要 `await s.rollback()`（dirty / in-flight / 归属探针 / flush-only），
            # 而 rollback 无条件 expire 全部实例（`expire_on_commit=False` 只管 commit）⇒
            # 之后哪怕只读一个 `pa.id` 都会触发同步惰性刷新，在 async 上抛
            # `MissingGreenlet`，整个阶段变成 harness_errors。
            return {
                "room": room,
                "participants": participants,
                "room_id": room.id,
                "generation": int(room.generation),
                "write_fence_epoch": int(room.write_fence_epoch),
                "participant_ids": tuple(p.id for p in participants),
            }

        async def _room_row(session, room_id: uuid.UUID) -> dict[str, Any]:
            row = (
                await session.execute(
                    sa.select(WorkpaperOoRoom).where(WorkpaperOoRoom.id == room_id)
                )
            ).scalar_one()
            return {col: _plain(getattr(row, col)) for col in ROOM_COLUMNS}

        async def _participant_row(session, pid: uuid.UUID) -> dict[str, Any]:
            row = (
                await session.execute(
                    sa.select(WorkpaperOoParticipant).where(
                        WorkpaperOoParticipant.id == pid
                    )
                )
            ).scalar_one()
            return {
                "state": row.state,
                "left_at": _plain(row.left_at),
                "revoked_at": _plain(row.revoked_at),
                "expires_at": _plain(row.expires_at),
                "oo_drop_confirmed_at": _plain(row.oo_drop_confirmed_at),
                "joined_write_fence_epoch": int(row.joined_write_fence_epoch),
                "updated_at": _plain(row.updated_at),
            }

        async def _side_effect_counts(session, room_id: uuid.UUID) -> dict[str, int]:
            """leave 之后「本不该出现的东西」的条数 —— 三张表全数。"""
            from app.models.workpaper_sync_models import WorkpaperOoCloseIntent

            out: dict[str, int] = {}
            out["forcesave_requests"] = int(
                (
                    await session.execute(
                        sa.select(sa.func.count())
                        .select_from(WorkpaperForcesaveRequest)
                        .where(WorkpaperForcesaveRequest.room_id == room_id)
                    )
                ).scalar_one()
            )
            out["close_capture_requests"] = int(
                (
                    await session.execute(
                        sa.select(sa.func.count())
                        .select_from(WorkpaperForcesaveRequest)
                        .where(
                            WorkpaperForcesaveRequest.room_id == room_id,
                            WorkpaperForcesaveRequest.kind
                            == RequestKind.close_capture.value,
                        )
                    )
                ).scalar_one()
            )
            out["close_intents"] = int(
                (
                    await session.execute(
                        sa.select(sa.func.count())
                        .select_from(WorkpaperOoCloseIntent)
                        .where(WorkpaperOoCloseIntent.room_id == room_id)
                    )
                ).scalar_one()
            )
            return out

        # ═══ 定义世界：建一次，全场景共用 ═══
        #
        # 🔴 不可每场景各建一份：`working_paper_sync_definition_artifact` 上有
        # `uq_wpsda_kind_sha256`（kind, sha256）唯一约束，而本判据的 definition 摘要是
        # **常量**（`_d("def-template")` 等）⇒ 第二个场景起必撞
        # `UniqueViolationError`，此后每个阶段都只剩 harness_errors。
        #
        # 共用不弱化任何判据：definition / bundle / content version / representation 对
        # 「leave 改了哪些行的哪些列」是纯 FK 前提，生产里同一份 approved bundle 本来就是
        # 全房共用的。每个场景各自独立的是 **room + participant**（generation 1..9 各一间）。
        #
        # 取值投影成纯标量（`SimpleNamespace`）而不是直接传 ORM 实例：那些实例属于这里这个
        # 已关闭的 session，后续场景在别的 session 里读它们属于 detached 访问。
        world: dict[str, Any] = {}
        try:
            async with Session() as s:
                built = await _definitions(WorkpaperSyncRepository(s))
                await s.commit()
                world = {
                    "bundle": SimpleNamespace(
                        id=built["bundle"].id,
                        canonical_payload_sha256=built["bundle"].canonical_payload_sha256,
                    ),
                    "authority": SimpleNamespace(
                        id=built["authority"].id,
                        sha256=built["authority"].sha256,
                    ),
                    "content_version": SimpleNamespace(id=built["content_version"].id),
                    "representation": SimpleNamespace(id=built["representation"].id),
                }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("definitions", exc)

        # ═══ 场景 A：active → left（happy path，两人房，AC 4.1 / 4.3 / P7）═══
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                rooms = RoomService(repo)
                env = await _room_with(
                    repo, world, generation=1, users=(user_a, user_b)
                )
                room_id, (pa_id, pb_id) = env["room_id"], env["participant_ids"]
                await s.commit()
                before_room = await _room_row(s, room_id)
                before_other = await _participant_row(s, pb_id)
                witness.reset()
                witness.enabled = True
                outcome = await rooms.leave_participant(
                    room_id=room_id,
                    participant_id=pa_id,
                    actor_user_id=user_a,
                    client_reports_dirty=False,
                )
                first_updates = witness.count_during()
                witness.enabled = False
                await s.commit()
                snap["happy"] = {
                    "outcome": {
                        "participant_id": str(outcome.participant_id),
                        "already_left": outcome.already_left,
                        "left_at": _plain(outcome.left_at),
                        "remaining_active_editors": outcome.remaining_active_editors,
                        "room_state": outcome.room_state,
                    },
                    "participant_after": await _participant_row(s, pa_id),
                    "other_before": before_other,
                    "other_after": await _participant_row(s, pb_id),
                    "room_before": before_room,
                    "room_after": await _room_row(s, room_id),
                    "side_effects": await _side_effect_counts(s, room_id),
                    "participant_updates_seen": first_updates,
                }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("happy", exc)

        # ═══ 场景 B：幂等（AC 4.2 / P9）═══
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                rooms = RoomService(repo)
                env = await _room_with(repo, world, generation=2, users=(user_a,))
                room_id, (pa_id,) = env["room_id"], env["participant_ids"]
                await s.commit()
                first = await rooms.leave_participant(
                    room_id=room_id, participant_id=pa_id,
                    actor_user_id=user_a, client_reports_dirty=False,
                )
                await s.commit()
                after_first = await _participant_row(s, pa_id)
                room_after_first = await _room_row(s, room_id)
                witness.reset()
                witness.enabled = True
                second = await rooms.leave_participant(
                    room_id=room_id, participant_id=pa_id,
                    actor_user_id=user_a, client_reports_dirty=False,
                )
                third = await rooms.leave_participant(
                    room_id=room_id, participant_id=pa_id,
                    actor_user_id=user_a, client_reports_dirty=False,
                )
                replay_updates = witness.count_during()
                witness.enabled = False
                await s.commit()
                snap["idempotent"] = {
                    "first": {
                        "already_left": first.already_left,
                        "left_at": _plain(first.left_at),
                        "remaining": first.remaining_active_editors,
                        "room_state": first.room_state,
                    },
                    "second": {
                        "already_left": second.already_left,
                        "left_at": _plain(second.left_at),
                        "remaining": second.remaining_active_editors,
                        "room_state": second.room_state,
                    },
                    "third_already_left": third.already_left,
                    "third_left_at": _plain(third.left_at),
                    "participant_after_first": after_first,
                    "participant_after_replays": await _participant_row(s, pa_id),
                    "room_after_first": room_after_first,
                    "room_after_replays": await _room_row(s, room_id),
                    "replay_participant_updates": replay_updates,
                    "side_effects": await _side_effect_counts(s, room_id),
                }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("idempotent", exc)

        # ═══ 场景 C：closing → left（转换表的第二条边）═══
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                rooms = RoomService(repo)
                env = await _room_with(repo, world, generation=3, users=(user_a,))
                room_id, (pa_id,) = env["room_id"], env["participant_ids"]
                await s.execute(
                    sa.update(WorkpaperOoParticipant)
                    .where(WorkpaperOoParticipant.id == pa_id)
                    .values(state=ParticipantState.closing.value)
                )
                await s.commit()
                before_room = await _room_row(s, room_id)
                outcome = await rooms.leave_participant(
                    room_id=room_id, participant_id=pa_id,
                    actor_user_id=user_a, client_reports_dirty=False,
                )
                await s.commit()
                snap["from_closing"] = {
                    "already_left": outcome.already_left,
                    "participant_after": await _participant_row(s, pa_id),
                    "room_before": before_room,
                    "room_after": await _room_row(s, room_id),
                    # `closing` 不计入 active ⇒ 离开前后 remaining 都是 0。
                    "remaining": outcome.remaining_active_editors,
                }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("from_closing", exc)

        # ═══ 场景 D：dirty 拒绝（AC 4.4 / P8）═══
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                rooms = RoomService(repo)
                env = await _room_with(repo, world, generation=4, users=(user_a,))
                room_id, (pa_id,) = env["room_id"], env["participant_ids"]
                await s.commit()
                refused: dict[str, Any] = {}
                witness.reset()
                witness.enabled = True
                try:
                    await rooms.leave_participant(
                        room_id=room_id, participant_id=pa_id,
                        actor_user_id=user_a, client_reports_dirty=True,
                    )
                except Exception as exc:  # noqa: BLE001 - 判据要类型与 code
                    refused = {
                        "type": type(exc).__name__,
                        "error_code": getattr(exc, "error_code", None),
                        "message": str(exc),
                    }
                refused["participant_updates_seen"] = witness.count_during()
                witness.enabled = False
                await s.rollback()
                refused["participant_after"] = await _participant_row(s, pa_id)
                # 同一个 participant 在 dirty=False 下必须能走（证明拒绝只由 dirty 决定）
                allowed = await rooms.leave_participant(
                    room_id=room_id, participant_id=pa_id,
                    actor_user_id=user_a, client_reports_dirty=False,
                )
                await s.commit()
                snap["dirty"] = {
                    "refused": refused,
                    "then_allowed_state": (await _participant_row(s, pa_id))["state"],
                    "then_allowed_replayed": allowed.already_left,
                }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("dirty", exc)

        # ═══ 场景 E：in-flight 拒绝（AC 4.4 的第二半）═══
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                rooms = RoomService(repo)
                env = await _room_with(repo, world, generation=5, users=(user_a, user_b))
                room_id, (pa_id, pb_id) = env["room_id"], env["participant_ids"]
                req_id = uuid.uuid4()
                req = WorkpaperForcesaveRequest(
                    id=req_id,
                    room_id=room_id,
                    generation=int(env["generation"]),
                    request_sequence=1,
                    kind=RequestKind.forcesave.value,
                    initiated_by_participant_id=pa_id,
                    initiator_permission_epoch=1,
                    client_edit_epoch=1,
                    write_fence_epoch=int(env["write_fence_epoch"]),
                    client_base_version_id=world["content_version"].id,
                    client_base_representation_id=world["representation"].id,
                    client_base_projection_sha256=_d("proj-base"),
                    definition_bundle_id=world["bundle"].id,
                    definition_bundle_sha256=world["bundle"].canonical_payload_sha256,
                    authority_model_definition_id=world["authority"].id,
                    authority_model_definition_sha256=world["authority"].sha256,
                    adapter_build_digest=_d("adapter-build"),
                    contributor_snapshot_digest=_d("contributor"),
                    idempotency_key="leave-inflight",
                    frozen_request_fingerprint=_d("fingerprint"),
                    state=RequestState.frozen.value,
                )
                s.add(req)
                await s.commit()
                blocked: dict[str, Any] = {}
                try:
                    await rooms.leave_participant(
                        room_id=room_id, participant_id=pa_id,
                        actor_user_id=user_a, client_reports_dirty=False,
                    )
                except Exception as exc:  # noqa: BLE001
                    blocked = {
                        "type": type(exc).__name__,
                        "error_code": getattr(exc, "error_code", None),
                        "message": str(exc),
                    }
                await s.rollback()
                blocked["participant_after"] = await _participant_row(s, pa_id)
                # 别人的未终结 request **不得**挡住我离开（in-flight 门按 participant 收窄）
                other = await rooms.leave_participant(
                    room_id=room_id, participant_id=pb_id,
                    actor_user_id=user_b, client_reports_dirty=False,
                )
                await s.commit()
                # request 终结之后我才能走
                await s.execute(
                    sa.update(WorkpaperForcesaveRequest)
                    .where(WorkpaperForcesaveRequest.id == req_id)
                    .values(state=RequestState.terminal.value)
                )
                await s.flush()
                after_terminal = await rooms.leave_participant(
                    room_id=room_id, participant_id=pa_id,
                    actor_user_id=user_a, client_reports_dirty=False,
                )
                await s.commit()
                snap["in_flight"] = {
                    "blocked": blocked,
                    "other_participant_left_anyway": (
                        (await _participant_row(s, pb_id))["state"]
                    ),
                    "other_outcome_replayed": other.already_left,
                    "after_request_terminal_state": (
                        (await _participant_row(s, pa_id))["state"]
                    ),
                    "after_request_terminal_replayed": after_terminal.already_left,
                }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("in_flight", exc)

        # ═══ 场景 F：归属 / 404 oracle（AC 4.2）═══
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                rooms = RoomService(repo)
                env = await _room_with(repo, world, generation=6, users=(user_a,))
                other_env = await _room_with(repo, world, generation=7, users=(user_b,))
                room_id, (pa_id,) = env["room_id"], env["participant_ids"]
                other_room_id, (pb_id,) = other_env["room_id"], other_env["participant_ids"]
                await s.commit()
                probes: dict[str, Any] = {}
                cases = {
                    # ① 别人的 lease（participant 存在、room 也对，只是不是我的）
                    "not_my_lease": (room_id, pa_id, user_intruder),
                    # ② 跨 room（participant 存在，但不属于这个 room）
                    "cross_room": (room_id, pb_id, user_b),
                    # ③ 压根不存在
                    "absent": (room_id, uuid.uuid4(), user_a),
                }
                for label, (rid, pid, actor) in cases.items():
                    try:
                        await rooms.leave_participant(
                            room_id=rid, participant_id=pid,
                            actor_user_id=actor, client_reports_dirty=False,
                        )
                        probes[label] = {"type": None, "error_code": None}
                    except Exception as exc:  # noqa: BLE001
                        probes[label] = {
                            "type": type(exc).__name__,
                            "error_code": getattr(exc, "error_code", None),
                            "message": str(exc),
                        }
                    await s.rollback()
                snap["ownership"] = {
                    "probes": probes,
                    "victim_after": await _participant_row(s, pa_id),
                    "cross_room_victim_after": await _participant_row(s, pb_id),
                    # 正主仍然能走（证明前三条不是「谁都不让走」）
                    "owner_can_still_leave": (
                        await rooms.leave_participant(
                            room_id=room_id, participant_id=pa_id,
                            actor_user_id=user_a, client_reports_dirty=False,
                        )
                    ).already_left,
                }
                await s.commit()
                snap["ownership"]["owner_state_after"] = (
                    await _participant_row(s, pa_id)
                )["state"]
        except Exception as exc:  # noqa: BLE001
            _phase_failed("ownership", exc)

        # ═══ 场景 G：非法起点不得被幂等分支吞掉 ═══
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                rooms = RoomService(repo)
                env = await _room_with(repo, world, generation=8, users=(user_a, user_b))
                room_id, (pa_id, pb_id) = env["room_id"], env["participant_ids"]
                # `revoked` 必须同时带 `revoked_at`：V151 的
                # `ck_wpoop_revoked_at CHECK (state <> 'revoked' OR revoked_at IS NOT NULL)`
                # 会拒掉只改 state 的裸 UPDATE（`expired` 无此伴随列要求）。
                for pid, state, extra in (
                    (pa_id, ParticipantState.revoked.value, {"revoked_at": sa.func.now()}),
                    (pb_id, ParticipantState.expired.value, {}),
                ):
                    await s.execute(
                        sa.update(WorkpaperOoParticipant)
                        .where(WorkpaperOoParticipant.id == pid)
                        .values(state=state, **extra)
                    )
                await s.commit()
                illegal: dict[str, Any] = {}
                for label, pid in (("revoked", pa_id), ("expired", pb_id)):
                    try:
                        await rooms.leave_participant(
                            room_id=room_id, participant_id=pid,
                            actor_user_id=user_a if label == "revoked" else user_b,
                            client_reports_dirty=False,
                        )
                        illegal[label] = {"type": None}
                    except Exception as exc:  # noqa: BLE001
                        illegal[label] = {
                            "type": type(exc).__name__,
                            "is_state_transition_error": isinstance(
                                exc, StateTransitionError
                            ),
                        }
                    await s.rollback()
                snap["illegal_start"] = {
                    "results": illegal,
                    "revoked_after": await _participant_row(s, pa_id),
                    "expired_after": await _participant_row(s, pb_id),
                }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("illegal_start", exc)

        # ═══ 场景 H：service 只 flush 不 commit（本域事务边界惯例）═══
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                rooms = RoomService(repo)
                env = await _room_with(repo, world, generation=9, users=(user_a,))
                room_id, (pa_id,) = env["room_id"], env["participant_ids"]
                await s.commit()
                await rooms.leave_participant(
                    room_id=room_id, participant_id=pa_id,
                    actor_user_id=user_a, client_reports_dirty=False,
                )
                inside = await _participant_row(s, pa_id)
                # 没人 commit ⇒ 回滚必须把它变回 active。若 service 自己 commit 了，
                # 这里会仍然是 left（判据即红）。
                await s.rollback()
                snap["flush_only"] = {
                    "state_before_rollback": inside["state"],
                    "state_after_rollback": (await _participant_row(s, pa_id))["state"],
                }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("flush_only", exc)

        snap["participant_states"] = sorted(s.value for s in ParticipantState)
        snap["error_codes"] = {
            "scope": ParticipantScopeNotVisibleError.error_code,
            "dirty": ParticipantDirtyLeaveError.error_code,
            "in_flight": ParticipantLeaveInFlightError.error_code,
        }
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
# 0. 采集完整性
# ═══════════════════════════════════════════════════════════════════════════


def test_ran_on_real_postgresql_in_scratch_schema(snap: dict[str, Any]) -> None:
    assert "PostgreSQL" in (snap["server_version"] or ""), snap["server_version"]
    assert snap["schema"].startswith(_SCHEMA_PREFIX)
    assert snap["apply_errors"] == []


def test_no_phase_crashed_during_collection(snap: dict[str, Any]) -> None:
    """任何阶段崩掉都必须在这里显性打红。

    这不是「多余的自检」：阶段异常被记录而不是抛出之后，若没有本断言，一个把某阶段打崩的
    回归就会变成「那一段的断言读到缺失数据、但测试全绿」。
    """
    assert snap["harness_errors"] == {}, (
        f"采集阶段异常（后续断言会读到 stale/缺失数据）: {snap['harness_errors']}"
    )


def test_the_statement_witness_can_actually_see_an_update(snap: dict[str, Any]) -> None:
    """观测者反证：第一次 leave 必须**被它看到**恰 1 条 participant UPDATE。

    没有这一条时，P9 的「零条」结论在一个坏掉的监听器下恒真。
    """
    assert snap["happy"]["participant_updates_seen"] == 1, snap["happy"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. AC 4.1 / 4.3 / P7：只改这一个 participant
# ═══════════════════════════════════════════════════════════════════════════


def test_the_participant_really_lands_on_left_with_a_timestamp(snap: dict[str, Any]) -> None:
    after = snap["happy"]["participant_after"]
    assert after["state"] == "left"
    assert after["left_at"] is not None, "left_at 没写上 ⇒ 这条迁移没有时间戳事实"
    # 主动离开**不是**被撤销：`revoked_at` / `oo_drop_confirmed_at` 必须仍为空，
    # 否则两件事在数据上混同，撤销的取证意义就没了。
    assert after["revoked_at"] is None
    assert after["oo_drop_confirmed_at"] is None
    assert snap["happy"]["outcome"]["already_left"] is False
    assert snap["happy"]["outcome"]["left_at"] == after["left_at"], (
        "响应里的 left_at 与落库值不一致 —— 幂等判据要靠它比「有没有第二条事件」"
    )


def test_property_7_not_one_room_column_changed(snap: dict[str, Any]) -> None:
    """P7 的正面：room 行**逐列**未变（反证是「让 leave 顺手改 room.state ⇒ 红」）。"""
    before, after = snap["happy"]["room_before"], snap["happy"]["room_after"]
    drifted = {c: (before[c], after[c]) for c in ROOM_COLUMNS if before[c] != after[c]}
    assert not drifted, f"leave 改了 room 的这些列: {drifted}"
    # 分母不塌：比较面必须真的覆盖 close barrier / generation / fence 那几列。
    assert {"state", "generation", "write_fence_epoch", "close_barrier_epoch"} <= set(
        ROOM_COLUMNS
    )
    assert len(before) == len(ROOM_COLUMNS) >= 17


def test_property_7_the_other_participant_is_untouched(snap: dict[str, Any]) -> None:
    before, after = snap["happy"]["other_before"], snap["happy"]["other_after"]
    assert before == after, f"另一个 participant 被改了: {before} → {after}"
    assert after["state"] == "active"


def test_ac_4_3_the_room_stays_active_when_another_editor_remains(
    snap: dict[str, Any],
) -> None:
    """AC 4.3：仍有其他 active participant 时 room **保持** active。

    这正是与 close-intent 的本质差别 —— 后者是「最后一个人走，该收尾了」，会把 room 推进
    `close_barrier`。真栈实测那一步之后 room 再也进不去。
    """
    assert snap["happy"]["room_after"]["state"] == "active"
    assert snap["happy"]["outcome"]["room_state"] == "active"
    assert snap["happy"]["outcome"]["remaining_active_editors"] == 1, (
        "两人房里一个人离开，remaining 必须是 1"
    )


def test_ac_4_1_no_request_no_close_intent_of_any_kind(snap: dict[str, Any]) -> None:
    """AC 4.1：不建 forcesave、不建 close_capture、不建 close intent —— 三张表全数为 0。"""
    for label in ("happy", "idempotent"):
        counts = snap[label]["side_effects"]
        assert counts["forcesave_requests"] == 0, (label, counts)
        assert counts["close_capture_requests"] == 0, (label, counts)
        assert counts["close_intents"] == 0, (label, counts)


# ═══════════════════════════════════════════════════════════════════════════
# 2. AC 4.2 / P9：幂等
# ═══════════════════════════════════════════════════════════════════════════


def test_property_9_repeating_leave_writes_nothing_at_all(snap: dict[str, Any]) -> None:
    """P9：第二、第三次 leave 发出的 participant UPDATE 语句数为 **0**。

    判据落在真实 SQL 上而不是返回值上：一个「先写一遍再说 already_left」的实现在只看
    返回值的判据下照样绿，而它每次重放都会刷新 `left_at` —— 那就是第二条审计事件。
    """
    idem = snap["idempotent"]
    assert idem["replay_participant_updates"] == 0, (
        f"两次重放共发出 {idem['replay_participant_updates']} 条 participant UPDATE"
    )


def test_property_9_the_replay_returns_the_very_same_result(snap: dict[str, Any]) -> None:
    idem = snap["idempotent"]
    assert idem["first"]["already_left"] is False
    assert idem["second"]["already_left"] is True
    assert idem["third_already_left"] is True
    # 「没有第二条事件」的可观测形态：`left_at` 是**第一次**那个值，逐字相同。
    assert idem["second"]["left_at"] == idem["first"]["left_at"]
    assert idem["third_left_at"] == idem["first"]["left_at"]
    assert idem["participant_after_replays"] == idem["participant_after_first"], (
        "重放改了 participant 行（哪怕只是 updated_at）—— 那就是第二条事件"
    )
    # 其余字段也必须一致（remaining / room_state 都是派生量，重放不得漂移）。
    assert idem["second"]["remaining"] == idem["first"]["remaining"]
    assert idem["second"]["room_state"] == idem["first"]["room_state"]


def test_the_replay_does_not_touch_the_room_either(snap: dict[str, Any]) -> None:
    idem = snap["idempotent"]
    assert idem["room_after_replays"] == idem["room_after_first"]
    assert idem["room_after_first"]["state"] == "active", (
        "单人房里那个人走了，room 也**不该**被 leave 收尾 —— 收尾是 close barrier 的职责，"
        "本端点不越界（design 四）"
    )


def test_an_illegal_start_state_is_refused_not_swallowed(snap: dict[str, Any]) -> None:
    """`revoked`/`expired → left` 必须抛，而不是被幂等分支当成「已经走了」。

    这条是幂等分支的**边界**：`PARTICIPANT_EDGES[left]` 是空集，所以「捕获异常即幂等」
    那种写法会把这两种非法起点也一起放过 —— 被撤销的会话就能自己走回一个正常终态。
    """
    results = snap["illegal_start"]["results"]
    for label in ("revoked", "expired"):
        assert results[label]["type"] is not None, f"{label} → left 居然成功了"
        assert results[label]["is_state_transition_error"] is True, results[label]
    assert snap["illegal_start"]["revoked_after"]["state"] == "revoked"
    assert snap["illegal_start"]["expired_after"]["state"] == "expired"


def test_closing_may_also_leave(snap: dict[str, Any]) -> None:
    """`closing → left` 是转换表里的第二条边，也必须真的通（AC 4.1 的 `active/closing`）。"""
    fc = snap["from_closing"]
    assert fc["already_left"] is False
    assert fc["participant_after"]["state"] == "left"
    assert fc["participant_after"]["left_at"] is not None
    assert fc["room_before"] == fc["room_after"], "从 closing 离开也不得动 room"
    assert fc["remaining"] == 0, "`closing` 不计入 active，离开后仍是 0"


# ═══════════════════════════════════════════════════════════════════════════
# 3. AC 4.4 / P8：dirty 与 in-flight
# ═══════════════════════════════════════════════════════════════════════════


def test_property_8_dirty_is_refused_and_writes_nothing(snap: dict[str, Any]) -> None:
    d = snap["dirty"]["refused"]
    assert d["type"] == "ParticipantDirtyLeaveError", d
    assert d["error_code"] == "participant_leave_refused_dirty", d
    assert d["participant_updates_seen"] == 0, "被拒之前不得已经写了一笔"
    assert d["participant_after"]["state"] == "active"
    assert d["participant_after"]["left_at"] is None
    # 文案必须是中文人话且指向补救动作（前端会直接透出）。
    assert "未保存" in d["message"] and "保存" in d["message"], d["message"]


def test_the_dirty_gate_is_the_only_reason_that_call_was_refused(
    snap: dict[str, Any],
) -> None:
    """同一个 participant 在 `dirty=False` 下立刻能走 ⇒ 拒绝确实只由 dirty 决定。

    没有这一条时，一个「永远拒绝」的实现也能让上面那条绿。
    """
    assert snap["dirty"]["then_allowed_state"] == "left"
    assert snap["dirty"]["then_allowed_replayed"] is False


def test_property_8_an_outstanding_request_blocks_leave(snap: dict[str, Any]) -> None:
    b = snap["in_flight"]["blocked"]
    assert b["type"] == "ParticipantLeaveInFlightError", b
    assert b["error_code"] == "participant_leave_refused_in_flight", b
    assert b["participant_after"]["state"] == "active"
    assert "未终结" in b["message"], b["message"]


def test_the_in_flight_gate_is_scoped_to_that_participant(snap: dict[str, Any]) -> None:
    """别人的未终结 request 不得挡住我离开。

    口径与前端一致：`leaveBlockReason` 的 in-flight 说的是**我这个客户端**的同步在进行中。
    按 room 收口会让「A 在保存」把 B 锁在编辑器里。
    """
    assert snap["in_flight"]["other_participant_left_anyway"] == "left"
    assert snap["in_flight"]["other_outcome_replayed"] is False


def test_once_the_request_is_terminal_leave_goes_through(snap: dict[str, Any]) -> None:
    assert snap["in_flight"]["after_request_terminal_state"] == "left"
    assert snap["in_flight"]["after_request_terminal_replayed"] is False


def test_the_two_refusals_have_distinct_error_codes(snap: dict[str, Any]) -> None:
    codes = snap["error_codes"]
    assert codes["dirty"] != codes["in_flight"], codes
    assert len(set(codes.values())) == 3, codes


# ═══════════════════════════════════════════════════════════════════════════
# 4. AC 4.2：归属与 404 oracle
# ═══════════════════════════════════════════════════════════════════════════


def test_only_the_owner_may_leave_and_all_three_misses_share_one_error(
    snap: dict[str, Any],
) -> None:
    """三种「不是你的」在**同一个**异常类型上收口 ⇒ router 换成同一份 404。

    分型错了的后果不是「不好看」：`participant_not_writable` 落 422 并带人话诊断，于是
    「这个 id 存在、只是不是你的」就被告诉了调用方 —— 那是 Property 45 要禁的存在性预言机。
    """
    probes = snap["ownership"]["probes"]
    assert set(probes) == {"not_my_lease", "cross_room", "absent"}
    for label, got in probes.items():
        assert got["type"] == "ParticipantScopeNotVisibleError", (label, got)
        assert got["error_code"] == "participant_scope_not_found", (label, got)
    # 三条的消息也不得从文案上区分（router 会丢掉它，但服务层日志同样不该泄露）。
    shapes = {p["message"].split(":")[0] for p in probes.values()}
    assert shapes == {"participant 不可见"}, shapes


def test_a_failed_probe_leaves_the_victim_untouched(snap: dict[str, Any]) -> None:
    for key in ("victim_after", "cross_room_victim_after"):
        row = snap["ownership"][key]
        assert row["state"] == "active", (key, row)
        assert row["left_at"] is None, (key, row)


def test_the_owner_can_still_leave_after_those_probes(snap: dict[str, Any]) -> None:
    """反空转：三条探测之后正主仍然能走 ⇒ 上面的拒绝不是「谁都不让走」。"""
    assert snap["ownership"]["owner_can_still_leave"] is False
    assert snap["ownership"]["owner_state_after"] == "left"


# ═══════════════════════════════════════════════════════════════════════════
# 5. 事务边界
# ═══════════════════════════════════════════════════════════════════════════


def test_the_service_only_flushes_so_a_rollback_undoes_the_leave(
    snap: dict[str, Any],
) -> None:
    """service 只 flush 不 commit（本域惯例：事务边界由 router 持有）。

    判据形态刻意是「回滚之后回到 active」：service 若自己 commit 了，回滚拿不回来 ⇒ 红。
    这比 AST 判据多一层 —— AST 只能证明「没写 commit 这个词」。
    """
    fo = snap["flush_only"]
    assert fo["state_before_rollback"] == "left"
    assert fo["state_after_rollback"] == "active", (
        "回滚之后仍是 left ⇒ service 自己 commit 了 —— 跨 service 编排时会把别人的"
        "半成品一起提交"
    )
