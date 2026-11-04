/**
 * 底稿编辑器与公式入口 — 打开的就是清单里的那份底稿，公式入口恰好一个且可用
 *
 * 接口：`GET /api/workpapers/{wp_id}/render-config` 返回的底稿 id / 编码 / 所属项目与种子清单一致；
 * 两个项目的同编码底稿各归各的项目（id 不串）。
 * 界面：编辑器 `/projects/{pid}/workpapers/{wp_id}/edit` 标题栏显示底稿编码与返回按钮，公式管理入口
 * （`formula-manager-open`，ADR-FMC-03「恰一个入口」）只有一个且可点；底稿短链 `/workpapers/{wp_id}`
 * 跳到同一个编辑器地址。原用例打开不存在的 `/projects/{pid}/workpapers/{wp_id}`，只看标题非空；
 * 接口部分只断言「不是 500」。
 */
import { test, expect } from '@playwright/test'
import { api, apiToken, loginAndInstall } from './helpers'
import { loadManifest } from './manifest'

const WP_CODE = 'D2-1'

test.describe('底稿编辑器与公式入口', () => {
  test('渲染配置：底稿 id、编码、所属项目与清单一致，两个项目不串', async ({ request }) => {
    const token = await apiToken(request)
    const manifest = loadManifest()
    for (const key of ['standalone', 'consolidated'] as const) {
      const m = manifest[key]
      const wpId = m.wp_ids[WP_CODE]
      expect(wpId, `种子清单 ${key} 缺 ${WP_CODE}`).toBeTruthy()
      const r = await api(request, token, 'GET', `/api/workpapers/${wpId}/render-config`)
      expect(r.status, `${key}：${JSON.stringify(r.error)}`).toBe(200)
      expect(r.data.wp_id).toBe(wpId)
      expect(r.data.wp_code).toBe(WP_CODE)
      expect(r.data.project_id).toBe(m.project_id)
      expect(Array.isArray(r.data.sheets)).toBe(true)
    }
    expect(manifest.standalone.wp_ids[WP_CODE]).not.toBe(manifest.consolidated.wp_ids[WP_CODE])
  })

  test('编辑器：标题栏是这份底稿，公式管理入口恰好一个且可点', async ({ page, request }) => {
    await loginAndInstall(page, request)
    const m = loadManifest().standalone
    await page.goto(`/projects/${m.project_id}/workpapers/${m.wp_ids[WP_CODE]}/edit`)
    await expect(page).not.toHaveURL(/\/login/)
    await expect(page.locator('.gt-wp-editor-code')).toHaveText(WP_CODE, { timeout: 30_000 })
    // 标题栏有底稿名称（不依赖返回按钮：它的文案与 testid 不在已提交代码里）
    await expect(page.locator('.gt-wp-editor-name')).toHaveText(/\S/)
    const entry = page.getByTestId('formula-manager-open')
    await expect(entry).toHaveCount(1, { timeout: 30_000 })
    await expect(entry).toBeEnabled({ timeout: 30_000 })
  })

  test('底稿短链：跳到所属项目的编辑器', async ({ page, request }) => {
    await loginAndInstall(page, request)
    const m = loadManifest().standalone
    const wpId = m.wp_ids[WP_CODE]
    await page.goto(`/workpapers/${wpId}`)
    await expect(page).toHaveURL(new RegExp(`/projects/${m.project_id}/workpapers/${wpId}/edit`), { timeout: 30_000 })
    await expect(page.locator('.gt-wp-editor-code')).toHaveText(WP_CODE, { timeout: 30_000 })
  })
})
