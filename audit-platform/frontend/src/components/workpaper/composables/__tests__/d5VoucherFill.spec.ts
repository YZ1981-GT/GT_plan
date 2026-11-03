/**
 * D5-2 应收款项融资明细表接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 10）
 *
 * - 一个样本一行；抽凭两次、挂凭导入两次都不重复；`_gt` 随行 JSON 落库（回填立即保存）；
 * - 映射：明细项目 = 对方科目（后端配对），借方记本期增加、贷方记本期减少，备注「抽凭: 凭证号」；
 * - 「替换本阶段抽凭行」只删本阶段抽凭填入的行（余额表导入等没有 `_gt` 的行不动），已录入调整的先确认；
 * - 撤销按批次删行；年审阶段预审行改、删都不生效，保存时按读入版本写回；
 * - 旧行（备注「抽凭: 凭证号」、没有 `_gt`）同号同金额：不再插入，补写 `_gt`。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref, type Ref } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

import http from '@/utils/http'
import { ElMessageBox } from 'element-plus'
import { __resetProjectAuditPhaseCache } from '@/composables/useProjectAuditPhase'
import { createEmptyRow, useD5Detail } from '../useD5Detail'
import type { ChecklistResponse } from '../useD5FormData'
import type { SamplePairing } from '../shared/voucherCheckFill'

const KEY = 'D5-2-rows'
const VK = JSON.stringify(['2025', '06', '2025-06-15', '记', '0007'])
const PAIRED: SamplePairing = {
  status: 'paired', basis: 'one_to_one',
  counterparts: [{ account_code: '1121', account_name: '应收票据', amount: '1000.00', line_fp: 'x' }],
  counterpart_summary: [],
}

const sample = (lineFp: string, over: Record<string, unknown> = {}) => ({
  voucherKey: VK, lineFp, voucherNo: '0007', voucherDate: '2025-06-15', summary: '票据贴现',
  debitAmount: '1000.00', creditAmount: null, pairing: PAIRED, ...over,
})

const wrappers: VueWrapper[] = []

function mk(seed?: unknown[]) {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<Map<string, ChecklistResponse>>
  const put = (remark: string): void => {
    allResponses.value.set(KEY, { item_id: KEY, conclusion: null, remark } as ChecklistResponse)
  }
  if (seed) put(JSON.stringify(seed))
  const saveImmediate = vi.fn(async (_id: string, data: Partial<ChecklistResponse>) => put(String(data.remark ?? '')))
  const debouncedSave = vi.fn((_id: string, data: Partial<ChecklistResponse>) => put(String(data.remark ?? '')))
  let api!: ReturnType<typeof useD5Detail>
  wrappers.push(mount(defineComponent({
    setup() {
      api = useD5Detail({
        allResponses, wpId: ref('wp-5'), projectId: ref('proj-1'), saveImmediate, debouncedSave, isReadonly: ref(false),
      })
      return () => h('div')
    },
  })))
  return { api, allResponses, saveImmediate, debouncedSave }
}

const stored = (allResponses: Ref<Map<string, ChecklistResponse>>) => JSON.parse(String(allResponses.value.get(KEY)?.remark ?? '[]'))
const remarks = (rows: Array<{ remark: string }>) => rows.map(r => r.remark)

beforeEach(() => {
  vi.clearAllMocks()
  __resetProjectAuditPhaseCache()
  vi.mocked(http.get).mockResolvedValue({ data: { current_audit_phase: 'final', interim_cutoff_date: null, can_edit: true } } as never)
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
})

afterEach(() => {
  while (wrappers.length) wrappers.pop()?.unmount()
})

describe('D5-2 抽凭 / 挂凭回填走共享函数', () => {
  it('抽凭两次、挂凭导入两次都不重复；`_gt` 随行落库且立即保存', async () => {
    const { api, allResponses, saveImmediate } = mk()
    const batch = [sample('fp-1'), sample('fp-2', { voucherNo: '0008', debitAmount: null, creditAmount: '20.00' })]
    await api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-1' })
    await api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-2' })
    await api.onAttachImported([sample('fp-1')])
    await api.onAttachImported([sample('fp-1')])
    expect(remarks(api.rows.value)).toEqual(['抽凭: 0007', '抽凭: 0008'])
    const rows = stored(allResponses)
    expect(rows[0]._gt).toMatchObject({ vk: VK, lfp: 'fp-1', ph: 'final', b: 'b-1', src: ['engine', 'attach'] })
    expect(saveImmediate).toHaveBeenCalledTimes(4)
  })

  it('映射：明细项目 = 对方科目，借方记本期增加、贷方记本期减少，期末余额随之重算', async () => {
    const { api } = mk()
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0008', debitAmount: null, creditAmount: '20.00' })], phase: 'final' })
    const [a, b] = api.rows.value
    expect([a.category, a.itemName, a.periodIncrease, a.periodDecrease, a.endBalance]).toEqual(['应收票据', '应收票据', 1000, 0, 1000])
    expect([b.periodIncrease, b.periodDecrease, b.endBalance]).toEqual([0, 20, -20])
  })

  it('「替换本阶段抽凭行」只删本阶段抽凭填入的行；余额表导入行不动；已录入调整的先确认', async () => {
    const aux = { ...createEmptyRow(), rowId: 'aux-1', category: '应收账款', itemName: '客户甲', priorUnadjusted: 50 }
    const { api } = mk([aux])
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0008' })], phase: 'final', batchId: 'b-1' })
    api.updateCell(api.rows.value[1].rowId, 'endAje', 5)
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel' as never)
    const cancelled = await api.onEngineFilled({ samples: [sample('fp-3', { voucherNo: '0009' })], phase: 'final', fillMode: 'replace', batchId: 'b-2' })
    expect(cancelled.cancelled).toBe(true)
    expect(api.rows.value).toHaveLength(3)
    await api.onEngineFilled({ samples: [sample('fp-3', { voucherNo: '0009' })], phase: 'final', fillMode: 'replace', batchId: 'b-2' })
    expect(api.rows.value.map(r => r.rowId === 'aux-1' ? 'aux' : r.remark)).toEqual(['aux', '抽凭: 0009'])
  })

  it('撤销按批次删行：同时来自挂凭的保留', async () => {
    const { api } = mk()
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0008' })], phase: 'final', batchId: 'b-1' })
    await api.onAttachImported([sample('fp-2', { voucherNo: '0008' })])
    expect(await api.onUndoRequest({ logId: 'l-1', batchId: 'b-1', performUndo: async () => true })).toBe(true)
    expect(remarks(api.rows.value)).toEqual(['抽凭: 0008'])
    expect((api.rows.value[0] as any)._gt).toMatchObject({ b: null, src: ['attach'] })
  })

  it('年审阶段预审行只读：改、删都不生效；绕过界面改了内存，保存时按读入版本写回', async () => {
    const prelim = {
      ...createEmptyRow(), rowId: 'p1', category: '应收票据', itemName: '应收票据', periodIncrease: 1000, endBalance: 1000,
      endUnadjusted: 1000, endAudited: 1000, remark: '抽凭: 0007',
      _gt: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' },
    }
    const { api, allResponses, debouncedSave } = mk([prelim])
    await api.voucherFillReady()
    expect(api.isVoucherRowLocked(api.rows.value[0])).toBe(true)
    expect(api.voucherRowClass({ row: api.rows.value[0] })).toBe('gt-row-locked')
    api.updateCell('p1', 'endAje', 9)
    api.removeRow('p1')
    expect(api.rows.value.map(r => [r.rowId, r.endAje])).toEqual([['p1', 0]])
    expect(debouncedSave).not.toHaveBeenCalled()
    api.rows.value[0].endAje = 7
    api.addRow()
    expect(stored(allResponses)[0]).toMatchObject({ rowId: 'p1', endAje: 0 })
  })

  it('旧行（备注「抽凭: 凭证号」、没有 `_gt`）同号同金额：不再插入，补写 `_gt`，已录入的调整保留', async () => {
    const old = { ...createEmptyRow(), rowId: 'old', category: '应收票据', itemName: '旧', periodIncrease: 1000, endAje: 3, remark: '抽凭: 0007' }
    const { api } = mk([old])
    await api.onEngineFilled({ samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    expect(api.rows.value).toHaveLength(1)
    expect(api.rows.value[0]).toMatchObject({ rowId: 'old', itemName: '旧', endAje: 3 })
    expect((api.rows.value[0] as any)._gt).toMatchObject({ lfp: 'fp-1', ph: null, src: ['manual', 'engine'] })
  })
})
