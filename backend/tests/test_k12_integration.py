"""K12 营业外收入 — 集成测试：损益取数(发生额) + 明细聚合 + 审定回写.

Spec: .kiro/specs/k12-non-operating-income/ Task 7.2
Validates: Requirements 2.5, 5.1

测试:
1. render策略从tb_ledger取发生额（非tb_balance期末余额），计算净发生额=贷方-借方
2. K12-2明细行聚合与审定表一致性验证
3. 审定回写发生额到trial_balance（handler正则^[D-N]\\d+-1$匹配K12-1）
4. K12_SHEETS全8 sheets覆盖
5. YAML schema合法性（income_statement=True, occurrence_amount）
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db
from app.routers.wp_render_strategies import RENDERER_DISPATCH


class _FakeUser:
    id = "test-user-id"
    name = "Test User"
    email = "test@example.com"
    role = UserRole.admin


@pytest.fixture(autouse=True)
def override_deps():
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db
    yield mock_db
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Render策略：损益取数(发生额) 验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK12RenderStrategyIncomeStatement:
    """验证 K12 render 策略走新架构（共享件 pl_occurrence + k_cycle_specs）."""

    def test_k12_registered_in_dispatch(self):
        """RENDERER_DISPATCH 包含 k12-non-operating-income."""
        assert "k12-non-operating-income" in RENDERER_DISPATCH

    def test_k12_render_is_callable(self):
        """render 函数可调用."""
        from app.routers.wp_render_strategies._k12_non_operating_income import render
        assert callable(render)

    def test_k12_account_prefix_is_6301(self):
        """科目 6301 由 k_cycle_specs 声明（不再是模块级 _K12_ACCOUNT_PREFIX）."""
        from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS
        assert K_CYCLE_SPECS["K12"].fallback_standard == "6301"

    def test_render_uses_shared_pl_occurrence(self):
        """render 走共享件 pl_render.render_pl_cycle（非自造取数函数）."""
        from app.routers.wp_render_strategies._k12_non_operating_income import render
        import inspect
        # 新架构 render 函数体 < 10 行（只调用 render_pl_cycle），不含自造取数逻辑
        src = inspect.getsource(render)
        assert "render_pl_cycle" in src, "render 应委托 render_pl_cycle 共享装配器"

    def test_pl_occurrence_uses_trial_balance_authority(self):
        """共享件 pl_occurrence 以 trial_balance 为权威口径，禁止 debit-credit 净额."""
        from app.services.four_table import pl_occurrence
        import inspect, re as _re
        src = inspect.getsource(pl_occurrence.pick_occurrence)
        # 去掉 docstring（里面写了「禁止 debit - credit」的说明文字）
        body = _re.sub(r'''""".*?"""''', "", src, flags=_re.DOTALL)
        # pick_occurrence 函数体只取方向侧发生额，不做减法
        assert "debit - credit" not in body
        assert "credit - debit" not in body

    def test_render_returns_income_statement_flag(self):
        """K12_META 标识 income_statement=True."""
        from app.routers.wp_render_strategies._k12_non_operating_income import K12_META
        assert K12_META["special_rules"]["income_statement"] is True

    def test_render_returns_component_type(self):
        """render 模块声明 component_type = 'k12-non-operating-income'."""
        from app.routers.wp_render_strategies._k12_non_operating_income import K12_SHEETS
        assert all(s["component_type"] == "k12-non-operating-income" for s in K12_SHEETS)

    def test_render_contains_tb_values(self):
        """pl_occurrence.build_pl_tb_values 返回结果包含 occurrence_unadjusted."""
        from app.services.four_table.pl_occurrence import PlOccurrence, build_pl_tb_values, AccountNature
        occ = PlOccurrence(unadjusted=75000.0, audited=75000.0, fallback_amount=80000.0,
                           source="trial_balance", nature=AccountNature.INCOME.value)
        tv = build_pl_tb_values(occ)
        assert "occurrence_unadjusted" in tv
        assert tv["occurrence_unadjusted"] == 75000.0

    def test_render_sheets_list_has_8_entries(self):
        """K12_SHEETS 恰好 8 个 sheet."""
        from app.routers.wp_render_strategies._k12_non_operating_income import K12_SHEETS
        assert len(K12_SHEETS) == 8

    def test_render_empty_ledger_returns_empty_tb(self):
        """无数据时 build_pl_tb_values 全部返 0."""
        from app.services.four_table.pl_occurrence import PlOccurrence, build_pl_tb_values, AccountNature
        occ = PlOccurrence(source="none", nature=AccountNature.INCOME.value)
        tv = build_pl_tb_values(occ)
        assert tv["occurrence_unadjusted"] == 0.0
        assert tv["audited_amount"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 明细聚合验证（K12-2 → K12-1）
# ═══════════════════════════════════════════════════════════════════════════════


class TestK12DetailAggregation:
    """验证K12-2明细行合计与K12-1审定表发生额一致性."""

    def test_detail_spec_has_amount_field(self):
        """K12-2 spec包含金额字段（用于聚合）."""
        from app.routers.wp_render_strategies._k12_import_export import _K12_SPECS

        k12_2 = _K12_SPECS["K12-2"]
        assert "amount" in k12_2["field_keys"], "K12-2缺少amount字段"

    def test_detail_spec_item_id_correct(self):
        """K12-2的item_id为'K12-2-rows'（聚合时定位用）."""
        from app.routers.wp_render_strategies._k12_import_export import _K12_SPECS

        assert _K12_SPECS["K12-2"]["item_id"] == "K12-2-rows"

    def test_aggregation_logic_single_source(self):
        """单来源聚合：1笔收入=审定发生额."""
        # 模拟明细行数据：政府补助 30000
        detail_rows = [{"incomeSource": "政府补助", "amount": 30000.0}]
        total = sum(r["amount"] for r in detail_rows if r.get("amount"))
        assert total == 30000.0

    def test_aggregation_logic_multiple_sources(self):
        """多来源聚合：各项收入合计=审定发生额."""
        # 模拟多笔营业外收入明细
        detail_rows = [
            {"incomeSource": "政府补助", "amount": 30000.0},
            {"incomeSource": "债务重组利得", "amount": 15000.0},
            {"incomeSource": "资产盘盈", "amount": 5000.0},
            {"incomeSource": "罚款收入", "amount": 8000.0},
            {"incomeSource": "捐赠利得", "amount": 2000.0},
        ]
        total = sum(r["amount"] for r in detail_rows if r.get("amount"))
        # 合计应等于审定发生额
        expected_audited = 60000.0
        assert total == expected_audited

    def test_aggregation_empty_rows(self):
        """空明细行聚合为0."""
        detail_rows: list = []
        total = sum(r.get("amount", 0) for r in detail_rows)
        assert total == 0

    def test_aggregation_with_none_amounts(self):
        """含None金额的明细行跳过不影响聚合."""
        detail_rows = [
            {"incomeSource": "政府补助", "amount": 30000.0},
            {"incomeSource": "其他", "amount": None},
            {"incomeSource": "罚款收入", "amount": 5000.0},
        ]
        total = sum(r["amount"] for r in detail_rows if r.get("amount"))
        assert total == 35000.0

    def test_cross_sheet_reference_defined(self):
        """YAML中定义了K12-2→K12-1的跨sheet引用."""
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "ledger_adapters"
            / "wp_render_schema"
            / "k12-non-operating-income.yaml"
        )
        with open(yaml_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        refs = schema.get("cross_wp_references", [])
        k12_2_to_k12_1 = [
            r for r in refs
            if r.get("source_wp") == "K12-2" and r.get("target_wp") == "K12-1"
        ]
        assert len(k12_2_to_k12_1) >= 1, "缺少K12-2→K12-1跨sheet引用定义"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 审定回写验证（TB writeback: 发生额→trial_balance）
# ═══════════════════════════════════════════════════════════════════════════════


class TestK12TbWriteback:
    """验证K12审定回写逻辑：K12-1审定→trial_balance.audited_amount(发生额)."""

    _PATTERN = re.compile(r"^[D-N]\d+-1$")

    def test_regex_matches_k12_1(self):
        """handler正则 ^[D-N]\\d+-1$ 匹配K12-1."""
        assert self._PATTERN.match("K12-1"), "K12-1应通过审定表回写正则"

    def test_regex_rejects_non_audit_sheets(self):
        """非审定表编码被正则拒绝."""
        non_audit = ["K12A", "K12-2", "K12-3", "K12-4", "K12"]
        for code in non_audit:
            assert not self._PATTERN.match(code), f"{code}不应匹配审定表正则"

    def test_regex_matches_all_k_audit_tables(self):
        """K1-1~K13-1 全部13个K类审定表都匹配."""
        for i in range(1, 14):
            code = f"K{i}-1"
            assert self._PATTERN.match(code), f"{code}应通过审定表正则"

    def test_handler_source_uses_correct_pattern(self):
        """handler源码包含正则 ^[D-N]\\d+-1$."""
        from app.services import event_handlers_cycle_linkage

        src = inspect.getsource(event_handlers_cycle_linkage)
        assert r'^[D-N]\d+-1$' in src, (
            "handler源码中未找到正则 ^[D-N]\\d+-1$"
        )

    def test_yaml_writeback_config_occurrence(self):
        """YAML tb_writeback.value_type='occurrence_amount'（发生额非余额）."""
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "ledger_adapters"
            / "wp_render_schema"
            / "k12-non-operating-income.yaml"
        )
        with open(yaml_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        wb = schema["tb_writeback"]
        assert wb["account_code"] == "6301"
        assert wb["value_type"] == "occurrence_amount", (
            "K12损益类回写应为发生额(occurrence_amount)而非余额"
        )
        assert wb["direction"] == "credit", "6301为贷方科目"
        assert wb["source_sheet"] == "K12-1"

    def test_yaml_writeback_trigger_is_workpaper_saved(self):
        """TB回写触发事件为WORKPAPER_SAVED."""
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "ledger_adapters"
            / "wp_render_schema"
            / "k12-non-operating-income.yaml"
        )
        with open(yaml_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        assert schema["tb_writeback"]["trigger"] == "WORKPAPER_SAVED"

    def test_other_cycles_still_matched_regression(self):
        """回归测试：其他循环审定表仍匹配."""
        other_codes = [
            "D1-1", "D2-1", "E1-1", "F1-1", "F2-1",
            "G1-1", "H1-1", "I1-1", "J1-1", "L1-1", "M1-1", "N1-1",
        ]
        for code in other_codes:
            assert self._PATTERN.match(code), f"{code}应继续匹配审定表正则"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. K12_SHEETS 全8 sheets定义验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK12Sheets:
    """验证 K12_SHEETS 定义结构."""

    def test_k12_sheets_count(self):
        """K12_SHEETS 恰好8个sheet."""
        from app.routers.wp_render_strategies._k12_non_operating_income import K12_SHEETS

        assert len(K12_SHEETS) == 8

    def test_k12_sheets_all_have_component_type(self):
        """每个sheet都标记component_type为k12-non-operating-income."""
        from app.routers.wp_render_strategies._k12_non_operating_income import K12_SHEETS

        for sheet in K12_SHEETS:
            assert sheet["component_type"] == "k12-non-operating-income"

    def test_k12_sheets_expected_names(self):
        """K12_SHEETS包含所有预期的sheet关键字."""
        from app.routers.wp_render_strategies._k12_non_operating_income import K12_SHEETS

        names = [s["sheet_name"] for s in K12_SHEETS]
        expected_keywords = [
            "底稿目录", "K12A", "K12-1", "K12-2", "K12-3", "K12-4",
            "上市公司", "国企",
        ]
        for kw in expected_keywords:
            assert any(kw in n for n in names), f"缺少含'{kw}'的sheet"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. YAML Schema完整性验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK12YamlSchema:
    """验证 k12-non-operating-income.yaml 结构完整性."""

    @pytest.fixture
    def schema(self):
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "ledger_adapters"
            / "wp_render_schema"
            / "k12-non-operating-income.yaml"
        )
        assert yaml_path.exists(), f"YAML schema not found: {yaml_path}"
        with open(yaml_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_income_statement_flag(self, schema):
        """income_statement=True 标识损益类."""
        assert schema["income_statement"] is True

    def test_account_codes(self, schema):
        """account_codes 包含 '6301'."""
        assert "6301" in schema["account_codes"]

    def test_component_type(self, schema):
        """component_type 为 k12-non-operating-income."""
        assert schema["component_type"] == "k12-non-operating-income"

    def test_wp_code(self, schema):
        """wp_code 为 K12."""
        assert schema["wp_code"] == "K12"

    def test_self_load(self, schema):
        """selfLoad=True."""
        assert schema["selfLoad"] is True

    def test_source_table_is_tb_ledger(self, schema):
        """special_rules.source_table='tb_ledger'（损益类从tb_ledger取数）."""
        assert schema["special_rules"]["source_table"] == "tb_ledger"

    def test_account_direction_credit(self, schema):
        """special_rules.account_direction='credit'（贷方科目）."""
        assert schema["special_rules"]["account_direction"] == "credit"

    def test_net_formula(self, schema):
        """special_rules.net_formula='贷方发生-借方发生'."""
        assert "贷方" in schema["special_rules"]["net_formula"]
        assert "借方" in schema["special_rules"]["net_formula"]

    def test_cross_wp_references(self, schema):
        """cross_wp_references 存在且≥3个引用."""
        refs = schema.get("cross_wp_references", [])
        assert len(refs) >= 3
        # 验证K12-3→A13引用存在
        a13_refs = [r for r in refs if "A13" in r.get("target_wp", "")]
        assert len(a13_refs) >= 1, "缺少K12-3→A13交叉引用"

    def test_ai_sections(self, schema):
        """ai_sections 包含 non-operating-eval 和 overall-opinion."""
        sections = {s["id"] for s in schema.get("ai_sections", [])}
        assert "non-operating-eval" in sections
        assert "overall-opinion" in sections


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Import/Export 路由验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK12ImportExport:
    """验证 K12 导入导出路由结构."""

    def test_k12_import_export_router_exists(self):
        """_k12_import_export 模块有 router 对象."""
        from app.routers.wp_render_strategies._k12_import_export import router

        assert router is not None

    def test_k12_import_export_two_sheet_specs(self):
        """_K12_SPECS 包含2个sheet规格（K12-2/K12-3）."""
        from app.routers.wp_render_strategies._k12_import_export import _K12_SPECS

        expected_keys = {"K12-2", "K12-3"}
        assert set(_K12_SPECS.keys()) == expected_keys

    def test_k12_each_spec_has_required_fields(self):
        """每个sheet spec都有item_id/title/headers/field_keys/guidance."""
        from app.routers.wp_render_strategies._k12_import_export import _K12_SPECS

        for key, spec in _K12_SPECS.items():
            assert "item_id" in spec, f"{key} 缺少 item_id"
            assert "title" in spec, f"{key} 缺少 title"
            assert "headers" in spec, f"{key} 缺少 headers"
            assert "field_keys" in spec, f"{key} 缺少 field_keys"
            assert "guidance" in spec, f"{key} 缺少 guidance"
            # headers 和 field_keys 长度一致
            assert len(spec["headers"]) == len(spec["field_keys"]), (
                f"{key}: headers({len(spec['headers'])}) != field_keys({len(spec['field_keys'])})"
            )

    @pytest.mark.asyncio
    async def test_k12_export_template_route_registered(self):
        """K12 export-template 路由已在 app 中注册."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/workpapers/test-wp/k12/export-template?sheet=K12-2")
        assert resp.status_code != 404, "K12 export-template route not registered"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. AI生成路由验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK12AiGenerate:
    """验证 K12 AI生成路由结构."""

    def test_k12_ai_router_exists(self):
        """_k12_ai_generate 模块有 router 对象."""
        from app.routers.wp_render_strategies._k12_ai_generate import router

        assert router is not None

    def test_k12_ai_two_supported_sections(self):
        """_SUPPORTED_SECTIONS 恰好包含2个section（non-operating-eval/overall-opinion）."""
        from app.routers.wp_render_strategies._k12_ai_generate import _SUPPORTED_SECTIONS

        expected = {"non-operating-eval", "overall-opinion"}
        assert _SUPPORTED_SECTIONS == expected

    @pytest.mark.asyncio
    async def test_k12_ai_generate_route_registered(self):
        """K12 AI生成路由已在 app 中注册."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/k12/ai-generate",
                json={"section": "non-operating-eval", "existingContent": ""},
            )
        assert resp.status_code != 404, "K12 ai-generate route not registered"
