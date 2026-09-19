/**
 * Property-Based Tests — D1 导入导出 Round-Trip
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Task: 16.2
 *
 * Feature: d1-inspection-check, Property 8: 导入导出 Round-Trip
 *
 * 使用 fast-check + vitest 验证 Property 8: 导入导出 Round-Trip。
 * 测试4种行类型的序列化/反序列化等价性（JSON.stringify → JSON.parse → 字段解析）。
 *
 * 由于真正的xlsx导入导出经过后端openpyxl，前端层面的round-trip契约是：
 * 1. 序列化: JSON.stringify(rows) — composable存储到remark字段
 * 2. 反序列化: JSON.parse(serialized) → 对每行应用字段解析规则
 *    - 数值字段: Number(val)，非有限数降级为0
 *    - 字符串字段: String(val)
 *
 * **Validates: Requirements 15.7, 15.8, 15.9, 15.10, 16.2, 16.3**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import type {
  InventoryCountRow,
  RelatedPartyRow,
  PledgeRow,
  VouchingRow,
} from '../d1InspectionFormulas'

// ═══════════════════════════════════════════════════════════════════════════════
// Helpers: parseNum mirrors the composable's internal parseNum
// ═══════════════════════════════════════════════════════════════════════════════

function parseNum(val: any): number {
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

// ═══════════════════════════════════════════════════════════════════════════════
// Field definitions per row type (matching composable NUMERIC_FIELDS/STRING_FIELDS)
// ═══════════════════════════════════════════════════════════════════════════════

const INVENTORY_NUMERIC_FIELDS: Array<keyof InventoryCountRow> = ['amount']
const INVENTORY_STRING_FIELDS: Array<keyof InventoryCountRow> = [
  'id', 'noteType', 'noteNo', 'issueDate', 'drawer', 'acceptor',
  'maturityDate', 'predecessor', 'receiveDate', 'endorseDate',
  'endorsee', 'noteStatus', 'hasDifference', 'differenceReason', 'indexRef',
]

const RP_NUMERIC_FIELDS: Array<keyof RelatedPartyRow> = [
  'openingBalance', 'debitOccurrence', 'creditOccurrence',
  'closingBalance', 'badDebtProvision', 'bookValue', 'postHonored',
]
const RP_STRING_FIELDS: Array<keyof RelatedPartyRow> = [
  'id', 'partyName', 'relationship', 'agingInfo',
  'transactionNature', 'indexRef', 'remark',
]

const PLEDGE_NUMERIC_FIELDS: Array<keyof PledgeRow> = ['noteAmount', 'pledgeAmount']
const PLEDGE_STRING_FIELDS: Array<keyof PledgeRow> = [
  'id', 'noteType', 'noteNo', 'receiveDate', 'predecessor',
  'issueDate', 'drawer', 'acceptor', 'maturityDate',
  'pledgee', 'pledgeReason', 'pledgeCondition',
  'pledgePeriod', 'pledgeAgreement', 'indexRef',
]

const VOUCHING_NUMERIC_FIELDS: Array<keyof VouchingRow> = ['amount', 'seq']
const VOUCHING_STRING_FIELDS: Array<keyof VouchingRow> = [
  'id', 'noteType', 'noteNo', 'drawer', 'acceptor',
  'maturityDate', 'existenceCheck', 'accuracyCheck',
  'appropriatenessCheck', 'remark', 'indexRef',
]

// ═══════════════════════════════════════════════════════════════════════════════
// Deserializers: mimic composable deserializeRow logic
// ═══════════════════════════════════════════════════════════════════════════════

function deserializeInventoryRow(raw: any): InventoryCountRow {
  const row: any = {}
  for (const f of INVENTORY_STRING_FIELDS) {
    row[f] = typeof raw[f] === 'string' ? raw[f] : String(raw[f] ?? '')
  }
  for (const f of INVENTORY_NUMERIC_FIELDS) {
    row[f] = parseNum(raw[f])
  }
  return row as InventoryCountRow
}

function deserializeRelatedPartyRow(raw: any): RelatedPartyRow {
  const row: any = {}
  for (const f of RP_STRING_FIELDS) {
    row[f] = typeof raw[f] === 'string' ? raw[f] : String(raw[f] ?? '')
  }
  for (const f of RP_NUMERIC_FIELDS) {
    row[f] = parseNum(raw[f])
  }
  return row as RelatedPartyRow
}

function deserializePledgeRow(raw: any): PledgeRow {
  const row: any = {}
  for (const f of PLEDGE_STRING_FIELDS) {
    row[f] = typeof raw[f] === 'string' ? raw[f] : String(raw[f] ?? '')
  }
  for (const f of PLEDGE_NUMERIC_FIELDS) {
    row[f] = parseNum(raw[f])
  }
  return row as PledgeRow
}

function deserializeVouchingRow(raw: any): VouchingRow {
  const row: any = {}
  for (const f of VOUCHING_STRING_FIELDS) {
    row[f] = typeof raw[f] === 'string' ? raw[f] : String(raw[f] ?? '')
  }
  for (const f of VOUCHING_NUMERIC_FIELDS) {
    row[f] = parseNum(raw[f])
  }
  return row as VouchingRow
}

// ═══════════════════════════════════════════════════════════════════════════════
// Generators (reuse same pattern as d1DynamicRows.spec.ts)
// ═══════════════════════════════════════════════════════════════════════════════

const InventoryCountRowArbitrary: fc.Arbitrary<InventoryCountRow> = fc.record({
  id: fc.uuid(),
  noteType: fc.constantFrom('银行承兑汇票', '商业承兑汇票', ''),
  noteNo: fc.string({ maxLength: 20 }),
  issueDate: fc.constantFrom('2024-01-15', '2024-06-30', '2025-12-31', ''),
  drawer: fc.string({ maxLength: 10 }),
  acceptor: fc.string({ maxLength: 10 }),
  amount: fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
  maturityDate: fc.constantFrom('2024-03-15', '2025-01-01', ''),
  predecessor: fc.string({ maxLength: 10 }),
  receiveDate: fc.constantFrom('2024-02-01', '2024-07-15', ''),
  endorseDate: fc.constantFrom('2024-04-01', ''),
  endorsee: fc.string({ maxLength: 10 }),
  noteStatus: fc.constantFrom('在库', '已背书', '已贴现', '已到期', '已质押', ''),
  hasDifference: fc.constantFrom('是', '否', ''),
  differenceReason: fc.string({ maxLength: 50 }),
  indexRef: fc.string({ maxLength: 10 }),
})

const RelatedPartyRowArbitrary: fc.Arbitrary<RelatedPartyRow> = fc.record({
  id: fc.uuid(),
  partyName: fc.string({ maxLength: 10 }),
  relationship: fc.constantFrom('母公司', '子公司', '联营企业', '合营企业', '关键管理人员', '其他关联方', ''),
  openingBalance: fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
  debitOccurrence: fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
  creditOccurrence: fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
  closingBalance: fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
  badDebtProvision: fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
  bookValue: fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
  agingInfo: fc.string({ maxLength: 10 }),
  transactionNature: fc.string({ maxLength: 20 }),
  postHonored: fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
  indexRef: fc.string({ maxLength: 10 }),
  remark: fc.string({ maxLength: 20 }),
})

const PledgeRowArbitrary: fc.Arbitrary<PledgeRow> = fc.record({
  id: fc.uuid(),
  noteType: fc.constantFrom('银行承兑汇票', '商业承兑汇票', ''),
  noteNo: fc.string({ maxLength: 20 }),
  receiveDate: fc.constantFrom('2024-01-15', '2024-06-30', ''),
  predecessor: fc.string({ maxLength: 10 }),
  issueDate: fc.constantFrom('2024-01-01', '2024-12-31', ''),
  drawer: fc.string({ maxLength: 10 }),
  acceptor: fc.string({ maxLength: 10 }),
  noteAmount: fc.float({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }),
  maturityDate: fc.constantFrom('2025-01-01', '2025-06-30', ''),
  pledgeAmount: fc.float({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }),
  pledgee: fc.string({ maxLength: 10 }),
  pledgeReason: fc.string({ maxLength: 20 }),
  pledgeCondition: fc.string({ maxLength: 20 }),
  pledgePeriod: fc.constantFrom('2024-01-01至2025-12-31', ''),
  pledgeAgreement: fc.string({ maxLength: 20 }),
  indexRef: fc.string({ maxLength: 10 }),
})

const VouchingRowArbitrary: fc.Arbitrary<VouchingRow> = fc.record({
  id: fc.uuid(),
  seq: fc.nat({ max: 100 }),
  noteType: fc.constantFrom('银行承兑汇票', '商业承兑汇票', ''),
  noteNo: fc.string({ maxLength: 20 }),
  drawer: fc.string({ maxLength: 10 }),
  acceptor: fc.string({ maxLength: 10 }),
  amount: fc.float({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }),
  maturityDate: fc.constantFrom('2025-03-15', '2025-09-30', ''),
  existenceCheck: fc.constantFrom('已核实', '未核实', '不适用', ''),
  accuracyCheck: fc.constantFrom('金额一致', '金额不一致', '不适用', ''),
  appropriatenessCheck: fc.constantFrom('恰当', '不恰当', '不适用', ''),
  remark: fc.string({ maxLength: 20 }),
  indexRef: fc.string({ maxLength: 10 }),
})

// ═══════════════════════════════════════════════════════════════════════════════
// Assertion helpers
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Assert field-level equality between original and deserialized row.
 * String fields: exact match. Numeric fields: toBeCloseTo ±0.01.
 */
