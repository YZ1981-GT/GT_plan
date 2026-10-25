"""Task 8: WpFormula source_scope/binding 持久化与校验契约。"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.workpaper_models import WpFormula
from app.routers.wp_formula import _formula_issue_error_code
from app.services.wp_formula_service import WpFormulaService


# SQLite 测试方言：保持与现有 WpFormula 测试相同的 UUID/JSONB 建表兼容处理。
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


@pytest.fixture(autouse=True)
def _stub_external_validation_and_reference_invalidation():
    with patch.object(
        WpFormulaService, "_verify_wp_ownership", new=AsyncMock(return_value=True)
    ), patch(
        "app.services.wp_formula_service.validate_refs_via_acnr",
        new_callable=AsyncMock,
        return_value=[],
    ), patch.object(
        WpFormulaService,
        "_invalidate_reference_dependents",
        new=AsyncMock(return_value=0),
    ):
        yield


@pytest.fixture
async def formula_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: WpFormula.__table__.create(
                sync_connection, checkfirst=True
            )
        )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _scope(project_id: uuid.UUID, *, year: int = 2025) -> dict:
    return {
        "project_id": str(project_id),
        "year": year,
        "node_key": "  parent-node  ",
        "include_descendants": True,
        "domains": ["report", "note", "workpaper", "consol_worksheet"],
    }


def _binding() -> dict:
    return {
        "kind": "related_transaction",
        "template": "  node_total  ",
        "parameters": {"direction": "closing", "include_elimination": False},
    }


async def _save(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    source_scope: dict | None,
    binding: dict | None,
):
    return await WpFormulaService().save(
        db,
        project_id=project_id,
        wp_id=wp_id,
        sheet_name="合并工作底稿",
        target_cell="B5",
        expression="1+2",
        year=2025,
        source_scope=source_scope,
        binding=binding,
    )


@pytest.mark.asyncio
async def test_source_scope_and_binding_save_and_fresh_session_roundtrip(
    formula_session_factory,
):
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()
    source_scope = _scope(project_id)
    binding = _binding()

    async with formula_session_factory() as db:
        saved, issues = await _save(
            db,
            project_id=project_id,
            wp_id=wp_id,
            source_scope=source_scope,
            binding=binding,
        )
        assert issues == []
        assert saved is not None
        await db.commit()

    # 用新 session 读回，证明字段已落库，不只是 ORM 对象内存属性。
    async with formula_session_factory() as fresh_db:
        loaded = (
            await fresh_db.get(WpFormula, saved.id)
        )
        assert loaded is not None
        assert loaded.source_scope == {
            **source_scope,
            "project_id": str(project_id),
            "node_key": "parent-node",
        }
        assert loaded.binding == {
            "kind": "related_transaction",
            "template": "node_total",
            "parameters": {"direction": "closing", "include_elimination": False},
        }


@pytest.mark.asyncio
async def test_scope_or_binding_change_updates_definition_hash_and_version(
    formula_session_factory,
):
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()

    async with formula_session_factory() as db:
        first, first_issues = await _save(
            db,
            project_id=project_id,
            wp_id=wp_id,
            source_scope=_scope(project_id),
            binding=_binding(),
        )
        assert first_issues == []
        assert first is not None
        first_hash = first.definition_hash
        first_version = first.definition_version
        await db.commit()

        changed_scope = _scope(project_id)
        changed_scope["node_key"] = "child-node"
        changed_binding = _binding()
        changed_binding["parameters"] = {"direction": "opening"}
        second, second_issues = await _save(
            db,
            project_id=project_id,
            wp_id=wp_id,
            source_scope=changed_scope,
            binding=changed_binding,
        )
        assert second_issues == []
        assert second is not None
        assert second.id == first.id
        assert second.definition_hash != first_hash
        assert second.definition_version == first_version + 1
        await db.commit()

    async with formula_session_factory() as fresh_db:
        loaded = await fresh_db.get(WpFormula, first.id)
        assert loaded is not None
        assert loaded.definition_hash == second.definition_hash
        assert loaded.definition_version == second.definition_version
        assert loaded.source_scope["node_key"] == "child-node"
        assert loaded.binding["parameters"] == {"direction": "opening"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_scope", "binding", "expected_status"),
    [
        (
            {
                "project_id": str(uuid.uuid4()),
                "year": 2025,
                "include_descendants": True,
                "domains": ["report"],
            },
            None,
            "source_scope_project_mismatch",
        ),
        (
            {
                "project_id": "not-a-uuid",
                "year": 2025,
                "include_descendants": True,
                "domains": ["report"],
            },
            None,
            "invalid_source_scope",
        ),
        (
            {
                "project_id": "00000000-0000-0000-0000-000000000001",
                "year": 2025,
                "include_descendants": True,
                "domains": ["unknown_domain"],
            },
            None,
            "invalid_source_scope",
        ),
        (
            {
                "project_id": "00000000-0000-0000-0000-000000000001",
                "year": 2025,
                "include_descendants": True,
                "domains": ["report"],
                "node_key": "   ",
            },
            None,
            "invalid_source_scope",
        ),
        (
            None,
            {"kind": "related_transaction", "parameters": []},
            "invalid_binding",
        ),
        (
            None,
            {"kind": "related_transaction", "unexpected": True},
            "invalid_binding",
        ),
    ],
)
async def test_invalid_source_scope_or_binding_is_rejected_without_insert(
    formula_session_factory,
    source_scope,
    binding,
    expected_status,
):
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()
    if source_scope is not None and expected_status == "source_scope_project_mismatch":
        # 参数化值使用独立 UUID，明确验证项目隔离而非依赖固定样例值。
        source_scope = {**source_scope, "project_id": str(uuid.uuid4())}
    elif (
        source_scope is not None
        and source_scope.get("project_id") == "00000000-0000-0000-0000-000000000001"
    ):
        source_scope = {**source_scope, "project_id": str(project_id)}

    async with formula_session_factory() as db:
        saved, issues = await _save(
            db,
            project_id=project_id,
            wp_id=wp_id,
            source_scope=source_scope,
            binding=binding,
        )
        assert saved is None
        assert issues
        assert issues[0]["status"] == expected_status
        await db.commit()
        assert (
            await db.execute(
                WpFormula.__table__.select().where(WpFormula.wp_id == wp_id)
            )
        ).first() is None


def test_formula_issue_error_codes_do_not_collapse_validation_categories():
    assert _formula_issue_error_code([{"status": "not_found"}]) == "FORMULA_REF_NOT_FOUND"
    assert _formula_issue_error_code([{"status": "invalid_source_scope"}]) == "FORMULA_SOURCE_SCOPE_INVALID"
    assert _formula_issue_error_code([{"status": "source_scope_year_mismatch"}]) == "FORMULA_SOURCE_SCOPE_INVALID"
    assert _formula_issue_error_code([{"status": "invalid_binding"}]) == "FORMULA_BINDING_INVALID"
    assert _formula_issue_error_code([{"status": "formula_blocked"}]) == "FORMULA_BLOCKED"
