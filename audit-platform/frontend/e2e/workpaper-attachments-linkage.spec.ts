/**
 * workpaper-attachments-linkage.spec.ts — Wave 7 Task 8.2
 *
 * spec: attachment-workpaper-linkage-convergence
 * 验证：多来源列表 / 空态 / 缺证据提示 / stale 提示 / 解除关联 round-trip（create→verify→cleanup）
 *
 * 无数据时：route mock 验空态与提示逻辑；有 FIX-B 项目时跑真实 unlink round-trip。
 * 依赖：dev server（前端代理 /api）+ 可登录；不可用时 skip（不 fabricate）。
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { TEST_PROJECT_ID, findWorkpaper } from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const WP_CODE_CANDIDATES = (process.env.ATTACHMENT_WP_E2E_CODE || 'E1,F2-1,D4,B1')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean)

async function loginAs(page: Page, username: string, password: string) {
  const resp = await page.request.post('/api/auth/login', {
    data: { username, password },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  if (!token) return null
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
  return token as string
}

async function getToken(request: APIRequestContext): Promise<string | null> {
  try {
    const resp = await request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    if (!resp.ok()) return null
    const body = await resp.json()
    return body.data?.access_token ?? body.access_token ?? null
  } catch {
    return null
  }
}

async function findFirstWorkpaper(
  request: APIRequestContext,
  token: string,
  codes: string[],
  projectId: string,
): Promise<{ exists: boolean; wpId?: string; wpCode?: string }> {
  for (const code of codes) {
    const wp = await findWorkpaper(request, token, code, projectId)
    if (wp.exists) return { exists: true, wpId: wp.wpId, wpCode: code }
  }
  return { exists: false }
}

async function openAttachmentsDrawer(page: Page) {
  const btn = page.getByRole('button', { name: /关联附件/ })
  await expect(btn.first()).toBeVisible({ timeout: 30_000 })
  await btn.first().click()
  await expect(page.getByText(/本底稿关联附件/)).toBeVisible({ timeout: 15_000 })
}

test.describe('底稿关联附件抽屉 — Wave 7', () => {
  test('空态 + mock 多来源 / 缺证据 / stale 提示', async ({ page, request }) => {
    test.setTimeout(90_000)
    const token = await getToken(request)
    test.skip(!token, '无法登录，跳过 Playwright（环境未就绪）')

    const wp = await findFirstWorkpaper(request, token!, WP_CODE_CANDIDATES, PROJECT_ID)
    test.skip(!wp.exists, `候选底稿均不存在: ${WP_CODE_CANDIDATES.join(',')}`)

    await loginAs(page, 'admin', 'admin123')

    // 先空态
    await page.route(`**/api/working-papers/${wp.wpId}/attachments`, async (route) => {
      if (route.request().method() !== 'GET') return route.continue()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [] }),
      })
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp.wpId}/edit`)
    await page.waitForTimeout(3_000)
    await openAttachmentsDrawer(page)
    await expect(page.getByText('本底稿暂无关联附件')).toBeVisible({ timeout: 10_000 })

    // 关闭后改 mock：多来源 + 缺证据 + stale
    await page.getByRole('button', { name: /关闭|Close/i }).first().click({ timeout: 5_000 }).catch(() => {})
    // drawer 可能用遮罩关闭
    await page.keyboard.press('Escape')

    await page.unroute(`**/api/working-papers/${wp.wpId}/attachments`)
    await page.route(`**/api/working-papers/${wp.wpId}/attachments`, async (route) => {
      if (route.request().method() !== 'GET') return route.continue()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: '11111111-1111-1111-1111-111111111111',
              file_name: '银行对账单.pdf',
              file_type: 'pdf',
              source: 'associated',
              sources: ['associated', 'referenced'],
              association_type: 'evidence',
            },
            {
              id: '22222222-2222-2222-2222-222222222222',
              file_name: '函证回函.pdf',
              file_type: 'pdf',
              source: 'confirmation',
              sources: ['confirmation'],
              association_type: null,
            },
          ],
          evidence_requirements: [
            { type: 'bank_statement', label: '银行对账单', satisfied: true },
            { type: 'confirmation', label: '银行询证函回函', satisfied: false },
          ],
          stale_info: {
            has_stale: true,
            level: 'definite',
            project_id: PROJECT_ID,
            items: [{ reason: 'ref_inactive', label: '失效引用-A' }],
          },
        }),
      })
    })

    await openAttachmentsDrawer(page)
    await expect(page.locator('.wp-att-source-tag').first()).toBeVisible({ timeout: 10_000 })
    await expect(page.getByTestId('evidence-requirements')).toBeVisible()
    await expect(page.getByText(/缺「银行询证函回函」证据/)).toBeVisible()
    await expect(page.getByTestId('stale-info')).toBeVisible()
    await expect(page.getByText(/明确失效的证据引用/)).toBeVisible()
  })

  test('解除关联 round-trip（create→verify→cleanup）', async ({ page, request }) => {
    test.setTimeout(120_000)
    const token = await getToken(request)
    test.skip(!token, '无法登录，跳过 Playwright（环境未就绪）')

    const wp = await findFirstWorkpaper(request, token!, WP_CODE_CANDIDATES, PROJECT_ID)
    test.skip(!wp.exists, `候选底稿均不存在: ${WP_CODE_CANDIDATES.join(',')}`)

    const auth = { Authorization: `Bearer ${token}` }
    const stamp = Date.now()
    const fileName = `e2e-wp-link-${stamp}.pdf`

    // create
    const createResp = await request.post(`/api/projects/${PROJECT_ID}/attachments`, {
      headers: auth,
      data: {
        file_name: fileName,
        file_path: `/tmp/${fileName}`,
        file_type: 'pdf',
        file_size: 128,
        attachment_type: 'general',
      },
    })
    test.skip(!createResp.ok(), `创建附件失败: ${createResp.status()}`)
    const created = await createResp.json()
    const attId = created?.data?.id ?? created?.id
    test.skip(!attId, '创建附件未返回 id')

    let cleaned = false
    const cleanup = async () => {
      if (cleaned) return
      cleaned = true
      await request.delete(`/api/working-papers/${wp.wpId}/attachments/${attId}/link`, {
        headers: auth,
      }).catch(() => {})
      await request.delete(`/api/attachments/${attId}`, { headers: auth }).catch(() => {})
    }

    try {
      const assoc = await request.post(`/api/attachments/${attId}/associate`, {
        headers: auth,
        data: { wp_id: wp.wpId, association_type: 'evidence' },
      })
      expect(assoc.ok()).toBeTruthy()

      await loginAs(page, 'admin', 'admin123')
      await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp.wpId}/edit`)
      await page.waitForTimeout(3_000)
      await openAttachmentsDrawer(page)

      await expect(page.getByText(fileName)).toBeVisible({ timeout: 15_000 })

      // 解除关联（抽屉 item 行内 .wp-att-unlink-btn）
      const row = page.locator('.el-drawer .wp-att-item', { hasText: fileName })
      await row.locator('.wp-att-unlink-btn').click({ timeout: 10_000 })
      const confirm = page.locator('.el-message-box').getByRole('button', { name: /解除/ })
      await expect(confirm).toBeVisible({ timeout: 10_000 })
      await confirm.click()

      await expect(page.getByText(fileName)).toHaveCount(0, { timeout: 15_000 })

      const listResp = await request.get(`/api/working-papers/${wp.wpId}/attachments`, {
        headers: auth,
      })
      expect(listResp.ok()).toBeTruthy()
      const listBody = await listResp.json()
      const items = listBody?.data?.items ?? listBody?.items ?? []
      expect(items.some((i: { id: string }) => i.id === attId)).toBeFalsy()
    } finally {
      await cleanup()
    }
  })
})
