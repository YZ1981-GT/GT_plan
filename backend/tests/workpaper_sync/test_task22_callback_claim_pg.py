# -*- coding: utf-8 -*-
"""Task 22 真实 PostgreSQL 行为守卫：delivery 归属真值表、去重、correlation 与 recovery。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 22
Requirements: 4.3, 4.9, 4.10, 5.1~5.8, 5.11, 5.12, 10.2, 10.3, 10.6~10.9
Properties: P16 / P17 / P18 / P19 / P44 / P45 / P63 / P64

═══ 为什么必须真库（而不是「顺便也跑一下真库」）═══

Task 22 的核心交付物是一张**归属真值表**，而它的唯一真源是 V151 的 6 条 CHECK 与 2 个
trigger。离线守卫只能证明「Python 侧的表自洽」；把表写错、或把库里的约束删掉，离线守卫
一条都不会红。因此本模块的判据形态固定为：

* `allowed` 行 —— 真的 INSERT 进真表，并 `SET CONSTRAINTS ALL IMMEDIATE` 让 deferred
  trigger 也当场表态；
* `forbidden` 行 —— 真的被拒，**且拒它的正是该行 `db_constraint` 声明的那条约束**。

只断言「被拒了」是不够的：一行若被另一条约束偶然挡住，表里的归因就是错的，而下一个人会
据此以为「这条约束还活着」。所以每个 forbidden 行都构造成**只违反自己那一条**（合取组合
不入表，见 `DeliveryOwnershipRow` 的 docstring）。

`DATABASE_URL` 非 PostgreSQL 时**直接失败而不是 skip** —— 与 Task 10/21 同约定：
本任务判据就是数据库行为，skip 等于静默抹掉唯一判据。

═══ 隔离与采集 ═══

scratch schema `tmp_task22_cb_<hex>`，`search_path` 只含它，结束 `DROP SCHEMA CASCADE`。
全部场景由**一次 `asyncio.run`** 跑完落进快照（module fixture）：不给每个测试各自开
async —— 共享连接池会被污染，第二个测试起 `NoneType has no attribute send`。

采集阶段的异常一律**记录不穿透**。理由与 Task 21 相同且已付过代价：异常穿透会把整个
module 变成 collection ERROR，而 pytest 的 `-rf` 只列 FAILED 不列 ERROR ⇒ 变异检验看不到
任何预期失败项 ⇒ 判 GREEN。`test_no_phase_crashed_during_collection` 是这个决定的另一半。
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
import re
import sys
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

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

_SCHEMA_PREFIX = "tmp_task22_cb_"

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
OO_ORIGIN = "http://localhost:8080"
OO_URL_A = f"{OO_ORIGIN}/cache/files/data/t22_6785/output.xlsx/output.xlsx?md5=aaa"
OO_URL_B = f"{OO_ORIGIN}/cache/files/data/t22_6104/output.xlsx/output.xlsx?md5=bbb"


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _opt(value: object) -> str | None:
    """可空 UUID → `str | None`。

    `str(None) == "None"` 是**真值**：用 `str(x)` 投影再 `all(...)` 判空，会把「这一列
    根本没写上」判成「写上了」。Task 21 首轮就有一条变异靠这个投影 bug 蒙过守卫。
    """
    return None if value is None else str(value)


def _err(exc: BaseException) -> str:
    """异常 → 单行诊断，**带最后几帧**。

    只记 `type: message` 时，`NoResultFound: No row was found` 这类消息完全不指向位置
    （`scalar_one()` 在采集里出现十几次），诊断成本极高而收益为零。
    """
    import traceback

    frames = traceback.extract_tb(exc.__traceback__)[-4:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


def _host_is_literal_ip(url: str) -> bool:
    """URL 的 host 是否是**IP 字面量**（v4 或 v6）而不是主机名。

    这才是「已校验 IP 被固定给连接使用」的可判据形态。断言具体某个地址（例如
    `127.0.0.1`）是错的：本机 `getaddrinfo('localhost')` 首个返回 `::1`，
    于是那种断言在 IPv6 优先的环境里必红，而它想证明的性质（不再做第二次解析）
    与具体是哪个地址无关。
    """
    import ipaddress
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or ""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


# ═══════════════════════════════════════════════════════════════════════════
# DB 拒绝原因归因
# ═══════════════════════════════════════════════════════════════════════════

_CONSTRAINT_IN_TEXT = re.compile(r'constraint "([a-z0-9_]+)"')
_CK_IN_TEXT = re.compile(r"\b(ck_[a-z0-9_]+)\b")
_TRIGGER_FN_IN_TEXT = re.compile(r"\b(wpsync_check_[a-z0-9_]+)\b")


def _blame(exc: BaseException) -> dict[str, Any]:
    """把一次 DB 拒绝归因到**具体**约束/trigger。

    三级取值，顺序固定：

    1. asyncpg 的 `constraint_name`（CHECK/UNIQUE/FK 走这条，最可靠）；
    2. 报文里的 `constraint "..."`；
    3. 报文里出现的 `ck_*` 或 `wpsync_check_*` 名字（plpgsql `RAISE EXCEPTION` 只有报文）。

    🔴 不做「取第一个 `ck_` 就算」的简化：真值表要求「**只**违反自己那一条」，所以还要把
    命中的名字**全部**记下来（`mentions`），让守卫能断言「没有第二条约束同时被提到」。
    只记一个名字时，一行同时撞两条约束的情形会被静默归成其中一条。
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
    # 执法点分三类。这条分类是必要的：plpgsql 的 `RAISE EXCEPTION ... USING ERRCODE =
    # 'check_violation'` **不带** constraint 名，报文里也常不含函数名 ⇒ 只按名字归因会把
    # 「trigger 挡住了」判成「没归因到」。而把它和「类型不匹配」混为一谈更糟：42804
    # 是 SQL 写错（探针缺陷），不是约束生效 —— 首轮实测就有一条 quarantine 探针因为
    # 漏了 `CAST` 报 42804，若不分类就会被读成「trigger 工作正常」（WRONG-TEST）。
    if sqlstate == "23505":
        source = "unique"
    elif sqlstate == "23503":
        source = "foreign_key"
    elif sqlstate == "23514":
        source = "check_constraint" if named else "trigger_raise"
    elif sqlstate in ("42804", "42883", "42703", "42P01", "22P02"):
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
# 测试用 OOXML 字节与 transport 替身
# ═══════════════════════════════════════════════════════════════════════════

_XLSX_CT = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="xml" ContentType="application/xml"/>'
    b'<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
    b'officedocument.spreadsheetml.sheet.main+xml"/></Types>'
)
_WORKBOOK = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    b"<sheets><sheet name=\"Sheet1\" sheetId=\"1\" r:id=\"rId1\" xmlns:r=\"http://schemas."
    b'openxmlformats.org/officeDocument/2006/relationships"/></sheets></workbook>'
)


def _xlsx(marker: bytes = b"A") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _XLSX_CT)
        zf.writestr("xl/workbook.xml", _WORKBOOK)
        zf.writestr("xl/marker.bin", marker)
    return buf.getvalue()


class _Response:
    def __init__(self, payload: bytes, *, status: int = 200, ctype: str = "application/zip"):
        self.status_code = status
        self.headers = {"content-type": ctype}
        self._payload = payload

    def iter_bytes(self, chunk_size: int) -> Iterator[bytes]:
        for i in range(0, len(self._payload), max(1, chunk_size)):
            yield self._payload[i : i + chunk_size]


class _Transport:
    """可编程 transport 替身。

    这不是「用 mock 测判据」：被测判据（allowlist / DNS 复核 / 3xx / 流式计数 / sealing）
    全在生产模块内，替身只提供字节与状态码。它换掉的是**网络**，不是判据。
    """

    def __init__(self, payload: bytes, *, status: int = 200) -> None:
        self.payload = payload
        self.status = status
        self.requests: list[Any] = []

    @contextmanager
    def stream(self, request: Any) -> Iterator[_Response]:
        self.requests.append(request)
        yield _Response(self.payload, status=self.status)


