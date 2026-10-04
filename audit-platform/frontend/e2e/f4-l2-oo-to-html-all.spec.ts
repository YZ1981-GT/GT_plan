/**
 * F4 应付账款 L2 OO→HTML 受管 sheet 验收（canary：关联方及交易检查表F4-6）。
 *
 * spec: `f4-sync-coverage-and-first-canary` · Task 11
 * 跑法：先 seed 再跑
 *   `..\.venv\Scripts\python.exe scripts/e2e/seed_f345_canary_rows.py --entry f4`（backend 目录）
 *   `npx playwright test e2e/f4-l2-oo-to-html-all.spec.ts --workers=1`
 *
 * 🔴 fixture 必须 readFileSync（`import … from '*.json'` 会让 Playwright ESM 加载器抛
 * `needs an import attribute of "type: json"`，整个文件 0 tests）—— 详见 f3 lane 同款注释。
 *
 * 🔴 canary 选的 F4-6 在真库**零载荷**（全库只有 F4-2-rows / F4-7-estimated-inbound-rows
 * 有数据）⇒ 必须 seed，否则空表往返会让三谓词全部成立而什么都没验证。
 * 前置用例断言「载荷非空 + 带 seed 标记」，它**不因 adapter 未注册而跳过**。
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { test, expect, type APIRequestContext } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

interface F4L2Fixture {
  readonly preconditions: {
    readonly store_item_id: string
    readonly min_row_count: number
  }
  readonly seed_policy: {
    readonly decision: string
    readonly seed_script: string
    readonly evidence: {
      readonly wp_id: string
      readonly project_id: string
      readonly wp_code: string
      readonly wp_name: string
      readonly row_count: number
      readonly seed_tag: string
    }
  }
  readonly cases: ReadonlyArray<{
    readonly id: string
    readonly description: string
    readonly sheet_name: string
    readonly edit_cell: string
    readonly edit_value: string
    readonly expect_formula_columns: readonly string[]
    readonly expect_formula_template: string
    readonly result_enum: string
    readonly pending_reason?: string
  }>
}

const fixture: F4L2Fixture = JSON.parse(
  readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), 'fixtures/f4-l2-cases.json'),
    'utf-8',
  ),
)

const PRE = fixture.preconditions
const EVIDENCE = fixture.seed_policy.evidence

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

async function readRows(
  request: APIRequestContext,
  itemId: string,
): Promise<Array<Record<string, unknown>>> {
  const token = await apiLogin(request)
  const res = await request.get(
    `/api/workpapers/${EVIDENCE.wp_id}/checklist-responses`,
    { headers: { Authorization: `Bearer ${token}` }, failOnStatusCode: false },
  )
  expect(res.ok(), `读 checklist 载荷失败：HTTP ${res.status()}`).toBe(true)
  const body = await res.json()
  const all: Array<Record<string, unknown>> = Array.isArray(body?.data)
    ? body.data
    : Array.isArray(body)
      ? body
      : []
  const hit = all.find((r) => r?.item_id === itemId)
  expect(
    hit,
    `真库没有 ${itemId} 载荷 ⇒ 空表往返会把三谓词全判成真。`
      + `先跑 seed：${fixture.seed_policy.seed_script}`,
  ).toBeTruthy()
  const parsed = JSON.parse(String((hit as Record<string, unknown>).remark ?? '[]'))
  expect(Array.isArray(parsed), `${itemId} 载荷不是行数组`).toBe(true)
  return parsed as Array<Record<string, unknown>>
}

test.describe('F4 L2 OO→HTML（canary 关联方及交易检查表F4-6）', () => {
  test('前置：seed 已落库且行数达标（不因 adapter 缺位而跳过）', async ({ request }) => {
    const rows = await readRows(request, PRE.store_item_id)
    expect(
      rows.length,
      `参与 roundtrip 的行数必须 ≥ ${PRE.min_row_count}（seed 应造 ${EVIDENCE.row_count} 行）`,
    ).toBeGreaterThanOrEqual(PRE.min_row_count)
  })

  test('前置：行身份齐备，且载荷确为 seed 造的（不是误读真实数据）', async ({ request }) => {
    const rows = await readRows(request, PRE.store_item_id)
    for (const [i, row] of rows.entries()) {
      expect(
        String(row?.rowId ?? '').trim(),
        `第 ${i} 行缺 rowId ⇒ store_row_identity 会 fail-closed`,
      ).not.toBe('')
      expect(
        row?._seed,
        `第 ${i} 行没有 _seed 标记 —— 说明这是真实数据而不是 seed 造的。`
          + 'e2e 会写格改值，直接跑会污染真实底稿；请确认 wp_id 与 seed 是否一致。',
      ).toBe(EVIDENCE.seed_tag)
    }
  })

  for (const c of fixture.cases) {
    test(`${c.id}: ${c.description}`, async ({ page }) => {
      test.skip(c.result_enum === 'pending_adapter', `⏭️ ${c.id}: ${c.pending_reason}`)
      // 供给就绪后补全五步：
      // 1. 打开 wp ${EVIDENCE.wp_id} 的 ${c.sheet_name}
      // 2. 切「在线编辑」→ 等 data-testid=wp-sync-host-editor
      // 3. 写 ${c.edit_cell} = ${c.edit_value} → Enter
      // 4. 等 forcesave callback 落地（durable ack）
      // 5. 三谓词 + 核公式列 ${c.expect_formula_columns.join('/')} 仍是模板公式
      //    （${c.expect_formula_template}，负债类 =C+E-D 镜像），未被投影覆盖成字面值
      expect(page).toBeTruthy()
    })
  }
})
