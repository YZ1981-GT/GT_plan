"""Property-based test for grammar_v1.json index namespace mapping.

# Feature: acnr, Property 11: 索引命名空间映射完备且限定

**Validates: Requirements 11.1, 11.4, 11.5, 13.4**

验证 grammar_v1.json 中：
1. 恰好 11 个索引命名空间（不多不少）
2. 11 个命名空间为 wp/sheet/cell/Note/TB/Adj/Att/EQCR/Calc/Sample/Confirm
3. 外部模块（Adj/Att/EQCR/Calc/Sample/Confirm）有 exists=true
4. 内部命名空间（wp/sheet/cell/Note/TB）不设 exists=true
5. 每个命名空间有 layer 字段且值在 1-4
6. 双向映射一致性：每个命名空间的 addr_id 模式与 entry_type/domain 配置一致
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

# ---------------------------------------------------------------------------
# Constants: 期望的命名空间集合
# ---------------------------------------------------------------------------

EXPECTED_NAMESPACES = frozenset([
    "wp", "sheet", "cell", "Note", "TB",
    "Adj", "Att", "EQCR", "Calc", "Sample", "Confirm",
])
EXPECTED_COUNT = 11

EXTERNAL_MODULES = frozenset(["Adj", "Att", "EQCR", "Calc", "Sample", "Confirm"])
INTERNAL_NAMESPACES = frozenset(["wp", "sheet", "cell", "Note", "TB"])

# ---------------------------------------------------------------------------
# Fixture: 加载 grammar_v1.json
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def grammar_data() -> dict:
    """加载 grammar_v1.json 并返回解析后的 dict。"""
    grammar_path = _BACKEND_ROOT / "data" / "acnr" / "grammar_v1.json"
    assert grammar_path.exists(), f"grammar_v1.json not found at {grammar_path}"
    with open(grammar_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def index_namespaces(grammar_data: dict) -> dict:
    """提取 index_namespaces 段。"""
    ns = grammar_data.get("index_namespaces")
    assert ns is not None, "grammar_v1.json 缺少 index_namespaces 段"
    return ns


# ---------------------------------------------------------------------------
# Strategy: 从 11 个命名空间中随机抽取子集进行检查
# ---------------------------------------------------------------------------

ns_strategy = st.sampled_from(sorted(EXPECTED_NAMESPACES))


# ---------------------------------------------------------------------------
# Property Test: 索引命名空间映射完备且限定
# ---------------------------------------------------------------------------


class TestGrammarNamespaceMappingCompleteness:
    """Property 11: 索引命名空间映射完备且限定。

    Validates: Requirements 11.1, 11.4, 11.5, 13.4
    """

    @settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(ns_name=ns_strategy)
    def test_namespace_exists_and_has_required_fields(
        self, ns_name: str, index_namespaces: dict
    ):
        """每个期望的命名空间存在于 grammar_v1 且具备必要字段。

        Property: ∀ ns ∈ EXPECTED_NAMESPACES →
          ns ∈ grammar_v1.index_namespaces ∧ ns.layer ∈ {1,2,3,4}
        """
        # R11.1: 命名空间必须存在
        assert ns_name in index_namespaces, (
            f"命名空间 '{ns_name}' 未在 grammar_v1.json 的 index_namespaces 中"
        )

        ns_def = index_namespaces[ns_name]

        # 每个命名空间必须有 layer 字段且值在 1-4
        assert "layer" in ns_def, f"命名空间 '{ns_name}' 缺少 layer 字段"
        assert ns_def["layer"] in (1, 2, 3, 4), (
            f"命名空间 '{ns_name}' 的 layer={ns_def['layer']} 不在 1-4 范围"
        )

    @settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(ns_name=st.sampled_from(sorted(EXTERNAL_MODULES)))
    def test_external_modules_have_exists_true(
        self, ns_name: str, index_namespaces: dict
    ):
        """外部模块命名空间必须设置 exists=true (R11.4)。

        Property: ∀ ns ∈ EXTERNAL_MODULES →
          ns.exists == true ∧ ns.external_module == true
        """
        assert ns_name in index_namespaces
        ns_def = index_namespaces[ns_name]

        # R11.4: 外部模块标 exists=true
        assert ns_def.get("exists") is True, (
            f"外部模块 '{ns_name}' 未设置 exists=true"
        )
        assert ns_def.get("external_module") is True, (
            f"外部模块 '{ns_name}' 未设置 external_module=true"
        )
        # 外部模块的 internal 应为 false
        assert ns_def.get("internal") is False, (
            f"外部模块 '{ns_name}' 不应标记为 internal"
        )

    @settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(ns_name=st.sampled_from(sorted(INTERNAL_NAMESPACES)))
    def test_internal_namespaces_no_exists_flag(
        self, ns_name: str, index_namespaces: dict
    ):
        """内部命名空间不设置 exists=true (R11.5)。

        Property: ∀ ns ∈ INTERNAL_NAMESPACES →
          ns.exists ∉ {true} ∧ ns.internal == true
        """
        assert ns_name in index_namespaces
        ns_def = index_namespaces[ns_name]

        # R11.5: 内部命名空间仅外部模块设 exists=true
        assert ns_def.get("exists") is not True, (
            f"内部命名空间 '{ns_name}' 不应设置 exists=true"
        )
        # 内部命名空间标 internal=true
        assert ns_def.get("internal") is True, (
            f"内部命名空间 '{ns_name}' 应标记为 internal=true"
        )

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(ns_name=ns_strategy)
    def test_bidirectional_mapping_consistency(
        self, ns_name: str, index_namespaces: dict
    ):
        """双向映射一致性：addr_id 模式与命名空间配置对应 (R13.4)。

        Property: ∀ ns ∈ EXPECTED_NAMESPACES →
          (ns.addr_id is not None → addr_id 模式含 ns 标识符或域前缀)
          ∧ (ns.layer == 4 ∧ ns.internal == false → ns.addr_id 以 ns_name/ 开头)
        """
        assert ns_name in index_namespaces
        ns_def = index_namespaces[ns_name]

        addr_id_pattern = ns_def.get("addr_id")

        if ns_def.get("external_module"):
            # 外部模块的 addr_id 模式应以命名空间名开头
            assert addr_id_pattern is not None, (
                f"外部模块 '{ns_name}' 应有 addr_id 模式"
            )
            assert addr_id_pattern.startswith(f"{ns_name}/"), (
                f"外部模块 '{ns_name}' 的 addr_id='{addr_id_pattern}' "
                f"应以 '{ns_name}/' 开头"
            )
        elif ns_def.get("internal") and addr_id_pattern is not None:
            # 内部命名空间有 addr_id 时，模式应包含占位符
            # TB 的 addr_id 为 null（委托 V1），这是合法的
            assert "{" in addr_id_pattern or addr_id_pattern == "null", (
                f"内部命名空间 '{ns_name}' 的 addr_id='{addr_id_pattern}' "
                f"应包含占位符模式"
            )

    def test_exactly_11_namespaces(self, index_namespaces: dict):
        """grammar_v1 恰好包含 11 个索引命名空间，不多不少 (R11.1)。

        静态断言（非 hypothesis 属性测试的补充前置检查）。
        """
        actual_ns = set(index_namespaces.keys())
        assert len(actual_ns) == EXPECTED_COUNT, (
            f"期望恰好 {EXPECTED_COUNT} 个命名空间，"
            f"实际 {len(actual_ns)} 个: {actual_ns}"
        )

    def test_namespace_set_matches_exactly(self, index_namespaces: dict):
        """命名空间集合精确匹配期望列表 (R11.1)。

        静态断言确保无意外增减。
        """
        actual_ns = set(index_namespaces.keys())
        assert actual_ns == EXPECTED_NAMESPACES, (
            f"命名空间不匹配。\n"
            f"多出: {actual_ns - EXPECTED_NAMESPACES}\n"
            f"缺少: {EXPECTED_NAMESPACES - actual_ns}"
        )

    def test_resolve_one_query_returns_exists_trimmed_reason(
        self, index_namespaces: dict
    ):
        """R13.4: 解析索引引用时一次查询应能提供 exists/trimmed/reason 信息。

        验证 grammar_v1 为每个命名空间提供了足够的元数据以支撑一次查询返回。
        外部模块：有 exists 字段。
        内部命名空间：有 uri/formula/addr_id 映射使 resolver 能一次性判断。
        """
        for ns_name, ns_def in index_namespaces.items():
            if ns_def.get("external_module"):
                # 外部模块必须有 exists 字段
                assert "exists" in ns_def, (
                    f"外部模块 '{ns_name}' 缺少 exists 字段，"
                    f"无法支撑一次查询返回 exists/trimmed/reason"
                )
            else:
                # 内部命名空间需有映射信息（uri 或 addr_id 或 domain 委托）
                has_mapping = (
                    ns_def.get("uri") is not None
                    or ns_def.get("addr_id") is not None
                    or ns_def.get("delegated_to") is not None
                )
                assert has_mapping, (
                    f"内部命名空间 '{ns_name}' 缺少 uri/addr_id/delegated_to，"
                    f"无法支撑 resolver 一次查询返回"
                )
