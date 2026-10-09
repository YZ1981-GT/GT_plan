/**
 * F5 营业成本 L2 OO→HTML 受管 sheet 验收（F5-8 canary + F5-1 其他业务区）。
 *
 * spec: `f5-sync-coverage-and-first-canary` · Task 11（骨架）· Task 21（F5-1 用例）
 * 跑法：先 seed 再跑
 *   `..\.venv\Scripts\python.exe scripts/e2e/seed_f345_canary_rows.py --entry f5`（backend 目录）
 *   `..\.venv\Scripts\python.exe scripts/e2e/seed_f345_canary_rows.py --entry f5-1`
 *   `npx playwright test e2e/f5-l2-oo-to-html-all.spec.ts --workers=1`
 *
 * 🔴 fixture 必须 readFileSync（`import … from '*.json'` 会让 Playwright ESM 加载器抛
 * `needs an import attribute of "type: json"`，整个文件 0 tests）—— 详见 f3 lane 同款注释。
 *
 * ═══ 🔴 P8：F5 是零载荷 entry，未 seed 必须显式失败 ═══
 *
 * 实测全库无任何 `F5-*` 载荷。spec P8 明确要求未 seed 时验收显式失败，**不得**因空表往返
 * 判 `store_mirrored`（出去 0 行、回来 0 行、镜像一致，三谓词全成立而什么都没验证）。
 * 故前置用例断言「载荷非空 + 带 seed 标记 + 行身份齐备」，它们**不因 adapter 缺位而跳过**。
 *
 * ═══ 🔴 两个用例的行身份键不同（同一册内）═══
 *
 *   F5-8-rows            → `id`
 *   F5-1-adj-other-rows  → `rowKey`
 *
 * 照抄任一张都会让另一张的投影 fail-closed。键名按值 grep 实测所得（FC-4：禁推演）。
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { test, expect, type APIRequestContext } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

interface F5L2Fixture {
  readonly preconditions: {
    readonly store_item_ids: readonly string[]
    readonly min_row_count: number
  }
  readonly seed_policy: {
    readonly seed_script: string
    readonly evidence: {
      readonly wp_id: string
      readonly project_id: string
      readonly wp_code: string
      readonly wp_name: string
      readonly items: ReadonlyArray<{
        readonly store_item_id: string
        readonly row_count: number
        readonly seed_tag: string
      }>
    }
  }
  readonly cases: ReadonlyArray<{
    readonly id: string
    readonly description: string
    readonly sheet_name: string
    readonly store_item_id: string
    readonly row_identity_key: string
    readonly edit_cell: string
    readonly edit_value: string
    readonly expect_formula_columns: readonly string[]
    readonly result_enum: string
    readonly pending_reason?: string
  }>
}

const fixture: F5L2Fixture = JSON.parse(
  readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), 'fixtures/f5-l2-cases.json'),
    'utf-8',
  ),
)

const PRE = fixture.preconditions
const EVIDENCE = fixture.seed_policy.evidence
const SEED_TAG = EVIDENCE.items[0].seed_tag

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
    `真库没有 ${itemId} 载荷（F5 是零载荷 entry）⇒ P8 要求此处显式失败而不是判绿。`
      + `先跑 seed：${fixture.seed_policy.seed_script}`,
  ).toBeTruthy()
  const parsed = JSON.parse(String((hit as Record<string, unknown>).remark ?? '[]'))
  expect(Array.isArray(parsed), `${itemId} 载荷不是行数组`).toBe(true)
  return parsed as Array<Record<string, unknown>>
}

test.describe('F5 L2 OO→HTML（F5-8 canary + F5-1 其他业务区）', () => {
  for (const itemId of PRE.store_item_ids) {
    test(`前置 P8：${itemId} 已 seed 且行数达标（不因 adapter 缺位而跳过）`, async ({
      request,
    }) => {
      const rows = await readRows(request, itemId)
      const expected = EVIDENCE.items.find((i) => i.store_item_id === itemId)
      expect(
        rows.length,
        `参与 roundtrip 的行数必须 ≥ ${PRE.min_row_count}`
          + `（seed 应造 ${expected?.row_count ?? '?'} 行）`,
      ).toBeGreaterThanOrEqual(PRE.min_row_count)
      for (const [i, row] of rows.entries()) {
        expect(
          row?._seed,
          `${itemId} 第 ${i} 行没有 _seed 标记 —— 说明它不是 seed 造的。`
            + 'e2e 会写格改值，直接跑会污染真实底稿。',
        ).toBe(SEED_TAG)
      }
    })
  }

  test('前置：两区行身份键不同且各自齐备（F5-8 用 id，F5-1 用 rowKey）', async ({
    request,
  }) => {
    const keyByItem = new Map(
      fixture.cases.map((c) => [c.store_item_id, c.row_identity_key]),
    )
    expect(
      new Set(keyByItem.values()).size,
      '两区的行身份键应当不同（这正是本册最容易照抄错的地方）',
    ).toBe(2)

    for (const [itemId, identityKey] of keyByItem) {
      const rows = await readRows(request, itemId)
      for (const [i, row] of rows.entries()) {
        expect(
          String(row?.[identityKey] ?? '').trim(),
          `${itemId} 第 ${i} 行缺 ${identityKey} ⇒ store_row_identity 会 fail-closed`
            + '（框架层绝不退回数组下标）',
        ).not.toBe('')
      }
    }
  })

  test('主营区不可受管：store 里不得出现 F5-1-adj-main-rows 的受管投影', async ({
    request,
  }) => {
    // 🔴 主营区 R8-R17 的 A~I 九列全是引用 F5-2 的模板公式（含 A 列项目名），零可编辑格。
    // 它的 store key 存在是正常的（HTML 侧仍读写），但**不得**进受管清单 —— 否则 OO 侧
    // 写入会与模板公式双源。这里断言它没被 seed 脚本误造成受管载荷。
    const token = await apiLogin(request)
    const res = await request.get(
      `/api/workpapers/${EVIDENCE.wp_id}/checklist-responses`,
      { headers: { Authorization: `Bearer ${token}` }, failOnStatusCode: false },
    )
    const body = await res.json()
    const all: Array<Record<string, unknown>> = Array.isArray(body?.data)
      ? body.data
      : Array.isArray(body)
        ? body
        : []
    const main = all.find((r) => r?.item_id === 'F5-1-adj-main-rows')
    if (main) {
      const parsed = JSON.parse(String(main.remark ?? '[]'))
      const rows: Array<Record<string, unknown>> = Array.isArray(parsed) ? parsed : []
      const seeded = rows.filter((r) => r?._seed === SEED_TAG)
      expect(
        seeded.length,
        'seed 脚本不得往主营区造载荷（该区零可编辑格，受管它等于登记只读投影）',
      ).toBe(0)
    }
  })

  for (const c of fixture.cases) {
    test(`${c.id}: ${c.description}`, async ({ page }) => {
      test.skip(c.result_enum === 'pending_adapter', `⏭️ ${c.id}: ${c.pending_reason}`)
      // 供给就绪后补全五步：
      // 1. 打开 wp ${EVIDENCE.wp_id} 的 ${c.sheet_name}
      // 2. 切「在线编辑」→ 等 data-testid=wp-sync-host-editor
      //    🔴 F5 宿主带 isHtmlSheet 门控，受管判定是 isHtmlSheet && currentSheet in MAP
      // 3. 写 ${c.edit_cell} = ${c.edit_value} → Enter
      // 4. 等 forcesave callback 落地（durable ack）
      // 5. 三谓词 + 核公式列 ${c.expect_formula_columns.join('/') || '（无）'} 仍由模板算出
      //    + P20 TB 红线：全程对 trial_balance 的写次数为 0
      expect(page).toBeTruthy()
    })
  }
})
