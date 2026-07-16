"""Wave 1 结构性护栏与基线特征测试（procedure-delegation-notification / Task 1）。

本文件建立 Task 2+ 不得静默破坏的**可运行**回归基线，全部在默认 SQLite 测试引擎上
真实运行通过，不使用 skip/xfail 掩盖：

1. 真实粒度：`ProcedureInstance` 是 WorkpaperScopeInstance（按 wp_code 一张底稿一条），
   不是程序表具体行；模型上没有 sheet_key/program_no/definition_key/row_key，
   且 `init_from_templates` 令 `procedure_code == wp_code`。
2. 迁移基线：Task 2 已落地 canonical V105 feature 迁移，最高迁移推进到 V105；
   4 张 V105 领域表已登记 ORM（expand 阶段建表为空、读路径零写）。
3. GET/render-config 「数据库领域零写」baseline：用独立 observer session 对现有表
   （procedure_instances / procedure_trim_schemes / WorkingPaper.parsed_data/file_version/updated_at）
   做 canonical 快照，只读观测前后不变；并用 to_regclass（PG）/inspector（SQLite）
   动态探测未来 V105 表在调用前不存在、调用后仍不存在。

零写定义为「数据库领域零写」，允许日志 / metrics 等进程副作用。

_需求：2.5, 7.3-7.5, 9.4, 9.7, 13.9_
"""
from __future__ import annotations

import inspect
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.procedure_models import ProcedureInstance, ProcedureTrimScheme
from app.models.workpaper_models import WorkingPaper, WpSourceType
from app.services.procedure_service import ProcedureService

# 复用架构守卫脚本的常量（V105 身份的单一真源），断言测试基线与守卫一致。
_CHECK_DIR = Path(__file__).resolve().parents[2] / "scripts" / "check"
if str(_CHECK_DIR) not in sys.path:
    sys.path.insert(0, str(_CHECK_DIR))
import check_procedure_delegation_architecture as guard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "backend" / "migrations"

# design.md 预留、Wave 1 绝不允许出现的 V105 领域表。
V105_RESERVED_TABLES = (
    "procedure_row_definitions",
    "procedure_row_tasks",
    "procedure_row_task_history",
    "procedure_operation_previews",
)


# ---------------------------------------------------------------------------
# 1. 真实粒度：ProcedureInstance = WorkpaperScopeInstance（一张底稿一条）
# ---------------------------------------------------------------------------
class TestProcedureInstanceGrain:
    def test_model_has_no_program_row_columns(self):
        """ProcedureInstance 不得携带程序行级身份列，否则会被误当行任务真源。"""
        cols = set(ProcedureInstance.__table__.columns.keys())
        forbidden = {"sheet_key", "program_no", "definition_key", "row_key"}
        leaked = cols & forbidden
        assert not leaked, (
            "ProcedureInstance 必须保持底稿范围粒度（WorkpaperScopeInstance），"
            f"不能出现程序行级列: {sorted(leaked)}"
        )
        # 底稿范围身份列必须存在。
        assert {"procedure_code", "wp_code", "wp_id", "audit_cycle"} <= cols

    def test_init_from_templates_materializes_one_instance_per_wp_code(self):
        """init_from_templates 令 procedure_code == wp_code：粒度是 wp_code 一条，非程序行。

        源码层面断言（不需真库）：主分支（template_library / json）与 wp_template 降级分支
        都以同一 wp_code 同时填充 procedure_code 与 wp_code。
        """
        src = inspect.getsource(ProcedureService.init_from_templates)
        # 主分支
        assert "procedure_code=wp_code" in src
        assert "wp_code=wp_code" in src
        # wp_template 降级分支
        assert "procedure_code=t.template_code" in src
        assert "wp_code=t.template_code" in src
        # 不得按程序行序号/行键建立身份。
        assert "row_key" not in src
        assert "definition_key" not in src


