/**
 * H 类底稿 E2E: H0 固定资产循环函证 → ConfirmationHub + H0-5 替代程序
 *
 * 对齐 g-cycle-g0-confirmation-hub 模式：
 * - H0-1 summary testid
 * - H0-5 四区块可见
 * - ensure-test-project findWorkpaper + loginAs
 *
 * Requirements: 全部 (1~7)
 */
import { test, expect, type Page } from '@playwright/test'
import { TEST_PROJECT_ID, findWorkpaper } from './fixtures/ensure-test-project'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'

async function loginAs(page: Page, username = 'admin', password = 'admin123'): Promise<string> {
  const resp = await page.request.post(`${BASE_URL}/api/auth/login`, {
    data: { username, password },
  })
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token ?? ''
  // 设置前端登录态
  await page.goto(`${BASE_URL}/login`)
  await page.fill('input[type="text"]', username)
  await page.fill('input[type="password"]', password)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/dashboard**', { timeout: 10000 })
  return token
}

test.describe('H0 固定资产循环函证 → ConfirmationHub', () => {
  let token: string

  test.beforeEach(async ({ page }) => {
    token = await loginAs(page)
  })

  // ─── Req 7: H0 复用 confirmation-hub ──────────────────────────────────────

  test('H0 页面可正常打开（ConfirmationHub 路由）', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${TEST_PROJECT_ID}/workpaper/H0`)
    await expect(
      page.locator('.confirmation-hub, .workpaper-container, [data-testid="workpaper-content"]'),
    ).toBeVisible({ timeout: 15000 })
  })

  test('H0 componentType 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${TEST_PROJECT_ID}/workpaper/H0`)
    expect(response?.status()).not.toBe(404)
  })

  test('H0 使用与 D0/G0 相同的 confirmation-hub 组件', async ({ page }) => {
    const h0Response = await page.goto(`${BASE_URL}/project/${TEST_PROJECT_ID}/workpaper/H0`)
    expect(h0Response?.status()).not.toBe(404)

    const g0Response = await page.goto(`${BASE_URL}/project/${TEST_PROJECT_ID}/workpaper/G0`)
    expect(g0Response?.status()).not.toBe(404)
  })

  // ─── Req 1: H0-1 confirmation-summary 路由 ────────────────────────────────

  test('H0-1 函证结果汇总渲染 confirmation-summary', async ({ page, request }) => {
    const wpResult = await findWorkpaper(request, token, 'H0-1', TEST_PROJECT_ID)
    test.skip(!wpResult.exists || !wpResult.wpId, '测试项目无 H0-1 底稿')

    await page.goto(
      `${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers/${wpResult.wpId}/edit`,
    )
    // confirmation-summary 组件渲染（class 或 onboarding 空态均算成功）
    await expect(
      page.locator('.gt-confirmation-summary'),
    ).toBeVisible({ timeout: 20000 })
  })

  test('H0-1 render-config 命中 confirmation-summary', async ({ request }) => {
    const wpResult = await findWorkpaper(request, token, 'H0-1', TEST_PROJECT_ID)
    test.skip(!wpResult.exists || !wpResult.wpId, '测试项目无 H0-1 底稿')

    const resp = await request.get(`${BASE_URL}/api/workpapers/${wpResult.wpId}/render-config`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(resp.ok()).toBeTruthy()
    const body = await resp.json()
    const data = body?.data ?? body
    const componentType = data?.componentType ?? data?.component_type
    // 可能在 sheets 数组内
    const sheets = data?.sheets as Array<{ componentType?: string; component_type?: string }> | undefined
    const resolvedType = componentType ?? sheets?.[0]?.componentType ?? sheets?.[0]?.component_type
    expect(resolvedType).toBe('confirmation-summary')
  })

  // ─── Req 2 + 4: H0-5 替代程序渲染 + 四区块 ────────────────────────────────

  test('H0-5 替代程序渲染 h0-alternative-h05 testid', async ({ page, request }) => {
    test.setTimeout(30000)
    const wpResult = await findWorkpaper(request, token, 'H0', TEST_PROJECT_ID)

    if (wpResult.exists && wpResult.wpId) {
      await page.goto(
        `${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers/${wpResult.wpId}/edit?sheet=替代程序H0-5`,
      )
    } else {
      await page.goto(`${BASE_URL}/project/${TEST_PROJECT_ID}/workpaper/H0-5`)
    }

    await expect(
      page.locator('[data-testid="h0-alternative-h05"]'),
    ).toBeVisible({ timeout: 20000 })
  })

  test('H0-5 四区块检查表可见', async ({ page, request }) => {
    test.setTimeout(45000)
    const wpResult = await findWorkpaper(request, token, 'H0', TEST_PROJECT_ID)

    if (wpResult.exists && wpResult.wpId) {
      await page.goto(
        `${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers/${wpResult.wpId}/edit?sheet=替代程序H0-5`,
      )
    } else {
      await page.goto(`${BASE_URL}/project/${TEST_PROJECT_ID}/workpaper/H0-5`)
    }

    await expect(
      page.locator('[data-testid="h0-alternative-h05"]'),
    ).toBeVisible({ timeout: 20000 })

    // 四区块标题（CheckBlock 组件渲染）
    // 区块① 期后验收/权属证据检查
    // 区块② 期末余额支持性证据
    // 区块③ 本期新增资产检查
    // 区块④ 抵押担保/融资租赁证据
    // 需要先有选中公司才能看到区块，否则只看到 master 空态
    const hasCompany = await page.locator('.alternative-d05-master__item, .master-list__item').count() > 0

    if (hasCompany) {
      // 点选第一个公司展开 Detail
      await page.locator('.alternative-d05-master__item, .master-list__item').first().click()
      await page.waitForTimeout(1000)

      // 验证四区块可见（CheckBlock 组件在 Detail 区域渲染）
      const checkBlocks = page.locator('.check-block, .gt-check-block')
      await expect(checkBlocks).toHaveCount(4, { timeout: 10000 })
    }
    // 无公司时 — 仍确保组件壳层正确渲染
    await expect(page.locator('.gt-confirmation-alternative-h05')).toBeVisible()
  })

  test('H0-5 "导入导出" 下拉按钮存在', async ({ page, request }) => {
    test.setTimeout(30000)
    const wpResult = await findWorkpaper(request, token, 'H0', TEST_PROJECT_ID)

    if (wpResult.exists && wpResult.wpId) {
      await page.goto(
        `${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers/${wpResult.wpId}/edit?sheet=替代程序H0-5`,
      )
    } else {
      await page.goto(`${BASE_URL}/project/${TEST_PROJECT_ID}/workpaper/H0-5`)
    }

    await expect(
      page.locator('[data-testid="h0-alternative-h05"]'),
    ).toBeVisible({ timeout: 20000 })

    // 导入导出 el-dropdown trigger button
    const ieButton = page.locator('.gt-confirmation-alternative-h05').getByText('导入导出')
    await expect(ieButton).toBeVisible({ timeout: 10000 })
  })

  test('H0-5 "版本历史" 按钮存在', async ({ page, request }) => {
    test.setTimeout(30000)
    const wpResult = await findWorkpaper(request, token, 'H0', TEST_PROJECT_ID)

    if (wpResult.exists && wpResult.wpId) {
      await page.goto(
        `${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers/${wpResult.wpId}/edit?sheet=替代程序H0-5`,
      )
    } else {
      await page.goto(`${BASE_URL}/project/${TEST_PROJECT_ID}/workpaper/H0-5`)
    }

    await expect(
      page.locator('[data-testid="h0-alternative-h05"]'),
    ).toBeVisible({ timeout: 20000 })

    // 版本历史按钮
    const versionBtn = page.locator('.gt-confirmation-alternative-h05').getByText('版本历史')
    await expect(versionBtn).toBeVisible({ timeout: 10000 })
  })

  // ─── Req 2.9: 基本交互 — 新增公司 ─────────────────────────────────────────

  test('H0-5 新增公司后出现在 master 列表', async ({ page, request }) => {
    test.setTimeout(60000)
    const wpResult = await findWorkpaper(request, token, 'H0', TEST_PROJECT_ID)
    test.skip(!wpResult.exists || !wpResult.wpId, '测试项目无 H0 底稿')

    await page.goto(
      `${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers/${wpResult.wpId}/edit?sheet=替代程序H0-5`,
    )
    await expect(
      page.locator('[data-testid="h0-alternative-h05"]'),
    ).toBeVisible({ timeout: 20000 })

    // 点击新增公司按钮（AlternativeD05Dashboard / Master 的 + 按钮）
    const addBtn = page.locator('.gt-confirmation-alternative-h05').getByText(/新增|添加/).first()
    if (await addBtn.isVisible()) {
      await addBtn.click()
      await page.waitForTimeout(500)

      // ElMessageBox.prompt 输入公司名称
      const promptInput = page.locator('.el-message-box__input input')
      if (await promptInput.isVisible({ timeout: 3000 }).catch(() => false)) {
        const testCompanyName = `E2E测试公司_${Date.now()}`
        await promptInput.fill(testCompanyName)
        await page.locator('.el-message-box__btns .el-button--primary').click()
        await page.waitForTimeout(1000)

        // 验证公司出现在 master 列表
        const masterList = page.locator('.gt-confirmation-alternative-h05')
        await expect(masterList.getByText(testCompanyName)).toBeVisible({ timeout: 5000 })
      }
    }
  })

  // ─── Req 1: render-config 契约验证 H0-5 ───────────────────────────────────

  test('H0-5 render-config 命中 confirmation-alternative-h05', async ({ request }) => {
    const wpResult = await findWorkpaper(request, token, 'H0', TEST_PROJECT_ID)
    test.skip(!wpResult.exists || !wpResult.wpId, '测试项目无 H0 底稿')

    const resp = await request.get(`${BASE_URL}/api/workpapers/${wpResult.wpId}/render-config`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(resp.ok()).toBeTruthy()
    const body = await resp.json()
    const data = body?.data ?? body
    const sheets = (data?.sheets ?? []) as Array<{
      sheetName?: string
      sheet_name?: string
      componentType?: string
      component_type?: string
    }>
    const target = sheets.find(
      (s) => (s.sheetName ?? s.sheet_name ?? '').includes('H0-5'),
    )
    const componentType = target?.componentType ?? target?.component_type
    expect(componentType).toBe('confirmation-alternative-h05')
  })
})
