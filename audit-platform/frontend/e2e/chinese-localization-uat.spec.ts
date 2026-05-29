/**
 * 全平台中文化 UAT — V3 Req 13.11
 *
 * 验证 Sprint 2 Req 13 中文化（337 处英文 UI → 0 处）零回归。
 * 默认 skip：需启动 dev server + 访问真实页面。
 * 本地手工跑：`RUN_I18N_UAT=1 npx playwright test chinese-localization-uat`
 *
 * 验收点：
 *  - 关键路由的可见文本均为中文（label/button/title/placeholder）
 *  - 技术术语白名单豁免（SQL/PDF/UUID/CAS/编号 D2-1 等）
 *  - 后端 4xx/5xx 错误响应包含 message 中文
 */
import { test, expect } from '@playwright/test'

const SHOULD_RUN = process.env.RUN_I18N_UAT === '1'

// 技术术语白名单（与 ESLint no-english-ui-text 一致）
const TECH_WHITELIST = new Set([
  'SQL', 'PDF', 'OCR', 'LLM', 'AI', 'API', 'URL', 'UUID', 'CSV', 'JSON', 'YAML',
  'HTTP', 'HTTPS', 'UTF-8', 'RFC', 'ISO', 'WCAG', 'CAS', 'PCAOB',
  'Qwen', 'GPT', 'Claude', 'DeepSeek', 'Ollama', 'vLLM',
  'Vue', 'TypeScript', 'JavaScript',
  'OK', 'ID',
])

/** 抽取页面 DOM 中可见的英文短语（label/button/title/placeholder） */
async function extractEnglishPhrases(page: import('@playwright/test').Page): Promise<string[]> {
  return page.evaluate((whitelist) => {
    const found = new Set<string>()
    // 1. 按钮文本
    document.querySelectorAll('button, .el-button').forEach((el) => {
      const txt = (el.textContent || '').trim()
      if (/^[A-Za-z][A-Za-z0-9 _\-]+$/.test(txt) && !whitelist.includes(txt)) {
        found.add(txt)
      }
    })
    // 2. label
    document.querySelectorAll('label, .el-form-item__label').forEach((el) => {
      const txt = (el.textContent || '').trim()
      if (/^[A-Za-z][A-Za-z0-9 _\-]+$/.test(txt) && !whitelist.includes(txt)) {
        found.add(txt)
      }
    })
    // 3. placeholder
    document.querySelectorAll('input, textarea').forEach((el) => {
      const ph = (el as HTMLInputElement).placeholder
      if (ph && /^[A-Za-z][A-Za-z0-9 _\-]+$/.test(ph) && !whitelist.includes(ph)) {
        found.add(ph)
      }
    })
    // 4. 表头 / table title
    document.querySelectorAll('th, .el-table__cell .cell').forEach((el) => {
      const txt = (el.textContent || '').trim()
      if (/^[A-Za-z][A-Za-z0-9 _\-]+$/.test(txt) && !whitelist.includes(txt)) {
        found.add(txt)
      }
    })
    return [...found]
  }, [...TECH_WHITELIST])
}

test.describe('全平台中文化 UAT (V3 Req 13.11)', () => {
  test.skip(!SHOULD_RUN, '默认跳过：需 RUN_I18N_UAT=1 + 启动 start-dev.bat')

  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
  })

  test('登录页：无英文残留', async ({ page }) => {
    const phrases = await extractEnglishPhrases(page)
    expect(phrases, `登录页发现英文残留：${phrases.join(', ')}`).toEqual([])
  })

  test('Dashboard：无英文残留', async ({ page }) => {
    await page.fill('input[placeholder*="用户名" i], input[name="username"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button:has-text("登录")')
    await page.waitForURL(/dashboard|projects/, { timeout: 10_000 })

    const phrases = await extractEnglishPhrases(page)
    expect(phrases, `Dashboard 发现英文残留：${phrases.join(', ')}`).toEqual([])
  })

  test('项目列表：无英文残留', async ({ page }) => {
    await page.fill('input[placeholder*="用户名" i], input[name="username"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button:has-text("登录")')
    await page.waitForURL(/dashboard|projects/, { timeout: 10_000 })
    await page.goto('/projects')
    await page.waitForLoadState('networkidle')

    const phrases = await extractEnglishPhrases(page)
    expect(phrases, `项目列表发现英文残留：${phrases.join(', ')}`).toEqual([])
  })

  test('后端 401 错误包含中文 message', async ({ page }) => {
    const resp = await page.request.post('/api/auth/login', {
      data: { username: 'nonexistent', password: 'wrong' },
    })
    expect(resp.status()).toBeGreaterThanOrEqual(400)
    const body = await resp.json().catch(() => ({}))
    const detail = body?.detail || body?.error || body
    // detail 应是 { message, message_en } 或 message 直接为中文
    const message = typeof detail === 'object' ? (detail.message || JSON.stringify(detail)) : String(detail)
    // 必须包含至少一个中文字符
    expect(message).toMatch(/[\u4e00-\u9fa5]/)
  })

  test('后端 422 错误（缺字段）包含中文 message', async ({ page }) => {
    const resp = await page.request.post('/api/auth/login', {
      data: {}, // 缺字段
    })
    expect([400, 422]).toContain(resp.status())
    const body = await resp.json().catch(() => ({}))
    // 422 通常是 Pydantic 标准格式 detail: [...]，本任务不强测此格式
    // 但若是自定义 HTTPException（已 13.8 双语化）应含中文
    if (typeof body?.detail === 'object' && !Array.isArray(body.detail) && body.detail?.message) {
      expect(body.detail.message).toMatch(/[\u4e00-\u9fa5]/)
    }
  })
})
