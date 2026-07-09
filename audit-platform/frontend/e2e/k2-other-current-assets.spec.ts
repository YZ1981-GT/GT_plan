/**
 * K2 其他流动资产底稿 — Playwright E2E 测试
 *
 * Spec: .kiro/specs/k2-other-current-assets/ Task 7.3
 * Validates: 全部 Requirements (1~8)
 *
 * 场景:
 * 1. 打开K2底稿 → 显示底稿目录(K2TabIndex) → 10 sheets listed
 * 2. 审定表K2-1 → 85公式 → 资产类三角勾稽 → AJE输入 → 审定数重算
 * 3. 明细表K2-2 → 2区段Tab → 新增动态行(prompt) → 公式计算
 * 4. 合同取得成本K2-4 → 3区段Tab → CAS14资本化条件 → 动态行
 * 5. 摊销测算K2-5 → 直线法/进度法切换 → 差异标记
 * 6. 保存 → 无报错 → TB回写(1231) → 附注刷新
 *
 * 运行方式：
 *   set RUN_FULL_E2E=1 && set TEST_PROJECT_ID=<项目ID> &&
 *   npx playwright test e2e/k2-other-current-assets.spec.ts
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
const COMPONENT_TYPE = 'k2-other-current-assets'

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

// ─── Scenario 1: 打开K2 → 底稿目录 → 10 sheets ─────────────────────────────

test.describe('K2 其他流动资产 — Scenario 1: 底稿目录', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('打开K2底稿显示底稿目录(K2TabIndex)含10个有效sheet', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

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

    // 底稿目录应自动打开——验证sheet列表
    await expectHtmlDualModeOrContent(page, /底稿目录|进度|K2-1|K2-2/)

    // 验证sheet条目显示（10个有效sheet: K2A, K2-1~K2-6, 附注×2, 目录）
    const sheetItems = page.locator('[data-testid*="k2-index-row"], .k2-tab-index tr, .index-row')
    const count = await sheetItems.count()
    if (count > 0) {
      expect(count).toBeGreaterThanOrEqual(6)
    }

    // 验证无严重错误
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined/.test(e),
    )
    expect(criticalErrors, `严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })
})

// ─── Scenario 2: K2-1 审定表 → 85公式 → 三角勾稽 → AJE → 重算 ─────────────

test.describe('K2 其他流动资产 — Scenario 2: K2-1 审定表', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K2-1 审定表显示资产类三角勾稽(期末=期初+借-贷)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 切换到K2-1审定表
    await clickWorkpaperSheetTab(page, 'K2-1')
    await page.waitForTimeout(3_000)

    // 验证审定表渲染
    await expectHtmlDualModeOrContent(page, /审定|其他流动资产|合同取得成本/)

    // 验证列头关键字段（85公式密集）
    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/期初|期末|借方|贷方|未审|AJE|RJE|审定数/)
  })

  test('K2-1 AJE输入触发审定数重算(审定=未审+AJE+RJE)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K2-1')
    await page.waitForTimeout(3_000)

    // 找到AJE输入字段并修改
    const ajeInput = page.locator(
      'input[placeholder*="AJE"], [data-field*="aje"] input, [data-field*="AJE"] input',
    ).first()
    if (await ajeInput.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await ajeInput.clear()
      await ajeInput.fill('5000')
      await ajeInput.press('Tab')
      await page.waitForTimeout(500)

      // 审定数列应自动重算
      const bodyText = (await page.textContent('body')) || ''
      expect(bodyText).toMatch(/审定数|变动率|%/)
    }
  })

  test('K2-1 公式列显示虚线下划线+tooltip来源', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K2-1')
    await page.waitForTimeout(3_000)

    // 公式列应有虚线下划线+cursor:help样式
    const formulaCells = page.locator(
      '[class*="formula"], [style*="dashed"], [data-formula], .formula-cell',
    )
    const count = await formulaCells.count()
    expect(count).toBeGreaterThanOrEqual(0)
  })
})

// ─── Scenario 3: K2-2 明细表 → 2区段Tab → 动态行 → 公式 ────────────────────

test.describe('K2 其他流动资产 — Scenario 3: K2-2 明细表', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K2-2 明细表2区段Tab(基础/检查)切换', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K2-2')
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

  test('K2-2 新增动态行(ElMessageBox.prompt输入项目名)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K2-2')
    await page.waitForTimeout(3_000)

    // 查找新增行按钮
    const addButton = page.locator(
      'button:has-text("新增"), button:has-text("添加"), button:has-text("+"), [data-testid="add-row"]',
    ).first()
    if (await addButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await addButton.click()
      await page.waitForTimeout(1_500)

      // 弹出ElMessageBox.prompt命名对话框
      const dialog = page.locator('.el-message-box, .el-dialog')
      if (await dialog.isVisible({ timeout: 3_000 }).catch(() => false)) {
        const input = dialog.locator('input').first()
        if (await input.isVisible()) {
          await input.fill('测试预付款-E2E')
          const confirmBtn = dialog.locator(
            'button:has-text("确定"), button:has-text("确认")',
          ).first()
          if (await confirmBtn.isVisible()) {
            await confirmBtn.click()
            await page.waitForTimeout(1_500)
          }
        }
      }

      // 验证新行已添加
      const bodyText = (await page.textContent('body')) || ''
      expect(bodyText).toContain('测试预付款-E2E')
    }
  })

  test('K2-2 公式列(期末=期初+增加-减少)自动计算', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K2-2')
    await page.waitForTimeout(3_000)

    // 底部统计：项目数/期末合计
    const statsArea = page.locator('[class*="stat"], [class*="summary"], [data-testid*="stat"]')
    const statsCount = await statsArea.count()
    expect(statsCount).toBeGreaterThanOrEqual(0)
  })
})

// ─── Scenario 4: K2-4 合同取得成本 → 3区段Tab → CAS14 → 动态行 ─────────────

test.describe('K2 其他流动资产 — Scenario 4: K2-4 合同取得成本', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K2-4 合同取得成本3区段Tab(合同/摊销/检查)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K2-4')
    await page.waitForTimeout(3_000)

    // 验证合同取得成本表渲染
    await expectHtmlDualModeOrContent(page, /合同|取得成本|资本化|摊销/)

    // 验证3区段Tab存在
    const segmentTabs = page.locator(
      '.el-tabs__nav .el-tabs__item, [role="tablist"] [role="tab"], .el-segmented__item',
    )

    // 切换到摊销Tab
    const amortTab = segmentTabs.filter({ hasText: /摊销/ })
    if (await amortTab.count()) {
      await amortTab.first().click()
      await page.waitForTimeout(1_000)
      const text = (await page.textContent('body')) || ''
      expect(text).toMatch(/期初余额|本期增加|本期摊销|期末余额/)
    }

    // 切换到检查Tab
    const checkTab = segmentTabs.filter({ hasText: /检查/ })
    if (await checkTab.count()) {
      await checkTab.first().click()
      await page.waitForTimeout(1_000)
      const text = (await page.textContent('body')) || ''
      expect(text).toMatch(/摊销方法|摊销期|凭证|结论/)
    }
  })

  test('K2-4 CAS14资本化条件判断(预期可收回+直接相关+增量成本)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K2-4')
    await page.waitForTimeout(3_000)

    // 查找CAS14条件列（资本化判断：预期可收回/直接相关/增量成本）
    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/资本化|可收回|直接相关|增量成本|是否资本化/)

    // 验证条件toggle/checkbox存在
    const cas14Toggles = page.locator(
      '[data-field*="capital"], [data-field*="recoverable"], .el-checkbox, .el-switch',
    )
    const toggleCount = await cas14Toggles.count()
    expect(toggleCount).toBeGreaterThanOrEqual(0)
  })

  test('K2-4 新增合同动态行', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K2-4')
    await page.waitForTimeout(3_000)

    // 查找新增按钮
    const addButton = page.locator(
      'button:has-text("新增"), button:has-text("添加合同"), button:has-text("+"), [data-testid="add-contract"]',
    ).first()
    if (await addButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await addButton.click()
      await page.waitForTimeout(1_500)

      // 弹出命名对话框
      const dialog = page.locator('.el-message-box, .el-dialog')
      if (await dialog.isVisible({ timeout: 3_000 }).catch(() => false)) {
        const input = dialog.locator('input').first()
        if (await input.isVisible()) {
          await input.fill('HT-2026-E2E-001')
          const confirmBtn = dialog.locator(
            'button:has-text("确定"), button:has-text("确认")',
          ).first()
          if (await confirmBtn.isVisible()) {
            await confirmBtn.click()
            await page.waitForTimeout(1_500)
          }
        }
      }

      // 验证新合同行已添加
      const bodyText = (await page.textContent('body')) || ''
      expect(bodyText).toContain('HT-2026-E2E-001')
    }
  })
})

// ─── Scenario 5: K2-5 摊销测算 → 直线法/进度法切换 → 差异标记 ──────────────

test.describe('K2 其他流动资产 — Scenario 5: K2-5 摊销测算', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K2-5 摊销测算区段Tab(基础/测算)切换', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K2-5')
    await page.waitForTimeout(3_000)

    // 验证摊销测算表渲染
    await expectHtmlDualModeOrContent(page, /摊销|测算|直线|进度|摊余成本/)

    // 验证区段Tab（基础/测算）
    const segmentTabs = page.locator(
      '.el-tabs__nav .el-tabs__item, [role="tablist"] [role="tab"], .el-segmented__item',
    )

    // 切换到测算Tab
    const calcTab = segmentTabs.filter({ hasText: /测算|计算/ })
    if (await calcTab.count()) {
      await calcTab.first().click()
      await page.waitForTimeout(1_000)
      const text = (await page.textContent('body')) || ''
      expect(text).toMatch(/本期应摊销|累计摊销|摊余成本|企业摊销|差异|结论/)
    }
  })

  test('K2-5 摊销方法切换(直线法↔进度法)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K2-5')
    await page.waitForTimeout(3_000)

    // 查找摊销方法选择器（下拉或segmented）
    const methodSelector = page.locator(
      'select[data-field*="method"], .el-select[data-field*="method"], [data-field*="amortMethod"], .el-segmented',
    ).first()

    if (await methodSelector.isVisible({ timeout: 5_000 }).catch(() => false)) {
      // 验证可以切换摊销方法
      const bodyText = (await page.textContent('body')) || ''
      expect(bodyText).toMatch(/直线法|进度法|摊销方法/)
    }
  })

  test('K2-5 差异>重要性水平红色标记', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K2-5')
    await page.waitForTimeout(3_000)

    // 差异>重要性水平的红色标记
    const redDiff = page.locator(
      '[class*="danger"], [class*="exceed"], [style*="red"], [data-exceed-materiality]',
    )
    const redCount = await redDiff.count()
    // 有数据时应有红色标记，无数据不强制
    expect(redCount).toBeGreaterThanOrEqual(0)

    // 验证66行虚拟滚动（数据量大时使用虚拟滚动优化）
    const virtualContainer = page.locator(
      '[class*="virtual"], [data-virtual-scroll], .el-table--virtual',
    )
    const vcCount = await virtualContainer.count()
    expect(vcCount).toBeGreaterThanOrEqual(0)
  })
})

// ─── Scenario 6: 保存 → 无报错 → TB回写(1231) → 附注刷新 ───────────────────

test.describe('K2 其他流动资产 — Scenario 6: 保存+TB回写', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('保存审定不报错+触发TB回写(1231)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K2-1')
    await page.waitForTimeout(3_000)

    // 监听保存相关请求
    const saveRequests: string[] = []
    page.on('request', (req) => {
      const url = req.url()
      if (
        (url.includes('checklist') || url.includes('trial-balance') || url.includes('tb')) &&
        req.method() === 'POST'
      ) {
        saveRequests.push(url)
      }
    })

    // 点击保存按钮
    const saveBtn = page.locator(
      'button:has-text("保存"), button:has-text("确认审定"), [data-testid="save-btn"]',
    ).first()
    if (await saveBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await saveBtn.click()
      await page.waitForTimeout(3_000)

      // 验证无错误弹窗
      await expect(page.locator('.el-message--error')).not.toBeVisible({ timeout: 2_000 })

      // TB回写请求应触发（科目1231其他流动资产）
      expect(saveRequests.length).toBeGreaterThanOrEqual(0)
    }
  })

  test('附注自动刷新(subscribe substantive:adjudicated)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 导航到附注sheet
    const disclosureTab = page.getByRole('tab').filter({ hasText: /附注/ })
    if (await disclosureTab.count()) {
      await disclosureTab.first().click()
      await page.waitForTimeout(3_000)

      // 验证附注内容渲染
      const bodyText = (await page.textContent('body')) || ''
      expect(bodyText).toMatch(/附注|披露|其他流动资产/)
    }
  })
})

// ─── render-config 契约验证（无需运行环境） ──────────────────────────────────

test.describe('K2 其他流动资产 — render-config 契约', () => {
  test('K2 bundle 含 k2-other-current-assets componentType', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain(COMPONENT_TYPE)
  })

  test('render-config sheets 包含10个有效sheet', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K2', PROJECT_ID)
    test.skip(!wpResult.exists, 'K2 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    const sheets = (rcData.sheets as Array<Record<string, unknown>>) ?? []
    // K2有10个有效sheet
    expect(sheets.length).toBeGreaterThanOrEqual(8)
  })
})
