# -*- coding: utf-8 -*-
"""Task 17 真实 PostgreSQL 守卫：non-current candidate 的**否定式承诺**逐条可 falsify。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 17
Requirements: 2.1, 2.3, 6.10, 6.13, 6.18, 6.19, 9.1, 9.8, 9.9, 9.10, 14.16
Properties: **P28**（definition 漂移 fail closed）/ **P66**（只用探针通过的载体）/
            **P67**（先 candidate、approved bundle 后 finalize）/ **P71**（evidence stale）

═══ 为什么这一档非真库不可 ═══

本任务的验收项**全部是否定式**：

* 「不得创建 published/current representation」
* 「不得切 entry pointer」
* 「不得递增 content revision」
* 「candidate 不得进入 resolver / room / download / current / evidence」
* 「不得伪造 per-entry contract / authority model / definition bundle」
* 「不得修改既有 representation / content version row」
* 「缺 approved child 时 candidate 停在不可见状态」

纯域 mock 里这些**全部恒真** —— 没有 representation 表可写、没有 pointer 可切、
没有 revision 可加，于是「我没做」和「我做不到」无法区分，判据空转。这正是
`test_task15_content_mutation_pg.py` docstring 记的同一个陷阱。

因此本文件的判据都不依赖被测代码自己的返回值：

1. **`xmin` 是独立于本代码的「行没被重写」判据。** PostgreSQL 为每个行版本记录写它的
   事务 id；既有 `working_paper` / content_version / representation / entry_state 四行的
   `xmin` 在 upgrader 跑完前后**逐行相等**，才证明没有一行被 UPDATE 过。这条不经过
   `UpgradeCandidateOutcome`（那是我们自己算的），所以「outcome 里的比较逻辑被改坏」
   不会让它假绿。

2. **全 schema uuid 列反向清扫**是「candidate 没进入任何地方」的结构判据。枚举
   `information_schema` 里**全部** uuid 列，逐列查是否等于 candidate id / staged
   artifact id；允许命中的位置写成白名单。往 `working_paper_sync_entry_state.
   current_representation_id` 塞 candidate id 会立刻越出白名单打红 —— 不需要预先知道
   「未来会有哪张表」，新表自动纳入分母。

3. **`set(ResolutionIntent)` 全枚举**：十个意图逐个断言 `assert_candidate_not_consumable`
   恒抛。将来新增第十一个意图而忘了拒绝 candidate 时，枚举分母自己变大 ⇒ 缺口可见。

4. **definition / bundle 行数按 delta 判**：baseline 播种本身要发布一个 approved bundle
   （否则 `create_representation` 过不了 `assert_bundle_usable`），所以绝对计数没意义；
   判据是 upgrader 跑完的**增量**恰为 `template +1 / instrumentation +1 /
   contract +0 / authority_model +0 / bundle +0`。

═══ 隔离 ═══

scratch schema `tmp_task17_ei_*`、`search_path` 不含 public；`projects/users/
working_paper` 建桩表，其余从 V151 建。文件全在系统临时目录，**绝不触碰真实
`storage/`**。`backend/wp_templates/` 只读（收工重算 sha256）。结束
`DROP SCHEMA CASCADE` + 删临时目录。

`DATABASE_URL` 非 PostgreSQL 时**直接失败不 skip**：静默 skip 会把本任务唯一的真判据
删掉，只留一份「全绿」的假象。

═══ 采集写法（Task 15 复盘第 3 条）═══

全部场景由**一次 `asyncio.run`** 跑完并落进 module 级快照；不给每个测试各自开 async
（共享连接池会被污染，第二个测试起 `NoneType has no attribute send`）。采集内部异常
记进 `snap["errors"]` 并返回**部分**快照，由 `test_no_harness_errors` 断言其为空 ——
既不 fail-open（有专门守卫盯着），又能被变异的失败名差集看见（ERROR 不进 `-rf` 摘要）。
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

_SCHEMA_PREFIX = "tmp_task17_ei_"

#: Task 5 真实容器的 dpkg 取证（build 字面量的最终溯源点，不在生产部署里）。
_OO_BUILD_EVIDENCE = (
    _REPO
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "evidence"
    / "task5-oo94-excel-identity"
    / "oo_build.json"
)

ENTRY = "k11.adjudication"

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

#: 既有行「没被重写」的四张表（`xmin` 逐行相等即证明未 UPDATE）。
_IMMUTABLE_ROW_PROBES: tuple[tuple[str, str], ...] = (
    ("working_paper", "id = :wp"),
    ("working_paper_content_version", "wp_id = :wp"),
    ("working_paper_content_representation", "wp_id = :wp"),
    ("working_paper_sync_entry_state", "wp_id = :wp"),
)

#: candidate id 允许出现的 (表, uuid 列)。其余任何 uuid 列命中即越界。
#:
#: `working_paper_sync_scope_index.resource_id` 是 varchar 而非 uuid，故不在本白名单，
#: 由 `scope_index` 那一节单独断言 —— 它是**应当**存在的一行（授权定位需要）。
_CANDIDATE_ID_ALLOWED: frozenset[tuple[str, str]] = frozenset(
    {("working_paper_representation_upgrade_candidate", "id")}
)

#: staged candidate artifact id 允许出现的位置：artifact 行本体 + candidate 的引用。
_STAGED_ARTIFACT_ID_ALLOWED: frozenset[tuple[str, str]] = frozenset(
    {
        ("working_paper_artifact", "id"),
        ("working_paper_representation_upgrade_candidate", "staged_artifact_id"),
    }
)

#: Task 5 findings.md §1 记录的权威源 digest（收工必须仍是这两个值）。
AUTHORITY_TEMPLATE_SHA: dict[str, str] = {
    "K/K11 资产减值损失.xlsx": (
        "dc0e5434b7c8e345913864ce524ad30a0a3729b5655627f3c30bce52294a9190"
    ),
    "C/C24 会计分录 - 细节测试.xlsx": (
        "b70229f48c13a635595b13f74aa199cb2d96ed1106a1661a66cecb7e6e87d5c6"
    ),
}


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成「无数据」）。"""


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# 采集
# ═══════════════════════════════════════════════════════════════════════════
async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - 一次采集覆盖全部场景
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.services.workpaper_sync import definitions as D
    from app.services.workpaper_sync import excel_instrumentation as EI
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.models import (
        ArtifactKind,
        ArtifactState,
        BundleSlot,
        BundleSlotSpec,
        CandidateState,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import (
        CandidateNotFinalizableError,
        CandidateNotResolvableError,
        CanonicalResolutionService,
        ResolutionIntent,
    )

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 17 的判据是「candidate 不进 resolver/pointer/current、revision 不动、"
            "既有行 xmin 不变、bundle 零增量」，全部依赖真实表与 V151 的 CHECK/trigger；"
            f"必须真实 PostgreSQL，当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    spec = EI.ExcelInstrumentationSpec(
        entry_id=ENTRY,
        template_id="K11",
        template_relative_path="K/K11 资产减值损失.xlsx",
        managed_sheet="审定表K11-1",
        first_data_row=7,
        last_data_row=25,
        footer_row=26,
        managed_last_col="L",
        uuid_col="N",
        table_name="GT_K11_1_ROWS",
    )

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task17_store_"))
    (base_root / "storage").mkdir()
    (base_root / "definition_store").mkdir()

    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "server_version": None,
        "apply_errors": [],
        "errors": [],
        "world": {},
        "gate": {},
        "source_sha_before": {},
        "source_sha_after": {},
        "publish_dag": {},
        "definitions_delta": {},
        "before": {},
        "after": {},
        "xmin": {},
        "candidate_row": {},
        "candidate_artifact": {},
        "outcome": {},
        "id_sweep": {},
        "scope_index": {},
        "resolver": {},
        "finalize_gate": {},
        "forbidden_surface": {},
    }
    engine = None
    try:
        # ── 开工先核权威源未被改（Requirement 9.9）─────────────────────────
        for rel, expected in AUTHORITY_TEMPLATE_SHA.items():
            path = _BACKEND / "wp_templates" / rel
            snap["source_sha_before"][rel] = hashlib.sha256(path.read_bytes()).hexdigest()
            snap["world"][f"expected_sha::{rel}"] = expected

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
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{project}')")
            await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{user}')")
            await conn.exec_driver_sql(
                f"INSERT INTO working_paper (id, project_id) VALUES ('{wp}', '{project}')"
            )

        artifacts = CanonicalArtifactRepository(base_root)
        gate = EI.ExcelIdentityCarrierGate.load()
        snap["gate"] = {
            "contract_sha256": gate.contract_sha256,
            "onlyoffice_build": gate.onlyoffice_build,
            "allowed_carriers": sorted(gate.allowed_carriers),
            "allowed_anchors": sorted(gate.allowed_anchors),
            "forbidden_anchors": sorted(gate.forbidden_anchors),
        }

        template_path = gate.assert_template_under_authority(spec.template_relative_path)
        template_bytes = template_path.read_bytes()

        # ── baseline 播种：存量（未 instrumentation 的）representation gen 1 ────
        #    「存量 artifact」就是原始模板字节 —— 与生产实况一致（旧底稿由模板生成）。
        blobs = {
            name: artifacts.publish_definition_blob(
                project_id=project, wp_id=wp, definition_kind=kind,
                payload=f'{{"seed":"{name}"}}'.encode("utf-8"),
            )
            for name, kind in {
                "seed_tpl": "template",
                "seed_instr": "instrumentation",
                "seed_contract": "contract",
                "seed_authority": "authority_model",
                "seed_bundle": "bundle",
            }.items()
        }
        gen1 = artifacts.publish_representation(
            entry_id=ENTRY,
            generation=1,
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=template_bytes,
                document_type="xlsx",
            ),
        )
        proj0 = artifacts.publish_projection(
            revision=0,
            staged=artifacts.stage_bytes(
                project_id=project, wp_id=wp, payload=b"task17-projection-v0",
                document_type="json.gz",
            ),
        )

        world: dict[str, Any] = {}
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            art = {
                name: await repo.register_artifact(
                    project_id=project, wp_id=wp,
                    kind=ArtifactKind.definition, state=ArtifactState.published,
                    relative_path=pub.relative_path, sha256=pub.sha256,
                    size_bytes=pub.size_bytes, document_type=pub.document_type,
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
            seed_tpl = await repo.create_definition_artifact(
                kind="template", logical_id="task17.seed.tpl", semantic_version="0.9.0",
                blob_artifact_id=art["seed_tpl"].id, sha256=_d("task17-seed-template"),
                structure_hash=_d("task17-seed-structure"), source_commit="task17-seed",
            )
            seed_instr = await repo.create_definition_artifact(
                kind="instrumentation", logical_id="task17.seed.instr",
                semantic_version="0.9.0", blob_artifact_id=art["seed_instr"].id,
                sha256=_d("task17-seed-instrumentation"), source_commit="task17-seed",
            )
            seed_contract = await repo.create_definition_artifact(
                kind="contract", logical_id="task17.seed.contract",
                semantic_version="0.9.0", blob_artifact_id=art["seed_contract"].id,
                sha256=_d("task17-seed-contract"), source_commit="task17-seed",
            )
            seed_authority = await repo.create_definition_artifact(
                kind="authority_model", logical_id="task17.seed.authority",
                semantic_version="0.9.0", blob_artifact_id=art["seed_authority"].id,
                sha256=_d("task17-seed-authority"),
                authority_model_type="projection_contract", source_commit="task17-seed",
            )

            def _seed_slots() -> dict[BundleSlot, BundleSlotSpec]:
                return {
                    BundleSlot.template: D.definition_slot_spec(
                        BundleSlot.template,
                        definition_id=seed_tpl.id, definition_sha256=seed_tpl.sha256,
                    ),
                    BundleSlot.instrumentation: D.definition_slot_spec(
                        BundleSlot.instrumentation,
                        definition_id=seed_instr.id, definition_sha256=seed_instr.sha256,
                    ),
                    BundleSlot.contract: D.definition_slot_spec(
                        BundleSlot.contract,
                        definition_id=seed_contract.id,
                        definition_sha256=seed_contract.sha256,
                    ),
                }

            seed_bundle = await repo.create_definition_bundle(
                authority_model_definition_id=seed_authority.id,
                slots=_seed_slots(),
                canonical_payload_artifact_id=art["seed_bundle"].id,
                canonical_payload_sha256=D.bundle_canonical_digest(
                    authority_model="projection_contract",
                    authority_model_definition_sha256=seed_authority.sha256,
                    slots=_seed_slots(),
                ),
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
                definition_bundle_id=seed_bundle.id,
                authority_model_definition_id=seed_authority.id,
                adapter_id=ENTRY, adapter_build_digest=_d("task17-seed-adapter"),
                structure_hash=_d("task17-seed-structure-1"),
                identity_inventory_sha256=_d("task17-seed-identity-1"),
                reason="content_commit",
            )
            await repo.set_entry_pointer(
                wp_id=wp, entry_id=ENTRY, representation_id=rep1.id, generation=1
            )
            await repo.set_current_content_version(wp, cv0.id)
            await s.commit()
            world.update({
                "cv0": cv0.id, "rep1": rep1.id, "seed_bundle": seed_bundle.id,
                "seed_authority": seed_authority.id, "gen1_rel": gen1.relative_path,
            })

        # ── 快照工具 ───────────────────────────────────────────────────────
        async def _state(session) -> dict[str, Any]:
            revision = (
                await session.execute(
                    sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"),
                    {"wp": str(wp)},
                )
            ).scalar_one()
            current_cv = (
                await session.execute(
                    sa.text(
                        "SELECT current_content_version_id FROM working_paper "
                        "WHERE id = :wp"
                    ),
                    {"wp": str(wp)},
                )
            ).scalar_one()
            pointer = (
                await session.execute(
                    sa.text(
                        "SELECT current_representation_id, representation_generation "
                        "FROM working_paper_sync_entry_state "
                        "WHERE wp_id = :wp AND entry_id = :e"
                    ),
                    {"wp": str(wp), "e": ENTRY},
                )
            ).first()
            counts = {}
            for table in (
                "working_paper_content_representation",
                "working_paper_content_version",
                "working_paper_representation_upgrade_candidate",
            ):
                counts[table] = int(
                    (
                        await session.execute(
                            sa.text(f"SELECT count(*) FROM {table} WHERE wp_id = :wp"),
                            {"wp": str(wp)},
                        )
                    ).scalar_one()
                )
            return {
                "content_revision": int(revision),
                "current_content_version_id": str(current_cv) if current_cv else None,
                "pointer_representation_id": str(pointer[0]) if pointer else None,
                "pointer_generation": int(pointer[1]) if pointer else None,
                "counts": counts,
            }

        async def _definition_census(session) -> dict[str, int]:
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT kind, count(*) FROM working_paper_sync_definition_artifact "
                        "GROUP BY kind"
                    )
                )
            ).all()
            out = {str(k): int(c) for k, c in rows}
            out["bundle"] = int(
                (
                    await session.execute(
                        sa.text("SELECT count(*) FROM working_paper_sync_definition_bundle")
                    )
                ).scalar_one()
            )
            return out

        async def _xmin_snapshot(session) -> dict[str, list[list[str]]]:
            out: dict[str, list[list[str]]] = {}
            for table, where in _IMMUTABLE_ROW_PROBES:
                rows = (
                    await session.execute(
                        sa.text(
                            f"SELECT id::text, xmin::text FROM {table} WHERE {where} "
                            "ORDER BY id"
                        )
                        if table != "working_paper_sync_entry_state"
                        else sa.text(
                            f"SELECT entry_id, xmin::text FROM {table} WHERE {where} "
                            "ORDER BY entry_id"
                        ),
                        {"wp": str(wp)},
                    )
                ).all()
                out[table] = [[str(a), str(b)] for a, b in rows]
            return out

        async with Session() as s:
            snap["before"] = await _state(s)
            snap["xmin"]["before"] = await _xmin_snapshot(s)
            snap["definitions_delta"]["before"] = await _definition_census(s)

        # ── DAG 顺序：instrumentation 先发 ⇒ 必须被真实服务拒绝（P28 / R 9.8）──
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            publisher = D.DefinitionPublisher(
                artifacts=artifacts, repository=repo, project_id=project, wp_id=wp,
                source_commit="task17-dag-probe",
            )
            payload = EI.build_instrumentation_payload(
                spec=spec,
                template_definition_sha256=_d("task17-not-yet-published-template"),
                template_sha256=hashlib.sha256(template_bytes).hexdigest(),
                gate=gate,
            )
            try:
                await publisher.publish_definition(
                    kind="instrumentation", payload=payload,
                    logical_id="task17.dag.probe", semantic_version="1.0.0",
                )
                snap["publish_dag"]["instrumentation_first"] = "NO ERROR"
            except D.PublishOrderError as exc:
                snap["publish_dag"]["instrumentation_first"] = _err(exc)
            except Exception as exc:  # noqa: BLE001
                snap["publish_dag"]["instrumentation_first"] = f"WRONG-TYPE {_err(exc)}"
            await s.rollback()

        # ── 真跑 upgrader：publish definitions → 注入 → 登记 candidate ────────
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            upgrader = EI.ExcelInstrumentationUpgrader(
                session=s, repository=repo, artifacts=artifacts,
                project_id=project, source_commit="task17-pg",
            )
            tpl_def, instr_def, instr_payload = await upgrader.publish_definitions(
                spec=spec, wp_id=wp, template_bytes=template_bytes
            )
            instrumented, equivalence, inventory = upgrader.instrument_source_bytes(
                source=template_bytes, spec=spec
            )
            outcome = await upgrader.stage_and_register_candidate(
                spec=spec, wp_id=wp, content_version_id=cv0.id,
                source_representation_id=rep1.id, source_bytes=template_bytes,
                instrumented=instrumented, equivalence=equivalence, inventory=inventory,
                template_definition=tpl_def, instrumentation_definition=instr_def,
                from_definition_bundle_id=seed_bundle.id,
                from_definition_bundle_sha256=seed_bundle.canonical_payload_sha256,
                actor_id=user,
            )
            await s.commit()

        snap["outcome"] = {
            k: (str(v) if isinstance(v, uuid.UUID) else v)
            for k, v in outcome.as_dict().items()
        }
        snap["outcome"]["state"] = outcome.state.value
        snap["outcome"]["revision_unchanged"] = outcome.revision_unchanged
        snap["outcome"]["pointer_unchanged"] = outcome.pointer_unchanged
        snap["outcome"]["no_representation_created"] = outcome.no_representation_created
        snap["world"].update({
            "candidate": str(outcome.candidate_id),
            "staged_artifact": str(outcome.staged_artifact_id),
            "template_definition": str(outcome.template_definition_id),
            "instrumentation_definition": str(outcome.instrumentation_definition_id),
            "rep1": str(rep1.id),
            "cv0": str(cv0.id),
            "seed_bundle": str(seed_bundle.id),
            "gen1_rel": str(world["gen1_rel"]),
        })
        snap["instrumentation_payload_keys"] = sorted(instr_payload)

        # ── 事后测量（全部走 fresh session + 裸 SQL）────────────────────────
        async with Session() as s:
            snap["after"] = await _state(s)
            snap["xmin"]["after"] = await _xmin_snapshot(s)
            snap["definitions_delta"]["after"] = await _definition_census(s)

            cand = (
                await s.execute(
                    sa.text(
                        "SELECT state, target_contract_definition_id::text, "
                        "       target_definition_bundle_id::text, "
                        "       template_definition_id::text, "
                        "       instrumentation_definition_id::text, "
                        "       source_representation_id::text, content_version_id::text, "
                        "       staged_artifact_sha256, visible_equivalence_report_sha256, "
                        "       rollback_source_sha256, finalized_at::text "
                        "FROM working_paper_representation_upgrade_candidate WHERE id = :c"
                    ),
                    {"c": str(outcome.candidate_id)},
                )
            ).mappings().one()
            snap["candidate_row"] = dict(cand)

            art_row = (
                await s.execute(
                    sa.text(
                        "SELECT kind, state, relative_path, sha256, document_type "
                        "FROM working_paper_artifact WHERE id = :a"
                    ),
                    {"a": str(outcome.staged_artifact_id)},
                )
            ).mappings().one()
            snap["candidate_artifact"] = dict(art_row)

            # ── 全 schema uuid 列反向清扫 ─────────────────────────────────
            uuid_cols = (
                await s.execute(
                    sa.text(
                        "SELECT table_name, column_name FROM information_schema.columns "
                        "WHERE table_schema = :s AND data_type = 'uuid' "
                        "ORDER BY table_name, column_name"
                    ),
                    {"s": schema},
                )
            ).all()
            snap["id_sweep"]["uuid_column_count"] = len(uuid_cols)
            for label, target, allowed in (
                ("candidate", outcome.candidate_id, _CANDIDATE_ID_ALLOWED),
                ("staged_artifact", outcome.staged_artifact_id, _STAGED_ARTIFACT_ID_ALLOWED),
            ):
                hits: list[list[str]] = []
                for table_name, column_name in uuid_cols:
                    n = int(
                        (
                            await s.execute(
                                sa.text(
                                    f'SELECT count(*) FROM "{table_name}" '
                                    f'WHERE "{column_name}" = :t'
                                ),
                                {"t": str(target)},
                            )
                        ).scalar_one()
                    )
                    if n:
                        hits.append([str(table_name), str(column_name), str(n)])
                snap["id_sweep"][label] = {
                    "hits": hits,
                    "unexpected": sorted(
                        f"{t}.{c}" for t, c, _ in hits if (t, c) not in allowed
                    ),
                    "allowed": sorted(f"{t}.{c}" for t, c in allowed),
                }

            scope_rows = (
                await s.execute(
                    sa.text(
                        "SELECT resource_kind, entry_id, retired_at::text "
                        "FROM working_paper_sync_scope_index WHERE resource_id = :r"
                    ),
                    {"r": str(outcome.candidate_id)},
                )
            ).mappings().all()
            snap["scope_index"] = [dict(r) for r in scope_rows]

            # ── resolver：十个意图逐个恒抛 + candidate id 不可解析 ────────────
            svc = CanonicalResolutionService(s, artifacts)
            snap["resolver"]["intents_declared"] = sorted(i.value for i in ResolutionIntent)
            not_consumable: dict[str, str] = {}
            for intent in ResolutionIntent:
                try:
                    await svc.assert_candidate_not_consumable(
                        candidate_id=outcome.candidate_id, intent=intent
                    )
                    not_consumable[intent.value] = "NO ERROR"
                except CandidateNotResolvableError as exc:
                    not_consumable[intent.value] = _err(exc)
                except Exception as exc:  # noqa: BLE001
                    not_consumable[intent.value] = f"WRONG-TYPE {_err(exc)}"
            snap["resolver"]["not_consumable"] = not_consumable

            frozen_identity_resolve: dict[str, str] = {}
            for intent in ResolutionIntent:
                try:
                    await svc.resolve(
                        intent=intent, project_id=project, wp_id=wp, entry_id=ENTRY,
                        representation_id=outcome.candidate_id,
                    )
                    frozen_identity_resolve[intent.value] = "NO ERROR"
                except CandidateNotResolvableError as exc:
                    frozen_identity_resolve[intent.value] = _err(exc)
                except Exception as exc:  # noqa: BLE001
                    frozen_identity_resolve[intent.value] = f"WRONG-TYPE {_err(exc)}"
            snap["resolver"]["resolve_with_candidate_id"] = frozen_identity_resolve

            current = await svc.resolve(
                intent=ResolutionIntent.config, project_id=project, wp_id=wp,
                entry_id=ENTRY,
            )
            snap["resolver"]["current"] = {
                "representation_id": str(current.representation_id),
                "generation": current.representation_generation,
                "revision": current.content_revision,
                "artifact_sha256": current.artifact_sha256,
                # 🔴 bundle 身份挂在 `CanonicalResolution.bundle`（Task 12 的
                #    `DefinitionBundleSnapshot`）上，不是 resolution 的平铺字段 ——
                #    写成 `current.definition_bundle_id` 会 AttributeError，而
                #    `_collect()` 的 except 会把它记进 `snap["errors"]`，
                #    于是 `test_no_harness_errors` 打红（不是静默无数据）。
                "definition_bundle_id": str(current.bundle.bundle_id),
                "definition_bundle_sha256": current.bundle.bundle_sha256,
            }

            try:
                await svc.assert_candidate_finalizable(outcome.candidate_id)
                snap["finalize_gate"]["awaiting_contract"] = "NO ERROR"
            except CandidateNotFinalizableError as exc:
                snap["finalize_gate"]["awaiting_contract"] = _err(exc)
            except Exception as exc:  # noqa: BLE001
                snap["finalize_gate"]["awaiting_contract"] = f"WRONG-TYPE {_err(exc)}"

        # ── 门面禁令：对**真** repository 逐个调用禁用方法 ────────────────────
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            upgrader = EI.ExcelInstrumentationUpgrader(
                session=s, repository=repo, artifacts=artifacts,
                project_id=project, source_commit="task17-pg-surface",
            )
            calls: dict[str, str] = {}
            for method in sorted(EI.CANDIDATE_FORBIDDEN_METHODS):
                try:
                    getattr(upgrader.repository, method)
                    calls[method] = "NO ERROR"
                except EI.CandidateSurfaceForbiddenError as exc:
                    calls[method] = _err(exc)
                except Exception as exc:  # noqa: BLE001
                    calls[method] = f"WRONG-TYPE {_err(exc)}"
            snap["forbidden_surface"] = {
                "calls": calls,
                "real_repository": type(repo).__name__,
                "wrapped": type(upgrader.repository).__name__,
            }
            # 门面透传的方法照旧可用（证明它不是把整个仓储禁掉）
            snap["forbidden_surface"]["passthrough_ok"] = callable(
                getattr(upgrader.repository, "create_upgrade_candidate")
            )
            await s.rollback()

        # 门面拒绝之后，representation 计数仍为 1（拒绝不是「抛了但也写了」）
        async with Session() as s:
            snap["forbidden_surface"]["state_after"] = await _state(s)

        # ── 收工核权威源 ────────────────────────────────────────────────────
        for rel in AUTHORITY_TEMPLATE_SHA:
            path = _BACKEND / "wp_templates" / rel
            snap["source_sha_after"][rel] = hashlib.sha256(path.read_bytes()).hexdigest()

    except Exception as exc:  # noqa: BLE001
        # 🔴 不是 fail-open：`test_no_harness_errors` 专门断言这里为空。
        #    Task 15 复盘第 3 条 —— 采集异常必须让守卫「打红」而不是让全部用例 ERROR。
        snap["errors"].append(_err(exc))
    finally:
        try:
            if engine is not None:
                await engine.dispose()
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except Exception as exc:  # noqa: BLE001
            snap["errors"].append(f"cleanup: {_err(exc)}")
        finally:
            await admin.dispose()
            shutil.rmtree(base_root, ignore_errors=True)
    return snap


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


