"""构建器作用域真 PG 回归（advanced-query-linkage-closure 任务 9；R1.2、R3.1~R3.3、R3.5 后端；ADR-AQL-09；
变异 #2、#5、#16、B3-a、B3-b）。

请求经生产注册的 query_builder router 真发（夹具 ``builder``：真库回滚事务会话，见 ``builder_client``）；金标准一律在
测试内用独立 SQL 现算（``gold``），数值随真库变化，不写死。写入只在回滚事务里、只写自建【测试】项目；报表配置副本行的
用例在真 PG 临时 schema（``pg_world``）里造身份与数据。

受限 / 主管身份的金标准按 design §10.2：OwnershipGuard 可访问 − 已删项目 − 对其设有审计循环范围的项目（任务 23，B6）。

🔴 2026-11-03 阶段 0 改造：原先读真实账号 e2e_manager（系统经理，只经委派访问一个项目、没有成员行 ⇒ 链路不唯一 ⇒
受限）与 u_011abb97dd2d4101（系统 auditor、成员行 manager / edit + 经理委派 ⇒ 本项目主管），并写死华氏 / 宜宾临港店 /
【UAT】子公司A 三个项目 UUID；两个账号与三个项目现算都已不存在。身份改为在回滚事务里按同一形态自建
（``insert_member``，另加「成员行审计员 + 审计员委派 D 循环」这种按循环委派的受限形态）；真实分布判据按能力解析
（``tb_detail`` / ``balance_with_narrowing_active_dataset``）；结构分支（已删行不可见、LEFT JOIN 无匹配保留基表行）
在自建项目上造行。自建行只在本事务里可见 ⇒ 可访问集合等前置一律走被测会话现算，不走 ``gold``（换连接读到的是 0 行）。
"""
from __future__ import annotations

import datetime as dt
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app import deps
from app.models.audit_platform_models import AccountCategory, TbBalance, TrialBalance
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.models.report_models import ReportConfig
from app.models.workpaper_models import WpIndex
from app.routers import query_builder
from tests.advanced_query_linkage.gold import active_sql
from tests.advanced_query_linkage.writable_projects import insert_member
from tests.authz_world import OTHER_PROJECT_ID, TARGET_PROJECT_ID, pg_world

pytestmark = pytest.mark.pg_only

ACCESSIBLE_LIVE_SQL = """
SELECT a.pid::text FROM (
  SELECT pu.project_id AS pid FROM project_users pu WHERE pu.user_id = :uid AND NOT pu.is_deleted
  UNION
  SELECT pa.project_id FROM project_assignments pa JOIN staff_members s ON s.id = pa.staff_id
   WHERE s.user_id = :uid AND NOT pa.is_deleted AND NOT s.is_deleted) a
JOIN projects p ON p.id = a.pid AND NOT p.is_deleted
"""
_PROJECTS = {"table": "projects", "fields": ["id", "name"], "limit": 1000}

#: 自建身份形态（``insert_member`` 的参数）→ 是否被排除出构建器作用域（对本人设有审计循环范围）
IDENTITIES: dict[str, tuple[dict, bool]] = {
    # 原 e2e_manager 的形态：系统经理、只经委派访问、没有成员行 ⇒ 链路不唯一 ⇒ 受限（范围为空列表）
    "assignment_only_manager": ({"system_role": "manager", "member_role": None, "assignment_role": "manager"}, True),
    # 按循环委派的受限形态（与 test_aql_cycle_scope_pg 同形）：系统经理（过构建器角色门；系统 auditor 且非任一项目经理
    # 会先被 ROLE_FORBIDDEN 挡掉、走不到作用域）、成员行审计员 + 审计员委派勾选 D 循环 ⇒ 受限（范围 ["D"]）
    "cycle_scoped_member": (
        {"system_role": "manager", "member_role": "auditor", "assignment_role": "auditor", "assigned_cycles": ["D"]},
        True,
    ),
    # 原 u_011abb97dd2d4101 的形态：系统 auditor、成员行经理 / edit + 经理委派 ⇒ 链路唯一的本项目主管 ⇒ 不受限
    "member_manager": ({"system_role": "auditor", "member_role": "manager", "assignment_role": "manager"}, False),
}

_INSERT_ACCOUNT = sa.text(
    "INSERT INTO account_chart (id, project_id, account_code, account_name, direction, level, category, source) "
    "VALUES (gen_random_uuid(), :pid, :code, :name, CAST('debit' AS account_direction), 1, "
    "CAST('asset' AS account_category), CAST(:source AS account_source))"
)


