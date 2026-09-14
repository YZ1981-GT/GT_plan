# -*- coding: utf-8 -*-
"""Task 12 真实 PostgreSQL 守卫：Property 7（十意图同解）、Property 28（definition/bundle
漂移 fail closed）、Property 42（DB 侧路径安全）与 candidate 隔离/finalize gate。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 12
Requirements: 2.3, 2.10, 6.10, 9.1, 9.6, 9.8, 9.11, 9.12
Properties: P7 / P28 / P39 / P42

═══ 为什么必须真库 + 真文件 ═══

Property 7 的原文是「十个意图对同一 (content version, entry, representation
generation) 解析到**相同** published artifact/path/hash、非空 immutable bundle 与
authority model」。这条判据只能在「有真实 representation 行 + 真实 entry pointer +
真实文件」的组合上成立：

* 没有真库 ⇒ V151 的 `trg_wpses_pointer`（entry pointer 只放行 published artifact）
  与 `trg_wpcr_identity`（bundle/authority/artifact 三重一致）不参与判定，
  「三层门」退化成一层；
* 没有真文件 ⇒ `resolve_published_artifact` 的存在性检查恒不触发，
  「pointer 指向缺失 artifact」这个半成功态无法被观测。

═══ 隔离 ═══

scratch schema `tmp_task12_res_*`，`search_path` 不含 public，
`projects/users/working_paper` 建桩表；文件全在系统临时目录。结束
`DROP SCHEMA CASCADE` + 删临时目录。**绝不触碰真实 `storage/`**。

`DATABASE_URL` 非 PostgreSQL 时**直接失败不 skip** —— 本任务判据就是数据库 + 文件
系统的联合行为，skip 等于静默抹掉唯一判据。

═══ 采集写法 ═══

全部场景由**一次 `asyncio.run`** 跑完并落进快照（module fixture）。不给每个测试各自
开 async（共享连接池会被污染，第二个测试起 `NoneType has no attribute send`）。
采集内部任何异常都记进快照的 `errors`，由守卫断言为空 —— **禁 fail-open**。
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

_SCHEMA_PREFIX = "tmp_task12_res_"
ENTRY = "g7.disclosure.listed"
OTHER_ENTRY = "g7.disclosure.soe"

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

_XLSX_CT = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="xml" ContentType="application/xml"/></Types>'
)
_WORKBOOK = b'<?xml version="1.0"?><workbook><sheets/></workbook>'


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _xlsx(marker: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _XLSX_CT)
        zf.writestr("xl/workbook.xml", _WORKBOOK)
        zf.writestr("xl/marker.xml", f"<m>{marker}</m>".encode())
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# 采集
# ═══════════════════════════════════════════════════════════════════════════


async def _collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部场景
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.services.workpaper_sync import definitions as D
    from app.services.workpaper_sync.artifacts import (
        CandidateNotResolvableError,
        CanonicalArtifactRepository,
    )
    from app.services.workpaper_sync.canonical_paths import DocumentTypeMismatchError
    from app.services.workpaper_sync.models import (
        ArtifactKind,
        ArtifactState,
        BundleIntegrityError,
        BundleSlot,
        BundleSlotSpec,
        CandidateState,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import (
        CandidateNotFinalizableError,
        CanonicalResolutionService,
        HistoricalResolutionError,
        ResolutionIntent,
    )

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 12 的判据是「十意图对同一 representation 解析到同一 artifact + "
            "frozen bundle」，依赖 V151 的 trigger 与真实文件；必须真实 PostgreSQL，"
            f"当前 DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task12_store_"))
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
        "intents": {},
        "frozen_vs_current": {},
        "unapproved_bundle": {},
        "candidate": {},
        "finalize": {},
        "path_safety": {},
        "document_type": {},
        "digest_drift": {},
        "pointer": {},
    }
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

        project, wp, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        other_wp = uuid.uuid4()
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{project}')")
            await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{user}')")
            for w in (wp, other_wp):
                await conn.exec_driver_sql(
                    f"INSERT INTO working_paper (id, project_id) VALUES ('{w}', '{project}')"
                )

        artifacts = CanonicalArtifactRepository(base_root)

        # ── 真发布 gen-1 / gen-2 canonical 与 definition blobs ─────────────
        g1 = artifacts.publish_representation(
            entry_id=ENTRY, generation=1,
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=_xlsx("g1"), document_type="xlsx"
            ),
        )
        g2 = artifacts.publish_representation(
            entry_id=ENTRY, generation=2,
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=_xlsx("g2"), document_type="xlsx"
            ),
        )
        proj = artifacts.publish_projection(
            revision=0,
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=b"projection-v0",
                document_type="json.gz",
            ),
        )
        blob_kinds = {
            "tpl": "template", "instr": "instrumentation", "contract": "contract",
            "contract2": "contract", "authority": "authority_model",
            "authority2": "authority_model",
            "bundle_payload": "bundle", "bundle_payload_v2": "bundle",
            "bundle_payload_unapproved": "bundle",
        }
        blobs = {
            name: artifacts.publish_definition_blob(
                project_id=project, wp_id=wp, definition_kind=kind,
                payload=json.dumps({"k": name}, sort_keys=True).encode(),
            )
            for name, kind in blob_kinds.items()
        }

        # digest 值：definition 的 sha256 是 canonical payload 的 hash，
        # 本测试用固定标签生成（真实发布由 DefinitionPublisher 负责）。
        sha = {
            "tpl": _d("task12-template"),
            "instr": _d("task12-instrumentation"),
            "contract": _d("task12-contract"),
            "contract2": _d("task12-contract-v2"),
            "authority": _d("task12-authority"),
            "authority2": _d("task12-authority-alt"),
        }

        world: dict[str, Any] = {}
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            art_rows = {
                name: await repo.register_artifact(
                    project_id=project, wp_id=wp,
                    kind=ArtifactKind.definition, state=ArtifactState.published,
                    relative_path=pub.relative_path, sha256=pub.sha256,
                    size_bytes=pub.size_bytes, document_type=pub.document_type,
                    retention_class="definition",
                )
                for name, pub in blobs.items()
            }
            art_g1 = await repo.register_artifact(
                project_id=project, wp_id=wp,
                kind=ArtifactKind.canonical, state=ArtifactState.published,
                relative_path=g1.relative_path, sha256=g1.sha256,
                size_bytes=g1.size_bytes, document_type="xlsx",
            )
            art_g2 = await repo.register_artifact(
                project_id=project, wp_id=wp,
                kind=ArtifactKind.canonical, state=ArtifactState.published,
                relative_path=g2.relative_path, sha256=g2.sha256,
                size_bytes=g2.size_bytes, document_type="xlsx",
            )
            art_proj = await repo.register_artifact(
                project_id=project, wp_id=wp,
                kind=ArtifactKind.projection, state=ArtifactState.published,
                relative_path=proj.relative_path, sha256=proj.sha256,
                size_bytes=proj.size_bytes, document_type="json.gz",
            )

            tpl = await repo.create_definition_artifact(
                kind="template", logical_id="task12.template", semantic_version="1.0.0",
                blob_artifact_id=art_rows["tpl"].id, sha256=sha["tpl"],
                structure_hash=_d("tpl-structure"), source_commit="task12",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation", logical_id="task12.instr",
                semantic_version="1.0.0", blob_artifact_id=art_rows["instr"].id,
                sha256=sha["instr"], structure_hash=_d("instr-structure"),
                source_commit="task12",
            )
            contract = await repo.create_definition_artifact(
                kind="contract", logical_id="task12.contract", semantic_version="1.0.0",
                blob_artifact_id=art_rows["contract"].id, sha256=sha["contract"],
                source_commit="task12",
            )
            contract2 = await repo.create_definition_artifact(
                kind="contract", logical_id="task12.contract", semantic_version="2.0.0",
                blob_artifact_id=art_rows["contract2"].id, sha256=sha["contract2"],
                source_commit="task12",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task12.authority",
                semantic_version="1.0.0", blob_artifact_id=art_rows["authority"].id,
                sha256=sha["authority"], authority_model_type="projection_contract",
                source_commit="task12",
            )
            # 🔴 第二个 authority definition 只为让「unapproved bundle」拿到不同的
            #    canonical digest：`canonical_payload_sha256` 是 UNIQUE（内容寻址），
            #    两个 slot 完全相同的 bundle 在 DB 层就是同一份，插不进去。
            authority2 = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task12.authority",
                semantic_version="1.0.1", blob_artifact_id=art_rows["authority2"].id,
                sha256=sha["authority2"], authority_model_type="projection_contract",
                source_commit="task12",
            )

            def _slots(contract_row) -> dict[BundleSlot, BundleSlotSpec]:
                return {
                    BundleSlot.template: BundleSlotSpec(
                        BundleSlot.template, "definition",
                        f"definition:{tpl.id}", tpl.sha256,
                    ),
                    BundleSlot.instrumentation: BundleSlotSpec(
                        BundleSlot.instrumentation, "definition",
                        f"definition:{instr.id}", instr.sha256,
                    ),
                    BundleSlot.contract: BundleSlotSpec(
                        BundleSlot.contract, "definition",
                        f"definition:{contract_row.id}", contract_row.sha256,
                    ),
                }

            def _canonical_digest(contract_row, authority_row=None) -> str:
                return D.bundle_canonical_digest(
                    authority_model="projection_contract",
                    authority_model_definition_sha256=(
                        authority_row or authority
                    ).sha256,
                    slots=_slots(contract_row),
                )

            bundle = await repo.create_definition_bundle(
                authority_model_definition_id=authority.id,
                slots=_slots(contract),
                canonical_payload_artifact_id=art_rows["bundle_payload"].id,
                canonical_payload_sha256=_canonical_digest(contract),
            )
            # 「新版 bundle」：contract child 换成 v2 ⇒ 与 bundle v1 是不同 identity。
            bundle_v2 = await repo.create_definition_bundle(
                authority_model_definition_id=authority.id,
                slots=_slots(contract2),
                canonical_payload_artifact_id=art_rows["bundle_payload_v2"].id,
                canonical_payload_sha256=_canonical_digest(contract2),
            )
            # unapproved（candidate 态）bundle：resolver 必须拒绝
            bundle_unapproved = await repo.create_definition_bundle(
                authority_model_definition_id=authority2.id,
                slots=_slots(contract),
                canonical_payload_artifact_id=art_rows["bundle_payload_unapproved"].id,
                canonical_payload_sha256=_canonical_digest(contract, authority2),
                approved=False,
            )

            cv0 = await repo.create_content_version(
                project_id=project, wp_id=wp, entry_id=ENTRY, revision=0, source="html",
                projection_artifact_id=art_proj.id, projection_sha256=art_proj.sha256,
                actor_id=user,
            )
            rep1 = await repo.create_representation(
                project_id=project, wp_id=wp, entry_id=ENTRY,
                content_version_id=cv0.id, generation=1, document_type="xlsx",
                artifact_id=art_g1.id, artifact_sha256=art_g1.sha256,
                definition_bundle_id=bundle.id,
                authority_model_definition_id=authority.id,
                adapter_id="task12.adapter", adapter_build_digest=_d("adapter"),
                structure_hash=_d("structure-1"),
                identity_inventory_sha256=_d("identity-1"),
                reason="content_commit",
            )
            # gen-2：同 content version，换成 bundle_v2（纯 definition upgrade）
            rep2 = await repo.create_representation(
                project_id=project, wp_id=wp, entry_id=ENTRY,
                content_version_id=cv0.id, generation=2, document_type="xlsx",
                artifact_id=art_g2.id, artifact_sha256=art_g2.sha256,
                definition_bundle_id=bundle_v2.id,
                authority_model_definition_id=authority.id,
                adapter_id="task12.adapter", adapter_build_digest=_d("adapter"),
                structure_hash=_d("structure-2"),
                identity_inventory_sha256=_d("identity-2"),
                reason="definition_upgrade",
                parent_representation_id=rep1.id,
            )
            await repo.set_entry_pointer(
                wp_id=wp, entry_id=ENTRY, representation_id=rep2.id, generation=2
            )
            await s.commit()
            world.update({
                "cv0": cv0.id, "rep1": rep1.id, "rep2": rep2.id,
                "bundle": bundle.id, "bundle_v2": bundle_v2.id,
                "bundle_unapproved": bundle_unapproved.id,
                "authority": authority.id, "contract": contract.id,
                "contract2": contract2.id, "tpl": tpl.id, "instr": instr.id,
                "art_g1": art_g1.id, "art_g2": art_g2.id,
                "g1_rel": g1.relative_path, "g2_rel": g2.relative_path,
                "g1_sha": g1.sha256, "g2_sha": g2.sha256,
                "bundle_sha": bundle.canonical_payload_sha256,
                "bundle_v2_sha": bundle_v2.canonical_payload_sha256,
                "authority_sha": authority.sha256,
            })
        snap["world"] = {k: str(v) for k, v in world.items()}

        # ── ① Property 7：十意图同解 ────────────────────────────────────
        async with Session() as s:
            svc = CanonicalResolutionService(s, artifacts)
            for intent in ResolutionIntent:
                pol_frozen = intent.value in ("retry", "rollback", "history", "evidence")
                try:
                    res = await svc.resolve(
                        intent=intent,
                        project_id=project, wp_id=wp, entry_id=ENTRY,
                        representation_id=world["rep2"] if pol_frozen else None,
                    )
                    snap["intents"][intent.value] = {
                        "ok": True,
                        "identity": [str(x) for x in res.identity_tuple()],
                        "artifact_path": str(res.artifact_path),
                        "artifact_sha256": res.artifact_sha256,
                        "bundle_sha256": res.bundle.bundle_sha256,
                        "authority_model": res.bundle.authority_model.value,
                        "typed_slots": [list(t) for t in res.bundle.typed_slot_inventory],
                        "generation": res.representation_generation,
                        "revision": res.content_revision,
                    }
                except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言
                    snap["intents"][intent.value] = {"ok": False, "error": _err(exc)}

            # 历史意图不给 representation_id ⇒ 必须 HistoricalResolutionError
            for intent in ("retry", "rollback", "history", "evidence"):
                try:
                    await svc.resolve(
                        intent=intent, project_id=project, wp_id=wp, entry_id=ENTRY
                    )
                    snap["frozen_vs_current"][f"{intent}_without_frozen"] = "NO ERROR"
                except HistoricalResolutionError as exc:
                    snap["frozen_vs_current"][f"{intent}_without_frozen"] = _err(exc)
                except Exception as exc:  # noqa: BLE001
                    snap["frozen_vs_current"][f"{intent}_without_frozen"] = (
                        f"WRONG-TYPE {_err(exc)}"
                    )

            # 历史 retry 读 gen-1 ⇒ 仍是 bundle v1（当前 pointer 已在 gen-2/bundle v2）
            try:
                old = await svc.resolve(
                    intent="retry", project_id=project, wp_id=wp, entry_id=ENTRY,
                    representation_id=world["rep1"],
                )
                cur = await svc.resolve(
                    intent="config", project_id=project, wp_id=wp, entry_id=ENTRY
                )
                snap["frozen_vs_current"]["history_keeps_old_bundle"] = {
                    "old_bundle": old.bundle.bundle_sha256,
                    "cur_bundle": cur.bundle.bundle_sha256,
                    "old_generation": old.representation_generation,
                    "cur_generation": cur.representation_generation,
                    "old_revision": old.content_revision,
                    "cur_revision": cur.content_revision,
                    "old_contract_digest": old.bundle.slots[BundleSlot.contract].slot_digest,
                    "cur_contract_digest": cur.bundle.slots[BundleSlot.contract].slot_digest,
                }
            except Exception as exc:  # noqa: BLE001
                snap["errors"].append(f"history_keeps_old_bundle: {_err(exc)}")

            # 跨 scope：用另一个 wp 的 id 请求同一 representation ⇒ 必须拒绝
            for label, kwargs in (
                ("cross_wp", {"wp_id": other_wp, "entry_id": ENTRY}),
                ("cross_entry", {"wp_id": wp, "entry_id": OTHER_ENTRY}),
            ):
                try:
                    await svc.resolve(
                        intent="history", project_id=project,
                        representation_id=world["rep2"], **kwargs,
                    )
                    snap["path_safety"][label] = "NO ERROR"
                except Exception as exc:  # noqa: BLE001
                    snap["path_safety"][label] = _err(exc)

        # ── ② Property 28：unapproved bundle / digest 漂移 fail closed ────
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            svc = CanonicalResolutionService(s, artifacts)
            try:
                await svc.load_bundle_snapshot(world["bundle_unapproved"])
                snap["unapproved_bundle"]["load"] = "NO ERROR"
            except BundleIntegrityError as exc:
                snap["unapproved_bundle"]["load"] = _err(exc)
            except Exception as exc:  # noqa: BLE001
                snap["unapproved_bundle"]["load"] = f"WRONG-TYPE {_err(exc)}"

            # representation 引用 unapproved bundle ⇒ repository/DB 双层拒绝
            try:
                await repo.create_representation(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    content_version_id=world["cv0"], generation=99,
                    document_type="xlsx",
                    artifact_id=world["art_g1"], artifact_sha256=world["g1_sha"],
                    definition_bundle_id=world["bundle_unapproved"],
                    authority_model_definition_id=world["authority"],
                    adapter_id="task12.adapter", adapter_build_digest=_d("adapter"),
                    structure_hash=_d("s"), identity_inventory_sha256=_d("i"),
                    reason="content_commit",
                )
                snap["unapproved_bundle"]["create_representation"] = "NO ERROR"
            except Exception as exc:  # noqa: BLE001
                snap["unapproved_bundle"]["create_representation"] = _err(exc)
            await s.rollback()

        # 「approved 后不可重组」由 V151 trigger 承担 —— 尝试 UPDATE 必须被 DB 拒绝。
        # 🔴 这条与「服务层重算 digest」是**两道不同的门**，各测一次：
        #    * DB 门拦「已 approved 的 row 被改」；
        #    * 服务层门拦「插入时 digest 就与 slots 不符」（`create_definition_bundle`
        #      的 `canonical_payload_sha256` 是入参，调用方可以传错）。
        #    只测一道时，把另一道删掉不会红。
        async with Session() as s:
            svc = CanonicalResolutionService(s, artifacts)
            for label, sql, params in (
                (
                    "db_blocks_slot_update",
                    "UPDATE working_paper_sync_definition_bundle "
                    "SET contract_slot_digest = :d WHERE id = :b",
                    {"d": _d("tampered"), "b": str(world["bundle"])},
                ),
                (
                    "db_blocks_representation_bundle_digest_update",
                    "UPDATE working_paper_content_representation "
                    "SET definition_bundle_sha256 = :d WHERE id = :r",
                    {"d": _d("drifted"), "r": str(world["rep2"])},
                ),
            ):
                try:
                    await s.execute(sa.text(sql), params)
                    await s.flush()
                    snap["digest_drift"][label] = "NO ERROR"
                except Exception as exc:  # noqa: BLE001
                    snap["digest_drift"][label] = _err(exc)
                await s.rollback()

        # 服务层门：新建一个「digest 与 slots 不符」的 bundle（插入时就错）
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            svc = CanonicalResolutionService(s, artifacts)
            try:
                bad_blob = artifacts.publish_definition_blob(
                    project_id=project, wp_id=wp, definition_kind="bundle",
                    payload=b'{"k":"bad-digest"}',
                )
                bad_row = await repo.register_artifact(
                    project_id=project, wp_id=wp,
                    kind=ArtifactKind.definition, state=ArtifactState.published,
                    relative_path=bad_blob.relative_path, sha256=bad_blob.sha256,
                    size_bytes=bad_blob.size_bytes, document_type=bad_blob.document_type,
                    retention_class="definition",
                )
                authority_row = (
                    await s.execute(
                        sa.text(
                            "SELECT id, sha256 FROM working_paper_sync_definition_artifact "
                            "WHERE id = :a"
                        ),
                        {"a": str(world["authority"])},
                    )
                ).one()
                bad_bundle = await repo.create_definition_bundle(
                    authority_model_definition_id=uuid.UUID(str(authority_row[0])),
                    slots={
                        BundleSlot.template: BundleSlotSpec(
                            BundleSlot.template, "definition",
                            f"definition:{world['tpl']}", _d("task12-template"),
                        ),
                        BundleSlot.instrumentation: BundleSlotSpec(
                            BundleSlot.instrumentation, "definition",
                            f"definition:{world['instr']}", _d("task12-instrumentation"),
                        ),
                        BundleSlot.contract: BundleSlotSpec(
                            BundleSlot.contract, "definition",
                            f"definition:{world['contract2']}", _d("task12-contract-v2"),
                        ),
                    },
                    canonical_payload_artifact_id=bad_row.id,
                    # 🔴 故意与 typed slots 不一致的 canonical digest
                    canonical_payload_sha256=_d("not-the-canonical-digest"),
                )
                await s.flush()
                try:
                    await svc.load_bundle_snapshot(bad_bundle.id)
                    snap["digest_drift"]["service_rejects_insert_time_digest"] = "NO ERROR"
                except BundleIntegrityError as exc:
                    snap["digest_drift"]["service_rejects_insert_time_digest"] = _err(exc)
                except Exception as exc:  # noqa: BLE001
                    snap["digest_drift"]["service_rejects_insert_time_digest"] = (
                        f"WRONG-TYPE {_err(exc)}"
                    )
            except Exception as exc:  # noqa: BLE001
                snap["errors"].append(f"insert_time_digest_setup: {_err(exc)}")
            await s.rollback()

        # contract child 被 retire ⇒ bundle 立即不可用（Property 28）
        async with Session() as s:
            svc = CanonicalResolutionService(s, artifacts)
            try:
                await s.execute(
                    sa.text(
                        "UPDATE working_paper_sync_definition_artifact "
                        "SET state = 'retired' WHERE id = :c"
                    ),
                    {"c": str(world["contract"])},
                )
                await s.flush()
                try:
                    await svc.load_bundle_snapshot(world["bundle"])
                    snap["digest_drift"]["retired_contract_child"] = "NO ERROR"
                except BundleIntegrityError as exc:
                    snap["digest_drift"]["retired_contract_child"] = _err(exc)
                except Exception as exc:  # noqa: BLE001
                    snap["digest_drift"]["retired_contract_child"] = (
                        f"WRONG-TYPE {_err(exc)}"
                    )
            except Exception as exc:  # noqa: BLE001
                # DB 也可能直接禁止 retire（那同样是 fail closed 的证据）
                snap["digest_drift"]["retired_contract_child"] = f"DB-BLOCKED {_err(exc)}"
            await s.rollback()

        # ── ③ candidate 隔离与 finalize gate ────────────────────────────
        cand_pub = artifacts.stage_upgrade_candidate(
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=_xlsx("cand"),
                document_type="xlsx",
            ),
            entry_id=ENTRY,
            equivalence_report=json.dumps({"equivalent": True}).encode(),
        )
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            svc = CanonicalResolutionService(s, artifacts)
            art_cand = await repo.register_artifact(
                project_id=project, wp_id=wp,
                kind=ArtifactKind.upgrade_candidate, state=ArtifactState.candidate,
                relative_path=cand_pub.relative_path, sha256=cand_pub.sha256,
                size_bytes=cand_pub.size_bytes, document_type="xlsx",
                retention_class="candidate",
            )
            cand = await repo.create_upgrade_candidate(
                project_id=project, wp_id=wp, entry_id=ENTRY,
                content_version_id=world["cv0"],
                source_representation_id=world["rep2"],
                staged_artifact_id=art_cand.id,
                staged_artifact_sha256=art_cand.sha256,
                template_definition_id=world["tpl"],
                instrumentation_definition_id=world["instr"],
                state=CandidateState.awaiting_contract,
            )
            await s.commit()
            # 🔴 先把主键取出来存成裸值：下面会 `expire_all()`，之后再访问 ORM 属性
            #    会触发同步 lazy refresh ⇒ asyncpg 下必抛 MissingGreenlet。
            cand_id = cand.id
            snap["candidate"]["id"] = str(cand_id)

            # a) candidate id 当 representation_id 传进 resolver ⇒ 专属异常
            try:
                await svc.resolve(
                    intent="history", project_id=project, wp_id=wp, entry_id=ENTRY,
                    representation_id=cand_id,
                )
                snap["candidate"]["resolve_by_candidate_id"] = "NO ERROR"
            except CandidateNotResolvableError as exc:
                snap["candidate"]["resolve_by_candidate_id"] = _err(exc)
            except Exception as exc:  # noqa: BLE001
                snap["candidate"]["resolve_by_candidate_id"] = f"WRONG-TYPE {_err(exc)}"

            # b) 恒抛的「candidate 不可消费」禁令
            for intent in ("config", "materialize", "evidence"):
                try:
                    await svc.assert_candidate_not_consumable(
                        candidate_id=cand_id, intent=intent
                    )
                    snap["candidate"][f"not_consumable_{intent}"] = "NO ERROR"
                except CandidateNotResolvableError as exc:
                    snap["candidate"][f"not_consumable_{intent}"] = _err(exc)

            # c) 缺 approved contract/bundle ⇒ 不可 finalize
            try:
                await svc.assert_candidate_finalizable(cand_id)
                snap["candidate"]["finalizable_without_contract"] = "NO ERROR"
            except CandidateNotFinalizableError as exc:
                snap["candidate"]["finalizable_without_contract"] = _err(exc)
            except Exception as exc:  # noqa: BLE001
                snap["candidate"]["finalizable_without_contract"] = (
                    f"WRONG-TYPE {_err(exc)}"
                )

            # d) 补 approved contract + bundle 但缺等值报告 ⇒ 仍不可 finalize
            await s.execute(
                sa.text(
                    "UPDATE working_paper_representation_upgrade_candidate SET "
                    "target_contract_definition_id = :c, target_definition_bundle_id = :b, "
                    "state = 'ready' WHERE id = :i"
                ),
                {"c": str(world["contract"]), "b": str(world["bundle"]),
                 "i": str(cand_id)},
            )
            await s.flush()
            # 🔴 裸 SQL UPDATE 不会刷新 session 的 identity map：不 expire 的话
            #    `assert_candidate_finalizable` 里的 select 会拿回**改之前**的 ORM 对象，
            #    于是「补了 contract 仍报缺 contract」——判据看似红了但原因是错的
            #    （典型 WRONG-TEST）。
            s.expire_all()
            try:
                await svc.assert_candidate_finalizable(cand_id)
                snap["candidate"]["finalizable_without_equivalence"] = "NO ERROR"
            except CandidateNotFinalizableError as exc:
                snap["candidate"]["finalizable_without_equivalence"] = _err(exc)
            except Exception as exc:  # noqa: BLE001
                snap["candidate"]["finalizable_without_equivalence"] = (
                    f"WRONG-TYPE {_err(exc)}"
                )

            # e) 补齐等值报告 ⇒ 通过（证明门不是恒红的死路）
            await s.execute(
                sa.text(
                    "UPDATE working_paper_representation_upgrade_candidate SET "
                    "visible_equivalence_report_sha256 = :e WHERE id = :i"
                ),
                {"e": _d("equivalence"), "i": str(cand_id)},
            )
            await s.flush()
            s.expire_all()
            try:
                ok = await svc.assert_candidate_finalizable(cand_id)
                snap["candidate"]["finalizable_when_ready"] = str(ok.state)
            except Exception as exc:  # noqa: BLE001
                snap["candidate"]["finalizable_when_ready"] = f"UNEXPECTED {_err(exc)}"

            # f) bundle 的 contract child 与 candidate 声明不一致 ⇒ compatibility 拒绝
            await s.execute(
                sa.text(
                    "UPDATE working_paper_representation_upgrade_candidate SET "
                    "target_contract_definition_id = :c WHERE id = :i"
                ),
                {"c": str(world["contract2"]), "i": str(cand_id)},
            )
            await s.flush()
            s.expire_all()
            try:
                await svc.assert_candidate_finalizable(cand_id)
                snap["candidate"]["contract_child_mismatch"] = "NO ERROR"
            except CandidateNotFinalizableError as exc:
                snap["candidate"]["contract_child_mismatch"] = _err(exc)
            except Exception as exc:  # noqa: BLE001
                snap["candidate"]["contract_child_mismatch"] = f"WRONG-TYPE {_err(exc)}"
            await s.rollback()

            # g) entry pointer 指向 candidate ⇒ DB FK/trigger 拒绝
            try:
                await s.execute(
                    sa.text(
                        "UPDATE working_paper_sync_entry_state "
                        "SET current_representation_id = :c WHERE wp_id = :w"
                    ),
                    {"c": str(cand_id), "w": str(wp)},
                )
                await s.flush()
                snap["pointer"]["points_to_candidate"] = "NO ERROR"
            except Exception as exc:  # noqa: BLE001
                snap["pointer"]["points_to_candidate"] = _err(exc)
            await s.rollback()

        # ── ③bis finalize 只增不改（Task 12 第 3 条后半句）────────────────
        #
        # 任务书原文：「finalize 只创建新的 immutable representation，不改旧 row 或
        # business revision」。前面 (a)~(g) 只覆盖前半句（candidate 不可解析/不可
        # current/前置不齐不可 finalize），**成功 finalize 之后的世界**没有任何判据 ——
        # 于是「finalize 顺手把 current pointer 挪了 / 把 content_revision 推了一格」
        # 这类回归无声。此处补齐：把 candidate 补成 ready、真发布 gen-4 artifact、
        # 真建 gen-4 representation、真跑 `repository.finalize_candidate()`，
        # 前后各拍一次快照逐项比对。
        #
        # 🔴 generation 刻意用 4 而不是 3：下面第 ④ 段的 end-to-end 反例会建
        #    generation=3 的越界 representation。若这里占了 3，那段会先撞
        #    `uq_wpcr_generation` 唯一键，于是 Property 42 的端到端判据被一个
        #    「唯一键冲突」冒充通过（WRONG-TEST）。
        g4 = artifacts.publish_representation(
            entry_id=ENTRY, generation=4,
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=_xlsx("g4"), document_type="xlsx"
            ),
        )
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            # 把 committed candidate 补齐成 ready（contract + bundle + 等值报告）
            await s.execute(
                sa.text(
                    "UPDATE working_paper_representation_upgrade_candidate SET "
                    "target_contract_definition_id = :c, target_definition_bundle_id = :b, "
                    "visible_equivalence_report_sha256 = :e, state = 'ready' WHERE id = :i"
                ),
                {"c": str(world["contract"]), "b": str(world["bundle"]),
                 "e": _d("equivalence"), "i": str(cand_id)},
            )
            await s.commit()

        async def _finalize_snapshot(sess) -> dict[str, Any]:
            """业务侧「不该被 finalize 碰到」的三样东西 + 旧 representation 全列。"""
            wp_row = (
                await sess.execute(
                    sa.text(
                        "SELECT content_revision, current_content_version_id::text, "
                        "file_version FROM working_paper WHERE id = :w"
                    ),
                    {"w": str(wp)},
                )
            ).one()
            pointer = (
                await sess.execute(
                    sa.text(
                        "SELECT current_representation_id::text, representation_generation "
                        "FROM working_paper_sync_entry_state "
                        "WHERE wp_id = :w AND entry_id = :e"
                    ),
                    {"w": str(wp), "e": ENTRY},
                )
            ).one()
            old_rep = (
                await sess.execute(
                    sa.text(
                        "SELECT to_jsonb(t)::text FROM "
                        "working_paper_content_representation t WHERE id = :r"
                    ),
                    {"r": str(world["rep2"])},
                )
            ).scalar_one()
            count = (
                await sess.execute(
                    sa.text(
                        "SELECT count(*) FROM working_paper_content_representation "
                        "WHERE wp_id = :w AND entry_id = :e"
                    ),
                    {"w": str(wp), "e": ENTRY},
                )
            ).scalar_one()
            return {
                "content_revision": int(wp_row[0]),
                "current_content_version_id": wp_row[1],
                "file_version": int(wp_row[2]),
                "pointer_representation_id": pointer[0],
                "pointer_generation": int(pointer[1]),
                "old_representation_row": old_rep,
                "representation_count": int(count),
            }

        async with Session() as s:
            snap["finalize"]["before"] = await _finalize_snapshot(s)

        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            try:
                art_g4 = await repo.register_artifact(
                    project_id=project, wp_id=wp,
                    kind=ArtifactKind.canonical, state=ArtifactState.published,
                    relative_path=g4.relative_path, sha256=g4.sha256,
                    size_bytes=g4.size_bytes, document_type="xlsx",
                )
                rep4 = await repo.create_representation(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    content_version_id=world["cv0"], generation=4,
                    document_type="xlsx",
                    artifact_id=art_g4.id, artifact_sha256=art_g4.sha256,
                    definition_bundle_id=world["bundle"],
                    authority_model_definition_id=world["authority"],
                    adapter_id="task12.adapter", adapter_build_digest=_d("adapter"),
                    structure_hash=_d("structure-4"),
                    identity_inventory_sha256=_d("identity-4"),
                    reason="definition_upgrade",
                    parent_representation_id=world["rep2"],
                )
                done = await repo.finalize_candidate(
                    candidate_id=cand_id, finalized_representation_id=rep4.id
                )
                finalized_state = str(done.state)
                await s.commit()
                snap["finalize"]["error"] = None
                snap["finalize"]["new_representation_id"] = str(rep4.id)
                snap["finalize"]["candidate_state"] = finalized_state
            except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言
                await s.rollback()
                snap["finalize"]["error"] = _err(exc)

        async with Session() as s:
            snap["finalize"]["after"] = await _finalize_snapshot(s)
            row = (
                await s.execute(
                    sa.text(
                        "SELECT state, finalized_representation_id::text, "
                        "(finalized_at IS NOT NULL) FROM "
                        "working_paper_representation_upgrade_candidate WHERE id = :i"
                    ),
                    {"i": str(cand_id)},
                )
            ).one()
            snap["finalize"]["candidate_row"] = {
                "state": row[0], "finalized_representation_id": row[1],
                "has_finalized_at": bool(row[2]),
            }
            # finalize 之后历史读取仍必须固定 gen-2 的 bundle（frozen 语义不被新
            # generation 影响）—— 与 `history_keeps_old_bundle` 是**两个时点**。
            svc = CanonicalResolutionService(s, artifacts)
            try:
                old = await svc.resolve(
                    intent="evidence", project_id=project, wp_id=wp, entry_id=ENTRY,
                    representation_id=world["rep2"],
                )
                snap["finalize"]["post_finalize_history"] = {
                    "generation": old.representation_generation,
                    "bundle": old.bundle.bundle_sha256,
                    "artifact_sha256": old.artifact_sha256,
                }
            except Exception as exc:  # noqa: BLE001
                snap["finalize"]["post_finalize_history"] = {"error": _err(exc)}

        # ── ④ Property 42：DB 侧路径安全 ────────────────────────────────
        #
        # 🔴 不能用 `UPDATE working_paper_artifact SET relative_path` 制造反例：
        #    V151 的 `working_paper_artifact` 内容身份列（kind/sha256/relative_path/
        #    size/scope）**不可变**，UPDATE 直接被 trigger 拒绝。那道拒绝本身是
        #    Property 5 的证据，但它会遮蔽 Property 42 的 resolver 侧判据。
        #    故这里分两支：
        #      a) 直接对 resolver 的文件门喂越界 relative_path（与 `resolve()` 第 ⑥ 步
        #         同一代码路径，无需改库）；
        #      b) 端到端：新建带越界路径的 artifact 行 + 新 representation + 切 pointer。
        #         若 DB 在插入时就拒绝，同样记为 fail-closed 证据。
        for label, bad_path in (
            ("traversal", "../../../etc/passwd"),
            ("absolute_outside", str(Path(tempfile.gettempdir()) / "escape.xlsx")),
            ("empty", "   "),
        ):
            try:
                artifacts.resolve_published_artifact(
                    project_id=project, kind=ArtifactKind.canonical,
                    state=ArtifactState.published, relative_path=bad_path,
                )
                snap["path_safety"][label] = "NO ERROR"
            except Exception as exc:  # noqa: BLE001
                snap["path_safety"][label] = _err(exc)

        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            svc = CanonicalResolutionService(s, artifacts)
            try:
                bad_art = await repo.register_artifact(
                    project_id=project, wp_id=wp,
                    kind=ArtifactKind.canonical, state=ArtifactState.published,
                    relative_path="../../../etc/passwd.xlsx",
                    sha256=_d("escape"), size_bytes=1, document_type="xlsx",
                )
                bad_rep = await repo.create_representation(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    content_version_id=world["cv0"], generation=3,
                    document_type="xlsx",
                    artifact_id=bad_art.id, artifact_sha256=bad_art.sha256,
                    definition_bundle_id=world["bundle"],
                    authority_model_definition_id=world["authority"],
                    adapter_id="task12.adapter", adapter_build_digest=_d("adapter"),
                    structure_hash=_d("s3"), identity_inventory_sha256=_d("i3"),
                    reason="content_commit",
                )
                await repo.set_entry_pointer(
                    wp_id=wp, entry_id=ENTRY, representation_id=bad_rep.id, generation=3
                )
                await s.flush()
                try:
                    await svc.resolve(
                        intent="config", project_id=project, wp_id=wp, entry_id=ENTRY
                    )
                    snap["path_safety"]["end_to_end_traversal"] = "NO ERROR"
                except Exception as exc:  # noqa: BLE001
                    snap["path_safety"]["end_to_end_traversal"] = _err(exc)
            except Exception as exc:  # noqa: BLE001
                snap["path_safety"]["end_to_end_traversal"] = f"DB-BLOCKED {_err(exc)}"
            await s.rollback()

        async with Session() as s:
            svc = CanonicalResolutionService(s, artifacts)
            # 跨 project 复用同一 relative_path
            other_project = uuid.uuid4()
            try:
                await svc.resolve(
                    intent="config", project_id=other_project, wp_id=wp, entry_id=ENTRY
                )
                snap["path_safety"]["cross_project"] = "NO ERROR"
            except Exception as exc:  # noqa: BLE001
                snap["path_safety"]["cross_project"] = _err(exc)

            # 文档类型不符（Property 41 的 DB 侧）
            try:
                await svc.resolve(
                    intent="config", project_id=project, wp_id=wp, entry_id=ENTRY,
                    expected_document_type="docx",
                )
                snap["document_type"]["docx_on_xlsx"] = "NO ERROR"
            except DocumentTypeMismatchError as exc:
                snap["document_type"]["docx_on_xlsx"] = _err(exc)
            except Exception as exc:  # noqa: BLE001
                snap["document_type"]["docx_on_xlsx"] = f"WRONG-TYPE {_err(exc)}"

            # pointer 指向的文件被删 ⇒ 必须可见报错（不返回不存在的 Path）
            Path(base_root / world["g2_rel"]).unlink()
            try:
                await svc.resolve(
                    intent="download", project_id=project, wp_id=wp, entry_id=ENTRY
                )
                snap["path_safety"]["missing_file"] = "NO ERROR"
            except Exception as exc:  # noqa: BLE001
                snap["path_safety"]["missing_file"] = _err(exc)

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
# 守卫
# ═══════════════════════════════════════════════════════════════════════════


class TestHarness:
    def test_real_postgres(self, snap: dict[str, Any]):
        assert "PostgreSQL" in (snap["server_version"] or "")

    def test_migration_applied_cleanly(self, snap: dict[str, Any]):
        assert snap["apply_errors"] == []

    def test_no_harness_errors(self, snap: dict[str, Any]):
        """🔴 采集内部异常必须为空：fail-open 会让「静默取空」冒充「判据通过」。"""
        assert snap["errors"] == [], f"采集内部异常: {snap['errors']}"

    def test_scratch_schema_is_isolated(self, snap: dict[str, Any]):
        assert snap["schema"].startswith(_SCHEMA_PREFIX)


class TestProperty7AllIntentsResolveIdentically:
    """十个意图对同一 (content version, entry, generation) 返回逐字段相同的结果。"""

    def test_every_intent_resolved(self, snap: dict[str, Any]):
        failed = {
            k: v.get("error") for k, v in snap["intents"].items() if not v["ok"]
        }
        assert not failed, f"以下意图解析失败: {failed}"

    def test_all_ten_intents_present(self, snap: dict[str, Any]):
        assert set(snap["intents"]) == {
            "config", "download", "callback", "materialize", "extract",
            "rematerialize", "retry", "rollback", "history", "evidence",
        }

    def test_identity_tuples_are_all_equal(self, snap: dict[str, Any]):
        """🔴 Property 7 的核心断言：identity 逐字段相等（不含 intent 自身）。"""
        identities = {k: tuple(v["identity"]) for k, v in snap["intents"].items()}
        distinct = set(identities.values())
        assert len(distinct) == 1, (
            "十意图解析出不同 identity ⇒ 全链未统一。逐项差异: "
            + json.dumps(
                {k: v for k, v in identities.items()},
                ensure_ascii=False, indent=1,
            )[:2000]
        )

    def test_all_intents_share_artifact_and_bundle(self, snap: dict[str, Any]):
        shas = {v["artifact_sha256"] for v in snap["intents"].values()}
        bundles = {v["bundle_sha256"] for v in snap["intents"].values()}
        paths = {v["artifact_path"] for v in snap["intents"].values()}
        assert len(shas) == 1, f"artifact sha 不一致: {shas}"
        assert len(bundles) == 1, f"bundle digest 不一致: {bundles}"
        assert len(paths) == 1, f"artifact path 不一致: {paths}"

    def test_bundle_is_non_empty_and_typed(self, snap: dict[str, Any]):
        for intent, v in snap["intents"].items():
            slots = v["typed_slots"]
            assert len(slots) == 3, f"{intent}: typed slot 数应为 3，实得 {len(slots)}"
            for slot, slot_type, digest in slots:
                assert slot_type, f"{intent}/{slot}: slot type 为空"
                assert digest and digest != "0" * 64, f"{intent}/{slot}: digest 非法"
            assert v["authority_model"] in (
                "projection_contract", "custom_authoritative_ooxml",
                "opaque_single_onlyoffice",
            )


class TestHistoricalReadsUseFrozenBundle:
    """Requirement 2.10：历史读取不得按当前 alias / 当前 pointer 重组 bundle。"""

    def test_historical_intents_reject_missing_frozen_identity(self, snap: dict[str, Any]):
        """🔴 断言必须落到 **frozen identity** 这条判据的消息上。

        历史四意图同时满足 `requires_frozen_identity=True` 与
        `allows_current_pointer=False`，两条检查抛**同一异常类型**。只断言类型时，
        把 frozen 门短路掉之后第二条会顶上来把它遮蔽（变异 M34 实测 GREEN）。
        """
        for intent in ("retry", "rollback", "history", "evidence"):
            got = snap["frozen_vs_current"][f"{intent}_without_frozen"]
            assert got.startswith("HistoricalResolutionError"), (
                f"{intent} 未给 frozen identity 时应抛 HistoricalResolutionError，实得 {got}"
            )
            assert "frozen `representation_id`" in got, (
                f"{intent} 的拒绝理由应是「必须给 frozen representation_id」，"
                f"实际命中的是另一条判据: {got}"
            )

    def test_old_generation_keeps_old_bundle(self, snap: dict[str, Any]):
        got = snap["frozen_vs_current"]["history_keeps_old_bundle"]
        assert got["old_generation"] == 1 and got["cur_generation"] == 2
        assert got["old_bundle"] != got["cur_bundle"], (
            "gen-1 与 gen-2 的 bundle digest 必须不同（否则测不出 frozen 语义）"
        )
        assert got["old_contract_digest"] != got["cur_contract_digest"], (
            "🔴 历史 retry 读到了**当前** contract child ⇒ 按 alias 重组了 bundle"
        )

    def test_pure_definition_upgrade_keeps_revision(self, snap: dict[str, Any]):
        got = snap["frozen_vs_current"]["history_keeps_old_bundle"]
        assert got["old_revision"] == got["cur_revision"] == 0, (
            "纯 representation/definition 升级不得推进 content revision"
        )


class TestProperty28FailClosedOnDrift:
    """definition/bundle 任一受管 identity 漂移必须在写入/读取前失败。"""

    def test_unapproved_bundle_is_not_loadable(self, snap: dict[str, Any]):
        got = snap["unapproved_bundle"]["load"]
        assert got.startswith("BundleIntegrityError"), got
        assert "approved" in got

    def test_unapproved_bundle_cannot_back_representation(self, snap: dict[str, Any]):
        got = snap["unapproved_bundle"]["create_representation"]
        assert got != "NO ERROR", "unapproved bundle 竟能创建 representation"

    def test_db_blocks_post_approval_slot_update(self, snap: dict[str, Any]):
        """第一道门：approved bundle 的 typed slot 不可被 UPDATE（V151 trigger）。"""
        got = snap["digest_drift"]["db_blocks_slot_update"]
        assert got != "NO ERROR", "approved bundle 的 slot 竟可被改（DB 门失效）"
        assert "IntegrityError" in got or "不可变" in got, got

    def test_db_blocks_representation_bundle_digest_update(self, snap: dict[str, Any]):
        got = snap["digest_drift"]["db_blocks_representation_bundle_digest_update"]
        assert got != "NO ERROR", "representation 的 bundle digest 竟可被改"

    def test_service_rejects_insert_time_digest_mismatch(self, snap: dict[str, Any]):
        """第二道门：插入时 digest 与 typed slots 不符 ⇒ resolver 侧重算后拒绝。

        🔴 与上面的 DB 门必须两条都在：DB trigger 只拦「approved 后被改」，
        `create_definition_bundle` 的 `canonical_payload_sha256` 是入参，
        调用方在**创建时**就能传一个与 slots 不符的 digest。
        """
        got = snap["digest_drift"]["service_rejects_insert_time_digest"]
        assert got.startswith("BundleIntegrityError"), got
        assert "重算" in got or "recomputed" in got, got

    def test_retired_contract_child_invalidates_bundle(self, snap: dict[str, Any]):
        got = snap["digest_drift"]["retired_contract_child"]
        assert got != "NO ERROR", "contract child 被 retire 后 bundle 仍可用"
        assert got.startswith("BundleIntegrityError") or got.startswith("DB-BLOCKED"), got


class TestCandidateIsolation:
    """candidate 永不可解析、永不可 current、finalize 前置齐了才放行。"""

    def test_candidate_id_as_representation_is_rejected(self, snap: dict[str, Any]):
        got = snap["candidate"]["resolve_by_candidate_id"]
        assert got.startswith("CandidateNotResolvableError"), got

    def test_candidate_not_consumable_for_every_intent(self, snap: dict[str, Any]):
        for intent in ("config", "materialize", "evidence"):
            got = snap["candidate"][f"not_consumable_{intent}"]
            assert got.startswith("CandidateNotResolvableError"), f"{intent}: {got}"

    def test_finalize_requires_approved_contract(self, snap: dict[str, Any]):
        got = snap["candidate"]["finalizable_without_contract"]
        assert got.startswith("CandidateNotFinalizableError"), got
        assert "contract" in got

    def test_finalize_requires_equivalence_report(self, snap: dict[str, Any]):
        """🔴 断言必须落到**等值报告**这条原因上。

        只断言异常类型时，「contract 缺失」分支会把这条判据遮蔽成不可达
        （实测过：identity map 未 expire ⇒ 报的是缺 contract，测试照样绿）。
        """
        got = snap["candidate"]["finalizable_without_equivalence"]
        assert got.startswith("CandidateNotFinalizableError"), got
        assert "visible-equivalence" in got or "等值" in got, (
            f"应因缺等值报告被拒，实际原因是: {got}"
        )

    def test_finalize_passes_when_all_prerequisites_present(self, snap: dict[str, Any]):
        """🔴 反向：门必须不是恒红的死路，否则「前置齐了」这条判据不可达。"""
        got = snap["candidate"]["finalizable_when_ready"]
        assert not got.startswith("UNEXPECTED"), got
        assert got == "ready"

    def test_contract_child_mismatch_is_rejected(self, snap: dict[str, Any]):
        got = snap["candidate"]["contract_child_mismatch"]
        assert got.startswith("CandidateNotFinalizableError"), got

    def test_entry_pointer_cannot_point_to_candidate(self, snap: dict[str, Any]):
        got = snap["pointer"]["points_to_candidate"]
        assert got != "NO ERROR", "entry pointer 竟能指向 candidate（DB 层门失效）"


class TestCandidateFinalizeIsAdditiveOnly:
    """Task 12 第 3 条后半句：finalize 只创建新 immutable representation。

    与 `TestCandidateIsolation` 分成两个类是刻意的：那个类测的是「不齐不放行」，
    本类测的是「放行之后什么都没被改动」。前者全绿也完全可能后者全红
    （finalize 里顺手挪 pointer / 推 revision）。
    """

    def test_finalize_succeeded(self, snap: dict[str, Any]):
        """前置：finalize 必须真的成功，否则下面的「不改」全是空转。"""
        assert snap["finalize"]["error"] is None, (
            f"finalize 失败，后续「只增不改」判据不可达: {snap['finalize']['error']}"
        )

    def test_finalize_creates_new_generation_and_binds_candidate(
        self, snap: dict[str, Any]
    ):
        """新增一行 representation，并把 candidate 绑到它上面（state=finalized）。"""
        before, after = snap["finalize"]["before"], snap["finalize"]["after"]
        assert after["representation_count"] == before["representation_count"] + 1, (
            "finalize 必须**新增**一个 representation generation，实测数量 "
            f"{before['representation_count']} → {after['representation_count']}"
        )
        row = snap["finalize"]["candidate_row"]
        assert row["state"] == "finalized", row
        assert row["finalized_representation_id"] == snap["finalize"].get(
            "new_representation_id"
        ), (
            "candidate 必须绑定**新建**的 representation，实得 "
            f"{row['finalized_representation_id']}"
        )
        assert row["has_finalized_at"] is True

    def test_finalize_is_additive_only(self, snap: dict[str, Any]):
        """🔴 business revision / current pointer / 旧 representation 全列都不得变。

        `content_revision` 与 pointer 分开断言：只测 revision 时，「finalize 顺手把
        current pointer 挪到新 generation」这类回归不红 —— 而 Requirement 9.10 明确
        「任何失败、未批准或缺 child 时 current pointer/revision 保持不变」，
        finalize 本身也只负责建行，切 pointer 是调用方的独立决定。
        """
        before, after = snap["finalize"]["before"], snap["finalize"]["after"]
        assert after["content_revision"] == before["content_revision"], (
            "纯 representation finalize 竟推进了 business content revision："
            f"{before['content_revision']} → {after['content_revision']}"
        )
        assert (
            after["current_content_version_id"] == before["current_content_version_id"]
        ), "finalize 竟改了 working_paper.current_content_version_id"
        assert after["file_version"] == before["file_version"], (
            "finalize 竟改了 legacy file_version"
        )
        assert (
            after["pointer_representation_id"] == before["pointer_representation_id"]
            and after["pointer_generation"] == before["pointer_generation"]
        ), (
            "finalize 竟移动了 entry current pointer："
            f"{before['pointer_representation_id']}/g{before['pointer_generation']} → "
            f"{after['pointer_representation_id']}/g{after['pointer_generation']}"
        )
        assert after["old_representation_row"] == before["old_representation_row"], (
            "旧 representation row 被 finalize 改动（immutable 承诺被破）"
        )

    def test_history_still_frozen_after_finalize(self, snap: dict[str, Any]):
        """新 generation 上线后，历史 evidence 读取仍固定旧 generation 的 bundle。"""
        got = snap["finalize"]["post_finalize_history"]
        assert "error" not in got, got
        assert got["generation"] == 2, got
        assert got["bundle"] == snap["world"]["bundle_v2_sha"], (
            "finalize 之后历史读取的 bundle 变了 ⇒ 历史被新 generation 重组"
        )
        assert got["artifact_sha256"] == snap["world"]["g2_sha"], got


class TestProperty42DbSidePathSafety:
    """artifact 的 relative_path 越界 / 跨 project / 缺失文件全部 fail visible。"""

    def test_traversal_rejected(self, snap: dict[str, Any]):
        got = snap["path_safety"]["traversal"]
        assert "ArtifactPathError" in got or "outside" in got, got

    def test_absolute_outside_rejected(self, snap: dict[str, Any]):
        got = snap["path_safety"]["absolute_outside"]
        assert got != "NO ERROR", got

    def test_empty_relative_path_rejected(self, snap: dict[str, Any]):
        got = snap["path_safety"]["empty"]
        assert got != "NO ERROR", got
        assert "empty_relative_path" in got or "不得为空" in got, got

    def test_end_to_end_traversal_rejected(self, snap: dict[str, Any]):
        """端到端：即便 DB 里真存了一个越界 relative_path，resolver 也必须拒绝。"""
        got = snap["path_safety"]["end_to_end_traversal"]
        assert got != "NO ERROR", "带越界路径的 representation 竟被解析成功"
        assert got.startswith("ArtifactPathError") or got.startswith("DB-BLOCKED"), got

    def test_cross_project_rejected(self, snap: dict[str, Any]):
        got = snap["path_safety"]["cross_project"]
        assert got != "NO ERROR", "跨 project 解析同一 relative_path 竟成功"

    def test_cross_scope_rejected(self, snap: dict[str, Any]):
        for label in ("cross_wp", "cross_entry"):
            got = snap["path_safety"][label]
            assert got != "NO ERROR", f"{label} 竟成功（跨 scope 解析必须拒绝）"

    def test_missing_file_is_visible_error(self, snap: dict[str, Any]):
        """pointer 指向缺失 artifact 时必须报错，不得返回不存在的 Path。"""
        got = snap["path_safety"]["missing_file"]
        assert got != "NO ERROR", got
        assert "不存在" in got or "ArtifactPublishError" in got, got

    def test_document_type_mismatch_rejected(self, snap: dict[str, Any]):
        got = snap["document_type"]["docx_on_xlsx"]
        assert got.startswith("DocumentTypeMismatchError"), got


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
