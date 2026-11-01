"""Batch project import security, CAS, and recovery regressions."""
from __future__ import annotations

from io import BytesIO
from uuid import UUID, uuid4

import pytest
from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.core import Project
from app.services.batch_project_execution import apply_validation_plan, create_validation_plan
from app.services.batch_project_service import generate_template, parse_and_import, validate_batch
from tests._batch_project_test_support import (
    BRANCH,
    CHILD,
    PARENT,
    ROOT,
    admin,
    grant_manager_codes,
    make_excel,
    row,
)

pytest_plugins = ("tests._batch_project_fixtures",)

@pytest.mark.asyncio
async def test_unknown_template_version_is_rejected(db):
    output = await generate_template()
    workbook = load_workbook(output)
    workbook["_GT_META"]["B1"] = "999"
    changed = BytesIO()
    workbook.save(changed)
    with pytest.raises(Exception) as captured:
        await validate_batch(changed.getvalue(), db)
    assert getattr(captured.value, "status_code", None) == 400
    assert "模板版本 999 不受支持" in str(getattr(captured.value, "detail", ""))

@pytest.mark.asyncio
async def test_unauthorized_existing_entity_does_not_leak_group_fields(db):
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.models.base import UserRole
    from app.models.core import User
    from app.services.batch_project_plan import analyze_batch
    from app.services.batch_project_workbook import entity_group_fields_hash
    from app.services.project_wizard_service import create_project

    hidden = await create_project(BasicInfoSchema(
        client_name="隐藏企业", audit_year=2041, project_type="annual",
        accounting_standard="enterprise", company_code=CHILD,
        short_name="隐藏企业", report_scope="standalone",
        parent_company_code=ROOT, ultimate_company_code=ROOT,
        relation_to_parent="subsidiary",
    ), db)
    manager = User(
        username="hidden_probe_manager", email="hidden_probe@example.test",
        hashed_password="x", role=UserRole.manager,
    )
    db.add(manager)
    await db.commit()

    update_row = [
        "隐藏企业", CHILD, "隐藏企业", 2041, "年报审计", "企业会计准则", "单户",
        ROOT, ROOT, "分公司", "更新集团关系", str(hidden.id),
        entity_group_fields_hash([hidden]),
    ]
    update = await analyze_batch(
        make_excel([update_row]), db, current_user=manager, mode="consolidation"
    )
    messages = "；".join(message for item in update.response.errors for message in item.errors)
    assert "完整模板" in messages
    assert "项目ID与" not in messages
    assert "基线摘要" not in messages

    create_row = row("隐藏企业合并", CHILD, 2041, "合并")
    with pytest.raises(Exception) as hidden_denied:
        await analyze_batch(
            make_excel([create_row]), db, current_user=manager, mode="consolidation"
        )
    with pytest.raises(Exception) as absent_denied:
        await analyze_batch(
            make_excel([row("不存在企业", BRANCH, 2041, "合并")]),
            db, current_user=manager, mode="consolidation",
        )
    # 无精确 grant 时在库存查询之前拒绝；隐藏项目与不存在项目的公开结果完全相同。
    assert getattr(hidden_denied.value, "status_code", None) == 403
    assert getattr(absent_denied.value, "status_code", None) == 403
    assert getattr(hidden_denied.value, "detail", None) == getattr(absent_denied.value, "detail", None)

    with pytest.raises(Exception) as legacy_denied:
        await parse_and_import(
            make_excel([create_row]), db, current_user=manager, mode="consolidation"
        )
    with pytest.raises(Exception) as plan_denied:
        await create_validation_plan(
            make_excel([row("隐藏企业单户", CHILD, 2041)]), db,
            actor=manager, file_name="隐藏冲突.xlsx", mode="project",
            idempotency_key="hidden-existing-plan-0001",
        )
    assert getattr(legacy_denied.value, "detail", None) == getattr(plan_denied.value, "detail", None)

