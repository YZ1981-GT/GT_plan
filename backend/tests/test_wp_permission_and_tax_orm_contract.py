"""真实 ORM 字段契约回归测试。

覆盖：
- WpPermissionService 必须经 StaffMember.user_id 关联项目委派；
- N2/N3 旧 service 必须读取 TbBalance 的真实列，并保持旧 payload 键；
- TbBalance 查询失败不能被吞成 found=False 或全零结果。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.services import dataset_query
from app.services import n2_taxes_payable_service as n2
from app.services import n3_deferred_tax_liabilities_service as n3
from app.services.wp_permission_service import WpPermissionService


class _Result:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


def _sql(statement) -> str:  # noqa: ANN001
    return str(statement.compile(compile_kwargs={"literal_binds": False}))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "kwargs", "expected_calls"),
    [
        ("check_project_access", {}, 1),
        ("check_cycle_access", {"cycle": "D"}, 2),
        ("check_workpaper_access", {"wp_id": uuid4()}, 2),
    ],
)
async def test_wp_permission_uses_staff_user_join(method_name, kwargs, expected_calls):
    """三层权限查询都必须沿 staff_id → StaffMember.user_id 解析用户。"""
    db = AsyncMock()
    execution_result = MagicMock()
    execution_result.scalars.return_value.all.return_value = [SimpleNamespace(role="auditor")]
    db.execute = AsyncMock(return_value=execution_result)
    service = WpPermissionService(db)
    common = {"user_id": uuid4(), "project_id": uuid4(), **kwargs}

    assert await getattr(service, method_name)(**common) is True
    assert db.execute.await_count == expected_calls

    for call in db.execute.await_args_list:
        statement = call.args[0]
        sql = _sql(statement).lower()
        assert "join staff_members" in sql
        assert "staff_members.user_id" in sql
        assert "staff_members.is_deleted" in sql
        assert "project_assignments.user_id" not in sql


@pytest.fixture
def active_tb_filter(monkeypatch):
    calls = []

    async def _fake(db, table, project_id, year, **kwargs):  # noqa: ANN001
        calls.append((db, table, project_id, year, kwargs))
        return sa.true()

    monkeypatch.setattr(dataset_query, "get_active_filter", _fake)
    return calls


@pytest.mark.asyncio
async def test_n2_tb_service_uses_real_columns_and_legacy_payload(active_tb_filter):
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=_Result(
            SimpleNamespace(
                begin_balance="10.25",
                debit_amount="2.00",
                credit_amount="5.50",
                end_balance="13.75",
            )
        )
    )

    result = await n2.get_tb_data("project-1", db, year=2025)

    assert result == {
        "account_code": "2221",
        "account_name": "应交税费",
        "direction": "credit",
        "begin_balance": 10.25,
        "debit_amount": 2.0,
        "credit_amount": 5.5,
        "end_balance": 13.75,
        "found": True,
    }
    statement_sql = _sql(db.execute.await_args.args[0]).lower()
    assert "tb_balance.opening_balance" in statement_sql
    assert "tb_balance.closing_balance" in statement_sql
    assert "tb_balance.account_code" in statement_sql
    assert "tb_balance.begin_balance" not in statement_sql
    assert "tb_balance.end_balance" not in statement_sql
    assert "tb_balance.standard_account_code" not in statement_sql
    assert active_tb_filter[0][3] == 2025
    assert active_tb_filter[0][4] == {"strict": True}


@pytest.mark.asyncio
async def test_n3_tb_service_uses_real_columns_and_legacy_payload(active_tb_filter):
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=_Result(
            SimpleNamespace(
                begin_balance="20.00",
                debit_amount="3.00",
                credit_amount="7.00",
                end_balance="24.00",
            )
        )
    )

    result = await n3.get_tb_data("project-1", db, year=2025)

    assert result["account_code"] == "2901"
    assert result["begin_balance"] == 20.0
    assert result["end_balance"] == 24.0
    assert result["found"] is True
    statement_sql = _sql(db.execute.await_args.args[0]).lower()
    assert "tb_balance.opening_balance" in statement_sql
    assert "tb_balance.closing_balance" in statement_sql
    assert "tb_balance.account_code" in statement_sql
    assert "tb_balance.begin_balance" not in statement_sql
    assert "tb_balance.end_balance" not in statement_sql
    assert "tb_balance.standard_account_code" not in statement_sql


@pytest.mark.asyncio
async def test_n3_cross_total_uses_real_columns_and_legacy_payload(active_tb_filter):
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _Result(SimpleNamespace(begin_balance=20.0, end_balance=25.0)),
            _Result(SimpleNamespace(begin_balance=10.0, end_balance=8.0)),
        ]
    )

    result = await n3.get_cross_wp_total("project-1", db, year=2025)

    assert result["n3_liability"] == {
        "begin_balance": 20.0,
        "end_balance": 25.0,
        "period_change": 5.0,
    }
    assert result["n1_asset"] == {
        "begin_balance": 10.0,
        "end_balance": 8.0,
        "period_change": -2.0,
    }
    assert result["deferred_tax_expense"] == 7.0
    assert all(
        "tb_balance.opening_balance" in _sql(call.args[0]).lower()
        and "tb_balance.closing_balance" in _sql(call.args[0]).lower()
        and "tb_balance.account_code" in _sql(call.args[0]).lower()
        for call in db.execute.await_args_list
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reader",
    [n2.get_tb_data, n3.get_tb_data],
)
async def test_tb_reader_error_is_not_reported_as_not_found(reader, active_tb_filter):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("tb unavailable"))

    with pytest.raises(RuntimeError, match="tb unavailable"):
        await reader("project-1", db, year=2025)


@pytest.mark.asyncio
async def test_n2_cross_summary_error_is_not_reported_as_all_zero():
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("cross source unavailable"))

    with pytest.raises(RuntimeError, match="cross source unavailable"):
        await n2.get_cross_wp_summary("project-1", db)


@pytest.mark.asyncio
async def test_n3_cross_total_error_is_not_reported_as_all_zero(active_tb_filter):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("tb unavailable"))

    with pytest.raises(RuntimeError, match="tb unavailable"):
        await n3.get_cross_wp_total("project-1", db, year=2025)


@pytest.mark.asyncio
async def test_wp_permission_rejects_duplicate_active_assignments():
    db = AsyncMock()
    execution_result = MagicMock()
    execution_result.scalars.return_value.all.return_value = [
        SimpleNamespace(role="auditor"),
        SimpleNamespace(role="manager"),
    ]
    db.execute = AsyncMock(return_value=execution_result)

    allowed = await WpPermissionService(db).check_project_access(
        user_id=uuid4(), project_id=uuid4()
    )

    assert allowed is False
