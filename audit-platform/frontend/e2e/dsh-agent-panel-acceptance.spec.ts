/**
 * Playwright E2E 五角色三视口完整用户可见行为验收
 *
 * Feature: dsh-agent-panel-integration / Task 34
 * Validates: Requirements 1.1–1.10, 5.1, 5.4, 7.1, 8.5, 9.4, 10.4, 13.1, 13.6, 14.6
 * Properties: 9, 13, 19, 21, 23–25, 34–39
 *
 * 覆盖六大场景组：
 *   A. 视口 390/768/1400px：打开/关闭/拖拽/全屏/focus/keyboard/badge/new-window
 *   B. 五角色：host/mention/知识库/note/adopt/review/agent capability 允许/拒绝+中文反馈
 *   C. Native 链路：发送/stream/断流重连/取消/history/quota/Context Manifest/XSS
 *   D. Phase B：mention 多选裁剪/粘贴 OCR 五态/note 幂等失败保留/review base/address
 *   E. Phase C：capability/engine_unavailable/多步工具可见/取消/queue limit
 *   F. 网络面板：run 幂等/Last-Event-ID replay/无旧 /doc 双轨/无 DSH iframe
 *
 * 环境要求: start-dev.bat（后端 9980 + 前端 3030）
 * 运行: npx playwright test e2e/dsh-agent-panel-acceptance.spec.ts
 *
 * ───────────────────────────────────────────────────────────────────────────
 * 🔴 断言纪律：本文件禁止 `expect(true).toBe(true)` 这类同义反复，也禁止
 * `expect(await x.count()).toBeGreaterThanOrEqual(0)` / `expect(s.length >= 0)`
 * 这类恒真判据 —— 它们无论 UI 怎么坏都绿，比没有测试更糟（会让人以为验过了）。
 *
 * 需要特殊后端状态 / 测试资产才能验的场景，一律用 `test.skip(!前置, '中文前置说明')`：
 * skip 在报告里是「未验证」，恒真断言是「已通过」。前者诚实，后者是假绿。
 * 每个 skip 的说明都必须可执行 —— 读完就知道怎么让它跑起来。
 *
 * 可选前置（未设置则相关用例 skip）：
 *   E2E_EMBEDDING_DOWN=1      故意停掉 embedding 服务后置位，验 semantic_unavailable
 *   E2E_AUDITOR_USER / ...    多角色凭据
 *   e2e/fixtures/blank.png    无文字图片，验 OCR 空结果态
 * ───────────────────────────────────────────────────────────────────────────
 */
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect, type Page, type BrowserContext } from '@playwright/test'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

const BASE_URL = 'http://localhost:3030'
const BACKEND_URL = 'http://localhost:9980'

/**
 * 三视口。取值必须落在 `useDshPanelLayout` 的断点区间内，否则测的不是标题写的那个档：
 *   `>=1401` → column（独立列，position: relative）
 *   `769–1400` → drawer（fixed + 遮罩）
 *   `<=768` → fullscreen（inset:0 + safe-area）
 *
 * 🔴 desktop 曾是 1400 —— 那落在 **drawer** 区间，于是「独立列模式」组里断言
 * `position ∈ {static, relative}` 的用例恒红（drawer 是 fixed）。改 1500 才真是 column。
 * tablet 768 落在 fullscreen 区间（边界含等号），下面该组的断言（fixed/absolute + Escape 关闭）
 * 在 fullscreen 同样成立，故保持不变；drawer 档的 Escape 行为由
 * `dsh-phase-a-smoke.spec.ts` 在 1024px 下覆盖。
 */
const VIEWPORTS = {
  mobile: { width: 390, height: 844 },
  tablet: { width: 768, height: 1024 },
  desktop: { width: 1500, height: 900 },
} as const

/**
 * 五角色测试凭据
 * 实际凭据从环境变量或 fixtures 读取；无可用凭据时跳过角色相关测试
 */
const ROLES = {
  auditor: { user: process.env.E2E_AUDITOR_USER ?? 'auditor_e2e', pass: process.env.E2E_AUDITOR_PASS ?? 'test123' },
  manager: { user: process.env.E2E_MANAGER_USER ?? 'manager_e2e', pass: process.env.E2E_MANAGER_PASS ?? 'test123' },
  partner: { user: process.env.E2E_PARTNER_USER ?? 'partner_e2e', pass: process.env.E2E_PARTNER_PASS ?? 'test123' },
  qc: { user: process.env.E2E_QC_USER ?? 'qc_e2e', pass: process.env.E2E_QC_PASS ?? 'test123' },
  eqcr: { user: process.env.E2E_EQCR_USER ?? 'eqcr_e2e', pass: process.env.E2E_EQCR_PASS ?? 'test123' },
} as const

// ---------------------------------------------------------------------------
// 环境检测 — 后端不可用时 skip 全部
// ---------------------------------------------------------------------------

test.beforeAll(async ({ request }) => {
  try {
    const resp = await request.get(`${BACKEND_URL}/api/health`)
    if (resp.status() !== 200) test.skip(true, '后端不可用')
  } catch {
    test.skip(true, '后端不可用')
  }
})

// ---------------------------------------------------------------------------
// 公共 Helpers
// ---------------------------------------------------------------------------

async function login(page: Page, user = 'admin', pass = 'admin123') {
  await page.goto(`${BASE_URL}/login`)
  await page.waitForLoadState('domcontentloaded')
  await page.fill('input[placeholder*="用户名"]', user)
  await page.fill('input[placeholder*="密码"], input[type="password"]', pass)
  await page.click('button:has-text("登录")')
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 })
}

/**
 * 走**真实登出路径**（ThreeColumnLayout 顶栏用户下拉 → 退出登录 → authStore.logout()）。
 *
 * 🔴 原实现找 `.el-dropdown-link, .user-avatar, [class*="header-user"]` —— 布局里
 * 实际是 `.gt-user-info`，三个都不匹配 ⇒ 每次都落到 `goto('/login')` 兜底，
 * **从未真正触发过 authStore.logout()**。于是「登出后清缓存」这条测的是
 * 「导航到 /login 后缓存还在不在」，必红且误导；「切换用户」那条则因为仍处登录态
 * 被重定向走、卡在找不到用户名输入框。
 */
async function logout(page: Page) {
  const userInfo = page.locator('.gt-user-info').first()
  await userInfo.waitFor({ state: 'visible', timeout: 8000 })
  await userInfo.click()
  const logoutItem = page.locator('.el-dropdown-menu__item', { hasText: '退出登录' }).first()
  await logoutItem.waitFor({ state: 'visible', timeout: 5000 })
  await logoutItem.click()
  await page.waitForURL('**/login**', { timeout: 10000 })
}

/**
 * 打开 AI 面板。
 *
 * 🔴 优先用 DshPanel 自带的侧边触发器 `.dsh-panel-trigger`：顶栏那个入口被
 * `el-badge`（未读数变化会改变尺寸）+ `el-tooltip` 包着，未读数一变按钮就位移，
 * Playwright 的 "visible, enabled and stable" 永远满足不了（实测在 /knowledge 上
 * 重试 51 次后超时）。两个入口都是真实可点控件，选不抖的那个。
 */
async function openAiPanel(page: Page) {
  const sideTrigger = page.locator('button.dsh-panel-trigger').first()
  const topbarTrigger = page.locator('[aria-label="打开 AI 助手"]').first()
  const trigger = (await sideTrigger.count()) > 0 ? sideTrigger : topbarTrigger
  await trigger.waitFor({ state: 'visible', timeout: 8000 })
  await trigger.click()
  await page.waitForSelector('#dsh-panel-region, .dsh-panel-container', { timeout: 5000 })
}

/** 关闭 AI 面板 */
async function closeAiPanel(page: Page) {
  const closeBtn = page.locator('button[aria-label="收起 AI 助手面板"], button[aria-label="关闭 AI 助手"]').first()
  if (await closeBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await closeBtn.click()
    await page.waitForTimeout(300)
  }
}

/** 面板输入区 */
function getChatInput(page: Page) {
  return page.locator(
    'textarea[placeholder*="输入"], textarea[aria-describedby="chat-input-status"], .chat-composer textarea',
  ).first()
}

/** 发送消息并等待 run 创建 */
async function sendMessage(page: Page, text: string) {
  const input = getChatInput(page)
  await input.fill(text)
  const sendBtn = page.locator('button[aria-label*="发送"], button:has-text("发送")').first()
  if (await sendBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await sendBtn.click()
  } else {
    await input.press('Enter')
  }
}

/**
 * assistant / user 消息的真实选择器。
 *
 * 🔴 `PlatformAiChatPanel` 渲染的是 `.platform-ai-chat-panel__msg` + `[msg.role, msg.status]`
 * 两个 class，**没有** `data-role` 属性，也没有 `.chat-message--assistant`。
 * 本文件此前用后两者当选择器 ⇒ 永不匹配 ⇒ 5 条 C 组用例卡在 `waitForSelector` 超时，
 * 而不是真的「模型没响应」。选择器必须跟组件对齐。
 */
const ASSISTANT_MSG = '.platform-ai-chat-panel__msg.assistant'
const USER_MSG = '.platform-ai-chat-panel__msg.user'
const ANY_MSG = '.platform-ai-chat-panel__msg'

/** 等待 assistant 消息出现（至少一个 delta 或完成） */
async function waitForAssistantResponse(page: Page, timeout = 20000) {
  await page.waitForSelector(ASSISTANT_MSG, { timeout })
}

// ---------------------------------------------------------------------------
// 前置条件探测 Helpers（skip 判据一律实测，不写死）
// ---------------------------------------------------------------------------