@pytest.mark.asyncio
async def test_legacy_endpoint_never_treats_update_rows_as_new_projects(db):
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.services.batch_project_workbook import entity_group_fields_hash
    from app.services.project_wizard_service import create_project
    project = await create_project(BasicInfoSchema(
        client_name="兼容更新企业", audit_year=2042, project_type="annual",
        accounting_standard="enterprise", company_code=CHILD,
        short_name="兼容更新", report_scope="standalone",
    ), db)
    update_row = [
        project.client_name, project.company_code, project.short_name, 2042,
        "年报审计", "企业会计准则", "单户", "", "", "",
        "更新集团关系", str(project.id), entity_group_fields_hash([project]),
    ]
    result = await parse_and_import(make_excel([update_row]), db, mode="consolidation")
    assert result.success_count == 0
    assert result.fail_count == 1
    assert "完整模板" in result.failures[0].errors[0]
    count = await db.scalar(select(func.count()).select_from(Project).where(
        Project.company_code == CHILD, Project.audit_year == 2042,
        Project.is_deleted == False,  # noqa: E712
    ))
    assert count == 1

@pytest.mark.asyncio
async def test_expired_unapplied_plan_can_be_revalidated_with_same_key(db):
    from datetime import datetime, timedelta, timezone
    actor = admin()
    key = "expired-plan-revalidate-0001"
    payload = make_excel([row("过期重验", CHILD, 2043)])
    plan, first, _ = await create_validation_plan(
        payload, db, actor=actor, file_name="过期.xlsx", mode="project",
        idempotency_key=key,
    )
    assert first.valid is True
    plan.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()
    refreshed, second, reused = await create_validation_plan(
        payload, db, actor=actor, file_name="过期.xlsx", mode="project",
        idempotency_key=key,
    )
    assert reused is True
    assert refreshed.id == plan.id
    assert second.valid is True
    assert refreshed.expires_at > datetime.now(timezone.utc)

def test_exported_user_text_never_becomes_excel_formula():
    from app.services.batch_project_workbook import export_workbook
    prefixes = ["=1+1", "+SUM(1,1)", "-1+2", "@SUM(1,1)"]
    rows = [[value, CHILD, value, 2044, "年报审计", "企业会计准则", "单户",
             "", "", "", "新建", "", ""] for value in prefixes]
    output = export_workbook(rows, mode="project")
    sheet = load_workbook(output, data_only=False)["数据"]
    for row_number, value in enumerate(prefixes, start=2):
        assert sheet.cell(row_number, 1).value == value
        assert sheet.cell(row_number, 1).data_type == "s"
        assert sheet.cell(row_number, 3).data_type == "s"

@pytest.mark.asyncio
async def test_partner_creator_gets_project_access_without_fake_assignment(db):
    from app.deps import assert_project_permission
    from app.models.base import PermissionLevel, ProjectUserRole, UserRole
    from app.models.core import ProjectUser, User
    from app.models.staff_models import ProjectAssignment
    partner = User(
        username="batch_partner", email="batch_partner@example.test",
        hashed_password="x", role=UserRole.partner,
    )
    db.add(partner)
    await db.commit()
    key = "partner-plan-access-0001"
    plan, validation, _ = await create_validation_plan(
        make_excel([row("合伙人创建项目", CHILD, 2045)]), db,
        actor=partner, file_name="合伙人.xlsx", mode="project", idempotency_key=key,
    )
    assert validation.valid is True
    await db.commit()
    result = await apply_validation_plan(
        db, plan_id=plan.id, actor=partner, idempotency_key=key
    )
    await db.commit()
    project_id = UUID(result.project_ids[0])
    member = (await db.execute(select(ProjectUser).where(
        ProjectUser.project_id == project_id,
        ProjectUser.user_id == partner.id,
        ProjectUser.is_deleted == False,  # noqa: E712
    ))).scalar_one()
    assert member.role == ProjectUserRole.partner
    assert member.permission_level == PermissionLevel.edit
    assert await db.scalar(select(func.count()).select_from(ProjectAssignment).where(
        ProjectAssignment.project_id == project_id,
        ProjectAssignment.is_deleted == False,  # noqa: E712
    )) == 0
    await assert_project_permission(db, partner, project_id, "edit")