async def _collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部 callback 场景
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.workpaper_sync_models import (
        WorkpaperCallbackDelivery,
        WorkpaperCallbackRecoveryCase,
        WorkpaperContentApplication,
        WorkpaperOoRoom,
        WorkpaperSyncOperation,
    )
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.callback_delivery import (
        DELIVERY_OWNERSHIP_TRUTH_TABLE,
        CallbackDeliveryService,
        CallbackStage,
        CallbackStageJournal,
        OwnershipVerdict,
        QuarantineOperationForbiddenError,
        assert_incoming_admissible_for_application,
        build_delivery_key,
        CallbackPayload,
    )
    from app.services.workpaper_sync.callback_download import build_download_policy
    from app.services.workpaper_sync.callback_route import (
        build_callback_url,
        sign_callback_route_token,
    )
    from app.services.workpaper_sync.models import (
        ArtifactKind,
        ArtifactState,
        BundleSlot,
        BundleSlotSpec,
        ParticipantMode,
        RequestKind,
        SyncDomainError,
        compute_application_key,
    )
    from app.services.workpaper_sync.oo_contract import load_callback_contract
    from app.services.workpaper_sync.repository import (
        IdempotencyConflictError,
        WorkpaperSyncRepository,
    )
    from app.services.workpaper_sync.rooms import (
        RoomScope,
        RoomService,
        mint_route_credential,
    )

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 22 的判据是 V151 的 6 条 delivery CHECK + 2 个 trigger 的**真实**行为"
            "（归属真值表逐行归因、delivery_key 唯一、quarantined→application 三层拒绝），"
            f"必须真实 PostgreSQL；当前 DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}。"
            "此处**不 skip** —— skip 等于静默抹掉本任务唯一判据。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    contract = load_callback_contract()
    secret = "task22-callback-route-secret"
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
        "ownership": {},
        "ownership_probe_count": 0,
        "dedupe": {},
        "e2e_request": {},
        "no_fold": {},
        "quarantine": {},
        "recovery": {},
        "failures": {},
        "forcesave_key": {},
    }

    def _phase_failed(name: str, exc: BaseException) -> None:
        snap["harness_errors"][name] = _err(exc)

    engine = None
    tmp_root = Path(os.environ.get("TEMP", "/tmp")) / f"task22-artifacts-{uuid.uuid4().hex[:8]}"
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
            "wp": uuid.uuid4(),
        }
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{ids['project']}')")
            for u in ("user_a", "user_b", "user_v"):
                await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{ids[u]}')")
            await conn.exec_driver_sql(
                "INSERT INTO working_paper (id, project_id) VALUES "
                f"('{ids['wp']}', '{ids['project']}')"
            )

        project_id, wp_id = ids["project"], ids["wp"]
        scope = RoomScope(project_id=project_id, wp_id=wp_id, entry_id=ENTRY)
        base_path = f"storage/{project_id}/workpapers"
        artifacts = CanonicalArtifactRepository(tmp_root)
        # 🔴 策略构造失败必须变成**可见的阶段错误**，不能让它穿透。它会因为「契约上限与
        # 容量预算不再锁死」而抛，而穿透时整个 module 变成 collection ERROR ⇒ pytest 的
        # `-rf` 只列 FAILED 不列 ERROR ⇒ 定向变异（M20 改契约数值）被判 GREEN。
        # 首轮实测就是这样：11 个用例 ERROR、零 FAILED、变异报告显示「守卫没拦住」。
        try:
            policy = build_download_policy(onlyoffice_url=OO_ORIGIN, contract=contract)
        except Exception as exc:  # noqa: BLE001 - 记录而非穿透
            _phase_failed("download_policy", exc)
            snap["policy"] = {"build_error": _err(exc)}
            return snap
        snap["policy"] = {
            "size_cap_bytes": policy.size_cap_bytes,
            "connect_timeout": policy.timeouts.connect_seconds,
            "read_timeout": policy.timeouts.read_seconds,
            "follow_redirects": policy.follow_redirects,
            "max_redirects": policy.max_redirects,
            "dns_recheck": policy.dns_recheck_after_resolve,
        }

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
                source_commit="task22",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation",
                logical_id=f"d2.instrumentation.{tag}",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["instr"].id,
                sha256=_d(f"instr-def-{tag}"),
                structure_hash=_d(f"instr-structure-{tag}"),
                source_commit="task22",
            )
            con = await repo.create_definition_artifact(
                kind="contract",
                logical_id=f"d2.contract.{tag}",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["contract"].id,
                sha256=_d(f"contract-def-{tag}"),
                source_commit="task22",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model",
                logical_id=f"authority.projection.{tag}",
                semantic_version="1.0.0",
                blob_artifact_id=blobs["authority"].id,
                sha256=_d(f"authority-def-{tag}"),
                authority_model_type="projection_contract",
                source_commit="task22",
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
        alt: dict[str, Any] = {}
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            world.update(await _build_world(repo, tag="g1"))
            alt.update(await _build_world(repo, tag="g2"))
            # 把 pointer 还原到 g1（`alt` 只用来给 no-fold 场景一个不同的 frozen 身份）
            await repo.set_entry_pointer(
                wp_id=wp_id,
                entry_id=ENTRY,
                representation_id=world["representation"].id,
                generation=1,
            )
            await s.commit()

        rep_id = world["representation"].id
        cv_id = world["content_version"].id
        bundle_id = world["bundle"].id
        projection_sha = world["projection_sha256"]

        # ═══ room / participant / confirmation ════════════════════════════
        room_id: uuid.UUID | None = None
        part_a_id: uuid.UUID | None = None
        part_b_id: uuid.UUID | None = None
        part_v_id: uuid.UUID | None = None
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
                pv = await svc.join_participant(
                    scope, room_id=room_id, user_id=ids["user_v"],
                    mode=ParticipantMode.view, permission_epoch=5, lease_token="lease-v",
                )
                part_a_id, part_b_id, part_v_id = pa.id, pb.id, pv.id
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

        assert room_id is not None and part_a_id is not None and conf_a_id is not None
        credential = mint_route_credential(
            room_id=room_id, generation=1, doc_key=doc_key
        )

        def _body(**over: Any) -> dict[str, Any]:
            body: dict[str, Any] = {
                "key": doc_key,
                "status": 6,
                "url": OO_URL_A,
                "users": ["user-b"],
                "filetype": "xlsx",
                "history": {"changes": [{"user": {"id": "user-a"}}, {"user": {"id": "user-b"}}]},
                "token": "oo-self-signed-jwt",
            }
            body.update(over)
            return body

        def _service(repo: WorkpaperSyncRepository, transport: Any) -> Any:
            return CallbackDeliveryService(
                repo,
                artifacts=artifacts,
                download_policy=policy,
                transport=transport,
                contract=contract,
            )

        async def _handle(
            repo: WorkpaperSyncRepository,
            *,
            body: dict[str, Any],
            payload: bytes,
            status: int = 200,
        ) -> tuple[Any, Any, CallbackStageJournal]:
            transport = _Transport(payload, status=status)
            journal = CallbackStageJournal()
            token = sign_callback_route_token(
                secret=secret, room_id=room_id, generation=1, doc_key=doc_key,
                route_credential_id=credential.credential_id, action="callback_write",
                ttl_seconds=300, contract=contract,
            )
            url = build_callback_url(
                base_url="https://platform.example.test", path="/api/wp-sync/callback",
                room_id=room_id, generation=1, doc_key=doc_key,
                route_credential_id=credential.credential_id,
            )
            outcome = await _service(repo, transport).handle_callback(
                authorization_header=f"Bearer {token}",
                callback_url=url,
                body=body,
                room_id=room_id,
                secret=secret,
                journal=journal,
            )
            return outcome, transport, journal

        async def _freeze_request(
            repo: WorkpaperSyncRepository,
            *,
            participant_id: uuid.UUID,
            key: str,
            kind: Any = None,
            client_edit_epoch: int = 1,
            contributors: list[uuid.UUID] | None = None,
        ) -> Any:
            svc = RoomService(repo)
            room, participant, confirmation = await svc.assert_can_initiate_request(
                room_id=room_id, participant_id=participant_id,
                kind=kind or RequestKind.forcesave,
            )
            freeze = await svc.build_request_freeze(
                room=room, participant=participant, confirmation=confirmation,
                client_edit_epoch=client_edit_epoch,
                contributor_user_ids=contributors or [ids["user_a"], ids["user_b"]],
                kind=kind or RequestKind.forcesave,
            )
            return await repo.create_forcesave_request_with_shell(
                **freeze.as_repository_kwargs(scope=scope),
                idempotency_key=key,
                created_by=ids["user_a"],
            )

        # ═══ ① 端到端 request-first correlation ═══════════════════════════
        payload_a = _xlsx(b"ALICE+BOB")
        incoming_sha_a = hashlib.sha256(payload_a).hexdigest()
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                outcome_req = await _freeze_request(
                    repo, participant_id=part_a_id, key="fs-e2e-1"
                )
                await s.commit()
                body = _body(userdata=str(outcome_req.request.id))
                res, transport, journal = await _handle(repo, body=body, payload=payload_a)
                await s.commit()

                # 🔴 先把 outcome 级事实无条件落进快照，再去查行。反过来写时，
                # 「correlation 没发生」会以 `NoResultFound` 的形态变成**阶段崩溃**，
                # 而崩溃在 `-rf` 里不可见 ⇒ 一个真实缺陷会被读成「守卫没写对」。
                snap["e2e_request"]["outcome"] = {
                    "response_error": res.response_error,
                    "delivery_state": res.delivery_state.value,
                    "correlation_result": (
                        res.correlation_result.value if res.correlation_result else None
                    ),
                    "application_id": _opt(res.application_id),
                    "operation_id": _opt(res.operation_id),
                    "recovery_case_id": _opt(res.recovery_case_id),
                    "incoming_artifact_id": _opt(res.incoming_artifact_id),
                    "quarantined_artifact_id": _opt(res.quarantined_artifact_id),
                    "error_code": res.error_code,
                    "error_stage": res.error_stage,
                    "journal": [st.value for st in journal.order],
                }
                if res.application_id is None:
                    raise _HarnessError(
                        "request-first callback 没有产出 application: "
                        f"{snap['e2e_request']['outcome']}"
                    )

                app = (
                    await s.execute(
                        sa.select(WorkpaperContentApplication).where(
                            WorkpaperContentApplication.id == res.application_id
                        )
                    )
                ).scalar_one()
                delivery = (
                    await s.execute(
                        sa.select(WorkpaperCallbackDelivery).where(
                            WorkpaperCallbackDelivery.id == res.delivery_id
                        )
                    )
                ).scalar_one()
                primary = (
                    await s.execute(
                        sa.select(WorkpaperSyncOperation).where(
                            WorkpaperSyncOperation.id == res.operation_id
                        )
                    )
                ).scalar_one()
                room_row = (
                    await s.execute(
                        sa.select(WorkpaperOoRoom).where(WorkpaperOoRoom.id == room_id)
                    )
                ).scalar_one()
                snap["e2e_request"] = {
                    "response_error": res.response_error,
                    "journal": [st.value for st in journal.order],
                    "correlation_result": (
                        res.correlation_result.value if res.correlation_result else None
                    ),
                    "delivery_state": delivery.state,
                    "delivery_durable_at_set": delivery.durable_at is not None,
                    "delivery_application": _opt(delivery.application_id),
                    "delivery_recovery": _opt(delivery.callback_recovery_case_id),
                    "delivery_request": _opt(delivery.forcesave_request_id),
                    "delivery_incoming": _opt(delivery.incoming_artifact_id),
                    "delivery_key": delivery.delivery_key,
                    "expected_delivery_key": build_delivery_key(
                        room_id=room_id,
                        generation=1,
                        payload=CallbackPayload.from_mapping(body, contract=contract),
                    ),
                    "application_key": app.application_key,
                    "expected_application_key": compute_application_key(
                        wp_id=wp_id,
                        room_id=room_id,
                        generation=1,
                        frozen_client_base_version_id=outcome_req.request.client_base_version_id,
                        frozen_client_base_representation_id=(
                            outcome_req.request.client_base_representation_id
                        ),
                        incoming_sha256=incoming_sha_a,
                        definition_bundle_sha256=outcome_req.request.definition_bundle_sha256,
                        authority_model_definition_sha256=(
                            outcome_req.request.authority_model_definition_sha256
                        ),
                        adapter_build_digest=outcome_req.request.adapter_build_digest,
                    ),
                    "application_incoming_sha": app.incoming_sha256,
                    "incoming_sha_downloaded": incoming_sha_a,
                    "origin_request_sequence": int(app.origin_request_sequence),
                    "effective_request_sequence": int(app.effective_request_sequence),
                    "primary_application": _opt(primary.application_id),
                    "primary_duplicate_of": _opt(primary.duplicate_of_operation_id),
                    "room_latest_durable_application": _opt(
                        room_row.latest_durable_application_id
                    ),
                    "room_latest_durable_sequence": int(room_row.latest_durable_sequence or 0),
                    "download_url_pinned_to_ip": str(transport.requests[0].url),
                    "download_url_host_is_literal_ip": _host_is_literal_ip(
                        str(transport.requests[0].url)
                    ),
                    "download_host_header": str(
                        transport.requests[0].headers.get("Host") or ""
                    ),
                    "download_headers": dict(transport.requests[0].headers),
                    "download_follow_redirects": transport.requests[0].follow_redirects,
                    "download_max_redirects": transport.requests[0].max_redirects,
                }
                app_id_e2e = app.id
                request_a_id = outcome_req.request.id
                primary_id = primary.id
                incoming_a_id = res.incoming_artifact_id
        except Exception as exc:  # noqa: BLE001
            _phase_failed("e2e_request", exc)
            app_id_e2e = None
            request_a_id = None
            primary_id = None
            incoming_a_id = None

        # ═══ ② 网络重试折叠 / status 6 与 2 各自成行 ═══════════════════════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                base = _body(userdata=str(request_a_id))
                retry = {**base, "token": "oo-resigned-jwt"}
                p_base = CallbackPayload.from_mapping(base, contract=contract)
                p_retry = CallbackPayload.from_mapping(retry, contract=contract)
                p_second = CallbackPayload.from_mapping(
                    {**base, "url": OO_URL_B}, contract=contract
                )
                p_close = CallbackPayload.from_mapping(
                    {**base, "status": 2, "userdata": None, "notmodified": True},
                    contract=contract,
                )
                keys = {
                    "base": build_delivery_key(room_id=room_id, generation=1, payload=p_base),
                    "retry": build_delivery_key(room_id=room_id, generation=1, payload=p_retry),
                    "second": build_delivery_key(room_id=room_id, generation=1, payload=p_second),
                    "close": build_delivery_key(room_id=room_id, generation=1, payload=p_close),
                }
                # 真库：同 key 第二次 INSERT 必须被唯一约束拒
                try:
                    await repo.record_delivery(
                        project_id=project_id, wp_id=wp_id, entry_id=ENTRY,
                        room_id=room_id, generation=1,
                        route_credential_id=credential.credential_id,
                        callback_status=6, delivery_key=keys["base"],
                    )
                    await s.flush()
                    dup_blame = None
                except Exception as exc:  # noqa: BLE001
                    dup_blame = _blame(exc)
                await s.rollback()
                snap["dedupe"] = {
                    "keys": keys,
                    "retry_folds": keys["base"] == keys["retry"],
                    "distinct_delivery_distinct_key": keys["base"] != keys["second"],
                    "status_2_separate_row": keys["base"] != keys["close"],
                    "duplicate_key_blame": dup_blame,
                }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("dedupe", exc)

        # ═══ ③ 归属真值表逐行归因 ════════════════════════════════════════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                # 第二条 durable incoming + 一个真 recovery case（给 FK 目标）
                res2, _t2, _j2 = await _handle(
                    repo,
                    body=_body(url=OO_URL_B, users=[], history={"changes": []},
                               notmodified=True),
                    payload=_xlsx(b"ORPHAN"),
                )
                await s.commit()
                case_id = res2.recovery_case_id
                incoming_b_id = res2.incoming_artifact_id
                snap["ownership_fixture"] = {
                    "recovery_case": _opt(case_id),
                    "second_response_error": res2.response_error,
                    "second_state": res2.delivery_state.value,
                }

                cols = {
                    "project_id": project_id,
                    "wp_id": wp_id,
                    "entry_id": ENTRY,
                    "room_id": room_id,
                    "generation": 1,
                    "route_credential_id": credential.credential_id,
                }
                probes: dict[str, Any] = {}
                for row in DELIVERY_OWNERSHIP_TRUTH_TABLE:
                    values = {
                        **cols,
                        "id": uuid.uuid4(),
                        "callback_status": 6,
                        "delivery_key": _d(f"own-{row.row_id}"),
                        "state": row.state.value,
                        "durable_at": sa.text("now()") if row.durable_at_is_set else None,
                        "application_id": app_id_e2e if row.has_application else None,
                        "callback_recovery_case_id": case_id if row.has_recovery else None,
                        "forcesave_request_id": request_a_id if row.has_request else None,
                        "incoming_artifact_id": incoming_a_id if row.has_incoming else None,
                        "operation_id": None,
                        "correlation_result": {
                            "absent": None,
                            "correlated": "request",
                            "unresolved": "ambiguous",
                        }[row.family.value],
                    }
                    sql = sa.text(
                        "INSERT INTO working_paper_callback_delivery ("
                        "id, project_id, wp_id, entry_id, room_id, generation,"
                        " route_credential_id, callback_status, delivery_key, state,"
                        " durable_at, application_id, callback_recovery_case_id,"
                        " forcesave_request_id, incoming_artifact_id, operation_id,"
                        " correlation_result) VALUES ("
                        ":id, :project_id, :wp_id, :entry_id, :room_id, :generation,"
                        " :route_credential_id, :callback_status, :delivery_key, :state,"
                        + ("now()" if row.durable_at_is_set else "NULL")
                        + ", :application_id, :callback_recovery_case_id,"
                        " :forcesave_request_id, :incoming_artifact_id, :operation_id,"
                        " :correlation_result)"
                    )
                    bind = {k: v for k, v in values.items() if k != "durable_at"}
                    sp = await s.begin_nested()
                    try:
                        await s.execute(sql, bind)
                        # deferred constraint trigger 也必须当场表态，否则「allowed」
                        # 只证明了行级 CHECK 放行，deferred 那层等于没测。
                        await s.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
                        probes[row.row_id] = {"accepted": True, "blame": None}
                        await sp.rollback()
                    except Exception as exc:  # noqa: BLE001
                        probes[row.row_id] = {"accepted": False, "blame": _blame(exc)}
                        await sp.rollback()
                snap["ownership"] = probes
                snap["ownership_probe_count"] = len(probes)
                snap["ownership_expected"] = {
                    r.row_id: {
                        "verdict": r.verdict.value,
                        "constraint": r.db_constraint,
                        "allowed": r.verdict is OwnershipVerdict.allowed,
                    }
                    for r in DELIVERY_OWNERSHIP_TRUTH_TABLE
                }
                await s.rollback()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("ownership", exc)
            case_id = None
            incoming_b_id = None

        # ═══ ④ same incoming + 不同 frozen identity 不折叠 ════════════════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                req = (
                    await s.execute(
                        sa.text(
                            "SELECT client_base_version_id, client_base_representation_id,"
                            " definition_bundle_sha256,"
                            " authority_model_definition_sha256, adapter_build_digest"
                            " FROM working_paper_forcesave_request"
                            " WHERE id = CAST(:rid AS uuid)"
                        ).bindparams(rid=str(request_a_id))
                    )
                ).first()
                baseline = dict(
                    wp_id=wp_id,
                    room_id=room_id,
                    generation=1,
                    frozen_client_base_version_id=uuid.UUID(str(req[0])),
                    frozen_client_base_representation_id=uuid.UUID(str(req[1])),
                    incoming_sha256=incoming_sha_a,
                    definition_bundle_sha256=str(req[2]),
                    authority_model_definition_sha256=str(req[3]),
                    adapter_build_digest=str(req[4]),
                )
                variants = {
                    "baseline": {},
                    "different_base": {
                        "frozen_client_base_version_id": alt["content_version"].id
                    },
                    "different_representation": {
                        "frozen_client_base_representation_id": alt["representation"].id
                    },
                    "different_bundle": {
                        "definition_bundle_sha256": alt["bundle"].canonical_payload_sha256
                    },
                    "different_authority": {
                        "authority_model_definition_sha256": _d("authority-def-g2")
                    },
                    "different_adapter_build": {
                        "adapter_build_digest": alt["adapter_build_digest"]
                    },
                    "different_generation": {"generation": 2},
                }
                computed = {
                    name: compute_application_key(**{**baseline, **over})
                    for name, over in variants.items()
                }
                # 只改 status/delivery order/request sequence 不得改 key：key 函数根本
                # 不接受这些入参，因此「同 frozen identity 重复计算」必然相等。
                snap["no_fold"] = {
                    "keys": computed,
                    "distinct_count": len(set(computed.values())),
                    "variant_count": len(computed),
                    "stable_on_recompute": (
                        compute_application_key(**baseline) == computed["baseline"]
                    ),
                    "key_signature": sorted(
                        __import__("inspect").signature(compute_application_key).parameters
                    ),
                }
                await s.rollback()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("no_fold", exc)

        # ═══ ⑤ quarantined incoming 的三层隔离 ════════════════════════════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                outcome_q = await _freeze_request(
                    repo, participant_id=part_a_id, key="fs-quarantine-1"
                )
                await s.commit()
                # `text/plain` 伪装成 xlsx：zip magic 门在 sealing 阶段拒绝 ⇒ quarantined
                res_q, _tq, jq = await _handle(
                    repo,
                    body=_body(userdata=str(outcome_q.request.id), url=OO_URL_B),
                    payload=b"this is not a zip at all, just plain text pretending",
                )
                await s.commit()
                qrow = (
                    await s.execute(
                        sa.text(
                            "SELECT state, durable_at, quarantined_at, relative_path"
                            " FROM working_paper_artifact WHERE id = CAST(:aid AS uuid)"
                        ).bindparams(aid=str(res_q.quarantined_artifact_id))
                    )
                ).first()
                delivery_q = (
                    await s.execute(
                        sa.select(WorkpaperCallbackDelivery).where(
                            WorkpaperCallbackDelivery.id == res_q.delivery_id
                        )
                    )
                ).scalar_one()

                layers: dict[str, Any] = {}
                # 第一层（纯内存 sealing 对象）在阶段 ⑨ 单独驱动 —— 它不需要 DB，
                # 放在这里会让「DB 阶段失败」连带抹掉一个本来独立的判据。
                # 第二层：仓储读 DB 行
                try:
                    await repo.assert_incoming_durable(res_q.quarantined_artifact_id)
                    layers["repository"] = None
                except SyncDomainError as exc:
                    layers["repository"] = {
                        "type": type(exc).__name__,
                        "error_code": getattr(exc, "error_code", None),
                    }
                # 第三层：DB trigger —— 直接把 quarantined 当 application 的 incoming
                sp = await s.begin_nested()
                try:
                    await s.execute(
                        sa.text(
                            # SET 一侧也必须 CAST：漏掉时 PG 报 42804（类型不匹配），
                            # 探针根本没走到 trigger，而「抛了异常」会被误读成 trigger 生效。
                            "UPDATE working_paper_content_application"
                            " SET incoming_artifact_id = CAST(:aid AS uuid)"
                            " WHERE id = CAST(:app AS uuid)"
                        ).bindparams(aid=str(res_q.quarantined_artifact_id), app=str(app_id_e2e))
                    )
                    await s.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
                    layers["db_trigger"] = None
                    await sp.rollback()
                except Exception as exc:  # noqa: BLE001
                    layers["db_trigger"] = _blame(exc)
                    await sp.rollback()
                # quarantined → durable 必须被 trigger 拒
                sp = await s.begin_nested()
                try:
                    await s.execute(
                        sa.text(
                            "UPDATE working_paper_artifact SET state = 'durable'"
                            " WHERE id = CAST(:aid AS uuid)"
                        ).bindparams(aid=str(res_q.quarantined_artifact_id))
                    )
                    layers["release_to_durable"] = None
                    await sp.rollback()
                except Exception as exc:  # noqa: BLE001
                    layers["release_to_durable"] = _blame(exc)
                    await sp.rollback()
                # incoming 永不 published / current
                for target in ("published", "candidate"):
                    sp = await s.begin_nested()
                    try:
                        await s.execute(
                            sa.text(
                                "UPDATE working_paper_artifact SET state = :st"
                                " WHERE id = CAST(:aid AS uuid)"
                            ).bindparams(st=target, aid=str(incoming_a_id))
                        )
                        layers[f"incoming_to_{target}"] = None
                        await sp.rollback()
                    except Exception as exc:  # noqa: BLE001
                        layers[f"incoming_to_{target}"] = _blame(exc)
                        await sp.rollback()
                # resolver 可见性：incoming 不得成为 entry 的 current representation 底料
                resolver_rows = (
                    await s.execute(
                        sa.text(
                            "SELECT count(*) FROM working_paper_content_representation r"
                            " JOIN working_paper_artifact a ON a.id = r.artifact_id"
                            " WHERE a.kind = 'incoming'"
                        )
                    )
                ).scalar_one()

                snap["quarantine"] = {
                    "response_error": res_q.response_error,
                    "journal": [st.value for st in jq.order],
                    "sealed_quarantined": CallbackStage.sealed_quarantined.value
                    in [st.value for st in jq.order],
                    "sealed_durable_absent": CallbackStage.sealed_durable.value
                    not in [st.value for st in jq.order],
                    "artifact_state": qrow[0] if qrow else None,
                    "artifact_durable_at": None if qrow is None else _opt(qrow[1]),
                    "artifact_quarantined_at_set": bool(qrow and qrow[2] is not None),
                    "delivery_state": delivery_q.state,
                    "delivery_durable_at": _opt(delivery_q.durable_at),
                    "delivery_application": _opt(delivery_q.application_id),
                    "delivery_recovery": _opt(delivery_q.callback_recovery_case_id),
                    "layers": layers,
                    "representations_backed_by_incoming": int(resolver_rows),
                    "quarantined_artifact_id": _opt(res_q.quarantined_artifact_id),
                    "error_code": res_q.error_code,
                    "error_stage": res_q.error_stage,
                }
                await s.rollback()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("quarantine", exc)

        # ═══ ⑥ recovery case：claim 前三实体为 0 / claim / download-only ══
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                res_r, _tr, jr = await _handle(
                    repo,
                    body=_body(url=f"{OO_ORIGIN}/cache/files/data/t22_r/o.xlsx?md5=r"),
                    payload=_xlsx(b"NO-REQUEST"),
                )
                await s.commit()
                case = (
                    await s.execute(
                        sa.select(WorkpaperCallbackRecoveryCase).where(
                            WorkpaperCallbackRecoveryCase.id == res_r.recovery_case_id
                        )
                    )
                ).scalar_one()
                delivery_r = (
                    await s.execute(
                        sa.select(WorkpaperCallbackDelivery).where(
                            WorkpaperCallbackDelivery.id == res_r.delivery_id
                        )
                    )
                ).scalar_one()
                before = {
                    "response_error": res_r.response_error,
                    "case_state": case.state,
                    "case_request": _opt(case.recovery_request_id),
                    "case_application": _opt(case.application_id),
                    "case_operation": _opt(case.operation_id),
                    "delivery_state": delivery_r.state,
                    "delivery_recovery": _opt(delivery_r.callback_recovery_case_id),
                    "delivery_application": _opt(delivery_r.application_id),
                    "delivery_request": _opt(delivery_r.forcesave_request_id),
                    "delivery_operation": _opt(delivery_r.operation_id),
                    "delivery_durable_at_set": delivery_r.durable_at is not None,
                    "journal": [st.value for st in jr.order],
                }

                # 只读 participant claim ⇒ 授权失败，三实体保持 0
                svc = _service(repo, _Transport(b""))
                sp = await s.begin_nested()
                try:
                    await svc.claim_recovery_case(
                        case_id=case.id,
                        claiming_participant_id=part_v_id,
                        prior_confirmation_id=conf_a_id,
                        idempotency_key="claim-view",
                        adapter_id="excel.d2.v1",
                        adapter_build_digest=world["adapter_build_digest"],
                        contributor_snapshot_digest=_d("contrib-claim"),
                    )
                    before["view_claim_error"] = None
                    await sp.rollback()
                except SyncDomainError as exc:
                    before["view_claim_error"] = {
                        "type": type(exc).__name__,
                        "error_code": getattr(exc, "error_code", None),
                    }
                    await sp.rollback()
                case_after_view = (
                    await s.execute(
                        sa.text(
                            "SELECT state, recovery_request_id, application_id, operation_id"
                            " FROM working_paper_callback_recovery_case WHERE id = CAST(:cid AS uuid)"
                        ).bindparams(cid=str(case.id))
                    )
                ).first()
                before["after_view_claim"] = {
                    "state": case_after_view[0],
                    "request": _opt(case_after_view[1]),
                    "application": _opt(case_after_view[2]),
                    "operation": _opt(case_after_view[3]),
                }

                # 合法 claim：一个事务内 request + shell + application
                claimed = await svc.claim_recovery_case(
                    case_id=case.id,
                    claiming_participant_id=part_a_id,
                    prior_confirmation_id=conf_a_id,
                    idempotency_key="claim-a-1",
                    adapter_id="excel.d2.v1",
                    adapter_build_digest=world["adapter_build_digest"],
                    contributor_snapshot_digest=_d("contrib-claim"),
                )
                await s.commit()
                after = {
                    "case_state": claimed.case.state,
                    "request_kind": claimed.request.kind,
                    "shape": claimed.shape.value,
                    "operation_application": _opt(claimed.operation.application_id),
                    "operation_duplicate_of": _opt(claimed.operation.duplicate_of_operation_id),
                    "case_application": _opt(claimed.case.application_id),
                    "case_request": _opt(claimed.case.recovery_request_id),
                    "case_operation": _opt(claimed.case.operation_id),
                    "application_incoming": _opt(claimed.application.incoming_artifact_id),
                    "case_incoming": _opt(claimed.case.incoming_artifact_id),
                    "cache_hit": claimed.cache_hit,
                }
                # 同 key 重放必须幂等命中，不得造第二套三实体
                replay = await svc.claim_recovery_case(
                    case_id=case.id,
                    claiming_participant_id=part_a_id,
                    prior_confirmation_id=conf_a_id,
                    idempotency_key="claim-a-1",
                    adapter_id="excel.d2.v1",
                    adapter_build_digest=world["adapter_build_digest"],
                    contributor_snapshot_digest=_d("contrib-claim"),
                )
                after["replay_cache_hit"] = replay.cache_hit
                after["replay_same_application"] = (
                    replay.application.id == claimed.application.id
                )
                after["replay_same_request"] = replay.request.id == claimed.request.id
                counts = (
                    await s.execute(
                        sa.text(
                            "SELECT (SELECT count(*) FROM working_paper_forcesave_request"
                            "         WHERE kind = 'recovery_claim'),"
                            "       (SELECT count(*) FROM working_paper_content_application"
                            "         WHERE origin_request_id IN ("
                            "            SELECT id FROM working_paper_forcesave_request"
                            "             WHERE kind = 'recovery_claim'))"
                        )
                    )
                ).first()
                after["recovery_request_rows"] = int(counts[0])
                after["recovery_application_rows"] = int(counts[1])
                snap["recovery"] = {"before_claim": before, "after_claim": after}
                await s.commit()

            # download-only：另建一个 case，三实体恒 0
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                res_dl, _tdl, _jdl = await _handle(
                    repo,
                    body=_body(url=f"{OO_ORIGIN}/cache/files/data/t22_dl/o.xlsx?md5=dl"),
                    payload=_xlsx(b"DOWNLOAD-ONLY"),
                )
                await s.commit()
                svc = _service(repo, _Transport(b""))
                dl_case = await svc.terminate_download_only(case_id=res_dl.recovery_case_id)
                await s.commit()
                snap["recovery"]["download_only"] = {
                    "state": dl_case.state,
                    "request": _opt(dl_case.recovery_request_id),
                    "application": _opt(dl_case.application_id),
                    "operation": _opt(dl_case.operation_id),
                }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("recovery", exc)

        # ═══ ⑦ 失败语义：durable 前非零 / durable 后 0 且保留 owner ═══════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                outcome_f = await _freeze_request(
                    repo, participant_id=part_a_id, key="fs-fail-1"
                )
                await s.commit()
                # durable 前失败：transport 返回 500
                res_f, _tf, jf = await _handle(
                    repo,
                    body=_body(
                        userdata=str(outcome_f.request.id),
                        url=f"{OO_ORIGIN}/cache/files/data/t22_f/o.xlsx?md5=f",
                    ),
                    payload=b"",
                    status=500,
                )
                await s.commit()
                d_f = (
                    await s.execute(
                        sa.select(WorkpaperCallbackDelivery).where(
                            WorkpaperCallbackDelivery.id == res_f.delivery_id
                        )
                    )
                ).scalar_one()
                pre = {
                    "response_error": res_f.response_error,
                    "state": d_f.state,
                    "durable_at": _opt(d_f.durable_at),
                    "application": _opt(d_f.application_id),
                    "recovery": _opt(d_f.callback_recovery_case_id),
                    "request_retained": _opt(d_f.forcesave_request_id),
                    "error_code": res_f.error_code,
                    "error_stage": res_f.error_stage,
                    "journal": [st.value for st in jf.order],
                }
                snap["failures"] = {"pre_durable": pre}
                await s.rollback()

            # post-durable error 走真行：重新取 e2e 的 delivery
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                row = (
                    await s.execute(
                        sa.select(WorkpaperCallbackDelivery)
                        .where(WorkpaperCallbackDelivery.application_id == app_id_e2e)
                        .limit(1)
                    )
                ).scalar_one()
                updated = await repo.mark_delivery_post_durable_error(delivery_id=row.id)
                await s.commit()
                snap["failures"]["post_durable"] = {
                    "state": updated.state,
                    "response_error": updated.response_error,
                    "durable_at_kept": updated.durable_at is not None,
                    "application_kept": _opt(updated.application_id),
                    "recovery": _opt(updated.callback_recovery_case_id),
                    "incoming_kept": _opt(updated.incoming_artifact_id),
                }
                # post-durable 丢弃 owner 必须被 trigger 拒
                sp = await s.begin_nested()
                try:
                    await s.execute(
                        sa.text(
                            "UPDATE working_paper_callback_delivery SET application_id = NULL"
                            " WHERE id = CAST(:did AS uuid)"
                        ).bindparams(did=str(row.id))
                    )
                    snap["failures"]["drop_owner_blame"] = None
                    await sp.rollback()
                except Exception as exc:  # noqa: BLE001
                    snap["failures"]["drop_owner_blame"] = _blame(exc)
                    await sp.rollback()
                # durable_at 是 immutable durable fact
                sp = await s.begin_nested()
                try:
                    await s.execute(
                        sa.text(
                            "UPDATE working_paper_callback_delivery SET durable_at = NULL"
                            " WHERE id = CAST(:did AS uuid)"
                        ).bindparams(did=str(row.id))
                    )
                    snap["failures"]["clear_durable_blame"] = None
                    await sp.rollback()
                except Exception as exc:  # noqa: BLE001
                    snap["failures"]["clear_durable_blame"] = _blame(exc)
                    await sp.rollback()
                await s.rollback()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("failures", exc)

        # ═══ ⑧ forcesave 同 key 的 (room,generation,participant,kind) 语义 ═
        try:
            # 🔴 id 必须在 session 内投影成 `str`：把 ORM 对象带出 `async with` 后再读
            # `.id`，SQLAlchemy 会尝试 refresh 一个已 detach 的实例 ⇒ DetachedInstanceError，
            # 而那个异常与被测语义（幂等/409）毫无关系，只会伪装成「阶段崩了」。
            first_request_id = ""
            first_operation_id = ""
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                first = await _freeze_request(
                    repo, participant_id=part_a_id, key="fs-idem-1"
                )
                first_request_id = str(first.request.id)
                first_operation_id = str(first.operation.id)
                out: dict[str, Any] = {
                    "first_request": first_request_id,
                    "first_operation": first_operation_id,
                    "first_cache_hit": first.cache_hit,
                }
                await s.commit()
                # 等值重放 ⇒ 命中同一 request/operation
                same = await _freeze_request(repo, participant_id=part_a_id, key="fs-idem-1")
                out["replay_cache_hit"] = same.cache_hit
                out["replay_same_request"] = str(same.request.id) == first_request_id
                out["replay_same_operation"] = str(same.operation.id) == first_operation_id
                await s.commit()

            # 🔴 三个冲突场景**必须**绕过 room 资格门直接打仓储。原写法用
            # `_freeze_request(kind=close_capture)`，而 `assert_can_initiate_request` 对
            # close_capture 另有一条 room-policy 判据，会**先**抛
            # `RoomPolicyError/room_policy_violation` ⇒ 测到的是 Task 21/24 的门，
            # 被测的幂等谓词一次都没跑到（首轮实测就是这个假红）。
            # 一个场景只违反一个谓词：这里保持 freeze 完全等值，只改被测那一维。
            async def _conflict_probe(label: str, **over: Any) -> None:
                async with Session() as s:
                    repo = WorkpaperSyncRepository(s)
                    svc = RoomService(repo)
                    room, participant, confirmation = (
                        await svc.assert_can_initiate_request(
                            room_id=room_id, participant_id=part_a_id
                        )
                    )
                    freeze = await svc.build_request_freeze(
                        room=room, participant=participant, confirmation=confirmation,
                        client_edit_epoch=int(over.pop("client_edit_epoch", 1)),
                        contributor_user_ids=[ids["user_a"], ids["user_b"]],
                    )
                    kwargs = freeze.as_repository_kwargs(scope=scope)
                    kwargs.update(over)
                    try:
                        await repo.create_forcesave_request_with_shell(
                            **kwargs, idempotency_key="fs-idem-1", created_by=ids["user_a"]
                        )
                        out[label] = {"conflict": False}
                    except IdempotencyConflictError as exc:
                        text = str(exc)
                        out[label] = {
                            "conflict": True,
                            "error_code": getattr(exc, "error_code", None),
                            "leaks_first_request": first_request_id in text,
                            "leaks_first_operation": first_operation_id in text,
                            "detail": text[:200],
                        }
                    except SyncDomainError as exc:
                        out[label] = {
                            "conflict": False,
                            "other_error": type(exc).__name__,
                            "error_code": getattr(exc, "error_code", None),
                        }
                    await s.rollback()

            await _conflict_probe(
                "cross_participant", initiated_by_participant_id=part_b_id
            )
            await _conflict_probe("cross_kind", kind=RequestKind.close_capture)
            await _conflict_probe("different_payload", client_edit_epoch=9)
            snap["forcesave_key"] = out
        except Exception as exc:  # noqa: BLE001
            _phase_failed("forcesave_key", exc)

        # ═══ ⑨ 纯内存第一层（quarantine 断言）══════════════════════════════
        try:
            from app.services.workpaper_sync.artifacts import SealedIncoming

            fake_q = SealedIncoming(
                delivery_id=uuid.uuid4(),
                project_id=project_id,
                wp_id=wp_id,
                state=ArtifactState.quarantined,
                path=tmp_root / "q.xlsx",
                relative_path="q.xlsx",
                sha256=_d("q"),
                size_bytes=10,
                document_type="xlsx",
                durable_at=None,
                quarantined_at=None,
                report=None,
                rejection_error_code="ooxml_zip_magic_invalid",
                rejection_gate="zip_magic",
                rejection_detail="not a zip",
            )
            snap["quarantine"].setdefault("layers", {})
            try:
                assert_incoming_admissible_for_application(fake_q)
                snap["quarantine"]["layers"]["memory"] = None
            except QuarantineOperationForbiddenError as exc:
                snap["quarantine"]["layers"]["memory"] = {
                    "type": type(exc).__name__,
                    "error_code": getattr(exc, "error_code", None),
                }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("quarantine_memory", exc)

        return snap
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await admin.dispose()
        try:
            import shutil

            shutil.rmtree(tmp_root, ignore_errors=True)
        except Exception:  # noqa: BLE001 - 清理失败不影响判据
            pass


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
    """任何采集阶段崩掉都必须在这里显性打红。

    这条不是「多余的自检」，而是「异常不得穿透采集函数」这个决定的另一半：阶段异常被
    记录而非抛出之后，若没有本断言，一个把某阶段打崩的回归就会变成「那一段断言全读到
    缺失数据、但测试全绿」。
    """
    assert snap["harness_errors"] == {}, (
        f"采集阶段异常（会让后续断言读到 stale/缺失数据）: {snap['harness_errors']}"
    )


