/**
 * useH8DetailColumnPrefs — H8-2 明细表列显示偏好（原值/折旧/减值区共用）
 *
 * 预设：
 * - core（核心）：未审期初/增减/期末 + 审定（隐藏期初调整与账项调整细列）
 * - full（完整）：全部列
 * localStorage 持久化；不改数据模型，仅 UI v-if
 */
import { ref, computed } from 'vue'

export type H82ColGroup = 'unadj' | 'openAdj' | 'aje' | 'audited'
export type H82ColPreset = 'core' | 'full' | 'custom'

export const H82_COL_GROUP_LABELS: Record<H82ColGroup, string> = {
  unadj: '未审数（期初/增减/期末）',
  openAdj: '期初调整',
  aje: '账项调整细列',
  audited: '审定数',
}

const ALL_GROUPS: H82ColGroup[] = ['unadj', 'openAdj', 'aje', 'audited']

const PRESET_GROUPS: Record<Exclude<H82ColPreset, 'custom'>, H82ColGroup[]> = {
  core: ['unadj', 'audited'],
  full: [...ALL_GROUPS],
}

const STORAGE_KEY = 'H8-2-detail-column-prefs'

export function useH8DetailColumnPrefs() {
  const activePreset = ref<H82ColPreset>('core')
  const visibleGroups = ref<Set<H82ColGroup>>(new Set(PRESET_GROUPS.core))

  function load(): void {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) {
        applyPreset('core')
        return
      }
      const parsed = JSON.parse(raw)
      if (parsed.preset === 'core' || parsed.preset === 'full' || parsed.preset === 'custom') {
        activePreset.value = parsed.preset
      }
      if (Array.isArray(parsed.groups)) {
        visibleGroups.value = new Set(
          parsed.groups.filter((g: string) => ALL_GROUPS.includes(g as H82ColGroup)),
        )
        if (!visibleGroups.value.size) applyPreset('core')
        return
      }
    } catch { /* fallback */ }
    applyPreset('core')
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
    } catch { /* ignore */ }
  }

  function isGroupVisible(group: H82ColGroup): boolean {
    // 身份列始终显示；未审/审定至少显示其一
    return visibleGroups.value.has(group)
  }

  function toggleGroup(group: H82ColGroup, visible: boolean): void {
    if (visible) visibleGroups.value.add(group)
    else visibleGroups.value.delete(group)
    // 至少保留未审或审定
    if (!visibleGroups.value.has('unadj') && !visibleGroups.value.has('audited')) {
      visibleGroups.value.add('unadj')
    }
    activePreset.value = 'custom'
    visibleGroups.value = new Set(visibleGroups.value)
    save()
  }

  function applyPreset(name: Exclude<H82ColPreset, 'custom'>): void {
    activePreset.value = name
    visibleGroups.value = new Set(PRESET_GROUPS[name])
    save()
  }

  const presetOptions = computed(() => [
    { name: 'core' as const, label: '核心列', description: '未审+审定（隐藏调整细列）' },
    { name: 'full' as const, label: '完整列', description: '含期初调整与账项调整' },
  ])

  load()

  return {
    activePreset,
    visibleGroups,
    presetOptions,
    groupLabels: H82_COL_GROUP_LABELS,
    allGroups: ALL_GROUPS,
    isGroupVisible,
    toggleGroup,
    applyPreset,
  }
}

export default useH8DetailColumnPrefs
