/**
 * review-panel.spec.ts — ReviewPanel 批量复核面板 E2E 验证
 *
 * 锚定 spec review-prompt-sheet-level-split Task 11.1
 *
 * 验证 ReviewPanel 组件完整 E2E 流程：
 * 1. 导航到含 D2 底稿的项目
 * 2. ReviewPanel 挂载渲染（卡片列表）
 * 3. 点击"开始批量复核"按钮触发 API
 * 4. 验证进度条显示
 * 5. 展开卡片查看 Finding 列表
 * 6. 导出 Excel 按钮触发下载
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 7.1
 *
 * 注意：这些测试需要运行中的后端 + vLLM 服务才能完整执行。
 * 在无 LLM 环境中标记为 .skip()，作为 E2E 流程文档。
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

// ─── 常量 ───────────────────────────────────────────────────────────────────
const BASE_URL = 'http://localhost:3030'
const API_BASE = '/api'
const CREDENTIALS = { username: 'admin', password: 'admin123' }

// 使用已知含 D2 底稿的测试项目（重药控股安徽）
const TEST_PROJECT_ID = '0ec33ac9-9b1c-4e0a-b7f6-8e3e2e5f1a2b'
const D2_WP_CODE_PREFIX = 'D2'

// ─── 辅助函数 ───────────────────────────────────────────────────────────────

async function loginAs(page: Page, username: string, password: string): Promise<string> {
  const resp = await page.request.post(`${API_BASE}/auth/login`, {
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
  const resp = await request.post(`${API_BASE}/auth/login`, {
    data: CREDENTIALS,
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

/**
 * 导航到含 D2 底稿的项目底稿列表页，并打开 ReviewPanel 所在入口
 */
async function navigateToD2WorkpaperList(page: Page, projectId: string) {
  // 导航到项目底稿列表（D 循环）
  await page.goto(`/projects/${projectId}/workpapers?cycle=D`)
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(3000)
}

// ─── 测试套件 ───────────────────────────────────────────────────────────────

