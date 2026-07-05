/**
 * useG12HedgeDetail — G12-2 套期关系明细
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { G12_HEDGE_TYPES, G12_EFFECTIVENESS_OPTIONS } from './g12Constants'
import { parseNum, calcHedgeIneffectiveness } from './useG12FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface G12HedgeDetailRow {
  rowId: string
  seq: number
  hedgeRelationId: string
  hedgeType: string
  hedgedItem: string
  hedgingInstrument: string
  designationDate: string
  maturityDate: string
  hedgedRisk: string
  hedgeRatio: number
  instrumentFVChange: number
  itemFVChange: number
  ineffectiveness: number
  profitLossAmount: number
  effectivenessConclusion: string
  indexRef: string
  remark: string
}

const ITEM_ID = 'G12-hedge-detail-rows'

function genId() { return `g12h-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}` }

function enrich(raw: Partial<G12HedgeDetailRow> & { rowId: string }): G12HedgeDetailRow {
  const instrumentFVChange = parseNum(raw.instrumentFVChange)
  const itemFVChange = parseNum(raw.itemFVChange)
  return {
    rowId: raw.rowId,
    seq: parseNum(raw.seq) || 0,
    hedgeRelationId: raw.hedgeRelationId ?? '',
    hedgeType: raw.hedgeType ?? 'fair_value',
    hedgedItem: raw.hedgedItem ?? '',
    hedgingInstrument: raw.hedgingInstrument ?? '',
    designationDate: raw.designationDate ?? '',
    maturityDate: raw.maturityDate ?? '',
    hedgedRisk: raw.hedgedRisk ?? '',
    hedgeRatio: parseNum(raw.hedgeRatio),
    instrumentFVChange,
    itemFVChange,
    ineffectiveness: calcHedgeIneffectiveness(instrumentFVChange, itemFVChange),
    profitLossAmount: parseNum(raw.profitLossAmount),
    effectivenessConclusion: raw.effectivenessConclusion ?? 'pending',
    indexRef: raw.indexRef ?? '',
    remark: raw.remark ?? '',
  }
}

function parse(json: string | null | undefined): G12HedgeDetailRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    return Array.isArray(arr) ? arr.map((r: any, i: number) => enrich({ ...r, rowId: r.rowId || genId(), seq: r.seq ?? i + 1 })) : []
  } catch { return [] }
}

export function useG12HedgeDetail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G12HedgeDetailRow[]>([])

  watch(() => opts.allResponses.value.get(ITEM_ID)?.remark, (j) => { rows.value = parse(j) }, { immediate: true })

  function persist() {
    opts.debouncedSave(ITEM_ID, { remark: JSON.stringify(rows.value.map((r) => ({
      rowId: r.rowId, seq: r.seq, hedgeRelationId: r.hedgeRelationId, hedgeType: r.hedgeType,
      hedgedItem: r.hedgedItem, hedgingInstrument: r.hedgingInstrument, designationDate: r.designationDate,
      maturityDate: r.maturityDate, hedgedRisk: r.hedgedRisk, hedgeRatio: r.hedgeRatio,
      instrumentFVChange: r.instrumentFVChange, itemFVChange: r.itemFVChange,
      profitLossAmount: r.profitLossAmount, effectivenessConclusion: r.effectivenessConclusion,
      indexRef: r.indexRef, remark: r.remark,
    }))) })
    window.dispatchEvent(new CustomEvent('g12:hedge-detail-updated'))
  }

  function updateCell(rowId: string, field: keyof G12HedgeDetailRow, value: unknown) {
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
      const { value } = await ElMessageBox.prompt('请输入套期关系编号', '新增套期关系', {
        inputPattern: /\S+/, inputErrorMessage: '编号不能为空',
      })
      if (rows.value.some((r) => r.hedgeRelationId === value)) {
        ElMessage.error('套期关系编号已存在')
        return
      }
      rows.value = [...rows.value, enrich({ rowId: genId(), seq: rows.value.length + 1, hedgeRelationId: value ?? '' })]
      persist()
    } catch { /* cancel */ }
  }

  function removeRow(rowId: string) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId).map((r, i) => enrich({ ...r, seq: i + 1 }))
    persist()
  }

  const totals = computed(() => ({
    instrumentFVChange: rows.value.reduce((s, r) => s + r.instrumentFVChange, 0),
    itemFVChange: rows.value.reduce((s, r) => s + r.itemFVChange, 0),
    ineffectiveness: rows.value.reduce((s, r) => s + r.ineffectiveness, 0),
    profitLossAmount: rows.value.reduce((s, r) => s + r.profitLossAmount, 0),
  }))

  function aggregateForAdjudication() {
    return {
      instrument_fv: { unadjusted: totals.value.instrumentFVChange, adjustment: 0, audited: totals.value.instrumentFVChange },
      item_fv: { unadjusted: totals.value.itemFVChange, adjustment: 0, audited: totals.value.itemFVChange },
      ineffectiveness: { unadjusted: totals.value.ineffectiveness, adjustment: 0, audited: totals.value.ineffectiveness },
      net_hedge: { unadjusted: totals.value.profitLossAmount, adjustment: 0, audited: totals.value.profitLossAmount },
    } as Record<string, { unadjusted: number; adjustment: number; audited: number }>
  }

  return { rows, totals, updateCell, addRow, removeRow, persist, aggregateForAdjudication, G12_HEDGE_TYPES, G12_EFFECTIVENESS_OPTIONS, ITEM_ID }
}
