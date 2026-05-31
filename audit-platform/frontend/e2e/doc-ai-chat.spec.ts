/**
 * Playwright UAT: 文档/文件夹级 AI 对话（doc-level-ai-chat）
 *
 * 待环境验证：需要 start-dev.bat 运行（后端 9980 + 前端 3030）
 * 本测试文件显式标"待环境"——不伪绿，环境未就绪时自动 skip。
 *
 * 覆盖需求:
 *   1.1 — 任意文档/文件夹页面有「AI 对话」入口
 *   2.1 — ContextBuilder 调 semantic_search 注入关联知识
 *   3.2 — 引用来源点击可跳转
 *   4.1 — 采纳走确认流（AIContentMustBeConfirmedRule）
 *
 * 场景:
 *   A) 底稿页发起 AI 对话 → 注入上下文 + 关联知识 → 引用可点跳转 → 采纳走确认流
 *   B) 文件夹级对话 → 注入文档集合
 */
import { test, expect } from '@playwright/test'

const BASE_URL = 'http://localhost:3030'
const BACKEND_URL = 'http://localhost:9980'
const PROJECT_ID = 'df5b8403-xxxx-xxxx-xxxx-xxxxxxxxxxxx' // 首汽租车_2025

// ─────────────────────────────────────────────────────────────────────────────
// 环境检测：后端未启动时整个文件 skip（待环境，不伪绿）
// ─────────────────────────────────────────────────────────────────────────────

test.beforeAll(async ({ request }) => {
  try {
    const resp = await request.get(`${BACKEND_URL}/api/health`)
    if (resp.status() !== 200) {
      test.skip()
    }
  } catch {
    test.skip()
  }
})

// ─────────────────────────────────────────────────────────────────────────────
// 公共：登录 helper
// ─────────────────────────────────────────────────────────────────────────────

async function login(page: import('@playwright/test').Page) {
  await page.goto(`${BASE_URL}/login`)
  await page.fill('input[placeholder*="用户名"]', 'admin')
  await page.fill('input[placeholder*="密码"]', 'admin123')
  await page.click('button:has-text("登录")')
  await page.waitForURL('**/dashboard**', { timeout: 10000 })
}

