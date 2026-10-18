/**
 * useSignoffChecklist — 签发一致性清单 composable（P2-2）
 *
 * 提供合伙人签发页的一致性清单数据获取、确认、阻断判断逻辑。
 * Requirements: 5.1, 5.2, 5.3
 */
import { ref, computed, readonly } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { isRequestCancelled } from '@/utils/http'

/** 后端错误文案（HTTPException.detail / 信封 message），取不到用兜底文案 */
function errorText(e: any, fallback: string): string {
  const data = e?.response?.data
  const detail = data?.detail ?? data?.message
  return typeof detail === 'string' && detail ? detail : fallback
}
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

      // 错误由本组件的错误态展示（_silent：不再叠一个全局 toast）
      const data: any = await api.get(
        `/api/projects/${projectId}/signoff/checklist`,
        { params, _silent: true } as any,
      )
      checklist.value = data as SignoffChecklist
    } catch (e: any) {
      if (isRequestCancelled(e)) return
      error.value = errorText(e, '获取清单失败')
      checklist.value = null
    } finally {
      loading.value = false
    }
  }

  /**
   * 合伙人确认单个 warning 项。
   * 只有后端留痕写入成功才记为已确认 —— 确认是审计证据，留痕失败时「已确认」等于没确认
   * （历史实现先本地记已确认、留痕失败只打 console）。
   */
  async function confirmWarning(itemIndex: number, userId: string): Promise<boolean> {
    try {
      await api.post(
        `/api/projects/${projectId}/signoff/confirm-warning`,
        {
          item_index: itemIndex,
          item_message: checklist.value?.items[itemIndex]?.message ?? '',
          item_category: checklist.value?.items[itemIndex]?.category ?? '',
        },
        { _silent: true } as any,
      )
    } catch (e: any) {
      ElMessage.error(errorText(e, '确认记录写入失败，请稍后重试'))
      return false
    }
    warningConfirmations.value.set(itemIndex, {
      itemIndex,
      confirmedAt: new Date().toISOString(),
      confirmedBy: userId,
    })
    return true
  }

  /** 批量确认所有 warning 项 */
  async function confirmAllWarnings(userId: string) {
    if (!checklist.value) return
    const pending = checklist.value.items
      .map((item, idx) => ({ item, idx }))
      .filter(({ item, idx }) => item.severity === 'warning' && !warningConfirmations.value.has(idx))
    // 逐项确认，遇到失败即停（只提示一次，未确认的项保持未确认）
    for (const { idx } of pending) {
      if (!(await confirmWarning(idx, userId))) return
    }
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
