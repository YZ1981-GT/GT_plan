# -*- coding: utf-8 -*-
"""Task 28 真实 PostgreSQL + ASGI 守卫：统一 404/403 oracle、scope tombstone、幂等 409。
spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 28
Requirements: 3.1, 3.6, 3.7, 5.8, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 11.4
Properties: **P10 / P11 / P45**

═══ 为什么必须真库 + 真 ASGI ═══

Task 28 的判据几乎全是「HTTP 响应」与「库里行数」的组合：

* **P45 的 404 oracle** —— 「不存在 / 已 retire / 跨 scope / 无 visibility / numeric
  revision 当 route key」五种原因的响应体必须**逐字节相同**。离线只能证明
  `_not_found()` 这一个构造点的内容；真正要证的是五条**不同代码路径**跑完之后从
  ASGI 出来的 body 一样。
* **scope tombstone** —— `retired_at` 退役后 scope 行**物理仍在**（防 id 复用），
  而用户访问与「不存在」同 404。这是「行还在」+「响应一样」两个事实的合成，
  离线替身仓储证不了第一个。
* **numeric revision 无碰撞** —— 两个 wp 都有 revision 1，必须由不同 UUID 定位，
  且拿另一个 wp 的 version UUID 打本 wp 的 rollback 必须 404。
* **复合幂等键 + fingerprint** —— 同 key 跨 participant 必须 409 **且不返回旧 ID**。
  唯一约束住在 V151 里，替身仓储无法复现。
* **claim 前三实体为 0 / download-only 保持 0** —— 行计数判据。
* **撤权重放零副作用** —— 前后行计数逐表相等。

═══ 注入边界（诚实说明）═══

app 只挂 `wp_sync_router`，并**只**替换三个依赖：`get_db`、`get_current_user`、
`_services`（后者用同一 session 装配真实服务，但 `visibility` 探针与 action 回调由
本文件的 `_Switchboard` 控制）。

那两个是**设计上的注入缝**（`ProjectVisibilityProbe` / `ActionAuthorizer`），不是为了
绕过判据：生产实现 `WpGateVisibilityProbe` 必须调用平台统一门 `enforce_wp_gate`，
这一条由离线文件的 AST 判据锁着
（`TestRegistrationAndLegacyDelegation::test_the_probe_reuses_the_platform_visibility_gate`）。
把整个 `wp_visibility` 域（delegation / wp_index / reviewer 白名单 / 历史版本）搬进
scratch schema 才能端到端跑那条链 —— 那属于 Task 30 的集成门。

guard、router、repository、request/application 服务、V151 的 scope index 约束
**全部是真的**。

═══ 隔离与采集 ═══

scratch schema `tmp_task28_router_<hex>` + 独立文件根，结束 `DROP SCHEMA CASCADE` +
`rmtree`。全部场景由**一次 `asyncio.run`** 跑完落进快照（module fixture）——
每个测试各自开 async 会污染共享连接池（Task 21~27 实测：第二个起
`NoneType has no attribute send`）。采集阶段异常一律**记录不穿透**：穿透会把整个
module 变成 collection ERROR，而 `-rf` 只列 FAILED 不列 ERROR ⇒ 定向变异看不到预期
失败项 ⇒ 判 GREEN。`test_no_phase_crashed_during_collection` 是这个决定的另一半。
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
from datetime import datetime, timezone
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

_SCHEMA_PREFIX = "tmp_task28_router_"
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


class _Switchboard:
    """一处控制 visibility / workflow lock / action，便于逐场景翻转。

    刻意**不返回硬编码 True**：`project_visible` 与 `action_allowed` 都是可翻的开关，
    于是「撤权后重放」「无 visibility」这两条判据各有真实的否定侧。
    """

    def __init__(self) -> None:
        self.project_visible = True
        self.workflow_locked = False
        self.action_allowed = True
        self.probe_calls: list[str] = []
        self.authorize_calls: list[str] = []

    async def observe(self, *, project_id, wp_id, entry_id):
        self.probe_calls.append(f"{wp_id}/{entry_id}")
        return {
            "project_visible": self.project_visible,
            "workflow_locked": self.workflow_locked,
            "readonly": self.workflow_locked,
        }

    def authorize(self, scope) -> bool:
        """复用生产词汇表判据 + 一个可翻的「撤权」开关。

        读 action 不受 `action_allowed` 影响：撤权场景要证的是「写重放被拦」，
        把读一起关掉会让判据失去区分度。
        """
        from app.routers.wp_sync_router import _KNOWN_ACTIONS, _READ_ONLY_ACTIONS

        self.authorize_calls.append(str(scope.action))
        if str(scope.action) not in _KNOWN_ACTIONS:
            return False
        if str(scope.action) in _READ_ONLY_ACTIONS:
            return True
        return self.action_allowed


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - 一次采集覆盖全部场景
    import httpx
    from fastapi import Depends, FastAPI, HTTPException
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.database import get_db
    from app.core.migration_runner import MigrationRunner
    from app.deps import get_current_user
    from app.models.workpaper_sync_models import (
        WorkpaperContentApplication,
        WorkpaperContentRepresentation,
        WorkpaperForcesaveRequest,
        WorkpaperSyncOperation,
        WorkpaperSyncScopeIndex,
    )
    from app.routers import wp_sync_router as SR
    from app.services.workpaper_sync import definitions as D
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.endpoint_guard import (
        ScopeClaimCodec,
        SyncEndpointGuard,
    )
    from app.services.workpaper_sync.models import (
        ArtifactKind,
        ArtifactState,
        BundleSlot,
        ParticipantMode,
        RecoveryReason,
        ScopeResourceKind,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.request_application import RequestApplicationService
    from app.services.workpaper_sync.rooms import RoomScope, RoomService

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 28 的判据是「HTTP 响应 + 库里行数」的组合（统一 404 oracle、"
            "scope tombstone、复合幂等 409、三实体计数），必须真实 PostgreSQL；"
            f"当前 DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(
        _MIGRATION.read_text(encoding="utf-8")
    )
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task28_store_"))
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
        "world": {},
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
        wp_a, wp_b = uuid.uuid4(), uuid.uuid4()
        artifacts = CanonicalArtifactRepository(base_root)

        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{project}')")
            for u in (user_a, user_b):
                await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{u}')")
            for w in (wp_a, wp_b):
                await conn.exec_driver_sql(
                    "INSERT INTO working_paper (id, project_id) VALUES "
                    f"('{w}', '{project}')"
                )

        # ── approved definition bundle（只为满足 representation 的 FK 与 room 的 bundle 门）
        world: dict[str, Any] = {}
        blobs = {
            name: artifacts.publish_definition_blob(
                project_id=project,
                wp_id=wp_a,
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
                    wp_id=wp_a,
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
                kind="template", logical_id="task28.tpl", semantic_version="1.0.0",
                blob_artifact_id=art["tpl"].id, sha256=_d("task28-template"),
                structure_hash=_d("task28-tpl-structure"), source_commit="task28",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation", logical_id="task28.instr",
                semantic_version="1.0.0", blob_artifact_id=art["instr"].id,
                sha256=_d("task28-instrumentation"),
                structure_hash=_d("task28-instr-structure"), source_commit="task28",
            )
            contract_def = await repo.create_definition_artifact(
                kind="contract", logical_id="task28.contract", semantic_version="1.0.0",
                blob_artifact_id=art["contract"].id, sha256=_d("task28-contract"),
                source_commit="task28",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task28.authority",
                semantic_version="1.0.0", blob_artifact_id=art["authority"].id,
                sha256=_d("task28-authority"),
                authority_model_type="projection_contract", source_commit="task28",
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
            world.update(bundle=bundle.id, authority=authority.id)

        # ── 两个 wp 各自的 revision 1（P45：numeric revision 无碰撞）
        async def _build_entry(wp: uuid.UUID, tag: str) -> dict[str, Any]:
            rep_bytes = b"PK\x03\x04" + json.dumps({"tag": tag}).encode()
            gen1 = artifacts.publish_representation(
                entry_id=ENTRY,
                generation=1,
                staged=artifacts.stage_bytes(
                    project_id=project, wp_id=wp, payload=rep_bytes,
                    document_type="xlsx",
                ),
                validate_ooxml=False,
            )
            proj = artifacts.publish_projection(
                revision=1,
                staged=artifacts.stage_bytes(
                    project_id=project, wp_id=wp,
                    payload=json.dumps({"tag": tag}, sort_keys=True).encode(),
                    document_type="json.gz",
                ),
            )
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                art_rep = await repo.register_artifact(
                    project_id=project, wp_id=wp, kind=ArtifactKind.canonical,
                    state=ArtifactState.published, relative_path=gen1.relative_path,
                    sha256=gen1.sha256, size_bytes=gen1.size_bytes,
                    document_type="xlsx",
                )
                art_proj = await repo.register_artifact(
                    project_id=project, wp_id=wp, kind=ArtifactKind.projection,
                    state=ArtifactState.published, relative_path=proj.relative_path,
                    sha256=proj.sha256, size_bytes=proj.size_bytes,
                    document_type="json.gz",
                )
                cv = await repo.create_content_version(
                    project_id=project, wp_id=wp, entry_id=ENTRY, revision=1,
                    source="html", projection_artifact_id=art_proj.id,
                    projection_sha256=proj.sha256, actor_id=user_a,
                )
                rep = await repo.create_representation(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    content_version_id=cv.id, generation=1, document_type="xlsx",
                    artifact_id=art_rep.id, artifact_sha256=art_rep.sha256,
                    definition_bundle_id=world["bundle"],
                    authority_model_definition_id=world["authority"],
                    adapter_id=ENTRY, adapter_build_digest=_d("task28-adapter"),
                    structure_hash=_d(f"task28-structure-{tag}"),
                    identity_inventory_sha256=_d(f"task28-identity-{tag}"),
                    reason="content_commit",
                )
                await repo.set_entry_pointer(
                    wp_id=wp, entry_id=ENTRY, representation_id=rep.id, generation=1
                )
                await repo.set_current_content_version(wp, cv.id)
                await s.commit()
            return {"wp": wp, "cv": cv.id, "rep": rep.id, "projection": proj.sha256}

        entry_a = await _build_entry(wp_a, "a")
        entry_b = await _build_entry(wp_b, "b")
        world.update(entry_a=entry_a, entry_b=entry_b)

        # ── room / 两个 participant / confirmation（forcesave 的八条资格门要它们）
        scope_a = RoomScope(project_id=project, wp_id=wp_a, entry_id=ENTRY)
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            svc = RoomService(repo)
            representation = (
                await s.execute(
                    sa.select(WorkpaperContentRepresentation).where(
                        WorkpaperContentRepresentation.id == entry_a["rep"]
                    )
                )
            ).scalar_one()
            room, _frozen = await svc.open_or_reuse_room(
                scope_a,
                representation=representation,
                opened_base_version_id=entry_a["cv"],
            )
            frozen = await svc.frozen_bundle_identity(world["bundle"])
            participants = {}
            for label, uid, lease in (("a", user_a, "lease-a"), ("b", user_b, "lease-b")):
                p = await svc.join_participant(
                    scope_a, room_id=room.id, user_id=uid,
                    mode=ParticipantMode.edit, permission_epoch=5, lease_token=lease,
                )
                conf, room = await svc.confirm_descriptor(
                    scope_a, room_id=room.id, participant_id=p.id,
                    representation_id=entry_a["rep"],
                    content_version_id=entry_a["cv"],
                    projection_sha256=entry_a["projection"],
                    idempotency_key=f"ready-{p.id}", expected_bundle=frozen,
                )
                participants[label] = {"id": p.id, "confirmation": conf.id}
            await s.commit()
            world.update(
                room=room.id,
                doc_key=room.doc_key,
                participant_a=participants["a"]["id"],
                participant_b=participants["b"]["id"],
                confirmation_a=participants["a"]["confirmation"],
            )

        # ── recovery case（claim 前三实体必须为 0）
        #
        # 🔴 incoming artifact 必须绑定 `source_delivery_id`（V151 的 CHECK）——
        # 「哪一次 callback 投递产生了这份 incoming」是可追溯性的地基，因此先建 delivery。
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            delivery = await repo.record_delivery(
                project_id=project, wp_id=wp_a, entry_id=ENTRY, room_id=world["room"],
                generation=1, route_credential_id=uuid.uuid4(), callback_status=6,
                delivery_key=_d("task28-delivery-key"),
                payload_sha256=_d("task28-payload"),
            )
            delivery_id = delivery.id
            staged = artifacts.stage_incoming(
                project_id=project, wp_id=wp_a, delivery_id=delivery_id,
                chunks=[b"PK\x03\x04incoming-task28"], document_type="xlsx",
            )
            sealed = artifacts.seal_incoming(staged, delivery_id=delivery_id)
            incoming_art = await repo.register_artifact(
                project_id=project, wp_id=wp_a, kind=ArtifactKind.incoming,
                state=ArtifactState.durable, relative_path=sealed.relative_path,
                sha256=sealed.sha256, size_bytes=sealed.size_bytes,
                document_type="xlsx", source_delivery_id=delivery_id,
            )
            case = await repo.create_recovery_case(
                project_id=project, wp_id=wp_a, entry_id=ENTRY, room_id=world["room"],
                generation=1, source_delivery_key=_d("task28-delivery-key"),
                incoming_artifact_id=incoming_art.id,
                reason=RecoveryReason.missing_request,
            )
            # 🔴 第二个 case 专供 claim 场景：download-only 是**终态**，
            # 用同一个 case 先 download-only 再 claim 会撞状态机（实测 409
            # `illegal_state_transition: download_only → claiming`），
            # 于是「claim 路径」这条判据实际上从未被执行过。
            delivery2 = await repo.record_delivery(
                project_id=project, wp_id=wp_a, entry_id=ENTRY, room_id=world["room"],
                generation=1, route_credential_id=uuid.uuid4(), callback_status=6,
                delivery_key=_d("task28-delivery-key-2"),
                payload_sha256=_d("task28-payload-2"),
            )
            staged2 = artifacts.stage_incoming(
                project_id=project, wp_id=wp_a, delivery_id=delivery2.id,
                chunks=[b"PK\x03\x04incoming-task28-two"], document_type="xlsx",
            )
            sealed2 = artifacts.seal_incoming(staged2, delivery_id=delivery2.id)
            incoming2 = await repo.register_artifact(
                project_id=project, wp_id=wp_a, kind=ArtifactKind.incoming,
                state=ArtifactState.durable, relative_path=sealed2.relative_path,
                sha256=sealed2.sha256, size_bytes=sealed2.size_bytes,
                document_type="xlsx", source_delivery_id=delivery2.id,
            )
            case_claim = await repo.create_recovery_case(
                project_id=project, wp_id=wp_a, entry_id=ENTRY, room_id=world["room"],
                generation=1, source_delivery_key=_d("task28-delivery-key-2"),
                incoming_artifact_id=incoming2.id,
                reason=RecoveryReason.crash_close,
            )
            await s.commit()
            world.update(
                case=case.id,
                case_claim=case_claim.id,
                incoming_artifact=incoming_art.id,
                delivery=delivery_id,
            )

        # ── 单独一个 room 后退役它的 scope 行（tombstone 判据）
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            # generation=2：`uq_wpoor_generation` 是 `(wp_id, entry_id, generation)`，
            # 与上面那个 generation=1 的 room 撞键。退役判据与 generation 无关。
            doomed = await repo.create_room(
                project_id=project, wp_id=wp_a, entry_id=ENTRY,
                doc_key="task28-dockey-retired", generation=2,
                opened_base_version_id=entry_a["cv"],
            )
            await repo.retire_scope(
                resource_kind=ScopeResourceKind.room, resource_id=str(doomed.id)
            )
            await s.commit()
            world.update(retired_room=doomed.id)

        snap["world"] = {
            k: (str(v) if not isinstance(v, dict) else {kk: str(vv) for kk, vv in v.items()})
            for k, v in world.items()
        }

        # ═══ ASGI app
        board = _Switchboard()
        app = FastAPI()
        # 🔴 装上生产中间件：`{code,message,data}` 信封与 callback 的跳过规则都是
        # **对外契约**的一部分。不装的话本文件断言的 body 形状与生产不同，
        # 「只在 API 层拆一次信封」这条也无从验证。
        from app.middleware.response import ResponseWrapperMiddleware

        app.add_middleware(ResponseWrapperMiddleware)
        app.include_router(SR.router)
        app.include_router(SR.public_router)

        class _User:
            def __init__(self, uid: uuid.UUID) -> None:
                self.id = uid

        current: dict[str, Any] = {"user": _User(user_a)}

        async def _override_db():
            async with Session() as s:
                yield s

        async def _override_user():
            user = current["user"]
            if user is None:
                raise HTTPException(status_code=401, detail="未认证")
            return user

        async def _services_override(
            db=Depends(get_db), user=Depends(get_current_user)
        ):
            from dataclasses import replace

            base_svc = SR.build_sync_services(db, user)
            repo = WorkpaperSyncRepository(db)
            rooms = RoomService(repo)
            return replace(
                base_svc,
                repo=repo,
                rooms=rooms,
                requests=RequestApplicationService(repo, rooms),
                probe=board,  # type: ignore[arg-type]
                guard=SyncEndpointGuard(
                    repository=repo,
                    visibility=board,
                    authorize=board.authorize,
                    claim_codec=ScopeClaimCodec("task28-pg-secret"),
                    read_only_actions=SR._READ_ONLY_ACTIONS,
                ),
            )

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[SR._services] = _services_override

        prefix = f"/api/projects/{project}/workpapers/{wp_a}/sync/entries/{ENTRY}"
        prefix_b = f"/api/projects/{project}/workpapers/{wp_b}/sync/entries/{ENTRY}"

        async def _counts() -> dict[str, int]:
            async with Session() as s:
                out: dict[str, int] = {}
                for label, model in (
                    ("request", WorkpaperForcesaveRequest),
                    ("operation", WorkpaperSyncOperation),
                    ("application", WorkpaperContentApplication),
                    ("scope", WorkpaperSyncScopeIndex),
                ):
                    out[label] = int(
                        (
                            await s.execute(sa.select(sa.func.count()).select_from(model))
                        ).scalar_one()
                    )
                return out

        scen = snap["scenarios"]
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://task28.local"
        ) as client:
            # ── S1 未认证 → 401（唯一 401 来源）
            try:
                current["user"] = None
                r = await client.get(f"{prefix}/operations/{uuid.uuid4()}")
                scen["unauthenticated"] = {"status": r.status_code}
            except Exception as exc:  # noqa: BLE001
                _phase_failed("unauthenticated", exc)
            finally:
                current["user"] = _User(user_a)

            # ── S2 统一 404 oracle 的五条来源
            try:
                oracle: dict[str, Any] = {}
                r = await client.get(f"{prefix}/operations/{uuid.uuid4()}")
                oracle["missing"] = {"status": r.status_code, "body": r.text}
                r = await client.post(
                    f"{prefix_b}/rooms/{world['room']}/forcesave",
                    json={"participant_id": str(world["participant_a"])},
                    headers={"Idempotency-Key": "cross-scope-1"},
                )
                oracle["cross_scope"] = {"status": r.status_code, "body": r.text}
                r = await client.post(
                    f"{prefix}/rooms/{world['retired_room']}/forcesave",
                    json={"participant_id": str(world["participant_a"])},
                    headers={"Idempotency-Key": "retired-1"},
                )
                oracle["retired"] = {"status": r.status_code, "body": r.text}
                board.project_visible = False
                r = await client.get(f"{prefix}/operations/{uuid.uuid4()}")
                oracle["invisible"] = {"status": r.status_code, "body": r.text}
                board.project_visible = True
                r = await client.post(
                    f"{prefix}/versions/1/rollback",
                    json={"confirmed": True, "expected_current_revision": 1},
                )
                oracle["numeric_revision"] = {"status": r.status_code, "body": r.text}
                scen["not_found_oracle"] = oracle
            except Exception as exc:  # noqa: BLE001
                board.project_visible = True
                _phase_failed("not_found_oracle", exc)

            # ── S3 403：workflow 锁定下写 action 拒绝、读 action 放行
            try:
                board.workflow_locked = True
                w = await client.post(
                    f"{prefix}/rooms/{world['room']}/forcesave",
                    json={"participant_id": str(world["participant_a"])},
                    headers={"Idempotency-Key": "locked-1"},
                )
                rd = await client.get(
                    f"{prefix}/recovery-cases",
                    params={"room_id": str(world["room"]), "generation": 1},
                )
                board.workflow_locked = False
                scen["workflow_lock"] = {
                    "write_status": w.status_code,
                    "write_body": w.text,
                    "read_status": rd.status_code,
                }
            except Exception as exc:  # noqa: BLE001
                board.workflow_locked = False
                _phase_failed("workflow_lock", exc)

            # ── S4 pending-mutations 不推进 content revision
            try:
                async def _revision() -> int:
                    async with Session() as s:
                        return int(
                            (
                                await s.execute(
                                    sa.text(
                                        "SELECT file_version FROM working_paper "
                                        "WHERE id = CAST(:w AS uuid)"
                                    ).bindparams(w=str(wp_a))
                                )
                            ).scalar_one()
                        )

                before = await _revision()
                r = await client.post(
                    f"{prefix}/pending-mutations",
                    json={
                        "sheet_key": "d2-detail",
                        "expected_revision": before,
                        "projection": None,
                    },
                    headers={"Idempotency-Key": "flush-1"},
                )
                scen["pending_mutation"] = {
                    "status": r.status_code,
                    "body": r.text[:600],
                    "revision_before": before,
                    "revision_after": await _revision(),
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("pending_mutation", exc)

            # ── S5 forcesave：202 + shell(application_id NULL) + 同 key 重放 + 跨 participant 409
            try:
                key = "forcesave-shared-key"
                first = await client.post(
                    f"{prefix}/rooms/{world['room']}/forcesave",
                    json={"participant_id": str(world["participant_a"])},
                    headers={"Idempotency-Key": key},
                )
                replay = await client.post(
                    f"{prefix}/rooms/{world['room']}/forcesave",
                    json={"participant_id": str(world["participant_a"])},
                    headers={"Idempotency-Key": key},
                )
                cross = await client.post(
                    f"{prefix}/rooms/{world['room']}/forcesave",
                    json={"participant_id": str(world["participant_b"])},
                    headers={"Idempotency-Key": key},
                )
                shell_app: Any = "<no-first>"
                request_rows = 0
                if first.status_code == 202:
                    op_id = uuid.UUID(first.json()["data"]["operation_id"])
                    async with Session() as s:
                        shell_app = (
                            await s.execute(
                                sa.select(WorkpaperSyncOperation.application_id).where(
                                    WorkpaperSyncOperation.id == op_id
                                )
                            )
                        ).scalar_one()
                        request_rows = int(
                            (
                                await s.execute(
                                    sa.select(sa.func.count())
                                    .select_from(WorkpaperForcesaveRequest)
                                    .where(
                                        WorkpaperForcesaveRequest.idempotency_key == key
                                    )
                                )
                            ).scalar_one()
                        )
                scen["forcesave"] = {
                    "first_status": first.status_code,
                    "first_body": first.text[:800],
                    "replay_status": replay.status_code,
                    "replay_body": replay.text[:800],
                    "cross_status": cross.status_code,
                    "cross_body": cross.text[:800],
                    "shell_application_id": (
                        None if shell_app is None else str(shell_app)
                    ),
                    "request_rows_for_key": request_rows,
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("forcesave", exc)

            # ── S6 撤权后同 key 重放：403 + 零副作用
            try:
                before_counts = await _counts()
                board.action_allowed = False
                r = await client.post(
                    f"{prefix}/rooms/{world['room']}/forcesave",
                    json={"participant_id": str(world["participant_a"])},
                    headers={"Idempotency-Key": "forcesave-shared-key"},
                )
                board.action_allowed = True
                scen["revoked_replay"] = {
                    "status": r.status_code,
                    "body": r.text[:400],
                    "counts_before": before_counts,
                    "counts_after": await _counts(),
                }
            except Exception as exc:  # noqa: BLE001
                board.action_allowed = True
                _phase_failed("revoked_replay", exc)

            # ── S7 recovery list：claim 前三实体为 0；generation 不符 / 缺 → 拒绝
            try:
                ok = await client.get(
                    f"{prefix}/recovery-cases",
                    params={"room_id": str(world["room"]), "generation": 1},
                )
                bad_gen = await client.get(
                    f"{prefix}/recovery-cases",
                    params={"room_id": str(world["room"]), "generation": 99},
                )
                missing_gen = await client.get(
                    f"{prefix}/recovery-cases", params={"room_id": str(world["room"])}
                )
                scen["recovery_list"] = {
                    "ok_status": ok.status_code,
                    "ok_body": ok.text[:2000],
                    "bad_generation_status": bad_gen.status_code,
                    "bad_generation_body": bad_gen.text,
                    "missing_generation_status": missing_gen.status_code,
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("recovery_list", exc)

            # ── S8 download-only：三实体保持 0 + 签发 claim + claim 消费/跨 scope 拒绝
            try:
                before_counts = await _counts()
                dl = await client.post(
                    f"{prefix}/recovery-cases/{world['case']}/download-only"
                )
                after_counts = await _counts()
                claim_token = (
                    dl.json()["data"]["download_claim"] if dl.status_code == 200 else None
                )
                good = await client.get(
                    f"{prefix}/recovery-cases/{world['case']}/download",
                    params={"claim": claim_token or "not-a-claim"},
                )
                no_claim = await client.get(
                    f"{prefix}/recovery-cases/{world['case']}/download"
                )
                cross = await client.get(
                    f"{prefix_b}/recovery-cases/{world['case']}/download",
                    params={"claim": claim_token or "not-a-claim"},
                )
                scen["download_only"] = {
                    "status": dl.status_code,
                    "body": dl.text[:600],
                    "counts_before": before_counts,
                    "counts_after": after_counts,
                    "download_status": good.status_code,
                    "download_body": good.text[:800],
                    "no_claim_status": no_claim.status_code,
                    "cross_scope_status": cross.status_code,
                    "cross_scope_body": cross.text,
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("download_only", exc)

            # ── S9 rollback：两个 wp 的 revision 1 由不同 UUID 定位、互不可见
            try:
                foreign = await client.post(
                    f"{prefix}/versions/{entry_b['cv']}/rollback",
                    json={"confirmed": True, "expected_current_revision": 1},
                )
                unconfirmed = await client.post(
                    f"{prefix}/versions/{entry_a['cv']}/rollback",
                    json={"expected_current_revision": 1},
                )
                own = await client.post(
                    f"{prefix}/versions/{entry_a['cv']}/rollback",
                    json={"confirmed": True, "expected_current_revision": 1},
                )
                async with Session() as s:
                    revisions = [
                        int(x)
                        for x in (
                            await s.execute(
                                sa.text(
                                    "SELECT revision FROM working_paper_content_version "
                                    "ORDER BY revision"
                                )
                            )
                        ).scalars()
                    ]
                scen["rollback"] = {
                    "other_wp_status": foreign.status_code,
                    "other_wp_body": foreign.text,
                    "unconfirmed_status": unconfirmed.status_code,
                    "unconfirmed_body": unconfirmed.text[:400],
                    "same_wp_status": own.status_code,
                    "same_wp_body": own.text[:600],
                    "version_ids_differ": str(entry_a["cv"]) != str(entry_b["cv"]),
                    "numeric_revisions": revisions,
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("rollback", exc)

            # ── S10 scope tombstone：物理行仍在且 `retired_at` 已设
            try:
                async with Session() as s:
                    row = (
                        await s.execute(
                            sa.select(
                                WorkpaperSyncScopeIndex.resource_id,
                                WorkpaperSyncScopeIndex.retired_at,
                            ).where(
                                WorkpaperSyncScopeIndex.resource_id
                                == str(world["retired_room"])
                            )
                        )
                    ).first()
                scen["tombstone"] = {
                    "row_present": row is not None,
                    "retired_at_set": bool(row is not None and row[1] is not None),
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("tombstone", exc)

            # ── S11 authorization-first claim：claim 前三实体为 0，claim 后落成 primary
            try:
                async def _case_entities(case_id: uuid.UUID) -> dict[str, Any]:
                    async with Session() as s:
                        row = (
                            await s.execute(
                                sa.text(
                                    "SELECT state, recovery_request_id, operation_id, "
                                    "application_id FROM "
                                    "working_paper_callback_recovery_case "
                                    "WHERE id = CAST(:c AS uuid)"
                                ).bindparams(c=str(case_id))
                            )
                        ).first()
                    return {
                        "state": None if row is None else str(row[0]),
                        "request": None if row is None else _opt(row[1]),
                        "operation": None if row is None else _opt(row[2]),
                        "application": None if row is None else _opt(row[3]),
                    }

                before_entities = await _case_entities(world["case_claim"])
                before_counts = await _counts()
                claim = await client.post(
                    f"{prefix}/recovery-cases/{world['case_claim']}/claim",
                    json={
                        "participant_id": str(world["participant_a"]),
                        "prior_confirmation_id": str(world["confirmation_a"]),
                        "room_id": str(world["room"]),
                        "expected_current_revision": 1,
                    },
                    headers={"Idempotency-Key": "claim-1"},
                )
                scen["recovery_claim"] = {
                    "status": claim.status_code,
                    "body": claim.text[:800],
                    "entities_before": before_entities,
                    "entities_after": await _case_entities(world["case_claim"]),
                    "counts_before": before_counts,
                    "counts_after": await _counts(),
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("recovery_claim", exc)

            # ── S12 claim 的 room 归属核对：客户端提交别的 room ⇒ 同 404
            try:
                r = await client.post(
                    f"{prefix}/recovery-cases/{world['case_claim']}/claim",
                    json={
                        "participant_id": str(world["participant_a"]),
                        "prior_confirmation_id": str(world["confirmation_a"]),
                        "room_id": str(world["retired_room"]),
                        "expected_current_revision": 1,
                    },
                    headers={"Idempotency-Key": "claim-wrong-room"},
                )
                scen["claim_room_mismatch"] = {"status": r.status_code, "body": r.text}
            except Exception as exc:  # noqa: BLE001
                _phase_failed("claim_room_mismatch", exc)

            # ── S13 close_capture 不得由客户端直接发起
            try:
                r = await client.post(
                    f"{prefix}/rooms/{world['room']}/forcesave",
                    json={
                        "participant_id": str(world["participant_a"]),
                        "kind": "close_capture",
                    },
                    headers={"Idempotency-Key": "close-capture-attempt"},
                )
                scen["close_capture_forbidden"] = {
                    "status": r.status_code,
                    "body": r.text[:400],
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("close_capture_forbidden", exc)

            # ── S14 服务凭证 callback route：已挂载、信封被跳过、pre-durable 非零 ack
            #
            # 🔴 这一条是**唯一**证明新 callback 端点真的可达的判据。其余关于它的判据都是
            # AST 形态（调用链、不 jwt.decode），而形态判据无法区分「挂上了」与「写好了但
            # 没注册」—— 本 spec 的 legacy 侧就有 30 条测试正因为 harness 只
            # `include_router(router)` 而全部拿到 404（`public_router` 没挂）。
            try:
                from app.models.workpaper_sync_models import WorkpaperCallbackDelivery

                async def _delivery_count() -> int:
                    async with Session() as s:
                        return int(
                            (
                                await s.execute(
                                    sa.select(sa.func.count()).select_from(
                                        WorkpaperCallbackDelivery
                                    )
                                )
                            ).scalar_one()
                        )

                before_deliveries = await _delivery_count()
                cb_path = f"/api/workpaper-sync/rooms/{world['room']}/onlyoffice-callback"
                no_auth = await client.post(
                    cb_path, json={"status": 6, "key": "task28-dockey", "url": "http://x/y"}
                )
                bogus_auth = await client.post(
                    cb_path,
                    headers={"Authorization": "Bearer not-a-real-jwt"},
                    json={"status": 2, "key": "task28-dockey", "url": "http://x/y"},
                )
                scen["service_callback_route"] = {
                    "no_auth_status": no_auth.status_code,
                    "no_auth_body": no_auth.text[:400],
                    "bogus_auth_status": bogus_auth.status_code,
                    "bogus_auth_body": bogus_auth.text[:400],
                    "deliveries_before": before_deliveries,
                    "deliveries_after": await _delivery_count(),
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("service_callback_route", exc)

        snap["counts_final"] = await _counts()
        snap["probe_calls"] = len(board.probe_calls)
        snap["authorize_calls"] = len(board.authorize_calls)
    except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言为空
        snap["harness_errors"].setdefault("bootstrap", _err(exc))
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


# ═══════════════════════════════════════════════════════════════════════════
# 判据
# ═══════════════════════════════════════════════════════════════════════════

#: 平台统一不可见响应体（与 `wp_visibility.denial.EXTERNAL_NOT_FOUND_DETAIL` 同一份）。
def _unified_404_body() -> str:
    from app.services.wp_visibility.denial import EXTERNAL_NOT_FOUND_DETAIL

    return json.dumps({"detail": EXTERNAL_NOT_FOUND_DETAIL}, ensure_ascii=False)


class TestHarnessIntegrity:
    """采集自身没崩 —— 这是所有其它判据的分母。"""

    def test_migration_applied_cleanly(self, snap: dict[str, Any]) -> None:
        assert snap["apply_errors"] == []
        assert "PostgreSQL" in str(snap["server_version"])

    def test_no_phase_crashed_during_collection(self, snap: dict[str, Any]) -> None:
        """采集阶段异常被记录而不是穿透；此处断言它们为空。

        🔴 若允许穿透，整个 module 会变成 collection ERROR，而 `-rf` 只列 FAILED ⇒
        定向变异看不到预期失败项 ⇒ 判 GREEN。这条是那个决定的另一半。
        """
        assert snap["harness_errors"] == {}, snap["harness_errors"]

    def test_every_scenario_was_collected(self, snap: dict[str, Any]) -> None:
        expected = {
            "unauthenticated",
            "not_found_oracle",
            "workflow_lock",
            "pending_mutation",
            "forcesave",
            "revoked_replay",
            "recovery_list",
            "download_only",
            "rollback",
            "tombstone",
            "recovery_claim",
            "claim_room_mismatch",
            "close_capture_forbidden",
            "service_callback_route",
        }
        assert set(snap["scenarios"]) == expected

    def test_the_probe_really_ran(self, snap: dict[str, Any]) -> None:
        """visibility 探针必须真被调用过 —— 硬编码放行的探针在这里露馅。"""
        assert int(snap["probe_calls"]) > 10, snap["probe_calls"]
        assert int(snap["authorize_calls"]) > 5, snap["authorize_calls"]


class TestUnifiedNotFoundOracle:
    """Property 45：五种原因的 404 **逐字节相同**。"""

    def test_all_five_causes_return_404(self, snap: dict[str, Any]) -> None:
        oracle = snap["scenarios"]["not_found_oracle"]
        assert set(oracle) == {
            "missing",
            "cross_scope",
            "retired",
            "invisible",
            "numeric_revision",
        }
        for cause, observed in sorted(oracle.items()):
            assert observed["status"] == 404, f"{cause} 返回 {observed['status']}"

    def test_all_five_bodies_are_byte_identical(self, snap: dict[str, Any]) -> None:
        """文案差异就是存在性预言机 —— 判据是**集合大小为 1**。"""
        bodies = {v["body"] for v in snap["scenarios"]["not_found_oracle"].values()}
        assert len(bodies) == 1, f"404 响应体出现 {len(bodies)} 种：{sorted(bodies)}"

    def test_the_body_is_the_platform_wide_unified_detail(
        self, snap: dict[str, Any]
    ) -> None:
        """不只是「五种一致」，还必须**等于平台统一 404**（否则同步域自成一套）。"""
        (body,) = {v["body"] for v in snap["scenarios"]["not_found_oracle"].values()}
        assert json.loads(body) == json.loads(_unified_404_body())

    def test_numeric_revision_as_a_route_key_is_404_not_422(
        self, snap: dict[str, Any]
    ) -> None:
        """`/versions/1/rollback` 必须落进 404 oracle。

        声明 `version_id: uuid.UUID` 时 FastAPI 会先拦成 **422**，那与 404 不同桶
        （攻击者据此区分「格式错」与「不存在」）。所以路由把它声明为 `str`，
        由 guard 的 `OpaqueResourceIdRequiredError` 判定。
        """
        observed = snap["scenarios"]["not_found_oracle"]["numeric_revision"]
        assert observed["status"] == 404
        assert json.loads(observed["body"]) == json.loads(_unified_404_body())

    def test_unauthenticated_is_401_and_never_folded_into_404(
        self, snap: dict[str, Any]
    ) -> None:
        assert snap["scenarios"]["unauthenticated"]["status"] == 401


class TestForbiddenIsDistinctFromNotFound:
    def test_workflow_lock_refuses_writes_with_403(self, snap: dict[str, Any]) -> None:
        lock = snap["scenarios"]["workflow_lock"]
        assert lock["write_status"] == 403
        assert "sync_workflow_locked" in lock["write_body"]

    def test_workflow_lock_still_allows_reads(self, snap: dict[str, Any]) -> None:
        """归档/复核通过的底稿仍要能查 recovery cases（AC 11.6 / 11.11）。

        🔴 首轮真库实测这里是 **403** —— guard 无条件按 `workflow_locked` 拒绝。
        离线守卫当时只测了写 action 的否定侧，所以全绿。
        """
        assert snap["scenarios"]["workflow_lock"]["read_status"] == 200

    def test_client_may_not_initiate_a_close_capture(self, snap: dict[str, Any]) -> None:
        """AC 4.4：`close_capture` 只能由 room arbiter 在锁内 CAS 产生。"""
        observed = snap["scenarios"]["close_capture_forbidden"]
        assert observed["status"] == 403
        assert "close_capture_forbidden" in observed["body"]


class TestFlushDoesNotAdvanceRevision:
    def test_pending_mutation_leaves_content_revision_untouched(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 3.1：flush 只创建 pending mutation。"""
        observed = snap["scenarios"]["pending_mutation"]
        assert observed["revision_before"] == observed["revision_after"]

    def test_an_entry_without_an_approved_adapter_fails_visible(
        self, snap: dict[str, Any]
    ) -> None:
        """registry 零注册 / capability 非 bidirectional ⇒ 422 且**不**创建 pending mutation。

        `build_production_registry()` 当前刻意零注册（逐 entry adapter 属 Tasks 40~57 /
        62~64），manifest 里这个 entry 的 capability 也是 `single_onlyoffice`。
        正确行为是 fail visible：静默成功会让审计师以为内容已进 OO（AC 3.9 / 1.7）。
        """
        observed = snap["scenarios"]["pending_mutation"]
        assert observed["status"] == 422, observed["body"]
        assert "bidirectional" in observed["body"] or "adapter" in observed["body"]


