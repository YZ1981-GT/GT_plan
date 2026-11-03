from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.services import formula_provenance
from app.services.note_readiness_service import (
    ProjectNoteMappingInvalid,
    resolve_section_workpapers,
)

ROOT = Path(__file__).resolve().parents[2]


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Db:
    def __init__(self, project):
        self.project = project

    async def execute(self, _statement):
        return _Result(self.project)


@pytest.mark.asyncio
async def test_registry_mapping_preserves_many_to_many_and_account_mapping(monkeypatch):
    project = SimpleNamespace(
        template_type="soe",
        wizard_state={},
        is_deleted=False,
    )
    monkeypatch.setattr(
        "app.services.note_readiness_service._strict_registry_entries",
        lambda: (
            {"wp_code": "D1", "soe": "八、4"},
            {"wp_code": "D2", "soe_sections": {"extra": "八、4"}},
        ),
    )

    async def mappings(_self, _template, _section):
        return [SimpleNamespace(
            report_row_code="BS-002", note_section_code="八、4", table_index=1,
            validation_role="余额", wp_code="D1", fetch_mode="total",
        )]

    monkeypatch.setattr(
        "app.services.note_account_mapping_service.NoteAccountMappingService.get_mapping_for_section",
        mappings,
    )
    resolved = await resolve_section_workpapers(_Db(project), UUID(int=1), "八、4")
    assert resolved.status == "mapped"
    assert resolved.wp_codes == ("D1", "D2")
    assert resolved.account_mappings[0]["report_row_code"] == "BS-002"


@pytest.mark.asyncio
async def test_registry_missing_section_is_normal_not_found(monkeypatch):
    project = SimpleNamespace(template_type="listed", wizard_state={}, is_deleted=False)
    monkeypatch.setattr(
        "app.services.note_readiness_service._strict_registry_entries",
        lambda: ({"wp_code": "D1", "listed": "五、4"},),
    )
    monkeypatch.setattr(
        "app.services.note_account_mapping_service.NoteAccountMappingService.get_mapping_for_section",
        lambda *_args: _empty_async(),
    )
    resolved = await resolve_section_workpapers(_Db(project), UUID(int=1), "五、999")
    assert resolved.status == "not_found"
    assert resolved.wp_codes == ()


async def _empty_async():
    return []


@pytest.mark.asyncio
async def test_invalid_project_override_is_explicit_error(monkeypatch):
    project = SimpleNamespace(
        template_type="soe", wizard_state={"note_wp_mapping": {"八、4": ["UNKNOWN"]}}, is_deleted=False,
    )
    monkeypatch.setattr(
        "app.services.note_readiness_service._strict_registry_entries",
        lambda: ({"wp_code": "D1", "soe": "八、4"},),
    )
    with pytest.raises(ProjectNoteMappingInvalid):
        await resolve_section_workpapers(_Db(project), UUID(int=1), "八、4")


def test_report_trace_source_has_no_legacy_mapping_table_sql():
    source = (ROOT / "app" / "services" / "report_trace_service.py").read_text(encoding="utf-8")
    assert "note_wp_mapping" not in source
    assert "account_codes" not in source
    tree = ast.parse(source)
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resolve_section_workpapers"
        for node in ast.walk(tree)
    )


def test_report_provenance_migration_matches_model_surface():
    migration = (ROOT / "migrations" / "V251__formula_provenance_report_runs.sql").read_text(encoding="utf-8")
    rollback = (ROOT / "migrations" / "R251__rollback_formula_provenance_report_runs.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS report_generation_run" in migration
    assert "ALTER TABLE financial_report ADD COLUMN IF NOT EXISTS run_id" in migration
    assert "ALTER TABLE financial_report ADD COLUMN IF NOT EXISTS provenance" in migration
    assert "DROP TABLE IF EXISTS report_generation_run" in rollback
    push_migration = (ROOT / "migrations" / "V248__formula_push_provenance.sql").read_text(encoding="utf-8")
    push_rollback = (ROOT / "migrations" / "R248__rollback_formula_push_provenance.sql").read_text(encoding="utf-8")
    assert "formula_push_state ADD COLUMN IF NOT EXISTS provenance" in push_migration
    assert "formula_push_state DROP COLUMN IF EXISTS provenance" in push_rollback
    from app.models.formula_push_models import FormulaPushState
    assert "provenance" in FormulaPushState.__table__.columns
    note_migration = (ROOT / "migrations" / "V249__note_formula_runs.sql").read_text(encoding="utf-8")
    note_rollback = (ROOT / "migrations" / "R249__rollback_note_formula_runs.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS note_formula_run" in note_migration
    assert "DROP TABLE IF EXISTS note_formula_run" in note_rollback
    from app.models.note_formula_models import NoteFormulaRun
    assert "note_formula_run" == NoteFormulaRun.__tablename__
    assert hasattr(formula_provenance, "ProvenanceEnvelopeV1")
    assert hasattr(formula_provenance, "FinalValueProvenanceV1")


def test_report_provenance_route_is_registered_before_generic_report_route():
    from fastapi.routing import APIRoute
    from app.models.report_schemas import ReportProvenanceResponse
    from app.routers.reports import router

    provenance_routes = [
        route for route in router.routes
        if isinstance(route, APIRoute) and route.path.endswith("/rows/{row_code}/provenance")
    ]
    assert len(provenance_routes) == 1
    assert provenance_routes[0].response_model is ReportProvenanceResponse
    generic = next(route for route in router.routes if isinstance(route, APIRoute) and route.path.endswith("/{report_type}"))
    assert router.routes.index(provenance_routes[0]) < router.routes.index(generic)


def test_no_runtime_sql_reads_or_writes_legacy_note_wp_mapping_table():
    pattern = __import__('re').compile(r"\b(?:FROM|JOIN|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+[\"']?note_wp_mapping\b", __import__('re').I)
    violations: list[str] = []
    for path in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and pattern.search(node.value):
                violations.append(str(path.relative_to(ROOT)))
    assert violations == []
    assert pattern.search("SELECT * FROM note_wp_mapping")


def _function(tree: ast.AST, name: str):
    hits = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    assert len(hits) == 1, (name, len(hits))
    return hits[0]


def _called_names(function: ast.AST) -> set[str]:
    return {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }


def test_note_and_push_provenance_writers_have_runtime_fences_and_actor_wiring():
    note_source = (ROOT / "app" / "services" / "note_formula_provenance.py").read_text(encoding="utf-8")
    note_tree = ast.parse(note_source)
    note_run = _function(note_tree, "execute_with_run")
    assert {"_note_run_lock", "_advisory_lock"} <= _called_names(note_run)

    router_source = (ROOT / "app" / "routers" / "disclosure_notes.py").read_text(encoding="utf-8")
    apply = _function(ast.parse(router_source), "apply_formulas")
    calls = [
        node for node in ast.walk(apply)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "execute_note_formulas"
    ]
    assert len(calls) == 1
    keywords = {keyword.arg: keyword.value for keyword in calls[0].keywords}
    actor = keywords.get("triggered_by")
    assert isinstance(actor, ast.Attribute) and isinstance(actor.value, ast.Name)
    assert (actor.value.id, actor.attr) == ("current_user", "id")

    push_source = (ROOT / "app" / "services" / "formula_push" / "engine.py").read_text(encoding="utf-8")
    push_run = _function(ast.parse(push_source), "run")
    assert {"_process_lock", "_advisory_lock", "_execute"} <= _called_names(push_run)
