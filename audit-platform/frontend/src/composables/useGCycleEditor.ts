/**
 * useGCycleEditor — G 投资循环专属逻辑 composable
 *
 * 锚定 spec workpaper-editor-refactor Phase 3 Task 3.5
 *
 * G 循环在 WorkpaperEditor.vue 中的独占代码：
 * - G1-6/G6/G8 公允价值测试弹窗（FairValueTestDialog）触发
 * - G4/G6 ECL 三阶段计算弹窗（ECLCalcDialog）触发
 * - G1-8/G1-10 金融资产分类辅助弹窗（ClassificationCheckDialog）触发
 * - G 循环计量模型分支选择器（公允价值/摊余成本/权益法）
 *
 * 本 composable 封装：
 * 1. G 循环弹窗 visible refs（委托 useCycleDialogs 已有的 fairValueTest/eclCalc/classificationCheck）
 * 2. G 循环特有的 trigger 判定（基于 wpCode + activeSheetId）
 * 3. 计量模型分支选择器（委托 useDepreciationBranchSelector — G 循环 sheet 名匹配）
 * 4. onFairValueTestApplied / onECLCalcApplied / onClassificationCheckApplied handlers
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

export interface GCycleDialogs {
  /** 公允价值测试弹窗 visible（委托 useCycleDialogs.fairValueTest） */
  fairValueTestDialogVisible: Ref<boolean>
  /** ECL 三阶段计算弹窗 visible（委托 useCycleDialogs.eclCalc） */
  eclCalcDialogVisible: Ref<boolean>
  /** 金融资产分类辅助弹窗 visible（委托 useCycleDialogs.classificationCheck） */
  classificationCheckDialogVisible: Ref<boolean>
}

export interface GCycleTriggers {
  /** 是否为 G 循环底稿 */
  isGCycle: ComputedRef<boolean>
  /** 是否显示公允价值测试按钮（G1-6/G6/G8 公允价值类 sheet） */
  showFairValueTestTrigger: ComputedRef<boolean>
  /** 是否显示 ECL 计算按钮（G4/G6 减值/信用损失类 sheet） */
  showECLCalcTrigger: ComputedRef<boolean>
  /** 是否显示分类辅助按钮（G1-8/G1-10 业务模式/SPPI 类 sheet） */
  showClassificationCheckTrigger: ComputedRef<boolean>
  /** 公允价值测试金融工具类型 */
  fairValueInstrumentType: ComputedRef<string>
  /** ECL 计算金融工具类型 */
  eclInstrumentType: ComputedRef<string>
}

export interface GCycleHandlers {
  /** 公允价值测试写回通知 */
  onFairValueTestApplied: (sheet: string) => void
  /** ECL 计算写回通知 */
  onECLCalcApplied: (sheet: string) => void
  /** 分类辅助写回通知 */
  onClassificationCheckApplied: (sheet: string) => void
}

export interface GCycleBranchSelector {
  /** 分支列表（G7 多核算方式 sheet 时 > 1） */
  branches: ComputedRef<BranchOption[]>
  /** 当前激活分支 */
  activeBranch: ComputedRef<string>
  /** 切换分支 */
  switchBranch: (sheetName: string) => void
}

export interface GCycleEditorAPI {
  dialogs: GCycleDialogs
  triggers: GCycleTriggers
  handlers: GCycleHandlers
  /** 计量模型分支选择器（G7 多核算方式 sheet 时显示） */
  branchSelector: GCycleBranchSelector
}

// ─── Composable 实现 ──────────────────────────────────────────────────────────

/**
 * G 投资循环编辑器 composable
 *
 * @param wpDetail - 当前底稿详情（含 wp_code）
 * @param sheetNav - Sheet 导航 facade（用于 activeSheetId + gCycleNav）
 * @param cycleDialogs - 统一弹窗管理（委托 visible/trigger/onApplied）
 */
export function useGCycleEditor(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  sheetNav: SheetNavFacadeAPI,
  cycleDialogs: CycleDialogsAPI,
): GCycleEditorAPI {
  // ─── Dialogs（委托 useCycleDialogs 已有的 G 循环弹窗） ─────────────────────────
  const dialogs: GCycleDialogs = {
    fairValueTestDialogVisible: cycleDialogs.fairValueTest.visible,
    eclCalcDialogVisible: cycleDialogs.eclCalc.visible,
    classificationCheckDialogVisible: cycleDialogs.classificationCheck.visible,
  }

  // ─── Triggers（委托 useCycleDialogs 已有的 trigger computed） ───────────────────
  const wpCode = computed(() => (wpDetail.value?.wp_code || '').toUpperCase())

  const triggers: GCycleTriggers = {
    isGCycle: computed(() => /^G\d/.test(wpCode.value)),
    showFairValueTestTrigger: cycleDialogs.fairValueTest.trigger,
    showECLCalcTrigger: cycleDialogs.eclCalc.trigger,
    showClassificationCheckTrigger: cycleDialogs.classificationCheck.trigger,
    fairValueInstrumentType: cycleDialogs.fairValueTest.instrumentType,
    eclInstrumentType: cycleDialogs.eclCalc.instrumentType,
  }

  // ─── Branch Selector（计量模型分支选择器） ──────────────────────────────────────
  const gCycleNav = sheetNav.gCycleNav

  const gActiveSheetName = computed(() => {
    if (!triggers.isGCycle.value) return ''
    const activeId = gCycleNav.activeSheetId.value
    const sheet = gCycleNav.sheets.value.find((s: any) => s.id === activeId)
    return sheet?.name || ''
  })

  const gAllSheetNames = computed(() => {
    if (!triggers.isGCycle.value) return [] as string[]
    return gCycleNav.sheets.value.map((s: any) => s.name)
  })

  const gBranchSelectorResult = useDepreciationBranchSelector(
    gActiveSheetName,
    gAllSheetNames,
    (sheetName: string) => {
      const target = gCycleNav.sheets.value.find((s: any) => s.name === sheetName)
      if (target) gCycleNav.switchTo(target.id)
    },
  )

  const branchSelector: GCycleBranchSelector = {
    branches: gBranchSelectorResult.branches,
    activeBranch: gBranchSelectorResult.activeBranch,
    switchBranch: gBranchSelectorResult.switchBranch,
  }

  // ─── Handlers ──────────────────────────────────────────────────────────────

  /** 公允价值测试写回通知（委托 useCycleDialogs.fairValueTest.onApplied） */
  function onFairValueTestApplied(sheet: string) {
    cycleDialogs.fairValueTest.onApplied(sheet)
  }

  /** ECL 计算写回通知（委托 useCycleDialogs.eclCalc.onApplied） */
  function onECLCalcApplied(sheet: string) {
    cycleDialogs.eclCalc.onApplied(sheet)
  }

  /** 分类辅助写回通知（委托 useCycleDialogs.classificationCheck.onApplied） */
  function onClassificationCheckApplied(sheet: string) {
    cycleDialogs.classificationCheck.onApplied(sheet)
  }

  const handlers: GCycleHandlers = {
    onFairValueTestApplied,
    onECLCalcApplied,
    onClassificationCheckApplied,
  }

  return {
    dialogs,
    triggers,
    handlers,
    branchSelector,
  }
}
