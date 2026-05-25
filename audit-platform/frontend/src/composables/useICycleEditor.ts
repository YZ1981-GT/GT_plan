/**
 * useICycleEditor — I 无形资产循环专属逻辑 composable
 *
 * 锚定 spec workpaper-editor-refactor Phase 3 Task 3.4
 *
 * I 循环在 WorkpaperEditor.vue 中的独占代码：
 * - I3 商誉减值 DCF 分析弹窗（GoodwillImpairmentDialog）触发
 * - I2 资本化时点判断弹窗（CapitalizationCheckDialog）触发
 * - I1/I4 摊销自动测算弹窗（AmortizationCalcDialog）触发
 * - I 循环摊销分支选择器（DepreciationBranchSelector — I1-10/I1-11 / I4-6/I4-7）
 *
 * 本 composable 封装：
 * 1. I 循环弹窗 visible refs（委托 useCycleDialogs 已有的 goodwillImpairment/capitalizationCheck/amortizationCalc）
 * 2. I 循环特有的 trigger 判定（基于 wpCode + activeSheetId）
 * 3. 摊销分支选择器（委托 useDepreciationBranchSelector — I 循环模式）
 * 4. onGoodwillImpairmentApplied / onCapitalizationCheckApplied / onAmortizationCalcApplied handlers
 *
 * 遵循 CycleEditorAPI 接口模式（design.md）：
 * - dialogs: { [key]: Ref<boolean> }
 * - triggers: { [key]: ComputedRef<boolean> }
 * - handlers: { [key]: (...args) => void | Promise<void> }
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { CycleDialogsAPI } from './useCycleDialogs'
import type { SheetNavFacadeAPI } from './useSheetNavFacade'
import { useDepreciationBranchSelector, type BranchOption } from './useDepreciationBranchSelector'

// ─── 接口定义 ─────────────────────────────────────────────────────────────────

export interface ICycleDialogs {
  /** 商誉减值 DCF 分析弹窗 visible（委托 useCycleDialogs.goodwillImpairment） */
  goodwillImpairmentDialogVisible: Ref<boolean>
  /** 资本化时点判断弹窗 visible（委托 useCycleDialogs.capitalizationCheck） */
  capitalizationCheckDialogVisible: Ref<boolean>
  /** 摊销自动测算弹窗 visible（委托 useCycleDialogs.amortizationCalc） */
  amortizationCalcDialogVisible: Ref<boolean>
}

export interface ICycleTriggers {
  /** 是否为 I 循环底稿 */
  isICycle: ComputedRef<boolean>
  /** 是否显示商誉减值分析按钮（I3 商誉减值类 sheet） */
  showGoodwillImpairmentTrigger: ComputedRef<boolean>
  /** 是否显示资本化时点判断按钮（I2-6 资本化时点 sheet） */
  showCapitalizationCheckTrigger: ComputedRef<boolean>
  /** 摊销测算 section（I1 或 I4，null 表示不在摊销 sheet） */
  amortizationCalcSection: ComputedRef<'I1' | 'I4' | null>
}

export interface ICycleHandlers {
  /** 商誉减值分析写回通知 */
  onGoodwillImpairmentApplied: (sheet: string) => void
  /** 资本化时点判断写回通知 */
  onCapitalizationCheckApplied: (sheet: string) => void
  /** 摊销测算写回通知 */
  onAmortizationCalcApplied: (sheet: string) => void
}

export interface ICycleBranchSelector {
  /** 分支列表（I1-10/I1-11 或 I4-6/I4-7 时 > 1） */
  branches: ComputedRef<BranchOption[]>
  /** 当前激活分支 */
  activeBranch: ComputedRef<string>
  /** 切换分支 */
  switchBranch: (sheetName: string) => void
}

export interface ICycleEditorAPI {
  dialogs: ICycleDialogs
  triggers: ICycleTriggers
  handlers: ICycleHandlers
  /** 摊销分支选择器（I1-10/I1-11 / I4-6/I4-7 时显示） */
  branchSelector: ICycleBranchSelector
}

// ─── Composable 实现 ──────────────────────────────────────────────────────────

/**
 * I 无形资产循环编辑器 composable
 *
 * @param wpDetail - 当前底稿详情（含 wp_code）
 * @param sheetNav - Sheet 导航 facade（用于 activeSheetId + iCycleNav）
 * @param cycleDialogs - 统一弹窗管理（委托 visible/trigger/onApplied）
 */
export function useICycleEditor(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  sheetNav: SheetNavFacadeAPI,
  cycleDialogs: CycleDialogsAPI,
): ICycleEditorAPI {
  // ─── Dialogs（委托 useCycleDialogs 已有的 I 循环弹窗） ─────────────────────────
  const dialogs: ICycleDialogs = {
    goodwillImpairmentDialogVisible: cycleDialogs.goodwillImpairment.visible,
    capitalizationCheckDialogVisible: cycleDialogs.capitalizationCheck.visible,
    amortizationCalcDialogVisible: cycleDialogs.amortizationCalc.visible,
  }

  // ─── Triggers（委托 useCycleDialogs 已有的 trigger computed） ───────────────────
  const wpCode = computed(() => (wpDetail.value?.wp_code || '').toUpperCase())

  const triggers: ICycleTriggers = {
    isICycle: computed(() => /^I\d/.test(wpCode.value)),
    showGoodwillImpairmentTrigger: cycleDialogs.goodwillImpairment.trigger,
    showCapitalizationCheckTrigger: cycleDialogs.capitalizationCheck.trigger,
    amortizationCalcSection: cycleDialogs.amortizationCalc.section,
  }

  // ─── Branch Selector（摊销分支选择器） ──────────────────────────────────────────
  const iCycleNav = sheetNav.iCycleNav

  const iActiveSheetName = computed(() => {
    if (!triggers.isICycle.value) return ''
    const activeId = iCycleNav.activeSheetId.value
    const sheet = iCycleNav.sheets.value.find((s: any) => s.id === activeId)
    return sheet?.name || ''
  })

  const iAllSheetNames = computed(() => {
    if (!triggers.isICycle.value) return [] as string[]
    return iCycleNav.sheets.value.map((s: any) => s.name)
  })

  const iBranchSelectorResult = useDepreciationBranchSelector(
    iActiveSheetName,
    iAllSheetNames,
    (sheetName: string) => {
      const target = iCycleNav.sheets.value.find((s: any) => s.name === sheetName)
      if (target) iCycleNav.switchTo(target.id)
    },
  )

  const branchSelector: ICycleBranchSelector = {
    branches: iBranchSelectorResult.branches,
    activeBranch: iBranchSelectorResult.activeBranch,
    switchBranch: iBranchSelectorResult.switchBranch,
  }

  // ─── Handlers ──────────────────────────────────────────────────────────────

  /** 商誉减值分析写回通知 */
  function onGoodwillImpairmentApplied(sheet: string) {
    cycleDialogs.goodwillImpairment.onApplied(sheet)
  }

  /** 资本化时点判断写回通知 */
  function onCapitalizationCheckApplied(sheet: string) {
    cycleDialogs.capitalizationCheck.onApplied(sheet)
  }

  /** 摊销测算写回通知 */
  function onAmortizationCalcApplied(sheet: string) {
    cycleDialogs.amortizationCalc.onApplied(sheet)
  }

  const handlers: ICycleHandlers = {
    onGoodwillImpairmentApplied,
    onCapitalizationCheckApplied,
    onAmortizationCalcApplied,
  }

  return {
    dialogs,
    triggers,
    handlers,
    branchSelector,
  }
}