def _ids(data: dict, column: str = "id") -> set[str]:
    return {str(row[column]) for row in data["rows"]}


async def _identity(builder, project, identity: str):
    spec, _excluded = IDENTITIES[identity]
    return await insert_member(builder.session, project_id=project.id, **spec)


async def _accessible(session, user) -> set[str]:
    """被测会话里现算的可访问未删项目（自建身份只在本事务里可见）。"""
    return {r[0] for r in await session.execute(sa.text(ACCESSIBLE_LIVE_SQL), {"uid": user.id})}


# ─── projects 与人员表（AQ-06；变异 #5、B3-a）──────────────────────────────────


async def test_admin_projects_are_all_live_projects(builder, gold) -> None:
    live = {r[0] for r in await gold.rows("SELECT id::text FROM projects WHERE NOT is_deleted")}
    deleted = await gold.scalar("SELECT count(*) FROM projects WHERE is_deleted")
    assert live and deleted > 0, "前置：库里同时有未删与已删项目，用例才证明得了「排除已删」"
    data = await builder.ok(builder.admin, _PROJECTS)
    assert data["total"] == len(live) and _ids(data) == live


async def test_admin_rows_exclude_deleted_projects(builder, gold) -> None:
    """不限项目的身份（admin / partner）也只查未删项目的行：现库已删项目上仍挂着未删的试算 / 序时账行。"""
    sql = ("SELECT count(*) FROM trial_balance t JOIN projects p ON p.id = t.project_id AND {deleted} p.is_deleted "
           "WHERE NOT t.is_deleted")
    live, on_deleted = await gold.scalar(sql.format(deleted="NOT")), await gold.scalar(sql.format(deleted=""))
    assert live > 0 and on_deleted > 0, "前置：已删项目上有未删的试算行（否则「排除已删项目」无从验证）"
    data = await builder.ok(builder.admin, {"table": "trial_balance",
                                            "aggregates": [{"func": "count", "field": "*", "alias": "n"}]})
    assert data["rows"][0]["n"] == live, f"应只数未删项目的 {live} 行（含已删项目为 {live + on_deleted}）"


@pytest.mark.parametrize("identity", sorted(IDENTITIES))
async def test_scoped_identity_sees_only_accessible_live_projects(builder, writable_project, identity: str) -> None:
    """受限身份（只经委派的系统经理、按循环委派的成员）⇒ 0 行 + 排除提示；链路唯一的本项目主管 ⇒ 只见其项目
    （任务 23，变异 #19 / #36 的构建器侧）。"""
    excluded = IDENTITIES[identity][1]
    user = await _identity(builder, writable_project, identity)
    accessible = await _accessible(builder.session, user)
    assert accessible == {str(writable_project.id)}, f"前置：{identity} 恰好能访问自建项目，现算 {sorted(accessible)}"
    restricted = {pid for pid in accessible
                  if await deps.get_user_scope_cycles(user, uuid.UUID(pid), builder.session) is not None}
    assert bool(restricted) is excluded, f"前置（身份形态）：{identity} 受限 = {excluded}，现算 {sorted(restricted)}"
    expected = accessible - restricted
    data = await builder.ok(user, _PROJECTS)
    assert _ids(data) == expected and data["total"] == len(expected)
    assert data["scope"] == {"all_projects": False, "project_count": len(expected), "unscoped_tables": [],
                             "requested_project_id": None}
    exclusion = f"已排除 {len(restricted)} 个对您设有审计循环范围的项目，请在业务视图中查询"
    assert (exclusion in data["warnings"]) is excluded, data["warnings"]


@pytest.mark.parametrize("body", [
    {"table": "staff_members", "fields": ["id", "name"]},
    {"table": "work_hours", "joins": [{"table": "staff_members", "type": "left"}],
     "fields": ["work_hours.hours", "staff_members.name"]},
], ids=["base", "join-target"])
async def test_manager_cannot_read_staff_members(builder, writable_project, body: dict) -> None:
    manager = await _identity(builder, writable_project, "assignment_only_manager")
    assert manager.role.value == "manager"
    response = await builder.execute(manager, body)
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["error_code"] == "TABLE_ROLE_FORBIDDEN"


# ─── 指定项目（AQ-18）──────────────────────────────────────────────────────────


