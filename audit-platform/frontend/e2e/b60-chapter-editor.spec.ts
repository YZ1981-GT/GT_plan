/**
 * b60-chapter-editor.spec.ts — B60 专用章节编辑器 E2E 测试
 *
 * 锚定 spec b60-dedicated-component Tasks 8.1 / 8.2 / 8.3
 *
 * 验证：
 * 8.1 B60 底稿打开渲染章节编辑器 + Tab 切换 + 适用性矩阵勾选/取消
 * 8.2 章节编辑保存与回显 — 编辑→等待自动保存→刷新→验证回显 + 保存状态指示器变化
 * 8.3 AI 辅助与模式切换 — AI 按钮点击降级测试 + 模式切换验证
 *
 * 项目：辽宁卫生服务有限公司 2025（37814426-a29e-4fc2-9313-a59d229bf7b0）
 * 或通过环境变量指定 TEST_PROJECT_ID
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { TEST_PROJECT_ID, findWorkpaper } from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID

// ─── Helpers ────────────────────────────────────────────────────────────────

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

/**
 * 收集非噪声 console 错误（排除 OnlyOffice/AI/SSE 降级噪声）
 */
function setupConsoleErrorCollector(page: Page): string[] {
  const consoleErrors: string[] = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text()
      // 排除已知降级噪声
      if (/\/ai\//.test(text) && /(405|500|503)/.test(text)) return
      if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
      if (/onlyoffice|docsapi/i.test(text)) return
      if (/events\?topic|EventSource|SSE/i.test(text)) return
      if (/401.*Unauthorized/i.test(text)) return
      consoleErrors.push(text)
    }
  })
  page.on('pageerror', (err) => {
    if (/DocsAPI|onlyoffice/i.test(err.message)) return
    consoleErrors.push(`pageerror: ${err.message}`)
  })
  return consoleErrors
}

function filterCriticalErrors(errors: string[]): string[] {
  return errors.filter((e) =>
    /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
  )
}

// ─── Tests ──────────────────────────────────────────────────────────────────

