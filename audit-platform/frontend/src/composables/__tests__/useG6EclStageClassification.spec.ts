/**
 * useG6EclStageClassification — G6-11 三阶段划分单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  useG6EclStageClassification,
  SECTION_ONE_COUNT,
  SECTION_TWO_COUNT,
  SECTION_THREE_COUNT,
  SECTION_ONE_LABELS,
} from '@/composables/useG6EclStageClassification'
import { determineStage } from '@/composables/useG6EclFormulaEngine'
import { applyStageUpdatesToRows } from '@/components/workpaper/composables/useG6EclImpairmentCalc'

describe('useG6EclStageClassification', () => {
  it('检查项数量为 13 + 3 + 8', () => {
    expect(SECTION_ONE_COUNT).toBe(13)
    expect(SECTION_TWO_COUNT).toBe(3)
    expect(SECTION_THREE_COUNT).toBe(8)
  })

  it('新增行默认未检查（空值），审计阶段 Stage1', async () => {
    const logic = useG6EclStageClassification()
    await logic.addRow('测试债券A')
    const row = logic.rows.value[0]
    expect(row.sectionOneChecks).toHaveLength(13)
    expect(row.sectionTwoChecks).toHaveLength(3)
    expect(row.sectionThreeChecks).toHaveLength(8)
    expect(row.sectionOneChecks.every(c => c.value === '')).toBe(true)
    expect(row.sectionOneChecks.every(c => c.hint.length > 0)).toBe(true)
    expect(row.auditStage).toBe('Stage1')
    expect(logic.hasIncompleteChecks(row)).toBe(true)
  })

  it('SICR=是 且 低风险豁免 → Stage1；SICR=是 无豁免 → Stage2', async () => {
    const logic = useG6EclStageClassification()
    await logic.addRow('债券B')
    const id = logic.rows.value[0].id

    logic.updateCheckValue(id, 'significantIncrease', 0, '是')
    expect(logic.rows.value[0].hasSignificantIncrease).toBe(true)
    expect(logic.rows.value[0].auditStage).toBe('Stage2')

    logic.updateCheckValue(id, 'lowCreditRisk', 0, '是')
    logic.updateCheckValue(id, 'lowCreditRisk', 1, '是')
    logic.updateCheckValue(id, 'lowCreditRisk', 2, '是')
    expect(logic.rows.value[0].hasLowCreditRisk).toBe(true)
    expect(logic.rows.value[0].auditStage).toBe('Stage1')
  })

  it('已减值优先于 SICR 与低风险', () => {
    expect(determineStage(true, true, true)).toBe('Stage3')
  })

  it('手动覆盖审计阶段后不被公式覆盖，可恢复', async () => {
    const logic = useG6EclStageClassification()
    await logic.addRow('债券D')
    const id = logic.rows.value[0].id
    logic.updateCheckValue(id, 'significantIncrease', 0, '是')
    expect(logic.rows.value[0].auditStage).toBe('Stage2')

    logic.updateAuditStage(id, 'Stage1')
    expect(logic.rows.value[0].auditStageManualOverride).toBe(true)
    expect(logic.rows.value[0].auditStage).toBe('Stage1')

    logic.updateCheckValue(id, 'creditImpairment', 0, '是')
    expect(logic.rows.value[0].auditStage).toBe('Stage1')

    logic.clearAuditStageOverride(id)
    expect(logic.rows.value[0].auditStageManualOverride).toBe(false)
    expect(logic.rows.value[0].auditStage).toBe('Stage3')
  })

  it('不一致且无差异说明时 canSave=false', async () => {
    const logic = useG6EclStageClassification()
    await logic.addRow('债券E')
    const id = logic.rows.value[0].id
    logic.updateCompanyStage(id, 'Stage1')
    logic.updateAuditStage(id, 'Stage2')
    expect(logic.canSave()).toBe(false)
    logic.updateDiscrepancyNote(id, '企业划分偏乐观')
    expect(logic.canSave()).toBe(true)
  })

  it('从明细导入并预填逾期≥30日 SICR', () => {
    const logic = useG6EclStageClassification()
    const result = logic.importFromDetailRows([
      {
        investProject: '甲公司债',
        closingAudited: 1000000,
        stageClassification: 'Stage1',
        maturityDate: '2020-01-01',
      },
    ], { asOfDate: '2025-12-31' })
    expect(result.added).toBe(1)
    expect(result.prefilledOverdue).toBe(1)
    expect(result.prefilledDefault).toBe(1)
    const row = logic.rows.value[0]
    expect(row.bookBalance).toBe(1000000)
    expect(row.sectionOneChecks.some(c => c.label.includes('逾期') && c.value === '是')).toBe(true)
    expect(row.hasSignificantIncrease).toBe(true)
    expect(row.hasCreditImpairment).toBe(true)
    expect(row.auditStage).toBe('Stage3')
    expect(SECTION_ONE_LABELS.some(l => l.includes('逾期'))).toBe(true)
  })

  it('逾期30~89日仅预填 SICR，不推定 Stage3', () => {
    const logic = useG6EclStageClassification()
    const result = logic.importFromDetailRows([
      { investProject: '乙公司债', closingAudited: 100, overdueDays: 45 },
    ])
    expect(result.prefilledOverdue).toBe(1)
    expect(result.prefilledDefault).toBe(0)
    expect(logic.rows.value[0].auditStage).toBe('Stage2')
  })
})

describe('applyStageUpdatesToRows (G6-11→G6-12)', () => {
  it('按项目名写入 stage 并新建缺失行', () => {
    const { rows, count, created } = applyStageUpdatesToRows([], [
      { investProject: '国债A', auditStage: 'Stage2', bookBalance: 500 },
    ])
    expect(count).toBe(1)
    expect(created).toBe(1)
    expect(rows[0].stage).toBe('Stage2')
    expect(rows[0].stageGroup).toBe('Stage2')
    expect(rows[0].amortizedCost).toBe(500)
    expect(rows[0].differenceNote).toContain('G6-11')
  })

  it('已有行仅更新阶段，余额为空时回填', () => {
    const base = applyStageUpdatesToRows([], [
      { investProject: '国债A', auditStage: 'Stage1', bookBalance: 0 },
    ]).rows
    const { rows, count, updated } = applyStageUpdatesToRows(base, [
      { investProject: '国债A', auditStage: 'Stage3', bookBalance: 800 },
    ])
    expect(count).toBe(1)
    expect(updated).toBe(1)
    expect(rows[0].stage).toBe('Stage3')
    expect(rows[0].amortizedCost).toBe(800)
  })

  it('重名项目记入 ambiguous', () => {
    const base = applyStageUpdatesToRows([], [
      { investProject: '同名债', auditStage: 'Stage1' },
    ]).rows
    base.push({ ...base[0], id: 'dup-2', seq: 2 })
    const { ambiguous } = applyStageUpdatesToRows(base, [
      { investProject: '同名债', auditStage: 'Stage2' },
    ])
    expect(ambiguous).toContain('同名债')
  })
})
