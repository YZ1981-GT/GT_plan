"""E1 货币资金后端 payload builder 单元测试。

不依赖数据库——mock load_disclosure_entries / load_project_template_type，
验证 sub_table_data 与前端 buildE1SyncPayload 逐字段一致。

spec: backend-disclosure-payload-builder Phase 2 Task 5 / Task 13
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from app.services.disclosure_builders.e1_builder import E1Builder

PID = UUID("aaaaaaaa-0000-0000-0000-000000000001")
YEAR = 2025

# ── 工具 ──────────────────────────────────────────────────────────────────────


def _make_entries(**overrides: str) -> dict[str, str]:
    """构造 checklist_responses 字典（默认三科目审定数 + 受限空数组）。"""
    base = {
        "E1-adj-total-1001": "1000",
        "E1-adj-total-1001-opening": "900",
        "E1-adj-total-1002": "50000",
        "E1-adj-total-1002-opening": "40000",
        "E1-adj-total-1012": "200000",
        "E1-adj-total-1012-opening": "150000",
        "E1-disclosure-soe-restricted": "[]",
    }
    base.update(overrides)
    return base


async def _build(entries: dict, template_type: str = "soe"):
    with patch(
        "app.services.disclosure_builders.e1_builder.load_disclosure_entries",
        new=AsyncMock(return_value=entries),
    ), patch(
        "app.services.disclosure_builders.e1_builder.load_project_template_type",
        new=AsyncMock(return_value=template_type),
    ), patch(
        "app.services.disclosure_builders.e1_builder.load_project_standard",
        new=AsyncMock(return_value=f"{template_type}_standalone"),
    ):
        builder = E1Builder()
        return await builder.build(AsyncMock(), PID, YEAR)


# ── 主表 ──────────────────────────────────────────────────────────────────────


class TestE1MainTableSoe:
    @pytest.mark.asyncio
    async def test_soe_six_rows(self):
        result = await _build(_make_entries())
        assert result is not None
        rows = result.sub_table_data["货币资金"]
        assert len(rows) == 6
        labels = [r["label"] for r in rows]
        assert labels == [
            "库存现金", "银行存款", "其他货币资金",
            "数字货币", "合计", "其中：存放在境外的款项总额",
        ]

    @pytest.mark.asyncio
    async def test_soe_amounts(self):
        result = await _build(_make_entries())
        rows = result.sub_table_data["货币资金"]
        # 库存现金 = 1001
        assert rows[0]["end_amount"] == 1000.0
        assert rows[0]["prior_amount"] == 900.0
        # 银行存款 = 1002
        assert rows[1]["end_amount"] == 50000.0
        # 其他货币资金 = 1012
        assert rows[2]["end_amount"] == 200000.0
        # 数字货币无 crossKey = 0
        assert rows[3]["end_amount"] == 0.0

    @pytest.mark.asyncio
    async def test_soe_total_is_sum(self):
        result = await _build(_make_entries())
        rows = result.sub_table_data["货币资金"]
        total_row = rows[4]
        assert total_row["is_total"] is True
        expected_end = 1000 + 50000 + 200000 + 0  # cash + bank + other + digital
        assert total_row["end_amount"] == expected_end
        expected_prior = 900 + 40000 + 150000 + 0
        assert total_row["prior_amount"] == expected_prior

    @pytest.mark.asyncio
    async def test_soe_memo_row(self):
        result = await _build(_make_entries())
        rows = result.sub_table_data["货币资金"]
        memo = rows[5]
        assert memo.get("is_memo") is True
        assert memo["label"] == "其中：存放在境外的款项总额"

    @pytest.mark.asyncio
    async def test_section_and_standard(self):
        result = await _build(_make_entries())
        assert result.section_id == "八、1"
        assert result.current_standard == "soe_standalone"
        assert result.sheet_name == "附注披露信息(国企)"


class TestE1MainTableListed:
    @pytest.mark.asyncio
    async def test_listed_eight_rows(self):
        result = await _build(_make_entries(), template_type="listed")
        rows = result.sub_table_data["货币资金"]
        assert len(rows) == 8
        labels = [r["label"] for r in rows]
        assert labels == [
            "库存现金", "银行存款", "存放财务公司款项", "其他货币资金",
            "存款应计利息", "数字货币", "合计", "其中：存放在境外的款项总额",
        ]

    @pytest.mark.asyncio
    async def test_listed_section(self):
        result = await _build(_make_entries(), template_type="listed")
        assert result.section_id == "五、1"
        assert result.current_standard == "listed_standalone"


# ── 受限明细 ──────────────────────────────────────────────────────────────────


class TestE1RestrictedTable:
    @pytest.mark.asyncio
    async def test_empty_array_produces_removed_key(self):
        result = await _build(_make_entries())
        assert "受限制的货币资金明细" not in result.sub_table_data
        assert result.sub_table_data.get("_removed_table_keys") == ["受限制的货币资金明细"]

    @pytest.mark.asyncio
    async def test_restricted_with_data(self):
        restricted = json.dumps([
            {"item": "保证金", "endingAmount": 100000, "openingAmount": 80000, "reason": "质押"},
            {"item": "冻结款", "endingAmount": 50000, "openingAmount": 0, "reason": "法院冻结"},
        ])
        result = await _build(_make_entries(**{
            "E1-disclosure-soe-restricted": restricted,
        }))
        rows = result.sub_table_data["受限制的货币资金明细"]
        assert len(rows) == 3  # 2 data + 1 total
        assert rows[0]["label"] == "保证金"
        assert rows[0]["end_amount"] == 100000.0
        assert rows[1]["label"] == "冻结款"
        # 合计
        assert rows[2]["is_total"] is True
        assert rows[2]["end_amount"] == 150000.0
        assert rows[2]["prior_amount"] == 80000.0
        # columns 也有
        assert "受限制的货币资金明细" in result.sub_table_columns

    @pytest.mark.asyncio
    async def test_no_restricted_key_means_no_removed(self):
        """restricted key 不存在（非空数组）= 不管这张表 → 不进 removed。"""
        entries = _make_entries()
        del entries["E1-disclosure-soe-restricted"]
        result = await _build(entries)
        assert "_removed_table_keys" not in result.sub_table_data


# ── 披露说明 ──────────────────────────────────────────────────────────────────


class TestE1NoteTexts:
    @pytest.mark.asyncio
    async def test_soe_note_texts(self):
        result = await _build(_make_entries(**{
            "E1-disclosure-soe-note-restricted": "期末无受限款项。",
            "E1-disclosure-soe-note-digital": "不涉及数字货币。",
        }))
        texts = result.sub_table_data.get("_note_texts", [])
        assert len(texts) == 2
        assert texts[0]["section"] == "restricted"
        assert texts[0]["title"] == "受限及境外款项说明"
        assert texts[0]["text"] == "期末无受限款项。"
        assert texts[1]["section"] == "digital"

    @pytest.mark.asyncio
    async def test_empty_text_not_included(self):
        result = await _build(_make_entries(**{
            "E1-disclosure-soe-note-restricted": "",
        }))
        texts = result.sub_table_data.get("_note_texts", [])
        assert len(texts) == 0

    @pytest.mark.asyncio
    async def test_listed_note_keys(self):
        result = await _build(_make_entries(**{
            "E1-disclosure-listed-restricted": "[]",
            "E1-disclosure-listed-note-restricted": "无受限。",
            "E1-disclosure-listed-note-interest": "利息说明。",
        }), template_type="listed")
        texts = result.sub_table_data.get("_note_texts", [])
        assert len(texts) == 2
        sections = [t["section"] for t in texts]
        assert sections == ["restricted", "interest"]


# ── 边界 ──────────────────────────────────────────────────────────────────────


class TestE1EdgeCases:
    @pytest.mark.asyncio
    async def test_no_data_returns_none(self):
        result = await _build({})
        assert result is None

    @pytest.mark.asyncio
    async def test_non_numeric_remark_becomes_zero(self):
        result = await _build(_make_entries(**{
            "E1-adj-total-1001": "N/A",
            "E1-adj-total-1001-opening": "",
        }))
        rows = result.sub_table_data["货币资金"]
        assert rows[0]["end_amount"] == 0.0
        assert rows[0]["prior_amount"] == 0.0

    @pytest.mark.asyncio
    async def test_float_precision(self):
        """小数不丢精度。"""
        result = await _build(_make_entries(**{
            "E1-adj-total-1002": "327095.20",
        }))
        rows = result.sub_table_data["货币资金"]
        assert rows[1]["end_amount"] == 327095.20
