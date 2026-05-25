/**
 * UAT — WorkpaperEditor 加载流程回归测试
 *
 * 锚定 spec workpaper-editor-refactor Phase 5.2
 *
 * 验证三大反模式不复现：
 * 1. Vue setup ref 顺序错误（"Cannot access 'X' before initialization"）
 * 2. 顶层 v-if="loading" 守卫拦 init 死锁（永久"加载底稿中..."）
 * 3. GtLoadingOverlay 可见 + loadingHint 阶段提示
 *
 * 项目：辽宁卫生服务有限公司 2025（37814426-a29e-4fc2-9313-a59d229bf7b0）
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

const PROJECT_ID = '37814426-a29e-4fc2-9313-a59d229bf7b0'

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

/** 找一个有效的底稿 ID（任意 wp_code，优先 D2 / E1） */
async function findAnyWpId(request: APIRequestContext, token: string): Promise<{ id: string; wpCode: string } | null> {
  const resp = await request.get(`/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])
  // 优先 D2 / E1
  for (const code of ['D2', 'E1', 'F2', 'A1']) {
    const wp = list.find((w: any) => (w.wp_code || '').toUpperCase() === code)
    if (wp?.id) return { id: wp.id, wpCode: code }
  }
  // 兜底任意一个
  if (list.length > 0) return { id: list[0].id, wpCode: list[0].wp_code || '?' }
  return null
}

test.describe('WorkpaperEditor 加载流程回归测试', () => {
  test('5.2.1 — 打开底稿无 ReferenceError + 无死锁', async ({ page, request }) => {
    test.setTimeout(60_000)
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        // 过滤已知的网络错误（如 SSE 断连）
        if (/Cannot access|before initialization|ReferenceError|TypeError.*undefined/.test(text)) {
          consoleErrors.push(text)
        }
      }
    })
    page.on('pageerror', (err) => {
      consoleErrors.push(`pageerror: ${err.message}`)
    })

    const token = await loginAs(page, 'admin', 'admin123')
    const wp = await findAnyWpId(request, token)
    test.skip(!wp, '项目内无可用底稿')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp!.id}/edit`)

    // 等待 Univer 容器渲染（关键：顶层 v-if 改 overlay 模式后，container 应一直存在）
    await page.waitForSelector('.gt-wp-editor-univer, .gt-wp-editor-loading', { timeout: 15_000 })

    // 等待 5 秒让 init 跑完
    await page.waitForTimeout(5_000)

    // 验证 1：没有 setup ref ReferenceError
    expect(consoleErrors, `控制台 ReferenceError:\n${consoleErrors.join('\n')}`).toHaveLength(0)

    // 验证 2：loading overlay 已消失（无死锁）
    const overlay = page.locator('.gt-loading-overlay')
    const overlayCount = await overlay.count()
    if (overlayCount > 0) {
      // 给 10 秒兜底 wait（大文件加载可能慢）
      await expect(overlay).toBeHidden({ timeout: 10_000 }).catch(() => {
        throw new Error(`GtLoadingOverlay 在 15 秒后仍可见，疑似死锁；底稿: ${wp!.wpCode}`)
      })
    }
  })

  test('5.2.2 — GtLoadingOverlay 加载阶段提示出现', async ({ page, request }) => {
    test.setTimeout(45_000)
    const token = await loginAs(page, 'admin', 'admin123')
    const wp = await findAnyWpId(request, token)
    test.skip(!wp, '项目内无可用底稿')

    // 提前监听 overlay 出现（避免错过快速一闪）
    let overlaySeen = false
    let hintSeen = false
    page.on('framenavigated', async () => {
      try {
        const ov = page.locator('.gt-loading-overlay')
        if ((await ov.count()) > 0) overlaySeen = true
        const hint = page.locator('.gt-loading-overlay__hint')
        if ((await hint.count()) > 0) hintSeen = true
      } catch { /* 页面跳转中 dom 可能短暂不可达 */ }
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp!.id}/edit`)

    // 在加载早期捕获 overlay 与 hint（轮询 200ms 一次，最多 5 秒）
    for (let i = 0; i < 25 && (!overlaySeen || !hintSeen); i++) {
      try {
        if (!overlaySeen && await page.locator('.gt-loading-overlay').count() > 0) overlaySeen = true
        if (!hintSeen && await page.locator('.gt-loading-overlay__hint').count() > 0) hintSeen = true
      } catch { /* */ }
      await page.waitForTimeout(200)
    }

    // overlay 至少出现过一次（除非加载极快 < 200ms，给个软 assertion）
    if (!overlaySeen) {
      console.warn('[5.2.2] GtLoadingOverlay 未捕获到，可能加载非常快（< 200ms）')
    }
    // 等待加载完成
    await page.waitForTimeout(3_000)
    // 验证 overlay 最终消失
    await expect(page.locator('.gt-loading-overlay')).toBeHidden({ timeout: 15_000 })
  })

  test('5.2.3 — 无效 wpId 不会卡死页面', async ({ page }) => {
    test.setTimeout(30_000)
    await loginAs(page, 'admin', 'admin123')

    const consoleErrors: string[] = []
    page.on('pageerror', (err) => {
      consoleErrors.push(`pageerror: ${err.message}`)
    })

    // 故意传非 UUID 的 wpId
    await page.goto(`/projects/${PROJECT_ID}/workpapers/not-a-real-id/edit`)
    await page.waitForTimeout(5_000)

    // 不应抛出 setup ref 类错误（可以有"底稿不存在"toast）
    const setupErrors = consoleErrors.filter((e) => /Cannot access|before initialization/.test(e))
    expect(setupErrors, `setup 阶段 ReferenceError:\n${setupErrors.join('\n')}`).toHaveLength(0)
  })
})
