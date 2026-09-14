# -*- coding: utf-8 -*-
"""Task 38 真实 PostgreSQL 守卫：纯 representation upgrade **不推进** content revision。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 38
Requirements: 3.4, 6.18, 8.10, 8.12
Properties: **P9** / **P65** / **P67**

═══ 为什么必须真库 + 真模板（不可 mock、不可 skip）═══

`RepresentationUpgradeOutcome.revision_delta == 0` 只是**声明**。Task 15 的
`ContentMutationService` / `RepresentationService` 才是 revision 的唯一权威，因此
「纯表示升级不增 revision」这条承诺必须**真实调用后查库**证明 —— 读
`working_paper.content_revision` 前后相等。只断言代码路径的守卫在「有人往
`representations.py` 里补一次 `bump_content_revision`」时照样绿。

Task 15 的 PG 套件已经用一个 **JSON 替身 adapter** 证明过 finalize 只加不改。本文件补的是
另一半：把 **Task 38 在真实权威模板上产出的 candidate 字节**喂进同一条真实发布链，证明

1. `plan_representation_upgrade` 自己**一次都没有**碰 revision（engine 侧零发布面）；
2. 真实 `finalize_candidate` 之后 `content_revision` 逐值不变，而 representation
   generation +1、绑定的仍是**同一个** content version（AC 6.18 的原话）；
3. outbox 事件里 `content_revision_advanced` 为假 —— 下游不得据此认为业务变了。

`DATABASE_URL` 非 PostgreSQL 时**直接失败而不是 skip**：静默 skip 会把本文件唯一的判据删掉，
留下一份「全绿」的假象。

═══ 隔离 ═══

scratch schema `tmp_task38_pg_*`，`search_path` 不含 public；文件全在系统临时目录。结束
`DROP SCHEMA CASCADE` + 删临时目录。**绝不触碰真实 `storage/` 与 `backend/wp_templates/`**
（后者跑完必须字节原样，由 `test_authority_template_is_untouched` 复核）。

═══ 采集写法 ═══

全部场景用**一次 `asyncio.run`** 跑完并落进快照（module fixture）。不给每个测试各自开
async —— 共享连接池会被污染，第二个测试起 `NoneType has no attribute send`。采集内部任何
异常都记进快照的 `errors`，由守卫断言为空（禁 fail-open）。
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

_SCHEMA_PREFIX = "tmp_task38_pg_"
ENTRY = "k11.adjudication"

# 🔴 复用 Task 15 PG 套件的 DDL / enum 工具与 Task 37/38 的真实模板 fixture：
#    两处都不抄第二份（抄一份就会出现「stub 表结构与生产不同」这类只在这里成立的绿）。
from test_task15_content_mutation_pg import (  # noqa: E402
    _STUB_DDL,
    _enum_ddl,
    _err,
)
from test_task38_excel_materialize import (  # noqa: E402
    TABLE_NAME,
    TEMPLATE,
    TEMPLATE_SHA,
    UUID_COL,
    label_cells,
)
from test_task37_excel_extract import (  # noqa: E402
    BINDING,
    CONTRACT_ID,
    FIRST_ROW,
    LAST_ROW,
    MANAGED_SHEET,
    SPEC,
    _d,
    _sheet_part_of,
    business_cells,
    contract_payload,
    make_definitions,
    patch_cells,
)


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：要守卫级，而不是降级成「无数据」）。"""


