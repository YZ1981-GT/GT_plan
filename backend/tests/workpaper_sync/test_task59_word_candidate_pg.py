# -*- coding: utf-8 -*-
"""Task 59 真实 PostgreSQL 守卫：Word candidate **不得带入运行态**的四条边界。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 5 Task 59
Requirements: 2.3, 6.18, 8.10, 9.1, 9.10
Properties: **P65** / **P67**

═══ 为什么这四条必须**真实调用后查库**证明 ═══

Task 59 的正文三处强调同一条边界：upgrader 只登记 **non-current** candidate，
**不得**创建 published/current representation、**不得**切 pointer、**不得**进入
resolver/room/evidence、**不得**递增 revision。

「代码里没有 UPDATE」证明不了这四条 —— revision 推进可以经 repository、helper 或
另一个 service 发生。所以本文件的判据全是**同一个 wp 上前后两次查库**：

======  =====================================  ==============================
边界    判据（真实 SQL）                        表 / 列
======  =====================================  ==============================
①       `content_revision` 前后逐值相等          `working_paper.content_revision`
②       current pointer 前后逐值相等             `working_paper_sync_entry_state
                                               .current_representation_id`
③       representation 行数与内容前后相等          `working_paper_content_representation`
④       resolver 可见性前后相等                   `CanonicalResolutionService
                                               .resolve()` 的实测返回
======  =====================================  ==============================

第 ④ 条尤其重要：它不是「查 candidate 表」，而是**真的调用统一 resolver**，证明
candidate 登记之后 resolver 返回的 artifact/bundle identity 与登记之前逐字段相同。
只查 candidate 表的守卫在「resolver 某天顺手把 candidate 当 fallback」时照样绿。

`DATABASE_URL` 非 PostgreSQL 时**直接失败而不是 skip**：静默 skip 会把本文件唯一的
判据删掉，留下一份「全绿」的假象。

═══ 隔离 ═══

scratch schema `tmp_task59_pg_*`，`search_path` 不含 public；文件全在系统临时目录。
结束 `DROP SCHEMA CASCADE` + 删临时目录。**绝不触碰真实 `storage/` 与
`backend/wp_templates/`**（后者跑完必须字节原样，由
`TestAuthorityTemplateIsUntouched` 复核）。

═══ 采集写法 ═══

全部场景用**一次 `asyncio.run`** 跑完并落进快照（module fixture）。不给每个测试各自
开 async —— 共享连接池会被污染，第二个测试起 `NoneType has no attribute send`。
采集内部任何异常都记进快照的 `errors`，由守卫断言为空（禁 fail-open）。
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

_SCHEMA_PREFIX = "tmp_task59_pg_"

# 🔴 复用既有 PG 套件的 DDL/enum 工具与 Task 59 离线套件的 fixture：两处都不抄第二份
#    （抄一份就会出现「stub 表结构与生产不同」这类只在这里成立的绿）。
from test_task15_content_mutation_pg import _STUB_DDL, _enum_ddl, _err  # noqa: E402
from test_task59_word_sdt_engine import (  # noqa: E402
    B30112,
    B30112_SHA,
    DEF_ID,
    F222,
    F222_SHA,
    PLAN_ID,
    deficiency_spec,
    plan_contract_payload,
    plan_spec,
)


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：要守卫级，而不是降级成「无数据」）。"""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(seed: str) -> str:
    return _sha(seed.encode("utf-8"))


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.dataset_models import ImportEventConsumption, ImportEventOutbox
    from app.services import event_bus as event_bus_module
    from app.services.workpaper_sync import definitions as D
    from app.services.workpaper_sync import word_instrumentation as WI
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.models import ArtifactKind, ArtifactState, BundleSlot
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import (
        CanonicalResolutionService,
        ResolutionIntent,
    )

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "本文件的判据是「真实登记 candidate 之后查库 revision/pointer/representation/"
            "resolver 全部不变」，依赖真实事务语义与 V151；必须真实 PostgreSQL，当前为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task59_store_"))
    (base_root / "storage").mkdir()

    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "template_sha_before": {
            "F2-22": _sha(F222.read_bytes()),
            "B30-11-2": _sha(B30112.read_bytes()),
        },
        "apply_errors": [],
        "errors": [],
        "gate": {},
        "definitions": {},
        "candidate": {},
        "before": {},
        "after": {},
        "resolver": {},
        "forbidden_surface": {},
    }
    engine = None
    bus = event_bus_module.event_bus
    previous_redis_flag = bus._redis_available
    bus._redis_available = False
    try:
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

        project, wp, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{project}')")
            await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{user}')")
            await conn.exec_driver_sql(
                f"INSERT INTO working_paper (id, project_id) VALUES ('{wp}', '{project}')"
            )

        artifacts = CanonicalArtifactRepository(base_root)
        gate = WI.WordSdtCarrierGate.load()
        snap["gate"] = gate.probe_gate_identity()

        # ── 先建一个「已发布」的 Word representation 当 from-state ────────
        source_bytes = F222.read_bytes()
        gen1 = artifacts.publish_representation(
            entry_id=PLAN_ID,
            generation=1,
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=source_bytes, document_type="docx"
            ),
        )
        proj0 = artifacts.publish_projection(
            revision=0,
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp,
                payload=b"task59-projection-v0", document_type="json.gz",
            ),
        )
        blobs = {
            name: artifacts.publish_definition_blob(
                project_id=project, wp_id=wp, definition_kind=kind,
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
                    project_id=project, wp_id=wp,
                    kind=ArtifactKind.definition, state=ArtifactState.published,
                    relative_path=pub.relative_path, sha256=pub.sha256,
                    size_bytes=pub.size_bytes, document_type="json",
                    retention_class="definition",
                )
                for name, pub in blobs.items()
            }
            art_gen1 = await repo.register_artifact(
                project_id=project, wp_id=wp,
                kind=ArtifactKind.canonical, state=ArtifactState.published,
                relative_path=gen1.relative_path, sha256=gen1.sha256,
                size_bytes=gen1.size_bytes, document_type="docx",
            )
            art_proj0 = await repo.register_artifact(
                project_id=project, wp_id=wp,
                kind=ArtifactKind.projection, state=ArtifactState.published,
                relative_path=proj0.relative_path, sha256=proj0.sha256,
                size_bytes=proj0.size_bytes, document_type="json.gz",
            )
            contract_payload = plan_contract_payload()
            tpl = await repo.create_definition_artifact(
                kind="template", logical_id="task59.word.tpl", semantic_version="1.0.0",
                blob_artifact_id=art["tpl"].id,
                sha256=contract_payload["template_definition_sha256"],
                structure_hash=_digest("task59-tpl-structure"), source_commit="task59",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation", logical_id="task59.word.instr",
                semantic_version="1.0.0", blob_artifact_id=art["instr"].id,
                sha256=contract_payload["instrumentation_definition_sha256"],
                structure_hash=_digest("task59-instr-structure"), source_commit="task59",
            )
            contract_def = await repo.create_definition_artifact(
                kind="contract", logical_id="task59.word.contract",
                semantic_version="1.0.0", blob_artifact_id=art["contract"].id,
                sha256=_digest("task59-contract"), source_commit="task59",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task59.word.authority",
                semantic_version="1.0.0", blob_artifact_id=art["authority"].id,
                sha256=_digest("task59-authority"),
                authority_model_type="projection_contract", source_commit="task59",
            )

            def _slots() -> dict[Any, Any]:
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
            cv0 = await repo.create_content_version(
                project_id=project, wp_id=wp, entry_id=PLAN_ID, revision=0, source="html",
                projection_artifact_id=art_proj0.id,
                projection_sha256=art_proj0.sha256, actor_id=user,
            )
            rep1 = await repo.create_representation(
                project_id=project, wp_id=wp, entry_id=PLAN_ID,
                content_version_id=cv0.id, generation=1, document_type="docx",
                artifact_id=art_gen1.id, artifact_sha256=art_gen1.sha256,
                definition_bundle_id=bundle.id,
                authority_model_definition_id=authority.id,
                adapter_id=PLAN_ID, adapter_build_digest=_digest("task59-adapter"),
                structure_hash=_digest("task59-structure-1"),
                identity_inventory_sha256=_digest("task59-identity-1"),
                reason="content_commit",
            )
            await repo.set_entry_pointer(
                wp_id=wp, entry_id=PLAN_ID, representation_id=rep1.id, generation=1
            )
            await repo.set_current_content_version(wp, cv0.id)
            await s.commit()
            world.update({"cv0": cv0.id, "rep1": rep1.id, "bundle": bundle.id,
                          "tpl": tpl.id, "instr": instr.id})

        # ── 四条边界的**前后**快照工具 ─────────────────────────────────
        async def _state(session: Any) -> dict[str, Any]:
            revision = (
                await session.execute(
                    sa.text("SELECT content_revision FROM working_paper WHERE id = :w"),
                    {"w": str(wp)},
                )
            ).scalar_one()
            pointer = (
                await session.execute(
                    sa.text(
                        "SELECT current_representation_id::text, representation_generation "
                        "FROM working_paper_sync_entry_state "
                        "WHERE wp_id = :w AND entry_id = :e"
                    ),
                    {"w": str(wp), "e": PLAN_ID},
                )
            ).first()
            reps = (
                await session.execute(
                    sa.text(
                        "SELECT generation, content_version_id::text, artifact_sha256, "
                        "definition_bundle_id::text "
                        "FROM working_paper_content_representation "
                        "WHERE wp_id = :w AND entry_id = :e ORDER BY generation"
                    ),
                    {"w": str(wp), "e": PLAN_ID},
                )
            ).all()
            versions = (
                await session.execute(
                    sa.text(
                        "SELECT count(*) FROM working_paper_content_version WHERE wp_id = :w"
                    ),
                    {"w": str(wp)},
                )
            ).scalar_one()
            return {
                "content_revision": int(revision),
                "pointer_representation_id": pointer[0] if pointer else None,
                "pointer_generation": int(pointer[1]) if pointer else None,
                "representations": [
                    {
                        "generation": int(r[0]),
                        "content_version_id": r[1],
                        "artifact_sha256": r[2],
                        "definition_bundle_id": r[3],
                    }
                    for r in reps
                ],
                "content_version_count": int(versions),
            }

        async def _resolved(session: Any) -> dict[str, Any]:
            """真实调用统一 resolver（不是查 candidate 表）。

            两个意图都跑：`config`（按 entry current pointer）与 `history`（按 frozen
            `representation_id`）。前者证明 candidate 没有偷换 current 指向，后者证明
            历史读取不会按 alias 重组 bundle —— 只跑一个会漏掉另一条路径。
            """
            service = CanonicalResolutionService(session, artifacts)
            out: dict[str, Any] = {}
            for intent, rep_id in (
                (ResolutionIntent.config, None),
                (ResolutionIntent.history, world["rep1"]),
            ):
                resolved = await service.resolve(
                    intent=intent,
                    project_id=project,
                    wp_id=wp,
                    entry_id=PLAN_ID,
                    representation_id=rep_id,
                    expected_content_version_id=world["cv0"],
                    expected_document_type="docx",
                )
                out[intent.value] = {
                    "representation_id": str(resolved.representation_id),
                    "generation": int(resolved.representation_generation),
                    "content_revision": int(resolved.content_revision),
                    "artifact_sha256": resolved.artifact_sha256,
                    "artifact_relative_path": resolved.artifact_relative_path,
                    "definition_bundle_id": str(resolved.bundle.bundle_id),
                    "definition_bundle_sha256": resolved.bundle.bundle_sha256,
                }
            return out

        async with Session() as s:
            snap["before"] = await _state(s)
            try:
                snap["resolver"]["before"] = await _resolved(s)
            except Exception as exc:  # noqa: BLE001
                snap["errors"].append(f"resolve(before): {_err(exc)}")

        # ── 真跑 upgrader：发布 definitions + 注入 + 登记 non-current candidate ──
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            upgrader = WI.WordInstrumentationUpgrader(
                session=s,
                repository=repo,
                artifacts=artifacts,
                project_id=project,
                source_commit="task59-pg",
                gate=gate,
            )
            snap["forbidden_surface"] = {}
            for method in ("create_representation", "set_entry_pointer", "finalize_candidate"):
                try:
                    getattr(upgrader.repository, method)
                except Exception as exc:  # noqa: BLE001
                    snap["forbidden_surface"][method] = getattr(exc, "error_code", "")
                else:  # pragma: no cover - 门面失守
                    snap["errors"].append(f"{method} 未被 candidate 门面拒绝")
            try:
                spec = plan_spec()
                template_def, instr_def, payload = await upgrader.publish_definitions(
                    spec=spec, wp_id=wp, template_bytes=source_bytes
                )
                snap["definitions"] = {
                    "template_sha256": template_def.sha256,
                    "instrumentation_sha256": instr_def.sha256,
                    "instrumentation_payload_keys": sorted(payload),
                }
                instrumented, equivalence, readback = upgrader.instrument_source_bytes(
                    source=source_bytes, spec=spec
                )
                outcome = await upgrader.stage_and_register_candidate(
                    spec=spec,
                    wp_id=wp,
                    content_version_id=world["cv0"],
                    source_representation_id=world["rep1"],
                    source_bytes=source_bytes,
                    instrumented=instrumented,
                    equivalence=equivalence,
                    readback=readback,
                    template_definition=template_def,
                    instrumentation_definition=instr_def,
                    from_definition_bundle_id=world["bundle"],
                    from_definition_bundle_sha256=_digest("task59-authority"),
                    actor_id=user,
                )
                await s.commit()
                snap["candidate"] = outcome.as_dict()
            except Exception as exc:  # noqa: BLE001
                snap["errors"].append(f"stage_and_register_candidate: {_err(exc)}")
                raise

        async with Session() as s:
            snap["after"] = await _state(s)
            try:
                snap["resolver"]["after"] = await _resolved(s)
            except Exception as exc:  # noqa: BLE001
                snap["errors"].append(f"resolve(after): {_err(exc)}")
            rows = (
                await s.execute(
                    sa.text(
                        "SELECT state, target_contract_definition_id, "
                        "target_definition_bundle_id, finalized_representation_id, "
                        "finalized_at, visible_equivalence_report_sha256, "
                        "rollback_source_sha256 "
                        "FROM working_paper_representation_upgrade_candidate "
                        "WHERE wp_id = :w AND entry_id = :e"
                    ),
                    {"w": str(wp), "e": PLAN_ID},
                )
            ).all()
            snap["candidate_rows"] = [
                {
                    "state": r[0],
                    "target_contract_definition_id": r[1],
                    "target_definition_bundle_id": r[2],
                    "finalized_representation_id": r[3],
                    "finalized_at": r[4],
                    "visible_equivalence_report_sha256": r[5],
                    "rollback_source_sha256": r[6],
                }
                for r in rows
            ]
            artifact_rows = (
                await s.execute(
                    sa.text(
                        "SELECT kind, state, relative_path FROM working_paper_artifact "
                        "WHERE wp_id = :w AND kind = 'upgrade_candidate'"
                    ),
                    {"w": str(wp)},
                )
            ).all()
            snap["candidate_artifacts"] = [
                {"kind": r[0], "state": r[1], "relative_path": r[2]} for r in artifact_rows
            ]
            events = (
                await s.execute(
                    sa.text(
                        "SELECT event_type FROM import_event_outbox ORDER BY created_at"
                    )
                )
            ).all()
            snap["outbox_event_types"] = [r[0] for r in events]

        snap["template_sha_after"] = {
            "F2-22": _sha(F222.read_bytes()),
            "B30-11-2": _sha(B30112.read_bytes()),
        }
        snap["deficiency_spec_row_count"] = len(deficiency_spec().rows)
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


