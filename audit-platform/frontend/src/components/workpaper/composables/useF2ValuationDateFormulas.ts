/**
 * F2-39 多产品 × 按日期计价测试（对齐致同源模板）
 *
 * 与 F2-38 月度表不同：首列为「日期」，年初数 + 逐笔发生 + 合计。
 * 计价方法：先进先出法 / 移动加权平均法（逐行滚动重算）。
 * 差异 M = K − F（应结转金额 − 账面发出金额）。
 */
import { calcSubtotal } from './useF2InvValFormulaEngine'

export type DateCostingMode = 'fifo' | 'moving-wa'

/** FIFO 成本层 */
export interface FifoLayer {
  qty: number
  unitPrice: number
}

export interface ValuationDateLine {
  id: string
  /** opening | txn */
  kind: 'opening' | 'txn'
  /** 日期文本：年初数 / YYYY-MM-DD / 自定义 */
  dateLabel: string
  prodQty: number
  prodPrice: number
  prodAmt: number
  saleQty: number
  salePrice: number
  saleAmt: number
  endQty: number
  endPrice: number
  endAmt: number
  shouldPrice: number
  shouldAmt: number
  remainder: number
  variance: number
}

export interface ValuationDateProject {
  id: string
  seq: number
  itemName: string
  remark: string
  lines: ValuationDateLine[]
}

