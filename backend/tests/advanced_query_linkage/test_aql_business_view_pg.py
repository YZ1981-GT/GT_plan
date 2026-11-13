"""业务视图口径真 PG 回归（advanced-query-linkage-closure 任务 8；R1.1、R1.3、R2.1~R2.5、R2.7、R5.8、R6.1~R6.3；
ADR-AQL-06 / 07；变异 #1、#3、#4、#14）。

被测请求经 httpx ASGI 真发到**生产注册**的 custom_query router（``authz_world.build_app``），只替换
``get_current_user``（系统 admin，不触达成员判定）与 ``get_db``（真库回滚事务会话，结束整体回滚）；Redis 换成
独占的 fakeredis、审计写入换成空操作——只读，不在共享库与共享 Redis 留任何东西。金标准一律在测试内用独立 SQL
现算（``gold.active_sql`` 即 §0.13 的 ``ACTIVE(t)``），数值随真库变化，不写死。

🔴 2026-11-01 阶段 0 改造：原先固定用和平药房 / 华氏 / 宜宾临港店 / 和平物流（``HP`` / ``HS`` / ``YB`` / ``WL``）四个
UUID，现算都已不存在 ⇒ 改按能力解析（见 ``project_picks``），年度取所选项目自己的审计年度；「没有 active 数据集」
这条结构分支现库没有任何活项目满足，改在回滚事务里自建（夹具 ``no_active_dataset_project``，金标准同会话读）。
用例名去掉了项目前缀（``test_hp_*`` 等），名字只描述被测行为。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import fakeredis
import fakeredis.aioredis
import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient

import app.core.redis as core_redis
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole
from app.models.core import User
from app.routers import custom_query
from app.services import dataset_query
from app.services.custom_query import audit_helper
from app.services.custom_query import source_registry as sr
from app.services.custom_query.paged_fetch import MAX_SQL_OFFSET
from app.services.custom_query.pagination import FETCH_HARD_CAP
from app.services.dataset_service import DatasetService
from tests.advanced_query_linkage.gold import active_sql
from tests.advanced_query_linkage.project_picks import Pick
from tests.authz_world import build_app

pytestmark = pytest.mark.pg_only
EXEC = "/api/custom-query/execute"
_ACTIVE_LEDGER = f"FROM tb_ledger t WHERE {active_sql('t')}"
_LEDGER_DEFAULT_ORDER = "ORDER BY voucher_date DESC, voucher_no ASC, entry_seq ASC NULLS LAST, id ASC"


@pytest_asyncio.fixture
async def client(pg_rollback_session, monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    monkeypatch.setattr(core_redis, "redis_client", redis)
    monkeypatch.setattr(core_redis, "_redis_client", redis)

    async def _no_audit(**_kwargs):  # 审计不落真库（被测的是取数口径，不是审计）
        return True

    monkeypatch.setattr(audit_helper, "_log_unthrottled", _no_audit)
    api = build_app(custom_query.router)
    admin = User(id=uuid.uuid4(), username="aql-b2-admin", email="aql-b2@test.invalid", hashed_password="x",
                 role=UserRole.admin, is_active=True)

    async def _db():
        yield pg_rollback_session

    async def _user() -> User:
        return admin

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://aql-b2") as http:
        yield http
    await redis.aclose()


async def _execute(client: AsyncClient, project: Pick, source: str, **body):
    return await client.post(EXEC, json={"project_id": str(project.id), "year": project.audit_year,
                                         "source": source, "limit": 100, **body})


async def _ok(client: AsyncClient, project: Pick, source: str, **body) -> dict:
    response = await _execute(client, project, source, **body)
    assert response.status_code == 200, response.text[:800]
    return response.json()


async def _all_rows(client: AsyncClient, project: Pick, source: str, **body) -> tuple[dict, list[dict]]:
    rows: list[dict] = []
    offset = 0
    while True:
        data = await _ok(client, project, source, limit=2000, offset=offset, **body)
        rows.extend(data["rows"])
        offset += 2000
        if offset >= data["total"]:
            return data, rows


def _money(value) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("0")


# ─── R1：四表只读生效数据集 ───────────────────────────────────────────────────


async def test_account_balance_matches_active_dataset_gold(client, gold, picks) -> None:
    project = await picks.resolve("balance_with_narrowing_active_dataset")
    count, closing = (await gold.rows(
        f"SELECT count(*), coalesce(sum(closing_balance), 0) FROM tb_balance t WHERE {active_sql('t')}",
        pid=project.id, year=project.audit_year))[0]
    undeleted = await gold.scalar(
        "SELECT count(*) FROM tb_balance WHERE project_id = :pid AND year = :year AND NOT is_deleted",
        pid=project.id, year=project.audit_year)
    assert 0 < count < undeleted, f"{project}：有非生效数据集的行，口径须比只按未删更窄，用例才证明得了口径"
    data, rows = await _all_rows(client, project, "account_balance")
    assert data["total"] == len(rows) == count
    assert abs(sum(_money(r["closing_balance"]) for r in rows) - closing) < Decimal("0.01")
    assert sr.NO_ACTIVE_DATASET_WARNING not in data["warnings"]
    assert data["meta"]["ref_context"] == {"template_type": project.standard_family, "year": project.audit_year}


async def test_without_active_dataset_returns_undeleted_rows_with_warning(
    client, pg_rollback_session, no_active_dataset_project
) -> None:
    # 自建行只在本事务里可见：金标准用同一会话读（换连接读到的是 0，会以「两边都空」假绿）
    project = no_active_dataset_project
    active = (await pg_rollback_session.execute(sa.text(
        "SELECT count(*) FROM ledger_datasets WHERE project_id = :pid AND year = :year AND status = 'active'"),
        {"pid": project.id, "year": project.audit_year})).scalar_one()
    undeleted = (await pg_rollback_session.execute(sa.text(
        "SELECT count(*) FROM tb_balance WHERE project_id = :pid AND year = :year AND NOT is_deleted"),
        {"pid": project.id, "year": project.audit_year})).scalar_one()
    assert active == 0 and undeleted > 0, "前置：自建项目没有 active 数据集但有未删行"
    data = await _ok(client, project, "account_balance")
    assert data["total"] == undeleted and sr.NO_ACTIVE_DATASET_WARNING in data["warnings"]


async def test_dataset_lookup_failure_is_500_not_unfiltered(client, picks, monkeypatch) -> None:
    project = await picks.resolve("balance_with_narrowing_active_dataset")
    real = DatasetService.get_active_dataset_id
    calls = {"n": 0}

    async def _boom(*args, **kwargs):
        # 只让本请求的第一次查询失败（取数口径谓词那一次）；之后的查询（无数据集提示）照常走真实实现——
        # 否则提示那一路也抛，无论口径谓词是否 fail-open 都是 500，用例分不出 strict 与否
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("ledger_datasets 查询失败（注入）")
        return await real(*args, **kwargs)

    # 注在平台入口 get_active_filter 的下一层；被测的口径函数本身不替换
    assert sr._four_table_where.__globals__["get_active_filter"] is dataset_query.get_active_filter
    monkeypatch.setattr(DatasetService, "get_active_dataset_id", staticmethod(_boom))
    response = await _execute(client, project, "account_balance")
    assert response.status_code == 500, response.text[:500]
    assert calls["n"] == 1, "口径谓词查询失败后不得继续取数"
    detail = response.json()["detail"]
    # 追踪号在响应体里（生产全局 HTTPException 处理器只回 {code, message}、不带异常头，响应头那份到不了客户端）
    assert detail["error_code"] == "INTERNAL_ERROR" and len(detail["correlation_id"]) == 32


# ─── R2：计数、排序、分页在数据库内 ───────────────────────────────────────────


async def test_ledger_total_is_full_count(client, gold, picks) -> None:
    project = await picks.resolve("ledger_over_fetch_cap")
    total = await gold.scalar(f"SELECT count(*) {_ACTIVE_LEDGER}", pid=project.id, year=project.audit_year)
    assert total > FETCH_HARD_CAP, f"{project}：序时账超过 5,000 行，用例才证明得了 total 不受取数上限影响"
    data = await _ok(client, project, "ledger_entries")
    assert data["total"] == total and len(data["rows"]) == 100


async def test_ledger_debit_desc_first_rows(client, gold, picks) -> None:
    project = await picks.resolve("ledger_over_fetch_cap")
    expected = await gold.rows(
        f"SELECT voucher_date, voucher_no, account_code, debit_amount {_ACTIVE_LEDGER} "
        "ORDER BY debit_amount DESC NULLS LAST, id LIMIT 2", pid=project.id, year=project.audit_year)
    data = await _ok(client, project, "ledger_entries", limit=2,
                     sort=[{"field": "debit_amount", "direction": "desc"}])
    got = [(r["voucher_date"], r["voucher_no"], r["account_code"], _money(r["debit_amount"])) for r in data["rows"]]
    assert got == [(d.isoformat(), no, code, _money(debit)) for d, no, code, debit in expected], "借方降序首行 = 全量最大借方"


async def test_ledger_pages_are_disjoint_and_match_gold_order(client, gold, picks) -> None:
    project = await picks.resolve("ledger_over_max_offset")
    head = [str(r[0]) for r in await gold.rows(
        f"SELECT id {_ACTIVE_LEDGER} {_LEDGER_DEFAULT_ORDER} LIMIT 200", pid=project.id, year=project.audit_year)]
    first = await _ok(client, project, "ledger_entries", limit=100, offset=0)
    second = await _ok(client, project, "ledger_entries", limit=100, offset=100)
    ids1, ids2 = [r["id"] for r in first["rows"]], [r["id"] for r in second["rows"]]
    assert ids1 == head[:100] and ids2 == head[100:200] and not set(ids1) & set(ids2)
    deep = [str(r[0]) for r in await gold.rows(
        f"SELECT id {_ACTIVE_LEDGER} {_LEDGER_DEFAULT_ORDER} LIMIT 50 OFFSET :off",
        pid=project.id, year=project.audit_year, off=MAX_SQL_OFFSET)]
    assert len(deep) == 50, f"{project}：offset 100,000 处应还能取满一页（能力判据保证 > 100,050 行）"
    edge = await _ok(client, project, "ledger_entries", limit=50, offset=MAX_SQL_OFFSET)
    assert [r["id"] for r in edge["rows"]] == deep, "offset = 100,000 仍可达，且与独立 SQL 分页逐行一致"
    too_deep = await _execute(client, project, "ledger_entries", limit=50, offset=MAX_SQL_OFFSET + 1)
    assert too_deep.status_code == 422 and too_deep.json()["detail"]["error_code"] == "OFFSET_TOO_DEEP"


async def test_offset_at_total_is_empty_page_with_same_total(client, picks) -> None:
    project = await picks.resolve("balance_with_narrowing_active_dataset")
    total = (await _ok(client, project, "account_balance"))["total"]
    assert total > 0, project
    beyond = await _ok(client, project, "account_balance", offset=total)
    assert beyond["rows"] == [] and beyond["total"] == total


async def test_debit_condition_counts_in_database(client, gold, picks) -> None:
    project = await picks.resolve("ledger_debit_over_1e8_within_page")
    expected = await gold.scalar(f"SELECT count(*) {_ACTIVE_LEDGER} AND debit_amount > 100000000",
                                 pid=project.id, year=project.audit_year)
    assert expected >= 1, project
    data = await _ok(client, project, "ledger_entries", limit=2000,
                     conditions=[{"field": "debit_amount", "op": "gt", "value": 100000000}])
    assert data["total"] == expected == len(data["rows"])
    assert all(_money(r["debit_amount"]) > 100000000 for r in data["rows"])


async def test_grouping_over_cap_is_rejected_not_truncated(client, gold, picks) -> None:
    project = await picks.resolve("ledger_1002_over_fetch_cap")
    rows_1002 = await gold.scalar(f"SELECT count(*) {_ACTIVE_LEDGER} AND account_code LIKE '1002%'",
                                  pid=project.id, year=project.audit_year)
    assert rows_1002 > FETCH_HARD_CAP, project
    response = await _execute(client, project, "ledger_entries", filters={"account_code": "1002"}, group={
        "dimensions": ["account_code"], "aggregates": [{"field": "debit_amount", "op": "sum", "alias": "dr"}]})
    assert response.status_code == 400, response.text[:500]
    detail = response.json()["detail"]
    assert detail["error_code"] == "AGGREGATION_TOO_LARGE" and detail["row_count"] == rows_1002


async def test_grouping_within_cap_uses_full_rows(client, gold, picks) -> None:
    project = await picks.resolve("balance_with_narrowing_active_dataset")
    expected = {code: _money(total) for code, total in await gold.rows(
        f"SELECT currency_code, coalesce(sum(closing_balance), 0) FROM tb_balance t WHERE {active_sql('t')} "
        "GROUP BY currency_code", pid=project.id, year=project.audit_year)}
    assert expected, project
    data = await _ok(client, project, "account_balance", limit=2000, group={
        "dimensions": ["currency_code"], "aggregates": [{"field": "closing_balance", "op": "sum", "alias": "s"}]})
    got = {row["currency_code"]: _money(row["s"]) for row in data["rows"]}
    assert got.keys() == expected.keys() and all(abs(got[k] - expected[k]) < Decimal("0.01") for k in got)


async def test_trial_balance_default_order_and_audited_sum(client, gold, picks) -> None:
    project = await picks.resolve("tb_detail")
    count, audited, min_code = (await gold.rows(
        "SELECT count(*), coalesce(sum(audited_amount), 0), min(standard_account_code) FROM trial_balance "
        "WHERE project_id = :pid AND year = :year AND NOT is_deleted", pid=project.id, year=project.audit_year))[0]
    data, rows = await _all_rows(client, project, "tb_detail")
    codes = [r["standard_account_code"] for r in rows]
    assert data["total"] == count == len(rows) and codes[0] == min_code and codes == sorted(codes)
    assert abs(sum(_money(r["audited_amount"]) for r in rows) - audited) < Decimal("0.01")


async def test_workpaper_list_matches_gold(client, gold, picks) -> None:
    """底稿清单默认按 wp_code 升序（数据库内排序，按库的排序规则）、id 兜底。

    🔴 金标准必须是 SQL 的 ``ORDER BY wp_code``，不能是 Python 的 ``sorted()``：共享库排序规则是 ``en_US.utf8``，
    比较时忽略连字符（``A10`` 排在 ``A1-11`` 前），而 ``sorted()`` 按码点（``-`` < ``0``，``A1-11`` 在前）。原用例拿
    ``sorted()`` 作判据，是因为旧夹具项目的底稿编码恰好没有这种组合；换到有 1,000 多张底稿的项目即现形。
    """
    project = await picks.resolve("workpapers")
    expected = [r[0] for r in await gold.rows(
        "SELECT i.wp_code FROM working_paper w JOIN wp_index i ON i.id = w.wp_index_id "
        "WHERE w.project_id = :pid AND NOT w.is_deleted ORDER BY i.wp_code, w.id", pid=project.id)]
    data = await _ok(client, project, "workpaper", limit=2000)
    codes = [r["wp_code"] for r in data["rows"]]
    assert data["total"] == len(expected) == len(codes) > 0, project
    assert codes == expected, "默认排序 = 数据库按 wp_code 升序（库排序规则）"


async def test_consol_unit_prefix_scopes_company(client, gold, picks) -> None:
    project = await picks.resolve("ledger_over_fetch_cap")
    company, expected = (await gold.rows(
        f"SELECT company_code, count(*) {_ACTIVE_LEDGER} GROUP BY company_code ORDER BY 2 DESC, 1 LIMIT 1",
        pid=project.id, year=project.audit_year))[0]
    data = await _ok(client, project, f"consol_unit:{company}:ledger_entries")
    assert data["total"] == expected


# ─── R6：条件、字段选择、未登记输入 ────────────────────────────────────────────


async def test_unregistered_filter_key_is_400_and_columns_project(client, picks) -> None:
    project = await picks.resolve("ledger_over_fetch_cap")
    unknown = await _execute(client, project, "ledger_entries", filters={"debit_amount_min": 100000000})
    assert unknown.status_code == 400 and unknown.json()["detail"]["error_code"] == "UNKNOWN_FILTER_KEY"
    data = await _ok(client, project, "ledger_entries", limit=5, columns=["account_name"])
    assert data["columns"] == ["account_name"] and "summary" not in data["rows"][0] and "id" in data["rows"][0]
    bad_column = await _execute(client, project, "ledger_entries", columns=["closing_balance"])
    assert bad_column.status_code == 400 and bad_column.json()["detail"]["error_code"] == "UNKNOWN_COLUMN"


async def test_json_sources_reject_conditions(client, picks) -> None:
    project = await picks.resolve("tb_detail")
    response = await _execute(client, project, "disclosure", conditions=[{"field": "x", "op": "eq", "value": 1}])
    assert response.status_code == 400 and response.json()["detail"]["error_code"] == "CONDITIONS_UNSUPPORTED"


@pytest.mark.parametrize("source", ["report:balance_sheet|A1:C5", "note:五-1-1|C3:D8", "adj:aje|B2:E10",
                                    "tb:detail|C1:C50"])
async def test_module_cell_source_keys_are_400_unknown_source(client, picks, source: str) -> None:
    """跨模块单元格源族已删除（任务 34，AQ-25）：这类源键按未知数据源 400，不再 200 返回虚拟单元格。"""
    project = await picks.resolve("tb_detail")
    response = await _execute(client, project, source)
    assert response.status_code == 400, response.text[:500]
    detail = response.json()["detail"]
    assert detail["error_code"] == "UNKNOWN_SOURCE" and detail["source"] == source and detail["message"], detail
