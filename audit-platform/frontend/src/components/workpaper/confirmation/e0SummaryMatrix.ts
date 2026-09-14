/**
 * e0SummaryMatrix.ts — E0-1 品种矩阵纯函数（6 品种 × 6 指标）
 *
 * 源模板：`函证结果汇总表E0-1` R28:J34
 * - R28 E:J = 品种列头
 * - R29 = 本期（期末）账面金额（手工填写，无公式）
 * - R30 = 抽取样本的发函金额 = SUMIF(D:D, 品种, F:F)
 * - R31 = 发函金额占账面金额的比例 = IF(ISERROR(R30/R29), 0, R30/R29)
 * - R32 = 回函确认金额 = SUMIF(D:D, 品种, X:X)
 * - R33 = 回函可确认金额占发函金额的比例
 * - R34 = 回函可确认金额占账面金额的比例
 *
 * 设计约束（e0-confirmation-completion §3, Property 6/7）：
 * - 分母 0 → 比例为 0（对齐 ISERROR 兜底），绝不产出 NaN/Infinity
 * - bookAmounts 缺该品种 → 比例返回 null 渲染「—」，不填 0 冒充
 * - 除 bookAmounts 行外全部只读
 */

import type { ConfirmationRow } from './confirmationTypes'

export const E0_MATRIX_CATEGORIES = [
  '银行存款', '其他货币资金', '短期借款', '长期借款', '应付票据', '理财产品',
] as const

export type E0Category = typeof E0_MATRIX_CATEGORIES[number]

export const E0_MATRIX_METRICS = [
  '本期（期末）账面金额',
  '抽取样本的发函金额',
  '发函金额占账面金额的比例(%)',
  '回函确认金额',
  '回函可确认金额占发函金额的比例(%)',
  '回函可确认金额占账面金额的比例(%)',
] as const

export type E0Metric = typeof E0_MATRIX_METRICS[number]

export interface E0MatrixCell {
  category: E0Category
  metric: E0Metric
  /** null = 无法计算（账面金额缺）→ 渲染「—」 */
  value: number | null
  /** 'ratio' 时渲染百分比 */
  kind: 'amount' | 'ratio'
  /** true = 可手填（仅「本期（期末）账面金额」行） */
  editable: boolean
  /** 取数口径说明（溯源 tooltip） */
  sourceHint?: string
}

export interface E0MatrixInput {
  rows: readonly ConfirmationRow[]
  /** 账面金额（四表预填或手填），缺省 undefined ≠ 0 */
  bookAmounts?: Partial<Record<E0Category, number>>
}

/** 安全除法：分母 0 → 0；分子/分母 undefined → null */
function safeRatio(numerator: number | undefined | null, denominator: number | undefined | null): number | null {
  if (numerator == null || denominator == null) return null
  if (denominator === 0) return 0
  const r = numerator / denominator
  if (!Number.isFinite(r)) return 0
  return r
}

/** 按品种求和（对齐 SUMIF(D:D, 品种, F:F)） */
function sumByCategory(
  rows: readonly ConfirmationRow[],
  category: string,
  field: 'amount' | 'amount_orig' | 'confirmed_amount' | 'confirmed_amount_orig',
): number {
  let total = 0
  for (const row of rows) {
    if (row.account_type === category) {
      const v = (row as Record<string, unknown>)[field]
      if (typeof v === 'number' && Number.isFinite(v)) {
        total += v
      }
    }
  }
  return total
}

/**
 * 构建 6×6 品种矩阵。
 *
 * 返回按行主序排列的 36 个 cell（category 变化慢、metric 变化快 → 便于按品种列渲染）。
 * 实际用法：`matrix[catIdx * 6 + metricIdx]` 或按 category/metric 过滤。
 */
export function buildE0SummaryMatrix(input: E0MatrixInput): E0MatrixCell[][] {
  const { rows, bookAmounts } = input
  const result: E0MatrixCell[][] = []

  for (const category of E0_MATRIX_CATEGORIES) {
    const book = bookAmounts?.[category] ?? undefined
    // 发函金额 = Σ amount_orig（原币）；若无原币则用 amount（本位币）
    const sendAmount = sumByCategory(rows, category, 'amount_orig') || sumByCategory(rows, category, 'amount')
    // 回函确认 = Σ confirmed_amount_orig；若无则用 confirmed_amount
    const confirmAmount = sumByCategory(rows, category, 'confirmed_amount_orig') || sumByCategory(rows, category, 'confirmed_amount')

    const cells: E0MatrixCell[] = [
      // R29 账面金额（手工）
      { category, metric: E0_MATRIX_METRICS[0], value: book ?? null, kind: 'amount', editable: true, sourceHint: book != null ? '四表预填' : '请手工填写' },
      // R30 发函金额
      { category, metric: E0_MATRIX_METRICS[1], value: sendAmount, kind: 'amount', editable: false },
      // R31 发函占账面比例
      { category, metric: E0_MATRIX_METRICS[2], value: safeRatio(sendAmount, book), kind: 'ratio', editable: false },
      // R32 回函确认金额
      { category, metric: E0_MATRIX_METRICS[3], value: confirmAmount, kind: 'amount', editable: false },
      // R33 回函占发函比例
      { category, metric: E0_MATRIX_METRICS[4], value: safeRatio(confirmAmount, sendAmount), kind: 'ratio', editable: false },
      // R34 回函占账面比例
      { category, metric: E0_MATRIX_METRICS[5], value: safeRatio(confirmAmount, book), kind: 'ratio', editable: false },
    ]
    result.push(cells)
  }

  return result
}

/**
 * 账面金额取数口径（render 侧注入）。
 * 理财产品无固定科目 → 不预填。
 */
export const E0_BOOK_AMOUNT_SOURCES: Record<E0Category, { code: string; hint: string } | null> = {
  '银行存款': { code: '1002', hint: "TB('1002','期末余额')" },
  '其他货币资金': { code: '1012', hint: "TB('1012','期末余额')" },
  '短期借款': { code: '2001', hint: "TB('2001','期末余额')" },
  '长期借款': { code: '2501', hint: "TB('2501','期末余额') + 一年内到期部分" },
  '应付票据': { code: '2201', hint: "TB('2201','期末余额')" },
  '理财产品': null, // 无固定科目，不预填
}
