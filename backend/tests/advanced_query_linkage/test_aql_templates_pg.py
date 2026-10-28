"""模板后端真库用例（advanced-query-linkage-closure 任务 24；R9.2、R9.3，design §10.2；AQ-16）。

- 权限世界（``pg_world``：同一事务内的临时 schema，表按 ORM 建，结束整体回滚）：管理员公开的模板，系统角色为 auditor 的
  项目经理在列表里看得到、按模板执行得到本项目的行；他人的私有模板读取与执行都 403「无权访问该模板」（合伙人可访问
  全部项目也不例外）。
- 真库回滚事务（``business``：系统管理员，``pg_rollback_session``）：在【UAT】子公司A 造两年度的试算行，按模板执行时
  年度 = 请求年度，否则 = 项目审计年度（【UAT】子公司A 现库 ``audit_year`` 2025），都没有 ⇒ 422 平台统一文案；翻页由请求
  决定。模板的作者取库里已有的管理员账号（只在回滚事务里引用，不改 users）。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import UserRole
from app.models.core import Project, ProjectStatus
from app.models.custom_query_models import CustomQueryTemplate
from app.models.workpaper_models import WpIndex
from app.routers import custom_query
from tests.advanced_query_linkage.gold import AUDIT_YEAR, UA
from tests.authz_world import OTHER_PROJECT_ID, TARGET_PROJECT_ID, pg_world

pytestmark = pytest.mark.pg_only

X, Y = TARGET_PROJECT_ID, OTHER_PROJECT_ID
CQ = "/api/custom-query"
NOT_VISIBLE = {"error_code": "TEMPLATE_NOT_VISIBLE", "message": "无权访问该模板"}
TAG = "【测试】AQL-B8"


async def _tb(session, project_id: uuid.UUID, year: int, name: str, code: str = "1001") -> None:
    session.add(TrialBalance(
        project_id=project_id, year=year, company_code="001", standard_account_code=code, account_name=name,
        account_category=AccountCategory.asset, unadjusted_amount=Decimal("1.00"), audited_amount=Decimal("1.00"),
    ))
    await session.flush()


async def test_project_manager_with_auditor_role_sees_and_runs_admin_public_template(monkeypatch):
    """R9.2：管理员保存的公开模板，系统 auditor 身份的项目经理在列表里看得到并能执行（原先列表只认 global ⇒ 看不到）。"""
    tables = (CustomQueryTemplate.__table__, TrialBalance.__table__, WpIndex.__table__)
    async with pg_world(monkeypatch, extra_tables=tables) as world:
        admin = (await world.admin_non_member()).user
        manager = (await world.edit_member()).user  # 系统 auditor、X 上（manager, edit）
        await world.eqcr_assignment("manager", user=manager)  # X 主管：不受循环范围限制
        await world.other_project()
        await _tb(world.db, X, AUDIT_YEAR, f"{TAG} X")
        await _tb(world.db, Y, AUDIT_YEAR, f"{TAG} Y")
        async with world.client(custom_query.router, user=admin) as client:
            saved = await client.post(f"{CQ}/templates", json={
                "name": f"{TAG} 管理员公开", "data_source": "tb_detail", "scope": "public",
                "config": {"source": "tb_detail", "filters": {"account_name": TAG}}})
        assert saved.status_code == 201, saved.text
        row = (await world.db.execute(select(CustomQueryTemplate.scope).where(
            CustomQueryTemplate.id == uuid.UUID(saved.json()["id"])))).scalar_one()
        assert row == "public"
        async with world.client(custom_query.router, user=manager) as client:
            listed = await client.get(f"{CQ}/templates")
            run = await client.post(f"{CQ}/templates/{saved.json()['id']}/execute",
                                    json={"project_id": str(X), "year": AUDIT_YEAR})
    assert saved.json()["id"] in {item["id"] for item in listed.json()["templates"]}
    assert run.status_code == 200, run.text
    assert [r["account_name"] for r in run.json()["rows"]] == [f"{TAG} X"]


async def test_private_template_of_another_user_is_403_to_read_and_execute(monkeypatch):
    """R9.2：他人的私有模板读取、执行都 403 TEMPLATE_NOT_VISIBLE（原先执行端点未映射 ⇒ 500）；作者本人照常执行。"""
    async with pg_world(monkeypatch, extra_tables=(CustomQueryTemplate.__table__, TrialBalance.__table__,
                                                   WpIndex.__table__)) as world:
        author = (await world.edit_member()).user
        await world.eqcr_assignment("manager", user=author)
        partner = await world.user(UserRole.partner)
        tpl = CustomQueryTemplate(
            id=uuid.uuid4(), name=f"{TAG} 私有", data_source="tb_detail", config={"source": "tb_detail"},
            scope="private", shared_project_ids=[], creator_id=author.id, created_by=author.id)
        world.db.add(tpl)
        await world.db.flush()
        body = {"project_id": str(X), "year": AUDIT_YEAR}
        async with world.client(custom_query.router, user=partner) as client:
            read = await client.get(f"{CQ}/templates/{tpl.id}")
            run = await client.post(f"{CQ}/templates/{tpl.id}/execute", json=body)
        async with world.client(custom_query.router, user=author) as client:
            own = await client.post(f"{CQ}/templates/{tpl.id}/execute", json=body)
    for response in (read, run):
        assert (response.status_code, response.json()["detail"]) == (403, NOT_VISIBLE), response.text
    assert own.status_code == 200, own.text


async def test_execute_year_comes_from_request_then_project_audit_year(business, gold):
    """R9.3：年度 = 请求年度，否则目标项目审计年度；翻页由请求决定（原先取模板里存的年度，没存时 year=0 直接 422）。"""
    session = business.session
    assert await gold.scalar("SELECT audit_year FROM projects WHERE id = :pid", pid=str(UA)) == AUDIT_YEAR
    admin_id = await gold.scalar("SELECT id FROM users WHERE username = 'admin'")
    # 科目码用本用例专属值：【UAT】子公司A 现库已有 2025 年 1001 等行（试算表按项目、年度、公司、科目唯一）
    rows = ((AUDIT_YEAR, f"{TAG} 本年 1", "AQLB8-1"), (AUDIT_YEAR, f"{TAG} 本年 2", "AQLB8-2"),
            (AUDIT_YEAR - 1, f"{TAG} 上年", "AQLB8-3"))
    for year, name, code in rows:
        await _tb(session, UA, year, name, code)
    tpl = CustomQueryTemplate(
        id=uuid.uuid4(), name=f"{TAG} 年度", data_source="tb_detail",
        config={"source": "tb_detail", "year": 2019, "filters": {"account_name": TAG}},  # 存的 2019 不应被采用
        scope="public", shared_project_ids=[], creator_id=admin_id, created_by=admin_id)
    session.add(tpl)
    no_year = Project(id=uuid.uuid4(), name=f"{TAG} 无审计年度项目", client_name=TAG, status=ProjectStatus.execution,
                      template_type="soe", report_scope="standalone", audit_year=None, scenario="normal")
    session.add(no_year)
    await session.flush()
    url = f"{CQ}/templates/{tpl.id}/execute"

    default = await business.http.post(url, json={"project_id": str(UA)})
    explicit = await business.http.post(url, json={"project_id": str(UA), "year": AUDIT_YEAR - 1})
    first = await business.http.post(url, json={"project_id": str(UA), "limit": 1, "offset": 0})
    second = await business.http.post(url, json={"project_id": str(UA), "limit": 1, "offset": 1})
    missing = await business.http.post(url, json={"project_id": str(no_year.id)})

    assert default.status_code == 200, default.text
    assert sorted(r["account_name"] for r in default.json()["rows"]) == [f"{TAG} 本年 1", f"{TAG} 本年 2"]
    assert [r["account_name"] for r in explicit.json()["rows"]] == [f"{TAG} 上年"]
    assert first.json()["total"] == second.json()["total"] == 2
    assert {first.json()["rows"][0]["id"], second.json()["rows"][0]["id"]} == {r["id"] for r in default.json()["rows"]}
    assert (missing.status_code, missing.json()["detail"]) == (422, "未设置审计年度，请先在项目基本信息中填写")
    # 只读核对：被测请求没有写库（模板仍是回滚事务里的那一行、没有新增模板）
    assert (await session.execute(text("SELECT count(*) FROM custom_query_templates WHERE name LIKE :p"),
                                  {"p": f"{TAG}%"})).scalar() == 1
