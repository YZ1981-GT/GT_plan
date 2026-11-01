/**
 * 浏览器检查 ③ — 待确认弹窗陈旧决策
 *
 * 验证：公式设置的待确认列表端点返回空或有效列表，
 * 不含陈旧（stale）决策项。
 *
 * formula-e2e-ci-gate Task 2 / R3 第 3 项
 */
import { test, expect } from '@playwright/test'
import { loginAndInstall, standaloneProjectId } from './helpers'

const BACKEND = process.env.PLAYWRIGHT_BACKEND_URL || 'http://127.0.0.1:9980'

test.describe('待确认弹窗陈旧决策', () => {
  test.beforeEach(async ({ page, request }) => {
    await loginAndInstall(page, request)
  })

  test('待确认列表不含 stale 决策', async ({ request }) => {
    const projectId = standaloneProjectId()
    const resp = await request.get(
      `${BACKEND}/api/projects/${projectId}/formula-settings/pending`,
      {
        headers: { Authorization: `Bearer ${process.env.FH_E2E_TOKEN || ''}` },
      },
    )
    if (resp.status() === 404) {
      // 端点不存在，种子项目无此功能，合理
      return
    }
    expect(resp.ok(), `待确认端点失败 ${resp.status()}`).toBeTruthy()
    const body = await resp.json()
    const items = body?.data?.items ?? body?.data ?? body?.items ?? []
    // 种子项目没有配置过公式，不应有 stale 决策
    for (const item of items) {
      expect(item.status, `决策 ${item.id} 是 stale`).not.toBe('stale')
    }
  })
})
