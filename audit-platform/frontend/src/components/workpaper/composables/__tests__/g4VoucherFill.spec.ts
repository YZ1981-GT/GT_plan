/**
 * G4-13 债权投资凭证检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * 通用五条用例见 voucherFillHostHarness（宿主表格 v-model 原地改行，组合式函数唯一的改行入口是删行 ⇒ 用它验只读；
 * 原地改了内存靠保存时按读入版本写回兜底）；另验：借方有正数进借方区、其余进贷方区，序号按区重排，
 * 金额在样本自己的借贷栏；父组件经 toJSON 保存时预审行同样按读入版本写回。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { watch } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useG4EclVoucherCheck } from '../useG4EclVoucherCheck'
import type { VoucherCheckRow } from '../useG4EclFormData'
import { paired, resetVoucherFillMocks, sample, VK, voucherFillHostCases, type HostInstance } from './voucherFillHostHarness'

type G4Api = ReturnType<typeof useG4EclVoucherCheck>

function make(seed?: unknown[]): HostInstance<VoucherCheckRow> & { api: G4Api } {
  const api = useG4EclVoucherCheck({ projectId: 'proj-1', readonly: false })
  api.loadRows((seed ?? []) as VoucherCheckRow[])
  // 宿主深度监听 rows 落库：每触发一次计一次
  let saves = 0
  watch(api.rows, () => { saves += 1 }, { deep: true, flush: 'sync' })
  return {
    api,
    rows: () => api.rows.value,
    stored: () => JSON.parse(JSON.stringify(api.rowsToPersist())),
    rowSaves: () => saves,
  }
}

beforeEach(resetVoucherFillMocks)

describe('G4-13 抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<VoucherCheckRow>({
    make,
    idKey: 'id',
    view: r => [r.voucherNo, [r.counterAccount, r.detailAccount].filter(Boolean).join(' '), r.debitAmount, r.creditAmount],
    edit: (inst, id) => (inst.api as unknown as G4Api).removeRow(id),
    editKey: 'remark',
    manualRow: { id: 'm1', voucherNo: '手-1', section: 'debit' },
    oldRow: { voucherNo: '0012', date: '2025-03-04', debitAmount: 1000, creditAmount: 0, section: 'debit', supportingDocDesc: '合同' },
    oldRowKept: { supportingDocDesc: '合同' },
  })

  it('按分录自己的借贷栏分区（借方红字仍在借方区），序号按区重排；金额在样本自己的借贷栏（不取对方分录的金额）', async () => {
    const inst = make()
    await inst.api.onEngineFilled({
      samples: [
        sample('fp-1'),
        sample('fp-2', { voucherNo: '0013', debitAmount: null, creditAmount: '300.00', pairing: paired(['1002', '银行存款', '200.00'], ['6111', '投资收益', '100.00']) }),
        sample('fp-3', { voucherNo: '0015', debitAmount: '-60.00', pairing: paired(['1002', '银行存款', '-60.00']) }),
      ],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.rows().map(r => [r.section, r.seq, r.voucherNo, r.counterAccount, r.debitAmount, r.creditAmount])).toEqual([
      ['debit', 1, '0012', '1002', 1000, 0],
      ['credit', 1, '0013', '1002', 0, 200],
      ['credit', 2, '0013', '6111', 0, 100],
      ['debit', 2, '0015', '1002', -60, 0],
    ])
    expect([inst.api.debitTotal.value, inst.api.creditTotal.value]).toEqual([940, 300])
  })

  it('父组件经 toJSON 保存：年审阶段预审行按读入版本写回', async () => {
    const inst = make([{
      id: 'p1', voucherNo: '0012', date: '2025-03-04', debitAmount: 1000, creditAmount: 0, section: 'debit', remark: '已核对',
      _gt: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' },
    }])
    await inst.api.voucherFillReady()
    inst.rows()[0].remark = '被改了'
    expect(inst.api.toJSON().rows[0]).toMatchObject({ id: 'p1', remark: '已核对' })
  })
})
