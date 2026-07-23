/**
 * useD7DetailColumnPrefs — D7 合同负债明细表列显示偏好（动态账龄段）
 *
 * 功能：
 * - 按分组管理列的显隐（核心组始终显示）
 * - 账龄组按当前项目账龄段（segments）动态生成显隐项（agingPrior.{key}/agingAudited.{key}）
 * - 偏好持久化到 localStorage（key: 'd7-detail-column-prefs'）
 * - 切换单列显隐 / 重置为默认隐藏方案
 *
 * 套 K7-5 / K8-8 范式：轻量 localStorage 方案
 * Spec: d7-contract-liabilities-enhancement Task 8
 * Requirements: 2.4, 2.5
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type { AgingSegment } from '@/composables/useAgingConfig'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ColumnGroup {
  label: string
  keys: string[]
  alwaysShow?: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'd7-detail-column-prefs'

/** 非账龄基础列组（账龄组按 segments 动态生成） */
const BASE_COLUMN_GROUPS: ColumnGroup[] = [
  { label: '核心', keys: ['customerName', 'contractName', 'natureType', 'endAudited', 'remark'], alwaysShow: true },
  { label: '期初', keys: ['priorUnadjusted', 'priorAje', 'priorRje', 'priorAudited'] },
  { label: '本期变动', keys: ['creditAmount', 'debitAmount', 'endUnadjusted'] },
  { label: '期末调整', keys: ['endAje', 'endRje'] },
  { label: '关联方', keys: ['relatedPartyType'] },
]

export const DEFAULT_HIDDEN: string[] = ['priorAje', 'priorRje', 'endAje', 'endRje']

// Keys that are always visible (from alwaysShow group)
const ALWAYS_VISIBLE_KEYS = new Set(
  BASE_COLUMN_GROUPS.filter(g => g.alwaysShow).flatMap(g => g.keys)
)

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD7DetailColumnPrefs(segments?: Ref<AgingSegment[]>) {
  const hiddenKeys = ref<Set<string>>(loadFromStorage())

  const segs = segments ?? ref<AgingSegment[]>([])

  /** 账龄列组按当前 segments 动态生成（期初审定账龄 + 期末审定账龄各段） */
  const columnGroups: ComputedRef<ColumnGroup[]> = computed(() => {
    const priorKeys = segs.value.map(s => `agingPrior.${s.key}`)
    const auditedKeys = segs.value.map(s => `agingAudited.${s.key}`)
    return [
      ...BASE_COLUMN_GROUPS,
      { label: '期初账龄', keys: priorKeys },
      { label: '期末账龄', keys: auditedKeys },
    ]
  })

  /** 段列 label 映射（供组件展示） */
  const colLabel = (key: string): string => {
    if (key.startsWith('agingPrior.') || key.startsWith('agingAudited.')) {
      const segKey = key.split('.')[1]
      return segs.value.find(s => s.key === segKey)?.label || segKey
    }
    return key
  }

  function isColVisible(key: string): boolean {
    if (ALWAYS_VISIBLE_KEYS.has(key)) return true
    return !hiddenKeys.value.has(key)
  }

  function toggleCol(key: string): void {
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

  function resetDefaults(): void {
    const defaults = new Set(DEFAULT_HIDDEN)
    hiddenKeys.value = defaults
    persistToStorage(defaults)
  }

  return {
    columnGroups,
    hiddenKeys,
    isColVisible,
    toggleCol,
    resetDefaults,
    colLabel,
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

export default useD7DetailColumnPrefs
