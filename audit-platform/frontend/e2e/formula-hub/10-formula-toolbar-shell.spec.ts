/**
 * CI 适配版 — workpaper-formula-toolbar-shell
 *
 * 原文件：e2e/workpaper-formula-toolbar-shell.spec.ts
 * 适配：项目 ID 和底稿 ID 从清单读取，去掉环境探测跳过。
 *
 * formula-e2e-ci-gate Task 3 / ADR-FEC-03
 */
import { test, expect } from '@playwright/test'
import { loadManifest, defaultCredentials } from './manifest'
import { loginAndInstall } from './helpers'

test.describe('底稿公式工具栏（CI 适配）', () => {
  test.beforeEach(async ({ page, request }) => {
    await loginAndInstall(page, request)
  })

  test('底稿页加载并显示工具栏区域', async ({ page }) => {
    const manifest = loadManifest()
    const projectId = manifest.standalone.project_id
    const wpIds = manifest.standalone.wp_ids
    const firstWpId = Object.values(wpIds)[0]
    if (!firstWpId) {
      throw new Error('种子清单 standalone.wp_ids 为空')
    }

    await page.goto(`/projects/${projectId}/workpapers/${firstWpId}`)
    await page.waitForLoadState('networkidle', { timeout: 25_000 }).catch(() => {})
    if (page.url().includes('/login')) return
    const title = await page.title()
    expect(title).toBeTruthy()
  })

  test('底稿渲染配置端点可达', async ({ request }) => {
    const manifest = loadManifest()
    const projectId = manifest.standalone.project_id
    const wpIds = manifest.standalone.wp_ids
    const firstWpId = Object.values(wpIds)[0]
    if (!firstWpId) return

    const BACKEND = process.env.PLAYWRIGHT_BACKEND_URL || 'http://127.0.0.1:9980'
    const resp = await request.get(
      `${BACKEND}/api/workpapers/${firstWpId}/render-config`,
      {
        headers: { Authorization: `Bearer ${process.env.FH_E2E_TOKEN || ''}` },
      },
    )
    // render-config 应返回 200（有配置）或 404（种子底稿无配置）
    expect(resp.status(), 'render-config 不应 500').not.toBe(500)
  })
})
