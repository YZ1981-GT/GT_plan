/**
 * useD5DetailColumnPrefs — D5-2 明细表列显示偏好
 *
 * 功能：
 * - 按分组管理列的显隐（核心组始终显示）
 * - 偏好持久化到 localStorage（key: 'd5-detail-column-prefs'）
 * - 切换单列显隐 / 重置为默认隐藏方案
 *
 * 套 K7-5 / K8-8 范式：轻量 localStorage 方案
 */
import { ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ColumnGroup {
  label: string
  keys: string[]
  alwaysShow?: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'd5-detail-column-prefs'

export const COLUMN_GROUPS: ColumnGroup[] = [
  { label: '核心', keys: ['category', 'itemName', 'endAudited', 'remark'], alwaysShow: true },
  { label: '期初', keys: ['priorUnadjusted', 'priorAje', 'priorRje', 'priorAudited'] },
  { label: '本期变动', keys: ['ociImpairment', 'periodIncrease', 'periodDecrease', 'endBalance'] },
  { label: '重分类与调整', keys: ['entityReclass', 'endUnadjusted', 'endAje', 'endRje'] },
  { label: 'OCI减值', keys: ['endOciImpairment'] },
]

export const DEFAULT_HIDDEN: string[] = ['priorAje', 'priorRje', 'ociImpairment', 'endOciImpairment']

// Keys that are always visible (from alwaysShow group)
const ALWAYS_VISIBLE_KEYS = new Set(
  COLUMN_GROUPS.filter(g => g.alwaysShow).flatMap(g => g.keys)
)

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD5DetailColumnPrefs() {
  const hiddenKeys = ref<Set<string>>(loadFromStorage())

  /**
   * Returns true if the column should be visible:
   * - alwaysShow group keys are always visible regardless of hiddenKeys
   * - Other keys are visible only if NOT in hiddenKeys
   */
  function isColVisible(key: string): boolean {
    if (ALWAYS_VISIBLE_KEYS.has(key)) return true
    return !hiddenKeys.value.has(key)
  }

  /**
   * Toggle a column's visibility (add/remove from hiddenKeys), then persist.
   */
  function toggleCol(key: string): void {
    // Don't allow toggling always-visible columns
    if (ALWAYS_VISIBLE_KEYS.has(key)) return
    const next = new Set(hiddenKeys.value)
    if (next.has(key)) {
      next.delete(key)
    } else {
      next.add(key)
    }
    hiddenKeys.value = next
    persistToStorage(next)
  }

  /**
   * Reset hiddenKeys to DEFAULT_HIDDEN, persist.
   */
  function resetDefaults(): void {
    const defaults = new Set(DEFAULT_HIDDEN)
    hiddenKeys.value = defaults
    persistToStorage(defaults)
  }

  return {
    columnGroups: COLUMN_GROUPS,
    hiddenKeys,
    isColVisible,
    toggleCol,
    resetDefaults,
  }
}

// ─── Persistence Helpers ─────────────────────────────────────────────────────

function loadFromStorage(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const arr: string[] = JSON.parse(raw)
      if (Array.isArray(arr)) return new Set(arr)
    }
  } catch { /* ignore corrupt data */ }
  return new Set(DEFAULT_HIDDEN)
}

function persistToStorage(keys: Set<string>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(keys)))
  } catch { /* ignore quota errors */ }
}

export default useD5DetailColumnPrefs