@pytest.mark.asyncio
async def test_existing_counterpart_conflict_is_repaired_not_marked_unchanged(engine):
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.services.batch_project_export import export_group_tree
    from app.services.project_wizard_service import create_project
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        root_project = await create_project(BasicInfoSchema(
            client_name="冲突集团", audit_year=2046, project_type="annual",
            accounting_standard="enterprise", company_code=ROOT,
            short_name="冲突集团", report_scope="consolidated", ultimate_company_code=ROOT,
        ), session)
        standalone = await create_project(BasicInfoSchema(
            client_name="冲突子公司", audit_year=2046, project_type="annual",
            accounting_standard="enterprise", company_code=CHILD,
            short_name="冲突单户", report_scope="standalone",
            parent_company_code=ROOT, ultimate_company_code=ROOT,
            relation_to_parent="subsidiary",
        ), session)
        consolidated = await create_project(BasicInfoSchema(
            client_name="冲突子公司", audit_year=2046, project_type="annual",
            accounting_standard="enterprise", company_code=CHILD,
            short_name="冲突合并", report_scope="consolidated",
            parent_company_code=ROOT, ultimate_company_code=ROOT,
            relation_to_parent="subsidiary",
        ), session)
        consolidated.relation_to_parent = "branch"
        await session.commit()
        output, _ = await export_group_tree(root_project.id, session)

    actor = admin()
    key = "counterpart-conflict-plan-0001"
    async with factory() as session:
        plan, validation, _ = await create_validation_plan(
            output.getvalue(), session, actor=actor, file_name="冲突树.xlsx",
            mode="consolidation", idempotency_key=key,
        )
        assert validation.valid is True, validation.errors
        assert validation.summary.update == 1
        plan_id = plan.id
        await session.commit()
    async with factory() as session:
        result = await apply_validation_plan(
            session, plan_id=plan_id, actor=actor, idempotency_key=key
        )
        await session.commit()
        assert result.updated_count == 1
        rows = list((await session.execute(select(Project).where(
            Project.company_code == CHILD, Project.audit_year == 2046,
        ))).scalars().all())
        assert {item.id for item in rows} == {standalone.id, consolidated.id}
        assert {item.relation_to_parent for item in rows} == {"subsidiary"}


@pytest.mark.asyncio
async def test_revoked_group_dependency_hides_plan_and_blocks_create_apply(db):
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.models.base import PermissionLevel, ProjectUserRole, UserRole
    from app.models.core import ProjectUser, User
    from app.services.batch_project_execution import get_readable_plan
    from app.services.project_wizard_service import create_project

    manager = User(
        username="revoked_batch_manager", email="revoked_batch@example.test",
        hashed_password="x", role=UserRole.manager,
    )
    db.add(manager)
    await db.flush()
    root = await create_project(BasicInfoSchema(
        client_name="撤权集团", audit_year=2047, project_type="annual",
        accounting_standard="enterprise", company_code=ROOT,
        short_name="撤权集团", report_scope="consolidated", ultimate_company_code=ROOT,
    ), db)
    membership = ProjectUser(
        project_id=root.id, user_id=manager.id, role=ProjectUserRole.manager,
        permission_level=PermissionLevel.edit,
    )
    db.add(membership)
    await grant_manager_codes(db, manager, BRANCH, ROOT)
    await db.commit()

    key = "revoked-plan-dependency-0001"
    plan, validation, _ = await create_validation_plan(
        make_excel([row("撤权后不得接入", BRANCH, 2047, parent=ROOT, ultimate=ROOT, relation="子公司")]),
        db, actor=manager, file_name="撤权.xlsx", mode="project", idempotency_key=key,
    )
    assert validation.valid is True
    await db.commit()

    membership.is_deleted = True
    await db.commit()
    with pytest.raises(Exception) as status_error:
        await get_readable_plan(db, plan.id, manager)
    assert getattr(status_error.value, "status_code", None) == 404

    with pytest.raises(Exception) as apply_error:
        await apply_validation_plan(db, plan_id=plan.id, actor=manager, idempotency_key=key)
    assert getattr(apply_error.value, "status_code", None) == 409
    assert "权限或库存已变化" in str(getattr(apply_error.value, "detail", ""))
    await db.rollback()
    assert await db.scalar(select(func.count()).select_from(Project).where(
        Project.company_code == BRANCH, Project.audit_year == 2047,
        Project.is_deleted == False,  # noqa: E712
    )) == 0


