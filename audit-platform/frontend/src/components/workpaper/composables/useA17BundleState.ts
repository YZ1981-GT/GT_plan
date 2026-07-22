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
  /** 未满足时跳转的 Bundle Tab id（如 A17-5） */
  actionTab?: string
  /** 按钮文案 */
  actionLabel?: string
  /** 补充说明（缺什么） */
  hint?: string
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
  consultationPairing: ComputedRef<{ hasConsult: boolean; closed: boolean; warning: string }>
  disagreementClosure: ComputedRef<{ hasDisagreement: boolean; closed: boolean; warning: string }>
  consistencyErrors: Ref<Array<{ rule_id: string; description: string }>>
  signOffPreconditions: ComputedRef<SignOffPrecondition[]>
  signOffReady: ComputedRef<boolean>
  kamReferences: Ref<KamReference[]>
  kamStale: Ref<boolean>
  independenceDrift: Ref<{ hasDrift: boolean; message: string }>
  chapterStale: Ref<Array<{ chapter_id: string; chapter_num: number; message: string }>>
  agendaStale: Ref<Array<{ agenda_index: number; message: string }>>
  partnerSummary: Ref<Record<string, any> | null>
  timeline: Ref<{ milestones: Array<{ id: string; label: string; date: string | null; ok: boolean }>; warnings: string[] } | null>
  crossAlerts: Ref<Array<{
    id: string
    severity: string
    title: string
    message: string
    action_tab?: string | null
    action_hint?: string
    links?: string[]
  }>>
  signoffSelfCheck: Ref<{
    ready: boolean
    items: Array<{
      id: string
      ok: boolean
      severity: string
      label: string
      detail: string
      action_tab?: string | null
    }>
  } | null>
  refreshCompletionStatus: () => Promise<void>
  refreshConsistencyCheck: () => Promise<void>
  refreshKamStale: () => Promise<void>
  refreshIndependenceDrift: () => Promise<void>
  refreshChapterStale: () => Promise<void>
  refreshAgendaStale: () => Promise<void>
  refreshPartnerSummary: () => Promise<void>
  refreshCrossAlerts: () => Promise<void>
  refreshSignoffSelfCheck: () => Promise<void>
  loadKamReferences: () => Promise<void>
}


// ─── Pure derivation functions (exported for unit/PBT testing) ───

/**
 * A17-5 完成状态推导：
 * - 全部有效结论（是/否/不适用）且「否」带备注 → completed
 * - 「否」无备注 → 仍视为 in_progress（未闭环）
 * - 部分填写 → in_progress
 * - 全空 → not_started
 */
