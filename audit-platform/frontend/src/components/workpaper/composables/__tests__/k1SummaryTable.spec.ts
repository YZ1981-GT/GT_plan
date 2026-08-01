/**
 * K1 附注汇总表「其他应收款」推送单测（Requirement 4 / Property 9）.
 *
 * spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
 */
import { describe, expect, it } from 'vitest'
import {
  calcSummaryTieOut,
  emptyK1ListedPayload,
  emptyK1SoePayload,
  readK1SummaryFigures,
} from '../k1DisclosureModel'
import {
  buildK1ListedSubTableData,
  buildK1SoeSubTableData,
} from '../k1DisclosureSyncPayload'
import { K1_LISTED_SUBTABLE, K1_SOE_SUBTABLE } from '../k1NoteSectionMap'

describe('readK1SummaryFigures', () => {
  it('全空 → 四项皆 0', () => {
    const fs = readK1SummaryFigures(new Map())
    expect(fs).toEqual({ interest: 0, dividend: 0, otherReceivable: 0, total: 0 })
  })

  it('优先取 K1-1-audited-net 作其他应收款净值', () => {
    const map = new Map<string, any>([
      ['K1-1-fs-interest', { remark: '100' }],
      ['K1-1-fs-dividend', { remark: '200' }],
      ['K1-1-audited-net', { remark: '5000' }],
    ])
    const fs = readK1SummaryFigures(map)
    expect(fs.otherReceivable).toBe(5000)
  })

  it('无 K1-1-audited-net 时按报表数倒推其他应收款净值', () => {
    const map = new Map<string, any>([
      ['K1-1-fs-interest', { remark: '100' }],
      ['K1-1-fs-dividend', { remark: '200' }],
      ['K1-1-fs-other-total', { remark: '5300' }],
    ])
    const fs = readK1SummaryFigures(map)
    expect(fs.otherReceivable).toBe(5000)
    expect(fs.total).toBe(5300)
  })

  it('无报表数时合计 = 三项之和', () => {
    const map = new Map<string, any>([
      ['K1-1-fs-interest', { remark: '100' }],
      ['K1-1-fs-dividend', { remark: '200' }],
      ['K1-1-audited-net', { remark: '5000' }],
    ])
    const fs = readK1SummaryFigures(map)
    expect(fs.total).toBe(5300)
  })
})

describe('汇总表推送（Property 9：条件表）', () => {
  it('三项全 0 → 不推送汇总表（listed）', () => {
    const data = buildK1ListedSubTableData(
      emptyK1ListedPayload(), '',
      { interest: 0, dividend: 0, otherReceivable: 0, total: 0 },
    )
    expect(data[K1_LISTED_SUBTABLE.summary]).toBeUndefined()
  })

  it('三项全 0 → 不推送汇总表（soe）', () => {
    const data = buildK1SoeSubTableData(
      emptyK1SoePayload(), '',
      { interest: 0, dividend: 0, otherReceivable: 0, total: 0 },
    )
    expect(data[K1_SOE_SUBTABLE.summary]).toBeUndefined()
  })

  it('有值 → 推送四行（listed，含合计）', () => {
    const data = buildK1ListedSubTableData(
      emptyK1ListedPayload(), '',
      { interest: 100, dividend: 200, otherReceivable: 5000, total: 5300 },
    )
    const rows = data[K1_LISTED_SUBTABLE.summary]
    expect(rows).toHaveLength(4)
    expect(rows.map((r) => r.label)).toEqual(['应收利息', '应收股利', '其他应收款', '合计'])
    expect(rows[0]['期末余额']).toBe(100)
    expect(rows[1]['期末余额']).toBe(200)
    expect(rows[2]['期末余额']).toBe(5000)
    expect(rows[3]['期末余额']).toBe(5300)
    expect(rows[3].is_total).toBe(true)
  })

  it('有值 → 推送四行（soe，第三行是「其他应收款项」）', () => {
    const data = buildK1SoeSubTableData(
      emptyK1SoePayload(), '',
      { interest: 100, dividend: 200, otherReceivable: 5000, total: 5300 },
    )
    const rows = data[K1_SOE_SUBTABLE.summary]
    expect(rows.map((r) => r.label)).toEqual(['应收利息', '应收股利', '其他应收款项', '合计'])
  })

  it('仅其中一项非零仍推送（如只有应收利息）', () => {
    const data = buildK1ListedSubTableData(
      emptyK1ListedPayload(), '',
      { interest: 0.01, dividend: 0, otherReceivable: 0, total: 0.01 },
    )
    expect(data[K1_LISTED_SUBTABLE.summary]).toHaveLength(4)
  })

  it('未传 fs 参数时默认零值，不推送（向后兼容既有调用点）', () => {
    const data = buildK1ListedSubTableData(emptyK1ListedPayload())
    expect(data[K1_LISTED_SUBTABLE.summary]).toBeUndefined()
  })
})

describe('calcSummaryTieOut（F8-48）', () => {
  it('三项全 0 → 不适用，视为已匹配', () => {
    const tie = calcSummaryTieOut({ interest: 0, dividend: 0, otherReceivable: 0, total: 0 })
    expect(tie.applicable).toBe(false)
    expect(tie.matched).toBe(true)
  })

  it('明细行之和 = 合计 → matched', () => {
    const tie = calcSummaryTieOut({ interest: 100, dividend: 200, otherReceivable: 5000, total: 5300 })
    expect(tie.applicable).toBe(true)
    expect(tie.sum).toBe(5300)
    expect(tie.matched).toBe(true)
  })

  it('明细行之和 ≠ 合计 → 告警', () => {
    const tie = calcSummaryTieOut({ interest: 100, dividend: 200, otherReceivable: 5000, total: 5000 })
    expect(tie.applicable).toBe(true)
    expect(tie.matched).toBe(false)
    expect(tie.diff).toBe(300)
  })
})
