# -*- coding: utf-8 -*-
"""R7 端点级真库守卫：`POST …/first-publication`（spec d2-online-edit-platform-closure）。

真发 HTTP 请求（ASGI transport）走生产 router + 生产 service + 真 PostgreSQL scratch schema，
不 mock 准入、不 mock 发布链：

| 场景 | 期望 |
|---|---|
| 未登录 | 401 |
| 无项目可见性 | 404（统一不可见响应） |
| 工作流锁定（归档/复核通过） | 403（写 action） |
| D2 空 store 首次打开 | 200 `published`，库里恰一行 representation + pointer，revision 0→1 |
| 再调一次 | 200 `already_published`，同一 representation，零新增行 |
| G7 空 store（`EMPTY_STORE_PAYLOAD is None`） | 422 `store_payload_empty_and_not_publishable`，零写入 |
| 未 provision 的 entry | 422 `projection_bundle_not_provisioned`，零写入 |

`DATABASE_URL` 非 PostgreSQL 时**直接失败而不是 skip**（skip = 把「没验证」记成「通过」）。
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import traceback
import uuid
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_MIGRATIONS = (
    _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql",
    _BACKEND / "migrations" / "V152__workpaper_content_version_upload_wopi_source.sql",
    _BACKEND / "migrations" / "V153__workpaper_representation_candidate_attach_event.sql",
)
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_first_pub_ondemand_"
D2_ENTRY = "xlsx/gt-d2-accounts-receivable"
G7_ENTRY = "xlsx/gt-g7-long-term-equity-main"
H1_ENTRY = "xlsx/gt-h1-fixed-assets"  # 刻意不 provision：准入 ② 的否定侧

#: scratch schema 的最小平台表（与 `test_projection_first_publication_pg` 同口径）。
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

#: V065 给 outbox enum 加过 'processing'（与 `test_projection_first_publication_pg` 同一处置）。
_EXTRA_ENUM_LABELS = {"import_event_outbox_status": ("processing",)}


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成「无数据」）。"""


