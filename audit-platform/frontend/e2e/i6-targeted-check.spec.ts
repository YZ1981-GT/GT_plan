/**
 * I6-4 研发费用针对性检查表 — Playwright E2E 烟雾测试
 *
 * 验证结构化 HTML 视图可打开，且呈现 Excel 对齐的五段式骨架与 VR-I6-01 联动条。
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

const TEST_PROJECT_ID = process.env.TEST_PROJECT_ID_FIX_I6
  || process.env.TEST_PROJECT_ID
  || '2aa00f57-1df4-4fe8-9840-2d65d0fd8749'
const API_BASE = process.env.PLAYWRIGHT_API_BASE_URL || 'http://127.0.0.1:9980'

async function loginAs(page: Page, request: APIRequestContext): Promise<string> {
  const resp = await request.post(`${API_BASE}/api/auth/login`, {
    data: { username: 'admin', password: 'admin123' },
    timeout: 20_000,
  })
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  if (token) {
    await page.goto('/')
    await page.evaluate((t: string) => {
      window.sessionStorage.setItem('token', t)
      window.localStorage.setItem('token', t)
    }, token)
  }
  return token as string
}

async function resolveI6Workpaper(request: APIRequestContext, token: string): Promise<{ exists: boolean; wpId: string }> {
  const fallbackWpId = process.env.I6_E2E_WP_ID
  if (fallbackWpId) {
    return { exists: true, wpId: fallbackWpId }
  }
  try {
    const resp = await request.get(`${API_BASE}/api/acnr/resolve-instance`, {
      params: {
        project_id: TEST_PROJECT_ID,
        parent: 'I6',
        sheet_code: 'I6',
      },
      headers: { Authorization: `Bearer ${token}` },
    })
    if (resp.status() !== 200) return { exists: false, wpId: '' }
    const body = await resp.json()
    if (body?.found && body.wp_id) {
      return { exists: true, wpId: String(body.wp_id) }
    }
    return { exists: false, wpId: '' }
  } catch {
    return { exists: false, wpId: '' }
  }
}

function shouldIgnoreError(text: string): boolean {
  return (
    (/\/ai\//.test(text) && /405/.test(text)) ||
    /net::ERR_|Failed to fetch|NetworkError/.test(text) ||
    /onlyoffice|DocsAPI/.test(text) ||
    /ResizeObserver/.test(text) ||
    /favicon/.test(text)
  )
}

async function openI64Sheet(page: Page, wpId: string): Promise<void> {
  await page.goto(`/projects/${TEST_PROJECT_ID}/workpapers/${wpId}/edit?sheet=I6-4`)
  await page.waitForTimeout(4_000)

  const sheetTab = page.locator('[data-sheet-code="I6-4"], .el-tabs__item').filter({ hasText: /I6-4|针对性/ }).first()
  if (await sheetTab.isVisible({ timeout: 6_000 }).catch(() => false)) {
    await sheetTab.click()
    await page.waitForTimeout(2_000)
  } else {
    const chipOrLink = page.locator('text=I6-4').first()
    if (await chipOrLink.isVisible({ timeout: 4_000 }).catch(() => false)) {
      await chipOrLink.click()
      await page.waitForTimeout(2_000)
    }
  }
}

test.describe('I6-4 研发费用针对性检查表（烟雾测试）', () => {
  test('I6-4 页面可打开并呈现测试目标与抽凭表头', async ({ page, request }) => {
    test.setTimeout(90_000)
    const token = await loginAs(page, request)
    const wpResult = await resolveI6Workpaper(request, token)
    test.skip(!wpResult.exists, 'I6 底稿不存在或项目未配置')

    await openI64Sheet(page, wpResult.wpId)

    const body = await page.textContent('body')
    expect(body).toBeTruthy()

    const hasTargetedShell =
      (await page.locator('.i6-targeted-check').count()) > 0
      || (body || '').includes('研发费用针对性检查表')
      || (body || '').includes('I6-4')
    expect(hasTargetedShell).toBe(true)

    const hasObjectives =
      (body || '').includes('一、测试目标')
      || (body || '').includes('发生')
      || (body || '').includes('分类')
    expect(hasObjectives).toBe(true)

    const hasSamplingSection =
      (body || '').includes('样本选取')
      || (body || '').includes('抽凭引擎')
      || (body || '').includes('测试原因')
    expect(hasSamplingSection).toBe(true)

    const hasLinkageBar =
      (body || '').includes('VR-I6-01')
      || (body || '').includes('I2 资本化数据未同步')
    expect(hasLinkageBar).toBe(true)
  })

  test('I6-4 页面无致命 console 错误', async ({ page, request }) => {
    test.setTimeout(90_000)
    const token = await loginAs(page, request)
    const wpResult = await resolveI6Workpaper(request, token)
    test.skip(!wpResult.exists, 'I6 底稿不存在或项目未配置')

    const errors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !shouldIgnoreError(msg.text())) {
        errors.push(msg.text())
      }
    })

    await openI64Sheet(page, wpResult.wpId)

    const fatal = errors.filter((e) =>
      /TypeError|ReferenceError|Cannot read|is not a function|Unhandled/.test(e),
    )
    expect(fatal).toEqual([])
  })
})
