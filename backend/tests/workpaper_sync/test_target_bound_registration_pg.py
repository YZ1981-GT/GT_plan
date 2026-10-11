"""R14 真库判据：同一 entry 的两家企业交替请求，各自的 adapter 绑在**自己**的 representation 上。

spec: d2-online-edit-platform-closure · R14

═══ 为什么要真库 + 真 D2 provider + 真首版发布 ═══

零库那份（``test_target_bound_registration.py``）证的是编排：pin / 缓存 / 换绑 / 三种绑不上。
它证不了「真 provider 在 pin 下真的读到了目标底稿的 representation、真观测器真的冻出了
那一份的行身份清册、真 store-projection 真的不再 422」—— 真实故障就出在这条链的**数据**上：
重药安徽 store-projection 422「OO 往返后丢失 729 个 row identity，首个
'dr-mtl5bqmm-0o950ft'」（和平药房的行）。所以这里在 scratch schema 里造两家企业、各写不同的
D2 明细行、各走一次**生产**按需首版，再走**生产** ``wp_sync_router._registration``。

判据里有一条**负对照**：直接拿 entry 级注册算第二家的 store-projection 必须仍抛
``excel_extract_identity_not_retained`` —— 证明本夹具复现的就是那个故障，而不是一个
「怎么做都绿」的世界。

═══ 隔离 ═══

scratch schema ``tmp_r14_pg_<hex>`` + 临时 artifact 根；结束 ``DROP SCHEMA CASCADE`` + ``rmtree``。
D2 provider 自己 ``new CanonicalArtifactRepository(_BACKEND_ROOT)``，因此把
``phase5_entry_orchestration._BACKEND_ROOT`` 指到临时根（换的是存储根，解析 / 注册逻辑全走生产，
与 ``test_task75_published_identity_observer`` 同一处置）。全部阶段一次 ``asyncio.run`` 采集。

用法（仓库根）::

    .\\.venv\\Scripts\\python.exe -m pytest backend/tests/workpaper_sync/test_target_bound_registration_pg.py -q
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

MIGRATIONS: tuple[Path, ...] = (
    BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql",
    BACKEND / "migrations" / "V152__workpaper_content_version_upload_wopi_source.sql",
    BACKEND / "migrations" / "V153__workpaper_representation_candidate_attach_event.sql",
)
_SCHEMA_PREFIX = "tmp_r14_pg_"
ENTRY = "xlsx/gt-d2-accounts-receivable"

#: 与 `test_projection_first_publication_pg._STUB_DDL` 同形（只取被消费的列）。
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

#: V065 给 outbox enum 加过 'processing'（与 test_projection_first_publication_pg 同一处置）。
_EXTRA_ENUM_LABELS = {"import_event_outbox_status": ("processing",)}


def _rows(prefix: str, count: int) -> list[dict[str, Any]]:
    """两家企业各自的 D2 明细行：行身份互不相交 ⇒ 冻结清册必然不同。"""
    return [
        {
            "rowId": f"r14-{prefix}-{i:03d}",
            "seq": i + 1,
            "customerName": f"R14客户{prefix}{i}",
            "relationType": "非关联方",
            "priorUnadjusted": 100.0 + i,
            "currentUnadjusted": 200.0 + i,
        }
        for i in range(count)
    ]


ROWS = {"a": _rows("a", 3), "b": _rows("b", 2)}


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成「无数据」）。"""


