/**
 * useS32BundleState — S32 舞弊核查聚合组件跨 Tab 业务状态管理
 *
 * Spec: .kiro/specs/s32-fraud-response-bundle/  Tasks 3.1 / 3.2
 * Requirements: 5.1, 5.2, 7.1
 *
 * 职责（对齐 useC22BundleState / useA1SubWorkpapers 模式）：
 * 1. wpIdMap：S32-1~S32-13 → wp_id（通过 wp_index 解析）
 * 2. visibleTabs：仅 wpIdMap 有值的舞弊情形 Tab 可见
 * 3. completionMap：各底稿程序完成状态推导 CompletionStatus
 * 4. progressSummary：完成/进行中/未开始计数
 * 5. refreshCompletion：刷新某/全底稿完成状态
 *
 * 🔴 铁律：wpIdMap 必须用 item.wp_id 不能用 item.id
 *
 * 仅做数据读取与状态推导，不做数据写入。
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { getWpIndex } from '@/services/workpaperApi'
import { api } from '@/services/apiProxy'
import { S32_FRAUD_TABS, type S32TabDef } from './S32_TAB_CONFIG'

// ─── Types (exported for testability) ───

export type CompletionStatus = 'completed' | 'in_progress' | 'not_started'

export interface ProgressSummary {
  completed: number
  inProgress: number
  notStarted: number
}

/** checklist_responses 精简形态 */
export interface ChecklistResponse {
  item_id: string
  conclusion?: string | null
  remark?: string | null
}

export interface UseS32BundleStateOptions {
  projectId: Ref<string>
}

export interface UseS32BundleStateReturn {
  /** S32-x wp_code → wp_id 映射 */
  wpIdMap: ComputedRef<Record<string, string>>
  /** 仅 wpIdMap 有值的舞弊情形 Tab（驱动 el-tabs 渲染） */
  visibleTabs: ComputedRef<S32TabDef[]>
  /** 各底稿完成状态 */
  completionMap: ComputedRef<Record<string, CompletionStatus>>
  /** 进度汇总 */
  progressSummary: ComputedRef<ProgressSummary>
  /** 加载状态 */
  loading: Ref<boolean>
  /** 加载 wp_index 解析 wpIdMap */
  loadWpIndex: () => Promise<void>
  /** 刷新完成状态（指定 wpCode 刷单个，不传刷全部可见底稿） */
  refreshCompletion: (wpCode?: string) => Promise<void>
}

// ─── 纯函数（导出供单元/PBT 测试） ───

/**
 * 从 wp_index 条目列表中提取 S32-* 的 wp_code → wp_id 映射。
 *
 * 🔴 铁律：使用 item.wp_id（非 item.id）。
 * wp_id 为 null/undefined 的条目被忽略（无对应底稿实体）。
 */
export function buildWpIdMap(
  items: Array<{ wp_code: string; wp_id?: string | null; id: string }>,
): Record<string, string> {
  const map: Record<string, string> = {}
  for (const item of items) {
    if (item.wp_code && /^S32-\d+$/.test(item.wp_code) && item.wp_id) {
      map[item.wp_code] = item.wp_id
    }
  }
  return map
}

/**
 * 计算可见 Tab：仅 wpIdMap 中存在的 S32 wp_code 对应 Tab 可见。
 * Property 3: Tab 可见性由 wp_index 存在性驱动。
 */
export function computeVisibleTabs(
  wpIdMap: Record<string, string>,
): S32TabDef[] {
  return S32_FRAUD_TABS.filter(tab => !!wpIdMap[tab.wpCode])
}

/**
 * 从 checklist-responses 推导程序表完成状态（Req 7.1）：
 * - 全部 conclusion 非空 → completed
 * - 部分非空 → in_progress
 * - 全空/空数组 → not_started
 *
 * 对齐 GtAProgramConsole 的核查程序完成逻辑：
 * 程序行的 conclusion 字段由用户填写核查结论。
 */
export function deriveProgramStatus(responses: ChecklistResponse[]): CompletionStatus {
  if (responses.length === 0) return 'not_started'
  const filled = responses.filter(r => r.conclusion != null && r.conclusion.trim() !== '')
  if (filled.length === 0) return 'not_started'
  if (filled.length === responses.length) return 'completed'
  return 'in_progress'
}

