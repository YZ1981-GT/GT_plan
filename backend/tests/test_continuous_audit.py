"""Phase 10 Task 2.1-2.2: 连续审计测试"""

import pytest
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal


class TestContinuousAuditService:
    """ContinuousAuditService 单元测试"""

    @pytest.mark.asyncio
    async def test_create_next_year_project_not_found(self):
        from app.services.continuous_audit_service import ContinuousAuditService
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        svc = ContinuousAuditService()
        with pytest.raises(ValueError, match="上年项目不存在"):
            await svc.create_next_year(db, uuid4())

    # 原 test_create_next_year_copies_basic_info 用 mock 按 execute 调用次序喂结果，
    # 只验「调了几次」不验语义：AccountMapping 属性名写错（上年有映射即 500）、第 8 步
    # 畸形 SQL（PG 上毒化事务 ⇒ commit 静默回滚）都没被咬出来。改为下方真 SQLite 用例
    # （consol-tree-three-code-autobuild 任务 3.6/3.7）。

    def test_schemas_import(self):
        from app.models.phase10_schemas import (
            CreateNextYearRequest, CreateNextYearResponse,
        )
        req = CreateNextYearRequest()
        assert req.copy_team is True
        assert req.copy_mapping is True

    def test_router_import(self):
        from app.routers.continuous_audit import router
        routes = [r.path for r in router.routes]
        assert "/create-next-year" in routes or any("create-next-year" in r for r in routes)


# ===========================================================================
# 真 SQLite + 真 ORM 行（consol-tree-three-code-autobuild 任务 3.6 / 需求 7.4）
# ===========================================================================

import pytest_asyncio  # noqa: E402
from decimal import Decimal as _D  # noqa: E402

from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

_SELF = "91110000300000000G"
_PARENT = "911100002000000005"
_GROUP = "91110000100000000R"


@pytest_asyncio.fixture
async def real_db() -> AsyncSession:
    from app.models.base import Base

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


async def _seed_prior(db, *, client_name="示例子公司有限公司", relation="branch"):
    """上年单户项目：三码 + 关系 + 派生链接（指向上年合并项目）+ 映射/试算/裁剪方案。"""
    from app.models.audit_platform_models import (
        AccountCategory, AccountMapping, MappingType, TrialBalance,
    )
    from app.models.base import ProjectStatus
    from app.models.core import Project
    from app.models.note_trim_models import NoteTrimScheme

    consol_2025 = Project(
        name="母公司_2025", client_name="母公司", status=ProjectStatus.archived,
        company_code=_PARENT, audit_year=2025, report_scope="consolidated",
    )
    db.add(consol_2025)
    await db.flush()
    prior = Project(
        name=f"{client_name}_2025", client_name=client_name, status=ProjectStatus.archived,
        project_type="annual", company_code=_SELF, audit_year=2025, report_scope="standalone",
        template_type="soe",
        parent_company_name="母公司", parent_company_code=_PARENT, relation_to_parent=relation,
        ultimate_company_name="某集团", ultimate_company_code=_GROUP,
        parent_project_id=consol_2025.id,
        wizard_state={"steps": {"basic_info": {"step": "basic_info", "completed": True, "data": {
            "audit_year": 2025, "client_name": client_name, "company_code": _SELF,
            "parent_company_code": _PARENT, "relation_to_parent": relation,
        }}}},
    )
    db.add(prior)
    await db.flush()
    db.add_all([
        AccountMapping(project_id=prior.id, original_account_code="1001", original_account_name="库存现金",
                       standard_account_code="1001", mapping_type=MappingType.auto_exact),
        AccountMapping(project_id=prior.id, original_account_code="100201", original_account_name="银行存款-工行",
                       standard_account_code="1002", mapping_type=MappingType.manual),
        TrialBalance(project_id=prior.id, year=2025, company_code=_SELF, standard_account_code="1001",
                     account_name="库存现金", account_category=AccountCategory.asset,
                     audited_amount=_D("100.00")),
        TrialBalance(project_id=prior.id, year=2025, company_code=_SELF, standard_account_code="1002",
                     account_name="银行存款", account_category=AccountCategory.asset,
                     audited_amount=_D("2500.50")),
        # 其他年度的行：不得被改写成新年度（会撞唯一索引，也不是「上年审定」）
        TrialBalance(project_id=prior.id, year=2024, company_code=_SELF, standard_account_code="1001",
                     account_name="库存现金", account_category=AccountCategory.asset,
                     audited_amount=_D("88.00")),
        NoteTrimScheme(project_id=prior.id, template_type="soe", scheme_name="上年裁剪",
                       trim_data={"hidden": ["五、1"]}),
    ])
    await db.commit()
    return prior