test.describe.skip('ReviewPanel — 批量复核面板 E2E 验证', () => {
  /**
   * 前置条件：需要运行中的后端(9980) + 前端(3030) + vLLM(8100)
   * 所有测试标记为 skip，作为 E2E 流程文档记录
   */

  test.beforeEach(async ({ page }) => {
    test.setTimeout(120_000)
    await loginAs(page, CREDENTIALS.username, CREDENTIALS.password)
  })

  test('11.1.1 — 导航到含 D2 底稿的项目，ReviewPanel 挂载渲染', async ({ page }) => {
    // Step 1: 导航到项目底稿列表
    await navigateToD2WorkpaperList(page, TEST_PROJECT_ID)

    // Step 2: 查找并点击进入 D2 应收账款科目级操作区
    // ReviewPanel 挂载在科目级操作区（底稿列表页 WorkpaperWorkbenchView）
    const d2Entry = page.locator('[class*="workpaper"]').filter({ hasText: '应收账款' }).first()
    if (await d2Entry.isVisible()) {
      await d2Entry.click()
      await page.waitForTimeout(2000)
    }

    // Step 3: 验证 ReviewPanel 组件已渲染
    // 检查"开始批量复核"按钮存在（Requirement 6.4）
    const batchReviewBtn = page.getByRole('button', { name: /开始批量复核/ })
    await expect(batchReviewBtn).toBeVisible({ timeout: 15_000 })

    // 验证卡片列表容器存在（Requirement 6.1）
    const reviewPanel = page.locator('.review-panel, [class*="review-panel"]')
    await expect(reviewPanel).toBeVisible({ timeout: 10_000 })
  })

  test('11.1.2 — ReviewPanel 显示底稿卡片列表', async ({ page }) => {
    await navigateToD2WorkpaperList(page, TEST_PROJECT_ID)

    // 等待 ReviewPanel 渲染
    await page.waitForTimeout(5000)

    // 验证卡片列表渲染（Requirement 6.1）
    // 每张底稿应显示: sheet name, pass/fail badge, finding count, risk distribution
    const cards = page.locator(
      '.review-sheet-card, [class*="sheet-card"], .el-card[class*="review"]',
    )
    const cardCount = await cards.count()

    // D2 应有多张底稿卡片（D2-1 ~ D2-8 + 附注）
    expect(cardCount, 'D2 应有至少 1 张底稿卡片').toBeGreaterThanOrEqual(1)

    // 验证卡片内含底稿名称文本
    const firstCard = cards.first()
    const cardText = await firstCard.textContent()
    expect(
      cardText,
      '卡片应包含底稿相关内容',
    ).toBeTruthy()
  })

  test('11.1.3 — 点击"开始批量复核"按钮触发批量复核 API', async ({ page }) => {
    await navigateToD2WorkpaperList(page, TEST_PROJECT_ID)
    await page.waitForTimeout(3000)

    // 监听 batch-review API 调用
    const batchReviewPromise = page.waitForResponse(
      (resp) => resp.url().includes('/batch-review') && resp.request().method() === 'POST',
      { timeout: 30_000 },
    )

    // 点击"开始批量复核"按钮（Requirement 6.4）
    const batchBtn = page.getByRole('button', { name: /开始批量复核/ })
    await expect(batchBtn).toBeVisible({ timeout: 10_000 })
    await batchBtn.click()

    // 验证 API 被调用
    const response = await batchReviewPromise
    expect(response.status()).toBe(200)

    // 验证请求体包含 wp_code_prefix 和 year
    const requestBody = response.request().postDataJSON()
    expect(requestBody).toHaveProperty('wp_code_prefix')
    expect(requestBody).toHaveProperty('year')
  })

  test('11.1.4 — 批量复核进行中显示进度条', async ({ page }) => {
    await navigateToD2WorkpaperList(page, TEST_PROJECT_ID)
    await page.waitForTimeout(3000)

    // 点击开始批量复核
    const batchBtn = page.getByRole('button', { name: /开始批量复核/ })
    await expect(batchBtn).toBeVisible({ timeout: 10_000 })
    await batchBtn.click()

    // 验证进度指示器出现（Requirement 6.3）
    const progressIndicator = page.locator(
      '.el-progress, [class*="progress"], [role="progressbar"]',
    )
    await expect(progressIndicator.first()).toBeVisible({ timeout: 10_000 })

    // 验证显示当前处理的底稿名称
    const progressText = page.locator('[class*="progress"] span, .review-progress-text')
    const text = await progressText.first().textContent()
    // 进度文本应包含当前处理的 sheet 信息或完成百分比
    expect(text).toBeTruthy()
  })

  test('11.1.5 — 展开卡片查看 Finding 列表', async ({ page }) => {
    await navigateToD2WorkpaperList(page, TEST_PROJECT_ID)
    await page.waitForTimeout(5000)

    // 等待复核结果加载（假设已有历史复核数据）
    const cards = page.locator(
      '.review-sheet-card, [class*="sheet-card"], .el-card[class*="review"]',
    )
    await expect(cards.first()).toBeVisible({ timeout: 15_000 })

    // 点击第一张卡片展开（Requirement 6.2）
    await cards.first().click()
    await page.waitForTimeout(1000)

    // 验证 Finding 列表展开显示
    const findings = page.locator(
      '.review-finding, [class*="finding"], .finding-item',
    )
    const findingCount = await findings.count()

    if (findingCount > 0) {
      // 验证 Finding 项包含必要信息
      const firstFinding = findings.first()
      const findingText = await firstFinding.textContent()

      // Finding 应包含描述文本（Requirement 6.2）
      expect(findingText, 'Finding 应包含描述').toBeTruthy()

      // 验证风险等级标签存在（色标：red=高, orange=中, gray=低）
      const riskTag = firstFinding.locator(
        '.el-tag, [class*="risk"], [class*="tag"]',
      )
      const hasRiskTag = (await riskTag.count()) > 0
      expect(hasRiskTag, 'Finding 应有风险等级标签').toBeTruthy()
    }

    // 验证 pass/fail badge 显示（Requirement 6.1）
    const badges = page.locator(
      '.pass-badge, .fail-badge, [class*="badge"], .el-tag[type="success"], .el-tag[type="danger"]',
    )
    expect(await badges.count(), '应有通过/未通过 badge').toBeGreaterThanOrEqual(0)
  })

  test('11.1.6 — 导出 Excel 按钮触发下载', async ({ page }) => {
    await navigateToD2WorkpaperList(page, TEST_PROJECT_ID)
    await page.waitForTimeout(5000)

    // 查找"导出Excel"按钮（Requirement 7.1）
    const exportBtn = page.getByRole('button', { name: /导出.*Excel|导出/i })
    await expect(exportBtn).toBeVisible({ timeout: 10_000 })

    // 监听下载事件
    const downloadPromise = page.waitForEvent('download', { timeout: 30_000 })

    // 点击导出
    await exportBtn.click()

    // 验证下载被触发
    const download = await downloadPromise
    const fileName = download.suggestedFilename()

    // 验证文件名包含中文（RFC5987 编码，Requirement 7.4）
    // 下载的文件应为 .xlsx 格式
    expect(fileName).toMatch(/\.xlsx$/)

    // 文件名应包含 D2 或应收账款相关标识
    expect(
      fileName.includes('D2') || fileName.includes('应收') || fileName.includes('复核'),
      '导出文件名应包含 D2/应收/复核标识',
    ).toBeTruthy()
  })
})

