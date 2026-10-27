"""辅助核算源与构建器白名单扩充真 PG 回归（advanced-query-linkage-closure 任务 21；R5.6、R1；design §3.1、§3.4；
变异 B5-f、B5-l、B5-n；B5-b 在 ``test_aql_source_registry.py``）。

改造前（AQ-12）：业务视图没有辅助余额 / 辅助明细两个源；构建器查 ``tb_aux_balance`` 400 ``TABLE_NOT_ALLOWED``。

现在：
- 业务视图 ``aux_balance`` / ``aux_ledger``：四表口径同 R1（只经 ``get_active_filter``）；辅助明细至少按科目或辅助类型之一
  收窄（旧筛选键，或该字段的 eq / in / between 条件），都没有 ⇒ 400 ``AUX_FILTER_REQUIRED``；辅助余额未收窄到一个辅助
  类型 ⇒ warnings「辅助核算按维度冗余存储，跨维度合计会重复」。
- 构建器白名单增 ``tb_aux_balance`` / ``tb_aux_ledger`` / ``financial_report``：作用域谓词同其余四表（项目、未删、生效数据集）。

和平药房只读；现库没有一个活项目的辅助表含非生效数据集的行，数据集口径在回滚事务里给【UAT】子公司A 造数据集与行验证。
"""
from __future__ import annotations

import datetime as dt
import time
import uuid
from decimal import Decimal

import pytest

from app.models.audit_platform_models import TbAuxBalance, TbAuxLedger
from app.models.dataset_models import DatasetStatus, LedgerDataset
from tests.advanced_query_linkage.gold import AUDIT_YEAR, HP, HS, UA, active_sql

pytestmark = pytest.mark.pg_only
CROSS_DIMENSION = "辅助核算按维度冗余存储，跨维度合计会重复"
_BAL = f"FROM tb_aux_balance t WHERE {active_sql('t')}"
_LED = f"FROM tb_aux_ledger t WHERE {active_sql('t')}"
_LEDGER_ORDER = "ORDER BY voucher_date DESC NULLS LAST, voucher_no ASC NULLS LAST, id ASC"


def _money(value) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("0")


async def test_hp_bank_account_aux_balance_matches_gold(business, gold) -> None:
    count, closing = (await gold.rows(
        f"SELECT count(*), coalesce(sum(closing_balance), 0) {_BAL} AND account_code LIKE '1002%' "
        "AND aux_type = '银行账户'", pid=HP, year=AUDIT_YEAR))[0]
    assert count > 0, "前置：和平药房银行存款有按银行账户的辅助余额"
    data, rows = await business.all_rows(HP, "aux_balance", filters={"account_code": "1002", "aux_type": "银行账户"})
    assert data["total"] == len(rows) == count
    assert abs(sum(_money(r["closing_balance"]) for r in rows) - closing) < Decimal("0.01")
    assert CROSS_DIMENSION not in data["warnings"], "已收窄到一个辅助类型，不提示跨维合计"
    assert data["columns"] == ["account_code", "account_name", "aux_type", "aux_code", "aux_name", "opening_direction",
                               "opening_balance", "debit_amount", "credit_amount", "closing_direction",
                               "closing_balance"]


async def test_aux_balance_warns_until_narrowed_to_one_dimension(business, gold) -> None:
    count = await gold.scalar(f"SELECT count(*) {_BAL} AND account_code LIKE '1002%'", pid=HP, year=AUDIT_YEAR)
    data = await business.ok(HP, "aux_balance", filters={"account_code": "1002"})
    assert data["total"] == count and CROSS_DIMENSION in data["warnings"]
    by_condition = await business.ok(HP, "aux_balance", filters={"account_code": "1002"},
                                     conditions=[{"field": "aux_type", "op": "eq", "value": "银行账户"}])
    assert CROSS_DIMENSION not in by_condition["warnings"], "结构化条件 aux_type = 一个值也算收窄"
    two = await business.ok(HP, "aux_balance", filters={"account_code": "1002"},
                            conditions=[{"field": "aux_type", "op": "in", "value": ["银行账户", "金融机构"]}])
    assert CROSS_DIMENSION in two["warnings"], "两个辅助类型仍是跨维合计"


async def test_aux_ledger_requires_account_or_type(business, gold) -> None:
    detail = await business.error(HP, "aux_ledger", 400)
    assert detail["error_code"] == "AUX_FILTER_REQUIRED" and detail["message"] == "辅助明细请先按科目或辅助类型筛选"
    either = await business.error(HP, "aux_ledger", 400, condition_logic="or", conditions=[
        {"field": "account_code", "op": "eq", "value": "1002"}, {"field": "summary", "op": "like", "value": "利息"}])
    assert either["error_code"] == "AUX_FILTER_REQUIRED", "OR 逻辑下一条科目条件不构成收窄"
    total = await gold.scalar(f"SELECT count(*) {_LED} AND account_code LIKE '1002%'", pid=HP, year=AUDIT_YEAR)
    head = [str(r[0]) for r in await gold.rows(
        f"SELECT id {_LED} AND account_code LIKE '1002%' {_LEDGER_ORDER} LIMIT 100", pid=HP, year=AUDIT_YEAR)]
    started = time.perf_counter()
    data = await business.ok(HP, "aux_ledger", filters={"account_code": "1002"})
    elapsed = time.perf_counter() - started
    assert data["total"] == total > 0 and [r["id"] for r in data["rows"]] == head
    print(f"[N1] 和平药房辅助明细 1002 首页（含 COUNT）{elapsed:.2f}s，total={total}")


