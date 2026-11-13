/**
 * 浏览器检查 ④ — 回滚按钮只给可回滚的历史条目
 *
 * `GET /api/formula-audit-log/{pid}/{year}`：每条都有布尔 `rollbackable`；可回滚的必带当前修订号 `current_version`
 * （回滚要带它做并发校验），不可回滚的必写原因 `rollback_blocked_reason`（界面据此禁用按钮并提示）。
 * 先改一处本项目公式造出历史，判据不空转。原用例打不存在的 `/formula-management/history` 并把 404 当通过，
 * 界面部分打开的是不存在的路由。
 */
import { test, expect } from '@playwright/test'
import { api, apiToken, requireIsolatedDb, runTag, seedYear, standaloneProjectId } from './helpers'

test.describe('回滚按钮条件', () => {
  test('历史条目的可回滚标记与修订号 / 原因一致', async ({ request }) => {
    const token = await apiToken(request)
    await requireIsolatedDb(request, token)
    const pid = standaloneProjectId()
    const slot = `D2-1|E2E-${runTag()}|D7`
    const adapted = await api(request, token, 'PUT', `/api/projects/${pid}/formula-settings/wp/overrides`, {
      data: { items: [{ slot_key: slot, definition: { expression: "TB('1002','期末余额')", formula_type: 'auto_calc' } }] },
    })
    expect(adapted.status, JSON.stringify(adapted.error)).toBe(200)

    const r = await api(request, token, 'GET', `/api/formula-audit-log/${pid}/${seedYear()}`, { params: { limit: 200 } })
    expect(r.status).toBe(200)
    const items = r.data as any[]
    expect(items.length, '刚改过一处公式，本年度历史不应为空').toBeGreaterThan(0)
    for (const item of items) {
      expect(typeof item.rollbackable, `条目 ${item.id}`).toBe('boolean')
      if (item.rollbackable) {
        expect(Number.isInteger(item.current_version), `可回滚条目 ${item.id} 缺当前修订号`).toBe(true)
      } else {
        expect(String(item.rollback_blocked_reason || '').length, `不可回滚条目 ${item.id} 缺原因`).toBeGreaterThan(0)
      }
    }
    const other = await api(request, token, 'GET', `/api/formula-audit-log/${pid}/${seedYear() - 1}`, { params: { limit: 200 } })
    expect(other.status).toBe(200)
    const thisYear = new Set(items.map((i) => i.id))
    expect((other.data as any[]).filter((i) => thisYear.has(i.id)), '上一年度查不到本年度的修改').toEqual([])
  })
})
