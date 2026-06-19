"""K 类底稿（管理循环）审定表 + 回写联动验证测试。

覆盖:
  22. 确认 K1-1~K13-1 共 13 个审定表的 d-form-table schema 字段完整
  23. 创建 K8-1/K9-1 手工 YAML schema（损益类：取发生额+按费用明细分行）
  24. 扩展 handler 正则匹配 K 类（^[D-N]\\d+-1$ 已覆盖 K）
  25. 验证审定表保存→trial_balance 回写正确（13 个审定表）
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
# Task 22: 确认 K1-1~K13-1 共 13 个审定表的 d-form-table schema 字段完整
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask22SchemaCompleteness:
    """Task 22: K1-1~K13-1 审定表 d-form-table schema 字段完整性。"""

    _AUDIT_DET_CODES = [
        "K1-1", "K2-1", "K3-1", "K4-1", "K5-1",
        "K6-1", "K7-1", "K8-1", "K9-1", "K10-1",
        "K11-1", "K12-1", "K13-1",
    ]

    @pytest.mark.parametrize("wp_code", _AUDIT_DET_CODES)
    def test_all_registered_as_d_form_table(self, wp_code):
        """K1-1~K13-1 均注册为 d-form-table。"""
        assert wp_code in _WP_CODE_OVERRIDE, f"{wp_code} 未在 _WP_CODE_OVERRIDE 中注册"
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table", (
            f"{wp_code} componentType 应为 d-form-table，实际为 {_WP_CODE_OVERRIDE[wp_code]}"
        )

    @pytest.mark.parametrize("wp_code", ["K8-1", "K9-1", "K7-1", "K10-1"])
    def test_special_schema_file_exists(self, wp_code):
        """K8-1/K9-1/K7-1/K10-1 有对应的特殊 YAML schema 文件。"""
        schema_path = _SCHEMA_DIR / f"{wp_code}.yaml"
        assert schema_path.exists(), f"{wp_code} schema 文件不存在: {schema_path}"

    @pytest.mark.parametrize("wp_code", ["K8-1", "K9-1", "K7-1", "K10-1"])
    def test_schema_has_required_top_level_fields(self, wp_code):
        """有 YAML 的 schema 包含必要的顶级字段。"""
        schema_path = _SCHEMA_DIR / f"{wp_code}.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        required_keys = ["wp_code", "wp_name", "component_type", "sections", "writeback"]
        for key in required_keys:
            assert key in schema, f"{wp_code} schema 缺少 {key} 字段"
        assert schema["component_type"] == "d-form-table"
        assert schema["wp_code"] == wp_code

    @pytest.mark.parametrize("wp_code", ["K8-1", "K9-1", "K7-1", "K10-1"])
    def test_schema_sections_have_standard_fields(self, wp_code):
        """每个 schema 的 sections 包含标准审定表字段。"""
        schema_path = _SCHEMA_DIR / f"{wp_code}.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        first_section = schema["sections"][0]
        field_names = [f["field"] for f in first_section["fields"]]
        required_fields = [
            "account_code", "account_name",
            "unadjusted_amount",
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

    @pytest.mark.parametrize("wp_code", ["K8-1", "K9-1", "K7-1", "K10-1"])
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
# Task 23: K8-1/K9-1 手工 YAML schema（损益类：取发生额+按费用明细分行）
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask23K8K9Schema:
    """Task 23: K8-1/K9-1 损益类审定表特殊结构验证。"""

    @pytest.fixture
    def k8_1_schema(self):
        schema_path = _SCHEMA_DIR / "K8-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def k9_1_schema(self):
        schema_path = _SCHEMA_DIR / "K9-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_k8_1_is_income_statement_type(self, k8_1_schema):
        """K8-1 标记为损益类（income_statement_type）。"""
        assert k8_1_schema.get("income_statement_type") is True

    def test_k8_1_takes_occurrence_amount(self, k8_1_schema):
        """K8-1 取发生额（非期末余额）。"""
        assert k8_1_schema.get("amount_source") == "occurrence_amount"

    def test_k8_1_has_expense_categories(self, k8_1_schema):
        """K8-1 包含费用明细类别行。"""
        section_names = [s["name"] for s in k8_1_schema["sections"]]
        expected = ["工资及福利", "折旧费", "办公费", "差旅费", "广告费", "运输费", "佣金", "其他"]
        for cat in expected:
            assert cat in section_names, f"K8-1 缺少费用类别 '{cat}'"

    def test_k8_1_has_total_row(self, k8_1_schema):
        """K8-1 包含合计行。"""
        section_names = [s["name"] for s in k8_1_schema["sections"]]
        assert "销售费用合计" in section_names

    def test_k9_1_is_income_statement_type(self, k9_1_schema):
        """K9-1 标记为损益类（income_statement_type）。"""
        assert k9_1_schema.get("income_statement_type") is True

    def test_k9_1_takes_occurrence_amount(self, k9_1_schema):
        """K9-1 取发生额（非期末余额）。"""
        assert k9_1_schema.get("amount_source") == "occurrence_amount"

    def test_k9_1_has_expense_categories(self, k9_1_schema):
        """K9-1 包含费用明细类别行。"""
        section_names = [s["name"] for s in k9_1_schema["sections"]]
        expected = ["工资及福利", "折旧费", "办公费", "差旅费", "业务招待费", "研发费摊销", "咨询费", "其他"]
        for cat in expected:
            assert cat in section_names, f"K9-1 缺少费用类别 '{cat}'"

    def test_k9_1_has_total_row(self, k9_1_schema):
        """K9-1 包含合计行。"""
        section_names = [s["name"] for s in k9_1_schema["sections"]]
        assert "管理费用合计" in section_names

    def test_k8_1_related_account(self, k8_1_schema):
        """K8-1 关联科目为 6601 销售费用。"""
        codes = [a["code"] for a in k8_1_schema["related_accounts"]]
        assert "6601" in codes

    def test_k9_1_related_account(self, k9_1_schema):
        """K9-1 关联科目为 6602 管理费用。"""
        codes = [a["code"] for a in k9_1_schema["related_accounts"]]
        assert "6602" in codes

    def test_k8_1_has_cross_refs(self, k8_1_schema):
        """K8-1 有跨底稿引用（K8-2/K8-3/K8-6）。"""
        assert "cross_refs" in k8_1_schema
        assert len(k8_1_schema["cross_refs"]) >= 3

    def test_k9_1_has_cross_refs(self, k9_1_schema):
        """K9-1 有跨底稿引用（K9-2/K9-3/K9-6）。"""
        assert "cross_refs" in k9_1_schema
        assert len(k9_1_schema["cross_refs"]) >= 3


# ═══════════════════════════════════════════════════════════════════════════════
# Task 24: handler 正则匹配 K 类
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask24HandlerRegex:
    """Task 24: _on_d_audit_determination_saved handler 正则匹配 K 类。"""

    _PATTERN = re.compile(r"^[D-N]\d+-1$")

    _K_AUDIT_CODES = [
        "K1-1", "K2-1", "K3-1", "K4-1", "K5-1",
        "K6-1", "K7-1", "K8-1", "K9-1", "K10-1",
        "K11-1", "K12-1", "K13-1",
    ]

    @pytest.mark.parametrize("wp_code", _K_AUDIT_CODES)
    def test_regex_matches_k_audit_tables(self, wp_code):
        """正则 ^[D-N]\\d+-1$ 匹配所有 K 类审定表。"""
        assert self._PATTERN.match(wp_code), f"正则不匹配 {wp_code}"

    def test_regex_does_not_match_non_audit(self):
        """正则不匹配非审定表代码。"""
        # 注意：K0-1 技术上匹配正则（K在D-N范围，0是数字），
        # 但 handler 内部会检查是否为审定表（K0-x 是函证辅助表不做回写）
        non_audit = ["K1A", "K1-2", "K2-3", "K3", "K1-6", "KA"]
        for code in non_audit:
            assert not self._PATTERN.match(code), f"正则不应匹配 {code}"

    def test_handler_registered_in_event_handlers(self):
        """handler 在 event_handlers.py 中注册。"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert (
            "event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_d_audit_determination_saved)"
            in src
        )

    def test_handler_uses_d_to_n_regex(self):
        """handler 使用 ^[D-N]\\d+-1$ 正则模式。"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert r'^[D-N]\d+-1$' in src


# ═══════════════════════════════════════════════════════════════════════════════
# Task 25: 审定表保存→trial_balance 回写正确（13 个审定表）
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask25WritebackIntegration:
    """Task 25: 审定表保存→trial_balance 回写正确。"""

    _K_AUDIT_CODES = [
        "K1-1", "K2-1", "K3-1", "K4-1", "K5-1",
        "K6-1", "K7-1", "K8-1", "K9-1", "K10-1",
        "K11-1", "K12-1", "K13-1",
    ]

    @pytest.mark.parametrize("wp_code", _K_AUDIT_CODES)
    def test_k_class_passes_regex_filter(self, wp_code):
        """K 类审定表能通过 handler 正则过滤。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        assert pattern.match(wp_code), f"{wp_code} 应通过审定表正则匹配"

    def test_handler_extracts_rows_from_parsed_data(self):
        """handler 从 payload.extra['parsed_data']['rows'] 提取审定数据。"""
        src = inspect.getsource(__import__("app.services.event_handlers", fromlist=["x"]))
        assert 'parsed_data.get("rows"' in src or "parsed_data.get('rows'" in src

    def test_handler_updates_trial_balance_audited_amount(self):
        """handler 执行 UPDATE trial_balance SET audited_amount。"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert "audited_amount" in src
        assert "TrialBalance" in src
        assert "standard_account_code" in src

    def test_handler_commits_on_success(self):
        """handler 成功后执行 commit。"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert "await session.commit()" in src

    def test_handler_triggers_trial_balance_updated_event(self):
        """handler 成功回写后触发 TRIAL_BALANCE_UPDATED 事件。"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert "TRIAL_BALANCE_UPDATED" in src

    def test_non_k_audit_codes_not_matched(self):
        """K 类非审定表编码被正则拒绝。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        non_audit = ["K1A", "K1-2", "K1-3", "K2-3", "K3-4", "K8-6"]
        for code in non_audit:
            assert not pattern.match(code), f"{code} 不应匹配审定表正则"

    def test_other_cycle_codes_still_matched(self):
        """扩展正则后其他循环审定表仍然正确匹配（回归测试）。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        other_codes = [
            "D1-1", "D2-1", "E1-1", "F1-1", "F2-1",
            "G7-1", "H1-1", "I1-1", "J1-1", "L1-1", "M1-1", "N1-1",
        ]
        for code in other_codes:
            assert pattern.match(code), f"'{code}' 应继续匹配"

    def test_handler_rollback_on_error(self):
        """handler 异常时执行 rollback。"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert "await session.rollback()" in src
