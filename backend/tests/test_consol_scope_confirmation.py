"""D5 persisted scope confirmation: real HTTP authorization and SQLite transactions."""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.consolidation_models import ConsolScope, ConsolTrial, ConsolWorksheet, EliminationEntry
from app.models.consol_worksheet_data_models import ConsolWorksheetData
from app.models.consol_scope_confirmation_models import (
    ConsolScopeConfirmation, ConsolScopeConfirmationNode,
)
from app.models.extension_models import AccountingStandard
from app.routers.consol_scope_confirmation import router
from app.services import consol_calc_basis as calc
from app.services import consol_scope_confirmation_service as svc
from app.services.consol_group_tree import build_group_tree
from app.services.consol_tree_service import build_tree, build_tree_view, iter_nodes

ROOT = Path(__file__).resolve().parents[2]
_TABLES = [User.__table__, AccountingStandard.__table__, Project.__table__,
           ProjectUser.__table__, ConsolScope.__table__, ConsolTrial.__table__,
           ConsolWorksheet.__table__, ConsolWorksheetData.__table__, TrialBalance.__table__,
           EliminationEntry.__table__, ConsolScopeConfirmation.__table__,
           ConsolScopeConfirmationNode.__table__]


def _project(pid, code, scope="standalone", *, parent="P", ultimate="P", relation=None, year=2025):
    return Project(id=pid, name=f"{code}_{year}", client_name=code, company_code=code,
                   audit_year=year, report_scope=scope, parent_company_code=parent,
                   ultimate_company_code=ultimate, relation_to_parent=relation,
                   consol_lock=False)

