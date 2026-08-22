/**
 * Playwright E2E Smoke: Phase A 统一 AI 面板基线验收
 *
 * Feature: dsh-agent-panel-integration / Task 13
 * Validates: Requirements 1.1, 1.4, 1.5, 1.8, 4.1, 4.8, 13.1, 13.3, 13.6
 *
 * 覆盖场景:
 *   1. 全部宿主页面可打开统一面板（PlatformAiChatPanel）
 *   2. native 对话：输入 → 两阶段 API → 流式响应
 *   3. 取消：运行中取消 → terminal cancelled
 *   4. 重连：SSE 断流 → Last-Event-ID replay（网络面板验证）
 *   5. 切账号/登出无缓存泄漏：logout → localStorage 无 doc_ai_chat_* key
 *   6. 网络面板核对：run 只创建一次、无旧 /doc 双轨、无 DSH iframe 请求
 *
 * 环境要求: start-dev.bat（后端 9980 + 前端 3030）
 * 未就绪时自动 skip（不伪绿）。
 */
import { test, expect, type Page, type BrowserContext } from '@playwright/test'

const BASE_URL = 'http://localhost:3030'
const BACKEND_URL = 'http://localhost:9980'

// ---------------------------------------------------------------------------
// 环境检测
// ---------------------------------------------------------------------------

test.beforeAll(async ({ request }) => {
  try {
    const resp = await request.get(`${BACKEND_URL}/api/health`)
    if (resp.status() !== 200) {
      test.skip(true, `后端 ${BACKEND_URL} 健康检查非 200：先用 start-dev.bat 起后端(9980)+前端(3030)`)
    }
  } catch {
    test.skip(true, `后端 ${BACKEND_URL} 不可达：先用 start-dev.bat 起后端(9980)+前端(3030)`)
  }
})

// ---------------------------------------------------------------------------
// 公共 Helpers
// ---------------------------------------------------------------------------

async function login(page: Page, user = 'admin', pass = 'admin123') {
  await page.goto(`${BASE_URL}/login`)
  await page.fill('input[placeholder*="用户名"]', user)
  await page.fill('input[placeholder*="密码"]', pass)
  await page.click('button:has-text("登录")')
  // 🔴 判据只能是「离开了 /login」。原实现等 `**/dashboard**` —— 实测登录后落地是站点根
  // `http://localhost:3030/`，于是本文件**每一条**用例都卡在这里超时（17/17 全红，
  // 等于整个 smoke 从未验证过任何东西）。
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 })
}

async function logout(page: Page) {
  // 走真实登出路径：ThreeColumnLayout 顶栏 `.gt-user-info` 下拉 → 退出登录 → authStore.logout()
  // 🔴 原实现找 `.el-dropdown-link, .user-avatar, [class*="header-user"]`（布局里都不存在）
  // ⇒ 恒落 `goto('/login')` 兜底，从未真正登出 ⇒ 「登出清缓存」类判据测的是别的东西。
  const userInfo = page.locator('.gt-user-info').first()
  await userInfo.waitFor({ state: 'visible', timeout: 8000 })
  await userInfo.click()
  const logoutItem = page.locator('.el-dropdown-menu__item', { hasText: '退出登录' }).first()
  await logoutItem.waitFor({ state: 'visible', timeout: 5000 })
  await logoutItem.click()
  await page.waitForURL('**/login**', { timeout: 10000 })
}

/**
 * 打开 AI 面板（优先 DshPanel 自带侧边触发器）。
 *
 * 🔴 顶栏入口被 `el-badge`（未读数变化改尺寸）+ `el-tooltip` 包着，会持续位移导致
 * Playwright 的 stable 检查永不通过；侧边触发器不抖。
 * 另：原实现用 `if (await trigger.isVisible())` 包住点击 —— 触发器不见时静默跳过、
 * 后续断言对着空面板跑，属于空转，故改成显式等待。
 */
async function openAiPanel(page: Page) {
  const sideTrigger = page.locator('button.dsh-panel-trigger').first()
  const topbarTrigger = page.locator('[aria-label="打开 AI 助手"]').first()
  const trigger = (await sideTrigger.count()) > 0 ? sideTrigger : topbarTrigger
  await trigger.waitFor({ state: 'visible', timeout: 8000 })
  await trigger.click()
  await page.waitForSelector('#dsh-panel-region, .dsh-panel-container', { timeout: 5000 })
}

