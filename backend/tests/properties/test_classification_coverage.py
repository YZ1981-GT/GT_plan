"""Property 1 PBT: 9 类全覆盖归类 → componentType 路由

**Validates: Requirements 1.2 + 3.0.1 + 3.9**

四条核心 property（hypothesis 生成 (sheet_name, sheet_features)）：

- Property 1a: 任意 (sheet_name, features) → classify_sheet 返回 class_code
  匹配 `^[A-I]-` 白名单 **或** `_pending`（非空输入永远有归属，禁止 None）
- Property 1b: 任意 classify_sheet 输出 class_code（非 _pending） →
  derive_component_type 返回值落在 VALID_COMPONENT_TYPES 白名单（禁止 Univer 兜底）
- Property 1c: D- 子类全部映射到 5 个 d-form-* componentType 之一
- Property 1d: A/B/C/E/F/G/H/I 类映射到各自非 d-form-* componentType 且幂等
  （同一 class_code 多次 derive 结果恒等）

Spec: `.kiro/specs/workpaper-html-renderer/`
"""

from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings as h_settings
from hypothesis import strategies as st

# ─── 让 backend/scripts/analyze_wp_templates.py 可被 import ──────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from analyze_wp_templates import classify_sheet  # noqa: E402

from app.services.wp_classification_service import (  # noqa: E402
    VALID_COMPONENT_TYPES,
    ClassificationNotFoundError,
    ClassificationResult,
    derive_component_type,
)


# ─── 白名单常量 ───────────────────────────────────────────────────────────────

VALID_CLASS_PREFIXES: set[str] = {
    "A-", "B-", "C-", "D-", "E-", "F-", "G-", "H-", "I-",
}
PENDING_MARKER = "_pending"

CLASS_PREFIX_RE = re.compile(r"^[A-I]-")

# d-form-* 子类型（D 类专属）
D_FORM_COMPONENT_TYPES: set[str] = {
    "d-form-table",
    "d-form-paragraph",
    "d-form-qa",
    "d-form-confirmation",
    "d-form-review",
}

# 非 D 类前缀 → 期望 componentType 映射（用于 Property 1d 幂等性 + 路由确定性）
NON_D_EXPECTED: dict[str, str] = {
    "A-": "a-program-console",
    "B-": "b-index",
    "C-": "c-note-table",
    "E-": "e-control-test",
    "F-": "univer",
    "G-": "univer",
    "H-": "h-static-doc",
    "I-": "skip",
}


# ─── Hypothesis Strategies ───────────────────────────────────────────────────

# 中文常见审计 sheet 命名词汇（智能受限，覆盖真实模板里 80%+ 命名模式）
_AUDIT_TERMS: list[str] = [
    # A 程序表关键词
    "实质性程序表", "替代程序", "审计程序", "程序表", "完成阶段", "业务约定",
    # B 底稿目录
    "底稿目录", "目录", "审计标识",
    # C 附注披露
    "附注披露", "披露信息",
    # D 检查/政策/业务模式/函证/盘点/访谈/复核
    "检查表", "业务模式", "会计政策", "政策检查", "函证", "询证", "回函",
    "盘点", "监盘", "访谈", "调查问卷", "复核记录", "项目经理复核",
    "风险评估", "互转审核", "核查清单", "管理层凌驾", "关联方",
    "业务承接", "业务保持", "前任注册会计师", "组成部分",
    # E 控制测试
    "控制测试", "评价控制偏差", "控制测试汇总",
    # F 数据表
    "审定表", "明细表", "分析表", "调整分录", "汇总表", "重要性",
    "CFS", "现金流量", "余额调节", "倒轧",
    # G 测算
    "测算", "测试", "初始计量", "后续计量", "追溯调整", "公允价值",
    "三阶段划分", "前瞻性调整",
    # H 辅助
    "修订说明", "编制说明", "填表说明", "文号规则", "参考-",
    "相关资源", "准则", "指南", "IPO 提示", "环境法规", "提示",
    # I 占位
    "GT_Custom", "Data", "Lists", "Instructions", "temp_", "参数",
    "Sheet1", "List", "不归档", "选项清单列表",
    # 编码 + 序号 + 拼接元素
    "D2A", "E1A", "G7A", "F2A", "S15", "S3", "S10", "B22A", "C21",
    "A1-13", "A30", "A31", "B19", "B50", "B60", "N5", "J3",
    # 通用串接
    "应收账款", "存货", "固定资产", "货币资金", "其他应收款",
    "权利和义务", "每股收益", "套期活动", "数据资产",
    # 边缘 case
    "0000", "Sheet", "(2)", " ",
]

