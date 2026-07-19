/**
 * useG6EclReversalWriteOff — G6-14 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('element-plus', () => ({
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
  ElMessage: { success: vi.fn() },
}))

import {
  useG6EclReversalWriteOff,
  migrateReversalWriteOff,
} from '../useG6EclReversalWriteOff'
import { isReversalValid, calcSumColumn } from '@/composables/useG6EclFormulaEngine'
import { ElMessageBox } from 'element-plus'

describe('isReversalValid / calcSumColumn', () => {
  it('转回 ≤ 累计计提为有效', () => {
    expect(isReversalValid(100, 100)).toBe(true)
    expect(isReversalValid(100, 200)).toBe(true)
    expect(isReversalValid(101, 100)).toBe(false)
  })

  it('列合计保留 2 位', () => {
    expect(calcSumColumn([10.005, 20.004])).toBe(30.01)
  })
})

describe('migrateReversalWriteOff', () => {
  it('旧单表按 type 拆分', () => {
    const data = migrateReversalWriteOff({
      rows: [
        { id: '1', investProject: 'A', type: '转回', amount: 10, reason: '改善', approvalProcedure: '', reasonConclusion: '合理', indexRef: '', seq: 1 },
        { id: '2', investProject: 'B', type: '核销', amount: 20, reason: '破产', approvalProcedure: '审批', reasonConclusion: '合理', indexRef: '', seq: 2 },
        { id: '3', investProject: 'C', type: '收回', amount: 5, reason: '收款', approvalProcedure: '', reasonConclusion: '合理', indexRef: '', seq: 3 },
      ],
      conclusion: 'ok',
    })
    expect(data.reversals).toHaveLength(2)
    expect(data.writeOffs).toHaveLength(1)
    expect(data.reversals[1].kind).toBe('收回')
    expect(data.writeOffs[0].writeOffAmount).toBe(20)
    expect(data.conclusion).toBe('ok')
  })

  it('新双表结构原样加载', () => {
    const data = migrateReversalWriteOff({
      schemaVersion: 2,
      reversals: [{ id: 'r1', seq: 1, unitName: 'X', reversalAmount: 1, accumulatedProvision: 2 }],
      writeOffs: [],
      conclusion: '',
    })
    expect(data.reversals[0].unitName).toBe('X')
  })
})

describe('useG6EclReversalWriteOff', () => {
  beforeEach(() => vi.clearAllMocks())

  it('转回超限计入 invalidCount / gate', () => {
    const { reversals, reversalSummary, gate, loadData } = useG6EclReversalWriteOff()
    loadData({
      schemaVersion: 2,
      reversals: [{
        id: '1', seq: 1, unitName: 'A',
        reversalReason: '', recoveryMethod: '', originalBasis: '',
        reversalAmount: 150, accumulatedProvision: 100,
        reasonAnalysis: '', isReasonable: '合理', indexRef: '',
      }],
      writeOffs: [],
      conclusion: '',
    })
    expect(reversals.value).toHaveLength(1)
    expect(reversalSummary.value.invalidCount).toBe(1)
    expect(gate.value.ready).toBe(false)
  })

  it('关联核销缺分析时闸门不通过', () => {
    const { gate, loadData } = useG6EclReversalWriteOff()
    loadData({
      schemaVersion: 2,
      reversals: [],
      writeOffs: [{
        id: '1', seq: 1, unitName: 'B',
        writeOffType: '', writeOffAmount: 10, writeOffReason: '',
        writeOffProcedure: '', isRelatedParty: true,
        reasonAnalysis: '', isReasonable: '合理', indexRef: '',
      }],
      conclusion: '',
    })
    expect(gate.value.relatedMissingAnalysis).toBe(1)
    expect(gate.value.ready).toBe(false)
  })

  it('addReversalRow 成功', async () => {
    vi.mocked(ElMessageBox.prompt).mockResolvedValue({ value: '新单位' } as any)
    const { reversals, addReversalRow } = useG6EclReversalWriteOff()
    await addReversalRow()
    expect(reversals.value).toHaveLength(1)
    expect(reversals.value[0].unitName).toBe('新单位')
  })
})
