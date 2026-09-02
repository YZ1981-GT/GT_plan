# -*- coding: utf-8 -*-
"""Task 15 真实 PostgreSQL 守卫：单事务原子性、双 revision 形态不可能、candidate
finalize 只增不改、rollback 只留不可见 orphan、pending mutation 幂等与三类拒绝。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 15
Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.6, 6.18, 8.10, 8.12, 13.1
Properties: **P4** / **P5** / **P10** / **P61** / **P65** / **P67**

═══ 为什么必须真库 + 真文件（不可 mock、不可 skip）═══

本任务的核心承诺全是**否定式**的：

* 「content version / revision / representation / entry pointer / outbox 同生共死」
* 「绝不先提交 projection-only version 再补一次 revision」
* 「失败后原 pointer/revision 不变，已 publish 的文件是不可见 orphan」
* 「纯表示 finalize 不推进 business revision、不改旧 row」

mock session 里「事务」根本不存在，回滚是个空操作，于是全部断言空转 —— 这正是
Task 16 docstring 里写过的同一个陷阱。因此：

1. **`xmin` 是独立于本代码的原子性判据**。PostgreSQL 给每个行版本记录写它的事务 id；
   五张表（`working_paper` / content_version / representation / entry_state /
   import_event_outbox）的 `xmin` **全部相等**，才证明它们是同一个事务写的。
   这条判据不依赖 `_TransactionWitness`（那是我们自己的代码），所以「见证逻辑被改坏」
   不会让它假绿。
2. **`after_commit` 事件计数**是第二条独立判据：一次 `commit()` 恰有一次数据库提交。
   注入第二次 `session.commit()` 会同时打破 xmin 相等与提交计数 —— 两条各自可 falsify。
3. **文件真发布**：rollback 后磁盘上的 canonical 文件仍在、但零 DB 行引用它 ⇒
   Requirement 2.4 承诺的「不可见 orphan」是被观测到的事实，而不是文档措辞。

═══ 隔离 ═══

scratch schema `tmp_task15_cm_*`，`search_path` 不含 public；`projects/users/
working_paper` 建桩表，`import_event_outbox` / `import_event_consumptions` 从 ORM
metadata 建（列不手抄，防第二真源）；文件全在系统临时目录。结束
`DROP SCHEMA CASCADE` + 删临时目录。**绝不触碰真实 `storage/`**。

`DATABASE_URL` 非 PostgreSQL 时**直接失败不 skip** —— 静默 skip 会把本任务唯一的判据
删掉，留下一份「全绿」的假象。

═══ 采集写法 ═══

全部场景由**一次 `asyncio.run`** 跑完并落进快照（module fixture）。不给每个测试各自
开 async（共享连接池会被污染，第二个测试起 `NoneType has no attribute send`）。
采集内部任何异常都记进快照的 `errors`，由守卫断言为空 —— **禁 fail-open**。
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
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

_SCHEMA_PREFIX = "tmp_task15_cm_"
ENTRY = "g7.disclosure.listed"
OTHER_WP_ENTRY = "g7.disclosure.soe"

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

#: V065 给 outbox enum 加过 'processing'；守卫不能跑在比生产更窄的类型上。
_EXTRA_ENUM_LABELS = {"import_event_outbox_status": ("processing",)}

#: 必须同事务写入的五张表（`xmin` 全等即证明单事务）。
_ATOMIC_TABLES: tuple[tuple[str, str], ...] = (
    ("working_paper", "revision_bump"),
    ("working_paper_content_version", "content_version"),
    ("working_paper_content_representation", "representation"),
    ("working_paper_sync_entry_state", "entry_pointer"),
    ("import_event_outbox", "outbox"),
)

_CONTENT_TYPES = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="xml" ContentType="application/xml"/></Types>'
)


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ooxml(document_type: str, *, extra: dict[str, bytes] | None = None) -> bytes:
    marker = "xl/workbook.xml" if document_type == "xlsx" else "word/document.xml"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr(marker, b'<?xml version="1.0"?><root/>')
        for name, payload in (extra or {}).items():
            zf.writestr(name, payload)
    return buf.getvalue()


def _enum_ddl(tables: list[sa.Table]) -> list[str]:
    seen: dict[str, tuple[str, ...]] = {}
    for table in tables:
        for column in table.columns:
            if isinstance(column.type, sa.Enum) and column.type.name:
                labels = tuple(column.type.enums) + _EXTRA_ENUM_LABELS.get(
                    column.type.name, ()
                )
                seen.setdefault(column.type.name, labels)
    return [
        "CREATE TYPE {name} AS ENUM ({labels})".format(
            name=name, labels=", ".join(f"'{label}'" for label in labels)
        )
        for name, labels in sorted(seen.items())
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 契约与 adapter 桩（真写真读的载体替身）
# ═══════════════════════════════════════════════════════════════════════════

PERIOD = "header_block/period_label"
TOTAL = "header_block/total_amount"


def _contract_payload() -> dict[str, Any]:
    from app.services.workpaper_sync import contracts as C

    return {
        "schema_version": C.CONTRACT_SCHEMA_VERSION,
        "contract_id": ENTRY,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": _d("task15-pg-template"),
        "instrumentation_definition_sha256": _d("task15-pg-instrumentation"),
        "template": {
            "relative_path": "G/G7 权益工具投资.xlsx",
            "template_sha256": _d("task15-pg-template-blob"),
            "normalized_structure_hash": _d("task15-pg-template-structure"),
        },
        "identity_carriers": ["hidden_sheet", "defined_name"],
        "sheets": [
            {
                "sheet_key": "g7-disclosure",
                "excel_name": "G7 披露表",
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
    """真 OOXML 容器 + JSON 受管部件的载体替身（真 materialize、真 extract）。

    不是 mock：`materialize` 真写 zip、`extract` 真读回来，因此 roundtrip 等值判据
    在真实执行上生效。真正的 Excel/Word 引擎归 Tasks 36~38 / 59~61。
    """

    adapter_id = ENTRY
    document_type = "xlsx"
    contract_version = "1.0.0"

    def __init__(self, *, drop_keys: tuple[str, ...] = ()) -> None:
        self.drop_keys = drop_keys

    async def read_current_projection(self, ctx):  # pragma: no cover
        raise NotImplementedError

    async def stage_projection_mutation(self, ctx, merged, *, expected_revision):  # pragma: no cover
        raise NotImplementedError

    def materialize(self, *, substrate, projection, output, contract):
        from app.services.workpaper_sync.adapters.base import MaterializeResult

        values = {
            key: {
                "value": value.value,
                "value_type": value.value_type.value,
                "mode": value.mode.value,
                "row_key": value.row_key,
            }
            for key, value in projection.values.items()
            if key not in self.drop_keys
        }
        blob = _ooxml(
            projection.document_type,
            extra={
                "_gt_sync/projection.json": json.dumps(
                    {"contract_id": projection.contract_id, "values": values},
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode("utf-8")
            },
        )
        Path(output).write_bytes(blob)
        return MaterializeResult(
            output_path=Path(output),
            document_type=projection.document_type,
            artifact_sha256=hashlib.sha256(blob).hexdigest(),
            structure_hash=_d("task15-structure"),
            identity_inventory_sha256=_d("task15-identity"),
            managed_field_count=len(values),
        )

    def extract(self, *, artifact, contract):
        from app.services.workpaper_sync import contracts as C
        from app.services.workpaper_sync.adapters.base import FieldValue, Projection

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

        return UnmanagedRegionReport(
            equivalent=True, inspected_aspects=("formula", "style", "drawing")
        )


# ═══════════════════════════════════════════════════════════════════════════
# 采集
# ═══════════════════════════════════════════════════════════════════════════


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - 一次采集覆盖全部场景
    from sqlalchemy import event as sa_event
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.audit_platform_schemas import EventType
    from app.models.dataset_models import ImportEventConsumption, ImportEventOutbox
    from app.services import event_bus as event_bus_module
    from app.services.workpaper_sync import content_mutation as CM
    from app.services.workpaper_sync import contracts as C
    from app.services.workpaper_sync import definitions as D
    from app.services.workpaper_sync import representations as R
    from app.services.workpaper_sync.adapters.base import (
        FieldValue,
        Projection,
        SubstrateRole,
    )
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.models import (
        ArtifactKind,
        ArtifactState,
        BundleSlot,
        BundleSlotSpec,
        CandidateState,
        RevisionConflictError,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import (
        CanonicalResolutionService,
        CandidateNotFinalizableError,
        ResolutionIntent,
    )

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 15 的判据是「五张表同事务、rollback 零可见、finalize 不推 revision」，"
            "依赖真实事务语义与 V151 的 trigger；必须真实 PostgreSQL，当前 DATABASE_URL "
            f"为 {settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task15_store_"))
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
        "errors": [],
        "business_commit": {},
        "atomicity": {},
        "outbox": {},
        "rollback": {},
        "double_revision": {},
        "idempotency": {},
        "pending_rejections": {},
        "finalize": {},
        "finalize_gate": {},
        "custom_authoritative": {},
        "resolver_view": {},
    }
    engine = None
    # Redis 不参与判定：置 False 让 _persist_to_stream 立刻返回，避免 xadd 抖动。
    bus = event_bus_module.event_bus
    previous_redis_flag = bus._redis_available
    bus._redis_available = False
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
            for stmt in _enum_ddl(outbox_tables):
                await conn.exec_driver_sql(stmt)
            await conn.run_sync(
                lambda sync_conn: ImportEventOutbox.metadata.create_all(
                    sync_conn, tables=outbox_tables, checkfirst=True
                )
            )

        project, wp, other_wp, user = (
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
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
        adapter = _JsonCarrierAdapter()

        # ── 发布 definitions + approved bundle（projection_contract 与 custom 两套）──
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
                "authority_custom": "authority_model",
                "bundle_payload": "bundle",
                "bundle_custom": "bundle",
                "bundle_unapproved": "bundle",
                "authority_unapproved": "authority_model",
            }.items()
        }
        gen1 = artifacts.publish_representation(
            entry_id=ENTRY,
            generation=1,
            staged=artifacts.stage_bytes(
                project_id=project,
                wp_id=wp,
                payload=_ooxml(
                    "xlsx",
                    extra={
                        "_gt_sync/projection.json": json.dumps(
                            {"contract_id": ENTRY, "values": {}}, sort_keys=True
                        ).encode()
                    },
                ),
                document_type="xlsx",
            ),
        )
        proj0 = artifacts.publish_projection(
            revision=0,
            staged=artifacts.stage_bytes(
                project_id=project,
                wp_id=wp,
                payload=b"projection-v0",
                document_type="json.gz",
            ),
        )

        world: dict[str, Any] = {}
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
            art_gen1 = await repo.register_artifact(
                project_id=project,
                wp_id=wp,
                kind=ArtifactKind.canonical,
                state=ArtifactState.published,
                relative_path=gen1.relative_path,
                sha256=gen1.sha256,
                size_bytes=gen1.size_bytes,
                document_type="xlsx",
            )
            art_proj0 = await repo.register_artifact(
                project_id=project,
                wp_id=wp,
                kind=ArtifactKind.projection,
                state=ArtifactState.published,
                relative_path=proj0.relative_path,
                sha256=proj0.sha256,
                size_bytes=proj0.size_bytes,
                document_type="json.gz",
            )
            tpl = await repo.create_definition_artifact(
                kind="template", logical_id="task15.tpl", semantic_version="1.0.0",
                blob_artifact_id=art["tpl"].id, sha256=_d("task15-pg-template"),
                structure_hash=_d("task15-tpl-structure"), source_commit="task15",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation", logical_id="task15.instr",
                semantic_version="1.0.0", blob_artifact_id=art["instr"].id,
                sha256=_d("task15-pg-instrumentation"),
                structure_hash=_d("task15-instr-structure"), source_commit="task15",
            )
            contract_def = await repo.create_definition_artifact(
                kind="contract", logical_id="task15.contract", semantic_version="1.0.0",
                blob_artifact_id=art["contract"].id,
                # 🔴 契约 definition 的 digest 必须等于 SyncContract 的 canonical digest：
                #    `SyncContext.assert_frozen_identity_consistent` 用它做三向锁死。
                sha256=contract.canonical_sha256, source_commit="task15",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task15.authority",
                semantic_version="1.0.0", blob_artifact_id=art["authority"].id,
                sha256=_d("task15-authority"),
                authority_model_type="projection_contract", source_commit="task15",
            )
            authority_custom = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task15.authority.custom",
                semantic_version="1.0.0", blob_artifact_id=art["authority_custom"].id,
                sha256=_d("task15-authority-custom"),
                authority_model_type="custom_authoritative_ooxml", source_commit="task15",
            )
            authority_unapproved = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task15.authority.alt",
                semantic_version="1.0.1", blob_artifact_id=art["authority_unapproved"].id,
                sha256=_d("task15-authority-alt"),
                authority_model_type="projection_contract", source_commit="task15",
            )

            def _slots() -> dict[BundleSlot, BundleSlotSpec]:
                return {
                    BundleSlot.template: D.definition_slot_spec(
                        BundleSlot.template,
                        definition_id=tpl.id,
                        definition_sha256=tpl.sha256,
                    ),
                    BundleSlot.instrumentation: D.definition_slot_spec(
                        BundleSlot.instrumentation,
                        definition_id=instr.id,
                        definition_sha256=instr.sha256,
                    ),
                    BundleSlot.contract: D.definition_slot_spec(
                        BundleSlot.contract,
                        definition_id=contract_def.id,
                        definition_sha256=contract_def.sha256,
                    ),
                }

            def _custom_slots() -> dict[BundleSlot, BundleSlotSpec]:
                return {
                    BundleSlot.template: D.definition_slot_spec(
                        BundleSlot.template,
                        definition_id=tpl.id,
                        definition_sha256=tpl.sha256,
                    ),
                    BundleSlot.instrumentation: D.marker_slot_spec(
                        BundleSlot.instrumentation
                    ),
                    BundleSlot.contract: D.marker_slot_spec(BundleSlot.contract),
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
            bundle_custom = await repo.create_definition_bundle(
                authority_model_definition_id=authority_custom.id,
                slots=_custom_slots(),
                canonical_payload_artifact_id=art["bundle_custom"].id,
                canonical_payload_sha256=D.bundle_canonical_digest(
                    authority_model="custom_authoritative_ooxml",
                    authority_model_definition_sha256=authority_custom.sha256,
                    slots=_custom_slots(),
                ),
            )
            bundle_unapproved = await repo.create_definition_bundle(
                authority_model_definition_id=authority_unapproved.id,
                slots=_slots(),
                canonical_payload_artifact_id=art["bundle_unapproved"].id,
                canonical_payload_sha256=D.bundle_canonical_digest(
                    authority_model="projection_contract",
                    authority_model_definition_sha256=authority_unapproved.sha256,
                    slots=_slots(),
                ),
                approved=False,
            )

            cv0 = await repo.create_content_version(
                project_id=project, wp_id=wp, entry_id=ENTRY, revision=0, source="html",
                projection_artifact_id=art_proj0.id, projection_sha256=art_proj0.sha256,
                actor_id=user,
            )
            rep1 = await repo.create_representation(
                project_id=project, wp_id=wp, entry_id=ENTRY,
                content_version_id=cv0.id, generation=1, document_type="xlsx",
                artifact_id=art_gen1.id, artifact_sha256=art_gen1.sha256,
                definition_bundle_id=bundle.id,
                authority_model_definition_id=authority.id,
                adapter_id=ENTRY, adapter_build_digest=_d("task15-adapter"),
                structure_hash=_d("task15-structure-1"),
                identity_inventory_sha256=_d("task15-identity-1"),
                reason="content_commit",
            )
            await repo.set_entry_pointer(
                wp_id=wp, entry_id=ENTRY, representation_id=rep1.id, generation=1
            )
            await repo.set_current_content_version(wp, cv0.id)
            # operation：pending mutation 的 `ck_wppm_committed_result` 要求 committed 时
            # 必须留下可重放的 operation + content version。html_to_oo 的 shell 不需要
            # room/request（两者 nullable），直接建。
            op_id = uuid.uuid4()
            await s.execute(
                sa.text(
                    "INSERT INTO working_paper_sync_operation "
                    "(id, project_id, wp_id, entry_id, direction, state, "
                    " definition_bundle_id, definition_bundle_sha256, "
                    " authority_model_definition_id, authority_model_definition_sha256, "
                    " created_by) VALUES "
                    "(:id, :p, :w, :e, 'html_to_oo', 'created', :b, :bs, :a, :as_, :u)"
                ),
                {
                    "id": str(op_id), "p": str(project), "w": str(wp), "e": ENTRY,
                    "b": str(bundle.id), "bs": bundle.canonical_payload_sha256,
                    "a": str(authority.id), "as_": authority.sha256, "u": str(user),
                },
            )
            await s.commit()
            world.update({
                "cv0": cv0.id, "rep1": rep1.id, "bundle": bundle.id,
                "bundle_custom": bundle_custom.id,
                "bundle_unapproved": bundle_unapproved.id,
                "authority": authority.id, "contract_def": contract_def.id,
                "tpl": tpl.id, "instr": instr.id, "op": op_id,
                "gen1_rel": gen1.relative_path, "gen1_sha": gen1.sha256,
            })
        snap["world"] = {k: str(v) for k, v in world.items()}
        substrate_path = base_root / world["gen1_rel"]

        # ── 工具：造 plan / mutation / 服务 ──────────────────────────────
        def _projection(values: dict[str, Any]) -> Projection:
            index = None
            fields: dict[str, FieldValue] = {}
            for key, raw in values.items():
                spec = contract.field_by_stable_key(key)
                fields[key] = FieldValue(
                    stable_key=key, value=raw,
                    value_type=spec.value_type, mode=spec.mode,
                )
            assert index is None
            return Projection(
                contract_id=contract.contract_id,
                semantic_version=contract.semantic_version,
                document_type=contract.document_type,
                values=fields,
            )

        def _services(session):
            repo = WorkpaperSyncRepository(session)
            resolution = CanonicalResolutionService(session, artifacts)
            return (
                repo,
                resolution,
                CM.ContentMutationService(
                    session=session, repository=repo, artifacts=artifacts,
                    resolution=resolution,
                ),
                R.RepresentationService(
                    session=session, repository=repo, artifacts=artifacts,
                    resolution=resolution,
                ),
            )

        def _count_commits(session) -> dict[str, int]:
            counter = {"n": 0}

            def _bump(_sess: Any) -> None:
                counter["n"] += 1

            sa_event.listen(session.sync_session, "after_commit", _bump)
            return counter

        async def _snapshot(session) -> dict[str, Any]:
            wp_row = (
                await session.execute(
                    sa.text(
                        "SELECT content_revision, current_content_version_id::text, "
                        "file_version FROM working_paper WHERE id = :w"
                    ),
                    {"w": str(wp)},
                )
            ).one()
            pointer = (
                await session.execute(
                    sa.text(
                        "SELECT current_representation_id::text, representation_generation "
                        "FROM working_paper_sync_entry_state "
                        "WHERE wp_id = :w AND entry_id = :e"
                    ),
                    {"w": str(wp), "e": ENTRY},
                )
            ).first()
            counts = {}
            for table in (
                "working_paper_content_version",
                "working_paper_content_representation",
                "import_event_outbox",
            ):
                counts[table] = int(
                    (
                        await session.execute(sa.text(f"SELECT count(*) FROM {table}"))
                    ).scalar_one()
                )
            old_rep = (
                await session.execute(
                    sa.text(
                        "SELECT to_jsonb(t)::text FROM "
                        "working_paper_content_representation t WHERE id = :r"
                    ),
                    {"r": str(world["rep1"])},
                )
            ).scalar_one()
            old_cv = (
                await session.execute(
                    sa.text(
                        "SELECT to_jsonb(t)::text FROM working_paper_content_version t "
                        "WHERE id = :c"
                    ),
                    {"c": str(world["cv0"])},
                )
            ).scalar_one()
            return {
                "content_revision": int(wp_row[0]),
                "current_content_version_id": wp_row[1],
                "file_version": int(wp_row[2]),
                "pointer_representation_id": pointer[0] if pointer else None,
                "pointer_generation": int(pointer[1]) if pointer else None,
                "counts": counts,
                "old_representation_row": old_rep,
                "old_content_version_row": old_cv,
            }

        async def _bundle_snapshot(session, bundle_id):
            return await CanonicalResolutionService(session, artifacts).load_bundle_snapshot(
                bundle_id
            )

        # ══ ① 业务 commit（HTML→OO）：五张表同事务 + 恰一次提交 ═══════════
        async with Session() as s:
            snap["business_commit"]["before"] = await _snapshot(s)
        async with Session() as s:
            repo, resolution, mutation_svc, _ = _services(s)
            commits = _count_commits(s)
            try:
                snapshot_bundle = await _bundle_snapshot(s, world["bundle"])
                plan = CM.ContentCommitPlan(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    source=CM.ContentSource("html"), expected_revision=0,
                    bundle=snapshot_bundle, adapter_id=ENTRY,
                    adapter_build_digest=_d("task15-adapter"), document_type="xlsx",
                    substrate_path=substrate_path,
                    substrate_role=SubstrateRole.published_representation,
                    substrate_kind=ArtifactKind.canonical,
                    substrate_state=ArtifactState.published,
                    actor_id=user, operation_id=world["op"],
                    parent_version_id=world["cv0"], contract=contract,
                )
                receipt = await mutation_svc.commit(
                    plan=plan,
                    mutation=CM.BusinessMutation(
                        projection=_projection({PERIOD: "2025 年度", TOTAL: "1234.50"})
                    ),
                    adapter=adapter,
                )
                snap["business_commit"]["receipt"] = receipt.as_dict()
                snap["business_commit"]["commit_count_observed"] = commits["n"]
                world["cv1"] = receipt.content_version_id
                world["rep2"] = receipt.representation_id
                world["pending_event"] = receipt.pending_event
                snap["business_commit"]["event_payload"] = {
                    k: (str(v) if isinstance(v, uuid.UUID) else v)
                    for k, v in (receipt.event_payload or {}).items()
                }
            except Exception as exc:  # noqa: BLE001
                snap["errors"].append(f"business_commit: {_err(exc)}")
                raise

        async with Session() as s:
            snap["business_commit"]["after"] = await _snapshot(s)
            # ── ② `xmin` 全等：独立于本代码的单事务判据 ─────────────────
            xmins: dict[str, str] = {}
            for table, label in _ATOMIC_TABLES:
                where = {
                    "working_paper": ("id = :k", str(wp)),
                    "working_paper_content_version": ("id = :k", str(world["cv1"])),
                    "working_paper_content_representation": ("id = :k", str(world["rep2"])),
                    "working_paper_sync_entry_state": ("wp_id = :k", str(wp)),
                    "import_event_outbox": ("project_id = :k", str(project)),
                }[table]
                xmins[label] = str(
                    (
                        await s.execute(
                            sa.text(f"SELECT xmin::text FROM {table} WHERE {where[0]}"),
                            {"k": where[1]},
                        )
                    ).scalars().first()
                )
            snap["atomicity"]["xmin"] = xmins
            snap["atomicity"]["distinct_xmin"] = sorted(set(xmins.values()))
            # ── ③ outbox 行在 commit 后仍是 pending（发布是独立一步）────
            row = (
                await s.execute(
                    sa.text(
                        "SELECT status::text, event_type, payload::text, "
                        "(published_at IS NOT NULL) FROM import_event_outbox"
                    )
                )
            ).one()
            snap["outbox"]["after_commit"] = {
                "status": row[0], "event_type": row[1],
                "payload_has_revision": '"revision": 1' in row[2] or '"revision":1' in row[2],
                "published_at_set": bool(row[3]),
            }

        # ── ④ commit 之后才发布（Requirement 13.1）────────────────────
        async with Session() as s:
            _, _, mutation_svc, _ = _services(s)
            try:
                receipt_obj = CM.ContentCommitReceipt(
                    wp_id=wp, entry_id=ENTRY,
                    content_version_id=world["cv1"], revision=1,
                    representation_id=world["rep2"],
                    representation_generation=1,
                    artifact_sha256=_d("x"), projection_sha256=None,
                    definition_bundle_id=world["bundle"],
                    definition_bundle_sha256=_d("y"),
                    authority_model="projection_contract",
                    operation_id=world["op"], replayed=False,
                    requires_client_refresh=False, commit_count=1,
                    transaction_ids=(), pending_event=world["pending_event"],
                    event_payload=None,
                )
                snap["outbox"]["publish_report"] = await mutation_svc.publish_committed_events(
                    receipt_obj
                )
            except Exception as exc:  # noqa: BLE001
                snap["errors"].append(f"publish_committed_events: {_err(exc)}")
        async with Session() as s:
            row = (
                await s.execute(
                    sa.text(
                        "SELECT status::text, (published_at IS NOT NULL), attempt_count "
                        "FROM import_event_outbox"
                    )
                )
            ).one()
            snap["outbox"]["after_publish"] = {
                "status": row[0], "published_at_set": bool(row[1]),
                "attempt_count": int(row[2]),
            }

        # ══ ⑤ rollback：原 pointer/revision 不变，文件成不可见 orphan ═════
        async with Session() as s:
            snap["rollback"]["before"] = await _snapshot(s)
        def _stored_files() -> set[str]:
            """`storage/` 下全部 xlsx 的 base_root 相对 POSIX 路径。"""
            return {
                p.relative_to(base_root).as_posix()
                for p in (base_root / "storage").rglob("*.xlsx")
            }

        orphan_candidates_before = _stored_files()
        async with Session() as s:
            _, _, mutation_svc, _ = _services(s)
            commits = _count_commits(s)
            try:
                snapshot_bundle = await _bundle_snapshot(s, world["bundle"])
                stale_plan = CM.ContentCommitPlan(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    source=CM.ContentSource("html"),
                    # 🔴 故意用**过期** base：真实 revision 已经是 1
                    expected_revision=0,
                    bundle=snapshot_bundle, adapter_id=ENTRY,
                    adapter_build_digest=_d("task15-adapter"), document_type="xlsx",
                    substrate_path=substrate_path,
                    substrate_role=SubstrateRole.published_representation,
                    substrate_kind=ArtifactKind.canonical,
                    substrate_state=ArtifactState.published,
                    actor_id=user, operation_id=world["op"],
                    parent_version_id=world["cv1"], contract=contract,
                )
                await mutation_svc.commit(
                    plan=stale_plan,
                    mutation=CM.BusinessMutation(
                        projection=_projection({PERIOD: "并发写入", TOTAL: "999.00"})
                    ),
                    adapter=adapter,
                )
                snap["rollback"]["outcome"] = "NO ERROR"
            except RevisionConflictError as exc:
                snap["rollback"]["outcome"] = _err(exc)
            except Exception as exc:  # noqa: BLE001
                snap["rollback"]["outcome"] = f"WRONG-TYPE {_err(exc)}"
            snap["rollback"]["commit_count_observed"] = commits["n"]
        async with Session() as s:
            snap["rollback"]["after"] = await _snapshot(s)
        new_files = sorted(_stored_files() - orphan_candidates_before)
        snap["rollback"]["new_files_on_disk"] = new_files
        async with Session() as s:
            # 判据是**逐条精确路径**比对，不是 LIKE 模糊匹配：sha12 里出现某个数字片段
            # 就会让模糊匹配误命中别的 artifact（首轮实测的假红）。
            referenced = (
                await s.execute(
                    sa.text(
                        "SELECT count(*) FROM working_paper_artifact "
                        "WHERE relative_path = ANY(:paths)"
                    ),
                    {"paths": new_files or [""]},
                )
            ).scalar_one()
            snap["rollback"]["orphan_rows_referencing_new_file"] = int(referenced)

        # ══ ⑥ 双 revision 形态不可能：同 expected 再来一次必失败 ═════════
        async with Session() as s:
            _, _, mutation_svc, _ = _services(s)
            try:
                snapshot_bundle = await _bundle_snapshot(s, world["bundle"])
                plan_again = CM.ContentCommitPlan(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    source=CM.ContentSource("html"), expected_revision=1,
                    bundle=snapshot_bundle, adapter_id=ENTRY,
                    adapter_build_digest=_d("task15-adapter"), document_type="xlsx",
                    substrate_path=substrate_path,
                    substrate_role=SubstrateRole.published_representation,
                    substrate_kind=ArtifactKind.canonical,
                    substrate_state=ArtifactState.published,
                    actor_id=user, operation_id=world["op"],
                    parent_version_id=world["cv1"], contract=contract,
                )
                receipt2 = await mutation_svc.commit(
                    plan=plan_again,
                    mutation=CM.BusinessMutation(
                        projection=_projection({PERIOD: "2025 年度 第二次", TOTAL: "1.00"})
                    ),
                    adapter=adapter,
                )
                snap["double_revision"]["second_commit_revision"] = receipt2.revision
                world["cv2"] = receipt2.content_version_id
                world["rep3"] = receipt2.representation_id
                # 同一份 receipt 的 representation 数：一次业务 commit 恰一个
                snap["double_revision"]["representations_for_cv2"] = int(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT count(*) FROM working_paper_content_representation "
                                "WHERE content_version_id = :c"
                            ),
                            {"c": str(receipt2.content_version_id)},
                        )
                    ).scalar_one()
                )
            except Exception as exc:  # noqa: BLE001
                snap["errors"].append(f"second_commit: {_err(exc)}")
        async with Session() as s:
            rows = (
                await s.execute(
                    sa.text(
                        "SELECT revision, count(*) FROM working_paper_content_version "
                        "WHERE wp_id = :w GROUP BY revision ORDER BY revision"
                    ),
                    {"w": str(wp)},
                )
            ).all()
            snap["double_revision"]["revision_histogram"] = {
                int(r[0]): int(r[1]) for r in rows
            }
            snap["double_revision"]["final_revision"] = int(
                (
                    await s.execute(
                        sa.text("SELECT content_revision FROM working_paper WHERE id = :w"),
                        {"w": str(wp)},
                    )
                ).scalar_one()
            )
            # 每个 content version 恰有一个 representation（不存在「先 projection-only
            # 再补 artifact」留下的裸 version）
            naked = (
                await s.execute(
                    sa.text(
                        "SELECT count(*) FROM working_paper_content_version cv "
                        "WHERE cv.wp_id = :w AND NOT EXISTS ("
                        "  SELECT 1 FROM working_paper_content_representation r "
                        "  WHERE r.content_version_id = cv.id)"
                    ),
                    {"w": str(wp)},
                )
            ).scalar_one()
            snap["double_revision"]["content_versions_without_representation"] = int(naked)

        # ══ ⑦ pending mutation 幂等重放（Property 10）════════════════════
        async with Session() as s:
            repo, _, mutation_svc, _ = _services(s)
            try:
                payload_pub = artifacts.publish_definition_blob(
                    project_id=project, wp_id=wp, definition_kind="bundle",
                    payload=b'{"pending":"payload"}',
                )
                payload_art = await repo.register_artifact(
                    project_id=project, wp_id=wp,
                    kind=ArtifactKind.definition, state=ArtifactState.published,
                    relative_path=payload_pub.relative_path, sha256=payload_pub.sha256,
                    size_bytes=payload_pub.size_bytes,
                    document_type=payload_pub.document_type,
                    retention_class="definition",
                )
                token = await repo.create_pending_mutation(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    sheet_key="G7 披露表", user_id=user,
                    expected_revision=2,
                    payload_artifact_id=payload_art.id,
                    payload_sha256=payload_pub.sha256,
                    idempotency_key="task15-idem-1",
                )
                expired = await repo.create_pending_mutation(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    sheet_key="G7 披露表", user_id=user,
                    expected_revision=2,
                    payload_artifact_id=payload_art.id,
                    payload_sha256=payload_pub.sha256,
                    idempotency_key="task15-idem-expired",
                    ttl=timedelta(minutes=1),
                )
                # 🔴 scope 判据是三个**独立**合取项（project / wp / entry），必须逐项
                #    可 falsify。原先只有一条「wp 与 entry 同时不同」的 token：短路
                #    `row.entry_id != plan.entry_id` 之后 wp 那一项照样把它拦下 ⇒ 异常
                #    类型与文案都不变 ⇒ 变异 M25 判 GREEN（实测过）。因此拆成两条：
                #      cross_wp    仅 wp 不同（entry 同名）
                #      cross_entry 仅 entry 不同（同 project 同 wp）
                cross = await repo.create_pending_mutation(
                    project_id=project, wp_id=other_wp, entry_id=ENTRY,
                    sheet_key="G7 披露表", user_id=user,
                    expected_revision=2,
                    payload_artifact_id=payload_art.id,
                    payload_sha256=payload_pub.sha256,
                    idempotency_key="task15-idem-cross",
                )
                cross_entry = await repo.create_pending_mutation(
                    project_id=project, wp_id=wp, entry_id=OTHER_WP_ENTRY,
                    sheet_key="G7 披露表", user_id=user,
                    expected_revision=2,
                    payload_artifact_id=payload_art.id,
                    payload_sha256=payload_pub.sha256,
                    idempotency_key="task15-idem-cross-entry",
                )
                wrong_base = await repo.create_pending_mutation(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    sheet_key="G7 披露表", user_id=user,
                    expected_revision=99,
                    payload_artifact_id=payload_art.id,
                    payload_sha256=payload_pub.sha256,
                    idempotency_key="task15-idem-wrong-base",
                )
                await s.commit()
                world.update({
                    "token": token.id, "token_expired": expired.id,
                    "token_cross": cross.id, "token_cross_entry": cross_entry.id,
                    "token_wrong_base": wrong_base.id,
                })
                # 让 expired 真的过期（不 sleep：直接把 expires_at 拨到过去，
                # 但 created_at 也要一起拨，否则撞 `ck_wppm_ttl`）
                await s.execute(
                    sa.text(
                        "UPDATE working_paper_pending_mutation SET "
                        "created_at = now() - interval '2 hours', "
                        "expires_at = now() - interval '1 hour' WHERE id = :i"
                    ),
                    {"i": str(expired.id)},
                )
                await s.commit()
            except Exception as exc:  # noqa: BLE001
                snap["errors"].append(f"pending_setup: {_err(exc)}")

        def _token_plan(session_bundle, *, token_id, expected_revision=2):
            return CM.ContentCommitPlan(
                project_id=project, wp_id=wp, entry_id=ENTRY,
                source=CM.ContentSource("html"), expected_revision=expected_revision,
                bundle=session_bundle, adapter_id=ENTRY,
                adapter_build_digest=_d("task15-adapter"), document_type="xlsx",
                substrate_path=substrate_path,
                substrate_role=SubstrateRole.published_representation,
                substrate_kind=ArtifactKind.canonical,
                substrate_state=ArtifactState.published,
                actor_id=user, operation_id=world["op"],
                parent_version_id=world["cv2"], contract=contract,
                pending_mutation_id=token_id, idempotency_key="task15-idem-1",
            )

        async with Session() as s:
            _, _, mutation_svc, _ = _services(s)
            try:
                sb = await _bundle_snapshot(s, world["bundle"])
                first = await mutation_svc.commit(
                    plan=_token_plan(sb, token_id=world["token"]),
                    mutation=CM.BusinessMutation(
                        projection=_projection({PERIOD: "token 提交", TOTAL: "77.00"})
                    ),
                    adapter=adapter,
                )
                snap["idempotency"]["first"] = first.as_dict()
                world["cv3"] = first.content_version_id
            except Exception as exc:  # noqa: BLE001
                snap["errors"].append(f"token_first_commit: {_err(exc)}")
        async with Session() as s:
            _, _, mutation_svc, _ = _services(s)
            commits = _count_commits(s)
            try:
                sb = await _bundle_snapshot(s, world["bundle"])
                replay = await mutation_svc.commit(
                    plan=_token_plan(sb, token_id=world["token"]),
                    mutation=CM.BusinessMutation(
                        projection=_projection({PERIOD: "token 提交", TOTAL: "77.00"})
                    ),
                    adapter=adapter,
                )
                snap["idempotency"]["replay"] = replay.as_dict()
                snap["idempotency"]["replay_commit_count"] = commits["n"]
            except Exception as exc:  # noqa: BLE001
                snap["idempotency"]["replay"] = {"error": _err(exc)}
        async with Session() as s:
            snap["idempotency"]["revision_after_replay"] = int(
                (
                    await s.execute(
                        sa.text("SELECT content_revision FROM working_paper WHERE id = :w"),
                        {"w": str(wp)},
                    )
                ).scalar_one()
            )
            snap["idempotency"]["token_row"] = dict(
                (
                    await s.execute(
                        sa.text(
                            "SELECT state, result_content_version_id::text AS cv, "
                            "result_operation_id::text AS op, "
                            "(committed_at IS NOT NULL) AS done "
                            "FROM working_paper_pending_mutation WHERE id = :i"
                        ),
                        {"i": str(world["token"])},
                    )
                ).mappings().one()
            )

        # ══ ⑧ pending mutation 四类拒绝各自专属类型 ══════════════════════
        for label, token_key, expected_revision, want in (
            ("cross_wp", "token_cross", 3, CM.PendingMutationScopeError),
            ("cross_entry", "token_cross_entry", 3, CM.PendingMutationScopeError),
            ("expired", "token_expired", 3, CM.PendingMutationExpiredError),
            ("wrong_base", "token_wrong_base", 3, CM.PendingMutationPayloadError),
        ):
            async with Session() as s:
                _, _, mutation_svc, _ = _services(s)
                try:
                    sb = await _bundle_snapshot(s, world["bundle"])
                    await mutation_svc.commit(
                        plan=_token_plan(
                            sb, token_id=world[token_key],
                            expected_revision=expected_revision,
                        ),
                        mutation=CM.BusinessMutation(
                            projection=_projection({PERIOD: "x", TOTAL: "1.00"})
                        ),
                        adapter=adapter,
                    )
                    snap["pending_rejections"][label] = "NO ERROR"
                except want as exc:  # type: ignore[misc]
                    snap["pending_rejections"][label] = _err(exc)
                except Exception as exc:  # noqa: BLE001
                    snap["pending_rejections"][label] = f"WRONG-TYPE {_err(exc)}"

        # ══ ⑨ candidate finalize 只增不改（P4 / P67）═══════════════════
        # 载荷只构造一次：`_ooxml` 用 `zipfile.writestr(str, …)`，ZipInfo 的时间戳取
        # `time.localtime()` ⇒ 同参数两次调用**字节不同**。⑨b′ 要造一份「同字节、异路径」
        # 的孪生 candidate 来隔离路径判据，必须复用同一份 bytes。
        cand_payload = _ooxml("xlsx", extra={"xl/instrumented.xml": b"<gt/>"})
        cand_staged = artifacts.stage_upgrade_candidate(
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp,
                payload=cand_payload,
                document_type="xlsx",
            ),
            entry_id=ENTRY,
            equivalence_report=json.dumps({"equivalent": True}).encode(),
        )
        async with Session() as s:
            repo, _, _, _ = _services(s)
            try:
                cand_art = await repo.register_artifact(
                    project_id=project, wp_id=wp,
                    kind=ArtifactKind.upgrade_candidate, state=ArtifactState.candidate,
                    relative_path=cand_staged.relative_path, sha256=cand_staged.sha256,
                    size_bytes=cand_staged.size_bytes, document_type="xlsx",
                    retention_class="candidate",
                )
                candidate = await repo.create_upgrade_candidate(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    # 🔴 绑**当前** content version：finalize 只为既有 version 加 generation
                    content_version_id=world["cv3"],
                    source_representation_id=world["rep3"],
                    staged_artifact_id=cand_art.id,
                    staged_artifact_sha256=cand_art.sha256,
                    template_definition_id=world["tpl"],
                    instrumentation_definition_id=world["instr"],
                    state=CandidateState.awaiting_contract,
                )
                await s.commit()
                world["candidate"] = candidate.id
            except Exception as exc:  # noqa: BLE001
                snap["errors"].append(f"candidate_setup: {_err(exc)}")

        # ⑨a 未 ready ⇒ 拒绝，且 pointer/revision 不变
        async with Session() as s:
            snap["finalize_gate"]["before"] = await _snapshot(s)
        async with Session() as s:
            _, _, _, rep_svc = _services(s)
            try:
                await rep_svc.finalize_candidate(
                    project_id=project, candidate_id=world["candidate"],
                    staged_candidate=cand_staged, adapter_id=ENTRY,
                    adapter_build_digest=_d("task15-adapter"),
                    structure_hash=_d("task15-structure-upgrade"),
                    identity_inventory_sha256=_d("task15-identity-upgrade"),
                )
                snap["finalize_gate"]["not_ready"] = "NO ERROR"
            except CandidateNotFinalizableError as exc:
                snap["finalize_gate"]["not_ready"] = _err(exc)
            except Exception as exc:  # noqa: BLE001
                snap["finalize_gate"]["not_ready"] = f"WRONG-TYPE {_err(exc)}"
        async with Session() as s:
            snap["finalize_gate"]["after"] = await _snapshot(s)
            # candidate 仍不可见：resolver 的 current 意图仍返回旧 generation
            svc = CanonicalResolutionService(s, artifacts)
            try:
                res = await svc.resolve(
                    intent=ResolutionIntent.config, project_id=project, wp_id=wp,
                    entry_id=ENTRY,
                )
                snap["resolver_view"]["before_finalize"] = {
                    "representation_id": str(res.representation_id),
                    "generation": res.representation_generation,
                    "revision": res.content_revision,
                }
            except Exception as exc:  # noqa: BLE001
                snap["errors"].append(f"resolver_before_finalize: {_err(exc)}")

        # ⑨b 补齐 approved contract + bundle + 等值报告 ⇒ finalize
        async with Session() as s:
            await s.execute(
                sa.text(
                    "UPDATE working_paper_representation_upgrade_candidate SET "
                    "target_contract_definition_id = :c, target_definition_bundle_id = :b, "
                    "visible_equivalence_report_sha256 = :e, state = 'ready' WHERE id = :i"
                ),
                {
                    "c": str(world["contract_def"]), "b": str(world["bundle"]),
                    "e": _d("task15-equivalence"), "i": str(world["candidate"]),
                },
            )
            await s.commit()

        # ⑨b′ 喂**不属于本 candidate** 的 staged artifact：candidate 已 ready
        #      （contract/bundle/等值报告齐全），唯一可拒绝的理由就是「artifact 身份与
        #      DB 登记不符」。两条判据（relative_path / digest）必须**各自**可 falsify ——
        #      只喂「另一份 candidate 的字节」时路径与 digest 同时不符，短路任一条另一条
        #      都会顶上来、异常类型与文案不变 ⇒ 变异判 GREEN（M30 首轮实测）。故：
        #        foreign_path  同字节、异路径（另一个 candidate 目录）→ 只有 path 不符
        #        forged_digest 本 candidate 的真路径 + 伪造 digest → 只有 digest 不符
        twin_staged = artifacts.stage_upgrade_candidate(
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp,
                payload=cand_payload,
                document_type="xlsx",
            ),
            entry_id=ENTRY,
            equivalence_report=json.dumps({"equivalent": True}).encode(),
        )
        forged_staged = dataclasses.replace(
            cand_staged, sha256=_d("task15-forged-candidate-digest")
        )
        for label, fed in (("foreign_path", twin_staged), ("forged_digest", forged_staged)):
            async with Session() as s:
                _, _, _, rep_svc = _services(s)
                try:
                    await rep_svc.finalize_candidate(
                        project_id=project, candidate_id=world["candidate"],
                        staged_candidate=fed, adapter_id=ENTRY,
                        adapter_build_digest=_d("task15-adapter"),
                        structure_hash=_d("task15-structure-upgrade"),
                        identity_inventory_sha256=_d("task15-identity-upgrade"),
                    )
                    snap["finalize_gate"][label] = "NO ERROR"
                except R.RepresentationPointerError as exc:
                    snap["finalize_gate"][label] = _err(exc)
                except Exception as exc:  # noqa: BLE001
                    snap["finalize_gate"][label] = f"WRONG-TYPE {_err(exc)}"
        snap["finalize_gate"]["twin_same_digest"] = (
            twin_staged.sha256 == cand_staged.sha256
            and twin_staged.relative_path != cand_staged.relative_path
        )

        async with Session() as s:
            snap["finalize"]["before"] = await _snapshot(s)
        async with Session() as s:
            _, _, _, rep_svc = _services(s)
            commits = _count_commits(s)
            try:
                outcome = await rep_svc.finalize_candidate(
                    project_id=project, candidate_id=world["candidate"],
                    staged_candidate=cand_staged, adapter_id=ENTRY,
                    adapter_build_digest=_d("task15-adapter"),
                    structure_hash=_d("task15-structure-upgrade"),
                    identity_inventory_sha256=_d("task15-identity-upgrade"),
                )
                snap["finalize"]["outcome"] = outcome.as_dict()
                snap["finalize"]["commit_count_observed"] = commits["n"]
                world["rep_upgraded"] = outcome.representation_id
            except Exception as exc:  # noqa: BLE001
                snap["finalize"]["outcome"] = {"error": _err(exc)}
                snap["errors"].append(f"finalize: {_err(exc)}")
        async with Session() as s:
            snap["finalize"]["after"] = await _snapshot(s)
            if "rep_upgraded" in world:
                xmins = {}
                for table, key, column in (
                    ("working_paper_content_representation", world["rep_upgraded"], "id"),
                    ("working_paper_sync_entry_state", wp, "wp_id"),
                    ("working_paper_representation_upgrade_candidate", world["candidate"], "id"),
                ):
                    xmins[table] = str(
                        (
                            await s.execute(
                                sa.text(
                                    f"SELECT xmin::text FROM {table} WHERE {column} = :k"
                                ),
                                {"k": str(key)},
                            )
                        ).scalars().first()
                    )
                snap["finalize"]["xmin"] = xmins
                snap["finalize"]["distinct_xmin"] = sorted(set(xmins.values()))
                snap["finalize"]["new_representation_row"] = dict(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT reason, generation, content_version_id::text AS cv, "
                                "parent_representation_id::text AS parent "
                                "FROM working_paper_content_representation WHERE id = :r"
                            ),
                            {"r": str(world["rep_upgraded"])},
                        )
                    ).mappings().one()
                )
                snap["finalize"]["candidate_row"] = dict(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT state, finalized_representation_id::text AS rep, "
                                "(finalized_at IS NOT NULL) AS done FROM "
                                "working_paper_representation_upgrade_candidate WHERE id = :i"
                            ),
                            {"i": str(world["candidate"])},
                        )
                    ).mappings().one()
                )
                snap["finalize"]["upgrade_event"] = dict(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT event_type, payload::text AS payload FROM "
                                "import_event_outbox ORDER BY created_at DESC LIMIT 1"
                            )
                        )
                    ).mappings().one()
                )
                svc = CanonicalResolutionService(s, artifacts)
                res = await svc.resolve(
                    intent=ResolutionIntent.config, project_id=project, wp_id=wp,
                    entry_id=ENTRY,
                )
                snap["resolver_view"]["after_finalize"] = {
                    "representation_id": str(res.representation_id),
                    "generation": res.representation_generation,
                    "revision": res.content_revision,
                    "bundle": res.bundle.bundle_sha256,
                }

        # ══ ⑩ custom authoritative commit（Requirement 2.11 / 6.19）══════
        async with Session() as s:
            _, _, mutation_svc, _ = _services(s)
            try:
                sb = await _bundle_snapshot(s, world["bundle_custom"])
                custom_plan = CM.ContentCommitPlan(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    source=CM.ContentSource("custom"),
                    expected_revision=snap["finalize"]["after"]["content_revision"],
                    bundle=sb, adapter_id=ENTRY,
                    adapter_build_digest=_d("task15-adapter"), document_type="xlsx",
                    substrate_path=substrate_path,
                    substrate_role=SubstrateRole.published_representation,
                    substrate_kind=ArtifactKind.canonical,
                    substrate_state=ArtifactState.published,
                    actor_id=user, operation_id=world["op"],
                    parent_version_id=world["cv3"], contract=None,
                )
                custom_receipt = await mutation_svc.commit(
                    plan=custom_plan,
                    mutation=CM.BusinessMutation(
                        authoritative_payload=_ooxml(
                            "xlsx", extra={"xl/user.xml": b"<uploaded/>"}
                        )
                    ),
                    adapter=None,
                )
                snap["custom_authoritative"]["receipt"] = custom_receipt.as_dict()
                row = (
                    await s.execute(
                        sa.text(
                            "SELECT projection_artifact_id::text AS proj, "
                            "authoritative_artifact_id::text AS auth, source "
                            "FROM working_paper_content_version WHERE id = :c"
                        ),
                        {"c": str(custom_receipt.content_version_id)},
                    )
                ).mappings().one()
                snap["custom_authoritative"]["version_row"] = dict(row)
            except Exception as exc:  # noqa: BLE001
                snap["custom_authoritative"]["receipt"] = {"error": _err(exc)}
                snap["errors"].append(f"custom_commit: {_err(exc)}")

        # ══ ⑪ room 双基线：server last-applied 推进 + merged≠incoming ⇒ refresh ══
        async with Session() as s:
            repo, _, mutation_svc, _ = _services(s)
            try:
                room = await repo.create_room(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    doc_key=f"task15-{uuid.uuid4().hex[:8]}", generation=1,
                    opened_base_version_id=world["cv0"],
                )
                await s.commit()
                world["room"] = room.id
            except Exception as exc:  # noqa: BLE001
                snap["errors"].append(f"room_setup: {_err(exc)}")
        async with Session() as s:
            _, _, mutation_svc, _ = _services(s)
            try:
                from app.services.workpaper_sync import merge as MG

                incoming = _projection({PERIOD: "编辑器里的旧值", TOTAL: "5.00"})
                merged = MG.merge_projections(
                    base=_projection({PERIOD: "编辑器里的旧值", TOTAL: "5.00"}),
                    current=_projection({PERIOD: "服务端改过", TOTAL: "5.00"}),
                    incoming=incoming,
                    contract=contract,
                )
                sb = await _bundle_snapshot(s, world["bundle"])
                current_rev = int(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT content_revision FROM working_paper WHERE id = :w"
                            ),
                            {"w": str(wp)},
                        )
                    ).scalar_one()
                )
                room_plan = CM.ContentCommitPlan(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    source=CM.ContentSource("onlyoffice"),
                    expected_revision=current_rev,
                    bundle=sb, adapter_id=ENTRY,
                    adapter_build_digest=_d("task15-adapter"), document_type="xlsx",
                    substrate_path=substrate_path,
                    substrate_role=SubstrateRole.published_representation,
                    substrate_kind=ArtifactKind.canonical,
                    substrate_state=ArtifactState.published,
                    actor_id=user, operation_id=world["op"],
                    parent_version_id=world["cv3"], contract=contract,
                    room_id=world["room"],
                )
                room_receipt = await mutation_svc.commit(
                    plan=room_plan,
                    mutation=CM.BusinessMutation(
                        projection=merged.merged, merge=merged, incoming=incoming
                    ),
                    adapter=adapter,
                )
                snap["room"] = {"receipt": room_receipt.as_dict()}
            except Exception as exc:  # noqa: BLE001
                snap["room"] = {"receipt": {"error": _err(exc)}}
                snap["errors"].append(f"room_commit: {_err(exc)}")
        async with Session() as s:
            if world.get("room"):
                snap.setdefault("room", {})["row"] = dict(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT state, last_applied_version_id::text AS applied, "
                                "client_confirmed_base_version_id::text AS confirmed, "
                                "refresh_reason, "
                                "(refresh_required_at IS NOT NULL) AS refresh_stamped "
                                "FROM working_paper_oo_room WHERE id = :r"
                            ),
                            {"r": str(world["room"])},
                        )
                    ).mappings().one()
                )

        # ══ ⑫ unapproved bundle 不得支撑 representation ═════════════════
        async with Session() as s:
            _, resolution, _, _ = _services(s)
            try:
                await resolution.load_bundle_snapshot(world["bundle_unapproved"])
                snap["finalize_gate"]["unapproved_bundle"] = "NO ERROR"
            except Exception as exc:  # noqa: BLE001
                snap["finalize_gate"]["unapproved_bundle"] = _err(exc)

        # 采集期间新增的 id（cv1/cv2/cv3/rep2/rep3/candidate/token…）也要进快照，
        # 否则守卫只能看到建世界阶段那一批（首轮实测 KeyError: 'cv3'）。
        snap["world"] = {
            k: (str(v) if not isinstance(v, (int, str, type(None))) else v)
            for k, v in world.items()
        }
        return snap
    except Exception as exc:  # noqa: BLE001
        # 🔴 采集**整体**失败也必须变成「守卫红」，不能变成「模块级 fixture ERROR」。
        #
        # 实测（变异 M20：往 `_commit_once` 中途注入第二次 `session.commit()`）：业务
        # commit 抛错被 ① 段捕获记进 `snap["errors"]`，但紧随其后的快照查询
        # （`SELECT … .one()`）拿不到行而抛 `NoResultFound` —— 它落在任何 per-section
        # `try` 之外 ⇒ `_collect()` 整体抛 ⇒ 本模块 45 条全部 **ERROR**。而 pytest 的
        # `-rf` 摘要只列 failed，errors 不在其中 ⇒ 变异四态判定拿不到任何「新增失败」，
        # M20 被判 WRONG-TEST（真凶是采集不是判据）。
        #
        # 这里把它收成「`snap["errors"]` 非空 + 部分快照」：`test_no_harness_errors`
        # 必红，其余守卫按缺键各自失败/报错。**不是 fail-open** —— 异常被记录且有一条
        # 守卫专门断言它为空，只是把「判据无法运行」降级成「判据打红」。
        world_snapshot = locals().get("world") or {}
        snap["errors"].append(f"collect_aborted: {_err(exc)}")
        snap.setdefault("world", {})
        snap["world"].update(
            {
                k: (str(v) if not isinstance(v, (int, str, type(None))) else v)
                for k, v in world_snapshot.items()
            }
        )
        return snap
    finally:
        bus._redis_available = previous_redis_flag
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await admin.dispose()
            shutil.rmtree(base_root, ignore_errors=True)


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


# ═══════════════════════════════════════════════════════════════════════════
# 守卫
# ═══════════════════════════════════════════════════════════════════════════


class TestHarness:
    def test_real_postgres(self, snap: dict[str, Any]) -> None:
        assert "PostgreSQL" in (snap["server_version"] or "")

    def test_migration_applied_cleanly(self, snap: dict[str, Any]) -> None:
        assert snap["apply_errors"] == []

    def test_no_harness_errors(self, snap: dict[str, Any]) -> None:
        """🔴 采集内部异常必须为空：fail-open 会让「静默取空」冒充「判据通过」。"""
        assert snap["errors"] == [], f"采集内部异常: {snap['errors']}"

    def test_scratch_schema_is_isolated(self, snap: dict[str, Any]) -> None:
        assert snap["schema"].startswith(_SCHEMA_PREFIX)
        assert "tmp_task15_store_" in snap["base_root"]


class TestSingleTransactionAtomicity:
    """Requirement 2.4 / 13.1：五张表同生共死。"""

    def test_business_commit_succeeded(self, snap: dict[str, Any]) -> None:
        """前置：commit 必须真的成功，否则下面的原子性判据全是空转。"""
        receipt = snap["business_commit"].get("receipt")
        assert receipt, snap["business_commit"]
        assert receipt["revision"] == 1
        assert receipt["replayed"] is False

    def test_all_five_writes_share_one_transaction_id(self, snap: dict[str, Any]) -> None:
        """🔴 独立判据：PostgreSQL 的 `xmin` 证明五张表是同一个事务写的。

        这条不依赖 `_TransactionWitness`（那是我们自己的代码）—— 即便见证逻辑被改坏，
        本条仍然会红。注入第二次 `session.commit()` 会让后半段落到新 xid ⇒ 打破全等。
        """
        xmins = snap["atomicity"]["xmin"]
        assert set(xmins) == {label for _, label in _ATOMIC_TABLES}, xmins
        assert len(snap["atomicity"]["distinct_xmin"]) == 1, (
            "content version / revision / representation / entry pointer / outbox "
            f"落在多个事务里: {xmins}"
        )

    def test_service_witness_agrees_with_database(self, snap: dict[str, Any]) -> None:
        """服务自报的事务 id 恰一个，且与数据库 `xmin` 一致（两条判据互相校验）。"""
        ids = snap["business_commit"]["receipt"]["transaction_ids"]
        assert len(ids) == 1, f"服务见证到多个事务: {ids}"
        assert ids[0] == snap["atomicity"]["distinct_xmin"][0], (
            f"服务见证 {ids[0]} 与数据库 xmin {snap['atomicity']['distinct_xmin'][0]} 不符"
        )

    def test_exactly_one_database_commit(self, snap: dict[str, Any]) -> None:
        """第二条独立判据：`after_commit` 事件恰触发一次。"""
        assert snap["business_commit"]["commit_count_observed"] == 1, (
            f"一次业务 commit 观测到 {snap['business_commit']['commit_count_observed']} 次"
            "数据库提交 —— 「先提交 projection-only version 再补一次」正是这个形态"
        )
        assert snap["business_commit"]["receipt"]["commit_count"] == 1

    def test_commit_creates_exactly_one_version_and_one_representation(
        self, snap: dict[str, Any]
    ) -> None:
        before = snap["business_commit"]["before"]
        after = snap["business_commit"]["after"]
        assert (
            after["counts"]["working_paper_content_version"]
            == before["counts"]["working_paper_content_version"] + 1
        )
        assert (
            after["counts"]["working_paper_content_representation"]
            == before["counts"]["working_paper_content_representation"] + 1
        )
        assert after["content_revision"] == before["content_revision"] + 1
        assert after["pointer_representation_id"] != before["pointer_representation_id"]
        assert after["file_version"] == before["file_version"], (
            "业务 commit 竟动了 legacy `file_version`（Requirement 2.1 明令它不参与同步版本）"
        )

    def test_no_content_version_lacks_a_representation(self, snap: dict[str, Any]) -> None:
        """🔴 被禁形态的直接判据：不存在「有 content version 却没有 representation」的行。

        「先提交 projection-only version，再补 artifact」一旦发生，中间态就会留下这样
        一行。查全表而不是查某一行，因此任何路径造出它都会红。
        """
        assert snap["double_revision"]["content_versions_without_representation"] == 0


class TestNoDoubleRevision:
    """Requirement 3.1 / Property 10：一次业务应用恰推进一次 revision。"""

    def test_stale_base_is_rejected(self, snap: dict[str, Any]) -> None:
        got = snap["rollback"]["outcome"]
        assert got.startswith("RevisionConflictError"), got
        assert "乐观锁" in got

    def test_second_commit_advances_by_exactly_one(self, snap: dict[str, Any]) -> None:
        assert snap["double_revision"]["second_commit_revision"] == 2
        assert snap["double_revision"]["representations_for_cv2"] == 1

    def test_every_revision_has_exactly_one_content_version(
        self, snap: dict[str, Any]
    ) -> None:
        """`uq_wpcv_wp_revision` 的行为判据：revision → version 是一对一。"""
        histogram = snap["double_revision"]["revision_histogram"]
        assert histogram, histogram
        assert all(count == 1 for count in histogram.values()), histogram
        assert sorted(histogram) == list(range(len(histogram))), (
            f"revision 序列出现空洞或重复: {sorted(histogram)}"
        )


class TestRollbackLeavesInvisibleOrphan:
    """Requirement 2.4 / Property 5：失败后 pointer/revision 不变，文件是不可见 orphan。"""

    def test_pointer_and_revision_unchanged(self, snap: dict[str, Any]) -> None:
        before, after = snap["rollback"]["before"], snap["rollback"]["after"]
        assert after["content_revision"] == before["content_revision"]
        assert after["current_content_version_id"] == before["current_content_version_id"]
        assert after["pointer_representation_id"] == before["pointer_representation_id"]
        assert after["pointer_generation"] == before["pointer_generation"]

    def test_no_new_rows_survived(self, snap: dict[str, Any]) -> None:
        before, after = snap["rollback"]["before"], snap["rollback"]["after"]
        assert after["counts"] == before["counts"], (
            f"失败的 commit 留下了可见行: {before['counts']} → {after['counts']}"
        )

    def test_no_commit_happened(self, snap: dict[str, Any]) -> None:
        assert snap["rollback"]["commit_count_observed"] == 0

    def test_published_file_survives_as_unreferenced_orphan(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 文件确实留在磁盘上，但零 DB 行引用它 —— 这是设计承诺，不是缺陷。

        「宁可留垃圾文件，也不留 pointer 指向缺失 artifact 的半成功态」
        （Requirement 2.4：事务失败的 artifact 不可见并由 orphan GC 清理）。
        """
        assert snap["rollback"]["new_files_on_disk"], (
            "失败路径连 staged/published 文件都没产生 ⇒ 判据不可达"
            "（说明失败发生在 publish 之前，那样测不到 orphan 语义）"
        )
        assert snap["rollback"]["orphan_rows_referencing_new_file"] == 0


