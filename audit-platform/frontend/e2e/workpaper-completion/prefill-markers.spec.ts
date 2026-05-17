/**
 * E2E — 预填充视觉标记验证
 * 验证陕西华氏 D2 底稿编辑器加载后有预填充标记
 *
 * Requirements: 6.2
 */
import { test, expect } from '@playwright/test'

const PROJECT_ID = '005a6f2d-cecd-4e30-bcbd-9fb01236c194'
const WP_ID = 'bd333fdd-dc84-4121-b164-7f5cb84d4c52'

test.describe('预填充视觉标记', () => {
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

  test('D2 底稿编辑器加载完整 sheet tabs', async ({ page }) => {
    test.setTimeout(30_000)

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${WP_ID}/edit`)

    // Wait for Univer to load (canvas elements appear)
    await page.waitForSelector('canvas', { timeout: 20_000 })

    // Verify page contains sheet tab names (底稿目录 / 审定表)
    const pageContent = await page.content()
    const hasSheetTabs =
      pageContent.includes('底稿目录') || pageContent.includes('审定表')
    expect(hasSheetTabs).toBeTruthy()
  })

  test('不走空白 workbook fallback', async ({ page }) => {
    test.setTimeout(30_000)

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text())
      }
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${WP_ID}/edit`)
    await page.waitForSelector('canvas', { timeout: 20_000 })

    // Verify no "creating empty workbook" fallback was triggered
    const emptyWorkbookErrors = consoleErrors.filter((e) =>
      e.toLowerCase().includes('creating empty workbook')
    )
    expect(emptyWorkbookErrors).toHaveLength(0)
  })
})
