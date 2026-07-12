/**
 * Property-Based Tests — D2-7 合并去重 + 字段映射（d2-7-voucher-check-enhancement）
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 1.4
 *
 * 使用 fast-check + vitest，numRuns=100 验证：
 * - Property 14: Merge deduplication on fill — 已有行保留 check 值，新行追加，总数正确
 * - Property 15: SampledVoucher field mapping completeness — 每个非空源字段正确映射到目标列
 *
 * **Validates: Requirements 10.2, 10.3**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  mergeVoucherRows,
  mapSampledVoucher,
  type VoucherCheckRow,
  type SampledVoucher,
} from '../useD2VoucherCheckEnhanced'

const RUNS = { numRuns: 100 }

// ─── Shared Generators ─────────────────────────────────────────────────────

/** 生成任意 VoucherCheckRow（可指定 voucherNo 和 check 值） */
function arbVoucherCheckRow(opts?: {
  voucherNo?: fc.Arbitrary<string>
  withChecks?: boolean
}): fc.Arbitrary<VoucherCheckRow> {
  const voucherNoArb = opts?.voucherNo ?? fc.string({ minLength: 1, maxLength: 12 })
  const checkArb = opts?.withChecks
    ? fc.oneof(fc.constant(''), fc.constantFrom('一致', '不一致', '无法判定', '金额一致', '日期一致'))
    : fc.constant('')

  return fc.record({
    rowId: fc.string({ minLength: 4, maxLength: 16 }),
    seq: fc.integer({ min: 1, max: 999 }),
    customerName: fc.string({ maxLength: 20 }),
    voucherDate: fc.constantFrom('2025-06-15', '2025-09-30', '2025-12-31', '2026-01-05'),
    voucherNo: voucherNoArb,
    businessContent: fc.string({ maxLength: 30 }),
    counterpartAccount: fc.string({ maxLength: 10 }),
    counterpartDetail: fc.string({ maxLength: 10 }),
    debitAmount: fc.integer({ min: 0, max: 10000000 }),
    creditAmount: fc.integer({ min: 0, max: 10000000 }),
    supportingDoc: fc.string({ maxLength: 10 }),
    check1: checkArb,
    check2: checkArb,
    check3: checkArb,
    check4: checkArb,
    check5: checkArb,
    indexRef: fc.string({ maxLength: 8 }),
    isAbnormal: fc.constantFrom('', '是', '否'),
    remark: fc.string({ maxLength: 20 }),
    attachments: fc.constant([]),
    source: fc.constantFrom('手动', '自动抽凭', ''),
  })
}

/** 生成唯一 voucherNo 的行数组 */
function arbUniqueRows(opts?: { withChecks?: boolean; min?: number; max?: number }): fc.Arbitrary<VoucherCheckRow[]> {
  const minLen = opts?.min ?? 0
  const maxLen = opts?.max ?? 8
  return fc
    .array(arbVoucherCheckRow({ withChecks: opts?.withChecks }), { minLength: minLen, maxLength: maxLen })
    .map((rows) => {
      const seen = new Set<string>()
      return rows.filter((r) => {
        if (!r.voucherNo || seen.has(r.voucherNo)) return false
        seen.add(r.voucherNo)
        return true
      })
    })
}

/** 生成任意 SampledVoucher */
function arbSampledVoucher(): fc.Arbitrary<SampledVoucher> {
  return fc.record({
    voucherNo: fc.string({ minLength: 1, maxLength: 12 }),
    voucherDate: fc.constantFrom('2025-06-15', '2025-09-30', '2025-12-31', '2026-01-05', ''),
    debitAmount: fc.option(fc.integer({ min: 0, max: 10000000 }), { nil: undefined }),
    creditAmount: fc.option(fc.integer({ min: 0, max: 10000000 }), { nil: undefined }),
    summary: fc.option(fc.string({ minLength: 1, maxLength: 30 }), { nil: undefined }),
    counterpartAccount: fc.option(fc.string({ minLength: 1, maxLength: 10 }), { nil: undefined }),
    accountCode: fc.option(fc.string({ minLength: 1, maxLength: 10 }), { nil: undefined }),
    customerName: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: undefined }),
  })
}

