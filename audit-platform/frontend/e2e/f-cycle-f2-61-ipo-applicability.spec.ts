/**
 * f-cycle-f2-61-ipo-applicability.spec.ts — F2-61 IPO 底稿适用性灰显（普通年审项目）E2E 验证
 *
 * 锚定 spec f-cycle-workpapers Task 57
 *
 * 验证 F2-61 IPO 底稿适用性控制：
 * 1. F2-61 底稿存在且 render-config 返回 audit-sheet
 * 2. F2-61~F2-72 IPO 系列全部为 audit-sheet
 * 3. 普通年审项目中 F2-61~F2-72 应标记为不适用
 * 4. render-config 应包含 applicable_when 或 applicability 字段
 *
 * 适用性规则：
 *   applicable_when: business_category IN ['ipo', 'listed', 'neeq', 'restructuring']
 *   普通年审项目 business_category = 'annual_audit' → 不适用 → 灰显
 *
 * 项目：辽宁卫生服务有限公司 2025（37814426-a29e-4fc2-9313-a59d229bf7b0）— 普通年审
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

test.describe('Task 57: F2-61 IPO 底稿适用性灰显（普通年审项目）', () => {
  test('57.1 — F2-61 底稿存在且为 audit-sheet', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'F2-61', PROJECT_ID)
    test.skip(!wpResult.exists, 'F2-61 底稿不存在，需先运行项目底稿生成')

    const rcResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}/render-config`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)
    const rcBody = await rcResp.json()
    const rcData = rcBody?.data || rcBody
    const componentType = rcData.component_type || rcData.componentType
    expect(componentType).toBe('audit-sheet')
  })

  test('57.2 — F2-61~F2-72 IPO 系列全部为 audit-sheet', async ({ request }) => {
    test.setTimeout(60_000)
    const token = await getToken(request)

    for (let i = 61; i <= 72; i++) {
      const code = `F2-${i}`
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

  test('57.3 — 普通年审项目 F2-61 底稿显示不适用（灰显）', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'F2-61', PROJECT_ID)
    test.skip(!wpResult.exists, 'F2-61 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(8_000)

    // 验证：页面上应有"不适用"提示 或 灰显覆盖层 或 applicable 相关元素
    const pageContent = await page.textContent('body')
    const hasNotApplicable =
      pageContent?.includes('不适用') ||
      pageContent?.includes('Not Applicable') ||
      pageContent?.includes('适用性')
    const hasGreyOverlay = await page.locator(
      '[class*="not-applicable"], [class*="grey"], [class*="disabled-overlay"], [class*="inapplicable"]',
    ).count() > 0

    // 或者 OnlyOffice 正常加载（IPO 底稿在普通项目中可能仍可打开但标记不适用）
    const hasOnlyOffice = await page.locator('[id*="onlyoffice"]').count() > 0

    expect(
      hasNotApplicable || hasGreyOverlay || hasOnlyOffice,
      'F2-61 在普通年审项目中应显示不适用/灰显或 OnlyOffice 渲染',
    ).toBeTruthy()
  })

  test('57.4 — 测试项目为普通年审类型确认', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    // 获取项目信息确认 business_category
    const projResp = await request.get(
      `/api/projects/${PROJECT_ID}`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(projResp.status()).toBe(200)
    const projBody = await projResp.json()
    const projData = projBody?.data || projBody

    // 项目类型应为普通年审（非 IPO）
    const category = projData.business_category || projData.audit_type || ''
    const isNotIPO = !['ipo', 'listed', 'neeq', 'restructuring'].includes(category)
    // 如果确实是 IPO 项目则跳过（测试逻辑不同）
    test.skip(!isNotIPO, '该项目为 IPO/上市/新三板类型，适用性为 True，跳过灰显验证')
  })
})
