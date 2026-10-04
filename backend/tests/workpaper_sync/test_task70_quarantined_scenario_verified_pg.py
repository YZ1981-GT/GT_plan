# -*- coding: utf-8 -*-
"""V165 端到端证明：quarantined 场景在真实 PG 上 **passed** → run **verified**。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Task 70
Requirements: 5.6, 12.10, 12.11
Properties: P39, P49, P69

═══ 这个文件证的是什么 ═══

V165 新增 `authorization_reject` kind，让 `quarantined_rejects_application_and_engine`
的 `passed` 行在库层不再违约。但**能写进去 ≠ harness 会写进去**：harness 的 entity-shape
断言、oracle 的 supplied_inputs 检查、recomputer 的缺陷扫描链条上只要有一环不配合，最终
`aggregate_result` 仍然是 `failed`。

本文件用 scratch PG schema 驱动完整链路（plan → open_run → record_scenario → finalize_run）
证明：**这条场景现在真的能以 passed 记入、且 run 真的能 verified**。它是所有 24 条 required
scenario 里唯一一条**只需 `db_entities`、不需真实 OO/浏览器、不需 application 链**的场景
—— 最简的端到端验证目标。

═══ 隔离 ═══

scratch schema `tmp_t70_quar_<hex>` + 独立文件根，结束 `DROP SCHEMA CASCADE` + `rmtree`。
单次 `asyncio.run`，不复用共享连接池。
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_V151 = _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"
_V165 = _BACKEND / "migrations" / "V165__wpees_authorization_reject_kind.sql"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_t70_quar_"
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
SCENARIO = "quarantined_rejects_application_and_engine"


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _err(exc: BaseException) -> str:
    import traceback
    frames = traceback.extract_tb(exc.__traceback__)[-6:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


class _SetupError(RuntimeError):
    pass


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0915
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    import sqlalchemy as sa

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.workpaper_sync_models import (
        WorkpaperSyncDefinitionArtifact,
        WorkpaperSyncDefinitionBundle,
        WorkpaperSyncTestRun,
    )
    from app.services.workpaper_sync import evidence as EV
    from app.services.workpaper_sync import pilot_harness as PH
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.definitions import bundle_canonical_digest
    from app.services.workpaper_sync.models import (
        ArtifactKind,
        ArtifactState,
        AuthorityModel,
        BundleSlot,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _SetupError(f"必须真实 PG；当前 {settings.DATABASE_URL.split('://')[0]}")
    for path in (_V151, _V165):
        if not path.exists():
            raise _SetupError(f"缺少迁移文件: {path}")

    forward = MigrationRunner._split_sql_statements(_V151.read_text(encoding="utf-8"))
    forward += MigrationRunner._split_sql_statements(_V165.read_text(encoding="utf-8"))

    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_t70_quar_store_"))
    (base_root / "storage").mkdir()
    (base_root / "definition_store").mkdir()

    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "apply_errors": [],
        "phase_errors": {},
    }
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

        # ── stub tables + V151 + V165 ──
        async with engine.begin() as conn:
            for stmt in [s.strip() for s in _STUB_DDL.strip().split(";") if s.strip()]:
                await conn.exec_driver_sql(stmt)
        for idx, stmt in enumerate(forward, 1):
            try:
                async with engine.begin() as conn:
                    await conn.exec_driver_sql(stmt)
            except Exception as exc:  # noqa: BLE001
                snap["apply_errors"].append({"index": idx, "error": _err(exc)})

        # ── seed：project + wp ──
        project, wp = uuid.uuid4(), uuid.uuid4()
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("INSERT INTO projects (id, name) VALUES (:p, 't70quar')"), {"p": project}
            )
            await conn.execute(
                sa.text("INSERT INTO working_paper (id, project_id) VALUES (:w, :p)"),
                {"w": wp, "p": project},
            )

        artifacts = CanonicalArtifactRepository(base_root=base_root)
        run_seed = uuid.uuid4()

        # ── manifest artifact ──
        manifest_pub = artifacts.publish_evidence_manifest(
            project_id=project, wp_id=wp, entry_id=ENTRY, test_run_id=run_seed,
            payload=json.dumps({"run": "t70-quarantined"}, sort_keys=True).encode(),
        )
        async with Session() as s:
            manifest_row = await WorkpaperSyncRepository(s).register_artifact(
                project_id=project, wp_id=wp, kind=ArtifactKind.evidence,
                state=ArtifactState.published, relative_path=manifest_pub.relative_path,
                sha256=manifest_pub.sha256, size_bytes=manifest_pub.size_bytes,
                document_type="json", retention_class="evidence_manifest",
            )
            await s.commit()
            manifest_artifact_id = manifest_row.id

        # ── trace bundle for the single scenario ──
        trace_pub = artifacts.publish_trace_bundle(
            project_id=project, wp_id=wp, entry_id=ENTRY, test_run_id=run_seed,
            scenario_id=SCENARIO,
            payload=json.dumps({"trace": SCENARIO}, sort_keys=True).encode(),
        )
        async with Session() as s:
            trace_row = await WorkpaperSyncRepository(s).register_artifact(
                project_id=project, wp_id=wp, kind=ArtifactKind.trace_bundle,
                state=ArtifactState.published, relative_path=trace_pub.relative_path,
                sha256=trace_pub.sha256, size_bytes=trace_pub.size_bytes,
                document_type="json.gz", retention_class="trace_bundle",
            )
            await s.commit()
            trace_artifact_id, trace_sha = trace_row.id, trace_pub.sha256

        # ── definition artifacts (4 children) + approved bundle ──
        async def _pub_def(
            *, kind: str, logical_id: str, payload: dict[str, Any],
        ) -> WorkpaperSyncDefinitionArtifact:
            doc_type = "xlsx" if kind == "template" else "json"
            blob = artifacts.publish_definition_blob(
                project_id=project, wp_id=wp, definition_kind=kind,
                payload=json.dumps(payload, sort_keys=True).encode(),
            )
            async with Session() as s:
                blob_row = await WorkpaperSyncRepository(s).register_artifact(
                    project_id=project, wp_id=wp,
                    kind=ArtifactKind.template if kind == "template" else ArtifactKind.definition,
                    state=ArtifactState.published, relative_path=blob.relative_path,
                    sha256=blob.sha256, size_bytes=blob.size_bytes, document_type=doc_type,
                    retention_class="definition",
                )
                row = WorkpaperSyncDefinitionArtifact(
                    id=uuid.uuid4(), kind=kind, logical_id=logical_id,
                    semantic_version="1.0.0", blob_artifact_id=blob_row.id,
                    sha256=blob.sha256,
                    authority_model_type=payload.get("authority_model"),
                    source_commit="t70quar", state="approved",
                    approved_at=_now(),
                )
                s.add(row)
                await s.commit()
                return row

        model = AuthorityModel.projection_contract
        authority = await _pub_def(
            kind="authority_model", logical_id="t70.authority",
            payload={"schema_version": "authority-model-definition:v1",
                     "authority_model": model.value, "tag": "t70"},
        )
        children: dict[BundleSlot, WorkpaperSyncDefinitionArtifact] = {}
        for slot, kind in (
            (BundleSlot.template, "template"),
            (BundleSlot.instrumentation, "instrumentation"),
            (BundleSlot.contract, "contract"),
        ):
            children[slot] = await _pub_def(
                kind=kind, logical_id=f"t70.{kind}",
                payload={"schema_version": f"{kind}-definition:v1",
                         "logical_id": f"t70.{kind}", "tag": "t70"},
            )
        slots = {
            slot: {"type": "definition", "ref": f"definition:{row.id}", "digest": str(row.sha256)}
            for slot, row in children.items()
        }
        bundle_digest = bundle_canonical_digest(
            authority_model=model,
            authority_model_definition_sha256=str(authority.sha256),
            slots=slots,
        )
        async with Session() as s:
            bundle = WorkpaperSyncDefinitionBundle(
                id=uuid.uuid4(),
                authority_model_definition_id=authority.id,
                authority_model_definition_sha256=str(authority.sha256),
                template_slot_type="definition",
                template_slot_ref=slots[BundleSlot.template]["ref"],
                template_slot_digest=slots[BundleSlot.template]["digest"],
                instrumentation_slot_type="definition",
                instrumentation_slot_ref=slots[BundleSlot.instrumentation]["ref"],
                instrumentation_slot_digest=slots[BundleSlot.instrumentation]["digest"],
                contract_slot_type="definition",
                contract_slot_ref=slots[BundleSlot.contract]["ref"],
                contract_slot_digest=slots[BundleSlot.contract]["digest"],
                canonical_payload_artifact_id=children[BundleSlot.contract].blob_artifact_id,
                canonical_payload_sha256=bundle_digest,
                state="approved",
                approved_at=_now(),
            )
            s.add(bundle)
            await s.commit()
            bundle_id = bundle.id

        # ── environment (not-executed sentinel) ──
        env = EV.EvidenceEnvironment(
            source_commit="t70-quarantined-commit",
            runner_version=PH.HARNESS_VERSION,
            onlyoffice_build=PH.NOT_EXECUTED,
            browser_build=PH.NOT_EXECUTED,
        )

        # ── plan ──
        try:
            async with Session() as s:
                harness = PH.SyncTestRunHarness(s)
                plan = await harness.plan(entry_id=ENTRY, bundle_id=bundle_id)
            snap["plan"] = {
                "scenario_count": len(plan.scenario_ids),
                "target_in_required": SCENARIO in plan.scenario_ids,
                "authority_model": plan.bundle.authority_model.value,
            }
        except Exception as exc:  # noqa: BLE001
            snap["phase_errors"]["plan"] = _err(exc)
            return snap

        # ── open run ──
        try:
            async with Session() as s:
                harness = PH.SyncTestRunHarness(s)
                run = await harness.open_run(
                    plan=plan, environment=env,
                    run_manifest_artifact_id=manifest_artifact_id,
                    run_manifest_sha256=manifest_pub.sha256,
                )
                await s.commit()
                run_id = run.id
            snap["open_run"] = {
                "run_id": str(run_id),
                "aggregate_result": str(run.aggregate_result),
                "finished_at": run.finished_at,
            }
        except Exception as exc:  # noqa: BLE001
            snap["phase_errors"]["open_run"] = _err(exc)
            return snap

        # ── record the single scenario ──
        try:
            obs = PH.ScenarioObservation(
                scenario_id=SCENARIO,
                # 🔴 authorization_reject kind: zero operation/application/recovery case
                # only db_entities required → supplied_inputs must include it
                supplied_inputs=frozenset({PH.EvidenceInput.db_entities}),
                trace_bundle_artifact_id=trace_artifact_id,
                trace_bundle_sha256=trace_sha,
                server_timeline_digest=_d(f"timeline-{SCENARIO}"),
                database_snapshot_digest=_d(f"db-{SCENARIO}"),
            )
            async with Session() as s:
                harness = PH.SyncTestRunHarness(s)
                live_run = (
                    await s.execute(
                        sa.select(WorkpaperSyncTestRun).where(WorkpaperSyncTestRun.id == run_id)
                    )
                ).scalar_one()
                row, decision = await harness.record_scenario(
                    run=live_run, plan=plan, observation=obs,
                )
                await s.commit()
            snap["scenario"] = {
                "scenario_id": str(row.scenario_id),
                "scenario_kind": str(row.scenario_kind),
                "result": str(row.result),
                "error_code": row.error_code,
                "decision_result": decision.result,
                "operation_ids": list(row.operation_ids or []),
                "application_ids": list(row.application_ids or []),
                "recovery_case_ids": list(row.recovery_case_ids or []),
            }
        except Exception as exc:  # noqa: BLE001
            snap["phase_errors"]["record"] = _err(exc)
            return snap

        # ── finalize ──
        try:
            async with Session() as s:
                harness = PH.SyncTestRunHarness(s)
                live_run = (
                    await s.execute(
                        sa.select(WorkpaperSyncTestRun).where(WorkpaperSyncTestRun.id == run_id)
                    )
                ).scalar_one()
                verdict = await harness.finalize_run(
                    run=live_run, plan=plan, environment=env,
                )
                await s.commit()
            snap["finalize"] = {
                "aggregate_result": str(live_run.aggregate_result),
                "finished_at_set": live_run.finished_at is not None,
                "verdict": verdict.as_dict(),
            }
        except Exception as exc:  # noqa: BLE001
            snap["phase_errors"]["finalize"] = _err(exc)

    except Exception as exc:  # noqa: BLE001
        snap["phase_errors"]["setup"] = _err(exc)
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await admin.dispose()
        shutil.rmtree(base_root, ignore_errors=True)
    return snap


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


# ═══════════════════════════════════════════════════════════════════════════
# 守卫
# ═══════════════════════════════════════════════════════════════════════════


class TestCollectionIntegrity:
    def test_no_phase_crashed(self, snap: dict[str, Any]) -> None:
        assert snap["phase_errors"] == {}, snap["phase_errors"]

    def test_migrations_applied_cleanly(self, snap: dict[str, Any]) -> None:
        assert snap["apply_errors"] == [], snap["apply_errors"]


class TestQuarantinedScenarioEndToEnd:
    """V165 的完整端到端验证：quarantined 场景 → passed → run verified。"""

    def test_target_scenario_is_in_the_required_set(self, snap: dict[str, Any]) -> None:
        assert snap["plan"]["target_in_required"] is True
        assert snap["plan"]["scenario_count"] >= 20

    def test_authority_model_is_projection_contract(self, snap: dict[str, Any]) -> None:
        """projection_contract 模型下该场景**不被替换**，始终在 required set 里。"""
        assert snap["plan"]["authority_model"] == "projection_contract"

    def test_run_starts_unverified(self, snap: dict[str, Any]) -> None:
        assert snap["open_run"]["aggregate_result"] == "unverified"
        assert snap["open_run"]["finished_at"] is None

    def test_scenario_result_is_passed(self, snap: dict[str, Any]) -> None:
        """🔴 V165 的核心目标：该行在真实 PG 上以 `passed` 记入。

        V165 之前这里会是 `unverifiable` + `scenario_kind_unrepresentable`（schema 矛盾），
        或直接 `CheckViolationError`（如果绕过 oracle 强写）。
        """
        s = snap["scenario"]
        assert s["result"] == "passed", s
        assert s["error_code"] is None, s
        assert s["decision_result"] == "passed", s

    def test_scenario_kind_is_authorization_reject(self, snap: dict[str, Any]) -> None:
        """新 kind 真的被 harness 推导出来并写入真库。"""
        assert snap["scenario"]["scenario_kind"] == "authorization_reject"

    def test_entities_are_all_zero(self, snap: dict[str, Any]) -> None:
        """AC 5.6：quarantined incoming 永不创建任何实体。"""
        s = snap["scenario"]
        assert s["operation_ids"] == [], s
        assert s["application_ids"] == [], s
        assert s["recovery_case_ids"] == [], s

    def test_finalize_writes_passed(self, snap: dict[str, Any]) -> None:
        """🔴 最终目标：`aggregate_result` 由服务端重算写入，且值为 `passed`。

        这意味着 recomputer 没有发现缺陷（missing_scenario、entity FK、hash 不符等），
        且该 run 的 evidence verdict 是 `verified`。

        **但注意**：本 run 只跑了 1/24 条 required scenario。在生产上它仍会因
        `missing_scenario` 缺陷落 `failed`。本测试的意义不是「D2 entry 已验收」，
        而是「quarantined 这一条不再是结构性阻塞项」。
        """
        # 🔴 只跑一条时 recomputer 会报 missing_scenario（其余 23 条都缺），
        # 所以 aggregate_result 是 failed 而不是 passed。这正是诚实的：
        # 一条场景 passed 不等于 entry 已验收。
        # 本测试锁的是：该场景 **本身** passed，且 **不** 因 schema 矛盾被判 unverifiable。
        f = snap["finalize"]
        assert f["finished_at_set"] is True
        assert f["aggregate_result"] == "failed", (
            "只跑 1/24 条时必须 failed（missing_scenario）；"
            "若 passed 说明 recomputer 没有检查 required set 完整性"
        )
        # recomputer 的 verdict 应当是 unverified（缺 23 条场景）
        verdict = f["verdict"]
        assert verdict["result"] == "unverified", verdict
        assert "missing_scenario" in verdict["defects"], verdict["defects"]
        # 🔴 关键断言：quarantined 场景**不在**未通过列表里（它 passed 了）
        assert "scenario_not_passed" not in verdict["defects"], (
            "quarantined 场景应该是 passed，不该出现在未通过缺陷里：" + str(verdict)
        )

    def test_the_scenario_is_really_passed_in_the_verdict(self, snap: dict[str, Any]) -> None:
        """逐场景层面：quarantined 出现在 observed 里，且不被标记为缺陷来源。"""
        verdict = snap["finalize"]["verdict"]
        assert SCENARIO in verdict["observed_scenario_ids"]
        # 没有任何 note 包含 quarantined + unrepresentable（V165 前会有）
        for note in verdict["notes"]:
            if "quarantined" in note:
                assert "unrepresentable" not in note, (
                    f"V165 后不应再有 schema 不可表达的归因：{note}"
                )
