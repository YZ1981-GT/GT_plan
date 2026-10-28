"""模板后端（advanced-query-linkage-closure 任务 24；R9.1~R9.3，ADR-AQL-11，design §3.6；AQ-16、AQ-29 模板部分）。

SQLite 权限世界（``tests/authz_world.py``），请求经 httpx 真发到生产注册的 custom_query router，只 override 当前用户与会话。
真库部分（审计员执行公开模板、私有模板 403、执行年度、【UAT】子公司A 的年度基线）在 ``test_aql_templates_pg.py``。

- scope 归一与可见性只在 ``TemplateScopeAdapter``：保存 private / project 不再 500，名称不合格 400 中文原因；adapter 报错中文。
- 列表先按可见性过滤、再截断（变异 #12：候选只认 global ⇒ 审计员看不到管理员的公开模板）。
- 更新传 ``scope=global`` 入库为 public（变异 B8-a：恢复更新末尾的原值覆盖）。
- 读取 / 执行不可见模板 403 ``TEMPLATE_NOT_VISIBLE``「无权访问该模板」（变异 B8-b：去掉执行端点的 403 映射 ⇒ 500）。
- 执行先校验目标项目归属、再解析年度：无权用户得 403 而不是 422（变异 B8-g：去掉端点里的归属校验）。
- ``config_to_request`` 是模板执行的唯一翻译，原样带上 ``acnr_targets``（变异 B8-c）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.base import UserRole
from app.models.core import User
from app.models.custom_query_models import CustomQueryTemplate
from app.routers import custom_query
from app.services.custom_query import template_service as template_service_module
from app.services.custom_query.template_scope_adapter import TemplateScopeAdapter, TemplateScopeValidationError
from app.services.custom_query.template_service import TemplateService, template_service
from tests.authz_world import OTHER_PROJECT_ID, TARGET_PROJECT_ID, AuthzWorld, sqlite_world

X, Y = TARGET_PROJECT_ID, OTHER_PROJECT_ID
CQ = "/api/custom-query"
NOT_VISIBLE = {"error_code": "TEMPLATE_NOT_VISIBLE", "message": "无权访问该模板"}
NO_YEAR = "未设置审计年度，请先在项目基本信息中填写"
T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


async def _template(world: AuthzWorld, owner: User, *, name: str, scope: str, shared=(), config=None,
                    minutes: int = 0) -> CustomQueryTemplate:
    tpl = CustomQueryTemplate(
        id=uuid.uuid4(), name=name, data_source="tb_detail", config=config or {"source": "tb_detail"},
        scope=scope, shared_project_ids=list(shared), creator_id=owner.id, created_by=owner.id,
        created_at=T0, updated_at=T0 + timedelta(minutes=minutes),
    )
    world.db.add(tpl)
    await world.db.flush()
    return tpl


async def _stored(world: AuthzWorld, template_id: uuid.UUID | str) -> CustomQueryTemplate:
    stmt = select(CustomQueryTemplate).where(CustomQueryTemplate.id == uuid.UUID(str(template_id)))
    return (await world.db.execute(stmt.execution_options(populate_existing=True))).scalar_one()


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch, extra_tables=(CustomQueryTemplate.__table__,)) as w:
        yield w


# ─── 纯函数 ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("scope", "shared", "reason"),
    [(1, None, "scope 必须是字符串"), ("shared", None, "不支持的模板范围：shared"),
     ("project", [], "指定项目共享至少需要一个项目"), ("project", ["x-1"], "共享项目标识非法：x-1")],
)
def test_adapter_reasons_are_chinese(scope, shared, reason):
    with pytest.raises(TemplateScopeValidationError) as exc:
        TemplateScopeAdapter.normalize(scope, shared)
    assert str(exc.value) == reason


def test_config_to_request_translates_every_field():
    config = {
        "project_id": "存的项目", "year": 2019, "source": "ledger_entries", "filters": {"account_code": "1002"},
        "cell_range": "A1:C3", "sheet_name": "审定表", "filter_text": "只在界面过滤",
        "conditions": [{"field": "debit_amount", "op": "gt", "value": 1}], "condition_logic": "OR",
        "selected_columns": ["account_code", "debit_amount"], "sort_field": "debit_amount", "sort_order": "desc",
        "page_size": 200, "group": {"dimensions": ["account_code"]}, "pivot": None, "acnr_targets": ["E1/E1-14/C10"],
    }
    body = TemplateService.config_to_request(config, project_id=X, year=2025)
    assert body == {
        "project_id": str(X), "year": 2025, "source": "ledger_entries",
        "filters": {"account_code": "1002", "cell_range": "A1:C3", "sheet_name": "审定表"},
        "columns": ["account_code", "debit_amount"],
        "conditions": [{"field": "debit_amount", "op": "gt", "value": 1}], "condition_logic": "or",
        "limit": 200, "offset": 0, "sort": [{"field": "debit_amount", "direction": "desc"}],
        "group": {"dimensions": ["account_code"]}, "pivot": None, "acnr_targets": ["E1/E1-14/C10"],
    }
    # 翻页以调用方为准；没有 source 时用模板的 data_source；explicit sort 优先于 sort_field
    paged = TemplateService.config_to_request(
        {"sort": [{"field": "a", "direction": "asc"}], "sort_field": "b", "page_size": 50, "offset": 50},
        project_id=X, year=2024, limit=100, offset=300, fallback_source="tb_detail",
    )
    assert (paged["source"], paged["limit"], paged["offset"], paged["sort"]) == (
        "tb_detail", 100, 300, [{"field": "a", "direction": "asc"}])


def test_config_to_request_carries_acnr_targets():
    """acnr_targets 字段归 acnr-foundation-defect-closure D1（用户裁决 Q0）：模板执行原样传递，不去重、不改写。"""
    targets = ["E1/E1-14/C10", "E1/E1-14/C10", "S15/S15-1/B3"]
    assert TemplateService.config_to_request({"acnr_targets": targets}, project_id=X, year=2025)["acnr_targets"] == targets


@pytest.mark.parametrize(
    "value", [{"$param": "materiality_performance"}, ["2025-01-01", {"$param": "period_end"}]],
)
def test_config_to_request_rejects_unresolved_params(value):
    config = {"conditions": [{"field": "debit_amount", "op": "gte", "value": value}]}
    with pytest.raises(ValueError, match="参数「(materiality_performance|period_end)」尚未取值"):
        TemplateService.config_to_request(config, project_id=X, year=2025)


# ─── 可见性与列表 ─────────────────────────────────────────────────────────────


async def test_visible_templates_filters_before_truncating(world, monkeypatch):
    """较新的不可见候选再多，也挤不掉较旧的可见模板（design §3.6 先过滤后截断）。"""
    monkeypatch.setattr(template_service_module, "_CANDIDATE_BATCH", 2)
    viewer = await world.user(UserRole.auditor)
    other = await world.user(UserRole.manager)
    await world.other_project()
    for i in range(5):  # 较新：共享给 viewer 无权的 Y ⇒ 过 SQL 候选、不过可见判定
        await _template(world, other, name=f"【测试】不可见{i}", scope="project", shared=[Y], minutes=20 + i)
    public = [await _template(world, other, name=f"【测试】公开{i}", scope="public", minutes=10 + i) for i in range(3)]
    own = await _template(world, viewer, name="【测试】本人私有", scope="private", minutes=1)
    await _template(world, other, name="【测试】他人私有", scope="private", minutes=30)

    top3 = await template_service.visible_templates(viewer, world.db, limit=3)
    assert [t.id for t in top3] == [t.id for t in reversed(public)]
    everything = await template_service.visible_templates(viewer, world.db)
    assert [t.id for t in everything] == [*(t.id for t in reversed(public)), own.id]


async def test_auditor_lists_admin_public_template(world):
    """变异 #12 的靶子：管理员保存的公开模板（入库 public），审计员在列表里看得到（原先只认 global ⇒ 0 条）。"""
    admin = (await world.admin_non_member()).user
    auditor = await world.user(UserRole.auditor)
    public = await _template(world, admin, name="【测试】管理员公开", scope="public")
    private = await _template(world, admin, name="【测试】管理员私有", scope="private")
    async with world.client(custom_query.router, user=auditor) as client:
        response = await client.get(f"{CQ}/templates")
    assert response.status_code == 200, response.text
    listed = {item["id"]: item for item in response.json()["templates"]}
    assert str(public.id) in listed and str(private.id) not in listed
    assert (listed[str(public.id)]["scope"], listed[str(public.id)]["is_owner"]) == ("public", False)


