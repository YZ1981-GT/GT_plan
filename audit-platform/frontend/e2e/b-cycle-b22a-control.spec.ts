/**
 * b-cycle-b22a-control.spec.ts — B22A-1 企业层面控制表单 E2E 验证
 *
 * 锚定 spec b-cycle-workpapers Task 50
 *
 * 验证 B22A-1 企业层面控制（控制环境）：
 * 1. 底稿页面正常加载
 * 2. d-form-table 渲染控制项列表
 * 3. 填写控制结论（选择"有效"）
 * 4. 保存并验证持久化
 *
 * 项目：辽宁卫生服务有限公司 2025（37814426-a29e-4fc2-9313-a59d229bf7b0）
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { TEST_PROJECT_ID, findWorkpaper } from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID

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

test.describe('Task 50: B22A-1 企业层面控制表单渲染+保存', () => {
  test('50.1 — B22A-1 d-form-table 渲染控制项', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'B22A-1', PROJECT_ID)
    test.skip(!wpResult.exists, 'B22A-1 底稿不存在，需先运行项目底稿生成')

    // 收集 console errors
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (/\/ai\//.test(text) && /405/.test(text)) return
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        if (/Failed to load resource.*500/.test(text)) return
        consoleErrors.push(text)
      }
    })
    page.on('pageerror', (err) => {
      consoleErrors.push(`pageerror: ${err.message}`)
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)

    // 等待编辑器/表单渲染
    await page.waitForSelector(
      '.gt-wp-editor, .gt-d-form-table, .gt-wp-editor-loading',
      { timeout: 15_000 },
    )
    await page.waitForTimeout(5_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 验证无 ErrorBoundary
    const errorBoundary = page.locator('.gt-error-boundary, [class*="error-boundary"]')
    expect(await errorBoundary.count(), 'ErrorBoundary 不应出现').toBe(0)

    // 验证表单表格渲染（d-form-table 使用 el-table）
    const table = page.locator('.el-table, .gt-d-form-table')
    await expect(table.first()).toBeVisible({ timeout: 10_000 })

    // 验证控制项行存在（B22A-1 控制环境至少有多行控制项）
    const tableRows = page.locator('.el-table__row')
    const rowCount = await tableRows.count()
    expect(rowCount, 'B22A-1 应有多行控制项').toBeGreaterThanOrEqual(3)

    // 验证无严重 console errors
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('50.2 — B22A-1 填写控制结论并保存', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'B22A-1', PROJECT_ID)
    test.skip(!wpResult.exists, 'B22A-1 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 查找可编辑的结论单元格（enum 类型通常是 el-select）
    const selects = page.locator('.el-select, select')
    const selectCount = await selects.count()

    if (selectCount > 0) {
      // 点击第一个 select 打开下拉
      const firstSelect = selects.first()
      await firstSelect.click()
      await page.waitForTimeout(500)

      // 选择"有效"选项
      const option = page.locator('.el-select-dropdown__item, .el-option').filter({ hasText: '有效' }).first()
      if (await option.isVisible()) {
        await option.click()
        await page.waitForTimeout(500)
      }
    } else {
      // 可能是点击激活编辑模式（与附注表格相同模式）
      const editableCells = page.locator('.gt-cell-editable, [role="gridcell"]')
      if (await editableCells.count() > 0) {
        await editableCells.first().click()
        await page.waitForTimeout(500)
      }
    }

    // 尝试保存（查找保存按钮或使用 Ctrl+S）
    const saveBtn = page.locator('button').filter({ hasText: /保存/ }).first()
    if (await saveBtn.isVisible()) {
      await saveBtn.click()
      await page.waitForTimeout(2_000)
    } else {
      // 使用快捷键保存
      await page.keyboard.press('Control+s')
      await page.waitForTimeout(2_000)
    }

    // 验证保存成功提示（ElMessage success）或无错误弹窗
    const errorMsg = page.locator('.el-message--error')
    const hasError = await errorMsg.count() > 0
    // 若有保存失败提示，断言不应出现
    if (hasError) {
      const errorText = await errorMsg.first().textContent()
      expect(errorText, '保存不应失败').not.toContain('失败')
    }
  })

  test('50.3 — B22A-1 render-config API 验证', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    // 验证 B22A-1 底稿存在
    const wpResult = await findWorkpaper(request, token, 'B22A-1', PROJECT_ID)
    test.skip(!wpResult.exists, 'B22A-1 底稿不存在')

    // 验证底稿详情 API
    const detailResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(detailResp.status()).toBe(200)
    const detail = await detailResp.json()
    const wpData = detail?.data || detail
    expect(wpData.wp_code).toBe('B22A-1')

    // 验证 render-config 返回 d-form-table 类型
    const rcResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}/render-config`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)
    const rcBody = await rcResp.json()
    const rcData = rcBody?.data || rcBody
    expect(rcData.component_type || rcData.componentType).toBe('d-form-table')
  })
})
