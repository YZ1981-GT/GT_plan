/**
 * `d3ManagedSheets` 单一来源清单的单元判据（Task 16 · Property 12 前端侧）。
 *
 * spec: d3-sync-coverage-via-row-table-engine · Task 16 · Requirements 6.6
 *
 * 后端一致性由 `backend/tests/workpaper_sync/test_d3_frontend_managed_sheet_parity.py` 守护
 * （前端 excelName 集合 == provider `all_managed_sheet_names()`）；本文件只验前端派生判定
 * 本身的正确性 + kind 分桥不混淆。
 */
import { describe, it, expect } from 'vitest'
import {
  D3_MANAGED_SHEETS,
  D3_OO_WIRED_ROWS_CODES,
  isD3ManagedSheet,
  isD3ManagedRowsSheet,
  isD3ManagedAdjudicationSheet,
  isD3OoWiredRowsSheet,
  d3ManagedSheetOf,
} from '../d3ManagedSheets'

describe('d3ManagedSheets 单一来源受管清单', () => {
  it('声明 6 张受管 sheet，短码唯一、sheetKey 唯一', () => {
    expect(D3_MANAGED_SHEETS).toHaveLength(6)
    const codes = D3_MANAGED_SHEETS.map((s) => s.code)
    const keys = D3_MANAGED_SHEETS.map((s) => s.sheetKey)
    expect(new Set(codes).size).toBe(6)
    expect(new Set(keys).size).toBe(6)
  })

  it('kind 分类：D3-2/4/5/6/7 是 rows，D3-1 是 adjudication', () => {
    expect(d3ManagedSheetOf('D3-2')?.kind).toBe('rows')
    expect(d3ManagedSheetOf('D3-4')?.kind).toBe('rows')
    expect(d3ManagedSheetOf('D3-5')?.kind).toBe('rows')
    expect(d3ManagedSheetOf('D3-6')?.kind).toBe('rows')
    expect(d3ManagedSheetOf('D3-7')?.kind).toBe('rows')
    expect(d3ManagedSheetOf('D3-1')?.kind).toBe('adjudication')
  })

  it('isD3ManagedSheet：受管返回 true、非受管（D3-3/D3A/附注）返回 false', () => {
    for (const code of ['D3-1', 'D3-2', 'D3-4', 'D3-5', 'D3-6', 'D3-7']) {
      expect(isD3ManagedSheet(code)).toBe(true)
    }
    for (const code of ['D3-3', 'D3A', '附注上市', '附注国企', 'directory', null, undefined, '']) {
      expect(isD3ManagedSheet(code as string | null | undefined)).toBe(false)
    }
  })

  it('rows / adjudication 两判定互斥（不会切错桥）', () => {
    // rows 判定：只对 rows kind 为真。
    expect(isD3ManagedRowsSheet('D3-2')).toBe(true)
    expect(isD3ManagedRowsSheet('D3-1')).toBe(false)
    // adjudication 判定：只对 adjudication kind 为真。
    expect(isD3ManagedAdjudicationSheet('D3-1')).toBe(true)
    expect(isD3ManagedAdjudicationSheet('D3-2')).toBe(false)
    // 任一受管 sheet 不会同时命中两套桥判定。
    for (const s of D3_MANAGED_SHEETS) {
      const rows = isD3ManagedRowsSheet(s.code)
      const adj = isD3ManagedAdjudicationSheet(s.code)
      expect(rows && adj).toBe(false)
      expect(rows || adj).toBe(true)
    }
  })

  it('诚实边界：只有真正接了 OO 直写宿主的行表才 isD3OoWiredRowsSheet=true（当前仅 D3-2）', () => {
    expect(D3_OO_WIRED_ROWS_CODES).toEqual(['D3-2'])
    expect(isD3OoWiredRowsSheet('D3-2')).toBe(true)
    // D3-4/5/6/7 是受管行表，但当前未接 OO 直写宿主 ⇒ 不假称可切 OO。
    for (const code of ['D3-4', 'D3-5', 'D3-6', 'D3-7']) {
      expect(isD3ManagedRowsSheet(code)).toBe(true)
      expect(isD3OoWiredRowsSheet(code)).toBe(false)
    }
    // D3-1 审定表：既非 rows 桥、更非 OO wired。
    expect(isD3OoWiredRowsSheet('D3-1')).toBe(false)
  })

  it('sheetKey 逐字对齐后端声明（d32/d36/d34/d35/d37/d31-managed）', () => {
    const byCode = Object.fromEntries(D3_MANAGED_SHEETS.map((s) => [s.code, s.sheetKey]))
    expect(byCode['D3-2']).toBe('d32-managed')
    expect(byCode['D3-6']).toBe('d36-managed')
    expect(byCode['D3-4']).toBe('d34-managed')
    expect(byCode['D3-5']).toBe('d35-managed')
    expect(byCode['D3-7']).toBe('d37-managed')
    expect(byCode['D3-1']).toBe('d31-managed')
  })
})
