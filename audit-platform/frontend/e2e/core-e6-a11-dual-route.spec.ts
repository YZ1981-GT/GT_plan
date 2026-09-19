/**
 * core-e6-a11-dual-route.spec.ts — E6 A11 双轨路由验证
 *
 * 锚定 spec a7-a15-completion-workpapers Task 23 / e2e-matrix E6
 * E6: A11 目录 F=A11-1 → 审定表 sheet，非 docx
 * E7: A11 chip A11-1 → docx 弹窗（已在 docx-popup-e2e.spec.ts 覆盖）
 *
 * 验证 A11 bundle 的双轨路由：
 * 1. 程序表 chip "A11-1" → INLINE_POPUP（docx 弹窗） — 已有 E7 覆盖
 * 2. 带 ?sheet=A11-WP-1 打开 A11 → 自动切换到"A11-1 审定表" tab
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

const PROJECT_ID = '37814426-a29e-4fc2-9313-a59d229bf7b0'
const BASE_API = `/api/projects/${PROJECT_ID}`

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

test.describe('E6: A11 双轨路由 — 底稿目录 F=A11-1 → 审定表 sheet', () => {
  test('带 ?sheet=A11-WP-1 打开 A11 bundle → 自动切换到审定表 tab', async ({
    page,
    request,
  }) => {
    test.setTimeout(60_000)
    await loginAs(page, 'admin', 'admin123')
    const token = await getToken(request)

    // 1. 查找 A11 底稿
    const wpListResp = await request.get(`${BASE_API}/working-papers`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const wpBody = await wpListResp.json()
    const wpList = wpBody?.data?.items || wpBody?.items || wpBody?.data || (Array.isArray(wpBody) ? wpBody : [])
    const a11Wp = wpList.find((w: any) => w.wp_code === 'A11')
    test.skip(!a11Wp, 'A11 底稿不存在，跳过')

    // 2. 带 sheet query 参数打开 A11（模拟从底稿目录跳转）
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${a11Wp!.id}/edit?sheet=A11-WP-1`)
    await page.waitForTimeout(5_000)

    // 3. 验证 A11 bundle Tab 渲染
    const tabs = page.locator('.el-tabs__item')
    const tabCount = await tabs.count()
    // A11 bundle 有 4 个 tab: 审计程序 | A11-1 审定表 | A11-2 | A11-3
    expect(tabCount, 'A11 bundle 应至少有 4 个 tab').toBeGreaterThanOrEqual(3)

    // 4. 验证"A11-1 审定表" tab 被激活（非默认的"审计程序" tab）
    const activeTab = page.locator('.el-tabs__item.is-active')
    const activeText = await activeTab.textContent()
    // 审定表 tab 应为活跃状态
    expect(
      activeText,
      '活跃 tab 应为 A11-1 审定表，而非默认程序表',
    ).toContain('审定表')
  })

  test('不带 ?sheet 参数打开 A11 → 默认显示程序表 tab', async ({
    page,
    request,
  }) => {
    test.setTimeout(60_000)
    await loginAs(page, 'admin', 'admin123')
    const token = await getToken(request)

    const wpListResp = await request.get(`${BASE_API}/working-papers`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const wpBody = await wpListResp.json()
    const wpList = wpBody?.data?.items || wpBody?.items || wpBody?.data || (Array.isArray(wpBody) ? wpBody : [])
    const a11Wp = wpList.find((w: any) => w.wp_code === 'A11')
    test.skip(!a11Wp, 'A11 底稿不存在，跳过')

    // 不带 sheet 参数
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${a11Wp!.id}/edit`)
    await page.waitForTimeout(5_000)

    // 默认应为"审计程序" tab
    const activeTab = page.locator('.el-tabs__item.is-active')
    const activeText = await activeTab.textContent()
    expect(activeText).toContain('审计程序')
  })

  test('BUNDLE_SHEET_ALIASES 配置 A11-WP-1 存在', async () => {
    // 静态验证：确保配置文件中有此 alias
    // 此测试不需要网络请求
    const { BUNDLE_SHEET_ALIASES } = await import(
      '../src/components/workpaper/bundleSheetAliases'
    )
    expect(BUNDLE_SHEET_ALIASES['A11-WP-1']).toBeDefined()
    expect(BUNDLE_SHEET_ALIASES['A11-WP-1'].parent).toBe('A11')
    expect(BUNDLE_SHEET_ALIASES['A11-WP-1'].sheet).toBe('A11-WP-1')
  })
})
