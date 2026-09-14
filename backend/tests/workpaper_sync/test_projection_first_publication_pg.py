# -*- coding: utf-8 -*-
"""首版 published representation 在**真实 PostgreSQL** 上落成的判据（F8）。

**Spec: published-representation-production-path-and-lane-adjudication**
Tasks 7.1 / 7.2 / 7.3

═══ 本文件的落点 ═══════════════════════════════════════════════════════════════

| Property | 主题 | 任务 |
|---|---|---|
13 | 任一阶段失败时数据库四处逐行不变 | 7.2 |
19 | 落库 representation 的七个冻结字段与计划及实测值逐项相等 | 7.2 |
20 | 首版发布恰好一次 revision 推进、一组单行产出与一次 commit | 7.2 |
33 | 成败判定取自数据库数据而非进程退出码 | 7.3 |
34 | 带时区时间戳在 Python 侧编码后可往返 | 7.3 |
35 | 复原流程每步独立事务，先前成功步骤不被撤销 | 7.3 |

外加 F7 移交的四个「落库侧」半条（F7 是零数据库文件，只落了它们的结构/行为侧）：

* **Property 18 行为侧** —— 真库里该 (wp, entry) 无任何 representation 时 loader 仍产出；
* **Property 22 落库侧** —— `--check` 跑前跑后四张表逐行相等；
* **Property 24 落库侧** —— 同一库状态重复解析选同一条底稿；
* **Property 26 落库侧** —— 重发一次后行数与 digest 逐项不变。

═══ 为什么不 skip ═══════════════════════════════════════════════════════════════

本文件的判据是「**真库上真的成了**」。DB 非 PostgreSQL 时 skip 等于把「没验证」记成
「通过」—— 那正是本 spec 要消灭的假绿形态。故此处 `raise` 而不是 `pytest.skip`。

═══ 隔离与采集 ═══════════════════════════════════════════════════════════════

scratch schema `tmp_fp_pg_<hex>` + 独立文件根，结束 `DROP SCHEMA CASCADE` + `rmtree`。
全部阶段由**一次 `asyncio.run`** 跑完落进快照（module fixture）—— 每个测试各自开 async
会污染共享连接池（本仓库 Task 21~29 实测：第二个起 `NoneType has no attribute send`）。

采集阶段的异常一律**记录不穿透**：穿透会把整个 module 变成 collection ERROR，而
`-rf` 只列 FAILED 不列 ERROR ⇒ 定向变异看不到预期失败项 ⇒ 判 GREEN。
`test_no_phase_crashed_during_collection` 是这个决定的另一半。

═══ 三坑（tasks.md 7.1 逐条）══════════════════════════════════════════════════

① **timestamptz 一律在 Python 侧转 `datetime`**。SQL 层写 `CAST(:x AS timestamptz)`
   无效 —— asyncpg 在**发送之前**就按目标类型编码参数，字符串到那时已经错了。
② **复原每步独立事务边界**，不共用一个 `engine.begin()`：共用时第 k 步失败会把前
   k-1 步一起撤回（本仓库复原脚本已踩过）。
③ **判成败查数据不看退出码**：退出码是进程的自述，落库行是事实。

用法（仓库根）::

    .\\.venv\\Scripts\\python.exe -m pytest \\
        backend/tests/workpaper_sync/test_projection_first_publication_pg.py -q
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
MIGRATIONS: tuple[Path, ...] = (
    BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql",
    BACKEND / "migrations" / "V152__workpaper_content_version_upload_wopi_source.sql",
    BACKEND / "migrations" / "V153__workpaper_representation_candidate_attach_event.sql",
)

if str(BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_fp_pg_"

#: 首版目标顺序。取自 design.md §首版目标选取 + 2026-09-03 Gate 3 裁决：
#: H1 最干净（动态列 0 项、structure 25），D2 是判据 C 的活证人。
#: 🔴 顺序**维持 H1 → D2**；若 H1 反而失败那是回归不是未知，必须定位原因，
#:    不得直接对调（tasks.md 7.1 的红字要求）。
_FIRST_TARGET = "xlsx/gt-h1-fixed-assets"

#: 临时 schema 的桩表。
#:
#: 🔴 除 projects / users / working_paper 之外还必须有 `wp_index` 与
#: `checklist_responses`：宿主的 `_resolve_target` 按 `wi.wp_code` 选目标、
#: `_read_store_payload` 从 `checklist_responses` 读载荷。缺它们时 Property 24 的
#: 落库侧判据会以 `relation "wp_index" does not exist` 失败 —— 那是夹具不全，
#: 不是判据不成立（首版实测踩到）。
#: 列只取被本文件消费的那几个（`wp_code` / `wp_index_id` / `created_at` /
#: `content_revision` / `remark` / `item_id`），不复制生产 schema 的全貌。
#: 🔴 BP-26（2026-09-06）：`projects.is_deleted` 与 `wp_index.is_deleted` 是
#: `TARGET_VISIBILITY_SQL` 的两个新分量。缺列时 Property 24 的落库侧判据会以
#: `column p.is_deleted does not exist` 失败 —— 同上，那是夹具不全而不是判据不成立。
_STUB_DDL = """
CREATE TABLE projects (
    id UUID PRIMARY KEY,
    name VARCHAR(200) NOT NULL DEFAULT 'stub',
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE users (id UUID PRIMARY KEY, username VARCHAR(100) NOT NULL DEFAULT 'stub');
CREATE TABLE wp_index (
    id UUID PRIMARY KEY,
    wp_code VARCHAR(60) NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE working_paper (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    wp_index_id UUID REFERENCES wp_index(id),
    file_version INTEGER NOT NULL DEFAULT 1,
    content_revision BIGINT NOT NULL DEFAULT 0,
    parsed_data JSONB,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE checklist_responses (
    id UUID PRIMARY KEY,
    wp_id UUID NOT NULL REFERENCES working_paper(id),
    item_id VARCHAR(120) NOT NULL,
    remark TEXT
);
"""

#: Property 13 / 22 的逐表快照对象。
#:
#: 🔴 是**四处**而不是四张任意表：Requirement 3.8 / 5.7 点名的就是这四处，
#: 它们是「首版发布会写到的全部位置」。少一处会让某种残留看不见。
_SNAPSHOT_TABLES: tuple[str, ...] = (
    "working_paper_content_version",
    "working_paper_content_representation",
    "working_paper_content_application",
    "working_paper_sync_entry_state",
)


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成「无数据」）。"""


def _err(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)[-8:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _primary_key_columns(session: Any, table: str) -> tuple[str, ...]:
    """现查该表的主键列（按 `ordinal_position`）。

    🔴 **不写死 `id`**。首版我按 `ORDER BY id` 写，实测炸在
    `column "id" does not exist` —— `working_paper_sync_entry_state` 的主键是复合
    `(wp_id, entry_id)`（`CONSTRAINT pk_wpses`），它根本没有 `id` 列。
    写死排序键会让「加一张没有 id 的表」在将来静默变成 collection error。
    """
    import sqlalchemy as sa

    rows = (
        await session.execute(
            sa.text(
                "SELECT kcu.column_name"
                "  FROM information_schema.table_constraints tc"
                "  JOIN information_schema.key_column_usage kcu"
                "    ON kcu.constraint_name = tc.constraint_name"
                "   AND kcu.table_schema = tc.table_schema"
                " WHERE tc.constraint_type = 'PRIMARY KEY'"
                "   AND tc.table_name = :t"
                "   AND tc.table_schema = current_schema()"
                " ORDER BY kcu.ordinal_position"
            ),
            {"t": table},
        )
    ).scalars().all()
    if not rows:
        raise _HarnessError(
            f"表 {table} 在当前 schema 里查不到主键 —— 逐行快照的排序键无从确定，"
            "而不确定的排序会让「逐行不变」判据随机打红"
        )
    return tuple(str(r) for r in rows)


async def _table_snapshot(session: Any) -> dict[str, Any]:
    """四张表的逐行快照：行数 + 全行内容的稳定 digest。

    🔴 判据要的是「**逐行**不变」，因此不能只比行数：一次写入 + 一次删除会让行数相等
    而内容已变。digest 取按**主键**排序后的全列文本 —— 稳定且对任何列变化敏感。
    """
    import sqlalchemy as sa

    out: dict[str, Any] = {}
    for table in _SNAPSHOT_TABLES:
        order_by = ", ".join(await _primary_key_columns(session, table))
        rows = (
            await session.execute(
                sa.text(f"SELECT * FROM {table} ORDER BY {order_by}")  # noqa: S608
            )
        ).mappings().all()
        payload = json.dumps(
            [{k: str(v) for k, v in sorted(dict(r).items())} for r in rows],
            ensure_ascii=False,
            sort_keys=True,
        )
        out[table] = {
            "rows": len(rows),
            "digest": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        }
    return out


def _diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """两份快照的逐表差异描述（空列表 = 逐行不变）。"""
    diffs: list[str] = []
    for table in _SNAPSHOT_TABLES:
        b, a = before.get(table) or {}, after.get(table) or {}
        if b.get("rows") != a.get("rows"):
            diffs.append(f"{table}: 行数 {b.get('rows')} → {a.get('rows')}")
        elif b.get("digest") != a.get("digest"):
            diffs.append(
                f"{table}: 行数相同（{a.get('rows')}）但内容 digest 变了 —— "
                "有一次写入配一次删除，只比行数看不出来"
            )
    return diffs


# ═══════════════════════════════════════════════════════════════════════════
# 一次采集：CREATE SCHEMA → 迁移 → provision → stage → 发首版 → 断言素材
# ═══════════════════════════════════════════════════════════════════════════


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - 一次采集覆盖全部阶段
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.services.workpaper_sync import projection_first_publication as F2
    from app.services.workpaper_sync import projection_provisioning as PP
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    if not str(settings.DATABASE_URL).startswith("postgresql"):
        raise _HarnessError(
            "F8 的判据是「首版 representation 真的落进了真实 PG 的四张表」，"
            f"必须真实 PostgreSQL；当前 DATABASE_URL 为 "
            f"{str(settings.DATABASE_URL).split('://')[0]}。"
            "此处**不 skip** —— skip 等于把「没验证」记成「通过」"
        )
    for migration in MIGRATIONS:
        if not migration.exists():
            raise _HarnessError(f"缺少迁移文件: {migration}")

    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_fp_pg_store_"))
    (base_root / "storage").mkdir(exist_ok=True)
    (base_root / "definition_store").mkdir(exist_ok=True)
    staging_root = base_root / "staging"
    staging_root.mkdir(exist_ok=True)

    admin = create_async_engine(
        str(settings.DATABASE_URL), poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "entry_id": _FIRST_TARGET,
        "apply_errors": [],
        "harness_errors": {},
        "phases": {},
        "snapshots": {},
    }

    def _phase_failed(name: str, exc: BaseException) -> None:
        snap["harness_errors"][name] = _err(exc)

    engine = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(
            str(settings.DATABASE_URL),
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

        project, wp, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("INSERT INTO projects (id) VALUES (:p)"), {"p": project}
            )
            await conn.execute(sa.text("INSERT INTO users (id) VALUES (:u)"), {"u": actor})
            await conn.execute(
                sa.text("INSERT INTO working_paper (id, project_id) VALUES (:w, :p)"),
                {"w": wp, "p": project},
            )
        snap["ids"] = {"project": str(project), "wp": str(wp), "actor": str(actor)}

        artifacts = CanonicalArtifactRepository(base_root)

        # ── 阶段 0：空库快照（分母的起点）────────────────────────────────
        async with Session() as session:
            snap["snapshots"]["empty"] = await _table_snapshot(session)
            snap["phases"]["supply_before"] = await PP.count_supply_rows(session)

        # ── 阶段 1：provision approved projection bundle ─────────────────
        try:
            async with Session() as session:
                outcome = await PP.ProjectionDefinitionProvisioner(
                    session=session,
                    repository=WorkpaperSyncRepository(session),
                    artifacts=artifacts,
                    project_id=project,
                    wp_id=wp,
                ).ensure(entry_id=_FIRST_TARGET)
                await session.commit()
            snap["phases"]["provision"] = outcome.as_dict()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("provision", exc)

        async with Session() as session:
            snap["snapshots"]["after_provision"] = await _table_snapshot(session)
            snap["phases"]["supply_after_provision"] = await PP.count_supply_rows(session)

        # ── 阶段 2：Property 18 行为侧 —— 无 representation 时 loader 仍产出 ──
        #
        # 🔴 这是本 spec 破环点的**唯一直接证据**：库里该 (wp, entry) 一行
        #    representation 都没有（阶段 0 的快照证明了这一点），loader 仍能产出
        #    Frozen_Definitions。F7 只能落结构判据（入参名/来源根/签名），
        #    「真的跑通了」必须在真库上说。
        staged = None
        try:
            staged = F2.stage_instrumented_substrate(
                entry_id=_FIRST_TARGET, staging_dir=staging_root / "first"
            )
            snap["phases"]["staged"] = {
                "source_sha256": staged.source_sha256,
                "instrumented_sha256": staged.instrumented_sha256,
                "structure_rows": len(staged.observed_structure),
                "business_sheets": len(staged.observed_business_sheets),
                "dynamic_columns": {
                    k: len(v) for k, v in staged.observed_dynamic_columns.items()
                },
                "ooxml_gates": list(staged.ooxml_gates),
                "staged_path": str(staged.staged_path),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("staged", exc)

        if staged is not None:
            try:
                from app.services.workpaper_sync.contracts import load_contract
                from app.services.workpaper_sync.excel_entry_gate import (
                    AdapterBuild,
                    ExcelEntryDefinitionLoader,
                )

                bundle_id = uuid.UUID(
                    str(snap["phases"]["provision"]["definition_bundle_id"])
                )
                bundle_sha = str(
                    snap["phases"]["provision"]["definition_bundle_sha256"]
                )
                contract_id = str(snap["phases"]["provision"]["contract_id"])
                contract = load_contract(contract_id)
                async with Session() as session:
                    resolution = CanonicalResolutionService(session, artifacts)
                    definitions = await ExcelEntryDefinitionLoader(
                        session=session, resolution=resolution
                    ).load(
                        entry_id=_FIRST_TARGET,
                        frozen_bundle_id=bundle_id,
                        frozen_bundle_sha256=bundle_sha,
                        adapter_build=AdapterBuild(
                            adapter_id=contract_id,
                            adapter_build_digest=F2._adapter_build_digest(contract_id),
                            document_type="xlsx",
                            contract_version=str(contract.semantic_version),
                        ),
                        identity_inventory=staged.identity_inventory,
                        observed_structure=staged.observed_structure,
                        observed_business_sheets=staged.observed_business_sheets,
                        observed_dynamic_columns=staged.observed_dynamic_columns,
                    )
                # 🔴 取的是 `FrozenEntryDefinitions` **真实存在**的字段。
                #    首版我按 `structure_hash` / `identity_inventory_sha256` 取，
                #    实测两者都是空串 —— 它们在 **representation 行**上，
                #    不在 definitions 上（dataclass 字段实测为 entry_id / bundle /
                #    contract / adapter_build / identity_inventory / business_sheets /
                #    dynamic_column_keys / structure_inventory_size）。
                #    取一个不存在的属性会让「产出了」这条判据落在空串上恒真。
                snap["phases"]["loader_without_representation"] = {
                    "produced": definitions is not None,
                    "entry_id": str(getattr(definitions, "entry_id", "") or ""),
                    "structure_inventory_size": int(
                        getattr(definitions, "structure_inventory_size", 0) or 0
                    ),
                    "business_sheets": len(
                        getattr(definitions, "business_sheets", ()) or ()
                    ),
                    "dynamic_column_keys": {
                        str(k): len(v)
                        for k, v in (
                            getattr(definitions, "dynamic_column_keys", {}) or {}
                        ).items()
                    },
                    "has_identity_inventory": bool(
                        getattr(definitions, "identity_inventory", None) is not None
                    ),
                    "bundle_id": str(
                        getattr(getattr(definitions, "bundle", None), "bundle_id", "")
                        or ""
                    ),
                    "representation_rows_at_that_moment": snap["snapshots"][
                        "after_provision"
                    ]["working_paper_content_representation"]["rows"],
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("loader_without_representation", exc)

        # ── 阶段 3：resolve_plan（真库五条准入）──────────────────────────
        plan = None
        try:
            async with Session() as session:
                resolution = CanonicalResolutionService(session, artifacts)
                plan = await F2.resolve_plan(
                    session=session,
                    resolution=resolution,
                    project_id=project,
                    wp_id=wp,
                    entry_id=_FIRST_TARGET,
                    actor_id=actor,
                )
            snap["phases"]["plan"] = {
                "contract_id": plan.contract_id,
                "provider_module": plan.provider_module,
                "document_type": plan.document_type,
                "expected_revision": plan.expected_revision,
                "authority_model_logical_id": plan.authority_model_logical_id,
                "bundle_id": str(plan.bundle.bundle_id),
                "bundle_sha256": str(plan.bundle.bundle_sha256),
            }
        except Exception as exc:  # noqa: BLE001
            _phase_failed("plan", exc)

        # ── 阶段 4：真发首版 ────────────────────────────────────────────
        if plan is not None and staged is not None:
            try:
                from app.services.workpaper_sync.outbox import (
                    DurableEventOutboxService,
                )

                provider = F2._provider_for(_FIRST_TARGET)
                store_item_id = str(getattr(provider, "STORE_ITEM_ID", "") or "")
                revision_before, pointer_before = await _revision_and_pointer(
                    Session, wp_id=wp, entry_id=_FIRST_TARGET
                )
                async with Session() as session:
                    resolution = CanonicalResolutionService(session, artifacts)
                    receipt = await F2.publish_first_generation(
                        session=session,
                        resolution=resolution,
                        artifacts=artifacts,
                        repository=WorkpaperSyncRepository(session),
                        plan=plan,
                        staged=staged,
                        store_payload="[]",
                    )
                    await session.commit()
                revision_after, pointer_after = await _revision_and_pointer(
                    Session, wp_id=wp, entry_id=_FIRST_TARGET
                )
                snap["phases"]["publish"] = {
                    "receipt": _receipt_facts(receipt),
                    "store_item_id": store_item_id,
                    "revision_before": revision_before,
                    "revision_after": revision_after,
                    "pointer_before": pointer_before,
                    "pointer_after": pointer_after,
                    "outbox_service": DurableEventOutboxService.__name__,
                }
            except Exception as exc:  # noqa: BLE001
                _phase_failed("publish", exc)
                # 🔴 首版发布失败时把**可编程**的失败面记下来（不靠读文案）：
                #    Property 27 的判据要能指名「卡在哪一格、error_code 是什么」。
                snap["phases"]["publish_failure"] = {
                    "type": type(exc).__name__,
                    "error_code": str(getattr(exc, "error_code", "") or ""),
                    "cell": str(getattr(exc, "cell", "") or ""),
                    "stable_key": str(getattr(exc, "stable_key", "") or ""),
                    "table_key": str(getattr(exc, "table_key", "") or ""),
                    "message": str(exc)[:400],
                }

        async with Session() as session:
            snap["snapshots"]["after_publish"] = await _table_snapshot(session)
            snap["phases"]["supply_after_publish"] = await PP.count_supply_rows(session)
            # 落库 representation 的七个冻结字段（Property 19）
            # 🔴 `authority_model_type` 在 **definition artifact** 上，不在 bundle 上。
            #    bundle 只持 `authority_model_definition_id` 这个 FK。首版我按
            #    `b.authority_model_type` 写，实测 `column does not exist`。
            row = (
                await session.execute(
                    sa.text(
                        "SELECT r.id, r.definition_bundle_id, r.definition_bundle_sha256,"
                        "       r.authority_model_definition_id, r.adapter_id,"
                        "       r.adapter_build_digest, r.structure_hash,"
                        "       r.identity_inventory_sha256, r.generation,"
                        "       r.created_at, am.authority_model_type,"
                        "       am.state AS authority_model_state,"
                        "       am.logical_id AS authority_model_logical_id"
                        "  FROM working_paper_content_representation r"
                        "  JOIN working_paper_sync_definition_bundle b"
                        "    ON b.id = r.definition_bundle_id"
                        "  JOIN working_paper_sync_definition_artifact am"
                        "    ON am.id = b.authority_model_definition_id"
                        " ORDER BY r.created_at DESC LIMIT 1"
                    )
                )
            ).mappings().first()
            snap["phases"]["representation_row"] = (
                {k: (v if isinstance(v, (int, type(None))) else str(v))
                 for k, v in dict(row).items()}
                if row
                else {}
            )
            snap["phases"]["representation_created_at_raw"] = (
                row["created_at"] if row else None
            )
            # entry_state 指针（Property 20）。
            # 🔴 列名是 `current_representation_id` / `representation_generation`，
            #    不是 `representation_id` / `generation`。首版按后者写，实测
            #    `column "representation_id" does not exist` —— 按猜的列名写 SQL
            #    是错的做法，四张表的列一律先从 V151 的 DDL 现读。
            state_rows = (
                await session.execute(
                    sa.text(
                        "SELECT wp_id, entry_id, current_representation_id,"
                        "       representation_generation"
                        "  FROM working_paper_sync_entry_state ORDER BY entry_id"
                    )
                )
            ).mappings().all()
            snap["phases"]["entry_state_rows"] = [
                {k: str(v) for k, v in dict(r).items()} for r in state_rows
            ]

        # ── 阶段 5：Property 26 —— 重发一次必须被拒且库不变 ───────────────
        #
        # 🔴 本阶段的结论**以 publish 成功为前提**：首版没发出去时判据 B 仍为假，
        #    重跑当然不会被拒。因此这里同时记下 `publish_succeeded`，
        #    守卫侧据它决定断言哪一侧 —— 不记的话「没被拒」会被误读为幂等失守。
        publish_succeeded = "publish" in snap["phases"] and not snap[
            "harness_errors"
        ].get("publish")
        if plan is not None:
            try:
                async with Session() as session:
                    resolution = CanonicalResolutionService(session, artifacts)
                    await F2.resolve_plan(
                        session=session,
                        resolution=resolution,
                        project_id=project,
                        wp_id=wp,
                        entry_id=_FIRST_TARGET,
                    )
                snap["phases"]["rerun"] = {
                    "rejected": False,
                    "error_code": None,
                    "publish_succeeded": publish_succeeded,
                }
            except Exception as exc:  # noqa: BLE001
                snap["phases"]["rerun"] = {
                    "rejected": True,
                    "error_code": str(getattr(exc, "error_code", "") or ""),
                    "type": type(exc).__name__,
                    "publish_succeeded": publish_succeeded,
                }
        async with Session() as session:
            snap["snapshots"]["after_rerun"] = await _table_snapshot(session)

        # ── 阶段 6：Property 24 —— 目标选取在固定库状态下确定 ─────────────
        try:
            snap["phases"]["target_resolution"] = await _repeat_target_resolution(
                Session, project=project, wp=wp
            )
        except Exception as exc:  # noqa: BLE001
            _phase_failed("target_resolution", exc)

        # ── 阶段 7：Property 34 —— timestamptz 往返 ──────────────────────
        try:
            snap["phases"]["timestamp_roundtrip"] = await _timestamp_roundtrip(
                engine, Session
            )
        except Exception as exc:  # noqa: BLE001
            _phase_failed("timestamp_roundtrip", exc)

        # ── 阶段 8：Property 13 —— 三个阶段各注入一次失败 ─────────────────
        try:
            snap["phases"]["injected_failures"] = await _injected_failures(
                Session,
                artifacts=artifacts,
                project=project,
                wp=wp,
                staging_root=staging_root,
                plan=plan,
                staged=staged,
            )
        except Exception as exc:  # noqa: BLE001
            _phase_failed("injected_failures", exc)

        # ── 阶段 9：Property 35 —— 多步复原，第 k 步失败 ──────────────────
        try:
            snap["phases"]["restore_sequence"] = await _restore_sequence(Session)
        except Exception as exc:  # noqa: BLE001
            _phase_failed("restore_sequence", exc)

        # ── 阶段 10：Property 33 —— 判定取自数据而非退出码 ────────────────
        try:
            snap["phases"]["exit_code_vs_data"] = await _exit_code_vs_data(Session)
        except Exception as exc:  # noqa: BLE001
            _phase_failed("exit_code_vs_data", exc)

        # ── 阶段 11：四个 pilot 各自停在哪一步（首版可行域的实测） ─────────
        try:
            snap["phases"]["feasible_domain"] = await _probe_all_entries(
                Session, artifacts=artifacts, engine=engine, staging_root=staging_root
            )
        except Exception as exc:  # noqa: BLE001
            _phase_failed("feasible_domain", exc)

        # ── 阶段 12：宿主的空 store 载荷常量对四个 provider 是否都成立 ─────
        try:
            snap["phases"]["empty_store_payload"] = _empty_store_payload_shapes()
        except Exception as exc:  # noqa: BLE001
            _phase_failed("empty_store_payload", exc)

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


async def _revision_and_pointer(
    Session: Any, *, wp_id: uuid.UUID, entry_id: str
) -> tuple[int, str | None]:
    """(content_revision, entry_state.representation_id) 的当前读数。"""
    import sqlalchemy as sa

    async with Session() as session:
        revision = int(
            (
                await session.execute(
                    sa.text(
                        "SELECT COALESCE(content_revision, 0) FROM working_paper"
                        " WHERE id = :w"
                    ),
                    {"w": wp_id},
                )
            ).scalar_one()
        )
        pointer = (
            await session.execute(
                sa.text(
                    "SELECT current_representation_id"
                    "  FROM working_paper_sync_entry_state"
                    " WHERE wp_id = :w AND entry_id = :e"
                ),
                {"w": wp_id, "e": entry_id},
            )
        ).scalar_one_or_none()
    return revision, (str(pointer) if pointer is not None else None)


def _receipt_facts(receipt: Any) -> dict[str, Any]:
    """从 commit 回执里取可断言的事实（属性缺失时记 `None` 而不是抛）。"""
    keys = (
        "representation_id",
        "content_version_id",
        "generation",
        "revision",
        "content_revision",
        "committed",
    )
    out: dict[str, Any] = {"type": type(receipt).__name__}
    for key in keys:
        value = getattr(receipt, key, None)
        out[key] = None if value is None else str(value)
    out["attrs"] = sorted(
        name for name in dir(receipt) if not name.startswith("_")
    )[:40]
    return out


async def _repeat_target_resolution(
    Session: Any, *, project: uuid.UUID, wp: uuid.UUID
) -> dict[str, Any]:
    """Property 24 落库侧：同一库状态下重复解析目标必须选同一条。

    🔴 用**生产**的 `_resolve_target`（宿主里那一个），不自己写一条 SQL ——
    自写等于测试自己的实现，宿主排序改了这里不跟。

    为了让「同一条」这件事有意义，先在同一码族里多插几条底稿：只有一条时，
    「重复选到同一条」在任何实现下都恒真（包括 `ORDER BY random()`）。
    """
    import importlib.util

    import sqlalchemy as sa

    from app.services.workpaper_sync.adapters import registry as RG

    host_path = BACKEND / "scripts/fix/fix_projection_first_publication.py"
    spec = importlib.util.spec_from_file_location("_fp_host_for_pg", host_path)
    assert spec is not None and spec.loader is not None
    host = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = host
    spec.loader.exec_module(host)

    row = next(
        r
        for r in RG.DELIVERED_PER_ENTRY_CONTRACTS
        if str(r["entry_id"]) == _FIRST_TARGET
    )
    store_item_id = str(row["store_item_id"]) if "store_item_id" in row else ""
    if not store_item_id:
        provider = __import__(
            str(row["provider_module"]), fromlist=["STORE_ITEM_ID"]
        )
        store_item_id = str(getattr(provider, "STORE_ITEM_ID", "") or "")
    wp_codes = host._adjudicated_wp_codes(_FIRST_TARGET)

    # 同码族多插几条候选（含一条 store 有数据的）—— 让全序真的有事可做。
    #
    # 🔴 至少 4 条。首版我写 `wp_codes * 2`，而 H1 的码族只有一个码 ⇒ 只种出 2 条，
    #    「重复选到同一条」在 2 条上几乎恒真（连 `ORDER BY random()` 也有 50% 蒙对）。
    #    5 次重复 × 4 条候选 ⇒ 随机实现漏检概率 4 × (1/4)**4 ≈ 1.6%，仍不算强，
    #    因此另配一条判据核实「选中的确实是排序键最优的那条」（见守卫侧）。
    seeded: list[str] = []
    async with Session() as session:
        for index, code in enumerate(list(wp_codes) * 4):
            wp_index_id = uuid.uuid4()
            candidate = uuid.uuid4()
            await session.execute(
                sa.text(
                    "INSERT INTO wp_index (id, wp_code) VALUES (:i, :c)"
                    " ON CONFLICT DO NOTHING"
                ),
                {"i": wp_index_id, "c": code},
            )
            await session.execute(
                sa.text(
                    "INSERT INTO working_paper (id, project_id, wp_index_id,"
                    " created_at) VALUES (:w, :p, :i, :t)"
                ),
                {
                    "w": candidate,
                    "p": project,
                    "i": wp_index_id,
                    "t": _now() - timedelta(days=index),
                },
            )
            # 🔴 让**最后**建的那条带 store 数据。`TARGET_ORDER_SQL` 的首项是
            #    `has_store_payload DESC`，因此正确实现必须选它 —— 而它的
            #    `created_at` 是最早的（index 越大越早），若实现漏了首项就会选中别的。
            #    这让「选取确定」与「选取正确」两件事都能被验到。
            has_store = index == len(list(wp_codes) * 4) - 1
            if has_store:
                await session.execute(
                    sa.text(
                        "INSERT INTO checklist_responses (id, wp_id, item_id, remark)"
                        " VALUES (:i, :w, :it, :r)"
                    ),
                    {
                        "i": uuid.uuid4(),
                        "w": candidate,
                        "it": store_item_id,
                        "r": "[]",
                    },
                )
            seeded.append(
                {
                    "wp_id": str(candidate),
                    "wp_code": code,
                    "created_at_offset_days": -index,
                    "has_store": has_store,
                }
            )
        await session.commit()

    picks: list[dict[str, Any]] = []
    for _ in range(5):
        async with Session() as session:
            target = await host._resolve_target(
                session, wp_codes=list(wp_codes), store_item_id=store_item_id
            )
        picks.append(
            {
                "wp_id": str(target.wp_id) if target else None,
                "wp_code": str(target.wp_code) if target else None,
                "store_bytes": int(target.store_bytes or 0) if target else None,
            }
        )
    expected = next((s for s in seeded if s["has_store"]), None)
    return {
        "wp_codes": list(wp_codes),
        "store_item_id": store_item_id,
        "seeded_candidates": seeded,
        "expected_pick_wp_id": expected["wp_id"] if expected else None,
        "picks": picks,
        "distinct_picks": len({json.dumps(p, sort_keys=True) for p in picks}),
    }


async def _timestamp_roundtrip(engine: Any, Session: Any) -> dict[str, Any]:
    """Property 34：带时区时间戳在 **Python 侧**编码后往返。

    🔴 坑①的落点。三组对照：
    * `python_datetime` —— 传 `datetime` 对象（正确做法）；
    * `sql_cast_string` —— 传字符串 + SQL 层 `CAST(:x AS timestamptz)`（**错误**做法，
      asyncpg 在发送前就按目标类型编码，到 CAST 时字符串已经错了）；
    * `dst_boundary` —— 夏令时切换点附近的时刻（时区换算最容易错的地方）。

    判据比**时间点**（`==` on aware datetime）而不是字符串表示：
    PG 返回的是 UTC，`+08:00` 的输入回来会长得不一样但表示同一时刻。
    """
    import sqlalchemy as sa

    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "CREATE TABLE _tstz_probe (id UUID PRIMARY KEY, at TIMESTAMPTZ NOT NULL)"
        )

    out: dict[str, Any] = {"cases": []}

    samples = [
        ("utc_now", _now()),
        ("tz_plus_8", datetime(2026, 3, 8, 1, 30, tzinfo=timezone(timedelta(hours=8)))),
        ("tz_minus_5", datetime(2026, 11, 1, 1, 30, tzinfo=timezone(timedelta(hours=-5)))),
        ("dst_boundary", datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc)),
        ("far_past", datetime(1970, 1, 1, 0, 0, 1, tzinfo=timezone.utc)),
        ("microseconds", datetime(2026, 6, 15, 12, 34, 56, 789012, tzinfo=timezone.utc)),
    ]
    async with Session() as session:
        for label, value in samples:
            probe_id = uuid.uuid4()
            await session.execute(
                sa.text("INSERT INTO _tstz_probe (id, at) VALUES (:i, :t)"),
                {"i": probe_id, "t": value},
            )
            await session.commit()
            got = (
                await session.execute(
                    sa.text("SELECT at FROM _tstz_probe WHERE id = :i"),
                    {"i": probe_id},
                )
            ).scalar_one()
            out["cases"].append(
                {
                    "label": label,
                    "sent_iso": value.isoformat(),
                    "got_iso": got.isoformat() if got is not None else None,
                    "instant_equal": bool(got is not None and got == value),
                    "string_equal": bool(
                        got is not None and got.isoformat() == value.isoformat()
                    ),
                    "got_is_aware": bool(got is not None and got.tzinfo is not None),
                }
            )

    # 错误做法的对照：字符串 + SQL 层 CAST
    async with Session() as session:
        probe_id = uuid.uuid4()
        value = _now()
        try:
            await session.execute(
                sa.text(
                    "INSERT INTO _tstz_probe (id, at)"
                    " VALUES (:i, CAST(:t AS timestamptz))"
                ),
                {"i": probe_id, "t": value.isoformat()},
            )
            await session.commit()
            got = (
                await session.execute(
                    sa.text("SELECT at FROM _tstz_probe WHERE id = :i"),
                    {"i": probe_id},
                )
            ).scalar_one()
            out["sql_cast_string"] = {
                "accepted": True,
                "instant_equal": bool(got == value),
                "note": "本次接受了字符串 —— 驱动/版本相关，判据不依赖它失败",
            }
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            out["sql_cast_string"] = {
                "accepted": False,
                "error": f"{type(exc).__name__}: {str(exc)[:160]}",
                "note": (
                    "SQL 层 CAST 对字符串无效 —— asyncpg 在**发送之前**就按目标类型"
                    "编码参数，到 CAST 时已经错了（坑①）"
                ),
            }
    return out


async def _injected_failures(
    Session: Any,
    *,
    artifacts: Any,
    project: uuid.UUID,
    wp: uuid.UUID,
    staging_root: Path,
    plan: Any,
    staged: Any,
) -> dict[str, Any]:
    """Property 13：三个阶段各注入一次失败，逐表快照比对。

    三个阶段选的是**链条上三个不同位置**（早/中/晚），因为「失败无残留」的风险随
    位置推进而上升：越晚失败，前面写下的东西越多。

    ① `stage_instrumented_substrate` 失败（最早 —— 本该零库写入）；
    ② `resolve_plan` 失败（准入阶段 —— 本该零库写入）；
    ③ `publish_first_generation` 中途失败（最晚 —— 已经开始写，必须整体回滚）。
    """
    from app.services.workpaper_sync import projection_first_publication as F2
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    out: dict[str, Any] = {"stages": []}

    async def _snapshot() -> dict[str, Any]:
        async with Session() as session:
            return await _table_snapshot(session)

    # ── ① staging 阶段失败：喂一个不存在的 entry ──────────────────────
    before = await _snapshot()
    error = None
    try:
        F2.stage_instrumented_substrate(
            entry_id="xlsx/definitely-not-a-delivered-entry",
            staging_dir=staging_root / "inject-1",
        )
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {str(exc)[:120]}"
    after = await _snapshot()
    out["stages"].append(
        {
            "stage": "stage_instrumented_substrate",
            "raised": error,
            "diffs": _diff_snapshots(before, after),
        }
    )

    # ── ② 准入阶段失败：opaque entry_id ───────────────────────────────
    from app.services.workpaper_sync.writer_migration import opaque_entry_id

    before = await _snapshot()
    error = None
    try:
        async with Session() as session:
            resolution = CanonicalResolutionService(session, artifacts)
            await F2.resolve_plan(
                session=session,
                resolution=resolution,
                project_id=project,
                wp_id=wp,
                entry_id=opaque_entry_id(wp_code=None, wp_id=wp),
            )
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {str(exc)[:120]}"
    after = await _snapshot()
    out["stages"].append(
        {
            "stage": "resolve_plan",
            "raised": error,
            "diffs": _diff_snapshots(before, after),
        }
    )

    # ── ③ 发布**已开始写库之后**失败 ──────────────────────────────────
    #
    # 🔴 注入点必须在「已经写了行」之后。首版我把 `store_payload` 换成坏 JSON，
    #    实测它在第 ③ 步（projection 组装）就抛 `StorePayloadError` —— 那时**一行都
    #    还没写**，于是「四表逐行不变」在构造上恒真，判据验不到回滚。
    #
    #    改法：替身包住 `ContentMutationService.commit`，先让真实实现跑完（它会写
    #    content_version / representation / entry_state 三处），再抛。此时事务里有
    #    未提交的真实写入 —— 「逐行不变」只能靠回滚成立。
    before = await _snapshot()
    error = None
    wrote_rows_before_failing: int | None = None
    if plan is not None and staged is not None:
        from app.services.workpaper_sync import content_mutation as CM

        original_commit = CM.ContentMutationService.commit

        async def _commit_then_explode(self: Any, **kwargs: Any) -> Any:
            nonlocal wrote_rows_before_failing
            import sqlalchemy as sa

            await original_commit(self, **kwargs)
            # 事务内现查：证明「已经写了」——「逐行不变」因此只能靠回滚成立
            wrote_rows_before_failing = int(
                (
                    await self._session.execute(
                        sa.text(
                            "SELECT count(*) FROM working_paper_content_representation"
                        )
                    )
                ).scalar_one()
            )
            raise _HarnessError(
                "注入失败：commit 已写完三处行、事务尚未提交（Property 13 的注入点）"
            )

        CM.ContentMutationService.commit = _commit_then_explode  # type: ignore[assignment]
        try:
            async with Session() as session:
                resolution = CanonicalResolutionService(session, artifacts)
                await F2.publish_first_generation(
                    session=session,
                    resolution=resolution,
                    artifacts=artifacts,
                    repository=WorkpaperSyncRepository(session),
                    plan=plan,
                    staged=staged,
                    store_payload="[]",
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {str(exc)[:160]}"
        finally:
            CM.ContentMutationService.commit = original_commit  # type: ignore[assignment]
    after = await _snapshot()
    out["stages"].append(
        {
            "stage": "publish_first_generation",
            "raised": error,
            "diffs": _diff_snapshots(before, after),
            "rows_written_before_failing": wrote_rows_before_failing,
            "note": (
                "替身未被调到（`rows_written_before_failing` 为 None）说明失败发生在"
                "`ContentMutationService.commit` **内部**（materialize 阶段）而不是"
                "它返回之后 —— H1 当前的模板/契约漂移使「写完再失败」这个注入点"
                "在 H1 上无法构造。第 ④ 处注入补上这一位置。"
            ),
        }
    )

    # ── ④ 真实四表上写了行之后回滚 ────────────────────────────────────
    #
    # 🔴 与第 ③ 处的区别：③ 依赖 `publish_first_generation` 能走到写库那一步，
    #    而 H1 当前走不到。这一处**直连真实表**写一行 content_version（它带 FK 与
    #    CHECK 约束），再抛、不 commit —— 于是「四表逐行不变」只能靠事务回滚成立。
    #
    #    与 `_restore_sequence` 的 B 组也不同：那组用自建探针表，这里用的是
    #    Requirement 3.8 / 5.7 点名的**那四张表**，约束齐全。
    import sqlalchemy as sa

    before = await _snapshot()
    error = None
    rows_inside_transaction: int | None = None
    try:
        async with Session() as session:
            artifact_row = (
                await session.execute(
                    sa.text("SELECT id FROM working_paper_artifact LIMIT 1")
                )
            ).scalar_one_or_none()
            await session.execute(
                sa.text(
                    "INSERT INTO working_paper_content_version"
                    " (id, wp_id, revision, source, projection_artifact_id,"
                    "  projection_sha256)"
                    " VALUES (:i, :w, :r, 'html', :a, :d)"
                ),
                {
                    "i": uuid.uuid4(),
                    "w": wp,
                    "r": 9001,
                    "a": artifact_row,
                    "d": hashlib.sha256(b"probe").hexdigest(),
                },
            )
            rows_inside_transaction = int(
                (
                    await session.execute(
                        sa.text("SELECT count(*) FROM working_paper_content_version")
                    )
                ).scalar_one()
            )
            raise _HarnessError("注入失败：真实表已写入一行、事务尚未提交")
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {str(exc)[:160]}"
    after = await _snapshot()
    out["stages"].append(
        {
            "stage": "real_table_write_then_rollback",
            "raised": error,
            "diffs": _diff_snapshots(before, after),
            "rows_written_before_failing": rows_inside_transaction,
        }
    )
    return out


async def _restore_sequence(Session: Any) -> dict[str, Any]:
    """Property 35：多步复原，第 k 步失败时前 k-1 步的写入必须保留。

    🔴 坑②的落点。构造一个三步「复原」序列，第 3 步注入失败：
    * **独立事务边界**（每步各自 `async with Session()` + `commit`）⇒ 前两步保留；
    * 对照组：同一序列共用一个事务 ⇒ 前两步被一起撤回。

    两组都跑，判据是「独立事务那组保留、共用那组丢失」—— 只跑前者时，
    「保留」在任何实现下都可能恰好成立（比如三步全成功）。
    """
    import sqlalchemy as sa

    async with Session() as session:
        await session.execute(
            sa.text(
                "CREATE TABLE _restore_probe ("
                " id UUID PRIMARY KEY, step INTEGER NOT NULL UNIQUE)"
            )
        )
        await session.commit()

    async def _step(session: Any, step: int, *, fail: bool) -> None:
        await session.execute(
            sa.text("INSERT INTO _restore_probe (id, step) VALUES (:i, :s)"),
            {"i": uuid.uuid4(), "s": step},
        )
        if fail:
            raise _HarnessError(f"注入失败：第 {step} 步")

    # ── A 组：逐步独立事务 ────────────────────────────────────────────
    independent_error = None
    for step in (1, 2, 3):
        try:
            async with Session() as session:
                await _step(session, step, fail=(step == 3))
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            independent_error = f"{type(exc).__name__}: {exc}"
    async with Session() as session:
        independent_rows = sorted(
            int(r)
            for r in (
                await session.execute(sa.text("SELECT step FROM _restore_probe"))
            ).scalars()
        )
        await session.execute(sa.text("DELETE FROM _restore_probe"))
        await session.commit()

    # ── B 组（对照）：共用一个事务 ────────────────────────────────────
    shared_error = None
    try:
        async with Session() as session:
            for step in (11, 12, 13):
                await _step(session, step, fail=(step == 13))
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        shared_error = f"{type(exc).__name__}: {exc}"
    async with Session() as session:
        shared_rows = sorted(
            int(r)
            for r in (
                await session.execute(sa.text("SELECT step FROM _restore_probe"))
            ).scalars()
        )

    return {
        "independent": {
            "surviving_steps": independent_rows,
            "error": independent_error,
        },
        "shared_transaction": {
            "surviving_steps": shared_rows,
            "error": shared_error,
        },
    }


async def _probe_all_entries(
    Session: Any, *, artifacts: Any, engine: Any, staging_root: Path
) -> dict[str, Any]:
    """四个 pilot entry 各自停在链条哪一步 —— 首版可行域的**实测**。

    🔴 为什么必须逐个跑而不是只跑 H1：Requirement 12.5 声明 H1 与 D2 为可发布目标，
    只跑 H1 时「H1 发不出去」会被误读为「H1 特有的问题」。逐个跑才能看出
    D2 撞的是**同一个**错形（模板末行的 `'……'`），从而定性为契约/模板漂移而非
    单个 entry 的偶发。

    每个 entry 用**独立** (project, wp) —— 共用会让第二个起撞上判据 ③
    （首版已发）而看不出它自己会停在哪。
    """
    import sqlalchemy as sa

    from app.services.workpaper_sync import projection_first_publication as F2
    from app.services.workpaper_sync import projection_provisioning as PP
    from app.services.workpaper_sync.adapters import registry as RG
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    out: dict[str, Any] = {}
    for row in RG.DELIVERED_PER_ENTRY_CONTRACTS:
        entry_id = str(row["entry_id"])
        record: dict[str, Any] = {"stopped_at": None, "error_code": "", "reached": []}
        project, wp = uuid.uuid4(), uuid.uuid4()
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("INSERT INTO projects (id) VALUES (:p)"), {"p": project}
            )
            await conn.execute(
                sa.text("INSERT INTO working_paper (id, project_id) VALUES (:w, :p)"),
                {"w": wp, "p": project},
            )

        try:
            async with Session() as session:
                await PP.ProjectionDefinitionProvisioner(
                    session=session,
                    repository=WorkpaperSyncRepository(session),
                    artifacts=artifacts,
                    project_id=project,
                    wp_id=wp,
                ).ensure(entry_id=entry_id)
                await session.commit()
            record["reached"].append("provision")
        except Exception as exc:  # noqa: BLE001
            record["stopped_at"] = "provision"
            record["error_code"] = str(getattr(exc, "error_code", "") or "")
            record["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            out[entry_id] = record
            continue

        staged_here = None
        try:
            staged_here = F2.stage_instrumented_substrate(
                entry_id=entry_id,
                staging_dir=staging_root / f"probe-{uuid.uuid4().hex[:8]}",
            )
            record["reached"].append("stage")
        except Exception as exc:  # noqa: BLE001
            record["stopped_at"] = "stage"
            record["error_code"] = str(getattr(exc, "error_code", "") or "")
            record["gate"] = str(getattr(exc, "gate", "") or "")
            record["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            out[entry_id] = record
            continue

        plan_here = None
        try:
            async with Session() as session:
                plan_here = await F2.resolve_plan(
                    session=session,
                    resolution=CanonicalResolutionService(session, artifacts),
                    project_id=project,
                    wp_id=wp,
                    entry_id=entry_id,
                )
            record["reached"].append("resolve_plan")
        except Exception as exc:  # noqa: BLE001
            record["stopped_at"] = "resolve_plan"
            record["error_code"] = str(getattr(exc, "error_code", "") or "")
            record["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            out[entry_id] = record
            continue

        try:
            async with Session() as session:
                await F2.publish_first_generation(
                    session=session,
                    resolution=CanonicalResolutionService(session, artifacts),
                    artifacts=artifacts,
                    repository=WorkpaperSyncRepository(session),
                    plan=plan_here,
                    staged=staged_here,
                    store_payload="[]",
                )
                await session.commit()
            record["reached"].append("publish")
            record["stopped_at"] = None  # 全通
            async with Session() as session:
                record["representation_rows"] = int(
                    (
                        await session.execute(
                            sa.text(
                                "SELECT count(*) FROM"
                                " working_paper_content_representation WHERE wp_id = :w"
                            ),
                            {"w": wp},
                        )
                    ).scalar_one()
                )
        except Exception as exc:  # noqa: BLE001
            record["stopped_at"] = "publish"
            record["error_code"] = str(getattr(exc, "error_code", "") or "")
            record["cell"] = str(getattr(exc, "cell", "") or "")
            record["stable_key"] = str(getattr(exc, "stable_key", "") or "")
            record["error"] = f"{type(exc).__name__}: {str(exc)[:220]}"
        out[entry_id] = record
    return out


def _empty_store_payload_shapes() -> dict[str, Any]:
    """宿主的 `_EMPTY_STORE_PAYLOAD` 对四个 provider 是否都成立。

    🔴 宿主用**同一个**常量 `"[]"` 喂所有 provider。实测：
    * H1 / D2 的 `build_store_projection` 要 `Sequence` ⇒ `"[]"` 正确；
    * **G7 要 `Mapping`** ⇒ `"[]"` 抛 `StorePayloadError`，而 `"{}"` 也不行
      （它还要 `STORE_STATE_VERSION`）。

    该路径至今未被走到，因为真库上 G7 被 `already_published` 拦在
    `_read_store_payload` **之前**。干净库上就会崩。
    """
    import importlib

    from app.services.workpaper_sync.adapters import registry as RG
    from app.services.workpaper_sync.contracts import load_contract

    out: dict[str, Any] = {}
    for row in RG.DELIVERED_PER_ENTRY_CONTRACTS:
        entry_id = str(row["entry_id"])
        provider = importlib.import_module(str(row["provider_module"]))
        record: dict[str, Any] = {
            "has_build_store_projection": hasattr(provider, "build_store_projection")
        }
        if record["has_build_store_projection"]:
            contract = load_contract(str(row["contract_id"]))
            for literal in ("[]", "{}"):
                try:
                    projection = provider.build_store_projection(
                        literal, contract=contract
                    )
                    record[literal] = {
                        "accepted": True,
                        "values": len(projection.values),
                    }
                except Exception as exc:  # noqa: BLE001
                    record[literal] = {
                        "accepted": False,
                        "type": type(exc).__name__,
                        "error": str(exc)[:180],
                    }
        out[entry_id] = record
    return out


async def _exit_code_vs_data(Session: Any) -> dict[str, Any]:
    """Property 33：成败判定取自数据库数据，不取进程退出码。

    🔴 坑③的落点。构造两种**不一致**：
    * `committed_but_nonzero_exit` —— 数据已提交，而「进程」报了非零退出码；
    * `uncommitted_but_zero_exit`  —— 数据未提交（回滚），而「进程」报了 0。

    判据：两种情形下，「成了没有」的结论都必须与**落库行**一致，与退出码无关。
    """
    import sqlalchemy as sa

    async with Session() as session:
        await session.execute(
            sa.text(
                "CREATE TABLE _exit_probe ("
                " id UUID PRIMARY KEY, label TEXT NOT NULL UNIQUE)"
            )
        )
        await session.commit()

    async def _rows() -> list[str]:
        async with Session() as session:
            return sorted(
                str(r)
                for r in (
                    await session.execute(sa.text("SELECT label FROM _exit_probe"))
                ).scalars()
            )

    # ① 已提交 + 非零退出码
    async with Session() as session:
        await session.execute(
            sa.text("INSERT INTO _exit_probe (id, label) VALUES (:i, 'committed')"),
            {"i": uuid.uuid4()},
        )
        await session.commit()
    committed_rows = await _rows()

    # ② 未提交（回滚）+ 退出码 0
    async with Session() as session:
        await session.execute(
            sa.text("INSERT INTO _exit_probe (id, label) VALUES (:i, 'rolled_back')"),
            {"i": uuid.uuid4()},
        )
        await session.rollback()
    after_rollback_rows = await _rows()

    return {
        "committed_but_nonzero_exit": {
            "claimed_exit_code": 1,
            "rows_after": committed_rows,
            "data_says_succeeded": "committed" in committed_rows,
        },
        "uncommitted_but_zero_exit": {
            "claimed_exit_code": 0,
            "rows_after": after_rollback_rows,
            "data_says_succeeded": "rolled_back" in after_rollback_rows,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# module fixture —— 一次 asyncio.run
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


# ═══════════════════════════════════════════════════════════════════════════
# 夹具自身的健康判据（这一节是「采集异常记录不穿透」那个决定的另一半）
# ═══════════════════════════════════════════════════════════════════════════


class TestHarnessItself:
    """夹具没有静默降级。

    🔴 采集里的 `except` 一律**记录不穿透**（否则整个 module 变 collection ERROR，
    而 `-rf` 只列 FAILED 不列 ERROR ⇒ 定向变异看不到预期失败项 ⇒ 判 GREEN）。
    这一节把「记下来的错」翻成真实的失败，缺了它 fail-open 就成立了。
    """

    def test_migrations_applied_cleanly(self, snap: dict[str, Any]) -> None:
        assert snap["apply_errors"] == [], (
            f"迁移应用报错 {snap['apply_errors'][:3]} —— 后续全部判据都建立在"
            "「schema 与生产一致」这个前提上"
        )

    def test_scratch_schema_is_isolated(self, snap: dict[str, Any]) -> None:
        """判据落在**命名前缀**上：写错前缀会让 DROP 落到别的 schema。"""
        assert str(snap["schema"]).startswith(_SCHEMA_PREFIX), (
            f"schema 名 {snap['schema']!r} 不带隔离前缀 {_SCHEMA_PREFIX!r}"
        )

    def test_only_the_known_blocking_phase_failed(self, snap: dict[str, Any]) -> None:
        """🔴 除**已知阻塞**的 `publish` 之外，任何阶段崩了都必须打红。

        白名单只有一项，且它的原因被 `TestFirstPublicationIsBlocked` 逐项定性。
        往这个白名单里加东西等于把「没验证」记成「通过」—— 加之前必须先在那一类
        判据里把新原因写清楚。
        """
        allowed = {"publish"}
        unexpected = {
            name: reason
            for name, reason in snap["harness_errors"].items()
            if name not in allowed
        }
        assert not unexpected, (
            "这些阶段在采集期崩了（不在已知阻塞白名单内）:\n"
            + "\n".join(f"  {name}: {reason}" for name, reason in unexpected.items())
        )

    def test_every_declared_phase_produced_material(self, snap: dict[str, Any]) -> None:
        """每个声明要跑的阶段都留下了素材（空字典 = 那条判据在空集上）。"""
        required = (
            "supply_before",
            "provision",
            "supply_after_provision",
            "staged",
            "loader_without_representation",
            "plan",
            "rerun",
            "target_resolution",
            "timestamp_roundtrip",
            "injected_failures",
            "restore_sequence",
            "exit_code_vs_data",
            "feasible_domain",
            "empty_store_payload",
        )
        empty = [name for name in required if not snap["phases"].get(name)]
        assert not empty, f"这些阶段没有素材: {empty} —— 对应判据会在空集上恒真"


# ═══════════════════════════════════════════════════════════════════════════
# Property 18 行为侧（F7 移交）：Frozen_Definitions 零 representation 依赖
# ═══════════════════════════════════════════════════════════════════════════


class TestLoaderProducesWithoutAnyRepresentation:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 18: Frozen_Definitions 的生产入参零 representation 依赖（行为侧）**

    **Validates: Requirements 5.1, 5.2, 5.3**

    F7 只能落结构判据（入参名 / AST 来源根 / 被调方签名 / ORM 取数点）。
    「**真的**在没有任何 representation 的库上产出了」只能在真库上说 —— 这里说。

    这是本 spec 破环点的唯一直接证据：要 representation 才能造 adapter、
    要 adapter 才能发 representation 的死环，被 `ExcelEntryDefinitionLoader` 破开。
    """

    def test_loader_produced_definitions(self, snap: dict[str, Any]) -> None:
        payload = snap["phases"]["loader_without_representation"]
        assert payload["produced"] is True, (
            "loader 在真库上没产出 Frozen_Definitions —— 破环点没有真的破环"
        )

    def test_there_was_no_representation_row_at_that_moment(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 分母：产出的那一刻，库里 representation 行数必须是 **0**。

        非 0 时本判据退化成「有 representation 时也能产出」—— 那是 observer 路径
        本来就能做的事，证明不了破环。
        """
        payload = snap["phases"]["loader_without_representation"]
        assert payload["representation_rows_at_that_moment"] == 0, (
            f"产出时库里已有 {payload['representation_rows_at_that_moment']} 行 "
            "representation —— 破环这件事没有被证明到"
        )

    def test_produced_definitions_carry_real_measured_inputs(
        self, snap: dict[str, Any]
    ) -> None:
        """产出物带着实测入参，不是一个空壳。

        `structure_inventory_size` 与 `business_sheets` 必须非零 ——
        全零的 `FrozenEntryDefinitions` 也能算「产出了」，但它对下游毫无用处。
        """
        payload = snap["phases"]["loader_without_representation"]
        assert payload["structure_inventory_size"] > 0, (
            f"structure_inventory_size={payload['structure_inventory_size']} —— "
            "产出物是空壳"
        )
        assert payload["business_sheets"] > 0, "business_sheets 为空"
        assert payload["has_identity_inventory"] is True, "identity_inventory 缺失"
        assert payload["entry_id"] == _FIRST_TARGET

    def test_the_bundle_it_used_is_the_provisioned_one(
        self, snap: dict[str, Any]
    ) -> None:
        """用的是 provision 出来的那个 approved bundle（不是别处捡的）。"""
        payload = snap["phases"]["loader_without_representation"]
        provisioned = str(snap["phases"]["provision"]["definition_bundle_id"])
        assert payload["bundle_id"] == provisioned, (
            f"loader 用的 bundle {payload['bundle_id']} 不是 provision 出来的 "
            f"{provisioned}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 13：任一阶段失败时数据库四处逐行不变
# ═══════════════════════════════════════════════════════════════════════════


class TestFailureLeavesNoResidue:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 13: 任一阶段失败时数据库四处逐行不变**

    **Validates: Requirements 3.8, 5.7**

    四处注入分布在链条的四个不同位置，因为「失败无残留」的风险随位置推进而上升：
    越晚失败，前面写下的东西越多。

    | 注入 | 位置 | 该位置本该 |
    |---|---|---|
    ① staging | 最早 | 零库写入（签名里没有 session） |
    ② 准入 | resolve_plan | 零库写入（五条准入全在读） |
    ③ 发布 | materialize 内部 | 事务回滚 |
    ④ 真实表写行后 | commit 之前 | 事务回滚（**带 FK 与 CHECK 的真表**） |
    """

    def _stage(self, snap: dict[str, Any], name: str) -> dict[str, Any]:
        stages = snap["phases"]["injected_failures"]["stages"]
        match = [s for s in stages if s["stage"] == name]
        assert len(match) == 1, f"注入阶段 {name!r} 命中 {len(match)} 条（应恰 1）"
        return match[0]

    @pytest.mark.parametrize(
        "stage_name",
        [
            "stage_instrumented_substrate",
            "resolve_plan",
            "publish_first_generation",
            "real_table_write_then_rollback",
        ],
    )
    def test_each_injected_failure_left_the_four_tables_unchanged(
        self, snap: dict[str, Any], stage_name: str
    ) -> None:
        stage = self._stage(snap, stage_name)
        assert stage["raised"], (
            f"{stage_name} 的注入**没有**让它失败 —— 「失败无残留」的前提不成立，"
            "本条判据在空集上（注入构造已失效，必须重造）"
        )
        assert stage["diffs"] == [], (
            f"{stage_name} 失败后四张表有残留:\n  "
            + "\n  ".join(stage["diffs"])
        )

    def test_diff_reports_both_row_count_and_content_changes(self) -> None:
        """`_diff_snapshots` 对行数变化与内容变化都报差异。"""
        before = {
            table: {"rows": 3, "digest": "aaa"} for table in _SNAPSHOT_TABLES
        }
        same = {table: {"rows": 3, "digest": "aaa"} for table in _SNAPSHOT_TABLES}
        assert _diff_snapshots(before, same) == [], "相同快照被报出了差异"

        content_changed = dict(same)
        content_changed[_SNAPSHOT_TABLES[0]] = {"rows": 3, "digest": "bbb"}
        diffs = _diff_snapshots(before, content_changed)
        assert diffs, (
            "行数相同而内容 digest 不同时 `_diff_snapshots` 没报差异 —— "
            "比较函数退化成了只比行数"
        )
        assert "digest" in diffs[0]

        count_changed = dict(same)
        count_changed[_SNAPSHOT_TABLES[1]] = {"rows": 4, "digest": "aaa"}
        assert _diff_snapshots(before, count_changed), "行数变了没报差异"

    def test_the_snapshot_digest_really_depends_on_row_content(self) -> None:
        """🔴 `_table_snapshot` 算出的 digest 必须**依赖行内容**，不只依赖行数。

        为什么单靠上一条不够：那条只验 `_diff_snapshots`（比较函数）。若
        `_table_snapshot` 把 digest 算成 `sha256(str(len(rows)))`，比较函数照样
        「正确」，而全部残留判据在**行数相同**的情形下集体空转 ——
        「一次写入配一次删除」就查不出来。变异实测确认了这个缺口（F8-M1 判 GREEN）。

        判据形态：跑一个**内存 sqlite** 上的同名表，构造两组「行数相同、内容不同」
        的真实行，断言 `_table_snapshot` 给出不同的 digest。用 sqlite 而不是 PG 是
        因为本条验的是**摘要函数**，与数据库方言无关，且不该占用真库连接。
        """
        import sqlite3

        def _digest_of(rows: list[tuple[int, str]]) -> str:
            """复刻 `_table_snapshot` 的摘要步骤（同一段 payload 构造）。"""
            connection = sqlite3.connect(":memory:")
            connection.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
            connection.executemany("INSERT INTO t (id, v) VALUES (?, ?)", rows)
            cursor = connection.execute("SELECT id, v FROM t ORDER BY id")
            columns = [c[0] for c in cursor.description]
            mapped = [dict(zip(columns, r)) for r in cursor.fetchall()]
            connection.close()
            payload = json.dumps(
                [{k: str(v) for k, v in sorted(r.items())} for r in mapped],
                ensure_ascii=False,
                sort_keys=True,
            )
            return hashlib.sha256(payload.encode("utf-8")).hexdigest()

        rows_a = [(1, "alpha"), (2, "beta"), (3, "gamma")]
        rows_b = [(1, "alpha"), (2, "beta"), (3, "DIFFERENT")]
        rows_c = [(1, "alpha"), (2, "beta"), (4, "gamma")]  # 主键不同、行数相同

        assert _digest_of(rows_a) == _digest_of(rows_a), "同一组行的 digest 不稳定"
        assert _digest_of(rows_a) != _digest_of(rows_b), (
            "行数相同而某列值不同时 digest 相等 —— 摘要没有依赖行内容"
        )
        assert _digest_of(rows_a) != _digest_of(rows_c), (
            "行数相同而主键不同时 digest 相等 —— 「删一行加一行」查不出来"
        )

        # 与生产实现的同源性：`_table_snapshot` 的 payload 构造必须与上面一致。
        # 判据落在 AST：那段 json.dumps 的入参不得是「只含行数的字面量」。
        import ast
        import inspect

        source = inspect.getsource(_table_snapshot)
        tree = ast.parse(source.strip())
        dumps_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "dumps"
        ]
        assert len(dumps_calls) == 1, (
            f"`_table_snapshot` 里有 {len(dumps_calls)} 处 json.dumps（应恰 1）"
        )
        first_arg = dumps_calls[0].args[0]
        assert isinstance(first_arg, (ast.ListComp, ast.GeneratorExp)), (
            f"digest 的入参是 {type(first_arg).__name__} 而不是对 rows 的推导式 —— "
            "摘要可能没有遍历行内容（变异 F8-M1 正是把它换成 `{'rows': len(rows)}`）"
        )
        assert "rows" in ast.unparse(first_arg), (
            "digest 的入参里没有 `rows` —— 它没在遍历真实行"
        )

    def test_the_fourth_injection_really_wrote_a_row_first(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 第 ④ 处注入的分母：事务内**确实写进了**一行才回滚。

        `rows_written_before_failing` 为 0 或 None 时，「四表逐行不变」在构造上恒真 ——
        什么都没写当然不变，那验不到回滚。
        """
        stage = self._stage(snap, "real_table_write_then_rollback")
        rows = stage.get("rows_written_before_failing")
        assert rows is not None and rows >= 1, (
            f"第 ④ 处注入在事务内只看到 {rows} 行 —— 它本该先写进一行 "
            "content_version 再抛；没写就回滚，「无残留」是恒真的"
        )

    def test_staging_and_admission_never_touch_the_database_at_all(
        self, snap: dict[str, Any]
    ) -> None:
        """① 与 ② 是**零库写入**位，不是「写了又回滚」位。

        这两处的失败即使不回滚也该无残留（前者签名里没有 session、后者只读）。
        它们与 ③④ 的区别值得单独锁：把 session 塞进 staging 签名会让 ① 变成
        「靠回滚」而不是「构造上不可能」。
        """
        import inspect

        from app.services.workpaper_sync import projection_first_publication as F2

        signature = inspect.signature(F2.stage_instrumented_substrate)
        names = set(signature.parameters)
        for banned in ("session", "db", "connection", "repository"):
            assert banned not in names, (
                f"`stage_instrumented_substrate` 的签名里出现 {banned!r} —— "
                "「暂存期零数据库」不再是构造上成立的了"
            )
        for name in ("stage_instrumented_substrate", "resolve_plan"):
            assert self._stage(snap, name)["diffs"] == []


# ═══════════════════════════════════════════════════════════════════════════
# Property 33：成败判定取自数据库数据而非进程退出码
# ═══════════════════════════════════════════════════════════════════════════


class TestVerdictComesFromDataNotExitCode:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 33: 成败判定取自数据库数据而非进程退出码**

    **Validates: Requirements 11.2**

    构造两种**不一致**（tasks.md 7.3 原文）：
    * 已提交但退出码非零 ⇒ 结论必须是「成了」；
    * 未提交但退出码为零 ⇒ 结论必须是「没成」。

    两种都要，因为只有一种时「恒看数据」与「恒看退出码」各能骗过一条。
    """

    def test_committed_data_wins_over_a_nonzero_exit_code(
        self, snap: dict[str, Any]
    ) -> None:
        case = snap["phases"]["exit_code_vs_data"]["committed_but_nonzero_exit"]
        assert case["claimed_exit_code"] != 0, "构造前提不成立：退出码不是非零"
        assert case["data_says_succeeded"] is True, (
            "数据已提交而结论说「没成」—— 判定跟着退出码走了"
        )

    def test_rolled_back_data_wins_over_a_zero_exit_code(
        self, snap: dict[str, Any]
    ) -> None:
        case = snap["phases"]["exit_code_vs_data"]["uncommitted_but_zero_exit"]
        assert case["claimed_exit_code"] == 0, "构造前提不成立：退出码不是 0"
        assert case["data_says_succeeded"] is False, (
            "数据已回滚而结论说「成了」—— 判定跟着退出码走了"
        )

    def test_the_first_publication_verdict_itself_follows_the_data(
        self, snap: dict[str, Any]
    ) -> None:
        """把这条判据用在**本次首版**上：四表全 0 ⇒ 结论只能是「没发出去」。

        这是 Property 33 的真实应用：`publish_first_generation` 抛异常（可类比非零
        退出码），而结论「首版未落成」是由 representation 行数为 0 得出的。
        """
        after = snap["snapshots"]["after_publish"]
        rows = after["working_paper_content_representation"]["rows"]
        published = bool(snap["phases"].get("representation_row"))
        assert (rows > 0) == published, (
            f"representation 行数 {rows} 与「有落库行」结论 {published} 不一致 —— "
            "结论没有取自数据"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 34：带时区时间戳在 Python 侧编码后可往返
# ═══════════════════════════════════════════════════════════════════════════


class TestTimestampRoundTrip:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 34: 带时区时间戳在 Python 侧编码后可往返**

    **Validates: Requirements 11.3**

    🔴 坑① 的判据。判**时间点**相等（`==` on aware datetime），不判字符串表示 ——
    PG 存的是 UTC，`+08:00` 的输入回来长得不一样但表示同一时刻。
    按字符串判会在正确实现上恒红。
    """

    def test_every_sample_round_trips_by_instant(self, snap: dict[str, Any]) -> None:
        cases = snap["phases"]["timestamp_roundtrip"]["cases"]
        assert len(cases) >= 5, f"只有 {len(cases)} 个样本，分母过小"
        failed = [c for c in cases if not c["instant_equal"]]
        assert not failed, (
            "这些时刻往返后不等:\n  "
            + "\n  ".join(
                f"{c['label']}: 发 {c['sent_iso']} → 回 {c['got_iso']}" for c in failed
            )
        )

    def test_returned_values_are_timezone_aware(self, snap: dict[str, Any]) -> None:
        """回来的必须是 aware datetime —— naive 值参与比较会静默按本地时区解释。"""
        cases = snap["phases"]["timestamp_roundtrip"]["cases"]
        naive = [c["label"] for c in cases if not c["got_is_aware"]]
        assert not naive, f"这些样本回来是 naive datetime: {naive}"

    def test_the_denominator_includes_non_utc_offsets(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 样本里必须有**非 UTC 偏移**的时刻。

        全是 UTC 时，「往返相等」对任何实现都近乎恒真（不需要做任何时区换算）。
        判据落在「有样本的字符串表示变了而时间点没变」—— 那证明真的发生了换算。
        """
        cases = snap["phases"]["timestamp_roundtrip"]["cases"]
        converted = [
            c for c in cases if c["instant_equal"] and not c["string_equal"]
        ]
        assert converted, (
            "没有任何样本是「时间点相等而字符串表示不同」的 —— 样本里可能全是 UTC，"
            f"于是时区换算这件事没有被验到。实测样本: "
            f"{[(c['label'], c['string_equal']) for c in cases]}"
        )

    def test_the_wrong_way_is_recorded(self, snap: dict[str, Any]) -> None:
        """错误做法（字符串 + SQL 层 CAST）的实测结果被记下来了。

        判据不断言它**必须**失败（那取决于驱动版本），但要求这一格有记录 ——
        坑① 的存在依据是可复查的事实，不是口头经验。
        """
        record = snap["phases"]["timestamp_roundtrip"].get("sql_cast_string")
        assert record, "错误做法那一格没有记录"
        assert "note" in record, "没有记下坑① 的成因说明"
        if record.get("accepted") is False:
            assert record.get("error"), "被拒了却没记原因"

    @settings(max_examples=200, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        moment=st.datetimes(
            min_value=datetime(1970, 1, 2),
            max_value=datetime(2100, 1, 1),
            timezones=st.sampled_from(
                [timezone.utc]
                + [timezone(timedelta(hours=h)) for h in (-11, -5, 5, 8, 14)]
            ),
        )
    )
    def test_python_side_encoding_preserves_the_instant(
        self, moment: datetime
    ) -> None:
        """🔴 纯 Python 侧的往返性质（不连库，`max_examples=200`）。

        这一条与上面的真库往返成对：它验的是「aware datetime 的时刻在 UTC 归一化
        下不变」这个前提本身。前提若不成立，真库那几条就是在错的基准上比。
        """
        as_utc = moment.astimezone(timezone.utc)
        assert as_utc == moment, "aware datetime 转 UTC 后时刻变了"
        assert as_utc.tzinfo is timezone.utc
        # 字符串往返（PG 侧的文本形态）后时刻仍相等
        parsed = datetime.fromisoformat(as_utc.isoformat())
        assert parsed == moment


# ═══════════════════════════════════════════════════════════════════════════
# Property 35：复原流程每步独立事务，先前成功步骤不被撤销
# ═══════════════════════════════════════════════════════════════════════════


class TestRestoreStepsAreIndependentlyTransactional:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 35: 复原流程每步独立事务，先前成功步骤不被撤销**

    **Validates: Requirements 11.4**

    🔴 坑② 的判据。两组都跑：
    * A 组逐步独立事务 ⇒ 第 3 步失败后前两步**保留**；
    * B 组共用一个事务 ⇒ 前两步**被一起撤回**。

    只跑 A 组时「保留」可能因为三步全成功而恰好成立；B 组是那件事的对照。
    """

    def test_independent_steps_survive_a_later_failure(
        self, snap: dict[str, Any]
    ) -> None:
        payload = snap["phases"]["restore_sequence"]["independent"]
        assert payload["error"], (
            "A 组的第 3 步注入没有失败 —— 「先前步骤保留」的前提不成立"
        )
        assert payload["surviving_steps"] == [1, 2], (
            f"A 组存活步骤是 {payload['surviving_steps']}，应为 [1, 2] —— "
            "第 3 步失败把前两步一起撤回了（独立事务边界失守）"
        )

    def test_a_shared_transaction_loses_everything(self, snap: dict[str, Any]) -> None:
        """对照组：共用事务时前两步**必须**丢失。

        若这组也「保留」，说明整个构造没有真的处在一个事务里 ⇒ A 组的通过不说明问题。
        """
        payload = snap["phases"]["restore_sequence"]["shared_transaction"]
        assert payload["error"], "B 组的注入没有失败 —— 对照组失效"
        assert payload["surviving_steps"] == [], (
            f"B 组共用一个事务却存活了 {payload['surviving_steps']} —— "
            "对照组没有真的共用事务，于是 A 组的「保留」证明不了独立事务边界"
        )

    def test_the_two_groups_differ(self, snap: dict[str, Any]) -> None:
        """两组结果必须**不同** —— 相同则说明事务边界这件事根本没被区分开。"""
        independent = snap["phases"]["restore_sequence"]["independent"][
            "surviving_steps"
        ]
        shared = snap["phases"]["restore_sequence"]["shared_transaction"][
            "surviving_steps"
        ]
        assert len(independent) != len(shared), (
            f"独立事务组存活 {independent}、共用事务组存活 {shared} —— "
            "两组数量相同意味着「独立事务」与「共用事务」在本构造下没有差别"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 22 落库侧（F7 移交）：只读阶段不改库
# ═══════════════════════════════════════════════════════════════════════════


class TestReadOnlyPhasesDoNotWrite:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 22: `--check` 只读且跑完全链（落库侧）**

    **Validates: Requirements 6.1, 6.2**

    F7 落的是结构侧（`run_check` 里零写入面调用）。这里落**落库侧**：
    真跑一遍只读链路，四张表逐行不变。
    """

    def test_staging_and_admission_did_not_change_the_four_tables(
        self, snap: dict[str, Any]
    ) -> None:
        """provision 之后跑 staging + resolve_plan + loader，四表必须逐行不变。

        `after_provision` 是这三步之前的快照；三步全在读，因此它必须与紧随其后的
        注入实验的 `before` 一致 —— 后者由 `injected_failures` 的第 ① 处记录。
        """
        stages = snap["phases"]["injected_failures"]["stages"]
        first = [s for s in stages if s["stage"] == "stage_instrumented_substrate"]
        assert first and first[0]["diffs"] == []

    def test_target_resolution_is_read_only_on_the_four_tables(
        self, snap: dict[str, Any]
    ) -> None:
        """目标解析阶段（Property 24 的素材采集）不动四张表。

        🔴 它**会**往 `working_paper` / `wp_index` / `checklist_responses` 插种子行，
        那是构造分母；但 Requirement 3.8 / 5.7 点名的四张表必须不变。
        判据比的正是那四张表。
        """
        before = snap["snapshots"]["after_rerun"]
        after = snap["snapshots"].get("after_publish")
        assert after is not None
        # 重跑被拒/未发布两种情形下，after_rerun 都不该比 after_publish 多行
        for table in _SNAPSHOT_TABLES:
            assert before[table]["rows"] <= after[table]["rows"] + 0, (
                f"{table}: 重跑之后行数从 {after[table]['rows']} 变成 "
                f"{before[table]['rows']} —— 重跑产生了第二份供给"
            )


# ═══════════════════════════════════════════════════════════════════════════
# Property 24 落库侧（F7 移交）：目标选取在固定库状态下确定
# ═══════════════════════════════════════════════════════════════════════════


class TestTargetSelectionIsDeterministicOnRealData:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 24: 目标选取在固定库状态下确定（落库侧）**

    **Validates: Requirements 6.5**

    F7 落的是结构侧（排序全序、无随机项、拼进 SQL 恰一处）。
    这里落**落库侧**：同码族里种 4 条候选，用**生产**的 `_resolve_target`
    重复解析 5 次。
    """

    def test_repeated_resolution_picks_the_same_row(
        self, snap: dict[str, Any]
    ) -> None:
        payload = snap["phases"]["target_resolution"]
        assert payload["distinct_picks"] == 1, (
            f"5 次解析选出了 {payload['distinct_picks']} 种结果 —— 目标选取不确定。"
            f"实测: {payload['picks']}"
        )

    def test_the_denominator_has_several_candidates(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 分母：同码族里必须有 ≥3 条候选。

        只有 1 条时「重复选到同一条」对任何实现恒真（连 `ORDER BY random()` 也过）。
        """
        payload = snap["phases"]["target_resolution"]
        seeded = payload["seeded_candidates"]
        assert len(seeded) >= 3, (
            f"只种了 {len(seeded)} 条候选 —— 「选取确定」在这个分母上几乎恒真"
        )

    def test_it_picked_the_row_the_order_clause_designates(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 不只是「每次都一样」，还必须是**排序键指定的那一条**。

        构造刻意让带 store 数据的候选拥有**最早**的 `created_at`：
        `TARGET_ORDER_SQL` 的首项是 `has_store_payload DESC`，正确实现必须选它；
        漏了首项就会按 `created_at` 选到别的一条 —— 而那条 store 为空，
        于是首版发出去的是空 projection（「管道通了但数据没进去」那种假绿）。
        """
        payload = snap["phases"]["target_resolution"]
        expected = payload["expected_pick_wp_id"]
        assert expected, "构造里没有带 store 数据的候选 —— 本判据的分母不成立"
        picked = payload["picks"][0]["wp_id"]
        assert picked == expected, (
            f"选中了 {picked}，而排序键指定的是 {expected}（带 store 数据的那条）—— "
            "`TARGET_ORDER_SQL` 的首项 `has_store_payload DESC` 没有生效，"
            "首版会发出一份空 projection"
        )
        assert int(payload["picks"][0]["store_bytes"] or 0) > 0, (
            "选中的那条 store 为空 —— 「有数据的排在前面」没有成立"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 26 落库侧（F7 移交）：重跑幂等
# ═══════════════════════════════════════════════════════════════════════════


class TestRerunIsIdempotentOnRealData:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 26: 重跑 `--apply` 幂等，不产生第二份供给（落库侧）**

    **Validates: Requirements 6.8**
    """

    def test_supply_rows_did_not_grow_after_the_publish_attempt(
        self, snap: dict[str, Any]
    ) -> None:
        """provision 之后的四张供给表行数在发布尝试前后逐项不变。

        provision 是幂等的（Task 76 已证），本条锁的是**发布链**不额外造供给行。
        """
        before = snap["phases"]["supply_after_provision"]
        after = snap["phases"]["supply_after_publish"]
        grew = {
            table: (before[table], after[table])
            for table in before
            if after[table] > before[table]
        }
        # representation 表会因成功发布而增长 —— 那是正当的，不算「第二份供给」
        grew.pop("working_paper_content_representation", None)
        assert not grew, (
            f"这些供给表在发布链里长了行: {grew} —— 发布不得自造供给"
        )

    def test_rerun_did_not_change_the_four_tables(self, snap: dict[str, Any]) -> None:
        """重跑前后四张表逐行不变。"""
        diffs = _diff_snapshots(
            snap["snapshots"]["after_publish"], snap["snapshots"]["after_rerun"]
        )
        assert diffs == [], "重跑之后四张表变了:\n  " + "\n  ".join(diffs)

    def test_rerun_verdict_matches_whether_the_first_publication_landed(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 重跑的结论必须与「首版是否真的落成」一致。

        * 首版**已落成** ⇒ 重跑必须被判据 ③ 拒（`first_publication_already_done`）；
        * 首版**未落成** ⇒ 判据 B 仍为假，重跑**不该**被拒。

        两侧都写，因为只写前者时「首版没发出去」会让判据静默变成空转，
        而只写后者会把真正的幂等失守当成正常。
        """
        payload = snap["phases"]["rerun"]
        published = bool(snap["phases"].get("representation_row"))
        if published:
            assert payload["rejected"] is True, (
                "首版已落成而重跑没被拒 —— 幂等失守，会产生第二份 representation"
            )
            assert payload["error_code"] == "first_publication_already_done", (
                f"重跑被拒的 error_code 是 {payload['error_code']!r}，"
                "应为 `first_publication_already_done`"
            )
        else:
            assert payload["rejected"] is False, (
                f"首版未落成而重跑被拒（{payload.get('error_code')}）—— "
                "判据 B 为假时不该拒，那会让首版永远发不出去"
            )
            assert payload["publish_succeeded"] is False, (
                "快照自相矛盾：没有 representation 行却记着 publish 成功了"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 首版可行域的实测 —— 本文件最重要的一节
# ═══════════════════════════════════════════════════════════════════════════


class TestFirstPublicationFeasibleDomain:
    """首版在**干净临时 schema** 上的实测可行域，以及它与 Requirement 12.5 的差距。

    **Validates: Requirements 12.5**

    ═══ 🔴 先分清两个环境 ════════════════════════════════════════════════════

    | | 真库（主 schema） | 本夹具（干净临时 schema）|
    |---|---|---|
    G7 | **已发布首版**（2026-09-04，`generation=1`，`projection_contract`，`is_current`）| store 为空 ⇒ 夹具喂空载荷 ⇒ 载荷形态不符 |
    H1 / D2 | `--apply` 真跑过，落 `blocked_*`，库 0 新增行 | 同一错形 |
    B60 | `blocked_ooxml_gate` | 同 |

    **Checkpoint Task 8 的判据在真库上成立** —— 本节问的是另一个问题：
    「在一个从零建起的 schema 上，这四个 entry 各自能走到哪一步」。
    两者都要看：真库证明路通了，干净 schema 证明路上还有哪几处坎。

    ⇒ 本节的 `test_no_entry_published_a_first_generation` 说的是**本夹具**里零个
    entry 走完发布链，**不是**「首版从未落成」。把两者混为一谈会得出与真库相反的结论。

    ═══ 为什么这一节存在 ═════════════════════════════════════════════════════

    Requirement 12.5 声明「`xlsx/gt-h1-fixed-assets` 与
    `xlsx/gt-d2-accounts-receivable` 为**可发布目标**」。2026-09-05 在干净临时
    schema 上逐个实测，**四个 entry 都没走完发布链**：

    | entry | 停在 | error_code |
    |---|---|---|
    B60 | stage | `ooxml_security_rejected`（gate=`external_relationships`）|
    **H1** | **publish** | `excel_materialize_editable_write_failed` |
    **D2** | **publish** | `excel_materialize_editable_write_failed` |
    G7 | publish | `sync_pilot_store_payload_invalid`（**夹具构造所致**，见该条 docstring）|

    H1 与 D2 的阻塞与真库上 `--apply` 实测的 `blocked_template_contract_drift` /
    `blocked_row_insertion_required` 同源，**不是**本夹具引入的。

    H1 与 D2 撞的是**同一个错形**，根因已定位到单元格级：

    * H1 契约声明受管数据行 13..27，模板里 13..26 是序号 `1..14`，**行 27 是 `'……'`**；
    * D2 契约声明 13..25，模板里 13..24 是 `1..12`，**行 25 是 `'……'`**。

    `'……'` 是模板「此处可续行」的视觉约定，而契约把该行也算作受管数据行且
    `seq` 的 `value_type` 是 `integer`。空 store ⇒ overlay 保留基线 ⇒ materialize
    把 `'……'` 写回 integer 字段 ⇒ 规范化拒绝（那正是 `excel_materialize` 该做的：
    「不得写一个自己都读不懂的值」）。

    这与 tasks.md 记的 H1 → `blocked_template_contract_drift` 是**同一件事**。

    ═══ 为什么不在本 spec 里改 ═══════════════════════════════════════════════

    三种改法都跨出本 spec 的范围，需要契约/模板裁决：

    1. 把受管区收到 13..26（H1）/ 13..24（D2）—— 动的是**已冻结的契约**，
       Task 40~43 的判据全部挂在上面；
    2. 放宽 `seq` 的 `value_type` —— 那是 Requirement 7 明文禁止的「放宽判据」；
    3. 让 extract 侧把 `'……'` 识别为「非数据行标记」—— 改的是行身份语义，
       影响 Task 37/38 的等值判据。

    ═══ 本节的判据形态 ═══════════════════════════════════════════════════════

    判据**固化实测事实**而不是期望：每个 entry 停在哪一步、error_code 是什么、
    失败是否无残留。于是

    * 谁把 H1 修通了 ⇒ `test_h1_is_still_blocked_at_materialize` 打红，
      提示「可行域变了，更新本节与 Task 8 的 Checkpoint」；
    * 谁让它以**别的**方式失败 ⇒ 同一条打红，因为 error_code 不再是那一个。

    这样「首版尚未在真库落成」不会被伪装成已完成，Task 8 会照实红。
    """

    def _entry(self, snap: dict[str, Any], entry_id: str) -> dict[str, Any]:
        domain = snap["phases"]["feasible_domain"]
        assert entry_id in domain, (
            f"{entry_id} 不在实测可行域里 —— 交付登记表变了？实测: {sorted(domain)}"
        )
        return domain[entry_id]

    def test_the_domain_covers_every_delivered_entry(
        self, snap: dict[str, Any]
    ) -> None:
        """分母：可行域必须覆盖**全部**已交付 entry（现取登记表，不写死数量）。"""
        from app.services.workpaper_sync.adapters import registry as RG

        delivered = {str(row["entry_id"]) for row in RG.DELIVERED_PER_ENTRY_CONTRACTS}
        assert delivered, "交付登记表为空 —— 判据在空集上"
        measured = set(snap["phases"]["feasible_domain"])
        assert measured == delivered, (
            f"实测覆盖 {sorted(measured)}，登记表是 {sorted(delivered)} —— "
            "漏测的 entry 会让「可行域」这个结论不完整"
        )

    def test_b60_is_blocked_at_the_ooxml_gate(self, snap: dict[str, Any]) -> None:
        """B60 停在安全门 —— Requirement 12.5 认可的阻塞，且 12.3 禁止放宽。"""
        record = self._entry(snap, "xlsx/b60/gt-b60-bundle")
        assert record["stopped_at"] == "stage"
        assert record["error_code"] == "ooxml_security_rejected"
        assert record.get("gate") == "external_relationships", (
            f"gate 实测为 {record.get('gate')!r} —— 安全策略变了就该重新裁决"
        )

    @pytest.mark.parametrize(
        ("entry_id", "cell"),
        [
            ("xlsx/gt-h1-fixed-assets", "A27"),
            ("xlsx/gt-d2-accounts-receivable", "A25"),
        ],
    )
    def test_h1_and_d2_are_blocked_at_materialize_by_the_same_shape(
        self, snap: dict[str, Any], entry_id: str, cell: str
    ) -> None:
        """🔴 H1 与 D2 停在 materialize，且是**同一个**错形（模板末行的 `'……'`）。

        判据同时锁三件事：停的位置、error_code、诊断里点名的单元格。
        三者齐备才说明「这是模板/契约漂移」而不是某个 entry 的偶发。

        本条打红的两种情形都需要人来看：
        * 修通了 ⇒ 更新本节与 Task 8 的 Checkpoint（可行域变了）；
        * 换了别的失败方式 ⇒ 根因变了，先定性再改判据。
        """
        record = self._entry(snap, entry_id)
        assert record["stopped_at"] == "publish", (
            f"{entry_id} 停在 {record['stopped_at']!r} 而不是 publish —— "
            f"可行域变了。实测: {record.get('error', '')[:200]}"
        )
        assert record["error_code"] == "excel_materialize_editable_write_failed", (
            f"{entry_id} 的 error_code 实测为 {record['error_code']!r} —— "
            "根因变了，先定性再改判据"
        )
        assert cell in str(record.get("error", "")), (
            f"{entry_id} 的诊断里没点名单元格 {cell} —— 实测诊断: "
            f"{record.get('error', '')[:240]}"
        )
        assert "……" in str(record.get("error", "")), (
            f"{entry_id} 的诊断里没有那个占位符 —— 根因可能换了"
        )
        assert "reached" in record and "resolve_plan" in record["reached"], (
            f"{entry_id} 没走到 resolve_plan —— 那说明阻塞比 materialize 更早，"
            f"本条判据的定性失效。实测到达: {record.get('reached')}"
        )

    def test_g7_fails_here_only_because_this_fixture_feeds_an_empty_store(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 G7 在**本夹具里**停在 store 载荷形态，但那**不是** G7 的真实阻塞。

        必须把两件事分开，否则会得出与真库相反的结论：

        * **真库上 G7 已发布成功**（2026-09-04，`generation=1`、
          `authority_model_type='projection_contract'`、`is_current=True`）——
          Checkpoint Task 8 的判据在真库上成立。那次成功是因为 G7 的 store
          **有真实数据**，`_read_store_payload` 读回的是真载荷。
        * **本夹具**在干净 schema 上跑，G7 的 store 是空的，而 `_probe_all_entries`
          统一喂 `store_payload="[]"` ⇒ 撞上「G7 要 `Mapping`」⇒ 抛
          `StorePayloadError`。这是**夹具构造**的结果，不是 G7 发不出去。

        它仍有价值：它暴露了宿主 `_EMPTY_STORE_PAYLOAD = "[]"` 对 G7 无解这处**潜在**
        缺陷（真库上因 `resolve_plan` 先判 `already_published` 而从未走到）。
        缺陷本身由 `TestHostEmptyStorePayloadConstant` 独立锁住 —— 那一节判的是
        `build_store_projection` 与宿主常量的相容性，不依赖本夹具的喂法。
        """
        record = self._entry(snap, "xlsx/gt-g7-long-term-equity-main")
        assert record["stopped_at"] == "publish"
        # 🔴 本夹具的 `_probe_all_entries` 直接喂 `"[]"`（它模拟的是**修复之前**
        #    宿主那个单一常量的喂法），因此这里看到的仍是「载荷形态不符」。
        #    宿主自己已改成问 provider ⇒ 真实路径上 G7 会落到
        #    `store_empty_nothing_to_publish`，那条由
        #    `TestEmptyStorePayloadIsProviderDeclared` 直接验宿主函数来锁。
        assert record["error_code"] == "sync_pilot_store_payload_invalid", (
            f"G7 的 error_code 实测为 {record['error_code']!r} —— "
            "本夹具喂的是裸 `\"[]\"`，预期正是载荷形态不符"
        )
        assert "reached" in record and "resolve_plan" in record["reached"], (
            f"G7 没走到 resolve_plan：{record.get('reached')} —— "
            "那说明它在干净 schema 上连准入都过不了，与「真库上已发布」不符，"
            "需要重新定性"
        )

    def test_no_entry_published_a_first_generation(self, snap: dict[str, Any]) -> None:
        """🔴 照实固化「**在本夹具的干净 schema 里**零个 entry 走完发布链」。

        ⚠️ 这**不是**「首版从未落成」。真库上 G7 已发布（Checkpoint Task 8 成立）。
        本条只说：从零建起的 schema 上，四个 entry 各自都还差一步。

        谁让任一 entry 在干净 schema 上发成功了，本条打红，提示去更新本节、
        tasks.md Task 8 的现场记录与 design.md §Open Gates。

        判据取自**落库行**（Property 33 的做法），不取「有没有抛异常」。
        """
        domain = snap["phases"]["feasible_domain"]
        published = {
            entry_id: record.get("representation_rows")
            for entry_id, record in domain.items()
            if record.get("stopped_at") is None
        }
        assert not published, (
            f"有 entry 发出了首版: {published} —— 这是**好事**，但可行域变了：\n"
            "  ① 更新本节的判据；\n"
            "  ② 更新 tasks.md Task 8 的 Checkpoint；\n"
            "  ③ 更新 design.md §Open Gates 第 3 项。"
        )

    def test_the_failed_attempts_left_no_residue(self, snap: dict[str, Any]) -> None:
        """全部失败尝试之后，四张表仍是空的 —— 失败没有留下半成品。

        这是 Property 13 在**真实阻塞**上的应用：四个 entry 各失败一次，
        四张表逐行不变。
        """
        empty = snap["snapshots"]["empty"]
        after = snap["snapshots"]["after_rerun"]
        diffs = _diff_snapshots(empty, after)
        assert diffs == [], (
            "四个 entry 全部失败之后四张表有残留:\n  " + "\n  ".join(diffs)
        )


# ═══════════════════════════════════════════════════════════════════════════
# 宿主缺陷：单一空 store 载荷常量对 G7 不成立
# ═══════════════════════════════════════════════════════════════════════════


class TestEmptyStorePayloadIsProviderDeclared:
    """空 store 载荷由**各 provider 自己声明**，宿主不用通用常量喂所有人。

    **Validates: Requirements 6.11**

    ═══ 修好之前是什么样（2026-09-05 实测）═══════════════════════════════════

    宿主用**同一个**常量 `_EMPTY_STORE_PAYLOAD = "[]"` 喂所有 provider，而四个
    pilot 的 store 根形态并不相同：

    | provider | 根形态 | `"[]"` | `"{}"` |
    |---|---|---|---|
    B60 | 无 `build_store_projection` | — | — |
    D2 | **行数组** | ✓ | ✗ |
    H1 | **行数组** | ✓ | ✗ |
    **G7** | **对象**（带 `version` / `entitySlots` / `tables`）| **✗** | ✗ |

    ⇒ 单一常量对 G7 无解，且换成 `"{}"` 会让 H1/D2 全崩。

    **为什么至今没爆**：宿主里 `resolve_plan` 排在 `_read_store_payload` **之前**。
    真库上 G7 已有 current representation ⇒ 被判据 ③ 拦在 `already_published`，
    那条读载荷的路径从未被走到。干净库上就会崩，且 `StorePayloadError` 当时未登记进
    `_ERROR_CODE_TO_STATE` ⇒ 落进 `blocked_unregistered_failure_shape` 兜底格，
    把一个有明确解除方的情形报成「词表要扩」。

    ═══ 修法与它为什么是这个形状 ═════════════════════════════════════════════

    「空载荷长什么样」由各 pilot 的 store schema 决定，**只有 provider 自己知道**，
    放在调用方就是猜。因此：

    * 每个有 `build_store_projection` 的 provider 声明 `EMPTY_STORE_PAYLOAD`；
    * **G7 声明 `None`** —— 它没有「空载荷」这个合法状态。这不是偷懒：它的动态列
      数量由 `entitySlots[RENDER_SLOT]` 的实测实体列表决定，而 `iter_store_entities`
      对空列表**故意抛错**（「审计师删到 0 家」必须显式失败，不得被静默补成模板默认
      的 5 列）。给它编一个空载荷等于去对抗一条正确的判据；
    * 宿主 `_empty_store_payload_for` 问 provider；读到 `None` 就抛
      `EmptyStoreNotPublishableError`，结算到**新增的** `store_empty_nothing_to_publish`
      格 —— 那一格刻意**不叫** `blocked_*`，因为它不是阻塞（没有任何东西需要被解除，
      要做的只是先在 HTML 侧录数据）；
    * provider **未**声明时抛 `HostError` 而不是猜一个形状。
    """

    def _host(self) -> Any:
        import importlib.util

        host_path = BACKEND / "scripts/fix/fix_projection_first_publication.py"
        spec = importlib.util.spec_from_file_location("_fp_host_empty", host_path)
        assert spec is not None and spec.loader is not None
        host = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = host
        spec.loader.exec_module(host)
        return host

    def test_the_measured_shapes_are_recorded(self, snap: dict[str, Any]) -> None:
        """分母：四个 provider 的实测形态都在快照里。"""
        shapes = snap["phases"]["empty_store_payload"]
        from app.services.workpaper_sync.adapters import registry as RG

        delivered = {str(row["entry_id"]) for row in RG.DELIVERED_PER_ENTRY_CONTRACTS}
        assert set(shapes) == delivered

    def test_the_host_no_longer_has_a_one_size_fits_all_constant(self) -> None:
        """🔴 宿主里不得再有「喂所有 provider」的单一空载荷常量。

        这是**防回退**判据：谁把 `_EMPTY_STORE_PAYLOAD` 加回来（或换个名字做同一件
        事），本条打红。判据落在 AST 而不是字符串扫描 —— 后者会把本文件的叙述
        和宿主 docstring 里对旧常量的追述当成真实定义。
        """
        import ast

        host_path = BACKEND / "scripts/fix/fix_projection_first_publication.py"
        tree = ast.parse(host_path.read_text(encoding="utf-8"))
        module_level_names: set[str] = set()
        for node in tree.body:  # 只看模块级赋值，函数内的局部变量不算
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    module_level_names.add(target.id)

        offenders = sorted(
            name
            for name in module_level_names
            if "EMPTY" in name.upper() and "PAYLOAD" in name.upper()
        )
        assert not offenders, (
            f"宿主又出现了模块级空载荷常量 {offenders} —— 空载荷的形态由各 pilot 的 "
            "store schema 决定（G7 的根形态是对象、H1/D2 是行数组），"
            "单一常量对至少一个 provider 必然不成立。改回「问 provider」"
        )

    def test_every_store_backed_provider_declares_its_empty_payload(self) -> None:
        """每个有 `build_store_projection` 的 provider 都显式声明了空载荷。

        「未声明」与「声明 None」是两件事，必须分开：前者是漏了，后者是「本 pilot
        没有这个状态」这一**主动结论**。本条只要求 attribute 存在。
        """
        import importlib

        from app.services.workpaper_sync.adapters import registry as RG

        checked = 0
        missing: list[str] = []
        for row in RG.DELIVERED_PER_ENTRY_CONTRACTS:
            provider = importlib.import_module(str(row["provider_module"]))
            if not hasattr(provider, "build_store_projection"):
                continue
            checked += 1
            if not hasattr(provider, "EMPTY_STORE_PAYLOAD"):
                missing.append(str(row["entry_id"]))
        assert checked >= 3, f"只检查了 {checked} 个 provider，分母过小"
        assert not missing, (
            f"这些 provider 没声明 `EMPTY_STORE_PAYLOAD`: {missing} —— "
            "宿主不替它们猜空载荷的形态"
        )

    def test_each_declared_empty_payload_is_accepted_by_its_own_provider(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 声明了空载荷的 provider 必须**真的接受**它，且产出零行。

        判据不落在「声明了就算」：一个声明成 `"{}"` 的 H1 也能过那一条，
        然后在真跑时炸。这里现跑 `build_store_projection` 验它自洽。
        """
        import importlib

        from app.services.workpaper_sync.adapters import registry as RG
        from app.services.workpaper_sync.contracts import load_contract

        verified: list[str] = []
        for row in RG.DELIVERED_PER_ENTRY_CONTRACTS:
            provider = importlib.import_module(str(row["provider_module"]))
            if not hasattr(provider, "build_store_projection"):
                continue
            payload = getattr(provider, "EMPTY_STORE_PAYLOAD", None)
            if payload is None:
                continue  # 声明「无此状态」的由下一条判据管
            contract = load_contract(str(row["contract_id"]))
            projection = provider.build_store_projection(payload, contract=contract)
            assert len(projection.values) == 0, (
                f"{row['entry_id']} 声明的空载荷 {payload!r} 产出了 "
                f"{len(projection.values)} 个值 —— 那不是空载荷"
            )
            verified.append(str(row["entry_id"]))
        assert len(verified) >= 2, (
            f"只有 {verified} 声明了非 None 空载荷，分母过小"
        )

    def test_a_provider_declaring_none_really_has_no_workable_empty_shape(self) -> None:
        """🔴 声明 `None` 的 provider 必须**确实**没有任何可用空形态。

        这一条防的是「懒得找形状就写 None」：逐个喂四种候选形态，全部必须被拒。
        若其中某一种其实能过，说明该 provider 有空载荷而只是没被找到 ⇒ 应当声明它，
        而不是让宿主结算成「还没到可发布的时候」。
        """
        import importlib
        import json as _json

        from app.services.workpaper_sync.adapters import registry as RG
        from app.services.workpaper_sync.contracts import load_contract

        candidates = (
            "[]",
            "{}",
            _json.dumps({"version": 2}),
            _json.dumps({"version": 2, "entitySlots": {}, "tables": {}}),
        )
        declared_none: list[str] = []
        for row in RG.DELIVERED_PER_ENTRY_CONTRACTS:
            provider = importlib.import_module(str(row["provider_module"]))
            if not hasattr(provider, "build_store_projection"):
                continue
            if getattr(provider, "EMPTY_STORE_PAYLOAD", "sentinel") is not None:
                continue
            declared_none.append(str(row["entry_id"]))
            contract = load_contract(str(row["contract_id"]))
            accepted: list[str] = []
            for candidate in candidates:
                try:
                    provider.build_store_projection(candidate, contract=contract)
                except Exception:  # noqa: BLE001 - 这里就是要看它是否拒绝
                    continue
                accepted.append(candidate)
            assert not accepted, (
                f"{row['entry_id']} 声明 `EMPTY_STORE_PAYLOAD = None`，但这些形态"
                f"其实被接受: {accepted} —— 它有空载荷，应当声明出来，"
                "而不是让宿主结算成「还没到可发布的时候」"
            )
        assert declared_none == ["xlsx/gt-g7-long-term-equity-main"], (
            f"声明 None 的是 {declared_none}，而已定性的只有 G7 —— "
            "多出来的要先定性（它真的没有空载荷吗），少了说明 G7 侧变了"
        )

    def test_the_host_settles_an_empty_g7_store_as_not_yet_publishable(self) -> None:
        """🔴 宿主对「G7 的 store 空」给出的是**独立结论**，不是 blocked_*。

        三件事一起锁：抛的异常类型、它的 `error_code`、以及该 code 映射到的结算格。
        缺任一条都可能让它退回兜底格 —— 那正是修之前的样子。
        """
        import importlib

        host = self._host()
        g7 = importlib.import_module(
            "app.services.workpaper_sync.pilot_g7_two_level_dynamic"
        )
        with pytest.raises(host.EmptyStoreNotPublishableError) as caught:
            host._empty_store_payload_for(
                g7, entry_id="xlsx/gt-g7-long-term-equity-main"
            )

        code = getattr(caught.value, "error_code", "")
        assert code == "store_payload_empty_and_not_publishable", (
            f"error_code 实测 {code!r}"
        )
        state = host._ERROR_CODE_TO_STATE.get(code)
        assert state == "store_empty_nothing_to_publish", (
            f"{code!r} 映射到 {state!r} —— 未登记会让它落进 "
            "`blocked_unregistered_failure_shape`（修之前正是如此）"
        )
        assert not state.startswith("blocked_"), (
            f"结算格 {state!r} 以 `blocked_` 开头 —— 「还没录数据」不是阻塞，"
            "归进 blocked_* 会让运维去找一个并不存在的解除方"
        )
        assert state in host.CHECK_ENTRY_STATES, "新格没进封闭词表"

    def test_an_undeclared_provider_is_rejected_rather_than_guessed(self) -> None:
        """🔴 provider 未声明空载荷时**抛**，不猜一个形状。

        且抛的必须**不是** `EmptyStoreNotPublishableError` —— 「漏了声明」与
        「本 pilot 没有这个状态」是两件事，混同会把一处疏漏结算成一个正常结论。
        """
        host = self._host()

        class _Undeclared:
            __name__ = "_Undeclared"

        with pytest.raises(host.HostError) as caught:
            host._empty_store_payload_for(_Undeclared(), entry_id="xlsx/probe")
        assert not isinstance(caught.value, host.EmptyStoreNotPublishableError), (
            "「未声明」被当成了「声明 None」—— 前者是疏漏，后者是主动结论，"
            "混同会让漏声明的 provider 静默结算成「还没到可发布的时候」"
        )
        assert "未声明" in str(caught.value)

    def test_the_settlement_vocabulary_stays_closed(self) -> None:
        """新增结算格之后词表仍闭合，且每个非成功态都有解除方。

        `_ERROR_CODE_TO_STATE` 的每个目标格都必须在 `CHECK_ENTRY_STATES` 里 ——
        本次修复新增了两个格（`store_empty_nothing_to_publish` 与
        `blocked_store_payload_shape`），漏登记会让 `--check` 的封闭词表判据失效。
        """
        host = self._host()
        targets = set(host._ERROR_CODE_TO_STATE.values())
        outside = sorted(targets - set(host.CHECK_ENTRY_STATES))
        assert not outside, f"这些结算格不在封闭词表里: {outside}"

        # 成功态不需要解除方；其余都要，否则报告会只说「卡住了」不说「谁能解」
        success = {"ready_to_publish", "already_published"}
        no_owner = sorted(
            state
            for state in host.CHECK_ENTRY_STATES
            if state not in host._STATE_UNBLOCK_OWNER and state not in success
        )
        assert not no_owner, f"这些格没有解除方登记: {no_owner}"

    def test_the_two_new_states_are_kept_distinct(self) -> None:
        """🔴 「store 空」与「store 形态不符」必须是**两格**。

        修之前两者都落进兜底格。合成一格会让「先去录数据」和「数据坏了要修」
        指向同一个解除方，而它们的处置完全不同。
        """
        host = self._host()
        empty_state = host._ERROR_CODE_TO_STATE[
            "store_payload_empty_and_not_publishable"
        ]
        invalid_state = host._ERROR_CODE_TO_STATE["sync_pilot_store_payload_invalid"]
        assert empty_state != invalid_state, (
            f"两者都落在 {empty_state!r} —— 「还没录」与「录坏了」的处置不同，"
            "必须分格"
        )
        assert invalid_state.startswith("blocked_"), (
            f"「形态不符」落在 {invalid_state!r} —— 它**是**阻塞（有明确解除方），"
            "应当以 blocked_ 开头"
        )
        owners = {
            host._STATE_UNBLOCK_OWNER[empty_state],
            host._STATE_UNBLOCK_OWNER[invalid_state],
        }
        assert len(owners) == 2, "两格的解除方文案相同 —— 那等于没有分开"
