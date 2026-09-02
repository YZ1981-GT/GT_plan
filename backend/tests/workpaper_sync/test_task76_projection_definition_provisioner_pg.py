r"""Task 76 真实 PostgreSQL 守卫：四张供给表 0 → 真实行、幂等重跑零新增、candidate 受控 attach。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 76
点名 Property：**4 / 5 / 10 / 28 / 67**
点名 AC：2.1 · 2.3 · 2.4 · 3.3 · 3.4 · 3.6 · 6.10 · 6.18 · 12.1

═══ 这一半证的是「真的落库了 + 真的幂等 + 真的拒得住」 ═══

离线守卫证判据正确，但纯 AST 判据**可能守着一段死代码**。本文件在真库上证明：

* `template → instrumentation → contract → bundle` 五段（含 authority model）真发布成
  **4 行 definition + 1 行 non-null bundle**，三个 typed slot 全是 approved `definition`，
  bundle digest 与 canonical bytes 逐字节自洽；
* **同一 `(project_id, wp_id, entry)` 重跑**：`created_stages` 空、`reused_stages` 五段全中、
  四张表行数逐表相等、`content_revision` 与 entry pointer 逐值不变（Property 4 / 10）；
* 存量 representation 绑旧 bundle 时，`awaiting_contract` candidate 经**受控 attach**
  进入 `ready`，两个 target FK 落到本次 approved contract/bundle，append-only 事件
  `sequence_no=1` 写入且 `UPDATE` / `DELETE` 被 DB 触发器拒（Property 67）；
* attach **拒得住**四种越权：已 finalize 的 candidate、跨 entry 的 candidate、
  非 approved contract、bundle 的 contract child 与 target 不符；
* 伪造 uuid（五形态之①）在**落库之前**被拒并指出首个非法 slot（Property 28）；
* attach 之后 `assert_candidate_finalizable` 才通过，但 candidate **仍不是 current**、
  representation 一行没多、`working_paper` 与既有 representation 行的 `xmin` 不变
  （Property 5 / 67：attach 只补前置，不代 finalize）。

═══ 隔离与采集 ═══

scratch schema `tmp_task76_prov_<hex>` + 独立文件根，结束 `DROP SCHEMA CASCADE` + `rmtree`。
全部场景由**一次 `asyncio.run`** 跑完落进快照（module fixture）—— 每个测试各自开 async
会污染共享连接池（Task 21~29 实测：第二个起 `NoneType has no attribute send`）。
采集阶段异常一律**记录不穿透**：穿透会把整个 module 变成 collection ERROR，而 `-rf`
只列 FAILED 不列 ERROR ⇒ 定向变异看不到预期失败项 ⇒ 判 GREEN。
`test_no_phase_crashed_during_collection` 是这个决定的另一半。

用法（仓库根）::

    .\.venv\Scripts\python.exe -m pytest \
        backend/tests/workpaper_sync/test_task76_projection_definition_provisioner_pg.py -q
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

if str(BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_task76_prov_"
#: 本 pilot 的 entry（从交付登记表现取，不写死字符串）。
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


def _pilot_entry_id() -> str:
    from app.services.workpaper_sync.adapters import registry as RG

    rows = [
        str(row["entry_id"])
        for row in RG.DELIVERED_PER_ENTRY_CONTRACTS
        if str(row.get("pilot_class")) == "simple_checklist"
    ]
    if len(rows) != 1:
        raise _HarnessError(f"simple_checklist pilot 现算到 {len(rows)} 条 entry ⇒ 分母可疑")
    return rows[0]


async def _seed_legacy_bundle(repo: Any, artifacts: Any, project: Any, wp: Any) -> dict[str, Any]:
    """存量（pre-instrumentation）approved bundle —— 与 Task 17 的 baseline 播种同款。

    存量 representation 必须绑**旧** bundle：绑本次 bundle 时 `reused_current` 分支会先
    命中，attach 分支永不执行 ⇒ 本文件最重要的一段会空跑。
    """
    from app.services.workpaper_sync import definitions as D
    from app.services.workpaper_sync.models import ArtifactKind, ArtifactState, BundleSlot

    blobs = {
        name: artifacts.publish_definition_blob(
            project_id=project,
            wp_id=wp,
            definition_kind=kind,
            payload=('{"seed":"%s"}' % name).encode("utf-8"),
        )
        for name, kind in {
            "tpl": "template",
            "instr": "instrumentation",
            "contract": "contract",
            "authority": "authority_model",
            "bundle": "bundle",
        }.items()
    }
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
    tpl = await repo.create_definition_artifact(
        kind="template",
        logical_id="t76.legacy.tpl",
        semantic_version="0.9.0",
        blob_artifact_id=art["tpl"].id,
        sha256=_d("t76-legacy-template"),
        structure_hash=_d("t76-legacy-structure"),
        source_commit="t76-legacy",
    )
    instr = await repo.create_definition_artifact(
        kind="instrumentation",
        logical_id="t76.legacy.instr",
        semantic_version="0.9.0",
        blob_artifact_id=art["instr"].id,
        sha256=_d("t76-legacy-instrumentation"),
        source_commit="t76-legacy",
    )
    contract = await repo.create_definition_artifact(
        kind="contract",
        logical_id="t76.legacy.contract",
        semantic_version="0.9.0",
        blob_artifact_id=art["contract"].id,
        sha256=_d("t76-legacy-contract"),
        source_commit="t76-legacy",
    )
    authority = await repo.create_definition_artifact(
        kind="authority_model",
        logical_id="t76.legacy.authority",
        semantic_version="0.9.0",
        blob_artifact_id=art["authority"].id,
        sha256=_d("t76-legacy-authority"),
        authority_model_type="projection_contract",
        source_commit="t76-legacy",
    )

    def _slots() -> dict[Any, Any]:
        return {
            BundleSlot.template: D.definition_slot_spec(
                BundleSlot.template, definition_id=tpl.id, definition_sha256=tpl.sha256
            ),
            BundleSlot.instrumentation: D.definition_slot_spec(
                BundleSlot.instrumentation,
                definition_id=instr.id,
                definition_sha256=instr.sha256,
            ),
            BundleSlot.contract: D.definition_slot_spec(
                BundleSlot.contract,
                definition_id=contract.id,
                definition_sha256=contract.sha256,
            ),
        }

    bundle = await repo.create_definition_bundle(
        authority_model_definition_id=authority.id,
        slots=_slots(),
        canonical_payload_artifact_id=art["bundle"].id,
        canonical_payload_sha256=D.bundle_canonical_digest(
            authority_model="projection_contract",
            authority_model_definition_sha256=authority.sha256,
            slots=_slots(),
        ),
    )
    return {
        "bundle_id": bundle.id,
        "authority_id": authority.id,
        "contract_id": contract.id,
    }


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - 一次采集覆盖全部阶段
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.services.workpaper_sync import projection_provisioning as PP
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.models import CandidateState
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import (
        CanonicalResolutionService,
        ResolutionIntent,
    )

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 76 的判据是「四张供给表真的从 0 变成有真实行」「幂等重跑零新增」"
            "「attach 的 append-only 事件被 DB 触发器锁住」，全部依赖真实表与 V151/V153 的 "
            f"CHECK/trigger；必须真实 PostgreSQL，当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    for migration in MIGRATIONS:
        if not migration.exists():
            raise _HarnessError(f"缺少迁移文件: {migration}")

    entry = _pilot_entry_id()
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task76_store_"))
    (base_root / "storage").mkdir()
    (base_root / "definition_store").mkdir()
    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "entry_id": entry,
        "apply_errors": [],
        "harness_errors": {},
        "counts": {},
        "runs": {},
        "refusals": {},
        "candidate": {},
        "events": [],
        "event_mutation": {},
        "bundle_row": {},
        "xmin": {},
        "finalizable": {},
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

        project, wp, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{project}')")
            await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{user}')")
            await conn.exec_driver_sql(
                f"INSERT INTO working_paper (id, project_id) VALUES ('{wp}', '{project}')"
            )
        artifacts = CanonicalArtifactRepository(base_root)
        snap["ids"] = {"project": str(project), "wp": str(wp), "user": str(user)}

        def _provisioner(session: Any) -> Any:
            return PP.ProjectionDefinitionProvisioner(
                session=session,
                repository=WorkpaperSyncRepository(session),
                artifacts=artifacts,
                project_id=project,
                wp_id=wp,
            )

        async with Session() as session:
            snap["counts"]["initial"] = await PP.count_supply_rows(session)

        # ── 阶段 1：首次 provision（四表 0 → 真实行）───────────────────────
        try:
            async with Session() as session:
                outcome = await _provisioner(session).ensure(entry_id=entry)
                await session.commit()
            snap["runs"]["first"] = outcome.as_dict()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("first_provision", exc)
        async with Session() as session:
            snap["counts"]["after_first"] = await PP.count_supply_rows(session)

        # ── 阶段 2：幂等重跑（零新增）─────────────────────────────────────
        try:
            async with Session() as session:
                outcome2 = await _provisioner(session).ensure(entry_id=entry)
                await session.commit()
            snap["runs"]["second"] = outcome2.as_dict()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("second_provision", exc)
        async with Session() as session:
            snap["counts"]["after_second"] = await PP.count_supply_rows(session)
            row = (
                await session.execute(
                    sa.text(
                        "SELECT b.state, b.canonical_payload_sha256,"
                        " b.template_slot_type, b.instrumentation_slot_type,"
                        " b.contract_slot_type, b.template_slot_ref,"
                        " b.instrumentation_slot_ref, b.contract_slot_ref,"
                        " b.template_slot_digest, b.instrumentation_slot_digest,"
                        " b.contract_slot_digest, b.authority_model_definition_sha256,"
                        " am.kind AS am_kind, am.state AS am_state,"
                        " am.authority_model_type AS am_type, am.sha256 AS am_sha"
                        " FROM working_paper_sync_definition_bundle b"
                        " JOIN working_paper_sync_definition_artifact am"
                        " ON am.id = b.authority_model_definition_id"
                        " WHERE b.id = :b"
                    ),
                    {"b": snap["runs"]["first"]["definition_bundle_id"]},
                )
            ).mappings().first()
            snap["bundle_row"] = dict(row or {})
            children = (
                await session.execute(
                    sa.text(
                        "SELECT kind, state, sha256, id FROM"
                        " working_paper_sync_definition_artifact ORDER BY kind"
                    )
                )
            ).mappings().all()
            snap["children"] = [dict(r) for r in children]

        # ── 阶段 3：播种存量 content version + representation + candidate ──
        try:
            async with Session() as session:
                repo = WorkpaperSyncRepository(session)
                projection = artifacts.publish_projection(
                    revision=0,
                    staged=artifacts.stage_bytes(
                        project_id=project,
                        wp_id=wp,
                        payload=b"t76-projection-v0",
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
                staged_legacy = artifacts.stage_bytes(
                    project_id=project,
                    wp_id=wp,
                    payload=b"PK\x03\x04t76-legacy-xlsx",
                    document_type="xlsx",
                )
                art_legacy = await repo.register_artifact(
                    project_id=project,
                    wp_id=wp,
                    kind="canonical",
                    state="published",
                    relative_path=staged_legacy.relative_path,
                    sha256=staged_legacy.sha256,
                    size_bytes=staged_legacy.size_bytes,
                    document_type="xlsx",
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
                legacy = await _seed_legacy_bundle(repo, artifacts, project, wp)
                representation = await repo.create_representation(
                    project_id=project,
                    wp_id=wp,
                    entry_id=entry,
                    content_version_id=content_version.id,
                    generation=1,
                    document_type="xlsx",
                    artifact_id=art_legacy.id,
                    artifact_sha256=art_legacy.sha256,
                    definition_bundle_id=legacy["bundle_id"],
                    authority_model_definition_id=legacy["authority_id"],
                    adapter_id="t76.legacy",
                    adapter_build_digest=_d("t76-legacy-build"),
                    structure_hash=_d("t76-legacy-structure"),
                    identity_inventory_sha256=_d("t76-legacy-inventory"),
                    reason="content_commit",
                )
                await repo.set_entry_pointer(
                    wp_id=wp, entry_id=entry, representation_id=representation.id, generation=1
                )
                staged_candidate = artifacts.stage_bytes(
                    project_id=project,
                    wp_id=wp,
                    payload=b"PK\x03\x04t76-instrumented",
                    document_type="xlsx",
                )
                art_candidate = await repo.register_artifact(
                    project_id=project,
                    wp_id=wp,
                    kind="upgrade_candidate",
                    state="candidate",
                    relative_path=staged_candidate.relative_path,
                    sha256=staged_candidate.sha256,
                    size_bytes=staged_candidate.size_bytes,
                    document_type="xlsx",
                )
                candidate = await repo.create_upgrade_candidate(
                    project_id=project,
                    wp_id=wp,
                    entry_id=entry,
                    content_version_id=content_version.id,
                    source_representation_id=representation.id,
                    staged_artifact_id=art_candidate.id,
                    staged_artifact_sha256=art_candidate.sha256,
                    template_definition_id=uuid.UUID(
                        snap["runs"]["first"]["template_definition_id"]
                    ),
                    instrumentation_definition_id=uuid.UUID(
                        snap["runs"]["first"]["instrumentation_definition_id"]
                    ),
                    state=CandidateState.awaiting_contract,
                )
                # 与 `ExcelInstrumentationUpgrader.stage_and_register_candidate` 的收尾
                # 两行一致：compatibility 报告 digest 由 upgrader 写，不是本任务的产物。
                # 不写这两列时 `assert_candidate_finalizable` 会停在 compatibility 那一条，
                # 于是「attach 到底补齐了哪一格」就分辨不出来。
                candidate.visible_equivalence_report_sha256 = _d("t76-equivalence-report")
                candidate.rollback_source_sha256 = _d("t76-rollback-source")
                await session.flush()
                await session.commit()
            snap["seed"] = {
                "content_version_id": str(content_version.id),
                "representation_id": str(representation.id),
                "candidate_id": str(candidate.id),
                "legacy_bundle_id": str(legacy["bundle_id"]),
                "legacy_contract_id": str(legacy["contract_id"]),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("seed", exc)
        async with Session() as session:
            snap["counts"]["after_seed"] = await PP.count_supply_rows(session)
            snap["xmin"]["after_seed"] = await _xmin_probe(session, sa, wp)

        # ── 阶段 4：attach 前 finalize 不可（缺 approved contract）─────────
        try:
            async with Session() as session:
                resolution = CanonicalResolutionService(session, artifacts)
                try:
                    await resolution.assert_candidate_finalizable(
                        uuid.UUID(snap["seed"]["candidate_id"])
                    )
                    snap["finalizable"]["before_attach"] = "ALLOWED"
                except Exception as exc:  # noqa: BLE001 - 记录类型即判据
                    snap["finalizable"]["before_attach"] = type(exc).__name__
                    snap["finalizable"]["before_attach_message"] = str(exc)[:200]
                try:
                    await resolution.assert_candidate_not_consumable(
                        candidate_id=uuid.UUID(snap["seed"]["candidate_id"]),
                        intent=ResolutionIntent.materialize,
                    )
                    snap["resolver"]["candidate_consumable"] = "ALLOWED"
                except Exception as exc:  # noqa: BLE001
                    snap["resolver"]["candidate_consumable"] = type(exc).__name__
        except Exception as exc:  # noqa: BLE001
            _phase_failed("pre_attach_gates", exc)

        # ── 阶段 5：受控 attach（awaiting_contract → ready）────────────────
        try:
            async with Session() as session:
                outcome3 = await _provisioner(session).ensure(entry_id=entry, actor_id=user)
                await session.commit()
            snap["runs"]["attach"] = outcome3.as_dict()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("attach", exc)
        async with Session() as session:
            snap["counts"]["after_attach"] = await PP.count_supply_rows(session)
            snap["xmin"]["after_attach"] = await _xmin_probe(session, sa, wp)
            snap["candidate"] = dict(
                (
                    await session.execute(
                        sa.text(
                            "SELECT id, state, target_contract_definition_id,"
                            " target_definition_bundle_id, finalized_representation_id"
                            " FROM working_paper_representation_upgrade_candidate"
                            " WHERE id = :c"
                        ),
                        {"c": snap["seed"]["candidate_id"]},
                    )
                ).mappings().first()
                or {}
            )
            snap["events"] = [
                dict(r)
                for r in (
                    await session.execute(
                        sa.text(
                            "SELECT sequence_no, event_type, from_state, to_state,"
                            " contract_definition_id, definition_bundle_id,"
                            " definition_bundle_sha256, correlation_id, actor_id"
                            " FROM working_paper_representation_candidate_event"
                            " ORDER BY sequence_no"
                        )
                    )
                ).mappings().all()
            ]
            snap["pointer_after_attach"] = str(
                (
                    await session.execute(
                        sa.text(
                            "SELECT current_representation_id FROM"
                            " working_paper_sync_entry_state WHERE wp_id = :w"
                            " AND entry_id = :e"
                        ),
                        {"w": str(wp), "e": entry},
                    )
                ).scalar_one_or_none()
            )

        # ── 阶段 6：attach 后 finalize 前置补齐但 candidate 仍非 current ───
        try:
            async with Session() as session:
                resolution = CanonicalResolutionService(session, artifacts)
                try:
                    cand = await resolution.assert_candidate_finalizable(
                        uuid.UUID(snap["seed"]["candidate_id"])
                    )
                    snap["finalizable"]["after_attach"] = "ALLOWED"
                    snap["finalizable"]["after_attach_state"] = str(cand.state)
                except Exception as exc:  # noqa: BLE001
                    snap["finalizable"]["after_attach"] = type(exc).__name__
                    snap["finalizable"]["after_attach_message"] = str(exc)[:300]
        except Exception as exc:  # noqa: BLE001
            _phase_failed("post_attach_gates", exc)

        # ── 阶段 7：attach 幂等重跑（reused_candidate、零新增）─────────────
        try:
            async with Session() as session:
                outcome4 = await _provisioner(session).ensure(entry_id=entry, actor_id=user)
                await session.commit()
            snap["runs"]["after_attach"] = outcome4.as_dict()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("post_attach_provision", exc)
        async with Session() as session:
            snap["counts"]["final"] = await PP.count_supply_rows(session)
            snap["events_final"] = int(
                (
                    await session.execute(
                        sa.text(
                            "SELECT count(*) FROM"
                            " working_paper_representation_candidate_event"
                        )
                    )
                ).scalar_one()
            )

        # ── 阶段 8：append-only 事件表拒 UPDATE / DELETE ───────────────────
        for op, stmt in (
            (
                "update",
                "UPDATE working_paper_representation_candidate_event"
                " SET to_state = 'finalized'",
            ),
            ("delete", "DELETE FROM working_paper_representation_candidate_event"),
        ):
            try:
                async with engine.begin() as conn:
                    await conn.exec_driver_sql(stmt)
                snap["event_mutation"][op] = "ALLOWED"
            except Exception as exc:  # noqa: BLE001 - 被拒即判据
                snap["event_mutation"][op] = type(exc).__name__

        # ── 阶段 9：attach 的四种越权各拒一次 ─────────────────────────────
        await _collect_refusals(
            snap=snap,
            Session=Session,
            sa=sa,
            project=project,
            wp=wp,
            entry=entry,
            artifacts=artifacts,
        )

        # ── 阶段 10：伪造 uuid（形态①）在落库之前被拒 ─────────────────────
        try:
            from app.services.workpaper_sync import definitions as D
            from app.services.workpaper_sync.models import AuthorityModel, BundleSlot

            async with Session() as session:
                slots = {
                    slot: D.definition_slot_spec(
                        slot,
                        definition_id=uuid.UUID(
                            snap["runs"]["first"][f"{slot.value}_definition_id"]
                        ),
                        definition_sha256=snap["runs"]["first"][f"{slot.value}_definition_sha256"],
                    )
                    for slot in BundleSlot
                }
                # template slot 换成一个**库里不存在**的 uuid（digest 保持真值）
                slots[BundleSlot.template] = D.definition_slot_spec(
                    BundleSlot.template,
                    definition_id=uuid.uuid4(),
                    definition_sha256=snap["runs"]["first"]["template_definition_sha256"],
                )
                contract = __import__(
                    "app.services.workpaper_sync.pilot_simple_checklist",
                    fromlist=["load_pilot_contract"],
                ).load_pilot_contract()
                try:
                    await PP.assert_projection_supply_authentic(
                        session=session,
                        entry_id=entry,
                        authority_model=AuthorityModel.projection_contract,
                        authority_model_definition_sha256=snap["runs"]["first"][
                            "authority_model_definition_sha256"
                        ],
                        slots=slots,
                        contract_payload=contract.canonical_payload,
                    )
                    snap["refusals"]["forged_uuid"] = {"outcome": "ALLOWED"}
                except Exception as exc:  # noqa: BLE001
                    snap["refusals"]["forged_uuid"] = {
                        "outcome": type(exc).__name__,
                        "message": str(exc)[:300],
                    }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("forged_uuid", exc)

        return snap
    finally:
        try:
            if engine is not None:
                await engine.dispose()
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await admin.dispose()
            shutil.rmtree(base_root, ignore_errors=True)


async def _xmin_probe(session: Any, sa: Any, wp: uuid.UUID) -> dict[str, list[str]]:
    """既有行「没被 UPDATE」的证据（`xmin` 逐行相等即证明未重写）。"""
    out: dict[str, list[str]] = {}
    for table in (
        "working_paper",
        "working_paper_content_version",
        "working_paper_content_representation",
        "working_paper_sync_entry_state",
    ):
        column = "id" if table == "working_paper" else "wp_id"
        rows = (
            await session.execute(
                sa.text(  # noqa: S608 - 表名来自本文件内的封闭元组
                    f"SELECT xmin::text AS x FROM {table} WHERE {column} = :w ORDER BY x"
                ),
                {"w": str(wp)},
            )
        ).all()
        out[table] = [str(r[0]) for r in rows]
    return out


async def _collect_refusals(
    *,
    snap: dict[str, Any],
    Session: Any,
    sa: Any,
    project: uuid.UUID,
    wp: uuid.UUID,
    entry: str,
    artifacts: Any,
) -> None:
    """attach 的四种越权（已 finalize / 跨 entry / 非 approved contract / bundle 不符）。"""
    from app.services.workpaper_sync import projection_provisioning as PP
    from app.services.workpaper_sync.models import CandidateState
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository

    first = snap["runs"]["first"]
    contract_id = uuid.UUID(first["contract_definition_id"])
    bundle_id = uuid.UUID(first["definition_bundle_id"])
    candidate_id = uuid.UUID(snap["seed"]["candidate_id"])

    snap.setdefault("refusal_messages", {})

    async def _attach(*, commit: bool = False, label: str = "", **kwargs: Any) -> str:
        async with Session() as session:
            service = PP.CandidateDefinitionAttachService(
                session=session, repository=WorkpaperSyncRepository(session)
            )
            try:
                await service.attach(
                    wp_id=kwargs.get("wp_id", wp),
                    entry_id=kwargs.get("entry_id", entry),
                    candidate_id=kwargs.get("candidate_id", candidate_id),
                    contract_definition_id=kwargs.get("contract_definition_id", contract_id),
                    definition_bundle_id=kwargs.get("definition_bundle_id", bundle_id),
                    correlation_id="t76-refusal-probe",
                )
                if commit:
                    await session.commit()
                    return "COMMITTED"
                await session.rollback()
                return "ALLOWED"
            except Exception as exc:  # noqa: BLE001 - 被拒即判据
                await session.rollback()
                # 🔴 只记异常类型不够：同一 `BundleIntegrityError` 可能来自四条不同判据，
                # 短路其中一条时另一条会接住 ⇒ 「反正拒了」的判据判不出守卫缺陷
                # （本轮变异 M17 实测 GREEN）。故连**原因**一起记。
                snap["refusal_messages"][label or "default"] = str(exc)[:300]
                return type(exc).__name__

    async def _spare_candidate(label: str) -> uuid.UUID:
        """再造一个 `awaiting_contract` candidate（每个越权场景各用一个，互不干扰）。"""
        async with Session() as session:
            repo = WorkpaperSyncRepository(session)
            staged = artifacts.stage_bytes(
                project_id=project,
                wp_id=wp,
                payload=f"PK\x03\x04t76-{label}".encode("utf-8"),
                document_type="xlsx",
            )
            art = await repo.register_artifact(
                project_id=project,
                wp_id=wp,
                kind="upgrade_candidate",
                state="candidate",
                relative_path=staged.relative_path,
                sha256=staged.sha256,
                size_bytes=staged.size_bytes,
                document_type="xlsx",
            )
            spare = await repo.create_upgrade_candidate(
                project_id=project,
                wp_id=wp,
                entry_id=entry,
                content_version_id=uuid.UUID(snap["seed"]["content_version_id"]),
                source_representation_id=uuid.UUID(snap["seed"]["representation_id"]),
                staged_artifact_id=art.id,
                staged_artifact_sha256=staged.sha256,
                template_definition_id=uuid.UUID(first["template_definition_id"]),
                instrumentation_definition_id=uuid.UUID(first["instrumentation_definition_id"]),
                state=CandidateState.awaiting_contract,
            )
            spare.visible_equivalence_report_sha256 = _d(f"t76-equivalence-{label}")
            spare.rollback_source_sha256 = _d(f"t76-rollback-{label}")
            await session.flush()
            await session.commit()
            return spare.id

    # ① 已 ready（本轮 attach 之后）的 candidate 再 attach —— 只接受 awaiting_contract
    snap["refusals"]["already_attached"] = await _attach(label="already_attached")

    # ② 跨 entry：同一 candidate 换一个 entry_id
    snap["refusals"]["cross_entry"] = await _attach(
        entry_id=f"{entry}/other", label="cross_entry"
    )

    # ③ contract 与 bundle 的 contract child 不符（用 legacy 的 approved contract）。
    #    必须用**未 attach 的** candidate：state 判据在语义判据之前，已 ready 的
    #    candidate 会先被状态边拒掉，于是这条判据永远不可达（本轮实测踩到）。
    try:
        mismatch_candidate = await _spare_candidate("mismatch")
        snap["refusals"]["contract_bundle_mismatch"] = await _attach(
            candidate_id=mismatch_candidate,
            contract_definition_id=uuid.UUID(snap["seed"]["legacy_contract_id"]),
            label="contract_bundle_mismatch",
        )
        snap["refusals"]["mismatch_candidate_id"] = str(mismatch_candidate)
    except Exception as exc:  # noqa: BLE001
        snap["harness_errors"]["mismatch_setup"] = _err(exc)

    # ③b 未 approved 的 contract（generator 候选态）不得绑定 —— 与 ③ 同类型不同原因，
    #     故判据必须比对**原因**而不只是异常类型。
    try:
        async with Session() as session:
            repo = WorkpaperSyncRepository(session)
            blob = artifacts.publish_definition_blob(
                project_id=project,
                wp_id=wp,
                definition_kind="contract",
                payload=b'{"seed":"unapproved-contract"}',
            )
            art = await repo.register_artifact(
                project_id=project,
                wp_id=wp,
                kind="definition",
                state="published",
                relative_path=blob.relative_path,
                sha256=blob.sha256,
                size_bytes=blob.size_bytes,
                document_type=blob.document_type,
                retention_class="definition",
            )
            unapproved = await repo.create_definition_artifact(
                kind="contract",
                logical_id="t76.unapproved.contract",
                semantic_version="0.0.1",
                blob_artifact_id=art.id,
                sha256=_d("t76-unapproved-contract"),
                source_commit="t76-unapproved",
                approved=False,
            )
            await session.commit()
            unapproved_id = unapproved.id
        unapproved_candidate = await _spare_candidate("unapproved")
        snap["refusals"]["unapproved_contract"] = await _attach(
            candidate_id=unapproved_candidate,
            contract_definition_id=unapproved_id,
            label="unapproved_contract",
        )
    except Exception as exc:  # noqa: BLE001
        snap["harness_errors"]["unapproved_contract_setup"] = _err(exc)

    # ④ 已 finalize 的 candidate 不得改写。先合法 attach（满足 DB 触发器的
    #    「finalized 前 target bundle 必须 approved」），再置 finalized，然后再试 attach。
    try:
        finalized_id = await _spare_candidate("finalized")
        legal = await _attach(candidate_id=finalized_id, commit=True)
        if legal != "COMMITTED":
            raise _HarnessError(f"finalized 场景的前置 attach 未成功: {legal}")
        async with Session() as session:
            await session.execute(
                sa.text(
                    "UPDATE working_paper_representation_upgrade_candidate"
                    " SET state = 'finalized', finalized_representation_id = :r,"
                    " finalized_at = now() WHERE id = :c"
                ),
                {"c": str(finalized_id), "r": snap["seed"]["representation_id"]},
            )
            await session.commit()
        snap["refusals"]["finalized_candidate"] = await _attach(
            candidate_id=finalized_id, label="finalized_candidate"
        )
        snap["refusals"]["finalized_candidate_id"] = str(finalized_id)
    except Exception as exc:  # noqa: BLE001
        snap["harness_errors"]["finalized_candidate_setup"] = _err(exc)

    async with Session() as session:
        snap["counts"]["after_refusals"] = await PP.count_supply_rows(session)
        snap["events_after_refusals"] = int(
            (
                await session.execute(
                    sa.text(
                        "SELECT count(*) FROM working_paper_representation_candidate_event"
                    )
                )
            ).scalar_one()
        )
        snap["candidate_states_after_refusals"] = [
            dict(r)
            for r in (
                await session.execute(
                    sa.text(
                        "SELECT id, state FROM"
                        " working_paper_representation_upgrade_candidate ORDER BY created_at, id"
                    )
                )
            ).mappings().all()
        ]


# ════════════════════════════════════════════════════════════════════════════
# fixture
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


# ════════════════════════════════════════════════════════════════════════════
# 0. 采集自身没崩
# ════════════════════════════════════════════════════════════════════════════


class TestCollectionIntegrity:
    def test_no_phase_crashed_during_collection(self, snap: dict[str, Any]) -> None:
        """**Validates: Requirements 12.1**"""
        assert snap["harness_errors"] == {}, snap["harness_errors"]

    def test_both_migrations_applied_cleanly(self, snap: dict[str, Any]) -> None:
        """V153 必须能在 V151 之上幂等应用（MigrationRunner 启动时会跑它）。

        **Validates: Requirements 12.1**
        """
        assert snap["apply_errors"] == [], snap["apply_errors"]

    def test_entry_denominator_is_source_backed(self, snap: dict[str, Any]) -> None:
        from app.services.workpaper_sync.adapters import registry as RG

        entries = {str(row["entry_id"]) for row in RG.DELIVERED_PER_ENTRY_CONTRACTS}
        assert snap["entry_id"] in entries, (snap["entry_id"], sorted(entries))


# ════════════════════════════════════════════════════════════════════════════
# 1. 四张供给表 0 → 真实行（AC 2.3 / 12.1）
# ════════════════════════════════════════════════════════════════════════════


class TestSupplyTablesGetRealRows:
    def test_all_four_tables_start_empty(self, snap: dict[str, Any]) -> None:
        """分母非空前提：scratch schema 起点必须是四表全 0（否则 0 → N 不成立）。"""
        assert snap["counts"]["initial"] == {t: 0 for t in _supply_tables()}

    def test_first_provision_creates_four_definitions_and_one_bundle(
        self, snap: dict[str, Any]
    ) -> None:
        """**Validates: Requirements 2.3**"""
        after = snap["counts"]["after_first"]
        assert after["working_paper_sync_definition_artifact"] == 4, after
        assert after["working_paper_sync_definition_bundle"] == 1, after
        created = tuple(snap["runs"]["first"]["created_stages"])
        assert set(created) == {
            "authority_model",
            "template",
            "instrumentation",
            "contract",
            "bundle",
        }, created
        assert len(created) == len(set(created)), f"同一段发布了两次: {created}"

    def test_bundle_has_three_non_null_typed_definition_slots(
        self, snap: dict[str, Any]
    ) -> None:
        """`projection_contract` 三 child 必须全是 approved definition（AC 2.3 / 3.3）。

        **Validates: Requirements 2.3**
        """
        row = snap["bundle_row"]
        assert row, "bundle 行读不到 ⇒ 判据无分母"
        assert row["state"] == "approved", row
        assert row["am_kind"] == "authority_model" and row["am_state"] == "approved", row
        assert row["am_type"] == "projection_contract", row
        assert row["authority_model_definition_sha256"] == row["am_sha"], row
        for slot in ("template", "instrumentation", "contract"):
            assert row[f"{slot}_slot_type"] == "definition", (slot, row[f"{slot}_slot_type"])
            ref = str(row[f"{slot}_slot_ref"] or "")
            assert ref.startswith("definition:"), (slot, ref)
            digest = str(row[f"{slot}_slot_digest"] or "")
            assert len(digest) == 64 and digest != "0" * 64, (slot, digest)

    def test_every_slot_child_row_is_approved_and_digest_matches(
        self, snap: dict[str, Any]
    ) -> None:
        """FK 与 digest 自洽：slot digest 必须等于被引用 definition 行的 `sha256`。

        **Validates: Requirements 6.2**
        """
        by_id = {str(child["id"]): child for child in snap["children"]}
        row = snap["bundle_row"]
        for slot in ("template", "instrumentation", "contract"):
            child_id = str(row[f"{slot}_slot_ref"]).split(":", 1)[1]
            child = by_id.get(child_id)
            assert child is not None, f"{slot} slot 指向的 definition 行不存在: {child_id}"
            assert child["kind"] == slot, (slot, child["kind"])
            assert child["state"] == "approved", (slot, child["state"])
            assert child["sha256"] == row[f"{slot}_slot_digest"], slot

    def test_bundle_digest_is_reproducible_from_canonical_bytes(
        self, snap: dict[str, Any]
    ) -> None:
        """库里的 bundle digest 必须能由 canonical bytes **现算**复现（不是随机值）。

        **Validates: Requirements 6.2**
        """
        from app.services.workpaper_sync import definitions as D
        from app.services.workpaper_sync.models import AuthorityModel, BundleSlot

        row = snap["bundle_row"]
        slots = {
            slot: D.definition_slot_spec(
                slot,
                definition_id=uuid.UUID(str(row[f"{slot.value}_slot_ref"]).split(":", 1)[1]),
                definition_sha256=str(row[f"{slot.value}_slot_digest"]),
            )
            for slot in BundleSlot
        }
        recomputed = D.bundle_canonical_digest(
            authority_model=AuthorityModel.projection_contract,
            authority_model_definition_sha256=str(row["authority_model_definition_sha256"]),
            slots=slots,
        )
        assert recomputed == row["canonical_payload_sha256"], (
            recomputed,
            row["canonical_payload_sha256"],
        )

    def test_all_four_tables_hold_real_rows_after_the_full_chain(
        self, snap: dict[str, Any]
    ) -> None:
        """Task 76 的验收标尺：四张表逐表 > 0。

        **Validates: Requirements 12.1**
        """
        final = snap["counts"]["final"]
        assert final == {
            # 4 = provisioner 发布的 authority/template/instrumentation/contract；
            # +4 = 存量播种的 legacy 四段（Task 17 之前的形态）
            "working_paper_sync_definition_artifact": 8,
            # 1 = 本次 approved bundle；+1 = legacy bundle
            "working_paper_sync_definition_bundle": 2,
            "working_paper_representation_upgrade_candidate": 1,
            "working_paper_content_representation": 1,
        }, final
        assert all(v > 0 for v in final.values()), final
        # 越权探针各自用一个新 candidate（mismatch / unapproved / finalized 各一个），
        # 故收尾时 candidate 更多；representation 一行都不许多。
        after = snap["counts"]["after_refusals"]
        assert after["working_paper_representation_upgrade_candidate"] == 4, after
        assert after["working_paper_content_representation"] == 1, after


def _supply_tables() -> tuple[str, ...]:
    from app.services.workpaper_sync.projection_provisioning import SUPPLY_TABLES

    return SUPPLY_TABLES


# ════════════════════════════════════════════════════════════════════════════
# 2. 幂等重跑零新增（AC 3.6 / Property 10）
# ════════════════════════════════════════════════════════════════════════════


class TestIdempotentRerun:
    def test_second_run_creates_nothing_and_reuses_every_stage(
        self, snap: dict[str, Any]
    ) -> None:
        """**Validates: Requirements 3.6**"""
        second = snap["runs"]["second"]
        assert second["created_stages"] == [], second["created_stages"]
        assert set(second["reused_stages"]) == {
            "authority_model",
            "template",
            "instrumentation",
            "contract",
            "bundle",
        }, second["reused_stages"]
        assert second["definition_bundle_id"] == snap["runs"]["first"]["definition_bundle_id"]
        assert (
            second["definition_bundle_sha256"]
            == snap["runs"]["first"]["definition_bundle_sha256"]
        )

    def test_second_run_adds_no_row_to_any_supply_table(self, snap: dict[str, Any]) -> None:
        """逐表等值（不是「总数相等」：总数相等能被「一表 +1 另一表 -1」骗过）。

        **Validates: Requirements 3.6**
        """
        before, after = snap["counts"]["after_first"], snap["counts"]["after_second"]
        assert before == after, (before, after)
        for table in _supply_tables():
            assert before[table] == after[table], table

    def test_no_duplicate_definition_content_exists(self, snap: dict[str, Any]) -> None:
        """同 `(kind, sha256)` 只能有一行 —— 第二份同内容 definition 即违规。

        **Validates: Requirements 6.2**
        """
        seen: dict[tuple[str, str], int] = {}
        for child in snap["children"]:
            key = (str(child["kind"]), str(child["sha256"]))
            seen[key] = seen.get(key, 0) + 1
        dupes = {k: v for k, v in seen.items() if v > 1}
        assert not dupes, f"同内容 definition 出现多份: {dupes}"

    def test_revision_never_moves_across_every_run(self, snap: dict[str, Any]) -> None:
        """纯 definition/bundle/attach 不得推进 `content_revision`。

        **Validates: Requirements 2.1**
        """
        for name, run in snap["runs"].items():
            assert run["content_revision_before"] == run["content_revision_after"] == 0, (
                name,
                run["content_revision_before"],
                run["content_revision_after"],
            )
            assert run["revision_unchanged"] is True, name

    def test_post_attach_run_reuses_the_candidate(self, snap: dict[str, Any]) -> None:
        """attach 之后重跑必须走 `reused_candidate`，不得再 attach 一次。

        **Validates: Requirements 3.6**
        """
        run = snap["runs"]["after_attach"]
        assert run["representation_settlement"] == "reused_candidate", run
        assert run["created_stages"] == [], run["created_stages"]
        assert run["attach"] is None, run["attach"]
        assert snap["events_final"] == 1, (
            f"attach 事件现算 {snap['events_final']} 条 ⇒ 幂等重跑又写了一次审计"
        )


# ════════════════════════════════════════════════════════════════════════════
# 3. candidate 受控 attach（AC 3.4 / 6.18 / Property 67）
# ════════════════════════════════════════════════════════════════════════════


class TestControlledAttach:
    def test_attach_moves_awaiting_contract_to_ready(self, snap: dict[str, Any]) -> None:
        """**Validates: Requirements 6.18**"""
        run = snap["runs"]["attach"]
        assert run["representation_settlement"] == "attached_candidate", run
        attach = run["attach"]
        assert attach is not None, "attach 结果缺失"
        assert attach["from_state"] == "awaiting_contract", attach
        assert attach["to_state"] == "ready", attach
        assert attach["revision_unchanged"] is True and attach["pointer_unchanged"] is True

    def test_candidate_row_now_points_at_the_approved_supply(
        self, snap: dict[str, Any]
    ) -> None:
        """两个 target FK 必须落到本次 approved contract/bundle。

        **Validates: Requirements 6.18**
        """
        cand = snap["candidate"]
        first = snap["runs"]["first"]
        assert cand["state"] == "ready", cand
        assert str(cand["target_contract_definition_id"]) == first["contract_definition_id"]
        assert str(cand["target_definition_bundle_id"]) == first["definition_bundle_id"]
        assert cand["finalized_representation_id"] is None, (
            "attach 顺手把 finalize 也做了 ⇒ 越过 Task 36 的门"
        )

    def test_append_only_audit_event_records_the_bound_identity(
        self, snap: dict[str, Any]
    ) -> None:
        """审计轨必须能复现「谁在哪次调用里绑了哪一份身份」。

        **Validates: Requirements 6.18**
        """
        assert len(snap["events"]) == 1, snap["events"]
        event = snap["events"][0]
        first = snap["runs"]["first"]
        assert event["sequence_no"] == 1, event
        assert event["event_type"] == "contract_bundle_attached", event
        assert (event["from_state"], event["to_state"]) == ("awaiting_contract", "ready"), event
        assert str(event["contract_definition_id"]) == first["contract_definition_id"]
        assert str(event["definition_bundle_id"]) == first["definition_bundle_id"]
        assert event["definition_bundle_sha256"] == first["definition_bundle_sha256"]
        assert str(event["correlation_id"]).strip(), "审计事件缺 correlation_id"
        assert event["actor_id"] is not None, "审计事件缺 actor"

    @pytest.mark.parametrize("op", ["update", "delete"])
    def test_audit_trail_rejects_mutation_at_the_database_layer(
        self, snap: dict[str, Any], op: str
    ) -> None:
        """append-only 由 DB 触发器落实，不是应用层承诺。

        **Validates: Requirements 6.18**
        """
        got = snap["event_mutation"].get(op)
        assert got not in (None, "ALLOWED"), f"{op} 竟然成功 ⇒ 审计轨可被改写: {got}"

    def test_pointer_and_representation_are_untouched_by_attach(
        self, snap: dict[str, Any]
    ) -> None:
        """candidate 进 `ready` 之后仍不是 current，representation 一行没多。

        **Validates: Requirements 6.18**
        """
        assert snap["pointer_after_attach"] == snap["seed"]["representation_id"], (
            snap["pointer_after_attach"],
            snap["seed"]["representation_id"],
        )
        assert (
            snap["counts"]["after_attach"]["working_paper_content_representation"]
            == snap["counts"]["after_seed"]["working_paper_content_representation"]
        )

    def test_existing_rows_were_not_rewritten(self, snap: dict[str, Any]) -> None:
        """`xmin` 逐行相等 ⇒ 既有 content version/representation/pointer 行未被 UPDATE。

        **Validates: Requirements 3.4**
        """
        before = snap["xmin"]["after_seed"]
        after = snap["xmin"]["after_attach"]
        assert set(before) == set(after)
        for table in before:
            assert before[table] == after[table], (
                f"{table} 的 xmin 变了 ⇒ 既有行被重写（AC 3.4 明令不得改写）"
            )

    @pytest.mark.parametrize(
        "case,expected",
        [
            ("already_attached", "CandidateNotAwaitingContractError"),
            ("cross_entry", "CandidateScopeMismatchError"),
            ("contract_bundle_mismatch", "BundleIntegrityError"),
            ("finalized_candidate", "CandidateNotAwaitingContractError"),
        ],
    )
    def test_attach_refuses_every_out_of_scope_request(
        self, snap: dict[str, Any], case: str, expected: str
    ) -> None:
        """四种越权各一条：已 ready / 跨 entry / contract 与 bundle 不符 / 已 finalize。

        **Validates: Requirements 6.18**
        """
        got = snap["refusals"].get(case)
        assert got is not None, f"{case} 场景没采到 ⇒ 判据空跑"
        assert got != "ALLOWED", f"{case} 竟然被允许"
        assert got == expected, (case, got, expected)

    def test_attach_refuses_an_unapproved_contract_for_that_reason(
        self, snap: dict[str, Any]
    ) -> None:
        """未 approved 的 contract 必须因**「不是 approved」**而被拒，不是被别的判据顺手接住。

        同类型不同原因的判据必须可分辨：`BundleIntegrityError` 在 attach 里有四个来源
        （contract 不存在 / kind 不符 / state 非 approved / 与 bundle child 不一致），
        只比异常类型时短路其中一条会被另一条接住 ⇒ 守卫缺陷不可见。

        **Validates: Requirements 3.3**
        """
        assert snap["refusals"].get("unapproved_contract") == "BundleIntegrityError", (
            snap["refusals"].get("unapproved_contract")
        )
        message = snap["refusal_messages"].get("unapproved_contract", "")
        assert "state=" in message and "approved" in message, message
        assert "slot ref" not in message, (
            f"拒绝原因落在 slot ref 比对而不是 contract state ⇒ state 判据可能已被短路: {message}"
        )


# ════════════════════════════════════════════════════════════════════════════
# 4. 伪造供给形态①（真库现读）与 finalize 前置（Property 28 / 67）
# ════════════════════════════════════════════════════════════════════════════


class TestForgedIdentityAndFinalizeGate:
    def test_forged_definition_uuid_is_refused_before_insert(
        self, snap: dict[str, Any]
    ) -> None:
        """① 自造 uuid：真库现读查不到即拒，并指出首个非法 slot。

        **Validates: Requirements 6.10**
        """
        got = snap["refusals"].get("forged_uuid")
        assert got is not None, "forged_uuid 场景没采到"
        assert got["outcome"] == "ForgedDefinitionIdentityError", got
        assert "template" in got["message"], got["message"]
        assert "不存在" in got["message"] or "首个非法 slot" in got["message"], got["message"]

    def test_finalize_was_blocked_before_attach(self, snap: dict[str, Any]) -> None:
        """attach 之前 `assert_candidate_finalizable` 必须因缺 approved contract 而拒。

        **Validates: Requirements 6.18**
        """
        got = snap["finalizable"]["before_attach"]
        assert got == "CandidateNotFinalizableError", got
        assert "contract" in snap["finalizable"]["before_attach_message"], snap["finalizable"]

    def test_finalize_prerequisites_are_satisfied_after_attach(
        self, snap: dict[str, Any]
    ) -> None:
        """attach 之后前置补齐（这正是本任务补的那一格），但 finalize 仍归 Task 36 的门。

        「补齐」的判据不是「不再报错」而是**报错原因变了**：attach 之前停在「缺 approved
        per-entry contract」，attach 之后那一条彻底消失（本例中 compatibility 报告由
        upgrader 写好，故整条前置通过）。

        **Validates: Requirements 6.18**
        """
        assert snap["finalizable"]["after_attach"] == "ALLOWED", snap["finalizable"]
        assert snap["finalizable"]["after_attach_state"] == "ready", snap["finalizable"]
        assert snap["candidate"]["finalized_representation_id"] is None
        assert "contract" in snap["finalizable"]["before_attach_message"], (
            "attach 之前的阻塞原因不是 contract ⇒ 本判据证明不了 attach 补的是哪一格"
        )

    def test_candidate_stays_unconsumable_by_resolver(self, snap: dict[str, Any]) -> None:
        """candidate 永不可被 resolver/room 消费（恒抛）。

        **Validates: Requirements 6.18**
        """
        assert snap["resolver"]["candidate_consumable"] == "CandidateNotResolvableError", (
            snap["resolver"]
        )


# ════════════════════════════════════════════════════════════════════════════
# 5. Property 收束
# ════════════════════════════════════════════════════════════════════════════


class TestProperties:
    def test_property_4_definitions_are_orthogonal_to_content_revision(
        self, snap: dict[str, Any]
    ) -> None:
        """**Validates: Requirements 2.1**"""
        assert snap["counts"]["final"]["working_paper_sync_definition_artifact"] > 0
        for run in snap["runs"].values():
            assert run["content_revision_after"] == 0, run
        assert snap["xmin"]["after_seed"]["working_paper"] == (
            snap["xmin"]["after_attach"]["working_paper"]
        )

    def test_property_5_no_dangling_visible_state(self, snap: dict[str, Any]) -> None:
        """被拒的 attach 全部回滚：candidate 仍只有 attach 那一条事件、状态未漂移。

        **Validates: Requirements 2.4**
        """
        assert snap["events_final"] == 1, snap["events_final"]
        assert snap["candidate"]["state"] == "ready", snap["candidate"]
        assert snap["pointer_after_attach"] == snap["seed"]["representation_id"]

    def test_property_10_idempotent_reuse_holds_on_real_rows(
        self, snap: dict[str, Any]
    ) -> None:
        """**Validates: Requirements 3.6**"""
        assert snap["counts"]["after_first"] == snap["counts"]["after_second"]
        assert snap["runs"]["second"]["created_stages"] == []

    def test_property_28_forged_identity_fails_closed(self, snap: dict[str, Any]) -> None:
        """**Validates: Requirements 6.10**"""
        assert snap["refusals"]["forged_uuid"]["outcome"] == "ForgedDefinitionIdentityError"
        assert snap["counts"]["after_attach"] == snap["counts"]["final"], (
            "被拒的伪造供给留下了行 ⇒ fail-closed 不成立"
        )

    def test_property_67_candidate_first_then_approved_bundle(
        self, snap: dict[str, Any]
    ) -> None:
        """**Validates: Requirements 6.18**"""
        assert snap["runs"]["attach"]["attach"]["to_state"] == "ready"
        assert snap["candidate"]["finalized_representation_id"] is None
        assert snap["pointer_after_attach"] == snap["seed"]["representation_id"]
        assert snap["resolver"]["candidate_consumable"] == "CandidateNotResolvableError"
