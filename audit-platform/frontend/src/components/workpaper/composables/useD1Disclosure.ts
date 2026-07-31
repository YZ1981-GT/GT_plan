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
import {
  parseNum, calcSubtotal, calcNetValue, safeDivide, calcDisclosureBadDebtEnd,
  deriveClassRows,
} from './useD1FormulaEngine'
import {
  D1_ZERO_AMOUNTS,
  readD1AdjudicationTotals,
} from './d1AdjudicationModel'

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
export interface ReversalDetailRow {
  rowId: string
  rowType: RowType
  isFixed: boolean
  companyName: string
  /** 上市「转回原因」/ 国企「转回或收回原因、方式」 */
  reversalReason: string
  /** 上市「收回方式」（国企无此列） */
  originalMethod: string
  /** 上市「原确定坏账准备的依据」（文本；国企无此列） */
  reversalBasis: string
  amount: number
  /**
   * 国企「转回或收回前累计已计提坏账准备金额」。
   * 源模板 C59==SUM(C55:C58) → **数值列**，进合计行。
   * 历史数据曾把该列绑在文本字段 `reversalBasis` 上，加载时按需迁移（见 loadReversalRows）。
   */
  cumulativeProvision: number
}
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

// 🔴 已删除 `CROSS_SHEET_KEYS`（原有 8 条锚点字面量**全平台无写入方**）：
//   * `-current-audited` / `-prior-audited` 后缀从不持久化 —— 审定数是 computed 列，
//     `useD1Adjudication` 只存 `-current-unadj` / `-current-aje` / `-current-rje`；
//   * 前缀 `baddebt-` 与写入方的 `bd-` 不一致。
// 结果：披露①分类表的跨表取数**从未生效过**，`crossSheetStatus` 恒 'empty'、主表恒走
// 手工兜底 → 「四表入库 → D1-2/D1-4 → D1-1」这条链到披露表就断了，附注自然没数。
// 而两个单测（`useD1Disclosure.pbt.spec.ts` / `useD1DisclosureDerived.spec.ts`）**镜像了
// 同款错误锚点**播种 fixture，测试恒绿、生产恒死。
// 现改为唯一真源 `d1AdjudicationModel.readD1AdjudicationTotals`（与审定表同一纯函数）。

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

  // ─── Cross-Sheet Data（唯一真源 = 审定表共享模型）────────────────────────
  //
  // 源模板披露①分类表就是从审定表取数：
  //   上市 B9='审定表D1-1'!I8（银承期末审定原值）/ C9=!I12（坏账）/ D9=B9-C9
  //        E9=!E8（期初审定原值）/ F9=!E12 / G9=E9-F9
  //   国企 B8/C8/D8 与 E8/F8/G8 同构
  // 故此处直接消费 `readD1AdjudicationTotals`（与 D1-1 渲染同一函数、同一口径）。
  const adjTotals = computed(() => readD1AdjudicationTotals(allResponses.value))

  /** 保留旧字段名供既有调用方/测试消费（银承 + 商承四个口径），值改由共享模型派生。 */
  const crossSheetData = computed(() => {
    const t = adjTotals.value
    const g = (slug: string) => t.gross[slug] ?? D1_ZERO_AMOUNTS
    const p = (slug: string) => t.provision[slug] ?? D1_ZERO_AMOUNTS
    return {
      bankEndBalance: g('bank').currentAudited,
      bankPriorBalance: g('bank').priorAudited,
      bankEndProvision: p('bank').currentAudited,
      bankPriorProvision: p('bank').priorAudited,
      commercialEndBalance: g('commercial').currentAudited,
      commercialPriorBalance: g('commercial').priorAudited,
      commercialEndProvision: p('commercial').currentAudited,
      commercialPriorProvision: p('commercial').priorAudited,
    }
  })

  const crossSheetStatus = computed<'loaded' | 'empty'>(() =>
    adjTotals.value.hasData ? 'loaded' : 'empty',
  )

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
  // 🔴 质押 / 背书贴现 / 转应收账款三表源模板用的是「票据」而非「汇票」
  //    （分类总表才用「汇票」）——这是源模板的**逐表**措辞，附注模板 JSON 亦然，
  //    按表各自对齐，不做全局统一，否则同步后附注行名与模板骨架不匹配。
  const defaultPledgedRows: PledgedRow[] = [
    { rowId: 'pledged-fixed-bank', rowType: 'fixed', category: '银行承兑票据', isFixed: true, pledgedAmount: 0 },
    { rowId: 'pledged-fixed-commercial', rowType: 'fixed', category: '商业承兑票据', isFixed: true, pledgedAmount: 0 },
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
    { rowId: 'endorsed-fixed-bank', rowType: 'fixed', category: '银行承兑票据', isFixed: true, derecognizedAmount: 0, notDerecognizedAmount: 0 },
    { rowId: 'endorsed-fixed-commercial', rowType: 'fixed', category: '商业承兑票据', isFixed: true, derecognizedAmount: 0, notDerecognizedAmount: 0 },
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
  // 🔴 源模板（上市 R33 / 国企 R76）与附注模板 JSON 都**只列商业承兑票据**：
  //    票据逾期后应转入应收账款并计提坏账准备、账龄连续计算，出票人未履约的场景
  //    只对商业承兑成立。多推一行银行承兑会在附注里出现凭空的空数据行。
  const defaultTransferRows: TransferRow[] = [
    { rowId: 'transfer-fixed-commercial', rowType: 'fixed', category: '商业承兑票据', isFixed: true, transferAmount: 0 },
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
  // 🔴 账面余额 / 坏账准备是唯一真源；比例(%) / 预期信用损失率(%) / 账面价值
  //    一律**读时推导**（`deriveClassRows`），不再持久化派生值。
  //    旧实现把 ratio 存进行对象、编辑时用**编辑前**的合计做分母且只重算被编辑行 →
  //    浏览器实测比例漂移到 162.50%（应 100.00%）并随同步污染附注。
  function buildClassRowsRaw(periodKey: string): Ref<BadDebtClassRow[]> {
    const defaults: BadDebtClassRow[] = [
      { rowId: `class-${periodKey}-individual`, rowType: 'fixed', label: '按单项计提', isFixed: true, balance: 0, ratio: 0, provision: 0, lossRate: 0, bookValue: 0 },
      { rowId: `class-${periodKey}-portfolio-bank`, rowType: 'fixed', label: '按组合计提-银行承兑汇票', isFixed: true, balance: 0, ratio: 0, provision: 0, lossRate: 0, bookValue: 0 },
      { rowId: `class-${periodKey}-portfolio-commercial`, rowType: 'fixed', label: '按组合计提-商业承兑汇票', isFixed: true, balance: 0, ratio: 0, provision: 0, lossRate: 0, bookValue: 0 },
    ]
    const loaded = loadRows<BadDebtClassRow>(`class-${periodKey}-rows`)
    return ref(loaded.length ? loaded : [...defaults])
  }

  /** 录入态（持久化对象）—— 只有 balance / provision 有意义 */
  const classEndRowsRaw = buildClassRowsRaw('end')
  const classPriorRowsRaw = buildClassRowsRaw('prior')

  function totalOf(rows: readonly BadDebtClassRow[]): BadDebtClassRow {
    const totalBalance = calcSubtotal(rows.map(r => r.balance))
    const totalProvision = calcSubtotal(rows.map(r => r.provision))
    return {
      rowId: '__class_total__', rowType: 'summary' as RowType, label: '合计', isFixed: true,
      balance: totalBalance, ratio: totalBalance ? 1 : 0, provision: totalProvision,
      lossRate: safeDivide(totalProvision, totalBalance), bookValue: calcNetValue(totalBalance, totalProvision),
    }
  }

  const classEndTotal = computed<BadDebtClassRow>(() => totalOf(classEndRowsRaw.value))
  const classPriorTotal = computed<BadDebtClassRow>(() => totalOf(classPriorRowsRaw.value))

  /** 对外暴露的分类行 —— 派生列按**当前**合计推导，恒自洽 */
  const classEndRows = computed<BadDebtClassRow[]>(
    () => deriveClassRows(classEndRowsRaw.value, classEndTotal.value.balance),
  )
  const classPriorRows = computed<BadDebtClassRow[]>(
    () => deriveClassRows(classPriorRowsRaw.value, classPriorTotal.value.balance),
  )

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
  /**
   * 按**项目账龄配置段**（枚举账龄：3年段 / 5年段 / 自定义）批量生成组合计提行。
   * 仅补齐缺失段（按名称去重，不覆盖已录入行与金额），返回新增行数。
   * 附注模板国企版组合分表行本就是账龄段（1年以内（含1年）/1至2年/…），故此处按段生成而非手打。
   */
  function fillPortfolioAgingBands(
    type: 'bank' | 'commercial',
    period: 'end' | 'prior',
    segmentLabels: readonly string[],
  ): number {
    const key = `${type === 'bank' ? 'bank' : 'commercial'}-portfolio-${period}-rows`
    const target = type === 'bank'
      ? (period === 'end' ? bankPortfolioEndRows : bankPortfolioPriorRows)
      : (period === 'end' ? commercialPortfolioEndRows : commercialPortfolioPriorRows)
    const existing = new Set(target.value.map(r => String(r.drawerTypeOrAging || '').trim()).filter(Boolean))
    const added: PortfolioDetailRow[] = []
    for (const label of segmentLabels) {
      const name = String(label || '').trim()
      if (!name || existing.has(name)) continue
      added.push({ rowId: genId('pf'), rowType: 'dynamic', drawerTypeOrAging: name, isFixed: false, balance: 0, provision: 0, lossRate: 0 })
      existing.add(name)
    }
    if (added.length === 0) return 0
    target.value = [...target.value, ...added]
    persistRows(key, target.value)
    return added.length
  }

  function removePortfolioRow(rowId: string, type: 'bank' | 'commercial', period: 'end' | 'prior'): void {
    const key = `${type === 'bank' ? 'bank' : 'commercial'}-portfolio-${period}-rows`
    const target = type === 'bank' ? (period === 'end' ? bankPortfolioEndRows : bankPortfolioPriorRows) : (period === 'end' ? commercialPortfolioEndRows : commercialPortfolioPriorRows)
    target.value = target.value.filter(r => r.rowId !== rowId)
    persistRows(key, target.value)
  }

  // ─── 上市组合计提：双期并列成对行 ────────────────────────────────────────
  // 源模板（R76~R89）上市组合计提项目是**一张表双期并列**，同步时
  // `mergePortfolio` 按 `drawerTypeOrAging` 名称把期末 / 上年末对齐。
  // 若两期名称不一致就会各自成为孤儿行，故新增 / 改名 / 按段生成一律**成对**操作。

  function _portfolioRef(type: 'bank' | 'commercial', period: 'end' | 'prior') {
    return type === 'bank'
      ? (period === 'end' ? bankPortfolioEndRows : bankPortfolioPriorRows)
      : (period === 'end' ? commercialPortfolioEndRows : commercialPortfolioPriorRows)
  }
  function _portfolioKey(type: 'bank' | 'commercial', period: 'end' | 'prior'): string {
    return `${type}-portfolio-${period}-rows`
  }

  /** 向期末 + 上年末各插一行同名行，返回是否新增（名称为空或两期均已存在则不加）。 */
  function addPortfolioPairRow(type: 'bank' | 'commercial', name: string): boolean {
    const trimmed = String(name || '').trim()
    if (!trimmed) return false
    let added = false
    for (const period of ['end', 'prior'] as const) {
      const target = _portfolioRef(type, period)
      if (target.value.some(r => String(r.drawerTypeOrAging || '').trim() === trimmed)) continue
      target.value = [...target.value, {
        rowId: genId('pf'), rowType: 'dynamic', drawerTypeOrAging: trimmed,
        isFixed: false, balance: 0, provision: 0, lossRate: 0,
      }]
      persistRows(_portfolioKey(type, period), target.value)
      added = true
    }
    return added
  }

  /** 同时改期末 + 上年末同名行的名称，保持两期对齐；返回改动行数。 */
  function renamePortfolioPair(type: 'bank' | 'commercial', oldName: string, nextName: string): number {
    const from = String(oldName ?? '').trim()
    const to = String(nextName ?? '').trim()
    if (!to || from === to) return 0
    let touched = 0
    for (const period of ['end', 'prior'] as const) {
      const target = _portfolioRef(type, period)
      let hit = false
      target.value = target.value.map(r => {
        if (String(r.drawerTypeOrAging || '').trim() !== from) return r
        hit = true
        touched += 1
        return { ...r, drawerTypeOrAging: to }
      })
      if (hit) persistRows(_portfolioKey(type, period), target.value)
    }
    return touched
  }

  /** 按账龄段成对补齐（期末 + 上年末），返回两期合计新增行数。 */
  function fillPortfolioAgingBandsPair(
    type: 'bank' | 'commercial',
    segmentLabels: readonly string[],
  ): number {
    return fillPortfolioAgingBands(type, 'end', segmentLabels)
      + fillPortfolioAgingBands(type, 'prior', segmentLabels)
  }

  /** 删除某组合项目在两期的同名行，返回删除行数。 */
  function removePortfolioPairRow(type: 'bank' | 'commercial', name: string): number {
    const target0 = String(name ?? '').trim()
    let removed = 0
    for (const period of ['end', 'prior'] as const) {
      const target = _portfolioRef(type, period)
      const before = target.value.length
      target.value = target.value.filter(r => String(r.drawerTypeOrAging || '').trim() !== target0)
      if (target.value.length !== before) {
        removed += before - target.value.length
        persistRows(_portfolioKey(type, period), target.value)
      }
    }
    return removed
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

  // ─── 变动表「其中：」明细行（国企，预设 F4-20）────────────────────────────
  // 源模板 A50「其中：」下方是可添加的组合明细行；F4-20 要求「其中：」下方所有明细行之和
  // = 按组合计提行。旧实现只渲染一个固定 hint 行、无法新增 → 该勾稽永远无法满足。
  const movementDetailRows = ref<BadDebtMovementRow[]>(
    loadRows<BadDebtMovementRow>('movement-detail-rows'),
  )

  /** 「其中：」下明细汇总（供按组合计提行在有明细时改为只读汇总）。 */
  const movementDetailTotal = computed<BadDebtMovementRow>(() => {
    const rows = movementDetailRows.value
    const sum = (k: keyof BadDebtMovementRow) =>
      calcSubtotal(rows.map(r => parseNum(r[k] as number)))
    return {
      rowId: '__mv_detail_total__', rowType: 'summary', label: '其中小计', isFixed: true,
      priorBalance: sum('priorBalance'), provision: sum('provision'), reversal: sum('reversal'),
      writeOff: sum('writeOff'), transfer: sum('transfer'), other: sum('other'),
      endBalance: sum('endBalance'),
    }
  })
  const hasMovementDetail = computed(() => movementDetailRows.value.length > 0)

  /** 新增「其中：」明细行（名称由调用方先 prompt 取得，空名不创建）。 */
  function addMovementDetailRow(label: string): boolean {
    const name = String(label ?? '').trim()
    if (!name || isReadonly.value) return false
    movementDetailRows.value = [...movementDetailRows.value, {
      rowId: genId('mvd'), rowType: 'dynamic', label: name, isFixed: false,
      priorBalance: 0, provision: 0, reversal: 0, writeOff: 0, transfer: 0, other: 0, endBalance: 0,
    }]
    persistRows('movement-detail-rows', movementDetailRows.value)
    return true
  }

  function removeMovementDetailRow(rowId: string): void {
    movementDetailRows.value = movementDetailRows.value.filter(r => r.rowId !== rowId)
    persistRows('movement-detail-rows', movementDetailRows.value)
  }

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
  /**
   * 加载转回明细并迁移 legacy 数据：国企「转回或收回前累计已计提坏账准备金额」
   * 原先误绑在文本字段 `reversalBasis` 上。若 `cumulativeProvision` 缺失而
   * `reversalBasis` 可解析为数值，则搬到数值字段并清空文本字段（否则同一值会重复显示）。
   */
  function loadReversalRows(): ReversalDetailRow[] {
    return loadRows<Partial<ReversalDetailRow>>('reversal-rows').map((r) => {
      const legacyNum = r.cumulativeProvision === undefined ? parseNum(r.reversalBasis) : 0
      const migrate = r.cumulativeProvision === undefined && legacyNum !== 0
      return {
        rowId: String(r.rowId ?? genId('rv')),
        rowType: (r.rowType ?? 'dynamic') as RowType,
        isFixed: Boolean(r.isFixed),
        companyName: String(r.companyName ?? ''),
        reversalReason: String(r.reversalReason ?? ''),
        originalMethod: String(r.originalMethod ?? ''),
        reversalBasis: migrate ? '' : String(r.reversalBasis ?? ''),
        amount: parseNum(r.amount),
        cumulativeProvision: migrate ? legacyNum : parseNum(r.cumulativeProvision),
      }
    })
  }
  const reversalDetailRows = ref<ReversalDetailRow[]>(loadReversalRows())
  const reversalDetailTotal = computed<ReversalDetailRow>(() => ({
    rowId: '__rev_total__', rowType: 'summary', isFixed: true, companyName: '合计', reversalReason: '', originalMethod: '', reversalBasis: '',
    amount: calcSubtotal(reversalDetailRows.value.map(r => r.amount)),
    cumulativeProvision: calcSubtotal(reversalDetailRows.value.map(r => r.cumulativeProvision)),
  }))
  function addReversalRow(): void {
    reversalDetailRows.value.push({ rowId: genId('rv'), rowType: 'dynamic', isFixed: false, companyName: '', reversalReason: '', originalMethod: '', reversalBasis: '', amount: 0, cumulativeProvision: 0 })
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

  /**
   * 主表（分类总表）行。优先走审定表 D1-1 跨表取数；取不到时回落到
   * **手工录入 / 导入的 `top-summary-rows`**。
   *
   * 🔴 回退分支原先写死 `variant === 'soe'` → 上市侧在审定表未加载时主表恒 0
   * （浏览器实测全为 `-`），且导入模板里的 topSummary 对上市**导了也不生效**。
   * 两个变体的主表语义完全相同（票据种类 × 双期 × 账面余额/坏账准备/账面价值），
   * 没有理由只让国企有兜底。
   */
  const categorySummaryRows = computed<CategorySummaryRow[]>(() => {
    const d = crossSheetData.value
    const hasCross = Boolean(d.bankEndBalance || d.bankPriorBalance || d.bankEndProvision || d.bankPriorProvision || d.commercialEndBalance || d.commercialPriorBalance || d.commercialEndProvision || d.commercialPriorProvision)
    if (!hasCross && importedTopSummaryRows.value.length > 0) {
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

  /**
   * 主表是否可手工录入 —— 审定表 D1-1 未取到数时开放（否则以审定表为准，只读）。
   * 两个变体一致：主表是附注交付的第一张表，不能因上游未导数就永远是 0 且无法补录。
   */
  const canEditCategorySummary = computed(() => crossSheetStatus.value === 'empty')

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
      // 只写录入列；派生列由 classEndRows computed 按新合计重新推导
      classEndRowsRaw.value = classEndRowsRaw.value.map(r => r.rowId === rowId ? { ...r, [field]: numVal } : r)
      persistRows('class-end-rows', classEndRowsRaw.value)
    } else if (section === 'classPrior') {
      classPriorRowsRaw.value = classPriorRowsRaw.value.map(r => r.rowId === rowId ? { ...r, [field]: numVal } : r)
      persistRows('class-prior-rows', classPriorRowsRaw.value)
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
    } else if (section === 'movementDetail') {
      movementDetailRows.value = movementDetailRows.value.map(r => {
        if (r.rowId !== rowId) return r
        const updated = { ...r, [field]: field === 'label' ? String(value) : numVal }
        updated.endBalance = calcBadDebtEndBalance(updated.priorBalance, updated.provision, updated.reversal, updated.writeOff, updated.transfer, updated.other)
        return updated
      })
      persistRows('movement-detail-rows', movementDetailRows.value)
    } else if (section === 'reversalDetail') {
      const isNumField = field === 'amount' || field === 'cumulativeProvision'
      reversalDetailRows.value = reversalDetailRows.value.map(r => r.rowId === rowId ? { ...r, [field]: isNumField ? numVal : value } : r)
      persistRows('reversal-rows', reversalDetailRows.value)
    } else if (section === 'writeOffDetail') {
      writeOffDetailRows.value = writeOffDetailRows.value.map(r => r.rowId === rowId ? { ...r, [field]: field === 'amount' ? numVal : value } : r)
      persistRows('writeoff-rows', writeOffDetailRows.value)
    } else if (section === 'categorySummary') {
      // 手工兜底：审定表 D1-1 未取到数时允许直接录主表，写入 `top-summary-rows`
      // （与导入路径同一个持久化键，两者互为覆盖，不新建第二真源）。
      if (!canEditCategorySummary.value) return
      const base = importedTopSummaryRows.value.length > 0
        ? importedTopSummaryRows.value
        : categorySummaryRows.value.map(r => ({ ...r }))
      const next = base.map((r: any) => {
        if (String(r.rowId) !== rowId) return r
        const updated: any = { ...r, [field]: numVal }
        updated.endBookValue = calcNetValue(parseNum(updated.endBalance), parseNum(updated.endProvision))
        updated.priorBookValue = calcNetValue(parseNum(updated.priorBalance), parseNum(updated.priorProvision))
        return updated
      })
      importedTopSummaryRows.value = next
      persistRows('top-summary-rows', next)
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
    addPortfolioRow, removePortfolioRow, fillPortfolioAgingBands,
    // 上市双期并列成对操作
    addPortfolioPairRow, renamePortfolioPair, fillPortfolioAgingBandsPair, removePortfolioPairRow,
    // Movement
    movementRows, movementTotal, reversalDetailRows, reversalDetailTotal, addReversalRow, removeReversalRow,
    // 变动表「其中：」明细（国企 F4-20）
    movementDetailRows, movementDetailTotal, hasMovementDetail,
    addMovementDetailRow, removeMovementDetailRow,
    // Write-off
    writeOffAmount, writeOffDetailRows, writeOffDetailTotal, addWriteOffRow, removeWriteOffRow,
    // Category summary（主表，两个变体共用；审定表未取数时可手工兜底）
    categorySummaryRows, categorySummaryTotal, canEditCategorySummary,
    // Generic
    updateCell,
  }
}
