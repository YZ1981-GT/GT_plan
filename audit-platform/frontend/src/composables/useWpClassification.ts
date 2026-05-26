/**
 * useWpClassification — 底稿 9 类归属 + scope 路由判定 composable
 *
 * 职责：
 * 1. 从 GET /api/wp-classifications 加载底稿归类信息
 * 2. 派生 componentType（9 类 + scope 路由委派）
 * 3. 派生 isRealWorkpaper / excludeFromArchive 布尔标记
 *
 * @example
 * const wpCode = computed(() => renderConfig.value?.wp_code ?? '')
 * const projectId = computed(() => route.params.projectId as string)
 * const { classification, componentType, isRealWorkpaper, excludeFromArchive, load } = useWpClassification(wpCode, projectId)
 *
 * Validates: Requirements 1.2（9 类路由）+ 3.0.2（真假底稿）+ 3.0.5（合并剔除 scope）
 */
import { ref, computed, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import type { WpComponentType } from '@/composables/useWpRenderer'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

/** scope 路由委派类型（合并/母公司专属底稿委派给独立模块） */
export type WpScopeRouteType = 'delegate-consolidation' | 'delegate-parent-view'

/** 完整 componentType 联合（9 类 + scope 委派） */
export type WpClassificationComponentType = WpComponentType | WpScopeRouteType

/** 单 sheet 归类条目（对应后端 ClassificationItem） */
export interface ClassificationItem {
  sheet_name: string
  class_code: string | null
  componentType: string
  scope: 'standalone' | 'consolidated' | 'parent_only' | 'both'
  is_real_workpaper: boolean
  exclude_from_archive: boolean
  delegated_module: string | null
  has_override: boolean
}

/** GET /api/wp-classifications 完整响应 */
export interface ClassificationResult {
  wp_code: string
  project_id: string
  classifications: ClassificationItem[]
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useWpClassification(wpCode: Ref<string>, projectId: Ref<string>) {
  const classification = ref<ClassificationResult | null>(null)
  const loading = ref(false)
  const error = ref<Error | null>(null)

  /** 加载归类信息 */
  async function load() {
    const code = wpCode.value
    const pid = projectId.value
    if (!code || !pid) return

    loading.value = true
    error.value = null
    try {
      const res = await api.get<ClassificationResult>('/api/wp-classifications', {
        params: { wp_code: code, project_id: pid },
      })
      classification.value = res
    } catch (e) {
      error.value = e as Error
      classification.value = null
    } finally {
      loading.value = false
    }
  }

  /**
   * 顶层 componentType 派生（取第一个 sheet 的归类 + scope 路由判定）
   *
   * 优先级：
   * 1. scope === 'consolidated' → 委派给合并模块
   * 2. scope === 'parent_only' → 委派给母公司视图
   * 3. 其他 → 按 9 类映射返回 componentType
   */
  const componentType = computed<WpClassificationComponentType>(() => {
    const c = classification.value
    if (!c || !c.classifications.length) return 'skip'

    const first = c.classifications[0]

    // scope 路由：合并/母公司专属 → 委派给独立模块
    if (first.scope === 'consolidated') return 'delegate-consolidation'
    if (first.scope === 'parent_only') return 'delegate-parent-view'

    // 9 类映射（后端已派生 componentType）
    return (first.componentType as WpClassificationComponentType) ?? 'skip'
  })

  /** 是否为真底稿（默认 true，假底稿不计入完成率） */
  const isRealWorkpaper = computed(() => {
    const c = classification.value
    if (!c || !c.classifications.length) return true
    return c.classifications[0].is_real_workpaper
  })

  /** 是否排除归档（默认 false） */
  const excludeFromArchive = computed(() => {
    const c = classification.value
    if (!c || !c.classifications.length) return false
    return c.classifications[0].exclude_from_archive ?? false
  })

  return {
    classification,
    loading,
    error,
    componentType,
    isRealWorkpaper,
    excludeFromArchive,
    load,
  }
}
