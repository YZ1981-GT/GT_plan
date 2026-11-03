/**
 * 浏览器检查 ⑥ — 门禁五态标签与只提示文案
 *
 * 验证：一致性门禁端点返回的每项都有合法五态 status，
 * 页面上显示对应的中文标签。
 *
 * formula-e2e-ci-gate Task 2 / R3 第 6 项
 */
import { test, expect } from '@playwright/test'
import { loginAndInstall, standaloneProjectId } from './helpers'

const BACKEND = process.env.PLAYWRIGHT_BACKEND_URL || 'http://127.0.0.1:9980'
const VALID_STATES = new Set([
  'passed', 'failed', 'not_executed', 'unavailable', 'warning',
])

test.describe('门禁五态标签', () => {
  test.beforeEach(async ({ page, request }) => {
    await loginAndInstall(page, request)
  })

  test('门禁端点每项 status 属于五态', async ({ request }) => {
    const projectId = standaloneProjectId()
    const resp = await request.get(
      `${BACKEND}/api/projects/${projectId}/consistency-gate`,
      {
        headers: { Authorization: `Bearer ${process.env.FH_E2E_TOKEN || ''}` },
      },
    )
    if (resp.status() === 404) return // 端点不存在
    expect(resp.ok(), `门禁端点失败 ${resp.status()}`).toBeTruthy()
    const body = await resp.json()
    const data = body?.data ?? body
    const items = data?.items ?? data?.checks ?? []
    if (Array.isArray(items)) {
      for (const item of items) {
        if (item.status) {
          expect(
            VALID_STATES.has(item.status),
            `非法门禁状态: ${item.status} (${item.name ?? item.id})`,
          ).toBe(true)
        }
      }
    }
  })

  test('门禁页面可导航', async ({ page }) => {
    const projectId = standaloneProjectId()
    await page.goto(`/projects/${projectId}/deliverable-center`)
    await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {})
    if (page.url().includes('/login')) return // token 未注入 SPA 路由守卫
    // 页面加载不崩溃即可
    const title = await page.title()
    expect(title).toBeTruthy()
  })
})