class TestHarness:
    """采集本身必须干净 —— 禁 fail-open。"""

    def test_no_collection_errors(self, snap: dict[str, Any]) -> None:
        assert snap["errors"] == [], snap["errors"]
        assert snap["apply_errors"] == []

    def test_definitions_were_actually_published(self, snap: dict[str, Any]) -> None:
        """DAG 前两段真的跑了（否则后面的「没动运行态」是因为什么都没做）。"""
        assert len(snap["definitions"]["template_sha256"]) == 64
        assert len(snap["definitions"]["instrumentation_sha256"]) == 64
        keys = snap["definitions"]["instrumentation_payload_keys"]
        assert "template_definition_sha256" in keys
        assert not [k for k in keys if k.startswith(("contract_", "bundle_"))]

    def test_candidate_was_actually_registered(self, snap: dict[str, Any]) -> None:
        assert len(snap["candidate_rows"]) == 1
        assert snap["candidate"]["state"] == "awaiting_contract"
        assert len(snap["candidate_artifacts"]) == 1


class TestBoundary1ContentRevisionUnchanged:
    """**Validates: Requirements 2.3 / 6.18 / 9.10** · Property 67

    边界①：登记 candidate 不得递增 `content_revision`。判据是查库前后逐值相等。
    """

    def test_database_revision_is_unchanged(self, snap: dict[str, Any]) -> None:
        before = snap["before"]["content_revision"]
        after = snap["after"]["content_revision"]
        assert after == before, (
            f"登记 non-current candidate 推进了 content revision：{before} → {after} —— "
            "纯 representation 升级前置阶段不得制造伪业务 revision（AC 6.18 / 9.10）"
        )

    def test_outcome_snapshot_agrees_with_the_database(
        self, snap: dict[str, Any]
    ) -> None:
        """upgrader 自采的 before/after 与独立查库口径必须一致（防自证）。"""
        assert snap["candidate"]["revision_unchanged"] is True
        assert snap["candidate"]["content_revision_before"] == snap["before"][
            "content_revision"
        ]
        assert snap["candidate"]["content_revision_after"] == snap["after"][
            "content_revision"
        ]

    def test_no_new_content_version_was_created(self, snap: dict[str, Any]) -> None:
        assert snap["after"]["content_version_count"] == snap["before"][
            "content_version_count"
        ]


