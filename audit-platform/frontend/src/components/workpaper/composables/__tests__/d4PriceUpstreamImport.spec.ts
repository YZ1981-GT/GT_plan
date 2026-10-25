/**
 * d4PriceUpstreamImport 守卫 —— D4-10/11 上游取数 merge 语义（Property 2）
 *
 * Spec: .kiro/specs/d4-price-analysis-writeback-linkage/ Requirements 2.2 / 3.2 / Property 2
 *
 * 断言 merge **行为**：并集导入上游行；不覆盖已有手工行的非导入字段。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { mergeCustomers, mergeProducts } from '../d4PriceUpstreamMerge'

const mkCustomerRow = (name: string, amount: number) => ({
  seq: null, customer: name, product: '', amount, quantity: 0, unitPrice: 0, avgPrice: 0, avgReason: '', marketPrice: 0, marketReason: '',
})
const mkProductRow = (product: string) => ({
  customer: '', product, unitPrice: 0, quantity: 0, invoiceDate: '', orderNo: '', orderDate: '', listPrice: 0, marketPrice: 0, reason: '', priceSource: '', remark: '',
})

describe('mergeCustomers（D4-10 从 D4-9 导入客户，Property 2）', () => {
  it('空表导入 → 全部新增', () => {
    const rows: any[] = []
    const s = mergeCustomers(rows, [{ name: '客户A', amount: 100 }, { name: '客户B', amount: 200 }], mkCustomerRow)
    expect(s).toEqual({ added: 2, updated: 0 })
    expect(rows.map(r => r.customer)).toEqual(['客户A', '客户B'])
    expect(rows[0].amount).toBe(100)
  })

  it('已有手工行（改过单价）→ 不覆盖手工字段，仅补空金额', () => {
    const rows = [{ ...mkCustomerRow('客户A', 0), unitPrice: 88, avgReason: '手工原因' }]
    const s = mergeCustomers(rows, [{ name: '客户A', amount: 500 }], mkCustomerRow)
    expect(s).toEqual({ added: 0, updated: 1 })
    expect(rows[0].amount).toBe(500)      // 空金额被补
    expect(rows[0].unitPrice).toBe(88)    // 手工单价不动
    expect(rows[0].avgReason).toBe('手工原因')
  })

  it('已有手工金额 → 不覆盖', () => {
    const rows = [{ ...mkCustomerRow('客户A', 999) }]
    const s = mergeCustomers(rows, [{ name: '客户A', amount: 500 }], mkCustomerRow)
    expect(s).toEqual({ added: 0, updated: 0 })
    expect(rows[0].amount).toBe(999)
  })

  it('PBT: 结果客户名集 = 原集 ∪ 上游集', () => {
    fc.assert(
      fc.property(
        fc.uniqueArray(fc.constantFrom('A', 'B', 'C', 'D'), { maxLength: 4 }),
        fc.uniqueArray(fc.constantFrom('A', 'B', 'C', 'D', 'E'), { maxLength: 5 }),
        (existing, upstream) => {
          const rows = existing.map(n => mkCustomerRow(n, 0))
          mergeCustomers(rows, upstream.map(n => ({ name: n, amount: 1 })), mkCustomerRow)
          const got = new Set(rows.map(r => r.customer))
          const want = new Set([...existing, ...upstream])
          expect(got).toEqual(want)
        },
      ),
      { numRuns: 30 },
    )
  })
})

describe('mergeProducts（D4-11 从 D4-2 导入产品，Property 2）', () => {
  it('并集导入，已存在品种跳过', () => {
    const rows = [mkProductRow('产品A')]
    const s = mergeProducts(rows, [{ product: '产品A', revenue: 1 }, { product: '产品B', revenue: 2 }], mkProductRow)
    expect(s.added).toBe(1)
    expect(rows.map(r => r.product)).toEqual(['产品A', '产品B'])
  })

  it('不覆盖已存在品种的手工字段', () => {
    const rows = [{ ...mkProductRow('产品A'), unitPrice: 55 }]
    mergeProducts(rows, [{ product: '产品A', revenue: 999 }], mkProductRow)
    expect(rows).toHaveLength(1)
    expect(rows[0].unitPrice).toBe(55) // 手工单价不动
  })

  it('空品种名跳过', () => {
    const rows: any[] = []
    const s = mergeProducts(rows, [{ product: '  ', revenue: 1 }, { product: '产品X', revenue: 2 }], mkProductRow)
    expect(s.added).toBe(1)
    expect(rows.map(r => r.product)).toEqual(['产品X'])
  })
})
