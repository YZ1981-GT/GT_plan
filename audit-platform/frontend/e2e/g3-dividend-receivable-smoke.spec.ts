/**
 * G3 应收股利 — Playwright 冒烟
 *
 * 验证 HTML 分表壳子可打开（G3-1 / G3-2），并露出关键工具栏文案。
 * 完整 1131 往返依赖真实项目试算数据，默认用环境变量覆盖项目路由。
 *
 * 环境：
 *   E2E_BASE_URL      默认 http://localhost:3030
 *   E2E_PROJECT_ID    含 G3 底稿的项目 ID
 *   E2E_G3_WP_CODE    默认 G3-1（可改 G3-2）
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || ''
const G3_SHEET = process.env.E2E_G3_WP_CODE || 'G3-1'

test.describe('G3 应收股利冒烟', () => {
  test.skip(!PROJECT_ID, '未设置 E2E_PROJECT_ID，跳过 G3 UI 冒烟（请用含 G3 底稿的真实项目）')

  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 15000 }).catch(() => undefined)
  })

  test('G3-1 审定表 HTML 壳与汇总按钮可见', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/${G3_SHEET}`)
    await page.waitForTimeout(2500)

    const root = page.locator(
      '.g3-adjudication, .g3-dividend-receivable, [class*="g3-"], .workpaper-container',
    )
    await expect(root.first()).toBeVisible({ timeout: 20000 })

    const body = (await page.textContent('body')) || ''
    const looksLikeG3 =
      body.includes('应收股利')
      || body.includes('G3-1')
      || body.includes('从 G3-2 汇总')
      || body.includes('取试算')
      || body.includes('被投资方')
    expect(looksLikeG3).toBe(true)
  })

  test('G3-2 明细表区段切换或表头可见', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G3-2`)
    await page.waitForTimeout(2500)

    const root = page.locator(
      '.g3-detail, .g3-dividend-receivable, [class*="g3-"], .workpaper-container',
    )
    await expect(root.first()).toBeVisible({ timeout: 20000 })

    const body = (await page.textContent('body')) || ''
    const looksLikeDetail =
      body.includes('被投资方')
      || body.includes('持股')
      || body.includes('分红')
      || body.includes('应收')
      || body.includes('G3-2')
    expect(looksLikeDetail).toBe(true)
  })
})
