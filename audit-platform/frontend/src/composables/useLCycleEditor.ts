/**
 * useLCycleEditor — L 筹资循环专属逻辑 composable
 *
 * 锚定 spec workpaper-editor-refactor Phase 3 Task 3.7
 *
 * L 循环在 WorkpaperEditor.vue 中的独占代码：
 * - L1/L3 利息测算弹窗（InterestCalcDialog）触发
 * - L5 摊余成本弹窗（BondAmortizationDialog）触发
 *
 * 本 composable 封装：
 * 1. L 循环弹窗 visible refs（委托 useCycleDialogs 已有的 interestCalc/bondAmortization）
 * 2. L 循环特有的 trigger 判定（基于 wpCode）
 * 3. onInterestCalcApplied / onBondAmortizationApplied handlers
 *
 * L 循环比 G/H/I 更简单：无分支选择器（branch selector）。
 *
 * 遵循 CycleEditorAPI 接口模式（design.md）：
 * - dialogs: { [key]: Ref<boolean> }
 * - triggers: { [key]: ComputedRef<boolean> }
 * - handlers: { [key]: (...args) => void | Promise<void> }
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { CycleDialogsAPI } from './useCycleDialogs'

// ─── 接口定义 ─────────────────────────────────────────────────────────────────

export interface LCycleDialogs {
  /** L1/L3 利息测算弹窗 visible（委托 useCycleDialogs.interestCalc） */
  interestCalcDialogVisible: Ref<boolean>
  /** L5 摊余成本弹窗 visible（委托 useCycleDialogs.bondAmortization） */
  bondAmortizationDialogVisible: Ref<boolean>
}

export interface LCycleTriggers {
  /** 是否为 L 循环底稿 */
  isLCycle: ComputedRef<boolean>
  /** 是否显示利息测算按钮（L1/L3 开头的底稿） */
  showInterestCalcTrigger: ComputedRef<boolean>
  /** 是否显示摊余成本按钮（L5 开头的底稿） */
  showBondAmortizationTrigger: ComputedRef<boolean>
}

export interface LCycleHandlers {
  /** 利息测算写回通知 */
  onInterestCalcApplied: (sheet: string) => void
  /** 摊余成本写回通知 */
  onBondAmortizationApplied: (sheet: string) => void
}

export interface LCycleEditorAPI {
  dialogs: LCycleDialogs
  triggers: LCycleTriggers
  handlers: LCycleHandlers
}

// ─── Composable 实现 ──────────────────────────────────────────────────────────

/**
 * L 筹资循环编辑器 composable
 *
 * @param wpDetail - 当前底稿详情（含 wp_code）
 * @param cycleDialogs - 统一弹窗管理（委托 visible/trigger/onApplied）
 */
export function useLCycleEditor(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  cycleDialogs: CycleDialogsAPI,
): LCycleEditorAPI {
  // ─── Dialogs（委托 useCycleDialogs 已有的 L 循环弹窗） ─────────────────────────
  const dialogs: LCycleDialogs = {
    interestCalcDialogVisible: cycleDialogs.interestCalc.visible,
    bondAmortizationDialogVisible: cycleDialogs.bondAmortization.visible,
  }

  // ─── Triggers（委托 useCycleDialogs 已有的 trigger computed） ───────────────────
  const wpCode = computed(() => (wpDetail.value?.wp_code || '').toUpperCase())

  const triggers: LCycleTriggers = {
    isLCycle: computed(() => /^L\d/.test(wpCode.value)),
    showInterestCalcTrigger: cycleDialogs.interestCalc.trigger,
    showBondAmortizationTrigger: cycleDialogs.bondAmortization.trigger,
  }

  // ─── Handlers ──────────────────────────────────────────────────────────────

  /** 利息测算写回通知（委托 useCycleDialogs.interestCalc.onApplied） */
  function onInterestCalcApplied(sheet: string) {
    cycleDialogs.interestCalc.onApplied(sheet)
  }

  /** 摊余成本写回通知（委托 useCycleDialogs.bondAmortization.onApplied） */
  function onBondAmortizationApplied(sheet: string) {
    cycleDialogs.bondAmortization.onApplied(sheet)
  }

  const handlers: LCycleHandlers = {
    onInterestCalcApplied,
    onBondAmortizationApplied,
  }

  return { dialogs, triggers, handlers }
}