class TestBoundary2CurrentPointerUnchanged:
    """**Validates: Requirements 6.18 / 9.10** · Property 67

    边界②：不得切 entry pointer。
    """

    def test_pointer_is_unchanged(self, snap: dict[str, Any]) -> None:
        assert snap["after"]["pointer_representation_id"] == snap["before"][
            "pointer_representation_id"
        ]
        assert snap["after"]["pointer_generation"] == snap["before"][
            "pointer_generation"
        ]
        assert snap["before"]["pointer_representation_id"], (
            "前置状态必须真的有一个 current pointer，否则「pointer 未变」是空转"
        )

    def test_candidate_is_not_the_pointer(self, snap: dict[str, Any]) -> None:
        assert snap["candidate"]["candidate_id"] != snap["after"][
            "pointer_representation_id"
        ]


class TestBoundary3NoPublishedRepresentation:
    """**Validates: Requirements 2.3 / 6.18 / 8.10** · Property 67

    边界③：不得创建 published/current representation，旧 row 不得被原地改写。
    """

    def test_representation_rows_are_byte_identical(self, snap: dict[str, Any]) -> None:
        assert snap["after"]["representations"] == snap["before"]["representations"]
        assert [r["generation"] for r in snap["before"]["representations"]] == [1]

    def test_candidate_reports_zero_representation_delta(
        self, snap: dict[str, Any]
    ) -> None:
        assert snap["candidate"]["no_representation_created"] is True
        assert snap["candidate"]["representation_count_before"] == 1
        assert snap["candidate"]["representation_count_after"] == 1

    def test_candidate_artifact_is_isolated_in_the_candidate_namespace(
        self, snap: dict[str, Any]
    ) -> None:
        row = snap["candidate_artifacts"][0]
        assert row["kind"] == "upgrade_candidate"
        assert row["state"] == "candidate"
        assert ".upgrade-candidates" in row["relative_path"], (
            "candidate 必须与 `.versions` 物理隔离，否则一个手滑的 relative_path 就能"
            "让它被 resolver 当 current 读到"
        )

    def test_candidate_is_not_finalizable_without_approved_children(
        self, snap: dict[str, Any]
    ) -> None:
        row = snap["candidate_rows"][0]
        assert row["state"] == "awaiting_contract"
        assert row["target_contract_definition_id"] is None
        assert row["target_definition_bundle_id"] is None
        assert row["finalized_representation_id"] is None
        assert row["finalized_at"] is None
        # 但审计所需的两个 digest 必须已写（Requirement 9.10 的记录清单）
        assert row["visible_equivalence_report_sha256"]
        assert row["rollback_source_sha256"]


