/**
 * useG12VoucherCheck — G12-6 凭证检查（3区段Tab）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum, calcSubtotal, isDebitCreditBalanced, isVoucherAbnormal } from './useG12FormulaEngine'
import { mapCutoffToG12Voucher, mergeByFillMode } from './gCycleCutoffFill'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import type { ChecklistResponse } from './useF1FormData'

export interface G12VoucherRow {
  rowId: string
  seq: number
  voucherDate: string
  voucherNo: string
  businessContent: string
  hedgeRelationId: string
  counterAccount: string
  debitAmount: number
  creditAmount: number
  attachment: string
  supportingDocDesc: string
  check1OriginalComplete: boolean
  check2Authorization: boolean
  check3Accounting: boolean
  check4HedgeDesignation: boolean
  check5FVValuation: boolean
  indexNo: string
  isAbnormal: boolean
  abnormalDesc: string
  riskLevel: string
  remark: string
}

const ITEM_ID = 'G12-voucher-rows'
function genId() { return `g12v-${Date.now().toString(36)}` }

function enrich(raw: Partial<G12VoucherRow> & { rowId: string }): G12VoucherRow {
  const checks = [
    raw.check1OriginalComplete !== false,
    raw.check2Authorization !== false,
    raw.check3Accounting !== false,
    raw.check4HedgeDesignation !== false,
    raw.check5FVValuation !== false,
  ]
  return {
    rowId: raw.rowId,
    seq: parseNum(raw.seq) || 0,
    voucherDate: raw.voucherDate ?? '',
    voucherNo: raw.voucherNo ?? '',
    businessContent: raw.businessContent ?? '',
    hedgeRelationId: raw.hedgeRelationId ?? '',
    counterAccount: raw.counterAccount ?? '',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    attachment: raw.attachment ?? '',
    supportingDocDesc: raw.supportingDocDesc ?? '',
    check1OriginalComplete: raw.check1OriginalComplete !== false,
    check2Authorization: raw.check2Authorization !== false,
    check3Accounting: raw.check3Accounting !== false,
    check4HedgeDesignation: raw.check4HedgeDesignation !== false,
    check5FVValuation: raw.check5FVValuation !== false,
    indexNo: raw.indexNo ?? '',
    isAbnormal: raw.isAbnormal ?? isVoucherAbnormal(checks),
    abnormalDesc: raw.abnormalDesc ?? '',
    riskLevel: raw.riskLevel ?? '',
    remark: raw.remark ?? '',
  }
}

export function useG12VoucherCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G12VoucherRow[]>([])
  const activeTab = ref<'basic' | 'check' | 'conclusion'>('basic')
  const selectedRowId = ref('')

  watch(() => opts.allResponses.value.get(ITEM_ID)?.remark, (j) => {
    try { rows.value = j ? JSON.parse(j).map((r: any, i: number) => enrich({ ...r, rowId: r.rowId || genId(), seq: r.seq ?? i + 1 })) : [] } catch { rows.value = [] }
  }, { immediate: true })

  const useVirtualScroll = computed(() => rows.value.length > 50)
  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const isBalanced = computed(() => isDebitCreditBalanced(rows.value.map((r) => r.debitAmount), rows.value.map((r) => r.creditAmount)))
  const abnormalCount = computed(() => rows.value.filter((r) => r.isAbnormal).length)

  function persist() {
    opts.debouncedSave(ITEM_ID, { remark: JSON.stringify(rows.value.map((r) => ({
      rowId: r.rowId, seq: r.seq, voucherDate: r.voucherDate, voucherNo: r.voucherNo,
      businessContent: r.businessContent, hedgeRelationId: r.hedgeRelationId, counterAccount: r.counterAccount,
      debitAmount: r.debitAmount, creditAmount: r.creditAmount, attachment: r.attachment,
      supportingDocDesc: r.supportingDocDesc, check1OriginalComplete: r.check1OriginalComplete,
      check2Authorization: r.check2Authorization, check3Accounting: r.check3Accounting,
      check4HedgeDesignation: r.check4HedgeDesignation, check5FVValuation: r.check5FVValuation,
      indexNo: r.indexNo, isAbnormal: r.isAbnormal, abnormalDesc: r.abnormalDesc, riskLevel: r.riskLevel, remark: r.remark,
    }))) })
  }

  function updateCell(rowId: string, field: keyof G12VoucherRow, value: unknown) {
    if (opts.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const next = [...rows.value]
    next[idx] = enrich({ ...next[idx], [field]: value })
    rows.value = next
    persist()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('凭证编号', '新增凭证检查行', { inputPattern: /\S+/ })
      const row = enrich({ rowId: genId(), seq: rows.value.length + 1, voucherNo: value ?? '' })
      rows.value = [...rows.value, row]
      selectedRowId.value = row.rowId
      persist()
    } catch { /* cancel */ }
  }

  function removeRow(rowId: string) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId).map((r, i) => enrich({ ...r, seq: i + 1 }))
    persist()
  }

  function applyCutoffResults(samples: ExtractedVoucher[], fillMode: FillMode) {
    if (opts.isReadonly.value || !samples.length) return
    const mapped = samples.map((v, i) => mapCutoffToG12Voucher(v, i + 1))
    const merged = mergeByFillMode(rows.value, mapped, fillMode, (r) => r.voucherNo)
    rows.value = merged.map((r, i) => enrich({ ...r, seq: i + 1 }))
    persist()
  }

  return { rows, activeTab, selectedRowId, useVirtualScroll, debitTotal, creditTotal, isBalanced, abnormalCount, updateCell, addRow, removeRow, persist, applyCutoffResults, ITEM_ID }
}
