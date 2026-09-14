# -*- coding: utf-8 -*-
"""Task 26 真实 PostgreSQL 行为守卫：canonical rematerialize、最终 fence 与双基线。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 26
Requirements: 2.9, 4.2, 4.3, 4.5, 4.6, 4.11, 4.12, 5.8, 6.8, 6.9, 6.11,
8.9, 8.10, 8.11, 8.12, 10.10
Properties: **P14 / P19 / P25 / P26 / P27 / P29 / P38 / P43 / P62 / P65**

═══ 为什么必须真库 ═══

本任务的判据几乎全是**跨行、跨表、跨事务**的：

* P65 —— `application.merged_projection_sha256` 必须**逐字节等于**落盘 projection
  artifact 的 sha256，且 result representation 的 bundle identity 必须等于 application
  冻结值。这是两张表 + 一个文件的三向比对。
* P62 —— server last-applied 推进而 client-confirmed 不推进，只有在真库上读 room 行
  才看得见；「下一次 forcesave 被拒」还要真的调一次 Task 21 的资格门。
* P43 —— fence 必须在 **DB commit 之前**失败。判据是「revision 与 pointer 逐列未变」，
  离线断言不了。
* P19 —— durable 之后失败必须保留 incoming 并让 operation 落可重试 error，同时
  content/representation pointer 与双基线一动不动。
* P38 —— retry 不得新建 operation/application：判据是**行计数**。

`DATABASE_URL` 非 PostgreSQL 时**直接失败而不是 skip** —— 与 Task 10/15/21/22/23 同约定：
skip 等于静默抹掉本任务唯一判据。

═══ 隔离与采集 ═══

scratch schema `tmp_task26_oh_<hex>` + 独立文件根 `tmp_task26_store_*`，结束
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

_SCHEMA_PREFIX = "tmp_task26_oh_"

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

_EXTRA_ENUM_LABELS: dict[str, tuple[str, ...]] = {}


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _opt(value: object) -> str | None:
    """可空 UUID → `str | None`。`str(None) == "None"` 会把「没写上」判成「写上了」。"""
    return None if value is None else str(value)


def _err(exc: BaseException) -> str:
    import traceback

    frames = traceback.extract_tb(exc.__traceback__)[-5:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


def _ooxml(*, projection_values: dict[str, Any], unmanaged: bytes = b"<formulas/>") -> bytes:
    """真 OOXML zip 容器 + `_gt_sync/projection.json` 受管部件。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("xl/workbook.xml", b'<?xml version="1.0"?><root/>')
        zf.writestr("xl/unmanaged.xml", unmanaged)
        zf.writestr(
            "_gt_sync/projection.json",
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
# 契约与 adapter 替身（真写真读；不是 mock）
# ═══════════════════════════════════════════════════════════════════════════


def _contract_payload() -> dict[str, Any]:
    from app.services.workpaper_sync import contracts as C

    return {
        "schema_version": C.CONTRACT_SCHEMA_VERSION,
        "contract_id": ENTRY,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": _d("task26-template"),
        "instrumentation_definition_sha256": _d("task26-instrumentation"),
        "template": {
            "relative_path": "D/D2 应收账款.xlsx",
            "template_sha256": _d("task26-template-blob"),
            "normalized_structure_hash": _d("task26-template-structure"),
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
    """真 OOXML 容器 + JSON 受管部件的载体替身（与 Task 15 PG 守卫同形）。

    `materialize` 真写 zip、`extract` 真读回来 ⇒ roundtrip 等值判据在真实执行上生效。
    真正的 Excel/Word engine 归 Tasks 36~38 / 59~61。

    `fail_on` / `drop_keys` / `break_unmanaged` 是**注入缺陷**开关，用于证明
    durable-后失败路径（P19）与 roundtrip/未管理区域判据（P29 / AC 8.11）可证伪。
    """

    adapter_id = ENTRY
    document_type = "xlsx"
    contract_version = "1.0.0"

    def __init__(
        self,
        *,
        fail_on: str | None = None,
        drop_keys: tuple[str, ...] = (),
        break_unmanaged: bool = False,
    ) -> None:
        self.fail_on = fail_on
        self.drop_keys = drop_keys
        self.break_unmanaged = break_unmanaged
        self.calls: list[str] = []

    async def read_current_projection(self, ctx):  # pragma: no cover - 本任务不用
        raise NotImplementedError

    async def stage_projection_mutation(self, ctx, merged, *, expected_revision):
        raise NotImplementedError  # pragma: no cover - 本任务不用

    def materialize(self, *, substrate, projection, output, contract):
        from app.services.workpaper_sync.adapters.base import MaterializeResult

        self.calls.append("materialize")
        if self.fail_on == "materialize":
            raise RuntimeError("注入缺陷：materialize 失败（模拟载体写入异常）")
        values = {
            key: {
                "value": (str(v.value) if isinstance(v.value, Decimal) else v.value),
                "value_type": v.value_type.value,
                "mode": v.mode.value,
                "row_key": v.row_key,
            }
            for key, v in projection.values.items()
            if key not in self.drop_keys
        }
        blob = _ooxml(
            projection_values=values,
            unmanaged=b"<tampered/>" if self.break_unmanaged else b"<formulas/>",
        )
        Path(output).write_bytes(blob)
        return MaterializeResult(
            output_path=Path(output),
            document_type=projection.document_type,
            artifact_sha256=hashlib.sha256(blob).hexdigest(),
            structure_hash=_d("task26-structure"),
            identity_inventory_sha256=_d("task26-identity"),
            managed_field_count=len(values),
        )

    def extract(self, *, artifact, contract):
        from app.services.workpaper_sync import contracts as C
        from app.services.workpaper_sync.adapters.base import FieldValue, Projection

        self.calls.append(f"extract:{Path(artifact).name}")
        if self.fail_on == "extract":
            raise RuntimeError("注入缺陷：extract 失败（模拟结构漂移）")
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
    """真执行的 :class:`AuthorizationProbe` 替身。

    刻意记录每次调用（含时刻）：`test_probe_actually_executed_before_each_fence` 用它
    证明探针**真被跑了**而不是被短路 —— 硬编码返回值的实现会让 fence 变成摆设，
    而那种缺陷在「最终有没有报错」上看不出来。
    """

    def __init__(self, *, visible: bool = True, locked: bool = False) -> None:
        self.visible = visible
        self.locked = locked
        self.calls: list[tuple[str, str]] = []

    async def observe(self, *, project_id, wp_id, entry_id):
        self.calls.append((str(wp_id), _now().isoformat()))
        return {"project_visible": self.visible, "workflow_locked": self.locked}


class _FlippingProbe(_RecordingProbe):
    """第 N 次观测起翻转 visibility —— 用来把撤权精确打在两道 fence 之间。

    `flip_at=1` ⇒ publish 前那道就失败（一次 adapter materialize 已发生但未 publish）；
    `flip_at=2` ⇒ publish 已发生、写库前那道失败（判据：revision 与 pointer 未变，
    文件侧只留不可见 orphan）。
    """

    def __init__(self, *, flip_at: int) -> None:
        super().__init__()
        self.flip_at = flip_at

    async def observe(self, *, project_id, wp_id, entry_id):
        self.calls.append((str(wp_id), _now().isoformat()))
        visible = len(self.calls) < self.flip_at
        return {"project_visible": visible, "workflow_locked": False}


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
        WorkpaperContentApplicationEvent,
        WorkpaperContentRepresentation,
        WorkpaperContentVersion,
        WorkpaperOoRoom,
        WorkpaperSyncEntryState,
        WorkpaperSyncOperation,
        WorkpaperSyncOperationEvent,
    )
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
        CloseIntentState,
        ParticipantMode,
        RequestKind,
        compute_contributor_snapshot_digest,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.request_application import RequestApplicationService
    from app.services.workpaper_sync.resolution import CanonicalResolutionService
    from app.services.workpaper_sync.rooms import (
        RoomNotWritableError,
        RoomScope,
        RoomService,
        mint_route_credential,
    )

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 26 的判据是跨表跨事务的（merged digest ↔ projection artifact、"
            "fence 在 commit 前失败、双基线分离、retry 行计数），必须真实 PostgreSQL；"
            f"当前 DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}。"
            "此处**不 skip** —— skip 等于静默抹掉本任务唯一判据。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task26_store_"))
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

        # ═══ definitions + approved bundle（跨 world 共用；bundle 不是 wp-scoped）═══
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
                "authority_alt": "authority_model",
                "bundle_alt": "bundle",
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
                kind="template", logical_id="task26.tpl", semantic_version="1.0.0",
                blob_artifact_id=art["tpl"].id, sha256=_d("task26-template"),
                structure_hash=_d("task26-tpl-structure"), source_commit="task26",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation", logical_id="task26.instr", semantic_version="1.0.0",
                blob_artifact_id=art["instr"].id, sha256=_d("task26-instrumentation"),
                structure_hash=_d("task26-instr-structure"), source_commit="task26",
            )
            contract_def = await repo.create_definition_artifact(
                kind="contract", logical_id="task26.contract", semantic_version="1.0.0",
                blob_artifact_id=art["contract"].id,
                # contract definition 的 digest 必须等于 SyncContract 的 canonical digest：
                # `SyncContext.assert_frozen_identity_consistent` 用它三向锁死。
                sha256=contract.canonical_sha256, source_commit="task26",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task26.authority",
                semantic_version="1.0.0", blob_artifact_id=art["authority"].id,
                sha256=_d("task26-authority"),
                authority_model_type="projection_contract", source_commit="task26",
            )
            authority_alt = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task26.authority.alt",
                semantic_version="1.0.1", blob_artifact_id=art["authority_alt"].id,
                sha256=_d("task26-authority-alt"),
                authority_model_type="projection_contract", source_commit="task26",
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
            bundle_alt = await repo.create_definition_bundle(
                authority_model_definition_id=authority_alt.id,
                slots=_slots(),
                canonical_payload_artifact_id=art["bundle_alt"].id,
                canonical_payload_sha256=D.bundle_canonical_digest(
                    authority_model="projection_contract",
                    authority_model_definition_sha256=authority_alt.sha256,
                    slots=_slots(),
                ),
            )
            await s.commit()
            world.update(
                bundle=bundle.id,
                bundle_alt=bundle_alt.id,
                authority=authority.id,
                authority_alt=authority_alt.id,
                contract_def=contract_def.id,
            )
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

        # ═══ 每个场景一个独立 wp（互不污染 revision / room / pointer）═══════
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
                    adapter_id=ENTRY, adapter_build_digest=_d("task26-adapter"),
                    structure_hash=_d(f"task26-structure-{tag}"),
                    identity_inventory_sha256=_d(f"task26-identity-{tag}"),
                    reason="content_commit",
                )
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

        async def _build_room(
            entry: dict[str, Any], *, second_participant: bool = False
        ) -> dict[str, Any]:
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
                pb_id = None
                if second_participant:
                    pb = await svc.join_participant(
                        scope, room_id=room.id, user_id=user_b,
                        mode=ParticipantMode.edit, permission_epoch=5,
                        lease_token="lease-b",
                    )
                    pb_id = pb.id
                frozen = await svc.frozen_bundle_identity(world["bundle"])
                conf = await svc.confirm_descriptor(
                    scope, room_id=room.id, participant_id=pa.id,
                    representation_id=entry["rep1"], content_version_id=entry["cv0"],
                    projection_sha256=entry["projection_sha256"],
                    idempotency_key=f"ready-{room.id}", expected_bundle=frozen,
                )
                if second_participant:
                    await svc.confirm_descriptor(
                        scope, room_id=room.id, participant_id=pb_id,
                        representation_id=entry["rep1"], content_version_id=entry["cv0"],
                        projection_sha256=entry["projection_sha256"],
                        idempotency_key=f"ready-b-{room.id}", expected_bundle=frozen,
                    )
                await s.commit()
                return {
                    "scope": scope,
                    "room": room.id,
                    "doc_key": room.doc_key,
                    "participant": pa.id,
                    "participant_b": pb_id,
                    "confirmation": conf[0].id if isinstance(conf, tuple) else conf.id,
                }

        async def _accept_request(
            env: dict[str, Any],
            *,
            key: str,
            contributor_user_ids: list[uuid.UUID] | None = None,
        ) -> dict[str, Any]:
            contributors = contributor_user_ids or [user_a]
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                ras = RequestApplicationService(repo)
                accepted = await ras.freeze_and_persist_request(
                    env["scope"],
                    room_id=env["room"],
                    participant_id=env["participant"],
                    idempotency_key=key,
                    client_edit_epoch=3,
                    contributor_user_ids=contributors,
                    created_by=user_a,
                )
                # contributor 快照必须真落库：最终 fence 会**重算**当下仍合法的
                # contributor digest 并与 application 冻结值比对（不是拿冻结值跟自己比）。
                rooms = RoomService(repo)
                cred = mint_route_credential(
                    room_id=env["room"], generation=1, doc_key=env["doc_key"]
                )
                await rooms.record_contributor_snapshot(
                    operation_id=accepted.operation.id,
                    room_id=env["room"],
                    initiator_participant_id=env["participant"],
                    route_credential=cred,
                    # initiator 自己恒被记入；其余 contributor 按 OO history 传入。
                    oo_contributor_user_ids=[
                        u for u in contributors if u != user_a
                    ],
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
                # `DELIVERY_EDGES` 只允许 `received → downloading → durable`：
                # 归组阶段会把它推到 durable，所以这里必须先走 downloading，
                # 否则 `bind_delivery_to_application` 撞非法状态边。
                await repo.mark_delivery_downloading(delivery_id=delivery.id)
                staged = artifacts.stage_incoming(
                    project_id=project, wp_id=entry["wp"], delivery_id=delivery.id,
                    chunks=[payload], document_type="xlsx",
                )
                sealed = artifacts.seal_incoming(staged, delivery_id=delivery.id)
                incoming = await repo.register_artifact(
                    project_id=project, wp_id=entry["wp"],
                    kind=ArtifactKind.incoming,
                    state=sealed.state,
                    relative_path=sealed.relative_path,
                    sha256=sealed.sha256, size_bytes=sealed.size_bytes,
                    document_type="xlsx", source_delivery_id=delivery.id,
                )
                await s.commit()
                return {
                    "delivery": delivery.id,
                    "incoming": incoming.id,
                    "sha256": sealed.sha256,
                    "state": sealed.state.value,
                    "relative_path": sealed.relative_path,
                }

        async def _correlate(
            env: dict[str, Any], entry: dict[str, Any], req: dict[str, Any],
            inc: dict[str, Any],
        ) -> uuid.UUID:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                ras = RequestApplicationService(repo)
                outcome = await ras.correlate(
                    operation_id=req["operation"],
                    incoming_artifact_id=inc["incoming"],
                    current_revision=0,
                    adapter_id=ENTRY,
                    delivery_id=inc["delivery"],
                )
                await s.commit()
                return outcome.application.id

        def _coordinator(session, *, probe, artifacts_repo=None):
            repo = WorkpaperSyncRepository(session)
            store = artifacts_repo or artifacts
            resolution = CanonicalResolutionService(session, store)
            content = ContentMutationService(
                session=session, repository=repo, artifacts=store, resolution=resolution
            )
            rooms = RoomService(repo)
            return OH.OoToHtmlCoordinator(
                repo=repo,
                artifacts=store,
                resolution=resolution,
                content=content,
                rooms=rooms,
                requests=RequestApplicationService(repo, rooms),
                probe=probe,
            )

        async def _db_state(wp: uuid.UUID, room_id: uuid.UUID, app_id: uuid.UUID) -> dict:
            async with Session() as s:
                revision = (
                    await s.execute(
                        sa.text("SELECT content_revision FROM working_paper WHERE id = :w"),
                        {"w": wp},
                    )
                ).scalar_one()
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
                room = (
                    await s.execute(
                        sa.select(WorkpaperOoRoom).where(WorkpaperOoRoom.id == room_id)
                    )
                ).scalar_one()
                app = (
                    await s.execute(
                        sa.select(WorkpaperContentApplication).where(
                            WorkpaperContentApplication.id == app_id
                        )
                    )
                ).scalar_one()
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
                op_events = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperSyncOperationEvent)
                            .where(
                                WorkpaperSyncOperationEvent.operation_id.in_(
                                    [o.id for o in ops] or [uuid.uuid4()]
                                )
                            )
                        )
                    ).scalar_one()
                )
                app_events = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperContentApplicationEvent)
                            .where(
                                WorkpaperContentApplicationEvent.application_id == app_id
                            )
                        )
                    ).scalar_one()
                )
                app_count = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperContentApplication)
                            .where(WorkpaperContentApplication.wp_id == wp)
                        )
                    ).scalar_one()
                )
                versions = int(
                    (
                        await s.execute(
                            sa.select(sa.func.count())
                            .select_from(WorkpaperContentVersion)
                            .where(WorkpaperContentVersion.wp_id == wp)
                        )
                    ).scalar_one()
                )
                incoming = (
                    await s.execute(
                        sa.select(WorkpaperArtifact).where(
                            WorkpaperArtifact.id == app.incoming_artifact_id
                        )
                    )
                ).scalar_one()
                result_rep = None
                result_art = None
                if app.result_representation_id is not None:
                    result_rep = (
                        await s.execute(
                            sa.select(WorkpaperContentRepresentation).where(
                                WorkpaperContentRepresentation.id
                                == app.result_representation_id
                            )
                        )
                    ).scalar_one()
                    # 🔴 result representation 指向的 artifact **行**，不只是它的内容 hash。
                    # 「incoming 永不晋升」是 artifact 身份/路径层面的承诺：两行不同、
                    # result 不在 `.incoming/` 下。只比 sha256 是弱代理 —— 内容寻址下
                    # 两个不同行完全可能同 sha（merged 恰好复现 incoming 字节）。
                    result_art = (
                        await s.execute(
                            sa.select(WorkpaperArtifact).where(
                                WorkpaperArtifact.id == result_rep.artifact_id
                            )
                        )
                    ).scalar_one()
                result_projection_sha = None
                if app.result_revision is not None:
                    result_projection_sha = (
                        await s.execute(
                            sa.text(
                                "SELECT projection_sha256 FROM working_paper_content_version "
                                "WHERE wp_id = :w AND revision = :r"
                            ),
                            {"w": wp, "r": int(app.result_revision)},
                        )
                    ).scalar_one_or_none()
                result_version_source = None
                if app.result_revision is not None:
                    result_version_source = (
                        await s.execute(
                            sa.text(
                                "SELECT source FROM working_paper_content_version "
                                "WHERE wp_id = :w AND revision = :r"
                            ),
                            {"w": wp, "r": int(app.result_revision)},
                        )
                    ).scalar_one_or_none()
                outbox_rows = int(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT count(*) FROM import_event_outbox "
                                "WHERE payload->>'wp_id' = :w"
                            ),
                            {"w": str(wp)},
                        )
                    ).scalar_one()
                )
                # Task 27：冲突行 + 裁决轨迹（AC 8.1 / 8.6）。按 operation 聚合，
                # `superseded_at IS NULL` 才算「本轮仍在」的冲突。
                conflict_rows = int(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT count(*) FROM working_paper_sync_conflict c "
                                "JOIN working_paper_sync_operation o ON o.id = c.operation_id "
                                "WHERE o.wp_id = :w"
                            ),
                            {"w": wp},
                        )
                    ).scalar_one()
                )
                conflict_rows_live = int(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT count(*) FROM working_paper_sync_conflict c "
                                "JOIN working_paper_sync_operation o ON o.id = c.operation_id "
                                "WHERE o.wp_id = :w AND c.superseded_at IS NULL"
                            ),
                            {"w": wp},
                        )
                    ).scalar_one()
                )
                conflict_rows_resolved = int(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT count(*) FROM working_paper_sync_conflict c "
                                "JOIN working_paper_sync_operation o ON o.id = c.operation_id "
                                "WHERE o.wp_id = :w AND c.resolved_at IS NOT NULL "
                                "  AND c.resolved_by IS NOT NULL"
                            ),
                            {"w": wp},
                        )
                    ).scalar_one()
                )
                conflict_resolved_values = sorted(
                    str(v)
                    for v in (
                        (
                            await s.execute(
                                sa.text(
                                    "SELECT c.resolved_value->>'value' FROM "
                                    "working_paper_sync_conflict c "
                                    "JOIN working_paper_sync_operation o "
                                    "  ON o.id = c.operation_id "
                                    "WHERE o.wp_id = :w AND c.resolved_value IS NOT NULL"
                                ),
                                {"w": wp},
                            )
                        )
                        .scalars()
                        .all()
                    )
                )
                return {
                    "revision": int(revision),
                    "current_content_version_id": _opt(current_cv),
                    "entry_pointer_representation_id": (
                        None if entry_state is None
                        else _opt(entry_state.current_representation_id)
                    ),
                    "entry_pointer_generation": (
                        None
                        if entry_state is None
                        else int(entry_state.representation_generation)
                    ),
                    "room_state": str(room.state),
                    "room_last_applied": _opt(room.last_applied_version_id),
                    "room_client_confirmed_version": _opt(
                        room.client_confirmed_base_version_id
                    ),
                    "room_client_confirmed_representation": _opt(
                        room.client_confirmed_representation_id
                    ),
                    "room_client_confirmed_projection_sha": (
                        room.client_confirmed_projection_sha256
                    ),
                    "room_refresh_required_at": (
                        None if room.refresh_required_at is None else "set"
                    ),
                    "room_refresh_reason": room.refresh_reason,
                    "room_latest_durable_application": _opt(
                        room.latest_durable_application_id
                    ),
                    "room_latest_durable_sequence": int(room.latest_durable_sequence),
                    "app_state": str(app.state),
                    "app_logical_result": app.logical_result_code,
                    "app_result_revision": (
                        None if app.result_revision is None else int(app.result_revision)
                    ),
                    "app_result_representation": _opt(app.result_representation_id),
                    "app_result_artifact_sha": app.result_artifact_sha256,
                    "app_merged_projection_sha": app.merged_projection_sha256,
                    "app_incoming_projection_sha": app.incoming_projection_sha256,
                    "app_conflict_count": int(app.conflict_count),
                    "app_conflict_digest": app.conflict_set_digest,
                    "app_bundle": _opt(app.definition_bundle_id),
                    "app_count_for_wp": app_count,
                    "operation_count": len(ops),
                    "operation_states": sorted(str(o.state) for o in ops),
                    "operation_event_count": op_events,
                    "application_event_count": app_events,
                    "content_version_count": versions,
                    "incoming_kind": str(incoming.kind),
                    "incoming_state": str(incoming.state),
                    "incoming_published_at": (
                        None if incoming.published_at is None else "set"
                    ),
                    "incoming_relative_path": incoming.relative_path,
                    "incoming_artifact_id": _opt(app.incoming_artifact_id),
                    "result_rep_artifact_id": (
                        None if result_art is None else _opt(result_art.id)
                    ),
                    "result_rep_artifact_path": (
                        None if result_art is None else result_art.relative_path
                    ),
                    "result_rep_artifact_kind": (
                        None if result_art is None else str(result_art.kind)
                    ),
                    "result_rep_artifact_state": (
                        None if result_art is None else str(result_art.state)
                    ),
                    "result_rep_bundle": (
                        None if result_rep is None else _opt(result_rep.definition_bundle_id)
                    ),
                    "result_rep_bundle_sha": (
                        None if result_rep is None else result_rep.definition_bundle_sha256
                    ),
                    "result_rep_artifact_sha": (
                        None if result_rep is None else result_rep.artifact_sha256
                    ),
                    "result_rep_reason": None if result_rep is None else result_rep.reason,
                    "result_version_projection_sha": result_projection_sha,
                    "result_version_source": result_version_source,
                    "outbox_rows": outbox_rows,
                    # Task 27：冲突集必须**落行**（AC 8.1），且裁决轨迹落在同一行上
                    # （AC 8.6）。只记 `app_conflict_count/digest` 两个标量时，
                    # 「预览没有数据可读」与「裁决没有留下痕迹」都观察不到。
                    "conflict_rows": conflict_rows,
                    "conflict_rows_live": conflict_rows_live,
                    "conflict_rows_resolved": conflict_rows_resolved,
                    "conflict_resolved_values": conflict_resolved_values,
                }

        # ═══════════════════════════════════════════════════════════════
        # 场景装配器
        # ═══════════════════════════════════════════════════════════════

        async def _stage_world(
            tag: str,
            *,
            base_values: dict[str, Any],
            current_values: dict[str, Any] | None,
            incoming_values: dict[str, Any],
            quarantine: bool = False,
            contributor_user_ids: list[uuid.UUID] | None = None,
            second_participant: bool = False,
        ) -> dict[str, Any]:
            """建 entry + room + request + durable incoming + application。

            `current_values` 非 None 时先用 HTML lane **改一次 current**（即服务器侧有
            独立编辑），从而制造 base ≠ current 的三方局面。这里刻意不走 coordinator ——
            它是被测对象，用它造前置条件会让判据自证。
            """
            entry = await _build_entry(tag, base_values)
            # 🔴 顺序即真实故事：先开 room 并 confirm descriptor（于是 frozen client base
            # = gen1），**再**在服务器侧发布 gen2 当 current。反过来做的话 room 的
            # client-confirmed 基线就等于 current，base 与 current 不可能分叉，
            # 三方 merge 退化成两方 —— P25/P26/P27 全部证明不了。
            env = await _build_room(entry, second_participant=second_participant)
            req = await _accept_request(
                env, key=f"fs-{tag}", contributor_user_ids=contributor_user_ids
            )
            if current_values is not None:
                # 直接发布第二个 generation 作为 current（不动 business revision）：
                # 三方 merge 的 `current` 侧来自 entry pointer，这样就能与 frozen base 分叉。
                cur_projection = _projection(current_values)
                cur_bytes = _ooxml(projection_values=_carrier_values(cur_projection))
                pub = artifacts.publish_representation(
                    entry_id=ENTRY,
                    generation=2,
                    staged=artifacts.stage_bytes(
                        project_id=project, wp_id=entry["wp"],
                        payload=cur_bytes, document_type="xlsx",
                    ),
                )
                async with Session() as s:
                    repo = WorkpaperSyncRepository(s)
                    art_cur = await repo.register_artifact(
                        project_id=project, wp_id=entry["wp"],
                        kind=ArtifactKind.canonical, state=ArtifactState.published,
                        relative_path=pub.relative_path, sha256=pub.sha256,
                        size_bytes=pub.size_bytes, document_type="xlsx",
                    )
                    rep2 = await repo.create_representation(
                        project_id=project, wp_id=entry["wp"], entry_id=ENTRY,
                        content_version_id=entry["cv0"], generation=2,
                        document_type="xlsx", artifact_id=art_cur.id,
                        artifact_sha256=art_cur.sha256,
                        definition_bundle_id=world["bundle"],
                        authority_model_definition_id=world["authority"],
                        adapter_id=ENTRY, adapter_build_digest=_d("task26-adapter"),
                        structure_hash=_d(f"task26-structure-{tag}-cur"),
                        identity_inventory_sha256=_d(f"task26-identity-{tag}-cur"),
                        reason="content_commit",
                    )
                    await repo.set_entry_pointer(
                        wp_id=entry["wp"], entry_id=ENTRY,
                        representation_id=rep2.id, generation=2,
                    )
                    await s.commit()
                entry["current_rep"] = rep2.id
            incoming_projection = _projection(incoming_values)
            payload = _ooxml(projection_values=_carrier_values(incoming_projection))
            if quarantine:
                # 触发 OOXML 安全门：非 zip 字节 ⇒ sealing 落 quarantined。
                payload = b"not-a-zip-at-all"
            inc = await _seal_incoming(env, entry, req, payload=payload)
            app_id: uuid.UUID | None = None
            correlate_error: str | None = None
            if not quarantine:
                app_id = await _correlate(env, entry, req, inc)
            else:
                try:
                    app_id = await _correlate(env, entry, req, inc)
                except Exception as exc:  # noqa: BLE001 - 隔离必须在 FK 层就被拒
                    correlate_error = f"{type(exc).__name__}:{getattr(exc, 'error_code', '')}"
            return {
                "tag": tag,
                "entry": entry,
                "env": env,
                "req": req,
                "inc": inc,
                "app": app_id,
                "incoming_projection": incoming_projection,
                "correlate_error": correlate_error,
            }

        # ═══ S1：applied happy path（P25 / P29 / P62 / P65 / P14）═══════════
        try:
            row = str(uuid.uuid4())
            s1 = await _stage_world(
                "applied",
                base_values={PERIOD: "2024", TOTAL: Decimal("100"), f"ar_rows/{row}/amount": Decimal("10")},
                current_values=None,
                incoming_values={PERIOD: "2024", TOTAL: Decimal("888"), f"ar_rows/{row}/amount": Decimal("10")},
            )
            probe = _RecordingProbe()
            adapter = _JsonCarrierAdapter()
            before = await _db_state(s1["entry"]["wp"], s1["env"]["room"], s1["app"])
            async with Session() as s:
                coord = _coordinator(s, probe=probe)
                outcome = await coord.apply_durable_incoming(
                    operation_id=s1["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s1["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=adapter,
                    contract=contract,
                    actor_id=user_a,
                )
            after = await _db_state(s1["entry"]["wp"], s1["env"]["room"], s1["app"])
            floor: Any = None
            floor_error: str | None = None
            async with Session() as s:
                coord = _coordinator(s, probe=_RecordingProbe())
                try:
                    floor = await coord.reload_floor_revision(
                        operation_id=s1["req"]["operation"],
                        declared_project_id=project,
                        declared_wp_id=s1["entry"]["wp"],
                        declared_entry_id=ENTRY,
                    )
                except Exception as exc:  # noqa: BLE001
                    floor_error = _err(exc)
            snap["scenarios"]["applied"] = {
                "outcome": outcome.as_dict(),
                "before": before,
                "after": after,
                "probe_calls": len(probe.calls),
                "adapter_calls": list(adapter.calls),
                "reload_floor": floor,
                "reload_floor_error": floor_error,
                "incoming_sha": s1["inc"]["sha256"],
                "wp": str(s1["entry"]["wp"]),
                "room": str(s1["env"]["room"]),
                "application": str(s1["app"]),
                "operation": str(s1["req"]["operation"]),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("applied", exc)

        # ═══ S2：merged ≠ incoming ⇒ refresh_required + supersede（P62）══════
        try:
            s2 = await _stage_world(
                "refresh",
                base_values={PERIOD: "2024", TOTAL: Decimal("100")},
                current_values={PERIOD: "2025 已审", TOTAL: Decimal("100")},
                incoming_values={PERIOD: "2024", TOTAL: Decimal("888")},
            )
            probe = _RecordingProbe()
            adapter = _JsonCarrierAdapter()
            before = await _db_state(s2["entry"]["wp"], s2["env"]["room"], s2["app"])
            async with Session() as s:
                coord = _coordinator(s, probe=probe)
                outcome = await coord.apply_durable_incoming(
                    operation_id=s2["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s2["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=adapter,
                    contract=contract,
                    actor_id=user_a,
                )
            after = await _db_state(s2["entry"]["wp"], s2["env"]["room"], s2["app"])
            # 「禁止下一 forcesave」必须真调一次 Task 21 的资格门。
            next_forcesave: dict[str, Any] = {}
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                ras = RequestApplicationService(repo)
                try:
                    await ras.freeze_and_persist_request(
                        s2["env"]["scope"],
                        room_id=s2["env"]["room"],
                        participant_id=s2["env"]["participant"],
                        idempotency_key="fs-refresh-2",
                        client_edit_epoch=4,
                        contributor_user_ids=[user_a],
                        created_by=user_a,
                    )
                    next_forcesave = {"accepted": True}
                except RoomNotWritableError as exc:
                    next_forcesave = {
                        "accepted": False,
                        "error_type": type(exc).__name__,
                        "error_code": getattr(exc, "error_code", None),
                    }
                except Exception as exc:  # noqa: BLE001
                    next_forcesave = {
                        "accepted": False,
                        "error_type": type(exc).__name__,
                        "error_code": getattr(exc, "error_code", None),
                        "unexpected": True,
                    }
            snap["scenarios"]["refresh"] = {
                "outcome": outcome.as_dict(),
                "before": before,
                "after": after,
                "next_forcesave": next_forcesave,
                "merged_equals_incoming": (
                    outcome.merged_projection_sha256 == outcome.incoming_projection_sha256
                ),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("refresh", exc)

        # ═══ S3：同字段异值 ⇒ conflict，指针一律不动（P26 / AC 8.11 / 4.6）═══
        try:
            s3 = await _stage_world(
                "conflict",
                base_values={PERIOD: "A", TOTAL: Decimal("1")},
                current_values={PERIOD: "B", TOTAL: Decimal("1")},
                incoming_values={PERIOD: "C", TOTAL: Decimal("1")},
            )
            probe = _RecordingProbe()
            adapter = _JsonCarrierAdapter()
            before = await _db_state(s3["entry"]["wp"], s3["env"]["room"], s3["app"])
            async with Session() as s:
                coord = _coordinator(s, probe=probe)
                outcome = await coord.apply_durable_incoming(
                    operation_id=s3["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s3["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=adapter,
                    contract=contract,
                    actor_id=user_a,
                )
            after = await _db_state(s3["entry"]["wp"], s3["env"]["room"], s3["app"])
            snap["scenarios"]["conflict"] = {
                "outcome": outcome.as_dict(),
                "before": before,
                "after": after,
                "adapter_calls": list(adapter.calls),
                "probe_calls": len(probe.calls),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("conflict", exc)

        # ═══ S4：delete/update 只冲突那一行（P27）════════════════════════════
        try:
            r1, r2 = str(uuid.uuid4()), str(uuid.uuid4())
            s4 = await _stage_world(
                "row_conflict",
                base_values={
                    PERIOD: "2025", TOTAL: Decimal("0"),
                    f"ar_rows/{r1}/amount": Decimal("10"),
                    f"ar_rows/{r2}/amount": Decimal("20"),
                },
                current_values={
                    PERIOD: "2025", TOTAL: Decimal("0"),
                    f"ar_rows/{r2}/amount": Decimal("20"),
                },
                incoming_values={
                    PERIOD: "2025", TOTAL: Decimal("0"),
                    f"ar_rows/{r1}/amount": Decimal("11"),
                    f"ar_rows/{r2}/amount": Decimal("22"),
                },
            )
            async with Session() as s:
                coord = _coordinator(s, probe=_RecordingProbe())
                outcome = await coord.apply_durable_incoming(
                    operation_id=s4["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s4["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=_JsonCarrierAdapter(),
                    contract=contract,
                    actor_id=user_a,
                )
            after = await _db_state(s4["entry"]["wp"], s4["env"]["room"], s4["app"])
            conflicted_rows = (
                sorted({rec.locator.row_key for rec in outcome.merge.conflicts.records})
                if outcome.merge is not None
                else []
            )
            merged_r2 = (
                None if outcome.merge is None
                else outcome.merge.merged.get(f"ar_rows/{r2}/amount")
            )
            snap["scenarios"]["row_conflict"] = {
                "result": outcome.result.value,
                "error_code": outcome.error_code,
                "error_detail": outcome.error_detail,
                "conflict_count": outcome.conflict_count,
                "conflicted_rows": conflicted_rows,
                "expected_conflicted_row": r1,
                "other_row": r2,
                "merged_other_row_value": (
                    None if merged_r2 is None else str(merged_r2.value)
                ),
                "after": after,
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("row_conflict", exc)

        # ═══ S5：publish 前撤权 ⇒ authorization_stale，零 revision（P43）═══════
        try:
            s5 = await _stage_world(
                "fence_before_publish",
                base_values={PERIOD: "2024", TOTAL: Decimal("100")},
                current_values=None,
                incoming_values={PERIOD: "2024", TOTAL: Decimal("777")},
            )
            probe = _FlippingProbe(flip_at=1)
            adapter = _JsonCarrierAdapter()
            before = await _db_state(s5["entry"]["wp"], s5["env"]["room"], s5["app"])
            # 🔴 只扫 `.versions/`（= publish 命名空间）。`.staging/` 是 materialize 的
            # 工作目录，fence 在 publish **之前**触发时 staging 里当然已经有产物 ——
            # 把它算进来会让判据变成「fence 必须在 materialize 之前」，那是另一条
            # （且与 AC 8.10 明文相反的）要求。
            def _published_xlsx() -> list[str]:
                return sorted(
                    p.relative_to(base_root).as_posix()
                    for p in (base_root / "storage").rglob("*.xlsx")
                    if "/.versions/" in p.as_posix().replace("\\", "/")
                )

            files_before = _published_xlsx()
            async with Session() as s:
                coord = _coordinator(s, probe=probe)
                outcome = await coord.apply_durable_incoming(
                    operation_id=s5["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s5["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=adapter,
                    contract=contract,
                    actor_id=user_a,
                )
            after = await _db_state(s5["entry"]["wp"], s5["env"]["room"], s5["app"])
            files_after = _published_xlsx()
            snap["scenarios"]["fence_before_publish"] = {
                "outcome": outcome.as_dict(),
                "before": before,
                "after": after,
                "adapter_calls": list(adapter.calls),
                "probe_calls": len(probe.calls),
                "new_files": [f for f in files_after if f not in files_before],
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("fence_before_publish", exc)

        # ═══ S6：publish 后、写库前撤权 ⇒ 仍零 revision（P43 第二道）══════════
        try:
            s6 = await _stage_world(
                "fence_before_write",
                base_values={PERIOD: "2024", TOTAL: Decimal("100")},
                current_values=None,
                incoming_values={PERIOD: "2024", TOTAL: Decimal("666")},
            )
            probe = _FlippingProbe(flip_at=2)
            adapter = _JsonCarrierAdapter()
            before = await _db_state(s6["entry"]["wp"], s6["env"]["room"], s6["app"])
            async with Session() as s:
                coord = _coordinator(s, probe=probe)
                outcome = await coord.apply_durable_incoming(
                    operation_id=s6["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s6["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=adapter,
                    contract=contract,
                    actor_id=user_a,
                )
            after = await _db_state(s6["entry"]["wp"], s6["env"]["room"], s6["app"])
            snap["scenarios"]["fence_before_write"] = {
                "outcome": outcome.as_dict(),
                "before": before,
                "after": after,
                "probe_calls": len(probe.calls),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("fence_before_write", exc)

        # ═══ S7：durable 后 extract 失败 → retry 成功（P19 / P38）════════════
        try:
            s7 = await _stage_world(
                "retry",
                base_values={PERIOD: "2024", TOTAL: Decimal("100")},
                current_values=None,
                incoming_values={PERIOD: "2024", TOTAL: Decimal("555")},
            )
            before = await _db_state(s7["entry"]["wp"], s7["env"]["room"], s7["app"])
            broken = _JsonCarrierAdapter(fail_on="extract")
            async with Session() as s:
                coord = _coordinator(s, probe=_RecordingProbe())
                failed = await coord.apply_durable_incoming(
                    operation_id=s7["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s7["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=broken,
                    contract=contract,
                    actor_id=user_a,
                )
            mid = await _db_state(s7["entry"]["wp"], s7["env"]["room"], s7["app"])
            healthy = _JsonCarrierAdapter()
            async with Session() as s:
                coord = _coordinator(s, probe=_RecordingProbe())
                retried = await coord.apply_durable_incoming(
                    operation_id=s7["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s7["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=healthy,
                    contract=contract,
                    actor_id=user_a,
                    attempt=2,
                )
            after = await _db_state(s7["entry"]["wp"], s7["env"]["room"], s7["app"])
            snap["scenarios"]["retry"] = {
                "failed_outcome": failed.as_dict(),
                "retried_outcome": retried.as_dict(),
                "before": before,
                "mid": mid,
                "after": after,
                "same_operation": (
                    failed.canonical_operation_id == retried.canonical_operation_id
                ),
                "same_application": failed.application_id == retried.application_id,
                "same_substrate": (
                    failed.substrate.artifact_id == retried.substrate.artifact_id
                ),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("retry", exc)

        # ═══ S8：quarantined incoming 在三层都被拒（AC 5.6 / 8.10）══════════
        try:
            s8 = await _stage_world(
                "quarantined",
                base_values={PERIOD: "2024", TOTAL: Decimal("100")},
                current_values=None,
                incoming_values={PERIOD: "2024", TOTAL: Decimal("1")},
                quarantine=True,
            )
            layer_results: dict[str, Any] = {"correlate": s8["correlate_error"]}
            # 第二层：coordinator 入口。手工把 quarantined artifact 塞进 frozen identity。
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                rooms = RoomService(repo)
                resolution = CanonicalResolutionService(s, artifacts)
                content = ContentMutationService(
                    session=s, repository=repo, artifacts=artifacts, resolution=resolution
                )
                coord = OH.OoToHtmlCoordinator(
                    repo=repo, artifacts=artifacts, resolution=resolution,
                    content=content, rooms=rooms,
                    requests=RequestApplicationService(repo, rooms),
                    probe=_RecordingProbe(),
                )
                frozen = OH.FrozenApplicationIdentity(
                    application_id=uuid.uuid4(),
                    project_id=project, wp_id=s8["entry"]["wp"], entry_id=ENTRY,
                    room_id=s8["env"]["room"], generation=1,
                    origin_request_id=s8["req"]["request"],
                    origin_request_sequence=1, effective_request_sequence=1,
                    client_edit_epoch=3,
                    incoming_artifact_id=s8["inc"]["incoming"],
                    incoming_sha256=s8["inc"]["sha256"],
                    base_version_id=s8["entry"]["cv0"],
                    base_representation_id=s8["entry"]["rep1"],
                    current_revision=0,
                    definition_bundle_id=world["bundle"],
                    definition_bundle_sha256=_d("irrelevant"),
                    authority_model_definition_id=world["authority"],
                    authority_model_definition_sha256=_d("irrelevant"),
                    adapter_id=ENTRY, adapter_build_digest=_d("task26-adapter"),
                    contributor_snapshot_digest=_d("irrelevant"),
                    state=OH.ApplicationState.queued,
                    frozen_write_fence_epoch=1,
                    frozen_initiator_participant_id=s8["env"]["participant"],
                    frozen_initiator_permission_epoch=5,
                    frozen_client_base_projection_sha256=_d("irrelevant"),
                    frozen_request_kind=RequestKind.forcesave,
                    frozen_close_leader_eligibility_epoch=None,
                )
                try:
                    await coord.open_substrate(frozen)
                    layer_results["coordinator"] = None
                except Exception as exc:  # noqa: BLE001
                    layer_results["coordinator"] = (
                        f"{type(exc).__name__}:{getattr(exc, 'error_code', '')}"
                    )
            # 第三层：engine（Task 13 的 assert_substrate_usable）
            from app.services.workpaper_sync.adapters.base import (
                SubstrateRole,
                assert_substrate_usable,
            )

            try:
                assert_substrate_usable(
                    role=SubstrateRole.incoming,
                    artifact_kind=ArtifactKind.incoming,
                    artifact_state=ArtifactState.quarantined,
                )
                layer_results["engine"] = None
            except Exception as exc:  # noqa: BLE001
                layer_results["engine"] = (
                    f"{type(exc).__name__}:{getattr(exc, 'error_code', '')}"
                )
            snap["scenarios"]["quarantined"] = {
                "sealed_state": s8["inc"]["state"],
                "layers": layer_results,
                "application_created": _opt(s8["app"]),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("quarantined", exc)

        # ═══ S9：未管理区域漂移 ⇒ 拒绝发布（AC 8.11）════════════════════════
        try:
            s9 = await _stage_world(
                "unmanaged_drift",
                base_values={PERIOD: "2024", TOTAL: Decimal("100")},
                current_values=None,
                incoming_values={PERIOD: "2024", TOTAL: Decimal("444")},
            )
            before = await _db_state(s9["entry"]["wp"], s9["env"]["room"], s9["app"])
            async with Session() as s:
                coord = _coordinator(s, probe=_RecordingProbe())
                outcome = await coord.apply_durable_incoming(
                    operation_id=s9["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s9["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=_JsonCarrierAdapter(break_unmanaged=True),
                    contract=contract,
                    actor_id=user_a,
                )
            after = await _db_state(s9["entry"]["wp"], s9["env"]["room"], s9["app"])
            snap["scenarios"]["unmanaged_drift"] = {
                "outcome": outcome.as_dict(),
                "before": before,
                "after": after,
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("unmanaged_drift", exc)

        # ═══ S10：pre-bind shell 问 result revision ⇒ 拒（P14）════════════════
        try:
            s10 = await _stage_world(
                "pre_bind",
                base_values={PERIOD: "2024", TOTAL: Decimal("100")},
                current_values=None,
                incoming_values={PERIOD: "2024", TOTAL: Decimal("2")},
            )
            # 另建一个**未 correlate** 的 request/shell —— 它的 application_id 恒为 NULL。
            pre = await _accept_request(s10["env"], key="fs-pre-bind")
            probe_result: dict[str, Any] = {}
            async with Session() as s:
                coord = _coordinator(s, probe=_RecordingProbe())
                try:
                    value = await coord.reload_floor_revision(
                        operation_id=pre["operation"],
                        declared_project_id=project,
                        declared_wp_id=s10["entry"]["wp"],
                        declared_entry_id=ENTRY,
                    )
                    probe_result = {"returned": value}
                except Exception as exc:  # noqa: BLE001
                    probe_result = {
                        "error_type": type(exc).__name__,
                        "error_code": getattr(exc, "error_code", None),
                    }
            async with Session() as s:
                shell = (
                    await s.execute(
                        sa.select(WorkpaperSyncOperation).where(
                            WorkpaperSyncOperation.id == pre["operation"]
                        )
                    )
                ).scalar_one()
                probe_result["shell_application_id"] = _opt(shell.application_id)
                probe_result["shell_duplicate_of"] = _opt(shell.duplicate_of_operation_id)
            snap["scenarios"]["pre_bind"] = probe_result
        except Exception as exc:  # noqa: BLE001
            _phase_failed("pre_bind", exc)

        # ═══ S11：bundle 被换成另一个 approved bundle ⇒ fence 拒（P43）════════
        try:
            s11 = await _stage_world(
                "bundle_swap",
                base_values={PERIOD: "2024", TOTAL: Decimal("100")},
                current_values=None,
                incoming_values={PERIOD: "2024", TOTAL: Decimal("333")},
            )
            # 把 entry 的 current published representation 换成绑定另一个 approved bundle
            # 的新 generation —— 这就是「current approved bundle 被替换」。
            # 🔴 `before` 快照必须在这次替换**之后**取：替换本身会移动 entry pointer，
            # 而本场景要证明的是「fence 失败后 coordinator 什么都没动」。在替换前取基线
            # 会把布景改动误算成 coordinator 的副作用（首轮实测即如此假红）。
            cur_projection = s11["entry"]["base_projection"]
            swap_bytes = _ooxml(projection_values=_carrier_values(cur_projection))
            pub = artifacts.publish_representation(
                entry_id=ENTRY,
                generation=3,
                staged=artifacts.stage_bytes(
                    project_id=project, wp_id=s11["entry"]["wp"],
                    payload=swap_bytes + b"\x00", document_type="xlsx",
                ),
            )
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                art_swap = await repo.register_artifact(
                    project_id=project, wp_id=s11["entry"]["wp"],
                    kind=ArtifactKind.canonical, state=ArtifactState.published,
                    relative_path=pub.relative_path, sha256=pub.sha256,
                    size_bytes=pub.size_bytes, document_type="xlsx",
                )
                rep3 = await repo.create_representation(
                    project_id=project, wp_id=s11["entry"]["wp"], entry_id=ENTRY,
                    content_version_id=s11["entry"]["cv0"], generation=3,
                    document_type="xlsx", artifact_id=art_swap.id,
                    artifact_sha256=art_swap.sha256,
                    definition_bundle_id=world["bundle_alt"],
                    authority_model_definition_id=world["authority_alt"],
                    adapter_id=ENTRY, adapter_build_digest=_d("task26-adapter"),
                    structure_hash=_d("task26-structure-swap"),
                    identity_inventory_sha256=_d("task26-identity-swap"),
                    reason="definition_upgrade",
                )
                await repo.set_entry_pointer(
                    wp_id=s11["entry"]["wp"], entry_id=ENTRY,
                    representation_id=rep3.id, generation=3,
                )
                await s.commit()
            before = await _db_state(s11["entry"]["wp"], s11["env"]["room"], s11["app"])
            async with Session() as s:
                coord = _coordinator(s, probe=_RecordingProbe())
                outcome = await coord.apply_durable_incoming(
                    operation_id=s11["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s11["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=_JsonCarrierAdapter(),
                    contract=contract,
                    actor_id=user_a,
                )
            after = await _db_state(s11["entry"]["wp"], s11["env"]["room"], s11["app"])
            snap["scenarios"]["bundle_swap"] = {
                "outcome": outcome.as_dict(),
                "before": before,
                "after": after,
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("bundle_swap", exc)

        # ═══ S12：initiator 被撤销 ⇒ fence 拒（P43 / AC 10.10）═══════════════
        try:
            s12 = await _stage_world(
                "initiator_revoked",
                base_values={PERIOD: "2024", TOTAL: Decimal("100")},
                current_values=None,
                incoming_values={PERIOD: "2024", TOTAL: Decimal("222")},
            )
            before = await _db_state(s12["entry"]["wp"], s12["env"]["room"], s12["app"])
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "UPDATE working_paper_oo_participant "
                        "SET state='revoked', revoked_at=:t WHERE id=:p"
                    ),
                    {"t": _now(), "p": s12["env"]["participant"]},
                )
                await s.commit()
            async with Session() as s:
                coord = _coordinator(s, probe=_RecordingProbe())
                outcome = await coord.apply_durable_incoming(
                    operation_id=s12["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s12["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=_JsonCarrierAdapter(),
                    contract=contract,
                    actor_id=user_a,
                )
            after = await _db_state(s12["entry"]["wp"], s12["env"]["room"], s12["app"])
            snap["scenarios"]["initiator_revoked"] = {
                "outcome": outcome.as_dict(),
                "before": before,
                "after": after,
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("initiator_revoked", exc)

        # ═══ S13：探针自身失败 ⇒ 可诊断失败，绝不放行（无 fail-open）══════════
        try:
            s13 = await _stage_world(
                "probe_broken",
                base_values={PERIOD: "2024", TOTAL: Decimal("100")},
                current_values=None,
                incoming_values={PERIOD: "2024", TOTAL: Decimal("111")},
            )
            before = await _db_state(s13["entry"]["wp"], s13["env"]["room"], s13["app"])

            class _BrokenProbe:
                async def observe(self, **kwargs):
                    raise AttributeError("注入缺陷：探针接线错误（列名写错）")

            async with Session() as s:
                coord = _coordinator(s, probe=_BrokenProbe())
                outcome = await coord.apply_durable_incoming(
                    operation_id=s13["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s13["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=_JsonCarrierAdapter(),
                    contract=contract,
                    actor_id=user_a,
                )
            after = await _db_state(s13["entry"]["wp"], s13["env"]["room"], s13["app"])
            snap["scenarios"]["probe_broken"] = {
                "outcome": outcome.as_dict(),
                "before": before,
                "after": after,
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("probe_broken", exc)

        # ═══ S14：探针返回值缺字段 ⇒ 拒绝（「缺字段视为放行」是经典 fail-open）═══
        #
        # 与 S13 不是重复：S13 是探针**抛异常**，S14 是探针**正常返回但少一个键**。
        # 后者是真实接线错误的主要形态（改了返回结构、拼错键名），而它在
        # 「最终有没有报错」上与前者完全不同 —— 少了 `if key not in external` 那条，
        # `project_visible` 判据会静默消失而不是抛。
        try:
            s14 = await _stage_world(
                "probe_incomplete",
                base_values={PERIOD: "2024", TOTAL: Decimal("100")},
                current_values=None,
                incoming_values={PERIOD: "2024", TOTAL: Decimal("99")},
            )
            before = await _db_state(s14["entry"]["wp"], s14["env"]["room"], s14["app"])

            class _IncompleteProbe:
                """只返回 `workflow_locked` —— `project_visible` 键根本不存在。"""

                async def observe(self, **kwargs):
                    return {"workflow_locked": False}

            async with Session() as s:
                coord = _coordinator(s, probe=_IncompleteProbe())
                outcome = await coord.apply_durable_incoming(
                    operation_id=s14["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s14["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=_JsonCarrierAdapter(),
                    contract=contract,
                    actor_id=user_a,
                )
            after = await _db_state(s14["entry"]["wp"], s14["env"]["room"], s14["app"])
            snap["scenarios"]["probe_incomplete"] = {
                "outcome": outcome.as_dict(),
                "before": before,
                "after": after,
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("probe_incomplete", exc)

        # ═══ S15：**只有 contributor** 变化 ⇒ fence 拒（AC 10.10 的 contributor 面）═══
        #
        # 判别性输入：initiator（A）保持 active，另一位 contributor（B）被撤销。
        # 于是十条 fence 里只有 contributor digest 那一条会不等值 —— 其余九条全部相同。
        # 这是唯一能证伪「重算 contributor digest」的输入形态：S12（撤销 initiator）会先
        # 在 `initiator_state` 那条失败，永远走不到 contributor 比对。
        try:
            s15 = await _stage_world(
                "contributor_revoked",
                base_values={PERIOD: "2024", TOTAL: Decimal("100")},
                current_values=None,
                incoming_values={PERIOD: "2024", TOTAL: Decimal("88")},
                contributor_user_ids=[user_a, user_b],
                second_participant=True,
            )
            before = await _db_state(s15["entry"]["wp"], s15["env"]["room"], s15["app"])
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "UPDATE working_paper_oo_participant "
                        "SET state='revoked', revoked_at=:t WHERE id=:p"
                    ),
                    {"t": _now(), "p": s15["env"]["participant_b"]},
                )
                await s.commit()
            async with Session() as s:
                coord = _coordinator(s, probe=_RecordingProbe())
                outcome = await coord.apply_durable_incoming(
                    operation_id=s15["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s15["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=_JsonCarrierAdapter(),
                    contract=contract,
                    actor_id=user_a,
                )
            after = await _db_state(s15["entry"]["wp"], s15["env"]["room"], s15["app"])
            async with Session() as s:
                initiator_state = (
                    await s.execute(
                        sa.text(
                            "SELECT state FROM working_paper_oo_participant WHERE id=:p"
                        ),
                        {"p": s15["env"]["participant"]},
                    )
                ).scalar_one()
            snap["scenarios"]["contributor_revoked"] = {
                "outcome": outcome.as_dict(),
                "before": before,
                "after": after,
                "initiator_state_after": str(initiator_state),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("contributor_revoked", exc)

        # ═══ S16：已 applied 的 application 不得再 apply（AC 4.3 / 8.12 / P65）═══
        #
        # 🔴 这是本轮实测抓到的真实缺陷（修前行为已录在下方 `test_...` 的注释里）：
        # `APPLICATION_EDGES[applied]` 是空集 ⇒ `_walk_application` 全部跳过、
        # `_advance_application` 在 `from == to` 时提前返回 ⇒ **一次异常都不抛**，
        # Task 15 照常提交，同一 incoming 产出第二个 business revision 与第二份
        # published representation，`application.result_revision` 被原地改写。
        try:
            s16 = await _stage_world(
                "reapply",
                base_values={PERIOD: "2024", TOTAL: Decimal("100")},
                current_values=None,
                incoming_values={PERIOD: "2024", TOTAL: Decimal("777")},
            )
            async with Session() as s:
                coord = _coordinator(s, probe=_RecordingProbe())
                first = await coord.apply_durable_incoming(
                    operation_id=s16["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s16["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=_JsonCarrierAdapter(),
                    contract=contract,
                    actor_id=user_a,
                )
            after_first = await _db_state(
                s16["entry"]["wp"], s16["env"]["room"], s16["app"]
            )
            second_adapter = _JsonCarrierAdapter()
            second_probe = _RecordingProbe()
            second_outcome: dict[str, Any] | None = None
            second_error: str | None = None
            async with Session() as s:
                coord = _coordinator(s, probe=second_probe)
                try:
                    again = await coord.apply_durable_incoming(
                        operation_id=s16["req"]["operation"],
                        declared_project_id=project,
                        declared_wp_id=s16["entry"]["wp"],
                        declared_entry_id=ENTRY,
                        adapter=second_adapter,
                        contract=contract,
                        actor_id=user_a,
                        # 运营侧最现实的触发方式：把它当成一次「重试」。
                        attempt=2,
                    )
                    second_outcome = again.as_dict()
                except Exception as exc:  # noqa: BLE001 - 拒绝形态由守卫断言
                    second_error = (
                        f"{type(exc).__name__}:{getattr(exc, 'error_code', '')}"
                    )
            after_second = await _db_state(
                s16["entry"]["wp"], s16["env"]["room"], s16["app"]
            )
            snap["scenarios"]["reapply"] = {
                "first_outcome": first.as_dict(),
                "after_first": after_first,
                "second_outcome": second_outcome,
                "second_error": second_error,
                "after_second": after_second,
                "second_adapter_calls": list(second_adapter.calls),
                "second_probe_calls": len(second_probe.calls),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("reapply", exc)

        # ═══ close-capture 装配器（S17/S18 共用）════════════════════════════
        #
        # 与 `_accept_request` 的差别是**本质**的：close-capture request 只能由
        # reconciler 在 room lock 内 CAS 产出（客户端不得直接发起），因此它带一个
        # promotion 时冻结的 eligibility epoch，而普通 forcesave 没有。
        async def _stage_close_capture(
            tag: str,
            incoming_values: dict[str, Any],
            *,
            desync_intent_epoch: int | None = None,
        ) -> dict:
            entry = await _build_entry(
                tag, {PERIOD: "2024", TOTAL: Decimal("100")}
            )
            env = await _build_room(entry)
            expected_contributors = compute_contributor_snapshot_digest(
                room_id=env["room"], generation=1, contributor_user_ids=[str(user_a)]
            )
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                intent = await repo.create_close_intent(
                    project_id=project, wp_id=entry["wp"], entry_id=ENTRY,
                    room_id=env["room"], participant_id=env["participant"],
                    client_confirmation_id=env["confirmation"], actor_id=user_a,
                )
                reconciled = await repo.reconcile_close_intents(
                    project_id=project, wp_id=entry["wp"], entry_id=ENTRY,
                    room_id=env["room"],
                    adapter_build_digest=_d("task26-adapter"),
                    contributor_snapshot_digest=expected_contributors,
                )
                await s.commit()
            if reconciled.promoted_request_id is None:
                raise _HarnessError(
                    f"{tag}: reconciler 没有提升 close-capture（"
                    f"no_successor={reconciled.no_successor}）"
                )
            async with Session() as s:
                op_id = (
                    await s.execute(
                        sa.text(
                            "SELECT id FROM working_paper_sync_operation "
                            "WHERE forcesave_request_id = :r"
                        ),
                        {"r": reconciled.promoted_request_id},
                    )
                ).scalar_one()
                repo = WorkpaperSyncRepository(s)
                rooms = RoomService(repo)
                cred = mint_route_credential(
                    room_id=env["room"], generation=1, doc_key=env["doc_key"]
                )
                await rooms.record_contributor_snapshot(
                    operation_id=op_id,
                    room_id=env["room"],
                    initiator_participant_id=env["participant"],
                    route_credential=cred,
                )
                await s.commit()
            req = {
                "request": reconciled.promoted_request_id,
                "operation": op_id,
                "credential": cred,
            }
            incoming_projection = _projection(incoming_values)
            inc = await _seal_incoming(
                env, entry, req,
                payload=_ooxml(projection_values=_carrier_values(incoming_projection)),
            )
            app_id = await _correlate(env, entry, req, inc)
            if desync_intent_epoch is not None:
                # 🔴 判别性输入：让 `close_intent.eligibility_epoch`（**intent 创建时**
                # 的值）与 append-only promotion event 的 epoch 分叉。
                #
                # 真实世界里这个分叉天然发生：A、B 都 close，B（序号高）先当 leader，
                # 在 promotion 前被撤销 ⇒ room epoch 0→1 ⇒ successor A 在 epoch 1 被
                # promote，而 A 的 intent 行还记着创建时的 0。用两个 closer 复现要额外
                # 摆一个未终结的 predecessor forcesave 才能阻止 B 被直接 promote；
                # 判据本身只关心「loader 读的是哪一列」，所以这里直接把分叉摆出来。
                #
                # 没有这条输入，「读 promotion event 还是读 intent 列」在单人 close 下
                # 两值都是 0 ⇒ 这个区分写了也无人能证伪。
                async with Session() as s:
                    await s.execute(
                        sa.text(
                            "UPDATE working_paper_oo_close_intent SET eligibility_epoch "
                            "= :e WHERE id = :i"
                        ),
                        {"e": desync_intent_epoch, "i": intent.id},
                    )
                    await s.commit()
            async with Session() as s:
                intent_epoch = (
                    await s.execute(
                        sa.text(
                            "SELECT eligibility_epoch FROM working_paper_oo_close_intent "
                            "WHERE id=:i"
                        ),
                        {"i": intent.id},
                    )
                ).scalar_one()
            return {
                "entry": entry, "env": env, "req": req, "inc": inc, "app": app_id,
                "intent": intent.id,
                "promotion_epoch": int(reconciled.eligibility_epoch),
                "intent_row_epoch": int(intent_epoch),
            }

        # ═══ S17：close-capture 的 leader 在 promotion **后**失格（AC 10.10 末句）═══
        try:
            s17 = await _stage_close_capture(
                "close_capture_stale", {PERIOD: "2024", TOTAL: Decimal("321")}
            )
            before = await _db_state(s17["entry"]["wp"], s17["env"]["room"], s17["app"])
            # reconciler 见到 `state=promoted` 就提前返回（源码原文：「已 promotion：
            # 授权失效只能由最终 fence 走 recovery」），所以这里直接推进 room 的
            # eligibility epoch —— 与 S12 用 UPDATE 撤销 participant 是同一手法。
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "UPDATE working_paper_oo_room SET close_leader_eligibility_epoch "
                        "= close_leader_eligibility_epoch + 1 WHERE id = :r"
                    ),
                    {"r": s17["env"]["room"]},
                )
                await s.commit()
            async with Session() as s:
                coord = _coordinator(s, probe=_RecordingProbe())
                outcome = await coord.apply_durable_incoming(
                    operation_id=s17["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s17["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=_JsonCarrierAdapter(),
                    contract=contract,
                    actor_id=user_a,
                )
            after = await _db_state(s17["entry"]["wp"], s17["env"]["room"], s17["app"])
            async with Session() as s:
                intent_state = (
                    await s.execute(
                        sa.text(
                            "SELECT state FROM working_paper_oo_close_intent WHERE id=:i"
                        ),
                        {"i": s17["intent"]},
                    )
                ).scalar_one()
                leader_pointer = (
                    await s.execute(
                        sa.text(
                            "SELECT close_leader_intent_id FROM working_paper_oo_room "
                            "WHERE id=:r"
                        ),
                        {"r": s17["env"]["room"]},
                    )
                ).scalar_one_or_none()
                intent_events = [
                    dict(row._mapping)
                    for row in (
                        await s.execute(
                            sa.text(
                                "SELECT to_state, authorization_result, error_code "
                                "FROM working_paper_oo_close_intent_event "
                                "WHERE intent_id=:i ORDER BY sequence_no"
                            ),
                            {"i": s17["intent"]},
                        )
                    ).all()
                ]
                capture_requests = int(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT count(*) FROM working_paper_forcesave_request "
                                "WHERE room_id=:r AND kind='close_capture'"
                            ),
                            {"r": s17["env"]["room"]},
                        )
                    ).scalar_one()
                )
            snap["scenarios"]["close_capture_stale"] = {
                "outcome": outcome.as_dict(),
                "before": before,
                "after": after,
                "promotion_epoch": s17["promotion_epoch"],
                "intent_state": str(intent_state),
                "leader_pointer": _opt(leader_pointer),
                "intent_events": intent_events,
                "capture_request_count": capture_requests,
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("close_capture_stale", exc)

        # ═══ S18：close-capture 正对照 —— epoch 未变时必须照常 applied ═══════════
        #
        # 没有这条，把 eligibility 分支写成「close-capture 一律拒」也能让 S17 变红，
        # 而那会让 clean close 恒失败（AC 4.10 的干净关闭永远拿不到内容）。
        try:
            s18 = await _stage_close_capture(
                "close_capture_ok",
                {PERIOD: "2024", TOTAL: Decimal("654")},
                # promotion event 记 0（room 也是 0），intent 行被摆成 7 ⇒ 只有
                # 「读 promotion event」的实现才会判等值并放行。
                desync_intent_epoch=7,
            )
            before = await _db_state(s18["entry"]["wp"], s18["env"]["room"], s18["app"])
            async with Session() as s:
                coord = _coordinator(s, probe=_RecordingProbe())
                outcome = await coord.apply_durable_incoming(
                    operation_id=s18["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s18["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=_JsonCarrierAdapter(),
                    contract=contract,
                    actor_id=user_a,
                )
            after = await _db_state(s18["entry"]["wp"], s18["env"]["room"], s18["app"])
            snap["scenarios"]["close_capture_ok"] = {
                "outcome": outcome.as_dict(),
                "before": before,
                "after": after,
                "promotion_epoch": s18["promotion_epoch"],
                "intent_row_epoch": s18["intent_row_epoch"],
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("close_capture_ok", exc)

        # ═══ S19：带人工裁决 ⇒ 折叠后发布（Task 27 把 Task 26 的欠账还了）═══
        #
        # 这个场景与 S3（conflict）是同一个三方局面，唯一差别是**带上了裁决**。
        # Task 26 交付时它会走无冲突分支、用 `merge.merged`（冲突字段保留 current 侧值）
        # 发布内容 —— 于是「审计师点了取 incoming，落库的是 current」，而 extract 等值、
        # roundtrip 与最终 fence 全部照常通过。Task 27 接线后判据翻转成：
        #   ① 结果是 applied/refresh_required（不再是拒绝）；
        #   ② 落库 projection 的 digest 等于 `apply_resolutions` 的重算结果，
        #      且**不等于** `merge.merged` 的 digest（真值 vs 错值两侧都断言）；
        #   ③ content version 的 source 是 `conflict_resolution`（AC 8.6 分桶）；
        #   ④ 冲突行留下 resolved_by/resolved_at/resolved_value 轨迹（AC 8.6）。
        try:
            s19 = await _stage_world(
                "adjudication_applied",
                base_values={PERIOD: "A", TOTAL: Decimal("1")},
                current_values={PERIOD: "B", TOTAL: Decimal("1")},
                incoming_values={PERIOD: "C", TOTAL: Decimal("1")},
            )
            # 先跑一次不带裁决的 merge 拿到真实 conflict record（裁决必须逐条对应真冲突，
            # 否则 Task 14 的 `UnknownConflictResolutionError` 会先抛，判据就串台了）。
            probe_dry = _RecordingProbe()
            async with Session() as s:
                coord = _coordinator(s, probe=probe_dry)
                dry = await coord.apply_durable_incoming(
                    operation_id=s19["req"]["operation"],
                    declared_project_id=project,
                    declared_wp_id=s19["entry"]["wp"],
                    declared_entry_id=ENTRY,
                    adapter=_JsonCarrierAdapter(),
                    contract=contract,
                    actor_id=user_a,
                )
            record = dry.merge.conflicts.records[0]
            choice = CF.ResolutionChoice(
                stable_field_key=record.locator.stable_field_key,
                row_key=record.locator.row_key,
                oo_location=record.locator.oo_location,
                kind=CF.ResolutionKind.take_incoming,
            )
            before = await _db_state(s19["entry"]["wp"], s19["env"]["room"], s19["app"])
            probe = _RecordingProbe()
            adapter = _JsonCarrierAdapter()
            raised: str | None = None
            raised_code: str | None = None
            resolved_outcome: dict[str, Any] | None = None
            async with Session() as s:
                coord = _coordinator(s, probe=probe)
                try:
                    got = await coord.apply_durable_incoming(
                        operation_id=s19["req"]["operation"],
                        declared_project_id=project,
                        declared_wp_id=s19["entry"]["wp"],
                        declared_entry_id=ENTRY,
                        adapter=adapter,
                        contract=contract,
                        resolutions=[choice],
                        actor_id=user_a,
                    )
                    resolved_outcome = got.as_dict()
                except Exception as exc:  # noqa: BLE001 - 期望成功；失败类型/码进快照
                    raised = type(exc).__name__
                    raised_code = getattr(exc, "error_code", None)
            after = await _db_state(s19["entry"]["wp"], s19["env"]["room"], s19["app"])
            # 裁决值确实与 `merge.merged` 不同 —— 前提成立，本场景才有意义。
            resolved = M.apply_resolutions(dry.merge, [choice], contract=contract)
            snap["scenarios"]["adjudication_applied"] = {
                "dry_result": dry.result.value,
                "dry_conflict_count": dry.conflict_count,
                "raised": raised,
                "raised_error_code": raised_code,
                "outcome": resolved_outcome,
                "adapter_calls": list(adapter.calls),
                "probe_calls": len(probe.calls),
                "before": before,
                "after": after,
                "merge_merged_value": str(dry.merge.merged.get(PERIOD).value),
                "resolved_value": str(resolved.get(PERIOD).value),
                "incoming_value": "C",
                "resolved_projection_sha": projection_canonical_digest(resolved),
                "merge_merged_projection_sha": projection_canonical_digest(
                    dry.merge.merged
                ),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("adjudication_applied", exc)

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
        assert "tmp_task26_store_" in snap["base_root"]

    def test_no_phase_crashed_during_collection(self, snap: dict[str, Any]) -> None:
        """采集阶段一个都不许挂。

        这条与「异常记录不穿透」是同一个决定的两半：不记录就会变成 collection ERROR，
        而 `-rf` 只列 FAILED；只记录不断言则任何场景静默缺失都不会被发现。
        """
        assert snap["harness_errors"] == {}, snap["harness_errors"]

    def test_every_scenario_was_collected(self, snap: dict[str, Any]) -> None:
        assert set(snap["scenarios"]) == {
            "applied",
            "refresh",
            "conflict",
            "row_conflict",
            "fence_before_publish",
            "fence_before_write",
            "retry",
            "quarantined",
            "unmanaged_drift",
            "pre_bind",
            "bundle_swap",
            "initiator_revoked",
            "probe_broken",
            "probe_incomplete",
            "contributor_revoked",
            "reapply",
            "close_capture_stale",
            "close_capture_ok",
            "adjudication_applied",
        }


# ═══════════════════════════════════════════════════════════════════════════
# S1 applied：P25 / P29 / P62 / P65 / P14
# ═══════════════════════════════════════════════════════════════════════════


class TestAppliedHappyPath:
    def test_result_is_applied(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["applied"]
        assert sc["outcome"]["result"] == "applied", sc["outcome"]
        assert sc["outcome"]["conflict_count"] == 0

    def test_business_revision_advanced_exactly_once(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["applied"]
        assert sc["before"]["revision"] == 0
        assert sc["after"]["revision"] == 1, "OO→HTML 只产生**一次** business revision"
        assert sc["after"]["content_version_count"] == sc["before"]["content_version_count"] + 1

    def test_entry_pointer_moved_to_the_new_result_representation(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["applied"]
        assert (
            sc["after"]["entry_pointer_representation_id"]
            == sc["after"]["app_result_representation"]
        )
        assert sc["after"]["entry_pointer_representation_id"] != (
            sc["before"]["entry_pointer_representation_id"]
        )

    def test_p65_merged_projection_digest_equals_published_projection_artifact(
        self, snap: dict[str, Any]
    ) -> None:
        """application 的 merged digest 必须**逐字节等于**该 revision 的 projection sha256。

        AC 8.12：applied content version 同时绑定 merged projection hash 与 result
        representation identity。两个 hash 出自两套序列化 ⇒ 等于没绑定，而那种漂移
        在任何单表断言里都看不见。
        """
        sc = snap["scenarios"]["applied"]
        assert sc["after"]["app_merged_projection_sha"] is not None
        assert (
            sc["after"]["app_merged_projection_sha"]
            == sc["after"]["result_version_projection_sha"]
        ), (
            "merged_projection_sha256 ≠ content version 的 projection_sha256 —— "
            "`projection_canonical_digest` 与 `_stage_and_verify` 的序列化口径已漂移"
        )
        assert (
            sc["outcome"]["merged_projection_sha256"]
            == sc["after"]["app_merged_projection_sha"]
        )

    def test_p65_result_representation_bundle_equals_frozen_bundle(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["applied"]
        assert sc["after"]["result_rep_bundle"] == sc["after"]["app_bundle"]
        assert sc["after"]["result_rep_reason"] == "rematerialize"

    def test_p65_result_artifact_digest_matches_representation_and_application(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["applied"]
        assert (
            sc["after"]["app_result_artifact_sha"]
            == sc["after"]["result_rep_artifact_sha"]
            == sc["outcome"]["result_artifact_sha256"]
        )

    def test_p65_incoming_is_never_promoted(self, snap: dict[str, Any]) -> None:
        """incoming 行逐列未变：仍 `kind=incoming/state=durable`，`published_at` 为空。"""
        sc = snap["scenarios"]["applied"]
        assert sc["after"]["incoming_kind"] == "incoming"
        assert sc["after"]["incoming_state"] == "durable"
        assert sc["after"]["incoming_published_at"] is None
        assert sc["after"]["incoming_relative_path"] == sc["before"]["incoming_relative_path"]
        assert ".incoming/" in sc["after"]["incoming_relative_path"]
        assert sc["after"]["app_result_representation"] is not None

        # 🔴 上一版这里是 `assert ... != sc["incoming_sha"] or True` —— `X or True` 结构上
        # 永真，等于没写。它本该锁死的正是本条 Property 最贵的那半句「incoming 本身永不
        # 晋升、**也不得被复制后标记为 published/current**」。
        # 改成落在 artifact **身份与路径**上，而不是内容 sha256：内容寻址下 merged 恰好
        # 复现 incoming 字节时同 sha 是合法的，拿 sha 当判据会在那天误红 —— 这大概也是
        # 上一版加 `or True` 而不是改判据的原因。
        after = sc["after"]
        assert after["result_rep_artifact_id"] is not None
        assert after["result_rep_artifact_id"] != after["incoming_artifact_id"], (
            "result representation 复用了 incoming 那一行 artifact ⇒ incoming 被直接晋升"
        )
        assert ".incoming/" not in after["result_rep_artifact_path"], (
            f"result artifact 落在 incoming 目录下：{after['result_rep_artifact_path']}"
        )
        assert after["result_rep_artifact_kind"] != "incoming", (
            f"result artifact 的 kind 仍是 incoming：{after['result_rep_artifact_kind']}"
        )
        assert after["result_rep_artifact_state"] == "published", (
            "只有新生成的 canonical result 才可 published"
            f"，实得 {after['result_rep_artifact_state']}"
        )

    def test_p62_both_baselines_advance_when_merged_equals_incoming(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["applied"]
        assert sc["outcome"]["merged_projection_sha256"] == (
            sc["outcome"]["incoming_projection_sha256"]
        ), "本场景的前置假设：merged 与 incoming 等值"
        assert sc["after"]["room_last_applied"] == sc["after"]["current_content_version_id"]
        assert sc["after"]["room_client_confirmed_version"] == (
            sc["after"]["current_content_version_id"]
        )
        assert sc["after"]["room_client_confirmed_version"] != (
            sc["before"]["room_client_confirmed_version"]
        )
        assert sc["outcome"]["client_baseline_advanced"] is True
        assert sc["after"]["room_refresh_required_at"] is None
        assert sc["after"]["room_state"] == "active"

    def test_room_canonical_fence_points_at_this_application(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 10.11：server last-applied 与 canonical fence 必须原子同步。"""
        sc = snap["scenarios"]["applied"]
        assert sc["after"]["room_latest_durable_application"] == sc["application"]
        assert sc["after"]["room_latest_durable_sequence"] >= 1

    def test_application_and_operation_reached_applied_terminal(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["applied"]
        assert sc["after"]["app_state"] == "applied"
        assert sc["after"]["app_logical_result"] == "applied"
        assert "applied" in sc["after"]["operation_states"]
        assert sc["after"]["application_event_count"] > sc["before"]["application_event_count"]
        assert sc["after"]["operation_event_count"] > sc["before"]["operation_event_count"]

    def test_outbox_row_written_in_the_same_transaction(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["applied"]
        assert sc["after"]["outbox_rows"] == sc["before"]["outbox_rows"] + 1

    def test_p25_incoming_field_change_was_auto_merged(self, snap: dict[str, Any]) -> None:
        """incoming 改的 TOTAL 真的进了新版本（否则「applied」只是空提交）。"""
        sc = snap["scenarios"]["applied"]
        assert sc["outcome"]["result_revision"] == 1
        assert sc["outcome"]["conflict_count"] == 0

    def test_p14_reload_floor_equals_application_result_revision(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["applied"]
        assert sc["reload_floor_error"] is None, sc["reload_floor_error"]
        assert sc["reload_floor"] == sc["after"]["app_result_revision"] == 1
        assert sc["outcome"]["reload_floor_revision"] == sc["reload_floor"]

    def test_both_fences_ran_and_in_order(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["applied"]
        stages = sc["outcome"]["stages"]
        assert "fence_verified_before_publish" in stages
        assert "fence_verified_before_write" in stages
        assert stages.index("fence_verified_before_publish") < stages.index(
            "fence_verified_before_write"
        )
        assert stages.index("fence_verified_before_write") < stages.index(
            "business_committed"
        )
        assert sc["outcome"]["fence_compared_before_publish"] == (
            sc["outcome"]["fence_compared_before_write"]
        )
        assert len(sc["outcome"]["fence_compared_before_publish"]) == 10

    def test_probe_actually_executed_twice(self, snap: dict[str, Any]) -> None:
        """探针必须真跑两次（两道 fence 各一次）。

        硬编码返回值的探针会让 fence 变成摆设，而那种缺陷在「最终有没有报错」上看不出来。
        """
        assert snap["scenarios"]["applied"]["probe_calls"] == 2

    def test_p29_roundtrip_extract_ran_on_the_new_result(
        self, snap: dict[str, Any]
    ) -> None:
        """adapter 调用序列证明：三方 extract → materialize → 反读 extract → 未管理区域。"""
        calls = snap["scenarios"]["applied"]["adapter_calls"]
        assert calls.count("materialize") == 1
        assert calls.count("verify_unmanaged_regions") == 1
        extracts = [c for c in calls if c.startswith("extract:")]
        assert len(extracts) == 4, (
            f"应为 base/current/incoming 三次 + 反读一次，实得 {extracts}"
        )
        assert calls.index("materialize") == 3, (
            "materialize 必须在三方 extract 之后 —— 顺序反了就等于「没读 base/current "
            "就直接覆盖」"
        )
        assert calls[4].startswith("extract:"), "materialize 之后必须紧跟一次反读 extract"

    def test_substrate_origin_is_the_application_fk(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["applied"]
        assert sc["outcome"]["substrate_origin"] == "application_incoming_fk"

    def test_callback_ack_is_zero(self, snap: dict[str, Any]) -> None:
        assert snap["scenarios"]["applied"]["outcome"]["callback_response_error"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# S2 refresh_required：P62 的下半段
# ═══════════════════════════════════════════════════════════════════════════


class TestRefreshRequired:
    def test_result_is_refresh_required(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["refresh"]
        assert sc["outcome"]["result"] == "refresh_required", sc["outcome"]
        assert sc["merged_equals_incoming"] is False, (
            "本场景的前置假设：current 改了另一个字段 ⇒ merged 同时含两侧 ⇒ ≠ incoming"
        )

    def test_server_last_applied_advances_but_client_confirmed_does_not(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 2.9 / 4.11 / Property 62 的核心：两条基线不混同。"""
        sc = snap["scenarios"]["refresh"]
        assert sc["after"]["revision"] == sc["before"]["revision"] + 1
        assert sc["after"]["room_last_applied"] == sc["after"]["current_content_version_id"]
        assert sc["after"]["room_client_confirmed_version"] == (
            sc["before"]["room_client_confirmed_version"]
        ), "merged ≠ incoming 时 client-confirmed 基线必须保持旧值"
        assert sc["outcome"]["client_baseline_advanced"] is False

    def test_room_is_refresh_required_and_superseded(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["refresh"]
        assert sc["after"]["room_refresh_required_at"] == "set"
        assert sc["after"]["room_refresh_reason"] is not None
        assert sc["after"]["room_state"] == "superseded"
        assert sc["outcome"]["room_refresh_required"] is True
        assert sc["outcome"]["room_superseded"] is True

    def test_next_forcesave_is_rejected(self, snap: dict[str, Any]) -> None:
        """AC 4.11：supersede/reopen 之前不得接受下一次 request。

        判据是**真调一次** Task 21 的资格门，而不是断言某个布尔字段 —— 后者只能证明
        coordinator 自己怎么想，证明不了下一次 forcesave 真的进不来。
        """
        sc = snap["scenarios"]["refresh"]
        assert sc["next_forcesave"]["accepted"] is False, sc["next_forcesave"]
        assert sc["next_forcesave"].get("unexpected") is not True, sc["next_forcesave"]
        assert sc["outcome"]["next_forcesave_allowed"] is False

    def test_application_and_operation_are_refresh_required(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["refresh"]
        assert sc["after"]["app_state"] == "refresh_required"
        assert sc["after"]["app_logical_result"] == "refresh_required"
        assert "refresh_required" in sc["after"]["operation_states"]

    def test_result_revision_still_bound_for_audit(self, snap: dict[str, Any]) -> None:
        """服务器结果仍然落库（AC 2.9 前半句），只是编辑器要重开确认。"""
        sc = snap["scenarios"]["refresh"]
        assert sc["after"]["app_result_revision"] == sc["after"]["revision"]
        assert sc["after"]["app_result_representation"] is not None

    def test_reload_floor_is_withheld_until_reopen(self, snap: dict[str, Any]) -> None:
        assert snap["scenarios"]["refresh"]["outcome"]["reload_floor_revision"] is None


# ═══════════════════════════════════════════════════════════════════════════
# S3 / S4 冲突：P26 / P27 / AC 8.11
# ═══════════════════════════════════════════════════════════════════════════


class TestConflictLeavesEverythingUntouched:
    def test_result_is_conflict_with_exactly_one_record(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["conflict"]
        assert sc["outcome"]["result"] == "conflict", sc["outcome"]
        assert sc["outcome"]["conflict_count"] == 1
        assert sc["outcome"]["conflict_set_digest"] is not None

    def test_no_revision_no_pointer_no_version(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["conflict"]
        for key in (
            "revision",
            "current_content_version_id",
            "entry_pointer_representation_id",
            "entry_pointer_generation",
            "content_version_count",
            "outbox_rows",
        ):
            assert sc["after"][key] == sc["before"][key], f"{key} 在冲突分支被改动"

    def test_neither_baseline_moved(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["conflict"]
        assert sc["after"]["room_last_applied"] == sc["before"]["room_last_applied"]
        assert sc["after"]["room_client_confirmed_version"] == (
            sc["before"]["room_client_confirmed_version"]
        )
        assert sc["after"]["room_refresh_required_at"] is None

    def test_application_records_the_conflict_set(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["conflict"]
        assert sc["after"]["app_state"] == "conflict"
        assert sc["after"]["app_conflict_count"] == 1
        assert sc["after"]["app_conflict_digest"] == sc["outcome"]["conflict_set_digest"]
        assert sc["after"]["app_result_revision"] is None
        assert sc["after"]["app_result_representation"] is None

    def test_conflict_path_never_materializes(self, snap: dict[str, Any]) -> None:
        """未裁决冲突不得走到 materialize/publish（AC 8.11）。"""
        sc = snap["scenarios"]["conflict"]
        assert "materialize" not in sc["adapter_calls"]
        assert "verify_unmanaged_regions" not in sc["adapter_calls"]
        assert "fence_verified_before_publish" not in sc["outcome"]["stages"]
        assert "conflict_recorded" in sc["outcome"]["stages"]

    def test_conflict_path_does_not_burn_the_fence_probe(self, snap: dict[str, Any]) -> None:
        """冲突分支不该调授权探针：它没有要提交的内容。"""
        assert snap["scenarios"]["conflict"]["probe_calls"] == 0

    def test_p27_only_the_touched_row_conflicts(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["row_conflict"]
        assert sc["result"] == "conflict", (
            sc["result"], sc.get("error_code"), sc.get("error_detail")
        )
        assert sc["conflicted_rows"] == [sc["expected_conflicted_row"]], sc
        assert sc["merged_other_row_value"] == "22", (
            "其他行必须照常合并 —— 位置/生命周期变化不得被误判为整表覆盖（AC 6.9）"
        )

    def test_p27_row_conflict_also_leaves_pointers_untouched(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["row_conflict"]
        assert sc["after"]["revision"] == 0
        assert sc["after"]["app_result_revision"] is None


# ═══════════════════════════════════════════════════════════════════════════
# S5 / S6 / S11 / S12 最终授权 fence：P43
# ═══════════════════════════════════════════════════════════════════════════


class TestFinalAuthorizationFence:
    @pytest.mark.parametrize(
        "scenario,expected_code",
        [
            ("fence_before_publish", "final_fence_project_not_visible"),
            ("fence_before_write", "final_fence_project_not_visible"),
            ("bundle_swap", "final_fence_approved_bundle_replaced"),
            ("initiator_revoked", "final_fence_initiator_not_live"),
        ],
        ids=["revoked_before_publish", "revoked_before_write", "bundle_replaced", "initiator_revoked"],
    )
    def test_each_revocation_shape_blocks_the_commit(
        self, snap: dict[str, Any], scenario: str, expected_code: str
    ) -> None:
        sc = snap["scenarios"][scenario]
        assert sc["outcome"]["result"] == "authorization_stale", sc["outcome"]
        assert sc["outcome"]["error_code"] == expected_code, sc["outcome"]

    @pytest.mark.parametrize(
        "scenario",
        ["fence_before_publish", "fence_before_write", "bundle_swap", "initiator_revoked"],
        ids=lambda v: v,
    )
    def test_nothing_committed_on_fence_failure(
        self, snap: dict[str, Any], scenario: str
    ) -> None:
        """P43：即使已 durable、已 rematerialize，也不得推进 revision 与任何指针。"""
        sc = snap["scenarios"][scenario]
        for key in (
            "revision",
            "current_content_version_id",
            "entry_pointer_representation_id",
            "content_version_count",
            "room_last_applied",
            "room_client_confirmed_version",
            "room_latest_durable_application",
            "outbox_rows",
        ):
            assert sc["after"][key] == sc["before"][key], (
                f"{scenario}: {key} 在 fence 失败后仍被改动"
            )

    @pytest.mark.parametrize(
        "scenario",
        ["fence_before_publish", "fence_before_write", "bundle_swap", "initiator_revoked"],
        ids=lambda v: v,
    )
    def test_application_and_operation_are_authorization_stale_not_error(
        self, snap: dict[str, Any], scenario: str
    ) -> None:
        """授权失效必须是独立终态：普通 retry 不重新取授权，混进 error 就绕过撤权。"""
        sc = snap["scenarios"][scenario]
        assert sc["after"]["app_state"] == "authorization_stale"
        assert sc["after"]["app_logical_result"] == "authorization_stale"
        assert "authorization_stale" in sc["after"]["operation_states"]

    @pytest.mark.parametrize(
        "scenario",
        ["fence_before_publish", "fence_before_write", "bundle_swap", "initiator_revoked"],
        ids=lambda v: v,
    )
    def test_incoming_survives_fence_failure(
        self, snap: dict[str, Any], scenario: str
    ) -> None:
        sc = snap["scenarios"][scenario]
        assert sc["after"]["incoming_kind"] == "incoming"
        assert sc["after"]["incoming_state"] == "durable"
        assert sc["after"]["incoming_published_at"] is None

    def test_publish_fence_fires_before_any_file_is_published(
        self, snap: dict[str, Any]
    ) -> None:
        """第一道 fence 在 publish **之前** ⇒ `.versions` 下不得多出新 xlsx。

        这条与 `test_nothing_committed_on_fence_failure` 不同：后者只看数据库。
        publish 是内容寻址的**不可变**发布，一旦发生就只能留 orphan。
        """
        sc = snap["scenarios"]["fence_before_publish"]
        assert sc["probe_calls"] == 1, "应当在第一道 fence 就失败"
        assert "materialize" in sc["adapter_calls"], (
            "前置假设：materialize 已经发生（fence 在它之后）"
        )
        assert sc["new_files"] == [], (
            f"fence 失败却已发布新 artifact: {sc['new_files']}"
        )

    def test_write_fence_fires_after_publish_and_before_revision_bump(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["fence_before_write"]
        assert sc["probe_calls"] == 2, "第一道通过、第二道失败"
        stages = sc["outcome"]["stages"]
        assert "fence_verified_before_publish" in stages
        assert "fence_verified_before_write" not in stages
        assert "business_committed" not in stages
        assert sc["after"]["revision"] == sc["before"]["revision"]


# ═══════════════════════════════════════════════════════════════════════════
# S7 retry：P19 / P38
# ═══════════════════════════════════════════════════════════════════════════


class TestDurablePostFailureAndRetry:
    def test_p19_post_durable_failure_acks_zero_and_keeps_incoming(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["retry"]
        failed = sc["failed_outcome"]
        assert failed["result"] == "error", failed
        assert failed["callback_response_error"] == 0, (
            "durable 之后返回非零 = 静默丢件（Task 4 实测 OO 不重投）"
        )
        assert sc["mid"]["incoming_kind"] == "incoming"
        assert sc["mid"]["incoming_state"] == "durable"

    def test_p19_no_pointer_moved_on_failure(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["retry"]
        for key in (
            "revision",
            "current_content_version_id",
            "entry_pointer_representation_id",
            "room_last_applied",
            "room_client_confirmed_version",
        ):
            assert sc["mid"][key] == sc["before"][key], f"{key} 在失败后被改动"

    def test_p19_application_and_operation_are_retryable_error(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["retry"]
        assert sc["mid"]["app_state"] == "error"
        assert sc["mid"]["app_logical_result"] == "error"
        assert "error" in sc["mid"]["operation_states"]

    def test_p38_retry_creates_no_second_operation_or_application(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["retry"]
        assert sc["same_operation"] is True
        assert sc["same_application"] is True
        assert sc["after"]["operation_count"] == sc["before"]["operation_count"]
        assert sc["after"]["app_count_for_wp"] == sc["before"]["app_count_for_wp"] == 1

    def test_p38_retry_reads_the_same_frozen_incoming(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["retry"]
        assert sc["same_substrate"] is True
        assert sc["retried_outcome"]["substrate_origin"] == "application_incoming_fk"

    def test_p38_retry_appends_to_the_same_timeline(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["retry"]
        assert sc["after"]["operation_event_count"] > sc["mid"]["operation_event_count"]
        assert sc["after"]["application_event_count"] > sc["mid"]["application_event_count"]

    def test_p38_retry_succeeds_and_produces_exactly_one_revision(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["retry"]
        assert sc["retried_outcome"]["result"] == "applied", sc["retried_outcome"]
        assert sc["retried_outcome"]["attempt"] == 2
        assert sc["after"]["revision"] == sc["before"]["revision"] + 1
        assert sc["after"]["app_state"] == "applied"

    def test_unmanaged_region_drift_blocks_publication(self, snap: dict[str, Any]) -> None:
        """AC 8.11：未管理区域变化 ⇒ application 失败，projection 不提交。"""
        sc = snap["scenarios"]["unmanaged_drift"]
        assert sc["outcome"]["result"] == "error", sc["outcome"]
        assert sc["outcome"]["error_code"] == "adapter_unmanaged_region_drift", sc["outcome"]
        assert sc["after"]["revision"] == sc["before"]["revision"]
        assert sc["after"]["app_state"] == "error"
        assert sc["after"]["incoming_state"] == "durable"


# ═══════════════════════════════════════════════════════════════════════════
# S8 quarantined：三层拒绝（AC 5.6 / 8.10）
# ═══════════════════════════════════════════════════════════════════════════


class TestQuarantinedThreeLayerRefusal:
    def test_sealing_produced_quarantined_not_durable(self, snap: dict[str, Any]) -> None:
        assert snap["scenarios"]["quarantined"]["sealed_state"] == "quarantined"

    def test_application_fk_layer_refuses(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["quarantined"]
        assert sc["application_created"] is None, "quarantined 不得创建 application"
        assert sc["layers"]["correlate"] is not None
        assert "Quarantined" in sc["layers"]["correlate"], sc["layers"]

    def test_coordinator_entry_layer_refuses_with_its_own_code(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["quarantined"]
        assert sc["layers"]["coordinator"] is not None
        assert "quarantined" in sc["layers"]["coordinator"].lower(), sc["layers"]

    def test_engine_layer_refuses(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["quarantined"]
        assert sc["layers"]["engine"] is not None
        assert "Quarantined" in sc["layers"]["engine"], sc["layers"]

    def test_coordinator_layer_is_not_shadowed_by_the_db_layer(
        self, snap: dict[str, Any]
    ) -> None:
        """coordinator 层必须**先于** DB 层触发，否则它是 provably-dead。

        判据是 error_code：coordinator 层的隔离拒绝是
        `substrate_incoming_quarantined_coordinator`，DB 层是
        `quarantined_incoming_rejected`。反过来排序时 `open_substrate` 报的是后者 ⇒
        「删掉 coordinator 层」在变异检验里判 GREEN（首轮实测即如此）。
        """
        layers = snap["scenarios"]["quarantined"]["layers"]
        assert layers["coordinator"].endswith(
            "substrate_incoming_quarantined_coordinator"
        ), f"coordinator 层被 DB 层遮蔽了: {layers}"
        assert layers["correlate"].endswith("quarantined_incoming_rejected"), layers
        assert layers["engine"].endswith("quarantined_incoming_rejected"), layers
        assert layers["coordinator"] != layers["engine"]


# ═══════════════════════════════════════════════════════════════════════════
# S10 / S13 边界
# ═══════════════════════════════════════════════════════════════════════════


class TestPreBindAndProbe:
    def test_p14_pre_bind_shell_refuses_to_report_result_revision(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["pre_bind"]
        assert sc["shell_application_id"] is None, "前置假设：这是未 correlate 的 shell"
        assert sc["shell_duplicate_of"] is None
        assert "returned" not in sc, f"pre-bind shell 竟然给出了 revision: {sc}"
        assert sc["error_code"] == "pre_bind_shell_has_no_result_revision", sc

    def test_broken_probe_fails_visibly_and_commits_nothing(
        self, snap: dict[str, Any]
    ) -> None:
        """无 fail-open：探针接线错误必须表现为可诊断失败，而不是「无此限制」。"""
        sc = snap["scenarios"]["probe_broken"]
        assert sc["outcome"]["result"] == "error", sc["outcome"]
        assert sc["outcome"]["error_code"] == "authorization_probe_failed", sc["outcome"]
        assert sc["after"]["revision"] == sc["before"]["revision"]
        assert sc["after"]["app_state"] == "error"
        assert sc["after"]["incoming_state"] == "durable"

    def test_incomplete_probe_response_is_refused_not_treated_as_allowed(
        self, snap: dict[str, Any]
    ) -> None:
        """探针**正常返回但少一个键** ⇒ 仍拒（「缺字段视为放行」是经典 fail-open）。

        与上一条不是重复：那条是探针抛异常，这条是返回结构不对 —— 后者才是真实接线
        错误的主要形态（改了返回结构、拼错键名）。少了 `if key not in external` 那条，
        `project_visible` 判据会静默消失而不是抛。
        """
        sc = snap["scenarios"]["probe_incomplete"]
        assert sc["outcome"]["result"] == "error", sc["outcome"]
        assert sc["outcome"]["error_code"] == "authorization_probe_failed", sc["outcome"]
        assert "project_visible" in (sc["outcome"]["error_detail"] or ""), sc["outcome"]
        assert sc["after"]["revision"] == sc["before"]["revision"]
        assert sc["after"]["incoming_state"] == "durable"


class TestContributorSnapshotIsRecomputed:
    """AC 10.10 的 contributor 面：判据必须是**重算**，不是拿冻结值跟自己比。

    判别性输入：initiator（A）保持 active，另一位 contributor（B）被撤销。于是十条
    fence 里只有 contributor digest 那一条不等值 —— 其余九条全部相同。这是唯一能证伪
    「重算」的输入形态：撤销 initiator 会先在 `initiator_state` 那条失败，永远走不到
    contributor 比对（M/R04 首轮实测正是因此判 GREEN）。
    """

    def test_initiator_stays_live_so_only_the_contributor_branch_can_fire(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["contributor_revoked"]
        assert sc["initiator_state_after"] == "active", (
            "前置假设：只撤销 contributor B，initiator A 必须仍 active —— 否则本场景"
            "会在 `initiator_state` 那条先失败，证明不了 contributor 判据"
        )

    def test_contributor_revocation_blocks_the_commit(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["contributor_revoked"]
        assert sc["outcome"]["result"] == "authorization_stale", sc["outcome"]
        assert sc["outcome"]["error_code"] == (
            "final_fence_contributor_snapshot_drift"
        ), sc["outcome"]

    def test_nothing_committed(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["contributor_revoked"]
        for key in ("revision", "current_content_version_id", "room_last_applied"):
            assert sc["after"][key] == sc["before"][key], f"{key} 被改动"
        assert sc["after"]["incoming_state"] == "durable"


# ═══════════════════════════════════════════════════════════════════════════
# S16 re-apply：同一 frozen application 只应用一次（AC 4.3 / 8.12 / P65）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 修前实测（2026-08-27，短路 `assert_application_state_admits_apply` 后的真实输出）：
# 第二次调用**跑完整条 pipeline** —— 三侧 extract + materialize 写出新的 staged result +
# 未管理区域比对（adapter 调用 6 次），直到写库阶段才撞出
# `StateTransitionError:illegal_state_transition`；`_record_post_durable_failure` 自己
# 也要走 `applied → error`（同样非法）⇒ 异常穿透入口，application/operation timeline
# 零 event。根因：`APPLICATION_EDGES[applied]` 是空集 ⇒ `_walk_application` 的
# 「到不了这一站就跳过」把整条 pipeline 静默跳过、`_advance_application` 在
# `from == to` 时提前返回 ⇒ 状态机不但没拦，反而成了掩护。
#
# **没有**观测到第二个 business revision：状态机在写库前偶然拦住了它。那份保护依赖
# 「`applied` 恰好没有出边」这个与 AC 4.3 无关的事实，所以下面的
# `test_nothing_moved_on_the_second_attempt` 在修前也是绿的 —— 它是「拒绝本身不得损坏
# 状态」的互补判据，不是本缺陷的证人。证人是另两条（拒绝的 error_code + 零 adapter）。
#
# 修法：入口按 `APPLICATION_EDGES` 反向可达性判准入，`applied/refresh_required` 与
# `superseded/authorization_stale` 各自一个 error_code。


class TestReapplyIsRefused:
    def test_first_apply_succeeded(self, snap: dict[str, Any]) -> None:
        """前置假设：第一次必须真的 applied，否则第二次的拒绝证明不了任何事。"""
        sc = snap["scenarios"]["reapply"]
        assert sc["first_outcome"]["result"] == "applied", sc["first_outcome"]
        assert sc["after_first"]["revision"] == 1
        assert sc["after_first"]["app_state"] == "applied"

    def test_second_apply_is_refused_with_its_own_error_code(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["reapply"]
        assert sc["second_outcome"] is None, (
            "第二次 apply 返回了 outcome —— 说明它跑完了整条流程。"
            f"实得 {sc['second_outcome']}"
        )
        assert sc["second_error"] == "ReapplyForbiddenError:application_already_applied", (
            f"实得 {sc['second_error']} —— 「已应用过」必须与「已作废」分型"
        )

    def test_nothing_moved_on_the_second_attempt(self, snap: dict[str, Any]) -> None:
        """逐列比对，而不是只看 revision：第二次不得留下任何痕迹。

        ⚠️ 本条在「删掉入口准入门」的变异下**仍是绿的**（状态机偶然拦住了写库），
        因此它不是缺陷②的证人 —— 它证的是另一件事：拒绝路径自己不得改坏状态。
        """
        sc = snap["scenarios"]["reapply"]
        first, second = sc["after_first"], sc["after_second"]
        for key in (
            "revision",
            "current_content_version_id",
            "content_version_count",
            "entry_pointer_representation_id",
            "entry_pointer_generation",
            "app_result_revision",
            "app_result_representation",
            "app_result_artifact_sha",
            "app_state",
            "room_last_applied",
            "room_client_confirmed_version",
            "room_latest_durable_application",
            "operation_count",
            "operation_states",
            "operation_event_count",
            "application_event_count",
            "outbox_rows",
        ):
            assert second[key] == first[key], (
                f"{key}: 第二次 apply 改动了它（{first[key]!r} → {second[key]!r}）—— "
                "同一 frozen application 只能应用一次"
            )

    def test_refusal_happens_before_any_adapter_or_probe_call(
        self, snap: dict[str, Any]
    ) -> None:
        """「立即失败」= 零 adapter、零探针。只断言「最终报错」时，
        「跑完 materialize 再报错」也算通过 —— 那已经写过文件了。"""
        sc = snap["scenarios"]["reapply"]
        assert sc["second_adapter_calls"] == [], sc["second_adapter_calls"]
        assert sc["second_probe_calls"] == 0

    def test_incoming_still_intact(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["reapply"]
        assert sc["after_second"]["incoming_kind"] == "incoming"
        assert sc["after_second"]["incoming_state"] == "durable"
        assert sc["after_second"]["incoming_published_at"] is None


# ═══════════════════════════════════════════════════════════════════════════
# S17/S18 close-capture eligibility：AC 10.10 末句（promotion 之后失格）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 修前实测：`assert_final_authorization` 的 eligibility 判据是
# `if int(observed.close_leader_eligibility_epoch) < 0`。`room.close_leader_
# eligibility_epoch` 是 bigint、server_default 0、全仓库唯一写入点只做 `+1`
# ⇒ 永远非负 ⇒ 该分支 provably-dead，而 `compared` 里却报着
# `close_leader_eligibility_epoch`，宣称「eligibility 已重验」。
# 于是 S17 修前是 `applied`（revision 0→1、指针照常推进）。


class TestCloseCaptureEligibilityFence:
    def test_the_scenario_really_produced_a_close_capture(
        self, snap: dict[str, Any]
    ) -> None:
        """前置假设：reconciler 真的 CAS 出了 close-capture（不是普通 forcesave）。

        没有这条，把 `_stage_close_capture` 写错成普通 forcesave 时，S17 会因为
        「eligibility 对普通 forcesave 不适用」而**恰好也是 applied**，
        修与不修一个样。
        """
        for tag in ("close_capture_stale", "close_capture_ok"):
            sc = snap["scenarios"][tag]
            assert sc["promotion_epoch"] == 0, (
                f"{tag}: 单人 clean close 的 promotion epoch 应为 0，"
                f"实得 {sc['promotion_epoch']}"
            )
        assert snap["scenarios"]["close_capture_stale"]["capture_request_count"] == 1

    def test_epoch_advance_after_promotion_blocks_the_commit(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["close_capture_stale"]
        assert sc["outcome"]["result"] == "authorization_stale", sc["outcome"]
        assert sc["outcome"]["error_code"] == (
            "final_fence_eligibility_epoch_advanced"
        ), sc["outcome"]

    def test_the_fence_actually_compared_the_eligibility_item(
        self, snap: dict[str, Any]
    ) -> None:
        """S18（未变）必须报出 `close_leader_eligibility_epoch` 这一项。

        判据落在**比较过的项名**上：只断言 S17 报错时，「close-capture 一律拒」
        也能通过 —— 而那会让 clean close 恒失败。
        """
        ok = snap["scenarios"]["close_capture_ok"]["outcome"]
        assert "close_leader_eligibility_epoch" in ok["fence_compared_before_publish"]
        assert "close_leader_eligibility_epoch" in ok["fence_compared_before_write"]
        assert (
            "close_leader_eligibility_not_applicable"
            not in ok["fence_compared_before_publish"]
        )

    def test_ordinary_forcesave_reports_not_applicable(
        self, snap: dict[str, Any]
    ) -> None:
        """普通 forcesave 走另一条项名 —— 两条路径在运行期可分辨。"""
        applied = snap["scenarios"]["applied"]["outcome"]
        assert (
            "close_leader_eligibility_not_applicable"
            in applied["fence_compared_before_publish"]
        )
        assert (
            "close_leader_eligibility_epoch"
            not in applied["fence_compared_before_publish"]
        )

    def test_nothing_committed_when_eligibility_advanced(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["close_capture_stale"]
        for key in (
            "revision",
            "current_content_version_id",
            "content_version_count",
            "entry_pointer_representation_id",
            "room_last_applied",
            "room_client_confirmed_version",
        ):
            assert sc["after"][key] == sc["before"][key], f"{key} 被改动"
        assert sc["after"]["incoming_state"] == "durable"

    def test_generation_is_superseded_so_the_close_is_not_blocked_forever(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 10.10 末句的**后半**：不只是落 authorization_stale，还要 supersede/recovery。

        修前 `_record_post_durable_failure` 只写 application/operation 终态，room 停在
        `close_barrier` ⇒ close 永久等待，Property 63 明令禁止的「永久 blocked」。
        """
        sc = snap["scenarios"]["close_capture_stale"]
        assert sc["outcome"]["room_superseded"] is True, sc["outcome"]
        assert sc["after"]["room_state"] == "superseded", sc["after"]
        assert sc["after"]["room_refresh_reason"] == "close_capture_authorization_stale"

    def test_no_successor_can_be_promoted_afterwards(self, snap: dict[str, Any]) -> None:
        """「不得接任再造第二个 capture」：intent 必须**留在** `promoted`。

        `state=promoted` 是 `reconcile_close_intents` 提前返回（`already_promoted`）的
        唯一依据。把它推成终态会让短路失效，于是下一次 reconcile 会走
        「current_leader 已不合格」分支、推进 eligibility epoch 并另选 successor。

        V151 的 `ck_wpoci_promoted_pair` 也要求离开 `promoted` 必须置空
        `promoted_request_id`（= 毁掉 fence 反查 promotion epoch 的审计链），
        与 `CLOSE_INTENT_EDGES[promoted]` 登记的四条出边**互相矛盾** ——
        那是 Task 9/24 的欠账，本任务不靠毁证绕过。
        """
        sc = snap["scenarios"]["close_capture_stale"]
        assert sc["intent_state"] == "promoted", (
            f"intent 落到了 {sc['intent_state']} —— reconciler 的 already_promoted "
            "短路失效，successor 可以接任并造第二个 capture"
        )
        assert sc["leader_pointer"] is not None, (
            "leader 指针被清空 —— 审计上再也说不出「谁是那次 close 的 leader」"
        )
        assert sc["capture_request_count"] == 1
        assert [e["to_state"] for e in sc["intent_events"]][-1] == "promoted", (
            "close intent 的 append-only timeline 末态必须仍是 promoted"
        )

    def test_close_capture_with_unchanged_epoch_still_applies(
        self, snap: dict[str, Any]
    ) -> None:
        """S18 正对照：epoch 未变的 clean close 必须照常拿到内容。"""
        sc = snap["scenarios"]["close_capture_ok"]
        assert sc["outcome"]["result"] == "applied", sc["outcome"]
        assert sc["before"]["revision"] == 0
        assert sc["after"]["revision"] == 1
        assert sc["after"]["app_state"] == "applied"
        assert sc["after"]["room_state"] != "superseded"

    def test_the_desync_between_intent_row_and_promotion_event_was_staged(
        self, snap: dict[str, Any]
    ) -> None:
        """判别性输入自证：intent 行的 epoch 必须**真的**与 promotion event 分叉。

        没有这条，`desync_intent_epoch` 哪天失效（列改名、UPDATE 打空）都不会有人发现，
        而 S18 会退化成「两值都是 0」的重言式 —— 那时「读 promotion event 而不是读
        intent 列」这个区分就无人能证伪。
        """
        sc = snap["scenarios"]["close_capture_ok"]
        assert sc["intent_row_epoch"] == 7
        assert sc["promotion_epoch"] == 0
        assert sc["intent_row_epoch"] != sc["promotion_epoch"]

    def test_frozen_side_reads_the_promotion_event_not_the_intent_row(
        self, snap: dict[str, Any]
    ) -> None:
        """S18 在 intent 行 epoch=7、room epoch=0 下仍 applied ⇒ 读的是 promotion event。

        读 intent 行的实现会把 7 与 room 的 0 比出不等 ⇒ 合法 successor 的 clean close
        被误判成 stale（真实世界里 successor 接任时 intent 行必然落后）。
        """
        sc = snap["scenarios"]["close_capture_ok"]
        assert sc["outcome"]["result"] == "applied", (
            "intent 行的创建时 epoch 被当成了冻结侧 —— 合法 successor 会被误杀"
        )
        assert (
            "close_leader_eligibility_epoch"
            in sc["outcome"]["fence_compared_before_write"]
        )

# ═══════════════════════════════════════════════════════════════════════════
# S19 带人工裁决 ⇒ 折叠后发布（Task 27 接线；曾是 Task 26 的 fail-closed 欠账）
# ═══════════════════════════════════════════════════════════════════════════


class TestManualAdjudicationIsAppliedOnRealDb:
    """同一个三方局面，仅多带一条裁决 ⇒ 必须发布**折叠结果**（不是 `merge.merged`）。

    ═══ Task 26 交付时会发生什么 ═══

    `resolutions` 非空时 coordinator 走的是**无冲突分支**，而那条分支提交的是
    `merge.merged` —— 它对每个冲突字段保留 current 侧值。四道关都不会拦：
    `apply_resolutions` 从未接线；Task 15 只校验裁决**覆盖率**；extract 等值比的是
    「result 与 merged 一致」（两边同为错值）；最终 fence 只看授权与身份。于是审计师的
    「取 incoming」被静默换成 current，且 `requires_client_refresh` 也按错值算。

    ═══ 为什么判据要**两侧**都断言 ═══

    只断言「落库值等于折叠结果」不够：若某天 `merge.merged` 恰好等于折叠结果（例如裁决
    选的就是 current），这条判据在真值与错值上同时成立 ⇒ 拦不住回退。所以本类同时断言
    「等于折叠 digest」**且**「不等于 `merge.merged` digest」，并先自证两者确实不同。
    """

    def test_the_same_world_really_produces_a_conflict(self, snap: dict[str, Any]) -> None:
        """判别性输入自证：不带裁决时它是 conflict（否则本场景什么都没测到）。"""
        sc = snap["scenarios"]["adjudication_applied"]
        assert sc["dry_result"] == "conflict", sc
        assert sc["dry_conflict_count"] == 1

    def test_adjudicated_value_really_differs_from_merge_merged(
        self, snap: dict[str, Any]
    ) -> None:
        """前提：裁决落地值 ≠ `merge.merged` 值，否则本类断言的两侧会重合。"""
        sc = snap["scenarios"]["adjudication_applied"]
        assert sc["merge_merged_value"] == "B", "merged 保持 current 侧（Task 14 语义）"
        assert sc["resolved_value"] == sc["incoming_value"] == "C"
        assert sc["merge_merged_value"] != sc["resolved_value"]
        assert sc["resolved_projection_sha"] != sc["merge_merged_projection_sha"]

    def test_call_with_resolutions_succeeds(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["adjudication_applied"]
        assert sc["raised"] is None, (sc["raised"], sc["raised_error_code"])
        assert sc["outcome"]["result"] in ("applied", "refresh_required"), sc["outcome"]
        assert sc["outcome"]["resolutions_applied"] == 1

    def test_the_published_projection_is_the_folded_one_not_merge_merged(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 本类的核心：落库 projection = `apply_resolutions` 结果，**不是** `merged`。"""
        sc = snap["scenarios"]["adjudication_applied"]
        after = sc["after"]
        assert after["app_merged_projection_sha"] == sc["resolved_projection_sha"], (
            "application 记录的 merged projection digest 不是折叠结果 —— "
            "审计师的裁决被静默换成了 current 侧值"
        )
        assert after["result_version_projection_sha"] == sc["resolved_projection_sha"], (
            "content version 落库的 projection digest 不是折叠结果"
        )
        assert after["app_merged_projection_sha"] != sc["merge_merged_projection_sha"]

    def test_conflict_resolution_is_its_own_source_bucket(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 8.6：带裁决的应用记成 `conflict_resolution`，与自动合并可区分。"""
        sc = snap["scenarios"]["adjudication_applied"]
        assert sc["after"]["result_version_source"] == "conflict_resolution", sc["after"]
        # 反向对照：不带裁决的 happy path 记成 onlyoffice（否则分桶等于恒定值）。
        assert (
            snap["scenarios"]["applied"]["after"]["result_version_source"]
            == "onlyoffice"
        )

    def test_conflict_rows_were_persisted_before_resolve(
        self, snap: dict[str, Any]
    ) -> None:
        """AC 8.1：冲突必须落行 —— 只记 count/digest 时预览无数据可读。"""
        sc = snap["scenarios"]["adjudication_applied"]
        assert sc["before"]["conflict_rows"] >= 1, sc["before"]
        assert sc["before"]["conflict_rows_live"] == sc["dry_conflict_count"]
        assert sc["before"]["conflict_rows_resolved"] == 0, (
            "裁决还没提交就已有 resolved 轨迹 —— 轨迹与事实脱钩"
        )

    def test_the_state_machine_is_not_what_let_it_through(
        self, snap: dict[str, Any]
    ) -> None:
        """自证：resolve 从 `conflict` 站继续是**登记过的**边，不是绕过状态机。"""
        from app.services.workpaper_sync import oo_to_html as OH
        from app.services.workpaper_sync.models import (
            APPLICATION_EDGES,
            ApplicationState,
        )

        sc = snap["scenarios"]["adjudication_applied"]
        assert sc["before"]["app_state"] == ApplicationState.conflict.value, sc["before"]
        assert ApplicationState.conflict in OH.APPLY_ADMISSIBLE_APPLICATION_STATES
        assert (
            ApplicationState.rematerializing
            in APPLICATION_EDGES[ApplicationState.conflict]
        ), "conflict → rematerializing 不是登记边 ⇒ resolve 走的是未登记的转换"

    def test_pointers_advanced_exactly_once(self, snap: dict[str, Any]) -> None:
        """revision / pointer / server last-applied 各推进一次，application 不新增。"""
        sc = snap["scenarios"]["adjudication_applied"]
        before, after = sc["before"], sc["after"]
        assert after["revision"] == before["revision"] + 1
        assert after["content_version_count"] == before["content_version_count"] + 1
        assert after["current_content_version_id"] != before["current_content_version_id"]
        assert (
            after["entry_pointer_representation_id"]
            != before["entry_pointer_representation_id"]
        )
        assert after["room_last_applied"] != before["room_last_applied"]
        # Property 38 的另一面：resolve 复用同一 timeline，不新建 operation/application。
        assert after["operation_count"] == before["operation_count"]
        assert after["app_count_for_wp"] == before["app_count_for_wp"]

    def test_incoming_was_not_promoted(self, snap: dict[str, Any]) -> None:
        """AC 8.10：incoming 行逐列未变，result artifact 是另一行、另一条路径。"""
        sc = snap["scenarios"]["adjudication_applied"]
        before, after = sc["before"], sc["after"]
        for column in (
            "incoming_kind",
            "incoming_state",
            "incoming_published_at",
            "incoming_relative_path",
            "incoming_artifact_id",
        ):
            assert before[column] == after[column], column
        assert after["result_rep_artifact_id"] != after["incoming_artifact_id"]
        assert not str(after["result_rep_artifact_path"]).startswith(".incoming/")
