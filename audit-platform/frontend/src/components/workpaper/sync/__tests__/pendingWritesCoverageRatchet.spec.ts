/**
 * 私有防抖写入方的完整保存屏障守卫。
 *
 * 切换「在线编辑」前，桥必须先冲刷 HTML 子 Tab 的私有防抖，再等待父宿主已发出的请求。
 * 本守卫把三种状态分开验证：
 *
 * * `MIGRATED_WRITERS`：106 个活写入方，必须登记 pending-only flusher；
 * * `DEAD_WRITERS`：2 个确实会写盘但没有生产消费者的死路径，必须持续不可达；
 * * `PARENT_QUEUE_BINDINGS`：10 个父宿主只消费事件 rejection，真实 HTTP tracking 由对应 formData 队列负责。
 *
 * 新出现的同形写入方直接失败；清单不是豁免表，每个声明都要由当前源码反向证明。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC = resolve(__dirname, '../../../..')
const DEBOUNCE = /\b(?:\w*[Dd]ebounceTimer|saveTimer)\s*=\s*setTimeout\(/
const SAVE = /save-items|injectedSave|SAVE_ITEMS_KEY|dispatchF2StocktakeSave/
const REGISTERED = /\bregister(?:H)?PendingFlusher\(|\bcreateChecklistWriteQueue(?:<[^>]+>)?\s*\(/

/** 防抖只重算、不写盘（核实过的豁免；须可证伪：文件仍命中 DEBOUNCE）。 */
const NON_WRITING_DEBOUNCE: Record<string, string> = {
  'components/workpaper/composables/useD2VcAuditSummary.ts':
    '防抖只调 recompute() 重算统计；写盘走即时 saveToResponses',
}

