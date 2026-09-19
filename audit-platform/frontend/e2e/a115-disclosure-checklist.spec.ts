/**
 * a115-disclosure-checklist.spec.ts — A1-15 企业会计准则财务报表列报及披露核对表 E2E 验证
 *
 * 锚定 spec a1-15-disclosure-checklist Task 9.2
 *
 * 验证链路：
 * 1. 导航到 A1 Dashboard → A1-15 Tab
 * 2. 章节导航（点击 SectionNav 项 → 右侧滚动定位）
 * 3. 填写 Y/N/NA 结论
 * 4. 自动保存（"已保存" 指示器）
 * 5. TOC 标记章节不适用 → 级联 NA
 * 6. 切换到 DOCX 模式
 * 7. 切回 HTML 模式
 * 8. 验证数据未丢失（之前填写的结论仍存在）
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

async function getToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

async function findA1Workpaper(request: APIRequestContext, token: string) {
  const wpListResp = await request.get(`/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const wpBody = await wpListResp.json()
  const wpList =
    wpBody?.data?.items || wpBody?.items || wpBody?.data || (Array.isArray(wpBody) ? wpBody : [])
  return wpList.find((w: any) => w.wp_code === 'A1')
}

test.describe('A1-15 企业会计准则财务报表列报及披露核对表', () => {
  test.describe.configure({ mode: 'serial' })

  let a1WpId: string | undefined

  test.beforeEach(async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page, 'admin', 'admin123')
    const token = await getToken(request)
    const a1Wp = await findA1Workpaper(request, token)
    test.skip(!a1Wp, 'A1 底稿不存在，跳过')
    a1WpId = a1Wp!.id

    // 导航到 A1 dashboard
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${a1WpId}/edit`)
    await page.waitForTimeout(5_000)

    // 点击 A1-15 tab
    const a115Tab = page
      .locator('.el-tabs__item')
      .filter({ hasText: /A1-15|企业会计准则财务报表/ })
      .first()
    if (!(await a115Tab.isVisible({ timeout: 8_000 }).catch(() => false))) {
      test.skip(true, 'A1-15 Tab 不可见，跳过')
    }
    await a115Tab.click()
    await page.waitForTimeout(3_000)
  })

  test('自加载: A1-15 Tab 正确渲染结构化视图', async ({ page }) => {
    // 验证主容器可见（骨架屏已消失）
    const container = page.locator('.gt-a115-disclosure-checklist')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 等待骨架屏消失
    await expect(container.locator('.el-skeleton')).not.toBeVisible({ timeout: 10_000 })

    // 验证 HTML 视图可见
    const htmlView = container.locator('.gt-a115-disclosure-checklist__html-view')
    await expect(htmlView).toBeVisible()

    // 验证 el-segmented 模式切换器存在
    const segmented = container.locator('.el-segmented')
    await expect(segmented).toBeVisible()

    // 验证章节导航栏已填充（35 章节）
    const navItems = container.locator('.gt-a115-disclosure-checklist__nav-item')
    expect(await navItems.count()).toBeGreaterThanOrEqual(10)

    // 验证全局进度条存在
    const progressBar = container.locator('.gt-a115-disclosure-checklist__progress-bar')
    await expect(progressBar).toBeVisible()

    // 验证进度统计包含 Y/N/NA/未填/总计
    const statsText = await progressBar.textContent()
    expect(statsText).toContain('Y:')
    expect(statsText).toContain('N:')
    expect(statsText).toContain('NA:')
    expect(statsText).toContain('未填:')
    expect(statsText).toContain('总计:')
  })

  test('章节导航: 点击章节→滚动到对应位置', async ({ page }) => {
    const container = page.locator('.gt-a115-disclosure-checklist')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 获取章节导航列表
    const navItems = container.locator('.gt-a115-disclosure-checklist__nav-item')
    const navCount = await navItems.count()
    test.skip(navCount < 3, '章节数量不足，跳过')

    // 点击第 3 个章节（避免第 1 个已在视口内）
    const targetNav = navItems.nth(2)
    const targetTitle = await targetNav.locator('.gt-a115-disclosure-checklist__nav-title').textContent()
    await targetNav.click()
    await page.waitForTimeout(1_000)

    // 验证点击后该章节被标为 active
    await expect(targetNav).toHaveClass(/--active/)

    // 验证右侧 body 内对应章节 header 可见
    const body = container.locator('.gt-a115-disclosure-checklist__body')
    const sectionHeaders = body.locator('.gt-a115-disclosure-checklist__section-title')
    const matchingHeader = sectionHeaders.filter({ hasText: targetTitle!.trim() })
    await expect(matchingHeader.first()).toBeVisible({ timeout: 5_000 })
  })

  test('填写 Y/N/NA: 点击结论按钮→自动保存', async ({ page }) => {
    const container = page.locator('.gt-a115-disclosure-checklist')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 找到第一个 actionable 卡片
    const cards = container.locator('.gt-a115-disclosure-checklist__card')
    await expect(cards.first()).toBeVisible({ timeout: 10_000 })

    const firstCard = cards.first()

    // 找到 Y 按钮并点击
    const yButton = firstCard
      .locator('.gt-a115-disclosure-checklist__card-buttons .el-button')
      .filter({ hasText: 'Y' })
      .first()
    await yButton.click()
    await page.waitForTimeout(500)

    // 验证卡片获得绿色边框（yes 类名）
    await expect(firstCard).toHaveClass(/--yes/, { timeout: 3_000 })

    // 等待自动保存触发（debounce 2s + 网络请求）
    const saveIndicator = container.locator('.gt-a115-disclosure-checklist__save-indicator')
    await expect(saveIndicator).toContainText('已保存', { timeout: 10_000 })
  })

  test('TOC 标记不适用: 级联所有条目为 NA', async ({ page }) => {
    const container = page.locator('.gt-a115-disclosure-checklist')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 找到一个有条目的章节的 switch（取倒数几个，避免影响前面测试数据）
    const navItems = container.locator('.gt-a115-disclosure-checklist__nav-item')
    const navCount = await navItems.count()
    test.skip(navCount < 5, '章节数量不足，跳过')

    // 选择最后一个章节
    const targetNavItem = navItems.nth(navCount - 1)

    // 找到 el-switch 并关闭（标记不适用）
    const toggleSwitch = targetNavItem.locator('.gt-a115-disclosure-checklist__nav-switch')
    if (!(await toggleSwitch.isVisible().catch(() => false))) {
      test.skip(true, '该章节无 switch 控件，跳过')
    }

    // 点击 switch 关闭（标记不适用）
    await toggleSwitch.click()
    await page.waitForTimeout(1_500)

    // 验证导航项显示 ▧ 图标（不适用状态）
    const navIcon = targetNavItem.locator('.gt-a115-disclosure-checklist__nav-icon')
    await expect(navIcon).toContainText('▧', { timeout: 3_000 })

    // 验证导航项有 --na 类名
    await expect(targetNavItem).toHaveClass(/--na/)

    // 点击该章节导航到对应位置
    await targetNavItem.click()
    await page.waitForTimeout(1_500)

    // 验证该章节内的卡片都变成 NA 状态
    const body = container.locator('.gt-a115-disclosure-checklist__body')
    const sections = body.locator('.gt-a115-disclosure-checklist__section-sentinel')
    const lastSection = sections.last()

    // 检查该章节的卡片是否都有 --na 类名
    const sectionCards = lastSection.locator('.gt-a115-disclosure-checklist__card')
    const cardCount = await sectionCards.count()
    if (cardCount > 0) {
      // 至少验证第一张卡片变 NA
      await expect(sectionCards.first()).toHaveClass(/--na/, { timeout: 5_000 })
    }
  })

  test('模式切换: HTML→DOCX→HTML 数据不丢失', async ({ page }) => {
    const container = page.locator('.gt-a115-disclosure-checklist')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // Step 1: 填写一个条目为 Y（确保有数据可验证）
    const cards = container.locator('.gt-a115-disclosure-checklist__card')
    await expect(cards.first()).toBeVisible({ timeout: 10_000 })

    const firstCard = cards.first()
    const yButton = firstCard
      .locator('.gt-a115-disclosure-checklist__card-buttons .el-button')
      .filter({ hasText: 'Y' })
      .first()
    await yButton.click()
    await page.waitForTimeout(500)

    // 验证 Y 状态已设
    await expect(firstCard).toHaveClass(/--yes/, { timeout: 3_000 })

    // Step 2: 等待保存完成
    const saveIndicator = container.locator('.gt-a115-disclosure-checklist__save-indicator')
    await expect(saveIndicator).toContainText('已保存', { timeout: 10_000 })

    // Step 3: 切换到 DOCX 模式
    const segmented = container.locator('.el-segmented')
    const docxOption = segmented.locator('.el-segmented__item').filter({ hasText: /Word 编辑/ })
    const canSwitchDocx = await docxOption.isVisible().catch(() => false)

    if (canSwitchDocx) {
      // 检查 DOCX 选项是否 disabled
      const isDisabled = await docxOption.getAttribute('class')
      if (isDisabled?.includes('disabled')) {
        // OnlyOffice 不可用时，跳过模式切换测试
        test.skip(true, 'Word 编辑不可用（OnlyOffice 服务未启动），跳过模式切换')
      }

      await docxOption.click()
      await page.waitForTimeout(3_000)

      // 验证 HTML 视图消失
      const htmlView = container.locator('.gt-a115-disclosure-checklist__html-view')
      await expect(htmlView).not.toBeVisible({ timeout: 5_000 })

      // 验证 DOCX 视图出现
      const docxView = container.locator('.gt-a115-disclosure-checklist__docx-view')
      await expect(docxView).toBeVisible({ timeout: 5_000 })

      // Step 4: 切回 HTML 模式
      const htmlOption = segmented
        .locator('.el-segmented__item')
        .filter({ hasText: /结构化视图/ })
      await htmlOption.click()
      await page.waitForTimeout(5_000)

      // 验证 HTML 视图恢复
      await expect(htmlView).toBeVisible({ timeout: 10_000 })
    } else {
      // 如果 DOCX 选项不存在，仅验证 HTML 模式持久
      await page.reload()
      await page.waitForTimeout(5_000)
    }

    // Step 5: 验证之前填写的数据仍然保留
    const cardsAfter = container.locator('.gt-a115-disclosure-checklist__card')
    await expect(cardsAfter.first()).toBeVisible({ timeout: 10_000 })

    // 第一张卡片应仍为 Y 状态（绿色边框）
    const firstCardAfter = cardsAfter.first()
    const cardClass = await firstCardAfter.getAttribute('class')
    expect(cardClass).toContain('--yes')
  })
})
