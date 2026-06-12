/**
 * UAT — 坏账准备明细表 D2-3 嵌套编辑器 Playwright 实测
 *
 * 锚定 spec workpaper-bad-debt-nested-structure Task 11.3
 *
 * 验证：
 * 1. D2 底稿 → 切换到「坏账准备明细表D2-3」sheet → 渲染 GtBadDebtSheet
 * 2. 展开/折叠父行子行
 * 3. 工具栏新增计提类别 + 右键新增/删除子行
 * 4. bad-debt-rows API 命中 200（非 404/307）
 *
 * 项目：辽宁卫生服务有限公司 2025（37814426-a29e-4fc2-9313-a59d229bf7b0）
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

const PROJECT_ID = '37814426-a29e-4fc2-9313-a59d229bf7b0'
const D2_3_SHEET_PATTERN = /坏账准备明细表D2-3|D2-3/

async function loginAs(page: Page, username: string, password: string) {
  const resp = await page.request.post('/api/auth/login', {
    data: { username, password },
  })
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
  return token as string
}

async function findD2WpId(request: APIRequestContext, token: string): Promise<string | null> {
  const resp = await request.get(`/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])
  const d2 = list.find((w: { wp_code?: string }) => (w.wp_code || '').toUpperCase() === 'D2')
  return d2?.id || null
}

async function waitEditorReady(page: Page) {
  await page.waitForSelector('.gt-wp-editor, .gt-wp-editor-loading', { timeout: 15_000 })
  await page.waitForTimeout(3_000)
  const overlay = page.locator('.gt-loading-overlay')
  if (await overlay.count() > 0) {
    await expect(overlay).toBeHidden({ timeout: 20_000 })
  }
}

async function openD2_3Sheet(page: Page) {
  // D 循环编辑器用顶部 tab 切换 sheet（非 Univer 左侧 gt-usn）
  const tab = page.getByRole('tab', { name: D2_3_SHEET_PATTERN })
  await expect(tab, '顶部 tab 应存在 D2-3 sheet').toBeVisible({ timeout: 10_000 })
  await tab.click()
  await page.waitForTimeout(1_500)
}

async function confirmDialog(page: Page, inputText?: string) {
  const box = page.locator('.el-message-box').last()
  await expect(box).toBeVisible({ timeout: 8_000 })
  if (inputText !== undefined) {
    await box.locator('input').fill(inputText)
  }
  const primary = box.locator('.el-message-box__btns .el-button--primary')
  await expect(primary).toBeVisible({ timeout: 3_000 })
  await primary.click()
}

async function seedParentRow(request: APIRequestContext, token: string, wpId: string) {
  const resp = await request.post(`/api/workpapers/${wpId}/bad-debt-rows/parents`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { provision_method: 'INDIVIDUAL', row_label: '按单项评估计提' },
  })
  expect(resp.ok(), `seed parent 应 201/200，实际 ${resp.status()}`).toBeTruthy()
  const body = await resp.json()
  return body?.data?.id ?? body?.id
}

test.describe('坏账准备明细表 D2-3（Task 11.3）', () => {
  test('11.3 — 层级渲染 + 展折 + 右键增删子行 + API 联通', async ({ page, request }) => {
    test.setTimeout(120_000)

    const apiCalls: { url: string; status: number }[] = []
    page.on('response', (resp) => {
      const url = resp.url()
      if (url.includes('/bad-debt-rows')) {
        apiCalls.push({ url, status: resp.status() })
      }
    })

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (/\/ai\//.test(text) && /405/.test(text)) return
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        consoleErrors.push(text)
      }
    })
    page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`))

    const token = await loginAs(page, 'admin', 'admin123')
    const wpId = await findD2WpId(request, token)
    test.skip(!wpId, '辽宁卫生项目无 D2 底稿')

    // 预清理 + 种子父行（API 层，保证 UI 可重复跑）
    const treeResp = await request.get(`/api/workpapers/${wpId}/bad-debt-rows`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(treeResp.ok(), 'bad-debt-rows GET 应 200').toBeTruthy()
    const treeBody = await treeResp.json()
    const parents = treeBody?.data?.parents ?? treeBody?.parents ?? []
    for (const p of parents) {
      for (const c of p.children ?? []) {
        await request.delete(`/api/workpapers/${wpId}/bad-debt-rows/${c.id}`, {
          headers: { Authorization: `Bearer ${token}` },
        })
      }
      await request.delete(`/api/workpapers/${wpId}/bad-debt-rows/${p.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
    }
    await seedParentRow(request, token, wpId)

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await waitEditorReady(page)

    await openD2_3Sheet(page)

    const badDebt = page.locator('.gt-bad-debt-sheet')
    await expect(badDebt, '应渲染 GtBadDebtSheet 组件').toBeVisible({ timeout: 10_000 })
    await expect(badDebt.locator('.gbds-title')).toHaveText('坏账准备明细表 D2-3')

    const parentRow = badDebt.locator('tr.gbds-parent').first()
    await expect(parentRow).toBeVisible({ timeout: 8_000 })

    // 展开/折叠
    const toggle = parentRow.locator('.gbds-toggle')
    await expect(toggle).toHaveText('▼')
    await toggle.click()
    await expect(toggle).toHaveText('▶')
    await toggle.click()
    await expect(toggle).toHaveText('▼')

    // 右键新增子行
    await parentRow.click({ button: 'right' })
    const menu = badDebt.locator('.gbds-menu')
    await expect(menu).toBeVisible({ timeout: 3_000 })
    await menu.locator('li').filter({ hasText: '新增子行' }).click()
    await confirmDialog(page, 'Playwright测试子行')
    await page.waitForTimeout(1_500)

    const childRow = badDebt.locator('tr.gbds-child').filter({ hasText: 'Playwright测试子行' })
    await expect(childRow).toBeVisible({ timeout: 8_000 })

    // 合计行应存在
    await expect(badDebt.locator('tr.gbds-summary')).toBeVisible()

    // 右键删除子行
    await childRow.click({ button: 'right' })
    await expect(menu).toBeVisible({ timeout: 3_000 })
    await menu.locator('li.gbds-menu-danger').click()
    await confirmDialog(page)
    await page.waitForTimeout(1_500)
    await expect(childRow).toHaveCount(0, { timeout: 8_000 })

    // API 联通：至少有一次 GET tree 200，且无 404
    const getCalls = apiCalls.filter((c) => c.url.includes('/bad-debt-rows') && !c.url.includes('/provision-methods'))
    expect(getCalls.length, '应发起 bad-debt-rows API 请求').toBeGreaterThan(0)
    const badStatuses = apiCalls.filter((c) => c.status === 404 || c.status === 307)
    expect(badStatuses, `不应有 404/307:\n${JSON.stringify(badStatuses)}`).toHaveLength(0)
    expect(apiCalls.every((c) => c.status >= 200 && c.status < 300 || c.status === 409),
      `bad-debt API 状态异常:\n${JSON.stringify(apiCalls)}`).toBeTruthy()

    const critical = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|bad-debt|404/.test(e),
    )
    expect(critical, `控制台严重错误:\n${critical.join('\n')}`).toHaveLength(0)
  })
})
