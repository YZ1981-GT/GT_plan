/**
 * 「私有防抖 + 宿主注入写盘」却没登记 pendingWrites 的写入方 —— 全前端棘轮（R20）。
 *
 * spec d2-online-edit-platform-closure R20：切「在线编辑」前桥统一 `flushPendingWrites()`，但它只等
 * **登记过**的写入方。子 Tab 自己 new 的 composable 若有私有防抖（`debounceTimer = setTimeout`）
 * 却没登记 flusher，改格后 2 秒内切在线编辑就会丢那次编辑（OO 打开旧值，保存回来再覆盖 store）。
 * D2 已全部接入（`d2PendingWritesBeforeOnlineEdit.spec.ts`）；其余循环规模超出本 spec，冻结在下表：
 *
 * * 新出现的同形写入方 ⇒ 红（必须登记，或证明它的防抖不写盘并进豁免表）；
 * * 表里的文件接入后 ⇒ 红（必须从表里删掉 —— 表只许变短，不许留失效条目）。
 *
 * 判据三条正则（与现算脚本同口径）：私有防抖 · 宿主注入写盘的标记 · 已登记的标记。这是「疑似」
 * 清单：个别文件的防抖可能只重算不写盘，核实后移入 NON_WRITING_DEBOUNCE 并写明理由。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC = resolve(__dirname, '../../../..')
const DEBOUNCE = /\b(?:\w*[Dd]ebounceTimer|saveTimer)\s*=\s*setTimeout\(/
const SAVE = /save-items|injectedSave|SAVE_ITEMS_KEY/
const REGISTERED = /\bregister(?:H)?PendingFlusher\(|_fieldFlushers\.add\(/

/** 防抖只重算、不写盘（核实过的豁免；须可证伪：文件仍命中 DEBOUNCE）。 */
const NON_WRITING_DEBOUNCE: Record<string, string> = {
  'components/workpaper/composables/useD2VcAuditSummary.ts':
    '防抖只调 recompute() 重算统计；写盘走即时 saveToResponses',
}

