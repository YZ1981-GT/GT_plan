/**
 * useK4DetailColumnPrefs — K4-2 明细表列显隐设置 (⚙ popover)
 *
 * 对齐 D5/D6/D7/K7 范式：
 * - 3 预设（全部/核心基础/审定+核查）
 * - 单列 checkbox 显隐
 * - 隐藏空列快捷
 * - localStorage 持久化 key: k4-detail-column-prefs
 *
 * 科目：2245 其他流动负债（负债类）
 */
import { ref, computed, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K4ColumnPref {
  key: string
  label: string
  visible: boolean
  group: 'basic' | 'check' | 'adjust'
  alwaysShow?: boolean  // 序号/项目名称 不可隐藏
}

export interface K4ColumnPreset {
  name: string
  description: string
  visibleKeys: Set<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'k4-detail-column-prefs'

/** 全部列定义 */
const ALL_COLUMNS: Omit<K4ColumnPref, 'visible'>[] = [
  // 基础区段
  { key: 'seqNo', label: '序号', group: 'basic', alwaysShow: true },
  { key: 'projectName', label: '项目名称', group: 'basic', alwaysShow: true },
  { key: 'nature', label: '性质', group: 'basic' },
  { key: 'beginBalance', label: '期初余额', group: 'basic' },
  { key: 'increase', label: '本期增加(贷方)', group: 'basic' },
  { key: 'decrease', label: '本期减少(借方)', group: 'basic' },
  { key: 'endBalance', label: '期末余额', group: 'basic' },
  // 检查区段
  { key: 'increaseReason', label: '增减原因', group: 'check' },
  { key: 'voucherRef', label: '凭证号', group: 'check' },
  { key: 'postPayment', label: '期后偿付金额', group: 'check' },
  { key: 'postPaymentDate', label: '偿付日期', group: 'check' },
  { key: 'checkConclusion', label: '核查结论', group: 'check' },
  { key: 'remark', label: '备注', group: 'check' },
  // 调整区段
  { key: 'openingAdjust', label: '期初调整', group: 'adjust' },
  { key: 'ajeIncrease', label: 'AJE增加', group: 'adjust' },
  { key: 'ajeDecrease', label: 'AJE减少', group: 'adjust' },
  { key: 'rjeIncrease', label: 'RJE增加', group: 'adjust' },
  { key: 'rjeDecrease', label: 'RJE减少', group: 'adjust' },
  { key: 'auditedEnd', label: '审定期末', group: 'adjust' },
]

/** 预设方案 */
const PRESETS: K4ColumnPreset[] = [
  {
    name: '全部',
    description: '显示所有列',
    visibleKeys: new Set(ALL_COLUMNS.map(c => c.key)),
  },
  {
    name: '核心基础',
    description: '项目/性质/期初/增/减/期末',
    visibleKeys: new Set(['seqNo', 'projectName', 'nature', 'beginBalance', 'increase', 'decrease', 'endBalance']),
  },
  {
    name: '审定+核查',
    description: '项目/期末/审定期末/期后偿付/核查结论',
    visibleKeys: new Set(['seqNo', 'projectName', 'endBalance', 'auditedEnd', 'postPayment', 'checkConclusion', 'remark']),
  },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK4DetailColumnPrefs() {
  const columns = ref<K4ColumnPref[]>(_loadFromStorage())
  const activePreset = ref<string>('全部')

  function _loadFromStorage(): K4ColumnPref[] {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const map: Record<string, boolean> = JSON.parse(saved)
        return ALL_COLUMNS.map(c => ({
          ...c,
          visible: c.alwaysShow ? true : (map[c.key] ?? true),
        }))
      }
    } catch { /* ignore */ }
    return ALL_COLUMNS.map(c => ({ ...c, visible: true }))
  }

  function _saveToStorage(): void {
    try {
      const map: Record<string, boolean> = {}
      for (const col of columns.value) {
        map[col.key] = col.visible
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(map))
    } catch { /* ignore */ }
  }

  /** 切换单列显隐 */
  function toggleColumn(key: string): void {
    const col = columns.value.find(c => c.key === key)
    if (col && !col.alwaysShow) {
      col.visible = !col.visible
      activePreset.value = ''
      _saveToStorage()
    }
  }

  /** 应用预设 */
  function applyPreset(presetName: string): void {
    const preset = PRESETS.find(p => p.name === presetName)
    if (!preset) return
    for (const col of columns.value) {
      col.visible = col.alwaysShow ? true : preset.visibleKeys.has(col.key)
    }
    activePreset.value = presetName
    _saveToStorage()
  }

  /** 重置为全部显示 */
  function resetAll(): void {
    for (const col of columns.value) col.visible = true
    activePreset.value = '全部'
    _saveToStorage()
  }

  /** 隐藏空列（基于传入的行数据） */
  function hideEmptyColumns(rows: any[]): void {
    if (!rows.length) return
    for (const col of columns.value) {
      if (col.alwaysShow) continue
      const hasData = rows.some(row => {
        const v = row[col.key]
        return v !== 0 && v !== '' && v != null
      })
      col.visible = hasData
    }
    activePreset.value = ''
    _saveToStorage()
  }

  /** 当前可见的列 key 集合 */
  const visibleKeys = computed(() => new Set(columns.value.filter(c => c.visible).map(c => c.key)))

  /** 按组分列 */
  const columnsByGroup = computed(() => {
    const groups: Record<string, K4ColumnPref[]> = { basic: [], check: [], adjust: [] }
    for (const col of columns.value) {
      groups[col.group]?.push(col)
    }
    return groups
  })

  return {
    columns,
    activePreset,
    presets: PRESETS,
    visibleKeys,
    columnsByGroup,
    toggleColumn,
    applyPreset,
    resetAll,
    hideEmptyColumns,
  }
}
