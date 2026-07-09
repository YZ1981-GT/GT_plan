/**
 * useD1Disclosure — D1 附注披露（上市+国企）composable
 *
 * Spec: .kiro/specs/d1-disclosure-note/
 * Tasks: 2.1~2.8
 *
 * 通过 variant='listed'|'soe' 区分上市/国企版本。
 * 复用 useD1FormulaEngine 纯函数 + allResponses Map 跨sheet取数。
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import { parseNum, calcSubtotal, calcNetValue, safeDivide, calcBadDebtEndBalance } from './useD1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type DisclosureVariant = 'listed' | 'soe'
export type RowType = 'fixed' | 'dynamic' | 'summary'

export interface PledgedRow { rowId: string; rowType: RowType; category: string; isFixed: boolean; pledgedAmount: number }
export interface EndorsedRow { rowId: string; rowType: RowType; category: string; isFixed: boolean; derecognizedAmount: number; notDerecognizedAmount: number }
export interface TransferRow { rowId: string; rowType: RowType; category: string; isFixed: boolean; transferAmount: number }
export interface BadDebtClassRow { rowId: string; rowType: RowType; label: string; isFixed: boolean; balance: number; ratio: number; provision: number; lossRate: number; bookValue: number }
export interface IndividualDetailRow { rowId: string; rowType: RowType; name: string; isFixed: boolean; balance: number; provision: number; lossRate: number; basis: string }
export interface PortfolioDetailRow { rowId: string; rowType: RowType; drawerTypeOrAging: string; isFixed: boolean; balance: number; provision: number; lossRate: number }
export interface BadDebtMovementRow { rowId: string; rowType: RowType; label: string; isFixed: boolean; priorBalance: number; provision: number; reversal: number; writeOff: number; transfer: number; other: number; endBalance: number }
export interface ReversalDetailRow { rowId: string; rowType: RowType; isFixed: boolean; companyName: string; reversalReason: string; originalMethod: string; reversalBasis: string; amount: number }
export interface WriteOffDetailRow { rowId: string; rowType: RowType; isFixed: boolean; companyName: string; noteType: string; amount: number; reason: string; procedure: string; relatedPartyFlag: string }
export interface CategorySummaryRow { rowId: string; rowType: RowType; category: string; isFixed: boolean; endBalance: number; endProvision: number; endBookValue: number; priorBalance: number; priorProvision: number; priorBookValue: number }

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export interface UseD1DisclosureOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  variant: DisclosureVariant
  saveImmediate: SaveFn
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

export const DISCLOSURE_GUIDANCE: Record<string, string[]> = {
  top: [
    '【提示：企业因销售商品、提供服务等取得的、不属于《中华人民共和国票据法》规范票据的"云信"、"融信"等数字化应收账款债权凭证，不应当在"应收票据"项目中列示。企业管理"云信"、"融信"等的业务模式以收取合同现金流量为目标的，应当在"应收账款"项目中列示；既以收取合同现金流量为目标又以出售为目标的，应当在"应收款项融资"项目中列示。',
    '如果法律上认定供应链票据属于《商业汇票承兑、贴现与再贴现管理办法》（中国人民银行中国银行保险监督管理委员会令〔2022〕第4号）的范围、具备《票据法》规定的要件，则持有方应当自法律认定生效日（2023年1月1日）起将其作为"应收票据"进行会计处理（根据其业务模式列示为应收票据或应收款项融资），且无需对前期比较期间数据进行追溯调整。】',
  ],
  tableHint: ['【上面各张表均可添加行项目】'],
  transferIntro: [
    '（如根据《企业会计准则第23号——金融资产转移》终止确认的应收票据，列示其终止确认的金额，及与终止确认相关的利得和损失）',
  ],
  endorsed: [
    '【提示：证监会《2014 年上市公司年报会计监管报告》，对已背书或贴现且尚未到期的银行承兑汇票予以终止确认后，需在财务报表中补充披露终止确认的票据以及对票据被追索时可能存在的支付风险予以清晰说明。参考披露：',
    '用于贴现的银行承兑汇票是由信用等级较高的银行承兑，信用风险和延期付款风险很小，并且票据相关的利率风险已转移给银行，可以判断票据所有权上的主要风险和报酬已经转移，故终止确认。',
    '或：用于贴现的银行承兑汇票是由信用等级不高的银行承兑，贴现不影响追索权，票据相关的信用风险和延期付款风险仍没有转移，故未终止确认。】',
  ],
  badDebtClassification: ['【提示：此处披露未逾期的应收票据计提的坏账准备。若票据逾期，则应转入应收账款并计提坏账准备，账龄应连续计算。】'],
  writeOff: ['【提示：对于其中重要的应收票据，应逐项披露款项性质、核销原因、履行的核销程序及核销金额。实际核销的款项由关联交易产生的，应单独披露。】'],
}

export const ENDORSED_JUDGMENT_TEMPLATES: Record<string, string> = {
  derecognized: '用于贴现的银行承兑汇票是由信用等级较高的银行承兑，信用风险和延期付款风险很小，并且票据相关的利率风险已转移给银行，可以判断票据相关的所有风险和报酬已经转移。根据上述主要风险和报酬已经转移，故终止确认。',
  notDerecognized: '用于贴现的银行承兑汇票是由信用等级不高的银行承兑，贴现不影响追索权，票据相关的信用风险和延期付款风险仍没有转移，故未终止确认。',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function genId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function safeParseArray<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try { const p = JSON.parse(jsonStr); return Array.isArray(p) ? p : [] } catch { return [] }
}

const CROSS_SHEET_KEYS = {
  bankEndBalance: 'D1-adj-gross-bank-current-audited',
  bankPriorBalance: 'D1-adj-gross-bank-prior-audited',
  bankEndProvision: 'D1-adj-baddebt-bank-current-audited',
  bankPriorProvision: 'D1-adj-baddebt-bank-prior-audited',
  commercialEndBalance: 'D1-adj-gross-commercial-current-audited',
  commercialPriorBalance: 'D1-adj-gross-commercial-prior-audited',
  commercialEndProvision: 'D1-adj-baddebt-commercial-current-audited',
  commercialPriorProvision: 'D1-adj-baddebt-commercial-prior-audited',
} as const

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1Disclosure(options: UseD1DisclosureOptions) {
  const { allResponses, variant, saveImmediate, isReadonly } = options
  const isLoading = ref(false)
  const prefix = variant === 'listed' ? 'D1-disc-listed-' : 'D1-disc-soe-'

  // ─── Section Order (Task 2.1) ────────────────────────────────────────────
  const sectionOrder = computed<string[]>(() =>
    variant === 'listed'
      ? ['pledged', 'endorsed', 'transfer', 'badDebtClass', 'badDebtMovement', 'writeOff']
      : ['categorySummary', 'badDebtClass', 'badDebtMovement', 'pledged', 'endorsed', 'transfer', 'writeOff']
  )

  // ─── Cross-Sheet Data (Task 2.1) ────────────────────────────────────────
  const crossSheetData = computed(() => {
    const m = allResponses.value
    const get = (k: string) => parseNum(m.get(k)?.remark ?? m.get(k)?.conclusion)
    return {
      bankEndBalance: get(CROSS_SHEET_KEYS.bankEndBalance),
      bankPriorBalance: get(CROSS_SHEET_KEYS.bankPriorBalance),
      bankEndProvision: get(CROSS_SHEET_KEYS.bankEndProvision),
      bankPriorProvision: get(CROSS_SHEET_KEYS.bankPriorProvision),
      commercialEndBalance: get(CROSS_SHEET_KEYS.commercialEndBalance),
      commercialPriorBalance: get(CROSS_SHEET_KEYS.commercialPriorBalance),
      commercialEndProvision: get(CROSS_SHEET_KEYS.commercialEndProvision),
      commercialPriorProvision: get(CROSS_SHEET_KEYS.commercialPriorProvision),
    }
  })

  const crossSheetStatus = computed<'loaded' | 'empty'>(() => {
    const d = crossSheetData.value
    return (d.bankEndBalance || d.commercialEndBalance) ? 'loaded' : 'empty'
  })

  // ─── Data Loading Helper ─────────────────────────────────────────────────
  function loadRows<T>(itemId: string): T[] {
    const resp = allResponses.value.get(prefix + itemId)
    return safeParseArray<T>(resp?.remark)
  }

  function persistRows(itemId: string, rows: any[]): void {
    if (isReadonly.value) return
    const fullId = prefix + itemId
    const item: ChecklistItem = { item_id: fullId, conclusion: null, remark: JSON.stringify(rows) }
    allResponses.value.set(fullId, item)
    saveImmediate([item])
  }

  // ─── Pledged Section (Task 2.2) ──────────────────────────────────────────
  const defaultPledgedRows: PledgedRow[] = [
    { rowId: 'pledged-fixed-bank', rowType: 'fixed', category: '银行承兑汇票', isFixed: true, pledgedAmount: 0 },
    { rowId: 'pledged-fixed-commercial', rowType: 'fixed', category: '商业承兑汇票', isFixed: true, pledgedAmount: 0 },
  ]
  const pledgedRows = ref<PledgedRow[]>(loadRows<PledgedRow>('pledged-rows').length ? loadRows<PledgedRow>('pledged-rows') : [...defaultPledgedRows])
  const pledgedTotal = computed<PledgedRow>(() => ({
    rowId: '__pledged_total__', rowType: 'summary', category: '合计', isFixed: true,
    pledgedAmount: calcSubtotal(pledgedRows.value.map(r => r.pledgedAmount)),
  }))
  function addPledgedRow(): void {
    pledgedRows.value.push({ rowId: genId('pl'), rowType: 'dynamic', category: '', isFixed: false, pledgedAmount: 0 })
    persistRows('pledged-rows', pledgedRows.value)
  }
  function removePledgedRow(rowId: string): void {
    pledgedRows.value = pledgedRows.value.filter(r => r.rowId !== rowId || r.isFixed)
    persistRows('pledged-rows', pledgedRows.value)
  }

  // ─── Endorsed Section (Task 2.3) ─────────────────────────────────────────
  const defaultEndorsedRows: EndorsedRow[] = [
    { rowId: 'endorsed-fixed-bank', rowType: 'fixed', category: '银行承兑汇票', isFixed: true, derecognizedAmount: 0, notDerecognizedAmount: 0 },
    { rowId: 'endorsed-fixed-commercial', rowType: 'fixed', category: '商业承兑汇票', isFixed: true, derecognizedAmount: 0, notDerecognizedAmount: 0 },
  ]
  const endorsedRows = ref<EndorsedRow[]>(loadRows<EndorsedRow>('endorsed-rows').length ? loadRows<EndorsedRow>('endorsed-rows') : [...defaultEndorsedRows])
  const endorsedTotal = computed<EndorsedRow>(() => ({
    rowId: '__endorsed_total__', rowType: 'summary', category: '合计', isFixed: true,
    derecognizedAmount: calcSubtotal(endorsedRows.value.map(r => r.derecognizedAmount)),
    notDerecognizedAmount: calcSubtotal(endorsedRows.value.map(r => r.notDerecognizedAmount)),
  }))
  function addEndorsedRow(): void {
    endorsedRows.value.push({ rowId: genId('en'), rowType: 'dynamic', category: '', isFixed: false, derecognizedAmount: 0, notDerecognizedAmount: 0 })
    persistRows('endorsed-rows', endorsedRows.value)
  }
  function removeEndorsedRow(rowId: string): void {
    endorsedRows.value = endorsedRows.value.filter(r => r.rowId !== rowId || r.isFixed)
    persistRows('endorsed-rows', endorsedRows.value)
  }

  // ─── Transfer Section (Task 2.4) ─────────────────────────────────────────
  const defaultTransferRows: TransferRow[] = [
    { rowId: 'transfer-fixed-bank', rowType: 'fixed', category: '银行承兑汇票', isFixed: true, transferAmount: 0 },
    { rowId: 'transfer-fixed-commercial', rowType: 'fixed', category: '商业承兑汇票', isFixed: true, transferAmount: 0 },
  ]
  const transferRows = ref<TransferRow[]>(loadRows<TransferRow>('transfer-rows').length ? loadRows<TransferRow>('transfer-rows') : [...defaultTransferRows])
  const transferTotal = computed<TransferRow>(() => ({
    rowId: '__transfer_total__', rowType: 'summary', category: '合计', isFixed: true,
    transferAmount: calcSubtotal(transferRows.value.map(r => r.transferAmount)),
  }))
  function addTransferRow(): void {
    transferRows.value.push({ rowId: genId('tr'), rowType: 'dynamic', category: '', isFixed: false, transferAmount: 0 })
    persistRows('transfer-rows', transferRows.value)
  }
  function removeTransferRow(rowId: string): void {
    transferRows.value = transferRows.value.filter(r => r.rowId !== rowId || r.isFixed)
    persistRows('transfer-rows', transferRows.value)
  }

  // ─── Bad Debt Classification (Task 2.5) ──────────────────────────────────
  function buildClassRows(periodKey: string): Ref<BadDebtClassRow[]> {
    const defaults: BadDebtClassRow[] = [
      { rowId: `class-${periodKey}-individual`, rowType: 'fixed', label: '按单项计提', isFixed: true, balance: 0, ratio: 0, provision: 0, lossRate: 0, bookValue: 0 },
      { rowId: `class-${periodKey}-portfolio-bank`, rowType: 'fixed', label: '按组合计提-银行承兑汇票', isFixed: true, balance: 0, ratio: 0, provision: 0, lossRate: 0, bookValue: 0 },
      { rowId: `class-${periodKey}-portfolio-commercial`, rowType: 'fixed', label: '按组合计提-商业承兑汇票', isFixed: true, balance: 0, ratio: 0, provision: 0, lossRate: 0, bookValue: 0 },
    ]
    const loaded = loadRows<BadDebtClassRow>(`class-${periodKey}-rows`)
    return ref(loaded.length ? loaded : [...defaults])
  }

  const classEndRows = buildClassRows('end')
  const classPriorRows = buildClassRows('prior')

  function computeClassTotal(rows: Ref<BadDebtClassRow[]>): ComputedRef<BadDebtClassRow> {
    return computed(() => {
      const totalBalance = calcSubtotal(rows.value.map(r => r.balance))
      const totalProvision = calcSubtotal(rows.value.map(r => r.provision))
      return {
        rowId: '__class_total__', rowType: 'summary' as RowType, label: '合计', isFixed: true,
        balance: totalBalance, ratio: totalBalance ? 1 : 0, provision: totalProvision,
        lossRate: safeDivide(totalProvision, totalBalance), bookValue: calcNetValue(totalBalance, totalProvision),
      }
    })
  }
  const classEndTotal = computeClassTotal(classEndRows)
  const classPriorTotal = computeClassTotal(classPriorRows)

  // Recalculate ratio/lossRate/bookValue for class rows when balance/provision change
  function recalcClassRow(row: BadDebtClassRow, totalBalance: number): BadDebtClassRow {
    return { ...row, ratio: safeDivide(row.balance, totalBalance), lossRate: safeDivide(row.provision, row.balance), bookValue: calcNetValue(row.balance, row.provision) }
  }

  // Individual detail rows
  const individualEndRows = ref<IndividualDetailRow[]>(loadRows<IndividualDetailRow>('individual-end-rows'))
  const individualPriorRows = ref<IndividualDetailRow[]>(loadRows<IndividualDetailRow>('individual-prior-rows'))

  function addIndividualRow(period: 'end' | 'prior'): void {
    const row: IndividualDetailRow = { rowId: genId('ind'), rowType: 'dynamic', name: '', isFixed: false, balance: 0, provision: 0, lossRate: 0, basis: '' }
    if (period === 'end') { individualEndRows.value.push(row); persistRows('individual-end-rows', individualEndRows.value) }
    else { individualPriorRows.value.push(row); persistRows('individual-prior-rows', individualPriorRows.value) }
  }
  function removeIndividualRow(rowId: string, period: 'end' | 'prior'): void {
    if (period === 'end') { individualEndRows.value = individualEndRows.value.filter(r => r.rowId !== rowId); persistRows('individual-end-rows', individualEndRows.value) }
    else { individualPriorRows.value = individualPriorRows.value.filter(r => r.rowId !== rowId); persistRows('individual-prior-rows', individualPriorRows.value) }
  }

  // Portfolio detail rows (bank + commercial × end/prior)
  const bankPortfolioEndRows = ref<PortfolioDetailRow[]>(loadRows<PortfolioDetailRow>('bank-portfolio-end-rows'))
  const bankPortfolioPriorRows = ref<PortfolioDetailRow[]>(loadRows<PortfolioDetailRow>('bank-portfolio-prior-rows'))
  const commercialPortfolioEndRows = ref<PortfolioDetailRow[]>(loadRows<PortfolioDetailRow>('commercial-portfolio-end-rows'))
  const commercialPortfolioPriorRows = ref<PortfolioDetailRow[]>(loadRows<PortfolioDetailRow>('commercial-portfolio-prior-rows'))

  function addPortfolioRow(type: 'bank' | 'commercial', period: 'end' | 'prior'): void {
    const row: PortfolioDetailRow = { rowId: genId('pf'), rowType: 'dynamic', drawerTypeOrAging: '', isFixed: false, balance: 0, provision: 0, lossRate: 0 }
    const key = `${type === 'bank' ? 'bank' : 'commercial'}-portfolio-${period}-rows`
    const target = type === 'bank' ? (period === 'end' ? bankPortfolioEndRows : bankPortfolioPriorRows) : (period === 'end' ? commercialPortfolioEndRows : commercialPortfolioPriorRows)
    target.value.push(row)
    persistRows(key, target.value)
  }
  function removePortfolioRow(rowId: string, type: 'bank' | 'commercial', period: 'end' | 'prior'): void {
    const key = `${type === 'bank' ? 'bank' : 'commercial'}-portfolio-${period}-rows`
    const target = type === 'bank' ? (period === 'end' ? bankPortfolioEndRows : bankPortfolioPriorRows) : (period === 'end' ? commercialPortfolioEndRows : commercialPortfolioPriorRows)
    target.value = target.value.filter(r => r.rowId !== rowId)
    persistRows(key, target.value)
  }

  // ─── Bad Debt Movement (Task 2.6) ────────────────────────────────────────
  function buildMovementRows(): BadDebtMovementRow[] {
    const loaded = loadRows<BadDebtMovementRow>('movement-rows')
    if (loaded.length) return loaded
    if (variant === 'listed') {
      return [{ rowId: 'mv-total', rowType: 'fixed', label: '合计', isFixed: true, priorBalance: 0, provision: 0, reversal: 0, writeOff: 0, transfer: 0, other: 0, endBalance: 0 }]
    }
    return [
      { rowId: 'mv-individual', rowType: 'fixed', label: '按单项计提', isFixed: true, priorBalance: 0, provision: 0, reversal: 0, writeOff: 0, transfer: 0, other: 0, endBalance: 0 },
      { rowId: 'mv-portfolio', rowType: 'fixed', label: '按组合计提', isFixed: true, priorBalance: 0, provision: 0, reversal: 0, writeOff: 0, transfer: 0, other: 0, endBalance: 0 },
      { rowId: 'mv-total', rowType: 'fixed', label: '合计', isFixed: true, priorBalance: 0, provision: 0, reversal: 0, writeOff: 0, transfer: 0, other: 0, endBalance: 0 },
    ]
  }
  const movementRows = ref<BadDebtMovementRow[]>(buildMovementRows())

  const movementTotal = computed<BadDebtMovementRow>(() => {
    const rows = variant === 'soe' ? movementRows.value.filter(r => r.label !== '合计') : movementRows.value
    return {
      rowId: '__mv_total__', rowType: 'summary', label: '合计', isFixed: true,
      priorBalance: calcSubtotal(rows.map(r => r.priorBalance)),
      provision: calcSubtotal(rows.map(r => r.provision)),
      reversal: calcSubtotal(rows.map(r => r.reversal)),
      writeOff: calcSubtotal(rows.map(r => r.writeOff)),
      transfer: calcSubtotal(rows.map(r => r.transfer)),
      other: calcSubtotal(rows.map(r => r.other)),
      endBalance: calcSubtotal(rows.map(r => r.endBalance)),
    }
  })

  // Reversal detail rows
  const reversalDetailRows = ref<ReversalDetailRow[]>(loadRows<ReversalDetailRow>('reversal-rows'))
  const reversalDetailTotal = computed<ReversalDetailRow>(() => ({
    rowId: '__rev_total__', rowType: 'summary', isFixed: true, companyName: '合计', reversalReason: '', originalMethod: '', reversalBasis: '',
    amount: calcSubtotal(reversalDetailRows.value.map(r => r.amount)),
  }))
  function addReversalRow(): void {
    reversalDetailRows.value.push({ rowId: genId('rv'), rowType: 'dynamic', isFixed: false, companyName: '', reversalReason: '', originalMethod: '', reversalBasis: '', amount: 0 })
    persistRows('reversal-rows', reversalDetailRows.value)
  }
  function removeReversalRow(rowId: string): void {
    reversalDetailRows.value = reversalDetailRows.value.filter(r => r.rowId !== rowId)
    persistRows('reversal-rows', reversalDetailRows.value)
  }

  // ─── Write-Off Section (Task 2.7) ────────────────────────────────────────
  const writeOffAmountResp = allResponses.value.get(prefix + 'writeoff-amount')
  const writeOffAmount = ref<number>(parseNum(writeOffAmountResp?.remark))

  const writeOffDetailRows = ref<WriteOffDetailRow[]>(loadRows<WriteOffDetailRow>('writeoff-rows'))
  const writeOffDetailTotal = computed<WriteOffDetailRow>(() => ({
    rowId: '__wo_total__', rowType: 'summary', isFixed: true, companyName: '合计', noteType: '', amount: calcSubtotal(writeOffDetailRows.value.map(r => r.amount)), reason: '', procedure: '', relatedPartyFlag: '',
  }))
  function addWriteOffRow(): void {
    writeOffDetailRows.value.push({ rowId: genId('wo'), rowType: 'dynamic', isFixed: false, companyName: '', noteType: '', amount: 0, reason: '', procedure: '', relatedPartyFlag: '' })
    persistRows('writeoff-rows', writeOffDetailRows.value)
  }
  function removeWriteOffRow(rowId: string): void {
    writeOffDetailRows.value = writeOffDetailRows.value.filter(r => r.rowId !== rowId)
    persistRows('writeoff-rows', writeOffDetailRows.value)
  }

  // ─── Category Summary - SOE Only (Task 2.8) ──────────────────────────────
  const importedTopSummaryRows = ref<any[]>(loadRows<any>('top-summary-rows'))
  const categorySummaryRows = computed<CategorySummaryRow[]>(() => {
    const d = crossSheetData.value
    const hasCross = Boolean(d.bankEndBalance || d.bankPriorBalance || d.bankEndProvision || d.bankPriorProvision || d.commercialEndBalance || d.commercialPriorBalance || d.commercialEndProvision || d.commercialPriorProvision)
    if (!hasCross && variant === 'soe' && importedTopSummaryRows.value.length > 0) {
      return importedTopSummaryRows.value.map((r, idx) => ({
        rowId: r.rowId || `cat-import-${idx}`,
        rowType: (r.rowType || 'fixed') as RowType,
        category: r.category || '',
        isFixed: true,
        endBalance: parseNum(r.endBalance),
        endProvision: parseNum(r.endProvision),
        endBookValue: parseNum(r.endBookValue),
        priorBalance: parseNum(r.priorBalance),
        priorProvision: parseNum(r.priorProvision),
        priorBookValue: parseNum(r.priorBookValue),
      }))
    }
    return [
      {
        rowId: 'cat-bank', rowType: 'fixed' as RowType, category: '银行承兑汇票', isFixed: true,
        endBalance: d.bankEndBalance, endProvision: d.bankEndProvision, endBookValue: calcNetValue(d.bankEndBalance, d.bankEndProvision),
        priorBalance: d.bankPriorBalance, priorProvision: d.bankPriorProvision, priorBookValue: calcNetValue(d.bankPriorBalance, d.bankPriorProvision),
      },
      {
        rowId: 'cat-commercial', rowType: 'fixed' as RowType, category: '商业承兑汇票', isFixed: true,
        endBalance: d.commercialEndBalance, endProvision: d.commercialEndProvision, endBookValue: calcNetValue(d.commercialEndBalance, d.commercialEndProvision),
        priorBalance: d.commercialPriorBalance, priorProvision: d.commercialPriorProvision, priorBookValue: calcNetValue(d.commercialPriorBalance, d.commercialPriorProvision),
      },
    ]
  })

  const categorySummaryTotal = computed<CategorySummaryRow>(() => {
    const rows = categorySummaryRows.value
    const endBal = calcSubtotal(rows.map(r => r.endBalance))
    const endProv = calcSubtotal(rows.map(r => r.endProvision))
    const priorBal = calcSubtotal(rows.map(r => r.priorBalance))
    const priorProv = calcSubtotal(rows.map(r => r.priorProvision))
    return {
      rowId: '__cat_total__', rowType: 'summary', category: '合计', isFixed: true,
      endBalance: endBal, endProvision: endProv, endBookValue: calcNetValue(endBal, endProv),
      priorBalance: priorBal, priorProvision: priorProv, priorBookValue: calcNetValue(priorBal, priorProv),
    }
  })

  // ─── Generic updateCell (all sections) ───────────────────────────────────
  function updateCell(section: string, rowId: string, field: string, value: number | string): void {
    if (isReadonly.value) return
    const numVal = typeof value === 'number' ? value : parseNum(value)

    if (section === 'pledged') {
      pledgedRows.value = pledgedRows.value.map(r => r.rowId === rowId ? { ...r, [field]: field === 'category' ? value : numVal } : r)
      persistRows('pledged-rows', pledgedRows.value)
    } else if (section === 'endorsed') {
      endorsedRows.value = endorsedRows.value.map(r => r.rowId === rowId ? { ...r, [field]: field === 'category' ? value : numVal } : r)
      persistRows('endorsed-rows', endorsedRows.value)
    } else if (section === 'transfer') {
      transferRows.value = transferRows.value.map(r => r.rowId === rowId ? { ...r, [field]: field === 'category' ? value : numVal } : r)
      persistRows('transfer-rows', transferRows.value)
    } else if (section === 'classEnd') {
      const totalBal = classEndTotal.value.balance
      classEndRows.value = classEndRows.value.map(r => r.rowId === rowId ? recalcClassRow({ ...r, [field]: numVal }, totalBal) : r)
      persistRows('class-end-rows', classEndRows.value)
    } else if (section === 'classPrior') {
      const totalBal = classPriorTotal.value.balance
      classPriorRows.value = classPriorRows.value.map(r => r.rowId === rowId ? recalcClassRow({ ...r, [field]: numVal }, totalBal) : r)
      persistRows('class-prior-rows', classPriorRows.value)
    } else if (section === 'individualEnd') {
      individualEndRows.value = individualEndRows.value.map(r => {
        if (r.rowId !== rowId) return r
        const updated = { ...r, [field]: field === 'name' || field === 'basis' ? value : numVal }
        updated.lossRate = safeDivide(updated.provision, updated.balance)
        return updated
      })
      persistRows('individual-end-rows', individualEndRows.value)
    } else if (section === 'individualPrior') {
      individualPriorRows.value = individualPriorRows.value.map(r => {
        if (r.rowId !== rowId) return r
        const updated = { ...r, [field]: field === 'name' || field === 'basis' ? value : numVal }
        updated.lossRate = safeDivide(updated.provision, updated.balance)
        return updated
      })
      persistRows('individual-prior-rows', individualPriorRows.value)
    } else if (section.startsWith('portfolio-')) {
      // section format: portfolio-bank-end, portfolio-bank-prior, portfolio-commercial-end, portfolio-commercial-prior
      const parts = section.split('-')
      const type = parts[1] as 'bank' | 'commercial'
      const period = parts[2] as 'end' | 'prior'
      const key = `${type === 'bank' ? 'bank' : 'commercial'}-portfolio-${period}-rows`
      const target = type === 'bank' ? (period === 'end' ? bankPortfolioEndRows : bankPortfolioPriorRows) : (period === 'end' ? commercialPortfolioEndRows : commercialPortfolioPriorRows)
      target.value = target.value.map(r => {
        if (r.rowId !== rowId) return r
        const updated = { ...r, [field]: field === 'drawerTypeOrAging' ? value : numVal }
        updated.lossRate = safeDivide(updated.provision, updated.balance)
        return updated
      })
      persistRows(key, target.value)
    } else if (section === 'movement') {
      movementRows.value = movementRows.value.map(r => {
        if (r.rowId !== rowId) return r
        const updated = { ...r, [field]: numVal }
        updated.endBalance = calcBadDebtEndBalance(updated.priorBalance, updated.provision, updated.reversal, updated.writeOff, updated.transfer, updated.other)
        return updated
      })
      persistRows('movement-rows', movementRows.value)
    } else if (section === 'reversalDetail') {
      reversalDetailRows.value = reversalDetailRows.value.map(r => r.rowId === rowId ? { ...r, [field]: field === 'amount' ? numVal : value } : r)
      persistRows('reversal-rows', reversalDetailRows.value)
    } else if (section === 'writeOffDetail') {
      writeOffDetailRows.value = writeOffDetailRows.value.map(r => r.rowId === rowId ? { ...r, [field]: field === 'amount' ? numVal : value } : r)
      persistRows('writeoff-rows', writeOffDetailRows.value)
    } else if (section === 'writeOffAmount') {
      writeOffAmount.value = numVal
      const fullId = prefix + 'writeoff-amount'
      const item: ChecklistItem = { item_id: fullId, conclusion: null, remark: String(numVal) }
      allResponses.value.set(fullId, item)
      saveImmediate([item])
    } else if (section.startsWith('D1-disc-')) {
      // Note textarea persistence — section is the full item_id
      const item: ChecklistItem = { item_id: section, conclusion: null, remark: String(value) }
      allResponses.value.set(section, item)
      saveImmediate([item])
    }
  }

  // ─── Return ──────────────────────────────────────────────────────────────
  return {
    variant, sectionOrder, isLoading, crossSheetData, crossSheetStatus,
    // Pledged
    pledgedRows, pledgedTotal, addPledgedRow, removePledgedRow,
    // Endorsed
    endorsedRows, endorsedTotal, addEndorsedRow, removeEndorsedRow,
    // Transfer
    transferRows, transferTotal, addTransferRow, removeTransferRow,
    // Bad debt classification
    classEndRows, classEndTotal, classPriorRows, classPriorTotal,
    individualEndRows, individualPriorRows, addIndividualRow, removeIndividualRow,
    bankPortfolioEndRows, bankPortfolioPriorRows, commercialPortfolioEndRows, commercialPortfolioPriorRows,
    addPortfolioRow, removePortfolioRow,
    // Movement
    movementRows, movementTotal, reversalDetailRows, reversalDetailTotal, addReversalRow, removeReversalRow,
    // Write-off
    writeOffAmount, writeOffDetailRows, writeOffDetailTotal, addWriteOffRow, removeWriteOffRow,
    // Category summary (SOE)
    categorySummaryRows, categorySummaryTotal,
    // Generic
    updateCell,
  }
}
