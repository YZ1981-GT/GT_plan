/**
 * F2-38 多产品 × 月度计价测试公式（月末一次加权平均）
 */
import { calcSubtotal } from './useF2InvValFormulaEngine'

export type ValuationMonthlyMethod = 'weighted-avg' | 'fifo' | 'standard-cost'

export const VALUATION_MONTH_DEFS = [
  { key: 'opening', label: '年初数' },
  { key: '01', label: '1月' },
  { key: '02', label: '2月' },
  { key: '03', label: '3月' },
  { key: '04', label: '4月' },
  { key: '05', label: '5月' },
  { key: '06', label: '6月' },
  { key: '07', label: '7月' },
  { key: '08', label: '8月' },
  { key: '09', label: '9月' },
  { key: '10', label: '10月' },
  { key: '11', label: '11月' },
  { key: '12', label: '12月' },
] as const

export type ValuationMonthKey = (typeof VALUATION_MONTH_DEFS)[number]['key']

/** 单月行（输入 + 自动计算列） */
export interface ValuationMonthLine {
  key: ValuationMonthKey
  label: string
  /** 本期生产/购入 A B C */
  prodQty: number
  prodPrice: number
  prodAmt: number
  /** 本期销售/发出 D E F（F 账面） */
  saleQty: number
  salePrice: number
  saleAmt: number
  /** 期末结存 */
  endQty: number
  endPrice: number
  endAmt: number
  /** 应结转 J K */
  shouldPrice: number
  shouldAmt: number
  /** 结余 L */
  remainder: number
  /** 差异 M = K − F */
  variance: number
}

export interface ValuationProductProject {
  id: string
  seq: number
  /** 品名 */
  itemName: string
  /** 标准成本法：标准单价 */
  stdPrice: number
  /** 备注（进口/运费/返利等关注点） */
  remark: string
  months: ValuationMonthLine[]
}

