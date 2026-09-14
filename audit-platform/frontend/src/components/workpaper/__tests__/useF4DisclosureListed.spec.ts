/**
 * useF4DisclosureListed.spec — F4 附注披露（上市公司）
 * 覆盖：F4-1联动、无限量添加行、F4-5账龄超1年提取与同步。
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useF4DisclosureListed,
  extractOverOneYearRows,
} from '../composables/useF4DisclosureListed'
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

describe('extractOverOneYearRows — F4-5账龄超1年提取', () => {
  it('仅保留挂账超过365天且有内容的行', () => {
    const rows = extractOverOneYearRows(JSON.stringify([
      { rowId: 'a', creditor: '甲公司', amount: 100, startDate: isoDaysAgo(500), reason: '合同纠纷' },
      { rowId: 'b', creditor: '乙公司', amount: 200, startDate: isoDaysAgo(100), reason: '正常账期' },
      { rowId: 'c', creditor: '', amount: 0, startDate: isoDaysAgo(800) },
    ]))
    expect(rows).toHaveLength(1)
    expect(rows[0].creditor).toBe('甲公司')
    expect(rows[0].reason).toBe('合同纠纷')
    expect(rows[0].outstandingDays).toBeGreaterThan(365)
  })

  it('非法JSON返回空数组', () => {
    expect(extractOverOneYearRows('oops')).toEqual([])
    expect(extractOverOneYearRows(null)).toEqual([])
  })
})

describe('useF4DisclosureListed — F4-1联动与动态行', () => {
  it('固定性质行联动F4-1：期末=期末审定、上年年末=期初审定', () => {
    const options = buildOptions([
      ['F4-1-adj-nature-rows', JSON.stringify([
        {
          rowKey: 'goods', label: '货款', isFixed: true,
          openingUnadjusted: 1000, openingAje: 30, openingRje: 0,
          closingUnadjusted: 1500, closingAje: 20, closingRje: -10,
        },
      ])],
    ])
    const { natureRows, natureClosingTotal, naturePriorTotal } = useF4DisclosureListed(options)
    const goods = natureRows.value.find((row) => row.sourceKey === 'goods')!
    expect(goods.linked).toBe(true)
    expect(goods.priorBalance).toBe(1030)
    expect(goods.closingBalance).toBe(1510)
    expect(natureClosingTotal.value).toBe(1510)
    expect(naturePriorTotal.value).toBe(1030)
  })

  it('默认生成源表五个性质项目，可无限添加手工行', () => {
    const options = buildOptions([])
    const { natureRows, addNatureRow, updateNatureCell, natureClosingTotal } = useF4DisclosureListed(options)
    expect(natureRows.value.map((row) => row.label)).toEqual([
      '货款', '工程款', '设备款', '服务费', '其他',
    ])
    addNatureRow()
    addNatureRow()
    expect(natureRows.value).toHaveLength(7)
    const manual = natureRows.value[5]
    expect(manual.linked).toBe(false)
    updateNatureCell(manual.rowId, 'label', '设备尾款质保金')
    updateNatureCell(manual.rowId, 'closingBalance', 8888)
    expect(natureRows.value[5].label).toBe('设备尾款质保金')
    expect(natureClosingTotal.value).toBe(8888)
  })

  it('披露合计与F4-1审定合计不一致时预警标记为false', () => {
    const options = buildOptions([
      ['F4-1-adj-nature-rows', JSON.stringify([
        {
          rowKey: 'goods', label: '货款', isFixed: true,
          openingUnadjusted: 0, openingAje: 0, openingRje: 0,
          closingUnadjusted: 1000, closingAje: 0, closingRje: 0,
        },
      ])],
    ])
    const { addNatureRow, natureRows, updateNatureCell, closingMatchesAdjudication } = useF4DisclosureListed(options)
    expect(closingMatchesAdjudication.value).toBe(true)
    addNatureRow()
    const manual = natureRows.value[natureRows.value.length - 1]
    updateNatureCell(manual.rowId, 'closingBalance', 500)
    expect(closingMatchesAdjudication.value).toBe(false)
  })
})

describe('useF4DisclosureListed — F4-5同步', () => {
  const longOutstanding = JSON.stringify([
    { rowId: 'lo-1', creditor: '甲公司', amount: 300, startDate: isoDaysAgo(600), reason: '质量纠纷未决' },
    { rowId: 'lo-2', creditor: '乙公司', amount: 150, startDate: isoDaysAgo(400), reason: '对方注销' },
    { rowId: 'lo-3', creditor: '丙公司', amount: 90, startDate: isoDaysAgo(90), reason: '正常账期' },
  ])

  it('同步仅带入账龄超1年的行，重复同步不重复添加', () => {
    const options = buildOptions([['F4-5-rows', longOutstanding]])
    const { syncFromLongOutstanding, agingRows, agingTotal, pendingSyncCount } = useF4DisclosureListed(options)
    expect(pendingSyncCount.value).toBe(2)
    expect(syncFromLongOutstanding()).toBe(2)
    expect(agingRows.value).toHaveLength(2)
    expect(agingRows.value.map((row) => row.creditor)).toEqual(['甲公司', '乙公司'])
    expect(agingTotal.value).toBe(450)
    expect(pendingSyncCount.value).toBe(0)
    expect(syncFromLongOutstanding()).toBe(0)
    expect(agingRows.value).toHaveLength(2)
  })

  it('已同步行金额跟随F4-5实时联动，原因可在披露表补充', () => {
    const options = buildOptions([['F4-5-rows', longOutstanding]])
    const composable = useF4DisclosureListed(options)
    composable.syncFromLongOutstanding()
    const first = composable.agingRows.value[0]
    expect(first.linked).toBe(true)
    expect(first.amount).toBe(300)

    // F4-5 金额更新 → 披露表自动跟随
    options.allResponses.value.set('F4-5-rows', {
      item_id: 'F4-5-rows',
      conclusion: null,
      remark: JSON.stringify([
        { rowId: 'lo-1', creditor: '甲公司', amount: 380, startDate: isoDaysAgo(600), reason: '质量纠纷未决' },
        { rowId: 'lo-2', creditor: '乙公司', amount: 150, startDate: isoDaysAgo(400), reason: '对方注销' },
      ]),
    })
    expect(composable.agingRows.value[0].amount).toBe(380)

    // 原因可覆盖
    composable.updateAgingCell(first.rowId, 'reason', '质量纠纷未决，已计提预计负债')
    expect(composable.agingRows.value[0].reason).toBe('质量纠纷未决，已计提预计负债')
  })

  it('手工行可自由编辑并删除', () => {
    const options = buildOptions([])
    const { addAgingRow, agingRows, updateAgingCell, removeAgingRow } = useF4DisclosureListed(options)
    addAgingRow()
    const row = agingRows.value[0]
    updateAgingCell(row.rowId, 'creditor', '丁公司')
    updateAgingCell(row.rowId, 'amount', 66)
    updateAgingCell(row.rowId, 'reason', '尾款争议')
    expect(agingRows.value[0]).toMatchObject({ creditor: '丁公司', amount: 66, reason: '尾款争议' })
    removeAgingRow(row.rowId)
    expect(agingRows.value).toHaveLength(0)
  })
})