def _err(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)[-6:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {str(exc)[:400]} @ {where}"


def _enum_ddl(tables: list[Any], sa: Any) -> list[str]:
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


def _projection_row_ids(response: dict[str, Any]) -> dict[str, bool]:
    keys = list(((response.get("projection") or {}).get("values") or {}).keys())
    joined = "\n".join(keys)
    return {
        "has_a": any(row["rowId"] in joined for row in ROWS["a"]),
        "has_b": any(row["rowId"] in joined for row in ROWS["b"]),
        "value_count": len(keys),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 一次采集：schema → 三家企业 → provision → 两次生产首版 → 生产 _registration 交替
# ═══════════════════════════════════════════════════════════════════════════


async def _setup_schema(engine: Any, sa: Any) -> None:
    from app.core.migration_runner import MigrationRunner
    from app.models.dataset_models import ImportEventConsumption, ImportEventOutbox

    async with engine.begin() as conn:
        for stmt in [s.strip() for s in _STUB_DDL.strip().split(";") if s.strip()]:
            await conn.exec_driver_sql(stmt)
    for migration in MIGRATIONS:
        if not migration.exists():
            raise _HarnessError(f"缺少迁移文件: {migration}")
        for stmt in MigrationRunner._split_sql_statements(migration.read_text(encoding="utf-8")):
            async with engine.begin() as conn:
                await conn.exec_driver_sql(stmt)
    # ContentMutationService.commit 第五步写 outbox；V151~V153 不建这两张表 ⇒ 从 ORM 补齐。
    outbox_tables = [ImportEventOutbox.__table__, ImportEventConsumption.__table__]
    async with engine.begin() as conn:
        for stmt in _enum_ddl(outbox_tables, sa):
            await conn.exec_driver_sql(stmt)
        await conn.run_sync(
            lambda sync_conn: ImportEventOutbox.metadata.create_all(
                sync_conn, tables=outbox_tables, checkfirst=True
            )
        )


async def _seed_companies(engine: Any, sa: Any) -> tuple[dict[str, dict[str, uuid.UUID]], uuid.UUID]:
    """三家企业：a（先建，全序第一）、b（第二家，R14 的受害者）、c（未发首版）。"""
    from app.services.workpaper_sync import pilot_d2_large_json as D2
    from app.services.workpaper_sync.projection_target_resolution import adjudicated_wp_codes

    code = adjudicated_wp_codes(ENTRY)[0]
    base = datetime.now(timezone.utc) - timedelta(days=1)
    actor = uuid.uuid4()
    ids: dict[str, dict[str, uuid.UUID]] = {}
    async with engine.begin() as conn:
        await conn.execute(sa.text("INSERT INTO users (id) VALUES (:u)"), {"u": actor})
        for offset, label in enumerate(("a", "b", "c")):
            project, index, wp = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            await conn.execute(
                sa.text("INSERT INTO projects (id, name) VALUES (:p, :n)"),
                {"p": project, "n": f"r14-{label}"},
            )
            await conn.execute(
                sa.text("INSERT INTO wp_index (id, wp_code) VALUES (:i, :c)"),
                {"i": index, "c": code},
            )
            await conn.execute(
                sa.text(
                    "INSERT INTO working_paper (id, project_id, wp_index_id, created_at) "
                    "VALUES (:w, :p, :i, :t)"
                ),
                {"w": wp, "p": project, "i": index, "t": base + timedelta(minutes=offset)},
            )
            if label in ROWS:
                await conn.execute(
                    sa.text(
                        "INSERT INTO checklist_responses (id, wp_id, item_id, remark) "
                        "VALUES (:id, :w, :item, :remark)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "w": wp,
                        "item": D2.STORE_ITEM_ID,
                        "remark": json.dumps(ROWS[label], ensure_ascii=False),
                    },
                )
            ids[label] = {"project": project, "wp": wp}
    return ids, actor


async def _publish_both(
    Session: Any, sa: Any, *, ids: dict[str, dict[str, uuid.UUID]], actor: uuid.UUID, artifacts: Any
) -> dict[str, dict[str, str]]:
    from app.services.workpaper_sync import projection_provisioning as PP
    from app.services.workpaper_sync.first_publication_on_demand import ensure_first_publication
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    async with Session() as session:
        await PP.ProjectionDefinitionProvisioner(
            session=session,
            repository=WorkpaperSyncRepository(session),
            artifacts=artifacts,
            project_id=ids["a"]["project"],
            wp_id=ids["a"]["wp"],
        ).ensure(entry_id=ENTRY)
        await session.commit()
    reps: dict[str, dict[str, str]] = {}
    for label in ("a", "b"):
        async with Session() as session:
            outcome = await ensure_first_publication(
                session=session,
                resolution=CanonicalResolutionService(session, artifacts),
                artifacts=artifacts,
                repository=WorkpaperSyncRepository(session),
                project_id=ids[label]["project"],
                wp_id=ids[label]["wp"],
                entry_id=ENTRY,
                actor_id=actor,
            )
            await session.commit()
        async with Session() as session:
            row = (
                await session.execute(
                    sa.text(
                        "SELECT id, identity_inventory_sha256 "
                        "FROM working_paper_content_representation WHERE id = :r"
                    ),
                    {"r": uuid.UUID(outcome.representation_id)},
                )
            ).first()
        reps[label] = {
            "status": outcome.status,
            "id": str(row.id),
            "inventory": str(row.identity_inventory_sha256).strip(),
        }
    return reps


def _inventory_of(registration: Any) -> str:
    return str(registration.adapter.definitions.as_dict()["identity_inventory_sha256"])


async def _exercise_registrations(
    Session: Any, engine: Any, sa: Any, *, ids: dict[str, dict[str, uuid.UUID]], artifacts: Any,
    snap: dict[str, Any],
) -> None:
    from fastapi import HTTPException

    from app.routers import wp_sync_router as SR
    from app.services.workpaper_sync import target_bound_registration as TB
    from app.services.workpaper_sync.adapters.registry import build_production_registry
    from app.services.workpaper_sync.resolution import CanonicalResolutionService
    from app.services.workpaper_sync.store_projection_response import (
        compute_store_projection_response,
    )

    async def projection(session: Any, label: str, registration: Any) -> dict[str, Any]:
        return await compute_store_projection_response(
            session=session,
            project_id=ids[label]["project"],
            wp_id=ids[label]["wp"],
            entry_id=ENTRY,
            registration=registration,
            resolution=CanonicalResolutionService(session, artifacts),
        )

    # ── ① entry 级注册（生产 _attach_pilot_adapters）+ 负对照 ────────────────
    async with Session() as session:
        registry = build_production_registry()
        await SR._attach_pilot_adapters(
            SR._RegistrationWarmupContext(session=session, registry=registry)
        )
        entry_level = registry.resolve_for_entry(ENTRY)
        snap["phases"]["entry_level_inventory"] = _inventory_of(entry_level)
        try:
            await projection(session, "b", entry_level)
            snap["phases"]["negative_control"] = {"raised": False}
        except Exception as exc:  # noqa: BLE001 - 负对照：必须抛
            snap["phases"]["negative_control"] = {
                "raised": True,
                "type": type(exc).__name__,
                "error_code": str(getattr(exc, "error_code", "") or ""),
                "message": str(exc)[:300],
            }

    # ── ② 生产 _registration：b → a → b → a 交替 ───────────────────────────
    steps: list[dict[str, Any]] = []
    for label in ("b", "a", "b", "a"):
        async with Session() as session:
            svc = SimpleNamespace(session=session, registry=build_production_registry())
            scope = SimpleNamespace(entry_id=ENTRY, wp_id=ids[label]["wp"])
            started = time.perf_counter()
            registration = await SR._registration(svc, scope)
            seconds = round(time.perf_counter() - started, 3)
            response = await projection(session, label, registration)
            steps.append(
                {
                    "label": label,
                    "inventory": _inventory_of(registration),
                    "object_id": id(registration),
                    "entry_registrations": sum(
                        1 for reg in svc.registry.registrations() if reg.entry_id == ENTRY
                    ),
                    "request_registry_holds_it": svc.registry.resolve_for_entry(ENTRY)
                    is registration,
                    "rows": _projection_row_ids(response),
                    "seconds": seconds,
                }
            )
    snap["phases"]["steps"] = steps

    # ── ③ 未发首版的第三家：沿用 entry 级 ─────────────────────────────────
    async with Session() as session:
        svc = SimpleNamespace(session=session, registry=build_production_registry())
        registration = await SR._registration(
            svc, SimpleNamespace(entry_id=ENTRY, wp_id=ids["c"]["wp"])
        )
        snap["phases"]["unpublished_inventory"] = _inventory_of(registration)

    # ── ④ 目标底稿所在项目被软删：fail closed，不退回别家 ──────────────────────
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("UPDATE projects SET is_deleted = true WHERE id = :p"),
            {"p": ids["b"]["project"]},
        )
    TB.clear_target_registration_cache()
    try:
        async with Session() as session:
            svc = SimpleNamespace(session=session, registry=build_production_registry())
            try:
                await SR._registration(
                    svc, SimpleNamespace(entry_id=ENTRY, wp_id=ids["b"]["wp"])
                )
                snap["phases"]["invisible"] = {"raised": False}
            except HTTPException as exc:
                snap["phases"]["invisible"] = {
                    "raised": True,
                    "status": exc.status_code,
                    "error_code": str((exc.detail or {}).get("error_code")),
                    "message": str((exc.detail or {}).get("message"))[:300],
                }
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("UPDATE projects SET is_deleted = false WHERE id = :p"),
                {"p": ids["b"]["project"]},
            )

    # ── ⑤ R15：同 bundle 新代际不改指纹、不冷建；绑定跟到新代际；首版发布改指纹 ──────
    await _exercise_generation_bump(Session, engine, sa, ids=ids, artifacts=artifacts, snap=snap)


