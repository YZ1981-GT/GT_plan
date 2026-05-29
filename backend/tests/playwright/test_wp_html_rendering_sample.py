"""
Playwright 抽样验证：每类（A/B/C/D/E/H）各选 2 个底稿打开确认 HTML 渲染正确

运行前提：
  1. 启动 dev server（start-dev.bat → 后端 9980 + 前端 3030）
  2. 数据库中有首汽租车_2025 项目（project_id=df5b8403...）且 is_deleted=false
  3. 底稿已通过 chain_orchestrator 生成

运行方式：
  python -m pytest backend/tests/playwright/test_wp_html_rendering_sample.py -v --headed

依赖：
  pip install pytest-playwright
  playwright install chromium
"""

import re

import pytest
from playwright.sync_api import Page, expect

# ─── 配置 ───────────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:3030"
LOGIN_USERNAME = "admin"
LOGIN_PASSWORD = "admin123"

# 首汽租车_2025 项目 ID（最完整的测试项目）
PROJECT_ID = "df5b8403-0000-0000-0000-000000000000"

# 每类抽样 2 个底稿的 wp_code
SAMPLE_WORKPAPERS = {
    "A": {
        "wp_codes": ["A1", "A3"],
        "description": ["一般程序表", "合并范围"],
        "css_selector": ".gt-a-program-console",
        "expected_elements": [
            ".gt-a-program-console__header",
            ".gt-a-program-console__table",
        ],
    },
    "B": {
        "wp_codes": ["B1", "B2A"],
        "description": ["底稿目录", "控制了解"],
        "css_selector": ".gt-b-index",
        "expected_elements": [
            ".gt-b-index__preparation",
            ".gt-b-index__navigation",
        ],
    },
    "C": {
        "wp_codes": ["C1", "C2"],
        "description": ["附注披露", "附注明细"],
        "css_selector": ".gt-c-note-table",
        "expected_elements": [
            ".gt-cnt__header",
        ],
    },
    "D": {
        "wp_codes": ["D2A", "D2-1"],
        "description": ["应收账款检查", "函证"],
        "css_selector": ".gt-d-form",
        "expected_elements": [
            # D 类有 5 种子模式，至少出现其中一种
            ".gt-d-form-table, .gt-d-form-conf, .gt-d-form-review, "
            ".gt-d-form-paragraph, .gt-d-form-qa",
        ],
    },
    "E": {
        "wp_codes": ["E1A", "E1"],
        "description": ["IT控制测试", "控制测试"],
        "css_selector": ".gt-e-control-test",
        "expected_elements": [
            ".gt-e__header",
        ],
    },
    "H": {
        "wp_codes": ["H1", "H2"],
        "description": ["辅助说明", "参考文档"],
        "css_selector": ".gt-h-static-doc",
        "expected_elements": [
            ".gt-h-static-doc__inner",
        ],
    },
}


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def browser_context_args():
    """Playwright browser context 配置"""
    return {
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,
    }


@pytest.fixture()
def authenticated_page(page: Page):
    """
    每个测试函数获取已认证的 page。
    pytest-playwright 自动提供 page fixture（含 browser context）。
    """
    _login(page)
    return page


def _login(page: Page):
    """执行登录流程，获取 token 并写入 localStorage"""
    page.goto(f"{BASE_URL}/login")
    page.wait_for_load_state("networkidle")

    # 填写登录表单
    page.fill('input[placeholder*="用户名"], input[name="username"]', LOGIN_USERNAME)
    page.fill('input[placeholder*="密码"], input[name="password"], input[type="password"]', LOGIN_PASSWORD)

    # 点击登录按钮
    page.click('button[type="submit"], button:has-text("登录")')

    # 等待登录成功（跳转到首页或 dashboard）
    page.wait_for_url(re.compile(r"/(dashboard|projects|home)"), timeout=15000)