@pytest_asyncio.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
        # 模拟 V183 迁移已正式执行，让确认门在本环境中生效
        await conn.execute(sa.text(
            "CREATE TABLE IF NOT EXISTS schema_version "
            "(version VARCHAR(20), filename VARCHAR(255), applied_at TIMESTAMP, checksum VARCHAR(64))"
        ))
        await conn.execute(sa.text(
            "INSERT INTO schema_version(version, filename, applied_at, checksum) "
            "VALUES ('183', 'V183__consol_scope_confirmation.sql', '2026-10-08T00:00:00', '0')"
        ))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = {key: uuid.uuid4() for key in ("p", "parent", "branch", "sub", "other", "edit", "read", "stranger")}
    async with factory() as db:
        for key in ("edit", "read", "stranger"):
            db.add(User(id=ids[key], username=key, email=f"{key}@test.invalid",
                        hashed_password="unused", role=UserRole.auditor))
        await db.flush()
        db.add_all([
            _project(ids["p"], "P", "consolidated"),
            _project(ids["parent"], "P"),
            _project(ids["branch"], "B", relation="branch"),
            _project(ids["sub"], "S", relation="subsidiary"),
            _project(ids["other"], "OTHER", "consolidated", parent=None, ultimate="OTHER"),
        ])
        await db.flush()
        for key, level in (("edit", PermissionLevel.edit), ("read", PermissionLevel.readonly)):
            db.add(ProjectUser(project_id=ids["p"], user_id=ids[key],
                               role=ProjectUserRole.auditor, permission_level=level))
        for key, amount in (("parent", "100"), ("branch", "20"), ("sub", "30")):
            db.add(TrialBalance(project_id=ids[key], year=2025, company_code={"parent": "P", "branch": "B", "sub": "S"}[key],
                                standard_account_code="1001", account_name="Cash", account_category=AccountCategory.asset,
                                audited_amount=Decimal(amount)))
        await db.commit()
        actors = {key: await db.get(User, ids[key]) for key in ("edit", "read", "stranger")}

    current = {"actor": actors["edit"]}
    app = FastAPI()
    app.include_router(router)

    async def override_db():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: current["actor"]
    with patch("app.deps._get_cached_permission", new=AsyncMock(return_value=None)), patch(
        "app.deps._set_cached_permission", new=AsyncMock()
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield {"client": client, "factory": factory, "ids": ids,
                   "set_actor": lambda key: current.update(actor=actors[key])}
    await engine.dispose()


async def _preview(env, pid=None):
    response = await env["client"].get(f"/api/consolidation/{pid or env['ids']['p']}/scope-confirmation/preview")
    assert response.status_code == 200, response.text
    return response.json()


async def _confirm(env, preview=None, **changes):
    preview = preview or await _preview(env)
    body = {"expected_fingerprint": preview["fingerprint"], "expected_revision": preview["revision"], **changes}
    return await env["client"].post(f"/api/consolidation/{env['ids']['p']}/scope-confirmation/confirm", json=body)


async def _counts(env):
    async with env["factory"]() as db:
        return tuple([await db.scalar(sa.select(sa.func.count()).select_from(model))
                      for model in (ConsolScopeConfirmation, ConsolScopeConfirmationNode)])


@pytest.mark.asyncio
async def test_preview_is_read_only_and_new_tree_cannot_compute(env):
    preview = await _preview(env)
    assert preview["revision"] == 0 and not preview["confirmed"]
    assert not preview["pending_legacy"]
    assert preview["pending_confirmation"] and preview["can_confirm"]
    assert await _counts(env) == (0, 0)
    async with env["factory"]() as db:
        with pytest.raises(HTTPException) as error:
            await calc.load_calc_basis(db, env["ids"]["p"], 2025)
        assert error.value.status_code == 409
        assert error.value.detail["error_code"] == "SCOPE_CONFIRMATION_REQUIRED"
        assert await build_tree_view(db, env["ids"]["p"]) is not None


@pytest.mark.asyncio
async def test_legacy_boundary_requires_pre183_data_and_explicit_read_switch(env):
    cutoff = datetime(2026, 10, 8, tzinfo=timezone.utc)  # schema_version applied_at
    legacy_created = datetime(2026, 9, 1, tzinfo=timezone.utc)
    async with env["factory"]() as db:
        project = await db.get(Project, env["ids"]["p"])
        project.created_at = legacy_created
        db.add_all([
            ConsolScope(project_id=env["ids"]["p"], year=2025, company_code="S", created_at=legacy_created),
            ConsolTrial(project_id=env["ids"]["p"], year=2025, standard_account_code="1001", created_at=legacy_created),
            ConsolWorksheet(project_id=env["ids"]["p"], node_company_code="P:parent",
                            account_code="1001", year=2025, created_at=legacy_created),
            ConsolWorksheetData(project_id=env["ids"]["p"], year=2025, sheet_key="legacy", data={},
                                created_at=legacy_created),
        ])
        await db.commit()

    preview = await _preview(env)
    assert preview["pending_legacy"] is True
    assert preview["confirmed"] is False
    async with env["factory"]() as db:
        with pytest.raises(HTTPException) as error:
            await calc.load_calc_basis(db, env["ids"]["p"], 2025)
        assert error.value.status_code == 409
        assert error.value.detail["error_code"] == "SCOPE_CONFIRMATION_REQUIRED"
        basis = await calc.load_calc_basis(db, env["ids"]["p"], 2025, allow_legacy_read=True)
        assert basis is not None


@pytest.mark.asyncio
async def test_schema_marker_without_pre183_data_does_not_mark_new_project_as_legacy(env):
    # env fixture 已建 schema_version 并插入了 V183，项目是新建的（created_at 不早于 applied_at）
    preview = await _preview(env)
    assert preview["pending_legacy"] is False
    async with env["factory"]() as db:
        with pytest.raises(HTTPException) as error:
            await calc.load_calc_basis(db, env["ids"]["p"], 2025, allow_legacy_read=True)
        assert error.value.status_code == 409
        assert error.value.detail["error_code"] == "SCOPE_CONFIRMATION_REQUIRED"


@pytest.mark.asyncio
async def test_confirmation_persists_once_and_parent_branch_amounts_are_not_doubled(env):
    preview = await _preview(env)
    response = await _confirm(env, preview)
    assert response.status_code == 200, response.text
    confirmed = response.json()
    assert confirmed["confirmed"] and confirmed["revision"] == 1
    assert not confirmed["pending_legacy"] and not confirmed["pending_confirmation"]
    repeat = await _confirm(env, preview)
    assert repeat.status_code == 200 and repeat.json() == confirmed
    assert await _counts(env) == (1, len(preview["nodes"]))
    assert len({node["node_key"] for node in preview["nodes"]}) == len(preview["nodes"])
    parent = next(node for node in preview["nodes"] if node["node_key"] == "P:parent")
    assert parent["role"] == "parent" and parent["kind"] == "aggregate" and parent["project_id"] is None
    children = [node["role"] for node in preview["nodes"] if node["parent_node_key"] == "P:parent"]
    assert children == ["branch_elim", "hq", "branch"]
    async with env["factory"]() as db:
        stored = (await db.execute(sa.select(ConsolScopeConfirmation))).scalar_one()
        assert stored.confirmed_by == env["ids"]["edit"] and stored.confirmed_at is not None
        assert svc.fingerprint_payload(stored.canonical_payload) == preview["fingerprint"]
        snapshots = (await db.execute(sa.select(ConsolScopeConfirmationNode))).scalars().all()
        assert {s.node_key for s in snapshots} == {n["node_key"] for n in preview["nodes"]}
        assert next(s for s in snapshots if s.role == "hq").project_id == env["ids"]["parent"]
        assert next(s for s in snapshots if s.role == "consol_elim").host_project_id == env["ids"]["p"]
        basis = await calc.load_calc_basis(db, env["ids"]["p"], 2025)
        assert basis is not None
        assert basis.leaf_amounts == {"P:hq": {"1001": Decimal("100.00")},
                                     "B:branch": {"1001": Decimal("20.00")},
                                     "S:subsidiary": {"1001": Decimal("30.00")}}
        rows = calc.node_amount_rows(basis, "P:consol")
        assert Decimal(rows[0]["consolidated_amount"]) == Decimal("150")


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["read", "stranger"])
async def test_http_confirmation_rejects_non_edit_members(env, actor):
    preview = await _preview(env)
    env["set_actor"](actor)
    response = await _confirm(env, preview)
    assert response.status_code == 403
    assert await _counts(env) == (0, 0)