class TestOutboxInSameTransaction:
    """Requirement 13.1：outbox 与 pointer 同事务写入，事件只在 commit 后发布。"""

    def test_outbox_row_exists_after_commit_but_unpublished(
        self, snap: dict[str, Any]
    ) -> None:
        row = snap["outbox"]["after_commit"]
        assert row["event_type"] == "workpaper.content.updated"
        assert row["status"] == "pending", (
            "outbox 行在业务事务里就被标 published ⇒ 事件早于 commit 发布"
        )
        assert row["published_at_set"] is False
        assert row["payload_has_revision"] is True

    def test_publish_after_commit_marks_the_row(self, snap: dict[str, Any]) -> None:
        report = snap["outbox"]["publish_report"]
        assert report["attempted"] == 1, report
        assert report["rolled_back"] == 0, report
        after = snap["outbox"]["after_publish"]
        assert after["status"] in ("published", "failed"), after
        if after["status"] == "published":
            assert after["published_at_set"] is True
        else:
            # 失败也必须是**耐久**的（worker 可重放），不得静默丢失
            assert after["attempt_count"] >= 1, after

    def test_event_payload_binds_the_full_identity(self, snap: dict[str, Any]) -> None:
        """AC 8.12：applied version 同时绑定 projection hash 与 representation/bundle identity。"""
        payload = snap["business_commit"]["event_payload"]
        for key in (
            "wp_id", "project_id", "revision", "operation_id", "source", "adapter_id",
            "file_sha256", "content_version_id", "projection_sha256",
            "representation_id", "representation_generation",
            "definition_bundle_id", "definition_bundle_sha256", "authority_model",
        ):
            assert payload.get(key) is not None, f"事件 payload 缺 {key}: {payload}"
        assert payload["content_revision_advanced"] is True
        assert payload["revision"] == 1


