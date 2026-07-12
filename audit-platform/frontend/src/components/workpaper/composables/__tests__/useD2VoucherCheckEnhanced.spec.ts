/**
 * useD2VoucherCheckEnhanced — Unit Tests
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 1.1
 *
 * Tests:
 * - classifyVoucherToZone pure function
 * - mapSampledVoucher field mapping
 * - mergeVoucherRows deduplication logic
 * - Dual zone state isolation
 * - View mode switching
 * - Row CRUD operations
 * - Persistence (loadFromResponses / saveToResponses)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  classifyVoucherToZone,
  mapSampledVoucher,
  mergeVoucherRows,
  useD2VoucherCheckEnhanced,
  type VoucherCheckRow,
  type SampledVoucher,
  type UseD2VoucherCheckEnhancedOptions,
} from '../useD2VoucherCheckEnhanced'

// Mock inject to avoid Vue runtime errors in unit tests
vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return {
    ...actual as any,
    inject: () => null,
    onBeforeUnmount: () => {},
  }
})

// ─── classifyVoucherToZone ─────────────────────────────────────────────────

describe('classifyVoucherToZone', () => {
  it('returns "current" when voucherDate <= bsDate', () => {
    expect(classifyVoucherToZone('2025-06-15', '2025-12-31')).toBe('current')
    expect(classifyVoucherToZone('2025-12-31', '2025-12-31')).toBe('current')
  })

  it('returns "post" when voucherDate > bsDate', () => {
    expect(classifyVoucherToZone('2026-01-05', '2025-12-31')).toBe('post')
    expect(classifyVoucherToZone('2026-03-15', '2025-12-31')).toBe('post')
  })

  it('returns "current" when voucherDate is empty', () => {
    expect(classifyVoucherToZone('', '2025-12-31')).toBe('current')
  })

  it('returns "current" when bsDate is empty', () => {
    expect(classifyVoucherToZone('2025-06-15', '')).toBe('current')
  })

  it('returns "current" when both are empty', () => {
    expect(classifyVoucherToZone('', '')).toBe('current')
  })
})

// ─── mapSampledVoucher ─────────────────────────────────────────────────────

describe('mapSampledVoucher', () => {
  it('maps all fields correctly', () => {
    const voucher: SampledVoucher = {
      voucherNo: 'PZ-2025-001',
      voucherDate: '2025-06-15',
      debitAmount: 10000,
      creditAmount: 0,
      summary: '销售商品',
      counterpartAccount: '6001',
      accountCode: '600101',
      customerName: '客户A',
    }

    const row = mapSampledVoucher(voucher, 1)

    expect(row.seq).toBe(1)
    expect(row.voucherNo).toBe('PZ-2025-001')
    expect(row.voucherDate).toBe('2025-06-15')
    expect(row.debitAmount).toBe(10000)
    expect(row.creditAmount).toBe(0)
    expect(row.businessContent).toBe('销售商品')
    expect(row.counterpartAccount).toBe('6001')
    expect(row.counterpartDetail).toBe('600101')
    expect(row.customerName).toBe('客户A')
    expect(row.source).toBe('自动抽凭')
    expect(row.rowId).toBeTruthy()
    expect(row.attachments).toEqual([])
  })

  it('handles missing optional fields', () => {
    const voucher: SampledVoucher = {
      voucherNo: 'PZ-001',
      voucherDate: '2025-01-01',
    }

    const row = mapSampledVoucher(voucher, 5)

    expect(row.seq).toBe(5)
    expect(row.debitAmount).toBe(0)
    expect(row.creditAmount).toBe(0)
    expect(row.businessContent).toBe('')
    expect(row.counterpartAccount).toBe('')
    expect(row.counterpartDetail).toBe('')
    expect(row.customerName).toBe('')
  })
})

// ─── mergeVoucherRows ──────────────────────────────────────────────────────

describe('mergeVoucherRows', () => {
  function makeRow(voucherNo: string, check1 = ''): VoucherCheckRow {
    return {
      rowId: `row-${voucherNo}`,
      seq: 0,
      customerName: '',
      voucherDate: '',
      voucherNo,
      businessContent: '',
      counterpartAccount: '',
      counterpartDetail: '',
      debitAmount: 0,
      creditAmount: 0,
      supportingDoc: '',
      check1,
      check2: '',
      check3: '',
      check4: '',
      check5: '',
      indexRef: '',
      isAbnormal: '',
      remark: '',
      attachments: [],
    }
  }

  it('appends new vouchers not in existing set', () => {
    const existing = [makeRow('PZ-001'), makeRow('PZ-002')]
    const incoming = [makeRow('PZ-003'), makeRow('PZ-004')]

    const result = mergeVoucherRows(existing, incoming)

    expect(result).toHaveLength(4)
    expect(result.map(r => r.voucherNo)).toEqual(['PZ-001', 'PZ-002', 'PZ-003', 'PZ-004'])
  })

  it('does not duplicate existing voucher numbers', () => {
    const existing = [makeRow('PZ-001', '一致'), makeRow('PZ-002', '不一致')]
    const incoming = [makeRow('PZ-001'), makeRow('PZ-003')]

    const result = mergeVoucherRows(existing, incoming)

    expect(result).toHaveLength(3)
    // Existing row PZ-001 retains its check1 value
    expect(result[0].check1).toBe('一致')
    expect(result[1].voucherNo).toBe('PZ-002')
    expect(result[2].voucherNo).toBe('PZ-003')
  })

  it('preserves check1~check5 of existing rows', () => {
    const existing = [makeRow('PZ-001', '金额一致')]
    existing[0].check2 = '日期一致'
    existing[0].check3 = '科目匹配'
    existing[0].check4 = '内容相符'
    existing[0].check5 = '附件完整'

    const incoming = [makeRow('PZ-001')]

    const result = mergeVoucherRows(existing, incoming)

    expect(result).toHaveLength(1)
    expect(result[0].check1).toBe('金额一致')
    expect(result[0].check2).toBe('日期一致')
    expect(result[0].check3).toBe('科目匹配')
    expect(result[0].check4).toBe('内容相符')
    expect(result[0].check5).toBe('附件完整')
  })

  it('re-sequences all rows correctly', () => {
    const existing = [makeRow('PZ-001')]
    const incoming = [makeRow('PZ-002'), makeRow('PZ-003')]

    const result = mergeVoucherRows(existing, incoming)

    expect(result[0].seq).toBe(1)
    expect(result[1].seq).toBe(2)
    expect(result[2].seq).toBe(3)
  })

  it('handles empty existing array', () => {
    const incoming = [makeRow('PZ-001'), makeRow('PZ-002')]
    const result = mergeVoucherRows([], incoming)
    expect(result).toHaveLength(2)
  })

  it('handles empty incoming array', () => {
    const existing = [makeRow('PZ-001')]
    const result = mergeVoucherRows(existing, [])
    expect(result).toHaveLength(1)
  })

  it('handles rows with empty voucherNo (always appended)', () => {
    const existing = [makeRow('PZ-001')]
    const incoming = [makeRow('')]

    const result = mergeVoucherRows(existing, incoming)

    // empty voucherNo is not in existingNos set, so appended
    expect(result).toHaveLength(2)
  })
})

// ─── useD2VoucherCheckEnhanced composable ──────────────────────────────────

describe('useD2VoucherCheckEnhanced', () => {
  let options: UseD2VoucherCheckEnhancedOptions

  beforeEach(() => {
    options = {
      allResponses: ref(new Map()),
      isReadonly: ref(false),
      bsDate: ref('2025-12-31'),
    }
  })

  it('initializes with empty state', () => {
    const { currentRows, postRows, activeZone, viewMode } = useD2VoucherCheckEnhanced(options)

    expect(currentRows.value).toEqual([])
    expect(postRows.value).toEqual([])
    expect(activeZone.value).toBe('current')
    expect(viewMode.value).toBe('matrix')
  })

  it('switches zone without affecting other zone data', () => {
    const { currentRows, postRows, activeZone, switchZone, addRow } = useD2VoucherCheckEnhanced(options)

    // Add row to current zone
    addRow()
    expect(currentRows.value).toHaveLength(1)
    expect(postRows.value).toHaveLength(0)

    // Switch to post zone
    switchZone('post')
    expect(activeZone.value).toBe('post')
    expect(currentRows.value).toHaveLength(1) // unchanged

    // Add row to post zone
    addRow()
    expect(postRows.value).toHaveLength(1)
    expect(currentRows.value).toHaveLength(1) // still unchanged

    // Switch back
    switchZone('current')
    expect(currentRows.value).toHaveLength(1)
    expect(postRows.value).toHaveLength(1)
  })

  it('switches view mode without affecting data', () => {
    const { currentRows, viewMode, switchViewMode, addRow } = useD2VoucherCheckEnhanced(options)

    addRow()
    const rowBefore = { ...currentRows.value[0] }

    switchViewMode('card')
    expect(viewMode.value).toBe('card')
    expect(currentRows.value[0].rowId).toBe(rowBefore.rowId)

    switchViewMode('matrix')
    expect(viewMode.value).toBe('matrix')
    expect(currentRows.value[0].rowId).toBe(rowBefore.rowId)
  })

  it('addRow adds to active zone', () => {
    const { currentRows, postRows, switchZone, addRow } = useD2VoucherCheckEnhanced(options)

    addRow()
    expect(currentRows.value).toHaveLength(1)
    expect(currentRows.value[0].seq).toBe(1)

    switchZone('post')
    addRow()
    addRow()
    expect(postRows.value).toHaveLength(2)
    expect(postRows.value[0].seq).toBe(1)
    expect(postRows.value[1].seq).toBe(2)
  })

  it('removeRow removes from active zone and re-sequences', () => {
    const { currentRows, addRow, removeRow } = useD2VoucherCheckEnhanced(options)

    addRow()
    addRow()
    addRow()
    const secondRowId = currentRows.value[1].rowId

    removeRow(secondRowId)

    expect(currentRows.value).toHaveLength(2)
    expect(currentRows.value[0].seq).toBe(1)
    expect(currentRows.value[1].seq).toBe(2)
  })

  it('updateRow updates field in active zone', () => {
    const { currentRows, addRow, updateRow } = useD2VoucherCheckEnhanced(options)

    addRow()
    const rowId = currentRows.value[0].rowId

    updateRow(rowId, 'customerName', '测试客户')
    expect(currentRows.value[0].customerName).toBe('测试客户')

    updateRow(rowId, 'debitAmount', 5000)
    expect(currentRows.value[0].debitAmount).toBe(5000)
  })

  it('does not mutate data in readonly mode', () => {
    options.isReadonly = ref(true)
    const { currentRows, addRow, updateRow } = useD2VoucherCheckEnhanced(options)

    addRow()
    expect(currentRows.value).toHaveLength(0)
  })

  it('loadFromResponses parses stored JSON', () => {
    const rows = [
      {
        rowId: 'r1',
        seq: 1,
        customerName: '客户A',
        voucherDate: '2025-06-01',
        voucherNo: 'PZ-001',
        businessContent: '销售',
        counterpartAccount: '6001',
        counterpartDetail: '',
        debitAmount: 1000,
        creditAmount: 0,
        supportingDoc: '',
        check1: '一致',
        check2: '',
        check3: '',
        check4: '',
        check5: '',
        indexRef: '',
        isAbnormal: '',
        remark: '',
        attachments: [],
      },
    ]
    options.allResponses.value.set('D2-vc-current-rows', {
      item_id: 'D2-vc-current-rows',
      conclusion: null,
      remark: JSON.stringify(rows),
    })

    const { currentRows, loadFromResponses } = useD2VoucherCheckEnhanced(options)
    loadFromResponses()

    expect(currentRows.value).toHaveLength(1)
    expect(currentRows.value[0].customerName).toBe('客户A')
    expect(currentRows.value[0].check1).toBe('一致')
  })

  it('saveToResponses serializes both zones', () => {
    const { currentRows, postRows, saveToResponses } = useD2VoucherCheckEnhanced(options)

    currentRows.value = [
      { rowId: 'r1', seq: 1, customerName: 'A', voucherDate: '', voucherNo: 'PZ-1',
        businessContent: '', counterpartAccount: '', counterpartDetail: '',
        debitAmount: 100, creditAmount: 0, supportingDoc: '',
        check1: '', check2: '', check3: '', check4: '', check5: '',
        indexRef: '', isAbnormal: '', remark: '', attachments: [] },
    ]
    postRows.value = [
      { rowId: 'r2', seq: 1, customerName: 'B', voucherDate: '', voucherNo: 'PZ-2',
        businessContent: '', counterpartAccount: '', counterpartDetail: '',
        debitAmount: 200, creditAmount: 0, supportingDoc: '',
        check1: '', check2: '', check3: '', check4: '', check5: '',
        indexRef: '', isAbnormal: '', remark: '', attachments: [] },
    ]

    saveToResponses()

    const currentStored = options.allResponses.value.get('D2-vc-current-rows')
    const postStored = options.allResponses.value.get('D2-vc-post-rows')

    expect(currentStored).toBeDefined()
    expect(postStored).toBeDefined()

    const parsedCurrent = JSON.parse(currentStored.remark)
    const parsedPost = JSON.parse(postStored.remark)

    expect(parsedCurrent).toHaveLength(1)
    expect(parsedCurrent[0].customerName).toBe('A')
    expect(parsedPost).toHaveLength(1)
    expect(parsedPost[0].customerName).toBe('B')
  })

  it('fillFromSampledVouchers classifies and merges correctly', () => {
    const { currentRows, postRows, fillFromSampledVouchers } = useD2VoucherCheckEnhanced(options)

    const vouchers: SampledVoucher[] = [
      { voucherNo: 'PZ-001', voucherDate: '2025-06-15', debitAmount: 1000 },
      { voucherNo: 'PZ-002', voucherDate: '2025-12-31', debitAmount: 2000 },
      { voucherNo: 'PZ-003', voucherDate: '2026-01-05', creditAmount: 3000 },
    ]

    fillFromSampledVouchers(vouchers, 'replace')

    // PZ-001 and PZ-002 are <= bsDate → current
    expect(currentRows.value).toHaveLength(2)
    expect(currentRows.value[0].voucherNo).toBe('PZ-001')
    expect(currentRows.value[1].voucherNo).toBe('PZ-002')

    // PZ-003 is > bsDate → post
    expect(postRows.value).toHaveLength(1)
    expect(postRows.value[0].voucherNo).toBe('PZ-003')
  })
})
