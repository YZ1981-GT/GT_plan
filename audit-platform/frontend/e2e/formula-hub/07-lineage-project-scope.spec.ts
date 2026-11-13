/**
 * 浏览器检查 ⑦ — 溯源与附件只见本项目
 *
 * `GET /api/projects/{pid}/lineage`（统一溯源）：各子源都要跑通（`partial` 为假、没有子源错误），当前对象就是查询的底稿；
 * 附件只列本项目的。种子没有附件（seed_formula_e2e.py 只建账号、项目、底稿），也没有非管理员账号 ⇒ 跨项目附件泄露这一条
 * 显式跳过并写明原因（后端由 test_formula_hub_endpoint_authz.py 的 attachment-link / links 配方在 PG 上覆盖）。
 * 原用例打不存在的 `/attachment-lineage`，404 即通过；界面部分打开的是不存在的路由。
 */
import { test, expect } from '@playwright/test'
import { api, apiToken, consolProjectId, seedYear, standaloneProjectId } from './helpers'

test.describe('溯源项目隔离', () => {
  let token = ''
  test.beforeAll(async ({ request }) => { token = await apiToken(request) })

  for (const [label, pid] of [['单体', standaloneProjectId], ['合并', consolProjectId]] as const) {
    test(`${label}项目：底稿溯源各子源跑通`, async ({ request }) => {
      const r = await api(request, token, 'GET', `/api/projects/${pid()}/lineage`, {
        params: { object_type: 'wp_cell', object_id: 'D2-1', year: seedYear() },
      })
      expect(r.status, JSON.stringify(r.error)).toBe(200)
      expect(r.data.partial, `子源失败：${JSON.stringify(r.data.errors)}`).toBe(false)
      expect(r.data.errors).toEqual([])
      expect(Array.isArray(r.data.upstream) && Array.isArray(r.data.downstream)).toBe(true)
      expect(Array.isArray(r.data.attachments)).toBe(true)
    })
  }

  test('附件只列本项目的', async ({ request }) => {
    const a = await api(request, token, 'GET', `/api/projects/${standaloneProjectId()}/lineage`, {
      params: { object_type: 'wp_cell', object_id: 'D2-1', year: seedYear() },
    })
    test.skip((a.data?.attachments || []).length === 0,
      '种子没有附件、五个账号都是管理员：跨项目附件泄露无法在 E2E 里构造（后端 PG 配方覆盖）')
    const b = await api(request, token, 'GET', `/api/projects/${consolProjectId()}/lineage`, {
      params: { object_type: 'wp_cell', object_id: 'D2-1', year: seedYear() },
    })
    const mine = new Set((a.data.attachments as any[]).map((x) => x.attachment_id))
    expect((b.data.attachments as any[]).filter((x) => mine.has(x.attachment_id)), '合并项目看到了单体项目的附件').toEqual([])
  })
})
