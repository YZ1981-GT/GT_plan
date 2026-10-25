/**
 * 合并工作底稿 → 草稿分录的来源分组（spec consol-elimination-single-source-push 任务 10.2 / 需求 2）。
 *
 * - 模拟权益法：期初模拟 / 当期模拟 / 还原分红三步，每家子企业每步一组；
 * - 内部往来：每对往来科目一组（抵销往来）+ 坏账冲回各一组；
 * - 内部交易：收入成本抵销一组 + 未实现利润一组。
 * 来源键在来源内确定且稳定：同一来源数据重复生成更新同一笔草稿（后端按来源键幂等）。
 * 科目只给名称（+ 明细），编码由后端映射；映射不到的在预览里标红说明，不以名称入账（需求 2.3）。
 * 内部现金流没有会计科目（属现金流量表工作底稿），不生成分录。
 *
 * 金额一律 Decimal，不做浮点算术；说明文字不含展示格式的金额（否则切换金额单位会被当成来源变化）。
 */
import Decimal from 'decimal.js'
import type {
  EliminationType,
  WorksheetOrigin,
  WorksheetSourceGroup,
  WorksheetSourceLine,
} from '@/services/consolidationApi'

/** 本表负责的来源：其中本次没有产出的来源键 ⇒ 后端软删其草稿（需求 2.5） */
export const WORKSHEET_ORIGINS: ReadonlyArray<WorksheetOrigin> = ['ws_equity_sim', 'ws_internal_arap', 'ws_internal_trade']

const ZERO = new Decimal(0)

/** 金额文本 / 数字 → Decimal；空、非数 ⇒ 0（与工作底稿「空即 0」一致） */
export function toDecimal(value: unknown): Decimal {
  if (value === null || value === undefined || value === '') return ZERO
  try {
    const d = new Decimal(typeof value === 'string' ? value.replace(/[,，\s]/g, '') : (value as number))
    return d.isFinite() ? d : ZERO
  } catch {
    return ZERO
  }
}

function sumOf(values: ReadonlyArray<unknown> | null | undefined): Decimal {
  return (values || []).reduce<Decimal>((s, v) => s.plus(toDecimal(v)), ZERO)
}

/** 到分为 0 ⇒ 不是一行分录（后端同样跳过零金额行） */
function isZeroCents(d: Decimal): boolean {
  return d.toDecimalPlaces(2).isZero()
}

function text(value: unknown): string {
  return String(value ?? '').trim()
}

function uniqueCodes(codes: ReadonlyArray<string | null | undefined>): string[] {
  return [...new Set(codes.map((c) => text(c)).filter(Boolean))].sort()
}

// ─── 企业名称 → 企业代码（交易方留痕与归属预填用）──────────────────────────────

export interface SourceCompany { name: string; code?: string | null }

/** 工作底稿里企业按名称选（「母公司」= 本合并项目的企业）；认不出的名称 ⇒ null（不猜） */
export function companyCodeResolver(
  companies: ReadonlyArray<SourceCompany>, rootCode?: string | null,
): (name: string | null | undefined) => string | null {
  const byName = new Map<string, string>()
  for (const c of companies) {
    const name = text(c.name)
    const code = text(c.code)
    if (name && code && !byName.has(name)) byName.set(name, code)
  }
  return (name) => {
    const n = text(name)
    if (!n) return null
    if (n === '母公司') return text(rootCode) || null
    return byName.get(n) || null
  }
}

// ─── 模拟权益法 ──────────────────────────────────────────────────────────────

export interface EquitySimRowLike {
  step?: string | null
  direction?: string | null
  subject?: string | null
  detail?: string | null
  values?: ReadonlyArray<number | string | null | undefined> | null
  isStep?: boolean
}

/** 生成分录的三步（第 4 步股比变动与期末小计不是分录） */
export const EQUITY_SIM_STEPS = [
  { n: 1, title: '期初长投模拟', label: '期初模拟' },
  { n: 2, title: '模拟当期长期股权投资', label: '当期模拟' },
  { n: 3, title: '还原分红影响', label: '还原分红' },
] as const