async def test_explicit_project_limits_scope(builder, gold, picks) -> None:
    project = await picks.resolve("tb_detail")
    expected = await gold.scalar(
        "SELECT count(*) FROM trial_balance WHERE project_id = :pid AND year = :year AND NOT is_deleted",
        pid=project.id, year=project.audit_year)
    data = await builder.ok(builder.admin, {
        "table": "trial_balance", "fields": ["project_id", "standard_account_code"], "project_id": str(project.id),
        "year": project.audit_year, "limit": 1000})
    assert expected > 0 and data["total"] == expected and _ids(data, "project_id") == {str(project.id)}, project
    assert data["scope"]["requested_project_id"] == str(project.id) and data["scope"]["project_count"] == 1


async def test_inaccessible_or_deleted_project_is_403_and_not_executed(builder, gold, picks, writable_project,
                                                                       monkeypatch) -> None:
    entered: list[int] = []
    real = query_builder.cancellable_query

    def _spy(db, timeout_ms):  # 执行的下一层：进入即记一次（被测的作用域解析不替换）
        entered.append(timeout_ms)
        return real(db, timeout_ms)

    monkeypatch.setattr(query_builder, "cancellable_query", _spy)
    member = await _identity(builder, writable_project, "member_manager")
    foreign = await picks.resolve("tb_detail")
    assert str(foreign.id) not in await _accessible(builder.session, member), f"前置：自建成员不能访问 {foreign}"
    deleted = (await gold.rows("SELECT id::text FROM projects WHERE is_deleted ORDER BY created_at LIMIT 1"))[0][0]
    for user, project in ((member, str(foreign.id)), (builder.admin, deleted)):
        response = await builder.execute(user, {"table": "trial_balance", "fields": ["id"], "project_id": project})
        assert response.status_code == 403, response.text
        assert response.json()["detail"]["error_code"] == "FORBIDDEN_PROJECT"
    assert entered == [], "403 之前不得执行任何查询"
    await builder.ok(member, {"table": "trial_balance", "fields": ["id"]})
    assert len(entered) == 1, "反向对照：放行的请求确实经过执行这一层"


# ─── 数据集口径与已删行（AQ-02；变异 #2）──────────────────────────────────────


async def test_tb_balance_uses_the_active_dataset(builder, gold, picks) -> None:
    project = await picks.resolve("balance_with_narrowing_active_dataset")
    params = {"pid": project.id, "year": project.audit_year}
    count, closing = (await gold.rows(
        f"SELECT count(*), coalesce(sum(closing_balance), 0) FROM tb_balance t WHERE {active_sql('t')}", **params))[0]
    undeleted = await gold.scalar(
        "SELECT count(*) FROM tb_balance WHERE project_id = :pid AND year = :year AND NOT is_deleted", **params)
    assert 0 < count < undeleted, f"前置：{project} 有非生效数据集的行"
    data = await builder.ok(builder.admin, {
        "table": "tb_balance", "project_id": str(project.id), "year": project.audit_year,
        "aggregates": [{"func": "count", "field": "*", "alias": "n"}, {"func": "sum", "field": "closing_balance",
                                                                        "alias": "s"}]})
    (row,) = data["rows"]
    assert row["n"] == count
    assert abs(Decimal(str(row["s"])) - closing) < Decimal("0.01")


@pytest.mark.parametrize("with_active_dataset", [False, True], ids=["no-active-dataset", "active-dataset"])
async def test_deleted_rows_are_invisible(builder, writable_project, with_active_dataset: bool) -> None:
    """自建项目上一行未删、一行软删：有 / 没有 active 数据集两条口径分支都只见未删的那一行。"""
    project, session = writable_project, builder.session
    dataset_id = None
    if with_active_dataset:
        dataset = LedgerDataset(project_id=project.id, year=project.audit_year, status=DatasetStatus.active,
                                activated_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))
        session.add(dataset)
        await session.flush()
        dataset_id = dataset.id
    for code, deleted in (("AQLB3-LIVE", False), ("AQLB3-DELETED", True)):
        session.add(TbBalance(project_id=project.id, year=project.audit_year, company_code="001", account_code=code,
                              account_name="【测试】B3 回滚事务造行", dataset_id=dataset_id, is_deleted=deleted))
    await session.flush()
    data = await builder.ok(builder.admin, {
        "table": "tb_balance", "fields": ["account_code"], "project_id": str(project.id), "year": project.audit_year,
        "filters": [{"field": "account_code", "op": "like", "value": "AQLB3-"}]})
    assert [r["account_code"] for r in data["rows"]] == ["AQLB3-LIVE"] and data["total"] == 1