def _navigate_to_workpaper(page: Page, project_id: str, wp_code: str):
    """
    导航到指定底稿编辑器页面。

    策略：
    1. 先通过 API 查询 wp_code 对应的 wp_id
    2. 直接导航到编辑器 URL
    """
    # 通过底稿列表页搜索 wp_code 获取 wp_id
    # 方案 A：直接用 API 查询（更可靠）
    response = page.request.get(
        f"{BASE_URL}/api/workpapers/search",
        params={"project_id": project_id, "wp_code": wp_code, "page_size": 1},
    )

    if response.ok:
        data = response.json()
        items = data.get("items") or data.get("data") or []
        if items:
            wp_id = items[0].get("id") or items[0].get("wp_id")
            if wp_id:
                page.goto(
                    f"{BASE_URL}/projects/{project_id}/workpapers/{wp_id}/edit"
                )
                page.wait_for_load_state("networkidle")
                return True

    # 方案 B：通过全局搜索 API
    response = page.request.get(
        f"{BASE_URL}/api/global-search",
        params={"q": wp_code, "project_id": project_id, "type": "workpaper"},
    )

    if response.ok:
        data = response.json()
        results = data.get("results") or data.get("items") or data.get("data") or []
        for item in results:
            if item.get("wp_code", "").upper() == wp_code.upper():
                wp_id = item.get("id") or item.get("wp_id")
                if wp_id:
                    page.goto(
                        f"{BASE_URL}/projects/{project_id}/workpapers/{wp_id}/edit"
                    )
                    page.wait_for_load_state("networkidle")
                    return True

    # 方案 C：通过底稿列表页面 UI 搜索
    page.goto(f"{BASE_URL}/projects/{project_id}/workpapers")
    page.wait_for_load_state("networkidle")

    # 尝试在搜索框中输入 wp_code
    search_input = page.locator(
        'input[placeholder*="搜索"], input[placeholder*="底稿"], '
        'input[placeholder*="编号"]'
    ).first
    if search_input.is_visible(timeout=3000):
        search_input.fill(wp_code)
        page.wait_for_timeout(1000)  # 等待搜索结果

        # 点击匹配的底稿行
        row = page.locator(f'tr:has-text("{wp_code}"), .wp-item:has-text("{wp_code}")').first
        if row.is_visible(timeout=3000):
            row.click()
            page.wait_for_load_state("networkidle")
            return True

    return False


# ─── 测试用例 ────────────────────────────────────────────────────────────────


class TestAClassRendering:
    """A 类底稿 HTML 渲染验证（程序表中控台）"""

    @pytest.mark.parametrize(
        "wp_code,desc",
        list(zip(SAMPLE_WORKPAPERS["A"]["wp_codes"], SAMPLE_WORKPAPERS["A"]["description"])),
    )
    def test_a_class_renders_html(self, authenticated_page: Page, wp_code: str, desc: str):
        """验证 A 类底稿 {wp_code}（{desc}）渲染为 GtAProgramConsole"""
        page = authenticated_page
        navigated = _navigate_to_workpaper(page, PROJECT_ID, wp_code)
        assert navigated, f"无法导航到底稿 {wp_code}（{desc}）"

        # 等待页面渲染完成
        page.wait_for_timeout(2000)

        # 验证 HTML 组件渲染（非 Univer fallback）
        config = SAMPLE_WORKPAPERS["A"]
        component = page.locator(config["css_selector"])
        expect(component).to_be_visible(timeout=10000)

        # 验证关键子元素存在
        for selector in config["expected_elements"]:
            element = page.locator(selector)
            expect(element).to_be_visible(timeout=5000)

        # 确认没有 Univer fallback
        univer = page.locator(".univer-container, #univer-container, [data-univer]")
        expect(univer).not_to_be_visible(timeout=2000)


class TestBClassRendering:
    """B 类底稿 HTML 渲染验证（索引导航）"""

    @pytest.mark.parametrize(
        "wp_code,desc",
        list(zip(SAMPLE_WORKPAPERS["B"]["wp_codes"], SAMPLE_WORKPAPERS["B"]["description"])),
    )
    def test_b_class_renders_html(self, authenticated_page: Page, wp_code: str, desc: str):
        """验证 B 类底稿 {wp_code}（{desc}）渲染为 GtBIndex"""
        page = authenticated_page
        navigated = _navigate_to_workpaper(page, PROJECT_ID, wp_code)
        assert navigated, f"无法导航到底稿 {wp_code}（{desc}）"

        page.wait_for_timeout(2000)

        config = SAMPLE_WORKPAPERS["B"]
        component = page.locator(config["css_selector"])
        expect(component).to_be_visible(timeout=10000)

        for selector in config["expected_elements"]:
            element = page.locator(selector)
            expect(element).to_be_visible(timeout=5000)

        univer = page.locator(".univer-container, #univer-container, [data-univer]")
        expect(univer).not_to_be_visible(timeout=2000)


class TestCClassRendering:
    """C 类底稿 HTML 渲染验证（嵌套表）"""

    @pytest.mark.parametrize(
        "wp_code,desc",
        list(zip(SAMPLE_WORKPAPERS["C"]["wp_codes"], SAMPLE_WORKPAPERS["C"]["description"])),
    )
    def test_c_class_renders_html(self, authenticated_page: Page, wp_code: str, desc: str):
        """验证 C 类底稿 {wp_code}（{desc}）渲染为 GtCNoteTable"""
        page = authenticated_page
        navigated = _navigate_to_workpaper(page, PROJECT_ID, wp_code)
        assert navigated, f"无法导航到底稿 {wp_code}（{desc}）"

        page.wait_for_timeout(2000)

        config = SAMPLE_WORKPAPERS["C"]
        component = page.locator(config["css_selector"])
        expect(component).to_be_visible(timeout=10000)

        for selector in config["expected_elements"]:
            element = page.locator(selector)
            expect(element).to_be_visible(timeout=5000)

        univer = page.locator(".univer-container, #univer-container, [data-univer]")
        expect(univer).not_to_be_visible(timeout=2000)


