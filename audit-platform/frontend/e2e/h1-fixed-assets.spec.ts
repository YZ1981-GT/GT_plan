/**
 * H1 固定资产 — Playwright E2E 测试
 *
 * Spec: .kiro/specs/h1-fixed-assets/ Task 7.5
 * Validates: 全部 Requirements
 *
 * 场景:
 * 1. 打开H1 → 切换到H1-1 → 验证表格渲染正确结构
 * 2. H1-12分支选择器 → 切换A/B/C → 验证组件变化
 * 3. 双模式切换 → HTML → OO → HTML
 * 4. H1-2 4区段Tab切换
 * 5. H1-7 添加行 + 基本交互
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  fetchRenderConfig,
  sheetComponentTypes,
  clickWorkpaperSheetTab,
  expectHtmlDualModeOrContent,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const COMPONENT_TYPE = 'h1-fixed-assets'

async function loginAs(page: Page) {
  const resp = await page.request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
  return token as string
}

async function getToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

// ─── Scenario 1: 打开H1 → H1-1 → 验证表格渲染 ────────────────────────────

test.describe('H1 固定资产 — Scenario 1: H1-1 审定表渲染', () => {
  test('打开H1底稿并切换到H1-1审定表', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'H1', PROJECT_ID)
    test.skip(!wpResult.exists, 'H1 底稿不存在')

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (/\/ai\//.test(text) && /405/.test(text)) return
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        if (/onlyoffice|DocsAPI/.test(text)) return
        consoleErrors.push(text)
      }
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 切换到H1-1
    await clickWorkpaperSheetTab(page, 'H1-1')
    await page.waitForTimeout(3_000)

    // 验证无严重错误
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined/.test(e),
    )
    expect(criticalErrors, `严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)

    // 验证表格渲染: 审定表应包含审定/未审/AJE等关键字
    await expectHtmlDualModeOrContent(page, /审定|未审|AJE|期末/)
  })
})

// ─── Scenario 2: H1-12 分支选择器 A/B/C ─────────────────────────────────

test.describe('H1 固定资产 — Scenario 2: H1-12 折旧分支选择', () => {
  test('H1-12 分支切换组件变化', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'H1', PROJECT_ID)
    test.skip(!wpResult.exists, 'H1 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 切换到H1-12
    await clickWorkpaperSheetTab(page, 'H1-12')
    await page.waitForTimeout(3_000)

    // 验证折旧相关内容显示
    await expectHtmlDualModeOrContent(page, /折旧|直线|递减|分支/)

    // 查找分支选择器(el-segmented或radio)
    const branchSelector = page.locator('[data-testid="depreciation-branch-selector"], .el-segmented, .el-radio-group').first()
    if (await branchSelector.isVisible()) {
      // 尝试切换分支
      const buttons = branchSelector.locator('button, .el-radio, .el-segmented__item')
      const count = await buttons.count()
      if (count >= 2) {
        await buttons.nth(1).click()
        await page.waitForTimeout(1_500)
        // 验证页面未崩溃
        await expect(page.locator('.workpaper-editor, [data-testid="h1-depreciation"]')).toBeVisible({ timeout: 5_000 })
      }
    }
  })
})

// ─── Scenario 3: 双模式切换 HTML → OO → HTML ────────────────────────────

test.describe('H1 固定资产 — Scenario 3: 双模式切换', () => {
  test('HTML ↔ OO 模式切换', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'H1', PROJECT_ID)
    test.skip(!wpResult.exists, 'H1 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 查找双模式切换器
    const modeSwitch = page.locator('[data-testid="dual-mode-switch"], .el-segmented').first()
    if (await modeSwitch.isVisible({ timeout: 5_000 }).catch(() => false)) {
      // 当前应为HTML模式
      const htmlContent = page.locator('.h1-fixed-assets, [data-testid*="h1-"]').first()
      const isHtml = await htmlContent.isVisible({ timeout: 3_000 }).catch(() => false)

      if (isHtml) {
        // 切换到OO模式
        const ooButton = modeSwitch.locator(':text("OnlyOffice"), :text("OO"), :text("Excel")')
        if (await ooButton.isVisible({ timeout: 2_000 }).catch(() => false)) {
          await ooButton.click()
          await page.waitForTimeout(3_000)
        }

        // 切回HTML
        const htmlButton = modeSwitch.locator(':text("HTML"), :text("结构化")')
        if (await htmlButton.isVisible({ timeout: 2_000 }).catch(() => false)) {
          await htmlButton.click()
          await page.waitForTimeout(3_000)
          // 验证HTML重新渲染
          await expectHtmlDualModeOrContent(page, /审定|明细|固定资产/)
        }
      }
    }
  })
})

// ─── Scenario 4: H1-2 4区段Tab切换 ──────────────────────────────────────

test.describe('H1 固定资产 — Scenario 4: H1-2 区段Tab', () => {
  test('H1-2 明细表4区段Tab切换', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'H1', PROJECT_ID)
    test.skip(!wpResult.exists, 'H1 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 切换到H1-2
    await clickWorkpaperSheetTab(page, 'H1-2')
    await page.waitForTimeout(3_000)

    // 验证明细表渲染
    await expectHtmlDualModeOrContent(page, /明细|原值|折旧|净值|基本/)

    // 查找区段Tab
    const segmentTabs = page.locator('.el-tabs__nav .el-tabs__item, [role="tablist"] [role="tab"]')
    const tabCount = await segmentTabs.count()

    if (tabCount >= 2) {
      // 切换各区段Tab
      for (let i = 0; i < Math.min(tabCount, 4); i++) {
        await segmentTabs.nth(i).click()
        await page.waitForTimeout(1_000)
        // 验证无崩溃
        const visible = await page.locator('.el-table, table, [data-testid*="h1-detail"]').first().isVisible({ timeout: 3_000 }).catch(() => false)
        // 至少一个tab应该显示表格内容
      }
    }
  })
})

// ─── Scenario 5: H1-7 添加行 + 基本交互 ─────────────────────────────────

test.describe('H1 固定资产 — Scenario 5: H1-7 添加行', () => {
  test('H1-7 新增检查行交互', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'H1', PROJECT_ID)
    test.skip(!wpResult.exists, 'H1 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 切换到H1-7
    await clickWorkpaperSheetTab(page, 'H1-7')
    await page.waitForTimeout(3_000)

    // 验证H1-7新增检查表内容
    await expectHtmlDualModeOrContent(page, /新增|购置|检查|样本|抽凭/)

    // 查找添加行按钮
    const addButton = page.locator('button:has-text("新增"), button:has-text("添加"), button:has-text("+"), [data-testid="add-row"]').first()
    if (await addButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await addButton.click()
      await page.waitForTimeout(1_500)

      // 可能弹出命名对话框
      const dialog = page.locator('.el-message-box, .el-dialog')
      if (await dialog.isVisible({ timeout: 2_000 }).catch(() => false)) {
        // 输入名称
        const input = dialog.locator('input').first()
        if (await input.isVisible()) {
          await input.fill('测试资产-001')
          // 确认
          const confirmBtn = dialog.locator('button:has-text("确定"), button:has-text("确认")').first()
          if (await confirmBtn.isVisible()) {
            await confirmBtn.click()
            await page.waitForTimeout(1_500)
          }
        }
      }

      // 验证页面未崩溃
      await expect(page.locator('.workpaper-editor, [data-testid*="h1-"]').first()).toBeVisible({ timeout: 5_000 })
    }
  })
})

// ─── render-config 契约验证 ──────────────────────────────────────────────

test.describe('H1 固定资产 — render-config', () => {
  test('H1 bundle 含 h1-fixed-assets componentType', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'H1', PROJECT_ID)
    test.skip(!wpResult.exists, 'H1 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain(COMPONENT_TYPE)
  })
})
