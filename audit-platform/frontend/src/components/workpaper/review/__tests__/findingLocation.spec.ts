/**
 * AI 复核疑点来源地址 → 平台格定位（spec llm-linkage-audit-practice-closure 任务 10）。
 */
import { describe, expect, it } from 'vitest'
import { parseFindingLocation } from '../findingLocation'

describe('parseFindingLocation', () => {
  it('表名!单元格 拆成表与格，格统一大写、去掉 $', () => {
    expect(parseFindingLocation('审定表D2-1!c8')).toEqual({ sheetName: '审定表D2-1', cellRef: 'C8' })
    expect(parseFindingLocation("'明细表 D2-2'!$AB$120")).toEqual({ sheetName: '明细表 D2-2', cellRef: 'AB120' })
  })

  it('只有单元格时表名留空，由调用方取疑点所属的表', () => {
    expect(parseFindingLocation('F12')).toEqual({ sheetName: null, cellRef: 'F12' })
  })

  it('只有表名或不是地址时按表名处理，不臆造单元格', () => {
    expect(parseFindingLocation('审定表D2-1')).toEqual({ sheetName: '审定表D2-1', cellRef: null })
    expect(parseFindingLocation('期初余额与上年不一致')).toEqual({ sheetName: '期初余额与上年不一致', cellRef: null })
    expect(parseFindingLocation('')).toEqual({ sheetName: null, cellRef: null })
    expect(parseFindingLocation(null)).toEqual({ sheetName: null, cellRef: null })
  })
})