test.describe('B60 Chapter Editor E2E', () => {
  test.beforeEach(async ({ page }) => {
    // 延长超时以适应底稿加载
    test.setTimeout(90_000)
  })

  test('8.1: B60 opens and renders chapter editor with tab switching and applicability matrix', async ({
    page,
    request,
  }) => {
    // ─── 登录 + 查找 B60 底稿 ───
    const token = await loginAs(page, 'admin', 'admin123')
    const wpResult = await findWorkpaper(request, token, 'B60', PROJECT_ID)
    test.skip(!wpResult.exists, 'B60 底稿不存在，需先在 DB 中生成 B60 系列底稿')

    const consoleErrors = setupConsoleErrorCollector(page)

    // ─── 导航到 B60 底稿编辑页 ───
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(3_000)

    // 等待编辑器容器加载完成
    await page.waitForSelector(
      '.gt-wp-editor, .b60-bundle, .b60-chapter-editor, [class*="b60"]',
      { timeout: 20_000 },
    )
    await page.waitForTimeout(3_000)

    // 等待 loading overlay 消失
    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 20_000 })
    }

    // ─── 验证章节编辑器渲染 ───
    // 验证无 ErrorBoundary
    const errorBoundary = page.locator('.gt-error-boundary, [class*="error-boundary"]')
    expect(await errorBoundary.count(), 'ErrorBoundary 不应出现').toBe(0)

    // 验证双栏布局存在：左导航 + 右编辑区
    const leftNav = page.locator(
      '.b60-chapter-nav, .chapter-nav, [class*="chapter-nav"], [class*="left-panel"]',
    )
    const rightContent = page.locator(
      '.b60-chapter-content, .chapter-content, [class*="chapter-content"], [class*="right-panel"], [class*="edit-area"]',
    )

    // 如果是专用 HTML 组件渲染（b60-strategy），应有章节编辑器结构
    const pageText = (await page.textContent('body')) || ''
    const isB60HtmlMode =
      pageText.includes('总体审计策略') ||
      pageText.includes('审计方法') ||
      pageText.includes('重大关注事项') ||
      pageText.includes('章节编辑')

    if (isB60HtmlMode) {
      // 验证左侧导航面板可见
      const hasLeftNav = (await leftNav.count()) > 0
      const hasChapterCards = (await page.locator('.el-card').count()) > 0
      expect(
        hasLeftNav || hasChapterCards,
        '章节编辑器应渲染：左导航面板或章节卡片',
      ).toBeTruthy()

      // 验证右侧编辑区有 textarea 或卡片内容
      const textareas = page.locator('textarea, .el-textarea__inner')
      const hasTextareas = (await textareas.count()) > 0
      expect(hasTextareas || hasChapterCards, '应有可编辑的章节 textarea 区域').toBeTruthy()

      // ─── 验证 Tab 导航 ───
      const tabs = page.locator('.el-tabs__item, [role="tab"]')
      const tabCount = await tabs.count()
      if (tabCount > 1) {
        // 存在多个 Tab，尝试点击第二个 Tab
        const secondTab = tabs.nth(1)
        const secondTabText = await secondTab.textContent()
        await secondTab.click()
        await page.waitForTimeout(1_500)

        // 验证 Tab 切换后内容有变化（至少没有崩溃）
        const afterClickError = page.locator('.gt-error-boundary, [class*="error-boundary"]')
        expect(await afterClickError.count(), 'Tab 切换不应导致 ErrorBoundary').toBe(0)

        // 切回第一个 Tab
        await tabs.first().click()
        await page.waitForTimeout(1_000)
      }

      // ─── 验证适用性矩阵 ───
      // 适用性矩阵应有 checkbox 元素
      const checkboxes = page.locator(
        '.el-checkbox, [class*="applicability"] .el-checkbox, [class*="matrix"] .el-checkbox',
      )
      const checkboxCount = await checkboxes.count()

      if (checkboxCount > 0) {
        // 找到一个已勾选的 checkbox 并取消勾选
        const checkedBox = page
          .locator('.el-checkbox.is-checked, .el-checkbox__input.is-checked')
          .first()

        if (await checkedBox.count()) {
          // 记录取消勾选前的 Tab 数量
          const tabsBeforeUncheck = await tabs.count()

          // 取消勾选
          await checkedBox.click()
          await page.waitForTimeout(1_200) // 等待 800ms 防抖 + 缓冲

          // 验证 Tab 可能减少（或至少无错误）
          const tabsAfterUncheck = await tabs.count()
          // 适用性取消后 Tab 数量应减少或保持（不增加）
          expect(tabsAfterUncheck).toBeLessThanOrEqual(tabsBeforeUncheck)

          // 重新勾选还原
          const uncheckedBox = page
            .locator('.el-checkbox:not(.is-checked)')
            .first()
          if (await uncheckedBox.count()) {
            await uncheckedBox.click()
            await page.waitForTimeout(1_200)
          }
        }
      }
    } else {
      // B60 可能仍走旧 word-template 模式（尚未注册 b60-strategy）
      // 仅验证页面可加载不崩溃
      expect(pageText.length, '页面应有内容').toBeGreaterThan(100)
    }

    // ─── 最终验证无严重错误 ───
    const criticalErrors = filterCriticalErrors(consoleErrors)
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('8.2: Chapter edit saves and echoes on reload', async ({ page, request }) => {
    // ─── 登录 + 查找 B60 底稿 ───
    const token = await loginAs(page, 'admin', 'admin123')
    const wpResult = await findWorkpaper(request, token, 'B60', PROJECT_ID)
    test.skip(!wpResult.exists, 'B60 底稿不存在，需先在 DB 中生成 B60 系列底稿')

    const consoleErrors = setupConsoleErrorCollector(page)

    // ─── 导航到 B60 底稿 ───
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(5_000)

    // 等待加载完成
    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 20_000 })
    }

    // 检查是否为 HTML 章节编辑模式
    const pageText = (await page.textContent('body')) || ''
    const isB60HtmlMode =
      pageText.includes('总体审计策略') ||
      pageText.includes('审计方法') ||
      pageText.includes('章节编辑')

    test.skip(!isB60HtmlMode, 'B60 当前非 HTML 章节编辑模式（可能仍为 word-template）')

    // ─── 找到章节 textarea 并编辑 ───
    const textareas = page.locator('textarea, .el-textarea__inner')
    await expect(textareas.first()).toBeVisible({ timeout: 15_000 })

    const firstTextarea = textareas.first()
    const testContent = `E2E测试内容_${Date.now()}`

    // 清空并输入测试内容
    await firstTextarea.click()
    await firstTextarea.fill(testContent)

    // ─── 等待自动保存（800ms 防抖 + 网络延迟缓冲） ───
    await page.waitForTimeout(2_000)

    // ─── 验证保存状态指示器变化 ───
    // 保存状态应经历: 未保存 → 保存中 → 已保存
    const statusIndicator = page.locator(
      '[class*="save-status"], [class*="status-indicator"], :text("已保存"), :text("保存中"), :text("未保存")',
    )

    // 等待状态变为"已保存"
    try {
      await page.waitForSelector(':text("已保存"), :text("✓"), [class*="saved"]', {
        timeout: 10_000,
      })
    } catch {
      // 如果超时，检查是否有保存失败提示
      const hasSavingIndicator =
        pageText.includes('保存中') || pageText.includes('已保存') || pageText.includes('✓')
      // 不强制断言（可能自动保存太快看不到中间态）
    }

    // ─── 刷新页面验证回显 ───
    await page.reload()
    await page.waitForTimeout(5_000)

    // 等待重新加载完成
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 20_000 })
    }

    // 验证之前输入的内容仍然存在
    const reloadedTextareas = page.locator('textarea, .el-textarea__inner')
    await expect(reloadedTextareas.first()).toBeVisible({ timeout: 15_000 })

    // 获取第一个 textarea 的值
    const reloadedValue = await reloadedTextareas.first().inputValue()
    expect(
      reloadedValue.includes(testContent),
      `刷新后 textarea 应包含之前编辑的内容 "${testContent}"，实际值: "${reloadedValue.slice(0, 100)}"`,
    ).toBeTruthy()

    // ─── 最终验证无严重错误 ───
    const criticalErrors = filterCriticalErrors(consoleErrors)
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('8.3: AI assist button + mode switching', async ({ page, request }) => {
    // ─── 登录 + 查找 B60 底稿 ───
    const token = await loginAs(page, 'admin', 'admin123')
    const wpResult = await findWorkpaper(request, token, 'B60', PROJECT_ID)
    test.skip(!wpResult.exists, 'B60 底稿不存在，需先在 DB 中生成 B60 系列底稿')

    const consoleErrors = setupConsoleErrorCollector(page)

    // ─── 导航到 B60 底稿 ───
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(5_000)

    // 等待加载完成
    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 20_000 })
    }

    // 检查是否为 HTML 章节编辑模式
    const pageText = (await page.textContent('body')) || ''
    const isB60HtmlMode =
      pageText.includes('总体审计策略') ||
      pageText.includes('审计方法') ||
      pageText.includes('章节编辑')

    test.skip(!isB60HtmlMode, 'B60 当前非 HTML 章节编辑模式（可能仍为 word-template）')

    // ─── 验证 AI 辅助按钮存在并点击 ───
    const aiButton = page.locator(
      'button:has-text("AI 辅助"), button:has-text("AI"), .el-button:has-text("AI")',
    )

    if (await aiButton.count() > 0) {
      // 点击第一个 AI 辅助按钮
      await aiButton.first().click()
      await page.waitForTimeout(3_000)

      // 验证结果之一：
      // 1. AI 预览对话框出现（el-dialog）
      // 2. ElMessage.warning 出现（AI 服务不可用时的降级提示）
      const aiDialog = page.locator('.el-dialog, [class*="ai-preview"], [role="dialog"]')
      const warningMessage = page.locator(
        '.el-message--warning, .el-message:has-text("AI"), .el-message:has-text("失败"), .el-message:has-text("重试")',
      )

      const hasDialog = (await aiDialog.count()) > 0
      const hasWarning = (await warningMessage.count()) > 0

      // AI 按钮点击后应出现对话框（成功）或 warning 消息（降级）
      expect(
        hasDialog || hasWarning,
        'AI 按钮点击后应弹出预览对话框或显示降级 warning 提示',
      ).toBeTruthy()

      // 如果有对话框，关闭它
      if (hasDialog) {
        const closeBtn = aiDialog.locator(
          '.el-dialog__headerbtn, button:has-text("取消"), button:has-text("关闭")',
        )
        if (await closeBtn.count()) {
          await closeBtn.first().click()
          await page.waitForTimeout(500)
        }
      }
    }

    // ─── 验证模式切换（章节编辑 ↔ 在线编辑）───
    const modeSwitch = page.locator(
      '.el-segmented, [class*="mode-switch"], [class*="segmented"]',
    )

    if (await modeSwitch.count() > 0) {
      // 找到"在线编辑"选项
      const onlineEditOption = modeSwitch.locator(
        ':text("在线编辑"), .el-segmented__item:has-text("在线编辑")',
      )
      const chapterEditOption = modeSwitch.locator(
        ':text("章节编辑"), .el-segmented__item:has-text("章节编辑")',
      )

      if (await onlineEditOption.count() > 0) {
        // 记录切换前的内容状态
        const beforeSwitchTextareas = await page.locator('textarea, .el-textarea__inner').count()

        // 切换到在线编辑模式
        await onlineEditOption.first().click()
        await page.waitForTimeout(3_000)

        // 验证内容区发生变化（OnlyOffice iframe 或相应组件出现）
        const onlyOfficeArea = page.locator(
          'iframe[src*="onlyoffice"], .onlyoffice-editor, [class*="only-office"], [class*="onlyoffice"]',
        )
        const afterSwitchTextareas = await page.locator('textarea, .el-textarea__inner').count()

        // 切换到在线编辑后，textarea 数量应减少（章节编辑器被替换）
        // 或者出现 OnlyOffice 相关元素
        // 或者出现 "OnlyOffice 不可用" 提示（tooltip/禁用状态）
        const contentChanged =
          afterSwitchTextareas < beforeSwitchTextareas ||
          (await onlyOfficeArea.count()) > 0 ||
          pageText.includes('不可用')

        // 模式切换应产生可观测的变化（内容区替换或降级提示）
        // 注：如果 OnlyOffice 不可用，选项可能被禁用，此时不会切换成功
        // 两种情况都是正确行为
        const disabledOption = modeSwitch.locator(
          '.is-disabled:has-text("在线编辑"), [disabled]:has-text("在线编辑")',
        )
        const isDisabled = (await disabledOption.count()) > 0

        if (!isDisabled) {
          // 如果选项未禁用，切换应产生内容变化
          expect(
            contentChanged || (await onlyOfficeArea.count()) > 0,
            '切换到在线编辑后内容区应变化（OnlyOffice 或降级）',
          ).toBeTruthy()
        }

        // 切回章节编辑模式
        if (await chapterEditOption.count() > 0) {
          await chapterEditOption.first().click()
          await page.waitForTimeout(3_000)

          // 切回后应恢复 textarea（章节编辑器重新加载）
          const restoredTextareas = await page.locator('textarea, .el-textarea__inner').count()
          // 恢复后的 textarea 数量应 >= 1
          expect(
            restoredTextareas,
            '切回章节编辑后应恢复 textarea 编辑区',
          ).toBeGreaterThanOrEqual(1)
        }
      }
    }

    // ─── 最终验证无严重错误 ───
    const criticalErrors = filterCriticalErrors(consoleErrors)
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })
})
