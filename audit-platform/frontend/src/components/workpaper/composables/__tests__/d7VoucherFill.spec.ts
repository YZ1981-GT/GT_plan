/**
 * D7-7 合同负债凭证检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 10）
 *
 * - 抽凭进本期增减变动；抽凭两次、挂凭导入两次都不重复；`_gt` 随行 JSON 落库；挂凭导入按凭证日期分区；
 * - 映射：客户名称取辅助明细账往来单位（原宿主写的是对方科目），对方科目 / 明细取后端配对，金额在样本自己的借贷栏；
 * - 「替换本阶段抽凭行」只删本期增减变动里本阶段抽凭填入的行；撤销按批次删行；
 * - 年审阶段预审行改、删都不生效，保存时按读入版本写回；旧行同号同日同金额不再插入。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

import http from '@/utils/http'
import { ElMessageBox } from 'element-plus'
import { __resetProjectAuditPhaseCache } from '@/composables/useProjectAuditPhase'
import { useD7VoucherCheck } from '../useD7VoucherCheck'
import type { ChecklistResponse } from '../useD7FormData'
import type { SamplePairing } from '../shared/voucherCheckFill'

const PERIOD = 'D7-7-period-rows'
const POST = 'D7-7-post-rows'
const VK = JSON.stringify(['2025', '06', '2025-06-15', '记', '0007'])
const PAIRED: SamplePairing = {
  status: 'paired', basis: 'one_to_one',
  counterparts: [{ account_code: '1002', account_name: '银行存款', amount: '1000.00', line_fp: 'x' }],
  counterpart_summary: [],
}

const sample = (lineFp: string, over: Record<string, unknown> = {}) => ({
  voucherKey: VK, lineFp, voucherNo: '0007', voucherDate: '2025-06-15', summary: '预收合同款',
  debitAmount: null, creditAmount: '1000.00', pairing: PAIRED,
  partyName: '客户甲', partyAuxType: '客户', partyAmbiguous: false, ...over,
})

const blank = (over: Record<string, unknown>) => ({
  rowId: 'r', customerName: '', date: '', voucherNo: '', businessContent: '', counterAccount: '', counterDetail: '',
  debitAmount: 0, creditAmount: 0, supportDocs: '', checkItems: [false, false, false, false, false],
  indexRef: '', isAbnormal: false, remark: '', ...over,
})

function mk(seed: { period?: unknown[]; post?: unknown[] } = {}) {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const put = (key: string, remark: string) => {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark } as ChecklistResponse)
  }
  if (seed.period) put(PERIOD, JSON.stringify(seed.period))
  if (seed.post) put(POST, JSON.stringify(seed.post))
  const saveImmediate = vi.fn(async (id: string, data: Partial<ChecklistResponse>) => put(id, String(data.remark ?? '')))
  const debouncedSave = vi.fn((id: string, data: Partial<ChecklistResponse>) => put(id, String(data.remark ?? '')))
  const api = useD7VoucherCheck({
    allResponses, wpId: ref('wp-7'), projectId: ref('proj-1'), saveImmediate, debouncedSave,
    isReadonly: false, bsDate: () => '2025-12-31',
  })
  return { api, allResponses, saveImmediate, debouncedSave }
}

const stored = (allResponses: Ref<Map<string, ChecklistResponse>>, key: string) => JSON.parse(String(allResponses.value.get(key)?.remark ?? '[]'))
const nos = (rows: Array<{ voucherNo: string }>) => rows.map(r => r.voucherNo)

beforeEach(() => {
  vi.clearAllMocks()
  __resetProjectAuditPhaseCache()
  vi.mocked(http.get).mockResolvedValue({ data: { current_audit_phase: 'final', interim_cutoff_date: null, can_edit: true } } as never)
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
})

describe('D7-7 抽凭 / 挂凭回填走共享函数', () => {
  it('抽凭两次、挂凭导入两次都不重复；`_gt` 随行落库；挂凭导入按凭证日期分区', async () => {
    const { api, allResponses } = mk()
    const batch = [sample('fp-1'), sample('fp-2', { voucherNo: '0008', creditAmount: '20.00' })]
    await api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-1' }, { tables: ['period'] })
    await api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-2' }, { tables: ['period'] })
    await api.onAttachImported([sample('fp-1')])
    await api.onAttachImported([sample('fp-1'), sample('fp-9', { voucherNo: '0101', voucherDate: '2026-01-10', debitAmount: '300.00', creditAmount: null })])
    await nextTick()
    expect(nos(api.periodChangeRows.value)).toEqual(['0007', '0008'])
    expect(nos(api.postTransferRows.value)).toEqual(['0101'])
    // 期后结转区只有借方金额（上游 oo-writeback-template-parity-closure R3 批 B2）：借方 300 落借方栏，没有贷方栏，
    // 落库的行也不带 creditAmount（与该区旧行载入即迁移、保存不再带 creditAmount 同口径）
    expect([api.postTransferRows.value[0].debitAmount, api.postTransferRows.value[0].creditAmount]).toEqual([300, undefined])
    expect(stored(allResponses, POST).map((r: Record<string, unknown>) => ['creditAmount' in r, r.debitAmount])).toEqual([[false, 300]])
    expect(stored(allResponses, PERIOD)[0]._gt).toMatchObject({ vk: VK, lfp: 'fp-1', ph: 'final', b: 'b-1', src: ['engine', 'attach'] })
  })

  it('期后的贷方分录不是结转：挂凭导入留在本期增减变动区，金额照记（期后结转区没有贷方栏，放过去会丢）', async () => {
    const { api } = mk()
    await api.onAttachImported([sample('fp-10', { voucherNo: '0102', voucherDate: '2026-01-12' })])
    await nextTick()
    expect(nos(api.postTransferRows.value)).toEqual([])
    expect(api.periodChangeRows.value.map(r => [r.voucherNo, r.creditAmount])).toEqual([['0102', 1000]])
  })

  it('映射：客户名称取往来单位，对方科目 / 明细取后端配对，金额在样本自己的借贷栏', async () => {
    const { api } = mk()
    await api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final' }, { tables: ['period'] })
    const [r] = api.periodChangeRows.value
    expect([r.customerName, r.counterAccount, r.counterDetail, r.debitAmount, r.creditAmount, r.businessContent])
      .toEqual(['客户甲', '1002', '银行存款', 0, 1000, '预收合同款'])
  })

  it('「替换本阶段抽凭行」只删本期增减变动里本阶段抽凭填入的行；撤销按批次删行，同时来自挂凭的保留', async () => {
    const { api } = mk({ period: [blank({ rowId: 'm1', voucherNo: '手-1' })] })
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0008' })], phase: 'final', batchId: 'b-1' }, { tables: ['period'] })
    await api.onAttachImported([sample('fp-2', { voucherNo: '0008' })])
    await api.onEngineFilled({ samples: [sample('fp-3', { voucherNo: '0009' })], phase: 'final', fillMode: 'replace', batchId: 'b-2' }, { tables: ['period'] })
    await nextTick()
    expect(nos(api.periodChangeRows.value)).toEqual(['手-1', '0008', '0009'])
    expect(await api.onUndoRequest({ logId: 'l-2', batchId: 'b-2', performUndo: async () => true })).toBe(true)
    await nextTick()
    expect(nos(api.periodChangeRows.value)).toEqual(['手-1', '0008'])
  })

  it('年审阶段预审行只读：改、删都不生效；绕过界面改了内存，保存时按读入版本写回', async () => {
    const prelim = blank({
      rowId: 'p1', voucherNo: '0007', date: '2025-06-15', creditAmount: 1000, remark: '已核对',
      _gt: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' },
    })
    const { api, debouncedSave } = mk({ period: [prelim] })
    await api.voucherFillReady()
    expect(api.voucherRowClass({ row: api.periodChangeRows.value[0] })).toBe('gt-row-locked')
    api.updateCell('period', 'p1', 'remark', '改了')
    api.removeSample('period', 'p1')
    expect(api.periodChangeRows.value.map(r => [r.rowId, r.remark])).toEqual([['p1', '已核对']])
    const periodSaves = () => debouncedSave.mock.calls.filter(c => c[0] === PERIOD)
    expect(periodSaves()).toHaveLength(0)
    api.periodChangeRows.value[0].remark = '被改了'
    api.addSample('period')
    expect(JSON.parse(String(periodSaves().at(-1)?.[1].remark))[0]).toMatchObject({ rowId: 'p1', remark: '已核对' })
  })

  it('旧行（没有 `_gt`）同号同日同金额：不再插入，补写 `_gt`，核对结果保留', async () => {
    const old = blank({ rowId: 'old', voucherNo: '0007', date: '2025-06-15', creditAmount: 1000, checkItems: [true, false, false, false, false] })
    const { api } = mk({ period: [old] })
    await api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' }, { tables: ['period'] })
    await nextTick()
    expect(api.periodChangeRows.value).toHaveLength(1)
    expect(api.periodChangeRows.value[0]).toMatchObject({ rowId: 'old', checkItems: [true, false, false, false, false] })
    expect((api.periodChangeRows.value[0] as any)._gt).toMatchObject({ lfp: 'fp-1', ph: null, src: ['manual', 'engine'] })
  })
})
