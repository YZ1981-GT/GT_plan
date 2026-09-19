/**
 * useK10DetailColumnPrefs — K10-2 明细表 列显隐偏好（12 列）
 *
 * - 可切换列 + 预设（全部/核心/审定）+ 隐藏空列
 * - localStorage 持久化（key: k10-2-column-prefs），仅前端 UI 偏好
 * - 序号/补助项目/审定/上年审定(公式)/操作 列常显，不在可切换集合
 */
import { ref, computed, watch, type Ref } from 'vue'

export interface K10DetailColDef {
  key: string
  label: string
}

/** 可切换列（不含常显的 序号/补助项目/审定/上年审定/操作） */
export const K10_DETAIL_TOGGLE_COLS: K10DetailColDef[] = [
  { key: 'grantType', label: '类型' },
  { key: 'judgmentBasis', label: '判断依据' },
  { key: 'unadjusted', label: '本期未审' },
  { key: 'aje', label: 'AJE' },
  { key: 'rje', label: '重分类' },
  { key: 'priorUnadj', label: '上年未审' },
  { key: 'priorAje', label: '上年AJE' },
  { key: 'fileRef', label: '文件索引号' },
]

const STORAGE_KEY = 'k10-2-column-prefs'

const PRESETS: Record<string, string[]> = {
  full: K10_DETAIL_TOGGLE_COLS.map(c => c.key),
  // 核心：类型 + 判断依据 + 本期未审（审定/上年审定 公式列常显）
  core: ['grantType', 'judgmentBasis', 'unadjusted'],
  // 审定：本期调整链
  audited: ['grantType', 'unadjusted', 'aje', 'rje'],
}

export function useK10DetailColumnPrefs(rows?: Ref<any[]>) {
  const visible = ref<Record<string, boolean>>({})

  function _default(): Record<string, boolean> {
    const m: Record<string, boolean> = {}
    for (const c of K10_DETAIL_TOGGLE_COLS) m[c.key] = true
    return m
  }

  function load(): void {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const parsed = JSON.parse(saved)
        const m = _default()
        for (const k of Object.keys(m)) if (typeof parsed[k] === 'boolean') m[k] = parsed[k]
        visible.value = m
        return
      }
    } catch { /* ignore */ }
    visible.value = _default()
  }

  function persist(): void {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(visible.value)) } catch { /* ignore */ }
  }

  function isVisible(key: string): boolean {
    return visible.value[key] !== false
  }

  function applyPreset(name: keyof typeof PRESETS): void {
    const keys = PRESETS[name]
    if (!keys) return
    const m: Record<string, boolean> = {}
    for (const c of K10_DETAIL_TOGGLE_COLS) m[c.key] = keys.includes(c.key)
    visible.value = m
    persist()
  }

  function resetDefault(): void {
    visible.value = _default()
    persist()
  }

  /** 隐藏全零/全空列（文本列判空串，数值列判 0） */
  function hideEmptyColumns(): void {
    if (!rows?.value) return
    const m = { ...visible.value }
    const textCols = new Set(['grantType', 'judgmentBasis', 'fileRef'])
    for (const c of K10_DETAIL_TOGGLE_COLS) {
      if (textCols.has(c.key)) {
        m[c.key] = rows.value.some(r => String(r?.[c.key] ?? '').trim() !== '')
      } else {
        m[c.key] = rows.value.some(r => Number(r?.[c.key] ?? 0) !== 0)
      }
    }
    visible.value = m
    persist()
  }

  const visibleCount = computed(() => K10_DETAIL_TOGGLE_COLS.filter(c => isVisible(c.key)).length)

  watch(visible, () => persist(), { deep: true })

  load()

  return {
    columns: K10_DETAIL_TOGGLE_COLS,
    visible,
    isVisible,
    applyPreset,
    resetDefault,
    hideEmptyColumns,
    visibleCount,
    load,
  }
}

export default useK10DetailColumnPrefs
