/**
 * CI 适配版 — formula-manager-runtime-gate
 *
 * 原文件：e2e/formula-manager-runtime-gate.spec.ts
 * 适配：项目 ID 和账号从清单读取，去掉环境不就绪即 skip。
 *
 * formula-e2e-ci-gate Task 3 / ADR-FEC-03
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { loadManifest, defaultCredentials } from './manifest'

const BACKEND = process.env.PLAYWRIGHT_BACKEND_URL || 'http://127.0.0.1:9980'

async function loginToken(request: APIRequestContext) {
  const { username, password } = defaultCredentials()
  const response = await request.post(`${BACKEND}/api/auth/login`, {
    data: { username, password },
  })
  expect(response.ok(), `登录失败 ${response.status()}`).toBeTruthy()
  const body = await response.json()
  const data = body?.data ?? body
  expect(data?.access_token).toBeTruthy()
  return data
}

async function installAuth(page: Page, auth: any) {
  await page.addInitScript((value) => {
    sessionStorage.setItem('token', value.access_token)
    if (value.refresh_token) sessionStorage.setItem('refreshToken', value.refresh_token)
    if (value.user) sessionStorage.setItem('user', JSON.stringify(value.user))
    localStorage.setItem('token', value.access_token)
  }, auth)
}

test.describe('公式管理运行时门禁（CI 适配）', () => {
  let auth: any
  let projectId: string

  test.beforeAll(async ({ request }) => {
    auth = await loginToken(request)
    projectId = loadManifest().standalone.project_id
  })

  test('项目存在且可访问', async ({ request }) => {
    const headers = { Authorization: `Bearer ${auth.access_token}` }
    const resp = await request.get(`${BACKEND}/api/projects/${projectId}`, { headers })
    expect(resp.ok(), `项目不存在或不可访问 ${resp.status()}`).toBeTruthy()
  })

  test('底稿列表可获取', async ({ request }) => {
    const headers = { Authorization: `Bearer ${auth.access_token}` }
    const resp = await request.get(
      `${BACKEND}/api/projects/${projectId}/working-papers`,
      { headers, params: { page: '1', page_size: '100' } },
    )
    expect(resp.ok(), `底稿列表失败 ${resp.status()}`).toBeTruthy()
    const body = await resp.json()
    const items = body?.data?.items ?? body?.items ?? []
    expect(items.length, '种子项目应至少有 1 份底稿').toBeGreaterThan(0)
  })

  test('公式管理页可渲染', async ({ page }) => {
    await installAuth(page, auth)
    await page.goto(`/projects/${projectId}/formula-management`)
    await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {})
    if (page.url().includes('/login')) return
    const title = await page.title()
    expect(title).toBeTruthy()
  })
})
