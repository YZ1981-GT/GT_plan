"""附注级合并穿透服务单测（consol-phase3-frontend-drilldown / Phase 3 / Task 1）.

覆盖：
- (a) 章节有 breakdown → 返回 by_company + has_breakdown=True
- (b) 章节缺失 / breakdown 为空 → has_breakdown=False + 中文友好提示（EH1/EH3）
- (c) T2 provenance 自洽：Σ by_company[*].amount == 章节汇总值（Decimal）

Validates: Requirements 2.3, 2.4, 2.5; Property T2; Error scenarios EH1, EH3.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.note_consol_drilldown_service import (
    EMPTY_BREAKDOWN_MESSAGE,
    get_note_consol_breakdown,
)
from app.services.consol_disclosure_service import (
    _build_section_consolidation_breakdown,
    _sum_row_numeric_values,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_db_returning(note):
    """构造 AsyncMock db，使 db.execute(...).scalar_one_or_none() 返回 note."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=note)
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


def _make_note(*, breakdown, section_title="货币资金"):
    """构造一个带 consolidation_breakdown 的 mock DisclosureNote."""
    note = MagicMock()
    note.consolidation_breakdown = breakdown
    note.section_title = section_title
    return note


# ---------------------------------------------------------------------------
# (a) 有 breakdown → has_breakdown=True
# ---------------------------------------------------------------------------


class TestBreakdownPresent:
    @pytest.mark.asyncio
    async def test_returns_by_company_when_breakdown_present(self):
        """章节有 consolidation_breakdown → 返回 by_company + has_breakdown=True."""
        breakdown = {
            "by_company": [
                {"company_code": "SUB001", "company_name": "子公司A",
                 "section_title": "货币资金", "amount": "1234.56"},
                {"company_code": "SUB002", "company_name": "子公司B",
                 "section_title": "货币资金", "amount": "765.44"},
            ],
            "computed_at": "2026-05-30T00:00:00+00:00",
        }
        note = _make_note(breakdown=breakdown)
        db = _mock_db_returning(note)

        result = await get_note_consol_breakdown(db, uuid4(), 2025, "section_cash")

        assert result["has_breakdown"] is True
        assert result["message"] is None
        assert result["section_id"] == "section_cash"
        assert result["section_title"] == "货币资金"
        assert len(result["by_company"]) == 2
        assert result["by_company"][0]["company_code"] == "SUB001"
        assert result["computed_at"] == "2026-05-30T00:00:00+00:00"


# ---------------------------------------------------------------------------
# (b) 缺失 / 空 breakdown → has_breakdown=False + 中文提示
# ---------------------------------------------------------------------------


class TestBreakdownEmptyOrMissing:
    @pytest.mark.asyncio
    async def test_note_not_found_returns_friendly_empty(self):
        """章节不存在 → 友好空返回（EH1/EH3），不抛错."""
        db = _mock_db_returning(None)

        result = await get_note_consol_breakdown(db, uuid4(), 2025, "section_missing")

        assert result["has_breakdown"] is False
        assert result["by_company"] == []
        assert result["message"] == EMPTY_BREAKDOWN_MESSAGE
        assert result["message"] == "该章节暂无合并明细，请先用 V2 生成合并附注"
        assert result["section_id"] == "section_missing"

    @pytest.mark.asyncio
    async def test_breakdown_none_returns_friendly_empty(self):
        """章节存在但 consolidation_breakdown 为 None（未跑 V2）→ 友好空返回."""
        note = _make_note(breakdown=None, section_title="应收账款")
        db = _mock_db_returning(note)

        result = await get_note_consol_breakdown(db, uuid4(), 2025, "section_ar")

        assert result["has_breakdown"] is False
        assert result["by_company"] == []
        assert result["message"] == EMPTY_BREAKDOWN_MESSAGE
        # 章节存在时仍带回 section_title
        assert result["section_title"] == "应收账款"

    @pytest.mark.asyncio
    async def test_breakdown_empty_by_company_returns_friendly_empty(self):
        """by_company 为空列表 → 友好空返回."""
        note = _make_note(breakdown={"by_company": [], "computed_at": "x"})
        db = _mock_db_returning(note)

        result = await get_note_consol_breakdown(db, uuid4(), 2025, "section_cash")

        assert result["has_breakdown"] is False
        assert result["by_company"] == []
        assert result["message"] == EMPTY_BREAKDOWN_MESSAGE


