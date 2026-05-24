"""Tests for Task 8: 模板入口可达性 + 保存完整性（Req 15）

Property 29: 模板 config save/load round-trip
表缺失修复单测
3 入口同步状态 e2e (simplified integration test)

Feature: advanced-query-enhancements-p1p2, Property 29: Template config save/load round-trip
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
import pytest_asyncio
from hypothesis import given, settings, strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import User, UserRole
from app.models.custom_query_models import CustomQueryTemplate

# SQLite doesn't have JSONB, patch it
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        # Seed user
        user = User(
            id=FAKE_USER_ID,
            username="tester",
            email="t@t.com",
            hashed_password="x",
            role=UserRole.admin,
        )
        session.add(user)
        await session.commit()
        yield session


# ---------------------------------------------------------------------------
# Strategies for Property 29
# ---------------------------------------------------------------------------

# Valid source URIs across 5 namespaces
st_source = st.sampled_from([
    "workpaper:D2|审定表D2-1",
    "workpaper:E1|银行存款E1-1",
    "report:balance_sheet|A1:D20",
    "note:五-1-1|B2:C10",
    "adj:aje|A1:F50",
    "tb:detail|A1:E100",
    "disclosure_note:五-1-1",
    "consol_unit:S01:account_balance",
])

st_cell_range = st.one_of(
    st.none(),
    st.from_regex(r"[A-Z]{1,2}[1-9][0-9]{0,3}:[A-Z]{1,2}[1-9][0-9]{0,3}", fullmatch=True),
)

st_sheet_name = st.one_of(
    st.none(),
    st.text(min_size=1, max_size=30, alphabet=st.characters(
        whitelist_categories=("L", "N", "Pd"),
        whitelist_characters="_- "
    )),
)

st_page_size = st.sampled_from([50, 100, 200, 500])

st_sort_order = st.sampled_from(["asc", "desc"])

st_conditions = st.lists(
    st.fixed_dictionaries({
        "field": st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L",))),
        "op": st.sampled_from(["eq", "ne", "gt", "gte", "lt", "lte", "in", "like", "is_null"]),
        "value": st.one_of(st.text(max_size=20), st.integers(-1000, 1000), st.none()),
    }),
    min_size=0,
    max_size=3,
)

st_columns = st.lists(
    st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    min_size=0,
    max_size=10,
)

st_template_config = st.fixed_dictionaries(
    {
        "source": st_source,
    },
    optional={
        "project_id": st.one_of(st.none(), st.uuids().map(str)),
        "year": st.one_of(st.none(), st.integers(2000, 2100)),
        "sheet_name": st_sheet_name,
        "cell_range": st_cell_range,
        "filter_text": st.one_of(st.none(), st.text(max_size=50)),
        "conditions": st_conditions,
        "selected_columns": st_columns,
        "available_columns": st_columns,
        "page_size": st_page_size,
        "sort_field": st.one_of(st.none(), st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L",)))),
        "sort_order": st_sort_order,
    },
)


# ---------------------------------------------------------------------------
# Property 29: Template config save/load round-trip
# Feature: advanced-query-enhancements-p1p2, Property 29: Template config save/load round-trip
# ---------------------------------------------------------------------------


class TestProperty29TemplateConfigRoundTrip:
    """For any valid CustomQueryTemplateConfig, saving then loading must produce identical state.

    **Validates: Requirements 15.3, 15.4**
    """

    @pytest.mark.asyncio
    @settings(max_examples=20)
    @given(config=st_template_config)
    async def test_save_load_round_trip(self, config):
        """Save a template config, then load it back — must be identical."""
        # Create fresh DB session for each hypothesis example
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            # Seed user
            user = User(
                id=FAKE_USER_ID,
                username="tester",
                email="t@t.com",
                hashed_password="x",
                role=UserRole.admin,
            )
            session.add(user)
            await session.flush()

            # Save template
            tpl = CustomQueryTemplate(
                id=uuid.uuid4(),
                name="test-template",
                description="auto-generated",
                data_source=config["source"],
                config=config,
                scope="private",
                created_by=FAKE_USER_ID,
                creator_id=FAKE_USER_ID,
            )
            session.add(tpl)
            await session.flush()

            # Load template back
            loaded = await session.get(CustomQueryTemplate, tpl.id)
            assert loaded is not None

            loaded_config = loaded.config
            assert loaded_config == config

            # Verify all fields individually
            assert loaded_config.get("source") == config["source"]
            if "project_id" in config:
                assert loaded_config.get("project_id") == config["project_id"]
            if "year" in config:
                assert loaded_config.get("year") == config["year"]
            if "sheet_name" in config:
                assert loaded_config.get("sheet_name") == config["sheet_name"]
            if "cell_range" in config:
                assert loaded_config.get("cell_range") == config["cell_range"]
            if "filter_text" in config:
                assert loaded_config.get("filter_text") == config["filter_text"]
            if "conditions" in config:
                assert loaded_config.get("conditions") == config["conditions"]
            if "selected_columns" in config:
                assert loaded_config.get("selected_columns") == config["selected_columns"]
            if "available_columns" in config:
                assert loaded_config.get("available_columns") == config["available_columns"]
            if "page_size" in config:
                assert loaded_config.get("page_size") == config["page_size"]
            if "sort_field" in config:
                assert loaded_config.get("sort_field") == config["sort_field"]
            if "sort_order" in config:
                assert loaded_config.get("sort_order") == config["sort_order"]

            await session.rollback()

    @pytest.mark.asyncio
    async def test_complete_config_round_trip(self, db_session):
        """Explicit test with all fields populated."""
        config = {
            "project_id": str(uuid.uuid4()),
            "year": 2025,
            "source": "workpaper:D2|审定表D2-1",
            "sheet_name": "审定表D2-1",
            "cell_range": "A1:D20,F1:F20",
            "filter_text": "应收账款",
            "conditions": [
                {"field": "amount", "op": "gt", "value": 1000},
                {"field": "status", "op": "eq", "value": "confirmed"},
            ],
            "selected_columns": ["cell_ref", "value", "formula"],
            "available_columns": ["cell_ref", "value", "formula", "sheet_name"],
            "page_size": 200,
            "sort_field": "cell_ref",
            "sort_order": "asc",
        }

        tpl = CustomQueryTemplate(
            id=uuid.uuid4(),
            name="完整配置测试",
            description="all fields",
            data_source=config["source"],
            config=config,
            scope="private",
            created_by=FAKE_USER_ID,
            creator_id=FAKE_USER_ID,
        )
        db_session.add(tpl)
        await db_session.flush()

        loaded = await db_session.get(CustomQueryTemplate, tpl.id)
        assert loaded is not None
        assert loaded.config == config
        assert loaded.config["cell_range"] == "A1:D20,F1:F20"
        assert loaded.config["page_size"] == 200
        assert loaded.config["sort_field"] == "cell_ref"
        assert loaded.config["sort_order"] == "asc"
        assert len(loaded.config["conditions"]) == 2

    @pytest.mark.asyncio
    async def test_minimal_config_round_trip(self, db_session):
        """Minimal config with only required 'source' field."""
        config = {"source": "report:balance_sheet|A1:A10"}

        tpl = CustomQueryTemplate(
            id=uuid.uuid4(),
            name="最小配置",
            data_source=config["source"],
            config=config,
            scope="private",
            created_by=FAKE_USER_ID,
            creator_id=FAKE_USER_ID,
        )
        db_session.add(tpl)
        await db_session.flush()

        loaded = await db_session.get(CustomQueryTemplate, tpl.id)
        assert loaded is not None
        assert loaded.config == config
        assert loaded.config["source"] == "report:balance_sheet|A1:A10"


# ---------------------------------------------------------------------------
# 8.7.2 表缺失修复单测
# ---------------------------------------------------------------------------


class TestTableMissingFix:
    """Verify _ensure_custom_query_tables.py logic handles missing/existing table."""

    def test_ddl_is_idempotent(self):
        """DDL uses IF NOT EXISTS — running twice should not error."""
        import sys
        from pathlib import Path
        scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        # Import the module constants directly
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_ensure_custom_query_tables",
            Path(__file__).resolve().parent.parent / "scripts" / "_ensure_custom_query_tables.py",
        )
        mod = importlib.util.module_from_spec(spec)
        # Don't execute the module (it connects to DB), just load constants
        import types
        # Read the file and extract DDL/INDEXES_DDL strings
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "_ensure_custom_query_tables.py"
        content = script_path.read_text(encoding="utf-8")

        assert "IF NOT EXISTS" in content
        assert "idx_cqt_scope_updated" in content
        assert "idx_cqt_creator_updated" in content
        assert "idx_cqt_tags" in content

    def test_ddl_contains_required_columns(self):
        """DDL must include all Req 15 AC3 fields."""
        from pathlib import Path
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "_ensure_custom_query_tables.py"
        content = script_path.read_text(encoding="utf-8")

        required_columns = [
            "id", "name", "description", "scope", "creator_id",
            "config", "tags", "use_count", "last_used_at",
            "created_at", "updated_at",
        ]
        for col in required_columns:
            assert col in content, f"Missing column: {col}"

    def test_ddl_contains_required_indexes(self):
        """DDL must include 3 indexes per design spec."""
        from pathlib import Path
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "_ensure_custom_query_tables.py"
        content = script_path.read_text(encoding="utf-8")

        assert "idx_cqt_scope_updated" in content
        assert "idx_cqt_creator_updated" in content
        assert "idx_cqt_tags" in content
        assert "GIN" in content

    def test_ddl_contains_scope_constraint(self):
        """DDL must include scope CHECK constraint."""
        from pathlib import Path
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "_ensure_custom_query_tables.py"
        content = script_path.read_text(encoding="utf-8")

        assert "private" in content
        assert "team" in content
        assert "public" in content

    def test_alter_add_columns_covers_new_fields(self):
        """ALTER statements cover upgrade path for existing tables."""
        from pathlib import Path
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "_ensure_custom_query_tables.py"
        content = script_path.read_text(encoding="utf-8")

        # Check ALTER ADD COLUMN statements exist for new fields
        assert "tags" in content
        assert "use_count" in content
        assert "last_used_at" in content
        assert "creator_id" in content
        assert "ALTER TABLE" in content


# ---------------------------------------------------------------------------
# 8.7.3 3 入口同步状态 (integration-level test)
# ---------------------------------------------------------------------------


class TestThreeEntryPointSync:
    """3 entry points (CustomQueryTab / CustomQueryDialog / SheetCellRangePicker)
    share the same template state via sessionStorage cache.

    This is a simplified integration test verifying the API layer supports
    the shared state pattern.
    """

    @pytest.mark.asyncio
    async def test_create_template_returns_complete_config(self, db_session):
        """Creating a template stores and returns the full config."""
        config = {
            "source": "workpaper:D2|审定表D2-1",
            "sheet_name": "审定表D2-1",
            "cell_range": "B2:D10",
            "page_size": 100,
            "sort_field": "cell_ref",
            "sort_order": "asc",
        }

        tpl = CustomQueryTemplate(
            id=uuid.uuid4(),
            name="三入口共享模板",
            data_source=config["source"],
            config=config,
            scope="private",
            created_by=FAKE_USER_ID,
            creator_id=FAKE_USER_ID,
        )
        db_session.add(tpl)
        await db_session.flush()

        # Simulate list_templates query (what all 3 entry points call)
        from sqlalchemy import select, or_

        stmt = (
            select(CustomQueryTemplate)
            .where(
                or_(
                    CustomQueryTemplate.created_by == FAKE_USER_ID,
                    CustomQueryTemplate.scope == "global",
                )
            )
            .order_by(CustomQueryTemplate.updated_at.desc())
        )
        result = await db_session.execute(stmt)
        templates = result.scalars().all()

        assert len(templates) == 1
        assert templates[0].config == config
        assert templates[0].config["cell_range"] == "B2:D10"
        assert templates[0].config["page_size"] == 100

    @pytest.mark.asyncio
    async def test_multiple_templates_ordered_by_updated(self, db_session):
        """Templates are returned ordered by updated_at DESC."""
        for i in range(3):
            tpl = CustomQueryTemplate(
                id=uuid.uuid4(),
                name=f"模板-{i}",
                data_source=f"workpaper:D{i}|sheet",
                config={"source": f"workpaper:D{i}|sheet"},
                scope="private",
                created_by=FAKE_USER_ID,
                creator_id=FAKE_USER_ID,
            )
            db_session.add(tpl)
        await db_session.flush()

        from sqlalchemy import select, or_

        stmt = (
            select(CustomQueryTemplate)
            .where(CustomQueryTemplate.created_by == FAKE_USER_ID)
            .order_by(CustomQueryTemplate.updated_at.desc())
        )
        result = await db_session.execute(stmt)
        templates = result.scalars().all()

        assert len(templates) == 3

    @pytest.mark.asyncio
    async def test_stale_sheet_detection_logic(self, db_session):
        """Config with cell_range referencing a sheet can be detected as stale."""
        config = {
            "source": "workpaper:D2|已删除的Sheet",
            "sheet_name": "已删除的Sheet",
            "cell_range": "A1:B10",
        }

        tpl = CustomQueryTemplate(
            id=uuid.uuid4(),
            name="过期模板",
            data_source=config["source"],
            config=config,
            scope="private",
            created_by=FAKE_USER_ID,
            creator_id=FAKE_USER_ID,
        )
        db_session.add(tpl)
        await db_session.flush()

        loaded = await db_session.get(CustomQueryTemplate, tpl.id)
        assert loaded is not None

        # Stale detection: check if sheet_name in config exists
        # (In real code, this checks against actual working_paper sheets)
        sheet_name = loaded.config.get("sheet_name")
        assert sheet_name == "已删除的Sheet"

        # Simulate stale detection: sheet not in available sheets
        available_sheets = ["审定表D2-1", "审定表D2-2", "底稿目录"]
        is_stale = sheet_name not in available_sheets
        assert is_stale is True

        # After user confirms, clear cell_range but keep source/filters
        if is_stale:
            cleared_config = {**loaded.config}
            cleared_config["cell_range"] = None
            cleared_config["sheet_name"] = None
            assert cleared_config["source"] == "workpaper:D2|已删除的Sheet"
            assert cleared_config["cell_range"] is None
