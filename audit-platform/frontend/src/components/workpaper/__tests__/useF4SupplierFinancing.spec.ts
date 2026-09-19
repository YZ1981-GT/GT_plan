import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import {
  buildF4FinancingDisplayRows,
  calcF4FinancingDifference,
  computeF4FinancingRow,
  extractF4FinancingSupplierCandidates,
  migrateF4FinancingRows,
  useF4SupplierFinancing,
} from '../composables/useF4SupplierFinancing'
import type { ChecklistResponse } from '../composables/useF4FormData'

function options(entries: Array<[string, unknown]> = []) {
  const allResponses = ref(new Map<string, ChecklistResponse>(
    entries.map(([key, value]) => [key, {
      item_id: key,
      conclusion: null,
      remark: typeof value === 'string' ? value : JSON.stringify(value),
    }]),
  ))
  return {
    wpId: ref('wp1'),
    projectId: ref('p1'),
    allResponses,
    isReadonly: ref(false),
  }
}

describe('F4-9 公式与风险', () => {
  it('差异 = 融资金额 − 本期采购金额', () => {
    expect(calcF4FinancingDifference(1000, 800)).toBe(200)
    const row = computeF4FinancingRow({
      rowId: 'r1', seq: 1, attSlot: 1, groupId: 'g1',
      supplierName: '甲', promisedPayer: '本公司', financingNo: 'RZ-1',
      fundProvider: '银行A', status: '已放款',
      financingAmount: 1000, supplierSignDate: '', disbursementDate: '',
      transferDate: '', promisedRepayDate: '', actualRepayDate: '',
      purchaseAmount: 600, loanBalance: 1000, remark: '', sourceRowId: '',
    })
    expect(row.difference).toBe(400)
    expect(row.riskFlags).toContain('融资金额大于采购金额')
    expect(row.highlightLevel).toBe('danger')
  })
})

describe('F4-9 动态分组显示', () => {
  it('同供应商多行后插入小计，末行合计', () => {
    const g1 = 'grp-a'
    const g2 = 'grp-b'
    const rows = [
      computeF4FinancingRow({
        rowId: '1', seq: 1, attSlot: 1, groupId: g1, supplierName: '供应商1',
        promisedPayer: '', financingNo: 'A1', fundProvider: '银', status: '',
        financingAmount: 100, supplierSignDate: '', disbursementDate: '',
        transferDate: '', promisedRepayDate: '', actualRepayDate: '',
        purchaseAmount: 80, loanBalance: 100, remark: '', sourceRowId: '',
      }),
      computeF4FinancingRow({
        rowId: '2', seq: 2, attSlot: 2, groupId: g1, supplierName: '供应商1',
        promisedPayer: '', financingNo: 'A2', fundProvider: '银', status: '',
        financingAmount: 50, supplierSignDate: '', disbursementDate: '',
        transferDate: '', promisedRepayDate: '', actualRepayDate: '',
        purchaseAmount: 40, loanBalance: 50, remark: '', sourceRowId: '',
      }),
      computeF4FinancingRow({
        rowId: '3', seq: 3, attSlot: 3, groupId: g2, supplierName: '供应商2',
        promisedPayer: '', financingNo: 'B1', fundProvider: '银', status: '',
        financingAmount: 200, supplierSignDate: '', disbursementDate: '',
        transferDate: '', promisedRepayDate: '', actualRepayDate: '',
        purchaseAmount: 200, loanBalance: 0, remark: '', sourceRowId: '',
      }),
    ]
    const display = buildF4FinancingDisplayRows(rows)
    expect(display.map((d) => d.kind)).toEqual([
      'detail', 'detail', 'subtotal', 'detail', 'subtotal', 'total',
    ])
    const sub1 = display.find((d) => d.kind === 'subtotal' && d.groupId === g1)!
    expect(sub1.financingAmount).toBe(150)
    expect(sub1.difference).toBe(30)
    const total = display.find((d) => d.kind === 'total')!
    expect(total.financingAmount).toBe(350)
    expect(total.purchaseAmount).toBe(320)
  })
})

describe('F4-9 旧三区迁移与F4-2引用', () => {
  it('旧保理行迁移到源表字段并保留说明', () => {
    const row = migrateF4FinancingRows(JSON.stringify([{
      id: 'old1',
      vendor: '乙公司',
      factor: '保理公司X',
      amount: 900,
      startDate: '2025-01-01',
      dueDate: '2025-06-01',
      hasRecourse: '是',
      derecognized: '否',
      auditEvaluation: '需关注终止确认',
    }]))[0]
    expect(row).toMatchObject({
      rowId: 'old1',
      supplierName: '乙公司',
      fundProvider: '保理公司X',
      financingAmount: 900,
      supplierSignDate: '2025-01-01',
      promisedRepayDate: '2025-06-01',
    })
    expect(row.remark).toContain('有追索权')
    expect(row.remark).toContain('需关注终止确认')
  })

  it('从F4-2按债权人归集本期贷方作为采购候选', () => {
    const candidates = extractF4FinancingSupplierCandidates(JSON.stringify([
      { rowId: 'a', creditor: '甲公司', currentCredit: 100 },
      { rowId: 'b', creditor: '甲公司', currentCredit: 50 },
      { rowId: 'c', creditor: '乙公司', currentCredit: 200 },
    ]))
    expect(candidates).toHaveLength(2)
    expect(candidates.find((c) => c.supplierName === '甲公司')?.purchaseAmount).toBe(150)
  })
})

describe('useF4SupplierFinancing — 插行与同步', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('新增供应商分组并可在组内插行，改名联动同组', () => {
    const api = useF4SupplierFinancing(options())
    api.addSupplierGroup('供应商1')
    const groupId = api.rows.value[api.rows.value.length - 1].groupId
    api.addRowInGroup(groupId)
    expect(api.rows.value.filter((r) => r.groupId === groupId)).toHaveLength(2)
    const firstId = api.rows.value.find((r) => r.groupId === groupId)!.rowId
    api.updateCell(firstId, 'supplierName', '甲供应商')
    expect(api.rows.value.filter((r) => r.groupId === groupId).every((r) => r.supplierName === '甲供应商')).toBe(true)
    vi.advanceTimersByTime(1300)
  })

  it('从F4-2同步未出现的供应商', () => {
    const api = useF4SupplierFinancing(options([
      ['F4-2-rows', [
        { rowId: 'd1', creditor: '新供应商', currentCredit: 500 },
      ]],
      ['F4-9-rows', [{
        rowId: 'r0', groupId: 'g0', supplierName: '已有供应商', financingAmount: 1, purchaseAmount: 1,
      }]],
    ]))
    const added = api.syncFromDetail()
    expect(added).toBe(1)
    expect(api.rows.value.some((r) => r.supplierName === '新供应商' && r.purchaseAmount === 500)).toBe(true)
    vi.advanceTimersByTime(1300)
  })

  it('OCR仅回填空字段', () => {
    const api = useF4SupplierFinancing(options([
      ['F4-9-rows', [{
        rowId: 'r1', groupId: 'g1', supplierName: '甲', financingNo: '旧单号',
        financingAmount: 0, purchaseAmount: 0, loanBalance: 0,
      }]],
    ]))
    api.mergeOcrFields('r1', {
      financingNo: '新单号',
      financingAmount: 800,
      fundProvider: '银行B',
    }, false)
    expect(api.rows.value[0].financingNo).toBe('旧单号')
    expect(api.rows.value[0].financingAmount).toBe(800)
    expect(api.rows.value[0].fundProvider).toBe('银行B')
    vi.advanceTimersByTime(1300)
  })
})
