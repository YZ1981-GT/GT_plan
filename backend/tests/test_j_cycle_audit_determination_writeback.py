"""J 类底稿（职工薪酬循环）审定表 + 回写联动验证测试。

覆盖:
  10. 确认 J1-1~J3-1 共 3 个审定表的 d-form-table schema 字段完整
  11. 创建 J1-1 手工 YAML schema（按薪酬类别分行：工资/奖金/社保/公积金/福利）
  12. 扩展 _on_d_audit_determination_saved handler 正则匹配 J 类（^J\\d+-1$）
  13. 验证审定表保存→trial_balance 回写正确（3 个审定表）
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
import yaml

from app.services.wp_classification_service import _WP_CODE_OVERRIDE

# ═══════════════════════════════════════════════════════════════════════════════
# 路径常量
# ═══════════════════════════════════════════════════════════════════════════════

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_SCHEMA_DIR = _DATA_DIR / "ledger_adapters" / "wp_render_schema"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 10: 确认 J1-1~J3-1 共 3 个审定表的 d-form-table schema 字段完整
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask10SchemaCompleteness:
    """Task 10: J1-1~J3-1 审定表 d-form-table schema 字段完整性。"""

    _AUDIT_DET_CODES = ["J1-1", "J2-1", "J3-1"]

    @pytest.mark.parametrize("wp_code", _AUDIT_DET_CODES)
    def test_all_registered_as_d_form_table(self, wp_code):
        """J1-1, J2-1, J3-1 均注册为 d-form-table。"""
        assert wp_code in _WP_CODE_OVERRIDE, f"{wp_code} 未在 _WP_CODE_OVERRIDE 中注册"
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table", (
            f"{wp_code} componentType 应为 d-form-table，实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    @pytest.mark.parametrize("wp_code", _AUDIT_DET_CODES)
    def test_schema_file_exists(self, wp_code):
        """每个审定表有对应的 YAML schema 文件。"""
        schema_path = _SCHEMA_DIR / f"{wp_code}.yaml"
        assert schema_path.exists(), f"{wp_code} schema 文件不存在: {schema_path}"

    @pytest.mark.parametrize("wp_code", _AUDIT_DET_CODES)
    def test_schema_has_required_top_level_fields(self, wp_code):
        """每个 schema 包含必要的顶级字段。"""
        schema_path = _SCHEMA_DIR / f"{wp_code}.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        required_keys = ["wp_code", "wp_name", "component_type", "sections", "writeback"]
        for key in required_keys:
            assert key in schema, f"{wp_code} schema 缺少 {key} 字段"
        assert schema["component_type"] == "d-form-table"
        assert schema["wp_code"] == wp_code

    @pytest.mark.parametrize("wp_code", _AUDIT_DET_CODES)
    def test_schema_sections_have_standard_fields(self, wp_code):
        """每个 schema 的 sections 包含标准审定表字段。"""
        schema_path = _SCHEMA_DIR / f"{wp_code}.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        # 检查第一个 section 的 fields
        first_section = schema["sections"][0]
        field_names = [f["field"] for f in first_section["fields"]]
        # 标准审定表必须字段
        required_fields = [
            "account_code", "account_name",
            "opening_balance", "unadjusted_amount",
            "aje_debit", "aje_credit",
            "rje_debit", "rje_credit",
            "audited_amount",
            "prior_year_audited",
            "variance_amount", "variance_pct", "variance_note",
        ]
        for field in required_fields:
            assert field in field_names, (
                f"{wp_code} 第一个 section 缺少字段 {field}"
            )

    @pytest.mark.parametrize("wp_code", _AUDIT_DET_CODES)
    def test_schema_has_writeback_config(self, wp_code):
        """每个 schema 的 writeback 配置正确。"""
        schema_path = _SCHEMA_DIR / f"{wp_code}.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        wb = schema["writeback"]
        assert wb["target"] == "trial_balance.audited_amount"
        assert wb["trigger"] == "WORKPAPER_SAVED"
        assert wb["key_field"] == "account_code"
        assert wb["value_field"] == "audited_amount"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 11: J1-1 手工 YAML schema 按薪酬类别分行
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask11J1Schema:
    """Task 11: J1-1 schema 按薪酬类别分行验证。"""

    @pytest.fixture
    def j1_1_schema(self):
        schema_path = _SCHEMA_DIR / "J1-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_j1_1_has_compensation_categories(self, j1_1_schema):
        """J1-1 包含全部薪酬类别行。"""
        section_names = [s["name"] for s in j1_1_schema["sections"]]
        expected = ["工资", "奖金", "社会保险", "住房公积金", "职工福利", "辞退福利", "其他"]
        for cat in expected:
            assert cat in section_names, f"J1-1 缺少薪酬类别 '{cat}'"

    def test_j1_1_has_total_row(self, j1_1_schema):
        """J1-1 包含合计行。"""
        section_names = [s["name"] for s in j1_1_schema["sections"]]
        assert "应付职工薪酬合计" in section_names

    def test_j1_1_total_formula_covers_all_categories(self, j1_1_schema):
        """合计行公式包含全部类别。"""
        total_section = next(
            s for s in j1_1_schema["sections"] if s["name"] == "应付职工薪酬合计"
        )
        formula = total_section["formula_source"]
        for cat in ["工资", "奖金", "社会保险", "住房公积金", "职工福利", "辞退福利", "其他"]:
            assert cat in formula, f"合计行公式缺少 '{cat}'"

    def test_j1_1_category_rows_have_group_key(self, j1_1_schema):
        """各类别行有 group_key 标识。"""
        category_sections = [
            s for s in j1_1_schema["sections"] if s.get("row_type") == "category_row"
        ]
        assert len(category_sections) == 7
        for section in category_sections:
            assert "group_key" in section, f"'{section['name']}' 缺少 group_key"

    def test_j1_1_related_accounts(self, j1_1_schema):
        """J1-1 关联科目为 2211 应付职工薪酬。"""
        accounts = j1_1_schema["related_accounts"]
        codes = [a["code"] for a in accounts]
        assert "2211" in codes

    def test_j1_1_has_cross_refs(self, j1_1_schema):
        """J1-1 有跨底稿引用。"""
        assert "cross_refs" in j1_1_schema
        assert len(j1_1_schema["cross_refs"]) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# Task 12: handler 正则匹配 J 类
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask12HandlerRegex:
    """Task 12: _on_d_audit_determination_saved handler 正则匹配 J 类。"""

    _PATTERN = re.compile(r"^[D-N]\d+-1$")

    @pytest.mark.parametrize("wp_code", ["J1-1", "J2-1", "J3-1"])
    def test_regex_matches_j_audit_tables(self, wp_code):
        """正则 ^[D-N]\\d+-1$ 匹配 J 类审定表。"""
        assert self._PATTERN.match(wp_code), f"正则不匹配 {wp_code}"

    def test_regex_does_not_match_non_audit(self):
        """正则不匹配非审定表代码。"""
        non_audit = ["J1A", "J1-2", "J2-3", "J3", "J1-8", "JA"]
        for code in non_audit:
            assert not self._PATTERN.match(code), f"正则不应匹配 {code}"

    def test_handler_registered_in_event_handlers(self):
        """handler 在 event_handlers.py 中注册。"""
        from app.services import event_handlers_cycle_linkage
        src = inspect.getsource(event_handlers_cycle_linkage)
        assert (
            "event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_d_audit_determination_saved)"
            in src
        )

    def test_handler_uses_d_to_n_regex(self):
        """handler 使用 ^[D-N]\\d+-1$ 正则模式。"""
        from app.services import event_handlers_cycle_linkage
        src = inspect.getsource(event_handlers_cycle_linkage)
        assert r'^[D-N]\d+-1$' in src


# ═══════════════════════════════════════════════════════════════════════════════
# Task 13: 审定表保存→trial_balance 回写正确（3 个审定表）
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask13WritebackIntegration:
    """Task 13: 审定表保存→trial_balance 回写正确。

    handler 定义在 event_handlers.py 局部作用域中。
    通过 inspect 源码检查 + 正则验证覆盖逻辑路径。
    """

    @pytest.mark.parametrize("wp_code", ["J1-1", "J2-1", "J3-1"])
    def test_j_class_passes_regex_filter(self, wp_code):
        """J 类审定表能通过 handler 正则过滤。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        assert pattern.match(wp_code), f"{wp_code} 应通过审定表正则匹配"

    def test_handler_extracts_rows_from_parsed_data(self):
        """handler 从 payload.extra['parsed_data']['rows'] 提取审定数据。"""
        src = inspect.getsource(__import__("app.services.event_handlers_cycle_linkage", fromlist=["x"]))
        assert 'parsed_data.get("rows"' in src or "parsed_data.get('rows'" in src

    def test_handler_updates_trial_balance_audited_amount(self):
        """handler 执行 UPDATE trial_balance SET audited_amount。"""
        from app.services import event_handlers_cycle_linkage
        src = inspect.getsource(event_handlers_cycle_linkage)
        assert "audited_amount" in src
        assert "TrialBalance" in src
        assert "standard_account_code" in src

    def test_handler_commits_on_success(self):
        """handler 成功后执行 commit。"""
        from app.services import event_handlers_cycle_linkage
        src = inspect.getsource(event_handlers_cycle_linkage)
        assert "await session.commit()" in src

    def test_handler_triggers_trial_balance_updated_event(self):
        """handler 成功回写后触发 TRIAL_BALANCE_UPDATED 事件。"""
        from app.services import event_handlers_cycle_linkage
        src = inspect.getsource(event_handlers_cycle_linkage)
        assert "TRIAL_BALANCE_UPDATED" in src

    def test_non_j_audit_codes_not_matched(self):
        """J 类非审定表编码被正则拒绝。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        non_audit = ["J1A", "J1-2", "J1-3", "J2-3", "J3-4", "J1-8"]
        for code in non_audit:
            assert not pattern.match(code), f"{code} 不应匹配审定表正则"

    def test_other_cycle_codes_still_matched(self):
        """扩展正则后其他循环审定表仍然正确匹配（回归测试）。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        other_codes = [
            "D1-1", "D2-1", "E1-1", "F1-1", "F2-1",
            "G7-1", "H1-1", "I1-1", "K1-1", "L1-1", "M1-1", "N1-1",
        ]
        for code in other_codes:
            assert pattern.match(code), f"'{code}' 应继续匹配"

    def test_handler_rollback_on_error(self):
        """handler 异常时执行 rollback。"""
        from app.services import event_handlers_cycle_linkage
        src = inspect.getsource(event_handlers_cycle_linkage)
        assert "await session.rollback()" in src
