/**
 * useWpRenderer — 底稿 HTML 渲染器顶层数据加载 composable
 *
 * 职责：
 * 1. 从 GET /api/workpapers/{wpId}/render-config 加载渲染配置
 * 2. 派生 componentType（9 类路由分发）
 * 3. 订阅 cross-ref:updated 事件，跨底稿引用变化时自动刷新
 * 4. onUnmounted 清理事件监听
 *
 * ─── cross-ref:updated 订阅契约（Task 13.2）──────────────────────────────────
 *
 * **传播架构（A~E 全 HTML 类共用）**：
 *
 *   1. 上游底稿（如 D0 函证）保存 cell 变化
 *      → 后端 cross_ref_service.detect_changes 比对 cross_wp_references.json
 *      → 发布 SSE cross_ref.updated（含 targetWpCode）
 *
 *   2. 前端某处（useDCycleEditor / WorkpaperEditor.onHtmlCrossRefUpdate / SSE bridge）
 *      → eventBus.emit('cross-ref:updated', { projectId, targetWpCode, ... })
 *
 *   3. **本 composable** 监听该事件，targetWpCode 命中当前 renderConfig.wp_code 时
 *      → 调用 load() 重拉 renderConfig
 *      → GtWpRenderer 接到新 renderConfig 后重新分发到 A/B/C/D/E 子组件
 *      → 子组件通过 props 拿到新 htmlData，**无需自身订阅**
 *
 * **为什么 A~E 子组件不单独订阅？**
 * - GtWpRenderer 是单一订阅入口，避免 N 个子组件重复订阅 + 清理失误风险
 * - 子组件保持纯展示职责（props in / emits out），逻辑解耦
 * - 复用既有 useStaleImpact composable（WorkpaperEditor 已接入）做 Layer 4 联动
 *
 * **onUnmounted 清理纪律**（design §8.2.4 强制要求）：
 * 任何订阅 cross-ref:updated 的 composable 必须在 onUnmounted off 监听器避免内存泄漏。
 * 本 composable 已遵守；useDCycleEditor 同样遵守；F/G Univer 类继续走自身 SSE 通道。
 *
 * @example
 * const wpId = computed(() => route.params.id as string)
 * const { renderConfig, loading, error, componentType, reload } = useWpRenderer(wpId)
 *
 * Validates: Requirements 1.2（路由分发）+ 3.11.4（跨底稿引用传播）+ 3.11.5（联动 4 层架构）
 */
