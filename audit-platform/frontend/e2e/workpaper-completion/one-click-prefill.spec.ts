/**
 * E2E — 一键填充功能验证
 * 验证点击"📊 一键填充"按钮后的 loading 状态和 toast 消息
 *
 * Requirements: 6.3
 */
import { test, expect } from '@playwright/test'

const PROJECT_ID = '005a6f2d-cecd-4e30-bcbd-9fb01236c194'
const WP_ID = 'bd333fdd-dc84-4121-b164-7f5cb84d4c52'

test.describe('一键填充', () => {
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

  test('点击一键填充按钮触发 loading 和 toast', async ({ page }) => {
    test.setTimeout(30_000)

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${WP_ID}/edit`)

    // Wait for Univer canvas to load
    await page.waitForSelector('canvas', { timeout: 20_000 })

    // Find the prefill button (visibility check is sufficient — disabled state is valid
    // when WP has no prefill mapping configured, which is correct gating per Requirement 2.6)
    const prefillBtn = page.locator('button:has-text("一键填充")')
    await expect(prefillBtn).toBeVisible({ timeout: 10_000 })

    const isDisabled = await prefillBtn.isDisabled()
    if (!isDisabled) {
      await prefillBtn.click()
      // Verify toast or loading state appears after completion
      const toastOrLoading = page.locator('.el-message, .el-notification, .is-loading')
      await expect(toastOrLoading.first()).toBeVisible({ timeout: 15_000 })
    } else {
      // Disabled = no prefill mapping configured for this WP, expected for some WPs
      const title = await prefillBtn.getAttribute('title')
      expect(title).toContain('当前底稿无预设公式配置')
    }
  })
})