def _base_bytes() -> bytes:
    from app.services.workpaper_sync import excel_instrumentation as EI

    gate = EI.ExcelIdentityCarrierGate.load()
    instrumented = EI.instrument_workbook_bytes(
        TEMPLATE.read_bytes(), SPEC, gate=gate
    ).instrumented_bytes
    part = _sheet_part_of(instrumented, MANAGED_SHEET)
    cells: dict[str, Any] = dict(business_cells())
    cells.update(label_cells(unit_1="公司甲", unit_2="公司乙"))
    for row in range(FIRST_ROW, LAST_ROW + 1):
        cells[f"K{row}"] = 1000 + row
        cells[f"L{row}"] = 2000 + row
    return patch_cells(instrumented, part, cells)


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.dataset_models import ImportEventConsumption, ImportEventOutbox
    from app.services.excel_structure_fingerprint import identity_inventory
    from app.services import event_bus as event_bus_module
    from app.services.workpaper_sync import definitions as D
    from app.services.workpaper_sync import excel_rematerialize as RM
    from app.services.workpaper_sync import representations as R
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.contracts import parse_contract
    from app.services.workpaper_sync.models import (
        ArtifactKind,
        ArtifactState,
        BundleSlot,
        BundleSlotSpec,
        CandidateState,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "本文件的判据是「真实 finalize 之后查库 content_revision 不变」，依赖真实事务"
            f"语义与 V151；必须真实 PostgreSQL，当前为 {settings.DATABASE_URL.split('://')[0]}。"
            "此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task38_store_"))
    (base_root / "storage").mkdir()
    (base_root / "definition_store").mkdir()

    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "template_sha_before": hashlib.sha256(TEMPLATE.read_bytes()).hexdigest(),
        "apply_errors": [],
        "errors": [],
        "engine_side": {},
        "finalize": {},
        "outbox": {},
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
        contract = parse_contract(contract_payload(), adapter_id=CONTRACT_ID)
        base_bytes = _base_bytes()
        definitions = make_definitions(
            contract,
            identity_inventory(
                base_bytes, expected_table=TABLE_NAME, uuid_column_letter=UUID_COL
            ),
        )

        # ── 发布 generation 1：真实模板字节作为 current published representation ──
        gen1 = artifacts.publish_representation(
            entry_id=ENTRY,
            generation=1,
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=base_bytes, document_type="xlsx"
            ),
        )
        proj0 = artifacts.publish_projection(
            revision=0,
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp,
                payload=b"task38-projection-v0", document_type="json.gz",
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
                size_bytes=gen1.size_bytes, document_type="xlsx",
            )
            art_proj0 = await repo.register_artifact(
                project_id=project, wp_id=wp,
                kind=ArtifactKind.projection, state=ArtifactState.published,
                relative_path=proj0.relative_path, sha256=proj0.sha256,
                size_bytes=proj0.size_bytes, document_type="json.gz",
            )
            tpl = await repo.create_definition_artifact(
                kind="template", logical_id="task38.tpl", semantic_version="1.0.0",
                blob_artifact_id=art["tpl"].id,
                sha256=contract.template_definition_sha256,
                structure_hash=_d("task38-tpl-structure"), source_commit="task38",
            )
            instr = await repo.create_definition_artifact(
                kind="instrumentation", logical_id="task38.instr",
                semantic_version="1.0.0", blob_artifact_id=art["instr"].id,
                sha256=contract.instrumentation_definition_sha256,
                structure_hash=_d("task38-instr-structure"), source_commit="task38",
            )
            contract_def = await repo.create_definition_artifact(
                kind="contract", logical_id="task38.contract", semantic_version="1.0.0",
                blob_artifact_id=art["contract"].id,
                sha256=contract.canonical_sha256, source_commit="task38",
            )
            authority = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task38.authority",
                semantic_version="1.0.0", blob_artifact_id=art["authority"].id,
                sha256=_d("task38-authority"),
                authority_model_type="projection_contract", source_commit="task38",
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
                adapter_id=ENTRY, adapter_build_digest=_d("task38-adapter"),
                structure_hash=_d("task38-structure-1"),
                identity_inventory_sha256=_d("task38-identity-1"),
                reason="content_commit",
            )
            await repo.set_entry_pointer(
                wp_id=wp, entry_id=ENTRY, representation_id=rep1.id, generation=1
            )
            await repo.set_current_content_version(wp, cv0.id)
            await s.commit()
            world.update(
                {
                    "cv0": cv0.id, "rep1": rep1.id, "bundle": bundle.id,
                    "authority": authority.id, "contract_def": contract_def.id,
                    "tpl": tpl.id, "instr": instr.id,
                }
            )

        substrate = base_root / gen1.relative_path
        snap["substrate_exists"] = substrate.is_file()

        async def _revision(session: Any) -> int:
            row = (
                await session.execute(
                    sa.text("SELECT content_revision FROM working_paper WHERE id = :w"),
                    {"w": str(wp)},
                )
            ).first()
            return int(row[0])

        async def _generations(session: Any) -> list[dict[str, Any]]:
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT generation, content_version_id::text, artifact_sha256, "
                        "structure_hash, identity_inventory_sha256 "
                        "FROM working_paper_content_representation "
                        "WHERE wp_id = :w AND entry_id = :e ORDER BY generation"
                    ),
                    {"w": str(wp), "e": ENTRY},
                )
            ).all()
            return [
                {
                    "generation": int(r[0]),
                    "content_version_id": r[1],
                    "artifact_sha256": r[2],
                    "structure_hash": r[3],
                    "identity_inventory_sha256": r[4],
                }
                for r in rows
            ]

        # ── ① engine 侧：Task 38 的升级路径自己不碰 revision ─────────────
        async with Session() as s:
            snap["engine_side"]["revision_before_upgrade"] = await _revision(s)
        candidate_dir = base_root / "staging" / RM.CANDIDATE_NAMESPACE
        candidate_dir.mkdir(parents=True, exist_ok=True)
        try:
            upgrade = RM.plan_representation_upgrade(
                current_representation=substrate,
                candidate_output=candidate_dir / "k11-upgrade.xlsx",
                definitions=definitions,
                binding=BINDING,
            )
            snap["engine_side"].update(
                revision_delta=upgrade.revision_delta,
                business_projection_unchanged=upgrade.business_projection_unchanged,
                before_digest=upgrade.before_projection_digest,
                after_digest=upgrade.after_projection_digest,
                candidate_path=str(upgrade.candidate_path),
                structure_hash=upgrade.rematerialize.materialize.result.structure_hash,
                identity_inventory_sha256=(
                    upgrade.rematerialize.materialize.result.identity_inventory_sha256
                ),
                publishable=upgrade.rematerialize.publishable,
            )
        except Exception as exc:  # noqa: BLE001
            snap["errors"].append(f"plan_representation_upgrade: {_err(exc)}")
            raise
        async with Session() as s:
            snap["engine_side"]["revision_after_upgrade"] = await _revision(s)

        # ── ② 把 Task 38 的 candidate 字节交给真实发布链 ────────────────
        candidate_bytes = upgrade.candidate_path.read_bytes()
        cand_staged = artifacts.stage_upgrade_candidate(
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp,
                payload=candidate_bytes, document_type="xlsx",
            ),
            entry_id=ENTRY,
            equivalence_report=json.dumps(
                {
                    "equivalent": True,
                    "before": upgrade.before_projection_digest,
                    "after": upgrade.after_projection_digest,
                },
                sort_keys=True,
            ).encode(),
        )
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            cand_art = await repo.register_artifact(
                project_id=project, wp_id=wp,
                kind=ArtifactKind.upgrade_candidate, state=ArtifactState.candidate,
                relative_path=cand_staged.relative_path, sha256=cand_staged.sha256,
                size_bytes=cand_staged.size_bytes, document_type="xlsx",
                retention_class="candidate",
            )
            candidate = await repo.create_upgrade_candidate(
                project_id=project, wp_id=wp, entry_id=ENTRY,
                content_version_id=world["cv0"],
                source_representation_id=world["rep1"],
                staged_artifact_id=cand_art.id,
                staged_artifact_sha256=cand_art.sha256,
                template_definition_id=world["tpl"],
                instrumentation_definition_id=world["instr"],
                state=CandidateState.awaiting_contract,
            )
            await s.commit()
            world["candidate"] = candidate.id
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
                    "c": str(world["contract_def"]),
                    "b": str(world["bundle"]),
                    # 🔴 用 `stage_upgrade_candidate` 实际落盘的等值报告 digest，不是随手造一个：
                    #    这一列是「candidate 与 current 的可见结构/projection 等值报告」的
                    #    内容寻址身份（AC 6.18），造假会让 finalize 门失去可核对的依据。
                    "e": cand_staged.equivalence_sha256,
                    "i": str(world["candidate"]),
                },
            )
            await s.commit()

        async with Session() as s:
            snap["finalize"]["before"] = {
                "content_revision": await _revision(s),
                "generations": await _generations(s),
            }
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            rep_svc = R.RepresentationService(
                session=s,
                repository=repo,
                artifacts=artifacts,
                resolution=CanonicalResolutionService(s, artifacts),
            )
            try:
                outcome = await rep_svc.finalize_candidate(
                    project_id=project,
                    candidate_id=world["candidate"],
                    staged_candidate=cand_staged,
                    adapter_id=ENTRY,
                    adapter_build_digest=_d("task38-adapter"),
                    structure_hash=snap["engine_side"]["structure_hash"],
                    identity_inventory_sha256=snap["engine_side"][
                        "identity_inventory_sha256"
                    ],
                )
                snap["finalize"]["outcome"] = {
                    "generation": getattr(outcome, "generation", None),
                    "representation_id": str(
                        getattr(outcome, "representation_id", "")
                    ),
                }
            except Exception as exc:  # noqa: BLE001
                snap["errors"].append(f"finalize_candidate: {_err(exc)}")
        async with Session() as s:
            snap["finalize"]["after"] = {
                "content_revision": await _revision(s),
                "generations": await _generations(s),
            }
            rows = (
                await s.execute(
                    sa.text(
                        "SELECT event_type, payload::text FROM import_event_outbox "
                        "ORDER BY created_at"
                    )
                )
            ).all()
            snap["outbox"]["events"] = [
                {"event_type": r[0], "payload": r[1]} for r in rows
            ]
        snap["template_sha_after"] = hashlib.sha256(TEMPLATE.read_bytes()).hexdigest()
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
        assert snap["substrate_exists"] is True

    def test_authority_template_is_untouched(self, snap: dict[str, Any]) -> None:
        """跑完模板库字节必须原样（Requirement 9.9）。"""
        assert snap["template_sha_before"] == TEMPLATE_SHA
        assert snap["template_sha_after"] == TEMPLATE_SHA