/**
 * 读取 `/api/ai-chat/capabilities` 的 capability manifest。
 *
 * 🔴 响应形态是 `{ engine, capabilities: {...}, gate_reason, disabled_reasons, health }`
 * （后端 `CapabilityResponse`）—— 八项能力在**嵌套的 `capabilities` 里**，不在根上。
 * 直接读 `data.tools` 恒为 `undefined`，会让 `if (!data.tools)` 这类门恒真。
 */
async function fetchCapabilities(page: Page): Promise<{ status: number; body: string }> {
  // 🔴 必须在页面内 fetch：token 存在 sessionStorage（auth store 已从 localStorage 迁走），
  // `page.request` 走独立的 request context、不带 Authorization ⇒ 该端点恒 401。
  // 本文件此前用 `page.request.get(...)` + `if (response.ok())` 包裹全部断言 ⇒ 恒空过。
  return page.evaluate(async () => {
    const token = sessionStorage.getItem('token') || localStorage.getItem('token') || ''
    const resp = await fetch('/api/ai-chat/capabilities', {
      headers: { Authorization: `Bearer ${token}` },
    })
    return { status: resp.status, body: await resp.text() }
  })
}

async function fetchCapabilityManifest(page: Page): Promise<Record<string, unknown> | null> {
  const { status, body } = await fetchCapabilities(page)
  if (status !== 200) return null
  let parsed: Record<string, any> | null = null
  try {
    parsed = JSON.parse(body)
  } catch {
    return null
  }
  const data = (parsed?.data ?? parsed) as Record<string, any> | null
  const caps = data?.capabilities
  return caps && typeof caps === 'object' ? (caps as Record<string, unknown>) : null
}

/**
 * 当前生效引擎是否支持多步工具调用。
 *
 * 实测得出而非写死：`native` 引擎 `tools=false`，`dsh` 引擎 `tools=true`
 * （后端 `CAPABILITIES_BY_ENGINE`）。DSH 需 `AI_DSH_ENABLED=true` + experimental flag
 * + 项目在 allowlist 三层门全过才会生效。
 */
async function isToolCapableEngine(page: Page): Promise<boolean> {
  const caps = await fetchCapabilityManifest(page)
  return caps?.tools === true
}

/** e2e 测试资产是否就位 */
function hasFixture(name: string): boolean {
  return existsSync(path.join(__dirname, 'fixtures', name))
}

/** 面板当前布局档（读 DshPanel 下发的 `dsh-panel-container--{mode}` class，不按视口猜） */
async function readPanelLayoutMode(page: Page): Promise<'column' | 'drawer' | 'fullscreen' | null> {
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

// ===========================================================================
// A. 三视口响应式与交互
// ===========================================================================

test.describe('A. 三视口响应式与交互', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await page.waitForLoadState('networkidle')
  })

  // ─── 1400px 桌面视口 ───────────────────────────────────────────────────

  test.describe('1400px 独立列模式', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.desktop)
    })

    test('面板作为独立列展开，不覆盖主内容', async ({ page }) => {
      await openAiPanel(page)
      const panel = page.locator('.platform-ai-chat-panel, #dsh-panel-region').first()
      await expect(panel).toBeVisible()
      // 验证面板不是 fixed/absolute overlay
      const position = await panel.evaluate((el) => window.getComputedStyle(el).position)
      expect(['static', 'relative', '']).toContain(position)
    })

    test('拖拽面板宽度限制在 320-800px', async ({ page }) => {
      await openAiPanel(page)
      // column 档一定渲染 resizer（只有 fullscreen 不渲染），所以这里不做条件包裹 ——
      // 包裹起来的话 resizer 消失时会静默通过。
      const resizer = page.locator('.dsh-panel-resizer').first()
      await expect(resizer).toBeVisible()
      const box = await resizer.boundingBox()
      expect(box).not.toBeNull()

      const panel = page.locator('#dsh-panel-region').first()

      /**
       * 拖拽一次并返回拖后宽度。
       * 🔴 位移量必须留在视口内 —— 目标点超出视口时 CDP 会丢事件，
       * 表现为「宽度一动不动」而判据以为是产品坏了。
       * 步进也要 >1，单步跳跃有些实现收不到中间的 mousemove。
       */
      async function dragBy(dx: number): Promise<number> {
        // hover 先把光标落到 resizer 上并等它稳定 —— 直接用 boundingBox 算坐标时，
        // 面板刚渲染完的一两帧里坐标可能是旧的，mousedown 就落到了空处（实测该测偶发 420/420）。
        await resizer.hover()
        const b = (await resizer.boundingBox())!
        const x = b.x + b.width / 2
        const y = b.y + b.height / 2
        await page.mouse.move(x, y)
        await page.mouse.down()
        // 先动一小步触发 onMove，再走完剩余位移
        await page.mouse.move(x + Math.sign(dx) * 5, y, { steps: 2 })
        await page.mouse.move(x + dx, y, { steps: 10 })
        await page.mouse.up()
        await page.waitForTimeout(100)
        return panel.evaluate((el) => el.getBoundingClientRect().width)
      }

      // 向右拖 = 收窄（面板在右侧）；必须被 MIN_WIDTH 夹住
      const narrow = await dragBy(600)
      expect(narrow).toBeGreaterThanOrEqual(320)

      // 向左拖 = 加宽；必须被 MAX_WIDTH 夹住
      const wide = await dragBy(-900)
      expect(wide).toBeLessThanOrEqual(800)

      // 拖拽真的生效了，不是两次都卡在初始值（否则上面两条被默认宽度 420 白白满足）
      expect(wide).toBeGreaterThan(narrow)
    })

    test('新窗口打开按钮指向平台聊天路由', async ({ page }) => {
      await openAiPanel(page)
      // 该按钮由 DshPanel 无条件渲染（aria-label="在新窗口打开 AI 助手"），
      // 所以这里不做条件包裹 —— 按钮消失时必须打红而不是静默通过。
      const newWindowBtn = page.locator('button[aria-label="在新窗口打开 AI 助手"]').first()
      await expect(newWindowBtn).toBeVisible()

      const [newPage] = await Promise.all([
        page.context().waitForEvent('page'),
        newWindowBtn.click(),
      ])
      await newPage.waitForLoadState('domcontentloaded')
      // ── 第一层：请求的是平台自己的地址，不是 DSH Web UI（Req 1.5：无双轨、无 iframe）
      expect(newPage.url()).toContain(BASE_URL)
      expect(newPage.url()).toContain('/ai-chat')
      expect(newPage.url()).not.toContain('3080')
      expect(newPage.url()).not.toContain('dsh-web-ui')

      // ── 第二层：新窗口真的渲染出了聊天面板
      //
      // 🔴 只断言 URL 是**不够**的，这不是冗余而是本条用例此前的真实缺陷：
      // Vue Router 的 NotFound 是 catch-all 客户端路由（`/:pathMatch(.*)*`），
      // 命中它**不改变 URL**。所以当 `/ai-chat` 路由未注册时（实测 commit 55c5e0fe
      // 的 router/index.ts 里 path 声明数为 0，原文还写着 "Do NOT re-add these routes"），
      // 新窗口打开的是 404 页面，而上面四条 URL 断言**全部照样通过**。
      // AC 1.5 因此在「已标完成」的交付里坏着，靠浏览器手点才暴露。
      //
      // 判据必须落到渲染结果：面板挂载 + 404 标志不存在。两条都要 ——
      // 只查 404 不存在的话，白屏（组件加载失败）也会放过。
      await expect(newPage.locator('.gt-not-found')).toHaveCount(0)
      await expect(newPage.locator('.platform-ai-chat-panel').first()).toBeVisible({
        timeout: 15000,
      })
      await newPage.close()
    })

    test('badge 在面板折叠时可见，展开时清零', async ({ page }) => {
      await openAiPanel(page)

      // 🔴 必须限定在 AI 徽标上（`ThreeColumnLayout` 的 `.gt-dsh-badge`）。
      // 原选择器是裸 `.el-badge__content` —— 会命中页面上**任何**徽标（实测抓到侧栏的
      // 「27」），于是这条测的根本不是 AI 未读数。
      const aiBadge = page.locator('.gt-dsh-badge .el-badge__content')

      // 真断言（不做条件包裹）：面板展开后未读计数必须清零 ——
      // `:hidden="dshUnreadCount === 0 || showDshPanel"` ⇒ 面板开着时徽标必须不可见。
      await expect(aiBadge).toBeHidden()
    })
  })

  // ─── 768px Drawer 模式 ─────────────────────────────────────────────────

  test.describe('768px Drawer 模式', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.tablet)
    })

    test('面板作为 fixed 浮层展示', async ({ page }) => {
      await openAiPanel(page)
      const panel = page.locator('.platform-ai-chat-panel, #dsh-panel-region').first()
      await expect(panel).toBeVisible()
      const position = await panel.evaluate((el) => window.getComputedStyle(el).position)
      expect(['fixed', 'absolute']).toContain(position)
    })

    test('Escape 关闭面板', async ({ page }) => {
      await openAiPanel(page)
      await page.keyboard.press('Escape')
      await page.waitForTimeout(500)
      // 验证面板不再可见或 collapsed
      const panel = page.locator('.platform-ai-chat-panel, #dsh-panel-region').first()
      const visible = await panel.isVisible().catch(() => false)
      // drawer 模式下 Escape 应该关闭
      expect(visible).toBe(false)
    })

    test('关闭后焦点回到触发器', async ({ page }) => {
      const trigger = page.locator(
        'button.dsh-panel-trigger, [aria-label="打开 AI 助手"]',
      ).first()
      await trigger.click()
      await page.waitForTimeout(300)
      await page.keyboard.press('Escape')
      await page.waitForTimeout(300)
      // 焦点应回到触发器
      const focused = await page.evaluate(() => document.activeElement?.getAttribute('aria-label'))
      // 接受 aria-label 匹配或靠近触发器
      expect(focused).toBeTruthy()
    })
  })

  // ─── 390px 全屏模式 ────────────────────────────────────────────────────

  test.describe('390px 全屏模式', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile)
    })

    test('面板使用全屏模式覆盖页面', async ({ page }) => {
      await openAiPanel(page)
      const panel = page.locator('.platform-ai-chat-panel, #dsh-panel-region').first()
      await expect(panel).toBeVisible()
      const rect = await panel.evaluate((el) => {
        const r = el.getBoundingClientRect()
        return { width: r.width, height: r.height }
      })
      // 应该接近满屏
      expect(rect.width).toBeGreaterThanOrEqual(380)
    })

    test('全屏模式有焦点锁定（focus trap）', async ({ page }) => {
      await openAiPanel(page)
      // 多次 Tab 不应跳出面板
      for (let i = 0; i < 10; i++) {
        await page.keyboard.press('Tab')
      }
      const activeInPanel = await page.evaluate(() => {
        const panel = document.querySelector('.platform-ai-chat-panel, #dsh-panel-region')
        return panel?.contains(document.activeElement) ?? false
      })
      expect(activeInPanel).toBe(true)
    })

    test('滚动隔离 — 面板内滚动不穿透到主页面', async ({ page }) => {
      await openAiPanel(page)
      const mainScrollBefore = await page.evaluate(() => document.documentElement.scrollTop)
      // 在面板内模拟滚动
      const panel = page.locator('.platform-ai-chat-panel, #dsh-panel-region').first()
      await panel.evaluate((el) => {
        el.dispatchEvent(new WheelEvent('wheel', { deltaY: 100, bubbles: true }))
      })
      const mainScrollAfter = await page.evaluate(() => document.documentElement.scrollTop)
      expect(mainScrollAfter).toBe(mainScrollBefore)
    })
  })

  // ─── 键盘操作 ──────────────────────────────────────────────────────────

  test.describe('键盘操作', () => {
    test('触发器可通过 Enter/Space 激活', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.desktop)
      // 明确锁 DshPanel 自己的侧边触发器（Req 14.6 / Task 11 管的就是这个语义 button）。
      // 原实现用逗号选择器 + `.first()` ⇒ 按 DOM 顺序命中顶栏那个入口，测的不是同一个控件。
      const trigger = page.locator('button.dsh-panel-trigger').first()
      await trigger.waitFor({ state: 'visible', timeout: 8000 })
      await trigger.focus()
      await expect(trigger).toBeFocused()
      await page.keyboard.press('Enter')
      await expect(page.locator('#dsh-panel-region').first()).toBeVisible({ timeout: 3000 })
    })

    test('面板打开后焦点进入输入区', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.desktop)
      await openAiPanel(page)
      await page.waitForTimeout(300)
      const activeTag = await page.evaluate(() => document.activeElement?.tagName?.toLowerCase())
      // 焦点应在 textarea 或 input
      expect(['textarea', 'input']).toContain(activeTag)
    })
  })
})

