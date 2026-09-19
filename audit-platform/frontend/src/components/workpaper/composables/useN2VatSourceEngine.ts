/**
 * useN2VatSourceEngine — N2-6 增值税测算表「源模板四段」纯函数公式引擎
 *
 * Spec: .kiro/specs/n2-vat-calc-source-alignment/
 * Tasks: 1.1（公式）+ 1.2（固定项常量）
 * Requirements: 1.1, 1.3, 1.5, 2.3, 2.6, 3.3, 3.5, 4.1, 4.2, 6.2
 *
 * 权威依据 = `backend/wp_templates/N/N2 应交税费.xlsx` 的 `增值税测算表N2-6`（A1:H48，逐格实证）：
 *
 *   （一）增值税纳税申报表核对  R10 标题 / R11 表头 / R12~R21 共 10 固定项
 *        R11: A=项目 C=账面数据 D=纳税申报表数据 E=差异 F=原因
 *        ⚠ 源模板 E 列未预置公式，按审计口径取 `E = C − D`
 *        ⚠ 第 6 项「6.销项税额」= C17，第 7 项「7.进项税额」= C18 —— 被（二）（三）跨段引用
 *
 *   （二）增值税销项税金测算  R22 标题 / R23 表头 / R24~R27 数据行 / R28 合计
 *        R23: A=品种 B=销售额 C=免税·扣除销售额 D=计税收入 E=税率 F=应计销项税
 *        R24: `D24=B24-C24`   `F24=D24*E24`
 *        R28: `B28=SUM(B24:B27)` `C28=SUM(C24:C27)` `D28=SUM(D24:D27)` `F28=SUM(F24:F27)`（无税率列合计）
 *        R29: 待转销项税额期末减期初金额（F29）
 *        R30: 差异 `F30=C17-F28-F29`
 *
 *   （三）增值税进项税测算  R31 标题 / R32 表头 / R33~R34 数据行 / R35 合计
 *        R32: A=项目 D=购进货物/固定资产及接受劳务发生额 E=税率 F=测算数
 *        R33: `F33=D33*E33`
 *        R35: `D35=SUM(D33:D34)` `F35=SUM(F33:F34)`
 *        R36/R37/R38: 待抵扣 / 待认证 / 留抵（均「期末减期初」）
 *        R39: 差异 `F39=F35-F36-F37-F38-C18`
 *
 *   （四）特殊情况检查  R40 标题 / R41 表头（A=项目 D=金额）/ R42~R45 共 4 固定项
 *
 * 本模块为**零依赖 leaf**（不 import vue / 不 import 其它 composable），全部纯函数，便于单测与 PBT。
 * 派生值一律读时推导、禁持久化（平台铁律：D1 曾因持久化 `ratio` 用旧分母算出 162.50% 错值并同步进附注）。
 */

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全数值解析：null / undefined / 空串 / NaN / ±Infinity / 溢出字面量 一律归 0。
 *
 * 🔴 必须用 `Number.isFinite` 而非 `isNaN`：`parseFloat('Infinity')` 与 `Number('1e400')`
 *    都能通过 `!isNaN(x)` 检查，一旦漏进乘法/求和会让整表变 `NaN`（平台既有踩坑）。
 */
