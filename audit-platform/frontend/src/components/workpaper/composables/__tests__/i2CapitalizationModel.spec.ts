/**
 * i2CapitalizationModel 单元测试 — 对齐 Excel I2-6
 */
import { describe, it, expect } from 'vitest'
import {
  emptyI2CapitalizationRow,
  migrateLegacyCapitalizationMap,
  summarizeI2Capitalization,
  seedRowsFromI2Detail,
  getRowCapResult,
  buildI26ConclusionDraft,
  validateI26CapGate,
  validateI26CapTiming,
  reconcileI26Amounts,
  suggestCas6ConditionsFromText,
  CAS6_CONDITION_NAMES,
} from '../i2CapitalizationModel'
import { evaluateCapitalization, createEmptyCAS6Conditions } from '../useI2CapitalizationEngine'

describe('i2CapitalizationModel', () => {
  it('五条件命名对齐 CAS6（④资源支持 ⑤可靠计量）', () => {
    expect(CAS6_CONDITION_NAMES[4]).toBe('资源支持')
    expect(CAS6_CONDITION_NAMES[5]).toBe('可靠计量')
  })

  it('须五条件全 yes 才可资本化', () => {
    const conds = createEmptyCAS6Conditions().map((c) => ({ ...c, result: 'yes' as const }))
    expect(evaluateCapitalization(conds).isMet).toBe(true)

    conds[3].result = 'na'
    expect(evaluateCapitalization(conds).isMet).toBe(false)
    expect(evaluateCapitalization(conds).missingConditions).toContain(4)
  })

  it('迁移旧 Map 持久化格式', () => {
    const rows = migrateLegacyCapitalizationMap({
      项目A: {
        date: '2023-06-01',
        conditions: [
          { id: 1, result: 'yes', evidence: '原型' },
          { id: 2, result: 'yes', evidence: '' },
          { id: 3, result: 'yes', evidence: '' },
          { id: 4, result: 'yes', evidence: '' },
          { id: 5, result: 'yes', evidence: '' },
        ],
      },
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].projectName).toBe('项目A')
    expect(rows[0].capStartDate).toBe('2023-06-01')
    expect(getRowCapResult(rows[0]).isMet).toBe(true)
  })

  it('从 I2-2 带入项目', () => {
    const rows = seedRowsFromI2Detail([
      { projectName: 'A', capStartDate: '2023-01-01', capIncrease: 100 },
      { projectName: '合计', capIncrease: 999 },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].projectName).toBe('A')
    expect(rows[0].developmentAmount).toBe(100)
  })

  it('汇总可资本化/不满足/待评', () => {
    const met = emptyI2CapitalizationRow({
      projectName: 'M',
      developmentAmount: 200,
      conditions: createEmptyCAS6Conditions().map((c) => ({ ...c, result: 'yes' as const })),
    })
    const fail = emptyI2CapitalizationRow({
      projectName: 'F',
      conditions: createEmptyCAS6Conditions().map((c, i) => ({
        ...c,
        result: i === 0 ? 'no' as const : 'yes' as const,
      })),
    })
    const pending = emptyI2CapitalizationRow({ projectName: 'P' })
    const s = summarizeI2Capitalization([met, fail, pending])
    expect(s.metCount).toBe(1)
    expect(s.notMetCount).toBe(1)
    expect(s.pendingCount).toBe(1)
    expect(s.totalDevelopment).toBe(200)
  })

  it('结论草稿包含项目统计', () => {
    const text = buildI26ConclusionDraft({
      projectCount: 3,
      metCount: 2,
      notMetCount: 1,
      pendingCount: 0,
      totalResearch: 0,
      totalDevelopment: 500,
      totalRecognizedIa: 0,
      ledgerInconsistentCount: 0,
    })
    expect(text).toContain('3 项')
    expect(text).toContain('2 项')
    expect(text).toContain('500.00')
  })

  it('闸门：有确认无形资产但五条件未齐 → error', () => {
    const row = emptyI2CapitalizationRow({
      projectName: 'X',
      recognizedIaAmount: 100,
      conditions: createEmptyCAS6Conditions(),
    })
    const issues = validateI26CapGate([row])
    expect(issues.some((i) => i.level === 'error')).toBe(true)
  })

  it('时点：资本化早于立项 → 提示', () => {
    const msgs = validateI26CapTiming(emptyI2CapitalizationRow({
      capStartDate: '2023-01-01',
      projectStartDate: '2023-06-01',
    }))
    expect(msgs.some((m) => m.includes('早于立项'))).toBe(true)
  })

  it('与 I2-7/I2-2 金额勾稽', () => {
    const rows = [emptyI2CapitalizationRow({
      projectName: 'P1',
      developmentAmount: 100,
      recognizedIaAmount: 50,
    })]
    const diffs = reconcileI26Amounts(
      rows,
      [{ projectName: 'P1', increase: { capitalized: 120 } }],
      [{ projectName: 'P1', capIncrease: 100, transferToI1: 80 }],
    )
    expect(diffs).toHaveLength(1)
    expect(diffs[0].messages.length).toBeGreaterThanOrEqual(2)
  })

  it('AI 关键词建议五条件', () => {
    const conds = suggestCas6ConditionsFromText({
      projectContent: '原型测试通过，技术可行',
      capBasis: '董事会立项决议继续开发',
      supportingEvidence: '市场调研与订单',
      personnelComposition: '预算充足，团队配备，单独核算工时领料',
    })
    expect(conds.filter((c) => c.result === 'yes').length).toBeGreaterThanOrEqual(3)
  })
})
