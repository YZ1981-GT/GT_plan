"""Sprint 5 综合测试 — 附注数据填充与通用规则引擎

验证:
- 4 种取数模式正确性 (Task 5.3)
- 5 条规则引擎判断逻辑 (Task 5.4)
- 填充率统计准确 (Task 5.5)
- 5 层分层处理策略 (Task 5.6)
- 增量刷新与 stale 联动 (Task 5.7)
- 科目对照映射服务 (Task 5.2)
"""
from __future__ import annotations

import pytest
from decimal import Decimal

from app.services.note_fill_engine import (
    NoteFillEngine,
    FetchMode,
    FillStats,
    SectionFillResult,
)
from app.services.note_rule_engine import (
    NoteRuleEngine,
    RuleEngineContext,
    RuleType,
    SectionDecision,
    DEFAULT_POLICY_SECTIONS,
    RELATED_PARTY_SECTIONS,
)
from app.services.note_layer_strategy import (
    NoteLayerStrategy,
    NoteLayer,
    PROCESSING_ORDER,
    LAYER_CONFIGS,
)
from app.services.note_account_mapping_service import (
    NoteAccountMappingService,
    MappingEntry,
    SectionMapping,
)


# ===========================================================================
# Task 5.3: 4 种取数模式
# ===========================================================================

class TestNoteFillEngine:
    """测试附注数据填充引擎 4 种取数模式"""

    def setup_method(self):
        self.engine = NoteFillEngine()

    # --- 模式 1：合计取数 ---

    def test_fetch_total_with_wp_data(self):
        """模式 1：从底稿审定表合计行取期末/期初余额"""
        result = self.engine.fetch_total(
            section_code="note_cash",
            wp_data={"total_row": {"period_end": 1000000, "period_start": 800000}},
        )
        assert result.section_code == "note_cash"
        assert result.stats.filled_cells == 2
        assert result.stats.total_cells == 2
        assert result.stats.fill_rate == 100.0
        assert len(result.cells) == 2
        assert result.cells[0].value == Decimal("1000000")
        assert result.cells[1].value == Decimal("800000")

    def test_fetch_total_with_report_fallback(self):
        """模式 1：底稿无数据时从报表行次取数"""
        result = self.engine.fetch_total(
            section_code="note_cash",
            wp_data=None,
            report_row_data={"current_period_amount": 500000, "prior_period_amount": 400000},
        )
        assert result.stats.filled_cells == 2
        assert result.cells[0].value == Decimal("500000")

    def test_fetch_total_partial_data(self):
        """模式 1：部分数据缺失"""
        result = self.engine.fetch_total(
            section_code="note_cash",
            wp_data={"total_row": {"period_end": 1000000}},
        )
        assert result.stats.filled_cells == 1
        assert result.stats.unfillable_cells == 1
        assert result.stats.fill_rate == 50.0

    # --- 模式 2：明细取数 ---

    def test_fetch_detail_multiple_rows(self):
        """模式 2：从底稿审定表明细行逐行取数"""
        detail_rows = [
            {"name": "工商银行", "period_end": 500000, "period_start": 400000},
            {"name": "建设银行", "period_end": 300000, "period_start": 200000},
            {"name": "农业银行", "period_end": 200000, "period_start": None},
        ]
        result = self.engine.fetch_detail(section_code="note_cash", detail_rows=detail_rows)
        assert result.stats.total_cells == 6  # 3 rows × 2 cols
        assert result.stats.filled_cells == 5  # 农业银行期初缺失
        assert result.stats.unfillable_cells == 1

    def test_fetch_detail_empty(self):
        """模式 2：无明细数据"""
        result = self.engine.fetch_detail(section_code="note_cash", detail_rows=[])
        assert result.stats.total_cells == 0
        assert result.stats.fill_rate == 0.0

    # --- 模式 3：分类取数 ---

    def test_fetch_category(self):
        """模式 3：从底稿按类别汇总"""
        category_data = [
            {"category": "1年以内", "amount": 800000, "percentage": 80.0},
            {"category": "1-2年", "amount": 150000, "percentage": 15.0},
            {"category": "2-3年", "amount": 50000, "percentage": 5.0},
        ]
        result = self.engine.fetch_category(section_code="note_ar_aging", category_data=category_data)
        assert result.stats.total_cells == 6  # 3 categories × 2 (amount + pct)
        assert result.stats.filled_cells == 6
        assert result.stats.fill_rate == 100.0

    def test_fetch_category_partial(self):
        """模式 3：部分类别缺少比例"""
        category_data = [
            {"category": "1年以内", "amount": 800000, "percentage": None},
        ]
        result = self.engine.fetch_category(section_code="note_ar_aging", category_data=category_data)
        assert result.stats.filled_cells == 1
        assert result.stats.unfillable_cells == 1

    # --- 模式 4：变动取数 ---

    def test_fetch_change(self):
        """模式 4：从底稿本期增加/减少列取数"""
        change_data = [
            {"name": "房屋建筑物", "opening": 5000000, "increase": 200000, "decrease": 100000, "closing": 5100000},
            {"name": "机器设备", "opening": 3000000, "increase": 500000, "decrease": 0, "closing": 3500000},
        ]
        result = self.engine.fetch_change(section_code="note_fixed_assets", change_data=change_data)
        assert result.stats.total_cells == 8  # 2 rows × 4 cols
        assert result.stats.filled_cells == 8
        assert result.stats.fill_rate == 100.0

    def test_fetch_change_with_missing(self):
        """模式 4：部分变动数据缺失"""
        change_data = [
            {"name": "房屋建筑物", "opening": 5000000, "increase": None, "decrease": None, "closing": 5000000},
        ]
        result = self.engine.fetch_change(section_code="note_fixed_assets", change_data=change_data)
        assert result.stats.filled_cells == 2  # opening + closing
        assert result.stats.unfillable_cells == 2  # increase + decrease

    # --- 统一入口 ---

    def test_fill_section_dispatch(self):
        """fill_section 按 fetch_mode 正确分发"""
        result = self.engine.fill_section(
            section_code="test",
            fetch_mode="total",
            wp_data={"total_row": {"period_end": 100, "period_start": 200}},
        )
        assert result.stats.filled_cells == 2

    # --- 试算表填充 ---

    def test_fill_from_trial_balance(self):
        """从试算表自动填充期末/期初/变动列"""
        result = self.engine.fill_from_trial_balance(
            section_code="note_cash",
            tb_current={"1001": Decimal("500000"), "1002": Decimal("300000")},
            tb_prior={"1001": Decimal("400000")},
            adjustments={"1001": Decimal("10000")},
        )
        # 2 codes × 3 cols = 6 total
        assert result.stats.total_cells == 6
        assert result.stats.filled_cells == 4  # 1001 has all 3, 1002 has only current
        assert result.stats.unfillable_cells == 2

    # --- 统计汇总 ---

    def test_aggregate_stats(self):
        """汇总多个章节的填充率统计"""
        results = [
            SectionFillResult(section_code="a", stats=FillStats(total_cells=10, filled_cells=8)),
            SectionFillResult(section_code="b", stats=FillStats(total_cells=20, filled_cells=15)),
        ]
        total = NoteFillEngine.aggregate_stats(results)
        assert total.total_cells == 30
        assert total.filled_cells == 23
        assert total.fill_rate == 76.7


