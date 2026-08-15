/**
 * I1 披露增强：审定勾稽、取数策略、检查表喂稿、编制校验、数据资源/摊销归属
 */
import { num } from './i1ListedDisclosureModel'
import {
  I1_LISTED_MOVEMENT_ROWS,
  i1ListedCellValue,
  i1ListedTotalCellValue,
  type I1ListedCategory,
  type MovementCellMap,
} from './i1ListedDisclosureModel'
import {
  I1_SOE_LAYER_META,
  layerTotal,
  type I1SoeLayerBlock,
} from './i1SoeDisclosureModel'

/** 审定字段优先：键存在（含合法 0）则用审定，避免账调为 0 时回退未审 */
export function preferAuditedAmount(
  row: Record<string, unknown> | null | undefined,
  auditedKey: string,
  unauditedKey: string,
): number {
  if (row != null && Object.prototype.hasOwnProperty.call(row, auditedKey) && row[auditedKey] != null && row[auditedKey] !== '') {
    return num(row[auditedKey])
  }
  return num(row?.[unauditedKey])
}

export interface I1DisclosureCrossCheck {
  costDiff: number
  amortDiff: number
  impairDiff: number
  hasCostWarning: boolean
  hasAmortWarning: boolean
  hasImpairWarning: boolean
  hasAnyWarning: boolean
  adjCost: number
  adjAmort: number
  adjImpair: number
  discCost: number
  discAmort: number
  discImpair: number
}

export function buildI1ListedCrossCheck(
  movement: MovementCellMap,
  categories: readonly I1ListedCategory[],
  adj: { cost: number; amort: number; impair: number },
): I1DisclosureCrossCheck {
  const costEnd = I1_LISTED_MOVEMENT_ROWS.find((r) => r.key === 'cost_end')!
  const amortEnd = I1_LISTED_MOVEMENT_ROWS.find((r) => r.key === 'amort_end')!
  const impEnd = I1_LISTED_MOVEMENT_ROWS.find((r) => r.key === 'imp_end')!
  const discCost = i1ListedTotalCellValue(movement, costEnd, categories)
  const discAmort = i1ListedTotalCellValue(movement, amortEnd, categories)
  const discImpair = i1ListedTotalCellValue(movement, impEnd, categories)
  const costDiff = discCost - num(adj.cost)
  const amortDiff = discAmort - num(adj.amort)
  const impairDiff = discImpair - num(adj.impair)
  const hasCostWarning = Math.abs(num(adj.cost)) > 0.005 && Math.abs(costDiff) > 0.01
  const hasAmortWarning = Math.abs(num(adj.amort)) > 0.005 && Math.abs(amortDiff) > 0.01
  const hasImpairWarning = Math.abs(num(adj.impair)) > 0.005 && Math.abs(impairDiff) > 0.01
  // 若审定尚未发布，也允许与 0 比：仅当披露侧非零且审定全 0 时不告警
  const adjAny = Math.abs(num(adj.cost)) + Math.abs(num(adj.amort)) + Math.abs(num(adj.impair)) > 0.01
  return {
    costDiff,
    amortDiff,
    impairDiff,
    hasCostWarning: adjAny && hasCostWarning,
    hasAmortWarning: adjAny && hasAmortWarning,
    hasImpairWarning: adjAny && hasImpairWarning,
    hasAnyWarning: adjAny && (hasCostWarning || hasAmortWarning || hasImpairWarning),
    adjCost: num(adj.cost),
    adjAmort: num(adj.amort),
    adjImpair: num(adj.impair),
    discCost,
    discAmort,
    discImpair,
  }
}