class TestProperty10Idempotency:
    """相同 pending mutation token 重放返回同 version，且不产生第二个 revision。"""

    def test_first_commit_consumed_the_token(self, snap: dict[str, Any]) -> None:
        row = snap["idempotency"]["token_row"]
        assert row["state"] == "committed", row
        assert row["cv"] == snap["idempotency"]["first"]["content_version_id"]
        assert row["op"] is not None and row["done"] is True

    def test_replay_returns_the_same_version_without_new_revision(
        self, snap: dict[str, Any]
    ) -> None:
        first, replay = snap["idempotency"]["first"], snap["idempotency"]["replay"]
        assert "error" not in replay, replay
        assert replay["replayed"] is True
        assert replay["content_version_id"] == first["content_version_id"]
        assert replay["revision"] == first["revision"]
        assert snap["idempotency"]["revision_after_replay"] == first["revision"], (
            "重放推进了 revision ⇒ 幂等失效（Property 10）"
        )
        assert snap["idempotency"]["replay_commit_count"] == 0, (
            "重放路径不该产生任何数据库提交"
        )

    @pytest.mark.parametrize(
        ("label", "prefix", "phrase"),
        [
            ("cross_wp", "PendingMutationScopeError", "跨 scope"),
            ("cross_entry", "PendingMutationScopeError", OTHER_WP_ENTRY),
            ("expired", "PendingMutationExpiredError", "已过期"),
            ("wrong_base", "PendingMutationPayloadError", "content base"),
        ],
    )
    def test_each_rejection_has_its_own_type_and_message(
        self, snap: dict[str, Any], label: str, prefix: str, phrase: str
    ) -> None:
        """🔴 四条拒绝各自类型 + 各自文案：共用类型时短路一条会被另几条遮蔽。

        `cross_wp` 与 `cross_entry` 刻意分开：scope 判据是 project/wp/entry 三个独立
        合取项，只用「wp 与 entry 同时不同」的一条 token 时，短路 entry 那一项仍被 wp
        拦住 ⇒ 异常类型与文案都不变 ⇒ 变异判 GREEN（M25 实测过）。`cross_entry` 断言
        文案里出现**越界的那个 entry**，因此 entry 合取项被短路时它必红（拒绝理由会
        退化成下一条 `PendingMutationPayloadError`）。
        """
        got = snap["pending_rejections"][label]
        assert got.startswith(prefix), f"{label}: {got}"
        assert phrase in got, f"{label} 命中的不是自己那条判据: {got}"


