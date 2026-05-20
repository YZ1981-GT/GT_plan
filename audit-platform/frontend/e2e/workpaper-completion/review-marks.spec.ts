/**
 * E2E — 复核标记功能验证
 * 验证侧面板"复核标记"Tab 存在
 * (完整右键测试延后 — Univer canvas 右键交互复杂)
 *
 * Requirements: 6.4
 */
import { test, expect } from '@playwright/test'

const PROJECT_ID = '005a6f2d-cecd-4e30-bcbd-9fb01236c194'
const WP_ID = 'bd333fdd-dc84-4121-b164-7f5cb84d4c52'

test.describe('复核标记', () => {
  test.beforeEach(async ({ page }) => {
    // Login via API
    const resp = await page.request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    const body = await resp.json()
    const token = body.data?.access_token ?? body.access_token
    await page.addInitScript((t: string) => {
      window.sessionStorage.setItem('token', t)
      window.localStorage.setItem('token', t)
    }, token)
  })

  test('侧面板包含"复核标记"Tab', async ({ page }) => {
    test.setTimeout(30_000)

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${WP_ID}/edit`)

    // Wait for Univer canvas to load
    await page.waitForSelector('canvas', { timeout: 20_000 })

    // Open the side panel drawer (默认隐藏)
    const panelBtn = page.locator('button:has-text("面板")')
    await expect(panelBtn).toBeVisible({ timeout: 10_000 })
    await panelBtn.click()

    // Now drawer is open — verify the 复核标记 tab is rendered
    const reviewTab = page.locator('text=复核标记').first()
    await expect(reviewTab).toBeVisible({ timeout: 10_000 })
  })
})