async def test_team_template_is_visible_to_anchor_members_only(world):
    owner = await world.user(UserRole.manager)
    member = (await world.member("edit", "auditor")).user
    outsider = (await world.non_member_with_other_project()).user
    team = await _template(world, owner, name="【测试】团队", scope="team", config={"source": "tb_detail", "project_id": str(X)})
    for user, seen in ((member, True), (outsider, False)):
        async with world.client(custom_query.router, user=user) as client:
            listed = {item["id"] for item in (await client.get(f"{CQ}/templates")).json()["templates"]}
            detail = await client.get(f"{CQ}/templates/{team.id}")
        assert (str(team.id) in listed, detail.status_code) == (seen, 200 if seen else 403)


# ─── 保存与更新 ───────────────────────────────────────────────────────────────


async def test_save_private_project_and_legacy_global(world):
    """原先 save_template 不认 private / project ⇒ 500（AQ-16）；历史 global 入库为 public。"""
    editor = (await world.member("edit", "auditor")).user
    bodies = {
        "private": {"scope": "private"},
        "project": {"scope": "project", "shared_project_ids": [str(X)]},
        "public": {"scope": "global"},
    }
    async with world.client(custom_query.router, user=editor) as client:
        for expected, extra in bodies.items():
            response = await client.post(f"{CQ}/templates", json={
                "name": f"【测试】AQL-B8 {expected}", "data_source": "tb_detail", "config": {"source": "tb_detail"},
                **extra})
            assert response.status_code == 201, response.text
            row = await _stored(world, response.json()["id"])
            assert (response.json()["scope"], row.scope) == (expected, expected)
    assert (await _stored(world, response.json()["id"])).shared_project_ids == []