def test_non_postgres_database_url_fails_instead_of_skipping() -> None:
    """判据形态自证：非 PG 必须**失败**而不是 skip。

    直接读采集函数源码里那句 `raise _HarnessError`：把它改成 `pytest.skip` 时本条打红。
    不用 monkeypatch 真跑一次（那会另起一个 engine 并污染连接池），判据落在
    「非 PG 分支抛的是异常类型」这个结构事实上。
    """
    import ast
    import inspect

    src = inspect.getsource(_collect)
    head = src.split("if not _MIGRATION.exists()")[0]
    assert "raise _HarnessError" in head, "非 PG 分支必须 raise"
    # 🔴 判据落在**调用**上，不能 grep 字符串 `skip`：这段的 raise 文案本身就写着
    # 「此处不 skip」，字符串判据于是恒假（首轮实测就是这么红的）。用 AST 找
    # `pytest.skip(...)` / `skipif` 这类真实调用。
    tree = ast.parse(inspect.getsource(inspect.getmodule(_collect)))
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_collect"
    )
    calls = {
        ast.unparse(n.func)
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and hasattr(n, "func")
    }
    offenders = {c for c in calls if "skip" in c.lower()}
    assert offenders == set(), f"非 PG 分支不得 skip —— skip 等于抹掉唯一判据: {offenders}"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 归属真值表：逐行归因（Requirement 5.4 / Property 18）
