/**
 * G12 复盘修复守卫测试
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { resolveProcedureSheetKey } from '@/utils/resolveProcedureSheetKey'
import { ALL_CYCLE_PROCEDURE_SHEETS } from '../cycleProcedureSheets'
import { G12_ADJUDICATION_ITEMS, G12_ACCOUNT_CODE } from '../g12Constants'
import { G12_NOTE_SECTION } from '../g12NoteSectionMap'
import { isG12SheetComplete } from '../g12SheetLabels'
import { G12A_PROCEDURE_SHEET } from '../g12VoucherCross'
import { G12_IMPORT_EXPORT_SHEETS } from '../useG12ImportExport'
import { CYCLE_ADJUDICATION_CONFIGS } from '../../shared/cycleAdjudicationConfigs'
import { FORMULA_ENGINE_INVENTORY } from '../formulaEngineInventory'

describe('G12 review fixes', () => {
  it('resolveProcedureSheetKey G12 → g12a', () => {
    expect(resolveProcedureSheetKey('G12')).toBe('g12a')
    expect(resolveProcedureSheetKey('G12-1')).toBe('g12a')
    expect(ALL_CYCLE_PROCEDURE_SHEETS.G12A?.sheetCode).toBe('G12A')
  })

  it('科目与附注：运行时 6103；上市五、70 / 国企八、71', () => {
    expect(G12_ACCOUNT_CODE).toBe('6103')
    expect(G12_NOTE_SECTION.listed).toBe('五、70')
    expect(G12_NOTE_SECTION.soe).toBe('八、71')
  })

  it('cycleAdjudicationConfigs G12-1 与 G12_ADJUDICATION_ITEMS 对齐', () => {
    const cfg = CYCLE_ADJUDICATION_CONFIGS['G12-1']
    expect(cfg.accountCode).toBe('6103')
    expect(cfg.rows).toHaveLength(G12_ADJUDICATION_ITEMS.length)
    expect(cfg.rows.map((r) => r.rowKey)).toEqual(G12_ADJUDICATION_ITEMS.map((r) => r.rowKey))
  })

  it('isG12SheetComplete：G12A 不认 G12-proc-*；空数组不算已编制', () => {
    const empty = new Map<string, any>([
      ['G12-hedge-detail-rows', { remark: '[]' }],
      ['G12-aje-rows', { remark: '[]' }],
      ['G12-proc-legacy', { conclusion: 'x' }],
    ])
    expect(isG12SheetComplete('G12-2', empty)).toBe(false)
    expect(isG12SheetComplete('G12-3', empty)).toBe(false)
    expect(isG12SheetComplete('G12A', empty)).toBe(false)

    const filled = new Map<string, any>([
      ['G12-hedge-detail-rows', { remark: JSON.stringify([{ id: '1' }]) }],
      ['G12-aje-rows', { remark: JSON.stringify([{ id: 'a1' }]) }],
      ['G12A-voucher-complete', { conclusion: 'completed' }],
    ])
    expect(isG12SheetComplete('G12-2', filled)).toBe(true)
    expect(isG12SheetComplete('G12-3', filled)).toBe(true)
    expect(isG12SheetComplete('G12A', filled)).toBe(true)
  })

  it('TB 回写单通道：父组件只听 g12:writeback-trial-balance', () => {
    const adj = readFileSync(resolve(__dirname, '../useG12Adjudication.ts'), 'utf8')
    const parent = readFileSync(resolve(__dirname, '../../GtG12NetHedgeGains.vue'), 'utf8')
    expect(adj).toContain("dispatchEvent(new CustomEvent('substantive:adjudicated'")
    expect(adj).toContain("dispatchEvent(new CustomEvent('g12:writeback-trial-balance'")
    expect(parent).toContain("addEventListener('g12:writeback-trial-balance'")
    expect(parent).not.toMatch(/addEventListener\(\s*['"]substantive:adjudicated['"]/)
  })

  it('G12A 表名与导入清单含 G12-5', () => {
    expect(G12A_PROCEDURE_SHEET).toBe('净敞口套期收益审计程序表G12A')
    expect([...G12_IMPORT_EXPORT_SHEETS]).toEqual(['G12-2', 'G12-3', 'G12-4', 'G12-5', 'G12-6'])
  })

  it('已移除 useG12NetHed* 别名与 inventory 登记', () => {
    expect(FORMULA_ENGINE_INVENTORY.some((e) => e.composable === 'useG12NetHedFormulaEngine')).toBe(false)
    expect(() => readFileSync(resolve(__dirname, '../useG12NetHedFormData.ts'), 'utf8')).toThrow()
    expect(() => readFileSync(resolve(__dirname, '../useG12NetHedDualMode.ts'), 'utf8')).toThrow()
    expect(() => readFileSync(resolve(__dirname, '../useG12NetHedFormulaEngine.ts'), 'utf8')).toThrow()
  })
})