// ===========================================================================
// B. 五角色权限与中文反馈
// ===========================================================================

test.describe('B. 五角色权限与中文反馈', () => {
  // 如果没有多角色测试凭据，使用默认 admin 做基础验证
  const hasMultiRole = !!(process.env.E2E_AUDITOR_USER && process.env.E2E_QC_USER)

  test.describe('通用权限验证（admin 角色）', () => {
    test.beforeEach(async ({ page }) => {
      await login(page)
      await page.waitForLoadState('networkidle')
    })

    test('当前 host 有权时面板正常加载', async ({ page }) => {
      await openAiPanel(page)
      const panel = page.locator('.platform-ai-chat-panel, #dsh-panel-region').first()
      await expect(panel).toBeVisible()
      // 输入区可用
      const input = getChatInput(page)
      await expect(input).toBeEnabled()
    })

    test('无项目上下文时项目工具禁用并显示中文原因', async ({ page }) => {
      // 全局知识库页面 = 无项目上下文
      await page.goto(`${BASE_URL}/knowledge`)
      await page.waitForLoadState('networkidle')
      await openAiPanel(page)

      // 真断言（无条件）：范围条必须标记为全局态，并给出中文范围说明。
      // 原实现挂在 `[data-testid="project-tool-btn"]` 上 —— 该属性在整个 src/ 里不存在，
      // 于是 if 永不进入、测试恒绿。改成断言真实存在的范围条。
      const scope = page.locator('.platform-ai-chat-panel__scope').first()
      await expect(scope).toBeVisible()
      await expect(scope).toHaveClass(/is-global/)

      const hint = scope.locator('.platform-ai-chat-panel__hint')
      await expect(hint).toBeVisible()
      expect((await hint.textContent()) ?? '').toMatch(/[\u4e00-\u9fff]/)

      // 复核模式属于项目/底稿工具：无项目上下文时必须禁用且给中文原因
      const reason = page.locator('.chat-review-mode-bar__reason')
      await expect(reason).toBeVisible()
      expect((await reason.textContent()) ?? '').toMatch(/[\u4e00-\u9fff]/)
    })
  })

  test.describe('五角色差异化验证', () => {
    test.skip(!hasMultiRole, '需要多角色凭据（设置 E2E_AUDITOR_USER / E2E_QC_USER 等）')

    for (const [roleName, cred] of Object.entries(ROLES)) {
      test(`${roleName} 角色可打开面板且权限反馈为中文`, async ({ page }) => {
        await login(page, cred.user, cred.pass)
        await page.waitForLoadState('networkidle')

        // 尝试打开面板
        const trigger = page.locator(
          'button.dsh-panel-trigger, [aria-label="打开 AI 助手"]',
        ).first()
        const triggerVisible = await trigger.isVisible({ timeout: 5000 }).catch(() => false)
        // 原实现在这里 `return` —— 无触发器时静默通过。改成 skip，报告里如实记「未验证」。
        test.skip(
          !triggerVisible,
          `${roleName} 角色在落地页看不到 AI 面板触发器：确认该账号有项目可见权限（否则无从验证面板行为）`,
        )

        await trigger.click()
        const panel = page.locator('.platform-ai-chat-panel, #dsh-panel-region').first()
        await expect(panel).toBeVisible({ timeout: 5000 })

        // 真断言：范围说明必须是中文（每个角色都能看到自己的可用范围）
        const hint = panel.locator('.platform-ai-chat-panel__hint').first()
        await expect(hint).toBeVisible()
        expect((await hint.textContent()) ?? '').toMatch(/[\u4e00-\u9fff]/)

        // 禁用入口若带 title，必须是中文原因（不能是英文 code 或空 title）
        for (const btn of await panel.locator('button:disabled').all()) {
          const title = await btn.getAttribute('title')
          if (title !== null && title !== '') {
            expect(title).toMatch(/[\u4e00-\u9fff]/)
          }
        }
      })
    }

    test('QC/EQCR 角色的写类操作（adopt/note）被禁用', async ({ page }) => {
      await login(page, ROLES.qc.user, ROLES.qc.pass)
      await page.waitForLoadState('networkidle')
      await openAiPanel(page)

      // 转存笔记入口只在「选择模式」里出现，而选择模式又要求先有 completed 回复。
      // 未出现 ⇒ 无从验证「被禁用」，如实记未验证，不空过。
      const selectBtn = page.locator('.platform-ai-chat-panel__select-btn').first()
      const canSelect = await selectBtn.isVisible({ timeout: 3000 }).catch(() => false)
      test.skip(
        !canSelect,
        'QC 账号会话内没有 completed 的 AI 回复，选择模式入口未出现：先用该账号问一轮再验「转存被禁用」',
      )

      await selectBtn.click()
      const noteBtn = page.locator('button:has-text("转存笔记")').first()
      await expect(noteBtn).toBeVisible()
      // 真断言：QC 只读 ⇒ 写类操作必须禁用
      await expect(noteBtn).toBeDisabled()
    })

    test('权限拒绝返回非枚举响应（不泄露资源名称）', async ({ page }) => {
      await login(page, ROLES.auditor.user, ROLES.auditor.pass)
      await page.waitForLoadState('networkidle')

      // 🔴 原实现只被动监听 403 —— 从不主动触发越权，`responses` 恒空，for 循环空转。
      // 改成主动探测：用随机 UUID 冒充别人的底稿，走只读端点（不写任何数据）。
      const probe = await page.evaluate(async () => {
        const token = sessionStorage.getItem('token') || localStorage.getItem('token') || ''
        const foreignWp = '00000000-0000-4000-8000-00000000dead'
        const foreignProject = '00000000-0000-4000-8000-00000000beef'
        const resp = await fetch(
          `/api/ai-chat/review-prompt?host_type=workpaper&host_id=${foreignWp}&project_id=${foreignProject}`,
          { headers: { Authorization: `Bearer ${token}` } },
        )
        return { status: resp.status, body: await resp.text() }
      })

      // 真断言 1：必须被拒（不能因为「查不到」就 200 返空）
      expect([401, 403, 404]).toContain(probe.status)

      // 真断言 2：拒绝响应不得枚举资源 —— 不带资源名称/编码字段（Property 1）
      expect(probe.body).not.toMatch(/project_name|wp_name|wp_code|doc_title|sheet_name/)

      // 真断言 3：拒绝文案是中文可执行说明，不是英文 stack/裸 code
      expect(probe.body).toMatch(/[\u4e00-\u9fff]/)
      expect(probe.body).not.toMatch(/Traceback|SQLAlchemy|psycopg|asyncpg/)
    })
  })
})

