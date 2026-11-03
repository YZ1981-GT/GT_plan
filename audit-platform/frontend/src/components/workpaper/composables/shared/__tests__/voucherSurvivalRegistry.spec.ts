/**
 * 预审样本存续核对前端注册表（任务 17，需求 8）。
 *
 * 覆盖：lfp 请求从元数据解析、无指纹旧行显式计数；一对多展开按 lfp 去重；
 * useVoucherCheckFill 在真实 Vue 注入上下文里注册表 refs，核对结果写 `_gt.sv` 并走宿主 persist；
 * 同 lfp 多行一起确认、未确认数幂等重算；卸载清理。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, provide, ref } from 'vue'
import { mount } from '@vue/test-utils'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

import { WorkpaperRuntimeContextKey } from '../../useWorkpaperScaffold'
import { survivalRequestOf, useVoucherCheckFill, type VoucherRowMeta } from '../voucherCheckFill'
import {
  __resetVoucherSurvivalRegistry,
  acknowledgeVoucherSurvivalRow,
  applyVoucherSurvivalResult,
  collectVoucherSurvivalRows,
  type SurvivalCheckWire,
} from '../voucherSurvivalRegistry'

const VK = JSON.stringify(['2025', 'T17', '2025-12-20', 'SV', 'U-1'])
const FP = JSON.stringify(['2025', 'T17', '2025-12-20', 'SV', 'U-1', '1001', 'D', '100.00', 0])

interface Row {
  id: string
  voucherNo: string
  voucherDate: string
  debitAmount: string
  creditAmount: null
  counterpart: string
  _gt: VoucherRowMeta
}

function row(id: string, over: Partial<VoucherRowMeta> = {}): Row {
  return {
    id, voucherNo: 'U-1', voucherDate: '2025-12-20', debitAmount: '100.00', creditAmount: null, counterpart: '2001',
    _gt: { vk: VK, lfp: FP, ph: 'preliminary', b: 'batch-1', src: ['engine'], pr: 'paired', cp: id, ...over },
  }
}

const RESULT: SurvivalCheckWire = {
  check_id: 'check-1', dataset_id: 'dataset-new', checked_by: 'user-1', checked_at: '2026-10-29T00:00:00Z',
  total: 1, unchanged: 0, modified: 1, renumbered: 0, deleted: 0, unacked: 1,
  results: [{ row_key: FP, lfp: FP, status: 'modified', acknowledged: false,
    current_voucher: { voucher_key: VK, line_count: 2, lines: [] } }],
}

afterEach(() => __resetVoucherSurvivalRegistry())

describe('survivalRequestOf', () => {
  it('科目 / 借贷栏 / 金额只从 lfp 解析，旧确认随请求带上', () => {
    const r = row('a', { sv: { status: 'modified', datasetId: 'ds-1', ackAt: '2026-10-28' } })
    expect(survivalRequestOf(r)).toEqual({
      row_key: FP, lfp: FP, vk: VK, account_code: '1001', side: 'D', amount: '100.00',
      previous_dataset_id: 'ds-1', previous_status: 'modified', acknowledged: true,
    })
  })

  it('非预审、缺 lfp、lfp 与 vk 不同、非法栏位都不给请求', () => {
    expect(survivalRequestOf(row('a', { ph: 'final' }))).toBeNull()
    expect(survivalRequestOf(row('a', { lfp: null }))).toBeNull()
    expect(survivalRequestOf(row('a', { vk: JSON.stringify(['2025', 'T17', '2025-12-20', 'SV', 'OTHER']) }))).toBeNull()
    const bad = JSON.stringify(['2025', 'T17', '2025-12-20', 'SV', 'U-1', '1001', 'debit', '100.00', 0])
    expect(survivalRequestOf(row('a', { lfp: bad }))).toBeNull()
  })
})

describe('useVoucherCheckFill × registry', () => {
  function mountedHost(initial: Row[]) {
    const rows = ref(initial)
    const persist = vi.fn().mockResolvedValue(undefined)
    const hostRef = ref<any>(null)
    const Host = defineComponent({
      setup(_, { expose }) {
        const fill = useVoucherCheckFill<Row>({
          projectId: 'project-1', tables: rows, persist,
          mapSampleToRow: () => row('mapped'),
        })
        fill.markLoaded()
        expose({ rows, fill })
        return () => h('div')
      },
    })
    const Parent = defineComponent({
      setup() {
        provide(WorkpaperRuntimeContextKey, {
          wpId: ref('wp-1'), projectId: ref('project-1'), wpCode: ref('J1'), year: ref(2025), readonly: ref(false),
        } as any)
        return () => h(Host, { ref: hostRef })
      },
    })
    const wrapper = mount(Parent)
    return { wrapper, rows, persist, hostRef }
  }

  it('注册、按源 lfp 去重、无指纹预审旧行不从分母静默消失', async () => {
    const unsupported = row('old', { lfp: null, vk: null })
    const { wrapper } = mountedHost([row('cp-1'), row('cp-2'), unsupported])
    await nextTick()
    const got = collectVoucherSurvivalRows('wp-1')
    expect(got.rows).toHaveLength(1)
    expect(got.preliminaryCount).toBe(3)
    expect(got.unsupportedCount).toBe(1)
    wrapper.unmount()
    expect(collectVoucherSurvivalRows('wp-1')).toEqual({ rows: [], preliminaryCount: 0, unsupportedCount: 0 })
  })

  it('结果写回全部同 lfp 展开行，存紧凑明细并只调一次宿主 persist', async () => {
    const { wrapper, rows, persist } = mountedHost([row('cp-1'), row('cp-2')])
    await nextTick()
    await applyVoucherSurvivalResult('wp-1', RESULT)
    expect(rows.value.map(r => r._gt.sv)).toEqual([
      expect.objectContaining({ status: 'modified', datasetId: 'dataset-new', checkId: 'check-1',
        detail: '原凭证仍在，但分录内容已变化（当前凭证 2 条分录）' }),
      expect.objectContaining({ status: 'modified', datasetId: 'dataset-new', checkId: 'check-1' }),
    ])
    expect(persist).toHaveBeenCalledTimes(1)

    const ack = await acknowledgeVoucherSurvivalRow('wp-1', FP, 'user-1', '2026-10-29T01:00:00Z')
    expect(ack).toEqual({ checkId: 'check-1', datasetId: 'dataset-new', unacked: 0 })
    expect(rows.value.every(r => (r._gt.sv as any).ackAt === '2026-10-29T01:00:00Z')).toBe(true)
    expect(persist).toHaveBeenCalledTimes(2)
    // 幂等：已经确认的同一 lfp 不再保存、不重复递减
    expect(await acknowledgeVoucherSurvivalRow('wp-1', FP, 'user-1', 'later')).toBeNull()
    expect(persist).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('同一数据集与状态重跑保留 ack；状态变化会清空 ack', async () => {
    const existing = row('a', { sv: { status: 'modified', datasetId: 'dataset-new', checkId: 'check-1',
      detail: 'old', ackBy: 'user-1', ackAt: '2026-10-29T01:00:00Z' } })
    const { wrapper, rows } = mountedHost([existing])
    await nextTick()
    await applyVoucherSurvivalResult('wp-1', { ...RESULT, results: [{ ...RESULT.results[0], acknowledged: true }] })
    expect((rows.value[0]._gt.sv as any).ackAt).toBe('2026-10-29T01:00:00Z')
    await applyVoucherSurvivalResult('wp-1', { ...RESULT, deleted: 1, modified: 0,
      results: [{ ...RESULT.results[0], status: 'deleted', acknowledged: false }] })
    expect((rows.value[0]._gt.sv as any).ackAt).toBeUndefined()
    wrapper.unmount()
  })
})
