/**
 * 浏览器检查 ⑤ — 删除冲突提示
 *
 * 验证：删除公式设置条目时，后端对不存在 / 冲突的条目
 * 返回合理错误码而非 500。
 *
 * formula-e2e-ci-gate Task 2 / R3 第 5 项
 */
import { test, expect } from '@playwright/test'
import { loginAndInstall, standaloneProjectId } from './helpers'

const BACKEND = process.env.PLAYWRIGHT_BACKEND_URL || 'http://127.0.0.1:9980'

test.describe('删除冲突提示', () => {
  test.beforeEach(async ({ page, request }) => {
    await loginAndInstall(page, request)
  })

  test('删除不存在的公式条目返回 404/409 而非 500', async ({ request }) => {
    const projectId = standaloneProjectId()
    const fakeId = '00000000-0000-0000-0000-000000000000'
    const resp = await request.delete(
      `${BACKEND}/api/projects/${projectId}/formula-settings/${fakeId}`,
      {
        headers: { Authorization: `Bearer ${process.env.FH_E2E_TOKEN || ''}` },
      },
    )
    // 合理的响应：404（不存在）、409（冲突）、400、403、422
    // 不应是 500
    expect(resp.status(), '删除不存在条目不应返回 500').not.toBe(500)
    expect([400, 403, 404, 405, 409, 422]).toContain(resp.status())
  })
})
