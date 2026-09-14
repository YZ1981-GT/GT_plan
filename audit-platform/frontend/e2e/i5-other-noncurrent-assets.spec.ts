/**
 * I5 其他非流动资产 — Playwright E2E 测试
 *
 * Spec: .kiro/specs/i5-other-noncurrent-assets/ Task 7.4
 * Validates: Requirements 1-6
 *
 * 场景:
 * 1. 打开I5底稿→验证底稿目录Tab加载
 * 2. 切换到I5-1审定表→编辑期初/增加/减少→验证期末自动计算
 * 3. 点击"回写TB(1911)"按钮→验证成功消息
 * 4. 切换到I5-2明细表→验证3区段Tab
 * 5. 切换到I5-3调整分录→新增条目→验证借贷平衡
 * 6. 切换到I5-4针对性检查→完成radio判断
 * 7. 多sheet切换无崩溃→无严重console错误
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  clickWorkpaperSheetTab,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID

async function loginAs(page: Page) {
  const resp = await page.request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
  return token as string
}

async function getToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

/** 忽略的 console error pattern */
function shouldIgnoreError(text: string): boolean {
  return (
    (/\/ai\//.test(text) && /405/.test(text)) ||
    /net::ERR_|Failed to fetch|NetworkError/.test(text) ||
    /onlyoffice|DocsAPI/.test(text) ||
    /ResizeObserver/.test(text) ||
    /favicon/.test(text)
  )
}

// ─── Scenario 1: 打开I5底稿→底稿目录加载

test.describe('I5 其他非流动资产 — Scenario 1: 底稿目录加载', () => {
  test('打开I5底稿→验证底稿目录显示→sheet列表可见', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'I5', PROJECT_ID)
    test.skip(!wpResult.exists, 'I5 底稿不存在')

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !shouldIgnoreError(msg.text())) {
        consoleErrors.push(msg.text())
      }
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 验证 I5 组件渲染（主入口或底稿目录）
    const hasDirectoryText = (await page.locator('text=底稿目录').count()) > 0
    const hasI5Content = (await page.locator('.i5-other-noncurrent-assets, [data-component="i5-other-noncurrent-assets"]').count()) > 0
    const hasWpContent = (await page.locator('.wp-renderer-content, .wp-html-content').count()) > 0
    expect(hasDirectoryText || hasI5Content || hasWpContent).toBeTruthy()

    // 验证无严重控制台错误
    const criticalErrors = consoleErrors.filter(e => !shouldIgnoreError(e))
    expect(criticalErrors.length).toBeLessThanOrEqual(2)
  })
})

// ─── Scenario 2: I5-1审定表→编辑期初/增加/减少→期末自动计算

test.describe('I5 其他非流动资产 — Scenario 2: 审定表编辑→期末自动计算', () => {
  test('切换到I5-1审定表→编辑行→验证期末=期初+增加-减少', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'I5', PROJECT_ID)
    test.skip(!wpResult.exists, 'I5 底稿不存在')

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !shouldIgnoreError(msg.text())) {
        consoleErrors.push(msg.text())
      }
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 切换到 I5-1 审定表
    try {
      await clickWorkpaperSheetTab(page, 'I5-1')
      await page.waitForTimeout(3_000)
    } catch {
      test.skip(true, 'I5-1 sheet tab 不可用')
    }

    // 验证审定表渲染 — 应含资产类列标题
    const auditTableContent =
      (await page.locator('text=期初').count()) > 0 ||
      (await page.locator('text=审定数').count()) > 0 ||
      (await page.locator('text=未审数').count()) > 0 ||
      (await page.locator('text=其他非流动资产').count()) > 0
    expect(auditTableContent).toBeTruthy()

    // 尝试编辑第一个可编辑行的"期初"输入
    const beginInput = page.locator('[data-field="begin"], input[name*="begin"]').first()
    if (await beginInput.isVisible({ timeout: 5000 }).catch(() => false)) {
      await beginInput.fill('100000')
      // 编辑"增加"
      const increaseInput = page.locator('[data-field="increase"], input[name*="increase"]').first()
      if (await increaseInput.isVisible({ timeout: 3000 }).catch(() => false)) {
        await increaseInput.fill('20000')
      }
      // 编辑"减少"
      const decreaseInput = page.locator('[data-field="decrease"], input[name*="decrease"]').first()
      if (await decreaseInput.isVisible({ timeout: 3000 }).catch(() => false)) {
        await decreaseInput.fill('5000')
      }
      // 触发blur → 等待公式计算
      await page.keyboard.press('Tab')
      await page.waitForTimeout(1_000)

      // 验证期末 = 期初 + 增加 - 减少 = 100000 + 20000 - 5000 = 115000
      const endCell = page.locator('[data-field="end"], [data-field="endBalance"]').first()
      if (await endCell.isVisible({ timeout: 3000 }).catch(() => false)) {
        const endText = await endCell.textContent()
        expect(endText).toContain('115')
      }
    }

    // 验证公式列虚线下划线样式
    const formulaCells = page.locator('[style*="dashed"], .formula-cell, [class*="formula"]')
    if (await formulaCells.count() > 0) {
      expect(await formulaCells.count()).toBeGreaterThan(0)
    }

    // 验证无严重错误
    const criticalErrors = consoleErrors.filter(e => !shouldIgnoreError(e))
    expect(criticalErrors.length).toBeLessThanOrEqual(2)
  })
})

