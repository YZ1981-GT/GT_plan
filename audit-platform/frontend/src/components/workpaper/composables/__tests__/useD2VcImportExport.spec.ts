/**
 * useD2VcImportExport — Unit tests for pure functions
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 6.1
 *
 * Tests:
 * - serializeRowsToSheetData: row → 2D array conversion
 * - deserializeSheetDataToRows: 2D array → row conversion
 * - buildHeaderMap: header row → field index mapping
 * - Round-trip: serialize then deserialize preserves data
 * - Missing/extra columns handling
 * - Empty/null cell tolerance
 */
import { describe, it, expect, vi } from 'vitest'
import {
  serializeRowsToSheetData,
  deserializeSheetDataToRows,
  buildHeaderMap,
  COLUMN_HEADERS,
  HEADER_TO_FIELD_MAP,
  SHEET_NAME_CURRENT,
  SHEET_NAME_POST,
} from '../useD2VcImportExport'
import type { VoucherCheckRow } from '../useD2VoucherCheckEnhanced'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeRow(overrides: Partial<VoucherCheckRow> = {}): VoucherCheckRow {
  return {
    rowId: 'test-row-1',
    seq: 1,
    customerName: '测试客户',
    voucherDate: '2025-06-15',
    voucherNo: 'PZ-001',
    businessContent: '货款',
    counterpartAccount: '银行存款',
    counterpartDetail: '工商银行',
    debitAmount: 10000,
    creditAmount: 0,
    supportingDoc: '发票#001',
    check1: '一致',
    check2: '一致',
    check3: '匹配',
    check4: '',
    check5: '',
    indexRef: 'D2-7-1',
    isAbnormal: '',
    remark: '正常',
    attachments: [],
    source: '手动',
    ...overrides,
  }
}

// ─── serializeRowsToSheetData ────────────────────────────────────────────────

describe('serializeRowsToSheetData', () => {
  it('should produce header row as first element with 17 columns', () => {
    const result = serializeRowsToSheetData([])
    expect(result).toHaveLength(1) // only header row
    expect(result[0]).toEqual(COLUMN_HEADERS)
    expect(result[0]).toHaveLength(17)
  })

  it('should serialize a single row correctly', () => {
    const row = makeRow()
    const result = serializeRowsToSheetData([row])
    expect(result).toHaveLength(2) // header + 1 data row

    const dataRow = result[1]
    expect(dataRow[0]).toBe('测试客户')       // 客户名称
    expect(dataRow[1]).toBe('2025-06-15')     // 日期
    expect(dataRow[2]).toBe('PZ-001')         // 凭证编号
    expect(dataRow[3]).toBe('货款')           // 业务内容
    expect(dataRow[4]).toBe('银行存款')       // 对方科目
    expect(dataRow[5]).toBe('工商银行')       // 对方明细科目
    expect(dataRow[6]).toBe(10000)            // 借方金额 (number)
    expect(dataRow[7]).toBe(0)                // 贷方金额 (number)
    expect(dataRow[8]).toBe('发票#001')       // 支持性文件
    expect(dataRow[9]).toBe('一致')           // 核对内容1
    expect(dataRow[10]).toBe('一致')          // 核对内容2
    expect(dataRow[11]).toBe('匹配')          // 核对内容3
    expect(dataRow[12]).toBe('')              // 核对内容4
    expect(dataRow[13]).toBe('')              // 核对内容5
    expect(dataRow[14]).toBe('D2-7-1')       // 索引号
    expect(dataRow[15]).toBe('')              // 是否异常
    expect(dataRow[16]).toBe('正常')          // 备注说明
  })

  it('should serialize multiple rows', () => {
    const rows = [makeRow({ seq: 1 }), makeRow({ seq: 2, customerName: '客户B' })]
    const result = serializeRowsToSheetData(rows)
    expect(result).toHaveLength(3) // header + 2 data rows
    expect(result[1][0]).toBe('测试客户')
    expect(result[2][0]).toBe('客户B')
  })

  it('should handle numeric amounts correctly', () => {
    const row = makeRow({ debitAmount: 123.45, creditAmount: 67.89 })
    const result = serializeRowsToSheetData([row])
    expect(result[1][6]).toBe(123.45)
    expect(result[1][7]).toBe(67.89)
  })
})

// ─── buildHeaderMap ──────────────────────────────────────────────────────────

