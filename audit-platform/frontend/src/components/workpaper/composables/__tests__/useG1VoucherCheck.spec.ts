/**
 * useG1VoucherCheck — G1-13 检查表单元测试
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  calcInspectionRatio,
  enrichVoucherRow,
  useG1VoucherCheck,
  G1_VOUCHER_CHECK_COLUMNS,
} from '../useG1VoucherCheck'
import type { ChecklistResponse } from '../useF1FormData'

describe('calcInspectionRatio', () => {
  it('总体为 0 返回 null（避免 DIV/0）', () => {
    expect(calcInspectionRatio(100, 0)).toBeNull()
  })

  it('样本/总体', () => {
    expect(calcInspectionRatio(50, 200)).toBe(0.25)
  })
})

describe('enrichVoucherRow', () => {
  it('六项有否 → 自动异常', () => {
    const r = enrichVoucherRow({
      check1DocsComplete: true,
      check2VoucherMatch: false,
      check3Accounting: true,
      check4Period: true,
      check5FairValue: true,
      check6Approval: true,
    }, 1)
    expect(r.isAbnormal).toBe(true)
    expect(r.amount).toBe(0)
  })

  it('旧文本核对列迁移', () => {
    const r = enrichVoucherRow({
      amount: 1000,
      contractCheck: '相符',
      bookkeepingCheck: '不符',
      approvalCheck: '是',
      quoteCheck: '相符',
    }, 1)
    expect(r.check1DocsComplete).toBe(true)
    expect(r.check3Accounting).toBe(false)
    expect(r.check6Approval).toBe(true)
    expect(r.check5FairValue).toBe(true)
    expect(r.amount).toBe(1000)
  })

  it('借贷金额取较大值为 amount', () => {
    const r = enrichVoucherRow({ debitAmount: 100, creditAmount: 500 }, 1)
    expect(r.amount).toBe(500)
  })
})

describe('G1_VOUCHER_CHECK_COLUMNS', () => {
  it('含核对与结论列（集成兼容）', () => {
    const props = G1_VOUCHER_CHECK_COLUMNS.map((c) => c.prop)
    expect(props).toContain('voucherDate')
    expect(props).toContain('contractCheck')
    expect(props).toContain('auditConclusion')
  })
})

describe('useG1VoucherCheck', () => {
  it('默认含本期与期后至少各一行', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const { currentRows, subsequentRows } = useG1VoucherCheck({
      allResponses: map,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    expect(currentRows.value.length).toBeGreaterThanOrEqual(1)
    expect(subsequentRows.value.length).toBeGreaterThanOrEqual(1)
  })

  it('mapVoucherToRow 取较大借贷方', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const { mapVoucherToRow } = useG1VoucherCheck({
      allResponses: map,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    const row = mapVoucherToRow({
      debitAmount: '0',
      creditAmount: '500000',
      summary: '购入股票',
      voucherDate: '2025-06-15',
      voucherNo: 'PZ-1',
      counterpartAccount: '1002',
    } as any, 1)
    expect(row.amount).toBe(500000)
    expect(row.sampleSource).toBe('抽凭引擎')
    expect(row.period).toBe('current')
  })

  it('检查比例依赖抽样计划总体', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const { updateSamplingPlan, inspectionRatio, addRow, updateRow, rows, activePeriod } = useG1VoucherCheck({
      allResponses: map,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    activePeriod.value = 'current'
    const id = rows.value.find((r) => r.period === 'current')!.id
    updateRow(id, { debitAmount: 100, creditAmount: 0 })
    expect(inspectionRatio.value).toBeNull()
    updateSamplingPlan({ populationDebit: 1000, populationCredit: 0 })
    expect(inspectionRatio.value).toBeCloseTo(0.1)
  })

  it('抽凭 replace 仅替换当前区段', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const save = vi.fn()
    const { applySamplingResults, currentRows, subsequentRows, activePeriod } = useG1VoucherCheck({
      allResponses: map,
      debouncedSave: save,
      isReadonly: ref(false),
    })
    activePeriod.value = 'current'
    applySamplingResults(
      [{ voucherNo: 'A1', debitAmount: '10', creditAmount: '0', summary: 't' } as any],
      'replace',
    )
    expect(currentRows.value.some((r) => r.voucherNo === 'A1')).toBe(true)
    expect(subsequentRows.value.length).toBeGreaterThanOrEqual(1)
  })
})
