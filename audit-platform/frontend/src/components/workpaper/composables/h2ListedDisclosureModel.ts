/**
 * H2 附注披露（上市公司）数据模型
 *
 * 对齐源模板「附注披露信息（上市公司）」列结构（列不可改）：
 *  23、在建工程汇总（期末 / 上年年末）
 *  （1）①在建工程明细（账面余额/减值/净值 × 期末+上年年末）
 *  ②重要在建工程项目变动（含利息资本化）
 *  续表（预算/进度/资金来源）
 *  ③减值准备变动
 *  （2）工程物资（专用材料/设备/工器具/减值）
 */

export const H2_LISTED_ITEM = {
  summary: 'H2-listed-summary',
  detail: 'H2-listed-detail-rows',
  projects: 'H2-listed-project-rows',
  impairment: 'H2-listed-impairment-rows',
  materials: 'H2-listed-materials',
  noteImpairment: 'H2-listed-note-impairment',
  noteFundSource: 'H2-listed-note-fund-source',
  /** 抵押/所有权受限（自 H2-2 isMortgaged=Y 带入） */
  mortgageRows: 'H2-listed-mortgage-rows',
  noteMortgage: 'H2-listed-note-mortgage',
} as const

export const H2_LISTED_GUIDANCE = {
  impairment:
    '长期资产本期进行减值测试的，应披露可收回金额的具体确定方法。可收回金额按公允价值减去处置费用后的净额确定的，应披露公允价值和处置费用的确定方式、关键参数及其确定依据。可收回金额按预计未来现金流量的现值确定的，应披露预测期的年限、预测期及稳定期的关键参数及其确定依据。（15号文第十九条（十九））',
  impairmentNote:
    '注意：1、本年执行减值测试的，即使未计提减值，也要参照上述要求披露。2、估计可收回金额时通常不应使用重置成本法。',
  fundSource: '资金来源应区分募股资金、金融机构贷款和自筹、其他来源等。',
  progress: '工程进度不一定是投入进度。',
  mortgage: '说明抵押、担保等所有权或使用权受限的在建工程情况（可与 H2-2「是否抵押」勾稽）。',
} as const

export function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function newRowId(prefix = 'h2'): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

/** 汇总：在建工程 / 工程物资 */
export interface ListedSummaryRow {
  key: 'cip' | 'materials'
  label: string
  endBalance: number
  priorBalance: number
}

export function createDefaultListedSummary(): ListedSummaryRow[] {
  return [
    { key: 'cip', label: '在建工程', endBalance: 0, priorBalance: 0 },
    { key: 'materials', label: '工程物资', endBalance: 0, priorBalance: 0 },
  ]
}

export function listedSummaryTotal(rows: ListedSummaryRow[]): { endBalance: number; priorBalance: number } {
  return {
    endBalance: rows.reduce((s, r) => s + num(r.endBalance), 0),
    priorBalance: rows.reduce((s, r) => s + num(r.priorBalance), 0),
  }
}

/** ①在建工程明细（动态行） */
export interface ListedDetailRow {
  rowId: string
  name: string
  endBook: number
  endImpairment: number
  priorBook: number
  priorImpairment: number
}

export function listedDetailNet(book: number, impairment: number): number {
  return num(book) - num(impairment)
}

export function listedDetailSubtotal(rows: ListedDetailRow[]) {
  const endBook = rows.reduce((s, r) => s + num(r.endBook), 0)
  const endImpairment = rows.reduce((s, r) => s + num(r.endImpairment), 0)
  const priorBook = rows.reduce((s, r) => s + num(r.priorBook), 0)
  const priorImpairment = rows.reduce((s, r) => s + num(r.priorImpairment), 0)
  return {
    endBook,
    endImpairment,
    endNet: listedDetailNet(endBook, endImpairment),
    priorBook,
    priorImpairment,
    priorNet: listedDetailNet(priorBook, priorImpairment),
  }
}

/** ②重要项目变动 + 续表（同一行模型，两段列） */
export interface ListedProjectRow {
  rowId: string
  name: string
  beginBalance: number
  increase: number
  transferToFA: number
  otherDecrease: number
  interestCapAccum: number
  interestCapCurrent: number
  /** 本期利息资本化率 % */
  interestCapRate: number
  budget: number
  /** 工程累计投入占预算比例 %；0 时可由累计投入/预算推算 */
  cumInputPct: number
  /** 工程累计投入（可选，用于推算占比） */
  accumulatedInput: number
  progress: string
  fundSource: string
}

