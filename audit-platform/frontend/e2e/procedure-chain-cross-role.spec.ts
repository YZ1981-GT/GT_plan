/**
 * 程序链跨角色可重放脚本（spec procedure-chain-hardening-and-java-contracts R21）
 *
 * 在一个【测试】项目上按界面顺序重放：经理粗裁 → 再生成被跳过 → 审计员不能裁剪 / 委派 → 经理委派给审计员 →
 * 审计员只打得开委派给他的底稿、编辑锁按可见性放行（接口 + 真实浏览器）→ 经理恢复执行 → 再生成按回执分流。
 * 与 backend/tests/procedure_chain_e2e/test_cross_role_chain_pg.py 同一条链（那边在回滚事务里跑、不落库）。
 *
 * 环境变量（缺任一必填项整组跳过；项目名不含「【测试】」拒绝执行）：
 *   GT_E2E_CHAIN_PROJECT_ID                    【测试】项目 id（必填）
 *   GT_E2E_MANAGER_USER / GT_E2E_MANAGER_PASS  项目经理账号：团队分配为经理 / 合伙人（必填）
 *   GT_E2E_AUDITOR_USER / GT_E2E_AUDITOR_PASS  审计员账号：项目成员（必填）
 *   GT_E2E_AUDITOR_STAFF_ID                    审计员的人员档案 id，委派对象（必填）
 *   GT_E2E_DELEGATE_WP_CODE                    委派给审计员的底稿（默认 D2；须已生成、在审计员勾选的循环内）
 *   GT_E2E_HIDDEN_WP_CODE                      可选：审计员循环内、但没委派给他的底稿（验证打不开）
 *   GT_E2E_TRIM_CODE                           粗裁 / 恢复的程序编码（默认 H3；项目里须有这条程序）
 *   GT_E2E_API_BASE / GT_E2E_UI_BASE           默认 http://127.0.0.1:9980/api、http://127.0.0.1:3030
 *
 * 会改动这个【测试】项目：裁剪后恢复执行（中途失败也在收尾恢复）；委派保留；项目里还没有时会新建
 * 「粗裁编码」与「粗裁编码-1」两份底稿。可重复执行（第二次起委派计入「未变化」、生成计入「已存在」）。
 *
 * 跑法（不跑全局种子）：SKIP_E2E_SEED=1 npx playwright test e2e/procedure-chain-cross-role.spec.ts
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

const env = process.env
const API = (env.GT_E2E_API_BASE || 'http://127.0.0.1:9980/api').replace(/\/$/, '')
const UI = (env.GT_E2E_UI_BASE || 'http://127.0.0.1:3030').replace(/\/$/, '')
const PID = env.GT_E2E_CHAIN_PROJECT_ID || ''
const MANAGER = { username: env.GT_E2E_MANAGER_USER || '', password: env.GT_E2E_MANAGER_PASS || '' }
const AUDITOR = { username: env.GT_E2E_AUDITOR_USER || '', password: env.GT_E2E_AUDITOR_PASS || '' }
const AUDITOR_STAFF_ID = env.GT_E2E_AUDITOR_STAFF_ID || ''
const DELEGATE_CODE = env.GT_E2E_DELEGATE_WP_CODE || 'D2'
const HIDDEN_CODE = env.GT_E2E_HIDDEN_WP_CODE || ''
const TRIM_CODE = env.GT_E2E_TRIM_CODE || 'H3'
const SUB_CODE = `${TRIM_CODE}-1`
const NOT_FOUND = '资源不存在或不可访问'

const REQUIRED: Record<string, string> = {
  GT_E2E_CHAIN_PROJECT_ID: PID,
  GT_E2E_MANAGER_USER: MANAGER.username,
  GT_E2E_MANAGER_PASS: MANAGER.password,
  GT_E2E_AUDITOR_USER: AUDITOR.username,
  GT_E2E_AUDITOR_PASS: AUDITOR.password,
  GT_E2E_AUDITOR_STAFF_ID: AUDITOR_STAFF_ID,
}
const MISSING = Object.entries(REQUIRED).filter(([, v]) => !v).map(([k]) => k)

type Json = Record<string, any>
interface Reply { status: number; body: unknown; data: Json }
interface Paper { wp_index_id: string; wp_id: string | null; wp_code: string; audit_cycle: string }

/** 后端响应包装为 { code, message, data }；错误详情在 message */
function unwrap(body: unknown): Json {
  const b = body as Json | null
  return b && typeof b === 'object' && 'code' in b && 'data' in b ? (b.data as Json) : (b ?? {})
}

function detailOf(r: Reply): unknown {
  const b = r.body as Json | null
  return b && typeof b === 'object' ? (b.detail ?? b.message) : b
}