# ═══════════════════════════════════════════════════════════════════════════
# 0. 采集完整性（必须第一个看）
# ═══════════════════════════════════════════════════════════════════════════
class TestHarness:
    def test_no_harness_errors(self, snap: dict[str, Any]) -> None:
        """采集自身零异常。**没有这条，其余判据的「无数据」会被读成「通过」。**"""
        assert snap["errors"] == [], snap["errors"]

    def test_ran_on_real_postgres(self, snap: dict[str, Any]) -> None:
        assert snap["server_version"] and "PostgreSQL" in snap["server_version"]
        assert snap["apply_errors"] == []

    def test_baseline_world_is_meaningful(self, snap: dict[str, Any]) -> None:
        """播种必须真的形成 published representation + pointer + current version。

        pointer 为空 / representation 计数为 0 时，「pointer 没被切」「没新增
        representation」两条判据会在空集上恒真 —— 假绿第③源。
        """
        before = snap["before"]
        assert before["pointer_representation_id"] == snap["world"]["rep1"]
        assert before["pointer_generation"] == 1
        assert before["counts"]["working_paper_content_representation"] == 1
        assert before["counts"]["working_paper_content_version"] == 1
        assert before["current_content_version_id"] == snap["world"]["cv0"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. 三条 pointer/revision/representation 否定式承诺（P67 / R 2.1 / 9.10）
# ═══════════════════════════════════════════════════════════════════════════
class TestCandidateChangesNothingCurrent:
    def test_content_revision_is_unchanged(self, snap: dict[str, Any]) -> None:
        assert snap["after"]["content_revision"] == snap["before"]["content_revision"], (
            "纯 instrumentation 前置阶段递增了 business content revision —— "
            "Requirement 2.1 明文禁止（只有业务 projection/custom 权威内容变化才递增）"
        )

    def test_entry_pointer_is_unchanged(self, snap: dict[str, Any]) -> None:
        assert (
            snap["after"]["pointer_representation_id"]
            == snap["before"]["pointer_representation_id"]
        )
        assert snap["after"]["pointer_generation"] == snap["before"]["pointer_generation"]

    def test_current_content_version_is_unchanged(self, snap: dict[str, Any]) -> None:
        assert (
            snap["after"]["current_content_version_id"]
            == snap["before"]["current_content_version_id"]
        )

    def test_no_new_representation_or_content_version(self, snap: dict[str, Any]) -> None:
        before, after = snap["before"]["counts"], snap["after"]["counts"]
        assert (
            after["working_paper_content_representation"]
            == before["working_paper_content_representation"]
        ), "本任务只能登记 candidate，出现新 representation 行即越权"
        assert (
            after["working_paper_content_version"]
            == before["working_paper_content_version"]
        )

    def test_exactly_one_candidate_was_registered(self, snap: dict[str, Any]) -> None:
        before, after = snap["before"]["counts"], snap["after"]["counts"]
        table = "working_paper_representation_upgrade_candidate"
        assert before[table] == 0
        assert after[table] == 1, "candidate 必须真的落库 —— 否则全部否定判据在空集上恒真"

    def test_existing_rows_were_never_rewritten(self, snap: dict[str, Any]) -> None:
        """`xmin` 逐行相等 = 既有四张表一行都没被 UPDATE（Requirement 9.10「不改旧 row」）。

        这条判据来自 PostgreSQL 自身的行版本事务 id，不经过任何被测代码，因此
        「outcome 里的比较逻辑被改坏」不会让它假绿。
        """
        before, after = snap["xmin"]["before"], snap["xmin"]["after"]
        assert set(before) == set(after)
        for table in sorted(before):
            assert before[table], f"{table} 的 xmin 基线为空 —— 判据会在空集上恒真"
            assert after[table] == before[table], (
                f"{table} 的行版本发生了变化：{before[table]} → {after[table]}"
            )

    def test_outcome_matches_the_database(self, snap: dict[str, Any]) -> None:
        """`UpgradeCandidateOutcome` 自报的三条与裸 SQL 实测一致（双向互锁）。

        单看 outcome 是「自证」；单看 SQL 又无法证明服务自己也这么认为。两侧都要。
        """
        out = snap["outcome"]
        assert out["revision_unchanged"] is True
        assert out["pointer_unchanged"] is True
        assert out["no_representation_created"] is True
        assert out["content_revision_after"] == snap["after"]["content_revision"]
        assert out["entry_pointer_after"] == snap["after"]["pointer_representation_id"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. candidate 不进入任何现行读取面（R 6.18 / P67）
# ═══════════════════════════════════════════════════════════════════════════
class TestCandidateIsNotResolvable:
    def test_all_ten_intents_are_declared(self, snap: dict[str, Any]) -> None:
        """意图分母来自 `set(ResolutionIntent)`；新增意图会自动进入下一条的循环。"""
        assert snap["resolver"]["intents_declared"] == [
            "callback", "config", "download", "evidence", "extract", "history",
            "materialize", "rematerialize", "retry", "rollback",
        ]

    def test_candidate_is_not_consumable_for_every_intent(
        self, snap: dict[str, Any]
    ) -> None:
        got = snap["resolver"]["not_consumable"]
        assert sorted(got) == snap["resolver"]["intents_declared"]
        for intent, verdict in sorted(got.items()):
            assert verdict.startswith("CandidateNotResolvableError"), (
                f"intent={intent} 没有以 CandidateNotResolvableError 拒绝 candidate：{verdict}"
            )
            assert intent in verdict, f"拒绝文案未指出意图 {intent}：{verdict}"

    def test_resolving_by_candidate_id_fails_for_every_intent(
        self, snap: dict[str, Any]
    ) -> None:
        """把 candidate id 当 representation id 递给 resolver ⇒ 十个意图全部拒绝。

        与上一条不同：上一条是**显式**禁令 API，这一条走的是 `resolve()` 真实路径 ——
        某天有人把 `_assert_not_candidate_id` 从 `resolve()` 里摘掉，只有这条会红。
        """
        got = snap["resolver"]["resolve_with_candidate_id"]
        assert sorted(got) == snap["resolver"]["intents_declared"]
        for intent, verdict in sorted(got.items()):
            assert verdict.startswith("CandidateNotResolvableError"), (
                f"intent={intent}: resolve() 拿 candidate id 竟没拒绝：{verdict}"
            )

    def test_current_resolution_still_returns_the_old_generation(
        self, snap: dict[str, Any]
    ) -> None:
        cur = snap["resolver"]["current"]
        assert cur["representation_id"] == snap["world"]["rep1"]
        assert cur["generation"] == 1
        assert cur["revision"] == snap["before"]["content_revision"]
        assert cur["representation_id"] != snap["world"]["candidate"]
        assert cur["definition_bundle_id"] == snap["world"]["seed_bundle"], (
            "current representation 的 bundle 被换成了新发布的 child —— "
            "candidate 阶段不得改变历史读取（Property 28）"
        )

    def test_candidate_id_appears_nowhere_but_its_own_row(
        self, snap: dict[str, Any]
    ) -> None:
        """全 schema uuid 列清扫：candidate id 只允许出现在 candidate 表主键上。

        分母是 `information_schema`，所以未来新增的表**自动**纳入检查；往
        `working_paper_sync_entry_state.current_representation_id` /
        `working_paper_oo_room.*` / `working_paper_content_application.*` 任一处
        塞 candidate id 都会立刻越出白名单。
        """
        sweep = snap["id_sweep"]["candidate"]
        assert snap["id_sweep"]["uuid_column_count"] > 50, (
            f"uuid 列分母只有 {snap['id_sweep']['uuid_column_count']} 列 —— "
            "V151 没建全，清扫会在近乎空集上恒真"
        )
        assert sweep["unexpected"] == [], (
            f"candidate id 出现在不该出现的位置: {sweep['unexpected']}"
        )
        assert [f"{t}.{c}" for t, c, _ in sweep["hits"]] == sweep["allowed"]

    def test_staged_artifact_never_becomes_a_representation_substrate(
        self, snap: dict[str, Any]
    ) -> None:
        sweep = snap["id_sweep"]["staged_artifact"]
        assert sweep["unexpected"] == [], (
            f"candidate 的 staged artifact 被别处引用了: {sweep['unexpected']} —— "
            "它永不成为 representation/application substrate（Requirement 6.18）"
        )

    def test_candidate_is_registered_in_scope_index_only_as_candidate(
        self, snap: dict[str, Any]
    ) -> None:
        """scope index 里**应该**有一行（授权定位需要），但 kind 必须是 upgrade_candidate。"""
        rows = snap["scope_index"]
        assert len(rows) == 1, rows
        assert rows[0]["resource_kind"] == "upgrade_candidate"
        assert rows[0]["entry_id"] == ENTRY
        assert rows[0]["retired_at"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. 缺 approved child ⇒ 不可 finalize、状态不可见（R 6.18 / 9.10 / P67）
# ═══════════════════════════════════════════════════════════════════════════
class TestAwaitingContractIsTerminalForThisTask:
    def test_candidate_state_is_awaiting_contract(self, snap: dict[str, Any]) -> None:
        row = snap["candidate_row"]
        assert row["state"] == "awaiting_contract", (
            f"candidate state={row['state']} —— 本任务只能停在 awaiting_contract："
            "ready 会让 Task 36 之前的 finalize 前置看起来已就绪"
        )
        assert row["finalized_at"] is None

    def test_contract_and_bundle_targets_are_null_not_forged(
        self, snap: dict[str, Any]
    ) -> None:
        row = snap["candidate_row"]
        assert row["target_contract_definition_id"] is None, (
            "本任务伪造了 per-entry contract —— tasks.md 明文把它划给 Task 36 / 40–57"
        )
        assert row["target_definition_bundle_id"] is None

    def test_frozen_children_are_the_two_this_task_may_publish(
        self, snap: dict[str, Any]
    ) -> None:
        row = snap["candidate_row"]
        assert row["template_definition_id"] == snap["world"]["template_definition"]
        assert row["instrumentation_definition_id"] == (
            snap["world"]["instrumentation_definition"]
        )

    def test_equivalence_and_rollback_evidence_are_recorded(
        self, snap: dict[str, Any]
    ) -> None:
        """Requirement 9.10 的审计清单：反读等值报告 + rollback target 必须落库。"""
        row = snap["candidate_row"]
        for field in ("visible_equivalence_report_sha256", "rollback_source_sha256"):
            value = row[field]
            assert isinstance(value, str) and len(value) == 64, f"{field}={value!r}"
            assert set(value) != {"0"}, f"{field} 是全零 hash"

    def test_finalize_is_rejected_and_says_contract_is_missing(
        self, snap: dict[str, Any]
    ) -> None:
        got = snap["finalize_gate"]["awaiting_contract"]
        assert got.startswith("CandidateNotFinalizableError"), got
        assert "contract" in got, (
            f"拒绝理由没指向缺 approved per-entry contract：{got} —— "
            "理由指错地方时，真正缺的那一环变得不可分辨"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 不伪造 contract / authority model / bundle（tasks.md 第 4 条）
# ═══════════════════════════════════════════════════════════════════════════
class TestDefinitionDeltaIsExactlyTemplateAndInstrumentation:
    def test_only_two_definition_rows_were_added(self, snap: dict[str, Any]) -> None:
        before = snap["definitions_delta"]["before"]
        after = snap["definitions_delta"]["after"]
        delta = {
            k: after.get(k, 0) - before.get(k, 0)
            for k in set(before) | set(after)
        }
        assert delta.get("template") == 1, delta
        assert delta.get("instrumentation") == 1, delta
        assert delta.get("contract", 0) == 0, (
            f"本任务发布了 contract definition：{delta}"
        )
        assert delta.get("authority_model", 0) == 0, (
            f"本任务发布了 authority model：{delta}"
        )
        assert delta.get("bundle", 0) == 0, (
            f"本任务发布了 definition bundle：{delta} —— bundle 属 Task 36 / 40–57"
        )

    def test_baseline_had_a_real_approved_bundle(self, snap: dict[str, Any]) -> None:
        """delta 判据的前提：播种确实建了 bundle，否则 `bundle delta == 0` 恒真。"""
        assert snap["definitions_delta"]["before"].get("bundle") == 1

    def test_publish_dag_rejects_instrumentation_before_template(
        self, snap: dict[str, Any]
    ) -> None:
        """DAG 第二段不能抢跑第一段（Requirement 9.8 / Property 28）。

        判据落在**真实 publisher + 真库**上：顺序不是靠 upgrader 里语句先后保证的，
        `publish_definition` 内部对 instrumentation 会调 `assert_publish_order`。
        """
        got = snap["publish_dag"]["instrumentation_first"]
        assert got.startswith("PublishOrderError"), got

    def test_instrumentation_payload_has_no_backward_reference(
        self, snap: dict[str, Any]
    ) -> None:
        """Requirement 6.14：payload 不含自身 UUID/hash、contract/bundle digest。

        纯域守卫已按 Task 12 validator 逐键验过；这里再核一次**实际发布出去的那份**
        payload 键集，防「域里构造的是干净的、发布时另塞了字段」。
        """
        keys = snap["instrumentation_payload_keys"]
        assert keys, keys
        forbidden = [
            k
            for k in keys
            if k
            in {
                "contract_definition_sha256",
                "definition_bundle_sha256",
                "authority_model_definition_sha256",
                "instrumentation_definition_sha256",
                "definition_id",
                "id",
                "sha256",
            }
        ]
        assert forbidden == [], f"instrumentation payload 含反向/自引用键: {forbidden}"
        assert "template_definition_sha256" in keys, (
            "payload 缺 template digest —— 单向引用这一段本身也必须成立"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. candidate artifact 命名空间与门面禁令（R 6.18 / 5.9）
# ═══════════════════════════════════════════════════════════════════════════
class TestCandidateArtifactIsIsolated:
    def test_artifact_row_is_candidate_kind_and_state(self, snap: dict[str, Any]) -> None:
        art = snap["candidate_artifact"]
        assert art["kind"] == "upgrade_candidate", art
        assert art["state"] == "candidate", art

    def test_artifact_lives_in_the_candidate_namespace(self, snap: dict[str, Any]) -> None:
        rel = snap["candidate_artifact"]["relative_path"].replace("\\", "/")
        assert ".upgrade-candidates/" in rel, rel
        assert ".versions/" not in rel, (
            f"candidate 落进了不可变发布目录: {rel} —— 只有 finalize 才可进 .versions"
        )
        assert rel != snap["world"]["gen1_rel"].replace("\\", "/")

    def test_forbidden_methods_are_unreachable_on_a_real_repository(
        self, snap: dict[str, Any]
    ) -> None:
        """门面套在**真** `WorkpaperSyncRepository` 上仍然摘掉那六个写入面。

        纯域守卫用 `_FakeRepo` 验过形态；这里证明它不是「fake 上碰巧没这些方法」。
        """
        surface = snap["forbidden_surface"]
        assert surface["real_repository"] == "WorkpaperSyncRepository"
        assert surface["wrapped"] == "CandidateOnlyRepository"
        assert surface["calls"], surface
        for method, verdict in sorted(surface["calls"].items()):
            assert verdict.startswith("CandidateSurfaceForbiddenError"), (
                f"{method} 在 candidate 生成路径上可达：{verdict}"
            )
        assert {
            "create_representation", "set_entry_pointer", "finalize_candidate",
        } <= set(surface["calls"])

    def test_passthrough_still_works(self, snap: dict[str, Any]) -> None:
        """门面不是「把仓储整体禁掉」—— candidate 登记这条路必须通。"""
        assert snap["forbidden_surface"]["passthrough_ok"] is True

    def test_rejected_calls_left_the_database_untouched(
        self, snap: dict[str, Any]
    ) -> None:
        state = snap["forbidden_surface"]["state_after"]
        assert state["counts"]["working_paper_content_representation"] == 1
        assert state["pointer_representation_id"] == snap["world"]["rep1"]
        assert state["content_revision"] == snap["before"]["content_revision"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. 权威模板只读（R 9.1 / 9.9）
# ═══════════════════════════════════════════════════════════════════════════
class TestAuthorityTemplatesAreReadOnly:
    def test_source_digests_match_task5_record(self, snap: dict[str, Any]) -> None:
        for rel, expected in AUTHORITY_TEMPLATE_SHA.items():
            assert snap["source_sha_before"][rel] == expected, (
                f"{rel} 的开工 digest 与 Task 5 记录不一致 —— 权威源被改过，"
                "载体裁决与等价基线全部失效"
            )

    def test_templates_are_byte_identical_after_the_whole_run(
        self, snap: dict[str, Any]
    ) -> None:
        assert snap["source_sha_after"] == snap["source_sha_before"], (
            "运行时写回了模板库（Requirement 9.9 明文禁止）"
        )

    def test_gate_identity_is_recorded_for_stale_policy(self, snap: dict[str, Any]) -> None:
        """Requirement 14.16：探针门身份必须可记录，环境变了才能判 stale（P71）。

        `onlyoffice_build` **不写字面量**：期望值从 Task 5 契约的
        `evidence.onlyoffice_build` 取，再要求它能在 Task 5 实测的 `oo_build.json`
        dpkg 行里找到。三处（gate 基线 / 契约 / 容器实测）互锁 ⇒ 任一处被改动都红，
        而不是「测试里抄的那个字符串恰好没人动」。
        """
        from app.services.workpaper_sync import excel_instrumentation as EI

        gate = snap["gate"]
        assert len(gate["contract_sha256"]) == 64

        contract = json.loads(EI.GATE_CONTRACT_PATH.read_text(encoding="utf-8"))
        expected_build = contract["evidence"]["onlyoffice_build"]
        assert gate["onlyoffice_build"] == expected_build, (
            f"gate 基线记的 OO build {gate['onlyoffice_build']!r} 与 Task 5 契约的 "
            f"{expected_build!r} 不一致 —— 两侧必须互锁（Property 71）"
        )
        build_probe = json.loads(_OO_BUILD_EVIDENCE.read_text(encoding="utf-8"))
        assert expected_build in build_probe["dpkg_onlyoffice_documentserver"], (
            f"契约声明的 build {expected_build!r} 在 Task 5 实测 dpkg 记录里找不到 —— "
            "裁决所依据的容器版本无法追溯"
        )

        assert set(gate["forbidden_anchors"]) == {"sheet_id", "sheet_display_name"}
        assert "sheet_id" not in gate["allowed_anchors"]