# ═══════════════════════════════════════════════════════════════════════════


def test_every_truth_table_row_was_probed_against_real_postgres(
    snap: dict[str, Any],
) -> None:
    """遍历性自证：表里每一行都必须真的被 INSERT 过一次。

    没有这条时，采集里任何一个 `continue` 都会静默减少覆盖，而剩下的断言照样全绿。
    """
    assert snap["ownership_probe_count"] == len(snap["ownership_expected"])
    assert snap["ownership_probe_count"] >= 14, snap["ownership_probe_count"]
    assert set(snap["ownership"]) == set(snap["ownership_expected"])


@pytest.mark.parametrize(
    "row_id",
    ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08"],
)
def test_allowed_ownership_rows_really_insert(snap: dict[str, Any], row_id: str) -> None:
    """`allowed` 行必须真能进真表（含 deferred trigger 当场表态）。"""
    expected = snap["ownership_expected"][row_id]
    assert expected["allowed"], f"{row_id} 在表里不是 allowed，参数化清单需同步"
    probe = snap["ownership"][row_id]
    assert probe["accepted"], f"{row_id} 被真库拒绝: {probe['blame']}"


def _assert_forbidden_row(snap: dict[str, Any], row_id: str) -> None:
    """`forbidden` 行必须被拒，**且**拒它的正是该行声明的那条约束。

    只断言「被拒了」不够：一行被另一条约束偶然挡住时，表里的归因是错的，而下一个人会
    据此以为「我声明的那条约束还活着」。因此这里同时断言：

    1. 确实被拒；
    2. 归因名 == `db_constraint`；
    3. 报文里**没有第二条** `ck_*`/`wpsync_check_*` 被提到（去遮蔽：一行只违反一条）。
    """
    expected = snap["ownership_expected"][row_id]
    assert not expected["allowed"], f"{row_id} 在表里不是 forbidden，判据清单需同步"
    probe = snap["ownership"][row_id]
    assert not probe["accepted"], f"{row_id} 竟被真库接受 —— 约束缺失或真值表写错"
    blame = probe["blame"]
    assert blame["source"] != "probe_defect", (
        f"{row_id} 的拒绝来自探针自己的 SQL 错误而不是约束: {blame}"
    )
    assert blame["constraint"] == expected["constraint"], (
        f"{row_id} 声明由 {expected['constraint']} 兜底，实际被 "
        f"{blame['constraint']} 拒绝: {blame['text']}"
    )
    others = [m for m in blame["mentions"] if m != expected["constraint"]]
    assert others == [], (
        f"{row_id} 同时触发了 {others} —— 合取组合无法归因，该行必须构造成只违反一条"
    )


