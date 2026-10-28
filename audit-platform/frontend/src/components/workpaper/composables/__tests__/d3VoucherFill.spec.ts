/**
 * D3-7 预收账款凭证检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 10）
 *
 * - 抽凭两次、挂凭导入两次都不重复；同一分录只留一行，来源记为两者；`_gt` 随行 JSON 落库；
 * - 抽凭进用户选的区块，已在另一区块的分录不重复插入；挂凭导入按凭证日期分区；
 * - 「替换本阶段抽凭行」只删所选区块里本阶段抽凭填入的行；撤销按批次删行；
 * - 年审阶段预审行改、删、OCR、自动标记跨期都不生效，保存时按读入版本写回；
 * - 旧行（没有 `_gt`）同号同日同金额：不再插入，补写 `_gt`。
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
import { useD3VoucherCheck } from '../useD3VoucherCheck'
import type { ChecklistResponse } from '../useD3FormData'
import type { SamplePairing } from '../shared/voucherCheckFill'

const CUR = 'D3-vc-current-rows'
const POST = 'D3-vc-post-rows'
const VK = JSON.stringify(['2025', '06', '2025-06-15', '记', '0007'])
const PAIRED: SamplePairing = {
  status: 'paired', basis: 'one_to_one',
  counterparts: [{ account_code: '1002', account_name: '银行存款', amount: '1000.00', line_fp: 'x' }],
  counterpart_summary: [],
}

const sample = (lineFp: string, over: Record<string, unknown> = {}) => ({
  voucherKey: VK, lineFp, voucherNo: '0007', voucherDate: '2025-06-15', summary: '预收货款',
  debitAmount: null, creditAmount: '1000.00', pairing: PAIRED, ...over,
})

const blank = (over: Record<string, unknown>) => ({
  rowId: 'r', customerName: '', date: '', voucherNo: '', businessContent: '', counterAccount: '',
  counterDetailAccount: '', debitAmount: 0, creditAmount: 0, supportingDoc: '',
  checkItems: [false, false, false, false, false], indexRef: '', isAbnormal: '', remark: '', ...over,
})

function mk(seed: { current?: unknown[]; post?: unknown[] } = {}) {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const put = (key: string, remark: string) => {
    allResponses.value.set(key, { ...(allResponses.value.get(key) ?? {}), item_id: key, conclusion: null, remark } as ChecklistResponse)
  }
  if (seed.current) put(CUR, JSON.stringify(seed.current))
  if (seed.post) put(POST, JSON.stringify(seed.post))
  // 保存桥照真实宿主：写回 allResponses（watch 读回）
  const saveImmediate = vi.fn(async (itemId: string, data: Partial<ChecklistResponse>) => put(itemId, String(data.remark ?? '')))
  const debouncedSave = vi.fn((itemId: string, data: Partial<ChecklistResponse>) => put(itemId, String(data.remark ?? '')))
  const api = useD3VoucherCheck({
    allResponses, wpId: ref('wp-3'), projectId: ref('proj-1'),
    saveImmediate, debouncedSave, isReadonly: ref(false), bsDate: () => '2025-12-31',
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

describe('D3-7 抽凭 / 挂凭回填走共享函数', () => {
  it('抽凭两次、挂凭导入两次都不重复；同一分录只留一行、来源记为两者；`_gt` 随行落库', async () => {
    const { api, allResponses, saveImmediate } = mk()
    const batch = [sample('fp-1'), sample('fp-2', { voucherNo: '0008', creditAmount: '20.00' })]
    await api.onEngineFilled({ samples: batch, phase: 'final', fillMode: 'append', batchId: 'b-1' }, { tables: ['current'] })
    await api.onEngineFilled({ samples: batch, phase: 'final', fillMode: 'append', batchId: 'b-2' }, { tables: ['current'] })
    await api.onAttachImported([sample('fp-1')])
    await api.onAttachImported([sample('fp-1')])
    await nextTick()
    expect(nos(api.currentChangeRows.value)).toEqual(['0007', '0008'])
    expect(api.postPeriodRows.value).toHaveLength(0)
    const rows = stored(allResponses, CUR)
    expect(rows[0]._gt).toMatchObject({ vk: VK, lfp: 'fp-1', ph: 'final', b: 'b-1', src: ['engine', 'attach'] })
    expect(rows[1]._gt).toMatchObject({ lfp: 'fp-2', src: ['engine'] })
    // 回填立即落库两区块（不走防抖）
    expect(saveImmediate.mock.calls.map(c => c[0])).toEqual(expect.arrayContaining([CUR, POST]))
  })

  it('抽凭进所选区块；已在另一区块的分录不重复插入；挂凭导入按凭证日期分区', async () => {
    const { api } = mk()
    await api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final' }, { tables: ['current'] })
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-3', { voucherNo: '0101' })], phase: 'final' }, { tables: ['postPeriod'] })
    await api.onAttachImported([sample('fp-9', { voucherNo: '0201', voucherDate: '2026-01-05' })])
    await nextTick()
    expect(nos(api.currentChangeRows.value)).toEqual(['0007'])
    expect(nos(api.postPeriodRows.value)).toEqual(['0101', '0201'])
  })

  it('「替换本阶段抽凭行」只删所选区块里本阶段抽凭填入的行，手工行与另一区块不动', async () => {
    const { api } = mk({ current: [blank({ rowId: 'm1', voucherNo: '手-1' })] })
    await api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' }, { tables: ['current'] })
    await api.onEngineFilled({ samples: [sample('fp-2', { voucherNo: '0008' })], phase: 'final', batchId: 'b-1' }, { tables: ['postPeriod'] })
    await api.onEngineFilled({ samples: [sample('fp-4', { voucherNo: '0010' })], phase: 'final', fillMode: 'replace', batchId: 'b-2' }, { tables: ['current'] })
    await nextTick()
    expect(nos(api.currentChangeRows.value)).toEqual(['手-1', '0010'])
    expect(nos(api.postPeriodRows.value)).toEqual(['0008'])
  })

  it('映射：贷方样本进贷方栏、对方科目来自后端配对；配不上一行「多科目」', async () => {
    const { api } = mk()
    const multi: SamplePairing = { status: 'multi', basis: null, counterparts: [], counterpart_summary: [] }
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0008', pairing: multi })], phase: 'final' }, { tables: ['current'] })
    const [a, b] = api.currentChangeRows.value
    expect([a.counterAccount, a.counterDetailAccount, a.debitAmount, a.creditAmount, a.source]).toEqual(['1002', '银行存款', undefined, 1000, '抽凭'])
    expect([b.counterAccount, b.counterDetailAccount]).toEqual(['多科目', ''])
  })

  it('撤销按批次删行：同时来自挂凭的保留；后端撤销失败不删', async () => {
    const { api } = mk()
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0008' })], phase: 'final', batchId: 'b-1' }, { tables: ['current'] })
    await api.onAttachImported([sample('fp-2', { voucherNo: '0008' })])
    expect(await api.onUndoRequest({ logId: 'l-1', batchId: 'b-1', performUndo: async () => false })).toBe(false)
    expect(api.currentChangeRows.value).toHaveLength(2)
    expect(await api.onUndoRequest({ logId: 'l-1', batchId: 'b-1', performUndo: async () => true })).toBe(true)
    await nextTick()
    expect(nos(api.currentChangeRows.value)).toEqual(['0008'])
    expect((api.currentChangeRows.value[0] as any)._gt).toMatchObject({ b: null, src: ['attach'] })
  })

  it('年审阶段预审行只读：改、删、自动标记跨期都不生效；绕过界面改了内存，保存时按读入版本写回', async () => {
    const lock = { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' }
    const prelim = blank({ rowId: 'p1', voucherNo: '0007', date: '2025-06-15', creditAmount: 1000, remark: '已核对', _gt: lock })
    const prelimPost = blank({ rowId: 'p2', voucherNo: '0101', date: '2025-12-20', creditAmount: 5, _gt: { ...lock, lfp: 'fp-2' } })
    const { api, debouncedSave } = mk({ current: [prelim], post: [prelimPost] })
    await api.voucherFillReady()
    const row = api.currentChangeRows.value[0]
    expect(api.isVoucherRowLocked(row)).toBe(true)
    expect(api.voucherRowClass({ row })).toBe('gt-row-locked')
    api.updateCell('current', 'p1', 'remark', '改了')
    api.updateRow('current', 'p1', { remark: '又改了' })
    api.removeSample('current', 'p1')
    api.autoMarkCrossPeriod('2025-12-31')
    expect(api.currentChangeRows.value.map(r => [r.rowId, r.remark])).toEqual([['p1', '已核对']])
    expect(api.postPeriodRows.value[0].isAbnormal).toBe('')
    expect(debouncedSave).not.toHaveBeenCalled()
    api.currentChangeRows.value[0].remark = '被改了'
    api.addSample('current')
    const saved = JSON.parse(String(debouncedSave.mock.calls.at(-1)?.[1].remark))
    expect(saved[0]).toMatchObject({ rowId: 'p1', remark: '已核对' })
  })

  it('旧行（没有 `_gt`）同号同日同金额：不再插入，补写 `_gt`，核对结果保留', async () => {
    const old = blank({ rowId: 'old', voucherNo: '0007', date: '2025-06-15', creditAmount: 1000, checkItems: [true, false, false, false, false] })
    const { api } = mk({ current: [old] })
    await api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' }, { tables: ['current'] })
    await nextTick()
    expect(api.currentChangeRows.value).toHaveLength(1)
    expect(api.currentChangeRows.value[0]).toMatchObject({ rowId: 'old', checkItems: [true, false, false, false, false] })
    expect((api.currentChangeRows.value[0] as any)._gt).toMatchObject({ lfp: 'fp-1', ph: null, src: ['manual', 'engine'] })
  })
})
