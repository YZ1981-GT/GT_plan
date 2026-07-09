"""L3 长期借款 — 集成测试：L3→L2/L8联动 + 征信核对 + 逾期 + 重分类.

Spec: .kiro/specs/l3-long-term-loans/ Task 7.2
Validates: Requirements 4.5-4.6, 5.1-5.4, 11.1-11.2

覆盖：
1. 利息测算API (POST /api/workpapers/{wp_id}/l3/calculate-interest)
2. 一年内到期重分类API (POST /api/workpapers/{wp_id}/l3/reclass-current-portion)
3. 导出模板 (GET /api/workpapers/{wp_id}/l3/export-template?sheet=L3-2)
4. 导入数据 (POST /api/workpapers/{wp_id}/l3/import-data?sheet=L3-2)
5. 征信核对 service
6. 逾期检查 service
7. 重分类 service
8. 负债类校验 service
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db
from app.services.l3_long_term_loans_service import (
    batch_calc_interest,
    batch_reclass,
    build_reclass_entry,
    calc_credit_diff,
    calc_current_portion,
    calc_interest,
    calc_overdue_days,
    check_credit_completeness,
    classify_overdue_risk,
    validate_liability_balance,
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
# 1. 利息测算API
# ═══════════════════════════════════════════════════════════════════════════════


class TestInterestCalcAPI:
    """POST /api/workpapers/{wp_id}/l3/calculate-interest"""

    @pytest.mark.asyncio
    async def test_multiple_loans_correct_interest(self):
        """多笔借款利息测算正确：利息=本金×年利率×天数/365."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/l3/calculate-interest",
                json={
                    "items": [
                        {
                            "contractNo": "HT-001",
                            "principal": 1000000.0,
                            "annualRate": 0.05,
                            "loanStart": "2025-01-01",
                            "loanEnd": "2025-07-01",
                        },
                        {
                            "contractNo": "HT-002",
                            "principal": 2000000.0,
                            "annualRate": 0.04,
                            "loanStart": "2025-03-01",
                            "loanEnd": "2025-06-01",
                        },
                    ],
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        data = body.get("data", body)

        assert data["count"] == 2
        items = data["items"]

        # HT-001: 181 days, interest = 1000000 * 0.05 * 181 / 365
        ht001 = next(i for i in items if i["contractNo"] == "HT-001")
        assert ht001["days"] == 181
        expected_1 = round(1000000 * 0.05 * 181 / 365, 2)
        assert abs(ht001["calculatedInterest"] - expected_1) < 0.01

        # HT-002: 92 days, interest = 2000000 * 0.04 * 92 / 365
        ht002 = next(i for i in items if i["contractNo"] == "HT-002")
        assert ht002["days"] == 92
        expected_2 = round(2000000 * 0.04 * 92 / 365, 2)
        assert abs(ht002["calculatedInterest"] - expected_2) < 0.01

    @pytest.mark.asyncio
    async def test_total_interest_sum_matches(self):
        """利息合计等于各笔利息之和."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/l3/calculate-interest",
                json={
                    "items": [
                        {
                            "contractNo": "A1",
                            "principal": 500000.0,
                            "annualRate": 0.06,
                            "loanStart": "2025-01-01",
                            "loanEnd": "2025-04-01",
                        },
                        {
                            "contractNo": "A2",
                            "principal": 800000.0,
                            "annualRate": 0.035,
                            "loanStart": "2025-02-01",
                            "loanEnd": "2025-05-01",
                        },
                    ],
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        data = body.get("data", body)
        total = sum(i["calculatedInterest"] for i in data["items"])
        assert abs(data["totalInterest"] - total) < 0.01

    @pytest.mark.asyncio
    async def test_zero_days_rate_produces_zero_interest(self):
        """零天数/零利率时利息为0."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/l3/calculate-interest",
                json={
                    "items": [
                        {
                            "contractNo": "ZERO-DAYS",
                            "principal": 1000000.0,
                            "annualRate": 0.05,
                            "loanStart": "2025-06-01",
                            "loanEnd": "2025-06-01",
                        },
                        {
                            "contractNo": "ZERO-RATE",
                            "principal": 1000000.0,
                            "annualRate": 0.0,
                            "loanStart": "2025-01-01",
                            "loanEnd": "2025-12-31",
                        },
                    ],
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        data = body.get("data", body)
        items = data["items"]

        zero_days = next(i for i in items if i["contractNo"] == "ZERO-DAYS")
        assert zero_days["calculatedInterest"] == 0.0
        assert zero_days["days"] == 0

        zero_rate = next(i for i in items if i["contractNo"] == "ZERO-RATE")
        assert zero_rate["calculatedInterest"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 一年内到期重分类API
# ═══════════════════════════════════════════════════════════════════════════════


class TestReclassCurrentPortionAPI:
    """POST /api/workpapers/{wp_id}/l3/reclass-current-portion"""

    @pytest.mark.asyncio
    async def test_due_within_one_year_full_reclass(self):
        """到期日在一年内 → currentPortion=full amount + reclassEntry present."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/l3/reclass-current-portion",
                json={
                    "dueDate": "2025-10-01",
                    "reportDate": "2025-01-01",
                    "amount": 5000000.0,
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        data = body.get("data", body)

        assert data["currentPortion"] == 5000000.0
        entry = data["reclassEntry"]
        assert entry is not None
        assert "2501" in entry["debit"]["account"]
        assert "2801" in entry["credit"]["account"]
        assert entry["debit"]["amount"] == 5000000.0
        assert entry["credit"]["amount"] == 5000000.0

    @pytest.mark.asyncio
    async def test_due_beyond_one_year_no_reclass(self):
        """到期日超过一年 → currentPortion=0, reclassEntry=null."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/l3/reclass-current-portion",
                json={
                    "dueDate": "2027-06-01",
                    "reportDate": "2025-01-01",
                    "amount": 3000000.0,
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        data = body.get("data", body)

        assert data["currentPortion"] == 0.0
        assert data["reclassEntry"] is None

    @pytest.mark.asyncio
    async def test_reclass_entry_structure_debit_2501_credit_2801(self):
        """重分类分录结构：debit含2501, credit含2801."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/l3/reclass-current-portion",
                json={
                    "dueDate": "2025-06-30",
                    "reportDate": "2025-01-01",
                    "amount": 1000000.0,
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        data = body.get("data", body)

        entry = data["reclassEntry"]
        assert entry["type"] == "RJE"
        assert "2501" in entry["debit"]["account"]
        assert "2801" in entry["credit"]["account"]
        assert entry["debit"]["amount"] == entry["credit"]["amount"] == 1000000.0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


class TestExportTemplateAPI:
    """GET /api/workpapers/{wp_id}/l3/export-template?sheet=L3-2"""

    @pytest.mark.asyncio
    async def test_returns_xlsx_content_type(self):
        """返回 application/vnd.openxmlformats xlsx content-type."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/workpapers/test-wp/l3/export-template?sheet=L3-2",
            )
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_has_content_disposition_with_filename(self):
        """Content-Disposition header 包含文件名."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/workpapers/test-wp/l3/export-template?sheet=L3-5",
            )
        assert resp.status_code == 200
        disposition = resp.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert "filename" in disposition


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


class TestImportDataAPI:
    """POST /api/workpapers/{wp_id}/l3/import-data?sheet=L3-2"""

    @pytest.mark.asyncio
    async def test_valid_xlsx_returns_imported_count(self, override_deps):
        """有效xlsx → imported_count."""
        import io
        from openpyxl import Workbook

        # 构造有效xlsx
        wb = Workbook()
        ws = wb.active
        ws.title = "L3-2"
        headers = [
            "借款银行", "借款合同号", "借款类型", "起始日", "到期日",
            "年利率", "币种", "期初余额", "本期借入", "本期归还",
            "期末余额", "一年内到期金额", "担保方式", "担保物", "备注",
        ]
        ws.append(headers)
        ws.append(["建设银行", "HT001", "信用", "2024-01-01", "2027-01-01",
                   0.045, "CNY", 5000000, 0, 500000, 4500000, 0, "信用", "", ""])

        # Mock execute to return None (no existing data)
        mock_result = AsyncMock()
        mock_result.fetchone.return_value = None
        override_deps.execute.return_value = mock_result

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/l3/import-data?sheet=L3-2",
                files={"file": ("test.xlsx", buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert resp.status_code == 200
        body = resp.json()
        data = body.get("data", body)
        assert data["imported_count"] == 1

    @pytest.mark.asyncio
    async def test_invalid_sheet_returns_400(self):
        """不支持的sheet → 400错误."""
        import io
        from openpyxl import Workbook

        wb = Workbook()
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/l3/import-data?sheet=L3-INVALID",
                files={"file": ("test.xlsx", buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 征信核对 service
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreditCheckService:
    """征信核对纯函数."""

    def test_calc_credit_diff_positive(self):
        """征信差异 = 征信余额 - 账面余额（正数=账面少计）."""
        diff = calc_credit_diff(5000000.0, 4800000.0)
        assert diff == 200000.0

    def test_calc_credit_diff_negative(self):
        """负差异=征信偏低."""
        diff = calc_credit_diff(4500000.0, 5000000.0)
        assert diff == -500000.0

    def test_calc_credit_diff_zero(self):
        """无差异."""
        diff = calc_credit_diff(3000000.0, 3000000.0)
        assert diff == 0.0

    def test_check_credit_completeness_threshold_normal(self):
        """差异在阈值内 → is_consistent=True."""
        result = check_credit_completeness(1000000.0, 1000000.0, threshold=100.0)
        assert result["is_consistent"] is True
        assert result["risk_level"] == "normal"
        assert result["difference"] == 0.0

    def test_check_credit_completeness_within_threshold(self):
        """差异在阈值边界内 → attention."""
        result = check_credit_completeness(1000050.0, 1000000.0, threshold=100.0)
        assert result["is_consistent"] is True
        assert result["risk_level"] == "attention"
        assert result["difference"] == 50.0

    def test_check_credit_completeness_exceeds_threshold(self):
        """差异超阈值 → warning + is_consistent=False."""
        result = check_credit_completeness(1500000.0, 1000000.0, threshold=100000.0)
        assert result["is_consistent"] is False
        assert result["risk_level"] == "warning"
        assert result["difference"] == 500000.0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 逾期检查 service
# ═══════════════════════════════════════════════════════════════════════════════


class TestOverdueCheckService:
    """逾期检查纯函数."""

    def test_calc_overdue_days_positive_is_overdue(self):
        """报告日>到期日 → 正数=逾期."""
        days = calc_overdue_days(date(2025, 1, 1), date(2025, 4, 1))
        assert days == 90

    def test_calc_overdue_days_zero_is_not_overdue(self):
        """报告日=到期日 → 0天=刚到期."""
        days = calc_overdue_days(date(2025, 6, 1), date(2025, 6, 1))
        assert days == 0

    def test_calc_overdue_days_negative_is_not_due(self):
        """报告日<到期日 → 负数=未到期."""
        days = calc_overdue_days(date(2025, 12, 31), date(2025, 6, 1))
        assert days < 0

    def test_classify_overdue_risk_normal(self):
        """未逾期 → normal."""
        assert classify_overdue_risk(0) == "normal"
        assert classify_overdue_risk(-10) == "normal"

    def test_classify_overdue_risk_attention(self):
        """1-30天 → attention."""
        assert classify_overdue_risk(1) == "attention"
        assert classify_overdue_risk(30) == "attention"

    def test_classify_overdue_risk_warning(self):
        """31-90天 → warning."""
        assert classify_overdue_risk(31) == "warning"
        assert classify_overdue_risk(90) == "warning"

    def test_classify_overdue_risk_danger(self):
        """>90天 → danger."""
        assert classify_overdue_risk(91) == "danger"
        assert classify_overdue_risk(365) == "danger"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. 重分类 service
# ═══════════════════════════════════════════════════════════════════════════════


class TestReclassService:
    """一年内到期重分类纯函数."""

    def test_calc_current_portion_due_within_year(self):
        """到期日在一年内 → 全额重分类."""
        portion = calc_current_portion(
            due_date=date(2025, 10, 1),
            report_date=date(2025, 1, 1),
            amount=5000000.0,
        )
        assert portion == 5000000.0

    def test_calc_current_portion_due_exactly_one_year(self):
        """到期日恰好等于报告日+1年 → 全额重分类（边界: <=）."""
        portion = calc_current_portion(
            due_date=date(2026, 1, 1),
            report_date=date(2025, 1, 1),
            amount=3000000.0,
        )
        assert portion == 3000000.0

    def test_calc_current_portion_due_beyond_year(self):
        """到期日超过一年 → 0（不重分类）."""
        portion = calc_current_portion(
            due_date=date(2027, 6, 1),
            report_date=date(2025, 1, 1),
            amount=2000000.0,
        )
        assert portion == 0.0

    def test_build_reclass_entry_positive_amount(self):
        """currentPortion>0 → 生成RJE分录."""
        entry = build_reclass_entry(1000000.0)
        assert entry is not None
        assert entry["type"] == "RJE"
        assert entry["debit"]["account"] == "2501"
        assert entry["credit"]["account"] == "2801"
        assert entry["debit"]["amount"] == 1000000.0
        assert entry["credit"]["amount"] == 1000000.0

    def test_build_reclass_entry_zero_returns_none(self):
        """currentPortion=0 → 无需重分类."""
        entry = build_reclass_entry(0.0)
        assert entry is None

    def test_build_reclass_entry_negative_returns_none(self):
        """currentPortion<0 → None."""
        entry = build_reclass_entry(-100.0)
        assert entry is None

    def test_batch_reclass_multiple_loans(self):
        """批量重分类：多笔借款混合到期."""
        loans = [
            {"contract_no": "A1", "due_date": date(2025, 6, 1), "amount": 1000000.0},
            {"contract_no": "A2", "due_date": date(2027, 12, 31), "amount": 2000000.0},
            {"contract_no": "A3", "due_date": date(2025, 12, 31), "amount": 500000.0},
        ]
        result = batch_reclass(loans, report_date=date(2025, 1, 1))

        assert len(result["details"]) == 3
        # A1 一年内到期
        a1 = next(d for d in result["details"] if d["contract_no"] == "A1")
        assert a1["is_current"] is True
        assert a1["current_portion"] == 1000000.0
        # A2 超过一年
        a2 = next(d for d in result["details"] if d["contract_no"] == "A2")
        assert a2["is_current"] is False
        assert a2["current_portion"] == 0.0
        # A3 一年内到期
        a3 = next(d for d in result["details"] if d["contract_no"] == "A3")
        assert a3["is_current"] is True
        assert a3["current_portion"] == 500000.0

        # 合计
        assert result["total_current_portion"] == 1500000.0
        # 合并重分类分录存在
        assert result["reclass_entry"] is not None
        assert result["reclass_entry"]["debit"]["amount"] == 1500000.0


# ═══════════════════════════════════════════════════════════════════════════════
# 8. 负债类校验 service
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateLiabilityBalance:
    """负债类期末余额校验：期末=期初+贷方-借方."""

    def test_expected_calculation(self):
        """期末 = 期初 + 贷方 - 借方."""
        result = validate_liability_balance(
            begin=10000000.0, credit=5000000.0, debit=2000000.0
        )
        assert result["expected"] == 13000000.0

    def test_with_reported_end_valid(self):
        """reported_end匹配 → is_valid=True."""
        result = validate_liability_balance(
            begin=10000000.0, credit=3000000.0, debit=1000000.0,
            reported_end=12000000.0
        )
        assert result["expected"] == 12000000.0
        assert result["is_valid"] is True
        assert result["difference"] == 0.0

    def test_with_reported_end_invalid(self):
        """reported_end不匹配 → is_valid=False."""
        result = validate_liability_balance(
            begin=10000000.0, credit=3000000.0, debit=1000000.0,
            reported_end=11000000.0  # 实际应为12000000
        )
        assert result["expected"] == 12000000.0
        assert result["is_valid"] is False
        assert result["difference"] == -1000000.0

    def test_within_tolerance(self):
        """差异在容差范围内 → is_valid=True."""
        result = validate_liability_balance(
            begin=10000000.0, credit=3000000.0, debit=1000000.0,
            reported_end=12000000.005,  # 0.005差异 < 0.01容差
            tolerance=0.01
        )
        assert result["is_valid"] is True

    def test_zero_movements(self):
        """无贷方无借方 → 期末=期初."""
        result = validate_liability_balance(begin=5000000.0, credit=0.0, debit=0.0)
        assert result["expected"] == 5000000.0
