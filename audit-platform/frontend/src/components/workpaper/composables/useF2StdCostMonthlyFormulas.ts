/**
 * F2-40 标准成本差异测试 — 多产品 × 月度（对齐致同源模板）
 *
 * 列组：本期生产/购入、本期销售应结转、期末应结存、期末实际结存、差异
 * 滚动：应结存 = 上期应结存 + 本期生产 − 本期发出（数量/标准成本/差异分项）
 * 差异：实际结存标准成本 − 应结存标准成本
 */
import { calcSubtotal, calcStandardCost } from './useF2InvValFormulaEngine'

export const STD_COST_MONTH_DEFS = [
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

export type StdCostMonthKey = (typeof STD_COST_MONTH_DEFS)[number]['key']

export interface StdCostMonthLine {
  key: StdCostMonthKey
  label: string
  kind: 'opening' | 'month'
  /** 本期生产/购入 */
  prodQty: number
  stdUnitPrice: number
  prodStdCost: number
  prodStdVariance: number
  /** 本期销售/发出应结转 */
  saleQty: number
  saleStdCost: number
  saleStdVariance: number
  /** 期末应结存（审计推算） */
  expEndQty: number
  expEndStdCost: number
  expEndStdVariance: number
  /** 期末实际结存（账面） */
  actEndQty: number
  actEndStdCost: number
  actEndStdVariance: number
  /** 差异 */
  diffStdCost: number
}

export interface StdCostProductProject {
  id: string
  seq: number
  itemName: string
  remark: string
  months: StdCostMonthLine[]
}

export function newStdCostProjectId(): string {
  return `f2sc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyStdCostMonthLine(key: StdCostMonthKey, label: string): StdCostMonthLine {
  return {
    key,
    label,
    kind: key === 'opening' ? 'opening' : 'month',
    prodQty: 0,
    stdUnitPrice: 0,
    prodStdCost: 0,
    prodStdVariance: 0,
    saleQty: 0,
    saleStdCost: 0,
    saleStdVariance: 0,
    expEndQty: 0,
    expEndStdCost: 0,
    expEndStdVariance: 0,
    actEndQty: 0,
    actEndStdCost: 0,
    actEndStdVariance: 0,
    diffStdCost: 0,
  }
}

export function emptyStdCostProject(seq: number, itemName = ''): StdCostProductProject {
  return {
    id: newStdCostProjectId(),
    seq,
    itemName,
    remark: '',
    months: STD_COST_MONTH_DEFS.map((m) => emptyStdCostMonthLine(m.key, m.label)),
  }
}

/** F2-40 源模板列示 3 个测试项目 */
/** 默认 1 个测试项目；需要时由「+ 增行」添加 */
export function defaultThreeStdCostProjects(): StdCostProductProject[] {
  return [emptyStdCostProject(1, '')]
}

function n(v: number): number {
  return Number.isFinite(v) ? v : 0
}

/** 单行 enrich */
function enrichStdCostLine(
  raw: StdCostMonthLine,
  prevExp: { qty: number; stdCost: number; stdVariance: number },
  projectStdPrice: number,
): { line: StdCostMonthLine; nextExp: { qty: number; stdCost: number; stdVariance: number } } {
  const line = { ...raw }
  const stdPrice = n(line.stdUnitPrice) || n(projectStdPrice)

  if (line.kind === 'opening') {
    // 年初数：期初结存录入「期末实际结存」，应结存默认与之一致（可改）
    const actQty = n(line.actEndQty)
    const actCost = n(line.actEndStdCost)
    const actVar = n(line.actEndStdVariance)
    line.expEndQty = n(line.expEndQty) || actQty
    line.expEndStdCost = n(line.expEndStdCost) || actCost
    line.expEndStdVariance = n(line.expEndStdVariance) || actVar
    line.actEndQty = actQty
    line.actEndStdCost = actCost
    line.actEndStdVariance = actVar
    line.diffStdCost = line.actEndStdCost - line.expEndStdCost
    const nextExp = {
      qty: line.expEndQty,
      stdCost: line.expEndStdCost,
      stdVariance: line.expEndStdVariance,
    }
    return { line, nextExp }
  }

  // 生产标准成本 = 数量 × 标准单价（未手填时）
  if (!line.prodStdCost && line.prodQty && stdPrice) {
    line.prodStdCost = calcStandardCost(stdPrice, line.prodQty)
  }
  // 发出标准成本 = 数量 × 标准单价
  if (!line.saleStdCost && line.saleQty && stdPrice) {
    line.saleStdCost = calcStandardCost(stdPrice, line.saleQty)
  }

  const prodQty = n(line.prodQty)
  const prodCost = n(line.prodStdCost)
  const prodVar = n(line.prodStdVariance)
  const saleQty = n(line.saleQty)
  const saleCost = n(line.saleStdCost)
  const saleVar = n(line.saleStdVariance)

  line.expEndQty = prevExp.qty + prodQty - saleQty
  line.expEndStdCost = prevExp.stdCost + prodCost - saleCost
  line.expEndStdVariance = prevExp.stdVariance + prodVar - saleVar

  line.diffStdCost = n(line.actEndStdCost) - line.expEndStdCost

  return {
    line,
    nextExp: {
      qty: line.expEndQty,
      stdCost: line.expEndStdCost,
      stdVariance: line.expEndStdVariance,
    },
  }
}

export function enrichStdCostMonths(
  project: StdCostProductProject,
): StdCostMonthLine[] {
  const out: StdCostMonthLine[] = []
  let prevExp = { qty: 0, stdCost: 0, stdVariance: 0 }
  // 项目级标准单价：取首个非零月度标准单价
  const projectStdPrice =
    project.months.find((m) => m.stdUnitPrice > 0)?.stdUnitPrice ?? 0

  for (const raw of project.months) {
    const { line, nextExp } = enrichStdCostLine(raw, prevExp, projectStdPrice)
    out.push(line)
    prevExp = nextExp
  }
  return out
}

export function enrichStdCostProject(project: StdCostProductProject): StdCostProductProject {
  return { ...project, months: enrichStdCostMonths(project) }
}

export interface StdCostProjectTotals {
  prodQty: number
  prodStdCost: number
  prodStdVariance: number
  saleQty: number
  saleStdCost: number
  saleStdVariance: number
  diffStdCost: number
}

export function calcStdCostProjectTotals(months: StdCostMonthLine[]): StdCostProjectTotals {
  const body = months.filter((m) => m.kind !== 'opening')
  return {
    prodQty: calcSubtotal(body.map((m) => m.prodQty)),
    prodStdCost: calcSubtotal(body.map((m) => m.prodStdCost)),
    prodStdVariance: calcSubtotal(body.map((m) => m.prodStdVariance)),
    saleQty: calcSubtotal(body.map((m) => m.saleQty)),
    saleStdCost: calcSubtotal(body.map((m) => m.saleStdCost)),
    saleStdVariance: calcSubtotal(body.map((m) => m.saleStdVariance)),
    diffStdCost: calcSubtotal(body.map((m) => m.diffStdCost)),
  }
}

export function calcStdCostBundleDiff(projects: StdCostProductProject[]): number {
  return calcSubtotal(
    projects.flatMap((p) => p.months.map((m) => m.diffStdCost)),
  )
}

/** 迁移旧 F2-40 月度/扁平行结构 */
export function migrateToStdCostProjects(
  legacy: Array<Record<string, unknown>>,
): StdCostProductProject[] | null {
  if (!Array.isArray(legacy) || !legacy.length) return null

  const first = legacy[0] as Record<string, unknown>
  if (first && Array.isArray(first.months) && 'expEndStdCost' in (first.months[0] as object)) {
    const projects = legacy as unknown as StdCostProductProject[]
    return projects.length ? projects.slice(0, 12) : [emptyStdCostProject(1)]
  }

  // 旧 F2-38 式月度结构
  if (first && Array.isArray(first.months) && 'prodAmt' in (first.months[0] as object)) {
    const migrated = (legacy as Array<{ itemName?: string; remark?: string; stdPrice?: number; months: Array<Record<string, unknown>> }>)
      .slice(0, 8)
      .map((p, i) => {
        const proj = emptyStdCostProject(i + 1, String(p.itemName || ''))
        proj.remark = String(p.remark || '')
        const opening = p.months.find((m) => m.key === 'opening')
        if (opening) {
          proj.months[0].actEndQty = Number(opening.prodQty || 0)
          proj.months[0].actEndStdCost = Number(opening.prodAmt || 0)
        }
        p.months
          .filter((m) => m.key && m.key !== 'opening')
          .forEach((m) => {
            const mi = proj.months.find((x) => x.key === m.key)
            if (!mi) return
            mi.prodQty = Number(m.prodQty || 0)
            mi.stdUnitPrice = Number(m.prodPrice || p.stdPrice || 0)
            mi.prodStdCost = Number(m.prodAmt || 0)
            mi.saleQty = Number(m.saleQty || 0)
            mi.saleStdCost = Number(m.shouldAmt || m.saleAmt || 0)
            mi.actEndStdCost = Number(m.endAmt || 0)
            mi.actEndQty = Number(m.endQty || 0)
          })
        return proj
      })
    return migrated.length ? migrated.slice(0, 12) : [emptyStdCostProject(1)]
  }

  const projects = legacy.slice(0, 8).map((r, i) => {
    const p = emptyStdCostProject(i + 1, String(r.itemName || ''))
    p.months[0].actEndQty = Number(r.openingQty || 0)
    p.months[0].actEndStdCost = Number(r.openingAmt || 0)
    const jan = p.months[1]
    jan.prodQty = Number(r.inboundQty || 0)
    jan.stdUnitPrice = Number(r.stdPrice || 0)
    jan.saleQty = Number(r.issueQty || 0)
    jan.saleStdCost = Number(r.bookIssueAmt || 0)
    return p
  })
  return projects.length ? projects : [emptyStdCostProject(1)]
}

export const F2_40_DEFAULT_OBJECTIVE =
  '验证存货金额是否恰当，标准成本差异是否已正确记录和披露。选取样本存货品种，按标准成本法重新计算应结存与应结转，核对期末实际结存与推算结存的差异。'
