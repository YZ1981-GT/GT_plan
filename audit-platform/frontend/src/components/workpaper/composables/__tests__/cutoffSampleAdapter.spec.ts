/**
 * cutoffSampleAdapter — 双侧证据模型适配器测试
 *
 * Spec: cutoff-test-architecture-convergence Wave 3 Task 6
 * 验证：P7 禁止金额复制 + Req2.5 往返保真 + 字段别名映射
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'

import {
  fromCycleRow,
  toCycleRow,
  fromK8Row,
  toK8Row,
  fromK9Row,
  toK9Row,
  type CutoffSample,
} from '../cutoffSampleAdapter'

const arbNum = fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true })
const arbStr = fc.string({ maxLength: 12 })
const arbDate = fc.constantFrom('2025-12-28', '2026-01-05', '2025-11-30', '')

// ═══════════════════════════════════════════════════════════════════════════════
// P7 禁止金额自动复制：documentAmount 缺失恒 0，不等于 bookAmount
// ═══════════════════════════════════════════════════════════════════════════════

describe('P7 禁止金额自动复制', () => {
  it('CycleRow 无 documentAmount → 0（不回退 amount）', () => {
    fc.assert(
      fc.property(arbNum, (amount) => {
        const s = fromCycleRow({ recordDate: '2025-12-28', amount, voucherNo: 'V1' })
        expect(s.documentAmount).toBe(0)
      }),
      { numRuns: 40 },
    )
  })

  it('K8Row 无 sourceAmount → 0', () => {
    fc.assert(
      fc.property(arbNum, (amount) => {
        const s = fromK8Row({ bookDate: '2025-12-28', amount, voucherNo: 'V1' })
        expect(s.documentAmount).toBe(0)
      }),
      { numRuns: 40 },
    )
  })

  it('K9Row documentAmount 恒 0（K9 无该字段）', () => {
    fc.assert(
      fc.property(arbNum, arbNum, (amount, anySource) => {
        const s = fromK9Row({ bookDate: '2025-12-28', amount, sourceAmount: anySource, voucherNo: 'V1' })
        expect(s.documentAmount).toBe(0)
      }),
      { numRuns: 40 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Req2.5 往返保真：fromX → toX 保留映射字段
// ═══════════════════════════════════════════════════════════════════════════════

describe('Req2.5 往返保真', () => {
  it('Cycle: fromCycleRow → toCycleRow 保留证据字段', () => {
    fc.assert(
      fc.property(arbDate, arbNum, arbStr, arbDate, arbNum, arbStr, arbStr, (recordDate, amount, voucherNo, documentDate, documentAmount, documentNo, description) => {
        const row = { recordDate, amount, voucherNo, documentDate, documentAmount, documentNo, description }
        const back = toCycleRow(fromCycleRow(row))
        expect(back.recordDate).toBe(recordDate)
        expect(back.amount).toBe(amount)
        expect(back.voucherNo).toBe(voucherNo)
        expect(back.documentDate).toBe(documentDate)
        expect(back.documentAmount).toBe(documentAmount)
        expect(back.documentNo).toBe(documentNo)
        expect(back.description).toBe(description)
      }),
      { numRuns: 60 },
    )
  })

  it('K8: fromK8Row → toK8Row 保留证据字段', () => {
    fc.assert(
      fc.property(arbDate, arbNum, arbStr, arbDate, arbNum, arbStr, arbStr, (bookDate, amount, voucherNo, sourceDate, sourceAmount, sourceVoucherNo, summary) => {
        const row = { bookDate, amount, voucherNo, sourceDate, sourceAmount, sourceVoucherNo, summary }
        const back = toK8Row(fromK8Row(row))
        expect(back.bookDate).toBe(bookDate)
        expect(back.amount).toBe(amount)
        expect(back.voucherNo).toBe(voucherNo)
        expect(back.sourceDate).toBe(sourceDate)
        expect(back.sourceAmount).toBe(sourceAmount)
        expect(back.sourceVoucherNo).toBe(sourceVoucherNo)
        expect(back.summary).toBe(summary)
      }),
      { numRuns: 60 },
    )
  })

  it('K9: fromK9Row → toK9Row 保留证据字段（documentAmount 除外，K9 无）', () => {
    fc.assert(
      fc.property(arbDate, arbNum, arbStr, arbDate, arbStr, arbStr, (bookDate, amount, voucherNo, sourceDate, sourceVoucherNo, summary) => {
        const row = { bookDate, amount, voucherNo, sourceDate, sourceVoucherNo, summary }
        const back = toK9Row(fromK9Row(row))
        expect(back.bookDate).toBe(bookDate)
        expect(back.amount).toBe(amount)
        expect(back.voucherNo).toBe(voucherNo)
        expect(back.sourceDate).toBe(sourceDate)
        expect(back.sourceVoucherNo).toBe(sourceVoucherNo)
        expect(back.summary).toBe(summary)
        expect(back).not.toHaveProperty('sourceAmount')
      }),
      { numRuns: 60 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 字段别名映射正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('字段别名映射', () => {
  it('三底稿映射到统一 book*/doc* 语义', () => {
    const cycle = fromCycleRow({ recordDate: '2025-12-28', amount: 100, voucherNo: 'C1', documentDate: '2026-01-03', documentAmount: 100, documentNo: 'D1', description: '费用' })
    const k8 = fromK8Row({ bookDate: '2025-12-28', amount: 100, voucherNo: 'C1', sourceDate: '2026-01-03', sourceAmount: 100, sourceVoucherNo: 'D1', summary: '费用' })
    const expected: CutoffSample = { bookDate: '2025-12-28', bookAmount: 100, voucherNo: 'C1', documentDate: '2026-01-03', documentAmount: 100, documentNo: 'D1', summary: '费用' }
    expect(cycle).toEqual(expected)
    expect(k8).toEqual(expected)
  })

  it('K8 summary 回退 businessContent', () => {
    const s = fromK8Row({ bookDate: '2025-12-28', amount: 1, businessContent: '差旅' })
    expect(s.summary).toBe('差旅')
  })
})