export function parseNum(v: unknown): number {
  if (v == null || v === '') return 0
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 金额求和（对任意长度数组安全，忽略非法值） */
export function sumAmounts(values: readonly unknown[]): number {
  let total = 0
  for (const v of values) total += parseNum(v)
  return total
}

// ─── （一）申报表核对 ────────────────────────────────────────────────────────

/**
 * （一）差异（源模板 R11 E 列「差异」）。
 *
 * 源模板 E 列未预置公式，按审计口径：`差异 E = 账面数据 C − 纳税申报表数据 D`。
 * 差异 ≠ 0 表示账面与申报表不符，须在 F 列「原因」说明。
 *
 * @param book     账面数据 C
 * @param declared 纳税申报表数据 D
 */
export function calcDeclarationDiff(book: unknown, declared: unknown): number {
  return parseNum(book) - parseNum(declared)
}

// ─── （二）销项税金测算 ──────────────────────────────────────────────────────

/**
 * （二）计税收入（源模板 `D24 = B24 − C24`）。
 *
 * @param sales       销售额 B
 * @param exemptSales 免税/扣除销售额 C
 */
export function calcTaxableRevenue(sales: unknown, exemptSales: unknown): number {
  return parseNum(sales) - parseNum(exemptSales)
}

/**
 * （二）应计销项税（源模板 `F24 = D24 × E24`）。
 *
 * @param taxableRevenue 计税收入 D（由 `calcTaxableRevenue` 派生）
 * @param rate           税率 E（小数形态，如 0.13）
 */
export function calcOutputTax(taxableRevenue: unknown, rate: unknown): number {
  return parseNum(taxableRevenue) * parseNum(rate)
}

/**
 * （二）差异（源模板 `F30 = C17 − F28 − F29`）。
 *
 * 🔴 跨段引用：`C17` 来自（一）第 6 项「6.销项税额」的**账面数据**列，
 *    不得取自附加分析区（按月/季矩阵），否则口径混淆。
 *
 * @param bookOutputTax    （一）C17 销项税额·账面数据
 * @param outputTaxTotal   （二）F28 应计销项税合计
 * @param pendingOutputTax （二）F29 待转销项税额期末减期初金额
 */
export function calcOutputVariance(
  bookOutputTax: unknown,
  outputTaxTotal: unknown,
  pendingOutputTax: unknown,
): number {
  return parseNum(bookOutputTax) - parseNum(outputTaxTotal) - parseNum(pendingOutputTax)
}

// ─── （三）进项税测算 ────────────────────────────────────────────────────────

/**
 * （三）测算数（源模板 `F33 = D33 × E33`）。
 *
 * @param amount 购进货物/固定资产及接受劳务发生额 D
 * @param rate   税率 E（小数形态）
 */
export function calcInputTax(amount: unknown, rate: unknown): number {
  return parseNum(amount) * parseNum(rate)
}

/** （三）三个调节项（源模板 R36/R37/R38，均为「期末减期初」金额） */
export interface N2VatInputAdjust {
  /** F36 待抵扣进项税额期末减期初金额 */
  deductible: number
  /** F37 待认证进项税额期末减期初金额 */
  uncertified: number
  /** F38 增值税留抵税额期末减期初金额 */
  retained: number
}

/**
 * （三）差异（源模板 `F39 = F35 − F36 − F37 − F38 − C18`）。
 *
 * 🔴 跨段引用：`C18` 来自（一）第 7 项「7.进项税额」的**账面数据**列。
 *
 * @param inputTaxTotal （三）F35 测算数合计
 * @param adjust        （三）F36/F37/F38 三调节项
 * @param bookInputTax  （一）C18 进项税额·账面数据
 */
export function calcInputVariance(
  inputTaxTotal: unknown,
  adjust: Partial<N2VatInputAdjust> | null | undefined,
  bookInputTax: unknown,
): number {
  return (
    parseNum(inputTaxTotal)
    - parseNum(adjust?.deductible)
    - parseNum(adjust?.uncertified)
    - parseNum(adjust?.retained)
    - parseNum(bookInputTax)
  )
}

// ─── R6：应交增值税口径（供 N2-8 城建税及附加计税依据） ───────────────────────

/**
 * 应交增值税（Requirements R6.2 口径）= （一）销项税额账面 C17 − （一）进项税额账面 C18。
 *
 * 🔴 该值写入 `N2-6-vat-payable`，被 `useN2CrossSheet.vatToSurtax` 读作 N2-8 城建税及附加的计税依据。
 *    口径必须取自源模板（一）段而非附加分析区，且（一）无数据时返回 0（不回退附加区），
 *    以免 N2-8 计税依据在两套口径间静默漂移（Requirements R6.3）。
 *
 * @param bookOutputTax （一）C17 销项税额·账面数据
 * @param bookInputTax  （一）C18 进项税额·账面数据
 */
export function calcVatPayableFromDeclaration(bookOutputTax: unknown, bookInputTax: unknown): number {
  return parseNum(bookOutputTax) - parseNum(bookInputTax)
}

// ─── 差异结论 ────────────────────────────────────────────────────────────────

/** 勾稽匹配阈值（0.01 元内视为匹配，与平台各循环一致） */
export const N2_VAT_MATCH_THRESHOLD = 0.01

/** 差异结论（供（二）（三）勾稽 bar 展示，含源模板公式原文以便溯源） */
export interface N2VatVariance {
  /** 源模板公式结果 */
  diff: number
  /** |diff| <= 0.01 视为匹配 */
  isMatch: boolean
  /** 展示用公式文字（源模板原文） */
  formula: string
}

/** 把差异数值包装为结论对象（保留 2 位小数，消除浮点尾差） */
export function buildVatVariance(diff: number, formula: string): N2VatVariance {
  const rounded = parseFloat(parseNum(diff).toFixed(2))
  return {
    diff: rounded,
    isMatch: Math.abs(rounded) <= N2_VAT_MATCH_THRESHOLD,
    formula,
  }
}

/** （二）差异公式原文（源模板 R30） */
export const N2_VAT_OUTPUT_VARIANCE_FORMULA
  = '差异 = （一）销项税额账面 − 应计销项税合计 − 待转销项税额期末减期初（源模板 F30 = C17 − F28 − F29）'

/** （三）差异公式原文（源模板 R39） */
export const N2_VAT_INPUT_VARIANCE_FORMULA
  = '差异 = 测算数合计 − 待抵扣 − 待认证 − 留抵 − （一）进项税额账面（源模板 F39 = F35 − F36 − F37 − F38 − C18）'

// ─── 固定项常量（Task 1.2；label 逐字取源模板，禁改动） ──────────────────────

/**
 * （一）增值税纳税申报表核对 10 个固定项（源模板 R12~R21 的 A 列，逐字含序号前缀与全角标点）。
 *
 * 🔴 源模板固定清单：不可增删、不可改名（Requirements 1.5）。
 *    `key` 为内部稳定标识（持久化用），改 key 会丢数据；`label` 供 UI 显示与守卫逐字比对。
 */
export const N2_VAT_DECLARATION_ITEMS = [
  { key: 'taxable-sales', label: '1.按适用税率征税销售额' },
  { key: 'deemed-sales', label: '2.视同销售' },
  { key: 'simplified', label: '3.按简易征收办法征税货物' },
  { key: 'export-refund', label: '4.免、抵、退办法出口销售额' },
  { key: 'exempt-sales', label: '5.免税销售额' },
  { key: 'output-tax', label: '6.销项税额' },
  { key: 'input-tax', label: '7.进项税额' },
  { key: 'input-transfer-out', label: '8.进项税额转出' },
  { key: 'export-refundable', label: '9.免、抵、退应退税额' },
  { key: 'other', label: '10.其他' },
] as const

/**
 * （四）特殊情况检查 4 个固定项（源模板 R42~R45 的 A 列，逐字）。
 * 同（一），不可增删改名（Requirements 4.2）。
 */
export const N2_VAT_SPECIAL_ITEMS = [
  { key: 'deemed-sales', label: '视同销售' },
  { key: 'large-input-transfer', label: '大额进项税转出' },
  { key: 'financial-goods', label: '转让金融商品应交增值税额' },
  { key: 'withholding', label: '代扣代缴增值税额' },
] as const

/**
 * （一）第 6 项「6.销项税额」的 key —— 即源模板 C17，被（二）差异公式跨段引用。
 * 🔴 禁在别处散落字面量 'output-tax'，一律引用本常量。
 */
export const N2_VAT_BOOK_OUTPUT_KEY = 'output-tax'

/**
 * （一）第 7 项「7.进项税额」的 key —— 即源模板 C18，被（三）差异公式跨段引用。
 * 🔴 禁在别处散落字面量 'input-tax'，一律引用本常量。
 */
export const N2_VAT_BOOK_INPUT_KEY = 'input-tax'

/** （二）（三）税率下拉预置档（源模板未限定，取现行增值税法定档次） */
export const N2_VAT_RATE_OPTIONS = [
  { value: 0.13, label: '13%' },
  { value: 0.09, label: '9%' },
  { value: 0.06, label: '6%' },
  { value: 0.05, label: '5%' },
  { value: 0.03, label: '3%' },
  { value: 0, label: '免税' },
] as const

export type N2VatDeclarationItemKey = typeof N2_VAT_DECLARATION_ITEMS[number]['key']
export type N2VatSpecialItemKey = typeof N2_VAT_SPECIAL_ITEMS[number]['key']