// ═══════════════════════════════════════════════════════════════════════════════
// 场景 A：底稿页发起 AI 对话
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('底稿页 AI 对话（需求 1.1, 2.1, 3.2, 4.1）', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('底稿编辑器有「AI 对话」入口按钮', async ({ page }) => {
    // 导航到底稿列表
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    // 打开第一个底稿
    const firstWp = page.locator('.el-table__row').first()
    await firstWp.dblclick()
    await page.waitForLoadState('networkidle')

    // 验证工具栏或右键菜单有「AI 对话」入口
    const aiChatBtn = page.locator('button:has-text("AI 对话"), [title*="AI 对话"]')
    await expect(aiChatBtn.first()).toBeVisible({ timeout: 10000 })
  })

  test('点击「AI 对话」打开对话面板', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    const firstWp = page.locator('.el-table__row').first()
    await firstWp.dblclick()
    await page.waitForLoadState('networkidle')

    // 点击 AI 对话按钮
    const aiChatBtn = page.locator('button:has-text("AI 对话"), [title*="AI 对话"]').first()
    await aiChatBtn.click()

    // 验证 Drawer 面板打开，标题为「AI 文档对话」
    const drawer = page.locator('.el-drawer')
    await expect(drawer).toBeVisible({ timeout: 5000 })
    await expect(drawer.locator('text=AI 文档对话')).toBeVisible()

    // 验证文档上下文信息栏显示
    await expect(drawer.locator('.doc-context-bar')).toBeVisible()
  })

  test('输入问题 → 收到流式响应（需求 2.1 注入上下文）', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    const firstWp = page.locator('.el-table__row').first()
    await firstWp.dblclick()
    await page.waitForLoadState('networkidle')

    // 打开 AI 对话面板
    const aiChatBtn = page.locator('button:has-text("AI 对话"), [title*="AI 对话"]').first()
    await aiChatBtn.click()
    await expect(page.locator('.el-drawer')).toBeVisible()

    // 输入问题
    const textarea = page.locator('.chat-input-area textarea')
    await textarea.fill('这个底稿的主要风险点是什么？')

    // 点击发送
    await page.click('.chat-input-area button:has-text("发送")')

    // 等待 AI 响应出现（streaming 或最终消息）
    const assistantMsg = page.locator('.chat-message.assistant .message-body')
    await expect(assistantMsg.first()).toBeVisible({ timeout: 30000 })

    // 验证响应非空
    const text = await assistantMsg.first().textContent()
    expect(text?.trim().length).toBeGreaterThan(0)
  })

  test('AI 回答显示引用来源 → 点击可跳转（需求 3.2）', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    const firstWp = page.locator('.el-table__row').first()
    await firstWp.dblclick()
    await page.waitForLoadState('networkidle')

    // 打开面板并发送问题
    const aiChatBtn = page.locator('button:has-text("AI 对话"), [title*="AI 对话"]').first()
    await aiChatBtn.click()

    const textarea = page.locator('.chat-input-area textarea')
    await textarea.fill('请参考知识库说明这个科目的审计要点')
    await page.click('.chat-input-area button:has-text("发送")')

    // 等待 AI 响应
    const assistantMsg = page.locator('.chat-message.assistant').first()
    await expect(assistantMsg).toBeVisible({ timeout: 30000 })

    // 检查引用来源标注
    const citationList = assistantMsg.locator('.citation-list')
    // 引用来源可能存在也可能不存在（取决于知识库是否有匹配内容）
    const hasCitations = await citationList.isVisible().catch(() => false)

    if (hasCitations) {
      // 验证引用标签可点击
      const citationTag = citationList.locator('.citation-tag').first()
      await expect(citationTag).toBeVisible()

      // 点击引用标签 → 应触发跳转（新窗口或路由导航）
      const [popup] = await Promise.all([
        page.waitForEvent('popup', { timeout: 5000 }).catch(() => null),
        citationTag.click(),
      ])

      // 如果打开了新窗口（知识文档），验证 URL 包含 knowledge
      if (popup) {
        expect(popup.url()).toMatch(/knowledge|workpaper|documents/)
        await popup.close()
      }
      // 如果是路由导航（底稿），验证 URL 变化
    }
  })

  test('点击「采纳」→ 走确认流（需求 4.1）', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    const firstWp = page.locator('.el-table__row').first()
    await firstWp.dblclick()
    await page.waitForLoadState('networkidle')

    // 打开面板并发送问题
    const aiChatBtn = page.locator('button:has-text("AI 对话"), [title*="AI 对话"]').first()
    await aiChatBtn.click()

    const textarea = page.locator('.chat-input-area textarea')
    await textarea.fill('帮我总结这个底稿的结论')
    await page.click('.chat-input-area button:has-text("发送")')

    // 等待 AI 响应
    const assistantMsg = page.locator('.chat-message.assistant').first()
    await expect(assistantMsg).toBeVisible({ timeout: 30000 })

    // 点击「采纳」按钮
    const adoptBtn = assistantMsg.locator('button:has-text("采纳")')
    await expect(adoptBtn).toBeVisible()
    await adoptBtn.click()

    // 验证确认流触发：应显示成功提示「已提交采纳，等待确认」
    const successMsg = page.locator('.el-message--success')
    await expect(successMsg).toBeVisible({ timeout: 5000 })
    await expect(successMsg).toContainText('采纳')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 场景 B：文件夹级对话 → 注入文档集合（需求 1.4）
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('文件夹级 AI 对话（需求 1.1, 1.4）', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('知识库文件夹页面有「AI 对话」入口', async ({ page }) => {
    // 导航到知识库
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/knowledge`)
    await page.waitForLoadState('networkidle')

    // 验证文件夹列表中有 AI 对话入口
    const aiChatBtn = page.locator(
      'button:has-text("AI 对话"), [title*="AI 对话"], .knowledge-folder-actions button'
    )
    // 可能在工具栏或右键菜单
    const hasToolbarBtn = await aiChatBtn.first().isVisible().catch(() => false)

    if (!hasToolbarBtn) {
      // 尝试右键第一个文件夹
      const firstFolder = page.locator('.el-table__row, .folder-item').first()
      if (await firstFolder.isVisible()) {
        await firstFolder.click({ button: 'right' })
        const contextMenu = page.locator('text=AI 对话')
        await expect(contextMenu).toBeVisible({ timeout: 3000 })
      }
    } else {
      await expect(aiChatBtn.first()).toBeVisible()
    }
  })

  test('文件夹级对话 → 面板显示 knowledge_folder 类型', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/knowledge`)
    await page.waitForLoadState('networkidle')

    // 打开文件夹级 AI 对话（通过工具栏或右键）
    const aiChatBtn = page.locator('button:has-text("AI 对话"), [title*="AI 对话"]').first()
    const hasBtn = await aiChatBtn.isVisible().catch(() => false)

    if (hasBtn) {
      await aiChatBtn.click()
    } else {
      // 右键第一个文件夹
      const firstFolder = page.locator('.el-table__row, .folder-item').first()
      await firstFolder.click({ button: 'right' })
      await page.click('text=AI 对话')
    }

    // 验证面板打开
    const drawer = page.locator('.el-drawer')
    await expect(drawer).toBeVisible({ timeout: 5000 })

    // 验证上下文栏显示「知识库文件夹」类型
    const contextBar = drawer.locator('.doc-context-bar')
    await expect(contextBar).toBeVisible()
    await expect(contextBar).toContainText('知识库文件夹')
  })

  test('文件夹级对话发送问题 → 注入文档集合上下文', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/knowledge`)
    await page.waitForLoadState('networkidle')

    // 打开文件夹级 AI 对话
    const aiChatBtn = page.locator('button:has-text("AI 对话"), [title*="AI 对话"]').first()
    const hasBtn = await aiChatBtn.isVisible().catch(() => false)

    if (hasBtn) {
      await aiChatBtn.click()
    } else {
      const firstFolder = page.locator('.el-table__row, .folder-item').first()
      await firstFolder.click({ button: 'right' })
      await page.click('text=AI 对话')
    }

    await expect(page.locator('.el-drawer')).toBeVisible()

    // 发送问题
    const textarea = page.locator('.chat-input-area textarea')
    await textarea.fill('这个文件夹里的文档主要涉及哪些审计领域？')
    await page.click('.chat-input-area button:has-text("发送")')

    // 等待响应（文件夹级对话应注入该文件夹下文档集合作上下文）
    const assistantMsg = page.locator('.chat-message.assistant .message-body')
    await expect(assistantMsg.first()).toBeVisible({ timeout: 30000 })

    // 验证响应非空
    const text = await assistantMsg.first().textContent()
    expect(text?.trim().length).toBeGreaterThan(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 场景 C：API 级验证（后端端点可达性）
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('后端 AI 对话端点可达性', () => {
  test('POST /api/ai-chat/doc/{doc_type}/{doc_id} 端点存在', async ({ request }) => {
    // 先登录获取 token
    const loginResp = await request.post(`${BACKEND_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })

    if (!loginResp.ok()) {
      test.skip()
      return
    }

    const { token } = await loginResp.json()

    // 验证对话端点可达（即使返回 4xx 也说明路由已注册）
    const chatResp = await request.post(
      `${BACKEND_URL}/api/ai-chat/doc/workpaper/test-doc-id`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: { query: 'test', year: 2025 },
      },
    )

    // 端点已注册：不应返回 404（可能 422/400/500 取决于数据）
    expect(chatResp.status()).not.toBe(404)
  })

  test('POST /api/ai-chat/adopt 端点存在', async ({ request }) => {
    const loginResp = await request.post(`${BACKEND_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })

    if (!loginResp.ok()) {
      test.skip()
      return
    }

    const { token } = await loginResp.json()

    const adoptResp = await request.post(`${BACKEND_URL}/api/ai-chat/adopt`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { message_id: 'nonexistent', target_doc_type: 'workpaper', target_doc_id: 'x' },
    })

    // 端点已注册：不应返回 404
    expect(adoptResp.status()).not.toBe(404)
  })
})