/** E = A + B − C − D */
export function listedProjectEnd(r: Pick<ListedProjectRow, 'beginBalance' | 'increase' | 'transferToFA' | 'otherDecrease'>): number {
  return num(r.beginBalance) + num(r.increase) - num(r.transferToFA) - num(r.otherDecrease)
}

export function listedProjectCumPct(r: ListedProjectRow): number {
  if (num(r.cumInputPct)) return num(r.cumInputPct)
  const budget = num(r.budget)
  if (budget <= 0) return 0
  const input = num(r.accumulatedInput) || listedProjectEnd(r)
  return Math.round((input / budget) * 10000) / 100
}

export function listedProjectSubtotal(rows: ListedProjectRow[]) {
  const beginBalance = rows.reduce((s, r) => s + num(r.beginBalance), 0)
  const increase = rows.reduce((s, r) => s + num(r.increase), 0)
  const transferToFA = rows.reduce((s, r) => s + num(r.transferToFA), 0)
  const otherDecrease = rows.reduce((s, r) => s + num(r.otherDecrease), 0)
  const interestCapAccum = rows.reduce((s, r) => s + num(r.interestCapAccum), 0)
  const interestCapCurrent = rows.reduce((s, r) => s + num(r.interestCapCurrent), 0)
  const budget = rows.reduce((s, r) => s + num(r.budget), 0)
  const accumulatedInput = rows.reduce((s, r) => s + num(r.accumulatedInput), 0)
  const endBalance = beginBalance + increase - transferToFA - otherDecrease
  return {
    beginBalance,
    increase,
    transferToFA,
    otherDecrease,
    interestCapAccum,
    interestCapCurrent,
    budget,
    accumulatedInput,
    endBalance,
    cumInputPct: budget > 0 ? Math.round((accumulatedInput / budget) * 10000) / 100 : 0,
  }
}

export function createEmptyListedProject(): ListedProjectRow {
  return {
    rowId: newRowId('proj'),
    name: '',
    beginBalance: 0,
    increase: 0,
    transferToFA: 0,
    otherDecrease: 0,
    interestCapAccum: 0,
    interestCapCurrent: 0,
    interestCapRate: 0,
    budget: 0,
    cumInputPct: 0,
    accumulatedInput: 0,
    progress: '',
    fundSource: '',
  }
}

/** ③减值准备 */
export interface ListedImpairmentRow {
  rowId: string
  name: string
  beginBalance: number
  provision: number
  decrease: number
}

export function listedImpairmentEnd(r: ListedImpairmentRow): number {
  return num(r.beginBalance) + num(r.provision) - num(r.decrease)
}

export function listedImpairmentSubtotal(rows: ListedImpairmentRow[]) {
  const beginBalance = rows.reduce((s, r) => s + num(r.beginBalance), 0)
  const provision = rows.reduce((s, r) => s + num(r.provision), 0)
  const decrease = rows.reduce((s, r) => s + num(r.decrease), 0)
  return { beginBalance, provision, decrease, endBalance: beginBalance + provision - decrease }
}

/** （2）工程物资 — 固定分类行，列结构不变 */
export type ListedMaterialKey = 'specialMaterial' | 'specialEquipment' | 'tools' | 'impairment'

export interface ListedMaterialRow {
  key: ListedMaterialKey
  label: string
  endBalance: number
  priorBalance: number
  /** 减值行为抵减 */
  isDeduction?: boolean
}

export function createDefaultListedMaterials(): ListedMaterialRow[] {
  return [
    { key: 'specialMaterial', label: '专用材料', endBalance: 0, priorBalance: 0 },
    { key: 'specialEquipment', label: '专用设备', endBalance: 0, priorBalance: 0 },
    { key: 'tools', label: '工器具', endBalance: 0, priorBalance: 0 },
    { key: 'impairment', label: '工程物资减值准备', endBalance: 0, priorBalance: 0, isDeduction: true },
  ]
}