@pytest.mark.parametrize(
    "row_id", ["T09", "T10", "T11", "T12", "T13", "T14"]
)
def test_forbidden_ownership_rows_are_rejected_by_their_declared_constraint(
    snap: dict[str, Any], row_id: str
) -> None:
    """表驱动的完整性判据：每个 forbidden 行都过一遍归因。"""
    _assert_forbidden_row(snap, row_id)


# 🔴 下面六条**逐行独立命名**，不是上面参数化那条的重复。理由是变异归因：削掉某一条
# V151 CHECK 时，必须能证明打红的正是**声明该约束的那一行**。参数化 nodeid 里的
# `[T09]` 不是源码里的字面量，变异脚本的 `want` 定位不到它，只能退化成「六个参数任一
# 红即算命中」—— 那就丢掉了「哪条约束兜哪一行」这个本任务的核心交付物。
# 逻辑不重复：全部委派给 `_assert_forbidden_row`，表仍是唯一真源。


def test_ownership_T09_double_owner_is_rejected_by_ck_wpcd_no_double_owner(
    snap: dict[str, Any],
) -> None:
    _assert_forbidden_row(snap, "T09")


def test_ownership_T10_durable_zero_owner_rejected_by_ck_wpcd_durable_exactly_one_owner(
    snap: dict[str, Any],
) -> None:
    _assert_forbidden_row(snap, "T10")