export function newProjectId(): string {
  return `f2vp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyMonthLine(key: ValuationMonthKey, label: string): ValuationMonthLine {
  return {
    key,
    label,
    prodQty: 0,
    prodPrice: 0,
    prodAmt: 0,
    saleQty: 0,
    salePrice: 0,
    saleAmt: 0,
    endQty: 0,
    endPrice: 0,
    endAmt: 0,
    shouldPrice: 0,
    shouldAmt: 0,
    remainder: 0,
    variance: 0,
  }
}

export function emptyProductProject(seq: number, itemName = ''): ValuationProductProject {
  return {
    id: newProjectId(),
    seq,
    itemName,
    stdPrice: 0,
    remark: '',
    months: VALUATION_MONTH_DEFS.map((m) => emptyMonthLine(m.key, m.label)),
  }
}

/** 默认 4 个测试项目（源模板列示规模） */
export function defaultFourProjects(): ValuationProductProject[] {
  return [1, 2, 3, 4].map((n) => emptyProductProject(n, ''))
}

function n(v: number): number {
  return Number.isFinite(v) ? v : 0
}

/** 先进先出月内简化：先耗期初层，再耗本期购入层 */
export function calcFifoIssueAmt(
  startQty: number,
  startAmt: number,
  prodQty: number,
  prodAmt: number,
  saleQty: number,
): { shouldPrice: number; shouldAmt: number } {
  const sq = n(saleQty)
  if (sq <= 0) return { shouldPrice: 0, shouldAmt: 0 }
  const openP = n(startQty) > 0 ? n(startAmt) / n(startQty) : 0
  const prodP = n(prodQty) > 0 ? n(prodAmt) / n(prodQty) : 0
  const fromOpen = Math.min(sq, Math.max(0, n(startQty)))
  const fromProd = Math.max(0, sq - fromOpen)
  const shouldAmt = fromOpen * openP + fromProd * prodP
  return { shouldPrice: shouldAmt / sq, shouldAmt }
}

/**
 * enrich 单个产品全年月份（链式：上月末 = 下月初）
 */
export function enrichProductMonths(
  project: ValuationProductProject,
  method: ValuationMonthlyMethod,
): ValuationMonthLine[] {
  const out: ValuationMonthLine[] = []
  let prevEndQty = 0
  let prevEndAmt = 0

  for (const raw of project.months) {
    const line = { ...raw }
    // 金额可由数量×单价回填（仅当金额为 0 且数量/单价有值）
    if (!line.prodAmt && line.prodQty && line.prodPrice) {
      line.prodAmt = line.prodQty * line.prodPrice
    }
    if (!line.saleAmt && line.saleQty && line.salePrice) {
      line.saleAmt = line.saleQty * line.salePrice
    }

    if (line.key === 'opening') {
      // 年初数：A/B/C 记期初结存
      const qty = n(line.prodQty)
      const amt = n(line.prodAmt) || (qty && line.prodPrice ? qty * n(line.prodPrice) : 0)
      line.prodAmt = amt
      line.endQty = qty
      line.endAmt = amt
      line.endPrice = qty ? amt / qty : 0
      line.shouldPrice = 0
      line.shouldAmt = 0
      line.remainder = 0
      line.variance = 0
      prevEndQty = line.endQty
      prevEndAmt = line.endAmt
      out.push(line)
      continue
    }

    const startQty = prevEndQty
    const startAmt = prevEndAmt
    const prodQty = n(line.prodQty)
    const prodAmt = n(line.prodAmt)
    const saleQty = n(line.saleQty)
    const saleAmt = n(line.saleAmt)

    let shouldPrice = 0
    let shouldAmt = 0

    if (method === 'weighted-avg') {
      const den = startQty + prodQty
      shouldPrice = den > 0 ? (startAmt + prodAmt) / den : 0
      shouldAmt = saleQty * shouldPrice
    } else if (method === 'fifo') {
      const fifo = calcFifoIssueAmt(startQty, startAmt, prodQty, prodAmt, saleQty)
      shouldPrice = fifo.shouldPrice
      shouldAmt = fifo.shouldAmt
    } else {
      shouldPrice = n(project.stdPrice)
      shouldAmt = saleQty * shouldPrice
    }

    const endQty = startQty + prodQty - saleQty
    // 审计推算期末（按应结转 K 倒轧）
    const endAmt = startAmt + prodAmt - shouldAmt
    const endPrice = endQty !== 0 ? endAmt / endQty : 0
    // 结余 L：账面推算期末 = 期初 + 购入 − 账面发出 F（与审计期末之差即 M）
    const remainder = startAmt + prodAmt - saleAmt
    const variance = shouldAmt - saleAmt

    line.shouldPrice = shouldPrice
    line.shouldAmt = shouldAmt
    line.endQty = endQty
    line.endAmt = endAmt
    line.endPrice = endPrice
    line.remainder = remainder
    line.variance = variance

    // 下月初沿用审计倒轧期末（计价测试重算链）
    prevEndQty = endQty
    prevEndAmt = endAmt
    out.push(line)
  }
  return out
}

export function enrichProductProject(
  project: ValuationProductProject,
  method: ValuationMonthlyMethod,
): ValuationProductProject {
  return {
    ...project,
    months: enrichProductMonths(project, method),
  }
}

export interface ProductMonthTotals {
  prodQty: number
  prodAmt: number
  saleQty: number
  saleAmt: number
  shouldAmt: number
  variance: number
}

export function calcProductTotals(months: ValuationMonthLine[]): ProductMonthTotals {
  const body = months.filter((m) => m.key !== 'opening')
  return {
    prodQty: calcSubtotal(body.map((m) => m.prodQty)),
    prodAmt: calcSubtotal(body.map((m) => m.prodAmt)),
    saleQty: calcSubtotal(body.map((m) => m.saleQty)),
    saleAmt: calcSubtotal(body.map((m) => m.saleAmt)),
    shouldAmt: calcSubtotal(body.map((m) => m.shouldAmt)),
    variance: calcSubtotal(body.map((m) => m.variance)),
  }
}

export function calcBundleVariance(projects: ValuationProductProject[]): number {
  return calcSubtotal(
    projects.flatMap((p) => p.months.filter((m) => m.key !== 'opening').map((m) => m.variance)),
  )
}

/** 迁移旧扁平样本行 → 产品项目（尽力） */
export function migrateLegacyValuationRows(
  legacy: Array<Record<string, unknown>>,
): ValuationProductProject[] | null {
  if (!Array.isArray(legacy) || !legacy.length) return null
  // 已是新产品结构
  if (legacy[0] && Array.isArray((legacy[0] as ValuationProductProject).months)) {
    return legacy as unknown as ValuationProductProject[]
  }
  // 旧 ValuationTestRow：每行一个品名 → 压到年初 + 合计近似放 12 月
  const projects = legacy.slice(0, 8).map((r, i) => {
    const p = emptyProductProject(i + 1, String(r.itemName || ''))
    const opening = p.months[0]
    opening.prodQty = Number(r.openingQty || 0) || 0
    opening.prodAmt = Number(r.openingAmt || 0) || 0
    opening.prodPrice = opening.prodQty ? opening.prodAmt / opening.prodQty : 0
    const dec = p.months[12] // 12月承载全年发生近似
    dec.prodQty = Number(r.inboundQty || 0) || 0
    dec.prodAmt = Number(r.inboundAmt || 0) || 0
    dec.saleQty = Number(r.issueQty || 0) || 0
    dec.saleAmt = Number(r.bookIssueAmt || 0) || 0
    if (r.fifoUnitPrice) {
      /* keep on project via std for fifo hint - store in remark */
    }
    if (r.stdPrice) p.stdPrice = Number(r.stdPrice) || 0
    return p
  })
  while (projects.length < 4) {
    projects.push(emptyProductProject(projects.length + 1))
  }
  return projects
}

export const VALUATION_PREP_NOTES = [
  '企业应当采用先进先出法、加权平均法或者个别计价法确定发出存货的实际成本。',
  '对于性质和用途相似的存货，应当采用相同的成本计算方法确定发出存货的成本。',
  '对于不能替代使用的存货、为特定项目专门购入或制造的存货以及提供劳务的成本，通常采用个别计价法确定发出存货的成本。',
  '对进口原材料、进口库存商品应测试初始入账时的外币折算及相应的关税的会计处理。',
  '关注前期减值项目的账面价值、运费、相关税费、返利和重大采购折扣（数量折扣除外）是否进行了调整。',
] as const
