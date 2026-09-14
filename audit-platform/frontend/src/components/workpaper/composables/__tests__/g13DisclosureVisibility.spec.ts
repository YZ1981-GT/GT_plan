/**
 * G13 上市附注 — 空项省略与「其中」父子逻辑
 */
import { describe, it, expect } from 'vitest'
import { G13_DISCLOSURE_LISTED_ROWS, G13_DISCLOSURE_SOE_ROWS, G13_DISCLOSURE_TEMPLATE_HINT } from '../g13Constants'
import {
  filterG13DisclosureRows,
  hasG13DisclosureAmount,
  isG13DisclosureRowVisible,
  g13DisclosureHasAnyAmount,
} from '../g13DisclosureVisibility'
import { buildG13NoteTextFromRows } from '../g13NoteText'

const listedDefs = G13_DISCLOSURE_LISTED_ROWS
const soeDefs = G13_DISCLOSURE_SOE_ROWS

function listedRows(partial: Record<string, { current?: number; prior?: number; remark?: string }> = {}) {
  return listedDefs.map((d) => ({
    rowKey: d.rowKey,
    label: d.label,
    currentAmount: partial[d.rowKey]?.current ?? 0,
    priorAmount: partial[d.rowKey]?.prior ?? 0,
    remark: partial[d.rowKey]?.remark ?? '',
  }))
}

describe('g13DisclosureVisibility', () => {
  it('全空时 includeEmpty=false 隐藏全部', () => {
    const rows = listedRows()
    expect(filterG13DisclosureRows(rows, listedDefs, { includeEmpty: true })).toHaveLength(9)
    expect(filterG13DisclosureRows(rows, listedDefs, { includeEmpty: false })).toHaveLength(0)
    expect(g13DisclosureHasAnyAmount(rows)).toBe(false)
  })

  it('空其中隐藏；有数其中强制保留空主行', () => {
    const rows = listedRows({ designated_fv_assets: { current: 30 } })
    expect(filterG13DisclosureRows(rows, listedDefs).map((r) => r.rowKey)).toEqual([
      'trading_assets',
      'designated_fv_assets',
    ])
    expect(isG13DisclosureRowVisible('designated_fv_assets', rows, listedDefs)).toBe(true)
  })

  it('国企空行过滤', () => {
    const rows = soeDefs.map((d) => ({
      rowKey: d.rowKey,
      label: d.label,
      currentAmount: d.rowKey === 'trading_assets' ? 10 : 0,
      priorAmount: 0,
    }))
    expect(filterG13DisclosureRows(rows, soeDefs).map((r) => r.rowKey)).toEqual(['trading_assets'])
  })

  it('hasG13DisclosureAmount 容忍浮点零；备注也算有数', () => {
    expect(hasG13DisclosureAmount({ currentAmount: 0.001, priorAmount: 0 })).toBe(false)
    expect(hasG13DisclosureAmount({ currentAmount: 0.01, priorAmount: 0 })).toBe(true)
    expect(hasG13DisclosureAmount({ currentAmount: 0, priorAmount: 0, remark: '说明' })).toBe(true)
  })
})

describe('buildG13NoteTextFromRows', () => {
  it('省略空行与模板提示', () => {
    const rows = listedRows({
      trading_assets: { current: 200, prior: 100 },
      designated_fv_assets: { current: 50 },
    })
    const text = buildG13NoteTextFromRows(rows, 'listed', { adjudicatedAmount: 200 })
    expect(text).toContain('与 G13-1 审定数 200.00 元勾稽一致')
    expect(text).toContain('交易性金融资产')
    expect(text).not.toContain('衍生金融工具')
    expect(text).not.toContain(G13_DISCLOSURE_TEMPLATE_HINT)
  })
})
