"""Property 7 PBT: 项目实例覆盖与 scope 路由

**Validates: Requirements 3.0.3（项目实例层级 L5）+ 3.0.5（合并/母公司剔除 scope 字段路由规则）**

五条核心 property（hypothesis 生成 (override, base_classification, base_schema)）：

- Property 7a (确定性): `merge_with_override(base, override)` 是纯函数 ——
  对同一 (base, override) 多次调用返回 deep-equal 的结果，且不修改原 base / override。
- Property 7b (override 优先): 当 override.class_override 非空时，
  应用覆盖后的 ClassificationResult.class_code 等于 class_override，scope_override 同理。
- Property 7c (scope 路由): 合并后 scope='consolidated' → componentType='delegate-consolidation'；
  scope='parent_only' → 'delegate-parent-view'；scope ∈ {'standalone','both'} → 9 类
  routing（落在 VALID_COMPONENT_TYPES 白名单）。
- Property 7d (深度合并): 嵌套 schema dict 中 override 仅替换指定路径，
  同级未提及的兄弟 key 不会被擦掉（递归合并）。
- Property 7e (None / 空 dict 透传): override is None 或 {} 时，merge 返回 base 不动。

Spec: `.kiro/specs/workpaper-html-renderer/`

Notes:
- 纯函数测试，不依赖 DB / FastAPI 上下文。
- 使用 hypothesis `max_examples=50` + `suppress_health_check=[HealthCheck.too_slow]`（中文/嵌套 dict 生成稍慢）。
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings as h_settings
from hypothesis import strategies as st

from app.services.wp_classification_service import (
    VALID_COMPONENT_TYPES,
    ClassificationNotFoundError,
    ClassificationResult,
    derive_component_type,
)
from app.services.wp_render_schema_service import WpRenderSchemaService


# ─── 常量 ──────────────────────────────────────────────────────────────────

# 与 backend 9 类映射保持一致（含 D 类 sub-routing 全集）
_NON_D_CLASS_CODES: list[str] = [
    "A-程序表",
    "A-替代程序",
    "B-目录",
    "C-附注",
    "E-控制测试",
    "F-数据表",
    "G-测算",
    "H-辅助说明",
    "I-占位",
]

_D_CLASS_CODES: list[str] = [
    "D-检查表",          # 默认 → d-form-table
    "D-政策检查",        # → d-form-paragraph
    "D-业务模式",        # → d-form-qa
    "D-函证",            # → d-form-confirmation
    "D-盘点",            # → d-form-confirmation
    "D-访谈",            # → d-form-confirmation
    "D-询证",            # → d-form-confirmation
    "D-复核记录",        # → d-form-review
    "D-复核",            # → d-form-review
]

_ALL_CLASS_CODES: list[str] = _NON_D_CLASS_CODES + _D_CLASS_CODES

_VALID_SCOPES: list[str] = ["standalone", "consolidated", "parent_only", "both"]


# ─── Hypothesis Strategies ───────────────────────────────────────────────

# 简单 schema 值（叶子）：标量或简单 list
_st_leaf: st.SearchStrategy[Any] = st.one_of(
    st.text(min_size=0, max_size=20),
    st.integers(min_value=-1000, max_value=1000),
    st.booleans(),
    st.none(),
    st.lists(st.text(max_size=8), max_size=3),
)


def _st_nested_dict(max_depth: int = 3) -> st.SearchStrategy[dict]:
    """Recursively-bounded nested dict strategy.

    深度受限 (默认 3 层) + 每层 ≤ 4 key，避免 hypothesis health check 触发。
    """
    keys = st.sampled_from([
        "fixed_cells", "dynamic_table", "static_text", "formulas",
        "merged_cells", "cross_refs",
        "A1", "A2", "A3", "B1", "C1", "H3",
        "wp_code", "template_version", "component_type",
        "sheets", "rows", "columns", "config",
    ])
    return st.recursive(
        st.dictionaries(keys, _st_leaf, max_size=4),
        lambda children: st.dictionaries(keys, st.one_of(_st_leaf, children), max_size=4),
        max_leaves=8,
    )


st_schema_dict = _st_nested_dict()


# 基础 classification dict（模拟 WorkpaperSheetClassification 行）
st_base_classification = st.fixed_dictionaries({
    "wp_code": st.sampled_from(["D2", "D2A", "B12", "E1A", "G7A", "S15"]),
    "sheet_name": st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
    "class_code": st.sampled_from(_ALL_CLASS_CODES),
    "scope": st.sampled_from(_VALID_SCOPES),
    "is_real_workpaper": st.booleans(),
    "delegated_module": st.one_of(st.none(), st.sampled_from([
        "consolidation_hub", "parent_view", "consolidation_index",
    ])),
})


# Override dict（模拟 ProjectWorkpaperSheetOverride 行的可选字段）
st_override = st.fixed_dictionaries({
    "class_override": st.one_of(st.none(), st.sampled_from(_ALL_CLASS_CODES)),
    "scope_override": st.one_of(st.none(), st.sampled_from(_VALID_SCOPES)),
    "schema_override": st.one_of(st.none(), st_schema_dict),
})


# ─── Helpers — 模拟 router/服务层逻辑（纯函数） ─────────────────────────

def _apply_classification_override(
    base: dict, override: dict | None
) -> ClassificationResult:
    """Mirror WpClassificationService.get_classification merge logic.

    应用项目级覆盖：override 中非 None 字段覆盖 base 中对应字段。
    """
    if override is None:
        override = {}

    class_override = override.get("class_override")
    scope_override = override.get("scope_override")
    schema_override = override.get("schema_override")

    effective_class = class_override if class_override else base["class_code"]
    effective_scope = scope_override if scope_override else base["scope"]
    has_override = any(
        v is not None for v in (class_override, scope_override, schema_override)
    )

    return ClassificationResult(
        wp_code=base["wp_code"],
        sheet_name=base["sheet_name"],
        class_code=effective_class,
        class_=effective_class,
        scope=effective_scope,
        is_real_workpaper=base.get("is_real_workpaper", True),
        delegated_module=base.get("delegated_module"),
        render_schema_path=None,
        template_version_id=uuid.uuid4(),
        has_override=has_override,
    )


def _route_to_component_type(classification: ClassificationResult) -> str:
    """Mirror render-config router scope routing + 9 类 fallback.

    - scope='consolidated' → 'delegate-consolidation'
    - scope='parent_only'  → 'delegate-parent-view'
    - scope ∈ {'standalone','both'} → derive_component_type (9 类)
    """
    if classification.scope == "consolidated":
        return "delegate-consolidation"
    if classification.scope == "parent_only":
        return "delegate-parent-view"
    return derive_component_type(classification)


# ─── Property 7a: merge_with_override 确定性（纯函数） ──────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(base=st_schema_dict, override=st.one_of(st.none(), st_schema_dict))
def test_property_7a_merge_with_override_is_pure(
    base: dict, override: dict | None
) -> None:
    """**Validates: Requirements 3.0.3** — merge_with_override 纯函数确定性

    1. 对同一 (base, override) 多次调用返回 deep-equal 结果
    2. 不修改原 base / override（无副作用）
    """
    service = WpRenderSchemaService()

    base_snapshot = copy.deepcopy(base)
    override_snapshot = copy.deepcopy(override)

    result1 = service.merge_with_override(base, override)
    result2 = service.merge_with_override(base, override)
    result3 = service.merge_with_override(base, override)

    # 1. 三次调用结果 deep-equal
    assert result1 == result2 == result3, (
        "merge_with_override 不是纯函数：多次调用结果不同 "
        f"(base={base!r}, override={override!r})"
    )

    # 2. 原 base / override 未被修改（无副作用）
    assert base == base_snapshot, "merge_with_override 修改了原 base 字典"
    assert override == override_snapshot, (
        "merge_with_override 修改了原 override 字典"
    )


# ─── Property 7b: class_override 优先于 base.class_code ──────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(base=st_base_classification, override=st_override)
def test_property_7b_override_class_wins(
    base: dict, override: dict
) -> None:
    """**Validates: Requirements 3.0.3** — override 优先级

    当 override.class_override 非空 → 合并结果 class_code == class_override；
    当 override.scope_override 非空 → 合并结果 scope == scope_override；
    否则保留 base 字段。
    """
    result = _apply_classification_override(base, override)

    # class_code 优先级：override.class_override > base.class_code
    if override["class_override"] is not None:
        assert result.class_code == override["class_override"], (
            f"override.class_override={override['class_override']!r} 应优先于 "
            f"base.class_code={base['class_code']!r}，实际 result={result.class_code!r}"
        )
        # class_ 与 class_code 同步
        assert result.class_ == override["class_override"]
    else:
        assert result.class_code == base["class_code"], (
            "override.class_override is None 时应保留 base.class_code"
        )

    # scope 优先级：override.scope_override > base.scope
    if override["scope_override"] is not None:
        assert result.scope == override["scope_override"], (
            f"override.scope_override={override['scope_override']!r} 应优先于 "
            f"base.scope={base['scope']!r}，实际 result={result.scope!r}"
        )
    else:
        assert result.scope == base["scope"], (
            "override.scope_override is None 时应保留 base.scope"
        )

    # has_override 标记一致性
    expected_has_override = any(
        override[k] is not None
        for k in ("class_override", "scope_override", "schema_override")
    )
    assert result.has_override == expected_has_override


# ─── Property 7c: scope 路由正确（含 9 类白名单） ────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(base=st_base_classification, override=st_override)
def test_property_7c_scope_routing_correct(
    base: dict, override: dict
) -> None:
    """**Validates: Requirements 3.0.5** — scope 路由

    - scope='consolidated' → componentType='delegate-consolidation'
    - scope='parent_only'  → componentType='delegate-parent-view'
    - scope ∈ {'standalone','both'} → componentType ∈ VALID_COMPONENT_TYPES (9 类)

    每条分支幂等：多次调用 _route_to_component_type 结果恒等。
    """
    classification = _apply_classification_override(base, override)
    effective_scope = classification.scope

    component_type = _route_to_component_type(classification)

    if effective_scope == "consolidated":
        assert component_type == "delegate-consolidation", (
            f"scope='consolidated' 应路由到 'delegate-consolidation'，"
            f"实际 {component_type!r}"
        )
    elif effective_scope == "parent_only":
        assert component_type == "delegate-parent-view", (
            f"scope='parent_only' 应路由到 'delegate-parent-view'，"
            f"实际 {component_type!r}"
        )
    else:
        # standalone / both → 走 9 类映射
        assert effective_scope in ("standalone", "both"), (
            f"未知 scope={effective_scope!r}（应为 4 个枚举值之一）"
        )
        assert component_type in VALID_COMPONENT_TYPES, (
            f"scope={effective_scope!r} 路由到 {component_type!r}，"
            f"不在 9 类白名单 {VALID_COMPONENT_TYPES}"
        )
        # 不会泄漏到 delegate-* 命名空间
        assert not component_type.startswith("delegate-"), (
            f"scope='{effective_scope}' 不应路由到 delegate-* 命名空间，"
            f"实际 {component_type!r}"
        )

    # 幂等：多次路由结果恒等（纯函数）
    again = _route_to_component_type(
        _apply_classification_override(base, override)
    )
    assert again == component_type, (
        f"scope 路由不幂等：{component_type!r} vs {again!r}"
    )


# ─── Property 7d: 深度合并保留同级兄弟 key ───────────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(
    base=st.dictionaries(
        st.text(min_size=1, max_size=8),
        st.one_of(_st_leaf, st_schema_dict),
        min_size=1,
        max_size=5,
    ),
    extra_keys=st.lists(
        st.text(min_size=1, max_size=8),
        min_size=1,
        max_size=3,
        unique=True,
    ),
    override_value=_st_leaf,
)
def test_property_7d_deep_merge_preserves_siblings(
    base: dict, extra_keys: list[str], override_value: Any
) -> None:
    """**Validates: Requirements 3.0.3** — 深度合并不擦兄弟 key

    构造嵌套 base = {'sheets': {'s1': {'fixed_cells': {<base 内容> + extra_keys}}}}，
    override 仅指定 fixed_cells.<one_extra_key>，验证：
    1. override 的目标 key 被覆盖
    2. 其他兄弟 key（含原 base 内容）保留不变
    3. base 上层结构（sheets / s1）保留
    """
    service = WpRenderSchemaService()

    # 构造嵌套结构：sheets.s1.fixed_cells = base + extra_keys
    fixed_cells = dict(base)  # 复制 base
    for k in extra_keys:
        # 避免与 base key 冲突
        if k not in fixed_cells:
            fixed_cells[k] = "sibling_value"

    nested_base = {
        "sheets": {
            "s1": {
                "fixed_cells": fixed_cells,
                "component_type": "a-program-console",
            },
            "s2": {"component_type": "b-index"},
        }
    }

    # 选第一个 extra key 作为 override 目标
    target_key = extra_keys[0] if extra_keys[0] not in base else f"{extra_keys[0]}_new"
    override = {
        "sheets": {
            "s1": {
                "fixed_cells": {target_key: override_value}
            }
        }
    }

    nested_base_snapshot = copy.deepcopy(nested_base)
    merged = service.merge_with_override(nested_base, override)

    # 1. 目标 key 被覆盖
    assert merged["sheets"]["s1"]["fixed_cells"][target_key] == override_value, (
        f"override 目标 key={target_key!r} 未被覆盖"
    )

    # 2. 兄弟 key 保留（base 中所有原 key 都还在）
    for k, v in fixed_cells.items():
        if k == target_key:
            continue  # 这个被覆盖了
        assert k in merged["sheets"]["s1"]["fixed_cells"], (
            f"深度合并擦掉了兄弟 key={k!r}"
        )
        assert merged["sheets"]["s1"]["fixed_cells"][k] == v, (
            f"深度合并修改了兄弟 key={k!r} 的值：{v!r} → "
            f"{merged['sheets']['s1']['fixed_cells'][k]!r}"
        )

    # 3. 上层结构保留
    assert merged["sheets"]["s1"]["component_type"] == "a-program-console"
    assert merged["sheets"]["s2"] == {"component_type": "b-index"}

    # 4. 原 nested_base 未被修改
    assert nested_base == nested_base_snapshot, (
        "merge_with_override 修改了原 base 嵌套结构"
    )


# ─── Property 7e: None / 空 dict 透传 ────────────────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(base=st_schema_dict)
def test_property_7e_none_or_empty_override_passes_through(
    base: dict,
) -> None:
    """**Validates: Requirements 3.0.3** — None / {} 透传

    1. override is None → merge 返回 base（== 等价）
    2. override == {} → merge 返回 base（== 等价）
    3. 两种情况下 base 字典都不被修改
    """
    service = WpRenderSchemaService()

    base_snapshot = copy.deepcopy(base)

    # None override
    result_none = service.merge_with_override(base, None)
    assert result_none == base, (
        "override=None 时 merge 应返回与 base 等价的结果"
    )
    assert base == base_snapshot, "override=None 时 base 不应被修改"

    # Empty dict override
    result_empty = service.merge_with_override(base, {})
    assert result_empty == base, (
        "override={} 时 merge 应返回与 base 等价的结果"
    )
    assert base == base_snapshot, "override={} 时 base 不应被修改"


# ─── 兜底：classification 覆盖 + 路由 端到端幂等 ─────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(base=st_base_classification, override=st_override)
def test_classification_override_then_route_is_idempotent(
    base: dict, override: dict
) -> None:
    """端到端幂等：(apply_override → route_to_component_type) 多次结果恒等。

    覆盖 Property 7a + 7b + 7c 的组合不变性。
    """
    ct1 = _route_to_component_type(_apply_classification_override(base, override))
    ct2 = _route_to_component_type(_apply_classification_override(base, override))
    ct3 = _route_to_component_type(_apply_classification_override(base, override))

    assert ct1 == ct2 == ct3, (
        f"classification 覆盖 + 路由不幂等：{ct1!r} / {ct2!r} / {ct3!r} "
        f"(base={base!r}, override={override!r})"
    )


# ─── Pending class_code 防御：override 指向 _pending → derive 抛异常 ───


def test_pending_class_code_raises_on_route() -> None:
    """补充防御 case（非 PBT 但与 Property 7c 互补）：
    pending 归类 → _route_to_component_type 在 standalone scope 下抛
    ClassificationNotFoundError（禁止 Univer 兜底，与 Property 1b 一致）。
    """
    classification = ClassificationResult(
        wp_code="UNKNOWN",
        sheet_name="某 sheet",
        class_code=None,  # pending
        class_=None,
        scope="standalone",
        is_real_workpaper=True,
        delegated_module=None,
        render_schema_path=None,
        template_version_id=uuid.uuid4(),
        has_override=False,
    )
    with pytest.raises(ClassificationNotFoundError):
        _route_to_component_type(classification)
