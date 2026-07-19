"""G7 长期股权投资(子公司组) — 后端单元测试.

Spec: .kiro/specs/g7-long-term-equity-subsidiary/ Task 11.6
Validates: Requirements 1.1, 7.1, 7.3

Tests:
  1. Render策略返回正确componentType + 7个sheet配置
  2. Service公式验证逻辑(validate_formulas正确/错误场景)
  3. 导入导出格式校验(不支持的sheet code / 非xlsx文件)
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook

from app.core.database import get_db
from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.routers.wp_render_strategies._g7_long_term_equity_subsidiary import (
    G7_SUBSIDIARY_SHEETS,
)
from app.routers.wp_render_strategies._g7_long_term_equity_subsidiary_service import (
    G7SubsidiaryService,
)
from app.routers.wp_render_strategies._g7_long_term_equity_subsidiary_import_export import (
    _build_g7_8_workbook,
    _build_g7_9_workbook,
    _parse_g7_8_import,
    _parse_g7_9_import,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeUser:
    id = "test-user-id"
    name = "Test User"
    email = "test@example.com"
    role = UserRole.admin


@pytest.fixture(autouse=True)
def override_deps():
    """Override DB and auth dependencies for all tests."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()

    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=None)
    mock_result.fetchone = AsyncMock(return_value=None)
    mock_result.fetchall = AsyncMock(return_value=[])
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db
    yield mock_db
    app.dependency_overrides.clear()


def _make_xlsx_bytes(headers: list[str], rows: list[list] | None = None) -> bytes:
    """Create minimal xlsx bytes."""
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    if rows:
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def test_g7_8_three_section_export_import_roundtrip():
    source_rows = [
        {
            "id": "m1",
            "section": "merger",
            "seq": 1,
            "investeeName": "公司1",
            "finalController": "最终控制方A",
            "ownerEquityBookValue": 100,
            "ownershipRatio": 0.32,
            "cashConsideration": 2,
            "nonCashAssetBookValue": 2,
            "debtBookValue": 3,
            "equitySecuritiesFaceValue": 0,
            "contingentConsideration": 3,
            "adjustmentTreatment": "增加资本公积",
            "indexRef": "G7-8-1",
            "auditConclusion": "无差异",
        },
        {
            "id": "s1",
            "section": "step",
            "companyId": "p",
            "companyName": "P公司",
            "seq": 1,
            "transactionNo": 1,
            "transactionDate": "2024-01-01",
            "purchaseRatio": 0.01,
            "consideration": 1,
            "netAssetsBookValue": 22,
            "priorInvestmentAdjustments": 22,
            "notPackageBasis": "独立交易",
            "indexRef": "G7-8-2",
        },
        {
            "id": "r1",
            "section": "reverse",
            "seq": 1,
            "transactionContent": "发行股份取得控制",
            "accountingAcquirer": "非上市公司A",
            "acquirerShareholders": "A原股东",
            "accountingAcquiree": "上市公司B",
            "acquireeOriginalShareholders": "B原股东",
            "reversePurchaseBasis": "A原股东取得控制",
            "businessDeterminationBasis": "B构成业务",
            "indexRef": "G7-8-3",
        },
    ]
    workbook = _build_g7_8_workbook(source_rows)
    buffer = io.BytesIO()
    workbook.save(buffer)

    parsed, errors = _parse_g7_8_import(buffer.getvalue())
    assert errors == []
    assert {row["section"] for row in parsed} == {"merger", "step", "reverse"}
    merger = next(row for row in parsed if row["section"] == "merger")
    assert merger["initialInvestmentCost"] == 32
    assert merger["totalConsideration"] == 10
    assert merger["capitalReserveRetainedEarningsAdjustment"] == 22


