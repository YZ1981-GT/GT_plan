/**
 * F4-8 应付账款检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * 通用五条用例见 voucherFillHostHarness（读行顺序：借方区、贷方区，空白占位行不算；单列金额）；另验：
 * 借贷分区与检查比例、区里的空白占位行回填时去掉、新行附件位顺延；单据核对保存保留行上的 `_gt`
 * （原读入逐字段重建会丢）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, watch, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { isBlankF4VoucherRow, useF4VoucherCheck, type F4VoucherCheckRow } from '../useF4VoucherCheck'
import type { ChecklistResponse } from '../useF4FormData'
import { paired, resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

const KEYS = { debit: 'F4-8-debit-rows', credit: 'F4-8-credit-rows' } as const
type F4Api = ReturnType<typeof useF4VoucherCheck>
const meta = (r: unknown) => (r as Record<string, unknown>)._gt as Record<string, unknown> | undefined
/** 区里没有行时补的那行空行不算（回填会去掉它） */
const real = (r: F4VoucherCheckRow) => !!meta(r) || !isBlankF4VoucherRow(r)

/** seed 行带 `table: 'credit'` 的进贷方区，其余进借方区；没有行的区不写 */
function make(seed?: Array<Record<string, unknown>>, extra: Array<[string, unknown]> = []): HostInstance<F4VoucherCheckRow> & { api: F4Api } {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const put = (key: string, value: unknown) => {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark: JSON.stringify(value) } as ChecklistResponse)
  }
  for (const [table, key] of [[undefined, KEYS.debit], ['credit', KEYS.credit]] as const) {
    const rows = (seed ?? []).filter(r => r.table === table)
    if (rows.length) put(key, rows)
  }
  for (const [key, value] of extra) put(key, value)
  let saves = 0
  watch(() => Object.values(KEYS).map(k => allResponses.value.get(k)), () => { saves += 1 }, { flush: 'sync' })
  const api = useF4VoucherCheck({ wpId: ref('wp-f4'), projectId: ref('proj-1'), allResponses, isReadonly: ref(false) })
  const parse = (key: string) => JSON.parse(String(allResponses.value.get(key)?.remark || '[]')) as F4VoucherCheckRow[]
  return {
    api,
    rows: () => [...api.debitRows.value, ...api.creditRows.value].filter(real),
    stored: () => Object.values(KEYS).flatMap(parse).filter(real),
    rowSaves: () => saves,
  }
}

beforeEach(resetVoucherFillMocks)

describe('F4-8 抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<F4VoucherCheckRow>({
    make: (seed?: unknown[]) => make(seed as Array<Record<string, unknown>>),
    idKey: 'rowId',
    view: r => [r.voucherNo, [r.counterAccount, r.detailAccount].filter(Boolean).join(' '), r.amount],
    // 借方区在前；本表一列金额（取样本自己那一栏）
    expected: [
      ['0014', '多科目', 1000],
      ['0012', '1002 银行存款', 200],
      ['0012', '6111 投资收益', 100],
    ],
    edit: (inst, id, value) => (inst.api as unknown as F4Api).updateCell('debit', id, 'issueDesc', value),
    editKey: 'issueDesc',
    manualRow: { rowId: 'm1', voucherNo: '手-1' },
    oldRow: { voucherNo: '0012', voucherDate: '2025-03-04', amount: 1000, supplierName: '甲公司' },
    oldRowKept: { supplierName: '甲公司' },
  })

  it('借贷分区与检查比例；空白占位行回填时去掉、新行附件位顺延', async () => {
    const inst = make(undefined, [['F4-2-rows', [{ currentDebit: 1000, currentCredit: 5000 }, { currentDebit: 1000, currentCredit: 5000 }]]])
    expect(inst.api.debitRows.value).toHaveLength(1)
    await inst.api.onEngineFilled({
      samples: [
        sample('fp-1', { voucherNo: '记-D1', debitAmount: '800.00', pairing: paired(['1002', '银行存款', '800.00']) }),
        sample('fp-2', { voucherNo: '记-C1', debitAmount: null, creditAmount: '4000.00', pairing: paired(['1405', '库存商品', '4000.00']) }),
      ],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.api.debitRows.value.map(r => [r.seq, r.attSlot, r.voucherNo, r.amount, r.counterAccount, r.detailAccount]))
      .toEqual([[1, 1, '记-D1', 800, '1002', '银行存款']])
    expect(inst.api.creditRows.value.map(r => [r.seq, r.attSlot, r.voucherNo, r.amount])).toEqual([[1, 1, '记-C1', 4000]])
    expect(inst.api.checkRatios.value.map(r => [r.label, r.bookAmount, r.checkedAmount, r.ratio]))
      .toEqual([['本期借方', 2000, 800, 40], ['本期贷方', 10000, 4000, 40]])
  })

  it('贷方红字进贷方区、带符号照记（不写成借方负数），借方红字进借方区', async () => {
    const inst = make()
    await inst.api.onEngineFilled({
      samples: [
        sample('fp-1', { voucherNo: '记-C9', debitAmount: null, creditAmount: '-120.00', pairing: paired(['1405', '库存商品', '-120.00']) }),
        sample('fp-2', { voucherNo: '记-D9', debitAmount: '-80.00', pairing: paired(['1002', '银行存款', '-80.00']) }),
      ],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.api.debitRows.value.map(r => [r.voucherNo, r.amount])).toEqual([['记-D9', -80]])
    expect(inst.api.creditRows.value.map(r => [r.voucherNo, r.amount])).toEqual([['记-C9', -120]])
  })

  it('单据核对保存保留行上的 `_gt`', async () => {
    const inst = make()
    await inst.api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    const row = inst.api.debitRows.value[0]
    inst.api.saveRow('debit', { ...row, approvalDateNo: 'SP-1' } as F4VoucherCheckRow)
    expect(inst.api.debitRows.value[0].approvalDateNo).toBe('SP-1')
    expect(meta(inst.stored()[0])).toMatchObject({ lfp: 'fp-1', b: 'b-1' })
  })
})