class TestBoundary4ResolverVisibilityUnchanged:
    """**Validates: Requirements 6.18 / 8.10 / 9.11** · Property 65 / 67

    边界④：candidate 登记前后，**真实调用**统一 resolver 的返回逐字段相同。

    这一条不是查 candidate 表 —— 只查表的守卫在「resolver 某天顺手把 candidate 当
    fallback」时照样绿。
    """

    def test_resolver_returns_the_same_identity(self, snap: dict[str, Any]) -> None:
        before = snap["resolver"]["before"]
        after = snap["resolver"]["after"]
        assert after == before, (
            "candidate 登记改变了 canonical resolver 的返回 —— candidate 永不可被 "
            f"resolver/room/download/current pointer/evidence 使用\n before={before}\n"
            f" after={after}"
        )

    def test_both_read_intents_were_actually_exercised(
        self, snap: dict[str, Any]
    ) -> None:
        """current-pointer 与 frozen-history 两条路径都必须真跑过（否则判据有盲区）。"""
        assert set(snap["resolver"]["after"]) == {"config", "history"}

    def test_resolver_never_returns_the_candidate_artifact(
        self, snap: dict[str, Any]
    ) -> None:
        for intent, resolved in snap["resolver"]["after"].items():
            assert ".upgrade-candidates" not in resolved["artifact_relative_path"], intent
            assert resolved["artifact_sha256"] != snap["candidate"][
                "staged_artifact_sha256"
            ], f"resolver({intent}) 返回了 candidate 的字节"

    def test_no_outbox_event_claims_a_content_change(self, snap: dict[str, Any]) -> None:
        """登记 candidate 不是业务内容变化 ⇒ 不得发出内容变更事件。"""
        assert snap["outbox_event_types"] == [], snap["outbox_event_types"]