import { ref, computed, onMounted, onUnmounted, watch, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { eventBus, type CrossRefUpdatedPayload } from '@/utils/eventBus'
import type { SheetContentType, FieldSourceContract } from '@/types/workpaperSemanticContract'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

/** componentType 白名单（9 类 + univer + skip） */
export type WpComponentType =
  | 'a-program-console'
  | 'b-index'
  | 'c-note-table'
  | 'd-form-table'
  | 'd-form-paragraph'
  | 'd-form-qa'
  | 'd-form-confirmation'
  | 'd-form-review'
  | 'e-control-test'
  | 'h-static-doc'
  | 'custom'
  | 'audit-sheet'
  | 'bad-debt-sheet'
  | 'univer'
  | 'skip'

/** 跨底稿引用条目 */
export interface CrossRefEntry {
  wp_code: string
  cell: string
}

/** 单 sheet 渲染配置 */
export interface SheetRenderConfig {
  sheet_name: string
  componentType: WpComponentType
  schema: Record<string, any>
  html_data: Record<string, any>
  cross_refs: CrossRefEntry[]
  /** Task 2.3: sheet 的业务语义类型（schema 显式 > 后端推断 > 前端启发式） */
  sheet_type?: SheetContentType
  /** Task 2.3: 关键字段来源契约映射 */
  field_sources?: Record<string, FieldSourceContract>
  /** Task 2.3: 关联程序状态引用（program_code 列表） */
  program_status_refs?: string[]
}

/** render-config 端点完整响应 */
export interface RenderConfig {
  wp_id: string
  wp_code: string
  project_id: string
  scope: 'standalone' | 'consolidated' | 'parent_only' | 'both'
  is_real_workpaper: boolean
  template_version: string
  sheets: SheetRenderConfig[]
  /** Sprint 4 Task 16: 自动刷数结果 */
  fill_results?: Record<string, {
    value: number | string | null
    source: string
    label: string
    status: 'ok' | 'unavailable'
  }>
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * resolveSheetType — 按优先级确定 sheet 的业务语义类型
 *
 * 优先级: schema 显式值 > 后端推断(API 返回) > 前端启发式 > 'unknown'
 *
 * 这是一个纯函数，可在 composable 外部直接使用。
 *
 * @param sheet - 渲染配置中的单 sheet 对象
 * @returns 解析后的 SheetContentType
 *
 * Validates: Requirements 1.2, 1.3（schema 优先，启发式回退）
 */
export function resolveSheetType(sheet: SheetRenderConfig): SheetContentType {
  // 1. schema 显式值（已由后端从 YAML 提取并放入 sheet_type 字段）
  //    或后端通过启发式推断后放入 sheet_type
  if (sheet.sheet_type) {
    return sheet.sheet_type
  }

  // 2. 前端启发式：根据 sheet_name 中文关键词推断
  const name = sheet.sheet_name || ''
  const heuristic = _detectSheetTypeByName(name)
  if (heuristic) {
    return heuristic
  }

  // 3. 无法确定
  return 'unknown'
}

/**
 * 前端启发式：根据 sheet_name 中文关键词推断 sheet_type。
 * 与后端 _infer_sheet_type_by_heuristic 保持同口径。
 */
function _detectSheetTypeByName(name: string): SheetContentType | null {
  // 顺序很重要：更具体的关键词优先匹配
  if (name.includes('函证') || name.includes('询证')) return 'confirmation_summary'
  if (name.includes('控制测试')) return 'control_test'
  if (name.includes('内控') && name.includes('了解')) return 'control_understanding'
  if (name.includes('控制') && name.includes('了解')) return 'control_understanding'
  if (name.includes('控制') && name.includes('测试')) return 'control_test'
  if (name.includes('审定') || name.includes('汇总')) return 'audit_sheet'
  if (name.includes('明细') || name.includes('清单')) return 'detail_table'
  if (name.includes('分析') || name.includes('测算') || name.includes('复核')) return 'analysis'
  if (name.includes('程序')) return 'procedure'
  if (name.includes('调整')) return 'adjustment'
  if (name.includes('披露') || name.includes('附注')) return 'disclosure'
  if (name.includes('结论')) return 'conclusion'
  if (name.includes('目录') || name.includes('索引') || name.includes('驾驶') || name.includes('控制台')) return 'control_panel'
  return null
}

export function useWpRenderer(wpId: Ref<string>) {
  const renderConfig = ref<RenderConfig | null>(null)
  const loading = ref(true)
  const error = ref<Error | null>(null)

  /** 顶层 componentType 派生（取第一个 sheet 的 componentType，无数据时 skip） */
  const componentType = computed<WpComponentType>(() => {
    if (!renderConfig.value || !renderConfig.value.sheets.length) return 'skip'
    return renderConfig.value.sheets[0].componentType ?? 'skip'
  })

  /** 当前底稿的 wp_code（用于 cross-ref 匹配） */
  const wpCode = computed(() => renderConfig.value?.wp_code ?? '')

  /** 加载渲染配置 */
  async function load() {
    const id = wpId.value
    if (!id) {
      error.value = new Error('底稿 ID 为空')
      loading.value = false
      return
    }

    loading.value = true
    error.value = null
    try {
      const res = await api.get<RenderConfig>(`/api/workpapers/${id}/render-config`)
      renderConfig.value = res
    } catch (e) {
      error.value = e as Error
      renderConfig.value = null
    } finally {
      loading.value = false
    }
  }

  /** SSE 订阅回调：跨底稿引用变化时刷新（覆盖 A~E HTML 类全部子组件，子组件无需自订阅） */
  function onCrossRefUpdated(payload: CrossRefUpdatedPayload) {
    if (!renderConfig.value) return
    // 当目标底稿是当前底稿时，重新拉取最新引用值
    if (payload.targetWpCode === renderConfig.value.wp_code) {
      load()
    }
  }

  onMounted(() => {
    load()
    // Task 13.2: A~E 类组件统一通过此处订阅，避免每个子组件重复挂监听器
    eventBus.on('cross-ref:updated', onCrossRefUpdated)
  })

  onUnmounted(() => {
    // design §8.2.4: 必须 off 避免内存泄漏
    eventBus.off('cross-ref:updated', onCrossRefUpdated)
  })

  // 监听 wpId 变化自动重新加载（支持路由切换底稿）
  watch(wpId, (newId, oldId) => {
    if (newId !== oldId && newId) {
      load()
    }
  })

  return {
    renderConfig,
    loading,
    error,
    componentType,
    wpCode,
    reload: load,
    /** Sprint 4 Task 16: 自动刷数结果 */
    fillResults: computed(() => renderConfig.value?.fill_results ?? null),
    /** Sprint 4 Task 10.1: schema 缺失时的 fallback 提示（A~E 类但 componentType 为 univer） */
    schemaFallbackBanner: computed(() => {
      if (!renderConfig.value) return null
      const wpCodeVal = renderConfig.value.wp_code
      if (wpCodeVal && /^[A-E]/i.test(wpCodeVal) && componentType.value === 'univer') {
        return '此底稿推荐使用 HTML 渲染器，当前因配置未就绪暂用表格模式'
      }
      return null
    }),
  }
}
