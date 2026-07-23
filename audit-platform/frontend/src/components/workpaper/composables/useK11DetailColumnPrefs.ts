/**
 * useK11DetailColumnPrefs — K11-2 明细表列显隐偏好
 *
 * K11-2 已按 2 区段 Tab（基础/核对）拆分宽表；本 composable 在区段内进一步
 * 允许隐藏非核心列（减值项目/凭证/结论等），偏好存 localStorage。
 * 核心列（资产类别/本期计提/本期发生额）恒显，不在可隐藏集合内。
 */
import { ref, computed } from 'vue'

const STORAGE_KEY = 'K11-2-detail-column-prefs'

export interface ColumnGroup {
  label: string
  columns: string[]
}

/** 可隐藏列（核心列不入此集合，恒显） */
export const K11_DETAIL_COLUMN_GROUPS: ColumnGroup[] = [
  { label: '基础', columns: ['impairmentItem', 'currentReversal'] },
  { label: '核对', columns: ['sourceWp', 'sourceAmount', 'variance', 'voucherRef', 'conclusion'] },
]

export const K11_DETAIL_TOGGLEABLE = K11_DETAIL_COLUMN_GROUPS.flatMap(g => g.columns)

/** 列中文名（popover 展示） */
export const K11_DETAIL_COLUMN_LABELS: Record<string, string> = {
  impairmentItem: '减值项目',
  currentReversal: '本期转回',
  sourceWp: '来源底稿',
  sourceAmount: '源底稿计提金额',
  variance: '差异',
  voucherRef: '凭证',
  conclusion: '结论',
}

export interface ColumnPreset {
  key: string
  label: string
  columns: string[]
}

export const K11_DETAIL_PRESETS: ColumnPreset[] = [
  { key: 'all', label: '全部', columns: K11_DETAIL_TOGGLEABLE },
  { key: 'core', label: '核心', columns: ['currentReversal', 'sourceWp', 'sourceAmount', 'variance'] },
]

export function useK11DetailColumnPrefs() {
  const visibleColumns = ref<Set<string>>(new Set(K11_DETAIL_TOGGLEABLE))

  function loadPrefs(): void {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        const parsed = JSON.parse(stored)
        if (Array.isArray(parsed)) {
          visibleColumns.value = new Set(parsed)
          return
        }
      }
    } catch { /* ignore */ }
    visibleColumns.value = new Set(K11_DETAIL_TOGGLEABLE)
  }

  function savePrefs(): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(visibleColumns.value)))
    } catch { /* ignore */ }
  }

  function toggleColumn(col: string): void {
    const s = new Set(visibleColumns.value)
    if (s.has(col)) s.delete(col)
    else s.add(col)
    visibleColumns.value = s
    savePrefs()
  }

  function applyPreset(presetKey: string): void {
    const preset = K11_DETAIL_PRESETS.find(p => p.key === presetKey)
    if (preset) {
      visibleColumns.value = new Set(preset.columns)
      savePrefs()
    }
  }

  function resetToAll(): void {
    visibleColumns.value = new Set(K11_DETAIL_TOGGLEABLE)
    savePrefs()
  }

  /** 核心列恒显；其余列查偏好集合 */
  function isVisible(col: string): boolean {
    if (!K11_DETAIL_TOGGLEABLE.includes(col)) return true
    return visibleColumns.value.has(col)
  }

  const visibleCount = computed(() => visibleColumns.value.size)
  const totalCount = K11_DETAIL_TOGGLEABLE.length

  loadPrefs()

  return {
    visibleColumns,
    toggleColumn,
    applyPreset,
    resetToAll,
    isVisible,
    visibleCount,
    totalCount,
    K11_DETAIL_COLUMN_GROUPS,
    K11_DETAIL_COLUMN_LABELS,
    K11_DETAIL_PRESETS,
  }
}

export default useK11DetailColumnPrefs