def test_g7_9_three_section_export_import_roundtrip():
    source_rows = [
        {
            "id": "m1",
            "section": "merger",
            "seq": 1,
            "investeeName": "目标公司",
            "acquisitionDate": "2024-06-30",
            "acquisitionDateEvidenceRef": "G7-9-A1",
            "cashConsideration": 100,
            "nonCashAssetFV": 20,
            "debtFV": 10,
            "equitySecuritiesFV": 5,
            "contingentConsiderationFV": 5,
            "priorHoldingFV": 40,
            "considerationBookValue": 120,
            "acquisitionCostsExpensed": 8,
            "acquireeIdentifiableNetAssetsFV": 200,
            "ownershipRatio": 0.8,
            "bargainPurchaseReviewed": "是",
            "bargainPurchaseReviewNote": "已复核",
            "considerationEvidenceRef": "G7-9-A2",
            "valuationReportRef": "G7-9-A3",
            "indexRef": "G7-9-1",
            "auditConclusion": "无差异",
        },
        {
            "id": "s1",
            "section": "step",
            "companyId": "p",
            "companyName": "P公司",
            "seq": 1,
            "transactionNo": 1,
            "transactionDate": "2024-01-01",
            "purchaseRatio": 0.3,
            "considerationFV": 30,
            # 兼容旧字段名，导出前应迁为 netAssetsFVAtTxn / priorEquityMethodAdjustments
            "netAssetsBookValueAtTxn": 100,
            "priorHoldingBookValue": 25,
            "priorHoldingFV": 40,
            "priorOCIReclassify": 2,
            "isPackageDeal": "否",
            "notPackageBasis": "独立定价",
            "indexRef": "G7-9-2",
        },
        {
            "id": "r1",
            "section": "reverse",
            "seq": 1,
            "transactionContent": "发行股份取得控制",
            "accountingAcquirer": "非上市公司A",
            "acquirerShareholders": "A原股东",
            "accountingAcquiree": "上市公司B",
            "acquireeOriginalShareholders": "B原股东",
            "reversePurchaseBasis": "A原股东取得控制",
            "constitutesBusiness": "是",
            "businessDeterminationBasis": "B构成业务",
            "indexRef": "G7-9-3",
        },
    ]
    workbook = _build_g7_9_workbook(source_rows)
    buffer = io.BytesIO()
    workbook.save(buffer)

    # 表头对齐源底稿编号
    merger_ws = workbook["1-一次购买取得"]
    merger_headers = [cell.value for cell in merger_ws[2]]
    assert "初始投资成本⑥=③+④" in merger_headers
    assert "对价损益⑦=③-⑤" in merger_headers
    assert "商誉/廉价购买利得⑧=⑥-①×②" in merger_headers
    assert "廉价购买已复核" in merger_headers
    reverse_ws = workbook["3-反向购买"]
    reverse_headers = [cell.value for cell in reverse_ws[2]]
    assert "是否构成业务" in reverse_headers

    parsed, errors = _parse_g7_9_import(buffer.getvalue())
    assert errors == []
    assert {row["section"] for row in parsed} == {"merger", "step", "reverse"}
    merger = next(row for row in parsed if row["section"] == "merger")
    assert merger["totalConsiderationFV"] == 140  # ③
    assert merger["initialInvestmentCost"] == 180  # ⑥=③+④
    assert merger["considerationGainLoss"] == 20  # ⑦=③−⑤
    assert merger["shareOfFV"] == 160
    assert merger["nonControllingInterestShare"] == 40
    assert merger["goodwill"] == 20  # ⑧=⑥−①×②
    assert merger["acquisitionCostsExpensed"] == 8
    assert merger["bargainPurchaseReviewed"] == "是"

    step = next(row for row in parsed if row["section"] == "step")
    assert step["netAssetsFVAtTxn"] == 100
    assert step["priorEquityMethodAdjustments"] == 2
    assert step["shareOfFVAtTxn"] == 30  # ④=①×③
    assert step["goodwillAtTxn"] == 0  # ⑤=②−④
    assert step["adjustmentScope"] == "transaction"
    assert step["companyId"] == "p"

    reverse = next(row for row in parsed if row["section"] == "reverse")
    assert reverse["constitutesBusiness"] == "是"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Render策略返回正确componentType
# ═══════════════════════════════════════════════════════════════════════════════


