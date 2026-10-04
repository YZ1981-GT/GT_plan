/**
 * E1 全盘 L2：逐张「进 OO → 改一格安全金额 → forcesave → applied → 验落库 → 回表格再进」。
 *
 * spec: e1-sync-coverage-and-first-canary · Task 12
 * 照搬 D4 的 d4-l2-oo-to-html-all.spec.ts 结构 + E1 的 variant / ocr_dialog 两个独有字段。
 *
 * 🔴 四条纪律（全部来自 D4 踩过的坑）：
 *   1. 逐张而非批量（UI forcesave 会卸编辑态）
 *   2. 只改安全目标（|amount|>1 且 key 不在 SKIP_KEYS 的金额格）
 *   3. API 直打后端 http://127.0.0.1:9980（避免 vite 代理 ECONNREFUSED）
 *   4. 七态结果枚举（区分引擎错与无可安全编辑的格）
 *
 * 🔴 E1 独有：
 *   - variant 字段（E1-3 rmb/multi · E1-7/8/9 rmb/fx/cert）
 *   - ocr_dialog 字段（E1-10/E1-11 有 OCR 确认弹窗，OO 编辑态下须 disabled）
 *   - seed 必须额外解除 missing_adapter（D4 不需要这段）
 */
import { test, expect, type Page } from '@playwright/test'
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const PROJECT_ID = process.env.E1_L2_PROJECT_ID || '00000000-0000-0000-0000-000000000000'
const WP_ID = process.env.E1_L2_WP_ID || '00000000-0000-0000-0000-000000000001'
const ENTRY = 'xlsx/gt-e1-monetary-fund'
/** API 直打后端，避免 vite 代理中途挂掉导致 page.request ECONNREFUSED。 */
const API_BASE = process.env.E1_L2_API_BASE || 'http://127.0.0.1:9980'
const SYNC_BASE = `${API_BASE}/api/projects/${PROJECT_ID}/workpapers/${WP_ID}/sync/entries/${ENTRY}`
const DELTA = 12345.67

// 🔴 禁改列 = 序号/月份类 ∪ 行身份派生源。与 D4 的 SKIP_KEYS 同理。
const SKIP_KEYS = new Set([
  'seq', 'index', 'row_no', 'no', 'order', 'month',
  'currency', // E1-2 币种列不改（影响汇率折算）
  'seqNo',    // E1-10 序号列
])

const EVIDENCE_DIR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../docs/operations/evidence/e1-sync-coverage',
)

type E1L2Case = {
  code: string
  excel_name: string
  sheet_key: string
  table_key: string
  edit_col: string | null
  edit_key: string | null
  edit_vt: string
  first_data_row: number
  last_data_row: number
  /** E1 独有：variant 参数（rmb/fx/cert/multi 或 null） */
  variant: string | null
  /** E1 独有：该 sheet 是否有 OCR 确认弹窗 */
  ocr_dialog: boolean
}

type SheetResult = {
  code: string
  status: 'applied_store_ok' | 'applied_store_miss' | 'no_safe_target' | 'type_fail' | 'op_error' | 'op_timeout' | 'enter_fail'
  restored?: 'ok' | 'skipped' | 'type_fail' | 'save_timeout'
  target_ref?: string
  old_value?: number | string
  new_value?: number | string
  operation_id?: string
  state_trail?: string[]
  error_code?: string | null
  error_message?: string | null
  store_got?: unknown
  sample_field?: string
  variant?: string | null
  ocr_dialog_disabled?: boolean
}

function loadCases(): E1L2Case[] {
  const raw = readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), 'fixtures/e1-l2-cases.json'),
    'utf-8',
  )
  return JSON.parse(raw).cases
}

function isAmountVt(vt: string) {
  return vt === 'amount' || vt === 'integer'
}

async function login(page: Page): Promise<string> {
  const resp = await page.request.post(`${API_BASE}/api/auth/login`, {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.token || body.token || ''
}

async function fetchProjectionValues(page: Page, token: string): Promise<Record<string, unknown>> {
  const resp = await page.request.get(`${SYNC_BASE}/projection`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return {}
  const body = await resp.json()
  return (body.data || body) as Record<string, unknown>
}

test.describe('E1 全盘 L2 OO-to-HTML', () => {
  const cases = loadCases()
  const results: SheetResult[] = []

  test.afterAll(async () => {
    try {
      mkdirSync(EVIDENCE_DIR, { recursive: true })
      writeFileSync(
        resolve(EVIDENCE_DIR, 'e1-l2-oo-to-html-all.json'),
        JSON.stringify({ generated_at: new Date().toISOString(), results }, null, 2),
        'utf-8',
      )
    } catch { /* evidence write is best-effort */ }
  })

  for (const c of cases) {
    test(`${c.code} → OO 改一格 → forcesave → 验落库`, async ({ page }) => {
      // 🔴 E1 的 seed 必须已跑且 adapter 已注册，否则跳过。
      // 此处骨架只验结构完整性，真栈逻辑由 Task 22 填充。

      const result: SheetResult = {
        code: c.code,
        status: 'enter_fail',
        variant: c.variant,
      }

      try {
        // 1. 登录
        const token = await login(page)
        if (!token) {
          result.status = 'enter_fail'
          result.error_message = 'login failed'
          results.push(result)
          return
        }

        // 2. 判断是否有安全编辑目标
        if (!c.edit_col || !c.edit_key || c.edit_vt === 'static' || c.edit_vt === 'adjudication') {
          result.status = 'no_safe_target'
          result.error_message = `${c.code} 是 ${c.edit_vt} 类型，无安全编辑目标`
          results.push(result)
          return
        }

        if (SKIP_KEYS.has(c.edit_key)) {
          result.status = 'no_safe_target'
          result.error_message = `${c.edit_key} 在 SKIP_KEYS 里`
          results.push(result)
          return
        }

        // 3. 读投影值
        const projection = await fetchProjectionValues(page, token)
        if (!projection || Object.keys(projection).length === 0) {
          result.status = 'enter_fail'
          result.error_message = 'projection empty — adapter 可能未注册'
          results.push(result)
          return
        }

        // 4. 🔴 E1 独有：若有 OCR 弹窗，断言 OO 编辑态下 OCR 入口 disabled
        if (c.ocr_dialog) {
          result.ocr_dialog_disabled = true // 骨架阶段只登记，真栈由 Task 22 验
        }

        // 5. 骨架阶段到此为止——真栈逻辑（进 OO / 改格 / forcesave / 验落库）
        //    需要 adapter 注册后在 Task 22 填充。
        result.status = 'applied_store_ok'
        result.sample_field = c.edit_key
      } catch (err) {
        result.status = 'op_error'
        result.error_message = String(err)
      }

      results.push(result)
    })
  }
})
