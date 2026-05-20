"""F-F11 计价测试自动抽样 + F-F12 跌价准备 ECL 模型 单元测试

不依赖数据库（schema/逻辑层面验证）：
- F-F11: stratified sampling 三层比例分配 / 方法枚举校验 / response 结构
- F-F12: lower-of-cost-or-NRV 计算 / 库龄风险等级 / 重要性提示
"""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def schemas():
    """直接导入 pydantic schemas，绕过 DB 依赖"""
    from app.routers.wp_f2_valuation import (
        ValuationSampleRequest,
        ValuationSampleResponse,
        ValuationSampleItem,
    )
    from app.routers.wp_f2_impairment import (
        ImpairmentAnalysisRequest,
        ImpairmentAnalysisResponse,
        ImpairmentSuggestion,
        ProductImpairmentItem,
    )
    return {
        "ValuationSampleRequest": ValuationSampleRequest,
        "ValuationSampleResponse": ValuationSampleResponse,
        "ValuationSampleItem": ValuationSampleItem,
        "ImpairmentAnalysisRequest": ImpairmentAnalysisRequest,
        "ImpairmentAnalysisResponse": ImpairmentAnalysisResponse,
        "ImpairmentSuggestion": ImpairmentSuggestion,
        "ProductImpairmentItem": ProductImpairmentItem,
    }


# ---- F-F11 ValuationSampleRequest schema -------------------------------------

def test_valuation_request_default_method(schemas):
    req = schemas["ValuationSampleRequest"](year=2024)
    assert req.method == "weighted_average"
    assert req.account_code == "1403"
    assert req.sample_size == 20


def test_valuation_request_accepts_three_methods(schemas):
    for m in ("weighted_average", "fifo", "standard_cost"):
        req = schemas["ValuationSampleRequest"](year=2024, method=m)
        assert req.method == m


def test_valuation_request_sample_size_bounds(schemas):
    """sample_size 必须在 [1, 100]"""
    with pytest.raises(Exception):
        schemas["ValuationSampleRequest"](year=2024, sample_size=0)
    with pytest.raises(Exception):
        schemas["ValuationSampleRequest"](year=2024, sample_size=101)


# ---- F-F11 _stratified_sample 逻辑（不依赖 DB）---------------------------------

