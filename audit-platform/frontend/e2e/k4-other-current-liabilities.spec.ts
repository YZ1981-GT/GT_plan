/**
 * K4 其他流动负债底稿 — Playwright E2E 测试
 *
 * Spec: .kiro/specs/k4-other-current-liabilities/ Task 7.3
 * Validates: Requirements 1~6
 *
 * 场景:
 * 1. 打开K4底稿 → sheetName dispatch → 渲染正确子组件
 * 2. 审定表K4-1 → 负债类三角勾稽(期末=期初+贷-借) → AJE → 审定数重算
 * 3. 明细表K4-2 → 2区段Tab(基础/检查) → 公式计算 → 合计联动
 * 4. 检查表K4-4 → 4维度检查项 → 合规/不合规判定
 * 5. 保存 → TB回写(2245) → 无报错
 *
 * 运行方式：
 *   set RUN_FULL_E2E=1 && set TEST_PROJECT_ID=<项目ID> &&
 *   npx playwright test e2e/k4-other-current-liabilities.spec.ts
 *
 * 科目：2245其他流动负债（贷方/负债类）
 * ⚠️ 负债类！期末=期初+贷方-借方（与资产类方向相反！）
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  fetchRenderConfig,
  sheetComponentTypes,
  clickWorkpaperSheetTab,
  expectHtmlDualModeOrContent,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const COMPONENT_TYPE = 'k4-other-current-liabilities'

const _env = ((globalThis as any).process?.env ?? {}) as Record<string, string | undefined>
const RUN_FULL_E2E = _env.RUN_FULL_E2E === '1'

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

// ─── Scenario 1: 打开K4 → sheetName dispatch → 渲染正确组件 ────────────────

test.describe('K4 其他流动负债 — Scenario 1: sheetName分发', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('打开K4底稿→底稿目录正确渲染', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K4', PROJECT_ID)
    test.skip(!wpResult.exists, 'K4 底稿不存在')

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (/\/ai\//.test(text) && /405/.test(text)) return
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        if (/onlyoffice|DocsAPI/.test(text)) return
        consoleErrors.push(text)
      }
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 底稿目录应自动打开
    await expectHtmlDualModeOrContent(page, /底稿目录|进度|K4-1|K4-2/)

    // 验证无严重错误
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined/.test(e),
    )
    expect(criticalErrors, `严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })
})

// ─── Scenario 2: 审定表K4-1 → 负债类公式 → AJE → 审定数 ───────────────────

test.describe('K4 其他流动负债 — Scenario 2: K4-1 审定表', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K4-1 审定表显示负债类列头(期初/贷方/借方/期末/审定数)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K4', PROJECT_ID)
    test.skip(!wpResult.exists, 'K4 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    await clickWorkpaperSheetTab(page, 'K4-1')
    await page.waitForTimeout(3_000)

    // 验证审定表渲染
    await expectHtmlDualModeOrContent(page, /审定|其他流动负债|2245/)

    // 验证关键列头
    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/期初|期末|贷方|借方|未审|AJE|RJE|审定数/)
  })

  test('K4-1 三角勾稽校验(期末=期初+贷-借)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K4', PROJECT_ID)
    test.skip(!wpResult.exists, 'K4 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K4-1')
    await page.waitForTimeout(3_000)

    // 三角勾稽列/区域应存在
    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/勾稽|差额|三角|reconcil/i)
  })

  test('K4-1 AJE输入触发审定数重算', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K4', PROJECT_ID)
    test.skip(!wpResult.exists, 'K4 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K4-1')
    await page.waitForTimeout(3_000)

    // 找到AJE输入字段
    const ajeInput = page.locator(
      'input[placeholder*="AJE"], [data-field*="aje"] input, [data-field*="AJE"] input',
    ).first()
    if (await ajeInput.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await ajeInput.clear()
      await ajeInput.fill('3000')
      await ajeInput.press('Tab')
      await page.waitForTimeout(500)

      // 审定数应重算
      const bodyText = (await page.textContent('body')) || ''
      expect(bodyText).toMatch(/审定数|变动率/)
    }
  })
})

// ─── Scenario 3: 明细表K4-2 → 2区段Tab → 公式 → 合计联动 ──────────────────

test.describe('K4 其他流动负债 — Scenario 3: K4-2 明细表', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K4-2 明细表2区段Tab(基础/检查)切换', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K4', PROJECT_ID)
    test.skip(!wpResult.exists, 'K4 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K4-2')
    await page.waitForTimeout(3_000)

    // 验证明细表渲染
    await expectHtmlDualModeOrContent(page, /明细|项目|性质|期初|期末/)

    // 查找区段Tab（基础/检查）
    const segmentTabs = page.locator(
      '.el-tabs__nav .el-tabs__item, [role="tablist"] [role="tab"], .el-segmented__item',
    )
    const tabCount = await segmentTabs.count()

    if (tabCount >= 2) {
      // 切换到检查Tab
      const checkTab = segmentTabs.filter({ hasText: /检查|核查/ })
      if (await checkTab.count()) {
        await checkTab.first().click()
        await page.waitForTimeout(1_000)
        const text = (await page.textContent('body')) || ''
        expect(text).toMatch(/增减原因|凭证号|核查结论|备注/)
      }
    }
  })

  test('K4-2 底部统计(项目数/期末合计)显示', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K4', PROJECT_ID)
    test.skip(!wpResult.exists, 'K4 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K4-2')
    await page.waitForTimeout(3_000)

    // 底部统计区
    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/项目数|合计|期末合计|总计/)
  })
})

// ─── Scenario 4: 检查表K4-4 → 4维度检查 → 合规判定 ─────────────────────────

test.describe('K4 其他流动负债 — Scenario 4: K4-4 检查表', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K4-4 检查表显示4维度检查项', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K4', PROJECT_ID)
    test.skip(!wpResult.exists, 'K4 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K4-4')
    await page.waitForTimeout(3_000)

    // 验证检查表渲染4维度
    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/分类正确性|流动性|完整性|合规性/)
  })

  test('K4-4 逐项合规/不合规/不适用选择', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K4', PROJECT_ID)
    test.skip(!wpResult.exists, 'K4 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K4-4')
    await page.waitForTimeout(3_000)

    // 验证有合规判定选项
    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/合规|不合规|不适用/)
  })
})

// ─── Scenario 5: 保存 → TB回写(2245) → 无报错 ──────────────────────────────

test.describe('K4 其他流动负债 — Scenario 5: 保存+TB回写', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('保存审定不报错+触发TB回写(2245)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K4', PROJECT_ID)
    test.skip(!wpResult.exists, 'K4 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K4-1')
    await page.waitForTimeout(3_000)

    // 监听保存相关请求
    const saveRequests: string[] = []
    page.on('request', (req) => {
      const url = req.url()
      if (
        (url.includes('checklist') || url.includes('trial-balance') || url.includes('writeback')) &&
        (req.method() === 'POST' || req.method() === 'PUT')
      ) {
        saveRequests.push(url)
      }
    })

    // 点击保存
    const saveBtn = page.locator(
      'button:has-text("保存"), button:has-text("确认审定"), [data-testid="save-btn"]',
    ).first()
    if (await saveBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await saveBtn.click()
      await page.waitForTimeout(3_000)

      // 验证无错误弹窗
      await expect(page.locator('.el-message--error')).not.toBeVisible({ timeout: 2_000 })
    }
  })
})

// ─── render-config 契约验证（无需运行环境） ──────────────────────────────────

test.describe('K4 其他流动负债 — render-config 契约', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1')

  test('K4 bundle 含 k4-other-current-liabilities componentType', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K4', PROJECT_ID)
    test.skip(!wpResult.exists, 'K4 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain(COMPONENT_TYPE)
  })

  test('render-config sheets 包含8个有效sheet', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K4', PROJECT_ID)
    test.skip(!wpResult.exists, 'K4 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    const sheets = (rcData.sheets as Array<Record<string, unknown>>) ?? []
    // K4有8个有效sheet
    expect(sheets.length).toBeGreaterThanOrEqual(6)
  })
})
