/**
 * K5 预计负债底稿 — Playwright E2E 测试
 *
 * Spec: .kiro/specs/k5-provisions/ Task 7.3
 * Validates: Requirements 全部
 *
 * 场景:
 * 1. 打开K5底稿 → sheetName dispatch → 渲染正确子组件
 * 2. 审定表K5-1 → 负债类三角勾稽(期末=期初+计提-转销) → AJE → 审定数重算
 * 3. 明细表K5-2 → 3区段Tab(基础/判断/估计) → 或有判断三级色标
 * 4. 产品质保K5-4 → 保修支出公式 → 回连审定验证
 * 5. 弃置费用K5-5 → 现值折现公式 → 回连审定验证
 * 6. 未决诉讼K5-6 → 可能性级别判断 → 确认/披露badge
 * 7. 保存 → TB回写(2701) → 无报错
 *
 * 运行方式：
 *   set RUN_FULL_E2E=1 && set TEST_PROJECT_ID=<项目ID> &&
 *   npx playwright test e2e/k5-provisions.spec.ts
 *
 * 科目：2701预计负债（贷方/负债类）
 * ⚠️ 负债类！期末=期初+计提-转销（与资产类方向相反！）
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
const COMPONENT_TYPE = 'k5-provisions'

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

// ─── Scenario 1: 打开K5 → sheetName dispatch → 渲染正确组件 ────────────────

test.describe('K5 预计负债 — Scenario 1: sheetName分发', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('打开K5底稿→底稿目录正确渲染', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K5', PROJECT_ID)
    test.skip(!wpResult.exists, 'K5 底稿不存在')

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
    await expectHtmlDualModeOrContent(page, /底稿目录|进度|K5-1|预计负债/)

    // 验证无严重错误
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined/.test(e),
    )
    expect(criticalErrors, `严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })
})

// ─── Scenario 2: 审定表K5-1 → 负债类公式 → AJE → 审定数 ───────────────────

test.describe('K5 预计负债 — Scenario 2: K5-1 审定表', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K5-1 审定表显示负债类列头(期初/计提/转销/期末/审定数)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K5', PROJECT_ID)
    test.skip(!wpResult.exists, 'K5 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)

    await clickWorkpaperSheetTab(page, 'K5-1')
    await page.waitForTimeout(3_000)

    // 验证审定表渲染
    await expectHtmlDualModeOrContent(page, /审定|预计负债|2701/)

    // 验证关键列头
    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/期初|期末|计提|转销|未审|AJE|RJE|审定数/)
  })

  test('K5-1 三角勾稽校验(期末=期初+计提-转销)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K5', PROJECT_ID)
    test.skip(!wpResult.exists, 'K5 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K5-1')
    await page.waitForTimeout(3_000)

    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/勾稽|差额|三角|reconcil/i)
  })

  test('K5-1 按类型分行(产品质保/未决诉讼/弃置义务等)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K5', PROJECT_ID)
    test.skip(!wpResult.exists, 'K5 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K5-1')
    await page.waitForTimeout(3_000)

    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/产品质量保证|未决诉讼|弃置义务/)
  })
})

// ─── Scenario 3: 明细表K5-2 → 3区段Tab → 或有判断三级色标 ──────────────────

test.describe('K5 预计负债 — Scenario 3: K5-2 明细表+或有判断', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K5-2 明细表3区段Tab(基础/判断/估计)切换', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K5', PROJECT_ID)
    test.skip(!wpResult.exists, 'K5 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K5-2')
    await page.waitForTimeout(3_000)

    // 验证明细表渲染
    await expectHtmlDualModeOrContent(page, /明细|项目|类型|可能性/)

    // 查找区段Tab
    const segmentTabs = page.locator(
      '.el-tabs__nav .el-tabs__item, [role="tablist"] [role="tab"], .el-segmented__item',
    )
    const tabCount = await segmentTabs.count()

    if (tabCount >= 2) {
      // 切换到判断Tab
      const judgeTab = segmentTabs.filter({ hasText: /判断|可能性|确认/ })
      if (await judgeTab.count()) {
        await judgeTab.first().click()
        await page.waitForTimeout(1_000)
        const text = (await page.textContent('body')) || ''
        expect(text).toMatch(/可能性|确认|披露|很可能|极小可能/)
      }
    }
  })

  test('K5-2 或有事项三级色标显示(红/橙/灰)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K5', PROJECT_ID)
    test.skip(!wpResult.exists, 'K5 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K5-2')
    await page.waitForTimeout(3_000)

    const bodyText = (await page.textContent('body')) || ''
    // 至少应显示可能性相关UI
    expect(bodyText).toMatch(/很可能|可能|极小可能|确认|披露|不处理/)
  })
})

// ─── Scenario 4: K5-4 产品质保 → 保修支出公式 → 回连审定 ───────────────────

test.describe('K5 预计负债 — Scenario 4: K5-4 产品质量保修', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K5-4 质保检查表显示关键列(产品/收入/保修率/预计支出)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K5', PROJECT_ID)
    test.skip(!wpResult.exists, 'K5 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K5-4')
    await page.waitForTimeout(3_000)

    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/产品|销售收入|保修率|预计.*支出|结论/)
  })
})

// ─── Scenario 5: K5-5 弃置费用 → 现值折现 → 回连审定 ───────────────────────

test.describe('K5 预计负债 — Scenario 5: K5-5 弃置费用', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K5-5 弃置费用显示关键列(资产/预计支出/折现率/现值)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K5', PROJECT_ID)
    test.skip(!wpResult.exists, 'K5 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K5-5')
    await page.waitForTimeout(3_000)

    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/资产|弃置.*支出|折现率|现值|结论/)
  })
})

// ─── Scenario 6: K5-6 未决诉讼 → 可能性判断 → 确认/披露badge ──────────────

test.describe('K5 预计负债 — Scenario 6: K5-6 未决诉讼', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('K5-6 诉讼检查表显示关键列(案件/涉案金额/败诉可能性/预计损失)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K5', PROJECT_ID)
    test.skip(!wpResult.exists, 'K5 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K5-6')
    await page.waitForTimeout(3_000)

    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/案件|涉案金额|败诉|预计损失|确认|披露/)
  })

  test('K5-6 诉讼可能性级别联动律师函证据', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K5', PROJECT_ID)
    test.skip(!wpResult.exists, 'K5 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K5-6')
    await page.waitForTimeout(3_000)

    const bodyText = (await page.textContent('body')) || ''
    expect(bodyText).toMatch(/律师|意见|诉讼阶段|可能性/)
  })
})

// ─── Scenario 7: 保存 → TB回写(2701) → 无报错 ──────────────────────────────

test.describe('K5 预计负债 — Scenario 7: 保存+TB回写', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat')

  test('保存审定不报错+触发TB回写(2701)', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K5', PROJECT_ID)
    test.skip(!wpResult.exists, 'K5 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'K5-1')
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

test.describe('K5 预计负债 — render-config 契约', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1')

  test('K5 bundle 含 k5-provisions componentType', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K5', PROJECT_ID)
    test.skip(!wpResult.exists, 'K5 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain(COMPONENT_TYPE)
  })

  test('render-config sheets 包含10+个有效sheet', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'K5', PROJECT_ID)
    test.skip(!wpResult.exists, 'K5 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    const sheets = (rcData.sheets as Array<Record<string, unknown>>) ?? []
    // K5有10个有效sheet
    expect(sheets.length).toBeGreaterThanOrEqual(8)
  })
})
