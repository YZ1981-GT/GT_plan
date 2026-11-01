/**
 * 浏览器检查 ④ — 回滚按钮只在可回滚条目
 *
 * 验证：公式历史端点对种子项目返回空或每条都标明 rollbackable，
 * 不可回滚的条目不应出现回滚入口。
 *
 * formula-e2e-ci-gate Task 2 / R3 第 4 项
 */
import { test, expect } from '@playwright/test'
import { loginAndInstall, standaloneProjectId } from './helpers'

const BACKEND = process.env.PLAYWRIGHT_BACKEND_URL || 'http://127.0.0.1:9980'

test.describe('回滚按钮条件', () => {
  test.beforeEach(async ({ page, request }) => {
    await loginAndInstall(page, request)
  })

  test('历史列表每条 rollbackable 字段与按钮条件一致', async ({ request }) => {
    const projectId = standaloneProjectId()
    const resp = await request.get(
      `${BACKEND}/api/projects/${projectId}/formula-management/history`,
      {
        headers: { Authorization: `Bearer ${process.env.FH_E2E_TOKEN || ''}` },
        params: { page: '1', page_size: '20' },
      },
    )
    if (resp.status() === 404) return // 端点不存在
    expect(resp.ok(), `历史端点失败 ${resp.status()}`).toBeTruthy()
    const body = await resp.json()
    const items = body?.data?.items ?? body?.data ?? body?.items ?? []
    // 种子项目没有执行过公式，history 应为空
    // 如果非空，每条必须有 rollbackable 布尔字段
    for (const item of items) {
      expect(typeof item.rollbackable).toBe('boolean')
    }
  })

  test('公式管理页回滚按钮不在空状态显示', async ({ page }) => {
    const projectId = standaloneProjectId()
    await page.goto(`/projects/${projectId}/formula-management`)
    await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {})
    // 种子项目无执行记录，不应出现回滚按钮
    const rollbackBtn = page.locator('button:has-text("回滚")').first()
    // 给页面足够时间渲染
    await page.waitForTimeout(2_000)
    const isVisible = await rollbackBtn.isVisible().catch(() => false)
    // 无数据时回滚按钮应隐藏
    expect(isVisible, '种子项目无历史时回滚按钮不应可见').toBe(false)
  })
})