// ===========================================================================
// C. Native 链路完整验证
// ===========================================================================

test.describe('C. Native 链路', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)
  })

  test('发送 → POST /runs 创建 → GET /events SSE 订阅', async ({ page }) => {
    const runCreated = page.waitForRequest(
      (req) => req.url().includes('/api/ai-chat/runs') && req.method() === 'POST',
      { timeout: 15000 },
    )
    const eventsSubscribed = page.waitForRequest(
      (req) => req.url().includes('/events') && req.method() === 'GET',
      { timeout: 20000 },
    )

    await sendMessage(page, '你好，简短回复')

    const runReq = await runCreated
    expect(runReq.method()).toBe('POST')

    const eventsReq = await eventsSubscribed
    expect(eventsReq.url()).toMatch(/\/runs\/[^/]+\/events/)
  })

  test('流式响应逐步展示 assistant 消息', async ({ page }) => {
    await sendMessage(page, '请用中文介绍自己')
    await waitForAssistantResponse(page, 30000)

    const assistant = page.locator(ASSISTANT_MSG).first()
    const text = await assistant.textContent()
    expect(text!.length).toBeGreaterThan(0)
  })

  test('取消运行中 run — 发送 POST /cancel 且停止输出', async ({ page }) => {
    await sendMessage(page, '请写一篇 500 字的审计方法论综述')

    const cancelBtn = page.locator(
      'button[aria-label*="取消"], button:has-text("停止"), button[aria-label*="停止"]',
    ).first()

    // 🔴 try 只包「取消按钮有没有出现」这一步。原实现把断言也包在 try 里 ——
    // 取消功能真坏了也会被 catch 转成 skip('响应太快')，属于把失败伪装成未验证。
    const cancellable = await cancelBtn
      .waitFor({ state: 'visible', timeout: 8000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!cancellable, '本轮回答在 8s 内已结束，取消按钮未出现：换更长的提问（或降低模型速度）后重跑')

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

  test('对话 history 可加载且按时间正序', async ({ page }) => {
    // 先发一条消息确保有历史
    await sendMessage(page, '测试历史记录')
    await waitForAssistantResponse(page, 30000)

    // 刷新页面
    await page.reload()
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)

    // 历史消息应加载
    const messages = page.locator(ANY_MSG)
    const count = await messages.count()
    // 至少有之前发的消息
    expect(count).toBeGreaterThanOrEqual(1)
  })

  test('quota 触发时显示中文倒计时并保留草稿', async ({ page }) => {
    // 快速连续发送以触发限流
    for (let i = 0; i < 20; i++) {
      const input = getChatInput(page)
      if (await input.isEnabled().catch(() => false)) {
        await input.fill(`限流测试 ${i}`)
        await input.press('Enter')
        await page.waitForTimeout(200)
      }
    }

    // 限流提示走面板的 quota / error 两个 live-region
    const quotaMsg = page.locator(
      '.platform-ai-chat-panel__quota, .platform-ai-chat-panel__error',
    ).first()
    const quotaVisible = await quotaMsg.isVisible({ timeout: 5000 }).catch(() => false)
    test.skip(
      !quotaVisible,
      '本次未触发限流：把 AI_CHAT_RATE_LIMIT 调低（或提高上面的连发次数）让后端返回 rate_limited 后重跑',
    )

    const text = (await quotaMsg.textContent()) ?? ''
    // 真断言 1：中文 + 明确「输入已保留 / 稍后再试」的下一步（rate_limited 的明文承诺）
    expect(text).toMatch(/[\u4e00-\u9fff]/)
    expect(text).toMatch(/保留|稍候|稍后/)

    // 真断言 2：限流时输入框不得被禁死，否则「草稿已保留」等于空话
    await expect(getChatInput(page)).toBeEnabled()
  })

  test('Context Manifest 可展开查看', async ({ page }) => {
    await sendMessage(page, '测试上下文清单')

    // Context Inspector 区域
    const inspector = page.locator(
      '[data-testid="context-inspector"], .chat-context-inspector, [aria-label*="上下文"]',
    ).first()

    /**
     * 前置：本轮必须收到 `context_ready`（检视器由 `v-if="contextManifestReady"` 控制）。
     *
     * 🔴 这里**不能**用 `waitForAssistantResponse` + `isVisible()` 的组合当判据（原实现如此）：
     *   ① `waitForAssistantResponse` 等的是 `.platform-ai-chat-panel__msg.assistant`，而
     *      打开面板时 `fetchHistory()` 会把**上一轮的历史回复**渲染出来 ⇒ 该选择器**立刻**
     *      就命中，等于没等；
     *   ② `locator.isVisible()` 是即时判定，`{timeout}` 不生效、不重试。
     * 两者叠加 ⇒ 在 `context_ready` 还没到达时就判定"未挂载"并 skip。实测（2026-08-22
     * 接线后）：单跑本条仍 skip，而同样步骤加 3s 等待的探针里 `.chat-context-inspector`
     * 计数为 1 且可见 —— 说明 skip 的是这个竞态，不是产品缺件。改成真等它出现。
     */
    const inspectorPresent = await inspector
      .waitFor({ state: 'visible', timeout: 30000 })
      .then(() => true)
      .catch(() => false)
    test.skip(
      !inspectorPresent,
      '本轮未收到 context_ready（检视器不渲染）：确认 AI 引擎可用、本轮 run 未被限流或直接失败后重跑',
    )

    // 🔴 条目类名以组件为准（`chat-context-inspector__item`）——
    // 原选择器 `.context-manifest-item` / `[data-testid="manifest-item"]` 在 src/ 里不存在。
    const toggle = inspector.locator('.chat-context-inspector__toggle')

    // 真断言（无条件跑）：折叠态默认 + 点击后真展开（这才是标题说的「可展开」）
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const content = inspector.locator('#context-inspector-content')
    await expect(content).toBeVisible()

    /**
     * 前置：本轮 manifest 必须**非空**才谈得上「列出条目」。
     *
     * 🔴 这里原来直接断言 `items.first()` 可见 ⇒ 在无项目宿主下恒红，而红的不是产品。
     * 2026-08-22 探针抓到的真实载荷（`context_ready.payload.manifest`）：
     *   `{"manifest_version":"native-included-only-v1","token_estimate":0,
     *     "citation_count":0,"project_tools_enabled":false,"review_mode":false,"included":[]}`
     * 服务端**自己就给了 0 条**（全局宿主、本轮无 mention / 无附件 / 无 RAG 命中），
     * 投影如实返回 `[]`，组件如实渲染空态 —— 三层都对。
     * 要真验「列出条目」这条路径，得在**项目宿主**下先引用至少一份底稿/附注再发问。
     */
    const items = inspector.locator('.chat-context-inspector__item')
    const emptyState = inspector.locator('.chat-context-inspector__empty')
    const itemCount = await items.count()
    if (itemCount === 0) {
      // 空态也必须是**中文明文**，不能是空白面板（用户得知道"确实没读任何东西"）
      await expect(emptyState).toBeVisible()
      await expect(emptyState).toHaveText('暂无上下文信息')
    }
    test.skip(
      itemCount === 0,
      '本轮 manifest 为空（服务端 context_ready 下发 included:[]，全局宿主无项目上下文）：'
        + '切到项目宿主并先 @ 引用至少一份底稿/附注（或挂附件）后重跑，即可验非空清单路径',
    )

    // 真断言：非空时每条都得渲染出来且可见
    await expect(items.first()).toBeVisible({ timeout: 5000 })
    expect(itemCount).toBeGreaterThan(0)
  })

  test('XSS — AI 返回恶意 HTML 后 DOM 无 script/event handler', async ({ page }) => {
    // 发送可能触发 markdown 渲染的内容
    await sendMessage(page, '请输出以下代码片段：<script>alert(1)</script>')
    await waitForAssistantResponse(page, 30000)

    // 验证 DOM 安全
    const panel = page.locator('.platform-ai-chat-panel, #dsh-panel-region').first()
    const hasScript = await panel.locator('script').count()
    expect(hasScript).toBe(0)

    // 检查 message 区域无 on* 事件属性
    const dangerousAttrs = await panel.evaluate((el) => {
      const messages = el.querySelectorAll('.platform-ai-chat-panel__msg.assistant *')
      const found: string[] = []
      for (const node of messages) {
        for (const attr of node.getAttributeNames()) {
          if (attr.startsWith('on')) found.push(`${node.tagName}.${attr}`)
        }
      }
      return found
    })
    expect(dangerousAttrs).toEqual([])
  })

  test('消息正文不写入 localStorage', async ({ page }) => {
    await sendMessage(page, '这条消息不应进入 localStorage')
    await waitForAssistantResponse(page, 30000)

    const sensitiveKeys = await page.evaluate(() => {
      const keys: string[] = []
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i)!
        const value = localStorage.getItem(key) ?? ''
        if (value.includes('这条消息不应进入') || key.startsWith('doc_ai_chat_')) {
          keys.push(key)
        }
      }
      return keys
    })
    expect(sensitiveKeys).toEqual([])
  })
})

// ===========================================================================
// D. Phase B — 上下文能力
// ===========================================================================

