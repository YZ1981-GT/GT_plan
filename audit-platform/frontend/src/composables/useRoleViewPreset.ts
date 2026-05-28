/**
 * useRoleViewPreset — 角色视图预设 composable（Role-Based View Switching）
 *
 * 封装视图切换逻辑：localStorage 持久化、排序/过滤/高亮/badge/分组计算。
 *
 * Requirements: 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 7.2, 7.4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { logger } from '@/utils/logger'
import {
  type ViewPresetId,
  type ViewPresetConfig,
  type WpItem,
  type HighlightContext,
  type RowHighlight,
  type BadgeData,
  type GroupedData,
  type SummaryData,
  type PrereqResult,
  type VRResult,
  type ReviewRecord,
  VIEW_PRESET_CONFIG,
  ROLE_DEFAULT_MAP,
  VALID_PRESET_IDS,
} from './viewPresetConfig'

export interface ManualFilters {
  audit_cycle?: string
  status?: string
  preparer?: string
  [key: string]: any
}

/** localStorage key 格式 */
function getStorageKey(userId: string): string {
  return `gt_wp_view_preset_${userId}`
}

/** 校验是否为有效 ViewPresetId */
function isValidPresetId(value: unknown): value is ViewPresetId {
  return typeof value === 'string' && VALID_PRESET_IDS.includes(value as ViewPresetId)
}

/**
 * 根据角色返回默认视图预设
 */
export function getDefaultPreset(role: string): ViewPresetId {
  return ROLE_DEFAULT_MAP[role] ?? 'assistant'
}

/**
 * useRoleViewPreset composable
 *
 * @param projectId - 当前项目 ID
 * @param userId - 当前用户 ID
 * @param wpList - 底稿列表（响应式）
 * @param searchKeyword - 搜索关键词（响应式）
 * @param manualFilters - 手动筛选条件（响应式）
 * @param options - 可选配置
 */