export function buildI1SoeCrossCheck(
  layers: I1SoeLayerBlock[],
  adj: { cost: number; amort: number; impair: number },
): I1DisclosureCrossCheck {
  const cost = layers.find((l) => l.layer === 'cost')
  const amort = layers.find((l) => l.layer === 'amort')
  const impair = layers.find((l) => l.layer === 'impair')
  const discCost = cost ? layerTotal(cost).end : 0
  const discAmort = amort ? layerTotal(amort).end : 0
  const discImpair = impair ? layerTotal(impair).end : 0
  const costDiff = discCost - num(adj.cost)
  const amortDiff = discAmort - num(adj.amort)
  const impairDiff = discImpair - num(adj.impair)
  const hasCostWarning = Math.abs(costDiff) > 0.01
  const hasAmortWarning = Math.abs(amortDiff) > 0.01
  const hasImpairWarning = Math.abs(impairDiff) > 0.01
  const adjAny = Math.abs(num(adj.cost)) + Math.abs(num(adj.amort)) + Math.abs(num(adj.impair)) > 0.01
  return {
    costDiff,
    amortDiff,
    impairDiff,
    hasCostWarning: adjAny && hasCostWarning,
    hasAmortWarning: adjAny && hasAmortWarning,
    hasImpairWarning: adjAny && hasImpairWarning,
    hasAnyWarning: adjAny && (hasCostWarning || hasAmortWarning || hasImpairWarning),
    adjCost: num(adj.cost),
    adjAmort: num(adj.amort),
    adjImpair: num(adj.impair),
    discCost,
    discAmort,
    discImpair,
  }
}

export interface I1DisclosurePrepValidation {
  ok: boolean
  blocking: string[]
  warnings: string[]
}

export function validateI1ListedPrep(params: {
  movement: MovementCellMap
  categories: readonly I1ListedCategory[]
  titleCertRows: Array<{ name: string; bookValue: number; reason: string }>
  cross?: I1DisclosureCrossCheck | null
}): I1DisclosurePrepValidation {
  const blocking: string[] = []
  const warnings: string[] = []
  const costIncKeys = ['cost_inc_purchase', 'cost_inc_rd', 'cost_inc_merge', 'cost_inc_other', 'cost_inc_ellipsis']
  const costDecKeys = ['cost_dec_dispose', 'cost_dec_expire', 'cost_dec_other']

  for (const cat of params.categories) {
    const begin = num(params.movement.cost_begin?.[cat.key])
    const incTotal = costIncKeys.reduce((s, k) => s + num(params.movement[k]?.[cat.key]), 0)
    const decTotal = costDecKeys.reduce((s, k) => s + num(params.movement[k]?.[cat.key]), 0)
    if (Math.abs(incTotal) + Math.abs(decTotal) + Math.abs(begin) < 0.005) continue
    // 有增加金额但方式全空（仅靠 ellipsis/other 也不强制）——若 begin+end 有值但无增减细项则跳过
    if (incTotal > 0.005) {
      const named = costIncKeys.slice(0, 4).reduce((s, k) => s + num(params.movement[k]?.[cat.key]), 0)
      if (named < 0.005 && num(params.movement.cost_inc_ellipsis?.[cat.key]) < 0.005) {
        warnings.push(`「${cat.label}」有原值增加但未填购置/研发/合并/其他方式`)
      }
    }
    const bookEndDef = I1_LISTED_MOVEMENT_ROWS.find((r) => r.key === 'book_end')!
    const book = i1ListedCellValue(params.movement, bookEndDef, cat.key)
    if (book < -0.01) blocking.push(`「${cat.label}」期末账面价值为负（${book.toFixed(2)}）`)
  }

  for (const r of params.titleCertRows || []) {
    if ((r.name || r.bookValue) && !String(r.reason || '').trim()) {
      warnings.push(`未办妥权属「${r.name || '未命名'}」未填原因`)
    }
  }

  if (params.cross?.hasAnyWarning) {
    warnings.push(
      `披露合计与 I1 审定差异：原值 ${params.cross.costDiff.toFixed(2)} / 摊销 ${params.cross.amortDiff.toFixed(2)} / 减值 ${params.cross.impairDiff.toFixed(2)}`,
    )
  }

  return { ok: blocking.length === 0, blocking, warnings }
}

