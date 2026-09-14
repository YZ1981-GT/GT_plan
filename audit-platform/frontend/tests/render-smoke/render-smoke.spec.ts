/**
 * render-smoke.spec.ts — render 冒烟测试集（数据驱动，按 wp_code 参数化）
 *
 * 每个 wp_code：
 *   1. 登录（admin/admin123）
 *   2. 导航到底稿
 *   3. 断言 console error 数量 = 0
 *   4. 断言关键区块选择器存在（.gt-wp-root 或等价渲染容器）
 *
 * 失败时报告 wp_code + 错误摘要。
 *
 * Feature: platform-global-hardening
 * Requirements: 3.5, 3.6
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { getWpCodeList, type WpCodeEntry } from './generate-wp-list'

// ─── 配置 ────────────────────────────────────────────────────────────────────

const LOGIN_USERNAME = 'admin'
const LOGIN_PASSWORD = 'admin123'
const BACKEND_BASE = process.env.RENDER_SMOKE_BACKEND_URL || 'http://localhost:9980'

/** 关键区块选择器 — 底稿渲染成功的标志 */
const KEY_SELECTORS = [
  '.gt-wp-root',
  '.workpaper-editor',
  '.gt-workpaper-shell',
  '[data-component-type]',
  '.el-tabs',           // 多 sheet 底稿的 tab 容器
  '.gt-onlyoffice',    // OnlyOffice 渲染容器
]

/** console error 过滤白名单（已知无害噪声） */
const NOISE_PATTERNS = [
  /Failed to fetch/i,                    // SSE 断连
  /ERR_CONNECTION_REFUSED/i,             // 后端未响应的网络错误
  /ResizeObserver/i,                     // 浏览器 resize observer 限制
  /favicon\.ico/i,                       // favicon 404
  /\/api\/.*events\?topic=/i,            // SSE 事件流断连
  /net::ERR_/i,                          // 网络层错误
]

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

/**
 * 通过 API 登录获取 token，设置到 page storage
 */
async function login(page: Page): Promise<string> {
  const resp = await page.request.post('/api/auth/login', {
    data: { username: LOGIN_USERNAME, password: LOGIN_PASSWORD },
  })
  expect(resp.ok(), `登录请求失败: ${resp.status()}`).toBeTruthy()

  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  expect(token, '登录响应未包含 token').toBeTruthy()

  // 注入 token 到 session/localStorage
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)

  return token
}

/**
 * 查找指定 wp_code 对应的 workpaper ID（从项目底稿列表）
 */
async function findWpId(
  request: APIRequestContext,
  token: string,
  wpCode: string,
  projectId: string,
): Promise<string | null> {
  const resp = await request.get(
    `${BACKEND_BASE}/api/projects/${projectId}/working-papers`,
    { headers: { Authorization: `Bearer ${token}` } },
  )
  if (!resp.ok()) return null

  const body = await resp.json()
  const list: any[] = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])

  const wp = list.find(
    (w: any) => (w.wp_code || '').toUpperCase() === wpCode.toUpperCase(),
  )
  return wp?.id || null
}

/**
 * 获取第一个可用项目 ID
 */
async function getFirstProjectId(
  request: APIRequestContext,
  token: string,
): Promise<string | null> {
  const resp = await request.get(`${BACKEND_BASE}/api/projects`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null

  const body = await resp.json()
  const list: any[] = body?.data?.items || body?.data || body?.items || (Array.isArray(body) ? body : [])
  return list[0]?.id || null
}

/**
 * 判断 console error 是否为已知噪声
 */
function isNoiseError(text: string): boolean {
  return NOISE_PATTERNS.some((pattern) => pattern.test(text))
}

// ─── 测试集 ──────────────────────────────────────────────────────────────────

const wpCodeList = getWpCodeList()

test.describe('render 冒烟测试集', () => {
  let token: string
  let projectId: string | null

  test.beforeAll(async ({ request }) => {
    // 通过 API 登录获取 token
    const resp = await request.post(`${BACKEND_BASE}/api/auth/login`, {
      data: { username: LOGIN_USERNAME, password: LOGIN_PASSWORD },
    })
    expect(resp.ok(), 'beforeAll 登录失败').toBeTruthy()
    const body = await resp.json()
    token = body.data?.access_token ?? body.access_token

    // 获取可用项目
    projectId = await getFirstProjectId(request, token)
  })

  for (const entry of wpCodeList) {
    test(`[${entry.wpCode}] 渲染无 console error 且关键区块存在`, async ({ page, request }) => {
      test.setTimeout(45_000)

      // 跳过条件：无可用项目
      if (!projectId) {
        test.skip(true, '无可用项目，跳过 render 冒烟')
        return
      }

      // 登录
      await login(page)

      // 收集 console errors
      const consoleErrors: string[] = []
      page.on('console', (msg) => {
        if (msg.type() === 'error') {
          const text = msg.text()
          if (!isNoiseError(text)) {
            consoleErrors.push(text)
          }
        }
      })

      // 查找 wp_id
      const wpId = await findWpId(request, token, entry.wpCode, projectId)
      if (!wpId) {
        test.skip(true, `项目中未找到 wp_code=${entry.wpCode} 的底稿`)
        return
      }

      // 导航到底稿
      await page.goto(`/workpapers/${wpId}`)

      // 等待底稿渲染完成（最多 20s）
      await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {
        // networkidle 超时不直接失败，继续检查
      })

      // 额外等待确保异步渲染完成
      await page.waitForTimeout(2000)

      // 断言 1：console error 数量为 0
      if (consoleErrors.length > 0) {
        const summary = consoleErrors
          .slice(0, 5)
          .map((e, i) => `  ${i + 1}. ${e.slice(0, 200)}`)
          .join('\n')
        const extra = consoleErrors.length > 5
          ? `\n  ... 及另外 ${consoleErrors.length - 5} 条错误`
          : ''

        expect.soft(
          consoleErrors.length,
          `[${entry.wpCode}] 存在 ${consoleErrors.length} 条 console error:\n${summary}${extra}`,
        ).toBe(0)
      }

      // 断言 2：至少一个关键区块选择器存在
      let hasKeyBlock = false
      for (const selector of KEY_SELECTORS) {
        const count = await page.locator(selector).count()
        if (count > 0) {
          hasKeyBlock = true
          break
        }
      }

      expect(
        hasKeyBlock,
        `[${entry.wpCode}] 未找到任何关键区块选择器: ${KEY_SELECTORS.join(', ')}`,
      ).toBeTruthy()
    })
  }
})
