"""Property 9 PBT: 行业特定 sheet 可见性派生

**Validates: Requirements 6.5 待决策点 4 选项 A**

按 `project.industry_type` 自动启用行业特定底稿（推荐方案）：

- **H5 油气资产** — 仅 industry_type='oil_gas' 项目可见
- **H7 生产性生物资产** — 仅 industry_type='agriculture' 项目可见
- **M7 专项储备** — 仅特定行业（mining / construction / 安全生产相关）可见
- 默认行业（generic / manufacturing / service / etc）→ 这些 sheet 隐藏
- 所有非行业特定底稿 → 全行业可见

七条核心 property（hypothesis 生成 (industry_type, sheet_industry_tag)）：

- Property 9a (非行业特定全可见): wp_code 不在 INDUSTRY_SPECIFIC_RULES 时
  derive_sheet_visibility 对所有 industry_type 返回 True。
- Property 9b (行业特定匹配可见): wp_code 在 rules + industry_type 在
  rule.industry_types 时 → True。
- Property 9c (行业特定不匹配隐藏): wp_code 在 rules + industry_type 不在
  rule.industry_types 时 → False。
- Property 9d (None industry 行业特定隐藏): wp_code 在 rules +
  industry_type=None → False（项目无行业即隐藏行业特定 sheet）。
- Property 9e (None industry 通用可见): wp_code 不在 rules +
  industry_type=None → True（通用底稿不依赖行业）。
- Property 9f (确定性纯函数): 同一 (wp_code, industry_type) 多次调用结果恒等。
- Property 9g (互斥布尔): 任意输入返回值严格 ∈ {True, False}（绝不返回
  None / int / 其他）。

Spec: ``.kiro/specs/workpaper-html-renderer/`` §6.5
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings as h_settings
from hypothesis import strategies as st

# ─── 行业特定底稿规则表（design §10.2 列举） ─────────────────────────────────

INDUSTRY_SPECIFIC_RULES: dict[str, dict[str, list[str]]] = {
    # H5 油气资产
    "H5": {"industry_types": ["oil_gas"]},
    # H7 生产性生物资产
    "H7": {"industry_types": ["agriculture"]},
    # M7 专项储备（采矿 / 建筑施工 / 高危行业含安全生产费）
    "M7": {
        "industry_types": [
            "mining",
            "construction",
            "manufacturing_with_safety_reserve",
        ]
    },
}

# 全部已知行业类型（用于 hypothesis sampled_from）
_ALL_INDUSTRY_TYPES: list[str | None] = [
    None,  # 项目未填行业
    "oil_gas",
    "agriculture",
    "mining",
    "construction",
    "manufacturing_with_safety_reserve",
    "manufacturing",
    "service",
    "finance",
    "real_estate",
    "generic",
]

# 通用 wp_code 样本（不在 INDUSTRY_SPECIFIC_RULES）
_GENERIC_WP_CODES: list[str] = [
    "D2", "A1", "B12", "C5", "E1", "F2", "G3", "H1", "H2", "H8",
    "I4", "J3", "K8", "L4", "M5", "N3", "S15",
]

# 行业特定 wp_code 样本（必须落在 INDUSTRY_SPECIFIC_RULES）
_INDUSTRY_SPECIFIC_WP_CODES: list[str] = list(INDUSTRY_SPECIFIC_RULES.keys())


# ─── Helper function（被测对象） ─────────────────────────────────────────────


def derive_sheet_visibility(wp_code: str, industry_type: str | None) -> bool:
    """For wp_code, return True if visible to project with industry_type.

    规则（Requirements 6.5 选项 A）：
    - wp_code in INDUSTRY_SPECIFIC_RULES → 仅 industry_type 匹配规则时可见
    - wp_code in INDUSTRY_SPECIFIC_RULES + industry_type=None → 隐藏（项目无行业）
    - wp_code 不在规则表 → 全行业可见（通用底稿）
    """
    rule = INDUSTRY_SPECIFIC_RULES.get(wp_code)
    if rule is None:
        # 通用底稿 → 全行业可见，包括 industry_type=None
        return True
    if industry_type is None:
        # 行业特定底稿 + 项目无行业信息 → 默认隐藏
        return False
    return industry_type in rule["industry_types"]


# ─── Hypothesis Strategies ───────────────────────────────────────────────────

# 通用 wp_code（不在行业特定规则表）
st_generic_wp_code = st.sampled_from(_GENERIC_WP_CODES)

# 行业特定 wp_code（落在规则表）
st_industry_specific_wp_code = st.sampled_from(_INDUSTRY_SPECIFIC_WP_CODES)

# 任意 wp_code（混合通用 + 行业特定）
st_wp_code = st.one_of(st_generic_wp_code, st_industry_specific_wp_code)

# industry_type 全集（含 None）
st_industry_type = st.sampled_from(_ALL_INDUSTRY_TYPES)

# (wp_code, industry_type) 配对
st_pair = st.tuples(st_wp_code, st_industry_type)


# ─── Property 9a: 非行业特定 wp_code → 全行业可见 ──────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(wp_code=st_generic_wp_code, industry_type=st_industry_type)
def test_property_9a_generic_wp_visible_to_all_industries(
    wp_code: str, industry_type: str | None
) -> None:
    """**Validates: Requirements 6.5 选项 A** — 通用底稿全行业可见

    wp_code 不在 INDUSTRY_SPECIFIC_RULES → derive_sheet_visibility 对所有
    industry_type（含 None / oil_gas / agriculture / 任意行业）返回 True。
    """
    assert wp_code not in INDUSTRY_SPECIFIC_RULES, (
        f"测试假设错误：wp_code={wp_code!r} 不应在行业特定规则表"
    )

    visible = derive_sheet_visibility(wp_code, industry_type)
    assert visible is True, (
        f"通用底稿 wp_code={wp_code!r} 应对 industry_type={industry_type!r} "
        f"可见，实际 visible={visible!r}"
    )


# ─── Property 9b: 行业特定 + 行业匹配 → 可见 ──────────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(wp_code=st_industry_specific_wp_code)
def test_property_9b_industry_match_visible(wp_code: str) -> None:
    """**Validates: Requirements 6.5 选项 A** — 行业特定底稿匹配行业可见

    wp_code 在 INDUSTRY_SPECIFIC_RULES + industry_type 落在
    rule.industry_types 列表内 → 返回 True。
    """
    rule = INDUSTRY_SPECIFIC_RULES[wp_code]
    for industry_type in rule["industry_types"]:
        visible = derive_sheet_visibility(wp_code, industry_type)
        assert visible is True, (
            f"行业特定 wp_code={wp_code!r} + 匹配行业 industry_type="
            f"{industry_type!r} 应可见，实际 {visible!r}"
        )


# ─── Property 9c: 行业特定 + 行业不匹配 → 隐藏 ────────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(wp_code=st_industry_specific_wp_code, industry_type=st_industry_type)
def test_property_9c_industry_mismatch_hidden(
    wp_code: str, industry_type: str | None
) -> None:
    """**Validates: Requirements 6.5 选项 A** — 行业特定底稿不匹配行业隐藏

    wp_code 在 INDUSTRY_SPECIFIC_RULES + industry_type 不在
    rule.industry_types 且非 None → 返回 False。
    """
    rule = INDUSTRY_SPECIFIC_RULES[wp_code]
    if industry_type is None or industry_type in rule["industry_types"]:
        return  # 由 9b / 9d 验证

    visible = derive_sheet_visibility(wp_code, industry_type)
    assert visible is False, (
        f"行业特定 wp_code={wp_code!r} + 不匹配行业 industry_type="
        f"{industry_type!r}（rule={rule['industry_types']!r}）应隐藏，"
        f"实际 {visible!r}"
    )


# ─── Property 9d: 行业特定 + industry_type=None → 隐藏 ────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(wp_code=st_industry_specific_wp_code)
def test_property_9d_none_industry_hides_industry_specific(
    wp_code: str,
) -> None:
    """**Validates: Requirements 6.5 选项 A** — 项目无行业时隐藏行业特定底稿

    wp_code 在 INDUSTRY_SPECIFIC_RULES + industry_type=None → 返回 False。
    项目立项未填 industry_type 时，行业特定底稿默认隐藏（避免误启用）。
    """
    visible = derive_sheet_visibility(wp_code, None)
    assert visible is False, (
        f"行业特定 wp_code={wp_code!r} + industry_type=None 应隐藏，"
        f"实际 {visible!r}"
    )


# ─── Property 9e: 通用 + industry_type=None → 可见 ────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(wp_code=st_generic_wp_code)
def test_property_9e_none_industry_keeps_generic_visible(
    wp_code: str,
) -> None:
    """**Validates: Requirements 6.5 选项 A** — 项目无行业时通用底稿仍可见

    wp_code 不在 INDUSTRY_SPECIFIC_RULES + industry_type=None → 返回 True。
    通用底稿不依赖行业属性，未填 industry_type 不影响可见性。
    """
    visible = derive_sheet_visibility(wp_code, None)
    assert visible is True, (
        f"通用 wp_code={wp_code!r} + industry_type=None 应可见，"
        f"实际 {visible!r}"
    )


# ─── Property 9f: 确定性纯函数 ───────────────────────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(pair=st_pair)
def test_property_9f_deterministic_pure_function(
    pair: tuple[str, str | None],
) -> None:
    """**Validates: Requirements 6.5 选项 A** — derive_sheet_visibility 纯函数

    同一 (wp_code, industry_type) 多次调用结果恒等，无副作用。
    """
    wp_code, industry_type = pair

    v1 = derive_sheet_visibility(wp_code, industry_type)
    v2 = derive_sheet_visibility(wp_code, industry_type)
    v3 = derive_sheet_visibility(wp_code, industry_type)

    assert v1 == v2 == v3, (
        f"derive_sheet_visibility 不幂等：{v1!r} / {v2!r} / {v3!r} "
        f"(wp_code={wp_code!r}, industry_type={industry_type!r})"
    )


# ─── Property 9g: 互斥布尔（永远 True 或 False） ──────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(pair=st_pair)
def test_property_9g_strict_boolean_output(
    pair: tuple[str, str | None],
) -> None:
    """**Validates: Requirements 6.5 选项 A** — 输出严格布尔

    任意 (wp_code, industry_type) → derive_sheet_visibility 严格返回
    True / False，绝不返回 None / int / str / 其他类型。
    """
    wp_code, industry_type = pair
    result = derive_sheet_visibility(wp_code, industry_type)

    assert isinstance(result, bool), (
        f"derive_sheet_visibility 应返回 bool，实际 "
        f"{type(result).__name__}: {result!r} "
        f"(wp_code={wp_code!r}, industry_type={industry_type!r})"
    )
    assert result is True or result is False, (
        f"derive_sheet_visibility 应严格 ∈ {{True, False}}，"
        f"实际 {result!r}"
    )


# ─── 单元测试：边界 case（PBT 互补） ─────────────────────────────────────


def test_h5_oil_gas_visible_only_to_oil_gas() -> None:
    """H5 油气资产仅 oil_gas 行业可见"""
    assert derive_sheet_visibility("H5", "oil_gas") is True
    assert derive_sheet_visibility("H5", "agriculture") is False
    assert derive_sheet_visibility("H5", "mining") is False
    assert derive_sheet_visibility("H5", "manufacturing") is False
    assert derive_sheet_visibility("H5", None) is False


def test_h7_agriculture_visible_only_to_agriculture() -> None:
    """H7 生产性生物资产仅 agriculture 行业可见"""
    assert derive_sheet_visibility("H7", "agriculture") is True
    assert derive_sheet_visibility("H7", "oil_gas") is False
    assert derive_sheet_visibility("H7", "manufacturing") is False
    assert derive_sheet_visibility("H7", None) is False


def test_m7_safety_reserve_visible_to_3_industries() -> None:
    """M7 专项储备对采矿/建筑/含安全生产费的制造业可见"""
    assert derive_sheet_visibility("M7", "mining") is True
    assert derive_sheet_visibility("M7", "construction") is True
    assert derive_sheet_visibility(
        "M7", "manufacturing_with_safety_reserve"
    ) is True
    # 普通制造业不可见
    assert derive_sheet_visibility("M7", "manufacturing") is False
    assert derive_sheet_visibility("M7", "service") is False
    assert derive_sheet_visibility("M7", "agriculture") is False
    assert derive_sheet_visibility("M7", None) is False


def test_generic_wp_visible_to_all_industries() -> None:
    """通用 wp_code（D2/A1/F2/etc）对所有行业可见"""
    for wp_code in ["D2", "A1", "F2", "B12", "M5", "N3"]:
        for industry in [None, "oil_gas", "agriculture", "mining",
                         "manufacturing", "service", "finance"]:
            assert derive_sheet_visibility(wp_code, industry) is True, (
                f"通用 wp_code={wp_code!r} 应对 industry={industry!r} 可见"
            )


def test_unknown_industry_hides_industry_specific() -> None:
    """未知行业（如 ``oil_and_gas`` 写错）→ 行业特定底稿隐藏（保守）"""
    assert derive_sheet_visibility("H5", "oil_and_gas") is False  # 拼写错误
    assert derive_sheet_visibility("H5", "OIL_GAS") is False  # 大小写敏感
    assert derive_sheet_visibility("H7", "Agriculture") is False
