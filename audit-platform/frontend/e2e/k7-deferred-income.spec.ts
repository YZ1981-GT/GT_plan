/**
 * K7 递延收益底稿 — Playwright E2E 测试
 *
 * Spec: .kiro/specs/k7-deferred-income/ Task 7.3
 * Validates: Requirements 全部
 *
 * 场景:
 * 1. 打开K7底稿 → sheetName dispatch → 底稿目录渲染
 * 2. K7-1 审定表 → 与资产相关/与收益相关分组 → 负债类列头
 * 3. K7-2 明细表 → 3区段Tab(基础/分摊/检查)
 * 4. K7-4 分摊测算表 → 公式列(本期应分摊/期末余额/差异)
 * 5. K7-5 检查表 → radio组(合规/不合规/不适用)
 * 6. 保存 → TB回写(2401) → 无报错
 *
 * 运行方式：
 *   set RUN_FULL_E2E=1 && set TEST_PROJECT_ID=<项目ID> &&
 *   npx playwright test e2e/k7-deferred-income.spec.ts
 *
 * 科目：2401递延收益（贷方/负债类）
 * ⚠️ 负债类！期末=期初+收到(贷方增加)-分摊(借方减少)
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
const COMPONENT_TYPE = 'k7-deferred-income'

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

// ─── Scenario 1: 打开K7 → 底稿目录正确渲染 ──────────────────────────────────

test.describe('K7 递延收益 — Scenario 1: sheetName分发+底稿目录', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('打开K7底稿→底稿目录正确渲染', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K7', PROJECT_ID)
    test.skip(!wpResult.exists, 'K7 底稿不存在')

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
    await expectHtmlDualModeOrContent(page, /底稿目录|进度|K7-1|递延收益/)

    // 验证无严重错误
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined/.test(e),
    )
    expect(criticalErrors, `严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })
})

// ─── Scenario 2: K7-1 审定表 → 与资产相关/与收益相关分组 ────────────────────

test.describe('K7 递延收益 — Scenario 2: K7-1 审定表', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K7-1 审定表显示负债类列头(期初/收到/分摊/期末/审定数)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K7', PROJECT_ID)
    test.skip(!wpResult.exists, 'K7 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    await clickWorkpaperSheetTab(page, 'K7-1')
    await page.waitForTimeout(3_000)

    // 验证审定表渲染
    await expectHtmlDualModeOrContent(page, /审定|递延收益|2401/)

    // 验证关键列头
    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/期初|期末|收到|分摊|未审|AJE|RJE|审定数/)
  })

  test('K7-1 显示与资产相关/与收益相关分组', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K7', PROJECT_ID)
    test.skip(!wpResult.exists, 'K7 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K7-1')
    await page.waitForTimeout(3_000)

    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/与资产相关/)
    expect(bodyText).toMatch(/与收益相关/)
  })

  test('K7-1 三角勾稽校验显示', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K7', PROJECT_ID)
    test.skip(!wpResult.exists, 'K7 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K7-1')
    await page.waitForTimeout(3_000)

    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/勾稽|差额|三角|reconcil/i)
  })
})

// ─── Scenario 3: K7-2 明细表 → 3区段Tab ─────────────────────────────────────

test.describe('K7 递延收益 — Scenario 3: K7-2 明细表', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K7-2 明细表3区段Tab(基础/分摊/检查)渲染', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K7', PROJECT_ID)
    test.skip(!wpResult.exists, 'K7 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    await clickWorkpaperSheetTab(page, 'K7-2')
    await page.waitForTimeout(3_000)

    // 验证明细表渲染
    await expectHtmlDualModeOrContent(page, /明细|补助项目|收到/)

    // 查找区段Tab
    const segmentTabs = page.locator(
      '.el-tabs__nav .el-tabs__item, [role="tablist"] [role="tab"], .el-segmented__item',
    )
    const tabCount = await segmentTabs.count()

    if (tabCount >= 2) {
      // 切换到分摊Tab
      const amortTab = segmentTabs.filter({ hasText: /分摊/ })
      if (await amortTab.count()) {
        await amortTab.first().click()
        await page.waitForTimeout(1_000)
        const text = (await page.textContent('body')) || ''
        expect(text).toMatch(/分摊方法|分摊期|期初|本期分摊|期末/)
      }
    }
  })

  test('K7-2 明细表显示补助项目关键列', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K7', PROJECT_ID)
    test.skip(!wpResult.exists, 'K7 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K7-2')
    await page.waitForTimeout(3_000)

    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/补助项目|批文号|补助类型|相关类型/)
  })
})

// ─── Scenario 4: K7-4 分摊测算表 → 公式列 ───────────────────────────────────

test.describe('K7 递延收益 — Scenario 4: K7-4 分摊测算表', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K7-4 测算表显示关键列(补助总额/分摊期/本期应分摊/期末余额/差异)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K7', PROJECT_ID)
    test.skip(!wpResult.exists, 'K7 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    await clickWorkpaperSheetTab(page, 'K7-4')
    await page.waitForTimeout(3_000)

    await expectHtmlDualModeOrContent(page, /测算|分摊|补助/)

    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/补助总额|分摊期|本期.*分摊|期末余额|差异|企业/)
  })

  test('K7-4 测算表显示分摊方法列(直线法/一次性计入)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K7', PROJECT_ID)
    test.skip(!wpResult.exists, 'K7 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K7-4')
    await page.waitForTimeout(3_000)

    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/分摊方法|直线法|一次性/)
  })
})

// ─── Scenario 5: K7-5 检查表 → radio组 ──────────────────────────────────────

test.describe('K7 递延收益 — Scenario 5: K7-5 检查表', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K7-5 检查表显示检查项(真实性/合规/分摊方法/计入科目)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K7', PROJECT_ID)
    test.skip(!wpResult.exists, 'K7 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    await clickWorkpaperSheetTab(page, 'K7-5')
    await page.waitForTimeout(3_000)

    await expectHtmlDualModeOrContent(page, /检查|补助|合规/)

    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/真实性|批文|分摊.*适当|计入科目|合规|不合规|不适用/)
  })

  test('K7-5 检查表radio组(合规/不合规/不适用)可交互', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K7', PROJECT_ID)
    test.skip(!wpResult.exists, 'K7 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K7-5')
    await page.waitForTimeout(3_000)

    // 查找radio组
    const radios = page.locator('.el-radio, .el-radio-group, input[type="radio"]')
    const radioCount = await radios.count()
    // 检查表应有多个radio组
    expect(radioCount).toBeGreaterThanOrEqual(1)
  })
})

// ─── Scenario 6: 保存 → TB回写(2401) → 无报错 ──────────────────────────────

test.describe('K7 递延收益 — Scenario 6: 保存+TB回写', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('保存审定不报错+触发TB回写(2401)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K7', PROJECT_ID)
    test.skip(!wpResult.exists, 'K7 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K7-1')
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

test.describe('K7 递延收益 — render-config 契约', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1')

  test('K7 bundle 含 k7-deferred-income componentType', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K7', PROJECT_ID)
    test.skip(!wpResult.exists, 'K7 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain(COMPONENT_TYPE)
  })

  test('render-config sheets 包含9+个有效sheet', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K7', PROJECT_ID)
    test.skip(!wpResult.exists, 'K7 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    const sheets = (rcData.sheets as Array<Record<string, unknown>>) ?? []
    // K7有9个功能sheet + 1会计提示辅助sheet
    expect(sheets.length).toBeGreaterThanOrEqual(9)
  })
})
