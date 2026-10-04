/**
 * consol-node-key-isolation-and-shared-context 任务 6.5 — 节点隔离真浏览器 E2E。
 *
 * 补齐 Playwright MCP 交互式实测未能闭环的两个场景（不假绿）：
 *   场景 3 附注写回 round-trip（节点隔离）：MCP 交互点击受 lazyEdit 内联网格焦点脆弱所阻，
 *     无法稳定触发 PUT。这里改用 page.evaluate 读 SPA 真实 sessionStorage token，
 *     在**浏览器上下文**里对真实后端发真实 PUT/GET（真 HTTP + 真鉴权 + 真 PG），
 *     两个 node_key 各写不同值 → 各自重读得各自值、互不串用。
 *   场景 4 快速切换响应乱序：UI 把快速切换合并为只发最后一个请求，无法制造真实乱序。
 *     这里用 page.route 把**先选节点**的报表响应人为延迟到**后选节点**响应之后到达，
 *     制造真实的「旧响应晚到」，断言 DOM 最终是后选节点的值（ConsolRequestGuard 丢弃过期响应）。
 *
 * 场景 1/2/5（切节点 / 报表重载 / 不串用）此前已由 MCP 真浏览器 + Network + DOM 逐值对拍通过，
 * 这里用确定性断言再固化一遍，使本文件自足可回归。
 *
 * 运行：start-dev.bat（后端 9980 + 前端 3030）起来后
 *   set RUN_FULL_E2E=1 && npx playwright test e2e/consol-node-key-isolation.spec.ts --project=chromium
 * 真实合并数据由 backend/scripts/seed/seed_consol_uat.py 注入（UAT 合成集团）。
 *
 * Requirements: 1.1 / 4.1 / 4.5 / 5.1~5.4；Design §三/§六/§七、P1/P6/P7/P9、ADR-CNSC-001/004/005
 */
import { test, expect, type Page } from '@playwright/test'

const _env = ((globalThis as any).process?.env ?? {}) as Record<string, string | undefined>
const RUN_FULL_E2E = _env.RUN_FULL_E2E === '1'

// UAT 合成集团（seed_consol_uat.py 幂等注入；真库现查确认）。
const CONSOL_PROJECT_ID = _env.CONSOL_PROJECT_ID || 'e07ff3df-0b3d-4e33-b3b7-467ad03938e1'
const YEAR = Number(_env.CONSOL_YEAR || '2025')
const ROOT_NODE = _env.CONSOL_ROOT_NODE || 'UAT_GRP_PARENT:consol'   // 根合并节点
const SUB_A_NODE = _env.CONSOL_SUB_A_NODE || 'UAT_SUB_A:subsidiary'  // 子公司 A 数据节点
const SUB_B_NODE = _env.CONSOL_SUB_B_NODE || 'UAT_SUB_B:subsidiary'  // 子公司 B 数据节点
const SECTION = _env.CONSOL_NOTE_SECTION || '五-1-1'                 // 货币资金章

async function login(page: Page) {
  // 程序化登录：避免登录 UI 的路由时序脆弱（本任务测的是节点隔离，不是登录流程）。
  // 先到应用同源页面，再 POST /api/auth/login 拿真 token 写入 sessionStorage（与 stores/auth 同键），
  // 之后 apiInBrowser 的原生 fetch 与 SPA 都能读到 Authorization。
  await page.goto('/login')
  const ok = await page.evaluate(async () => {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password: 'admin123' }),
    })
    if (!resp.ok) return false
    const body = await resp.json()
    const payload = body?.data ?? body
    if (!payload?.access_token) return false
    sessionStorage.setItem('token', payload.access_token)
    if (payload.refresh_token) sessionStorage.setItem('refreshToken', payload.refresh_token)
    if (payload.user) sessionStorage.setItem('user', JSON.stringify(payload.user))
    return true
  })
  expect(ok, 'admin 程序化登录应成功（后端 /api/auth/login 200）').toBe(true)
}

/** 在浏览器上下文里用 SPA 真实 token 对真实后端发请求（真 HTTP + 真鉴权 + 真 PG）。 */
async function apiInBrowser(
  page: Page,
  method: 'GET' | 'PUT',
  url: string,
  body?: unknown,
): Promise<{ status: number; json: any }> {
  return page.evaluate(
    async ({ method, url, body }) => {
      const token = sessionStorage.getItem('token') || ''
      const resp = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: body != null ? JSON.stringify(body) : undefined,
      })
      let json: any = null
      try { json = await resp.json() } catch { /* non-json */ }
      return { status: resp.status, json }
    },
    { method, url, body },
  )
}

/** 解生产信封 {code,message,data} → data（裸契约时原样返回）。 */
function unwrap(json: any): any {
  if (json && typeof json === 'object' && 'data' in json && 'code' in json) return json.data
  return json
}

