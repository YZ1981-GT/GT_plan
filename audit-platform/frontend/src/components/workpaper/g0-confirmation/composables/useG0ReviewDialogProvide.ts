/**
 * useG0ReviewDialogProvide — G0 投资循环函证入口复核对话 provider
 *
 * G0-3(证券)/G0-6 主入口调用，provide('openReviewDialog') 供 section 标题栏复核按钮 inject。
 * sectionId 字符串映射为 ReviewDialogActivation 并挂载 GtReviewDialog。
 *
 * @see useF2ReviewDialogProvide（同源模式）
 */
import { provide, type Ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import type { SenderRole } from '@/composables/useReviewDialog'
import { useReviewDialogProvider } from '@/composables/useReviewDialogProvider'

function mapUserRole(role: string | undefined): SenderRole {
  const m: Record<string, SenderRole> = {
    partner: '业务合伙人',
    manager: '现场经理',
    eqcr: 'EQCR技术复核人',
    qc: '质量控制复核合伙人',
    qc_partner: '质量控制复核合伙人',
  }
  return m[role ?? ''] ?? '审计助理'
}

export function useG0ReviewDialogProvide(options: {
  wpId: Ref<string>
  projectId?: Ref<string>
}) {
  const auth = useAuthStore()
  const ctx = useReviewDialogProvider()

  function openReviewBySectionId(sectionId: string): void {
    const user = auth.user
    ctx.openReviewDialog({
      wpId: options.wpId.value,
      sectionId,
      sectionLabel: sectionId,
      currentUser: {
        id: user?.id ?? '',
        name: user?.full_name || user?.username || '当前用户',
        role: mapUserRole(user?.role),
      },
      relatedData: options.projectId ? { projectId: options.projectId.value } : undefined,
    })
  }

  provide('openReviewDialog', openReviewBySectionId)

  return ctx
}
