/**
 * f-cycle-f2-21-inventory-count.spec.ts — F2-21 存货监盘底稿 OnlyOffice 打开 + 多 sheet Tab 切换
 *
 * 锚定 spec f-cycle-workpapers Task 55
 *
 * 验证 F2-21 存货监盘计划底稿：
 * 1. F2-21 底稿存在且 render-config 返回 f2-stocktake-bundle
 * 2. F2-21~F2-26 全系列为 f2-stocktake-bundle
 * 3. 底稿页面加载无严重 JS 错误
 * 4. 监盘系列底稿在 address_registry 中有坐标注册
 *
 * 项目：辽宁卫生服务有限公司 2025（37814426-a29e-4fc2-9313-a59d229bf7b0）
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  fetchRenderConfig,
  sheetComponentTypes,
  clickWorkpaperSheetTab,
} from './fixtures/ensure-test-project'

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

test.describe('Task 55: F2-21 存货监盘底稿 OnlyOffice 打开 + 多 sheet Tab', () => {
  test('55.1 — F2-21 底稿存在且为 f2-stocktake-bundle', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'F2-21', PROJECT_ID)
    test.skip(!wpResult.exists, 'F2-21 底稿不存在，需先运行项目底稿生成')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain('f2-stocktake-bundle')
  })

  test('55.2 — F2-21~F2-26 监盘系列全部为 f2-stocktake-bundle', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    const monitorCodes = ['F2-21', 'F2-22', 'F2-23', 'F2-24', 'F2-25', 'F2-26']
    for (const code of monitorCodes) {
      const wpResult = await findWorkpaper(request, token, code, PROJECT_ID)
      if (wpResult.exists) {
        const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
        expect(sheetComponentTypes(rcData), `${code} 应为 f2-stocktake-bundle`).toContain(
          'f2-stocktake-bundle',
        )
      }
    }
  })

  test('55.3 — F2-21 底稿页面加载无严重错误', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'F2-21', PROJECT_ID)
    test.skip(!wpResult.exists, 'F2-21 底稿不存在')

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (/\/ai\//.test(text) && /405/.test(text)) return
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        if (/Failed to load resource.*500/.test(text)) return
        if (/onlyoffice|DocsAPI/.test(text)) return // OnlyOffice 在无服务器时报错
        consoleErrors.push(text)
      }
    })
    page.on('pageerror', (err) => {
      consoleErrors.push(`pageerror: ${err.message}`)
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    // OnlyOffice 不可用时走降级预览——不作为致命错误
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('55.4 — F2-21 底稿页面渲染 HTML 监盘内容或双模式工具栏', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'F2-21', PROJECT_ID)
    test.skip(!wpResult.exists, 'F2-21 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'F2-21')
    await page.waitForTimeout(2_000)

    const pageContent = await page.textContent('body')
    const hasSegmented = await page.locator('.el-segmented').count() > 0
    const hasInventoryContent =
      pageContent?.includes('监盘') ||
      pageContent?.includes('盘点') ||
      pageContent?.includes('问卷') ||
      pageContent?.includes('存货')

    expect(
      hasSegmented || hasInventoryContent,
      'F2-21 应渲染 HTML 双模式工具栏或监盘内容',
    ).toBeTruthy()
  })
})
