/**
 * Property-Based Tests — D2-7 导入导出 round trip
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 6.2
 *
 * 使用 fast-check + vitest 验证 Property 17: Import/Export round trip
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  serializeRowsToSheetData,
  deserializeSheetDataToRows,
  COLUMN_HEADERS,
} from '../useD2VcImportExport'
import type { VoucherCheckRow } from '../useD2VoucherCheckEnhanced'

// ─── Generators ──────────────────────────────────────────────────────────────

/**
 * 生成合法的 VoucherCheckRow（17 列业务字段 + 元数据）
 * 为保证 round trip 成功，凭证编号需唯一且非空（用于按 key 比较）
 */
function arbVoucherCheckRow(idSuffix: number): fc.Arbitrary<VoucherCheckRow> {
  return fc.record({
    rowId: fc.constant(`vcr-test-${idSuffix}`),
    seq: fc.constant(idSuffix),
    customerName: fc.string({ minLength: 0, maxLength: 20 }).map((s) => s.replace(/[\r\n\t]/g, '')),
    voucherDate: fc.constantFrom('2025-01-15', '2025-03-20', '2025-06-30', '2025-12-31', ''),
    voucherNo: fc.constant(`PZ-${String(idSuffix).padStart(4, '0')}`), // Unique per row
    businessContent: fc.string({ minLength: 0, maxLength: 30 }).map((s) => s.replace(/[\r\n\t]/g, '')),
    counterpartAccount: fc.constantFrom('6001', '6401', '1001', '2202', ''),
    counterpartDetail: fc.constantFrom('主营业务收入', '管理费用-办公费', '银行存款-工行', ''),
    debitAmount: fc.oneof(fc.constant(0), fc.double({ min: 0, max: 9999999.99, noNaN: true, noDefaultInfinity: true }).map((v) => Math.round(v * 100) / 100)),
    creditAmount: fc.oneof(fc.constant(0), fc.double({ min: 0, max: 9999999.99, noNaN: true, noDefaultInfinity: true }).map((v) => Math.round(v * 100) / 100)),
    supportingDoc: fc.constantFrom('', '发票#001', '合同附件.pdf'),
    check1: fc.constantFrom('', '一致', '不一致', '无法判定'),
    check2: fc.constantFrom('', '一致', '不一致', '无法判定'),
    check3: fc.constantFrom('', '一致', '不一致', '无法判定'),
    check4: fc.constantFrom('', '相符', '不相符', '无法判定'),
    check5: fc.constantFrom('', '完整', '不完整', '无法判定'),
    indexRef: fc.constantFrom('', 'D2-7-001', 'D2-7-002'),
    isAbnormal: fc.constantFrom('', '是', '否', '跨期疑点', '金额异常'),
    remark: fc.string({ minLength: 0, maxLength: 20 }).map((s) => s.replace(/[\r\n\t]/g, '')),
    // Metadata fields — NOT preserved in round trip
    attachments: fc.constant([]),
    ocrResult: fc.constant(undefined),
    source: fc.constantFrom(undefined, '手动', '抽凭', '导入'),
  })
}

/**
 * 生成包含 1~10 行的 VoucherCheckRow 数组（凭证编号唯一）
 */
const arbVoucherCheckRows: fc.Arbitrary<VoucherCheckRow[]> = fc
  .integer({ min: 1, max: 10 })
  .chain((len) =>
    fc.tuple(...Array.from({ length: len }, (_, i) => arbVoucherCheckRow(i + 1)))
  )

// ─── 17 列业务字段（不含元数据） ─────────────────────────────────────────────

const BUSINESS_FIELDS: (keyof VoucherCheckRow)[] = [
  'customerName',
  'voucherDate',
  'voucherNo',
  'businessContent',
  'counterpartAccount',
  'counterpartDetail',
  'debitAmount',
  'creditAmount',
  'supportingDoc',
  'check1',
  'check2',
  'check3',
  'check4',
  'check5',
  'indexRef',
  'isAbnormal',
  'remark',
]

/**
 * 按凭证编号建立 Map，用于按 key 比较
 */
function indexByVoucherNo(rows: VoucherCheckRow[]): Map<string, VoucherCheckRow> {
  const map = new Map<string, VoucherCheckRow>()
  for (const row of rows) {
    map.set(row.voucherNo, row)
  }
  return map
}

/**
 * 比较两行的 17 列业务字段是否等价
 * - 数字字段用 === 比较（serialize 保证 number 类型输出）
 * - 字符串字段：serialize 把 null/undefined 转 ''，所以比较原始值的 String 转换
 */
