/**
 * 浏览器检查 ① — 中央调试 / 报表试算失败原因
 *
 * 公式调试（`POST /api/formula/debug`）对算不出的公式要给可读原因、不给数；算得出的给值。
 * 原用例打的是不存在的 `/api/projects/{pid}/formula-management/debug`，404 时只断言「不是 500」⇒ 恒绿。
 *
 * formula-e2e-ci-gate Task 2 / R3 第 1 项；spec formula-management-repair-closure R7 重写
 */
import { test, expect } from '@playwright/test'
import { api, apiToken, loginAndInstall, seedYear, standaloneProjectId } from './helpers'

test.describe('中央调试失败原因', () => {
  let token = ''
  test.beforeAll(async ({ request }) => { token = await apiToken(request) })

  test('1/0：不给数，原因写明除数为 0', async ({ request }) => {
    const r = await api(request, token, 'POST', '/api/formula/debug', {
      data: { formula: '1/0', project_id: standaloneProjectId(), year: seedYear(), scope: 'report' },
    })
    expect(r.status).toBe(200)
    expect(r.data.ok).toBe(false)
    expect(r.data.value).toBeNull()
    expect(r.data.errors.join('；')).toContain('除数为 0')
  })

  test('2*3：算得出就给值', async ({ request }) => {
    const r = await api(request, token, 'POST', '/api/formula/debug', {
      data: { formula: '2*3', project_id: standaloneProjectId(), year: seedYear(), scope: 'report' },
    })
    expect(r.status).toBe(200)
    expect(r.data.ok).toBe(true)
    expect(Number(r.data.value)).toBe(6)
    expect(r.data.errors).toEqual([])
  })

  test('报表配置页可打开', async ({ page, request }) => {
    await loginAndInstall(page, request)
    await page.goto(`/projects/${standaloneProjectId()}/report-config`)
    await expect(page).not.toHaveURL(/\/login/)
    await expect(page.getByText('报表配置', { exact: true }).first()).toBeVisible({ timeout: 20_000 })
  })
})
