/**
 * hCycleAmountControlRegistry — H 类披露表/审定表金额控件登记表（单一真源）
 *
 * Spec: `.kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/` Task 12
 * （R10.1 / R10.2）
 *
 * ## 为什么需要登记表
 *
 * 平台铁律：**可编辑金额千分符只能用 `el-input`**（实证 element-plus 2.13.6 的
 * `input-number` 编译产物全文无 `formatter`/`parser` prop ⇒ `:formatter` 是未知属性、
 * 千分符从未生效）⇒ 金额一律走 `components/workpaper/shared/WpAmountInput.vue`。
 *
 * 但同一张表里金额与**非金额数值**混排（利息资本化率 % / 工程累计投入占预算比例 %），
 * `WpAmountInput` 强制两位小数 + 千分符 + 右对齐，套到比率上会把 `5.25%` 显示成
 * `5.25`（尚可）但把 `12` 显示成 `12.00` 并加千分符逻辑（语义错）。
 * 故必须逐字段声明「哪些不是金额」，并由守卫**双向锁死**：
 *
 * - 正向：登记为金额的字段不得再出现 `el-input-number`
 * - 反向：登记为非金额的字段**必须**保持 `el-input-number`（防被"顺手统一"）
 *
 * ## 范围
 *
 * 本轮只覆盖**披露 Tab 与审定表**（用户可见的交付件口径表）。
 * 检查/测算类 Tab（`*TabRecoverable` / `*TabImpairment` / `*TabDepreciation*` /
 * `*TabAnalysis` / `*Tab*Check` 等 120+ 文件 / 700+ 处）本轮不动 ——
 * 与存量 40+ 处失效 `el-input-number :formatter` 一并另立 spec 收口。
 *
 * 数据来源：逐文件 openpyxl 无关，纯前端源码扫描（2026-08-06 实证 9 文件 / 131 处）。
 */

/** 本轮纳入替换的文件（相对 `components/workpaper/`），顺序即实证扫描序 */
export const H_AMOUNT_TARGET_FILES: readonly string[] = [
  'h1/core/H1TabAdjudication.vue',
  'h1/core/H1TabDisclosureListed.vue',
  'h1/core/H1TabDisclosureSoe.vue',
  'h2/core/H2TabDisclosureListed.vue',
  'h2/core/H2TabDisclosureSoe.vue',
  'h5/core/H5TabAdjudication.vue',
  'h7/core/H7TabAdjudicationCost.vue',
  'h7/core/H7TabAdjudicationFair.vue',
  'h9/core/H9TabAdjudication.vue',
] as const

/**
 * 非金额数值字段：**必须保持 `el-input-number`**，禁套 `WpAmountInput`。
 *
 * key = `{文件相对路径}::{v-model 绑定的字段名}`，value = 保留理由（守卫要求非空）。
 *
 * 🔴 实证只有 4 处（H2 两版各 2 处比率列）；H1/H5/H7/H9 的审定表与披露表
 * 全部字段都是金额（期初余额 / 本期借贷 / AJE / RJE / 账面原值 / 累计折旧 /
 * 减值准备 / 账面价值 / 预算数 / 利息资本化累计与本期金额…）。
 *
 * 注意：`interestCapAccum`（利息资本化**累计金额**）与 `interestCapCurrent`
 * （其中：本期利息资本化**金额**）是金额，只有 `interestCapRate`（**率 %**）不是 ——
 * 三者字段名前缀相同，按前缀匹配会误伤，故按**完整字段名**登记。
 */
export const H_NON_AMOUNT_FIELDS: Readonly<Record<string, string>> = Object.freeze({
  'h2/core/H2TabDisclosureListed.vue::interestCapRate':
    '源模板列头「本期利息资本化率%」—— 利率类，不加千分符、不强制两位小数',
  'h2/core/H2TabDisclosureListed.vue::cumInputPct':
    '源模板列头「工程累计投入占预算比例%」—— 比例类',
  'h2/core/H2TabDisclosureSoe.vue::interestCapRate':
    '源模板列头「本期利息资本化率(%)」—— 利率类（国企侧括号为半角，与上市侧不同）',
  'h2/core/H2TabDisclosureSoe.vue::cumInputPct':
    '源模板列头「工程累计投入占预算比例(%)」—— 比例类',
})

/** 登记表的 key 构造（守卫与脚本共用，避免两侧各拼一份） */
export function hAmountFieldKey(file: string, field: string): string {
  return `${file}::${field}`
}

/** 该字段是否登记为非金额（⇒ 保留 `el-input-number`） */
export function isHNonAmountField(file: string, field: string): boolean {
  return Object.prototype.hasOwnProperty.call(
    H_NON_AMOUNT_FIELDS,
    hAmountFieldKey(file, field),
  )
}

/**
 * 语义关键词（供守卫做**反向**兜底：登记表之外若出现这类字段名仍用
 * `WpAmountInput`，说明有人把比率类误当金额替换了）。
 */
export const H_NON_AMOUNT_NAME_HINTS: readonly string[] = [
  'Rate',
  'Pct',
  'Percent',
  'Ratio',
  'Years',
  'Months',
  'Count',
  'Qty',
] as const
