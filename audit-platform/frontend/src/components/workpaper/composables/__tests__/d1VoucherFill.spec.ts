/**
 * D1-13 应收票据凭证核对接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 10）
 *
 * - 抽凭两次、挂凭导入两次都不重复；抽凭与挂凭命中同一分录只留一行，来源记为两者；
 * - 行元数据 `_gt` 随行 JSON 落库，读回仍在（需求 4.1）；
 * - 映射：金额落在样本自己的借贷栏（贷方样本进 H 贷方金额），对方科目（后端配对）进 F 对方明细科目；
 * - 旧行（没有 `_gt`，凭证号记在票据号码里）同号同日同金额：不再插入，补写 `_gt`。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

import http from '@/utils/http'
import { __resetProjectAuditPhaseCache } from '@/composables/useProjectAuditPhase'
import { useD1SamplingVouching } from '../useD1SamplingVouching'
import type { ChecklistResponse } from '../useD1FormData'
import type { SamplePairing } from '../shared/voucherCheckFill'

const KEY = 'D1-sampling-vouching-rows'
const VK = JSON.stringify(['2025', '01', '2025-03-04', '记', '0012'])
const PAIRED: SamplePairing = {
  status: 'paired', basis: 'one_to_one',
  counterparts: [{ account_code: '1122', account_name: '应收账款', amount: '1000.00', line_fp: 'x' }], counterpart_summary: [],
}

function mk() {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const opts = {
    allResponses, wpId: ref('wp-1'), projectId: ref('proj-1'),
    saveImmediate: vi.fn(), saveDebouncedText: vi.fn(), isReadonly: ref(false),
  }
  return { allResponses, opts, api: useD1SamplingVouching(opts as never) }
}

const sample = (lineFp: string, over: Record<string, unknown> = {}) => ({
  voucherKey: VK, lineFp, voucherNo: '0012', voucherDate: '2025-03-04', summary: '收到承兑汇票',
  debitAmount: '1000.00', creditAmount: null,
  pairing: PAIRED,
  ...over,
})

const stored = (allResponses: Ref<Map<string, ChecklistResponse>>) => JSON.parse(String(allResponses.value.get(KEY)?.remark ?? '[]'))

beforeEach(() => {
  vi.clearAllMocks()
  __resetProjectAuditPhaseCache()
  vi.mocked(http.get).mockResolvedValue({ data: { current_audit_phase: 'final', interim_cutoff_date: null, can_edit: true } } as never)
})

describe('D1-13 抽凭 / 挂凭回填走共享函数', () => {
  it('抽凭两次不重复；挂凭导入同一分录不再插入、来源记为两者；`_gt` 随行落库', async () => {
    const { allResponses, api } = mk()
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { debitAmount: '20.00' })], phase: 'final', batchId: 'b-1' })
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { debitAmount: '20.00' })], phase: 'final', batchId: 'b-2' })
    expect(api.vouchingRows.value.map(r => r.seq)).toEqual([1, 2])
    await api.onAttachImported([sample('fp-1')])
    await api.onAttachImported([sample('fp-1')])
    const rows = stored(allResponses)
    expect(rows).toHaveLength(2)
    expect(rows[0]._gt).toMatchObject({ lfp: 'fp-1', ph: 'final', b: 'b-1', src: ['engine', 'attach'] })
    expect(rows[1]._gt).toMatchObject({ lfp: 'fp-2', src: ['engine'] })
  })

  it('读回（别的页签 / 在线编辑写回）后 `_gt` 还在', async () => {
    const { allResponses, api } = mk()
    await api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    const again = mk()
    again.allResponses.value.set(KEY, { ...(allResponses.value.get(KEY) as ChecklistResponse) })
    const reread = useD1SamplingVouching(again.opts as never)
    expect((reread.vouchingRows.value[0] as any)._gt).toMatchObject({ lfp: 'fp-1', vk: VK })
  })

  it('金额落在样本自己的借贷栏，对方科目进对方明细科目', async () => {
    const { api } = mk()
    await api.onEngineFilled({ samples: [sample('fp-c', { debitAmount: null, creditAmount: '300.00' })], phase: 'final' })
    const [row] = api.vouchingRows.value
    expect([row.amount, row.creditAmount, row.counterDetail, row.noteNo, row.voucherDate]).toEqual([0, 300, '1122 应收账款', '0012', '2025-03-04'])
  })

  it('旧行（没有 `_gt`）同号同日同金额：不再插入，补写 `_gt`', async () => {
    const { allResponses, opts } = mk()
    allResponses.value.set(KEY, {
      item_id: KEY, conclusion: null,
      remark: JSON.stringify([{ id: 'old', seq: 1, noteNo: '0012', maturityDate: '2025-03-04', amount: 1000, existenceCheck: '已核实' }]),
    } as ChecklistResponse)
    const api = useD1SamplingVouching(opts as never)
    await api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    expect(api.vouchingRows.value).toHaveLength(1)
    expect(api.vouchingRows.value[0]).toMatchObject({ id: 'old', existenceCheck: '已核实' })
    expect((api.vouchingRows.value[0] as any)._gt).toMatchObject({ lfp: 'fp-1', ph: null, src: ['manual', 'engine'] })
  })
})
