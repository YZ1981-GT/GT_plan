/**
 * G8 复盘修复守卫测试
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { resolveProcedureSheetKey } from '@/utils/resolveProcedureSheetKey'
import { ALL_CYCLE_PROCEDURE_SHEETS } from '../cycleProcedureSheets'
import { G8_ADJUDICATION_ITEMS, G8_ACCOUNT_CODE, G8_IMPORTABLE_SHEETS } from '../g8Constants'
import { G8_NOTE_SECTION } from '../g8NoteSectionMap'
import { isG8SheetComplete } from '../g8SheetLabels'
import { CYCLE_ADJUDICATION_CONFIGS } from '../../shared/cycleAdjudicationConfigs'

describe('G8 review fixes', () => {
  it('resolveProcedureSheetKey G8 → g8a', () => {
    expect(resolveProcedureSheetKey('G8')).toBe('g8a')
    expect(resolveProcedureSheetKey('G8-1')).toBe('g8a')
    expect(ALL_CYCLE_PROCEDURE_SHEETS.G8A?.sheetCode).toBe('G8A')
  })

  it('科目与附注：1503；上市五、19 / 国企八、19', () => {
    expect(G8_ACCOUNT_CODE).toBe('1503')
    expect(G8_NOTE_SECTION.listed).toBe('五、19')
    expect(G8_NOTE_SECTION.soe).toBe('八、19')
  })

  it('cycleAdjudicationConfigs G8-1 与 G8_ADJUDICATION_ITEMS 对齐', () => {
    const cfg = CYCLE_ADJUDICATION_CONFIGS['G8-1']
    expect(cfg.accountCode).toBe('1503')
    expect(cfg.rows).toHaveLength(G8_ADJUDICATION_ITEMS.length)
    expect(cfg.rows.map((r) => r.rowKey)).toEqual(G8_ADJUDICATION_ITEMS.map((r) => r.rowKey))
  })

  it('isG8SheetComplete：G8A 不认 G8-proc-*；空数组不算已编制', () => {
    const empty = new Map<string, any>([
      ['G8-detail-rows', { remark: '[]' }],
      ['G8-adjustment-rows', { remark: '[]' }],
      ['G8-proc-legacy', { conclusion: 'x' }],
    ])
    expect(isG8SheetComplete('G8-2', empty)).toBe(false)
    expect(isG8SheetComplete('G8-3', empty)).toBe(false)
    expect(isG8SheetComplete('G8A', empty)).toBe(false)

    const filled = new Map<string, any>([
      ['G8-detail-rows', { remark: JSON.stringify([{ id: '1' }]) }],
      ['G8-adjustment-rows', { remark: JSON.stringify([{ id: 'a1' }]) }],
      ['G8A-voucher-complete', { conclusion: 'completed' }],
      ['G8-1-adjudicated-amount', { conclusion: '100' }],
    ])
    expect(isG8SheetComplete('G8-2', filled)).toBe(true)
    expect(isG8SheetComplete('G8-3', filled)).toBe(true)
    expect(isG8SheetComplete('G8A', filled)).toBe(true)
    expect(isG8SheetComplete('G8-1', filled)).toBe(true)
  })

  // spec: tb-writeback-explicit-publish-gate Task 12（test-follows-source）—— G8 已改走显式发布门
  it('TB 回写走显式发布门：publishToTb → POST publish-to-tb；debounce 只 emit 不写 TB；不再监听 g8:writeback', () => {
    const adj = readFileSync(resolve(__dirname, '../useG8Adjudication.ts'), 'utf8')
    const parent = readFileSync(resolve(__dirname, '../../GtG8OtherEquityInstruments.vue'), 'utf8')
    // 数据变化/debounce 只 emit substantive:adjudicated（不写 TB）
    expect(adj).toMatch(/function notifyAdjudicated[\s\S]*substantive:adjudicated/)
    expect(adj).toMatch(/function publishAdjudicatedDebounced[\s\S]*notifyAdjudicated/)
    // 显式发布门：publishToTb 走 POST publish-to-tb
    expect(adj).toContain('publish-to-tb')
    expect(adj).toMatch(/function publishToTb/)
    // 旧的 g8:writeback-trial-balance 单通道已移除
    expect(adj).not.toContain("dispatchEvent(new CustomEvent('g8:writeback-trial-balance'")
    expect(parent).not.toContain("addEventListener('g8:writeback-trial-balance'")
  })

  it('导入清单含 G8-2~6 与附注', () => {
    expect(G8_IMPORTABLE_SHEETS.map((s) => s.code)).toEqual([
      'G8-2', 'G8-3', 'G8-4', 'G8-5', 'G8-6', '附注上市', '附注国企',
    ])
  })

  it('已移除 useG8OthEqu* 别名', () => {
    const dual = readFileSync(resolve(__dirname, '../useG8DualMode.ts'), 'utf8')
    expect(dual).not.toContain('useG8OthEquDualMode')
    const form = readFileSync(resolve(__dirname, '../useG8FormData.ts'), 'utf8')
    expect(form).not.toContain('useG8OthEquFormData')
  })

  it('审计结论写 conclusion（兼容旧 remark）', () => {
    const detail = readFileSync(resolve(__dirname, '../../g8-other-equity-instruments/core/G8TabDetail.vue'), 'utf8')
    const adj = readFileSync(resolve(__dirname, '../../g8-other-equity-instruments/core/G8TabAdjustment.vue'), 'utf8')
    expect(detail).toContain('conclusion: v, remark: null')
    expect(adj).toContain('conclusion: v, remark: null')
  })
})