export function deriveA17_5Status(responses: ChecklistResponse[]): CompletionStatus {
  if (responses.length === 0) return 'not_started'
  const actionable = responses.filter(r => !r.item_id?.includes('header'))
  if (actionable.length === 0) return 'not_started'

  const filled = actionable.filter(r => r.conclusion != null && String(r.conclusion).trim() !== '')
  if (filled.length === 0) return 'not_started'

  let allOk = filled.length === actionable.length
  for (const r of filled) {
    const c = String(r.conclusion).trim()
    const normalized = c.toLowerCase()
    // 「否」及历史异常码 X/W 均须备注闭环
    const isNo = c === '否' || normalized === 'n' || normalized === 'no' || c === 'X/W'
    if (isNo) {
      const remark = (r.remark || '').trim()
      if (!remark) {
        allOk = false
        break
      }
    }
  }
  if (allOk) return 'completed'
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
 * A17-3 / A17-3-1 成对状态：
 * - 无咨询内容 → closed（不阻断）
 * - 多事项：按 consultation_id / a173-matter-{id} / a1731-matter-{id} 成对
 * - 有咨询 +（执行内容 或 勾选无需执行）→ closed
 * - 有咨询且未关闭 → open（需警示）
 */
export function deriveConsultationPairing(
  a173Responses: ChecklistResponse[],
  a1731Responses: ChecklistResponse[],
): { hasConsult: boolean; closed: boolean; warning: string } {
  const matterIds = new Set<string>()
  for (const r of a173Responses) {
    const m = r.item_id?.match(/^a173-matter-([^-]+)/)
    if (m) matterIds.add(m[1])
  }
  const consultIdMeta = a173Responses.find(r => r.item_id === 'a173-meta-consultation_id')
  const consultId = (consultIdMeta?.conclusion || consultIdMeta?.remark || '').trim()
  if (consultId) matterIds.add(consultId)

  // 多事项模式
  if (matterIds.size > 0) {
    const closedIds = new Set<string>()
    for (const r of a1731Responses) {
      const m = r.item_id?.match(/^a1731-matter-([^-]+)/)
      if (m) {
        const filled = (r.conclusion != null && r.conclusion !== '')
          || (r.remark != null && r.remark.trim() !== '')
        if (filled) closedIds.add(m[1])
      }
    }
    const linkId = (a1731Responses.find(r => r.item_id === 'a1731-meta-consultation_id')?.conclusion
      || a1731Responses.find(r => r.item_id === 'a1731-meta-consultation_id')?.remark
      || '').trim()
    const notRequired = a1731Responses.some(
      r => r.item_id === 'a1731-meta-not_required'
        && ['1', 'true', 'yes', 'y', '是'].includes(String(r.conclusion || '').toLowerCase()),
    )
    if (linkId && (notRequired || a1731Responses.some(
      r => r.item_id.startsWith('a1731-sec')
        && ((r.conclusion != null && r.conclusion !== '')
          || (r.remark != null && r.remark.trim() !== '')),
    ))) {
      closedIds.add(linkId)
    }
    // 全局无需执行：关闭全部
    if (notRequired && !linkId) {
      for (const id of matterIds) closedIds.add(id)
    }

    const open = [...matterIds].filter(id => !closedIds.has(id))
    if (open.length === 0) {
      return { hasConsult: true, closed: true, warning: '' }
    }
    return {
      hasConsult: true,
      closed: false,
      warning: `咨询事项未闭环（consultation_id: ${open.join(', ')}），请在 A17-3-1 填写执行或勾选「无需执行」`,
    }
  }

  const hasConsult = a173Responses.some(
    r => r.item_id !== 'a173-meta-not_applicable'
      && ((r.conclusion != null && r.conclusion !== '')
        || (r.remark != null && r.remark.trim() !== '')),
  )
  const na = a173Responses.some(
    r => r.item_id === 'a173-meta-not_applicable'
      && ['1', 'true', 'yes', 'y', '是', '不适用'].includes(String(r.conclusion || '').toLowerCase()),
  )
  if (na || !hasConsult) {
    return { hasConsult: false, closed: true, warning: '' }
  }
  const notRequired = a1731Responses.some(
    r => r.item_id === 'a1731-meta-not_required'
      && ['1', 'true', 'yes', 'y', '是'].includes(String(r.conclusion || '').toLowerCase()),
  )
  const hasExecution = a1731Responses.some(
    r => r.item_id.startsWith('a1731-sec')
      && ((r.conclusion != null && r.conclusion !== '')
        || (r.remark != null && r.remark.trim() !== '')),
  )
  // 若 3-1 填了 consultation_id，须与 3 的一致（若 3 也有）
  const id3 = (a173Responses.find(r => r.item_id === 'a173-meta-consultation_id')?.conclusion || '').trim()
  const id31 = (a1731Responses.find(r => r.item_id === 'a1731-meta-consultation_id')?.conclusion || '').trim()
  if (id3 && id31 && id3 !== id31) {
    return {
      hasConsult: true,
      closed: false,
      warning: `A17-3 与 A17-3-1 的 consultation_id 不一致（${id3} ≠ ${id31}）`,
    }
  }
  const closed = notRequired || hasExecution
  return {
    hasConsult: true,
    closed,
    warning: closed
      ? ''
      : '已填写 A17-3 业务咨询记录，请同步完成 A17-3-1 执行情况，或勾选「无需执行」',
  }
}

/**
 * A17-4 分歧闭环：
 * - 无内容 → closed（不适用）
 * - 有分歧内容但无最终结论（sec6）→ open
 * - 有结论 → closed
 */
export function deriveDisagreementClosure(
  a174Responses: ChecklistResponse[],
): { hasDisagreement: boolean; closed: boolean; warning: string } {
  const filled = (r: ChecklistResponse) =>
    (r.conclusion != null && String(r.conclusion).trim() !== '')
    || (r.remark != null && r.remark.trim() !== '')

  const hasAny = a174Responses.some(
    r => r.item_id !== 'a174-meta-not_applicable' && filled(r),
  )
  const na = a174Responses.some(
    r => r.item_id === 'a174-meta-not_applicable'
      && ['1', 'true', 'yes', 'y', '是', '不适用'].includes(String(r.conclusion || '').toLowerCase()),
  )
  if (na || !hasAny) {
    return { hasDisagreement: false, closed: true, warning: '' }
  }
  const hasConclusion = a174Responses.some(
    r => (r.item_id === 'a174-sec6-conclusion' || r.item_id === 'a174-sec6')
      && filled(r),
  )
  if (hasConclusion) {
    return { hasDisagreement: true, closed: true, warning: '' }
  }
  return {
    hasDisagreement: true,
    closed: false,
    warning: '已填写 A17-4 专业分歧记录，请在第六节填写最终结论后方可签发',
  }
}

/**
 * 从核对表 preset_wp_ref 文本中提取可跳转的底稿编码
 * 例："B60" / "A12以及对应实质性底稿函证程序" / "A1-13、A1-14"
 */
export function parsePresetWpRefs(preset: string | null | undefined): string[] {
  if (!preset) return []
  const matches = preset.match(/[A-Z]\d{1,2}(?:-\d+(?:-\d+)?)?[A-Z]?/g) || []
  // 去重并过滤过短噪声
  const out: string[] = []
  for (const m of matches) {
    if (!out.includes(m)) out.push(m)
  }
  return out
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
  kind: 'program' | 'a17-summary' | 'word' | 'checklist' | 'independence' | 'kam'
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
    'A17-3': [],
    'A17-3-1': [],
    'A17-4': [],
  })

  const kamReferences = ref<KamReference[]>([])
  const consistencyErrors = ref<Array<{ rule_id: string; description: string }>>([])
  const kamStale = ref(false)
  const independenceDrift = ref<{ hasDrift: boolean; message: string }>({
    hasDrift: false,
    message: '',
  })
  const chapterStale = ref<Array<{ chapter_id: string; chapter_num: number; message: string }>>([])
  const agendaStale = ref<Array<{ agenda_index: number; message: string }>>([])
  const partnerSummary = ref<Record<string, any> | null>(null)
  const timeline = ref<{
    milestones: Array<{ id: string; label: string; date: string | null; ok: boolean }>
    warnings: string[]
  } | null>(null)
  const crossAlerts = ref<Array<{
    id: string
    severity: string
    title: string
    message: string
    action_tab?: string | null
    action_hint?: string
    links?: string[]
  }>>([])
  const signoffSelfCheck = ref<{
    ready: boolean
    items: Array<{
      id: string
      ok: boolean
      severity: string
      label: string
      detail: string
      action_tab?: string | null
    }>
  } | null>(null)

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

  const consultationPairing = computed(() =>
    deriveConsultationPairing(
      rawResponses.value['A17-3'] || [],
      rawResponses.value['A17-3-1'] || [],
    ),
  )

  const disagreementClosure = computed(() =>
    deriveDisagreementClosure(rawResponses.value['A17-4'] || []),
  )

  const a175OpenNoItems = computed(() => {
    const items = (rawResponses.value['A17-5'] || []).filter((r) => {
      const c = String(r.conclusion || '').trim()
      const isNo = c === '否' || c.toLowerCase() === 'n' || c.toLowerCase() === 'no' || c === 'X/W'
      return isNo && !(r.remark || '').trim()
    })
    return items.map(r => ({
      item_id: r.item_id,
      wp_ref: r.wp_ref || '',
    }))
  })

  const subTabCompletions = computed<SubTabCompletion[]>(() => {
    const items: SubTabCompletion[] = [
      { tabId: 'A17-1', label: '概要汇总', status: completionMap.value['A17-1'] },
      { tabId: 'A17-5', label: '核对表', status: completionMap.value['A17-5'] },
      { tabId: 'A17-6', label: '总结会', status: completionMap.value['A17-6'] },
      { tabId: 'A17-7', label: '独立性', status: completionMap.value['A17-7'] },
    ]
    if (consultationPairing.value.hasConsult) {
      items.push({
        tabId: 'A17-3-1',
        label: '咨询闭环',
        status: consultationPairing.value.closed ? 'completed' : 'in_progress',
      })
    }
    return items
  })

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
  const signOffPreconditions = computed<SignOffPrecondition[]>(() => {
    const a175Hint = a175OpenNoItems.value.length
      ? `尚有 ${a175OpenNoItems.value.length} 项「否」无备注：${a175OpenNoItems.value.slice(0, 3).map(i => i.item_id).join('、')}${a175OpenNoItems.value.length > 3 ? '…' : ''}`
      : (completionMap.value['A17-5'] !== 'completed' ? '核对表未全部填写完成' : undefined)

    return [
      {
        id: 'kam',
        label: 'A17-1 重大事项概要汇总编制完成（A 类必备）',
        satisfied: completionMap.value['A17-1'] === 'completed',
        actionTab: 'A17-1',
        actionLabel: '前往 A17-1 →',
        hint: completionMap.value['A17-1'] !== 'completed' ? '请补齐至少 10 个章节内容' : undefined,
      },
      {
        id: 'checklist',
        label: 'A17-5 审计完成核对表全部完成（「否」须备注）',
        satisfied: completionMap.value['A17-5'] === 'completed',
        actionTab: 'A17-5',
        actionLabel: '前往核对表 →',
        hint: a175Hint,
      },
      {
        id: 'independence',
        label: 'A17-7 独立性声明已签署（A 类必备）',
        satisfied: completionMap.value['A17-7'] === 'completed',
        actionTab: 'A17-7',
        actionLabel: '前往独立性 →',
        hint: completionMap.value['A17-7'] !== 'completed' ? '项目组成员尚未完成签署' : undefined,
      },
      {
        id: 'consultation',
        label: 'A17-3↔A17-3-1 咨询闭环（无咨询则自动满足）',
        satisfied: consultationPairing.value.closed,
        actionTab: consultationPairing.value.hasConsult ? 'A17-3-1' : undefined,
        actionLabel: '前往 A17-3-1 →',
        hint: consultationPairing.value.warning || undefined,
      },
      {
        id: 'disagreement',
        label: 'A17-4 专业分歧已闭环（无分歧则自动满足）',
        satisfied: disagreementClosure.value.closed,
        actionTab: disagreementClosure.value.hasDisagreement ? 'A17-4' : undefined,
        actionLabel: '前往 A17-4 →',
        hint: disagreementClosure.value.warning || undefined,
      },
      {
        id: 'consistency',
        label: '一致性校验无 error 级问题',
        satisfied: consistencyErrors.value.length === 0,
        actionTab: 'A17-1',
        actionLabel: '前往 A17-1 校验 →',
        hint: consistencyErrors.value.length
          ? consistencyErrors.value.slice(0, 2).map(e => e.description).join('；')
          : undefined,
      },
      {
        id: 'kam_stale',
        label: 'KAM 与审计报告一致（无过期）',
        satisfied: !kamStale.value,
        actionTab: 'A17-2-1',
        actionLabel: '前往 KAM →',
        hint: kamStale.value ? '请重新推送 KAM 至审计报告' : undefined,
      },
    ]
  })

  const signOffReady = computed(() => signOffPreconditions.value.every(p => p.satisfied))

  // ─── Data loading ───
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

  async function refreshCompletionStatus(): Promise<void> {
    const a17_1WpId = wpIdMap.value['A17-1'] || ''
    const a17_7WpId = wpIdMap.value['A17-7'] || ''
    const a17_3WpId = wpIdMap.value['A17-3'] || ''
    const a17_31WpId = wpIdMap.value['A17-3-1'] || ''
    const a17_4WpId = wpIdMap.value['A17-4'] || ''

    // Collect all applicable A17-5 wp_ids
    const a17_5WpIds = ['A17-5-1', 'A17-5-2', 'A17-5-3', 'A17-5-4', 'A17-5-5']
      .map(code => wpIdMap.value[code])
      .filter(Boolean)

    const [a17_1Res, a17_7Res, a17_3Res, a17_31Res, a17_4Res, ...a17_5Results] = await Promise.all([
      loadResponses(a17_1WpId),
      loadResponses(a17_7WpId),
      loadResponses(a17_3WpId),
      loadResponses(a17_31WpId),
      loadResponses(a17_4WpId),
      ...a17_5WpIds.map(id => loadResponses(id)),
    ])

    rawResponses.value = {
      'A17-1': a17_1Res,
      'A17-5': a17_5Results.flat(),
      'A17-7': a17_7Res,
      'A17-3': a17_3Res,
      'A17-3-1': a17_31Res,
      'A17-4': a17_4Res,
    }
  }

  async function refreshConsistencyCheck(): Promise<void> {
    const a171 = wpIdMap.value['A17-1']
    if (!projectId.value || !a171) {
      consistencyErrors.value = []
      return
    }
    try {
      const data = await api.post<any>('/api/a17/consistency-check', {
        project_id: projectId.value,
        wp_id: a171,
      }, { _silent: true } as any)
      const results = (data?.results || []) as Array<{ rule_id: string; severity: string; description: string }>
      consistencyErrors.value = results
        .filter(r => r.severity === 'error')
        .map(r => ({ rule_id: r.rule_id, description: r.description }))
    } catch {
      // 校验失败不阻断加载；签发时视为未通过更安全——保持上次结果
    }
  }

  async function refreshKamStale(): Promise<void> {
    const kamWp = wpIdMap.value['A17-2-1']
    if (!projectId.value || !kamWp) {
      kamStale.value = false
      return
    }
    try {
      const data = await api.get<any>('/api/a17/kam/stale-check', {
        params: { project_id: projectId.value, wp_id: kamWp },
        _silent: true,
      } as any)
      kamStale.value = !!data?.stale
    } catch {
      kamStale.value = false
    }
  }

  async function refreshIndependenceDrift(): Promise<void> {
    if (!projectId.value) {
      independenceDrift.value = { hasDrift: false, message: '' }
      return
    }
    try {
      const data = await api.get<any>('/api/a17/independence-drift', {
        params: { project_id: projectId.value },
        _silent: true,
      } as any)
      independenceDrift.value = {
        hasDrift: !!data?.has_drift,
        message: data?.message || '',
      }
    } catch {
      independenceDrift.value = { hasDrift: false, message: '' }
    }
  }

  async function refreshChapterStale(): Promise<void> {
    const a171 = wpIdMap.value['A17-1']
    if (!projectId.value || !a171) {
      chapterStale.value = []
      return
    }
    try {
      const data = await api.get<any>('/api/a17/chapters/stale-check', {
        params: { project_id: projectId.value, wp_id: a171 },
        _silent: true,
      } as any)
      chapterStale.value = data?.stale_chapters || []
    } catch {
      chapterStale.value = []
    }
  }

  async function refreshAgendaStale(): Promise<void> {
    const a176 = wpIdMap.value['A17-6']
    if (!projectId.value || !a176) {
      agendaStale.value = []
      return
    }
    try {
      const data = await api.get<any>('/api/a17/a176/agenda-stale-check', {
        params: { project_id: projectId.value, wp_id: a176 },
        _silent: true,
      } as any)
      agendaStale.value = data?.stale_items || []
    } catch {
      agendaStale.value = []
    }
  }

  async function refreshPartnerSummary(): Promise<void> {
    if (!projectId.value) {
      partnerSummary.value = null
      timeline.value = null
      return
    }
    try {
      const [summary, tl] = await Promise.all([
        api.get<any>('/api/a17/partner-summary', {
          params: { project_id: projectId.value },
          _silent: true,
        } as any),
        api.get<any>('/api/a17/report-date-timeline', {
          params: { project_id: projectId.value },
          _silent: true,
        } as any),
      ])
      partnerSummary.value = summary || null
      timeline.value = tl || null
    } catch {
      partnerSummary.value = null
      timeline.value = null
    }
  }

  async function refreshCrossAlerts(): Promise<void> {
    if (!projectId.value) {
      crossAlerts.value = []
      return
    }
    try {
      const data = await api.get<any>('/api/a17/cross-alerts', {
        params: { project_id: projectId.value },
        _silent: true,
      } as any)
      crossAlerts.value = data?.alerts || []
    } catch {
      crossAlerts.value = []
    }
  }

  async function refreshSignoffSelfCheck(): Promise<void> {
    if (!projectId.value) {
      signoffSelfCheck.value = null
      return
    }
    try {
      const data = await api.get<any>('/api/a17/signoff-self-check', {
        params: { project_id: projectId.value },
        _silent: true,
      } as any)
      signoffSelfCheck.value = data
        ? { ready: !!data.ready, items: data.items || [] }
        : null
    } catch {
      signoffSelfCheck.value = null
    }
  }

  async function loadKamReferences(): Promise<void> {
    if (!projectId.value) {
      kamReferences.value = []
      return
    }
    try {
      const data = await api.get(`/api/projects/${projectId.value}/kam-references`, {
        _silent: true,
      } as any)
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
    consultationPairing,
    disagreementClosure,
    consistencyErrors,
    signOffPreconditions,
    signOffReady,
    kamReferences,
    kamStale,
    independenceDrift,
    chapterStale,
    agendaStale,
    partnerSummary,
    timeline,
    crossAlerts,
    signoffSelfCheck,
    refreshCompletionStatus,
    refreshConsistencyCheck,
    refreshKamStale,
    refreshIndependenceDrift,
    refreshChapterStale,
    refreshAgendaStale,
    refreshPartnerSummary,
    refreshCrossAlerts,
    refreshSignoffSelfCheck,
    loadKamReferences,
  }
}