export function listedMaterialsGross(rows: ListedMaterialRow[]): { endBalance: number; priorBalance: number } {
  const gross = rows.filter((r) => !r.isDeduction)
  return {
    endBalance: gross.reduce((s, r) => s + num(r.endBalance), 0),
    priorBalance: gross.reduce((s, r) => s + num(r.priorBalance), 0),
  }
}

export function listedMaterialsNet(rows: ListedMaterialRow[]): { endBalance: number; priorBalance: number } {
  const g = listedMaterialsGross(rows)
  const imp = rows.find((r) => r.isDeduction)
  return {
    endBalance: g.endBalance - num(imp?.endBalance),
    priorBalance: g.priorBalance - num(imp?.priorBalance),
  }
}

/** 从 H2-2 明细行映射重要项目 */
export interface H2DetailSourceRow {
  rowId?: string
  name?: string
  budget?: number
  completionRate?: number
  accumulatedInput?: number
  cipBegin?: number
  increaseTotal?: number
  increaseInterest?: number
  decrease?: number
  transferAmount?: number
  transferOut?: number
  cipEnd?: number
  endAudited?: number
  impairmentEnd?: number
  impairEndAud?: number
  netEndAud?: number
  fundSource?: string
  progress?: string
  isMortgaged?: string
  projectCode?: string
  remark?: string
}

/** 抵押/受限披露行 */
export interface ListedMortgageRow {
  rowId: string
  name: string
  /** 抵押对应账面金额（优先审定净值） */
  amount: number
  description: string
  remark: string
}

export function mapMortgagedDetailToRows(
  rows: Array<H2DetailSourceRow & { netEndAud?: number; endAudited?: number; cipEnd?: number }>,
): ListedMortgageRow[] {
  return (rows || [])
    .filter((r) => String(r.isMortgaged || '').toUpperCase() === 'Y' && String(r.name || '').trim())
    .map((r, i) => {
      const amount = num(r.netEndAud) || num(r.endAudited) || num(r.cipEnd)
      const code = r.projectCode ? `编号${r.projectCode}` : ''
      return {
        rowId: r.rowId || newRowId(`mort-${i}`),
        name: String(r.name || ''),
        amount,
        description: [code, '在建工程抵押/担保'].filter(Boolean).join('；'),
        remark: String(r.remark || ''),
      }
    })
}

export function buildMortgageNoteText(rows: ListedMortgageRow[]): string {
  if (!rows.length) return ''
  return rows
    .map((r) => {
      const amt = num(r.amount)
      const amtStr = amt
        ? amt.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
        : '—'
      return `${r.name}：抵押/担保金额 ${amtStr}${r.description ? `（${r.description}）` : ''}`
    })
    .join('\n')
}

export function mapDetailToListedProjects(rows: H2DetailSourceRow[]): ListedProjectRow[] {
  return (rows || [])
    .filter((r) => String(r.name || '').trim())
    .map((r, i) => {
      const begin = num(r.cipBegin)
      const increase = num(r.increaseTotal)
      const transfer = num(r.transferAmount)
      const otherDec = num(r.decrease) + num(r.transferOut)
      const interest = num(r.increaseInterest)
      const budget = num(r.budget)
      const accum = num(r.accumulatedInput)
      return {
        rowId: r.rowId || newRowId(`proj-${i}`),
        name: String(r.name || ''),
        beginBalance: begin,
        increase,
        transferToFA: transfer,
        otherDecrease: otherDec,
        interestCapAccum: interest,
        interestCapCurrent: interest,
        interestCapRate: 0,
        budget,
        cumInputPct: budget > 0 && accum > 0 ? Math.round((accum / budget) * 10000) / 100 : 0,
        accumulatedInput: accum,
        progress: r.progress != null ? String(r.progress) : (r.completionRate != null ? `${num(r.completionRate)}%` : ''),
        fundSource: String(r.fundSource || ''),
      }
    })
}

export function mapDetailToListedDetail(rows: H2DetailSourceRow[]): ListedDetailRow[] {
  return (rows || [])
    .filter((r) => String(r.name || '').trim())
    .map((r, i) => ({
      rowId: r.rowId || newRowId(`det-${i}`),
      name: String(r.name || ''),
      endBook: num(r.endAudited) || num(r.cipEnd),
      endImpairment: num(r.impairEndAud) || num(r.impairmentEnd),
      priorBook: num(r.cipBegin),
      priorImpairment: 0,
    }))
}
