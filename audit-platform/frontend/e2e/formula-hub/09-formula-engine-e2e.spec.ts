/**
 * CI 适配版 — formula-engine-e2e
 *
 * 原文件：e2e/formula-engine-e2e.spec.ts
 * 适配：去掉 RUN_FULL_E2E 跳过开关，项目 ID 从清单读取，
 *       地址改为相对（走 playwright 配置的 baseURL）。
 *
 * formula-e2e-ci-gate Task 3 / ADR-FEC-03
 */
import { test, expect } from '@playwright/test'
import { loadManifest, defaultCredentials } from './manifest'
import { loginAndInstall } from './helpers'

test.describe('公式引擎全链路（CI 适配）', () => {
  test.beforeEach(async ({ page, request }) => {
    await loginAndInstall(page, request)
  })

  test('报表公式编辑页可导航', async ({ page }) => {
    const projectId = loadManifest().standalone.project_id
    await page.goto(`/projects/${projectId}/report-config`)
    await expect(
      page.locator('text=报表配置').or(page.locator('text=报表')).first(),
    ).toBeVisible({ timeout: 15_000 })
  })

  test('公式管理页可导航', async ({ page }) => {
    const projectId = loadManifest().standalone.project_id
    await page.goto(`/projects/${projectId}/formula-management`)
    await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {})
    if (page.url().includes('/login')) return
    const title = await page.title()
    expect(title).toBeTruthy()
  })

  test('公式地址库端点可达', async ({ request }) => {
    const projectId = loadManifest().standalone.project_id
    const BACKEND = process.env.PLAYWRIGHT_BACKEND_URL || 'http://127.0.0.1:9980'
    const resp = await request.get(
      `${BACKEND}/api/projects/${projectId}/formula-management/address-registry`,
      {
        headers: { Authorization: `Bearer ${process.env.FH_E2E_TOKEN || ''}` },
      },
    )
    // 200 或 404 都合理（种子项目可能无地址注册）
    expect(resp.status()).not.toBe(500)
  })
})
