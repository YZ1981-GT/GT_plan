/**
 * G2-8 应收利息凭证检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * 通用五条用例见 voucherFillHostHarness（借方区在前、贷方区在后读行）；另验：进区沿用原规则、两区各自去重；
 * 年审阶段「异常行索引 → G2-4」不动预审行；年审阶段 Excel 导入改了 / 删了的预审行按读入版本写回，
 * 导入的行沿用导入前同一分录的 `_gt`（导入不经改行入口，只有保存时的写回兜底）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, watch, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useG2VoucherCheck, type G2StoredVoucherRow } from '../useG2VoucherCheck'
import type { ChecklistResponse } from '../useF1FormData'
import { paired, resetVoucherFillMocks, sample, VK, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

const DEBIT = 'G2-8-debit-check-rows'
const CREDIT = 'G2-8-credit-check-rows'
type G2Api = ReturnType<typeof useG2VoucherCheck>
/** 贷方区的行（落库行带贷方区才有的字段） */
const isCredit = (r: unknown) => 'receivingBank' in (r as object)
const meta = (r: unknown) => (r as Record<string, unknown>)._gt as Record<string, unknown> | undefined
const gt = (ph: string, lfp: string) => ({ vk: VK, lfp, ph, b: 'b-0', src: ['engine'], pr: 'paired' })

function make(seed?: unknown[]): HostInstance<G2StoredVoucherRow> & { api: G2Api } {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const put = (key: string, rows: unknown[]) => {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark: JSON.stringify(rows) } as ChecklistResponse)
  }
  if (seed) {
    put(DEBIT, seed.filter(r => !isCredit(r)))
    put(CREDIT, seed.filter(isCredit))
  }
  // 两区的 JSON 每写一次计一次（G2 的行就存在这两项里，改行即写）
  let saves = 0
  watch([() => allResponses.value.get(DEBIT), () => allResponses.value.get(CREDIT)], () => { saves += 1 }, { flush: 'sync' })
  const api = useG2VoucherCheck({ wpId: ref('wp-2'), projectId: ref('proj-1'), allResponses, isReadonly: ref(false) })
  const parse = (key: string) => JSON.parse(String(allResponses.value.get(key)?.remark ?? '[]'))
  return {
    api,
    rows: () => [...api.debitRows.value, ...api.creditRows.value],
    stored: () => [...parse(DEBIT), ...parse(CREDIT)],
    rowSaves: () => saves,
  }
}

beforeEach(resetVoucherFillMocks)

describe('G2-8 抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<G2StoredVoucherRow>({
    make,
    idKey: 'id',
    view: r => [r.voucherNo, r.counterAccount, isCredit(r) ? 0 : r.amount, isCredit(r) ? r.amount : 0],
    // 借方区在前：多科目那笔借方样本进借方区，贷方样本按对方科目展开进贷方区
    expected: [
      ['0014', '多科目', 1000, 0],
      ['0012', '1002 银行存款', 0, 200],
      ['0012', '6111 投资收益', 0, 100],
    ],
    edit: (inst, id, value) => (inst.api as unknown as G2Api).updateDebitCell(id, 'remark', value),
    editKey: 'remark',
    manualRow: { id: 'm1', voucherNo: '手-1' },
    oldRow: { voucherNo: '0012', voucherDate: '2025-03-04', amount: 1000, supportingDocs: '合同' },
    oldRowKept: { supportingDocs: '合同' },
  })

  it('按分录自己的借贷栏进区（贷方红字进贷方区、带符号照记）；一次抽凭两区都填、各自去重、序号连续', async () => {
    const inst = make()
    const batch = [
      sample('fp-1'),
      sample('fp-2', { voucherNo: '0013', debitAmount: null, creditAmount: '300.00', pairing: paired(['1002', '银行存款', '300.00']) }),
      sample('fp-3', { voucherNo: '0014', debitAmount: null, creditAmount: '-50.00', pairing: paired(['6111', '投资收益', '-50.00']) }),
    ]
    await inst.api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-1' })
    await inst.api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-2' })
    expect(inst.api.debitRows.value.map(r => [r.seq, r.voucherNo, r.amount, r.counterAccount]))
      .toEqual([[1, '0012', 1000, '1002 银行存款']])
    expect(inst.api.creditRows.value.map(r => [r.seq, r.voucherNo, r.amount, r.counterAccount]))
      .toEqual([[1, '0013', 300, '1002 银行存款'], [2, '0014', -50, '6111 投资收益']])
  })

  it('年审阶段「异常行索引 → G2-4」不动预审行，只填本阶段的异常行', async () => {
    const inst = make([
      { id: 'p1', voucherNo: '0012', voucherDate: '2025-03-04', amount: 100, isAbnormal: true, _gt: gt('preliminary', 'fp-1') },
      { id: 'f1', voucherNo: '0013', voucherDate: '2025-03-05', amount: 100, isAbnormal: true, _gt: gt('final', 'fp-2') },
    ])
    await inst.api.voucherFillReady()
    expect(inst.api.fillAbnormalIndexToAdjustment(false)).toBe(1)
    expect(inst.stored().map(r => [r.id, r.indexRef])).toEqual([['p1', ''], ['f1', 'G2-4']])
  })

  it('年审阶段 Excel 导入：改了的预审行按读入版本写回、删了的补回；导入的行沿用导入前同一分录的 `_gt`', async () => {
    const inst = make([
      { id: 'p1', voucherNo: '0012', voucherDate: '2025-03-04', amount: 1000, auditConclusion: '已核对', _gt: gt('preliminary', 'fp-1') },
      { id: 'p2', voucherNo: '0015', voucherDate: '2025-03-06', amount: 70, auditConclusion: '已核对', _gt: gt('preliminary', 'fp-5') },
      { id: 'f1', voucherNo: '0013', voucherDate: '2025-03-05', amount: 20, _gt: gt('final', 'fp-2') },
    ])
    await inst.api.voucherFillReady()
    // 导入：预审行 0012 的结论被改、0015 被删；本阶段行 0013 摘要改了；新增一行 0016（Excel 不带 `_gt`、不带行 id）
    const flat = [
      { checkZone: 'debit', voucherNo: '0012', voucherDate: '2025-03-04', amount: 1000, auditConclusion: '改了' },
      { checkZone: 'debit', voucherNo: '0013', voucherDate: '2025-03-05', amount: 20, summary: '改了摘要' },
      { checkZone: 'debit', voucherNo: '0016', voucherDate: '2025-03-07', amount: 5 },
    ]
    expect(inst.api.hydrateFromFlat(JSON.stringify(flat))).toBe(true)
    const stored = inst.stored()
    expect(stored.map(r => [r.seq, r.voucherNo, r.auditConclusion])).toEqual([
      [1, '0012', '已核对'], [2, '0013', ''], [3, '0016', ''], [4, '0015', '已核对'],
    ])
    expect(stored.map(r => r.id).filter(id => id === 'p1' || id === 'p2')).toEqual(['p1', 'p2'])
    expect(meta(stored[1])).toMatchObject({ lfp: 'fp-2', ph: 'final' })
    expect(stored[1].summary).toBe('改了摘要')
    expect(meta(stored[2])).toBeUndefined()
  })
})
