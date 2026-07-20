/**
 * useF1DetailColumnPrefs — F1-2 明细表列显示偏好（对齐 D2 列设置思路，精简版）
 *
 * - 预设：全部 / 核心 / 审定+账龄
 * - 分组 checkbox + localStorage 持久化
 * - 不改变数据模型，仅 UI v-if
 */
import { ref, computed, watch, type Ref } from 'vue'

export type F1ColGroup =
  | 'prior'
  | 'priorAging'
  | 'movement'
  | 'current'
  | 'currentAging'
  | 'adjust'
  | 'audited'
  | 'auditedAging'
  | 'meta'

export type F1ColPreset = 'all' | 'core' | 'audited-aging' | 'custom'

export const F1_COL_GROUP_LABELS: Record<F1ColGroup, string> = {
  prior: '期初金额',
  priorAging: '期初账龄',
  movement: '本期发生',
  current: '期末未审',
  currentAging: '期末未审账龄',
  adjust: '期末调整',
  audited: '期末审定',
  auditedAging: '期末审定账龄',
  meta: '函证/期后/备注',
}

const ALL_GROUPS: F1ColGroup[] = [
  'prior',
  'priorAging',
  'movement',
  'current',
  'currentAging',
  'adjust',
  'audited',
  'auditedAging',
  'meta',
]

const PRESET_GROUPS: Record<Exclude<F1ColPreset, 'custom'>, F1ColGroup[]> = {
  all: [...ALL_GROUPS],
  core: ['movement', 'audited', 'meta'],
  'audited-aging': ['audited', 'auditedAging'],
}

const STORAGE_KEY = 'F1-detail-column-prefs'

export function useF1DetailColumnPrefs(_options?: { isReadonly?: Ref<boolean> }) {
  const activePreset = ref<F1ColPreset>('all')
  const visibleGroups = ref<Set<F1ColGroup>>(new Set(ALL_GROUPS))

  function load(): void {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) {
        applyPreset('all')
        return
      }
      const parsed = JSON.parse(raw)
      if (parsed.preset) activePreset.value = parsed.preset
      if (Array.isArray(parsed.groups)) {
        visibleGroups.value = new Set(parsed.groups.filter((g: string) => ALL_GROUPS.includes(g as F1ColGroup)))
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
          groups: Array.from(visibleGroups.value),
        }),
      )
    } catch {
      /* ignore quota */
    }
  }

  function isGroupVisible(group: F1ColGroup): boolean {
    return visibleGroups.value.has(group)
  }

  function toggleGroup(group: F1ColGroup, visible: boolean): void {
    if (visible) visibleGroups.value.add(group)
    else visibleGroups.value.delete(group)
    activePreset.value = 'custom'
    // trigger reactivity
    visibleGroups.value = new Set(visibleGroups.value)
    save()
  }

  function applyPreset(name: Exclude<F1ColPreset, 'custom'> | 'all'): void {
    const preset = name === 'all' ? 'all' : name
    activePreset.value = preset
    visibleGroups.value = new Set(PRESET_GROUPS[preset])
    save()
  }

  const presetOptions = computed(() => [
    { name: 'all' as const, label: '全部列', description: '显示完整宽表' },
    { name: 'core' as const, label: '核心列', description: '发生额+审定+函证期后' },
    { name: 'audited-aging' as const, label: '审定+账龄', description: '期末审定及审定账龄' },
  ])

  load()

  watch(visibleGroups, () => save(), { deep: true })

  return {
    activePreset,
    visibleGroups,
    presetOptions,
    groupLabels: F1_COL_GROUP_LABELS,
    allGroups: ALL_GROUPS,
    isGroupVisible,
    toggleGroup,
    applyPreset,
  }
}

export default useF1DetailColumnPrefs
