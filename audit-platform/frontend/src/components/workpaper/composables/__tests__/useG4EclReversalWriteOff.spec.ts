/**
 * useG4EclReversalWriteOff — 闸门与合计
 */
import { describe, it, expect } from 'vitest'
import { useG4EclReversalWriteOff } from '../useG4EclReversalWriteOff'

describe('useG4EclReversalWriteOff gate', () => {
  it('转回超限时 gate.ready=false', () => {
    const rw = useG4EclReversalWriteOff()
    rw.loadData({
      reversals: [{
        id: '1',
        seq: 1,
        unitName: '甲',
        reversalReason: '',
        recoveryMethod: '',
        originalBasis: '',
        reversalAmount: 200,
        accumulatedProvision: 100,
        reasonAnalysis: '',
        isReasonable: '合理',
        indexRef: '',
      }],
      writeOffs: [],
    })
    expect(rw.gate.value.invalidReversals).toBe(1)
    expect(rw.gate.value.ready).toBe(false)
  })

  it('关联交易核销缺合理性分析时 gate.ready=false', () => {
    const rw = useG4EclReversalWriteOff()
    rw.loadData({
      reversals: [],
      writeOffs: [{
        id: '1',
        seq: 1,
        unitName: '乙',
        writeOffType: '公司债',
        writeOffAmount: 50,
        writeOffReason: '无力偿还',
        writeOffProcedure: '董事会审批',
        isRelatedParty: true,
        reasonAnalysis: '',
        isReasonable: '合理',
        indexRef: '',
      }],
    })
    expect(rw.gate.value.relatedPartyWriteOffs).toBe(1)
    expect(rw.gate.value.ready).toBe(false)
  })

  it('合规数据 gate.ready=true', () => {
    const rw = useG4EclReversalWriteOff()
    rw.loadData({
      reversals: [{
        id: '1',
        seq: 1,
        unitName: '甲',
        reversalReason: '信用改善',
        recoveryMethod: '现金',
        originalBasis: 'Stage2',
        reversalAmount: 80,
        accumulatedProvision: 100,
        reasonAnalysis: 'OK',
        isReasonable: '合理',
        indexRef: '',
      }],
      writeOffs: [{
        id: '2',
        seq: 1,
        unitName: '乙',
        writeOffType: '信托计划',
        writeOffAmount: 10,
        writeOffReason: '破产',
        writeOffProcedure: '审批完备',
        isRelatedParty: true,
        reasonAnalysis: '已披露关联交易',
        isReasonable: '合理',
        indexRef: '',
      }],
    })
    expect(rw.gate.value.ready).toBe(true)
    expect(rw.writeOffSummary.value.relatedPartyCount).toBe(1)
  })
})
