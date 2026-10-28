/**
 * F1-7 预付账款检查表接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * 通用五条用例见 voucherFillHostHarness（读行顺序：本期借方、本期贷方、期后贷方）；另验：分录按借贷方向进
 * 本期借方 / 贷方表、替换不动期后表；行上的 `_gt` 经读入 / 改单元格 / 单据核对保存都还在（原读入逐字段重建会丢）；
 * 年审阶段「标注跨期疑点」不动预审行。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useF1VoucherCheck, type F1CreditCheckRow, type F1DebitCheckRow } from '../useF1ComprehensiveCheck'
import type { ChecklistResponse } from '../useF1FormData'
import { paired, resetVoucherFillMocks, sample, VK, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

const DEBIT = 'F1-vc-current-rows'
const CREDIT = 'F1-vc-credit-rows'
const POST = 'F1-vc-post-rows'
type Row = F1DebitCheckRow | F1CreditCheckRow
type F1Api = ReturnType<typeof useF1VoucherCheck>
const meta = (r: unknown) => (r as Record<string, unknown>)._gt as Record<string, unknown> | undefined
const gt = (ph: string, lfp: string) => ({ vk: VK, lfp, ph, b: 'b-0', src: ['engine'], pr: 'paired' })

/** seed 行带 `table: 'credit' | 'post'` 的进对应表，其余进本期借方表 */
function make(seedIn?: unknown[]): HostInstance<Row> & { api: F1Api } {
  const seed = seedIn as Array<Record<string, unknown>> | undefined
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const put = (key: string, remark: string) => {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark } as ChecklistResponse)
  }
  if (seed) {
    put(DEBIT, JSON.stringify(seed.filter(r => !r.table)))
    put(CREDIT, JSON.stringify(seed.filter(r => r.table === 'credit')))
    put(POST, JSON.stringify(seed.filter(r => r.table === 'post')))
  }
  const debouncedSave = vi.fn((id: string, data: Partial<ChecklistResponse>) => put(id, String(data.remark ?? '')))
  const api = useF1VoucherCheck({
    allResponses, wpId: ref('wp-f1'), projectId: ref('proj-1'),
    saveImmediate: vi.fn(async () => undefined), debouncedSave, isReadonly: ref(false),
  })
  const parse = (key: string) => JSON.parse(String(allResponses.value.get(key)?.remark || '[]'))
  return {
    api,
    rows: () => [...api.debitRows.value, ...api.creditRows.value, ...api.postPeriodRows.value],
    stored: () => [...parse(DEBIT), ...parse(CREDIT), ...parse(POST)],
    rowSaves: () => debouncedSave.mock.calls.filter(c => [DEBIT, CREDIT, POST].includes(c[0])).length,
  }
}

beforeEach(resetVoucherFillMocks)

describe('F1-7 抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<Row>({
    make,
    idKey: 'rowId',
    view: r => [
      r.voucherNo, [r.counterAccount, r.counterDetailAccount].filter(Boolean).join(' '),
      'debitAmount' in r ? r.debitAmount : 0, 'creditAmount' in r ? r.creditAmount : 0,
    ],
    // 借方表在前：多科目那笔借方样本进借方表，贷方样本按对方科目展开进贷方表
    expected: [
      ['0014', '多科目', 1000, 0],
      ['0012', '1002 银行存款', 0, 200],
      ['0012', '6111 投资收益', 0, 100],
    ],
    edit: (inst, id, value) => (inst.api as unknown as F1Api).updateCell('debit', id, 'remark', value),
    editKey: 'remark',
    manualRow: { rowId: 'm1', voucherNo: '手-1' },
    oldRow: { voucherNo: '0012', date: '2025-03-04', debitAmount: 1000, bankPayee: '甲公司' },
    oldRowKept: { bankPayee: '甲公司' },
  })

  it('按借贷方向进本期借方 / 贷方表；「替换本阶段抽凭行」不动期后表', async () => {
    const inst = make([{ rowId: 'p1', voucherNo: '9001', date: '2026-01-05', creditAmount: 50, table: 'post', _gt: gt('final', 'fp-9') }])
    await inst.api.onEngineFilled({
      samples: [
        sample('fp-1'),
        sample('fp-2', { voucherNo: '0013', debitAmount: null, creditAmount: '300.00', pairing: paired(['1123', '预付账款', '300.00']) }),
      ],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.api.debitRows.value.map(r => [r.voucherNo, r.debitAmount])).toEqual([['0012', 1000]])
    expect(inst.api.creditRows.value.map(r => [r.voucherNo, r.creditAmount])).toEqual([['0013', 300]])
    await inst.api.onEngineFilled({ samples: [sample('fp-3', { voucherNo: '0015' })], phase: 'final', fillMode: 'replace', batchId: 'b-2' })
    expect(inst.rows().map(r => r.voucherNo)).toEqual(['0015', '9001'])
  })

  it('贷方红字进本期贷方表、带符号照记（原规则写进借方表成借方负数）', async () => {
    const inst = make([])
    await inst.api.onEngineFilled({
      samples: [sample('fp-1', { voucherNo: '0051', debitAmount: null, creditAmount: '-40.00', pairing: paired(['2202', '应付账款', '-40.00']) })],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.api.debitRows.value.filter(r => r.voucherNo)).toEqual([])
    expect(inst.api.creditRows.value.filter(r => r.voucherNo).map(r => [r.voucherNo, r.creditAmount])).toEqual([['0051', -40]])
  })

  it('改单元格与单据核对保存都保留行上的 `_gt`', async () => {
    const inst = make()
    await inst.api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    const id = inst.api.debitRows.value[0].rowId
    inst.api.updateCell('debit', id, 'remark', '已核')
    inst.api.saveRow('debit', { ...inst.api.debitRows.value[0], approvalOk: '是' })
    expect(inst.api.debitRows.value[0]).toMatchObject({ remark: '已核', approvalOk: '是' })
    expect(meta(inst.stored()[0])).toMatchObject({ lfp: 'fp-1', b: 'b-1' })
  })

  it('年审阶段「标注跨期疑点」不动预审行', async () => {
    const inst = make([
      { rowId: 'p1', voucherNo: '9001', date: '2025-12-20', creditAmount: 50, table: 'post', _gt: gt('preliminary', 'fp-8') },
      { rowId: 'f1', voucherNo: '9002', date: '2025-12-21', creditAmount: 60, table: 'post', _gt: gt('final', 'fp-9') },
    ])
    await inst.api.voucherFillReady()
    expect(inst.api.autoMarkCrossPeriod('2025-12-31')).toBe(1)
    expect(inst.api.postPeriodRows.value.map(r => [r.rowId, r.isAbnormal])).toEqual([['p1', ''], ['f1', '跨期疑点']])
  })
})