// ═══════════════════════════════════════════════════════════════════════════
// Property 14: Merge deduplication on fill
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: d2-7-voucher-check-enhancement, Property 14: Merge deduplication on fill', () => {
  /** **Validates: Requirements 10.3** */

  it('已存在凭证（按 voucherNo 匹配）保留原行的 check1~check5 不覆盖', () => {
    fc.assert(
      fc.property(
        arbUniqueRows({ withChecks: true, min: 1, max: 6 }),
        arbUniqueRows({ withChecks: false, min: 1, max: 6 }),
        (existing, incoming) => {
          // 创建一些 overlap: 将 incoming 的部分 voucherNo 设为 existing 已有的
          const existingNos = existing.map((r) => r.voucherNo)
          if (existingNos.length > 0 && incoming.length > 0) {
            // 强制第一个 incoming 与第一个 existing 同 voucherNo
            incoming[0] = { ...incoming[0], voucherNo: existingNos[0] }
          }

          const result = mergeVoucherRows(existing, incoming)

          // 验证：已存在的凭证保留原 check 值
          for (const existRow of existing) {
            const found = result.find((r) => r.voucherNo === existRow.voucherNo)
            expect(found).toBeDefined()
            expect(found!.check1).toBe(existRow.check1)
            expect(found!.check2).toBe(existRow.check2)
            expect(found!.check3).toBe(existRow.check3)
            expect(found!.check4).toBe(existRow.check4)
            expect(found!.check5).toBe(existRow.check5)
          }
        },
      ),
      RUNS,
    )
  })

  it('新凭证（voucherNo 不在 existing 中）被追加到结果', () => {
    fc.assert(
      fc.property(
        arbUniqueRows({ withChecks: true, min: 0, max: 6 }),
        arbUniqueRows({ withChecks: false, min: 1, max: 6 }),
        (existing, incoming) => {
          const existingNos = new Set(existing.map((r) => r.voucherNo))
          // 确保 incoming 全部为新凭证（不重叠）
          const newIncoming = incoming.filter((r) => !existingNos.has(r.voucherNo))

          const result = mergeVoucherRows(existing, newIncoming)

          // 所有新凭证都应出现在结果中
          for (const inc of newIncoming) {
            const found = result.find((r) => r.voucherNo === inc.voucherNo)
            expect(found).toBeDefined()
          }
        },
      ),
      RUNS,
    )
  })

  it('总行数 == |existing| + |incoming 中 voucherNo 不在 existing 中的|', () => {
    fc.assert(
      fc.property(
        arbUniqueRows({ withChecks: true, min: 0, max: 8 }),
        arbUniqueRows({ withChecks: false, min: 0, max: 8 }),
        (existing, incoming) => {
          const existingNos = new Set(existing.map((r) => r.voucherNo).filter(Boolean))
          const newCount = incoming.filter(
            (r) => !r.voucherNo || !existingNos.has(r.voucherNo),
          ).length

          const result = mergeVoucherRows(existing, incoming)
          expect(result.length).toBe(existing.length + newCount)
        },
      ),
      RUNS,
    )
  })

  it('结果中 seq 从 1 连续编号', () => {
    fc.assert(
      fc.property(
        arbUniqueRows({ withChecks: true, min: 0, max: 6 }),
        arbUniqueRows({ withChecks: false, min: 0, max: 6 }),
        (existing, incoming) => {
          const result = mergeVoucherRows(existing, incoming)
          for (let i = 0; i < result.length; i++) {
            expect(result[i].seq).toBe(i + 1)
          }
        },
      ),
      RUNS,
    )
  })

  it('空 voucherNo 的 incoming 行总是被追加（不参与去重）', () => {
    fc.assert(
      fc.property(
        arbUniqueRows({ withChecks: true, min: 1, max: 4 }),
        fc.integer({ min: 1, max: 3 }),
        (existing, emptyCount) => {
          const emptyRows: VoucherCheckRow[] = Array.from({ length: emptyCount }, (_, i) => ({
            rowId: `empty-${i}`,
            seq: 0,
            customerName: '',
            voucherDate: '',
            voucherNo: '',
            businessContent: '',
            counterpartAccount: '',
            counterpartDetail: '',
            debitAmount: 0,
            creditAmount: 0,
            supportingDoc: '',
            check1: '',
            check2: '',
            check3: '',
            check4: '',
            check5: '',
            indexRef: '',
            isAbnormal: '',
            remark: '',
            attachments: [],
          }))

          const result = mergeVoucherRows(existing, emptyRows)
          expect(result.length).toBe(existing.length + emptyCount)
        },
      ),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 15: SampledVoucher field mapping completeness
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: d2-7-voucher-check-enhancement, Property 15: SampledVoucher field mapping completeness', () => {
  /** **Validates: Requirements 10.2** */

  it('每个非空源字段正确映射到对应目标列', () => {
    fc.assert(
      fc.property(
        arbSampledVoucher(),
        fc.integer({ min: 1, max: 999 }),
        (voucher, seq) => {
          const row = mapSampledVoucher(voucher, seq)

          // voucherNo → voucherNo
          expect(row.voucherNo).toBe(voucher.voucherNo || '')

          // voucherDate → voucherDate
          expect(row.voucherDate).toBe(voucher.voucherDate || '')

          // debitAmount → debitAmount
          expect(row.debitAmount).toBe(voucher.debitAmount ?? 0)

          // creditAmount → creditAmount
          expect(row.creditAmount).toBe(voucher.creditAmount ?? 0)

          // summary → businessContent
          expect(row.businessContent).toBe(voucher.summary || '')

          // counterpartAccount → counterpartAccount
          expect(row.counterpartAccount).toBe(voucher.counterpartAccount || '')

          // accountCode → counterpartDetail
          expect(row.counterpartDetail).toBe(voucher.accountCode || '')

          // customerName → customerName
          expect(row.customerName).toBe(voucher.customerName || '')
        },
      ),
      RUNS,
    )
  })

  it('seq 参数正确赋值到结果行', () => {
    fc.assert(
      fc.property(
        arbSampledVoucher(),
        fc.integer({ min: 1, max: 9999 }),
        (voucher, seq) => {
          const row = mapSampledVoucher(voucher, seq)
          expect(row.seq).toBe(seq)
        },
      ),
      RUNS,
    )
  })

  it('映射结果的 check1~check5 初始为空（不从源字段污染）', () => {
    fc.assert(
      fc.property(arbSampledVoucher(), (voucher) => {
        const row = mapSampledVoucher(voucher, 1)
        expect(row.check1).toBe('')
        expect(row.check2).toBe('')
        expect(row.check3).toBe('')
        expect(row.check4).toBe('')
        expect(row.check5).toBe('')
      }),
      RUNS,
    )
  })

  it('映射结果 source 标记为"自动抽凭"', () => {
    fc.assert(
      fc.property(arbSampledVoucher(), (voucher) => {
        const row = mapSampledVoucher(voucher, 1)
        expect(row.source).toBe('自动抽凭')
      }),
      RUNS,
    )
  })

  it('映射结果 attachments 为空数组', () => {
    fc.assert(
      fc.property(arbSampledVoucher(), (voucher) => {
        const row = mapSampledVoucher(voucher, 1)
        expect(row.attachments).toEqual([])
      }),
      RUNS,
    )
  })

  it('rowId 非空且唯一（多次调用产生不同 id）', () => {
    fc.assert(
      fc.property(arbSampledVoucher(), (voucher) => {
        const row1 = mapSampledVoucher(voucher, 1)
        const row2 = mapSampledVoucher(voucher, 2)
        expect(row1.rowId).toBeTruthy()
        expect(row2.rowId).toBeTruthy()
        expect(row1.rowId).not.toBe(row2.rowId)
      }),
      RUNS,
    )
  })

  it('目标列不包含来自错误源字段的数据', () => {
    fc.assert(
      fc.property(arbSampledVoucher(), (voucher) => {
        const row = mapSampledVoucher(voucher, 1)

        // businessContent 来自 summary，不来自 counterpartAccount/accountCode/customerName
        if (voucher.summary) {
          expect(row.businessContent).toBe(voucher.summary)
          // 如果 summary 与 counterpartAccount 不同，确认不混淆
          if (voucher.counterpartAccount && voucher.summary !== voucher.counterpartAccount) {
            expect(row.businessContent).not.toBe(voucher.counterpartAccount)
          }
        }

        // counterpartDetail 来自 accountCode，不来自 counterpartAccount
        if (voucher.accountCode) {
          expect(row.counterpartDetail).toBe(voucher.accountCode)
          if (voucher.counterpartAccount && voucher.accountCode !== voucher.counterpartAccount) {
            expect(row.counterpartDetail).not.toBe(voucher.counterpartAccount)
          }
        }

        // counterpartAccount 来自 counterpartAccount，不来自 accountCode
        if (voucher.counterpartAccount) {
          expect(row.counterpartAccount).toBe(voucher.counterpartAccount)
          if (voucher.accountCode && voucher.counterpartAccount !== voucher.accountCode) {
            expect(row.counterpartAccount).not.toBe(voucher.accountCode)
          }
        }
      }),
      RUNS,
    )
  })
})