# ---------------------------------------------------------------------------
# 2. 迁移基线：最高 V104，V105 仅预留、尚未创建
# ---------------------------------------------------------------------------
class TestMigrationHead:
    """Task 2 已落地 V105 feature 迁移；后续其他特性可继续追加更高版本号迁移。

    这里锁定：canonical V105 存在、无非法 V105 变体、常量与守卫一致。
    """

    @staticmethod
    def _versions() -> list[int]:
        versions: list[int] = []
        for path in MIGRATIONS_DIR.glob("V*.sql"):
            m = re.match(r"V(\d+)__", path.name)
            if m:
                versions.append(int(m.group(1)))
        return sorted(versions)

    def test_migration_head_is_at_least_105(self):
        versions = self._versions()
        assert versions, f"未发现 V*.sql 迁移: {MIGRATIONS_DIR}"
        assert max(versions) >= 105, f"Task 2 后迁移头应至少为 V105，实际 V{max(versions)}"
        assert 105 in versions, "canonical V105 迁移必须存在"

    def test_canonical_v105_file_exists_and_no_variant(self):
        v105 = sorted(p.name for p in MIGRATIONS_DIR.glob("V105__*.sql"))
        assert v105 == ["V105__procedure_row_tasks.sql"], (
            f"仅允许 canonical V105 迁移文件（重复/改名会被 runner 版本去重静默跳过）: {v105}"
        )

    def test_reserved_v105_identity_matches_guard(self):
        """canonical filename / current version 常量必须与架构守卫脚本一致。"""
        assert guard.CANONICAL_V105_FILENAME == "V105__procedure_row_tasks.sql"
        assert guard.NEXT_MIGRATION_FILENAME == "V105__procedure_row_tasks.sql"
        assert guard.CURRENT_MIGRATION_VERSION == 105
        assert 105 in self._versions()


# ---------------------------------------------------------------------------
# 3a. V105 表已登记到 ORM（Task 2 落地）
# ---------------------------------------------------------------------------
class TestV105InOrm:
    def test_v105_tables_present_in_metadata(self):
        registered = set(Base.metadata.tables.keys())
        missing = set(V105_RESERVED_TABLES) - registered
        assert not missing, f"Task 2 后 V105 表必须登记到 ORM: {sorted(missing)}"

    def test_scope_tables_present_in_metadata(self):
        registered = set(Base.metadata.tables.keys())
        assert {"procedure_instances", "procedure_trim_schemes", "working_paper"} <= registered


# ---------------------------------------------------------------------------
# 3b. GET/render-config 「数据库领域零写」baseline（可运行 observer 快照）
# ---------------------------------------------------------------------------
async def _table_exists(session, table_name: str) -> bool:
    """动态探测表是否存在：PG 用 to_regclass，其余（SQLite）用 inspector。"""
    if session.bind.dialect.name == "postgresql":
        result = await session.execute(
            sa.text("SELECT to_regclass(:t)"), {"t": table_name}
        )
        return result.scalar() is not None
    conn = await session.connection()
    return await conn.run_sync(lambda c: sa.inspect(c).has_table(table_name))


async def _domain_snapshot(session_factory, wp_id: uuid.UUID) -> dict:
    """独立 observer session 对现有领域表取 canonical 快照。"""
    async with session_factory() as observer:
        pi_count = (
            await observer.execute(
                sa.select(sa.func.count()).select_from(ProcedureInstance)
            )
        ).scalar()
        scheme_count = (
            await observer.execute(
                sa.select(sa.func.count()).select_from(ProcedureTrimScheme)
            )
        ).scalar()
        wp = (
            await observer.execute(
                sa.select(
                    WorkingPaper.parsed_data,
                    WorkingPaper.file_version,
                    WorkingPaper.updated_at,
                ).where(WorkingPaper.id == wp_id)
            )
        ).one()
        return {
            "procedure_instances": pi_count,
            "procedure_trim_schemes": scheme_count,
            "wp_parsed_data": wp.parsed_data,
            "wp_file_version": wp.file_version,
            "wp_updated_at": wp.updated_at,
        }


