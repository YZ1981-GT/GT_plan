/**
 * d-cycle-d4-22-ipo-applicable.spec.ts — D4-22 IPO 底稿适用性 E2E 验证
 *
 * 锚定 spec d-cycle-workpapers Task 46
 *
 * 验证 D4-22 营业收入IPO舞弊应对：
 * 1. 对于标准年审项目（annual_audit）：应显示"不适用"覆盖层
 * 2. 对于 IPO 项目：正常渲染（无覆盖层）
 *
 * applicable_when: business_category IN ['ipo','listed','neeq','restructuring']
 * 测试项目为普通年审 → 应显示不适用
 *
 * 项目：辽宁卫生服务有限公司 2025（37814426-a29e-4fc2-9313-a59d229bf7b0）
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { TEST_PROJECT_ID, findWorkpaper } from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID

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

async function getToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

test.describe('Task 46: D4-22 IPO 底稿适用性灰显（普通年审项目）', () => {
  test('46.1 — D4-22 普通年审项目显示不适用覆盖', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'D4-22', PROJECT_ID)
    test.skip(!wpResult.exists, 'D4-22 底稿不存在，需先运行项目底稿生成')

    // 先确认测试项目是普通年审（非 IPO）
    const projResp = await request.get(`/api/projects/${PROJECT_ID}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const projBody = await projResp.json()
    const projData = projBody?.data || projBody
    const businessCategory = projData?.business_category || 'annual_audit'
    const isIpo = ['ipo', 'listed', 'neeq', 'restructuring'].includes(businessCategory)

    // 收集 console errors
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (/\/ai\//.test(text) && /405/.test(text)) return
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        if (/Failed to load resource.*500/.test(text)) return
        consoleErrors.push(text)
      }
    })
    page.on('pageerror', (err) => {
      consoleErrors.push(`pageerror: ${err.message}`)
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    if (!isIpo) {
      // 普通年审项目：应显示"不适用"覆盖层或灰显效果
      const notApplicable = page.locator(
        '[class*="not-applicable"], [class*="na-overlay"], .gt-not-applicable',
      )
      const naTextOnPage = page.locator('text=不适用')
      const overlayEl = page.locator('[class*="overlay"]').filter({ hasText: /不适用|N\/A/ })

      const hasNaOverlay = await notApplicable.count() > 0
      const hasNaText = await naTextOnPage.count() > 0
      const hasOverlay = await overlayEl.count() > 0

      // 页面内容检查
      const pageContent = await page.textContent('body')
      const contentHasNa =
        pageContent?.includes('不适用') ||
        pageContent?.includes('本底稿不适用') ||
        pageContent?.includes('仅适用于')

      expect(
        hasNaOverlay || hasNaText || hasOverlay || contentHasNa,
        'D4-22 在普通年审项目中应显示"不适用"覆盖或提示',
      ).toBeTruthy()
    } else {
      // IPO 项目：正常渲染
      const auditSheet = page.locator(
        '.gt-audit-sheet, .onlyoffice-editor, .gt-d-form-table, .gt-deliverable-preview',
      )
      expect(
        await auditSheet.count(),
        'D4-22 在 IPO 项目中应正常渲染',
      ).toBeGreaterThan(0)
    }

    // 验证无严重 console errors
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('46.2 — D4-22 render-config API 验证 audit-sheet 类型', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'D4-22', PROJECT_ID)
    test.skip(!wpResult.exists, 'D4-22 底稿不存在')

    // 验证 render-config 返回 audit-sheet 类型
    const rcResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}/render-config`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)
    const rcBody = await rcResp.json()
    const rcData = rcBody?.data || rcBody
    expect(rcData.component_type || rcData.componentType).toBe('audit-sheet')
  })

  test('46.3 — 项目 business_category 确认', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    // 确认测试项目的 business_category
    const projResp = await request.get(`/api/projects/${PROJECT_ID}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(projResp.status()).toBe(200)
    const projBody = await projResp.json()
    const projData = projBody?.data || projBody

    // 至少项目应存在且有基本信息
    expect(projData).toBeTruthy()
    expect(projData.id || projData.project_id).toBeTruthy()

    // 记录 business_category（用于决定测试预期）
    const bc = projData?.business_category || 'annual_audit'
    console.log(`测试项目 business_category: ${bc}`)
  })
})
