/**
 * useK1DetailColumnPrefs — K1-2 明细表列显示偏好（localStorage）
 *
 * 与区段 Tab 配合：Tab 决定当前区段，列设置控制区内可选列显隐。
 * 预设：全部 / 核心 / 账龄焦点
 */
import { ref, computed, watch } from 'vue'

export type K1DetailColKey =
  | 'nature'
  | 'relatedParty'
  | 'beginBalance'
  | 'endBalance'
  | 'agingBands'
  | 'agingTotal'
  | 'stage'
  | 'provision'
  | 'netValue'
  | 'voucherNo'
  | 'conclusion'
  | 'remark'

export type K1DetailColPreset = 'all' | 'core' | 'aging-focus' | 'custom'

export const K1_DETAIL_COL_LABELS: Record<K1DetailColKey, string> = {
  nature: '性质',
  relatedParty: '关联关系',
  beginBalance: '期初余额',
  endBalance: '期末余额',
  agingBands: '账龄各段',
  agingTotal: '账龄合计',
  stage: '减值阶段',
  provision: '坏账准备',
  netValue: '净值',
  voucherNo: '凭证号',
  conclusion: '结论',
  remark: '备注',
}

export const K1_DETAIL_COLS_BY_SEGMENT: Record<'basic' | 'aging' | 'impairment', K1DetailColKey[]> = {
  basic: ['nature', 'relatedParty', 'beginBalance', 'endBalance'],
  aging: ['agingBands', 'agingTotal'],
  impairment: ['stage', 'provision', 'netValue', 'voucherNo', 'conclusion', 'remark'],
}

const ALL_COLS: K1DetailColKey[] = [
  'nature',
  'relatedParty',
  'beginBalance',
  'endBalance',
  'agingBands',
  'agingTotal',
  'stage',
  'provision',
  'netValue',
  'voucherNo',
  'conclusion',
  'remark',
]

const PRESET_COLS: Record<Exclude<K1DetailColPreset, 'custom'>, K1DetailColKey[]> = {
  all: [...ALL_COLS],
  core: ['nature', 'endBalance', 'agingBands', 'agingTotal', 'stage', 'provision', 'netValue'],
  'aging-focus': ['endBalance', 'agingBands', 'agingTotal', 'stage', 'provision'],
}

const STORAGE_KEY = 'K1-2-detail-column-prefs'

export function useK1DetailColumnPrefs() {
  const activePreset = ref<K1DetailColPreset>('all')
  const visibleCols = ref<Set<K1DetailColKey>>(new Set(ALL_COLS))

  function load(): void {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) {
        applyPreset('all')
        return
      }
      const parsed = JSON.parse(raw)
      if (parsed.preset) activePreset.value = parsed.preset
      if (Array.isArray(parsed.cols)) {
        visibleCols.value = new Set(
          parsed.cols.filter((c: string) => ALL_COLS.includes(c as K1DetailColKey)),
        )
        return
      }
    } catch {
      /* fallback */
    }
    applyPreset('all')
  }

  function save(): void {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          preset: activePreset.value,
          cols: Array.from(visibleCols.value),
        }),
      )
    } catch {
      /* ignore */
    }
  }

  function isColVisible(col: K1DetailColKey): boolean {
    return visibleCols.value.has(col)
  }

  function toggleCol(col: K1DetailColKey, visible: boolean): void {
    if (visible) visibleCols.value.add(col)
    else visibleCols.value.delete(col)
    activePreset.value = 'custom'
    visibleCols.value = new Set(visibleCols.value)
    save()
  }

  function applyPreset(name: Exclude<K1DetailColPreset, 'custom'>): void {
    activePreset.value = name
    visibleCols.value = new Set(PRESET_COLS[name])
    save()
  }

  const presetOptions = computed(() => [
    { name: 'all' as const, label: '全部列' },
    { name: 'core' as const, label: '核心列' },
    { name: 'aging-focus' as const, label: '账龄焦点' },
  ])

  load()
  watch(visibleCols, () => save(), { deep: true })

  return {
    activePreset,
    visibleCols,
    presetOptions,
    colLabels: K1_DETAIL_COL_LABELS,
    colsBySegment: K1_DETAIL_COLS_BY_SEGMENT,
    allCols: ALL_COLS,
    isColVisible,
    toggleCol,
    applyPreset,
  }
}

export default useK1DetailColumnPrefs
