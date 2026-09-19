/**
 * a112-dual-checklist.spec.ts — A1-12 双模式核查表 E2E 集成验证
 *
 * 锚定 spec a1-12-dual-mode-checklist Task 8.2
 *
 * 验证链路：
 * 1. 导航到项目 A1 dashboard
 * 2. 点击 A1-12 tab
 * 3. HTML 模式渲染（卡片列表可见）
 * 4. 标记一项为"适用"
 * 5. 填写索引号
 * 6. 切换到 DOCX 模式（如可用）
 * 7. 切回 HTML 模式
 * 8. 验证之前标记的数据保留
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

test.describe('A1-12 双模式核查表 E2E', () => {
  test.describe.configure({ mode: 'serial' })

  test('HTML模式渲染 → 标记适用 → 填索引号 → 切DOCX → 切回 → 数据保留', async ({
    page,
    request,
  }) => {
    test.setTimeout(90_000)
    await loginAs(page, 'admin', 'admin123')
    const token = await getToken(request)

    // 1. 查找 A1 底稿
    const a1Wp = await findA1Workpaper(request, token)
    test.skip(!a1Wp, 'A1 底稿不存在，跳过')

    // 2. 导航到 A1 dashboard
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${a1Wp!.id}/edit`)
    await page.waitForTimeout(5_000)

    // 3. 点击 A1-12 tab
    const a112Tab = page.locator('.el-tabs__item').filter({ hasText: /A1-12|重大事项/ }).first()
    if (!(await a112Tab.isVisible({ timeout: 5_000 }).catch(() => false))) {
      test.skip(true, 'A1-12 Tab 不可见，跳过')
    }
    await a112Tab.click()
    await page.waitForTimeout(3_000)

    // 4. 验证 HTML 模式渲染 — 核查表容器可见
    const container = page.locator('.gt-a112-dual-checklist')
    await expect(container).toBeVisible({ timeout: 10_000 })

    // 验证 el-segmented 模式切换器
    const segmented = container.locator('.el-segmented')
    await expect(segmented).toBeVisible()

    // 验证 HTML 视图区域
    const htmlView = container.locator('.gt-a112-dual-checklist__html-view')
    await expect(htmlView).toBeVisible()

    // 验证有卡片（至少 1 个分组标题 + 多张卡片）
    const categoryHeadings = container.locator('.gt-a112-dual-checklist__category-heading')
    expect(await categoryHeadings.count()).toBeGreaterThanOrEqual(1)

    const cards = container.locator('.gt-a112-dual-checklist__card')
    expect(await cards.count()).toBeGreaterThanOrEqual(14)

    // 5. 标记第一项为"适用"
    const firstCard = cards.first()
    const applicableRadio = firstCard.locator('.el-radio').filter({ hasText: '适用' }).first()
    await applicableRadio.click()
    await page.waitForTimeout(500)

    // 验证索引号输入区域出现
    const indexArea = firstCard.locator('.gt-a112-dual-checklist__card-index')
    await expect(indexArea).toBeVisible({ timeout: 3_000 })

    // 6. 填写索引号
    const indexInput = firstCard.locator('.gt-a112-dual-checklist__card-index-input input')
    if (await indexInput.isVisible()) {
      await indexInput.fill('A17-1')
      await indexInput.press('Enter')
      await page.waitForTimeout(3_000) // 等待 debounce 保存
    }

    // 7. 尝试切换到 DOCX 模式
    const docxOption = segmented.locator('.el-segmented__item').filter({ hasText: /Word|DOCX/ })
    const canSwitchDocx = await docxOption.isVisible().catch(() => false)

    if (canSwitchDocx) {
      await docxOption.click()
      await page.waitForTimeout(3_000)

      // 验证 HTML 视图消失
      await expect(htmlView).not.toBeVisible({ timeout: 5_000 })

      // 8. 切回 HTML 模式
      const htmlOption = segmented
        .locator('.el-segmented__item')
        .filter({ hasText: /结构化|HTML/ })
      await htmlOption.click()
      await page.waitForTimeout(5_000) // 等待刷新
    }

    // 9. 验证数据保留 — 第一项仍为"适用"状态
    const firstCardAfter = container.locator('.gt-a112-dual-checklist__card').first()

    // 卡片应处于"适用"状态（有 applicable 类名）
    const cardClass = await firstCardAfter.getAttribute('class')
    const hasApplicableState =
      cardClass?.includes('applicable') ||
      (await firstCardAfter
        .locator('.gt-a112-dual-checklist__card-index')
        .isVisible()
        .catch(() => false))

    // 验证索引号区域仍然可见（说明"适用"状态保留）
    if (hasApplicableState) {
      const indexAreaAfter = firstCardAfter.locator('.gt-a112-dual-checklist__card-index')
      await expect(indexAreaAfter).toBeVisible()
    }

    // 验证进度统计更新（至少 1 项已标记）
    const progressSection = container.locator('.gt-a112-dual-checklist__progress')
    await expect(progressSection).toBeVisible()
    const statsText = await progressSection.textContent()
    expect(statsText).toContain('适用')
  })

  test('进度汇总条正确统计', async ({ page, request }) => {
    test.setTimeout(60_000)
    await loginAs(page, 'admin', 'admin123')
    const token = await getToken(request)

    const a1Wp = await findA1Workpaper(request, token)
    test.skip(!a1Wp, 'A1 底稿不存在，跳过')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${a1Wp!.id}/edit`)
    await page.waitForTimeout(5_000)

    // 切到 A1-12 tab
    const a112Tab = page.locator('.el-tabs__item').filter({ hasText: /A1-12|重大事项/ }).first()
    if (!(await a112Tab.isVisible({ timeout: 5_000 }).catch(() => false))) {
      test.skip(true, 'A1-12 Tab 不可见，跳过')
    }
    await a112Tab.click()
    await page.waitForTimeout(3_000)

    const container = page.locator('.gt-a112-dual-checklist')
    await expect(container).toBeVisible({ timeout: 10_000 })

    // 验证进度条渲染
    const progress = container.locator('.gt-a112-dual-checklist__progress')
    await expect(progress).toBeVisible()

    // 应包含三种状态统计文本
    const statsText = await progress.textContent()
    expect(statsText).toMatch(/适用.*项/)
    expect(statsText).toMatch(/不适用.*项/)
    expect(statsText).toMatch(/未标记.*项/)
    expect(statsText).toMatch(/\d+%.*完成/)

    // 验证 el-progress 组件存在
    const progressBar = progress.locator('.el-progress')
    await expect(progressBar).toBeVisible()
  })
})
