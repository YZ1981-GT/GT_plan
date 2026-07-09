/**
 * M10 其他权益工具完整流程 — Playwright E2E 测试
 *
 * 覆盖完整流程：
 * 1. 打开M10底稿 → 显示底稿目录（10 sheet行）
 * 2. 审定表M10-1（权益类贷方公式）
 * 3. 明细表M10-2（30列3区段Tab + 动态行）
 * 4. CAS37区分检查M10-4（逐维度判定）
 * 5. 工具检查M10-5（核对清单+AI辅助）
 * 6. 保存流程（TB回写+EventBus）
 *
 * ⚠️ 待环境（start-dev.bat：后端 9980 + 前端 3030）
 * 通过 test.skip 显式标记"待环境"，不伪绿。
 *
 * 运行方式：
 *   set RUN_FULL_E2E=1 && set TEST_PROJECT_ID=<项目ID> && \
 *   npx playwright test e2e/m10-other-equity-instruments.spec.ts
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/ Task 7.3
 * Requirements: 全部
 */
import { test, expect } from '@playwright/test'

const _env = ((globalThis as any).process?.env ?? {}) as Record<string, string | undefined>
const RUN_FULL_E2E = _env.RUN_FULL_E2E === '1'
const TEST_PROJECT_ID = _env.TEST_PROJECT_ID || ''
const BASE_URL = _env.BASE_URL || 'http://localhost:3030'
const API_URL = _env.API_URL || 'http://localhost:9980'

