import { describe, it, expect } from 'vitest'
import {
  applyStageUpdatesToRows,
  applyEclRateUpdatesToRows,
  collectEclRateUpdates,
} from '../useG4EclImpairmentCalc'
import {
  parseRowsJson,
  calcOverdueDays,
  pickG4ImpairmentTbRow,
  normalizeInvestName,
  extractG41ImpairmentClosingAudited,
  parseG411MeasurementPayload,
  buildG411MeasurementPayload,
  applyG4ClassificationUpdates,
  applyG44InterestToDetailRows,
} from '../g4CrossHelpers'

describe('applyStageUpdatesToRows', () => {
  it('新建缺失项目并写入 stageGroup / bookBalance', () => {
    const { rows, count } = applyStageUpdatesToRows([], [
      { investProject: '债A', auditStage: 'Stage2', bookBalance: 100 },
      { investProject: '债B', auditStage: 'Stage3', bookBalance: 200 },
    ])
    expect(count).toBe(2)
    expect(rows).toHaveLength(2)
    expect(rows[0].stageGroup).toBe('Stage2')
    expect(rows[0].bookBalance).toBe(100)
    expect(rows[1].stageGroup).toBe('Stage3')
  })

  it('已有行仅更新阶段，余额为空时回填', () => {
    const existing = applyStageUpdatesToRows([], [
      { investProject: '债A', auditStage: 'Stage1', bookBalance: 0 },
    ]).rows
    const { rows, count } = applyStageUpdatesToRows(existing, [
      { investProject: '债A', auditStage: 'Stage2', bookBalance: 888 },
    ])
    expect(count).toBe(1)
    expect(rows).toHaveLength(1)
    expect(rows[0].stageGroup).toBe('Stage2')
    expect(rows[0].bookBalance).toBe(888)
  })

  it('名称空白归一后可匹配已有行', () => {
    const existing = applyStageUpdatesToRows([], [
      { investProject: '债  A', auditStage: 'Stage1', bookBalance: 50 },
    ]).rows
    const { rows, count } = applyStageUpdatesToRows(existing, [
      { investProject: '债A', auditStage: 'Stage3', bookBalance: 999 },
    ])
    expect(count).toBe(1)
    expect(rows).toHaveLength(1)
    expect(rows[0].stageGroup).toBe('Stage3')
    expect(rows[0].bookBalance).toBe(50)
    expect(normalizeInvestName('债  A')).toBe('债A')
  })
})

describe('applyEclRateUpdatesToRows / collectEclRateUpdates', () => {
  it('collect 同名两法时按 prefer 覆盖', () => {
    const updates = collectEclRateUpdates(
      [{ projectName: '债A', eclRate: 0.01, stage: 'Stage1' }],
      [{ projectName: '债A', eclRate: 0.05, stage: 'Stage1' }],
      'lossRate',
    )
    expect(updates).toHaveLength(1)
    expect(updates[0].eclRate).toBe(0.05)
    expect(updates[0].method).toBe('lossRate')
  })

  it('回写 ②；未触碰时同步 ②A；跳过 Stage3 与未匹配', () => {
    const base = applyStageUpdatesToRows([], [
      { investProject: '债A', auditStage: 'Stage1', bookBalance: 1000 },
      { investProject: '债B', auditStage: 'Stage3', bookBalance: 2000 },
    ]).rows
    base[0].adjRateTouched = false
    base[0].creditLossRate = 0.01
    base[0].adjustedCreditLossRate = 0.01

    const { rows, count, skipped } = applyEclRateUpdatesToRows(base, [
      { projectName: '债A', eclRate: 0.08, method: 'pdLgd' },
      { projectName: '债B', eclRate: 1, method: 'pdLgd' },
      { projectName: '债C', eclRate: 0.1, method: 'lossRate' },
    ])

    expect(count).toBe(1)
    expect(rows[0].creditLossRate).toBe(0.08)
    expect(rows[0].adjustedCreditLossRate).toBe(0.08)
    expect(skipped.map(s => s.reason).sort()).toEqual(['not-found', 'stage3'])
  })

  it('adjRateTouched=true 时不覆盖 ②A', () => {
    const base = applyStageUpdatesToRows([], [
      { investProject: '债A', auditStage: 'Stage2', bookBalance: 100 },
    ]).rows
    base[0].adjRateTouched = true
    base[0].creditLossRate = 0.02
    base[0].adjustedCreditLossRate = 0.09

    const { rows } = applyEclRateUpdatesToRows(base, [
      { projectName: '债A', eclRate: 0.03, method: 'lossRate' },
    ])
    expect(rows[0].creditLossRate).toBe(0.03)
    expect(rows[0].adjustedCreditLossRate).toBe(0.09)
  })

  it('force=true 时覆盖人工 ②A，并报告 matched/unmatched', () => {
    const base = applyStageUpdatesToRows([], [
      { investProject: '债A', auditStage: 'Stage1', bookBalance: 100 },
    ]).rows
    base[0].adjRateTouched = true
    base[0].adjustedCreditLossRate = 0.09
    const result = applyEclRateUpdatesToRows(base, [
      { projectName: '债A', eclRate: 0.03, method: 'lossRate' },
      { projectName: '债B', eclRate: 0.04, method: 'lossRate' },
    ], { force: true })
    expect(result.rows[0].adjustedCreditLossRate).toBe(0.03)
    expect(result.matched).toEqual(['债A'])
    expect(result.unmatched).toEqual(['债B'])
    expect(result.matchReport.byName).toEqual(['债A'])
    expect(result.matchReport.unmatched).toEqual(['债B'])
  })

  it('优先按 crossSheetInvestmentId 匹配损失率', () => {
    const base = applyStageUpdatesToRows([], [
      { investProject: '债A-别名', auditStage: 'Stage1', bookBalance: 100 },
    ]).rows
    base[0].crossSheetInvestmentId = 'inv-stable-1'
    const collected = collectEclRateUpdates(
      [{ id: 'inv-stable-1', projectName: '债A', eclRate: 0.12, stage: 'Stage1' }],
      null,
      'pdLgd',
    )
    expect(collected[0].crossSheetInvestmentId).toBe('inv-stable-1')
    const result = applyEclRateUpdatesToRows(base, collected)
    expect(result.count).toBe(1)
    expect(result.matchReport.byId).toEqual(['债A-别名'])
    expect(result.rows[0].creditLossRate).toBe(0.12)
  })
})

