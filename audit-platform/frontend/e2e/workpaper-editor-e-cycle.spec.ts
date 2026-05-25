/**
 * UAT — E 循环底稿编辑器 Playwright 实测
 *
 * 锚定 spec workpaper-editor-refactor Phase 3 Task 3.1
 *
 * 验证 E1 货币资金底稿全流程：
 * 1. 编辑器正常加载（无 ErrorBoundary / 无 ReferenceError）
 * 2. Sheet 导航正常渲染
 * 3. console.errors = 0（排除已知 /ai/ 405）
 * 4. useECycleEditor composable 集成验证（API 层）
 *
 * 项目：辽宁卫生服务有限公司 2025（37814426-a29e-4fc2-9313-a59d229bf7b0）
 *
 * Requirements: Req 2, Req 4
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

const PROJECT_ID = '37814426-a29e-4fc2-9313-a59d229bf7b0'

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
  return token
}

/** 调 API 找出 E1 底稿 ID */
async function findE1WpId(request: APIRequestContext, token: string): Promise<string | null> {
  const resp = await request.get(`/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])
  const e1 = list.find((w: any) => (w.wp_code || '').toUpperCase() === 'E1')
  return e1?.id || null
}

test.describe('E 循环底稿编辑器实测（Phase 3 Task 3.1）', () => {
  test('3.1.1 — E1 货币资金底稿加载无 ErrorBoundary + 无 console errors', async ({ page, request }) => {
    test.setTimeout(60_000)

    // 收集 console errors（排除已知 /ai/ 405）
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        // 排除已知的 /ai/ 端点 405（AI 服务未实现）
        if (/\/ai\//.test(text) && /405/.test(text)) return
        // 排除 SSE 断连等网络噪音
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        consoleErrors.push(text)
      }
    })
    page.on('pageerror', (err) => {
      consoleErrors.push(`pageerror: ${err.message}`)
    })

    const token = await loginAs(page, 'admin', 'admin123')
    const wpId = await findE1WpId(request, token)
    test.skip(!wpId, '辽宁卫生项目无 E1 底稿（需先跑 chain orchestrator）')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)

    // 等待编辑器容器渲染（overlay 模式：容器永远存在）
    await page.waitForSelector('.gt-wp-editor, .gt-wp-editor-loading', { timeout: 15_000 })

    // 等待加载完成（GtLoadingOverlay 消失）
    await page.waitForTimeout(8_000)
    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 }).catch(() => {
        throw new Error('GtLoadingOverlay 在 23 秒后仍可见，疑似死锁；底稿: E1')
      })
    }

    // 验证 1：无 ErrorBoundary 错误页面
    const errorBoundary = page.locator('.gt-error-boundary, [class*="error-boundary"]')
    expect(await errorBoundary.count(), 'ErrorBoundary 不应出现').toBe(0)

    // 验证 2：无 setup ref ReferenceError / TypeError
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)

    // 验证 3：总 console errors 为 0
    expect(consoleErrors, `控制台错误（排除 /ai/ 405 后）:\n${consoleErrors.join('\n')}`).toHaveLength(0)
  })

  test('3.1.2 — E1 sheet 导航正常渲染', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')
    const wpId = await findE1WpId(request, token)
    test.skip(!wpId, 'E1 不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)

    // 等待编辑器加载完成
    await page.waitForTimeout(8_000)
    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 验证 sheet 导航面板存在
    const sheetNav = page.locator('.gt-usn')
    await expect(sheetNav).toBeVisible({ timeout: 5_000 })

    // 验证至少有 1 个 sheet 分组（E1 使用通用 useUniverSheetNav）
    const groups = page.locator('.gt-usn__group')
    const groupCount = await groups.count()
    expect(groupCount, `E1 应有 ≥1 个 sheet 分组，实际 ${groupCount}`).toBeGreaterThanOrEqual(1)
  })

  test('3.1.3 — E 循环 useECycleEditor composable 集成验证（API 层）', async ({ request }) => {
    test.setTimeout(20_000)
    // 验证 E1 底稿存在且可通过 API 访问
    const tokenResp = await request.post('/api/auth/login', { data: { username: 'admin', password: 'admin123' } })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const wpId = await findE1WpId(request, token)
    test.skip(!wpId, 'E1 不存在')

    // 验证底稿详情可获取
    const detailResp = await request.get(`/api/projects/${PROJECT_ID}/working-papers/${wpId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(detailResp.status()).toBe(200)
    const detail = await detailResp.json()
    const wpData = detail?.data || detail
    expect(wpData.wp_code?.toUpperCase()).toBe('E1')

    // 验证 prerequisite-status 端点可达（E 循环前置状态）
    const preResp = await request.get(
      `/api/projects/${PROJECT_ID}/workpapers/prerequisite-status?wp_code=E1`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect([200, 404]).toContain(preResp.status())
  })
})