def test_ownership_T11_durable_state_without_fact_rejected_by_ck_wpcd_durable_state_requires_fact(
    snap: dict[str, Any],
) -> None:
    _assert_forbidden_row(snap, "T11")


def test_ownership_T12_unmatched_with_request_rejected_by_ck_wpcd_unmatched_zero_entities(
    snap: dict[str, Any],
) -> None:
    _assert_forbidden_row(snap, "T12")


def test_ownership_T13_ambiguous_with_entities_rejected_by_ck_wpcd_ambiguous_zero_entities(
    snap: dict[str, Any],
) -> None:
    _assert_forbidden_row(snap, "T13")


def test_ownership_T14_durable_without_incoming_rejected_by_ck_wpcd_durable_requires_incoming(
    snap: dict[str, Any],
) -> None:
    _assert_forbidden_row(snap, "T14")


def test_the_three_mandated_ownership_semantics_hold_in_the_database(
    snap: dict[str, Any],
) -> None:
    """Task 22 正文逐字要求的三条语义，各自由真库行为背书。

    ① `durable_at IS NULL` 的 received/downloading/rejected/error 可零 owner；
    ② durable fact 存在 ⇒ 恰属 application 或 recovery 之一（零 owner 也非法）；
    ③ request 与 application **可同时存在** —— 不做 XOR。
    """
    own = snap["ownership"]
    # ① 四个 pre-durable state 各自被接受（零 owner）
    for row_id in ("T01", "T02", "T03", "T04", "T05"):
        assert own[row_id]["accepted"], row_id
    # ② durable 零 owner 被拒（T10），且拒它的是 XOR 那条
    assert not own["T10"]["accepted"]
    assert own["T10"]["blame"]["constraint"] == "ck_wpcd_durable_exactly_one_owner"
    # 双 owner 在任何阶段都被拒（T09），且拒它的是 no_double_owner
    assert not own["T09"]["accepted"]
    assert own["T09"]["blame"]["constraint"] == "ck_wpcd_no_double_owner"
    # ③ request + application 同时存在被**接受**（T06）—— 这条是「不做 XOR」的正面证据
    assert own["T06"]["accepted"], (
        "request 与 application 同时存在必须合法；被拒说明有人把它们错做成了 XOR"
    )