/** 企业在来源键里的标识：优先企业代码；没有代码（基本信息表未填）才用名称 */
function companyKey(c: SourceCompany): string {
  return text(c.code) || `名称:${text(c.name)}`
}

/**
 * 每家子企业每步一组：该步下各行在该企业列（与 `companies` 同序）的金额；全为 0 的企业不成组。
 * 交易方 = 本合并项目企业 + 该子企业（两方的最近公共祖先是合并节点 ⇒ 归属预填为合并差额）。
 */
export function equitySimGroups(
  rows: ReadonlyArray<EquitySimRowLike>,
  companies: ReadonlyArray<SourceCompany>,
  rootCode?: string | null,
): WorksheetSourceGroup[] {
  const groups: WorksheetSourceGroup[] = []
  for (const step of EQUITY_SIM_STEPS) {
    const start = rows.findIndex((r) => r.isStep && text(r.step) === step.title)
    if (start < 0) continue
    const body: EquitySimRowLike[] = []
    for (let j = start + 1; j < rows.length && !rows[j].isStep; j += 1) body.push(rows[j])
    companies.forEach((company, ci) => {
      if (!text(company.name) && !text(company.code)) return
      const lines: WorksheetSourceLine[] = []
      for (const r of body) {
        const amount = toDecimal(r.values?.[ci])
        if (isZeroCents(amount)) continue
        lines.push({
          subject: text(r.subject),
          detail: text(r.detail) || null,
          direction: text(r.direction),
          amount: amount.toString(),
        })
      }
      if (!lines.length) return
      groups.push({
        origin: 'ws_equity_sim',
        origin_key: `equity_sim:step${step.n}:${companyKey(company)}`,
        description: `模拟权益法·${step.label}：${text(company.name) || text(company.code)}`,
        lines,
        related_company_codes: uniqueCodes([rootCode, company.code]),
      })
    })
  }
  return groups
}

// ─── 内部往来 ────────────────────────────────────────────────────────────────

export interface ArApRowLike {
  localCompany?: string | null
  localSubject?: string | null
  localAmounts?: ReadonlyArray<number | string | null> | null
  localImpairments?: ReadonlyArray<number | string | null> | null
  remoteCompany?: string | null
  remoteSubject?: string | null
  remoteAmounts?: ReadonlyArray<number | string | null> | null
  remoteImpairments?: ReadonlyArray<number | string | null> | null
}

/** 一对往来科目（本方科目 | 对方科目）跨行汇总 */
export interface ArApPair {
  localSubject: string
  remoteSubject: string
  local: Decimal
  remote: Decimal
  localImp: Decimal
  remoteImp: Decimal
  /** 参与的企业名称（本方、对方） */
  companies: string[]
}

export function arapPairs(rows: ReadonlyArray<ArApRowLike>): ArApPair[] {
  const pairs = new Map<string, ArApPair>()
  for (const row of rows) {
    const ls = text(row.localSubject)
    const rs = text(row.remoteSubject)
    if (!ls && !rs) continue
    const key = `${ls}|${rs}`
    let p = pairs.get(key)
    if (!p) {
      p = { localSubject: ls, remoteSubject: rs, local: ZERO, remote: ZERO, localImp: ZERO, remoteImp: ZERO, companies: [] }
      pairs.set(key, p)
    }
    p.local = p.local.plus(sumOf(row.localAmounts))
    p.remote = p.remote.plus(sumOf(row.remoteAmounts))
    p.localImp = p.localImp.plus(sumOf(row.localImpairments))
    p.remoteImp = p.remoteImp.plus(sumOf(row.remoteImpairments))
    for (const name of [row.localCompany, row.remoteCompany]) {
      const n = text(name)
      if (n && !p.companies.includes(n)) p.companies.push(n)
    }
  }
  return [...pairs.values()]
}

const LIABILITY_RE = /应付|预收|合同负债/
const ASSET_RE = /应收|预付|合同资产/