export function useRoleViewPreset(
  projectId: Ref<string>,
  userId: Ref<string>,
  wpList: Ref<WpItem[]>,
  searchKeyword: Ref<string>,
  manualFilters: Ref<ManualFilters>,
  options?: {
    role?: Ref<string>
    prerequisiteStatus?: Ref<Map<string, PrereqResult>>
    consistencyGate?: Ref<Map<string, VRResult>>
    reviewRecords?: Ref<Map<string, ReviewRecord[]>>
  },
) {
  // ─── State ───────────────────────────────────────────────────────────────

  const activePreset = ref<ViewPresetId>(initPreset())

  // ─── Initialization ──────────────────────────────────────────────────────

  function initPreset(): ViewPresetId {
    // 1. 尝试从 localStorage 读取
    try {
      const stored = localStorage.getItem(getStorageKey(userId.value))
      if (stored && isValidPresetId(stored)) {
        return stored
      }
    } catch {
      // localStorage 不可用（隐私模式等），静默忽略
    }

    // 2. 回退到角色默认
    const role = options?.role?.value ?? ''
    return getDefaultPreset(role)
  }

  // ─── Preset Config ───────────────────────────────────────────────────────

  const presetConfig: ComputedRef<ViewPresetConfig> = computed(() => {
    return VIEW_PRESET_CONFIG[activePreset.value]
  })

  // ─── HighlightContext (Task 1.3) ─────────────────────────────────────────

  const highlightContext: ComputedRef<HighlightContext> = computed(() => {
    return {
      prerequisiteStatus: options?.prerequisiteStatus?.value ?? new Map(),
      consistencyGate: options?.consistencyGate?.value ?? new Map(),
      reviewRecords: options?.reviewRecords?.value ?? new Map(),
    }
  })

  // ─── Processed List ──────────────────────────────────────────────────────

  const processedList: ComputedRef<WpItem[]> = computed(() => {
    let list = [...wpList.value]

    // 1. Apply filterFn (质控视图)
    const config = presetConfig.value
    if (config.filterFn) {
      list = list.filter(config.filterFn)
    }

    // 2. Apply sortFn (stable sort via Array.prototype.sort which is stable in modern engines)
    list.sort(config.sortFn)

    // 3. Overlay manualFilters
    const filters = manualFilters.value
    if (filters.audit_cycle) {
      list = list.filter(item => item.audit_cycle === filters.audit_cycle)
    }
    if (filters.status) {
      list = list.filter(item => item.status === filters.status)
    }
    if (filters.preparer) {
      list = list.filter(item => item.preparer === filters.preparer)
    }

    // 4. Apply searchKeyword
    const keyword = searchKeyword.value?.trim().toLowerCase()
    if (keyword) {
      list = list.filter(item =>
        item.wp_code.toLowerCase().includes(keyword) ||
        (item.wp_name && item.wp_name.toLowerCase().includes(keyword)) ||
        (item.title && item.title.toLowerCase().includes(keyword)),
      )
    }

    return list
  })

  // ─── Highlight Map ───────────────────────────────────────────────────────

  const highlightMap: ComputedRef<Map<string, RowHighlight>> = computed(() => {
    const map = new Map<string, RowHighlight>()
    const config = presetConfig.value
    const ctx = highlightContext.value

    if (config.highlightRules.length === 0) return map

    for (const item of wpList.value) {
      for (const rule of config.highlightRules) {
        if (rule.condition(item, ctx)) {
          const existing = map.get(item.id)
          const highlight: RowHighlight = {
            style: existing
              ? { ...existing.style, ...rule.style }
              : { ...rule.style },
            tooltip: rule.tooltip ? rule.tooltip(item, ctx) : existing?.tooltip,
          }
          map.set(item.id, highlight)
        }
      }
    }

    return map
  })

  // ─── Badge Map ───────────────────────────────────────────────────────────

  const badgeMap: ComputedRef<Map<string, BadgeData>> = computed(() => {
    const map = new Map<string, BadgeData>()
    const config = presetConfig.value

    if (!config.badgeRules || config.badgeRules.length === 0) return map

    for (const item of wpList.value) {
      for (const rule of config.badgeRules) {
        const val = rule.value(item)
        if (rule.visible(val)) {
          map.set(item.id, {
            value: val,
            type: rule.type(val),
            visible: true,
          })
        }
      }
    }

    return map
  })

  // ─── Grouped List (经理视图) ─────────────────────────────────────────────

  /** 折叠状态缓存 */
  const collapseState = ref<Map<string, boolean>>(new Map())

  const groupedList: ComputedRef<GroupedData[] | null> = computed(() => {
    const config = presetConfig.value
    if (!config.groupBy) return null

    const groups = new Map<string, WpItem[]>()

    // 使用 processedList（已排序+已过滤）
    for (const item of processedList.value) {
      const key = config.groupBy(item)
      if (!groups.has(key)) {
        groups.set(key, [])
      }
      groups.get(key)!.push(item)
    }

    const result: GroupedData[] = []
    for (const [key, items] of groups) {
      const completed = items.filter(i =>
        i.status === 'completed' || i.status === 'reviewed',
      ).length
      const total = items.length
      const progress = total > 0 ? Math.round((completed / total) * 100) : 0
      const trimmedCount = items.filter(i => i.status === 'trimmed' || i.is_trimmed).length

      // 折叠逻辑：进度 < 100% 展开，100% 折叠（用户手动切换优先）
      const userCollapsed = collapseState.value.get(key)
      const defaultCollapsed = progress >= 100
      const collapsed = userCollapsed !== undefined ? userCollapsed : defaultCollapsed

      result.push({
        key,
        label: key || '未分类',
        items,
        progress,
        total,
        completed,
        trimmedCount,
        collapsed,
      })
    }

    return result
  })

  // ─── Summary Data ────────────────────────────────────────────────────────

  const summaryData: ComputedRef<SummaryData | null> = computed(() => {
    const config = presetConfig.value
    if (!config.summaryFn) return null
    return config.summaryFn(processedList.value, highlightContext.value)
  })

  // ─── Actions ─────────────────────────────────────────────────────────────

  /**
   * 切换视图预设
   * - 更新 activePreset
   * - 写入 localStorage
   */
  function switchPreset(id: ViewPresetId): void {
    if (!isValidPresetId(id)) return

    const prev = activePreset.value
    activePreset.value = id

    // 写入 localStorage
    try {
      localStorage.setItem(getStorageKey(userId.value), id)
    } catch (e) {
      console.warn('[useRoleViewPreset] localStorage 写入失败，降级为内存态', e)
    }

    // Debug log
    logger.log('[useRoleViewPreset] 视图切换', {
      from: prev,
      to: id,
      userId: userId.value,
      timestamp: new Date().toISOString(),
    })
  }

  /**
   * 切换分组折叠状态（经理视图）
   */
  function toggleGroupCollapse(groupKey: string): void {
    const current = collapseState.value.get(groupKey)
    const newState = new Map(collapseState.value)
    newState.set(groupKey, !current)
    collapseState.value = newState
  }

  // ─── Watch userId changes → re-init ──────────────────────────────────────

  watch(userId, () => {
    activePreset.value = initPreset()
  })

  // ─── Return ──────────────────────────────────────────────────────────────

  return {
    activePreset,
    presetConfig,
    processedList,
    highlightMap,
    badgeMap,
    groupedList,
    summaryData,
    switchPreset,
    getDefaultPreset,
    toggleGroupCollapse,
  }
}