describe('buildHeaderMap', () => {
  it('should map standard headers to correct field indices', () => {
    const map = buildHeaderMap(COLUMN_HEADERS)
    expect(map.size).toBe(17)
    expect(map.get(0)).toBe('customerName')
    expect(map.get(1)).toBe('voucherDate')
    expect(map.get(2)).toBe('voucherNo')
    expect(map.get(6)).toBe('debitAmount')
    expect(map.get(7)).toBe('creditAmount')
    expect(map.get(16)).toBe('remark')
  })

  it('should handle reordered columns', () => {
    const reordered = ['凭证编号', '客户名称', '借方金额', '备注说明']
    const map = buildHeaderMap(reordered)
    expect(map.size).toBe(4)
    expect(map.get(0)).toBe('voucherNo')
    expect(map.get(1)).toBe('customerName')
    expect(map.get(2)).toBe('debitAmount')
    expect(map.get(3)).toBe('remark')
  })

  it('should skip unrecognized headers and warn', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const headers = ['客户名称', '未知列', '凭证编号', '另一个未知']
    const map = buildHeaderMap(headers)
    expect(map.size).toBe(2)
    expect(map.get(0)).toBe('customerName')
    expect(map.get(2)).toBe('voucherNo')
    expect(warnSpy).toHaveBeenCalledTimes(1)
    expect(warnSpy.mock.calls[0][0]).toContain('未知列')
    expect(warnSpy.mock.calls[0][0]).toContain('另一个未知')
    warnSpy.mockRestore()
  })

  it('should handle null/empty values in header row', () => {
    const headers = ['客户名称', null, '', '凭证编号', undefined]
    const map = buildHeaderMap(headers as any)
    expect(map.size).toBe(2)
    expect(map.get(0)).toBe('customerName')
    expect(map.get(3)).toBe('voucherNo')
  })

  it('should trim whitespace from header text', () => {
    const headers = ['  客户名称  ', ' 凭证编号 ']
    const map = buildHeaderMap(headers)
    expect(map.size).toBe(2)
    expect(map.get(0)).toBe('customerName')
    expect(map.get(1)).toBe('voucherNo')
  })
})

// ─── deserializeSheetDataToRows ──────────────────────────────────────────────

describe('deserializeSheetDataToRows', () => {
  it('should return empty array for empty sheet data', () => {
    expect(deserializeSheetDataToRows([])).toEqual([])
    expect(deserializeSheetDataToRows([COLUMN_HEADERS])).toEqual([]) // only header, no data
  })

  it('should deserialize a simple row correctly', () => {
    const sheetData = [
      COLUMN_HEADERS,
      ['客户A', '2025-01-01', 'V001', '销售', '银行', '工行', 5000, 0, '', '', '', '', '', '', 'I-1', '', '备注'],
    ]
    const rows = deserializeSheetDataToRows(sheetData)
    expect(rows).toHaveLength(1)
    expect(rows[0].customerName).toBe('客户A')
    expect(rows[0].voucherDate).toBe('2025-01-01')
    expect(rows[0].voucherNo).toBe('V001')
    expect(rows[0].businessContent).toBe('销售')
    expect(rows[0].counterpartAccount).toBe('银行')
    expect(rows[0].counterpartDetail).toBe('工行')
    expect(rows[0].debitAmount).toBe(5000)
    expect(rows[0].creditAmount).toBe(0)
    expect(rows[0].indexRef).toBe('I-1')
    expect(rows[0].remark).toBe('备注')
  })

  it('should handle reordered columns', () => {
    const headers = ['凭证编号', '借方金额', '客户名称']
    const sheetData = [
      headers,
      ['V002', 8888, '客户B'],
    ]
    const rows = deserializeSheetDataToRows(sheetData)
    expect(rows).toHaveLength(1)
    expect(rows[0].voucherNo).toBe('V002')
    expect(rows[0].debitAmount).toBe(8888)
    expect(rows[0].customerName).toBe('客户B')
    // Unmapped fields should remain defaults
    expect(rows[0].creditAmount).toBe(0)
    expect(rows[0].remark).toBe('')
  })

  it('should skip empty rows', () => {
    const sheetData = [
      COLUMN_HEADERS,
      ['客户A', '2025-01-01', 'V001', '', '', '', 0, 0, '', '', '', '', '', '', '', '', ''],
      [null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null],
      ['客户B', '2025-02-01', 'V002', '', '', '', 100, 0, '', '', '', '', '', '', '', '', ''],
    ]
    const rows = deserializeSheetDataToRows(sheetData)
    expect(rows).toHaveLength(2)
    expect(rows[0].voucherNo).toBe('V001')
    expect(rows[1].voucherNo).toBe('V002')
  })

  it('should accept pre-built header map', () => {
    const headerMap = new Map<number, keyof VoucherCheckRow>([
      [0, 'voucherNo'],
      [1, 'debitAmount'],
    ])
    const sheetData = [
      ['凭证编号', '借方金额'],  // header row (ignored when map provided)
      ['V003', 777],
    ]
    const rows = deserializeSheetDataToRows(sheetData, headerMap)
    expect(rows).toHaveLength(1)
    expect(rows[0].voucherNo).toBe('V003')
    expect(rows[0].debitAmount).toBe(777)
  })

  it('should handle null cells gracefully', () => {
    const sheetData = [
      COLUMN_HEADERS,
      [null, '2025-03-01', null, '内容', null, null, null, null, null, null, null, null, null, null, null, null, null],
    ]
    const rows = deserializeSheetDataToRows(sheetData)
    expect(rows).toHaveLength(1)
    expect(rows[0].customerName).toBe('')
    expect(rows[0].voucherDate).toBe('2025-03-01')
    expect(rows[0].voucherNo).toBe('')
    expect(rows[0].debitAmount).toBe(0)
  })

  it('should parse numeric strings for amount fields', () => {
    const sheetData = [
      ['借方金额', '贷方金额'],
      ['1234.56', '789.01'],
    ]
    const rows = deserializeSheetDataToRows(sheetData)
    expect(rows).toHaveLength(1)
    expect(rows[0].debitAmount).toBe(1234.56)
    expect(rows[0].creditAmount).toBe(789.01)
  })
})