async def _fingerprint_now(Session: Any) -> str:
    from app.routers import wp_sync_router as SR
    from app.services.workpaper_sync.adapters.registry import build_production_registry

    async with Session() as session:
        return await SR._registration_state_fingerprint(
            SR._RegistrationWarmupContext(session=session, registry=build_production_registry())
        )


async def _exercise_generation_bump(
    Session: Any, engine: Any, sa: Any, *, ids: dict[str, dict[str, uuid.UUID]], artifacts: Any,
    snap: dict[str, Any],
) -> None:
    from app.routers import wp_sync_router as SR
    from app.services.workpaper_sync import target_bound_registration as TB
    from app.services.workpaper_sync.adapters.registry import build_production_registry
    from app.services.workpaper_sync.first_publication_on_demand import ensure_first_publication
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService
    from app.services.workpaper_sync.store_projection_response import (
        compute_store_projection_response,
    )

    fp_before = await _fingerprint_now(Session)
    snapshot_before = SR._REGISTRATION_CACHE.get(fp_before)
    old_rep = uuid.UUID(snap["phases"]["published"]["a"]["id"])
    new_rep = uuid.uuid4()
    # 一次「保存」在数据层的样子：同 content version、同 bundle、同 artifact 的下一代 representation，
    # current pointer 移过去（与 materialize / OO→HTML 落新代际同形，bundle 不变）。
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO working_paper_content_representation (id, wp_id, content_version_id, "
                "entry_id, generation, parent_representation_id, document_type, artifact_id, "
                "artifact_sha256, definition_bundle_id, definition_bundle_sha256, "
                "authority_model_definition_id, authority_model_definition_sha256, adapter_id, "
                "adapter_build_digest, structure_hash, identity_inventory_sha256, reason) "
                "SELECT :new, wp_id, content_version_id, entry_id, generation + 1, id, "
                "document_type, artifact_id, artifact_sha256, definition_bundle_id, "
                "definition_bundle_sha256, authority_model_definition_id, "
                "authority_model_definition_sha256, adapter_id, adapter_build_digest, "
                "structure_hash, identity_inventory_sha256, 'rematerialize' "
                "FROM working_paper_content_representation WHERE id = :old"
            ),
            {"new": new_rep, "old": old_rep},
        )
        await conn.execute(
            sa.text(
                "UPDATE working_paper_sync_entry_state SET current_representation_id = :new, "
                "representation_generation = representation_generation + 1 "
                "WHERE wp_id = :wp AND entry_id = :e"
            ),
            {"new": new_rep, "wp": ids["a"]["wp"], "e": ENTRY},
        )
    fp_after_bump = await _fingerprint_now(Session)
    async with Session() as session:
        svc = SimpleNamespace(session=session, registry=build_production_registry())
        registration = await SR._registration(
            svc, SimpleNamespace(entry_id=ENTRY, wp_id=ids["a"]["wp"])
        )
        response = await compute_store_projection_response(
            session=session,
            project_id=ids["a"]["project"],
            wp_id=ids["a"]["wp"],
            entry_id=ENTRY,
            registration=registration,
            resolution=CanonicalResolutionService(session, artifacts),
        )
    bump = {
        "fingerprint_unchanged": fp_after_bump == fp_before,
        "global_snapshot_reused": snapshot_before is not None
        and SR._REGISTRATION_CACHE.get(fp_before) is snapshot_before,
        "bound_to_new_generation": TB.TARGET_REGISTRATION_CACHE.get((ENTRY, str(new_rep)))
        is registration,
        "rows": _projection_row_ids(response),
    }
    async with Session() as session:
        await ensure_first_publication(
            session=session,
            resolution=CanonicalResolutionService(session, artifacts),
            artifacts=artifacts,
            repository=WorkpaperSyncRepository(session),
            project_id=ids["c"]["project"],
            wp_id=ids["c"]["wp"],
            entry_id=ENTRY,
            actor_id=None,
        )
        await session.commit()
    bump["first_publication_changes_fingerprint"] = (
        await _fingerprint_now(Session)
    ) != fp_after_bump
    snap["phases"]["generation_bump"] = bump