@pytest.mark.asyncio
async def test_create_plan_rejects_root_appearing_after_preview(db):
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.services.project_wizard_service import create_project

    actor = admin()
    key = "root-inventory-cas-0001"
    plan, validation, _ = await create_validation_plan(
        make_excel([row("库存 CAS 子公司", CHILD, 2048, parent=ROOT, ultimate=ROOT, relation="子公司")]),
        db, actor=actor, file_name="库存 CAS.xlsx", mode="project", idempotency_key=key,
    )
    assert validation.valid is True
    assert validation.summary.auto_root == 1
    await db.commit()

    await create_project(BasicInfoSchema(
        client_name="确认后出现的集团", audit_year=2048, project_type="annual",
        accounting_standard="enterprise", company_code=ROOT,
        short_name="后出现集团", report_scope="consolidated", ultimate_company_code=ROOT,
    ), db)
    await db.commit()

    with pytest.raises(Exception) as captured:
        await apply_validation_plan(db, plan_id=plan.id, actor=actor, idempotency_key=key)
    assert getattr(captured.value, "status_code", None) == 409
    assert getattr(captured.value, "detail", {}).get("error_code") == "BATCH_PLAN_STALE"
    assert "权限或库存已变化" in str(getattr(captured.value, "detail", ""))
    await db.rollback()
    assert await db.scalar(select(func.count()).select_from(Project).where(
        Project.company_code == CHILD, Project.audit_year == 2048,
        Project.is_deleted == False,  # noqa: E712
    )) == 0


@pytest.mark.asyncio
async def test_template_metadata_binds_mode_and_group_root_scope(db):
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.services.batch_project_export import _project_export_row
    from app.services.batch_project_plan import analyze_batch
    from app.services.batch_project_workbook import entity_group_fields_hash, export_workbook
    from app.services.project_wizard_service import create_project

    project_template = await generate_template(mode="project")
    with pytest.raises(Exception) as mode_error:
        await validate_batch(project_template.getvalue(), db, mode="consolidation")
    assert getattr(mode_error.value, "status_code", None) == 400
    assert "场景" in str(getattr(mode_error.value, "detail", ""))

    root = await create_project(BasicInfoSchema(
        client_name="来源集团", audit_year=2049, project_type="annual",
        accounting_standard="enterprise", company_code=ROOT,
        short_name="来源集团", report_scope="consolidated", ultimate_company_code=ROOT,
    ), db)
    outsider = await create_project(BasicInfoSchema(
        client_name="其他集团企业", audit_year=2049, project_type="annual",
        accounting_standard="enterprise", company_code=PARENT,
        short_name="其他企业", report_scope="standalone", ultimate_company_code=PARENT,
    ), db)
    await db.commit()
    scoped = export_workbook(
        [_project_export_row(outsider, action="update", base_hash=entity_group_fields_hash([outsider]))],
        mode="consolidation", root_project_id=str(root.id),
    )
    with pytest.raises(Exception) as scope_error:
        await analyze_batch(scoped.getvalue(), db, current_user=admin(), mode="consolidation")
    assert getattr(scope_error.value, "status_code", None) == 400
    assert "当前集团树模板不可用" in str(getattr(scope_error.value, "detail", ""))

    from app.models.base import PermissionLevel, ProjectUserRole, UserRole
    from app.models.core import ProjectUser, User
    revoked_manager = User(
        username="template_root_probe", email="template_root_probe@example.test",
        hashed_password="x", role=UserRole.manager,
    )
    db.add(revoked_manager)
    await db.commit()
    with pytest.raises(Exception) as forbidden_root:
        await analyze_batch(scoped.getvalue(), db, current_user=revoked_manager, mode="consolidation")
    unknown_root = load_workbook(BytesIO(scoped.getvalue()))
    unknown_root["_GT_META"]["B3"] = str(uuid4())
    unknown_root_bytes = BytesIO()
    unknown_root.save(unknown_root_bytes)
    with pytest.raises(Exception) as missing_root:
        await analyze_batch(
            unknown_root_bytes.getvalue(), db, current_user=revoked_manager, mode="consolidation"
        )
    assert getattr(forbidden_root.value, "status_code", None) == 400
    assert getattr(missing_root.value, "status_code", None) == 400
    assert getattr(forbidden_root.value, "detail", None) == getattr(missing_root.value, "detail", None)

    root_editor = User(
        username="template_target_probe", email="template_target_probe@example.test",
        hashed_password="x", role=UserRole.manager,
    )
    db.add(root_editor)
    await db.flush()
    db.add(ProjectUser(
        project_id=root.id, user_id=root_editor.id, role=ProjectUserRole.manager,
        permission_level=PermissionLevel.edit,
    ))
    await db.commit()
    with pytest.raises(Exception) as hidden_target:
        await analyze_batch(scoped.getvalue(), db, current_user=root_editor, mode="consolidation")
    unknown_target = load_workbook(BytesIO(scoped.getvalue()))
    unknown_target["数据"]["L2"] = str(uuid4())
    unknown_target_bytes = BytesIO()
    unknown_target.save(unknown_target_bytes)
    with pytest.raises(Exception) as missing_target:
        await analyze_batch(
            unknown_target_bytes.getvalue(), db, current_user=root_editor, mode="consolidation"
        )
    assert getattr(hidden_target.value, "status_code", None) == 400
    assert getattr(missing_target.value, "status_code", None) == 400
    assert getattr(hidden_target.value, "detail", None) == getattr(missing_target.value, "detail", None)

    for mutation in ("delete", "clear-root"):
        workbook = load_workbook(BytesIO(scoped.getvalue()))
        if mutation == "delete":
            workbook.remove(workbook["_GT_META"])
        else:
            workbook["_GT_META"]["B3"] = ""
        stripped = BytesIO()
        workbook.save(stripped)
        result = await analyze_batch(
            stripped.getvalue(), db, current_user=admin(), mode="consolidation"
        )
        messages = "；".join(
            message for error in result.response.errors for message in error.errors
        )
        assert result.response.valid is False
        assert "完整模板" in messages