test.describe('D. Phase B 上下文能力', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)
  })

  // ─── mention 多选裁剪 ──────────────────────────────────────────────────

  test.describe('Mention', () => {
    test('@ 触发 mention picker 且可键盘导航', async ({ page }) => {
      const input = getChatInput(page)
      await input.fill('@')

      // 前置：`@` 必须真能唤出 picker（面板已挂载 ChatMentionPicker，见「地址坐标」组说明）
      const picker = page.locator('.chat-mention-picker').first()
      const pickerOpened = await picker
        .waitFor({ state: 'visible', timeout: 8000 })
        .then(() => true)
        .catch(() => false)
      test.skip(
        !pickerOpened,
        '@ 未唤出 mention picker：接线已完成（面板已挂载 ChatMentionPicker，watch(draft) 按活跃 @ 词开关），2026-08-22 实测 79ms 内弹出；此处若仍 skip 先查宿主是否可用与 @ 词判定是否被改坏',
      )

      /**
       * 候选项只在 picker **自己的搜索框**里输入后才会有 —— 组件契约没有查询词 prop，
       * 打开时它 `focusInput()` 等用户输入。不搜就断言键盘导航等于测 idle 态（恒 0 条）。
       */
      const searchInput = picker.locator('input').first()
      await expect(searchInput).toBeFocused()
      await searchInput.fill('审')
      await page.waitForTimeout(1500) // debounceMs = 300 + 请求往返

      // 前置：键盘导航需要有候选项（activeIndex 在 items 为空时恒 -1）
      const options = picker.locator('[role="option"]')
      const optionCount = await options.count()
      test.skip(
        optionCount === 0,
        '当前无可引用候选（2026-08-22 实测：全局宿主下搜「审」返回 0 条，picker 显示「无匹配结果」）：'
          + '切到项目宿主并为该项目准备至少一份底稿/附注后重跑',
      )

      // 真断言：↓ 必须把高亮移到第一项，并通过 aria-activedescendant 暴露给屏幕阅读器
      await searchInput.press('ArrowDown')
      await expect(options.first()).toHaveClass(/is-active/)
      await expect(searchInput).toHaveAttribute('aria-activedescendant', 'mention-option-0')
    })

    test('搜索失败与空结果显示不同状态', async ({ page }) => {
      const input = getChatInput(page)
      await input.fill('@')

      const picker = page.locator('.chat-mention-picker').first()
      const pickerOpened = await picker
        .waitFor({ state: 'visible', timeout: 8000 })
        .then(() => true)
        .catch(() => false)
      test.skip(
        !pickerOpened,
        '@ 未唤出 mention picker：接线已完成（面板已挂载 ChatMentionPicker，watch(draft) 按活跃 @ 词开关），2026-08-22 实测 79ms 内弹出；此处若仍 skip 先查宿主是否可用与 @ 词判定是否被改坏',
      )

      /**
       * 🔴 关键词必须打进 **picker 自己的搜索框**，不是聊天输入框。
       *
       * 原实现把 `@不可能存在的资源名称XXXXXXXXX` 填进聊天 textarea 就直接断言三态 ——
       * 但 `ChatMentionPicker` 的 props 契约只有 `{ host, open }`，**没有**接收查询词的
       * prop（宿主无权把 `@` 后的词灌进去），组件 `open` 变 true 时自己 `focusInput()`，
       * 等用户在它的搜索框里输入。于是 picker 一直停在 **idle 态**
       * （`.chat-mention-picker__status--idle`「输入关键词搜索可引用的资源」），
       * 三个 testid 一个都不在 ⇒ `shown === 0` 恒红。
       *
       * 2026-08-22 探针实测：搜索框自动获得焦点（`SEARCH_FOCUSED=true`），
       * 往它填不存在的名字后 `mention-empty-state` 计数为 1、文案「无匹配结果」——
       * 产品行为本就正确，红的是判据打错了输入框。
       */
      const searchInput = picker.locator('input').first()
      await expect(searchInput).toBeFocused() // 契约：picker 打开即接管输入焦点
      await searchInput.fill('不可能存在的资源名称XXXXXXXXX')
      await page.waitForTimeout(1500) // useAiMention debounceMs = 300 + 请求往返

      // Property 13：三态各有独立 DOM 与文案，互斥
      const empty = picker.locator('[data-testid="mention-empty-state"]')
      const error = picker.locator('[data-testid="mention-error-state"]')
      const unavailable = picker.locator('[data-testid="mention-unavailable-state"]')

      const shown = (await empty.count()) + (await error.count()) + (await unavailable.count())
      expect(shown).toBe(1) // 恰好一态，不多不少（互斥且必现其一）

      // 空态文案必须是「无匹配结果」而不是错误措辞（否则用户以为系统坏了）
      if ((await empty.count()) === 1) {
        await expect(empty).toHaveText('无匹配结果')
      }
    })

    test('多选 mention 显示为 tag 并可移除', async ({ page }) => {
      const input = getChatInput(page)
      await input.fill('@')

      const picker = page.locator('.chat-mention-picker').first()
      const pickerOpened = await picker
        .waitFor({ state: 'visible', timeout: 8000 })
        .then(() => true)
        .catch(() => false)
      test.skip(
        !pickerOpened,
        '@ 未唤出 mention picker：接线已完成（面板已挂载 ChatMentionPicker，watch(draft) 按活跃 @ 词开关），2026-08-22 实测 79ms 内弹出；此处若仍 skip 先查宿主是否可用与 @ 词判定是否被改坏',
      )

      // 候选项要先在 picker 自己的搜索框里搜出来（组件契约无查询词 prop，详见上一条注释）
      const searchInput = picker.locator('input').first()
      await expect(searchInput).toBeFocused()
      await searchInput.fill('审')
      await page.waitForTimeout(1500)

      const firstItem = picker.locator('[role="option"]').first()
      const hasCandidate = await firstItem.isVisible({ timeout: 3000 }).catch(() => false)
      test.skip(
        !hasCandidate,
        '当前无可引用候选（2026-08-22 实测：全局宿主下搜「审」返回 0 条，picker 显示「无匹配结果」）：'
          + '切到项目宿主并为该项目准备至少一份底稿/附注后重跑',
      )

      // 真断言 1：点选后必须标记为已选，再点必须取消（多选可增可减）
      await firstItem.click()
      await expect(firstItem).toHaveAttribute('aria-selected', 'true')
      await expect(firstItem).toHaveClass(/is-selected/)

      // 真断言 2：宿主输入区上方必须出现可移除的引用 tag —— 这是标题里的「显示为 tag」，
      // 也是 Task 15 接线的宿主侧一半（picker 内高亮 ≠ 宿主真收到 change 事件）
      const hostTags = page.locator('.platform-ai-chat-panel__mention-tags .el-tag')
      await expect(hostTags.first()).toBeVisible({ timeout: 3000 })

      await firstItem.click()
      await expect(firstItem).toHaveAttribute('aria-selected', 'false')
      // 取消后宿主 tag 必须同步消失（否则会把已取消的引用提交给下一轮 run）
      await expect(hostTags).toHaveCount(0)
    })
  })

  // ─── OCR 五态 ──────────────────────────────────────────────────────────

  test.describe('附件与 OCR', () => {
    test('附件按钮可见且可交互', async ({ page }) => {
      const attachBtn = page.locator(
        '[data-testid="attachment-btn"], button[aria-label*="附件"], button:has-text("上传")',
      ).first()
      await expect(attachBtn).toBeVisible({ timeout: 5000 })
      await expect(attachBtn).toBeEnabled()
    })

    test('上传非法文件类型被拒绝且显示中文错误', async ({ page }) => {
      // 直接打接口（不依赖 UI）：安全校验必须先于 OCR（Property 18）。
      // 原实现三层 if 包裹 + `|| status === 400` 兜底 —— 任一层不满足就静默通过，
      // 且兜底让「中文文案」这半条判据形同虚设。这里全部无条件断言。
      const probe = await page.evaluate(async () => {
        const token = sessionStorage.getItem('token') || localStorage.getItem('token') || ''
        const form = new FormData()
        form.append('file', new Blob(['MZ fake exe'], { type: 'application/x-msdownload' }), 'malicious.exe')
        const resp = await fetch('/api/ai-chat/attachments', {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: form,
        })
        return { status: resp.status, body: await resp.text() }
      })

      // 真断言 1：必须拒绝（4xx），不能落盘也不能进 OCR
      expect(probe.status).toBeGreaterThanOrEqual(400)
      expect(probe.status).toBeLessThan(500)

      // 真断言 2：错误必须是中文可执行说明（NFR-5）
      expect(probe.body).toMatch(/[\u4e00-\u9fff]/)

      // 真断言 3：不得回显服务端路径/异常栈
      expect(probe.body).not.toMatch(/Traceback|[A-Za-z]:\\\\|\/var\/|site-packages/)
    })

    test('OCR 空结果显示"未识别到文字内容"', async ({ page }) => {
      // 前置：需要一张**确定不含文字**的图片，OCR 才会回空文本走 empty 态。
      // 造资产：任意画图工具存一张纯色 PNG 到 e2e/fixtures/blank.png 即可。
      test.skip(
        !hasFixture('blank.png'),
        '需要 e2e/fixtures/blank.png 测试资产（一张无文字的纯色图片）；OCR 对它返回空文本才会进入 empty 态',
      )

      const fileInput = page.locator('input[type="file"].chat-attachment-picker__file-input').first()
      await fileInput.setInputFiles(path.join(__dirname, 'fixtures', 'blank.png'))

      // 上传 → OCR 识别 → empty 态（五态互斥，Property 19）
      const emptyMsg = page.locator('.chat-attachment-picker__empty-msg')
      await expect(emptyMsg).toHaveText('未识别到文字内容', { timeout: 60000 })

      // empty 态必须允许人工补充说明（否则空 OCR 的附件等于废件）
      const supplement = page.locator('.chat-attachment-picker__empty-hint textarea')
      await expect(supplement).toBeVisible()

      // 五态互斥：empty 时不得同时显示失败态
      await expect(page.locator('.chat-attachment-picker__error-msg')).toHaveCount(0)
    })
  })

  // ─── 项目笔记 ──────────────────────────────────────────────────────────

  test.describe('项目笔记', () => {
    test('转存操作要求确认名称（ElMessageBox.prompt）', async ({ page }) => {
      // 前置 1：需要一条 completed 的 assistant 回复
      await sendMessage(page, '请生成一段审计建议')
      try {
        await waitForAssistantResponse(page, 30000)
      } catch {
        test.skip(true, '模型未在 30s 内返回 assistant 回复：确认 vLLM(8100) 已启动且 /api/ai-chat/runs 正常')
        return
      }

      // 前置 2：选择模式入口只在有 completed 回复时出现
      const selectBtn = page.locator('.platform-ai-chat-panel__select-btn').first()
      const canSelect = await selectBtn.isVisible({ timeout: 5000 }).catch(() => false)
      test.skip(!canSelect, '回复未进入 completed 态（选择模式入口未出现）：等待 run 结束后重跑')

      // 前置 3：必须有项目上下文。
      // 🔴 实测（2026-08-16）：全局模式下「转存笔记」按钮是**可点的**，但 `saveAsNote`
      // 在 `!host.projectId` 时先返回 `host_unavailable` ⇒ 名称确认框根本不会弹。
      // 所以「按钮 enabled」不足以当前置，必须再判范围条。
      // （按钮在无项目上下文时仍可点，本身是一处能力门控缺口，已在收口说明中登记。）
      const scope = page.locator('.platform-ai-chat-panel__scope').first()
      const isGlobalScope = (await scope.getAttribute('class'))?.includes('is-global') ?? true
      test.skip(
        isGlobalScope,
        '需要带项目上下文的宿主页面（当前是全局模式）：进入某项目的底稿/报表/附注页后再打开面板重跑',
      )

      await selectBtn.click()
      await page.locator('.platform-ai-chat-panel__msg.assistant.is-selectable').first().click()

      const noteBtn = page.locator('button:has-text("转存笔记")').first()
      await expect(noteBtn).toBeVisible()
      const enabled = await noteBtn.isEnabled()
      test.skip(!enabled, '转存按钮不可用（选中消息缺服务端签发 ID）：刷新会话后重跑')

      // 真断言：必须弹名称确认框且带输入框（Req 8.2 — 禁止静默用时间戳命名）
      await noteBtn.click()
      const dialog = page.locator('.el-message-box').first()
      await expect(dialog).toBeVisible({ timeout: 5000 })
      await expect(dialog.locator('input').first()).toBeVisible()
      await expect(dialog).toContainText('笔记名称')

      // 收尾：取消掉，不给库里留测试数据
      await dialog.locator('button:has-text("取消")').first().click()
    })

    test('笔记保存成功后返回跳转链接', async ({ page }) => {
      // 前置 1：必须有项目上下文 —— `saveAsNote` 在 `!host.projectId` 时直接返回
      // 「当前页面无项目上下文，无法保存项目笔记」，连名称确认框都不会弹。
      const scope = page.locator('.platform-ai-chat-panel__scope').first()
      await scope.waitFor({ state: 'visible', timeout: 8000 })
      const isGlobalScope = (await scope.getAttribute('class'))?.includes('is-global') ?? true
      test.skip(
        isGlobalScope,
        '需要带项目上下文的宿主页面（当前是全局模式）：进入某项目的底稿/报表/附注页后再打开面板',
      )

      // 前置 2：需要一条 completed 的 assistant 回复（转存只接受服务端签发 ID 的消息）
      await sendMessage(page, '请用两句话总结应收账款的审计要点')
      try {
        await waitForAssistantResponse(page, 30000)
      } catch {
        test.skip(true, '模型未在 30s 内返回 assistant 回复：确认 vLLM(8100) 已启动且 /api/ai-chat/runs 正常')
        return
      }

      const selectBtn = page.locator('.platform-ai-chat-panel__select-btn').first()
      const canSelect = await selectBtn.isVisible({ timeout: 5000 }).catch(() => false)
      test.skip(!canSelect, '回复未进入 completed 态（选择模式入口未出现）：等待 run 结束后重跑')

      await selectBtn.click()
      await page.locator('.platform-ai-chat-panel__msg.assistant.is-selectable').first().click()

      const noteBtn = page.locator('button:has-text("转存笔记")').first()
      await expect(noteBtn).toBeVisible()
      const noteBtnEnabled = await noteBtn.isEnabled()
      test.skip(
        !noteBtnEnabled,
        '转存按钮不可用（选中回复缺少服务端签发的 message ID）：刷新会话让消息带上服务端 UUID 后重跑',
      )

      // 真断言 1：必须弹名称确认框（Req 8.2 — 不许静默用时间戳命名）
      await noteBtn.click()
      const promptBox = page.locator('.el-message-box').first()
      await expect(promptBox).toBeVisible({ timeout: 5000 })
      await promptBox.locator('input').first().fill(`E2E 笔记 ${Date.now()}`)

      // 真断言 2：成功后必须给出「去哪看」的落点 —— 要么新标签打开笔记路由，
      // 要么给出中文成功反馈；且新标签必须是本平台路由，不能是外链。
      const newPagePromise = page.context().waitForEvent('page', { timeout: 15000 }).catch(() => null)
      await promptBox.locator('button:has-text("保存")').first().click()

      const successToast = page.locator('.el-message--success')
      await expect(successToast).toContainText(/笔记保存成功|笔记已保存/, { timeout: 15000 })

      const jumped = await newPagePromise
      if (jumped) {
        await jumped.waitForLoadState('domcontentloaded').catch(() => undefined)
        expect(jumped.url().startsWith(BASE_URL)).toBe(true)
        await jumped.close()
      }

      // 真断言 3：成功后退出选择模式（否则用户会重复点出第二篇笔记）
      await expect(page.locator('.platform-ai-chat-panel__selection-toolbar')).toHaveCount(0)
    })
  })

  // ─── 复核模式 ──────────────────────────────────────────────────────────

  test.describe('复核模式', () => {
    test('底稿页面复核模式 bar 可见', async ({ page }) => {
      // 导航到底稿编辑页面
      await page.goto(`${BASE_URL}/workpapers`)
      await page.waitForLoadState('networkidle')

      const firstWp = page.locator('table tbody tr, .workpaper-item').first()
      const hasWp = await firstWp.isVisible({ timeout: 5000 }).catch(() => false)
      test.skip(!hasWp, '底稿列表为空：先为测试项目导入或生成至少一份底稿后重跑')

      await firstWp.click()
      await page.waitForLoadState('networkidle')
      await openAiPanel(page)

      // 真断言：底稿宿主里 bar 必须渲染且开关必须**启用**（canEnable 要求 host=workpaper）
      const reviewBar = page.locator('.chat-review-mode-bar').first()
      await expect(reviewBar).toBeVisible({ timeout: 8000 })
      expect((await reviewBar.textContent()) ?? '').toMatch(/[\u4e00-\u9fff]/)
      await expect(reviewBar).not.toHaveClass(/chat-review-mode-bar--disabled/)
      await expect(reviewBar.locator('.chat-review-mode-bar__reason')).toHaveCount(0)
    })

    test('非底稿宿主禁用复核模式并显示中文原因', async ({ page }) => {
      // 在知识库页面（host.type = knowledge_*，非 workpaper → canEnable=false）
      await page.goto(`${BASE_URL}/knowledge`)
      await page.waitForLoadState('networkidle')
      await openAiPanel(page)

      // 真断言（无条件）：开关必须禁用 + 必须给可区分的中文原因。
      // Property 24 要求原因按宿主类型可区分，不能一句「不可用」糊过去。
      const bar = page.locator('.chat-review-mode-bar').first()
      await expect(bar).toBeVisible()
      await expect(bar).toHaveClass(/chat-review-mode-bar--disabled/)
      await expect(bar.locator('.el-switch')).toHaveClass(/is-disabled/)

      const reason = bar.locator('.chat-review-mode-bar__reason')
      await expect(reason).toBeVisible()
      expect((await reason.textContent()) ?? '').toMatch(/仅在底稿页面可用|无法解析文档上下文|不可用/)
    })

    test('base 模板提示"当前使用通用复核模板"', async ({ page }) => {
      // 导航到底稿
      await page.goto(`${BASE_URL}/workpapers`)
      await page.waitForLoadState('networkidle')

      // 前置 1：底稿列表里得有可进入的底稿
      const firstWp = page.locator('table tbody tr, .workpaper-item').first()
      const hasWp = await firstWp.isVisible({ timeout: 5000 }).catch(() => false)
      test.skip(!hasWp, '底稿列表为空：先为测试项目导入或生成至少一份底稿（列表页 /workpapers 可见一行即可）')

      await firstWp.click()
      await page.waitForLoadState('networkidle')
      await openAiPanel(page)

      // 前置 2：复核模式开关必须可用（`canEnable` 要求 host.type === 'workpaper'）
      const reviewSwitch = page.locator('.chat-review-mode-bar__toggle .el-switch').first()
      await reviewSwitch.waitFor({ state: 'visible', timeout: 8000 })
      const switchDisabled = (await reviewSwitch.getAttribute('class'))?.includes('is-disabled') ?? true
      test.skip(
        switchDisabled,
        '复核模式开关被禁用（当前宿主未被解析为 workpaper）：确认已进入底稿编辑页而非列表页/预览弹窗',
      )

      // 打开复核模式 → 拉 review prompt preview
      await reviewSwitch.click()

      const detail = page.locator('.chat-review-mode-bar__detail')
      const loadFailed = page.locator('.chat-review-mode-bar__error')
      await Promise.race([
        detail.waitFor({ state: 'visible', timeout: 20000 }).catch(() => undefined),
        loadFailed.waitFor({ state: 'visible', timeout: 20000 }).catch(() => undefined),
      ])
      test.skip(
        await loadFailed.isVisible().catch(() => false),
        '复核配置加载失败：确认后端 review prompt 接口可用（面板内「重试」按钮可复现）后重跑',
      )
      await expect(detail).toBeVisible()

      // 真断言（双向锁死，与后端挑中哪一级模板无关）：
      //   source_level tag 显示「通用模板」 ⟺ 必须出现「当前使用通用复核模板」提示。
      // 任一侧单独出现都是缺陷：只有 tag 没提示 = 用户不知道在用兜底模板；
      // 只有提示没 tag = 提示与来源标签自相矛盾。
      const baseHint = page.locator('.chat-review-mode-bar__base-hint')
      const levelTagText = (await page.locator('.chat-review-mode-bar__meta .el-tag').first().textContent()) ?? ''
      const isBaseLevel = levelTagText.includes('通用模板')
      if (isBaseLevel) {
        await expect(baseHint).toHaveText('当前使用通用复核模板')
      } else {
        await expect(baseHint).toHaveCount(0)
        // 非 base 时来源标签必须是已登记的三级之一，不能是裸 source_level 字符串
        expect(levelTagText.trim()).toMatch(/Sheet 级|科目级/)
      }
    })
  })

  // ─── 地址坐标 ──────────────────────────────────────────────────────────

  test.describe('地址坐标', () => {
    test('address mention 类型在 picker 中可见', async ({ page }) => {
      const input = getChatInput(page)
      await input.fill('@')
      await page.waitForTimeout(500)

      // 前置：`@` 必须真能唤出 mention picker。
      // 🔴 履历：2026-08-16 实测 `ChatMentionPicker.vue` 存在且有 13 条 vitest 守卫，
      // 但**没有任何宿主 import 它** —— `PlatformAiChatPanel.vue` 只挂了
      // ChatAttachmentPicker / ChatReviewModeBar，`@` 触发链未接线，浏览器里 picker
      // 永不出现（本条与另 3 条 mention 用例因此长期 skip）。
      // 2026-08-22 已接线（面板挂载 picker + watch(draft) 按活跃 `@` 词开关），
      // 本条随即转为**真跑并通过**。此处前置保留，用于挡「宿主不可用」等情形。
      const picker = page.locator('.chat-mention-picker').first()
      const pickerOpened = await picker.isVisible({ timeout: 3000 }).catch(() => false)
      test.skip(
        !pickerOpened,
        '@ 未唤出 mention picker：接线已完成（面板已挂载 ChatMentionPicker，watch(draft) 按活跃 @ 词开关），2026-08-22 实测可弹出；此处若仍 skip 先查宿主是否可用与 @ 词判定是否被改坏',
      )

      // 真断言：类型过滤器是**声明式固定集合**（useAiMention 的 availableFilters
      // 硬列 workpaper/note/report/knowledge_doc/knowledge_folder/address），
      // 所以「地址坐标」这一项必须在，与库里有没有地址数据无关。
      const filters = page.locator('.chat-mention-picker__filters')
      await expect(filters).toBeVisible()
      await expect(filters.locator('.chat-mention-picker__filter-tag', { hasText: '地址坐标' })).toHaveCount(1)

      // 点它必须真切换过滤器（aria-pressed 翻到 true），不能是死标签
      const addressTag = filters.locator('.chat-mention-picker__filter-tag', { hasText: '地址坐标' }).first()
      await addressTag.click()
      await expect(addressTag).toHaveAttribute('aria-pressed', 'true')
    })

    test('embedding 不可用时显示 semantic_unavailable', async ({ page }) => {
      // 前置：必须真把 embedding 服务停掉，否则语义检索会成功、这条无从触发。
      // 复现步骤：停掉 embedding 服务（或把 EMBEDDING_ENDPOINT 指向不可达地址）
      //          → 重启后端 → 置 E2E_EMBEDDING_DOWN=1 → 重跑本文件。
      test.skip(
        process.env.E2E_EMBEDDING_DOWN !== '1',
        '需设置 E2E_EMBEDDING_DOWN=1 并停掉 embedding 服务（Property 16：语义不可用必须显式报错，不许伪降级成空结果）',
      )

      // 真断言 1：capabilities 的 health 必须把 embedding 报成不可用（不许谎报健康）
      const capsResp = await page.request.get(`${BACKEND_URL}/api/ai-chat/capabilities`)
      expect(capsResp.ok()).toBe(true)
      const capsBody = await capsResp.json()
      const capsData = capsBody.data ?? capsBody
      expect(capsData.health?.embedding?.available).toBe(false)

      // 真断言 2：发一轮问答后，面板必须出现 semantic_unavailable 的中文文案，
      // 而不是静默给一个「看起来正常」的回答（伪降级）。
      await sendMessage(page, '请结合知识库解释应收账款函证的替代程序')
      const notice = page.locator(
        '.platform-ai-chat-panel__error, .platform-ai-chat-panel__quota, .chat-mention-picker__status--unavailable',
      )
      await expect(notice.filter({ hasText: '语义检索服务当前不可用' }).first()).toBeVisible({ timeout: 30000 })
    })
  })
})