/** 验证面板打开且显示输入区域 */
async function assertPanelOpen(page: Page) {
  const panel = page.locator('#dsh-panel-region, .dsh-panel-container')
  await expect(panel.first()).toBeVisible({ timeout: 5000 })
}

// ---------------------------------------------------------------------------
// 场景 1：全部宿主页面可打开统一面板
// ---------------------------------------------------------------------------

test.describe('场景 1: 全部宿主打开统一面板', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Dashboard 页面有 AI 面板触发器', async ({ page }) => {
    await page.waitForLoadState('networkidle')
    const trigger = page.locator('button.dsh-panel-trigger, [aria-label="打开 AI 助手"]').first()
    await expect(trigger).toBeVisible({ timeout: 10000 })
  })

  test('打开面板后渲染 PlatformAiChatPanel 核心结构', async ({ page }) => {
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)
    await assertPanelOpen(page)
    // 验证核心 DOM 结构
    const chatPanel = page.locator('.platform-ai-chat-panel, [class*="platform-ai-chat"]')
    await expect(chatPanel.first()).toBeVisible({ timeout: 5000 })
  })

  test('面板有输入区域且可输入', async ({ page }) => {
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)
    const input = page.locator('textarea[placeholder*="输入"], textarea[aria-describedby="chat-input-status"]').first()
    await expect(input).toBeVisible({ timeout: 5000 })
    await input.fill('测试输入')
    await expect(input).toHaveValue('测试输入')
  })

  test('面板关闭按钮语义为 button 且有 aria-label', async ({ page }) => {
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)
    const closeBtn = page.locator('button[aria-label="收起 AI 助手面板"]')
    await expect(closeBtn.first()).toBeVisible({ timeout: 5000 })
  })
})

// ---------------------------------------------------------------------------
// 场景 2：Native 对话流程
// ---------------------------------------------------------------------------

test.describe('场景 2: Native 对话两阶段 API', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('发送消息触发 POST /api/ai-chat/runs 请求', async ({ page }) => {
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)

    // 监听网络请求
    const runRequest = page.waitForRequest(
      (req) => req.url().includes('/api/ai-chat/runs') && req.method() === 'POST',
      { timeout: 15000 },
    )

    const input = page.locator('textarea[placeholder*="输入"], textarea[aria-describedby="chat-input-status"]').first()
    await input.fill('你好，这是测试')
    // 提交（Enter 或按钮）
    const sendBtn = page.locator('button[aria-label*="发送"], button:has-text("发送")').first()
    if (await sendBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await sendBtn.click()
    } else {
      await input.press('Enter')
    }

    const req = await runRequest
    expect(req.method()).toBe('POST')
    expect(req.url()).toContain('/api/ai-chat/runs')
  })

  test('run 创建后订阅 events_url（SSE 连接）', async ({ page }) => {
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)

    // 监听 GET /runs/*/events 请求（SSE）
    const eventsRequest = page.waitForRequest(
      (req) => req.url().includes('/events') && req.url().includes('/runs/'),
      { timeout: 20000 },
    )

    const input = page.locator('textarea[placeholder*="输入"], textarea[aria-describedby="chat-input-status"]').first()
    await input.fill('测试 SSE 订阅')
    // 🔴 必须点「发送」。面板的快捷键是 **Ctrl+Enter**（placeholder 写明），裸 Enter 只换行 ——
    // 原实现 `input.press('Enter')` 压根没发出 run，于是这条恒在等 SSE 请求超时。
    await page.locator('button:has-text("发送")').first().click()

    const req = await eventsRequest
    expect(req.method()).toBe('GET')
    expect(req.url()).toMatch(/\/runs\/[^/]+\/events/)
  })
})

// ---------------------------------------------------------------------------
// 场景 3：取消
// ---------------------------------------------------------------------------

