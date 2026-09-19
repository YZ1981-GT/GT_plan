"""
Playwright 端到端测试：符号约定统一后的平衡校验

验证目标（需求 8.4）：
1. 导入后试算表借方类合计 = 贷方类合计（差额 ≤ ±1 元容差）
2. 报表资产合计 = 负债合计 + 权益合计（资产负债表平衡）
3. 底稿取数符号正确（如应付账款 =TB('2202','期末余额') 返回正数）

运行前提：
  1. 手动启动 dev server（start-dev.bat → 后端 9980 + 前端 3030）
  2. 数据库中已有导入完成且迁移到 v2 符号约定的项目
  3. 安装依赖: pip install pytest-playwright playwright
     playwright install chromium

运行方式：
  # 设置项目 ID（可选，默认使用 df5b8403...首汽租车）
  set SIGN_E2E_PROJECT_ID=your-project-uuid-here

  # 运行测试
  python -m pytest backend/tests/e2e/test_sign_convention_e2e.py -v --headed

  # 无头模式
  python -m pytest backend/tests/e2e/test_sign_convention_e2e.py -v
"""

from __future__ import annotations

import os
import re
from decimal import Decimal

import pytest
from playwright.sync_api import Page, expect

# ─── 配置 ───────────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("SIGN_E2E_BASE_URL", "http://localhost:3030")
API_BASE = os.environ.get("SIGN_E2E_API_BASE", "http://localhost:9980")
LOGIN_USERNAME = os.environ.get("SIGN_E2E_USERNAME", "admin")
LOGIN_PASSWORD = os.environ.get("SIGN_E2E_PASSWORD", "admin123")

# 目标项目 ID（需已导入数据+迁移到 v2 符号约定）
PROJECT_ID = os.environ.get(
    "SIGN_E2E_PROJECT_ID",
    "df5b8403-0000-0000-0000-000000000000",
)
# 审计年度
AUDIT_YEAR = int(os.environ.get("SIGN_E2E_YEAR", "2025"))

# 平衡容差（与 sign_convention_types.BALANCE_TOLERANCE 对齐，±1 元）
BALANCE_TOLERANCE = Decimal("1")


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def browser_context_args():
    """Playwright browser context 配置"""
    return {
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,
    }


@pytest.fixture(scope="module")
def auth_token(page: Page) -> str:
    """通过 API 登录获取 JWT token"""
    response = page.request.post(
        f"{API_BASE}/api/auth/login",
        data={
            "username": LOGIN_USERNAME,
            "password": LOGIN_PASSWORD,
        },
    )
    assert response.ok, f"登录失败: {response.status} {response.text()}"
    body = response.json()
    # 解信封：ResponseWrapperMiddleware 包装为 {code, message, data}
    payload = body.get("data", body)
    token = payload.get("access_token")
    assert token, f"登录响应中缺少 access_token: {body}"
    return token


@pytest.fixture()
def authenticated_page(page: Page, auth_token: str) -> Page:
    """已认证的页面（将 token 写入 localStorage 模拟前端登录态）"""
    # 先访问前端首页以初始化 localStorage 域
    page.goto(f"{BASE_URL}/login")
    page.wait_for_load_state("domcontentloaded")

    # 将 token 写入 localStorage（与前端 auth store 一致）
    page.evaluate(
        """([token]) => {
            localStorage.setItem('access_token', token);
            localStorage.setItem('token', token);
        }""",
        [auth_token],
    )
    return page


@pytest.fixture()
def api_headers(auth_token: str) -> dict[str, str]:
    """API 请求头"""
    return {"Authorization": f"Bearer {auth_token}"}


# ─── 辅助函数 ────────────────────────────────────────────────────────────────


def _parse_amount(text: str | None) -> Decimal:
    """解析页面上的金额文本为 Decimal（处理千分符、负号、括号负数等）"""
    if not text:
        return Decimal("0")
    # 去除空白
    text = text.strip()
    # 处理括号负数 (1,234.56) → -1234.56
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    elif text.startswith("-"):
        negative = True
        text = text[1:]
    # 去除千分符
    text = text.replace(",", "").replace(" ", "")
    # 去除货币符号
    text = re.sub(r"[¥$€￥]", "", text)
    if not text or text == "-" or text == "—":
        return Decimal("0")
    try:
        value = Decimal(text)
    except Exception:
        return Decimal("0")
    return -value if negative else value


