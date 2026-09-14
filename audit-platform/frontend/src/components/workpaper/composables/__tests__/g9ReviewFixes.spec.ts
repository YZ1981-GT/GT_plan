/**
 * G9 复盘修复守卫测试
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { resolveProcedureSheetKey } from '@/utils/resolveProcedureSheetKey'
import { ALL_CYCLE_PROCEDURE_SHEETS } from '../cycleProcedureSheets'
import { G9_ADJUDICATION_ITEMS, G9_ACCOUNT_CODE } from '../g9Constants'
import { G9_NOTE_SECTION } from '../g9NoteSectionMap'
import { isG9SheetComplete } from '../g9SheetLabels'
import { G9_IMPORTABLE_SHEETS } from '../useG9ImportExport'
import { CYCLE_ADJUDICATION_CONFIGS } from '../../shared/cycleAdjudicationConfigs'

describe('G9 review fixes', () => {
  it('resolveProcedureSheetKey G9 → g9a', () => {
    expect(resolveProcedureSheetKey('G9')).toBe('g9a')
    expect(resolveProcedureSheetKey('G9-1')).toBe('g9a')
    expect(ALL_CYCLE_PROCEDURE_SHEETS.G9A?.sheetCode).toBe('G9A')
  })

  it('科目与附注：1519；上市五、20 / 国企八、20', () => {
    expect(G9_ACCOUNT_CODE).toBe('1519')
    expect(G9_NOTE_SECTION.listed).toBe('五、20')
    expect(G9_NOTE_SECTION.soe).toBe('八、20')
  })

  it('cycleAdjudicationConfigs G9-1 与 G9_ADJUDICATION_ITEMS 对齐', () => {
    const cfg = CYCLE_ADJUDICATION_CONFIGS['G9-1']
    expect(cfg.accountCode).toBe('1519')
    expect(cfg.rows).toHaveLength(G9_ADJUDICATION_ITEMS.length)
    expect(cfg.rows.map((r) => r.rowKey)).toEqual(G9_ADJUDICATION_ITEMS.map((r) => r.rowKey))
  })

  it('isG9SheetComplete：G9A 不认 G9-proc-*；空数组不算已编制', () => {
    const empty = new Map<string, any>([
      ['G9-detail-rows', { remark: '[]' }],
      ['G9-adjustment-rows', { remark: '[]' }],
      ['G9-proc-legacy', { conclusion: 'x' }],
    ])
    expect(isG9SheetComplete('G9-2', empty)).toBe(false)
    expect(isG9SheetComplete('G9-3', empty)).toBe(false)
    expect(isG9SheetComplete('G9A', empty)).toBe(false)

    const filled = new Map<string, any>([
      ['G9-detail-rows', { remark: JSON.stringify([{ id: '1' }]) }],
      ['G9-adjustment-rows', { remark: JSON.stringify([{ id: 'a1' }]) }],
      ['G9A-voucher-complete', { conclusion: 'completed' }],
      ['G9-1-adjudicated-amount', { conclusion: '100' }],
      ['G9-disclosure-listed', { remark: '{}' }],
      ['G9-disclosure-soe', { remark: '{}' }],
    ])
    expect(isG9SheetComplete('G9-2', filled)).toBe(true)
    expect(isG9SheetComplete('G9-3', filled)).toBe(true)
    expect(isG9SheetComplete('G9A', filled)).toBe(true)
    expect(isG9SheetComplete('G9-1', filled)).toBe(true)
    expect(isG9SheetComplete('附注上市', filled)).toBe(true)
    expect(isG9SheetComplete('附注国企', filled)).toBe(true)
  })

  it('TB 回写单通道：父组件只听 g9:writeback-trial-balance', () => {
    const adj = readFileSync(resolve(__dirname, '../useG9Adjudication.ts'), 'utf8')
    const form = readFileSync(resolve(__dirname, '../useG9FormData.ts'), 'utf8')
    const parent = readFileSync(resolve(__dirname, '../../GtG9OtherNoncurrentFinancial.vue'), 'utf8')
    expect(adj).toContain("'substantive:adjudicated'")
    expect(adj).toContain("'g9:writeback-trial-balance'")
    expect(form).toContain('/trial-balance/writeback')
    expect(parent).toContain("addEventListener('g9:writeback-trial-balance'")
    expect(parent).not.toMatch(/addEventListener\(\s*['"]substantive:adjudicated['"]/)
  })

  it('导入清单含 G9-2~6 与附注', () => {
    expect(G9_IMPORTABLE_SHEETS.map((s) => s.code)).toEqual([
      'G9-2', 'G9-3', 'G9-4', 'G9-5', 'G9-6', '附注上市', '附注国企',
    ])
  })

  it('已移除 useG9OthNcf* / OthNon 别名', () => {
    expect(() => readFileSync(resolve(__dirname, '../useG9OthNcfFormData.ts'), 'utf8')).toThrow()
    const dual = readFileSync(resolve(__dirname, '../useG9DualMode.ts'), 'utf8')
    expect(dual).not.toContain('useG9OthNonDualMode')
    const form = readFileSync(resolve(__dirname, '../useG9FormData.ts'), 'utf8')
    expect(form).not.toContain('useG9OthNcfFormData')
  })

  it('审计结论写 conclusion（兼容旧 remark）', () => {
    const detail = readFileSync(resolve(__dirname, '../../g9-other-noncurrent-financial/core/G9TabDetail.vue'), 'utf8')
    const adj = readFileSync(resolve(__dirname, '../../g9-other-noncurrent-financial/core/G9TabAdjustment.vue'), 'utf8')
    expect(detail).toContain('conclusion: v, remark: null')
    expect(adj).toContain('conclusion: v, remark: null')
  })
})
