import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

const BACKEND = process.env.PLAYWRIGHT_BACKEND_URL || 'http://127.0.0.1:9980'
const FORMULA_GATE_PROJECT_PREFIX = '【E2E】公式管理运行时门禁_'
const FORMULA_GATE_CODES = ['A1', 'D2-1'] as const

type Target = { projectId: string; wpId: string; wpCode: string }

async function loginToken(request: APIRequestContext) {
  const response = await request.post(`${BACKEND}/api/auth/login`, {
    data: { username: 'admin', password: 'admin123' },
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

async function discoverTargets(request: APIRequestContext, token: string): Promise<Target[]> {
  const headers = { Authorization: `Bearer ${token}` }
  const projectsResponse = await request.get(`${BACKEND}/api/projects`, {
    headers,
    params: { page: 1, page_size: 100 },
  })
  expect(projectsResponse.ok(), `项目列表失败 ${projectsResponse.status()}`).toBeTruthy()
  const projectsBody = await projectsResponse.json()
  const projects = projectsBody?.data?.items ?? projectsBody?.items ?? projectsBody?.data ?? []
  const project = projects.find((item: any) =>
    item.report_scope === 'standalone'
    && String(item.name || item.client_name || '').startsWith(FORMULA_GATE_PROJECT_PREFIX),
  )
  expect(project, '必须由 fresh-DB seed 生成稳定 standalone 公式门禁项目').toBeTruthy()
  const projectId = String(project.id || project.project_id || '')
  const papersResponse = await request.get(`${BACKEND}/api/projects/${projectId}/working-papers`, {
    headers,
    params: { page: 1, page_size: 100 },
  })
  expect(papersResponse.ok(), `底稿列表失败 ${papersResponse.status()}`).toBeTruthy()
  const papersBody = await papersResponse.json()
  const papers = papersBody?.data?.items ?? papersBody?.items ?? []
  const targets = FORMULA_GATE_CODES.map((wpCode) => {
    const paper = papers.find((item: any) => String(item.wp_code || '') === wpCode)
    const wpId = String(paper?.wp_id || paper?.id || '')
    expect(wpId, `门禁项目必须包含 active ${wpCode} 底稿`).toBeTruthy()
    return { projectId, wpId, wpCode }
  })
  expect(new Set(targets.map((item) => item.projectId)).size).toBe(1)
  return targets
}


test('公式管理真实 capability 与当前页入口代表矩阵', async ({ page, request }) => {
  test.setTimeout(180_000)
  const health = await request.get(`${BACKEND}/livez`)
  expect(health.status(), '后端必须真实可达，禁止默认 skip').toBe(200)
  const auth = await loginToken(request)
  const targets = await discoverTargets(request, String(auth.access_token))
  expect(targets.map((item) => item.wpCode), '必须同时验证 A1 与普通底稿').toEqual([...FORMULA_GATE_CODES])
  await installAuth(page, auth)

  for (const target of targets) {
    const formulaRequests: Array<{ url: string; status: number }> = []
    const capabilityRequests: string[] = []
    const consoleErrors: string[] = []
    const onResponse = (response: any) => {
      const url = response.url()
      if (/formula|acnr\/anchors/.test(url)) formulaRequests.push({ url, status: response.status() })
      if (url.includes('/capability-snapshot')) capabilityRequests.push(url)
    }
    const onConsole = (message: any) => {
      if (message.type() === 'error') consoleErrors.push(message.text())
    }
    page.on('response', onResponse)
    page.on('console', onConsole)

    await page.goto(`/projects/${target.projectId}/workpapers/${target.wpId}/edit`, {
      waitUntil: 'domcontentloaded',
    })
    expect(page.url()).not.toMatch(/\/login/)
    await expect.poll(
      () => capabilityRequests.length,
      { timeout: 30_000, message: `${target.wpCode} 必须取得真实 capability snapshot` },
    ).toBeGreaterThan(0)
    const button = page.locator('[data-testid="formula-manager-open"]')
    await expect(button, `${target.wpCode} 公式管理入口`).toHaveCount(1, { timeout: 30_000 })
    await expect(button).toBeVisible()
    await expect(button).toBeEnabled({ timeout: 30_000 })

    // 页面装载期的其它业务模块错误不冒充公式门禁结果；从点击前清零，只观测本次公式操作。
    formulaRequests.length = 0
    consoleErrors.length = 0
    await button.click()
    const dialog = page.locator('.el-dialog').filter({ hasText: '公式管理' })
    await expect(dialog).toHaveCount(1, { timeout: 20_000 })
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText(target.wpCode)

    await expect.poll(
      () => formulaRequests.some(
        (item) => item.url.includes(`/workpapers/${target.wpId}/formulas`),
      ),
      { timeout: 30_000, message: `${target.wpCode} 必须请求当前实例公式，而不是全局/其他实例` },
    ).toBe(true)
    const relevant4xx = formulaRequests.filter((item) => item.status >= 400)
    expect(relevant4xx, `${target.wpCode} 公式请求不得出现 4xx/5xx`).toEqual([])
    expect(consoleErrors.filter((text) => !text.includes('favicon'))).toEqual([])

    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    page.off('response', onResponse)
    page.off('console', onConsole)
  }
})


async function discoverConsolidatedProject(request: APIRequestContext, token: string): Promise<string> {
  const response = await request.get(`${BACKEND}/api/projects`, {
    headers: { Authorization: `Bearer ${token}` },
    params: { page: 1, page_size: 100 },
  })
  expect(response.ok()).toBeTruthy()
  const body = await response.json()
  const projects = body?.data?.items ?? body?.items ?? body?.data ?? []
  const hit = projects.find((project: any) => project.report_scope === 'consolidated')
  expect(hit, '必须有 consolidated 项目验证 scope context').toBeTruthy()
  return String(hit.id)
}

test('合并三 scope 使用显式 context，不伪造 wpId', async ({ page, request }) => {
  test.setTimeout(180_000)
  const auth = await loginToken(request)
  const projectId = await discoverConsolidatedProject(request, String(auth.access_token))
  await installAuth(page, auth)
  await page.goto(`/projects/${projectId}/consolidation`, { waitUntil: 'domcontentloaded' })
  expect(page.url()).not.toMatch(/\/login/)

  const formulaButton = page.getByRole('button', { name: /公式管理/ }).first()
  await expect(formulaButton).toBeVisible({ timeout: 30_000 })
  const cases = [
    { tab: '合并工作底稿', expected: '合并工作底稿' },
    { tab: '合并报表', expected: '合并报表' },
    { tab: '合并附注', expected: '合并附注' },
  ]

  for (const item of cases) {
    const tab = page.getByRole('tab', { name: item.tab })
    await expect(tab).toBeVisible({ timeout: 30_000 })
    await tab.click()
    await formulaButton.click()
    const dialog = page.locator('.el-dialog').filter({ hasText: '公式管理' })
    await expect(dialog).toHaveCount(1, { timeout: 20_000 })
    await expect(dialog).toContainText(item.expected)
    const currentUrl = page.url()
    expect(currentUrl).toContain(`/projects/${projectId}/consolidation`)
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
  }
})


test('capability 拒绝时入口禁用且不请求公式数据', async ({ page, request }) => {
  test.setTimeout(120_000)
  const auth = await loginToken(request)
  const targets = await discoverTargets(request, String(auth.access_token))
  const target = targets[0]
  expect(target).toBeTruthy()
  await installAuth(page, auth)

  const denied = {
    allowed: false, reasonCode: 'role_denied', owner: 'workpaper-capability-matrix',
    nextAction: '联系项目负责人', zhMessage: '当前角色无权执行此操作。',
  }
  await page.route('**/api/workpapers/*/capability-snapshot*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, message: 'success', data: {
        snapshotVersion: '1.0', subjectDigest: 'd'.repeat(64), ownerEpoch: 1,
        expiresAt: '2099-01-01T00:00:00Z', projectId: target.projectId,
        wpId: target.wpId, sheetUid: null, role: 'readonly',
        formulaView: denied, formulaEditUser: denied, formulaHistory: denied,
        aiReviewPage: denied, aiReviewBatch: denied, aiAssistChat: denied,
        humanReviewRead: denied, humanReviewWrite: denied, guidanceRead: denied,
      } }),
    })
  })
  let formulaListRequests = 0
  page.on('request', (req) => {
    if (req.url().includes(`/workpapers/${target.wpId}/formulas`)) formulaListRequests++
  })

  await page.goto(`/projects/${target.projectId}/workpapers/${target.wpId}/edit`, {
    waitUntil: 'domcontentloaded',
  })
  const button = page.locator('[data-testid="formula-manager-open"]')
  await expect(button).toHaveCount(1, { timeout: 30_000 })
  await expect(button).toBeDisabled({ timeout: 30_000 })
  expect(formulaListRequests).toBe(0)
})