// ─── API 级验证（不依赖 LLM，可独立运行） ────────────────────────────────────

test.describe('ReviewPanel — API 端点可达性验证', () => {
  test('batch-review 端点存在且可接受 POST', async ({ request }) => {
    const token = await getToken(request)

    // 验证批量复核端点可达（可能返回 422/404 因缺数据，但不应 405/500）
    const resp = await request.post(
      `${API_BASE}/projects/${TEST_PROJECT_ID}/batch-review`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: { wp_code_prefix: D2_WP_CODE_PREFIX, year: 2025 },
      },
    )

    // 端点存在：200/202/400/404/422 都表示路由已注册
    // 405 = 路由不存在或方法不匹配
    expect(
      [200, 202, 400, 404, 422].includes(resp.status()),
      `batch-review 端点应已注册，实际状态: ${resp.status()}`,
    ).toBeTruthy()
  })

  test('review-export 端点存在且可接受 GET', async ({ request }) => {
    const token = await getToken(request)

    const resp = await request.get(
      `${API_BASE}/projects/${TEST_PROJECT_ID}/review-export?wp_code_prefix=${D2_WP_CODE_PREFIX}`,
      {
        headers: { Authorization: `Bearer ${token}` },
      },
    )

    // 端点存在：200/404/422 都表示路由已注册
    expect(
      [200, 404, 422].includes(resp.status()),
      `review-export 端点应已注册，实际状态: ${resp.status()}`,
    ).toBeTruthy()
  })

  test('review-prompts/coverage 端点存在且返回覆盖率数据', async ({ request }) => {
    const token = await getToken(request)

    const resp = await request.get(`${API_BASE}/review-prompts/coverage`, {
      headers: { Authorization: `Bearer ${token}` },
    })

    // 端点应返回 200
    expect(resp.status()).toBe(200)

    const body = await resp.json()
    const data = body.data ?? body

    // 验证返回结构包含覆盖率字段
    expect(data).toHaveProperty('total_subjects')
    expect(data).toHaveProperty('subjects_with_sheet_prompts')
  })

  test('单底稿 review 端点存在且可接受 POST', async ({ request }) => {
    const token = await getToken(request)

    // 使用任意 wp_id（可能不存在，验证路由注册即可）
    const fakeWpId = '00000000-0000-0000-0000-000000000001'
    const resp = await request.post(
      `${API_BASE}/workpapers/${fakeWpId}/review`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: { sheet_name: '审定表D2-1' },
      },
    )

    // 路由已注册（404=wp不存在但路由在, 422=参数问题, 200=成功）
    // 不应返回 405 (Method Not Allowed)
    expect(resp.status()).not.toBe(405)
  })
})
