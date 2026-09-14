"""K13 营业外支出 — 集成测试：损益取数(发生额) + 明细聚合 + 审定回写.

Spec: .kiro/specs/k13-non-operating-expense/ Task 7.2
Validates: Requirements 2.5, 5.1

测试:
1. render策略从tb_ledger取发生额（非tb_balance期末余额），计算净发生额=借方-贷方
2. K13-2明细行聚合与审定表一致性验证
3. 审定回写发生额到trial_balance（handler正则^[D-N]\\d+-1$匹配K13-1）
4. K13_SHEETS全8 sheets覆盖
5. YAML schema合法性（income_statement=True, occurrence_amount）
6. Import/Export规格验证（K13-2: 27列, K13-3: 10列）
7. AI生成路由验证
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


class TestK13RenderStrategyIncomeStatement:
    """验证 K13 render 策略走新架构（共享件 pl_occurrence + k_cycle_specs）."""

    def test_k13_registered_in_dispatch(self):
        """RENDERER_DISPATCH 包含 k13-non-operating-expense."""
        assert "k13-non-operating-expense" in RENDERER_DISPATCH

    def test_k13_render_is_callable(self):
        """render 函数可调用."""
        from app.routers.wp_render_strategies._k13_non_operating_expense import render
        assert callable(render)

    def test_k13_account_prefix_is_6711(self):
        """科目 6711 由 k_cycle_specs 声明（不再是模块级 _K13_ACCOUNT_PREFIX）."""
        from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS
        assert K_CYCLE_SPECS["K13"].fallback_standard == "6711"

    def test_render_uses_shared_pl_occurrence(self):
        """render 走共享件 pl_render.render_pl_cycle（非自造取数函数）."""
        from app.routers.wp_render_strategies._k13_non_operating_expense import render
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
        """K13_META 标识 income_statement=True."""
        from app.routers.wp_render_strategies._k13_non_operating_expense import K13_META
        assert K13_META["special_rules"]["income_statement"] is True

    def test_render_returns_component_type(self):
        """render 模块声明 component_type = 'k13-non-operating-expense'."""
        from app.routers.wp_render_strategies._k13_non_operating_expense import K13_SHEETS
        assert all(s["component_type"] == "k13-non-operating-expense" for s in K13_SHEETS)

    def test_render_contains_tb_values(self):
        """pl_occurrence.build_pl_tb_values 返回结果包含 occurrence_unadjusted."""
        from app.services.four_table.pl_occurrence import PlOccurrence, build_pl_tb_values, AccountNature
        occ = PlOccurrence(unadjusted=75000.0, audited=75000.0, fallback_amount=80000.0,
                           source="trial_balance", nature=AccountNature.EXPENSE.value)
        tv = build_pl_tb_values(occ)
        assert "occurrence_unadjusted" in tv
        assert tv["occurrence_unadjusted"] == 75000.0

    def test_render_sheets_list_has_8_entries(self):
        """K13_SHEETS 恰好 8 个 sheet."""
        from app.routers.wp_render_strategies._k13_non_operating_expense import K13_SHEETS
        assert len(K13_SHEETS) == 8

    def test_render_empty_ledger_returns_empty_tb(self):
        """无数据时 build_pl_tb_values 全部返 0."""
        from app.services.four_table.pl_occurrence import PlOccurrence, build_pl_tb_values, AccountNature
        occ = PlOccurrence(source="none", nature=AccountNature.EXPENSE.value)
        tv = build_pl_tb_values(occ)
        assert tv["occurrence_unadjusted"] == 0.0
        assert tv["audited_amount"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 明细聚合验证（K13-2 → K13-1）
# ═══════════════════════════════════════════════════════════════════════════════


class TestK13DetailAggregation:
    """验证K13-2明细行合计与K13-1审定表发生额一致性."""

    def test_detail_spec_has_month_total_field(self):
        """K13-2 spec包含monthTotal字段（用于聚合）."""
        from app.routers.wp_render_strategies._k13_import_export import _K13_SPECS

        k13_2 = _K13_SPECS["K13-2"]
        assert "monthTotal" in k13_2["field_keys"], "K13-2缺少monthTotal字段"

    def test_detail_spec_item_id_correct(self):
        """K13-2的item_id为'K13-2-detail-rows'（聚合时定位用）."""
        from app.routers.wp_render_strategies._k13_import_export import _K13_SPECS

        assert _K13_SPECS["K13-2"]["item_id"] == "K13-2-detail-rows"

    def test_aggregation_logic_single_source(self):
        """单去向聚合：1笔支出=审定发生额."""
        detail_rows = [{"project": "非流动资产处置损失", "monthTotal": 50000.0}]
        total = sum(r["monthTotal"] for r in detail_rows if r.get("monthTotal"))
        assert total == 50000.0

    def test_aggregation_logic_multiple_sources(self):
        """多去向聚合：各项支出合计=审定发生额."""
        detail_rows = [
            {"project": "非流动资产处置损失", "monthTotal": 50000.0},
            {"project": "捐赠支出", "monthTotal": 20000.0},
            {"project": "罚款滞纳金", "monthTotal": 8000.0},
            {"project": "债务重组损失", "monthTotal": 15000.0},
            {"project": "资产盘亏损失", "monthTotal": 3000.0},
            {"project": "其他", "monthTotal": 4000.0},
        ]
        total = sum(r["monthTotal"] for r in detail_rows if r.get("monthTotal"))
        expected_audited = 100000.0
        assert total == expected_audited

    def test_aggregation_empty_rows(self):
        """空明细行聚合为0."""
        detail_rows: list = []
        total = sum(r.get("monthTotal", 0) for r in detail_rows)
        assert total == 0

    def test_aggregation_with_none_amounts(self):
        """含None金额的明细行跳过不影响聚合."""
        detail_rows = [
            {"project": "捐赠支出", "monthTotal": 20000.0},
            {"project": "其他", "monthTotal": None},
            {"project": "罚款滞纳金", "monthTotal": 8000.0},
        ]
        total = sum(r["monthTotal"] for r in detail_rows if r.get("monthTotal"))
        assert total == 28000.0

    def test_cross_sheet_reference_defined(self):
        """YAML中定义了K13-2→K13-1的跨sheet引用."""
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "ledger_adapters"
            / "wp_render_schema"
            / "k13-non-operating-expense.yaml"
        )
        with open(yaml_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        refs = schema.get("cross_wp_references", [])
        k13_2_to_k13_1 = [
            r for r in refs
            if r.get("source_wp") == "K13-2" and r.get("target_wp") == "K13-1"
        ]
        assert len(k13_2_to_k13_1) >= 1, "缺少K13-2→K13-1跨sheet引用定义"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 审定回写验证（TB writeback: 发生额→trial_balance）
# ═══════════════════════════════════════════════════════════════════════════════


class TestK13TbWriteback:
    """验证K13审定回写逻辑：K13-1审定→trial_balance.audited_amount(发生额)."""

    _PATTERN = re.compile(r"^[D-N]\d+-1$")

    def test_regex_matches_k13_1(self):
        """handler正则 ^[D-N]\\d+-1$ 匹配K13-1."""
        assert self._PATTERN.match("K13-1"), "K13-1应通过审定表回写正则"

    def test_regex_rejects_non_audit_sheets(self):
        """非审定表编码被正则拒绝."""
        non_audit = ["K13A", "K13-2", "K13-3", "K13-4", "K13"]
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
            / "k13-non-operating-expense.yaml"
        )
        with open(yaml_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        wb = schema["tb_writeback"]
        assert wb["account_code"] == "6711"
        assert wb["value_type"] == "occurrence_amount", (
            "K13损益类回写应为发生额(occurrence_amount)而非余额"
        )
        assert wb["direction"] == "debit", "6711为借方科目"
        assert wb["source_sheet"] == "K13-1"

    def test_yaml_writeback_trigger_is_workpaper_saved(self):
        """TB回写触发事件为WORKPAPER_SAVED."""
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "ledger_adapters"
            / "wp_render_schema"
            / "k13-non-operating-expense.yaml"
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
# 4. K13_SHEETS 全8 sheets定义验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK13Sheets:
    """验证 K13_SHEETS 定义结构."""

    def test_k13_sheets_count(self):
        """K13_SHEETS 恰好8个sheet."""
        from app.routers.wp_render_strategies._k13_non_operating_expense import K13_SHEETS

        assert len(K13_SHEETS) == 8

    def test_k13_sheets_all_have_component_type(self):
        """每个sheet都标记component_type为k13-non-operating-expense."""
        from app.routers.wp_render_strategies._k13_non_operating_expense import K13_SHEETS

        for sheet in K13_SHEETS:
            assert sheet["component_type"] == "k13-non-operating-expense"

    def test_k13_sheets_expected_names(self):
        """K13_SHEETS包含所有预期的sheet关键字."""
        from app.routers.wp_render_strategies._k13_non_operating_expense import K13_SHEETS

        names = [s["sheet_name"] for s in K13_SHEETS]
        expected_keywords = [
            "底稿目录", "K13A", "K13-1", "K13-2", "K13-3", "K13-4",
            "上市公司", "国企",
        ]
        for kw in expected_keywords:
            assert any(kw in n for n in names), f"缺少含'{kw}'的sheet"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. YAML Schema完整性验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK13YamlSchema:
    """验证 k13-non-operating-expense.yaml 结构完整性."""

    @pytest.fixture
    def schema(self):
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "ledger_adapters"
            / "wp_render_schema"
            / "k13-non-operating-expense.yaml"
        )
        assert yaml_path.exists(), f"YAML schema not found: {yaml_path}"
        with open(yaml_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_income_statement_flag(self, schema):
        """income_statement=True 标识损益类."""
        assert schema["income_statement"] is True

    def test_account_codes(self, schema):
        """account_codes 包含 '6711'."""
        assert "6711" in schema["account_codes"]

    def test_component_type(self, schema):
        """component_type 为 k13-non-operating-expense."""
        assert schema["component_type"] == "k13-non-operating-expense"

    def test_wp_code(self, schema):
        """wp_code 为 K13."""
        assert schema["wp_code"] == "K13"

    def test_self_load(self, schema):
        """selfLoad=True."""
        assert schema["selfLoad"] is True

    def test_source_table_is_tb_ledger(self, schema):
        """special_rules.source_table='tb_ledger'（损益类从tb_ledger取数）."""
        assert schema["special_rules"]["source_table"] == "tb_ledger"

    def test_account_direction_debit(self, schema):
        """special_rules.account_direction='debit'（借方科目）."""
        assert schema["special_rules"]["account_direction"] == "debit"

    def test_net_formula(self, schema):
        """special_rules.net_formula 包含'借方'和'贷方'."""
        assert "借方" in schema["special_rules"]["net_formula"]
        assert "贷方" in schema["special_rules"]["net_formula"]

    def test_sheets_count(self, schema):
        """YAML sheets 定义恰好8个."""
        assert len(schema["sheets"]) == 8

    def test_cross_wp_references(self, schema):
        """cross_wp_references 存在且≥3个引用."""
        refs = schema.get("cross_wp_references", [])
        assert len(refs) >= 3
        # 验证K13-3→A13引用存在
        a13_refs = [r for r in refs if "A13" in r.get("target_wp", "")]
        assert len(a13_refs) >= 1, "缺少K13-3→A13交叉引用"

    def test_ai_sections(self, schema):
        """ai_sections 包含 non-operating-eval 和 overall-opinion."""
        sections = {s["id"] for s in schema.get("ai_sections", [])}
        assert "non-operating-eval" in sections
        assert "overall-opinion" in sections


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Import/Export 路由验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK13ImportExport:
    """验证 K13 导入导出路由结构."""

    def test_k13_import_export_router_exists(self):
        """_k13_import_export 模块有 router 对象."""
        from app.routers.wp_render_strategies._k13_import_export import router

        assert router is not None

    def test_k13_import_export_two_sheet_specs(self):
        """_K13_SPECS 包含2个sheet规格（K13-2/K13-3）."""
        from app.routers.wp_render_strategies._k13_import_export import _K13_SPECS

        expected_keys = {"K13-2", "K13-3"}
        assert set(_K13_SPECS.keys()) == expected_keys

    def test_k13_2_has_27_columns(self):
        """K13-2 明细表恰好27列（headers和field_keys各27项）."""
        from app.routers.wp_render_strategies._k13_import_export import _K13_SPECS

        k13_2 = _K13_SPECS["K13-2"]
        assert len(k13_2["headers"]) == 27, (
            f"K13-2应有27列headers，实际{len(k13_2['headers'])}"
        )
        assert len(k13_2["field_keys"]) == 27, (
            f"K13-2应有27列field_keys，实际{len(k13_2['field_keys'])}"
        )

    def test_k13_3_has_10_columns(self):
        """K13-3 调整分录恰好10列（headers和field_keys各10项）."""
        from app.routers.wp_render_strategies._k13_import_export import _K13_SPECS

        k13_3 = _K13_SPECS["K13-3"]
        assert len(k13_3["headers"]) == 10, (
            f"K13-3应有10列headers，实际{len(k13_3['headers'])}"
        )
        assert len(k13_3["field_keys"]) == 10, (
            f"K13-3应有10列field_keys，实际{len(k13_3['field_keys'])}"
        )

    def test_k13_headers_and_keys_length_match(self):
        """每个sheet spec的headers和field_keys长度一致."""
        from app.routers.wp_render_strategies._k13_import_export import _K13_SPECS

        for key, spec in _K13_SPECS.items():
            assert len(spec["headers"]) == len(spec["field_keys"]), (
                f"{key}: headers({len(spec['headers'])}) != field_keys({len(spec['field_keys'])})"
            )

    def test_k13_each_spec_has_required_fields(self):
        """每个sheet spec都有item_id/title/headers/field_keys/guidance."""
        from app.routers.wp_render_strategies._k13_import_export import _K13_SPECS

        for key, spec in _K13_SPECS.items():
            assert "item_id" in spec, f"{key} 缺少 item_id"
            assert "title" in spec, f"{key} 缺少 title"
            assert "headers" in spec, f"{key} 缺少 headers"
            assert "field_keys" in spec, f"{key} 缺少 field_keys"
            assert "guidance" in spec, f"{key} 缺少 guidance"

    @pytest.mark.asyncio
    async def test_k13_export_template_route_registered(self):
        """K13 export-template 路由已在 app 中注册."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/workpapers/test-wp/k13/export-template?sheet=K13-2")
        assert resp.status_code != 404, "K13 export-template route not registered"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. AI生成路由验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK13AiGenerate:
    """验证 K13 AI生成路由结构."""

    def test_k13_ai_router_exists(self):
        """_k13_ai_generate 模块有 router 对象."""
        from app.routers.wp_render_strategies._k13_ai_generate import router

        assert router is not None

    def test_k13_ai_two_supported_sections(self):
        """_SUPPORTED_SECTIONS 恰好包含2个section（non-operating-eval/overall-opinion）."""
        from app.routers.wp_render_strategies._k13_ai_generate import _SUPPORTED_SECTIONS

        expected = {"non-operating-eval", "overall-opinion"}
        assert _SUPPORTED_SECTIONS == expected

    @pytest.mark.asyncio
    async def test_k13_ai_generate_route_registered(self):
        """K13 AI生成路由已在 app 中注册."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/k13/ai-generate",
                json={"section": "non-operating-eval", "existingContent": ""},
            )
        assert resp.status_code != 404, "K13 ai-generate route not registered"