# ─── JOIN 目标的作用域在 ON（变异 #16）──────────────────────────────────────────


async def test_left_join_without_match_keeps_the_base_row(builder, writable_project) -> None:
    """自建项目：两行试算有标准科目、一行没有；1001 另有一行客户科目（登记只认标准科目，不得放大、不得取错名称）。"""
    project, session = writable_project, builder.session
    for code, name in (("1001", "库存现金"), ("1002", "银行存款"), ("AQLB3-NOMATCH", "【测试】B3 无对应标准科目")):
        session.add(TrialBalance(project_id=project.id, year=project.audit_year, company_code="001",
                                 standard_account_code=code, account_name=name,
                                 account_category=AccountCategory.asset, audited_amount=Decimal("1.00")))
    await session.flush()
    for code, name, source in (("1001", "【测试】标准 库存现金", "standard"), ("1001", "【测试】客户 库存现金", "client"),
                               ("1002", "【测试】标准 银行存款", "standard")):
        await session.execute(_INSERT_ACCOUNT, {"pid": project.id, "code": code, "name": name, "source": source})
    base = {"table": "trial_balance", "project_id": str(project.id), "year": project.audit_year, "limit": 1000}
    plain = await builder.ok(builder.admin, {**base, "fields": ["trial_balance.standard_account_code"]})
    joined = await builder.ok(builder.admin, {**base, "joins": [{"table": "account_chart", "type": "left"}],
                                              "fields": ["trial_balance.standard_account_code",
                                                         "account_chart.account_name"]})
    assert plain["total"] == joined["total"] == 3, (plain["total"], joined["total"])
    names = {r["trial_balance.standard_account_code"]: r["account_chart.account_name"] for r in joined["rows"]}
    assert names == {"1001": "【测试】标准 库存现金", "1002": "【测试】标准 银行存款", "AQLB3-NOMATCH": None}, names


# ─── 报表配置的项目副本行（变异 B3-b）────────────────────────────────────────────


@asynccontextmanager
async def _report_config_world(monkeypatch):
    # wp_index：PM / SM 补经理委派后是各自项目的主管，主管的范围要读项目循环（缺表即按受限处理、作用域被排除）
    async with pg_world(monkeypatch, extra_tables=(ReportConfig.__table__, WpIndex.__table__)) as world:
        await world.other_project()
        for number, standard in enumerate(("soe_standalone", f"project:{TARGET_PROJECT_ID}",
                                           f"project:{OTHER_PROJECT_ID}"), start=1):
            world.db.add(ReportConfig(report_type="balance_sheet", row_number=number, row_code=f"BS-{number:03d}",
                                      row_name="【测试】副本行可见性", applicable_standard=standard))
        await world.db.flush()
        yield world


async def test_report_config_project_copies_only_for_accessible_projects(monkeypatch) -> None:
    async with _report_config_world(monkeypatch) as world:
        pm = (await world.edit_member()).user  # X 上（manager, edit），系统 auditor
        sm_identity = await world.non_member_with_other_project(global_role="manager")  # 只在 Y 有成员行
        sm = sm_identity.user
        # 经理委派 ⇒ 链路唯一的本项目主管、不受循环范围限制（否则作用域被排除，见任务 23 / design §10.3）
        await world.eqcr_assignment("manager", user=pm)
        await world.eqcr_assignment("manager", user=sm, project=sm_identity.other_project)
        admin = (await world.admin_non_member()).user
        seen = {}
        for key, user in (("PM", pm), ("SM", sm), ("AD", admin)):
            async with world.client(query_builder.router, user=user) as client:
                response = await client.post("/api/query/execute", json={
                    "table": "report_config", "fields": ["applicable_standard"], "limit": 100})
            assert response.status_code == 200, response.text
            seen[key] = {r["applicable_standard"] for r in response.json()["rows"]}
    assert seen["PM"] == {"soe_standalone", f"project:{TARGET_PROJECT_ID}"}
    assert seen["SM"] == {"soe_standalone", f"project:{OTHER_PROJECT_ID}"}
    assert seen["AD"] == {"soe_standalone", f"project:{TARGET_PROJECT_ID}", f"project:{OTHER_PROJECT_ID}"}