export function newDateLineId(): string {
  return `f2vd-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function newProjectId(): string {
  return `f2vp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyTxnLine(dateLabel = ''): ValuationDateLine {
  return {
    id: newDateLineId(),
    kind: 'txn',
    dateLabel,
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

export function emptyOpeningLine(): ValuationDateLine {
  return {
    id: newDateLineId(),
    kind: 'opening',
    dateLabel: '年初数',
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

/** 源模板每个测试项目约 12 笔空白发生行 */
const DEFAULT_TXN_ROW_COUNT = 12

export function emptyDateProject(seq: number, itemName = ''): ValuationDateProject {
  return {
    id: newProjectId(),
    seq,
    itemName,
    remark: '',
    lines: [
      emptyOpeningLine(),
      ...Array.from({ length: DEFAULT_TXN_ROW_COUNT }, () => emptyTxnLine()),
    ],
  }
}

/** F2-39 源模板列示 3 个测试项目 */
export function defaultThreeDateProjects(): ValuationDateProject[] {
  return [1, 2, 3].map((n) => emptyDateProject(n, ''))
}

function n(v: number): number {
  return Number.isFinite(v) ? v : 0
}

function cloneLayers(layers: FifoLayer[]): FifoLayer[] {
  return layers.map((l) => ({ ...l }))
}

/** 购入增加 FIFO 层（同价合并到队尾，保持批次清晰） */
export function addFifoLayers(layers: FifoLayer[], qty: number, unitPrice: number): FifoLayer[] {
  const q = n(qty)
  if (q <= 0) return layers
  const p = n(unitPrice)
  const next = cloneLayers(layers)
  const last = next[next.length - 1]
  if (last && Math.abs(last.unitPrice - p) < 1e-9) {
    last.qty += q
  } else {
    next.push({ qty: q, unitPrice: p })
  }
  return next
}

/** 从队首逐层消耗，返回发出成本与剩余层 */
export function consumeFifoLayers(
  layers: FifoLayer[],
  saleQty: number,
): { cost: number; remaining: FifoLayer[] } {
  let need = n(saleQty)
  if (need <= 0) return { cost: 0, remaining: cloneLayers(layers) }
  const next = cloneLayers(layers)
  let cost = 0
  while (need > 0 && next.length > 0) {
    const head = next[0]
    const take = Math.min(need, head.qty)
    cost += take * head.unitPrice
    head.qty -= take
    need -= take
    if (head.qty <= 1e-9) next.shift()
  }
  return { cost, remaining: next }
}

export function layersToTotals(layers: FifoLayer[]): { qty: number; amt: number } {
  return layers.reduce(
    (acc, l) => ({ qty: acc.qty + l.qty, amt: acc.amt + l.qty * l.unitPrice }),
    { qty: 0, amt: 0 },
  )
}

export function layersFromOpening(qty: number, amt: number): FifoLayer[] {
  const q = n(qty)
  if (q <= 0) return []
  const price = n(amt) / q
  return [{ qty: q, unitPrice: price }]
}

/** 移动加权平均：先入库再加权，再按均价结转发出 */
export function calcMovingWaIssue(
  startQty: number,
  startAmt: number,
  prodQty: number,
  prodAmt: number,
  saleQty: number,
): { shouldPrice: number; shouldAmt: number; endQty: number; endAmt: number } {
  const totalQty = n(startQty) + n(prodQty)
  const totalAmt = n(startAmt) + n(prodAmt)
  const sq = n(saleQty)
  if (sq <= 0) {
    return { shouldPrice: 0, shouldAmt: 0, endQty: totalQty, endAmt: totalAmt }
  }
  const waPrice = totalQty > 0 ? totalAmt / totalQty : 0
  const shouldAmt = sq * waPrice
  return {
    shouldPrice: waPrice,
    shouldAmt,
    endQty: totalQty - sq,
    endAmt: totalAmt - shouldAmt,
  }
}

/**
 * 按日期逐行 enrich（链式：上行期末层/余额 = 下行期初）
 */
export function enrichDateProjectLines(
  project: ValuationDateProject,
  mode: DateCostingMode,
): ValuationDateLine[] {
  const out: ValuationDateLine[] = []
  let fifoLayers: FifoLayer[] = []
  let rollQty = 0
  let rollAmt = 0

  for (const raw of project.lines) {
    const line = { ...raw }
    if (!line.prodAmt && line.prodQty && line.prodPrice) {
      line.prodAmt = line.prodQty * line.prodPrice
    }
    if (!line.saleAmt && line.saleQty && line.salePrice) {
      line.saleAmt = line.saleQty * line.salePrice
    }

    if (line.kind === 'opening') {
      const qty = n(line.prodQty)
      const amt = n(line.prodAmt) || (qty && line.prodPrice ? qty * line.prodPrice : 0)
      line.prodAmt = amt
      line.endQty = qty
      line.endAmt = amt
      line.endPrice = qty ? amt / qty : 0
      line.shouldPrice = 0
      line.shouldAmt = 0
      line.remainder = 0
      line.variance = 0
      fifoLayers = layersFromOpening(qty, amt)
      rollQty = qty
      rollAmt = amt
      out.push(line)
      continue
    }

    const startQty = rollQty
    const startAmt = rollAmt
    const prodQty = n(line.prodQty)
    const prodAmt = n(line.prodAmt)
    const prodPrice = prodQty > 0 ? prodAmt / prodQty : n(line.prodPrice)
    const saleQty = n(line.saleQty)
    const saleAmt = n(line.saleAmt)

    let shouldPrice = 0
    let shouldAmt = 0
    let endQty = 0
    let endAmt = 0

    if (mode === 'fifo') {
      let layers = cloneLayers(fifoLayers)
      if (prodQty > 0) layers = addFifoLayers(layers, prodQty, prodPrice)
      if (saleQty > 0) {
        const consumed = consumeFifoLayers(layers, saleQty)
        shouldAmt = consumed.cost
        shouldPrice = saleQty > 0 ? shouldAmt / saleQty : 0
        layers = consumed.remaining
      }
      const totals = layersToTotals(layers)
      endQty = totals.qty
      endAmt = totals.amt
      fifoLayers = layers
      rollQty = endQty
      rollAmt = endAmt
    } else {
      const wa = calcMovingWaIssue(startQty, startAmt, prodQty, prodAmt, saleQty)
      shouldPrice = wa.shouldPrice
      shouldAmt = wa.shouldAmt
      endQty = wa.endQty
      endAmt = wa.endAmt
      rollQty = endQty
      rollAmt = endAmt
      fifoLayers = layersFromOpening(endQty, endAmt)
    }

    const endPrice = endQty !== 0 ? endAmt / endQty : 0
    const remainder = startAmt + prodAmt - saleAmt
    const variance = shouldAmt - saleAmt

    line.shouldPrice = shouldPrice
    line.shouldAmt = shouldAmt
    line.endQty = endQty
    line.endAmt = endAmt
    line.endPrice = endPrice
    line.remainder = remainder
    line.variance = variance
    out.push(line)
  }
  return out
}

export function enrichDateProject(
  project: ValuationDateProject,
  mode: DateCostingMode,
): ValuationDateProject {
  return { ...project, lines: enrichDateProjectLines(project, mode) }
}

export interface DateProjectTotals {
  prodQty: number
  prodAmt: number
  saleQty: number
  saleAmt: number
  shouldAmt: number
  variance: number
}

export function calcDateProjectTotals(lines: ValuationDateLine[]): DateProjectTotals {
  const body = lines.filter((l) => l.kind !== 'opening')
  return {
    prodQty: calcSubtotal(body.map((l) => l.prodQty)),
    prodAmt: calcSubtotal(body.map((l) => l.prodAmt)),
    saleQty: calcSubtotal(body.map((l) => l.saleQty)),
    saleAmt: calcSubtotal(body.map((l) => l.saleAmt)),
    shouldAmt: calcSubtotal(body.map((l) => l.shouldAmt)),
    variance: calcSubtotal(body.map((l) => l.variance)),
  }
}

export function calcDateBundleVariance(projects: ValuationDateProject[]): number {
  return calcSubtotal(
    projects.flatMap((p) => p.lines.filter((l) => l.kind !== 'opening').map((l) => l.variance)),
  )
}

/** 底部「提示」— 源 F2-39 模板 */
export const F2_39_TIPS = [
  '存货在取得时按实际成本计价，存货成本包括采购成本、加工成本和其他成本。',
  '存货发出时按先进先出法或移动加权平均法计价，采用一次加权平均法的，月末计算加权平均单价；采用移动加权平均法的，每入库一次即重新计算加权平均单价。',
  '对于性质和用途相似的存货，应当采用相同的成本计算方法确定发出存货的成本。',
  '对于不能替代使用的存货、为特定项目专门购入或制造的存货，通常采用个别计价法确定发出存货的成本。',
  '存货成本结转时，已计提的存货跌价准备应当同时结转，计入当期损益。',
] as const

/** 迁移：旧月度结构 / 扁平行 → 日期结构 */
export function migrateToDateProjects(
  legacy: Array<Record<string, unknown>>,
): ValuationDateProject[] | null {
  if (!Array.isArray(legacy) || !legacy.length) return null

  const first = legacy[0] as Record<string, unknown>
  if (first && Array.isArray(first.lines)) {
    const projects = legacy as unknown as ValuationDateProject[]
    while (projects.length < 3) {
      projects.push(emptyDateProject(projects.length + 1))
    }
    return projects.slice(0, 12)
  }

  // 月度结构（误存为 F2-39）
  if (first && Array.isArray(first.months)) {
    return (legacy as Array<{ seq?: number; itemName?: string; remark?: string; months: Array<Record<string, unknown>> }>)
      .slice(0, 8)
      .map((p, i) => {
        const proj = emptyDateProject(i + 1, String(p.itemName || ''))
        proj.remark = String(p.remark || '')
        const opening = p.months.find((m) => m.key === 'opening')
        if (opening) {
          proj.lines[0].prodQty = Number(opening.prodQty || 0)
          proj.lines[0].prodAmt = Number(opening.prodAmt || 0)
          proj.lines[0].prodPrice = Number(opening.prodPrice || 0)
        }
        const txns = p.months.filter((m) => m.key && m.key !== 'opening')
        txns.forEach((m, ti) => {
          const line = proj.lines[ti + 1] || emptyTxnLine(String(m.label || ''))
          line.dateLabel = String(m.label || '')
          line.prodQty = Number(m.prodQty || 0)
          line.prodAmt = Number(m.prodAmt || 0)
          line.prodPrice = Number(m.prodPrice || 0)
          line.saleQty = Number(m.saleQty || 0)
          line.saleAmt = Number(m.saleAmt || 0)
          line.salePrice = Number(m.salePrice || 0)
          if (ti + 1 >= proj.lines.length) proj.lines.push(line)
          else proj.lines[ti + 1] = line
        })
        return proj
      })
      .concat(
        Array.from({ length: Math.max(0, 3 - legacy.length) }, (_, i) =>
          emptyDateProject(legacy.length + i + 1),
        ),
      )
      .slice(0, 12)
  }

  // 旧扁平行
  const projects = legacy.slice(0, 8).map((r, i) => {
    const p = emptyDateProject(i + 1, String(r.itemName || ''))
    p.lines[0].prodQty = Number(r.openingQty || 0)
    p.lines[0].prodAmt = Number(r.openingAmt || 0)
    if (p.lines[0].prodQty) p.lines[0].prodPrice = p.lines[0].prodAmt / p.lines[0].prodQty
    const txn = p.lines[1]
    txn.prodQty = Number(r.inboundQty || 0)
    txn.prodAmt = Number(r.inboundAmt || 0)
    txn.saleQty = Number(r.issueQty || 0)
    txn.saleAmt = Number(r.bookIssueAmt || 0)
    return p
  })
  while (projects.length < 3) projects.push(emptyDateProject(projects.length + 1))
  return projects
}
