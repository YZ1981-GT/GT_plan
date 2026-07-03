/**
 * useReviewDialogProvider — 全局复核对话激活机制
 *
 * 顶层组件（如 WorkpaperEditor.vue）调用 useReviewDialogProvider() 并在 template 中
 * 放置 `<GtReviewDialog v-if="isOpen" v-bind="activationParams" />`。
 *
 * 子组件通过 useReviewDialogInject() 获取 openReviewDialog / closeReviewDialog。
 *
 * @see .kiro/specs/audit-review-dialog/design.md §全局激活机制设计
 */
import { ref, provide, inject, type Ref, type InjectionKey } from 'vue'
import type { SenderRole } from './useReviewDialog'

// ── 激活参数接口 ─────────────────────────────────────────────────────────────

export interface ReviewDialogActivation {
  wpId: string
  sectionId: string
  sectionLabel: string
  currentUser: { id: string; name: string; role: SenderRole }
  relatedData?: Record<string, unknown>
}

// ── Provider 上下文接口 ──────────────────────────────────────────────────────

export interface ReviewDialogContext {
  openReviewDialog: (params: ReviewDialogActivation) => void
  closeReviewDialog: () => void
  isOpen: Ref<boolean>
  activationParams: Ref<ReviewDialogActivation | null>
}

// ── InjectionKey ─────────────────────────────────────────────────────────────

export const REVIEW_DIALOG_KEY: InjectionKey<ReviewDialogContext> = Symbol('reviewDialog')

// ── Provider（顶层组件调用）──────────────────────────────────────────────────

/**
 * 在顶层组件中调用，provide 全局复核对话激活能力。
 *
 * @example
 * // WorkpaperEditor.vue <script setup>
 * const { isOpen, activationParams } = useReviewDialogProvider()
 *
 * // template:
 * // <GtReviewDialog v-if="isOpen" v-bind="activationParams" />
 */
export function useReviewDialogProvider(): ReviewDialogContext {
  const isOpen = ref(false)
  const activationParams = ref<ReviewDialogActivation | null>(null)

  function openReviewDialog(params: ReviewDialogActivation): void {
    activationParams.value = params
    isOpen.value = true
  }

  function closeReviewDialog(): void {
    isOpen.value = false
    activationParams.value = null
  }

  const ctx: ReviewDialogContext = {
    openReviewDialog,
    closeReviewDialog,
    isOpen,
    activationParams,
  }

  provide(REVIEW_DIALOG_KEY, ctx)

  // 同时 provide 简化版 openReviewDialog 供已有子组件 inject('openReviewDialog') 使用
  // （D1TabAdjudication 等已通过 inject('openReviewDialog') 调用）
  provide('openReviewDialog', (params: Omit<ReviewDialogActivation, 'wpId' | 'currentUser'> & { wpId?: string; currentUser?: ReviewDialogActivation['currentUser'] }) => {
    // 子组件可能不传 wpId/currentUser（从 activationParams 中上次的值继承）
    const merged: ReviewDialogActivation = {
      wpId: params.wpId ?? activationParams.value?.wpId ?? '',
      sectionId: params.sectionId,
      sectionLabel: params.sectionLabel,
      currentUser: params.currentUser ?? activationParams.value?.currentUser ?? { id: '', name: '', role: '审计助理' },
      relatedData: params.relatedData,
    }
    openReviewDialog(merged)
  })

  return ctx
}

// ── Inject（子组件调用）──────────────────────────────────────────────────────

/**
 * 子组件注入复核对话上下文。若未找到 provider 则返回 no-op 安全默认值。
 */
export function useReviewDialogInject(): ReviewDialogContext {
  const ctx = inject(REVIEW_DIALOG_KEY)
  if (ctx) return ctx
  // 安全降级：不在 provider 下也不崩溃
  return {
    openReviewDialog: () => { console.warn('[useReviewDialogInject] 未找到 ReviewDialog provider') },
    closeReviewDialog: () => {},
    isOpen: ref(false),
    activationParams: ref(null),
  }
}
