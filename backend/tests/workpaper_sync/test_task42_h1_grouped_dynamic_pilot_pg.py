# -*- coding: utf-8 -*-
"""Task 42 真实 PostgreSQL 守卫：definitions/bundle 真发布 + 全场景 run + 真实库观测。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 42
Requirements: 6.3, 6.4, 6.5, 6.9, 6.16, 12.1, 12.2, 12.10, 14.1
Properties: **P22 / P23 / P27 / P49 / P66 / P69**

═══ 这一半证的是「真跑了 + 结果真的是推导出来的 + 真实库观测被冻结」 ═══

离线守卫证判据正确，但纯函数**可能是死代码**。本文件在真库上证明：

* `template → instrumentation → contract → bundle` 四段真发布成四行 definition + 一行
  non-null bundle，且**发布顺序**被 `DefinitionPublisher` 强制（contract 先于 template 必拒）；
* Task 39 的 harness 用**这个 bundle** plan 出 **24** 条 required scenario 并逐条落库，
  逐场景各自实体、无复用；一条 operation 复用两个场景必须被拒；
* 没有真实 OO/浏览器时 `aggregate_result` 必须是 `failed` 而不是 `passed`（Property 49）；
* 本 entry 的 `required_scenario_set_digest` 与 Task 40/41 的**都不同**（不复用别的 bundle）；
* 🔴 **真实库观测被冻结**：`checklist_responses` 里 `item_id='H1-8-rows'`（本 pilot 的
  store 载体）**全库为空**（0 行、0 字节），而同一族的 `H1-2-rows` 有真实载荷。这条事实
  正是离线守卫用合成行跑 merge/delete-update oracle 的**理由** —— 真实数据一旦出现且
  形态不符（不是 JSON 数组 / 缺 `rowId` / 有重复 `rowId` / 缺契约声明的字段），本文件打红。

═══ 为什么「载荷为空」不 skip、也不静默 ═══

AC 14.9 允许「无法获得合法对象时标 UNVERIFIABLE」，但这里要冻结的是**观测本身**：
「今天为空」是一条可打红的事实，而不是缺证据。若写成 skip，将来数据出现时守卫悄悄不跑；
若写成「有就跑没有就算了」，那条分支在真实数据上不可达 ⇒ 永久 GREEN（本 spec 假绿第④源）。
故本文件**总是**跑合成路径的 oracle，**并且**总是断言真实库的观测形态。

═══ 隔离与采集 ═══

scratch schema `tmp_task42_pilot_<hex>` + 独立文件根，结束 `DROP SCHEMA CASCADE` + `rmtree`。
真实数据只经 **admin engine 只读** `public.checklist_responses`，一个字节都不写
（`test_real_workpaper_data_is_untouched` 复核）。
全部阶段由**一次 `asyncio.run`** 跑完落进快照（module fixture）—— 每个测试各自开 async
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

_SCHEMA_PREFIX = "tmp_task42_pilot_"

#: 参考库里唯一带完整 `H1-*` item 集合的真实底稿（**只读**）。
H1_WP_ID = "dbd9cc36-0d78-468a-b342-9478e15671d3"

#: 与离线守卫互锁的冻结观测（两侧任一漂移都打红）。
EXPECTED_H1_ITEM_COUNT = 24
EXPECTED_H1_TOTAL_REMARK_BYTES = 19_524
EXPECTED_H1_2_ROWS_BYTES = 9_026
#: 🔴 本 pilot 的 store 载体今天**全库为空**。
EXPECTED_DISPOSAL_ROWS_BYTES = 0
EXPECTED_DISPOSAL_ROWS_WORKPAPERS = 0
EXPECTED_REQUIRED_SCENARIOS = 24
EXPECTED_FIELDS_PER_ROW = 25

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

_MERGE_ROW = "disp-merge-fixture-0001"


def _merge_evidence(*, conflict: bool) -> Any:
    """用本 pilot 契约的真实 stable key 构造三方 projection。

    * `conflict=False` ⇒ P25：current 改 A（`asset_name`）、incoming 改 B（`remark` 位
      —— 本契约没有 remark 列，改用 `index_ref`），两键不同 ⇒ 自动合并且 conflict_count=0。
    * `conflict=True`  ⇒ P26：三方在**同一键**（`asset_name`）上三个不同值。

    键不是编的：`contract.field_by_stable_key` 对未登记键抛，写错立刻炸。
    """
    from app.services.workpaper_sync import pilot_h1_grouped_dynamic as P
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.pilot_harness import MergeEvidence

    contract = P.load_pilot_contract()
    key_a = P.stable_key_for("asset_name", _MERGE_ROW)
    key_b = P.stable_key_for("index_ref", _MERGE_ROW)
    spec_a = contract.field_by_stable_key(P.stable_key_for("asset_name"))
    spec_b = contract.field_by_stable_key(P.stable_key_for("index_ref"))

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
                    row_key=_MERGE_ROW,
                )
                for key, (value, spec) in values.items()
            },
            row_keys={P.ROWS_TABLE_KEY: (_MERGE_ROW,)},
        )

    if conflict:
        return MergeEvidence(
            base=projection({key_a: ("三号厂房", spec_a)}),
            current=projection({key_a: ("三号厂房（东区）", spec_a)}),
            incoming=projection({key_a: ("三号生产厂房", spec_a)}),
            contract=contract,
            conflict_key=key_a,
        )
    return MergeEvidence(
        base=projection({key_a: ("三号厂房", spec_a), key_b: ("", spec_b)}),
        current=projection({key_a: ("三号厂房（东区）", spec_a), key_b: ("", spec_b)}),
        incoming=projection({key_a: ("三号厂房", spec_a), key_b: ("H1-8-1", spec_b)}),
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

    from app.services.workpaper_sync import pilot_h1_grouped_dynamic as P

    async with engine.connect() as conn:
        # ① 本 pilot 的 store item：全库有几条、多少字节。
        disposal = (
            await conn.execute(
                sa.text(
                    "SELECT wp_id, coalesce(length(remark), 0) AS n "
                    "FROM public.checklist_responses WHERE item_id = :item "
                    "ORDER BY n DESC"
                ),
                {"item": P.STORE_ITEM_ID},
            )
        ).all()
        # ② 参考底稿的 H1-* item 全貌（证明这份底稿真的有 H1 数据）。
        h1_items = (
            await conn.execute(
                sa.text(
                    "SELECT item_id, coalesce(length(remark), 0) AS n, remark "
                    "FROM public.checklist_responses "
                    "WHERE wp_id = :wp AND item_id LIKE 'H1-%' ORDER BY item_id"
                ),
                {"wp": H1_WP_ID},
            )
        ).all()
        # ③ 同族的 H1-2-rows 的真实载荷（用来证明「同族有数据、本 item 没有」）。
        h1_2 = (
            await conn.execute(
                sa.text(
                    "SELECT remark FROM public.checklist_responses "
                    "WHERE wp_id = :wp AND item_id = 'H1-2-rows'"
                ),
                {"wp": H1_WP_ID},
            )
        ).first()

    payload_shape: dict[str, Any] = {"present": False}
    if h1_2 is not None and h1_2.remark:
        try:
            parsed = json.loads(h1_2.remark)
            payload_shape = {
                "present": True,
                "bytes": len(h1_2.remark),
                "is_list": isinstance(parsed, list),
                "rows": len(parsed) if isinstance(parsed, list) else -1,
                "row_id_key_present": bool(
                    isinstance(parsed, list)
                    and parsed
                    and P.ROW_IDENTITY_STORE_KEY in parsed[0]
                ),
            }
        except ValueError as exc:
            payload_shape = {"present": True, "parse_error": str(exc)}

    return {
        "disposal_item_id": P.STORE_ITEM_ID,
        "disposal_rows": [
            {"wp_id": str(row.wp_id), "bytes": int(row.n)} for row in disposal
        ],
        "disposal_total_bytes": sum(int(row.n) for row in disposal),
        "h1_item_count": len(h1_items),
        "h1_total_bytes": sum(int(row.n) for row in h1_items),
        "h1_item_ids": sorted(str(row.item_id) for row in h1_items),
        "h1_2_payload": payload_shape,
        "wp_sha256": _d(
            json.dumps(
                sorted((str(row.item_id), int(row.n)) for row in h1_items), sort_keys=True
            )
        ),
    }


def _synthetic_property_phases() -> dict[str, Any]:
    """在**合成行**上跑 Property 22/23/27 的 oracle（理由见模块 docstring）。"""
    from app.services.workpaper_sync import pilot_h1_grouped_dynamic as P
    from app.services.workpaper_sync.merge import merge_projections

    contract = P.load_pilot_contract()

    def rows(count: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for index in range(count):
            row: dict[str, Any] = {P.ROW_IDENTITY_STORE_KEY: f"disp-pg-{index:04d}"}
            for _key, _col, _mode, value_type, path, _leaf, _label in (
                P.MANAGED_FIELD_SPECS
            ):
                if value_type == "amount":
                    row[path] = float(index + 1)
                elif value_type == "integer":
                    row[path] = index + 1
                elif value_type == "date":
                    row[path] = "2026-01-01"
                else:
                    row[path] = f"{path}-{index}"
            out.append(row)
        return out

    total = 20
    base_rows = rows(total)
    victim = base_rows[6][P.ROW_IDENTITY_STORE_KEY]
    current = [r for r in base_rows if r[P.ROW_IDENTITY_STORE_KEY] != victim]
    incoming = json.loads(json.dumps(base_rows))
    for row in incoming:
        if row[P.ROW_IDENTITY_STORE_KEY] == victim:
            row["originalCost"] = 987654.0

    def projection(payload: list[dict[str, Any]]) -> Any:
        return P.build_store_projection(payload, contract=contract)

    base_projection = projection(base_rows)
    outcome = merge_projections(
        base=base_projection,
        current=projection(current),
        incoming=projection(incoming),
        contract=contract,
    )
    untouched_compared = 0
    untouched_mismatched: list[str] = []
    for row in base_rows:
        identity = row[P.ROW_IDENTITY_STORE_KEY]
        if identity == victim:
            continue
        for spec in P.MANAGED_FIELD_SPECS:
            key = P.stable_key_for(spec[0], identity)
            untouched_compared += 1
            got = outcome.merged.values.get(key)
            if got is None or got.value != base_projection.values[key].value:
                untouched_mismatched.append(key)

    reordered = merge_projections(
        base=base_projection,
        current=base_projection,
        incoming=projection(list(reversed(base_rows))),
        contract=contract,
    )

    # Property 22：25 个 stable key 互不相同，且 7 列共用 3 个重复叶子 label。
    from collections import Counter

    labels = Counter(spec[6] for spec in P.MANAGED_FIELD_SPECS)
    return {
        "rows": total,
        "fields_per_row": EXPECTED_FIELDS_PER_ROW,
        "projection_field_count": len(base_projection.values),
        "victim": victim,
        "conflict_count": outcome.conflict_count,
        "conflict_kinds": [record.kind.value for record in outcome.conflicts.records],
        "conflict_keys": [
            record.locator.stable_field_key for record in outcome.conflicts.records
        ],
        "untouched_compared": untouched_compared,
        "untouched_mismatched": untouched_mismatched[:5],
        "reorder_conflict_count": reordered.conflict_count,
        "duplicate_leaf_labels": {
            label: count for label, count in sorted(labels.items()) if count > 1
        },
        "distinct_stable_keys": len(
            {P.stable_key_for(spec[0]) for spec in P.MANAGED_FIELD_SPECS}
        ),
        "labels_never_in_keys": not [
            key
            for key in (P.stable_key_for(spec[0]) for spec in P.MANAGED_FIELD_SPECS)
            for label in labels
            if label in key
        ],
        "skeleton_rows": {
            str(seed): P.skeleton_row_count(seed) for seed in (0, 1, 2, 15, 1260)
        },
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
    from app.services.workpaper_sync import pilot_h1_grouped_dynamic as P
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
            "Task 42 的判据是「pilot definitions/bundle 真的落进 V151 的表」与「真实库里 "
            f"{P.STORE_ITEM_ID} 的观测形态」，必须真实 PostgreSQL；当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task42_store_"))
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
        # ── phase: 真实库观测（只读 public）+ 合成行 oracle ────────────────
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
                sa.text("INSERT INTO projects (id, name) VALUES (:pid, 'task42')"),
                {"pid": project},
            )
            await conn.execute(
                sa.text("INSERT INTO working_paper (id, project_id) VALUES (:wid, :pid)"),
                {"wid": wp, "pid": project},
            )

        artifacts = CanonicalArtifactRepository(base_root=base_root)

        # ── phase: 真发布四个 definition + non-null bundle ─────────────────
        definitions = None
        try:
            async with Session() as s:
                publisher = DefinitionPublisher(
                    artifacts=artifacts,
                    repository=WorkpaperSyncRepository(s),
                    project_id=project,
                    wp_id=wp,
                    source_commit="task42",
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
                    source_commit="task42-order",
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
            payload=json.dumps({"run": "task42"}, sort_keys=True).encode(),
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
            source_commit="task42-commit",
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

        # ── phase: 只读复核 —— 全程结束后**重新观测**真实库，与开头逐项比对 ──
        #    🔴 这条是真判据而不是同义反复：整轮跑完之后再读一次 `public.checklist_responses`，
        #    与开头的观测逐字段比。若中间有任何一步写了真实数据（哪怕只是 UPDATE 一个
        #    remark），这里立刻打红。
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
    assert snap["schema"].startswith(_SCHEMA_PREFIX)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 真实库观测：本 pilot 的 store 载体今天为空（可打红的事实）
# ═══════════════════════════════════════════════════════════════════════════


def test_disposal_store_item_is_empty_across_the_whole_database(
    real: dict[str, Any]
) -> None:
    """🔴 `H1-8-rows` **全库 0 行 0 字节** —— 这是合成行 oracle 的理由，不是缺证据。

    真实数据一旦出现，这条打红，提醒把 oracle 改跑在真实载荷上（并核对形态）。
    """
    from app.services.workpaper_sync import pilot_h1_grouped_dynamic as P

    assert real["disposal_item_id"] == P.STORE_ITEM_ID == "H1-8-rows"
    assert len(real["disposal_rows"]) == EXPECTED_DISPOSAL_ROWS_WORKPAPERS == 0, real[
        "disposal_rows"
    ][:3]
    assert real["disposal_total_bytes"] == EXPECTED_DISPOSAL_ROWS_BYTES == 0


def test_contract_declares_the_observed_emptiness(real: dict[str, Any]) -> None:
    """契约的 review 段登记了这条观测（离线与在线两侧互锁）。"""
    from app.services.workpaper_sync import pilot_h1_grouped_dynamic as P

    payload = json.loads(P.contract_file_path().read_text(encoding="utf-8"))
    store = payload["review"]["html_store"]
    assert store["item_id"] == P.STORE_ITEM_ID
    assert store["observed_empty_in_reference_database"] is True
    assert real["disposal_total_bytes"] == 0


def test_the_same_workpaper_family_really_has_h1_data(real: dict[str, Any]) -> None:
    """「本 item 为空」不是「这个底稿没有 H1 数据」—— 同族 24 条 item / 19,524 字节。

    这条把上面那条从「库是空的」收紧成「**这一个 item** 是空的」，否则
    `disposal_total_bytes == 0` 在一个完全空库上也成立（空集恒真）。
    """
    assert real["h1_item_count"] == EXPECTED_H1_ITEM_COUNT == 24, real["h1_item_count"]
    assert real["h1_total_bytes"] == EXPECTED_H1_TOTAL_REMARK_BYTES, real["h1_total_bytes"]
    assert "H1-2-rows" in real["h1_item_ids"]
    assert "H1-8-rows" not in real["h1_item_ids"]


def test_sibling_payload_shape_matches_the_contract_row_identity_convention(
    real: dict[str, Any]
) -> None:
    """同族 `H1-2-rows` 的真实载荷形态与本契约的行身份约定一致（JSON 数组 + `rowId`）。

    它证明「行身份取载荷自带的 `rowId`」不是本模块臆想的约定，而是这一族底稿真实在用的。
    """
    from app.services.workpaper_sync import pilot_h1_grouped_dynamic as P

    shape = real["h1_2_payload"]
    assert shape["present"] is True, shape
    assert "parse_error" not in shape, shape
    assert shape["bytes"] == EXPECTED_H1_2_ROWS_BYTES, shape["bytes"]
    assert shape["is_list"] is True
    assert shape["rows"] > 0, shape
    assert shape["row_id_key_present"] is True
    assert P.ROW_IDENTITY_STORE_KEY == "rowId"


def test_real_workpaper_data_is_untouched(snap: dict[str, Any]) -> None:
    """只读复核：整轮跑完后**重新观测**真实库，与开头逐项相同（一个字节都没写）。

    🔴 是真判据不是同义反复：`real_store_after` 是在发布 definitions、跑完 24 个场景、
    finalize 之后**第二次**读 `public.checklist_responses` 的结果。任何一步写了真实数据
    （哪怕只 UPDATE 一个 remark 的长度）都会让下面的逐字段比对失败。
    """
    before = snap["phases"]["real_store"]
    after = snap["phases"]["real_store_after"]
    assert after is not before, "必须是两次独立观测"
    for key in (
        "disposal_item_id",
        "disposal_rows",
        "disposal_total_bytes",
        "h1_item_count",
        "h1_total_bytes",
        "h1_item_ids",
        "h1_2_payload",
        "wp_sha256",
    ):
        assert after[key] == before[key], key
    assert isinstance(before["wp_sha256"], str) and len(before["wp_sha256"]) == 64
    # 指纹**不是**空集算出来的（否则「两次相同」在空库上恒真）。
    assert before["h1_item_count"] > 0
    assert before["h1_total_bytes"] > 0
    assert before["wp_sha256"] != _d(json.dumps([], sort_keys=True))


def test_authority_template_is_untouched() -> None:
    """`backend/wp_templates/` 运行时只读（Requirement 9.9）。"""
    from app.services.workpaper_sync import pilot_h1_grouped_dynamic as P

    data = P.authoritative_template_path().read_bytes()
    assert hashlib.sha256(data).hexdigest() == P.TEMPLATE_SHA256


# ═══════════════════════════════════════════════════════════════════════════
# 2. Property 22 / 23 / 27 在真实契约形态上真跑一次
# ═══════════════════════════════════════════════════════════════════════════


def test_projection_splits_into_one_field_per_column_per_row(
    props: dict[str, Any]
) -> None:
    assert props["rows"] == 20
    assert props["fields_per_row"] == EXPECTED_FIELDS_PER_ROW == 25
    assert props["projection_field_count"] == 20 * 25 == 500


def test_property22_duplicate_labels_do_not_collide(props: dict[str, Any]) -> None:
    """Property 22：7 列共用 3 个重复叶子 label，而 25 个 stable key 互不相同。"""
    assert props["duplicate_leaf_labels"] == {
        "对手方名称": 2,
        "金额": 2,
        "日期/编号": 3,
    }, props["duplicate_leaf_labels"]
    assert sum(props["duplicate_leaf_labels"].values()) == 7
    assert props["distinct_stable_keys"] == EXPECTED_FIELDS_PER_ROW == 25
    assert props["labels_never_in_keys"] is True


def test_property27_only_the_touched_row_conflicts(props: dict[str, Any]) -> None:
    """Property 27：一侧删行 + 另一侧改同 rowId ⇒ 恰 1 条 `delete_update`。"""
    assert props["conflict_count"] == 1, props["conflict_kinds"]
    assert props["conflict_kinds"] == ["delete_update"], props["conflict_kinds"]
    assert len(props["conflict_keys"]) == 1
    assert props["victim"] in props["conflict_keys"][0]


def test_property27_every_other_row_merges_normally(props: dict[str, Any]) -> None:
    """**非空**判据：其余 19 行 × 25 字段 = 475 个字段逐个与 base 相同，不符 0 条。"""
    assert props["untouched_compared"] == 19 * 25 == 475, props["untouched_compared"]
    assert props["untouched_mismatched"] == [], props["untouched_mismatched"]


def test_reorder_is_not_a_whole_table_overwrite(props: dict[str, Any]) -> None:
    assert props["reorder_conflict_count"] == 0


def test_skeleton_policy_is_max_seed_one(props: dict[str, Any]) -> None:
    assert props["skeleton_rows"] == {
        "0": 1,
        "1": 1,
        "2": 2,
        "15": 15,
        "1260": 1260,
    }, props["skeleton_rows"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. 四个 definition + 一个 non-null bundle 真的落库
# ═══════════════════════════════════════════════════════════════════════════


def test_four_definitions_and_one_bundle_are_published(snap: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_h1_grouped_dynamic as P

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
        assert isinstance(published[key], str) and len(published[key]) == 64, key
    ids = {
        published[key]
        for key in (
            "authority_model_definition_id",
            "template_definition_id",
            "instrumentation_definition_id",
            "contract_definition_id",
            "definition_bundle_id",
        )
    }
    assert len(ids) == 5, ids
    # digest 与本模块现算的 canonical payload 逐字一致（不是"随便发布了点什么"）。
    from app.services.workpaper_sync.definitions import canonical_digest

    assert published["template_definition_sha256"] == canonical_digest(
        P.template_definition_payload()
    )
    assert published["instrumentation_definition_sha256"] == canonical_digest(
        P.instrumentation_definition_payload()
    )
    assert published["authority_model_definition_sha256"] == canonical_digest(
        P.authority_model_payload()
    )
    assert published["contract_definition_sha256"] == P.load_pilot_contract().canonical_sha256


def test_bundle_is_non_null_and_all_children_are_approved(snap: dict[str, Any]) -> None:
    row = snap["phases"]["bundle_row"]
    assert "approved" in row["state"]
    for slot, (slot_type, digest) in row["slots"].items():
        assert slot_type.endswith("definition"), (slot, slot_type)
        assert isinstance(digest, str) and len(digest) == 64, (slot, digest)
        assert digest != "0" * 64, slot
    assert len(row["children"]) == 4, row["children"]
    kinds = sorted(child["kind"].split(".")[-1] for child in row["children"])
    assert kinds == ["authority_model", "contract", "instrumentation", "template"], kinds
    for child in row["children"]:
        assert "approved" in child["state"], child


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


def test_publish_order_is_enforced(snap: dict[str, Any]) -> None:
    """contract 先于 template 必须被 `DefinitionPublisher` 拒（顺序不可交换）。"""
    order = snap["phases"]["publish_order"]
    assert order["rejected"] is True, order
    assert "template" in order["message"] or "顺序" in order["message"], order


# ═══════════════════════════════════════════════════════════════════════════
# 4. plan / 全场景 run / finalize
# ═══════════════════════════════════════════════════════════════════════════


def test_plan_uses_this_pilot_bundle_and_derives_a_non_empty_set(
    snap: dict[str, Any]
) -> None:
    plan = snap["phases"]["plan"]
    assert plan["scenario_count"] == EXPECTED_REQUIRED_SCENARIOS == 24
    assert plan["authority_model"] == "projection_contract"
    assert plan["close_required"] is True
    assert plan["substituted"] is False
    assert plan["bundle_digest"] == snap["phases"]["publish"]["definition_bundle_sha256"]
    assert plan["black_box"], "必须有需要真实 OO 的场景，否则 Property 49 无从体现"
    # 字段级两场景没被替换掉。
    assert "different_field_merge" in plan["scenario_ids"]
    assert "same_field_conflict_resolve" in plan["scenario_ids"]
    # AC 6.4 / 6.9 自己的两条场景确实不在分母里（登记的上游缺口）。
    assert "dynamic_row_add_delete_reorder_copy" not in plan["scenario_ids"]
    assert "dynamic_column_stable_keys" not in plan["scenario_ids"]


def test_required_digest_is_not_another_pilots(snap: dict[str, Any]) -> None:
    """本 entry 的 required digest 与 Task 40/41 的**都不同**（不复用别的 bundle）。"""
    from app.services.workpaper_sync import pilot_h1_grouped_dynamic as P
    from app.services.workpaper_sync.entry_profile import (
        load_entry_manifest,
        manifest_entries_by_id,
    )
    from app.services.workpaper_sync.evidence import derive_for_manifest_entry

    entries = manifest_entries_by_id(load_entry_manifest())
    mine = snap["phases"]["plan"]["required_digest"]
    assert mine == derive_for_manifest_entry(
        entries[P.PILOT_ENTRY_ID], authority_model=P.AUTHORITY_MODEL
    ).digest
    for other in ("xlsx/b60/gt-b60-bundle", "xlsx/gt-d2-accounts-receivable"):
        assert mine != derive_for_manifest_entry(
            entries[other], authority_model=P.AUTHORITY_MODEL
        ).digest, other
    assert snap["phases"]["open_run"]["derived_digest_matches"] is True


def test_every_required_scenario_has_a_persisted_row(snap: dict[str, Any]) -> None:
    plan = snap["phases"]["plan"]
    recorded = snap["phases"]["scenarios"]
    persisted = snap["phases"]["persisted_rows"]
    assert set(recorded) == set(plan["scenario_ids"])
    assert set(persisted) == set(plan["scenario_ids"])
    assert len(persisted) == EXPECTED_REQUIRED_SCENARIOS == 24


def test_no_entity_is_reused_across_scenarios(snap: dict[str, Any]) -> None:
    reuse = snap["phases"]["entity_reuse"]
    assert reuse["total"] > 0
    assert reuse["total"] == reuse["distinct"], reuse


def test_reused_entity_is_refused_at_write_time(snap: dict[str, Any]) -> None:
    """一条 operation 冒充两个场景必须被 harness 拒（AC 12.12）。"""
    refused = snap["phases"]["entity_reuse_refused"]
    assert len(refused["pair"]) == 2, refused
    outcomes = refused["outcome"]
    assert outcomes[0]["rejected"] is False, outcomes
    assert outcomes[1]["rejected"] is True, outcomes
    assert outcomes[1]["kind"] == "entity_reused_within_run", outcomes


def test_property25_and_26_really_ran_on_this_contract(snap: dict[str, Any]) -> None:
    """merge 家族两条场景的 oracle 真跑了，且是在**本 pilot 契约**的 stable key 上。"""
    scenarios = snap["phases"]["scenarios"]
    for scenario_id in ("different_field_merge", "same_field_conflict_resolve"):
        row = scenarios[scenario_id]
        assert row["result"] == "passed", row
        assert row["error_code"] is None, row
        assert row["notes"], row


def test_black_box_scenarios_are_unverifiable(snap: dict[str, Any]) -> None:
    """需要真实 OO/浏览器的场景在 NOT_EXECUTED 下只能 `unverifiable`（Property 49）。"""
    plan = snap["phases"]["plan"]
    scenarios = snap["phases"]["scenarios"]
    assert plan["black_box"], plan
    for scenario_id in plan["black_box"]:
        row = scenarios[scenario_id]
        assert row["result"] == "unverifiable", (scenario_id, row)
        assert row["error_code"], (scenario_id, row)
    assert "identity_retention" in plan["black_box"], plan["black_box"]


def test_upstream_gap_scenarios_are_failed_not_unverifiable(
    snap: dict[str, Any]
) -> None:
    """Task 32 登记的两条缺口是**实现缺失**而不是环境缺失 ⇒ 必须 `failed`。

    判定顺序不可交换：「上游缺口 → failed」在「黑盒环境缺失 → unverifiable」**之前**，
    否则接了真实 OO 之后它们会自动变绿，而它们其实永远不会通过。
    """
    plan = snap["phases"]["plan"]
    scenarios = snap["phases"]["scenarios"]
    assert plan["upstream_debt"], plan
    for scenario_id in plan["upstream_debt"]:
        row = scenarios[scenario_id]
        assert row["result"] == "failed", (scenario_id, row)
        assert row["error_code"] == "upstream_gap", (scenario_id, row)
    assert set(plan["upstream_debt"]) == {
        "same_application_higher_sequence_fold",
        "wrong_prior_confirmation_bundle_fence_contributor_rejected",
    }, plan["upstream_debt"]


def test_run_is_not_verified_without_real_onlyoffice(snap: dict[str, Any]) -> None:
    """Property 49 的后半句：文档声明不得计为通过。"""
    finalize = snap["phases"]["finalize"]
    assert finalize["finished_at_set"] is True
    assert "failed" in finalize["aggregate_result"], finalize["aggregate_result"]
    assert "passed" not in finalize["aggregate_result"]


def test_result_is_never_supplied_by_the_caller() -> None:
    """`record_scenario` / `finalize_run` 的签名里根本没有 result 参数（结构性保证）。"""
    import inspect

    from app.services.workpaper_sync.pilot_harness import SyncTestRunHarness

    record = inspect.signature(SyncTestRunHarness.record_scenario).parameters
    assert "result" not in record, sorted(record)
    finalize = inspect.signature(SyncTestRunHarness.finalize_run).parameters
    assert "aggregate_result" not in finalize, sorted(finalize)
    assert "verified_at" not in finalize, sorted(finalize)


def test_pilot_class_stays_unverifiable_after_this_run(snap: dict[str, Any]) -> None:
    """跑完一整轮之后 pilot 类仍是 unverifiable（capability 未启用 ⇒ 不计入已验收）。"""
    from app.services.workpaper_sync import pilot_harness as PH

    assessment = PH.assess_pilot_classes()[PH.PilotClass.h1_grouped_dynamic]
    assert assessment.status is PH.PilotClassStatus.unverifiable
    assert assessment.verified_entry_ids == ()
    assert snap["phases"]["finalize"]["finished_at_set"] is True


def test_download_only_scenario_has_zero_operation_and_application(
    snap: dict[str, Any]
) -> None:
    from app.services.workpaper_sync import evidence as EV

    scenario = next(
        item
        for item in EV.PROJECTION_BASE_SCENARIOS
        if item.scenario_id == "download_only_zero_three_entities"
    )
    assert scenario.expects_zero_entities is True
    assert scenario.expects_application is False
    assert scenario.expects_recovery_case is True
    row = snap["phases"]["scenarios"]["download_only_zero_three_entities"]
    # 恰好一个实体，且它是那条 recovery case（不是 operation/application）。
    assert len(row["entity_ids"]) == 1, row["entity_ids"]
    assert all(item for item in row["entity_ids"]), row["entity_ids"]
    # 对照：一条**期望有** application 的场景确实有两个实体（判据不是"永远只有 1 个"）。
    paired = snap["phases"]["scenarios"]["different_field_merge"]
    assert len(paired["entity_ids"]) == 2, paired["entity_ids"]


def test_every_scenario_row_binds_a_published_trace_bundle(
    snap: dict[str, Any]
) -> None:
    for scenario_id, row in sorted(snap["phases"]["scenarios"].items()):
        assert isinstance(row["trace_sha256"], str), scenario_id
        assert len(row["trace_sha256"]) == 64, (scenario_id, row["trace_sha256"])
    digests = {row["trace_sha256"] for row in snap["phases"]["scenarios"].values()}
    assert len(digests) == EXPECTED_REQUIRED_SCENARIOS, len(digests)


def test_ordinals_are_dense_and_unique(snap: dict[str, Any]) -> None:
    ordinals = sorted(row["ordinal"] for row in snap["phases"]["scenarios"].values())
    assert ordinals == list(range(1, EXPECTED_REQUIRED_SCENARIOS + 1)), ordinals


def test_run_row_freezes_this_pilot_identity(snap: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_h1_grouped_dynamic as P

    run = snap["phases"]["open_run"]
    published = snap["phases"]["publish"]
    assert run["entry_id"] == P.PILOT_ENTRY_ID
    assert run["definition_bundle_sha256"] == published["definition_bundle_sha256"]
    assert (
        run["authority_model_definition_sha256"]
        == published["authority_model_definition_sha256"]
    )
    assert "editable" in run["editability"]
    assert "shared" in run["room_model"]
    assert run["finished_at"] is None, "open_run 不得预置 finished_at"
