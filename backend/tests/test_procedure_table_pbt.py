"""程序表适用性自动填充 PBT

Property: 对任意 business_category，A1 第15/16项仅 A/B 类适用（C 类为 na）。
max_examples=5
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.procedure_table_auto_service import get_template, ProcedureTableService

category_st = st.sampled_from(["A1", "A3", "B1", "B4", "C"])


@given(category=category_st)
@settings(max_examples=5, deadline=None)
def test_a1_item18_applicable_by_category(category):
    """Property: A1 第18项(质控复核)仅 A/B 适用"""
    template = get_template("A1")
    assert template is not None
    item18 = next(i for i in template["items"] if i["seq"] == 18)

    # 直接调用 _check_applicable 逻辑
    svc = ProcedureTableService.__new__(ProcedureTableService)
    result = svc._check_applicable(item18, category)

    prefix = category[0].upper()
    if prefix in ("A", "B"):
        assert result == "yes"
    else:
        assert result == "na"


@given(category=category_st)
@settings(max_examples=5, deadline=None)
def test_a1_item19_a_only(category):
    """Property: A1 第19项(专委会)仅 A 类适用"""
    template = get_template("A1")
    assert template is not None
    item19 = next(i for i in template["items"] if i["seq"] == 19)

    svc = ProcedureTableService.__new__(ProcedureTableService)
    result = svc._check_applicable(item19, category)

    prefix = category[0].upper()
    if prefix == "A":
        assert result == "yes"
    else:
        assert result == "na"


def test_all_templates_load():
    """所有程序表模板都能加载"""
    from app.services.procedure_table_auto_service import list_table_codes
    codes = list_table_codes()
    assert len(codes) >= 17
    assert "A1" in codes
    assert "A16" in codes
    assert "A17" in codes


def test_a16_seq3_applicable_default_no():
    """A16 seq3（关联交易声明书）默认 applicable_default='no'，无 applicable_categories"""
    template = get_template("A16")
    assert template is not None
    seq3 = next(i for i in template["items"] if i["seq"] == 3)

    # 验证 JSON 配置
    assert seq3["applicable_default"] == "no"
    assert seq3["auto_data_source"] == "related_party_transaction_count"
    assert seq3["ref_index"] == "A16-7"
    assert seq3.get("applicable_categories") is None

    # 对任意 business_category，因为无 applicable_categories 限制，
    # _check_applicable 应直接返回 applicable_default = "no"
    svc = ProcedureTableService.__new__(ProcedureTableService)
    for cat in ("A1", "B1", "C"):
        result = svc._check_applicable(seq3, cat)
        assert result == "no", f"Expected 'no' for category {cat}, got '{result}'"


import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4


@pytest.mark.asyncio
async def test_a16_seq3_auto_suggests_applicable_yes_when_txn_exists():
    """A16 seq3: related_party_transaction_count > 0 时自动建议 applicable='yes'"""
    from app.services.procedure_table_auto_service import ProcedureTableService

    template = get_template("A16")
    seq3 = next(i for i in template["items"] if i["seq"] == 3)

    # Mock DB session
    db = AsyncMock()
    svc = ProcedureTableService(db)

    project_id = uuid4()

    # Mock: party_count=2, txn_count=5, txn_total=100000.0
    mock_party_result = MagicMock()
    mock_party_result.scalar.return_value = 2

    mock_txn_result = MagicMock()
    mock_txn_row = MagicMock()
    mock_txn_row.__getitem__ = lambda self, idx: [5, 100000.0][idx]
    mock_txn_result.one.return_value = mock_txn_row

    db.execute = AsyncMock(side_effect=[mock_party_result, mock_txn_result])

    result = await svc._resolve_auto_values(project_id, 2025, seq3, "C")

    # 有交易时 applicable 应被覆盖为 "yes"
    assert result["applicable"] == "yes"
    assert "5笔关联交易" in result["summary"]
    assert "2个关联方" in result["summary"]


@pytest.mark.asyncio
async def test_a16_seq3_auto_keeps_no_when_no_txn():
    """A16 seq3: 无关联交易时 applicable 保持默认 'no'"""
    from app.services.procedure_table_auto_service import ProcedureTableService

    template = get_template("A16")
    seq3 = next(i for i in template["items"] if i["seq"] == 3)

    # Mock DB session
    db = AsyncMock()
    svc = ProcedureTableService(db)

    project_id = uuid4()

    # Mock: party_count=0, txn_count=0, txn_total=0
    mock_party_result = MagicMock()
    mock_party_result.scalar.return_value = 0

    mock_txn_result = MagicMock()
    mock_txn_row = MagicMock()
    mock_txn_row.__getitem__ = lambda self, idx: [0, 0][idx]
    mock_txn_result.one.return_value = mock_txn_row

    db.execute = AsyncMock(side_effect=[mock_party_result, mock_txn_result])

    result = await svc._resolve_auto_values(project_id, 2025, seq3, "C")

    # 无交易时 applicable 保持 _check_applicable 返回的 "no"
    assert result["applicable"] == "no"
    assert result["summary"] == "待识别"
