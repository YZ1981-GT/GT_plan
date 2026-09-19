/**
 * useB50DetailColumnPrefs — B50 Tab3 认定矩阵「元列」显隐偏好
 *
 * 说明：6 认定单元格是矩阵核心恒显示，本 prefs 仅控制审计范围/应对方案等元列显隐。
 * - 列分组（审计范围 / 应对方案）
 * - 预设方案（全部 / 核心）
 * - localStorage 持久化 b50-t3-column-prefs
 * - 纯前端 UI 偏好，不入 checklist_responses
 *
 * Spec: .kiro/specs/b50-workpaper-rework/ Task 5
 */
import { ref, computed } from 'vue'

const STORAGE_KEY = 'b50-t3-column-prefs'

export interface ColumnGroup {
  label: string
  columns: { key: string; label: string }[]
}

/** 可显隐的元列（科目名 + 6 认定单元格 + 综合风险恒显示，不在此列） */
export const B50_T3_COLUMN_GROUPS: ColumnGroup[] = [
  {
    label: '审计范围（源 B50-3）',
    columns: [
      { key: 'balance', label: '余额/金额' },
      { key: 'category', label: '类别' },
      { key: 'estimate', label: '是否会计估计' },
    ],
  },
  {
    label: '风险应对',
    columns: [
      { key: 'cycle', label: '相关业务循环' },
      { key: 'approach', label: '应对方案' },
      { key: 'reliance', label: '拟信赖控制' },
      { key: 'subonly', label: '仅实质性是否足够' },
    ],
  },
]

export const ALL_COLUMNS = B50_T3_COLUMN_GROUPS.flatMap(g => g.columns.map(c => c.key))

/** 默认显示：余额/类别/循环/应对方案；隐藏：会计估计/拟信赖控制/仅实质性 */
export const DEFAULT_VISIBLE = ['balance', 'category', 'cycle', 'approach']

export interface ColumnPreset {
  key: string
  label: string
  columns: string[]
}

export const B50_T3_COLUMN_PRESETS: ColumnPreset[] = [
  { key: 'all', label: '全部', columns: ALL_COLUMNS },
  { key: 'core', label: '核心', columns: DEFAULT_VISIBLE },
]

export function useB50DetailColumnPrefs() {
  const visibleColumns = ref<Set<string>>(new Set(DEFAULT_VISIBLE))

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
    visibleColumns.value = new Set(DEFAULT_VISIBLE)
  }

  function savePrefs(): void {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(visibleColumns.value)))
  }

  function toggleColumn(col: string): void {
    const s = new Set(visibleColumns.value)
    if (s.has(col)) s.delete(col)
    else s.add(col)
    visibleColumns.value = s
    savePrefs()
  }

  function applyPreset(presetKey: string): void {
    const preset = B50_T3_COLUMN_PRESETS.find(p => p.key === presetKey)
    if (preset) {
      visibleColumns.value = new Set(preset.columns)
      savePrefs()
    }
  }

  function resetToDefault(): void {
    visibleColumns.value = new Set(DEFAULT_VISIBLE)
    savePrefs()
  }

  function isVisible(col: string): boolean {
    return visibleColumns.value.has(col)
  }

  const visibleCount = computed(() => visibleColumns.value.size)
  const totalCount = ALL_COLUMNS.length

  loadPrefs()

  return {
    visibleColumns,
    toggleColumn,
    applyPreset,
    resetToDefault,
    isVisible,
    visibleCount,
    totalCount,
    B50_T3_COLUMN_GROUPS,
    B50_T3_COLUMN_PRESETS,
  }
}

export default useB50DetailColumnPrefs
