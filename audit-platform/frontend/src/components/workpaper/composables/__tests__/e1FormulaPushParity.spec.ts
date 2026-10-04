/**
 * E1 公式推送 · 前后端同式双侧夹具（前端侧）
 *
 * spec: chain-closure-phase2-formula-push-engine · design §一.3 / 任务 9
 *
 * 后端公式推送引擎复刻了 E1 的派生算式（明细合计 → 审定合计 / 语义槽 → 披露主表）。
 * 本 spec 用**真 composable / 纯函数**按与后端引擎相同的管线逐级算出期望值，与
 * `backend/tests/fixtures/formula_push_e1_parity.json` 逐值比对；后端
 * `test_formula_push_e1_parity.py` 用同一夹具断言 `e1_calc` 逐值相等。
 * **任一侧改算式，另一侧必红。**
 *
 * 重新生成夹具（仅在有意改动前端算式后）：
 *   $env:UPDATE_E1_PUSH_PARITY='1'; npx vitest --run src/components/workpaper/composables/__tests__/e1FormulaPushParity.spec.ts
 * 生成后必须同时跑后端 `test_formula_push_e1_parity.py` 并让它变绿（即同步改后端算式）。
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { defineComponent, h, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'

import { useE1CashDetail } from '../useE1CashDetail'
import { useE1BankDetail, type BankDetailVariant } from '../useE1BankDetail'
import { useE1Adjudication, type ChecklistResponse } from '../useE1Adjudication'
import {
  buildBankSeedRows,
  buildCashSeedRows,
  buildCrossSheetSeeds,
  normalizePrefill,
} from '../e1FourTablePrefill'
import { buildBankSeedRowsFromAccounts, normalizeAccountPrefill } from '../e1BankAccountPrefill'
import { buildE1MainRowSlotWrites, E1_MAIN_ROW_DEDUCTIONS, E1_MAIN_ROW_SLOTS } from '../e1MainRowPrefill'
import { computeE1DisclosureMainRows } from '../e1DisclosureMainRows'
import { e1MainRows, type E1DisclosureVariantKey } from '../e1DisclosureScope'
import { E1_HALL_ADJ_ITEM_KEYS } from '../e1AdjustmentFor'

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    try {
      readFileSync(resolve(dir, 'backend/app/services/formula_push/bindings/e1_calc.py'))
      readFileSync(resolve(dir, 'audit-platform/frontend/package.json'))
      return dir
    } catch {
      dir = resolve(dir, '..')
    }
  }
  throw new Error('定位不到仓库根（双哨兵均未命中）')
}

const FIXTURE = resolve(repoRoot(), 'backend/tests/fixtures/formula_push_e1_parity.json')
const UPDATE = process.env.UPDATE_E1_PUSH_PARITY === '1'

type Json = Record<string, unknown>
interface ParityCase {
  name: string
  entries: Record<string, string>
  fourTablePrefill: Json
  accountPrefill: Json | null
}

const j = (v: unknown): string => JSON.stringify(v)

// ─── 用例（改动须重新生成夹具）────────────────────────────────────────────────
const CASES: ParityCase[] = [
  {
    name: 'listed_rmb_rows',
    fourTablePrefill: {
      cash: [
        { code: '1001.01', name: '人民币', currency: 'CNY', opening: 286.73, increase: 90, decrease: 0, ending: 376.73 },
        { code: '1001.02', name: '美元', currency: 'USD', opening: 100.5, increase: 20.25, decrease: 10, ending: 110.75 },
      ],
      bank: [{ code: '1002.01', name: '工行', currency: '', opening: 22944619.45, increase: 1000000.1, decrease: 19241563.29, ending: 4703056.26 }],
      other: [{ code: '1012.02', name: '保证金', currency: 'CNY', opening: 6000001.09, increase: 0.1, decrease: 1520861.19, ending: 4479140 }],
      finance_co: [],
      digital: [],
    },
    accountPrefill: null,
    entries: {
      'E1-cash-detail-rows': j([
        { id: 'fixed-rmb', currency: '人民币', opening: 286.73, increase: 90, decrease: 0, fxRate: 1, adjustment: 0, note: '四表取数 1001.01' },
        { id: 'cash-ft-1001.02', currency: 'USD', opening: 100.5, increase: 20.25, decrease: 10, fxRate: 7.1, adjustment: 0, note: '四表取数 1001.02' },
        { id: 'cash-u1', currency: '欧元', opening: 3.3, increase: 0, decrease: 1.1, fxRate: 7.9, adjustment: 0, note: '手工' },
        // 外币种子行汇率待录入（fxRate 0）与缺汇率字段：composable 按 0 折算（宿主 reconcile 已对齐为同一口径）
        { id: 'cash-ft-1001.03', currency: 'HKD', opening: 50, increase: 5, decrease: 1, fxRate: 0, adjustment: 0, note: '四表取数 1001.03' },
        { id: 'cash-u2', currency: '日元', opening: 1000, increase: 0, decrease: 0, adjustment: 0, note: '缺汇率' },
      ]),
      'E1-bank-detail-rows': j([
        { id: 'bank-principal-institution-ft-1002.01', section: 'principal', group: 'institution', opening: 22944619.45, increase: 1000000.1, decrease: 19241563.29, adjustment: 0 },
        { id: 'bank-fin-1', section: 'principal', group: 'finance', opening: 1000, increase: 500.5, decrease: 200.25 },
        { id: 'bank-principal-other-ft-1012.02', section: 'principal', group: 'other', opening: 6000001.09, increase: 0.1, decrease: 1520861.19 },
        { id: 'bank-accrued-1', section: 'accrued', group: 'institution', opening: 12.5, increase: 3, decrease: 1 },
      ]),
      'E1-bank-variant': 'rmb',
      'E1-adjustment-by-item-cash-ending': '-10.5',
      'E1-adjustment-by-item-cash-opening': '2',
      'E1-adjustment-by-item-bank_principal-ending': '1000',
      'E1-adjustment-by-item-other_mf-ending': '-0.1',
      'E1-adjustment-by-item-digital-ending': '5',
      'E1-adjustment-by-item-accrued_bank-ending': '7.77',
      'E1-adjustment-by-item-finance_co-ending': '3',
      'E1-hall-adj-cash-ending': '100',
      'E1-hall-adj-other_mf-ending': '-50.25',
      'E1-hall-adj-bank_principal-ending': '0',
      'E1-hall-adj-digital-ending': '999',
      'E1-digital-opening-unaudited': '10',
      'E1-digital-total-unaudited': '20.5',
      'E1-accrued-interest-rows': j([{ category: 'bank', accruedRmb: 12.34 }, { category: 'finance', accruedRmb: 1.5 }, { accruedRmb: 2 }]),
      'E1-adj-accrued_finance-opening-unadj': '0.5',
      'E1-disclosure-listed-openings': j({ bank: 111.11, overseas: '5' }),
      'E1-disclosure-soe-openings': j({ cash: 'abc' }),
    },
  },
  {
    name: 'soe_multi_accounts',
    fourTablePrefill: {
      cash: [],
      bank: [{ code: '1002', name: '银行存款', currency: '', opening: 8255, increase: 921, decrease: 52, ending: 9124 }],
      other: [],
      finance_co: [],
      digital: [],
    },
    accountPrefill: {
      accounts: {
        bank: [
          { account_code: '1002', account_no: '6222-1', bank_name: '工行', currency: 'CNY', opening: 1000, debit: 200, credit: 50, closing: 1150 },
          { account_code: '1002', account_no: '6222-1', bank_name: '工行二', currency: '', opening: 5, debit: 1, credit: 2, closing: 4 },
          { account_code: '1002', account_no: '', bank_name: '建行', currency: 'USD', opening: 7200, debit: 720, credit: 0, closing: 7920 },
        ],
        other: [{ account_code: '1012', account_no: 'BZJ', bank_name: '保证金', currency: '人民币', opening: 300, debit: 0, credit: 100, closing: 200 }],
        finance_co: [{ account_code: '1002.09', account_no: 'CWGS', bank_name: '财务公司', currency: 'CNY', opening: 50, debit: 5, credit: 0, closing: 55 }],
        unassigned: [],
      },
      reconcile: {},
      meta: { source: 'tb_aux_balance', account_count: 5, parsed_level_dist: {} },
    },
    entries: {
      'E1-bank-variant': 'multi',
      'E1-bank-detail-rows': j([
        { id: 'bank-principal-institution-acct-6222-1', section: 'principal', group: 'institution', opening: 1000, increase: 200, decrease: 50, fxCurrency: '人民币', fxRate: 1, openingFc: 1000, increaseFc: 200, decreaseFc: 50, adjustmentFc: 0 },
        { id: 'bank-principal-institution-acct-1002', section: 'principal', group: 'institution', opening: 0, increase: 0, decrease: 0, fxCurrency: 'USD', fxRate: 0, openingFc: 0, increaseFc: 0, decreaseFc: 0 },
        { id: 'usd-auth', section: 'principal', group: 'institution', opening: 1, increase: 1, decrease: 1, fxCurrency: '美元', fxRate: 7.2, openingFc: 1000, increaseFc: 100.5, decreaseFc: 0.25 },
        { id: 'legacy-group', section: 'weird', group: 'bank', opening: 10, increase: 5, decrease: 1 },
        { id: 'fx-empty', section: 'principal', group: 'other', opening: 300, increase: 0, decrease: 100, fxCurrency: '人民币', fxRate: '' },
        { id: 'bank-principal-finance-acct-CWGS', section: 'principal', group: 'finance', opening: 50, increase: 5, decrease: 0, fxCurrency: 'CNY', fxRate: 1, openingFc: 50, increaseFc: 5, decreaseFc: 0 },
      ]),
      'E1-adjustment-by-item-bank_principal-opening': '1.25',
      'E1-hall-adj-bank_principal-ending': '12.5',
      'E1-disclosure-soe-openings': j({ bank: 0, digital: '3.5' }),
    },
  },
  {
    name: 'no_rows_leaf_fallback',
    fourTablePrefill: {
      cash: [{ code: '1001', name: '库存现金', currency: '', opening: 50, increase: 10, decrease: 5, ending: 55 }],
      bank: [
        { code: '1002.01', name: '工行', currency: '', opening: 100, increase: 50, decrease: 30, ending: 120 },
        { code: '1002.02', name: '农行', currency: '', opening: 0.1, increase: 0.2, decrease: 0, ending: 0.3 },
      ],
      other: [{ code: '1012.01', name: '其他', currency: '', opening: 7, increase: 0, decrease: 0, ending: 7 }],
      finance_co: [],
      digital: [],
    },
    accountPrefill: null,
    entries: {
      'E1-adjustment-by-item-other_mf-opening': '0.3',
    },
  },
  {
    name: 'untouched_default_cash',
    fourTablePrefill: {
      cash: [{ code: '1001.01', name: '人民币', currency: 'CNY', opening: 1, increase: 2, decrease: 0.5, ending: 2.5 }],
      bank: [],
      other: [],
      finance_co: [],
      digital: [],
    },
    accountPrefill: null,
    entries: {
      'E1-cash-detail-rows': j([
        { id: 'fixed-rmb', currency: '人民币', opening: 0, increase: 0, decrease: 0, fxRate: 1, adjustment: 0, note: '' },
      ]),
      'E1-bank-variant': 'rmb',
    },
  },
]

// ─── 挂载 composable（真实组件上下文，watch immediate 才会执行）─────────────────

type ResponseMap = Ref<Map<string, ChecklistResponse>>

function toMap(entries: Record<string, string>): ResponseMap {
  const m = new Map<string, ChecklistResponse>()
  for (const [k, v] of Object.entries(entries)) m.set(k, { item_id: k, conclusion: null, remark: v })
  return ref(m) as ResponseMap
}

function withComposable<T>(setup: () => T): { api: T; unmount: () => void } {
  let captured: T | null = null
  const wrapper = mount(defineComponent({ setup() { captured = setup(); return () => h('div') } }))
  if (captured === null) throw new Error('composable 未被捕获')
  return { api: captured as T, unmount: () => wrapper.unmount() }
}

function baseOptions(allResponses: ResponseMap) {
  return {
    wpId: ref('wp-parity'),
    projectId: ref('proj-parity'),
    allResponses,
    saveImmediate: async () => {},
    debouncedSave: async () => {},
    isReadonly: ref(false),
  }
}

const CASH_KEYS = { opening: 'E1-cash-detail-opening-unaudited', ending: 'E1-cash-detail-total-unaudited' }
const BANK_GROUPS = ['principal', 'institution', 'finance', 'other'] as const
const bankKey = (g: string, p: 'opening' | 'ending') =>
  `E1-bank-detail-${g}-${p === 'opening' ? 'opening' : 'total'}-unaudited`

function computeCase(c: ParityCase): Json {
  const prefill = normalizePrefill(c.fourTablePrefill)
  const accountPrefill = normalizeAccountPrefill(c.accountPrefill)
  const variant = (c.entries['E1-bank-variant'] === 'rmb' ? 'rmb' : 'multi') as BankDetailVariant
  const crossSeeds = new Map(buildCrossSheetSeeds(prefill).map((s) => [s.itemId, s.remark]))

  // ① 种子（宿主 seedFromFourTable 口径）
  const cashSeeds = (buildCashSeedRows(prefill) ?? []).map((r) => ({
    id: r.id, opening: r.opening, increase: r.increase, decrease: r.decrease, fxRate: r.fxRate,
  }))
  const bankSeeds = (buildBankSeedRowsFromAccounts(accountPrefill, variant) ?? buildBankSeedRows(prefill) ?? []).map(
    (r) => ({ id: r.id, opening: r.opening, increase: r.increase, decrease: r.decrease }),
  )

  // ② 明细合计键：行存在走 composable，行不存在走宿主 buildCrossSheetSeeds
  const detail: Record<string, string | null> = {}
  if (c.entries['E1-cash-detail-rows'] !== undefined) {
    const map = toMap(c.entries)
    const { unmount } = withComposable(() => useE1CashDetail(baseOptions(map)))
    for (const k of Object.values(CASH_KEYS)) detail[k] = map.value.get(k)?.remark ?? null
    unmount()
  } else {
    for (const k of Object.values(CASH_KEYS)) detail[k] = crossSeeds.get(k) ?? null
  }
  if (c.entries['E1-bank-detail-rows'] !== undefined) {
    const map = toMap(c.entries)
    const { unmount } = withComposable(() => useE1BankDetail({ ...baseOptions(map), variant: ref(variant) }))
    for (const g of BANK_GROUPS) for (const p of ['opening', 'ending'] as const) {
      detail[bankKey(g, p)] = map.value.get(bankKey(g, p))?.remark ?? null
    }
    unmount()
  } else {
    for (const g of BANK_GROUPS) for (const p of ['opening', 'ending'] as const) {
      detail[bankKey(g, p)] = crossSeeds.get(bankKey(g, p)) ?? null
    }
  }

  // ③ 审定表：在明细合计之上挂载 useE1Adjudication（syncAuditedTotals 挂载即写）
  const stage2: Record<string, string> = { ...c.entries }
  for (const [k, v] of Object.entries(detail)) if (v !== null) stage2[k] = v
  const adjMap = toMap(stage2)
  const adj = withComposable(() => useE1Adjudication(baseOptions(adjMap)))
  const adjTotals: Record<string, string | null> = {}
  for (const code of ['1001', '1002', '1012']) {
    for (const suffix of ['', '-opening']) {
      const k = `E1-adj-total-${code}${suffix}`
      adjTotals[k] = adjMap.value.get(k)?.remark ?? null
    }
  }
  const slotWrites = buildE1MainRowSlotWrites(adj.api.detailRows.value)
  adj.unmount()
  const slots: Record<string, string | null> = {}
  for (const key of ['finance_co', 'accrued', 'digital']) {
    for (const suffix of ['', '-opening']) {
      const k = `E1-adj-slot-${key}${suffix}`
      slots[k] = slotWrites.find((w) => w.itemId === k)?.value ?? null
    }
  }

  // ④ 披露主表：在审定合计 + 语义槽之上用纯函数算两变体
  const stage3: Record<string, string> = { ...stage2 }
  for (const [k, v] of Object.entries(adjTotals)) if (v !== null) stage3[k] = v
  for (const [k, v] of Object.entries(slots)) if (v !== null) stage3[k] = v
  const disclosure: Record<string, unknown> = {}
  for (const v of ['listed', 'soe'] as E1DisclosureVariantKey[]) {
    const raw = stage3[`E1-disclosure-${v}-openings`]
    let openingMap: Record<string, unknown> = {}
    if (raw) { try { openingMap = JSON.parse(raw) } catch { openingMap = {} } }
    disclosure[v] = computeE1DisclosureMainRows(v, (k) => stage3[k], openingMap).map((r) => ({
      key: r.key,
      endingAmount: r.endingAmount,
      openingAmount: r.openingAmount,
      endingResolved: r.endingResolved,
      openingResolved: r.openingResolved,
    }))
  }

  return { variant, cashSeeds, bankSeeds, detail, adjTotals, slots, disclosure }
}

function constantsSnapshot(): Json {
  const rows = (v: E1DisclosureVariantKey) =>
    e1MainRows(v).map((r) => ({
      key: r.key, label: r.label, noteLabel: r.noteLabel ?? null, crossKey: r.crossKey,
      isTotal: !!r.isTotal, isMemo: !!r.isMemo,
    }))
  return {
    hallAdjItemKeys: [...E1_HALL_ADJ_ITEM_KEYS],
    mainRowSlots: { ...E1_MAIN_ROW_SLOTS },
    mainRowDeductions: Object.fromEntries(Object.entries(E1_MAIN_ROW_DEDUCTIONS).map(([k, v]) => [k, [...v]])),
    mainRows: { listed: rows('listed'), soe: rows('soe') },
  }
}

function buildFixture(): Json {
  return {
    spec: 'chain-closure-phase2-formula-push-engine',
    generatedBy: 'audit-platform/frontend/src/components/workpaper/composables/__tests__/e1FormulaPushParity.spec.ts',
    constants: constantsSnapshot(),
    cases: CASES.map((c) => ({ ...c, expected: computeCase(c) })),
  }
}

describe('E1 公式推送 · 前后端同式夹具（前端侧）', () => {
  const computed = buildFixture()

  if (UPDATE) {
    it('重新生成夹具', () => {
      writeFileSync(FIXTURE, JSON.stringify(computed, null, 2) + '\n', 'utf-8')
      expect(JSON.parse(readFileSync(FIXTURE, 'utf-8'))).toEqual(computed)
    })
    return
  }

  const committed = JSON.parse(readFileSync(FIXTURE, 'utf-8')) as {
    constants: Json
    cases: Array<ParityCase & { expected: Json }>
  }

  it('夹具用例与本 spec 的用例一致（改用例须重新生成夹具）', () => {
    expect(committed.cases.map((c) => c.name)).toEqual(CASES.map((c) => c.name))
    for (const [i, c] of CASES.entries()) {
      expect({ ...committed.cases[i], expected: undefined }).toEqual({ ...c, expected: undefined })
    }
  })

  it('常量（大厅调整行 / 语义槽 / 扣减映射 / 披露行集）与夹具一致', () => {
    expect(committed.constants).toEqual(computed.constants)
  })

  it.each(CASES.map((c) => c.name))('%s：真 composable 算出的值与夹具逐值一致', (name) => {
    const want = committed.cases.find((c) => c.name === name)!.expected
    const got = (computed.cases as Array<{ name: string; expected: Json }>).find((c) => c.name === name)!.expected
    expect(got).toEqual(want)
  })

  it('夹具非空转：每个用例都有明细 / 审定 / 披露三级输出，且至少一个大厅调整生效', () => {
    for (const c of committed.cases) {
      const e = c.expected as { detail: Json; adjTotals: Json; disclosure: Json }
      expect(Object.keys(e.detail).length).toBe(10)
      expect(Object.keys(e.adjTotals).length).toBe(6)
      expect(Object.keys(e.disclosure)).toEqual(['listed', 'soe'])
    }
    // listed_rmb_rows 的 1001 期末 = 现金明细期末 + E1-5(-10.5) + 大厅(100)
    const first = committed.cases[0].expected as { detail: Record<string, string>; adjTotals: Record<string, string> }
    const cash = Number(first.detail['E1-cash-detail-total-unaudited'])
    expect(Number(first.adjTotals['E1-adj-total-1001'])).toBeCloseTo(cash - 10.5 + 100, 6)
  })
})
