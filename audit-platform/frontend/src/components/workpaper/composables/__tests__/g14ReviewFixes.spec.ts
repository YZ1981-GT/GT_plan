/**
 * G14 复盘修复守卫测试
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { resolveProcedureSheetKey } from '@/utils/resolveProcedureSheetKey'
import { ALL_CYCLE_PROCEDURE_SHEETS } from '../cycleProcedureSheets'
import { G14_LINE_ITEMS, G14_ACCOUNT_CODE } from '../g14Constants'
import { G14_NOTE_SECTION } from '../g14NoteSectionMap'
import { isG14SheetComplete } from '../g14SheetLabels'
import { G14_IMPORT_EXPORT_SHEETS } from '../useG14ImportExport'
import { CYCLE_ADJUDICATION_CONFIGS } from '../../shared/cycleAdjudicationConfigs'
import { FORMULA_ENGINE_INVENTORY } from '../formulaEngineInventory'

describe('G14 review fixes', () => {
  it('resolveProcedureSheetKey G14 → g14a', () => {
    expect(resolveProcedureSheetKey('G14')).toBe('g14a')
    expect(resolveProcedureSheetKey('G14-1')).toBe('g14a')
    expect(ALL_CYCLE_PROCEDURE_SHEETS.G14A?.sheetCode).toBe('G14A')
  })

  it('科目与附注：6702；上市三、信用减值损失 / 国企八、73', () => {
    expect(G14_ACCOUNT_CODE).toBe('6702')
    expect(G14_NOTE_SECTION.listed).toBe('三、信用减值损失')
    expect(G14_NOTE_SECTION.soe).toBe('八、73')
  })

  it('cycleAdjudicationConfigs G14-1 与 G14_LINE_ITEMS 对齐', () => {
    const cfg = CYCLE_ADJUDICATION_CONFIGS['G14-1']
    expect(cfg.accountCode).toBe('6702')
    expect(cfg.rows).toHaveLength(G14_LINE_ITEMS.length)
    expect(cfg.rows.map((r) => r.rowKey)).toEqual(G14_LINE_ITEMS.map((r) => r.rowKey))
  })

  it('isG14SheetComplete：G14A 不认 G14-proc-*；空数组不算已编制', () => {
    const empty = new Map<string, any>([
      ['G14-detail-rows', { remark: '[]' }],
      ['G14-aje-rows', { remark: '[]' }],
      ['G14-proc-legacy', { conclusion: 'x' }],
    ])
    expect(isG14SheetComplete('G14-2', empty)).toBe(false)
    expect(isG14SheetComplete('G14-3', empty)).toBe(false)
    expect(isG14SheetComplete('G14A', empty)).toBe(false)

    const filled = new Map<string, any>([
      ['G14-detail-rows', { remark: JSON.stringify([{ id: '1' }]) }],
      ['G14-aje-rows', { remark: JSON.stringify([{ id: 'a1' }]) }],
      ['G14A-voucher-complete', { conclusion: 'completed' }],
      ['G14-1-adjudicated-amount', { conclusion: '100' }],
      ['G14-disclosure-listed', { remark: '{}' }],
      ['G14-disclosure-soe', { remark: '{}' }],
    ])
    expect(isG14SheetComplete('G14-2', filled)).toBe(true)
    expect(isG14SheetComplete('G14-3', filled)).toBe(true)
    expect(isG14SheetComplete('G14A', filled)).toBe(true)
    expect(isG14SheetComplete('G14-1', filled)).toBe(true)
    expect(isG14SheetComplete('附注上市', filled)).toBe(true)
    expect(isG14SheetComplete('附注国企', filled)).toBe(true)
  })

  it('TB 回写单通道：父组件只听 g14:writeback-trial-balance', () => {
    const adj = readFileSync(resolve(__dirname, '../useG14Adjudication.ts'), 'utf8')
    const form = readFileSync(resolve(__dirname, '../useG14FormData.ts'), 'utf8')
    const parent = readFileSync(resolve(__dirname, '../../GtG14CreditImpairmentLoss.vue'), 'utf8')
    expect(adj).toContain("'substantive:adjudicated'")
    expect(adj).toContain("'g14:writeback-trial-balance'")
    expect(form).toContain('/trial-balance/writeback')
    expect(parent).toContain("addEventListener('g14:writeback-trial-balance'")
    expect(parent).not.toMatch(/addEventListener\(\s*['"]substantive:adjudicated['"]/)
  })

  it('导入清单仅 G14-2 / G14-3', () => {
    expect([...G14_IMPORT_EXPORT_SHEETS]).toEqual(['G14-2', 'G14-3'])
  })

  it('已移除 useG14CreImp* 别名与 inventory 登记', () => {
    expect(FORMULA_ENGINE_INVENTORY.some((e) => e.composable === 'useG14CreImpFormulaEngine')).toBe(false)
    expect(() => readFileSync(resolve(__dirname, '../useG14CreImpFormData.ts'), 'utf8')).toThrow()
    expect(() => readFileSync(resolve(__dirname, '../useG14CreImpDualMode.ts'), 'utf8')).toThrow()
    expect(() => readFileSync(resolve(__dirname, '../useG14CreImpFormulaEngine.ts'), 'utf8')).toThrow()
  })
})
