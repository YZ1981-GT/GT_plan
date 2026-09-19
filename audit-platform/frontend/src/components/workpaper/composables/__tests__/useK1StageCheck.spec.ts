import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { determineStage, determineStageWithExemption } from '../useK1ECLEngine'
import {
  useK1StageCheck,
  calcK1HasSignificantIncrease,
  calcK1HasLowCreditRisk,
  calcK1HasCreditImpairment,
  mergeOverdueStageHintsToK7,
  buildK110StageHintsFromSources,
  buildK1StageInconsistencyAdjDrafts,
  pullK110OverdueHints,
  K1_STAGE_PUSH_MARK,
  K110_STORAGE_KEY,
} from '../useK1StageCheck'

describe('determineStageWithExemption', () => {
  it('applies low credit risk exemption for SICR', () => {
    expect(determineStageWithExemption(false, true, true)).toBe(1)
    expect(determineStageWithExemption(false, true, false)).toBe(2)
    expect(determineStageWithExemption(true, false, true)).toBe(3)
  })

  it('remains compatible with legacy determineStage when no exemption', () => {
    expect(determineStage(false, false)).toBe(1)
    expect(determineStage(false, true)).toBe(2)
    expect(determineStage(true, false)).toBe(3)
  })
})

describe('useK1StageCheck', () => {
  it('derives stage from section checklists', () => {
    const map = ref(new Map())
    const sc = useK1StageCheck({ allResponses: map, wpId: ref(''), projectId: ref('') })
    const row = sc.addRow('甲公司', 100000)
    row.sectionOneChecks[12].value = '是'
    sc.updateCheckValue(row.id, 'significantIncrease', 12, '是')
    expect(sc.rows.value[0].isSignificantIncrease).toBe(true)
    expect(sc.rows.value[0].suggestedStage).toBe(2)
    expect(sc.rows.value[0].stage).toBe(2)
  })

  it('low credit risk exemption keeps stage 1 despite SICR', () => {
    const map = ref(new Map())
    const sc = useK1StageCheck({ allResponses: map, wpId: ref(''), projectId: ref('') })
    const row = sc.addRow('乙公司', 50000)
    row.sectionOneChecks[0].value = '是'
    row.sectionTwoChecks.forEach(c => { c.value = '是' })
    sc.updateCheckValue(row.id, 'significantIncrease', 0, '是')
    sc.updateCheckValue(row.id, 'lowCreditRisk', 0, '是')
    sc.updateCheckValue(row.id, 'lowCreditRisk', 1, '是')
    sc.updateCheckValue(row.id, 'lowCreditRisk', 2, '是')
    expect(sc.rows.value[0].hasLowCreditRisk).toBe(true)
    expect(sc.rows.value[0].suggestedStage).toBe(1)
  })

  it('credit impairment forces stage 3', () => {
    const map = ref(new Map())
    const sc = useK1StageCheck({ allResponses: map, wpId: ref(''), projectId: ref('') })
    const row = sc.addRow('丙公司', 80000)
    sc.updateCheckValue(row.id, 'creditImpairment', 1, '是')
    expect(sc.rows.value[0].isImpaired).toBe(true)
    expect(sc.rows.value[0].stage).toBe(3)
  })

  it('migrates legacy boolean rows on load', () => {
    const legacy = [{
      id: 'old-1', counterparty: '丁', endBalance: 1000,
      isSignificantIncrease: true, isImpaired: false,
      stage: 2, priorStage: 1, changeNote: '',
    }]
    const map = ref(new Map([['K1-7-stage-rows', { remark: JSON.stringify(legacy) }]]))
    const sc = useK1StageCheck({ allResponses: map, wpId: ref(''), projectId: ref('') })
    sc.loadRows()
    expect(sc.rows.value[0].sectionOneChecks[12].value).toBe('是')
    expect(sc.rows.value[0].stage).toBe(2)
  })

  it('applyFromK12Detail imports counterparties', () => {
    const map = ref(new Map<string, any>([
      ['K1-2-detail-rows', { remark: JSON.stringify([
        { counterparty: '客户A', endBalance: 200000, stage: 2 },
        { counterparty: '客户B', endBalance: 50000, stage: 1 },
      ]) }],
    ]))
    const sc = useK1StageCheck({ allResponses: map, wpId: ref(''), projectId: ref('') })
    const { added } = sc.applyFromK12Detail()
    expect(added).toBe(2)
    expect(sc.rows.value).toHaveLength(2)
    expect(sc.rows.value[0].endBalance).toBe(200000)
  })

  it('flags stage migration without change note', () => {
    const map = ref(new Map())
    const sc = useK1StageCheck({ allResponses: map, wpId: ref(''), projectId: ref('') })
    const row = sc.addRow('戊', 10000)
    row.priorStage = 1
    sc.updateCheckValue(row.id, 'creditImpairment', 0, '是')
    expect(sc.stageMigrationWarnings.value).toHaveLength(1)
    sc.updateRow(row.id, 'changeNote', '本期逾期90天')
    expect(sc.stageMigrationWarnings.value).toHaveLength(0)
  })

  it('counts company vs audit stage inconsistencies', () => {
    const map = ref(new Map())
    const sc = useK1StageCheck({ allResponses: map, wpId: ref(''), projectId: ref('') })
    const row = sc.addRow('己', 30000)
    sc.updateRow(row.id, 'companyStage', 1)
    sc.updateCheckValue(row.id, 'creditImpairment', 0, '是')
    expect(sc.summary.value.inconsistentCount).toBe(1)
  })

  it('applyFromK110 auto-checks overdue items from K1-10 storage', () => {
    const k110Rows = [{
      debtorName: '逾期户A',
      openingBalance: 100000,
      periodDebit: 0,
      periodCredit: 0,
      aging: '1-2年',
      isUncollectible: '',
      litigation: '',
    }]
    const map = ref(new Map<string, any>([
      [K110_STORAGE_KEY, { remark: JSON.stringify({ rows: k110Rows }) }],
    ]))
    const sc = useK1StageCheck({ allResponses: map, wpId: ref(''), projectId: ref('') })
    const { checked, added } = sc.applyFromK110()
    expect(checked).toBe(1)
    expect(added).toBe(1)
    expect(sc.rows.value[0].sectionOneChecks[12].value).toBe('是')
    expect(sc.rows.value[0].stage).toBeGreaterThanOrEqual(2)
  })

  it('applyFromK110 marks uncollectible as stage 3 impairment checks', () => {
    const hints = buildK110StageHintsFromSources([{
      debtorName: '坏账户B',
      closingBalance: 50000,
      aging: '3年以上',
      isUncollectible: '是',
      litigation: '',
    }])
    const map = ref(new Map())
    const sc = useK1StageCheck({ allResponses: map, wpId: ref(''), projectId: ref('') })
    sc.addRow('坏账户B', 50000)
    const merged = mergeOverdueStageHintsToK7(sc.rows.value, hints)
    sc.rows.value = merged.rows
    expect(sc.rows.value[0].sectionThreeChecks[0].value).toBe('是')
    expect(sc.rows.value[0].sectionThreeChecks[1].value).toBe('是')
    expect(sc.rows.value[0].stage).toBe(3)
  })

  it('buildK1StageInconsistencyAdjDrafts includes push mark for K1-4 dedup', () => {
    const map = ref(new Map())
    const sc = useK1StageCheck({ allResponses: map, wpId: ref(''), projectId: ref('') })
    const row = sc.addRow('差异户C', 80000)
    sc.updateRow(row.id, 'companyStage', 1)
    sc.updateCheckValue(row.id, 'creditImpairment', 0, '是')
    const drafts = buildK1StageInconsistencyAdjDrafts(sc.rows.value)
    expect(drafts).toHaveLength(1)
    expect(drafts[0].summary).toContain(K1_STAGE_PUSH_MARK)
    expect(drafts[0].summary).toContain('企业Stage1')
    expect(drafts[0].summary).toContain('审计Stage3')
  })

  it('pullK110OverdueHints parses bundle rows', () => {
    const map = new Map<string, any>([
      [K110_STORAGE_KEY, { remark: JSON.stringify({
        rows: [{ debtorName: '测试', openingBalance: 1, periodDebit: 0, periodCredit: 0, aging: '2-3年' }],
      }) }],
    ])
    const hints = pullK110OverdueHints(map)
    expect(hints).toHaveLength(1)
    expect(hints[0].debtorName).toBe('测试')
    expect(hints[0].suggestedStage).toBeGreaterThanOrEqual(2)
  })
})

describe('calcK1 checklist helpers', () => {
  it('section one any yes triggers SICR', () => {
    const checks = [{ label: 'a', value: '否' as const }, { label: 'b', value: '是' as const }]
    expect(calcK1HasSignificantIncrease(checks as any)).toBe(true)
  })

  it('section two all yes for low risk', () => {
    const checks = [
      { label: 'a', value: '是' as const },
      { label: 'b', value: '是' as const },
      { label: 'c', value: '是' as const },
    ]
    expect(calcK1HasLowCreditRisk(checks)).toBe(true)
  })

  it('section three any yes for impairment', () => {
    const checks = [{ label: 'a', value: '否' as const }, { label: 'b', value: '是' as const }]
    expect(calcK1HasCreditImpairment(checks as any)).toBe(true)
  })
})