class TestCandidateOnlySurfaceIsBlockedOnRealRepository:
    """在**真实** `WorkpaperSyncRepository` 上，四类写入面必须真的抛。"""

    def test_publication_surface_raises_with_its_own_error_code(
        self, snap: dict[str, Any]
    ) -> None:
        surface = snap["forbidden_surface"]
        assert set(surface) == {
            "create_representation",
            "set_entry_pointer",
            "finalize_candidate",
        }
        assert set(surface.values()) == {"candidate_stage_surface_forbidden"}


class TestAuthorityTemplateIsUntouched:
    def test_templates_are_byte_identical_after_the_run(
        self, snap: dict[str, Any]
    ) -> None:
        """Requirement 9.9：跑完 `backend/wp_templates/` 必须字节原样。"""
        assert snap["template_sha_before"]["F2-22"] == F222_SHA
        assert snap["template_sha_before"]["B30-11-2"] == B30112_SHA
        assert snap["template_sha_after"] == snap["template_sha_before"]

    def test_row_carrier_spec_is_still_declared(self, snap: dict[str, Any]) -> None:
        """行身份声明还在（否则「模板未变」可能是因为整段被删了）。"""
        assert snap["deficiency_spec_row_count"] == 3
        assert snap["gate"]["lock_policy"] == "no_w_lock_injected"
        assert snap["gate"]["onlyoffice_build"] == "9.4.0-129"
        assert DEF_ID
