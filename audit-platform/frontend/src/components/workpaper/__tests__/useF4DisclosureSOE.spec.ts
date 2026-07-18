/**
 * useF4DisclosureSOE.spec — F4 附注披露（国企）
 * 覆盖：F4-1按账龄联动、按性质交叉核对、F4-5账龄超1年同步、手工行。
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useF4DisclosureSOE } from '../composables/useF4DisclosureSOE'
import type { ChecklistResponse } from '../composables/useF4FormData'

function isoDaysAgo(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() - days)
  return date.toISOString().slice(0, 10)
}

function buildOptions(entries: Array<[string, string]>) {
  const allResponses = ref(new Map<string, ChecklistResponse>(
    entries.map(([key, remark]) => [key, { item_id: key, conclusion: null, remark }]),
  ))
  return {
    wpId: ref('wp1'),
    projectId: ref('p1'),
    allResponses,
    isReadonly: ref(false),
  }
}

describe('useF4DisclosureSOE — 按账龄联动F4-1', () => {
  it('账龄行取F4-1审定数：期末=期末审定、期初=期初审定', () => {
    const options = buildOptions([
      ['F4-1-adj-aging-rows', JSON.stringify([
        {
          rowKey: 'within1year', label: '1年以内（含1年）', isFixed: true,
          openingUnadjusted: 800, openingAje: 50, openingRje: 0,
          closingUnadjusted: 1200, closingAje: -20, closingRje: 10,
        },
        {
          rowKey: '3yearplus', label: '3年以上', isFixed: true,
          openingUnadjusted: 100, openingAje: 0, openingRje: 0,
          closingUnadjusted: 60, closingAje: 0, closingRje: 0,
        },
      ])],
    ])
    const { agingRows, agingClosingTotal, agingOpeningTotal } = useF4DisclosureSOE(options)
    const within = agingRows.value.find((row) => row.rowKey === 'within1year')!
    expect(within.openingBalance).toBe(850)
    expect(within.closingBalance).toBe(1190)
    const over3 = agingRows.value.find((row) => row.rowKey === '3yearplus')!
    expect(over3.closingBalance).toBe(60)
    expect(agingClosingTotal.value).toBe(1250)
    expect(agingOpeningTotal.value).toBe(950)
  })

  it('无F4-1数据时默认生成账龄区间且金额为零', () => {
    const { agingRows, agingClosingTotal } = useF4DisclosureSOE(buildOptions([]))
    expect(agingRows.value.map((row) => row.rowKey)).toEqual([
      'within1year', '1to2year', '2to3year', '3yearplus', 'aging-other',
    ])
    expect(agingClosingTotal.value).toBe(0)
  })

  it('按账龄合计与F4-1按性质合计交叉核对', () => {
    const options = buildOptions([
      ['F4-1-adj-aging-rows', JSON.stringify([
        { rowKey: 'within1year', label: '1年以内（含1年）', isFixed: true, closingUnadjusted: 1000 },
      ])],
      ['F4-1-adj-nature-rows', JSON.stringify([
        { rowKey: 'goods', label: '货款', isFixed: true, closingUnadjusted: 1000 },
      ])],
    ])
    const matched = useF4DisclosureSOE(options)
    expect(matched.closingMatchesNature.value).toBe(true)

    const mismatchOptions = buildOptions([
      ['F4-1-adj-aging-rows', JSON.stringify([
        { rowKey: 'within1year', label: '1年以内（含1年）', isFixed: true, closingUnadjusted: 1000 },
      ])],
      ['F4-1-adj-nature-rows', JSON.stringify([
        { rowKey: 'goods', label: '货款', isFixed: true, closingUnadjusted: 900 },
      ])],
    ])
    const mismatched = useF4DisclosureSOE(mismatchOptions)
    expect(mismatched.closingMatchesNature.value).toBe(false)
  })

  it('1年以上账龄披露合计=各1年以上区间之和', () => {
    const options = buildOptions([
      ['F4-1-adj-aging-rows', JSON.stringify([
        { rowKey: 'within1year', label: '1年以内（含1年）', isFixed: true, closingUnadjusted: 1000 },
        { rowKey: '1to2year', label: '1至2年（含2年）', isFixed: true, closingUnadjusted: 200 },
        { rowKey: '3yearplus', label: '3年以上', isFixed: true, closingUnadjusted: 50 },
      ])],
    ])
    const { overOneYearAgingTotal } = useF4DisclosureSOE(options)
    expect(overOneYearAgingTotal.value).toBe(250)
  })
})

describe('useF4DisclosureSOE — 重要应付账款联动F4-5', () => {
  const longOutstanding = JSON.stringify([
    { rowId: 'lo-1', creditor: '甲公司', amount: 300, startDate: isoDaysAgo(600), reason: '质量纠纷未决' },
    { rowId: 'lo-2', creditor: '乙公司', amount: 150, startDate: isoDaysAgo(400), reason: '对方注销' },
    { rowId: 'lo-3', creditor: '丙公司', amount: 90, startDate: isoDaysAgo(90), reason: '正常账期' },
  ])

  it('同步仅带入账龄超1年的行，重复同步不重复添加', () => {
    const options = buildOptions([['F4-5-rows', longOutstanding]])
    const { syncFromLongOutstanding, importantRows, importantTotal, pendingSyncCount } = useF4DisclosureSOE(options)
    expect(pendingSyncCount.value).toBe(2)
    expect(syncFromLongOutstanding()).toBe(2)
    expect(importantRows.value).toHaveLength(2)
    expect(importantRows.value.map((row) => row.creditor)).toEqual(['甲公司', '乙公司'])
    expect(importantTotal.value).toBe(450)
    expect(syncFromLongOutstanding()).toBe(0)
    expect(importantRows.value).toHaveLength(2)
  })

  it('已同步行金额与原因跟随F4-5，披露表补充的原因优先', () => {
    const options = buildOptions([['F4-5-rows', longOutstanding]])
    const composable = useF4DisclosureSOE(options)
    composable.syncFromLongOutstanding()
    const first = composable.importantRows.value[0]
    expect(first.linked).toBe(true)
    expect(first.amount).toBe(300)
    expect(first.reason).toBe('质量纠纷未决')

    options.allResponses.value.set('F4-5-rows', {
      item_id: 'F4-5-rows',
      conclusion: null,
      remark: JSON.stringify([
        { rowId: 'lo-1', creditor: '甲公司', amount: 380, startDate: isoDaysAgo(600), reason: '质量纠纷未决' },
        { rowId: 'lo-2', creditor: '乙公司', amount: 150, startDate: isoDaysAgo(400), reason: '对方注销' },
      ]),
    })
    expect(composable.importantRows.value[0].amount).toBe(380)

    composable.updateImportantCell(first.rowId, 'reason', '质量纠纷未决，已计提预计负债')
    expect(composable.importantRows.value[0].reason).toBe('质量纠纷未决，已计提预计负债')
  })

  it('手工行可自由编辑并删除', () => {
    const options = buildOptions([])
    const { addImportantRow, importantRows, updateImportantCell, removeImportantRow } = useF4DisclosureSOE(options)
    addImportantRow()
    const row = importantRows.value[0]
    expect(row.linked).toBe(false)
    updateImportantCell(row.rowId, 'creditor', '丁公司')
    updateImportantCell(row.rowId, 'amount', 66)
    updateImportantCell(row.rowId, 'reason', '尾款争议')
    expect(importantRows.value[0]).toMatchObject({ creditor: '丁公司', amount: 66, reason: '尾款争议' })
    removeImportantRow(row.rowId)
    expect(importantRows.value).toHaveLength(0)
  })
})