function assertBusinessFieldsEqual(original: VoucherCheckRow, roundTripped: VoucherCheckRow): void {
  for (const field of BUSINESS_FIELDS) {
    const origVal = original[field]
    const rtVal = roundTripped[field]

    if (field === 'debitAmount' || field === 'creditAmount') {
      // 数字字段：serialize 会把 non-number 转 Number(x)||0
      const expectedNum = typeof origVal === 'number' ? origVal : Number(origVal) || 0
      expect(rtVal, `Field ${field} mismatch for voucherNo=${original.voucherNo}`).toBe(expectedNum)
    } else {
      // 字符串字段：serialize/deserialize 均 trim（whitespace-only → ''）
      const expectedStr = origVal != null ? String(origVal).trim() : ''
      expect(rtVal, `Field ${field} mismatch for voucherNo=${original.voucherNo}`).toBe(expectedStr)
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Property 17: Import/Export round trip
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-7-voucher-check-enhancement, Property 17: Import/Export round trip', () => {
  /**
   * **Validates: Requirements 12.3, 12.4**
   *
   * For any dual-zone dataset (currentRows, postRows), exporting to xlsx format
   * (two sheets as 2D arrays) and then importing that data back should produce
   * datasets equivalent to the originals (preserving all 17 column values per row,
   * ordering may differ but content is identical by voucherNo key).
   */

  it('single zone round trip: serialize → deserialize preserves 17 business columns', () => {
    fc.assert(
      fc.property(
        arbVoucherCheckRows,
        (rows) => {
          // Export: rows → 2D array (with header row)
          const sheetData = serializeRowsToSheetData(rows)

          // Import: 2D array → rows
          const imported = deserializeSheetDataToRows(sheetData)

          // Same row count
          expect(imported.length).toBe(rows.length)

          // Compare by voucherNo key
          const originalMap = indexByVoucherNo(rows)
          const importedMap = indexByVoucherNo(imported)

          expect(importedMap.size).toBe(originalMap.size)

          for (const [voucherNo, origRow] of originalMap) {
            const rtRow = importedMap.get(voucherNo)
            expect(rtRow, `Missing voucherNo=${voucherNo} after round trip`).toBeDefined()
            assertBusinessFieldsEqual(origRow, rtRow!)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('dual zone round trip: both currentRows and postRows preserve independently', () => {
    fc.assert(
      fc.property(
        arbVoucherCheckRows,
        arbVoucherCheckRows.map((rows) =>
          // Offset IDs for postRows to ensure unique voucherNo across both zones
          rows.map((r, i) => ({ ...r, voucherNo: `PZ-POST-${String(i + 1).padStart(4, '0')}`, rowId: `vcr-post-${i}` }))
        ),
        (currentRows, postRows) => {
          // Export both zones
          const currentSheet = serializeRowsToSheetData(currentRows)
          const postSheet = serializeRowsToSheetData(postRows)

          // Import both zones
          const importedCurrent = deserializeSheetDataToRows(currentSheet)
          const importedPost = deserializeSheetDataToRows(postSheet)

          // Verify current zone
          expect(importedCurrent.length).toBe(currentRows.length)
          const currentOrigMap = indexByVoucherNo(currentRows)
          const currentImportMap = indexByVoucherNo(importedCurrent)
          for (const [voucherNo, origRow] of currentOrigMap) {
            const rtRow = currentImportMap.get(voucherNo)
            expect(rtRow, `currentZone: missing voucherNo=${voucherNo}`).toBeDefined()
            assertBusinessFieldsEqual(origRow, rtRow!)
          }

          // Verify post zone
          expect(importedPost.length).toBe(postRows.length)
          const postOrigMap = indexByVoucherNo(postRows)
          const postImportMap = indexByVoucherNo(importedPost)
          for (const [voucherNo, origRow] of postOrigMap) {
            const rtRow = postImportMap.get(voucherNo)
            expect(rtRow, `postZone: missing voucherNo=${voucherNo}`).toBeDefined()
            assertBusinessFieldsEqual(origRow, rtRow!)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('metadata fields (rowId, seq, attachments, ocrResult, source) are NOT preserved — round trip generates fresh metadata', () => {
    fc.assert(
      fc.property(
        arbVoucherCheckRows,
        (rows) => {
          const sheetData = serializeRowsToSheetData(rows)
          const imported = deserializeSheetDataToRows(sheetData)

          for (const importedRow of imported) {
            // rowId should be regenerated (not match original)
            // source should be '导入' (set by createEmptyImportRow)
            expect(importedRow.source).toBe('导入')
            // attachments should be empty array
            expect(importedRow.attachments).toEqual([])
            // ocrResult should be undefined
            expect(importedRow.ocrResult).toBeUndefined()
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('header row is exactly COLUMN_HEADERS (17 entries)', () => {
    fc.assert(
      fc.property(
        arbVoucherCheckRows,
        (rows) => {
          const sheetData = serializeRowsToSheetData(rows)

          // First row is header
          expect(sheetData[0]).toEqual(COLUMN_HEADERS)
          expect(sheetData[0].length).toBe(17)

          // Data rows count matches input
          expect(sheetData.length).toBe(rows.length + 1)
        },
      ),
      { numRuns: 100 },
    )
  })
})
