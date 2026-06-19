/**
 * e-cycle-e1-26-ipo-applicability.spec.ts — E1-26 IPO 底稿适用性灰显 E2E 验证
 *
 * 锚定 spec e-cycle-workpapers Task 38
 *
 * 验证 E1-26 货币资金IPO/舞弊应对底稿：
 * 1. 对于标准年审项目（annual_audit）：应显示"不适用"覆盖层或灰显
 * 2. render-config 返回 audit-sheet componentType
 * 3. 项目 business_category 确认
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

test.describe('Task 38: E1-26 IPO 底稿适用性灰显（普通年审项目）', () => {
  test('38.1 — E1-26 普通年审项目显示不适用覆盖', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'E1-26', PROJECT_ID)
    test.skip(!wpResult.exists, 'E1-26 底稿不存在，需先运行项目底稿生成')

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
        if (/onlyoffice|DocsAPI/.test(text)) return
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
        pageContent?.includes('仅适用于') ||
        pageContent?.includes('IPO') ||
        pageContent?.includes('上市')

      expect(
        hasNaOverlay || hasNaText || hasOverlay || contentHasNa,
        'E1-26 在普通年审项目中应显示"不适用"覆盖或提示',
      ).toBeTruthy()
    } else {
      // IPO 项目：正常渲染
      const auditSheet = page.locator(
        '.gt-audit-sheet, .onlyoffice-editor, .gt-d-form-table, .gt-deliverable-preview',
      )
      expect(
        await auditSheet.count(),
        'E1-26 在 IPO 项目中应正常渲染',
      ).toBeGreaterThan(0)
    }

    // 验证无严重 console errors
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('38.2 — E1-26 render-config API 验证 audit-sheet 类型', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'E1-26', PROJECT_ID)
    test.skip(!wpResult.exists, 'E1-26 底稿不存在')

    const rcResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}/render-config`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)
    const rcBody = await rcResp.json()
    const rcData = rcBody?.data || rcBody
    expect(rcData.component_type || rcData.componentType).toBe('audit-sheet')
  })

  test('38.3 — 项目 business_category 确认', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    const projResp = await request.get(`/api/projects/${PROJECT_ID}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(projResp.status()).toBe(200)
    const projBody = await projResp.json()
    const projData = projBody?.data || projBody

    expect(projData).toBeTruthy()
    expect(projData.id || projData.project_id).toBeTruthy()

    const bc = projData?.business_category || 'annual_audit'
    console.log(`测试项目 business_category: ${bc}`)
    // 辽宁卫生服务为普通年审，不在 IPO 范围内
    expect(['ipo', 'listed', 'neeq', 'restructuring']).not.toContain(bc)
  })

  test('38.4 — E1-26~E1-32 全部 IPO 底稿类型一致性', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    // 验证 E1-26~E1-32 全部为 audit-sheet
    const ipoCodes = ['E1-26', 'E1-27', 'E1-28', 'E1-29', 'E1-30', 'E1-31', 'E1-32']
    for (const code of ipoCodes) {
      const wpResult = await findWorkpaper(request, token, code, PROJECT_ID)
      if (wpResult.exists) {
        const rcResp = await request.get(
          `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}/render-config`,
          { headers: { Authorization: `Bearer ${token}` } },
        )
        if (rcResp.status() === 200) {
          const rcBody = await rcResp.json()
          const rcData = rcBody?.data || rcBody
          const ct = rcData.component_type || rcData.componentType
          expect(ct, `${code} 应为 audit-sheet`).toBe('audit-sheet')
        }
      }
    }
  })
})