const rid = (tag: string) => `e2e-chain-${tag}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

class Api {
  constructor(private readonly ctx: APIRequestContext, private readonly token: string) {}

  async call(method: 'GET' | 'POST' | 'DELETE', path: string, data?: unknown,
             params?: Record<string, string | number>): Promise<Reply> {
    const r = await this.ctx.fetch(`${API}${path}`, {
      method, data, params, headers: { Authorization: `Bearer ${this.token}` },
    })
    const text = await r.text()
    let body: unknown = text
    try { body = JSON.parse(text) } catch { /* 非 JSON 原样保留 */ }
    return { status: r.status(), body, data: unwrap(body) }
  }
}

async function login(ctx: APIRequestContext, who: { username: string; password: string }): Promise<Api> {
  const r = await ctx.post(`${API}/auth/login`, { data: who })
  expect(r.status(), `登录 ${who.username}`).toBe(200)
  const body = unwrap(await r.json())
  expect(body.access_token, `登录 ${who.username} 没拿到令牌`).toBeTruthy()
  return new Api(ctx, body.access_token as string)
}

/** 按编码找底稿（经理看全部循环；列表按循环过滤、分页取） */
async function findPaper(api: Api, code: string): Promise<Paper | null> {
  for (let page = 1; page <= 20; page += 1) {
    const r = await api.call('GET', `/projects/${PID}/working-papers`, undefined,
                             { audit_cycle: code[0], page, page_size: 100 })
    expect(r.status, JSON.stringify(r.body)).toBe(200)
    const hit = (r.data.items as Paper[]).find((i) => i.wp_code === code)
    if (hit) return hit
    if (page * 100 >= Number(r.data.total ?? 0)) break
  }
  return null
}

function trimEntry(status: 'not_applicable' | 'execute') {
  return {
    kind: 'scope', cycle: TRIM_CODE[0], wp_index_code: TRIM_CODE, target_status: status,
    ...(status === 'not_applicable' ? { skip_reason: '【测试】程序链重放：本期不适用' } : {}),
  }
}

/** 粗裁 / 恢复执行：预览 → 应用（有编制内容的底稿照样确认移入，收尾会恢复） */
async function trim(api: Api, status: 'not_applicable' | 'execute'): Promise<Json> {
  const entries = [trimEntry(status)]
  const pv = await api.call('POST', `/projects/${PID}/procedure-trim/preview`, { entries })
  expect(pv.status, JSON.stringify(pv.body)).toBe(200)
  expect(pv.data.summary.conflict, `项目里要有程序 ${TRIM_CODE}：${JSON.stringify(pv.data.conflicts)}`).toBe(0)
  const ap = await api.call('POST', `/projects/${PID}/procedure-trim/apply`, {
    entries, preview_id: pv.data.preview_id, request_id: rid(status), confirm_substantive_recycle: true,
  })
  expect(ap.status, JSON.stringify(ap.body)).toBe(200)
  return ap.data
}

async function generate(api: Api, codes: string[]): Promise<Json> {
  const r = await api.call('POST', `/projects/${PID}/working-papers/generate-from-codes`, { wp_codes: codes })
  expect(r.status, JSON.stringify(r.body)).toBe(200)
  expect(r.data.failures, '生成不应有失败项').toEqual([])
  return r.data
}

/** 真实浏览器以当前登录身份打开底稿编辑页，收集该底稿详情 / 渲染配置请求的状态码 */
async function openEditor(page: Page, wpId: string): Promise<number[]> {
  const statuses: number[] = []
  const watch = (resp: { url(): string; status(): number }) => {
    const url = resp.url()
    if (url.includes(wpId) && (url.includes('/render-config') || /\/working-papers\/[0-9a-f-]{36}(\?|$)/.test(url))) {
      statuses.push(resp.status())
    }
  }
  page.on('response', watch)
  await page.goto(`${UI}/projects/${PID}/workpapers/${wpId}/edit`)
  await page.waitForResponse((r) => r.url().includes(wpId), { timeout: 30000 }).catch(() => null)
  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => undefined)
  page.off('response', watch)
  return statuses
}

async function uiLogin(page: Page, who: { username: string; password: string }) {
  await page.goto(`${UI}/login`)
  await page.fill('input[placeholder*="用户名"]', who.username)
  await page.fill('input[type="password"]', who.password)
  await page.click('button:has-text("登录")')
  await page.waitForFunction(() => !window.location.pathname.includes('/login'), undefined, { timeout: 20000 })
}

test.describe.serial('程序链跨角色重放（【测试】项目）', () => {
  test.skip(MISSING.length > 0, `未配置环境变量：${MISSING.join('、')}`)

  let ctx: APIRequestContext
  let manager: Api
  let auditor: Api
  let delegated: Paper
  let hidden: Paper | null = null
  let trimmed = false

  test.beforeAll(async ({ playwright }) => {
    ctx = await playwright.request.newContext()
    manager = await login(ctx, MANAGER)
    auditor = await login(ctx, AUDITOR)
    const project = await manager.call('GET', `/projects/${PID}`)
    expect(project.status, JSON.stringify(project.body)).toBe(200)
    if (!String(project.data.name ?? '').includes('【测试】')) {
      throw new Error(`项目「${project.data.name}」不是【测试】项目，拒绝重放（会裁剪、委派、生成底稿）`)
    }
    const found = await findPaper(manager, DELEGATE_CODE)
    if (!found?.wp_id) throw new Error(`项目里没有已生成的底稿 ${DELEGATE_CODE}（GT_E2E_DELEGATE_WP_CODE）`)
    delegated = found
    hidden = HIDDEN_CODE ? await findPaper(manager, HIDDEN_CODE) : null
    if (HIDDEN_CODE && !hidden?.wp_id) throw new Error(`项目里没有已生成的底稿 ${HIDDEN_CODE}（GT_E2E_HIDDEN_WP_CODE）`)
  })

  test.afterAll(async () => {
    try {
      if (trimmed) await trim(manager, 'execute') // 中途失败也把粗裁恢复回去
    } finally {
      await ctx?.dispose()
    }
  })

  test('经理粗裁：再生成按「已裁」跳过（含子表）', async () => {
    const res = await trim(manager, 'not_applicable')
    trimmed = true
    expect(res.restored_codes).toEqual([])
    const again = await generate(manager, [TRIM_CODE, SUB_CODE])
    expect(again.skipped_trimmed_codes).toEqual([TRIM_CODE, SUB_CODE])
    expect(again.created_codes).toEqual([])
  })

  test('审计员不能裁剪、不能委派', async () => {
    const t = await auditor.call('POST', `/projects/${PID}/procedure-trim/preview`, { entries: [trimEntry('execute')] })
    expect(t.status).toBe(403)
    const d = await auditor.call('POST', `/projects/${PID}/procedure-delegations/preview`, {
      selector: { kind: 'workpaper', wp_index_ids: [delegated.wp_index_id] }, assignee_staff_id: AUDITOR_STAFF_ID,
    })
    expect(d.status).toBe(403)
  })

  test('经理把底稿委派给审计员', async () => {
    const body = { selector: { kind: 'workpaper', wp_index_ids: [delegated.wp_index_id] }, assignee_staff_id: AUDITOR_STAFF_ID }
    const pv = await manager.call('POST', `/projects/${PID}/procedure-delegations/preview`, body)
    expect(pv.status, JSON.stringify(pv.body)).toBe(200)
    expect(pv.data.preparation_ready, String(pv.data.hint ?? '')).toBe(true)
    expect(pv.data.scope_gaps ?? [], '审计员的可见范围要包含该底稿的循环（团队分配里勾选）').toEqual([])
    const s = pv.data.summary
    expect(s.would_assign + s.would_reassign + s.unchanged, '该底稿要有可委派的程序行').toBeGreaterThan(0)
    const ap = await manager.call('POST', `/projects/${PID}/procedure-delegations/apply`,
                                  { ...body, preview_id: pv.data.preview_id, request_id: rid('delegate') })
    expect(ap.status, JSON.stringify(ap.body)).toBe(200)
    expect(ap.data.applied + ap.data.unchanged).toBeGreaterThan(0)
  })

  test('审计员只打得开委派给他的底稿；编辑锁按可见性放行', async () => {
    const ok = await auditor.call('GET', `/projects/${PID}/working-papers/${delegated.wp_id}`)
    expect(ok.status, JSON.stringify(ok.body)).toBe(200)
    const lock = `/editing-locks/workpaper/${delegated.wp_id}`
    const got = await auditor.call('POST', lock)
    expect(got.status, `编辑锁：${JSON.stringify(got.body)}`).toBe(200)
    expect((await auditor.call('DELETE', lock)).status).toBe(200)
    if (hidden) {
      const no = await auditor.call('GET', `/projects/${PID}/working-papers/${hidden.wp_id}`)
      expect([no.status, detailOf(no)]).toEqual([404, NOT_FOUND])
      expect((await auditor.call('POST', `/editing-locks/workpaper/${hidden.wp_id}`)).status).toBe(404)
    }
  })

  test('审计员在浏览器里打开底稿：委派的能打开，没委派的 404', async ({ page }) => {
    await uiLogin(page, AUDITOR)
    const okStatuses = await openEditor(page, delegated.wp_id as string)
    expect(okStatuses.length, '编辑页没有请求该底稿').toBeGreaterThan(0)
    expect(okStatuses.filter((s) => s === 404 || s === 403)).toEqual([])
    if (hidden) {
      const noStatuses = await openEditor(page, hidden.wp_id as string)
      expect(noStatuses).toContain(404)
      expect(noStatuses).not.toContain(200)
    }
  })

  test('经理恢复执行：再生成按已存在 / 新建分流', async () => {
    const res = await trim(manager, 'execute')
    trimmed = false
    expect(res.recycled_codes).toEqual([])
    const final = await generate(manager, [TRIM_CODE, SUB_CODE])
    expect(final.skipped_trimmed_codes).toEqual([])
    expect(final.in_recycle_codes).toEqual([])
    expect([...final.created_codes, ...final.existing_codes].sort()).toEqual([TRIM_CODE, SUB_CODE].sort())
  })
})