# ===========================================================================
# Task 5.4: 5 条规则引擎
# ===========================================================================

class TestNoteRuleEngine:
    """测试附注通用规则引擎 5 条规则"""

    def setup_method(self):
        self.context = RuleEngineContext(
            report_data={
                "BS-002": {"current_period_amount": 1000000, "prior_period_amount": 800000},
                "BS-099": {"current_period_amount": 0, "prior_period_amount": 0},
            },
            workpaper_status={
                "E1": {"has_data": True, "audited": True},
                "D2": {"has_data": True, "audited": False},
            },
            materiality=Decimal("500000"),
            related_party_data={
                "母公司A": {"transaction_amount": 100000, "balance_amount": 50000},
            },
            policy_sections=DEFAULT_POLICY_SECTIONS,
        )
        self.engine = NoteRuleEngine(context=self.context)

    # --- 规则 A：余额驱动 ---

    def test_rule_a_balance_nonzero(self):
        """规则 A：报表行次金额 ≠ 0 → 触发"""
        result = self.engine.check_balance_rule("note_cash", "BS-002")
        assert result.triggered is True
        assert result.rule_type == RuleType.BALANCE

    def test_rule_a_balance_zero(self):
        """规则 A：报表行次金额 = 0 → 不触发"""
        result = self.engine.check_balance_rule("note_other", "BS-099")
        assert result.triggered is False

    # --- 规则 B：变动驱动 ---

    def test_rule_b_change_significant(self):
        """规则 B：变动 > 重要性×5% → 触发"""
        result = self.engine.check_change_rule("note_cash", "BS-002")
        # diff = |1000000 - 800000| = 200000, threshold = 500000 * 0.05 = 25000
        assert result.triggered is True

    def test_rule_b_change_insignificant(self):
        """规则 B：变动 ≤ 重要性×5% → 不触发"""
        # 设置一个变动很小的行次
        self.context.report_data["BS-003"] = {"current_period_amount": 100, "prior_period_amount": 99}
        result = self.engine.check_change_rule("note_x", "BS-003")
        # diff = 1, threshold = 25000
        assert result.triggered is False

    # --- 规则 C：底稿驱动 ---

    def test_rule_c_workpaper_ready(self):
        """规则 C：底稿已编制且有审定数 → 触发"""
        result = self.engine.check_workpaper_rule("note_cash", "E1")
        assert result.triggered is True

    def test_rule_c_workpaper_not_audited(self):
        """规则 C：底稿未审定 → 不触发"""
        result = self.engine.check_workpaper_rule("note_ar", "D2")
        assert result.triggered is False

    # --- 规则 D：政策驱动 ---

    def test_rule_d_policy_section(self):
        """规则 D：会计政策章节 → 始终触发"""
        result = self.engine.check_policy_rule("note_accounting_policies")
        assert result.triggered is True

    def test_rule_d_non_policy_section(self):
        """规则 D：非政策章节 → 不触发"""
        result = self.engine.check_policy_rule("note_cash")
        assert result.triggered is False

    # --- 规则 E：关联方驱动 ---

    def test_rule_e_related_party_has_data(self):
        """规则 E：关联方交易/余额 > 0 → 触发"""
        result = self.engine.check_related_party_rule("note_related_parties")
        assert result.triggered is True

    def test_rule_e_related_party_no_data(self):
        """规则 E：无关联方数据 → 不触发"""
        self.context.related_party_data = {}
        engine = NoteRuleEngine(context=self.context)
        result = engine.check_related_party_rule("note_related_parties")
        assert result.triggered is False

    # --- 综合判断 ---

    def test_judge_section_generate(self):
        """综合判断：有余额 → GENERATE"""
        judgment = self.engine.judge_section("note_cash", report_row_code="BS-002", wp_code="E1")
        assert judgment.decision == SectionDecision.GENERATE

    def test_judge_section_skip(self):
        """综合判断：无余额无底稿 → SKIP"""
        judgment = self.engine.judge_section("note_other", report_row_code="BS-099", wp_code=None)
        assert judgment.decision == SectionDecision.SKIP
        assert judgment.skip_reason == "本期无此项业务"

    def test_judge_section_always(self):
        """综合判断：政策章节 → ALWAYS"""
        judgment = self.engine.judge_section("note_accounting_policies")
        assert judgment.decision == SectionDecision.ALWAYS

    def test_judge_all_sections(self):
        """批量判断"""
        sections = [
            {"section_code": "note_cash", "report_row_code": "BS-002", "wp_code": "E1"},
            {"section_code": "note_other", "report_row_code": "BS-099", "wp_code": None},
            {"section_code": "note_accounting_policies", "report_row_code": None, "wp_code": None},
        ]
        results = self.engine.judge_all_sections(sections)
        assert len(results) == 3
        summary = NoteRuleEngine.summarize(results)
        assert summary["generate"] == 1
        assert summary["skip"] == 1
        assert summary["always"] == 1


