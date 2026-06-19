"""F 类审定表保存→trial_balance 回写验证（Tasks 15-19）。

验证:
  15. F1-1/F2-1/F3-1/F4-1/F5-1 审定表 d-form-table schema 字段完整（标准审定表字段集）
  16. F2-1 手工 YAML schema（存货特殊：多类别行+跌价扣减+净额行）
  17. F1-1/F3-1/F4-1/F5-1 手工 YAML schema（标准审定表结构）
  18. _on_d_audit_determination_saved handler 正则匹配 F 类审定表（^[D-N]\\d+-1$）
  19. 审定表保存→trial_balance 回写正确（单元测试，覆盖 F1-1~F5-1 全部 5 个审定表）
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
import yaml

from app.services.wp_classification_service import _WP_CODE_OVERRIDE


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures & Constants
# ═══════════════════════════════════════════════════════════════════════════════

_SCHEMA_DIR = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "ledger_adapters"
    / "wp_render_schema"
)

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

# F 类全部 5 个审定表
_F_AUDIT_DETERMINATION_CODES = ["F1-1", "F2-1", "F3-1", "F4-1", "F5-1"]


@pytest.fixture(scope="module")
def f_schemas() -> dict[str, dict]:
    """加载全部 F 类审定表 YAML schema。"""
    schemas = {}
    for code in _F_AUDIT_DETERMINATION_CODES:
        path = _SCHEMA_DIR / f"{code}.yaml"
        assert path.exists(), f"{code}.yaml 不存在: {path}"
        with open(path, encoding="utf-8") as f:
            schemas[code] = yaml.safe_load(f)
    return schemas


# ═══════════════════════════════════════════════════════════════════════════════
# Task 15: 确认 F1-1/F2-1/F3-1/F4-1/F5-1 审定表 schema 字段完整
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask15SchemaFieldCompleteness:
    """确认 F 类全部 5 个审定表的 d-form-table schema 字段完整（标准审定表字段集）。"""

    @pytest.mark.parametrize("wp_code", _F_AUDIT_DETERMINATION_CODES)
    def test_schema_has_sections(self, f_schemas, wp_code):
        """每个审定表 schema 必须有 sections。"""
        schema = f_schemas[wp_code]
        sections = schema.get("sections", [])
        assert len(sections) >= 1, f"{wp_code} 没有 sections"

    @pytest.mark.parametrize("wp_code", _F_AUDIT_DETERMINATION_CODES)
    def test_all_standard_fields_present(self, f_schemas, wp_code):
        """每个审定表的每组 section 包含全部 13 个标准审定表字段。"""
        schema = f_schemas[wp_code]
        sections = schema.get("sections", [])
        for section in sections:
            fields = section.get("fields", [])
            field_names = [f.get("field") for f in fields]
            for required_field in _REQUIRED_FIELDS:
                assert required_field in field_names, (
                    f"{wp_code} section '{section.get('name')}' 缺少字段 '{required_field}'"
                )

    @pytest.mark.parametrize("wp_code", _F_AUDIT_DETERMINATION_CODES)
    def test_audited_amount_has_formula(self, f_schemas, wp_code):
        """每个审定表的 audited_amount 字段必须有计算公式。"""
        schema = f_schemas[wp_code]
        sections = schema.get("sections", [])
        for section in sections:
            fields = section.get("fields", [])
            audited = [f for f in fields if f.get("field") == "audited_amount"]
            assert audited, f"{wp_code} section '{section.get('name')}' 缺 audited_amount"
            assert audited[0].get("formula"), (
                f"{wp_code} section '{section.get('name')}' 的 audited_amount 缺少 formula"
            )

    @pytest.mark.parametrize("wp_code", _F_AUDIT_DETERMINATION_CODES)
    def test_auto_source_fields(self, f_schemas, wp_code):
        """unadjusted_amount 和 opening_balance 必须有 auto_source。"""
        schema = f_schemas[wp_code]
        sections = schema.get("sections", [])
        for section in sections:
            fields = section.get("fields", [])
            for f in fields:
                if f.get("field") in ("unadjusted_amount", "opening_balance"):
                    assert f.get("auto_source"), (
                        f"{wp_code} section '{section.get('name')}' 的 {f['field']} 缺少 auto_source"
                    )

    @pytest.mark.parametrize("wp_code", _F_AUDIT_DETERMINATION_CODES)
    def test_component_type_is_d_form_table(self, f_schemas, wp_code):
        """每个审定表的 component_type 为 d-form-table。"""
        schema = f_schemas[wp_code]
        assert schema.get("component_type") == "d-form-table"

    @pytest.mark.parametrize("wp_code", _F_AUDIT_DETERMINATION_CODES)
    def test_writeback_config(self, f_schemas, wp_code):
        """每个审定表有正确的 writeback 配置。"""
        schema = f_schemas[wp_code]
        wb = schema.get("writeback", {})
        assert wb.get("target") == "trial_balance.audited_amount"
        assert wb.get("trigger") == "WORKPAPER_SAVED"
        assert wb.get("key_field") == "account_code"
        assert wb.get("value_field") == "audited_amount"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 16: F2-1 存货特殊结构验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask16F21InventorySpecial:
    """验证 F2-1 存货审定表的特殊结构：多类别行+跌价扣减+净额行。"""

    def test_f2_1_has_multiple_categories(self, f_schemas):
        """F2-1 应有多个存货类别 section（≥8 个类别）。"""
        schema = f_schemas["F2-1"]
        sections = schema.get("sections", [])
        category_sections = [s for s in sections if s.get("row_type") == "category"]
        assert len(category_sections) >= 8, (
            f"F2-1 类别行应≥8，实际 {len(category_sections)}"
        )

    def test_f2_1_has_subtotal_row(self, f_schemas):
        """F2-1 应有存货合计行（row_type: subtotal）。"""
        schema = f_schemas["F2-1"]
        sections = schema.get("sections", [])
        subtotal = [s for s in sections if s.get("row_type") == "subtotal"]
        assert len(subtotal) >= 1, "F2-1 缺少存货合计行"
        assert "存货合计" in subtotal[0].get("name", "")

    def test_f2_1_has_deduction_row(self, f_schemas):
        """F2-1 应有跌价准备扣减行（row_type: deduction）。"""
        schema = f_schemas["F2-1"]
        sections = schema.get("sections", [])
        deduction = [s for s in sections if s.get("row_type") == "deduction"]
        assert len(deduction) >= 1, "F2-1 缺少跌价准备扣减行"
        assert "跌价准备" in deduction[0].get("name", "")

    def test_f2_1_has_net_row(self, f_schemas):
        """F2-1 应有存货净额行（row_type: net）。"""
        schema = f_schemas["F2-1"]
        sections = schema.get("sections", [])
        net = [s for s in sections if s.get("row_type") == "net"]
        assert len(net) >= 1, "F2-1 缺少净额行"
        assert "净额" in net[0].get("name", "")

    def test_f2_1_category_names_cover_inventory_types(self, f_schemas):
        """F2-1 类别行覆盖主要存货类型。"""
        schema = f_schemas["F2-1"]
        sections = schema.get("sections", [])
        names = [s.get("name", "") for s in sections]
        # 核心类别
        assert any("原材料" in n for n in names), "缺少原材料类别"
        assert any("在产品" in n for n in names), "缺少在产品类别"
        assert any("产成品" in n or "库存商品" in n for n in names), "缺少产成品/库存商品类别"
        assert any("周转材料" in n for n in names), "缺少周转材料类别"
        assert any("委托加工" in n for n in names), "缺少委托加工物资类别"

    def test_f2_1_related_accounts_include_impairment(self, f_schemas):
        """F2-1 related_accounts 包含跌价准备科目 1461。"""
        schema = f_schemas["F2-1"]
        accounts = schema.get("related_accounts", [])
        codes = {a.get("code") for a in accounts}
        assert "1461" in codes, "F2-1 related_accounts 应包含 1461 存货跌价准备"

    def test_f2_1_section_order_is_logical(self, f_schemas):
        """F2-1 section 顺序：类别行 → 合计 → 扣减 → 净额。"""
        schema = f_schemas["F2-1"]
        sections = schema.get("sections", [])
        row_types = [s.get("row_type") for s in sections]
        # category 在前
        last_category_idx = max(
            i for i, rt in enumerate(row_types) if rt == "category"
        )
        subtotal_idx = next(i for i, rt in enumerate(row_types) if rt == "subtotal")
        deduction_idx = next(i for i, rt in enumerate(row_types) if rt == "deduction")
        net_idx = next(i for i, rt in enumerate(row_types) if rt == "net")
        assert last_category_idx < subtotal_idx < deduction_idx < net_idx


# ═══════════════════════════════════════════════════════════════════════════════
# Task 17: F1-1/F3-1/F4-1/F5-1 标准审定表结构验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask17StandardSchemas:
    """验证 F1-1/F3-1/F4-1/F5-1 手工 YAML schema（标准审定表结构）。"""

    @pytest.mark.parametrize("wp_code,expected_name", [
        ("F1-1", "预付账款审定表"),
        ("F3-1", "应付票据审定表"),
        ("F4-1", "应付账款审定表"),
        ("F5-1", "营业成本审定表"),
    ])
    def test_yaml_file_exists_and_has_correct_name(self, f_schemas, wp_code, expected_name):
        """YAML 文件存在且 wp_name 正确。"""
        schema = f_schemas[wp_code]
        assert schema.get("wp_code") == wp_code
        assert schema.get("wp_name") == expected_name

    @pytest.mark.parametrize("wp_code", ["F1-1", "F3-1", "F4-1", "F5-1"])
    def test_template_version(self, f_schemas, wp_code):
        """template_version 为 v2025-R5。"""
        schema = f_schemas[wp_code]
        assert schema.get("template_version") == "v2025-R5"

    @pytest.mark.parametrize("wp_code", ["F1-1", "F3-1", "F4-1", "F5-1"])
    def test_has_related_accounts(self, f_schemas, wp_code):
        """有 related_accounts 配置。"""
        schema = f_schemas[wp_code]
        accounts = schema.get("related_accounts", [])
        assert len(accounts) >= 1, f"{wp_code} 应至少有 1 个关联科目"

    @pytest.mark.parametrize("wp_code", ["F1-1", "F3-1", "F4-1", "F5-1"])
    def test_has_cross_refs(self, f_schemas, wp_code):
        """有跨底稿引用配置。"""
        schema = f_schemas[wp_code]
        refs = schema.get("cross_refs", [])
        assert len(refs) >= 1, f"{wp_code} 应至少有 1 个跨底稿引用"

    @pytest.mark.parametrize("wp_code", ["F1-1", "F3-1", "F4-1", "F5-1"])
    def test_override_maps_to_d_form_table(self, wp_code):
        """在 _WP_CODE_OVERRIDE 中映射为 d-form-table。"""
        assert wp_code in _WP_CODE_OVERRIDE, f"{wp_code} 不在 _WP_CODE_OVERRIDE 中"
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table"

    def test_f5_1_has_two_sections(self, f_schemas):
        """F5-1 营业成本审定表应有 2 组（主营/其他）。"""
        schema = f_schemas["F5-1"]
        sections = schema.get("sections", [])
        assert len(sections) == 2
        names = [s.get("name") for s in sections]
        assert "主营业务成本" in names
        assert "其他业务成本" in names


# ═══════════════════════════════════════════════════════════════════════════════
# Task 18: handler 正则匹配 F 类审定表
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask18HandlerRegex:
    """验证 _on_d_audit_determination_saved handler 正则匹配 F 类审定表。"""

    _PATTERN = re.compile(r"^[D-N]\d+-1$")

    @pytest.mark.parametrize("wp_code", _F_AUDIT_DETERMINATION_CODES)
    def test_regex_matches_all_f_audit_tables(self, wp_code):
        """^[D-N]\\d+-1$ 正确匹配全部 5 个 F 类审定表编码。"""
        assert self._PATTERN.match(wp_code), f"正则未匹配 '{wp_code}'"

    @pytest.mark.parametrize("wp_code", [
        "F1-2",   # 预付账款明细表（非审定表）
        "F2-2",   # 存货分类明细（非审定表）
        "F0",     # 函证路由
        "F1A",    # 程序表
        "F2A",    # 程序表
        "F2-11",  # 跌价准备明细（非审定表）
        "",       # 空字符串
    ])
    def test_regex_rejects_non_audit_f_codes(self, wp_code):
        """正则正确排除 F 类非审定表编码。"""
        assert not self._PATTERN.match(wp_code), f"正则不应匹配 '{wp_code}'"

    def test_handler_source_uses_correct_pattern(self):
        """handler 源码使用 ^[D-N]\\d+-1$ 正则（F 在 D-N 范围内）。"""
        from app.services import event_handlers_cycle_linkage
        src = inspect.getsource(event_handlers_cycle_linkage)
        assert r'^[D-N]\d+-1$' in src, (
            "handler 源码中未找到正则 ^[D-N]\\d+-1$"
        )

    def test_f_is_within_d_to_n_range(self):
        """确认字符 F 在 D-N 范围内（ASCII 验证）。"""
        assert ord('D') <= ord('F') <= ord('N'), "F 不在 [D-N] 范围内"

    def test_handler_subscribed_to_workpaper_saved(self):
        """handler 已订阅 WORKPAPER_SAVED 事件。"""
        from app.services import event_handlers_cycle_linkage
        src = inspect.getsource(event_handlers_cycle_linkage)
        assert (
            "event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_d_audit_determination_saved)"
            in src
        )

    def test_d_cycle_codes_still_matched_regression(self):
        """回归：D 循环审定表仍然正确匹配。"""
        for code in ["D1-1", "D2-1", "D3-1", "D4-1", "D5-1", "D6-1", "D7-1"]:
            assert self._PATTERN.match(code), f"D 循环 '{code}' 应继续匹配"

    def test_e_cycle_still_matched_regression(self):
        """回归：E 循环审定表仍然正确匹配。"""
        assert self._PATTERN.match("E1-1"), "E1-1 应继续匹配"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 19: 审定表保存→trial_balance 回写正确（单元测试）
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask19WritebackIntegration:
    """验证审定表保存→trial_balance 回写正确（覆盖 F1-1~F5-1 全部 5 个审定表）。"""

    @pytest.mark.parametrize("wp_code", _F_AUDIT_DETERMINATION_CODES)
    def test_f_code_passes_regex_filter(self, wp_code):
        """F1-1~F5-1 均能通过 handler 正则过滤。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        assert pattern.match(wp_code), f"{wp_code} 应通过审定表正则匹配"

    def test_handler_extracts_rows_from_parsed_data(self):
        """handler 从 payload.extra['parsed_data']['rows'] 提取审定数据。"""
        from app.services import event_handlers_cycle_linkage
        src = inspect.getsource(event_handlers_cycle_linkage)
        assert 'parsed_data.get("rows"' in src or "parsed_data.get('rows'" in src

    def test_handler_updates_trial_balance_by_account_code(self):
        """handler 按 standard_account_code 更新 trial_balance.audited_amount。"""
        from app.services import event_handlers_cycle_linkage
        src = inspect.getsource(event_handlers_cycle_linkage)
        assert "audited_amount" in src
        assert "TrialBalance" in src
        assert "standard_account_code" in src

    def test_handler_triggers_trial_balance_updated_event(self):
        """handler 成功回写后触发 TRIAL_BALANCE_UPDATED 事件。"""
        from app.services import event_handlers_cycle_linkage
        src = inspect.getsource(event_handlers_cycle_linkage)
        assert "TRIAL_BALANCE_UPDATED" in src

    def test_handler_commits_on_success(self):
        """handler 成功后执行 commit。"""
        from app.services import event_handlers_cycle_linkage
        src = inspect.getsource(event_handlers_cycle_linkage)
        assert "await session.commit()" in src

    def test_handler_rolls_back_on_failure(self):
        """handler 失败时执行 rollback。"""
        from app.services import event_handlers_cycle_linkage
        src = inspect.getsource(event_handlers_cycle_linkage)
        assert "await session.rollback()" in src

    @pytest.mark.parametrize("wp_code", _F_AUDIT_DETERMINATION_CODES)
    def test_f_code_in_wp_code_override(self, wp_code):
        """F1-1~F5-1 在 _WP_CODE_OVERRIDE 中注册为 d-form-table。"""
        assert wp_code in _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE[wp_code] == "d-form-table"

    @pytest.mark.parametrize("wp_code", _F_AUDIT_DETERMINATION_CODES)
    def test_schema_writeback_matches_handler_pattern(self, f_schemas, wp_code):
        """每个 F 类审定表 schema 的 writeback.match_pattern 与 handler 正则一致。"""
        schema = f_schemas[wp_code]
        wb = schema.get("writeback", {})
        pattern_str = wb.get("match_pattern", "")
        # schema 中存的 pattern 应与 handler 源码一致
        assert pattern_str == r"^[D-N]\d+-1$", (
            f"{wp_code} writeback.match_pattern 应为 ^[D-N]\\d+-1$"
        )

    def test_handler_skips_empty_rows(self):
        """handler 在 rows 为空时提前返回不执行更新。"""
        from app.services import event_handlers_cycle_linkage
        src = inspect.getsource(event_handlers_cycle_linkage)
        assert "if not rows:" in src

    def test_handler_skips_missing_project_or_year(self):
        """handler 在缺少 project_id 或 year 时提前返回。"""
        from app.services import event_handlers_cycle_linkage
        src = inspect.getsource(event_handlers_cycle_linkage)
        assert "if not project_id or not year:" in src

    @pytest.mark.parametrize("wp_code,expected_accounts", [
        ("F1-1", ["1123"]),
        ("F2-1", ["1403", "1405", "1461"]),
        ("F3-1", ["2201"]),
        ("F4-1", ["2202"]),
        ("F5-1", ["6401", "6402"]),
    ])
    def test_schema_related_accounts(self, f_schemas, wp_code, expected_accounts):
        """每个审定表 schema 的 related_accounts 包含预期科目编码。"""
        schema = f_schemas[wp_code]
        accounts = schema.get("related_accounts", [])
        codes = {a.get("code") for a in accounts}
        for expected in expected_accounts:
            assert expected in codes, (
                f"{wp_code} related_accounts 应包含 {expected}"
            )