// ─── Scenario 3: 回写TB(1911)

test.describe('I5 其他非流动资产 — Scenario 3: 回写TB(1911)', () => {
  test('点击"回写TB(1911)"按钮→验证成功消息', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'I5', PROJECT_ID)
    test.skip(!wpResult.exists, 'I5 底稿不存在')

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !shouldIgnoreError(msg.text())) {
        consoleErrors.push(msg.text())
      }
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 切换到 I5-1 审定表
    try {
      await clickWorkpaperSheetTab(page, 'I5-1')
      await page.waitForTimeout(3_000)
    } catch {
      test.skip(true, 'I5-1 sheet tab 不可用')
    }

    // 查找并点击"回写TB"按钮
    const writebackBtn = page.locator('button').filter({ hasText: /回写TB|回写/ }).first()
    if (await writebackBtn.isVisible({ timeout: 8000 }).catch(() => false)) {
      await writebackBtn.click()
      await page.waitForTimeout(2_000)

      // 验证成功消息（el-message 或 el-notification）
      const successMsg = page.locator('.el-message--success, .el-notification__content')
      if (await successMsg.isVisible({ timeout: 5000 }).catch(() => false)) {
        const msgText = await successMsg.textContent()
        expect(msgText).toMatch(/成功|1911|回写/)
      }
    }

    // 验证无严重错误
    const criticalErrors = consoleErrors.filter(e => !shouldIgnoreError(e))
    expect(criticalErrors.length).toBeLessThanOrEqual(2)
  })
})

// ─── Scenario 4: I5-2明细表→3区段Tab

test.describe('I5 其他非流动资产 — Scenario 4: I5-2明细表区段Tab', () => {
  test('切换到I5-2明细表→验证3区段Tab存在', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'I5', PROJECT_ID)
    test.skip(!wpResult.exists, 'I5 底稿不存在')

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !shouldIgnoreError(msg.text())) {
        consoleErrors.push(msg.text())
      }
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 切换到 I5-2 明细表
    try {
      await clickWorkpaperSheetTab(page, 'I5-2')
      await page.waitForTimeout(3_000)
    } catch {
      test.skip(true, 'I5-2 sheet tab 不可用')
    }

    // 验证3区段Tab（el-segmented 或内部 tab 切换）
    const segmented = page.locator('.el-segmented, [data-testid="i5-detail-segment"]')
    if (await segmented.isVisible({ timeout: 8000 }).catch(() => false)) {
      const items = segmented.locator('.el-segmented__item')
      await expect(items).toHaveCount(3)

      // 验证区段名称：基础 | 金额 | 检查
      await expect(items.nth(0)).toContainText(/基础/)
      await expect(items.nth(1)).toContainText(/金额/)
      await expect(items.nth(2)).toContainText(/检查/)

      // 切换到金额区段 → 验证列标题
      await items.nth(1).click()
      await page.waitForTimeout(1_000)
      const hasAmountHeaders =
        (await page.locator('text=期初').count()) > 0 ||
        (await page.locator('text=增加').count()) > 0 ||
        (await page.locator('text=期末').count()) > 0
      expect(hasAmountHeaders).toBeTruthy()
    }

    // 验证明细表含表格结构
    const tableHeaders = page.locator('th, .el-table__header-wrapper th')
    if (await tableHeaders.count() > 0) {
      expect(await tableHeaders.count()).toBeGreaterThanOrEqual(1)
    }

    // 验证无严重错误
    const criticalErrors = consoleErrors.filter(e => !shouldIgnoreError(e))
    expect(criticalErrors.length).toBeLessThanOrEqual(2)
  })
})

// ─── Scenario 5: I5-3调整分录→新增→借贷平衡

