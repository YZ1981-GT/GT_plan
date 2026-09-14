/**
 * G10 复盘修复守卫测试
 */
import { describe, expect, it } from 'vitest'
import { resolveProcedureSheetKey } from '@/utils/resolveProcedureSheetKey'
import { G10_IMPORTABLE_SHEETS, resolveG10ImportableSheet } from '../useG10ImportExport'
import { isG10SheetComplete } from '../g10SheetLabels'
import { ALL_CYCLE_PROCEDURE_SHEETS } from '../cycleProcedureSheets'

describe('G10 review fixes', () => {
  it('resolveProcedureSheetKey G10 → g10a', () => {
    expect(resolveProcedureSheetKey('G10')).toBe('g10a')
    expect(resolveProcedureSheetKey('G10-4')).toBe('g10a')
    expect(ALL_CYCLE_PROCEDURE_SHEETS.G10A?.sheetCode).toBe('G10A')
  })

  it('G10-4 / G10-8 已纳入导入导出清单', () => {
    const codes = G10_IMPORTABLE_SHEETS.map((s) => s.code)
    expect(codes).toContain('G10-4')
    expect(codes).toContain('G10-8')
    expect(resolveG10ImportableSheet('分类的适当性检查表G10-4')).toBe('G10-4')
    expect(resolveG10ImportableSheet('衍生金融工具核查表G10-8')).toBe('G10-8')
  })

  it('isG10SheetComplete：空数组不算已编制；G10A 不认 G10-proc-*；G10-4 兼容旧 conclusion 存行', () => {
    const empty = new Map<string, any>([
      ['G10-classification-rows', { remark: '[]' }],
      ['G10-derivative-rows', { remark: '[]' }],
      ['G10-proc-legacy', { conclusion: 'x' }],
    ])
    expect(isG10SheetComplete('G10-4', empty)).toBe(false)
    expect(isG10SheetComplete('G10-8', empty)).toBe(false)
    expect(isG10SheetComplete('G10A', empty)).toBe(false)

    const legacyConclusion = new Map<string, any>([
      ['G10-classification-rows', { conclusion: JSON.stringify([{ id: '1', liabilityName: '旧存' }]) }],
    ])
    expect(isG10SheetComplete('G10-4', legacyConclusion)).toBe(true)

    const filled = new Map<string, any>([
      ['G10-classification-rows', { remark: JSON.stringify([{ id: '1', liabilityName: 'A' }]) }],
      ['G10-derivative-rows', { remark: JSON.stringify([{ rowId: 'r1', checkItem: 'x' }]) }],
      ['G10A-fv-complete', { conclusion: 'completed' }],
    ])
    expect(isG10SheetComplete('G10-4', filled)).toBe(true)
    expect(isG10SheetComplete('G10-8', filled)).toBe(true)
    expect(isG10SheetComplete('G10A', filled)).toBe(true)
  })
})
