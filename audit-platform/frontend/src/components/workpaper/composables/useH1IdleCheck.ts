/**
 * useH1IdleCheck — H1-4 闲置检查表 composable
 *
 * IdleAssetRow 12列 + 闲置统计computed + 减值迹象判定
 * addRow(弹窗命名)/removeRow + 汇总统计
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.6
 * Requirements: 5.1-5.8
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface IdleAssetRow {
  rowId: string
  seq: number                  // 序号
  name: string                 // 资产名称
  assetNo: string              // 资产编号
  originalCost: number         // 原值
  accDep: number               // 累计折旧
  netValue: number             // 净值
  idleReason: string           // 闲置原因
  idleStartDate: string        // 闲置起始日期
  hasImpairment: string        // 是否计提减值(Y/N)
  impairmentAmount: number     // 减值金额
  disposalSuggestion: string   // 处置建议
  remark: string               // 备注
}

/** 汇总统计 */
export interface IdleStatistics {
  totalCount: number           // 闲置资产总数
  totalNetValue: number        // 闲置净值合计
  impairedTotal: number        // 已计提减值合计
  notImpairedCount: number     // 未计提减值数量
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H1-4'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1IdleCheck(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<IdleAssetRow[]>([])
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

  function _normalizeRow(raw: any, idx: number): IdleAssetRow {
    return {
      rowId: raw.rowId ?? `idle-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      name: raw.name ?? '',
      assetNo: raw.assetNo ?? '',
      originalCost: Number(raw.originalCost) || 0,
      accDep: Number(raw.accDep) || 0,
      netValue: Number(raw.netValue) || 0,
      idleReason: raw.idleReason ?? '',
      idleStartDate: raw.idleStartDate ?? '',
      hasImpairment: raw.hasImpairment ?? 'N',
      impairmentAmount: Number(raw.impairmentAmount) || 0,
      disposalSuggestion: raw.disposalSuggestion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed: 汇总统计 ────────────────────────────────────────────────────

  const statistics = computed<IdleStatistics>(() => {
    const totalCount = rows.value.length
    const totalNetValue = calcSubtotal(rows.value.map((r) => r.netValue))
    const impairedTotal = calcSubtotal(
      rows.value.filter((r) => r.hasImpairment === 'Y').map((r) => r.impairmentAmount),
    )
    const notImpairedCount = rows.value.filter(
      (r) => r.hasImpairment !== 'Y' && r.netValue > 0,
    ).length
    return { totalCount, totalNetValue, impairedTotal, notImpairedCount }
  })

  /** 减值迹象判定：净值>0且未计提减值 */
  function hasImpairmentIndication(row: IdleAssetRow): boolean {
    return row.netValue > 0 && row.hasImpairment !== 'Y'
  }

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addRow(name: string): void {
    const newRow: IdleAssetRow = {
      rowId: `idle-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1,
      name,
      assetNo: '',
      originalCost: 0,
      accDep: 0,
      netValue: 0,
      idleReason: '',
      idleStartDate: '',
      hasImpairment: 'N',
      impairmentAmount: 0,
      disposalSuggestion: '',
      remark: '',
    }
    rows.value.push(newRow)
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      rows.value.forEach((r, i) => { r.seq = i + 1 })
      _persist()
    }
  }

  function updateCell(rowId: string, field: keyof IdleAssetRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persist()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    options?.onSave?.(`${ITEM_PREFIX}-rows`, rows.value)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    auditNote,
    auditConclusion,
    statistics,
    hasImpairmentIndication,
    addRow,
    removeRow,
    updateCell,
    saveNote,
    saveConclusion,
  }
}

export default useH1IdleCheck
