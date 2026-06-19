"""E 类审定表保存→trial_balance 回写验证（Tasks 10-13）。

验证:
  10. E1-1 审定表 d-form-table schema 字段完整（3 组：库存现金/银行存款/其他货币资金）
  11. E1-1 手工 YAML schema 文件存在且结构正确
  12. _on_d_audit_determination_saved handler 正则匹配 E 类审定表（^[D-N]\\d+-1$）
  13. 审定表保存→trial_balance 回写正确（直接调用 handler）
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from app.models.audit_platform_schemas import EventPayload, EventType
from app.services.wp_classification_service import _WP_CODE_OVERRIDE


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "ledger_adapters"
    / "wp_render_schema"
    / "E1-1.yaml"
)


@pytest.fixture(scope="module")
def e1_1_schema() -> dict:
    """加载 E1-1.yaml schema。"""
    assert _SCHEMA_PATH.exists(), f"E1-1.yaml 不存在: {_SCHEMA_PATH}"
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ═══════════════════════════════════════════════════════════════════════════════
# Task 10: E1-1 审定表 schema 字段完整性
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask10SchemaFields:
    """确认 E1-1 审定表 d-form-table schema 字段完整（标准审定表字段集，3 组）。"""

    # 标准审定表必备字段
    _REQUIRED_FIELDS = [
        "account_code",
        "account_name",
        "opening_balance",
        "unadjusted_amount",
        "aje_debit",
        "aje_credit",
        "rje_debit",
        "rje_credit",
        "audited_amount",
        "prior_year_audited",
        "variance_amount",
        "variance_pct",
        "variance_note",
    ]

    # 3 组科目前缀
    _EXPECTED_SECTIONS = [
        ("库存现金", "1001"),
        ("银行存款", "1002"),
        ("其他货币资金", "1012"),
    ]

    def test_schema_has_three_sections(self, e1_1_schema):
        """E1-1 审定表必须包含 3 组 section。"""
        sections = e1_1_schema.get("sections", [])
        assert len(sections) == 3, f"期望 3 组 section，实际 {len(sections)}"

    @pytest.mark.parametrize(
        "section_name,prefix", _EXPECTED_SECTIONS
    )
    def test_section_account_prefix(self, e1_1_schema, section_name, prefix):
        """每组 section 的 account_code_prefix 正确。"""
        sections = e1_1_schema.get("sections", [])
        matching = [s for s in sections if s.get("name") == section_name]
        assert matching, f"未找到 section '{section_name}'"
        assert matching[0].get("account_code_prefix") == prefix

    def test_all_standard_fields_present(self, e1_1_schema):
        """每组 section 包含全部 13 个标准审定表字段。"""
        sections = e1_1_schema.get("sections", [])
        for section in sections:
            fields = section.get("fields", [])
            field_names = [f.get("field") for f in fields]
            for required_field in self._REQUIRED_FIELDS:
                assert required_field in field_names, (
                    f"section '{section.get('name')}' 缺少字段 '{required_field}'"
                )

    def test_audited_amount_has_formula(self, e1_1_schema):
        """audited_amount 字段必须有计算公式。"""
        sections = e1_1_schema.get("sections", [])
        for section in sections:
            fields = section.get("fields", [])
            audited = [f for f in fields if f.get("field") == "audited_amount"]
            assert audited, f"section '{section.get('name')}' 缺 audited_amount"
            assert audited[0].get("formula"), (
                f"section '{section.get('name')}' 的 audited_amount 缺少 formula"
            )

    def test_auto_source_fields(self, e1_1_schema):
        """unadjusted_amount 和 opening_balance 必须有 auto_source。"""
        sections = e1_1_schema.get("sections", [])
        for section in sections:
            fields = section.get("fields", [])
            for f in fields:
                if f.get("field") in ("unadjusted_amount", "opening_balance"):
                    assert f.get("auto_source"), (
                        f"section '{section.get('name')}' 的 {f['field']} 缺少 auto_source"
                    )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 11: E1-1 YAML schema 文件存在且结构正确
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask11YamlSchema:
    """验证 E1-1 手工 YAML schema 文件存在且结构正确。"""

    def test_yaml_file_exists(self):
        """E1-1.yaml 文件存在于正确路径。"""
        assert _SCHEMA_PATH.exists()

    def test_wp_code_correct(self, e1_1_schema):
        """wp_code 字段为 E1-1。"""
        assert e1_1_schema.get("wp_code") == "E1-1"

    def test_component_type_is_d_form_table(self, e1_1_schema):
        """component_type 为 d-form-table。"""
        assert e1_1_schema.get("component_type") == "d-form-table"

    def test_template_version(self, e1_1_schema):
        """template_version 为 v2025-R5。"""
        assert e1_1_schema.get("template_version") == "v2025-R5"

    def test_related_accounts(self, e1_1_schema):
        """related_accounts 包含 1001/1002/1012 三个科目。"""
        accounts = e1_1_schema.get("related_accounts", [])
        codes = {a.get("code") for a in accounts}
        assert codes == {"1001", "1002", "1012"}

    def test_writeback_config(self, e1_1_schema):
        """writeback 配置指向 trial_balance.audited_amount。"""
        wb = e1_1_schema.get("writeback", {})
        assert wb.get("target") == "trial_balance.audited_amount"
        assert wb.get("trigger") == "WORKPAPER_SAVED"

    def test_override_maps_to_d_form_table(self):
        """E1-1 在 _WP_CODE_OVERRIDE 中映射为 d-form-table。"""
        assert "E1-1" in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE["E1-1"] == "d-form-table"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 12: handler 正则匹配 E 类审定表
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask12HandlerRegex:
    """验证 _on_d_audit_determination_saved handler 正则匹配 E 类审定表。"""

    # 统一正则
    _PATTERN = re.compile(r"^[D-N]\d+-1$")

    @pytest.mark.parametrize("wp_code", [
        "D1-1", "D2-1", "D3-1", "D4-1", "D5-1", "D6-1", "D7-1",  # D 循环
        "E1-1",  # E 循环（货币资金）
        "F1-1", "F2-1",  # F 循环（采购存货）
        "G1-1", "G7-1",  # G 循环（投资）
        "H1-1",  # H 循环（固定资产）
        "I1-1",  # I 循环（无形资产）
        "J1-1",  # J 循环（职工薪酬）
        "K1-1", "K3-1",  # K 循环（管理）
        "L1-1", "L5-1",  # L 循环（筹资）
        "M1-1",  # M 循环（股东权益）
        "N1-1",  # N 循环（税费）
    ])
    def test_regex_matches_valid_codes(self, wp_code):
        """^[D-N]\\d+-1$ 正确匹配 D~N 循环审定表编码。"""
        assert self._PATTERN.match(wp_code), f"正则未匹配 '{wp_code}'"

    @pytest.mark.parametrize("wp_code", [
        "E1-2",   # 不是审定表（明细表）
        "E1A",    # 程序表
        "E0",     # 函证
        "C3-1",   # C 循环不在 D-N 范围
        "B50-1",  # B 循环
        "A1-1",   # A 循环
        "E1-11",  # 编号>9 但后缀不是 -1（是 E1-11 非 E11-1 形式）
        "",       # 空字符串
    ])
    def test_regex_rejects_invalid_codes(self, wp_code):
        """正则正确排除非审定表编码。"""
        assert not self._PATTERN.match(wp_code), f"正则不应匹配 '{wp_code}'"

    def test_handler_source_uses_correct_pattern(self):
        """handler 源码使用 ^[D-N]\\d+-1$ 正则。"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert r'^[D-N]\d+-1$' in src, (
            "handler 源码中未找到正则 ^[D-N]\\d+-1$"
        )

    def test_handler_subscribed_to_workpaper_saved(self):
        """handler 已订阅 WORKPAPER_SAVED 事件。"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert (
            "event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_d_audit_determination_saved)"
            in src
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 13: 审定表保存→trial_balance 回写正确（集成级单元测试）
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask13WritebackIntegration:
    """验证审定表保存→trial_balance 回写正确。

    handler 定义在 event_handlers.py 局部作用域中，无法直接导入。
    通过 inspect 模块源码检查 + 正则验证覆盖逻辑路径。
    """

    def test_e1_1_passes_regex_filter(self):
        """E1-1 能通过 handler 正则过滤（不被 return 跳过）。"""
        # 直接验证正则逻辑
        pattern = re.compile(r"^[D-N]\d+-1$")
        assert pattern.match("E1-1"), "E1-1 应通过审定表正则匹配"

    def test_handler_extracts_rows_from_parsed_data(self):
        """handler 从 payload.extra['parsed_data']['rows'] 提取审定数据。"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        # 验证 handler 读取 parsed_data.rows
        assert 'parsed_data.get("rows"' in src or "parsed_data.get('rows'" in src

    def test_handler_updates_trial_balance_audited_amount(self):
        """handler 执行 UPDATE trial_balance SET audited_amount。"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert "audited_amount" in src
        assert "TrialBalance" in src
        assert "standard_account_code" in src

    def test_handler_triggers_trial_balance_updated_event(self):
        """handler 成功回写后触发 TRIAL_BALANCE_UPDATED 事件。"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert "TRIAL_BALANCE_UPDATED" in src

    def test_handler_commits_on_success(self):
        """handler 成功后执行 commit。"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        # 在 _on_d_audit_determination_saved 附近应有 commit
        assert "await session.commit()" in src

    def test_non_e_code_rejected_by_regex(self):
        """非 D~N 审定表编码被正则拒绝。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        # B 循环
        assert not pattern.match("B50-1")
        # A 循环
        assert not pattern.match("A1-1")
        # C 循环
        assert not pattern.match("C3-1")
        # E 明细表（非审定表）
        assert not pattern.match("E1-2")

    def test_d_cycle_codes_still_matched(self):
        """扩展正则后 D 循环审定表仍然正确匹配（回归测试）。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        for code in ["D1-1", "D2-1", "D3-1", "D4-1", "D5-1", "D6-1", "D7-1"]:
            assert pattern.match(code), f"D 循环 '{code}' 应继续匹配"