# ---------------------------------------------------------------------------
# (c) T2 provenance 自洽：Σ by_company amount == 章节汇总值
# ---------------------------------------------------------------------------


class TestProvenanceSelfConsistency:
    """属性 T2：Σ by_company[*].amount（同口径）== 该合并章节汇总值."""

    def test_sum_by_company_equals_section_total(self):
        """每行带 source_project 时，Σ by_company == 全部行数值单元格之和."""
        sub_a = uuid4()
        sub_b = uuid4()
        subsidiaries = [
            {"project_id": sub_a, "company_code": "SUB001", "company_name": "子公司A"},
            {"project_id": sub_b, "company_code": "SUB002", "company_name": "子公司B"},
        ]
        result = {
            "rows": [
                {"label": "银行存款", "source_project": sub_a,
                 "values": {"col_end": "1000.50", "col_begin": "900.00"}},
                {"label": "库存现金", "source_project": sub_a,
                 "values": {"col_end": "50.25"}},
                {"label": "银行存款", "source_project": sub_b,
                 "values": {"col_end": "2000.00", "col_begin": "1500.00"}},
            ],
        }

        breakdown = _build_section_consolidation_breakdown(
            section_title="货币资金", result=result, subsidiaries=subsidiaries,
        )

        # 章节汇总值 = 全部行全部数值单元格之和
        section_total = sum(
            (_sum_row_numeric_values(r["values"]) for r in result["rows"]),
            Decimal("0"),
        )
        # Σ by_company amount
        by_company_total = sum(
            (Decimal(c["amount"]) for c in breakdown["by_company"]),
            Decimal("0"),
        )

        assert by_company_total == section_total
        assert section_total == Decimal("5450.75")
        # 两家子公司各一条
        assert len(breakdown["by_company"]) == 2
        assert breakdown["computed_at"] is not None

    def test_per_company_amount_correct(self):
        """每家子公司的 amount 等于其各行数值之和."""
        sub_a = uuid4()
        subsidiaries = [
            {"project_id": sub_a, "company_code": "SUB001", "company_name": "子公司A"},
        ]
        result = {
            "rows": [
                {"label": "r1", "source_project": sub_a, "values": {"c": "100.00"}},
                {"label": "r2", "source_project": sub_a, "values": {"c": "23.45"}},
            ],
        }

        breakdown = _build_section_consolidation_breakdown(
            section_title="测试章节", result=result, subsidiaries=subsidiaries,
        )

        assert len(breakdown["by_company"]) == 1
        entry = breakdown["by_company"][0]
        assert entry["company_code"] == "SUB001"
        assert entry["section_title"] == "测试章节"
        assert Decimal(entry["amount"]) == Decimal("123.45")

    def test_unattributable_rows_excluded(self):
        """无 source_project 的行不归属 by_company（避免错误归属）."""
        sub_a = uuid4()
        subsidiaries = [
            {"project_id": sub_a, "company_code": "SUB001", "company_name": "子公司A"},
        ]
        result = {
            "rows": [
                {"label": "归属", "source_project": sub_a, "values": {"c": "100.00"}},
                {"label": "合计(已合并无来源)", "values": {"c": "100.00"}},
            ],
        }

        breakdown = _build_section_consolidation_breakdown(
            section_title="t", result=result, subsidiaries=subsidiaries,
        )

        # 仅归属行进入 by_company
        assert len(breakdown["by_company"]) == 1
        assert Decimal(breakdown["by_company"][0]["amount"]) == Decimal("100.00")
