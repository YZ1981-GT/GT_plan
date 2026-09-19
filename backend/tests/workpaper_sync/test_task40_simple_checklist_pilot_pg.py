# -*- coding: utf-8 -*-
"""Task 40 真实 PostgreSQL 守卫：pilot 的 definitions/bundle 真发布 + 全场景 run 真落库。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 40
Requirements: 3.7, 4.11, 6.8, 6.11, 12.1, 12.2, 12.10, 12.12, 14.1, 14.2
Properties: **P11 / P25 / P26 / P29 / P49 / P55 / P62 / P69**

═══ 这一半证的是「真的发布了 + 结果真的是推导出来的」 ═══

离线守卫证判据正确，但纯函数**可能是死代码**。本文件在真库上证明：

* `template → instrumentation → contract → bundle` 四段真发布成四行 definition +
  一行 non-null bundle，且 bundle 的三个 typed slot 全是 approved `definition`
  （`projection_contract` 不允许 typed null marker 冒充）；
* Task 39 的 harness 用**这个 bundle** plan 出的 required scenario set 逐条落库，
  每条各自的 operation/application/recovery/trace 实体（`assert_no_reuse_within_run`
  在写入时拒绝复用）；
* P25 / P26 的 oracle 用**本 pilot 契约自己的 stable field key** 真跑一次三方 merge；
* 没有真实 OO/浏览器时 `aggregate_result` 必须是 `failed` 而不是 `passed`（Property 49）；
* 顺序门：`assert_publish_order` 真的拦住「先发 contract 再发 template」。

═══ 隔离与采集 ═══

scratch schema `tmp_task40_pilot_<hex>` + 独立文件根，结束 `DROP SCHEMA CASCADE` + `rmtree`。
全部场景由**一次 `asyncio.run`** 跑完落进快照（module fixture）—— 每个测试各自开 async
会污染共享连接池（Task 21~29 实测：第二个起 `NoneType has no attribute send`）。
采集阶段异常一律**记录不穿透**：穿透会把整个 module 变成 collection ERROR，而 `-rf`
只列 FAILED 不列 ERROR ⇒ 定向变异看不到预期失败项 ⇒ 判 GREEN。
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
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_task40_pilot_"
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


# ═══════════════════════════════════════════════════════════════════════════
# P25 / P26 的三方 projection —— 键全部来自**本 pilot 契约自己**
# ═══════════════════════════════════════════════════════════════════════════

ROW = "GTROW-B601-0007"


def _merge_evidence(*, conflict: bool) -> Any:
    """用本 pilot 契约的真实 stable key 构造三方 projection。

    * `conflict=False` ⇒ P25：current 改 A（`member_name`）、incoming 改 B
      （`variance_note`），两键不同 ⇒ 必须自动合并且 conflict_count=0。
    * `conflict=True`  ⇒ P26：三方在**同一键**（`member_name`）上三个不同值。

    键不是编的：`contract.field_by_stable_key` 会对未登记键抛，所以这里一旦写错
    契约里没有的 key，oracle 之前就先炸（不会静默变成"零冲突"）。
    """
    from app.services.workpaper_sync import pilot_simple_checklist as P
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.pilot_harness import MergeEvidence

    contract = P.load_pilot_contract()
    key_a = f"{P.ROWS_TABLE_KEY}/{ROW}/member_name"
    key_b = f"{P.ROWS_TABLE_KEY}/{ROW}/variance_note"
    for template in (
        f"{P.ROWS_TABLE_KEY}/{{row_uuid}}/member_name",
        f"{P.ROWS_TABLE_KEY}/{{row_uuid}}/variance_note",
    ):
        contract.field_by_stable_key(template)  # 未登记键立刻抛

    spec_a = contract.field_by_stable_key(f"{P.ROWS_TABLE_KEY}/{{row_uuid}}/member_name")
    spec_b = contract.field_by_stable_key(f"{P.ROWS_TABLE_KEY}/{{row_uuid}}/variance_note")

    def projection(values: dict[str, tuple[Any, Any]]) -> Projection:
        return Projection(
            contract_id=contract.contract_id,
            semantic_version=contract.semantic_version,
            document_type=contract.document_type,
            values={
                key: FieldValue(
                    stable_key=key,
                    value=value,
                    value_type=spec.value_type,
                    mode=spec.mode,
                    row_key=ROW,
                )
                for key, (value, spec) in values.items()
            },
            row_keys={P.ROWS_TABLE_KEY: (ROW,)},
        )

    if conflict:
        base = projection({key_a: ("张XX", spec_a)})
        current = projection({key_a: ("李XX", spec_a)})
        incoming = projection({key_a: ("王XX", spec_a)})
        return MergeEvidence(
            base=base,
            current=current,
            incoming=incoming,
            contract=contract,
            conflict_key=key_a,
        )
    base = projection({key_a: ("张XX", spec_a), key_b: ("", spec_b)})
    current = projection({key_a: ("李XX", spec_a), key_b: ("", spec_b)})
    incoming = projection({key_a: ("张XX", spec_a), key_b: ("工时超支 12%", spec_b)})
    return MergeEvidence(
        base=base,
        current=current,
        incoming=incoming,
        contract=contract,
        current_changed_key=key_a,
        incoming_changed_key=key_b,
    )


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - 一次采集覆盖全部阶段
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.workpaper_sync_models import (
        WorkpaperEntryEvidenceScenario,
        WorkpaperSyncDefinitionArtifact,
        WorkpaperSyncDefinitionBundle,
        WorkpaperSyncTestRun,
    )
    from app.services.workpaper_sync import evidence as EV
    from app.services.workpaper_sync import pilot_harness as PH
    from app.services.workpaper_sync import pilot_simple_checklist as P
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.definitions import (
        DefinitionPublisher,
        PublishOrderError,
    )
    from app.services.workpaper_sync.models import (
        ArtifactKind,
        ArtifactState,
        BundleSlot,
        DefinitionKind,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 40 的判据是「pilot definitions/bundle 真的落进 V151 的表」与「harness "
            f"写进真表的逐场景行」，必须真实 PostgreSQL；当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task40_store_"))
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
            await conn.execute(
                sa.text("INSERT INTO projects (id, name) VALUES (:pid, 'task40')"),
                {"pid": project},
            )
            await conn.execute(
                sa.text("INSERT INTO working_paper (id, project_id) VALUES (:wid, :pid)"),
                {"wid": wp, "pid": project},
            )

        artifacts = CanonicalArtifactRepository(base_root=base_root)

        # ── phase: 真发布 pilot 的四个 definition + non-null bundle ──────────
        definitions = None
        try:
            async with Session() as s:
                publisher = DefinitionPublisher(
                    artifacts=artifacts,
                    repository=WorkpaperSyncRepository(s),
                    project_id=project,
                    wp_id=wp,
                    source_commit="task40",
                )
                definitions = await P.publish_pilot_definitions(publisher)
                await s.commit()
            snap["phases"]["publish"] = definitions.as_dict()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("publish", exc)

        # ── phase: 顺序门真的拦住「contract 先于 template」────────────────
        try:
            async with Session() as s:
                publisher = DefinitionPublisher(
                    artifacts=artifacts,
                    repository=WorkpaperSyncRepository(s),
                    project_id=project,
                    wp_id=wp,
                    source_commit="task40-order",
                )
                try:
                    await publisher.publish_definition(
                        kind=DefinitionKind.contract,
                        payload=dict(P.load_pilot_contract().canonical_payload),
                        logical_id=f"{P.PILOT_ADAPTER_ID}.out-of-order",
                        semantic_version="1.0.0",
                    )
                    snap["phases"]["publish_order"] = {"rejected": False}
                except PublishOrderError as exc:
                    snap["phases"]["publish_order"] = {
                        "rejected": True,
                        "message": str(exc)[:200],
                    }
                await s.rollback()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("publish_order", exc)

        # ── phase: bundle 行的 typed slot 形态 ─────────────────────────────
        if definitions is not None:
            try:
                async with Session() as s:
                    row = (
                        await s.execute(
                            sa.select(WorkpaperSyncDefinitionBundle).where(
                                WorkpaperSyncDefinitionBundle.id == definitions.bundle_id
                            )
                        )
                    ).scalar_one()
                    children = list(
                        (
                            await s.execute(
                                sa.select(
                                    WorkpaperSyncDefinitionArtifact.kind,
                                    WorkpaperSyncDefinitionArtifact.state,
                                    WorkpaperSyncDefinitionArtifact.sha256,
                                    WorkpaperSyncDefinitionArtifact.logical_id,
                                )
                            )
                        ).all()
                    )
                    snap["phases"]["bundle_row"] = {
                        "state": str(row.state),
                        "canonical_payload_sha256": str(row.canonical_payload_sha256),
                        "authority_model_definition_sha256": str(
                            row.authority_model_definition_sha256
                        ),
                        "slots": {
                            "template": [
                                str(row.template_slot_type),
                                str(row.template_slot_digest),
                            ],
                            "instrumentation": [
                                str(row.instrumentation_slot_type),
                                str(row.instrumentation_slot_digest),
                            ],
                            "contract": [
                                str(row.contract_slot_type),
                                str(row.contract_slot_digest),
                            ],
                        },
                        "children": [
                            {
                                "kind": str(k),
                                "state": str(st),
                                "sha256": str(sh),
                                "logical_id": str(lid),
                            }
                            for k, st, sh, lid in children
                        ],
                    }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("bundle_row", exc)

        # ── 不可变 artifact：run manifest + 每场景一个 trace bundle ──────────
        run_seed = uuid.uuid4()
        manifest_pub = artifacts.publish_evidence_manifest(
            project_id=project,
            wp_id=wp,
            entry_id=P.PILOT_ENTRY_ID,
            test_run_id=run_seed,
            payload=json.dumps({"run": "task40"}, sort_keys=True).encode(),
        )
        async with Session() as s:
            manifest_row = await WorkpaperSyncRepository(s).register_artifact(
                project_id=project,
                wp_id=wp,
                kind=ArtifactKind.evidence,
                state=ArtifactState.published,
                relative_path=manifest_pub.relative_path,
                sha256=manifest_pub.sha256,
                size_bytes=manifest_pub.size_bytes,
                document_type="json",
                retention_class="evidence_manifest",
            )
            await s.commit()
            manifest_artifact_id = manifest_row.id

        async def _register_trace(label: str) -> tuple[uuid.UUID, str]:
            pub = artifacts.publish_trace_bundle(
                project_id=project,
                wp_id=wp,
                entry_id=P.PILOT_ENTRY_ID,
                test_run_id=run_seed,
                scenario_id=label,
                payload=json.dumps({"trace": label}, sort_keys=True).encode(),
            )
            async with Session() as s:
                row = await WorkpaperSyncRepository(s).register_artifact(
                    project_id=project,
                    wp_id=wp,
                    kind=ArtifactKind.trace_bundle,
                    state=ArtifactState.published,
                    relative_path=pub.relative_path,
                    sha256=pub.sha256,
                    size_bytes=pub.size_bytes,
                    document_type="json.gz",
                    retention_class="trace_bundle",
                )
                await s.commit()
                return row.id, pub.sha256

        env = EV.EvidenceEnvironment(
            source_commit="task40-commit",
            runner_version=PH.HARNESS_VERSION,
            onlyoffice_build=PH.NOT_EXECUTED,
            browser_build=PH.NOT_EXECUTED,
        )

        # ── phase: plan（用**这个** bundle）──────────────────────────────
        plan = None
        if definitions is not None:
            try:
                async with Session() as s:
                    plan = await PH.SyncTestRunHarness(s).plan(
                        entry_id=P.PILOT_ENTRY_ID, bundle_id=definitions.bundle_id
                    )
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
                    "typed_child_digest": plan.bundle.typed_child_digest,
                    "required_digest": plan.required.digest,
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("plan", exc)

        # ── phase: 全场景 run（逐场景各自实体，无复用）────────────────────
        declared = {s.scenario_id: s for s in PH.all_declared_scenarios()}
        if plan is not None:
            try:
                async with Session() as s:
                    harness = PH.SyncTestRunHarness(s)
                    run = await harness.open_run(
                        plan=plan,
                        environment=env,
                        run_manifest_artifact_id=manifest_artifact_id,
                        run_manifest_sha256=manifest_pub.sha256,
                    )
                    await s.commit()
                    run_id = run.id
                    snap["phases"]["open_run"] = {
                        "run_id": str(run.id),
                        "entry_id": str(run.entry_id),
                        "aggregate_result": str(run.aggregate_result),
                        "finished_at": run.finished_at,
                        "editability": str(run.editability),
                        "room_model": str(run.room_model),
                        "definition_bundle_sha256": str(run.definition_bundle_sha256),
                        "authority_model_definition_sha256": str(
                            run.authority_model_definition_sha256
                        ),
                        "required_scenario_set_digest": str(
                            run.required_scenario_set_digest
                        ),
                        "derived_digest_matches": (
                            str(run.required_scenario_set_digest) == plan.required.digest
                        ),
                    }

                results: dict[str, dict[str, Any]] = {}
                all_entity_ids: list[str] = []
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
                    if scenario.expects_application:
                        over["operation_ids"] = (uuid.uuid4(),)
                        over["application_ids"] = (uuid.uuid4(),)
                    if scenario.expects_recovery_case:
                        over["recovery_case_ids"] = (uuid.uuid4(),)
                        over["recovery_precondition_zero_entities"] = True
                    if EV.EvidenceInput if False else False:  # pragma: no cover
                        pass
                    if PH.EvidenceInput.merge_execution in oracle.requires:
                        over["merge_evidence"] = _merge_evidence(
                            conflict=scenario.family is not EV.ScenarioFamily.merge
                        )
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
                            run=live_run,
                            plan=plan,
                            observation=PH.ScenarioObservation(
                                scenario_id=scenario_id, **over
                            ),
                        )
                        await s.commit()
                        entity_ids = [
                            *(str(i) for i in (row.operation_ids or [])),
                            *(str(i) for i in (row.application_ids or [])),
                            *(str(i) for i in (row.recovery_case_ids or [])),
                        ]
                        all_entity_ids.extend(entity_ids)
                        results[scenario_id] = {
                            "operation_ids": [
                                str(i) for i in (row.operation_ids or [])
                            ],
                            "application_ids": [
                                str(i) for i in (row.application_ids or [])
                            ],
                            "recovery_case_ids": [
                                str(i) for i in (row.recovery_case_ids or [])
                            ],
                            "result": str(row.result),
                            "scenario_kind": str(row.scenario_kind),
                            "error_code": row.error_code,
                            "ordinal": int(row.ordinal),
                            "decision_result": decision.result,
                            "entity_ids": entity_ids,
                            "trace_sha256": str(row.trace_bundle_sha256),
                            "notes": list(decision.verdict.notes),
                        }
                snap["phases"]["scenarios"] = results
                snap["phases"]["entity_reuse"] = {
                    "total": len(all_entity_ids),
                    "distinct": len(set(all_entity_ids)),
                }

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
                        run=live_run, plan=plan, environment=env
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

        # ── phase: 一条 operation 复用两个场景必须被拒 ──────────────────────
        if plan is not None:
            try:
                async with Session() as s:
                    harness = PH.SyncTestRunHarness(s)
                    reuse_run = await harness.open_run(
                        plan=plan,
                        environment=env,
                        run_manifest_artifact_id=manifest_artifact_id,
                        run_manifest_sha256=manifest_pub.sha256,
                    )
                    await s.commit()
                    reuse_run_id = reuse_run.id
                shared_op = uuid.uuid4()
                shared_app = uuid.uuid4()
                pair = [
                    sid
                    for sid in plan.scenario_ids
                    if declared[sid].expects_application
                    and not declared[sid].expects_recovery_case
                ][:2]
                outcome: list[Any] = []
                for scenario_id in pair:
                    trace_id, trace_sha = await _register_trace(f"reuse-{scenario_id}")
                    oracle = PH.SCENARIO_ORACLES[scenario_id]
                    scenario = declared[scenario_id]
                    over = {
                        "supplied_inputs": oracle.requires,
                        "server_timeline": {
                            stage: _now() + timedelta(seconds=i)
                            for i, stage in enumerate(PH.OO_TO_HTML_TIMELINE_ORDER)
                        },
                        "observed_close_captures": scenario.expected_close_captures,
                        "operation_ids": (shared_op,),
                        "application_ids": (shared_app,),
                        "trace_bundle_artifact_id": trace_id,
                        "trace_bundle_sha256": trace_sha,
                        "server_timeline_digest": _d(f"reuse-{scenario_id}"),
                        "database_snapshot_digest": _d(f"reuse-db-{scenario_id}"),
                    }
                    if PH.EvidenceInput.merge_execution in oracle.requires:
                        over["merge_evidence"] = _merge_evidence(conflict=False)
                    try:
                        async with Session() as s:
                            harness = PH.SyncTestRunHarness(s)
                            live = (
                                await s.execute(
                                    sa.select(WorkpaperSyncTestRun).where(
                                        WorkpaperSyncTestRun.id == reuse_run_id
                                    )
                                )
                            ).scalar_one()
                            await harness.record_scenario(
                                run=live,
                                plan=plan,
                                observation=PH.ScenarioObservation(
                                    scenario_id=scenario_id, **over
                                ),
                            )
                            await s.commit()
                        outcome.append({"scenario_id": scenario_id, "rejected": False})
                    except PH.HarnessRejected as exc:
                        outcome.append(
                            {
                                "scenario_id": scenario_id,
                                "rejected": True,
                                "kind": exc.kind.value,
                            }
                        )
                snap["phases"]["entity_reuse_refused"] = {
                    "pair": pair,
                    "outcome": outcome,
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("entity_reuse_refused", exc)

        # ── phase: 场景数与 evidence 行数一致（分母 == 分子）────────────────
        if snap["phases"].get("run_id"):
            try:
                async with Session() as s:
                    rows = list(
                        (
                            await s.execute(
                                sa.select(
                                    WorkpaperEntryEvidenceScenario.scenario_id,
                                    WorkpaperEntryEvidenceScenario.result,
                                ).where(
                                    WorkpaperEntryEvidenceScenario.run_id
                                    == uuid.UUID(snap["phases"]["run_id"])
                                )
                            )
                        ).all()
                    )
                snap["phases"]["persisted_rows"] = {
                    str(sid): str(res) for sid, res in rows
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("persisted_rows", exc)

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
# 0. 采集自身
# ═══════════════════════════════════════════════════════════════════════════


def test_v151_applies_cleanly(snap: dict[str, Any]) -> None:
    assert snap["apply_errors"] == [], snap["apply_errors"]


def test_no_phase_crashed_during_collection(snap: dict[str, Any]) -> None:
    """采集阶段零异常 —— 否则下面每条断言都在看一个残缺快照。"""
    assert snap["harness_errors"] == {}, snap["harness_errors"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. definitions / bundle 真的发布了（AC 12.1）
# ═══════════════════════════════════════════════════════════════════════════


def test_four_definitions_and_one_bundle_are_published(snap: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_simple_checklist as P
    from app.services.workpaper_sync.definitions import canonical_digest

    published = snap["phases"]["publish"]
    assert published["entry_id"] == P.PILOT_ENTRY_ID
    assert published["adapter_id"] == P.PILOT_ADAPTER_ID
    assert published["authority_model"] == "projection_contract"
    # digest 与源侧现算值逐条相同（不是"看起来像 hash"）。
    assert published["template_definition_sha256"] == canonical_digest(
        P.template_definition_payload()
    )
    assert published["instrumentation_definition_sha256"] == canonical_digest(
        P.instrumentation_definition_payload()
    )
    assert published["contract_definition_sha256"] == canonical_digest(
        dict(P.load_pilot_contract().canonical_payload)
    )
    assert published["authority_model_definition_sha256"] == canonical_digest(
        P.authority_model_payload()
    )
    for key in (
        "template_definition_id",
        "instrumentation_definition_id",
        "contract_definition_id",
        "authority_model_definition_id",
        "definition_bundle_id",
    ):
        uuid.UUID(published[key])


def test_bundle_is_non_null_and_all_children_are_approved(snap: dict[str, Any]) -> None:
    """`projection_contract` ⇒ 三个 typed slot 必须都是 approved `definition`。"""
    row = snap["phases"]["bundle_row"]
    assert row["state"] == "approved"
    for slot, (slot_type, digest) in row["slots"].items():
        assert slot_type == "definition", (slot, slot_type)
        assert len(digest) == 64 and digest != "0" * 64, (slot, digest)
    kinds = {child["kind"] for child in row["children"]}
    assert {"template", "instrumentation", "contract", "authority_model"} <= kinds, kinds
    assert all(child["state"] == "approved" for child in row["children"]), row["children"]
    logical = {child["logical_id"] for child in row["children"]}
    assert "b60.hour_budget" in logical, logical


def test_bundle_digest_matches_the_canonical_recompute(snap: dict[str, Any]) -> None:
    from app.services.workpaper_sync.definitions import bundle_canonical_digest
    from app.services.workpaper_sync.models import AuthorityModel, BundleSlot

    published = snap["phases"]["publish"]
    row = snap["phases"]["bundle_row"]
    recomputed = bundle_canonical_digest(
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_sha256=published["authority_model_definition_sha256"],
        slots={
            BundleSlot.template: {
                "type": "definition",
                "ref": f"definition:{published['template_definition_id']}",
                "digest": published["template_definition_sha256"],
            },
            BundleSlot.instrumentation: {
                "type": "definition",
                "ref": f"definition:{published['instrumentation_definition_id']}",
                "digest": published["instrumentation_definition_sha256"],
            },
            BundleSlot.contract: {
                "type": "definition",
                "ref": f"definition:{published['contract_definition_id']}",
                "digest": published["contract_definition_sha256"],
            },
        },
    )
    assert row["canonical_payload_sha256"] == recomputed == published[
        "definition_bundle_sha256"
    ]


def test_publish_order_is_enforced(snap: dict[str, Any]) -> None:
    """先发 contract 再发 template 必须被 `assert_publish_order` 拒。"""
    outcome = snap["phases"]["publish_order"]
    assert outcome["rejected"] is True, outcome


# ═══════════════════════════════════════════════════════════════════════════
# 2. required scenario set（AC 12.12 / Property 69）
# ═══════════════════════════════════════════════════════════════════════════


def test_plan_uses_the_pilot_bundle_and_derives_a_non_empty_set(
    snap: dict[str, Any]
) -> None:
    plan = snap["phases"]["plan"]
    assert plan["bundle_digest"] == snap["phases"]["publish"]["definition_bundle_sha256"]
    assert plan["authority_model"] == "projection_contract"
    assert plan["substituted"] is False, "projection_contract 不得触发字段级替换"
    assert plan["close_required"] is True
    assert plan["scenario_count"] > 0
    assert len(plan["required_digest"]) == 64


def test_required_set_covers_every_unconditional_family(snap: dict[str, Any]) -> None:
    ids = set(snap["phases"]["plan"]["scenario_ids"])
    for scenario_id in (
        "html_to_oo",
        "oo_to_html",
        "identity_retention",
        "different_field_merge",
        "same_field_conflict_resolve",
        "frozen_base_status_6_2_dedupe",
        "browser_crash_no_userdata_recovery_case",
        "wrong_prior_confirmation_bundle_fence_contributor_rejected",
        "download_only_zero_three_entities",
        "refresh_required_reopen",
        "rollback",
        "single_participant_close",
        "two_user_close_order_a_then_b",
        "two_user_close_order_b_then_a",
        "b_close_before_a_forcesave_terminal",
        "b_close_after_a_forcesave_terminal",
        "close_leader_revoked_successor_exactly_one",
        "close_leader_revoked_no_successor_recovery_required",
        "close_reconciler_reentrant_exactly_one_capture",
    ):
        assert scenario_id in ids, scenario_id


def test_every_required_scenario_has_a_persisted_row(snap: dict[str, Any]) -> None:
    """分母 == 分子：required set 的每一条都必须有一行 evidence（不许少跑）。"""
    required = set(snap["phases"]["plan"]["scenario_ids"])
    persisted = set(snap["phases"]["persisted_rows"])
    assert persisted == required, {
        "missing": sorted(required - persisted),
        "extra": sorted(persisted - required),
    }


def test_no_entity_is_reused_across_scenarios(snap: dict[str, Any]) -> None:
    """一条 operation 不得填满多个场景（AC 12.10）。"""
    counts = snap["phases"]["entity_reuse"]
    assert counts["total"] > 0, "零实体会让本判据空转"
    assert counts["total"] == counts["distinct"], counts


def test_reused_entity_is_refused_at_write_time(snap: dict[str, Any]) -> None:
    """反向自检：故意复用同一 operation/application ⇒ 第二条必须被拒。"""
    outcome = snap["phases"]["entity_reuse_refused"]
    assert len(outcome["pair"]) == 2, outcome
    assert outcome["outcome"][0]["rejected"] is False, outcome
    assert outcome["outcome"][1]["rejected"] is True, outcome
    assert outcome["outcome"][1]["kind"] == "entity_reused_within_run", outcome


# ═══════════════════════════════════════════════════════════════════════════
# 3. Property 25 / 26：字段级 oracle 在**本 pilot 契约**上真跑
# ═══════════════════════════════════════════════════════════════════════════


def test_property25_different_field_merge_passes_on_the_pilot_contract(
    snap: dict[str, Any]
) -> None:
    """Property 25：current 改 A、incoming 改 B ⇒ 同时含 A/B 且 conflict_count=0。"""
    row = snap["phases"]["scenarios"]["different_field_merge"]
    assert row["result"] == "passed", row
    assert row["error_code"] is None, row
    assert any("conflict_count=0" in note for note in row["notes"]), row["notes"]


def test_property26_same_field_conflict_passes_on_the_pilot_contract(
    snap: dict[str, Any]
) -> None:
    """Property 26：base=A/current=B/incoming=C ⇒ 不得应用任一侧、三值完整。"""
    row = snap["phases"]["scenarios"]["same_field_conflict_resolve"]
    assert row["result"] == "passed", row
    assert row["error_code"] is None, row


def test_field_level_oracles_really_ran_the_merge(snap: dict[str, Any]) -> None:
    """两条字段级场景都带了 merge notes ⇒ oracle 真执行过（不是结构判据兜底）。"""
    for scenario_id in ("different_field_merge", "same_field_conflict_resolve"):
        notes = snap["phases"]["scenarios"][scenario_id]["notes"]
        assert any("conflict_count=" in note for note in notes), (scenario_id, notes)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Property 49 / 55：真实 OO 未跑 ⇒ UNVERIFIABLE，且 run 不得判 passed
# ═══════════════════════════════════════════════════════════════════════════

#: 需要真实 OO / 浏览器的场景在 `NOT_EXECUTED` 哨兵下的唯一合法结果。
_BLACK_BOX_ERROR = "real_onlyoffice_not_executed"


def test_black_box_scenarios_are_unverifiable(snap: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_harness as PH

    scenarios = snap["phases"]["scenarios"]
    debts = set(snap["phases"]["plan"]["upstream_debt"])
    black_box = [
        sid
        for sid in snap["phases"]["plan"]["black_box"]
        if sid not in debts
    ]
    assert black_box, "黑盒场景集合为空会让本判据空转"
    for scenario_id in black_box:
        row = scenarios[scenario_id]
        assert row["result"] == "unverifiable", (scenario_id, row)
        assert row["error_code"] == _BLACK_BOX_ERROR, (scenario_id, row)
    # 与 harness 的黑盒输入声明双向锁死。
    for scenario_id in black_box:
        assert PH.SCENARIO_ORACLES[scenario_id].needs_black_box, scenario_id


def test_upstream_gap_scenarios_are_failed_not_unverifiable(
    snap: dict[str, Any]
) -> None:
    """Task 32 的两条上游缺口是**实现**缺失 ⇒ 必须 failed（接了 OO 也不会自动变绿）。"""
    debts = snap["phases"]["plan"]["upstream_debt"]
    assert debts, "上游缺口集合为空会让本判据空转"
    for scenario_id in debts:
        row = snap["phases"]["scenarios"][scenario_id]
        assert row["result"] == "failed", (scenario_id, row)
        assert row["error_code"] == "upstream_gap", (scenario_id, row)


def test_run_is_not_verified_without_real_onlyoffice(snap: dict[str, Any]) -> None:
    """Property 49 的后半句：probe/pilot 未实际通过时不得计为通过。"""
    finalize = snap["phases"]["finalize"]
    assert finalize["finished_at_set"] is True
    assert finalize["aggregate_result"] == "failed", finalize
    assert finalize["verdict"]["result"] != "verified", finalize["verdict"]
    assert finalize["verdict"]["result"] in {"unverified", "stale"}, finalize["verdict"]
    # 缺陷集合非空 ⇒ 这不是「零场景全过」的空转（Property 69 的分母判据）。
    assert finalize["verdict"]["defects"] or finalize["verdict"]["stale_reasons"], (
        finalize["verdict"]
    )


def test_result_is_never_supplied_by_the_caller(snap: dict[str, Any]) -> None:
    """`ScenarioObservation` 没有 `result` 字段、`finalize_run` 没有 `aggregate_result`。"""
    import inspect

    from app.services.workpaper_sync import pilot_harness as PH

    assert "result" not in {
        f.name for f in PH.ScenarioObservation.__dataclass_fields__.values()
    }
    assert "aggregate_result" not in inspect.signature(
        PH.SyncTestRunHarness.finalize_run
    ).parameters
    assert "verified_at" not in inspect.signature(
        PH.SyncTestRunHarness.finalize_run
    ).parameters


def test_pilot_class_stays_unverifiable_after_this_run(snap: dict[str, Any]) -> None:
    """本 run 结束后 simple_checklist 类仍必须是 UNVERIFIABLE（没有真实 OO）。"""
    from app.services.workpaper_sync import pilot_harness as PH

    assert snap["phases"]["finalize"]["verdict"]["result"] != "verified"
    assessment = PH.assess_pilot_classes()[PH.PilotClass.simple_checklist]
    assert assessment.status is PH.PilotClassStatus.unverifiable


# ═══════════════════════════════════════════════════════════════════════════
# 5. evidence 行形态（AC 14.1）
# ═══════════════════════════════════════════════════════════════════════════


def test_download_only_scenario_has_zero_operation_and_application(
    snap: dict[str, Any]
) -> None:
    row = snap["phases"]["scenarios"]["download_only_zero_three_entities"]
    assert row["scenario_kind"] == "download_only", row
    assert row["operation_ids"] == [], row
    assert row["application_ids"] == [], row
    # 反向自检：该场景**有** recovery case（否则上面两条是空集恒真）。
    assert len(row["recovery_case_ids"]) == 1, row


def test_every_scenario_row_binds_a_published_trace_bundle(
    snap: dict[str, Any]
) -> None:
    for scenario_id, row in snap["phases"]["scenarios"].items():
        assert len(row["trace_sha256"]) == 64, (scenario_id, row["trace_sha256"])


def test_ordinals_are_dense_and_unique(snap: dict[str, Any]) -> None:
    ordinals = sorted(row["ordinal"] for row in snap["phases"]["scenarios"].values())
    assert ordinals == list(range(1, len(ordinals) + 1)), ordinals


def test_run_row_freezes_the_pilot_identity(snap: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_simple_checklist as P

    run = snap["phases"]["open_run"]
    assert run["entry_id"] == P.PILOT_ENTRY_ID
    assert run["editability"] == "editable"
    assert run["room_model"] == "shared"
    assert run["definition_bundle_sha256"] == snap["phases"]["publish"][
        "definition_bundle_sha256"
    ]
    assert run["authority_model_definition_sha256"] == snap["phases"]["publish"][
        "authority_model_definition_sha256"
    ]
    assert run["derived_digest_matches"] is True
    # open_run 恒写 unverified + finished_at NULL（结果只能由重算写）。
    assert run["aggregate_result"] == "unverified"
    assert run["finished_at"] is None
