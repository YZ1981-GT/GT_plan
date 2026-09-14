# -*- coding: utf-8 -*-
"""Task 18 真实 PostgreSQL 守卫：普通 single_html 保存恰增一次 business revision、
状态变化零 revision、orchestrator 失败整笔回滚可重试、CAS 冲突只留不可见 orphan。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 18
Requirements: 2.1, 2.2, 2.12, 3.1, 13.4
Properties: **P4**（业务版本与 representation generation 正交）/ **P54**（after-save
失败可重试）/ **P61**（所有 writer 进入唯一 revision 域）

═══ 为什么必须真库（不可 mock、不可 skip）═══

Task 18 的三条核心承诺全是**关于事务的**：

* 「恰一次 business revision」—— 判据是 `working_paper.content_revision` 的实际值与
  `working_paper_content_version` 的行数，两者都只在真事务里有意义；
* 「状态/复核变化不增 content revision」—— 判据是**另一条** UPDATE 走完之后版本没动；
* 「orchestrator 异常进入 outbox retry，不被 warning 吞掉」—— 判据是失败后**整笔**
  回滚（内容、审计日志、耐久行同生共死），重试后恰一次 revision。

mock session 里「事务」不存在、`rollback()` 是空操作，于是三条断言全部空转。这与
Task 15/16 的 `_pg.py` 是同一个理由，不重复论证。

`xmin` 是**独立于本代码**的原子性判据：PostgreSQL 给每个行版本记录写它的事务 id，
`working_paper` / `working_paper_content_version` / `working_paper_artifact` /
`import_event_outbox` 四张表的 `xmin` 全等，才证明它们是同一个事务写的。它不依赖
`_TransactionWitness`（那是我们自己的代码），所以「见证逻辑被改坏」不会让它假绿。

═══ 两条 lane 的形态差异也在这里被观测 ═══

`single_html` lane 与 bidirectional lane 的区别不是「少写两张表」这句话，而是
**零 representation 行、零 entry pointer 行**这两个可数事实（Requirement 3.9：
「single_html entry SHALL 不创建空白 OO artifact」）。场景 A 直接数它们。

═══ 隔离 ═══

scratch schema `tmp_task18_hs_*`，`search_path` 不含 public；`projects/users/
working_paper` 建桩表，`import_event_outbox` / `import_event_consumptions` 从 ORM
metadata 建（列不手抄，防第二真源）；artifact 全落系统临时目录。结束
`DROP SCHEMA CASCADE` + 删临时目录。**绝不触碰真实 `storage/`**。

`DATABASE_URL` 非 PostgreSQL 时**直接失败不 skip**。

═══ 采集写法 ═══

全部场景由**一次 `asyncio.run`** 跑完并落进快照（module fixture）。不给每个测试各自
开 async（共享连接池会被污染，第二个测试起 `NoneType has no attribute send`）。
采集内部任何异常都记进快照的 `errors`，由守卫断言为空 —— **禁 fail-open**。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_MIGRATION = (
    _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"
)

if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_task18_hs_"
SHEET = "审定表D2-1"
SCHEMA_VERSION = "v2025-R5"

_STUB_DDL = """
CREATE TABLE projects (id UUID PRIMARY KEY, name VARCHAR(200) NOT NULL DEFAULT 'stub');
CREATE TABLE users (id UUID PRIMARY KEY, username VARCHAR(100) NOT NULL DEFAULT 'stub');
CREATE TABLE working_paper (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    file_version INTEGER NOT NULL DEFAULT 1,
    prefill_stale BOOLEAN NOT NULL DEFAULT false,
    parsed_data JSONB,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

#: `logs` 表**从 ORM metadata 建**，不手抄 DDL：`Log` 有 `ip_address` 等列，手抄一份
#: 就是第二真源，漏一列表现为「采集期 UndefinedColumnError」而不是判据失效 —— 但下一次
#: 生产加列时同样会挂，且挂在一个看不出原因的地方。
_ORM_BUILT_TABLES = ("logs", "import_event_outbox", "import_event_consumptions")

#: V065 给 outbox enum 加过 'processing'；守卫不能跑在比生产更窄的类型上。
_EXTRA_ENUM_LABELS = {"import_event_outbox_status": ("processing",)}

#: 一次 `single_html` 业务 commit 必须同事务写入的四张表（`xmin` 全等即证明单事务）。
#: **刻意不含** representation / entry_state —— 这条 lane 不产生它们。
_ATOMIC_TABLES: tuple[tuple[str, str], ...] = (
    ("working_paper", "revision_bump"),
    ("working_paper_content_version", "content_version"),
    ("working_paper_artifact", "projection_artifact"),
    ("import_event_outbox", "outbox"),
)

#: 这条 lane 结束后必须**恒为 0 行**的两张表（Requirement 3.9）。
_FORBIDDEN_TABLES: tuple[str, ...] = (
    "working_paper_content_representation",
    "working_paper_sync_entry_state",
)


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


class _User:
    def __init__(self, user_id: uuid.UUID) -> None:
        self.id = user_id
        self.username = "task18"


def _enum_ddl(tables: list[sa.Table]) -> list[str]:
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


# ═══════════════════════════════════════════════════════════════════════════
# 采集
# ═══════════════════════════════════════════════════════════════════════════


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - 一次采集覆盖全部场景
    from sqlalchemy import event as sa_event
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.models.dataset_models import ImportEventConsumption, ImportEventOutbox
    from app.services import event_bus as event_bus_module
    from app.services.workpaper_sync import content_mutation as CM
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.entry_profile import Capability
    from app.services.workpaper_sync.models import RevisionConflictError
    from app.services.workpaper_sync.outbox import (
        DurableEventOutboxService,
        DurableOutboxError,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "Task 18 的判据是「恰一次 revision、状态变化零 revision、失败整笔回滚」，"
            "依赖真实事务语义与 V151 的 CHECK/trigger；必须真实 PostgreSQL，当前 "
            f"DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task18_store_"))
    (base_root / "storage").mkdir()
    (base_root / "definition_store").mkdir()

    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "base_root": str(base_root),
        "server_version": None,
        "apply_errors": [],
        "errors": [],
        "first_save": {},
        "second_save": {},
        "status_change": {},
        "cas_conflict": {},
        "after_save_failure": {},
        "bidirectional_refused": {},
    }
    engine = None
    # Redis 不参与判定：置 False 让 _persist_to_stream 立刻返回，避免 xadd 抖动。
    bus = event_bus_module.event_bus
    previous_redis_flag = bus._redis_available
    bus._redis_available = False
    try:
        async with admin.connect() as conn:
            snap["server_version"] = (
                await conn.exec_driver_sql("SELECT version()")
            ).scalar_one()
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
                snap["apply_errors"].append(
                    {"index": idx, "error": _err(exc), "head": stmt[:120]}
                )
        if snap["apply_errors"]:
            raise _HarnessError(f"V151 应用失败: {snap['apply_errors'][:3]}")

        from app.models.core import Log

        outbox_tables = [ImportEventOutbox.__table__, ImportEventConsumption.__table__]
        async with engine.begin() as conn:
            for stmt in _enum_ddl(outbox_tables + [Log.__table__]):
                await conn.exec_driver_sql(stmt)
            await conn.run_sync(
                lambda sync_conn: ImportEventOutbox.metadata.create_all(
                    sync_conn, tables=outbox_tables, checkfirst=True
                )
            )
            await conn.run_sync(
                lambda sync_conn: Log.metadata.create_all(
                    sync_conn, tables=[Log.__table__], checkfirst=True
                )
            )
        assert Log.__tablename__ in _ORM_BUILT_TABLES, (
            f"审计日志表名变了（{Log.__tablename__}）—— 采集里的计数 SQL 要跟着改"
        )

        project, wp, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"INSERT INTO projects (id) VALUES ('{project}')")
            await conn.exec_driver_sql(f"INSERT INTO users (id) VALUES ('{user}')")
            await conn.exec_driver_sql(
                f"INSERT INTO working_paper (id, project_id, file_version) "
                f"VALUES ('{wp}', '{project}', 7)"
            )

        artifacts = CanonicalArtifactRepository(base_root)
        entry_id = CM.html_only_entry_id(wp_code="D2", wp_id=wp)

        # ── 计数与快照工具 ────────────────────────────────────────────────
        async def _counts(session) -> dict[str, int]:
            out: dict[str, int] = {}
            for table in (
                "working_paper_content_version",
                "working_paper_artifact",
                "working_paper_sync_scope_index",
                "import_event_outbox",
                "logs",
                *_FORBIDDEN_TABLES,
            ):
                out[table] = int(
                    (
                        await session.execute(sa.text(f"SELECT count(*) FROM {table}"))
                    ).scalar_one()
                )
            return out

        async def _wp_state(session) -> dict[str, Any]:
            row = (
                await session.execute(
                    sa.text(
                        "SELECT content_revision, file_version, prefill_stale, "
                        "current_content_version_id::text FROM working_paper WHERE id = :wp"
                    ),
                    {"wp": str(wp)},
                )
            ).first()
            return {
                "content_revision": int(row[0]),
                "file_version": int(row[1]),
                "prefill_stale": bool(row[2]),
                "current_content_version_id": row[3],
            }

        async def _xmins(session) -> dict[str, list[str]]:
            out: dict[str, list[str]] = {}
            for table, label in _ATOMIC_TABLES:
                where = " WHERE id = :wp" if table == "working_paper" else ""
                params = {"wp": str(wp)} if where else {}
                rows = (
                    await session.execute(
                        sa.text(f"SELECT xmin::text FROM {table}{where}"), params
                    )
                ).scalars().all()
                out[label] = [str(value) for value in rows]
            return out

        def _make_plan(
            expected_revision: int,
            *,
            capability=Capability.single_html,
            parent_version_id: uuid.UUID | None = None,
        ):
            return CM.HtmlOnlyCommitPlan(
                project_id=project,
                wp_id=wp,
                entry_id=entry_id,
                expected_revision=expected_revision,
                capability=capability,
                sheet_name=SHEET,
                schema_version=SCHEMA_VERSION,
                actor_id=user,
                parent_version_id=parent_version_id,
            )

        def _service(session) -> Any:
            return CM.ContentMutationService(
                session=session,
                repository=WorkpaperSyncRepository(session),
                artifacts=artifacts,
                resolution=CanonicalResolutionService(session, artifacts),
            )

        async def _save(
            session, expected_revision: int, html_data: dict[str, Any], *, revision_hint=None
        ):
            """复刻 `wp_html_save` 的次序：stage → parsed_data → after_save → 唯一 commit。"""
            from app.services.workpaper_save_orchestrator import orchestrator

            service = _service(session)
            # 与 `wp_html_save` 一致：parent 取当前 current pointer（opaque UUID），
            # 让 immutable version 链在真库上真形成（不是文档措辞）。
            parent = (await _wp_state(session))["current_content_version_id"]
            plan = _make_plan(
                expected_revision,
                parent_version_id=uuid.UUID(parent) if parent else None,
            )
            staged = service.stage_html_projection(plan=plan, html_data=html_data)
            # `CAST(:pd AS jsonb)` 而不是 `:pd::jsonb` —— 后者的 `::` 会被 SQLAlchemy
            # 的 bind-param 词法当成又一个 `:name` 起始，asyncpg 收到的是裸 `:`。
            await session.execute(
                sa.text(
                    "UPDATE working_paper SET parsed_data = CAST(:pd AS jsonb) "
                    "WHERE id = CAST(:wp AS uuid)"
                ),
                {"pd": '{"html_data": {}}', "wp": str(wp)},
            )
            wp_row = _WpProxy(wp, project)
            await orchestrator.after_save(
                session, wp_row, _User(user),
                trigger="html_save",
                extra={"sheet_name": SHEET, "entry_id": entry_id},
                content_revision=revision_hint or plan.target_revision,
            )
            # after_save 只改内存 ORM 替身的两个字段，这里把它们落到 SQL（生产里
            # `working_paper` 是真 ORM 实例，flush 自动带上）。
            await session.execute(
                sa.text(
                    "UPDATE working_paper SET prefill_stale = :ps, updated_at = :ua "
                    "WHERE id = :wp"
                ),
                {"ps": wp_row.prefill_stale, "ua": wp_row.updated_at, "wp": str(wp)},
            )
            receipt = await service.commit_html_projection(plan=plan, staged=staged)
            return receipt, staged

        # ── 场景 A：第一次保存 —— 恰一次 revision、单事务、零 representation ──
        commit_counter = {"n": 0}

        async with Session() as db:
            sync_session = db.sync_session

            def _on_commit(_sess) -> None:
                commit_counter["n"] += 1

            sa_event.listen(sync_session, "after_commit", _on_commit)
            try:
                receipt, staged = await _save(db, 0, {"rows": [{"cell": "B7", "value": 1}]})
            finally:
                sa_event.remove(sync_session, "after_commit", _on_commit)

        async with Session() as verify:
            state = await _wp_state(verify)
            counts = await _counts(verify)
            xmins = await _xmins(verify)
            revisions = (
                await verify.execute(
                    sa.text(
                        "SELECT revision FROM working_paper_content_version "
                        "ORDER BY revision"
                    )
                )
            ).scalars().all()
            version_row = (
                await verify.execute(
                    sa.text(
                        "SELECT source, projection_sha256, authoritative_artifact_id::text, "
                        "actor_id::text FROM working_paper_content_version"
                    )
                )
            ).first()
            outbox_row = (
                await verify.execute(
                    sa.text("SELECT event_type, payload FROM import_event_outbox")
                )
            ).all()
        snap["first_save"] = {
            "receipt": receipt.as_dict(),
            "wp": state,
            "counts": counts,
            "xmins": xmins,
            "revisions": [int(value) for value in revisions],
            "version_source": version_row[0],
            "version_projection_sha256": version_row[1],
            "version_authoritative_artifact_id": version_row[2],
            "version_actor_id": version_row[3],
            "commit_count": commit_counter["n"],
            "artifact_exists_on_disk": staged.artifact.path.is_file(),
            "outbox_event_types": sorted({str(row[0]) for row in outbox_row}),
            "outbox_payloads": [dict(row[1] or {}) for row in outbox_row],
        }

        # ── 场景 B：第二次保存 —— 单调 +1，两个 immutable version 并存 ────────
        async with Session() as db:
            receipt2, _ = await _save(db, 1, {"rows": [{"cell": "B7", "value": 2}]})
        async with Session() as verify:
            state2 = await _wp_state(verify)
            counts2 = await _counts(verify)
            revisions2 = (
                await verify.execute(
                    sa.text(
                        "SELECT revision, parent_version_id::text "
                        "FROM working_paper_content_version ORDER BY revision"
                    )
                )
            ).all()
        snap["second_save"] = {
            "receipt": receipt2.as_dict(),
            "wp": state2,
            "counts": counts2,
            "revisions": [int(row[0]) for row in revisions2],
            "parents": [row[1] for row in revisions2],
        }

        # ── 场景 C：状态/复核变化 —— content revision 必须不动（AC 2.1）────────
        async with Session() as db:
            await db.execute(
                sa.text(
                    "UPDATE working_paper SET prefill_stale = true, "
                    "updated_at = now() WHERE id = :wp"
                ),
                {"wp": str(wp)},
            )
            await db.execute(
                sa.text("UPDATE working_paper SET file_version = file_version + 1 WHERE id = :wp"),
                {"wp": str(wp)},
            )
            await db.commit()
        async with Session() as verify:
            state3 = await _wp_state(verify)
            counts3 = await _counts(verify)
        snap["status_change"] = {"wp": state3, "counts": counts3}

        # ── 场景 D：CAS 冲突 —— 零 revision 移动 + 已发布 artifact 是不可见 orphan ─
        before_counts = counts3
        artifact_before = None
        raised = None
        async with Session() as db:
            service = _service(db)
            stale_plan = _make_plan(0)  # 服务端已经是 2 了
            stale_staged = service.stage_html_projection(
                plan=stale_plan, html_data={"rows": [{"cell": "B7", "value": 99}]}
            )
            artifact_before = stale_staged.artifact
            try:
                await service.commit_html_projection(plan=stale_plan, staged=stale_staged)
            except RevisionConflictError as exc:
                raised = _err(exc)
        async with Session() as verify:
            state4 = await _wp_state(verify)
            counts4 = await _counts(verify)
            orphan_refs = int(
                (
                    await verify.execute(
                        sa.text(
                            "SELECT count(*) FROM working_paper_artifact "
                            "WHERE sha256 = :sha"
                        ),
                        {"sha": artifact_before.sha256},
                    )
                ).scalar_one()
            )
        snap["cas_conflict"] = {
            "raised": raised,
            "wp": state4,
            "counts": counts4,
            "counts_unchanged": counts4 == before_counts,
            "orphan_file_on_disk": artifact_before.path.is_file(),
            "orphan_db_rows": orphan_refs,
        }

        # ── 场景 E：orchestrator/耐久入队失败 —— 整笔回滚 + 重试成功（P54）─────
        original_enqueue = DurableEventOutboxService.enqueue
        calls = {"n": 0}

        async def _flaky_enqueue(db_, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise DurableOutboxError("injected durable enqueue failure")
            return await original_enqueue(db_, **kwargs)

        failure_raised = None
        DurableEventOutboxService.enqueue = staticmethod(_flaky_enqueue)  # type: ignore[assignment]
        try:
            async with Session() as db:
                try:
                    await _save(db, 2, {"rows": [{"cell": "B7", "value": 3}]})
                except DurableOutboxError as exc:
                    failure_raised = _err(exc)
                    await db.rollback()
            async with Session() as verify:
                state5 = await _wp_state(verify)
                counts5 = await _counts(verify)
            # 重试：同一 expected revision 再来一次，必须恰增一次
            async with Session() as db:
                receipt3, _ = await _save(db, 2, {"rows": [{"cell": "B7", "value": 3}]})
        finally:
            DurableEventOutboxService.enqueue = original_enqueue  # type: ignore[assignment]
        async with Session() as verify:
            state6 = await _wp_state(verify)
            counts6 = await _counts(verify)
        snap["after_save_failure"] = {
            "raised": failure_raised,
            "wp_after_failure": state5,
            "counts_after_failure": counts5,
            "wp_after_retry": state6,
            "counts_after_retry": counts6,
            "retry_receipt": receipt3.as_dict(),
            "enqueue_calls": calls["n"],
        }

        # ── 场景 F：bidirectional 声明 —— 构造点即拒，零数据库写入 ─────────────
        refusal = None
        async with Session() as verify:
            counts_before_refusal = await _counts(verify)
        try:
            _make_plan(3, capability=Capability.bidirectional)
        except Exception as exc:  # noqa: BLE001 - 记录类型由守卫断言
            refusal = {"type": type(exc).__name__, "code": getattr(exc, "error_code", None)}
        async with Session() as verify:
            counts_after_refusal = await _counts(verify)
        snap["bidirectional_refused"] = {
            "refusal": refusal,
            "counts_unchanged": counts_before_refusal == counts_after_refusal,
        }

    except Exception as exc:  # noqa: BLE001 - 采集失败必须可见
        snap["errors"].append(_err(exc))
    finally:
        bus._redis_available = previous_redis_flag
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except Exception as exc:  # noqa: BLE001
            snap["errors"].append(f"cleanup: {_err(exc)}")
        await admin.dispose()
        shutil.rmtree(base_root, ignore_errors=True)
    return snap


class _WpProxy:
    """`after_save` 需要的 WorkingPaper 最小面（id / project_id / 两个可写字段）。

    刻意不是 ORM 实例：本文件的 stub `working_paper` 表没有 ORM 映射，而
    `after_save` 的契约只要求 `id / project_id / prefill_stale / updated_at`。
    它同时把「handler 只写这两个字段」这件事变成可观察的 —— 写别的字段会直接
    `AttributeError`（`__slots__`）。
    """

    __slots__ = ("id", "project_id", "prefill_stale", "updated_at")

    def __init__(self, wp_id: uuid.UUID, project_id: uuid.UUID) -> None:
        self.id = wp_id
        self.project_id = project_id
        self.prefill_stale = False
        self.updated_at = None


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


# ═══════════════════════════════════════════════════════════════════════════
# 守卫
# ═══════════════════════════════════════════════════════════════════════════


def test_harness_ran_on_real_postgres_without_errors(snap: dict[str, Any]) -> None:
    """采集自身不得 fail-open：任何异常都让本条红，而不是让后面的判据空转。"""
    assert snap["errors"] == [], snap["errors"]
    assert snap["apply_errors"] == []
    assert "PostgreSQL" in (snap["server_version"] or "")


def test_plain_single_html_save_advances_the_business_revision_exactly_once(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 2.1**

    Property 4 的正面判据。三个可数事实：`content_revision` 0→1、恰一个 immutable
    content version、revision 序列就是 `[1]`。
    """
    fact = snap["first_save"]
    assert fact["wp"]["content_revision"] == 1, "恰一次 business revision（0 → 1）"
    assert fact["counts"]["working_paper_content_version"] == 1
    assert fact["revisions"] == [1]
    assert fact["receipt"]["revision"] == 1
    assert fact["wp"]["current_content_version_id"] == fact["receipt"]["content_version_id"]
    # source 走 V151 的封闭词表，projection 侧有 digest、authoritative 侧为空
    # （single_html 的权威内容是结构化 projection，不是 OOXML 本体）。
    assert fact["version_source"] == "html"
    assert fact["version_projection_sha256"]
    assert fact["version_authoritative_artifact_id"] is None
    assert fact["version_actor_id"], "content version 必须留下 actor"


def test_the_single_html_lane_creates_no_representation_and_no_entry_pointer(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 3.9**

    「single_html entry SHALL 不创建空白 OO artifact」。判据是两张表**恒 0 行**，
    不是"我们没写那段代码"。
    """
    for scenario in ("first_save", "second_save", "status_change", "cas_conflict"):
        counts = snap[scenario].get("counts") or snap[scenario].get("counts_after_retry")
        for table in _FORBIDDEN_TABLES:
            assert counts[table] == 0, (
                f"{scenario}: {table} 出现了 {counts[table]} 行 —— single_html 入口"
                "凭空造了一个 OO 指针"
            )


def test_the_business_commit_is_one_transaction_and_one_database_commit(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 2.2, 13.1**

    两条**互相独立**的判据：

    1. `xmin` 全等 —— PostgreSQL 自己记录的"哪个事务写了这一行"，不依赖我们的
       `_TransactionWitness`；
    2. `after_commit` 事件恰一次 —— 注入第二次 `session.commit()` 会同时打破两者。
    """
    fact = snap["first_save"]
    assert fact["commit_count"] == 1, (
        f"一次业务保存恰一次数据库提交，实得 {fact['commit_count']}"
    )
    assert fact["receipt"]["commit_count"] == 1
    assert len(fact["receipt"]["transaction_ids"]) == 1

    stamps = fact["xmins"]
    flattened = {label: set(values) for label, values in stamps.items()}
    for label, values in flattened.items():
        assert len(values) == 1, f"{label} 的行来自 {len(values)} 个事务: {sorted(values)}"
    distinct = {next(iter(values)) for values in flattened.values()}
    assert len(distinct) == 1, (
        f"四张表落在 {len(distinct)} 个事务里 {sorted(distinct)} —— revision / content "
        f"version / artifact / outbox 必须同生共死（逐表: {stamps}）"
    )


def test_the_outbox_row_carries_the_business_revision(snap: dict[str, Any]) -> None:
    """**Validates: Requirements 13.1, 13.2**

    一次业务保存在同事务里落两条耐久事件：`workpaper.content.updated`（内容域，
    由统一 commit 写）与 `workpaper.saved`（副作用域，由 after_save 写）。两者都必须
    携带同一个 business revision，否则下游"按返回的新版本刷新"没有一致依据。
    """
    fact = snap["first_save"]
    assert fact["outbox_event_types"] == [
        "workpaper.content.updated",
        "workpaper.saved",
    ], fact["outbox_event_types"]
    assert fact["counts"]["import_event_outbox"] == 2
    revisions = set()
    for payload in fact["outbox_payloads"]:
        value = payload.get("revision", payload.get("content_revision"))
        assert value is not None, f"耐久 payload 缺 revision: {sorted(payload)}"
        revisions.add(int(value))
    assert revisions == {1}, (
        f"两条耐久事件携带的 revision 不一致: {sorted(revisions)} —— 那就是"
        "「两个计数器」的形态又回来了"
    )
    # 审计日志同事务恰一条。
    assert fact["counts"]["logs"] == 1


def test_a_second_save_is_monotonic_and_keeps_the_earlier_version_immutable(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 2.1, 2.3**"""
    fact = snap["second_save"]
    assert fact["wp"]["content_revision"] == 2
    assert fact["revisions"] == [1, 2], "旧 version 不被覆盖，新的追加"
    assert fact["counts"]["working_paper_content_version"] == 2
    assert fact["receipt"]["revision"] == 2
    # revision 2 的 parent 指向 revision 1 的 opaque id（不是数字 revision）。
    assert fact["parents"][0] is None
    assert fact["parents"][1] is not None


def test_status_and_file_lifecycle_changes_do_not_advance_the_content_revision(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 2.1**

    Property 4 的核心：`prefill_stale` / `updated_at` / `file_version` 都不是业务内容，
    改它们**不得**推进 `content_revision`，也不得产生 content version。
    """
    before = snap["second_save"]
    after = snap["status_change"]
    assert after["wp"]["content_revision"] == before["wp"]["content_revision"] == 2
    assert (
        after["counts"]["working_paper_content_version"]
        == before["counts"]["working_paper_content_version"]
        == 2
    )
    # 而这几个字段确实变了 —— 否则这条判据是空转（"什么都没改，当然没涨"）。
    assert after["wp"]["prefill_stale"] is True
    assert after["wp"]["file_version"] > before["wp"]["file_version"]


def test_a_lost_cas_race_moves_nothing_and_leaves_only_an_invisible_orphan(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 2.1, 2.4**

    真乐观锁：`UPDATE ... WHERE content_revision = :expected` 命中 0 行即冲突。
    冲突后：

    * 数据库侧**一行都没动**（Property 4）；
    * 文件侧留下一个已发布但**零 DB 行引用**的 orphan（Requirement 2.4 的设计承诺：
      宁可留垃圾文件，也不留"pointer 指向缺失 artifact"的半成功态）。
    """
    fact = snap["cas_conflict"]
    assert fact["raised"] and "RevisionConflictError" in fact["raised"], fact["raised"]
    assert fact["wp"]["content_revision"] == 2, "冲突不得推进 revision"
    assert fact["counts_unchanged"], f"冲突改动了数据库: {fact['counts']}"
    assert fact["orphan_file_on_disk"] is True, (
        "staged artifact 在事务之前就已 publish，这是 Requirement 2.4 的协议"
    )
    assert fact["orphan_db_rows"] == 0, (
        "orphan 必须对数据库不可见 —— 有引用行就说明形成了半成功态"
    )


def test_a_failed_side_effect_rolls_the_whole_save_back_and_stays_retryable(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 13.4**

    Property 54 的 Task 18 侧：「orchestrator 异常进入 outbox retry，不被 warning
    吞掉」。落地形态是**整笔回滚 + 可重试**：

    * 耐久入队失败会抛到调用方（不是 `logger.warning` 后返回 200）；
    * 回滚后 `content_revision`、content version 与 outbox 行**全部**没动 ——
      不存在"内容写了但事件丢了"的半成功态；
    * 用同一个 expected revision 重试成功，且**恰增一次**（不是两次）。
    """
    fact = snap["after_save_failure"]
    assert fact["raised"] and "DurableOutboxError" in fact["raised"], (
        f"耐久入队失败必须抛出去，实得 {fact['raised']}"
    )
    assert fact["enqueue_calls"] >= 2, "注入生效且重试真的又调了一次"

    before = snap["status_change"]["counts"]
    failed = fact["counts_after_failure"]
    assert fact["wp_after_failure"]["content_revision"] == 2, "失败不得推进 revision"
    assert (
        failed["working_paper_content_version"] == before["working_paper_content_version"]
    ), "失败后不该留下 content version"
    assert failed["import_event_outbox"] == before["import_event_outbox"], (
        "失败后不该留下耐久行 —— 内容与事件同生共死"
    )
    assert failed["logs"] == before["logs"], "失败后不该留下审计日志"

    retried = fact["counts_after_retry"]
    assert fact["wp_after_retry"]["content_revision"] == 3, "重试恰增一次（2 → 3）"
    assert fact["retry_receipt"]["revision"] == 3
    assert retried["working_paper_content_version"] == 3
    assert retried["import_event_outbox"] == before["import_event_outbox"] + 2


def test_a_bidirectional_entry_cannot_use_the_projection_only_lane(
    snap: dict[str, Any],
) -> None:
    """**Validates: Requirements 3.1**

    design 明确拒绝的方案 #20（先提交 projection-only revision 再补 artifact）在这条
    lane 上必须**不可能**。拒绝发生在 plan 构造点，因此数据库一行都没被碰。
    """
    fact = snap["bidirectional_refused"]
    assert fact["refusal"] is not None, "bidirectional 竟然被 html-only lane 接受了"
    assert fact["refusal"]["type"] == "RepresentationLaneRequiredError"
    assert fact["refusal"]["code"] == "bidirectional_requires_representation_lane"
    assert fact["counts_unchanged"], "拒绝之前不得有任何数据库写入"
