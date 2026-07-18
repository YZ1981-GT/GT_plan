import { describe, it, expect } from 'vitest'
import {
  defaultContractCostSheet,
  enrichContractCostProject,
  enrichContractCostProjects,
  calcContractCostTotals,
  migrateContractCostSheet,
  emptyContractCostProject,
  isBlankContractCostProject,
  pruneBlankContractCostProjects,
} from '../useF2ContractCostFormulas'

describe('useF2ContractCostFormulas', () => {
  it('default sheet keeps only one editable project row', () => {
    expect(defaultContractCostSheet().products).toHaveLength(1)
    expect(isBlankContractCostProject(defaultContractCostSheet().products[0])).toBe(true)
  })

  it('prunes reserved blank rows but retains entered projects', () => {
    const entered = { ...emptyContractCostProject(), projectName: '项目A' }
    const rows = [emptyContractCostProject(), entered, emptyContractCostProject()]
    expect(pruneBlankContractCostProjects(rows)).toEqual([entered])
  })

  it('keeps one blank row when all rows are empty', () => {
    const rows = pruneBlankContractCostProjects([
      emptyContractCostProject(),
      emptyContractCostProject(),
    ])
    expect(rows).toHaveLength(1)
    expect(isBlankContractCostProject(rows[0])).toBe(true)
  })

  it('calculates end balance and audited amount', () => {
    const row = {
      ...emptyContractCostProject(),
      opening_equipment: 100,
      increase_equipment: 50,
      decrease_equipment: 20,
      adj_equipment: -10,
    }
    const enriched = enrichContractCostProject(row)
    expect(enriched.end_equipment).toBe(130)
    expect(enriched.audited_equipment).toBe(120)
    expect(enriched.end_subtotal).toBe(130)
    expect(enriched.audited_subtotal).toBe(120)
  })

  it('subtotals sum four categories', () => {
    const row = {
      ...emptyContractCostProject(),
      opening_equipment: 10,
      opening_construction: 20,
      opening_labor: 30,
      opening_other: 40,
    }
    expect(enrichContractCostProject(row).opening_subtotal).toBe(100)
  })

  it('highlights when capitalisation flags fail', () => {
    const row = { ...emptyContractCostProject(), isRecoverable: '否' as const }
    expect(enrichContractCostProject(row).highlight).toBe(true)
  })

  it('column totals aggregate', () => {
    const products = [
      { ...emptyContractCostProject(), opening_equipment: 100, increase_equipment: 0, decrease_equipment: 0 },
      { ...emptyContractCostProject(), opening_equipment: 200, increase_equipment: 0, decrease_equipment: 0 },
    ]
    const enriched = enrichContractCostProjects(products)
    const totals = calcContractCostTotals(enriched)
    expect(totals.opening_subtotal).toBe(300)
    expect(totals.end_subtotal).toBe(300)
  })

  it('migrates legacy array rows', () => {
    const legacy = [{
      id: '1',
      projectName: '项目A',
      opening_equipment: 500,
    }]
    const sheet = migrateContractCostSheet(legacy)
    expect(sheet?.products[0].projectName).toBe('项目A')
    expect(sheet?.products[0].opening_equipment).toBe(500)
  })
})
