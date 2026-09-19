import { describe, expect, it } from 'vitest'
import {
  getStageTriggerLabels,
  useG5StageClassification,
} from '../useG5StageClassification'

describe('useG5StageClassification', () => {
  it('已减值优先 → suggested Stage3', () => {
    const s = useG5StageClassification()
    s.loadRows([{
      debtor: '甲',
      companyStage: 'Stage1',
      sectionThreeChecks: [
        { label: 'a', value: '是' },
        { label: 'b', value: '否' },
        { label: 'c', value: '否' },
        { label: 'd', value: '否' },
        { label: 'e', value: '否' },
        { label: 'f', value: '否' },
        { label: 'g', value: '否' },
        { label: 'h', value: '否' },
      ],
    } as any])
    const row = s.rows.value[0]
    expect(row.suggestedStage).toBe('Stage3')
    expect(row.auditStage).toBe('Stage3')
    expect(row.isConsistent).toBe(false)
    expect(getStageTriggerLabels(row).some(t => t.includes('已减值'))).toBe(true)
  })

  it('SICR 且非低风险 → Stage2；人工覆写后不跟随建议', () => {
    const s = useG5StageClassification()
    s.loadRows([{
      debtor: '乙',
      companyStage: 'Stage2',
      sectionOneChecks: Array.from({ length: 13 }, (_, i) => ({
        label: `f${i}`,
        value: i === 10 ? '是' : '否',
      })),
    } as any])
    const id = s.rows.value[0].id
    expect(s.rows.value[0].suggestedStage).toBe('Stage2')
    s.updateAuditStage(id, 'Stage1')
    expect(s.rows.value[0].auditStageOverridden).toBe(true)
    // 再改检查项仍保持覆写
    s.updateCheckValue(id, 'significantIncrease', 0, '是')
    expect(s.rows.value[0].auditStage).toBe('Stage1')
    expect(s.rows.value[0].suggestedStage).toBe('Stage2')
    s.resetAuditStageToSuggested(id)
    expect(s.rows.value[0].auditStage).toBe('Stage2')
    expect(s.rows.value[0].auditStageOverridden).toBe(false)
  })

  it('从 G5-2 带入并汇总阶段余额', () => {
    const s = useG5StageClassification()
    const n = s.importFromBalanceRows([
      { debtorName: 'A', closingBalance: 100, businessType: 'lease' },
      { debtorName: 'B', closingBalance: 200, businessType: 'installment' },
    ])
    expect(n).toBe(2)
    s.updateAuditStage(s.rows.value[0].id, 'Stage1')
    // force stage amounts: set B to stage3 via impairment
    const bId = s.rows.value[1].id
    s.updateCheckValue(bId, 'creditImpairment', 0, '是')
    expect(s.summary.value.stage3Amount).toBe(200)
    expect(s.summary.value.totalAmount).toBe(300)
  })

  it('不一致草稿可推送 G5-4', () => {
    const s = useG5StageClassification()
    s.loadRows([{
      debtor: '丙',
      closingBalance: 50,
      companyStage: 'Stage1',
      sectionThreeChecks: Array.from({ length: 8 }, (_, i) => ({
        label: `i${i}`,
        value: i === 0 ? '是' : '否',
      })),
      discrepancyNote: '企业未关注违约',
    } as any])
    const drafts = s.buildInconsistencyAdjDrafts()
    expect(drafts).toHaveLength(1)
    expect(drafts[0].description).toContain('丙')
    expect(drafts[0].remark).toContain('来自G5-9三阶段')
  })
})
