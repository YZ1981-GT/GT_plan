/**
 * useS35BundleState — S35 再融资审核特项底稿聚合组件跨 Tab 业务状态管理
 *
 * Spec: .kiro/specs/s35-refinancing-bundle/  Task 3.1 / 3.2
 * Requirements: 6.1, 6.2, 8.1
 *
 * 职责（对齐 useS34BundleState 模式）：
 * 1. wpIdMap：S35-1~S35-5 及子表（S35-x-1）→ wp_id（通过 wp_index 解析）
 * 2. visibleTabs：仅 wpIdMap 中有 wp_id 的底稿显示为可见 Tab
 * 3. completionMap：各底稿完成状态（Task 3.2 实现）
 * 4. progressSummary：完成/进行中/未开始 计数（Task 3.2 实现）
 * 5. refreshCompletion：刷新完成状态（Task 3.2 实现）
 *
 * 🔴 铁律：wpIdMap 必须用 item.wp_id 不能用 item.id
 *
 * 仅做数据读取与状态推导，不做数据写入。
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { getWpIndex } from '@/services/workpaperApi'
import { api } from '@/services/apiProxy'

// ─── Types (exported for testability & cross-module reuse) ───

export type CompletionStatus = 'completed' | 'in_progress' | 'not_started'

export interface TabDef {
  /** Tab 标识 = sheetName 路由值 */
  id: string
  /** Tab 显示名（中文标签） */
  label: string
  /** 子底稿编码（wp_index 查 wp_id） */
  wpCode: string
  /** 明细核查子表编码列表（无子表时为 undefined） */
  subSheets?: string[]
}

export interface ProgressSummary {
  completed: number
  inProgress: number
  notStarted: number
}

export interface UseS35BundleStateOptions {
  projectId: Ref<string>
}

export interface UseS35BundleStateReturn {
  /** S35-x（含子表）wp_code → wp_id 映射 */
  wpIdMap: ComputedRef<Record<string, string>>
  /** 仅显示 wpIdMap 中有 wp_id 的 Tab */
  visibleTabs: ComputedRef<TabDef[]>
  /** 各底稿完成状态（Task 3.2） */
  completionMap: ComputedRef<Record<string, CompletionStatus>>
  /** 进度统计（Task 3.2） */
  progressSummary: ComputedRef<ProgressSummary>
  /** 加载状态 */
  loading: Ref<boolean>
  /** 加载 wp_index 解析 wpIdMap */
  loadWpIndex: () => Promise<void>
  /** 刷新完成状态（Task 3.2） */
  refreshCompletion: (wpCode?: string) => Promise<void>
}

// ─── 常量：5 再融资核查底稿 Tab 配置 ───

export const S35_TAB_DEFS: TabDef[] = [
  { id: 'S35-1', label: '关联交易', wpCode: 'S35-1', subSheets: ['S35-1-1'] },
  { id: 'S35-2', label: '财务性投资核查', wpCode: 'S35-2', subSheets: ['S35-2-1'] },
  { id: 'S35-3', label: '现金分红核查', wpCode: 'S35-3', subSheets: ['S35-3-1'] },
  { id: 'S35-4', label: '商誉减值', wpCode: 'S35-4' },
  { id: 'S35-5', label: '募集资金涉及收购核查', wpCode: 'S35-5' },
]

/**
 * 所有 S35 系列 wp_code（主底稿 + 子表），用于 wp_index 过滤。
 */
export const S35_ALL_CODES: string[] = [
  'S35-1', 'S35-1-1',
  'S35-2', 'S35-2-1',
  'S35-3', 'S35-3-1',
  'S35-4',
  'S35-5',
]

/** checklist_responses 精简形态（与 S32 对齐） */
export interface ChecklistResponse {
  item_id: string
  conclusion?: string | null
  remark?: string | null
}

// ─── 纯函数（导出供单元/PBT 测试） ───

/**
 * 从 checklist-responses 推导程序表完成状态：
 * - 全部 conclusion 非空 → completed
 * - 部分非空 → in_progress
 * - 全空/空数组 → not_started
 *
 * 对齐 GtAProgramConsole 的核查程序完成逻辑：
 * 程序行的 conclusion 字段由用户填写核查结论。
 *
 * Property 6: 完成进度统计一致性
 * Validates: Requirements 8.1
 */