async def test_blank_name_is_400_with_a_chinese_reason(world):
    user = await world.user(UserRole.auditor)
    async with world.client(custom_query.router, user=user) as client:
        created = await client.post(f"{CQ}/templates", json={
            "name": "   ", "data_source": "tb_detail", "config": {}, "scope": "private"})
        mine = await _template(world, user, name="【测试】改名", scope="private")
        renamed = await client.put(f"{CQ}/templates/{mine.id}", json={"name": "  "})
    for response in (created, renamed):
        assert response.status_code == 400, response.text
        assert response.json()["detail"] == {"error_code": "TEMPLATE_INVALID", "message": "名称非法：不能为空"}
    assert (await _stored(world, mine.id)).name == "【测试】改名"


async def test_update_with_legacy_global_is_stored_public(world):
    """变异 B8-a 的靶子：更新末尾曾把 body.scope 原样写回 ⇒ 传 global 入库仍是 global（读回才看得出，响应已归一）。"""
    owner = await world.user(UserRole.auditor)
    mine = await _template(world, owner, name="【测试】改范围", scope="private")
    async with world.client(custom_query.router, user=owner) as client:
        response = await client.put(f"{CQ}/templates/{mine.id}", json={"scope": "global", "name": "【测试】改范围后"})
    assert response.status_code == 200, response.text
    row = await _stored(world, mine.id)
    assert (row.scope, row.name, response.json()["scope"]) == ("public", "【测试】改范围后", "public")


# ─── 读取与执行 ───────────────────────────────────────────────────────────────


