"""Sprint A.4.3 单测 — 段落变量自动收集器（merge_paragraph_vars + 子源工具）.

Spec:    .kiro/specs/note-dynamic-tables-and-template-inheritance/ Sprint A.4.3
Design:  D7 文字段落 Jinja 渲染 — vars 来源（wizard_state + project + consol + prior）
Reqs:    A.4.3 段落变量自动收集

主要覆盖：
- ``merge_paragraph_vars`` 优先级
- 缺 wizard_state 的 fallback
- ``project_to_vars`` 派生字段（is_listed / is_soe）
- ``basic_info_to_vars`` 双 path 兼容（steps.basic_info / basic_info）

注：``collect_paragraph_vars`` 异步 + DB 路径在 integration 测试覆盖，
此文件只做纯函数验证（无 DB / 无 mock）。
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.note_text_paragraph_vars import (
    basic_info_to_vars,
    merge_paragraph_vars,
    project_to_vars,
)


# ---------------------------------------------------------------------------
# merge_paragraph_vars
# ---------------------------------------------------------------------------


class TestMergeParagraphVars:
    def test_later_overrides_earlier(self):
        out = merge_paragraph_vars({"a": 1, "b": 2}, {"b": 99, "c": 3})
        assert out == {"a": 1, "b": 99, "c": 3}

    def test_skips_none_and_empty(self):
        out = merge_paragraph_vars(None, {"a": 1}, {}, None, {"b": 2})
        assert out == {"a": 1, "b": 2}

    def test_returns_new_dict_does_not_mutate_input(self):
        a = {"x": 1}
        b = {"x": 2}
        out = merge_paragraph_vars(a, b)
        assert out == {"x": 2}
        # 入参未变
        assert a == {"x": 1}
        assert b == {"x": 2}


# ---------------------------------------------------------------------------
# basic_info_to_vars
# ---------------------------------------------------------------------------


class TestBasicInfoToVars:
    def test_new_schema_steps_basic_info(self):
        wizard = {
            "steps": {
                "basic_info": {
                    "data": {
                        "registration_authority": "北京市工商局",
                        "registered_capital": 50000000,
                        "list_exchange": "上交所",
                    }
                }
            }
        }
        out = basic_info_to_vars(wizard)
        assert out == {
            "registration_authority": "北京市工商局",
            "registered_capital": 50000000,
            "list_exchange": "上交所",
        }

    def test_legacy_schema_basic_info(self):
        wizard = {
            "basic_info": {
                "data": {
                    "registration_authority": "上海工商局",
                }
            }
        }
        out = basic_info_to_vars(wizard)
        assert out == {"registration_authority": "上海工商局"}

    def test_none_or_empty_returns_dict(self):
        assert basic_info_to_vars(None) == {}
        assert basic_info_to_vars({}) == {}
        assert basic_info_to_vars({"steps": {}}) == {}

    def test_malformed_state_does_not_crash(self):
        # data 不是 dict → 跳过返 {}
        assert basic_info_to_vars(
            {"steps": {"basic_info": {"data": "not a dict"}}}
        ) == {}
        assert basic_info_to_vars({"basic_info": "string"}) == {}


# ---------------------------------------------------------------------------
# project_to_vars
# ---------------------------------------------------------------------------


class TestProjectToVars:
    def test_basic_fields_extracted(self):
        proj = SimpleNamespace(
            name="2025 年报",
            client_name="首汽租车",
            template_type="listed",
            report_scope="standalone",
            parent_company_name="首汽集团",
            ultimate_company_name="北汽集团",
            consol_level=1,
            scenario="normal",
            company_code="SQZL",
        )
        out = project_to_vars(proj)
        assert out["name"] == "2025 年报"
        assert out["project_name"] == "2025 年报"
        assert out["client_name"] == "首汽租车"
        assert out["company_name"] == "首汽租车"
        assert out["template_type"] == "listed"
        assert out["parent_company_name"] == "首汽集团"
        assert out["ultimate_company_name"] == "北汽集团"
        assert out["company_code"] == "SQZL"

    def test_derived_is_listed_and_is_soe(self):
        listed_proj = SimpleNamespace(
            name="A", client_name="X", template_type="listed",
            report_scope=None, parent_company_name=None,
            ultimate_company_name=None, consol_level=1,
            scenario=None, company_code=None,
        )
        soe_proj = SimpleNamespace(
            name="A", client_name="X", template_type="soe",
            report_scope=None, parent_company_name=None,
            ultimate_company_name=None, consol_level=1,
            scenario=None, company_code=None,
        )

        listed_vars = project_to_vars(listed_proj)
        soe_vars = project_to_vars(soe_proj)

        assert listed_vars["is_listed"] is True
        assert listed_vars["is_soe"] is False
        assert soe_vars["is_listed"] is False
        assert soe_vars["is_soe"] is True

    def test_handles_none_project(self):
        assert project_to_vars(None) == {}

    def test_skips_none_fields(self):
        # template_type=None → 不应该出现 is_listed / is_soe
        proj = SimpleNamespace(
            name="A", client_name="X", template_type=None,
            report_scope=None, parent_company_name=None,
            ultimate_company_name=None, consol_level=1,
            scenario=None, company_code=None,
        )
        out = project_to_vars(proj)
        assert "is_listed" not in out
        assert "is_soe" not in out
        # 但 client_name / company_name 还在（因为 client_name 不 None）
        assert out["client_name"] == "X"
        assert out["company_name"] == "X"


# ---------------------------------------------------------------------------
# 集成验证：完整收集顺序（合并优先级链路）
# ---------------------------------------------------------------------------


class TestCollectionPriorityChain:
    """validates merge order matches design：
    project < wizard < consol < prior < year < section_db < section_param
    """

    def test_section_param_overrides_all(self):
        # 模拟 collect_paragraph_vars 的合并顺序
        project_vars = {"company_name": "P-1"}
        wizard_vars = {"company_name": "P-2"}
        consol_vars = {"subsidiary_count": 5}
        year_vars = {"year": 2025}
        section_db = {"company_name": "P-3"}
        section_param = {"company_name": "P-4"}

        out = merge_paragraph_vars(
            project_vars, wizard_vars, consol_vars,
            year_vars, section_db, section_param,
        )
        assert out["company_name"] == "P-4"  # param 最高
        assert out["subsidiary_count"] == 5
        assert out["year"] == 2025

    def test_year_overrides_project_year(self):
        # year_vars 先于 section 覆盖，但晚于 project 字段（project 不应有 year）
        out = merge_paragraph_vars(
            {"company_name": "X"},  # project
            {},                      # wizard
            {},                      # consol
            {},                      # prior
            {"year": 2025, "report_year": 2025},
            {},
            {},
        )
        assert out["year"] == 2025
        assert out["report_year"] == 2025
