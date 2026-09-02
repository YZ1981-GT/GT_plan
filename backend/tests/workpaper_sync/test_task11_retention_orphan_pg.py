# -*- coding: utf-8 -*-
"""Task 11 真实 PostgreSQL 守卫：Property 5（publish 后 DB rollback）、orphan 对账与
RetentionPolicy 的 dry-run / 二次引用复核 / 逐对象删除审计。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 11
Requirements: 2.4, 3.4, 5.9, 5.11, 9.6, 9.7, 10.7
Properties: P5 / P42（DB 侧）

═══ 为什么必须真库、必须真文件 ═══

Property 5 的全部内容都是「**跨介质**不一致」：DB `ROLLBACK` 不回滚已 publish 的文件，
DB `COMMIT` 也不创造文件。用 mock/SQLite/内存字典任一环节都会把唯一判据抹掉：

* 没有真 PostgreSQL ⇒ V151 的 CHECK/trigger（representation 不得引用
  candidate/incoming/orphan）不参与判定，「双层锁死」退化成单层；
* 没有真文件 ⇒ 「rollback 后文件仍在、hash 不变」无从观测，orphan 对账与
  RetentionPolicy 的删除也变成对字典的操作。

因此本文件同时开一个 scratch schema（`tmp_task11_ret_*`）与一个临时 base_root，
`CanonicalArtifactRepository` 真发布文件，`RetentionPolicyService` 真删文件。

═══ 隔离 ═══

schema 名随机、`search_path` 只含它（不含 public）、`projects/users/working_paper` 在
scratch 内建桩表，结束 `DROP SCHEMA CASCADE`。文件全在系统临时目录，绝不触碰真实
`storage/`。`DATABASE_URL` 非 PostgreSQL 时**直接失败不 skip**。

═══ 采集写法 ═══

全部场景由**一次 `asyncio.run`** 跑完并落进快照（module fixture）。不给每个测试各自
开 async —— 共享连接池会被污染，第二个测试起 `NoneType has no attribute send`。
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
_CONTRACT_PATH = _BACKEND / "data" / "workpaper_staged_artifact_boundary_contract.json"

if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_task11_ret_"
ENTRY = "g7.disclosure.listed"

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


def _xlsx(marker: str) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _XLSX_CT)
        zf.writestr("xl/workbook.xml", _WORKBOOK)
        zf.writestr("xl/marker.xml", f"<m>{marker}</m>".encode())
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# 采集
# ═══════════════════════════════════════════════════════════════════════════


async def _collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部跨介质场景
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.workpaper_sync_models import WorkpaperArtifact
    from app.services.workpaper_sync.artifacts import (
        CanonicalArtifactRepository,
        OrphanReconciler,
    )
    from app.services.workpaper_sync.models import ArtifactKind, ArtifactState, BundleSlot
    from app.services.workpaper_sync.models import BundleSlotSpec
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.retention import (
        RetentionPolicyService,
        load_retention_policy,
    )

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 11 的 Property 5 判据是「文件系统与 PostgreSQL 不是同一事务」，"
            "必须真实 PostgreSQL；当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task11_store_"))
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
        "rollback": {},
        "reconcile": {},
        "retention_before_grace": {},
        "retention_ttl_elapsed_grace_not": {},
        "retention_after_grace_dry_run": {},
        "retention_apply_reference_reappears": {},
        "retention_apply_deletes": {},
        "retention_reason_matrix": {},
        "reference_sources_execute": {},
        "audit": {},
        "flush_only": {},
        "resolver": {},
        "db_rejects_representation": {},
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
            except Exception as exc:  # noqa: BLE001 - 记录后继续，最终由守卫断言为空
                snap["apply_errors"].append(
                    {"index": idx, "error": f"{type(exc).__name__}: {exc}",
                     "head": stmt[:120]}
                )
        if snap["apply_errors"]:
            raise _HarnessError(f"V151 应用失败: {snap['apply_errors'][:3]}")

        project = uuid.uuid4()
        wp = uuid.uuid4()
        user = uuid.uuid4()
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{project}')")
            await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{user}')")
            await conn.exec_driver_sql(
                "INSERT INTO working_paper (id, project_id) VALUES "
                f"('{wp}', '{project}')"
            )

        artifacts = CanonicalArtifactRepository(base_root)
        policy = load_retention_policy()

        # ── 真实发布 gen-1 canonical 与 projection、definition blobs ──────
        g1 = artifacts.publish_representation(
            entry_id=ENTRY, generation=1,
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=_xlsx("g1"), document_type="xlsx"
            ),
        )
        proj = artifacts.publish_projection(
            revision=0,
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=b"projection-v0",
                document_type="json.gz",
            ),
        )
        blobs = {
            name: artifacts.publish_definition_blob(
                project_id=project, wp_id=wp, definition_kind=kind,
                payload=json.dumps({"k": name}).encode(),
            )
            for name, kind in (
                ("tpl", "template"), ("instr", "instrumentation"),
                ("contract", "contract"), ("authority", "authority_model"),
                ("bundle_payload", "bundle"),
            )
        }

        world: dict[str, Any] = {}
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            rows: dict[str, Any] = {}
            for name, pub in blobs.items():
                rows[name] = await repo.register_artifact(
                    project_id=project, wp_id=wp,
                    kind=ArtifactKind.definition, state=ArtifactState.published,
                    relative_path=pub.relative_path, sha256=pub.sha256,
                    size_bytes=pub.size_bytes, document_type=pub.document_type,
                    retention_class="definition",
                )
            art_g1 = await repo.register_artifact(
                project_id=project, wp_id=wp,
                kind=ArtifactKind.canonical, state=ArtifactState.published,
                relative_path=g1.relative_path, sha256=g1.sha256,
                size_bytes=g1.size_bytes, document_type="xlsx",
            )
            art_proj = await repo.register_artifact(
                project_id=project, wp_id=wp,
                kind=ArtifactKind.projection, state=ArtifactState.published,
                relative_path=proj.relative_path, sha256=proj.sha256,
                size_bytes=proj.size_bytes, document_type="json.gz",
            )
            tpl = await repo.create_definition_artifact(
                kind="template", logical_id="task11.template", semantic_version="1.0.0",
                blob_artifact_id=rows["tpl"].id, sha256=_d("tpl-def"),
                structure_hash=_d("tpl-structure"), source_commit="task11",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation", logical_id="task11.instr", semantic_version="1.0.0",
                blob_artifact_id=rows["instr"].id, sha256=_d("instr-def"),
                structure_hash=_d("instr-structure"), source_commit="task11",
            )
            contract = await repo.create_definition_artifact(
                kind="contract", logical_id="task11.contract", semantic_version="1.0.0",
                blob_artifact_id=rows["contract"].id, sha256=_d("contract-def"),
                source_commit="task11",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task11.authority",
                semantic_version="1.0.0", blob_artifact_id=rows["authority"].id,
                sha256=_d("authority-def"), authority_model_type="projection_contract",
                source_commit="task11",
            )
            bundle = await repo.create_definition_bundle(
                authority_model_definition_id=authority.id,
                slots={
                    BundleSlot.template: BundleSlotSpec(
                        BundleSlot.template, "definition", f"definition:{tpl.id}", tpl.sha256
                    ),
                    BundleSlot.instrumentation: BundleSlotSpec(
                        BundleSlot.instrumentation, "definition",
                        f"definition:{instr.id}", instr.sha256,
                    ),
                    BundleSlot.contract: BundleSlotSpec(
                        BundleSlot.contract, "definition",
                        f"definition:{contract.id}", contract.sha256,
                    ),
                },
                canonical_payload_artifact_id=rows["bundle_payload"].id,
                canonical_payload_sha256=_d("bundle-canonical"),
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
                adapter_id="task11.adapter", adapter_build_digest=_d("adapter"),
                structure_hash=_d("structure"),
                identity_inventory_sha256=_d("identity"),
                reason="content_commit",
            )
            await repo.set_entry_pointer(
                wp_id=wp, entry_id=ENTRY, representation_id=rep1.id, generation=1
            )
            await repo.set_current_content_version(wp, cv0.id)
            world.update(
                {"cv0": cv0, "rep1": rep1, "art_g1": art_g1, "bundle": bundle,
                 "authority": authority}
            )
            await s.commit()

        async def _counts() -> dict[str, int]:
            async with Session() as s:
                out = {}
                for tbl in (
                    "working_paper_artifact", "working_paper_content_version",
                    "working_paper_content_representation",
                    "working_paper_sync_entry_state",
                ):
                    out[tbl] = int(
                        (await s.execute(sa.text(f"SELECT count(*) FROM {tbl}"))).scalar_one()
                    )
                return out

        async def _pointer() -> dict[str, Any]:
            async with Session() as s:
                row = (
                    await s.execute(
                        sa.text(
                            "SELECT representation_generation, current_representation_id "
                            "FROM working_paper_sync_entry_state "
                            "WHERE wp_id = :wp AND entry_id = :e"
                        ),
                        {"wp": str(wp), "e": ENTRY},
                    )
                ).first()
                return {
                    "generation": int(row[0]) if row else None,
                    "representation_id": str(row[1]) if row else None,
                }

        baseline_counts = await _counts()
        baseline_pointer = await _pointer()

        # ══ 场景 A：Property 5 —— publish 之后注入 DB 失败 ═════════════════
        g2 = artifacts.publish_representation(
            entry_id=ENTRY, generation=2,
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=_xlsx("g2"), document_type="xlsx"
            ),
        )
        proj1 = artifacts.publish_projection(
            revision=1,
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=b"projection-v1",
                document_type="json.gz",
            ),
        )
        injected = None
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                art2 = await repo.register_artifact(
                    project_id=project, wp_id=wp,
                    kind=ArtifactKind.canonical, state=ArtifactState.published,
                    relative_path=g2.relative_path, sha256=g2.sha256,
                    size_bytes=g2.size_bytes, document_type="xlsx",
                )
                art_proj1 = await repo.register_artifact(
                    project_id=project, wp_id=wp,
                    kind=ArtifactKind.projection, state=ArtifactState.published,
                    relative_path=proj1.relative_path, sha256=proj1.sha256,
                    size_bytes=proj1.size_bytes, document_type="json.gz",
                )
                cv1 = await repo.create_content_version(
                    project_id=project, wp_id=wp, entry_id=ENTRY, revision=1,
                    source="onlyoffice", projection_artifact_id=art_proj1.id,
                    projection_sha256=art_proj1.sha256, actor_id=user,
                )
                rep2 = await repo.create_representation(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    content_version_id=cv1.id, generation=2, document_type="xlsx",
                    artifact_id=art2.id, artifact_sha256=art2.sha256,
                    definition_bundle_id=world["bundle"].id,
                    authority_model_definition_id=world["authority"].id,
                    adapter_id="task11.adapter", adapter_build_digest=_d("adapter"),
                    structure_hash=_d("structure2"),
                    identity_inventory_sha256=_d("identity2"),
                    reason="content_commit",
                )
                await repo.set_entry_pointer(
                    wp_id=wp, entry_id=ENTRY, representation_id=rep2.id, generation=2
                )
                raise RuntimeError("injected_outbox_failure_after_publish")
        except RuntimeError as exc:
            injected = str(exc)

        disk_sha, disk_size = artifacts.sha256_of_file(g2.path)
        snap["rollback"] = {
            "injected": injected,
            "pointer_after": await _pointer(),
            "pointer_unchanged": (await _pointer()) == baseline_pointer,
            "counts_equal_baseline": (await _counts()) == baseline_counts,
            "file_survived_db_rollback": g2.path.exists(),
            "file_sha_unchanged": disk_sha == g2.sha256,
            "file_size": disk_size,
            "orphan_relative_path": g2.relative_path,
            "versions_namespace": artifacts.scan_versions_namespace(project, wp),
        }

        # ══ 场景 A2：V151 拒绝 representation 引用 candidate/incoming/orphan ══
        rejects: dict[str, str] = {}
        cand_pub = artifacts.stage_upgrade_candidate(
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=_xlsx("cand"), document_type="xlsx"
            ),
            entry_id=ENTRY, equivalence_report=b"{}",
        )
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            cand_art = await repo.register_artifact(
                project_id=project, wp_id=wp,
                kind=ArtifactKind.upgrade_candidate, state=ArtifactState.candidate,
                relative_path=cand_pub.relative_path, sha256=cand_pub.sha256,
                size_bytes=cand_pub.size_bytes, document_type="xlsx",
                retention_class="upgrade_candidate",
            )
            await s.commit()
            cand_art_id = cand_art.id
        try:
            async with Session() as s:
                repo = WorkpaperSyncRepository(s)
                await repo.create_representation(
                    project_id=project, wp_id=wp, entry_id=ENTRY,
                    content_version_id=world["cv0"].id, generation=99,
                    document_type="xlsx", artifact_id=cand_art_id,
                    artifact_sha256=cand_pub.sha256,
                    definition_bundle_id=world["bundle"].id,
                    authority_model_definition_id=world["authority"].id,
                    adapter_id="task11.adapter", adapter_build_digest=_d("adapter"),
                    structure_hash=_d("s99"), identity_inventory_sha256=_d("i99"),
                    reason="content_commit",
                )
                await s.commit()
                rejects["candidate"] = "ACCEPTED"
        except Exception as exc:  # noqa: BLE001 - 期望被 DB 拒绝
            rejects["candidate"] = getattr(
                getattr(exc, "orig", None), "sqlstate", None
            ) or type(exc).__name__
        snap["db_rejects_representation"] = rejects

        # ══ 场景 B 前置：Task 7 db4 形态二 —— artifact row 已提交但无任何引用 ══
        # （artifact row 先单独提交、pointer 事务失败的真实形态。缺了它，
        #  `OrphanReconciler` 的「标记」分支在本采集里根本不会被执行 ⇒ 相应变异判 GREEN。）
        unref = artifacts.publish_representation(
            entry_id=ENTRY, generation=3,
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=_xlsx("unreferenced"),
                document_type="xlsx",
            ),
        )
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            await repo.register_artifact(
                project_id=project, wp_id=wp,
                kind=ArtifactKind.canonical, state=ArtifactState.published,
                relative_path=unref.relative_path, sha256=unref.sha256,
                size_bytes=unref.size_bytes, document_type="xlsx",
            )
            await s.commit()

        # ══ 场景 B：orphan 对账 ═══════════════════════════════════════════
        async with Session() as s:
            reconciler = OrphanReconciler(s, artifacts)
            outcome = await reconciler.reconcile(project_id=project, wp_id=wp)
            snap["reconcile"] = {
                "scanned_files": outcome.scanned_files,
                "known_paths": outcome.known_paths,
                "registered": list(outcome.registered),
                "marked": list(outcome.marked),
                "missing_files": list(outcome.missing_files),
                "untouched": outcome.untouched,
            }
            await s.commit()
        snap["reconcile"]["pointer_after"] = await _pointer()
        async with Session() as s:
            orphan_row = (
                await s.execute(
                    sa.select(WorkpaperArtifact).where(
                        WorkpaperArtifact.relative_path == g2.relative_path
                    )
                )
            ).scalar_one()
            snap["reconcile"]["orphan_state"] = orphan_row.state
            snap["reconcile"]["orphan_has_orphaned_at"] = orphan_row.orphaned_at is not None
            snap["reconcile"]["orphan_retention_class"] = orphan_row.retention_class
            orphan_id = orphan_row.id
            marked_row = (
                await s.execute(
                    sa.select(WorkpaperArtifact).where(
                        WorkpaperArtifact.relative_path == unref.relative_path
                    )
                )
            ).scalar_one()
            snap["reconcile"]["marked_path"] = unref.relative_path
            snap["reconcile"]["marked_state"] = marked_row.state
            snap["reconcile"]["marked_has_orphaned_at"] = marked_row.orphaned_at is not None
            snap["reconcile"]["marked_retention_class"] = marked_row.retention_class

        # ══ 场景 C：grace 未到的 dry-run ═══════════════════════════════════
        async with Session() as s:
            svc = RetentionPolicyService(s, artifacts, policy=policy)
            plan = await svc.plan(project_id=project, wp_id=wp)
            snap["retention_before_grace"] = {
                "policy_version": plan.policy_version,
                "dry_run": plan.dry_run,
                "decisions": [
                    {"path": d.relative_path, "decision": d.decision, "reason": d.reason,
                     "class": d.retention_class, "sensitivity": d.sensitivity,
                     "roles": list(d.access_roles)}
                    for d in plan.decisions
                ],
                "delete_count": len(plan.deletions),
                "alerts": list(plan.alerts),
            }
            await s.commit()
        snap["retention_before_grace"]["orphan_file_still_there"] = g2.path.exists()

        # ══ 场景 C2：TTL 已过但 grace 未过 ⇒ 必须是 `grace_not_elapsed` ══════
        # （缺了这一档，TTL 门会先行短路，grace 门变成不可达分支 ⇒ 「去掉 grace」
        #  这条变异首轮实测判 GREEN。）
        ttl_only = datetime.now(timezone.utc) - timedelta(hours=24 + 36)
        async with Session() as s:
            await s.execute(
                sa.text(
                    "UPDATE working_paper_artifact SET orphaned_at = :ts WHERE id = :id"
                ),
                {"ts": ttl_only, "id": str(orphan_id)},
            )
            await s.commit()
        async with Session() as s:
            svc = RetentionPolicyService(s, artifacts, policy=policy)
            plan_c2 = await svc.plan(project_id=project, wp_id=wp, write_audit=False)
            await s.rollback()
        snap["retention_ttl_elapsed_grace_not"] = {
            "reason": next(
                d.reason for d in plan_c2.decisions
                if d.relative_path == g2.relative_path
            ),
            "decision": next(
                d.decision for d in plan_c2.decisions
                if d.relative_path == g2.relative_path
            ),
            "delete_count": len(plan_c2.deletions),
            "file_still_there": g2.path.exists(),
        }

        # ══ 场景 D：backdate 之后的 dry-run（永不删）═══════════════════════
        past = datetime.now(timezone.utc) - timedelta(hours=24 + 72 + 5)
        async with Session() as s:
            await s.execute(
                sa.text(
                    "UPDATE working_paper_artifact SET orphaned_at = :ts WHERE id = :id"
                ),
                {"ts": past, "id": str(orphan_id)},
            )
            await s.commit()
        async with Session() as s:
            svc = RetentionPolicyService(s, artifacts, policy=policy)
            plan2 = await svc.plan(project_id=project, wp_id=wp)
            await s.commit()
        snap["retention_after_grace_dry_run"] = {
            "delete_paths": [d.relative_path for d in plan2.deletions],
            "delete_reasons": sorted({d.reason for d in plan2.deletions}),
            "orphan_file_still_there": g2.path.exists(),
            "audit_relative_path": plan2.audit_relative_path,
        }

        # ══ 场景 E：apply 前引用重现 ⇒ 二次复核保留 ════════════════════════
        async with Session() as s:
            await s.execute(
                sa.text(
                    "INSERT INTO working_paper_sync_definition_artifact "
                    "(id, kind, logical_id, semantic_version, blob_artifact_id, sha256, "
                    " source_commit, state) VALUES "
                    "(:id, 'contract', 'reappeared.ref', '9.9.9', :blob, :sha, "
                    " 'task11', 'candidate')"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "blob": str(orphan_id),
                    "sha": _d("reappeared-reference"),
                },
            )
            await s.commit()
        async with Session() as s:
            svc = RetentionPolicyService(s, artifacts, policy=policy)
            outcome_e = await svc.apply(plan2)
            await s.commit()
        snap["retention_apply_reference_reappears"] = {
            "deleted": [d.relative_path for d in outcome_e.deleted],
            "retained": [
                {"path": d.relative_path, "reason": d.reason,
                 "referenced_by": list(d.referenced_by)}
                for d in outcome_e.retained_on_recheck
            ],
            "alerts": list(outcome_e.alerts),
            "orphan_file_still_there": g2.path.exists(),
            "audit_relative_path": outcome_e.audit_relative_path,
        }

        # ══ 场景 F：移除引用后 apply ⇒ 真删 + 逐对象审计 ════════════════════
        async with Session() as s:
            await s.execute(
                sa.text(
                    "DELETE FROM working_paper_sync_definition_artifact "
                    "WHERE logical_id = 'reappeared.ref'"
                )
            )
            await s.commit()
        async with Session() as s:
            svc = RetentionPolicyService(s, artifacts, policy=policy)
            plan3 = await svc.plan(project_id=project, wp_id=wp)
            outcome_f = await svc.apply(plan3)
            await s.commit()
        async with Session() as s:
            row = (
                await s.execute(
                    sa.select(WorkpaperArtifact).where(WorkpaperArtifact.id == orphan_id)
                )
            ).scalar_one()
            deleted_state = row.state
            deleted_at_set = row.deleted_at is not None
        snap["retention_apply_deletes"] = {
            "deleted": [d.relative_path for d in outcome_f.deleted],
            "delete_reasons": sorted({d.reason for d in outcome_f.deleted}),
            "orphan_file_gone": not g2.path.exists(),
            "row_state": deleted_state,
            "row_deleted_at_set": deleted_at_set,
            "gen1_file_intact": g1.path.exists(),
            "pointer_after": await _pointer(),
            "audit_relative_path": outcome_f.audit_relative_path,
            "audit_sha256": outcome_f.audit_sha256,
        }

        # ══ 场景 G：审计产物已持久化且自身不可删 ════════════════════════════
        audit_path = artifacts.resolve_relative_path(outcome_f.audit_relative_path)
        audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
        async with Session() as s:
            audit_rows = list(
                (
                    await s.execute(
                        sa.select(WorkpaperArtifact).where(
                            WorkpaperArtifact.retention_class == "retention_audit"
                        )
                    )
                ).scalars()
            )
            snap["audit"] = {
                "row_count": len(audit_rows),
                "all_legal_hold": all(bool(r.legal_hold) for r in audit_rows),
                "all_published": all(r.state == "published" for r in audit_rows),
                "payload_dry_run": audit_payload["dry_run"],
                "payload_policy_version": audit_payload["policy_version"],
                "payload_decision_count": audit_payload["decision_count"],
                "payload_has_per_object_rows": len(audit_payload["decisions"]) > 0,
                "dry_run_flags_seen": sorted(
                    {
                        json.loads(
                            artifacts.resolve_relative_path(r.relative_path).read_text(
                                encoding="utf-8"
                            )
                        )["dry_run"]
                        for r in audit_rows
                    },
                    key=str,
                ),
            }
            svc = RetentionPolicyService(s, artifacts, policy=policy)
            plan4 = await svc.plan(project_id=project, wp_id=wp, write_audit=False)
            snap["audit"]["audit_decisions"] = sorted(
                {
                    f"{d.decision}:{d.reason}"
                    for d in plan4.decisions
                    if d.retention_class == "retention_audit"
                }
            )
            snap["audit"]["definition_decisions"] = sorted(
                {
                    f"{d.decision}:{d.reason}"
                    for d in plan4.decisions
                    if d.retention_class == "definition"
                }
            )
            await s.rollback()

        # ══ 场景 H：retain 原因矩阵 ════════════════════════════════════════
        matrix: dict[str, dict[str, Any]] = {}
        probe_files: dict[str, Any] = {}
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            svc = RetentionPolicyService(s, artifacts, policy=policy)
            specs = [
                ("legal_hold", "orphan_canonical", ArtifactState.orphan, True, True),
                ("no_policy_retain_and_alert", "bogus_class", ArtifactState.orphan, False, True),
                ("class_scope_mismatch", "orphan_canonical", ArtifactState.published,
                 False, True),
                ("orphaned_at_missing", "orphan_canonical", ArtifactState.orphan, False, False),
            ]
            for label, klass, state, hold, set_orphaned in specs:
                pub = artifacts.publish_representation(
                    entry_id=f"{ENTRY}.probe.{label}", generation=1,
                    staged=artifacts.stage_bytes(
                        project_id=project, wp_id=wp, payload=_xlsx(label),
                        document_type="xlsx",
                    ),
                )
                probe_files[label] = pub
                art = await repo.register_artifact(
                    project_id=project, wp_id=wp,
                    kind=ArtifactKind.canonical, state=state,
                    relative_path=pub.relative_path, sha256=pub.sha256,
                    size_bytes=pub.size_bytes, document_type="xlsx",
                    retention_class=klass,
                )
                art.legal_hold = hold
                if set_orphaned:
                    art.orphaned_at = past
                await s.flush()
                decision = await svc._decide(  # noqa: SLF001 - 判定核心的直接判据
                    art, datetime.now(timezone.utc), recheck=False
                )
                matrix[label] = {
                    "decision": decision.decision,
                    "reason": decision.reason,
                    "alert": decision.alert,
                }

            # in_flight_operation：artifact 的 created_by_operation_id 指向非终态 operation
            pub = artifacts.publish_representation(
                entry_id=f"{ENTRY}.probe.inflight", generation=1,
                staged=artifacts.stage_bytes(
                    project_id=project, wp_id=wp, payload=_xlsx("inflight"),
                    document_type="xlsx",
                ),
            )
            probe_files["in_flight_operation"] = pub
            op_id = uuid.uuid4()
            await s.execute(
                sa.text(
                    "INSERT INTO working_paper_sync_operation "
                    "(id, project_id, wp_id, entry_id, direction, state, "
                    " definition_bundle_id, definition_bundle_sha256, "
                    " authority_model_definition_id, authority_model_definition_sha256) "
                    "VALUES (:id, :p, :wp, :e, 'oo_to_html', 'merging', :b, :bs, :a, :as_)"
                ),
                {
                    "id": str(op_id), "p": str(project), "wp": str(wp), "e": ENTRY,
                    "b": str(world["bundle"].id),
                    "bs": world["bundle"].canonical_payload_sha256,
                    "a": str(world["authority"].id),
                    "as_": world["authority"].sha256,
                },
            )
            art = await repo.register_artifact(
                project_id=project, wp_id=wp,
                kind=ArtifactKind.canonical, state=ArtifactState.orphan,
                relative_path=pub.relative_path, sha256=pub.sha256,
                size_bytes=pub.size_bytes, document_type="xlsx",
                retention_class="orphan_canonical",
                created_by_operation_id=op_id,
            )
            art.orphaned_at = past
            await s.flush()
            decision = await svc._decide(  # noqa: SLF001
                art, datetime.now(timezone.utc), recheck=False
            )
            matrix["in_flight_operation"] = {
                "decision": decision.decision,
                "reason": decision.reason,
                "alert": decision.alert,
                "referenced_by": list(decision.referenced_by),
            }
            await s.rollback()
        snap["retention_reason_matrix"] = matrix
        snap["retention_reason_matrix"]["_probe_files_still_on_disk"] = all(
            p.path.exists() for p in probe_files.values()
        )

        # ══ 场景 I：references_of 的 12 条 SQL 必须真跑通（防拼错列名）══════
        async with Session() as s:
            svc = RetentionPolicyService(s, artifacts, policy=policy)
            unknown = await svc.references_of(uuid.uuid4())
            hits_for_definition_blob = await svc.references_of(
                uuid.UUID(str(world["art_g1"].id))
            )
            snap["reference_sources_execute"] = {
                "unknown_artifact_refs": list(unknown),
                "gen1_artifact_refs": list(hits_for_definition_blob),
            }

        # ══ 场景 J：service 只 flush 不 commit ═════════════════════════════
        async with Session() as s:
            before = int(
                (
                    await s.execute(
                        sa.text(
                            "SELECT count(*) FROM working_paper_artifact "
                            "WHERE retention_class = 'retention_audit'"
                        )
                    )
                ).scalar_one()
            )
        async with Session() as s:
            svc = RetentionPolicyService(s, artifacts, policy=policy)
            plan5 = await svc.plan(project_id=project, wp_id=wp)
            await s.rollback()
        async with Session() as s:
            after = int(
                (
                    await s.execute(
                        sa.text(
                            "SELECT count(*) FROM working_paper_artifact "
                            "WHERE retention_class = 'retention_audit'"
                        )
                    )
                ).scalar_one()
            )
        snap["flush_only"] = {
            "audit_rows_before": before,
            "audit_rows_after_rollback": after,
            "audit_file_orphaned_on_disk": artifacts.resolve_relative_path(
                str(plan5.audit_relative_path)
            ).exists(),
        }

        # ══ 场景 K：resolver 只返回 published canonical/projection ═════════
        async with Session() as s:
            visible = list(
                (
                    await s.execute(
                        sa.text(
                            "SELECT a.relative_path FROM working_paper_sync_entry_state es "
                            "JOIN working_paper_content_representation r "
                            "  ON r.id = es.current_representation_id "
                            "JOIN working_paper_artifact a ON a.id = r.artifact_id "
                            "WHERE es.wp_id = :wp AND es.entry_id = :e"
                        ),
                        {"wp": str(wp), "e": ENTRY},
                    )
                ).scalars()
            )
        snap["resolver"] = {
            "current_paths": visible,
            "gen1_path": g1.relative_path,
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
        shutil.rmtree(base_root, ignore_errors=True)


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    """一次 `asyncio.run` 采集全部场景（共享连接池不可跨测试重开）。"""
    return asyncio.run(_collect())


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    assert _CONTRACT_PATH.exists(), f"Task 7 边界契约缺失: {_CONTRACT_PATH}"
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════════════════
# 断言
# ═══════════════════════════════════════════════════════════════════════════


def test_scratch_schema_isolated_and_migration_applied(snap: dict[str, Any]) -> None:
    assert snap["schema"].startswith(_SCHEMA_PREFIX)
    assert snap["apply_errors"] == []
    assert "PostgreSQL" in str(snap["server_version"])


def test_property_5_publish_then_db_rollback_leaves_invisible_orphan(
    snap: dict[str, Any], contract: dict[str, Any]
) -> None:
    """Property 5 核心：DB rollback 后 pointer 不变、行数不变，但**文件仍在**。

    这同时是「文件系统与 PostgreSQL 不是同一事务」的正证据 —— 契约里
    `cross_medium_transaction.filesystem_and_postgres_share_one_transaction` 必须为 false。
    """
    assert contract["cross_medium_transaction"][
        "filesystem_and_postgres_share_one_transaction"
    ] is False
    rb = snap["rollback"]
    assert rb["injected"] == "injected_outbox_failure_after_publish"
    assert rb["pointer_unchanged"] is True
    assert rb["pointer_after"]["generation"] == 1
    assert rb["counts_equal_baseline"] is True
    assert rb["file_survived_db_rollback"] is True
    assert rb["file_sha_unchanged"] is True
    # 磁盘上有两个 generation 的文件，但 pointer 只认 gen 1
    assert len(rb["versions_namespace"]) >= 2


def test_v151_rejects_representation_referencing_candidate(snap: dict[str, Any]) -> None:
    """服务端 `assert_canonical_resolvable` 之外的第二道锁：DB CHECK/trigger。"""
    assert snap["db_rejects_representation"]["candidate"] != "ACCEPTED"
    assert snap["db_rejects_representation"]["candidate"] in {"23514", "IntegrityError"}


def test_orphan_reconciliation_registers_and_marks(snap: dict[str, Any]) -> None:
    """Task 7 db4 的两种形态都必须被对账出来，且 resolver 不受影响。"""
    rec = snap["reconcile"]
    assert snap["rollback"]["orphan_relative_path"] in rec["registered"], (
        "磁盘有文件、DB 无 row 的 orphan 必须被登记"
    )
    assert rec["orphan_state"] == "orphan"
    assert rec["orphan_has_orphaned_at"] is True
    assert rec["orphan_retention_class"] == "orphan_canonical"
    assert rec["pointer_after"]["generation"] == 1
    assert rec["scanned_files"] >= 2

    # 形态二：DB 有 published row 但无任何 representation/content_version 引用
    assert rec["marked_path"] in rec["marked"], (
        "DB 有 published row、无引用的 artifact 必须被**标记**为 orphan"
    )
    assert rec["marked_state"] == "orphan"
    assert rec["marked_has_orphaned_at"] is True
    assert rec["marked_retention_class"] == "orphan_canonical", (
        "标记 orphan 时必须同步 retention class —— 否则 default 类的 "
        "applies_to_states 只含 published，这批 orphan 会永远 class_scope_mismatch "
        "保留 + 告警，既回收不了也刷屏"
    )
    assert rec["untouched"] >= 2, "被正常引用的 published artifact 不得被动"


def test_dry_run_never_deletes_and_reports_grace(snap: dict[str, Any]) -> None:
    """Requirement 5.11：dry-run 必须先行且永不删除。"""
    before = snap["retention_before_grace"]
    assert before["dry_run"] is True
    assert before["delete_count"] == 0, "grace 未到不得出现 delete 判定"
    reasons = {d["reason"] for d in before["decisions"]}
    assert "ttl_not_elapsed" in reasons, "刚对账出的 orphan 必须先卡 TTL"
    assert before["orphan_file_still_there"] is True
    # 每条判定都带 class / 敏感级别 / access roles（Requirement 10.7）
    for d in before["decisions"]:
        assert d["sensitivity"], d
        assert d["roles"], d

    # TTL 已过、grace 未过：必须是独立的 `grace_not_elapsed` 档。
    # 只测「刚 orphan」时 TTL 门会先短路，grace 门成为不可达分支。
    mid = snap["retention_ttl_elapsed_grace_not"]
    assert mid["decision"] == "retain"
    assert mid["reason"] == "grace_not_elapsed"
    assert mid["delete_count"] == 0
    assert mid["file_still_there"] is True

    after = snap["retention_after_grace_dry_run"]
    assert after["delete_reasons"] == ["grace_elapsed_and_unreferenced"]
    assert after["orphan_file_still_there"] is True, "dry-run 阶段文件必须完好"
    assert after["audit_relative_path"]


def test_second_reference_recheck_retains_when_reference_reappears(
    snap: dict[str, Any], contract: dict[str, Any]
) -> None:
    """计划与执行之间新出现的引用必须让 apply 改判 retain（Task 7 db5 的关键分支）。"""
    gc = contract["db_boundary"]["retention_gc"]
    assert gc["observed_reference_reappears_retained"] is True
    assert gc["observed_reference_reappears_reason"] == "reference_found_on_recheck"

    step = snap["retention_apply_reference_reappears"]
    assert step["deleted"] == [], "引用重现时不得删除任何对象"
    assert step["orphan_file_still_there"] is True
    retained = {r["reason"] for r in step["retained"]}
    assert "reference_found_on_recheck" in retained
    hit = next(r for r in step["retained"] if r["reason"] == "reference_found_on_recheck")
    assert "working_paper_sync_definition_artifact.blob_artifact_id" in hit["referenced_by"], (
        "审计必须记下命中的是哪张表哪一列，而不是只回答『有引用』"
    )
    assert any("reference_found_on_recheck" in a for a in step["alerts"])


def test_apply_deletes_only_after_unreferenced_and_writes_audit(
    snap: dict[str, Any], contract: dict[str, Any]
) -> None:
    gc = contract["db_boundary"]["retention_gc"]
    assert gc["observed_delete_reason"] == "grace_elapsed_and_unreferenced"
    step = snap["retention_apply_deletes"]
    assert step["delete_reasons"] == ["grace_elapsed_and_unreferenced"]
    assert step["orphan_file_gone"] is True
    assert step["row_state"] == "deleted" and step["row_deleted_at_set"] is True
    assert step["gen1_file_intact"] is True, "GC 不得动到 current published artifact"
    assert step["pointer_after"]["generation"] == 1, "GC 全程不影响 resolver 结果"
    assert step["audit_relative_path"] and step["audit_sha256"]


def test_audit_is_per_object_persisted_and_itself_not_deletable(snap: dict[str, Any]) -> None:
    audit = snap["audit"]
    assert audit["row_count"] >= 2, "dry-run 与 apply 必须各留一份审计"
    assert audit["all_legal_hold"] is True
    assert audit["all_published"] is True
    assert audit["payload_has_per_object_rows"] is True
    assert audit["payload_policy_version"] == "workpaper-sync-retention:v1"
    assert set(audit["dry_run_flags_seen"]) == {True, False}, (
        "dry_run 真假必须分别留痕（Requirement 5.11）"
    )
    # 审计产物自身永不被删：legal_hold 与 class_not_deletable 双保险。
    # legal hold 判定在 deletable 之前（法务冻结优先级最高），故这里命中 legal_hold。
    assert audit["audit_decisions"] == ["retain:legal_hold"], (
        "审计产物自身若可被 GC 删除，删除记录会被下一轮抹掉"
    )
    # `class_not_deletable` 分支由 definition 类（无 legal hold、deletable=false）证明可达 ——
    # 否则那条分支会被 legal_hold 永久遮蔽成不可达代码。
    assert audit["definition_decisions"] == ["retain:class_not_deletable"]


def test_retain_reason_matrix_covers_every_uncertainty_branch(snap: dict[str, Any]) -> None:
    """『不确定即保留告警』的五条分支都必须真产出，且 alert 位正确。"""
    m = snap["retention_reason_matrix"]
    expected = {
        "legal_hold": False,
        "no_policy_retain_and_alert": True,
        "class_scope_mismatch": True,
        "orphaned_at_missing": True,
        "in_flight_operation": True,
    }
    for label, wants_alert in expected.items():
        assert m[label]["decision"] == "retain", label
        assert m[label]["reason"] == label, label
        assert m[label]["alert"] is wants_alert, label
    assert m["in_flight_operation"]["referenced_by"][0].startswith("operation:")
    assert m["_probe_files_still_on_disk"] is True


def test_reference_sources_all_execute_against_real_schema(snap: dict[str, Any]) -> None:
    """12 条引用查询必须真跑通：表名/列名拼错会直接 ProgrammingError 而不是静默 0 行。

    这是本任务里最容易 fail-open 的一处 —— 若 `references_of` 包了
    `except Exception: return ()`，GC 会把「查不到引用」当成「无引用」并删掉在用文件。
    采集阶段不设任何兜底，异常会让整个 fixture 报 ERROR。
    """
    refs = snap["reference_sources_execute"]
    assert refs["unknown_artifact_refs"] == []
    assert "working_paper_content_representation.artifact_id" in refs["gen1_artifact_refs"]


def test_retention_service_only_flushes(snap: dict[str, Any]) -> None:
    """service 不 commit：rollback 后审计行数不变，但审计**文件**仍在（跨介质证据）。"""
    fo = snap["flush_only"]
    assert fo["audit_rows_after_rollback"] == fo["audit_rows_before"]
    assert fo["audit_file_orphaned_on_disk"] is True, (
        "rollback 不回滚文件 —— 这正是 orphan 对账存在的理由"
    )


def test_resolver_returns_only_current_published_artifact(snap: dict[str, Any]) -> None:
    assert snap["resolver"]["current_paths"] == [snap["resolver"]["gen1_path"]]