async def test_reading_invisible_template_is_403_in_chinese(world):
    admin = (await world.admin_non_member()).user
    auditor = await world.user(UserRole.auditor)
    private = await _template(world, admin, name="【测试】管理员私有", scope="private")
    async with world.client(custom_query.router, user=auditor) as client:
        response = await client.get(f"{CQ}/templates/{private.id}")
    assert (response.status_code, response.json()["detail"]) == (403, NOT_VISIBLE)


async def test_execute_invisible_template_is_403(world):
    """变异 B8-b 的靶子：TemplateForbiddenError 原先未映射 ⇒ 500。"""
    admin = (await world.admin_non_member()).user
    partner = await world.user(UserRole.partner)  # 可访问全部项目，但私有模板只给作者
    private = await _template(world, admin, name="【测试】管理员私有", scope="private")
    async with world.client(custom_query.router, user=partner) as client:
        response = await client.post(f"{CQ}/templates/{private.id}/execute", json={"project_id": str(X), "year": 2025})
    assert (response.status_code, response.json()["detail"]) == (403, NOT_VISIBLE)


async def test_unknown_or_malformed_template_id(world):
    user = await world.user(UserRole.auditor)
    async with world.client(custom_query.router, user=user) as client:
        missing = await client.get(f"{CQ}/templates/{uuid.uuid4()}")
        malformed = await client.post(f"{CQ}/templates/abc/execute", json={"project_id": str(X)})
    assert (missing.status_code, missing.json()["detail"]["error_code"]) == (404, "TEMPLATE_NOT_FOUND")
    assert (malformed.status_code, malformed.json()["detail"]["error_code"]) == (400, "INVALID_TEMPLATE_ID")


@pytest.mark.parametrize(
    ("config", "status", "code"),
    [({"source": "tb_detail", "filters": ["不是对象"]}, 422, "TEMPLATE_CONFIG_INVALID"),
     ({"source": "tb_detail", "conditions": [{"field": "audited_amount", "op": "gte",
                                              "value": {"$param": "materiality_performance"}}]}, 400, "TEMPLATE_INVALID")],
)
async def test_bad_stored_config_is_4xx_not_500(world, config, status, code):
    """库里存了不合格的配置（filters 不是对象 / 条件里还有没取值的参数占位）：执行 4xx 中文原因，不 500、不查数。"""
    owner = (await world.member("edit", "auditor")).user
    tpl = await _template(world, owner, name="【测试】坏配置", scope="private", config=config)
    async with world.client(custom_query.router, user=owner) as client:
        response = await client.post(f"{CQ}/templates/{tpl.id}/execute", json={"project_id": str(X), "year": 2025})
    assert (response.status_code, response.json()["detail"]["error_code"]) == (status, code), response.text
    assert "模板" in response.json()["detail"]["message"]


async def test_target_project_is_checked_before_the_year(world):
    """变异 B8-g 的靶子：执行先校验目标项目归属、再解析年度。目标项目没有审计年度时，无权用户得 403（不从 422 得知该项目
    有没有审计年度），有权用户得 422 平台统一文案（R9.3）。"""
    admin = (await world.admin_non_member()).user
    outsider = await world.user(UserRole.auditor)
    public = await _template(world, admin, name="【测试】公开", scope="public")
    url = f"{CQ}/templates/{public.id}/execute"
    async with world.client(custom_query.router, user=outsider) as client:
        denied = await client.post(url, json={"project_id": str(X)})
    async with world.client(custom_query.router, user=admin) as client:
        no_year = await client.post(url, json={"project_id": str(X)})
    # 先比状态码再取 error_code：变异 B8-g（去掉函数体内归属校验）时无权用户拿到 422（detail 是字符串），
    # 红在「403 ≠ 422」上，而不是取 detail["error_code"] 时的 TypeError（B8 评审非阻塞 #1）
    assert denied.status_code == 403, f"无权用户应先被归属校验拒绝（403），实得 {denied.status_code}：{denied.text[:300]}"
    assert denied.json()["detail"]["error_code"] == "FORBIDDEN_PROJECT"
    assert (no_year.status_code, no_year.json()["detail"]) == (422, NO_YEAR)