async def _collect() -> dict[str, Any]:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.routers import wp_sync_router as SR
    from app.services.workpaper_sync import phase5_entry_orchestration as ORCH
    from app.services.workpaper_sync import target_bound_registration as TB
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.parse_cache import BoundedLruCache, clear_all_parse_caches

    if not str(settings.DATABASE_URL).startswith("postgresql"):
        raise _HarnessError(
            "R14 的判据是「真 provider + 真首版 + 真 store-projection 在两家企业上各自成立」，"
            "必须真实 PostgreSQL。此处**不 skip** —— skip 等于把「没验证」记成「通过」"
        )
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_r14_pg_store_"))
    (base_root / "storage").mkdir(exist_ok=True)
    (base_root / "definition_store").mkdir(exist_ok=True)
    snap: dict[str, Any] = {"schema": schema, "errors": {}, "phases": {}}
    saved = (ORCH._BACKEND_ROOT, SR._REGISTRATION_CACHE, SR._REGISTRATION_BUILD_LOCK)
    admin = create_async_engine(
        str(settings.DATABASE_URL), poolclass=NullPool, connect_args=dict(ssl_off)
    )
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
        artifacts = CanonicalArtifactRepository(base_root)
        await _setup_schema(engine, sa)
        ids, actor = await _seed_companies(engine, sa)
        snap["phases"]["published"] = await _publish_both(
            Session, sa, ids=ids, actor=actor, artifacts=artifacts
        )
        # 存储根换到临时根；注册缓存 / 绑定缓存 / 解析缓存全部从空开始。
        ORCH._BACKEND_ROOT = base_root
        SR._REGISTRATION_CACHE = BoundedLruCache(maxsize=8)
        SR._REGISTRATION_BUILD_LOCK = None
        TB.clear_target_registration_cache()
        clear_all_parse_caches()
        await _exercise_registrations(
            Session, engine, sa, ids=ids, artifacts=artifacts, snap=snap
        )
    except Exception as exc:  # noqa: BLE001 - 记录不穿透，由守卫断言为空
        snap["errors"]["collect"] = _err(exc)
    finally:
        ORCH._BACKEND_ROOT, SR._REGISTRATION_CACHE, SR._REGISTRATION_BUILD_LOCK = saved
        TB.clear_target_registration_cache()
        clear_all_parse_caches()
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
# 判据
# ═══════════════════════════════════════════════════════════════════════════


