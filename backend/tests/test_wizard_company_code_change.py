"""向导改企业代码：越权、授权与影响检查（spec consol-group-code-entry-consistency 任务 3.6）。

覆盖 design §5 三行：

- 改代码授权（真实依赖链：manager 无授权 403 / 有授权通过 / 年度锁后撤销 409 STALE /
  partner、admin 直通 / auditor 403 / 代码未变不触发 / 上级代码变化不触发）；
- 改代码影响（五类引用各一例 → 409 列计数；跨年度不算；无引用保存成功）；
- 节点身份列登记守卫（ORM 元数据 node_key / entity_node_key / node_company_code 列
  须在影响清单或豁免表；内置变异：临时模型加列须红）。

另覆盖：向导路由非成员 403 / edit 成员通过（R2.6）。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_schemas import WizardStep
from app.models.base import Base, UserRole
from app.models.consolidation_models import ConsolWorksheet
from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_note_mapping_models import ConsolNoteMappingBinding
from app.models.core import Project, ProjectUser, User
from app.models.share_change_event_models import ShareChangeEvent
from app.routers.project_wizard import router
from app.services import project_wizard_service as svc
from app.services.company_code_change_guard import (
    code_change_impacts,
    discover_node_identity_columns,
    find_unregistered_node_identity_columns,
    validate_node_identity_exemptions,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

CHILD_CODE = "91110000300000000G"
NEW_CODE = "91110000400000000U"
PARENT_CODE = "911100002000000005"
GROUP_CODE = "91110000100000000R"


def _basic_info(**overrides) -> dict:
    base = {
        "client_name": "测试子公司有限公司",
        "audit_year": 2025,
        "project_type": "annual",
        "accounting_standard": "enterprise",
        "company_code": CHILD_CODE,
        "short_name": "测试子公司",
        "report_scope": "standalone",
    }
    base.update(overrides)
    return base


def _actor(role: str) -> User:
    user = User(
        id=uuid.uuid4(), username=f"{role}_{uuid.uuid4().hex[:6]}",
        email=f"{role}@t.cn", role=UserRole(role), is_active=True,
        hashed_password="x",
    )
    return user


async def _add_membership(db: AsyncSession, project_id, user_id, level="edit") -> None:
    from app.models.core import PermissionLevel

    db.add(ProjectUser(
        project_id=project_id, user_id=user_id, role="manager",
        permission_level=PermissionLevel(level),
    ))
    await db.flush()


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def project(db: AsyncSession) -> Project:
    p = await svc.create_project(
        svc.__dict__ and (await _mk_schema()), db, auto_commit=False,
    ) if False else await svc.create_project(await _mk_schema(), db, auto_commit=False)
    await db.flush()
    return p


async def _mk_schema():
    from app.models.audit_platform_schemas import BasicInfoSchema

    return BasicInfoSchema(**_basic_info())


# ───────────────────────── 授权链（design §5「改代码授权」） ─────────────────────────


class TestCompanyCodeChangeAuthorization:
    async def test_actor_none_with_code_change_rejected(self, db, project, monkeypatch):
        """fail-closed：内部调用不带 actor 且代码有变化 ⇒ 403。"""
        from app.services import group_links

        async def _must_not_load_inventory(*args, **kwargs):
            raise AssertionError("企业代码授权失败前不应读取项目库存")

        monkeypatch.setattr(group_links, "prepare_group_fields", _must_not_load_inventory)
        with pytest.raises(HTTPException) as exc:
            await svc.update_step(
                project.id, WizardStep.basic_info,
                _basic_info(company_code=NEW_CODE), db, actor=None,
            )
        assert exc.value.status_code == 403
        assert exc.value.detail["error_code"] == "COMPANY_CREATION_NOT_AUTHORIZED"
        assert "修改企业代码需要该代码的建项授权" in exc.value.detail["message"]
        refreshed = await db.get(Project, project.id)
        assert refreshed.company_code == CHILD_CODE

    async def test_actor_none_guard_cannot_be_bypassed_when_authorizer_allows_none(self, db, project, monkeypatch):
        """守卫变异若让 actor=None 继续执行，授权服务的兼容返回不应使保存成功。"""
        from app.services import project_creation_grant_service as grants

        async def _authorize(*args, **kwargs):
            return []

        async def _revalidate(*args, **kwargs):
            return None

        monkeypatch.setattr(grants, "authorize_creation_codes", _authorize)
        monkeypatch.setattr(grants, "lock_and_revalidate_creation_codes", _revalidate)
        with pytest.raises(HTTPException) as exc:
            await svc.update_step(
                project.id, WizardStep.basic_info,
                _basic_info(company_code=NEW_CODE), db, actor=None,
            )
        assert exc.value.status_code == 403
        assert exc.value.detail["error_code"] == "COMPANY_CREATION_NOT_AUTHORIZED"
        refreshed = await db.get(Project, project.id)
        assert refreshed.company_code == CHILD_CODE

    async def test_invalid_new_code_is_rejected_before_authorization(self, db, project, monkeypatch):
        """非法新代码先报 422，不得把格式错误送进授权服务或库存读取。"""
        from app.services import group_links, project_creation_grant_service

        async def _must_not_authorize(*args, **kwargs):
            raise AssertionError("非法企业代码不应进入授权服务")

        async def _must_not_load_inventory(*args, **kwargs):
            raise AssertionError("非法企业代码不应读取项目库存")

        monkeypatch.setattr(
            project_creation_grant_service,
            "authorize_creation_codes",
            _must_not_authorize,
        )
        monkeypatch.setattr(group_links, "prepare_group_fields", _must_not_load_inventory)
        with pytest.raises(HTTPException) as exc:
            await svc.update_step(
                project.id, WizardStep.basic_info,
                _basic_info(company_code="91110000300000000H"),
                db,
                actor=_actor("manager"),
            )
        assert exc.value.status_code == 422
        assert exc.value.detail.startswith("企业代码：")
        refreshed = await db.get(Project, project.id)
        assert refreshed.company_code == CHILD_CODE

    async def test_uniqueness_failure_precedes_inventory_and_keeps_project(self, db, project, monkeypatch):
        """唯一性冲突在 prepare_group_fields 前失败，项目仍保持旧企业代码。"""
        from app.services import group_links

        await svc.create_project(
            await _mk_schema_with(company_code=NEW_CODE, client_name="已存在企业", short_name="已存在"),
            db,
            auto_commit=False,
        )
        admin = _actor("admin")
        db.add(admin)
        await db.flush()

        async def _must_not_load_inventory(*args, **kwargs):
            raise AssertionError("唯一性失败前不应读取项目库存")

        monkeypatch.setattr(group_links, "prepare_group_fields", _must_not_load_inventory)
        with pytest.raises(HTTPException) as exc:
            await svc.update_step(
                project.id, WizardStep.basic_info,
                _basic_info(company_code=NEW_CODE), db, actor=admin,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail == "已存在该单位该年度的单户项目"
        refreshed = await db.get(Project, project.id)
        assert refreshed.company_code == CHILD_CODE

    async def test_code_change_checks_order_before_prepare_group_fields(self, db, project, monkeypatch):
        """授权、锁后重验、唯一性、影响检查均先于集团库存读取。"""
        from app.services import company_code_change_guard, group_links
        from app.services import project_creation_grant_service as grants

        admin = _actor("admin")
        db.add(admin)
        await db.flush()
        events: list[str] = []
        original_authorize = grants.authorize_creation_codes
        original_revalidate = grants.lock_and_revalidate_creation_codes
        original_unique = svc.check_uniqueness
        original_impacts = company_code_change_guard.code_change_impacts
        original_prepare = group_links.prepare_group_fields

        async def _authorize(*args, **kwargs):
            events.append("authorize")
            return await original_authorize(*args, **kwargs)

        async def _revalidate(*args, **kwargs):
            events.append("revalidate")
            return await original_revalidate(*args, **kwargs)

        async def _unique(*args, **kwargs):
            events.append("unique")
            return await original_unique(*args, **kwargs)

        async def _impacts(*args, **kwargs):
            events.append("impact")
            return await original_impacts(*args, **kwargs)

        async def _prepare(*args, **kwargs):
            events.append("prepare")
            return await original_prepare(*args, **kwargs)

        monkeypatch.setattr(grants, "authorize_creation_codes", _authorize)
        monkeypatch.setattr(grants, "lock_and_revalidate_creation_codes", _revalidate)
        monkeypatch.setattr(svc, "check_uniqueness", _unique)
        monkeypatch.setattr(company_code_change_guard, "code_change_impacts", _impacts)
        monkeypatch.setattr(group_links, "prepare_group_fields", _prepare)

        await svc.update_step(
            project.id, WizardStep.basic_info,
            _basic_info(company_code=NEW_CODE), db, actor=admin,
        )
        assert events == ["authorize", "revalidate", "unique", "impact", "prepare"]

    async def test_manager_without_grant_rejected_and_value_unchanged(self, db, project, monkeypatch):
        from app.services import group_links

        async def _must_not_load_inventory(*args, **kwargs):
            raise AssertionError("授权拒绝前不应读取项目库存")

        monkeypatch.setattr(group_links, "prepare_group_fields", _must_not_load_inventory)
        manager = _actor("manager")
        db.add(manager)
        await _add_membership(db, project.id, manager.id)
        with pytest.raises(HTTPException) as exc:
            await svc.update_step(
                project.id, WizardStep.basic_info,
                _basic_info(company_code=NEW_CODE), db, actor=manager,
            )
        assert exc.value.status_code == 403
        detail = exc.value.detail
        assert isinstance(detail, dict)
        assert detail["error_code"] == "COMPANY_CREATION_NOT_AUTHORIZED"
        assert "修改企业代码需要该代码的建项授权" in detail["message"]
        refreshed = await db.get(Project, project.id)
        assert refreshed.company_code == CHILD_CODE  # 库值不变

    async def test_manager_with_grant_passes(self, db, project):
        from app.models.project_creation_grant_models import ProjectCreationGrant
        from datetime import datetime, timedelta, timezone

        manager = _actor("manager")
        db.add(manager)
        await _add_membership(db, project.id, manager.id)
        db.add(ProjectCreationGrant(
            grantee_user_id=manager.id, company_code=NEW_CODE,
            valid_from=datetime.now(timezone.utc) - timedelta(days=1),
            valid_until=datetime.now(timezone.utc) + timedelta(days=30),
            reason="测试授权",
        ))
        await db.flush()
        await svc.update_step(
            project.id, WizardStep.basic_info,
            _basic_info(company_code=NEW_CODE), db, actor=manager,
        )
        refreshed = await db.get(Project, project.id)
        assert refreshed.company_code == NEW_CODE

    async def test_grant_revoked_after_lock_returns_stale(self, db, project):
        """授权在年度锁后被撤销 ⇒ 409 PROJECT_CREATION_GRANT_STALE。

        通过 monkeypatch lock_and_revalidate：锁后重验前撤销授权行，
        验证 stale 路径把 ProjectCreationGrantStale 转成 409。
        """
        from app.services import project_creation_grant_service as grants
        from app.services.project_creation_grant_service import ProjectCreationGrantStale

        manager = _actor("manager")
        db.add(manager)
        await _add_membership(db, project.id, manager.id)
        original = grants.lock_and_revalidate_creation_codes

        async def _revoked_then_stale(db_, actor_, codes_, *, expected_snapshots=None):
            raise ProjectCreationGrantStale("建项授权已撤销")

        # 服务层在函数内 import，替换模块属性即可生效
        grants.lock_and_revalidate_creation_codes = _revoked_then_stale
        try:
            from app.models.project_creation_grant_models import ProjectCreationGrant
            from datetime import datetime, timedelta, timezone

            db.add(ProjectCreationGrant(
                grantee_user_id=manager.id, company_code=NEW_CODE,
                valid_from=datetime.now(timezone.utc) - timedelta(days=1),
                reason="测试授权",
            ))
            await db.flush()
            with pytest.raises(HTTPException) as exc:
                await svc.update_step(
                    project.id, WizardStep.basic_info,
                    _basic_info(company_code=NEW_CODE), db, actor=manager,
                )
            assert exc.value.status_code == 409
            assert exc.value.detail["error_code"] == "PROJECT_CREATION_GRANT_STALE"
        finally:
            grants.lock_and_revalidate_creation_codes = original
        refreshed = await db.get(Project, project.id)
        assert refreshed.company_code == CHILD_CODE

    @pytest.mark.parametrize("role", ["admin", "partner"])
    async def test_admin_partner_bypass(self, db, project, role):
        actor = _actor(role)
        db.add(actor)
        await _add_membership(db, project.id, actor.id)
        await svc.update_step(
            project.id, WizardStep.basic_info,
            _basic_info(company_code=NEW_CODE), db, actor=actor,
        )
        refreshed = await db.get(Project, project.id)
        assert refreshed.company_code == NEW_CODE

    async def test_auditor_cannot_change_code(self, db, project):
        auditor = _actor("auditor")
        db.add(auditor)
        await _add_membership(db, project.id, auditor.id)
        with pytest.raises(HTTPException) as exc:
            await svc.update_step(
                project.id, WizardStep.basic_info,
                _basic_info(company_code=NEW_CODE), db, actor=auditor,
            )
        assert exc.value.status_code == 403

    async def test_case_only_change_does_not_trigger_authorization(self, db, project):
        """只差大小写（规范化后相同）不触发授权（auditor 也能保存）。"""
        auditor = _actor("auditor")
        db.add(auditor)
        await _add_membership(db, project.id, auditor.id)
        await svc.update_step(
            project.id, WizardStep.basic_info,
            _basic_info(company_code=CHILD_CODE.lower()), db, actor=auditor,
        )
        refreshed = await db.get(Project, project.id)
        assert refreshed.company_code == CHILD_CODE

    async def test_parent_code_change_does_not_trigger_authorization(self, db, project):
        """上级 / 控制方代码变化不要求授权（与批量更新集团关系、拖拽同口径）。"""
        auditor = _actor("auditor")
        db.add(auditor)
        await _add_membership(db, project.id, auditor.id)
        await svc.update_step(
            project.id, WizardStep.basic_info,
            _basic_info(parent_company_code=PARENT_CODE), db, actor=auditor,
        )
        refreshed = await db.get(Project, project.id)
        assert refreshed.parent_company_code == PARENT_CODE


# ───────────────────────── 影响检查（design §5「改代码影响」） ─────────────────────────


class TestCompanyCodeChangeImpacts:
    async def test_no_references_saves(self, db, project):
        admin = _actor("admin")
        db.add(admin)
        impacts = await code_change_impacts(db, project, CHILD_CODE, 2025)
        assert impacts == []

    async def test_other_scope_project_blocks(self, db, project):
        _other = await svc.create_project(
            await _mk_schema_with(
                company_code=CHILD_CODE,
                client_name="同企业合并项目",
                short_name="同企业合并",
                report_scope="consolidated",
            ),
            db,
            auto_commit=False,
        )
        await db.flush()
        impacts = await code_change_impacts(db, project, f"  {CHILD_CODE.lower()}  ", 2025)
        kinds = {i["kind"]: i["count"] for i in impacts}
        assert kinds.get("project_refs") == 1

    async def test_consol_note_data_blocks(self, db, project):
        db.add(ConsolNoteData(
            project_id=project.id, year=2025, section_id="五-5-6",
            node_key=f"{CHILD_CODE}:consol", data={},
        ))
        await db.flush()
        impacts = await code_change_impacts(db, project, CHILD_CODE, 2025)
        kinds = {i["kind"]: i["count"] for i in impacts}
        assert kinds.get("consol_note_data") == 1

    async def test_mapping_binding_blocks(self, db, project):
        admin = _actor("admin")
        db.add(admin)
        rule = await _mk_mapping_rule(db, project.id, admin.id)
        db.add(ConsolNoteMappingBinding(
            project_id=project.id, section_id="五-5-6",
            entity_node_key=f"{CHILD_CODE}:subsidiary",
            entity_project_id=project.id, rule_id=rule.id,
            bound_source_hash="0" * 64,
        ))
        await db.flush()
        impacts = await code_change_impacts(db, project, CHILD_CODE, 2025)
        kinds = {i["kind"]: i["count"] for i in impacts}
        assert kinds.get("mapping_binding") == 1

    async def test_worksheet_blocks(self, db, project):
        db.add(ConsolWorksheet(
            project_id=project.id, node_company_code=f"{CHILD_CODE}:consol",
            account_code="1001", year=2025,
        ))
        await db.flush()
        impacts = await code_change_impacts(db, project, CHILD_CODE, 2025)
        kinds = {i["kind"]: i["count"] for i in impacts}
        assert kinds.get("worksheet") == 1

    async def test_share_change_blocks(self, db, project):
        db.add(ShareChangeEvent(
            project_id=project.id, year=2025, company_code=CHILD_CODE,
            node_key=f"{CHILD_CODE}:consol",
        ))
        await db.flush()
        impacts = await code_change_impacts(db, project, CHILD_CODE, 2025)
        kinds = {i["kind"]: i["count"] for i in impacts}
        assert kinds.get("share_change") == 1

    async def test_soft_deleted_worksheet_does_not_block(self, db, project):
        row = ConsolWorksheet(
            project_id=project.id, node_company_code=f"{CHILD_CODE}:consol",
            account_code="1001", year=2025, is_deleted=True,
        )
        db.add(row)
        await db.flush()
        impacts = await code_change_impacts(db, project, CHILD_CODE, 2025)
        assert not any(item["kind"] == "worksheet" for item in impacts)

    async def test_cross_year_reference_not_counted(self, db, project):
        db.add(ConsolNoteData(
            project_id=project.id, year=2024, section_id="五-5-6",
            node_key=f"{CHILD_CODE}:consol", data={},
        ))
        await db.flush()
        impacts = await code_change_impacts(db, project, CHILD_CODE, 2025)
        assert impacts == []

    async def test_impact_returns_409_with_details(self, db, project, monkeypatch):
        from app.services import group_links
        async def _must_not_load_inventory(*args, **kwargs):
            raise AssertionError("影响检查失败前不应读取项目库存")

        monkeypatch.setattr(group_links, "prepare_group_fields", _must_not_load_inventory)
        db.add(ConsolNoteData(
            project_id=project.id, year=2025, section_id="五-5-6",
            node_key=f"{CHILD_CODE}:consol", data={},
        ))
        await db.flush()
        admin = _actor("admin")
        db.add(admin)
        with pytest.raises(HTTPException) as exc:
            await svc.update_step(
                project.id, WizardStep.basic_info,
                _basic_info(company_code=NEW_CODE), db, actor=admin,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["error_code"] == "COMPANY_CODE_IN_USE"
        kinds = {i["kind"] for i in exc.value.detail["impacts"]}
        assert "consol_note_data" in kinds
        refreshed = await db.get(Project, project.id)
        assert refreshed.company_code == CHILD_CODE


async def _mk_schema_with(**overrides):
    from app.models.audit_platform_schemas import BasicInfoSchema

    return BasicInfoSchema(**_basic_info(**overrides))


async def _mk_mapping_rule(db: AsyncSession, project_id, user_id):
    from app.models.consol_note_mapping_models import (
        ConsolNoteDetailTemplate,
        ConsolNoteDetailTemplateVersion,
        ConsolNoteMappingRule,
    )

    tmpl = ConsolNoteDetailTemplate(
        template_type="soe", section_id="五-5-6", name="货币资金",
        visibility="project", created_by=user_id,
    )
    db.add(tmpl)
    await db.flush()
    ver = ConsolNoteDetailTemplateVersion(
        template_id=tmpl.id, version_number=1, rows=[], created_by=user_id,
    )
    db.add(ver)
    await db.flush()
    rule = ConsolNoteMappingRule(
        project_id=project_id, section_id="五-5-6", template_version_id=ver.id,
        source_structure_hash="0" * 64, version_number=1, mappings=[], is_active=True,
    )
    db.add(rule)
    await db.flush()
    return rule


# ───────────────────────── 节点身份列登记守卫（R6.5） ─────────────────────────


class TestNodeIdentityColumnRegistry:
    def test_all_node_identity_columns_registered(self):
        """ORM 元数据中三类节点身份列必须逐列登记，且豁免理由对应真实表列。"""
        from app.models.base import Base

        discovered = discover_node_identity_columns()
        expected = {
            "consol_artifact.node_key",
            "consol_note_data.node_key",
            "consol_note_mapping_binding.entity_node_key",
            "consol_scope_confirmation_nodes.node_key",
            "consol_worksheet.node_company_code",
            "report_generation_run.node_key",
            "share_change_event.node_key",
        }
        assert discovered == expected, "节点身份列扫描分母必须来自完整 Base.registry"
        assert not find_unregistered_node_identity_columns(registry=Base.registry)
        assert not validate_node_identity_exemptions(registry=Base.registry)

    def test_mutation_unregistered_column_detected(self):
        """内置变异：模拟真实 mapper 新增未登记 node_key，生产判据须打红。"""
        from types import SimpleNamespace
        import app.services.company_code_change_guard as guard

        baseline = guard.discover_node_identity_columns()
        fake_table = SimpleNamespace(
            name="tmp_fake_table",
            columns=(SimpleNamespace(name="node_key"),),
        )
        fake_registry = SimpleNamespace(
            mappers=(SimpleNamespace(local_table=fake_table),),
        )

        discovered = guard.discover_node_identity_columns(fake_registry)
        assert discovered == {"tmp_fake_table.node_key"}
        assert guard.find_unregistered_node_identity_columns(registry=fake_registry) == discovered
        # 变异只使用隔离的 registry，生产 registry 不得残留临时列。
        assert guard.discover_node_identity_columns() == baseline


# ───────────────────────── 路由鉴权（R2.6） ─────────────────────────


class TestWizardRouteAuthorization:
    @pytest_asyncio.fixture
    async def setup_app(self, db: AsyncSession):
        admin = User(
            id=uuid.uuid4(), username="admin_x", email="a@t.cn",
            role=UserRole.admin, is_active=True, hashed_password="x",
        )
        outsider = User(
            id=uuid.uuid4(), username="outsider", email="o@t.cn",
            role=UserRole.auditor, is_active=True, hashed_password="x",
        )
        member = User(
            id=uuid.uuid4(), username="member", email="m@t.cn",
            role=UserRole.auditor, is_active=True, hashed_password="x",
        )
        db.add_all([admin, outsider, member])
        await db.flush()
        p = await svc.create_project(await _mk_schema(), db, auto_commit=False)
        from app.models.core import PermissionLevel

        db.add(ProjectUser(
            project_id=p.id, user_id=member.id, role="auditor",
            permission_level=PermissionLevel.edit,
        ))
        await db.flush()
        await db.commit()

        app = FastAPI()
        app.include_router(router)

        async def _override_db():
            yield db

        app.dependency_overrides[get_db] = _override_db

        def _user_factory(user: User):
            async def _override():
                return user
            return _override

        transport = ASGITransport(app=app)
        return app, _user_factory, transport, p, outsider, member

    async def test_outsider_put_basic_info_403(self, setup_app):
        app, factory, transport, project, outsider, _ = setup_app
        app.dependency_overrides[get_current_user] = factory(outsider)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.put(
                f"/api/projects/{project.id}/wizard/basic_info",
                json=_basic_info(),
            )
        assert resp.status_code == 403

    async def test_member_put_basic_info_ok(self, setup_app):
        app, factory, transport, project, _, member = setup_app
        app.dependency_overrides[get_current_user] = factory(member)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.put(
                f"/api/projects/{project.id}/wizard/basic_info",
                json=_basic_info(),
            )
        assert resp.status_code == 200

    async def test_outsider_confirm_403(self, setup_app):
        app, factory, transport, project, outsider, _ = setup_app
        app.dependency_overrides[get_current_user] = factory(outsider)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(f"/api/projects/{project.id}/wizard/confirm")
        assert resp.status_code == 403
