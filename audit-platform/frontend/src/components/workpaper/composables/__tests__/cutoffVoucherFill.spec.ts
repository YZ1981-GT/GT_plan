/**
 * I2-13 / I2-14（I6-5 / I6-6 同一内核 useCycleCutoff）截止测试接入共享回填函数
 * （spec voucher-identity-writeback-and-audit-phase 任务 12）
 *
 * 截止行没有行主键、保存只留固定字段，不套通用用例，逐条验：
 * - 抽凭两次不重复；`_gt` 随保存落库，读回后还在；
 * - 映射：记账日期 / 期间、凭证号、摘要、账面金额（原实现只取借方，贷方样本金额为 0），单据侧留空待查原件；
 * - 替换只动本方向的表（账→单据 / 单据→账各一张）；
 * - 年审阶段预审行只读：改、删不生效，保存按读入版本写回；旧行同号同日同金额补写 `_gt`。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useI2Cutoff } from '../useI2Cutoff'
import { resetVoucherFillMocks, sample, VK } from './voucherFillHostHarness'

function make(seed: { forward?: unknown[]; backward?: unknown[] } = {}) {
  const allResponses = ref(new Map<string, any>()) as Ref<Map<string, any>>
  if (seed.forward) allResponses.value.set('I2-13-rows', { item_id: 'I2-13-rows', remark: JSON.stringify(seed.forward) })
  if (seed.backward) allResponses.value.set('I2-14-rows', { item_id: 'I2-14-rows', remark: JSON.stringify(seed.backward) })
  const saved: Record<string, any> = {}
  const saveResponses = vi.fn(async (_sheet: string, data: Record<string, any>) => { Object.assign(saved, data) })
  const api = useI2Cutoff({ allResponses, saveResponses, projectId: ref('proj-1'), year: 2025, autoSaveMs: 0 })
  return { api, saved, allResponses }
}

const meta = (r: unknown) => (r as { _gt?: Record<string, unknown> })._gt
const PRELIM = { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' }

beforeEach(resetVoucherFillMocks)

describe('截止测试（useCycleCutoff）抽凭回填走共享函数', () => {
  it('抽凭两次不重复；`_gt` 随保存落库，读回后还在', async () => {
    const inst = make()
    const batch = [sample('fp-1'), sample('fp-2', { voucherNo: '0013' })]
    await inst.api.onEngineFilled('forward', { samples: batch, phase: 'final', batchId: 'b-1' })
    await inst.api.onEngineFilled('forward', { samples: batch, phase: 'final', batchId: 'b-2' })
    expect(inst.api.forwardRows.value.map(r => r.voucherNo)).toEqual(['0012', '0013'])
    await inst.api.save('forward')
    expect(meta(inst.saved['I2-13-rows'][0])).toMatchObject({ vk: VK, lfp: 'fp-1', b: 'b-1', ph: 'final', src: ['engine'] })
    const again = make({ forward: inst.saved['I2-13-rows'] })
    expect(meta(again.api.forwardRows.value[0])).toMatchObject({ lfp: 'fp-1', b: 'b-1' })
  })

  it('映射：记账日期 / 期间、凭证号、摘要、账面金额（贷方样本金额照记，原实现为 0），单据侧留空待查原件', async () => {
    const inst = make()
    await inst.api.onEngineFilled('forward', {
      samples: [sample('fp-c', { debitAmount: null, creditAmount: '-450.00', summary: '冲销研发领料' })], phase: 'final', batchId: 'b-1',
    })
    expect(inst.api.forwardRows.value.map(r => [r.recordDate, r.recordPeriod, r.voucherNo, r.description, r.amount, r.documentDate, r.documentAmount, r.conclusion]))
      .toEqual([['2025-03-04', '2025-03', '0012', '冲销研发领料', -450, '', 0, '证据不完整']])
  })

  it('替换只动本方向的表：单据→账的抽凭行不受账→单据「替换本阶段抽凭行」影响', async () => {
    const inst = make()
    await inst.api.onEngineFilled('backward', { samples: [sample('fp-9', { voucherNo: '0099' })], phase: 'final', batchId: 'b-0' })
    await inst.api.onEngineFilled('forward', { samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    await inst.api.onEngineFilled('forward', { samples: [sample('fp-2', { voucherNo: '0013' })], phase: 'final', fillMode: 'replace', batchId: 'b-2' })
    expect(inst.api.forwardRows.value.map(r => r.voucherNo)).toEqual(['0013'])
    expect(inst.api.backwardRows.value.map(r => r.voucherNo)).toEqual(['0099'])
  })

  it('年审阶段预审行只读：改、删不生效；绕过界面改了内存，保存按读入版本写回', async () => {
    const prelim = { recordDate: '2025-03-04', voucherNo: '0012', amount: 1000, documentNo: 'DJ-1', _gt: PRELIM }
    const inst = make({ forward: [prelim] })
    await inst.api.voucherFillReady()
    const row = inst.api.forwardRows.value[0]
    expect(inst.api.isVoucherRowLocked(row)).toBe(true)
    inst.api.updateForwardRow(0, 'documentNo', '改了')
    inst.api.removeForwardRow(0)
    expect(inst.api.forwardRows.value).toHaveLength(1)
    expect(inst.api.forwardRows.value[0].documentNo).toBe('DJ-1')
    inst.api.forwardRows.value[0].documentNo = '被改了'
    await inst.api.save('forward')
    expect(inst.saved['I2-13-rows'][0]).toMatchObject({ voucherNo: '0012', documentNo: 'DJ-1' })
  })

  it('旧行（没有 `_gt`）同号同日同金额：不再插入，补写 `_gt`，单据核对内容保留', async () => {
    const inst = make({ forward: [{ recordDate: '2025-03-04', voucherNo: '0012', amount: 1000, documentNo: 'DJ-7' }] })
    await inst.api.onEngineFilled('forward', { samples: [sample('fp-1')], phase: 'final', batchId: 'b-1' })
    expect(inst.api.forwardRows.value).toHaveLength(1)
    expect(inst.api.forwardRows.value[0]).toMatchObject({ documentNo: 'DJ-7' })
    expect(meta(inst.api.forwardRows.value[0])).toMatchObject({ lfp: 'fp-1', src: ['manual', 'engine'] })
  })
})