class TestEngineSideDoesNotTouchRevision:
    """**Validates: Requirements 6.18** · Property 4 / 67

    Task 38 的升级路径**自己**不碰 revision —— 判据是查库前后相等，不是「代码里没写
    bump」。
    """

    def test_upgrade_reports_zero_revision_delta(self, snap: dict[str, Any]) -> None:
        engine_side = snap["engine_side"]
        assert engine_side["revision_delta"] == 0
        assert engine_side["business_projection_unchanged"] is True
        assert engine_side["before_digest"] == engine_side["after_digest"]
        assert engine_side["publishable"] is True

    def test_database_revision_is_unchanged_by_the_engine(
        self, snap: dict[str, Any]
    ) -> None:
        engine_side = snap["engine_side"]
        assert engine_side["revision_after_upgrade"] == engine_side[
            "revision_before_upgrade"
        ], (
            "engine 自己推进了 content revision —— materialize/rematerialize 必须零发布面，"
            f"{engine_side['revision_before_upgrade']} → "
            f"{engine_side['revision_after_upgrade']}"
        )

    def test_candidate_lands_in_the_candidate_namespace(
        self, snap: dict[str, Any]
    ) -> None:
        from app.services.workpaper_sync import excel_rematerialize as RM

        assert RM.CANDIDATE_NAMESPACE in Path(
            snap["engine_side"]["candidate_path"]
        ).parts


