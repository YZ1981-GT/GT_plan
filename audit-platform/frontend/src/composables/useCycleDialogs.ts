/**
 * useCycleDialogs — 统一管理 WorkpaperEditor 中各循环弹窗的 visible ref + trigger computed + applied handler
 *
 * 锚定 spec workpaper-editor-refactor Phase 2-3
 *
 * 把 WorkpaperEditor 中 ~290 行重复的 dialog 状态代码集中到此 composable，
 * 主组件只需 `const dialogs = useCycleDialogs(...)` 即可访问所有弹窗状态。
 *
 * 设计原则：
 * - 每个弹窗暴露 `visible: Ref<boolean>` + `trigger: ComputedRef<boolean>` + `onApplied: (sheet) => void`
 * - trigger 依赖 cycleType flags + wpDetail.wp_code + sheetNav.activeSheetId
 * - onApplied 统一 ElMessage.success + eventBus.emit('workpaper:saved')
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import type { CycleTypeFlags } from './useCycleType'

export interface CycleDialogEntry {
  visible: Ref<boolean>
  trigger: ComputedRef<boolean>
  onApplied: (sheet: string) => void
}

export interface CycleDialogsAPI {
  // F 循环
  stocktake: CycleDialogEntry
  valuation: { visible: Ref<boolean>; trigger: ComputedRef<boolean>; loading: Ref<boolean> }
  impairment: CycleDialogEntry
  // H 循环
  hStocktake: CycleDialogEntry
  depreciationCalc: CycleDialogEntry
  assetImpairment: CycleDialogEntry
  // I 循环
  goodwillImpairment: CycleDialogEntry
  capitalizationCheck: CycleDialogEntry
  amortizationCalc: CycleDialogEntry & { section: ComputedRef<'I1' | 'I4' | null> }
  // G 循环
  fairValueTest: CycleDialogEntry & { instrumentType: ComputedRef<string> }
  eclCalc: CycleDialogEntry & { instrumentType: ComputedRef<string> }
  classificationCheck: CycleDialogEntry
  // K 循环
  expenseAnalysis: CycleDialogEntry
  impairmentSummary: CycleDialogEntry
  // L 循环
  interestCalc: CycleDialogEntry
  bondAmortization: CycleDialogEntry
  // M 循环
  equityMovement: CycleDialogEntry
  // N 循环
  incomeTaxCalc: CycleDialogEntry
}

export function useCycleDialogs(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
  wpId: Ref<string>,
  activeSheetId: ComputedRef<string>,
  cycleType: CycleTypeFlags,
): CycleDialogsAPI {
  const { isFCycle, isHCycle, isICycle, isGCycle, isKCycle, isLCycle, isMCycle, isNCycle } = cycleType

  // 通用 applied handler 工厂
  function makeApplied(label: string) {
    return (sheet: string) => {
      ElMessage.success(`${label}已写回 ${sheet}`)
      eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
    }
  }

  const wpCode = computed(() => (wpDetail.value?.wp_code || '').toUpperCase())

  // ─── F 循环 ───────────────────────────────────────────────────────────────
  const stocktake: CycleDialogEntry = {
    visible: ref(false),
    trigger: computed(() => {
      if (!isFCycle.value) return false
      if (!wpCode.value.startsWith('F2')) return false
      const id = activeSheetId.value
      return /F2-2[1-6]/i.test(id) || /监盘|盘点|抽盘/.test(id)
    }),
    onApplied: makeApplied('监盘'),
  }

  const valuation = {
    visible: ref(false),
    loading: ref(false),
    trigger: computed(() => {
      if (!isFCycle.value) return false
      if (!wpCode.value.startsWith('F2')) return false
      const id = activeSheetId.value
      return /F2-(3[89]|4[0-4])/i.test(id) || /计价测试|价格测试/.test(id)
    }),
  }

  const impairment: CycleDialogEntry = {
    visible: ref(false),
    trigger: computed(() => {
      if (!isFCycle.value) return false
      if (!wpCode.value.startsWith('F2')) return false
      const id = activeSheetId.value
      return /F2-4[789]/i.test(id) || /跌价|减值|可变现/.test(id)
    }),
    onApplied: makeApplied('跌价分析'),
  }

  // ─── H 循环 ───────────────────────────────────────────────────────────────
  const hStocktake: CycleDialogEntry = {
    visible: ref(false),
    trigger: computed(() => {
      if (!isHCycle.value) return false
      const id = activeSheetId.value
      return /H[1-9]-(?:9|1[0-4])/i.test(id) || /监盘|盘点/.test(id)
    }),
    onApplied: makeApplied('固定资产盘点'),
  }

  const depreciationCalc: CycleDialogEntry = {
    visible: ref(false),
    trigger: computed(() => {
      if (!isHCycle.value) return false
      const id = activeSheetId.value
      return /折旧测算表.*H1-12|H3-7|H5-12|H7-11|H8-8/i.test(id) || /折旧测算/.test(id)
    }),
    onApplied: makeApplied('折旧测算'),
  }

  const assetImpairment: CycleDialogEntry = {
    visible: ref(false),
    trigger: computed(() => {
      if (!isHCycle.value) return false
      const id = activeSheetId.value
      return /减值测算表.*H1-14|减值测算.*H\d/i.test(id) || /减值测算表H1-14/.test(id)
    }),
    onApplied: makeApplied('减值分析'),
  }

  // ─── I 循环 ───────────────────────────────────────────────────────────────
  const goodwillImpairment: CycleDialogEntry = {
    visible: ref(false),
    trigger: computed(() => {
      if (!isICycle.value) return false
      const id = activeSheetId.value
      return /商誉减值|可收回金额.*I3|减值.*I3-[67]|I3-[67]/i.test(id)
    }),
    onApplied: makeApplied('商誉减值分析'),
  }

  const capitalizationCheck: CycleDialogEntry = {
    visible: ref(false),
    trigger: computed(() => {
      if (!isICycle.value) return false
      const id = activeSheetId.value
      return /资本化时点|项目成立条件.*I2|I2-6/i.test(id)
    }),
    onApplied: makeApplied('资本化时点判断'),
  }

  const amortizationCalcSection = computed<'I1' | 'I4' | null>(() => {
    if (!isICycle.value) return null
    const id = activeSheetId.value
    if (/摊销测算.*I1-1[01]|I1-1[01].*摊销/.test(id)) return 'I1'
    if (/摊销测算.*I4-[67]|I4-[67].*摊销/.test(id)) return 'I4'
    return null
  })

  const amortizationCalc = {
    visible: ref(false),
    trigger: computed(() => amortizationCalcSection.value !== null),
    section: amortizationCalcSection,
    onApplied: makeApplied('摊销测算'),
  }

  // ─── G 循环 ───────────────────────────────────────────────────────────────
  const fairValueTest = {
    visible: ref(false),
    trigger: computed(() => {
      if (!isGCycle.value) return false
      const id = activeSheetId.value
      return /公允价值测试|公允价值计量|第三层次/.test(id)
    }),
    instrumentType: computed(() => {
      const code = wpCode.value
      if (code.startsWith('G1') && !code.startsWith('G10') && !code.startsWith('G11') && !code.startsWith('G12') && !code.startsWith('G13') && !code.startsWith('G14')) return '交易性金融资产'
      if (code.startsWith('G6')) return '其他债权投资'
      if (code.startsWith('G8')) return '其他权益工具投资'
      if (code.startsWith('G10')) return '交易性金融负债'
      if (code.startsWith('G12')) return '净敞口套期'
      if (code.startsWith('G13')) return '公允价值变动收益'
      return '交易性金融资产'
    }),
    onApplied: makeApplied('公允价值测试'),
  }

  const eclCalc = {
    visible: ref(false),
    trigger: computed(() => {
      if (!isGCycle.value) return false
      const code = wpCode.value
      if (!(/^G4(\b|-|$|\d)/.test(code) || /^G6(\b|-|$|\d)/.test(code))) return false
      const id = activeSheetId.value
      return /减值|信用损失|ECL/.test(id)
    }),
    instrumentType: computed(() => {
      const code = wpCode.value
      if (code.startsWith('G4')) return '债权投资'
      if (code.startsWith('G6')) return '其他债权投资'
      return '债权投资'
    }),
    onApplied: makeApplied('ECL 计算'),
  }

  const classificationCheck: CycleDialogEntry = {
    visible: ref(false),
    trigger: computed(() => {
      if (!isGCycle.value) return false
      const code = wpCode.value
      if (!/^G1(\b|-|$)/.test(code) && !/^G1\d?$/.test(code)) {
        if (!code.startsWith('G1') || code.startsWith('G10') || code.startsWith('G11') || code.startsWith('G12') || code.startsWith('G13') || code.startsWith('G14')) return false
      }
      const id = activeSheetId.value
      return /业务模式|合同现金流|分类.*适当性|SPPI/.test(id)
    }),
    onApplied: makeApplied('分类辅助'),
  }

  // ─── K 循环 ───────────────────────────────────────────────────────────────
  const expenseAnalysis: CycleDialogEntry = {
    visible: ref(false),
    trigger: computed(() => isKCycle.value && /^K[89](\b|-|$|\d)/.test(wpCode.value)),
    onApplied: makeApplied('费用分析'),
  }

  const impairmentSummary: CycleDialogEntry = {
    visible: ref(false),
    trigger: computed(() => isKCycle.value && /^K11(\b|-|$|\d)/.test(wpCode.value)),
    onApplied: makeApplied('减值汇总'),
  }

  // ─── L 循环 ───────────────────────────────────────────────────────────────
  const interestCalc: CycleDialogEntry = {
    visible: ref(false),
    trigger: computed(() => isLCycle.value && /^L[13](\b|-|$|\d)/.test(wpCode.value)),
    onApplied: makeApplied('利息测算'),
  }

  const bondAmortization: CycleDialogEntry = {
    visible: ref(false),
    trigger: computed(() => isLCycle.value && /^L5(\b|-|$|\d)/.test(wpCode.value)),
    onApplied: makeApplied('摊余成本'),
  }

  // ─── M 循环 ───────────────────────────────────────────────────────────────
  const equityMovement: CycleDialogEntry = {
    visible: ref(false),
    trigger: computed(() => isMCycle.value && /^M6(\b|-|$|\d)/.test(wpCode.value)),
    onApplied: makeApplied('权益变动'),
  }

  // ─── N 循环 ───────────────────────────────────────────────────────────────
  const incomeTaxCalc: CycleDialogEntry = {
    visible: ref(false),
    trigger: computed(() => isNCycle.value && /^N5(\b|-|$|\d)/.test(wpCode.value)),
    onApplied: makeApplied('所得税测算'),
  }

  return {
    stocktake, valuation, impairment,
    hStocktake, depreciationCalc, assetImpairment,
    goodwillImpairment, capitalizationCheck, amortizationCalc,
    fairValueTest, eclCalc, classificationCheck,
    expenseAnalysis, impairmentSummary,
    interestCalc, bondAmortization,
    equityMovement,
    incomeTaxCalc,
  }
}