describe('g4CrossHelpers', () => {
  it('parseRowsJson 兼容数组与 rows 包装', () => {
    expect(parseRowsJson(JSON.stringify([{ a: 1 }]))).toHaveLength(1)
    expect(parseRowsJson(JSON.stringify({ rows: [{ a: 1 }, { a: 2 }] }))).toHaveLength(2)
    expect(parseRowsJson('bad')).toEqual([])
  })

  it('calcOverdueDays 计算已逾期天数', () => {
    expect(calcOverdueDays('2020-01-01', '2020-02-01')).toBe(31)
    expect(calcOverdueDays('2025-12-31', '2020-01-01')).toBe(0)
  })

  it('pickG4ImpairmentTbRow 优先科目名，其次 1502，再 1505+债权投资减值', () => {
    expect(pickG4ImpairmentTbRow([])).toBeNull()

    const byName = pickG4ImpairmentTbRow([
      { standard_account_code: '9999', standard_account_name: '债权投资减值准备', audited_amount: 12 },
      { standard_account_code: '1502', standard_account_name: '其他', audited_amount: 99 },
    ])
    expect(byName?.amount).toBe(12)
    expect(byName?.code).toBe('9999')

    const by1502 = pickG4ImpairmentTbRow([
      { standard_account_code: '1502', account_name: '减值备抵', audited_amount: 30 },
    ])
    expect(by1502?.amount).toBe(30)
    expect(by1502?.code).toBe('1502')

    const by1505 = pickG4ImpairmentTbRow([
      { standard_account_code: '1505', standard_account_name: '债权投资减值准备-明细', audited_amount: 7 },
    ])
    expect(by1505?.amount).toBe(7)
  })

  it('extractG41ImpairmentClosingAudited 汇总单项+组合期末审定', () => {
    expect(extractG41ImpairmentClosingAudited(null)).toBe(0)
    expect(extractG41ImpairmentClosingAudited({})).toBe(0)
    expect(extractG41ImpairmentClosingAudited({
      'impairment-individual': { closingUnadjusted: 100, closingAdjustment: 10 },
      'impairment-portfolio': { closingUnadjusted: 50, closingAdjustment: -5 },
      'original-individual': { closingUnadjusted: 999, closingAdjustment: 0 },
    })).toBe(155)

    expect(extractG41ImpairmentClosingAudited({
      'impairment-individual': { closingUnadjusted: 80, closingAJE: 3, closingRJE: 2 },
    })).toBe(85)
  })

  it('parseG411MeasurementPayload 解析测算 JSON', () => {
    expect(parseG411MeasurementPayload(null)).toBeNull()
    const p = parseG411MeasurementPayload(JSON.stringify({
      pdLgdRows: [{ projectName: 'A', eclRate: 0.1 }],
      lossRateRows: [],
      conclusion: 'ok',
    }))
    expect(p?.pdLgdRows).toHaveLength(1)
    expect(p?.conclusion).toBe('ok')
  })

  it('G4-11 canonical payload includes schemaVersion', () => {
    expect(buildG411MeasurementPayload({ pdLgdRows: [] }).schemaVersion).toBe(1)
  })

  it('分类按 id/名称回写并保留已有 SPPI', () => {
    const result = applyG4ClassificationUpdates([
      { id: 'a', investProject: '债 A', sppiResult: 'PASS' },
    ], [
      { investProject: '债A', businessModelResult: 'FVOCI', classificationSource: 'G4-5' },
    ])
    expect(result.matched).toEqual(['债 A'])
    expect(result.rows[0]).toMatchObject({
      businessModelResult: 'FVOCI',
      sppiResult: 'PASS',
      measurementClassification: 'FVOCI',
    })
  })

  it('G4-4 仅写实际利息减票息至期间利息调整', () => {
    const result = applyG44InterestToDetailRows([
      { id: 'a', investProject: '债A', periodInterestAdjChange: 999 },
    ], [{
      projectName: '债 A',
      periods: [
        { effectiveInterest: 12, cashInflow: 10 },
        { effectiveInterest: 6, cashInflow: 5 },
      ],
    }])
    expect(result.rows[0].periodInterestAdjChange).toBe(3)
    expect(result.matched).toEqual(['债A'])
  })
})