class TestCreateNextYearRealDb:
    @pytest.mark.asyncio
    async def test_inherits_group_fields_and_year_without_parent_link(self, real_db):
        from app.models.audit_platform_models import AccountMapping, TrialBalance
        from app.models.core import Project
        from app.models.note_trim_models import NoteTrimScheme
        from app.services.continuous_audit_service import ContinuousAuditService

        prior = await _seed_prior(real_db)
        prior_ws_before = {k: v for k, v in prior.wizard_state.items()}

        result = await ContinuousAuditService().create_next_year(real_db, prior.id)
        await real_db.commit()

        assert result["new_year"] == 2026
        new = (await real_db.execute(
            select(Project).where(Project.id == UUID(result["new_project_id"]))
        )).scalar_one()
        # 物化年度必须写（唯一索引与企业树按年度分组都依赖它）
        assert new.audit_year == 2026
        assert new.name == "示例子公司有限公司_2026"
        # 集团关系继承
        assert new.parent_company_code == _PARENT
        assert new.ultimate_company_code == _GROUP
        assert new.relation_to_parent == "branch"
        # 派生链接不复制（上年值指向上年合并项目）
        assert new.parent_project_id is None
        # 向导回填数据：年度与关系同步，且上年项目的向导数据没被连带改掉（深拷贝）
        data = new.wizard_state["steps"]["basic_info"]["data"]
        assert data["audit_year"] == 2026
        assert data["relation_to_parent"] == "branch"
        await real_db.refresh(prior)
        assert prior.wizard_state == prior_ws_before
        assert prior.wizard_state["steps"]["basic_info"]["data"]["audit_year"] == 2025

        # 科目映射按真实字段复制
        maps = (await real_db.execute(
            select(AccountMapping).where(AccountMapping.project_id == new.id)
        )).scalars().all()
        assert result["items_copied"]["account_mapping"] == 2
        assert {(m.original_account_code, m.standard_account_code) for m in maps} == {
            ("1001", "1001"), ("100201", "1002"),
        }
        # 试算：只取上年度行，审定数 → 期初
        tbs = (await real_db.execute(
            select(TrialBalance).where(TrialBalance.project_id == new.id)
        )).scalars().all()
        assert result["items_copied"]["trial_balance"] == 2
        assert {(t.year, t.standard_account_code, t.opening_balance) for t in tbs} == {
            (2026, "1001", _D("100.00")), (2026, "1002", _D("2500.50")),
        }
        # 附注裁剪方案结转
        schemes = (await real_db.execute(
            select(NoteTrimScheme).where(NoteTrimScheme.project_id == new.id)
        )).scalars().all()
        assert result["items_copied"]["note_trim_schemes"] == 1
        assert schemes[0].trim_data == {"hidden": ["五、1"]}

    @pytest.mark.asyncio
    async def test_duplicate_next_year_rejected(self, real_db):
        from app.services.continuous_audit_service import ContinuousAuditService

        prior = await _seed_prior(real_db)
        svc = ContinuousAuditService()
        await svc.create_next_year(real_db, prior.id)
        await real_db.commit()

        with pytest.raises(ValueError) as exc:
            await svc.create_next_year(real_db, prior.id)
        assert str(exc.value) == "2026 年度已存在该单位该年度的单户项目，不能重复创建"

    @pytest.mark.asyncio
    async def test_legacy_prior_without_relation_defaults_by_name(self, real_db):
        """上年有上级代码却没关系（历史数据）⇒ 按企业名称补默认，保持「有上级 ⇔ 有关系」。"""
        from app.models.core import Project
        from app.services.continuous_audit_service import ContinuousAuditService

        prior = await _seed_prior(real_db, client_name="示例有限公司临港店", relation=None)
        result = await ContinuousAuditService().create_next_year(real_db, prior.id)
        new = (await real_db.execute(
            select(Project).where(Project.id == UUID(result["new_project_id"]))
        )).scalar_one()
        assert new.relation_to_parent == "branch"
        assert new.wizard_state["steps"]["basic_info"]["data"]["relation_to_parent"] == "branch"

    def test_optional_carry_forward_is_savepoint_isolated(self):
        """源码守卫：被 try/except 吞掉异常的数据库操作必须在 SAVEPOINT 里。

        PG 上事务内任一语句失败即中止整个事务；吞掉异常后路由照常 commit，PG 会把 COMMIT
        当 ROLLBACK 执行 ⇒ 新项目静默丢失、接口仍返回 200。SQLite 失败语句不中止事务，
        真库行为测不出，故用 AST 钉住写法。
        """
        import ast
        import inspect
        import textwrap

        from app.services.continuous_audit_service import ContinuousAuditService

        src = textwrap.dedent(inspect.getsource(ContinuousAuditService.create_next_year))
        tree = ast.parse(src)
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            swallows = any(
                not any(isinstance(s, ast.Raise) for s in ast.walk(h)) for h in node.handlers
            )
            touches_db = any(
                isinstance(s, ast.Await) and isinstance(s.value, ast.Call)
                and isinstance(s.value.func, ast.Attribute)
                and s.value.func.attr in {"execute", "flush"}
                for s in ast.walk(ast.Module(body=node.body, type_ignores=[]))
            )
            nested = any(
                isinstance(s, ast.AsyncWith)
                and any(
                    isinstance(item.context_expr, ast.Call)
                    and isinstance(item.context_expr.func, ast.Attribute)
                    and item.context_expr.func.attr == "begin_nested"
                    for item in s.items
                )
                for s in node.body
            )
            if swallows and touches_db and not nested:
                offenders.append(node.lineno)
        assert offenders == [], f"吞异常的数据库操作未放进 begin_nested()：行 {offenders}"
        # 反向自检：判据确实能认出原来的写法
        legacy = textwrap.dedent('''
            async def f(db):
                for t in ["a"]:
                    try:
                        await db.execute(sa.text("INSERT INTO a (id, SELECT"))
                    except Exception:
                        continue
        ''')
        legacy_tree = ast.parse(legacy)
        hits = [
            n for n in ast.walk(legacy_tree)
            if isinstance(n, ast.Try) and not any(isinstance(s, ast.AsyncWith) for s in n.body)
        ]
        assert hits, "反向自检失败：判据认不出旧写法"


@pytest.mark.asyncio
async def test_endpoint_duplicate_next_year_is_400(real_db):
    """真发请求：下年项目已存在 ⇒ 400 中文原因（不是 IntegrityError 500）。"""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers.continuous_audit import router
    from app.services.continuous_audit_service import ContinuousAuditService

    prior = await _seed_prior(real_db)
    await ContinuousAuditService().create_next_year(real_db, prior.id)
    await real_db.commit()

    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield real_db

    class _User:
        id = uuid4()
        role = MagicMock(value="admin")

    async def _user():
        return _User()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"/api/projects/{prior.id}/create-next-year", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "2026 年度已存在该单位该年度的单户项目，不能重复创建"
