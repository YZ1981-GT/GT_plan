"""任务 40 新条件能力真 PG 金标准（真实项目只读；三条空摘要只在回滚事务中可见）。

项目 ID 不写死：共享库项目曾整体重建，固定 UUID 会让 admin 对不存在项目的请求在
OwnershipGuard 处 403，或在旧门禁下对空集假绿。每例按未删除项目的唯一名称现取 ID；
请求经 ``business`` 的生产 router/TestClient 路径，金标准使用独立只读 SQL。
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
import uuid

import pytest
import sqlalchemy as sa

import app.core.redis as core_redis
from app.models.audit_platform_models import TbLedger
from app.services.custom_query.param_sql_builder import BLANK_CHARS
from tests.advanced_query_linkage.gold import AUDIT_YEAR, active_sql

pytestmark = pytest.mark.pg_only
_ACTIVE = f"FROM tb_ledger t WHERE {active_sql('t')}"
_HP_NAME = "重庆和平药房连锁有限责任公司_2025"
_HS_NAME = "陕西华氏医药有限公司_2025"


async def _project_id(gold, name: str) -> uuid.UUID:
    rows = await gold.rows(
        "SELECT id FROM projects WHERE name = :name AND NOT is_deleted ORDER BY id",
        name=name,
    )
    assert len(rows) == 1, f"前置：未删除项目「{name}」应恰好一条，实得 {len(rows)} 条"
    return rows[0][0]


async def test_hp_weekend_and_account_prefix_match_independent_sql(business, gold) -> None:
    hp = await _project_id(gold, _HP_NAME)
    weekend = await gold.scalar(
        f"SELECT count(*) {_ACTIVE} AND EXTRACT(DOW FROM voucher_date) IN (0, 6)",
        pid=hp,
        year=AUDIT_YEAR,
    )
    weekend_data = await business.ok(
        hp,
        "ledger_entries",
        conditions=[{"field": "voucher_date", "op": "weekday_in", "value": [0, 6]}],
    )
    assert weekend_data["total"] == weekend

    prefix = await gold.scalar(
        f"SELECT count(*) {_ACTIVE} AND account_code LIKE '1002%'",
        pid=hp,
        year=AUDIT_YEAR,
    )
    prefix_data = await business.ok(
        hp,
        "ledger_entries",
        conditions=[{"field": "account_code", "op": "starts_with", "value": "1002"}],
    )
    assert prefix_data["total"] == prefix


async def test_hs_string_line_amount_threshold_matches_independent_sql(business, gold) -> None:
    hs = await _project_id(gold, _HS_NAME)
    expected = await gold.scalar(
        f"SELECT count(*) {_ACTIVE} "
        "AND GREATEST(COALESCE(debit_amount, 0), COALESCE(credit_amount, 0)) >= 1000000",
        pid=hs,
        year=AUDIT_YEAR,
    )
    data = await business.ok(
        hs,
        "ledger_entries",
        conditions=[{"field": "line_amount", "op": "gte", "value": "1000000"}],
    )
    assert data["total"] == expected
    assert "line_amount" not in data["columns"]
    assert all("line_amount" not in row for row in data["rows"])

    detail = await business.error(
        hs,
        "ledger_entries",
        400,
        conditions=[{"field": "line_amount", "op": "gte", "value": ""}],
    )
    assert detail["error_code"] == "CONDITION_VALUE_REQUIRED"


async def _active_dataset_id(session, project_id: uuid.UUID) -> uuid.UUID | None:
    result = await session.execute(
        sa.text(
            "SELECT id FROM ledger_datasets "
            "WHERE project_id = :pid AND year = :year AND status = 'active' "
            "ORDER BY activated_at DESC NULLS LAST, created_at DESC LIMIT 1"
        ),
        {"pid": project_id, "year": AUDIT_YEAR},
    )
    return result.scalar_one_or_none()


async def test_blank_summary_matches_gold_and_three_rollback_rows(business, gold) -> None:
    hp = await _project_id(gold, _HP_NAME)
    hp_expected = await gold.scalar(
        f"SELECT count(*) {_ACTIVE} AND (summary IS NULL OR btrim(summary, :blank_chars) = '')",
        pid=hp,
        year=AUDIT_YEAR,
        blank_chars=BLANK_CHARS,
    )
    hp_data = await business.ok(
        hp,
        "ledger_entries",
        conditions=[{"field": "summary", "op": "is_blank", "value": None}],
    )
    assert hp_data["total"] == hp_expected

    dataset_id = await _active_dataset_id(business.session, hp)
    for index, summary in enumerate((None, "", "   ")):
        business.session.add(
            TbLedger(
                id=uuid.uuid4(),
                project_id=hp,
                year=AUDIT_YEAR,
                company_code="AQL_TASK40_ROLLBACK",
                voucher_date=dt.date(AUDIT_YEAR, 12, 20 + index),
                voucher_no=f"AQL-T40-BLANK-{index}",
                account_code="1002",
                account_name="银行存款",
                debit_amount=Decimal("1.00"),
                credit_amount=Decimal("0.00"),
                summary=summary,
                dataset_id=dataset_id,
            )
        )
    await business.session.flush()
    await core_redis.redis_client.flushdb()  # 同请求身份已有首轮结果；写后必须使本例隔离缓存失效

    after = await business.ok(
        hp,
        "ledger_entries",
        conditions=[{"field": "summary", "op": "is_blank", "value": None}],
    )
    assert after["total"] == hp_expected + 3