/**
 * 计算进度汇总（Property 5：completed + inProgress + notStarted == 可见底稿数）
 */
export function computeProgressSummary(
  completionMap: Record<string, CompletionStatus>,
): ProgressSummary {
  let completed = 0, inProgress = 0, notStarted = 0
  for (const status of Object.values(completionMap)) {
    if (status === 'completed') completed++
    else if (status === 'in_progress') inProgress++
    else notStarted++
  }
  return { completed, inProgress, notStarted }
}

// ─── Composable ───

export function useS32BundleState(options: UseS32BundleStateOptions): UseS32BundleStateReturn {
  const { projectId } = options

  const loading = ref(false)
  /** S32-x → wp_id 内部状态 */
  const wpIdMapState = ref<Record<string, string>>({})
  /** S32-x → checklist-responses 原始数据缓存 */
  const responsesCache = ref<Record<string, ChecklistResponse[]>>({})

  // ─── wpIdMap（Task 3.1）───
  const wpIdMap = computed<Record<string, string>>(() => wpIdMapState.value)

  // ─── visibleTabs（Task 3.1）───
  const visibleTabs = computed<S32TabDef[]>(() =>
    computeVisibleTabs(wpIdMapState.value),
  )

  // ─── completionMap（Task 3.2）───
  const completionMap = computed<Record<string, CompletionStatus>>(() => {
    const map: Record<string, CompletionStatus> = {}
    for (const tab of visibleTabs.value) {
      const responses = responsesCache.value[tab.wpCode] || []
      map[tab.wpCode] = deriveProgramStatus(responses)
    }
    return map
  })

  // ─── progressSummary（Task 3.2）───
  const progressSummary = computed<ProgressSummary>(() =>
    computeProgressSummary(completionMap.value),
  )

  // ─── 数据加载 ───

  /**
   * 通过 wp_index 查询获取 S32-1~13 的 wp_id 映射（Req 5.1）。
   * 🔴 铁律：bundle wpIdMap 必须用 item.wp_id 不能用 item.id。
   */
  async function loadWpIndex(): Promise<void> {
    if (!projectId.value) {
      wpIdMapState.value = {}
      return
    }
    loading.value = true
    try {
      const items = await getWpIndex(projectId.value)
      wpIdMapState.value = buildWpIdMap(items)
    } catch {
      wpIdMapState.value = {}
    } finally {
      loading.value = false
    }
  }

  /**
   * 拉取单个底稿的 checklist-responses。
   */
  async function loadResponses(wpId: string): Promise<ChecklistResponse[]> {
    if (!wpId) return []
    try {
      const data = await api.get(`/api/workpapers/${wpId}/checklist-responses`, {
        params: { project_id: projectId.value },
        _silent: true,
      } as any)
      return (data as ChecklistResponse[]) || []
    } catch {
      return []
    }
  }

  /**
   * 刷新完成状态（Req 7.1, 7.4）。
   * - wpCode 指定时仅刷新该底稿
   * - 不传时刷新全部可见底稿
   *
   * Tab 切走时由组件调用 refreshCompletion(prevTabWpCode) 实现实时更新（Req 7.4）。
   */
  async function refreshCompletion(wpCode?: string): Promise<void> {
    loading.value = true
    try {
      if (wpCode) {
        // 刷新单个底稿
        const wpId = wpIdMapState.value[wpCode]
        if (wpId) {
          const responses = await loadResponses(wpId)
          responsesCache.value = { ...responsesCache.value, [wpCode]: responses }
        }
      } else {
        // 刷新全部可见底稿
        const tabs = visibleTabs.value
        const results = await Promise.all(
          tabs.map(async (tab) => {
            const wpId = wpIdMapState.value[tab.wpCode]
            const responses = await loadResponses(wpId)
            return { wpCode: tab.wpCode, responses }
          }),
        )
        const newCache: Record<string, ChecklistResponse[]> = {}
        for (const { wpCode: code, responses } of results) {
          newCache[code] = responses
        }
        responsesCache.value = newCache
      }
    } finally {
      loading.value = false
    }
  }

  return {
    wpIdMap,
    visibleTabs,
    completionMap,
    progressSummary,
    loading,
    loadWpIndex,
    refreshCompletion,
  }
}

export default useS32BundleState
