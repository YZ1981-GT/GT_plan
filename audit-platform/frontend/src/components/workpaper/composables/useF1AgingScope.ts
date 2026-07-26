/**
 * useF1AgingScope — F1 预付账款账龄口径**单一真源**
 *
 * 背景（修复前的双真源缺陷）：
 * - F1-2 明细表支持**表级**账龄枚举覆盖（3年段/5年段/自定义，持久化 `F1-det-aging-preset`）；
 * - 但 F1-1 审定表 / useF1CrossSheet / 附注披露 / F1-4 / F1-5 / F1-6 各自读**项目级**
 *   `useAgingConfig(projectId,'F1')` → 表级切到 5 年段后，审定表账龄行仍按 3 年段
 *   （`over3` 读不到 `y3to4/y4to5/over5`）→ 3 年以上金额在审定表/附注凭空消失、
 *   超 1 年筛选（F1-5 长期挂款 / 附注超 1 年重要项）漏行、性质≠账龄假告警。
 *
 * 本 composable 把「表级枚举覆盖 > 项目级配置 > 科目默认 THREE_YEAR」收敛为一处解析，
 * 由 F1 主入口装配一次后注入全部消费方（crossSheet / 审定表 / 披露 / 长期 / 关联方 / 分析），
 * 保证同一底稿内所有账龄区块口径一致。
 *
 * 与后端 `_f1_import_export._resolve_f1_segments` 同口径（导入导出列头随表级覆盖）。
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import {
  useAgingConfig,
  PRESET_SEGMENTS,
  type AgingPreset,
  type AgingSegment,
} from '@/composables/useAgingConfig'
import type { ChecklistResponse } from './useF1FormData'

/** 表级账龄口径覆盖（空=跟随项目配置） */
export const F1_AGING_PRESET_ITEM_ID = 'F1-det-aging-preset'
/** 表级自定义段标签（JSON 字符串数组，2-10 段） */
export const F1_AGING_CUSTOM_ITEM_ID = 'F1-det-aging-custom-segments'

export interface UseF1AgingScopeOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  projectId: Ref<string>
  debouncedSave?: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly?: Ref<boolean>
}

export interface F1AgingScope {
  /** 当前生效预设（表级覆盖优先） */
  preset: ComputedRef<AgingPreset>
  /** 当前生效账龄段（唯一真源） */
  segments: ComputedRef<AgingSegment[]>
  /** 表级自定义段（仅 CUSTOM 生效时非空） */
  customSegments: Ref<AgingSegment[]>
  /** 是否存在表级覆盖（true 时不跟随项目全局账龄变更） */
  hasSheetOverride: ComputedRef<boolean>
  /** 切换表级账龄口径；CUSTOM 需 ≥2 段标签，返回是否生效 */
  setPreset: (preset: AgingPreset, customLabels?: string[]) => boolean
}

/** 自定义标签 → segments（key 与后端 `custom-{i}` 一致） */
export function labelsToCustomSegments(labels: string[]): AgingSegment[] {
  return labels.map((label, i) => ({
    key: `custom-${i}`,
    label,
    dayFrom: 0,
    dayTo: null,
  }))
}

/** 解析持久化的自定义标签 JSON（非法/空 → []） */
export function parseCustomLabels(raw: string | null | undefined): string[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map((x) => String(x || '').trim()).filter(Boolean)
  } catch {
    return []
  }
}

/**
 * 纯函数：解析 F1 有效账龄段（供单测；与 composable computed 同逻辑）。
 */
export function resolveF1Segments(
  sheetPreset: '' | AgingPreset,
  sheetCustom: AgingSegment[],
  projectPreset: AgingPreset | undefined,
  projectSegments: AgingSegment[],
): AgingSegment[] {
  if (sheetPreset === 'CUSTOM') {
    if (sheetCustom.length >= 2) return sheetCustom
    if (projectPreset === 'CUSTOM' && projectSegments.length >= 2) return projectSegments
    return PRESET_SEGMENTS.THREE_YEAR
  }
  if (sheetPreset === 'THREE_YEAR' || sheetPreset === 'FIVE_YEAR') {
    return PRESET_SEGMENTS[sheetPreset]
  }
  if (projectSegments.length) return projectSegments
  return PRESET_SEGMENTS.THREE_YEAR
}

export function useF1AgingScope(options: UseF1AgingScopeOptions): F1AgingScope {
  const { allResponses, projectId, debouncedSave, isReadonly } = options

  const { segments: projectSegments, preset: projectPreset } = useAgingConfig(projectId, 'F1')

  const sheetPreset = ref<'' | AgingPreset>('')
  const customSegments = ref<AgingSegment[]>([])

  watch(
    () => allResponses.value.get(F1_AGING_PRESET_ITEM_ID)?.remark,
    (v) => {
      const raw = String(v || '').trim().toUpperCase()
      sheetPreset.value =
        raw === 'THREE_YEAR' || raw === 'FIVE_YEAR' || raw === 'CUSTOM' ? (raw as AgingPreset) : ''
    },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(F1_AGING_CUSTOM_ITEM_ID)?.remark,
    (v) => {
      const labels = parseCustomLabels(v)
      customSegments.value = labels.length >= 2 ? labelsToCustomSegments(labels) : []
    },
    { immediate: true },
  )

  const preset: ComputedRef<AgingPreset> = computed(() => {
    if (sheetPreset.value) return sheetPreset.value
    const p = projectPreset.value
    if (p === 'THREE_YEAR' || p === 'FIVE_YEAR' || p === 'CUSTOM') return p
    return 'THREE_YEAR'
  })

  const segments: ComputedRef<AgingSegment[]> = computed(() =>
    resolveF1Segments(
      sheetPreset.value,
      customSegments.value,
      projectPreset.value,
      projectSegments.value,
    ),
  )

  const hasSheetOverride: ComputedRef<boolean> = computed(() => !!sheetPreset.value)

  function setPreset(next: AgingPreset, customLabels?: string[]): boolean {
    if (isReadonly?.value) return false
    if (next === 'CUSTOM') {
      const labels = (customLabels || customSegments.value.map((s) => s.label))
        .map((x) => String(x || '').trim())
        .filter(Boolean)
      if (labels.length < 2) return false
      const segs = labelsToCustomSegments(labels.slice(0, 10))
      sheetPreset.value = 'CUSTOM'
      customSegments.value = segs
      debouncedSave?.(F1_AGING_PRESET_ITEM_ID, { remark: 'CUSTOM' })
      debouncedSave?.(F1_AGING_CUSTOM_ITEM_ID, { remark: JSON.stringify(labels.slice(0, 10)) })
      return true
    }
    sheetPreset.value = next
    customSegments.value = []
    debouncedSave?.(F1_AGING_PRESET_ITEM_ID, { remark: next })
    debouncedSave?.(F1_AGING_CUSTOM_ITEM_ID, { remark: '[]' })
    return true
  }

  return { preset, segments, customSegments, hasSheetOverride, setPreset }
}

export default useF1AgingScope
