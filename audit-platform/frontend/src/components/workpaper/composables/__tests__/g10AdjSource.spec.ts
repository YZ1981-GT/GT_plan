import { describe, expect, it } from 'vitest'
import {
  countG10AdjBySource,
  filterG10AdjRows,
  g10AdjSourceFilterFromEvent,
  isFromG105,
  isG10AdjZeroAmountMemoRow,
  resolveG10AdjSource,
} from '../g10AdjSource'

describe('g10AdjSource', () => {
  it('resolveG10AdjSource 识别各来源', () => {
    expect(resolveG10AdjSource({ summary: 'G10-5 公允测试差异：A', indexRef: 'G10-5' })).toBe('g105')
    expect(resolveG10AdjSource({ summary: 'G10-6 L3调节差异：A', indexRef: 'G10-6', remark: '来自 G10-6' })).toBe('g106')
    expect(resolveG10AdjSource({ summary: 'G10-7 凭证异常：记-1', indexRef: 'G10-7', remark: '来自 G10-7' })).toBe('g107')
    expect(resolveG10AdjSource({ summary: 'G10-8 衍生不合规：2', indexRef: 'G10-8' })).toBe('g108')
    expect(resolveG10AdjSource({ summary: 'G10-4 重分类—A', indexRef: 'G10-4', remark: '由 G10-4 分类检查生成' })).toBe('g104')
    expect(resolveG10AdjSource({ summary: '手工', sourceGroupId: 'mod-1' })).toBe('module')
    expect(resolveG10AdjSource({ summary: '手工录入' })).toBe('manual')
  })

  it('isFromG105 不与 G10-7/8 冲突', () => {
    expect(isFromG105({ summary: 'G10-5 差异', indexRef: 'G10-5' })).toBe(true)
    expect(isFromG105({ summary: 'G10-7 凭证异常', indexRef: 'G10-7' })).toBe(false)
  })

  it('filterG10AdjRows 按来源筛选', () => {
    const rows = [
      { summary: 'G10-5 公允测试差异：A', indexRef: 'G10-5' },
      { summary: 'G10-7 凭证异常', indexRef: 'G10-7', remark: '来自 G10-7' },
      { summary: '手工' },
    ]
    expect(filterG10AdjRows(rows, 'g105')).toHaveLength(1)
    expect(filterG10AdjRows(rows, 'g107')).toHaveLength(1)
    expect(filterG10AdjRows(rows, 'manual')).toHaveLength(1)
    expect(countG10AdjBySource(rows).g105).toBe(1)
  })

  it('g10AdjSourceFilterFromEvent 映射跨表来源', () => {
    expect(g10AdjSourceFilterFromEvent('G10-4')).toBe('pending_g104')
    expect(g10AdjSourceFilterFromEvent('G10-5')).toBe('g105')
    expect(g10AdjSourceFilterFromEvent('G10-6')).toBe('g106')
    expect(g10AdjSourceFilterFromEvent('G10-7')).toBe('g107')
    expect(g10AdjSourceFilterFromEvent('G10-8')).toBe('g108')
    expect(g10AdjSourceFilterFromEvent(undefined)).toBeNull()
  })

  it('零金额备忘识别', () => {
    const row = {
      summary: 'G10-8 衍生不合规',
      indexRef: 'G10-8',
      debitAmount: 0,
      creditAmount: 0,
      remark: '来自 G10-8 衍生工具核查；金额待追查补录',
    }
    expect(isG10AdjZeroAmountMemoRow(row)).toBe(true)
    expect(filterG10AdjRows([row], 'zero_memo')).toHaveLength(1)
  })
})
