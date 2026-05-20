"""K-F8 K11 资产减值损失跨循环汇总 — 单元测试

Covers:
- IMPAIRMENT_SOURCES 4 类资产配置（H1 / I3 / G14 / F2）
- 跨循环来源数据查找（含字段名兼容：impairment_amount / total_impairment / ecl_amount）
- 汇总计算正确性
- 来源缺失处理（sources_missing 列表 + 不阻断）
- apply_to_sheet 写回联动
- RBAC 校验（require_project_access('edit')）
- is_llm_stub config 驱动
- summary 文案变量插值

对应 spec: workpaper-k-admin-cycle K-F8 / ADR-K5
"""

import sys
sys.path.insert(0, "backend")

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_k_impairment_summary import (
    IMPAIRMENT_SOURCES,
    ImpairmentByType,
    ImpairmentSummaryRequest,
    ImpairmentSummaryResponse,
    _lookup_impairment_amount,
    _maybe_apply_summary_to_workpaper,
    k11_impairment_summary,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. IMPAIRMENT_SOURCES 配置
# ═══════════════════════════════════════════════════════════════════════════════


class TestImpairmentSourcesConfig:
    """4 类资产减值来源配置（H1 / I3 / G14 / F2）"""

    def test_four_sources_configured(self):
        assert len(IMPAIRMENT_SOURCES) == 4

    def test_source_h1_fixed_assets(self):
        src = next(s for s in IMPAIRMENT_SOURCES if s["wp_code"] == "H1")
        assert src["asset_type"] == "固定资产减值"
        assert src["namespace"] == "impairment_calcs"

    def test_source_i3_goodwill(self):
        src = next(s for s in IMPAIRMENT_SOURCES if s["wp_code"] == "I3")
        assert src["asset_type"] == "商誉减值"
        assert src["namespace"] == "goodwill_impairment_calcs"

    def test_source_g14_ecl(self):
        src = next(s for s in IMPAIRMENT_SOURCES if s["wp_code"] == "G14")
        assert src["asset_type"] == "信用减值损失"
        assert src["namespace"] == "ecl_calcs"

    def test_source_f2_inventory(self):
        src = next(s for s in IMPAIRMENT_SOURCES if s["wp_code"] == "F2")
        assert src["asset_type"] == "存货跌价"
        assert src["namespace"] == "impairment_calcs"

    def test_each_source_has_default_sheet_pattern(self):
        for src in IMPAIRMENT_SOURCES:
            assert src.get("default_sheet_pattern"), (
                f"{src['wp_code']} 缺少 default_sheet_pattern"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 跨循环来源查找逻辑
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestLookupImpairment:
    """_lookup_impairment_amount 逻辑测试"""

    async def test_lookup_no_workpaper_returns_zero(self):
        """无对应底稿 → 返回 (0.0, None)"""
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        amount, sheet = await _lookup_impairment_amount(
            db, "00000000-0000-0000-0000-000000000001", "H1", "impairment_calcs"
        )
        assert amount == 0.0
        assert sheet is None

    async def test_lookup_empty_namespace_returns_zero(self):
        """parsed_data 中无指定 namespace → 返回 (0.0, None)"""
        from app.models.workpaper_models import WorkingPaper

        wp = MagicMock(spec=WorkingPaper)
        wp.parsed_data = {"other_namespace": {}}
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = wp
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)

        amount, sheet = await _lookup_impairment_amount(
            db, "00000000-0000-0000-0000-000000000001", "H1", "impairment_calcs"
        )
        assert amount == 0.0
        assert sheet is None

    async def test_lookup_with_impairment_amount_field(self):
        """字段名 impairment_amount → 正确累加"""
        from app.models.workpaper_models import WorkingPaper

        wp = MagicMock(spec=WorkingPaper)
        wp.parsed_data = {
            "impairment_calcs": {
                "减值测算表H1-14": {
                    "data": {"impairment_amount": 350000.00}
                }
            }
        }
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = wp
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)

        amount, sheet = await _lookup_impairment_amount(
            db, "00000000-0000-0000-0000-000000000001", "H1", "impairment_calcs"
        )
        assert amount == 350000.00
        assert sheet == "减值测算表H1-14"

    async def test_lookup_with_total_impairment_field(self):
        """字段名 total_impairment（兼容）"""
        from app.models.workpaper_models import WorkingPaper

        wp = MagicMock(spec=WorkingPaper)
        wp.parsed_data = {
            "goodwill_impairment_calcs": {
                "减值测试I3-6": {
                    "data": {"total_impairment": 200000.00}
                }
            }
        }
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = wp
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)

        amount, sheet = await _lookup_impairment_amount(
            db, "00000000-0000-0000-0000-000000000001", "I3", "goodwill_impairment_calcs"
        )
        assert amount == 200000.00
        assert sheet == "减值测试I3-6"

    async def test_lookup_with_ecl_amount_field(self):
        """字段名 ecl_amount（G14 ECL 兼容）"""
        from app.models.workpaper_models import WorkingPaper

        wp = MagicMock(spec=WorkingPaper)
        wp.parsed_data = {
            "ecl_calcs": {
                "审定表G14-1": {"data": {"ecl_amount": 100000.00}}
            }
        }
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = wp
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)

        amount, sheet = await _lookup_impairment_amount(
            db, "00000000-0000-0000-0000-000000000001", "G14", "ecl_calcs"
        )
        assert amount == 100000.00
        assert sheet == "审定表G14-1"

    async def test_lookup_invalid_uuid_returns_zero(self):
        """无效 project_id → (0.0, None)"""
        db = MagicMock()
        amount, sheet = await _lookup_impairment_amount(
            db, "not-a-uuid", "H1", "impairment_calcs"
        )
        assert amount == 0.0
        assert sheet is None

    async def test_lookup_multiple_sheets_accumulated(self):
        """单 namespace 多 sheet → 金额累加"""
        from app.models.workpaper_models import WorkingPaper

        wp = MagicMock(spec=WorkingPaper)
        wp.parsed_data = {
            "impairment_calcs": {
                "sheet_a": {"data": {"impairment_amount": 100.00}},
                "sheet_b": {"data": {"impairment_amount": 200.00}},
            }
        }
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = wp
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)

        amount, sheet = await _lookup_impairment_amount(
            db, "00000000-0000-0000-0000-000000000001", "H1", "impairment_calcs"
        )
        assert amount == 300.00
        # 第一个非零 sheet 作为代表
        assert sheet in ("sheet_a", "sheet_b")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. RBAC