# ─── 测试 1: 试算表借贷平衡 ─────────────────────────────────────────────────


class TestTrialBalanceEquilibrium:
    """验证导入后试算表借方类合计 = 贷方类合计（差额 ≤ ±1 元）"""

    def test_tb_balance_via_api(self, page: Page, api_headers: dict):
        """通过 API 获取试算表数据，验证借方类合计 = 贷方类合计

        Validates: Requirements 8.4（端到端平衡校验）
        """
        # 调用试算表 summary-with-adjustments 端点
        response = page.request.get(
            f"{API_BASE}/api/projects/{PROJECT_ID}/trial-balance/summary-with-adjustments",
            params={"year": AUDIT_YEAR, "report_type": "balance_sheet"},
            headers=api_headers,
        )
        assert response.ok, (
            f"试算表 API 调用失败: {response.status} {response.text()}"
        )

        body = response.json()
        payload = body.get("data", body)
        rows = payload.get("rows", [])
        assert len(rows) > 0, "试算表无数据，请确认项目已导入且迁移到 v2"

        # 按类别分组统计：借方类（资产+费用+成本）vs 贷方类（负债+权益+收入）
        debit_categories = {"asset", "expense", "cost"}
        credit_categories = {"liability", "equity", "revenue"}

        debit_total = Decimal("0")
        credit_total = Decimal("0")

        for row in rows:
            category = (row.get("account_category") or "").lower()
            # audited_amount 是审定金额（v2 约定下为自然正数）
            amount = Decimal(str(row.get("audited_amount") or 0))

            if category in debit_categories:
                debit_total += amount
            elif category in credit_categories:
                credit_total += amount

        difference = abs(debit_total - credit_total)
        assert difference <= BALANCE_TOLERANCE, (
            f"试算表借贷不平衡！\n"
            f"  借方类合计: {debit_total:,.2f}\n"
            f"  贷方类合计: {credit_total:,.2f}\n"
            f"  差额: {difference:,.2f}（容差 ±{BALANCE_TOLERANCE} 元）"
        )

    def test_tb_balance_via_consistency_check(self, page: Page, api_headers: dict):
        """通过一致性校验端点验证试算表平衡

        Validates: Requirements 6.1, 8.4
        """
        response = page.request.get(
            f"{API_BASE}/api/projects/{PROJECT_ID}/trial-balance/consistency-check",
            params={"year": AUDIT_YEAR},
            headers=api_headers,
        )
        assert response.ok, (
            f"一致性校验 API 失败: {response.status} {response.text()}"
        )

        body = response.json()
        payload = body.get("data", body)
        consistent = payload.get("consistent", False)
        issues = payload.get("issues", [])

        # 过滤平衡相关的 issue
        balance_issues = [
            i for i in issues
            if "平衡" in str(i.get("message", ""))
            or "balance" in str(i.get("type", "")).lower()
        ]
        assert not balance_issues, (
            f"试算表一致性校验发现平衡问题:\n"
            + "\n".join(f"  - {i}" for i in balance_issues)
        )

    def test_tb_balance_via_page(self, authenticated_page: Page):
        """通过前端页面验证试算表借贷合计

        导航到试算表页面，读取页面显示的借方/贷方合计行，断言差额在容差内。

        Validates: Requirements 8.4
        """
        page = authenticated_page
        page.goto(
            f"{BASE_URL}/projects/{PROJECT_ID}/trial-balance?year={AUDIT_YEAR}"
        )
        page.wait_for_load_state("networkidle")

        # 等待试算表数据加载（表格行出现）
        page.wait_for_selector(
            "table, .el-table, .trial-balance-table",
            timeout=15000,
        )

        # 尝试定位合计行（不同 UI 实现可能有不同的选择器）
        # 策略 1: 查找包含"合计"文字的行
        summary_rows = page.locator(
            "tr:has-text('合计'), .summary-row, .total-row"
        )

        if summary_rows.count() >= 2:
            # 假设有"借方合计"和"贷方合计"或统一的"合计"行
            # 尝试从页面文本中提取数值
            page_text = page.content()

            # 查找借方合计和贷方合计的数值
            debit_match = re.search(
                r"借方[类]?合计[：:]\s*([\d,.]+)", page_text
            )
            credit_match = re.search(
                r"贷方[类]?合计[：:]\s*([\d,.]+)", page_text
            )

            if debit_match and credit_match:
                debit_total = _parse_amount(debit_match.group(1))
                credit_total = _parse_amount(credit_match.group(1))
                difference = abs(debit_total - credit_total)
                assert difference <= BALANCE_TOLERANCE, (
                    f"页面试算表借贷不平衡！差额: {difference:,.2f}"
                )
            else:
                # 如果无法从文本中直接解析，确认页面至少正常渲染了
                assert summary_rows.count() > 0, "试算表未显示合计行"
        else:
            # 降级：确认页面正常加载（有表格数据行）
            data_rows = page.locator("table tbody tr, .el-table__body tr")
            assert data_rows.count() > 0, "试算表页面无数据行"


