/**
 * H 循环披露说明 AI 辅助 + 复核的统一接线（薄封装 `useDisclosureNoteAi`）
 *
 * 收敛 12 个披露 Tab 的重复样板：每个 Tab 只声明「键 → 读/写函数」，
 * sectionId 构造、中文名、context、复核弹窗注入全在此处一次做对。
 *
 * 🔴 必须在 **setup 顶层** 调用（内部 `inject('openReviewDialog')`）；
 * 写进事件处理函数体里会静默拿不到 provide 值（平台已踩过 3 次同款坑）。
 *
 * spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R2 / R3
 */
import { computed, inject, type ComputedRef } from 'vue'

import { useDisclosureNoteAi } from './useDisclosureNoteAi'

export interface HCycleAiField {
  get: () => string
  set: (v: string) => void
}

export interface UseHCycleDisclosureAiOptions {
  /** 循环码，如 `H8`；与后端 prompt 键前缀一致 */
  wpCode: string
  /** 变体，`listed` | `soe` */
  variant: string
  wpId: () => string | undefined
  isReadonly: () => boolean
  /** 附注章节号（进 AI context，便于模型知道在写哪一节） */
  noteSectionId: string
  /** 键 → 中文名（供复核弹窗标题与 AI context） */
  labels: Record<string, string>
  /** 键 → 读写函数 */
  fields: Record<string, HCycleAiField>
}

export interface HCycleDisclosureAi {
  /** 当前正在生成的键（''=空闲），供按钮 `:loading` */
  aiLoadingSection: ComputedRef<string>
  runAi: (key: string) => Promise<void>
  openReview: (key: string) => void
}

const VARIANT_LABEL: Record<string, string> = {
  listed: '上市公司',
  soe: '国有企业',
}

export function useHCycleDisclosureAi(opts: UseHCycleDisclosureAiOptions): HCycleDisclosureAi {
  const openReviewDialog = inject<((payload: Record<string, unknown>) => void) | null>(
    'openReviewDialog',
    null,
  )

  const labelOf = (key: string): string => opts.labels[key] ?? key

  const { aiLoadingSection, runAi, openReview } = useDisclosureNoteAi({
    wpId: () => opts.wpId(),
    isReadonly: opts.isReadonly,
    getText: (key) => opts.fields[key]?.get() ?? '',
    setText: (key, text) => opts.fields[key]?.set(text),
    buildSectionId: (key) => `${opts.wpCode}-disclosure-${opts.variant}-${key}`,
    labelOf,
    buildContext: (key) => ({
      变体: VARIANT_LABEL[opts.variant] ?? opts.variant,
      章节: opts.noteSectionId,
      子节: labelOf(key),
    }),
    openReviewDialog,
  })

  return {
    aiLoadingSection: computed(() => aiLoadingSection.value),
    runAi,
    openReview,
  }
}

export default useHCycleDisclosureAi
