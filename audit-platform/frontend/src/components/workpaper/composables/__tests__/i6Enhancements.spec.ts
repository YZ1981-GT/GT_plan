import { describe, it, expect } from 'vitest'
import {
  buildI6AdjudicationAuditNoteDraft,
  pickI6HighChangeRateRows,
} from '../i6AdjudicationNoteDraft'
import { resolveI6ExpenseNature } from '../i6DisclosureModel'
import { resolveI6DisclosureVisibility } from '../i6ApplicableSheets'

describe('i6AdjudicationNoteDraft', () => {
  it('builds draft for rows with change rate > 30%', () => {
    const draft = buildI6AdjudicationAuditNoteDraft([
      { 类别: '人工费', 上期审定: 100, 本期审定: 150, 变动额: 50, 变动率: 0.5, changeRateHighlight: true },
      { 类别: '材料费', 上期审定: 80, 本期审定: 85, 变动额: 5, 变动率: 0.0625 },
    ])
    expect(draft).toContain('人工费')
    expect(draft).toContain('变动率超过30%')
    expect(draft).not.toContain('材料费')
  })

  it('pickI6HighChangeRateRows respects threshold', () => {
    const rows = pickI6HighChangeRateRows([
      { 类别: 'A', 上期审定: 0, 本期审定: 10, 变动额: 10, 变动率: 1 },
    ])
    expect(rows).toHaveLength(1)
  })
})

describe('i6 expenseNature column', () => {
  it('resolveI6ExpenseNature prefers X column', () => {
    expect(resolveI6ExpenseNature({ category: '项目A', expenseNature: '人工费' })).toBe('人工费')
    expect(resolveI6ExpenseNature({ category: '人工费' })).toBe('人工费')
  })
})

describe('i6ApplicableSheets', () => {
  it('hides listed when only soe standard', () => {
    const vis = resolveI6DisclosureVisibility(['soe_standalone'])
    expect(vis.listed).toBe(false)
    expect(vis.soe).toBe(true)
  })

  it('shows both when no standards', () => {
    const vis = resolveI6DisclosureVisibility([])
    expect(vis.listed).toBe(true)
    expect(vis.soe).toBe(true)
  })
})