class TestHarness:
    def test_collection_did_not_crash(self, snap: dict[str, Any]) -> None:
        assert snap["errors"] == {}, snap["errors"]

    def test_both_companies_have_their_own_first_publication(
        self, snap: dict[str, Any]
    ) -> None:
        published = snap["phases"]["published"]
        assert {published["a"]["status"], published["b"]["status"]} == {"published"}
        assert published["a"]["inventory"] != published["b"]["inventory"], (
            "两家企业的冻结行身份清册相同 —— 夹具没造出 R14 的前提（行身份必须互不相交）"
        )


class TestR14:
    def test_entry_level_registration_is_bound_to_the_first_company(
        self, snap: dict[str, Any]
    ) -> None:
        """前提：entry 级注册按全序绑第一家 —— 这正是故障的来源。"""
        assert snap["phases"]["entry_level_inventory"] == snap["phases"]["published"]["a"]["inventory"]

    def test_negative_control_reproduces_the_production_fault(
        self, snap: dict[str, Any]
    ) -> None:
        """拿 entry 级注册算第二家必须仍抛「丢失 row identity」—— 证明夹具复现的就是那个故障。"""
        control = snap["phases"]["negative_control"]
        assert control["raised"] is True, "负对照没抛 —— 这个世界里怎么做都绿，判据无效"
        assert control["error_code"] == "excel_extract_identity_not_retained", control

    def test_each_company_is_served_with_its_own_representation(
        self, snap: dict[str, Any]
    ) -> None:
        published = snap["phases"]["published"]
        for step in snap["phases"]["steps"]:
            label, other = step["label"], ("a" if step["label"] == "b" else "b")
            assert step["inventory"] == published[label]["inventory"], (
                f"{label} 的请求拿到的 adapter 冻结的是另一家的清册（R14 未修）: {step}"
            )
            assert step["rows"][f"has_{label}"] is True, step
            assert step["rows"][f"has_{other}"] is False, (
                f"{label} 的 store-projection 里出现了 {other} 的行: {step}"
            )
            assert step["entry_registrations"] == 1, step
            assert step["request_registry_holds_it"] is True, step

    def test_alternating_requests_reuse_the_binding_per_representation(
        self, snap: dict[str, Any]
    ) -> None:
        steps = snap["phases"]["steps"]
        by_label: dict[str, set[int]] = {}
        for step in steps:
            by_label.setdefault(step["label"], set()).add(step["object_id"])
        assert all(len(objects) == 1 for objects in by_label.values()), (
            f"同一 (entry, representation) 每次请求都重建了绑定注册: {by_label}"
        )
        assert by_label["a"] != by_label["b"]

    def test_unpublished_workpaper_keeps_the_entry_level_registration(
        self, snap: dict[str, Any]
    ) -> None:
        assert (
            snap["phases"]["unpublished_inventory"]
            == snap["phases"]["published"]["a"]["inventory"]
        )

    def test_invisible_target_is_refused_instead_of_rebound_to_another_company(
        self, snap: dict[str, Any]
    ) -> None:
        invisible = snap["phases"]["invisible"]
        assert invisible["raised"] is True, "目标底稿不可见却拿到了 adapter（退回了别家企业）"
        assert invisible["status"] == 422
        assert invisible["error_code"] == "adapter_target_representation_unbound", invisible
        assert "可见性" in invisible["message"], invisible


class TestR15SavesDoNotColdRebuildTheRegistry:
    """一次「保存」（同 bundle 新代际）不得让全平台 entry 级注册冷建（实测 30~38s、持全局锁）。"""

    def test_a_new_generation_keeps_the_fingerprint_and_the_cached_snapshot(
        self, snap: dict[str, Any]
    ) -> None:
        bump = snap["phases"]["generation_bump"]
        assert bump["fingerprint_unchanged"] is True, bump
        assert bump["global_snapshot_reused"] is True, (
            "同 bundle 新代际之后 entry 级注册被重建了 —— 每次保存都让所有人多等 30s"
        )

    def test_the_request_still_binds_to_the_new_generation(self, snap: dict[str, Any]) -> None:
        """不冷建 ≠ 用旧代际：绑定按目标底稿**当前**代际现建（R14）。"""
        bump = snap["phases"]["generation_bump"]
        assert bump["bound_to_new_generation"] is True, bump
        assert bump["rows"]["has_a"] is True and bump["rows"]["has_b"] is False, bump

    def test_a_first_publication_still_changes_the_fingerprint(
        self, snap: dict[str, Any]
    ) -> None:
        assert snap["phases"]["generation_bump"]["first_publication_changes_fingerprint"] is True