export function validateI1SoePrep(params: {
  layers: I1SoeLayerBlock[]
  cross?: I1DisclosureCrossCheck | null
}): I1DisclosurePrepValidation {
  const blocking: string[] = []
  const warnings: string[] = []
  const carrying = params.layers.find((l) => l.layer === 'carrying')
  if (carrying) {
    for (const c of carrying.categories) {
      if (c.end < -0.01) blocking.push(`「${c.key}」账面价值为负（${c.end.toFixed(2)}）`)
    }
  }
  // 原价层有期末但增减与期初不一致已由公式保证；检查原价层空壳
  const cost = params.layers.find((l) => l.layer === 'cost')
  if (cost) {
    for (const c of cost.categories) {
      if (Math.abs(c.end) > 0.01 && Math.abs(c.begin) + Math.abs(c.increase) + Math.abs(c.decrease) < 0.005) {
        warnings.push(`分类 ${c.key} 期末有数但期初/增减均为空`)
      }
    }
  }
  void I1_SOE_LAYER_META
  if (params.cross?.hasAnyWarning) {
    warnings.push(
      `披露合计与 I1 审定差异：原值 ${params.cross.costDiff.toFixed(2)} / 摊销 ${params.cross.amortDiff.toFixed(2)} / 减值 ${params.cross.impairDiff.toFixed(2)}`,
    )
  }
  return { ok: blocking.length === 0, blocking, warnings }
}

/** 仅当目标为空时写入草稿 */
export function fillNoteIfEmpty(current: string, draft: string): string {
  if (String(current || '').trim()) return current
  return String(draft || '').trim()
}

export function draftImpairmentNoteFromI112(rows: any[]): string {
  if (!Array.isArray(rows) || !rows.length) return ''
  const tested = rows.filter((r) => r.needTest === 'Y' || r.needTest === true || num(r.supplement) || num(r.alreadyProvided))
  if (!tested.length) return ''
  const supplement = tested.reduce((s, r) => s + num(r.supplement), 0)
  const fmt = (n: number) => n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const lines = tested
    .filter((r) => r.hasIndication === 'Y' || num(r.supplement) > 0)
    .slice(0, 8)
    .map((r) => `· ${r.name || '未命名'}：应提 ${fmt(num(r.impairmentAmount ?? r.shouldProvision))}，已提 ${fmt(num(r.alreadyProvided))}，补提 ${fmt(num(r.supplement))}`)
  let text = `本期对 ${tested.length} 项无形资产执行减值测试（来源 I1-12）。本期补提减值准备合计 ${fmt(supplement)} 元。`
  if (lines.length) text += `\n有迹象/补提项目：\n${lines.join('\n')}`
  text += '\n可收回金额确定方法及参数详见 I1-13；即使未计提减值，亦已按准则要求执行测试。'
  return text
}

export function draftSaleNoteFromI16(rows: any[]): string {
  if (!Array.isArray(rows) || !rows.length) return ''
  const high = rows.filter((r) => {
    const gain = num(r.disposalGainLoss)
    const net = num(r.netBookValue)
    const unfair = r.salePriceFair === 'N'
    return unfair || (net > 0 && gain / net > 0.2) || gain > 100000
  })
  if (!high.length) return ''
  const parts = high.slice(0, 5).map((r) => {
    const name = r.name || '未命名'
    const income = num(r.disposalIncome)
    const net = num(r.netBookValue)
    const gain = num(r.disposalGainLoss)
    return `· ${name}：清理收入 ${income.toFixed(2)}，净值 ${net.toFixed(2)}，净损益 ${gain.toFixed(2)}${r.salePriceFair === 'N' ? '（售价公允性存疑）' : ''}`
  })
  return `本期存在以明显高于账面价值出售或公允性需关注的减少事项（来源 I1-6）：\n${parts.join('\n')}\n交易作价基础、估值模型及敏感性分析须补充披露。`
}

export function draftTitleRowsFromI18(rows: any[]): Array<{ rowId: string; name: string; bookValue: number; reason: string }> {
  if (!Array.isArray(rows)) return []
  return rows
    .filter((r) => r.hasCertificate === 'N' || r.hasTitleEvidence === 'N' || r.certificateComplete === 'N')
    .map((r, i) => ({
      rowId: `tc-i18-${r.rowId || i}`,
      name: String(r.name || ''),
      bookValue: num(r.netBookValue ?? r.bookValue),
      reason: String(r.noCertReason || r.remark || ''),
    }))
    .filter((r) => r.name || r.bookValue)
}