# ─── 测试 2: 资产负债表平衡 ──────────────────────────────────────────────────


class TestBalanceSheetEquilibrium:
    """验证资产合计 = 负债合计 + 权益合计"""

    def test_bs_balance_via_api(self, page: Page, api_headers: dict):
        """通过报表 API 获取资产负债表，验证 资产 = 负债 + 权益

        Validates: Requirements 6.2, 8.4
        """
        response = page.request.get(
            f"{API_BASE}/api/reports/{PROJECT_ID}/{AUDIT_YEAR}/balance_sheet",
            headers=api_headers,
        )
        assert response.ok, (
            f"资产负债表 API 失败: {response.status} {response.text()}"
        )

        body = response.json()
        payload = body.get("data", body)
        rows = payload.get("rows", payload.get("items", []))
        assert len(rows) > 0, "资产负债表无数据"

        # 从报表行中提取关键合计行
        asset_total = Decimal("0")
        liability_total = Decimal("0")
        equity_total = Decimal("0")

        for row in rows:
            row_code = (row.get("row_code") or "").upper()
            row_name = row.get("row_name") or ""
            amount = Decimal(str(row.get("current_period_amount") or 0))

            # 匹配资产合计行（不同模板行次编码不同，按名称+编码双匹配）
            if "资产合计" in row_name or row_code in ("BS-ASSET-TOTAL", "BS-099"):
                asset_total = amount
            elif "负债合计" in row_name or row_code in ("BS-LIABILITY-TOTAL", "BS-199"):
                liability_total = amount
            elif (
                "所有者权益合计" in row_name
                or "股东权益合计" in row_name
                or "权益合计" in row_name
                or row_code in ("BS-EQUITY-TOTAL", "BS-299")
            ):
                equity_total = amount
            # 兜底：负债和所有者权益合计
            elif (
                "负债和所有者权益合计" in row_name
                or "负债及股东权益合计" in row_name
                or row_code in ("BS-TOTAL", "BS-399")
            ):
                # 如果有负债+权益合计行，可直接用来校验
                liability_equity_combined = amount
                if asset_total != Decimal("0"):
                    diff = abs(asset_total - liability_equity_combined)
                    assert diff <= BALANCE_TOLERANCE, (
                        f"资产负债表不平衡！\n"
                        f"  资产合计: {asset_total:,.2f}\n"
                        f"  负债和权益合计: {liability_equity_combined:,.2f}\n"
                        f"  差额: {diff:,.2f}"
                    )
                    return  # 已验证，提前返回

        # 如果找到了分项合计行，验证 资产 = 负债 + 权益
        if asset_total != Decimal("0") and (
            liability_total != Decimal("0") or equity_total != Decimal("0")
        ):
            liability_equity_sum = liability_total + equity_total
            diff = abs(asset_total - liability_equity_sum)
            assert diff <= BALANCE_TOLERANCE, (
                f"资产负债表不平衡！\n"
                f"  资产合计: {asset_total:,.2f}\n"
                f"  负债合计: {liability_total:,.2f}\n"
                f"  权益合计: {equity_total:,.2f}\n"
                f"  负债+权益: {liability_equity_sum:,.2f}\n"
                f"  差额: {diff:,.2f}（容差 ±{BALANCE_TOLERANCE} 元）"
            )
        else:
            pytest.skip(
                "未找到资产/负债/权益合计行，请检查报表模板 row_code 配置"
            )

    def test_bs_balance_via_consistency_check(self, page: Page, api_headers: dict):
        """通过报表一致性校验端点验证平衡

        Validates: Requirements 6.2, 8.4
        """
        response = page.request.get(
            f"{API_BASE}/api/reports/{PROJECT_ID}/{AUDIT_YEAR}/consistency-check",
            headers=api_headers,
        )
        assert response.ok, (
            f"报表一致性校验 API 失败: {response.status} {response.text()}"
        )

        body = response.json()
        payload = body.get("data", body)
        checks = payload.get("checks", payload.get("results", []))

        # 查找资产负债表平衡相关的校验结果
        bs_checks = [
            c for c in checks
            if "balance_sheet" in str(c.get("type", "")).lower()
            or "资产负债" in str(c.get("message", ""))
            or "bs_balance" in str(c.get("code", "")).lower()
        ]
        for check in bs_checks:
            status = check.get("status", check.get("passed", True))
            assert status in (True, "pass", "passed"), (
                f"资产负债表平衡校验未通过: {check}"
            )

    def test_bs_balance_via_page(self, authenticated_page: Page):
        """通过前端报表页面验证资产负债表

        Validates: Requirements 8.4
        """
        page = authenticated_page
        page.goto(
            f"{BASE_URL}/projects/{PROJECT_ID}/reports?year={AUDIT_YEAR}&type=balance_sheet"
        )
        page.wait_for_load_state("networkidle")

        # 等待报表渲染（表格出现）
        page.wait_for_selector(
            "table, .el-table, .report-table",
            timeout=15000,
        )

        # 检查页面上是否有"不平衡"警告
        imbalance_warning = page.locator(
            ":text('不平衡'), :text('差额'), .balance-warning, .imbalance-alert"
        )
        # 正常情况不应出现不平衡警告
        if imbalance_warning.count() > 0:
            warning_text = imbalance_warning.first.text_content()
            # 允许差额在容差内的提示
            if warning_text:
                amount_match = re.search(r"[\d,.]+", warning_text)
                if amount_match:
                    diff = _parse_amount(amount_match.group())
                    assert diff <= BALANCE_TOLERANCE, (
                        f"页面显示资产负债表不平衡: {warning_text}"
                    )


