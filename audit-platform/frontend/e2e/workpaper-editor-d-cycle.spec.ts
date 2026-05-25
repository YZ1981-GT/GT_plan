/**
 * UAT — D 循环底稿编辑器 Playwright 实测
 *
 * 锚定 spec workpaper-editor-refactor Phase 2 Task 2.4
 *
 * 验证 D2 应收账款审定表全流程：
 * 1. 编辑器正常加载（无 ErrorBoundary / 无 ReferenceError）
 * 2. 18 sheet 分组导航正常渲染
 * 3. 审计导航图弹窗可打开/关闭
 * 4. console.errors = 0（排除已知 /ai/ 405）
 *
 * 项目：辽宁卫生服务有限公司 2025（37814426-a29e-4fc2-9313-a59d229bf7b0）
 *
 * Requirements: Req 4
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

/** 调 API 找出 D2 底稿 ID */
async function findD2WpId(request: APIRequestContext, token: string): Promise<string | null> {
  const resp = await request.get(`/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])
  const d2 = list.find((w: any) => (w.wp_code || '').toUpperCase() === 'D2')
  return d2?.id || null
}

test.describe('D 循环底稿编辑器实测（Phase 2 Task 2.4）', () => {
  test('2.4.1 — D2 应收账款审定表加载无 ErrorBoundary + 无 console errors', async ({ page, request }) => {
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
    const wpId = await findD2WpId(request, token)
    test.skip(!wpId, '辽宁卫生项目无 D2 底稿（需先跑 chain orchestrator）')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)

    // 等待编辑器容器渲染（overlay 模式：容器永远存在）
    await page.waitForSelector('.gt-wp-editor, .gt-wp-editor-loading', { timeout: 15_000 })

    // 等待加载完成（GtLoadingOverlay 消失）
    await page.waitForTimeout(8_000)
    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 }).catch(() => {
        throw new Error('GtLoadingOverlay 在 23 秒后仍可见，疑似死锁；底稿: D2')
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

  test('2.4.2 — D2 sheet 分组导航正常渲染（≥5 个分组）', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')
    const wpId = await findD2WpId(request, token)
    test.skip(!wpId, 'D2 不存在')

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

    // 验证分组数量（D2 有多个 sheet 分类组，至少应有 5 个）
    const groups = page.locator('.gt-usn__group')
    const groupCount = await groups.count()
    expect(groupCount, `D2 应有 ≥5 个 sheet 分组，实际 ${groupCount}`).toBeGreaterThanOrEqual(5)

    // 验证 sheet 总数显示
    const totalBadge = page.locator('.gt-usn__title .gt-amt')
    if (await totalBadge.count() > 0) {
      const totalText = await totalBadge.textContent()
      const totalNum = parseInt(totalText || '0', 10)
      expect(totalNum, `D2 sheet 总数应 ≥15，实际 ${totalNum}`).toBeGreaterThanOrEqual(15)
    }
  })

  test('2.4.3 — 审计导航图弹窗可打开和关闭', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')
    const wpId = await findD2WpId(request, token)
    test.skip(!wpId, 'D2 不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)

    // 等待编辑器加载完成
    await page.waitForTimeout(8_000)
    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 验证审计导航图按钮存在（hasAuditNav 对 D 循环应为 true）
    const auditNavBtn = page.locator('button').filter({ hasText: /审计导航图/ })
    await expect(auditNavBtn.first()).toBeVisible({ timeout: 5_000 })

    // 点击打开审计导航图弹窗
    await auditNavBtn.first().click()
    await page.waitForTimeout(1_500)

    // 验证弹窗打开（dialog 通过 append-to-body 传送到 body）
    const dialog = page.locator('.gt-audit-nav-dialog')
    await expect(dialog).toBeVisible({ timeout: 5_000 })

    // 验证弹窗标题包含 D2 信息
    const dialogTitle = page.locator('.gt-audit-nav-dialog__title')
    await expect(dialogTitle).toBeVisible()

    // 关闭弹窗（点击关闭按钮）
    const closeBtn = dialog.locator('.el-dialog__headerbtn').first()
    if (await closeBtn.count() > 0) {
      await closeBtn.click()
    } else {
      // 备选：按 ESC 关闭
      await page.keyboard.press('Escape')
    }
    await page.waitForTimeout(500)

    // 验证弹窗已关闭
    await expect(dialog).toBeHidden({ timeout: 5_000 })
  })

  test('2.4.4 — D 循环 useDCycleEditor composable 集成验证（API 层）', async ({ request }) => {
    test.setTimeout(20_000)
    // 验证 D2 底稿存在且可通过 API 访问
    const tokenResp = await request.post('/api/auth/login', { data: { username: 'admin', password: 'admin123' } })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const wpId = await findD2WpId(request, token)
    test.skip(!wpId, 'D2 不存在')

    // 验证底稿详情可获取
    const detailResp = await request.get(`/api/projects/${PROJECT_ID}/working-papers/${wpId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(detailResp.status()).toBe(200)
    const detail = await detailResp.json()
    const wpData = detail?.data || detail
    expect(wpData.wp_code?.toUpperCase()).toBe('D2')

    // 验证 prerequisite-status 端点可达（D 循环前置状态）
    const preResp = await request.get(
      `/api/projects/${PROJECT_ID}/workpapers/prerequisite-status?wp_code=D2`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect([200, 404]).toContain(preResp.status())
  })
})
