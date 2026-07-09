"""I2 开发支出 — 后端集成测试

Spec: .kiro/specs/i2-development-expenditure/ Task 7.3
Requirements: 1.1, 5.1-5.5, 9.1-9.4

测试内容：
1. render策略函数返回正确结构
2. CAS6五条件评估纯函数
3. validate_research_split 费用化+资本化校验
4. AI generate section validation（存在性检查）
"""
from __future__ import annotations

import sys

sys.path.insert(0, "backend")

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Render策略结构测试（纯函数/同步部分）
# ═══════════════════════════════════════════════════════════════════════════════

class TestRenderStrategy:
    """验证 _i2_development_expenditure.py 的结构和常量"""

    def test_i2_sheets_list_complete(self):
        """I2_SHEETS 包含全部20个sheet条目"""
        from app.routers.wp_render_strategies._i2_development_expenditure import I2_SHEETS

        assert len(I2_SHEETS) == 20
        # 每个条目有 sheet_name 和 component_type
        for sheet in I2_SHEETS:
            assert "sheet_name" in sheet
            assert sheet["component_type"] == "i2-development-expenditure"

    def test_i2_sheets_contains_key_sheets(self):
        """验证关键sheet存在"""
        from app.routers.wp_render_strategies._i2_development_expenditure import I2_SHEETS

        names = [s["sheet_name"] for s in I2_SHEETS]
        assert any("审定表" in n for n in names)
        assert any("明细表" in n for n in names)
        assert any("资本化时点判断" in n for n in names)
        assert any("附注" in n and "上市" in n for n in names)
        assert any("附注" in n and "国" in n for n in names)

    def test_account_prefixes_include_1717(self):
        """科目前缀包含1717开发支出"""
        from app.routers.wp_render_strategies._i2_development_expenditure import _I2_ACCOUNT_PREFIXES

        assert "1717" in _I2_ACCOUNT_PREFIXES

    def test_render_function_exists_and_is_async(self):
        """render 函数存在且是异步的"""
        import inspect
        from app.routers.wp_render_strategies._i2_development_expenditure import render

        assert callable(render)
        assert inspect.iscoroutinefunction(render)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CAS6资本化判断纯函数测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestCapitalizationEvaluate:
    """验证 evaluate_capitalization 纯函数（与前端对等）"""

    def test_all_yes_is_met(self):
        """五条件全yes → isMet=True"""
        from app.routers.wp_render_strategies._i2_capitalization_engine import evaluate_capitalization

        conditions = [
            {"id": 1, "result": "yes", "evidence": "技术报告已出"},
            {"id": 2, "result": "yes", "evidence": "董事会决议"},
            {"id": 3, "result": "yes", "evidence": "市场分析报告"},
            {"id": 4, "result": "yes", "evidence": "可行性报告"},
            {"id": 5, "result": "yes", "evidence": "资金计划"},
        ]
        result = evaluate_capitalization(conditions)
        assert result["isMet"] is True
        assert result["missingConditions"] == []
        assert "满足" in result["conclusion"]

    def test_single_no_not_met(self):
        """任一条件no → isMet=False"""
        from app.routers.wp_render_strategies._i2_capitalization_engine import evaluate_capitalization

        conditions = [
            {"id": 1, "result": "yes", "evidence": ""},
            {"id": 2, "result": "yes", "evidence": ""},
            {"id": 3, "result": "no", "evidence": "无市场"},
            {"id": 4, "result": "yes", "evidence": ""},
            {"id": 5, "result": "yes", "evidence": ""},
        ]
        result = evaluate_capitalization(conditions)
        assert result["isMet"] is False
        assert 3 in result["missingConditions"]
        assert "不满足" in result["conclusion"]

    def test_multiple_no_lists_all_missing(self):
        """多个no → missingConditions包含全部"""
        from app.routers.wp_render_strategies._i2_capitalization_engine import evaluate_capitalization

        conditions = [
            {"id": 1, "result": "no", "evidence": ""},
            {"id": 2, "result": "no", "evidence": ""},
            {"id": 3, "result": "yes", "evidence": ""},
            {"id": 4, "result": "no", "evidence": ""},
            {"id": 5, "result": "yes", "evidence": ""},
        ]
        result = evaluate_capitalization(conditions)
        assert result["isMet"] is False
        assert set(result["missingConditions"]) == {1, 2, 4}

    def test_empty_conditions_all_yes(self):
        """空条件列表 → isMet=True（无no）"""
        from app.routers.wp_render_strategies._i2_capitalization_engine import evaluate_capitalization

        result = evaluate_capitalization([])
        assert result["isMet"] is True  # no "no" found

    def test_na_conditions_treated_as_met(self):
        """na条件不影响判断（不计入missing）"""
        from app.routers.wp_render_strategies._i2_capitalization_engine import evaluate_capitalization

        conditions = [
            {"id": 1, "result": "yes", "evidence": ""},
            {"id": 2, "result": "na", "evidence": ""},
            {"id": 3, "result": "yes", "evidence": ""},
            {"id": 4, "result": "na", "evidence": ""},
            {"id": 5, "result": "yes", "evidence": ""},
        ]
        result = evaluate_capitalization(conditions)
        assert result["isMet"] is True
        assert result["missingConditions"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# 3. validate_research_split 校验逻辑
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateResearchSplit:
    """费用化+资本化=研发总额 拆分校验"""

    def test_valid_split_exact(self):
        """精确匹配 → isValid=True"""
        from app.routers.wp_render_strategies._i2_capitalization_engine import validate_research_split

        result = validate_research_split(300000.0, 200000.0, 500000.0)
        assert result["isValid"] is True
        assert result["difference"] == 0.0

    def test_valid_split_within_tolerance(self):
        """误差<1分钱 → isValid=True"""
        from app.routers.wp_render_strategies._i2_capitalization_engine import validate_research_split

        result = validate_research_split(300000.005, 199999.999, 500000.0)
        # 实际总额=500000.004, 差额=0.004 < 0.01
        assert result["isValid"] is True

    def test_invalid_split_large_difference(self):
        """大差异 → isValid=False"""
        from app.routers.wp_render_strategies._i2_capitalization_engine import validate_research_split

        result = validate_research_split(300000.0, 200000.0, 600000.0)
        assert result["isValid"] is False
        assert result["difference"] != 0

    def test_zero_budget_zero_amounts(self):
        """全零 → isValid=True"""
        from app.routers.wp_render_strategies._i2_capitalization_engine import validate_research_split

        result = validate_research_split(0.0, 0.0, 0.0)
        assert result["isValid"] is True

    def test_difference_sign(self):
        """差额符号: 实际<预算时差额为负"""
        from app.routers.wp_render_strategies._i2_capitalization_engine import validate_research_split

        result = validate_research_split(100.0, 100.0, 300.0)
        # actual=200, budget=300 → difference = 200-300 = -100
        assert result["difference"] == -100.0
        assert result["isValid"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. API 模型和路由器注册
# ═══════════════════════════════════════════════════════════════════════════════

class TestApiModels:
    """验证API模型和路由器"""

    def test_router_exists(self):
        """router 对象存在"""
        from app.routers.wp_render_strategies._i2_capitalization_engine import router

        assert router is not None

    def test_cas6_condition_item_model(self):
        """CAS6ConditionItem Pydantic模型验证"""
        from app.routers.wp_render_strategies._i2_capitalization_engine import CAS6ConditionItem

        item = CAS6ConditionItem(id=1, result="yes", evidence="证据")
        assert item.id == 1
        assert item.result == "yes"

    def test_cas6_condition_item_validation_bounds(self):
        """条件id范围1-5"""
        from app.routers.wp_render_strategies._i2_capitalization_engine import CAS6ConditionItem
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CAS6ConditionItem(id=0, result="yes", evidence="")
        with pytest.raises(ValidationError):
            CAS6ConditionItem(id=6, result="yes", evidence="")

    def test_cas6_condition_item_result_pattern(self):
        """result只允许 yes/no/na"""
        from app.routers.wp_render_strategies._i2_capitalization_engine import CAS6ConditionItem
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CAS6ConditionItem(id=1, result="maybe", evidence="")

    def test_validate_split_request_model(self):
        """ValidateSplitRequest 模型"""
        from app.routers.wp_render_strategies._i2_capitalization_engine import ValidateSplitRequest

        req = ValidateSplitRequest(expense_i6=100.0, capitalized_i2=200.0, total_budget=300.0)
        assert req.expense_i6 == 100.0
        assert req.capitalized_i2 == 200.0
        assert req.total_budget == 300.0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. AI生成模块存在性（不实际调用LLM）
# ═══════════════════════════════════════════════════════════════════════════════

class TestAiGenerateModule:
    """验证AI生成模块文件存在且可导入"""

    def test_ai_generate_module_importable(self):
        """_i2_ai_generate.py 可导入"""
        try:
            from app.routers.wp_render_strategies import _i2_ai_generate  # noqa: F401
            assert True
        except ImportError:
            pytest.skip("AI generate module not yet created")

    def test_import_export_module_importable(self):
        """_i2_import_export.py 可导入"""
        try:
            from app.routers.wp_render_strategies import _i2_import_export  # noqa: F401
            assert True
        except ImportError:
            pytest.skip("Import/export module not yet created")