@pytest.mark.asyncio
async def test_preview_has_real_project_isolation_and_anonymous_authentication(env):
    assert (await env["client"].get(f"/api/consolidation/{env['ids']['other']}/scope-confirmation/preview")).status_code == 403
    env["set_actor"]("stranger")
    assert (await env["client"].get(f"/api/consolidation/{env['ids']['p']}/scope-confirmation/preview")).status_code == 403
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/consolidation/{env['ids']['p']}/scope-confirmation/preview")
        assert response.status_code == 401
        response = await client.post(f"/api/consolidation/{env['ids']['p']}/scope-confirmation/confirm",
                                     json={"expected_fingerprint": "0" * 64, "expected_revision": 0})
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_locked_project_is_previewable_but_cannot_confirm(env):
    async with env["factory"]() as db:
        project = await db.get(Project, env["ids"]["p"])
        project.consol_lock = True
        await db.commit()
    preview = await _preview(env)
    assert not preview["can_confirm"]
    response = await _confirm(env, preview)
    assert response.status_code == 423
    assert response.json()["detail"]["error_code"] == "CONSOL_PROJECT_LOCKED"
    assert await _counts(env) == (0, 0)


@pytest.mark.asyncio
async def test_fingerprint_and_revision_cas_rejections_return_latest_preview(env):
    preview = await _preview(env)
    for changes, code in (({"expected_fingerprint": "0" * 64}, "SCOPE_FINGERPRINT_CONFLICT"),
                          ({"expected_revision": 7}, "SCOPE_REVISION_CONFLICT")):
        response = await _confirm(env, preview, **changes)
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["error_code"] == code and detail["latest_preview"] == preview
        assert await _counts(env) == (0, 0)
    assert (await _confirm(env, preview)).status_code == 200
    assert (await _confirm(env, preview, expected_revision=42)).status_code == 409


@pytest.mark.asyncio
async def test_tree_changes_invalidate_gate_and_reconfirmation_cas_preserves_history(env):
    old = await _preview(env)
    assert (await _confirm(env, old)).status_code == 200
    async with env["factory"]() as db:
        project = await db.get(Project, env["ids"]["sub"])
        project.relation_to_parent = "branch"
        await db.commit()
    latest = await _preview(env)
    assert latest["revision"] == 1 and not latest["confirmed"]
    assert latest["fingerprint"] != old["fingerprint"]
    response = await _confirm(env, old)
    assert response.status_code == 409 and response.json()["detail"]["latest_preview"] == latest
    response = await _confirm(env, latest, expected_revision=0)
    assert response.status_code == 409 and response.json()["detail"]["error_code"] == "SCOPE_REVISION_CONFLICT"
    async with env["factory"]() as db:
        with pytest.raises(HTTPException, match="409"):
            await calc.load_calc_basis(db, env["ids"]["p"], 2025)
    assert (await _confirm(env, latest)).json()["revision"] == 2
    async with env["factory"]() as db:
        rows = (await db.execute(sa.select(ConsolScopeConfirmation).order_by(ConsolScopeConfirmation.revision))).scalars().all()
        assert [row.status for row in rows] == ["superseded", "active"]
        project = await db.get(Project, env["ids"]["sub"])
        project.relation_to_parent = "subsidiary"
        await db.commit()
    reverted = await _preview(env)
    assert reverted["fingerprint"] == old["fingerprint"]
    assert (await _confirm(env, reverted)).json()["revision"] == 3
    assert (await _counts(env))[0] == 3