# sheet_name strategy: 1~3 个 term 拼接 + 偶尔加纯英数后缀（模拟 D2A / S15-1 等）
_term_st = st.sampled_from(_AUDIT_TERMS)
_suffix_st = st.text(
    alphabet="ABCDEFGHIJKLMNS0123456789-",
    min_size=0,
    max_size=6,
)

st_sheet_name = st.builds(
    lambda terms, suffix: "".join(terms) + suffix,
    st.lists(_term_st, min_size=1, max_size=3),
    _suffix_st,
).filter(lambda s: s.strip() != "")

# sheet_features strategy: 模拟 extract_sheet_features() 输出的 dict
st_sheet_features = st.fixed_dictionaries({
    "max_row": st.integers(min_value=0, max_value=500),
    "max_col": st.integers(min_value=0, max_value=50),
    "merged_count": st.integers(min_value=0, max_value=200),
    "merged_density": st.floats(min_value=0.0, max_value=2.0, allow_nan=False),
    "long_text_cells": st.integers(min_value=0, max_value=100),
    "formula_cells": st.integers(min_value=0, max_value=200),
    "has_step_words": st.booleans(),
    "has_index_triplet": st.booleans(),
    "has_assertion_5": st.booleans(),
    "first_col_samples": st.lists(
        st.text(alphabet="一二三四五六七八九十0123456789、序号内容索引号", max_size=20),
        min_size=0,
        max_size=10,
    ),
})


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_classification_result(class_code: str | None) -> ClassificationResult:
    """Wrap class_code into ClassificationResult for derive_component_type()."""
    return ClassificationResult(
        wp_code="D2",
        sheet_name="prop_test",
        class_code=class_code,
        class_=class_code,
        scope="standalone",
        is_real_workpaper=True,
        delegated_module=None,
        render_schema_path=None,
        template_version_id=uuid.uuid4(),
        has_override=False,
    )


def _is_pending(class_code: str | None) -> bool:
    return class_code is None or class_code == PENDING_MARKER


# ─── Property 1a: classify_sheet 输出落在白名单或 _pending ──────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(sheet_name=st_sheet_name, features=st_sheet_features)
def test_property_1a_classify_returns_whitelist_or_pending(
    sheet_name: str, features: dict
) -> None:
    """**Validates: Requirements 1.2** — classify_sheet 永远返回有归属

    任意 (sheet_name, features) →
        class_code matches `^[A-I]-` (合法归类) OR class_code == "_pending"
    且 reason 非空。
    """
    class_code, reason = classify_sheet(sheet_name, features)

    # class_code 必须是字符串（非 None / 非空）
    assert isinstance(class_code, str), (
        f"classify_sheet returned non-str class_code={class_code!r} "
        f"for sheet_name={sheet_name!r}"
    )
    assert class_code != "", (
        f"classify_sheet returned empty class_code for sheet_name={sheet_name!r}"
    )

    # 必须满足 ^[A-I]- 白名单或 _pending
    is_valid_prefix = CLASS_PREFIX_RE.match(class_code) is not None
    is_pending = class_code == PENDING_MARKER
    assert is_valid_prefix or is_pending, (
        f"classify_sheet returned class_code={class_code!r} which is neither "
        f"in {VALID_CLASS_PREFIXES} prefix whitelist nor '_pending' "
        f"(sheet_name={sheet_name!r})"
    )

    # reason 必须非空（决策可追踪）
    assert isinstance(reason, str) and reason, (
        f"classify_sheet returned empty reason for sheet_name={sheet_name!r}"
    )


