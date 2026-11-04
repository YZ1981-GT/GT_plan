/**
 * 运行时基线 — 种子清单与库对得上；全局公式设置页如实提示「未接入计算」的公式域
 *
 * 其余用例的项目 / 底稿 id 都取自种子清单：清单和库对不上，后面的断言就不是针对种子数据了。所以先逐项核对：
 * 两个项目都在，名称、报表口径、年度与清单一致；清单里每个底稿编码在库里对应的底稿 id 与清单相等。
 * 界面：全局公式设置页打开「试算表科目明细公式」显示「目前只保存、不参与计算」，报表域不显示这条提示
 * （spec formula-management-repair-closure R3.1）。原用例打开不存在的 `/formula-management` 页面，只看标题非空。
 */
import { test, expect } from '@playwright/test'
import { api, apiToken, loginAndInstall } from './helpers'
import { loadManifest } from './manifest'

test.describe('种子清单与运行时', () => {
  for (const key of ['standalone', 'consolidated'] as const) {
    test(`${key === 'standalone' ? '单体' : '合并'}项目：项目与底稿和种子清单一致`, async ({ request }) => {
      const token = await apiToken(request)
      const manifest = loadManifest()
      const m = manifest[key]
      const p = await api(request, token, 'GET', `/api/projects/${m.project_id}`)
      expect(p.status, JSON.stringify(p.error)).toBe(200)
      expect(p.data.id).toBe(m.project_id)
      expect(p.data.name).toBe(m.project_name)
      expect(p.data.report_scope).toBe(key)
      expect(p.data.audit_year).toBe(manifest.year)

      const codes = Object.keys(m.wp_ids)
      expect(codes.length, '种子清单没有底稿').toBeGreaterThan(0)
      const wps = await api(request, token, 'GET', `/api/projects/${m.project_id}/working-papers`, {
        params: { page: 1, page_size: 100 },
      })
      expect(wps.status, JSON.stringify(wps.error)).toBe(200)
      const byCode = new Map((wps.data.items as any[]).map((w) => [w.wp_code, w.wp_id]))
      expect(Object.fromEntries(codes.map((c) => [c, byCode.get(c)]))).toEqual(m.wp_ids)
    })
  }

  test('全局公式设置：试算表科目明细提示未接入计算，报表域不提示', async ({ page, request }) => {
    await loginAndInstall(page, request)
    const domainsLoaded = () => page.waitForResponse(
      (r) => r.url().includes('/api/formula-settings/domains') && r.status() === 200, { timeout: 30_000 })

    let loaded = domainsLoaded()
    await page.goto('/settings/formula-global?domain=tb_detail')
    await expect(page).not.toHaveURL(/\/login/)
    await loaded
    await expect(page.getByTestId('fgs-not-wired')).toContainText('试算表科目明细公式目前只保存、不参与计算',
      { timeout: 20_000 })

    // 报表域已接入计算 ⇒ 不提示。先等域清单到达再判断「提示不存在」，否则在响应回来之前就会判定通过
    loaded = domainsLoaded()
    await page.goto('/settings/formula-global?domain=report')
    await loaded
    await expect(page.getByTestId('fgs-group')).toBeVisible({ timeout: 20_000 })
    await expect(page.getByTestId('fgs-not-wired')).toHaveCount(0)
  })
})
