/**
 * 浏览器检查 ② — 全局一键刷新的状态文案
 *
 * `POST /api/workpapers/draft-refresh`：种子项目没有余额表与试算表 ⇒ 前置校验阻断，422 + 中文原因 + 缺哪张表；
 * 空 scopes ⇒ 422（不再隐式全量刷新）。原用例打不存在的 `/formula-management/refresh-all` 并把 404 当通过。
 *
 * formula-e2e-ci-gate Task 2 / R3 第 2 项；spec formula-management-repair-closure R7 重写
 */
import { test, expect } from '@playwright/test'
import { api, apiToken, seedYear, standaloneProjectId } from './helpers'

test.describe('全局刷新状态文案', () => {
  let token = ''
  test.beforeAll(async ({ request }) => { token = await apiToken(request) })

  test('四表库缺数据：阻断并说明缺哪张表（不写任何数据）', async ({ request }) => {
    const r = await api(request, token, 'POST', '/api/workpapers/draft-refresh', {
      data: { project_id: standaloneProjectId(), year: seedYear(), scopes: ['report'] },
    })
    expect(r.status).toBe(422)
    expect(r.error.message).toBe('四表库数据不完整，无法一键刷新')
    expect(r.error.can_refresh).toBe(false)
    const blocking = Object.fromEntries((r.error.blocking as any[]).map((b) => [b.table, b.message]))
    expect(Object.keys(blocking).sort()).toEqual(['tb_balance', 'trial_balance'])
    expect(blocking.tb_balance).toContain('科目余额表无该项目')
  })

  test('空 scopes：422 校验失败（不再隐式全量刷新）', async ({ request }) => {
    const r = await api(request, token, 'POST', '/api/workpapers/draft-refresh', {
      data: { project_id: standaloneProjectId(), year: seedYear(), scopes: [] },
    })
    expect(r.status).toBe(422)
    expect(r.error).toBe('请求参数校验失败')
  })
})
