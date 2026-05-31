"""合并模块 Phase 2 S7 cross_template 降级不丢章节 PBT（hypothesis）

`consol_disclosure_service.apply_cross_template_to_children` 把孤立的
`consol_cross_template_service.translate_child_section` 接入 V2 附注汇总 live 路径
（国企↔上市跨模板翻译，需求 6）。S7 核心不变量：

    len(apply_cross_template_to_children(...)[0]) == len(input)   永远成立（不丢章节）

三类行为：
- 同 template_type 子公司 → 原样透传（不翻译、无 warning）。
- 不同 template_type 但无匹配映射 → 降级原样汇总 + warning（EH7），但不丢章节。
- 翻译异常 → 降级原样汇总 + warning，不丢章节。

测试通过 patch `translate_child_section`（disclosure 函数内 lazy import，patch 目标
是其源模块 `app.services.consol_cross_template_service.translate_child_section`）
覆盖各分类结果，验证长度不变量在所有情况下成立。

Validates: Requirements 6.1, 6.2, 6.4 (Property S7); Error scenario EH7
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from hypothesis import given, settings, strategies as st

from app.services.consol_disclosure_service import apply_cross_template_to_children

_XT = "app.services.consol_cross_template_service.translate_child_section"

_TEMPLATE_TYPES = ["soe", "listed"]


@st.composite
def children_strategy(draw: st.DrawFn):
    """生成随机子公司章节列表（随机 template_type + section_data 形态）。"""
    n = draw(st.integers(min_value=0, max_value=8))
    children = []
    for i in range(n):
        template_type = draw(st.sampled_from(_TEMPLATE_TYPES + [None]))
        # section_data：dict（可翻译）/ 非 dict（强制透传）
        section_data = draw(
            st.one_of(
                st.fixed_dictionaries({"section_id": st.text(max_size=8)}),
                st.none(),
                st.integers(),
            )
        )
        children.append(
            {
                "project_id": str(uuid4()),
                "company_name": f"子公司{i}",
                "template_type": template_type,
                "section_data": section_data,
            }
        )
    return children


def _stub_translate(translation_type: str):
    """构造 translate_child_section 替身，返回指定 _translation_type 的结果。"""

    def _impl(payload, from_type, to_type):
        result = dict(payload)
        result["_translated"] = True
        result["_translation_type"] = translation_type
        if translation_type == "target_only":
            return {"section_id": payload.get("section_id"), "_not_applicable": True,
                    "_translation_type": "target_only"}
        return result

    return MagicMock(side_effect=_impl)


# ===========================================================================
# S7 长度不变量（核心属性）
# ===========================================================================


class TestS7NoSectionLoss:
    """S7：apply_cross_template_to_children 输出章节数恒等于输入（不丢章节）。

    **Validates: Requirements 6.4**
    """

    @given(
        children=children_strategy(),
        consol_type=st.sampled_from(_TEMPLATE_TYPES),
        translation_type=st.sampled_from(["common", "format_diff", "source_only", "unknown", "target_only"]),
    )
    @settings(max_examples=15)
    def test_output_length_equals_input_length(self, children, consol_type, translation_type):
        """任意子公司列表 + 任意翻译分类 → 输出长度 == 输入长度。"""
        with patch(_XT, new=_stub_translate(translation_type)):
            out, warnings = apply_cross_template_to_children("sec_x", children, consol_type)

        assert len(out) == len(children), "S7 不变量：cross_template 不得丢失章节"
        assert isinstance(warnings, list)

    @given(children=children_strategy(), consol_type=st.sampled_from(_TEMPLATE_TYPES))
    @settings(max_examples=10)
    def test_output_length_invariant_when_translate_raises(self, children, consol_type):
        """翻译抛异常 → 降级原样汇总，长度仍守恒（EH7）。"""
        boom = MagicMock(side_effect=RuntimeError("translate boom"))
        with patch(_XT, new=boom):
            out, warnings = apply_cross_template_to_children("sec_x", children, consol_type)

        assert len(out) == len(children)


# ===========================================================================
# 同模板透传（无翻译、无 warning）
# ===========================================================================


class TestSameTypePassthrough:
    """同 template_type 子公司原样透传，不调 translate，无 warning。

    **Validates: Requirements 6.2**
    """

    def test_same_type_does_not_call_translate(self):
        """所有子公司 template_type == consol_type → translate 不被调用，无 warning。"""
        children = [
            {"project_id": str(uuid4()), "company_name": "甲", "template_type": "soe",
             "section_data": {"section_id": "s1"}},
            {"project_id": str(uuid4()), "company_name": "乙", "template_type": "soe",
             "section_data": {"section_id": "s1"}},
        ]
        stub = _stub_translate("common")
        with patch(_XT, new=stub):
            out, warnings = apply_cross_template_to_children("s1", children, "soe")

        stub.assert_not_called()
        assert len(out) == 2
        assert warnings == []
        # 原样透传：对象保持不变
        assert out == children

    def test_non_dict_section_data_passthrough(self):
        """section_data 非 dict（即便 template_type 不同）→ 原样透传不翻译。"""
        children = [
            {"project_id": str(uuid4()), "company_name": "丙", "template_type": "listed",
             "section_data": None},
        ]
        stub = _stub_translate("common")
        with patch(_XT, new=stub):
            out, warnings = apply_cross_template_to_children("s1", children, "soe")

        stub.assert_not_called()
        assert len(out) == 1
        assert warnings == []


# ===========================================================================
# 不同模板：翻译 / 降级
# ===========================================================================


class TestDifferingTypeTranslation:
    """不同 template_type 子公司调 translate；无映射降级 + warning，不丢章节。

    **Validates: Requirements 6.1, 6.2, 6.4; EH7**
    """

    def test_differing_type_common_translation(self):
        """listed 子公司 → soe 合并，common 映射 → 翻译后汇总，无 warning。"""
        children = [
            {"project_id": str(uuid4()), "company_name": "上市子", "template_type": "listed",
             "section_data": {"section_id": "s1", "table_data": {}}},
        ]
        stub = _stub_translate("common")
        with patch(_XT, new=stub):
            out, warnings = apply_cross_template_to_children("s1", children, "soe")

        stub.assert_called_once()
        assert len(out) == 1
        assert warnings == []
        # 翻译结果写回 section_data
        assert out[0]["section_data"]["_translation_type"] == "common"

    def test_unknown_mapping_degrades_with_warning(self):
        """无匹配映射（unknown）→ 降级原样汇总 + warning，但保留章节（S7/EH7）。"""
        children = [
            {"project_id": str(uuid4()), "company_name": "上市子", "template_type": "listed",
             "section_data": {"section_id": "s_unknown"}},
        ]
        with patch(_XT, new=_stub_translate("unknown")):
            out, warnings = apply_cross_template_to_children("s_unknown", children, "soe")

        assert len(out) == 1
        assert len(warnings) == 1
        assert "降级原样汇总" in warnings[0]

    def test_target_only_degrades_with_warning(self):
        """target_only（子公司无此章节数据）→ 降级 + warning，保留原始 section_data。"""
        original = {"section_id": "s_target"}
        children = [
            {"project_id": str(uuid4()), "company_name": "上市子", "template_type": "listed",
             "section_data": original},
        ]
        with patch(_XT, new=_stub_translate("target_only")):
            out, warnings = apply_cross_template_to_children("s_target", children, "soe")

        assert len(out) == 1
        assert len(warnings) == 1
        # target_only：保留子公司原始 section_data（不丢）
        assert out[0]["section_data"] == original

    def test_translate_exception_degrades_with_warning(self):
        """翻译异常 → 降级原样汇总 + warning，章节保留（EH7）。"""
        children = [
            {"project_id": str(uuid4()), "company_name": "上市子", "template_type": "listed",
             "section_data": {"section_id": "s1"}},
        ]
        boom = MagicMock(side_effect=ValueError("mapping load failed"))
        with patch(_XT, new=boom):
            out, warnings = apply_cross_template_to_children("s1", children, "soe")

        assert len(out) == 1
        assert len(warnings) == 1
        assert "降级原样汇总" in warnings[0]

    def test_empty_children_returns_empty(self):
        """空子公司列表 → 空输出 + 空 warning（不抛错）。"""
        with patch(_XT, new=_stub_translate("common")):
            out, warnings = apply_cross_template_to_children("s1", [], "soe")
        assert out == []
        assert warnings == []
