"""Sprint A.2.3 — aux_balance 行 explode 单测.

覆盖：
  1. 单 aux_code 命中 → 1 行
  2. 多 aux_code → 多行 + 排序（按 |closing_balance| 降序）
  3. 同 aux_code 多月份 → 求和合并
  4. aux_type 过滤
  5. exclude_zero=True 过滤全 0 行
  6. exclude_zero=False 保留 0 行
  7. top_n 截断
  8. 缺 db / project_id / year / account_codes → []
  9. db.execute 抛异常 → []（不抛给外层）
 10. 自定义 field_map（含 debit_amount / credit_amount）
 11. aux_name 缺失时用 aux_code 当 label
 12. aux_code 缺失的行被忽略（无法 explode 成行）
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.note_aux_balance_explode import explode_aux_balance


def _make_db_with_rows(rows: list) -> MagicMock:
    """模拟 db.execute() → result.scalars().all() = rows."""
    db = MagicMock()
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=rows)
    result.scalars = MagicMock(return_value=scalars_mock)
    db.execute = AsyncMock(return_value=result)
    return db


def _make_db_raising() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(side_effect=RuntimeError("fake db error"))
    return db


def _ctx(db=None, project_id=None, year=2025) -> dict:
    return {
        "db": db,
        "project_id": project_id or uuid4(),
        "year": year,
    }


def _aux_row(
    *,
    aux_code: str = "C001",
    aux_name: str = "客户A",
    aux_type: str = "customer",
    closing: Decimal | float | None = Decimal("100"),
    opening: Decimal | float | None = Decimal("80"),
    debit: Decimal | float | None = None,
    credit: Decimal | float | None = None,
):
    return SimpleNamespace(
        aux_code=aux_code,
        aux_name=aux_name,
        aux_type=aux_type,
        closing_balance=Decimal(str(closing)) if closing is not None else None,
        opening_balance=Decimal(str(opening)) if opening is not None else None,
        debit_amount=Decimal(str(debit)) if debit is not None else None,
        credit_amount=Decimal(str(credit)) if credit is not None else None,
    )


# ---------------------------------------------------------------------------
# 1) 基本命中
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_aux_code_returns_one_row() -> None:
    rows = [_aux_row(aux_code="C001", aux_name="客户A", closing=500, opening=400)]
    ctx = _ctx(db=_make_db_with_rows(rows))
    binding = {"account_codes": ["1122"]}

    result = await explode_aux_balance(binding, ctx)

    assert len(result) == 1
    assert result[0]["label"] == "客户A"
    assert result[0]["aux_code"] == "C001"
    assert result[0]["values"]["col_amount_end"] == Decimal("500")
    assert result[0]["values"]["col_amount_start"] == Decimal("400")


# ---------------------------------------------------------------------------
# 2) 多行排序
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_aux_codes_sorted_by_abs_closing_desc() -> None:
    rows = [
        _aux_row(aux_code="A", aux_name="客户A", closing=100),
        _aux_row(aux_code="B", aux_name="客户B", closing=300),
        _aux_row(aux_code="C", aux_name="客户C", closing=-500),  # |500| 最大
        _aux_row(aux_code="D", aux_name="客户D", closing=200),
    ]
    ctx = _ctx(db=_make_db_with_rows(rows))
    binding = {"account_codes": ["1122"]}

    result = await explode_aux_balance(binding, ctx)

    assert [r["aux_code"] for r in result] == ["C", "B", "D", "A"]


# ---------------------------------------------------------------------------
# 3) 同 aux_code 多行求和
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_aux_code_multiple_rows_summed() -> None:
    rows = [
        _aux_row(aux_code="C001", aux_name="客户A", closing=100, opening=80),
        _aux_row(aux_code="C001", aux_name="客户A", closing=200, opening=20),
    ]
    ctx = _ctx(db=_make_db_with_rows(rows))
    binding = {"account_codes": ["1122"]}

    result = await explode_aux_balance(binding, ctx)

    assert len(result) == 1
    assert result[0]["values"]["col_amount_end"] == Decimal("300")
    assert result[0]["values"]["col_amount_start"] == Decimal("100")


# ---------------------------------------------------------------------------
# 4) aux_type 过滤（在 SQL 层验证 — mock 不真过滤，但 binding 中含 aux_type 不报错）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aux_type_filter_passes_to_query() -> None:
    rows = [_aux_row(aux_code="C001", aux_name="客户A", closing=100, aux_type="customer")]
    ctx = _ctx(db=_make_db_with_rows(rows))
    binding = {"account_codes": ["1122"], "aux_type": "customer"}

    result = await explode_aux_balance(binding, ctx)

    assert len(result) == 1


# ---------------------------------------------------------------------------
# 5/6) exclude_zero
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exclude_zero_default_true_skips_all_zero_rows() -> None:
    rows = [
        _aux_row(aux_code="A", closing=0, opening=0),
        _aux_row(aux_code="B", closing=100, opening=80),
    ]
    ctx = _ctx(db=_make_db_with_rows(rows))
    binding = {"account_codes": ["1122"]}

    result = await explode_aux_balance(binding, ctx)

    assert len(result) == 1
    assert result[0]["aux_code"] == "B"


@pytest.mark.asyncio
async def test_exclude_zero_false_keeps_zero_rows() -> None:
    rows = [
        _aux_row(aux_code="A", closing=0, opening=0),
        _aux_row(aux_code="B", closing=100, opening=80),
    ]
    ctx = _ctx(db=_make_db_with_rows(rows))
    binding = {"account_codes": ["1122"], "exclude_zero": False}

    result = await explode_aux_balance(binding, ctx)

    assert len(result) == 2


@pytest.mark.asyncio
async def test_zero_closing_with_nonzero_opening_kept_when_exclude_zero_true() -> None:
    """closing=0 但 opening 非 0 时，仍视为有效辅助账（如本期清账户）."""
    rows = [_aux_row(aux_code="A", aux_name="X", closing=0, opening=80)]
    ctx = _ctx(db=_make_db_with_rows(rows))
    binding = {"account_codes": ["1122"]}

    result = await explode_aux_balance(binding, ctx)

    assert len(result) == 1


# ---------------------------------------------------------------------------
# 7) top_n
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_top_n_truncates_after_sort() -> None:
    rows = [
        _aux_row(aux_code=str(i), aux_name=f"X{i}", closing=Decimal(str(100 - i)))
        for i in range(10)
    ]
    ctx = _ctx(db=_make_db_with_rows(rows))
    binding = {"account_codes": ["1122"], "top_n": 3}

    result = await explode_aux_balance(binding, ctx)

    assert len(result) == 3
    # 排序后前 3 是 closing 最大的（100, 99, 98 → aux_code 0/1/2）
    assert [r["aux_code"] for r in result] == ["0", "1", "2"]


# ---------------------------------------------------------------------------
# 8) 边界：空 / None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_db_returns_empty() -> None:
    result = await explode_aux_balance(
        {"account_codes": ["1122"]}, _ctx(db=None)
    )
    assert result == []


@pytest.mark.asyncio
async def test_missing_project_id_returns_empty() -> None:
    ctx = {"db": _make_db_with_rows([]), "project_id": None, "year": 2025}
    assert await explode_aux_balance({"account_codes": ["1122"]}, ctx) == []


@pytest.mark.asyncio
async def test_missing_account_codes_returns_empty() -> None:
    ctx = _ctx(db=_make_db_with_rows([]))
    assert await explode_aux_balance({}, ctx) == []
    assert await explode_aux_balance({"account_codes": []}, ctx) == []
    assert await explode_aux_balance({"account_codes": [None, ""]}, ctx) == []


# ---------------------------------------------------------------------------
# 9) db 抛异常
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_exception_returns_empty() -> None:
    ctx = _ctx(db=_make_db_raising())
    result = await explode_aux_balance({"account_codes": ["1122"]}, ctx)
    assert result == []


# ---------------------------------------------------------------------------
# 10) 自定义 field_map
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_custom_field_map_with_debit_credit() -> None:
    rows = [
        _aux_row(aux_code="A", aux_name="客户A", closing=100, debit=300, credit=200)
    ]
    ctx = _ctx(db=_make_db_with_rows(rows))
    binding = {
        "account_codes": ["1122"],
        "field_map": {
            "col_debit": "debit_amount",
            "col_credit": "credit_amount",
        },
        "exclude_zero": False,
    }

    result = await explode_aux_balance(binding, ctx)

    assert len(result) == 1
    assert result[0]["values"]["col_debit"] == Decimal("300")
    assert result[0]["values"]["col_credit"] == Decimal("200")


# ---------------------------------------------------------------------------
# 11) aux_name 缺失 → 用 aux_code 当 label
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_aux_name_falls_back_to_aux_code() -> None:
    rows = [_aux_row(aux_code="C001", aux_name=None, closing=100)]  # type: ignore[arg-type]
    ctx = _ctx(db=_make_db_with_rows(rows))

    result = await explode_aux_balance({"account_codes": ["1122"]}, ctx)

    assert result[0]["label"] == "C001"
    assert result[0]["aux_code"] == "C001"


# ---------------------------------------------------------------------------
# 12) aux_code 缺失的行被忽略
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rows_without_aux_code_skipped() -> None:
    rows = [
        _aux_row(aux_code="", aux_name="无码", closing=100),  # type: ignore[arg-type]
        _aux_row(aux_code="C001", aux_name="客户A", closing=200),
    ]
    ctx = _ctx(db=_make_db_with_rows(rows))

    result = await explode_aux_balance({"account_codes": ["1122"]}, ctx)

    assert len(result) == 1
    assert result[0]["aux_code"] == "C001"


# ---------------------------------------------------------------------------
# 13) tie-breaker 字典序
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_amount_sorted_by_aux_code_asc() -> None:
    """同 |closing| 时按 aux_code 字典序升序排列（确定性）."""
    rows = [
        _aux_row(aux_code="Z", aux_name="zz", closing=100),
        _aux_row(aux_code="A", aux_name="aa", closing=100),
        _aux_row(aux_code="M", aux_name="mm", closing=100),
    ]
    ctx = _ctx(db=_make_db_with_rows(rows))

    result = await explode_aux_balance({"account_codes": ["1122"]}, ctx)

    assert [r["aux_code"] for r in result] == ["A", "M", "Z"]
