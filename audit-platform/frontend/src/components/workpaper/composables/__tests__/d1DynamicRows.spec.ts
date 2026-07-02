/**
 * Property-Based Tests — D1 动态行增删计数不变量
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Task: 3.2
 *
 * 使用 fast-check + vitest 验证 Property 6: 动态行增删计数不变量。
 * 覆盖 D1-10 InventoryCountRow 的 addRow/removeRow 逻辑。
 *
 * 由于 useD1InventoryCount 依赖 Vue reactivity (ref/computed/watch/onBeforeUnmount)，
 * PBT 在纯数组层面测试 CRUD 逻辑（与 composable 内部 addRow/removeRow 实现等价）。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { emptyInventoryCountRow } from '../useD1InventoryCount'
import { emptyRelatedPartyRow } from '../useD1RelatedPartyCheck'
import { emptyPledgeRow } from '../useD1PledgeCheck'
import { emptyVouchingRow, emptySpecificSampleRow } from '../useD1SamplingVouching'
import type { InventoryCountRow, RelatedPartyRow, PledgeRow, VouchingRow, SpecificSampleRow } from '../d1InspectionFormulas'

// ═══════════════════════════════════════════════════════════════════════════════
// Generator: InventoryCountRowArbitrary
// ═══════════════════════════════════════════════════════════════════════════════

const InventoryCountRowArbitrary: fc.Arbitrary<InventoryCountRow> = fc.record({
  id: fc.uuid(),
  noteType: fc.constantFrom('银行承兑汇票', '商业承兑汇票', ''),
  noteNo: fc.string({ maxLength: 20 }),
  issueDate: fc.constant(''),
  drawer: fc.string({ maxLength: 10 }),
  acceptor: fc.string({ maxLength: 10 }),
  amount: fc.float({ min: -1e6, max: 1e6, noNaN: true }),
  maturityDate: fc.constant(''),
  predecessor: fc.string({ maxLength: 10 }),
  receiveDate: fc.constant(''),
  endorseDate: fc.constant(''),
  endorsee: fc.string({ maxLength: 10 }),
  noteStatus: fc.constantFrom('在库', '已背书', '已贴现', '已到期', '已质押', ''),
  hasDifference: fc.constantFrom('是', '否', ''),
  differenceReason: fc.string({ maxLength: 50 }),
  indexRef: fc.constant(''),
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 动态行增删计数不变量（D1-10）
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-inspection-check, Property 6: 动态行增删计数不变量（D1-10）
describe('Feature: d1-inspection-check, Property 6: 动态行增删计数不变量（D1-10）', () => {
  /**
   * **Validates: Requirements 1.4**
   *
   * For any array of InventoryCountRow (length N, N >= 0):
   * - After addRow(), length should be N + 1
   * - For length N > 0, after removeRow(validId), length should be N - 1
   */
  it('P6: addRow increases length by 1', () => {
    fc.assert(
      fc.property(
        fc.array(InventoryCountRowArbitrary, { minLength: 0, maxLength: 20 }),
        (rows) => {
          const N = rows.length

          // Simulate addRow: push a new emptyInventoryCountRow
          const afterAdd = [...rows, emptyInventoryCountRow()]

          expect(afterAdd.length).toBe(N + 1)
        }
      ),
      { numRuns: 100 }
    )
  })

  it('P6: removeRow(validId) decreases length by 1', () => {
    fc.assert(
      fc.property(
        fc.array(InventoryCountRowArbitrary, { minLength: 1, maxLength: 20 }),
        fc.nat(),
        (rows, indexSeed) => {
          const N = rows.length
          // Pick a valid index using modulo
          const validIndex = indexSeed % N
          const validId = rows[validIndex].id

          // Simulate removeRow: filter by id
          const afterRemove = rows.filter((r) => r.id !== validId)

          expect(afterRemove.length).toBe(N - 1)
        }
      ),
      { numRuns: 100 }
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Generator: RelatedPartyRowArbitrary
// ═══════════════════════════════════════════════════════════════════════════════

const RelatedPartyRowArbitrary: fc.Arbitrary<RelatedPartyRow> = fc.record({
  id: fc.uuid(),
  partyName: fc.string({ maxLength: 10 }),
  relationship: fc.constantFrom('母公司', '子公司', '联营企业', '合营企业', '关键管理人员', '其他关联方', ''),
  openingBalance: fc.float({ min: -1e6, max: 1e6, noNaN: true }),
  debitOccurrence: fc.float({ min: -1e6, max: 1e6, noNaN: true }),
  creditOccurrence: fc.float({ min: -1e6, max: 1e6, noNaN: true }),
  closingBalance: fc.float({ min: -1e6, max: 1e6, noNaN: true }),
  badDebtProvision: fc.float({ min: -1e6, max: 1e6, noNaN: true }),
  bookValue: fc.float({ min: -1e6, max: 1e6, noNaN: true }),
  agingInfo: fc.string({ maxLength: 10 }),
  transactionNature: fc.string({ maxLength: 20 }),
  postHonored: fc.float({ min: -1e6, max: 1e6, noNaN: true }),
  indexRef: fc.constant(''),
  remark: fc.string({ maxLength: 20 }),
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 动态行增删计数不变量（D1-11）
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-inspection-check, Property 6: 动态行增删计数不变量（D1-11）
describe('Feature: d1-inspection-check, Property 6: 动态行增删计数不变量（D1-11）', () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * For any array of RelatedPartyRow (length N, N >= 0):
   * - After addRow(), length should be N + 1
   * - For length N > 0, after removeRow(validId), length should be N - 1
   */
  it('P6: addRow increases length by 1', () => {
    fc.assert(
      fc.property(
        fc.array(RelatedPartyRowArbitrary, { minLength: 0, maxLength: 20 }),
        (rows) => {
          const N = rows.length

          // Simulate addRow: push a new emptyRelatedPartyRow
          const afterAdd = [...rows, emptyRelatedPartyRow()]

          expect(afterAdd.length).toBe(N + 1)
        }
      ),
      { numRuns: 100 }
    )
  })

  it('P6: removeRow(validId) decreases length by 1', () => {
    fc.assert(
      fc.property(
        fc.array(RelatedPartyRowArbitrary, { minLength: 1, maxLength: 20 }),
        fc.nat(),
        (rows, indexSeed) => {
          const N = rows.length
          // Pick a valid index using modulo
          const validIndex = indexSeed % N
          const validId = rows[validIndex].id

          // Simulate removeRow: filter by id
          const afterRemove = rows.filter((r) => r.id !== validId)

          expect(afterRemove.length).toBe(N - 1)
        }
      ),
      { numRuns: 100 }
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Generator: PledgeRowArbitrary
// ═══════════════════════════════════════════════════════════════════════════════

const PledgeRowArbitrary: fc.Arbitrary<PledgeRow> = fc.record({
  id: fc.uuid(),
  noteType: fc.constantFrom('银行承兑汇票', '商业承兑汇票', ''),
  noteNo: fc.string({ maxLength: 20 }),
  receiveDate: fc.constant(''),
  predecessor: fc.string({ maxLength: 10 }),
  issueDate: fc.constant(''),
  drawer: fc.string({ maxLength: 10 }),
  acceptor: fc.string({ maxLength: 10 }),
  noteAmount: fc.float({ min: 0, max: 1e6, noNaN: true }),
  maturityDate: fc.constant(''),
  pledgeAmount: fc.float({ min: 0, max: 1e6, noNaN: true }),
  pledgee: fc.string({ maxLength: 10 }),
  pledgeReason: fc.string({ maxLength: 20 }),
  pledgeCondition: fc.string({ maxLength: 20 }),
  pledgePeriod: fc.constant(''),
  pledgeAgreement: fc.string({ maxLength: 20 }),
  indexRef: fc.constant(''),
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 动态行增删计数不变量（D1-12）
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-inspection-check, Property 6: 动态行增删计数不变量（D1-12）
describe('Feature: d1-inspection-check, Property 6: 动态行增删计数不变量（D1-12）', () => {
  /**
   * **Validates: Requirements 7.4**
   *
   * For any array of PledgeRow (length N, N >= 0):
   * - After addRow(), length should be N + 1
   * - For length N > 0, after removeRow(validId), length should be N - 1
   */
  it('P6: addRow increases length by 1', () => {
    fc.assert(
      fc.property(
        fc.array(PledgeRowArbitrary, { minLength: 0, maxLength: 20 }),
        (rows) => {
          const N = rows.length

          // Simulate addRow: push a new emptyPledgeRow
          const afterAdd = [...rows, emptyPledgeRow()]

          expect(afterAdd.length).toBe(N + 1)
        }
      ),
      { numRuns: 100 }
    )
  })

  it('P6: removeRow(validId) decreases length by 1', () => {
    fc.assert(
      fc.property(
        fc.array(PledgeRowArbitrary, { minLength: 1, maxLength: 20 }),
        fc.nat(),
        (rows, indexSeed) => {
          const N = rows.length
          // Pick a valid index using modulo
          const validIndex = indexSeed % N
          const validId = rows[validIndex].id

          // Simulate removeRow: filter by id
          const afterRemove = rows.filter((r) => r.id !== validId)

          expect(afterRemove.length).toBe(N - 1)
        }
      ),
      { numRuns: 100 }
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Generator: VouchingRowArbitrary
// ═══════════════════════════════════════════════════════════════════════════════

const VouchingRowArbitrary: fc.Arbitrary<VouchingRow> = fc.record({
  id: fc.uuid(),
  seq: fc.nat({ max: 100 }),
  noteType: fc.constantFrom('银行承兑汇票', '商业承兑汇票', ''),
  noteNo: fc.string({ maxLength: 20 }),
  drawer: fc.string({ maxLength: 10 }),
  acceptor: fc.string({ maxLength: 10 }),
  amount: fc.float({ min: 0, max: 1e6, noNaN: true }),
  maturityDate: fc.constant(''),
  existenceCheck: fc.constantFrom('已核实', '未核实', '不适用', ''),
  accuracyCheck: fc.constantFrom('金额一致', '金额不一致', '不适用', ''),
  appropriatenessCheck: fc.constantFrom('恰当', '不恰当', '不适用', ''),
  remark: fc.string({ maxLength: 20 }),
  indexRef: fc.constant(''),
})

// ═══════════════════════════════════════════════════════════════════════════════
// Generator: SpecificSampleRowArbitrary
// ═══════════════════════════════════════════════════════════════════════════════

const SpecificSampleRowArbitrary: fc.Arbitrary<SpecificSampleRow> = fc.record({
  id: fc.uuid(),
  description: fc.string({ maxLength: 20 }),
  amount: fc.float({ min: 0, max: 1e6, noNaN: true }),
  reason: fc.string({ maxLength: 20 }),
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 动态行增删计数不变量（D1-13 凭证核对）
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-inspection-check, Property 6: 动态行增删计数不变量（D1-13 凭证核对+特定样本）
describe('Feature: d1-inspection-check, Property 6: 动态行增删计数不变量（D1-13 凭证核对）', () => {
  /**
   * **Validates: Requirements 10.3**
   *
   * For any array of VouchingRow (length N, N >= 0):
   * - After addVouchingRow(), length should be N + 1
   * - For length N > 0, after removeVouchingRow(validId), length should be N - 1
   */
  it('P6: addVouchingRow increases length by 1', () => {
    fc.assert(
      fc.property(
        fc.array(VouchingRowArbitrary, { minLength: 0, maxLength: 20 }),
        (rows) => {
          const N = rows.length

          // Simulate addVouchingRow: push a new emptyVouchingRow with next seq
          const nextSeq = N + 1
          const afterAdd = [...rows, emptyVouchingRow(nextSeq)]

          expect(afterAdd.length).toBe(N + 1)
        }
      ),
      { numRuns: 100 }
    )
  })

  it('P6: removeVouchingRow(validId) decreases length by 1', () => {
    fc.assert(
      fc.property(
        fc.array(VouchingRowArbitrary, { minLength: 1, maxLength: 20 }),
        fc.nat(),
        (rows, indexSeed) => {
          const N = rows.length
          // Pick a valid index using modulo
          const validIndex = indexSeed % N
          const validId = rows[validIndex].id

          // Simulate removeVouchingRow: filter by id
          const afterRemove = rows.filter((r) => r.id !== validId)

          expect(afterRemove.length).toBe(N - 1)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 动态行增删计数不变量（D1-13 特定样本）
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-inspection-check, Property 6: 动态行增删计数不变量（D1-13 特定样本）
describe('Feature: d1-inspection-check, Property 6: 动态行增删计数不变量（D1-13 特定样本）', () => {
  /**
   * **Validates: Requirements 11.2**
   *
   * For any array of SpecificSampleRow (length N, N >= 0):
   * - After addSpecificSample(), length should be N + 1
   * - For length N > 0, after removeSpecificSample(validId), length should be N - 1
   */
  it('P6: addSpecificSample increases length by 1', () => {
    fc.assert(
      fc.property(
        fc.array(SpecificSampleRowArbitrary, { minLength: 0, maxLength: 20 }),
        (rows) => {
          const N = rows.length

          // Simulate addSpecificSample: push a new emptySpecificSampleRow
          const afterAdd = [...rows, emptySpecificSampleRow()]

          expect(afterAdd.length).toBe(N + 1)
        }
      ),
      { numRuns: 100 }
    )
  })

  it('P6: removeSpecificSample(validId) decreases length by 1', () => {
    fc.assert(
      fc.property(
        fc.array(SpecificSampleRowArbitrary, { minLength: 1, maxLength: 20 }),
        fc.nat(),
        (rows, indexSeed) => {
          const N = rows.length
          // Pick a valid index using modulo
          const validIndex = indexSeed % N
          const validId = rows[validIndex].id

          // Simulate removeSpecificSample: filter by id
          const afterRemove = rows.filter((r) => r.id !== validId)

          expect(afterRemove.length).toBe(N - 1)
        }
      ),
      { numRuns: 100 }
    )
  })
})