class TestFinalizeIsAdditiveOnly:
    """**Validates: Requirements 6.18 / 8.12** · Property 67

    真实 `finalize_candidate` 之后：revision 逐值不变、generation +1、绑定同一个 content
    version、artifact digest 是 Task 38 那份 candidate 的 digest。
    """

    def test_content_revision_is_unchanged(self, snap: dict[str, Any]) -> None:
        before = snap["finalize"]["before"]["content_revision"]
        after = snap["finalize"]["after"]["content_revision"]
        assert after == before, (
            f"纯 representation upgrade 推进了 content revision：{before} → {after} —— "
            "AC 6.18 明文要求业务 projection 未变时 content_revision 保持不变"
        )

    def test_a_new_generation_is_added_for_the_same_content_version(
        self, snap: dict[str, Any]
    ) -> None:
        before = snap["finalize"]["before"]["generations"]
        after = snap["finalize"]["after"]["generations"]
        assert [g["generation"] for g in before] == [1], before
        assert [g["generation"] for g in after] == [1, 2], after
        assert after[0] == before[0], "旧 representation row 被原地改写了（immutable 失守）"
        assert after[1]["content_version_id"] == before[0]["content_version_id"], (
            "新 generation 绑到了另一个 content version —— finalize 只为**既有** version "
            "加 generation"
        )

    def test_the_published_generation_carries_task38_identity(
        self, snap: dict[str, Any]
    ) -> None:
        """新 generation 的 structure_hash / identity 清册 digest 来自 Task 38 的实测产物。"""
        after = snap["finalize"]["after"]["generations"][1]
        assert after["structure_hash"] == snap["engine_side"]["structure_hash"]
        assert after["identity_inventory_sha256"] == snap["engine_side"][
            "identity_inventory_sha256"
        ]
        assert after["structure_hash"] != snap["finalize"]["before"]["generations"][0][
            "structure_hash"
        ], "新旧 generation 的 structure_hash 相同 ⇒ 本判据没有区分力"

    def test_outbox_event_says_revision_did_not_advance(
        self, snap: dict[str, Any]
    ) -> None:
        events = snap["outbox"]["events"]
        assert events, "finalize 没有发出任何 outbox 事件 —— 下游无从感知新 generation"
        payloads = [
            event["payload"].replace(
                '"content_revision_advanced":false',
                '"content_revision_advanced": false',
            )
            for event in events
        ]
        assert any(
            '"content_revision_advanced": false' in payload for payload in payloads
        ), f"outbox 事件没有声明 revision 未推进: {payloads[:2]}"
