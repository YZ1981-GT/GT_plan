/**
 * useA17BundleState — A17 审计总结聚合组件的跨 Tab 业务状态管理
 *
 * 职责：
 * 1. 完成状态追踪（A17-1 / A17-5 / A17-6 / A17-7）
 * 2. 联动锁定（A17-5 未完成 → A17-6/A17-7 锁定）
 * 3. 签发前置条件（三者全 completed → signOffReady）
 * 4. KAM 引用加载（B50 + D~N 重大发现）
 *
 * 仅做数据读取和状态推导，不做数据写入。
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { api } from '@/services/apiProxy'

// ─── Types (exported for testability) ───

export type CompletionStatus = 'completed' | 'in_progress' | 'not_started'

export interface SubTabCompletion {
  tabId: string
  label: string
  status: CompletionStatus
}

export interface SignOffPrecondition {
  id: string
  label: string
  satisfied: boolean
}

export interface KamReference {
  source: string
  title: string
  riskLevel?: 'high' | 'medium'
  wpCode: string
  summary: string
}

export interface ChecklistResponse {
  item_id: string
  conclusion?: string | null
  remark?: string | null
  wp_ref?: string | null
}

export interface UseA17BundleStateOptions {
  projectId: Ref<string>
  wpIdMap: Ref<Record<string, string>>
}

export interface UseA17BundleStateReturn {
  completionMap: ComputedRef<Record<string, CompletionStatus>>
  subTabCompletions: ComputedRef<SubTabCompletion[]>
  isA17_6Locked: ComputedRef<boolean>
  isA17_7Locked: ComputedRef<boolean>
  a17_6LockReason: ComputedRef<string>
  a17_7LockReason: ComputedRef<string>
  signOffPreconditions: ComputedRef<SignOffPrecondition[]>
  signOffReady: ComputedRef<boolean>
  kamReferences: Ref<KamReference[]>
  refreshCompletionStatus: () => Promise<void>
  loadKamReferences: () => Promise<void>
}

// ─── Pure derivation functions (exported for unit/PBT testing) ───

/**
 * A17-5 完成状态推导：
 * - 全部 conclusion 非空 → completed
 * - 部分非空 → in_progress
 * - 全空/空数组 → not_started
 */
export function deriveA17_5Status(responses: ChecklistResponse[]): CompletionStatus {
  if (responses.length === 0) return 'not_started'
  const filled = responses.filter(r => r.conclusion != null && r.conclusion !== '')
  if (filled.length === 0) return 'not_started'
  if (filled.length === responses.length) return 'completed'
  return 'in_progress'
}

/**
 * A17-1 完成状态推导：
 * - 10+ 章节有内容 → completed（简化规则）
 * - 部分有内容 → in_progress
 * - 无内容/空数组 → not_started
 */
export function deriveA17_1Status(responses: ChecklistResponse[]): CompletionStatus {
  if (responses.length === 0) return 'not_started'
  const filled = responses.filter(r => r.remark != null && r.remark.trim() !== '')
  if (filled.length === 0) return 'not_started'
  if (filled.length >= 10) return 'completed'
  return 'in_progress'
}

/**
 * A17-7 完成状态推导：
 * - sign_status item conclusion = 'signed' → completed
 * - 有其他填写 → in_progress
 * - 无填写 → not_started
 */
export function deriveA17_7Status(responses: ChecklistResponse[]): CompletionStatus {
  const signItem = responses.find(r => r.item_id === 'A17-7-sign-status')
  if (signItem?.conclusion === 'signed') return 'completed'
  if (responses.some(r => r.conclusion != null && r.conclusion !== '')) return 'in_progress'
  return 'not_started'
}

/**
 * 状态 → 显示映射（仪表盘用）
 */
export function statusToDisplay(status: CompletionStatus): { icon: string; color: string } {
  switch (status) {
    case 'completed': return { icon: '✓', color: 'green' }
    case 'in_progress': return { icon: '◐', color: 'yellow' }
    case 'not_started': return { icon: '○', color: 'gray' }
  }
}

// ─── Tab Configuration (exported for tests) ───

export interface TabDef {
  id: string
  label: string
  kind: 'program' | 'a17-summary' | 'word' | 'checklist' | 'independence'
  wpCode?: string
  tracked?: boolean
}

export const A17_BUNDLE_TABS: TabDef[] = [
  { id: 'program', label: '审计程序', kind: 'program' },
  { id: 'A17-1', label: '重大事项概要汇总', kind: 'a17-summary', wpCode: 'A17-1', tracked: true },
  { id: 'A17-2-1', label: '关键审计事项', kind: 'kam', wpCode: 'A17-2-1' },
  { id: 'A17-3', label: '业务咨询记录', kind: 'word', wpCode: 'A17-3' },
  { id: 'A17-3-1', label: '业务咨询执行记录', kind: 'word', wpCode: 'A17-3-1' },
  { id: 'A17-4', label: '重大专业分歧事项记录', kind: 'word', wpCode: 'A17-4' },
  { id: 'A17-5', label: '审计工作完成核对表', kind: 'checklist', wpCode: 'A17-5', tracked: true },
  { id: 'A17-6', label: '总结会会议纪要', kind: 'word', wpCode: 'A17-6', tracked: true },
  { id: 'A17-7', label: '独立性声明书', kind: 'independence', wpCode: 'A17-7', tracked: true },
]

