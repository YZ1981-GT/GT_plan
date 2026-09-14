# -*- coding: utf-8 -*-
"""Task 39 真实 PostgreSQL 守卫：harness 真的把判据接上了、结果真的由重算写入。
spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 39
Requirements: 4.10, 5.8, 12.2, 12.10, 12.11, 12.12, 14.1, 14.14, 14.16
Properties: **P49 / P69 / P70 / P71**

═══ 这一半证的是「接线真实性」 ═══

`test_task39_pilot_harness.py` 证的是判据本身正确（纯函数，18 个 rejection 各真触发一次）。
但纯函数**可能是死代码** —— 本 spec 的第①号假绿形态正是「新加的取数/字段无消费方」。
所以这个文件必须在真库上证明：

* `plan/open_run/record_scenario/finalize_run` 真的调用了那些判据（把非法输入喂给 harness
  本身，而不是喂给纯函数）；
* 写进 `working_paper_sync_test_run` / `working_paper_entry_evidence_scenario` 的行**真的**
  过了 V151 的全部 CHECK（`scenario_kind` 域、三条 entity 约束、
  `ck_wpstr_result_requires_finish`）——离线守卫对此一无所知，而 Task 29 复盘实测过
  「离线全绿、真库 `CheckViolationError`」；
* `aggregate_result` 真的只由服务端重算写入：一个证据齐全、环境对齐的 run 在**没有真实
  OO**时必须落 `failed`，而不是 `passed`（Property 49）。

═══ 隔离与采集 ═══

scratch schema `tmp_task39_harness_<hex>` + 独立文件根，结束 `DROP SCHEMA CASCADE` +
`rmtree`。全部场景由**一次 `asyncio.run`** 跑完落进快照（module fixture）—— 每个测试各自
开 async 会污染共享连接池（Task 21~29 实测：第二个起 `NoneType has no attribute send`）。
采集阶段异常一律**记录不穿透**：穿透会把整个 module 变成 collection ERROR，而 `-rf` 只列
FAILED 不列 ERROR ⇒ 定向变异看不到预期失败项 ⇒ 判 GREEN。
`test_no_phase_crashed_during_collection` 是这个决定的另一半。
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

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_MIGRATION = (
    _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"
)
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_task39_harness_"
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

#: 采集用的真实 manifest entry（编造的 entry_id 会走「未登记入口」分支，测不到本判据）。
ENTRY = "xlsx/gt-d2-accounts-receivable"
OTHER_ENTRY = "xlsx/gt-h1-fixed-assets"
#: 真 manifest 里唯一 `capability=unreachable` 的 entry —— required set 为空。
UNREACHABLE_ENTRY = "xlsx/gt-g6-other-bond-ecl"


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _err(exc: BaseException) -> str:
    import traceback

    frames = traceback.extract_tb(exc.__traceback__)[-8:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成"无数据"）。"""


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - 一次采集覆盖全部场景
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    import sqlalchemy as sa

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.workpaper_sync_models import (
        WorkpaperEntryEvidenceScenario,
        WorkpaperSyncDefinitionArtifact,
        WorkpaperSyncDefinitionBundle,
        WorkpaperSyncTestRun,
    )
    from app.services.workpaper_sync import capacity_profile as CP
    from app.services.workpaper_sync import evidence as EV
    from app.services.workpaper_sync import evidence_freshness as EF
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
        raise _HarnessError(
            "Task 39 的判据是「harness 写进真表的行」与「V151 CHECK 的接受面」，必须真实 "
            f"PostgreSQL；当前 DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}。"
            "此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task39_store_"))
    (base_root / "storage").mkdir()
    (base_root / "definition_store").mkdir()

    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "apply_errors": [],
        "harness_errors": {},
        "phases": {},
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
        for idx, stmt in enumerate(forward, 1):
            try:
                async with engine.begin() as conn:
                    await conn.exec_driver_sql(stmt)
            except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言为空
                snap["apply_errors"].append({"index": idx, "error": _err(exc)})

        project = uuid.uuid4()
        wp = uuid.uuid4()
        async with engine.begin() as conn:
            # asyncpg 用 `$1` 占位符，`exec_driver_sql` 的 `%s` 会 PostgresSyntaxError；
            # 一律走 `sa.text()` + 命名参数（首轮实测踩过）。
            await conn.execute(
                sa.text("INSERT INTO projects (id, name) VALUES (:pid, 'task39')"),
                {"pid": project},
            )
            await conn.execute(
                sa.text("INSERT INTO working_paper (id, project_id) VALUES (:wid, :pid)"),
                {"wid": wp, "pid": project},
            )

        artifacts = CanonicalArtifactRepository(base_root=base_root)

        # ── 不可变 artifact：run manifest + 每场景一个 trace bundle ──────────
        run_seed = uuid.uuid4()
        manifest_pub = artifacts.publish_evidence_manifest(
            project_id=project, wp_id=wp, entry_id=ENTRY, test_run_id=run_seed,
            payload=json.dumps({"run": "task39"}, sort_keys=True).encode(),
        )

        async def _register_trace(label: str) -> tuple[uuid.UUID, str]:
            pub = artifacts.publish_trace_bundle(
                project_id=project, wp_id=wp, entry_id=ENTRY, test_run_id=run_seed,
                scenario_id=label,
                payload=json.dumps({"trace": label}, sort_keys=True).encode(),
            )
            async with Session() as s:
                row = await WorkpaperSyncRepository(s).register_artifact(
                    project_id=project, wp_id=wp, kind=ArtifactKind.trace_bundle,
                    state=ArtifactState.published, relative_path=pub.relative_path,
                    sha256=pub.sha256, size_bytes=pub.size_bytes, document_type="json.gz",
                    retention_class="trace_bundle",
                )
                await s.commit()
                return row.id, pub.sha256

        async with Session() as s:
            manifest_row = await WorkpaperSyncRepository(s).register_artifact(
                project_id=project, wp_id=wp, kind=ArtifactKind.evidence,
                state=ArtifactState.published, relative_path=manifest_pub.relative_path,
                sha256=manifest_pub.sha256, size_bytes=manifest_pub.size_bytes,
                document_type="json", retention_class="evidence_manifest",
            )
            await s.commit()
            manifest_artifact_id = manifest_row.id

        # ── approved authority model definition + approved bundle ───────────
        async def _publish_definition(
            *, kind: str, logical_id: str, payload: dict[str, Any], state: str = "approved"
        ) -> WorkpaperSyncDefinitionArtifact:
            """真发布一个 definition artifact 行。

            🔴 V151 有触发器/外键要求 `definition:<uuid>` slot ref 指向**真实存在**的
            definition 行（首轮实测 `ForeignKeyViolationError: template slot 引用不存在的
            definition`）—— 因此四个 child 一个都不能是编出来的 UUID。
            """
            # V151 的 `ck_wpa_document_type` 只收 xlsx/docx/json.gz/json/zip ——
            # template definition 的落盘扩展名是 `.ooxml`，但 artifact 行的
            # `document_type` 必须落在这个封闭域里（首轮实测 CheckViolationError）。
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
                    source_commit="task39", state=state,
                    approved_at=_now() if state == "approved" else None,
                )
                s.add(row)
                await s.commit()
                return row

        async def _make_bundle(
            *, model: AuthorityModel, state: str = "approved", authority_state: str = "approved",
            tag: str = "",
        ) -> tuple[uuid.UUID, str, str]:
            suffix = tag or f"{model.value}-{state}"
            authority = await _publish_definition(
                kind="authority_model", logical_id=f"task39.authority.{suffix}",
                payload={
                    "schema_version": "authority-model-definition:v1",
                    "authority_model": model.value,
                    "tag": suffix,
                },
                state=authority_state,
            )
            children: dict[BundleSlot, WorkpaperSyncDefinitionArtifact] = {}
            for slot, kind in (
                (BundleSlot.template, "template"),
                (BundleSlot.instrumentation, "instrumentation"),
                (BundleSlot.contract, "contract"),
            ):
                children[slot] = await _publish_definition(
                    kind=kind, logical_id=f"task39.{kind}.{suffix}",
                    payload={
                        "schema_version": f"{kind}-definition:v1",
                        "logical_id": f"task39.{kind}.{suffix}",
                        "tag": suffix,
                    },
                )
            slots = {
                slot: {
                    "type": "definition",
                    "ref": f"definition:{row.id}",
                    "digest": str(row.sha256),
                }
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
                    state=state,
                    approved_at=_now() if state == "approved" else None,
                )
                s.add(bundle)
                await s.commit()
                return bundle.id, bundle_digest, str(authority.sha256)

        approved_bundle_id, approved_bundle_digest, approved_authority_digest = (
            await _make_bundle(model=AuthorityModel.opaque_single_onlyoffice)
        )
        candidate_bundle_id, _, _ = await _make_bundle(
            model=AuthorityModel.opaque_single_onlyoffice, state="candidate", tag="candidate"
        )

        env_not_executed = EV.EvidenceEnvironment(
            source_commit="task39-commit",
            runner_version=PH.HARNESS_VERSION,
            onlyoffice_build=PH.NOT_EXECUTED,
            browser_build=PH.NOT_EXECUTED,
        )

        # ── phase: plan ────────────────────────────────────────────────────
        plan = None
        try:
            async with Session() as s:
                harness = PH.SyncTestRunHarness(s)
                plan = await harness.plan(entry_id=ENTRY, bundle_id=approved_bundle_id)
                snap["phases"]["plan"] = {
                    "scenario_count": len(plan.scenario_ids),
                    "scenario_ids": list(plan.scenario_ids),
                    "authority_model": plan.bundle.authority_model.value,
                    "capability": plan.capability.value,
                    "close_required": plan.required.close_required,
                    "substituted": plan.required.substituted,
                    "black_box": list(plan.black_box_scenario_ids),
                    "upstream_debt": list(plan.upstream_debt_scenario_ids),
                    "bundle_digest": plan.bundle.bundle_sha256,
                }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("plan", exc)

        # ── phase: plan 的 fail-closed 三条（真的走 harness，不是纯函数）─────
        for label, coro in (
            ("plan_unreachable", lambda s: PH.SyncTestRunHarness(s).plan(
                entry_id=UNREACHABLE_ENTRY, bundle_id=approved_bundle_id)),
            ("plan_candidate_bundle", lambda s: PH.SyncTestRunHarness(s).plan(
                entry_id=ENTRY, bundle_id=candidate_bundle_id)),
            ("plan_unknown_entry", lambda s: PH.SyncTestRunHarness(s).plan(
                entry_id="xlsx/does-not-exist", bundle_id=approved_bundle_id)),
        ):
            try:
                async with Session() as s:
                    await coro(s)
                snap["phases"][label] = {"rejected": False}
            except PH.HarnessRejected as exc:
                snap["phases"][label] = {"rejected": True, "kind": exc.kind.value}
            except Exception as exc:  # noqa: BLE001
                _phase_failed(label, exc)

        # ── phase: plan 真的逐场景解析生产符号（行为判据，不是源码判据）───────
        try:
            victim = "rollback"
            original = PH.SCENARIO_ORACLES[victim]
            patched = dict(PH.SCENARIO_ORACLES)
            patched[victim] = PH.ScenarioOracle(
                scenario_id=victim,
                requires=original.requires,
                production_refs=("app.services.workpaper_sync.merge:gone_for_good",),
                why="接线探针",
            )
            saved = PH.SCENARIO_ORACLES
            PH.SCENARIO_ORACLES = patched  # type: ignore[misc]
            try:
                async with Session() as s:
                    await PH.SyncTestRunHarness(s).plan(
                        entry_id=ENTRY, bundle_id=approved_bundle_id
                    )
                snap["phases"]["plan_broken_ref"] = {"rejected": False}
            except PH.HarnessRejected as exc:
                snap["phases"]["plan_broken_ref"] = {"rejected": True, "kind": exc.kind.value}
            finally:
                PH.SCENARIO_ORACLES = saved  # type: ignore[misc]
        except Exception as exc:  # noqa: BLE001
            _phase_failed("plan_broken_ref", exc)

        # ── phase: 完整 run（证据尽可能齐全，但没有真实 OO）────────────────
        declared = {s.scenario_id: s for s in PH.all_declared_scenarios()}
        if plan is not None:
            try:
                async with Session() as s:
                    harness = PH.SyncTestRunHarness(s)
                    run = await harness.open_run(
                        plan=plan, environment=env_not_executed,
                        run_manifest_artifact_id=manifest_artifact_id,
                        run_manifest_sha256=manifest_pub.sha256,
                    )
                    await s.commit()
                    snap["phases"]["open_run"] = {
                        "run_id": str(run.id),
                        "aggregate_result": str(run.aggregate_result),
                        "finished_at": run.finished_at,
                        "editability": str(run.editability),
                        "room_model": str(run.room_model),
                        "runner_version": str(run.runner_version),
                        "required_scenario_set_digest": str(run.required_scenario_set_digest),
                        "derived_digest_matches": (
                            str(run.required_scenario_set_digest) == plan.required.digest
                        ),
                        "onlyoffice_build": str(run.onlyoffice_build),
                    }
                    run_id = run.id

                results: dict[str, dict[str, Any]] = {}
                for scenario_id in plan.scenario_ids:
                    scenario = declared[scenario_id]
                    oracle = PH.SCENARIO_ORACLES[scenario_id]
                    trace_id, trace_sha = await _register_trace(scenario_id)
                    stamps = {
                        stage: _now() + timedelta(seconds=i)
                        for i, stage in enumerate(
                            PH.RECOVERY_TIMELINE_ORDER
                            if scenario.family is EV.ScenarioFamily.recovery
                            else PH.OO_TO_HTML_TIMELINE_ORDER
                        )
                    }
                    over: dict[str, Any] = {
                        "supplied_inputs": oracle.requires,
                        "server_timeline": stamps,
                        "observed_close_captures": scenario.expected_close_captures,
                        "trace_bundle_artifact_id": trace_id,
                        "trace_bundle_sha256": trace_sha,
                        "server_timeline_digest": _d(f"timeline-{scenario_id}"),
                        "database_snapshot_digest": _d(f"db-{scenario_id}"),
                    }
                    # 🔴 只在场景**声明**需要 application 时才给实体：V151 的
                    # `ck_wpees_download_only_zero_entities` 对 download_only 与
                    # recovery_reject 两类都要求 operation/application 为 0（首轮实测
                    # CheckViolationError），AC 5.6 又要求 quarantined 场景永不带
                    # application。用 `expects_application` 单点推导，不各自手填。
                    if scenario.expects_application:
                        over["operation_ids"] = (uuid.uuid4(),)
                        over["application_ids"] = (uuid.uuid4(),)
                    if scenario.expects_recovery_case:
                        over["recovery_case_ids"] = (uuid.uuid4(),)
                        over["recovery_precondition_zero_entities"] = True
                    async with Session() as s:
                        harness = PH.SyncTestRunHarness(s)
                        live_run = (
                            await s.execute(
                                sa.select(WorkpaperSyncTestRun).where(
                                    WorkpaperSyncTestRun.id == run_id
                                )
                            )
                        ).scalar_one()
                        row, decision = await harness.record_scenario(
                            run=live_run, plan=plan,
                            observation=PH.ScenarioObservation(scenario_id=scenario_id, **over),
                        )
                        await s.commit()
                        results[scenario_id] = {
                            "result": str(row.result),
                            "scenario_kind": str(row.scenario_kind),
                            "error_code": row.error_code,
                            "ordinal": int(row.ordinal),
                            "decision_result": decision.result,
                        }
                snap["phases"]["scenarios"] = results

                async with Session() as s:
                    harness = PH.SyncTestRunHarness(s)
                    live_run = (
                        await s.execute(
                            sa.select(WorkpaperSyncTestRun).where(
                                WorkpaperSyncTestRun.id == run_id
                            )
                        )
                    ).scalar_one()
                    verdict = await harness.finalize_run(
                        run=live_run, plan=plan, environment=env_not_executed
                    )
                    await s.commit()
                    snap["phases"]["finalize"] = {
                        "aggregate_result": str(live_run.aggregate_result),
                        "finished_at_set": live_run.finished_at is not None,
                        "verdict": verdict.as_dict(),
                    }
                snap["phases"]["run_id"] = str(run_id)
            except Exception as exc:  # noqa: BLE001
                _phase_failed("full_run", exc)

        # ── phase: 写入侧 fail-closed（真的走 harness）─────────────────────
        run_id_for_rejects = None
        if plan is not None:
            try:
                async with Session() as s:
                    harness = PH.SyncTestRunHarness(s)
                    reject_run = await harness.open_run(
                        plan=plan, environment=env_not_executed,
                        run_manifest_artifact_id=manifest_artifact_id,
                        run_manifest_sha256=manifest_pub.sha256,
                    )
                    await s.commit()
                    run_id_for_rejects = reject_run.id
            except Exception as exc:  # noqa: BLE001
                _phase_failed("open_reject_run", exc)

        async def _try_record(label: str, scenario_id: str, **over: Any) -> None:
            if run_id_for_rejects is None or plan is None:
                return
            try:
                trace_id, trace_sha = await _register_trace(f"{label}-{scenario_id}")
                payload: dict[str, Any] = {
                    "trace_bundle_artifact_id": trace_id,
                    "trace_bundle_sha256": trace_sha,
                    "server_timeline_digest": _d(label),
                    "database_snapshot_digest": _d(label),
                }
                payload.update(over)
                async with Session() as s:
                    harness = PH.SyncTestRunHarness(s)
                    live_run = (
                        await s.execute(
                            sa.select(WorkpaperSyncTestRun).where(
                                WorkpaperSyncTestRun.id == run_id_for_rejects
                            )
                        )
                    ).scalar_one()
                    await harness.record_scenario(
                        run=live_run, plan=plan,
                        observation=PH.ScenarioObservation(scenario_id=scenario_id, **payload),
                    )
                    await s.commit()
                snap["phases"][label] = {"rejected": False}
            except PH.HarnessRejected as exc:
                snap["phases"][label] = {"rejected": True, "kind": exc.kind.value}
            except Exception as exc:  # noqa: BLE001
                _phase_failed(label, exc)

        # download-only 带实体
        await _try_record(
            "reject_download_only_entities", "download_only_zero_three_entities",
            operation_ids=(uuid.uuid4(),), recovery_case_ids=(uuid.uuid4(),),
        )
        # 场景不在 required set（projection_contract 专属场景，opaque 下已被替换掉）
        await _try_record(
            "reject_scenario_not_required", "different_field_merge",
            operation_ids=(uuid.uuid4(),), application_ids=(uuid.uuid4(),),
        )
        # 缺 trace bundle
        if run_id_for_rejects is not None and plan is not None:
            try:
                async with Session() as s:
                    harness = PH.SyncTestRunHarness(s)
                    live_run = (
                        await s.execute(
                            sa.select(WorkpaperSyncTestRun).where(
                                WorkpaperSyncTestRun.id == run_id_for_rejects
                            )
                        )
                    ).scalar_one()
                    await harness.record_scenario(
                        run=live_run, plan=plan,
                        observation=PH.ScenarioObservation(
                            scenario_id="rollback",
                            operation_ids=(uuid.uuid4(),),
                            application_ids=(uuid.uuid4(),),
                            trace_bundle_artifact_id=None,
                            trace_bundle_sha256=_d("nope"),
                            server_timeline_digest=_d("nope"),
                            database_snapshot_digest=_d("nope"),
                        ),
                    )
                snap["phases"]["reject_missing_trace"] = {"rejected": False}
            except PH.HarnessRejected as exc:
                snap["phases"]["reject_missing_trace"] = {
                    "rejected": True, "kind": exc.kind.value
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("reject_missing_trace", exc)

        # ── phase: 跨 entry 复用（Property 70）──────────────────────────────
        if plan is not None:
            try:
                async with Session() as s:
                    harness = PH.SyncTestRunHarness(s)
                    other_plan = await harness.plan(
                        entry_id=OTHER_ENTRY, bundle_id=approved_bundle_id
                    )
                    other_run = await harness.open_run(
                        plan=other_plan, environment=env_not_executed,
                        run_manifest_artifact_id=manifest_artifact_id,
                        run_manifest_sha256=manifest_pub.sha256,
                    )
                    await s.commit()
                    other_run_id = other_run.id
                borrowed = None
                async with Session() as s:
                    rows = list(
                        (
                            await s.execute(
                                sa.select(WorkpaperEntryEvidenceScenario.application_ids)
                                .join(
                                    WorkpaperSyncTestRun,
                                    WorkpaperSyncTestRun.id
                                    == WorkpaperEntryEvidenceScenario.run_id,
                                )
                                .where(WorkpaperSyncTestRun.entry_id == ENTRY)
                            )
                        ).all()
                    )
                    for (app_ids,) in rows:
                        if app_ids:
                            borrowed = uuid.UUID(str(app_ids[0]))
                            break
                if borrowed is None:
                    raise _HarnessError("找不到可借用的 application id —— 上一阶段没落行")
                trace_id, trace_sha = await _register_trace("cross-entry")
                async with Session() as s:
                    harness = PH.SyncTestRunHarness(s)
                    live_run = (
                        await s.execute(
                            sa.select(WorkpaperSyncTestRun).where(
                                WorkpaperSyncTestRun.id == other_run_id
                            )
                        )
                    ).scalar_one()
                    await harness.record_scenario(
                        run=live_run, plan=other_plan,
                        observation=PH.ScenarioObservation(
                            scenario_id="rollback",
                            operation_ids=(uuid.uuid4(),),
                            application_ids=(borrowed,),
                            trace_bundle_artifact_id=trace_id,
                            trace_bundle_sha256=trace_sha,
                            server_timeline_digest=_d("cross"),
                            database_snapshot_digest=_d("cross"),
                            supplied_inputs=PH.SCENARIO_ORACLES["rollback"].requires,
                        ),
                    )
                snap["phases"]["reject_cross_entry"] = {"rejected": False}
            except PH.HarnessRejected as exc:
                snap["phases"]["reject_cross_entry"] = {
                    "rejected": True, "kind": exc.kind.value
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("reject_cross_entry", exc)

        # ── phase: freshness 三条 bundle 轴（真库上改 run 行）──────────────
        if snap["phases"].get("run_id"):
            try:
                run_id = uuid.UUID(snap["phases"]["run_id"])
                async with Session() as s:
                    guard = EF.EvidenceFreshnessGuard(s)
                    identity = await guard.load_bundle_identity(approved_bundle_id)
                    fresh = await guard.assess(
                        entry_id=ENTRY, bundle_id=approved_bundle_id,
                        environment=env_not_executed, run_id=run_id,
                        frozen_child_digest=identity.typed_child_digest,
                    )
                    snap["phases"]["freshness_baseline"] = fresh.as_dict()
                    stale_child = await guard.assess(
                        entry_id=ENTRY, bundle_id=approved_bundle_id,
                        environment=env_not_executed, run_id=run_id,
                        frozen_child_digest=_d("older-children"),
                    )
                    snap["phases"]["freshness_child_changed"] = stale_child.as_dict()
                    drifted_env = EV.EvidenceEnvironment(
                        source_commit="another-commit",
                        runner_version=PH.HARNESS_VERSION,
                        onlyoffice_build=PH.NOT_EXECUTED,
                        browser_build=PH.NOT_EXECUTED,
                    )
                    stale_commit = await guard.assess(
                        entry_id=ENTRY, bundle_id=approved_bundle_id,
                        environment=drifted_env, run_id=run_id,
                        frozen_child_digest=identity.typed_child_digest,
                    )
                    snap["phases"]["freshness_commit_changed"] = stale_commit.as_dict()
                # 🔴 「换了 bundle」不能用 `UPDATE test_run SET ...` 模拟：V151 有
                # `sync test run 的 profile/identity 列不可变（stale 只能新建 run）` 的
                # 约束（本任务首轮实测 CheckViolationError）。真实形态是**发布了新
                # bundle、旧 run 仍冻结着旧 bundle** —— 因此这里新建一个冻结 bundle B 的
                # run，再拿 bundle A 去评估它。
                bundle_b_id, _, _ = await _make_bundle(
                    model=AuthorityModel.opaque_single_onlyoffice, tag="upgraded-b"
                )
                async with Session() as s:
                    harness = PH.SyncTestRunHarness(s)
                    plan_b = await harness.plan(entry_id=ENTRY, bundle_id=bundle_b_id)
                    run_b = await harness.open_run(
                        plan=plan_b, environment=env_not_executed,
                        run_manifest_artifact_id=manifest_artifact_id,
                        run_manifest_sha256=manifest_pub.sha256,
                    )
                    await s.commit()
                    run_b_id = run_b.id
                async with Session() as s:
                    guard = EF.EvidenceFreshnessGuard(s)
                    identity_a = await guard.load_bundle_identity(approved_bundle_id)
                    stale_bundle = await guard.assess(
                        entry_id=ENTRY, bundle_id=approved_bundle_id,
                        environment=env_not_executed, run_id=run_b_id,
                        frozen_child_digest=identity_a.typed_child_digest,
                    )
                    snap["phases"]["freshness_bundle_changed"] = stale_bundle.as_dict()
                    # 反向自检：同一个 run 用它自己冻结的 bundle B 评估 ⇒ 三条轴全静默。
                    identity_b = await guard.load_bundle_identity(bundle_b_id)
                    own = await guard.assess(
                        entry_id=ENTRY, bundle_id=bundle_b_id,
                        environment=env_not_executed, run_id=run_b_id,
                        frozen_child_digest=identity_b.typed_child_digest,
                    )
                    snap["phases"]["freshness_own_bundle"] = own.as_dict()
            except Exception as exc:  # noqa: BLE001
                _phase_failed("freshness", exc)

        # ── phase: pilot 覆盖 + 容量（只登记）─────────────────────────────
        try:
            snap["phases"]["pilot"] = PH.pilot_coverage_summary()
            snap["phases"]["capacity"] = {
                "status": CP.CAPACITY_PROFILE.status.value,
                "owner": CP.CAPACITY_PROFILE.execution_owner,
                "digest": CP.CAPACITY_PROFILE.digest,
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("pilot_capacity", exc)

    except Exception as exc:  # noqa: BLE001 - setup 阶段失败也不穿透
        _phase_failed("setup", exc)
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


class TestCollectionIntegrity:
    """**Validates: Requirements 14.9**"""

    def test_no_phase_crashed_during_collection(self, snap: dict[str, Any]) -> None:
        """采集期异常一律记录不穿透 ⇒ 这一条是它的另一半。

        少了它，采集失败会表现为「后续测试全部 skip/空断言通过」——
        本 spec 点名的 fail-open。
        """
        assert snap["harness_errors"] == {}, snap["harness_errors"]

    def test_v151_applies_cleanly(self, snap: dict[str, Any]) -> None:
        assert snap["apply_errors"] == [], snap["apply_errors"]


class TestPlanIsDerivedFromSourceFacts:
    """**Validates: Requirements 12.10, 12.12**"""

    def test_authority_model_comes_from_the_bundle_row(self, snap: dict[str, Any]) -> None:
        """🔴 authority model 不是入参 —— 它从 approved bundle 的 definition child 读出。

        调用方给不了 authority model，于是"直接传 opaque 少跑两个字段级场景"这条路被堵死。
        """
        plan = snap["phases"]["plan"]
        assert plan["authority_model"] == "opaque_single_onlyoffice", plan
        assert plan["substituted"] is True, plan

    def test_required_set_is_derived_and_non_trivial(self, snap: dict[str, Any]) -> None:
        """真 manifest 上的实测分母：该 entry 是 editable+shared ⇒ 含 8 条 close 场景。"""
        plan = snap["phases"]["plan"]
        assert plan["close_required"] is True, plan
        close_ids = {"single_participant_close", "two_user_close_order_a_then_b",
                     "two_user_close_order_b_then_a", "b_close_before_a_forcesave_terminal",
                     "b_close_after_a_forcesave_terminal",
                     "close_leader_revoked_successor_exactly_one",
                     "close_leader_revoked_no_successor_recovery_required",
                     "close_reconciler_reentrant_exactly_one_capture"}
        assert close_ids <= set(plan["scenario_ids"]), sorted(
            close_ids - set(plan["scenario_ids"])
        )
        assert plan["scenario_count"] == len(set(plan["scenario_ids"])), "分母里有重复场景"
        assert plan["scenario_count"] >= 20, plan["scenario_count"]

    def test_unreachable_entry_is_refused_by_the_harness_itself(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 零场景不算通过 —— 而且是 harness 拒的，不是纯函数拒的。"""
        phase = snap["phases"]["plan_unreachable"]
        assert phase["rejected"] is True, phase
        assert phase["kind"] == "empty_required_set", phase

    def test_candidate_bundle_is_refused_by_the_harness_itself(
        self, snap: dict[str, Any]
    ) -> None:
        phase = snap["phases"]["plan_candidate_bundle"]
        assert phase["rejected"] is True and phase["kind"] == "bundle_not_approved", phase

    def test_unregistered_entry_is_refused_by_the_harness_itself(
        self, snap: dict[str, Any]
    ) -> None:
        phase = snap["phases"]["plan_unknown_entry"]
        assert phase["rejected"] is True and phase["kind"] == "entry_not_in_manifest", phase

    def test_plan_really_resolves_every_scenarios_production_symbol(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 接线判据落在**行为**上：把某个必需场景的生产符号换成不存在的名字，
        `plan()` 必须拒。

        用源码里"有没有那行调用"做判据会被改个变量名绕过；这里换的是 oracle 表本身，
        因此只有真的执行了解析才会打红。
        """
        phase = snap["phases"]["plan_broken_ref"]
        assert phase["rejected"] is True, phase
        assert phase["kind"] == "oracle_unresolvable", phase


class TestOpenRunFreezesDerivedIdentity:
    """**Validates: Requirements 12.10, 14.16**"""

    def test_run_starts_unverified_with_no_finish_time(self, snap: dict[str, Any]) -> None:
        run = snap["phases"]["open_run"]
        assert run["aggregate_result"] == "unverified", run
        assert run["finished_at"] is None, run

    def test_identity_columns_are_derived_not_supplied(self, snap: dict[str, Any]) -> None:
        run = snap["phases"]["open_run"]
        assert run["derived_digest_matches"] is True, run
        assert run["editability"] == "editable" and run["room_model"] == "shared", run
        assert run["runner_version"].startswith("task39-harness/"), run
        assert run["onlyoffice_build"] == "NOT-EXECUTED", run


class TestScenarioRowsAreRealAndSchemaValid:
    """**Validates: Requirements 12.11, 14.1**"""

    def test_every_required_scenario_got_its_own_row(self, snap: dict[str, Any]) -> None:
        plan = snap["phases"]["plan"]
        rows = snap["phases"]["scenarios"]
        assert set(rows) == set(plan["scenario_ids"]), (
            f"缺行 {sorted(set(plan['scenario_ids']) - set(rows))}"
        )
        ordinals = sorted(info["ordinal"] for info in rows.values())
        assert ordinals == list(range(1, len(rows) + 1)), ordinals

    def test_scenario_kind_domain_is_accepted_by_v151(self, snap: dict[str, Any]) -> None:
        """真库接受面 —— 离线守卫对 CHECK 一无所知（Task 29 复盘实测过这个坑）。"""
        kinds = {info["scenario_kind"] for info in snap["phases"]["scenarios"].values()}
        assert kinds <= {
            "standard", "download_only", "recovery_reject", "recovery_claim", "close_capture"
        }, kinds

    def test_result_is_derived_by_the_oracle_not_supplied(self, snap: dict[str, Any]) -> None:
        """每行的 `result` 与 harness 返回的 decision 一致，且非 passed 必带 error_code。"""
        for scenario_id, info in sorted(snap["phases"]["scenarios"].items()):
            assert info["result"] == info["decision_result"], (scenario_id, info)
            if info["result"] != "passed":
                assert info["error_code"], (scenario_id, info)

    def test_no_black_box_scenario_was_recorded_as_passed(self, snap: dict[str, Any]) -> None:
        """🔴 Property 49：没有真实 OO/浏览器时，黑盒场景一个都不能 passed。"""
        offenders = sorted(
            scenario_id
            for scenario_id in snap["phases"]["plan"]["black_box"]
            if snap["phases"]["scenarios"][scenario_id]["result"] == "passed"
        )
        assert offenders == [], offenders

    def test_black_box_scenarios_carry_the_not_executed_error_code(
        self, snap: dict[str, Any]
    ) -> None:
        """而且理由必须指名"未执行真实 OO"，不是笼统的失败。"""
        codes = {
            snap["phases"]["scenarios"][sid]["error_code"]
            for sid in snap["phases"]["plan"]["black_box"]
            if sid not in {"quarantined_rejects_application_and_engine"}
        }
        assert codes and codes <= {
            "real_onlyoffice_not_executed", "upstream_gap", "scenario_kind_unrepresentable"
        }, codes
        assert "real_onlyoffice_not_executed" in codes

    def test_upstream_gap_scenarios_are_failed_with_task32_attribution(
        self, snap: dict[str, Any]
    ) -> None:
        """两条上游缺口场景落 `failed` 并指名 Task 32 —— 不是静默跳过。"""
        for scenario_id in snap["phases"]["plan"]["upstream_debt"]:
            info = snap["phases"]["scenarios"][scenario_id]
            assert info["result"] == "failed", (scenario_id, info)
            assert info["error_code"] == "upstream_gap", (scenario_id, info)


class TestWriteSideFailClosedIsWired:
    """**Validates: Requirements 12.10, 12.11, 12.12**（判据真的接在 harness 上）"""

    def test_download_only_with_entities_is_refused(self, snap: dict[str, Any]) -> None:
        phase = snap["phases"]["reject_download_only_entities"]
        assert phase["rejected"] is True, phase
        assert phase["kind"] == "download_only_has_entities", phase

    def test_a_scenario_outside_the_required_set_is_refused(
        self, snap: dict[str, Any]
    ) -> None:
        """`different_field_merge` 在 opaque authority model 下已被替换掉 ⇒ 不得追加。"""
        phase = snap["phases"]["reject_scenario_not_required"]
        assert phase["rejected"] is True, phase
        assert phase["kind"] == "scenario_not_required", phase

    def test_a_scenario_without_a_trace_bundle_is_refused(self, snap: dict[str, Any]) -> None:
        """只有截图/自由文本不构成逐 scenario 证据。"""
        phase = snap["phases"]["reject_missing_trace"]
        assert phase["rejected"] is True, phase
        assert phase["kind"] == "trace_bundle_not_published", phase

    def test_borrowing_another_entrys_application_is_refused(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 Property 70：跨 entry 复制证据，在**写入时**就被拒。"""
        phase = snap["phases"]["reject_cross_entry"]
        assert phase["rejected"] is True, phase
        assert phase["kind"] == "entity_reused_across_entry", phase


class TestFinalizeWritesOnlyRecomputedResult:
    """**Validates: Requirements 12.10, 14.14**"""

    def test_finalize_sets_finished_at_and_a_recomputed_result(
        self, snap: dict[str, Any]
    ) -> None:
        phase = snap["phases"]["finalize"]
        assert phase["finished_at_set"] is True, phase
        assert phase["aggregate_result"] in {"passed", "failed"}, phase

    def test_a_run_without_real_onlyoffice_cannot_be_passed(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 证据齐全、环境对齐、每条场景都有自己的实体和 trace —— 仍然 `failed`。

        这是本任务最核心的一条：harness 建好了，但它**拒绝**宣称真实 OO pilot 已通过。
        """
        phase = snap["phases"]["finalize"]
        assert phase["aggregate_result"] == "failed", phase
        verdict = phase["verdict"]
        assert verdict["result"] == "unverified", verdict
        assert "scenario_not_passed" in verdict["defects"], verdict

    def test_the_recomputer_saw_the_full_required_set(self, snap: dict[str, Any]) -> None:
        """重算的分母是推导出来的 required set，且没有 missing/extra。"""
        verdict = snap["phases"]["finalize"]["verdict"]
        assert set(verdict["required_scenario_ids"]) == set(verdict["observed_scenario_ids"])
        assert "missing_scenario" not in verdict["defects"], verdict["defects"]
        assert "extra_scenario" not in verdict["defects"], verdict["defects"]


class TestFreshnessAxesOnRealRows:
    """**Validates: Requirements 14.16**（Property 71）"""

    def test_baseline_has_no_bundle_stale_reason(self, snap: dict[str, Any]) -> None:
        """反向自检：bundle/authority/child 都没变时，三条轴一条都不报。"""
        baseline = snap["phases"]["freshness_baseline"]
        assert baseline["bundle_stale_reasons"] == [], baseline

    def test_typed_child_change_is_reported_on_its_own_axis(
        self, snap: dict[str, Any]
    ) -> None:
        phase = snap["phases"]["freshness_child_changed"]
        assert phase["bundle_stale_reasons"] == ["definition_bundle_child_changed"], phase
        assert phase["result"] in {"stale", "unverified"}, phase

    def test_source_commit_change_still_flows_from_the_recomputer(
        self, snap: dict[str, Any]
    ) -> None:
        """Task 29 的十条轴与本任务的三条轴合成一个结论，互不遮蔽。"""
        phase = snap["phases"]["freshness_commit_changed"]
        assert "source_commit_changed" in phase["recomputed_stale_reasons"], phase
        assert "source_commit_changed" in phase["stale_reasons"], phase

    def test_bundle_and_authority_change_are_two_axes(self, snap: dict[str, Any]) -> None:
        """🔴 这两条码在 Task 29 交付时就在枚举里，却从未被 emit —— 现在真的会报。

        构造的是真实形态：发布了 bundle B、run 冻结着 B、而现行 approved bundle 是 A。
        （不能用 `UPDATE test_run` 模拟 —— V151 明令 profile/identity 列不可变。）
        """
        phase = snap["phases"]["freshness_bundle_changed"]
        assert set(phase["bundle_stale_reasons"]) == {
            "definition_bundle_changed", "authority_model_changed"
        }, phase

    def test_a_run_assessed_against_its_own_bundle_is_not_stale(
        self, snap: dict[str, Any]
    ) -> None:
        """反向自检：同一 run 用它自己冻结的 bundle 评估 ⇒ 三条轴全静默。

        少了这一条，把 `bundle_stale_reasons` 写成"恒报两条"也能让上面全绿。
        """
        phase = snap["phases"]["freshness_own_bundle"]
        assert phase["bundle_stale_reasons"] == [], phase


class TestPilotAndCapacityStayUnclaimed:
    """**Validates: Requirements 12.2, 14.10**（Property 49 / 72）"""

    def test_no_pilot_class_is_verified(self, snap: dict[str, Any]) -> None:
        pilot = snap["phases"]["pilot"]
        assert pilot["all_verified"] is False, pilot
        assert pilot["verified_classes"] == [], pilot

    def test_capacity_is_registered_pending_task_71(self, snap: dict[str, Any]) -> None:
        capacity = snap["phases"]["capacity"]
        assert capacity["status"] == "registered_pending_execution", capacity
        assert capacity["owner"] == "Task 71", capacity
