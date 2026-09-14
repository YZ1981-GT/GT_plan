/**
 * useS34BundleState — S34 首发审核（IPO）特项底稿聚合组件跨 Tab 业务状态管理
 *
 * Spec: .kiro/specs/s34-ipo-review-bundle/  Task 4.1 / 4.2 / 4.3
 * Requirements: 8.1, 8.3, 9.1, 10.1, 10.2, 10.5, 12.1, 12.3
 *
 * 职责（对齐 useS32BundleState / useS33BundleState 模式）：
 * 1. wpIdMap：S34-0~S34-41 → wp_id（通过 wp_index 解析）
 * 2. checklist：S34ChecklistItem[]（从 S34-0 核查清单 API 加载）
 * 3. applicableCodes：wpIdMap 有值的 wp_code 列表
 * 4. completionMap：各底稿完成状态（Task 4.2 实现）
 * 5. regRefMap：法规溯源映射（Task 4.3 实现）
 * 6. progressSummary：完成/进行中/未开始/不适用 计数（Task 4.2 实现）
 * 7. refreshCompletion：刷新完成状态（Task 4.2 实现）
 * 8. loadChecklist：加载 S34 核查清单（Task 4.1 实现）
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
export type Applicability = 'applicable' | 'not_applicable' | 'unknown'

export interface RegRef {
  csrc?: string | null   // 证监会 发行类 4/5/9 号 条目
  sse?: string | null    // 上交所指南条目
  szse?: string | null   // 深交所指南条目
  bse?: string | null    // 北交所指引条目
  title: string          // 核查事项名称
}

export interface S34ChecklistItem {
  seq: number
  wpCode: string         // S34-x
  name: string
  regRef: RegRef
  applicability: Applicability
  status: CompletionStatus
}

export interface ProgressSummary {
  completed: number
  inProgress: number
  notStarted: number
  notApplicable: number
}

export interface UseS34BundleStateOptions {
  projectId: Ref<string>
}

export interface UseS34BundleStateReturn {
  /** S34-x wp_code → wp_id 映射 */
  wpIdMap: ComputedRef<Record<string, string>>
  /** S34-0 核查清单结构化数据 */
  checklist: Ref<S34ChecklistItem[]>
  /** wpIdMap 有值的 wp_code 列表（适用底稿编码） */
  applicableCodes: ComputedRef<string[]>
  /** 各底稿完成状态（Task 4.2） */
  completionMap: ComputedRef<Record<string, CompletionStatus>>
  /** 法规溯源映射（Task 4.3） */
  regRefMap: ComputedRef<Record<string, RegRef>>
  /** 进度统计（Task 4.2） */
  progressSummary: ComputedRef<ProgressSummary>
  /** 加载状态 */
  loading: Ref<boolean>
  /** 加载 wp_index 解析 wpIdMap */
  loadWpIndex: () => Promise<void>
  /** 刷新完成状态（Task 4.2） */
  refreshCompletion: (wpCode?: string) => Promise<void>
  /** 加载 S34 核查清单 */
  loadChecklist: () => Promise<void>
}

// ─── 纯函数（导出供单元/PBT 测试） ───

/**
 * 从 wp_index 条目列表中提取 S34-* 的 wp_code → wp_id 映射。
 *
 * 🔴 铁律：使用 item.wp_id（非 item.id）。
 * wp_id 为 null/undefined 的条目被忽略（无对应底稿实体）。
 *
 * Property 2: wp_id 解析与传播
 */
export function buildWpIdMap(
  items: Array<{ wp_code: string; wp_id?: string | null; id: string }>,
): Record<string, string> {
  const map: Record<string, string> = {}
  for (const item of items) {
    if (item.wp_code && /^S34-\d+/.test(item.wp_code) && item.wp_id) {
      map[item.wp_code] = item.wp_id
    }
  }
  return map
}

/**
 * 从 wpIdMap 提取适用底稿编码列表（有 wp_id 的 wp_code）。
 *
 * Property 3: Tab 可见性由 wp_index 存在性驱动。
 * Requirement 9.1: 有 wp_id 即适用。
 */
export function computeApplicableCodes(
  wpIdMap: Record<string, string>,
): string[] {
  return Object.keys(wpIdMap).sort((a, b) => {
    // 按数字排序 S34-1, S34-2, ... S34-41
    const numA = parseInt(a.replace('S34-', ''), 10)
    const numB = parseInt(b.replace('S34-', ''), 10)
    return numA - numB
  })
}

/**
 * 从清单条目数组中计算完成进度统计。
 *
 * Property 5: 完成进度统计一致性 —— 所有计数之和等于条目总数。
 * - not_applicable 条目计入 notApplicable
 * - 其余按 status 计入 completed / inProgress / notStarted
 *
 * Validates: Requirements 10.1, 10.2
 */
export function computeProgressSummary(
  items: Array<{ applicability: Applicability; status: CompletionStatus }>,
): ProgressSummary {
  let completed = 0, inProgress = 0, notStarted = 0, notApplicable = 0
  for (const item of items) {
    if (item.applicability === 'not_applicable') {
      notApplicable++
    } else if (item.status === 'completed') {
      completed++
    } else if (item.status === 'in_progress') {
      inProgress++
    } else {
      notStarted++
    }
  }
  return { completed, inProgress, notStarted, notApplicable }
}