export function draftMortgageNoteFromI18(rows: any[]): string {
  if (!Array.isArray(rows) || !rows.length) return ''
  const m = rows.filter((r) => r.mortgageRestricted === 'Y' || r.isMortgaged === 'Y' || r.isMortgaged === true)
  if (!m.length) return ''
  const total = m.reduce((s, r) => s + num(r.mortgageValue ?? r.netBookValue), 0)
  const names = m.slice(0, 5).map((r) => r.name || '未命名').join('、')
  return `权属检查（I1-8）显示抵押/受限无形资产 ${m.length} 项（${names}${m.length > 5 ? '等' : ''}），抵押相关账面约 ${total.toFixed(2)} 元。`
}

export interface I1AmortAllocSummary {
  productionCost: number
  manufacturing: number
  selling: number
  management: number
  rd: number
  other: number
  total: number
}

export function aggregateI19AmortAlloc(rows: any[]): I1AmortAllocSummary {
  const out: I1AmortAllocSummary = {
    productionCost: 0,
    manufacturing: 0,
    selling: 0,
    management: 0,
    rd: 0,
    other: 0,
    total: 0,
  }
  if (!Array.isArray(rows)) return out
  for (const r of rows) {
    out.productionCost += num(r.productionCost)
    out.manufacturing += num(r.manufacturingExpense ?? r.manufacturing)
    out.selling += num(r.sellingExpense ?? r.selling)
    out.management += num(r.managementExpense ?? r.admin)
    out.rd += num(r.rdExpense ?? r.rd)
    out.other += num(r.otherExpense ?? r.other)
  }
  out.total = out.productionCost + out.manufacturing + out.selling + out.management + out.rd + out.other
  return out
}

export function formatAmortAllocNote(a: I1AmortAllocSummary): string {
  if (Math.abs(a.total) < 0.005) return ''
  const fmt = (n: number) => n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `本期摊销费用合计 ${fmt(a.total)} 元，其中：生产成本 ${fmt(a.productionCost)}、制造费用 ${fmt(a.manufacturing)}、销售费用 ${fmt(a.selling)}、管理费用 ${fmt(a.management)}、研发费用 ${fmt(a.rd)}、其他 ${fmt(a.other)}（来源 I1-9）。`
}

/** 上市分类预设：精简（对齐 note_template 表头）/ 全量（对齐 Excel） */
export const I1_LISTED_COMPACT_CATEGORIES: readonly I1ListedCategory[] = [
  { key: 'land', label: '土地使用权' },
  { key: 'patent', label: '专利权' },
  { key: 'knowhow', label: '非专利技术' },
  { key: 'data', label: '数据资源' },
] as const

export type I1ListedCategoryPreset = 'compact' | 'full'

/** 数据资源独立子表行（对齐 note_template「确认为无形资产的数据资源」精简版） */
export interface I1DataResourceMove {
  costBegin: number
  costIncPurchase: number
  costIncRd: number
  costIncOther: number
  costDec: number
  amortBegin: number
  amortInc: number
  amortDec: number
  impairBegin: number
  impairInc: number
  impairDec: number
  note: string
}

export function emptyDataResourceMove(): I1DataResourceMove {
  return {
    costBegin: 0,
    costIncPurchase: 0,
    costIncRd: 0,
    costIncOther: 0,
    costDec: 0,
    amortBegin: 0,
    amortInc: 0,
    amortDec: 0,
    impairBegin: 0,
    impairInc: 0,
    impairDec: 0,
    note: '',
  }
}

export function dataResourceCostEnd(m: I1DataResourceMove): number {
  return num(m.costBegin) + num(m.costIncPurchase) + num(m.costIncRd) + num(m.costIncOther) - num(m.costDec)
}

export function dataResourceAmortEnd(m: I1DataResourceMove): number {
  return num(m.amortBegin) + num(m.amortInc) - num(m.amortDec)
}

export function dataResourceImpairEnd(m: I1DataResourceMove): number {
  return num(m.impairBegin) + num(m.impairInc) - num(m.impairDec)
}

export function dataResourceBookEnd(m: I1DataResourceMove): number {
  return dataResourceCostEnd(m) - dataResourceAmortEnd(m) - dataResourceImpairEnd(m)
}

