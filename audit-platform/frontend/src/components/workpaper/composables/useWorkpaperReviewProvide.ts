/**
 * useWorkpaperReviewProvide — 循环底稿通用复核对话 provider（D1–D7 等）
 *
 * 须在同组件 template 内挂载 GtWpReviewDialogHost（及可选 GtWpReviewRail）。
 */
import { provide, type Ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import type { SenderRole } from '@/composables/useReviewDialog'
import { useReviewDialogProvider } from '@/composables/useReviewDialogProvider'

export type WorkpaperOpenReviewParams = {
  sectionId: string
  sectionLabel?: string
  relatedData?: Record<string, unknown>
}

export type WorkpaperOpenReviewFn = (sectionIdOrParams: string | WorkpaperOpenReviewParams) => void

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

function normalizeParams(sectionIdOrParams: string | WorkpaperOpenReviewParams): WorkpaperOpenReviewParams {
  if (typeof sectionIdOrParams === 'string') {
    return { sectionId: sectionIdOrParams, sectionLabel: sectionIdOrParams }
  }
  return {
    sectionId: sectionIdOrParams.sectionId,
    sectionLabel: sectionIdOrParams.sectionLabel ?? sectionIdOrParams.sectionId,
    relatedData: sectionIdOrParams.relatedData,
  }
}

export function useWorkpaperReviewProvide(options: {
  wpId: Ref<string>
  projectId?: Ref<string>
}) {
  const auth = useAuthStore()
  const ctx = useReviewDialogProvider()

  const openReview: WorkpaperOpenReviewFn = (sectionIdOrParams) => {
    const params = normalizeParams(sectionIdOrParams)
    const user = auth.user
    ctx.openReviewDialog({
      wpId: options.wpId.value,
      sectionId: params.sectionId,
      sectionLabel: params.sectionLabel ?? params.sectionId,
      currentUser: {
        id: user?.id ?? '',
        name: user?.full_name || user?.username || '当前用户',
        role: mapUserRole(user?.role),
      },
      relatedData: params.relatedData
        ?? (options.projectId ? { projectId: options.projectId.value } : undefined),
    })
  }

  provide('openReviewDialog', openReview)

  return ctx
}

export default useWorkpaperReviewProvide