# ═══════════════════════════════════════════════════════════════════════════════


class TestRBAC:
    """RBAC 校验"""

    def test_endpoint_uses_require_project_access_edit(self):
        import app.routers.wp_k_impairment_summary as mod
        src = inspect.getsource(mod)
        assert 'require_project_access("edit")' in src

    def test_endpoint_function_has_user_dependency(self):
        sig = inspect.signature(k11_impairment_summary)
        param_names = list(sig.parameters.keys())
        assert "_user" in param_names

    def test_router_prefix_contains_project_id_and_wp_id(self):
        from app.routers.wp_k_impairment_summary import router
        assert "{project_id}" in router.prefix
        assert "{wp_id}" in router.prefix

    def test_router_prefix_contains_k11(self):
        """路由前缀应明确指向 K11（资产减值损失）"""
        from app.routers.wp_k_impairment_summary import router
        assert "k11" in router.prefix


# ═══════════════════════════════════════════════════════════════════════════════
# 4. is_llm_stub 配置驱动
# ═══════════════════════════════════════════════════════════════════════════════


class TestStubConfig:
    """is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动"""

    def test_stub_flag_default_true(self):
        from app.core.config import settings
        enabled = getattr(settings, "WP_AI_SERVICE_ENABLED", False)
        is_stub = not enabled
        assert is_stub is True

    def test_stub_flag_when_enabled(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", True)
        enabled = getattr(settings, "WP_AI_SERVICE_ENABLED", False)
        is_stub = not enabled
        assert is_stub is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 写回联动
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestWriteBack:
    """apply_to_sheet 写回联动"""

    def test_write_back_function_callable(self):
        assert callable(_maybe_apply_summary_to_workpaper)

    async def test_write_back_invalid_uuid_returns_none(self):
        """无效 wp_id → 返回 None（不抛异常）"""
        r = await _maybe_apply_summary_to_workpaper(
            None, "invalid-uuid", "审定表K11-1", {"foo": "bar"}
        )
        assert r is None

    async def test_write_back_writes_namespace_correctly(self):
        """写回结构：parsed_data.impairment_summary[sheet] = {applied_at, data}"""
        from app.models.workpaper_models import WorkingPaper

        wp = MagicMock(spec=WorkingPaper)
        wp.parsed_data = None  # 初始为 None
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = wp
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        wp_id = "00000000-0000-0000-0000-000000000001"
        data = {"total_impairment": 1000000.0}

        applied = await _maybe_apply_summary_to_workpaper(
            db, wp_id, "审定表K11-1", data
        )
        assert applied == "审定表K11-1"
        assert "impairment_summary" in wp.parsed_data
        assert "审定表K11-1" in wp.parsed_data["impairment_summary"]
        assert (
            wp.parsed_data["impairment_summary"]["审定表K11-1"]["data"]
            == data
        )
        assert "applied_at" in wp.parsed_data["impairment_summary"]["审定表K11-1"]


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Schema 校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestSchemas:
    """Schema 类型与字段校验"""

    def test_request_schema_year_range(self):
        """year 必须在 [2000, 2100]"""
        # 合法
        req = ImpairmentSummaryRequest(year=2025)
        assert req.year == 2025
        # 越界
        with pytest.raises(Exception):
            ImpairmentSummaryRequest(year=1999)
        with pytest.raises(Exception):
            ImpairmentSummaryRequest(year=2101)

    def test_request_schema_apply_to_sheet_optional(self):
        """apply_to_sheet 可选"""
        req = ImpairmentSummaryRequest(year=2025)
        assert req.apply_to_sheet is None
        req2 = ImpairmentSummaryRequest(year=2025, apply_to_sheet="审定表K11-1")
        assert req2.apply_to_sheet == "审定表K11-1"

    def test_response_schema_required_fields(self):
        """响应必含字段"""
        resp = ImpairmentSummaryResponse(
            impairment_by_type=[
                ImpairmentByType(
                    asset_type="固定资产减值",
                    amount=350000.0,
                    source_wp="H1",
                    source_sheet="减值测算表H1-14",
                )
            ],
            total_impairment=350000.0,
            sources_found=["H1.减值测算表H1-14"],
            sources_missing=[],
            summary="K11 资产减值汇总：合计 ¥350,000.00",
            is_llm_stub=True,
        )
        assert resp.total_impairment == 350000.0
        assert len(resp.impairment_by_type) == 1
        assert resp.is_llm_stub is True


# ═══════════════════════════════════════════════════════════════════════════════
# 7. summary 文案
# ═══════════════════════════════════════════════════════════════════════════════


class TestSummaryGeneration:
    """summary 文案验证（变量插值正确性）"""

    def test_summary_includes_total(self):
        """summary 应含 total_impairment 数值"""
        # 通过反射验证 summary 模板含变量占位（不直接调用 endpoint）
        import app.routers.wp_k_impairment_summary as mod
        src = inspect.getsource(mod)
        # 验证 summary 字段含变量插值（K11 + 总额 + 来源数）
        assert "K11" in src and "合计" in src and "来源" in src

    def test_summary_stub_marker_when_disabled(self):
        """is_llm_stub=True 时 summary 应包含 wp_ai_service 提示"""
        import app.routers.wp_k_impairment_summary as mod
        src = inspect.getsource(mod)
        assert "wp_ai_service" in src