class TestRenderStrategy:
    """测试render策略返回结构正确性."""

    def test_sheets_count_is_7(self):
        """G7_SUBSIDIARY_SHEETS包含7个sheet配置."""
        assert len(G7_SUBSIDIARY_SHEETS) == 7

    def test_all_sheets_have_correct_component_type(self):
        """每个sheet的componentType == 'g7-long-term-equity-subsidiary'."""
        for sheet in G7_SUBSIDIARY_SHEETS:
            assert sheet["componentType"] == "g7-long-term-equity-subsidiary"

    def test_all_sheets_have_required_fields(self):
        """每个sheet有code/sheetName/group字段."""
        for sheet in G7_SUBSIDIARY_SHEETS:
            assert "code" in sheet, f"sheet缺少code: {sheet}"
            assert "sheetName" in sheet, f"sheet缺少sheetName: {sheet}"
            assert "group" in sheet, f"sheet缺少group: {sheet}"

    def test_sheet_codes_correct(self):
        """7个sheet的code分别为G7-7~G7-12和G7-18."""
        codes = [s["code"] for s in G7_SUBSIDIARY_SHEETS]
        expected = ["G7-7", "G7-8", "G7-9", "G7-10", "G7-11", "G7-12", "G7-18"]
        assert codes == expected

    def test_sheet_groups(self):
        """sheet按group正确分组: initial/subsequent/disposal/voucher."""
        groups = {s["code"]: s["group"] for s in G7_SUBSIDIARY_SHEETS}
        assert groups["G7-7"] == "initial"
        assert groups["G7-8"] == "initial"
        assert groups["G7-9"] == "initial"
        assert groups["G7-10"] == "subsequent"
        assert groups["G7-11"] == "disposal"
        assert groups["G7-12"] == "disposal"
        assert groups["G7-18"] == "voucher"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Service公式验证逻辑
# ═══════════════════════════════════════════════════════════════════════════════


