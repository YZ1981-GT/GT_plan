/**
 * useDiffSecuritiesData — G0-3(证券) 差异核对数据 composable
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { DiffSecuritiesMetrics, DiffSecuritiesPayload, SecuritiesDiffRow } from '../diffSecuritiesTypes'
import {
  calcFairValueDiff,
  calcMarketValueDiff,
  calcQuantityDiff,
  hasDifference,
} from '../../composables/useG0FormulaEngine'

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function toNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function recalcRow(row: SecuritiesDiffRow): SecuritiesDiffRow {
  const confirmedQty = toNum(row.confirmed_qty)
  const bookedQty = toNum(row.booked_qty)
  const confirmedFv = toNum(row.confirmed_unit_fv)
  const bookedFv = toNum(row.booked_unit_fv)
  const confirmedMv = toNum(row.confirmed_market_value)
  const bookedMv = toNum(row.booked_market_value)
  // 🔴 差异 = 账面 − 回函（源模板表头 `③=①−②`，①账面/②回函）。
  //    形参顺序 `(booked, reply)`，勿颠倒 —— 源 M 列公式写反已登记为源缺陷
  //    `g0SourceDefects#securities-mv-diff-direction`（Task 20 / Property 27）。
  return {
    ...row,
    qty_diff: calcQuantityDiff(bookedQty, confirmedQty),
    fv_diff: calcFairValueDiff(bookedFv, confirmedFv),
    market_value_diff: calcMarketValueDiff(bookedMv, confirmedMv),
  }
}

/**
 * migrateAdjust — 旧数据「是否需要调账」判断列迁移（Property 2）
 *
 * 源模板 G0-3·P「是否需要调账」是判断列（是/否/待定）。既有实现把它做成自由文本
 * `adjustment_note`。迁移规则：`adjustment_note` 非空且 `need_adjust` 未设时，
 * 映射 need_adjust='待定' 并**保留原文**（不丢，Requirement 1.3）。
 * 已有 need_adjust 的行不动（幂等，二次读回不变）。
 */
export function migrateAdjust(row: SecuritiesDiffRow): SecuritiesDiffRow {
  if (row.need_adjust) return row
  const note = (row.adjustment_note ?? '').trim()
  if (!note) return row
  return { ...row, need_adjust: '待定' }
}

export interface UseDiffSecuritiesDataProps {
  htmlData: () => any
  readonly: boolean
}

export interface UseDiffSecuritiesDataReturn {
  rows: Ref<SecuritiesDiffRow[]>
  conclusion: Ref<string>
  auditNote: Ref<string>
  isDirty: Ref<boolean>
  metrics: ComputedRef<DiffSecuritiesMetrics>
  addRow: () => SecuritiesDiffRow
  deleteRow: (rowId: string) => void
  updateRow: (rowId: string, field: string, value: unknown) => void
  rowHasDiff: (row: SecuritiesDiffRow) => boolean
  buildPayload: () => DiffSecuritiesPayload
}

export function useDiffSecuritiesData(props: UseDiffSecuritiesDataProps): UseDiffSecuritiesDataReturn {
  const rows = ref<SecuritiesDiffRow[]>([])
  const conclusion = ref('')
  const auditNote = ref('')
  const isDirty = ref(false)

  function initFromHtmlData(data: any) {
    if (!data || data._format !== 'diff-securities-v1') {
      rows.value = []
      conclusion.value = ''
      auditNote.value = ''
      return
    }
    rows.value = Array.isArray(data.rows)
      ? data.rows.map((r: SecuritiesDiffRow) => recalcRow(migrateAdjust(ensureRowId(r))))
      : []
    conclusion.value = data.conclusion || ''
    auditNote.value = data.audit_note || ''
    isDirty.value = false
  }

  function ensureRowId(row: SecuritiesDiffRow): SecuritiesDiffRow {
    return row._row_id ? row : { ...row, _row_id: generateId() }
  }

  initFromHtmlData(props.htmlData())
  watch(() => props.htmlData(), (d) => initFromHtmlData(d), { deep: true })

  function addRow(): SecuritiesDiffRow {
    const maxSeq = rows.value.reduce((max, r) => Math.max(max, r.seq ?? 0), 0)
    const newRow = recalcRow({ _row_id: generateId(), seq: maxSeq + 1 })
    rows.value.push(newRow)
    isDirty.value = true
    return newRow
  }

  function deleteRow(rowId: string) {
    rows.value = rows.value.filter((r) => r._row_id !== rowId)
    isDirty.value = true
  }

  function updateRow(rowId: string, field: string, value: unknown) {
    const idx = rows.value.findIndex((r) => r._row_id === rowId)
    if (idx < 0) return
    const updated = recalcRow({ ...rows.value[idx], [field]: value })
    rows.value[idx] = updated
    isDirty.value = true
  }

  function rowHasDiff(row: SecuritiesDiffRow): boolean {
    return hasDifference(toNum(row.qty_diff), toNum(row.fv_diff))
      || Math.abs(toNum(row.market_value_diff)) > 0.01
  }

  const metrics = computed<DiffSecuritiesMetrics>(() => {
    let diffCount = 0
    let maxAbs = 0
    for (const row of rows.value) {
      if (rowHasDiff(row)) diffCount++
      const abs = Math.max(
        Math.abs(toNum(row.qty_diff)),
        Math.abs(toNum(row.fv_diff)),
        Math.abs(toNum(row.market_value_diff)),
      )
      if (abs > maxAbs) maxAbs = abs
    }
    const total = rows.value.length
    return {
      total_count: total,
      diff_count: diffCount,
      no_diff_count: total - diffCount,
      max_abs_diff: maxAbs,
    }
  })

  function buildPayload(): DiffSecuritiesPayload {
    return {
      _format: 'diff-securities-v1',
      rows: rows.value,
      conclusion: conclusion.value,
      audit_note: auditNote.value,
    }
  }

  return {
    rows,
    conclusion,
    auditNote,
    isDirty,
    metrics,
    addRow,
    deleteRow,
    updateRow,
    rowHasDiff,
    buildPayload,
  }
}
