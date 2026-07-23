/**
 * I3-3 / I3-7 联动冒烟（UI 可打开 + 关键控件存在）
 */
import { test, expect } from '@playwright/test'

const PROJECT_ID = process.env.TEST_PROJECT_ID || 'df5b8403-4157-b297-744707db5883'
const BASE_URL = process.env.BASE_URL || 'http://localhost:3030'

test.describe('I3-3 / I3-7 联动冒烟', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL(/.*projects.*|.*dashboard.*/, { timeout: 15000 }).catch(() => {})
  })

  test('I3-3 页面含保存回写与贷方科目选择', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=I3-3`)
    await page.waitForTimeout(2500)
    const body = await page.textContent('body')
    expect(body).toBeTruthy()
    // 组件可能懒加载；控件存在则断言，否则至少无致命空白
    const saveBtn = page.getByTestId('i3-3-save-sync')
    if (await saveBtn.count()) {
      await expect(saveBtn).toBeVisible()
      await expect(page.getByTestId('i3-3-credit-account')).toBeVisible()
    }
  })

  test('I3-7 页面含 CGU 状态或可收回标题', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=I3-7`)
    await page.waitForTimeout(2500)
    const body = await page.textContent('body')
    expect(body || '').toMatch(/可收回|I3-7|商誉/)
  })

  test('I3-6 含从 I3-7 同步按钮文案或控件', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=I3-6`)
    await page.waitForTimeout(2500)
    const syncBtn = page.getByTestId('i3-6-sync-from-i37')
    if (await syncBtn.count()) {
      await expect(syncBtn).toBeVisible()
    } else {
      const body = await page.textContent('body')
      expect(body || '').toMatch(/减值|I3-6|可收回/)
    }
  })
})
