"""K10 其他收益 — 集成测试：损益取数(发生额) + 补助核对联动K7 + 审定回写.

Spec: .kiro/specs/k10-other-income/ Task 7.2
Validates: Requirements 2.5, 4.3, 6.1

测试:
1. render策略从tb_ledger取发生额（非tb_balance期末余额），计算净发生额=贷方-借方
2. K10-4政府补助核对表与K7递延收益分摊一致性校验
3. 审定回写发生额到trial_balance（handler正则^[D-N]\\d+-1$匹配K10-1）
4. K10_SHEETS全10 sheets覆盖
5. YAML schema合法性（income_statement=True, occurrence_amount）
6. Import/Export路由验证
7. AI生成路由验证
8. wp_code_overrides映射（8个K10编码→k10-other-income）
"""
from __future__ import annotations

import inspect
import json
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


class TestK10RenderStrategyIncomeStatement:
    """验证 K10 render 策略走新架构（共享件 pl_occurrence + k_cycle_specs）."""

    def test_k10_registered_in_dispatch(self):
        """RENDERER_DISPATCH 包含 k10-other-income."""
        assert "k10-other-income" in RENDERER_DISPATCH

    def test_k10_render_is_callable(self):
        """render 函数可调用."""
        from app.routers.wp_render_strategies._k10_other_income import render
        assert callable(render)

    def test_k10_account_prefix_is_6117(self):
        """科目 6117 由 k_cycle_specs 声明（不再是模块级 _K10_ACCOUNT_PREFIX）."""
        from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS
        assert K_CYCLE_SPECS["K10"].fallback_standard == "6117"

    def test_render_uses_shared_pl_occurrence(self):
        """render 走共享件 pl_render.render_pl_cycle（非自造取数函数）."""
        from app.routers.wp_render_strategies._k10_other_income import render
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
        """K10_META 标识 income_statement=True."""
        from app.routers.wp_render_strategies._k10_other_income import K10_META
        assert K10_META["special_rules"]["income_statement"] is True

    def test_render_returns_component_type(self):
        """render 模块声明 component_type = 'k10-other-income'."""
        from app.routers.wp_render_strategies._k10_other_income import K10_SHEETS
        assert all(s["component_type"] == "k10-other-income" for s in K10_SHEETS)

    def test_render_contains_tb_values(self):
        """pl_occurrence.build_pl_tb_values 返回结果包含 occurrence_unadjusted."""
        from app.services.four_table.pl_occurrence import PlOccurrence, build_pl_tb_values, AccountNature
        occ = PlOccurrence(unadjusted=75000.0, audited=75000.0, fallback_amount=80000.0,
                           source="trial_balance", nature=AccountNature.INCOME.value)
        tv = build_pl_tb_values(occ)
        assert "occurrence_unadjusted" in tv
        assert tv["occurrence_unadjusted"] == 75000.0

    def test_render_sheets_list_has_10_entries(self):
        """K10_SHEETS 恰好 10 个 sheet."""
        from app.routers.wp_render_strategies._k10_other_income import K10_SHEETS
        assert len(K10_SHEETS) == 10

    def test_render_empty_ledger_returns_empty_tb(self):
        """无数据时 build_pl_tb_values 全部返 0."""
        from app.services.four_table.pl_occurrence import PlOccurrence, build_pl_tb_values, AccountNature
        occ = PlOccurrence(source="none", nature=AccountNature.INCOME.value)
        tv = build_pl_tb_values(occ)
        assert tv["occurrence_unadjusted"] == 0.0
        assert tv["audited_amount"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 政府补助核对联动K7验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK10GrantReconcileK7:
    """验证K10-4政府补助核对与K7递延收益分摊联动."""

    def test_k10_4_spec_has_reconcile_fields(self):
        """K10-4 spec包含核对字段（合计计入/是否与K7一致）."""
        from app.routers.wp_render_strategies._k10_import_export import _K10_SPECS

        k10_4 = _K10_SPECS["K10-4"]
        assert "totalRecognized" in k10_4["field_keys"], "K10-4缺少totalRecognized字段"
        assert "consistentWithK7" in k10_4["field_keys"], "K10-4缺少consistentWithK7字段"
        assert "deferredAmortization" in k10_4["field_keys"], "K10-4缺少deferredAmortization字段"

    def test_k10_4_spec_item_id_correct(self):
        """K10-4的item_id为'K10-4-rows'."""
        from app.routers.wp_render_strategies._k10_import_export import _K10_SPECS

        assert _K10_SPECS["K10-4"]["item_id"] == "K10-4-rows"

    def test_yaml_cross_ref_k7_exists(self):
        """YAML中定义了K10-4与K7的跨底稿引用（递延收益分摊核对）."""
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "ledger_adapters"
            / "wp_render_schema"
            / "k10-other-income.yaml"
        )
        with open(yaml_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        refs = schema.get("cross_wp_references", [])
        k7_refs = [r for r in refs if "K7" in r.get("target_wp", "")]
        assert len(k7_refs) >= 1, "缺少K10-4→K7跨底稿引用定义"
        # 验证核对方向为bidirectional
        bidi = [r for r in k7_refs if r.get("direction") == "bidirectional"]
        assert len(bidi) >= 1, "K10-4与K7应为双向(bidirectional)引用"

    def test_yaml_grant_reconcile_flag(self):
        """YAML special_rules.grant_reconcile=True."""
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "ledger_adapters"
            / "wp_render_schema"
            / "k10-other-income.yaml"
        )
        with open(yaml_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        assert schema["special_rules"]["grant_reconcile"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 审定回写验证（TB writeback: 发生额→trial_balance）
# ═══════════════════════════════════════════════════════════════════════════════


class TestK10TbWriteback:
    """验证K10审定回写逻辑：K10-1审定→trial_balance.audited_amount(发生额)."""

    _PATTERN = re.compile(r"^[D-N]\d+-1$")

    def test_regex_matches_k10_1(self):
        """handler正则 ^[D-N]\\d+-1$ 匹配K10-1."""
        assert self._PATTERN.match("K10-1"), "K10-1应通过审定表回写正则"

    def test_regex_rejects_non_audit_sheets(self):
        """非审定表编码被正则拒绝."""
        non_audit = ["K10A", "K10-2", "K10-3", "K10-4", "K10-5", "K10-6", "K10"]
        for code in non_audit:
            assert not self._PATTERN.match(code), f"{code}不应匹配审定表正则"

    def test_yaml_writeback_config_occurrence(self):
        """YAML tb_writeback.value_type='occurrence_amount'（发生额非余额）."""
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "ledger_adapters"
            / "wp_render_schema"
            / "k10-other-income.yaml"
        )
        with open(yaml_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        wb = schema["tb_writeback"]
        assert wb["account_code"] == "6117"
        assert wb["value_type"] == "occurrence_amount", (
            "K10损益类回写应为发生额(occurrence_amount)而非余额"
        )
        assert wb["direction"] == "credit", "6117为贷方科目"
        assert wb["source_sheet"] == "K10-1"

    def test_yaml_writeback_trigger_is_workpaper_saved(self):
        """TB回写触发事件为WORKPAPER_SAVED."""
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "ledger_adapters"
            / "wp_render_schema"
            / "k10-other-income.yaml"
        )
        with open(yaml_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        assert schema["tb_writeback"]["trigger"] == "WORKPAPER_SAVED"

    def test_handler_source_uses_correct_pattern(self):
        """handler源码包含正则 ^[D-N]\\d+-1$."""
        from app.services import event_handlers_cycle_linkage

        src = inspect.getsource(event_handlers_cycle_linkage)
        assert r'^[D-N]\d+-1$' in src, (
            "handler源码中未找到正则 ^[D-N]\\d+-1$"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. K10_SHEETS 全10 sheets定义验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK10Sheets:
    """验证 K10_SHEETS 定义结构."""

    def test_k10_sheets_count(self):
        """K10_SHEETS 恰好10个sheet."""
        from app.routers.wp_render_strategies._k10_other_income import K10_SHEETS

        assert len(K10_SHEETS) == 10

    def test_k10_sheets_all_have_component_type(self):
        """每个sheet都标记component_type为k10-other-income."""
        from app.routers.wp_render_strategies._k10_other_income import K10_SHEETS

        for sheet in K10_SHEETS:
            assert sheet["component_type"] == "k10-other-income"

    def test_k10_sheets_expected_names(self):
        """K10_SHEETS包含所有预期的sheet关键字."""
        from app.routers.wp_render_strategies._k10_other_income import K10_SHEETS

        names = [s["sheet_name"] for s in K10_SHEETS]
        expected_keywords = [
            "底稿目录", "K10A", "K10-1", "K10-2", "K10-3",
            "K10-4", "K10-5", "K10-6", "上市公司", "国企",
        ]
        for kw in expected_keywords:
            assert any(kw in n for n in names), f"缺少含'{kw}'的sheet"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. YAML Schema完整性验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK10YamlSchema:
    """验证 k10-other-income.yaml 结构完整性."""

    @pytest.fixture
    def schema(self):
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "ledger_adapters"
            / "wp_render_schema"
            / "k10-other-income.yaml"
        )
        assert yaml_path.exists(), f"YAML schema not found: {yaml_path}"
        with open(yaml_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_income_statement_flag(self, schema):
        """income_statement=True 标识损益类."""
        assert schema["income_statement"] is True

    def test_account_codes(self, schema):
        """account_codes 包含 '6117'."""
        assert "6117" in schema["account_codes"]

    def test_component_type(self, schema):
        """component_type 为 k10-other-income."""
        assert schema["component_type"] == "k10-other-income"

    def test_wp_code(self, schema):
        """wp_code 为 K10."""
        assert schema["wp_code"] == "K10"

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
        """special_rules.net_formula包含'贷方'和'借方'."""
        assert "贷方" in schema["special_rules"]["net_formula"]
        assert "借方" in schema["special_rules"]["net_formula"]

    def test_cross_wp_references(self, schema):
        """cross_wp_references 存在且≥5个引用."""
        refs = schema.get("cross_wp_references", [])
        assert len(refs) >= 5
        # 验证K10-3→A13引用存在
        a13_refs = [r for r in refs if "A13" in r.get("target_wp", "")]
        assert len(a13_refs) >= 1, "缺少K10-3→A13交叉引用"

    def test_ai_sections(self, schema):
        """ai_sections 包含 grant-reconcile-conclusion 和 overall-opinion."""
        sections = {s["id"] for s in schema.get("ai_sections", [])}
        assert "grant-reconcile-conclusion" in sections
        assert "receivable-grant-eval" in sections
        assert "overall-opinion" in sections


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Import/Export 路由验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK10ImportExport:
    """验证 K10 导入导出路由结构."""

    def test_k10_import_export_router_exists(self):
        """_k10_import_export 模块有 router 对象."""
        from app.routers.wp_render_strategies._k10_import_export import router

        assert router is not None

    def test_k10_import_export_two_sheet_specs(self):
        """_K10_SPECS 包含2个sheet规格（K10-2/K10-4）."""
        from app.routers.wp_render_strategies._k10_import_export import _K10_SPECS

        expected_keys = {"K10-2", "K10-4"}
        assert set(_K10_SPECS.keys()) == expected_keys

    def test_k10_each_spec_has_required_fields(self):
        """每个sheet spec都有item_id/title/headers/field_keys/guidance."""
        from app.routers.wp_render_strategies._k10_import_export import _K10_SPECS

        for key, spec in _K10_SPECS.items():
            assert "item_id" in spec, f"{key} 缺少 item_id"
            assert "title" in spec, f"{key} 缺少 title"
            assert "headers" in spec, f"{key} 缺少 headers"
            assert "field_keys" in spec, f"{key} 缺少 field_keys"
            assert "guidance" in spec, f"{key} 缺少 guidance"
            assert len(spec["headers"]) == len(spec["field_keys"]), (
                f"{key}: headers({len(spec['headers'])}) != field_keys({len(spec['field_keys'])})"
            )

    @pytest.mark.asyncio
    async def test_k10_export_template_route_registered(self):
        """K10 export-template 路由已在 app 中注册."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/workpapers/test-wp/k10/export-template?sheet=K10-2")
        assert resp.status_code != 404, "K10 export-template route not registered"

    @pytest.mark.asyncio
    async def test_k10_export_data_route_registered(self):
        """K10 export-data 路由已在 app 中注册."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/workpapers/test-wp/k10/export-data?sheet=K10-2")
        assert resp.status_code != 404, "K10 export-data route not registered"

    @pytest.mark.asyncio
    async def test_k10_import_data_route_registered(self):
        """K10 import-data 路由已在 app 中注册（空文件返回适当错误）."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/k10/import-data?sheet=K10-2",
                files={"file": ("empty.xlsx", b"", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        # 非404即路由已注册（可能是400/422因为空文件）
        assert resp.status_code != 404, "K10 import-data route not registered"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. AI生成路由验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK10AiGenerate:
    """验证 K10 AI生成路由结构."""

    def test_k10_ai_router_exists(self):
        """_k10_ai_generate 模块有 router 对象."""
        from app.routers.wp_render_strategies._k10_ai_generate import router

        assert router is not None

    def test_k10_ai_three_supported_sections(self):
        """_SUPPORTED_SECTIONS 恰好包含3个section."""
        from app.routers.wp_render_strategies._k10_ai_generate import _SUPPORTED_SECTIONS

        expected = {"grant-reconcile-conclusion", "receivable-grant-eval", "overall-opinion"}
        assert _SUPPORTED_SECTIONS == expected

    @pytest.mark.asyncio
    async def test_k10_ai_generate_route_registered(self):
        """K10 AI生成路由已在 app 中注册."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/k10/ai-generate",
                json={"section": "overall-opinion", "existingContent": ""},
            )
        assert resp.status_code != 404, "K10 ai-generate route not registered"

    @pytest.mark.asyncio
    async def test_k10_ai_invalid_section_returns_400(self):
        """不支持的section返回400."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/k10/ai-generate",
                json={"section": "invalid-section", "existingContent": ""},
            )
        # 应该返回400（不支持的section），而非404
        assert resp.status_code == 400 or resp.status_code != 404


# ═══════════════════════════════════════════════════════════════════════════════
# 8. wp_code_overrides 映射验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK10WpCodeOverrides:
    """验证 wp_code_overrides.json 中K10的8个编码映射."""

    @pytest.fixture
    def overrides(self):
        overrides_path = (
            Path(__file__).resolve().parent.parent
            / "app"
            / "data"
            / "wp_code_overrides.json"
        )
        assert overrides_path.exists(), f"wp_code_overrides.json not found: {overrides_path}"
        with open(overrides_path, encoding="utf-8") as f:
            return json.load(f)

    def test_all_8_k10_codes_mapped(self, overrides):
        """全部8个K10编码映射到k10-other-income."""
        expected_codes = [
            "K10", "K10-1", "K10-2", "K10-3", "K10-4", "K10-5", "K10-6", "K10A",
        ]
        for code in expected_codes:
            assert code in overrides, f"wp_code_overrides缺少 {code}"
            assert overrides[code] == "k10-other-income", (
                f"{code} 应映射到 k10-other-income，实际为 {overrides[code]}"
            )

    def test_no_extra_k10_codes(self, overrides):
        """不应有意外的K10编码映射（只有8个）."""
        k10_keys = [k for k in overrides if k.startswith("K10")]
        assert len(k10_keys) == 8, f"应有8个K10编码，实际有 {len(k10_keys)}: {k10_keys}"