// ─── Composable ───

export function useA17BundleState(options: UseA17BundleStateOptions): UseA17BundleStateReturn {
  const { projectId, wpIdMap } = options

  // Raw responses storage
  const rawResponses = ref<Record<string, ChecklistResponse[]>>({
    'A17-1': [],
    'A17-5': [],
    'A17-7': [],
  })

  const kamReferences = ref<KamReference[]>([])

  // ─── Completion map ───
  const completionMap = computed<Record<string, CompletionStatus>>(() => {
    const a17_5Status = wpIdMap.value['A17-5-1'] || wpIdMap.value['A17-5-2']
      || wpIdMap.value['A17-5-3'] || wpIdMap.value['A17-5-4'] || wpIdMap.value['A17-5-5']
      ? deriveA17_5Status(rawResponses.value['A17-5'] || [])
      : 'completed' // No A17-5 applicable → treat as completed (no check needed)

    return {
      'A17-1': deriveA17_1Status(rawResponses.value['A17-1'] || []),
      'A17-5': a17_5Status,
      'A17-6': a17_5Status === 'completed' ? 'in_progress' : 'not_started', // A17-6 status is word doc, simplified
      'A17-7': deriveA17_7Status(rawResponses.value['A17-7'] || []),
    }
  })

  const subTabCompletions = computed<SubTabCompletion[]>(() => [
    { tabId: 'A17-1', label: '概要汇总', status: completionMap.value['A17-1'] },
    { tabId: 'A17-5', label: '核对表', status: completionMap.value['A17-5'] },
    { tabId: 'A17-6', label: '总结会', status: completionMap.value['A17-6'] },
    { tabId: 'A17-7', label: '独立性', status: completionMap.value['A17-7'] },
  ])

  // ─── Linkage locking ───
  const isA17_6Locked = computed(() => completionMap.value['A17-5'] !== 'completed')
  const isA17_7Locked = computed(() => completionMap.value['A17-5'] !== 'completed')

  const a17_6LockReason = computed(() =>
    isA17_6Locked.value ? 'A17-5 审计完成核对表未完成，无法编辑总结会议纪要' : '',
  )
  const a17_7LockReason = computed(() =>
    isA17_7Locked.value ? 'A17-5 审计完成核对表未完成，无法进行独立性签署' : '',
  )

  // ─── Sign-off preconditions ───
  const signOffPreconditions = computed<SignOffPrecondition[]>(() => [
    {
      id: 'kam',
      label: 'A17-1 关键审计事项编制完成',
      satisfied: completionMap.value['A17-1'] === 'completed',
    },
    {
      id: 'checklist',
      label: 'A17-5 审计完成核对表全部完成',
      satisfied: completionMap.value['A17-5'] === 'completed',
    },
    {
      id: 'independence',
      label: 'A17-7 独立性声明书完成',
      satisfied: completionMap.value['A17-7'] === 'completed',
    },
  ])

  const signOffReady = computed(() => signOffPreconditions.value.every(p => p.satisfied))

  // ─── Data loading ───
  async function loadResponses(wpId: string): Promise<ChecklistResponse[]> {
    if (!wpId) return []
    try {
      const data = await api.get(`/api/workpapers/${wpId}/checklist-responses`, {
        params: { project_id: projectId.value },
      })
      return (data as ChecklistResponse[]) || []
    } catch {
      return []
    }
  }

  async function refreshCompletionStatus(): Promise<void> {
    const a17_1WpId = wpIdMap.value['A17-1'] || ''
    const a17_7WpId = wpIdMap.value['A17-7'] || ''

    // Collect all applicable A17-5 wp_ids
    const a17_5WpIds = ['A17-5-1', 'A17-5-2', 'A17-5-3', 'A17-5-4', 'A17-5-5']
      .map(code => wpIdMap.value[code])
      .filter(Boolean)

    const [a17_1Res, a17_7Res, ...a17_5Results] = await Promise.all([
      loadResponses(a17_1WpId),
      loadResponses(a17_7WpId),
      ...a17_5WpIds.map(id => loadResponses(id)),
    ])

    rawResponses.value = {
      'A17-1': a17_1Res,
      'A17-5': a17_5Results.flat(),
      'A17-7': a17_7Res,
    }
  }

  async function loadKamReferences(): Promise<void> {
    if (!projectId.value) {
      kamReferences.value = []
      return
    }
    try {
      const data = await api.get(`/api/projects/${projectId.value}/kam-references`)
      kamReferences.value = (data as KamReference[]) || []
    } catch {
      kamReferences.value = []
    }
  }

  return {
    completionMap,
    subTabCompletions,
    isA17_6Locked,
    isA17_7Locked,
    a17_6LockReason,
    a17_7LockReason,
    signOffPreconditions,
    signOffReady,
    kamReferences,
    refreshCompletionStatus,
    loadKamReferences,
  }
}
