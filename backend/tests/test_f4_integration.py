"""F4 应付账款 — 后端集成测试：负债类期末余额 + 审定回写 + 导入导出 + AI生成.

Spec: .kiro/specs/f4-accounts-payable/ Task 7.2
Validates: Requirements 2.5, 4.3, 6.1

测试:
1. render策略从tb_balance取期末余额（贷方/负债类科目2202）
2. 审定回写期末余额到trial_balance（handler正则^[D-N]\\d+-1$匹配F4-1）
3. wp_code_overrides映射（12个F4编码→f4-accounts-payable）
4. Import/Export路由验证（12个sheet specs）
5. AI生成路由验证
6. F4_SHEETS定义验证（12 sheets）
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
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
# 1. Render策略验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestF4RenderStrategy:
    """验证 F4 render策略：负债类(贷方)科目2202，从tb_balance取期末余额."""

    def test_f4_registered_in_dispatch(self):
        """RENDERER_DISPATCH 包含 'f4-accounts-payable'."""
        assert "f4-accounts-payable" in RENDERER_DISPATCH

    def test_f4_render_is_callable(self):
        """render 函数可调用."""
        from app.routers.wp_render_strategies._f4_accounts_payable import render

        assert callable(render)

    @pytest.mark.asyncio
    async def test_render_returns_correct_structure(self):
        """render 返回正确结构 (component_type, account_code='2202', prefix='F4', sheets, responses_snapshot)."""
        from app.routers.wp_render_strategies._f4_accounts_payable import render

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        ctx = MagicMock()
        ctx.db = mock_db
        ctx.project_id = "test-project"
        ctx.year = 2025
        ctx.wp_id = "test-wp-id"

        result = await render(ctx)

        assert result is not None
        assert result["component_type"] == "f4-accounts-payable"
        assert result["account_code"] == "2202"
        assert result["prefix"] == "F4"
        assert result["sheets"] is not None
        assert "responses_snapshot" in result

    def test_f4_sheets_count_is_12(self):
        """F4_SHEETS 恰好12个sheet."""
        from app.routers.wp_render_strategies._f4_accounts_payable import F4_SHEETS

        assert len(F4_SHEETS) == 12


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 审定回写验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestF4TbWriteback:
    """验证F4审定回写逻辑：F4-1审定→trial_balance（负债类/贷方/期末余额）."""

    _PATTERN = re.compile(r"^[D-N]\d+-1$")

    def test_regex_matches_f4_1(self):
        """handler正则 ^[D-N]\\d+-1$ 匹配 F4-1."""
        assert self._PATTERN.match("F4-1"), "F4-1应通过审定表回写正则"

    def test_regex_rejects_non_audit_sheets(self):
        """拒绝非审定表编码 (F4A, F4-2, F4-3...F4-9, F4)."""
        non_audit = ["F4A", "F4-2", "F4-3", "F4-4", "F4-5", "F4-6", "F4-7", "F4-8", "F4-9", "F4"]
        for code in non_audit:
            assert not self._PATTERN.match(code), f"{code}不应匹配审定表正则"

    def test_handler_source_uses_correct_pattern(self):
        """handler源码包含该正则 ^[D-N]\\d+-1$."""
        from app.services import event_handlers_cycle_linkage

        src = inspect.getsource(event_handlers_cycle_linkage)
        assert r'^[D-N]\d+-1$' in src, (
            "handler源码中未找到正则 ^[D-N]\\d+-1$"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. wp_code_overrides映射验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestF4WpCodeOverrides:
    """验证 wp_code_overrides.json 中F4的12个编码映射."""

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

    def test_all_12_f4_codes_mapped(self, overrides):
        """全部12个F4编码映射到 'f4-accounts-payable'."""
        expected_codes = [
            "F4A", "F4-1", "F4-2", "F4-3", "F4-4", "F4-5",
            "F4-6", "F4-7", "F4-8", "F4-9", "F4-note-listed", "F4-note-soe",
        ]
        for code in expected_codes:
            assert code in overrides, f"wp_code_overrides缺少 {code}"
            assert overrides[code] == "f4-accounts-payable", (
                f"{code} 应映射到 f4-accounts-payable，实际为 {overrides[code]}"
            )

    def test_no_extra_f4_codes(self, overrides):
        """不应有意外的F4编码."""
        f4_keys = [k for k in overrides if k.startswith("F4")]
        assert len(f4_keys) == 12, f"应有12个F4编码，实际有 {len(f4_keys)}: {f4_keys}"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Import/Export路由验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestF4ImportExport:
    """验证 F4 导入导出路由结构."""

    def test_f4_import_export_router_exists(self):
        """_f4_import_export 模块有 router 对象."""
        from app.routers.wp_render_strategies._f4_import_export import router

        assert router is not None

    def test_f4_import_export_sheet_specs(self):
        """包含F4-1双分类、F4-7五段、F4-8借贷及F4-9共14个sheet specs."""
        from app.routers.wp_render_strategies._f4_import_export import _F4_SPECS

        expected_keys = {
            "F4-1-nature", "F4-1-aging",
            "F4-2", "F4-3", "F4-5", "F4-6",
            "F4-7-payment-window", "F4-7-estimated-inbound",
            "F4-7-unprocessed-invoice", "F4-7-subsequent-payment",
            "F4-7-subsequent-increase",
            "F4-8-debit", "F4-8-credit",
            "F4-9",
        }
        assert set(_F4_SPECS.keys()) == expected_keys

    def test_f4_each_spec_has_required_fields(self):
        """每个spec有 item_id/title/headers/field_keys."""
        from app.routers.wp_render_strategies._f4_import_export import _F4_SPECS

        for key, spec in _F4_SPECS.items():
            assert "item_id" in spec, f"{key} 缺少 item_id"
            assert "title" in spec, f"{key} 缺少 title"
            assert "headers" in spec, f"{key} 缺少 headers"
            assert "field_keys" in spec, f"{key} 缺少 field_keys"
            assert len(spec["headers"]) == len(spec["field_keys"]), (
                f"{key}: headers({len(spec['headers'])}) != field_keys({len(spec['field_keys'])})"
            )

    def test_f4_2_spec_matches_source_27_columns(self):
        """F4-2导入导出严格对应源表A:AA，无旧版自造字段."""
        from app.routers.wp_render_strategies._f4_import_export import _F4_SPECS

        spec = _F4_SPECS["F4-2"]
        assert len(spec["headers"]) == 27
        assert spec["headers"][:4] == ["债权人名称", "公司代码", "关联方类型", "款项性质"]
        assert spec["headers"][13:17] == [
            "未审账龄-1年以下", "未审账龄-1～2年", "未审账龄-2～3年", "未审账龄-3年以上",
        ]
        assert spec["headers"][20:24] == [
            "审定账龄-1年以下", "审定账龄-1～2年", "审定账龄-2～3年", "审定账龄-3年以上",
        ]
        assert "confirmationResult" not in spec["field_keys"]
        assert "subsequentPaymentDate" not in spec["field_keys"]
        assert "indexRef" not in spec["field_keys"]

    def test_f4_5_spec_matches_source_11_columns(self):
        """F4-5导入导出对应账龄1年以上检查表原始11列."""
        from app.routers.wp_render_strategies._f4_import_export import _F4_SPECS

        spec = _F4_SPECS["F4-5"]
        assert spec["headers"] == [
            "债权人名称", "期末余额", "账龄", "经济业务说明", "未偿还或未结转的原因",
            "是否无法支付", "是否诉讼", "支付计划", "审定金额", "支持性证据", "备注",
        ]
        assert spec["field_keys"] == [
            "creditor", "closingBalance", "aging", "businessDescription", "unsettledReason",
            "unableToPay", "litigation", "paymentPlan", "auditedAmount", "supportingEvidence", "remark",
        ]

    def test_f4_6_spec_matches_source_12_columns(self):
        """F4-6导入导出对应关联方及交易检查表原始12列."""
        from app.routers.wp_render_strategies._f4_import_export import _F4_SPECS

        spec = _F4_SPECS["F4-6"]
        assert spec["headers"] == [
            "关联方名称", "关联关系", "期初余额", "本期借方", "本期贷方", "期末余额",
            "账龄", "定价政策", "发生原因（款项性质）", "期后付款金额", "索引号", "备注",
        ]
        assert spec["field_keys"] == [
            "partyName", "relationship", "openingBalance", "currentDebit", "currentCredit",
            "closingBalance", "aging", "pricingPolicy", "transactionNature",
            "postPaymentAmount", "indexNo", "remark",
        ]

    def test_f4_7_specs_match_five_source_sections(self):
        """F4-7按源表五段分别导入导出，不再使用旧三段通用表."""
        from app.routers.wp_render_strategies._f4_import_export import _F4_SPECS

        keys = {
            "F4-7-payment-window", "F4-7-estimated-inbound",
            "F4-7-unprocessed-invoice", "F4-7-subsequent-payment",
            "F4-7-subsequent-increase",
        }
        assert keys.issubset(_F4_SPECS)
        assert len(_F4_SPECS["F4-7-payment-window"]["headers"]) == 10
        assert len(_F4_SPECS["F4-7-estimated-inbound"]["headers"]) == 10
        assert len(_F4_SPECS["F4-7-unprocessed-invoice"]["headers"]) == 9
        assert len(_F4_SPECS["F4-7-subsequent-payment"]["headers"]) == 9
        assert len(_F4_SPECS["F4-7-subsequent-increase"]["headers"]) == 9

    @pytest.mark.asyncio
    async def test_f4_export_template_route_registered(self):
        """export-template 路由注册 (POST /api/workpapers/test-wp/f4/export-template?sheet=F4-2, 非404)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/workpapers/test-wp/f4/export-template?sheet=F4-2")
        assert resp.status_code != 404, "F4 export-template route not registered"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. AI生成路由验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestF4AiGenerate:
    """验证 F4 AI生成路由结构."""

    def test_f4_ai_router_exists(self):
        """_f4_accounts_payable_ai 模块有 router 对象."""
        from app.routers.wp_render_strategies._f4_accounts_payable_ai import router

        assert router is not None

    @pytest.mark.asyncio
    async def test_f4_ai_generate_route_registered(self):
        """ai-generate 路由注册 (POST /api/workpapers/test-wp/f4/ai-generate, 非404)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/f4/ai-generate",
                json={"section": "substantive-analysis", "existingContent": ""},
            )
        assert resp.status_code != 404, "F4 ai-generate route not registered"

    def test_f4_contract_ocr_router_exists(self):
        """F4长期挂账OCR模块有router及字段schema."""
        from app.routers.wp_render_strategies._f4_contract_ocr import (
            LONG_OUTSTANDING_FIELDS_SCHEMA,
            router,
        )

        assert router is not None
        assert set(LONG_OUTSTANDING_FIELDS_SCHEMA) == {
            "creditor", "closingBalance", "aging", "businessDescription",
            "unsettledReason", "unableToPay", "litigation", "paymentPlan",
            "auditedAmount", "supportingEvidence", "remark",
        }

    def test_f4_contract_ocr_supports_all_unrecorded_sections(self):
        """F4 OCR提供F4-7五种多单据提取schema."""
        from app.routers.wp_render_strategies._f4_contract_ocr import DOCUMENT_SCHEMAS

        assert {
            "unrecorded-payment-window",
            "unrecorded-estimated-inbound",
            "unrecorded-unprocessed-invoice",
            "unrecorded-subsequent-payment",
            "unrecorded-subsequent-increase",
        }.issubset(DOCUMENT_SCHEMAS)

    def test_f4_contract_ocr_supports_voucher_check_documents(self):
        """F4 OCR提供F4-8弹窗逐单据核对schema."""
        from app.routers.wp_render_strategies._f4_contract_ocr import DOCUMENT_SCHEMAS

        assert {
            "voucher",
            "approval",
            "bank-receipt",
            "goods-receipt",
            "invoice",
        }.issubset(DOCUMENT_SCHEMAS)
        assert "supplierName" in DOCUMENT_SCHEMAS["voucher"]
        assert "approvalProper" in DOCUMENT_SCHEMAS["approval"]
        assert "bankAmount" in DOCUMENT_SCHEMAS["bank-receipt"]
        assert "receiptProduct" in DOCUMENT_SCHEMAS["goods-receipt"]
        assert "invoiceAmount" in DOCUMENT_SCHEMAS["invoice"]

    def test_f4_8_spec_matches_source_debit_credit_columns(self):
        """F4-8导入导出对应借/贷两区源表字段，不再使用旧三单匹配字段."""
        from app.routers.wp_render_strategies._f4_import_export import _F4_SPECS

        debit = _F4_SPECS["F4-8-debit"]
        credit = _F4_SPECS["F4-8-credit"]
        assert debit["headers"][:7] == [
            "供应商名称", "日期", "凭证编号", "业务内容", "对方科目", "明细科目", "借方金额",
        ]
        assert "付款审批单日期/编号" in debit["headers"]
        assert "银行回单日期" in debit["headers"]
        assert "threeWayMatch" not in debit["field_keys"]
        assert credit["headers"][:7] == [
            "供应商名称", "日期", "凭证编号", "业务内容", "对方科目", "明细科目", "贷方金额",
        ]
        assert "入库单日期/编号" in credit["headers"]
        assert "发票金额" in credit["headers"]
        assert "purchaseOrder" not in credit["field_keys"]

    def test_f4_ai_supports_voucher_check_sections(self):
        """F4 AI支持检查表说明、结论与单笔异常说明."""
        from app.routers.wp_render_strategies._f4_accounts_payable_ai import _SUPPORTED_SECTIONS

        assert {
            "voucher-check",
            "voucher-check-note",
            "voucher-check-conclusion",
            "voucher-check-issue",
        }.issubset(_SUPPORTED_SECTIONS)

    def test_f4_9_spec_matches_source_supplier_financing_columns(self):
        """F4-9导入导出对应供应商融资源表字段，不再使用旧三区模型."""
        from app.routers.wp_render_strategies._f4_import_export import _F4_SPECS

        spec = _F4_SPECS["F4-9"]
        assert spec["headers"][:6] == [
            "供应商名称", "承诺付款方", "融资单号", "资金提供方（金融机构）", "状态", "融资金额",
        ]
        assert "本期采购金额" in spec["headers"]
        assert "借款余额" in spec["headers"]
        assert "difference" not in spec["field_keys"]  # 公式列不导入
        assert "F4-9-factoring" not in _F4_SPECS

    def test_f4_contract_ocr_supports_supplier_financing(self):
        """F4 OCR提供供应商融资单据提取schema."""
        from app.routers.wp_render_strategies._f4_contract_ocr import DOCUMENT_SCHEMAS

        assert "supplier-financing" in DOCUMENT_SCHEMAS
        assert "financingNo" in DOCUMENT_SCHEMAS["supplier-financing"]
        assert "financingAmount" in DOCUMENT_SCHEMAS["supplier-financing"]

    def test_f4_ai_supports_financing_sections(self):
        """F4 AI支持供应商融资说明与结论."""
        from app.routers.wp_render_strategies._f4_accounts_payable_ai import _SUPPORTED_SECTIONS

        assert {
            "financing-evaluation",
            "financing-note",
            "financing-conclusion",
        }.issubset(_SUPPORTED_SECTIONS)

    @pytest.mark.asyncio
    async def test_f4_contract_ocr_route_registered(self):
        """contract-ocr路由注册；缺少file应为422而非404."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/workpapers/test-wp/f4/contract-ocr")
        assert resp.status_code != 404, "F4 contract-ocr route not registered"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. F4_SHEETS定义验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestF4Sheets:
    """验证 F4_SHEETS 定义结构."""

    def test_f4_sheets_count(self):
        """F4_SHEETS 恰好12个sheet."""
        from app.routers.wp_render_strategies._f4_accounts_payable import F4_SHEETS

        assert len(F4_SHEETS) == 12

    def test_f4_sheets_expected_names(self):
        """包含所有预期名称: F4A/F4-1~F4-9/附注披露(上市)/附注披露(国企)."""
        from app.routers.wp_render_strategies._f4_accounts_payable import F4_SHEETS

        expected_keywords = [
            "F4A", "F4-1", "F4-2", "F4-3", "F4-4",
            "F4-5", "F4-6", "F4-7", "F4-8", "F4-9",
            "附注披露(上市)", "附注披露(国企)",
        ]
        for kw in expected_keywords:
            assert kw in F4_SHEETS, f"F4_SHEETS 缺少 '{kw}'"
