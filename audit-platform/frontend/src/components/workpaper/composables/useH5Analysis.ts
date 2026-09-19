/**
 * useH5Analysis — H5-6 分析表 composable
 *
 * 变动率计算, OO渲染配置
 * 26行23列9公式, 含结构分析+变动分析
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.4
 * Requirements: 4.3-4.4
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH5FormData'
import { calcChangeRate, calcSubtotal } from './useH5FormulaEngine'
import { calcDepletionRate } from './useH5DepletionEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AnalysisRow {
  rowId: string
  category: string              // 资产分类
  priorCost: number             // 上期原值
  currentCost: number           // 本期原值
  costChangeRate: number        // 原值变动率(%) - 公式
  priorDepletion: number        // 上期累计折耗
  currentDepletion: number      // 本期累计折耗
  depletionChangeRate: number   // 折耗变动率(%) - 公式
  priorNetValue: number         // 上期净值
  currentNetValue: number       // 本期净值
  netValueChangeRate: number    // 净值变动率(%) - 公式
  depletionRate: number         // 折耗率(%) - 公式
  explanation: string           // 变动原因说明
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H5-6'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5Analysis(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = opts

  const rows = ref<AnalysisRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  /** 是否使用OO渲染（复杂分析图表场景） */
  const useOnlyOffice = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _load(): void {
    const raw = allResponses.value.get(`${ITEM_PREFIX}-rows`)?.remark
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        rows.value = Array.isArray(parsed) ? parsed.map(_normalize) : []
      } catch { rows.value = [] }
    } else { rows.value = [] }
    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalize(raw: any): AnalysisRow {
    const r: AnalysisRow = {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      category: raw.category ?? '',
      priorCost: Number(raw.priorCost) || 0,
      currentCost: Number(raw.currentCost) || 0,
      costChangeRate: 0,
      priorDepletion: Number(raw.priorDepletion) || 0,
      currentDepletion: Number(raw.currentDepletion) || 0,
      depletionChangeRate: 0,
      priorNetValue: Number(raw.priorNetValue) || 0,
      currentNetValue: Number(raw.currentNetValue) || 0,
      netValueChangeRate: 0,
      depletionRate: 0,
      explanation: raw.explanation ?? '',
    }
    _recalcRow(r)
    return r
  }

  function _recalcRow(row: AnalysisRow): void {
    row.costChangeRate = calcChangeRate(row.currentCost, row.priorCost)
    row.depletionChangeRate = calcChangeRate(row.currentDepletion, row.priorDepletion)
    row.netValueChangeRate = calcChangeRate(row.currentNetValue, row.priorNetValue)
    row.depletionRate = calcDepletionRate(row.currentDepletion, row.currentCost)
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const totalCurrentCost = computed(() => calcSubtotal(rows.value.map((r) => r.currentCost)))
  const totalCurrentNetValue = computed(() => calcSubtotal(rows.value.map((r) => r.currentNetValue)))
  const overallDepletionRate = computed(() => calcDepletionRate(
    calcSubtotal(rows.value.map((r) => r.currentDepletion)),
    totalCurrentCost.value,
  ))

  /** 变动率超过30%的异常项 */
  const significantChanges = computed(() =>
    rows.value.filter((r) => Math.abs(r.costChangeRate) > 30 || Math.abs(r.netValueChangeRate) > 30),
  )

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: keyof AnalysisRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  function _persist(): void { onSave?.(`${ITEM_PREFIX}-rows`, rows.value) }
  function saveNote(note: string): void { auditNote.value = note; onSave?.(`${ITEM_PREFIX}-audit-note`, note) }
  function saveConclusion(conclusion: string): void { auditConclusion.value = conclusion; onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion) }

  watch(allResponses, () => _load(), { immediate: true })

  return {
    rows, auditNote, auditConclusion, useOnlyOffice,
    totalCurrentCost, totalCurrentNetValue, overallDepletionRate, significantChanges,
    updateCell, saveNote, saveConclusion,
  }
}
