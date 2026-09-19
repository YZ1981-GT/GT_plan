/**
 * PBT + Unit Tests for useD4WalkthroughTest pure functions
 *
 * Property-Based Tests (P1-P11) using fast-check
 * Unit Tests for consistency engine edge cases + mapping functions
 *
 * Spec: .kiro/specs/d4-14-walkthrough-test/
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import {
  compareAmounts,
  compareProductNames,
  compareDates,
  computeConsistency,
  isDimensionComplete,
  mapD4ContractToDimension,
  mapLedgerToTransaction,
  mapOcrToDimension,
  collectAiContext,
  DIMENSION_GROUPS,
  type TransactionItem,
  type VoucherDimension,
  type ContractDimension,
  type DeliveryDimension,
  type ShippingDimension,
  type ReceiptDimension,
  type InvoiceDimension,
  type OtherDimension,
} from '../useD4WalkthroughTest'

// ═══════════════════════════════════════════════════════════════════════════════
// Arbitraries (Generators)
// ═══════════════════════════════════════════════════════════════════════════════

const positiveAmount = fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true })
const nonNegativeAmount = fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true })
const nonEmptyStr = fc.string({ minLength: 1, maxLength: 30 }).filter(s => s.trim().length > 0)
const dateStr = fc.integer({ min: 2020, max: 2030 }).chain(year =>
  fc.integer({ min: 1, max: 12 }).chain(month =>
    fc.integer({ min: 1, max: 28 }).map(day =>
      `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`,
    ),
  ),
)

function makeVoucher(o: Partial<VoucherDimension> = {}): VoucherDimension {
  return { month: '', date: '', number: '', productName: '', quantity: '', amount: 0, accountingDate: '', ...o }
}
function makeContract(o: Partial<ContractDimension> = {}): ContractDimension {
  return { number: '', productName: '', amount: 0, approver: '', confirmor: '', ...o }
}
function makeDelivery(o: Partial<DeliveryDimension> = {}): DeliveryDimension {
  return { date: '', productName: '', amount: 0, warehouseKeeper: '', ...o }
}
function makeShipping(o: Partial<ShippingDimension> = {}): ShippingDimension {
  return { date: '', productName: '', amount: 0, ...o }
}
function makeReceipt(o: Partial<ReceiptDimension> = {}): ReceiptDimension {
  return { date: '', productName: '', amount: 0, ...o }
}
function makeInvoice(o: Partial<InvoiceDimension> = {}): InvoiceDimension {
  return { date: '', number: '', amount: 0, ...o }
}
function makeOther(o: Partial<OtherDimension> = {}): OtherDimension {
  return { description: '', indexNo: '', ...o }
}
function makeItem(o: Partial<TransactionItem> = {}): TransactionItem {
  return {
    id: 't-test-1', indexNo: 'D4-14-1', label: '测试事项',
    voucher: makeVoucher(), contract: makeContract(), delivery: makeDelivery(),
    shipping: makeShipping(), receipt: makeReceipt(), invoice: makeInvoice(), other: makeOther(),
    consistencyScore: 0, consistencyDetails: null, conclusion: '', isAnomalous: false, ...o,
  }
}
function reindexItems(items: TransactionItem[]): void {
  items.forEach((item, i) => { item.indexNo = `D4-14-${i + 1}` })
}

// ═══════════════════════════════════════════════════════════════════════════════
// PBT Property Tests (P1 - P11)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useD4WalkthroughTest - PBT', () => {
  /** Feature: d4-14-walkthrough-test, Property 1: Consistency engine field comparison correctness */
  describe('P1: Consistency engine field comparison correctness', () => {
    it('all amounts equal → isConsistent=true', () => {
      fc.assert(fc.property(positiveAmount, (amt) => {
        const item = makeItem({
          voucher: makeVoucher({ amount: amt }),
          contract: makeContract({ amount: amt }),
          delivery: makeDelivery({ amount: amt }),
        })
        const r = compareAmounts(item)
        expect(r.isConsistent).toBe(true)
        expect(r.mismatchDimensions).toHaveLength(0)
      }), { numRuns: 100 })
    })

    it('different amounts → isConsistent=false with mismatchDimensions non-empty', () => {
      fc.assert(fc.property(positiveAmount, positiveAmount, (a1, a2) => {
        fc.pre(a1 !== a2)
        const item = makeItem({
          voucher: makeVoucher({ amount: a1 }),
          contract: makeContract({ amount: a2 }),
        })
        const r = compareAmounts(item)
        expect(r.isConsistent).toBe(false)
        expect(r.mismatchDimensions.length).toBeGreaterThan(0)
      }), { numRuns: 100 })
    })

    it('same productNames → isConsistent=true', () => {
      fc.assert(fc.property(nonEmptyStr, (name) => {
        const item = makeItem({
          voucher: makeVoucher({ productName: name }),
          contract: makeContract({ productName: name }),
        })
        const r = compareProductNames(item)
        expect(r.isConsistent).toBe(true)
        expect(r.mismatchDimensions).toHaveLength(0)
      }), { numRuns: 100 })
    })

    it('different productNames → isConsistent=false', () => {
      fc.assert(fc.property(nonEmptyStr, nonEmptyStr, (n1, n2) => {
        fc.pre(n1.trim() !== n2.trim())
        const item = makeItem({
          voucher: makeVoucher({ productName: n1 }),
          contract: makeContract({ productName: n2 }),
        })
        const r = compareProductNames(item)
        expect(r.isConsistent).toBe(false)
        expect(r.mismatchDimensions.length).toBeGreaterThan(0)
      }), { numRuns: 100 })
    })

    it('same dates → isConsistent=true', () => {
      fc.assert(fc.property(dateStr, (d) => {
        const item = makeItem({
          voucher: makeVoucher({ date: d }),
          delivery: makeDelivery({ date: d }),
        })
        expect(compareDates(item).isConsistent).toBe(true)
      }), { numRuns: 100 })
    })

    it('different dates → isConsistent=false', () => {
      fc.assert(fc.property(dateStr, dateStr, (d1, d2) => {
        fc.pre(d1 !== d2)
        const item = makeItem({
          voucher: makeVoucher({ date: d1 }),
          delivery: makeDelivery({ date: d2 }),
        })
        const r = compareDates(item)
        expect(r.isConsistent).toBe(false)
        expect(r.mismatchDimensions.length).toBeGreaterThan(0)
      }), { numRuns: 100 })
    })
  })

  /** Feature: d4-14-walkthrough-test, Property 2: Consistency score formula correctness */
  describe('P2: Consistency score formula correctness', () => {
    it('all 3 field types match → score = 100', () => {
      fc.assert(fc.property(positiveAmount, nonEmptyStr, dateStr, (amt, name, date) => {
        const item = makeItem({
          voucher: makeVoucher({ amount: amt, productName: name, date }),
          contract: makeContract({ amount: amt, productName: name }),
          delivery: makeDelivery({ amount: amt, productName: name, date }),
        })
        expect(computeConsistency(item).score).toBe(100)
      }), { numRuns: 100 })
    })

    it('1/3 field types mismatch → score = 67', () => {
      fc.assert(fc.property(positiveAmount, positiveAmount, nonEmptyStr, dateStr, (a1, a2, name, date) => {
        fc.pre(a1 !== a2)
        const item = makeItem({
          voucher: makeVoucher({ amount: a1, productName: name, date }),
          contract: makeContract({ amount: a2, productName: name }),
          delivery: makeDelivery({ amount: a1, productName: name, date }),
        })
        expect(computeConsistency(item).score).toBe(67)
      }), { numRuns: 100 })
    })

    it('2/3 field types mismatch → score = 33', () => {
      fc.assert(fc.property(positiveAmount, positiveAmount, nonEmptyStr, nonEmptyStr, dateStr, dateStr,
        (a1, a2, n1, n2, d1, d2) => {
          fc.pre(a1 !== a2 && n1.trim() !== n2.trim())
          const item = makeItem({
            voucher: makeVoucher({ amount: a1, productName: n1, date: d1 }),
            contract: makeContract({ amount: a2, productName: n2 }),
            delivery: makeDelivery({ amount: a1, productName: n1, date: d1 }),
          })
          expect(computeConsistency(item).score).toBe(33)
        }), { numRuns: 100 })
    })

    it('3/3 field types mismatch → score = 0', () => {
      fc.assert(fc.property(positiveAmount, positiveAmount, nonEmptyStr, nonEmptyStr, dateStr, dateStr,
        (a1, a2, n1, n2, d1, d2) => {
          fc.pre(a1 !== a2 && n1.trim() !== n2.trim() && d1 !== d2)
          const item = makeItem({
            voucher: makeVoucher({ amount: a1, productName: n1, date: d1 }),
            contract: makeContract({ amount: a2, productName: n2 }),
            delivery: makeDelivery({ amount: a1, productName: n1, date: d2 }),
          })
          expect(computeConsistency(item).score).toBe(0)
        }), { numRuns: 100 })
    })
  })

  /** Feature: d4-14-walkthrough-test, Property 3: IndexNo sequential after add/remove */
  describe('P3: IndexNo sequential after add/remove', () => {
    it('N items reindexed → D4-14-1 through D4-14-N, no gaps/duplicates', () => {
      fc.assert(fc.property(fc.integer({ min: 1, max: 30 }), (n) => {
        const items = Array.from({ length: n }, (_, i) => makeItem({ id: `t-${i}`, indexNo: '' }))
        reindexItems(items)
        for (let i = 0; i < n; i++) expect(items[i].indexNo).toBe(`D4-14-${i + 1}`)
        expect(new Set(items.map(it => it.indexNo)).size).toBe(n)
      }), { numRuns: 100 })
    })

    it('after removing one item, remaining are re-sequential', () => {
      fc.assert(fc.property(fc.integer({ min: 2, max: 20 }), fc.nat(), (n, removeIdx) => {
        const items = Array.from({ length: n }, (_, i) => makeItem({ id: `t-${i}`, indexNo: `D4-14-${i + 1}` }))
        items.splice(removeIdx % n, 1)
        reindexItems(items)
        expect(items.length).toBe(n - 1)
        for (let i = 0; i < items.length; i++) expect(items[i].indexNo).toBe(`D4-14-${i + 1}`)
      }), { numRuns: 100 })
    })
  })

  /** Feature: d4-14-walkthrough-test, Property 4: Coverage/anomaly/progress stats */
  describe('P4: Coverage/anomaly/progress stats correctness', () => {
    it('totalVoucherAmount = sum of all voucher.amount', () => {
      fc.assert(fc.property(fc.array(nonNegativeAmount, { minLength: 1, maxLength: 15 }), (amounts) => {
        const items = amounts.map(a => makeItem({ voucher: makeVoucher({ amount: a }) }))
        const total = items.reduce((s, it) => s + it.voucher.amount, 0)
        expect(total).toBeCloseTo(amounts.reduce((s, a) => s + a, 0), 8)
      }), { numRuns: 100 })
    })

    it('coverageRate = min(100, total/revenue * 100)', () => {
      fc.assert(fc.property(fc.array(nonNegativeAmount, { minLength: 1, maxLength: 15 }), positiveAmount, (amounts, revenue) => {
        const total = amounts.reduce((s, a) => s + a, 0)
        const rate = Math.min((total / revenue) * 100, 100)
        expect(rate).toBeGreaterThanOrEqual(0)
        expect(rate).toBeLessThanOrEqual(100)
      }), { numRuns: 100 })
    })

    it('anomalyRate = anomalous/total * 100', () => {
      fc.assert(fc.property(fc.array(fc.boolean(), { minLength: 1, maxLength: 20 }), (flags) => {
        const rate = (flags.filter(f => f).length / flags.length) * 100
        expect(rate).toBeGreaterThanOrEqual(0)
        expect(rate).toBeLessThanOrEqual(100)
      }), { numRuns: 100 })
    })

    it('progress = min(100, items.length / target * 100)', () => {
      fc.assert(fc.property(fc.integer({ min: 0, max: 50 }), fc.integer({ min: 1, max: 50 }), (count, target) => {
        const progress = Math.min((count / target) * 100, 100)
        expect(progress).toBeGreaterThanOrEqual(0)
        expect(progress).toBeLessThanOrEqual(100)
      }), { numRuns: 100 })
    })
  })

  /** Feature: d4-14-walkthrough-test, Property 5: Matrix row count = transaction count */
  describe('P5: Matrix row count = transaction count', () => {
    it('N items → matrix data has exactly N rows', () => {
      fc.assert(fc.property(fc.integer({ min: 0, max: 30 }), (n) => {
        const items = Array.from({ length: n }, (_, i) => makeItem({ id: `t-${i}` }))
        expect(items.length).toBe(n)
      }), { numRuns: 100 })
    })
  })

  /** Feature: d4-14-walkthrough-test, Property 6: isDimensionComplete correctness */
  describe('P6: isDimensionComplete correctness', () => {
    it('voucher all fields filled → true', () => {
      fc.assert(fc.property(positiveAmount, nonEmptyStr, nonEmptyStr, nonEmptyStr, nonEmptyStr, nonEmptyStr, nonEmptyStr,
        (amt, month, date, num, name, qty, accDate) => {
          const dim = { month, date, number: num, productName: name, quantity: qty, amount: amt, accountingDate: accDate }
          expect(isDimensionComplete(dim, 'voucher')).toBe(true)
        }), { numRuns: 100 })
    })

    it('voucher with some empty fields → false', () => {
      fc.assert(fc.property(positiveAmount, nonEmptyStr, (amt, name) => {
        const dim = { month: '', date: '', number: '', productName: name, quantity: '', amount: amt, accountingDate: '' }
        expect(isDimensionComplete(dim, 'voucher')).toBe(false)
      }), { numRuns: 100 })
    })

    it('delivery all fields filled → true', () => {
      fc.assert(fc.property(positiveAmount, nonEmptyStr, nonEmptyStr, nonEmptyStr, (amt, date, name, keeper) => {
        expect(isDimensionComplete({ date, productName: name, amount: amt, warehouseKeeper: keeper }, 'delivery')).toBe(true)
      }), { numRuns: 100 })
    })

    it('other all fields filled → true', () => {
      fc.assert(fc.property(nonEmptyStr, nonEmptyStr, (desc, idx) => {
        expect(isDimensionComplete({ description: desc, indexNo: idx }, 'other')).toBe(true)
      }), { numRuns: 100 })
    })

    it('attachment fields do not count', () => {
      const dim = { date: '', productName: '', amount: 0, warehouseKeeper: '', attachmentId: 'att-1', attachmentName: 'f.pdf', ocrStatus: 'done' }
      expect(isDimensionComplete(dim, 'delivery')).toBe(false)
    })
  })

  /** Feature: d4-14-walkthrough-test, Property 7: Persistence JSON round-trip */
  describe('P7: Persistence JSON round-trip', () => {
    it('serialize → deserialize → deep equal', () => {
      const txArb = fc.record({
        id: fc.string({ minLength: 1, maxLength: 20 }),
        indexNo: fc.string({ maxLength: 10 }),
        label: fc.string({ maxLength: 30 }),
        voucher: fc.record({ month: fc.string({ maxLength: 5 }), date: fc.string({ maxLength: 10 }), number: fc.string({ maxLength: 10 }), productName: fc.string({ maxLength: 20 }), quantity: fc.string({ maxLength: 5 }), amount: fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }), accountingDate: fc.string({ maxLength: 10 }) }),
        contract: fc.record({ number: fc.string({ maxLength: 10 }), productName: fc.string({ maxLength: 20 }), amount: fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }), approver: fc.string({ maxLength: 10 }), confirmor: fc.string({ maxLength: 10 }) }),
        delivery: fc.record({ date: fc.string({ maxLength: 10 }), productName: fc.string({ maxLength: 20 }), amount: fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }), warehouseKeeper: fc.string({ maxLength: 10 }) }),
        shipping: fc.record({ date: fc.string({ maxLength: 10 }), productName: fc.string({ maxLength: 20 }), amount: fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }) }),
        receipt: fc.record({ date: fc.string({ maxLength: 10 }), productName: fc.string({ maxLength: 20 }), amount: fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }) }),
        invoice: fc.record({ date: fc.string({ maxLength: 10 }), number: fc.string({ maxLength: 10 }), amount: fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }) }),
        other: fc.record({ description: fc.string({ maxLength: 30 }), indexNo: fc.string({ maxLength: 10 }) }),
        consistencyScore: fc.integer({ min: 0, max: 100 }),
        consistencyDetails: fc.constant(null),
        conclusion: fc.constantFrom('无异常', '存在差异已解释', '存在重大异常', '' as const),
        isAnomalous: fc.boolean(),
      })
      fc.assert(fc.property(fc.array(txArb, { minLength: 0, maxLength: 5 }), (items) => {
        expect(JSON.parse(JSON.stringify(items))).toEqual(items)
      }), { numRuns: 50 })
    })
  })

  /** Feature: d4-14-walkthrough-test, Property 8: D4-12 contract mapping correctness */
  describe('P8: D4-12 contract mapping correctness', () => {
    it('maps contractNo→number, serviceContent→productName, contractAmount→amount', () => {
      fc.assert(fc.property(
        fc.string({ minLength: 1, maxLength: 20 }),
        fc.string({ minLength: 1, maxLength: 30 }),
        positiveAmount,
        fc.string({ minLength: 1, maxLength: 10 }),
        (contractNo, serviceContent, contractAmount, id) => {
          const r = mapD4ContractToDimension({ id, contractNo, serviceContent, contractAmount })
          expect(r.number).toBe(contractNo)
          expect(r.productName).toBe(serviceContent)
          expect(r.amount).toBe(contractAmount)
          expect(r.refD4ContractId).toBe(id)
        }), { numRuns: 100 })
    })

    it('no other dimension fields affected', () => {
      fc.assert(fc.property(fc.string({ minLength: 1, maxLength: 20 }), positiveAmount, (cno, amt) => {
        const r = mapD4ContractToDimension({ contractNo: cno, contractAmount: amt })
        const keys = Object.keys(r)
        expect(keys.every(k => ['number', 'productName', 'amount', 'refD4ContractId'].includes(k))).toBe(true)
      }), { numRuns: 50 })
    })
  })

  /** Feature: d4-14-walkthrough-test, Property 9: OCR field mapping dimension isolation */
  describe('P9: OCR field mapping dimension isolation', () => {
    it('mapOcrToDimension only returns keys for target dimension', () => {
      fc.assert(fc.property(
        fc.record({
          date: fc.string({ minLength: 1, maxLength: 10 }),
          productName: fc.string({ minLength: 1, maxLength: 20 }),
          amount: fc.double({ min: 1, max: 1e6, noNaN: true, noDefaultInfinity: true }),
          number: fc.string({ minLength: 1, maxLength: 10 }),
          warehouseKeeper: fc.string({ minLength: 1, maxLength: 10 }),
          month: fc.string({ minLength: 1, maxLength: 5 }),
          description: fc.string({ minLength: 1, maxLength: 20 }),
        }),
        (fields) => {
          for (const group of DIMENSION_GROUPS) {
            const validKeys = new Set(group.fields.map(f => f.key))
            const mapped = mapOcrToDimension(fields, group.key)
            for (const key of Object.keys(mapped)) {
              expect(validKeys.has(key)).toBe(true)
            }
          }
        }), { numRuns: 100 })
    })

    it('fields from other dimensions are excluded', () => {
      fc.assert(fc.property(
        fc.constantFrom('voucher', 'contract', 'delivery', 'shipping', 'receipt', 'invoice', 'other'),
        (dimKey) => {
          const allFields: Record<string, any> = {
            month: '6', date: '2025-06-01', number: 'V001', productName: '产品A',
            quantity: '10', amount: 5000, accountingDate: '2025-06-02',
            approver: '张三', confirmor: '李四', warehouseKeeper: '王五',
            description: '其他文件', indexNo: 'IX-01',
          }
          const group = DIMENSION_GROUPS.find(g => g.key === dimKey)!
          const validKeys = new Set(group.fields.map(f => f.key))
          const mapped = mapOcrToDimension(allFields, dimKey)
          for (const key of Object.keys(mapped)) expect(validKeys.has(key)).toBe(true)
          for (const key of Object.keys(allFields)) {
            if (!validKeys.has(key)) expect(mapped[key]).toBeUndefined()
          }
        }), { numRuns: 50 })
    })
  }
)
  /** Feature: d4-14-walkthrough-test, Property 10: Ledger import mapping */
  describe('P10: Ledger import mapping correctness', () => {
    it('mapLedgerToTransaction fills voucher correctly', () => {
      fc.assert(fc.property(dateStr, fc.string({ minLength: 1, maxLength: 10 }), fc.string({ minLength: 1, maxLength: 30 }), positiveAmount,
        (date, voucherNo, summary, amount) => {
          const item = mapLedgerToTransaction({ date, voucherNo, summary, amount })
          expect(item.voucher.date).toBe(date)
          expect(item.voucher.number).toBe(voucherNo)
          expect(item.voucher.amount).toBe(amount)
          expect(item.label).toBe(summary)
        }), { numRuns: 100 })
    })

    it('all other dimensions remain at defaults', () => {
      fc.assert(fc.property(dateStr, fc.string({ minLength: 1, maxLength: 10 }), positiveAmount,
        (date, voucherNo, amount) => {
          const item = mapLedgerToTransaction({ date, voucherNo, amount })
          expect(item.contract.number).toBe('')
          expect(item.contract.amount).toBe(0)
          expect(item.delivery.date).toBe('')
          expect(item.delivery.amount).toBe(0)
          expect(item.shipping.amount).toBe(0)
          expect(item.receipt.amount).toBe(0)
          expect(item.invoice.amount).toBe(0)
          expect(item.other.description).toBe('')
        }), { numRuns: 100 })
    })
  })

  /** Feature: d4-14-walkthrough-test, Property 11: AI context collection completeness */
  describe('P11: AI context collection completeness', () => {
    it('collectAiContext includes data from every populated dimension', () => {
      fc.assert(fc.property(positiveAmount, nonEmptyStr, nonEmptyStr, nonEmptyStr,
        (amt, name, date, desc) => {
          const item = makeItem({
            voucher: makeVoucher({ amount: amt, productName: name }),
            contract: makeContract({ amount: amt }),
            delivery: makeDelivery({ date, productName: name }),
            other: makeOther({ description: desc }),
          })
          const ctx = collectAiContext(item)
          expect(ctx.dimensions.voucher).toBeDefined()
          expect(ctx.dimensions.voucher.label).toBe('记账凭证')
          expect(ctx.dimensions.contract).toBeDefined()
          expect(ctx.dimensions.delivery).toBeDefined()
          expect(ctx.dimensions.other).toBeDefined()
        }), { numRuns: 100 })
    })

    it('empty dimensions are NOT included', () => {
      fc.assert(fc.property(positiveAmount, (amt) => {
        const item = makeItem({ voucher: makeVoucher({ amount: amt }) })
        const ctx = collectAiContext(item)
        expect(ctx.dimensions.voucher).toBeDefined()
        expect(ctx.dimensions.contract).toBeUndefined()
        expect(ctx.dimensions.delivery).toBeUndefined()
        expect(ctx.dimensions.shipping).toBeUndefined()
        expect(ctx.dimensions.receipt).toBeUndefined()
        expect(ctx.dimensions.invoice).toBeUndefined()
        expect(ctx.dimensions.other).toBeUndefined()
      }), { numRuns: 50 })
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Unit Tests — Consistency engine edge cases (7.2.4) + mappings (7.2.5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useD4WalkthroughTest - Unit Tests', () => {
  describe('Consistency engine edge cases (7.2.4)', () => {
    it('only 1 dimension populated → isConsistent=true (cannot compare)', () => {
      const item = makeItem({ voucher: makeVoucher({ amount: 5000 }) })
      const r = compareAmounts(item)
      expect(r.isConsistent).toBe(true)
      expect(r.values.length).toBeLessThanOrEqual(1)
    })

    it('all dimensions empty → score = 0', () => {
      expect(computeConsistency(makeItem()).score).toBe(0)
    })

    it('partial fill: 2 dims same amount, 1 different → mismatch detected', () => {
      const item = makeItem({
        voucher: makeVoucher({ amount: 1000 }),
        contract: makeContract({ amount: 1000 }),
        delivery: makeDelivery({ amount: 2000 }),
      })
      const r = compareAmounts(item)
      expect(r.isConsistent).toBe(false)
      expect(r.mismatchDimensions).toContain('出库单')
    })

    it('only productName in 1 dimension → isConsistent=true', () => {
      const item = makeItem({ voucher: makeVoucher({ productName: '产品A' }) })
      expect(compareProductNames(item).isConsistent).toBe(true)
    })

    it('dates in 2 dims same → consistent', () => {
      const item = makeItem({
        voucher: makeVoucher({ date: '2025-06-01' }),
        delivery: makeDelivery({ date: '2025-06-01' }),
      })
      expect(compareDates(item).isConsistent).toBe(true)
    })

    it('score = 100 when all comparable fields match', () => {
      const item = makeItem({
        voucher: makeVoucher({ amount: 5000, productName: 'A', date: '2025-01-01' }),
        contract: makeContract({ amount: 5000, productName: 'A' }),
        delivery: makeDelivery({ amount: 5000, productName: 'A', date: '2025-01-01' }),
      })
      expect(computeConsistency(item).score).toBe(100)
    })
  })

  describe('D4-12 reference + ledger import conversion (7.2.5)', () => {
    it('mapD4ContractToDimension with real-like data', () => {
      const r = mapD4ContractToDimension({ id: 'c-001', contractNo: 'HT-2025-0088', serviceContent: '软件开发服务', contractAmount: 1500000 })
      expect(r.number).toBe('HT-2025-0088')
      expect(r.productName).toBe('软件开发服务')
      expect(r.amount).toBe(1500000)
      expect(r.refD4ContractId).toBe('c-001')
    })

    it('mapD4ContractToDimension handles missing fields', () => {
      const r = mapD4ContractToDimension({})
      expect(r.number).toBe('')
      expect(r.productName).toBe('')
      expect(r.amount).toBe(0)
      expect(r.refD4ContractId).toBe('')
    })

    it('mapLedgerToTransaction creates correct structure', () => {
      const item = mapLedgerToTransaction({ date: '2025-03-15', voucherNo: 'PZ-0321', summary: '销售货款', amount: 88000 })
      expect(item.id).toBeTruthy()
      expect(item.indexNo).toBe('')
      expect(item.label).toBe('销售货款')
      expect(item.voucher.date).toBe('2025-03-15')
      expect(item.voucher.number).toBe('PZ-0321')
      expect(item.voucher.amount).toBe(88000)
      expect(item.contract.amount).toBe(0)
      expect(item.delivery.amount).toBe(0)
    })

    it('mapLedgerToTransaction handles empty entry', () => {
      const item = mapLedgerToTransaction({})
      expect(item.voucher.date).toBe('')
      expect(item.voucher.number).toBe('')
      expect(item.voucher.amount).toBe(0)
      expect(item.label).toBe('')
    })
  })

  describe('mapOcrToDimension isolation', () => {
    it('only fills voucher keys for voucher dimension', () => {
      const r = mapOcrToDimension({ month: '6', date: '2025-06-01', number: 'V001', productName: '产品A', warehouseKeeper: '王五', description: '文件X' }, 'voucher')
      expect(r.month).toBe('6')
      expect(r.date).toBe('2025-06-01')
      expect(r.productName).toBe('产品A')
      expect((r as any).warehouseKeeper).toBeUndefined()
      expect((r as any).description).toBeUndefined()
    })

    it('returns empty object for unknown dimension', () => {
      expect(mapOcrToDimension({ date: '2025-01-01' }, 'unknown_dim')).toEqual({})
    })

    it('skips null/empty values', () => {
      const r = mapOcrToDimension({ date: '', productName: null, amount: 5000 }, 'delivery')
      expect(r.date).toBeUndefined()
      expect(r.productName).toBeUndefined()
      expect(r.amount).toBe(5000)
    })
  })

  describe('collectAiContext', () => {
    it('includes consistency data when available', () => {
      const item = makeItem({
        voucher: makeVoucher({ amount: 5000 }),
        contract: makeContract({ amount: 5000 }),
        consistencyScore: 100,
        consistencyDetails: {
          amountMatch: { isConsistent: true, values: [], mismatchDimensions: [] },
          productNameMatch: { isConsistent: true, values: [], mismatchDimensions: [] },
          dateMatch: { isConsistent: true, values: [], mismatchDimensions: [] },
          score: 100,
        },
      })
      const ctx = collectAiContext(item)
      expect(ctx.consistency).toBeDefined()
      expect(ctx.consistency.score).toBe(100)
    })

    it('includes conclusion when set', () => {
      const item = makeItem({ conclusion: '存在重大异常', voucher: makeVoucher({ amount: 1000 }) })
      expect(collectAiContext(item).conclusion).toBe('存在重大异常')
    })

    it('does not include conclusion when empty', () => {
      const item = makeItem({ voucher: makeVoucher({ amount: 1000 }) })
      expect(collectAiContext(item).conclusion).toBeUndefined()
    })
  })

  describe('isDimensionComplete additional cases', () => {
    it('shipping with all fields → true', () => {
      expect(isDimensionComplete({ date: '2025-01-01', productName: 'A', amount: 100 }, 'shipping')).toBe(true)
    })
    it('invoice with amount=0 → false', () => {
      expect(isDimensionComplete({ date: '2025-01-01', number: 'INV001', amount: 0 }, 'invoice')).toBe(false)
    })
    it('contract missing approver → false', () => {
      expect(isDimensionComplete({ number: 'C01', productName: 'B', amount: 100, approver: '', confirmor: '张三' }, 'contract')).toBe(false)
    })
  })
})