/**
 * 从清单条目中构建 completionMap（仅适用底稿）。
 *
 * Property 5: completionMap 仅包含 applicability === 'applicable' 的条目。
 *
 * Validates: Requirements 10.1, 10.5
 */
export function computeCompletionMap(
  items: Array<{ wpCode: string; applicability: Applicability; status: CompletionStatus }>,
): Record<string, CompletionStatus> {
  const map: Record<string, CompletionStatus> = {}
  for (const item of items) {
    if (item.applicability === 'applicable') {
      map[item.wpCode] = item.status
    }
  }
  return map
}

/**
 * 从清单条目数组中构建 regRefMap（wpCode → RegRef）。
 *
 * Property 6: 法规溯源映射稳定性 —— 每个 wpCode 都有对应 RegRef。
 * null 的 csrc/sse/szse/bse 值被保留（不转换或移除）。
 *
 * Validates: Requirements 12.1, 12.3
 */
export function computeRegRefMap(
  items: Array<{ wpCode: string; regRef: RegRef }>,
): Record<string, RegRef> {
  const map: Record<string, RegRef> = {}
  for (const item of items) {
    map[item.wpCode] = item.regRef
  }
  return map
}

/**
 * 将后端 API 返回的 snake_case 清单数据转为前端 camelCase 类型。
 * 后端返回：{ seq, wp_code, name, reg_ref: { csrc, sse, szse, bse, title }, applicability, status }
 */
export function mapApiChecklist(
  apiItems: Array<{
    seq: number
    wp_code: string
    name: string
    reg_ref: { csrc?: string | null; sse?: string | null; szse?: string | null; bse?: string | null; title: string }
    applicability: string
    status: string
  }>,
): S34ChecklistItem[] {
  return apiItems.map(item => ({
    seq: item.seq,
    wpCode: item.wp_code,
    name: item.name,
    regRef: {
      csrc: item.reg_ref.csrc ?? null,
      sse: item.reg_ref.sse ?? null,
      szse: item.reg_ref.szse ?? null,
      bse: item.reg_ref.bse ?? null,
      title: item.reg_ref.title,
    },
    applicability: item.applicability as Applicability,
    status: item.status as CompletionStatus,
  }))
}

// ─── Composable ───

export function useS34BundleState(options: UseS34BundleStateOptions): UseS34BundleStateReturn {
  const { projectId } = options

  const loading = ref(false)
  /** S34-x → wp_id 内部状态 */
  const wpIdMapState = ref<Record<string, string>>({})
  /** S34 核查清单（从 API 加载） */
  const checklist = ref<S34ChecklistItem[]>([])

  // ─── wpIdMap（Task 4.1, Req 8.1, 8.3）───
  const wpIdMap = computed<Record<string, string>>(() => wpIdMapState.value)

  // ─── applicableCodes（Task 4.1, Req 9.1）───
  const applicableCodes = computed<string[]>(() =>
    computeApplicableCodes(wpIdMapState.value),
  )

  // ─── completionMap（Task 4.2, Req 10.1, 10.5）───
  const completionMap = computed<Record<string, CompletionStatus>>(() =>
    computeCompletionMap(checklist.value),
  )

  // ─── regRefMap（Task 4.3, Req 12.1, 12.3）───
  const regRefMap = computed<Record<string, RegRef>>(() =>
    computeRegRefMap(checklist.value),
  )

  // ─── progressSummary（Task 4.2, Req 10.1, 10.2）───
  const progressSummary = computed<ProgressSummary>(() =>
    computeProgressSummary(checklist.value),
  )

  // ─── 数据加载 ───

  /**
   * 通过 wp_index 查询获取 S34-0~S34-41 的 wp_id 映射（Req 8.1, 8.3）。
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
   * 加载 S34 核查清单（Req 3.2, 9.1, 12.1）。
   * 调用 GET /api/projects/{project_id}/s34-checklist
   */
  async function loadChecklist(): Promise<void> {
    if (!projectId.value) {
      checklist.value = []
      return
    }
    loading.value = true
    try {
      const data = await api.get(`/api/projects/${projectId.value}/s34-checklist`, {
        _silent: true,
      } as any)
      checklist.value = mapApiChecklist(data as any[])
    } catch {
      checklist.value = []
    } finally {
      loading.value = false
    }
  }

  /**
   * 刷新完成状态（Task 4.2, Req 10.5）。
   * 当用户从某 Tab 切走时触发，通过重新加载 checklist 来刷新所有底稿的完成状态。
   * checklist API 在服务端查询 wp_index.status，因此 reload 即获得最新完成状态。
   */
  async function refreshCompletion(_wpCode?: string): Promise<void> {
    await loadChecklist()
  }

  return {
    wpIdMap,
    checklist,
    applicableCodes,
    completionMap,
    regRefMap,
    progressSummary,
    loading,
    loadWpIndex,
    refreshCompletion,
    loadChecklist,
  }
}

export default useS34BundleState