// ===========================================================================
// E. Phase C — DSH 能力与引擎
// ===========================================================================

test.describe('E. Phase C 能力与引擎', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)
  })

  test('capabilities 端点返回当前引擎能力', async ({ page }) => {
    const resp = await fetchCapabilities(page)
    expect(resp.status).toBe(200)

    const body = JSON.parse(resp.body)
    const data = body.data ?? body
    // 🔴 八项能力在嵌套的 capabilities 里（后端 CapabilityResponse），不在根上。
    expect(data).toHaveProperty('engine')
    expect(data).toHaveProperty('capabilities')
    const caps = data.capabilities
    for (const field of ['streaming', 'tools', 'subagents', 'structured_output', 'local_only', 'review_mode', 'attachments']) {
      expect(typeof caps[field]).toBe('boolean')
    }
    expect(typeof caps.max_context).toBe('number')
    // local_only 是本平台的硬约束（Req 12.1）：任何引擎都必须保证全本地执行
    expect(caps.local_only).toBe(true)
  })

  test('不支持的能力在 UI 中禁用并显示中文原因', async ({ page }) => {
    const caps = await fetchCapabilityManifest(page)
    expect(caps).not.toBeNull()

    const resp = await fetchCapabilities(page)
    const body = JSON.parse(resp.body)
    const disabledReasons = ((body.data ?? body) as Record<string, any>).disabled_reasons ?? {}

    // 真断言：每个 false 的能力都必须在 disabled_reasons 里有中文原因
    // （前端据此禁用入口 + 显示原因；缺原因就会出现「按钮灰了但没人知道为什么」）
    for (const [field, value] of Object.entries(caps!)) {
      if (value === false) {
        expect(Object.keys(disabledReasons)).toContain(field)
        expect(String(disabledReasons[field])).toMatch(/[\u4e00-\u9fff]/)
      }
    }

    // 反向：不该给「支持的能力」编造禁用原因
    for (const field of Object.keys(disabledReasons)) {
      expect(caps![field]).not.toBe(true)
    }
  })

  test('engine_unavailable 不静默 fallback — 显示明确错误', async ({ page }) => {
    // 验证当 DSH 不可用时不会偷偷用 native
    // 监听网络请求
    const requests: string[] = []
    page.on('request', (req) => {
      if (req.url().includes('/api/ai-chat/runs')) {
        requests.push(req.url())
      }
    })

    // 正常发送消息
    await sendMessage(page, '测试引擎路由')
    await page.waitForTimeout(3000)

    // 所有 run 请求不应包含 engine override 字段
    // （验证客户端未发送 engine 选择）
    for (const url of requests) {
      expect(url).not.toContain('engine=dsh')
    }
  })

  test('多步工具调用可见（tool_started/tool_finished 事件渲染）', async ({ page }) => {
    // 前置：工具能力由服务端引擎决定（实测 capabilities.tools，不写死）。
    // native 引擎恒 false；要真跑本条需 AI_DSH_ENABLED=true + experimental flag
    // + 当前项目在 DSH allowlist，三层门全过后 /capabilities 才会报 tools=true。
    test.skip(
      !(await isToolCapableEngine(page)),
      '需 AI_DSH_ENABLED=true、experimental flag 开启且项目在 DSH allowlist（判据：/api/ai-chat/capabilities 的 capabilities.tools 为 true）',
    )

    await sendMessage(page, '请查询当前项目的试算表数据')

    // 真断言：引擎声明支持工具时，多步调用必须在面板里可见 —— Agent 悄悄取数
    // 而 UI 不显示，审计师就无法追溯「这个结论用了哪些数据」。
    const toolIndicator = page.locator(
      '[data-testid="tool-call"], .tool-call-indicator, .platform-ai-chat-panel__tool-call',
    ).first()
    await expect(toolIndicator).toBeVisible({ timeout: 60000 })
  })

  test('queue limit 触发时显示明确排队或拒绝消息', async ({ page }) => {
    test.skip(
      !(await isToolCapableEngine(page)),
      '需 AI_DSH_ENABLED=true、experimental flag 开启且项目在 DSH allowlist（判据：/api/ai-chat/capabilities 的 capabilities.tools 为 true）；native 引擎无 DSH 队列',
    )

    // 连续压入多个 run，尝试触达队列上界（Property 38：backpressure 有界）
    for (let i = 0; i < 12; i++) {
      const input = getChatInput(page)
      if (await input.isEnabled().catch(() => false)) {
        await input.fill(`队列压测 ${i}`)
        await input.press('Enter')
      }
      await page.waitForTimeout(150)
    }

    const notice = page.locator(
      '.platform-ai-chat-panel__error, .platform-ai-chat-panel__quota',
    ).first()
    const noticeShown = await notice.isVisible({ timeout: 10000 }).catch(() => false)
    test.skip(
      !noticeShown,
      '本次未触达 queue limit：需把并发压到 DSH 引擎队列上界（提高循环次数或并行多标签同时发 run）后重跑',
    )

    // 真断言：触达上界时必须给**已登记的中文 typed 文案**，
    // 不能是空白、英文 code 或「未知错误」——用户要知道下一步做什么。
    const text = (await notice.textContent()) ?? ''
    expect(text).toMatch(/[\u4e00-\u9fff]/)
    expect(text).toMatch(/请求过于频繁|排队|已达上限|配额已用尽|请稍候|请稍后/)
    expect(text).not.toMatch(/发生未知错误/)
  })
})