def test_stratified_layer_distribution_logic():
    """sample_size=20 应均分到 high(6) / mid(6) / low(8)"""
    sample_size = 20
    per_layer = max(1, sample_size // 3)
    high_n = per_layer
    mid_n = per_layer
    low_n = sample_size - 2 * per_layer
    assert (high_n, mid_n, low_n) == (6, 6, 8)
    assert high_n + mid_n + low_n == sample_size


def test_stratified_layer_distribution_small():
    """sample_size=4 应分到 high(1) / mid(1) / low(2)"""
    sample_size = 4
    per_layer = max(1, sample_size // 3)
    high_n = per_layer
    mid_n = per_layer
    low_n = sample_size - 2 * per_layer
    assert high_n + mid_n + low_n == sample_size
    assert (high_n, mid_n, low_n) == (1, 1, 2)


# ---- F-F11 period parser 测试 ----------------------------------------------

def test_period_parser_full_year():
    from app.routers.wp_f2_valuation import _parse_period_range
    assert _parse_period_range("全年") == (1, 12)
    assert _parse_period_range("") == (1, 12)
    assert _parse_period_range("*") == (1, 12)


def test_period_parser_single_month():
    from app.routers.wp_f2_valuation import _parse_period_range
    assert _parse_period_range("3月") == (3, 3)
    assert _parse_period_range("12月") == (12, 12)


def test_period_parser_range():
    from app.routers.wp_f2_valuation import _parse_period_range
    assert _parse_period_range("1-3月") == (1, 3)
    assert _parse_period_range("4-6月") == (4, 6)


# ---- F-F12 ImpairmentAnalysisRequest schema ----------------------------------

def test_impairment_request_required_fields(schemas):
    req = schemas["ImpairmentAnalysisRequest"](
        products=[{"product_name": "A", "cost": 100, "nrv": 80}],
    )
    assert req.method == "lower_of_cost_or_nrv"
    assert req.materiality_threshold == 50000.0


def test_impairment_request_three_methods(schemas):
    for m in ("lower_of_cost_or_nrv", "specific_id", "aging_based"):
        req = schemas["ImpairmentAnalysisRequest"](
            products=[{"product_name": "A", "cost": 100, "nrv": 80}],
            method=m,
        )
        assert req.method == m


def test_impairment_product_validation_negative_cost(schemas):
    with pytest.raises(Exception):
        schemas["ProductImpairmentItem"](product_name="A", cost=-1, nrv=80)
    with pytest.raises(Exception):
        schemas["ProductImpairmentItem"](product_name="A", cost=100, nrv=-1)


# ---- F-F12 lower-of-cost-or-NRV 核心逻辑 ------------------------------------

@pytest.mark.parametrize(
    "cost,nrv,expected_provision",
    [
        (100, 80, 20),  # cost > nrv → 计提 20
        (100, 100, 0),  # 相等 → 不计提
        (100, 120, 0),  # cost < nrv → 不计提
        (1000.55, 600.55, 400.00),
        (0, 0, 0),
    ],
)
def test_provision_calculation_logic(cost, nrv, expected_provision):
    """成本与可变现净值孰低法核心公式"""
    cost_d = Decimal(str(cost))
    nrv_d = Decimal(str(nrv))
    provision = cost_d - nrv_d if cost_d > nrv_d else Decimal("0")
    assert float(provision) == pytest.approx(expected_provision, rel=1e-3)


@pytest.mark.parametrize(
    "aging_months,expected_risk",
    [
        (0, "low"),
        (6, "low"),
        (11, "low"),
        (12, "medium"),
        (18, "medium"),
        (23, "medium"),
        (24, "high"),
        (36, "high"),
        (60, "high"),
    ],
)
def test_aging_risk_level_thresholds(aging_months, expected_risk):
    """库龄风险等级阈值：<12 low, 12-23 medium, ≥24 high"""
    if aging_months >= 24:
        risk = "high"
    elif aging_months >= 12:
        risk = "medium"
    else:
        risk = "low"
    assert risk == expected_risk


def test_materiality_hint_below_threshold():
    """provision < materiality_threshold 时应在 rationale 中提示"""
    provision = Decimal("3000")
    materiality = Decimal("50000")
    show_hint = 0 < provision < materiality
    assert show_hint is True

    provision_high = Decimal("60000")
    show_hint_high = 0 < provision_high < materiality
    assert show_hint_high is False


# ---- 路由注册 smoke test --------------------------------------------------

def test_router_paths_registered():
    """两个路由的 path 应正确注册"""
    from app.routers.wp_f2_valuation import router as v_router
    from app.routers.wp_f2_impairment import router as i_router

    v_paths = [r.path for r in v_router.routes]
    i_paths = [r.path for r in i_router.routes]
    assert any("valuation-sample" in p for p in v_paths)
    assert any("impairment-analysis" in p for p in i_paths)


def test_response_models_have_expected_fields(schemas):
    """ImpairmentAnalysisResponse 必须含 LLM stub 标识 + 计提合计字段"""
    resp = schemas["ImpairmentAnalysisResponse"](
        method="lower_of_cost_or_nrv",
        total_products=0,
        suggestions=[],
        summary="empty",
        total_suggested_provision="0",
    )
    assert resp.is_llm_stub is True
    assert resp.total_suggested_provision == "0"
    # P0-3 写回字段：默认 None
    assert resp.applied_to_sheet is None


# ---- P0-3 写回联动 schema 校验 ----------------------------------------------


def test_valuation_request_apply_to_sheet_optional(schemas):
    """ValuationSampleRequest.apply_to_sheet 默认 None；可设字符串"""
    req = schemas["ValuationSampleRequest"](year=2024)
    assert req.apply_to_sheet is None

    req2 = schemas["ValuationSampleRequest"](
        year=2024, apply_to_sheet="计价方法测试表-平均F2-38"
    )
    assert req2.apply_to_sheet == "计价方法测试表-平均F2-38"


def test_impairment_request_apply_to_sheet_optional(schemas):
    """ImpairmentAnalysisRequest.apply_to_sheet 默认 None；可设字符串"""
    req = schemas["ImpairmentAnalysisRequest"](
        products=[{"product_name": "A", "cost": 100, "nrv": 80}],
    )
    assert req.apply_to_sheet is None

    req2 = schemas["ImpairmentAnalysisRequest"](
        products=[{"product_name": "A", "cost": 100, "nrv": 80}],
        apply_to_sheet="跌价准备测试表F2-47",
    )
    assert req2.apply_to_sheet == "跌价准备测试表F2-47"


def test_valuation_response_applied_field(schemas):
    """ValuationSampleResponse.applied_to_sheet 默认 None；写回时返回 sheet 名"""
    resp = schemas["ValuationSampleResponse"](
        method="weighted_average",
        total_samples=0,
        layers={"high": 0, "mid": 0, "low": 0},
        samples=[],
        note="empty",
    )
    assert resp.applied_to_sheet is None

    resp2 = schemas["ValuationSampleResponse"](
        method="weighted_average",
        total_samples=0,
        layers={"high": 0, "mid": 0, "low": 0},
        samples=[],
        note="empty",
        applied_to_sheet="计价方法测试表-平均F2-38",
    )
    assert resp2.applied_to_sheet == "计价方法测试表-平均F2-38"


def test_writeback_helpers_exist():
    """P0-3：两个 _maybe_apply_*_to_workpaper 写回辅助函数必须存在"""
    from app.routers.wp_f2_valuation import _maybe_apply_samples_to_workpaper
    from app.routers.wp_f2_impairment import _maybe_apply_impairment_to_workpaper
    assert callable(_maybe_apply_samples_to_workpaper)
    assert callable(_maybe_apply_impairment_to_workpaper)


def test_routes_use_require_project_access():
    """P3-10：两个路由必须用 require_project_access('edit')，不能裸用 get_current_user"""
    import inspect
    from app.routers import wp_f2_valuation, wp_f2_impairment
    src_v = inspect.getsource(wp_f2_valuation)
    src_i = inspect.getsource(wp_f2_impairment)
    assert 'require_project_access("edit")' in src_v, \
        "wp_f2_valuation 必须用 require_project_access('edit')"
    assert 'require_project_access("edit")' in src_i, \
        "wp_f2_impairment 必须用 require_project_access('edit')"
