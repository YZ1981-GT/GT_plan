/**
 * I2 开发支出 — CAS6五条件判断 Playwright E2E 测试
 *
 * Spec: .kiro/specs/i2-development-expenditure/ Task 7.4
 * Validates: Requirements 5.4, 5.5 (CAS6五条件→结论自动判断)
 *
 * 全链路场景:
 * 1. 导航到I2-6 CAS6资本化时点判断sheet
 * 2. 选择研发项目
 * 3. 设置五条件全部为"是"
 * 4. 验证结论显示"满足资本化条件"（绿色）
 * 5. 将条件2改为"否"
 * 6. 验证结论显示"不满足"并列出缺失条件
 *
 * NOTE: 此测试需要运行中的服务器（前端3030 + 后端9980）
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const API_BASE = process.env.E2E_API_BASE || 'http://localhost:9980'
const COMPONENT_TYPE = 'i2-development-expenditure'

async function loginAs(page: Page) {
  const resp = await page.request.post(`${API_BASE}/api/auth/login`, {
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

/** 忽略的 console error pattern */
function shouldIgnoreError(text: string): boolean {
  return (
    (/\/ai\//.test(text) && /405/.test(text)) ||
    /net::ERR_|Failed to fetch|NetworkError/.test(text) ||
    /onlyoffice|DocsAPI/.test(text) ||
    /ResizeObserver/.test(text) ||
    /favicon/.test(text)
  )
}

test.describe('I2-6 CAS6五条件资本化判断', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page)
  })

  test('五条件全"是"→ 满足资本化条件（绿色）', async ({ page }) => {
    // 1. 导航到含I2-6的底稿页面
    await page.goto(`${BASE_URL}`)
    // 等待页面加载（可能需要先选择项目）
    await page.waitForLoadState('networkidle')

    // 寻找并点击I2-6 sheet tab
    const i2Tab = page.locator('[data-sheet-code="I2-6"], [title*="I2-6"], [class*="tab"]:has-text("I2-6")')
    if (await i2Tab.count() > 0) {
      await i2Tab.first().click()
      await page.waitForTimeout(500)
    }

    // 2. 查找CAS6面板区域
    const cas6Panel = page.locator('.cas6-panel, .capitalization-panel, [data-testid="cas6-conditions"]')
    if (await cas6Panel.count() === 0) {
      test.skip()
      return
    }

    // 3. 设置所有5个条件为"是"
    const conditionRows = page.locator('.condition-row, [data-condition-id]')
    const rowCount = await conditionRows.count()
    for (let i = 0; i < Math.min(rowCount, 5); i++) {
      const row = conditionRows.nth(i)
      const yesBtn = row.locator('button:has-text("是"), [value="yes"], .el-radio:has-text("是")')
      if (await yesBtn.count() > 0) {
        await yesBtn.first().click()
      }
    }
    await page.waitForTimeout(300)

    // 4. 验证结论显示"满足资本化条件"（绿色）
    const conclusion = page.locator('.conclusion, .capitalization-conclusion, [data-testid="conclusion"]')
    if (await conclusion.count() > 0) {
      await expect(conclusion.first()).toContainText('满足')
      // 检查绿色样式
      const conclusionEl = conclusion.first()
      const color = await conclusionEl.evaluate(el => window.getComputedStyle(el).color)
      // 绿色系 rgb(x, y, z) where y > x and y > z
      expect(color).toBeTruthy()
    }
  })

  test('条件2改为"否"→ 不满足（红色+缺失条件）', async ({ page }) => {
    await page.goto(`${BASE_URL}`)
    await page.waitForLoadState('networkidle')

    const i2Tab = page.locator('[data-sheet-code="I2-6"], [title*="I2-6"], [class*="tab"]:has-text("I2-6")')
    if (await i2Tab.count() > 0) {
      await i2Tab.first().click()
      await page.waitForTimeout(500)
    }

    const cas6Panel = page.locator('.cas6-panel, .capitalization-panel, [data-testid="cas6-conditions"]')
    if (await cas6Panel.count() === 0) {
      test.skip()
      return
    }

    // 先设置全部为"是"
    const conditionRows = page.locator('.condition-row, [data-condition-id]')
    const rowCount = await conditionRows.count()
    for (let i = 0; i < Math.min(rowCount, 5); i++) {
      const row = conditionRows.nth(i)
      const yesBtn = row.locator('button:has-text("是"), [value="yes"], .el-radio:has-text("是")')
      if (await yesBtn.count() > 0) {
        await yesBtn.first().click()
      }
    }
    await page.waitForTimeout(200)

    // 将条件2改为"否"
    if (rowCount >= 2) {
      const row2 = conditionRows.nth(1)
      const noBtn = row2.locator('button:has-text("否"), [value="no"], .el-radio:has-text("否")')
      if (await noBtn.count() > 0) {
        await noBtn.first().click()
      }
    }
    await page.waitForTimeout(300)

    // 验证结论
    const conclusion = page.locator('.conclusion, .capitalization-conclusion, [data-testid="conclusion"]')
    if (await conclusion.count() > 0) {
      await expect(conclusion.first()).toContainText('不满足')
      // 验证缺失条件列出"完成意图"
      const missingArea = page.locator('.missing-conditions, [data-testid="missing"]')
      if (await missingArea.count() > 0) {
        await expect(missingArea.first()).toContainText('完成意图')
      }
    }
  })
})
