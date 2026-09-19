# -*- coding: utf-8 -*-
"""Task 27 真实 PostgreSQL 行为守卫：冲突预览、resolve fence 五判定、retry 与 rollback。
spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 27
Requirements: 6.18, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12, 10.10
Properties: **P35 / P36 / P37 / P38 / P43 / P65 / P67**

═══ 为什么必须真库 ═══

Task 27 的判据几乎全是跨表跨事务的：

* **P35** —— 冲突行必须真的落在 `working_paper_sync_conflict` 上，且预览能把它与
  application 冻结的 bundle/authority model、room generation、current revision 拼成一份
  可下钻的响应。只记 `conflict_count/digest` 两个标量时离线断言不出「预览没有数据可读」。
* **P36** —— fence 的五种判定各自要求不同的**服务端真值组合**（room generation、
  write fence、latest durable application/sequence、conflict digest、current revision）。
  它们全在 DB 行上，离线只能测纯函数（那已在 Task 14 覆盖）；本文件测的是
  「服务端有没有把对的真值读出来喂给判据」—— 接线错了纯函数照样绿。
* **P37 / P67** —— rollback 必须**创建新版本**（revision 严格增大、历史行与文件仍在），
  而业务 projection 未变化时**零写入**。两者都是行计数与 pointer 判据。
* **P38** —— retry 不新建 operation/application：判据是行计数。
* **P65** —— 落库 projection digest 必须等于折叠结果、不等于 `merge.merged`。

`DATABASE_URL` 非 PostgreSQL 时**直接失败而不是 skip** —— 与 Task 10/15/21~26 同约定：
skip 等于静默抹掉本任务唯一判据。

═══ 隔离与采集 ═══

scratch schema `tmp_task27_cr_<hex>` + 独立文件根 `tmp_task27_store_*`，结束
`DROP SCHEMA CASCADE` + `rmtree`。全部场景由**一次 `asyncio.run`** 跑完落进快照
（module fixture）。采集阶段异常一律**记录不穿透**：异常穿透会把整个 module 变成
collection ERROR，而 `-rf` 只列 FAILED 不列 ERROR ⇒ 定向变异看不到预期失败项 ⇒ 判 GREEN。
`test_no_phase_crashed_during_collection` 是这个决定的另一半。
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
import uuid
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
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

_SCHEMA_PREFIX = "tmp_task27_cr_"
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
PERIOD = "header_block/period_label"
TOTAL = "header_block/total_amount"
ROWS = "ar_rows/{row_uuid}/amount"
_CONTENT_TYPES = (
    b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/'
    b'2006/content-types"><Default Extension="xml" ContentType="application/xml"/>'
    b'<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats'
    b'-officedocument.spreadsheetml.sheet.main+xml"/></Types>'
)


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _opt(value: object) -> str | None:
    """可空 UUID → `str | None`。`str(None) == "None"` 会把「没写上」判成「写上了」。"""
    return None if value is None else str(value)


def _err(exc: BaseException) -> str:
    import traceback

    frames = traceback.extract_tb(exc.__traceback__)[-6:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


#: 固定 zip 条目时间戳（ZIP 格式最早可表示 1980-01-01）。
#:
#: 🔴 为什么必须固定（2026-08-28 实测代价）：`zf.writestr("name", data)` 会用
#: `time.localtime()` 现场构造 `ZipInfo`，**秒级**粒度进入 zip 头 ⇒ 同一份内容在不同
#: 秒写出来字节不同、sha256 不同。本文件有两处判据依赖「同内容 ⇒ 同字节」：
#:   * `resolve_via_duplicate`：同 payload 的第二个 delivery 必须命中同一 application key；
#:   * `rollback`：重新 materialize 出的 representation 必须与历史那一份**逐字节相同**，
#:     才会走到 `register_artifact` 的内容寻址幂等分支（R02 变异守的正是这条）。
#: 不固定时这两条都只在「两次调用恰好同秒」时成立 —— R02 实测因此在慢跑里翻 GREEN，
#: 而那是**判据靠运气**，不是守卫或生产代码的问题。
_ZIP_EPOCH: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0)


def _zip_entry(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def _ooxml(*, projection_values: dict[str, Any], unmanaged: bytes = b"<formulas/>") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(_zip_entry("[Content_Types].xml"), _CONTENT_TYPES)
        zf.writestr(_zip_entry("xl/workbook.xml"), b'<?xml version="1.0"?><root/>')
        zf.writestr(_zip_entry("xl/unmanaged.xml"), unmanaged)
        zf.writestr(
            _zip_entry("_gt_sync/projection.json"),
            json.dumps(
                {"contract_id": ENTRY, "values": projection_values},
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8"),
        )
    return buf.getvalue()


def _enum_ddl(tables: list[sa.Table]) -> list[str]:
    seen: dict[str, tuple[str, ...]] = {}
    for table in tables:
        for column in table.columns:
            if isinstance(column.type, sa.Enum) and column.type.name:
                seen.setdefault(column.type.name, tuple(column.type.enums))
    return [
        "CREATE TYPE {name} AS ENUM ({labels})".format(
            name=name, labels=", ".join(f"'{label}'" for label in labels)
        )
        for name, labels in sorted(seen.items())
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 契约与 adapter 替身（真写真读；不是 mock）
# ═══════════════════════════════════════════════════════════════════════════


def _contract_payload(*, contract_id: str = ENTRY) -> dict[str, Any]:
    from app.services.workpaper_sync import contracts as C

    return {
        "schema_version": C.CONTRACT_SCHEMA_VERSION,
        "contract_id": contract_id,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": _d("task27-template"),
        "instrumentation_definition_sha256": _d("task27-instrumentation"),
        "template": {
            "relative_path": "D/D2 应收账款.xlsx",
            "template_sha256": _d("task27-template-blob"),
            "normalized_structure_hash": _d("task27-template-structure"),
        },
        "identity_carriers": ["hidden_sheet", "defined_name", "hidden_uuid_column"],
        "sheets": [
            {
                "sheet_key": "d2-detail",
                "excel_name": "D2 明细",
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
                    },
                    {
                        "table_key": "ar_rows",
                        "anchor": "A10",
                        "header_rows": 1,
                        "row_identity": {"kind": "field", "json_pointer": "/rows/*/rowUuid"},
                        "delete_policy": "tombstone",
                        "fields": [
                            {
                                "stable_field_key": ROWS,
                                "json_pointer": "/rows/{row_uuid}/amount",
                                "column_key": "amount",
                                "cell": {"column": "C", "row_from": "row_identity"},
                                "mode": "editable",
                                "value_type": "amount",
                                "source_ref": "源xlsx!C11",
                            }
                        ],
                    },
                ],
            }
        ],
    }


class _JsonCarrierAdapter:
    """真 OOXML 容器 + JSON 受管部件的载体替身（与 Task 15/26 PG 守卫同形）。

    `materialize` 真写 zip、`extract` 真读回来 ⇒ roundtrip 等值判据在真实执行上生效。
    """

    adapter_id = ENTRY
    document_type = "xlsx"
    contract_version = "1.0.0"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def read_current_projection(self, ctx):  # pragma: no cover - 本任务不用
        raise NotImplementedError

    async def stage_projection_mutation(self, ctx, merged, *, expected_revision):
        raise NotImplementedError  # pragma: no cover - 本任务不用

    def materialize(self, *, substrate, projection, output, contract):
        from app.services.workpaper_sync.adapters.base import MaterializeResult

        self.calls.append("materialize")
        values = {
            key: {
                "value": (str(v.value) if isinstance(v.value, Decimal) else v.value),
                "value_type": v.value_type.value,
                "mode": v.mode.value,
                "row_key": v.row_key,
            }
            for key, v in projection.values.items()
        }
        blob = _ooxml(projection_values=values)
        Path(output).write_bytes(blob)
        return MaterializeResult(
            output_path=Path(output),
            document_type=projection.document_type,
            artifact_sha256=hashlib.sha256(blob).hexdigest(),
            structure_hash=_d("task27-structure"),
            identity_inventory_sha256=_d("task27-identity"),
            managed_field_count=len(values),
        )

    def extract(self, *, artifact, contract):
        from app.services.workpaper_sync import contracts as C
        from app.services.workpaper_sync.adapters.base import FieldValue, Projection

        self.calls.append(f"extract:{Path(artifact).name}")
        with zipfile.ZipFile(artifact) as zf:
            raw = json.loads(zf.read("_gt_sync/projection.json").decode("utf-8"))
        values: dict[str, FieldValue] = {}
        row_keys: dict[str, list[str]] = {}
        for key, item in raw["values"].items():
            vt = C.ValueType(item["value_type"])
            value = item["value"]
            if vt is C.ValueType.amount and value is not None:
                value = Decimal(str(value))
            row_key = item.get("row_key")
            values[key] = FieldValue(
                stable_key=key,
                value=value,
                value_type=vt,
                mode=C.FieldMode(item["mode"]),
                row_key=row_key,
            )
            if row_key:
                row_keys.setdefault(key.split("/")[0], []).append(row_key)
        return Projection(
            contract_id=raw["contract_id"],
            semantic_version=contract.semantic_version,
            document_type=contract.document_type,
            values=values,
            row_keys={k: tuple(v) for k, v in row_keys.items()},
        )

    def verify_unmanaged_regions(self, *, before, after, contract):
        from app.services.workpaper_sync.adapters.base import UnmanagedRegionReport

        self.calls.append("verify_unmanaged_regions")
        with zipfile.ZipFile(before) as zb, zipfile.ZipFile(after) as za:
            same = zb.read("xl/unmanaged.xml") == za.read("xl/unmanaged.xml")
        return UnmanagedRegionReport(
            equivalent=same,
            inspected_aspects=("formula", "style", "drawing", "chart"),
            first_difference=None if same else "xl/unmanaged.xml",
        )


class _RecordingProbe:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def observe(self, *, project_id, wp_id, entry_id):
        self.calls.append(str(wp_id))
        return {"project_visible": True, "workflow_locked": False}


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
        WorkpaperArtifact,
        WorkpaperContentApplication,
        WorkpaperContentRepresentation,
        WorkpaperContentVersion,
        WorkpaperOoRoom,
        WorkpaperSyncEntryState,
        WorkpaperSyncOperation,
    )
    from app.services.workpaper_sync import conflict_resolution as CR
    from app.services.workpaper_sync import conflicts as CF
    from app.services.workpaper_sync import contracts as C
    from app.services.workpaper_sync import definitions as D
    from app.services.workpaper_sync import merge as M
    from app.services.workpaper_sync import oo_to_html as OH
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.content_mutation import (
        ContentMutationService,
        projection_canonical_digest,
    )
    from app.services.workpaper_sync.models import (
        ArtifactKind,
        ArtifactState,
        BundleSlot,
        ParticipantMode,
        ScopeResourceKind,
        compute_application_key,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.request_application import RequestApplicationService
    from app.services.workpaper_sync.resolution import CanonicalResolutionService
    from app.services.workpaper_sync.rooms import RoomScope, RoomService, mint_route_credential

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 27 的判据是跨表跨事务的（冲突落行、fence 真值组合、rollback 行计数），"
            f"必须真实 PostgreSQL；当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task27_store_"))
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

        outbox_tables = [ImportEventOutbox.__table__, ImportEventConsumption.__table__]
        async with engine.begin() as conn:
            for stmt in _enum_ddl(outbox_tables):
                await conn.exec_driver_sql(stmt)
            await conn.run_sync(
                lambda sync_conn: ImportEventOutbox.metadata.create_all(
                    sync_conn, tables=outbox_tables, checkfirst=True
                )
            )

        project = uuid.uuid4()
        user_a, user_b = uuid.uuid4(), uuid.uuid4()
        artifacts = CanonicalArtifactRepository(base_root)
        contract = C.parse_contract(_contract_payload())
        other_contract = C.parse_contract(_contract_payload(contract_id="xlsx/other"))

        defs_wp = uuid.uuid4()
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{project}')")
            for u in (user_a, user_b):
                await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{u}')")
            await conn.exec_driver_sql(
                "INSERT INTO working_paper (id, project_id) VALUES "
                f"('{defs_wp}', '{project}')"
            )

        blobs = {
            name: artifacts.publish_definition_blob(
                project_id=project,
                wp_id=defs_wp,
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

        world: dict[str, Any] = {}
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            art = {
                name: await repo.register_artifact(
                    project_id=project,
                    wp_id=defs_wp,
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
                kind="template", logical_id="task27.tpl", semantic_version="1.0.0",
                blob_artifact_id=art["tpl"].id, sha256=_d("task27-template"),
                structure_hash=_d("task27-tpl-structure"), source_commit="task27",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation", logical_id="task27.instr",
                semantic_version="1.0.0", blob_artifact_id=art["instr"].id,
                sha256=_d("task27-instrumentation"),
                structure_hash=_d("task27-instr-structure"), source_commit="task27",
            )
            contract_def = await repo.create_definition_artifact(
                kind="contract", logical_id="task27.contract", semantic_version="1.0.0",
                blob_artifact_id=art["contract"].id,
                sha256=contract.canonical_sha256, source_commit="task27",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task27.authority",
                semantic_version="1.0.0", blob_artifact_id=art["authority"].id,
                sha256=_d("task27-authority"),
                authority_model_type="projection_contract", source_commit="task27",
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
        snap["world"] = {k: str(v) for k, v in world.items()}

        def _projection(values: dict[str, Any]) -> Projection:
            fields: dict[str, FieldValue] = {}
            row_keys: dict[str, list[str]] = {}
            for key, raw in values.items():
                if key.startswith("ar_rows/"):
                    _t, row_uuid, _leaf = key.split("/")
                    spec = contract.field_by_stable_key(ROWS)
                    fields[key] = FieldValue(
                        stable_key=key, value=raw, value_type=spec.value_type,
                        mode=spec.mode, row_key=row_uuid,
                    )
                    row_keys.setdefault("ar_rows", []).append(row_uuid)
                    continue
                spec = contract.field_by_stable_key(key)
                fields[key] = FieldValue(
                    stable_key=key, value=raw,
                    value_type=spec.value_type, mode=spec.mode,
                )
            return Projection(
                contract_id=contract.contract_id,
                semantic_version=contract.semantic_version,
                document_type=contract.document_type,
                values=fields,
                row_keys={k: tuple(v) for k, v in row_keys.items()},
            )

        def _carrier_values(projection: Projection) -> dict[str, Any]:
            return {
                key: {
                    "value": (str(v.value) if isinstance(v.value, Decimal) else v.value),
                    "value_type": v.value_type.value,
                    "mode": v.mode.value,
                    "row_key": v.row_key,
                }
                for key, v in projection.values.items()
            }

        async def _build_entry(tag: str, base_values: dict[str, Any]) -> dict[str, Any]:
            wp = uuid.uuid4()
            async with engine.begin() as conn:
                await conn.exec_driver_sql(
                    "INSERT INTO working_paper (id, project_id) VALUES "
                    f"('{wp}', '{project}')"
                )
            base_projection = _projection(base_values)
            rep_bytes = _ooxml(projection_values=_carrier_values(base_projection))
            gen1 = artifacts.publish_representation(
                entry_id=ENTRY,
                generation=1,
                staged=artifacts.stage_bytes(
                    project_id=project, wp_id=wp, payload=rep_bytes, document_type="xlsx"
                ),
            )
            proj_digest = projection_canonical_digest(base_projection)
            proj0 = artifacts.publish_projection(
                revision=0,
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
                    sha256=gen1.sha256, size_bytes=gen1.size_bytes, document_type="xlsx",
                )
                art_proj = await repo.register_artifact(
                    project_id=project, wp_id=wp, kind=ArtifactKind.projection,
                    state=ArtifactState.published, relative_path=proj0.relative_path,
                    sha256=proj0.sha256, size_bytes=proj0.size_bytes,
                    document_type="json.gz",
                )
                cv0 = await repo.create_content_version(
                    project_id=project, wp_id=wp, entry_id=ENTRY, revision=0,
                    source="html", projection_artifact_id=art_proj.id,
                    projection_sha256=proj_digest, actor_id=user_a,
                )
                rep1 = await repo.create_representation(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    content_version_id=cv0.id, generation=1, document_type="xlsx",
                    artifact_id=art_rep.id, artifact_sha256=art_rep.sha256,
                    definition_bundle_id=world["bundle"],
                    authority_model_definition_id=world["authority"],
                    adapter_id=ENTRY, adapter_build_digest=_d("task27-adapter"),
                    structure_hash=_d(f"task27-structure-{tag}"),
                    identity_inventory_sha256=_d(f"task27-identity-{tag}"),
                    reason="content_commit",
                )
                # scope row 由 `create_content_version` 同事务写（不能在这里补第二条：
                # `uq_wpssi_resource` 永不复用，重复注册直接 ScopeIntegrityError）。
                await repo.set_entry_pointer(
                    wp_id=wp, entry_id=ENTRY, representation_id=rep1.id, generation=1
                )
                await repo.set_current_content_version(wp, cv0.id)
                await s.commit()
            return {
                "wp": wp,
                "cv0": cv0.id,
                "rep1": rep1.id,
                "projection_sha256": proj_digest,
                "base_projection": base_projection,
                "rep_rel": gen1.relative_path,
            }

        async def _build_room(entry: dict[str, Any]) -> dict[str, Any]:
            scope = RoomScope(project_id=project, wp_id=entry["wp"], entry_id=ENTRY)
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                svc = RoomService(repo)
                room, _frozen = await svc.open_or_reuse_room(
                    scope,
                    representation=(
                        await s.execute(
                            sa.select(WorkpaperContentRepresentation).where(
                                WorkpaperContentRepresentation.id == entry["rep1"]
                            )
                        )
                    ).scalar_one(),
                    opened_base_version_id=entry["cv0"],
                )
                pa = await svc.join_participant(
                    scope, room_id=room.id, user_id=user_a,
                    mode=ParticipantMode.edit, permission_epoch=5, lease_token="lease-a",
                )
                frozen = await svc.frozen_bundle_identity(world["bundle"])
                conf = await svc.confirm_descriptor(
                    scope, room_id=room.id, participant_id=pa.id,
                    representation_id=entry["rep1"], content_version_id=entry["cv0"],
                    projection_sha256=entry["projection_sha256"],
                    idempotency_key=f"ready-{room.id}", expected_bundle=frozen,
                )
                await s.commit()
                return {
                    "scope": scope,
                    "room": room.id,
                    "doc_key": room.doc_key,
                    "participant": pa.id,
                    "confirmation": conf[0].id if isinstance(conf, tuple) else conf.id,
                }

        async def _accept_request(env: dict[str, Any], *, key: str) -> dict[str, Any]:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                ras = RequestApplicationService(repo)
                accepted = await ras.freeze_and_persist_request(
                    env["scope"],
                    room_id=env["room"],
                    participant_id=env["participant"],
                    idempotency_key=key,
                    client_edit_epoch=3,
                    contributor_user_ids=[user_a],
                    created_by=user_a,
                )
                rooms = RoomService(repo)
                cred = mint_route_credential(
                    room_id=env["room"], generation=1, doc_key=env["doc_key"]
                )
                await rooms.record_contributor_snapshot(
                    operation_id=accepted.operation.id,
                    room_id=env["room"],
                    initiator_participant_id=env["participant"],
                    route_credential=cred,
                    oo_contributor_user_ids=[],
                )
                await s.commit()
                return {
                    "request": accepted.request.id,
                    "operation": accepted.operation.id,
                    "sequence": accepted.request_sequence,
                    "credential": cred,
                }

        async def _seal_incoming(
            env: dict[str, Any], entry: dict[str, Any], req: dict[str, Any],
            *, payload: bytes,
        ) -> dict[str, Any]:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                delivery = await repo.record_delivery(
                    project_id=project, wp_id=entry["wp"], entry_id=ENTRY,
                    room_id=env["room"], generation=1,
                    route_credential_id=req["credential"].credential_id,
                    callback_status=6,
                    delivery_key=_d(f"delivery-{uuid.uuid4()}"),
                    payload_sha256=_d(f"payload-{uuid.uuid4()}"),
                )
                await repo.mark_delivery_downloading(delivery_id=delivery.id)
                staged = artifacts.stage_incoming(
                    project_id=project, wp_id=entry["wp"], delivery_id=delivery.id,
                    chunks=[payload], document_type="xlsx",
                )
                sealed = artifacts.seal_incoming(staged, delivery_id=delivery.id)
                incoming = await repo.register_artifact(
                    project_id=project, wp_id=entry["wp"],
                    kind=ArtifactKind.incoming, state=sealed.state,
                    relative_path=sealed.relative_path, sha256=sealed.sha256,
                    size_bytes=sealed.size_bytes, document_type="xlsx",
                    source_delivery_id=delivery.id,
                )
                await s.commit()
                return {
                    "delivery": delivery.id,
                    "incoming": incoming.id,
                    "sha256": sealed.sha256,
                    "relative_path": sealed.relative_path,
                }

        async def _correlate(
            req: dict[str, Any], inc: dict[str, Any], *, current_revision: int = 0
        ) -> uuid.UUID:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                ras = RequestApplicationService(repo)
                outcome = await ras.correlate(
                    operation_id=req["operation"],
                    incoming_artifact_id=inc["incoming"],
                    current_revision=current_revision,
                    adapter_id=ENTRY,
                    delivery_id=inc["delivery"],
                )
                await s.commit()
                return outcome.application.id

        def _services(session, *, probe):
            repo = WorkpaperSyncRepository(session)
            resolution = CanonicalResolutionService(session, artifacts)
            content = ContentMutationService(
                session=session, repository=repo, artifacts=artifacts,
                resolution=resolution,
            )
            rooms = RoomService(repo)
            requests = RequestApplicationService(repo, rooms)
            coordinator = OH.OoToHtmlCoordinator(
                repo=repo, artifacts=artifacts, resolution=resolution,
                content=content, rooms=rooms, requests=requests, probe=probe,
            )
            return CR.ConflictResolutionService(
                repo=repo, resolution=resolution, content=content,
                requests=requests, coordinator=coordinator,
            ), coordinator

        async def _db_state(wp: uuid.UUID) -> dict[str, Any]:
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
                current_cv = (
                    await s.execute(
                        sa.text(
                            "SELECT current_content_version_id FROM working_paper "
                            "WHERE id = :w"
                        ),
                        {"w": wp},
                    )
                ).scalar_one_or_none()
                entry_state = (
                    await s.execute(
                        sa.select(WorkpaperSyncEntryState).where(
                            WorkpaperSyncEntryState.wp_id == wp,
                            WorkpaperSyncEntryState.entry_id == ENTRY,
                        )
                    )
                ).scalar_one_or_none()
                versions = (
                    (
                        await s.execute(
                            sa.select(WorkpaperContentVersion)
                            .where(WorkpaperContentVersion.wp_id == wp)
                            .order_by(WorkpaperContentVersion.revision)
                        )
                    )
                    .scalars()
                    .all()
                )
                reps = (
                    (
                        await s.execute(
                            sa.select(WorkpaperContentRepresentation)
                            .where(WorkpaperContentRepresentation.wp_id == wp)
                            .order_by(WorkpaperContentRepresentation.generation)
                        )
                    )
                    .scalars()
                    .all()
                )
                ops = (
                    (
                        await s.execute(
                            sa.select(WorkpaperSyncOperation).where(
                                WorkpaperSyncOperation.wp_id == wp
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                apps = (
                    (
                        await s.execute(
                            sa.select(WorkpaperContentApplication).where(
                                WorkpaperContentApplication.wp_id == wp
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                rooms_rows = (
                    (
                        await s.execute(
                            sa.select(WorkpaperOoRoom).where(WorkpaperOoRoom.wp_id == wp)
                        )
                    )
                    .scalars()
                    .all()
                )
                conflicts = (
                    (
                        await s.execute(
                            sa.text(
                                "SELECT c.stable_field_key, c.business_label, "
                                "  c.json_pointer, c.oo_location, c.conflict_kind, "
                                "  c.field_source, c.protection_policy, "
                                "  c.suggested_action, c.client_edit_epoch, "
                                "  c.effective_request_sequence, "
                                "  c.base_value::text, c.current_value::text, "
                                "  c.incoming_value::text, c.resolution::text, "
                                "  c.resolved_value::text, "
                                "  (c.resolved_by IS NOT NULL) AS has_actor, "
                                "  (c.resolved_at IS NOT NULL) AS has_time, "
                                "  (c.superseded_at IS NOT NULL) AS superseded "
                                "FROM working_paper_sync_conflict c "
                                "JOIN working_paper_sync_operation o "
                                "  ON o.id = c.operation_id "
                                "WHERE o.wp_id = :w "
                                "ORDER BY c.stable_field_key, c.row_key"
                            ),
                            {"w": wp},
                        )
                    )
                    .mappings()
                    .all()
                )
                return {
                    "revision": revision,
                    "current_content_version_id": _opt(current_cv),
                    "entry_pointer_representation_id": (
                        None if entry_state is None
                        else _opt(entry_state.current_representation_id)
                    ),
                    "version_count": len(versions),
                    "version_rows": [
                        {
                            "id": str(v.id),
                            "revision": int(v.revision),
                            "source": v.source,
                            "projection_sha256": v.projection_sha256,
                            "parent": _opt(v.parent_version_id),
                        }
                        for v in versions
                    ],
                    "representation_count": len(reps),
                    "representation_reasons": [r.reason for r in reps],
                    "operation_count": len(ops),
                    "application_count": len(apps),
                    "room_states": sorted(str(r.state) for r in rooms_rows),
                    "room_last_applied": sorted(
                        _opt(r.last_applied_version_id) or "" for r in rooms_rows
                    ),
                    "conflicts": [dict(row) for row in conflicts],
                }

        # ═══════════════════════════════════════════════════════════════
        # 场景装配器：一个 world = entry + room + request + durable incoming
        # ═══════════════════════════════════════════════════════════════

        async def _stage_world(
            tag: str,
            *,
            base_values: dict[str, Any],
            current_values: dict[str, Any] | None,
            incoming_values: dict[str, Any],
        ) -> dict[str, Any]:
            entry = await _build_entry(tag, base_values)
            # 🔴 顺序即真实故事：先开 room 并 confirm descriptor（于是 frozen client base
            # = gen1），**再**在服务器侧发布 gen2 当 current。反过来做时 room 的
            # client-confirmed 基线就等于 current，base 与 current 不可能分叉，
            # 三方 merge 退化成两方 —— 冲突根本造不出来。
            env = await _build_room(entry)
            req = await _accept_request(env, key=f"{tag}-fs")
            if current_values is not None:
                # 让服务端 current 与 frozen base 不同（三方 merge 的 current 侧）。
                cur = _projection(current_values)
                blob = _ooxml(projection_values=_carrier_values(cur))
                gen2 = artifacts.publish_representation(
                    entry_id=ENTRY, generation=2,
                    staged=artifacts.stage_bytes(
                        project_id=project, wp_id=entry["wp"], payload=blob,
                        document_type="xlsx",
                    ),
                )
                async with Session() as s:
                    repo = WorkpaperSyncRepository(s)
                    art2 = await repo.register_artifact(
                        project_id=project, wp_id=entry["wp"],
                        kind=ArtifactKind.canonical, state=ArtifactState.published,
                        relative_path=gen2.relative_path, sha256=gen2.sha256,
                        size_bytes=gen2.size_bytes, document_type="xlsx",
                    )
                    rep2 = await repo.create_representation(
                        project_id=project, wp_id=entry["wp"], entry_id=ENTRY,
                        content_version_id=entry["cv0"], generation=2,
                        document_type="xlsx", artifact_id=art2.id,
                        artifact_sha256=art2.sha256,
                        definition_bundle_id=world["bundle"],
                        authority_model_definition_id=world["authority"],
                        adapter_id=ENTRY,
                        adapter_build_digest=_d("task27-adapter"),
                        structure_hash=_d(f"task27-structure-{tag}-cur"),
                        identity_inventory_sha256=_d(f"task27-identity-{tag}-cur"),
                        reason="content_commit",
                    )
                    await repo.set_entry_pointer(
                        wp_id=entry["wp"], entry_id=ENTRY,
                        representation_id=rep2.id, generation=2,
                    )
                    await s.commit()
            # 🔴 payload 字节必须**保留**给调用方：`_ooxml()` 用 `zf.writestr(str, ...)`，
            # 其 `ZipInfo.date_time` 取 `time.localtime()`（秒级）⇒ 两次「同内容」调用跨过
            # 一个秒边界就得到不同字节、不同 sha256。需要「同一份 incoming 的第二个
            # delivery」（status 6/2 去重）的场景只能复用这一份字节，不能重新 `_ooxml()`。
            # 本轮实测代价：重新构造的版本连跑三次都碰巧同秒通过，直到整套变异跑慢下来
            # 才暴露 —— 典型的「靠运气的判据」。
            incoming_payload = _ooxml(
                projection_values=_carrier_values(_projection(incoming_values))
            )
            inc = await _seal_incoming(env, entry, req, payload=incoming_payload)
            app_id = await _correlate(req, inc)
            return {
                "entry": entry, "env": env, "req": req, "inc": inc, "app": app_id,
                "incoming_payload": incoming_payload,
            }

        def _choice_for(record) -> CF.ResolutionChoice:
            return CF.ResolutionChoice(
                stable_field_key=record.locator.stable_field_key,
                row_key=record.locator.row_key,
                oo_location=record.locator.oo_location,
                kind=CF.ResolutionKind.take_incoming,
            )

        async def _fence_for(
            world_ctx: dict[str, Any], **overrides: Any
        ) -> CF.ResolveFenceRequest:
            """从**服务端真值**构造一份「全部一致」的 fence，再按需覆盖某一项。

            这样每个拒绝场景只偏离一个字段 ⇒ 归因唯一（否则一次改两项时判不出是哪条
            判据在起作用）。
            """
            async with Session() as s:
                app = (
                    await s.execute(
                        sa.select(WorkpaperContentApplication).where(
                            WorkpaperContentApplication.id == world_ctx["app"]
                        )
                    )
                ).scalar_one()
                room = (
                    await s.execute(
                        sa.select(WorkpaperOoRoom).where(
                            WorkpaperOoRoom.id == world_ctx["env"]["room"]
                        )
                    )
                ).scalar_one()
                revision = int(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT content_revision FROM working_paper WHERE id = :w"
                            ),
                            {"w": world_ctx["entry"]["wp"]},
                        )
                    ).scalar_one()
                )
            payload: dict[str, Any] = {
                "expected_current_revision": revision,
                "room_generation": int(room.generation),
                "client_edit_epoch": int(app.client_edit_epoch),
                "canonical_application_id": app.id,
                "application_effective_request_sequence": int(
                    app.effective_request_sequence
                ),
                "room_latest_durable_application_id": room.latest_durable_application_id,
                "room_latest_durable_sequence": int(room.latest_durable_sequence or 0),
                "conflict_set_digest": str(app.conflict_set_digest or _d("empty")),
            }
            payload.update(overrides)
            return CF.ResolveFenceRequest(**payload)

        async def _dry_conflict(ctx: dict[str, Any]) -> Any:
            """先跑一次不带裁决的 apply ⇒ 冲突落行、application 停在 `conflict`。"""
            async with Session() as s:
                _svc, coord = _services(s, probe=_RecordingProbe())
                return await coord.apply_durable_incoming(
                    operation_id=ctx["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=ctx["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=_JsonCarrierAdapter(),
                    contract=contract,
                    actor_id=user_a,
                )

        _CONFLICT_WORLD = dict(
            base_values={PERIOD: "A", TOTAL: Decimal("1")},
            current_values={PERIOD: "B", TOTAL: Decimal("1")},
            incoming_values={PERIOD: "C", TOTAL: Decimal("1")},
        )

        # ═══ P1：冲突预览（AC 8.1 / 8.2 / Property 35）═══════════════════
        try:
            ctx = await _stage_world("preview", **_CONFLICT_WORLD)
            dry = await _dry_conflict(ctx)
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                preview = await svc.preview(
                    operation_id=ctx["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=ctx["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    contract=contract,
                )
            drift: str | None = None
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                try:
                    await svc.preview(
                        operation_id=ctx["req"]["operation"],
                        declared_project_id=project,
                        declared_wp_id=ctx["entry"]["wp"],
                        declared_entry_id=ENTRY,
                        contract=other_contract,
                    )
                except Exception as exc:  # noqa: BLE001
                    drift = getattr(exc, "error_code", type(exc).__name__)
            cross: str | None = None
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                try:
                    await svc.preview(
                        operation_id=ctx["req"]["operation"],
                        declared_project_id=project,
                        declared_wp_id=uuid.uuid4(),
                        declared_entry_id=ENTRY,
                        contract=contract,
                    )
                except Exception as exc:  # noqa: BLE001
                    cross = getattr(exc, "error_code", type(exc).__name__)
            snap["scenarios"]["preview"] = {
                "dry_result": dry.result.value,
                "dry_conflict_rows_written": dry.conflict_rows_written,
                "preview": preview.as_dict(),
                "bundle": str(world["bundle"]),
                "contract_digest": contract.canonical_sha256,
                "drift_error": drift,
                "cross_scope_error": cross,
                "db": await _db_state(ctx["entry"]["wp"]),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("preview", exc)

        # ═══ P2：resolve proceed ⇒ 折叠后发布 + 裁决轨迹（AC 8.3~8.6 / P36 / P65）═
        try:
            ctx = await _stage_world("resolve_ok", **_CONFLICT_WORLD)
            dry = await _dry_conflict(ctx)
            choice = _choice_for(dry.merge.conflicts.records[0])
            fence = await _fence_for(ctx)
            before = await _db_state(ctx["entry"]["wp"])
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                outcome = await svc.resolve(
                    operation_id=ctx["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=ctx["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    fence=fence,
                    resolutions=[choice],
                    adapter=_JsonCarrierAdapter(),
                    contract=contract,
                    actor_id=user_a,
                )
            snap["scenarios"]["resolve_ok"] = {
                "outcome": outcome.as_dict(),
                "folded_sha": projection_canonical_digest(
                    M.apply_resolutions(dry.merge, [choice], contract=contract)
                ),
                "merged_sha": projection_canonical_digest(dry.merge.merged),
                "before": before,
                "after": await _db_state(ctx["entry"]["wp"]),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("resolve_ok", exc)

        # ═══ P3：fence 拒绝（generation 变化）⇒ 零副作用（AC 8.5 / P43）═══
        try:
            ctx = await _stage_world("resolve_rejected", **_CONFLICT_WORLD)
            dry = await _dry_conflict(ctx)
            choice = _choice_for(dry.merge.conflicts.records[0])
            fence = await _fence_for(ctx, room_generation=999)
            before = await _db_state(ctx["entry"]["wp"])
            raised: dict[str, Any] = {}
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                try:
                    await svc.resolve(
                        operation_id=ctx["req"]["operation"],
                        declared_project_id=project,
                        declared_wp_id=ctx["entry"]["wp"],
                        declared_entry_id=ENTRY,
                        fence=fence, resolutions=[choice],
                        adapter=_JsonCarrierAdapter(), contract=contract,
                        actor_id=user_a,
                    )
                except Exception as exc:  # noqa: BLE001
                    raised = {
                        "type": type(exc).__name__,
                        "code": getattr(exc, "error_code", None),
                        "reason": getattr(
                            getattr(exc, "fence_reason", None), "value", None
                        ),
                    }
            snap["scenarios"]["resolve_rejected"] = {
                "raised": raised,
                "before": before,
                "after": await _db_state(ctx["entry"]["wp"]),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("resolve_rejected", exc)

        # ═══ P4：另一个更新的 canonical application ⇒ superseded（P36）═══
        try:
            ctx = await _stage_world("resolve_superseded", **_CONFLICT_WORLD)
            dry = await _dry_conflict(ctx)
            choice = _choice_for(dry.merge.conflicts.records[0])
            # 🔴 制造「另一个更新的 canonical application」用的是**真实第二次
            # forcesave + 第二份 durable incoming**，不是 UPDATE 一个假 UUID：
            # `ck_wpoor_durable_fence_pair` 要求 id 与 sequence 同生共死、
            # `ck_wpoor_durable_le_request` 要求 durable ≤ latest request，
            # 手写假值会被 CHECK 直接拒（本轮实测两条都撞过）。
            req2 = await _accept_request(ctx["env"], key="resolve_superseded-fs2")
            inc2 = await _seal_incoming(
                ctx["env"], ctx["entry"], req2,
                payload=_ooxml(
                    projection_values=_carrier_values(
                        _projection({PERIOD: "D", TOTAL: Decimal("1")})
                    )
                ),
            )
            app2 = await _correlate(req2, inc2)
            fence = await _fence_for(ctx)
            before = await _db_state(ctx["entry"]["wp"])
            raised = {}
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                try:
                    await svc.resolve(
                        operation_id=ctx["req"]["operation"],
                        declared_project_id=project,
                        declared_wp_id=ctx["entry"]["wp"],
                        declared_entry_id=ENTRY,
                        fence=fence, resolutions=[choice],
                        adapter=_JsonCarrierAdapter(), contract=contract,
                        actor_id=user_a,
                    )
                except Exception as exc:  # noqa: BLE001
                    raised = {
                        "type": type(exc).__name__,
                        "code": getattr(exc, "error_code", None),
                        "reason": getattr(
                            getattr(exc, "fence_reason", None), "value", None
                        ),
                    }
            snap["scenarios"]["resolve_superseded"] = {
                "raised": raised,
                "first_application": str(ctx["app"]),
                "second_application": str(app2),
                "before": before,
                "after": await _db_state(ctx["entry"]["wp"]),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("resolve_superseded", exc)

        # ═══ P5：同 application 的 sequence fold ⇒ 只规范化、不判 stale（P36 核心）═
        try:
            ctx = await _stage_world("resolve_fold", **_CONFLICT_WORLD)
            dry = await _dry_conflict(ctx)
            choice = _choice_for(dry.merge.conflicts.records[0])
            # room latest durable 指向**同一个** application，而服务端 application 的
            # effective sequence 已被 same-key duplicate 抬高；请求还带着旧的 1。
            # `latest_request_sequence` 必须一起抬（`ck_wpoor_durable_le_request`）——
            # 真实故事里那个更高的 sequence 本来就来自一次真实 request。
            async with engine.begin() as conn:
                await conn.exec_driver_sql(
                    "UPDATE working_paper_content_application SET "
                    f"effective_request_sequence = 7 WHERE id = '{ctx['app']}'"
                )
                await conn.exec_driver_sql(
                    "UPDATE working_paper_oo_room SET latest_request_sequence = "
                    "GREATEST(latest_request_sequence, 7), "
                    f"latest_durable_application_id = '{ctx['app']}', "
                    f"latest_durable_sequence = 7 WHERE id = '{ctx['env']['room']}'"
                )
            fence = await _fence_for(
                ctx, application_effective_request_sequence=1
            )
            before = await _db_state(ctx["entry"]["wp"])
            fold_outcome: dict[str, Any] | None = None
            raised = {}
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                try:
                    got = await svc.resolve(
                        operation_id=ctx["req"]["operation"],
                        declared_project_id=project,
                        declared_wp_id=ctx["entry"]["wp"],
                        declared_entry_id=ENTRY,
                        fence=fence, resolutions=[choice],
                        adapter=_JsonCarrierAdapter(), contract=contract,
                        actor_id=user_a,
                    )
                    fold_outcome = got.as_dict()
                except Exception as exc:  # noqa: BLE001
                    raised = {
                        "type": type(exc).__name__,
                        "code": getattr(exc, "error_code", None),
                    }
            snap["scenarios"]["resolve_fold"] = {
                "outcome": fold_outcome,
                "raised": raised,
                "before": before,
                "after": await _db_state(ctx["entry"]["wp"]),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("resolve_fold", exc)

        # ═══ P6：current revision 变化 ⇒ rebase（AC 8.5 末段）═══════════
        try:
            ctx = await _stage_world("resolve_rebase", **_CONFLICT_WORLD)
            dry = await _dry_conflict(ctx)
            choice = _choice_for(dry.merge.conflicts.records[0])
            fence = await _fence_for(ctx, expected_current_revision=42)
            before = await _db_state(ctx["entry"]["wp"])
            raised = {}
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                try:
                    await svc.resolve(
                        operation_id=ctx["req"]["operation"],
                        declared_project_id=project,
                        declared_wp_id=ctx["entry"]["wp"],
                        declared_entry_id=ENTRY,
                        fence=fence, resolutions=[choice],
                        adapter=_JsonCarrierAdapter(), contract=contract,
                        actor_id=user_a,
                    )
                except Exception as exc:  # noqa: BLE001
                    raised = {
                        "type": type(exc).__name__,
                        "code": getattr(exc, "error_code", None),
                        "rebased_digest": getattr(
                            exc, "rebased_conflict_set_digest", None
                        ),
                        "rebased_count": getattr(exc, "rebased_conflict_count", None),
                    }
            snap["scenarios"]["resolve_rebase"] = {
                "raised": raised,
                "before": before,
                "after": await _db_state(ctx["entry"]["wp"]),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("resolve_rebase", exc)

        # ═══ P7：零裁决的 resolve 与 nullable-operation 的 retry 都拒（AC 8.3 / 8.9）═
        try:
            ctx = await _stage_world("retry_gate", **_CONFLICT_WORLD)
            await _dry_conflict(ctx)
            before = await _db_state(ctx["entry"]["wp"])
            null_retry: dict[str, Any] = {}
            empty_resolve: dict[str, Any] = {}
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                try:
                    await svc.retry(
                        operation_id=None,
                        declared_project_id=project,
                        declared_wp_id=ctx["entry"]["wp"],
                        declared_entry_id=ENTRY,
                        adapter=_JsonCarrierAdapter(), contract=contract,
                        actor_id=user_a,
                    )
                except Exception as exc:  # noqa: BLE001
                    null_retry = {
                        "type": type(exc).__name__,
                        "code": getattr(exc, "error_code", None),
                    }
                try:
                    await svc.resolve(
                        operation_id=ctx["req"]["operation"],
                        declared_project_id=project,
                        declared_wp_id=ctx["entry"]["wp"],
                        declared_entry_id=ENTRY,
                        fence=await _fence_for(ctx), resolutions=[],
                        adapter=_JsonCarrierAdapter(), contract=contract,
                        actor_id=user_a,
                    )
                except Exception as exc:  # noqa: BLE001
                    empty_resolve = {
                        "type": type(exc).__name__,
                        "code": getattr(exc, "error_code", None),
                    }
            snap["scenarios"]["retry_gate"] = {
                "null_retry": null_retry,
                "empty_resolve": empty_resolve,
                "before": before,
                "after": await _db_state(ctx["entry"]["wp"]),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("retry_gate", exc)

        # ═══ P8：普通 retry 复用同一 timeline（AC 8.9 / Property 38）═══════
        try:
            ctx = await _stage_world(
                "retry_reuse",
                base_values={PERIOD: "A", TOTAL: Decimal("1")},
                current_values=None,
                incoming_values={PERIOD: "A", TOTAL: Decimal("9")},
            )
            before = await _db_state(ctx["entry"]["wp"])
            adapter = _JsonCarrierAdapter()
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                retried = await svc.retry(
                    operation_id=ctx["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=ctx["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=adapter, contract=contract, actor_id=user_a,
                    attempt=2,
                )
            snap["scenarios"]["retry_reuse"] = {
                "outcome": retried.as_dict(),
                "adapter_calls": list(adapter.calls),
                "before": before,
                "after": await _db_state(ctx["entry"]["wp"]),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("retry_reuse", exc)

        # ═══ P9：rollback 创建新版本（AC 8.7 / 8.8 / Property 37）═════════
        try:
            ctx = await _stage_world(
                "rollback",
                base_values={PERIOD: "A", TOTAL: Decimal("1")},
                current_values=None,
                incoming_values={PERIOD: "A", TOTAL: Decimal("777")},
            )
            wp = ctx["entry"]["wp"]
            async with Session() as s:
                _svc, coord = _services(s, probe=_RecordingProbe())
                applied = await coord.apply_durable_incoming(
                    operation_id=ctx["req"]["operation"],
                    declared_project_id=project, declared_wp_id=wp,
                    declared_entry_id=ENTRY, adapter=_JsonCarrierAdapter(),
                    contract=contract, actor_id=user_a,
                )
            before = await _db_state(wp)
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                rolled = await svc.rollback(
                    version_id=ctx["entry"]["cv0"],
                    declared_project_id=project, declared_wp_id=wp,
                    declared_entry_id=ENTRY,
                    expected_current_revision=before["revision"],
                    adapter=_JsonCarrierAdapter(), contract=contract,
                    actor_id=user_a,
                )
            mid = await _db_state(wp)
            # 再 rollback 到**当前**版本 ⇒ projection 等值 ⇒ 零写入、revision 不变。
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                noop = await svc.rollback(
                    version_id=rolled.new_content_version_id,
                    declared_project_id=project, declared_wp_id=wp,
                    declared_entry_id=ENTRY,
                    expected_current_revision=mid["revision"],
                    adapter=_JsonCarrierAdapter(), contract=contract,
                    actor_id=user_a,
                )
            snap["scenarios"]["rollback"] = {
                "applied_revision": applied.result_revision,
                "rolled": rolled.as_dict(),
                "noop": noop.as_dict(),
                "before": before,
                "mid": mid,
                "after": await _db_state(wp),
                "source_file_exists": (
                    base_root / "storage" / str(project) / ctx["entry"]["rep_rel"]
                ).is_file()
                or (base_root / ctx["entry"]["rep_rel"]).is_file(),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("rollback", exc)

        # ═══ P9b：rollback 的乐观锁 —— stale expected revision 必须拒（AC 8.7）═══
        try:
            ctx = await _stage_world(
                "rollback_stale",
                base_values={PERIOD: "A", TOTAL: Decimal("1")},
                current_values=None,
                incoming_values={PERIOD: "A", TOTAL: Decimal("55")},
            )
            wp = ctx["entry"]["wp"]
            async with Session() as s:
                _svc, coord = _services(s, probe=_RecordingProbe())
                await coord.apply_durable_incoming(
                    operation_id=ctx["req"]["operation"],
                    declared_project_id=project, declared_wp_id=wp,
                    declared_entry_id=ENTRY, adapter=_JsonCarrierAdapter(),
                    contract=contract, actor_id=user_a,
                )
            before = await _db_state(wp)
            stale: dict[str, Any] = {}
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                try:
                    await svc.rollback(
                        version_id=ctx["entry"]["cv0"],
                        declared_project_id=project, declared_wp_id=wp,
                        declared_entry_id=ENTRY,
                        # 客户端手里还是 revision 0 —— 期间已经推进到 1。
                        expected_current_revision=0,
                        adapter=_JsonCarrierAdapter(), contract=contract,
                        actor_id=user_a,
                    )
                except Exception as exc:  # noqa: BLE001
                    stale = {
                        "type": type(exc).__name__,
                        "code": getattr(exc, "error_code", None),
                    }
            snap["scenarios"]["rollback_stale_expectation"] = {
                "raised": stale,
                "before": before,
                "after": await _db_state(wp),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("rollback_stale_expectation", exc)

        # ═══ P9c：resolve 期间 initiator 被撤销 ⇒ fence 拒（AC 10.10 / P43）═══
        try:
            ctx = await _stage_world("resolve_revoked", **_CONFLICT_WORLD)
            dry = await _dry_conflict(ctx)
            choice = _choice_for(dry.merge.conflicts.records[0])
            fence = await _fence_for(ctx)
            # 🔴 真撤销那一行（`revoked_at`），不是改 epoch 数字：服务端读的是
            # 「**当下仍然合法**的发起人 epoch」，撤销后查不到行 ⇒ 观测侧必须 fail closed
            # （返回一个与任何冻结值都不相等的哨兵），而不是当成「授权仍有效」。
            async with engine.begin() as conn:
                await conn.exec_driver_sql(
                    "UPDATE working_paper_oo_participant SET revoked_at = now(), "
                    f"state = 'revoked' WHERE id = '{ctx['env']['participant']}'"
                )
            before = await _db_state(ctx["entry"]["wp"])
            revoked: dict[str, Any] = {}
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                try:
                    await svc.resolve(
                        operation_id=ctx["req"]["operation"],
                        declared_project_id=project,
                        declared_wp_id=ctx["entry"]["wp"],
                        declared_entry_id=ENTRY,
                        fence=fence, resolutions=[choice],
                        adapter=_JsonCarrierAdapter(), contract=contract,
                        actor_id=user_a,
                    )
                except Exception as exc:  # noqa: BLE001
                    revoked = {
                        "type": type(exc).__name__,
                        "code": getattr(exc, "error_code", None),
                        "reason": getattr(
                            getattr(exc, "fence_reason", None), "value", None
                        ),
                    }
            snap["scenarios"]["resolve_initiator_revoked"] = {
                "raised": revoked,
                "before": before,
                "after": await _db_state(ctx["entry"]["wp"]),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("resolve_initiator_revoked", exc)

        # ═══ P9d：冲突行生命周期（AC 8.1 / 8.6 的仓储层不变量）═══════════
        #
        # 两条判据在 happy path 上都**恒不触发**（冲突集不缩小、裁决 key 恒命中），
        # 因此必须用合成输入直接喂仓储方法 —— 否则短路它们在变异检验里判 GREEN。
        try:
            ctx = await _stage_world("conflict_rows", **_CONFLICT_WORLD)
            dry = await _dry_conflict(ctx)
            op_id = dry.canonical_operation_id
            rows_before = (await _db_state(ctx["entry"]["wp"]))["conflicts"]
            # ① 第二轮观测里少了那一条 ⇒ 旧行必须被打 `superseded_at`（不删行）。
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                shrink = await repo.record_conflicts(
                    operation_id=op_id,
                    client_edit_epoch=3,
                    canonical_application_id=ctx["app"],
                    effective_request_sequence=1,
                    rows=[],
                )
                await s.commit()
            rows_after_shrink = (await _db_state(ctx["entry"]["wp"]))["conflicts"]
            # ② 裁决指向不存在的冲突 ⇒ 必须抛（静默跳过 = 轨迹不全）。
            unknown_trail: dict[str, Any] = {}
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                try:
                    await repo.mark_conflicts_resolved(
                        operation_id=op_id,
                        resolutions=[
                            {
                                "stable_field_key": "header_block/does_not_exist",
                                "row_key": "",
                                "oo_location": "ZZ999",
                                "resolution": {"kind": "keep_current"},
                                "resolved_value": {"present": False},
                            }
                        ],
                        actor_id=user_a,
                    )
                    await s.commit()
                except Exception as exc:  # noqa: BLE001
                    unknown_trail = {
                        "type": type(exc).__name__,
                        "code": getattr(exc, "error_code", None),
                    }
                    await s.rollback()
            snap["scenarios"]["conflict_row_lifecycle"] = {
                "rows_before": rows_before,
                "shrink": {
                    "inserted": shrink.inserted,
                    "updated": shrink.updated,
                    "superseded": shrink.superseded,
                },
                "rows_after_shrink": rows_after_shrink,
                "unknown_trail": unknown_trail,
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("conflict_row_lifecycle", exc)

        # ═══ P10：同 numeric revision 跨 wp 由不同 UUID 无碰撞（AC 8.7 末句）═
        try:
            a = await _build_entry("collide_a", {PERIOD: "A", TOTAL: Decimal("1")})
            b = await _build_entry("collide_b", {PERIOD: "B", TOTAL: Decimal("2")})
            async with Session() as s:
                rows = (
                    (
                        await s.execute(
                            sa.text(
                                "SELECT wp_id::text, revision, id::text FROM "
                                "working_paper_content_version WHERE wp_id IN (:x, :y) "
                                "ORDER BY wp_id"
                            ),
                            {"x": a["wp"], "y": b["wp"]},
                        )
                    )
                    .mappings()
                    .all()
                )
            cross_wp: dict[str, Any] = {}
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                try:
                    await svc.rollback(
                        version_id=b["cv0"],  # 属于 wp B 的 UUID
                        declared_project_id=project,
                        declared_wp_id=a["wp"],  # 声明的却是 wp A
                        declared_entry_id=ENTRY,
                        expected_current_revision=0,
                        adapter=_JsonCarrierAdapter(), contract=contract,
                        actor_id=user_a,
                    )
                except Exception as exc:  # noqa: BLE001
                    cross_wp = {
                        "type": type(exc).__name__,
                        "code": getattr(exc, "error_code", None),
                        # 内部标记：证明**是哪一道门**拒的（authorization-before-resource）。
                        "refused_at": getattr(exc, "refused_at", None),
                    }
            unknown: dict[str, Any] = {}
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                try:
                    await svc.rollback(
                        version_id=uuid.uuid4(),
                        declared_project_id=project, declared_wp_id=a["wp"],
                        declared_entry_id=ENTRY, expected_current_revision=0,
                        adapter=_JsonCarrierAdapter(), contract=contract,
                        actor_id=user_a,
                    )
                except Exception as exc:  # noqa: BLE001
                    unknown = {
                        "type": type(exc).__name__,
                        "code": getattr(exc, "error_code", None),
                        "refused_at": getattr(exc, "refused_at", None),
                    }
            snap["scenarios"]["version_scope"] = {
                "rows": [dict(r) for r in rows],
                "cross_wp": cross_wp,
                "unknown": unknown,
                "db_a": await _db_state(a["wp"]),
                "db_b": await _db_state(b["wp"]),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("version_scope", exc)

        # ═══ P11：incoming / 未发布 artifact 不可作 rollback source（AC 8.7 / P65 / 67）═
        #
        # 两层各自取证：
        #   ① DB 层 —— `working_paper_content_representation` 的 CHECK 直接拒绝
        #      「representation 指向 incoming artifact」，连这个形态都造不出来；
        #   ② 服务层 —— 但 `canonical` 却**未发布**（staged）的 artifact 是 DB 允许的形态
        #      （发布失败留下的 staged 行），必须由 `assert_rollback_source_publishable` 拒。
        # 只测其中一层都会留下盲区：①证明不了服务层有牙，②证明不了 incoming 被 DB 挡住。
        try:
            entry = await _build_entry("bad_source", {PERIOD: "A", TOTAL: Decimal("1")})
            wp = entry["wp"]
            env = await _build_room(entry)
            req = await _accept_request(env, key="bad-source-fs")
            inc = await _seal_incoming(
                env, entry, req,
                payload=_ooxml(
                    projection_values=_carrier_values(entry["base_projection"])
                ),
            )
            db_layer: dict[str, Any] = {}
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                try:
                    await repo.create_representation(
                        project_id=project, wp_id=wp, entry_id=ENTRY,
                        content_version_id=entry["cv0"], generation=9,
                        document_type="xlsx", artifact_id=inc["incoming"],
                        artifact_sha256=inc["sha256"],
                        definition_bundle_id=world["bundle"],
                        authority_model_definition_id=world["authority"],
                        adapter_id=ENTRY,
                        adapter_build_digest=_d("task27-adapter"),
                        structure_hash=_d("bad-source-structure"),
                        identity_inventory_sha256=_d("bad-source-identity"),
                        reason="content_commit",
                    )
                    await s.commit()
                except Exception as exc:  # noqa: BLE001 - 期望被 DB CHECK 拒
                    db_layer = {
                        "type": type(exc).__name__,
                        "mentions_incoming": "incoming" in str(exc),
                    }
                    await s.rollback()
            # ② canonical 但 staged 的 artifact：DB 允许，服务层必须拒。
            staged_rep_bytes = _ooxml(
                projection_values=_carrier_values(entry["base_projection"]),
                unmanaged=b"<staged/>",
            )
            staged_only = artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=staged_rep_bytes,
                document_type="xlsx",
            )
            bad_proj = artifacts.publish_projection(
                revision=1,
                staged=artifacts.stage_bytes(
                    project_id=project, wp_id=wp,
                    payload=json.dumps({"tag": "bad-source"}, sort_keys=True).encode(),
                    document_type="json.gz",
                ),
            )
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                bad_proj_art = await repo.register_artifact(
                    project_id=project, wp_id=wp, kind=ArtifactKind.projection,
                    state=ArtifactState.published,
                    relative_path=bad_proj.relative_path, sha256=bad_proj.sha256,
                    size_bytes=bad_proj.size_bytes, document_type="json.gz",
                )
                staged_art = await repo.register_artifact(
                    project_id=project, wp_id=wp, kind=ArtifactKind.canonical,
                    state=ArtifactState.staged,
                    relative_path=str(
                        staged_only.path.relative_to(base_root)
                    ).replace("\\", "/"),
                    sha256=staged_only.sha256,
                    size_bytes=staged_only.size_bytes, document_type="xlsx",
                )
                # `ck_wpcv_has_content` 要求 projection 或 authoritative 至少一个非空。
                cv = await repo.create_content_version(
                    project_id=project, wp_id=wp, entry_id=ENTRY, revision=1,
                    source="onlyoffice", projection_artifact_id=bad_proj_art.id,
                    projection_sha256=_d("bad-source-projection"), actor_id=user_a,
                )
                await repo.create_representation(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    content_version_id=cv.id, generation=1, document_type="xlsx",
                    artifact_id=staged_art.id, artifact_sha256=staged_art.sha256,
                    definition_bundle_id=world["bundle"],
                    authority_model_definition_id=world["authority"],
                    adapter_id=ENTRY, adapter_build_digest=_d("task27-adapter"),
                    structure_hash=_d("bad-source-structure"),
                    identity_inventory_sha256=_d("bad-source-identity"),
                    reason="content_commit",
                )
                await s.commit()
            before = await _db_state(wp)
            bad: dict[str, Any] = {}
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                try:
                    await svc.rollback(
                        version_id=cv.id,
                        declared_project_id=project, declared_wp_id=wp,
                        declared_entry_id=ENTRY,
                        expected_current_revision=before["revision"],
                        adapter=_JsonCarrierAdapter(), contract=contract,
                        actor_id=user_a,
                    )
                except Exception as exc:  # noqa: BLE001
                    bad = {
                        "type": type(exc).__name__,
                        "code": getattr(exc, "error_code", None),
                    }
            snap["scenarios"]["rollback_bad_source"] = {
                "raised": bad,
                "db_layer": db_layer,
                "incoming_artifact": str(inc["incoming"]),
                "before": before,
                "after": await _db_state(wp),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("rollback_bad_source", exc)

        # ═══ P15：requested id 是 terminal duplicate ⇒ 预览/裁决都落 canonical primary ═
        #
        # 🔴 为什么这个场景必须存在（本轮补齐的覆盖空洞）：
        # AC 8.5 / Property 38 要求 duplicate 的 GET/timeline/conflict/retry/resolve 走
        # 「requested 授权 → direct-primary invariant → canonicalize → 只要求 canonical
        # primary 绑定 application」。此前**只有 AST 形态判据**（`preview`/`resolve` 确实
        # 调了 Task 23 的四步入口）+ Task 23 自己的真库判据（`read_operation` 会正确跟随
        # duplicate）。两者都不能证明**canonicalize 之后**本模块用的是哪个 id：
        # 其余 13 个场景里 requested 恒等于 canonical，于是
        #   * `load_conflicts(operation_id=requested)` —— duplicate 请求返回**空预览**；
        #   * `mark_conflicts_resolved(operation_id=requested)` —— 裁决轨迹**标 0 行**，
        #     而 resolve 照常回 200。
        # 两条形态实测（2026-08-28，把本场景的断言 `-k` 排除掉后重跑同两条变异）：
        #   * 读侧 G01 = **完全静默**：405 passed 一条不红，预览回 200 + conflict_count=0；
        #   * 写侧 G02 = **commit 后失败**：内容已发布、revision 已 +1，随后
        #     `mark_conflicts_resolved` 抛 `ScopeIntegrityError`（它对匹配不到的裁决
        #     刻意不静默跳过）—— 轨迹缺失 + 一个与裁决无关的完整性错误。
        # 两条都只有在「requested ≠ canonical」的世界里才可观测，故必须有本场景。
        #
        # 造 duplicate 的手法是**真实的 status 6/2 多 delivery**：第二个 delivery 的
        # payload 与第一次逐字节相同 ⇒ incoming sha256 相同 ⇒ application key 相同
        # （key 不含 request id/sequence/status，Property 64）⇒ 第二个 shell 落成
        # direct terminal duplicate。不手写 UPDATE 伪造 duplicate 指针：V151 的
        # `ck_wpso_duplicate_shape` / `wpsync_check_operation_duplicate_link` 会拒，
        # 而绕过它们造出来的行根本不是协议里的形态。
        try:
            ctx = await _stage_world("resolve_dup", **_CONFLICT_WORLD)
            dry = await _dry_conflict(ctx)
            choice = _choice_for(dry.merge.conflicts.records[0])
            req2 = await _accept_request(ctx["env"], key="resolve_dup-fs2")
            inc2 = await _seal_incoming(
                ctx["env"], ctx["entry"], req2,
                payload=ctx["incoming_payload"],  # 复用**同一份字节**（见 _stage_world 注释）
            )
            app_again = await _correlate(req2, inc2)
            dup_op = req2["operation"]
            primary_op = ctx["req"]["operation"]
            async with Session() as s:
                shapes = {
                    str(row[0]): {
                        "application_id": _opt(row[1]),
                        "duplicate_of": _opt(row[2]),
                        "state": str(row[3]),
                    }
                    for row in (
                        await s.execute(
                            sa.select(
                                WorkpaperSyncOperation.id,
                                WorkpaperSyncOperation.application_id,
                                WorkpaperSyncOperation.duplicate_of_operation_id,
                                WorkpaperSyncOperation.state,
                            ).where(
                                WorkpaperSyncOperation.id.in_([primary_op, dup_op])
                            )
                        )
                    ).all()
                }
            before = await _db_state(ctx["entry"]["wp"])
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                dup_preview = await svc.preview(
                    operation_id=dup_op,
                    declared_project_id=project,
                    declared_wp_id=ctx["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    contract=contract,
                )
            fence = await _fence_for(ctx)
            async with Session() as s:
                svc, _c = _services(s, probe=_RecordingProbe())
                dup_outcome = await svc.resolve(
                    operation_id=dup_op,
                    declared_project_id=project,
                    declared_wp_id=ctx["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    fence=fence,
                    resolutions=[choice],
                    adapter=_JsonCarrierAdapter(),
                    contract=contract,
                    actor_id=user_a,
                )
            snap["scenarios"]["resolve_via_duplicate"] = {
                "primary_operation": str(primary_op),
                "duplicate_operation": str(dup_op),
                "application": str(ctx["app"]),
                "application_again": str(app_again),
                "shapes": shapes,
                "incoming_sha_first": ctx["inc"]["sha256"],
                "incoming_sha_second": inc2["sha256"],
                "incoming_artifact_first": str(ctx["inc"]["incoming"]),
                "incoming_artifact_second": str(inc2["incoming"]),
                "preview": dup_preview.as_dict(),
                "outcome": dup_outcome.as_dict(),
                "folded_sha": projection_canonical_digest(
                    M.apply_resolutions(dry.merge, [choice], contract=contract)
                ),
                "merged_sha": projection_canonical_digest(dry.merge.merged),
                "before": before,
                "after": await _db_state(ctx["entry"]["wp"]),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("resolve_via_duplicate", exc)

        # ═══ P16：AC 8.4 —— 谁可以提交裁决 ═════════════════════════════
        #
        # AC 8.4 有**三个**独立的拒绝理由，此前只覆盖了第三个：
        #   ① 没有底稿编辑权限            → `authorize` 回调否决（403，与 404 分型）
        #   ② 复核锁定 / 归档              → probe 观测到 `workflow_locked`
        #   ③ 权限 epoch 变化              → 已有 `resolve_initiator_revoked` 场景
        # ①②各自的拒绝点在不同层（scope 授权门 / 最终 fence），因此必须各有一条：
        # 只测 ③ 时，把 `authorize` 参数丢掉（一路不传下去）或把 probe 的 workflow 分支
        # 短路都不会有任何判据变红。
        try:
            ctx = await _stage_world("resolve_auth", **_CONFLICT_WORLD)
            dry = await _dry_conflict(ctx)
            choice = _choice_for(dry.merge.conflicts.records[0])
            fence = await _fence_for(ctx)
            before = await _db_state(ctx["entry"]["wp"])

            async def _resolve_with(probe: Any, **kwargs: Any) -> dict[str, Any]:
                async with Session() as s:
                    svc, _c = _services(s, probe=probe)
                    try:
                        ok = await svc.resolve(
                            operation_id=ctx["req"]["operation"],
                            declared_project_id=project,
                            declared_wp_id=ctx["entry"]["wp"],
                            declared_entry_id=ENTRY,
                            fence=fence, resolutions=[choice],
                            adapter=_JsonCarrierAdapter(), contract=contract,
                            actor_id=user_a, **kwargs,
                        )
                    except Exception as exc:  # noqa: BLE001
                        return {
                            "type": type(exc).__name__,
                            "code": getattr(exc, "error_code", None),
                            # 落地阶段拒绝时**内层**是哪一条 fence（AC 10.10 要求十条
                            # 逐条可分辨）；服务层的类型只说明「不可重试 vs 可重试」。
                            "apply_error_code": getattr(exc, "apply_error_code", None),
                        }
                # 没抛 = 放行。把结果原样带出来（而不是 `{}`）：判据失败时要看得见
                # 「它究竟放行成了什么」，否则只剩一个 KeyError。
                return {"type": None, "code": None, "succeeded": ok.as_dict()}

            # ① 无编辑权限：`authorize` 回调否决。判据不是「抛了个异常」而是
            #    「抛的是 403 分型、且与跨 scope/不存在的 404 分型不同」。
            denying_probe = _RecordingProbe()
            no_permission = await _resolve_with(
                denying_probe, authorize=lambda _ref: False
            )
            after_no_permission = await _db_state(ctx["entry"]["wp"])

            # ② 复核锁定 / 归档：probe 现场观测到 workflow 已锁。
            class _LockedProbe:
                def __init__(self) -> None:
                    self.calls: list[str] = []

                async def observe(self, *, project_id, wp_id, entry_id):  # noqa: ANN001
                    self.calls.append(str(wp_id))
                    return {"project_visible": True, "workflow_locked": True}

            locked_probe = _LockedProbe()
            workflow_locked = await _resolve_with(locked_probe)

            # ② 之后 application 已落**不可重试终态** `authorization_stale`（AC 10.10 末句）
            # —— 这正是「拒绝不是空操作」的证据，也是为什么 ③ 必须换一个 world：
            # 同一个 application 再来一次只会撞 `ApplicationTerminalStaleError`，
            # 那时测到的就不是 probe 的可见性分支了（首版实测踩到）。
            async with Session() as s:
                app_state_after_lock = (
                    await s.execute(
                        sa.text(
                            "SELECT state FROM working_paper_content_application "
                            "WHERE id = :a"
                        ),
                        {"a": ctx["app"]},
                    )
                ).scalar_one()

            # ③ 项目不可见（同一 probe 口的另一个分支，与 ② 分型）——**独立 world**。
            class _InvisibleProbe:
                def __init__(self) -> None:
                    self.calls: list[str] = []

                async def observe(self, *, project_id, wp_id, entry_id):  # noqa: ANN001
                    self.calls.append(str(wp_id))
                    return {"project_visible": False, "workflow_locked": False}

            ctx_v = await _stage_world("resolve_auth_vis", **_CONFLICT_WORLD)
            dry_v = await _dry_conflict(ctx_v)
            choice_v = _choice_for(dry_v.merge.conflicts.records[0])
            fence_v = await _fence_for(ctx_v)
            before_v = await _db_state(ctx_v["entry"]["wp"])
            invisible_probe = _InvisibleProbe()
            not_visible: dict[str, Any] = {}
            async with Session() as s:
                svc, _c = _services(s, probe=invisible_probe)
                try:
                    await svc.resolve(
                        operation_id=ctx_v["req"]["operation"],
                        declared_project_id=project,
                        declared_wp_id=ctx_v["entry"]["wp"],
                        declared_entry_id=ENTRY,
                        fence=fence_v, resolutions=[choice_v],
                        adapter=_JsonCarrierAdapter(), contract=contract,
                        actor_id=user_a,
                    )
                except Exception as exc:  # noqa: BLE001
                    not_visible = {
                        "type": type(exc).__name__,
                        "code": getattr(exc, "error_code", None),
                        "apply_error_code": getattr(exc, "apply_error_code", None),
                    }

            snap["scenarios"]["resolve_authorization"] = {
                "application_state_after_workflow_lock": str(app_state_after_lock),
                "visibility_before": before_v,
                "visibility_after": await _db_state(ctx_v["entry"]["wp"]),
                "no_permission": no_permission,
                # 授权门必须在**任何**业务读之前 ⇒ 这一层拒绝时 probe 一次都不该被调用
                "probe_calls_when_unauthorized": list(denying_probe.calls),
                "workflow_locked": workflow_locked,
                "workflow_probe_calls": list(locked_probe.calls),
                "not_visible": not_visible,
                "visibility_probe_calls": list(invisible_probe.calls),
                "before": before,
                "after_no_permission": after_no_permission,
                "after": await _db_state(ctx["entry"]["wp"]),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("resolve_authorization", exc)

        _ = compute_application_key  # 显式保留：staging 只用仓储层，不自算 key
        return snap
    finally:
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
# 环境自证
# ═══════════════════════════════════════════════════════════════════════════


class TestHarness:
    def test_real_postgresql(self, snap: dict[str, Any]) -> None:
        assert "PostgreSQL" in (snap["server_version"] or "")

    def test_migration_applied_cleanly(self, snap: dict[str, Any]) -> None:
        assert snap["apply_errors"] == []

    def test_scratch_isolation(self, snap: dict[str, Any]) -> None:
        assert snap["schema"].startswith(_SCHEMA_PREFIX)
        assert "tmp_task27_store_" in snap["base_root"]

    def test_no_phase_crashed_during_collection(self, snap: dict[str, Any]) -> None:
        """采集阶段一个都不许挂 —— 只记录不断言等于静默缺失。"""
        assert snap["harness_errors"] == {}, snap["harness_errors"]

    def test_the_carrier_payload_is_byte_deterministic(self) -> None:
        """载体替身写出的 zip 不得含**现场时钟** —— 两处判据依赖「同内容 ⇒ 同字节」。

        直接断言每个条目的 `date_time` 是固定纪元，而不是「跑两次比 sha」：后者在同一秒
        内恒成立，正是它让 R02 在快跑里假红、慢跑里翻 GREEN。
        """
        payload = _ooxml(projection_values={})
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            stamps = {info.filename: info.date_time for info in zf.infolist()}
        assert stamps, "zip 里一个条目都没有"
        assert set(stamps.values()) == {_ZIP_EPOCH}, (
            f"zip 条目带上了现场时钟 ⇒ 同内容不同字节：{stamps}"
        )
        assert _ooxml(projection_values={}) == payload

    def test_every_scenario_was_collected(self, snap: dict[str, Any]) -> None:
        assert set(snap["scenarios"]) == {
            "preview",
            "resolve_ok",
            "resolve_rejected",
            "resolve_superseded",
            "resolve_fold",
            "resolve_rebase",
            "resolve_initiator_revoked",
            "retry_gate",
            "retry_reuse",
            "rollback",
            "rollback_stale_expectation",
            "conflict_row_lifecycle",
            "version_scope",
            "rollback_bad_source",
            "resolve_via_duplicate",
            "resolve_authorization",
        }


# ═══════════════════════════════════════════════════════════════════════════
# P35 冲突预览：双侧可追溯
# ═══════════════════════════════════════════════════════════════════════════


class TestConflictPreview:
    def test_conflict_rows_were_really_persisted(self, snap: dict[str, Any]) -> None:
        """AC 8.1 的前提：冲突**落行**。只记 count/digest 时预览没有数据可读。"""
        sc = snap["scenarios"]["preview"]
        assert sc["dry_result"] == "conflict"
        assert sc["dry_conflict_rows_written"] >= 1
        assert len(sc["db"]["conflicts"]) == sc["dry_conflict_rows_written"]

    def test_every_item_is_traceable_on_both_sides(self, snap: dict[str, Any]) -> None:
        """Property 35：JSON Pointer 与 OO 地址都能定位，三方值与 kind 非空。"""
        items = [
            item
            for group in snap["scenarios"]["preview"]["preview"]["groups"]
            for item in group["items"]
        ]
        assert items, "预览没有任何条目"
        for item in items:
            assert item["json_pointer"].startswith("/"), item
            assert item["oo_location"].strip(), item
            assert item["business_label"].strip(), item
            assert item["kind"], item
            for side in ("base", "current", "incoming"):
                assert item[side] is not None, (side, item)
                assert "present" in item[side], (side, item)
            assert item["field_source"] and item["protection_policy"]
            assert item["suggested_action"]

    def test_amount_fields_declare_their_value_type(self, snap: dict[str, Any]) -> None:
        """AC 8.2：金额要走平台 `fmtAmount()`，前端必须拿得到 `value_type`。

        `value_type` 不在冲突行里 —— 它只能由 **frozen contract** 推出，因此这条判据
        同时锁住「预览按 frozen contract 渲染」。
        """
        items = [
            item
            for group in snap["scenarios"]["preview"]["preview"]["groups"]
            for item in group["items"]
        ]
        types = {item["stable_field_key"]: item["value_type"] for item in items}
        assert types, types
        assert all(v for v in types.values()), types
        assert types.get(PERIOD) == "text", types

    def test_grouping_is_by_sheet_table_row(self, snap: dict[str, Any]) -> None:
        groups = snap["scenarios"]["preview"]["preview"]["groups"]
        assert groups
        keys = [(g["sheet_key"], g["table_key"], g["row_key"]) for g in groups]
        assert keys == sorted(keys), f"分组顺序不稳定: {keys}"
        assert len({tuple(k) for k in keys}) == len(keys)

    def test_preview_carries_the_two_fence_fields_per_item(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 8.5：client edit epoch 与 incoming sequence 逐条随冲突返回。"""
        preview = snap["scenarios"]["preview"]["preview"]
        for group in preview["groups"]:
            for item in group["items"]:
                assert item["client_edit_epoch"] == preview["client_edit_epoch"]
                assert item["incoming_sequence"] == preview["incoming_sequence"]

    def test_preview_pins_the_frozen_bundle_and_authority_model(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["preview"]
        preview = sc["preview"]
        assert preview["definition_bundle_id"] == sc["bundle"]
        assert len(preview["definition_bundle_sha256"]) == 64
        assert preview["authority_model"] == "projection_contract"
        assert len(preview["authority_model_definition_sha256"]) == 64
        assert preview["contract_id"] == ENTRY

    def test_preview_returns_both_requested_and_canonical_ids(
        self, snap: dict[str, Any]
    ) -> None:
        preview = snap["scenarios"]["preview"]["preview"]
        assert preview["requested_operation_id"]
        assert preview["canonical_operation_id"]
        assert preview["canonical_application_id"]

    def test_a_drifted_contract_is_refused(self, snap: dict[str, Any]) -> None:
        """按 registry 当前 alias 渲染历史 operation ⇒ 拒绝（AC 6.2 / 7.10）。"""
        assert (
            snap["scenarios"]["preview"]["drift_error"] == "frozen_contract_digest_drift"
        )

    def test_cross_scope_preview_is_a_uniform_404(self, snap: dict[str, Any]) -> None:
        """声明另一个 wp ⇒ 与「不存在」同一语义，不得泄露 operation 是否存在。"""
        from app.services.workpaper_sync.request_application import (
            OperationScopeNotVisibleError,
        )

        assert snap["scenarios"]["preview"]["cross_scope_error"] == (
            OperationScopeNotVisibleError.error_code
        ), snap["scenarios"]["preview"]["cross_scope_error"]


# ═══════════════════════════════════════════════════════════════════════════
# P36 / P65 resolve proceed：折叠后发布 + 裁决轨迹
# ═══════════════════════════════════════════════════════════════════════════


class TestResolveProceeds:
    def test_decision_is_proceed_and_maps_to_200(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["resolve_ok"]
        assert sc["outcome"]["decision"] == "proceed", sc["outcome"]
        assert sc["outcome"]["http_status"] == 200
        assert sc["outcome"]["reject_code"] == "OK"

    def test_the_published_projection_is_the_folded_one(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 P65：落库 digest = `apply_resolutions` 结果，**不等于** `merge.merged`。"""
        sc = snap["scenarios"]["resolve_ok"]
        assert sc["folded_sha"] != sc["merged_sha"], "前提不成立：两侧本就相同"
        published = [
            v for v in sc["after"]["version_rows"] if v["source"] == "conflict_resolution"
        ]
        assert len(published) == 1, sc["after"]["version_rows"]
        assert published[0]["projection_sha256"] == sc["folded_sha"]
        assert published[0]["projection_sha256"] != sc["merged_sha"]

    def test_revision_advanced_exactly_once(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["resolve_ok"]
        assert sc["after"]["revision"] == sc["before"]["revision"] + 1
        assert sc["after"]["version_count"] == sc["before"]["version_count"] + 1
        assert sc["outcome"]["revision_after"] == sc["after"]["revision"]
        assert sc["outcome"]["revision_before"] == sc["before"]["revision"]

    def test_no_second_operation_or_application(self, snap: dict[str, Any]) -> None:
        """Property 38 的 resolve 面：复用同一 append-only timeline。"""
        sc = snap["scenarios"]["resolve_ok"]
        assert sc["after"]["operation_count"] == sc["before"]["operation_count"]
        assert sc["after"]["application_count"] == sc["before"]["application_count"]

    def test_the_resolution_trail_was_written(self, snap: dict[str, Any]) -> None:
        """AC 8.6：actor / 时间 / 选择结果 / 落地值都落在冲突行上。"""
        sc = snap["scenarios"]["resolve_ok"]
        assert sc["outcome"]["conflict_rows_marked"] == 1
        resolved = [c for c in sc["after"]["conflicts"] if c["resolution"]]
        assert len(resolved) == 1, sc["after"]["conflicts"]
        row = resolved[0]
        assert row["has_actor"] and row["has_time"]
        assert '"take_incoming"' in row["resolution"], row["resolution"]
        assert row["resolved_value"] and '"C"' in row["resolved_value"], row
        # 反向：裁决前这一行没有轨迹（否则轨迹与事实脱钩）。
        assert all(not c["resolution"] for c in sc["before"]["conflicts"])

    def test_entry_pointer_and_room_baseline_moved(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["resolve_ok"]
        assert (
            sc["after"]["entry_pointer_representation_id"]
            != sc["before"]["entry_pointer_representation_id"]
        )
        assert sc["after"]["room_last_applied"] != sc["before"]["room_last_applied"]
        assert "rematerialize" in sc["after"]["representation_reasons"]


# ═══════════════════════════════════════════════════════════════════════════
# P36 五种判定：rejected / superseded / fold / rebase
# ═══════════════════════════════════════════════════════════════════════════


def _unchanged(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        k: (before.get(k), after.get(k))
        for k in set(before) | set(after)
        if before.get(k) != after.get(k)
    }


class TestResolveFenceRejections:
    def test_generation_change_is_rejected_with_its_own_reason(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["resolve_rejected"]
        assert sc["raised"]["type"] == "ResolveFenceRejectedError", sc["raised"]
        assert sc["raised"]["code"] == "resolve_fence_rejected"
        assert sc["raised"]["reason"] == "room_generation_changed"

    def test_rejection_has_zero_side_effects(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["resolve_rejected"]
        assert _unchanged(sc["before"], sc["after"]) == {}, _unchanged(
            sc["before"], sc["after"]
        )

    def test_newer_different_application_supersedes(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["resolve_superseded"]
        assert sc["raised"]["type"] == "ResolveSupersededError", sc["raised"]
        assert sc["raised"]["code"] == "resolve_conflict_superseded"
        assert sc["raised"]["reason"] == "newer_canonical_application"
        assert _unchanged(sc["before"], sc["after"]) == {}

    def test_same_application_higher_sequence_only_folds(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 P36 核心：same-app 抬 sequence 只 fold，**绝不**判自己 stale。"""
        sc = snap["scenarios"]["resolve_fold"]
        assert sc["raised"] == {}, sc["raised"]
        assert sc["outcome"] is not None
        assert sc["outcome"]["decision"] == "fold", sc["outcome"]
        assert sc["outcome"]["fence_reason"] == "same_application_sequence_fold"
        assert sc["outcome"]["reject_code"] == "SEQUENCE_FOLDED"
        assert sc["outcome"]["http_status"] == 200
        assert sc["outcome"]["normalized_effective_request_sequence"] == 7, (
            "没有规范化到最新 effective sequence"
        )
        # 而且它**真的继续**了同一 conflict set：revision 推进、裁决落地。
        assert sc["after"]["revision"] == sc["before"]["revision"] + 1
        assert sc["outcome"]["conflict_rows_marked"] == 1

    def test_current_revision_change_rebases_and_rebuilds_conflicts(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["resolve_rebase"]
        assert sc["raised"]["type"] == "ResolveRebaseRequiredError", sc["raised"]
        assert sc["raised"]["code"] == "resolve_rebase_required"
        assert sc["raised"]["rebased_count"] == 1, sc["raised"]
        assert len(str(sc["raised"]["rebased_digest"] or "")) == 64
        # rebase **不**推进 revision（它只重建冲突集）。
        assert sc["after"]["revision"] == sc["before"]["revision"]
        assert sc["after"]["version_count"] == sc["before"]["version_count"]

    def test_empty_resolutions_are_refused(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["retry_gate"]
        assert sc["empty_resolve"]["code"] == "resolve_requires_resolutions", (
            sc["empty_resolve"]
        )

    def test_revoked_initiator_blocks_the_resolve(self, snap: dict[str, Any]) -> None:
        """AC 10.10 / P43 的 resolve 面：期间发起人被撤销 ⇒ 拒绝、零副作用。

        🔴 观测侧必须 fail closed：撤销后查不到 participant 行时若返回 0（或冻结值本身），
        「fence 变化即拒绝」就退化成重言式。判据是「permission epoch 变化」这条 reason，
        而不是笼统的 409。
        """
        sc = snap["scenarios"]["resolve_initiator_revoked"]
        assert sc["raised"]["type"] == "ResolveFenceRejectedError", sc["raised"]
        assert sc["raised"]["reason"] == "permission_epoch_changed", sc["raised"]
        assert _unchanged(sc["before"], sc["after"]) == {}


# ═══════════════════════════════════════════════════════════════════════════
# P38 retry
# ═══════════════════════════════════════════════════════════════════════════


class TestRetry:
    def test_nullable_operation_retry_is_refused_with_zero_side_effects(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["retry_gate"]
        assert sc["null_retry"]["type"] == "RecoveryCaseRetryForbiddenError"
        assert sc["null_retry"]["code"] == (
            "recovery_case_requires_claim_before_retry"
        )
        assert _unchanged(sc["before"], sc["after"]) == {}

    def test_retry_reuses_the_same_timeline(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["retry_reuse"]
        assert sc["outcome"]["result"] in ("applied", "refresh_required"), sc["outcome"]
        assert sc["outcome"]["attempt"] == 2
        assert sc["after"]["operation_count"] == sc["before"]["operation_count"]
        assert sc["after"]["application_count"] == sc["before"]["application_count"]

    def test_retry_never_touches_the_command_service(
        self, snap: dict[str, Any]
    ) -> None:
        """Property 38：零 forcesave。adapter 只被 extract/materialize 调用。"""
        sc = snap["scenarios"]["retry_reuse"]
        assert sc["adapter_calls"], "adapter 一次都没被调用 ⇒ retry 根本没执行"
        assert all(
            call.startswith(("extract", "materialize", "verify_"))
            for call in sc["adapter_calls"]
        ), sc["adapter_calls"]


# ═══════════════════════════════════════════════════════════════════════════
# P37 / P67 rollback
# ═══════════════════════════════════════════════════════════════════════════


class TestRollback:
    def test_rollback_creates_a_new_version_and_never_rewinds(
        self, snap: dict[str, Any]
    ) -> None:
        """Property 37：回滚后 current revision **大于**回滚前。"""
        sc = snap["scenarios"]["rollback"]
        assert sc["before"]["revision"] == 1, sc["before"]
        assert sc["rolled"]["revision_unchanged"] is False
        assert sc["mid"]["revision"] > sc["before"]["revision"]
        assert sc["rolled"]["revision_after"] == sc["mid"]["revision"]
        assert sc["mid"]["version_count"] == sc["before"]["version_count"] + 1

    def test_history_rows_and_files_are_untouched(self, snap: dict[str, Any]) -> None:
        """AC 8.7：不得删除或原地改写历史版本。"""
        sc = snap["scenarios"]["rollback"]
        before_by_rev = {v["revision"]: v for v in sc["before"]["version_rows"]}
        mid_by_rev = {v["revision"]: v for v in sc["mid"]["version_rows"]}
        for revision, row in before_by_rev.items():
            assert mid_by_rev[revision] == row, (revision, row, mid_by_rev.get(revision))
        assert sc["source_file_exists"], "历史 representation 文件不在了"

    def test_the_new_version_carries_the_rollback_source_bucket(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["rollback"]
        new = [
            v
            for v in sc["mid"]["version_rows"]
            if v["revision"] == sc["mid"]["revision"]
        ]
        assert len(new) == 1
        assert new[0]["source"] == "rollback", new[0]
        assert new[0]["projection_sha256"] == sc["rolled"]["projection_sha256"]
        assert "rollback" in sc["mid"]["representation_reasons"]

    def test_the_rolled_back_projection_equals_the_historical_one(
        self, snap: dict[str, Any]
    ) -> None:
        """新版本的 projection 必须等于回滚源的 projection（不是「随便新建一版」）。"""
        sc = snap["scenarios"]["rollback"]
        source = [
            v
            for v in sc["before"]["version_rows"]
            if v["id"] == sc["rolled"]["source_version_id"]
        ]
        assert len(source) == 1, sc["rolled"]["source_version_id"]
        assert source[0]["projection_sha256"] == sc["rolled"]["projection_sha256"]

    def test_unchanged_projection_means_zero_writes(self, snap: dict[str, Any]) -> None:
        """AC 6.18 / 9.10 / Property 67：业务 projection 未变化 ⇒ revision 不变、零写入。"""
        sc = snap["scenarios"]["rollback"]
        assert sc["noop"]["revision_unchanged"] is True, sc["noop"]
        assert sc["noop"]["new_content_version_id"] is None
        assert sc["noop"]["new_representation_id"] is None
        assert sc["noop"]["revision_after"] == sc["noop"]["revision_before"]
        assert _unchanged(sc["mid"], sc["after"]) == {}, _unchanged(
            sc["mid"], sc["after"]
        )

    def test_stale_expected_revision_is_refused(self, snap: dict[str, Any]) -> None:
        """numeric revision 只作乐观锁：失配必须拒，不得按旧值创建新版本（AC 8.7）。"""
        sc = snap["scenarios"]["rollback_stale_expectation"]
        assert sc["before"]["revision"] == 1, sc["before"]
        assert sc["raised"]["type"] == "RollbackRevisionRewindError", sc["raised"]
        assert sc["raised"]["code"] == "rollback_revision_rewind_forbidden"
        assert _unchanged(sc["before"], sc["after"]) == {}

    def test_incoming_artifact_can_never_be_a_rollback_source(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 8.7 / 8.10：`incoming` 连 representation 都造不出来（DB 层第一道门）。"""
        sc = snap["scenarios"]["rollback_bad_source"]
        assert sc["db_layer"], "DB 层没有拒绝「representation 指向 incoming artifact」"
        assert sc["db_layer"]["mentions_incoming"] is True, sc["db_layer"]

    def test_unpublished_canonical_artifact_is_refused_by_the_service(
        self, snap: dict[str, Any]
    ) -> None:
        """`canonical` 但 `staged` 是 DB 允许的形态 ⇒ 必须由服务层准入判据拒。

        判据类型必须是**本域的** `RollbackSourceNotPublishedError` 而不是 resolver 的
        通用 `ArtifactNotPublishedError`：后者意味着准入判据排在 resolver 之后、
        在所有可达输入上被遮蔽（provably dead）。
        """
        sc = snap["scenarios"]["rollback_bad_source"]
        assert sc["raised"]["type"] == "RollbackSourceNotPublishedError", sc["raised"]
        assert sc["raised"]["code"] == "rollback_source_not_published"
        assert _unchanged(sc["before"], sc["after"]) == {}


class TestWhoMaySubmitAdjudications:
    """AC 8.4 的三个拒绝理由，各自一条判据（第三个在 `TestResolveFenceRejections`）。"""

    def test_a_user_without_edit_permission_is_refused_with_the_403_type(
        self, snap: dict[str, Any]
    ) -> None:
        """仅具备底稿编辑权限者可提交裁决 —— 403 分型，与 404「不存在/越权」不混。"""
        from app.services.workpaper_sync.request_application import (
            OperationScopeNotVisibleError,
            ScopeAuthorizationDeniedError,
        )

        sc = snap["scenarios"]["resolve_authorization"]
        assert sc["no_permission"]["type"] == "ScopeAuthorizationDeniedError", (
            sc["no_permission"]
        )
        assert sc["no_permission"]["code"] == ScopeAuthorizationDeniedError.error_code
        assert (
            ScopeAuthorizationDeniedError.error_code
            != OperationScopeNotVisibleError.error_code
        ), "403 与 404 共用 error_code ⇒ 「scope 可见但不许操作」与「不存在」不可分辨"

    def test_the_permission_gate_fires_before_any_authorization_probe(
        self, snap: dict[str, Any]
    ) -> None:
        """authorization-before-resource：被拒时连 probe 都不该被调用（零业务读）。"""
        sc = snap["scenarios"]["resolve_authorization"]
        assert sc["probe_calls_when_unauthorized"] == [], (
            f"授权否决后仍观测了业务事实：{sc['probe_calls_when_unauthorized']}"
        )
        assert _unchanged(sc["before"], sc["after_no_permission"]) == {}, _unchanged(
            sc["before"], sc["after_no_permission"]
        )

    def test_review_lock_or_archive_blocks_the_adjudication(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 复核锁定/归档 ⇒ 拒绝（本轮修掉的生产缺陷）。

        修之前：coordinator 在 durable 之后**不抛异常**（AC 5.7/5.8 要求保留 incoming），
        而 `resolve` 不看 `outcome.result` ⇒ 冲突行被标成「已裁决」、返回 200，
        而 revision/version/pointer 一个都没动。实测 `conflict_rows_marked=1`。

        两层判据：服务层类型说明「不可重试」，`apply_error_code` 保留**哪一条** fence。
        """
        sc = snap["scenarios"]["resolve_authorization"]
        assert sc["workflow_locked"]["type"] == "ResolveAuthorizationStaleError", (
            sc["workflow_locked"]
        )
        assert sc["workflow_locked"]["code"] == "resolve_authorization_stale"
        assert sc["workflow_locked"]["apply_error_code"] == (
            "final_fence_workflow_locked"
        ), "十条 fence 的归因丢了 —— 只说「授权失效」等于让运维猜是哪一条"
        assert sc["workflow_probe_calls"], "probe 一次都没被调用 ⇒ 这条 fence 没真跑"

    def test_the_refused_application_is_left_in_a_non_retryable_terminal_state(
        self, snap: dict[str, Any]
    ) -> None:
        """拒绝不是空操作：application 落 `authorization_stale`（AC 10.10 末句）。

        这条同时解释了为什么下一条判据必须换一个 world —— 同一 application 再来一次
        只会撞 `ApplicationTerminalStaleError`，测到的就不是 probe 的可见性分支了。
        """
        sc = snap["scenarios"]["resolve_authorization"]
        assert sc["application_state_after_workflow_lock"] == "authorization_stale", (
            sc["application_state_after_workflow_lock"]
        )

    def test_project_invisibility_is_a_separate_refusal(
        self, snap: dict[str, Any]
    ) -> None:
        """同一 probe 口的另一个分支必须分型：共用 code 时靠前那条永久不可达。"""
        sc = snap["scenarios"]["resolve_authorization"]
        assert sc["not_visible"]["type"] == "ResolveAuthorizationStaleError", (
            sc["not_visible"]
        )
        assert sc["not_visible"]["apply_error_code"] == (
            "final_fence_project_not_visible"
        ), sc["not_visible"]
        assert (
            sc["not_visible"]["apply_error_code"]
            != sc["workflow_locked"]["apply_error_code"]
        ), "可见性与 workflow 锁共用了 error_code ⇒ 靠前那条永久不可达"
        assert _unchanged(sc["visibility_before"], sc["visibility_after"]) == {}, (
            _unchanged(sc["visibility_before"], sc["visibility_after"])
        )

    def test_none_of_the_refusals_wrote_an_adjudication_trail(
        self, snap: dict[str, Any]
    ) -> None:
        """三次拒绝跑完，revision / version / pointer / 冲突行全部原样（P43 / AC 8.6）。"""
        sc = snap["scenarios"]["resolve_authorization"]
        assert _unchanged(sc["before"], sc["after"]) == {}, _unchanged(
            sc["before"], sc["after"]
        )
        for key in ("after", "visibility_after"):
            assert all(not c["resolution"] for c in sc[key]["conflicts"]), (
                f"被拒的裁决却写进了冲突行（{key}）—— 「已裁决」这条审计事实"
                "被记在一次没有落地的应用上"
            )


class TestDuplicateRequestedOperation:
    """requested id 是 terminal duplicate 时，四步读路径之**后**用的必须是 canonical id。

    AC 8.5 / Property 38。Task 23 的真库判据证明 `read_operation` 会正确跟随 duplicate；
    本类证明**本模块**在拿到 `CanonicalRead` 之后没有回头去用 requested id —— 那是一条
    静默错值路径（空预览 / 裁决轨迹标 0 行），AST 形态判据看不见它。
    """

    def test_the_second_delivery_really_became_a_direct_terminal_duplicate(
        self, snap: dict[str, Any]
    ) -> None:
        """前提自证：不是「造了个 duplicate 变量」，而是 V151 形态上的 direct duplicate。"""
        sc = snap["scenarios"]["resolve_via_duplicate"]
        # 去重的**前提**先自证：两个 delivery 是两行 artifact、但内容 digest 相同。
        # 少了这一条，「没造出 duplicate」会表现成下面某条断言的莫名失败。
        assert sc["incoming_artifact_first"] != sc["incoming_artifact_second"], (
            "两个 delivery 复用了同一行 incoming artifact —— 那不是 status 6/2 的形态"
        )
        assert sc["incoming_sha_first"] == sc["incoming_sha_second"], (
            "第二个 delivery 的 payload 字节与第一次不同 ⇒ application key 不同 ⇒ "
            "根本不会产生 duplicate（`_ooxml()` 的 zip 时间戳是秒级的）"
        )
        assert sc["application_again"] == sc["application"], (
            "同 payload 的第二个 delivery 没有命中同一 application —— "
            f"key 里混进了 request 身份？{sc['application_again']} != {sc['application']}"
        )
        primary = sc["shapes"][sc["primary_operation"]]
        dup = sc["shapes"][sc["duplicate_operation"]]
        assert primary["application_id"] == sc["application"], primary
        assert primary["duplicate_of"] is None, primary
        assert dup["application_id"] is None, (
            "duplicate 不得绑定 application（AC 5.5：只要求 canonical primary 绑定）"
        )
        assert dup["duplicate_of"] == sc["primary_operation"], dup
        assert dup["state"] == "duplicate", dup

    def test_preview_through_the_duplicate_returns_the_primary_conflicts(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 冲突必须按 canonical primary 读：按 requested 读会得到**空预览**。"""
        sc = snap["scenarios"]["resolve_via_duplicate"]
        preview = sc["preview"]
        assert preview["requested_operation_id"] == sc["duplicate_operation"]
        assert preview["canonical_operation_id"] == sc["primary_operation"]
        assert preview["followed_duplicate"] is True, preview
        assert preview["canonical_application_id"] == sc["application"]
        assert preview["conflict_count"] >= 1, (
            "用 duplicate id 预览得到 0 条冲突 —— 冲突是按 requested id 读的，"
            "而冲突行挂在 canonical primary 上"
        )

    def test_resolve_through_the_duplicate_publishes_the_folded_projection(
        self, snap: dict[str, Any]
    ) -> None:
        """裁决经 duplicate 提交仍必须折叠后发布，且 revision 恰进一格。"""
        sc = snap["scenarios"]["resolve_via_duplicate"]
        assert sc["outcome"]["decision"] == "proceed", sc["outcome"]
        assert sc["outcome"]["requested_operation_id"] == sc["duplicate_operation"]
        assert sc["outcome"]["canonical_operation_id"] == sc["primary_operation"]
        assert sc["after"]["revision"] == sc["before"]["revision"] + 1
        assert sc["folded_sha"] != sc["merged_sha"], "前提不成立：两侧本就相同"
        published = [
            v for v in sc["after"]["version_rows"]
            if v["revision"] == sc["after"]["revision"]
        ]
        assert len(published) == 1, sc["after"]["version_rows"]
        assert published[0]["projection_sha256"] == sc["folded_sha"], (
            "经 duplicate 提交的裁决落库值不是折叠结果"
        )

    def test_the_resolution_trail_lands_on_the_primary_conflict_rows(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 AC 8.6：轨迹必须真标到 canonical primary 的冲突行上。

        按 requested id 回写时（G01/G02 的写侧）内容已经发布、revision 已 +1，
        而轨迹写入抛 `ScopeIntegrityError` —— 判据落在「行上真有 resolution/actor/时间」，
        不是「调用没抛异常」。
        """
        sc = snap["scenarios"]["resolve_via_duplicate"]
        assert sc["outcome"]["conflict_rows_marked"] >= 1, (
            "裁决轨迹标了 0 行 —— `mark_conflicts_resolved` 用的是 requested id"
        )
        resolved = [c for c in sc["after"]["conflicts"] if c["resolution"]]
        assert len(resolved) == sc["outcome"]["conflict_rows_marked"]
        assert all(c["has_actor"] and c["has_time"] for c in resolved), resolved

    def test_no_third_operation_or_second_application_was_created(
        self, snap: dict[str, Any]
    ) -> None:
        """Property 38：duplicate 路径复用同一 timeline，零新建。"""
        sc = snap["scenarios"]["resolve_via_duplicate"]
        assert sc["after"]["operation_count"] == sc["before"]["operation_count"]
        assert sc["after"]["application_count"] == sc["before"]["application_count"]
        assert sc["before"]["operation_count"] == 2, (
            f"前提：primary + duplicate 两条 operation，实得 "
            f"{sc['before']['operation_count']}"
        )
        assert sc["before"]["application_count"] == 1, sc["before"]


class TestOpaqueVersionScope:
    def test_same_numeric_revision_lives_in_two_wps_under_different_uuids(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 8.7 末句的前提：numeric revision 会跨 wp 重复，UUID 不会。"""
        rows = snap["scenarios"]["version_scope"]["rows"]
        by_rev = [r for r in rows if int(r["revision"]) == 0]
        assert len(by_rev) == 2, rows
        assert len({r["wp_id"] for r in by_rev}) == 2, "两行不属于两个不同的 wp"
        assert len({r["id"] for r in by_rev}) == 2, "两个 wp 的 revision 0 共用了 UUID"

    def test_cross_wp_uuid_and_unknown_uuid_share_one_404(
        self, snap: dict[str, Any]
    ) -> None:
        """越权与不存在必须无法区分（否则可探测别的 wp 有哪些版本）。"""
        sc = snap["scenarios"]["version_scope"]
        assert sc["cross_wp"]["type"] == "ContentVersionNotFoundError", sc["cross_wp"]
        assert sc["unknown"]["type"] == "ContentVersionNotFoundError", sc["unknown"]
        assert sc["cross_wp"]["code"] == sc["unknown"]["code"] == (
            "content_version_not_found"
        )

    def test_the_scope_index_door_is_the_one_that_refuses(
        self, snap: dict[str, Any]
    ) -> None:
        """authorization-before-resource：拒绝必须发生在 **scope index** 那一道门。

        🔴 只断言异常类型时，删掉 scope 门之后业务行门会接住同一输入并抛同一类型 ⇒
        变异检验判 GREEN（本任务首轮实测如此）。`refused_at` 是**内部**标记（不进
        `error_code`、不进响应信封），因此断言它不会引入存在性泄露。
        """
        sc = snap["scenarios"]["version_scope"]
        assert sc["cross_wp"]["refused_at"] == "scope_index", sc["cross_wp"]
        assert sc["unknown"]["refused_at"] == "scope_index", sc["unknown"]

    def test_neither_workpaper_was_touched(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["version_scope"]
        for key in ("db_a", "db_b"):
            assert sc[key]["revision"] == 0, (key, sc[key])
            assert sc[key]["version_count"] == 1


class TestConflictRowLifecycle:
    """AC 8.1 / 8.6 的仓储层不变量：行永不删除，轨迹永不静默缺失。"""

    def test_disappeared_conflicts_are_superseded_not_deleted(
        self, snap: dict[str, Any]
    ) -> None:
        """rebase 后消失的冲突必须被打 `superseded_at` —— 行仍在，只是不再 live。"""
        sc = snap["scenarios"]["conflict_row_lifecycle"]
        assert len(sc["rows_before"]) >= 1, sc["rows_before"]
        assert sc["shrink"]["superseded"] == len(sc["rows_before"]), sc["shrink"]
        assert sc["shrink"]["inserted"] == 0 and sc["shrink"]["updated"] == 0
        # 行数不变（不删行），但全部变成 superseded。
        assert len(sc["rows_after_shrink"]) == len(sc["rows_before"])
        assert all(row["superseded"] is True for row in sc["rows_after_shrink"]), (
            sc["rows_after_shrink"]
        )

    def test_a_resolution_for_an_unknown_conflict_is_refused(
        self, snap: dict[str, Any]
    ) -> None:
        """裁决指向不存在的冲突 ⇒ 抛，不得静默跳过（静默 = 轨迹不全）。"""
        sc = snap["scenarios"]["conflict_row_lifecycle"]
        assert sc["unknown_trail"], "未知裁决 key 被静默接受了"
        assert sc["unknown_trail"]["type"] == "ScopeIntegrityError", sc["unknown_trail"]