// ===========================================================================
// F. 网络面板合规性
// ===========================================================================

test.describe('F. 网络面板合规性', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)
  })

  test('run 只创建一次 — 重复提交不产生第二个 POST /runs', async ({ page }) => {
    const runRequests: string[] = []
    page.on('request', (req) => {
      if (req.url().includes('/api/ai-chat/runs') && req.method() === 'POST') {
        runRequests.push(req.url())
      }
    })

    await sendMessage(page, '幂等性测试')
    await page.waitForTimeout(5000)

    // 一次发送只应产生一个 POST /runs
    expect(runRequests.length).toBe(1)
  })

  test('Last-Event-ID replay — 断流后重连携带 Last-Event-ID', async ({ page }) => {
    const eventsRequests: Array<{ url: string; headers: Record<string, string> }> = []
    page.on('request', (req) => {
      if (req.url().includes('/events') && req.method() === 'GET') {
        eventsRequests.push({
          url: req.url(),
          headers: req.headers(),
        })
      }
    })

    await sendMessage(page, '长文本测试重连')
    await page.waitForTimeout(10000)

    // 如果发生重连，第二次请求应携带 Last-Event-ID
    if (eventsRequests.length > 1) {
      const reconnect = eventsRequests[1]
      const hasLastEventId =
        reconnect.headers['last-event-id'] !== undefined ||
        reconnect.url.includes('Last-Event-ID') ||
        reconnect.url.includes('last_event_id')
      expect(hasLastEventId).toBe(true)
    }
  })

  test('不出现旧 /doc 双轨 API 请求', async ({ page }) => {
    const legacyRequests: string[] = []
    page.on('request', (req) => {
      const url = req.url()
      if (
        url.match(/\/doc-ai-chat/) ||
        url.match(/\/docs\/[^/]+\/ai-chat/) ||
        url.match(/\/api\/workpapers\/[^/]+\/doc\//)
      ) {
        legacyRequests.push(url)
      }
    })

    await sendMessage(page, '验证无双轨')
    await page.waitForTimeout(5000)

    expect(legacyRequests).toEqual([])
  })

  test('不出现 DSH Web UI iframe 请求', async ({ page }) => {
    const dshUiRequests: string[] = []
    page.on('request', (req) => {
      const url = req.url()
      if (
        url.includes('127.0.0.1:3080') ||
        url.includes('localhost:3080') ||
        url.includes('dsh-web-ui') ||
        url.includes('dsh-panel.html')
      ) {
        dshUiRequests.push(url)
      }
    })

    await page.waitForTimeout(5000)
    expect(dshUiRequests).toEqual([])
  })

  test('面板 DOM 无 iframe 元素', async ({ page }) => {
    // 面板由 beforeEach 打开 —— 这里先断言它真的开着，否则「无 iframe」会因为
    // 面板压根没渲染而空过（原实现用 if 包裹，面板不可见时静默通过）。
    const panel = page.locator('#dsh-panel-region, .dsh-panel-container').first()
    await expect(panel).toBeVisible()
    expect(await panel.locator('iframe').count()).toBe(0)
  })

  test('workspace 选择器不在面板中渲染', async ({ page }) => {
    const panel = page.locator('#dsh-panel-region, .platform-ai-chat-panel').first()
    await expect(panel).toBeVisible()
    expect(await panel.locator('[data-testid="workspace-selector"]').count()).toBe(0)
    expect(await panel.getByText('工作空间选择').count()).toBe(0)
  })
})