# ─── Property 1b: derive_component_type 返回值落在 VALID_COMPONENT_TYPES ────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(sheet_name=st_sheet_name, features=st_sheet_features)
def test_property_1b_derive_component_in_whitelist(
    sheet_name: str, features: dict
) -> None:
    """**Validates: Requirements 3.9** — 禁止 Univer 兜底，class → componentType 必落白名单

    classify_sheet 返回非 _pending → derive_component_type 必须返回
    VALID_COMPONENT_TYPES 中的某值（绝不返回空 / None / 白名单外字符串）。
    _pending 输入 → derive 必抛 ClassificationNotFoundError（禁止隐式降级到 univer）。
    """
    class_code, _ = classify_sheet(sheet_name, features)
    cls_result = _make_classification_result(class_code)

    if _is_pending(class_code):
        # _pending → 必须抛异常，不能静默回退
        with pytest.raises(ClassificationNotFoundError):
            derive_component_type(cls_result)
    else:
        component_type = derive_component_type(cls_result)
        assert component_type in VALID_COMPONENT_TYPES, (
            f"derive_component_type({class_code!r}) returned {component_type!r} "
            f"which is not in VALID_COMPONENT_TYPES={VALID_COMPONENT_TYPES}"
        )
        # 非空非 None
        assert isinstance(component_type, str) and component_type
        # 不允许返回空串 / None / 'pending'
        assert component_type not in ("", "pending", "fallback"), (
            f"componentType={component_type!r} 表示降级，违反 Requirement 3.9"
        )


# ─── Property 1c: D- 子类映射到 5 个 d-form-* ────────────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(sheet_name=st_sheet_name, features=st_sheet_features)
def test_property_1c_d_class_maps_to_d_form_subset(
    sheet_name: str, features: dict
) -> None:
    """**Validates: Requirements 1.2** — D 类 5 子模式路由

    classify_sheet 返回 D- 开头 → derive_component_type 必返回
    {d-form-table, d-form-paragraph, d-form-qa, d-form-confirmation, d-form-review}
    五个子类型之一，不会回到非 d-form-* 的 componentType。
    """
    class_code, _ = classify_sheet(sheet_name, features)

    if not class_code.startswith("D-"):
        return  # 非 D 类不验证此 property

    cls_result = _make_classification_result(class_code)
    component_type = derive_component_type(cls_result)

    assert component_type in D_FORM_COMPONENT_TYPES, (
        f"D 类 class_code={class_code!r} 路由到 component={component_type!r}，"
        f"应在 d-form-* 5 子类内：{D_FORM_COMPONENT_TYPES}"
    )


# ─── Property 1d: 非 D 类映射确定且幂等 ──────────────────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(sheet_name=st_sheet_name, features=st_sheet_features)
def test_property_1d_non_d_class_routing_deterministic_idempotent(
    sheet_name: str, features: dict
) -> None:
    """**Validates: Requirements 1.2 + 3.0.1** — 非 D 类路由决定性 + 幂等

    1. 非 D 类 class_code（A/B/C/E/F/G/H/I）映射到 NON_D_EXPECTED 中预期 componentType
    2. 多次调用 derive_component_type 结果恒等（无副作用，纯函数）
    """
    class_code, _ = classify_sheet(sheet_name, features)

    if _is_pending(class_code) or class_code.startswith("D-"):
        return  # _pending 与 D 类由其他 property 验证

    prefix = class_code[:2]
    assert prefix in NON_D_EXPECTED, (
        f"非 D 类 class_code={class_code!r} 前缀 {prefix!r} 不在预期 "
        f"NON_D_EXPECTED={list(NON_D_EXPECTED.keys())}"
    )
    expected_component = NON_D_EXPECTED[prefix]

    cls_result = _make_classification_result(class_code)

    # 1. 决定性：classify_sheet 输出对应的 componentType 与 NON_D_EXPECTED 一致
    component_type = derive_component_type(cls_result)
    assert component_type == expected_component, (
        f"class_code={class_code!r} 期望路由到 {expected_component!r}，"
        f"实际 {component_type!r}"
    )
    # 不会落入 d-form-* 命名空间
    assert component_type not in D_FORM_COMPONENT_TYPES, (
        f"非 D 类不应路由到 d-form-* 子类型，class_code={class_code!r}, "
        f"component={component_type!r}"
    )

    # 2. 幂等：多次调用结果恒等
    again = derive_component_type(_make_classification_result(class_code))
    once_more = derive_component_type(cls_result)
    assert component_type == again == once_more, (
        f"derive_component_type 不幂等，class_code={class_code!r}: "
        f"{component_type!r} vs {again!r} vs {once_more!r}"
    )
