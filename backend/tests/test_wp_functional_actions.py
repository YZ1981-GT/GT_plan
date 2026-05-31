"""底稿功能行为联动测试 — wp-functional-actions spec Task 8

测试覆盖：
  8.1 ACTION_REGISTRY 可扩展性（新增类型只配置不改框架）
  8.2 各动作填充正确性单测
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.wp_action_registry import (
    ACTION_REGISTRY,
    ActionConfig,
    get_actions,
    get_all_functional_types,
    get_action_config,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 8.1 ACTION_REGISTRY 可扩展性测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestActionRegistryExtensibility:
    """**Validates: Requirements 5.1, 5.2** — 动作注册机制可扩展性"""

    def test_registry_has_known_types(self):
        """注册表包含已知的 functional_type"""
        known_types = {"cutoff", "aging", "monthly_analysis", "sampling", "contract_ledger", "confirmation"}
        registered = set(ACTION_REGISTRY.keys())
        assert known_types.issubset(registered), f"缺失类型: {known_types - registered}"

    def test_each_type_has_at_least_one_action(self):
        """每个 functional_type 至少有一个动作"""
        for ft, actions in ACTION_REGISTRY.items():
            assert len(actions) >= 1, f"{ft} 没有注册动作"

    def test_action_config_fields_complete(self):
        """每个 ActionConfig 字段完整"""
        for ft, actions in ACTION_REGISTRY.items():
            for action in actions:
                assert action.label, f"{ft} 动作缺少 label"
                assert action.description, f"{ft} 动作缺少 description"
                assert action.endpoint, f"{ft} 动作缺少 endpoint"
                assert action.method in ("GET", "POST", "PUT", "PATCH"), f"{ft} 动作 method 无效"
                assert isinstance(action.params_schema, dict), f"{ft} 动作 params_schema 不是 dict"
                assert action.fill_strategy in ("replace_rows", "append_rows", "merge_cells")
                assert isinstance(action.requires_llm, bool)
                assert action.icon

    def test_add_new_type_without_framework_change(self):
        """新增 functional_type 只需配置注册表（Property 3）"""
        # 模拟新增一个类型
        new_action = ActionConfig(
            label="测试动作",
            description="测试用动作",
            endpoint="test/endpoint",
            params_schema={"type": "object", "properties": {}},
            fill_strategy="replace_rows",
            icon="🧪",
        )

        # 临时添加到注册表
        original_keys = set(ACTION_REGISTRY.keys())
        ACTION_REGISTRY["test_new_type"] = [new_action]

        try:
            # 验证框架函数无需修改即可工作
            actions = get_actions("test_new_type")
            assert len(actions) == 1
            assert actions[0].label == "测试动作"

            all_types = get_all_functional_types()
            assert "test_new_type" in all_types

            found = get_action_config("test_new_type", "测试动作")
            assert found is not None
            assert found.endpoint == "test/endpoint"
        finally:
            # 清理
            del ACTION_REGISTRY["test_new_type"]

    def test_get_actions_returns_empty_for_unknown_type(self):
        """未注册的 functional_type 返回空列表"""
        actions = get_actions("nonexistent_type")
        assert actions == []

    def test_get_action_config_returns_none_for_unknown(self):
        """未找到的动作返回 None"""
        result = get_action_config("cutoff", "不存在的动作")
        assert result is None

    def test_params_schema_has_required_fields(self):
        """L1 动作的 params_schema 包含 required 字段"""
        for ft in ["cutoff", "aging", "monthly_analysis", "sampling"]:
            actions = get_actions(ft)
            for action in actions:
                if not action.requires_llm:
                    schema = action.params_schema
                    assert "properties" in schema, f"{ft}/{action.label} 缺少 properties"
                    assert "required" in schema, f"{ft}/{action.label} 缺少 required"

    def test_llm_actions_marked_correctly(self):
        """L2 动作正确标记 requires_llm"""
        contract_actions = get_actions("contract_ledger")
        assert any(a.requires_llm for a in contract_actions)

        # L1 动作不依赖 LLM
        cutoff_actions = get_actions("cutoff")
        assert all(not a.requires_llm for a in cutoff_actions)


# ═══════════════════════════════════════════════════════════════════════════════
# 8.2 各动作填充正确性单测
# ═══════════════════════════════════════════════════════════════════════════════

class TestActionFillCorrectness:
    """**Validates: Requirements 3.1, 3.2, 3.3, 3.4** — 动作填充正确性"""

    @pytest.mark.asyncio
    async def test_cutoff_test_returns_entries(self):
        """截止测试返回 entries 列表"""
        from app.services.sampling_enhanced_service import CutoffTestService

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        svc = CutoffTestService()
        result = await svc.run_cutoff_test(db, uuid4(), 2025, ["6001"])

        assert "entries" in result
        assert "total_entries" in result
        assert "period_end" in result
        assert "window" in result
        assert result["total_entries"] == 0

    @pytest.mark.asyncio
    async def test_monthly_detail_returns_months(self):
        """月度分析返回 months 列表"""
        from app.services.sampling_enhanced_service import MonthlyDetailService

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        svc = MonthlyDetailService()
        result = await svc.generate_monthly_detail(db, uuid4(), "6001", 2025)

        assert "months" in result
        assert "account_code" in result
        assert "year" in result
        assert result["account_code"] == "6001"
        assert result["year"] == 2025

    @pytest.mark.asyncio
    async def test_aging_analysis_returns_details(self):
        """账龄分析返回 details + summary"""
        from app.services.sampling_enhanced_service import AgingAnalysisService

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        svc = AgingAnalysisService()
        brackets = [
            {"label": "1年以内", "min_days": 0, "max_days": 365},
            {"label": "1-2年", "min_days": 366, "max_days": 730},
        ]
        result = await svc.analyze_aging(db, uuid4(), "1122", brackets, "2025-12-31", 2025)

        assert "details" in result
        assert "summary" in result
        assert result["account_code"] == "1122"

    @pytest.mark.asyncio
    async def test_sampling_engine_random(self):
        """随机抽样返回正确数量"""
        from app.services.wp_sampling_engine import WpSamplingEngine

        engine = WpSamplingEngine()

        # 模拟候选数据
        candidates = [
            {"voucher_no": f"V{i:04d}", "amount": i * 100, "voucher_date": "2025-01-01",
             "account_code": "6001", "account_name": "收入", "debit_amount": i * 100,
             "credit_amount": 0, "summary": f"摘要{i}"}
            for i in range(100)
        ]

        with patch.object(engine, '_fetch_candidates', return_value=candidates):
            db = AsyncMock()
            result = await engine.execute_sampling(
                db, uuid4(), 2025, ["6001"], method="random", sample_size=10
            )

        assert result["method"] == "random"
        assert result["total_population"] == 100
        assert result["sample_size"] == 10
        assert len(result["entries"]) == 10

    @pytest.mark.asyncio
    async def test_sampling_engine_top_n(self):
        """大额抽样返回超阈值条目"""
        from app.services.wp_sampling_engine import WpSamplingEngine

        engine = WpSamplingEngine()

        candidates = [
            {"voucher_no": f"V{i:04d}", "amount": i * 1000, "voucher_date": "2025-01-01",
             "account_code": "6001", "account_name": "收入", "debit_amount": i * 1000,
             "credit_amount": 0, "summary": f"摘要{i}"}
            for i in range(50)
        ]

        with patch.object(engine, '_fetch_candidates', return_value=candidates):
            db = AsyncMock()
            result = await engine.execute_sampling(
                db, uuid4(), 2025, ["6001"], method="top_n", amount_threshold=30000
            )

        assert result["method"] == "top_n"
        # 金额 >= 30000 的条目：i*1000 >= 30000 → i >= 30，共 20 条
        assert result["sample_size"] == 20

    @pytest.mark.asyncio
    async def test_sampling_engine_stratified(self):
        """分层抽样按比例分配"""
        from app.services.wp_sampling_engine import WpSamplingEngine

        engine = WpSamplingEngine()

        candidates = [
            {"voucher_no": f"V{i:04d}", "amount": i * 100, "voucher_date": "2025-01-01",
             "account_code": "6001", "account_name": "收入", "debit_amount": i * 100,
             "credit_amount": 0, "summary": f"摘要{i}"}
            for i in range(1, 101)  # 100-10000
        ]

        with patch.object(engine, '_fetch_candidates', return_value=candidates):
            db = AsyncMock()
            result = await engine.execute_sampling(
                db, uuid4(), 2025, ["6001"], method="stratified", sample_size=15
            )

        assert result["method"] == "stratified"
        assert result["sample_size"] <= 15
        assert len(result["entries"]) <= 15

    @pytest.mark.asyncio
    async def test_sampling_engine_empty_population(self):
        """空总体返回空结果"""
        from app.services.wp_sampling_engine import WpSamplingEngine

        engine = WpSamplingEngine()

        with patch.object(engine, '_fetch_candidates', return_value=[]):
            db = AsyncMock()
            result = await engine.execute_sampling(
                db, uuid4(), 2025, ["6001"], method="random", sample_size=10
            )

        assert result["total_population"] == 0
        assert result["sample_size"] == 0
        assert result["entries"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# 推断工具测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestInferFunctionalType:
    """functional_type 推断工具正确性"""

    def test_wp_code_cutoff(self):
        """wp_code D2-8 → cutoff"""
        from scripts.seed.infer_functional_type import infer_functional_type
        assert infer_functional_type("D2-8", "截止测试", None) == "cutoff"

    def test_wp_code_aging(self):
        """wp_code D2-13 → aging"""
        from scripts.seed.infer_functional_type import infer_functional_type
        assert infer_functional_type("D2-13", "账龄分析", None) == "aging"

    def test_wp_code_sampling(self):
        """wp_code D2-9 → sampling"""
        from scripts.seed.infer_functional_type import infer_functional_type
        assert infer_functional_type("D2-9", "抽凭", None) == "sampling"

    def test_sheet_name_monthly(self):
        """sheet_name 含"月度" → monthly_analysis"""
        from scripts.seed.infer_functional_type import infer_functional_type
        assert infer_functional_type("X1", "月度分析表", None) == "monthly_analysis"

    def test_sheet_name_reconciliation(self):
        """sheet_name 含"调节表" → reconciliation"""
        from scripts.seed.infer_functional_type import infer_functional_type
        assert infer_functional_type("X1", "银行余额调节表", None) == "reconciliation"

    def test_class_code_fallback(self):
        """class_code 兜底映射"""
        from scripts.seed.infer_functional_type import infer_functional_type
        assert infer_functional_type("X1", "普通表", "e-control-test") == "control_test"

    def test_no_match_returns_none(self):
        """无匹配返回 None"""
        from scripts.seed.infer_functional_type import infer_functional_type
        assert infer_functional_type("Z99", "未知表", None) is None


# ═══════════════════════════════════════════════════════════════════════════════
# 证据链交叉核对测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvidenceCrossCheck:
    """证据链交叉核对正确性"""

    @pytest.mark.asyncio
    async def test_matching_evidence(self):
        """凭证号和金额匹配 → matched=True"""
        from app.services.wp_evidence_ocr_service import WpEvidenceOcrService

        svc = WpEvidenceOcrService()
        entry = {"voucher_no": "V0001", "debit_amount": 10000, "credit_amount": 0}
        evidence = [{"voucher_no": "V0001", "amount": 10000}]

        result = await svc.cross_check_evidence(entry, evidence)
        assert result["matched"] is True
        assert result["issues"] == []

    @pytest.mark.asyncio
    async def test_voucher_no_mismatch(self):
        """凭证号不匹配 → warning"""
        from app.services.wp_evidence_ocr_service import WpEvidenceOcrService

        svc = WpEvidenceOcrService()
        entry = {"voucher_no": "V0001", "debit_amount": 10000, "credit_amount": 0}
        evidence = [{"voucher_no": "V0002", "amount": 10000}]

        result = await svc.cross_check_evidence(entry, evidence)
        assert result["matched"] is False
        assert any(i["type"] == "voucher_no_mismatch" for i in result["issues"])

    @pytest.mark.asyncio
    async def test_amount_mismatch(self):
        """金额差异超 1% → warning/error"""
        from app.services.wp_evidence_ocr_service import WpEvidenceOcrService

        svc = WpEvidenceOcrService()
        entry = {"voucher_no": "V0001", "debit_amount": 10000, "credit_amount": 0}
        evidence = [{"voucher_no": "V0001", "amount": 9000}]  # 10% 差异

        result = await svc.cross_check_evidence(entry, evidence)
        assert result["matched"] is False
        assert any(i["type"] == "amount_mismatch" for i in result["issues"])
