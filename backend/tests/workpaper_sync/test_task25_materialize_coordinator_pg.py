# -*- coding: utf-8 -*-
"""Task 25 真实 PostgreSQL 行为守卫：HTML→OO 编排的 revision / room / operation 事实。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 25
Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 6.18
Properties: **P8 / P9 / P10 / P11 / P67**

═══ 为什么这些判据必须连真库 ═══

Task 25 的承诺全是**跨表、跨事务的数量关系**，一个都不能靠源码或 mock 证明：

* **P8**「room 创建次数为 0、编辑器挂载次数为 0」—— 只能数 `working_paper_oo_room`
  的真实行数与 `descriptors_issued`；
* **P9**「校验任一点注入失败，current file hash/pointer/revision 均不变」—— 三个
  指针分别在 `working_paper.content_revision`、`working_paper_sync_entry_state.
  current_representation_id` 与 representation 行的 `artifact_sha256` 上；
* **P10**「禁止两次 revision」—— `commit_count` / `transaction_ids` 由 Task 15 的
  `pg_current_xact_id()` 见证给出，而 revision delta 要在真库上前后各读一次；
* **P11**「ready 后仍须 descriptor-confirm」—— 判据是 room 从 `opening` 到 `active`
  的真实状态迁移，以及**确认前** `assert_can_initiate_request` 真的拒绝 forcesave；
* **P67**「candidate 不得进 resolver/room」—— candidate 是 V151 的一张真表，
  它对 resolver 的阻断只有连库才能观察。

═══ 判别性：失败注入必须落在**两个不同**校验点 ═══

🔴 P9 最容易假绿的形态是「只注入一种失败」：materialize 链上有 roundtrip 反读与
未管理区域比对两道校验，若只测前者，把后者删掉不会有任何测试变红。所以本模块用
两个**行为不同**的 adapter 桩分别注入（`drop_keys` ⇒ roundtrip 不等值；
`unmanaged_drift` ⇒ 未管理区域漂移），并各自独立断言三个指针不变 + operation 落
`error` 终态。

同理，422 preflight 家族测三条**不同来源**的拒绝（unapproved bundle / 缺 contract /
capability=single_html），三者在代码里是三个独立分支。

═══ 每个阶段一个独立事务 ═══

与 Task 21~24 同约定：场景逐阶段各开 session 并 commit，阶段间只传纯值
（uuid/int/str）。理由是实测过的两个坑：`sa.update()` 不刷新 identity map，
而 `expire_all()` 在 async 引擎下会 `MissingGreenlet`。

═══ 隔离与采集 ═══

scratch schema `tmp_task25_mc_<hex>` + 独立临时 artifact 根，结束 `DROP SCHEMA CASCADE`
并删目录。全部场景由**一次 `asyncio.run`** 跑完落进快照；采集阶段异常一律
**记录不穿透** —— 穿透会把整个 module 变成 collection ERROR，而 `-rf` 只列 FAILED
不列 ERROR ⇒ 定向变异看不到预期失败项 ⇒ 判 GREEN。
`test_no_phase_crashed_during_collection` 是这个决定的另一半。

`DATABASE_URL` 非 PostgreSQL 时**直接失败而不是 skip** —— skip 等于静默抹掉本任务
唯一判据。
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import traceback
import uuid
import zipfile
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

_SCHEMA_PREFIX = "tmp_task25_mc_"
ENTRY = "xlsx/gt-d2-accounts-receivable"
SECRET = "task25-pg-secret"
PERIOD = "header_block/period_label"
TOTAL = "header_block/total_amount"

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

_CONTENT_TYPES = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="xml" ContentType="application/xml"/></Types>'
)

#: confirm-descriptor 的篡改用例（每条一个**不同**的 identity 项）。
_TAMPER_CASES = (
    "generation",
    "doc_key",
    "artifact_sha256",
    "write_fence_epoch",
    "definition_bundle_sha256",
    "authority_model_definition_sha256",
    "content_revision",
    "participant_id",
)

#: 422 preflight 家族在真库上**可达**的三条独立来源。
#:
#: 🔴 刻意**不含** `unapproved_bundle`：V151 让它在库里不可构造 ——
#: `wpsync_check_representation_bundle_approved` 拒绝 representation 指向非 approved
#: bundle，`wpsync_check_bundle_immutable` 拒绝 `approved → candidate`，
#: `trg_wpcr_immutable` 又禁止 UPDATE representation。也就是说「current representation
#: 指向未 approved bundle」这个状态在真库里**不存在**。硬造它只能靠禁用触发器，那等于
#: 测一个不可能发生的世界。该分支的判据改由离线文件用 stub resolution 覆盖
#: （`test_task25_materialize_coordinator.py::test_preflight_maps_*`），
#: 那里跑的是**同一段生产映射代码**。
_PREFLIGHT_CASES = (
    "substrate_not_published",
    "missing_contract",
    "capability_single_html",
)

#: P9 的两个**不同**注入点。
_INJECTION_CASES = ("roundtrip_drop_key", "unmanaged_drift")


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _err(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)[-4:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


def _ooxml(*, extra: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("xl/workbook.xml", b'<?xml version="1.0"?><workbook><sheets/></workbook>')
        for name, payload in (extra or {}).items():
            zf.writestr(name, payload)
    return buf.getvalue()


def _contract_payload() -> dict[str, Any]:
    from app.services.workpaper_sync import contracts as C

    return {
        "schema_version": C.CONTRACT_SCHEMA_VERSION,
        "contract_id": ENTRY,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": _d("task25-template"),
        "instrumentation_definition_sha256": _d("task25-instrumentation"),
        "template": {
            "relative_path": "D/D2 应收账款.xlsx",
            "template_sha256": _d("task25-template-blob"),
            "normalized_structure_hash": _d("task25-template-structure"),
        },
        "identity_carriers": ["hidden_sheet", "defined_name"],
        "sheets": [
            {
                "sheet_key": "d2-receivables",
                "excel_name": "D2 应收账款",
                "locator": {"anchor": "defined_name_ref"},
                "tables": [
                    {
                        "table_key": "header_block",
                        "anchor": "A1",
                        "header_rows": 1,
                        "fields": [
                            {
                                "stable_field_key": PERIOD,
                                "json_pointer": "/header/periodLabel",
                                "column_key": "period_label",
                                "cell": {"column": "B", "row_from": 2},
                                "mode": "editable",
                                "value_type": "text",
                                "source_ref": "源xlsx!B2",
                            },
                            {
                                "stable_field_key": TOTAL,
                                "json_pointer": "/header/totalAmount",
                                "column_key": "total_amount",
                                "cell": {"column": "C", "row_from": 3},
                                "mode": "editable",
                                "value_type": "amount",
                                "source_ref": "源xlsx!C3",
                            },
                        ],
                    }
                ],
            }
        ],
    }


class _JsonCarrierAdapter:
    """真 OOXML 容器 + JSON 受管部件的载体替身（真写真读）。

    不是 mock：`materialize` 真写 zip、`extract` 真读回来，所以 roundtrip 等值判据在
    **真实执行**上生效。真正的 Excel/Word 引擎归 Tasks 36~38 / 59~61。

    两个注入开关分别对应 P9 的两个**不同**校验点：`drop_keys` 让反读缺字段
    （roundtrip 不等值），`unmanaged_drift` 让未管理区域比对报漂移。分开是必需的 ——
    只注入一种时，删掉另一道校验不会有任何测试变红。
    """

    adapter_id = ENTRY
    document_type = "xlsx"
    contract_version = "1.0.0"

    def __init__(
        self, *, drop_keys: tuple[str, ...] = (), unmanaged_drift: bool = False
    ) -> None:
        self.drop_keys = drop_keys
        self.unmanaged_drift = unmanaged_drift
        self.materialize_calls = 0
        self.extract_calls = 0
        self.unmanaged_calls = 0

    async def read_current_projection(self, ctx):  # pragma: no cover - 本任务不用
        raise NotImplementedError

    async def stage_projection_mutation(self, ctx, merged, *, expected_revision):
        raise NotImplementedError  # pragma: no cover - 本任务不用

    def materialize(self, *, substrate, projection, output, contract):
        from app.services.workpaper_sync.adapters.base import MaterializeResult

        self.materialize_calls += 1
        values = {
            key: {
                "value": (
                    format(value.value, "f")
                    if hasattr(value.value, "as_tuple")
                    else value.value
                ),
                "value_type": value.value_type.value,
                "mode": value.mode.value,
                "row_key": value.row_key,
            }
            for key, value in projection.values.items()
            if key not in self.drop_keys
        }
        blob = _ooxml(
            extra={
                "_gt_sync/projection.json": json.dumps(
                    {"contract_id": projection.contract_id, "values": values},
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode("utf-8")
            }
        )
        Path(output).write_bytes(blob)
        return MaterializeResult(
            output_path=Path(output),
            document_type=projection.document_type,
            artifact_sha256=hashlib.sha256(blob).hexdigest(),
            structure_hash=_d("task25-structure"),
            identity_inventory_sha256=_d("task25-identity"),
            managed_field_count=len(values),
        )

    def extract(self, *, artifact, contract):
        from app.services.workpaper_sync import contracts as C
        from app.services.workpaper_sync.adapters.base import FieldValue, Projection

        self.extract_calls += 1
        with zipfile.ZipFile(artifact) as zf:
            raw = json.loads(zf.read("_gt_sync/projection.json").decode("utf-8"))
        return Projection(
            contract_id=raw["contract_id"],
            semantic_version=contract.semantic_version,
            document_type=contract.document_type,
            values={
                key: FieldValue(
                    stable_key=key,
                    value=item["value"],
                    value_type=C.ValueType(item["value_type"]),
                    mode=C.FieldMode(item["mode"]),
                    row_key=item.get("row_key"),
                )
                for key, item in raw["values"].items()
            },
        )

    def verify_unmanaged_regions(self, *, before, after, contract):
        from app.services.workpaper_sync.adapters.base import UnmanagedRegionReport

        self.unmanaged_calls += 1
        if self.unmanaged_drift:
            return UnmanagedRegionReport(
                equivalent=False,
                inspected_aspects=("formula", "style", "drawing"),
                first_difference="xl/worksheets/sheet1.xml!D9 公式被改写",
            )
        return UnmanagedRegionReport(
            equivalent=True, inspected_aspects=("formula", "style", "drawing")
        )


# ═══════════════════════════════════════════════════════════════════════════
# 采集
# ═══════════════════════════════════════════════════════════════════════════


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - 一次采集覆盖全部场景
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.dataset_models import ImportEventConsumption, ImportEventOutbox
    from app.models.workpaper_sync_models import (
        WorkpaperOoRoom,
        WorkpaperSyncEntryState,
        WorkpaperSyncOperation,
        WorkpaperSyncOperationEvent,
    )
    from app.services import event_bus as event_bus_module
    from app.services.workpaper_sync import contracts as C
    from app.services.workpaper_sync import definitions as D
    from app.services.workpaper_sync import materialize_coordinator as MC
    from app.services.workpaper_sync import representations as R
    from app.services.workpaper_sync.adapters.base import (
        FieldValue,
        Projection,
        UnmanagedRegionDriftError,
    )
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.content_mutation import (
        ContentMutationService,
        RoundtripEquivalenceError,
    )
    from app.services.workpaper_sync.entry_profile import Capability
    from app.services.workpaper_sync.models import (
        ArtifactKind,
        ArtifactState,
        BundleSlot,
        BundleSlotSpec,
        CandidateState,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService
    from app.services.workpaper_sync.rooms import (
        DescriptorNotConfirmedError,
        RoomService,
    )

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 25 的判据是 room 行数、revision 前后差、entry pointer 与 operation 终态，"
            "全部依赖真实 PostgreSQL 约束与事务语义；当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip** —— skip 等于"
            "静默抹掉本任务唯一判据。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task25_store_"))
    (base_root / "storage").mkdir()
    (base_root / "definition_store").mkdir()

    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "base_root": str(base_root),
        "server_version": None,
        "apply_errors": [],
        "harness_errors": {},
        "flush": {},
        "authorization": {},
        "blocked": {},
        "injection": {},
        "commit": {},
        "idempotency": {},
        "descriptor": {},
        "confirm": {},
        "tamper": {},
        "preflight": {},
        "candidate": {},
        "operations": {},
        "stale_fence": {},
    }

    def _phase_failed(name: str, exc: BaseException) -> None:
        snap["harness_errors"][name] = _err(exc)

    engine = None
    bus = event_bus_module.event_bus
    previous_redis_flag = bus._redis_available
    bus._redis_available = False  # Redis 不参与判定，避免 xadd 抖动
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

        outbox_tables = [ImportEventOutbox.__table__, ImportEventConsumption.__table__]
        async with engine.begin() as conn:
            seen: dict[str, tuple[str, ...]] = {}
            for table in outbox_tables:
                for column in table.columns:
                    if isinstance(column.type, sa.Enum) and column.type.name:
                        seen.setdefault(column.type.name, tuple(column.type.enums))
            for name, labels in sorted(seen.items()):
                await conn.exec_driver_sql(
                    "CREATE TYPE {n} AS ENUM ({l})".format(
                        n=name, l=", ".join(f"'{x}'" for x in labels)
                    )
                )
            await conn.run_sync(
                lambda sync_conn: ImportEventOutbox.metadata.create_all(
                    sync_conn, tables=outbox_tables, checkfirst=True
                )
            )

        project, wp, other_wp, user = (
            uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        )
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{project}')")
            await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{user}')")
            for w in (wp, other_wp):
                await conn.exec_driver_sql(
                    f"INSERT INTO working_paper (id, project_id) VALUES ('{w}', '{project}')"
                )

        artifacts = CanonicalArtifactRepository(base_root)
        contract = C.parse_contract(_contract_payload())
        adapter_digest = _d("task25-adapter-build")

        # ═══ 世界：definitions / bundle / gen-1 representation ═════════════
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
                "authority_alt": "authority_model",
                "bundle_payload": "bundle",
                "bundle_unapproved": "bundle",
            }.items()
        }
        gen1 = artifacts.publish_representation(
            entry_id=ENTRY,
            generation=1,
            staged=artifacts.stage_bytes(
                project_id=project,
                wp_id=wp,
                payload=_ooxml(
                    extra={
                        "_gt_sync/projection.json": json.dumps(
                            {"contract_id": ENTRY, "values": {}}, sort_keys=True
                        ).encode()
                    }
                ),
                document_type="xlsx",
            ),
        )
        proj0 = artifacts.publish_projection(
            revision=0,
            staged=artifacts.stage_bytes(
                project_id=project,
                wp_id=wp,
                payload=b"projection-baseline",
                document_type="json.gz",
            ),
        )

        world: dict[str, Any] = {}
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            art = {
                name: await repo.register_artifact(
                    project_id=project, wp_id=wp, kind=ArtifactKind.definition,
                    state=ArtifactState.published, relative_path=pub.relative_path,
                    sha256=pub.sha256, size_bytes=pub.size_bytes,
                    document_type=pub.document_type, retention_class="definition",
                )
                for name, pub in blobs.items()
            }
            art_gen1 = await repo.register_artifact(
                project_id=project, wp_id=wp, kind=ArtifactKind.canonical,
                state=ArtifactState.published, relative_path=gen1.relative_path,
                sha256=gen1.sha256, size_bytes=gen1.size_bytes, document_type="xlsx",
            )
            art_proj0 = await repo.register_artifact(
                project_id=project, wp_id=wp, kind=ArtifactKind.projection,
                state=ArtifactState.published, relative_path=proj0.relative_path,
                sha256=proj0.sha256, size_bytes=proj0.size_bytes,
                document_type="json.gz",
            )
            tpl = await repo.create_definition_artifact(
                kind="template", logical_id="task25.tpl", semantic_version="1.0.0",
                blob_artifact_id=art["tpl"].id, sha256=_d("task25-template"),
                structure_hash=_d("task25-tpl-structure"), source_commit="task25",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation", logical_id="task25.instr",
                semantic_version="1.0.0", blob_artifact_id=art["instr"].id,
                sha256=_d("task25-instrumentation"),
                structure_hash=_d("task25-instr-structure"), source_commit="task25",
            )
            contract_def = await repo.create_definition_artifact(
                kind="contract", logical_id="task25.contract",
                semantic_version="1.0.0", blob_artifact_id=art["contract"].id,
                # contract definition 的 digest 必须等于 SyncContract 的 canonical digest：
                # `SyncContext.assert_frozen_identity_consistent` 用它做三向锁死。
                sha256=contract.canonical_sha256, source_commit="task25",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task25.authority",
                semantic_version="1.0.0", blob_artifact_id=art["authority"].id,
                sha256=_d("task25-authority"),
                authority_model_type="projection_contract", source_commit="task25",
            )
            authority_alt = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task25.authority.alt",
                semantic_version="1.0.1", blob_artifact_id=art["authority_alt"].id,
                sha256=_d("task25-authority-alt"),
                authority_model_type="projection_contract", source_commit="task25",
            )

            def _slots() -> dict[BundleSlot, BundleSlotSpec]:
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
            bundle_unapproved = await repo.create_definition_bundle(
                authority_model_definition_id=authority_alt.id,
                slots=_slots(),
                canonical_payload_artifact_id=art["bundle_unapproved"].id,
                canonical_payload_sha256=D.bundle_canonical_digest(
                    authority_model="projection_contract",
                    authority_model_definition_sha256=authority_alt.sha256,
                    slots=_slots(),
                ),
                approved=False,
            )
            cv0 = await repo.create_content_version(
                project_id=project, wp_id=wp, entry_id=ENTRY, revision=0, source="html",
                projection_artifact_id=art_proj0.id,
                projection_sha256=art_proj0.sha256, actor_id=user,
            )
            rep1 = await repo.create_representation(
                project_id=project, wp_id=wp, entry_id=ENTRY,
                content_version_id=cv0.id, generation=1, document_type="xlsx",
                artifact_id=art_gen1.id, artifact_sha256=art_gen1.sha256,
                definition_bundle_id=bundle.id,
                authority_model_definition_id=authority.id,
                adapter_id=ENTRY, adapter_build_digest=adapter_digest,
                structure_hash=_d("task25-structure-1"),
                identity_inventory_sha256=_d("task25-identity-1"),
                reason="content_commit",
            )
            await repo.set_entry_pointer(
                wp_id=wp, entry_id=ENTRY, representation_id=rep1.id, generation=1
            )
            await repo.set_current_content_version(wp, cv0.id)
            await s.commit()
            world.update({
                "cv0": cv0.id, "rep1": rep1.id, "bundle": bundle.id,
                "bundle_unapproved": bundle_unapproved.id, "authority": authority.id,
                "authority_alt": authority_alt.id, "contract_def": contract_def.id,
                "tpl": tpl.id, "instr": instr.id, "gen1_sha": gen1.sha256,
            })
        snap["world"] = {k: str(v) for k, v in world.items()}

        # ── 工具 ─────────────────────────────────────────────────────────
        def _projection(period: str, total: str) -> Projection:
            from decimal import Decimal

            return Projection(
                contract_id=contract.contract_id,
                semantic_version=contract.semantic_version,
                document_type=contract.document_type,
                values={
                    PERIOD: FieldValue(
                        stable_key=PERIOD, value=period,
                        value_type=C.ValueType.text, mode=C.FieldMode.editable,
                    ),
                    TOTAL: FieldValue(
                        stable_key=TOTAL, value=Decimal(total),
                        value_type=C.ValueType.amount, mode=C.FieldMode.editable,
                    ),
                },
            )

        def _coordinator(session, *, artifacts_repo=artifacts) -> Any:
            repo = WorkpaperSyncRepository(session)
            resolution = CanonicalResolutionService(session, artifacts_repo)
            return MC.MaterializeCoordinator(
                session=session,
                repository=repo,
                artifacts=artifacts_repo,
                resolution=resolution,
                mutations=ContentMutationService(
                    session=session, repository=repo, artifacts=artifacts_repo,
                    resolution=resolution,
                ),
                rooms=RoomService(repo),
                token_codec=MC.PendingMutationTokenCodec(SECRET),
                representations=R.RepresentationService(
                    session=session, repository=repo, artifacts=artifacts_repo,
                    resolution=resolution,
                ),
            )

        def _request(
            *,
            token: str | None,
            key: str,
            revision: int,
            projection: Projection,
            adapter: Any,
            capability: Any = Capability.bidirectional,
            with_contract: bool = True,
            project_id: uuid.UUID | None = None,
            entry_id: str = ENTRY,
        ) -> Any:
            return MC.MaterializeRequest(
                project_id=project_id or project,
                wp_id=wp,
                entry_id=entry_id,
                sheet_key="d2-receivables",
                user_id=user,
                pending_mutation_token=token,
                idempotency_key=key,
                expected_revision=revision,
                capability=capability,
                projection=projection,
                document_type="xlsx",
                contract=contract if with_contract else None,
                adapter=adapter,
                adapter_id=ENTRY,
                adapter_build_digest=adapter_digest,
                permission_epoch=1,
                lease_token=f"lease-{key}",
            )

        async def _pointers() -> dict[str, Any]:
            """三个指针 + room/operation 计数的一次快照（P9 的判据面）。"""
            async with Session() as s:
                revision = int(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT content_revision FROM working_paper WHERE id = :w"
                            ),
                            {"w": wp},
                        )
                    ).scalar_one()
                )
                state = (
                    await s.execute(
                        sa.select(WorkpaperSyncEntryState).where(
                            WorkpaperSyncEntryState.wp_id == wp,
                            WorkpaperSyncEntryState.entry_id == ENTRY,
                        )
                    )
                ).scalar_one()
                current_sha = (
                    await s.execute(
                        sa.text(
                            "SELECT artifact_sha256 FROM "
                            "working_paper_content_representation WHERE id = :r"
                        ),
                        {"r": state.current_representation_id},
                    )
                ).scalar_one()
                rooms = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count()).select_from(WorkpaperOoRoom).where(
                                WorkpaperOoRoom.wp_id == wp,
                                WorkpaperOoRoom.entry_id == ENTRY,
                            )
                        )
                    ).scalar_one()
                )
                ops = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count()).select_from(
                                WorkpaperSyncOperation
                            ).where(WorkpaperSyncOperation.wp_id == wp)
                        )
                    ).scalar_one()
                )
                return {
                    "revision": revision,
                    "current_representation_id": str(state.current_representation_id),
                    "current_generation": int(state.representation_generation),
                    "current_artifact_sha256": str(current_sha),
                    "rooms": rooms,
                    "operations": ops,
                }

        async def _operation_ids() -> set[str]:
            async with Session() as s:
                return {
                    str(x)
                    for x in (
                        (
                            await s.execute(
                                sa.select(WorkpaperSyncOperation.id).where(
                                    WorkpaperSyncOperation.wp_id == wp
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                }

        async def _flush(
            key: str, projection: Projection, revision: int, **over: Any
        ) -> dict[str, Any]:
            async with Session() as s:
                coordinator = _coordinator(s)
                request = _request(
                    token=None, key=key, revision=revision,
                    projection=projection, adapter=_JsonCarrierAdapter(), **over,
                )
                authorized = await coordinator.authorize_create(request)
                receipt = await coordinator.create_pending_mutation(authorized)
                return {
                    "token": receipt.pending_mutation_token,
                    "pending_id": str(receipt.pending_mutation_id),
                    "replayed": receipt.replayed,
                    "payload_sha256": receipt.payload_sha256,
                    "expected_revision": receipt.expected_revision,
                    "body": receipt.as_dict(),
                }

        # ═══ 阶段 1：flush 不推进 revision + 幂等 ══════════════════════════
        try:
            before = await _pointers()
            p1 = _projection("2025年度", "1234.50")
            first = await _flush("idem-1", p1, before["revision"])
            after = await _pointers()
            replay = await _flush("idem-1", p1, before["revision"])
            same_key_other_payload: str | None = None
            try:
                await _flush("idem-1", _projection("2025年度", "9999.00"), before["revision"])
            except Exception as exc:  # noqa: BLE001 - 期望拒绝，记类型
                same_key_other_payload = type(exc).__name__
            same_key_other_revision: str | None = None
            try:
                await _flush("idem-1", p1, before["revision"] + 5)
            except Exception as exc:  # noqa: BLE001
                same_key_other_revision = type(exc).__name__
            async with Session() as s:
                scope_kind = (
                    await s.execute(
                        sa.text(
                            "SELECT count(*) FROM working_paper_sync_scope_index "
                            "WHERE resource_kind = 'pending_mutation' "
                            "AND resource_id = :rid AND retired_at IS NULL"
                        ),
                        {"rid": first["pending_id"]},
                    )
                ).scalar_one()
                pending_rows = (
                    await s.execute(
                        sa.text("SELECT count(*) FROM working_paper_pending_mutation")
                    )
                ).scalar_one()
            snap["flush"] = {
                "revision_before": before["revision"],
                "revision_after": after["revision"],
                "rooms_after": after["rooms"],
                "operations_after": after["operations"],
                "first_pending_id": first["pending_id"],
                "replay_pending_id": replay["pending_id"],
                "replay_flag": replay["replayed"],
                "first_replay_flag": first["replayed"],
                "receipt_keys": sorted(first["body"]),
                "scope_rows": int(scope_kind),
                "pending_rows": int(pending_rows),
                "same_key_other_payload": same_key_other_payload,
                "same_key_other_revision": same_key_other_revision,
            }
            token1 = first["token"]
            base_revision = before["revision"]
        except Exception as exc:  # noqa: BLE001
            _phase_failed("flush", exc)
            token1, base_revision = None, 0

        # ═══ 阶段 2：P8 —— 没有/坏 token ⇒ 零 room、零 operation、零 descriptor ══
        for case, token in (
            ("missing_token", None),
            ("tampered_token", (token1 or "x.y")[:-3] + "AAA"),
            ("foreign_secret", None),  # 下面单独造
        ):
            try:
                if case == "foreign_secret":
                    async with Session() as s:
                        alien = MC.PendingMutationTokenCodec("another-secret")
                        payload = MC.PendingMutationTokenPayload(
                            schema_version=MC.TOKEN_SCHEMA_VERSION,
                            pending_mutation_id=uuid.uuid4(),
                            project_id=project, wp_id=wp, entry_id=ENTRY,
                            sheet_key="d2-receivables", user_id=user,
                            expected_revision=base_revision,
                            payload_sha256=_d("whatever"),
                            idempotency_key="idem-alien",
                            expires_at=_now() + timedelta(minutes=5),
                        )
                        token = alien.encode(payload)
                before = await _pointers()
                async with Session() as s:
                    coordinator = _coordinator(s)
                    request = _request(
                        token=token, key="idem-1", revision=base_revision,
                        projection=_projection("2025年度", "1234.50"),
                        adapter=_JsonCarrierAdapter(),
                    )
                    refusal = None
                    try:
                        authorized = await coordinator.authorize(request)
                        await coordinator.materialize(authorized)
                    except Exception as exc:  # noqa: BLE001 - 期望拒绝
                        refusal = exc
                    descriptors = coordinator.descriptors_issued
                    commits = coordinator.commits_invoked
                after = await _pointers()
                snap["blocked"][case] = {
                    "refusal": None if refusal is None else type(refusal).__name__,
                    "error_code": (
                        None if refusal is None
                        else str(getattr(refusal, "error_code", ""))
                    ),
                    "status": (
                        None if refusal is None
                        else MC.classify_materialize_rejection(refusal)
                    ),
                    "descriptors_issued": descriptors,
                    "commits_invoked": commits,
                    "rooms_before": before["rooms"],
                    "rooms_after": after["rooms"],
                    "operations_before": before["operations"],
                    "operations_after": after["operations"],
                    "revision_before": before["revision"],
                    "revision_after": after["revision"],
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed(f"blocked_{case}", exc)

        # ═══ 阶段 3：422 preflight 家族 ⇒ 零 operation、零 room ═════════════
        for case in _PREFLIGHT_CASES:
            try:
                key = f"idem-pre-{case}"
                projection = _projection("2025年度", f"{abs(hash(case)) % 900 + 100}.00")
                # `substrate_not_published` 用一个**全新** entry：它合法地没有 current
                # representation pointer，正是 Requirement 6.18「首个 representation 只能
                # 由 template upgrader 产生」的真库形态。
                entry = (
                    f"{ENTRY}#fresh-{uuid.uuid4().hex[:8]}"
                    if case == "substrate_not_published"
                    else ENTRY
                )
                flushed = await _flush(key, projection, base_revision, entry_id=entry)
                before = await _pointers()
                async with Session() as s:
                    coordinator = _coordinator(s)
                    request = _request(
                        token=flushed["token"], key=key, revision=base_revision,
                        projection=projection, adapter=_JsonCarrierAdapter(),
                        entry_id=entry,
                        capability=(
                            Capability.single_html
                            if case == "capability_single_html"
                            else Capability.bidirectional
                        ),
                        with_contract=(case != "missing_contract"),
                    )
                    refusal = None
                    try:
                        authorized = await coordinator.authorize(request)
                        await coordinator.materialize(authorized)
                    except Exception as exc:  # noqa: BLE001
                        refusal = exc
                    descriptors = coordinator.descriptors_issued
                after = await _pointers()
                snap["preflight"][case] = {
                    "refusal": None if refusal is None else type(refusal).__name__,
                    "error_code": (
                        None if refusal is None
                        else str(getattr(refusal, "error_code", ""))
                    ),
                    "status": (
                        None if refusal is None
                        else MC.classify_materialize_rejection(refusal)
                    ),
                    "is_preflight_group": (
                        None if refusal is None
                        else isinstance(refusal, MC.MaterializePreflightError)
                    ),
                    "descriptors_issued": descriptors,
                    "rooms_delta": after["rooms"] - before["rooms"],
                    "operations_delta": after["operations"] - before["operations"],
                    "revision_delta": after["revision"] - before["revision"],
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed(f"preflight_{case}", exc)

        # ═══ 阶段 4：P9 —— 两个注入点各自保持三个指针不变 + operation 落 error ══
        for case in _INJECTION_CASES:
            try:
                key = f"idem-inj-{case}"
                projection = _projection("2025年度", "555.00")
                flushed = await _flush(key, projection, base_revision)
                before = await _pointers()
                op_ids_before = await _operation_ids()
                adapter = _JsonCarrierAdapter(
                    drop_keys=(TOTAL,) if case == "roundtrip_drop_key" else (),
                    unmanaged_drift=(case == "unmanaged_drift"),
                )
                async with Session() as s:
                    coordinator = _coordinator(s)
                    request = _request(
                        token=flushed["token"], key=key, revision=base_revision,
                        projection=projection, adapter=adapter,
                    )
                    refusal = None
                    try:
                        authorized = await coordinator.authorize(request)
                        await coordinator.materialize(authorized)
                    except Exception as exc:  # noqa: BLE001
                        refusal = exc
                    descriptors = coordinator.descriptors_issued
                after = await _pointers()
                # 🔴 按**集合差**定位本次新建的 operation，不按 `created_at desc` 取首行：
                # 同一时钟刻度内插入的两行会并列，取首行是不确定的。
                new_ops = sorted(await _operation_ids() - op_ids_before)
                op = None
                events: list[Any] = []
                if len(new_ops) == 1:
                    async with Session() as s:
                        op = (
                            await s.execute(
                                sa.select(WorkpaperSyncOperation).where(
                                    WorkpaperSyncOperation.id == uuid.UUID(new_ops[0])
                                )
                            )
                        ).scalar_one()
                        events = list(
                            (
                                await s.execute(
                                    sa.select(WorkpaperSyncOperationEvent.to_state)
                                    .where(
                                        WorkpaperSyncOperationEvent.operation_id == op.id
                                    )
                                    .order_by(WorkpaperSyncOperationEvent.sequence_no)
                                )
                            )
                            .scalars()
                            .all()
                        )
                snap["injection"][case] = {
                    "new_operation_count": len(new_ops),
                    "refusal": None if refusal is None else type(refusal).__name__,
                    "expected_refusal": {
                        "roundtrip_drop_key": RoundtripEquivalenceError.__name__,
                        "unmanaged_drift": UnmanagedRegionDriftError.__name__,
                    }[case],
                    "descriptors_issued": descriptors,
                    "materialize_calls": adapter.materialize_calls,
                    "extract_calls": adapter.extract_calls,
                    "unmanaged_calls": adapter.unmanaged_calls,
                    "revision_unchanged": before["revision"] == after["revision"],
                    "pointer_unchanged": (
                        before["current_representation_id"]
                        == after["current_representation_id"]
                    ),
                    "artifact_sha_unchanged": (
                        before["current_artifact_sha256"]
                        == after["current_artifact_sha256"]
                    ),
                    "rooms_delta": after["rooms"] - before["rooms"],
                    "operation_state": None if op is None else str(op.state),
                    "operation_error_code": None if op is None else op.error_code,
                    "operation_room_id": (
                        None if op is None or op.room_id is None else str(op.room_id)
                    ),
                    "operation_events": [str(x) for x in events],
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed(f"injection_{case}", exc)

        # ═══ 阶段 5：happy path —— 单次 commit、单事务、恰一次 revision ═════
        descriptor_payload: dict[str, Any] | None = None
        room_id_ok: uuid.UUID | None = None
        participant_id_ok: uuid.UUID | None = None
        try:
            key = "idem-ok"
            projection = _projection("2025年度", "1234.50")
            flushed = await _flush(key, projection, base_revision)
            before = await _pointers()
            adapter = _JsonCarrierAdapter()
            async with Session() as s:
                coordinator = _coordinator(s)
                request = _request(
                    token=flushed["token"], key=key, revision=base_revision,
                    projection=projection, adapter=adapter,
                )
                authorized = await coordinator.authorize(request)
                outcome = await coordinator.materialize(authorized)
                descriptors = coordinator.descriptors_issued
                commits = coordinator.commits_invoked
            after = await _pointers()
            descriptor = outcome.descriptor
            assert descriptor is not None
            descriptor_payload = descriptor.as_dict()
            room_id_ok = descriptor.room_id
            participant_id_ok = descriptor.participant_id
            async with Session() as s:
                room_state = (
                    await s.execute(
                        sa.text("SELECT state FROM working_paper_oo_room WHERE id = :r"),
                        {"r": room_id_ok},
                    )
                ).scalar_one()
                op = (
                    await s.execute(
                        sa.select(WorkpaperSyncOperation).where(
                            WorkpaperSyncOperation.id == outcome.operation_id
                        )
                    )
                ).scalar_one()
                events = (
                    (
                        await s.execute(
                            sa.select(WorkpaperSyncOperationEvent.to_state)
                            .where(WorkpaperSyncOperationEvent.operation_id == op.id)
                            .order_by(WorkpaperSyncOperationEvent.sequence_no)
                        )
                    )
                    .scalars()
                    .all()
                )
                pending_state = (
                    await s.execute(
                        sa.text(
                            "SELECT state FROM working_paper_pending_mutation WHERE id = :p"
                        ),
                        {"p": uuid.UUID(flushed["pending_id"])},
                    )
                ).scalar_one()
            snap["commit"] = {
                "commit_count": outcome.commit_count,
                "transaction_ids": list(outcome.transaction_ids),
                "revision_delta": outcome.revision_delta,
                "revision_before": before["revision"],
                "revision_after": after["revision"],
                "rooms_opened": outcome.rooms_opened,
                "descriptors_issued": descriptors,
                "commits_invoked": commits,
                "replayed": outcome.replayed,
                "business_identity_reused": outcome.business_identity_reused,
                "materialize_calls": adapter.materialize_calls,
                "extract_calls": adapter.extract_calls,
                "unmanaged_calls": adapter.unmanaged_calls,
                "pointer_moved": (
                    before["current_representation_id"]
                    != after["current_representation_id"]
                ),
                "current_representation_id": after["current_representation_id"],
                "descriptor_representation_id": str(outcome.representation_id),
                "room_state_before_confirm": str(room_state),
                "operation_state": str(op.state),
                "operation_direction": str(op.direction),
                "operation_room_id": None if op.room_id is None else str(op.room_id),
                "operation_application_id": (
                    None if op.application_id is None else str(op.application_id)
                ),
                "operation_duplicate_of": (
                    None if op.duplicate_of_operation_id is None
                    else str(op.duplicate_of_operation_id)
                ),
                "operation_events": [str(x) for x in events],
                "pending_state": str(pending_state),
                "projection_sha256": (
                    None if outcome.receipt is None else outcome.receipt.projection_sha256
                ),
                "flush_payload_sha256": flushed["payload_sha256"],
            }
            snap["descriptor"] = descriptor_payload
            ok_key, ok_token = key, flushed["token"]
            revision_after_ok = after["revision"]
        except Exception as exc:  # noqa: BLE001
            _phase_failed("commit", exc)
            ok_key, ok_token, revision_after_ok = "", None, 0

        # ═══ 阶段 6：P11 —— 确认前 forcesave 被拒；确认后放行 ════════════════
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                rooms = RoomService(repo)
                before_confirm = None
                try:
                    await rooms.assert_can_initiate_request(
                        room_id=room_id_ok, participant_id=participant_id_ok
                    )
                except Exception as exc:  # noqa: BLE001 - 期望拒绝
                    before_confirm = type(exc).__name__
            async with Session() as s:
                coordinator = _coordinator(s)
                request = _request(
                    token=ok_token, key=ok_key, revision=base_revision,
                    projection=_projection("2025年度", "1234.50"),
                    adapter=_JsonCarrierAdapter(),
                )
                authorized = await coordinator.authorize(request)
                echoed = dict(descriptor_payload or {})
                confirm = await coordinator.confirm_descriptor(
                    authorized,
                    room_id=room_id_ok,
                    participant_id=participant_id_ok,
                    echoed={
                        "participant_id": str(participant_id_ok),
                        "generation": echoed["generation"],
                        "doc_key": echoed["doc_key"],
                        "representation_id": echoed["representation_id"],
                        "artifact_sha256": echoed["artifact_sha256"],
                        "content_revision": echoed["server_applied_revision"],
                        "write_fence_epoch": echoed["write_fence_epoch"],
                        "authority_model_definition_sha256": echoed[
                            "authority_model_definition_sha256"
                        ],
                        "definition_bundle_id": echoed["definition_bundle_id"],
                        "definition_bundle_sha256": echoed["definition_bundle_sha256"],
                    },
                    idempotency_key="confirm-1",
                )
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                rooms = RoomService(repo)
                after_confirm = None
                try:
                    await rooms.assert_can_initiate_request(
                        room_id=room_id_ok, participant_id=participant_id_ok
                    )
                except Exception as exc:  # noqa: BLE001
                    after_confirm = type(exc).__name__
                room_state_after = (
                    await s.execute(
                        sa.text("SELECT state FROM working_paper_oo_room WHERE id = :r"),
                        {"r": room_id_ok},
                    )
                ).scalar_one()
                revision_after_confirm = int(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT content_revision FROM working_paper WHERE id = :w"
                            ),
                            {"w": wp},
                        )
                    ).scalar_one()
                )
            snap["confirm"] = {
                "forcesave_before_confirm": before_confirm,
                "expected_before_confirm": DescriptorNotConfirmedError.__name__,
                "forcesave_after_confirm": after_confirm,
                "room_state_after": str(room_state_after),
                "forcesave_unlocked": confirm.forcesave_unlocked,
                "confirmation_id": str(confirm.confirmation_id),
                "revision_unchanged_by_confirm": (
                    revision_after_confirm == revision_after_ok
                ),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("confirm", exc)

        # ═══ 阶段 7：篡改 confirm 的每一项 identity ⇒ 409 ═══════════════════
        for case in _TAMPER_CASES:
            try:
                async with Session() as s:
                    coordinator = _coordinator(s)
                    request = _request(
                        token=ok_token, key=ok_key, revision=base_revision,
                        projection=_projection("2025年度", "1234.50"),
                        adapter=_JsonCarrierAdapter(),
                    )
                    authorized = await coordinator.authorize(request)
                    base = dict(descriptor_payload or {})
                    echoed = {
                        "participant_id": str(participant_id_ok),
                        "generation": base["generation"],
                        "doc_key": base["doc_key"],
                        "representation_id": base["representation_id"],
                        "artifact_sha256": base["artifact_sha256"],
                        "content_revision": base["server_applied_revision"],
                        "write_fence_epoch": base["write_fence_epoch"],
                        "authority_model_definition_sha256": base[
                            "authority_model_definition_sha256"
                        ],
                        "definition_bundle_id": base["definition_bundle_id"],
                        "definition_bundle_sha256": base["definition_bundle_sha256"],
                    }
                    if case == "generation":
                        echoed["generation"] = int(echoed["generation"]) + 1
                    elif case == "doc_key":
                        echoed["doc_key"] = "wpsync-forged-g1"
                    elif case == "artifact_sha256":
                        echoed["artifact_sha256"] = _d("forged-artifact")
                    elif case == "write_fence_epoch":
                        echoed["write_fence_epoch"] = int(echoed["write_fence_epoch"]) + 7
                    elif case == "definition_bundle_sha256":
                        echoed["definition_bundle_sha256"] = _d("forged-bundle")
                    elif case == "authority_model_definition_sha256":
                        echoed["authority_model_definition_sha256"] = _d("forged-authority")
                    elif case == "content_revision":
                        echoed["content_revision"] = int(echoed["content_revision"]) + 3
                    elif case == "participant_id":
                        echoed["participant_id"] = str(uuid.uuid4())
                    refusal = None
                    try:
                        await coordinator.confirm_descriptor(
                            authorized,
                            room_id=room_id_ok,
                            participant_id=participant_id_ok,
                            echoed=echoed,
                            idempotency_key=f"confirm-tamper-{case}",
                        )
                    except Exception as exc:  # noqa: BLE001
                        refusal = exc
                snap["tamper"][case] = {
                    "refusal": None if refusal is None else type(refusal).__name__,
                    "status": (
                        None if refusal is None
                        else MC.classify_materialize_rejection(refusal)
                    ),
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed(f"tamper_{case}", exc)

        # ═══ 阶段 8：P10 —— 三条幂等/非幂等路径 ═════════════════════════════
        try:
            # 8a. 同 token 重放
            async with Session() as s:
                coordinator = _coordinator(s)
                request = _request(
                    token=ok_token, key=ok_key, revision=base_revision,
                    projection=_projection("2025年度", "1234.50"),
                    adapter=_JsonCarrierAdapter(),
                )
                authorized = await coordinator.authorize(request)
                before = await _pointers()
                replay_outcome = await coordinator.materialize(authorized)
                commits_after_replay = coordinator.commits_invoked
            after = await _pointers()
            snap["idempotency"]["token_replay"] = {
                "replayed": replay_outcome.replayed,
                "commit_count": replay_outcome.commit_count,
                "revision_delta": after["revision"] - before["revision"],
                "same_operation": (
                    str(replay_outcome.operation_id)
                    == snap["commit"].get("descriptor", {}).get("operation_id")
                    or str(replay_outcome.operation_id)
                    == (snap["descriptor"] or {}).get("operation_id")
                ),
                "operation_id": str(replay_outcome.operation_id),
                "content_version_id": str(replay_outcome.content_version_id),
                "representation_id": str(replay_outcome.representation_id),
                "rooms_opened": replay_outcome.rooms_opened,
                "commits_invoked": commits_after_replay,
            }

            # 8b. 不同 token、**相同**业务身份 ⇒ 复用（AC 3.6）
            reuse_key = "idem-reuse"
            reuse_projection = _projection("2025年度", "1234.50")
            reuse_flush = await _flush(reuse_key, reuse_projection, revision_after_ok)
            before = await _pointers()
            async with Session() as s:
                coordinator = _coordinator(s)
                request = _request(
                    token=reuse_flush["token"], key=reuse_key,
                    revision=revision_after_ok, projection=reuse_projection,
                    adapter=_JsonCarrierAdapter(),
                )
                authorized = await coordinator.authorize(request)
                reuse_outcome = await coordinator.materialize(authorized)
            after = await _pointers()
            snap["idempotency"]["business_identity_reuse"] = {
                "business_identity_reused": reuse_outcome.business_identity_reused,
                "commit_count": reuse_outcome.commit_count,
                "revision_delta": after["revision"] - before["revision"],
                "content_version_id": str(reuse_outcome.content_version_id),
                "representation_id": str(reuse_outcome.representation_id),
                "matches_committed_version": (
                    str(reuse_outcome.content_version_id)
                    == (snap["descriptor"] or {}).get("content_version_id")
                ),
                "rooms_opened": reuse_outcome.rooms_opened,
                "descriptor_present": reuse_outcome.descriptor is not None,
            }

            # 8c. 不同 token、**不同**业务内容 ⇒ 必须新 revision（反向自检）
            new_key = "idem-new-content"
            new_projection = _projection("2025年度", "8888.00")
            new_flush = await _flush(new_key, new_projection, revision_after_ok)
            before = await _pointers()
            async with Session() as s:
                coordinator = _coordinator(s)
                request = _request(
                    token=new_flush["token"], key=new_key,
                    revision=revision_after_ok, projection=new_projection,
                    adapter=_JsonCarrierAdapter(),
                )
                authorized = await coordinator.authorize(request)
                new_outcome = await coordinator.materialize(authorized)
            after = await _pointers()
            snap["idempotency"]["new_content"] = {
                "business_identity_reused": new_outcome.business_identity_reused,
                "replayed": new_outcome.replayed,
                "commit_count": new_outcome.commit_count,
                "revision_delta": after["revision"] - before["revision"],
                "revision": new_outcome.revision,
                "transaction_ids": list(new_outcome.transaction_ids),
                "content_version_id": str(new_outcome.content_version_id),
                "differs_from_previous": (
                    str(new_outcome.content_version_id)
                    != (snap["descriptor"] or {}).get("content_version_id")
                ),
            }
            # 8d. 世界已经前进之后再拿老 token 重放 ⇒ 不得下发陈旧 descriptor
            before = await _pointers()
            async with Session() as s:
                coordinator = _coordinator(s)
                request = _request(
                    token=ok_token, key=ok_key, revision=base_revision,
                    projection=_projection("2025年度", "1234.50"),
                    adapter=_JsonCarrierAdapter(),
                )
                authorized = await coordinator.authorize(request)
                stale_replay = None
                try:
                    await coordinator.materialize(authorized)
                except Exception as exc:  # noqa: BLE001
                    stale_replay = exc
                stale_replay_descriptors = coordinator.descriptors_issued
            after = await _pointers()
            snap["idempotency"]["stale_replay"] = {
                "refusal": (
                    None if stale_replay is None else type(stale_replay).__name__
                ),
                "status": (
                    None if stale_replay is None
                    else MC.classify_materialize_rejection(stale_replay)
                ),
                "descriptors_issued": stale_replay_descriptors,
                "revision_delta": after["revision"] - before["revision"],
                "rooms_delta": after["rooms"] - before["rooms"],
                # 🔴 记下**哪一条**判据在起作用：两个 raise 点共用一个异常类型，
                #    只断言类型时它们互相遮蔽（本任务实测 GREEN 过一次）。
                "marker": "" if stale_replay is None else str(stale_replay)[:40],
            }
            revision_latest = after["revision"]
        except Exception as exc:  # noqa: BLE001
            _phase_failed("idempotency", exc)
            revision_latest = revision_after_ok

        # ═══ 阶段 9：撤权重放不得泄露 cached descriptor ══════════════════════
        try:
            async with Session() as s:
                coordinator = _coordinator(s)
                request = _request(
                    token=ok_token, key=ok_key, revision=base_revision,
                    projection=_projection("2025年度", "1234.50"),
                    adapter=_JsonCarrierAdapter(),
                )
                refusal = None
                try:
                    await coordinator.authorize(request, authorize=lambda _r: False)
                except Exception as exc:  # noqa: BLE001
                    refusal = exc
                descriptors = coordinator.descriptors_issued
            # 跨 project 声明同一 token ⇒ token↔request 比对在**读库之前**拦下
            async with Session() as s:
                coordinator = _coordinator(s)
                foreign = _request(
                    token=ok_token, key=ok_key, revision=base_revision,
                    projection=_projection("2025年度", "1234.50"),
                    adapter=_JsonCarrierAdapter(), project_id=uuid.uuid4(),
                )
                cross = None
                try:
                    await coordinator.authorize(foreign)
                except Exception as exc:  # noqa: BLE001
                    cross = exc
            # 合法签名 + 同 scope，但 pending mutation id 在 scope index 里不存在
            # ⇒ 走到 scope-index 查询并返回统一 404 语义。
            async with Session() as s:
                coordinator = _coordinator(s)
                codec = MC.PendingMutationTokenCodec(SECRET)
                ghost_projection = _projection("2025年度", "1234.50")
                ghost_digest = hashlib.sha256(
                    MC._canonical_projection_bytes(ghost_projection)
                ).hexdigest()
                ghost_token = codec.encode(
                    MC.PendingMutationTokenPayload(
                        schema_version=MC.TOKEN_SCHEMA_VERSION,
                        pending_mutation_id=uuid.uuid4(),
                        project_id=project, wp_id=wp, entry_id=ENTRY,
                        sheet_key="d2-receivables", user_id=user,
                        expected_revision=base_revision,
                        payload_sha256=ghost_digest,
                        idempotency_key="idem-ghost",
                        expires_at=_now() + timedelta(minutes=5),
                    )
                )
                ghost = None
                try:
                    await coordinator.authorize(
                        _request(
                            token=ghost_token, key="idem-ghost", revision=base_revision,
                            projection=ghost_projection,
                            adapter=_JsonCarrierAdapter(),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    ghost = exc
            snap["authorization"] = {
                "unknown_resource_refusal": (
                    None if ghost is None else type(ghost).__name__
                ),
                "unknown_resource_status": (
                    None if ghost is None else MC.classify_materialize_rejection(ghost)
                ),
                "revoked_refusal": None if refusal is None else type(refusal).__name__,
                "revoked_status": (
                    None if refusal is None
                    else MC.classify_materialize_rejection(refusal)
                ),
                "descriptors_issued_after_revoked_replay": descriptors,
                "cross_scope_refusal": None if cross is None else type(cross).__name__,
                "cross_scope_status": (
                    None if cross is None else MC.classify_materialize_rejection(cross)
                ),
                "scope_shape": list(MC.assert_authorization_first_shape()),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("authorization", exc)

        # ═══ 阶段 10：P67 —— candidate 阻断 + finalize 不动 revision ═════════
        try:
            async with Session() as s:
                current_rep_id = (
                    await s.execute(
                        sa.text(
                            "SELECT current_representation_id FROM "
                            "working_paper_sync_entry_state WHERE wp_id = :w "
                            "AND entry_id = :e"
                        ),
                        {"w": wp, "e": ENTRY},
                    )
                ).scalar_one()
                current_cv_id = (
                    await s.execute(
                        sa.text(
                            "SELECT content_version_id FROM "
                            "working_paper_content_representation WHERE id = :r"
                        ),
                        {"r": current_rep_id},
                    )
                ).scalar_one()
            staged_candidate = artifacts.stage_upgrade_candidate(
                staged=artifacts.stage_bytes(
                    project_id=project,
                    wp_id=wp,
                    payload=_ooxml(extra={"xl/instrumented.xml": b"<gt-sync/>"}),
                    document_type="xlsx",
                ),
                entry_id=ENTRY,
                equivalence_report=json.dumps({"equivalent": True}).encode(),
            )
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                cand_artifact = await repo.register_artifact(
                    project_id=project, wp_id=wp, kind=ArtifactKind.upgrade_candidate,
                    state=ArtifactState.candidate,
                    relative_path=staged_candidate.relative_path,
                    sha256=staged_candidate.sha256,
                    size_bytes=staged_candidate.size_bytes, document_type="xlsx",
                    retention_class="candidate",
                )
                candidate = await repo.create_upgrade_candidate(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    # 🔴 绑**当前** content version：finalize 只为既有 version 加 generation
                    content_version_id=current_cv_id,
                    source_representation_id=current_rep_id,
                    staged_artifact_id=cand_artifact.id,
                    staged_artifact_sha256=cand_artifact.sha256,
                    template_definition_id=world["tpl"],
                    instrumentation_definition_id=world["instr"],
                    state=CandidateState.awaiting_contract,
                )
                candidate_id = candidate.id
                await s.commit()

            cand_key = "idem-candidate"
            cand_projection = _projection("2025年度", "7777.00")
            cand_flush = await _flush(cand_key, cand_projection, revision_latest)
            before = await _pointers()
            async with Session() as s:
                coordinator = _coordinator(s)
                request = _request(
                    token=cand_flush["token"], key=cand_key,
                    revision=revision_latest, projection=cand_projection,
                    adapter=_JsonCarrierAdapter(),
                )
                authorized = await coordinator.authorize(request)
                refusal = None
                try:
                    await coordinator.materialize(authorized)
                except Exception as exc:  # noqa: BLE001
                    refusal = exc
                descriptors = coordinator.descriptors_issued
            after = await _pointers()
            snap["candidate"]["blocks_materialize"] = {
                "refusal": None if refusal is None else type(refusal).__name__,
                "status": (
                    None if refusal is None
                    else MC.classify_materialize_rejection(refusal)
                ),
                "descriptors_issued": descriptors,
                "rooms_delta": after["rooms"] - before["rooms"],
                "revision_delta": after["revision"] - before["revision"],
                "pointer_unchanged": (
                    before["current_representation_id"]
                    == after["current_representation_id"]
                ),
            }

            # 补齐 approved contract + bundle + 等值报告后才允许 finalize
            # （Requirement 6.18 的 `template → instrumentation → contract → bundle
            #  → representation` 偏序，判据在 Task 12 的 assert_candidate_finalizable）。
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "UPDATE working_paper_representation_upgrade_candidate SET "
                        "target_contract_definition_id = :c, "
                        "target_definition_bundle_id = :b, "
                        "visible_equivalence_report_sha256 = :e, state = 'ready' "
                        "WHERE id = :i"
                    ),
                    {
                        "c": world["contract_def"], "b": world["bundle"],
                        "e": _d("task25-equivalence"), "i": candidate_id,
                    },
                )
                await s.commit()

            before = await _pointers()
            async with Session() as s:
                coordinator = _coordinator(s)
                finalize = await coordinator.finalize_definition_upgrade(
                    project_id=project,
                    candidate_id=candidate_id,
                    staged_candidate=staged_candidate,
                    adapter_id=ENTRY,
                    adapter_build_digest=adapter_digest,
                    structure_hash=_d("task25-structure-upgraded"),
                    identity_inventory_sha256=_d("task25-identity-upgraded"),
                    document_type="xlsx",
                )
            after = await _pointers()
            snap["candidate"]["finalize"] = {
                "revision_unchanged": finalize.revision_unchanged,
                "revision_before": before["revision"],
                "revision_after": after["revision"],
                "revision_delta": after["revision"] - before["revision"],
                "generation_before": before["current_generation"],
                "generation_after": after["current_generation"],
                "entry_pointer_moved": finalize.entry_pointer_moved,
                "representation_generation": finalize.representation_generation,
                "content_version_id": str(finalize.content_version_id),
                "same_content_version": (
                    str(finalize.content_version_id) == str(current_cv_id)
                ),
            }
            async with Session() as s:
                cand_state = (
                    await s.execute(
                        sa.text(
                            "SELECT state FROM "
                            "working_paper_representation_upgrade_candidate WHERE id = :c"
                        ),
                        {"c": candidate_id},
                    )
                ).scalar_one()
            snap["candidate"]["finalize"]["candidate_state"] = str(cand_state)
            snap["candidate"]["finalize"]["expected_state"] = CandidateState.finalized.value

            # finalize 之后同一个 content version 上有**两个** generation。此时再 flush
            # 一份与当前 content version 完全相同的 projection：AC 3.6 的复用必须命中
            # **current pointer 指向的那一代**（gen 2），而不是任意一代。
            async with Session() as s:
                current_projection_sha = (
                    await s.execute(
                        sa.text(
                            "SELECT projection_sha256 FROM working_paper_content_version "
                            "WHERE id = :c"
                        ),
                        {"c": current_cv_id},
                    )
                ).scalar_one()
                current_pointer = (
                    await s.execute(
                        sa.text(
                            "SELECT current_representation_id FROM "
                            "working_paper_sync_entry_state WHERE wp_id = :w "
                            "AND entry_id = :e"
                        ),
                        {"w": wp, "e": ENTRY},
                    )
                ).scalar_one()
            # 找出该 digest 对应的 projection（本采集里所有 projection 都由 `_projection`
            # 生成，逐个试出与当前 content version 同 digest 的那一份）。
            multi_projection = None
            for amount in ("1234.50", "8888.00", "555.00", "6543.21", "9999.00"):
                candidate_projection = _projection("2025年度", amount)
                if (
                    hashlib.sha256(
                        MC._canonical_projection_bytes(candidate_projection)
                    ).hexdigest()
                    == str(current_projection_sha)
                ):
                    multi_projection = candidate_projection
                    break
            if multi_projection is None:
                raise _HarnessError(
                    "找不到与当前 content version 同 digest 的 projection —— "
                    "多代际复用场景无法构造"
                )
            multi_key = "idem-multi-generation-reuse"
            multi_flush = await _flush(multi_key, multi_projection, revision_latest)
            before = await _pointers()
            async with Session() as s:
                coordinator = _coordinator(s)
                multi_outcome = await coordinator.materialize(
                    await coordinator.authorize(
                        _request(
                            token=multi_flush["token"], key=multi_key,
                            revision=revision_latest, projection=multi_projection,
                            adapter=_JsonCarrierAdapter(),
                        )
                    )
                )
            after = await _pointers()
            snap["candidate"]["multi_generation_reuse"] = {
                "business_identity_reused": multi_outcome.business_identity_reused,
                "revision_delta": after["revision"] - before["revision"],
                "representation_id": str(multi_outcome.representation_id),
                "current_pointer": str(current_pointer),
                "representation_generation": multi_outcome.representation_generation,
                "descriptor_generation": (
                    None if multi_outcome.descriptor is None
                    else multi_outcome.descriptor.representation_generation
                ),
            }
            revision_latest = after["revision"]
        except Exception as exc:  # noqa: BLE001
            _phase_failed("candidate", exc)

        # ═══ 阶段 11：全量 operation 形态自证 ═══════════════════════════════
        try:
            async with Session() as s:
                rows = (
                    (
                        await s.execute(
                            sa.select(
                                WorkpaperSyncOperation.id,
                                WorkpaperSyncOperation.direction,
                                WorkpaperSyncOperation.state,
                                WorkpaperSyncOperation.application_id,
                                WorkpaperSyncOperation.duplicate_of_operation_id,
                                WorkpaperSyncOperation.forcesave_request_id,
                                WorkpaperSyncOperation.definition_bundle_sha256,
                            ).where(WorkpaperSyncOperation.wp_id == wp)
                        )
                    )
                    .all()
                )
                event_counts = dict(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT operation_id::text, count(*) FROM "
                                "working_paper_sync_operation_event GROUP BY 1"
                            )
                        )
                    ).all()
                )
            snap["operations"] = {
                "total": len(rows),
                "directions": sorted({str(r[1]) for r in rows}),
                "states": sorted({str(r[2]) for r in rows}),
                "with_application": [str(r[0]) for r in rows if r[3] is not None],
                "with_duplicate_pointer": [str(r[0]) for r in rows if r[4] is not None],
                "with_forcesave_request": [str(r[0]) for r in rows if r[5] is not None],
                "bundle_digests": sorted({str(r[6]) for r in rows}),
                "operations_without_events": [
                    str(r[0]) for r in rows if not event_counts.get(str(r[0]))
                ],
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("operations", exc)

        # ═══ 阶段 12：room write fence 提升后旧 lease 不得再拿 descriptor ══════
        #
        # 🔴 必须是**最后**一个 room 相关阶段：V151 的 `ck_wpoor_monotonic_fence` 只允许
        # fence 单调提升，提上去之后**无法**还原，而它一提升，之后任何走到 room/lease 的
        # materialize 都会被拒。前面所有需要「fence 未变」的场景都已跑完。
        try:
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "UPDATE working_paper_oo_room SET write_fence_epoch = "
                        "write_fence_epoch + 1 WHERE id = :r"
                    ),
                    {"r": room_id_ok},
                )
                await s.commit()
            # 用**新内容**再走一次完整 materialize：这样才会走到 room/lease 那一步
            # （token 重放会先在 substrate 陈旧判据上被拦下，测不到 lease fence）。
            stale_key = "idem-stale-fence"
            stale_projection = _projection("2025年度", "4321.00")
            stale_flush = await _flush(stale_key, stale_projection, revision_latest)
            stale_before = await _pointers()
            stale_ops_before = await _operation_ids()
            async with Session() as s:
                coordinator = _coordinator(s)
                stale = None
                try:
                    await coordinator.materialize(
                        await coordinator.authorize(
                            _request(
                                token=stale_flush["token"], key=stale_key,
                                revision=revision_latest, projection=stale_projection,
                                adapter=_JsonCarrierAdapter(),
                            )
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    stale = exc
                stale_descriptors = coordinator.descriptors_issued
            stale_after = await _pointers()
            stale_new_ops = sorted(await _operation_ids() - stale_ops_before)
            stale_op_state = None
            if len(stale_new_ops) == 1:
                async with Session() as s:
                    stale_op_state = (
                        await s.execute(
                            sa.text(
                                "SELECT state FROM working_paper_sync_operation "
                                "WHERE id = :o"
                            ),
                            {"o": uuid.UUID(stale_new_ops[0])},
                        )
                    ).scalar_one()
            snap["stale_fence"] = {
                "refusal": None if stale is None else type(stale).__name__,
                "status": (
                    None if stale is None else MC.classify_materialize_rejection(stale)
                ),
                "descriptors_issued": stale_descriptors,
                "rooms_delta": stale_after["rooms"] - stale_before["rooms"],
                "new_operations": len(stale_new_ops),
                "operation_state": (
                    None if stale_op_state is None else str(stale_op_state)
                ),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("stale_fence", exc)

    except Exception as exc:  # noqa: BLE001 - 采集顶层也不穿透
        _phase_failed("bootstrap", exc)
    finally:
        bus._redis_available = previous_redis_flag
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except Exception as exc:  # noqa: BLE001
            snap["harness_errors"]["drop_schema"] = _err(exc)
        await admin.dispose()
        shutil.rmtree(base_root, ignore_errors=True)
    return snap


# ═══════════════════════════════════════════════════════════════════════════
# 守卫
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


def test_real_postgres_and_v151_applied(snap: dict[str, Any]) -> None:
    assert "PostgreSQL" in str(snap["server_version"])
    assert snap["apply_errors"] == [], snap["apply_errors"][:3]


def test_no_phase_crashed_during_collection(snap: dict[str, Any]) -> None:
    """采集阶段零异常。

    这条是「采集失败不穿透」这个决定的另一半：穿透会把 module 变成 collection ERROR，
    而 `-rf` 只列 FAILED ⇒ 定向变异看不到预期失败项 ⇒ 误判 GREEN。
    """
    assert snap["harness_errors"] == {}, snap["harness_errors"]


def test_every_scenario_produced_a_measurement(snap: dict[str, Any]) -> None:
    """场景清册齐全 —— 少一个场景意味着某条判据静默消失。"""
    assert set(snap["blocked"]) == {"missing_token", "tampered_token", "foreign_secret"}
    assert set(snap["preflight"]) == set(_PREFLIGHT_CASES)
    assert set(snap["injection"]) == set(_INJECTION_CASES)
    assert set(snap["tamper"]) == set(_TAMPER_CASES)
    assert set(snap["idempotency"]) == {
        "token_replay", "business_identity_reuse", "new_content", "stale_replay"
    }
    assert snap["commit"] and snap["descriptor"] and snap["confirm"]
    assert snap["stale_fence"]
    assert set(snap["candidate"]) == {
        "blocks_materialize", "finalize", "multi_generation_reuse"
    }


# ─────────────────────────────────────────────────────────────────────────
# flush（Requirement 3.1）
# ─────────────────────────────────────────────────────────────────────────


def test_flush_does_not_advance_business_revision(snap: dict[str, Any]) -> None:
    """flush 只创建 pending mutation —— revision、room、operation 全部零变化。"""
    flush = snap["flush"]
    assert flush["revision_before"] == flush["revision_after"], (
        "flush 推进了 business content revision —— Requirement 3.1 规定它只创建 "
        "pending mutation；revision 只由 ContentMutationService.commit(...) 推进"
    )
    assert flush["rooms_after"] == 0, "flush 不得开 room"
    assert flush["operations_after"] == 0, "flush 不得建 operation"


def test_flush_is_idempotent_on_the_same_key_and_payload(snap: dict[str, Any]) -> None:
    """同 key + 同 payload ⇒ 同一个 pending mutation，库里只有一行。"""
    flush = snap["flush"]
    assert flush["first_replay_flag"] is False
    assert flush["replay_flag"] is True
    assert flush["first_pending_id"] == flush["replay_pending_id"]
    assert flush["pending_rows"] == 1, (
        f"同 Idempotency-Key 重复 flush 造出了 {flush['pending_rows']} 行 pending mutation"
    )
    assert flush["scope_rows"] == 1, "pending mutation 必须有且仅有一条 scope index 行"


def test_flush_receipt_exposes_exactly_the_four_documented_fields(
    snap: dict[str, Any],
) -> None:
    """响应体恰为 design §API 的四项 —— 多一项会诱使前端把 flush 当成提交。"""
    assert snap["flush"]["receipt_keys"] == sorted(
        ["pending_mutation_token", "expected_revision", "payload_sha256", "expires_at"]
    )


@pytest.mark.parametrize(
    "case,expected",
    [
        ("same_key_other_payload", "PendingTokenPayloadError"),
        ("same_key_other_revision", "PendingTokenRevisionError"),
    ],
    ids=["other_payload", "other_revision"],
)
def test_same_key_different_input_is_refused_with_its_own_type(
    snap: dict[str, Any], case: str, expected: str
) -> None:
    """同 key 不同 payload / 不同 expected revision ⇒ 两个**不同**的拒绝类型。"""
    assert snap["flush"][case] == expected


# ─────────────────────────────────────────────────────────────────────────
# Property 8：flush 失败 ⇒ 零 room、零 operation、零 descriptor
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "case,expected",
    [
        ("missing_token", "PendingTokenRequiredError"),
        ("tampered_token", "PendingTokenSignatureError"),
        ("foreign_secret", "PendingTokenSignatureError"),
    ],
    ids=["missing_token", "tampered_token", "foreign_secret"],
)
def test_no_valid_token_means_zero_room_zero_operation_zero_descriptor(
    snap: dict[str, Any], case: str, expected: str
) -> None:
    """P8 的三个计数都必须是 0，且拒绝类型正是预期那一个。

    「没有合法 token」是 Requirement 3.2「HTML flush 未得到服务端成功响应」的服务端
    对应事实。三个计数分别数库里的 room 行、operation 行与本次发出的 descriptor 数 ——
    都不是本模块的自述。
    """
    row = snap["blocked"][case]
    assert row["refusal"] == expected, row
    assert row["descriptors_issued"] == 0, "零挂载：一个 descriptor 都不许发出"
    assert row["commits_invoked"] == 0, "零业务 commit"
    assert row["rooms_after"] == row["rooms_before"] == 0, "零 room"
    assert row["operations_after"] == row["operations_before"], "零新增 operation"
    assert row["revision_after"] == row["revision_before"], "零 revision 变化"


def test_missing_token_and_tampered_token_are_different_refusals(
    snap: dict[str, Any],
) -> None:
    """「压根没 flush」与「token 被篡改」必须可分辨。

    共用一个类型时，把空 token 分支删掉会被 signature 分支接住 ⇒ P8 的判据变成
    不可达分支，它的定向变异永久 GREEN。
    """
    assert (
        snap["blocked"]["missing_token"]["error_code"]
        != snap["blocked"]["tampered_token"]["error_code"]
    )


# ─────────────────────────────────────────────────────────────────────────
# Requirement 3.3：422 preflight 家族 ⇒ 零 operation、零 room
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "case,expected",
    [
        ("substrate_not_published", "SubstrateNotPublishedError"),
        ("missing_contract", "PerEntryContractMissingError"),
        ("capability_single_html", "EntryNotMaterializableError"),
    ],
    ids=list(_PREFLIGHT_CASES),
)
def test_preflight_rejections_are_422_with_zero_room_and_zero_operation(
    snap: dict[str, Any], case: str, expected: str
) -> None:
    """三条**独立来源**的 422，各自零 room、零 operation、零 revision、零 descriptor。

    「零 operation」是本任务对 Requirement 3.8 的诚实边界：
    `working_paper_sync_operation.definition_bundle_id` 是 NOT NULL，而这一类失败的
    定义就是「没有一个合法 bundle 可冻结」⇒ 它们**不可能**有 operation。
    """
    row = snap["preflight"][case]
    assert row["refusal"] == expected, row
    assert row["status"] == 422, row
    assert row["is_preflight_group"] is True, (
        "422 家族必须都是 MaterializePreflightError 的子类，否则 router 的 "
        "`except MaterializePreflightError` 会漏掉它"
    )
    assert row["descriptors_issued"] == 0
    assert row["rooms_delta"] == 0
    assert row["operations_delta"] == 0
    assert row["revision_delta"] == 0


def test_preflight_rejections_have_three_distinct_error_codes(
    snap: dict[str, Any],
) -> None:
    """三条来源的 error_code 两两不同 —— 用户要做的事不同（发 contract vs 批准 bundle
    vs 改裁决），共用 code 前端只能给一句废话。"""
    codes = [snap["preflight"][case]["error_code"] for case in _PREFLIGHT_CASES]
    assert len(set(codes)) == 3, codes


# ─────────────────────────────────────────────────────────────────────────
# Property 9：两个注入点各自保持三个指针不变 + operation 落 error
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", list(_INJECTION_CASES), ids=list(_INJECTION_CASES))
def test_injected_verification_failure_leaves_all_three_pointers_intact(
    snap: dict[str, Any], case: str
) -> None:
    """P9：注入失败后 revision / current pointer / artifact hash 三者全不变。"""
    row = snap["injection"][case]
    assert row["refusal"] == row["expected_refusal"], row
    assert row["new_operation_count"] == 1, (
        f"本次注入新建了 {row['new_operation_count']} 个 operation —— 必须恰一个"
    )
    assert row["revision_unchanged"] is True, "current revision 变了"
    assert row["pointer_unchanged"] is True, "entry current representation pointer 变了"
    assert row["artifact_sha_unchanged"] is True, "current artifact hash 变了"
    assert row["rooms_delta"] == 0, "校验失败仍开了 room"
    assert row["descriptors_issued"] == 0, "校验失败仍发出了 descriptor"


@pytest.mark.parametrize("case", list(_INJECTION_CASES), ids=list(_INJECTION_CASES))
def test_the_injected_validation_path_actually_executed(
    snap: dict[str, Any], case: str
) -> None:
    """判别性：被注入的那道校验必须**真的跑过**。

    🔴 Task 23 的第一版竞态就是「断言全过而目标分支一次都没执行」。这里逐条数 adapter
    的真实调用次数：`roundtrip_drop_key` 必须走完 materialize + extract（否则不等值判据
    没被触发过）；`unmanaged_drift` 还必须走到 `verify_unmanaged_regions`。
    """
    row = snap["injection"][case]
    assert row["materialize_calls"] == 1, row
    assert row["extract_calls"] == 1, row
    if case == "unmanaged_drift":
        assert row["unmanaged_calls"] == 1, (
            "未管理区域比对一次都没执行 —— 这条注入没有触达它要测的校验点"
        )
    else:
        assert row["unmanaged_calls"] == 0, (
            "roundtrip 不等值必须在未管理区域比对**之前**失败（顺序即判据）"
        )


@pytest.mark.parametrize("case", list(_INJECTION_CASES), ids=list(_INJECTION_CASES))
def test_failed_materialize_leaves_a_terminal_operation_with_events(
    snap: dict[str, Any], case: str
) -> None:
    """Requirement 3.8：任一失败都留下终态明确的 operation 与 transition events。

    不得「warning 后继续打开旧文件」—— 所以 operation 必须是 `error` 而不是停在
    `created`，且 `room_id` 保持空（room 从未创建）。
    """
    row = snap["injection"][case]
    assert row["operation_state"] == "error", row
    assert row["operation_error_code"], "error 终态必须带 error_code"
    assert row["operation_room_id"] is None, "失败的 materialize 不得绑定 room"
    assert row["operation_events"][:1] == ["created"], row["operation_events"]
    assert row["operation_events"][-1] == "error", row["operation_events"]


# ─────────────────────────────────────────────────────────────────────────
# Property 10：单次业务 commit + 三条幂等/非幂等路径
# ─────────────────────────────────────────────────────────────────────────


def test_happy_path_commits_exactly_once_in_exactly_one_transaction(
    snap: dict[str, Any],
) -> None:
    """P10 / Requirement 3.1：一次 materialize = 一次 commit、一个事务、一次 revision。"""
    row = snap["commit"]
    assert row["commit_count"] == 1, row
    assert len(row["transaction_ids"]) == 1, (
        f"业务写入落在 {len(row['transaction_ids'])} 个数据库事务里 —— projection 与"
        "兼容 representation 必须同生共死"
    )
    assert row["revision_delta"] == 1, row
    assert row["revision_after"] == row["revision_before"] + 1
    assert row["commits_invoked"] == 1, "ContentMutationService.commit 只许被调一次"
    assert row["pointer_moved"] is True, "成功 commit 必须把 entry pointer 切到新代际"
    assert row["current_representation_id"] == row["descriptor_representation_id"], (
        "descriptor 指向的 representation 必须正是 entry 的 current pointer"
    )
    assert row["rooms_opened"] == 1, "成功 commit 之后恰开一个 room"
    assert row["pending_state"] == "committed", "pending mutation 必须被单次消费"


def test_happy_path_ran_the_full_materialize_chain(snap: dict[str, Any]) -> None:
    """判别性：materialize / extract / 未管理区域比对三步都真跑过。

    否则「三步缺一不可」这条承诺可以在一个跳过后两步的实现下全绿。
    """
    row = snap["commit"]
    assert (row["materialize_calls"], row["extract_calls"], row["unmanaged_calls"]) == (
        1, 1, 1,
    ), row


def test_flush_digest_equals_the_committed_projection_digest(
    snap: dict[str, Any],
) -> None:
    """AC 3.6 幂等复用的前提：flush 算的 digest == commit 落盘的 projection digest。

    🔴 这一条是「两套 canonicalizer 漂移」的唯一真实判据。不等时幂等复用永远命中不了，
    而那在只测 token 重放的守卫下**全绿**。
    """
    assert snap["commit"]["flush_payload_sha256"] == snap["commit"]["projection_sha256"]


def test_html_to_oo_operation_never_binds_an_application(snap: dict[str, Any]) -> None:
    """Property 64：HTML→OO 方向没有 incoming artifact ⇒ 永不产生 content application。"""
    row = snap["commit"]
    assert row["operation_direction"] == "html_to_oo"
    assert row["operation_state"] == "applied"
    assert row["operation_application_id"] is None
    assert row["operation_duplicate_of"] is None
    assert row["operation_room_id"] == (snap["descriptor"] or {}).get("room_id")
    assert row["operation_events"] == ["created", "applied"], row["operation_events"]


def test_token_replay_returns_the_same_result_without_a_second_revision(
    snap: dict[str, Any],
) -> None:
    """P10：同 token 重放返回既有 operation/version/representation，revision 不动。"""
    row = snap["idempotency"]["token_replay"]
    assert row["replayed"] is True
    assert row["commit_count"] == 0
    assert row["revision_delta"] == 0
    assert row["rooms_opened"] == 0, "重放不得开第二个 room（同 generation 复用）"
    assert row["operation_id"] == (snap["descriptor"] or {}).get("operation_id")
    assert row["content_version_id"] == (snap["descriptor"] or {}).get(
        "content_version_id"
    )
    assert row["representation_id"] == (snap["descriptor"] or {}).get(
        "representation_id"
    )


def test_same_business_identity_with_a_new_token_reuses_the_existing_version(
    snap: dict[str, Any],
) -> None:
    """AC 3.6 第一句：projection + bundle + substrate 全同 ⇒ 复用，零 revision。

    这是与 token 重放**不同**的第二条幂等路径：用户 flush 了两次但内容一字未改。
    """
    row = snap["idempotency"]["business_identity_reuse"]
    assert row["business_identity_reused"] is True, row
    assert row["commit_count"] == 0
    assert row["revision_delta"] == 0
    assert row["matches_committed_version"] is True, (
        "复用必须命中**既有**那个 content version，而不是新建一个"
    )
    assert row["descriptor_present"] is True, "复用路径同样要返回可挂载 descriptor"


def test_replay_after_the_world_moved_on_refuses_to_hand_out_a_stale_descriptor(
    snap: dict[str, Any],
) -> None:
    """老 token 在**新** commit 之后重放 ⇒ 409，不得下发陈旧 descriptor。

    Task 25 正文：「仅当前 project/workflow/lease/generation/fence/bundle 仍有效时
    成功重放才返回同 operation/content version/representation」。世界已经前进时，
    pending mutation 记录的 result representation 已被新代际取代 —— 把它照原样挂上去
    会让审计师在 OO 里编辑一份**旧** artifact，随后的 forcesave 基线也全错。

    这条守卫保护的是一个实测缺陷：修复前该路径会把 `RoomPolicyError` 原样漏出去
    （router 会记成 500，前端拿到一个无法操作的错误）。
    """
    from app.services.workpaper_sync.materialize_coordinator import (
        STALE_ON_REPLAY_MARKER,
    )

    row = snap["idempotency"]["stale_replay"]
    assert row["refusal"] == "DescriptorSubstrateStaleError", row
    assert row["status"] == 409, row
    assert row["descriptors_issued"] == 0
    assert row["revision_delta"] == 0
    assert row["rooms_delta"] == 0
    # 🔴 必须是**重放侧**那条判据在起作用：room 打开侧抛的是同一个异常类型，
    #    只断言类型时删掉重放侧判据会被它接住 ⇒ 变异判 GREEN（本任务实测过）。
    assert row["marker"].startswith(STALE_ON_REPLAY_MARKER), row


def test_changed_business_content_still_produces_a_new_revision(
    snap: dict[str, Any],
) -> None:
    """反向自检：内容真变了必须新 revision。

    没有这一条，把幂等复用的判据放宽成「永远复用」也能让上面几条全绿 —— 而那会让
    用户的修改静默丢失。
    """
    row = snap["idempotency"]["new_content"]
    assert row["business_identity_reused"] is False, row
    assert row["replayed"] is False
    assert row["commit_count"] == 1
    assert row["revision_delta"] == 1
    assert len(row["transaction_ids"]) == 1
    assert row["differs_from_previous"] is True


# ─────────────────────────────────────────────────────────────────────────
# Property 11：唯一 descriptor + ready 后服务端确认
# ─────────────────────────────────────────────────────────────────────────


def test_descriptor_carries_every_field_requirement_3_7_names(
    snap: dict[str, Any],
) -> None:
    """descriptor 字段齐全且值非占位（Requirement 3.7）。"""
    from app.services.workpaper_sync import materialize_coordinator as MC

    payload = snap["descriptor"]
    assert payload is not None
    for name in MC.DESCRIPTOR_REQUIRED_FIELDS:
        assert name in payload, f"descriptor 缺 {name}"
    assert payload["onlyoffice_config"], "config 为空会逼组件再请求一次（P11 禁止）"
    assert sorted(payload["definition_bundle_slots"]) == [
        "contract", "instrumentation", "template"
    ]
    for slot, spec in payload["definition_bundle_slots"].items():
        assert spec["type"], slot
        assert len(spec["sha256"]) == 64, slot


def test_room_is_not_active_and_forcesave_is_refused_before_confirmation(
    snap: dict[str, Any],
) -> None:
    """P11 后半：ready 之后仍必须调 confirm-descriptor，确认前不得 forcesave。"""
    assert snap["commit"]["room_state_before_confirm"] == "opening", (
        "materialize 之后 room 必须停在 opening —— 只有 descriptor confirmation 才让它 active"
    )
    row = snap["confirm"]
    assert row["forcesave_before_confirm"] == row["expected_before_confirm"], row


def test_confirmation_unlocks_forcesave_without_touching_revision(
    snap: dict[str, Any],
) -> None:
    """确认成功 ⇒ room `active`、forcesave 放行，且 confirm 本身不递增 revision。"""
    row = snap["confirm"]
    assert row["room_state_after"] == "active"
    assert row["forcesave_unlocked"] is True
    assert row["forcesave_after_confirm"] is None, (
        f"确认之后 forcesave 仍被拒: {row['forcesave_after_confirm']}"
    )
    assert row["revision_unchanged_by_confirm"] is True, (
        "confirm-descriptor 不得递增 content revision（design §API 明文）"
    )


@pytest.mark.parametrize("case", list(_TAMPER_CASES), ids=list(_TAMPER_CASES))
def test_every_tampered_identity_item_is_refused_with_409(
    snap: dict[str, Any], case: str
) -> None:
    """八项 identity 逐项篡改都必须 409。

    逐项而不是「改一项试试」：每一项在服务端都是一条独立比对，只测一项时删掉其余
    七条不会有任何测试变红。
    """
    row = snap["tamper"][case]
    assert row["refusal"] == "DescriptorStaleIdentityError", row
    assert row["status"] == 409, row


# ─────────────────────────────────────────────────────────────────────────
# 授权：撤权重放零泄露
# ─────────────────────────────────────────────────────────────────────────


def test_revoked_replay_yields_403_and_leaks_no_cached_descriptor(
    snap: dict[str, Any],
) -> None:
    """撤权后原 token + 原 Idempotency-Key 重放 ⇒ 403，且一个 descriptor 都不发。"""
    row = snap["authorization"]
    assert row["revoked_refusal"] == "MaterializeAuthorizationError", row
    assert row["revoked_status"] == 403, row
    assert row["descriptors_issued_after_revoked_replay"] == 0, (
        "撤权重放竟然发出了 cached descriptor"
    )


def test_cross_scope_token_is_refused_before_any_database_read(
    snap: dict[str, Any],
) -> None:
    """token 自带 scope 与声明的 route scope 不符 ⇒ 在**读库之前**就 409。

    这条判据存在的理由是「不泄露服务端状态」：token 是客户端自己持有的签名字节，
    拿它和 URL 上的 project/wp/entry 比对不需要碰数据库，也就无从泄露「那个 id 存不存在」。
    真正的 404 语义属于**资源查找**路径，由下一条测试覆盖。
    """
    row = snap["authorization"]
    assert row["cross_scope_refusal"] == "PendingTokenScopeError", row
    assert row["cross_scope_status"] == 409, row


def test_unknown_resource_yields_the_unified_404_envelope(
    snap: dict[str, Any],
) -> None:
    """合法签名 + 同 scope 但资源不在 scope index ⇒ 统一 404，不泄露是否存在。"""
    row = snap["authorization"]
    assert row["unknown_resource_refusal"] == "MaterializeScopeNotVisibleError", row
    assert row["unknown_resource_status"] == 404, row


def test_stale_lease_after_a_fence_bump_cannot_get_a_descriptor(
    snap: dict[str, Any],
) -> None:
    """room write fence 提升后，旧 lease 不得再拿到 descriptor（AC 2.8 / 4.7）。

    fence 提升的含义是「期间有 participant 被撤销或 generation 被旋转」。此时复用
    旧 lease 等于让一个可能已失权的会话继续写 —— 必须在**发 descriptor 之前**就拒。
    """
    row = snap["stale_fence"]
    assert row["refusal"] == "MaterializeAuthorizationError", row
    assert row["status"] == 403, row
    assert row["descriptors_issued"] == 0, "陈旧 lease 竟然拿到了 descriptor"
    assert row["rooms_delta"] == 0, "不得为陈旧 lease 另开一个 room"
    # 业务内容**已经**提交（用户的 HTML 编辑不该因为 OO 会话开不起来而丢失），
    # 但 operation 必须落 `error` 终态、descriptor 一个都不发 ⇒ 前端停留在 HTML。
    assert row["new_operations"] == 1, row
    assert row["operation_state"] == "error", row


def test_authorization_phase_touches_only_the_scope_index(snap: dict[str, Any]) -> None:
    """AST 判据在真库环境下同样成立（源码形态与运行环境无关，但一并记录）。"""
    assert snap["authorization"]["scope_shape"] == ["resolve_scope"]


# ─────────────────────────────────────────────────────────────────────────
# Property 67：candidate 阻断 + finalize 不动 revision
# ─────────────────────────────────────────────────────────────────────────


def test_unfinalized_candidate_blocks_materialize_with_zero_side_effects(
    snap: dict[str, Any],
) -> None:
    """P67：representation 上挂着未 finalize 的 candidate ⇒ 422，零 room、零 revision。"""
    row = snap["candidate"]["blocks_materialize"]
    assert row["refusal"] == "RepresentationStillCandidateError", row
    assert row["status"] == 422, row
    assert row["descriptors_issued"] == 0
    assert row["rooms_delta"] == 0
    assert row["revision_delta"] == 0
    assert row["pointer_unchanged"] is True


def test_finalize_adds_a_generation_without_moving_content_revision(
    snap: dict[str, Any],
) -> None:
    """P67 / AC 3.6 后半：approved bundle 后 finalize ⇒ 新 generation、revision 不变。"""
    row = snap["candidate"]["finalize"]
    assert row["revision_unchanged"] is True, row
    assert row["revision_delta"] == 0, row
    assert row["generation_after"] == row["generation_before"] + 1, (
        "finalize 必须为**同一** content version 新增一个 representation generation"
    )
    assert row["entry_pointer_moved"] is True
    assert row["same_content_version"] is True, (
        "纯定义升级不得新建 content version —— 那就是伪业务 revision"
    )
    assert row["candidate_state"] == row["expected_state"]


def test_reuse_on_a_multi_generation_version_picks_the_current_pointer(
    snap: dict[str, Any],
) -> None:
    """同一 content version 有多代 representation 时，复用必须命中 **current pointer**。

    finalize 之后 cv 上有 gen1（业务提交产生）与 gen2（定义升级产生）两代。此时把
    「相同业务内容」再 flush 一次：AC 3.6 的复用要求返回**现在**那一代 ——
    返回 gen1 会让审计师在 OO 里打开一份未 instrumented 的旧载体，随后 extract 找不到
    identity 载体。

    🔴 这条判据同时是 `_find_business_identity_reuse` 里「substrate identity =
    current representation id」那个 pin 的唯一 falsifier：把 pin 放宽成「同 content
    version 的任一代」时，本测试才会红。
    """
    row = snap["candidate"]["multi_generation_reuse"]
    assert row["business_identity_reused"] is True, row
    assert row["revision_delta"] == 0, row
    assert row["representation_id"] == row["current_pointer"], row
    assert row["representation_generation"] == 2, row
    assert row["descriptor_generation"] == 2, row


# ─────────────────────────────────────────────────────────────────────────
# operation 形态全量自证
# ─────────────────────────────────────────────────────────────────────────


def test_every_html_to_oo_operation_keeps_the_pre_correlation_shape(
    snap: dict[str, Any],
) -> None:
    """本任务产生的 operation 全部是 `html_to_oo`，且永不绑定 application/duplicate/request。

    Property 64 的形态自证：HTML→OO 没有 incoming artifact，也没有 forcesave request；
    任何一条绑上去都说明编排走错了方向。
    """
    row = snap["operations"]
    assert row["total"] >= 4, row
    assert row["directions"] == ["html_to_oo"], row
    assert row["with_application"] == [], row
    assert row["with_duplicate_pointer"] == [], row
    assert row["with_forcesave_request"] == [], row
    assert set(row["states"]) <= {"applied", "error"}, row
    assert row["operations_without_events"] == [], (
        "每个 operation 都必须有 append-only transition event（Requirement 3.8）"
    )


def test_all_operations_froze_the_same_approved_bundle_digest(
    snap: dict[str, Any],
) -> None:
    """operation 冻结的 bundle digest 只能是那一份 approved bundle 的。

    出现第二个 digest 意味着某次编排按**当前 alias** 重组了 bundle
    （AC 2.10 明令禁止）。
    """
    assert len(snap["operations"]["bundle_digests"]) == 1, snap["operations"][
        "bundle_digests"
    ]
