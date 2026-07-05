/**
 * useG1ReviewDialogProvide — G1 交易性金融资产入口复核对话 provider
 *
 * GtG1TradingFinancialAssets.vue 主入口调用，provide('openReviewDialog') 供各 section 标题栏
 * 复核按钮 inject。子组件通过 inject('openReviewDialog')(sectionId) 触发复核对话。
 *
 * @see useG0ReviewDialogProvide / useF2ReviewDialogProvide（同源模式）
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

export function useG1ReviewDialogProvide(options: {
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