def test_post_durable_error_keeps_its_owner(snap: dict[str, Any]) -> None:
    """post-durable 失败保留既有 owner，且 owner 不得被丢弃、durable fact 不得被清空。"""
    post = snap["failures"]["post_durable"]
    assert post["state"] == "error"
    assert post["response_error"] == 0, "durable 之后一律 error=0（OO 不重发）"
    assert post["durable_at_kept"] is True
    assert post["application_kept"] is not None, "post-durable error 必须保留 application owner"
    assert post["recovery"] is None, "owner 仍恰一"
    assert post["incoming_kept"] is not None, "durable incoming 必须保留以供重试"
    # 这两条的执法点是 `wpsync_check_delivery_durable_fact`（BEFORE UPDATE trigger）。
    # plpgsql 的 `RAISE EXCEPTION` 不带 constraint 名，所以归因按 `source=trigger_raise`
    # + 报文语义断言。**不能**只断言「抛了异常」：探针自己写错 SQL（42804/22P02）也会
    # 抛，那时 `source=probe_defect`，本条会打红而不是把探针缺陷读成「trigger 有效」。
    for label, phrase in (
        ("drop_owner_blame", "application owner"),
        ("clear_durable_blame", "durable_at"),
    ):
        blame = snap["failures"][label]
        assert blame is not None, f"{label}: 真库竟允许该 UPDATE"
        assert blame["source"] == "trigger_raise", (
            f"{label} 的拒绝来自 {blame['source']}（非 trigger）: {blame}"
        )
        assert phrase in blame["text"], f"{label} 报文未指向预期语义: {blame['text']}"


# ═══════════════════════════════════════════════════════════════════════════
# 2. delivery 去重（Requirement 5.4 / Task 4 §7）
# ═══════════════════════════════════════════════════════════════════════════


def test_network_retry_folds_but_distinct_deliveries_do_not(snap: dict[str, Any]) -> None:
    """同一投递重发折叠成一行；不同投递与不同 status 各自成行。"""
    d = snap["dedupe"]
    assert d["retry_folds"] is True, "OO 重签 body token 不得被算成新投递（token 不进 digest）"
    assert d["distinct_delivery_distinct_key"] is True, (
        "Task 4 实测同 userdata 连发两次的 url 与字节都不同 ⇒ 必须两行证据"
    )
    assert d["status_2_separate_row"] is True, "delivery key 含 status：6 与 2 各自成行"


def test_duplicate_delivery_key_is_refused_by_the_database(snap: dict[str, Any]) -> None:
    """去重的**执法点在库里**：同 delivery_key 第二行必须被唯一约束拒。

    不钉住这条时，服务层「查一下有没有」的写法会被当成唯一防线，而它在并发下会双写。
    """
    blame = snap["dedupe"]["duplicate_key_blame"]
    assert blame is not None, "真库竟允许同 delivery_key 两行"
    assert "delivery_key" in (blame["constraint"] or "") or "delivery_key" in blame["text"], blame
    assert blame["sqlstate"] in ("23505", None), blame


# ═══════════════════════════════════════════════════════════════════════════
# 3. 端到端 request-first correlation（Requirement 4.3 / Property 64）
# ═══════════════════════════════════════════════════════════════════════════


def test_request_first_correlation_produces_one_primary_and_one_application(
    snap: dict[str, Any],
) -> None:
    e = snap["e2e_request"]
    assert e["response_error"] == 0
    assert e["correlation_result"] == "request"
    assert e["delivery_state"] == "acknowledged"
    assert e["delivery_durable_at_set"] is True
    assert e["delivery_application"] is not None
    assert e["delivery_recovery"] is None
    assert e["delivery_request"] is not None, "request 与 application 同时关联（不做 XOR）"
    assert e["delivery_incoming"] is not None
    assert e["primary_application"] == e["delivery_application"]
    assert e["primary_duplicate_of"] is None, "winner shell 是 primary，不得是 duplicate"
    assert e["origin_request_sequence"] == e["effective_request_sequence"]
    assert e["room_latest_durable_application"] == e["delivery_application"], (
        "room canonical fence 必须指向该 canonical application"
    )
    assert e["room_latest_durable_sequence"] == e["effective_request_sequence"]


def test_application_key_is_computed_from_the_downloaded_durable_incoming(
    snap: dict[str, Any],
) -> None:
    """application key 用的是**真实下载并 sealing 后**的 incoming digest，不是猜的。

    两条一起才有意义：key 等于按 frozen request + 实测 incoming sha 重算的值，且
    application 行里的 `incoming_sha256` 就是下载字节的 sha256。少了后半段时，
    「key 用了另一个 digest」这类漂移不会被发现。
    """
    e = snap["e2e_request"]
    assert e["application_key"] == e["expected_application_key"]
    assert e["application_incoming_sha"] == e["incoming_sha_downloaded"]


def test_correlation_happens_strictly_after_sealed_durable(snap: dict[str, Any]) -> None:
    """轨迹是**真实执行顺序**：correlated 必须晚于 sealed_durable，且 request_bound 最早。"""
    order = snap["e2e_request"]["journal"]
    for stage in ("route_verified", "request_bound", "download_started",
                  "sealed_durable", "correlated"):
        assert stage in order, f"{stage} 不在轨迹里: {order}"
    assert order.index("request_bound") < order.index("download_started")
    assert order.index("sealed_durable") < order.index("correlated")
    assert order.index("route_verified") == 0


def test_download_was_pinned_carried_no_credential_and_refused_redirects(
    snap: dict[str, Any],
) -> None:
    """durable 之前的下载控制在端到端路径上真的生效了。"""
    e = snap["e2e_request"]
    assert e["download_follow_redirects"] is False
    assert e["download_max_redirects"] == 0
    assert e["download_url_host_is_literal_ip"] is True, (
        "连接必须用已校验的 IP 字面量（不再做第二次解析 ⇒ rebinding 无处落脚），"
        f"实得 {e['download_url_pinned_to_ip']}"
    )
    assert not _host_is_literal_ip("http://" + e["download_host_header"] + "/x"), (
        "`Host` 头必须保留原始主机名（否则签名/虚拟主机会失效）"
        f"，实得 {e['download_host_header']}"
    )
    headers = {k.lower() for k in e["download_headers"]}
    assert "authorization" not in headers and "cookie" not in headers, (
        f"下载不得携带平台凭证（Requirement 10.7）: {e['download_headers']}"
    )


