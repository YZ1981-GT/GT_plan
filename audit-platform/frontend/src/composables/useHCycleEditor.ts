/**
 * useHCycleEditor — H 固定资产循环专属逻辑 composable
 *
 * 锚定 spec workpaper-editor-refactor Phase 3 Task 3.3
 *
 * H 循环在 WorkpaperEditor.vue 中的独占代码：
 * - H 循环监盘弹窗（FixedAssetStocktakeDialog）触发
 * - H1-12 折旧测算弹窗（DepreciationCalcDialog）触发
 * - H1-14 减值 DCF 分析弹窗（AssetImpairmentDialog）触发
 * - H 循环折旧/减值分支选择器（DepreciationBranchSelector）
 *
 * 本 composable 封装：
 * 1. H 循环弹窗 visible refs（委托 useCycleDialogs 已有的 hStocktake/depreciationCalc/assetImpairment）
 * 2. H 循环特有的 trigger 判定（基于 wpCode + activeSheetId）
 * 3. 折旧/减值分支选择器（委托 useDepreciationBranchSelector）
 * 4. onDepreciationCalcApplied / onAssetImpairmentApplied handlers
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

export interface HCycleDialogs {
  /** 固定资产监盘弹窗 visible（委托 useCycleDialogs.hStocktake） */
  hStocktakeDialogVisible: Ref<boolean>
  /** 折旧测算弹窗 visible（委托 useCycleDialogs.depreciationCalc） */
  depreciationCalcDialogVisible: Ref<boolean>
  /** 减值 DCF 分析弹窗 visible（委托 useCycleDialogs.assetImpairment） */
  assetImpairmentDialogVisible: Ref<boolean>
}

export interface HCycleTriggers {
  /** 是否为 H 循环底稿 */
  isHCycle: ComputedRef<boolean>
  /** 是否显示固定资产盘点按钮（H 循环监盘类 sheet） */
  showHStocktakeTrigger: ComputedRef<boolean>
  /** 是否显示折旧测算按钮（H1-12 等折旧测算 sheet） */
  showDepreciationCalcTrigger: ComputedRef<boolean>
  /** 是否显示减值分析按钮（H1-14 等减值测算 sheet） */
  showAssetImpairmentTrigger: ComputedRef<boolean>
}

export interface HCycleHandlers {
  /** 折旧测算写回通知 */
  onDepreciationCalcApplied: (sheet: string) => void
  /** 减值分析写回通知 */
  onAssetImpairmentApplied: (sheet: string) => void
}

export interface HCycleBranchSelector {
  /** 分支列表（多版本 sheet 时 > 1） */
  branches: ComputedRef<BranchOption[]>
  /** 当前激活分支 */
  activeBranch: ComputedRef<string>
  /** 切换分支 */
  switchBranch: (sheetName: string) => void
}

export interface HCycleEditorAPI {
  dialogs: HCycleDialogs
  triggers: HCycleTriggers
  handlers: HCycleHandlers
  /** 折旧/减值分支选择器（多版本 sheet 时显示） */
  branchSelector: HCycleBranchSelector
}

// ─── Composable 实现 ──────────────────────────────────────────────────────────

/**
 * H 固定资产循环编辑器 composable
 *
 * @param wpDetail - 当前底稿详情（含 wp_code）
 * @param sheetNav - Sheet 导航 facade（用于 activeSheetId）
 * @param cycleDialogs - 统一弹窗管理（委托 visible/trigger/onApplied）
 */
export function useHCycleEditor(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  sheetNav: SheetNavFacadeAPI,
  cycleDialogs: CycleDialogsAPI,
): HCycleEditorAPI {
  // ─── Dialogs（委托 useCycleDialogs 已有的 H 循环弹窗） ─────────────────────────
  const dialogs: HCycleDialogs = {
    hStocktakeDialogVisible: cycleDialogs.hStocktake.visible,
    depreciationCalcDialogVisible: cycleDialogs.depreciationCalc.visible,
    assetImpairmentDialogVisible: cycleDialogs.assetImpairment.visible,
  }

  // ─── Triggers（委托 useCycleDialogs 已有的 trigger computed） ───────────────────
  const wpCode = computed(() => (wpDetail.value?.wp_code || '').toUpperCase())

  const triggers: HCycleTriggers = {
    isHCycle: computed(() => /^H\d/.test(wpCode.value)),
    showHStocktakeTrigger: cycleDialogs.hStocktake.trigger,
    showDepreciationCalcTrigger: cycleDialogs.depreciationCalc.trigger,
    showAssetImpairmentTrigger: cycleDialogs.assetImpairment.trigger,
  }

  // ─── Branch Selector（折旧/减值分支选择器） ─────────────────────────────────────
  const hCycleNav = sheetNav.hCycleNav

  const hActiveSheetName = computed(() => {
    if (!triggers.isHCycle.value) return ''
    const activeId = hCycleNav.activeSheetId.value
    const sheet = hCycleNav.sheets.value.find((s: any) => s.id === activeId)
    return sheet?.name || ''
  })

  const hAllSheetNames = computed(() => {
    if (!triggers.isHCycle.value) return [] as string[]
    return hCycleNav.sheets.value.map((s: any) => s.name)
  })

  const hBranchSelectorResult = useDepreciationBranchSelector(
    hActiveSheetName,
    hAllSheetNames,
    (sheetName: string) => {
      const target = hCycleNav.sheets.value.find((s: any) => s.name === sheetName)
      if (target) hCycleNav.switchTo(target.id)
    },
  )

  const branchSelector: HCycleBranchSelector = {
    branches: hBranchSelectorResult.branches,
    activeBranch: hBranchSelectorResult.activeBranch,
    switchBranch: hBranchSelectorResult.switchBranch,
  }

  // ─── Handlers ──────────────────────────────────────────────────────────────

  /** 折旧测算写回通知（委托 useCycleDialogs.depreciationCalc.onApplied） */
  function onDepreciationCalcApplied(sheet: string) {
    cycleDialogs.depreciationCalc.onApplied(sheet)
  }

  /** 减值分析写回通知（委托 useCycleDialogs.assetImpairment.onApplied） */
  function onAssetImpairmentApplied(sheet: string) {
    cycleDialogs.assetImpairment.onApplied(sheet)
  }

  const handlers: HCycleHandlers = {
    onDepreciationCalcApplied,
    onAssetImpairmentApplied,
  }

  return {
    dialogs,
    triggers,
    handlers,
    branchSelector,
  }
}
