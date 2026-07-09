/**
 * useH5Detail — H5-2 明细表 composable
 *
 * 54列3区段, 动态行, 期末计算
 * 行内公式：原值期末=期初+增加-减少, 折耗期末=期初+计提-转回, 净值=原值-折耗
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.4
 * Requirements: 3.1-3.3
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH5FormData'
import {
  calcAssetEndBalance,
  calcContraEndBalance,
  calcNetValue,
  calcSubtotal,
} from './useH5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H5DetailRow {
  rowId: string
  // 区段1: 基础信息
  category: string
  name: string
  oilField: string
  block: string
  // 区段2: 原值变动
  originalCostBegin: number
  originalCostIncrease: number
  originalCostDecrease: number
  originalCostEnd: number       // 公式
  increaseReason: string
  decreaseReason: string
  // 区段3: 折耗
  accDepletionBegin: number
  accDepletionProvision: number
  accDepletionReversal: number
  accDepletionEnd: number       // 公式
  netValue: number              // 公式
  remark: string
}

export interface SegmentConfig {
  key: string
  label: string
  fields: (keyof H5DetailRow)[]
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H5-2'

export const SEGMENT_CONFIGS: SegmentConfig[] = [
  {
    key: 'basic', label: '基础信息',
    fields: ['category', 'name', 'oilField', 'block'],
  },
  {
    key: 'cost', label: '原值变动',
    fields: ['originalCostBegin', 'originalCostIncrease', 'originalCostDecrease', 'originalCostEnd', 'increaseReason', 'decreaseReason'],
  },
  {
    key: 'depletion', label: '折耗',
    fields: ['accDepletionBegin', 'accDepletionProvision', 'accDepletionReversal', 'accDepletionEnd', 'netValue'],
  },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5Detail(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  crossSheetCostAudited?: Ref<number>
  crossSheetDepletionAudited?: Ref<number>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = opts

  const rows = ref<H5DetailRow[]>([])
  const activeSegment = ref<string>('basic')
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    const raw = item?.remark
    if (!raw) { rows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      rows.value = Array.isArray(parsed) ? parsed.map(_normalizeRow) : []
    } catch { rows.value = [] }
    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any): H5DetailRow {
    const r: H5DetailRow = {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      category: raw.category ?? '',
      name: raw.name ?? '',
      oilField: raw.oilField ?? '',
      block: raw.block ?? '',
      originalCostBegin: Number(raw.originalCostBegin) || 0,
      originalCostIncrease: Number(raw.originalCostIncrease) || 0,
      originalCostDecrease: Number(raw.originalCostDecrease) || 0,
      originalCostEnd: 0,
      increaseReason: raw.increaseReason ?? '',
      decreaseReason: raw.decreaseReason ?? '',
      accDepletionBegin: Number(raw.accDepletionBegin) || 0,
      accDepletionProvision: Number(raw.accDepletionProvision) || 0,
      accDepletionReversal: Number(raw.accDepletionReversal) || 0,
      accDepletionEnd: 0,
      netValue: 0,
      remark: raw.remark ?? '',
    }
    _recalcRow(r)
    return r
  }

  function _recalcRow(row: H5DetailRow): void {
    row.originalCostEnd = calcAssetEndBalance(row.originalCostBegin, row.originalCostIncrease, row.originalCostDecrease)
    row.accDepletionEnd = calcContraEndBalance(row.accDepletionBegin, row.accDepletionReversal, row.accDepletionProvision)
    row.netValue = calcNetValue(row.originalCostEnd, row.accDepletionEnd, 0)
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const subtotalRow = computed(() => ({
    rowId: 'subtotal', category: '合计', name: '',
    originalCostBegin: calcSubtotal(rows.value.map((r) => r.originalCostBegin)),
    originalCostIncrease: calcSubtotal(rows.value.map((r) => r.originalCostIncrease)),
    originalCostDecrease: calcSubtotal(rows.value.map((r) => r.originalCostDecrease)),
    originalCostEnd: calcSubtotal(rows.value.map((r) => r.originalCostEnd)),
    accDepletionBegin: calcSubtotal(rows.value.map((r) => r.accDepletionBegin)),
    accDepletionProvision: calcSubtotal(rows.value.map((r) => r.accDepletionProvision)),
    accDepletionReversal: calcSubtotal(rows.value.map((r) => r.accDepletionReversal)),
    accDepletionEnd: calcSubtotal(rows.value.map((r) => r.accDepletionEnd)),
    netValue: calcSubtotal(rows.value.map((r) => r.netValue)),
  }))

  const crossValidation = computed(() => {
    const costFromAdj = opts.crossSheetCostAudited?.value ?? 0
    const deplFromAdj = opts.crossSheetDepletionAudited?.value ?? 0
    return {
      costDiff: (subtotalRow.value.originalCostEnd ?? 0) - costFromAdj,
      deplDiff: (subtotalRow.value.accDepletionEnd ?? 0) - deplFromAdj,
      hasCostWarning: Math.abs((subtotalRow.value.originalCostEnd ?? 0) - costFromAdj) > 0.01,
      hasDepWarning: Math.abs((subtotalRow.value.accDepletionEnd ?? 0) - deplFromAdj) > 0.01,
    }
  })

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addRow(name: string, category?: string): void {
    const newRow: H5DetailRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      category: category ?? '', name, oilField: '', block: '',
      originalCostBegin: 0, originalCostIncrease: 0, originalCostDecrease: 0, originalCostEnd: 0,
      increaseReason: '', decreaseReason: '',
      accDepletionBegin: 0, accDepletionProvision: 0, accDepletionReversal: 0, accDepletionEnd: 0,
      netValue: 0, remark: '',
    }
    rows.value.push(newRow)
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) { rows.value.splice(idx, 1); _persist() }
  }

  function updateCell(rowId: string, field: keyof H5DetailRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  function _persist(): void { onSave?.(`${ITEM_PREFIX}-rows`, rows.value) }
  function saveNote(note: string): void { auditNote.value = note; onSave?.(`${ITEM_PREFIX}-audit-note`, note) }
  function saveConclusion(conclusion: string): void { auditConclusion.value = conclusion; onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion) }

  watch(allResponses, () => _loadRows(), { immediate: true })

  return {
    rows, activeSegment, auditNote, auditConclusion,
    subtotalRow, crossValidation,
    addRow, removeRow, updateCell, saveNote, saveConclusion,
    SEGMENT_CONFIGS,
  }
}