/** 2026-11-01 已接入的 106 个活写入方；每条都必须继续满足登记与 pending-only 顺序。 */
const MIGRATED_WRITERS: readonly string[] = [
  'components/workpaper/composables/useD4Adjudication.ts',
  'components/workpaper/composables/useD4Adjustment.ts',
  'components/workpaper/composables/useD4CompletenessCheck.ts',
  'components/workpaper/composables/useD4ContractInspection.ts',
  'components/workpaper/composables/useD4InvoiceCompare.ts',
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

/** 写盘逻辑仍存在，但全生产源码零 import/零消费者；不得伪装成“非写盘”豁免。 */
const DEAD_WRITERS: Record<string, string> = {
  'components/workpaper/composables/useD4Analysis.ts': '被拆分后的 D4 分析 Tab 已直接使用各自 composable',
  'components/workpaper/composables/useD4Ipo.ts': 'D4 IPO 页面已改用 useIpoChecklistTab 等细分实现',
}

/** 子 writer 事件由父宿主消费；对应 formData 的 generation-safe 队列是唯一 HTTP tracking 边界。 */
const PARENT_QUEUE_BINDINGS: ReadonlyArray<{ host: string; formData: string }> = [
  { host: 'components/workpaper/GtD4OperatingRevenue.vue', formData: 'components/workpaper/composables/useD4FormData.ts' },
  { host: 'components/workpaper/GtF2InventoryMain.vue', formData: 'components/workpaper/composables/useF2FormData.ts' },
  { host: 'components/workpaper/GtF2InventoryValuation.vue', formData: 'components/workpaper/composables/useF2ValuationFormData.ts' },
  { host: 'components/workpaper/GtF2InventorySpecial.vue', formData: 'components/workpaper/composables/useF2SpecialFormData.ts' },
  { host: 'components/workpaper/GtF2StocktakeBundle.vue', formData: 'components/workpaper/composables/useF2StocktakeFormData.ts' },
  { host: 'components/workpaper/GtF3NotesPayable.vue', formData: 'components/workpaper/composables/useF3FormData.ts' },
  { host: 'components/workpaper/GtF4AccountsPayable.vue', formData: 'components/workpaper/composables/useF4FormData.ts' },
  { host: 'components/workpaper/GtF5CostOfSales.vue', formData: 'components/workpaper/composables/useF5CosSalFormData.ts' },
  { host: 'components/workpaper/GtG2InterestReceivable.vue', formData: 'components/workpaper/composables/useG2IntRecFormData.ts' },
  { host: 'components/workpaper/GtG4BondInvestmentMain.vue', formData: 'components/workpaper/composables/useG4BonInvFormData.ts' },
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

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function sourceOf(rel: string): string {
  return readFileSync(join(SRC, rel), 'utf-8')
}

/**
 * flusher 必须按「无 timer 立即返回 → clear → 置 null → 立即保存」顺序执行。
 * 只看注册调用前最近的 flusher，避免卸载清理代码或普通 debounce 代码误让判据变绿。
 */
function hasPendingOnlyFlusher(text: string): boolean {
  const registration = text.lastIndexOf('registerPendingFlusher(')
  if (registration < 0) return false
  const candidate = text.slice(Math.max(0, registration - 5000), registration)
  const guards = [...candidate.matchAll(
    /if\s*\(\s*!\s*(\w*Timer)\s*\)\s*return/g,
  )]
  const guard = guards.at(-1)
  if (!guard || guard.index === undefined) return false
  const timer = guard[1]
  const clear = candidate.indexOf(`clearTimeout(${timer})`, guard.index + guard[0].length)
  if (clear < 0) return false
  const afterClear = candidate.slice(clear + `clearTimeout(${timer})`.length)
  const reset = new RegExp(`${escapeRegex(timer)}\\s*=\\s*null`).exec(afterClear)
  if (!reset) return false
  const beforeRegistration = afterClear.slice(reset.index + reset[0].length)
  return /\b_?(?:flush|save|persist|dispatch|write|injected)\w*\s*\(/i.test(beforeRegistration)
}

function productionImporters(rel: string): string[] {
  const fileName = rel.split('/').pop() || ''
  const stem = fileName.replace(/\.(?:ts|vue)$/, '')
  const escaped = escapeRegex(stem)
  const staticImport = new RegExp(`\\bfrom\\s+['\"][^'\"]*${escaped}['\"]`)
  const dynamicImport = new RegExp(`\\bimport\\s*\\(\\s*['\"][^'\"]*${escaped}['\"]`)
  return walk(SRC, [])
    .filter((file) => relative(SRC, file).split('\\').join('/') !== rel)
    .filter((file) => {
      const text = readFileSync(file, 'utf-8')
      return staticImport.test(text) || dynamicImport.test(text)
    })
    .map((file) => relative(SRC, file).split('\\').join('/'))
    .sort()
}

function hostConsumesRejectionWithoutTracking(text: string): boolean {
  const save = Math.max(
    text.lastIndexOf('await formData.saveBatch('),
    text.lastIndexOf('await formData.saveItemsFromEvent('),
  )
  if (save < 0 || text.includes('trackPendingWrite')) return false
  const before = text.slice(Math.max(0, save - 1000), save)
  const after = text.slice(save, save + 5000)
  return before.includes('try {')
    && /catch\s*(?:\([^)]*\))?\s*\{[\s\S]{0,200}?(?:return|\.reject\?\.\()/.test(after)
}

function formDataOwnsGenerationQueue(text: string): boolean {
  return /createChecklistWriteQueue(?:<[^>]+>)?\s*\(/.test(text)
    && /persist:\s*async\s*\(items\)/.test(text)
    && /await\s+cas\.save\(/.test(text)
    && /await\s+queue\.flush\(\)/.test(text)
    && !text.includes('_pendingItems')
}

function hostFreezesOnlyStructuredInput(text: string): boolean {
  return text.includes("import { pendingWriteBarrierActive } from './sync/pendingWrites'")
    && text.includes('const businessReadonly = computed(() => !!props.readonly)')
    && text.includes('businessReadonly.value || pendingWriteBarrierActive.value')
    && text.includes(':is-readonly="isReadonly"')
    && text.includes(':readonly="businessReadonly"')
    && !text.includes(':readonly="isReadonly"')
}

describe('私有防抖写入方完整保存屏障', () => {
  const actual = offenders()

  it('扫描器分母没失锚（D2 已接入的写入方能被同一组正则认出来）', () => {
    const d2 = sourceOf('components/workpaper/composables/useD2Detail.ts')
    expect(DEBOUNCE.test(d2) && SAVE.test(d2) && REGISTERED.test(d2)).toBe(true)
  })

  it('106 个活写入方逐项登记 pending-only flusher', () => {
    expect(MIGRATED_WRITERS).toHaveLength(106)
    expect(new Set(MIGRATED_WRITERS).size).toBe(MIGRATED_WRITERS.length)
    const invalid = MIGRATED_WRITERS.filter((rel) => {
      const text = sourceOf(rel)
      return !DEBOUNCE.test(text)
        || !SAVE.test(text)
        || !REGISTERED.test(text)
        || !hasPendingOnlyFlusher(text)
    })
    expect(invalid).toEqual([])
  })

  it('未登记写入方只剩两条已证明不可达的死路径', () => {
    expect(actual).toEqual(Object.keys(DEAD_WRITERS).sort())
  })

  it('死路径仍会写盘、仍未登记，而且没有生产 import 消费者', () => {
    for (const rel of Object.keys(DEAD_WRITERS)) {
      const text = sourceOf(rel)
      expect(DEBOUNCE.test(text) && SAVE.test(text), rel).toBe(true)
      expect(REGISTERED.test(text), rel).toBe(false)
      expect(productionImporters(rel), rel).toEqual([])
    }
  })

  it('10 个父宿主消费 rejection、队列追踪 HTTP，并只冻结结构化输入', () => {
    expect(PARENT_QUEUE_BINDINGS).toHaveLength(10)
    const invalid = PARENT_QUEUE_BINDINGS.flatMap(({ host, formData }) => {
      const failures: string[] = []
      if (!hostConsumesRejectionWithoutTracking(sourceOf(host))) failures.push(`${host}:host`)
      if (!hostFreezesOnlyStructuredInput(sourceOf(host))) failures.push(`${host}:freeze`)
      if (!formDataOwnsGenerationQueue(sourceOf(formData))) failures.push(`${formData}:queue`)
      return failures
    })
    expect(invalid).toEqual([])
  })

  it('非写盘防抖豁免仍可被当前源码证伪', () => {
    for (const rel of Object.keys(NON_WRITING_DEBOUNCE)) {
      const text = sourceOf(rel)
      expect(DEBOUNCE.test(text), rel).toBe(true)
      const callback = /debounceTimer\s*=\s*setTimeout\(\(\)\s*=>\s*\{([\s\S]*?)\},\s*\d+\s*\)/.exec(text)?.[1] || ''
      expect(callback, rel).toContain('recompute()')
      expect(SAVE.test(callback), rel).toBe(false)
    }
  })
})

// ─── G 共享切换器宿主的过渡静止点 ─────────────────────────────────────────────
//
// `useGRenderModeSwitch` 会在挂载后自动把受管底稿恢复到 OnlyOffice 模式。过渡期间若宿主
// 不冻结结构化输入、或 flushHtml 不 await formData.flushPending()，用户这一刻的编辑既进不了
// 已读出的 projection，又会被随后的 OO 保存覆盖 ⇒ 静默丢写（spec R1.4）。
//
// 分母由真实 import 反查，不写死：新增消费宿主会让双向相等断言立刻失败。

/** 16 个宿主；每条都必须由当前源码正向证明，不是豁免表。 */
const G_SWITCH_HOSTS: readonly string[] = [
  'components/workpaper/GtG10TradingFinancialLiabilities.vue',
  'components/workpaper/GtG11InvestmentIncome.vue',
  'components/workpaper/GtG12NetHedgeGains.vue',
  'components/workpaper/GtG13FairValueChanges.vue',
  'components/workpaper/GtG14CreditImpairmentLoss.vue',
  'components/workpaper/GtG1TradingFinancialAssets.vue',
  'components/workpaper/GtG2InterestReceivable.vue',
  'components/workpaper/GtG3DividendReceivable.vue',
  'components/workpaper/GtG4BondInvestmentEcl.vue',
  'components/workpaper/GtG4BondInvestmentMain.vue',
  'components/workpaper/GtG4BondInvestmentSppi.vue',
  'components/workpaper/GtG5LongTermReceivable.vue',
  'components/workpaper/GtG6OtherBondMain.vue',
  'components/workpaper/GtG6OtherBondSppi.vue',
  'components/workpaper/GtG8OtherEquityInstruments.vue',
  'components/workpaper/GtG9OtherNoncurrentFinancial.vue',
]

/** 14 个仍按 LWW 保存、但必须 await + 接入屏障的 formData（strict CAS 迁移见 R1.3 递减清单）。 */
const G_AWAIT_ONLY_FORM_DATA: readonly string[] = [
  'components/workpaper/composables/useG10FormData.ts',
  'components/workpaper/composables/useG11FormData.ts',
  'components/workpaper/composables/useG12FormData.ts',
  'components/workpaper/composables/useG13FormData.ts',
  'components/workpaper/composables/useG14FormData.ts',
  'components/workpaper/composables/useG1TraFinFormData.ts',
  'components/workpaper/composables/useG3FormData.ts',
  'components/workpaper/composables/useG4EclFormData.ts',
  'components/workpaper/composables/useG5LonRecFormData.ts',
  'components/workpaper/composables/useG6MainFormData.ts',
  'components/workpaper/composables/useG6SppiFormData.ts',
  'components/workpaper/composables/useG8FormData.ts',
  'components/workpaper/composables/useG9FormData.ts',
  'composables/useG4SppiFormData.ts',
]

/** 反查所有 import `useGRenderModeSwitch` 的生产文件（.vue 宿主）。 */
function gRenderModeSwitchConsumers(): string[] {
  return walk(SRC, [])
    .filter((file) => /\.vue$/.test(file))
    .filter((file) => /\bfrom\s+['"][^'"]*useGRenderModeSwitch['"]/.test(readFileSync(file, 'utf-8')))
    .map((file) => relative(SRC, file).split('\\').join('/'))
    .sort()
}

/**
 * 逐个只读绑定回溯最近的开标签：OnlyOffice 挂点必须绑 businessReadonly（否则切过去就是只读），
 * HTML 侧输入必须留在 isReadonly 上（否则过渡期间仍可编辑 ⇒ 丢写）。只比字符串会把两类混在一起，
 * 故按标签判定。
 *
 * 🔴 两种属性名都要采：OnlyOffice 挂点与 `GtGridSheet` 用 `:readonly=`，而 G 循环的子 Tab
 * 全部用 `:is-readonly=`。只采 `/:readonly="/`（需要紧邻的冒号，`:is-readonly=` 前面是 `-`
 * 故匹配不上）会让 7/16 个宿主的 HTML 侧集合为空，`[].some()` 恒 false ⇒ 整条判据恒绿。
 * 2026-11-01 磁盘变异坐实过：GtG3 的 8 处绑定全改成 businessReadonly（等于整稿拆掉过渡冻结），
 * 旧判据仍 15/15 全绿。
 */
function readonlyBindingsByOwner(text: string): { oo: string[]; html: string[] } {
  const lines = text.split(/\r?\n/)
  const oo: string[] = []
  const html: string[] = []
  lines.forEach((line, index) => {
    const bound = /:(?:is-)?readonly="([^"]+)"/.exec(line)
    if (!bound) return
    let owner = '?'
    for (let j = index; j >= 0; j--) {
      const tag = /<([A-Za-z][\w.-]*)/.exec(lines[j])
      if (tag) { owner = tag[1]; break }
    }
    ;(owner === 'GtOnlyOfficeSheet' ? oo : html).push(bound[1])
  })
  return { oo, html }
}

describe('G 共享切换器宿主的过渡静止点', () => {
  it('宿主分母由真实 import 反查，与清单双向相等', () => {
    expect(gRenderModeSwitchConsumers()).toEqual([...G_SWITCH_HOSTS])
    expect(new Set(G_SWITCH_HOSTS).size).toBe(G_SWITCH_HOSTS.length)
  })

  it('16 个宿主都冻结 HTML 结构化输入，且不冻结 OnlyOffice 挂点', () => {
    const invalid = G_SWITCH_HOSTS.filter((rel) => {
      const text = sourceOf(rel)
      const { oo, html } = readonlyBindingsByOwner(text)
      return !text.includes("import { pendingWriteBarrierActive } from './sync/pendingWrites'")
        || !text.includes('const businessReadonly = computed(() => !!props.readonly)')
        || !text.includes('businessReadonly.value || pendingWriteBarrierActive.value')
        || oo.length === 0
        || oo.some((bound) => bound !== 'businessReadonly')
        // 空集合会让下面的 some() 恒 false（= 空断言），必须显式要求有被观测的 HTML 输入
        || html.length < 2
        // 写死 `true` 的 Tab 是永久只读，严于屏障，不可能在过渡期间被编辑 ⇒ 放行
        || html.some((bound) => bound !== 'isReadonly' && bound !== 'true')
    })
    expect(invalid).toEqual([])
  })

  it('只读绑定的取值集合封闭（出现第四种写法就必须人工复核）', () => {
    // 比数字区间更不易失锚：模板增删行不影响，但任何新绑定值（例如直接绑某个局部 flag）
    // 都会让这条红，强制回到「这个值在过渡期间会不会放开编辑」这个问题上。
    const values = new Set<string>()
    const hardcoded: string[] = []
    for (const rel of G_SWITCH_HOSTS) {
      const { oo, html } = readonlyBindingsByOwner(sourceOf(rel))
      expect(oo.length, `${rel} 的 OnlyOffice 挂点数`).toBe(2)
      for (const bound of [...oo, ...html]) values.add(bound)
      if (html.includes('true')) hardcoded.push(rel)
    }
    expect([...values].sort()).toEqual(['businessReadonly', 'isReadonly', 'true'])
    expect(hardcoded.sort()).toEqual([
      'components/workpaper/GtG4BondInvestmentEcl.vue',
      'components/workpaper/GtG8OtherEquityInstruments.vue',
    ])
  })

  it('16 个宿主的 flushHtml 真 await flushPending（fire-and-forget 会读到旧投影）', () => {
    const invalid = G_SWITCH_HOSTS.filter((rel) => {
      const text = sourceOf(rel)
      const flushHtml = text.indexOf('flushHtml: async () => {')
      if (flushHtml < 0) return true
      // 锚点必须是真实调用 `await readStoreProjection`，不能是裸 `readStoreProjection`——
      // 顺序刚性的注释里也写着这个词，按裸词截断会把 await 行切掉、判据恒红。
      const projection = text.indexOf('await readStoreProjection', flushHtml)
      if (projection < 0) return true
      const body = text.slice(flushHtml, projection)
      return !/await\s+formData\.flushPending\(\)/.test(body)
    })
    expect(invalid).toEqual([])
  })

  it('宿主不得遗留裸 formData.flushPending()（现在返回 Promise，裸调会漏掉失败）', () => {
    const invalid = G_SWITCH_HOSTS.filter((rel) => (
      /(?<!await |void )formData\.flushPending\(\)(?!\s*\.catch)/.test(sourceOf(rel))
    ))
    expect(invalid).toEqual([])
  })

  it('14 个 await-only formData 的 flushPending 是 Promise、已接入屏障且被导出', () => {
    expect(G_AWAIT_ONLY_FORM_DATA).toHaveLength(14)
    const invalid = G_AWAIT_ONLY_FORM_DATA.filter((rel) => {
      const text = sourceOf(rel)
      const isAsync = /async function _?flushPending\(\): Promise<void>/.test(text)
      const registered = /registerPendingFlusher\(_?flushPending\)/.test(text)
      // 真正 await 下层写入：批量型 await _doSave，逐项型 await Promise.all(inFlight)
      const awaits = /await _doSave\(items\)/.test(text) || /await Promise\.all\(inFlight\)/.test(text)
      const exported = /flushPending(?:,|: _flushPending,)/.test(text)
      return !isAsync || !registered || !awaits || !exported
    })
    expect(invalid).toEqual([])
  })

  // 失败如何到达调用方分两种形态，必须分别证明；混成一条判据会让其中一种恒绿：
  //   * 显式重抛：_doSave 的 catch 里 rethrow，或逐项 saveImmediate 耗尽重试、落本地草稿后 throw；
  //   * 自然冒泡：saveImmediate 整个函数体没有 try，PUT 的 rejection 直接向上传。
  const G_FORM_DATA_EXPLICIT_THROW: readonly string[] = [
    'components/workpaper/composables/useG10FormData.ts',
    'components/workpaper/composables/useG11FormData.ts',
    'components/workpaper/composables/useG12FormData.ts',
    'components/workpaper/composables/useG3FormData.ts',
    'components/workpaper/composables/useG4EclFormData.ts',
    'components/workpaper/composables/useG6MainFormData.ts',
    'components/workpaper/composables/useG6SppiFormData.ts',
    'components/workpaper/composables/useG8FormData.ts',
    'components/workpaper/composables/useG9FormData.ts',
    'composables/useG4SppiFormData.ts',
  ]
  const G_FORM_DATA_NATURAL_PROPAGATION: readonly string[] = [
    'components/workpaper/composables/useG13FormData.ts',
    'components/workpaper/composables/useG14FormData.ts',
    'components/workpaper/composables/useG1TraFinFormData.ts',
    'components/workpaper/composables/useG5LonRecFormData.ts',
  ]

  it('两种失败传递形态的清单合起来恰好是那 14 个，不重不漏', () => {
    expect([...G_FORM_DATA_EXPLICIT_THROW, ...G_FORM_DATA_NATURAL_PROPAGATION].sort())
      .toEqual([...G_AWAIT_ONLY_FORM_DATA].sort())
    const overlap = G_FORM_DATA_EXPLICIT_THROW
      .filter((rel) => G_FORM_DATA_NATURAL_PROPAGATION.includes(rel))
    expect(overlap).toEqual([])
  })

  it('显式重抛组：写入失败真的 throw 出来', () => {
    const invalid = G_FORM_DATA_EXPLICIT_THROW.filter((rel) => {
      const text = sourceOf(rel)
      // 判据只认「ElMessage 之后、同一个 catch 块里 throw err」这件事本身；
      // 不把中间的注释行写进正则——删注释会让判据变红而语义没变，那种脆会训练人去改判据。
      const rethrowsInDoSave = /ElMessage\.error\('[^']*'\)[\s\S]{0,200}?throw err/.test(text)
      const throwsAfterDraft = /throw new Error\(`\u4fdd\u5b58\u672a\u843d\u5e93/.test(text)
      return !rethrowsInDoSave && !throwsAfterDraft
    })
    expect(invalid).toEqual([])
  })

  // R1.3「迁移清单只许减少」：固定长度断言看不出方向（迁一家红、退一家也红）。
  // 这里用单向上限 + 与 strict CAS 清单互斥，保证 LWW 这边只能变短。
  it('await-only（仍 LWW）清单只许缩短，且与 strict CAS 调用面互斥', () => {
    expect(G_AWAIT_ONLY_FORM_DATA.length).toBeLessThanOrEqual(14)
    expect(new Set(G_AWAIT_ONLY_FORM_DATA).size).toBe(G_AWAIT_ONLY_FORM_DATA.length)
    const strict = G_AWAIT_ONLY_FORM_DATA.filter((rel) => (
      /createChecklistCasClient|createChecklistWriteQueue/.test(sourceOf(rel))
    ))
    expect(strict).toEqual([])
  })

  it('自然冒泡组：saveImmediate 体内没有 try，PUT rejection 无处被吞', () => {
    const invalid = G_FORM_DATA_NATURAL_PROPAGATION.filter((rel) => {
      const text = sourceOf(rel)
      const start = text.search(/async function saveImmediate\(/)
      if (start < 0) return true
      const open = text.indexOf('{', start)
      let depth = 0
      let end = -1
      for (let i = open; i < text.length; i++) {
        if (text[i] === '{') depth += 1
        else if (text[i] === '}') { depth -= 1; if (depth === 0) { end = i; break } }
      }
      if (end < 0) return true
      const body = text.slice(start, end)
      return !/await api\.put\(/.test(body) || /\btry\s*\{/.test(body) || /\bcatch\b/.test(body)
    })
    expect(invalid).toEqual([])
  })

  // 🔴 必须全文件扫，不能只看 flushPending 之后的若干字符：debouncedSave 与 restoreDrafts
  //    里的 `void saveImmediate(...)` 正是「计时器已触发、PUT 已在途」的来源，它们在
  //    flushPending 之前或很远处，窗口式扫描看不到（design §2.3「在途型」）。
  it('14 个 formData 全文件无裸 fire-and-forget 保存：在途 PUT 一律交给屏障', () => {
    const invalid = G_AWAIT_ONLY_FORM_DATA.flatMap((rel) => {
      const text = sourceOf(rel)
      const bare = [...text.matchAll(/void\s+(?:_doSave|saveImmediate)\(/g)]
      const tracked = [...text.matchAll(/void trackPendingWrite\((?:_doSave|saveImmediate)\(/g)]
      const failures: string[] = []
      if (bare.length > 0) failures.push(`${rel}:bare=${bare.length}`)
      if (tracked.length === 0) failures.push(`${rel}:untracked`)
      if (!/import \{ registerPendingFlusher, trackPendingWrite \} from/.test(text)) {
        failures.push(`${rel}:import`)
      }
      return failures
    })
    expect(invalid).toEqual([])
  })

  it('在途调用点总数与现算一致（19 处），少了就是有人改回 fire-and-forget', () => {
    const total = G_AWAIT_ONLY_FORM_DATA.reduce((sum, rel) => (
      sum + [...sourceOf(rel).matchAll(/void trackPendingWrite\((?:_doSave|saveImmediate)\(/g)].length
    ), 0)
    expect(total).toBe(19)
  })

  it('卸载路径不得静默吞失败：要么有草稿兜底/ElMessage，要么留下日志', () => {
    const invalid = G_AWAIT_ONLY_FORM_DATA.filter((rel) => {
      const text = sourceOf(rel)
      const dispose = text.indexOf('onScopeDispose(')
      if (dispose < 0) return true
      const body = text.slice(dispose, dispose + 700)
      if (!/void _?flushPending\(\)/.test(body)) return true  // 只清 timer 不冲刷 = 丢写
      if (/catch\(\(\) => undefined\)/.test(body)) {
        // 允许静默，但必须另有处置：_doSave 会 ElMessage，或 saveImmediate 落本地草稿
        return !/ElMessage\.error\(/.test(text) && !/localStorage\.setItem\(/.test(text)
      }
      return !/console\.error\(/.test(body)
    })
    expect(invalid).toEqual([])
  })
})