export function deriveProgramStatus(responses: ChecklistResponse[]): CompletionStatus {
  if (responses.length === 0) return 'not_started'
  const filled = responses.filter(r => r.conclusion != null && r.conclusion.trim() !== '')
  if (filled.length === 0) return 'not_started'
  if (filled.length === responses.length) return 'completed'
  return 'in_progress'
}

/**
 * 从 responsesCache 构建 completionMap：对每个可见 Tab 的 wpCode，
 * 取出对应 checklist-responses 推导完成状态。
 *
 * Property 6: 完成进度统计一致性
 * Validates: Requirements 8.1
 */
export function computeCompletionMap(
  visibleWpCodes: string[],
  responsesCache: Record<string, ChecklistResponse[]>,
): Record<string, CompletionStatus> {
  const map: Record<string, CompletionStatus> = {}
  for (const wpCode of visibleWpCodes) {
    const responses = responsesCache[wpCode] || []
    map[wpCode] = deriveProgramStatus(responses)
  }
  return map
}

/**
 * 从 completionMap 计算进度汇总。
 *
 * Property 6: completed + inProgress + notStarted == 可见底稿数。
 * Validates: Requirements 8.1
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

/**
 * 从 wp_index 条目列表中提取 S35-* 的 wp_code → wp_id 映射。
 *
 * 🔴 铁律：使用 item.wp_id（非 item.id）。
 * wp_id 为 null/undefined 的条目被忽略（无对应底稿实体）。
 *
 * 匹配规则：wp_code 以 'S35-' 开头（含 S35-1~S35-5 及子表 S35-x-1）。
 *
 * Property 2: wp_id 解析与传播
 * Validates: Requirements 6.1
 */
export function buildS35WpIdMap(
  items: Array<{ wp_code: string; wp_id?: string | null; id: string }>,
): Record<string, string> {
  const map: Record<string, string> = {}
  for (const item of items) {
    if (item.wp_code && /^S35-\d+/.test(item.wp_code) && item.wp_id) {
      map[item.wp_code] = item.wp_id
    }
  }
  return map
}

/**
 * 计算可见 Tab 列表：仅 wpIdMap 中有 wp_id 的底稿 Tab 可见。
 *
 * Property 3: Tab 可见性由 wp_index 存在性驱动
 * Validates: Requirements 6.2
 */
export function computeVisibleTabs(
  wpIdMap: Record<string, string>,
  tabDefs: TabDef[] = S35_TAB_DEFS,
): TabDef[] {
  return tabDefs.filter(t => !!wpIdMap[t.wpCode])
}

// ─── Composable ───

export function useS35BundleState(options: UseS35BundleStateOptions): UseS35BundleStateReturn {
  const { projectId } = options

  const loading = ref(false)
  /** S35-x（含子表）→ wp_id 内部状态 */
  const wpIdMapState = ref<Record<string, string>>({})
  /** S35-x → checklist-responses 原始数据缓存 */
  const responsesCache = ref<Record<string, ChecklistResponse[]>>({})

  // ─── wpIdMap（Task 3.1, Req 6.1）───
  const wpIdMap = computed<Record<string, string>>(() => wpIdMapState.value)

  // ─── visibleTabs（Task 3.1, Req 6.2）───
  const visibleTabs = computed<TabDef[]>(() =>
    computeVisibleTabs(wpIdMapState.value),
  )

  // ─── completionMap（Task 3.2, Req 8.1）───
  const completionMap = computed<Record<string, CompletionStatus>>(() =>
    computeCompletionMap(
      visibleTabs.value.map(t => t.wpCode),
      responsesCache.value,
    ),
  )

  // ─── progressSummary（Task 3.2, Req 8.1）───
  const progressSummary = computed<ProgressSummary>(() =>
    computeProgressSummary(completionMap.value),
  )

  // ─── 数据加载 ───

  /**
   * 通过 wp_index 查询获取 S35-1~S35-5 及子表的 wp_id 映射（Req 6.1）。
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
      wpIdMapState.value = buildS35WpIdMap(items)
    } catch {
      wpIdMapState.value = {}
    } finally {
      loading.value = false
    }
  }

  /**
   * 拉取单个底稿的 checklist-responses（对齐 S32 模式）。
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
   * 刷新完成状态（Task 3.2, Req 8.1）。
   * - wpCode 指定时仅刷新该底稿
   * - 不传时刷新全部可见底稿
   *
   * Tab 切走时由组件调用 refreshCompletion(prevTabWpCode) 实现实时更新。
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

export default useS35BundleState