/**
 * 往来抵销的借贷：借负债方（应付 / 预收）、贷资产方（应收 / 预付）——与本方 / 对方填在哪一边无关；
 * 两边认不出性质（或同一性质）时按表内顺序「借本方、贷对方」。
 */
export function arapSides(pair: Pick<ArApPair, 'localSubject' | 'remoteSubject'>): { debit: string; credit: string } {
  const local = pair.localSubject || pair.remoteSubject
  const remote = pair.remoteSubject || pair.localSubject
  const nature = (s: string) => (LIABILITY_RE.test(s) ? 'liability' : ASSET_RE.test(s) ? 'asset' : '')
  if (nature(local) === 'asset' && nature(remote) === 'liability') return { debit: remote, credit: local }
  return { debit: local, credit: remote }
}

/** 本方 − 对方（未抵销差异，只提示不生成分录） */
export function arapDifference(pair: ArApPair): Decimal {
  return pair.local.minus(pair.remote)
}

export function arapGroups(
  pairs: ReadonlyArray<ArApPair>, codeOf: (name: string) => string | null,
): WorksheetSourceGroup[] {
  const groups: WorksheetSourceGroup[] = []
  for (const p of pairs) {
    const pairKey = `${p.localSubject}|${p.remoteSubject}`
    const related = uniqueCodes(p.companies.map(codeOf))
    const amount = Decimal.min(p.local, p.remote)
    if (amount.gt(0) && !isZeroCents(amount)) {
      const { debit, credit } = arapSides(p)
      groups.push({
        origin: 'ws_internal_arap',
        origin_key: `internal_arap:pair:${pairKey}`,
        description: `内部往来抵销：${debit} ↔ ${credit}`,
        lines: [
          { subject: debit, detail: null, direction: '借', amount: amount.toString() },
          { subject: credit, detail: null, direction: '贷', amount: amount.toString() },
        ],
        related_company_codes: related,
      })
    }
    for (const [side, imp, subject] of [
      ['local', p.localImp, p.localSubject], ['remote', p.remoteImp, p.remoteSubject],
    ] as const) {
      if (!imp.gt(0) || isZeroCents(imp)) continue
      groups.push({
        origin: 'ws_internal_arap',
        origin_key: `internal_arap:bad_debt_${side}:${pairKey}`,
        description: `冲回${side === 'local' ? '本方' : '对方'}内部往来坏账准备（${subject || '未填科目'}）`,
        lines: [
          { subject: '坏账准备', detail: null, direction: '借', amount: imp.toString() },
          { subject: '信用减值损失', detail: null, direction: '贷', amount: imp.toString() },
        ],
        related_company_codes: related,
      })
    }
  }
  return groups
}

// ─── 内部交易 ────────────────────────────────────────────────────────────────

export interface TradeRowLike {
  sellerCompany?: string | null
  buyerCompany?: string | null
  sellerAmount?: number | string | null
  buyerAmount?: number | string | null
  unrealizedProfit?: number | string | null
  inventoryRatio?: number | string | null
}

export interface TradeTotals {
  revenue: Decimal
  cost: Decimal
  /** Σ 未实现利润 × 存货留存率% */
  unrealized: Decimal
  companies: string[]
}

/** 只计卖方、买方都填了的行（与内部交易表口径一致） */
export function tradeTotals(rows: ReadonlyArray<TradeRowLike>): TradeTotals {
  const totals: TradeTotals = { revenue: ZERO, cost: ZERO, unrealized: ZERO, companies: [] }
  for (const row of rows) {
    const seller = text(row.sellerCompany)
    const buyer = text(row.buyerCompany)
    if (!seller || !buyer) continue
    totals.revenue = totals.revenue.plus(toDecimal(row.sellerAmount))
    totals.cost = totals.cost.plus(toDecimal(row.buyerAmount))
    totals.unrealized = totals.unrealized.plus(
      toDecimal(row.unrealizedProfit).times(toDecimal(row.inventoryRatio)).dividedBy(100),
    )
    for (const n of [seller, buyer]) if (!totals.companies.includes(n)) totals.companies.push(n)
  }
  return totals
}