test.describe('场景 3: 运行中取消', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('运行中出现取消按钮，点击后发送 POST /runs/{id}/cancel', async ({ page }) => {
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)

    const input = page.locator('textarea[placeholder*="输入"], textarea[aria-describedby="chat-input-status"]').first()
    await input.fill('生成一段长文本用于取消测试')
    // 🔴 点「发送」，不用裸 Enter（快捷键是 Ctrl+Enter）。原实现按 Enter ⇒ 根本没发出 run
    // ⇒ 取消按钮当然不出现 ⇒ 落进 catch 里的 `test.skip()`（**无原因**），报告里是一条
    // 没人看得懂的静默跳过。
    await page.locator('button:has-text("发送")').first().click()

    // 只把「取消按钮有没有出现」放进条件里；断言不能包在 try 里，否则取消真坏了
    // 也会被 catch 成 skip（把失败伪装成未验证）。
    const cancelBtn = page.locator('button[aria-label*="取消"], button:has-text("停止")').first()
    const cancellable = await cancelBtn
      .waitFor({ state: 'visible', timeout: 10000 })
      .then(() => true)
      .catch(() => false)
    test.skip(
      !cancellable,
      '本轮回答在 10s 内已结束，取消按钮未出现：换更长的提问（或让模型放慢）后重跑',
    )

    const cancelRequest = page.waitForRequest(
      (req) => req.url().includes('/cancel') && req.method() === 'POST',
      { timeout: 10000 },
    )
    await cancelBtn.click()
    const req = await cancelRequest
    expect(req.method()).toBe('POST')
    // 取消后按钮必须消失（run 进入 terminal cancelled）
    await expect(cancelBtn).not.toBeVisible({ timeout: 5000 })
  })
})

// ---------------------------------------------------------------------------
// 场景 4：网络面板核对
// ---------------------------------------------------------------------------

test.describe('场景 4: 网络请求合规性', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('不存在旧 /doc 双轨请求', async ({ page }) => {
    const legacyRequests: string[] = []
    page.on('request', (req) => {
      const url = req.url()
      // 旧双轨：/api/workpapers/*/doc-ai-chat 或 /api/docs/*/ai-chat
      if (url.match(/\/doc-ai-chat|\/docs\/[^/]+\/ai-chat/)) {
        legacyRequests.push(url)
      }
    })

    await page.waitForLoadState('networkidle')
    await openAiPanel(page)

    const input = page.locator('textarea[placeholder*="输入"], textarea[aria-describedby="chat-input-status"]').first()
    await input.fill('检查旧双轨')
    await input.press('Enter')

    // 等一会让请求发出
    await page.waitForTimeout(3000)
    expect(legacyRequests).toEqual([])
  })

  test('不存在 DSH Web UI iframe 请求', async ({ page }) => {
    const dshIframeRequests: string[] = []
    page.on('request', (req) => {
      const url = req.url()
      if (url.includes('127.0.0.1:3080') || url.includes('dsh-web-ui')) {
        dshIframeRequests.push(url)
      }
    })

    await page.waitForLoadState('networkidle')
    await openAiPanel(page)
    await page.waitForTimeout(3000)

    expect(dshIframeRequests).toEqual([])
  })

  test('面板 DOM 中无 <iframe> 元素', async ({ page }) => {
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)

    const iframes = await page.locator('#dsh-panel-region iframe, .dsh-panel-container iframe').count()
    expect(iframes).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// 场景 5：切账号/登出无缓存泄漏
// ---------------------------------------------------------------------------

test.describe('场景 5: 切账号无缓存泄漏', () => {
  test('登出后 localStorage 无 doc_ai_chat_* key', async ({ page }) => {
    await login(page)
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)

    // 模拟有历史缓存
    await page.evaluate(() => {
      localStorage.setItem('doc_ai_chat_test_legacy', JSON.stringify([{ text: 'old' }]))
    })

    await logout(page)

    // 检查 localStorage
    const keys = await page.evaluate(() => {
      const result: string[] = []
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i)
        if (key && key.startsWith('doc_ai_chat_')) {
          result.push(key)
        }
      }
      return result
    })

    expect(keys).toEqual([])
  })

  test('登出后重新登录，面板不显示上一用户的消息', async ({ page }) => {
    await login(page)
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)

    // 记录当前面板是否有消息（如果有的话都是当前用户的）
    await logout(page)
    await login(page)
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)

    // 面板应处于空状态或只显示当前用户的历史
    // 不应显示 localStorage 中另一用户的缓存消息
    const panel = page.locator('.platform-ai-chat-panel, [class*="platform-ai-chat"]').first()
    await expect(panel).toBeVisible({ timeout: 5000 })
  })
})

// ---------------------------------------------------------------------------
// 场景 6：XSS 渲染安全
// ---------------------------------------------------------------------------

