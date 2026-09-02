"""Task 43 真实 PostgreSQL 守卫：definitions/bundle 真发布 + 全场景 run + 真实库观测。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 43
Requirements: 6.3, 6.4, 6.10, 6.16, 12.1, 12.2, 12.10, 14.1
Properties: **P22 / P28 / P49 / P66 / P69**

═══ 这一半证的是「真跑了 + 结果真的是推导出来的 + 真实库观测被冻结」 ═══

离线守卫证判据正确，但纯函数**可能是死代码**。本文件在真库上证明：

* `template → instrumentation → contract → bundle` 四段真发布成四行 definition + 一行
  non-null bundle，且**发布顺序**被 `DefinitionPublisher` 强制（contract 先于 template 必拒）；
* Task 39 的 harness 用**这个 bundle** plan 出 **24** 条 required scenario 并逐条落库，
  逐场景各自实体、无复用；一条 operation 复用两个场景必须被拒；
* 没有真实 OO/浏览器时 `aggregate_result` 必须是 `failed` 而不是 `passed`（Property 49）；
* 本 entry 的 `required_scenario_set_digest` 与 Task 40/41/42 的**都不同**；
* 🔴 **真实库观测被冻结，而且 Property 22 的 oracle 跑在真实载荷上**：
  `checklist_responses` 里 `item_id='G7-main-disclosure-soe-v2'` 实测 **3** 条，
  三条都带 `minority-financials` 的 **10** 个 metric 行、`entitySlots['minority-fs-company']`
  的 **5** 个实体名。其中 **2 条**用改造后的 `{slot}_{seq}_{subKey}` 列键、**1 条**（字节
  最大的那条）仍是改造前的 `c{n}Current` / `c{n}Prior` ⇒ 那一条的披露数据在当前 UI 上整块
  读不出来。这是本任务发现的第 6 条欠账
  （`UPSTREAM_DEBT_LEGACY_COLUMN_KEYS_STRANDED`），由本文件冻结并要求
  `build_store_projection` 对它 **fail closed** 而不是静默丢整行。

═══ 隔离与采集 ═══

scratch schema `tmp_task43_pilot_<hex>` + 独立文件根，结束 `DROP SCHEMA CASCADE` + `rmtree`。
真实数据只经 **admin engine 只读** `public.checklist_responses`，一个字节都不写
（`test_real_workpaper_data_is_untouched` 整轮跑完后重新观测、逐字段比对）。
全部阶段由**一次 `asyncio.run`** 跑完落进快照（module fixture）—— 每个测试各自开 async
会污染共享连接池（实测：第二个起 `NoneType has no attribute send`）。
采集阶段异常一律**记录不穿透**：穿透会把整个 module 变成 collection ERROR，而 `-rf`
只列 FAILED 不列 ERROR ⇒ 定向变异看不到预期失败项 ⇒ 判 GREEN。
`test_no_phase_crashed_during_collection` 是这个决定的另一半。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
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

_SCHEMA_PREFIX = "tmp_task43_pilot_"

#: 与离线守卫互锁的冻结观测（两侧任一漂移都打红）。
EXPECTED_SOE_STORE_ROWS = 3
EXPECTED_MODERN_KEY_ROWS = 2
EXPECTED_LEGACY_KEY_ROWS = 1
EXPECTED_METRIC_ROWS = 10
EXPECTED_ENTITY_SLOTS = 5
EXPECTED_DYNAMIC_COLUMNS = 10
EXPECTED_REQUIRED_SCENARIOS = 24

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

_MERGE_METRIC = "minority-fs-1"


def _merge_evidence(*, conflict: bool) -> Any:
    """用本 pilot 契约的真实 stable key 构造三方 projection。

    * `conflict=False` ⇒ P25：current 改**第 1 家公司的期末列**、incoming 改**第 5 家公司的
      期初列**，两键不同 ⇒ 自动合并且 conflict_count=0。这同时是 **Property 22** 的行为级
      oracle：两个键的 label 完全相同（`期末数/本期发生额` / `期初数/上期发生额` 各重复
      5 次），能分开合并只能是因为 identity 不是 label。
    * `conflict=True`  ⇒ P26：三方在**同一键**上三个不同值。

    键不是编的：`contract.field_by_stable_key` 对未登记键抛，写错立刻炸。
    """
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.pilot_harness import MergeEvidence

    contract = P.load_pilot_contract()
    key_a = P.stable_key_for_metric_cell(_MERGE_METRIC, f"{P.MATRIX_TABLE_KEY}_1")
    key_b = P.stable_key_for_metric_cell(_MERGE_METRIC, f"{P.MATRIX_TABLE_KEY}_10")
    spec_a = contract.field_by_stable_key(key_a)
    spec_b = contract.field_by_stable_key(key_b)

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
                    row_key=None,
                )
                for key, (value, spec) in values.items()
            },
            row_keys={},
        )

    if conflict:
        return MergeEvidence(
            base=projection({key_a: (1000.0, spec_a)}),
            current=projection({key_a: (1200.0, spec_a)}),
            incoming=projection({key_a: (1300.0, spec_a)}),
            contract=contract,
            conflict_key=key_a,
        )
    return MergeEvidence(
        base=projection({key_a: (1000.0, spec_a), key_b: (2000.0, spec_b)}),
        current=projection({key_a: (1200.0, spec_a), key_b: (2000.0, spec_b)}),
        incoming=projection({key_a: (1000.0, spec_a), key_b: (2500.0, spec_b)}),
        contract=contract,
        current_changed_key=key_a,
        incoming_changed_key=key_b,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 真实库观测（只读 public.checklist_responses）
# ═══════════════════════════════════════════════════════════════════════════


async def _observe_real_store(engine: Any) -> dict[str, Any]:
    """观测本 pilot 的 store 载体在真实库里的形态。**只读**。"""
    import sqlalchemy as sa

    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                sa.text(
                    "SELECT wp_id, remark, coalesce(length(remark), 0) AS n "
                    "FROM public.checklist_responses WHERE item_id = :item "
                    "ORDER BY n DESC, wp_id"
                ),
                {"item": P.STORE_ITEM_ID},
            )
        ).all()

    observed: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {"wp_id": str(row.wp_id), "bytes": int(row.n)}
        try:
            state = json.loads(row.remark or "null")
        except ValueError as exc:
            item["parse_error"] = str(exc)
            observed.append(item)
            continue
        if not isinstance(state, dict):
            item["type"] = type(state).__name__
            observed.append(item)
            continue
        item["version"] = state.get("version")
        tables = state.get("tables") or {}
        item["has_matrix_table"] = P.RENDER_MATRIX_TABLE_ID in tables
        item["has_record_table"] = P.RENDER_RECORD_TABLE_ID in tables
        matrix = tables.get(P.RENDER_MATRIX_TABLE_ID)
        if isinstance(matrix, list):
            item["metric_ids"] = [
                str(r.get("id")) for r in matrix if isinstance(r, dict)
            ]
            item["metric_labels"] = [
                str(r.get("label")) for r in matrix if isinstance(r, dict)
            ]
            column_keys: set[str] = set()
            for r in matrix:
                if isinstance(r, dict) and isinstance(r.get("values"), dict):
                    column_keys |= {str(k) for k in r["values"]}
            item["column_keys"] = sorted(column_keys)
            item["legacy_column_keys"] = sorted(
                key for key in column_keys if re.match(P.LEGACY_COLUMN_KEY_PATTERN, key)
            )
            item["modern_column_keys"] = sorted(
                key for key in column_keys if key.startswith(f"{P.RENDER_SLOT}_")
            )
        slots = state.get("entitySlots") or {}
        item["entity_names"] = list(slots.get(P.RENDER_SLOT) or ())
        # 真实载荷上跑一次 store 拆分（本 pilot 的 Property 22 行为级 oracle）。
        try:
            projection = P.build_store_projection(state, contract=P.load_pilot_contract())
            item["projection_field_count"] = len(projection.values)
            item["projection_error"] = None
        except Exception as exc:  # noqa: BLE001 - 分型本身就是被测项
            item["projection_field_count"] = None
            item["projection_error"] = f"{type(exc).__name__}: {exc}"
        observed.append(item)

    return {
        "item_id": P.STORE_ITEM_ID,
        "row_count": len(rows),
        "rows": observed,
        "digest": _d(
            json.dumps(
                sorted((str(row.wp_id), int(row.n)) for row in rows), sort_keys=True
            )
        ),
    }


def _synthetic_property_phases() -> dict[str, Any]:
    """在合成载荷上跑 Property 22 的键级 oracle（真实载荷侧在 `_observe_real_store`）。"""
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P
    from app.services.workpaper_sync.excel_entry_gate import (
        assert_dynamic_columns_label_independent,
    )
    from app.services.workpaper_sync.merge import merge_projections

    renamed = ("华东实业", "华东实业", "华东实业", "北方能源", "北方能源")
    before = P.dynamic_column_keys_for_entities(P.RENDER_SLOT_DEFAULT_NAMES)
    after = P.dynamic_column_keys_for_entities(renamed)
    observed = P.observed_dynamic_columns_for(renamed)[P.MATRIX_TABLE_KEY]
    derived = assert_dynamic_columns_label_independent(
        slot=P.MATRIX_TABLE_KEY, observed=observed, where="task43-pg"
    )
    merge = _merge_evidence(conflict=False)
    outcome = merge_projections(
        base=merge.base, current=merge.current, incoming=merge.incoming,
        contract=merge.contract,
    )
    conflicting = _merge_evidence(conflict=True)
    conflicted = merge_projections(
        base=conflicting.base,
        current=conflicting.current,
        incoming=conflicting.incoming,
        contract=conflicting.contract,
    )
    labels: dict[str, int] = {}
    for _label, sub_label in P.RENDER_SUB_COLUMNS:
        labels[sub_label] = len(P.TEMPLATE_SLOT_GROUP_MERGES)
    return {
        "keys_unchanged_after_rename": list(after) == list(before),
        "derived_equals_before": list(derived) == list(before),
        "duplicate_label_count": len(observed) - len({label for label, _ in observed}),
        "distinct_keys": len({key for _label, key in observed}),
        "merge_conflict_count": outcome.conflict_count,
        "merge_has_both_sides": sorted(
            key
            for key in (merge.current_changed_key, merge.incoming_changed_key)
            if outcome.merged.get(key) is not None
        ),
        "same_field_conflict_count": conflicted.conflict_count,
        "same_field_conflict_keys": [
            record.locator.stable_field_key for record in conflicted.conflicts.records
        ],
        "duplicate_leaf_labels": labels,
        "binding_columns": list(
            P.dynamic_column_binding_for(P.RENDER_SLOT_DEFAULT_NAMES).values()
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 一次采集：真库发布 → plan → 全场景 record → finalize
# ═══════════════════════════════════════════════════════════════════════════


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
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P
    from app.services.workpaper_sync import pilot_harness as PH
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.definitions import (
        DefinitionPublisher,
        PublishOrderError,
    )
    from app.services.workpaper_sync.models import (
        ArtifactKind,
        ArtifactState,
        DefinitionKind,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 43 的判据是「pilot definitions/bundle 真的落进 V151 的表」与「真实库里 "
            f"{P.STORE_ITEM_ID} 的观测形态」，必须真实 PostgreSQL；当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task43_store_"))
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
        try:
            snap["phases"]["real_store"] = await _observe_real_store(admin)
        except Exception as exc:  # noqa: BLE001
            _phase_failed("real_store", exc)
        try:
            snap["phases"]["properties"] = _synthetic_property_phases()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("properties", exc)

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
                sa.text("INSERT INTO projects (id, name) VALUES (:pid, 'task43')"),
                {"pid": project},
            )
            await conn.execute(
                sa.text("INSERT INTO working_paper (id, project_id) VALUES (:wid, :pid)"),
                {"wid": wp, "pid": project},
            )

        artifacts = CanonicalArtifactRepository(base_root=base_root)

        definitions = None
        try:
            async with Session() as s:
                publisher = DefinitionPublisher(
                    artifacts=artifacts,
                    repository=WorkpaperSyncRepository(s),
                    project_id=project,
                    wp_id=wp,
                    source_commit="task43",
                )
                definitions = await P.publish_pilot_definitions(publisher)
                await s.commit()
            snap["phases"]["publish"] = definitions.as_dict()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("publish", exc)

        try:
            async with Session() as s:
                publisher = DefinitionPublisher(
                    artifacts=artifacts,
                    repository=WorkpaperSyncRepository(s),
                    project_id=project,
                    wp_id=wp,
                    source_commit="task43-order",
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

        run_seed = uuid.uuid4()
        manifest_pub = artifacts.publish_evidence_manifest(
            project_id=project,
            wp_id=wp,
            entry_id=P.PILOT_ENTRY_ID,
            test_run_id=run_seed,
            payload=json.dumps({"run": "task43"}, sort_keys=True).encode(),
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
            source_commit="task43-commit",
            runner_version=PH.HARNESS_VERSION,
            onlyoffice_build=PH.NOT_EXECUTED,
            browser_build=PH.NOT_EXECUTED,
        )

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

        declared = {item.scenario_id: item for item in PH.all_declared_scenarios()}
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
                            "result": str(row.result),
                            "scenario_kind": str(row.scenario_kind),
                            "error_code": row.error_code,
                            "ordinal": int(row.ordinal),
                            "decision_result": decision.result,
                            "entity_ids": entity_ids,
                            "operation_ids": [str(i) for i in (row.operation_ids or [])],
                            "application_ids": [
                                str(i) for i in (row.application_ids or [])
                            ],
                            "recovery_case_ids": [
                                str(i) for i in (row.recovery_case_ids or [])
                            ],
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
                outcome_rows: list[Any] = []
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
                        outcome_rows.append({"scenario_id": scenario_id, "rejected": False})
                    except PH.HarnessRejected as exc:
                        outcome_rows.append(
                            {
                                "scenario_id": scenario_id,
                                "rejected": True,
                                "kind": exc.kind.value,
                            }
                        )
                snap["phases"]["entity_reuse_refused"] = {
                    "pair": pair,
                    "outcome": outcome_rows,
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("entity_reuse_refused", exc)

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

        # ── 只读复核：整轮结束后**重新观测**真实库，与开头逐字段比对 ─────────
        try:
            snap["phases"]["real_store_after"] = await _observe_real_store(admin)
        except Exception as exc:  # noqa: BLE001
            _phase_failed("real_store_after", exc)

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


@pytest.fixture(scope="module")
def real(snap: dict[str, Any]) -> dict[str, Any]:
    return snap["phases"]["real_store"]


@pytest.fixture(scope="module")
def props(snap: dict[str, Any]) -> dict[str, Any]:
    return snap["phases"]["properties"]


# ═══════════════════════════════════════════════════════════════════════════
# 0. 采集自身
# ═══════════════════════════════════════════════════════════════════════════


def test_v151_applies_cleanly(snap: dict[str, Any]) -> None:
    assert snap["apply_errors"] == [], snap["apply_errors"][:2]


def test_no_phase_crashed_during_collection(snap: dict[str, Any]) -> None:
    """采集阶段一个都不许抛。

    这是「异常记录不穿透」那个决定的另一半：穿透会让整个 module 变成 collection ERROR，
    而 `-rf` 只列 FAILED 不列 ERROR ⇒ 定向变异看不到预期失败项 ⇒ 判 GREEN。
    """
    assert snap["harness_errors"] == {}, snap["harness_errors"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. 真实库观测（冻结的事实 + 真实载荷上的 Property 22 oracle）
# ═══════════════════════════════════════════════════════════════════════════


def test_soe_store_item_exists_in_the_real_database(real: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    assert real["item_id"] == P.STORE_ITEM_ID
    assert real["row_count"] == EXPECTED_SOE_STORE_ROWS, real["row_count"]
    for row in real["rows"]:
        assert row.get("parse_error") is None, row
        assert row["version"] == P.STORE_STATE_VERSION, row
        assert row["bytes"] > 0, row


def test_every_real_payload_carries_my_two_tables(real: dict[str, Any]) -> None:
    for row in real["rows"]:
        assert row["has_matrix_table"] is True, row["wp_id"]
        assert row["has_record_table"] is True, row["wp_id"]


def test_real_metric_ids_and_labels_match_the_contract(real: dict[str, Any]) -> None:
    """真实库里的 10 个 metric 行 id / label 与契约常量**逐字**相等。"""
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    expected_ids = [key for key, _label in P.MATRIX_METRICS]
    expected_labels = [label for _key, label in P.MATRIX_METRICS]
    for row in real["rows"]:
        assert row["metric_ids"] == expected_ids, row["wp_id"]
        assert row["metric_labels"] == expected_labels, row["wp_id"]
        assert len(row["metric_ids"]) == EXPECTED_METRIC_ROWS


def test_real_entity_slots_are_five_named_placeholders(real: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    for row in real["rows"]:
        assert len(row["entity_names"]) == EXPECTED_ENTITY_SLOTS, row
        assert list(row["entity_names"]) == list(P.RENDER_SLOT_DEFAULT_NAMES), row


def test_two_of_three_payloads_use_the_modern_slot_seq_keys(real: dict[str, Any]) -> None:
    """🔴 本任务的第 6 条欠账就是这条观测：2 条现代键 + 1 条历史键，无迁移。"""
    modern = [row for row in real["rows"] if row["modern_column_keys"]]
    legacy = [row for row in real["rows"] if row["legacy_column_keys"]]
    assert len(modern) == EXPECTED_MODERN_KEY_ROWS, [r["wp_id"] for r in modern]
    assert len(legacy) == EXPECTED_LEGACY_KEY_ROWS, [r["wp_id"] for r in legacy]
    assert {r["wp_id"] for r in modern} & {r["wp_id"] for r in legacy} == set()
    for row in modern:
        assert len(row["modern_column_keys"]) == EXPECTED_DYNAMIC_COLUMNS, row["wp_id"]
    for row in legacy:
        assert len(row["legacy_column_keys"]) == EXPECTED_DYNAMIC_COLUMNS, row["wp_id"]


def test_modern_payloads_split_into_one_hundred_fields(real: dict[str, Any]) -> None:
    """**Property 22 的行为级 oracle 跑在真实载荷上**：10 metric × 10 动态列。"""
    modern = [row for row in real["rows"] if row["modern_column_keys"]]
    for row in modern:
        assert row["projection_error"] is None, row
        assert row["projection_field_count"] == (
            EXPECTED_METRIC_ROWS * EXPECTED_DYNAMIC_COLUMNS
        ), row


def test_legacy_payload_fails_closed_instead_of_dropping_the_rows(
    real: dict[str, Any]
) -> None:
    """历史键载荷必须 fail closed 并点名历史键 —— 静默丢整行是最贵的 fail-open。"""
    legacy = [row for row in real["rows"] if row["legacy_column_keys"]]
    assert legacy, real["rows"]
    for row in legacy:
        assert row["projection_field_count"] is None, row
        assert "StorePayloadError" in str(row["projection_error"]), row
        assert "改造前的历史键" in str(row["projection_error"]), row


def test_legacy_debt_note_matches_the_observation(real: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    note = P.UPSTREAM_DEBT_LEGACY_COLUMN_KEYS_STRANDED
    assert f"共 {real['row_count']} 条" in note, note
    assert f"{EXPECTED_MODERN_KEY_ROWS} 条用改造后" in note, note


def test_real_workpaper_data_is_untouched(snap: dict[str, Any]) -> None:
    """整轮跑完后重新观测，与开头逐字段比对 —— 中间任何一次写真实库都会打红。"""
    before = snap["phases"]["real_store"]
    after = snap["phases"]["real_store_after"]
    assert before["digest"] == after["digest"]
    assert before["row_count"] == after["row_count"]
    for lhs, rhs in zip(before["rows"], after["rows"]):
        assert lhs == rhs, (lhs.get("wp_id"), rhs.get("wp_id"))


def test_authoritative_template_is_untouched() -> None:
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    data = P.read_authoritative_template()
    assert hashlib.sha256(data).hexdigest() == P.TEMPLATE_SHA256


# ═══════════════════════════════════════════════════════════════════════════
# 2. Property 22 的键级与合并级 oracle（真跑 merge，不是断言常量）
# ═══════════════════════════════════════════════════════════════════════════


def test_property22_keys_survive_renaming_and_duplicate_labels(
    props: dict[str, Any]
) -> None:
    assert props["keys_unchanged_after_rename"] is True
    assert props["derived_equals_before"] is True
    assert props["duplicate_label_count"] > 0, props
    assert props["distinct_keys"] == EXPECTED_DYNAMIC_COLUMNS
    assert props["duplicate_leaf_labels"] == {
        "期末数/本期发生额": EXPECTED_ENTITY_SLOTS,
        "期初数/上期发生额": EXPECTED_ENTITY_SLOTS,
    }
    assert props["binding_columns"] == list("CDEFGHIJKL")


def test_property25_different_field_merge_really_ran(props: dict[str, Any]) -> None:
    """两个键的 label 完全相同却能分开合并 ⇒ identity 不是 label（Property 22 行为级）。"""
    assert props["merge_conflict_count"] == 0, props
    assert len(props["merge_has_both_sides"]) == 2, props


def test_property26_same_field_conflict_really_ran(props: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    assert props["same_field_conflict_count"] >= 1, props
    assert props["same_field_conflict_keys"] == [
        P.stable_key_for_metric_cell("minority-fs-1", f"{P.MATRIX_TABLE_KEY}_1")
    ], props


# ═══════════════════════════════════════════════════════════════════════════
# 3. 四个 definition + 一个 non-null bundle 真的落库
# ═══════════════════════════════════════════════════════════════════════════


def test_four_definitions_and_one_bundle_are_published(snap: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    published = snap["phases"]["publish"]
    assert published["entry_id"] == P.PILOT_ENTRY_ID
    assert published["adapter_id"] == P.PILOT_ADAPTER_ID
    assert published["authority_model"] == "projection_contract"
    for key in (
        "authority_model_definition_sha256",
        "template_definition_sha256",
        "instrumentation_definition_sha256",
        "contract_definition_sha256",
        "definition_bundle_sha256",
    ):
        assert re.fullmatch(r"[0-9a-f]{64}", published[key]), (key, published[key])
    digests = {
        published[key]
        for key in (
            "authority_model_definition_sha256",
            "template_definition_sha256",
            "instrumentation_definition_sha256",
            "contract_definition_sha256",
            "definition_bundle_sha256",
        )
    }
    assert len(digests) == 5, digests
    children = snap["phases"]["bundle_row"]["children"]
    assert len(children) == 4, children
    assert {row["kind"] for row in children} == {
        "authority_model",
        "template",
        "instrumentation",
        "contract",
    }


def test_bundle_is_non_null_and_all_children_are_approved(snap: dict[str, Any]) -> None:
    row = snap["phases"]["bundle_row"]
    assert row["state"] == "approved"
    for kind, (slot_type, digest) in row["slots"].items():
        assert slot_type == "definition", (kind, slot_type)
        assert re.fullmatch(r"[0-9a-f]{64}", digest), (kind, digest)
        assert digest != "0" * 64
    for child in row["children"]:
        assert child["state"] == "approved", child


def test_bundle_slot_digests_match_the_published_definitions(
    snap: dict[str, Any]
) -> None:
    published = snap["phases"]["publish"]
    slots = snap["phases"]["bundle_row"]["slots"]
    assert slots["template"][1] == published["template_definition_sha256"]
    assert slots["instrumentation"][1] == published["instrumentation_definition_sha256"]
    assert slots["contract"][1] == published["contract_definition_sha256"]
    assert (
        snap["phases"]["bundle_row"]["authority_model_definition_sha256"]
        == published["authority_model_definition_sha256"]
    )


def test_contract_child_digest_equals_the_disk_contract(snap: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    published = snap["phases"]["publish"]
    assert published["contract_definition_sha256"] == P.load_pilot_contract().canonical_sha256


def test_publish_order_is_enforced(snap: dict[str, Any]) -> None:
    """contract 先于 template 必须被 `DefinitionPublisher` 拒（顺序不是靠调用方记得）。"""
    assert snap["phases"]["publish_order"]["rejected"] is True, snap["phases"][
        "publish_order"
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 4. harness：plan → 24 场景 → finalize
# ═══════════════════════════════════════════════════════════════════════════


def test_plan_uses_this_pilot_bundle_and_derives_the_standard_set(
    snap: dict[str, Any]
) -> None:
    plan = snap["phases"]["plan"]
    published = snap["phases"]["publish"]
    assert plan["bundle_digest"] == published["definition_bundle_sha256"]
    assert plan["authority_model"] == "projection_contract"
    assert plan["scenario_count"] == EXPECTED_REQUIRED_SCENARIOS, plan["scenario_count"]
    assert plan["close_required"] is True
    assert plan["substituted"] is False
    assert "different_field_merge" in plan["scenario_ids"]
    assert "same_field_conflict_resolve" in plan["scenario_ids"]
    assert "dynamic_column_stable_keys" not in plan["scenario_ids"]


def test_required_digest_is_not_another_pilots(snap: dict[str, Any]) -> None:
    """本 entry 的 required digest 与 Task 40/41/42 的都不同（不复用别的 bundle）。"""
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P
    from app.services.workpaper_sync.entry_profile import (
        load_entry_manifest,
        manifest_entries_by_id,
    )
    from app.services.workpaper_sync.evidence import derive_for_manifest_entry

    entries = manifest_entries_by_id(load_entry_manifest())
    mine = snap["phases"]["plan"]["required_digest"]
    assert mine == snap["phases"]["open_run"]["required_scenario_set_digest"]
    assert snap["phases"]["open_run"]["derived_digest_matches"] is True
    for other_id in (
        "xlsx/b60/gt-b60-bundle",
        "xlsx/gt-d2-accounts-receivable",
        "xlsx/gt-h1-fixed-assets",
    ):
        other = derive_for_manifest_entry(
            entries[other_id], authority_model=P.AUTHORITY_MODEL
        )
        assert other.digest != mine, other_id


def test_every_required_scenario_has_a_persisted_row(snap: dict[str, Any]) -> None:
    plan = snap["phases"]["plan"]
    persisted = snap["phases"]["persisted_rows"]
    assert set(persisted) == set(plan["scenario_ids"])
    assert len(persisted) == EXPECTED_REQUIRED_SCENARIOS


def test_no_entity_is_reused_across_scenarios(snap: dict[str, Any]) -> None:
    reuse = snap["phases"]["entity_reuse"]
    assert reuse["total"] > 0
    assert reuse["total"] == reuse["distinct"], reuse


def test_reused_entity_is_refused_at_write_time(snap: dict[str, Any]) -> None:
    outcome = snap["phases"]["entity_reuse_refused"]
    assert len(outcome["pair"]) == 2, outcome
    assert outcome["outcome"][0]["rejected"] is False, outcome
    assert outcome["outcome"][1]["rejected"] is True, outcome


def test_black_box_scenarios_are_unverifiable(snap: dict[str, Any]) -> None:
    """需要真实 OO/浏览器的场景一律 `unverifiable`（Property 49 后半句）。"""
    from app.services.workpaper_sync import pilot_harness as PH

    results = snap["phases"]["scenarios"]
    for scenario_id in snap["phases"]["plan"]["black_box"]:
        assert results[scenario_id]["result"] == "unverifiable", (
            scenario_id,
            results[scenario_id],
        )
        assert PH.SCENARIO_ORACLES[scenario_id].needs_black_box is True


def test_upstream_gap_scenarios_are_failed_not_unverifiable(
    snap: dict[str, Any]
) -> None:
    """Task 32 的两条缺口是**实现缺失**而不是环境缺失 ⇒ `failed`，且判定顺序在黑盒之前。"""
    results = snap["phases"]["scenarios"]
    debts = snap["phases"]["plan"]["upstream_debt"]
    assert set(debts) == {
        "same_application_higher_sequence_fold",
        "wrong_prior_confirmation_bundle_fence_contributor_rejected",
    }, debts
    for scenario_id in debts:
        assert results[scenario_id]["result"] == "failed", (
            scenario_id,
            results[scenario_id],
        )
        assert results[scenario_id]["error_code"] == "upstream_gap", results[scenario_id]


def test_offline_scenarios_that_can_pass_really_passed(snap: dict[str, Any]) -> None:
    """merge 家族与 single close 在进程内可判 ⇒ 必须真的 `passed`（否则分母为空）。"""
    results = snap["phases"]["scenarios"]
    for scenario_id in (
        "different_field_merge",
        "same_field_conflict_resolve",
        "single_participant_close",
    ):
        assert results[scenario_id]["result"] == "passed", (
            scenario_id,
            results[scenario_id],
        )


def test_run_is_not_verified_without_real_onlyoffice(snap: dict[str, Any]) -> None:
    finalize = snap["phases"]["finalize"]
    assert finalize["aggregate_result"] == "failed", finalize
    assert finalize["finished_at_set"] is True


def test_result_is_never_supplied_by_the_caller() -> None:
    """`ScenarioObservation` 没有 `result` 字段；`finalize_run` 也不吃 `aggregate_result`。"""
    import inspect

    from app.services.workpaper_sync import pilot_harness as PH

    assert "result" not in PH.ScenarioObservation.__dataclass_fields__
    params = set(inspect.signature(PH.SyncTestRunHarness.finalize_run).parameters)
    assert "aggregate_result" not in params
    assert "verified_at" not in params
    assert "result" not in set(
        inspect.signature(PH.SyncTestRunHarness.record_scenario).parameters
    )


def test_pilot_class_stays_unverifiable_after_this_run(snap: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_harness as PH

    assert snap["phases"]["finalize"]["aggregate_result"] == "failed"
    assessment = PH.assess_pilot_classes()[PH.PilotClass.g7_two_level_dynamic]
    assert assessment.status is PH.PilotClassStatus.unverifiable
    assert assessment.verified_entry_ids == ()


def test_download_only_scenario_has_zero_operation_and_application(
    snap: dict[str, Any]
) -> None:
    from app.services.workpaper_sync import pilot_harness as PH

    declared = {item.scenario_id: item for item in PH.all_declared_scenarios()}
    scenario_id = "download_only_zero_three_entities"
    assert declared[scenario_id].expects_application is False
    row = snap["phases"]["scenarios"][scenario_id]
    # AC 12.11：download-only 断言 **operation/application** 为空；recovery case 本身存在
    # 才是这条场景的意义（claim 前三实体为 0，claim 后才有 operation）。
    assert row["operation_ids"] == [], row
    assert row["application_ids"] == [], row
    assert len(row["recovery_case_ids"]) == 1, row
    assert declared[scenario_id].expects_recovery_case is True


def test_every_scenario_row_binds_a_published_trace_bundle(snap: dict[str, Any]) -> None:
    for scenario_id, row in snap["phases"]["scenarios"].items():
        assert re.fullmatch(r"[0-9a-f]{64}", row["trace_sha256"]), (scenario_id, row)
    digests = {row["trace_sha256"] for row in snap["phases"]["scenarios"].values()}
    assert len(digests) == EXPECTED_REQUIRED_SCENARIOS, len(digests)


def test_ordinals_are_dense_and_unique(snap: dict[str, Any]) -> None:
    ordinals = sorted(row["ordinal"] for row in snap["phases"]["scenarios"].values())
    assert ordinals == list(range(min(ordinals), min(ordinals) + len(ordinals)))
    assert len(set(ordinals)) == EXPECTED_REQUIRED_SCENARIOS


def test_run_row_freezes_this_pilot_identity(snap: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    run = snap["phases"]["open_run"]
    published = snap["phases"]["publish"]
    assert run["entry_id"] == P.PILOT_ENTRY_ID
    assert run["definition_bundle_sha256"] == published["definition_bundle_sha256"]
    assert (
        run["authority_model_definition_sha256"]
        == published["authority_model_definition_sha256"]
    )
    assert run["editability"] == "editable"
    assert run["room_model"] == "shared"