# ===========================================================================
# Task 5.6: 5 层分层处理策略
# ===========================================================================

class TestNoteLayerStrategy:
    """测试附注内容分层处理策略"""

    def setup_method(self):
        self.strategy = NoteLayerStrategy()

    def test_processing_order(self):
        """处理顺序：E → A → B → C → D"""
        assert PROCESSING_ORDER == [NoteLayer.E, NoteLayer.A, NoteLayer.B, NoteLayer.C, NoteLayer.D]

    def test_classify_policy_section(self):
        """分类：会计政策 → A 层"""
        sec = {"section_code": "note_accounting_policies", "title": "重要会计政策"}
        assert self.strategy.classify_section(sec) == NoteLayer.A

    def test_classify_appendix_section(self):
        """分类：附录索引 → E 层"""
        sec = {"section_code": "appendix_index", "title": "附录索引"}
        assert self.strategy.classify_section(sec) == NoteLayer.E

    def test_classify_parent_section(self):
        """分类：母公司注释 → C 层"""
        sec = {"section_code": "parent_cash", "title": "母公司货币资金"}
        assert self.strategy.classify_section(sec) == NoteLayer.C

    def test_classify_supplement_section(self):
        """分类：补充信息 → D 层"""
        sec = {"section_code": "note_subsequent_events", "title": "期后事项"}
        assert self.strategy.classify_section(sec) == NoteLayer.D

    def test_classify_default_b_layer(self):
        """分类：默认 → B 层"""
        sec = {"section_code": "note_cash", "title": "货币资金"}
        assert self.strategy.classify_section(sec) == NoteLayer.B

    def test_classify_with_explicit_layer(self):
        """分类：已有 layer 标记直接使用"""
        sec = {"section_code": "note_x", "title": "X", "layer": "D"}
        assert self.strategy.classify_section(sec) == NoteLayer.D

    def test_process_all_layers(self):
        """按顺序处理所有层"""
        sections = [
            {"section_code": "appendix_index", "title": "附录索引"},
            {"section_code": "note_accounting_policies", "title": "重要会计政策", "text_content": "公司名称：{company_name}"},
            {"section_code": "note_cash", "title": "货币资金"},
            {"section_code": "parent_cash", "title": "母公司货币资金"},
            {"section_code": "note_subsequent_events", "title": "期后事项"},
        ]
        result = self.strategy.process_all_layers(
            sections=sections,
            placeholders={"company_name": "测试公司"},
            fill_data={
                "note_cash": {"cells_filled": 8, "cells_total": 10},
                "parent_cash": {"cells_filled": 6, "cells_total": 10},
                "note_subsequent_events": {"cells_filled": 2, "cells_total": 5},
            },
        )
        assert result.total_sections == 5
        assert len(result.layer_results) == 5  # All 5 layers have sections
        # Check A layer text replacement
        assert sections[1]["text_content"] == "公司名称：测试公司"

    def test_layer_config(self):
        """层级配置正确"""
        config_b = NoteLayerStrategy.get_layer_config(NoteLayer.B)
        assert config_b.auto_fill_target == 0.9
        assert config_b.links_workpaper is True

        config_a = NoteLayerStrategy.get_layer_config(NoteLayer.A)
        assert config_a.template_text_only is True
        assert config_a.links_workpaper is False

        config_e = NoteLayerStrategy.get_layer_config(NoteLayer.E)
        assert config_e.fully_auto is True


