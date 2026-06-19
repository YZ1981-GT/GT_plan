/**
 * Playwright E2E: 底稿编制指导面板（workpaper-editing-guidance）
 *
 * 验证编制指导浮动面板核心交互：
 * - 触发按钮可见
 * - 面板展开/折叠
 * - 编制说明 Tab 默认激活 + 来源徽章
 * - AI 对话 Tab 输入功能
 *
 * 依赖：后端 9980 + 前端 3030 运行 + 测试项目存在底稿
 * 环境变量未设时自动 skip（data-blocked 模式，不伪绿）
 */
import { test, expect } from '@playwright/test'
import {
  ensureTestProject,
  findWorkpaper,
  TEST_PROJECT_ID,
  type TestFixture,
} from './fixtures/ensure-test-project'

const BASE_URL = process.env.BASE_URL || 'http://localhost:3030'
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:9980'

// 使用一个已知的中等复杂度底稿（A1-15 核对表）或动态查找
const TARGET_WP_CODE = process.env.TEST_WP_CODE || 'A1-15'

let fixture: TestFixture
let wpId: string

test.describe('底稿编制指导面板', () => {
  test.beforeAll(async ({ request }) => {
    // 环境检测：后端未启动时整个文件 skip
    try {
      const resp = await request.get(`${BACKEND_URL}/api/health`)
      if (resp.status() !== 200) {
        test.skip()
        return
      }
    } catch {
      test.skip()
      return
    }

    // 验证测试项目存在
    fixture = await ensureTestProject(request, TEST_PROJECT_ID)
    if (!fixture.ready) {
      test.skip()
      return
    }

    // 查找目标底稿
    const wp = await findWorkpaper(request, fixture.token, TARGET_WP_CODE, TEST_PROJECT_ID)
    if (!wp.exists || !wp.wpId) {
      test.skip()
      return
    }
    wpId = wp.wpId
  })

  test.beforeEach(async ({ page }) => {
    if (!fixture?.ready || !wpId) {
      test.skip()
      return
    }

    // 登录
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[placeholder*="密码"]', 'admin123')
    await page.click('button:has-text("登录")')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })

    // 导航到底稿编辑器页面
    await page.goto(
      `${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers/${wpId}`,
    )
    await page.waitForLoadState('networkidle')
  })

  test('面板触发按钮可见', async ({ page }) => {
    // 验证右侧固定触发按钮可见
    const trigger = page.locator('.gt-guidance-trigger')
    await expect(trigger).toBeVisible({ timeout: 10000 })
    await expect(trigger).toContainText('编制指导')
  })

  test('点击展开面板', async ({ page }) => {
    // 点击触发按钮
    const trigger = page.locator('.gt-guidance-trigger')
    await expect(trigger).toBeVisible({ timeout: 10000 })
    await trigger.click()

    // 验证面板展开（380px 宽度）
    const panel = page.locator('.gt-guidance-panel')
    await expect(panel).toBeVisible({ timeout: 5000 })

    // 验证面板宽度为 380px
    const box = await panel.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.width).toBeCloseTo(380, -1) // 允许 ±10px 误差
  })

  test('编制说明 Tab 默认激活 + 来源徽章可见', async ({ page }) => {
    // 展开面板
    const trigger = page.locator('.gt-guidance-trigger')
    await expect(trigger).toBeVisible({ timeout: 10000 })
    await trigger.click()

    const panel = page.locator('.gt-guidance-panel')
    await expect(panel).toBeVisible({ timeout: 5000 })

    // 验证「编制说明」Tab 默认激活
    const activeTab = panel.locator('.el-tabs__item.is-active')
    await expect(activeTab).toContainText('编制说明')

    // 验证来源徽章可见（模板提取/知识库/通用提示 之一）
    const sourceBadge = panel.locator('.el-tag')
    await expect(sourceBadge.first()).toBeVisible({ timeout: 10000 })
    const badgeText = await sourceBadge.first().textContent()
    expect(['模板提取', '知识库', '通用提示']).toContain(badgeText?.trim())
  })

  test('折叠面板恢复触发按钮', async ({ page }) => {
    // 展开面板
    const trigger = page.locator('.gt-guidance-trigger')
    await expect(trigger).toBeVisible({ timeout: 10000 })
    await trigger.click()

    const panel = page.locator('.gt-guidance-panel')
    await expect(panel).toBeVisible({ timeout: 5000 })

    // 点击折叠按钮
    const foldBtn = panel.locator('.gt-guidance-panel__fold-btn')
    await foldBtn.click()

    // 面板消失
    await expect(panel).not.toBeVisible({ timeout: 3000 })

    // 触发按钮重新出现
    await expect(trigger).toBeVisible({ timeout: 3000 })
  })

  test('AI 对话 Tab 输入框可用', async ({ page }) => {
    // 展开面板
    const trigger = page.locator('.gt-guidance-trigger')
    await expect(trigger).toBeVisible({ timeout: 10000 })
    await trigger.click()

    const panel = page.locator('.gt-guidance-panel')
    await expect(panel).toBeVisible({ timeout: 5000 })

    // 检查 AI 对话 Tab 是否存在（取决于 WP_AI_SERVICE_ENABLED）
    const aiTab = panel.locator('.el-tabs__item:has-text("AI 对话")')
    const aiTabVisible = await aiTab.isVisible().catch(() => false)

    if (!aiTabVisible) {
      // AI 未启用 — 跳过此测试（不伪绿）
      test.skip()
      return
    }

    // 切换到 AI 对话 Tab
    await aiTab.click()

    // 验证输入框可见且可用
    const textarea = panel.locator('.gt-ai-chat__input-area textarea')
    await expect(textarea).toBeVisible({ timeout: 5000 })
    await expect(textarea).toBeEnabled()

    // 输入一个问题
    await textarea.fill('这个底稿的编制目的是什么？')

    // 验证发送按钮可用
    const sendBtn = panel.locator('.gt-ai-chat__input-area .el-button--primary')
    await expect(sendBtn).toBeEnabled()

    // 点击发送
    await sendBtn.click()

    // 验证 streaming 开始（打字动画 dots 出现）
    const typingDots = panel.locator('.gt-ai-chat__typing-dots')
    await expect(typingDots).toBeVisible({ timeout: 15000 })
  })
})
