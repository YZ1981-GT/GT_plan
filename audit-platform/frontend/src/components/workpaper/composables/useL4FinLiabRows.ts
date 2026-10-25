/**
 * L4-3 划分为金融负债的其他金融工具明细表 —— 行模型 + 持久化（稳定 rowId）。
 *
 * spec: l-cycle-true-adapter-registration · Task 12（L4）
 *
 * 🔴 三方身份必须逐字一致（后端有判据守着）：
 *   · `L4_3_ROWS_ITEM_ID` ↔ `phase5_l4_sheets.STORE_ITEM_ID` ↔ 契约 `review.html_store.item_id`
 *   · 行身份键 `rowId` ↔ `ROW_IDENTITY_STORE_KEY`
 *   · 字段 json 键 ↔ `MANAGED_FIELD_SPECS_7` 第 5 位（模板 A..AM 列序）
 *
 * 旧形态 `L4-3-row-{index+1}-data` 是位置化行身份（删行只 splice 不重存、组件无 hydration，
 * 刷新即丢）；真库旧键 0 行 ⇒ 直接切新形态，不留回落路径。
 */
import { newRowIdentity } from './shared/rowIdentity'

export const L4_3_ROWS_ITEM_ID = 'L4-3-rows'

/** 数量/金额成对列的 json 词干（模板 L..AM 十四对）。 */
export const L4_3_PAIR_STEMS = [
  'unauditedPrior', 'unauditedIncrease', 'unauditedDecrease', 'unauditedEnd',
  'priorAje', 'priorRje',
  'ajeIncrease', 'ajeDecrease', 'rjeIncrease', 'rjeDecrease',
  'auditedPrior', 'auditedIncrease', 'auditedDecrease', 'auditedEnd',
] as const
export type L4PairStem = (typeof L4_3_PAIR_STEMS)[number]

/** 模板里是公式的词干（R/S、AF~AM）—— HTML 侧只显示计算值，不提供输入。 */
export const L4_3_FORMULA_STEMS: ReadonlySet<L4PairStem> = new Set([
  'unauditedEnd', 'auditedPrior', 'auditedIncrease', 'auditedDecrease', 'auditedEnd',
])

export interface L4FinLiabRow {
  rowId: string
  // ── 模板 A..K 标量列 ──
  instrumentName: string
  issueDate: string
  accountingClass: string
  rate: number
  issuePrice: number
  issueQty: number
  issueAmount: number
  maturity: string
  conversionTerms: string
  conversionStatus: string
  // ── 模板 L..AM 十四对（数量/金额）── 以 `${stem}Qty` / `${stem}Amount` 存
  [key: string]: string | number | boolean
}

/** 模板无对应列、保留在 HTML 侧的旧字段（不入契约，见 phase5_l4_sheets.HTML_ONLY_ROW_KEYS）。 */
export const L4_3_HTML_ONLY_KEYS = [
  'instrumentType', 'contractTerms', 'liabilityReason', 'initialAmount', 'endBalance', 'isFairValue',
] as const

export function createEmptyFinLiabRow(instrumentName = ''): L4FinLiabRow {
  const row: L4FinLiabRow = {
    rowId: newRowIdentity('l43'),
    instrumentName,
    issueDate: '',
    accountingClass: '',
    rate: 0,
    issuePrice: 0,
    issueQty: 0,
    issueAmount: 0,
    maturity: '',
    conversionTerms: '',
    conversionStatus: '',
    instrumentType: '',
    contractTerms: '',
    liabilityReason: '',
    initialAmount: 0,
    endBalance: 0,
    isFairValue: false,
  }
  for (const stem of L4_3_PAIR_STEMS) {
    row[`${stem}Qty`] = 0
    row[`${stem}Amount`] = 0
  }
  return row
}

const num = (v: unknown): number => {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 与模板逐行公式同口径（负债：期末 = 期初 + 增加 − 减少；审定 = 未审 + 账项 + 重分类）。
 * 只覆盖公式词干，不动用户输入列。
 */
export function applyL4_3Formulas(row: L4FinLiabRow): L4FinLiabRow {
  const out: L4FinLiabRow = { ...row }
  for (const unit of ['Qty', 'Amount'] as const) {
    const g = (stem: string): number => num(row[`${stem}${unit}`])
    out[`unauditedEnd${unit}`] = g('unauditedPrior') + g('unauditedIncrease') - g('unauditedDecrease')
    out[`auditedPrior${unit}`] = g('unauditedPrior') + g('priorAje') + g('priorRje')
    out[`auditedIncrease${unit}`] = g('unauditedIncrease') + g('ajeIncrease') + g('rjeIncrease')
    out[`auditedDecrease${unit}`] = g('unauditedDecrease') + g('ajeDecrease') + g('rjeDecrease')
    out[`auditedEnd${unit}`] =
      num(out[`auditedPrior${unit}`]) + num(out[`auditedIncrease${unit}`]) - num(out[`auditedDecrease${unit}`])
  }
  return out
}

/** 解析单条 item 的 JSON 数组；坏载荷给空表不半解析；缺 rowId 的行当场补铸。 */
export function parseL4_3Rows(raw: string | null | undefined): L4FinLiabRow[] {
  if (!raw) return []
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return []
  }
  if (!Array.isArray(parsed)) return []
  return parsed
    .filter((r): r is Record<string, unknown> => !!r && typeof r === 'object')
    .map((r) => {
      const base = createEmptyFinLiabRow()
      const merged = { ...base, ...(r as Partial<L4FinLiabRow>) } as L4FinLiabRow
      merged.rowId = typeof r.rowId === 'string' && r.rowId ? r.rowId : base.rowId
      return merged
    })
}

/** 整表序列化成一条 item；空表落 `null`（与 L1 同口径）。 */
export function serializeL4_3Rows(rows: readonly L4FinLiabRow[]): string | null {
  if (rows.length === 0) return null
  return JSON.stringify(rows.map(applyL4_3Formulas))
}

/** 按 rowId 删（排序/筛选后下标不可信时的正解）。 */
export function removeL4_3RowById(rows: readonly L4FinLiabRow[], rowId: string): L4FinLiabRow[] {
  return rows.filter((r) => r.rowId !== rowId)
}
