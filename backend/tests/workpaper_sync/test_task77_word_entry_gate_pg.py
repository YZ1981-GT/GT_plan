# -*- coding: utf-8 -*-
"""Task 77 守卫（真实 PG）—— Word candidate 真的走完 `finalizeCandidate(entry)`。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 77
点名 Property：**28 / 30 / 31 / 32 / 34 / 67**
点名 AC：6.10 · 6.18 · 7.1 · 7.2 · 7.3 · 7.4 · 7.5 · 7.8 · 7.10 · 12.5

═══ 这一半证的是「真的能 finalize + 真的拒得住 + 真的没多写一个字节」 ═══

离线守卫证判据正确，但纯 AST/纯函数判据**可能守着一段死代码**。本文件在真库上跑完
整条链，全部用**生产代码**与**真实权威模板**（F2-22 存货监盘计划.docx）：

    ReusingDefinitionPublisher（Task 76）
        → template / instrumentation / contract / authority_model / bundle 真落库
    WordInstrumentationUpgrader（Task 59）
        → 真注入 tagged SDT、真 stage candidate、state=awaiting_contract
    CandidateDefinitionAttachService（Task 76）
        → 绑 approved contract/bundle，state=ready，append-only 事件
    WordEntryFinalizeGate（**Task 77**）
        → 四条 tagged-SDT 判据 + Word-only 往返 → Task 25 的唯一出口
        → 同一 content version 的新 published immutable representation generation

并逐条证明拒绝：attach 之前 finalize 不可；frozen bundle digest 不符即拒；换一份
instrumentation 清册即拒；跨 entry 的 candidate 即拒 —— 且**每一次拒绝之后**
`content_revision` 与 entry pointer 逐值不变、representation 一行没多。

═══ 🔴 为什么是 scratch schema 而不是 public ═══

`working_paper_content_version` 在真实库里 **0 行**（本任务实测；`--check` 报告的
`supply_rows` 亦然），整条 `content version → representation → candidate → finalize`
在真实库从未跑过。要在 public schema 里造出这条链，就得先对某个真实底稿走一次业务
内容应用（`ContentMutationService.commit`）—— 那是**真实业务写入**，不属于本任务。
因此正面证明落在 scratch schema：表结构、CHECK、trigger、外键全是真的（V151/V153 现跑），
只有 schema 名是临时的。这条限制已登记为 BP-18，不为凑「真实库有行」去伪造业务 commit。

═══ 隔离与采集 ═══

scratch schema `tmp_task77_word_<hex>` + 独立文件根，结束 `DROP SCHEMA CASCADE` + `rmtree`。
全部场景由**一次 `asyncio.run`** 跑完落进快照（module fixture）—— 每个测试各自开 async
会污染共享连接池（Task 21~29 实测：第二个起 `NoneType has no attribute send`）。
采集阶段异常一律**记录不穿透**：穿透会把整个 module 变成 collection ERROR，而 `-rf`
只列 FAILED 不列 ERROR ⇒ 定向变异看不到预期失败项 ⇒ 判 GREEN。
`test_no_phase_crashed_during_collection` 是这个决定的另一半。

用法（仓库根）::

    .\\.venv\\Scripts\\python.exe -m pytest \\
        backend/tests/workpaper_sync/test_task77_word_entry_gate_pg.py -q
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import sys
import tempfile
import traceback
import uuid
from pathlib import Path
from typing import Any

import pytest

_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
MIGRATIONS: tuple[Path, ...] = (
    BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql",
    BACKEND / "migrations" / "V153__workpaper_representation_candidate_attach_event.sql",
)
HOST_SCRIPT = BACKEND / "scripts" / "fix" / "fix_task77_finalize_word_entry_representation.py"

if str(BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(BACKEND))
for _extra in (BACKEND / "scripts" / "gen", HOST_SCRIPT.parent):
    if str(_extra) not in sys.path:  # pragma: no cover - import 自举
        sys.path.insert(0, str(_extra))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_task77_word_"

#: V065 给 outbox enum 加过 `processing`；守卫不能跑在比生产更窄的类型上
#: （与 `test_task15_content_mutation_pg.py` 同一处置）。
_EXTRA_ENUM_LABELS = {"import_event_outbox_status": ("processing",)}

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


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成「无数据」）。"""


