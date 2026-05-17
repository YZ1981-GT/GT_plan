/**
 * E2E — 循环级复核状态徽章验证
 * 验证 WorkpaperWorkbench 底稿树中循环节点显示复核状态徽章
 *
 * Requirements: 6.5
 */
import { test, expect } from '@playwright/test'

const PROJECT_ID = '005a6f2d-cecd-4e30-bcbd-9fb01236c194'

test.describe('循环复核徽章', () => {
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

  test('底稿树显示循环节点和复核徽章', async ({ page }) => {
    test.setTimeout(30_000)

    await page.goto(`/projects/${PROJECT_ID}/workpapers`)

    // Wait for the workpaper tree to load
    await page.waitForSelector('.el-tree, [class*="tree"]', { timeout: 15_000 })

    // Verify cycle nodes exist (D 收入循环)
    const cycleNode = page.locator('text=/D.*收入/')
    await expect(cycleNode.first()).toBeVisible({ timeout: 10_000 })

    // Verify badge text contains review status indicators
    const pageText = await page.textContent('body')
    const hasBadge =
      pageText?.includes('已复核') || pageText?.includes('待复核')
    expect(hasBadge).toBeTruthy()
  })
})
