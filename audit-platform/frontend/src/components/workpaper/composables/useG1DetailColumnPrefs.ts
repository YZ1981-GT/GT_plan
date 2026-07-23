/**
 * useG1DetailColumnPrefs — G1-2 明细表列显隐偏好（⚙ 列设置）
 *
 * G1-2 明细已按区段（准入/期初/本期/期末/披露）分 Tab，本 composable 在
 * 当前区段内提供列级 show/hide + 隐藏空列，偏好按 localStorage 持久化（纯前端 UI）。
 * 「投资项目」列（securityName）常显不纳入设置。
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { G1DetailColumn, G1DetailSegment, TradingDetailRow } from './useG1Detail'

const STORAGE_KEY = 'g1-2-detail-column-prefs'

type SegmentHiddenMap = Record<string, string[]> // segmentKey -> hidden prop[]

function loadPrefs(): SegmentHiddenMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

export function useG1DetailColumnPrefs(opts: {
  segments: G1DetailSegment[]
  currentSegmentKey: Ref<string>
  rows: Ref<TradingDetailRow[]>
}) {
  const hiddenMap = ref<SegmentHiddenMap>(loadPrefs())

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(hiddenMap.value))
    } catch {
      /* ignore quota */
    }
  }

  /** 当前区段所有可配置列（排除固定的 securityName） */
  const configurableColumns = computed<G1DetailColumn[]>(() => {
    const seg = opts.segments.find((s) => s.key === opts.currentSegmentKey.value)
    return (seg?.columns ?? []).filter((c) => c.prop !== 'securityName')
  })

  const hiddenSet = computed<Set<string>>(
    () => new Set(hiddenMap.value[opts.currentSegmentKey.value] ?? []),
  )

  /** 过滤后可见列（供 el-table 渲染） */
  const visibleColumns = computed<G1DetailColumn[]>(() =>
    configurableColumns.value.filter((c) => !hiddenSet.value.has(String(c.prop))),
  )

  function isVisible(prop: string): boolean {
    return !hiddenSet.value.has(prop)
  }

  function setColumnVisible(prop: string, visible: boolean) {
    const key = opts.currentSegmentKey.value
    const cur = new Set(hiddenMap.value[key] ?? [])
    if (visible) cur.delete(prop)
    else cur.add(prop)
    hiddenMap.value = { ...hiddenMap.value, [key]: Array.from(cur) }
    persist()
  }

  /** 隐藏当前区段全部为空/零的列（securityName 除外） */
  function hideEmptyColumns() {
    const key = opts.currentSegmentKey.value
    const empties: string[] = []
    for (const col of configurableColumns.value) {
      const prop = String(col.prop) as keyof TradingDetailRow
      const allEmpty = opts.rows.value.every((r) => {
        const v = r[prop]
        return v === 0 || v === '' || v == null || v === false
      })
      if (allEmpty) empties.push(prop)
    }
    hiddenMap.value = { ...hiddenMap.value, [key]: empties }
    persist()
  }

  /** 恢复当前区段全部显示 */
  function resetCurrentSegment() {
    const key = opts.currentSegmentKey.value
    const next = { ...hiddenMap.value }
    delete next[key]
    hiddenMap.value = next
    persist()
  }

  // 切区段时无需额外处理，computed 已按 currentSegmentKey 派生
  watch(opts.currentSegmentKey, () => { /* reactive via computed */ })

  return {
    configurableColumns,
    visibleColumns,
    isVisible,
    setColumnVisible,
    hideEmptyColumns,
    resetCurrentSegment,
  }
}

export default useG1DetailColumnPrefs