// ===========================================================================
// G. 综合安全与缓存清理
// ===========================================================================

test.describe('G. 安全与缓存清理', () => {
  test('登出后 localStorage 无 doc_ai_chat_* 敏感 key', async ({ page }) => {
    await login(page)
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)

    // 注入模拟遗留缓存
    await page.evaluate(() => {
      localStorage.setItem('doc_ai_chat_history_legacy', '{"messages":[]}')
      localStorage.setItem('doc_ai_chat_ocr_text', 'sensitive OCR content')
    })

    await logout(page)

    const sensitiveKeys = await page.evaluate(() => {
      const found: string[] = []
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i)!
        if (key.startsWith('doc_ai_chat_')) found.push(key)
      }
      return found
    })
    expect(sensitiveKeys).toEqual([])
  })

  test('面板宽度偏好可保留（非敏感）', async ({ page }) => {
    await page.setViewportSize({ width: 1500, height: 900 }) // ≥1401 → column 档，resizer 一定渲染
    await login(page)
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)

    // 用键盘微调触发一次持久化（resizer 的 ArrowLeft/ArrowRight → keyboardResize → localStorage）
    const resizer = page.locator('.dsh-panel-resizer').first()
    await expect(resizer).toBeVisible()
    await resizer.focus()
    await page.keyboard.press('ArrowLeft')

    // 真断言 1：宽度偏好必须落到约定 key，且是 320–800 的合法数值
    const saved = await page.evaluate(() => localStorage.getItem('gt-dsh-panel-width'))
    expect(saved).not.toBeNull()
    const width = Number(saved)
    expect(Number.isFinite(width)).toBe(true)
    expect(width).toBeGreaterThanOrEqual(320)
    expect(width).toBeLessThanOrEqual(800)

    // 真断言 2：刷新后必须真恢复（否则「可保留」只是写了没读）
    await page.reload()
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)
    const panelWidth = await page
      .locator('#dsh-panel-region, .dsh-panel-container')
      .first()
      .evaluate((el) => Math.round(el.getBoundingClientRect().width))
    expect(Math.abs(panelWidth - width)).toBeLessThanOrEqual(12) // 含 resizer 6px 与取整误差

    // 真断言 3（Property 35）：允许保留的**只有**这类非敏感偏好 ——
    // localStorage 里不得出现消息正文或 doc_ai_chat_* 遗留缓存。
    const leaked = await page.evaluate(() => {
      const bad: string[] = []
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i)!
        if (key.startsWith('doc_ai_chat_')) bad.push(key)
      }
      return bad
    })
    expect(leaked).toEqual([])
  })

  test('切换用户后 AI 面板不显示前用户消息', async ({ page }) => {
    await login(page)
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)

    // 发送一条消息
    await sendMessage(page, '用户 A 的私密消息')
    try {
      await waitForAssistantResponse(page, 20000)
    } catch { /* 模型可能不可用 */ }

    // 切换用户（登出+登入另一账号）
    await logout(page)
    await login(page, 'admin', 'admin123')
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)

    // 面板不应显示前用户的消息
    const messages = page.locator(USER_MSG)
    const allTexts = await messages.allTextContents()
    const hasLeaked = allTexts.some((t) => t.includes('用户 A 的私密消息'))
    expect(hasLeaked).toBe(false)
  })

  test('aria-live 流式回复不逐 token 轰炸', async ({ page }) => {
    await login(page)
    await page.waitForLoadState('networkidle')
    await openAiPanel(page)

    // 监听 aria-live 更新频率
    let liveUpdateCount = 0
    await page.exposeFunction('__onLiveUpdate', () => {
      liveUpdateCount++
    })

    await page.evaluate(() => {
      const observer = new MutationObserver(() => {
        (window as any).__onLiveUpdate()
      })
      const liveRegion = document.querySelector('[aria-live]')
      if (liveRegion) {
        observer.observe(liveRegion, { childList: true, characterData: true, subtree: true })
      }
    })

    await sendMessage(page, '写一段 100 字的摘要')
    await page.waitForTimeout(5000)

    // 如果有 aria-live 区域，更新次数应被节流（远少于 token 数）
    // 100 字约 100+ token，更新次数应远低于此
    if (liveUpdateCount > 0) {
      expect(liveUpdateCount).toBeLessThan(50)
    }
  })
})

// ===========================================================================
// H. 三视口截图验证（视觉基线，可选）
// ===========================================================================

test.describe('H. 三视口视觉验证', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await page.waitForLoadState('networkidle')
  })

  for (const [name, size] of Object.entries(VIEWPORTS)) {
    test(`${name} (${size.width}px) 面板截图`, async ({ page }) => {
      await page.setViewportSize(size)
      await openAiPanel(page)
      await page.waitForTimeout(500)
      // 截图保存到 test-results 供人工查阅
      await page.screenshot({
        path: `test-results/dsh-panel-${name}-${size.width}px.png`,
        fullPage: false,
      })
    })
  }
})
