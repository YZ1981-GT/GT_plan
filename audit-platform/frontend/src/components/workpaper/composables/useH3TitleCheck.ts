/**
 * useH3TitleCheck — H3-12 产权核对 composable
 *
 * TitleRow 16列 + 面积差异 + 产权异常高亮
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.16
 * Requirements: 12.1-12.5
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import { calcTitleDiff } from './useH3TransferEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface TitleRow {
  rowId: string
  seq: number
  assetName: string
  bookValue: number           // 账面原值
  titleCertNo: string         // 产权证号
  certArea: number            // 证载面积
  bookArea: number            // 账面面积
  areaDiff: number            // 面积差异（公式）
  certOwner: string           // 证载所有人
  isAuditEntity: boolean      // 是否被审计单位
  mortgage: string            // 抵押情况
  seizure: string             // 查封情况
  restriction: string         // 使用限制
  certPurpose: string         // 证载用途
  actualPurpose: string       // 实际用途
  purposeConsistent: boolean  // 用途是否一致
  remark: string
}

const ITEM_ID = 'H3-12-title-rows'

export function useH3TitleCheck(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params
  const rows = ref<TitleRow[]>([])

  function loadRows(): void {
    const raw = getValue(ITEM_ID)
    rows.value = Array.isArray(raw) ? raw.map(_normalize) : []
  }

  function _normalize(raw: any, idx?: number): TitleRow {
    const certArea = Number(raw.certArea) || 0
    const bookArea = Number(raw.bookArea) || 0
    return {
      rowId: raw.rowId ?? `tt-${Math.random().toString(36).slice(2, 8)}`,
      seq: raw.seq ?? (idx != null ? idx + 1 : 1),
      assetName: raw.assetName ?? '',
      bookValue: Number(raw.bookValue) || 0,
      titleCertNo: raw.titleCertNo ?? '',
      certArea,
      bookArea,
      areaDiff: certArea - bookArea,
      certOwner: raw.certOwner ?? '',
      isAuditEntity: raw.isAuditEntity ?? true,
      mortgage: raw.mortgage ?? '',
      seizure: raw.seizure ?? '',
      restriction: raw.restriction ?? '',
      certPurpose: raw.certPurpose ?? '',
      actualPurpose: raw.actualPurpose ?? '',
      purposeConsistent: raw.purposeConsistent ?? true,
      remark: raw.remark ?? '',
    }
  }

  /** 产权异常行：非被审计单位（红色高亮） */
  const ownerAnomalies = computed(() => rows.value.filter((r) => !r.isAuditEntity))
  /** 面积差异行（黄色高亮） */
  const areaDiffRows = computed(() => rows.value.filter((r) => Math.abs(r.areaDiff) > 0.01))

  function addRow(assetName: string): void {
    rows.value.push(_normalize({ assetName, seq: rows.value.length + 1 }))
    _persist()
  }

  function removeRow(index: number): void {
    rows.value.splice(index, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
  }

  function updateCell(index: number, field: keyof TitleRow, value: any): void {
    const row = rows.value[index]
    if (!row) return
    ;(row as any)[field] = value
    row.areaDiff = row.certArea - row.bookArea
    _persist()
  }

  function _persist(): void { setValue(ITEM_ID, rows.value) }
  watch(allResponses, () => loadRows(), { immediate: true })

  return { rows, ownerAnomalies, areaDiffRows, addRow, removeRow, updateCell, loadRows }
}

export default useH3TitleCheck