/** 从上市 movement 的 data 列回填数据资源子表 */
export function pullDataResourceFromListedMovement(map: MovementCellMap): I1DataResourceMove {
  const g = (k: string) => num(map[k]?.data)
  return {
    costBegin: g('cost_begin'),
    costIncPurchase: g('cost_inc_purchase'),
    costIncRd: g('cost_inc_rd'),
    costIncOther: g('cost_inc_other') + g('cost_inc_merge') + g('cost_inc_ellipsis'),
    costDec: g('cost_dec_dispose') + g('cost_dec_expire') + g('cost_dec_other'),
    amortBegin: g('amort_begin'),
    amortInc: g('amort_inc_provision') + g('amort_inc_other') + g('amort_inc_ellipsis'),
    amortDec: g('amort_dec_dispose') + g('amort_dec_expire') + g('amort_dec_other'),
    impairBegin: g('imp_begin'),
    impairInc: g('imp_inc_provision') + g('imp_inc_other') + g('imp_inc_ellipsis'),
    // 与上面 costDec / amortDec 同构：源模板减值准备减少段是 处置/失效且终止确认的部分/其他减少
    // 三个明细，无扩位（改造前误用 `imp_dec_ellipsis`，见 i1ListedDisclosureModel 内注释）
    impairDec: g('imp_dec_dispose') + g('imp_dec_expire') + g('imp_dec_other'),
    note: '',
  }
}

export function buildDataResourceSubTableRows(m: I1DataResourceMove): Record<string, unknown>[] {
  const costEnd = dataResourceCostEnd(m)
  const amortEnd = dataResourceAmortEnd(m)
  const impairEnd = dataResourceImpairEnd(m)
  const bookEnd = dataResourceBookEnd(m)
  const bookBegin = num(m.costBegin) - num(m.amortBegin) - num(m.impairBegin)
  return [
    { label: '一、账面原值', is_section: true },
    { label: '1.期初余额', 外购的数据资源无形资产: m.costBegin, 自行开发的数据资源无形资产: 0, 其他方式取得的数据资源无形资产: 0, 合计: m.costBegin },
    { label: '2.本期增加金额', 外购的数据资源无形资产: m.costIncPurchase, 自行开发的数据资源无形资产: m.costIncRd, 其他方式取得的数据资源无形资产: m.costIncOther, 合计: m.costIncPurchase + m.costIncRd + m.costIncOther },
    { label: '其中：购入', 外购的数据资源无形资产: m.costIncPurchase, 自行开发的数据资源无形资产: 0, 其他方式取得的数据资源无形资产: 0, 合计: m.costIncPurchase },
    { label: '内部研发', 外购的数据资源无形资产: 0, 自行开发的数据资源无形资产: m.costIncRd, 其他方式取得的数据资源无形资产: 0, 合计: m.costIncRd },
    { label: '3.本期减少金额', 合计: m.costDec },
    { label: '4.期末余额', 合计: costEnd, is_total: true },
    { label: '二、累计摊销', is_section: true },
    { label: '1.期初余额', 合计: m.amortBegin },
    { label: '2.本期增加金额', 合计: m.amortInc },
    { label: '3.本期减少金额', 合计: m.amortDec },
    { label: '4.期末余额', 合计: amortEnd, is_total: true },
    { label: '三、减值准备', is_section: true },
    { label: '1.期初余额', 合计: m.impairBegin },
    { label: '2.本期增加金额', 合计: m.impairInc },
    { label: '3.本期减少金额', 合计: m.impairDec },
    { label: '4.期末余额', 合计: impairEnd, is_total: true },
    { label: '四、账面价值', is_section: true },
    { label: '1.期末账面价值', 合计: bookEnd, is_total: true },
    { label: '2.期初账面价值', 合计: bookBegin, is_total: true },
  ]
}

export function readI1AdjAudited(map: Map<string, any>): { cost: number; amort: number; impair: number } {
  const read = (key: string) => {
    const item = map.get(key)
    if (!item) return 0
    const raw = item.remark ?? item.conclusion
    return num(raw)
  }
  return {
    cost: read('I1-adj-audited-cost'),
    amort: read('I1-adj-audited-amort'),
    impair: read('I1-adj-audited-impairment'),
  }
}
