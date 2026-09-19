/**
 * useD6DetailColumnPrefs — D6-2 明细表30列显隐偏好
 *
 * 功能：
 * - 列分组(基础信息/期初/期初账龄/本期发生/期末/期末账龄/收款权/其他)
 * - 预设方案(全部/核心/审定+账龄)
 * - localStorage 持久化 D6-detail-column-prefs
 * - 隐藏空列
 * - 重置默认
 */
import { ref, computed, watch } from 'vue'

const STORAGE_KEY = 'D6-detail-column-prefs'

export interface ColumnGroup {
  label: string
  columns: string[]
}

export const D6_COLUMN_GROUPS: ColumnGroup[] = [
  { label: '基础信息', columns: ['seqNo', 'contractName', 'contractType', 'customerName', 'companyCode', 'relatedPartyType'] },
  { label: '期初', columns: ['priorUnadjusted', 'priorAje', 'priorRje', 'priorAudited'] },
  { label: '期初账龄', columns: ['agePrior1y', 'agePrior1to2y', 'agePrior2to3y', 'agePrior3yAbove'] },
  { label: '本期发生', columns: ['debitAmount', 'creditAmount'] },
  { label: '期末', columns: ['endUnadjusted', 'endAje', 'endRje', 'endAudited'] },
  { label: '期末账龄', columns: ['ageEnd1y', 'ageEnd1to2y', 'ageEnd2to3y', 'ageEnd3yAbove'] },
  { label: '收款权', columns: ['receivableWithin1y', 'receivableAbove1y'] },
  { label: '其他', columns: ['isInConstructionPeriod', 'creditRiskGroup', 'isConfirmed', 'postPeriodSettlement'] },
]

export const ALL_COLUMNS = D6_COLUMN_GROUPS.flatMap(g => g.columns)

export interface ColumnPreset {
  key: string
  label: string
  columns: string[]
}

export const D6_COLUMN_PRESETS: ColumnPreset[] = [
  { key: 'all', label: '全部', columns: ALL_COLUMNS },
  { key: 'core', label: '核心', columns: ['seqNo', 'contractName', 'contractType', 'customerName', 'priorAudited', 'debitAmount', 'creditAmount', 'endAudited', 'postPeriodSettlement'] },
  { key: 'audit-aging', label: '审定+账龄', columns: ['seqNo', 'contractName', 'customerName', 'priorAudited', 'endAudited', 'ageEnd1y', 'ageEnd1to2y', 'ageEnd2to3y', 'ageEnd3yAbove', 'receivableWithin1y', 'receivableAbove1y'] },
]

export function useD6DetailColumnPrefs() {
  const visibleColumns = ref<Set<string>>(new Set(ALL_COLUMNS))

  // Load from localStorage
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
    visibleColumns.value = new Set(ALL_COLUMNS)
  }

  // Save to localStorage
  function savePrefs(): void {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(visibleColumns.value)))
  }

  // Toggle column
  function toggleColumn(col: string): void {
    const s = new Set(visibleColumns.value)
    if (s.has(col)) {
      s.delete(col)
    } else {
      s.add(col)
    }
    visibleColumns.value = s
    savePrefs()
  }

  // Apply preset
  function applyPreset(presetKey: string): void {
    const preset = D6_COLUMN_PRESETS.find(p => p.key === presetKey)
    if (preset) {
      visibleColumns.value = new Set(preset.columns)
      savePrefs()
    }
  }

  // Reset to all
  function resetToAll(): void {
    visibleColumns.value = new Set(ALL_COLUMNS)
    savePrefs()
  }

  // Check if a column is visible
  function isVisible(col: string): boolean {
    return visibleColumns.value.has(col)
  }

  // Visible count
  const visibleCount = computed(() => visibleColumns.value.size)
  const totalCount = ALL_COLUMNS.length

  loadPrefs()

  return {
    visibleColumns,
    toggleColumn,
    applyPreset,
    resetToAll,
    isVisible,
    visibleCount,
    totalCount,
    D6_COLUMN_GROUPS,
    D6_COLUMN_PRESETS,
  }
}

export default useD6DetailColumnPrefs