@pytest.mark.asyncio
async def test_revoked_invalid_or_failed_plan_cannot_expose_status_or_error_workbook(db):
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.models.base import PermissionLevel, ProjectUserRole, UserRole
    from app.models.core import ProjectUser, User
    from app.services.batch_project_execution import build_plan_error_workbook, get_readable_plan
    from app.services.project_wizard_service import create_project

    manager = User(
        username="revoked_invalid_manager", email="revoked_invalid@example.test",
        hashed_password="x", role=UserRole.manager,
    )
    db.add(manager)
    await db.flush()
    existing = await create_project(BasicInfoSchema(
        client_name="可撤权既有项目", audit_year=2050, project_type="annual",
        accounting_standard="enterprise", company_code=CHILD,
        short_name="既有项目", report_scope="standalone",
    ), db)
    member = ProjectUser(
        project_id=existing.id, user_id=manager.id, role=ProjectUserRole.manager,
        permission_level=PermissionLevel.edit,
    )
    db.add(member)
    await grant_manager_codes(db, manager, CHILD)
    await db.commit()

    key = "revoked-invalid-plan-0001"
    plan, validation, _ = await create_validation_plan(
        make_excel([row("可撤权既有项目", CHILD, 2050)]), db,
        actor=manager, file_name="错误计划.xlsx", mode="project", idempotency_key=key,
    )
    assert validation.valid is False
    plan.status = "failed"
    plan.public_error = "不应在撤权后泄露的执行错误"
    await db.commit()
    member.is_deleted = True
    await db.commit()

    for read_operation in (
        lambda: get_readable_plan(db, plan.id, manager),
        lambda: build_plan_error_workbook(db, plan_id=plan.id, actor=manager),
    ):
        with pytest.raises(Exception) as captured:
            await read_operation()
        assert getattr(captured.value, "status_code", None) == 404

    with pytest.raises(Exception) as apply_error:
        await apply_validation_plan(db, plan_id=plan.id, actor=manager, idempotency_key=key)
    assert getattr(apply_error.value, "status_code", None) == 409
    assert "不应在撤权后泄露" not in str(getattr(apply_error.value, "detail", ""))
    await db.rollback()


