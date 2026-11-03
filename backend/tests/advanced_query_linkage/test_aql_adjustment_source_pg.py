"""调整分录源真 PG 回归（advanced-query-linkage-closure 任务 18；R5.2；design §3.1；变异 #7、B5-g）。

改造前（AQ-07）：取数器把「审计调整分录(AJE)」「重分类调整(RCL)」绑成大写 ``'AJE'`` / ``'RCL'`` 去比 PG 枚举
``adjustment_type``（取值 aje / rje / cf，没有 RCL）——两个叶子在真库恒 500；页面版不带类型时一律按 AJE 查；合并单位的
「调整分录」写死 ``'AJE'``，也不按单位过滤。

现在：adj_aje = aje、adj_rje = rje（旧键 adj_rcl 兼容）；通用源 ``adjustment`` 不带类型 = 全部类型（含 cf）并带类型列，
带类型时 AJE→aje、RJE / RCL→rje（大小写不敏感），其余 400；合并单位 ``consol_unit:{单位}:adjustment`` = 该单位的全部
类型；隐藏列 entry_group_id 随行返回。

请求经生产注册的 custom_query router（夹具 ``business``）；华氏只读。现库只有华氏有 2 行 aje、没有一个活项目有 rje / cf：
多类型形态在回滚事务里给【UAT】子公司A 造行（cf 不在 ORM 枚举里，用文本 SQL 写），造的行用同一会话独立 SQL 计数。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa

from tests.advanced_query_linkage.gold import AUDIT_YEAR, HS, UA

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


async def _seed(session) -> None:
    creator = (await session.execute(sa.text("SELECT id FROM users WHERE username = 'admin'"))).scalar_one()
    groups: dict[str, uuid.UUID] = {}
    for number, kind, company, account, debit, credit in SEED:
        await session.execute(sa.text(
            "INSERT INTO adjustments (id, project_id, year, company_code, adjustment_no, adjustment_type, description, "
            "account_code, account_name, debit_amount, credit_amount, entry_group_id, created_by) VALUES "
            "(:id, :pid, :year, :co, :no, CAST(:kind AS adjustment_type), '【UAT】B5 回滚事务造行', :acct, :acct, "
            ":dr, :cr, :grp, :creator)"),
            {"id": uuid.uuid4(), "pid": UA, "year": AUDIT_YEAR, "co": company, "no": number, "kind": kind,
             "acct": account, "dr": Decimal(debit), "cr": Decimal(credit),
             "grp": groups.setdefault(number, uuid.uuid4()), "creator": creator})


async def _count(session, where: str = "", **params) -> int:
    return (await session.execute(sa.text(
        "SELECT count(*) FROM adjustments WHERE project_id = :pid AND year = :year AND NOT is_deleted " + where),
        {"pid": UA, "year": AUDIT_YEAR, **params})).scalar_one()


async def test_hs_aje_rows_match_gold(business, gold) -> None:
    expected = await gold.rows(
        "SELECT adjustment_no, account_code, debit_amount, credit_amount, entry_group_id::text FROM adjustments "
        "WHERE project_id = :pid AND year = :year AND NOT is_deleted AND adjustment_type = 'aje' "
        "ORDER BY adjustment_no, id", pid=HS, year=AUDIT_YEAR)
    assert expected, "前置：华氏有审计调整分录"
    data = await business.ok(HS, "adj_aje", filters={"adjustment_type": "AJE"})
    got = [(r["adjustment_no"], r["account_code"], Decimal(str(r["debit_amount"])), Decimal(str(r["credit_amount"])),
            r["entry_group_id"]) for r in data["rows"]]
    assert data["total"] == len(expected), f"审计调整分录行数 {data['total']} ≠ 金标准 {len(expected)}"
    assert got == [tuple(row) for row in expected]
    assert "adjustment_type" not in data["columns"] and "entry_group_id" not in data["columns"], "隐藏列不进 columns"


@pytest.mark.parametrize("source", ["adj_rje", "adj_rcl"])
async def test_rje_without_rows_is_empty_not_error(business, gold, source: str) -> None:
    assert await gold.scalar("SELECT count(*) FROM adjustments WHERE project_id = :pid AND year = :year "
                             "AND NOT is_deleted AND adjustment_type = 'rje'", pid=HS, year=AUDIT_YEAR) == 0
    data = await business.ok(HS, source, filters={"adjustment_type": "RCL"})
    assert data["total"] == 0 and data["rows"] == []


async def test_generic_source_returns_all_types_with_type_column(business) -> None:
    await _seed(business.session)
    data = await business.ok(UA, "adjustment", limit=2000)
    assert data["total"] == len(data["rows"]) == await _count(business.session) == len(SEED)
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
async def test_typed_sources_and_legacy_values(business, source: str, filters: dict, kind: str) -> None:
    await _seed(business.session)
    data = await business.ok(UA, source, limit=2000, filters=filters)
    expected = await _count(business.session, "AND adjustment_type::text = :kind", kind=kind)
    assert expected > 0 and data["total"] == len(data["rows"]) == expected, (
        f"{source} {filters}：{data['total']} 行 ≠ 金标准 {expected}（类型 {kind}）")
    numbers = {r["adjustment_no"] for r in data["rows"]}
    assert numbers == {number for number, k, *_ in SEED if k == kind}


@pytest.mark.parametrize("value", ["CF", "XYZ"])
async def test_unknown_type_value_is_400(business, value: str) -> None:
    detail = await business.error(UA, "adjustment", 400, filters={"adjustment_type": value})
    assert detail["error_code"] == "INVALID_FILTER_VALUE" and "AJE" in detail["message"], detail


async def test_consol_unit_adjustment_is_scoped_to_its_company(business) -> None:
    await _seed(business.session)
    data = await business.ok(UA, f"consol_unit:{CO_A}:adjustment", limit=2000)
    expected = await _count(business.session, "AND company_code = :co", co=CO_A)
    assert expected == sum(1 for row in SEED if row[2] == CO_A)
    assert data["total"] == expected, f"合并单位调整分录 {data['total']} 行 ≠ 该单位金标准 {expected}（未按单位过滤）"
    assert {r["adjustment_type"] for r in data["rows"]} == {"aje", "rje"} and "adjustment_type" in data["columns"]


async def test_adjustment_conditions_and_columns(business) -> None:
    await _seed(business.session)
    data = await business.ok(UA, "adjustment", limit=2000, columns=["adjustment_no", "debit_amount"],
                             conditions=[{"field": "debit_amount", "op": "gt", "value": 0}])
    expected = await _count(business.session, "AND debit_amount > 0")
    assert data["total"] == expected and data["columns"] == ["adjustment_no", "debit_amount"]
    assert all(Decimal(str(r["debit_amount"])) > 0 for r in data["rows"])