@pytest.mark.asyncio
async def test_three_equal_codes_deduplicate_identity_but_still_need_confirmation(env):
    async with env["factory"]() as db:
        for key in ("branch", "sub"):
            await db.delete(await db.get(TrialBalance, (await db.scalars(sa.select(TrialBalance.id).where(TrialBalance.project_id == env["ids"][key]))).one()))
            await db.delete(await db.get(Project, env["ids"][key]))
        await db.commit()
    preview = await _preview(env)
    assert not preview["confirmed"] and preview["revision"] == 0
    assert [n["node_key"] for n in preview["nodes"]] == ["P:consol", "P:consol_elim", "P:parent"]
    assert preview["tree"]["parent_company_code"] is None
    assert (await _confirm(env, preview)).json()["confirmed"]
    assert await _counts(env) == (1, 3)


@pytest.mark.asyncio
async def test_explicit_tree_and_wrong_year_cannot_bypass_calculation_gate(env):
    assert (await _confirm(env)).status_code == 200
    async with env["factory"]() as db:
        tree = await build_tree(db, env["ids"]["p"])
        tree.children = []
        with pytest.raises(HTTPException) as error:
            await calc.load_calc_basis(db, env["ids"]["p"], 2025, tree=tree)
        assert error.value.status_code == 409
        assert "待计算树" in error.value.detail["message"]
        with pytest.raises(HTTPException) as error:
            await calc.load_calc_basis(db, env["ids"]["p"], 2024)
        assert error.value.status_code == 409
        assert "年度" in error.value.detail["message"]


@pytest.mark.asyncio
async def test_service_only_flushes_and_rollback_removes_role_batch(env):
    async with env["factory"]() as db:
        preview = await svc.preview_scope_confirmation(db, env["ids"]["p"])
        result = await svc.confirm_scope(db, env["ids"]["p"], confirmed_by=env["ids"]["edit"],
                                         expected_fingerprint=preview["fingerprint"], expected_revision=0)
        assert result["revision"] == 1 and db.in_transaction()
        assert await db.scalar(sa.select(sa.func.count()).select_from(ConsolScopeConfirmationNode)) == len(preview["nodes"])
        await db.rollback()
    assert await _counts(env) == (0, 0)


@pytest.mark.asyncio
async def test_fingerprint_uses_stable_canonical_fields_not_database_ids(env):
    async with env["factory"]() as db:
        project = await db.get(Project, env["ids"]["p"])
        result = await build_group_tree(db, project.id)
        payload = svc._canonical_payload(project, result)
        fingerprint = svc.fingerprint_payload(payload)
        expected = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        assert fingerprint == expected and len(fingerprint) == 64
        changed = copy.deepcopy(result)
        for node in iter_nodes(changed.root):
            node.project_id = uuid.uuid4() if node.project_id else None
            node.host_project_id = uuid.uuid4() if node.host_project_id else None
            node.diagnostics = [{"random": str(uuid.uuid4())}]
            node.company_name = f"  {node.company_name}  "
        assert svc.fingerprint_payload(svc._canonical_payload(project, changed)) == fingerprint
        assert "project_id" not in json.dumps(payload) and "diagnostics" not in json.dumps(payload)
        changed.root.company_code = "NEW"
        assert svc.fingerprint_payload(svc._canonical_payload(project, changed)) != fingerprint


def test_model_registry_and_migration_are_consistent():
    import app.models as models
    assert models.ConsolScopeConfirmation is ConsolScopeConfirmation
    assert models.ConsolScopeConfirmationNode is ConsolScopeConfirmationNode
    sql = (ROOT / "backend/migrations/V183__consol_scope_confirmation.sql").read_text(encoding="utf-8")
    rollback = (ROOT / "backend/migrations/R183__rollback_consol_scope_confirmation.sql").read_text(encoding="utf-8")
    for model in (ConsolScopeConfirmation, ConsolScopeConfirmationNode):
        assert f"CREATE TABLE IF NOT EXISTS {model.__tablename__}" in sql
        assert f"DROP TABLE IF EXISTS {model.__tablename__}" in rollback
        for column in model.__table__.columns:
            assert column.name in sql
    assert rollback.index("DROP TABLE IF EXISTS consol_scope_confirmation_nodes") < rollback.index(
        "DROP TABLE IF EXISTS consol_scope_confirmations"
    )
    assert "WHERE status = 'active'" in sql
    assert "uq_consol_scope_confirmation_revision" in sql
    assert "uq_consol_scope_confirmation_node_key" in sql
