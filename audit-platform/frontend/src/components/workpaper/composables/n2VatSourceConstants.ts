/**
 * n2VatSourceConstants — N2-6 增值税测算表「源模板固定项清单」单一真源
 *
 * 常量全部取自致同源模板 `backend/wp_templates/N/N2 应交税费.xlsx`
 * 的 `增值税测算表N2-6` sheet（A1:H48），逐字对齐单元格文本：
 *
 * - `N2_VAT_DECLARATION_ITEMS` ←（一）增值税纳税申报表核对，源模板 **R12~R21**（10 项）
 * - `N2_VAT_SPECIAL_ITEMS`     ←（四）特殊情况检查，源模板 **R42~R45**（4 项）
 * - `N2_VAT_SECTION_TITLES`    ← 四个小节标题（源模板 A10 / A22 / A31 / A40）
 * - `N2_VAT_VARIANCE_FORMULA`  ←（二）R30 `F30=C17-F28-F29` /（三）R39 `F39=F35-F36-F37-F38-C18`
 *
 * 🔴 **固定清单不可增删改名**（含序号前缀、顿号、全角标点均为源模板原文）。
 * 改动须同步 wave 5 守卫（`__tests__/n2VatSourceContract.spec.ts` 内写死了同一份
 * 源模板字面量做逐字比对，Property 1；`__tests__/n2VatSourceEngine.spec.ts` 覆盖跨段公式）。
 *
 * 跨段依赖：（二）（三）的差异公式引用（一）的账面列 —— `F30` 用 C17「销项税额」、
 * `F39` 用 C18「进项税额」→ 故导出 `N2_VAT_BOOK_OUTPUT_KEY` / `N2_VAT_BOOK_INPUT_KEY`，
 * 禁止在数据层/组件层散落 `'output-tax'` / `'input-tax'` 字面量。
 *
 * 零依赖 leaf：本文件**不得 import 任何东西**（供纯函数引擎、数据层、组件与守卫共用）。
 *
 * Spec: .kiro/specs/n2-vat-calc-source-alignment/ Task 1.2
 * Requirements: 1.1, 1.5, 4.1, 4.2
 */

/**
 * （一）增值税纳税申报表核对 —— 10 个固定项目行
 * 源模板 `增值税测算表N2-6` R12~R21（A 列项目名逐字）。
 *
 * 注：`deemed-sales`（视同销售）在（一）与（四）都出现（源模板两处都有该项目），
 * 两个数组各自独立、互不冲突，属**有意为之**，勿去重。
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
 * （四）特殊情况检查 —— 4 个固定项目行
 * 源模板 `增值税测算表N2-6` R42~R45（A 列项目名逐字）。
 */
export const N2_VAT_SPECIAL_ITEMS = [
  { key: 'deemed-sales', label: '视同销售' },
  { key: 'large-input-transfer', label: '大额进项税转出' },
  { key: 'financial-goods', label: '转让金融商品应交增值税额' },
  { key: 'withholding', label: '代扣代缴增值税额' },
] as const

/** （一）第 6 项「销项税额」的 key —— 供（二）差异公式 F30 跨段引用 C17，禁散落字面量 */
export const N2_VAT_BOOK_OUTPUT_KEY = 'output-tax'
/** （一）第 7 项「进项税额」的 key —— 供（三）差异公式 F39 跨段引用 C18，禁散落字面量 */
export const N2_VAT_BOOK_INPUT_KEY = 'input-tax'

/**
 * 税率下拉 6 档（（二）销项税额 E 列 /（三）进项税额 E 列共用）
 * 一般纳税人 13%/9%/6%，简易征收 5%/3%，免税 0。
 * 🔴 税率不是金额，禁套用 `WpAmountInput` 千分符控件。
 */
export const N2_VAT_RATE_OPTIONS = [
  { value: 0.13, label: '13%' },
  { value: 0.09, label: '9%' },
  { value: 0.06, label: '6%' },
  { value: 0.05, label: '5%' },
  { value: 0.03, label: '3%' },
  { value: 0, label: '免税' },
] as const

/** 源模板四个小节标题（A10 / A22 / A31 / A40 原文），供 UI 区块标题与守卫比对 */
export const N2_VAT_SECTION_TITLES = {
  declaration: '（一）增值税纳税申报表核对',
  output: '（二）增值税销项税金测算',
  input: '（三）增值税进项税测算',
  special: '（四）特殊情况检查',
} as const

/**
 * 差异公式展示文字（供 UI tooltip 溯源，括注源模板单元格公式原文）
 * - output ← 源模板 R30：`F30=C17-F28-F29`
 * - input  ← 源模板 R39：`F39=F35-F36-F37-F38-C18`
 */
export const N2_VAT_VARIANCE_FORMULA = {
  output:
    '差异 = （一）销项税额账面 − 应计销项税合计 − 待转销项税额期末减期初金额（源模板 F30=C17-F28-F29）',
  input:
    '差异 = 测算数合计 − 待抵扣 − 待认证 − 留抵 − （一）进项税额账面（源模板 F39=F35-F36-F37-F38-C18）',
} as const

/** （一）固定项 key 联合类型（从 as const 推导，禁手写字符串联合） */
export type N2VatDeclarationKey = (typeof N2_VAT_DECLARATION_ITEMS)[number]['key']
/** （四）固定项 key 联合类型 */
export type N2VatSpecialKey = (typeof N2_VAT_SPECIAL_ITEMS)[number]['key']
