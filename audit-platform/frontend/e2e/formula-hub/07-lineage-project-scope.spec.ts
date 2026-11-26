/**
 * 浏览器检查 ⑦ — 溯源与附件只见本项目
 *
 * `GET /api/projects/{pid}/lineage`（统一溯源）：各子源都要跑通（`partial` 为假、没有子源错误），当前对象就是查询的底稿；
 * 附件只列本项目的。种子不带附件（seed_formula_e2e.py 只建账号、项目、底稿）⇒ 用例经真实上传 / 关联接口自建一份，
 * 断言它出现在本项目溯源、不出现在另一个项目同编码底稿的溯源里（原先「种子没有附件」时显式跳过，从未真跑）。
 * 原用例打不存在的 `/attachment-lineage`，404 即通过；界面部分打开的是不存在的路由。
 */
import { test, expect } from '@playwright/test'
import { BACKEND, api, apiToken, consolProjectId, requireIsolatedDb, runTag, seedYear, standaloneProjectId } from './helpers'
import { loadManifest } from './manifest'

const standaloneWpId = (code: string) => {
  const id = loadManifest().standalone.wp_ids[code]
  if (!id) throw new Error(`种子清单里单体项目没有 ${code} 底稿`)
  return id
}

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
    // 种子不带附件：本用例经真实接口自建一份——上传到单体项目、整稿关联到它的 D2-1 底稿。
    // 两个项目都有 D2-1，溯源按 wp_code 解析底稿，正好检验附件子源是否按项目隔离。
    await requireIsolatedDb(request, token)
    const standalone = standaloneProjectId()
    const marker = `【E2E】溯源附件-${runTag()}.txt`
    const uploaded = await request.fetch(`${BACKEND}/api/projects/${standalone}/attachments/upload`, {
      method: 'POST', timeout: 60_000,
      headers: { Authorization: `Bearer ${token}` },
      multipart: {
        file: { name: marker, mimeType: 'text/plain', buffer: Buffer.from('E2E lineage attachment\n', 'utf-8') },
        attachment_type: 'general',
      },
    })
    expect(uploaded.status(), await uploaded.text()).toBe(200)
    const attachmentId = ((await uploaded.json())?.data ?? {}).id as string
    expect(attachmentId, '上传回执缺少附件 id').toBeTruthy()
    const linked = await api(request, token, 'POST', `/api/attachments/${attachmentId}/associate`, {
      data: { wp_id: standaloneWpId('D2-1'), association_type: 'evidence' },
    })
    expect(linked.status, JSON.stringify(linked.error)).toBe(200)

    const lineageOf = (pid: string) => api(request, token, 'GET', `/api/projects/${pid}/lineage`, {
      params: { object_type: 'wp_cell', object_id: 'D2-1', year: seedYear() },
    })
    const a = await lineageOf(standalone)
    expect(a.status, JSON.stringify(a.error)).toBe(200)
    const ids = (rows: any[]) => (rows || []).map((x) => x.attachment_id)
    expect(ids(a.data.attachments), '单体项目自己的溯源里看不到刚关联的附件').toContain(attachmentId)

    const b = await lineageOf(consolProjectId())
    expect(b.status, JSON.stringify(b.error)).toBe(200)
    expect(ids(b.data.attachments), '合并项目看到了单体项目的附件').not.toContain(attachmentId)
  })
})
