/**
 * useKCycleEditor — K 管理费用循环专属逻辑 composable
 *
 * 锚定 spec workpaper-editor-refactor Phase 3 Task 3.6
 *
 * K 循环在 WorkpaperEditor.vue 中的独占代码：
 * - K8/K9 费用分析弹窗（ExpenseAnalysisDialog）触发
 * - K11 跨循环减值汇总弹窗（ImpairmentSummaryDialog）触发
 *
 * 本 composable 封装：
 * 1. K 循环弹窗 visible refs（委托 useCycleDialogs 已有的 expenseAnalysis/impairmentSummary）
 * 2. K 循环特有的 trigger 判定（基于 wpCode）
 * 3. onExpenseAnalysisApplied / onImpairmentSummaryApplied handlers
 *
 * K 循环比 G/H/I 更简单：无分支选择器（branch selector）。
 *
 * 遵循 CycleEditorAPI 接口模式（design.md）：
 * - dialogs: { [key]: Ref<boolean> }
 * - triggers: { [key]: ComputedRef<boolean> }
 * - handlers: { [key]: (...args) => void | Promise<void> }
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { CycleDialogsAPI } from './useCycleDialogs'

// ─── 接口定义 ─────────────────────────────────────────────────────────────────

export interface KCycleDialogs {
  /** K8/K9 费用分析弹窗 visible（委托 useCycleDialogs.expenseAnalysis） */
  expenseAnalysisDialogVisible: Ref<boolean>
  /** K11 跨循环减值汇总弹窗 visible（委托 useCycleDialogs.impairmentSummary） */
  impairmentSummaryDialogVisible: Ref<boolean>
}

export interface KCycleTriggers {
  /** 是否为 K 循环底稿 */
  isKCycle: ComputedRef<boolean>
  /** 是否显示费用分析按钮（K8/K9 开头的底稿） */
  showExpenseAnalysisTrigger: ComputedRef<boolean>
  /** 是否显示减值汇总按钮（K11 开头的底稿） */
  showImpairmentSummaryTrigger: ComputedRef<boolean>
}

export interface KCycleHandlers {
  /** 费用分析写回通知 */
  onExpenseAnalysisApplied: (sheet: string) => void
  /** 减值汇总写回通知 */
  onImpairmentSummaryApplied: (sheet: string) => void
}

export interface KCycleEditorAPI {
  dialogs: KCycleDialogs
  triggers: KCycleTriggers
  handlers: KCycleHandlers
}

// ─── Composable 实现 ──────────────────────────────────────────────────────────

/**
 * K 管理费用循环编辑器 composable
 *
 * @param wpDetail - 当前底稿详情（含 wp_code）
 * @param cycleDialogs - 统一弹窗管理（委托 visible/trigger/onApplied）
 */
export function useKCycleEditor(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  cycleDialogs: CycleDialogsAPI,
): KCycleEditorAPI {
  // ─── Dialogs（委托 useCycleDialogs 已有的 K 循环弹窗） ─────────────────────────
  const dialogs: KCycleDialogs = {
    expenseAnalysisDialogVisible: cycleDialogs.expenseAnalysis.visible,
    impairmentSummaryDialogVisible: cycleDialogs.impairmentSummary.visible,
  }

  // ─── Triggers（委托 useCycleDialogs 已有的 trigger computed） ───────────────────
  const wpCode = computed(() => (wpDetail.value?.wp_code || '').toUpperCase())

  const triggers: KCycleTriggers = {
    isKCycle: computed(() => /^K\d/.test(wpCode.value)),
    showExpenseAnalysisTrigger: cycleDialogs.expenseAnalysis.trigger,
    showImpairmentSummaryTrigger: cycleDialogs.impairmentSummary.trigger,
  }

  // ─── Handlers ──────────────────────────────────────────────────────────────

  /** 费用分析写回通知（委托 useCycleDialogs.expenseAnalysis.onApplied） */
  function onExpenseAnalysisApplied(sheet: string) {
    cycleDialogs.expenseAnalysis.onApplied(sheet)
  }

  /** 减值汇总写回通知（委托 useCycleDialogs.impairmentSummary.onApplied） */
  function onImpairmentSummaryApplied(sheet: string) {
    cycleDialogs.impairmentSummary.onApplied(sheet)
  }

  const handlers: KCycleHandlers = {
    onExpenseAnalysisApplied,
    onImpairmentSummaryApplied,
  }

  return { dialogs, triggers, handlers }
}