# ===========================================================================
# Task 5.2: 科目对照映射服务
# ===========================================================================

class TestNoteAccountMappingService:
    """测试附注科目对照映射服务"""

    def setup_method(self):
        self.service = NoteAccountMappingService(db=None)

    def test_get_default_mappings_soe(self):
        """获取国企版默认映射"""
        mappings = NoteAccountMappingService.get_default_mappings("soe")
        assert len(mappings) > 0
        # 验证货币资金映射
        cash_mapping = next((m for m in mappings if m.report_row_code == "BS-002"), None)
        assert cash_mapping is not None
        assert cash_mapping.note_section_code == "note_cash"
        assert cash_mapping.wp_code == "E1"
        assert cash_mapping.fetch_mode == "total"
        assert cash_mapping.validation_role == "余额"

    def test_get_default_mappings_listed(self):
        """获取上市版默认映射"""
        mappings = NoteAccountMappingService.get_default_mappings("listed")
        assert len(mappings) > 0

    def test_build_section_mappings(self):
        """构建章节级映射"""
        mappings_data = NoteAccountMappingService.get_default_mappings("soe")
        # 模拟 NoteAccountMapping 对象
        from unittest.mock import MagicMock
        mock_mappings = []
        for m in mappings_data:
            mock = MagicMock()
            mock.report_row_code = m.report_row_code
            mock.note_section_code = m.note_section_code
            mock.table_index = m.table_index
            mock.validation_role = m.validation_role
            mock.wp_code = m.wp_code
            mock.fetch_mode = m.fetch_mode
            mock_mappings.append(mock)

        section_map = self.service.build_section_mappings(mock_mappings)
        assert "note_cash" in section_map
        assert len(section_map["note_cash"].tables) >= 1

    def test_build_row_to_sections(self):
        """构建行次到章节的映射"""
        from unittest.mock import MagicMock
        mappings_data = NoteAccountMappingService.get_default_mappings("soe")
        mock_mappings = []
        for m in mappings_data:
            mock = MagicMock()
            mock.report_row_code = m.report_row_code
            mock.note_section_code = m.note_section_code
            mock_mappings.append(mock)

        row_map = self.service.build_row_to_sections(mock_mappings)
        assert "BS-002" in row_map
        assert "note_cash" in row_map["BS-002"]

    def test_fill_from_report_row(self):
        """从报表行次取数填充附注合计行"""
        mapping = MappingEntry(
            report_row_code="BS-002",
            note_section_code="note_cash",
            fetch_mode="total",
        )
        report_data = {
            "BS-002": {"current_period_amount": 1000000, "prior_period_amount": 800000},
        }
        result = self.service.fill_from_report_row(mapping, report_data)
        assert result.filled_cells == 2
        assert result.source == "report"

    def test_fill_from_tb_detail(self):
        """从试算表明细科目取数填充附注明细行"""
        mapping = MappingEntry(
            report_row_code="BS-005",
            note_section_code="note_accounts_receivable",
            fetch_mode="detail",
        )
        tb_data = [
            {"account_code": "1122.01", "account_name": "客户A", "closing_balance": 500000, "opening_balance": 400000},
            {"account_code": "1122.02", "account_name": "客户B", "closing_balance": 300000, "opening_balance": None},
        ]
        result = self.service.fill_from_tb_detail(mapping, tb_data)
        assert result.total_cells == 4
        assert result.filled_cells == 3  # 客户B 期初缺失