@pytest.mark.asyncio
async def test_commit_result_unknown_never_overwrites_applied_receipt(db, monkeypatch):
    import httpx

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.models.base import UserRole
    from app.models.core import User
    from app.routers.batch_project import router
    from fastapi import FastAPI

    user = User(
        username="commit_unknown_admin", email="commit_unknown@example.test",
        hashed_password="x", role=UserRole.admin,
    )
    db.add(user)
    await db.commit()

    async def override_db():
        yield db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    transport = httpx.ASGITransport(app=app)
    key = "commit-result-unknown-0001"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        validated = await client.post(
            "/api/projects/batch-validate?mode=project",
            files={"file": ("建项.xlsx", make_excel([row("提交未知", CHILD, 2051)]),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"idempotency_key": key},
        )
        assert validated.status_code == 200
        plan_id = validated.json()["validation_id"]
        real_commit = db.commit
        commit_calls = 0

        async def commit_then_disconnect():
            nonlocal commit_calls
            commit_calls += 1
            if commit_calls == 1:
                await real_commit()
                raise ConnectionError("commit acknowledgement lost")
            await real_commit()

        monkeypatch.setattr(db, "commit", commit_then_disconnect)
        unknown = await client.post("/api/projects/batch-apply", json={
            "validation_id": plan_id, "idempotency_key": key,
        })
        assert unknown.status_code == 503
        assert unknown.json()["detail"]["error_code"] == "BATCH_PLAN_RESULT_UNKNOWN"

        status = await client.get(f"/api/projects/batch-imports/{plan_id}")
        assert status.status_code == 200
        assert status.json()["status"] == "applied"
        assert status.json()["receipt"]["created_count"] == 1


@pytest.mark.asyncio
async def test_unique_integrity_conflict_is_returned_as_revalidatable_stale_plan(monkeypatch):
    from app.routers import batch_project as batch_router
    from app.services.batch_project_execution import BatchApplyRequest
    from sqlalchemy.exc import IntegrityError

    class _Db:
        async def rollback(self):
            return None

        async def commit(self):
            return None

    async def raise_unique_conflict(*_args, **_kwargs):
        raise IntegrityError("INSERT INTO projects", {}, Exception("unique violation"))

    async def ignore_failed_mark(*_args, **_kwargs):
        return None

    monkeypatch.setattr(batch_router, "apply_validation_plan", raise_unique_conflict)
    monkeypatch.setattr(batch_router, "mark_plan_failed", ignore_failed_mark)
    with pytest.raises(Exception) as captured:
        await batch_router.batch_apply_projects(
            BatchApplyRequest(validation_id=uuid4(), idempotency_key="unique-conflict-0001"),
            db=_Db(), current_user=admin(),
        )
    assert getattr(captured.value, "status_code", None) == 409
    detail = getattr(captured.value, "detail", {})
    assert detail["error_code"] == "BATCH_PLAN_STALE"


@pytest.mark.asyncio
async def test_unique_failure_status_preserves_stale_error_code_for_network_recovery(db):
    from sqlalchemy.exc import IntegrityError

    from app.services.batch_project_execution import mark_plan_failed, plan_status_response

    actor = admin()
    key = "failed-stale-recovery-0001"
    plan, validation, _ = await create_validation_plan(
        make_excel([row("失败恢复项目", CHILD, 2054)]), db,
        actor=actor, file_name="失败恢复.xlsx", mode="project", idempotency_key=key,
    )
    assert validation.valid is True
    await db.commit()
    await mark_plan_failed(
        db, plan_id=plan.id, actor=actor,
        error=IntegrityError("INSERT INTO projects", {}, Exception("unique violation")),
    )
    await db.commit()
    status = plan_status_response(plan)
    assert status.status == "failed"
    assert status.failure_error_code == "BATCH_PLAN_STALE"
    assert "_plan_failure_error_code" not in status.summary


@pytest.mark.asyncio
async def test_apply_checks_edit_before_reading_current_group_tree(db, monkeypatch):
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.models.base import PermissionLevel, ProjectUserRole, UserRole
    from app.models.core import ProjectUser, User
    from app.services import batch_project_execution
    from app.services.batch_project_export import export_group_tree
    from app.services.project_wizard_service import create_project

    manager = User(
        username="apply_order_manager", email="apply_order@example.test",
        hashed_password="x", role=UserRole.manager,
    )
    db.add(manager)
    await db.flush()
    root = await create_project(BasicInfoSchema(
        client_name="执行顺序集团", audit_year=2055, project_type="annual",
        accounting_standard="enterprise", company_code=ROOT,
        short_name="执行顺序集团", report_scope="consolidated", ultimate_company_code=ROOT,
    ), db)
    child = await create_project(BasicInfoSchema(
        client_name="执行顺序子公司", audit_year=2055, project_type="annual",
        accounting_standard="enterprise", company_code=CHILD,
        short_name="执行顺序子公司", report_scope="standalone",
        parent_company_code=ROOT, ultimate_company_code=ROOT, relation_to_parent="subsidiary",
    ), db)
    root_member = ProjectUser(
        project_id=root.id, user_id=manager.id, role=ProjectUserRole.manager,
        permission_level=PermissionLevel.edit,
    )
    child_member = ProjectUser(
        project_id=child.id, user_id=manager.id, role=ProjectUserRole.manager,
        permission_level=PermissionLevel.edit,
    )
    db.add_all([root_member, child_member])
    await db.commit()
    exported, _ = await export_group_tree(root.id, db)
    workbook = load_workbook(exported)
    child_row = next(cells for cells in workbook["数据"].iter_rows(min_row=2) if cells[1].value == CHILD)
    child_row[9].value = "分公司"
    edited = BytesIO()
    workbook.save(edited)
    key = "apply-edit-before-tree-0001"
    plan, validation, _ = await create_validation_plan(
        edited.getvalue(), db, actor=manager, file_name="执行顺序.xlsx",
        mode="consolidation", idempotency_key=key,
    )
    assert validation.valid is True
    await db.commit()
    child_member.permission_level = PermissionLevel.readonly
    await db.commit()

    async def tree_must_not_be_read(*_args, **_kwargs):
        raise AssertionError("权限不足时不应读取当前集团树")

    monkeypatch.setattr(batch_project_execution, "_assert_template_root_scope", tree_must_not_be_read)
    with pytest.raises(Exception) as captured:
        await apply_validation_plan(db, plan_id=plan.id, actor=manager, idempotency_key=key)
    assert getattr(captured.value, "status_code", None) == 409
    detail = getattr(captured.value, "detail", {})
    assert detail["error_code"] == "BATCH_PLAN_STALE"
    assert "权限或库存已变化" in detail["message"]
    await db.rollback()


@pytest.mark.asyncio
async def test_route_stale_cas_is_persisted_for_lost_response_recovery(db):
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.routers import batch_project as batch_router
    from app.services.batch_project_execution import (
        BatchApplyRequest,
        get_readable_plan,
        plan_status_response,
    )
    from app.services.project_wizard_service import create_project

    actor = admin()
    key = "route-stale-status-recovery-0001"
    plan, validation, _ = await create_validation_plan(
        make_excel([row("状态恢复子公司", CHILD, 2056, parent=ROOT, ultimate=ROOT, relation="子公司")]),
        db, actor=actor, file_name="状态恢复.xlsx", mode="project", idempotency_key=key,
    )
    assert validation.valid is True
    await db.commit()
    await create_project(BasicInfoSchema(
        client_name="确认后新增根", audit_year=2056, project_type="annual",
        accounting_standard="enterprise", company_code=ROOT,
        short_name="新增根", report_scope="consolidated", ultimate_company_code=ROOT,
    ), db)
    await db.commit()

    with pytest.raises(Exception) as captured:
        await batch_router.batch_apply_projects(
            BatchApplyRequest(validation_id=plan.id, idempotency_key=key),
            db=db, current_user=actor,
        )
    assert getattr(captured.value, "status_code", None) == 409
    assert getattr(captured.value, "detail", {})["error_code"] == "BATCH_PLAN_STALE"
    recovered = await get_readable_plan(db, plan.id, actor)
    status = plan_status_response(recovered)
    assert status.status == "failed"
    assert status.failure_error_code == "BATCH_PLAN_STALE"