class TestRepresentationFinalizeIsAdditiveOnly:
    """Property 4 / 67：纯表示 finalize 只加 generation，不推 revision、不改旧 row。"""

    def test_finalize_succeeded(self, snap: dict[str, Any]) -> None:
        outcome = snap["finalize"]["outcome"]
        assert "error" not in outcome, outcome
        assert outcome["revision_unchanged"] is True

    def test_new_generation_bound_to_the_same_content_version(
        self, snap: dict[str, Any]
    ) -> None:
        outcome = snap["finalize"]["outcome"]
        before, after = snap["finalize"]["before"], snap["finalize"]["after"]
        assert (
            after["counts"]["working_paper_content_representation"]
            == before["counts"]["working_paper_content_representation"] + 1
        )
        assert (
            after["counts"]["working_paper_content_version"]
            == before["counts"]["working_paper_content_version"]
        ), "纯表示升级竟新增了 content version"
        assert outcome["representation_generation"] >= 2
        assert outcome["content_version_id"] == snap["world"]["cv3"]

    def test_revision_and_old_rows_untouched(self, snap: dict[str, Any]) -> None:
        before, after = snap["finalize"]["before"], snap["finalize"]["after"]
        assert after["content_revision"] == before["content_revision"], (
            f"纯表示 finalize 推进了 business revision: "
            f"{before['content_revision']} → {after['content_revision']}"
        )
        assert after["current_content_version_id"] == before["current_content_version_id"]
        assert after["file_version"] == before["file_version"]
        assert after["old_representation_row"] == before["old_representation_row"], (
            "旧 representation row 被 finalize 改动（immutable 承诺被破）"
        )
        assert after["old_content_version_row"] == before["old_content_version_row"]

    def test_entry_pointer_moved_to_the_new_generation(self, snap: dict[str, Any]) -> None:
        before, after = snap["finalize"]["before"], snap["finalize"]["after"]
        outcome = snap["finalize"]["outcome"]
        assert after["pointer_representation_id"] == outcome["representation_id"]
        assert after["pointer_generation"] == outcome["representation_generation"]
        assert after["pointer_representation_id"] != before["pointer_representation_id"]

    def test_candidate_row_records_the_finalized_representation(
        self, snap: dict[str, Any]
    ) -> None:
        row = snap["finalize"]["candidate_row"]
        assert row["state"] == "finalized"
        assert row["rep"] == snap["finalize"]["outcome"]["representation_id"]
        assert row["done"] is True

    def test_new_representation_is_recorded_as_definition_upgrade(
        self, snap: dict[str, Any]
    ) -> None:
        """`reason` 必须是 `definition_upgrade`，不得记成 `content_commit`。

        记错 reason 会让审计轨迹里「这一代是业务改动还是隐形模板升级」永久分不开 ——
        而 revision 恰好相同，事后无法从数字上区分。
        """
        row = snap["finalize"]["new_representation_row"]
        assert row["reason"] == "definition_upgrade", row
        assert row["cv"] == snap["world"]["cv3"], row
        assert row["parent"] == snap["world"]["rep3"], (
            "新 generation 必须挂在 candidate 的 source representation 之下（可追溯链）"
        )

    def test_finalize_is_one_transaction(self, snap: dict[str, Any]) -> None:
        assert len(snap["finalize"]["distinct_xmin"]) == 1, snap["finalize"]["xmin"]
        assert snap["finalize"]["commit_count_observed"] == 1
        assert len(snap["finalize"]["outcome"]["transaction_ids"]) == 1

    def test_upgrade_event_declares_revision_unchanged(self, snap: dict[str, Any]) -> None:
        """纯表示升级的事件必须自报 revision 没变，否则下游会当业务改动去刷新。"""
        event = snap["finalize"]["upgrade_event"]
        assert event["event_type"] == "workpaper.content.updated"
        assert '"content_revision_advanced": false' in event["payload"].replace(
            '"content_revision_advanced":false', '"content_revision_advanced": false'
        ), event["payload"]

    def test_resolver_switches_to_the_new_generation_at_same_revision(
        self, snap: dict[str, Any]
    ) -> None:
        """canonical resolver 看到新 generation，但 content revision 不变（Property 4）。"""
        before = snap["resolver_view"]["before_finalize"]
        after = snap["resolver_view"]["after_finalize"]
        assert after["generation"] > before["generation"]
        assert after["revision"] == before["revision"], (
            "resolver 看到的 content revision 随纯表示升级变化 ⇒ 两个域没有正交"
        )