// ─── Round-trip test ─────────────────────────────────────────────────────────

describe('serialize/deserialize round trip', () => {
  it('should preserve data through serialize→deserialize cycle', () => {
    const originalRows = [
      makeRow({ seq: 1, voucherNo: 'PZ-001', debitAmount: 10000, creditAmount: 0 }),
      makeRow({ seq: 2, voucherNo: 'PZ-002', customerName: '另一客户', debitAmount: 0, creditAmount: 5000 }),
    ]

    const sheetData = serializeRowsToSheetData(originalRows)
    const deserialized = deserializeSheetDataToRows(sheetData)

    expect(deserialized).toHaveLength(2)

    // Compare 17 data fields (excluding metadata: rowId, seq, attachments, ocrResult, source)
    for (let i = 0; i < originalRows.length; i++) {
      const orig = originalRows[i]
      const deser = deserialized[i]
      expect(deser.customerName).toBe(orig.customerName)
      expect(deser.voucherDate).toBe(orig.voucherDate)
      expect(deser.voucherNo).toBe(orig.voucherNo)
      expect(deser.businessContent).toBe(orig.businessContent)
      expect(deser.counterpartAccount).toBe(orig.counterpartAccount)
      expect(deser.counterpartDetail).toBe(orig.counterpartDetail)
      expect(deser.debitAmount).toBe(orig.debitAmount)
      expect(deser.creditAmount).toBe(orig.creditAmount)
      expect(deser.supportingDoc).toBe(orig.supportingDoc)
      expect(deser.check1).toBe(orig.check1)
      expect(deser.check2).toBe(orig.check2)
      expect(deser.check3).toBe(orig.check3)
      expect(deser.check4).toBe(orig.check4)
      expect(deser.check5).toBe(orig.check5)
      expect(deser.indexRef).toBe(orig.indexRef)
      expect(deser.isAbnormal).toBe(orig.isAbnormal)
      expect(deser.remark).toBe(orig.remark)
    }
  })
})

// ─── Constants verification ──────────────────────────────────────────────────

describe('constants', () => {
  it('should have 17 column headers', () => {
    expect(COLUMN_HEADERS).toHaveLength(17)
  })

  it('should have matching HEADER_TO_FIELD_MAP entries for all headers', () => {
    for (const header of COLUMN_HEADERS) {
      expect(HEADER_TO_FIELD_MAP[header]).toBeDefined()
    }
  })

  it('should export correct sheet names', () => {
    expect(SHEET_NAME_CURRENT).toBe('本期增减变动检查')
    expect(SHEET_NAME_POST).toBe('期后收款调整检查')
  })
})
