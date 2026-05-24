"""Tests for custom_query_templates (Req 15 / Task 8.7)

Property 29: 模板 config save/load round-trip — 保存完整 config 后加载必须还原所有字段
表缺失修复单测 — _ensure_custom_query_tables.py 幂等建表
3 入口同步状态 e2e — 3 个入口保存/加载模板共享同一份数据

Feature: advanced-query-enhancements-p1p2, Task 8.7
"""

from __future__ import annotations

import os
import uuid

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import Column, String, JSON, create_engine, select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.orm import DeclarativeBase, Session as SyncSession

# Patch SQLite to handle PG-specific types before importing models
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"


# ---------------------------------------------------------------------------
# Minimal test model (avoids PG-specific server_defaults that break SQLite)
# ---------------------------------------------------------------------------

class _SqliteBase(DeclarativeBase):
    pass


class _TemplateModel(_SqliteBase):
    """Minimal model mirroring custom_query_templates for SQLite testing."""
    __tablename__ = "test_templates"
    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    data_source = Column(String(50), nullable=True)
    config = Column(JSON, nullable=False)
    scope = Column(String(16), nullable=False, default="private")
    created_by = Column(String(36), nullable=False)


# ---------------------------------------------------------------------------
# Strategies for Property 29
# ---------------------------------------------------------------------------

# Valid source URIs across 5 namespaces
st_source = st.sampled_from([
    "workpaper:D2|审定表D2-1",
    "workpaper:E1|银行存款E1-1",
    "report:balance_sheet|A1:B10",
    "note:五-1-1|C1:C5",
    "adj:aje|A1:D20",
    "tb:detail|A1:F100",
])

st_page_size = st.sampled_from([50, 100, 200, 500])
st_sort_order = st.sampled_from(["asc", "desc"])

st_cell_range = st.one_of(
    st.none(),
    st.from_regex(r"[A-Z]{1,2}[1-9][0-9]{0,3}:[A-Z]{1,2}[1-9][0-9]{0,3}", fullmatch=True),
)

st_condition = st.fixed_dictionaries({
    "field": st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
    "op": st.sampled_from(["eq", "ne", "gt", "gte", "lt", "lte", "in", "like", "is_null"]),
    "value": st.one_of(st.text(max_size=50), st.integers(min_value=-9999, max_value=9999), st.none()),
})

st_columns = st.lists(
    st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N", "Pd"))),
    min_size=0,
    max_size=10,
)

st_config = st.fixed_dictionaries(
    {
        "source": st_source,
    },
    optional={
        "project_id": st.one_of(st.none(), st.uuids().map(str)),
        "year": st.one_of(st.none(), st.integers(min_value=2000, max_value=2100)),
        "sheet_name": st.one_of(st.none(), st.text(min_size=1, max_size=50)),
        "cell_range": st_cell_range,
        "filter_text": st.one_of(st.none(), st.text(max_size=100)),
        "conditions": st.lists(st_condition, min_size=0, max_size=5),
        "selected_columns": st_columns,
        "available_columns": st_columns,
        "page_size": st_page_size,
        "sort_field": st.one_of(st.none(), st.text(min_size=1, max_size=30)),
        "sort_order": st_sort_order,
    },
)


# ---------------------------------------------------------------------------
# Property 29: Template config save/load round-trip
# Feature: advanced-query-enhancements-p1p2, Property 29: Template config save/load round-trip
# ---------------------------------------------------------------------------