const UNREALIZED_TYPE: EliminationType = 'unrealized_profit'

export function tradeGroups(totals: TradeTotals, codeOf: (name: string) => string | null): WorksheetSourceGroup[] {
  const groups: WorksheetSourceGroup[] = []
  const related = uniqueCodes(totals.companies.map(codeOf))
  const amount = Decimal.min(totals.revenue, totals.cost)
  if (amount.gt(0) && !isZeroCents(amount)) {
    groups.push({
      origin: 'ws_internal_trade',
      origin_key: 'internal_trade:revenue',
      description: '内部交易收入与成本抵销',
      lines: [
        { subject: '营业收入', detail: null, direction: '借', amount: amount.toString() },
        { subject: '营业成本', detail: null, direction: '贷', amount: amount.toString() },
      ],
      related_company_codes: related,
    })
  }
  if (totals.unrealized.gt(0) && !isZeroCents(totals.unrealized)) {
    groups.push({
      origin: 'ws_internal_trade',
      origin_key: 'internal_trade:unrealized',
      description: '存货中未实现内部利润抵销',
      // 同一来源默认生成「内部交易抵销」；未实现利润须显式标明类型
      entry_type: UNREALIZED_TYPE,
      lines: [
        { subject: '营业成本', detail: null, direction: '借', amount: totals.unrealized.toString() },
        { subject: '存货', detail: null, direction: '贷', amount: totals.unrealized.toString() },
      ],
      related_company_codes: related,
    })
  }
  return groups
}

// ─── 汇总 ────────────────────────────────────────────────────────────────────

export interface WorksheetSources {
  equitySimRows: ReadonlyArray<EquitySimRowLike>
  arapRows: ReadonlyArray<ArApRowLike>
  tradeRows: ReadonlyArray<TradeRowLike>
  companies: ReadonlyArray<SourceCompany>
  rootCode?: string | null
}

/** 按来源分开的分组（声明负责的来源时要逐来源判断） */
export function sourceGroupsByOrigin(src: WorksheetSources): Record<WorksheetOrigin, WorksheetSourceGroup[]> {
  const codeOf = companyCodeResolver(src.companies, src.rootCode)
  return {
    ws_equity_sim: equitySimGroups(src.equitySimRows, src.companies, src.rootCode),
    ws_internal_arap: arapGroups(arapPairs(src.arapRows), codeOf),
    ws_internal_trade: tradeGroups(tradeTotals(src.tradeRows), codeOf),
  }
}

/** 三张表的全部来源分组（顺序：模拟权益法 → 内部往来 → 内部交易） */
export function buildSourceGroups(src: WorksheetSources): WorksheetSourceGroup[] {
  const byOrigin = sourceGroupsByOrigin(src)
  return WORKSHEET_ORIGINS.flatMap((o) => byOrigin[o])
}

/** 来源对应的工作底稿表（consol_worksheet_data 的 sheet_key） */
export const ORIGIN_SHEET_KEYS: Readonly<Record<WorksheetOrigin, string>> = {
  ws_equity_sim: 'equity_sim',
  ws_internal_arap: 'internal_arap',
  ws_internal_trade: 'internal_trade',
}

/**
 * 本次负责的来源：该表有已保存的数据，或本次算出了分组。
 * 两者都没有 ⇒ 该表数据未知（没保存过、本次也没填），不能当成「算出来是空的」去删它以前生成的草稿。
 */
export function declaredOrigins(
  byOrigin: Readonly<Record<WorksheetOrigin, ReadonlyArray<WorksheetSourceGroup>>>,
  savedSheetKeys: ReadonlySet<string>,
): WorksheetOrigin[] {
  return WORKSHEET_ORIGINS.filter((o) => savedSheetKeys.has(ORIGIN_SHEET_KEYS[o]) || byOrigin[o].length > 0)
}

// ─── 工作底稿内的「自动生成的抵消分录」预览（与生成接口同一分组）────────────────

export interface PreviewLine {
  direction: string
  subject: string
  amount: string
  desc: string
}

