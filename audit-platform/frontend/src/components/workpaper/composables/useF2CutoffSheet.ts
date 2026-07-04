/**
 * useF2CutoffSheet — F2-29~F2-32 截止测试通用逻辑
 */
import { ref, computed, watch, type Ref } from 'vue'
import { calcSubtotal, isCutoffCorrect } from './useF2InvMaiFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF2FormData'
import type { F2CutoffSheetConfig } from '../f2/inspection/f2CutoffSheetConfigs'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'

export interface F2CutoffRow {
  id: string
  seq: number
  party: string
  docNo: string
  docDate: string
  itemName: string
  quantity: number
  amount: number
  voucherNo: string
  bookDate: string
  isCrossPeriod: boolean
  correctPeriod: string
  bookedPeriod: string
  isCorrect: boolean
  /** 用户手动覆盖标记：null=使用公式自动判定，boolean=手动覆盖值 */
  isCorrectOverride: boolean | null
  /** 公式自动判定结果（只读） */
  autoCorrect: boolean
  suggestion: string
  remark: string
  source?: string
}

function dataKey(sheetCode: string): string {
  return `${sheetCode}-rows`
}

function conclusionKey(sheetCode: string): string {
  return `${sheetCode}-conclusion`
}

function emptyRow(id: string, seq: number): F2CutoffRow {
  return {
    id, seq, party: '', docNo: '', docDate: '', itemName: '', quantity: 0, amount: 0,
    voucherNo: '', bookDate: '', isCrossPeriod: false, correctPeriod: '', bookedPeriod: '',
    isCorrect: true, isCorrectOverride: null, autoCorrect: true, suggestion: '', remark: '',
  }
}

function loadRows(map: Map<string, ChecklistResponse>, sheetCode: string): F2CutoffRow[] {
  const raw = readRowJson(map.get(dataKey(sheetCode)))
  if (!raw) return [emptyRow('1', 1)]
  try {
    const parsed = JSON.parse(raw) as Partial<F2CutoffRow>[]
    if (!parsed.length) return [emptyRow('1', 1)]
    // Backfill new fields for existing data
    return parsed.map((r) => ({
      ...emptyRow(r.id || genRowId(), r.seq || 1),
      ...r,
      isCorrectOverride: r.isCorrectOverride ?? null,
      autoCorrect: r.autoCorrect ?? (r.isCorrect ?? true),
    })) as F2CutoffRow[]
  } catch {
    return [emptyRow('1', 1)]
  }
}

function genRowId(): string {
  return `f2ct-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function mapVoucherToRow(v: ExtractedVoucher, seq: number): F2CutoffRow {
  const debit = v.debitAmount ? parseFloat(v.debitAmount) : 0
  const credit = v.creditAmount ? parseFloat(v.creditAmount) : 0
  const amount = debit > 0 ? debit : credit
  const isCross = v.cutoffStatus === '可能跨期'
  return {
    id: genRowId(),
    seq,
    party: v.accountName || v.counterpartAccount || '',
    docNo: '',
    docDate: v.voucherDate || '',
    itemName: v.summary || '',
    quantity: 0,
    amount,
    voucherNo: v.voucherNo || '',
    bookDate: v.voucherDate || '',
    isCrossPeriod: isCross,
    correctPeriod: '',
    bookedPeriod: '',
    isCorrect: !isCross,
    isCorrectOverride: null,
    autoCorrect: !isCross,
    suggestion: isCross ? '可能跨期，需核查' : '',
    remark: v.remark || '',
    source: '自动提取',
  }
}

export function useF2CutoffSheet(opts: {
  config: Ref<F2CutoffSheetConfig>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
  /** 期末日期（bs_date），用于公式自动判定截止正确性 */
  periodEnd?: Ref<string>
}) {
  const sheetCode = computed(() => opts.config.value.sheetCode)
  const periodEndDate = computed(() => opts.periodEnd?.value || '')

  /** 公式自动判定+覆盖逻辑：enrichRow */
  function enrichCutoffRow(r: F2CutoffRow): F2CutoffRow {
    // 如果有单据日期和记账日期且有期末日期→公式自动判定
    const autoResult = (r.docDate && r.bookDate && periodEndDate.value)
      ? isCutoffCorrect(r.docDate, r.bookDate, periodEndDate.value)
      : true // 无日期时默认为正确（待填写）
    const finalCorrect = r.isCorrectOverride !== null ? r.isCorrectOverride : autoResult
    return { ...r, autoCorrect: autoResult, isCorrect: finalCorrect }
  }

  const rows = ref<F2CutoffRow[]>(
    loadRows(opts.allResponses.value, sheetCode.value).map(enrichCutoffRow),
  )
  const cutoffConclusion = ref('')

  watch(
    () => opts.allResponses.value.get(conclusionKey(sheetCode.value))?.remark,
    (v) => { cutoffConclusion.value = v || '' },
    { immediate: true },
  )

  const cutoffSummary = computed(() => {
    const incorrect = rows.value.filter((r) => !r.isCorrect)
    return {
      total: rows.value.length,
      correctCount: rows.value.length - incorrect.length,
      errorCount: incorrect.length,
      errorAmount: calcSubtotal(incorrect.map((r) => r.amount)),
    }
  })

  function persistRows() {
    if (opts.isReadonly.value) return
    const key = dataKey(sheetCode.value)
    const item: ChecklistResponse = {
      item_id: key,
      conclusion: null,
      remark: JSON.stringify(rows.value),
    }
    opts.allResponses.value.set(key, item)
    window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
  }

  function persistConclusion() {
    if (opts.isReadonly.value) return
    const key = conclusionKey(sheetCode.value)
    const item: ChecklistResponse = {
      item_id: key,
      conclusion: null,
      remark: cutoffConclusion.value,
    }
    opts.allResponses.value.set(key, item)
    window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
  }

  function updateRow(id: string, patch: Partial<F2CutoffRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.id !== id) return r
      const merged = { ...r, ...patch }
      // Re-run auto-determination when date fields change
      if ('docDate' in patch || 'bookDate' in patch || 'isCorrectOverride' in patch) {
        return enrichCutoffRow(merged)
      }
      return merged
    })
    persistRows()
  }

  function addRow() {
    if (opts.isReadonly.value) return
    rows.value = [...rows.value, emptyRow(genRowId(), rows.value.length + 1)]
    persistRows()
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persistRows()
  }

  function fillFromExtracted(extracted: ExtractedVoucher[], fillMode: FillMode) {
    if (opts.isReadonly.value) return
    const mapped = extracted.map((v, i) => mapVoucherToRow(v, i + 1))

    if (fillMode === 'replace') {
      rows.value = mapped.map((r, i) => ({ ...r, seq: i + 1 }))
    } else if (fillMode === 'merge') {
      const existingNos = new Set(rows.value.map((r) => r.voucherNo).filter(Boolean))
      const newRows = mapped.filter((r) => !r.voucherNo || !existingNos.has(r.voucherNo))
      const startSeq = rows.value.length
      newRows.forEach((r, i) => { r.seq = startSeq + i + 1 })
      rows.value = [...rows.value, ...newRows]
    } else {
      const startSeq = rows.value.length
      mapped.forEach((r, i) => { r.seq = startSeq + i + 1 })
      rows.value = [...rows.value, ...mapped]
    }
    persistRows()
  }

  watch(cutoffConclusion, () => { persistConclusion() })

  return { rows, cutoffSummary, cutoffConclusion, updateRow, addRow, removeRow, fillFromExtracted }
}