class TestFinalizeGate:
    """Property 67：未 ready 的 candidate 不得 finalize，且失败后什么都不变。"""

    def test_not_ready_candidate_is_rejected(self, snap: dict[str, Any]) -> None:
        got = snap["finalize_gate"]["not_ready"]
        assert got.startswith("CandidateNotFinalizableError"), got
        assert "contract" in got

    def test_failed_finalize_changes_nothing(self, snap: dict[str, Any]) -> None:
        before, after = snap["finalize_gate"]["before"], snap["finalize_gate"]["after"]
        assert after["content_revision"] == before["content_revision"]
        assert after["pointer_representation_id"] == before["pointer_representation_id"]
        assert after["counts"] == before["counts"]

    def test_candidate_is_invisible_to_the_resolver_before_finalize(
        self, snap: dict[str, Any]
    ) -> None:
        """candidate 存在但 resolver 仍返回既有 published generation（Requirement 6.18）。"""
        view = snap["resolver_view"]["before_finalize"]
        assert view["representation_id"] != snap["world"].get("candidate")
        assert view["generation"] >= 1

    def test_unapproved_bundle_is_not_loadable(self, snap: dict[str, Any]) -> None:
        got = snap["finalize_gate"]["unapproved_bundle"]
        assert got != "NO ERROR"
        assert got.startswith("BundleIntegrityError"), got

    def test_foreign_candidate_scenarios_are_isolated(self, snap: dict[str, Any]) -> None:
        """孪生 candidate 必须「同 digest、异路径」，否则下一条测不出路径判据。"""
        assert snap["finalize_gate"]["twin_same_digest"] is True, (
            "孪生 candidate 的 digest 与原 candidate 不同 —— 两条判据又互相遮蔽了，"
            "`_ooxml` 的 zip 时间戳非确定，载荷必须复用同一份 bytes"
        )

    @pytest.mark.parametrize(
        ("label", "phrase"),
        [("foreign_path", "relative_path"), ("forged_digest", "digest")],
    )
    def test_foreign_candidate_artifact_is_rejected(
        self, snap: dict[str, Any], label: str, phrase: str
    ) -> None:
        """🔴 喂不属于本 candidate 的 staged artifact 必须被拒，且两条判据各自可 falsify。

        candidate 此时已 `ready`（contract/bundle/等值报告都补齐），所以唯一可拒绝的
        理由就是「staged artifact 身份与 DB 登记的 relative_path/digest 不符」。它挡的
        正是「representation 的 artifact 与等值报告对不上」这类事后无法发现的错配。

        两个场景刻意把两条判据拆开（`foreign_path` 同字节异路径、`forged_digest` 真路径
        伪 digest）：只喂「另一份 candidate 的字节」时两者同时不符，短路任一条另一条都
        会顶上来、异常类型与文案都不变 ⇒ 变异判 GREEN（M30 首轮实测过）。
        """
        got = snap["finalize_gate"][label]
        assert got != "NO ERROR", (
            f"{label}: 喂了不属于本 candidate 的 artifact 竟然 finalize 成功 —— "
            "artifact 身份判据失守"
        )
        assert got.startswith("RepresentationPointerError"), got
        assert phrase in got, f"{label} 命中的不是自己那条判据: {got}"


