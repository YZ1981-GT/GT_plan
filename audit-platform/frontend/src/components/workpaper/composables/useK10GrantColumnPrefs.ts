/**
 * useK10GrantColumnPrefs — K10-4 政府补助核对表 列显隐偏好（宽表 13 列）
 *
 * - 可切换列显隐 + 预设方案（全部/核心/递延）+ 隐藏空列
 * - localStorage 持久化（key: k10-4-column-prefs），仅前端 UI 偏好，不影响数据
 * - 补助项目/期末递延余额(公式)/操作 列常显，不在可切换集合
 */
import { ref, computed, watch, type Ref } from 'vue'

export interface K10GrantColDef {
  key: string
  label: string
}

/** 可切换列（不含常显的 补助项目/期末递延余额/操作） */
export const K10_GRANT_TOGGLE_COLS: K10GrantColDef[] = [
  { key: 'period', label: '期间' },
  { key: 'directReduceCost', label: '直接冲减成本' },
  { key: 'directToOtherIncome', label: '直接计入其他收益' },
  { key: 'directToNonOpIncome', label: '直接计入营业外' },
  { key: 'newDeferred', label: '新增递延' },
  { key: 'openingDeferred', label: '期初递延余额' },
  { key: 'amortReduceCost', label: '摊销冲减成本' },
  { key: 'amortToOtherIncome', label: '摊销转其他收益' },
  { key: 'amortToNonOpIncome', label: '摊销转营业外' },
  { key: 'refund', label: '返还' },
  { key: 'otherTransferOut', label: '其他转出' },
]

const STORAGE_KEY = 'k10-4-column-prefs'

/** 预设方案 */
const PRESETS: Record<string, string[]> = {
  // 全部：所有可切换列
  full: K10_GRANT_TOGGLE_COLS.map(c => c.key),
  // 核心：期间 + 直接计入其他收益 + 摊销转其他收益（其余隐藏）
  core: ['period', 'directToOtherIncome', 'amortToOtherIncome'],
  // 递延：递延相关列
  deferred: ['period', 'newDeferred', 'openingDeferred', 'amortReduceCost', 'amortToOtherIncome', 'amortToNonOpIncome', 'refund', 'otherTransferOut'],
}

export function useK10GrantColumnPrefs(rows?: Ref<any[]>) {
  const visible = ref<Record<string, boolean>>({})

  function _default(): Record<string, boolean> {
    const m: Record<string, boolean> = {}
    for (const c of K10_GRANT_TOGGLE_COLS) m[c.key] = true
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
    for (const c of K10_GRANT_TOGGLE_COLS) m[c.key] = keys.includes(c.key)
    visible.value = m
    persist()
  }

  function resetDefault(): void {
    visible.value = _default()
    persist()
  }

  /** 隐藏所有全零空列（保留至少有值的列） */
  function hideEmptyColumns(): void {
    if (!rows?.value) return
    const m = { ...visible.value }
    for (const c of K10_GRANT_TOGGLE_COLS) {
      if (c.key === 'period') continue // 文本列不判空
      const hasVal = rows.value.some(r => Number(r?.[c.key] ?? 0) !== 0)
      m[c.key] = hasVal
    }
    visible.value = m
    persist()
  }

  const visibleCount = computed(() => K10_GRANT_TOGGLE_COLS.filter(c => isVisible(c.key)).length)

  watch(visible, () => persist(), { deep: true })

  load()

  return {
    columns: K10_GRANT_TOGGLE_COLS,
    visible,
    isVisible,
    applyPreset,
    resetDefault,
    hideEmptyColumns,
    visibleCount,
    load,
  }
}

export default useK10GrantColumnPrefs
