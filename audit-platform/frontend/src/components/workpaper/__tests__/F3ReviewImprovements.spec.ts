/**
 * F3 应付票据 — 2026-07-22 复盘改进单测
 *
 * 覆盖：
 * P0-1 供应链票据动态聚合（不再被审定表/附注丢弃）
 * P0-2/P1-5 F3-3 调整分录幂等注入（逾期重分类 / 补提利息）
 *
 * **Validates: 复盘 P0-1 / P0-2 / P1-5**
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

import {
  rowCategoryKey,
  aggregateDetailByCategory,
  buildF3DisclosureClassRows,
  F3_CATEGORY_META,
  type F3DetailRowRaw,
} from '../composables/useF3CrossSheet'
import { injectF3Adjustments } from '../composables/f3AdjustmentInject'
import type { ChecklistResponse } from '../composables/useF3FormData'

// window.dispatchEvent 在 jsdom 下可用；无 jsdom 时兜底
beforeEach(() => {
  if (typeof window !== 'undefined' && !window.dispatchEvent) {
    ;(window as any).dispatchEvent = vi.fn()
  }
})

// ---------------------------------------------------------------------------
// P0-1 票据类别归类
// ---------------------------------------------------------------------------
describe('P0-1 rowCategoryKey 票据类别归类', () => {
  it('银行/商业/供应链关键字匹配，其余归 other', () => {
    expect(rowCategoryKey({ noteType: '银行承兑汇票' })).toBe('bank')
    expect(rowCategoryKey({ noteType: '商业承兑汇票' })).toBe('commercial')
    expect(rowCategoryKey({ noteType: '供应链票据' })).toBe('supplychain')
    expect(rowCategoryKey({ noteType: '其他' })).toBe('other')
    expect(rowCategoryKey({ noteType: '' })).toBe('other')
    expect(rowCategoryKey({})).toBe('other')
  })

  it('F3_CATEGORY_META 覆盖 4 类且键唯一', () => {
    expect(F3_CATEGORY_META).toHaveLength(4)
    const keys = F3_CATEGORY_META.map((m) => m.rowKey)
    expect(new Set(keys).size).toBe(4)
    expect(keys).toEqual(['bank', 'commercial', 'supplychain', 'other'])
  })
})

// ---------------------------------------------------------------------------
// P0-1 按类别聚合：供应链票据不丢失
// ---------------------------------------------------------------------------
describe('P0-1 aggregateDetailByCategory 供应链票据不丢失', () => {
  const rows: F3DetailRowRaw[] = [
    { noteType: '银行承兑汇票', openingBalance: 100, currentIssued: 50, currentAccepted: 10 },
    { noteType: '商业承兑汇票', openingBalance: 200, currentIssued: 30, currentAccepted: 20 },
    { noteType: '供应链票据', openingBalance: 300, currentIssued: 80, currentAccepted: 5 },
  ]

  it('三类分别聚合，本期发生与期末数正确归集', () => {
    const agg = aggregateDetailByCategory(rows)
    expect(agg.bank.count).toBe(1)
    expect(agg.commercial.count).toBe(1)
    expect(agg.supplychain.count).toBe(1)
    expect(agg.other.count).toBe(0)

    expect(agg.bank.periodCredit).toBe(50)
    expect(agg.bank.periodDebit).toBe(10)
    // 银行期末审定 = 100 + 50 - 10 = 140
    expect(agg.bank.closingAdjusted).toBe(140)
    // 供应链期末审定 = 300 + 80 - 5 = 375（此前会被丢弃）
    expect(agg.supplychain.closingAdjusted).toBe(375)
  })

  it('明细合计 = 各类别期末审定之和（口径一致）', () => {
    const agg = aggregateDetailByCategory(rows)
    const sum = agg.bank.closingAdjusted + agg.commercial.closingAdjusted
      + agg.supplychain.closingAdjusted + agg.other.closingAdjusted
    // 140 + 210 + 375 + 0
    expect(sum).toBe(140 + 210 + 375)
  })
})

// ---------------------------------------------------------------------------
// P0-1 附注分类行构建
// ---------------------------------------------------------------------------
describe('P0-1 buildF3DisclosureClassRows 附注分类行', () => {
  it('银行/商业始终列示；供应链有明细时列示', () => {
    const adj = JSON.stringify([
      { rowKey: 'bank', openingUnadjusted: 100, openingAje: 0, openingRje: 0, closingAje: 0, closingRje: 0 },
      { rowKey: 'commercial', openingUnadjusted: 200, openingAje: 0, openingRje: 0, closingAje: 0, closingRje: 0 },
    ])
    const detail = JSON.stringify([
      { noteType: '银行承兑汇票', openingBalance: 100, currentIssued: 50, currentAccepted: 10 },
      { noteType: '供应链票据', openingBalance: 0, currentIssued: 375, currentAccepted: 0 },
    ])
    const rows = buildF3DisclosureClassRows(adj, detail)
    const byKey = Object.fromEntries(rows.map((r) => [r.rowKey, r]))
    expect(byKey.bank).toBeDefined()
    expect(byKey.commercial).toBeDefined()
    expect(byKey.supplychain).toBeDefined()
    // 供应链期末 = 期初审定0 + 本期开票375 - 兑付0 = 375
    expect(byKey.supplychain.endAmount).toBe(375)
    // 银行期末 = 100(期初审定) + 50 - 10 = 140
    expect(byKey.bank.endAmount).toBe(140)
  })

  it('无供应链明细时不列示供应链行；银行/商业仍在', () => {
    const adj = JSON.stringify([
      { rowKey: 'bank', openingUnadjusted: 100, openingAje: 0, openingRje: 0, closingAje: 0, closingRje: 0 },
    ])
    const rows = buildF3DisclosureClassRows(adj, JSON.stringify([]))
    const keys = rows.map((r) => r.rowKey)
    expect(keys).toContain('bank')
    expect(keys).toContain('commercial')
    expect(keys).not.toContain('supplychain')
    expect(keys).not.toContain('other')
  })

  it('期末数含期末 AJE/RJE 调整', () => {
    const adj = JSON.stringify([
      { rowKey: 'bank', openingUnadjusted: 100, openingAje: 0, openingRje: 0, closingAje: 5, closingRje: -2 },
    ])
    const detail = JSON.stringify([
      { noteType: '银行承兑汇票', openingBalance: 100, currentIssued: 0, currentAccepted: 0 },
    ])
    const rows = buildF3DisclosureClassRows(adj, detail)
    const bank = rows.find((r) => r.rowKey === 'bank')!
    // 期初审定100 + 本期0 + AJE5 + RJE(-2) = 103
    expect(bank.endAmount).toBe(103)
  })
})

// ---------------------------------------------------------------------------
// P0-2 / P1-5 F3-3 调整分录幂等注入
// ---------------------------------------------------------------------------
describe('P0-2/P1-5 injectF3Adjustments 幂等注入', () => {
  function getRows(map: Map<string, ChecklistResponse>): any[] {
    const raw = map.get('F3-3-rows')?.remark
    return raw ? JSON.parse(raw) : []
  }

  it('写入调整分录并携带 sourceKind、seq 连续', () => {
    const map = new Map<string, ChecklistResponse>()
    const n = injectF3Adjustments(map, [
      { entryType: 'RJE', summary: '逾期重分类', accountCode: '2201', accountName: '应付票据', debitAmount: 100, creditAmount: 0 },
      { entryType: 'RJE', summary: '逾期重分类', accountCode: '2001', accountName: '短期借款', debitAmount: 0, creditAmount: 100 },
    ], 'overdue-reclass')
    expect(n).toBe(2)
    const rows = getRows(map)
    expect(rows).toHaveLength(2)
    expect(rows[0].sourceKind).toBe('overdue-reclass')
    expect(rows.map((r) => r.seq)).toEqual([1, 2])
  })

  it('重复注入同 sourceKind 幂等替换（不累积）', () => {
    const map = new Map<string, ChecklistResponse>()
    injectF3Adjustments(map, [
      { entryType: 'RJE', summary: 'A', accountCode: '2201', accountName: '应付票据', debitAmount: 100, creditAmount: 0 },
    ], 'overdue-reclass')
    injectF3Adjustments(map, [
      { entryType: 'RJE', summary: 'B', accountCode: '2201', accountName: '应付票据', debitAmount: 200, creditAmount: 0 },
      { entryType: 'RJE', summary: 'B', accountCode: '2202', accountName: '应付账款', debitAmount: 0, creditAmount: 200 },
    ], 'overdue-reclass')
    const rows = getRows(map)
    expect(rows).toHaveLength(2)
    expect(rows.every((r) => r.summary === 'B')).toBe(true)
  })

  it('不同 sourceKind 各自保留（逾期重分类 + 补提利息共存）', () => {
    const map = new Map<string, ChecklistResponse>()
    injectF3Adjustments(map, [
      { entryType: 'RJE', summary: '逾期重分类', accountCode: '2201', accountName: '应付票据', debitAmount: 100, creditAmount: 0 },
    ], 'overdue-reclass')
    injectF3Adjustments(map, [
      { entryType: 'AJE', summary: '补提利息', accountCode: '6603', accountName: '财务费用', debitAmount: 30, creditAmount: 0 },
      { entryType: 'AJE', summary: '补提利息', accountCode: '2231', accountName: '应付利息', debitAmount: 0, creditAmount: 30 },
    ], 'interest-accrual')
    const rows = getRows(map)
    expect(rows).toHaveLength(3)
    expect(rows.filter((r) => r.sourceKind === 'overdue-reclass')).toHaveLength(1)
    expect(rows.filter((r) => r.sourceKind === 'interest-accrual')).toHaveLength(2)
    // 借贷平衡（补提部分）
    const accrual = rows.filter((r) => r.sourceKind === 'interest-accrual')
    const debit = accrual.reduce((s, r) => s + r.debitAmount, 0)
    const credit = accrual.reduce((s, r) => s + r.creditAmount, 0)
    expect(debit).toBe(credit)
  })

  it('保留用户手工分录（无 sourceKind），仅替换同源生成项', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F3-3-rows', {
      item_id: 'F3-3-rows',
      conclusion: null,
      remark: JSON.stringify([
        { rowId: 'manual1', seq: 1, entryType: 'AJE', summary: '手工分录', accountCode: '2201', accountName: '应付票据', debitAmount: 0, creditAmount: 500, preparer: '张三', remark: '' },
      ]),
    })
    injectF3Adjustments(map, [
      { entryType: 'RJE', summary: '逾期重分类', accountCode: '2201', accountName: '应付票据', debitAmount: 100, creditAmount: 0 },
    ], 'overdue-reclass')
    const rows = getRows(map)
    expect(rows).toHaveLength(2)
    expect(rows.find((r) => r.summary === '手工分录')).toBeDefined()
    expect(rows.find((r) => r.sourceKind === 'overdue-reclass')).toBeDefined()
  })
})