class TestRoomBaselines:
    """AC 2.9 / 8.12：server last-applied 每次推进；merged≠incoming ⇒ refresh_required。"""

    def test_room_commit_succeeded(self, snap: dict[str, Any]) -> None:
        receipt = snap["room"]["receipt"]
        assert "error" not in receipt, receipt
        assert receipt["requires_client_refresh"] is True, (
            "merged 与 incoming 不等值时必须要求编辑器确认新基线"
        )

    def test_server_last_applied_advanced(self, snap: dict[str, Any]) -> None:
        row = snap["room"]["row"]
        assert row["applied"] == snap["room"]["receipt"]["content_version_id"], row

    def test_client_confirmed_base_did_not_advance(self, snap: dict[str, Any]) -> None:
        """🔴 服务端合并结果**不得**冒充编辑器已加载的基线（AC 2.9 的核心）。"""
        assert snap["room"]["row"]["confirmed"] is None, snap["room"]["row"]

    def test_room_entered_refresh_required_with_a_reason(
        self, snap: dict[str, Any]
    ) -> None:
        """refresh 必须留下原因与时间 —— 静默 refresh 让审计师查不到为什么要重开。"""
        row = snap["room"]["row"]
        assert row["state"] == "refresh_required", row
        assert row["refresh_reason"] == "merged_projection_differs_from_incoming", row
        assert row["refresh_stamped"] is True, row


class TestCustomAuthoritativePath:
    """Requirement 2.11 / 6.19：custom 保持 xlsx 单一权威，但仍进统一协议。"""

    def test_custom_commit_succeeded(self, snap: dict[str, Any]) -> None:
        receipt = snap["custom_authoritative"]["receipt"]
        assert "error" not in receipt, receipt
        assert receipt["authority_model"] == "custom_authoritative_ooxml"
        assert receipt["projection_sha256"] is None, (
            "custom 底稿被标准结构化 JSON projection writer 改写了（Requirement 2.11）"
        )

    def test_content_version_binds_authoritative_artifact(self, snap: dict[str, Any]) -> None:
        row = snap["custom_authoritative"]["version_row"]
        assert row["proj"] is None
        assert row["auth"] is not None
        assert row["source"] == "custom"

    def test_custom_commit_still_advances_revision_once(self, snap: dict[str, Any]) -> None:
        """custom 权威文件内容变化**是**业务内容变化 ⇒ 必须推进 revision（AC 2.1）。"""
        finalize_after = snap["finalize"]["after"]["content_revision"]
        assert snap["custom_authoritative"]["receipt"]["revision"] == finalize_after + 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
