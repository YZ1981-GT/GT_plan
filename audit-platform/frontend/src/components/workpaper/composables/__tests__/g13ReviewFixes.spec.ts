/**
 * G13 复盘修复守卫测试
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { resolveProcedureSheetKey } from '@/utils/resolveProcedureSheetKey'
import { ALL_CYCLE_PROCEDURE_SHEETS } from '../cycleProcedureSheets'
import { G13_ADJUDICATION_ITEMS, G13_ACCOUNT_CODE } from '../g13Constants'
import { G13_NOTE_SECTION } from '../g13NoteSectionMap'
import { isG13SheetComplete } from '../g13SheetLabels'
import { CYCLE_ADJUDICATION_CONFIGS } from '../../shared/cycleAdjudicationConfigs'
import { FORMULA_ENGINE_INVENTORY } from '../formulaEngineInventory'

describe('G13 review fixes', () => {
  it('resolveProcedureSheetKey G13 → g13a', () => {
    expect(resolveProcedureSheetKey('G13')).toBe('g13a')
    expect(resolveProcedureSheetKey('G13-1')).toBe('g13a')
    expect(ALL_CYCLE_PROCEDURE_SHEETS.G13A?.sheetCode).toBe('G13A')
  })

  it('科目与附注：6101；上市三、公允价值变动收益 / 国企八、72', () => {
    expect(G13_ACCOUNT_CODE).toBe('6101')
    expect(G13_NOTE_SECTION.listed).toBe('三、公允价值变动收益')
    expect(G13_NOTE_SECTION.soe).toBe('八、72')
  })

  it('cycleAdjudicationConfigs G13-1 与 G13_ADJUDICATION_ITEMS 对齐', () => {
    const cfg = CYCLE_ADJUDICATION_CONFIGS['G13-1']
    expect(cfg.accountCode).toBe('6101')
    expect(cfg.rows).toHaveLength(G13_ADJUDICATION_ITEMS.length)
    expect(cfg.rows.map((r) => r.rowKey)).toEqual(G13_ADJUDICATION_ITEMS.map((r) => r.rowKey))
  })

  it('isG13SheetComplete：G13A 不认 G13-proc-*；空数组不算已编制', () => {
    const empty = new Map<string, any>([
      ['G13-detail-rows', { remark: '[]' }],
      ['G13-aje-rows', { remark: '[]' }],
      ['G13-proc-legacy', { conclusion: 'x' }],
    ])
    expect(isG13SheetComplete('G13-2', empty)).toBe(false)
    expect(isG13SheetComplete('G13-3', empty)).toBe(false)
    expect(isG13SheetComplete('G13A', empty)).toBe(false)

    const filled = new Map<string, any>([
      ['G13-detail-rows', { remark: JSON.stringify([{ id: '1' }]) }],
      ['G13-aje-rows', { remark: JSON.stringify([{ id: 'a1' }]) }],
      ['G13A-voucher-complete', { conclusion: 'completed' }],
    ])
    expect(isG13SheetComplete('G13-2', filled)).toBe(true)
    expect(isG13SheetComplete('G13-3', filled)).toBe(true)
    expect(isG13SheetComplete('G13A', filled)).toBe(true)
  })

  it('TB 回写单通道：显式发布发 g13:writeback；父组件只听该事件', () => {
    const adj = readFileSync(resolve(__dirname, '../useG13Adjudication.ts'), 'utf8')
    const form = readFileSync(resolve(__dirname, '../useG13FormData.ts'), 'utf8')
    const parent = readFileSync(resolve(__dirname, '../../GtG13FairValueChanges.vue'), 'utf8')
    expect(adj).toContain("'g13:writeback-trial-balance'")
    expect(adj).toMatch(/function publishAdjudicated[\s\S]*g13:writeback-trial-balance/)
    expect(adj).toMatch(/function broadcastAdjudicated[\s\S]*substantive:adjudicated/)
    expect(form).toContain('/trial-balance/writeback')
    expect(parent).toContain("addEventListener('g13:writeback-trial-balance'")
    expect(parent).not.toMatch(/addEventListener\(\s*['"]substantive:adjudicated['"]/)
  })

  it('已移除 useG13FaiVal* 别名与 inventory 登记', () => {
    expect(FORMULA_ENGINE_INVENTORY.some((e) => e.composable === 'useG13FaiValFormulaEngine')).toBe(false)
    expect(() => readFileSync(resolve(__dirname, '../useG13FaiValFormData.ts'), 'utf8')).toThrow()
    expect(() => readFileSync(resolve(__dirname, '../useG13FaiValDualMode.ts'), 'utf8')).toThrow()
    expect(() => readFileSync(resolve(__dirname, '../useG13FaiValFormulaEngine.ts'), 'utf8')).toThrow()
  })

  it('审计结论写 conclusion（兼容旧 remark）', () => {
    const detail = readFileSync(resolve(__dirname, '../../g13-fair-value-changes/G13TabDetail.vue'), 'utf8')
    const adj = readFileSync(resolve(__dirname, '../../g13-fair-value-changes/G13TabAdjustment.vue'), 'utf8')
    expect(detail).toContain('debouncedSave(CONCLUSION_KEY, { conclusion: val, remark: null })')
    expect(adj).toContain('debouncedSave(CONCLUSION_KEY, { conclusion: val, remark: null })')
  })
})
