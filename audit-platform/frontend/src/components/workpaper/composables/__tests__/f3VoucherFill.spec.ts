/**
 * F3-7 应付票据检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * 通用五条用例见 voucherFillHostHarness（读行顺序：借方区、贷方区、日后区，空白占位行不算；单列金额）；另验：
 * 借贷分区（红字借方仍进借方区、金额照记）、区里的空白占位行回填时去掉、新行附件位顺延、替换不动日后区；
 * 行上的 `_gt` 经读入 / 单据核对保存都还在（原读入逐字段重建会丢）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, watch, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { isBlankVoucherRow, useF3VoucherCheck, type F3VoucherCheckRow } from '../useF3VoucherCheck'
import type { ChecklistResponse } from '../useF3FormData'
import { paired, resetVoucherFillMocks, sample, VK, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

const KEYS = { debit: 'F3-7-debit-rows', credit: 'F3-7-credit-rows', subsequent: 'F3-7-subsequent-rows' } as const
type F3Api = ReturnType<typeof useF3VoucherCheck>
const meta = (r: unknown) => (r as Record<string, unknown>)._gt as Record<string, unknown> | undefined
/** 区里没有行时补的那行空行不算（回填会去掉它） */
const real = (r: F3VoucherCheckRow) => !!meta(r) || !isBlankVoucherRow(r)

/** seed 行带 `table: 'credit' | 'subsequent'` 的进对应区，其余进借方区 */
function make(seedIn?: unknown[]): HostInstance<F3VoucherCheckRow> & { api: F3Api } {
  const seed = seedIn as Array<Record<string, unknown>> | undefined
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const put = (key: string, rows: unknown[]) => {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark: JSON.stringify(rows) } as ChecklistResponse)
  }
  // 没有行的区不写（与真实底稿一致：从没存过的区读入时补一行空白占位行）
  for (const [table, key] of [[undefined, KEYS.debit], ['credit', KEYS.credit], ['subsequent', KEYS.subsequent]] as const) {
    const rows = (seed ?? []).filter(r => r.table === table)
    if (rows.length) put(key, rows)
  }
  let saves = 0
  watch(() => Object.values(KEYS).map(k => allResponses.value.get(k)), () => { saves += 1 }, { flush: 'sync' })
  const api = useF3VoucherCheck({ wpId: ref('wp-f3'), projectId: ref('proj-1'), allResponses, isReadonly: ref(false) })
  const parse = (key: string) => JSON.parse(String(allResponses.value.get(key)?.remark || '[]')) as F3VoucherCheckRow[]
  return {
    api,
    rows: () => [...api.debitRows.value, ...api.creditRows.value, ...api.subsequentRows.value].filter(real),
    stored: () => Object.values(KEYS).flatMap(parse).filter(real),
    rowSaves: () => saves,
  }
}

beforeEach(resetVoucherFillMocks)

describe('F3-7 抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<F3VoucherCheckRow>({
    make,
    idKey: 'rowId',
    view: r => [r.voucherNo, [r.counterAccount, r.detailAccount].filter(Boolean).join(' '), r.amount],
    // 借方区在前；本表一列金额（取样本自己那一栏）
    expected: [
      ['0014', '多科目', 1000],
      ['0012', '1002 银行存款', 200],
      ['0012', '6111 投资收益', 100],
    ],
    edit: (inst, id, value) => (inst.api as unknown as F3Api).updateCell('debit', id, 'issueDesc', value),
    editKey: 'issueDesc',
    manualRow: { rowId: 'm1', voucherNo: '手-1' },
    oldRow: { voucherNo: '0012', voucherDate: '2025-03-04', amount: 1000, noteType: '银行承兑汇票' },
    oldRowKept: { noteType: '银行承兑汇票' },
  })

  it('按借贷栏分区（借方红字进借方区、贷方红字进贷方区，带符号照记）；空白占位行回填时去掉、新行附件位顺延；替换不动日后区', async () => {
    const inst = make([
      { rowId: 's1', voucherNo: '9001', voucherDate: '2026-01-05', amount: 50, table: 'subsequent',
        _gt: { vk: VK, lfp: 'fp-9', ph: 'final', b: 'b-0', src: ['engine'], pr: 'paired' } },
    ])
    expect(inst.api.debitRows.value).toHaveLength(1)
    await inst.api.onEngineFilled({
      samples: [
        sample('fp-1'),
        sample('fp-2', { voucherNo: '0013', debitAmount: '-30.00', pairing: paired(['1002', '银行存款', '-30.00']) }),
        sample('fp-3', { voucherNo: '0014', debitAmount: null, creditAmount: '500.00', pairing: paired(['2202', '应付账款', '500.00']) }),
        // 余额结转类贷方红字（医疗器械 0051 实测）：进贷方区、金额 -20，不写成借方负数
        sample('fp-5', { voucherNo: '0051', debitAmount: null, creditAmount: '-20.00', pairing: paired(['2201.02', '商业承兑汇票', '-20.00']) }),
      ],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.api.debitRows.value.map(r => [r.seq, r.attSlot, r.voucherNo, r.amount])).toEqual([[1, 1, '0012', 1000], [2, 2, '0013', -30]])
    expect(inst.api.creditRows.value.map(r => [r.voucherNo, r.amount, r.counterAccount])).toEqual([['0014', 500, '2202'], ['0051', -20, '2201.02']])
    expect([inst.api.debitTotal.value, inst.api.creditTotal.value]).toEqual([970, 480])
    await inst.api.onEngineFilled({ samples: [sample('fp-4', { voucherNo: '0015' })], phase: 'final', fillMode: 'replace', batchId: 'b-2' })
    expect(inst.rows().map(r => r.voucherNo)).toEqual(['0015', '9001'])
  })

  it('单据核对保存保留行上的 `_gt`', async () => {
    const inst = make()
    await inst.api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    const row = inst.api.debitRows.value[0]
    inst.api.saveRow('debit', { ...row, approvalDateNo: 'SP-1' } as F3VoucherCheckRow)
    expect(inst.api.debitRows.value[0].approvalDateNo).toBe('SP-1')
    expect(meta(inst.stored()[0])).toMatchObject({ lfp: 'fp-1', b: 'b-1' })
  })
})