def test_download_cap_equals_the_capacity_budget(snap: dict[str, Any]) -> None:
    """契约的流式上限与 Requirement 14.11 的压缩预算锁死（50 MiB）。"""
    assert snap["policy"]["size_cap_bytes"] == 50 * 1024 * 1024
    assert snap["policy"]["connect_timeout"] == 5
    assert snap["policy"]["read_timeout"] == 30
    assert snap["policy"]["dns_recheck"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 4. same incoming + 不同 frozen identity 不折叠（Property 64）
# ═══════════════════════════════════════════════════════════════════════════


def test_same_incoming_with_different_frozen_identity_never_folds(
    snap: dict[str, Any],
) -> None:
    """base / representation / bundle / authority / adapter / generation 任一不同 ⇒ 不同 key。

    七个变体（含 baseline）必须得到七个互不相同的 key。只测其中一个维度时，别的维度
    被从 key 里删掉不会被发现。
    """
    nf = snap["no_fold"]
    assert nf["variant_count"] == nf["distinct_count"], (
        f"以下变体折叠成了同一 key: {nf['keys']}"
    )
    assert nf["distinct_count"] == 7, nf["keys"]
    assert nf["stable_on_recompute"] is True


def test_application_key_signature_excludes_status_and_request_id(
    snap: dict[str, Any],
) -> None:
    """key 函数**连入参都不接受** status / request id / room last-applied。

    判据落在签名而不是「算一遍看变不变」：后者只能证明当前实现没用它们，而签名里没有
    这些参数时，任何人想把它们塞进 key 都必须先改签名（会被本条打红）。
    """
    params = set(snap["no_fold"]["key_signature"])
    forbidden = {
        "callback_status", "status", "request_id", "origin_request_id",
        "request_sequence", "room_last_applied_version_id", "last_applied_version_id",
        "delivery_key", "delivery_id",
    }
    assert not (params & forbidden), params & forbidden
    assert {
        "wp_id", "room_id", "generation", "frozen_client_base_version_id",
        "frozen_client_base_representation_id", "incoming_sha256",
        "definition_bundle_sha256", "authority_model_definition_sha256",
        "adapter_build_digest",
    } <= params, params


# ═══════════════════════════════════════════════════════════════════════════
# 5. quarantined incoming 的隔离（Requirement 5.6 / Property 17）
# ═══════════════════════════════════════════════════════════════════════════


def test_failed_ooxml_gate_seals_quarantined_and_returns_non_zero(
    snap: dict[str, Any],
) -> None:
    """安全门失败 ⇒ quarantined + `durable_at=NULL` + 非零 error，零 owner。"""
    q = snap["quarantine"]
    assert q["sealed_quarantined"] is True
    assert q["sealed_durable_absent"] is True, "quarantined 分支不得同时记 sealed_durable"
    assert q["artifact_state"] == "quarantined"
    assert q["artifact_durable_at"] is None, "quarantined 必须保持 durable_at=NULL"
    assert q["artifact_quarantined_at_set"] is True
    assert q["response_error"] != 0, "durable 之前的失败返回 OO 非零 error"
    assert q["delivery_state"] == "rejected"
    assert q["delivery_durable_at"] is None
    assert q["delivery_application"] is None and q["delivery_recovery"] is None
    assert q["error_code"], "隔离必须留下非空 error code（不得静默）"


def test_quarantined_cannot_reach_an_application_at_any_of_the_three_layers(
    snap: dict[str, Any],
) -> None:
    """三层各自独立拒绝：内存 sealing 对象 / 仓储读 DB 行 / 库内 trigger。

    三层都要有，因为它们覆盖不同的绕过路径：内存对象直传 engine、拿 artifact id 绕过
    服务层、直接写 SQL。少一层就少一条绕过路径的防线，而另两层的绿会掩盖它。
    """
    layers = snap["quarantine"]["layers"]
    assert layers["memory"] is not None, "内存层：quarantined 直传 engine 竟被放行"
    assert layers["memory"]["error_code"] == "quarantined_operation_forbidden"
    assert layers["repository"] is not None, "仓储层：assert_incoming_durable 竟放行"
    assert layers["db_trigger"] is not None, "DB 层：application FK trigger 竟放行"
    assert layers["db_trigger"]["source"] != "probe_defect", (
        "这次拒绝来自探针自己的 SQL 错误（类型/列名），**不是** trigger 生效 —— "
        f"WRONG-TEST，必须修探针: {layers['db_trigger']}"
    )
    assert "durable" in layers["db_trigger"]["text"], layers["db_trigger"]


def test_quarantined_can_never_be_released_and_incoming_never_published(
    snap: dict[str, Any],
) -> None:
    """quarantined→durable 与 incoming→published/candidate 都必须被真库拒。"""
    layers = snap["quarantine"]["layers"]
    assert layers["release_to_durable"] is not None, "quarantined 竟可 release 成 durable"
    assert layers["incoming_to_published"] is not None, "incoming 竟可变 published"
    assert layers["incoming_to_candidate"] is not None, "incoming 竟可变 candidate"


def test_no_representation_is_ever_backed_by_an_incoming_artifact(
    snap: dict[str, Any],
) -> None:
    """resolver 可见性：没有任何 representation 的 artifact 是 `kind=incoming`。

    这是「incoming 永不成为 resolver-visible substrate」的可测投影：representation 是
    resolver 的唯一入口，它不指向 incoming ⇒ resolver 拿不到 incoming。
    """
    assert snap["quarantine"]["representations_backed_by_incoming"] == 0


def test_quarantine_allowed_operations_are_exactly_three() -> None:
    """允许集就是 download-only / expire / retention，别的一律拒。"""
    from app.services.workpaper_sync.callback_delivery import (
        QUARANTINE_ALLOWED_OPERATIONS,
        QUARANTINE_FORBIDDEN_OPERATIONS,
        assert_quarantine_operation_allowed,
    )

    assert QUARANTINE_ALLOWED_OPERATIONS == {"download_only", "expire", "retention"}
    for op in QUARANTINE_ALLOWED_OPERATIONS:
        assert_quarantine_operation_allowed(op)
    assert not (set(QUARANTINE_FORBIDDEN_OPERATIONS) & QUARANTINE_ALLOWED_OPERATIONS)
    for op in QUARANTINE_FORBIDDEN_OPERATIONS:
        with pytest.raises(Exception):
            assert_quarantine_operation_allowed(op)


# ═══════════════════════════════════════════════════════════════════════════
# 6. recovery case（Requirement 5.8 / Property 19）
# ═══════════════════════════════════════════════════════════════════════════


def test_no_request_callback_creates_only_a_recovery_case(snap: dict[str, Any]) -> None:
    """无 request 的 durable incoming ⇒ error=0 + recovery case，claim 前三实体为 0。"""
    b = snap["recovery"]["before_claim"]
    assert b["response_error"] == 0, "durable 之后一律 0（Task 4 实测 OO 不重发）"
    assert b["case_state"] == "unclaimed"
    assert b["case_request"] is None
    assert b["case_application"] is None
    assert b["case_operation"] is None
    assert b["delivery_state"] == "unmatched"
    assert b["delivery_durable_at_set"] is True
    assert b["delivery_recovery"] is not None
    assert b["delivery_application"] is None
    assert b["delivery_request"] is None and b["delivery_operation"] is None
    assert "recovery_case_created" in b["journal"]


def test_unauthorized_claim_leaves_all_three_entities_absent(snap: dict[str, Any]) -> None:
    """只读 participant 认领 ⇒ 授权失败，且 case 上仍然三实体全空。

    两段一起断言：只断言「抛错」不够 —— 抛错后若 case 已被推进到 claiming 并写了
    request，那才是真正的缺陷；只断言「三实体空」也不够 —— 那在「什么都没发生」时恒真。
    """
    b = snap["recovery"]["before_claim"]
    assert b["view_claim_error"] is not None, "只读 participant 竟能认领"
    assert b["view_claim_error"]["error_code"] == "recovery_claim_authorization_failed"
    after = b["after_view_claim"]
    assert after["state"] == "unclaimed"
    assert after["request"] is None and after["application"] is None
    assert after["operation"] is None


def test_authorized_claim_creates_request_shell_and_application_atomically(
    snap: dict[str, Any],
) -> None:
    """合法 claim 在一个事务内产出 request + primary shell + application，三者互相一致。"""
    a = snap["recovery"]["after_claim"]
    assert a["case_state"] == "application_created"
    assert a["request_kind"] == "recovery_claim"
    assert a["shape"] == "primary"
    assert a["operation_application"] == a["case_application"], (
        "shell 必须成为绑定同一 canonical application 的 primary"
    )
    assert a["operation_duplicate_of"] is None
    assert a["case_request"] is not None and a["case_operation"] is not None
    assert a["application_incoming"] == a["case_incoming"], (
        "application 的 substrate 必须就是 case 的 durable incoming"
    )
    assert a["cache_hit"] is False


def test_claim_replay_hits_the_same_three_entities(snap: dict[str, Any]) -> None:
    """同 Idempotency-Key 重放只命中，不造第二套三实体。"""
    a = snap["recovery"]["after_claim"]
    assert a["replay_cache_hit"] is True
    assert a["replay_same_application"] is True
    assert a["replay_same_request"] is True
    assert a["recovery_request_rows"] == 1, "并发/重放后 recovery_claim request 只许一行"
    assert a["recovery_application_rows"] == 1


def test_download_only_keeps_all_three_entities_at_zero(snap: dict[str, Any]) -> None:
    dl = snap["recovery"]["download_only"]
    assert dl["state"] == "download_only"
    assert dl["request"] is None and dl["application"] is None and dl["operation"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 7. 失败语义（Requirement 5.7）
# ═══════════════════════════════════════════════════════════════════════════


def test_pre_durable_failure_returns_non_zero_with_zero_owner(snap: dict[str, Any]) -> None:
    """durable 之前失败 ⇒ 非零 error、`durable_at` 空、零 owner，但保留已绑定 request。"""
    pre = snap["failures"]["pre_durable"]
    assert pre["response_error"] != 0
    assert pre["state"] == "rejected"
    assert pre["durable_at"] is None
    assert pre["application"] is None and pre["recovery"] is None
    assert pre["request_retained"] is not None, (
        "已精确绑定的 request 应保留可追溯性（T04 行），只是不算归组"
    )
    assert pre["error_code"], "失败必须留 error code"
    assert "sealed_durable" not in pre["journal"]
    assert "correlated" not in pre["journal"]


# ═══════════════════════════════════════════════════════════════════════════
# 8. forcesave 同 key 语义（Requirement 4.1 / Property 45 / Property 64）
# ═══════════════════════════════════════════════════════════════════════════


def test_same_slot_equal_fingerprint_replay_returns_the_same_ids(
    snap: dict[str, Any],
) -> None:
    k = snap["forcesave_key"]
    assert k["first_cache_hit"] is False
    assert k["replay_cache_hit"] is True
    assert k["replay_same_request"] is True
    assert k["replay_same_operation"] is True


@pytest.mark.parametrize(
    "label", ["cross_participant", "cross_kind", "different_payload"]
)
def test_cross_slot_or_different_payload_conflicts_without_leaking_old_ids(
    snap: dict[str, Any], label: str
) -> None:
    """跨 participant / 跨 kind / payload 不等 ⇒ 409，且**不得**回传旧标识。

    三个场景各自参数化：合成一条时，任何一个维度失效都会被另两个遮蔽。
    """
    got = snap["forcesave_key"][label]
    assert got["conflict"] is True, f"{label} 应 409，实得 {got}"
    assert got["leaks_first_request"] is False, f"{label} 泄露了旧 request id: {got['detail']}"
    assert got["leaks_first_operation"] is False, (
        f"{label} 泄露了旧 operation id: {got['detail']}"
    )