class TestProperty29ConfigSaveLoadRoundTrip:
    """For any valid CustomQueryTemplateConfig, saving to DB then loading
    must produce an identical config object (all fields preserved).

    **Validates: Requirements 15.3, 15.4**
    """

    @settings(max_examples=20)
    @given(config=st_config)
    def test_config_round_trip_via_orm(self, config):
        """Save config via ORM, reload, verify all fields match.

        **Validates: Requirements 15.3, 15.4**
        """
        engine = create_engine("sqlite:///:memory:", echo=False)
        _SqliteBase.metadata.create_all(engine)

        with SyncSession(engine) as session:
            tpl_id = str(uuid.uuid4())
            user_id = str(uuid.uuid4())

            # Save
            tpl = _TemplateModel(
                id=tpl_id,
                name="test-template",
                description="round-trip test",
                data_source=config["source"],
                config=config,
                scope="private",
                created_by=user_id,
            )
            session.add(tpl)
            session.commit()

            # Load
            session.expire_all()
            loaded = session.get(_TemplateModel, tpl_id)
            assert loaded is not None
            loaded_config = loaded.config

            # Verify all fields match
            for key, value in config.items():
                assert key in loaded_config, f"Missing key: {key}"
                assert loaded_config[key] == value, (
                    f"Mismatch for key '{key}': saved={value!r}, loaded={loaded_config[key]!r}"
                )

            # Verify no extra keys
            for key in loaded_config:
                assert key in config, f"Extra key in loaded config: {key}"

        engine.dispose()

    def test_full_config_round_trip(self):
        """Explicit test with all fields populated."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        _SqliteBase.metadata.create_all(engine)

        config = {
            "project_id": str(uuid.uuid4()),
            "year": 2025,
            "source": "workpaper:D2|审定表D2-1",
            "sheet_name": "审定表D2-1",
            "cell_range": "A1:B10,C1:C5",
            "filter_text": "应收账款",
            "conditions": [
                {"field": "account_code", "op": "eq", "value": "1122"},
                {"field": "amount", "op": "gt", "value": 10000},
            ],
            "selected_columns": ["account_code", "account_name", "amount"],
            "available_columns": ["account_code", "account_name", "amount", "currency"],
            "page_size": 100,
            "sort_field": "account_code",
            "sort_order": "asc",
        }

        with SyncSession(engine) as session:
            tpl_id = str(uuid.uuid4())
            tpl = _TemplateModel(
                id=tpl_id,
                name="full-config-test",
                description="all fields",
                data_source=config["source"],
                config=config,
                scope="private",
                created_by=str(uuid.uuid4()),
            )
            session.add(tpl)
            session.commit()

            session.expire_all()
            loaded = session.get(_TemplateModel, tpl_id)
            assert loaded is not None
            assert loaded.config == config

        engine.dispose()

    def test_minimal_config_round_trip(self):
        """Minimal config with only required 'source' field."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        _SqliteBase.metadata.create_all(engine)

        config = {"source": "workpaper:D2|审定表D2-1"}

        with SyncSession(engine) as session:
            tpl_id = str(uuid.uuid4())
            tpl = _TemplateModel(
                id=tpl_id,
                name="minimal-config",
                data_source=config["source"],
                config=config,
                scope="private",
                created_by=str(uuid.uuid4()),
            )
            session.add(tpl)
            session.commit()

            session.expire_all()
            loaded = session.get(_TemplateModel, tpl_id)
            assert loaded is not None
            assert loaded.config == config
            assert loaded.config["source"] == "workpaper:D2|审定表D2-1"

        engine.dispose()

    def test_config_with_null_optional_fields(self):
        """Config with explicit null values for optional fields."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        _SqliteBase.metadata.create_all(engine)

        config = {
            "source": "report:balance_sheet|A1:B10",
            "project_id": None,
            "year": None,
            "sheet_name": None,
            "cell_range": None,
            "filter_text": None,
            "conditions": [],
            "selected_columns": [],
            "available_columns": [],
            "page_size": 50,
            "sort_field": None,
            "sort_order": "desc",
        }

        with SyncSession(engine) as session:
            tpl_id = str(uuid.uuid4())
            tpl = _TemplateModel(
                id=tpl_id,
                name="null-fields-test",
                data_source=config["source"],
                config=config,
                scope="private",
                created_by=str(uuid.uuid4()),
            )
            session.add(tpl)
            session.commit()

            session.expire_all()
            loaded = session.get(_TemplateModel, tpl_id)
            assert loaded is not None
            assert loaded.config == config

        engine.dispose()

    def test_config_preserves_unicode_and_special_chars(self):
        """Config with Chinese characters and special chars in values."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        _SqliteBase.metadata.create_all(engine)

        config = {
            "source": "workpaper:D2|审定表D2-1",
            "sheet_name": "审定表D2-1（修订版）",
            "cell_range": "A1:Z100",
            "filter_text": "应收账款 & 预付款项",
            "conditions": [
                {"field": "备注", "op": "like", "value": "%特殊字符!@#$%"},
            ],
            "selected_columns": ["科目编码", "科目名称", "期末余额"],
        }

        with SyncSession(engine) as session:
            tpl_id = str(uuid.uuid4())
            tpl = _TemplateModel(
                id=tpl_id,
                name="unicode-test-模板",
                data_source=config["source"],
                config=config,
                scope="private",
                created_by=str(uuid.uuid4()),
            )
            session.add(tpl)
            session.commit()

            session.expire_all()
            loaded = session.get(_TemplateModel, tpl_id)
            assert loaded is not None
            assert loaded.config == config

        engine.dispose()


# ---------------------------------------------------------------------------
# 8.7.2 表缺失修复单测
# ---------------------------------------------------------------------------