class TestForcesaveCompositeIdempotency:
    """AC 4.1 / Property 45：`(room, generation, participant, kind, key)` + fingerprint。"""

    def test_accepted_returns_202_with_a_nullable_application_shell(
        self, snap: dict[str, Any]
    ) -> None:
        observed = snap["scenarios"]["forcesave"]
        assert observed["first_status"] == 202, observed["first_body"]
        assert observed["shell_application_id"] is None, (
            "accepted 响应里的 operation 必须是 `application_id=NULL` 的 shell —— "
            "accepted 前预建 application 违反 AC 4.1"
        )

    def test_the_envelope_is_the_platform_wrapper(self, snap: dict[str, Any]) -> None:
        """2xx JSON 只在 API 层被包一次 `{code,message,data}`。"""
        body = json.loads(snap["scenarios"]["forcesave"]["first_body"])
        assert set(body) == {"code", "message", "data"}
        assert body["code"] == 202
        assert "operation_id" in body["data"]
        assert not isinstance(body["data"].get("data"), dict), "信封被包了两层"

    def test_same_participant_same_key_replays_to_the_same_ids(
        self, snap: dict[str, Any]
    ) -> None:
        observed = snap["scenarios"]["forcesave"]
        assert observed["replay_status"] == 202
        first = json.loads(observed["first_body"])["data"]
        replay = json.loads(observed["replay_body"])["data"]
        assert replay["forcesave_request_id"] == first["forcesave_request_id"]
        assert replay["operation_id"] == first["operation_id"]
        assert observed["request_rows_for_key"] == 1, (
            "同 key 重放创建了第二条 request 行 —— 复合幂等键失效"
        )

    def test_another_participant_reusing_the_key_gets_409(
        self, snap: dict[str, Any]
    ) -> None:
        observed = snap["scenarios"]["forcesave"]
        assert observed["cross_status"] == 409, observed["cross_body"]
        assert "idempotency_conflict" in observed["cross_body"]

    def test_the_409_body_leaks_no_existing_identifier(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 4.1 明文：跨 participant 复用同 key「不得返回已有标识」。"""
        observed = snap["scenarios"]["forcesave"]
        first = json.loads(observed["first_body"])["data"]
        for leaked in (first["forcesave_request_id"], first["operation_id"]):
            assert leaked not in observed["cross_body"], (
                f"409 响应体泄露了已有标识 {leaked}"
            )


class TestRevokedReplayHasZeroSideEffects:
    """Property 45 末段：首次成功后撤权，同 key 重放零泄露、零副作用。"""

    def test_the_replay_is_refused_with_403(self, snap: dict[str, Any]) -> None:
        assert snap["scenarios"]["revoked_replay"]["status"] == 403

    def test_no_row_was_created_or_changed(self, snap: dict[str, Any]) -> None:
        observed = snap["scenarios"]["revoked_replay"]
        assert observed["counts_before"] == observed["counts_after"], (
            f"撤权重放产生了副作用：{observed['counts_before']} -> "
            f"{observed['counts_after']}"
        )

    def test_the_cached_identifiers_are_not_returned(self, snap: dict[str, Any]) -> None:
        forcesave = json.loads(snap["scenarios"]["forcesave"]["first_body"])["data"]
        body = snap["scenarios"]["revoked_replay"]["body"]
        for leaked in (forcesave["forcesave_request_id"], forcesave["operation_id"]):
            assert leaked not in body, f"撤权后重放泄露了 cached 标识 {leaked}"


class TestRecoveryListRequiresExplicitRoomAndGeneration:
    def test_the_happy_path_returns_candidate_summaries(
        self, snap: dict[str, Any]
    ) -> None:
        observed = snap["scenarios"]["recovery_list"]
        assert observed["ok_status"] == 200
        payload = json.loads(observed["ok_body"])["data"]
        assert payload["cases"], "列表为空 —— 采集时建的 recovery case 没被读出来"
        for case in payload["cases"]:
            assert case["candidate_prior_confirmations"], (
                "AC 5.8 要求返回候选 prior confirmation 摘要"
            )

    def test_claim_free_cases_report_all_three_entities_as_null(
        self, snap: dict[str, Any]
    ) -> None:
        """claim 前 request/application/operation 三者全空（AC 5.8 / Property 45）。"""
        payload = json.loads(snap["scenarios"]["recovery_list"]["ok_body"])["data"]
        unclaimed = [c for c in payload["cases"] if c["state"] == "unclaimed"]
        assert unclaimed, "没有 unclaimed case，本判据失去分母"
        for case in unclaimed:
            assert case["operation_id"] is None
            assert case["application_id"] is None
            assert case["forcesave_request_id"] is None

    def test_the_response_carries_no_business_content(self, snap: dict[str, Any]) -> None:
        """AC 5.8：不返回业务内容。artifact 路径/hash 一律不得出现。"""
        body = snap["scenarios"]["recovery_list"]["ok_body"]
        for banned in ("relative_path", "artifact_sha256", "incoming_artifact_id"):
            assert banned not in body, f"recovery list 泄露了 {banned}"

    def test_a_generation_that_does_not_match_the_scope_index_is_404(
        self, snap: dict[str, Any]
    ) -> None:
        observed = snap["scenarios"]["recovery_list"]
        assert observed["bad_generation_status"] == 404
        assert json.loads(observed["bad_generation_body"]) == json.loads(
            _unified_404_body()
        )

    def test_omitting_generation_is_refused(self, snap: dict[str, Any]) -> None:
        """AC 10.6：recovery list 必须显式带 room/generation。"""
        assert snap["scenarios"]["recovery_list"]["missing_generation_status"] == 422


class TestDownloadOnlyKeepsAllThreeEntitiesAtZero:
    def test_termination_succeeds(self, snap: dict[str, Any]) -> None:
        assert snap["scenarios"]["download_only"]["status"] == 200

    def test_no_request_application_or_operation_was_created(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 5.8：download-only 永远零三实体。"""
        observed = snap["scenarios"]["download_only"]
        assert observed["counts_before"] == observed["counts_after"], (
            f"download-only 产生了实体：{observed['counts_before']} -> "
            f"{observed['counts_after']}"
        )

    def test_the_signed_claim_is_consumable(self, snap: dict[str, Any]) -> None:
        """签发的 claim 必须有真实消费方 —— 没有消费方的签名就是死代码。"""
        observed = snap["scenarios"]["download_only"]
        assert observed["download_status"] == 200, observed["download_body"]

    def test_a_missing_claim_is_refused(self, snap: dict[str, Any]) -> None:
        assert snap["scenarios"]["download_only"]["no_claim_status"] == 422

    def test_a_claim_from_another_wp_scope_is_404(self, snap: dict[str, Any]) -> None:
        observed = snap["scenarios"]["download_only"]
        assert observed["cross_scope_status"] == 404
        assert json.loads(observed["cross_scope_body"]) == json.loads(
            _unified_404_body()
        )


class TestOpaqueVersionIdRollback:
    def test_two_workpapers_both_have_numeric_revision_one(
        self, snap: dict[str, Any]
    ) -> None:
        """Property 45 的前提：numeric revision 真的碰撞（否则判据没有分母）。"""
        revisions = snap["scenarios"]["rollback"]["numeric_revisions"]
        assert revisions.count(1) >= 2, revisions
        assert snap["scenarios"]["rollback"]["version_ids_differ"] is True

    def test_another_workpapers_version_uuid_is_404_here(
        self, snap: dict[str, Any]
    ) -> None:
        observed = snap["scenarios"]["rollback"]
        assert observed["other_wp_status"] == 404
        assert json.loads(observed["other_wp_body"]) == json.loads(_unified_404_body())

    def test_rollback_requires_a_second_confirmation(self, snap: dict[str, Any]) -> None:
        """design §API：需编辑权限**和二次确认**。"""
        observed = snap["scenarios"]["rollback"]
        assert observed["unconfirmed_status"] == 422
        assert "rollback_confirmation_required" in observed["unconfirmed_body"]

    def test_rollback_without_a_registered_adapter_fails_visible(
        self, snap: dict[str, Any]
    ) -> None:
        """本 entry 尚无 approved adapter ⇒ 422（不得静默「回滚成功」）。"""
        assert snap["scenarios"]["rollback"]["same_wp_status"] == 422


class TestScopeTombstone:
    def test_the_retired_scope_row_is_physically_preserved(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 10.6：child 退役只设 `retired_at`，tombstone 永久保留（防 id 复用）。"""
        observed = snap["scenarios"]["tombstone"]
        assert observed["row_present"] is True
        assert observed["retired_at_set"] is True

    def test_a_retired_resource_reads_like_a_nonexistent_one(
        self, snap: dict[str, Any]
    ) -> None:
        """行还在，但用户看到的与「不存在」逐字节相同。"""
        oracle = snap["scenarios"]["not_found_oracle"]
        assert oracle["retired"]["body"] == oracle["missing"]["body"]


class TestAuthorizationFirstRecoveryClaim:
    """AC 5.8 / 10.6：claim 在一个事务里创建 request + shell + application + scope rows。"""

    def test_all_three_entities_are_null_before_the_claim(
        self, snap: dict[str, Any]
    ) -> None:
        before = snap["scenarios"]["recovery_claim"]["entities_before"]
        assert before["state"] == "unclaimed"
        assert before["request"] is None
        assert before["operation"] is None
        assert before["application"] is None

    def test_the_claim_binds_all_three_in_one_transaction(
        self, snap: dict[str, Any]
    ) -> None:
        observed = snap["scenarios"]["recovery_claim"]
        assert observed["status"] == 202, observed["body"]
        after = observed["entities_after"]
        assert after["state"] == "application_created"
        for key in ("request", "operation", "application"):
            assert after[key] is not None, f"claim 后 {key} 仍为空"

    def test_the_response_reports_the_bound_identifiers(
        self, snap: dict[str, Any]
    ) -> None:
        observed = snap["scenarios"]["recovery_claim"]
        payload = json.loads(observed["body"])["data"]
        after = observed["entities_after"]
        assert payload["forcesave_request_id"] == after["request"]
        assert payload["operation_id"] == after["operation"]
        assert payload["application_id"] == after["application"]

    def test_scope_rows_are_created_alongside_the_children(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 10.6：每个 child 与 scope row **同事务**创建。

        判据是增量比对：claim 新建 request + operation + application 三个 child，
        scope index 必须同步多出**恰好** 3 行。少于 3 意味着某个 child 没有归属行
        （之后任何人都能跨 scope 读它）。
        """
        observed = snap["scenarios"]["recovery_claim"]
        before, after = observed["counts_before"], observed["counts_after"]
        children = (
            (after["request"] - before["request"])
            + (after["operation"] - before["operation"])
            + (after["application"] - before["application"])
        )
        assert children == 3, children
        assert after["scope"] - before["scope"] == children, (
            f"child 新增 {children} 个，scope 行只新增 "
            f"{after['scope'] - before['scope']} 个"
        )

    def test_a_client_supplied_foreign_room_is_404(self, snap: dict[str, Any]) -> None:
        """room 归属取自 scope index；客户端提交的 room 只做事后核对。"""
        observed = snap["scenarios"]["claim_room_mismatch"]
        assert observed["status"] == 404
        assert json.loads(observed["body"]) == json.loads(_unified_404_body())


class TestServiceScopeCallbackRoute:
    """新 callback 端点：服务凭证、独立契约、pre-durable 非零 ack、零副作用。

    Task 28 bullet 4：「旧 config/callback URL 只委派新服务；callback 单独校验 room/
    generation/doc_key/route token，不伪造 participant attribution」。

    🔴 本类是**唯一**证明该端点真的可达的判据。其余关于它的判据全是 AST 形态
    （调用链、不 `jwt.decode`、路径含 `onlyoffice-callback`），而形态判据分不清
    「挂载了」与「写好了但没注册」—— 本 spec 的 legacy 侧就有 30 条测试正因为 harness
    只 `include_router(router)`（`public_router` 未挂）而全部拿到 404。
    """

    def test_the_route_is_mounted_and_not_a_user_404(self, snap: dict[str, Any]) -> None:
        observed = snap["scenarios"]["service_callback_route"]
        for label in ("no_auth_status", "bogus_auth_status"):
            assert observed[label] == 200, (
                f"{label}={observed[label]} —— DocServer 侧一律 HTTP 200 + 顶层 "
                "`{\"error\": N}`；404/401/403 说明端点没挂或误用了用户契约"
            )

    def test_a_pre_durable_rejection_returns_a_non_zero_ack(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 5.7：durable **前**的失败必须回非零，让 OO 重投而不是当成已保存。"""
        observed = snap["scenarios"]["service_callback_route"]
        for label in ("no_auth_body", "bogus_auth_body"):
            body = json.loads(observed[label])
            assert body.get("error") not in (0, None), (
                f"{label}={observed[label]} —— 未通过 route 凭证校验却回了 error=0，"
                "等于让 OO 认为已保存"
            )

    def test_the_response_envelope_is_not_wrapped(self, snap: dict[str, Any]) -> None:
        """OO 协议要求 `{\"error\": N}` 是**顶层**。

        被 `{code,message,data}` 包一层等于回了个 200 空壳 —— OO 读不到 `error` 字段，
        于是把失败当成功。判据落在真实中间件下的响应体上（harness 装了
        `ResponseWrapperMiddleware`），不是只看 `_SKIP_CONTAINS` 的子串。
        """
        observed = snap["scenarios"]["service_callback_route"]
        body = json.loads(observed["no_auth_body"])
        assert set(body) == {"error"}, (
            f"callback 响应体 {body!r} 不是顶层 `{{\"error\": N}}` —— "
            "被信封包住时 OO 读不到 error 字段"
        )
        assert "data" not in body and "code" not in body

    def test_a_rejected_callback_creates_no_delivery_row(
        self, snap: dict[str, Any]
    ) -> None:
        """route 凭证校验失败发生在下载与 delivery 登记**之前**（AC 5.1「下载前拒绝」）。"""
        observed = snap["scenarios"]["service_callback_route"]
        assert observed["deliveries_after"] == observed["deliveries_before"], (
            f"被拒的 callback 仍写了 delivery 行："
            f"{observed['deliveries_before']} → {observed['deliveries_after']}"
        )
