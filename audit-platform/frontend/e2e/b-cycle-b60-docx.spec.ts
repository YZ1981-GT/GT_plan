/**
 * b-cycle-b60-docx.spec.ts — B60 docx 预览/OnlyOffice 编辑
 *
 * 锚定 spec b-cycle-workpapers Task 53
 *
 * 验证 B60 总体审计策略及具体审计计划 docx：
 * 1. 底稿页面正常加载（word-template componentType）
 * 2. docx 预览或 OnlyOffice 编辑器加载（或降级为下载按钮）
 * 3. 基本 UI 元素验证（标题、下载按钮）
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

test.describe('Task 53: B60 docx 预览/OnlyOffice 编辑', () => {
  test('53.1 — B60 底稿页面加载（word-template 渲染）', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'B60', PROJECT_ID)
    test.skip(!wpResult.exists, 'B60 底稿不存在，需先运行项目底稿生成')

    // 收集 console errors
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (/\/ai\//.test(text) && /405/.test(text)) return
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        if (/Failed to load resource.*500/.test(text)) return
        // OnlyOffice 连接失败是正常降级场景
        if (/onlyoffice|docsapi/i.test(text)) return
        consoleErrors.push(text)
      }
    })
    page.on('pageerror', (err) => {
      // OnlyOffice JS API 加载失败不应视为错误（降级处理）
      if (/DocsAPI|onlyoffice/i.test(err.message)) return
      consoleErrors.push(`pageerror: ${err.message}`)
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)

    // 等待编辑器容器渲染
    await page.waitForSelector(
      '.gt-wp-editor, .gt-wp-editor-loading, .workpaper-word-editor, .onlyoffice-editor',
      { timeout: 15_000 },
    )
    await page.waitForTimeout(5_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 20_000 })
    }

    // 验证无 ErrorBoundary
    const errorBoundary = page.locator('.gt-error-boundary, [class*="error-boundary"]')
    expect(await errorBoundary.count(), 'ErrorBoundary 不应出现').toBe(0)

    // 验证无严重 console errors（排除 OnlyOffice 降级）
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('53.2 — B60 docx 预览或 OnlyOffice 编辑器加载（含降级验证）', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'B60', PROJECT_ID)
    test.skip(!wpResult.exists, 'B60 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(8_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 20_000 })
    }

    // B60 是 word-template 类型，应出现以下之一：
    // 1. OnlyOffice 编辑器 iframe（onlyoffice-editor / iframe[src*=onlyoffice]）
    // 2. 降级预览（VueOfficeDocx / deliverable-preview）
    // 3. 降级下载界面（下载按钮）

    const onlyofficeEditor = page.locator(
      '.onlyoffice-editor, iframe[src*="onlyoffice"], #onlyoffice-container, [class*="only-office"]',
    )
    const degradedPreview = page.locator(
      '.deliverable-preview, .vue-office-docx, [class*="docx-preview"]',
    )
    const downloadArea = page.locator(
      'button:has-text("下载"), .wp-popup-docx-editor__download, [class*="download"]',
    )

    const hasOnlyOffice = (await onlyofficeEditor.count()) > 0
    const hasPreview = (await degradedPreview.count()) > 0
    const hasDownload = (await downloadArea.count()) > 0

    // 至少应有一种展示方式（编辑器/预览/下载）
    expect(
      hasOnlyOffice || hasPreview || hasDownload,
      'B60 应显示 OnlyOffice 编辑器、docx 预览、或降级下载按钮之一',
    ).toBeTruthy()
  })

  test('53.3 — B60 基本 UI 元素验证（标题、下载按钮）', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'B60', PROJECT_ID)
    test.skip(!wpResult.exists, 'B60 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 20_000 })
    }

    // 验证页面标题/面包屑中包含 B60 相关文本
    const pageText = await page.locator('body').textContent()
    const hasB60Context =
      pageText?.includes('B60') ||
      pageText?.includes('总体审计策略') ||
      pageText?.includes('审计计划')
    expect(hasB60Context, '页面应包含 B60 相关上下文文本').toBeTruthy()

    // 验证下载/导出按钮存在（word-template 类组件一般有下载功能）
    const downloadBtn = page.locator('button').filter({ hasText: /下载|导出|模板/ }).first()
    const toolbarBtn = page.locator('.el-button, button').filter({ hasText: /下载/ })
    const hasDownloadButton = (await downloadBtn.count()) > 0 || (await toolbarBtn.count()) > 0

    // 下载按钮不是强制要求（OnlyOffice 编辑模式下可能隐藏），但至少页面无报错
    if (hasDownloadButton) {
      await expect(downloadBtn.or(toolbarBtn.first()).first()).toBeVisible()
    }
  })

  test('53.4 — B60 render-config + 模板下载 API 验证', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'B60', PROJECT_ID)
    test.skip(!wpResult.exists, 'B60 底稿不存在')

    // 验证 render-config 返回 word-template
    const rcResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}/render-config`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)
    const rcBody = await rcResp.json()
    const rcData = rcBody?.data || rcBody
    expect(rcData.component_type || rcData.componentType).toBe('word-template')

    // 验证 prefilled-download 端点（B60 已注册到 DOCX_CONFIGS）
    const dlResp = await request.get(
      `/api/projects/${PROJECT_ID}/wp-templates/B60/prefilled-download`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(dlResp.status()).toBe(200)
    const contentType = dlResp.headers()['content-type'] || ''
    expect(contentType).toContain('wordprocessingml.document')
    const body = await dlResp.body()
    expect(body.length, 'B60 docx 模板应有实际内容').toBeGreaterThan(1000)

    // 验证 Content-Disposition 正确
    const disposition = dlResp.headers()['content-disposition'] || ''
    expect(disposition).toContain('attachment')
  })

  test('53.5 — B60 OnlyOffice config 端点验证（如可用）', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'B60', PROJECT_ID)
    test.skip(!wpResult.exists, 'B60 底稿不存在')

    // 验证 OnlyOffice 配置端点（可能 500 如果 OnlyOffice 未部署）
    const ooResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}/onlyoffice/config`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    // OnlyOffice 可能未部署（500）或底稿无已上传文件（404）
    // 200 = OnlyOffice 可用；其他状态码 = 降级场景
    expect([200, 404, 500]).toContain(ooResp.status())

    if (ooResp.status() === 200) {
      const ooBody = await ooResp.json()
      const ooData = ooBody?.data || ooBody
      // config 应包含 document.url 和 editorConfig
      expect(ooData.document || ooData.documentType).toBeTruthy()
    }
  })
})