class TestDClassRendering:
    """D 类底稿 HTML 渲染验证（表单型）"""

    @pytest.mark.parametrize(
        "wp_code,desc",
        list(zip(SAMPLE_WORKPAPERS["D"]["wp_codes"], SAMPLE_WORKPAPERS["D"]["description"])),
    )
    def test_d_class_renders_html(self, authenticated_page: Page, wp_code: str, desc: str):
        """验证 D 类底稿 {wp_code}（{desc}）渲染为 GtDForm"""
        page = authenticated_page
        navigated = _navigate_to_workpaper(page, PROJECT_ID, wp_code)
        assert navigated, f"无法导航到底稿 {wp_code}（{desc}）"

        page.wait_for_timeout(2000)

        config = SAMPLE_WORKPAPERS["D"]
        component = page.locator(config["css_selector"])
        expect(component).to_be_visible(timeout=10000)

        # D 类有 5 种子模式，验证至少出现其中一种
        sub_forms = page.locator(
            ".gt-d-form-table, .gt-d-form-conf, .gt-d-form-review, "
            ".gt-d-form-paragraph, .gt-d-form-qa"
        )
        expect(sub_forms.first).to_be_visible(timeout=5000)

        univer = page.locator(".univer-container, #univer-container, [data-univer]")
        expect(univer).not_to_be_visible(timeout=2000)


class TestEClassRendering:
    """E 类底稿 HTML 渲染验证（控制测试）"""

    @pytest.mark.parametrize(
        "wp_code,desc",
        list(zip(SAMPLE_WORKPAPERS["E"]["wp_codes"], SAMPLE_WORKPAPERS["E"]["description"])),
    )
    def test_e_class_renders_html(self, authenticated_page: Page, wp_code: str, desc: str):
        """验证 E 类底稿 {wp_code}（{desc}）渲染为 GtEControlTest"""
        page = authenticated_page
        navigated = _navigate_to_workpaper(page, PROJECT_ID, wp_code)
        assert navigated, f"无法导航到底稿 {wp_code}（{desc}）"

        page.wait_for_timeout(2000)

        config = SAMPLE_WORKPAPERS["E"]
        component = page.locator(config["css_selector"])
        expect(component).to_be_visible(timeout=10000)

        for selector in config["expected_elements"]:
            element = page.locator(selector)
            expect(element).to_be_visible(timeout=5000)

        univer = page.locator(".univer-container, #univer-container, [data-univer]")
        expect(univer).not_to_be_visible(timeout=2000)


class TestHClassRendering:
    """H 类底稿 HTML 渲染验证（静态文档）"""

    @pytest.mark.parametrize(
        "wp_code,desc",
        list(zip(SAMPLE_WORKPAPERS["H"]["wp_codes"], SAMPLE_WORKPAPERS["H"]["description"])),
    )
    def test_h_class_renders_html(self, authenticated_page: Page, wp_code: str, desc: str):
        """验证 H 类底稿 {wp_code}（{desc}）渲染为 GtHStaticDoc"""
        page = authenticated_page
        navigated = _navigate_to_workpaper(page, PROJECT_ID, wp_code)
        assert navigated, f"无法导航到底稿 {wp_code}（{desc}）"

        page.wait_for_timeout(2000)

        config = SAMPLE_WORKPAPERS["H"]
        component = page.locator(config["css_selector"])
        expect(component).to_be_visible(timeout=10000)

        for selector in config["expected_elements"]:
            element = page.locator(selector)
            expect(element).to_be_visible(timeout=5000)

        univer = page.locator(".univer-container, #univer-container, [data-univer]")
        expect(univer).not_to_be_visible(timeout=2000)


# ─── 综合验证 ────────────────────────────────────────────────────────────────


class TestNoUniverFallback:
    """验证所有 HTML 类底稿不会 fallback 到 Univer"""

    @pytest.mark.parametrize(
        "class_code,wp_code",
        [
            (cls, wp)
            for cls, cfg in SAMPLE_WORKPAPERS.items()
            for wp in cfg["wp_codes"]
        ],
    )
    def test_no_univer_fallback(self, authenticated_page: Page, class_code: str, wp_code: str):
        """验证 {class_code} 类底稿 {wp_code} 不使用 Univer 渲染"""
        page = authenticated_page
        navigated = _navigate_to_workpaper(page, PROJECT_ID, wp_code)
        if not navigated:
            pytest.skip(f"无法导航到底稿 {wp_code}，可能项目中不存在")

        page.wait_for_timeout(2000)

        # 对应类的 HTML 组件应该可见
        config = SAMPLE_WORKPAPERS[class_code]
        component = page.locator(config["css_selector"])

        # 如果 HTML 组件不可见，检查是否 fallback 到了 Univer
        if not component.is_visible(timeout=5000):
            univer = page.locator(
                ".univer-container, #univer-container, [data-univer]"
            )
            assert not univer.is_visible(), (
                f"底稿 {wp_code}（{class_code} 类）错误地 fallback 到 Univer 渲染！"
                f"应使用 HTML 组件 {config['css_selector']}"
            )
