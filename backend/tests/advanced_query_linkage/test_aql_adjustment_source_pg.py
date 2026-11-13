"""调整分录源真 PG 回归（advanced-query-linkage-closure 任务 18；R5.2；design §3.1；变异 #7、B5-g）。

改造前（AQ-07）：取数器把「审计调整分录(AJE)」「重分类调整(RCL)」绑成大写 ``'AJE'`` / ``'RCL'`` 去比 PG 枚举
``adjustment_type``（取值 aje / rje / cf，没有 RCL）——两个叶子在真库恒 500；页面版不带类型时一律按 AJE 查；合并单位的
「调整分录」写死 ``'AJE'``，也不按单位过滤。

现在：adj_aje = aje、adj_rje = rje（旧键 adj_rcl 兼容）；通用源 ``adjustment`` 不带类型 = 全部类型（含 cf）并带类型列，
带类型时 AJE→aje、RJE / RCL→rje（大小写不敏感），其余 400；合并单位 ``consol_unit:{单位}:adjustment`` = 该单位的全部
类型；隐藏列 entry_group_id 随行返回。

请求经生产注册的 custom_query router（夹具 ``business``）。

🔴 2026-11-01 阶段 0 改造：原先读华氏（``HS``）的真实 AJE、在【UAT】子公司A（``UA``）上造多类型行，两个 UUID 现算
都已不存在。现在真实行对账按能力 ``adjustments_aje`` 解析（审计年度有 AJE 的项目，只读）；多类型形态在回滚事务里给
自建的【测试】项目造行（cf 不在 ORM 枚举里，用文本 SQL 写），造的行用同一会话独立 SQL 计数。
原「华氏 RJE 恰好 0 行」那条是当年的偶然事实而非业务不变式，拆成两条：真实项目上 RJE 源行数 = 金标准现算（空与非空
都对）；自建空项目上 RJE 源 200 + 0 行。

🔴 2026-11-03 磁盘变异校正（closure §16.8）：把映射表 ``"rcl": "rje"`` 改成 ``"rcl": "RCL"``，空项目那条**照样绿** ——
类型列按文本比较，未映射的值只是匹配不到；且 ``adj_rje`` / ``adj_rcl`` 两个源键的类型由 ``fixed_filters`` 固定为
``rje``、覆盖请求里的 ``RCL``。这张映射表只有通用源 ``adjustment`` 带 ``RCL`` 时才用得到，钉住它的是
``test_typed_sources_and_legacy_values[generic-RCL]``（该变异下唯一变红的一格）。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa

from tests.advanced_query_linkage.project_picks import Pick

pytestmark = pytest.mark.pg_only

CO_A, CO_B = "AQLB5-CO-A", "AQLB5-CO-B"
#: （分录号, 类型, 单位, 科目, 借, 贷）——同一分录组两行；cf 只在另一单位
SEED = (
    ("AQLB5-AJE-1", "aje", CO_A, "1001", "10.00", "0.00"),
    ("AQLB5-AJE-1", "aje", CO_A, "1002", "0.00", "10.00"),
    ("AQLB5-RJE-1", "rje", CO_A, "1122", "5.00", "0.00"),
    ("AQLB5-RJE-1", "rje", CO_A, "2203", "0.00", "5.00"),
    ("AQLB5-CF-1", "cf", CO_B, "1001", "1.00", "0.00"),
)


async def _seed(session, project: Pick) -> None:
    creator = (await session.execute(sa.text("SELECT id FROM users WHERE username = 'admin'"))).scalar_one()
    groups: dict[str, uuid.UUID] = {}
    for number, kind, company, account, debit, credit in SEED:
        await session.execute(sa.text(
            "INSERT INTO adjustments (id, project_id, year, company_code, adjustment_no, adjustment_type, description, "
            "account_code, account_name, debit_amount, credit_amount, entry_group_id, created_by) VALUES "
            "(:id, :pid, :year, :co, :no, CAST(:kind AS adjustment_type), '【测试】B5 回滚事务造行', :acct, :acct, "
            ":dr, :cr, :grp, :creator)"),
            {"id": uuid.uuid4(), "pid": project.id, "year": project.audit_year, "co": company, "no": number,
             "kind": kind, "acct": account, "dr": Decimal(debit), "cr": Decimal(credit),
             "grp": groups.setdefault(number, uuid.uuid4()), "creator": creator})


async def _count(session, project: Pick, where: str = "", **params) -> int:
    """自建行只在本事务里可见：金标准必须用同一会话读（换连接读到的是 0，会以「两边都空」假绿）。"""
    return (await session.execute(sa.text(
        "SELECT count(*) FROM adjustments WHERE project_id = :pid AND year = :year AND NOT is_deleted " + where),
        {"pid": project.id, "year": project.audit_year, **params})).scalar_one()


async def test_real_aje_rows_match_gold(business, gold, picks) -> None:
    project = await picks.resolve("adjustments_aje")
    expected = await gold.rows(
        "SELECT adjustment_no, account_code, debit_amount, credit_amount, entry_group_id::text FROM adjustments "
        "WHERE project_id = :pid AND year = :year AND NOT is_deleted AND adjustment_type = 'aje' "
        "ORDER BY adjustment_no, id", pid=project.id, year=project.audit_year)
    assert expected, f"能力 adjustments_aje 选中 {project} 却查不到 AJE 行 ⇒ 判据与金标准口径不一致"
    data = await business.ok(project, "adj_aje", limit=2000, filters={"adjustment_type": "AJE"})
    got = [(r["adjustment_no"], r["account_code"], Decimal(str(r["debit_amount"])), Decimal(str(r["credit_amount"])),
            r["entry_group_id"]) for r in data["rows"]]
    assert data["total"] == len(expected), f"审计调整分录行数 {data['total']} ≠ 金标准 {len(expected)}（{project}）"
    assert got == [tuple(row) for row in expected]
    assert "adjustment_type" not in data["columns"] and "entry_group_id" not in data["columns"], "隐藏列不进 columns"


@pytest.mark.parametrize("source", ["adj_rje", "adj_rcl"])
async def test_rje_sources_match_gold_on_a_real_project(business, gold, picks, source: str) -> None:
    """真实项目：RJE 源（含旧键 adj_rcl + 旧值 RCL）行数 = 金标准现算，空与非空都对。"""
    project = await picks.resolve("adjustments_aje")
    expected = await gold.scalar(
        "SELECT count(*) FROM adjustments WHERE project_id = :pid AND year = :year AND NOT is_deleted "
        "AND adjustment_type = 'rje'", pid=project.id, year=project.audit_year)
    data = await business.ok(project, source, limit=2000, filters={"adjustment_type": "RCL"})
    assert data["total"] == len(data["rows"]) == expected, (project, source, data["total"], expected)
    assert {r["adjustment_type"] for r in data["rows"]} <= {"rje"}


@pytest.mark.parametrize("source", ["adj_rje", "adj_rcl"])
async def test_rje_without_rows_is_empty_not_error(business, writable_project, source: str) -> None:
    """没有 RJE 的项目：两个 RJE 源键带旧值 RCL 都是 200 + 0 行，不报错。

    改造前取数器把大写 'RCL' 直接绑到枚举上，这里会 500；现在类型由源键固定、列按文本比较，这条只钉「空结果不报错」，
    RCL → rje 的映射由 ``test_typed_sources_and_legacy_values[generic-RCL]`` 钉（见模块说明）。
    """
    assert await _count(business.session, writable_project, "AND adjustment_type::text = 'rje'") == 0
    data = await business.ok(writable_project, source, filters={"adjustment_type": "RCL"})
    assert data["total"] == 0 and data["rows"] == []


async def test_generic_source_returns_all_types_with_type_column(business, writable_project) -> None:
    await _seed(business.session, writable_project)
    data = await business.ok(writable_project, "adjustment", limit=2000)
    assert data["total"] == len(data["rows"]) == await _count(business.session, writable_project) == len(SEED)
    assert "adjustment_type" in data["columns"]
    assert {r["adjustment_type"] for r in data["rows"]} == {"aje", "rje", "cf"}, "通用源含 cf"
    assert all(r["entry_group_id"] for r in data["rows"]), "分录组随行返回（下钻按组）"


@pytest.mark.parametrize(("source", "filters", "kind"), [
    ("adj_aje", {}, "aje"),
    ("adj_rje", {}, "rje"),
    ("adj_rcl", {}, "rje"),
    ("adj_aje", {"adjustment_type": "AJE"}, "aje"),
    ("adj_rcl", {"adjustment_type": "RCL"}, "rje"),
    ("adjustment", {"adjustment_type": "AJE"}, "aje"),
    ("adjustment", {"adjustment_type": "aje"}, "aje"),
    ("adjustment", {"adjustment_type": "RJE"}, "rje"),
    ("adjustment", {"adjustment_type": "RCL"}, "rje"),
], ids=["aje", "rje", "rcl-alias", "aje-upper", "rcl-upper", "generic-AJE", "generic-aje", "generic-RJE", "generic-RCL"])
async def test_typed_sources_and_legacy_values(business, writable_project, source: str, filters: dict, kind: str) -> None:
    await _seed(business.session, writable_project)
    data = await business.ok(writable_project, source, limit=2000, filters=filters)
    expected = await _count(business.session, writable_project, "AND adjustment_type::text = :kind", kind=kind)
    assert expected > 0 and data["total"] == len(data["rows"]) == expected, (
        f"{source} {filters}：{data['total']} 行 ≠ 金标准 {expected}（类型 {kind}）")
    numbers = {r["adjustment_no"] for r in data["rows"]}
    assert numbers == {number for number, k, *_ in SEED if k == kind}


@pytest.mark.parametrize("value", ["CF", "XYZ"])
async def test_unknown_type_value_is_400(business, writable_project, value: str) -> None:
    detail = await business.error(writable_project, "adjustment", 400, filters={"adjustment_type": value})
    assert detail["error_code"] == "INVALID_FILTER_VALUE" and "AJE" in detail["message"], detail


async def test_consol_unit_adjustment_is_scoped_to_its_company(business, writable_project) -> None:
    await _seed(business.session, writable_project)
    data = await business.ok(writable_project, f"consol_unit:{CO_A}:adjustment", limit=2000)
    expected = await _count(business.session, writable_project, "AND company_code = :co", co=CO_A)
    assert expected == sum(1 for row in SEED if row[2] == CO_A)
    assert data["total"] == expected, f"合并单位调整分录 {data['total']} 行 ≠ 该单位金标准 {expected}（未按单位过滤）"
    assert {r["adjustment_type"] for r in data["rows"]} == {"aje", "rje"} and "adjustment_type" in data["columns"]


async def test_adjustment_conditions_and_columns(business, writable_project) -> None:
    await _seed(business.session, writable_project)
    data = await business.ok(writable_project, "adjustment", limit=2000, columns=["adjustment_no", "debit_amount"],
                             conditions=[{"field": "debit_amount", "op": "gt", "value": 0}])
    expected = await _count(business.session, writable_project, "AND debit_amount > 0")
    assert data["total"] == expected and data["columns"] == ["adjustment_no", "debit_amount"]
    assert all(Decimal(str(r["debit_amount"])) > 0 for r in data["rows"])
