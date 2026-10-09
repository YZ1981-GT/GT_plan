/**
 * G2 应收利息 L2 OO→HTML 受管 sheet 验收（canary：明细表G2-2）。
 *
 * spec: `g-cycle-sync-foundation-and-first-canary` · Task 16
 * 跑法：`npx playwright test e2e/g2-l2-oo-to-html-all.spec.ts --workers=1`
 *
 * ═══ 🔴 P15：先断言载荷非空，再谈三谓词 ═══
 *
 * 裁决 GF-H2 定了**不交付 seed 脚本** —— 真库 `G2-2-detail-rows` 已有 475 B / 1 行真实载荷
 * （fixture `seed_policy.evidence` 记了 SQL 与 wp_id）。但「不 seed」带一个必须堵住的洞：
 * **一张空表往返也会让三谓词全部成立** —— 出去 0 行、回来 0 行、镜像一致，于是
 * `store_mirrored` 为真而什么都没验证。所以本文件第一个用例是**前置断言**：
 * 参与 roundtrip 的行数 > 0 且来自真库，它**不因 adapter 未注册而跳过**。
 *
 * ═══ 为什么 canary 用例当前是 pending_adapter ═══
 *
 * G2 entry 的 manifest capability 仍是 `single_onlyoffice`（BP-1~BP-3 是平台级欠账，本
 * spec 如实登记为 `upstream_gap` 而不是改 overlay 伪造 bidirectional）。
 * `attach_pilot_adapters` 走 capability 门返回空 ⇒ adapter 未注册 ⇒ OO 侧三谓词跑不了。
 * 供给就绪后把 fixture 的 `result_enum` 改成 `pass` 并补全下面 TODO 的五步。
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { test, expect, type APIRequestContext } from '@playwright/test'

// 同一 wp 的 OO room / forcesave / content_revision 是串行资源，禁并行。
test.describe.configure({ mode: 'serial' })

/**
 * 🔴 fixture 走 `readFileSync` 而**不是** `import cases from './fixtures/*.json'`。
 *
 * 后者在 Playwright 的 Node ESM 加载器下直接抛
 * `TypeError: Module "…g2-l2-cases.json" needs an import attribute of "type: json"`
 * ⇒ 整个 spec 文件加载失败、`--list` 报 `Total: 0 tests in 0 files`。
 * 本轮实测 `f1-l2-oo-to-html-all.spec.ts` 正是这个形态，**一条用例都跑不起来**（既存缺陷，
 * 已在本 spec 的收口证据里登记）。D4 lane 用的就是 `readFileSync`，照它。
 */
interface G2L2Fixture {
  readonly preconditions: {
    readonly store_item_id: string
    readonly min_row_count: number
    readonly must_assert_before_skip: boolean
  }
  readonly seed_policy: {
    readonly evidence: {
      readonly wp_id: string
      readonly project_id: string
      readonly wp_code: string
      readonly wp_name: string
      readonly row_count: number
      readonly remark_bytes: number
    }
  }
  readonly cases: ReadonlyArray<{
    readonly id: string
    readonly description: string
    readonly sheet_name: string
    readonly edit_cell: string
    readonly edit_value: string
    readonly expect_formula_columns: readonly string[]
    readonly result_enum: string
    readonly pending_reason?: string
  }>
}

const cases: G2L2Fixture = JSON.parse(
  readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), 'fixtures/g2-l2-cases.json'),
    'utf-8',
  ),
)

const PRE = cases.preconditions
const EVIDENCE = cases.seed_policy.evidence

/** 与既有 e2e 同款：admin/admin123 换 access_token（相对路径走 Vite 代理到后端）。 */
async function apiLogin(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  expect(resp.ok(), `登录应成功，实际 HTTP ${resp.status()}`).toBeTruthy()
  const body = await resp.json()
  const token = String(body?.data?.access_token ?? body?.access_token ?? '')
  expect(token, '登录响应里没有 access_token').toBeTruthy()
  return token
}

test.describe('G2 L2 OO→HTML（canary 明细表G2-2）', () => {
  test('P15 前置：参与 roundtrip 的行数 > 0 且来自真库（不因 adapter 缺位而跳过）', async ({
    request,
  }) => {
    const token = await apiLogin(request)
    const res = await request.get(
      `/api/workpapers/${EVIDENCE.wp_id}/checklist-responses`,
      { headers: { Authorization: `Bearer ${token}` }, failOnStatusCode: false },
    )
    expect(
      res.ok(),
      `读底稿 ${EVIDENCE.wp_id}（${EVIDENCE.wp_code} ${EVIDENCE.wp_name}）的 checklist `
        + `载荷失败：HTTP ${res.status()}`,
    ).toBe(true)

    const body = await res.json()
    const rows: Array<Record<string, unknown>> = Array.isArray(body?.data)
      ? body.data
      : Array.isArray(body)
        ? body
        : []
    const hit = rows.find((r) => r?.item_id === PRE.store_item_id)
    expect(
      hit,
      `真库没有 ${PRE.store_item_id} 载荷 ⇒ 空表往返会把三谓词全判成真（P15 要堵的正是这个）。`
        + '不要用 seed 脚本绕过：裁决 GF-H2 明确不 seed，载荷缺失说明取错了 wp_id。',
    ).toBeTruthy()

    const payload = String((hit as Record<string, unknown>).remark ?? '')
    let parsed: unknown
    try {
      parsed = JSON.parse(payload)
    } catch (err) {
      throw new Error(
        `${PRE.store_item_id} 的 remark 不是合法 JSON（${String(err)}）：`
          + payload.slice(0, 160),
      )
    }
    expect(Array.isArray(parsed), `${PRE.store_item_id} 载荷不是行数组`).toBe(true)
    expect(
      (parsed as unknown[]).length,
      `参与 roundtrip 的行数必须 ≥ ${PRE.min_row_count}（真库现值应为 ${EVIDENCE.row_count}）`,
    ).toBeGreaterThanOrEqual(PRE.min_row_count)
  })

  for (const c of cases.cases) {
    test(`${c.id}: ${c.description}`, async ({ page }) => {
      test.skip(c.result_enum === 'pending_adapter', `⏭️ ${c.id}: ${c.pending_reason}`)
      // 供给就绪后补全五步（照 d4-l2-oo-to-html-all.spec.ts）：
      // 1. 打开 wp ${EVIDENCE.wp_id} 的 ${c.sheet_name}
      // 2. 切「在线编辑」→ 等 data-testid=wp-sync-host-editor
      // 3. 写 ${c.edit_cell} = ${c.edit_value} → Enter
      // 4. 等 forcesave callback 落地（durable ack）
      // 5. 三谓词：confirm 成功 / forcesave 有 durable ack / store 镜像一致
      //    并核公式列 ${c.expect_formula_columns.join('/')} 由模板算出、未被投影覆盖
      expect(page).toBeTruthy()
    })
  }
})
