/**
 * useJ1DetailColumnPrefs - J1-2 明细表列显示偏好
 *
 * 14 列按分组可选：期初段/本期增减段/期初调整段/账项调整段/审定段/备注
 * 预设：全部 / 核心（期初+增+减+期末审定+备注）/ 审定（审定四列+备注）
 * 隐藏空列选项
 * localStorage 持久化 j1-2-detail-column-prefs
 */
import { ref, computed, type Ref } from 'vue'

export interface J1ColumnDef {
  key: string
  label: string
  group: string
  defaultVisible: boolean
}

export type J1DetailPreset = 'all' | 'core' | 'audited'

export const J1_DETAIL_COLUMN_GROUPS = [
  {
    name: '期初段',
    columns: [
      { key: 'unadjBegin', label: '未审-期初数', group: '期初段', defaultVisible: true },
    ],
  },
  {
    name: '本期增减段',
    columns: [
      { key: 'unadjIncrease', label: '未审-本期增加', group: '本期增减段', defaultVisible: true },
      { key: 'unadjDecrease', label: '未审-本期减少', group: '本期增减段', defaultVisible: true },
      { key: 'unadjEnd', label: '未审-期末数', group: '本期增减段', defaultVisible: true },
    ],
  },
  {
    name: '期初调整段',
    columns: [
      { key: 'openingAdj', label: '期初调整-账项调整', group: '期初调整段', defaultVisible: true },
    ],
  },
  {
    name: '账项调整段',
    columns: [
      { key: 'ajeIncrease', label: '账项调整-本期增加', group: '账项调整段', defaultVisible: true },
      { key: 'ajeDecrease', label: '账项调整-本期减少', group: '账项调整段', defaultVisible: true },
    ],
  },
  {
    name: '审定段',
    columns: [
      { key: 'auditedBegin', label: '审定-期初数', group: '审定段', defaultVisible: true },
      { key: 'auditedIncrease', label: '审定-本期增加', group: '审定段', defaultVisible: true },
      { key: 'auditedDecrease', label: '审定-本期减少', group: '审定段', defaultVisible: true },
      { key: 'auditedEnd', label: '审定-期末数', group: '审定段', defaultVisible: true },
    ],
  },
  {
    name: '备注',
    columns: [
      { key: 'remark', label: '备注', group: '备注', defaultVisible: true },
    ],
  },
]

const ALL_COLUMNS = J1_DETAIL_COLUMN_GROUPS.flatMap(g => g.columns)

const PRESETS: Record<J1DetailPreset, { label: string; keys: string[] | 'all' }> = {
  all: { label: '全部', keys: 'all' },
  core: { label: '核心', keys: ['unadjBegin', 'unadjIncrease', 'unadjDecrease', 'auditedEnd', 'remark'] },
  audited: { label: '审定', keys: ['auditedBegin', 'auditedIncrease', 'auditedDecrease', 'auditedEnd', 'remark'] },
}

const STORAGE_KEY = 'j1-2-detail-column-prefs'

export function useJ1DetailColumnPrefs(rows?: Ref<any[]>) {
  const hiddenKeys = ref<Set<string>>(loadFromStorage())
  const currentPreset = ref<J1DetailPreset | 'custom'>('all')

  function loadFromStorage(): Set<string> {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const arr = JSON.parse(raw)
        if (Array.isArray(arr)) return new Set(arr)
      }
    } catch { /* ignore */ }
    return new Set()
  }

  function saveToStorage() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...hiddenKeys.value]))
  }

  function isVisible(key: string): boolean {
    return !hiddenKeys.value.has(key)
  }

  function toggleColumn(key: string) {
    if (hiddenKeys.value.has(key)) {
      hiddenKeys.value.delete(key)
    } else {
      hiddenKeys.value.add(key)
    }
    currentPreset.value = 'custom'
    saveToStorage()
  }

  function setPreset(name: J1DetailPreset) {
    const preset = PRESETS[name]
    if (!preset) return
    if (preset.keys === 'all') {
      hiddenKeys.value = new Set()
    } else {
      const visible = new Set(preset.keys)
      hiddenKeys.value = new Set(ALL_COLUMNS.filter(c => !visible.has(c.key)).map(c => c.key))
    }
    currentPreset.value = name
    saveToStorage()
  }

  function hideEmptyColumns() {
    if (!rows?.value) return
    for (const col of ALL_COLUMNS) {
      const allEmpty = rows.value.every(r => {
        const v = r[col.key]
        return v === 0 || v === null || v === undefined || v === ''
      })
      if (allEmpty) hiddenKeys.value.add(col.key)
    }
    currentPreset.value = 'custom'
    saveToStorage()
  }

  function resetToDefault() {
    hiddenKeys.value = new Set()
    currentPreset.value = 'all'
    saveToStorage()
  }

  return {
    hiddenKeys,
    currentPreset,
    isVisible,
    toggleColumn,
    setPreset,
    hideEmptyColumns,
    resetToDefault,
    COLUMN_GROUPS: J1_DETAIL_COLUMN_GROUPS,
    PRESETS,
  }
}