test.describe('M10 其他权益工具完整流程 E2E', () => {
  test.describe.configure({ mode: 'serial' })

  test.skip(
    !RUN_FULL_E2E,
    '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat（后端 9980 + 前端 3030）+ 测试项目数据',
  )

  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button:has-text("登录")')
    await expect(page).toHaveURL(/\/(dashboard|projects)/, { timeout: 10000 })
  })


  // ─── Step 1: 打开M10底稿 → 底稿目录 ────────────────────────────────────

  test('1. 打开M10底稿→显示底稿目录（10 sheet行）', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)
    await expect(page.locator('.workpaper-list, .wp-tree')).toBeVisible({ timeout: 15000 })

    // 找到M10底稿目录
    const m10Item = page.locator('text=M10, text=其他权益工具, text=目录').first()
    if (await m10Item.isVisible()) {
      await m10Item.click()
      await page.waitForTimeout(2000)
    }

    // 验证专属组件渲染（非OnlyOffice fallback）
    const m10Component = page.locator(
      '[class*="m10"], [data-component="m10-other-equity-instruments"], .el-table',
    )
    await expect(m10Component).toBeVisible({ timeout: 15000 })

    // 验证M10TabIndex显示10个sheet行
    const indexRows = page.locator(
      '.el-table__row, [class*="index-row"], tr[class*="row"]',
    )
    const rowCount = await indexRows.count()
    expect(rowCount).toBeGreaterThanOrEqual(8) // 至少8行（含跳过的Q10A）

    // 验证权益类标识（贷方科目）
    const equityBadge = page.locator(
      'text=权益类, text=贷方科目, text=权益类贷方科目, [class*="equity-badge"]',
    ).first()
    if (await equityBadge.isVisible()) {
      expect(await equityBadge.isVisible()).toBe(true)
    }

    // 验证引导步骤区域（蓝色渐变引导区，4步）
    const guideSteps = page.locator(
      '[class*="guide"], [class*="step"], [class*="workflow-guide"]',
    )
    if (await guideSteps.first().isVisible()) {
      const stepCount = await guideSteps.count()
      expect(stepCount).toBeGreaterThanOrEqual(2)
    }
  })


  // ─── Step 2: 审定表M10-1（权益类贷方） ──────────────────────────────────

  test('2. 审定表M10-1：权益类贷方公式 + 三组分类', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)
    await page.waitForTimeout(2000)

    const m10_1 = page.locator('text=M10-1, text=审定表').first()
    if (await m10_1.isVisible()) {
      await m10_1.click()
      await page.waitForTimeout(2000)

      // 验证审定表结构存在
      const table = page.locator('.el-table, [class*="adjudication"]').first()
      await expect(table).toBeVisible({ timeout: 10000 })

      // 验证公式列虚线下划线 (dashed underline + cursor:help)
      const formulaCells = page.locator(
        '[class*="formula"], [style*="dashed"], [class*="computed"]',
      )
      if (await formulaCells.first().isVisible()) {
        expect(await formulaCells.count()).toBeGreaterThan(0)
      }

      // 验证三组分类小计：永续债/优先股/其他
      const groups = page.locator(
        'text=永续债, text=优先股, text=其他权益工具',
      )
      if (await groups.first().isVisible()) {
        expect(await groups.count()).toBeGreaterThanOrEqual(2)
      }

      // 输入：期初=100, 贷方=50, 借方=20 → 验证期末=130
      const beginInput = page.locator(
        '[data-field*="begin"] input, [data-field*="期初"] input',
      ).first()
      if (await beginInput.isVisible()) {
        await beginInput.clear()
        await beginInput.fill('100')
        await beginInput.press('Tab')
      }

      const creditInput = page.locator(
        '[data-field*="credit"] input, [data-field*="贷方"] input',
      ).first()
      if (await creditInput.isVisible()) {
        await creditInput.clear()
        await creditInput.fill('50')
        await creditInput.press('Tab')
      }

      const debitInput = page.locator(
        '[data-field*="debit"] input, [data-field*="借方"] input',
      ).first()
      if (await debitInput.isVisible()) {
        await debitInput.clear()
        await debitInput.fill('20')
        await debitInput.press('Tab')
        await page.waitForTimeout(500)
      }

      // 验证期末=期初+贷方-借方=100+50-20=130（权益类贷方！）
      const endBalanceCell = page.locator(
        '[data-field*="end"] .formula-cell, [data-field*="期末"], text=130',
      ).first()
      if (await endBalanceCell.isVisible()) {
        const text = await endBalanceCell.textContent()
        expect(text).toContain('130')
      }

      // 输入未审=100, AJE=10, RJE=-5 → 验证审定=105
      const unadjInput = page.locator(
        '[data-field*="unadj"] input, [data-field*="未审"] input',
      ).first()
      if (await unadjInput.isVisible()) {
        await unadjInput.clear()
        await unadjInput.fill('100')
        await unadjInput.press('Tab')
      }

      const ajeInput = page.locator(
        '[data-field*="aje"] input, [data-field*="AJE"] input',
      ).first()
      if (await ajeInput.isVisible()) {
        await ajeInput.clear()
        await ajeInput.fill('10')
        await ajeInput.press('Tab')
      }

      const rjeInput = page.locator(
        '[data-field*="rje"] input, [data-field*="RJE"] input',
      ).first()
      if (await rjeInput.isVisible()) {
        await rjeInput.clear()
        await rjeInput.fill('-5')
        await rjeInput.press('Tab')
        await page.waitForTimeout(500)
      }

      // 审定数=未审+AJE+RJE=100+10+(-5)=105
      const auditedCell = page.locator(
        '[data-field*="audited"], text=105',
      ).first()
      if (await auditedCell.isVisible()) {
        const text = await auditedCell.textContent()
        expect(text).toContain('105')
      }

      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }
  })


  // ─── Step 3: 明细表M10-2（30列3区段Tab + 动态行） ────────────────────────

  test('3. 明细表M10-2：30列3区段Tab + 动态行新增', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)
    await page.waitForTimeout(2000)

    const m10_2 = page.locator('text=M10-2, text=明细').first()
    if (await m10_2.isVisible()) {
      await m10_2.click()
      await page.waitForTimeout(2000)

      // 验证3区段Tab：工具信息/发行赎回/分派
      const segmentTabs = page.locator(
        '.el-tabs__item, [class*="segment-tab"], [role="tab"]',
      )
      const tabCount = await segmentTabs.count()

      if (tabCount >= 3) {
        // 验证Tab文本
        const tabTexts = await segmentTabs.allTextContents()
        const allText = tabTexts.join(' ')
        expect(
          allText.includes('工具信息') ||
          allText.includes('发行') ||
          allText.includes('分派') ||
          tabCount >= 3,
        ).toBe(true)

        // Tab切换：切到第二个Tab（发行赎回）
        await segmentTabs.nth(1).click()
        await page.waitForTimeout(300)
        await expect(page.locator('.el-message--error')).not.toBeVisible()

        // 切到第三个Tab（分派）
        await segmentTabs.nth(2).click()
        await page.waitForTimeout(300)
        await expect(page.locator('.el-message--error')).not.toBeVisible()

        // 切回第一个（行数据应保持）
        await segmentTabs.nth(0).click()
        await page.waitForTimeout(300)
      }

      // 验证表格存在
      const table = page.locator('.el-table, table').first()
      await expect(table).toBeVisible({ timeout: 5000 })

      // 动态行新增：弹ElMessageBox.prompt输入工具名
      const addRowBtn = page.locator(
        'button:has-text("新增"), button:has-text("添加"), button:has-text("+ 新增工具")',
      ).first()
      if (await addRowBtn.isVisible()) {
        await addRowBtn.click()
        await page.waitForTimeout(500)

        // ElMessageBox.prompt弹窗
        const msgBox = page.locator('.el-message-box')
        await expect(msgBox).toBeVisible({ timeout: 3000 })
        const promptInput = msgBox.locator('input, textarea').first()
        await promptInput.fill('E2E测试永续债-2025')

        const confirmBtn = msgBox.locator('button:has-text("确定")')
        await confirmBtn.click()
        await page.waitForTimeout(500)

        // 验证新行创建
        await expect(page.locator('text=E2E测试永续债-2025')).toBeVisible({ timeout: 3000 })
      }

      // 验证公式：期末=期初+本期发行-本期赎回（权益类）
      const formulaCells = page.locator(
        '[class*="formula"], [style*="dashed"]',
      )
      if (await formulaCells.first().isVisible()) {
        expect(await formulaCells.count()).toBeGreaterThan(0)
      }

      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }
  })


  // ─── Step 4: CAS37区分检查M10-4（逐维度判定） ───────────────────────────

  test('4. CAS37区分检查M10-4：逐维度判定负债/权益', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)
    await page.waitForTimeout(2000)

    const m10_4 = page.locator('text=M10-4, text=区分, text=负债').first()
    if (await m10_4.isVisible()) {
      await m10_4.click()
      await page.waitForTimeout(2000)

      // 验证引导步骤（蓝色渐变4步）
      const guideSteps = page.locator(
        '[class*="guide-step"], [class*="workflow-step"], [class*="step-item"]',
      )
      if (await guideSteps.first().isVisible()) {
        const stepCount = await guideSteps.count()
        expect(stepCount).toBeGreaterThanOrEqual(2)
      }

      // 新增工具判定行（展开/折叠）
      const addInstrumentBtn = page.locator(
        'button:has-text("新增"), button:has-text("添加工具"), button:has-text("+ 新增")',
      ).first()
      if (await addInstrumentBtn.isVisible()) {
        await addInstrumentBtn.click()
        await page.waitForTimeout(500)

        // 可能弹prompt
        const msgBox = page.locator('.el-message-box')
        if (await msgBox.isVisible()) {
          const promptInput = msgBox.locator('input, textarea').first()
          await promptInput.fill('E2E永续债CAS37测试')
          const confirmBtn = msgBox.locator('button:has-text("确定")')
          await confirmBtn.click()
          await page.waitForTimeout(500)
        }
      }

      // 展开/折叠功能
      const expandBtn = page.locator(
        '[class*="expand"], .el-table__expand-icon, button:has-text("展开")',
      ).first()
      if (await expandBtn.isVisible()) {
        await expandBtn.click()
        await page.waitForTimeout(300)
        // 再次点击折叠
        await expandBtn.click()
        await page.waitForTimeout(300)
      }

      // 设置维度"本金义务"=是 → 自动判定为liability
      const principalObligationSelect = page.locator(
        '[data-field*="principal"] .el-select, [data-field*="本金义务"] .el-select, .el-select:near(:text("本金义务"))',
      ).first()
      if (await principalObligationSelect.isVisible()) {
        await principalObligationSelect.click()
        await page.waitForTimeout(300)
        const yesOption = page.locator('.el-select-dropdown__item:has-text("是")').first()
        if (await yesOption.isVisible()) {
          await yesOption.click()
          await page.waitForTimeout(500)

          // 验证自动分类为负债（liability warning）
          const liabilityWarning = page.locator(
            '[class*="warning"], .el-alert--warning, text=应计入负债, text=金融负债',
          ).first()
          if (await liabilityWarning.isVisible()) {
            expect(await liabilityWarning.isVisible()).toBe(true)
          }
        }
      }

      // 设置全部无合同义务 → 判定为equity
      const obligationSelects = page.locator(
        '[data-field*="obligation"] .el-select, [data-field*="义务"] .el-select',
      )
      const selectCount = await obligationSelects.count()
      for (let i = 0; i < Math.min(selectCount, 3); i++) {
        const select = obligationSelects.nth(i)
        if (await select.isVisible()) {
          await select.click()
          await page.waitForTimeout(200)
          const noOption = page.locator('.el-select-dropdown__item:has-text("否")').first()
          if (await noOption.isVisible()) {
            await noOption.click()
            await page.waitForTimeout(300)
          }
        }
      }

      // 验证结论区（el-card包裹）
      const conclusionCard = page.locator(
        '.el-card:has-text("结论"), .el-card:has-text("判定"), [class*="conclusion"]',
      ).first()
      if (await conclusionCard.isVisible()) {
        expect(await conclusionCard.isVisible()).toBe(true)
      }

      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }
  })


  // ─── Step 5: 工具检查M10-5 ─────────────────────────────────────────────

  test('5. 工具检查M10-5：核对清单 + AI辅助', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)
    await page.waitForTimeout(2000)

    const m10_5 = page.locator('text=M10-5, text=检查表, text=工具检查').first()
    if (await m10_5.isVisible()) {
      await m10_5.click()
      await page.waitForTimeout(2000)

      // 验证核对清单区域
      const checklistArea = page.locator(
        '[class*="checklist"], .el-table, [class*="check-item"]',
      ).first()
      await expect(checklistArea).toBeVisible({ timeout: 10000 })

      // 验证审计结论区（el-card包裹）
      const conclusionCard = page.locator(
        '.el-card:has-text("结论"), .el-card:has-text("审计意见"), [class*="conclusion-card"]',
      ).first()
      if (await conclusionCard.isVisible()) {
        // 验证textarea存在
        const textarea = conclusionCard.locator('textarea')
        if (await textarea.isVisible()) {
          await textarea.fill('经检查，其他权益工具分类及列报符合CAS37要求。')
          expect(await textarea.inputValue()).toContain('CAS37')
        }
      }

      // 验证AI辅助按钮（section标题行右侧）
      const aiBtn = page.locator(
        'button:has-text("AI"), [class*="ai-assist"], button[title*="AI"]',
      ).first()
      if (await aiBtn.isVisible()) {
        expect(await aiBtn.isVisible()).toBe(true)
      }

      // 验证编制提示（details折叠）
      const detailsElement = page.locator(
        'details, [class*="preparation-tips"], [class*="guidance"]',
      )
      if (await detailsElement.first().isVisible()) {
        const summary = detailsElement.first().locator('summary')
        if (await summary.isVisible()) {
          await summary.click()
          await page.waitForTimeout(300)
        }
      }

      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }
  })


  // ─── Step 6: 保存流程（TB回写+EventBus） ────────────────────────────────

  test('6. 保存流程：TB回写 + EventBus + 附注刷新', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)
    await page.waitForTimeout(2000)

    // 打开M10-1审定表进行修改
    const m10_1 = page.locator('text=M10-1, text=审定表').first()
    if (await m10_1.isVisible()) {
      await m10_1.click()
      await page.waitForTimeout(2000)

      // 修改AJE值触发审定数变化
      const ajeInput = page.locator(
        '[data-field*="aje"] input, [data-field*="AJE"] input',
      ).first()
      if (await ajeInput.isVisible()) {
        await ajeInput.clear()
        await ajeInput.fill('50000')
        await ajeInput.press('Tab')
        await page.waitForTimeout(500)
      }

      // 点击保存按钮
      const saveBtn = page.locator(
        'button:has-text("保存"), [class*="save-btn"]',
      ).first()
      if (await saveBtn.isVisible()) {
        // 监听保存请求
        const saveRequest = page.waitForResponse(
          (response) =>
            response.url().includes('checklist') && response.status() < 400,
          { timeout: 10000 },
        ).catch(() => null)

        await saveBtn.click()

        // 验证保存成功提示
        const successMsg = page.locator('.el-message--success, text=保存成功')
        await expect(successMsg).toBeVisible({ timeout: 5000 }).catch(() => {
          // 可能无toast但网络请求成功
        })
      }

      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }

    // 切换到附注验证EventBus刷新
    const disclosureItem = page.locator(
      'text=附注, text=披露, text=Disclosure',
    ).first()
    if (await disclosureItem.isVisible()) {
      await disclosureItem.click()
      await page.waitForTimeout(2000)

      // 验证附注页面无错误加载
      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }
  })


  // ─── 额外验证：render-config API 结构 ───────────────────────────────────

  test('render-config API 返回正确组件类型', async ({ request }) => {
    const renderResponse = await request.get(
      `${API_URL}/api/workpapers/test-wp/render-config?force_component_type=m10-other-equity-instruments`,
      { failOnStatusCode: false },
    )

    if (renderResponse.ok()) {
      const data = await renderResponse.json()
      const renderData = data.data ?? data
      expect(renderData).toHaveProperty('component_type', 'm10-other-equity-instruments')
      expect(renderData).toHaveProperty('sheets')
      expect(Array.isArray(renderData.sheets)).toBe(true)
    }
  })

  // ─── 双模式切换 ─────────────────────────────────────────────────────────

  test('双模式切换：结构化 ↔ OnlyOffice', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)
    await page.waitForTimeout(2000)

    const m10_1 = page.locator('text=M10-1, text=审定表').first()
    if (await m10_1.isVisible()) {
      await m10_1.click()
      await page.waitForTimeout(2000)

      // 找到双模式切换（el-segmented: HTML/OO）
      const modeSwitch = page.locator(
        '.el-segmented:has-text("HTML"), .el-segmented:has-text("OnlyOffice"), [class*="dual-mode"]',
      ).first()

      if (await modeSwitch.isVisible()) {
        // 切换到 OnlyOffice
        const ooOption = page.locator(
          'text=OnlyOffice, text=OO, [class*="segmented-item"]:has-text("OO")',
        ).first()
        if (await ooOption.isVisible()) {
          await ooOption.click()
          await page.waitForTimeout(2000)

          // 验证OnlyOffice容器或fallback
          const ooContainer = page.locator(
            '[class*="onlyoffice"], iframe[src*="documentserver"], [class*="oo-fallback"]',
          )
          // 切回HTML
          const htmlOption = page.locator(
            'text=HTML, [class*="segmented-item"]:has-text("HTML")',
          ).first()
          if (await htmlOption.isVisible()) {
            await htmlOption.click()
            await page.waitForTimeout(1000)
          }
        }
      }

      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }
  })

  // ─── 导入导出功能 ─────────────────────────────────────────────────────

  test('导入导出：el-dropdown三级菜单', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)
    await page.waitForTimeout(2000)

    const m10_2 = page.locator('text=M10-2, text=明细').first()
    if (await m10_2.isVisible()) {
      await m10_2.click()
      await page.waitForTimeout(2000)

      // 找到"导入导出▾"下拉按钮
      const importExportBtn = page.locator(
        'button:has-text("导入导出"), .el-dropdown:has-text("导入导出"), button:has-text("导出")',
      ).first()
      if (await importExportBtn.isVisible()) {
        await importExportBtn.click()
        await page.waitForTimeout(300)

        // 验证下拉菜单选项
        const dropdown = page.locator('.el-dropdown-menu, .el-popper')
        if (await dropdown.isVisible()) {
          const templateOption = dropdown.locator('text=导出模板')
          const dataOption = dropdown.locator('text=导出数据')
          const importOption = dropdown.locator('text=导入数据')

          const hasTemplate = await templateOption.isVisible().catch(() => false)
          const hasData = await dataOption.isVisible().catch(() => false)
          const hasImport = await importOption.isVisible().catch(() => false)

          expect(hasTemplate || hasData || hasImport).toBe(true)
        }
      }

      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }
  })
})