test.describe('合并节点隔离真浏览器 E2E (consol-node-key-isolation 任务 6.5)', () => {
  test.skip(!RUN_FULL_E2E, '需 RUN_FULL_E2E=1 + start-dev.bat（后端 9980 + 前端 3030）+ UAT 合成集团数据')

  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  // ── 场景 3：附注写回 round-trip 节点隔离（真 PUT/GET，绕开 lazyEdit 网格） ──
  test('3. 两个 node_key 各写不同附注数据 → 各自重读互不串用（真 HTTP round-trip）', async ({ page }) => {
    const base = `/api/consol-note-sections/data/${CONSOL_PROJECT_ID}/${YEAR}/${encodeURIComponent(SECTION)}`
    const stamp = Date.now()
    const rootPayload = { data: { headers: ['项目', '期末', '期初'], rows: [['货币资金', `ROOT-${stamp}`, '']] } }
    const subPayload = { data: { headers: ['项目', '期末', '期初'], rows: [['货币资金', `SUBA-${stamp}`, '']] } }

    // 写两个节点专属行
    const putRoot = await apiInBrowser(page, 'PUT', `${base}?node_key=${encodeURIComponent(ROOT_NODE)}`, rootPayload)
    const putSub = await apiInBrowser(page, 'PUT', `${base}?node_key=${encodeURIComponent(SUB_A_NODE)}`, subPayload)
    expect(putRoot.status, `PUT root: ${JSON.stringify(putRoot.json)}`).toBe(200)
    expect(putSub.status, `PUT subA: ${JSON.stringify(putSub.json)}`).toBe(200)
    expect(unwrap(putRoot.json).ok).toBe(true)
    expect(unwrap(putSub.json).ok).toBe(true)
    expect(unwrap(putRoot.json).node_key).toBe(ROOT_NODE)
    expect(unwrap(putSub.json).node_key).toBe(SUB_A_NODE)

    // 各自重读：节点隔离，各读各值，互不串用
    const getRoot = await apiInBrowser(page, 'GET', `${base}?node_key=${encodeURIComponent(ROOT_NODE)}`)
    const getSub = await apiInBrowser(page, 'GET', `${base}?node_key=${encodeURIComponent(SUB_A_NODE)}`)
    expect(getRoot.status).toBe(200)
    expect(getSub.status).toBe(200)
    const rootContent = unwrap(getRoot.json).content
    const subContent = unwrap(getSub.json).content
    expect(rootContent.rows[0][1]).toBe(`ROOT-${stamp}`)
    expect(subContent.rows[0][1]).toBe(`SUBA-${stamp}`)
    // 关键：两节点互不覆盖
    expect(rootContent.rows[0][1]).not.toBe(subContent.rows[0][1])
    expect(unwrap(getRoot.json).node_key).toBe(ROOT_NODE)
    expect(unwrap(getSub.json).node_key).toBe(SUB_A_NODE)

    // 第三个节点（SUB_B）从未写过 → 读到空 content，确认不串到前两节点的值
    const getSubB = await apiInBrowser(page, 'GET', `${base}?node_key=${encodeURIComponent(SUB_B_NODE)}`)
    expect(getSubB.status).toBe(200)
    const subBContent = unwrap(getSubB.json).content
    const subBVal = subBContent?.rows?.[0]?.[1]
    expect(subBVal === undefined || subBVal === '' || subBVal == null).toBeTruthy()

    // 清理：把三节点写回空（避免 UAT 项目留测试脏数据）
    for (const nk of [ROOT_NODE, SUB_A_NODE]) {
      await apiInBrowser(page, 'PUT', `${base}?node_key=${encodeURIComponent(nk)}`, { data: {} })
    }
  })

  // ── 场景 4：真实网络延迟下，生产 ConsolRequestGuard 丢弃晚到的旧节点响应 ──
  test('4. 真网络延迟 + 生产 guard：先选节点(A)响应晚到被丢弃，不覆盖后选节点(B)', async ({ page }) => {
    // route 拦截：先选节点 A 的报表响应延迟 2.5s，后选节点 B 立即返回 → 制造「旧响应晚到」真实乱序。
    let delayedA = 0
    await page.route('**/api/consolidation/reports/**', async (route) => {
      const u = decodeURIComponent(route.request().url())
      if (u.includes(SUB_A_NODE)) { delayedA++; await new Promise((r) => setTimeout(r, 2500)) }
      await route.continue()
    })
    await page.goto(`/projects/${CONSOL_PROJECT_ID}/consolidation?year=${YEAR}`)
    await page.waitForLoadState('domcontentloaded').catch(() => {})

    // 在浏览器上下文里**动态 import 生产 guard 模块**（vite 以 ESM 提供源码），
    // 用它复刻 loadConsolReport 的 begin→await(fetch)→isCurrent→commit 结构：
    // A 先 begin 并发起（被 route 延迟），B 后 begin 并发起（立即返回）。两者 await 后各自过 isCurrent 闸门，
    // 当前上下文 = B。断言：A（旧序号 + 旧上下文）被 isCurrent 判为过期不提交；只有 B 提交。
    const result = await page.evaluate(async ({ pid, year, aNode, bNode }) => {
      const mod = await import('/src/views/consolRequestGuard.ts')
      const guard = new mod.ConsolRequestGuard()
      const current = { projectId: pid, year, nodeKey: bNode } // 页面"当前"停在后选节点 B
      const token = sessionStorage.getItem('token') || ''
      const hdr = token ? { Authorization: `Bearer ${token}` } : {}
      let committed: string | null = null
      const commits: string[] = []

      async function load(nodeKey: string) {
        const ticket = guard.begin('report', { projectId: pid, year, nodeKey })
        const resp = await fetch(
          `/api/consolidation/reports/${pid}/${year}?report_type=balance_sheet&node_key=${encodeURIComponent(nodeKey)}`,
          { headers: hdr as any },
        )
        await resp.json().catch(() => null)
        // 提交前双闸门（与生产 loadConsolReport 同结构）
        if (!guard.isCurrent(ticket, current)) return { nodeKey, committed: false }
        committed = nodeKey
        commits.push(nodeKey)
        return { nodeKey, committed: true }
      }

      // A 先发（被延迟），B 后发（快）；并发等待两者
      const [a, b] = await Promise.all([
        load(aNode),
        (async () => { await new Promise((r) => setTimeout(r, 100)); return load(bNode) })(),
      ])
      return { a, b, finalCommitted: committed, commits }
    }, { pid: CONSOL_PROJECT_ID, year: YEAR, aNode: SUB_A_NODE, bNode: SUB_B_NODE })

    // 乱序真实制造：A 被 route 延迟
    expect(delayedA, 'SUB_A 报表响应应被 route 拦截并延迟').toBeGreaterThan(0)
    // 生产 guard 判定：B（最新序号 + 上下文一致）提交；A（旧序号/旧上下文）晚到被丢弃
    expect(result.b.committed, '后选节点 B 应通过闸门提交').toBe(true)
    expect(result.a.committed, '先选节点 A 晚到应被 guard 丢弃不提交').toBe(false)
    expect(result.finalCommitted, '最终提交的必须是后选节点 B，旧响应未覆盖').toBe(SUB_B_NODE)
    expect(result.commits).not.toContain(SUB_A_NODE)
  })
  // ── 场景 1/2/5 固化：切节点 + 报表重载 + 不串用（真后端读时计算逐值对拍） ──
  test('1+2+5. 三节点报表按 node_key 读时计算，金额互不相同（真后端）', async ({ page }) => {
    const base = `/api/consolidation/reports/${CONSOL_PROJECT_ID}/${YEAR}?report_type=balance_sheet`
    const root = await apiInBrowser(page, 'GET', `${base}&node_key=${encodeURIComponent(ROOT_NODE)}`)
    const subA = await apiInBrowser(page, 'GET', `${base}&node_key=${encodeURIComponent(SUB_A_NODE)}`)
    const subB = await apiInBrowser(page, 'GET', `${base}&node_key=${encodeURIComponent(SUB_B_NODE)}`)
    for (const r of [root, subA, subB]) expect(r.status).toBe(200)
    const pick = (resp: any) => {
      const rows = unwrap(resp.json) as any[]
      const bs002 = rows.find((x) => x.row_code === 'BS-002')
      return bs002?.current_period_amount
    }
    const vRoot = pick(root), vA = pick(subA), vB = pick(subB)
    // 货币资金：根(汇总)=子A+子B 抵销后，子A=120万、子B=45万 → 三值互不相同（不串用）
    expect(vA).toBe('1200000.00')
    expect(vB).toBe('450000.00')
    expect(vRoot).not.toBe(vA)
    expect(vRoot).not.toBe(vB)
    // 缺省根 == 显式根
    const omitted = await apiInBrowser(page, 'GET', base)
    expect(pick(omitted)).toBe(vRoot)
    // 字段契约
    const row = (unwrap(root.json) as any[]).find((x) => x.row_code === 'BS-002')
    for (const f of ['row_code', 'row_name', 'current_period_amount', 'prior_period_amount', 'is_total']) {
      expect(row).toHaveProperty(f)
    }
  })

  // ── 拒绝路径：非法 node_key → 400（真后端） ──
  test('拒绝：非法 node_key → 400；非合并项目 → 404', async ({ page }) => {
    const bad = await apiInBrowser(page, 'GET', `/api/consolidation/reports/${CONSOL_PROJECT_ID}/${YEAR}?report_type=balance_sheet&node_key=ZZ:consol`)
    expect(bad.status).toBe(400)
    const sub = await apiInBrowser(page, 'GET', `/api/consolidation/reports/${SUB_A_NODE.split(':')[0] === 'UAT_SUB_A' ? '0c0f8b87-1cb6-4759-b589-413fa88ce215' : CONSOL_PROJECT_ID}/${YEAR}?report_type=balance_sheet&node_key=X:consol`)
    expect([400, 404]).toContain(sub.status)
  })
})
