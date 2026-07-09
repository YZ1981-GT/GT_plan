/**
 * useH5IdleCheck — H5-4 闲置检查 composable
 *
 * 11列, 减值迹象标记
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.4
 * Requirements: 4.1
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface IdleCheckRow {
  rowId: string
  seq: number                   // 序号
  assetName: string             // 资产名称
  oilField: string              // 油田
  originalCost: number          // 原值
  netValue: number              // 净值
  idleReason: string            // 闲置原因
  idleStartDate: string         // 闲置起始日
  disposalPlan: string          // 处置计划
  impairmentSign: boolean       // 减值迹象
  conclusion: string            // 核查结论
  remark: string                // 备注
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H5-4'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5IdleCheck(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = opts

  const rows = ref<IdleCheckRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _load(): void {
    const item = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    const raw = item?.remark
    if (!raw) { rows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      rows.value = Array.isArray(parsed) ? parsed.map(_normalize) : []
    } catch { rows.value = [] }
    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalize(raw: any): IdleCheckRow {
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seq: Number(raw.seq) || 0,
      assetName: raw.assetName ?? '',
      oilField: raw.oilField ?? '',
      originalCost: Number(raw.originalCost) || 0,
      netValue: Number(raw.netValue) || 0,
      idleReason: raw.idleReason ?? '',
      idleStartDate: raw.idleStartDate ?? '',
      disposalPlan: raw.disposalPlan ?? '',
      impairmentSign: raw.impairmentSign === true,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const impairmentCount = computed(() => rows.value.filter((r) => r.impairmentSign).length)
  const totalIdleNetValue = computed(() => rows.value.reduce((sum, r) => sum + r.netValue, 0))

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(assetName: string): void {
    rows.value.push({
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1, assetName,
      oilField: '', originalCost: 0, netValue: 0,
      idleReason: '', idleStartDate: '', disposalPlan: '',
      impairmentSign: false, conclusion: '', remark: '',
    })
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) { rows.value.splice(idx, 1); _persist() }
  }

  function updateCell(rowId: string, field: keyof IdleCheckRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persist()
  }

  function _persist(): void { onSave?.(`${ITEM_PREFIX}-rows`, rows.value) }
  function saveNote(note: string): void { auditNote.value = note; onSave?.(`${ITEM_PREFIX}-audit-note`, note) }
  function saveConclusion(conclusion: string): void { auditConclusion.value = conclusion; onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion) }

  watch(allResponses, () => _load(), { immediate: true })

  return {
    rows, auditNote, auditConclusion,
    impairmentCount, totalIdleNetValue,
    addRow, removeRow, updateCell, saveNote, saveConclusion,
  }
}