export function groupsPreviewLines(groups: ReadonlyArray<WorksheetSourceGroup>): PreviewLine[] {
  return groups.flatMap((g) => g.lines.map((l) => ({
    direction: l.direction,
    subject: l.detail ? `${l.subject}-${l.detail}` : l.subject,
    amount: String(l.amount ?? ''),
    desc: g.description || '',
  })))
}

/** 本方与对方金额不等：只提示差异，不生成分录 */
export function arapDifferenceLines(pairs: ReadonlyArray<ArApPair>): PreviewLine[] {
  return pairs
    .filter((p) => !isZeroCents(arapDifference(p)))
    .map((p) => ({
      direction: '—',
      subject: '⚠️ 差异',
      amount: arapDifference(p).toString(),
      desc: `${p.localSubject || '（未填科目）'}↔${p.remoteSubject || '（未填科目）'} 未抵消差异（本方 − 对方）`,
    }))
}

/** 内部往来表的预览：每对科目依次列出往来抵销、坏账冲回与未抵销差异 */
export function arapPreviewLines(rows: ReadonlyArray<ArApRowLike>): PreviewLine[] {
  const noCode = () => null
  return arapPairs(rows).flatMap((p) => [
    ...groupsPreviewLines(arapGroups([p], noCode)),
    ...arapDifferenceLines([p]),
  ])
}

export function tradePreviewLines(rows: ReadonlyArray<TradeRowLike>): PreviewLine[] {
  return groupsPreviewLines(tradeGroups(tradeTotals(rows), () => null))
}

// ─── 已保存行的恢复（工作底稿表切走再切回、刷新页面后不丢数据）───────────────────

function numOrNull(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function amountList(value: unknown, len: number): (number | null)[] {
  const list = Array.isArray(value) ? value.map(numOrNull) : []
  while (list.length < len) list.push(null)
  return list
}

/** 已保存行里最长的账龄数组长度（恢复时据此选回账龄段预设；0 = 没有账龄数据） */
export function savedAgingLength(raw: unknown): number {
  if (!Array.isArray(raw)) return 0
  let len = 0
  for (const r of raw as any[]) {
    for (const k of ['localAmounts', 'localImpairments', 'remoteAmounts', 'remoteImpairments']) {
      if (Array.isArray(r?.[k])) len = Math.max(len, r[k].length)
    }
  }
  return len
}

/** 内部往来表已保存的行 → 表格行（缺字段补空、账龄数组至少 ``agingLen`` 段；无效行丢弃） */
export function restoreArApRows(raw: unknown, agingLen: number) {
  if (!Array.isArray(raw)) return []
  return raw.filter((r) => r && typeof r === 'object').map((r: any) => ({
    localCompany: text(r.localCompany),
    localSubject: text(r.localSubject),
    localDetail: text(r.localDetail),
    localAmounts: amountList(r.localAmounts, agingLen),
    localImpairments: amountList(r.localImpairments, agingLen),
    remoteCompany: text(r.remoteCompany),
    remoteSubject: text(r.remoteSubject),
    remoteDetail: text(r.remoteDetail),
    remoteAmounts: amountList(r.remoteAmounts, agingLen),
    remoteImpairments: amountList(r.remoteImpairments, agingLen),
    diffReason: text(r.diffReason),
  }))
}

/** 内部交易表已保存的行 → 表格行 */
export function restoreTradeRows(raw: unknown) {
  if (!Array.isArray(raw)) return []
  return raw.filter((r) => r && typeof r === 'object').map((r: any) => ({
    sellerCompany: text(r.sellerCompany),
    buyerCompany: text(r.buyerCompany),
    tradeType: text(r.tradeType),
    sellerSubject: text(r.sellerSubject),
    sellerAmount: numOrNull(r.sellerAmount),
    buyerSubject: text(r.buyerSubject),
    buyerAmount: numOrNull(r.buyerAmount),
    unrealizedProfit: numOrNull(r.unrealizedProfit),
    inventoryRatio: numOrNull(r.inventoryRatio),
  }))
}
