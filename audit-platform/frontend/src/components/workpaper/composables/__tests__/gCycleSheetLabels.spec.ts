import { describe, it, expect } from 'vitest'
import { resolveG12SheetLabel, isG12SheetComplete } from '../g12SheetLabels'
import { resolveG13SheetLabel, isG13SheetComplete } from '../g13SheetLabels'
import { resolveG14SheetLabel, isG14SheetComplete } from '../g14SheetLabels'

describe('gCycleSheetLabels', () => {
  const sheets = [
    { sheet_name: '审定表G12-1' },
    { sheet_name: '附注披露信息（上市公司）' },
  ]

  it('resolveG12SheetLabel uses availableSheets', () => {
    expect(resolveG12SheetLabel('G12-1', sheets)).toBe('审定表G12-1')
    expect(resolveG12SheetLabel('附注上市', sheets)).toBe('附注披露信息（上市公司）')
  })

  it('isG12SheetComplete detects adjudication data', () => {
    const m = new Map([['G12-adj-prior', { remark: '{}' }]])
    expect(isG12SheetComplete('G12-1', m)).toBe(true)
    expect(isG12SheetComplete('G12-2', m)).toBe(false)
  })

  it('resolveG13SheetLabel fallback', () => {
    expect(resolveG13SheetLabel('G13-2')).toBe('明细表G13-2')
  })

  it('isG13SheetComplete detects detail rows', () => {
    const m = new Map([['G13-detail-rows', { remark: '[{"id":1}]' }]])
    expect(isG13SheetComplete('G13-2', m)).toBe(true)
  })

  it('resolveG14SheetLabel fallback', () => {
    expect(resolveG14SheetLabel('G14A')).toBe('信用减值损失审计程序表G14A')
  })

  it('isG14SheetComplete detects disclosure', () => {
    const m = new Map([['G14-disclosure-listed', { remark: '[]' }]])
    expect(isG14SheetComplete('附注上市', m)).toBe(true)
  })
})