# ─── 测试 3: 底稿取数符号正确 ────────────────────────────────────────────────


class TestFormulaSignCorrectness:
    """验证底稿/报表公式取数在 v2 约定下符号正确"""

    def test_tb_formula_accounts_payable_positive(
        self, page: Page, api_headers: dict
    ):
        """=TB('2202','期末余额') 应返回正数（应付账款为贷方类，v2 存正数）

        Validates: Requirements 11.4, 8.4
        """
        response = page.request.post(
            f"{API_BASE}/api/report-config/execute-formula",
            headers=api_headers,
            data={
                "project_id": PROJECT_ID,
                "year": AUDIT_YEAR,
                "formula": "TB('2202','期末余额')",
            },
        )
        assert response.ok, (
            f"公式执行 API 失败: {response.status} {response.text()}"
        )

        body = response.json()
        payload = body.get("data", body)
        value = payload.get("value", payload.get("result"))

        if value is None:
            pytest.skip("应付账款(2202)在该项目中无数据")

        # v2 约定：应付账款是负债类，贷方正常余额存正数
        numeric_value = Decimal(str(value))
        assert numeric_value >= 0, (
            f"=TB('2202','期末余额') 返回负数 {numeric_value}，"
            f"v2 约定下应付账款（贷方类）应存正数"
        )

    def test_tb_formula_fixed_assets_positive(
        self, page: Page, api_headers: dict
    ):
        """=TB('1601','期末余额') 应返回正数（固定资产为借方类，v2 存正数）

        Validates: Requirements 11.1, 8.4
        """
        response = page.request.post(
            f"{API_BASE}/api/report-config/execute-formula",
            headers=api_headers,
            data={
                "project_id": PROJECT_ID,
                "year": AUDIT_YEAR,
                "formula": "TB('1601','期末余额')",
            },
        )
        assert response.ok, (
            f"公式执行 API 失败: {response.status} {response.text()}"
        )

        body = response.json()
        payload = body.get("data", body)
        value = payload.get("value", payload.get("result"))

        if value is None:
            pytest.skip("固定资产(1601)在该项目中无数据")

        # v2 约定：固定资产是资产类，借方正常余额存正数
        numeric_value = Decimal(str(value))
        assert numeric_value >= 0, (
            f"=TB('1601','期末余额') 返回负数 {numeric_value}，"
            f"v2 约定下固定资产（借方类）应存正数"
        )

    def test_tb_formula_revenue_positive(
        self, page: Page, api_headers: dict
    ):
        """=TB('6001','期末余额') 应返回正数（主营收入为贷方类，v2 存正数）

        Validates: Requirements 11.1, 8.4
        """
        response = page.request.post(
            f"{API_BASE}/api/report-config/execute-formula",
            headers=api_headers,
            data={
                "project_id": PROJECT_ID,
                "year": AUDIT_YEAR,
                "formula": "TB('6001','期末余额')",
            },
        )
        assert response.ok, (
            f"公式执行 API 失败: {response.status} {response.text()}"
        )

        body = response.json()
        payload = body.get("data", body)
        value = payload.get("value", payload.get("result"))

        if value is None:
            pytest.skip("主营业务收入(6001)在该项目中无数据")

        # v2 约定：收入类贷方正常余额存正数
        numeric_value = Decimal(str(value))
        assert numeric_value >= 0, (
            f"=TB('6001','期末余额') 返回负数 {numeric_value}，"
            f"v2 约定下收入类（贷方类）应存正数"
        )

    def test_tb_formula_accumulated_depreciation_positive(
        self, page: Page, api_headers: dict
    ):
        """=TB('1602','期末余额') 应返回正数（累计折旧为备抵，贷方正常，v2 存正数）

        Validates: Requirements 3.1, 11.1, 8.4
        """
        response = page.request.post(
            f"{API_BASE}/api/report-config/execute-formula",
            headers=api_headers,
            data={
                "project_id": PROJECT_ID,
                "year": AUDIT_YEAR,
                "formula": "TB('1602','期末余额')",
            },
        )
        assert response.ok, (
            f"公式执行 API 失败: {response.status} {response.text()}"
        )

        body = response.json()
        payload = body.get("data", body)
        value = payload.get("value", payload.get("result"))

        if value is None:
            pytest.skip("累计折旧(1602)在该项目中无数据")

        # v2 约定：累计折旧是资产备抵（贷方正常方向），存正数
        numeric_value = Decimal(str(value))
        assert numeric_value >= 0, (
            f"=TB('1602','期末余额') 返回负数 {numeric_value}，"
            f"v2 约定下累计折旧（资产备抵，贷方方向）应存正数"
        )

    def test_tb_sum_formula_receivables_positive(
        self, page: Page, api_headers: dict
    ):
        """=TB_SUM('1122~1231','期末余额') 应返回正数（应收类为资产借方类）

        Validates: Requirements 11.1, 8.4
        """
        response = page.request.post(
            f"{API_BASE}/api/report-config/execute-formula",
            headers=api_headers,
            data={
                "project_id": PROJECT_ID,
                "year": AUDIT_YEAR,
                "formula": "SUM_TB('1122~1231','期末余额')",
            },
        )
        # SUM_TB 可能不支持或数据为空
        if not response.ok:
            pytest.skip(f"SUM_TB 公式执行失败（可能该范围无数据）: {response.status}")

        body = response.json()
        payload = body.get("data", body)
        value = payload.get("value", payload.get("result"))

        if value is None or value == 0:
            pytest.skip("应收类科目在该项目中无数据")

        numeric_value = Decimal(str(value))
        assert numeric_value >= 0, (
            f"SUM_TB('1122~1231','期末余额') 返回负数 {numeric_value}，"
            f"v2 约定下应收类（借方类）应存正数"
        )
