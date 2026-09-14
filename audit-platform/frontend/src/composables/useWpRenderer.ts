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
import { resolveSheetNameByDeepLink } from '@/utils/normalizeSheetName'
import type { SheetContentType } from '@/types/workpaperSemanticContract'
import type { WpComponentType } from '@/types/componentCapabilities.generated'
import type { RenderConfig, SheetRenderConfig } from '@/types/renderConfig'
import { projectSheetUid } from './sheetUidProjection'

export type { WpComponentType } from '@/types/componentCapabilities.generated'
export type {
  CrossRefEntry,
  RenderConfig,
  RenderConfigWire,
  SheetRenderConfig,
  SheetRenderConfigWire,
} from '@/types/renderConfig'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

/** Guidance、公式与宿主导航共享的结构化 sheet 上下文。 */
export interface WorkpaperSheetContext {
  sheetName: string
  sheetCode: string | null
  /** G-ID stable uid from render-config; never invented from display name. */
  sheetUid: string | null
  sheetUidNullReason: string | null
  host: 'html' | 'univer' | 'onlyoffice'
  wholeWorkbook: boolean
  /** Race stamps from HtmlStableContextEmitter (or Univer/OO host bridge). */
  ownerEpoch?: number
  contextRevision?: number
}

export interface EngineSheetIdentity {
  id: string
  name: string
}

/**
 * 从 render-config 的可见 sheet 中解析定位器。
 * 初始 deep-link、页签、导航和 locate 共用同一名称归一化规则。
 */
export function resolveRenderSheet(
  sheets: readonly SheetRenderConfig[],
  locator: string | null | undefined,
): SheetRenderConfig | null {
  const resolvedName = resolveSheetNameByDeepLink(
    sheets.map((sheet) => sheet.sheet_name),
    locator,
  )
  if (!resolvedName) return null
  return sheets.find((sheet) => sheet.sheet_name === resolvedName) ?? null
}

/** 将后端 sheet identity 投影为 HTML/OnlyOffice 的统一宿主 context。 */
export function resolveWorkpaperSheetContext(
  configWpId: string | null | undefined,
  expectedWpId: string,
  sheetName: string,
  sheet: SheetRenderConfig | null | undefined,
  wholeWorkbook = false,
  parentWpCode: string | null | undefined = null,
): WorkpaperSheetContext | null {
  if (!configWpId || configWpId !== expectedWpId || !sheetName) return null
  const isWholeWorkbook = wholeWorkbook || sheet?.whole_workbook === true
  const isOnlyOffice = isWholeWorkbook
    || sheet?.componentType === 'onlyoffice-sheet'
    || sheet?.html_data?.onlyoffice === true
  const sheetCode = isWholeWorkbook ? null : (sheet?.sheet_code ?? null)
  const wpCode = parentWpCode?.trim() || ''
  const projected = projectSheetUid({
    parentWpCode: wpCode,
    sheetCode,
    sheetName,
    wholeWorkbook: isWholeWorkbook,
    explicitUid: sheet?.sheet_uid,
    codeReason: sheet?.sheet_uid_null_reason || sheet?.sheet_code_reason,
  })
  // Prefer server-annotated uid when present; client projection is fallback only.
  const sheetUid = sheet?.sheet_uid?.trim() || projected.sheetUid
  const sheetUidNullReason = sheetUid
    ? null
    : (sheet?.sheet_uid_null_reason ?? projected.nullReason)
  return {
    sheetName,
    sheetCode,
    sheetUid,
    sheetUidNullReason,
    host: isOnlyOffice ? 'onlyoffice' : 'html',
    wholeWorkbook: isWholeWorkbook,
  }
}

/** Univer 的 engine sheet id 先映射真实名称，再消费 render-config 的 canonical uid/code。 */
export function resolveUniverSheetContext(
  engineSheets: readonly EngineSheetIdentity[],
  activeSheetId: string | null | undefined,
  renderSheets: readonly SheetRenderConfig[],
  parentWpCode: string | null | undefined = null,
): WorkpaperSheetContext | null {
  if (!activeSheetId) return null
  const engineSheet = engineSheets.find((sheet) => sheet.id === activeSheetId)
  if (!engineSheet) return null
  const renderSheet = resolveRenderSheet(renderSheets, engineSheet.name)
  const sheetName = renderSheet?.sheet_name ?? engineSheet.name
  const sheetCode = renderSheet?.sheet_code ?? null
  const wpCode = parentWpCode?.trim() || ''
  const projected = projectSheetUid({
    parentWpCode: wpCode,
    sheetCode,
    sheetName,
    wholeWorkbook: false,
    explicitUid: renderSheet?.sheet_uid,
    codeReason: renderSheet?.sheet_uid_null_reason || renderSheet?.sheet_code_reason,
  })
  const sheetUid = renderSheet?.sheet_uid?.trim() || projected.sheetUid
  const sheetUidNullReason = sheetUid
    ? null
    : (renderSheet?.sheet_uid_null_reason ?? projected.nullReason)
  return {
    sheetName,
    sheetCode,
    sheetUid,
    sheetUidNullReason,
    host: 'univer',
    wholeWorkbook: false,
  }
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
