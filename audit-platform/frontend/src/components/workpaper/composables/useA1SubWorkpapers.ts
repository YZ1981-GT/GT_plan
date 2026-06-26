/**
 * useA1SubWorkpapers — A1 Dashboard 子底稿（A1-11~A1-16）管理 composable
 *
 * 职责：
 * 1. wp_id 解析：通过 getWpIndex 获取子底稿 wp_id 映射
 * 2. 可见性控制：仅显示项目中存在的子底稿 Tab
 * 3. 依赖锁定：A17→A1-11（签发）、A1-11→A1-15（归档）
 * 4. EventBus 集成：监听 A17 完成 / A1-11 签发事件
 * 5. 进度集成：子底稿完成数纳入进度环计算
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { getWpIndex } from '@/services/workpaperApi'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───

export type CompletionStatus = 'completed' | 'in_progress' | 'not_started'

export interface A1SubTab {
  id: string
  label: string
  wpCode: string
  componentType: 'signing-form' | 'checklist' | 'analytical-review' | 'a1-12-dual-checklist' | 'a1-15-disclosure-checklist'
  dependsOn?: string
}

export interface UseA1SubWorkpapersOptions {
  projectId: Ref<string>
  wpId: Ref<string>
}

export interface UseA1SubWorkpapersReturn {
  wpIdMap: Ref<Record<string, string>>
  loading: Ref<boolean>
  visibleTabs: ComputedRef<A1SubTab[]>
  hasAnySubTab: ComputedRef<boolean>
  isA17Completed: Ref<boolean>
  isA111Signed: Ref<boolean>
  isA111Locked: ComputedRef<boolean>
  isA115Locked: ComputedRef<boolean>
  a111LockReason: ComputedRef<string>
  a115LockReason: ComputedRef<string>
  subWorkpaperCompletions: ComputedRef<Record<string, CompletionStatus>>
  subCompletedCount: ComputedRef<number>
  subTotalCount: ComputedRef<number>
  loadWpIndex: () => Promise<void>
  refreshDependencyStatus: () => Promise<void>
  setupEventListeners: () => void
  cleanup: () => void
}

// ─── Constants ───

export const A1_SUB_TABS: A1SubTab[] = [
  { id: 'A1-11', label: '签发流转控制表', wpCode: 'A1-11', componentType: 'signing-form', dependsOn: 'a17-completed' },
  { id: 'A1-12', label: '重大事项决定程序的履行情况检查表', wpCode: 'A1-12', componentType: 'a1-12-dual-checklist' },
  { id: 'A1-13', label: '分析性复核（母公司）', wpCode: 'A1-13', componentType: 'analytical-review' },
  { id: 'A1-14', label: '分析性复核（合并）', wpCode: 'A1-14', componentType: 'analytical-review' },
  { id: 'A1-15', label: '企业会计准则财务报表系列及勾稽对照表', wpCode: 'A1-15', componentType: 'a1-15-disclosure-checklist', dependsOn: 'a111-signed' },
  { id: 'A1-16', label: '上市公司额外披露要求审核对比表', wpCode: 'A1-16', componentType: 'checklist' },
  { id: 'A1-17', label: '对应数据', wpCode: 'A1-17', componentType: 'checklist' },
  { id: 'A1-18', label: '实际抽样比及工时用量记录', wpCode: 'A1-18', componentType: 'checklist' },
]

// ─── Composable ───

export function useA1SubWorkpapers(options: UseA1SubWorkpapersOptions): UseA1SubWorkpapersReturn {
  const { projectId } = options

  // ─── State ───
  const wpIdMap = ref<Record<string, string>>({})
  const loading = ref(false)
  const isA17Completed = ref(false)
  const isA111Signed = ref(false)

  // ─── Computed: visibility ───
  const visibleTabs = computed(() =>
    A1_SUB_TABS.filter(tab => !!wpIdMap.value[tab.wpCode]),
  )
  const hasAnySubTab = computed(() => visibleTabs.value.length > 0)

  // ─── Computed: dependency locking ───
  const isA111Locked = computed(() => !isA17Completed.value)
  const isA115Locked = computed(() => !isA111Signed.value)
  const a111LockReason = computed(() =>
    isA111Locked.value ? 'A17 审计总结未完成，无法进行签发操作' : '',
  )
  const a115LockReason = computed(() =>
    isA115Locked.value ? 'A1-11 签发流转控制表未完成，无法进行归档检查' : '',
  )

  // ─── Computed: progress integration ───
  const subWorkpaperCompletions = computed<Record<string, CompletionStatus>>(() => {
    const map: Record<string, CompletionStatus> = {}
    for (const tab of A1_SUB_TABS) {
      if (!wpIdMap.value[tab.wpCode]) continue
      if (tab.id === 'A1-11') {
        map[tab.id] = isA111Signed.value ? 'completed' : 'not_started'
      } else {
        map[tab.id] = 'not_started'
      }
    }
    return map
  })

  const subCompletedCount = computed(() =>
    Object.values(subWorkpaperCompletions.value).filter(s => s === 'completed').length,
  )
  const subTotalCount = computed(() =>
    Object.keys(subWorkpaperCompletions.value).length,
  )

  // ─── Actions ───

  async function loadWpIndex(): Promise<void> {
    if (!projectId.value) return
    loading.value = true
    try {
      const items = await getWpIndex(projectId.value)
      const map: Record<string, string> = {}
      for (const item of items) {
        if (item.wp_code && /^A1-1[1-8]$/.test(item.wp_code)) {
          map[item.wp_code] = (item as any).wp_id || item.id
        }
      }
      wpIdMap.value = map
    } catch {
      wpIdMap.value = {}
    } finally {
      loading.value = false
    }
  }

  async function refreshDependencyStatus(): Promise<void> {
    // Check A1-11 sign status
    if (wpIdMap.value['A1-11']) {
      try {
        const responses = await api.get(`/api/workpapers/${wpIdMap.value['A1-11']}/checklist-responses`, {
          params: { project_id: projectId.value },
          _silent: true,
        } as any)
        const signItem = (responses as any[])?.find((r: any) => r.item_id === 'sign-status')
        isA111Signed.value = signItem?.conclusion === 'signed'
      } catch {
        isA111Signed.value = false
      }
    }

    // Check A17 completion via project-level flag
    try {
      const data = await api.get(`/api/projects/${projectId.value}/completion-flags`, {
        _silent: true,
      } as any)
      isA17Completed.value = !!(data as any)?.a17_completed
    } catch {
      // API may not exist yet — default to locked (safe side)
      isA17Completed.value = false
    }
  }

  // ─── EventBus ───

  function handleA17Completed() {
    isA17Completed.value = true
  }

  function handleA111Signed() {
    isA111Signed.value = true
  }

  function setupEventListeners() {
    eventBus.on('a17-audit-summary-completed', handleA17Completed)
    eventBus.on('a1-11-signing-completed', handleA111Signed)
  }

  function cleanup() {
    eventBus.off('a17-audit-summary-completed', handleA17Completed)
    eventBus.off('a1-11-signing-completed', handleA111Signed)
  }

  return {
    wpIdMap,
    loading,
    visibleTabs,
    hasAnySubTab,
    isA17Completed,
    isA111Signed,
    isA111Locked,
    isA115Locked,
    a111LockReason,
    a115LockReason,
    subWorkpaperCompletions,
    subCompletedCount,
    subTotalCount,
    loadWpIndex,
    refreshDependencyStatus,
    setupEventListeners,
    cleanup,
  }
}
