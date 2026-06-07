/**
 * useSignoffChecklist — 签发一致性清单 composable（P2-2）
 *
 * 提供合伙人签发页的一致性清单数据获取、确认、阻断判断逻辑。
 * Requirements: 5.1, 5.2, 5.3
 */
import { ref, computed, readonly } from 'vue'
import { api } from '@/services/apiProxy'
import type { LinkageContract } from '@/types/linkageContract'

/** 检查结果严重级别 */
export type CheckSeverity = 'blocking' | 'warning' | 'info'

/** 单项检查结果 */
export interface CheckItem {
  severity: CheckSeverity
  category: string
  message: string
  contract?: LinkageContract | null
  route?: string | null
}

/** 签发一致性清单 */
export interface SignoffChecklist {
  project_id: string
  year: number
  items: CheckItem[]
  can_signoff: boolean
  has_warnings: boolean
}

/** 确认记录 */
export interface WarningConfirmation {
  itemIndex: number
  confirmedAt: string
  confirmedBy: string
}

export function useSignoffChecklist(projectId: string) {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const checklist = ref<SignoffChecklist | null>(null)
  const warningConfirmations = ref<Map<number, WarningConfirmation>>(new Map())

  // ─── 计算属性 ────────────────────────────────────────────────────

  const blockingItems = computed(() =>
    checklist.value?.items.filter((i) => i.severity === 'blocking') ?? [],
  )

  const warningItems = computed(() =>
    checklist.value?.items.filter((i) => i.severity === 'warning') ?? [],
  )

  const infoItems = computed(() =>
    checklist.value?.items.filter((i) => i.severity === 'info') ?? [],
  )

  /** 所有 warning 项是否已确认 */
  const allWarningsConfirmed = computed(() => {
    if (!warningItems.value.length) return true
    return warningItems.value.every((_, idx) => {
      const globalIdx = checklist.value?.items.indexOf(warningItems.value[idx]) ?? -1
      return warningConfirmations.value.has(globalIdx)
    })
  })

  /** 是否可签发：无 blocking + 所有 warning 已确认 */
  const canSignoff = computed(() => {
    if (!checklist.value) return false
    if (blockingItems.value.length > 0) return false
    if (warningItems.value.length > 0 && !allWarningsConfirmed.value) return false
    return true
  })

  // ─── 方法 ────────────────────────────────────────────────────────

  /** 获取签发一致性清单 */
  async function fetchChecklist(year?: number) {
    loading.value = true
    error.value = null
    warningConfirmations.value.clear()
    try {
      const params: Record<string, string> = {}
      if (year) params.year = String(year)

      const data: any = await api.get(
        `/api/projects/${projectId}/signoff/checklist`,
        { params },
      )
      checklist.value = data as SignoffChecklist
    } catch (e: any) {
      error.value = e?.message || '获取清单失败'
      checklist.value = null
    } finally {
      loading.value = false
    }
  }

  /** 合伙人确认单个 warning 项 */
  async function confirmWarning(itemIndex: number, userId: string) {
    const confirmation: WarningConfirmation = {
      itemIndex,
      confirmedAt: new Date().toISOString(),
      confirmedBy: userId,
    }
    warningConfirmations.value.set(itemIndex, confirmation)

    // 记录审计日志
    try {
      await api.post(`/api/projects/${projectId}/signoff/confirm-warning`, {
        item_index: itemIndex,
        item_message: checklist.value?.items[itemIndex]?.message ?? '',
        item_category: checklist.value?.items[itemIndex]?.category ?? '',
      })
    } catch (e) {
      // 审计日志写入失败不阻断操作
      console.warn('审计日志写入失败:', e)
    }
  }

  /** 批量确认所有 warning 项 */
  async function confirmAllWarnings(userId: string) {
    if (!checklist.value) return
    const promises: Promise<void>[] = []
    checklist.value.items.forEach((item, idx) => {
      if (item.severity === 'warning' && !warningConfirmations.value.has(idx)) {
        promises.push(confirmWarning(idx, userId))
      }
    })
    await Promise.all(promises)
  }

  /** 重置清单 */
  function reset() {
    checklist.value = null
    warningConfirmations.value.clear()
    error.value = null
  }

  return {
    loading: readonly(loading),
    error: readonly(error),
    checklist: readonly(checklist),
    blockingItems,
    warningItems,
    infoItems,
    allWarningsConfirmed,
    canSignoff,
    warningConfirmations: readonly(warningConfirmations),
    fetchChecklist,
    confirmWarning,
    confirmAllWarnings,
    reset,
  }
}