/** 2026-10-11 现算冻结（108 条）：只许变短。 */
const UNREGISTERED_BASELINE: readonly string[] = [
  'components/workpaper/composables/useD4Adjudication.ts',
  'components/workpaper/composables/useD4Adjustment.ts',
  'components/workpaper/composables/useD4Analysis.ts',
  'components/workpaper/composables/useD4CompletenessCheck.ts',
  'components/workpaper/composables/useD4ContractInspection.ts',
  'components/workpaper/composables/useD4InvoiceCompare.ts',
  'components/workpaper/composables/useD4Ipo.ts',
  'components/workpaper/composables/useD4KeyIndicator.ts',
  'components/workpaper/composables/useD4OtherRevenue.ts',
  'components/workpaper/composables/useD4PolicyCheck.ts',
  'components/workpaper/composables/useD4RelatedPrice.ts',
  'components/workpaper/composables/useD4RevenueDetail.ts',
  'components/workpaper/composables/useD4WalkthroughTest.ts',
  'components/workpaper/composables/useF2Adjudication.ts',
  'components/workpaper/composables/useF2Adjustment.ts',
  'components/workpaper/composables/useF2CapacityEnergy.ts',
  'components/workpaper/composables/useF2ContractCost.ts',
  'components/workpaper/composables/useF2ContractCostCheck.ts',
  'components/workpaper/composables/useF2CostAllocation.ts',
  'components/workpaper/composables/useF2CostComparison.ts',
  'components/workpaper/composables/useF2DetailSummary.ts',
  'components/workpaper/composables/useF2DirectLaborAnalysis.ts',
  'components/workpaper/composables/useF2DisclosureListed.ts',
  'components/workpaper/composables/useF2DisclosureSoe.ts',
  'components/workpaper/composables/useF2Impairment.ts',
  'components/workpaper/composables/useF2ImpairmentReversal.ts',
  'components/workpaper/composables/useF2ImpairmentTest.ts',
  'components/workpaper/composables/useF2InspectionCheck.ts',
  'components/workpaper/composables/useF2InterviewDetail.ts',
  'components/workpaper/composables/useF2InterviewSummary.ts',
  'components/workpaper/composables/useF2LossContract.ts',
  'components/workpaper/composables/useF2MasterDetail.ts',
  'components/workpaper/composables/useF2ObsoleteInventory.ts',
  'components/workpaper/composables/useF2OverallAnalysis.ts',
  'components/workpaper/composables/useF2OverheadDetail.ts',
  'components/workpaper/composables/useF2Policy.ts',
  'components/workpaper/composables/useF2ProductionCostDetail.ts',
  'components/workpaper/composables/useF2ProductionSales.ts',
  'components/workpaper/composables/useF2PurchasePrice.ts',
  'components/workpaper/composables/useF2RelatedPartyInquiry.ts',
  'components/workpaper/composables/useF2RelatedPartyMarket.ts',
  'components/workpaper/composables/useF2RelatedPurchase.ts',
  'components/workpaper/composables/useF2StdCostMonthlySheet.ts',
  'components/workpaper/composables/useF2StocktakeQuestionnaire.ts',
  'components/workpaper/composables/useF2SubcontractCheck.ts',
  'components/workpaper/composables/useF2SupplierChecklist.ts',
  'components/workpaper/composables/useF2SupplierInfoCheck.ts',
  'components/workpaper/composables/useF2SupplierStructure.ts',
  'components/workpaper/composables/useF2UndisclosedParty.ts',
  'components/workpaper/composables/useF2UnitConsumption.ts',
  'components/workpaper/composables/useF2UnitPrice.ts',
  'components/workpaper/composables/useF2ValuationDateSheet.ts',
  'components/workpaper/composables/useF2ValuationMonthlySheet.ts',
  'components/workpaper/composables/useF2ValuationTestSheet.ts',
  'components/workpaper/composables/useF3Adjudication.ts',
  'components/workpaper/composables/useF3Adjustment.ts',
  'components/workpaper/composables/useF3Detail.ts',
  'components/workpaper/composables/useF3DisclosureListed.ts',
  'components/workpaper/composables/useF3DisclosureSoe.ts',
  'components/workpaper/composables/useF3InterestCalc.ts',
  'components/workpaper/composables/useF3OverdueCheck.ts',
  'components/workpaper/composables/useF3RelatedParty.ts',
  'components/workpaper/composables/useF3VoucherCheck.ts',
  'components/workpaper/composables/useF4Adjudication.ts',
  'components/workpaper/composables/useF4Detail.ts',
  'components/workpaper/composables/useF4DisclosureListed.ts',
  'components/workpaper/composables/useF4DisclosureSOE.ts',
  'components/workpaper/composables/useF4LongOutstanding.ts',
  'components/workpaper/composables/useF4RelatedParty.ts',
  'components/workpaper/composables/useF4SubstantiveAnalysis.ts',
  'components/workpaper/composables/useF4SupplierFinancing.ts',
  'components/workpaper/composables/useF4UnrecordedCheck.ts',
  'components/workpaper/composables/useF4VoucherCheck.ts',
  'components/workpaper/composables/useF5Adjudication.ts',
  'components/workpaper/composables/useF5Comparison.ts',
  'components/workpaper/composables/useF5CostRollforward.ts',
  'components/workpaper/composables/useF5MajorAdjustment.ts',
  'components/workpaper/composables/useF5MonthlyDetail.ts',
  'components/workpaper/composables/useF5OtherCost.ts',
  'components/workpaper/composables/useF5QuantityRecon.ts',
  'components/workpaper/composables/useG2Adjudication.ts',
  'components/workpaper/composables/useG2BadDebtDetail.ts',
  'components/workpaper/composables/useG2Detail.ts',
  'components/workpaper/composables/useG2InterestCalc.ts',
  'components/workpaper/composables/useG2OverdueCheck.ts',
  'components/workpaper/composables/useG2VoucherCheck.ts',
  'components/workpaper/composables/useG4MainAdjudication.ts',
  'components/workpaper/composables/useG4MainAdjustment.ts',
  'components/workpaper/composables/useG4MainInterestCalc.ts',
  'components/workpaper/d4/analysis/D4TabCustomerPrice.vue',
  'components/workpaper/d4/analysis/D4TabCustomerStructure.vue',
  'components/workpaper/d4/analysis/D4TabIndicator.vue',
  'components/workpaper/d4/analysis/D4TabMarginMonthly.vue',
  'components/workpaper/d4/analysis/D4TabProductMargin.vue',
  'components/workpaper/d4/analysis/D4TabProductPrice.vue',
  'components/workpaper/d4/inspection/D4TabCutoffBackward.vue',
  'components/workpaper/d4/inspection/D4TabCutoffForward.vue',
  'components/workpaper/d4/inspection/D4TabDiscount.vue',
  'components/workpaper/d4/inspection/D4TabExport.vue',
  'components/workpaper/d4/inspection/D4TabReturn.vue',
  'components/workpaper/d4/ipo/D4TabThirdParty.vue',
  'components/workpaper/d4/ipo/useIpoChecklistTab.ts',
  'components/workpaper/d4/other/D4TabOtherCheck.vue',
  'components/workpaper/d4/other/D4TabOtherContract.vue',
  'components/workpaper/d4/other/D4TabOtherCutoff.vue',
  'components/workpaper/d4/other/D4TabOtherMargin.vue',
  'components/workpaper/f4-accounts-payable/F4TabAdjustment.vue',
  'components/workpaper/f5-cost-of-sales/F5TabAdjustment.vue',
]

function walk(dir: string, out: string[]): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (name === '__tests__' || name === 'node_modules') continue
    if (statSync(full).isDirectory()) walk(full, out)
    else if (/\.(ts|vue)$/.test(name)) out.push(full)
  }
  return out
}

function offenders(): string[] {
  return walk(SRC, [])
    .filter((file) => {
      const text = readFileSync(file, 'utf-8')
      return DEBOUNCE.test(text) && SAVE.test(text) && !REGISTERED.test(text)
    })
    .map((file) => relative(SRC, file).split('\\').join('/'))
    .filter((rel) => !(rel in NON_WRITING_DEBOUNCE))
    .sort()
}

describe('私有防抖写入方登记棘轮（R20）', () => {
  const actual = offenders()

  it('扫描器分母没失锚（D2 已接入的写入方能被同一组正则认出来）', () => {
    const d2 = readFileSync(join(SRC, 'components/workpaper/composables/useD2Detail.ts'), 'utf-8')
    expect(DEBOUNCE.test(d2) && SAVE.test(d2) && REGISTERED.test(d2)).toBe(true)
  })

  it('没有新的未登记写入方', () => {
    expect(actual.filter((rel) => !UNREGISTERED_BASELINE.includes(rel))).toEqual([])
  })

  it('表里没有已接入 / 已删除的失效条目（表只许变短）', () => {
    expect(UNREGISTERED_BASELINE.filter((rel) => !actual.includes(rel))).toEqual([])
  })

  it('豁免条目仍成立（文件在、仍有私有防抖）', () => {
    for (const rel of Object.keys(NON_WRITING_DEBOUNCE)) {
      expect(DEBOUNCE.test(readFileSync(join(SRC, rel), 'utf-8')), rel).toBe(true)
    }
  })
})