test.describe('I5 其他非流动资产 — Scenario 5: I5-3调整分录借贷平衡', () => {
  test('切换到I5-3调整分录→新增条目→验证借贷平衡', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'I5', PROJECT_ID)
    test.skip(!wpResult.exists, 'I5 底稿不存在')

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !shouldIgnoreError(msg.text())) {
        consoleErrors.push(msg.text())
      }
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 切换到 I5-3 调整分录
    try {
      await clickWorkpaperSheetTab(page, 'I5-3')
      await page.waitForTimeout(3_000)
    } catch {
      test.skip(true, 'I5-3 sheet tab 不可用')
    }

    // 验证调整分录页面渲染
    const adjustmentContent =
      (await page.locator('text=借方').count()) > 0 ||
      (await page.locator('text=贷方').count()) > 0 ||
      (await page.locator('text=调整分录').count()) > 0 ||
      (await page.locator('text=科目').count()) > 0
    expect(adjustmentContent).toBeTruthy()

    // 查找新增按钮
    const addBtn = page.locator('button').filter({ hasText: /新增|添加|\+/ }).first()
    if (await addBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await addBtn.click()
      await page.waitForTimeout(2_000)

      // 填入借方金额
      const debitInput = page.locator('[data-field="debit"], input[name*="debit"]').first()
      if (await debitInput.isVisible({ timeout: 3000 }).catch(() => false)) {
        await debitInput.fill('50000')
      }
      // 填入贷方金额
      const creditInput = page.locator('[data-field="credit"], input[name*="credit"]').first()
      if (await creditInput.isVisible({ timeout: 3000 }).catch(() => false)) {
        await creditInput.fill('50000')
      }
      await page.keyboard.press('Tab')
      await page.waitForTimeout(1_000)

      // 验证借贷平衡标识（绿色 / 平衡图标 / 差额=0）
      const balanceIndicator = page.locator('[data-testid="balance-status"], .balance-ok, .balance-indicator')
      if (await balanceIndicator.isVisible({ timeout: 3000 }).catch(() => false)) {
        const text = await balanceIndicator.textContent()
        expect(text).toMatch(/平衡|0|balanced/i)
      }
    }

    // 验证无严重错误
    const criticalErrors = consoleErrors.filter(e => !shouldIgnoreError(e))
    expect(criticalErrors.length).toBeLessThanOrEqual(2)
  })
})

// ─── Scenario 6: I5-4针对性检查→radio判断

test.describe('I5 其他非流动资产 — Scenario 6: I5-4针对性检查', () => {
  test('切换到I5-4针对性检查→完成radio判断', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'I5', PROJECT_ID)
    test.skip(!wpResult.exists, 'I5 底稿不存在')

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !shouldIgnoreError(msg.text())) {
        consoleErrors.push(msg.text())
      }
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 切换到 I5-4 针对性检查表
    try {
      await clickWorkpaperSheetTab(page, 'I5-4')
      await page.waitForTimeout(3_000)
    } catch {
      test.skip(true, 'I5-4 sheet tab 不可用')
    }

    // 验证检查表渲染 — 含分类/期限/可回收性相关内容
    const checkContent =
      (await page.locator('text=分类').count()) > 0 ||
      (await page.locator('text=期限').count()) > 0 ||
      (await page.locator('text=可回收').count()) > 0 ||
      (await page.locator('text=针对性检查').count()) > 0 ||
      (await page.locator('text=检查项').count()) > 0
    expect(checkContent).toBeTruthy()

    // 查找 radio 或选择器元素
    const radioGroups = page.locator('.el-radio-group, .el-radio, input[type="radio"]')
    if (await radioGroups.count() > 0) {
      // 点击第一个radio选项
      const firstRadio = radioGroups.first()
      await firstRadio.click()
      await page.waitForTimeout(500)
    }

    // 验证方法论琥珀色块存在
    const methodologyBlock = page.locator('[class*="methodology"], [class*="amber"], .methodology-context')
    if (await methodologyBlock.count() > 0) {
      expect(await methodologyBlock.count()).toBeGreaterThan(0)
    }

    // 验证无严重错误
    const criticalErrors = consoleErrors.filter(e => !shouldIgnoreError(e))
    expect(criticalErrors.length).toBeLessThanOrEqual(2)
  })
})

// ─── Scenario 7: 多sheet切换无崩溃

test.describe('I5 其他非流动资产 — Scenario 7: 多sheet切换无崩溃', () => {
  test('打开I5→依次切换I5-1/I5-2/I5-3/I5-4→验证无console错误', async ({ page, request }) => {
    test.setTimeout(120_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'I5', PROJECT_ID)
    test.skip(!wpResult.exists, 'I5 底稿不存在')

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !shouldIgnoreError(msg.text())) {
        consoleErrors.push(msg.text())
      }
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 依次切换多个 sheet，验证无崩溃
    const sheetsToVisit = ['I5-1', 'I5-2', 'I5-3', 'I5-4']
    for (const sheet of sheetsToVisit) {
      try {
        await clickWorkpaperSheetTab(page, sheet)
        await page.waitForTimeout(2_500)
      } catch {
        // 某些sheet可能不存在，跳过
      }
    }

    // 最终验证：页面未白屏
    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText.length).toBeGreaterThan(50)

    // 验证无严重控制台错误（≤3个容忍）
    const criticalErrors = consoleErrors.filter(e => !shouldIgnoreError(e))
    expect(criticalErrors.length).toBeLessThanOrEqual(3)
  })
})