async def test_aux_ledger_type_condition_narrows(business, gold) -> None:
    total = await gold.scalar(f"SELECT count(*) {_LED} AND aux_type = '银行账户'", pid=HP, year=AUDIT_YEAR)
    data = await business.ok(HP, "aux_ledger", limit=10,
                             conditions=[{"field": "aux_type", "op": "eq", "value": "银行账户"}])
    assert data["total"] == total > 0
    assert all(r["aux_type"] == "银行账户" for r in data["rows"])


async def _seed_ua_datasets(session) -> dict[str, uuid.UUID]:
    """回滚事务：【UAT】子公司A 一个生效数据集 + 一个已替代数据集，两张辅助表各造生效 / 已替代 / 已删行。"""
    t0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    active = LedgerDataset(project_id=UA, year=AUDIT_YEAR, status=DatasetStatus.active, activated_at=t0)
    old = LedgerDataset(project_id=UA, year=AUDIT_YEAR, status=DatasetStatus.superseded,
                        activated_at=t0 - dt.timedelta(days=1))
    session.add_all([active, old])
    await session.flush()
    rows = (("AQLB5-ACTIVE", active.id, False), ("AQLB5-ACTIVE-DEL", active.id, True), ("AQLB5-OLD", old.id, False))
    for aux_code, dataset_id, deleted in rows:
        session.add(TbAuxBalance(project_id=UA, year=AUDIT_YEAR, company_code="UAT_SUB_A", account_code="1002",
                                 account_name="银行存款", aux_type="银行账户", aux_code=aux_code, aux_name=aux_code,
                                 closing_balance=Decimal("1.00"), dataset_id=dataset_id, is_deleted=deleted))
        session.add(TbAuxLedger(project_id=UA, year=AUDIT_YEAR, company_code="UAT_SUB_A", account_code="1002",
                                voucher_date=dt.date(AUDIT_YEAR, 3, 1), voucher_no=aux_code, aux_type="银行账户",
                                aux_code=aux_code, aux_name=aux_code, debit_amount=Decimal("1.00"),
                                summary="【UAT】B5 回滚事务造行", dataset_id=dataset_id, is_deleted=deleted))
    await session.flush()
    return {"active": active.id, "old": old.id}


async def test_aux_sources_follow_active_dataset(business) -> None:
    await _seed_ua_datasets(business.session)
    balance = await business.ok(UA, "aux_balance", filters={"aux_type": "银行账户"})
    assert [r["aux_code"] for r in balance["rows"]] == ["AQLB5-ACTIVE"], "只取生效数据集、未删的行"
    ledger = await business.ok(UA, "aux_ledger", filters={"account_code": "1002"})
    assert [r["aux_code"] for r in ledger["rows"]] == ["AQLB5-ACTIVE"]


async def test_builder_aux_tables_follow_the_same_scope(builder, gold) -> None:
    await _seed_ua_datasets(builder.session)
    for table in ("tb_aux_balance", "tb_aux_ledger"):
        data = await builder.ok(builder.admin, {
            "table": table, "project_id": str(UA), "year": AUDIT_YEAR,
            "fields": [f"{table}.aux_code"], "limit": 100})
        assert [r[f"{table}.aux_code"] for r in data["rows"]] == ["AQLB5-ACTIVE"], table
    hp = await gold.scalar(f"SELECT count(*) {_BAL} AND account_code = '1002'", pid=HP, year=AUDIT_YEAR)
    data = await builder.ok(builder.admin, {
        "table": "tb_aux_balance", "project_id": str(HP), "year": AUDIT_YEAR,
        "filters": [{"field": "account_code", "op": "eq", "value": "1002"}],
        "fields": ["tb_aux_balance.aux_type"], "limit": 1000})
    assert data["total"] == hp, "构建器口径 = 业务视图同一口径（生效数据集、未删）"


async def test_builder_financial_report_is_project_scoped(builder, gold) -> None:
    expected = await gold.scalar("SELECT count(*) FROM financial_report WHERE project_id = :pid AND year = :year "
                                 "AND NOT is_deleted", pid=HS, year=AUDIT_YEAR)
    data = await builder.ok(builder.admin, {"table": "financial_report", "project_id": str(HS), "year": AUDIT_YEAR,
                                            "fields": ["financial_report.row_code"], "limit": 1000})
    assert data["total"] == expected > 0