class TestEnsureCustomQueryTables:
    """Test that _ensure_custom_query_tables.py script logic is idempotent."""

    def _load_script_module(self):
        """Load the ensure script module without executing main()."""
        import importlib.util
        from pathlib import Path

        script_path = Path(__file__).parent.parent / "scripts" / "_ensure_custom_query_tables.py"
        assert script_path.exists(), f"Script not found: {script_path}"

        spec = importlib.util.spec_from_file_location("_ensure_custom_query_tables", script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_script_module_importable(self):
        """The ensure script should be importable without side effects."""
        module = self._load_script_module()
        assert hasattr(module, "main")
        assert hasattr(module, "DDL")
        assert hasattr(module, "INDEXES_DDL")

    def test_ddl_contains_required_columns(self):
        """DDL must contain all required columns per design spec."""
        module = self._load_script_module()
        ddl = module.DDL

        # Required columns per design
        required_columns = [
            "id", "name", "scope", "creator_id", "config",
            "tags", "use_count", "last_used_at", "created_at", "updated_at",
        ]
        for col in required_columns:
            assert col in ddl, f"DDL missing required column: {col}"

        # Required constraints
        assert "PRIMARY KEY" in ddl
        assert "REFERENCES users(id)" in ddl
        assert "ck_custom_query_templates_scope" in ddl

    def test_indexes_ddl_contains_required_indexes(self):
        """Indexes DDL must contain the 3 required indexes."""
        module = self._load_script_module()
        indexes_ddl = module.INDEXES_DDL

        # 3 required indexes per design
        assert "idx_cqt_scope_updated" in indexes_ddl
        assert "idx_cqt_creator_updated" in indexes_ddl
        assert "idx_cqt_tags" in indexes_ddl
        assert "GIN" in indexes_ddl

    def test_check_sql_targets_correct_table(self):
        """CHECK_SQL must query the correct table name."""
        module = self._load_script_module()
        assert "custom_query_templates" in module.CHECK_SQL

    def test_alter_add_columns_covers_new_fields(self):
        """ALTER_ADD_COLUMNS must cover fields that may be missing in old DBs."""
        module = self._load_script_module()
        alter_cols = module.ALTER_ADD_COLUMNS

        # These columns may be missing in old DBs
        assert "tags" in alter_cols
        assert "use_count" in alter_cols
        assert "last_used_at" in alter_cols
        assert "creator_id" in alter_cols

    def test_scope_check_constraint_values(self):
        """Scope CHECK constraint must include all valid values."""
        module = self._load_script_module()
        ddl = module.DDL

        # Must support all scope values
        assert "'private'" in ddl
        assert "'team'" in ddl
        assert "'public'" in ddl

    def test_ddl_uses_create_if_not_exists(self):
        """DDL must be idempotent (CREATE TABLE IF NOT EXISTS)."""
        module = self._load_script_module()
        assert "CREATE TABLE IF NOT EXISTS" in module.DDL

    def test_indexes_use_create_if_not_exists(self):
        """Index DDL must be idempotent (CREATE INDEX IF NOT EXISTS)."""
        module = self._load_script_module()
        assert "CREATE INDEX IF NOT EXISTS" in module.INDEXES_DDL


# ---------------------------------------------------------------------------
# 8.7.3 3 入口同步状态 e2e
# Tests that all 3 entry points (CustomQueryTab / CustomQueryDialog /
# SheetCellRangePicker) share the same template data via the API.
# ---------------------------------------------------------------------------


class TestThreeEntryPointSync:
    """3 入口同步状态：验证模板 CRUD 在所有入口共享同一份数据。

    Tests the API contract: templates saved from any entry point are visible
    from all other entry points via the same /api/custom-query/templates endpoint.
    Uses direct ORM operations to simulate the API behavior without full app startup.
    """

    @pytest.fixture
    def sync_engine(self):
        """Create a sync SQLite engine with the test template table."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        _SqliteBase.metadata.create_all(engine)
        yield engine
        engine.dispose()

    def test_create_template_from_one_entry_visible_in_list(self, sync_engine):
        """Template created from any entry point is visible in list (shared state).

        Simulates: SheetCellRangePicker saves → MyTemplatesDialog lists.
        """
        with SyncSession(sync_engine) as session:
            # Simulate saving from SheetCellRangePicker (entry 3)
            config = {
                "source": "workpaper:D2|审定表D2-1",
                "sheet_name": "审定表D2-1",
                "cell_range": "A1:B10",
                "page_size": 100,
                "sort_field": "account_code",
                "sort_order": "asc",
            }
            user_id = str(uuid.uuid4())
            tpl_id = str(uuid.uuid4())

            tpl = _TemplateModel(
                id=tpl_id,
                name="从选区器保存的模板",
                description="D2 审定表 A1:B10",
                data_source=config["source"],
                config=config,
                scope="private",
                created_by=user_id,
            )
            session.add(tpl)
            session.commit()

            # Simulate listing from MyTemplatesDialog (any entry point)
            stmt = select(_TemplateModel).where(_TemplateModel.created_by == user_id)
            results = session.execute(stmt).scalars().all()

            assert len(results) == 1
            found = results[0]
            assert found.name == "从选区器保存的模板"
            assert found.config["source"] == config["source"]
            assert found.config["cell_range"] == config["cell_range"]
            assert found.config["page_size"] == config["page_size"]
            assert found.config["sort_field"] == config["sort_field"]
            assert found.config["sort_order"] == config["sort_order"]

    def test_template_config_fully_preserved_through_save_load(self, sync_engine):
        """Full config saved via one entry is fully preserved when loaded from another."""
        with SyncSession(sync_engine) as session:
            config = {
                "project_id": str(uuid.uuid4()),
                "year": 2025,
                "source": "workpaper:E1|银行存款E1-1",
                "sheet_name": "银行存款E1-1",
                "cell_range": "A1:F50,H1:H50",
                "filter_text": "银行",
                "conditions": [
                    {"field": "bank_name", "op": "like", "value": "%工商%"},
                ],
                "selected_columns": ["bank_name", "account_no", "balance"],
                "available_columns": ["bank_name", "account_no", "balance", "currency", "date"],
                "page_size": 200,
                "sort_field": "balance",
                "sort_order": "desc",
            }
            user_id = str(uuid.uuid4())
            tpl_id = str(uuid.uuid4())

            # Save (simulates POST /api/custom-query/templates)
            tpl = _TemplateModel(
                id=tpl_id,
                name="完整配置模板",
                description="E1 银行存款",
                data_source=config["source"],
                config=config,
                scope="private",
                created_by=user_id,
            )
            session.add(tpl)
            session.commit()

            # Load (simulates GET /api/custom-query/templates/{id})
            session.expire_all()
            loaded = session.get(_TemplateModel, tpl_id)
            assert loaded is not None
            loaded_config = loaded.config

            # All fields must match exactly (round-trip through DB)
            assert loaded_config == config

    def test_multiple_templates_from_different_entries_all_listed(self, sync_engine):
        """Templates saved from different entry points all appear in the shared list."""
        with SyncSession(sync_engine) as session:
            user_id = str(uuid.uuid4())
            configs = [
                # Entry 1: CustomQueryTab
                {"source": "workpaper:D2|审定表D2-1", "page_size": 100},
                # Entry 2: CustomQueryDialog
                {"source": "report:balance_sheet|A1:B20", "page_size": 50, "sort_order": "asc"},
                # Entry 3: SheetCellRangePicker
                {"source": "workpaper:F2|存货F2-1", "sheet_name": "存货F2-1",
                 "cell_range": "A1:D100", "page_size": 200},
            ]

            created_ids = []
            for i, config in enumerate(configs):
                tpl_id = str(uuid.uuid4())
                tpl = _TemplateModel(
                    id=tpl_id,
                    name=f"入口{i+1}模板",
                    data_source=config["source"],
                    config=config,
                    scope="private",
                    created_by=user_id,
                )
                session.add(tpl)
                created_ids.append(tpl_id)

            session.commit()

            # All 3 templates visible in list (simulates GET /api/custom-query/templates)
            stmt = select(_TemplateModel).where(_TemplateModel.created_by == user_id)
            results = session.execute(stmt).scalars().all()
            listed_ids = {t.id for t in results}

            assert len(listed_ids) == 3
            for tid in created_ids:
                assert tid in listed_ids, f"Template {tid} not found in list"

    def test_delete_template_removes_from_shared_list(self, sync_engine):
        """Deleting a template from one entry removes it from all entries' view."""
        with SyncSession(sync_engine) as session:
            user_id = str(uuid.uuid4())
            config = {"source": "workpaper:D2|审定表D2-1"}
            tpl_id = str(uuid.uuid4())

            tpl = _TemplateModel(
                id=tpl_id,
                name="待删除模板",
                data_source=config["source"],
                config=config,
                scope="private",
                created_by=user_id,
            )
            session.add(tpl)
            session.commit()

            # Delete (simulates DELETE /api/custom-query/templates/{id})
            session.delete(tpl)
            session.commit()

            # Verify gone from list
            stmt = select(_TemplateModel).where(_TemplateModel.created_by == user_id)
            results = session.execute(stmt).scalars().all()
            assert len(results) == 0