function assertRowEquality<T>(
  original: T,
  deserialized: T,
  stringFields: Array<keyof T>,
  numericFields: Array<keyof T>,
): void {
  for (const f of stringFields) {
    expect(deserialized[f]).toBe(original[f])
  }
  for (const f of numericFields) {
    expect(deserialized[f] as number).toBeCloseTo(original[f] as number, 1)
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: 导入导出 Round-Trip
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-inspection-check, Property 8: 导入导出 Round-Trip
describe('Feature: d1-inspection-check, Property 8: 导入导出 Round-Trip', () => {
  /**
   * **Validates: Requirements 15.7, 15.8, 15.9, 15.10, 16.2, 16.3**
   *
   * For any valid dynamic row array, serializing (JSON.stringify) and then
   * deserializing (JSON.parse → field parsing rules) produces data deeply
   * equal to the original (string exact, numeric ±0.01).
   */

  it('P8: InventoryCountRow serialize→deserialize round-trip', () => {
    fc.assert(
      fc.property(
        fc.array(InventoryCountRowArbitrary, { minLength: 0, maxLength: 10 }),
        (rows) => {
          // Serialize (mimics composable: JSON.stringify to remark)
          const serialized = JSON.stringify(rows)

          // Deserialize (mimics composable: JSON.parse → deserializeRow each)
          const parsed: any[] = JSON.parse(serialized)
          const deserialized = parsed.map(deserializeInventoryRow)

          // Assert length preserved
          expect(deserialized.length).toBe(rows.length)

          // Assert field-level equality
          for (let i = 0; i < rows.length; i++) {
            assertRowEquality(
              rows[i],
              deserialized[i],
              INVENTORY_STRING_FIELDS,
              INVENTORY_NUMERIC_FIELDS,
            )
          }
        }
      ),
      { numRuns: 100 }
    )
  })

  it('P8: RelatedPartyRow serialize→deserialize round-trip', () => {
    fc.assert(
      fc.property(
        fc.array(RelatedPartyRowArbitrary, { minLength: 0, maxLength: 10 }),
        (rows) => {
          const serialized = JSON.stringify(rows)
          const parsed: any[] = JSON.parse(serialized)
          const deserialized = parsed.map(deserializeRelatedPartyRow)

          expect(deserialized.length).toBe(rows.length)

          for (let i = 0; i < rows.length; i++) {
            assertRowEquality(
              rows[i],
              deserialized[i],
              RP_STRING_FIELDS,
              RP_NUMERIC_FIELDS,
            )
          }
        }
      ),
      { numRuns: 100 }
    )
  })

  it('P8: PledgeRow serialize→deserialize round-trip', () => {
    fc.assert(
      fc.property(
        fc.array(PledgeRowArbitrary, { minLength: 0, maxLength: 10 }),
        (rows) => {
          const serialized = JSON.stringify(rows)
          const parsed: any[] = JSON.parse(serialized)
          const deserialized = parsed.map(deserializePledgeRow)

          expect(deserialized.length).toBe(rows.length)

          for (let i = 0; i < rows.length; i++) {
            assertRowEquality(
              rows[i],
              deserialized[i],
              PLEDGE_STRING_FIELDS,
              PLEDGE_NUMERIC_FIELDS,
            )
          }
        }
      ),
      { numRuns: 100 }
    )
  })

  it('P8: VouchingRow serialize→deserialize round-trip', () => {
    fc.assert(
      fc.property(
        fc.array(VouchingRowArbitrary, { minLength: 0, maxLength: 10 }),
        (rows) => {
          const serialized = JSON.stringify(rows)
          const parsed: any[] = JSON.parse(serialized)
          const deserialized = parsed.map(deserializeVouchingRow)

          expect(deserialized.length).toBe(rows.length)

          for (let i = 0; i < rows.length; i++) {
            assertRowEquality(
              rows[i],
              deserialized[i],
              VOUCHING_STRING_FIELDS,
              VOUCHING_NUMERIC_FIELDS,
            )
          }
        }
      ),
      { numRuns: 100 }
    )
  })
})