def _err(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)[-8:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


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


class _Switchboard:
    """visibility / workflow lock 的可翻开关（与 Task 28 PG 守卫同形）。"""

    def __init__(self) -> None:
        self.project_visible = True
        self.workflow_locked = False

    async def observe(self, *, project_id: Any, wp_id: Any, entry_id: Any) -> dict[str, Any]:
        return {
            "project_visible": self.project_visible,
            "workflow_locked": self.workflow_locked,
            "readonly": self.workflow_locked,
        }

    def authorize(self, scope: Any) -> bool:
        from app.routers.wp_sync_router import _KNOWN_ACTIONS

        return str(scope.action) in _KNOWN_ACTIONS


async def _row_counts(Session: Any, *, wp_id: uuid.UUID) -> dict[str, int]:
    """首版会写到的四处（与 `test_projection_first_publication_pg._SNAPSHOT_TABLES` 同集合）。"""
    import sqlalchemy as sa

    out: dict[str, int] = {}
    async with Session() as s:
        for table in (
            "working_paper_content_version",
            "working_paper_content_representation",
            "working_paper_sync_entry_state",
        ):
            out[table] = int(
                (
                    await s.execute(
                        sa.text(f"SELECT count(*) FROM {table} WHERE wp_id = :w"),  # noqa: S608
                        {"w": wp_id},
                    )
                ).scalar_one()
            )
        out["content_revision"] = int(
            (
                await s.execute(
                    sa.text("SELECT content_revision FROM working_paper WHERE id = :w"),
                    {"w": wp_id},
                )
            ).scalar_one()
        )
    return out


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0915 - 一次采集覆盖全部场景
    import httpx
    import sqlalchemy as sa
    from fastapi import Depends, FastAPI, HTTPException
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.database import get_db
    from app.core.migration_runner import MigrationRunner
    from app.deps import get_current_user
    from app.middleware.response import ResponseWrapperMiddleware
    from app.models.dataset_models import ImportEventConsumption, ImportEventOutbox
    from app.routers import wp_sync_router as SR
    from app.services import event_bus as event_bus_module
    from app.services.workpaper_sync import projection_provisioning as PP
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.content_mutation import ContentMutationService
    from app.services.workpaper_sync.endpoint_guard import ScopeClaimCodec, SyncEndpointGuard
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.request_application import RequestApplicationService
    from app.services.workpaper_sync.resolution import CanonicalResolutionService
    from app.services.workpaper_sync.rooms import RoomService

    if not str(settings.DATABASE_URL).startswith("postgresql"):
        raise _HarnessError(
            "本守卫的判据是「真库上首版真的落成」，必须真实 PostgreSQL —— 此处不 skip"
        )
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_first_pub_ondemand_store_"))
    (base_root / "storage").mkdir(exist_ok=True)
    (base_root / "definition_store").mkdir(exist_ok=True)
    admin = create_async_engine(
        str(settings.DATABASE_URL), poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {"apply_errors": [], "harness_errors": {}, "scenarios": {}}
    bus = event_bus_module.event_bus
    previous_redis_flag = bus._redis_available
    bus._redis_available = False  # Redis 不参与判定
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
        for migration in _MIGRATIONS:
            for idx, stmt in enumerate(
                MigrationRunner._split_sql_statements(migration.read_text(encoding="utf-8")), 1
            ):
                try:
                    async with engine.begin() as conn:
                        await conn.exec_driver_sql(stmt)
                except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言为空
                    snap["apply_errors"].append(
                        {"migration": migration.name, "index": idx, "error": _err(exc)}
                    )
        if snap["apply_errors"]:
            raise _HarnessError(f"迁移应用失败: {snap['apply_errors'][:3]}")
        outbox_tables = [ImportEventOutbox.__table__, ImportEventConsumption.__table__]
        async with engine.begin() as conn:
            for stmt in _enum_ddl(outbox_tables, sa):
                await conn.exec_driver_sql(stmt)
            await conn.run_sync(
                lambda sync_conn: ImportEventOutbox.metadata.create_all(
                    sync_conn, tables=outbox_tables, checkfirst=True
                )
            )

        project, user = uuid.uuid4(), uuid.uuid4()
        wps = {name: uuid.uuid4() for name in ("d2", "g7", "h1")}
        async with engine.begin() as conn:
            await conn.execute(sa.text("INSERT INTO projects (id) VALUES (:p)"), {"p": project})
            await conn.execute(sa.text("INSERT INTO users (id) VALUES (:u)"), {"u": user})
            for wp in wps.values():
                await conn.execute(
                    sa.text("INSERT INTO working_paper (id, project_id) VALUES (:w, :p)"),
                    {"w": wp, "p": project},
                )
        snap["ids"] = {"project": str(project), **{k: str(v) for k, v in wps.items()}}

        artifacts = CanonicalArtifactRepository(base_root)
        # approved projection bundle 是 entry 全局的：D2 / G7 各 provision 一次（H1 刻意不做）。
        for entry_id, wp in ((D2_ENTRY, wps["d2"]), (G7_ENTRY, wps["g7"])):
            async with Session() as session:
                await PP.ProjectionDefinitionProvisioner(
                    session=session,
                    repository=WorkpaperSyncRepository(session),
                    artifacts=artifacts,
                    project_id=project,
                    wp_id=wp,
                ).ensure(entry_id=entry_id)
                await session.commit()

        # ═══ ASGI app：生产 router + 生产中间件；只替换 visibility 探针与 artifact 根 ═══
        board = _Switchboard()
        app = FastAPI()
        app.add_middleware(ResponseWrapperMiddleware)
        app.include_router(SR.router)

        class _User:
            def __init__(self, uid: uuid.UUID) -> None:
                self.id = uid

        current: dict[str, Any] = {"user": _User(user)}

        async def _override_db():
            async with Session() as s:
                yield s

        async def _override_user():
            if current["user"] is None:
                raise HTTPException(status_code=401, detail="未认证")
            return current["user"]

        async def _services_override(db=Depends(get_db), who=Depends(get_current_user)):
            from dataclasses import replace

            base = SR.build_sync_services(db, who)
            repo = WorkpaperSyncRepository(db)
            resolution = CanonicalResolutionService(db, artifacts)
            rooms = RoomService(repo)
            return replace(
                base,
                repo=repo,
                artifacts=artifacts,
                resolution=resolution,
                content=ContentMutationService(
                    session=db, repository=repo, artifacts=artifacts, resolution=resolution
                ),
                rooms=rooms,
                requests=RequestApplicationService(repo, rooms),
                probe=board,  # type: ignore[arg-type]
                guard=SyncEndpointGuard(
                    repository=repo,
                    visibility=board,
                    authorize=board.authorize,
                    claim_codec=ScopeClaimCodec("first-pub-ondemand-pg-secret"),
                    read_only_actions=SR._READ_ONLY_ACTIONS,
                ),
            )

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[SR._services] = _services_override

        def _url(wp: uuid.UUID, entry_id: str) -> str:
            return (
                f"/api/projects/{project}/workpapers/{wp}/sync/entries/{entry_id}"
                "/first-publication"
            )

        def _body(response: Any) -> dict[str, Any]:
            try:
                payload = response.json()
            except Exception:  # noqa: BLE001
                return {"raw": response.text[:300]}
            if isinstance(payload, dict) and "data" in payload and response.status_code < 300:
                return dict(payload["data"] or {})
            detail = payload.get("detail") if isinstance(payload, dict) else None
            return dict(detail) if isinstance(detail, dict) else {"detail": detail}

        scen = snap["scenarios"]
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://first-pub.local", timeout=600
        ) as client:

            async def _case(name: str, wp_key: str, entry_id: str) -> None:
                before = await _row_counts(Session, wp_id=wps[wp_key])
                try:
                    response = await client.post(_url(wps[wp_key], entry_id))
                    scen[name] = {
                        "status": response.status_code,
                        "body": _body(response),
                        "before": before,
                        "after": await _row_counts(Session, wp_id=wps[wp_key]),
                    }
                except Exception as exc:  # noqa: BLE001 - 记录不穿透
                    snap["harness_errors"][name] = _err(exc)

            current["user"] = None
            await _case("unauthenticated", "d2", D2_ENTRY)
            current["user"] = _User(user)

            board.project_visible = False
            await _case("invisible", "d2", D2_ENTRY)
            board.project_visible = True

            board.workflow_locked = True
            await _case("workflow_locked", "d2", D2_ENTRY)
            board.workflow_locked = False

            await _case("first_publish", "d2", D2_ENTRY)
            await _case("again", "d2", D2_ENTRY)
            await _case("empty_store_not_publishable", "g7", G7_ENTRY)
            await _case("not_provisioned", "h1", H1_ENTRY)
    except Exception as exc:  # noqa: BLE001 - 采集顶层也不穿透
        snap["harness_errors"]["collect"] = _err(exc)
    finally:
        bus._redis_available = previous_redis_flag
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except Exception as exc:  # noqa: BLE001
            snap["harness_errors"]["drop_schema"] = _err(exc)
        await admin.dispose()
        shutil.rmtree(base_root, ignore_errors=True)
    return snap


# ═══════════════════════════════════════════════════════════════════════════
# 守卫
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


def _unchanged(row: dict[str, Any]) -> bool:
    return row["before"] == row["after"]


def test_harness_ran_every_scenario(snap: dict[str, Any]) -> None:
    assert snap["apply_errors"] == [], snap["apply_errors"][:3]
    assert snap["harness_errors"] == {}, snap["harness_errors"]
    assert set(snap["scenarios"]) == {
        "unauthenticated",
        "invisible",
        "workflow_locked",
        "first_publish",
        "again",
        "empty_store_not_publishable",
        "not_provisioned",
    }


def test_unauthenticated_is_401_and_writes_nothing(snap: dict[str, Any]) -> None:
    row = snap["scenarios"]["unauthenticated"]
    assert row["status"] == 401, row
    assert _unchanged(row), row


def test_invisible_project_is_the_unified_404(snap: dict[str, Any]) -> None:
    from app.services.wp_visibility.denial import EXTERNAL_NOT_FOUND_DETAIL

    row = snap["scenarios"]["invisible"]
    assert row["status"] == 404, row
    assert row["body"] == {"detail": EXTERNAL_NOT_FOUND_DETAIL}, row
    assert _unchanged(row), row


def test_workflow_locked_refuses_the_write_action(snap: dict[str, Any]) -> None:
    """归档 / 复核通过的底稿不得因「点了在线编辑」被写入新版本。"""
    row = snap["scenarios"]["workflow_locked"]
    assert row["status"] == 403, row
    assert _unchanged(row), row


def test_first_open_publishes_exactly_one_generation(snap: dict[str, Any]) -> None:
    row = snap["scenarios"]["first_publish"]
    assert row["status"] == 200, row
    body = row["body"]
    assert body["status"] == "published", body
    assert body["representation_generation"] == 1, body
    assert body["content_revision"] == row["before"]["content_revision"] + 1, row
    for table in (
        "working_paper_content_version",
        "working_paper_content_representation",
        "working_paper_sync_entry_state",
    ):
        assert row["after"][table] == row["before"][table] + 1, (table, row)


def test_second_call_is_idempotent(snap: dict[str, Any]) -> None:
    first = snap["scenarios"]["first_publish"]["body"]
    row = snap["scenarios"]["again"]
    assert row["status"] == 200, row
    assert row["body"]["status"] == "already_published", row
    assert row["body"]["representation_id"] == first["representation_id"], row
    assert row["body"]["content_revision"] == first["content_revision"], row
    assert _unchanged(row), "已发布时再调不得写任何一行"


def test_empty_store_without_a_legal_empty_state_is_422(snap: dict[str, Any]) -> None:
    row = snap["scenarios"]["empty_store_not_publishable"]
    assert row["status"] == 422, row
    assert row["body"].get("error_code") == "store_payload_empty_and_not_publishable", row
    assert "录入" in str(row["body"].get("message", "")), "失败原因必须是可读的中文"
    assert _unchanged(row), row


def test_unprovisioned_entry_is_422_and_writes_nothing(snap: dict[str, Any]) -> None:
    row = snap["scenarios"]["not_provisioned"]
    assert row["status"] == 422, row
    assert row["body"].get("error_code") == "projection_bundle_not_provisioned", row
    assert _unchanged(row), row