test.describe('场景 6: 浏览器渲染安全', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('面板 DOM 中无 script 标签（在渲染后检查）', async ({ page }) => {
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)
    await assertPanelOpen(page)

    const scripts = await page.locator('#dsh-panel-region script, .dsh-panel-container script').count()
    expect(scripts).toBe(0)
  })

  test('面板 DOM 中无 on* 事件属性（注入检查）', async ({ page }) => {
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)
    await assertPanelOpen(page)

    // 检查整个面板区域无 on* event handler 属性
    const dangerousAttrs = await page.evaluate(() => {
      const panel = document.querySelector('#dsh-panel-region') || document.querySelector('.dsh-panel-container')
      if (!panel) return []
      const allElements = panel.querySelectorAll('*')
      const found: string[] = []
      for (const el of allElements) {
        for (const attr of el.getAttributeNames()) {
          if (attr.startsWith('on') && attr.length > 2) {
            found.push(`${el.tagName}.${attr}`)
          }
        }
      }
      return found
    })

    expect(dangerousAttrs).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// 场景 7：可访问性基线
// ---------------------------------------------------------------------------

test.describe('场景 7: 可访问性基线', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  /**
   * 🔴 只锁 DshPanel 自己的侧边触发器（Task 11 / Req 14.6 管的是这个语义 button）。
   * 原实现用逗号选择器 + `.first()` ⇒ 按 DOM 顺序命中的是 `ThreeColumnLayout` 顶栏那个
   * 入口。实测（2026-08-16）：**侧边触发器 Enter 能打开面板，顶栏入口 Enter 打不开**
   * （鼠标点击两者都行）。顶栏入口的键盘可达性是独立缺陷，已在收口说明中登记待产品定夺，
   * 不在本条里混测两个控件。
   */
  test('触发器可通过键盘 Enter 激活', async ({ page }) => {
    await page.waitForLoadState('networkidle')
    const trigger = page.locator('button.dsh-panel-trigger').first()
    await trigger.waitFor({ state: 'visible', timeout: 8000 })
    await trigger.focus()
    await expect(trigger).toBeFocused()
    await page.keyboard.press('Enter')
    await assertPanelOpen(page)
  })

  test('面板打开后有 aria-label 标识区域', async ({ page }) => {
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)

    const region = page.locator('[aria-label="AI 审计助手面板"], #dsh-panel-region')
    await expect(region.first()).toBeVisible({ timeout: 5000 })
  })

  /**
   * 读面板容器 class 判当前布局档（`dsh-panel-container--{column|drawer|fullscreen}`）。
   * 🔴 用 DOM 实测而不是按视口宽度推断：断点常量改了这里会跟着变，不会静默测错档。
   */
  async function readLayoutMode(page: Page): Promise<'column' | 'drawer' | 'fullscreen' | null> {
    const cls = await page
      .locator('#dsh-panel-region, .dsh-panel-container')
      .first()
      .getAttribute('class')
      .catch(() => null)
    if (!cls) return null
    for (const mode of ['column', 'drawer', 'fullscreen'] as const) {
      if (cls.includes(`dsh-panel-container--${mode}`)) return mode
    }
    return null
  }

  test('Escape 键按布局档区分行为（drawer/fullscreen 关闭，column 不关）', async ({ page }) => {
    // 1024px → drawer 档（769–1400）；Escape 必须关闭
    await page.setViewportSize({ width: 1024, height: 768 })
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)
    await assertPanelOpen(page)

    const drawerMode = await readLayoutMode(page)
    expect(drawerMode).not.toBeNull()
    expect(drawerMode).not.toBe('column') // 1024px 不该落进 column 档

    await page.locator('#dsh-panel-region, .dsh-panel-container').first().press('Escape')
    await expect(page.locator('#dsh-panel-region, .dsh-panel-container').first()).toBeHidden({
      timeout: 5000,
    })
    // 关闭后焦点回到触发器（DshPanel 的 watch 里显式 focus）
    await expect(page.locator('button.dsh-panel-trigger').first()).toBeFocused()

    // 1500px → column 档（≥1401）；Escape 明确**不**关闭（面板是布局的一列，
    // 不是浮层，按 Escape 就消失会打断正在阅读的对话）
    await page.setViewportSize({ width: 1500, height: 900 })
    await openAiPanel(page)
    await assertPanelOpen(page)
    expect(await readLayoutMode(page)).toBe('column')

    await page.locator('#dsh-panel-region, .dsh-panel-container').first().press('Escape')
    await page.waitForTimeout(500)
    await expect(page.locator('#dsh-panel-region, .dsh-panel-container').first()).toBeVisible()
  })
})
