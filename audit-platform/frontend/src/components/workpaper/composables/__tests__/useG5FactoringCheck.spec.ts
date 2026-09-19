import { describe, expect, it } from 'vitest'
import {
  applyConclusionToRow,
  createJudgmentSteps,
  emptyRow,
  suggestJudgmentConclusion,
  useG5FactoringCheck,
} from '../useG5FactoringCheck'

describe('useG5FactoringCheck', () => {
  it('九步决策树：步骤6符合 → 终止确认', () => {
    const steps = createJudgmentSteps()
    steps.find(s => s.stepId === 's6')!.judgment = '符合'
    expect(suggestJudgmentConclusion(steps)).toBe('终止确认')
  })

  it('九步决策树：步骤7符合 → 不终止确认（质押）', () => {
    const steps = createJudgmentSteps()
    steps.find(s => s.stepId === 's7')!.judgment = '符合'
    expect(suggestJudgmentConclusion(steps)).toBe('不终止确认（继续确认，作质押融资处理）')
  })

  it('九步决策树：步骤8符合 → 继续涉入', () => {
    const steps = createJudgmentSteps()
    steps.find(s => s.stepId === 's8')!.judgment = '符合'
    expect(suggestJudgmentConclusion(steps)).toBe('按继续涉入程度确认')
  })

  it('applyConclusionToRow 同步 treatment / derecognition', () => {
    const row = emptyRow({ amount: 100 })
    applyConclusionToRow(row, '终止确认')
    expect(row.treatment).toBe('derecognized')
    expect(row.derecognition).toBe('是')
    expect(row.derecognizedAmount).toBe(100)

    applyConclusionToRow(row, '按继续涉入程度确认')
    expect(row.treatment).toBe('continuing')

    applyConclusionToRow(row, '不终止确认（继续确认，作质押融资处理）')
    expect(row.treatment).toBe('pledged')
    expect(row.derecognition).toBe('否')
  })

  it('loadRows 兼容旧扁平格式并分类', () => {
    const fc = useG5FactoringCheck()
    fc.loadRows([
      { id: 'a', debtor: '甲', amount: 10, method: '无追索', derecognition: '是', basis: '', conclusion: '', indexRef: '', factor: '' },
      { id: 'b', debtor: '乙', amount: 20, method: '有追索', derecognition: '否', basis: '', conclusion: '不终止确认', indexRef: '', factor: '' },
    ] as any)
    expect(fc.rows.value).toHaveLength(2)
    expect(fc.derecognizedRows.value.some(r => r.debtor === '甲')).toBe(true)
    expect(fc.warningRows.value).toHaveLength(0)
  })

  it('有追索 + 终止确认进入警示', () => {
    const fc = useG5FactoringCheck()
    const row = emptyRow({ debtor: '丙', method: '有追索', amount: 50 })
    applyConclusionToRow(row, '终止确认')
    fc.upsertRow(row)
    expect(fc.warningRows.value).toHaveLength(1)
  })
})
