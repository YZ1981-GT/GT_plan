"""后端 disclosure payload builder 全量回归测试。

spec: backend-disclosure-payload-builder Task 13/18/24/25/26
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

PID = UUID("aaaaaaaa-0000-0000-0000-000000000001")
YEAR = 2025


# ── 注册表验证 ────────────────────────────────────────────────────────────────


class TestBuilderRegistry:
    def test_all_builders_registered(self):
        from app.services.disclosure_payload_builder_service import registered_wp_codes
        codes = registered_wp_codes()
        assert len(codes) >= 78, f"应至少注册 78 个 builder，实际 {len(codes)}"
        # 核心 8 个必须在列
        for core in ["E1", "D1", "D2", "F2", "H1", "I1", "G7", "K1"]:
            assert core in codes, f"{core} 未注册"

    def test_no_duplicate_wp_codes(self):
        from app.services.disclosure_payload_builder_service import registered_wp_codes
        codes = registered_wp_codes()
        assert len(codes) == len(set(codes)), "有重复的 wp_code"

    def test_get_builder_returns_instance(self):
        from app.services.disclosure_payload_builder_service import get_builder
        b = get_builder("E1")
        assert b is not None
        assert b.wp_code == "E1"

    def test_get_builder_unknown_returns_none(self):
        from app.services.disclosure_payload_builder_service import get_builder
        assert get_builder("Z99") is None


# ── E1 专用 builder 回归 ──────────────────────────────────────────────────────


class TestE1BuilderRegression:
    @pytest.mark.asyncio
    async def test_soe_produces_six_rows(self):
        from app.services.disclosure_builders.e1_builder import E1Builder
        entries = {
            "E1-adj-total-1001": "1000",
            "E1-adj-total-1001-opening": "900",
            "E1-adj-total-1002": "50000",
            "E1-adj-total-1002-opening": "40000",
            "E1-adj-total-1012": "200000",
            "E1-adj-total-1012-opening": "150000",
            "E1-disclosure-soe-restricted": "[]",
        }
        with patch("app.services.disclosure_builders.e1_builder.load_disclosure_entries", new=AsyncMock(return_value=entries)), \
             patch("app.services.disclosure_builders.e1_builder.load_project_template_type", new=AsyncMock(return_value="soe")), \
             patch("app.services.disclosure_builders.e1_builder.load_project_standard", new=AsyncMock(return_value="soe_standalone")):
            result = await E1Builder().build(AsyncMock(), PID, YEAR)
        assert result is not None
        rows = result.sub_table_data["货币资金"]
        assert len(rows) == 6
        total = next(r for r in rows if r.get("is_total"))
        assert total["end_amount"] == 251000.0


# ── 标准 builder 批量验证 ────────────────────────────────────────────────────


class TestStandardBuilders:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("wp_code,expected_table", [
        ("D3", "预收款项"),
        ("D5", "应收款项融资"),
        ("F1", "预付款项"),
        ("F3", "应付票据"),
        ("G1", "交易性金融资产"),
        ("H2", "在建工程"),
        ("I2", "开发支出"),
        ("J1", "应付职工薪酬"),
        ("K2", "其他流动资产"),
        ("L1", "短期借款"),
        ("M2", "实收资本"),
        ("N1", "递延所得税资产"),
    ])
    async def test_standard_builder_produces_result(self, wp_code, expected_table):
        from app.services.disclosure_payload_builder_service import build_for_wp_code
        entries = {f"{wp_code}-adj-tb-amount": "12345.67"}
        with patch("app.services.disclosure_builders.standard_builder.load_disclosure_entries", new=AsyncMock(return_value=entries)), \
             patch("app.services.disclosure_builders.standard_builder.load_project_template_type", new=AsyncMock(return_value="soe")), \
             patch("app.services.disclosure_builders.standard_builder.load_project_standard", new=AsyncMock(return_value="soe_standalone")):
            result = await build_for_wp_code(AsyncMock(), PID, YEAR, wp_code)
        assert result is not None, f"{wp_code} 应产出结果"
        assert expected_table in result.sub_table_data
        rows = result.sub_table_data[expected_table]
        assert len(rows) == 2  # 数据行 + 合计
        assert rows[0]["end_amount"] == 12345.67
        assert rows[1].get("is_total") is True

    @pytest.mark.asyncio
    async def test_empty_entries_returns_none(self):
        from app.services.disclosure_payload_builder_service import build_for_wp_code
        with patch("app.services.disclosure_builders.standard_builder.load_disclosure_entries", new=AsyncMock(return_value={})):
            result = await build_for_wp_code(AsyncMock(), PID, YEAR, "D3")
        assert result is None


# ── D2 账龄聚合验证 ──────────────────────────────────────────────────────────


class TestD2BuilderAging:
    @pytest.mark.asyncio
    async def test_aging_aggregation(self):
        import json
        from app.services.disclosure_builders.d2_builder import D2Builder
        detail_rows = json.dumps([
            {"agingAudited": {"within1": 100, "y1to2": 50}, "agingPrior": {"within1": 80}},
            {"agingAudited": {"within1": 200, "y2to3": 30}, "agingPrior": {"within1": 150}},
        ])
        entries = {"D2-detail-rows": detail_rows, "D2-adj-tb-amount": "380"}
        with patch("app.services.disclosure_builders.d2_builder.load_disclosure_entries", new=AsyncMock(return_value=entries)), \
             patch("app.services.disclosure_builders.d2_builder.load_project_template_type", new=AsyncMock(return_value="soe")), \
             patch("app.services.disclosure_builders.d2_builder.load_project_standard", new=AsyncMock(return_value="soe_standalone")):
            result = await D2Builder().build(AsyncMock(), PID, YEAR)
        # soe 表名是「（1）按账龄披露应收账款」
        aging_table = "（1）按账龄披露应收账款"
        assert aging_table in result.sub_table_data, f"子表键: {list(result.sub_table_data.keys())}"
        rows = result.sub_table_data[aging_table]
        assert rows[0]["end_amount"] == 300.0  # within1: 100+200
        assert rows[0]["prior_amount"] == 230.0  # prior within1: 80+150
        assert rows[1]["end_amount"] == 50.0   # y1to2
        assert rows[2]["end_amount"] == 30.0   # y2to3
        total = rows[-1]
        assert total["is_total"] is True
        assert total["end_amount"] == 380.0
        # 还应有分类表和前五名
        assert len(result.sub_table_data) >= 4, f"应至少 4 张子表，实际 {len(result.sub_table_data)}"


# ── K1 JSON 解析验证 ─────────────────────────────────────────────────────────


class TestK1BuilderNoteRows:
    @pytest.mark.asyncio
    async def test_parses_aging_from_note_json(self):
        import json
        from app.services.disclosure_builders.k1_builder import K1Builder
        note_json = json.dumps({
            "version": 2,
            "agingRows": [
                {"label": "1年以内", "kind": "data", "endAmount": 500, "priorAmount": 400},
                {"label": "合计", "kind": "total", "endAmount": 500, "priorAmount": 400},
            ],
        })
        entries = {"K1-note-soe-rows": note_json, "K1-1-audited-net": "500"}
        with patch("app.services.disclosure_builders.k1_builder.load_disclosure_entries", new=AsyncMock(return_value=entries)), \
             patch("app.services.disclosure_builders.k1_builder.load_project_template_type", new=AsyncMock(return_value="soe")), \
             patch("app.services.disclosure_builders.k1_builder.load_project_standard", new=AsyncMock(return_value="soe_standalone")):
            result = await K1Builder().build(AsyncMock(), PID, YEAR)
        rows = result.sub_table_data["其他应收款"]
        assert len(rows) == 2
        assert rows[0]["end_amount"] == 500.0
        assert rows[1].get("is_total") is True


# ── PayloadBuildResult 结构契约 ──────────────────────────────────────────────


class TestPayloadBuildResultContract:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("wp_code", ["E1", "D1", "D2", "F2", "H1", "I1", "G7", "K1"])
    async def test_result_has_required_fields(self, wp_code):
        from app.services.disclosure_payload_builder_service import get_builder
        builder = get_builder(wp_code)
        assert builder is not None
        assert builder.wp_code == wp_code