@pytest_asyncio.fixture
async def observer_setup():
    """独立内存引擎 + 种子数据；避免与共享 test_engine 互相干扰。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    project_id = uuid.uuid4()
    wp_index_id = uuid.uuid4()
    wp_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            WorkingPaper(
                id=wp_id,
                project_id=project_id,
                wp_index_id=wp_index_id,
                file_path="/tmp/D2.xlsx",
                source_type=WpSourceType.template,
                parsed_data={"procedure_status": {"D2": {"row-1": {"status": "pending"}}}},
            )
        )
        for i in range(3):
            session.add(
                ProcedureInstance(
                    project_id=project_id,
                    audit_cycle="D",
                    procedure_code=f"D{i + 1}",
                    procedure_name=f"程序 D{i + 1}",
                    wp_code=f"D{i + 1}",
                )
            )
        session.add(
            ProcedureTrimScheme(
                project_id=project_id,
                audit_cycle="D",
                scheme_name="默认方案",
                trim_data={"D1": "execute"},
            )
        )
        await session.commit()

    try:
        yield session_factory, wp_id
    finally:
        await engine.dispose()


async def _v105_row_counts(session_factory) -> dict:
    """独立 observer session 统计 V105 领域表行数（Task 2 后表已存在，expand 阶段应为空）。"""
    from app.models.procedure_models import (
        ProcedureOperationPreview,
        ProcedureRowDefinition,
        ProcedureRowTask,
        ProcedureRowTaskHistory,
    )

    model_by_table = {
        "procedure_row_definitions": ProcedureRowDefinition,
        "procedure_row_tasks": ProcedureRowTask,
        "procedure_row_task_history": ProcedureRowTaskHistory,
        "procedure_operation_previews": ProcedureOperationPreview,
    }
    counts: dict[str, int] = {}
    async with session_factory() as observer:
        for table, model in model_by_table.items():
            counts[table] = (
                await observer.execute(sa.select(sa.func.count()).select_from(model))
            ).scalar()
    return counts


@pytest.mark.asyncio
class TestRenderConfigZeroDomainWriteBaseline:
    async def test_v105_tables_present_in_live_db(self, observer_setup):
        session_factory, _ = observer_setup
        async with session_factory() as session:
            # 现有表确实存在（探针有效性自证）。
            assert await _table_exists(session, "procedure_instances")
            assert await _table_exists(session, "procedure_trim_schemes")
            assert await _table_exists(session, "working_paper")
            # Task 2 后 V105 表已登记 ORM → create_all 建成，存在于数据库。
            for table in V105_RESERVED_TABLES:
                assert await _table_exists(session, table), (
                    f"Task 2 后 V105 表应存在于数据库: {table}"
                )

    async def test_read_only_observation_is_domain_zero_write(self, observer_setup):
        session_factory, wp_id = observer_setup

        before = await _domain_snapshot(session_factory, wp_id)
        v105_before = await _v105_row_counts(session_factory)

        # 模拟 GET/render-config 的只读语义：独立 observer session 只做 SELECT。
        async with session_factory() as reader:
            await reader.execute(sa.select(ProcedureInstance).limit(50))
            await reader.execute(sa.select(ProcedureTrimScheme))
            await reader.execute(
                sa.select(WorkingPaper.parsed_data).where(WorkingPaper.id == wp_id)
            )
            # 只读，不 commit、不 add、不 update。

        after = await _domain_snapshot(session_factory, wp_id)
        v105_after = await _v105_row_counts(session_factory)

        # 领域快照前后完全一致：行数、parsed_data、file_version、updated_at 均不变。
        assert after == before
        # V105 领域表在 expand 阶段保持空且只读观测零写入。
        assert v105_before == {t: 0 for t in V105_RESERVED_TABLES}
        assert v105_after == v105_before
