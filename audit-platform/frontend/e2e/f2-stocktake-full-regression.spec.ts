/**
 * f2-stocktake-full-regression.spec.ts — F2 监盘全量回归 E2E
 *
 * 验证点：
 *   1. F2-21/F2-22/F2-23 三个文本 sheet 加载不报错
 *   2. OCR 按钮可见（F2-22/F2-23 附件OCR填叙述）
 *   3. 双模式（HTML/OO）切换不崩
 *   4. F2-21 迁移banner逻辑（有旧数据时可见）
 *   5. F2-24~26 混合 Tab 加载
 *
 * 注意：此文件为骨架/占位，需运行环境（后端 9980 + 前端 3030）
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  fetchRenderConfig,
  sheetComponentTypes,
  clickWorkpaperSheetTab,
  expectHtmlDualModeOrContent,
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

// ─── 1. 三个文本 sheet 加载不报错 ───────────────────────────────

test.describe('F2 监盘全量回归 — 文本 sheet 加载', () => {
  const TEXT_SHEETS = [
    { code: 'F2-21', hint: /盘点|监盘|问卷|仓库/ },
    { code: 'F2-22', hint: /监盘|计划|程序|观察/ },
    { code: 'F2-23', hint: /监盘|小结|结论|覆盖/ },
  ]

  for (const sheet of TEXT_SHEETS) {
    test(`${sheet.code} — 加载无严重错误`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page, 'admin', 'admin123')
      const token = await getToken(request)
      const wp = await findWorkpaper(request, token, sheet.code, PROJECT_ID)
      test.skip(!wp.exists, `${sheet.code} 底稿不存在`)

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
      page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`))

      await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp.wpId}/edit`)
      await page.waitForTimeout(4_000)
      await clickWorkpaperSheetTab(page, sheet.code)
      await page.waitForTimeout(2_000)

      const critical = consoleErrors.filter((e) =>
        /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
      )
      expect(critical, `严重 JS 错误:\n${critical.join('\n')}`).toHaveLength(0)
      await expectHtmlDualModeOrContent(page, sheet.hint)
    })
  }
})

// ─── 2. OCR 按钮可见（F2-22/F2-23） ────────────────────────────

test.describe('F2 监盘全量回归 — OCR 按钮可见', () => {
  for (const code of ['F2-22', 'F2-23'] as const) {
    test(`${code} — 📎 附件OCR按钮存在`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page, 'admin', 'admin123')
      const token = await getToken(request)
      const wp = await findWorkpaper(request, token, code, PROJECT_ID)
      test.skip(!wp.exists, `${code} 底稿不存在`)

      await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp.wpId}/edit`)
      await page.waitForTimeout(4_000)
      await clickWorkpaperSheetTab(page, code)
      await page.waitForTimeout(2_000)

      // OCR 按钮文案
      const ocrBtn = page.locator('button', { hasText: /附件OCR/ })
      await expect(ocrBtn.first()).toBeVisible({ timeout: 10_000 })
    })
  }
})

// ─── 3. 双模式切换不崩 ─────────────────────────────────────────

test.describe('F2 监盘全量回归 — 双模式切换', () => {
  test('F2-21 — HTML↔OO 双模式切换无崩溃', async ({ page, request }) => {
    test.setTimeout(120_000)
    await loginAs(page, 'admin', 'admin123')
    const token = await getToken(request)
    const wp = await findWorkpaper(request, token, 'F2-21', PROJECT_ID)
    test.skip(!wp.exists, 'F2-21 不存在')

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (/\/ai\//.test(text) && /405/.test(text)) return
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        if (/onlyoffice|DocsAPI/.test(text)) return
        consoleErrors.push(text)
      }
    })
    page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`))

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 初始应为 HTML 模式（结构化视图）
    const segmented = page.locator('.el-segmented')
    await expect(segmented.first()).toBeVisible({ timeout: 15_000 })

    // 尝试切换到 OO 模式
    const ooOption = segmented.locator('text=在线编辑')
    if (await ooOption.isVisible()) {
      await ooOption.click()
      await page.waitForTimeout(3_000)
    }

    // 切回 HTML
    const htmlOption = segmented.locator('text=结构化视图')
    if (await htmlOption.isVisible()) {
      await htmlOption.click()
      await page.waitForTimeout(2_000)
    }

    const critical = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(critical, `双模式切换后严重错误:\n${critical.join('\n')}`).toHaveLength(0)
  })
})

// ─── 4. F2-24~26 混合 Tab 加载 ──────────────────────────────────

test.describe('F2 监盘全量回归 — 混合 Tab 加载', () => {
  const MIXED_SHEETS = [
    { code: 'F2-24', hint: /核对|账面|ERP|差异/ },
    { code: 'F2-25', hint: /抽盘|样本|盘点/ },
    { code: 'F2-26', hint: /倒轧|调节|入库|出库/ },
  ]

  for (const sheet of MIXED_SHEETS) {
    test(`${sheet.code} — 混合表加载不报错`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page, 'admin', 'admin123')
      const token = await getToken(request)
      const wp = await findWorkpaper(request, token, sheet.code, PROJECT_ID)
      test.skip(!wp.exists, `${sheet.code} 底稿不存在`)

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
      page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`))

      await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp.wpId}/edit`)
      await page.waitForTimeout(4_000)
      await clickWorkpaperSheetTab(page, sheet.code)
      await page.waitForTimeout(3_000)

      const critical = consoleErrors.filter((e) =>
        /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
      )
      expect(critical, `${sheet.code} 严重错误:\n${critical.join('\n')}`).toHaveLength(0)
      await expectHtmlDualModeOrContent(page, sheet.hint)
    })
  }
})

// ─── 5. render-config 全sheet一致性 ─────────────────────────────

test.describe('F2 监盘全量回归 — 契约一致性', () => {
  test('F2-21~F2-26 全部映射到 f2-stocktake-bundle', async ({ request }) => {
    test.setTimeout(45_000)
    const token = await getToken(request)
    for (const code of ['F2-21', 'F2-22', 'F2-23', 'F2-24', 'F2-25', 'F2-26']) {
      const wp = await findWorkpaper(request, token, code, PROJECT_ID)
      if (!wp.exists) continue
      const data = await fetchRenderConfig(request, token, wp.wpId!)
      expect(sheetComponentTypes(data), `${code} componentType`).toContain('f2-stocktake-bundle')
    }
  })
})