class TestServiceFormulaValidation:
    """测试G7SubsidiaryService.validate_formulas各场景."""

    def setup_method(self):
        self.svc = G7SubsidiaryService(db=None)

    def test_validate_correct_data_no_errors(self):
        """正确数据 → 空error list."""
        data = {
            "same_control_checks": [
                {"row_key": "r1", "net_assets": 1000, "ratio": 0.6, "cost": 600},
            ],
            "not_same_control_checks": [
                {"row_key": "r2", "price": 500, "fees": 50, "cost": 500},
            ],
            "goodwill_checks": [
                {"row_key": "r3", "cost": 550, "share": 400, "goodwill": 150},
            ],
            "cost_method_income_checks": [
                {"row_key": "r4", "dividend": 100, "ratio": 0.6, "income": 60},
            ],
            "subsequent_balance_checks": [
                {"row_key": "r5", "opening": 1000, "addition": 200, "impairment": 50, "balance": 1150},
            ],
            "disposal_gain_checks": [
                {"row_key": "r6", "price": 800, "book_value": 600, "dividend": 20, "oci": 10, "gain": 190},
            ],
            "debit_credit_balance": {
                "debits": [100, 200, 300],
                "credits": [150, 250, 200],
            },
        }
        errors = self.svc.validate_formulas(data)
        assert errors == []

    def test_validate_wrong_same_control_cost(self):
        """同控成本错误 → 返回same_control_cost error."""
        data = {
            "same_control_checks": [
                {"row_key": "r1", "net_assets": 1000, "ratio": 0.6, "cost": 999},
            ],
        }
        errors = self.svc.validate_formulas(data)
        assert len(errors) == 1
        assert errors[0].field == "same_control_cost"
        assert errors[0].row_key == "r1"

    def test_validate_wrong_goodwill(self):
        """商誉错误 → 返回goodwill error."""
        data = {
            "goodwill_checks": [
                {"row_key": "r3", "cost": 550, "share": 400, "goodwill": 999},
            ],
        }
        errors = self.svc.validate_formulas(data)
        assert len(errors) == 1
        assert errors[0].field == "goodwill"
        assert errors[0].row_key == "r3"

    def test_validate_unbalanced_debits_credits(self):
        """借贷不平衡 → 返回debit_credit_balance error."""
        data = {
            "debit_credit_balance": {
                "debits": [100, 200],
                "credits": [500],
            },
        }
        errors = self.svc.validate_formulas(data)
        assert len(errors) == 1
        assert errors[0].field == "debit_credit_balance"
        assert errors[0].row_key == "voucher"

    def test_validate_empty_data_no_errors(self):
        """空数据(无任何检查项) → 空error list."""
        errors = self.svc.validate_formulas({})
        assert errors == []

    def test_validate_wrong_not_same_control_cost(self):
        """非同控成本错误 → 返回not_same_control_cost error."""
        data = {
            "not_same_control_checks": [
                {"row_key": "r2", "price": 500, "fees": 50, "cost": 999},
            ],
        }
        errors = self.svc.validate_formulas(data)
        assert len(errors) == 1
        assert errors[0].field == "not_same_control_cost"

    def test_prepare_g7_9_rows_recalculates_and_rejects_hard_errors(self):
        """G7-9实际rows由服务端重算，廉价购买/反向购买规则不可绕过。"""
        rows, errors = self.svc.prepare_g7_9_rows([
            {
                "id": "m1",
                "section": "merger",
                "cashConsideration": 100,
                "priorHoldingFV": 20,
                "considerationBookValue": 80,
                "acquireeIdentifiableNetAssetsFV": 100,
                "ownershipRatio": 0.6,
                "initialInvestmentCost": 999,
                "goodwill": 999,
            },
            {
                "id": "r1",
                "section": "reverse",
                "constitutesBusiness": "否",
                "businessDeterminationBasis": "仅持有资产",
            },
        ])
        assert rows[0]["initialInvestmentCost"] == 120
        assert rows[0]["considerationGainLoss"] == 20
        assert rows[0]["goodwill"] == 60
        assert any(error.field == "constitutesBusiness" for error in errors)

    def test_prepare_g7_9_step_generates_stable_company_id_and_recalculates(self):
        rows, errors = self.svc.prepare_g7_9_rows([
            {
                "section": "step",
                "companyId": "",
                "companyName": "P公司",
                "transactionNo": 1,
                "purchaseRatio": 0.3,
                "considerationFV": 40,
                "netAssetsFVAtTxn": 100,
                "priorEquityMethodAdjustments": 2,
                "isPackageDeal": "否",
            },
            {
                "section": "step",
                "companyId": "",
                "companyName": "P公司",
                "transactionNo": 2,
                "purchaseRatio": 0.4,
                "considerationFV": 50,
                "netAssetsFVAtTxn": 100,
                "priorEquityMethodAdjustments": 3,
                "isPackageDeal": "否",
            },
        ])
        assert errors == []
        assert rows[0]["companyId"] == rows[1]["companyId"]
        assert rows[0]["shareOfFVAtTxn"] == 30
        assert rows[0]["goodwillAtTxn"] == 10
        assert rows[0]["adjustmentScope"] == "transaction"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 导入导出格式校验(422/400错误)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestImportExportValidation:
    """测试导入导出端点对无效输入的错误处理."""

    async def test_unsupported_sheet_code_returns_400(self):
        """不支持的sheet code → 400."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/workpapers/test-wp/g7-sub/export-template",
                params={"sheet": "G7-INVALID"},
            )
            assert resp.status_code == 400
            body = resp.json()
            # ResponseWrapperMiddleware wraps as {code, message}
            msg = body.get("message", "") or body.get("detail", "")
            assert "不支持" in msg

    async def test_import_non_xlsx_file_returns_400(self):
        """非xlsx文件导入 → 400."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/workpapers/test-wp/g7-sub/import-data",
                params={"sheet": "G7-8"},
                files={"file": ("test.csv", b"some,csv,data", "text/csv")},
            )
            assert resp.status_code == 400

    async def test_export_template_valid_sheet_returns_200(self):
        """有效sheet code导出模板 → 200 + xlsx content-type."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/workpapers/test-wp/g7-sub/export-template",
                params={"sheet": "G7-8"},
            )
            assert resp.status_code == 200
            assert "spreadsheet" in resp.headers.get("content-type", "")