def _err(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)[-8:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _enum_ddl(tables: list[Any], sa: Any) -> list[str]:
    """按 ORM 列类型现算 enum DDL（不手抄标签，防第二真源）。"""
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


async def _revision_pointer(session: Any, sa: Any, *, wp: uuid.UUID, entry: str) -> dict[str, Any]:
    revision = (
        await session.execute(
            sa.text("SELECT content_revision FROM working_paper WHERE id = :w"),
            {"w": str(wp)},
        )
    ).scalar_one()
    pointer = (
        await session.execute(
            sa.text(
                "SELECT current_representation_id FROM working_paper_sync_entry_state "
                "WHERE wp_id = :w AND entry_id = :e"
            ),
            {"w": str(wp), "e": entry},
        )
    ).scalar_one_or_none()
    count = (
        await session.execute(
            sa.text(
                "SELECT count(*) FROM working_paper_content_representation "
                "WHERE wp_id = :w AND entry_id = :e"
            ),
            {"w": str(wp), "e": entry},
        )
    ).scalar_one()
    return {
        "content_revision": int(revision),
        "pointer": None if pointer is None else str(pointer),
        "representation_count": int(count),
    }


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - 一次采集覆盖全链
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    import fix_task77_finalize_word_entry_representation as HOST
    import generate_task60_f2_word_contracts as G60
    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.services.workpaper_sync import definitions as D
    from app.services.workpaper_sync import projection_provisioning as PP
    from app.services.workpaper_sync import word_entry_gate as WG
    from app.services.workpaper_sync import word_instrumentation as WI
    from app.services.workpaper_sync.artifacts import (
        CanonicalArtifactRepository,
        StagedCandidate,
    )
    from app.services.workpaper_sync.contracts import load_word_carrier_gate
    from app.services.workpaper_sync.materialize_coordinator import (
        build_materialize_coordinator,
    )
    from app.services.workpaper_sync.models import (
        AuthorityModel,
        BundleSlot,
        CandidateState,
        DefinitionKind,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 77 的判据是「Word candidate 真的经 gate finalize 成 published "
            "representation」「拒绝之后 pointer/revision 逐值不变」，全部依赖真实表与 "
            f"V151/V153 的 CHECK/trigger；必须真实 PostgreSQL，当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    for migration in MIGRATIONS:
        if not migration.exists():
            raise _HarnessError(f"缺少迁移文件: {migration}")

    lanes = list(G60.ENTRIES)
    if len(lanes) != 2:
        raise _HarnessError(f"Word lane 现算 {len(lanes)} 条 entry ⇒ 分母可疑")
    primary, other = lanes[0], lanes[1]

    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task77_store_"))
    (base_root / "storage").mkdir()
    (base_root / "definition_store").mkdir()
    scratch_dir = base_root / "gate-scratch"
    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "entry_id": primary.contract_id,
        "other_entry_id": other.contract_id,
        "apply_errors": [],
        "harness_errors": {},
        "state": {},
        "supply": {},
        "refusals": {},
        "finalize": {},
        "candidate": {},
        "representation": {},
        "xmin": {},
        "resolver": {},
    }

    def _phase_failed(name: str, exc: BaseException) -> None:
        snap["harness_errors"][name] = _err(exc)

    engine = None
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
        for migration in MIGRATIONS:
            statements = MigrationRunner._split_sql_statements(
                migration.read_text(encoding="utf-8")
            )
            for idx, stmt in enumerate(statements, 1):
                try:
                    async with engine.begin() as conn:
                        await conn.exec_driver_sql(stmt)
                except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言为空
                    snap["apply_errors"].append(
                        {"migration": migration.name, "index": idx, "error": _err(exc)}
                    )
        if snap["apply_errors"]:
            raise _HarnessError(f"迁移应用失败: {snap['apply_errors'][:3]}")

        # outbox 两张表从 **ORM metadata** 建（列不手抄，防第二真源）——
        # `RepresentationService.finalize_candidate` 会在同事务里入队 outbox 事件。
        from app.models.dataset_models import ImportEventConsumption, ImportEventOutbox

        outbox_tables = [ImportEventOutbox.__table__, ImportEventConsumption.__table__]
        async with engine.begin() as conn:
            for stmt in _enum_ddl(outbox_tables, sa):
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
        snap["ids"] = {"project": str(project), "wp": str(wp), "user": str(user)}

        # ── 声明（真实权威模板 + 真契约 + 真 instrumentation payload）───────
        decl = HOST.load_lane_declaration(contract_id=primary.contract_id)
        decl_other = HOST.load_lane_declaration(contract_id=other.contract_id)
        entry = decl.entry_id
        engine_gate = load_word_carrier_gate()
        inject_gate = WI.WordSdtCarrierGate.load()
        snap["declaration"] = {
            "entry_id": entry,
            "contract_origin": decl.contract_origin,
            "contract_sha256": decl.contract.canonical_sha256,
            "template_sha256": decl.template_sha256,
            "instrumentation_sha256": D.canonical_digest(decl.instrumentation_payload),
            "field_count": len(decl.contract.all_fields()),
        }

        async with Session() as session:
            snap["supply"]["initial"] = await PP.count_supply_rows(session)

        # ── 阶段 1：发布真实 Word definition 链 + approved bundle ───────────
        published: dict[str, Any] = {}
        try:
            async with Session() as session:
                repo = WorkpaperSyncRepository(session)
                publisher = PP.ReusingDefinitionPublisher(
                    session=session,
                    artifacts=artifacts,
                    repository=repo,
                    project_id=project,
                    wp_id=wp,
                    source_commit="task77-pg",
                )
                template_payload = WI.build_word_template_payload(
                    spec=decl.spec,
                    template_sha256=decl.template_sha256,
                    structure_hash=WI.word_structure_hash(decl.template_bytes),
                )
                tpl = await publisher.publish_definition(
                    kind=DefinitionKind.template,
                    payload=template_payload,
                    logical_id=f"word-template/{decl.spec.template_id}",
                    semantic_version=decl.contract.semantic_version,
                    blob_bytes=decl.template_bytes,
                    structure_hash=WI.word_structure_hash(decl.template_bytes),
                )
                instr = await publisher.publish_definition(
                    kind=DefinitionKind.instrumentation,
                    payload=decl.instrumentation_payload,
                    logical_id=f"word-instrumentation/{entry}",
                    semantic_version=decl.contract.semantic_version,
                )
                contract_def = await publisher.publish_definition(
                    kind=DefinitionKind.contract,
                    payload=dict(decl.contract.canonical_payload),
                    logical_id=decl.contract.contract_id,
                    semantic_version=decl.contract.semantic_version,
                    blob_bytes=decl.contract.canonical_bytes,
                )
                authority_payload = {
                    "schema_version": "authority-model-definition:v1",
                    "authority_model": AuthorityModel.projection_contract.value,
                    "document_type": "docx",
                    "contract_id": decl.contract.contract_id,
                    "entry_lane_key": primary.lane_entry_key,
                }
                authority = await publisher.publish_definition(
                    kind=DefinitionKind.authority_model,
                    payload=authority_payload,
                    logical_id=f"word-authority/{entry}",
                    semantic_version=decl.contract.semantic_version,
                )
                slots = {
                    BundleSlot.template: D.definition_slot_spec(
                        BundleSlot.template,
                        definition_id=tpl.definition_id,
                        definition_sha256=tpl.sha256,
                    ),
                    BundleSlot.instrumentation: D.definition_slot_spec(
                        BundleSlot.instrumentation,
                        definition_id=instr.definition_id,
                        definition_sha256=instr.sha256,
                    ),
                    BundleSlot.contract: D.definition_slot_spec(
                        BundleSlot.contract,
                        definition_id=contract_def.definition_id,
                        definition_sha256=contract_def.sha256,
                    ),
                }
                bundle = await publisher.publish_bundle(
                    authority_model_definition_id=authority.definition_id,
                    authority_model=AuthorityModel.projection_contract,
                    authority_model_definition_sha256=authority.sha256,
                    slots=slots,
                )
                await session.commit()
            published = {
                "template_definition_id": tpl.definition_id,
                "template_sha256": tpl.sha256,
                "instrumentation_definition_id": instr.definition_id,
                "instrumentation_sha256": instr.sha256,
                "contract_definition_id": contract_def.definition_id,
                "contract_sha256": contract_def.sha256,
                "authority_definition_id": authority.definition_id,
                "bundle_id": bundle.bundle_id,
                "bundle_sha256": bundle.canonical_sha256,
            }
            snap["published"] = {k: str(v) for k, v in published.items()}
        except Exception as exc:  # noqa: BLE001
            _phase_failed("publish_definitions", exc)
            raise _HarnessError(f"definition 链发布失败: {_err(exc)}") from exc
        async with Session() as session:
            snap["supply"]["after_publish"] = await PP.count_supply_rows(session)

        # ── 阶段 2：播种存量 content version + representation + pointer ─────
        seed: dict[str, Any] = {}
        try:
            async with Session() as session:
                repo = WorkpaperSyncRepository(session)
                projection = artifacts.publish_projection(
                    revision=0,
                    staged=artifacts.stage_bytes(
                        project_id=project,
                        wp_id=wp,
                        payload=b"t77-projection-v0",
                        document_type="json.gz",
                    ),
                )
                art_projection = await repo.register_artifact(
                    project_id=project,
                    wp_id=wp,
                    kind="projection",
                    state="published",
                    relative_path=projection.relative_path,
                    sha256=projection.sha256,
                    size_bytes=projection.size_bytes,
                    document_type="json.gz",
                )
                legacy_staged = artifacts.stage_bytes(
                    project_id=project,
                    wp_id=wp,
                    payload=decl.template_bytes,
                    document_type="docx",
                )
                legacy_published = artifacts.publish_representation(
                    entry_id=entry, generation=1, staged=legacy_staged
                )
                art_legacy = await repo.register_artifact(
                    project_id=project,
                    wp_id=wp,
                    kind="canonical",
                    state="published",
                    relative_path=legacy_published.relative_path,
                    sha256=legacy_published.sha256,
                    size_bytes=legacy_published.size_bytes,
                    document_type="docx",
                )
                content_version = await repo.create_content_version(
                    project_id=project,
                    wp_id=wp,
                    entry_id=entry,
                    revision=0,
                    source="html",
                    projection_artifact_id=art_projection.id,
                    projection_sha256=art_projection.sha256,
                    actor_id=user,
                )
                representation = await repo.create_representation(
                    project_id=project,
                    wp_id=wp,
                    entry_id=entry,
                    content_version_id=content_version.id,
                    generation=1,
                    document_type="docx",
                    artifact_id=art_legacy.id,
                    artifact_sha256=art_legacy.sha256,
                    definition_bundle_id=published["bundle_id"],
                    authority_model_definition_id=published["authority_definition_id"],
                    adapter_id="t77.legacy",
                    adapter_build_digest=_d("t77-legacy-build"),
                    structure_hash=_d("t77-legacy-structure"),
                    identity_inventory_sha256=_d("t77-legacy-inventory"),
                    reason="content_commit",
                )
                await repo.set_entry_pointer(
                    wp_id=wp,
                    entry_id=entry,
                    representation_id=representation.id,
                    generation=1,
                )
                await session.commit()
            seed = {
                "content_version_id": content_version.id,
                "representation_id": representation.id,
                "legacy_artifact_sha256": art_legacy.sha256,
            }
            snap["seed"] = {k: str(v) for k, v in seed.items()}
        except Exception as exc:  # noqa: BLE001
            _phase_failed("seed", exc)
            raise _HarnessError(f"存量播种失败: {_err(exc)}") from exc
        async with Session() as session:
            snap["state"]["after_seed"] = await _revision_pointer(
                session, sa, wp=wp, entry=entry
            )

        # ── 阶段 3：真跑 Task 59 的 upgrader → non-current candidate ────────
        candidates: dict[str, Any] = {}
        try:
            async with Session() as session:
                repo = WorkpaperSyncRepository(session)
                upgrader = WI.WordInstrumentationUpgrader(
                    session=session,
                    repository=repo,
                    artifacts=artifacts,
                    project_id=project,
                    source_commit="task77-pg",
                    gate=inject_gate,
                )
                instrumented, equivalence, readback = upgrader.instrument_source_bytes(
                    source=decl.template_bytes, spec=decl.spec
                )
                outcome = await upgrader.stage_and_register_candidate(
                    spec=decl.spec,
                    wp_id=wp,
                    content_version_id=seed["content_version_id"],
                    source_representation_id=seed["representation_id"],
                    source_bytes=decl.template_bytes,
                    instrumented=instrumented,
                    equivalence=equivalence,
                    readback=readback,
                    template_definition=type(
                        "_D", (), {"definition_id": published["template_definition_id"], "sha256": published["template_sha256"]}
                    )(),
                    instrumentation_definition=type(
                        "_D", (), {"definition_id": published["instrumentation_definition_id"], "sha256": published["instrumentation_sha256"]}
                    )(),
                    actor_id=user,
                )
                await session.commit()
            candidates["primary"] = outcome
            snap["candidate"]["primary"] = {
                "candidate_id": str(outcome.candidate_id),
                "state": outcome.state.value,
                "target_contract_definition_id": outcome.target_contract_definition_id,
                "target_definition_bundle_id": outcome.target_definition_bundle_id,
                "staged_artifact_sha256": outcome.staged_artifact_sha256,
                "instrumented_sha256": instrumented.instrumented_sha256,
                "report_sha256": outcome.visible_equivalence_report_sha256,
                "revision_before": outcome.content_revision_before,
                "revision_after": outcome.content_revision_after,
                "pointer_before": outcome.entry_pointer_before,
                "pointer_after": outcome.entry_pointer_after,
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("upgrader", exc)
            raise _HarnessError(f"candidate 登记失败: {_err(exc)}") from exc
        async with Session() as session:
            snap["state"]["after_candidate"] = await _revision_pointer(
                session, sa, wp=wp, entry=entry
            )

        # ── 组装 StagedCandidate（字节只来自 candidate 自己）────────────────
        cand_primary = candidates["primary"]
        cand_path = artifacts.resolve_relative_path(cand_primary.staged_relative_path)
        eq_path, eq_bytes = HOST.locate_candidate_evidence(
            candidate_path=cand_path,
            expected_sha256=cand_primary.visible_equivalence_report_sha256,
        )
        staged = StagedCandidate(
            candidate_id=cand_primary.candidate_id,
            project_id=project,
            wp_id=wp,
            entry_id=entry,
            path=cand_path,
            relative_path=cand_primary.staged_relative_path,
            sha256=cand_primary.staged_artifact_sha256,
            size_bytes=cand_path.stat().st_size,
            document_type="docx",
            equivalence_relative_path=cand_primary.staged_relative_path.rsplit("/", 1)[0]
            + "/"
            + eq_path.name,
            equivalence_sha256=hashlib.sha256(eq_bytes).hexdigest(),
            verified_before_move=True,
            verified_after_move=True,
        )

        def _gate(session: Any) -> Any:
            resolution = CanonicalResolutionService(session, artifacts)
            return WG.WordEntryFinalizeGate(
                loader=WG.WordEntryDefinitionLoader(
                    session=session, resolution=resolution
                ),
                resolution=resolution,
                coordinator=build_materialize_coordinator(session),
            )

        async def _finalize(**overrides: Any) -> Any:
            kwargs: dict[str, Any] = {
                "project_id": project,
                "entry_id": entry,
                "candidate_id": cand_primary.candidate_id,
                "staged_candidate": staged,
                "contract": decl.contract,
                "contract_origin": decl.contract_origin,
                "instrumentation_payload": decl.instrumentation_payload,
                "frozen_bundle_sha256": published["bundle_sha256"],
                "scratch_dir": scratch_dir,
                "equivalence_report_bytes": eq_bytes,
                "carrier_gate": engine_gate,
            }
            kwargs.update(overrides)
            async with Session() as session:
                gate = _gate(session)
                return await gate.finalize_candidate(**kwargs)

        async def _record_refusal(label: str, **overrides: Any) -> None:
            before = None
            after = None
            async with Session() as probe:
                before = await _revision_pointer(probe, sa, wp=wp, entry=entry)
            try:
                await _finalize(**overrides)
            except Exception as exc:  # noqa: BLE001 - 记录**类型 + 原因**，不只记类型
                snap["refusals"][label] = {
                    "type": type(exc).__name__,
                    "error_code": getattr(exc, "error_code", None),
                    "message": str(exc),
                }
            else:
                snap["refusals"][label] = {"type": None, "error_code": None, "message": ""}
            async with Session() as probe:
                after = await _revision_pointer(probe, sa, wp=wp, entry=entry)
            snap["refusals"][label]["state_before"] = before
            snap["refusals"][label]["state_after"] = after

        # ── 阶段 4：attach 之前 finalize 必不可 ────────────────────────────
        await _record_refusal("before_attach")

        # ── 阶段 5：受控 attach（Task 76）→ ready ───────────────────────────
        try:
            async with Session() as session:
                service = PP.CandidateDefinitionAttachService(
                    session=session, repository=WorkpaperSyncRepository(session)
                )
                attach = await service.attach(
                    wp_id=wp,
                    entry_id=entry,
                    candidate_id=cand_primary.candidate_id,
                    contract_definition_id=published["contract_definition_id"],
                    definition_bundle_id=published["bundle_id"],
                    correlation_id="task77-pg-attach",
                    actor_id=user,
                )
                await session.commit()
            snap["candidate"]["attach"] = attach.as_dict()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("attach", exc)

        # ── 阶段 6：finalize 前置成立 ──────────────────────────────────────
        try:
            async with Session() as session:
                resolution = CanonicalResolutionService(session, artifacts)
                row = await resolution.assert_candidate_finalizable(
                    cand_primary.candidate_id
                )
            snap["candidate"]["finalizable"] = {
                "state": str(row.state),
                "target_contract_definition_id": str(row.target_contract_definition_id),
                "target_definition_bundle_id": str(row.target_definition_bundle_id),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("finalizable", exc)

        # ── 阶段 7：逐条拒绝越权（每次都记「原因」并复核 pointer/revision）──
        import dataclasses

        await _record_refusal("wrong_frozen_bundle_digest", frozen_bundle_sha256="c" * 64)
        await _record_refusal(
            "foreign_instrumentation_payload",
            instrumentation_payload=decl_other.instrumentation_payload,
        )
        await _record_refusal("foreign_entry_id", entry_id=decl_other.entry_id)
        # candidate **行**的 entry 归属对得上、但 staged **字节**属于另一个 entry。
        # 与上一条分开：前者由 `candidate.entry_id != entry_id` 守，本条由
        # `staged_candidate.entry_id != entry_id` 守；不分开就锁不住第二条。
        await _record_refusal(
            "foreign_staged_bytes",
            staged_candidate=dataclasses.replace(staged, entry_id=decl_other.entry_id),
        )
        # 证据登记的 instrumented digest 与将要发布的字节不是同一份。
        await _record_refusal(
            "mismatched_instrumented_digest",
            staged_candidate=dataclasses.replace(staged, sha256=_d("t77-not-the-bytes")),
        )
        # candidate 行的 rollback 源 digest 被改过（回滚源不可追溯 ⇒ 失败时无法保留原
        # Word 文件版本）。改完立刻改回，避免污染后续真 finalize。
        async with Session() as session:
            original_rollback = (
                await session.execute(
                    sa.text(
                        "SELECT rollback_source_sha256 FROM "
                        "working_paper_representation_upgrade_candidate WHERE id = :c"
                    ),
                    {"c": str(cand_primary.candidate_id)},
                )
            ).scalar_one()
            await session.execute(
                sa.text(
                    "UPDATE working_paper_representation_upgrade_candidate "
                    "SET rollback_source_sha256 = :d WHERE id = :c"
                ),
                {"d": _d("t77-tampered-rollback"), "c": str(cand_primary.candidate_id)},
            )
            await session.commit()
        await _record_refusal("tampered_rollback_digest")
        async with Session() as session:
            await session.execute(
                sa.text(
                    "UPDATE working_paper_representation_upgrade_candidate "
                    "SET rollback_source_sha256 = :d WHERE id = :c"
                ),
                {"d": original_rollback, "c": str(cand_primary.candidate_id)},
            )
            await session.commit()

        # ── 阶段 8：真 finalize ────────────────────────────────────────────
        async with Session() as probe:
            snap["state"]["before_finalize"] = await _revision_pointer(
                probe, sa, wp=wp, entry=entry
            )
            snap["xmin"]["before_finalize"] = await _xmin(probe, sa, wp=wp)
        try:
            outcome = await _finalize()
            snap["finalize"]["outcome"] = outcome.as_dict()
            snap["finalize"]["revision_unchanged"] = outcome.revision_unchanged
        except Exception as exc:  # noqa: BLE001
            _phase_failed("finalize", exc)
        async with Session() as probe:
            snap["state"]["after_finalize"] = await _revision_pointer(
                probe, sa, wp=wp, entry=entry
            )
            snap["xmin"]["after_finalize"] = await _xmin(probe, sa, wp=wp)
            snap["supply"]["after_finalize"] = await PP.count_supply_rows(probe)
            rows = (
                (
                    await probe.execute(
                        sa.text(
                            "SELECT id, generation, document_type, adapter_id,"
                            " artifact_sha256, definition_bundle_id, content_version_id,"
                            " structure_hash, identity_inventory_sha256, reason"
                            " FROM working_paper_content_representation"
                            " WHERE wp_id = :w AND entry_id = :e ORDER BY generation"
                        ),
                        {"w": str(wp), "e": entry},
                    )
                )
                .mappings()
                .all()
            )
            snap["representation"]["rows"] = [
                {k: str(v) for k, v in dict(r).items()} for r in rows
            ]
            cand_row = (
                (
                    await probe.execute(
                        sa.text(
                            "SELECT state, finalized_representation_id"
                            " FROM working_paper_representation_upgrade_candidate"
                            " WHERE id = :c"
                        ),
                        {"c": str(cand_primary.candidate_id)},
                    )
                )
                .mappings()
                .first()
            )
            snap["candidate"]["after_finalize"] = {
                k: (None if v is None else str(v)) for k, v in dict(cand_row or {}).items()
            }

        # ── 阶段 9：candidate 仍不可被 resolver 消费 ───────────────────────
        try:
            async with Session() as session:
                resolution = CanonicalResolutionService(session, artifacts)
                await resolution.assert_candidate_not_consumable(
                    candidate_id=cand_primary.candidate_id, intent="download"
                )
            snap["resolver"]["candidate_consumable"] = True
        except Exception as exc:  # noqa: BLE001
            snap["resolver"]["candidate_consumable"] = False
            snap["resolver"]["refusal"] = f"{type(exc).__name__}: {exc}"

        # ── 阶段 10：finalize 之后再 finalize 必不可（不可变代际）────────────
        await _record_refusal("second_finalize")
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


async def _xmin(session: Any, sa: Any, *, wp: uuid.UUID) -> dict[str, Any]:
    """`working_paper` 与既有 representation 行的 `xmin`（证明「没被改写」）。"""
    paper = (
        await session.execute(
            sa.text("SELECT xmin::text FROM working_paper WHERE id = :w"), {"w": str(wp)}
        )
    ).scalar_one()
    reps = (
        (
            await session.execute(
                sa.text(
                    "SELECT id::text AS id, xmin::text AS x"
                    " FROM working_paper_content_representation WHERE wp_id = :w"
                    " ORDER BY generation"
                ),
                {"w": str(wp)},
            )
        )
        .mappings()
        .all()
    )
    return {"working_paper": str(paper), "representations": {r["id"]: r["x"] for r in reps}}


# ════════════════════════════════════════════════════════════════════════════
# module fixture —— **一次** asyncio.run
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


# ════════════════════════════════════════════════════════════════════════════
# 0. 采集完整性
# ════════════════════════════════════════════════════════════════════════════


class TestCollectionIntegrity:
    def test_no_phase_crashed_during_collection(self, snap: dict[str, Any]) -> None:
        """采集阶段异常记录不穿透 —— 但**必须**为空，否则后面的判据整类空跑。"""
        assert snap["harness_errors"] == {}, snap["harness_errors"]

    def test_both_migrations_applied_cleanly(self, snap: dict[str, Any]) -> None:
        assert snap["apply_errors"] == [], snap["apply_errors"][:3]

    def test_lane_declaration_is_source_backed(self, snap: dict[str, Any]) -> None:
        """声明来自真实权威模板与已 reviewed 契约（不是手搓最小 DOCX）。"""
        decl = snap["declaration"]
        assert decl["contract_origin"] in ("production_inventory", "staged_word_lane")
        assert decl["field_count"] >= 16, decl
        assert len(decl["template_sha256"]) == 64
        assert decl["instrumentation_sha256"] != decl["contract_sha256"]


# ════════════════════════════════════════════════════════════════════════════
# 1. 供给真的落库
# ════════════════════════════════════════════════════════════════════════════


class TestWordSupplyLandsInTheDatabase:
    def test_four_definitions_and_one_bundle_are_created(self, snap: dict[str, Any]) -> None:
        """**Validates: Requirements 7.10**"""
        before = snap["supply"]["initial"]
        after = snap["supply"]["after_publish"]
        assert before["working_paper_sync_definition_artifact"] == 0, before
        assert after["working_paper_sync_definition_artifact"] == 4, after
        assert after["working_paper_sync_definition_bundle"] == 1, after

    def test_bundle_binds_the_three_typed_children(self, snap: dict[str, Any]) -> None:
        pub = snap["published"]
        ids = {
            pub["template_definition_id"],
            pub["instrumentation_definition_id"],
            pub["contract_definition_id"],
            pub["authority_definition_id"],
        }
        assert len(ids) == 4, "四个 child 有重复 ⇒ typed slot 不是各自独立的 definition"
        assert len(pub["bundle_sha256"]) == 64

    def test_instrumentation_digest_matches_the_contract_declaration(
        self, snap: dict[str, Any]
    ) -> None:
        """契约声明的 instrumentation digest 与落库 child 逐字节相同（三边锁第一边）。"""
        assert (
            snap["declaration"]["instrumentation_sha256"]
            == snap["published"]["instrumentation_sha256"]
        )


# ════════════════════════════════════════════════════════════════════════════
# 2. candidate 是 non-current，attach 之前不可 finalize
# ════════════════════════════════════════════════════════════════════════════


class TestCandidateStaysNonCurrent:
    def test_upgrader_leaves_both_targets_empty(self, snap: dict[str, Any]) -> None:
        """**Validates: Requirements 6.18 / Property 67**"""
        cand = snap["candidate"]["primary"]
        assert cand["state"] == "awaiting_contract", cand
        assert cand["target_contract_definition_id"] is None
        assert cand["target_definition_bundle_id"] is None
        assert cand["revision_before"] == cand["revision_after"]
        assert cand["pointer_before"] == cand["pointer_after"]

    def test_candidate_registration_did_not_add_a_representation(
        self, snap: dict[str, Any]
    ) -> None:
        assert (
            snap["state"]["after_seed"]["representation_count"]
            == snap["state"]["after_candidate"]["representation_count"]
            == 1
        ), snap["state"]

    def test_finalize_before_attach_is_refused_for_the_right_reason(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 判「拒绝」不能只比异常类型 —— 必须比对**原因**。

        **Validates: Requirements 6.18 / Property 67**
        """
        refusal = snap["refusals"]["before_attach"]
        assert refusal["type"] is not None, "attach 之前竟然 finalize 成功了"
        assert "approved per-entry contract" in refusal["message"] or (
            "缺 approved" in refusal["message"]
        ), refusal["message"]
        assert refusal["state_before"] == refusal["state_after"], refusal


# ════════════════════════════════════════════════════════════════════════════
# 3. 受控 attach 之后前置成立
# ════════════════════════════════════════════════════════════════════════════


class TestAttachThenFinalizable:
    def test_attach_moves_to_ready_without_touching_pointer(
        self, snap: dict[str, Any]
    ) -> None:
        attach = snap["candidate"]["attach"]
        assert attach["from_state"] == "awaiting_contract"
        assert attach["to_state"] == "ready"
        assert attach["revision_unchanged"] is True
        assert attach["pointer_unchanged"] is True
        assert attach["definition_bundle_id"] == snap["published"]["bundle_id"]

    def test_prerequisites_are_satisfied_only_after_attach(
        self, snap: dict[str, Any]
    ) -> None:
        """**Validates: Requirements 6.18**"""
        verdict = snap["candidate"]["finalizable"]
        assert verdict["state"] == "ready"
        assert verdict["target_contract_definition_id"] == (
            snap["published"]["contract_definition_id"]
        )
        assert verdict["target_definition_bundle_id"] == snap["published"]["bundle_id"]


# ════════════════════════════════════════════════════════════════════════════
# 4. 三种越权各自被拒，且 pointer/revision 逐值不变
# ════════════════════════════════════════════════════════════════════════════

REFUSAL_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "wrong_frozen_bundle_digest",
        "word_entry_frozen_bundle_digest_mismatch",
        "canonical digest",
    ),
    (
        "foreign_instrumentation_payload",
        "word_entry_instrumentation_digest_mismatch",
        "instrumentation slot digest",
    ),
    (
        "foreign_entry_id",
        "word_entry_finalize_gate_blocked",
        "不得用另一个 entry 的 candidate finalize",
    ),
    (
        "foreign_staged_bytes",
        "word_entry_finalize_gate_blocked",
        "禁跨 entry 复用 candidate 字节",
    ),
    (
        "mismatched_instrumented_digest",
        "word_entry_candidate_evidence_invalid",
        "往返证据与将要发布的字节不是同一份",
    ),
    (
        "tampered_rollback_digest",
        "word_entry_candidate_evidence_invalid",
        "回滚源必须可追溯",
    ),
)


class TestRefusalsAreReasonScoped:
    @pytest.mark.parametrize("label,code,needle", REFUSAL_CASES)
    def test_each_refusal_has_its_own_error_code_and_reason(
        self, snap: dict[str, Any], label: str, code: str, needle: str
    ) -> None:
        """🔴 每条拒绝比对 **error_code + 原因文案**，不只比异常类型。

        同一异常类型在本 gate 里有多个来源，短路一条会被另一条接住 ⇒ 只断言类型的
        守卫会判 GREEN（Task 76 首轮实测的三条 GREEN 之一）。

        **Validates: Requirements 6.10 / 7.10 / Property 28**
        """
        refusal = snap["refusals"][label]
        assert refusal["type"] is not None, f"{label} 竟然通过了"
        assert refusal["error_code"] == code, refusal
        assert needle in refusal["message"], refusal["message"]

    @pytest.mark.parametrize("label,_code,_needle", REFUSAL_CASES)
    def test_refusal_leaves_pointer_and_revision_verbatim(
        self, snap: dict[str, Any], label: str, _code: str, _needle: str
    ) -> None:
        """失败时 pointer 与 `content_revision` 逐字不变。

        **Validates: Requirements 6.18 / Property 67**
        """
        refusal = snap["refusals"][label]
        assert refusal["state_before"] == refusal["state_after"], refusal

    def test_refusal_codes_and_reasons_are_both_load_bearing(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 code 至少三类互不相同，**原因**六条各不相同。

        为什么不是「六条 code 全不同」：`foreign_entry_id` 与 `foreign_staged_bytes`
        本就是同一类拒绝（entry scope 不符）的两个来源 —— 一个在 candidate **行**上、
        一个在 staged **字节**上。硬要它们 code 不同会造出一个没有语义的分类；
        真正要锁住的是「短路一条时另一条不会替它顶住」，那靠**原因**分辨
        （Task 76 首轮三条 GREEN 的第一条教训）。
        """
        codes = [snap["refusals"][label]["error_code"] for label, _c, _n in REFUSAL_CASES]
        needles = [n for _l, _c, n in REFUSAL_CASES]
        assert len(REFUSAL_CASES) == 6, REFUSAL_CASES
        assert len(set(codes)) >= 3, codes
        assert len(set(needles)) == 6, needles
        for label, _code, needle in REFUSAL_CASES:
            others = [n for _l, _c, n in REFUSAL_CASES if n != needle]
            message = snap["refusals"][label]["message"]
            assert needle in message, (label, message)
            assert not [n for n in others if n in message], (
                f"{label} 的错误文案同时命中了别的原因 ⇒ 原因不可分辨"
            )


# ════════════════════════════════════════════════════════════════════════════
# 5. 真 finalize：新代际 + 同 content version + revision 不变
# ════════════════════════════════════════════════════════════════════════════


class TestFinalizeCreatesANewGeneration:
    def test_finalize_succeeded(self, snap: dict[str, Any]) -> None:
        """**Validates: Requirements 6.18 / 12.5**"""
        assert "outcome" in snap["finalize"], snap["harness_errors"]
        outcome = snap["finalize"]["outcome"]
        assert outcome["entry_id"] == snap["entry_id"]
        assert snap["finalize"]["revision_unchanged"] is True

    def test_a_second_generation_exists_for_the_same_content_version(
        self, snap: dict[str, Any]
    ) -> None:
        """同一 content version 的**新** immutable representation generation。

        **Validates: Requirements 6.18 / Property 67**
        """
        rows = snap["representation"]["rows"]
        assert len(rows) == 2, rows
        assert [r["generation"] for r in rows] == ["1", "2"], rows
        assert rows[0]["content_version_id"] == rows[1]["content_version_id"], (
            "新代际换了 content version ⇒ 制造了伪业务 revision"
        )
        assert rows[1]["document_type"] == "docx"

    def test_content_revision_never_moved(self, snap: dict[str, Any]) -> None:
        """**Validates: Requirements 6.18 / Property 67**"""
        states = [
            snap["state"]["after_seed"],
            snap["state"]["after_candidate"],
            snap["state"]["before_finalize"],
            snap["state"]["after_finalize"],
        ]
        revisions = {s["content_revision"] for s in states}
        assert revisions == {0}, revisions

    def test_pointer_switched_to_the_new_generation(self, snap: dict[str, Any]) -> None:
        rows = snap["representation"]["rows"]
        before = snap["state"]["before_finalize"]["pointer"]
        after = snap["state"]["after_finalize"]["pointer"]
        assert before is not None and after is not None
        assert before != after, "pointer 没切到新代际"
        assert before == rows[0]["id"], (before, rows[0])
        assert after == rows[1]["id"], (after, rows[1])

    def test_published_bytes_are_the_candidate_bytes_verbatim(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 发布的字节与 candidate **逐字节相同** ⇒ 没有用模板重生成。

        这是「不得用模板重生成覆盖审计师已编辑的 Word-only 正文」在真库上的可观察形态。

        **Validates: Requirements 7.3**
        """
        rows = snap["representation"]["rows"]
        assert rows[1]["artifact_sha256"] == snap["candidate"]["primary"][
            "staged_artifact_sha256"
        ], (rows[1]["artifact_sha256"], snap["candidate"]["primary"])
        assert rows[1]["artifact_sha256"] != snap["seed"]["legacy_artifact_sha256"], (
            "新代际的字节与存量 representation 相同 ⇒ instrumentation 没生效"
        )

    def test_identity_columns_are_tag_shaped(self, snap: dict[str, Any]) -> None:
        """`adapter_id` = 契约 id；structure/identity digest 非空且与存量不同。

        **Validates: Requirements 7.10**
        """
        rows = snap["representation"]["rows"]
        assert rows[1]["adapter_id"] == snap["entry_id"], rows[1]
        for column in ("structure_hash", "identity_inventory_sha256"):
            assert len(rows[1][column]) == 64, rows[1]
            assert rows[1][column] != rows[0][column], column

    def test_new_generation_binds_the_frozen_bundle(self, snap: dict[str, Any]) -> None:
        """**Validates: Requirements 7.10 / Property 28**"""
        rows = snap["representation"]["rows"]
        assert rows[1]["definition_bundle_id"] == snap["published"]["bundle_id"]

    def test_existing_rows_were_not_rewritten(self, snap: dict[str, Any]) -> None:
        """`xmin` 逐行不变 ⇒ 既有行没被改写（不是「看起来没变」）。

        **Validates: Requirements 6.18 / Property 67**
        """
        before = snap["xmin"]["before_finalize"]
        after = snap["xmin"]["after_finalize"]
        assert before["working_paper"] == after["working_paper"], (before, after)
        for rid, xmin in before["representations"].items():
            assert after["representations"][rid] == xmin, (rid, xmin)

    def test_candidate_is_finalized_and_still_not_consumable(
        self, snap: dict[str, Any]
    ) -> None:
        """candidate 变 finalized，但**永不**进 resolver / download。

        **Validates: Requirements 6.18 / Property 67**
        """
        assert snap["candidate"]["after_finalize"]["state"] == "finalized"
        assert snap["resolver"]["candidate_consumable"] is False
        assert "CandidateNotResolvable" in snap["resolver"]["refusal"], snap["resolver"]

    def test_second_finalize_is_refused(self, snap: dict[str, Any]) -> None:
        """已 finalize 的 candidate 不得再 finalize（不可变代际）。

        **Validates: Requirements 6.18**
        """
        refusal = snap["refusals"]["second_finalize"]
        assert refusal["type"] is not None, "同一 candidate 被 finalize 了两次"
        assert refusal["state_before"] == refusal["state_after"], refusal


# ════════════════════════════════════════════════════════════════════════════
# 6. Property 收束（真库侧）
# ════════════════════════════════════════════════════════════════════════════


class TestProperties:
    def test_property_28_frozen_identity_is_enforced_on_real_rows(
        self, snap: dict[str, Any]
    ) -> None:
        """**Validates: Requirements 6.10**"""
        assert snap["refusals"]["wrong_frozen_bundle_digest"]["error_code"] == (
            "word_entry_frozen_bundle_digest_mismatch"
        )
        assert snap["refusals"]["foreign_instrumentation_payload"]["error_code"] == (
            "word_entry_instrumentation_digest_mismatch"
        )

    def test_property_31_word_only_equivalence_ran_with_real_coverage(
        self, snap: dict[str, Any]
    ) -> None:
        """Word-only 等值在真实权威模板派生的 candidate 上跑过且覆盖非空。

        **Validates: Requirements 7.3**
        """
        coverage = snap["finalize"]["outcome"]["roundtrip"]["word_only_coverage"]
        for name in ("outside_sdt_text", "sdt_tag_set", "sdt_hierarchy", "protected_parts"):
            assert int(coverage[name]) > 0, coverage

    def test_property_34_no_degradation_happened_on_the_success_path(
        self, snap: dict[str, Any]
    ) -> None:
        """成功路径上 tag 一个不少（tag 集合与冻结清册等值）。

        **Validates: Requirements 7.8**
        """
        observation = snap["finalize"]["outcome"]["roundtrip"]["observation"]
        inventory = snap["finalize"]["outcome"]["definitions"]["inventory"]
        assert observation["tags"] == inventory["tags"], (observation, inventory)
        assert observation["managed_instance_total"] == inventory["managed_instance_total"]

    def test_property_67_full_order_held(self, snap: dict[str, Any]) -> None:
        """P67 全序：candidate → approved bundle → finalize，且失败不动 pointer。

        **Validates: Requirements 6.18**
        """
        assert snap["candidate"]["primary"]["state"] == "awaiting_contract"
        assert snap["candidate"]["attach"]["to_state"] == "ready"
        assert snap["candidate"]["after_finalize"]["state"] == "finalized"
        assert snap["state"]["after_finalize"]["representation_count"] == 2
        for label in ("before_attach", "wrong_frozen_bundle_digest", "foreign_entry_id"):
            refusal = snap["refusals"][label]
            assert refusal["state_before"] == refusal["state_after"], label
