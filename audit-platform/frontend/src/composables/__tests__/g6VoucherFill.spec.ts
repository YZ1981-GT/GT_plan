/**
 * G6-15 其他债权投资凭证检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * 通用五条用例见 voucherFillHostHarness（宿主表格 v-model 原地改行，组合式函数唯一的改行入口是删行 ⇒ 用它验只读；
 * 原地改了内存靠保存时按读入版本写回兜底）；另验：本期 / 期后两张表 —— 期后表只收资产负债表日之后的凭证、
 * 行上记抽样方法与选样类别、替换只删本阶段抽凭行（手工行保留；原实现清空整个期间）；同一分录按对方科目
 * 展开的几行金额相同也不算重复样本。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, watch } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { ElMessage } from 'element-plus'
import { useG6EclVoucherCheck } from '../useG6EclVoucherCheck'
import type { VoucherCheckRow } from '@/components/workpaper/composables/useG6EclFormData'
import {
  paired, resetVoucherFillMocks, sample, voucherFillHostCases, type HostInstance,
} from '@/components/workpaper/composables/__tests__/voucherFillHostHarness'

type G6Api = ReturnType<typeof useG6EclVoucherCheck>

function make(seed?: unknown[]): HostInstance<VoucherCheckRow> & { api: G6Api } {
  const api = useG6EclVoucherCheck(ref('wp-6'), ref('proj-1'), ref({ bsDate: '2025-12-31' }), { readonly: false })
  api.loadRows((seed ?? []) as any[])
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

describe('G6-15 抽凭 / 挂凭回填走共享函数', () => {
  voucherFillHostCases<VoucherCheckRow>({
    make,
    idKey: 'id',
    view: r => [r.voucherNo, [r.counterAccount, r.detailAccount].filter(Boolean).join(' '), r.debitAmount, r.creditAmount],
    edit: (inst, id) => (inst.api as unknown as G6Api).removeRow(id),
    editKey: 'remark',
    manualRow: { id: 'm1', voucherNo: '手-1', period: 'occurrence' },
    oldRow: { voucherNo: '0012', date: '2025-03-04', debitAmount: 1000, creditAmount: 0, supportingDoc: '合同', period: 'occurrence' },
    oldRowKept: { supportingDoc: '合同' },
  })

  it('期后表只收资产负债表日之后的凭证；行上记抽样方法与选样类别；替换只删本阶段抽凭行、手工行保留', async () => {
    const inst = make([{ id: 'm1', voucherNo: '手-9', date: '2026-01-02', debitAmount: 5, period: 'post' }])
    await inst.api.onEngineFilled({
      samples: [
        sample('fp-1', { voucherNo: 'OLD', voucherDate: '2025-12-01' }),
        sample('fp-2', { voucherNo: 'PZ-1', voucherDate: '2026-01-05', isHighValue: true }),
      ],
      phase: 'final', batchId: 'b-1', method: 'systematic',
    }, 'post')
    expect(vi.mocked(ElMessage.warning)).toHaveBeenCalledWith(expect.stringContaining('已剔除截止日前 1 笔'))
    expect(inst.api.postPeriodRows.value.map(r => [r.voucherNo, r.samplingMethod, r.selectionCategory]))
      .toEqual([['手-9', '', ''], ['PZ-1', 'systematic', 'specific']])
    expect(inst.api.occurrenceRows.value).toHaveLength(0)
    await inst.api.onEngineFilled({
      samples: [sample('fp-3', { voucherNo: 'PZ-2', voucherDate: '2026-02-01' })], phase: 'final', fillMode: 'replace', batchId: 'b-2',
    }, 'post')
    expect(inst.api.postPeriodRows.value.map(r => [r.seq, r.voucherNo])).toEqual([[1, '手-9'], [2, 'PZ-2']])
  })

  it('同一分录按对方科目展开的几行金额相同也不算重复样本', async () => {
    const inst = make()
    await inst.api.onEngineFilled({
      samples: [sample('fp-1', {
        debitAmount: null, creditAmount: '300.00', pairing: paired(['1002', '银行存款', '150.00'], ['6111', '投资收益', '150.00']),
      })],
      phase: 'final', batchId: 'b-1',
    })
    expect(inst.api.occurrenceRows.value.map(r => [r.counterAccount, r.creditAmount])).toEqual([['1002', 150], ['6111', 150]])
    expect(inst.api.duplicateRows.value).toHaveLength(0)
  })
})
