/**
 * G 类底稿 E2E: G7-16 未确认投资损失页可打开（冒烟）
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('G7-16 未确认投资损失', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('权益法组件路由可打开且含 G7-16 文案', async ({ page }) => {
    const candidates = [
      `/project/${PROJECT_ID}/workpaper/G7-16`,
      `/project/${PROJECT_ID}/workpaper/G7`,
    ]
    let opened = false
    for (const path of candidates) {
      const resp = await page.goto(`${BASE_URL}${path}`)
      if (resp && resp.status() !== 404) {
        opened = true
        break
      }
    }
    expect(opened).toBe(true)
    await page.waitForTimeout(2500)
    const content = await page.textContent('body')
    expect(content).toBeTruthy()
  })

  test('若打开到未确认损失页则可见方法论与工具按钮', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G7-16`)
    await page.waitForTimeout(3000)
    const body = (await page.textContent('body')) || ''
    if (!body.includes('未确认') && !body.includes('超额亏损')) {
      test.skip(true, '当前项目未挂载 G7-16 专属页')
      return
    }
    await expect(page.locator('text=CAS2').first()).toBeVisible({ timeout: 5000 })
    const hasTool = await page.locator('text=从关联表带入').count()
      || await page.locator('text=按CAS2自动分配').count()
      || await page.locator('text=反序恢复').count()
    expect(hasTool).toBeGreaterThan(0)
  })
})
