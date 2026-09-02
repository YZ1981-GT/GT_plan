# -*- coding: utf-8 -*-
"""Task 41 真实 PostgreSQL 守卫：真实 866KB 载荷 + definitions/bundle 真发布 + 全场景 run。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 41
Requirements: 6.9, 6.11, 6.12, 12.1, 12.2, 12.10, 14.1, 14.11
Properties: **P27 / P29 / P49 / P60 / P69**

═══ 这一半证的是「真实载荷上真跑了 + 结果真的是推导出来的」 ═══

离线守卫证判据正确，但纯函数**可能是死代码**，而且合成数据上「不覆盖其他 item/section」
是空集恒真。本文件在真库上证明：

* :data:`D2_WP_ID` 这份**真实项目底稿**的 `checklist_responses` 里，
  `item_id='D2-detail-rows'` 一条 `remark` 就是 **906,239 字节 / 1260 行**的大 JSON，
  同一份底稿另有 **23** 条 D2-* item（合计 915,155 字节）；
* `build_store_projection` 把它拆成 **1260 × 39 = 49,140** 个 stable field；
* **Property 27**：一侧删第 8 行、另一侧改同一 `rowId` 的 `remark` ⇒ 恰 **1** 条
  `delete_update` 冲突，其余 **1259 行 × 39 = 49,101** 个字段**逐字段**与 base 相同，
  且另外 23 条 item 一个都不在契约声明里（「不覆盖其他 item/section」的非空判据）；
* **Property 60**：行/field 预算在真实 1260 行上做 N-1/N/N+1；
* `template → instrumentation → contract → bundle` 四段真发布成四行 definition + 一行
  non-null bundle，Task 39 的 harness 用**这个 bundle** plan 出 24 条 required scenario
  并逐条落库；
* 没有真实 OO/浏览器时 `aggregate_result` 必须是 `failed` 而不是 `passed`（Property 49）。

═══ 为什么真实载荷缺失时**失败**而不是 skip ═══

AC 14.9 允许「无法获得合法对象时标 UNVERIFIABLE」，但本任务正文要求的是「以真实约 866KB
载荷拆 stable field/row UUID」—— 用合成数据跑完再判绿就是 AC 14.9 明令禁止的「用 fixture
冒充」。因此载荷不在库里时本文件**直接失败**并指出需要哪份底稿，而不是静默降级。

═══ 隔离与采集 ═══

scratch schema `tmp_task41_pilot_<hex>` + 独立文件根，结束 `DROP SCHEMA CASCADE` + `rmtree`。
真实载荷只经 **admin engine 只读** `public.checklist_responses`，一个字节都不写。
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
import tracemalloc
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

_SCHEMA_PREFIX = "tmp_task41_pilot_"

#: 真实项目底稿：D2 应收账款（`wp_index.wp_code` 家族 D2），**只读**。
D2_WP_ID = "e2c95d10-181d-4549-8910-d5ab5bc5edd1"

#: 与离线守卫的字面量互锁（两侧任一漂移都打红）。
EXPECTED_PAYLOAD_BYTES = 906_239
EXPECTED_PAYLOAD_ROWS = 1_260
EXPECTED_D2_ITEM_COUNT = 24
EXPECTED_TOTAL_REMARK_BYTES = 915_155
EXPECTED_FIELDS_PER_ROW = 39
#: 被删/被改的那一行在载荷里的序位（**只用于选样本**，不参与任何身份构造）。
VICTIM_ORDINAL = 7

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

_MERGE_ROW = "dr-merge-fixture-0001"


def _merge_evidence(*, conflict: bool) -> Any:
    """用本 pilot 契约的真实 stable key 构造三方 projection。

    * `conflict=False` ⇒ P25：current 改 A（`customer_name`）、incoming 改 B（`remark`），
      两键不同 ⇒ 必须自动合并且 conflict_count=0。
    * `conflict=True`  ⇒ P26：三方在**同一键**（`customer_name`）上三个不同值。

    键不是编的：`contract.field_by_stable_key` 对未登记键抛，写错立刻炸。
    """
    from app.services.workpaper_sync import pilot_d2_large_json as P
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.pilot_harness import MergeEvidence

    contract = P.load_pilot_contract()
    key_a = P.stable_key_for("customer_name", _MERGE_ROW)
    key_b = P.stable_key_for("remark", _MERGE_ROW)
    spec_a = contract.field_by_stable_key(P.stable_key_for("customer_name"))
    spec_b = contract.field_by_stable_key(P.stable_key_for("remark"))

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
            base=projection({key_a: ("安徽省华嘉医药有限公司", spec_a)}),
            current=projection({key_a: ("安徽华嘉医药股份有限公司", spec_a)}),
            incoming=projection({key_a: ("华嘉医药（安徽）有限公司", spec_a)}),
            contract=contract,
            conflict_key=key_a,
        )
    return MergeEvidence(
        base=projection({key_a: ("安徽省华嘉医药有限公司", spec_a), key_b: ("", spec_b)}),
        current=projection(
            {key_a: ("安徽华嘉医药股份有限公司", spec_a), key_b: ("", spec_b)}
        ),
        incoming=projection(
            {key_a: ("安徽省华嘉医药有限公司", spec_a), key_b: ("已函证，回函相符", spec_b)}
        ),
        contract=contract,
        current_changed_key=key_a,
        incoming_changed_key=key_b,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 真实载荷阶段（只读 public.checklist_responses）
# ═══════════════════════════════════════════════════════════════════════════


async def _read_real_payload(engine: Any) -> dict[str, str]:
    import sqlalchemy as sa

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                sa.text(
                    "SELECT item_id, remark FROM public.checklist_responses "
                    "WHERE wp_id = :wp AND item_id LIKE 'D2-%' ORDER BY item_id"
                ),
                {"wp": D2_WP_ID},
            )
        ).all()
    return {str(item): (remark or "") for item, remark in rows}


def _real_payload_phases(items: dict[str, str]) -> dict[str, Any]:  # noqa: C901, PLR0915
    """在真实载荷上跑拆分 / Property 27 / 预算 / sidecar，返回可断言的快照。"""
    from app.services.workpaper_sync import excel_extract as X
    from app.services.workpaper_sync import pilot_d2_large_json as P
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.conflicts import ConflictKind
    from app.services.workpaper_sync.limits import (
        BudgetExceededError,
        SyncLimits,
        load_limits,
    )
    from app.services.workpaper_sync.merge import merge_projections

    contract = P.load_pilot_contract()
    if P.STORE_ITEM_ID not in items:
        raise _HarnessError(
            f"真实底稿 {D2_WP_ID} 的 checklist_responses 里没有 "
            f"item_id={P.STORE_ITEM_ID!r} —— 本任务正文要求「以真实约 866KB 载荷拆 stable "
            "field/row UUID」，用合成数据跑完判绿就是 AC 14.9 禁止的「用 fixture 冒充」。"
            f"实测该底稿现有 D2-* item：{sorted(items)}"
        )
    raw = items[P.STORE_ITEM_ID]
    blob = raw.encode("utf-8")

    snap: dict[str, Any] = {
        "item_count": len(items),
        "item_ids": sorted(items),
        "total_remark_bytes": sum(len(v.encode("utf-8")) for v in items.values()),
        "payload_bytes": len(blob),
        "payload_sha256": hashlib.sha256(blob).hexdigest(),
    }

    # ── 拆分（流式，tracemalloc 观测峰值）───────────────────────────────
    tracemalloc.start()
    try:
        identities = [identity for identity, _row in P.iter_store_rows(raw)]
        _, peak_iter = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    snap["row_count"] = len(identities)
    snap["distinct_row_count"] = len(set(identities))
    snap["iter_peak_bytes"] = peak_iter
    snap["row_identity_sample"] = identities[:3]

    base = P.build_store_projection(raw, contract=contract)
    base.assert_matches_contract(contract)
    snap["field_count"] = len(base.values)
    snap["projection_row_count"] = len(base.row_keys[P.ROWS_TABLE_KEY])
    snap["positional_keys"] = [key for key in base.values if "/0/" in key or "/1/" in key][:3]

    # ── Property 27：一侧删行、另一侧改同 rowId ─────────────────────────
    victim = identities[VICTIM_ORDINAL]
    others = [identity for identity in identities if identity != victim]
    changed_key = P.stable_key_for("remark", victim)

    def clone(*, drop_row: str | None = None, override: dict[str, Any] | None = None):
        values: dict[str, FieldValue] = {}
        for key, field in base.values.items():
            if drop_row is not None and field.row_key == drop_row:
                continue
            if override and key in override:
                values[key] = FieldValue(
                    stable_key=key,
                    value=override[key],
                    value_type=field.value_type,
                    mode=field.mode,
                    row_key=field.row_key,
                )
            else:
                values[key] = field
        keys = tuple(i for i in identities if i != drop_row) if drop_row else tuple(identities)
        return Projection(
            contract_id=base.contract_id,
            semantic_version=base.semantic_version,
            document_type=base.document_type,
            values=values,
            row_keys={P.ROWS_TABLE_KEY: keys},
        )

    current = clone(override={changed_key: "服务端在同一行改了备注"})
    incoming = clone(drop_row=victim)
    outcome = merge_projections(
        base=base, current=current, incoming=incoming, contract=contract
    )
    untouched_mismatch: list[str] = []
    compared = 0
    for identity in others:
        for column_key, *_rest in P.MANAGED_FIELD_SPECS:
            key = P.stable_key_for(column_key, identity)
            compared += 1
            merged = outcome.merged.get(key)
            if merged is None or merged.value != base.values[key].value:
                if len(untouched_mismatch) < 5:
                    untouched_mismatch.append(key)
    snap["p27"] = {
        "victim": victim,
        "changed_key": changed_key,
        "conflict_count": outcome.conflict_count,
        "conflict_kinds": sorted({record.kind.value for record in outcome.conflicts}),
        "conflict_keys": sorted(
            record.locator.stable_field_key for record in outcome.conflicts
        ),
        "conflict_rows": sorted(
            {record.locator.row_key or "" for record in outcome.conflicts}
        ),
        "delete_update_count": sum(
            1 for record in outcome.conflicts if record.kind is ConflictKind.delete_update
        ),
        "other_row_count": len(others),
        "compared_untouched_fields": compared,
        "untouched_mismatch": untouched_mismatch,
        "victim_lifecycles": sorted(
            {
                decision.lifecycle.value
                for decision in outcome.rows
                if decision.row_key == victim
            }
        ),
        "victim_held": all(
            decision.held for decision in outcome.rows if decision.row_key == victim
        ),
        "other_rows_held": sorted(
            {
                decision.row_key
                for decision in outcome.rows
                if decision.held and decision.row_key != victim
            }
        )[:5],
    }

    # ── 增行 / 重排：不得产生冲突（AC 6.9「不得把位置变化误判为整表覆盖」）──
    reordered = list(reversed(identities))
    reordered_projection = Projection(
        contract_id=base.contract_id,
        semantic_version=base.semantic_version,
        document_type=base.document_type,
        values=dict(base.values),
        row_keys={P.ROWS_TABLE_KEY: tuple(reordered)},
    )
    reorder_outcome = merge_projections(
        base=base, current=base, incoming=reordered_projection, contract=contract
    )
    snap["reorder"] = {
        "conflict_count": reorder_outcome.conflict_count,
        "first_row_changed": reordered[0] != identities[0],
    }

    added_row_id = "dr-oo-inserted-0001"
    added_values = dict(base.values)
    for column_key, *_rest in P.MANAGED_FIELD_SPECS:
        spec = contract.field_by_stable_key(P.stable_key_for(column_key))
        key = P.stable_key_for(column_key, added_row_id)
        added_values[key] = FieldValue(
            stable_key=key,
            value=None,
            value_type=spec.value_type,
            mode=spec.mode,
            row_key=added_row_id,
        )
    added_projection = Projection(
        contract_id=base.contract_id,
        semantic_version=base.semantic_version,
        document_type=base.document_type,
        values=added_values,
        row_keys={P.ROWS_TABLE_KEY: tuple(identities) + (added_row_id,)},
    )
    add_outcome = merge_projections(
        base=base, current=base, incoming=added_projection, contract=contract
    )
    snap["added"] = {
        "conflict_count": add_outcome.conflict_count,
        "new_row_present": any(
            key.startswith(f"{P.ROWS_TABLE_KEY}/{added_row_id}/")
            for key in add_outcome.merged.values
        ),
        "existing_rows_intact": all(
            add_outcome.merged.get(P.stable_key_for(column_key, identity)) is not None
            for identity in identities[:20]
            for column_key, *_rest in P.MANAGED_FIELD_SPECS
        ),
    }

    # ── 不覆盖其他 item ────────────────────────────────────────────────
    contract_blob = json.dumps(contract.canonical_payload, ensure_ascii=False)
    snap["other_items"] = {
        "count": len(items) - 1,
        "leaked_into_contract": sorted(
            item for item in items if item != P.STORE_ITEM_ID and item in contract_blob
        ),
        "merged_key_prefixes": sorted({key.split("/")[0] for key in outcome.merged.values}),
        "merged_row_keys_are_payload_rows": set(
            field.row_key for field in outcome.merged.values.values()
        )
        <= set(identities),
    }

    # ── Property 60：真实行数上的 N-1 / N / N+1 ────────────────────────
    def scaled(**over: Any) -> SyncLimits:
        limits = load_limits()
        fields = {
            name: getattr(limits, name)
            for name in limits.__dataclass_fields__
            if name != "ooxml"
        }
        fields.update(over)
        return SyncLimits(ooxml=limits.ooxml, **fields)

    row_budget: dict[str, Any] = {}
    for delta in (-1, 0, 1):
        limit = len(identities) + delta
        try:
            P.build_store_projection(raw, contract=contract, limits=scaled(max_table_rows=limit))
            row_budget[str(delta)] = {"accepted": True}
        except BudgetExceededError as exc:
            row_budget[str(delta)] = {
                "accepted": False,
                "budget": exc.budget,
                "observed": exc.observed,
                "limit": exc.limit,
            }
    field_budget: dict[str, Any] = {}
    total_fields = len(identities) * EXPECTED_FIELDS_PER_ROW
    for delta in (-1, 0, 1):
        limit = total_fields + delta
        try:
            P.build_store_projection(
                raw, contract=contract, limits=scaled(max_projection_fields=limit)
            )
            field_budget[str(delta)] = {"accepted": True}
        except BudgetExceededError as exc:
            field_budget[str(delta)] = {
                "accepted": False,
                "budget": exc.budget,
                "observed": exc.observed,
                "limit": exc.limit,
            }
    snap["budget"] = {
        "rows": row_budget,
        "fields": field_budget,
        "total_fields": total_fields,
        "max_table_rows": load_limits().max_table_rows,
        "max_projection_fields": load_limits().max_projection_fields,
    }

    # ── 分块 sidecar：真实 49,140 个字段流式落盘 ───────────────────────
    sidecar_dir = Path(tempfile.mkdtemp(prefix="tmp_task41_sidecar_"))
    try:
        stub_outcome = X.ExcelExtractOutcome(
            projection=base,
            anomalies=(),
            protected_findings=(),
            identity_inventory=None,  # type: ignore[arg-type]
            unmanaged=None,  # type: ignore[arg-type]
            stats=None,  # type: ignore[arg-type]
            region=X.ManagedRegion(
                table_key=P.ROWS_TABLE_KEY,
                table_name=P.TABLE_NAME,
                sheet_name=P.MANAGED_SHEET,
                sheet_part="xl/worksheets/sheet8.xml",
                table_ref=f"A{P.FIRST_DATA_ROW}:{P.UUID_COL}{P.LAST_DATA_ROW}",
                first_row=P.FIRST_DATA_ROW,
                last_row=P.LAST_DATA_ROW,
                first_column="A",
                last_column=P.MANAGED_LAST_COL,
                uuid_column=P.UUID_COL,
            ),
            scan=None,  # type: ignore[arg-type]
            formula_inventory={},
            sidecar_path=None,
        )
        tracemalloc.start()
        try:
            path = X.write_projection_sidecar(stub_outcome, sidecar_dir / "real.ndjson.gz")
            _, peak_sidecar = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        header, fields = X.read_projection_sidecar(path)
        second = X.write_projection_sidecar(stub_outcome, sidecar_dir / "real_b.ndjson.gz")
        snap["sidecar"] = {
            "bytes": path.stat().st_size,
            "is_gzip": path.read_bytes()[:2] == b"\x1f\x8b",
            "header": dict(header),
            "field_count": len(fields),
            "reproducible": path.read_bytes() == second.read_bytes(),
            "peak_bytes": peak_sidecar,
            "peak_budget": load_limits().peak_memory_budget_bytes,
            "rows_per_chunk": X.rows_per_chunk(load_limits()),
        }
    finally:
        shutil.rmtree(sidecar_dir, ignore_errors=True)

    # ── P25 / P26 在本契约上真跑一次（离线可判定，但必须真执行）─────────
    from app.services.workpaper_sync.pilot_harness import (
        evaluate_different_field_merge,
        evaluate_same_field_conflict,
    )

    snap["field_level"] = {
        "p25": evaluate_different_field_merge(_merge_evidence(conflict=False)).outcome.value,
        "p26": evaluate_same_field_conflict(_merge_evidence(conflict=True)).outcome.value,
    }
    return snap


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
    from app.services.workpaper_sync import pilot_d2_large_json as P
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
            "Task 41 的判据是「真实 866KB 载荷」与「pilot definitions/bundle 真的落进 V151 "
            f"的表」，必须真实 PostgreSQL；当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task41_store_"))
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
        # ── phase: 真实载荷（只读 public）─────────────────────────────────
        try:
            items = await _read_real_payload(admin)
            snap["phases"]["real_payload"] = _real_payload_phases(items)
        except Exception as exc:  # noqa: BLE001
            _phase_failed("real_payload", exc)

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
                sa.text("INSERT INTO projects (id, name) VALUES (:pid, 'task41')"),
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
                    source_commit="task41",
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
                    source_commit="task41-order",
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
            payload=json.dumps({"run": "task41"}, sort_keys=True).encode(),
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
            source_commit="task41-commit",
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
                            "operation_ids": [str(i) for i in (row.operation_ids or [])],
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
    return snap["phases"]["real_payload"]


# ═══════════════════════════════════════════════════════════════════════════
# 0. 采集自身
# ═══════════════════════════════════════════════════════════════════════════


def test_v151_applies_cleanly(snap: dict[str, Any]) -> None:
    assert snap["apply_errors"] == [], snap["apply_errors"]


def test_no_phase_crashed_during_collection(snap: dict[str, Any]) -> None:
    """采集阶段零异常 —— 否则下面每条断言都在看一个残缺快照。"""
    assert snap["harness_errors"] == {}, snap["harness_errors"]
    for name in (
        "real_payload",
        "publish",
        "publish_order",
        "bundle_row",
        "plan",
        "scenarios",
        "finalize",
    ):
        assert name in snap["phases"], name


# ═══════════════════════════════════════════════════════════════════════════
# 1. 真实 866KB 载荷（AC 6.12 / 14.11）
# ═══════════════════════════════════════════════════════════════════════════


def test_real_store_payload_is_the_frozen_866kb_shape(real: dict[str, Any]) -> None:
    """从库里重取一次，与离线守卫的字面量逐条互锁。"""
    from app.services.workpaper_sync import pilot_d2_large_json as P

    assert real["payload_bytes"] == EXPECTED_PAYLOAD_BYTES == 906_239
    assert real["row_count"] == EXPECTED_PAYLOAD_ROWS == 1_260
    assert real["item_count"] == EXPECTED_D2_ITEM_COUNT == 24
    assert real["total_remark_bytes"] == EXPECTED_TOTAL_REMARK_BYTES
    assert real["payload_bytes"] / 1024 == pytest.approx(885.0, abs=0.1)
    assert P.STORE_ITEM_ID in real["item_ids"]


def test_whole_json_is_split_into_one_field_per_column_per_row(real: dict[str, Any]) -> None:
    """1260 × 39 = 49,140 个 stable field，**不是** 1 个整 JSON 字段。"""
    assert real["field_count"] == EXPECTED_PAYLOAD_ROWS * EXPECTED_FIELDS_PER_ROW == 49_140
    assert real["projection_row_count"] == EXPECTED_PAYLOAD_ROWS


def test_row_identity_is_the_payload_row_id_not_an_index(real: dict[str, Any]) -> None:
    assert real["distinct_row_count"] == EXPECTED_PAYLOAD_ROWS, "1260 行零重复"
    assert all(str(sample).startswith("dr-") for sample in real["row_identity_sample"])
    assert real["positional_keys"] == [], real["positional_keys"]


def test_split_peak_memory_is_bounded(real: dict[str, Any]) -> None:
    """流式拆分的峰值必须落在内存预算内（`tracemalloc` 实测，不是「代码里写了 flush」）。"""
    assert 0 < real["iter_peak_bytes"] < real["sidecar"]["peak_budget"], real["iter_peak_bytes"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. Property 27：delete/update 冲突不整表覆盖
# ═══════════════════════════════════════════════════════════════════════════


def test_property27_only_the_touched_row_conflicts(real: dict[str, Any]) -> None:
    """一侧删行、另一侧改同 `rowId` ⇒ **恰 1** 条 `delete_update` 冲突。"""
    p27 = real["p27"]
    assert p27["conflict_count"] == 1, p27
    assert p27["conflict_kinds"] == ["delete_update"]
    assert p27["delete_update_count"] == 1
    assert p27["conflict_keys"] == [p27["changed_key"]]
    assert p27["conflict_rows"] == [p27["victim"]]
    assert p27["victim_lifecycles"] == ["delete_update_conflict"]
    assert p27["victim_held"] is True


def test_property27_every_other_row_merges_normally(real: dict[str, Any]) -> None:
    """其余 1259 行 × 39 = 49,101 个字段**逐字段**与 base 相同（不是「只查有没有冲突」）。"""
    p27 = real["p27"]
    assert p27["other_row_count"] == EXPECTED_PAYLOAD_ROWS - 1 == 1_259
    assert p27["compared_untouched_fields"] == 1_259 * EXPECTED_FIELDS_PER_ROW == 49_101
    assert p27["untouched_mismatch"] == [], p27["untouched_mismatch"]
    assert p27["other_rows_held"] == [], p27["other_rows_held"]


def test_reorder_and_insert_are_not_whole_table_overwrites(real: dict[str, Any]) -> None:
    """重排与新增按 row identity 合并，不产生冲突（AC 6.9 后半句）。"""
    assert real["reorder"]["first_row_changed"] is True
    assert real["reorder"]["conflict_count"] == 0
    assert real["added"]["conflict_count"] == 0
    assert real["added"]["new_row_present"] is True
    assert real["added"]["existing_rows_intact"] is True


def test_no_other_store_item_is_touched(real: dict[str, Any]) -> None:
    """「不覆盖其他 item/section」的**非空**判据：同一份底稿另有 23 条 item。"""
    other = real["other_items"]
    assert other["count"] == EXPECTED_D2_ITEM_COUNT - 1 == 23
    assert other["leaked_into_contract"] == [], other["leaked_into_contract"]
    assert other["merged_key_prefixes"] == ["receivable_detail_rows"]
    assert other["merged_row_keys_are_payload_rows"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 3. Property 60：真实行数上的 N-1 / N / N+1
# ═══════════════════════════════════════════════════════════════════════════


def test_row_budget_boundaries_on_the_real_payload(real: dict[str, Any]) -> None:
    rows = real["budget"]["rows"]
    assert rows["-1"]["accepted"] is False
    assert rows["-1"]["budget"] == "max_table_rows"
    assert rows["-1"]["observed"] == EXPECTED_PAYLOAD_ROWS
    assert rows["-1"]["limit"] == EXPECTED_PAYLOAD_ROWS - 1
    assert rows["0"]["accepted"] is True
    assert rows["1"]["accepted"] is True


def test_field_budget_boundaries_on_the_real_payload(real: dict[str, Any]) -> None:
    fields = real["budget"]["fields"]
    assert real["budget"]["total_fields"] == 49_140
    assert fields["-1"]["accepted"] is False
    assert fields["-1"]["budget"] == "max_projection_fields"
    assert fields["-1"]["observed"] == 49_140
    assert fields["0"]["accepted"] is True
    assert fields["1"]["accepted"] is True


def test_real_payload_is_well_inside_the_production_budget(real: dict[str, Any]) -> None:
    """生产预算是单一真源，真实载荷远在界内（越界拒绝由上面两条覆盖）。"""
    assert real["budget"]["max_table_rows"] == 100_000
    assert real["budget"]["max_projection_fields"] == 200_000
    assert EXPECTED_PAYLOAD_ROWS < real["budget"]["max_table_rows"]
    assert real["budget"]["total_fields"] < real["budget"]["max_projection_fields"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. 分块 sidecar：真实 49,140 个字段流式落盘
# ═══════════════════════════════════════════════════════════════════════════


def test_sidecar_streams_the_real_projection(real: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_d2_large_json as P

    sidecar = real["sidecar"]
    assert sidecar["is_gzip"] is True
    assert sidecar["field_count"] == 49_140
    assert sidecar["header"]["contract_id"] == P.PILOT_ADAPTER_ID
    assert sidecar["header"]["table_key"] == P.ROWS_TABLE_KEY
    assert sidecar["header"]["schema_version"] == "excel-projection-sidecar:v1"
    assert sidecar["reproducible"] is True, "两次导出必须逐字节相同（mtime=0）"


def test_sidecar_never_holds_the_whole_projection_in_one_buffer(real: dict[str, Any]) -> None:
    sidecar = real["sidecar"]
    assert 0 < sidecar["peak_bytes"] < sidecar["peak_budget"], sidecar
    # gzip 之后的体积必须显著小于原始 906KB 载荷（证明真的压缩流式写出）。
    assert sidecar["bytes"] < EXPECTED_PAYLOAD_BYTES


def test_chunk_size_is_derived_from_limits_not_hardcoded(real: dict[str, Any]) -> None:
    assert real["sidecar"]["rows_per_chunk"] == 64


# ═══════════════════════════════════════════════════════════════════════════
# 5. definitions / bundle 真发布
# ═══════════════════════════════════════════════════════════════════════════


def test_four_definitions_and_one_bundle_are_published(snap: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_d2_large_json as P
    from app.services.workpaper_sync.definitions import canonical_digest

    published = snap["phases"]["publish"]
    assert published["entry_id"] == P.PILOT_ENTRY_ID
    assert published["adapter_id"] == P.PILOT_ADAPTER_ID
    assert published["authority_model"] == "projection_contract"
    assert published["template_definition_sha256"] == canonical_digest(
        P.template_definition_payload()
    )
    assert published["instrumentation_definition_sha256"] == canonical_digest(
        P.instrumentation_definition_payload()
    )
    assert published["contract_definition_sha256"] == P.load_pilot_contract().canonical_sha256
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
        assert uuid.UUID(published[key])


def test_bundle_is_non_null_and_all_children_are_approved(snap: dict[str, Any]) -> None:
    """`projection_contract` ⇒ 三个 typed slot 必须都是 approved `definition`。"""
    row = snap["phases"]["bundle_row"]
    assert row["state"].endswith("approved"), row["state"]
    for slot, (slot_type, digest) in sorted(row["slots"].items()):
        assert slot_type.endswith("definition"), (slot, slot_type)
        assert len(digest) == 64 and set(digest) != {"0"}, (slot, digest)
    kinds = {child["kind"].rsplit(".", 1)[-1] for child in row["children"]}
    assert {"template", "instrumentation", "contract", "authority_model"} <= kinds, kinds
    for child in row["children"]:
        assert child["state"].endswith("approved"), child


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
# 6. run / evidence（Property 69）
# ═══════════════════════════════════════════════════════════════════════════


def test_plan_uses_this_pilot_bundle_and_derives_a_non_empty_set(
    snap: dict[str, Any]
) -> None:
    plan = snap["phases"]["plan"]
    assert plan["scenario_count"] == 24, plan["scenario_ids"]
    assert plan["authority_model"] == "projection_contract"
    assert plan["capability"].endswith("bidirectional") or plan["capability"], plan
    assert plan["close_required"] is True
    assert plan["substituted"] is False
    assert plan["bundle_digest"] == snap["phases"]["publish"]["definition_bundle_sha256"]
    assert snap["phases"]["open_run"]["derived_digest_matches"] is True


def test_required_digest_is_not_the_checklist_pilots(snap: dict[str, Any]) -> None:
    """evidence 按**本** bundle digest 记录（禁用 checklist pilot 的 digest 冒充）。"""
    from app.services.workpaper_sync import pilot_simple_checklist as CHECKLIST
    from app.services.workpaper_sync.entry_profile import (
        load_entry_manifest,
        manifest_entries_by_id,
    )
    from app.services.workpaper_sync.evidence import derive_for_manifest_entry

    entries = manifest_entries_by_id(load_entry_manifest())
    theirs = derive_for_manifest_entry(
        entries[CHECKLIST.PILOT_ENTRY_ID], authority_model=CHECKLIST.AUTHORITY_MODEL
    )
    assert snap["phases"]["plan"]["required_digest"] != theirs.digest


def test_every_required_scenario_has_a_persisted_row(snap: dict[str, Any]) -> None:
    """分母 == 分子：required set 的每一条都必须有一行 evidence（不许少跑）。"""
    required = set(snap["phases"]["plan"]["scenario_ids"])
    persisted = set(snap["phases"]["persisted_rows"])
    assert required == persisted, sorted(required ^ persisted)
    assert len(persisted) == 24


def test_no_entity_is_reused_across_scenarios(snap: dict[str, Any]) -> None:
    counts = snap["phases"]["entity_reuse"]
    assert counts["total"] > 0
    assert counts["total"] == counts["distinct"], counts


def test_reused_entity_is_refused_at_write_time(snap: dict[str, Any]) -> None:
    """反向自检：故意复用同一 operation/application ⇒ 第二条必须被拒。"""
    outcome = snap["phases"]["entity_reuse_refused"]
    assert len(outcome["pair"]) == 2, outcome
    assert outcome["outcome"][0]["rejected"] is False
    assert outcome["outcome"][1]["rejected"] is True, outcome
    assert outcome["outcome"][1]["kind"], outcome


def test_property25_and_26_really_ran_on_this_contract(
    snap: dict[str, Any], real: dict[str, Any]
) -> None:
    """字段级两条 oracle 用**本契约自己的** stable key 真跑一次三方 merge。"""
    assert real["field_level"]["p25"] == "passed"
    assert real["field_level"]["p26"] == "passed"
    for scenario_id in ("different_field_merge", "same_field_conflict_resolve"):
        row = snap["phases"]["scenarios"][scenario_id]
        assert row["result"] == "passed", row
        assert row["notes"], row


def test_black_box_scenarios_are_unverifiable(snap: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_harness as PH

    black_box = set(snap["phases"]["plan"]["black_box"])
    assert black_box, "黑盒场景集合为空 ⇒ 判据空转"
    for scenario_id in sorted(black_box):
        row = snap["phases"]["scenarios"][scenario_id]
        assert row["result"] == "unverifiable", (scenario_id, row)
        assert PH.SCENARIO_ORACLES[scenario_id].needs_black_box


def test_upstream_gap_scenarios_are_failed_not_unverifiable(snap: dict[str, Any]) -> None:
    """Task 32 的两条上游缺口 ⇒ `failed`（缺的是实现不是环境；顺序不可交换）。"""
    debts = set(snap["phases"]["plan"]["upstream_debt"])
    assert debts == {
        "same_application_higher_sequence_fold",
        "wrong_prior_confirmation_bundle_fence_contributor_rejected",
    }, sorted(debts)
    for scenario_id in sorted(debts):
        row = snap["phases"]["scenarios"][scenario_id]
        assert row["result"] == "failed", (scenario_id, row)
        assert row["error_code"], row


def test_run_is_not_verified_without_real_onlyoffice(snap: dict[str, Any]) -> None:
    """Property 49 的后半句：probe/pilot 未实际通过时不得计为通过。"""
    finalize = snap["phases"]["finalize"]
    assert finalize["finished_at_set"] is True
    assert finalize["aggregate_result"].endswith("failed"), finalize["aggregate_result"]
    assert not finalize["aggregate_result"].endswith("passed")


def test_result_is_never_supplied_by_the_caller() -> None:
    """`ScenarioObservation` 没有 `result` 字段、`finalize_run` 没有 `aggregate_result`。"""
    import inspect

    from app.services.workpaper_sync import pilot_harness as PH

    assert "result" not in PH.ScenarioObservation.__dataclass_fields__
    record_params = set(
        inspect.signature(PH.SyncTestRunHarness.record_scenario).parameters
    )
    assert "result" not in record_params, record_params
    finalize_params = set(
        inspect.signature(PH.SyncTestRunHarness.finalize_run).parameters
    )
    assert "aggregate_result" not in finalize_params, finalize_params
    assert "verified_at" not in finalize_params, finalize_params


def test_pilot_class_stays_unverifiable_after_this_run(snap: dict[str, Any]) -> None:
    """本 run 结束后 d2_large_json 类仍必须是 UNVERIFIABLE（没有真实 OO）。"""
    from app.services.workpaper_sync import pilot_harness as PH

    assert snap["phases"]["finalize"]["aggregate_result"].endswith("failed")
    assessment = PH.assess_pilot_classes()[PH.PilotClass.d2_large_json]
    assert assessment.status is PH.PilotClassStatus.unverifiable
    assert assessment.verified_entry_ids == ()


def test_download_only_scenario_has_zero_operation_and_application(
    snap: dict[str, Any]
) -> None:
    row = snap["phases"]["scenarios"]["download_only_zero_three_entities"]
    assert row["operation_ids"] == []
    assert row["application_ids"] == []


def test_every_scenario_row_binds_a_published_trace_bundle(snap: dict[str, Any]) -> None:
    for scenario_id, row in sorted(snap["phases"]["scenarios"].items()):
        assert len(row["trace_sha256"]) == 64, (scenario_id, row["trace_sha256"])


def test_ordinals_are_dense_and_unique(snap: dict[str, Any]) -> None:
    ordinals = sorted(row["ordinal"] for row in snap["phases"]["scenarios"].values())
    assert ordinals == list(range(1, len(ordinals) + 1)), ordinals


def test_run_row_freezes_this_pilot_identity(snap: dict[str, Any]) -> None:
    from app.services.workpaper_sync import pilot_d2_large_json as P

    run = snap["phases"]["open_run"]
    assert run["entry_id"] == P.PILOT_ENTRY_ID
    assert run["definition_bundle_sha256"] == snap["phases"]["publish"][
        "definition_bundle_sha256"
    ]
    assert run["authority_model_definition_sha256"] == snap["phases"]["publish"][
        "authority_model_definition_sha256"
    ]
    assert run["editability"].endswith("editable")
    assert run["room_model"].endswith("shared")


# ═══════════════════════════════════════════════════════════════════════════
# 7. 权威模板与真实底稿都没被本文件改动
# ═══════════════════════════════════════════════════════════════════════════


def test_authority_template_is_untouched() -> None:
    from app.services.workpaper_sync import pilot_d2_large_json as P

    assert (
        hashlib.sha256(P.authoritative_template_path().read_bytes()).hexdigest()
        == P.TEMPLATE_SHA256
    )


def test_real_workpaper_payload_is_untouched(real: dict[str, Any]) -> None:
    """真实底稿只读：跑完 sha256 必须还是采集时那一个。"""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    async def _reread() -> str:
        ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
        engine = create_async_engine(
            settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
        )
        try:
            items = await _read_real_payload(engine)
        finally:
            await engine.dispose()
        from app.services.workpaper_sync import pilot_d2_large_json as P

        return hashlib.sha256(items[P.STORE_ITEM_ID].encode("utf-8")).hexdigest()

    assert asyncio.run(_reread()) == real["payload_sha256"]
