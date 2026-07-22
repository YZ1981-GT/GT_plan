/**
 * G11 复盘修复守卫测试
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { resolveProcedureSheetKey } from '@/utils/resolveProcedureSheetKey'
import { ALL_CYCLE_PROCEDURE_SHEETS } from '../cycleProcedureSheets'
import { G11_ADJUDICATION_ITEMS } from '../g11Constants'
import { G11_NOTE_SECTION } from '../g11NoteSectionMap'
import { isG11SheetComplete } from '../g11SheetLabels'
import { collectG11SheetConclusions } from '../g11Conclusion'
import { findBalanceSourceForRowKey } from '../g11ReturnRateBalanceMap'
import { CYCLE_ADJUDICATION_CONFIGS } from '../../shared/cycleAdjudicationConfigs'
import { FORMULA_ENGINE_INVENTORY } from '../formulaEngineInventory'

describe('G11 review fixes', () => {
  it('resolveProcedureSheetKey G11 → g11a', () => {
    expect(resolveProcedureSheetKey('G11')).toBe('g11a')
    expect(resolveProcedureSheetKey('G11-1')).toBe('g11a')
    expect(ALL_CYCLE_PROCEDURE_SHEETS.G11A?.sheetCode).toBe('G11A')
  })

  it('附注章节：上市五、69 / 国企八、70', () => {
    expect(G11_NOTE_SECTION.listed).toBe('五、69')
    expect(G11_NOTE_SECTION.soe).toBe('八、70')
  })

  it('cycleAdjudicationConfigs G11-1 与 G11_ADJUDICATION_ITEMS 对齐', () => {
    const cfg = CYCLE_ADJUDICATION_CONFIGS['G11-1']
    expect(cfg).toBeTruthy()
    expect(cfg.rows).toHaveLength(G11_ADJUDICATION_ITEMS.length)
    expect(cfg.rows.map((r) => r.rowKey)).toEqual(G11_ADJUDICATION_ITEMS.map((r) => r.rowKey))
  })

  it('isG11SheetComplete：G11A 不认 G11-proc-*；空数组不算已编制', () => {
    const empty = new Map<string, any>([
      ['G11-detail-rows', { remark: '[]' }],
      ['G11-aje-rows', { remark: '[]' }],
      ['G11-proc-legacy', { conclusion: 'x' }],
    ])
    expect(isG11SheetComplete('G11-2', empty)).toBe(false)
    expect(isG11SheetComplete('G11-3', empty)).toBe(false)
    expect(isG11SheetComplete('G11A', empty)).toBe(false)

    const filled = new Map<string, any>([
      ['G11-detail-rows', { remark: JSON.stringify([{ id: '1' }]) }],
      ['G11-aje-rows', { remark: JSON.stringify([{ id: 'a1' }]) }],
      ['G11A-fv-complete', { conclusion: 'completed' }],
    ])
    expect(isG11SheetComplete('G11-2', filled)).toBe(true)
    expect(isG11SheetComplete('G11-3', filled)).toBe(true)
    expect(isG11SheetComplete('G11A', filled)).toBe(true)
  })

  it('TB 回写单通道：父组件只听 g11:writeback-trial-balance', () => {
    const adj = readFileSync(resolve(__dirname, '../useG11Adjudication.ts'), 'utf8')
    const parent = readFileSync(resolve(__dirname, '../../GtG11InvestmentIncome.vue'), 'utf8')
    expect(adj).toContain("dispatchEvent(new CustomEvent('substantive:adjudicated'")
    expect(adj).toContain("dispatchEvent(new CustomEvent('g11:writeback-trial-balance'")
    expect(parent).toContain("addEventListener('g11:writeback-trial-balance'")
    expect(parent).not.toMatch(/addEventListener\(\s*['"]substantive:adjudicated['"]/)
  })

  it('P2：oei_dividend 优先 1507；oth_debt 优先 1506', () => {
    expect(findBalanceSourceForRowKey('oei_dividend')?.codes[0]).toBe('1507')
    expect(findBalanceSourceForRowKey('oth_debt_hold_interest')?.codes[0]).toBe('1506')
  })

  it('P2：审计结论读 conclusion，兼容旧 remark', () => {
    const legacy = new Map<string, any>([
      ['G11-detail-audit-conclusion', { remark: 'A、未见异常。' }],
      ['G11-adjustment-audit-conclusion', { conclusion: 'B、需调整。' }],
    ])
    const items = collectG11SheetConclusions(legacy)
    expect(items.find((i) => i.code === 'G11-2')?.text).toContain('A、')
    expect(items.find((i) => i.code === 'G11-3')?.text).toContain('B、')
  })

  it('P2：已移除 useG11InvInc* 别名与 inventory 登记', () => {
    expect(FORMULA_ENGINE_INVENTORY.some((e) => e.composable === 'useG11InvIncFormulaEngine')).toBe(false)
    expect(() => readFileSync(resolve(__dirname, '../useG11InvIncFormData.ts'), 'utf8')).toThrow()
    expect(() => readFileSync(resolve(__dirname, '../useG11InvIncDualMode.ts'), 'utf8')).toThrow()
    expect(() => readFileSync(resolve(__dirname, '../useG11InvIncFormulaEngine.ts'), 'utf8')).toThrow()
  })
})
